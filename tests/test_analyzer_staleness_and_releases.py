"""Tests for Sprint 1.4: README staleness + release-shipped signal.

README staleness tests live in TestReadmeStaleness.
Release-shipped signal tests live in TestActivityReleaseSignals.
"""
from __future__ import annotations

import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.analyzers.activity import ActivityAnalyzer
from src.analyzers.readme import ReadmeAnalyzer, _compute_readme_staleness
from src.models import RepoMetadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
        pushed_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
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


def _make_release(
    tag: str = "v1.0.0",
    published_at: str = "2026-03-01T00:00:00Z",
    prerelease: bool = False,
) -> dict:
    return {
        "tag_name": tag,
        "name": tag,
        "published_at": published_at,
        "created_at": published_at,
        "prerelease": prerelease,
        "draft": False,
    }


def _make_git_repo(tmp_path: Path, readme_ts: int, code_ts: int) -> Path:
    """Create a minimal git repo where README and code have controlled commit timestamps."""
    repo = tmp_path / "repo"
    repo.mkdir()

    env_base = {"GIT_CONFIG_NOSYSTEM": "1", "HOME": str(tmp_path)}

    def run(*args: str, env_extra: dict | None = None) -> None:
        env = {**env_base, **(env_extra or {})}
        subprocess.run(
            list(args),
            cwd=repo,
            check=True,
            capture_output=True,
            env=env,
        )

    run("git", "init")
    run("git", "config", "user.email", "test@test.com")
    run("git", "config", "user.name", "Test")

    # Commit 1: add code file at code_ts
    (repo / "main.py").write_text("print('hello')\n")
    run("git", "add", "main.py")
    ts_str = str(code_ts)
    run(
        "git", "commit", "-m", "add code",
        env_extra={
            "GIT_AUTHOR_DATE": ts_str,
            "GIT_COMMITTER_DATE": ts_str,
        },
    )

    # Commit 2: add README at readme_ts
    (repo / "README.md").write_text(
        "# Test\n\nA project for testing.\n\n"
        "## Installation\n\n```bash\npip install x\n```\n"
    )
    run("git", "add", "README.md")
    run(
        "git", "commit", "-m", "add readme",
        env_extra={
            "GIT_AUTHOR_DATE": str(readme_ts),
            "GIT_COMMITTER_DATE": str(readme_ts),
        },
    )

    return repo


# ---------------------------------------------------------------------------
# README staleness tests
# ---------------------------------------------------------------------------


class TestReadmeStaleness:
    def test_fresh_readme_and_fresh_code_returns_ratio(self, tmp_path: Path) -> None:
        """README and code both touched today → all staleness fields populated."""
        now = int(time.time())
        repo = _make_git_repo(tmp_path, readme_ts=now, code_ts=now)

        staleness = _compute_readme_staleness(repo, "README.md")

        assert staleness["readme_last_touched_days"] is not None
        assert staleness["code_last_touched_days"] is not None
        # Both touched today; days = 0, ratio = 0/1 = 0.0, stale field is a bool
        assert staleness["readme_staleness_ratio"] is not None
        assert isinstance(staleness["readme_stale"], bool)

    def test_old_readme_vs_fresh_code_not_flagged_stale(self, tmp_path: Path) -> None:
        """README 365 days old, code 7 days old → ratio = 365/7 ≈ 52 (>> 0.2) → NOT stale.

        The stale flag uses: ratio < 0.2 AND code_days < 90.
        readme_days/code_days = 365/7 >> 0.2 so the condition is false.
        (Stale = README proportionally newer than code with fresh code activity.)
        """
        now = int(time.time())
        readme_ts = now - 365 * 86400
        code_ts = now - 7 * 86400
        repo = _make_git_repo(tmp_path, readme_ts=readme_ts, code_ts=code_ts)

        staleness = _compute_readme_staleness(repo, "README.md")

        assert staleness["readme_last_touched_days"] is not None
        assert staleness["code_last_touched_days"] is not None
        # ratio = readme_days / code_days ≈ 365/7 >> 1
        assert staleness["readme_staleness_ratio"] is not None
        assert staleness["readme_staleness_ratio"] > 1.0
        # Per spec: stale = ratio < 0.2 AND code < 90 — false here (ratio >> 0.2)
        assert staleness["readme_stale"] is False

    def test_fresh_readme_vs_old_code_flags_stale(self, tmp_path: Path) -> None:
        """README touched 1 day ago, code 60 days ago → ratio ~0.017 < 0.2, code < 90 → stale."""
        now = int(time.time())
        readme_ts = now - 1 * 86400   # 1 day ago
        code_ts = now - 60 * 86400    # 60 days ago
        repo = _make_git_repo(tmp_path, readme_ts=readme_ts, code_ts=code_ts)

        staleness = _compute_readme_staleness(repo, "README.md")

        # ratio = 1/60 ≈ 0.017 < 0.2, code_days = 60 < 90 → stale
        assert staleness["readme_stale"] is True
        assert staleness["readme_staleness_ratio"] < 0.2

    def test_no_readme_returns_none_fields(self, tmp_path: Path) -> None:
        """When repo_path has no git history for README, new fields are None."""
        # No git repo — subprocess git log will fail gracefully
        repo = tmp_path / "bare"
        repo.mkdir()

        staleness = _compute_readme_staleness(repo, "README.md")

        assert staleness["readme_last_touched_days"] is None
        assert staleness["code_last_touched_days"] is None
        assert staleness["readme_staleness_ratio"] is None
        assert staleness["readme_stale"] is None

    def test_docs_only_repo_skips_staleness(self, tmp_path: Path) -> None:
        """No code files → staleness skipped, no exception, code_last_touched_days is None."""
        now = int(time.time())
        readme_ts = now - 10 * 86400
        repo = tmp_path / "docs-only"
        repo.mkdir()

        env_base = {"GIT_CONFIG_NOSYSTEM": "1", "HOME": str(tmp_path)}

        def run(*args: str, env_extra: dict | None = None) -> None:
            env = {**env_base, **(env_extra or {})}
            subprocess.run(list(args), cwd=repo, check=True, capture_output=True, env=env)

        run("git", "init")
        run("git", "config", "user.email", "t@t.com")
        run("git", "config", "user.name", "T")
        (repo / "README.md").write_text("# Docs\n")
        run("git", "add", "README.md")
        ts_str = str(readme_ts)
        run("git", "commit", "-m", "docs",
            env_extra={"GIT_AUTHOR_DATE": ts_str, "GIT_COMMITTER_DATE": ts_str})

        staleness = _compute_readme_staleness(repo, "README.md")

        assert staleness["code_last_touched_days"] is None
        assert staleness["readme_staleness_ratio"] is None
        assert staleness["readme_stale"] is None
        # readme_last_touched_days is populated though
        assert staleness["readme_last_touched_days"] is not None

    def test_analyze_no_readme_includes_null_staleness_fields(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """ReadmeAnalyzer returns None staleness fields when no README exists."""
        repo = tmp_path / "no-readme"
        repo.mkdir()
        meta = _make_metadata()

        result = ReadmeAnalyzer().analyze(repo, meta)

        assert result.details.get("readme_last_touched_days") is None
        assert result.details.get("readme_staleness_ratio") is None
        assert result.details.get("readme_stale") is None

    def test_analyze_with_readme_includes_staleness_keys(
        self, tmp_path: Path
    ) -> None:
        """ReadmeAnalyzer always includes staleness keys in details."""
        repo = tmp_path / "with-readme"
        repo.mkdir()
        (repo / "README.md").write_text(
            "# Project\n\nA project.\n\n"
            "## Install\n\n```bash\npip install x\n```\n"
        )
        meta = _make_metadata()

        result = ReadmeAnalyzer().analyze(repo, meta)

        assert "readme_last_touched_days" in result.details
        assert "code_last_touched_days" in result.details
        assert "readme_staleness_ratio" in result.details
        assert "readme_stale" in result.details


# ---------------------------------------------------------------------------
# Activity analyzer — release-shipped signal tests
# ---------------------------------------------------------------------------


class TestActivityReleaseSignals:
    def _make_client(self, releases: list[dict], available: bool = True) -> MagicMock:
        client = MagicMock()
        client.get_releases.return_value = (releases, available)
        client.get_contributor_stats.return_value = [{"total": 5}]
        client.get_commit_activity.return_value = []
        return client

    def test_repo_with_three_releases(self, tmp_path: Path) -> None:
        """has_any_release=True, release_count=3, latest_release_age_days correct."""
        now = datetime.now(timezone.utc)
        # Latest release published 30 days ago
        pub = (now.replace(microsecond=0).isoformat()).replace("+00:00", "Z")
        # Hack: set 30 days ago
        from datetime import timedelta
        pub30 = (now - timedelta(days=30)).isoformat().replace("+00:00", "Z")
        pub60 = (now - timedelta(days=60)).isoformat().replace("+00:00", "Z")
        pub90 = (now - timedelta(days=90)).isoformat().replace("+00:00", "Z")

        releases = [
            _make_release("v3.0", pub30),
            _make_release("v2.0", pub60),
            _make_release("v1.0", pub90),
        ]
        client = self._make_client(releases)
        meta = _make_metadata()

        result = ActivityAnalyzer().analyze(tmp_path, meta, github_client=client)

        assert result.details["has_any_release"] is True
        assert result.details["release_count"] == 3
        assert result.details["releases_available"] is True
        assert result.details["latest_release_is_prerelease"] is False
        age = result.details["latest_release_age_days"]
        assert age is not None
        assert 28 <= age <= 32  # allow ±2 days for test timing

    def test_repo_with_zero_releases(self, tmp_path: Path) -> None:
        """has_any_release=False, release_count=0, age None."""
        client = self._make_client([], available=True)
        meta = _make_metadata()

        result = ActivityAnalyzer().analyze(tmp_path, meta, github_client=client)

        assert result.details["has_any_release"] is False
        assert result.details["release_count"] == 0
        assert result.details["latest_release_age_days"] is None
        assert result.details["latest_release_is_prerelease"] is False
        assert result.details["releases_available"] is True

    def test_releases_endpoint_404_returns_unavailable(self, tmp_path: Path) -> None:
        """On 404, releases_available=False, fields zeroed, no exception."""
        client = self._make_client([], available=False)
        meta = _make_metadata()

        result = ActivityAnalyzer().analyze(tmp_path, meta, github_client=client)

        assert result.details["releases_available"] is False
        assert result.details["has_any_release"] is False
        assert result.details["release_count"] == 0
        assert result.details["latest_release_age_days"] is None
        assert result.details["latest_release_is_prerelease"] is False

    def test_prerelease_flag_propagated(self, tmp_path: Path) -> None:
        """If latest release is a prerelease, latest_release_is_prerelease=True."""
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        pub = (now - timedelta(days=5)).isoformat().replace("+00:00", "Z")

        releases = [_make_release("v2.0-beta", pub, prerelease=True)]
        client = self._make_client(releases)
        meta = _make_metadata()

        result = ActivityAnalyzer().analyze(tmp_path, meta, github_client=client)

        assert result.details["latest_release_is_prerelease"] is True
        assert result.details["has_any_release"] is True

    def test_no_client_skips_release_fields(self, tmp_path: Path) -> None:
        """Without a github_client, release fields are absent from details."""
        meta = _make_metadata()

        result = ActivityAnalyzer().analyze(tmp_path, meta, github_client=None)

        # When no client, API checks are skipped entirely
        assert "has_any_release" not in result.details
        assert "release_count" not in result.details
