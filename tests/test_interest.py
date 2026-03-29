from __future__ import annotations

from pathlib import Path

from src.analyzers.interest import (
    InterestAnalyzer,
    _score_commit_bursts,
    _score_description,
    _score_recency,
    _burst_coefficient,
    _count_assets,
    _estimate_loc,
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


class TestProjectAmbition:
    def test_large_repo_with_assets(self, tmp_repo):
        # Add some code and assets
        (tmp_repo / "assets").mkdir()
        (tmp_repo / "assets" / "logo.png").write_bytes(b"PNG")
        (tmp_repo / "assets" / "sound.mp3").write_bytes(b"MP3")
        meta = _meta()
        result = InterestAnalyzer().analyze(tmp_repo, meta)
        assert result.details["ambition"]["asset_count"] >= 2


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
