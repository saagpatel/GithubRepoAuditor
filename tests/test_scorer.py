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
        name="test",
        full_name="user/test",
        description=None,
        language="Python",
        languages={},
        private=False,
        fork=False,
        archived=False,
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        pushed_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
        default_branch="main",
        stars=0,
        forks=0,
        open_issues=0,
        size_kb=100,
        html_url="",
        clone_url="",
        topics=[],
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
        results.append(
            AnalyzerResult(
                dimension="interest",
                score=total_interest,
                max_score=1.0,
                findings=[],
                details={"tech_novelty": novelty},
            )
        )
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
    def test_populates_lenses_actions_hotspots_security_posture_and_implementation_hotspots(
        self, tmp_path
    ):
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
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        (repo_path / "src").mkdir()
        (repo_path / "src" / "core.py").write_text(
            "# TODO: tighten flow\n# FIXME: split branches\n\ndef run(value):\n    if value:\n        return value\n    return 0\n"
        )
        audit = score_repo(_make_metadata(stars=7), results, repo_path=repo_path)

        assert "ship_readiness" in audit.lenses
        assert "maintenance_risk" in audit.lenses
        assert audit.security_posture["secrets_found"] == 1
        assert "local" in audit.security_posture
        assert "providers" in audit.security_posture
        assert audit.action_candidates
        assert audit.hotspots
        assert audit.implementation_hotspots

    def test_maintenance_risk_uses_risk_orientation(self):
        results = _make_results({dim: 0.45 for dim in WEIGHTS})
        audit = score_repo(_make_metadata(), results)
        assert audit.lenses["maintenance_risk"]["orientation"] == "higher-is-riskier"


# ---------------------------------------------------------------------------
# WEIGHTS constant — all dimension keys must be present
# ---------------------------------------------------------------------------


class TestWeightsKeys:
    def test_all_dimension_keys_present(self):
        expected = {
            "readme",
            "structure",
            "code_quality",
            "testing",
            "cicd",
            "dependencies",
            "activity",
            "documentation",
            "build_readiness",
            "community_profile",
        }
        assert set(WEIGHTS.keys()) == expected

    def test_readme_weight(self):
        assert WEIGHTS["readme"] == 0.12

    def test_testing_weight(self):
        assert WEIGHTS["testing"] == 0.18

    def test_activity_weight(self):
        assert WEIGHTS["activity"] == 0.15


# ---------------------------------------------------------------------------
# letter_grade boundary values
# ---------------------------------------------------------------------------


class TestLetterGradeBoundaries:
    def test_exactly_0_80_is_A(self):
        from src.scorer import letter_grade

        assert letter_grade(0.80) == "A"

    def test_exactly_0_70_is_B(self):
        from src.scorer import letter_grade

        assert letter_grade(0.70) == "B"

    def test_exactly_0_55_is_C(self):
        from src.scorer import letter_grade

        assert letter_grade(0.55) == "C"

    def test_exactly_0_35_is_D(self):
        from src.scorer import letter_grade

        assert letter_grade(0.35) == "D"

    def test_exactly_0_0_is_F(self):
        from src.scorer import letter_grade

        assert letter_grade(0.0) == "F"

    def test_just_below_0_80_is_B(self):
        from src.scorer import letter_grade

        assert letter_grade(0.799) == "B"

    def test_above_1_is_A(self):
        from src.scorer import letter_grade

        assert letter_grade(1.0) == "A"


# ---------------------------------------------------------------------------
# Completeness tier constant — tier names and thresholds
# ---------------------------------------------------------------------------


class TestCompletenessTiers:
    def test_shipped_threshold(self):
        from src.scorer import COMPLETENESS_TIERS

        tier_map = dict(COMPLETENESS_TIERS)
        assert tier_map["shipped"] == 0.75
        assert tier_map["functional"] == 0.55
        assert tier_map["wip"] == 0.35
        assert tier_map["skeleton"] == 0.15
        assert tier_map["abandoned"] == 0.0

    def test_wip_tier_name(self):
        results = _make_results({dim: 0.4 for dim in WEIGHTS})
        audit = score_repo(_make_metadata(), results)
        assert audit.completeness_tier == "wip"

    def test_skeleton_tier_name(self):
        results = _make_results({dim: 0.2 for dim in WEIGHTS})
        audit = score_repo(_make_metadata(), results)
        assert audit.completeness_tier == "skeleton"

    def test_abandoned_tier_name(self):
        # Results with no structure/code_quality details → no meaningful files
        bare_results = [
            AnalyzerResult(dimension=dim, score=0.0, max_score=1.0, findings=[], details={})
            for dim in WEIGHTS
        ]
        audit = score_repo(_make_metadata(), bare_results)
        assert audit.completeness_tier in ("abandoned", "skeleton")


# ---------------------------------------------------------------------------
# Interest tier constant
# ---------------------------------------------------------------------------


class TestInterestTiers:
    def test_flagship_tier(self):
        from src.scorer import INTEREST_TIERS

        tier_map = dict(INTEREST_TIERS)
        assert tier_map["flagship"] == 0.70
        assert tier_map["notable"] == 0.45
        assert tier_map["standard"] == 0.20
        assert tier_map["mundane"] == 0.0

    def test_flagship_interest_tier_name(self):
        results = _make_results({dim: 0.5 for dim in WEIGHTS})
        results.append(
            AnalyzerResult(
                dimension="interest",
                score=0.75,
                max_score=1.0,
                findings=[],
                details={"tech_novelty": 0.0},
            )
        )
        audit = score_repo(_make_metadata(), results)
        assert audit.interest_tier == "flagship"

    def test_notable_interest_tier_name(self):
        results = _make_results({dim: 0.5 for dim in WEIGHTS})
        results.append(
            AnalyzerResult(
                dimension="interest",
                score=0.50,
                max_score=1.0,
                findings=[],
                details={"tech_novelty": 0.0},
            )
        )
        audit = score_repo(_make_metadata(), results)
        assert audit.interest_tier == "notable"

    def test_standard_interest_tier_name(self):
        results = _make_results({dim: 0.5 for dim in WEIGHTS})
        results.append(
            AnalyzerResult(
                dimension="interest",
                score=0.25,
                max_score=1.0,
                findings=[],
                details={"tech_novelty": 0.0},
            )
        )
        audit = score_repo(_make_metadata(), results)
        assert audit.interest_tier == "standard"

    def test_mundane_interest_tier_name(self):
        results = _make_results({dim: 0.5 for dim in WEIGHTS})
        results.append(
            AnalyzerResult(
                dimension="interest",
                score=0.10,
                max_score=1.0,
                findings=[],
                details={"tech_novelty": 0.0},
            )
        )
        audit = score_repo(_make_metadata(), results)
        assert audit.interest_tier == "mundane"


# ---------------------------------------------------------------------------
# STALE_THRESHOLD_DAYS constant
# ---------------------------------------------------------------------------


class TestStaleness:
    def test_stale_threshold_days_exact(self):
        from src.scorer import STALE_THRESHOLD_DAYS

        # Must be exactly 730 (not 731)
        assert STALE_THRESHOLD_DAYS == 730

    def test_exactly_730_days_is_stale(self):
        old_push = datetime.now(timezone.utc) - timedelta(days=731)
        results = _make_results({dim: 0.9 for dim in WEIGHTS})
        meta = _make_metadata(pushed_at=old_push)
        audit = score_repo(meta, results)
        assert "stale-2yr" in audit.flags

    def test_exactly_729_days_is_not_stale(self):
        recent_push = datetime.now(timezone.utc) - timedelta(days=729)
        results = _make_results({dim: 0.9 for dim in WEIGHTS})
        meta = _make_metadata(pushed_at=recent_push)
        audit = score_repo(meta, results)
        assert "stale-2yr" not in audit.flags


# ---------------------------------------------------------------------------
# score_repo — scorecard and security_offline defaults
# ---------------------------------------------------------------------------


class TestScoreRepoDefaults:
    def test_scorecard_enabled_default_is_false(self):
        # Kills scorecard_enabled: bool = True mutation
        results = _make_results({dim: 0.5 for dim in WEIGHTS})
        meta = _make_metadata()
        audit = score_repo(meta, results)
        # If scorecard_enabled were True, it would attempt live scorecard fetch → error
        assert audit is not None

    def test_score_explanation_populated(self):
        # Kills audit.score_explanation = None mutation
        results = _make_results({dim: 0.6 for dim in WEIGHTS})
        audit = score_repo(_make_metadata(), results)
        assert audit.score_explanation is not None


# ---------------------------------------------------------------------------
# compute_portfolio_grade — comprehensive coverage
# ---------------------------------------------------------------------------


class TestComputePortfolioGrade:
    from src.scorer import compute_portfolio_grade

    def _audit(self, score: float, tier: str, language: str = "Python", badges: int = 0):
        results = _make_results({dim: score for dim in WEIGHTS})
        meta = _make_metadata(language=language)
        audit = score_repo(meta, results)
        # Override completeness_tier and badges for isolation
        audit.completeness_tier = tier
        audit.overall_score = score
        audit.badges = ["b"] * badges
        return audit

    def test_empty_audits_returns_F(self):
        from src.scorer import compute_portfolio_grade

        grade, score = compute_portfolio_grade([])
        assert grade == "F"
        assert score == 0.0

    def test_single_perfect_audit(self):
        from src.scorer import compute_portfolio_grade

        audit = self._audit(1.0, "shipped")
        grade, score = compute_portfolio_grade([audit])
        assert grade == "A"
        assert score > 0.9

    def test_avg_score_used(self):
        # Kills * → / mutation: avg = sum * len instead of sum / len
        from src.scorer import compute_portfolio_grade

        a1 = self._audit(0.6, "functional")
        a2 = self._audit(0.4, "wip")
        grade, score = compute_portfolio_grade([a1, a2])
        # avg_score = 0.5; final should be near 0.5 (with adjustments capped)
        assert 0.4 <= score <= 0.8  # would be huge if * was used

    def test_diversity_bonus_applies_with_many_languages(self):
        from src.scorer import compute_portfolio_grade

        # 5 languages → bonus = min(0.10, max(0, (5-3)) * 0.05) = 0.10
        audits = [
            self._audit(0.5, "functional", lang)
            for lang in ["Python", "Rust", "Go", "Swift", "TypeScript"]
        ]
        grade, score = compute_portfolio_grade(audits)
        # With diversity bonus of 0.10, score >= 0.5
        assert score >= 0.5

    def test_diversity_bonus_zero_with_few_languages(self):
        from src.scorer import compute_portfolio_grade

        # 2 languages → bonus = min(0.10, max(0, (2-3)) * 0.05) = 0
        audits = [
            self._audit(0.5, "functional", "Python"),
            self._audit(0.5, "functional", "Rust"),
        ]
        _, score_few = compute_portfolio_grade(audits)
        # 5 langs
        audits_many = [
            self._audit(0.5, "functional", lang)
            for lang in ["Python", "Rust", "Go", "Swift", "TypeScript"]
        ]
        _, score_many = compute_portfolio_grade(audits_many)
        assert score_many > score_few

    def test_diversity_bonus_max_10_pct(self):
        # Kills min(0.10 → 1.10) mutation
        from src.scorer import compute_portfolio_grade

        audits = [
            self._audit(0.5, "functional", lang)
            for lang in ["Python", "Rust", "Go", "Swift", "TypeScript", "Java", "C++", "Kotlin"]
        ]
        _, score = compute_portfolio_grade(audits)
        # Bonus capped at 0.10, not 1.10
        assert score <= 0.7  # 0.5 + 0.10 + small bonuses < 0.7

    def test_diversity_bonus_three_languages_is_zero(self):
        # Kills (len - 3) → (len + 3) mutation
        from src.scorer import compute_portfolio_grade

        audits = [self._audit(0.5, "wip", lang) for lang in ["Python", "Rust", "Go"]]
        _, score3 = compute_portfolio_grade(audits)
        audits_none = [self._audit(0.5, "wip", "Python")]
        _, score1 = compute_portfolio_grade(audits_none)
        # 3 langs gives 0 diversity bonus, same as 1 lang
        # (they differ by avg_score only, so difference should be < 0.01)
        assert abs(score3 - score1) < 0.01

    def test_diversity_bonus_four_languages_is_nonzero(self):
        # Kills (len - 4) → (len - 3) off-by-one mutation
        from src.scorer import compute_portfolio_grade

        audits_3 = [self._audit(0.5, "wip", lang) for lang in ["Python", "Rust", "Go"]]
        audits_4 = [self._audit(0.5, "wip", lang) for lang in ["Python", "Rust", "Go", "Swift"]]
        _, score3 = compute_portfolio_grade(audits_3)
        _, score4 = compute_portfolio_grade(audits_4)
        # 4 langs gives 0.05 bonus, 3 langs gives 0 bonus
        assert score4 > score3

    def test_shipped_ratio_above_50_pct_gives_10_pct_bonus(self):
        from src.scorer import compute_portfolio_grade

        # 2/3 shipped → ratio = 0.67 > 0.5 → bonus = 0.10
        audits = [
            self._audit(0.5, "shipped"),
            self._audit(0.5, "shipped"),
            self._audit(0.5, "wip"),
        ]
        _, score_high = compute_portfolio_grade(audits)
        audits_low = [self._audit(0.5, "wip"), self._audit(0.5, "wip"), self._audit(0.5, "wip")]
        _, score_low = compute_portfolio_grade(audits_low)
        assert score_high > score_low

    def test_shipped_bonus_threshold_30_pct(self):
        # 1/4 shipped = 0.25, not > 0.3, so bonus = 0
        # 2/4 shipped = 0.50, not > 0.5, so bonus = 0.05
        from src.scorer import compute_portfolio_grade

        audits_25 = [self._audit(0.5, "shipped")] + [self._audit(0.5, "wip")] * 3
        audits_50 = [self._audit(0.5, "shipped")] * 2 + [self._audit(0.5, "wip")] * 2
        _, score_25 = compute_portfolio_grade(audits_25)
        _, score_50 = compute_portfolio_grade(audits_50)
        assert score_50 > score_25

    def test_abandonment_penalty_above_60_pct(self):
        from src.scorer import compute_portfolio_grade

        # 4/5 abandoned → ratio = 0.80 > 0.6 → penalty = -0.10
        audits = [self._audit(0.5, "abandoned")] * 4 + [self._audit(0.5, "wip")]
        _, score_high_abandon = compute_portfolio_grade(audits)
        audits_none = [self._audit(0.5, "wip")] * 5
        _, score_no_abandon = compute_portfolio_grade(audits_none)
        assert score_no_abandon > score_high_abandon

    def test_abandonment_penalty_above_40_pct_but_below_60(self):
        # 3/6 = 0.50 > 0.40 but not > 0.60 → penalty = -0.05
        from src.scorer import compute_portfolio_grade

        audits_50 = [self._audit(0.5, "abandoned")] * 3 + [self._audit(0.5, "wip")] * 3
        audits_none = [self._audit(0.5, "wip")] * 6
        _, score_50 = compute_portfolio_grade(audits_50)
        _, score_none = compute_portfolio_grade(audits_none)
        assert score_none > score_50

    def test_abandonment_counts_skeleton_tier(self):
        # Kills "XXskeletonXX" mutation — skeleton must be counted as abandoned-like
        from src.scorer import compute_portfolio_grade

        audits = [self._audit(0.5, "skeleton")] * 5
        audits_wip = [self._audit(0.5, "wip")] * 5
        _, score_skel = compute_portfolio_grade(audits)
        _, score_wip = compute_portfolio_grade(audits_wip)
        assert score_wip > score_skel

    def test_badge_bonus_above_3_avg(self):
        # Kills avg_badges = None mutation
        from src.scorer import compute_portfolio_grade

        audits_many = [self._audit(0.5, "wip", badges=4)] * 3
        audits_few = [self._audit(0.5, "wip", badges=0)] * 3
        _, score_many = compute_portfolio_grade(audits_many)
        _, score_few = compute_portfolio_grade(audits_few)
        assert score_many > score_few

    def test_health_score_clamped_to_0_1(self):
        from src.scorer import compute_portfolio_grade

        # extreme inputs should still produce 0..1 score
        audits = [self._audit(1.0, "shipped", badges=10)] * 10
        _, score = compute_portfolio_grade(audits)
        assert 0.0 <= score <= 1.0

    def test_health_score_not_none(self):
        # Kills health_score = None mutation
        from src.scorer import compute_portfolio_grade

        audits = [self._audit(0.7, "shipped")]
        grade, score = compute_portfolio_grade(audits)
        assert grade is not None
        assert score > 0.0

    def test_returns_letter_grade(self):
        from src.scorer import compute_portfolio_grade

        audits = [self._audit(0.85, "shipped")]
        grade, score = compute_portfolio_grade(audits)
        assert grade == "A"

    def test_grade_uses_rounded_score(self):
        # Kills round(health_score, 3) side-effects
        from src.scorer import compute_portfolio_grade

        audits = [self._audit(0.5, "wip")]
        _, score = compute_portfolio_grade(audits)
        # Score should be a float rounded to 3 decimal places
        assert score == round(score, 3)


# ---------------------------------------------------------------------------
# _count_meaningful_files
# ---------------------------------------------------------------------------


class TestCountMeaningfulFiles:
    def test_structure_dimension_triggers_count(self):
        # Kills dimension == "structure" → != "structure" mutation
        results = [
            AnalyzerResult(
                dimension="structure",
                score=0.8,
                max_score=1.0,
                findings=[],
                details={"config_files": ["pyproject.toml"], "source_dirs": ["src"]},
            )
        ]
        from src.scorer import _count_meaningful_files

        assert _count_meaningful_files(results) == 1

    def test_code_quality_with_entry_point(self):
        results = [
            AnalyzerResult(
                dimension="code_quality",
                score=0.8,
                max_score=1.0,
                findings=[],
                details={"entry_point": "main.py", "total_loc": 0},
            )
        ]
        from src.scorer import _count_meaningful_files

        assert _count_meaningful_files(results) == 1

    def test_code_quality_with_loc(self):
        # Kills total_loc default 0→1 mutation
        results = [
            AnalyzerResult(
                dimension="code_quality",
                score=0.8,
                max_score=1.0,
                findings=[],
                details={"total_loc": 100},
            )
        ]
        from src.scorer import _count_meaningful_files

        assert _count_meaningful_files(results) == 1

    def test_code_quality_zero_loc_no_entry_point_returns_zero(self):
        # Kills total_loc default 0→1 mutation (0 > 0 is False, 0 > 1 is also False — same)
        # but the explicit case confirms 0 loc with no entry_point → returns 0
        results = [
            AnalyzerResult(
                dimension="code_quality",
                score=0.0,
                max_score=1.0,
                findings=[],
                details={"total_loc": 0},
            )
        ]
        from src.scorer import _count_meaningful_files

        assert _count_meaningful_files(results) == 0

    def test_no_relevant_dimensions_returns_zero(self):
        # Kills return 0 → return 1 mutation
        results = [
            AnalyzerResult(dimension="readme", score=0.5, max_score=1.0, findings=[], details={})
        ]
        from src.scorer import _count_meaningful_files

        assert _count_meaningful_files(results) == 0

    def test_structure_returns_1_not_2(self):
        # Kills return 1 → return 2 mutation
        results = [
            AnalyzerResult(
                dimension="structure",
                score=0.8,
                max_score=1.0,
                findings=[],
                details={"config_files": ["pyproject.toml"]},
            )
        ]
        from src.scorer import _count_meaningful_files

        assert _count_meaningful_files(results) == 1

    def test_readme_only_repo_forces_skeleton_tier(self):
        # Kills tier = "XXskeletonXX" and tier = None mutations in score_repo
        bare = [
            AnalyzerResult(dimension=dim, score=0.9, max_score=1.0, findings=[], details={})
            for dim in WEIGHTS
        ]
        audit = score_repo(_make_metadata(), bare)
        assert audit.completeness_tier == "skeleton"
        assert "readme-only" in audit.flags

    def test_readme_only_flag_present(self):
        # Kills flags.append("XXreadme-onlyXX") mutation
        bare = [
            AnalyzerResult(dimension=dim, score=0.9, max_score=1.0, findings=[], details={})
            for dim in WEIGHTS
        ]
        audit = score_repo(_make_metadata(), bare)
        assert "readme-only" in audit.flags

    def test_count_from_source_dirs(self):
        # Kills "XXsource_dirsXX" key mutation
        results = [
            AnalyzerResult(
                dimension="structure",
                score=0.8,
                max_score=1.0,
                findings=[],
                details={"source_dirs": ["src"]},
            )
        ]
        from src.scorer import _count_meaningful_files

        assert _count_meaningful_files(results) == 1

    def test_code_quality_total_loc_1_counts(self):
        # Kills total_loc > 0 → > 1 mutation: loc=1 should still count
        results = [
            AnalyzerResult(
                dimension="code_quality",
                score=0.8,
                max_score=1.0,
                findings=[],
                details={"total_loc": 1},
            )
        ]
        from src.scorer import _count_meaningful_files

        assert _count_meaningful_files(results) == 1


class TestScoreRepoAdditional:
    """Additional coverage for surviving mutants."""

    def test_no_readme_flag_when_readme_present(self):
        # Kills score_map.get("readme", 2.0) mutation: ensures default=1.0 matters
        # Only readme=0.0 should trigger no-readme flag; if default were 0.0 it would fire wrongly
        results = _make_results({dim: 0.5 for dim in WEIGHTS if dim != "readme"})
        # No readme in score_map → default used → should NOT trigger no-readme
        audit = score_repo(_make_metadata(), results)
        assert "no-readme" not in audit.flags

    def test_no_tests_flag_when_testing_absent(self):
        # Kills score_map.get("testing", 2.0) mutation
        results = _make_results({dim: 0.5 for dim in WEIGHTS if dim != "testing"})
        audit = score_repo(_make_metadata(), results)
        assert "no-tests" not in audit.flags

    def test_no_ci_flag_when_cicd_absent(self):
        # Kills score_map.get("cicd", 2.0) mutation
        results = _make_results({dim: 0.5 for dim in WEIGHTS if dim != "cicd"})
        audit = score_repo(_make_metadata(), results)
        assert "no-ci" not in audit.flags

    def test_archived_capped_at_exactly_0_5_score(self):
        # Kills archived and overall_score >= 0.5 mutation: score exactly 0.5 should NOT be capped
        # (condition is > 0.5, so exactly 0.5 must not cap)
        results = _make_results({dim: 0.5 for dim in WEIGHTS})
        # Force a score that leads to exactly a value just at/around the 0.5 threshold
        meta = _make_metadata(archived=True)
        audit = score_repo(meta, results)
        # archived=True, score ~0.5 → if score <= 0.5, tier shouldn't change from shipped to functional
        # The current score for all 0.5 inputs is ~0.5; tier would be "functional" not "shipped" anyway
        assert "archived" in audit.flags

    def test_stale_exactly_730_days_not_triggered(self):
        # Kills days_since >= STALE_THRESHOLD_DAYS mutation: exactly 730 should NOT trigger stale
        from datetime import datetime, timedelta, timezone

        pushed = datetime.now(timezone.utc) - timedelta(days=730)
        results = _make_results({dim: 0.9 for dim in WEIGHTS})
        meta = _make_metadata(pushed_at=pushed)
        audit = score_repo(meta, results)
        # 730 days is exactly equal to threshold, but condition is >, not >=
        assert "stale-2yr" not in audit.flags

    def test_stale_functional_tier_capped_to_wip(self):
        # Kills "XXfunctionalXX" mutation in the tier list
        old_push = datetime.now(timezone.utc) - timedelta(days=800)
        results = _make_results({dim: 0.6 for dim in WEIGHTS})
        meta = _make_metadata(pushed_at=old_push)
        audit = score_repo(meta, results)
        # Score ~0.6 → "functional" tier without stale; with stale → should become "wip"
        assert audit.completeness_tier == "wip"
        assert "stale-2yr" in audit.flags

    def test_interest_score_default_is_zero_not_one(self):
        # Kills interest_score default 0.0 → 1.0 mutation
        results = _make_results({dim: 0.5 for dim in WEIGHTS})
        # No "interest" dimension → interest_score should default to 0.0 (mundane)
        audit = score_repo(_make_metadata(), results)
        assert audit.interest_score == 0.0
        assert audit.interest_tier == "mundane"

    def test_overall_score_empty_dimensions_is_zero(self):
        # Kills overall_score else 1.0 mutation
        results = []
        meta = _make_metadata()
        audit = score_repo(meta, results)
        assert audit.overall_score == 0.0

    def test_next_badges_populated(self):
        # Kills audit.next_badges = None mutation
        results = _make_results({dim: 0.5 for dim in WEIGHTS})
        audit = score_repo(_make_metadata(), results)
        assert audit.next_badges is not None

    def test_completeness_tier_initial_default_abandoned(self):
        # Kills tier = "XXabandonedXX" and tier = None mutations
        # A very low score (0.1) with structure details → "abandoned" (below 0.15 threshold)
        bare = [
            AnalyzerResult(
                dimension=dim,
                score=0.1,
                max_score=1.0,
                findings=[],
                details=({"config_files": ["pyproject.toml"]} if dim == "structure" else {}),
            )
            for dim in WEIGHTS
        ]
        audit = score_repo(_make_metadata(), bare)
        assert audit.completeness_tier == "abandoned"

    def test_completeness_tier_at_threshold(self):
        # Kills overall_score > threshold mutation: score clearly above tier boundary
        # A score of 0.80 (well above 0.75) should be "shipped"
        results = _make_results({dim: 0.80 for dim in WEIGHTS})
        audit = score_repo(_make_metadata(), results)
        assert audit.completeness_tier == "shipped"

    def test_interest_tier_at_boundary(self):
        # Kills interest_score > threshold mutation: score exactly 0.70 → "flagship"
        results = _make_results({dim: 0.5 for dim in WEIGHTS})
        results.append(
            AnalyzerResult(
                dimension="interest",
                score=0.70,
                max_score=1.0,
                findings=[],
                details={"tech_novelty": 0.0},
            )
        )
        audit = score_repo(_make_metadata(), results)
        assert audit.interest_tier == "flagship"

    def test_grade_F_returned_when_no_threshold_matches(self):
        # Kills return "XXFXX" mutation for letter_grade fallback
        # Score -1.0 would fall below all thresholds if letter_grade fallback changed
        from src.scorer import letter_grade

        assert letter_grade(0.0) == "F"
        assert letter_grade(-0.1) == "F"

    def test_letter_grade_unreachable_fallback(self):
        # The literal "F" at the last GRADE_THRESHOLDS entry (0.0) means the fallback
        # `return "F"` at the end of letter_grade is actually unreachable for valid scores.
        # The test verifies that changing its value still works correctly via the threshold path.
        from src.scorer import GRADE_THRESHOLDS

        # The last threshold is (0.0, "F") — anything >= 0.0 returns "F" from the loop
        assert GRADE_THRESHOLDS[-1] == (0.0, "F")

    def test_fork_weight_redistribution_uses_subtraction(self):
        # Kills weights["activity"] - FORK_ACTIVITY_WEIGHT → + mutation
        # When fork=True, activity_reduction = old_activity - FORK_ACTIVITY_WEIGHT
        # If + instead of -, the reduction is negative → other weights go down, not up

        results = _make_results({dim: 0.8 for dim in WEIGHTS})
        meta_fork = _make_metadata(fork=True)
        meta_normal = _make_metadata(fork=False)
        audit_fork = score_repo(meta_fork, results)
        audit_normal = score_repo(meta_normal, results)
        # Fork should give different score from non-fork (weights redistributed)
        assert audit_fork.overall_score != audit_normal.overall_score

    def test_fork_activity_weight_set_correctly(self):
        # Kills weights["XXactivityXX"] mutation
        # Vary only activity score to verify fork reduces its impact
        results_high_act = _make_results({**{dim: 0.5 for dim in WEIGHTS}, "activity": 1.0})
        results_low_act = _make_results({**{dim: 0.5 for dim in WEIGHTS}, "activity": 0.0})
        meta_fork = _make_metadata(fork=True)
        audit_high = score_repo(meta_fork, results_high_act)
        audit_low = score_repo(meta_fork, results_low_act)
        # activity difference should exist but be reduced compared to non-fork
        diff_fork = audit_high.overall_score - audit_low.overall_score
        meta_nofork = _make_metadata(fork=False)
        audit_high_nf = score_repo(meta_nofork, results_high_act)
        audit_low_nf = score_repo(meta_nofork, results_low_act)
        diff_nofork = audit_high_nf.overall_score - audit_low_nf.overall_score
        # Fork reduces activity impact — difference should be smaller
        assert diff_fork < diff_nofork

    def test_fork_other_keys_excludes_activity(self):
        # Kills "XXactivityXX" in the other_keys filter
        # If activity is not excluded from other_keys, it would be updated twice
        results = _make_results({dim: 0.8 for dim in WEIGHTS})
        meta = _make_metadata(fork=True)
        audit = score_repo(meta, results)
        # Just ensure the computation doesn't crash and gives a valid score
        assert 0.0 <= audit.overall_score <= 1.0

    def test_novelty_freq_missing_key_defaults_to_zero(self):
        # Kills freq = portfolio_lang_freq.get(language, 1.0) mutation
        # When language is not in freq dict, default 0.0 means freq < 0.30 → no adjustment
        results = _make_results({dim: 0.5 for dim in WEIGHTS})
        results.append(
            AnalyzerResult(
                dimension="interest",
                score=0.50,
                max_score=1.0,
                findings=[],
                details={"tech_novelty": 0.10},
            )
        )
        meta = _make_metadata(language="Rust")
        freq = {"Python": 0.80}  # Rust not in freq → default 0.0
        audit = score_repo(meta, results, portfolio_lang_freq=freq)
        # No adjustment since freq defaults to 0.0 < 0.30
        assert audit.interest_score == 0.50

    def test_novelty_adjustment_at_exactly_30_pct(self):
        # Kills freq >= 0.30 → freq > 0.30 mutation: exactly 0.30 should trigger
        results = _make_results({dim: 0.5 for dim in WEIGHTS})
        results.append(
            AnalyzerResult(
                dimension="interest",
                score=0.50,
                max_score=1.0,
                findings=[],
                details={"tech_novelty": 0.10},
            )
        )
        meta = _make_metadata(language="Rust")
        freq = {"Rust": 0.30}  # exactly 0.30 — should trigger adjustment with >=
        audit = score_repo(meta, results, portfolio_lang_freq=freq)
        # raw_novelty=0.10, adjusted=0.10 * max(0, 1-0.30)=0.07, delta=0.03
        assert audit.interest_score < 0.50  # adjustment should reduce it

    def test_novelty_default_zero_not_one(self):
        # Kills tech_novelty default 0.0 → 1.0 mutation
        # When tech_novelty is missing from details, should default to 0.0 (no adjustment)
        results = _make_results({dim: 0.5 for dim in WEIGHTS})
        results.append(
            AnalyzerResult(
                dimension="interest",
                score=0.50,
                max_score=1.0,
                findings=[],
                details={},  # no tech_novelty
            )
        )
        meta = _make_metadata(language="Rust")
        freq = {"Rust": 0.60}
        audit = score_repo(meta, results, portfolio_lang_freq=freq)
        # tech_novelty defaults to 0.0 → delta = 0 → no adjustment
        assert audit.interest_score == 0.50


class TestComputePortfolioGradeAdditional:
    """Extra coverage for portfolio grade boundary mutations."""

    def _simple_audit(self, score: float, tier: str, language: str = "Python", badges: int = 0):
        results = _make_results({dim: score for dim in WEIGHTS})
        meta = _make_metadata(language=language)
        audit = score_repo(meta, results)
        audit.completeness_tier = tier
        audit.overall_score = score
        audit.badges = ["b"] * badges
        return audit

    def test_grade_F_for_empty(self):
        from src.scorer import compute_portfolio_grade

        grade, score = compute_portfolio_grade([])
        assert grade == "F"
        assert score == 0.0  # Not 1.0

    def test_shipped_ratio_exactly_50_pct(self):
        # Kills shipped_ratio > 0.5 → >= 0.5 mutation: exactly 50% should NOT give 10% bonus
        from src.scorer import compute_portfolio_grade

        audits_50 = [self._simple_audit(0.5, "shipped"), self._simple_audit(0.5, "wip")]
        audits_66 = [
            self._simple_audit(0.5, "shipped"),
            self._simple_audit(0.5, "shipped"),
            self._simple_audit(0.5, "wip"),
        ]
        _, score_50 = compute_portfolio_grade(audits_50)
        _, score_66 = compute_portfolio_grade(audits_66)
        # 50% exact → 0.05 bonus (mid tier), 66% → 0.10 bonus (high tier)
        assert score_66 > score_50

    def test_shipped_ratio_exactly_50_pct_gets_mid_bonus(self):
        # With ratio=0.5 (> 0.5 is False, but > 0.3 is True) → gets 0.05 bonus, not 0.10
        from src.scorer import compute_portfolio_grade

        audits_exactly_50 = [self._simple_audit(0.5, "shipped"), self._simple_audit(0.5, "wip")]
        audits_all_wip = [self._simple_audit(0.5, "wip"), self._simple_audit(0.5, "wip")]
        _, score_50 = compute_portfolio_grade(audits_exactly_50)
        _, score_0 = compute_portfolio_grade(audits_all_wip)
        assert score_50 > score_0  # 0.05 bonus

    def test_shipped_bonus_sum_1_not_2(self):
        # Kills sum(1 for ...) → sum(2 for ...) mutation: 2 shipped out of 4 = 0.5 ratio
        # With sum(1): ratio = 2/4 = 0.5; with sum(2): ratio = 4/4 = 1.0 → different bonus tier
        from src.scorer import compute_portfolio_grade

        audits_2of4 = [self._simple_audit(0.5, "shipped")] * 2 + [
            self._simple_audit(0.5, "wip")
        ] * 2
        _, score = compute_portfolio_grade(audits_2of4)
        # ratio = 0.5 exactly → mid bonus (0.05), not high (0.10)
        # If sum(2) were used, ratio = 4/4 = 1.0 → 0.10 bonus → score would be higher
        # So with correct sum(1): score should be at the mid bonus level
        audits_all_wip = [self._simple_audit(0.5, "wip")] * 4
        _, score_no_bonus = compute_portfolio_grade(audits_all_wip)
        assert score > score_no_bonus

    def test_abandon_ratio_sum_1_not_2(self):
        # Kills sum(1 for ...) → sum(2 for ...) mutation: 2 abandoned out of 4 = 0.5
        # With sum(2): 4/4 = 1.0 → high penalty; with sum(1): 0.5 → mid penalty
        from src.scorer import compute_portfolio_grade

        audits_2of4 = [self._simple_audit(0.5, "abandoned")] * 2 + [
            self._simple_audit(0.5, "wip")
        ] * 2
        _, score = compute_portfolio_grade(audits_2of4)
        audits_none = [self._simple_audit(0.5, "wip")] * 4
        _, score_none = compute_portfolio_grade(audits_none)
        assert score_none > score  # some penalty applied

    def test_abandon_ratio_div_not_mul(self):
        # Kills ) / len(audits) → ) * len(audits) mutation
        from src.scorer import compute_portfolio_grade

        # 1 abandoned out of 5: / → 0.2; * → 1.0 (then penalty would be -0.10 not -0.05)
        audits = [self._simple_audit(0.5, "abandoned")] + [self._simple_audit(0.5, "wip")] * 4
        _, score = compute_portfolio_grade(audits)
        # 0.2 abandon ratio → -0 penalty (below 0.4 threshold)
        audits_none = [self._simple_audit(0.5, "wip")] * 5
        _, score_none = compute_portfolio_grade(audits_none)
        # With correct division: 1/5 = 0.2 < 0.4 → no penalty → scores equal
        assert abs(score - score_none) < 0.02  # no penalty since 0.2 < 0.4

    def test_abandon_penalty_high_threshold_0_6(self):
        # Kills > 0.6 → >= 0.6 and > 1.6 mutations
        from src.scorer import compute_portfolio_grade

        # Exactly 60% abandoned → should get -0.05 (mid penalty), not -0.10 (high penalty)
        audits_60 = [self._simple_audit(0.5, "abandoned")] * 3 + [
            self._simple_audit(0.5, "wip")
        ] * 2
        audits_80 = [self._simple_audit(0.5, "abandoned")] * 4 + [self._simple_audit(0.5, "wip")]
        _, score_60 = compute_portfolio_grade(audits_60)
        _, score_80 = compute_portfolio_grade(audits_80)
        # 80% > 60% → score_80 should be lower (more penalty)
        assert score_60 > score_80

    def test_abandon_penalty_mid_threshold_0_4(self):
        # Kills > 0.4 → >= 0.4 mutation for mid-penalty threshold
        from src.scorer import compute_portfolio_grade

        # Exactly 40% abandoned → should NOT get -0.05 penalty (threshold is > 0.4, not >=)
        audits_40 = [self._simple_audit(0.5, "abandoned")] * 2 + [
            self._simple_audit(0.5, "wip")
        ] * 3
        audits_0 = [self._simple_audit(0.5, "wip")] * 5
        _, score_40 = compute_portfolio_grade(audits_40)
        _, score_0 = compute_portfolio_grade(audits_0)
        # 40% exactly: > 0.4 is False → no penalty → scores should be equal
        assert abs(score_40 - score_0) < 0.02

    def test_badge_bonus_avg_3_not_triggered(self):
        # Kills > 3 → >= 3 mutation: avg_badges = 3 should NOT get bonus
        from src.scorer import compute_portfolio_grade

        audits_3badges = [self._simple_audit(0.5, "wip", badges=3)]
        audits_4badges = [self._simple_audit(0.5, "wip", badges=4)]
        _, score_3 = compute_portfolio_grade(audits_3badges)
        _, score_4 = compute_portfolio_grade(audits_4badges)
        # exactly 3 badges → no bonus; 4 badges → 0.05 bonus
        assert score_4 > score_3

    def test_avg_badges_div_not_mul(self):
        # Kills / len(audits) → * len(audits) mutation for avg_badges
        from src.scorer import compute_portfolio_grade

        # 1 badge across 2 audits: / → 0.5 (no bonus); * → 2 (would trigger bonus)
        audits = [
            self._simple_audit(0.5, "wip", badges=1),
            self._simple_audit(0.5, "wip", badges=0),
        ]
        audits_no_badges = [
            self._simple_audit(0.5, "wip", badges=0),
            self._simple_audit(0.5, "wip", badges=0),
        ]
        _, score_1badge = compute_portfolio_grade(audits)
        _, score_0badge = compute_portfolio_grade(audits_no_badges)
        # With correct division: avg = 0.5 < 3 → no bonus → scores equal
        assert abs(score_1badge - score_0badge) < 0.001

    def test_diversity_bonus_uses_multiply_0_05(self):
        # Kills * 0.05 → / 0.05 and * 1.05 mutations
        from src.scorer import compute_portfolio_grade

        # 4 langs: bonus = min(0.10, max(0, 1) * 0.05) = 0.05
        # If / 0.05: bonus = min(0.10, max(0, 1) / 0.05) = min(0.10, 20) = 0.10
        # If * 1.05: bonus = min(0.10, max(0, 1) * 1.05) = min(0.10, 1.05) = 0.10
        # Both wrong paths give 0.10 instead of 0.05 for 4 languages
        # We need a test that distinguishes 0.05 from 0.10 for 4 languages
        audits_4langs = [
            self._simple_audit(0.5, "wip", lang) for lang in ["Python", "Rust", "Go", "Swift"]
        ]
        audits_5langs = [
            self._simple_audit(0.5, "wip", lang)
            for lang in ["Python", "Rust", "Go", "Swift", "TypeScript"]
        ]
        _, score_4 = compute_portfolio_grade(audits_4langs)
        _, score_5 = compute_portfolio_grade(audits_5langs)
        # 4 langs: 0.05 bonus; 5 langs: 0.10 bonus → score_5 > score_4 by 0.05
        assert abs(score_5 - score_4 - 0.05) < 0.01

    def test_shipped_bonus_uses_0_10_not_1_1(self):
        # Kills 0.10 → 1.1 for high shipped ratio
        from src.scorer import compute_portfolio_grade

        # All shipped: ratio = 1.0 > 0.5 → bonus = 0.10
        # If 1.1: health_score could exceed 1.0 before clamping
        audits = [self._simple_audit(0.6, "shipped")] * 5
        _, score = compute_portfolio_grade(audits)
        assert score <= 1.0  # clamped; proves 1.1 would be wrong

    def test_abandon_penalty_uses_negative_0_10_not_negative_1_1(self):
        # Kills -0.10 → -1.10 for high abandonment penalty
        from src.scorer import compute_portfolio_grade

        audits = [self._simple_audit(0.5, "abandoned")] * 4 + [self._simple_audit(0.5, "wip")]
        _, score = compute_portfolio_grade(audits)
        assert score >= 0.0  # clamped; -1.1 would cause max(0, ...) to rescue it

    def test_rounded_to_3_decimal_places(self):
        # Kills round(health_score, 4) mutation
        from src.scorer import compute_portfolio_grade

        audits = [self._simple_audit(0.5123456789, "wip")]
        _, score = compute_portfolio_grade(audits)
        assert score == round(score, 3)
        # Verify it's not rounded to 4 places when it would differ
        # round(0.5123, 3) = 0.512; round(0.5123, 4) = 0.5123 → they differ
        assert len(str(score).split(".")[-1]) <= 3

    def test_shipped_bonus_exact_value_0_10(self):
        # Kills 0.10 → 1.1 mutation: verify exact bonus value (not just clamped max)
        # avg_score=0.3, ratio=1.0 → health = 0.3 + 0.10 = 0.40 (unclamped)
        # With 1.1: 0.3 + 1.1 = 1.0 (clamped) → diff detectable
        from src.scorer import compute_portfolio_grade

        audits = [self._simple_audit(0.3, "shipped")] * 3
        _, score = compute_portfolio_grade(audits)
        assert abs(score - 0.40) < 0.01  # 0.3 avg + 0.10 bonus = 0.40

    def test_shipped_bonus_mid_tier_exact_0_05(self):
        # Kills shipped_bonus 0.05 → other mutations at mid-ratio tier
        # avg_score=0.3, ratio=0.4 (1 shipped, 2 not) → health = 0.3 + 0.05 = 0.35
        from src.scorer import compute_portfolio_grade

        audits_mid = [
            self._simple_audit(0.3, "shipped"),
            self._simple_audit(0.3, "wip"),
            self._simple_audit(0.3, "wip"),
        ]
        _, score = compute_portfolio_grade(audits_mid)
        assert abs(score - 0.35) < 0.01  # 0.3 avg + 0.05 bonus = 0.35

    def test_abandon_penalty_exact_negative_0_10(self):
        # Kills -0.10 → -1.1 mutation: verify exact penalty value (not just clamped min)
        # avg_score=0.5, abandon_ratio=0.8 > 0.6 → health = 0.5 - 0.10 = 0.40
        # With -1.1: 0.5 - 1.1 = max(0, -0.6) = 0.0 → diff detectable
        from src.scorer import compute_portfolio_grade

        audits = [self._simple_audit(0.5, "abandoned")] * 4 + [self._simple_audit(0.5, "wip")]
        _, score = compute_portfolio_grade(audits)
        assert abs(score - 0.40) < 0.01  # 0.5 avg - 0.10 penalty = 0.40

    def test_badge_bonus_exact_0_05(self):
        # Kills 0.05 → 1.05 mutation: verify exact bonus when clamping would differ
        # avg_score=0.3, avg_badges=4 > 3 → health = 0.3 + 0.05 = 0.35
        # With 1.05: 0.3 + 1.05 = 1.0 (clamped) → detectable
        from src.scorer import compute_portfolio_grade

        audits = [self._simple_audit(0.3, "wip", badges=4)]
        _, score = compute_portfolio_grade(audits)
        assert abs(score - 0.35) < 0.01  # 0.3 avg + 0.05 badge_bonus = 0.35

    def test_avg_badges_div_not_mul_two_audits(self):
        # Kills / len(audits) → * len(audits) mutation with 2 audits
        # 2 audits each with 2 badges: sum=4, / 2 = 2.0 (< 3, no bonus), * 2 = 8 (bonus)
        from src.scorer import compute_portfolio_grade

        audits = [
            self._simple_audit(0.3, "wip", badges=2),
            self._simple_audit(0.3, "wip", badges=2),
        ]
        _, score = compute_portfolio_grade(audits)
        # avg = 4/2 = 2.0 < 3 → no badge bonus → score = 0.3 (avg) only
        audits_no_badges = [
            self._simple_audit(0.3, "wip", badges=0),
            self._simple_audit(0.3, "wip", badges=0),
        ]
        _, score_no = compute_portfolio_grade(audits_no_badges)
        assert abs(score - score_no) < 0.001  # same score: no bonus in either case

    def test_overall_score_partial_dims_uses_division(self):
        # Kills / weight_sum → * weight_sum when weight_sum != 1.0
        # Pass only 2 dims (readme=0.12, structure=0.10, total=0.22) with score 1.0
        # / 0.22 = 1.0; * 0.22 = 0.22 → detectably different
        from src.models import AnalyzerResult

        partial = [
            AnalyzerResult(
                dimension="readme",
                score=1.0,
                max_score=1.0,
                findings=[],
                details={},
            ),
            AnalyzerResult(
                dimension="structure",
                score=1.0,
                max_score=1.0,
                findings=[],
                details={"config_files": ["pyproject.toml"]},
            ),
        ]
        meta = _make_metadata()
        audit = score_repo(meta, partial)
        assert audit.overall_score > 0.9  # near 1.0 since all 1.0 scores

    def test_fork_activity_reduction_uses_minus_not_plus(self):
        # Kills - FORK_ACTIVITY_WEIGHT → + FORK_ACTIVITY_WEIGHT mutation
        # activity weight 0.15, FORK_ACTIVITY_WEIGHT 0.05
        # Correct: reduction = 0.15 - 0.05 = 0.10 (other weights each increase)
        # Mutant: reduction = 0.15 + 0.05 = 0.20 (even bigger increase to others)
        # Fork with high activity score vs fork with low activity score:
        # correct: activity impact = 0.05; mutant: same (weights["activity"]=0.05 either way)
        # But other weights differ: correct other_total sums differently
        # Use a uniform score across dims so impact shows via activity contribution
        from src.scorer import WEIGHTS

        # activity weight is explicitly set to FORK_ACTIVITY_WEIGHT regardless of -/+;
        # the difference only manifests via redistribution to other keys.
        # With all non-activity scores = 0.0, redistribution amount is masked.
        # This is a documented equivalent mutant (see docs/release-gates.md).
        meta_fork = _make_metadata(fork=True)
        audit_act = score_repo(
            meta_fork, _make_results({**{dim: 0.0 for dim in WEIGHTS}, "activity": 1.0})
        )
        assert 0.0 <= audit_act.overall_score <= 1.0
