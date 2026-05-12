"""Structured weekly operator briefing — Markdown + voice-readable plain text."""

from __future__ import annotations

import json
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from src.narrative import NarrativeProvider, _resolve_provider

if TYPE_CHECKING:
    from src.llm_cost import CostTracker

logger = logging.getLogger(__name__)

# Cheap default model per provider
_ANTHROPIC_BRIEFING_MODEL = "claude-haiku-4-5"
_GITHUB_MODELS_BRIEFING_MODEL = "gpt-4o-mini"

# How many repos for each section
_SHIPPED_WINDOW_DAYS = 7
_NEEDS_ATTENTION_TOP_N = 5
_HEALTH_DELTA_TOP_N = 3
_SUGGESTION_TOP_N = 3


# ── Data model ───────────────────────────────────────────────────────────────


@dataclass
class ShippedRepo:
    name: str
    language: str
    automation_status: str  # "eligible" | "not-eligible" | "unknown"


@dataclass
class NeedsAttentionRepo:
    name: str
    overall_score: float
    days_since_push: int
    reason: str


@dataclass
class ScoreMover:
    name: str
    old_score: float
    new_score: float
    delta: float


@dataclass
class Suggestion:
    name: str
    action: str


@dataclass(frozen=True)
class InitiativeStatus:
    repo_name: str
    current_tier: int
    target_tier: int
    deadline: str
    status: str  # "on-track" | "at-risk" | "overdue" | "met"


@dataclass(frozen=True)
class InitiativeSuggestionRow:
    repo_name: str
    current_tier: int
    target_tier: int
    rationale: str
    estimated_effort: str


@dataclass(frozen=True)
class DismissedRepoRow:
    repo_name: str
    reason: str
    expires_at: str | None = None  # ISO date or None for permanent


@dataclass
class Briefing:
    username: str
    date: str
    shipped_this_week: list[ShippedRepo] = field(default_factory=list)
    needs_attention: list[NeedsAttentionRepo] = field(default_factory=list)
    health_delta: dict[str, list[ScoreMover]] = field(default_factory=dict)  # up/down keys
    suggestions: list[Suggestion] = field(default_factory=list)
    suppressed_by_prefs: list[str] = field(default_factory=list)  # repo names skipped due to prefs
    initiatives: list[InitiativeStatus] = field(default_factory=list)
    suggested_initiatives: list[InitiativeSuggestionRow] = field(default_factory=list)
    dismissed_repos: list[DismissedRepoRow] = field(default_factory=list)


# ── Section builders ─────────────────────────────────────────────────────────


def _parse_pushed_at(pushed_at: str | None) -> datetime | None:
    if not pushed_at:
        return None
    try:
        # Handle both Z suffix and +00:00 offsets
        s = pushed_at.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _days_since(pushed_at: str | None) -> int | None:
    dt = _parse_pushed_at(pushed_at)
    if dt is None:
        return None
    now = datetime.now(timezone.utc)
    return (now - dt).days


def _build_shipped(audits: list[dict]) -> list[ShippedRepo]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=_SHIPPED_WINDOW_DAYS)
    shipped = []
    for audit in audits:
        meta = audit.get("metadata", {})
        pushed_at = meta.get("pushed_at")
        dt = _parse_pushed_at(pushed_at)
        if dt is None or dt < cutoff:
            continue
        name = meta.get("name", "unknown")
        language = meta.get("language") or "unknown"
        cat = audit.get("portfolio_catalog", {})
        auto = cat.get("automation_eligible")
        if auto is True:
            automation_status = "eligible"
        elif auto is False:
            automation_status = "not-eligible"
        else:
            automation_status = "unknown"
        shipped.append(
            ShippedRepo(name=name, language=language, automation_status=automation_status)
        )
    shipped.sort(key=lambda r: r.name)
    return shipped


def _build_needs_attention(audits: list[dict]) -> list[NeedsAttentionRepo]:
    """
    Top-N repos ranked by the gap between completeness score (higher = more done) and
    recency (lower days_since_push = more recently touched).

    Attention score = (1 - overall_score) * log1p(days_since_push + 1)

    A high-scoring untouched repo ranks below a low-scoring frequently-touched one —
    this matches the control-center "urgent" heuristic: repos that aren't improving
    despite existing completeness debt.
    """
    import math

    candidates = []
    for audit in audits:
        name = audit.get("metadata", {}).get("name", "unknown")
        overall_score = audit.get("overall_score", 0.0)
        # Extract days_since_push from activity analyzer result
        days_since: int | None = None
        for ar in audit.get("analyzer_results", []):
            if ar.get("dimension") == "activity":
                details = ar.get("details") or {}
                if isinstance(details, dict):
                    days_since = details.get("days_since_push")
                break
        if days_since is None:
            pushed = audit.get("metadata", {}).get("pushed_at")
            days_since = _days_since(pushed) or 0

        gap_score = (1.0 - overall_score) * math.log1p(days_since + 1)
        reason = _attention_reason(overall_score, days_since)
        candidates.append(
            (
                gap_score,
                NeedsAttentionRepo(
                    name=name,
                    overall_score=round(overall_score, 3),
                    days_since_push=days_since,
                    reason=reason,
                ),
            )
        )

    candidates.sort(key=lambda t: t[0], reverse=True)
    return [item for _, item in candidates[:_NEEDS_ATTENTION_TOP_N]]


def _attention_reason(score: float, days_since: int) -> str:
    if score < 0.3:
        return f"low completeness ({score:.0%}) untouched for {days_since}d"
    if days_since > 180:
        return f"dormant {days_since}d, completeness {score:.0%}"
    if score < 0.5:
        return f"completeness {score:.0%}, last push {days_since}d ago"
    return f"completeness gap ({score:.0%}), last push {days_since}d ago"


def _build_health_delta(
    audits: list[dict], use_history: bool = True
) -> dict[str, list[ScoreMover]]:
    """
    Compare current run score vs. the most recent archived run from history.
    Returns {"up": [...top-3...], "down": [...top-3...]}.
    Falls back to empty lists if no history is available.

    load_repo_score_history() returns {repo_name: [oldest_score, ..., newest_score]}
    (chronological order). The current run's score is in `audits` and has NOT yet
    been archived, so history[-1] is the previous run's score.
    """
    if not use_history:
        return {"up": [], "down": []}

    # Build current score map from the audits passed in
    current_scores: dict[str, float] = {
        a.get("metadata", {}).get("name", ""): a.get("overall_score", 0.0)
        for a in audits
        if a.get("metadata", {}).get("name")
    }

    try:
        from src.history import load_repo_score_history

        score_history = load_repo_score_history()
        if not score_history:
            return {"up": [], "down": []}

        movers: list[ScoreMover] = []
        for name, current_score in current_scores.items():
            history = score_history.get(name, [])
            if not history:
                continue
            # history is chronological (oldest→newest); last entry = most recent archived run
            prev_score = float(history[-1])
            delta = current_score - prev_score
            if abs(delta) < 0.005:
                continue
            movers.append(
                ScoreMover(
                    name=name,
                    old_score=round(prev_score, 3),
                    new_score=round(current_score, 3),
                    delta=round(delta, 3),
                )
            )

        movers.sort(key=lambda m: m.delta, reverse=True)
        up = [m for m in movers if m.delta > 0][:_HEALTH_DELTA_TOP_N]
        down = sorted([m for m in movers if m.delta < 0], key=lambda m: m.delta)[
            :_HEALTH_DELTA_TOP_N
        ]
        return {"up": up, "down": down}

    except Exception as exc:
        logger.warning("health_delta computation skipped: %s", exc)
        return {"up": [], "down": []}


def _build_suggestions(
    audits: list[dict],
    provider: NarrativeProvider | None,
    model: str,
    *,
    prefs: dict | None = None,
    semantic_index: object | None = None,
    cost_tracker: CostTracker | None = None,
) -> tuple[list[Suggestion], list[str]]:
    """Generate one-sentence "suggested next action" for top-N repos.

    Uses LLM if provider is available; returns empty list on any failure.

    Returns ``(suggestions, suppressed_names)`` where *suppressed_names* lists
    repo names that were filtered out by active operator preference suppressions.

    If *semantic_index* is provided (a :class:`SemanticIndex` instance), the
    top-N repo summaries are enriched with their nearest neighbors so that the
    LLM prompt can suggest cross-repo consolidation opportunities.
    """
    from src.operator_prefs import is_suppressed

    # Pick top-N by hotspot priority or lowest-scoring actionable repos
    sorted_audits = sorted(audits, key=lambda a: a.get("overall_score", 1.0))

    # Filter out suppressed repos/actions if prefs are provided
    suppressed_names: list[str] = []
    eligible: list[dict] = []
    if prefs:
        for audit in sorted_audits:
            repo_name = audit.get("metadata", {}).get("name", "")
            hotspots = audit.get("hotspots", [])
            top_hotspot_type = hotspots[0].get("category", "") if hotspots else ""
            # Check suppression: action_type=hotspot category, target_context=repo name or "*"
            suppressed = (
                is_suppressed(prefs, top_hotspot_type, repo_name) if top_hotspot_type else None
            )
            if suppressed is not None:
                suppressed_names.append(repo_name)
            else:
                eligible.append(audit)
    else:
        eligible = sorted_audits

    top_repos = eligible[:_SUGGESTION_TOP_N]
    if not top_repos:
        return [], suppressed_names

    if provider is None:
        return [], suppressed_names

    # Optionally enrich each repo summary with related repos from semantic index
    related_by_repo: dict[str, list[str]] = {}
    if semantic_index is not None:
        for audit in top_repos:
            name = audit.get("metadata", {}).get("name", "")
            if not name:
                continue
            try:
                neighbors = semantic_index.find_neighbors(name, k=3)  # type: ignore[union-attr]
                related = [
                    n.repo_name for n in neighbors if n.score <= 0.3
                ]  # distance ≤ 0.3 → sim ≥ 0.7
                if related:
                    related_by_repo[name] = related
            except Exception as exc:
                logger.debug("briefing: semantic neighbor lookup failed for %r: %s", name, exc)

    # Build a compact summary per repo
    summaries = []
    for audit in top_repos:
        name = audit.get("metadata", {}).get("name", "?")
        score = audit.get("overall_score", 0.0)
        lang = audit.get("metadata", {}).get("language") or "unknown"
        hotspots = audit.get("hotspots", [])
        top_hotspot = hotspots[0].get("title", "no hotspot") if hotspots else "no hotspot"
        line = f"- {name} (lang={lang}, score={score:.2f}, top-hotspot={top_hotspot})"
        related = related_by_repo.get(name, [])
        if related:
            line += f" [related: {', '.join(related)}]"
        summaries.append(line)

    repo_block = "\n".join(summaries)
    cross_repo_note = (
        " Where repos share a 'related' annotation, consider whether consolidation "
        "or cross-repo patterns would be the most impactful suggestion."
        if related_by_repo
        else ""
    )
    prompt = (
        "You are a portfolio advisor. For each repository below, write ONE short, actionable "
        "sentence (under 20 words) suggesting the single most impactful improvement the developer "
        "should make this week. Return ONLY a JSON array of strings, one per repo, in the same "
        f"order as the input.{cross_repo_note}\n\n"
        f"Repositories:\n{repo_block}\n\n"
        "Response (JSON array only, no explanation):"
    )

    try:
        raw = provider.generate(
            prompt, model, max_tokens=150, cost_tracker=cost_tracker, feature="briefing-suggestion"
        )
    except Exception as exc:
        logger.warning("briefing suggestion LLM call failed: %s", exc)
        return [], suppressed_names

    suggestions = _parse_suggestions_json(raw, top_repos)
    return suggestions, suppressed_names


def _parse_suggestions_json(raw: str, top_repos: list[dict]) -> list[Suggestion]:
    """Parse LLM JSON response; fall back to regex extraction on failure."""
    # Try strict JSON first
    try:
        parsed = json.loads(raw.strip())
        if isinstance(parsed, list):
            result = []
            for i, repo in enumerate(top_repos):
                name = repo.get("metadata", {}).get("name", "?")
                action = str(parsed[i]) if i < len(parsed) else ""
                result.append(Suggestion(name=name, action=action))
            return result
    except (json.JSONDecodeError, IndexError, TypeError):
        pass

    # Regex fallback: extract quoted strings
    matches = re.findall(r'"([^"]+)"', raw)
    if matches:
        result = []
        for i, repo in enumerate(top_repos):
            name = repo.get("metadata", {}).get("name", "?")
            action = matches[i] if i < len(matches) else ""
            result.append(Suggestion(name=name, action=action))
        return result

    logger.warning("briefing: could not parse LLM suggestions response, using empty suggestions")
    return []


# ── Public build entry point ─────────────────────────────────────────────────


def _build_initiatives(
    audits: list[dict],
    output_dir: Path | None,
) -> list[InitiativeStatus]:
    """Load open initiatives and derive their current status.

    Returns an empty list if *output_dir* is ``None``, the file is missing, or
    no open initiatives exist.
    """
    if output_dir is None:
        return []

    from src.initiatives import (
        derive_status,
        initiatives_path,
        load_initiatives,
    )
    from src.maturity_tiers import compute_tier

    path = initiatives_path(output_dir)
    all_initiatives = load_initiatives(path)
    if not all_initiatives:
        return []

    # Build a name → audit dict for fast lookup
    audit_map: dict[str, dict] = {}
    for audit in audits:
        name = audit.get("metadata", {}).get("name", "")
        if name:
            audit_map[name] = audit

    results: list[InitiativeStatus] = []
    for initiative in all_initiatives:
        # Skip already-closed initiatives
        if initiative.closed_at is not None:
            continue
        repo_audit = audit_map.get(initiative.repo_name, {})
        # Convert audit to portfolio-truth-style dict for compute_tier
        pt_repo: dict = {
            "identity": {
                "display_name": initiative.repo_name,
                "has_git": repo_audit.get("identity", {}).get("has_git", True),
            },
            "derived": repo_audit.get("derived", {}),
            "risk": repo_audit.get("risk", {}),
        }
        status = derive_status(initiative, pt_repo)
        current = compute_tier(pt_repo)
        results.append(
            InitiativeStatus(
                repo_name=initiative.repo_name,
                current_tier=current,
                target_tier=initiative.target_tier,
                deadline=initiative.deadline,
                status=status,
            )
        )
    return results


def _build_suggested_initiatives(
    audits: list[dict],
    budget_usd: float = 0.05,
) -> list[InitiativeSuggestionRow]:
    """Generate LLM-ranked suggested initiatives for the briefing.

    Uses a smaller budget ($0.05) than the CLI flag ($0.10) since the briefing
    context is already rich and this is a secondary feature.

    Returns an empty list if no candidates exist or no LLM provider is available
    (deterministic fallback is still used in that case, but we only populate the
    briefing when the LLM is available to keep the section meaningful).
    """
    try:
        from src.suggest_initiatives import generate_suggestions
    except ImportError:
        logger.warning("briefing: suggest_initiatives module not available; skipping")
        return []

    try:
        raw_suggestions, _cost = generate_suggestions(audits, budget_usd=budget_usd)
    except Exception as exc:  # noqa: BLE001
        logger.warning("briefing: error generating suggested initiatives: %s", exc)
        return []

    rows: list[InitiativeSuggestionRow] = []
    for s in raw_suggestions:
        rows.append(
            InitiativeSuggestionRow(
                repo_name=s.repo_name,
                current_tier=s.current_tier,
                target_tier=s.target_tier,
                rationale=s.rationale,
                estimated_effort=s.estimated_effort,
            )
        )
    return rows


def _build_dismissed_repos(
    output_dir: Path | None,
    today: date | None = None,
) -> list[DismissedRepoRow]:
    """Load dismissed-suggestions.json and return non-expired rows.

    today: optional override for testing. Default = today's date.
    Skips entries whose expires_at < today (those are expired).
    Returns empty list if output_dir is None or file is missing.

    DismissedSuggestion has no expires_at field; we read it from the raw JSON
    items dict alongside the parsed objects so optional per-entry expiry is
    preserved without changing the upstream dataclass.
    """
    if output_dir is None:
        return []
    from src.suggest_initiatives import dismissed_path, load_dismissed

    path = dismissed_path(output_dir)
    if not path.exists():
        return []

    today_d = today or date.today()

    # Load structured objects (validates schema + skips malformed entries)
    items = load_dismissed(path)

    # Also parse raw JSON to retrieve optional expires_at per entry
    try:
        raw_data = json.loads(path.read_text(encoding="utf-8"))
        raw_items: list[dict] = raw_data.get("items", []) if isinstance(raw_data, dict) else []
    except (OSError, json.JSONDecodeError):
        raw_items = []

    # Build a repo_name → expires_at lookup from raw entries
    expires_map: dict[str, str | None] = {}
    for raw in raw_items:
        if isinstance(raw, dict) and "repo_name" in raw:
            expires_map[str(raw["repo_name"])] = raw.get("expires_at") or None

    rows: list[DismissedRepoRow] = []
    for d in items:
        expires: str | None = expires_map.get(d.repo_name)
        if expires:
            try:
                exp_d = date.fromisoformat(str(expires)[:10])
                if exp_d < today_d:
                    continue  # already expired; skip
            except ValueError:
                pass  # malformed expiry — keep the row
        rows.append(
            DismissedRepoRow(
                repo_name=d.repo_name,
                reason=d.reason,
                expires_at=expires,
            )
        )
    return rows


def build_briefing(
    audits: list[dict],
    username: str,
    date: str,
    *,
    use_history: bool = True,
    provider: NarrativeProvider | None = None,
    model: str = _ANTHROPIC_BRIEFING_MODEL,
    prefs: dict | None = None,
    semantic_index: object | None = None,
    cost_tracker: CostTracker | None = None,
    output_dir: Path | None = None,
    include_suggestions: bool = False,
) -> Briefing:
    """Build a structured weekly operator briefing from audit data.

    Pass *prefs* (loaded via ``operator_prefs.load_prefs``) to filter out
    suggestions for actions the operator has repeatedly declined.

    Pass *semantic_index* (a :class:`~src.semantic_index.SemanticIndex` instance)
    to enrich the LLM suggestion prompt with cross-repo "related repos" context.
    If ``None``, behaviour is identical to S3.2 (no enrichment, backward compat).

    Pass *cost_tracker* (a :class:`~src.llm_cost.CostTracker` instance) to record
    LLM spend and enforce an optional budget cap.

    Pass *output_dir* to load initiative tracker data from
    ``output_dir/initiatives.json`` and include a top-level initiatives section
    in the rendered output.

    Pass *include_suggestions=True* to run the LLM-suggested initiatives ranking
    (Arc G S8.4).  Default is ``False`` to keep briefings cheap.
    """
    shipped = _build_shipped(audits)
    needs_attention = _build_needs_attention(audits)
    health_delta = _build_health_delta(audits, use_history=use_history)
    suggestions, suppressed_by_prefs = _build_suggestions(
        audits,
        provider,
        model,
        prefs=prefs,
        semantic_index=semantic_index,
        cost_tracker=cost_tracker,
    )
    initiatives = _build_initiatives(audits, output_dir)

    suggested_initiatives: list[InitiativeSuggestionRow] = []
    if include_suggestions:
        suggested_initiatives = _build_suggested_initiatives(audits)

    dismissed_repos = _build_dismissed_repos(output_dir)

    return Briefing(
        username=username,
        date=date,
        shipped_this_week=shipped,
        needs_attention=needs_attention,
        health_delta=health_delta,
        suggestions=suggestions,
        suppressed_by_prefs=suppressed_by_prefs,
        initiatives=initiatives,
        suggested_initiatives=suggested_initiatives,
        dismissed_repos=dismissed_repos,
    )


# ── Renderers ────────────────────────────────────────────────────────────────


def render_markdown(briefing: Briefing) -> str:
    """Render a rich Markdown briefing document."""
    lines: list[str] = [
        f"# Weekly Operator Briefing: {briefing.username}",
        "",
        f"*Generated {briefing.date}*",
        "",
    ]

    # ── Section 0: Initiatives this week ─────────────────────────────────────
    if briefing.initiatives:
        from datetime import date as _date

        lines.append("## Initiatives this week")
        lines.append("")
        counts: dict[str, int] = {"on-track": 0, "at-risk": 0, "overdue": 0, "met": 0}
        for ini in briefing.initiatives:
            counts[ini.status] = counts.get(ini.status, 0) + 1
        status_summary = (
            f"**Status counts:** {counts['on-track']} on-track"
            f" · {counts['at-risk']} at-risk"
            f" · {counts['overdue']} overdue"
        )
        lines.append(status_summary)
        lines.append("")
        today = _date.today()
        for ini in briefing.initiatives:
            from src.maturity_tiers import tier_name as _tier_name

            try:
                deadline_date = _date.fromisoformat(ini.deadline)
                days_left = (deadline_date - today).days
                days_str = (
                    f"{days_left} days until {ini.deadline}"
                    if days_left >= 0
                    else f"{abs(days_left)} days overdue"
                )
            except (ValueError, TypeError):
                days_str = ini.deadline
            target_name = _tier_name(ini.target_tier)
            lines.append(
                f"- **{ini.repo_name}** → {target_name} (target) — `{ini.status}` — {days_str}"
            )
        lines.append("")

    # ── Section 0b: Suggested Initiatives ────────────────────────────────────
    if briefing.suggested_initiatives:
        from src.maturity_tiers import tier_name as _tier_name2

        n = len(briefing.suggested_initiatives)
        lines.append("## Suggested Initiatives")
        lines.append("")
        lines.append(
            f"The portfolio has {n} {'repo' if n == 1 else 'repos'} close to qualifying "
            "for higher tiers. Top suggestions:"
        )
        lines.append("")
        for s in briefing.suggested_initiatives:
            target_name = _tier_name2(s.target_tier)
            lines.append(
                f"- **{s.repo_name}** → Tier {s.target_tier} ({target_name}) — "
                f"`{s.estimated_effort}` — _{s.rationale}_"
            )
        lines.append("")

    # ── Section 0c: Currently Dismissed ─────────────────────────────────────
    if briefing.dismissed_repos:
        if lines and lines[-1] != "":
            lines.append("")
        n = len(briefing.dismissed_repos)
        lines.append("## Currently Dismissed")
        lines.append("")
        lines.append(f"{n} repo(s) currently suppressed from LLM suggestions:")
        lines.append("")
        for d in briefing.dismissed_repos:
            reason_part = f" — _{d.reason}_" if d.reason else ""
            expiry_part = f" (expires {d.expires_at[:10]})" if d.expires_at else ""
            lines.append(f"- **{d.repo_name}**{reason_part}{expiry_part}")
        lines.append("")

    # ── Section 1: Shipped this week ──────────────────────────────────────────
    lines.append("## Shipped This Week")
    lines.append("")
    if briefing.shipped_this_week:
        lines.append("| Repo | Language | Automation |")
        lines.append("|------|----------|------------|")
        for repo in briefing.shipped_this_week:
            lines.append(f"| {repo.name} | {repo.language} | {repo.automation_status} |")
    else:
        lines.append("*No commits pushed in the last 7 days.*")
    lines.append("")

    # ── Section 2: Needs attention ────────────────────────────────────────────
    lines.append("## Needs Attention")
    lines.append("")
    if briefing.needs_attention:
        lines.append("| Repo | Score | Days Since Push | Reason |")
        lines.append("|------|-------|-----------------|--------|")
        for repo in briefing.needs_attention:
            lines.append(
                f"| {repo.name} | {repo.overall_score:.2f} | {repo.days_since_push}d | {repo.reason} |"
            )
    else:
        lines.append("*No attention candidates found.*")
    lines.append("")

    # ── Section 3: Portfolio health delta ─────────────────────────────────────
    lines.append("## Portfolio Health Delta")
    lines.append("")
    up = briefing.health_delta.get("up", [])
    down = briefing.health_delta.get("down", [])
    if not up and not down:
        lines.append("*No historical data available for delta computation.*")
    else:
        if up:
            lines.append("**Score improvers:**")
            lines.append("")
            lines.append("| Repo | Previous | Current | Delta |")
            lines.append("|------|----------|---------|-------|")
            for m in up:
                sign = "+" if m.delta > 0 else ""
                lines.append(
                    f"| {m.name} | {m.old_score:.3f} | {m.new_score:.3f} | {sign}{m.delta:.3f} |"
                )
            lines.append("")
        if down:
            lines.append("**Score decliners:**")
            lines.append("")
            lines.append("| Repo | Previous | Current | Delta |")
            lines.append("|------|----------|---------|-------|")
            for m in down:
                lines.append(
                    f"| {m.name} | {m.old_score:.3f} | {m.new_score:.3f} | {m.delta:.3f} |"
                )
    lines.append("")

    # ── Section 4: Suggested next actions ────────────────────────────────────
    lines.append("## Suggested Next Actions")
    lines.append("")
    if briefing.suggestions:
        for s in briefing.suggestions:
            lines.append(f"- **{s.name}**: {s.action}")
    else:
        lines.append("*No suggestions generated (LLM provider not configured or unavailable).*")
    lines.append("")

    lines.append("---")
    lines.append(
        "*Generated by [GithubRepoAuditor](https://github.com/saagpatel/GithubRepoAuditor)*"
    )
    lines.append("")
    return "\n".join(lines)


def render_voice(briefing: Briefing) -> str:
    """
    Render a voice-readable plain text briefing.
    No tables, no markdown. One paragraph per section.
    Blank lines between sections act as ~5-second TTS pauses.
    """
    parts: list[str] = []

    # Header
    parts.append(f"Weekly operator briefing for {briefing.username}, generated on {briefing.date}.")
    parts.append("")

    # ── Dismissed suppressions ────────────────────────────────────────────────
    if briefing.dismissed_repos:
        n = len(briefing.dismissed_repos)
        parts.append(
            f"You currently have {n} dismissed {'suggestion' if n == 1 else 'suggestions'}."
        )
        parts.append("")

    # ── Section 0: Initiatives ────────────────────────────────────────────────
    if briefing.initiatives:
        n = len(briefing.initiatives)
        on_track = sum(1 for i in briefing.initiatives if i.status == "on-track")
        at_risk = sum(1 for i in briefing.initiatives if i.status == "at-risk")
        overdue = sum(1 for i in briefing.initiatives if i.status == "overdue")
        parts.append(
            f"You have {n} {'initiative' if n == 1 else 'initiatives'} this week, "
            f"{on_track} on-track, {at_risk} at-risk, {overdue} overdue."
        )
        parts.append("")

    # ── Section 1 ────────────────────────────────────────────────────────────
    if briefing.shipped_this_week:
        repo_sentences = []
        for repo in briefing.shipped_this_week:
            auto_note = (
                "automation eligible"
                if repo.automation_status == "eligible"
                else (
                    "not automation eligible"
                    if repo.automation_status == "not-eligible"
                    else "automation status unknown"
                )
            )
            repo_sentences.append(f"{repo.name}, written in {repo.language}, is {auto_note}")
        shipped_text = (
            f"Shipped this week: {len(briefing.shipped_this_week)} "
            f"{'repo' if len(briefing.shipped_this_week) == 1 else 'repos'} had commits. "
            + ". ".join(repo_sentences)
            + "."
        )
    else:
        shipped_text = "Shipped this week: no repos had commits in the last 7 days."
    parts.append(shipped_text)
    parts.append("")

    # ── Section 2 ────────────────────────────────────────────────────────────
    if briefing.needs_attention:
        attn_sentences = []
        for repo in briefing.needs_attention:
            attn_sentences.append(
                f"{repo.name} has a completeness score of {repo.overall_score:.0%} "
                f"and was last pushed {repo.days_since_push} days ago"
            )
        needs_text = (
            "Needs attention: the following repos have the highest gap between completeness and "
            "recent activity. " + ". ".join(attn_sentences) + "."
        )
    else:
        needs_text = "Needs attention: no repos flagged for attention this week."
    parts.append(needs_text)
    parts.append("")

    # ── Section 3 ────────────────────────────────────────────────────────────
    up = briefing.health_delta.get("up", [])
    down = briefing.health_delta.get("down", [])
    if not up and not down:
        delta_text = (
            "Portfolio health delta: no historical data available to compute score changes."
        )
    else:
        sentences = []
        for m in up:
            sentences.append(f"{m.name} improved by {m.delta:+.3f} points to {m.new_score:.3f}")
        for m in down:
            sentences.append(f"{m.name} declined by {m.delta:.3f} points to {m.new_score:.3f}")
        delta_text = "Portfolio health delta: " + ". ".join(sentences) + "."
    parts.append(delta_text)
    parts.append("")

    # ── Section 4 ────────────────────────────────────────────────────────────
    if briefing.suggestions:
        sug_sentences = [f"For {s.name}: {s.action}" for s in briefing.suggestions]
        sug_text = "Suggested next actions: " + ". ".join(sug_sentences) + "."
    else:
        sug_text = (
            "Suggested next actions: no suggestions generated. "
            "Configure a narrative provider to enable LLM suggestions."
        )
    parts.append(sug_text)

    return "\n".join(parts)


# ── Public generate entry point ───────────────────────────────────────────────


def generate_briefing(
    report_data: dict,
    output_dir: Path,
    *,
    provider_name: str | None = None,
    model: str | None = None,
    github_token: str | None = None,
    write_voice: bool = False,
    semantic_index: object | None = None,
    cost_tracker: CostTracker | None = None,
    include_suggestions: bool = False,
) -> dict:
    """
    Generate the weekly operator briefing.
    Returns a dict with briefing_path (and optionally voice_path), or {skipped, reason}.

    Pass *semantic_index* (a :class:`~src.semantic_index.SemanticIndex` instance) to
    enrich suggestion prompts with cross-repo related-repos context.  Defaults to ``None``
    (backward-compatible, no enrichment).

    Pass *cost_tracker* (a :class:`~src.llm_cost.CostTracker` instance) to record
    LLM spend and enforce an optional budget cap.
    """
    audits: list[dict] = report_data.get("audits", [])
    username = report_data.get("username", "unknown")
    date = report_data.get("generated_at", "")[:10] or datetime.now(timezone.utc).strftime(
        "%Y-%m-%d"
    )

    # Resolve provider (same strategy as narrative.py) — use Haiku-equivalent for cost
    try:
        result = _resolve_provider(provider_name, model, github_token)
    except ValueError as exc:
        print(f"  Briefing error: {exc}", file=sys.stderr)
        return {"skipped": True, "reason": str(exc)}

    provider_obj: NarrativeProvider | None = None
    resolved_model = _ANTHROPIC_BRIEFING_MODEL

    if result is not None:
        provider_obj, resolved_model_from_result = result
        # If user didn't specify a model, use cheap Haiku-equivalent instead of Sonnet default
        if model is None:
            from src.narrative import DEFAULT_ANTHROPIC_MODEL, DEFAULT_GITHUB_MODELS_MODEL

            if resolved_model_from_result == DEFAULT_ANTHROPIC_MODEL:
                resolved_model = _ANTHROPIC_BRIEFING_MODEL
            elif resolved_model_from_result == DEFAULT_GITHUB_MODELS_MODEL:
                resolved_model = _GITHUB_MODELS_BRIEFING_MODEL
            else:
                resolved_model = resolved_model_from_result
        else:
            resolved_model = resolved_model_from_result
    else:
        print(
            "  No narrative credentials available. Briefing will skip LLM suggestions.",
            file=sys.stderr,
        )

    # Load operator prefs to suppress repeatedly-rejected suggestions
    from src.operator_prefs import load_prefs, prefs_path

    prefs = load_prefs(prefs_path(Path(output_dir)))

    briefing = build_briefing(
        audits,
        username,
        date,
        use_history=True,
        provider=provider_obj,
        model=resolved_model,
        prefs=prefs or None,
        semantic_index=semantic_index,
        cost_tracker=cost_tracker,
        output_dir=Path(output_dir),
        include_suggestions=include_suggestions,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / f"briefing-{username}-{date}.md"
    md_path.write_text(render_markdown(briefing))
    print(f"  Briefing generated: {md_path}", file=sys.stderr)

    result_dict: dict = {"briefing_path": md_path}

    if write_voice:
        voice_path = output_dir / f"briefing-{username}-{date}.voice.txt"
        voice_path.write_text(render_voice(briefing))
        print(f"  Voice briefing generated: {voice_path}", file=sys.stderr)
        result_dict["voice_path"] = voice_path

    return result_dict
