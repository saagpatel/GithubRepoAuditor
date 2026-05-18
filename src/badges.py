from __future__ import annotations

from src.models import RepoAudit

# Badge definitions: (name, check_fn, action_hint)
# check_fn receives (score_map, details_map, audit)
# Returns True if badge is earned

BADGE_DEFS: list[tuple[str, callable, str]] = []


def _def(name: str, hint: str):
    """Decorator to register a badge definition."""
    def decorator(fn):
        BADGE_DEFS.append((name, fn, hint))
        return fn
    return decorator


@_def("fully-tested", "Add test files and configure a test framework")
def _fully_tested(scores, details, audit):
    return scores.get("testing", 0) >= 0.8


@_def("well-documented", "Add a detailed README and documentation directory")
def _well_documented(scores, details, audit):
    return scores.get("readme", 0) >= 0.8 and scores.get("documentation", 0) >= 0.5


@_def("ci-champion", "Add GitHub Actions workflows for CI/CD")
def _ci_champion(scores, details, audit):
    return scores.get("cicd", 0) >= 0.8


@_def("dependency-disciplined", "Add a lockfile and dependency manifest")
def _dep_disciplined(scores, details, audit):
    return scores.get("dependencies", 0) >= 0.8


@_def("fresh", "Push a commit within the last 30 days")
def _fresh(scores, details, audit):
    days = details.get("activity", {}).get("days_since_push", 999)
    return isinstance(days, (int, float)) and days <= 30


@_def("battle-tested", "Add 10+ test files with a configured test framework")
def _battle_tested(scores, details, audit):
    test_count = details.get("testing", {}).get("test_file_count", 0)
    return scores.get("testing", 0) >= 0.8 and test_count >= 10


@_def("complete-package", "Bring all scoring dimensions above 0.5")
def _complete_package(scores, details, audit):
    core_dims = ["readme", "structure", "code_quality", "testing", "cicd",
                 "dependencies", "activity", "documentation", "build_readiness"]
    return all(scores.get(d, 0) >= 0.5 for d in core_dims)


@_def("novel-tech", "Use an uncommon language or multi-language stack")
def _novel_tech(scores, details, audit):
    return details.get("interest", {}).get("tech_novelty", 0) >= 0.15


@_def("storyteller", "Add images or diagrams to a detailed README (>1000 chars)")
def _storyteller(scores, details, audit):
    return details.get("interest", {}).get("readme_storytelling", 0) > 0


@_def("community-ready", "Add LICENSE, CONTRIBUTING, and CODE_OF_CONDUCT files")
def _community_ready(scores, details, audit):
    return scores.get("community_profile", 0) >= 0.6


@_def("zero-debt", "Reduce TODO/FIXME density below 1 per 1000 LOC")
def _zero_debt(scores, details, audit):
    density = details.get("code_quality", {}).get("todo_density_per_1k", 999)
    return isinstance(density, (int, float)) and density < 1.0


@_def("actively-maintained", "Push regularly and maintain recent commit activity")
def _actively_maintained(scores, details, audit):
    return scores.get("activity", 0) >= 0.8


@_def("built-to-ship", "Add a Dockerfile, Makefile, or deployment config")
def _built_to_ship(scores, details, audit):
    return scores.get("build_readiness", 0) >= 0.6


@_def("polyglot", "Use 3+ programming languages in the project")
def _polyglot(scores, details, audit):
    return len(audit.metadata.languages) >= 3


@_def("has-fans", "Get at least one star or fork on the repository")
def _has_fans(scores, details, audit):
    return audit.metadata.stars > 0 or audit.metadata.forks > 0


def compute_badges(audit: RepoAudit) -> list[str]:
    """Compute which badges a repo has earned."""
    score_map = {r.dimension: r.score for r in audit.analyzer_results}
    details_map = {r.dimension: r.details for r in audit.analyzer_results}

    earned = []
    for name, check_fn, _ in BADGE_DEFS:
        try:
            if check_fn(score_map, details_map, audit):
                earned.append(name)
        except Exception:
            continue

    return earned


def suggest_next_badges(audit: RepoAudit, max_suggestions: int = 3) -> list[dict]:
    """Find badges closest to being earned, with actionable hints."""
    score_map = {r.dimension: r.score for r in audit.analyzer_results}
    details_map = {r.dimension: r.details for r in audit.analyzer_results}
    earned = set(audit.badges)

    suggestions = []
    for name, check_fn, hint in BADGE_DEFS:
        if name in earned:
            continue

        # Estimate gap based on the badge type
        gap = _estimate_gap(name, score_map, details_map, audit)
        if gap is not None and gap < 1.0:
            suggestions.append({
                "badge": name,
                "action": hint,
                "gap": round(gap, 2),
            })

    suggestions.sort(key=lambda s: s["gap"])
    return suggestions[:max_suggestions]


def _estimate_gap(
    badge: str,
    scores: dict[str, float],
    details: dict[str, dict],
    audit: RepoAudit,
) -> float | None:
    """Estimate how far a repo is from earning a badge (0.0 = almost there)."""
    gap_map = {
        "fully-tested": max(0, 0.8 - scores.get("testing", 0)),
        "well-documented": max(0, 0.8 - scores.get("readme", 0)) + max(0, 0.5 - scores.get("documentation", 0)),
        "ci-champion": max(0, 0.8 - scores.get("cicd", 0)),
        "dependency-disciplined": max(0, 0.8 - scores.get("dependencies", 0)),
        "fresh": 0.0 if details.get("activity", {}).get("days_since_push", 999) <= 30 else 0.5,
        "battle-tested": max(0, 0.8 - scores.get("testing", 0)) + (0.3 if details.get("testing", {}).get("test_file_count", 0) < 10 else 0),
        "complete-package": sum(max(0, 0.5 - scores.get(d, 0)) for d in ["readme", "structure", "code_quality", "testing", "cicd", "dependencies", "activity", "documentation", "build_readiness"]),
        "novel-tech": 0.0 if details.get("interest", {}).get("tech_novelty", 0) >= 0.15 else 0.5,
        "storyteller": 0.0 if details.get("interest", {}).get("readme_storytelling", 0) > 0 else 0.3,
        "community-ready": max(0, 0.6 - scores.get("community_profile", 0)),
        "zero-debt": 0.0 if details.get("code_quality", {}).get("todo_density_per_1k", 999) < 1.0 else 0.2,
        "actively-maintained": max(0, 0.8 - scores.get("activity", 0)),
        "built-to-ship": max(0, 0.6 - scores.get("build_readiness", 0)),
        "polyglot": 0.0 if len(audit.metadata.languages) >= 3 else 0.5,
        "has-fans": 0.0 if (audit.metadata.stars > 0 or audit.metadata.forks > 0) else 0.8,
    }
    return gap_map.get(badge)
