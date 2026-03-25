from __future__ import annotations

from datetime import datetime, timezone

from src.models import AnalyzerResult, RepoAudit, RepoMetadata

WEIGHTS: dict[str, float] = {
    "readme": 0.15,
    "structure": 0.10,
    "code_quality": 0.15,
    "testing": 0.15,
    "cicd": 0.10,
    "dependencies": 0.10,
    "activity": 0.15,
    "documentation": 0.05,
    "build_readiness": 0.05,
}

# Fork override: reduce activity weight, redistribute to others
FORK_ACTIVITY_WEIGHT = 0.05

TIERS = [
    ("shipped", 0.75),
    ("functional", 0.55),
    ("wip", 0.35),
    ("skeleton", 0.15),
    ("abandoned", 0.0),
]

STALE_THRESHOLD_DAYS = 730  # 2 years


def score_repo(
    metadata: RepoMetadata,
    results: list[AnalyzerResult],
) -> RepoAudit:
    """Compute weighted score, classify tier, apply overrides."""
    weights = dict(WEIGHTS)
    flags: list[str] = []

    # Fork override: reduce activity weight
    if metadata.fork:
        flags.append("forked")
        activity_reduction = weights["activity"] - FORK_ACTIVITY_WEIGHT
        weights["activity"] = FORK_ACTIVITY_WEIGHT
        # Redistribute proportionally to other dimensions
        other_keys = [k for k in weights if k != "activity"]
        other_total = sum(weights[k] for k in other_keys)
        for k in other_keys:
            weights[k] += activity_reduction * (weights[k] / other_total)

    # Compute weighted score
    score_map = {r.dimension: r.score for r in results}
    weighted_sum = 0.0
    weight_sum = 0.0

    for dimension, weight in weights.items():
        if dimension in score_map:
            weighted_sum += score_map[dimension] * weight
            weight_sum += weight

    overall_score = weighted_sum / weight_sum if weight_sum > 0 else 0.0

    # Classify tier
    tier = "abandoned"
    for tier_name, threshold in TIERS:
        if overall_score >= threshold:
            tier = tier_name
            break

    # Generate flags from analyzer results
    if score_map.get("readme", 1.0) == 0.0:
        flags.append("no-readme")
    if score_map.get("testing", 1.0) == 0.0:
        flags.append("no-tests")
    if score_map.get("cicd", 1.0) == 0.0:
        flags.append("no-ci")
    if metadata.archived:
        flags.append("archived")

    # Override: archived repos capped at "functional"
    if metadata.archived and overall_score > 0.5:
        if tier == "shipped":
            tier = "functional"

    # Override: stale >2 years capped at "wip"
    if metadata.pushed_at:
        days_since = (datetime.now(timezone.utc) - metadata.pushed_at).days
        if days_since > STALE_THRESHOLD_DAYS:
            flags.append("stale-2yr")
            if tier in ("shipped", "functional"):
                tier = "wip"

    # Override: 0 files beyond README → force "skeleton"
    file_count = _count_meaningful_files(results)
    if file_count == 0:
        tier = "skeleton"
        flags.append("readme-only")

    return RepoAudit(
        metadata=metadata,
        analyzer_results=results,
        overall_score=overall_score,
        completeness_tier=tier,
        flags=flags,
    )


def _count_meaningful_files(results: list[AnalyzerResult]) -> int:
    """Heuristic: check if the repo has files beyond just a README.

    Uses structure and code_quality analyzer results as signals.
    """
    for r in results:
        if r.dimension == "structure":
            # If it has config files or source dirs, it has real files
            if r.details.get("config_files") or r.details.get("source_dirs"):
                return 1
        if r.dimension == "code_quality":
            if r.details.get("entry_point") or r.details.get("total_loc", 0) > 0:
                return 1
    return 0
