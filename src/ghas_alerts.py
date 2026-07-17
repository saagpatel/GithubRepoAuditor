"""GitHub Advanced Security (GHAS) alert fetcher.

Surfaces open alert counts from three GitHub endpoints per repo:
  - Dependabot alerts   (severities: critical / high / medium / low)
  - Code-scanning alerts (bucketed: critical / high / warning / note)
  - Secret-scanning alerts (count of open alerts only)

Code-scanning severity bucketing:
  API security_severity_level is preferred when present because some tools,
  including Scorecard, report rule.severity="error" for medium/low findings.
  API value  → output bucket
  critical   → critical
  high       → high
  error      → high       (fallback for tools without security severity)
  medium     → warning
  low        → warning
  warning    → warning
  note       → note
"""
from __future__ import annotations

import json
import logging
import os
import sys
from collections import defaultdict

import requests

from src.cache import ResponseCache
from src.http_link_header import next_link_from_header

logger = logging.getLogger(__name__)

# Allow override via env var for testing / proxies (mirrors S1.2 pattern)
GITHUB_API_BASE_URL = os.environ.get("GITHUB_API_BASE_URL", "https://api.github.com")

# Sentinel params used to namespace GHAS cache entries separately from GitHub API
_GHAS_CACHE_PARAMS = {"__source": "ghas-alerts"}

# 403 / 404 / 410 → GHAS not enabled for this repo (expected, not an error)
_EXPECTED_UNAVAILABLE_STATUSES = {403, 404, 410}

# Cache TTL for GHAS data: 6 hours (these endpoints change relatively slowly)
GHAS_CACHE_TTL = 6 * 3600

# Code-scanning severity → output bucket mapping
_CODE_SCANNING_BUCKET: dict[str, str] = {
    "critical": "critical",
    "high": "high",
    "error": "high",
    "medium": "warning",
    "low": "warning",
    "warning": "warning",
    "note": "note",
}


def _paginate(
    session: requests.Session,
    url: str,
    params: dict | None = None,
) -> list[dict]:
    """Follow Link-header pagination, collecting all results.

    Respects Retry-After on 429 via the session's HTTPAdapter Retry config.
    Fails soft: on non-2xx (after retries) raises HTTPError to the caller.
    """
    results: list[dict] = []
    next_url: str | None = url
    current_params = dict(params or {})

    while next_url:
        resp = session.get(next_url, params=current_params, timeout=30)
        resp.raise_for_status()
        page = resp.json()
        if isinstance(page, list):
            results.extend(page)

        # After first page, params are baked into the next URL from Link header
        current_params = {}

        # Parse Link header for rel="next"
        next_url = None
        next_link = resp.links.get("next", {}).get("url")
        if next_link:
            next_url = next_link
        else:
            link_header = resp.headers.get("Link", "")
            next_url = next_link_from_header(link_header)

    return results


def _make_session(token: str | None, session: requests.Session | None) -> requests.Session:
    """Return a configured requests.Session with GitHub auth and retry."""
    if session is not None:
        return session

    from requests.adapters import HTTPAdapter
    from urllib3.util import Retry

    s = requests.Session()
    s.headers.update({
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "github-repo-auditor/0.1",
        "X-GitHub-Api-Version": "2026-03-10",
    })
    if token:
        s.headers["Authorization"] = f"token {token}"

    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        other=0,
        allowed_methods=frozenset({"GET", "HEAD", "OPTIONS"}),
        status_forcelist={429, 500, 502, 503, 504},
        backoff_factor=1,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


def _fetch_dependabot_counts(
    session: requests.Session,
    owner: str,
    repo: str,
) -> dict:
    """Fetch open Dependabot alert counts grouped by severity."""
    base: dict = {"critical": 0, "high": 0, "medium": 0, "low": 0, "available": False}
    url = f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}/dependabot/alerts"
    try:
        alerts = _paginate(session, url, {"state": "open", "per_page": "100"})
        for alert in alerts:
            severity = (
                alert.get("security_advisory", {}).get("severity", "")
                or alert.get("security_vulnerability", {}).get("severity", "")
                or ""
            ).lower()
            if severity in base:
                base[severity] += 1
        base["available"] = True
        return base
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status in _EXPECTED_UNAVAILABLE_STATUSES:
            logger.debug(
                "Dependabot alerts unavailable for %s/%s (HTTP %s)", owner, repo, status
            )
        else:
            logger.warning(
                "Failed to fetch Dependabot alerts for %s/%s: %s", owner, repo, exc
            )
        return base
    except Exception as exc:
        logger.warning("Unexpected error fetching Dependabot alerts for %s/%s: %s", owner, repo, exc)
        return base


def _fetch_code_scanning_counts(
    session: requests.Session,
    owner: str,
    repo: str,
) -> dict:
    """Fetch open code-scanning alert counts bucketed into critical/high/warning/note.

    API security_severity_level is preferred over rule severity when present.
    """
    base: dict = {"critical": 0, "high": 0, "warning": 0, "note": 0, "available": False}
    url = f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}/code-scanning/alerts"
    try:
        alerts = _paginate(session, url, {"state": "open", "per_page": "100"})
        for alert in alerts:
            rule = alert.get("rule", {}) if isinstance(alert, dict) else {}
            raw_severity = (
                rule.get("security_severity_level")
                or rule.get("severity")
                or ""
            ).lower()
            bucket = _CODE_SCANNING_BUCKET.get(raw_severity)
            if bucket and bucket in base:
                base[bucket] += 1
        base["available"] = True
        return base
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status in _EXPECTED_UNAVAILABLE_STATUSES:
            logger.debug(
                "Code scanning alerts unavailable for %s/%s (HTTP %s)", owner, repo, status
            )
        else:
            logger.warning(
                "Failed to fetch code scanning alerts for %s/%s: %s", owner, repo, exc
            )
        return base
    except Exception as exc:
        logger.warning(
            "Unexpected error fetching code scanning alerts for %s/%s: %s", owner, repo, exc
        )
        return base


def _fetch_secret_scanning_counts(
    session: requests.Session,
    owner: str,
    repo: str,
) -> dict:
    """Fetch open secret-scanning alert count."""
    base: dict = {"open": 0, "available": False}
    url = f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}/secret-scanning/alerts"
    try:
        alerts = _paginate(session, url, {"state": "open", "per_page": "100"})
        base["open"] = len(alerts)
        base["available"] = True
        return base
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status in _EXPECTED_UNAVAILABLE_STATUSES:
            logger.debug(
                "Secret scanning alerts unavailable for %s/%s (HTTP %s)", owner, repo, status
            )
        else:
            logger.warning(
                "Failed to fetch secret scanning alerts for %s/%s: %s", owner, repo, exc
            )
        return base
    except Exception as exc:
        logger.warning(
            "Unexpected error fetching secret scanning alerts for %s/%s: %s", owner, repo, exc
        )
        return base


def fetch_ghas_alerts(
    audits: list[dict],
    *,
    token: str | None = None,
    cache: ResponseCache | None = None,
    session: requests.Session | None = None,
) -> dict[str, dict]:
    """Fetch open Dependabot/CodeQL/Secret-scanning alert counts for each repo.

    Returns {repo_name: {
        "dependabot": {"critical": N, "high": N, "medium": N, "low": N, "available": bool},
        "code_scanning": {"critical": N, "high": N, "warning": N, "note": N, "available": bool},
        "secret_scanning": {"open": N, "available": bool},
    }}

    Repos with no GitHub token are skipped (all categories get available=False).
    403/404/410 responses indicate GHAS is not enabled for that repo — recorded
    as available=False with zero counts, not raised as errors.
    """
    if not token:
        print("GHAS alerts skipped: no GitHub token available", file=sys.stderr)
        return {}

    s = _make_session(token, session)
    results: dict[str, dict] = {}

    for audit in audits:
        metadata = audit.get("metadata", {})
        repo_name = metadata.get("name", "")
        full_name = metadata.get("full_name", "")

        if not repo_name or not full_name or "/" not in full_name:
            continue

        owner, repo = full_name.split("/", 1)

        # Cache key: stable per repo-name + date (GHAS data changes slowly)
        cache_key = f"ghas-alerts-{full_name}"

        if cache:
            cached = cache.get(cache_key, _GHAS_CACHE_PARAMS)
            if cached is not None:
                results[repo_name] = json.loads(cached)  # type: ignore[arg-type]
                continue

        repo_result: dict = {
            "dependabot": _fetch_dependabot_counts(s, owner, repo),
            "code_scanning": _fetch_code_scanning_counts(s, owner, repo),
            "secret_scanning": _fetch_secret_scanning_counts(s, owner, repo),
        }

        if cache:
            cache.put(cache_key, _GHAS_CACHE_PARAMS, json.dumps(repo_result, default=str))

        results[repo_name] = repo_result

    return results


def format_ghas_summary(alerts: dict[str, dict]) -> str:
    """Format GHAS alert results for terminal output (4-6 lines max).

    Example:
        GHAS Alerts (open):
          Dependabot: 12 critical, 47 high across 23 repos
          Code Scanning: 3 critical, 8 high across 7 repos
          Secret Scanning: 2 open across 2 repos
          Top exposed repos: foo (8 critical), bar (5 critical), baz (3 critical)
    """
    if not alerts:
        return "No GHAS alerts."

    dep_totals: dict[str, int] = defaultdict(int)
    cs_totals: dict[str, int] = defaultdict(int)
    ss_open = 0

    dep_repos = 0
    cs_repos = 0
    ss_repos = 0

    # Accumulate per-repo critical counts for top-N ranking
    repo_critical: dict[str, int] = {}

    for repo_name, data in alerts.items():
        dep = data.get("dependabot", {})
        cs = data.get("code_scanning", {})
        ss = data.get("secret_scanning", {})

        if dep.get("available"):
            for k in ("critical", "high", "medium", "low"):
                dep_totals[k] += dep.get(k, 0)
            if any(dep.get(k, 0) > 0 for k in ("critical", "high", "medium", "low")):
                dep_repos += 1

        if cs.get("available"):
            for k in ("critical", "high", "warning", "note"):
                cs_totals[k] += cs.get(k, 0)
            if any(cs.get(k, 0) > 0 for k in ("critical", "high", "warning", "note")):
                cs_repos += 1

        if ss.get("available"):
            open_count = ss.get("open", 0)
            ss_open += open_count
            if open_count > 0:
                ss_repos += 1

        # Sum critical across all categories for top-N
        critical = dep.get("critical", 0) + cs.get("critical", 0)
        if critical > 0:
            repo_critical[repo_name] = critical

    lines = ["GHAS Alerts (open):"]

    if dep_totals:
        lines.append(
            f"  Dependabot: {dep_totals['critical']} critical, {dep_totals['high']} high"
            f" across {dep_repos} repos"
        )
    else:
        lines.append("  Dependabot: unavailable or no data")

    if cs_totals:
        lines.append(
            f"  Code Scanning: {cs_totals['critical']} critical, {cs_totals['high']} high"
            f" across {cs_repos} repos"
        )
    else:
        lines.append("  Code Scanning: unavailable or no data")

    lines.append(f"  Secret Scanning: {ss_open} open across {ss_repos} repos")

    if repo_critical:
        top = sorted(repo_critical.items(), key=lambda x: -x[1])[:3]
        top_str = ", ".join(f"{name} ({count} critical)" for name, count in top)
        lines.append(f"  Top exposed repos: {top_str}")

    return "\n".join(lines)
