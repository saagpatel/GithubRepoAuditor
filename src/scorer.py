from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from src.badges import compute_badges, suggest_next_badges
from src.models import AnalyzerResult, RepoAudit, RepoMetadata

if TYPE_CHECKING:
    from src.github_client import GitHubClient

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

GRADE_THRESHOLDS = [(0.80, "A"), (0.70, "B"), (0.55, "C"), (0.35, "D"), (0.0, "F")]


def letter_grade(score: float) -> str:
    """Map a 0.0-1.0 score to a letter grade A-F."""
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


def score_repo(
    metadata: RepoMetadata,
    results: list[AnalyzerResult],
    repo_path: Path | None = None,
    portfolio_lang_freq: dict[str, float] | None = None,
    custom_weights: dict[str, float] | None = None,
    github_client: GitHubClient | None = None,
    *,
    scorecard_enabled: bool = False,
    security_offline: bool = False,
) -> RepoAudit:
    """Compute dual-axis scores: completeness + interest."""
    weights = dict(custom_weights) if custom_weights else dict(WEIGHTS)
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

    # Portfolio-relative novelty adjustment: reduce novelty for dominant languages
    if portfolio_lang_freq and metadata.language:
        from src.analyzers.interest import NOVEL_LANGUAGES
        if metadata.language in NOVEL_LANGUAGES:
            freq = portfolio_lang_freq.get(metadata.language, 0.0)
            if freq >= 0.30:
                interest_result = next(
                    (r for r in results if r.dimension == "interest"), None,
                )
                if interest_result:
                    raw_novelty = interest_result.details.get("tech_novelty", 0.0)
                    adjusted_novelty = raw_novelty * max(0.0, 1.0 - freq)
                    interest_score = max(0.0, interest_score - (raw_novelty - adjusted_novelty))

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
    from src.portfolio_intelligence import (
        build_action_candidates,
        build_hotspots,
        compute_lens_scores,
    )
    from src.implementation_hotspots import build_implementation_hotspots
    from src.report_enrichment import build_score_explanation
    from src.security_intelligence import build_security_posture

    audit.security_posture = build_security_posture(
        metadata,
        results,
        github_client,
        scorecard_enabled=scorecard_enabled,
        security_offline=security_offline,
    )
    audit.lenses = compute_lens_scores(
        metadata,
        results,
        overall_score=overall_score,
        interest_score=interest_score,
        security_posture=audit.security_posture,
    )
    audit.action_candidates = build_action_candidates(audit)
    audit.hotspots = build_hotspots(audit)
    audit.implementation_hotspots = build_implementation_hotspots(repo_path, audit)
    audit.score_explanation = build_score_explanation(audit)

    return audit


def compute_portfolio_grade(audits: list[RepoAudit]) -> tuple[str, float]:
    """Compute nuanced portfolio health grade with diversity/abandonment adjustments."""
    if not audits:
        return "F", 0.0

    avg_score = sum(a.overall_score for a in audits) / len(audits)

    # Diversity bonus: more languages = broader skills
    languages = set(a.metadata.language for a in audits if a.metadata.language)
    diversity_bonus = min(0.10, max(0, (len(languages) - 3)) * 0.05)

    # Shipped ratio bonus
    shipped_ratio = sum(1 for a in audits if a.completeness_tier == "shipped") / len(audits)
    shipped_bonus = 0.10 if shipped_ratio > 0.5 else (0.05 if shipped_ratio > 0.3 else 0)

    # Abandonment penalty
    abandon_ratio = sum(
        1 for a in audits if a.completeness_tier in ("skeleton", "abandoned")
    ) / len(audits)
    abandon_penalty = -0.10 if abandon_ratio > 0.6 else (-0.05 if abandon_ratio > 0.4 else 0)

    # Badge density bonus
    avg_badges = sum(len(a.badges) for a in audits) / len(audits)
    badge_bonus = 0.05 if avg_badges > 3 else 0

    health_score = avg_score + diversity_bonus + shipped_bonus + abandon_penalty + badge_bonus
    health_score = max(0.0, min(1.0, health_score))

    return letter_grade(health_score), round(health_score, 3)


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
