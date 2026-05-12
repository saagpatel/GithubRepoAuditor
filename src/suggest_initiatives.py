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
