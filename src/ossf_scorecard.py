"""OSSF Scorecard integration — fetches pre-computed scores for public repos.

Endpoint: GET https://api.securityscorecards.dev/projects/github.com/{owner}/{repo}
No auth required; 404 means the repo has never been scanned.
Cache TTL: 24h (scorecards re-run weekly so 24h is a safe freshness bound).
"""

from __future__ import annotations

import logging
import os

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from src.cache import ResponseCache

logger = logging.getLogger(__name__)

# Allow override via env var for testing / proxies
OSSF_SCORECARD_BASE_URL = os.environ.get(
    "OSSF_SCORECARD_BASE_URL",
    "https://api.securityscorecards.dev",
)

# Sentinel param to namespace cache entries for this source
_OSSF_CACHE_PARAMS: dict[str, str] = {"__source": "ossf-scorecard"}

# 24h TTL — scorecards re-run weekly; daily cache is safe
OSSF_CACHE_TTL = 24 * 3600

# 404 means no scorecard data; not an error worth logging at WARNING level
_EXPECTED_MISSING_STATUSES = {404}


def _make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/json",
            "User-Agent": "github-repo-auditor/0.1",
        }
    )
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        other=0,
        allowed_methods=frozenset({"GET", "HEAD"}),
        status_forcelist={429, 500, 502, 503, 504},
        backoff_factor=1,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _fetch_one(
    full_name: str,
    *,
    session: requests.Session,
    cache: ResponseCache | None,
) -> dict:
    """Fetch OSSF Scorecard data for a single repo.

    Returns:
        {"score": float, "checks": [...], "date": str, "available": True}
        or {"available": False} when no data exists (404)
        or {"available": False, "error": str} on transient failure.
    """
    owner, _, repo = full_name.partition("/")
    if not owner or not repo:
        logger.warning("OSSF Scorecard: invalid full_name %r — skipping", full_name)
        return {"available": False, "error": "invalid_full_name"}

    url = f"{OSSF_SCORECARD_BASE_URL}/projects/github.com/{owner}/{repo}"

    # Check cache first (keyed by url + sentinel params for namespace isolation)
    if cache is not None:
        cached = cache.get(url, _OSSF_CACHE_PARAMS)
        if cached is not None:
            return cached  # type: ignore[return-value]

    try:
        resp = session.get(url, timeout=30)
    except requests.RequestException as exc:
        logger.warning("OSSF Scorecard: network error for %s: %s", full_name, exc)
        return {"available": False, "error": str(exc)}

    if resp.status_code in _EXPECTED_MISSING_STATUSES:
        logger.debug("OSSF Scorecard: no data for %s (404)", full_name)
        result: dict = {"available": False}
        if cache is not None:
            cache.put(url, _OSSF_CACHE_PARAMS, result)
        return result

    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        logger.warning("OSSF Scorecard: HTTP error for %s: %s", full_name, exc)
        return {"available": False, "error": str(exc)}

    try:
        data = resp.json()
    except ValueError as exc:
        logger.warning("OSSF Scorecard: invalid JSON for %s: %s", full_name, exc)
        return {"available": False, "error": f"json_parse_error: {exc}"}

    if not isinstance(data, dict):
        logger.warning("OSSF Scorecard: unexpected response shape for %s", full_name)
        return {"available": False, "error": "unexpected_shape"}

    result = {
        "available": True,
        "score": data.get("score"),
        "checks": data.get("checks", []),
        "date": data.get("date", ""),
        "repo": data.get("repo", {}),
    }
    if cache is not None:
        _cache_with_ttl(cache, url, _OSSF_CACHE_PARAMS, result)
    return result


def _cache_with_ttl(
    cache: ResponseCache,
    url: str,
    params: dict,
    data: dict,
) -> None:
    """Write to cache, temporarily overriding TTL if needed.

    ResponseCache uses a single TTL per instance.  For OSSF data we want 24h.
    We swap the TTL, write, then restore — this is safe because caching is not
    threaded here.
    """
    original_ttl = cache.ttl
    cache.ttl = OSSF_CACHE_TTL
    try:
        cache.put(url, params, data)
    finally:
        cache.ttl = original_ttl


def fetch_ossf_scorecards(
    audits: list[dict],
    *,
    cache: ResponseCache | None = None,
    session: requests.Session | None = None,
) -> dict[str, dict]:
    """Fetch pre-computed OSSF Scorecard data for public repos.

    Args:
        audits: List of audit JSON entries (each must have a ``full_name`` key
                under ``metadata``, e.g. ``{"metadata": {"full_name": "owner/repo"}}``)
        cache:  Optional ResponseCache; when provided, results are cached for 24h.
        session: Optional requests.Session; a default one is created if not supplied.

    Returns:
        Mapping of ``full_name → scorecard_data`` where each value is either:
          ``{"available": True, "score": float, "checks": [...], "date": str}``
          ``{"available": False}``  — no scorecard data (private or never scanned)
          ``{"available": False, "error": str}``  — transient fetch failure
    """
    if session is None:
        session = _make_session()

    results: dict[str, dict] = {}
    for audit in audits:
        metadata = audit.get("metadata") or {}
        full_name: str = metadata.get("full_name", "")
        if not full_name:
            continue
        results[full_name] = _fetch_one(full_name, session=session, cache=cache)

    return results


def format_ossf_summary(scorecard_results: dict[str, dict]) -> str:
    """Return a one-line terminal summary for OSSF Scorecard results."""
    total = len(scorecard_results)
    scored = [
        v["score"]
        for v in scorecard_results.values()
        if v.get("available") and v.get("score") is not None
    ]
    if not scored:
        return f"OSSF Scorecard: 0/{total} repos scored (no public data found)"
    avg = sum(scored) / len(scored)
    return f"OSSF Scorecard: {len(scored)}/{total} repos scored, avg score {avg:.1f}"
