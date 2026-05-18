"""Async parallel fetcher for per-repo REST enrichment calls.

Provides ``AsyncGitHubClient`` (httpx-based, semaphore-bounded) and a
sync-compatible bridge ``fetch_enrichment_sync`` for use in the CLI.

Design notes
------------
* A single ``asyncio.Semaphore`` bounds **global** concurrency across
  all repos × all endpoint-types.  With 100 repos × 6 endpoints and no
  bound you would easily exceed GitHub's secondary rate limit.
* Per-request retry logic honours ``Retry-After`` (429) and backs off
  exponentially on 5xx.  404/403 are treated as "not available" and
  return None without retry.
* Cache integration reuses the same URL+params key scheme as
  ``src.cache.ResponseCache`` (SHA-256 hex prefix, file-backed).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import httpx

from src.github_client import API_BASE, REST_API_VERSION, GitHubClientError

if TYPE_CHECKING:
    from src.cache import ResponseCache

logger = logging.getLogger(__name__)

# ── Retry budget constants ────────────────────────────────────────────────────
_MAX_429_RETRIES = 3
_MAX_5XX_RETRIES = 2
_MAX_NETWORK_RETRIES = 1
_DEFAULT_BACKOFF_BASE = 1.0  # seconds; multiplied by attempt number


# ── Enrichment endpoint registry ─────────────────────────────────────────────


def _enrichment_endpoints(owner: str, repo: str) -> dict[str, tuple[str, dict | None]]:
    """Return {result_key: (url, params)} for a single repo's enrichment calls."""
    base = f"{API_BASE}/repos/{owner}/{repo}"
    return {
        "community_profile": (f"{base}/community/profile", None),
        "languages": (f"{base}/languages", None),
        "releases": (f"{base}/releases", {"per_page": "10"}),
        "security_analysis": (base, None),
        "topics": (f"{base}/topics", None),
        "custom_properties": (f"{base}/properties/values", None),
    }


# ── Core async client ─────────────────────────────────────────────────────────


class AsyncGitHubClient:
    """Async parallel fetcher for per-repo REST enrichment calls.

    Wraps ``httpx.AsyncClient`` with a semaphore-bounded concurrency limit and
    exponential backoff on 429 / secondary rate-limit responses.

    Parameters
    ----------
    token:
        GitHub personal access token.  May be None for public repos.
    max_concurrency:
        Hard cap on simultaneous in-flight HTTP requests (across all repos).
    transport:
        Optional ``httpx.AsyncBaseTransport`` override — used in tests.
    """

    def __init__(
        self,
        token: str | None = None,
        *,
        max_concurrency: int = 10,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token = token
        self._semaphore = asyncio.Semaphore(max_concurrency)
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "github-repo-auditor/0.1",
            "X-GitHub-Api-Version": REST_API_VERSION,
        }
        if token:
            headers["Authorization"] = f"token {token}"
        self._client = httpx.AsyncClient(
            headers=headers,
            timeout=30.0,
            transport=transport,
        )

    async def __aenter__(self) -> "AsyncGitHubClient":
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._client.__aexit__(*args)

    # ── Low-level fetch with retry ────────────────────────────────────────

    async def _fetch(
        self,
        url: str,
        params: dict | None = None,
        *,
        cache: "ResponseCache | None" = None,
    ) -> object | None:
        """Fetch *url* with retry/backoff.

        Returns parsed JSON on success, ``None`` on 404/403.
        Raises ``GitHubClientError`` after exhausting retries on 5xx.
        """
        # Cache check
        if cache is not None:
            cached = cache.get(url, params)
            if cached is not None:
                return cached

        attempt_429 = 0
        attempt_5xx = 0
        attempt_network = 0

        while True:
            async with self._semaphore:
                try:
                    response = await self._client.get(url, params=params)
                except httpx.TransportError as exc:
                    if attempt_network < _MAX_NETWORK_RETRIES:
                        attempt_network += 1
                        wait = _DEFAULT_BACKOFF_BASE * attempt_network
                        logger.warning(
                            "Network error fetching %s (attempt %d): %s — retrying in %.1fs",
                            url,
                            attempt_network,
                            exc,
                            wait,
                        )
                        await asyncio.sleep(wait)
                        continue
                    logger.error(
                        "Network error fetching %s after %d retries: %s", url, attempt_network, exc
                    )
                    raise GitHubClientError(f"Network error for {url}: {exc}") from exc

            status = response.status_code

            if status in (404, 403):
                logger.debug("Endpoint unavailable (%d) for %s — returning None", status, url)
                return None

            if status == 429 or (
                status == 403 and response.headers.get("X-RateLimit-Remaining") == "0"
            ):
                if attempt_429 >= _MAX_429_RETRIES:
                    logger.error(
                        "Rate limit not recovering for %s after %d retries", url, attempt_429
                    )
                    raise GitHubClientError(f"Rate limit exhausted for {url}")
                retry_after = _retry_after_seconds(response)
                wait = retry_after if retry_after > 0 else _DEFAULT_BACKOFF_BASE * (attempt_429 + 1)
                attempt_429 += 1
                logger.warning(
                    "Rate-limited on %s (attempt %d/%d) — waiting %.2fs",
                    url,
                    attempt_429,
                    _MAX_429_RETRIES,
                    wait,
                )
                await asyncio.sleep(wait)
                continue

            if status >= 500:
                if attempt_5xx >= _MAX_5XX_RETRIES:
                    logger.error(
                        "Persistent 5xx (%d) for %s after %d retries", status, url, attempt_5xx
                    )
                    raise GitHubClientError(
                        f"Server error {status} for {url} after {attempt_5xx} retries"
                    )
                wait = _DEFAULT_BACKOFF_BASE * (attempt_5xx + 1)
                attempt_5xx += 1
                logger.warning(
                    "5xx error %d on %s (attempt %d/%d) — retrying in %.1fs",
                    status,
                    url,
                    attempt_5xx,
                    _MAX_5XX_RETRIES,
                    wait,
                )
                await asyncio.sleep(wait)
                continue

            response.raise_for_status()
            data = response.json()

            # Cache write
            if cache is not None:
                cache.put(url, params, data)

            return data

    # ── Per-repo fan-out ──────────────────────────────────────────────────

    async def get_repo_enrichment(
        self,
        owner: str,
        repo: str,
        *,
        cache: "ResponseCache | None" = None,
    ) -> dict:
        """Fan out N concurrent GETs for one repo's enrichment endpoints.

        Returns a dict with keys: community_profile, languages, releases,
        security_analysis, topics, custom_properties.  Each value is the
        endpoint payload or ``None`` on 404/403.
        """
        endpoints = _enrichment_endpoints(owner, repo)

        async def _fetch_key(key: str, url: str, params: dict | None) -> tuple[str, object]:
            try:
                result = await self._fetch(url, params, cache=cache)
            except GitHubClientError as exc:
                logger.warning("Enrichment fetch failed for %s/%s [%s]: %s", owner, repo, key, exc)
                result = None
            return key, result

        tasks = [
            asyncio.create_task(_fetch_key(key, url, params))
            for key, (url, params) in endpoints.items()
        ]
        pairs = await asyncio.gather(*tasks)
        return dict(pairs)

    # ── Portfolio-wide fan-out ────────────────────────────────────────────

    async def fetch_enrichment_for_all(
        self,
        repos: list[tuple[str, str]],
        *,
        cache: "ResponseCache | None" = None,
    ) -> dict[str, dict]:
        """Fan out enrichment across all repos under the concurrency limit.

        Parameters
        ----------
        repos:
            List of ``(owner, repo)`` tuples.

        Returns
        -------
        Mapping of ``"owner/repo"`` → enrichment dict.
        """

        async def _fetch_one(owner: str, repo: str) -> tuple[str, dict]:
            enrichment = await self.get_repo_enrichment(owner, repo, cache=cache)
            return f"{owner}/{repo}", enrichment

        tasks = [asyncio.create_task(_fetch_one(owner, repo)) for owner, repo in repos]
        pairs = await asyncio.gather(*tasks)
        return dict(pairs)


# ── Sync bridge ───────────────────────────────────────────────────────────────


async def _run_with_client(
    repos: list[tuple[str, str]],
    token: str | None,
    max_concurrency: int,
    cache: "ResponseCache | None",
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, dict]:
    async with AsyncGitHubClient(
        token=token,
        max_concurrency=max_concurrency,
        transport=transport,
    ) as client:
        return await client.fetch_enrichment_for_all(repos, cache=cache)


def fetch_enrichment_sync(
    repos: list[tuple[str, str]],
    *,
    token: str | None = None,
    max_concurrency: int = 10,
    cache: "ResponseCache | None" = None,
    _transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, dict]:
    """Sync wrapper around the async enrichment fetcher.

    Parameters
    ----------
    repos:
        List of ``(owner, repo)`` tuples.
    token:
        GitHub personal access token.
    max_concurrency:
        Max simultaneous in-flight HTTP requests.
    cache:
        Optional ``ResponseCache`` instance for read-through/write-through caching.
    _transport:
        Internal — async transport override for testing.

    Returns
    -------
    Mapping of ``"owner/repo"`` → enrichment dict.
    """
    return asyncio.run(_run_with_client(repos, token, max_concurrency, cache, _transport))


# ── Helpers ───────────────────────────────────────────────────────────────────


def _retry_after_seconds(response: httpx.Response) -> float:
    """Extract ``Retry-After`` header value in seconds, or 0.0 if absent."""
    raw = response.headers.get("Retry-After", "")
    if not raw:
        return 0.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.0
