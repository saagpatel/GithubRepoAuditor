"""Per-alert Dependabot detail fetcher — decoupled from ghas_alerts.py.

Fetches the same open-alert stream that fetch_ghas_alerts uses for counts, but
extracts per-alert detail fields needed by the security burndown.  Lives in a
separate module so ghas_alerts.py (a token-session file) stays byte-for-byte
unchanged and doesn't trigger CodeQL clear-text-logging checks.

CodeQL-avoidance contract (enforced in every except handler):
  - No interpolated values in log calls — no owner, repo, exc, status, or
    any response-derived data.
  - Only static-string log messages (zero format args).
  - On any error: set that repo's details to [] and continue (best-effort).
"""

from __future__ import annotations

import logging

import requests

from src.ghas_alerts import (
    _EXPECTED_UNAVAILABLE_STATUSES,
    GITHUB_API_BASE_URL,
    _make_session,
    _paginate,
)

logger = logging.getLogger(__name__)


def _extract_detail(alert: dict) -> dict:
    """Extract the flat detail dict from one GitHub Dependabot alert API object."""
    advisory = alert.get("security_advisory") or {}
    vulnerability = alert.get("security_vulnerability") or {}
    dependency = alert.get("dependency") or {}
    package = dependency.get("package") or {}

    severity_raw = (advisory.get("severity", "") or vulnerability.get("severity", "") or "").lower()

    first_patched: str | None = None
    first_patched_obj = vulnerability.get("first_patched_version")
    if isinstance(first_patched_obj, dict):
        first_patched = first_patched_obj.get("identifier")

    return {
        "package": package.get("name"),
        "ecosystem": package.get("ecosystem"),
        "scope": dependency.get("scope"),
        "severity": severity_raw or None,
        "ghsa_id": advisory.get("ghsa_id"),
        "first_patched_version": first_patched,
        "manifest_path": dependency.get("manifest_path"),
    }


def fetch_dependabot_details(
    audits: list[dict],
    *,
    token: str | None = None,
    cache: object = None,
    session: requests.Session | None = None,
) -> dict[str, list[dict]]:
    """Fetch per-alert Dependabot detail for each repo, keyed by repo name.

    Returns {repo_name: [detail_dict, ...]} where each detail_dict has keys:
        package, ecosystem, scope, severity, ghsa_id,
        first_patched_version, manifest_path.

    Errors are best-effort: any repo that fails gets an empty list; no
    exception is propagated.  Returns {} immediately when no token is provided.

    CodeQL contract: exception handlers log only static strings (zero args).
    """
    if not token:
        return {}

    s = _make_session(token, session)
    results: dict[str, list[dict]] = {}

    for audit in audits:
        metadata = audit.get("metadata") or {}
        repo_name = metadata.get("name", "")
        full_name = metadata.get("full_name", "")

        if not repo_name or not full_name or "/" not in full_name:
            continue

        owner, repo = full_name.split("/", 1)
        url = f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}/dependabot/alerts"

        try:
            alerts = _paginate(s, url, {"state": "open", "per_page": "100"})
            results[repo_name] = [_extract_detail(a) for a in alerts]
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status not in _EXPECTED_UNAVAILABLE_STATUSES:
                # Static message only — no interpolated values (CodeQL contract)
                logger.debug("Dependabot detail fetch unavailable for a repo (best-effort)")
            results[repo_name] = []
        except Exception:
            # Static message only — no interpolated values (CodeQL contract)
            logger.debug("Dependabot detail fetch failed for a repo (best-effort)")
            results[repo_name] = []

    return results
