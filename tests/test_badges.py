from __future__ import annotations

from datetime import datetime, timezone

from src.badges import compute_badges, suggest_next_badges
from src.models import AnalyzerResult, RepoAudit, RepoMetadata


def _meta(**overrides) -> RepoMetadata:
    defaults = dict(
        name="test", full_name="user/test", description=None,
        language="Python", languages={"Python": 5000}, private=False, fork=False,
        archived=False, created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        pushed_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
        default_branch="main", stars=0, forks=0, open_issues=0,
        size_kb=100, html_url="", clone_url="", topics=[],
    )
    defaults.update(overrides)
    return RepoMetadata(**defaults)


def _audit(scores: dict[str, float], details: dict[str, dict] | None = None, **meta_kw) -> RepoAudit:
    results = []
    for dim, score in scores.items():
        d = (details or {}).get(dim, {})
        results.append(AnalyzerResult(dim, score, 1.0, [], d))
    return RepoAudit(
        metadata=_meta(**meta_kw),
        analyzer_results=results,
        overall_score=0.5,
        completeness_tier="wip",
    )


class TestComputeBadges:
    def test_fully_tested(self):
        audit = _audit({"testing": 0.9})
        assert "fully-tested" in compute_badges(audit)

    def test_not_fully_tested(self):
        audit = _audit({"testing": 0.5})
        assert "fully-tested" not in compute_badges(audit)

    def test_fresh_badge(self):
        audit = _audit(
            {"activity": 0.5},
            details={"activity": {"days_since_push": 10}},
        )
        assert "fresh" in compute_badges(audit)

    def test_not_fresh(self):
        audit = _audit(
            {"activity": 0.5},
            details={"activity": {"days_since_push": 60}},
        )
        assert "fresh" not in compute_badges(audit)

    def test_polyglot(self):
        audit = _audit({}, languages={"Python": 1, "Rust": 1, "Go": 1})
        assert "polyglot" in compute_badges(audit)

    def test_has_fans(self):
        audit = _audit({}, stars=3)
        assert "has-fans" in compute_badges(audit)

    def test_complete_package(self):
        scores = {d: 0.6 for d in [
            "readme", "structure", "code_quality", "testing", "cicd",
            "dependencies", "activity", "documentation", "build_readiness",
        ]}
        audit = _audit(scores)
        assert "complete-package" in compute_badges(audit)

    def test_zero_debt(self):
        audit = _audit(
            {"code_quality": 0.8},
            details={"code_quality": {"todo_density_per_1k": 0.3}},
        )
        assert "zero-debt" in compute_badges(audit)


class TestSuggestNextBadges:
    def test_suggests_closest_badges(self):
        audit = _audit({"testing": 0.7, "cicd": 0.2})
        audit.badges = compute_badges(audit)
        suggestions = suggest_next_badges(audit)
        assert len(suggestions) > 0
        # Testing is closest (0.7 -> 0.8 = gap 0.1)
        assert suggestions[0]["gap"] <= 0.2

    def test_no_suggestions_when_all_earned(self):
        scores = {d: 1.0 for d in [
            "readme", "structure", "code_quality", "testing", "cicd",
            "dependencies", "activity", "documentation", "build_readiness",
            "community_profile", "interest",
        ]}
        audit = _audit(
            scores,
            details={
                "activity": {"days_since_push": 1},
                "testing": {"test_file_count": 20},
                "code_quality": {"todo_density_per_1k": 0.0},
                "interest": {"tech_novelty": 0.2, "readme_storytelling": 0.1},
            },
            stars=1, languages={"Python": 1, "Rust": 1, "Go": 1},
        )
        audit.badges = compute_badges(audit)
        suggestions = suggest_next_badges(audit)
        # Most badges should be earned, few suggestions left
        assert len(audit.badges) >= 10
