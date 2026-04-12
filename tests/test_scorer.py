from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.models import AnalyzerResult, RepoMetadata
from src.scorer import WEIGHTS, score_repo


def _make_results(scores: dict[str, float]) -> list[AnalyzerResult]:
    results = []
    for dim, score in scores.items():
        details: dict = {}
        # Structure and code_quality need details for _count_meaningful_files
        if dim == "structure":
            details = {"config_files": ["pyproject.toml"], "source_dirs": ["src"]}
        if dim == "code_quality":
            details = {"entry_point": "main.py", "total_loc": 500}
        results.append(
            AnalyzerResult(dimension=dim, score=score, max_score=1.0, findings=[], details=details)
        )
    return results


def _make_metadata(**overrides) -> RepoMetadata:
    defaults = dict(
        name="test", full_name="user/test", description=None,
        language="Python", languages={}, private=False, fork=False,
        archived=False,
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        pushed_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
        default_branch="main", stars=0, forks=0, open_issues=0,
        size_kb=100, html_url="", clone_url="", topics=[],
    )
    defaults.update(overrides)
    return RepoMetadata(**defaults)


class TestScoring:
    def test_weights_sum_to_one(self):
        assert abs(sum(WEIGHTS.values()) - 1.0) < 0.001

    def test_perfect_scores_yield_shipped(self):
        results = _make_results({dim: 1.0 for dim in WEIGHTS})
        audit = score_repo(_make_metadata(), results)
        assert audit.completeness_tier == "shipped"
        assert audit.overall_score >= 0.99

    def test_zero_scores_yield_abandoned(self):
        results = _make_results({dim: 0.0 for dim in WEIGHTS})
        meta = _make_metadata()
        # Need config or source dirs for it not to be forced to skeleton
        audit = score_repo(meta, results)
        assert audit.completeness_tier in ("abandoned", "skeleton")

    def test_medium_scores_yield_functional(self):
        results = _make_results({dim: 0.65 for dim in WEIGHTS})
        audit = score_repo(_make_metadata(), results)
        assert audit.completeness_tier == "functional"


class TestOverrides:
    def test_archived_capped_at_functional(self):
        results = _make_results({dim: 1.0 for dim in WEIGHTS})
        meta = _make_metadata(archived=True)
        audit = score_repo(meta, results)
        assert audit.completeness_tier == "functional"
        assert "archived" in audit.flags

    def test_stale_two_years_capped_at_wip(self):
        old_push = datetime.now(timezone.utc) - timedelta(days=800)
        results = _make_results({dim: 0.9 for dim in WEIGHTS})
        meta = _make_metadata(pushed_at=old_push)
        audit = score_repo(meta, results)
        assert audit.completeness_tier == "wip"
        assert "stale-2yr" in audit.flags

    def test_fork_reduces_activity_weight(self):
        results = _make_results({dim: 0.8 for dim in WEIGHTS})
        meta_normal = _make_metadata()
        meta_fork = _make_metadata(fork=True)

        audit_normal = score_repo(meta_normal, results)
        audit_fork = score_repo(meta_fork, results)

        assert "forked" in audit_fork.flags
        # Scores should differ slightly due to weight redistribution
        assert audit_normal.overall_score != audit_fork.overall_score


class TestFlags:
    def test_no_readme_flag(self):
        scores = {dim: 0.5 for dim in WEIGHTS}
        scores["readme"] = 0.0
        results = _make_results(scores)
        audit = score_repo(_make_metadata(), results)
        assert "no-readme" in audit.flags

    def test_no_tests_flag(self):
        scores = {dim: 0.5 for dim in WEIGHTS}
        scores["testing"] = 0.0
        results = _make_results(scores)
        audit = score_repo(_make_metadata(), results)
        assert "no-tests" in audit.flags

    def test_no_ci_flag(self):
        scores = {dim: 0.5 for dim in WEIGHTS}
        scores["cicd"] = 0.0
        results = _make_results(scores)
        audit = score_repo(_make_metadata(), results)
        assert "no-ci" in audit.flags


class TestPortfolioNovelty:
    """Portfolio-relative novelty reduces interest for dominant 'novel' languages."""

    def _results_with_interest(self, novelty: float = 0.10, total_interest: float = 0.50):
        results = _make_results({dim: 0.5 for dim in WEIGHTS})
        results.append(AnalyzerResult(
            dimension="interest", score=total_interest, max_score=1.0,
            findings=[], details={"tech_novelty": novelty},
        ))
        return results

    def test_dominant_novel_language_reduced(self):
        results = self._results_with_interest(novelty=0.10, total_interest=0.50)
        meta = _make_metadata(language="Rust")
        freq = {"Rust": 0.60, "Python": 0.40}
        audit = score_repo(meta, results, portfolio_lang_freq=freq)
        # 0.10 * max(0, 1.0 - 0.60) = 0.04, delta = 0.06
        assert abs(audit.interest_score - 0.44) < 0.01

    def test_rare_novel_language_unchanged(self):
        results = self._results_with_interest(novelty=0.10, total_interest=0.50)
        meta = _make_metadata(language="Rust")
        freq = {"Rust": 0.10, "Python": 0.60, "JavaScript": 0.30}
        audit = score_repo(meta, results, portfolio_lang_freq=freq)
        # Below 30% threshold — no adjustment
        assert audit.interest_score == 0.50

    def test_no_freq_data_unchanged(self):
        results = self._results_with_interest(novelty=0.10, total_interest=0.50)
        meta = _make_metadata(language="Rust")
        audit = score_repo(meta, results)
        assert audit.interest_score == 0.50

    def test_common_language_not_affected(self):
        results = self._results_with_interest(novelty=0.0, total_interest=0.40)
        meta = _make_metadata(language="Python")
        freq = {"Python": 0.80}
        audit = score_repo(meta, results, portfolio_lang_freq=freq)
        # Python is not in NOVEL_LANGUAGES — no adjustment
        assert audit.interest_score == 0.40


class TestNextPhaseSignals:
    def test_populates_lenses_actions_hotspots_and_security_posture(self):
        results = _make_results({dim: 0.55 for dim in WEIGHTS})
        results.append(
            AnalyzerResult(
                dimension="security",
                score=0.35,
                max_score=1.0,
                findings=["No SECURITY.md", "No Dependabot config"],
                details={
                    "secrets_found": 1,
                    "dangerous_files": [".env"],
                    "has_security_md": False,
                    "has_dependabot": False,
                },
            )
        )
        results.append(
            AnalyzerResult(
                dimension="interest",
                score=0.62,
                max_score=1.0,
                findings=[],
                details={"tech_novelty": 0.15},
            )
        )
        audit = score_repo(_make_metadata(stars=7), results)

        assert "ship_readiness" in audit.lenses
        assert "maintenance_risk" in audit.lenses
        assert audit.security_posture["secrets_found"] == 1
        assert "local" in audit.security_posture
        assert "providers" in audit.security_posture
        assert audit.action_candidates
        assert audit.hotspots

    def test_maintenance_risk_uses_risk_orientation(self):
        results = _make_results({dim: 0.45 for dim in WEIGHTS})
        audit = score_repo(_make_metadata(), results)
        assert audit.lenses["maintenance_risk"]["orientation"] == "higher-is-riskier"
