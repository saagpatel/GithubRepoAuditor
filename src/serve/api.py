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
from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BaseModel, Field

from src.api_only import audit_user_api_only
from src.github_client import GitHubClient, GitHubClientError
from src.serve.hosting import RateLimiter, ReportCache
from src.serve.runner import validate_username
from src.serve.waitlist import WaitlistStore, is_valid_email

router = APIRouter(prefix="/api", tags=["report"])

# Bound the interactive scan: a public free endpoint must not score an account
# with hundreds of repos in one request. Requests above this clamp down.
MAX_REPOS_CAP = 30

# Env var for the shared server-side GitHub App / PAT token. Absent in tests
# (the dependency is overridden) and acceptable locally (public, unauthenticated
# requests still work, just at a lower rate limit).
TOKEN_ENV_VAR = "GHRA_GITHUB_TOKEN"

# When set, trust X-Forwarded-For for the throttle key (a trusted proxy is in
# front). Default off — XFF is spoofable, so we key on the direct peer instead.
TRUST_FORWARDED_ENV_VAR = "GHRA_TRUST_FORWARDED_FOR"

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
    by concurrent worker threads. Connection-pool reuse via a shared server-side
    client is a future optimization; the report cache and per-IP throttle below
    already bound how often this client actually reaches GitHub.
    """
    return GitHubClient(token=os.environ.get(TOKEN_ENV_VAR))


def get_report_cache(request: Request) -> ReportCache:
    """Return the app-wide report cache (built once in the app factory)."""
    return request.app.state.report_cache


def get_rate_limiter(request: Request) -> RateLimiter:
    """Return the app-wide per-IP rate limiter (built once in the app factory)."""
    return request.app.state.rate_limiter


def _trust_forwarded_for() -> bool:
    return os.environ.get(TRUST_FORWARDED_ENV_VAR, "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def client_ip(request: Request) -> str:
    """Best-effort client IP used as the throttle key.

    X-Forwarded-For is client-spoofable, so honoring it blindly would let a
    caller pick a fresh throttle bucket per request. We only trust it when
    GHRA_TRUST_FORWARDED_FOR is set — i.e. a known proxy that overwrites the
    header sits in front. Otherwise we use the direct peer address. (When the
    ASGI transport supplies no client, all such requests share one bucket.)
    """
    if _trust_forwarded_for():
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def get_waitlist_store(request: Request) -> WaitlistStore:
    """Return the app-wide waitlist store (built once in the app factory)."""
    return request.app.state.waitlist_store


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
    request: Request,
    username: str = Path(..., description="GitHub username or org name"),
    client: GitHubClient = Depends(get_github_client),
    cache: ReportCache = Depends(get_report_cache),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> dict[str, Any]:
    """Score a user's portfolio clone-free and return the report as JSON.

    Always scans up to ``MAX_REPOS_CAP`` repos; there is no per-request repo
    knob, so a username fully determines the cached report.
    """
    # Throttle first — cheap, and it covers cache hits and garbage input alike.
    if not limiter.allow(client_ip(request)):
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded; try again later"
        )

    try:
        safe_username = validate_username(username)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    cached = cache.get(safe_username)
    if cached is not None:
        return cached

    try:
        result = audit_user_api_only(
            safe_username, client, max_repos=MAX_REPOS_CAP, fast=True
        )
    except requests.HTTPError as exc:
        raise _http_exception(exc, safe_username) from exc
    except (requests.RequestException, GitHubClientError) as exc:
        # Network failures (DNS, timeout, connection reset) and non-HTTP client
        # errors surface as a clean 502 rather than an unstructured 500.
        raise HTTPException(status_code=502, detail="Upstream GitHub error") from exc

    payload = result.to_dict()
    cache.put(safe_username, payload)
    return payload


class WaitlistSignup(BaseModel):
    """Body for the monitoring-waitlist capture."""

    email: str = Field(..., max_length=254)  # RFC 5321 max; matches is_valid_email
    # Optional context — e.g. the username whose report the visitor was viewing.
    source: str | None = Field(default=None, max_length=120)


@router.post("/waitlist", status_code=201)
def join_waitlist(
    request: Request,
    signup: WaitlistSignup,
    store: WaitlistStore = Depends(get_waitlist_store),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> dict[str, Any]:
    """Capture an email for the monitoring waitlist (idempotent on email)."""
    # Separate throttle bucket so browsing reports never exhausts signup budget.
    if not limiter.allow(client_ip(request), bucket="waitlist"):
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded; try again later"
        )
    if not is_valid_email(signup.email):
        raise HTTPException(status_code=422, detail="Enter a valid email address")

    created = store.add(signup.email, source=signup.source)
    # Idempotent: a repeat email is a success, not an error.
    return {"status": "joined" if created else "already_joined"}
