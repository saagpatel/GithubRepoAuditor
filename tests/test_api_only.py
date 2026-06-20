from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import patch

import requests

from src.api_only import (
    API_ONLY_MODE,
    ApiOnlyReport,
    _list_user_repos,
    audit_user_api_only,
    score_repos_api_only,
)
from src.models import RepoMetadata


class _RepoListClient:
    """Stub exposing only the repo-list surface (.token + .list_repos)."""

    def __init__(self, token: str | None, rest_repos: list[dict]) -> None:
        self.token = token
        self._rest_repos = rest_repos
        self.list_repos_calls = 0

    def list_repos(self, username: str) -> list[dict]:
        self.list_repos_calls += 1
        return self._rest_repos


def test_list_user_repos_prefers_graphql_with_token() -> None:
    client = _RepoListClient(token="t", rest_repos=[{"name": "rest"}])
    gql = [{"name": "graphql"}]
    with patch("src.api_only.bulk_fetch_repos", return_value=gql) as mock_gql:
        result = _list_user_repos("octocat", client)  # type: ignore[arg-type]
    assert result == gql
    assert client.list_repos_calls == 0
    mock_gql.assert_called_once()


def test_list_user_repos_uses_rest_without_token() -> None:
    client = _RepoListClient(token=None, rest_repos=[{"name": "rest"}])
    with patch("src.api_only.bulk_fetch_repos") as mock_gql:
        result = _list_user_repos("octocat", client)  # type: ignore[arg-type]
    assert result == [{"name": "rest"}]
    assert client.list_repos_calls == 1
    mock_gql.assert_not_called()


def test_list_user_repos_falls_back_when_graphql_user_null() -> None:
    # GraphQL returns user: null → mapping raises TypeError → fall back to REST.
    client = _RepoListClient(token="t", rest_repos=[{"name": "rest"}])
    with patch("src.api_only.bulk_fetch_repos", side_effect=TypeError("user is None")):
        result = _list_user_repos("ghost", client)  # type: ignore[arg-type]
    assert result == [{"name": "rest"}]
    assert client.list_repos_calls == 1


def test_list_user_repos_falls_back_on_graphql_http_error() -> None:
    client = _RepoListClient(token="t", rest_repos=[{"name": "rest"}])
    with patch(
        "src.api_only.bulk_fetch_repos",
        side_effect=requests.ConnectionError("boom"),
    ):
        result = _list_user_repos("octocat", client)  # type: ignore[arg-type]
    assert result == [{"name": "rest"}]
    assert client.list_repos_calls == 1


def _meta(
    name: str = "demo", full_name: str = "octocat/demo", language: str = "Python"
) -> RepoMetadata:
    dt = datetime(2024, 6, 1, tzinfo=timezone.utc)
    return RepoMetadata(
        name=name,
        full_name=full_name,
        description="A demo project",
        language=language,
        languages={},
        private=False,
        fork=False,
        archived=False,
        created_at=dt,
        updated_at=dt,
        pushed_at=dt,
        default_branch="main",
        stars=12,
        forks=2,
        open_issues=1,
        size_kb=200,
        html_url="https://github.com/octocat/demo",
        clone_url="https://github.com/octocat/demo.git",
        topics=["cli"],
    )


def _rich_tree() -> dict:
    return {
        "available": True,
        "truncated": False,
        "files": [
            "README.md",
            "pyproject.toml",
            "src/app.py",
            "tests/test_app.py",
            ".github/workflows/ci.yml",
        ],
        "dirs": ["src", "tests", ".github", ".github/workflows"],
    }


class _FakeClient:
    """Minimal duck-typed client: tree + content + repo list. No HTTP.

    Analyzers that reach for API-only endpoints (activity, community, security)
    fail soft inside ``run_all_analyzers`` — exactly the API-only fidelity floor.
    """

    def __init__(
        self,
        tree: dict,
        contents: dict[str, str] | None = None,
        repos: list[dict] | None = None,
    ) -> None:
        self._tree = tree
        self._contents = contents or {}
        self._repos = repos or []

    def get_repo_tree(self, owner: str, repo: str, ref: str) -> dict:
        return self._tree

    def get_file_content(
        self, owner, repo, path, *, ref=None, max_bytes=1_000_000
    ) -> str | None:
        return self._contents.get(path)

    def list_repos(self, username: str) -> list[dict]:
        return self._repos


def test_score_repos_api_only_runs_real_engine_without_clone():
    contents = {
        "README.md": (
            "# App\n\nA real project that does a real thing.\n\n"
            "## Usage\n\nRun it.\n\n## Install\n\npip install app\n"
        ),
        "pyproject.toml": "[project]\nname = 'app'\n\n[tool.pytest.ini_options]\n",
    }
    client = _FakeClient(_rich_tree(), contents)

    audits = score_repos_api_only([_meta()], client)

    assert len(audits) == 1
    audit = audits[0]
    assert audit.metadata.name == "demo"
    assert 0.0 <= audit.overall_score <= 1.0

    dims = {r.dimension: r.score for r in audit.analyzer_results}
    # Presence signals recovered from the API tree alone — no clone:
    assert dims["testing"] > 0  # tests/ dir + test file present
    assert dims["readme"] > 0  # README present, with content
    assert dims["cicd"] > 0  # .github/workflows/ci.yml present
    assert dims["structure"] > 0


def test_bare_repo_is_detected_as_having_no_tests():
    tree = {"available": True, "truncated": False, "files": ["README.md"], "dirs": []}
    client = _FakeClient(tree, {"README.md": "# bare\n"})

    audits = score_repos_api_only([_meta(name="bare", full_name="o/bare")], client)

    audit = audits[0]
    dims = {r.dimension: r.score for r in audit.analyzer_results}
    assert dims["testing"] == 0.0
    assert "no-tests" in audit.flags


def test_audit_user_api_only_lists_then_scores():
    repo_dict = {
        "name": "demo",
        "full_name": "octocat/demo",
        "description": "A demo project",
        "language": "Python",
        "private": False,
        "fork": False,
        "archived": False,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-06-01T00:00:00Z",
        "pushed_at": "2024-06-01T00:00:00Z",
        "default_branch": "main",
        "stargazers_count": 12,
        "forks_count": 2,
        "open_issues_count": 1,
        "size": 200,
        "html_url": "https://github.com/octocat/demo",
        "clone_url": "https://github.com/octocat/demo.git",
        "topics": ["cli"],
    }
    client = _FakeClient(
        _rich_tree(), {"README.md": "# Demo\n\nbody\n"}, repos=[repo_dict]
    )

    report = audit_user_api_only("octocat", client)

    assert isinstance(report, ApiOnlyReport)
    assert report.username == "octocat"
    assert report.mode == API_ONLY_MODE
    assert len(report.audits) == 1

    payload = report.to_dict()
    assert payload["mode"] == "api_only"
    assert payload["repo_count"] == 1
    assert payload["fidelity_note"]  # honest API-only caveat is present
    assert payload["repos"][0]["metadata"]["name"] == "demo"


def test_report_to_dict_is_json_serializable():
    client = _FakeClient(_rich_tree(), {"README.md": "# x\n\nbody\n"})
    audits = score_repos_api_only([_meta()], client)
    report = ApiOnlyReport(username="octocat", audits=audits)

    # Must serialize cleanly for the hosted (Next.js) consumer.
    encoded = json.dumps(report.to_dict())
    assert '"mode": "api_only"' in encoded


class _RecordingClient(_FakeClient):
    """Records calls to the slow async-stats endpoints."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.stats_calls: list[str] = []

    def get_contributor_stats(self, owner, repo):
        self.stats_calls.append("contributor")
        return []

    def get_commit_activity(self, owner, repo):
        self.stats_calls.append("commit_activity")
        return []

    def get_participation_stats(self, owner, repo):
        self.stats_calls.append("participation")
        return {}

    # Fast (non-202) endpoints the analyzers also touch — provided so they
    # delegate cleanly rather than fail-soft.
    def get_releases(self, owner, repo, per_page=10):
        return ([], True)

    def get_recent_commits(self, owner, repo, per_page=10):
        return []

    def get_pull_requests(self, owner, repo, state="all", per_page=30):
        return []

    def get_community_profile(self, owner, repo):
        return {"available": False}


def test_fast_mode_skips_async_stats_endpoints():
    client = _RecordingClient(_rich_tree(), {"README.md": "# x\n"})

    score_repos_api_only([_meta()], client, fast=True)

    assert client.stats_calls == []


def test_thorough_mode_uses_async_stats_endpoints():
    client = _RecordingClient(_rich_tree(), {"README.md": "# x\n"})

    score_repos_api_only([_meta()], client, fast=False)

    assert "contributor" in client.stats_calls
    assert "commit_activity" in client.stats_calls
