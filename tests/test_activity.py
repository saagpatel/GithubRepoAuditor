from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.analyzers.activity import (
    ActivityAnalyzer,
    _classify_commit_pattern,
    _compute_bus_factor,
    _count_clusters,
    _recent_commit_count,
)
from src.models import RepoMetadata


def _make_metadata(**kwargs) -> RepoMetadata:
    defaults = dict(
        name="test-repo",
        full_name="user/test-repo",
        description="A test repo",
        language="Python",
        languages={"Python": 5000},
        private=False,
        fork=False,
        archived=False,
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        pushed_at=datetime.now(timezone.utc) - timedelta(days=30),
        default_branch="main",
        stars=5,
        forks=1,
        open_issues=0,
        size_kb=512,
        html_url="https://github.com/user/test-repo",
        clone_url="https://github.com/user/test-repo.git",
        topics=[],
    )
    defaults.update(kwargs)
    return RepoMetadata(**defaults)


def _make_client(
    *,
    contributor_stats: list[dict] | None = None,
    commit_activity: list[dict] | None = None,
    releases: list[dict] | None = None,
    releases_available: bool = True,
) -> MagicMock:
    client = MagicMock()
    client.get_contributor_stats.return_value = contributor_stats or []
    client.get_commit_activity.return_value = commit_activity or []
    client.get_releases.return_value = (releases or [], releases_available)
    return client


def _weeks(totals: list[int]) -> list[dict]:
    return [{"total": total} for total in totals]


def _release(
    tag: str,
    published_at: object | None = "2026-03-01T00:00:00Z",
    *,
    created_at: object | None = None,
    prerelease: bool = False,
) -> dict:
    return {
        "tag_name": tag,
        "name": tag,
        "published_at": published_at,
        "created_at": published_at if created_at is None else created_at,
        "prerelease": prerelease,
        "draft": False,
    }


class TestActivityAnalyze:
    def test_within_one_year_push_scores_recent_branch(self, tmp_path: Path) -> None:
        metadata = _make_metadata(
            pushed_at=datetime.now(timezone.utc) - timedelta(days=240),
        )

        result = ActivityAnalyzer().analyze(tmp_path, metadata, github_client=None)

        assert result.score == pytest.approx(0.3)
        assert result.details["days_since_push"] >= 239
        assert "Recent: pushed" in result.findings[0]
        assert "Skipped API-based activity checks" in result.findings

    def test_stale_push_and_archived_repo_do_not_add_activity_points(
        self, tmp_path: Path
    ) -> None:
        metadata = _make_metadata(
            archived=True,
            pushed_at=datetime.now(timezone.utc) - timedelta(days=500),
        )

        result = ActivityAnalyzer().analyze(tmp_path, metadata, github_client=None)

        assert result.score == 0.0
        assert result.details["archived"] is True
        assert "Stale: last push" in result.findings[0]
        assert "Repo is archived" in result.findings

    def test_missing_push_date_keeps_days_since_push_absent(
        self, tmp_path: Path
    ) -> None:
        metadata = _make_metadata(pushed_at=None)

        result = ActivityAnalyzer().analyze(tmp_path, metadata, github_client=None)

        assert result.score == pytest.approx(0.1)
        assert "days_since_push" not in result.details
        assert result.findings[0] == "No push date available"
        assert "Not archived" in result.findings

    def test_api_checks_score_total_commits_recent_commits_and_bus_factor(
        self, tmp_path: Path
    ) -> None:
        commit_activity = _weeks([0] * 39 + [1] * 13)
        client = _make_client(
            contributor_stats=[{"total": 8}, {"total": 4}],
            commit_activity=commit_activity,
            releases=[],
        )

        result = ActivityAnalyzer().analyze(
            tmp_path,
            _make_metadata(),
            github_client=client,
        )

        assert result.score == pytest.approx(0.8)
        assert result.details["total_commits"] == 12
        assert result.details["recent_3mo_commits"] == 13
        assert result.details["commit_pattern"] == "new"
        assert result.details["bus_factor"] == 1
        assert result.details["has_any_release"] is False
        assert "Total commits: 12" in result.findings
        assert "Recent commits (3mo): 13" in result.findings
        assert "No releases found" in result.findings

    def test_api_checks_report_few_commits_no_recent_commits_and_unavailable_releases(
        self, tmp_path: Path
    ) -> None:
        client = _make_client(
            contributor_stats=[{"total": 5}],
            commit_activity=[],
            releases=[],
            releases_available=False,
        )

        result = ActivityAnalyzer().analyze(
            tmp_path,
            _make_metadata(),
            github_client=client,
        )

        assert result.score == pytest.approx(0.5)
        assert result.details["total_commits"] == 5
        assert result.details["recent_3mo_commits"] == 0
        assert result.details["commit_pattern"] == "unknown"
        assert result.details["bus_factor"] == 1
        assert result.details["releases_available"] is False
        assert "Few commits: 5" in result.findings
        assert "No commits in last 3 months" in result.findings
        assert "Releases endpoint unavailable (404)" in result.findings

    def test_api_checks_report_zero_commit_count(self, tmp_path: Path) -> None:
        client = _make_client(
            contributor_stats=[],
            commit_activity=[],
            releases=[],
        )

        result = ActivityAnalyzer().analyze(
            tmp_path,
            _make_metadata(),
            github_client=client,
        )

        assert result.score == pytest.approx(0.4)
        assert result.details["total_commits"] == 0
        assert result.details["bus_factor"] == 0
        assert "Zero or unknown commit count" in result.findings

    @pytest.mark.parametrize("malformed", ["not-a-date", b"not-a-date"])
    def test_malformed_latest_release_timestamp_sets_age_to_none(
        self, tmp_path: Path, malformed: object
    ) -> None:
        client = _make_client(
            contributor_stats=[{"total": 11}],
            commit_activity=_weeks([0] * 39 + [1] * 13),
            releases=[
                _release("v2.0", malformed),
                _release("v1.0", "2026-01-01T00:00:00Z"),
            ],
        )

        result = ActivityAnalyzer().analyze(
            tmp_path,
            _make_metadata(),
            github_client=client,
        )

        assert result.details["latest_release_age_days"] is None
        assert result.details["release_count"] == 2
        assert "release_cadence_days" not in result.details
        assert "Releases: 2" in result.findings

    def test_release_without_timestamp_sets_age_to_none(self, tmp_path: Path) -> None:
        client = _make_client(
            contributor_stats=[{"total": 11}],
            commit_activity=_weeks([0] * 39 + [1] * 13),
            releases=[_release("v1.0", "", created_at="")],
        )

        result = ActivityAnalyzer().analyze(
            tmp_path,
            _make_metadata(),
            github_client=client,
        )

        assert result.details["latest_release_age_days"] is None
        assert result.details["latest_release_is_prerelease"] is False
        assert result.details["release_count"] == 1

    def test_valid_release_dates_compute_rounded_cadence(self, tmp_path: Path) -> None:
        client = _make_client(
            contributor_stats=[{"total": 11}],
            commit_activity=_weeks([0] * 39 + [1] * 13),
            releases=[
                _release("v3.0", "2026-03-01T00:00:00Z", prerelease=True),
                _release("v2.0", "2026-01-31T00:00:00Z"),
                _release("v1.0", "2026-01-01T00:00:00Z"),
            ],
        )

        result = ActivityAnalyzer().analyze(
            tmp_path,
            _make_metadata(),
            github_client=client,
        )

        assert result.details["release_cadence_days"] == 30
        assert result.details["latest_release_is_prerelease"] is True
        assert result.details["has_any_release"] is True


class TestActivityHelpers:
    def test_recent_commit_count_sums_only_last_thirteen_weeks(self) -> None:
        activity = _weeks([100] * 39 + list(range(13)))

        assert _recent_commit_count(activity) == 78
        assert _recent_commit_count([]) == 0

    @pytest.mark.parametrize(
        ("totals", "expected"),
        [
            ([], "unknown"),
            ([0] * 52, "dormant"),
            ([2] + [0] * 51, "dormant"),
            ([0] * 39 + [1] * 13, "new"),
            ([1] * 20 + [0] * 6 + [1] + [0] * 25, "steady"),
            ([10] * 9 + [0] * 30 + [5] + [0] * 12, "winding-down"),
            ([0] * 20 + [10] * 3 + [0] * 16 + [10] * 4 + [0] * 9, "burst"),
            ([0] * 10 + [1] * 6 + [0] * 24 + [1] * 6 + [0] * 6, "seasonal"),
            ([0] * 30 + [1] * 12 + [0] * 10, "burst"),
        ],
    )
    def test_classify_commit_pattern_branches(
        self, totals: list[int], expected: str
    ) -> None:
        assert _classify_commit_pattern(_weeks(totals)) == expected

    def test_count_clusters_resets_only_after_minimum_gap(self) -> None:
        assert _count_clusters([1, 1, 0, 0, 0, 0, 2]) == 2
        assert _count_clusters([1, 0, 0, 0, 2]) == 1

    @pytest.mark.parametrize(
        ("stats", "expected"),
        [
            ([], 0),
            ([{"total": 0}, {"total": 0}], 0),
            ([{"total": 80}, {"total": 10}, {"total": 10}], 1),
            ([{"total": 25}, {"total": 25}, {"total": 25}, {"total": 25}], 2),
        ],
    )
    def test_compute_bus_factor_branches(
        self, stats: list[dict], expected: int
    ) -> None:
        assert _compute_bus_factor(stats) == expected
