from __future__ import annotations

from src.models import RepoAudit
from src.scorer import COMPLETENESS_TIERS

# Tier thresholds in ascending order for "next tier" lookup
_TIER_THRESHOLDS = list(reversed(COMPLETENESS_TIERS))  # abandoned -> shipped

# Action advice per dimension when score is low
DIMENSION_ADVICE: dict[str, list[tuple[float, str]]] = {
    "readme": [
        (0.0, "Add a README.md with project description"),
        (0.5, "Add install instructions, usage examples, and code blocks to README"),
    ],
    "testing": [
        (0.0, "Add a test directory with at least one test file"),
        (0.5, "Add more test files and configure a test framework"),
    ],
    "cicd": [
        (0.0, "Add a .github/workflows/ci.yml for CI/CD"),
        (0.5, "Add build and test scripts to your CI workflow"),
    ],
    "structure": [
        (0.3, "Add a .gitignore and organize code into src/"),
        (0.6, "Add a LICENSE file and project config (package.json, Cargo.toml, etc.)"),
    ],
    "dependencies": [
        (0.0, "Add a dependency manifest (package.json, requirements.txt, etc.)"),
        (0.5, "Add a lockfile (package-lock.json, Cargo.lock, etc.)"),
    ],
    "build_readiness": [
        (0.0, "Add a Dockerfile or Makefile"),
        (0.4, "Add .env.example or deployment config"),
    ],
    "activity": [
        (0.3, "Push a recent commit to show the project is alive"),
    ],
    "code_quality": [
        (0.3, "Add an identifiable entry point (main.py, index.ts, etc.)"),
        (0.5, "Reduce TODO/FIXME density and add type definitions"),
    ],
    "documentation": [
        (0.0, "Add a docs/ directory or CHANGELOG"),
    ],
}


def find_quick_wins(
    audits: list[RepoAudit],
    max_gap: float = 0.15,
) -> list[dict]:
    """Find repos closest to the next tier with specific improvement actions.

    Returns list of {name, current_tier, score, next_tier, gap, actions}.
    """
    wins: list[dict] = []

    for audit in audits:
        next_tier, threshold = _next_tier(audit.completeness_tier, audit.overall_score)
        if next_tier is None:
            continue  # Already at top tier

        gap = threshold - audit.overall_score
        if gap > max_gap:
            continue  # Too far from next tier

        # Find lowest-scoring dimensions
        actions = _get_actions(audit)

        wins.append({
            "name": audit.metadata.name,
            "current_tier": audit.completeness_tier,
            "score": round(audit.overall_score, 3),
            "next_tier": next_tier,
            "gap": round(gap, 3),
            "actions": actions[:3],  # Top 3 actions
        })

    # Sort by smallest gap first (easiest wins)
    wins.sort(key=lambda w: w["gap"])
    return wins


def _next_tier(current_tier: str, score: float) -> tuple[str | None, float]:
    """Find the next tier above the current one and its threshold."""
    for i, (tier_name, threshold) in enumerate(_TIER_THRESHOLDS):
        if tier_name == current_tier:
            # Look for the next tier up
            if i + 1 < len(_TIER_THRESHOLDS):
                next_name, next_threshold = _TIER_THRESHOLDS[i + 1]
                return next_name, next_threshold
            return None, 0.0  # Already at top
    return None, 0.0


def _get_actions(audit: RepoAudit) -> list[str]:
    """Get specific improvement actions based on lowest-scoring dimensions."""
    score_map = {r.dimension: r.score for r in audit.analyzer_results}

    # Sort dimensions by score ascending (worst first)
    sorted_dims = sorted(
        [(dim, score) for dim, score in score_map.items()
         if dim in DIMENSION_ADVICE],
        key=lambda x: x[1],
    )

    actions: list[str] = []
    for dim, score in sorted_dims:
        advices = DIMENSION_ADVICE.get(dim, [])
        for threshold, advice in advices:
            if score <= threshold:
                actions.append(f"{advice} ({dim}={score:.1f})")
                break
        if len(actions) >= 3:
            break

    return actions
