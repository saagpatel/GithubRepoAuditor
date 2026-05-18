"""Tests for GitHub SBOM-based dependency fetching.

Covers:
  - get_dependency_sbom: happy path, 403 fallback, network error
  - DependenciesAnalyzer.analyze with sbom_source="github"
  - DependenciesAnalyzer.analyze with sbom_source="lockfile" (default, unchanged)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from src.analyzers.dependencies import DependenciesAnalyzer
from src.github_client import GitHubClient
from src.models import RepoMetadata

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sbom_metadata() -> RepoMetadata:
    from datetime import datetime, timezone

    return RepoMetadata(
        name="myrepo",
        full_name="owner/myrepo",
        description="A test repo",
        language="Python",
        languages={"Python": 3000},
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
        size_kb=512,
        html_url="https://github.com/owner/myrepo",
        clone_url="https://github.com/owner/myrepo.git",
    )


def _spdx_payload(packages: list[dict] | None = None) -> dict:
    """Build a minimal SPDX SBOM payload."""
    if packages is None:
        packages = [
            {
                "name": "requests",
                "versionInfo": "2.31.0",
                "externalRefs": [
                    {
                        "referenceType": "purl",
                        "referenceLocator": "pkg:pypi/requests@2.31.0",
                    }
                ],
            },
            {
                "name": "urllib3",
                "versionInfo": "2.0.7",
                "externalRefs": [
                    {
                        "referenceType": "purl",
                        "referenceLocator": "pkg:pypi/urllib3@2.0.7",
                    }
                ],
            },
        ]
    return {
        "sbom": {
            "spdxVersion": "SPDX-2.3",
            "packages": packages,
        }
    }


def _make_mock_client(sbom_result: dict) -> MagicMock:
    """Build a GitHubClient mock whose get_dependency_sbom returns sbom_result."""
    client = MagicMock(spec=GitHubClient)
    client.get_dependency_sbom.return_value = sbom_result
    return client


# ---------------------------------------------------------------------------
# get_dependency_sbom unit tests
# ---------------------------------------------------------------------------


class TestGetDependencySbom:
    def test_happy_path_parses_packages(self):
        """SPDX payload is parsed into packages list with name/version/purl."""
        client = GitHubClient.__new__(GitHubClient)
        client.cache = None

        with patch.object(client, "_fetch_json", return_value=_spdx_payload()):
            result = client.get_dependency_sbom("owner", "myrepo")

        assert result["available"] is True
        assert result["package_count"] == 2
        pkgs = result["packages"]
        assert pkgs[0]["name"] == "requests"
        assert pkgs[0]["version"] == "2.31.0"
        assert pkgs[0]["purl"] == "pkg:pypi/requests@2.31.0"
        assert result["spdx_version"] == "SPDX-2.3"

    def test_403_returns_unavailable_with_reason(self):
        """HTTP 403 (dependency graph disabled) returns available=False, no exception."""
        client = GitHubClient.__new__(GitHubClient)
        client.cache = None

        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 403
        http_err = requests.HTTPError(response=mock_resp)

        with patch.object(client, "_fetch_json", side_effect=http_err):
            result = client.get_dependency_sbom("owner", "myrepo")

        assert result["available"] is False
        assert result["http_status"] == 403

    def test_404_returns_unavailable(self):
        """HTTP 404 also treated as 'unavailable'."""
        client = GitHubClient.__new__(GitHubClient)
        client.cache = None

        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 404
        http_err = requests.HTTPError(response=mock_resp)

        with patch.object(client, "_fetch_json", side_effect=http_err):
            result = client.get_dependency_sbom("owner", "myrepo")

        assert result["available"] is False
        assert result["http_status"] == 404

    def test_network_error_returns_unavailable(self):
        """RequestException (non-HTTP) is caught and returned as unavailable."""
        client = GitHubClient.__new__(GitHubClient)
        client.cache = None

        with patch.object(client, "_fetch_json", side_effect=requests.ConnectionError("timeout")):
            result = client.get_dependency_sbom("owner", "myrepo")

        assert result["available"] is False
        assert result["http_status"] is None
        assert "timeout" in result["reason"]

    def test_empty_packages_list(self):
        """SBOM with zero packages is handled gracefully."""
        client = GitHubClient.__new__(GitHubClient)
        client.cache = None

        with patch.object(client, "_fetch_json", return_value=_spdx_payload(packages=[])):
            result = client.get_dependency_sbom("owner", "myrepo")

        assert result["available"] is True
        assert result["package_count"] == 0
        assert result["packages"] == []


# ---------------------------------------------------------------------------
# DependenciesAnalyzer integration tests
# ---------------------------------------------------------------------------


class TestDependenciesAnalyzerSbomSource:
    def test_sbom_source_github_uses_api(self, tmp_path, sbom_metadata):
        """When sbom_source='github', dep_count comes from SBOM API."""
        empty_repo = tmp_path / "repo"
        empty_repo.mkdir()

        client = _make_mock_client(
            {
                "available": True,
                "packages": [
                    {"name": "requests", "version": "2.31.0", "purl": "pkg:pypi/requests@2.31.0"},
                    {"name": "click", "version": "8.0.0", "purl": "pkg:pypi/click@8.0.0"},
                ],
                "package_count": 2,
                "spdx_version": "SPDX-2.3",
            }
        )

        result = DependenciesAnalyzer().analyze(
            empty_repo, sbom_metadata, github_client=client, sbom_source="github"
        )

        client.get_dependency_sbom.assert_called_once_with("owner", "myrepo")
        assert result.details["dep_count"] == 2
        assert result.details["sbom_source"] == "github"
        assert any("Dependency count: 2" in f for f in result.findings)

    def test_sbom_source_lockfile_default_unchanged(self, tmp_path, sbom_metadata):
        """Default sbom_source='lockfile' leaves existing behavior intact."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "package.json").write_text(
            '{"dependencies": {"lodash": "^4.0.0"}, "devDependencies": {}}'
        )

        client = _make_mock_client({"available": False})  # Should not be called

        result = DependenciesAnalyzer().analyze(
            repo, sbom_metadata, github_client=client, sbom_source="lockfile"
        )

        client.get_dependency_sbom.assert_not_called()
        assert result.details["sbom_source"] == "lockfile"
        assert result.details["dep_count"] == 1  # lodash

    def test_sbom_403_falls_back_to_lockfile(self, tmp_path, sbom_metadata):
        """When SBOM API returns available=False, analyzer falls back to lockfile parsing."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "requirements.txt").write_text("requests\nclick\nflask\n")

        client = _make_mock_client({"available": False, "http_status": 403, "reason": "forbidden"})

        result = DependenciesAnalyzer().analyze(
            repo, sbom_metadata, github_client=client, sbom_source="github"
        )

        # Fell back to lockfile: reads requirements.txt
        assert result.details["sbom_source"] == "lockfile"
        assert result.details["dep_count"] == 3

    def test_sbom_no_client_falls_back_to_lockfile(self, tmp_path, sbom_metadata):
        """sbom_source='github' with no client silently falls back to lockfile."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "requirements.txt").write_text("requests\n")

        result = DependenciesAnalyzer().analyze(
            repo, sbom_metadata, github_client=None, sbom_source="github"
        )

        assert result.details["sbom_source"] == "lockfile"
        assert result.details["dep_count"] == 1

    def test_sbom_exception_falls_back_gracefully(self, tmp_path, sbom_metadata):
        """Unexpected exceptions from the SBOM call fall back to lockfile, not crash."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "requirements.txt").write_text("requests\nclick\n")

        client = MagicMock(spec=GitHubClient)
        client.get_dependency_sbom.side_effect = RuntimeError("unexpected error")

        result = DependenciesAnalyzer().analyze(
            repo, sbom_metadata, github_client=client, sbom_source="github"
        )

        assert result.details["sbom_source"] == "lockfile"
        assert result.details["dep_count"] == 2
