"""Tests for src/serve/api.py — hosted clone-free report JSON endpoint (Phase 2 S1)."""

from __future__ import annotations

from types import SimpleNamespace
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
def _sentinel_github_client() -> object:
    return object()


def _make_client(tmp_path) -> TestClient:
    """Build a TestClient with the GitHub client dependency stubbed to a sentinel.

    The endpoint's network work is exercised through a patched
    ``audit_user_api_only`` in each test, so the dependency only needs to avoid
    constructing a real client (which would read env / open a session).
    """
    app = create_app(output_dir=tmp_path)
    app.dependency_overrides[get_github_client] = _sentinel_github_client
    return TestClient(app)


@pytest.fixture()
def client(tmp_path) -> TestClient:
    return _make_client(tmp_path)


def _http_error(
    status: int, headers: dict[str, str] | None = None
) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status
    if headers:
        response.headers.update(headers)
    return requests.HTTPError(f"{status} error", response=response)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
def test_health_ok(client: TestClient) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "github_token" in body


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
def test_scan_is_capped_at_max_repos(client: TestClient) -> None:
    from src.serve.api import MAX_REPOS_CAP

    report = ApiOnlyReport(username="octocat", audits=[])
    with patch("src.serve.api.audit_user_api_only", return_value=report) as mock_audit:
        # No per-request repo knob — a stray query param is ignored and the
        # server always bounds the scan at MAX_REPOS_CAP.
        resp = client.get("/api/report/octocat?max_repos=9999")

    assert resp.status_code == 200
    assert mock_audit.call_args.kwargs["max_repos"] == MAX_REPOS_CAP


# ---------------------------------------------------------------------------
# CORS (browser frontend reachability)
# ---------------------------------------------------------------------------
def test_cors_allows_frontend_origin(client: TestClient) -> None:
    report = ApiOnlyReport(username="octocat", audits=[])
    origin = "http://localhost:3000"
    with patch("src.serve.api.audit_user_api_only", return_value=report):
        resp = client.get("/api/report/octocat", headers={"Origin": origin})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == origin


def test_cors_preflight_allows_waitlist_post(client: TestClient) -> None:
    resp = client.options(
        "/api/waitlist",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code == 200
    assert "POST" in resp.headers.get("access-control-allow-methods", "")


def test_cors_origins_reads_env(monkeypatch) -> None:
    from src.serve.api import cors_origins

    monkeypatch.setenv("GHRA_CORS_ORIGINS", "https://a.example, https://b.example")
    assert cors_origins() == ["https://a.example", "https://b.example"]
    monkeypatch.delenv("GHRA_CORS_ORIGINS", raising=False)
    assert cors_origins() == ["http://localhost:3000", "http://127.0.0.1:3000"]


# ---------------------------------------------------------------------------
# Caching + throttle (hosting guards)
# ---------------------------------------------------------------------------
def test_cache_hit_skips_second_scan(client: TestClient) -> None:
    report = ApiOnlyReport(username="octocat", audits=[])
    with patch("src.serve.api.audit_user_api_only", return_value=report) as mock_audit:
        first = client.get("/api/report/octocat")
        second = client.get("/api/report/octocat")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    # The second identical request is served from cache — no re-scan.
    assert mock_audit.call_count == 1


def test_rate_limit_returns_429_past_limit(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GHRA_RATE_LIMIT", "2")
    monkeypatch.setenv("GHRA_RATE_WINDOW_SECONDS", "3600")
    local_client = _make_client(tmp_path)

    report = ApiOnlyReport(username="octocat", audits=[])
    with patch("src.serve.api.audit_user_api_only", return_value=report) as mock_audit:
        codes = [local_client.get("/api/report/octocat").status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    # The 2nd request was a cache hit but still consumed throttle budget, so the
    # scan ran exactly once across the two allowed requests.
    assert mock_audit.call_count == 1


class _FakeRequest:
    """Minimal Request stand-in for client_ip unit tests."""

    def __init__(self, headers: dict[str, str], host: str | None) -> None:
        self.headers = headers
        self.client = SimpleNamespace(host=host) if host is not None else None


def test_client_ip_ignores_forwarded_by_default(monkeypatch) -> None:
    from src.serve.api import client_ip

    monkeypatch.delenv("GHRA_TRUST_FORWARDED_FOR", raising=False)
    req = _FakeRequest({"x-forwarded-for": "9.9.9.9"}, host="1.2.3.4")
    # Spoofable XFF is ignored — keyed on the direct peer.
    assert client_ip(req) == "1.2.3.4"  # type: ignore[arg-type]


def test_client_ip_honors_forwarded_when_trusted(monkeypatch) -> None:
    from src.serve.api import client_ip

    monkeypatch.setenv("GHRA_TRUST_FORWARDED_FOR", "true")
    req = _FakeRequest({"x-forwarded-for": "9.9.9.9, 1.2.3.4"}, host="1.2.3.4")
    assert client_ip(req) == "9.9.9.9"  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Waitlist capture
# ---------------------------------------------------------------------------
def test_waitlist_accepts_valid_email(client: TestClient) -> None:
    resp = client.post(
        "/api/waitlist", json={"email": "dev@example.com", "source": "octocat"}
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "joined"


def test_waitlist_is_idempotent(client: TestClient) -> None:
    client.post("/api/waitlist", json={"email": "dev@example.com"})
    resp = client.post("/api/waitlist", json={"email": "dev@example.com"})
    assert resp.status_code == 201
    assert resp.json()["status"] == "already_joined"


def test_waitlist_dedupes_case_insensitively_through_endpoint(
    client: TestClient,
) -> None:
    first = client.post("/api/waitlist", json={"email": "Dev@Example.com"})
    second = client.post("/api/waitlist", json={"email": "dev@example.com"})
    assert first.json()["status"] == "joined"
    assert second.json()["status"] == "already_joined"


def test_waitlist_rejects_invalid_email(client: TestClient) -> None:
    resp = client.post("/api/waitlist", json={"email": "not-an-email"})
    assert resp.status_code == 422


def test_waitlist_requires_email_field(client: TestClient) -> None:
    resp = client.post("/api/waitlist", json={"source": "octocat"})
    assert resp.status_code == 422  # pydantic: missing required field


def test_waitlist_throttled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GHRA_RATE_LIMIT", "1")
    monkeypatch.setenv("GHRA_RATE_WINDOW_SECONDS", "3600")
    local_client = _make_client(tmp_path)
    first = local_client.post("/api/waitlist", json={"email": "a@b.co"})
    second = local_client.post("/api/waitlist", json={"email": "c@d.co"})
    assert first.status_code == 201
    assert second.status_code == 429
