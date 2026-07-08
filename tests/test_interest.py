from __future__ import annotations

import pytest

from src.analyzers.interest import (
    InterestAnalyzer,
    _burst_coefficient,
    _count_assets,
    _estimate_loc,
    _score_ambition,
    _score_commit_bursts,
    _score_description,
    _score_readme_storytelling,
    _score_recency,
)
from src.models import RepoMetadata


def _meta(**overrides) -> RepoMetadata:
    from datetime import datetime, timezone
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


class TestDescriptionScoring:
    def test_no_description(self):
        assert _score_description(_meta(description=None)) == 0.0

    def test_short_description(self):
        assert _score_description(_meta(description="A short desc")) == 0.0

    def test_medium_description(self):
        score = _score_description(_meta(description="A medium-length project description that explains what this does"))
        assert score >= 0.10

    def test_long_unique_description(self):
        score = _score_description(_meta(
            name="MyApp",
            description="Interactive animated explainer tracing a dollar through the US banking system with ACH and Fedwire"
        ))
        assert score >= 0.15

    def test_analyze_reports_rich_project_description(self, tmp_repo):
        result = InterestAnalyzer().analyze(
            tmp_repo,
            _meta(
                name="weather",
                description=(
                    "A detailed local weather analysis dashboard with alerts, "
                    "maps, climate comparisons, and historical trend summaries"
                ),
            ),
        )
        assert result.details["description_score"] == pytest.approx(0.15)
        assert "Rich project description" in result.findings

    def test_analyze_reports_basic_description(self, tmp_repo):
        result = InterestAnalyzer().analyze(
            tmp_repo,
            _meta(name="weather", description="Weather tracker app"),
        )
        assert result.details["description_score"] == 0.05
        assert "Basic description" in result.findings

    def test_analyze_reports_no_description(self, tmp_repo):
        result = InterestAnalyzer().analyze(tmp_repo, _meta(description=None))
        assert result.details["description_score"] == 0.0
        assert "No description" in result.findings


class TestCommitBursts:
    def test_empty_weeks(self):
        assert _score_commit_bursts([]) == 0.0

    def test_steady_commits(self):
        # Steady = low variance = low score (CV ≈ 0)
        weeks = [5, 5, 5, 5, 5, 5, 5, 5]
        assert _score_commit_bursts(weeks) == 0.0

    def test_bursty_commits(self):
        # High variance in active weeks = burst pattern
        weeks = [1, 1, 50, 2, 1, 1, 30, 1, 2, 1, 1, 40]
        assert _score_commit_bursts(weeks) >= 0.10

    def test_single_week(self):
        assert _score_commit_bursts([10]) == 0.0

    def test_inactive_weeks_only_do_not_score(self):
        assert _score_commit_bursts([0, 0, 7, 0]) == 0.0

    def test_medium_high_variance_scores_ten_points(self):
        assert _score_commit_bursts([1, 1, 1, 5]) == 0.10

    def test_moderate_variance_scores_five_points(self):
        assert _score_commit_bursts([1, 1, 2, 3]) == 0.05


class TestBurstCoefficient:
    def test_empty_and_short_series_return_zero(self):
        assert _burst_coefficient([]) == 0.0
        assert _burst_coefficient([0, 0, 9]) == 0.0

    def test_computes_rounded_coefficient_for_active_weeks(self):
        assert _burst_coefficient([0, 1, 1, 2, 3]) == 0.55

    def test_zero_mean_branch_is_unreachable_after_positive_week_filter(self):
        # The production filter keeps only w > 0, so any remaining active week
        # makes the mean positive and this still returns the short-series guard.
        assert _burst_coefficient([0, 0, 0, 0]) == 0.0


class TestAnalyzeCommitBursts:
    class _GitHubClientStub:
        def __init__(self, owner_weeks):
            self.owner_weeks = owner_weeks

        def get_participation_stats(self, owner, repo):
            assert (owner, repo) == ("user", "test")
            return {"owner": self.owner_weeks}

    def test_analyze_reports_passionate_burst_pattern(self, tmp_repo):
        result = InterestAnalyzer().analyze(
            tmp_repo,
            _meta(),
            github_client=self._GitHubClientStub([1, 1, 50, 2, 1, 1]),
        )
        assert result.details["burst_coefficient"] > 1.0
        assert "Passionate burst development pattern" in result.findings

    def test_analyze_reports_some_development_bursts(self, tmp_repo):
        result = InterestAnalyzer().analyze(
            tmp_repo,
            _meta(),
            github_client=self._GitHubClientStub([1, 1, 2, 3]),
        )
        assert result.details["burst_coefficient"] == 0.55
        assert "Some development bursts" in result.findings


class TestRecencyBonus:
    def test_recent_push_gets_max(self):
        from datetime import datetime, timedelta, timezone
        meta = _meta(pushed_at=datetime.now(timezone.utc) - timedelta(days=30))
        assert _score_recency(meta) == 0.05

    def test_medium_age_gets_partial(self):
        from datetime import datetime, timedelta, timezone
        meta = _meta(pushed_at=datetime.now(timezone.utc) - timedelta(days=150))
        assert _score_recency(meta) == 0.03

    def test_within_year_gets_small(self):
        from datetime import datetime, timedelta, timezone
        meta = _meta(pushed_at=datetime.now(timezone.utc) - timedelta(days=300))
        assert _score_recency(meta) == 0.01

    def test_old_push_no_bonus(self):
        from datetime import datetime, timedelta, timezone
        meta = _meta(pushed_at=datetime.now(timezone.utc) - timedelta(days=500))
        assert _score_recency(meta) == 0.0

    def test_no_pushed_at(self):
        meta = _meta(pushed_at=None)
        assert _score_recency(meta) == 0.0


class TestTechNovelty:
    def test_novel_language_scores(self, tmp_repo):
        meta = _meta(language="Rust", languages={"Rust": 5000, "TypeScript": 3000, "Python": 1000})
        result = InterestAnalyzer().analyze(tmp_repo, meta)
        # Rust is novel + 3 languages = multi-language
        assert result.score >= 0.20

    def test_common_language(self, tmp_repo):
        meta = _meta(language="JavaScript", languages={"JavaScript": 5000})
        result = InterestAnalyzer().analyze(tmp_repo, meta)
        # JS is not novel, single language
        details = result.details
        assert details["tech_novelty"] == 0.0


class TestTopicScoring:
    def test_three_topics_receive_full_topic_score(self, tmp_repo):
        result = InterestAnalyzer().analyze(
            tmp_repo,
            _meta(topics=["portfolio", "automation", "analytics"]),
        )
        assert result.details["topic_count"] == 3
        assert result.score >= 0.10
        assert "Topics: portfolio, automation, analytics" in result.findings


class TestExternalValidation:
    def test_stars_and_forks_add_validation_findings(self, tmp_repo):
        result = InterestAnalyzer().analyze(tmp_repo, _meta(stars=3, forks=2))
        assert "Stars: 3" in result.findings
        assert "Forks: 2" in result.findings


class TestProjectAmbition:
    def test_large_repo_with_assets(self, tmp_repo):
        # Add some code and assets
        (tmp_repo / "assets").mkdir()
        (tmp_repo / "assets" / "logo.png").write_bytes(b"PNG")
        (tmp_repo / "assets" / "sound.mp3").write_bytes(b"MP3")
        meta = _meta()
        result = InterestAnalyzer().analyze(tmp_repo, meta)
        assert result.details["ambition"]["asset_count"] >= 2

    def test_large_loc_repo_gets_ambition_bonus(self, tmp_repo):
        baseline_loc = _estimate_loc(tmp_repo)
        (tmp_repo / "main.py").write_text("\n".join(f"line_{i} = {i}" for i in range(1001)))
        score, details = _score_ambition(tmp_repo, _meta())
        assert details["estimated_loc"] == baseline_loc + 1001
        assert score >= 0.10

    def test_loc_estimate_stops_after_max_files(self, tmp_repo):
        repo = tmp_repo / "many-files"
        repo.mkdir()
        for index in range(205):
            (repo / f"file_{index:03}.py").write_text("x = 1\n")
        assert _estimate_loc(repo) == 200

    def test_loc_estimate_skips_dotfiles_and_node_modules(self, tmp_repo):
        repo = tmp_repo / "skip-paths"
        repo.mkdir()
        (repo / ".hidden").mkdir()
        (repo / ".hidden" / "ignored.py").write_text("x = 1\n" * 50)
        (repo / "node_modules").mkdir()
        (repo / "node_modules" / "ignored.js").write_text("x = 1\n" * 50)
        (repo / "visible.py").write_text("a = 1\nb = 2\nc = 3\n")
        assert _estimate_loc(repo) == 3

    def test_loc_estimate_continues_after_oserror(self, tmp_repo, monkeypatch):
        repo = tmp_repo / "oserror"
        repo.mkdir()
        bad_file = repo / "bad.py"
        good_file = repo / "good.py"
        bad_file.write_text("unreadable\n")
        good_file.write_text("a = 1\nb = 2\n")
        original_read_text = type(bad_file).read_text

        def raise_for_bad_files(path, *args, **kwargs):
            if path == bad_file:
                raise OSError("cannot read")
            return original_read_text(path, *args, **kwargs)

        monkeypatch.setattr(type(bad_file), "read_text", raise_for_bad_files)
        assert _estimate_loc(repo) == 2

    def test_asset_count_stops_after_max_scan(self, tmp_repo):
        repo = tmp_repo / "many-assets"
        repo.mkdir()
        scanned_files = []
        for index in range(500):
            path = repo / f"{index:03}.txt"
            path.write_text("not an asset\n")
            scanned_files.append(path)
        late_asset = repo / "late.png"
        late_asset.write_bytes(b"PNG")

        class FakeRepo:
            def rglob(self, pattern):
                assert pattern == "*"
                yield from scanned_files
                yield late_asset

        assert _count_assets(FakeRepo()) == 0

    def test_asset_count_counts_asset_within_max_scan(self, tmp_repo):
        repo = tmp_repo / "early-asset"
        repo.mkdir()
        scanned_files = []
        for index in range(10):
            path = repo / f"{index:03}.txt"
            path.write_text("not an asset\n")
            scanned_files.append(path)
        early_asset = repo / "early.png"
        early_asset.write_bytes(b"PNG")

        class FakeRepo:
            def rglob(self, pattern):
                assert pattern == "*"
                yield from scanned_files
                yield early_asset

        assert _count_assets(FakeRepo()) == 1


class TestReadmeStorytelling:
    def test_long_readme_with_images(self, tmp_repo):
        (tmp_repo / "README.md").write_text(
            "# Amazing Project\n\n"
            "This is a long and detailed description. " * 30
            + "\n\n![screenshot](./screenshot.png)\n"
        )
        result = InterestAnalyzer().analyze(tmp_repo, _meta())
        assert result.details["readme_storytelling"] >= 0.10

    def test_short_readme_no_images(self, tmp_repo):
        (tmp_repo / "README.md").write_text("# Short\n\nBrief.\n")
        result = InterestAnalyzer().analyze(tmp_repo, _meta())
        assert result.details["readme_storytelling"] == 0.0

    def test_missing_readme_scores_zero(self, tmp_repo):
        repo = tmp_repo / "no-readme"
        repo.mkdir()
        assert _score_readme_storytelling(repo) == 0.0

    def test_readme_oserror_scores_zero(self, tmp_repo, monkeypatch):
        readme = tmp_repo / "README.md"
        readme.write_text("# Present but unreadable\n")

        def raise_oserror(*args, **kwargs):
            raise OSError("cannot read")

        monkeypatch.setattr(type(readme), "read_text", raise_oserror)
        assert _score_readme_storytelling(tmp_repo) == 0.0
