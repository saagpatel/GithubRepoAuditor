from __future__ import annotations

from datetime import datetime, timezone

from src.badges import compute_badges, suggest_next_badges
from src.models import AnalyzerResult, RepoAudit, RepoMetadata

# Rebalanced completeness weights (sum = 1.0)
WEIGHTS: dict[str, float] = {
    "readme": 0.12,
    "structure": 0.10,
    "code_quality": 0.15,
    "testing": 0.18,
    "cicd": 0.10,
    "dependencies": 0.08,
    "activity": 0.15,
    "documentation": 0.02,
    "build_readiness": 0.07,
    "community_profile": 0.03,
}

# Fork override: reduce activity weight, redistribute to others
FORK_ACTIVITY_WEIGHT = 0.05

COMPLETENESS_TIERS = [
    ("shipped", 0.75),
    ("functional", 0.55),
    ("wip", 0.35),
    ("skeleton", 0.15),
    ("abandoned", 0.0),
]

INTEREST_TIERS = [
    ("flagship", 0.70),
    ("notable", 0.45),
    ("standard", 0.20),
    ("mundane", 0.0),
]

STALE_THRESHOLD_DAYS = 730  # 2 years

GRADE_THRESHOLDS = [(0.85, "A"), (0.70, "B"), (0.55, "C"), (0.35, "D"), (0.0, "F")]


def letter_grade(score: float) -> str:
    """Map a 0.0-1.0 score to a letter grade A-F."""
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


def score_repo(
    metadata: RepoMetadata,
    results: list[AnalyzerResult],
) -> RepoAudit:
    """Compute dual-axis scores: completeness + interest."""
    weights = dict(WEIGHTS)
    flags: list[str] = []

    # Fork override: reduce activity weight
    if metadata.fork:
        flags.append("forked")
        activity_reduction = weights["activity"] - FORK_ACTIVITY_WEIGHT
        weights["activity"] = FORK_ACTIVITY_WEIGHT
        other_keys = [k for k in weights if k != "activity"]
        other_total = sum(weights[k] for k in other_keys)
        for k in other_keys:
            weights[k] += activity_reduction * (weights[k] / other_total)

    # Compute completeness score (weighted average of all non-interest dimensions)
    score_map = {r.dimension: r.score for r in results}
    weighted_sum = 0.0
    weight_sum = 0.0

    for dimension, weight in weights.items():
        if dimension in score_map:
            weighted_sum += score_map[dimension] * weight
            weight_sum += weight

    overall_score = weighted_sum / weight_sum if weight_sum > 0 else 0.0

    # Compute interest score (separate axis, from interest analyzer)
    interest_score = score_map.get("interest", 0.0)

    # Classify completeness tier
    tier = "abandoned"
    for tier_name, threshold in COMPLETENESS_TIERS:
        if overall_score >= threshold:
            tier = tier_name
            break

    # Classify interest tier
    interest_tier = "mundane"
    for tier_name, threshold in INTEREST_TIERS:
        if interest_score >= threshold:
            interest_tier = tier_name
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

    audit = RepoAudit(
        metadata=metadata,
        analyzer_results=results,
        overall_score=overall_score,
        interest_score=interest_score,
        completeness_tier=tier,
        interest_tier=interest_tier,
        grade=letter_grade(overall_score),
        interest_grade=letter_grade(interest_score),
        flags=flags,
    )

    # Compute badges and suggestions
    audit.badges = compute_badges(audit)
    audit.next_badges = suggest_next_badges(audit)

    return audit


def _count_meaningful_files(results: list[AnalyzerResult]) -> int:
    """Heuristic: check if the repo has files beyond just a README."""
    for r in results:
        if r.dimension == "structure":
            if r.details.get("config_files") or r.details.get("source_dirs"):
                return 1
        if r.dimension == "code_quality":
            if r.details.get("entry_point") or r.details.get("total_loc", 0) > 0:
                return 1
    return 0
