"""LLM-ranked initiative suggestions — Arc G Sprint 8.4.

Walk the portfolio, narrow repos that are close to qualifying for their next
maturity tier, ask an LLM to rank them by leverage, and return structured
:class:`InitiativeSuggestion` objects.

Deterministic fallback (rank by fewest missing requirements) is used
automatically when no LLM provider is available.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from src.narrative import _resolve_provider

logger = logging.getLogger(__name__)

# ── Public dataclass ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class InitiativeSuggestion:
    repo_name: str
    current_tier: int
    target_tier: int
    missing_requirements: list[str]
    rationale: str  # LLM-provided (or fallback message)
    estimated_effort: str  # "small" | "medium" | "large" | "unknown"


# ── Candidate selection ───────────────────────────────────────────────────────


def narrow_candidates(
    projects: list[dict],
    target_tier: int | None = None,
    max_missing: int = 3,
) -> list[tuple[dict, int, "TierGap"]]:  # noqa: F821
    """Return (repo, target_tier, gap) tuples for repos close to their next tier.

    Filters:
    - Skip repos with ``compute_tier == 0`` (no git history).
    - Skip repos already at Platinum (tier 4) — no next tier exists.
    - If *target_tier* is specified, use it for all repos; otherwise use
      ``current + 1`` per repo.
    - Skip if *target_tier* > 4.
    - Skip if repo already qualifies for the target (no missing requirements).
    - Skip if ``len(missing_requirements) > max_missing`` (too far away).
    """
    from src.maturity_tiers import TierGap, compute_tier, tier_gap

    candidates: list[tuple[dict, int, TierGap]] = []

    for repo in projects:
        current = compute_tier(repo)
        # Skip no-git repos and repos already at max tier
        if current == 0 or current >= 4:
            continue

        t = target_tier if target_tier is not None else current + 1
        if t > 4:
            continue

        gap = tier_gap(repo, t)
        # Skip if already qualifies
        if not gap.missing_requirements:
            continue
        # Skip if too many missing
        if len(gap.missing_requirements) > max_missing:
            continue

        candidates.append((repo, t, gap))

    return candidates


# ── Prompt builder ────────────────────────────────────────────────────────────


def build_suggest_prompt(
    candidates: list[tuple[dict, int, "TierGap"]],  # noqa: F821
) -> str:
    """Build a prompt asking the LLM to rank candidates by leverage.

    Includes per-candidate context (name, tiers, missing requirements, and a
    1-line status blurb).  Asks the LLM to return a JSON array sorted by
    descending leverage, capped at 8 entries.
    """
    from src.maturity_tiers import tier_name

    blurbs: list[str] = []
    for repo, target, gap in candidates:
        name = (
            repo.get("identity", {}).get("display_name")
            or repo.get("metadata", {}).get("name")
            or repo.get("repo_name")
            or "unknown"
        )
        current = gap.current_tier
        derived = repo.get("derived", {})
        activity_status = derived.get("activity_status", "unknown")
        context_quality = derived.get("context_quality", "unknown")
        missing_str = "; ".join(gap.missing_requirements)

        blurbs.append(
            f"- repo_name: {name}\n"
            f"  current_tier: {current} ({tier_name(current)})\n"
            f"  target_tier: {target} ({tier_name(target)})\n"
            f"  missing_requirements: [{missing_str}]\n"
            f"  activity_status: {activity_status}\n"
            f"  context_quality: {context_quality}"
        )

    candidates_block = "\n".join(blurbs)

    return (
        "You are a portfolio advisor for a software developer with many GitHub repos.\n"
        "Below is a list of repos that are close to qualifying for a higher maturity tier.\n"
        "Each entry shows the repo name, current and target tiers, and the missing requirements.\n\n"
        "Rank these repos by LEVERAGE — which ones would benefit MOST from the small remaining "
        "effort to reach the next tier? Consider factors like: how few requirements remain, "
        "how active the repo is, how much context quality matters, and which tier upgrades are "
        "most impactful.\n\n"
        "Return a JSON array of objects (up to 8 entries, sorted by descending leverage):\n"
        '[\n  {"repo_name": "...", "rationale": "1-sentence why this is high-leverage",'
        ' "estimated_effort": "small|medium|large"},\n  ...\n]\n\n'
        "IMPORTANT: Return ONLY the JSON array, no other text.\n\n"
        "Candidates:\n"
        f"{candidates_block}\n\n"
        "JSON response:"
    )


# ── Response parser ───────────────────────────────────────────────────────────


def parse_suggest_response(
    raw_response: str,
    candidates: list[tuple[dict, int, "TierGap"]],  # noqa: F821
) -> list[InitiativeSuggestion]:
    """Parse the LLM JSON response into :class:`InitiativeSuggestion` objects.

    Uses brace-scan (mirrors plan_campaign.py pattern).  Cross-references
    repo_name against the known candidates — LLM-invented names are dropped.
    The current_tier, target_tier, and missing_requirements are taken from the
    candidate tuple, NOT from the LLM output.
    """
    # Build a lookup from repo_name → (repo, target, gap)
    candidate_map: dict[str, tuple[dict, int, "TierGap"]] = {}  # noqa: F821
    for repo, target, gap in candidates:
        name = (
            repo.get("identity", {}).get("display_name")
            or repo.get("metadata", {}).get("name")
            or repo.get("repo_name")
            or "unknown"
        )
        candidate_map[name] = (repo, target, gap)

    text = raw_response.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    # Find the first [ ... ] array block
    start = text.find("[")
    end = text.rfind("]") + 1
    if start < 0 or end <= start:
        logger.warning("suggest_initiatives: no JSON array found in provider response")
        return []

    try:
        parsed = json.loads(text[start:end])
    except json.JSONDecodeError as exc:
        logger.warning("suggest_initiatives: failed to parse JSON response: %s", exc)
        return []

    if not isinstance(parsed, list):
        logger.warning("suggest_initiatives: expected JSON array, got %s", type(parsed))
        return []

    results: list[InitiativeSuggestion] = []
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        repo_name = str(entry.get("repo_name") or "")
        if repo_name not in candidate_map:
            logger.debug(
                "suggest_initiatives: unknown repo_name %r in LLM response — skipping", repo_name
            )
            continue

        _repo, target, gap = candidate_map[repo_name]
        rationale = str(entry.get("rationale") or "")
        raw_effort = str(entry.get("estimated_effort") or "unknown").lower()
        effort = raw_effort if raw_effort in ("small", "medium", "large") else "unknown"

        results.append(
            InitiativeSuggestion(
                repo_name=repo_name,
                current_tier=gap.current_tier,
                target_tier=target,
                missing_requirements=list(gap.missing_requirements),
                rationale=rationale,
                estimated_effort=effort,
            )
        )

    return results


# ── Deterministic fallback ────────────────────────────────────────────────────


def _deterministic_rank(
    candidates: list[tuple[dict, int, "TierGap"]],  # noqa: F821
) -> list[InitiativeSuggestion]:
    """Rank candidates by fewest missing requirements, then by highest current tier.

    Used when no LLM provider is available.
    """
    # Sort: ascending by missing count, descending by current tier
    sorted_candidates = sorted(
        candidates,
        key=lambda t: (len(t[2].missing_requirements), -t[2].current_tier),
    )

    results: list[InitiativeSuggestion] = []
    for repo, target, gap in sorted_candidates[:8]:
        name = (
            repo.get("identity", {}).get("display_name")
            or repo.get("metadata", {}).get("name")
            or repo.get("repo_name")
            or "unknown"
        )
        results.append(
            InitiativeSuggestion(
                repo_name=name,
                current_tier=gap.current_tier,
                target_tier=target,
                missing_requirements=list(gap.missing_requirements),
                rationale="(no LLM available; ranked by fewest missing requirements)",
                estimated_effort="unknown",
            )
        )

    return results


# ── Deadline helpers ─────────────────────────────────────────────────────────

_EFFORT_DAYS: dict[str, int] = {"small": 14, "medium": 30, "large": 60}
_DEFAULT_DEADLINE_DAYS = 30  # for "unknown" or any other value


def default_deadline_for_effort(effort: str, today: date | None = None) -> str:
    """Map estimated_effort string to a deadline in YYYY-MM-DD form.

    small  → today + 14 days
    medium → today + 30 days
    large  → today + 60 days
    unknown/anything else → today + 30 days
    """
    if today is None:
        today = date.today()
    days = (
        _EFFORT_DAYS.get(effort.lower(), _DEFAULT_DEADLINE_DAYS)
        if effort
        else _DEFAULT_DEADLINE_DAYS
    )
    return (today + timedelta(days=days)).isoformat()


def accept_suggestion(
    repo_name: str,
    projects: list[dict],
    output_dir: Path,
    deadline: str | None = None,
    target_tier: int | None = None,
) -> "Initiative":  # noqa: F821
    """Convert a suggestion into an initiative.

    This is the single backend entry point for both CLI and web routes.

    Steps
    -----
    1. Find project in ``projects`` by ``identity.display_name == repo_name``.
    2. Validate current tier (must be 1-3).
    3. Derive or validate ``target_tier``.
    4. Derive ``deadline`` from suggestion effort when not supplied.
    5. Validate ``deadline`` is a future YYYY-MM-DD string.
    6. Build, persist, and return the :class:`Initiative`.
    """
    from datetime import datetime, timezone

    from src.initiatives import Initiative, initiatives_path, operator_identity, upsert_initiative
    from src.maturity_tiers import compute_tier

    # 1. Find project
    project: dict | None = None
    for p in projects:
        if p.get("identity", {}).get("display_name") == repo_name:
            project = p
            break
    if project is None:
        raise ValueError(f"repo '{repo_name}' not found in portfolio truth")

    # 2. Validate current tier
    current = compute_tier(project)
    if current == 0:
        raise ValueError(f"repo '{repo_name}' has no git (current_tier=0); cannot set initiative")
    if current >= 4:
        raise ValueError(f"repo '{repo_name}' is already at Platinum (tier 4)")

    # 3. Derive / validate target_tier
    if target_tier is None:
        target = current + 1
    else:
        if target_tier <= current:
            raise ValueError(
                f"target_tier {target_tier} must be greater than current tier {current}"
            )
        if target_tier not in {2, 3, 4}:
            raise ValueError(f"target_tier must be 2, 3, or 4; got {target_tier}")
        target = target_tier

    # 4. Derive deadline when not supplied
    if deadline is None:
        effort = "medium"  # default
        try:
            suggestions, _ = generate_suggestions(projects, target_tier=target, budget_usd=0.0)
            for s in suggestions:
                if s.repo_name == repo_name:
                    effort = s.estimated_effort
                    break
        except Exception:  # noqa: BLE001 — never let deadline derivation crash accept
            pass
        deadline = default_deadline_for_effort(effort)

    # 5. Validate deadline format
    try:
        deadline_date = date.fromisoformat(deadline)
    except ValueError:
        raise ValueError(f"deadline must be YYYY-MM-DD, got: {deadline!r}")

    # 6. Validate deadline is not in the past
    if deadline_date < date.today():
        raise ValueError(
            f"deadline {deadline} must be in the future (today is {date.today().isoformat()})"
        )

    # 7. Build initiative
    initiative = Initiative(
        repo_name=repo_name,
        target_tier=target,
        deadline=deadline,
        set_at=datetime.now(timezone.utc).isoformat(),
        set_by=operator_identity(),
        closed_at=None,
        closed_reason=None,
    )

    # 8. Persist
    upsert_initiative(initiatives_path(output_dir), initiative)

    # 9. Return
    return initiative


# ── Top-level entrypoint ──────────────────────────────────────────────────────


def generate_suggestions(
    projects: list[dict],
    target_tier: int | None = None,
    budget_usd: float = 0.10,
    max_missing: int = 3,
) -> tuple[list[InitiativeSuggestion], float]:
    """Generate LLM-ranked initiative suggestions for the portfolio.

    Parameters
    ----------
    projects:
        List of repo dicts from portfolio-truth.
    target_tier:
        If set, filter to repos targeting this specific tier.
        If ``None``, each repo targets its own ``current_tier + 1``.
    budget_usd:
        Hard cap on LLM spend.  Default $0.10.
    max_missing:
        Maximum number of missing requirements to include a repo as a candidate.

    Returns
    -------
    (suggestions, actual_cost_usd)
        ``actual_cost_usd`` is 0.0 when the deterministic fallback is used.
    """
    import os

    from src.llm_cost import BudgetExceededError, CostTracker

    candidates = narrow_candidates(projects, target_tier=target_tier, max_missing=max_missing)
    if not candidates:
        return [], 0.0

    # Resolve LLM provider (module-level import so tests can patch src.suggest_initiatives._resolve_provider)
    github_token = os.environ.get("GITHUB_TOKEN", "").strip() or None
    provider_result = _resolve_provider(None, None, github_token)

    if provider_result is None:
        logger.warning(
            "suggest_initiatives: no LLM provider available; using deterministic fallback"
        )
        return _deterministic_rank(candidates), 0.0

    provider, model_name = provider_result
    prompt = build_suggest_prompt(candidates)

    cost_tracker = CostTracker(budget_usd=budget_usd)

    # Rough token estimate: ~4 chars per token; enforce pre-call budget check
    estimated_input_tokens = len(prompt) // 4
    estimated_output_tokens = 1500
    estimated_cost = estimated_input_tokens * 0.000003 + estimated_output_tokens * 0.000015
    if budget_usd is not None and estimated_cost > budget_usd:
        raise BudgetExceededError(
            budget_usd=budget_usd,
            current_usd=0.0,
            call_cost_usd=estimated_cost,
            feature="suggest-initiatives",
        )

    raw = provider.generate(
        prompt,
        model_name,
        1500,
        cost_tracker=cost_tracker,
        feature="suggest-initiatives",
    )

    actual_cost = cost_tracker._total_usd
    suggestions = parse_suggest_response(raw, candidates)
    return suggestions, actual_cost
