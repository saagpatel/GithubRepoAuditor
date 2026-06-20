"""Tests for src/serve/api.py — hosted clone-free report JSON endpoint (Phase 2 S1)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Dependency guard — skip entire module if [serve] extra not installed
# ---------------------------------------------------------------------------
pytest.importorskip("fastapi", reason="[serve] extra not installed")

import requests  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from src.api_only import ApiOnlyReport  # noqa: E402
from src.serve.api import get_github_client  # noqa: E402
from src.serve.app import create_app  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def client(tmp_path) -> TestClient:
    """TestClient with the GitHub client dependency stubbed to a sentinel.

    The endpoint's network work is exercised through a patched
    ``audit_user_api_only`` in each test, so the dependency only needs to avoid
    constructing a real client (which would read env / open a session).
    """
    app = create_app(output_dir=tmp_path)
    app.dependency_overrides[get_github_client] = lambda: object()
    return TestClient(app)


def _http_error(
    status: int, headers: dict[str, str] | None = None
) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status
    if headers:
        response.headers.update(headers)
    return requests.HTTPError(f"{status} error", response=response)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------
def test_report_returns_serialized_report(client: TestClient) -> None:
    report = ApiOnlyReport(username="octocat", audits=[])
    with patch("src.serve.api.audit_user_api_only", return_value=report) as mock_audit:
        resp = client.get("/api/report/octocat")

        assert resp.status_code == 200
        body = resp.json()
        # Fast mode is the interactive default for the hosted endpoint.
        assert mock_audit.call_args.kwargs["fast"] is True
    assert body["username"] == "octocat"
    assert body["mode"] == "api_only"
    assert body["repo_count"] == 0
    assert body["repos"] == []
    assert "fidelity_note" in body


def test_report_passes_validated_username(client: TestClient) -> None:
    report = ApiOnlyReport(username="octocat", audits=[])
    with patch("src.serve.api.audit_user_api_only", return_value=report) as mock_audit:
        resp = client.get("/api/report/octocat")

    assert resp.status_code == 200
    # username is the first positional arg to audit_user_api_only
    assert mock_audit.call_args.args[0] == "octocat"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad", ["bad--name", "has space", "-leading", "a" * 40])
def test_invalid_username_returns_422(client: TestClient, bad: str) -> None:
    with patch("src.serve.api.audit_user_api_only") as mock_audit:
        resp = client.get(f"/api/report/{bad}")
    assert resp.status_code == 422
    mock_audit.assert_not_called()


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------
def test_unknown_user_returns_404(client: TestClient) -> None:
    with patch("src.serve.api.audit_user_api_only", side_effect=_http_error(404)):
        resp = client.get("/api/report/ghost")
    assert resp.status_code == 404


def test_rate_limited_403_with_zero_quota_returns_429(client: TestClient) -> None:
    err = _http_error(403, headers={"X-RateLimit-Remaining": "0"})
    with patch("src.serve.api.audit_user_api_only", side_effect=err):
        resp = client.get("/api/report/octocat")
    assert resp.status_code == 429


def test_rate_limited_429_returns_429(client: TestClient) -> None:
    with patch("src.serve.api.audit_user_api_only", side_effect=_http_error(429)):
        resp = client.get("/api/report/octocat")
    assert resp.status_code == 429


def test_forbidden_403_without_quota_header_returns_403(client: TestClient) -> None:
    # A 403 that is NOT rate-limiting (e.g. private resource) stays a 403, not 429.
    with patch("src.serve.api.audit_user_api_only", side_effect=_http_error(403)):
        resp = client.get("/api/report/octocat")
    assert resp.status_code == 403


def test_upstream_error_returns_502(client: TestClient) -> None:
    with patch("src.serve.api.audit_user_api_only", side_effect=_http_error(500)):
        resp = client.get("/api/report/octocat")
    assert resp.status_code == 502


def test_network_error_returns_502(client: TestClient) -> None:
    err = requests.ConnectionError("connection reset")
    with patch("src.serve.api.audit_user_api_only", side_effect=err):
        resp = client.get("/api/report/octocat")
    assert resp.status_code == 502


def test_github_client_error_returns_502(client: TestClient) -> None:
    from src.github_client import GitHubClientError

    with patch(
        "src.serve.api.audit_user_api_only",
        side_effect=GitHubClientError("graphql failed"),
    ):
        resp = client.get("/api/report/octocat")
    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# Cost bound
# ---------------------------------------------------------------------------
def test_max_repos_clamped_to_cap(client: TestClient) -> None:
    from src.serve.api import MAX_REPOS_CAP

    report = ApiOnlyReport(username="octocat", audits=[])
    with patch("src.serve.api.audit_user_api_only", return_value=report) as mock_audit:
        resp = client.get("/api/report/octocat?max_repos=9999")

    assert resp.status_code == 200
    assert mock_audit.call_args.kwargs["max_repos"] == MAX_REPOS_CAP
