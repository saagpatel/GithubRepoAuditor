"""Hosted clone-free report endpoint — the HTTP surface over ``audit_user_api_only``.

Exposes ``GET /api/report/{username}`` returning :meth:`ApiOnlyReport.to_dict`
JSON. This is the free "paste your GitHub username" report's backend: it lists a
user's repos and scores them from the GitHub API alone (no cloning), via the
existing engine in :mod:`src.api_only`.

The route is defined as a plain ``def`` so FastAPI runs the blocking,
network-bound scan in a worker thread rather than on the event loop. The
:class:`~src.github_client.GitHubClient` is supplied through a FastAPI
dependency so tests can override it and a deployment can inject a shared
server-side token.
"""

from __future__ import annotations

import os
from typing import Any

import requests
from fastapi import APIRouter, Depends, HTTPException, Path, Query

from src.api_only import audit_user_api_only
from src.github_client import GitHubClient, GitHubClientError
from src.serve.runner import validate_username

router = APIRouter(prefix="/api", tags=["report"])

# Bound the interactive scan: a public free endpoint must not score an account
# with hundreds of repos in one request. Requests above this clamp down.
MAX_REPOS_CAP = 30

# Env var for the shared server-side GitHub App / PAT token. Absent in tests
# (the dependency is overridden) and acceptable locally (public, unauthenticated
# requests still work, just at a lower rate limit).
TOKEN_ENV_VAR = "GHRA_GITHUB_TOKEN"

# Comma-separated allowed CORS origins for the browser frontend. Defaults to the
# local Next.js dev server; set to the deployed origin (or "*") in production.
CORS_ORIGINS_ENV_VAR = "GHRA_CORS_ORIGINS"
DEFAULT_CORS_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")


def cors_origins() -> list[str]:
    """Resolve allowed CORS origins from env, falling back to the dev server."""
    raw = os.environ.get(CORS_ORIGINS_ENV_VAR, "").strip()
    if not raw:
        return list(DEFAULT_CORS_ORIGINS)
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def get_github_client() -> GitHubClient:
    """Provide a GitHubClient for the request (overridable in tests/deploys).

    A fresh client (and ``requests.Session``) is built per request on purpose:
    the route runs in FastAPI's threadpool, so a shared Session would be touched
    by concurrent worker threads. Connection-pool reuse and a shared server-side
    client land in Phase 2 step 3 alongside the per-IP throttle that bounds load.
    """
    return GitHubClient(token=os.environ.get(TOKEN_ENV_VAR))


def _is_rate_limited(status: int | None, response: requests.Response | None) -> bool:
    """True when a GitHub error is rate-limiting (429, or 403 with quota at 0)."""
    if status == 429:
        return True
    if status == 403 and response is not None:
        return response.headers.get("X-RateLimit-Remaining") == "0"
    return False


def _http_exception(exc: requests.HTTPError, username: str) -> HTTPException:
    """Map a GitHub HTTP error onto the endpoint's client-facing status."""
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if status == 404:
        return HTTPException(
            status_code=404, detail=f"GitHub user '{username}' not found"
        )
    if _is_rate_limited(status, response):
        return HTTPException(
            status_code=429, detail="GitHub rate limit reached; try again later"
        )
    if status == 403:
        return HTTPException(
            status_code=403, detail="GitHub denied access to this resource"
        )
    return HTTPException(status_code=502, detail="Upstream GitHub error")


@router.get("/report/{username}")
def report(
    username: str = Path(..., description="GitHub username or org name"),
    max_repos: int | None = Query(
        None, ge=1, description="Cap repos scored (clamped to the server limit)"
    ),
    client: GitHubClient = Depends(get_github_client),
) -> dict[str, Any]:
    """Score a user's portfolio clone-free and return the report as JSON."""
    try:
        safe_username = validate_username(username)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    capped = MAX_REPOS_CAP if max_repos is None else min(max_repos, MAX_REPOS_CAP)

    try:
        result = audit_user_api_only(safe_username, client, max_repos=capped, fast=True)
    except requests.HTTPError as exc:
        raise _http_exception(exc, safe_username) from exc
    except (requests.RequestException, GitHubClientError) as exc:
        # Network failures (DNS, timeout, connection reset) and non-HTTP client
        # errors surface as a clean 502 rather than an unstructured 500.
        raise HTTPException(status_code=502, detail="Upstream GitHub error") from exc

    return result.to_dict()
