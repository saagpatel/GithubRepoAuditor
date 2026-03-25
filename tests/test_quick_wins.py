from __future__ import annotations

from datetime import datetime, timezone

from src.models import AnalyzerResult, RepoAudit, RepoMetadata
from src.quick_wins import find_quick_wins
from src.scorer import letter_grade


def _meta(name: str = "test") -> RepoMetadata:
    return RepoMetadata(
        name=name, full_name=f"user/{name}", description=None,
        language="Python", languages={}, private=False, fork=False,
        archived=False, created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        pushed_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
        default_branch="main", stars=0, forks=0, open_issues=0,
        size_kb=100, html_url="", clone_url="", topics=[],
    )


def _audit(name: str, score: float, tier: str, dim_scores: dict[str, float] | None = None) -> RepoAudit:
    results = []
    for dim, s in (dim_scores or {}).items():
        results.append(AnalyzerResult(dim, s, 1.0, [], {"config_files": ["x"], "total_loc": 100}))
    return RepoAudit(
        metadata=_meta(name),
        analyzer_results=results,
        overall_score=score,
        completeness_tier=tier,
    )


class TestFindQuickWins:
    def test_finds_near_tier_repos(self):
        audits = [
            _audit("close", 0.50, "wip", {"testing": 0.0, "readme": 0.9}),
            _audit("far", 0.15, "skeleton", {"testing": 0.0}),
        ]
        wins = find_quick_wins(audits, max_gap=0.15)
        names = [w["name"] for w in wins]
        assert "close" in names  # 0.50 -> 0.55 = gap 0.05
        assert "far" not in names  # 0.20 -> 0.35 = gap 0.15, borderline

    def test_actions_target_lowest_dimensions(self):
        audits = [
            _audit("test-repo", 0.50, "wip", {"testing": 0.0, "cicd": 0.1, "readme": 0.9}),
        ]
        wins = find_quick_wins(audits)
        assert len(wins) == 1
        assert "testing" in wins[0]["actions"][0].lower() or "cicd" in wins[0]["actions"][0].lower()

    def test_shipped_repos_excluded(self):
        audits = [
            _audit("shipped", 0.90, "shipped", {"testing": 1.0}),
        ]
        wins = find_quick_wins(audits)
        assert len(wins) == 0

    def test_sorted_by_gap(self):
        audits = [
            _audit("bigger-gap", 0.46, "wip", {"testing": 0.0}),
            _audit("smaller-gap", 0.52, "wip", {"testing": 0.0}),
        ]
        wins = find_quick_wins(audits)
        if len(wins) >= 2:
            assert wins[0]["gap"] <= wins[1]["gap"]


class TestLetterGrade:
    def test_a_grade(self):
        assert letter_grade(0.90) == "A"

    def test_b_grade(self):
        assert letter_grade(0.75) == "B"

    def test_c_grade(self):
        assert letter_grade(0.60) == "C"

    def test_d_grade(self):
        assert letter_grade(0.40) == "D"

    def test_f_grade(self):
        assert letter_grade(0.20) == "F"

    def test_boundary(self):
        assert letter_grade(0.85) == "A"
        assert letter_grade(0.849) == "B"
