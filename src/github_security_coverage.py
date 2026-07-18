"""Bounded, receipt-backed GitHub security coverage collection.

The receipt is intentionally count-only.  It records enough provenance to make
PortfolioTruth coverage claims auditable without persisting credentials, raw
alerts, or secret-scanning payloads.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

GITHUB_SECURITY_RECEIPT_SCHEMA_VERSION = "GitHubSecurityCoverageReceiptV1"
GITHUB_SECURITY_RECEIPT_FILENAME = "github-security-coverage-latest.json"
GITHUB_API_VERSION = "2026-03-10"
DEFAULT_COHORT_POLICY = "portfolio-default-attention-v1"
DEFAULT_ATTENTION_STATES = frozenset(
    {"active-product", "active-infra", "decision-needed"}
)
DEFAULT_EXPECTED_GITHUB_COHORT_COUNT = 9
PROVIDER_NAMES = ("dependabot", "code_scanning", "secret_scanning")
ELIGIBILITY_SOURCE = "github-account-repository-preflight-v1"
ELIGIBILITY_REASON = "private_user_repo_plan_unavailable"
ELIGIBILITY_STATES = frozenset(
    {
        "not_requested",
        "observed",
        "forbidden",
        "rate_limited",
        "transient_error",
        "malformed",
    }
)
PROVIDER_STATES = frozenset(
    {
        "observed",
        "not_requested",
        "credential_unavailable",
        "forbidden",
        "feature_unavailable",
        "not_found",
        "gone",
        "rate_limited",
        "transient_error",
        "malformed",
        "stale",
    }
)
DEFAULT_BASE_REQUEST_LIMIT = 48
DEFAULT_TOTAL_REQUEST_LIMIT = 75
DEFAULT_QUOTA_RESERVE = 100
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

_ENDPOINTS = {
    "dependabot": "dependabot/alerts",
    "code_scanning": "code-scanning/alerts",
    "secret_scanning": "secret-scanning/alerts",
}
_COUNT_KEYS = {
    "dependabot": ("critical", "high", "medium", "low"),
    "code_scanning": ("critical", "high", "warning", "note"),
    "secret_scanning": ("open",),
}
_CODE_SCANNING_BUCKET = {
    "critical": "critical",
    "high": "high",
    "error": "high",
    "medium": "warning",
    "low": "warning",
    "warning": "warning",
    "note": "note",
}


class SecurityCoverageError(ValueError):
    """Raised when a coverage receipt or bounded collection contract is invalid."""


@dataclass(frozen=True)
class LoadedSecurityCoverage:
    entries_by_full_name: dict[str, dict[str, Any]]
    produced_at: str
    schema_version: str
    cohort_policy: str
    cohort_repositories: tuple[str, ...]
    receipt_state: str
    age_hours: float
    source_path: str


@dataclass
class _Budget:
    base_limit: int
    total_limit: int
    quota_reserve: int
    base_requests: int = 0
    total_requests: int = 0
    stop_reason: str | None = None

    def consume(self, *, pagination: bool) -> bool:
        if self.stop_reason:
            return False
        if self.total_requests >= self.total_limit:
            self.stop_reason = "total_request_limit"
            return False
        if not pagination and self.base_requests >= self.base_limit:
            self.stop_reason = "base_request_limit"
            return False
        self.total_requests += 1
        if not pagination:
            self.base_requests += 1
        return True


def _parse_datetime(value: Any, *, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise SecurityCoverageError(f"{field_name} is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SecurityCoverageError(f"{field_name} is invalid: {value!r}") from exc
    if parsed.tzinfo is None:
        raise SecurityCoverageError(f"{field_name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _canonical_repo(value: Any) -> str:
    full_name = _text(value)
    if not _REPOSITORY_RE.fullmatch(full_name):
        raise SecurityCoverageError(f"invalid canonical repository name: {value!r}")
    return full_name


def derive_default_attention_cohort(
    portfolio_truth: dict[str, Any],
    *,
    expected_count: int = DEFAULT_EXPECTED_GITHUB_COHORT_COUNT,
) -> tuple[str, ...]:
    """Return the repo-backed default-attention cohort, failing on expansion."""
    repos: list[str] = []
    for project in portfolio_truth.get("projects") or []:
        if not isinstance(project, dict):
            continue
        derived = _mapping(project.get("derived"))
        if derived.get("attention_state") not in DEFAULT_ATTENTION_STATES:
            continue
        identity = _mapping(project.get("identity"))
        repo_full_name = identity.get("repo_full_name")
        if not _text(repo_full_name) and _text(identity.get("project_key")).startswith(
            "supp:"
        ):
            # Supplementary projects such as personal-ops are real portfolio
            # identities, but they do not have a GitHub repository to query.
            continue
        repos.append(_canonical_repo(repo_full_name))
    if len({repo.lower() for repo in repos}) != len(repos):
        raise SecurityCoverageError(
            "default-attention cohort contains duplicate canonical repositories"
        )
    cohort = tuple(sorted(repos, key=str.lower))
    if len(cohort) != expected_count:
        raise SecurityCoverageError(
            "default-attention cohort size changed: "
            f"expected {expected_count}, observed {len(cohort)}"
        )
    return cohort


def _empty_counts(provider: str) -> dict[str, int]:
    return {key: 0 for key in _COUNT_KEYS[provider]}


def _provider_result(
    provider: str,
    *,
    state: str,
    observed_at: str | None = None,
    http_status: int | None = None,
    reason: str | None = None,
    etag: str | None = None,
    last_modified: str | None = None,
    pagination_complete: bool = False,
    counts: dict[str, int] | None = None,
    conditional_request: bool = False,
    conditional_result: str = "not_used",
    http_classification: str | None = None,
) -> dict[str, Any]:
    if state not in PROVIDER_STATES:
        raise SecurityCoverageError(f"invalid provider state: {state}")
    return {
        "state": state,
        "observed_at": observed_at,
        "http_status": http_status,
        "http_classification": http_classification
        or (
            None
            if http_status is None
            else "success"
            if http_status == 200
            else "not_modified"
            if http_status == 304
            else reason
        ),
        "reason": reason,
        "etag": etag,
        "last_modified": last_modified,
        "conditional": {
            "requested": conditional_request,
            "result": conditional_result,
        },
        "pagination_complete": pagination_complete,
        "counts": counts if state == "observed" else None,
    }


def _response_message(response: requests.Response) -> str:
    try:
        payload = response.json()
    except (ValueError, TypeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    return _text(payload.get("message")).lower()


def _classify_failure(provider: str, response: requests.Response) -> tuple[str, str]:
    status = response.status_code
    message = _response_message(response)
    remaining = response.headers.get("X-RateLimit-Remaining")
    if status == 429 or (
        status == 403
        and (remaining == "0" or "rate limit" in message or "secondary rate" in message)
    ):
        return "rate_limited", "github_rate_limit"
    if status == 403:
        if provider == "code_scanning" and (
            "advanced security" in message
            or "code scanning is not enabled" in message
            or "code security" in message
        ):
            return "feature_unavailable", "code_scanning_not_enabled"
        return "forbidden", "github_forbidden"
    if status == 404:
        return "not_found", "github_not_found"
    if status == 410:
        return "gone", "github_gone"
    if status >= 500:
        return "transient_error", f"github_http_{status}"
    return "malformed", f"unexpected_http_{status}"


def _accumulate(provider: str, counts: dict[str, int], alerts: list[Any]) -> bool:
    for alert in alerts:
        if not isinstance(alert, dict):
            return False
        if provider == "dependabot":
            advisory = _mapping(alert.get("security_advisory"))
            vulnerability = _mapping(alert.get("security_vulnerability"))
            severity = _text(
                advisory.get("severity") or vulnerability.get("severity")
            ).lower()
            if severity in counts:
                counts[severity] += 1
        elif provider == "code_scanning":
            rule = _mapping(alert.get("rule"))
            severity = _text(
                rule.get("security_severity_level") or rule.get("severity")
            ).lower()
            bucket = _CODE_SCANNING_BUCKET.get(severity)
            if bucket:
                counts[bucket] += 1
        else:
            counts["open"] += 1
    return True


def _prior_provider(
    prior_receipt: dict[str, Any] | None,
    repo_full_name: str,
    provider: str,
) -> dict[str, Any]:
    repositories = _mapping(_mapping(prior_receipt).get("repositories"))
    entry = _mapping(repositories.get(repo_full_name))
    return _mapping(_mapping(entry.get("providers")).get(provider))


def _eligibility_candidates(
    prior_receipt: dict[str, Any] | None,
    cohort: tuple[str, ...],
) -> tuple[str, ...]:
    candidates: list[str] = []
    for repo_full_name in cohort:
        code_state = _text(
            _prior_provider(prior_receipt, repo_full_name, "code_scanning").get("state")
        )
        secret_state = _text(
            _prior_provider(prior_receipt, repo_full_name, "secret_scanning").get(
                "state"
            )
        )
        if code_state in {"feature_unavailable", "not_found"} or secret_state in {
            "feature_unavailable",
            "not_found",
        }:
            candidates.append(repo_full_name)
    return tuple(candidates)


def _reserve_reached(response: requests.Response, budget: _Budget) -> bool:
    remaining = response.headers.get("X-RateLimit-Remaining")
    if remaining is None:
        return False
    try:
        return int(remaining) <= budget.quota_reserve
    except ValueError:
        return False


def _eligibility_metadata(
    *,
    state: str,
    observed_at: str | None,
    reason: str | None,
    candidates: tuple[str, ...],
    request_count: int,
    account: dict[str, str] | None = None,
    repositories: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if state not in ELIGIBILITY_STATES:
        raise SecurityCoverageError(f"invalid eligibility state: {state}")
    return {
        "source": ELIGIBILITY_SOURCE,
        "state": state,
        "observed_at": observed_at,
        "reason": reason,
        "candidate_repositories": list(candidates),
        "request_count": request_count,
        "account": account,
        "repositories": repositories or {},
    }


def _preflight_failure(
    response: requests.Response,
) -> tuple[str, str]:
    state, reason = _classify_failure("dependabot", response)
    if state in {"not_found", "gone"}:
        return "malformed", reason
    if state == "feature_unavailable":
        return "forbidden", reason
    return state, reason


def _preflight_json(
    session: requests.Session,
    *,
    method: str,
    url: str,
    budget: _Budget,
    request_kwargs: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, str, str | None, bool]:
    if not budget.consume(pagination=False):
        return None, "not_requested", budget.stop_reason, True
    try:
        response = getattr(session, method)(
            url,
            timeout=30,
            **(request_kwargs or {}),
        )
    except requests.RequestException:
        return None, "transient_error", "network_error", False
    reserve_reached = _reserve_reached(response, budget)
    if response.status_code != 200:
        state, reason = _preflight_failure(response)
        if state == "rate_limited":
            budget.stop_reason = "rate_limited"
        elif reserve_reached:
            budget.stop_reason = "quota_reserve"
        return (
            None,
            state,
            reason,
            state == "rate_limited" or reserve_reached,
        )
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        return None, "malformed", "non_object_payload", reserve_reached
    if reserve_reached:
        budget.stop_reason = "quota_reserve"
    return payload, "observed", None, reserve_reached


def _collect_eligibility_preflight(
    session: requests.Session,
    *,
    api_base_url: str,
    candidates: tuple[str, ...],
    now_iso: str,
    budget: _Budget,
) -> tuple[dict[str, Any], dict[str, frozenset[str]], bool]:
    before_requests = budget.base_requests

    def finish(
        *,
        state: str,
        reason: str | None,
        account: dict[str, str] | None = None,
        repositories: dict[str, dict[str, Any]] | None = None,
        unavailable: dict[str, frozenset[str]] | None = None,
        halted: bool = False,
    ) -> tuple[dict[str, Any], dict[str, frozenset[str]], bool]:
        return (
            _eligibility_metadata(
                state=state,
                observed_at=now_iso if budget.base_requests > before_requests else None,
                reason=reason,
                candidates=candidates,
                request_count=budget.base_requests - before_requests,
                account=account,
                repositories=repositories,
            ),
            unavailable or {},
            halted,
        )

    if not candidates:
        return finish(
            state="not_requested",
            reason="no_prior_unavailable_candidates",
        )
    account_payload, state, reason, halted = _preflight_json(
        session,
        method="get",
        url=f"{api_base_url}/user",
        budget=budget,
    )
    if state != "observed":
        return finish(
            state=state,
            reason=f"account_{reason}",
            halted=halted,
        )
    account_data = _mapping(account_payload)
    account_login = _text(account_data.get("login"))
    account_plan = _text(_mapping(account_data.get("plan")).get("name")).lower()
    if not account_login or not account_plan:
        return finish(
            state="malformed",
            reason="account_payload_invalid",
            halted=halted,
        )
    account = {"login": account_login, "plan": account_plan}
    if halted:
        return finish(
            state="not_requested",
            reason="quota_reserve_before_repository_query",
            account=account,
            halted=True,
        )

    variables: dict[str, str] = {}
    fields: list[str] = []
    for index, repo_full_name in enumerate(candidates):
        owner_name, name = repo_full_name.split("/", 1)
        variables[f"owner{index}"] = owner_name
        variables[f"name{index}"] = name
        fields.append(
            f"repo{index}: repository(owner: $owner{index}, name: $name{index}) "
            "{ nameWithOwner visibility owner { __typename login } }"
        )
    declarations = ", ".join(f"${key}: String!" for key in variables)
    query = f"query({declarations}) {{ {' '.join(fields)} }}"
    repository_payload, state, reason, halted = _preflight_json(
        session,
        method="post",
        url=f"{api_base_url}/graphql",
        budget=budget,
        request_kwargs={"json": {"query": query, "variables": variables}},
    )
    if state != "observed":
        return finish(
            state=state,
            reason=f"repository_query_{reason}",
            account=account,
            halted=halted,
        )
    payload_mapping = _mapping(repository_payload)
    data = _mapping(payload_mapping.get("data"))
    if payload_mapping.get("errors") or len(data) != len(candidates):
        return finish(
            state="malformed",
            reason="repository_query_payload_invalid",
            account=account,
            halted=halted,
        )

    repository_evidence: dict[str, dict[str, Any]] = {}
    unavailable: dict[str, frozenset[str]] = {}
    for index, expected_repo in enumerate(candidates):
        repository = _mapping(data.get(f"repo{index}"))
        full_name = _canonical_repo(repository.get("nameWithOwner"))
        if full_name.lower() != expected_repo.lower():
            return finish(
                state="malformed",
                reason="repository_identity_mismatch",
                account=account,
                halted=halted,
            )
        owner_data = _mapping(repository.get("owner"))
        visibility = _text(repository.get("visibility")).lower()
        owner_type = _text(owner_data.get("__typename"))
        owner_login = _text(owner_data.get("login"))
        plan_blocked = (
            account_plan in {"free", "pro"}
            and visibility == "private"
            and owner_type == "User"
            and owner_login.lower() == account_login.lower()
        )
        unavailable_providers = (
            frozenset({"code_scanning", "secret_scanning"})
            if plan_blocked
            else frozenset()
        )
        repository_evidence[expected_repo] = {
            "visibility": visibility,
            "owner_type": owner_type,
            "owner_login": owner_login,
            "unavailable_providers": sorted(unavailable_providers),
        }
        if unavailable_providers:
            unavailable[expected_repo] = unavailable_providers
    return finish(
        state="observed",
        reason=None,
        account=account,
        repositories=repository_evidence,
        unavailable=unavailable,
        halted=halted,
    )


def _fetch_provider(
    session: requests.Session,
    *,
    api_base_url: str,
    repo_full_name: str,
    provider: str,
    now_iso: str,
    budget: _Budget,
    prior: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    endpoint = _ENDPOINTS[provider]
    next_url: str | None = f"{api_base_url}/repos/{repo_full_name}/{endpoint}"
    params: dict[str, str] = {"state": "open", "per_page": "100"}
    headers: dict[str, str] = {}
    prior_etag = _text(prior.get("etag"))
    if prior_etag:
        headers["If-None-Match"] = prior_etag
    counts = _empty_counts(provider)
    first_response = True
    etag = last_modified = None

    while next_url:
        if not budget.consume(pagination=not first_response):
            return (
                _provider_result(
                    provider,
                    state="not_requested",
                    reason=budget.stop_reason,
                    conditional_request=bool(prior_etag),
                    conditional_result="incomplete",
                ),
                True,
            )
        try:
            response = session.get(
                next_url,
                params=params if first_response else None,
                headers=headers if first_response else None,
                timeout=30,
            )
        except requests.RequestException:
            return (
                _provider_result(
                    provider,
                    state="transient_error",
                    observed_at=now_iso,
                    reason="network_error",
                    conditional_request=bool(prior_etag),
                    conditional_result="failed",
                ),
                False,
            )

        etag = response.headers.get("ETag") or etag
        last_modified = response.headers.get("Last-Modified") or last_modified
        reserve_reached = False
        remaining = response.headers.get("X-RateLimit-Remaining")
        if remaining is not None:
            try:
                reserve_reached = int(remaining) <= budget.quota_reserve
            except ValueError:
                pass  # Missing/malformed quota metadata leaves the conservative request budget in control.
        if response.status_code == 304:
            if reserve_reached:
                budget.stop_reason = "quota_reserve"
            prior_counts = prior.get("counts")
            if prior.get("state") != "observed" or not isinstance(prior_counts, dict):
                return (
                    _provider_result(
                        provider,
                        state="malformed",
                        http_status=304,
                        reason="conditional_response_without_observed_prior",
                        observed_at=now_iso,
                        conditional_request=True,
                        conditional_result="invalid_prior",
                    ),
                    False,
                )
            return (
                _provider_result(
                    provider,
                    state="observed",
                    observed_at=now_iso,
                    http_status=304,
                    reason="not_modified",
                    etag=etag or prior_etag,
                    last_modified=last_modified
                    or _text(prior.get("last_modified"))
                    or None,
                    pagination_complete=True,
                    counts={
                        key: int(prior_counts.get(key, 0) or 0)
                        for key in _COUNT_KEYS[provider]
                    },
                    conditional_request=True,
                    conditional_result="not_modified",
                ),
                reserve_reached,
            )
        if response.status_code != 200:
            state, reason = _classify_failure(provider, response)
            if state == "rate_limited":
                budget.stop_reason = "rate_limited"
            elif reserve_reached:
                budget.stop_reason = "quota_reserve"
            return (
                _provider_result(
                    provider,
                    state=state,
                    http_status=response.status_code,
                    reason=reason,
                    observed_at=now_iso,
                    etag=etag,
                    last_modified=last_modified,
                    conditional_request=bool(prior_etag),
                    conditional_result="failed",
                ),
                state == "rate_limited" or reserve_reached,
            )
        try:
            page = response.json()
        except ValueError:
            page = None
        if not isinstance(page, list) or not _accumulate(provider, counts, page):
            return (
                _provider_result(
                    provider,
                    state="malformed",
                    http_status=200,
                    reason="non_list_or_invalid_alert_payload",
                    observed_at=now_iso,
                    etag=etag,
                    last_modified=last_modified,
                    conditional_request=bool(prior_etag),
                    conditional_result="malformed",
                ),
                False,
            )
        next_url = response.links.get("next", {}).get("url")
        if reserve_reached:
            budget.stop_reason = "quota_reserve"
            if next_url:
                return (
                    _provider_result(
                        provider,
                        state="not_requested",
                        observed_at=now_iso,
                        reason="quota_reserve_before_pagination_complete",
                        conditional_request=bool(prior_etag),
                        conditional_result="incomplete",
                    ),
                    True,
                )
        first_response = False
        params = {}
        headers = {}

    result = _provider_result(
        provider,
        state="observed",
        observed_at=now_iso,
        http_status=200,
        etag=etag,
        last_modified=last_modified,
        pagination_complete=True,
        counts=counts,
        conditional_request=bool(prior_etag),
        conditional_result="modified" if prior_etag else "not_used",
    )
    return result, budget.stop_reason == "quota_reserve"


def collect_security_coverage(
    portfolio_truth: dict[str, Any],
    *,
    token: str | None,
    expected_cohort_count: int = DEFAULT_EXPECTED_GITHUB_COHORT_COUNT,
    base_request_limit: int = DEFAULT_BASE_REQUEST_LIMIT,
    total_request_limit: int = DEFAULT_TOTAL_REQUEST_LIMIT,
    quota_reserve: int = DEFAULT_QUOTA_RESERVE,
    prior_receipt: dict[str, Any] | None = None,
    session: requests.Session | None = None,
    now: datetime | None = None,
    producer_commit: str | None = None,
    api_base_url: str | None = None,
) -> dict[str, Any]:
    """Collect the bounded default-attention cohort into a provenance receipt."""
    if not token:
        raise SecurityCoverageError(
            "authorized GitHub read credential unavailable; no receipt was written"
        )
    if (
        not 0 < base_request_limit <= DEFAULT_BASE_REQUEST_LIMIT
        or not base_request_limit <= total_request_limit <= DEFAULT_TOTAL_REQUEST_LIMIT
        or quota_reserve < 0
    ):
        raise SecurityCoverageError("request budget limits exceed the bounded contract")
    if prior_receipt is not None:
        prior_expected_count = _mapping(prior_receipt.get("cohort")).get(
            "expected_count"
        )
        if not isinstance(prior_expected_count, int):
            raise SecurityCoverageError(
                "prior receipt cohort expected_count is invalid"
            )
        validate_security_coverage_receipt(
            prior_receipt,
            max_age_hours=24 * 365,
            expected_cohort_count=prior_expected_count,
            now=now,
        )
        if prior_expected_count != expected_cohort_count:
            # A valid receipt for the previous bounded cohort cannot safely
            # supply conditional-request or eligibility hints for the new one.
            # Ignore it so the policy transition can produce fresh evidence.
            prior_receipt = None
    cohort = derive_default_attention_cohort(
        portfolio_truth, expected_count=expected_cohort_count
    )
    commit = producer_commit
    if not commit:
        try:
            commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            raise SecurityCoverageError(
                "producer commit unavailable; refusing an unproven receipt"
            )
    if not _COMMIT_RE.fullmatch(commit):
        raise SecurityCoverageError(
            "producer commit is invalid; refusing an unproven receipt"
        )

    collected_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    now_iso = collected_at.isoformat()
    client = session or requests.Session()
    client.headers.update(
        {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "github-repo-auditor/security-coverage",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        }
    )
    budget = _Budget(
        base_limit=base_request_limit,
        total_limit=total_request_limit,
        quota_reserve=quota_reserve,
    )
    resolved_api_base_url = api_base_url or os.environ.get(
        "GITHUB_API_BASE_URL", "https://api.github.com"
    )
    eligibility, unavailable_providers, halted = _collect_eligibility_preflight(
        client,
        api_base_url=resolved_api_base_url,
        candidates=_eligibility_candidates(prior_receipt, cohort),
        now_iso=now_iso,
        budget=budget,
    )
    repositories: dict[str, dict[str, Any]] = {}
    for repo_full_name in cohort:
        providers: dict[str, dict[str, Any]] = {}
        for provider in PROVIDER_NAMES:
            if halted:
                providers[provider] = _provider_result(
                    provider,
                    state="not_requested",
                    reason=budget.stop_reason or "collection_halted",
                )
                continue
            if provider in unavailable_providers.get(repo_full_name, frozenset()):
                providers[provider] = _provider_result(
                    provider,
                    state="feature_unavailable",
                    observed_at=now_iso,
                    http_status=200,
                    http_classification="eligibility",
                    reason=ELIGIBILITY_REASON,
                )
                continue
            providers[provider], halted = _fetch_provider(
                client,
                api_base_url=resolved_api_base_url,
                repo_full_name=repo_full_name,
                provider=provider,
                now_iso=now_iso,
                budget=budget,
                prior=_prior_provider(prior_receipt, repo_full_name, provider),
            )
        repositories[repo_full_name] = {"providers": providers}

    produced_at = (
        collected_at if now is not None else datetime.now(timezone.utc)
    ).astimezone(timezone.utc)
    return {
        "schema_version": GITHUB_SECURITY_RECEIPT_SCHEMA_VERSION,
        "produced_at": produced_at.isoformat(),
        "producer": {
            "repository": "saagpatel/GithubRepoAuditor",
            "commit": commit,
        },
        "github_api_version": GITHUB_API_VERSION,
        "eligibility": eligibility,
        "cohort": {
            "policy": DEFAULT_COHORT_POLICY,
            "expected_count": expected_cohort_count,
            "repository_count": len(cohort),
            "repositories": list(cohort),
        },
        "request_budget": {
            "base_limit": base_request_limit,
            "total_limit": total_request_limit,
            "quota_reserve": quota_reserve,
            "base_requests": budget.base_requests,
            "total_requests": budget.total_requests,
            "stop_reason": budget.stop_reason,
        },
        "repositories": repositories,
    }


def _validate_eligibility(
    value: Any,
    *,
    produced_at: datetime,
    current: datetime,
    cohort: tuple[str, ...],
) -> dict[str, Any] | None:
    if value is None:
        return None
    data = _mapping(value)
    if data.get("source") != ELIGIBILITY_SOURCE:
        raise SecurityCoverageError("eligibility.source is invalid")
    state = _text(data.get("state"))
    if state not in ELIGIBILITY_STATES:
        raise SecurityCoverageError(f"eligibility.state is invalid: {state!r}")
    request_count = data.get("request_count")
    if (
        not isinstance(request_count, int)
        or isinstance(request_count, bool)
        or not 0 <= request_count <= 2
    ):
        raise SecurityCoverageError("eligibility.request_count is invalid")
    raw_candidates = data.get("candidate_repositories")
    if not isinstance(raw_candidates, list):
        raise SecurityCoverageError("eligibility candidates are required")
    candidates = tuple(_canonical_repo(repo) for repo in raw_candidates)
    if candidates != tuple(sorted(candidates, key=str.lower)):
        raise SecurityCoverageError("eligibility candidates must be canonically sorted")
    if len({repo.lower() for repo in candidates}) != len(candidates):
        raise SecurityCoverageError("eligibility candidates contain duplicates")
    if not set(candidates).issubset(cohort):
        raise SecurityCoverageError("eligibility candidates are outside the cohort")

    observed_at_value = data.get("observed_at")
    observed_at = (
        _parse_datetime(observed_at_value, field_name="eligibility.observed_at")
        if observed_at_value is not None
        else None
    )
    if observed_at is not None:
        if observed_at > produced_at:
            raise SecurityCoverageError(
                "eligibility.observed_at is later than receipt produced_at"
            )
        if (current - observed_at).total_seconds() / 3600 < -0.05:
            raise SecurityCoverageError("eligibility.observed_at is future-dated")
    if request_count and observed_at is None:
        raise SecurityCoverageError(
            "eligibility.observed_at is required when requests were attempted"
        )

    account_value = data.get("account")
    account = _mapping(account_value)
    normalized_account: dict[str, str] | None = None
    if account_value is not None:
        login = _text(account.get("login"))
        plan = _text(account.get("plan")).lower()
        if not login or not plan:
            raise SecurityCoverageError("eligibility.account is invalid")
        normalized_account = {"login": login, "plan": plan}

    raw_repositories = data.get("repositories")
    if not isinstance(raw_repositories, dict):
        raise SecurityCoverageError("eligibility.repositories must be an object")
    if not set(raw_repositories).issubset(candidates):
        raise SecurityCoverageError(
            "eligibility repository evidence is outside the candidates"
        )
    normalized_repositories: dict[str, dict[str, Any]] = {}
    for repo_full_name, raw_repository in raw_repositories.items():
        repository = _mapping(raw_repository)
        visibility = _text(repository.get("visibility")).lower()
        owner_type = _text(repository.get("owner_type"))
        owner_login = _text(repository.get("owner_login"))
        unavailable = repository.get("unavailable_providers")
        if (
            visibility not in {"public", "private", "internal"}
            or not owner_type
            or not owner_login
            or not isinstance(unavailable, list)
            or any(
                provider not in {"code_scanning", "secret_scanning"}
                for provider in unavailable
            )
            or len(set(unavailable)) != len(unavailable)
        ):
            raise SecurityCoverageError(
                f"eligibility repository evidence is invalid: {repo_full_name}"
            )
        normalized_unavailable = sorted(unavailable)
        if normalized_unavailable:
            if (
                normalized_account is None
                or normalized_account["plan"] not in {"free", "pro"}
                or visibility != "private"
                or owner_type != "User"
                or owner_login.lower() != normalized_account["login"].lower()
            ):
                raise SecurityCoverageError(
                    f"eligibility unavailable claim is unproven: {repo_full_name}"
                )
        normalized_repositories[repo_full_name] = {
            "visibility": visibility,
            "owner_type": owner_type,
            "owner_login": owner_login,
            "unavailable_providers": normalized_unavailable,
        }
    if state == "observed":
        if (
            request_count != 2
            or normalized_account is None
            or set(normalized_repositories) != set(candidates)
        ):
            raise SecurityCoverageError("observed eligibility evidence is incomplete")
    return {
        "source": ELIGIBILITY_SOURCE,
        "state": state,
        "observed_at": data.get("observed_at"),
        "reason": data.get("reason"),
        "candidate_repositories": list(candidates),
        "request_count": request_count,
        "account": normalized_account,
        "repositories": normalized_repositories,
    }


def _validate_provider(
    provider: str,
    value: Any,
    *,
    repo_full_name: str,
    eligibility: dict[str, Any] | None,
    receipt_is_stale: bool,
    produced_at: datetime,
    current: datetime,
    max_age_hours: int,
) -> dict[str, Any]:
    data = _mapping(value)
    state = _text(data.get("state"))
    if state not in PROVIDER_STATES:
        raise SecurityCoverageError(f"{provider}.state is invalid: {state!r}")
    counts = data.get("counts")
    http_status = data.get("http_status")
    http_classification = data.get("http_classification")
    conditional = _mapping(data.get("conditional"))
    if not isinstance(conditional.get("requested"), bool) or conditional.get(
        "result"
    ) not in {
        "not_used",
        "modified",
        "not_modified",
        "failed",
        "malformed",
        "incomplete",
        "invalid_prior",
    }:
        raise SecurityCoverageError(f"{provider}.conditional metadata is invalid")
    if http_status is not None and (
        not isinstance(http_status, int) or isinstance(http_status, bool)
    ):
        raise SecurityCoverageError(
            f"{provider}.http_status must be an integer or null"
        )
    if http_classification is not None and not isinstance(http_classification, str):
        raise SecurityCoverageError(
            f"{provider}.http_classification must be a string or null"
        )
    observed_at_value = data.get("observed_at")
    observed_at = (
        _parse_datetime(observed_at_value, field_name=f"{provider}.observed_at")
        if observed_at_value is not None
        else None
    )
    if observed_at is not None:
        if observed_at > produced_at:
            raise SecurityCoverageError(
                f"{provider}.observed_at is later than receipt produced_at"
            )
        if (current - observed_at).total_seconds() / 3600 < -0.05:
            raise SecurityCoverageError(f"{provider}.observed_at is future-dated")
    if state == "observed":
        if observed_at is None:
            raise SecurityCoverageError(f"{provider}.observed_at is required")
        provider_age_hours = (current - observed_at).total_seconds() / 3600
        if not data.get("pagination_complete"):
            raise SecurityCoverageError(
                f"{provider} observed without complete pagination"
            )
        if not isinstance(counts, dict) or set(counts) != set(_COUNT_KEYS[provider]):
            raise SecurityCoverageError(f"{provider}.counts required when observed")
        if http_status not in {200, 304}:
            raise SecurityCoverageError(
                f"{provider}.http_status must be 200 or 304 when observed"
            )
        expected_classification = "success" if http_status == 200 else "not_modified"
        if http_classification != expected_classification:
            raise SecurityCoverageError(
                f"{provider}.http_classification does not match observed response"
            )
        normalized_counts: dict[str, int] = {}
        for key in _COUNT_KEYS[provider]:
            raw = counts.get(key)
            if not isinstance(raw, int) or raw < 0:
                raise SecurityCoverageError(
                    f"{provider}.counts.{key} must be non-negative"
                )
            normalized_counts[key] = raw
        counts = normalized_counts
        if provider_age_hours > max_age_hours:
            state = "stale"
            counts = None
    elif counts is not None:
        raise SecurityCoverageError(f"{provider}.counts must be null unless observed")
    if state == "not_requested" and http_status is not None:
        raise SecurityCoverageError(
            f"{provider} not_requested must not claim HTTP status"
        )
    if state == "forbidden" and http_status != 403:
        raise SecurityCoverageError(f"{provider} forbidden requires HTTP 403")
    if state == "feature_unavailable":
        if data.get("reason") == ELIGIBILITY_REASON:
            repository_eligibility = _mapping(
                _mapping(eligibility).get("repositories")
            ).get(repo_full_name)
            unavailable = _mapping(repository_eligibility).get("unavailable_providers")
            if (
                http_status != 200
                or http_classification != "eligibility"
                or _mapping(eligibility).get("state") != "observed"
                or not isinstance(unavailable, list)
                or provider not in unavailable
            ):
                raise SecurityCoverageError(
                    f"{provider} eligibility-based unavailability is unproven"
                )
        elif http_status not in {403, 404}:
            raise SecurityCoverageError(
                f"{provider} feature_unavailable requires HTTP 403 or 404"
            )
    if state == "not_found" and http_status != 404:
        raise SecurityCoverageError(f"{provider} not_found requires HTTP 404")
    if state == "gone" and http_status != 410:
        raise SecurityCoverageError(f"{provider} gone requires HTTP 410")
    if state == "rate_limited" and http_status not in {403, 429}:
        raise SecurityCoverageError(f"{provider} rate_limited requires HTTP 403 or 429")
    if receipt_is_stale and state == "observed":
        state = "stale"
        counts = None
    return {
        "state": state,
        "observed_at": data.get("observed_at"),
        "http_status": http_status,
        "http_classification": http_classification,
        "reason": "receipt_stale" if state == "stale" else data.get("reason"),
        "etag": data.get("etag"),
        "last_modified": data.get("last_modified"),
        "conditional": conditional,
        "pagination_complete": bool(data.get("pagination_complete")),
        "counts": counts,
    }


def validate_security_coverage_receipt(
    payload: Any,
    *,
    max_age_hours: int = 24,
    expected_cohort_count: int = DEFAULT_EXPECTED_GITHUB_COHORT_COUNT,
    now: datetime | None = None,
    source_path: str = "",
) -> LoadedSecurityCoverage:
    """Validate provenance/freshness and return normalized full-name entries."""
    if max_age_hours <= 0:
        raise SecurityCoverageError("max_age_hours must be positive")
    if not isinstance(payload, dict):
        raise SecurityCoverageError("security coverage receipt must be an object")
    if payload.get("schema_version") != GITHUB_SECURITY_RECEIPT_SCHEMA_VERSION:
        raise SecurityCoverageError(
            "unexpected security coverage receipt schema: "
            f"{payload.get('schema_version')!r}"
        )
    produced_at = _parse_datetime(payload.get("produced_at"), field_name="produced_at")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    age_hours = (current - produced_at).total_seconds() / 3600
    if age_hours < -0.05:
        raise SecurityCoverageError("security coverage receipt is future-dated")
    receipt_is_stale = age_hours > max_age_hours

    producer = _mapping(payload.get("producer"))
    if producer.get("repository") != "saagpatel/GithubRepoAuditor":
        raise SecurityCoverageError(
            "security coverage receipt producer repository is invalid"
        )
    commit = _text(producer.get("commit"))
    if not _COMMIT_RE.fullmatch(commit):
        raise SecurityCoverageError(
            "security coverage receipt producer commit is invalid"
        )
    if payload.get("github_api_version") != GITHUB_API_VERSION:
        raise SecurityCoverageError("security coverage receipt API version is invalid")

    cohort = _mapping(payload.get("cohort"))
    policy = _text(cohort.get("policy"))
    if policy != DEFAULT_COHORT_POLICY:
        raise SecurityCoverageError(f"unexpected cohort policy: {policy!r}")
    expected_count = cohort.get("expected_count")
    repository_count = cohort.get("repository_count")
    repositories_list = cohort.get("repositories")
    if (
        not isinstance(expected_count, int)
        or not isinstance(repository_count, int)
        or not isinstance(repositories_list, list)
    ):
        raise SecurityCoverageError("cohort counts and repositories are required")
    canonical_cohort = tuple(_canonical_repo(repo) for repo in repositories_list)
    if len({repo.lower() for repo in canonical_cohort}) != len(canonical_cohort):
        raise SecurityCoverageError("cohort contains duplicate repositories")
    if (
        repository_count != len(canonical_cohort)
        or expected_count != repository_count
        or repository_count != expected_cohort_count
    ):
        raise SecurityCoverageError("cohort count contract mismatch")
    if canonical_cohort != tuple(sorted(canonical_cohort, key=str.lower)):
        raise SecurityCoverageError("cohort repositories must be canonically sorted")
    eligibility = _validate_eligibility(
        payload.get("eligibility"),
        produced_at=produced_at,
        current=current,
        cohort=canonical_cohort,
    )

    request_budget = _mapping(payload.get("request_budget"))
    base_limit = request_budget.get("base_limit")
    total_limit = request_budget.get("total_limit")
    quota_reserve = request_budget.get("quota_reserve")
    base_requests = request_budget.get("base_requests")
    total_requests = request_budget.get("total_requests")
    if (
        not isinstance(base_limit, int)
        or not 0 < base_limit <= DEFAULT_BASE_REQUEST_LIMIT
        or not isinstance(total_limit, int)
        or not base_limit <= total_limit <= DEFAULT_TOTAL_REQUEST_LIMIT
        or not isinstance(quota_reserve, int)
        or quota_reserve < 0
        or not isinstance(base_requests, int)
        or not 0 <= base_requests <= base_limit
        or not isinstance(total_requests, int)
        or not base_requests <= total_requests <= total_limit
    ):
        raise SecurityCoverageError("request budget contract is invalid")

    raw_repositories = _mapping(payload.get("repositories"))
    if set(raw_repositories) != set(canonical_cohort):
        raise SecurityCoverageError("receipt repositories do not match cohort")
    entries: dict[str, dict[str, Any]] = {}
    for repo_full_name in canonical_cohort:
        repo_data = _mapping(raw_repositories.get(repo_full_name))
        providers = _mapping(repo_data.get("providers"))
        if set(providers) != set(PROVIDER_NAMES):
            raise SecurityCoverageError(
                f"{repo_full_name} does not contain exactly the required providers"
            )
        entries[repo_full_name] = {
            "repo_full_name": repo_full_name,
            "cohort_member": True,
            "cohort_policy": policy,
            "receipt_schema_version": GITHUB_SECURITY_RECEIPT_SCHEMA_VERSION,
            "source_produced_at": produced_at.isoformat(),
            "receipt_state": "stale" if receipt_is_stale else "fresh",
            "providers": {
                provider: _validate_provider(
                    provider,
                    providers[provider],
                    repo_full_name=repo_full_name,
                    eligibility=eligibility,
                    receipt_is_stale=receipt_is_stale,
                    produced_at=produced_at,
                    current=current,
                    max_age_hours=max_age_hours,
                )
                for provider in PROVIDER_NAMES
            },
        }
    return LoadedSecurityCoverage(
        entries_by_full_name=entries,
        produced_at=produced_at.isoformat(),
        schema_version=GITHUB_SECURITY_RECEIPT_SCHEMA_VERSION,
        cohort_policy=policy,
        cohort_repositories=canonical_cohort,
        receipt_state="stale" if receipt_is_stale else "fresh",
        age_hours=round(age_hours, 3),
        source_path=source_path,
    )


def load_security_coverage_receipt(
    path: Path,
    *,
    max_age_hours: int = 24,
    expected_cohort_count: int = DEFAULT_EXPECTED_GITHUB_COHORT_COUNT,
    now: datetime | None = None,
) -> LoadedSecurityCoverage:
    try:
        payload = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise SecurityCoverageError(
            f"security coverage receipt not found: {path}"
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise SecurityCoverageError(
            f"could not read security coverage receipt {path}: {exc}"
        ) from exc
    return validate_security_coverage_receipt(
        payload,
        max_age_hours=max_age_hours,
        expected_cohort_count=expected_cohort_count,
        now=now,
        source_path=str(path),
    )


def write_security_coverage_receipt(
    payload: dict[str, Any],
    path: Path,
    *,
    expected_cohort_count: int = DEFAULT_EXPECTED_GITHUB_COHORT_COUNT,
) -> None:
    """Atomically write a validated receipt payload."""
    validate_security_coverage_receipt(
        payload,
        max_age_hours=24 * 365,
        expected_cohort_count=expected_cohort_count,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SecurityCoverageError(
            f"could not read JSON object {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise SecurityCoverageError(f"{path} must contain a JSON object")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect bounded default-attention GitHub security coverage"
    )
    parser.add_argument(
        "--truth",
        type=Path,
        default=Path("output/portfolio-truth-latest.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output") / GITHUB_SECURITY_RECEIPT_FILENAME,
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the existing receipt without using a credential or GitHub API",
    )
    parser.add_argument(
        "--max-age-hours",
        type=int,
        default=24,
        help="Freshness window used by --validate-only (default: 24)",
    )
    parser.add_argument(
        "--expected-cohort-count",
        type=int,
        default=DEFAULT_EXPECTED_GITHUB_COHORT_COUNT,
    )
    parser.add_argument(
        "--base-request-limit", type=int, default=DEFAULT_BASE_REQUEST_LIMIT
    )
    parser.add_argument(
        "--total-request-limit", type=int, default=DEFAULT_TOTAL_REQUEST_LIMIT
    )
    parser.add_argument("--quota-reserve", type=int, default=DEFAULT_QUOTA_RESERVE)
    args = parser.parse_args()

    try:
        if args.validate_only:
            loaded = load_security_coverage_receipt(
                args.output,
                max_age_hours=args.max_age_hours,
                expected_cohort_count=args.expected_cohort_count,
            )
            print(
                json.dumps(
                    {
                        "state": "validated",
                        "path": str(args.output),
                        "receipt_state": loaded.receipt_state,
                        "age_hours": loaded.age_hours,
                        "cohort_count": len(loaded.cohort_repositories),
                    },
                    indent=2,
                )
            )
            return
        truth = _load_json_object(args.truth)
        prior = _load_json_object(args.output) if args.output.is_file() else None
        receipt = collect_security_coverage(
            truth,
            token=os.environ.get("GITHUB_TOKEN"),
            expected_cohort_count=args.expected_cohort_count,
            base_request_limit=args.base_request_limit,
            total_request_limit=args.total_request_limit,
            quota_reserve=args.quota_reserve,
            prior_receipt=prior,
        )
        write_security_coverage_receipt(
            receipt,
            args.output,
            expected_cohort_count=args.expected_cohort_count,
        )
    except SecurityCoverageError as exc:
        raise SystemExit(str(exc)) from exc
    print(
        json.dumps(
            {
                "state": "written",
                "path": str(args.output),
                "cohort_count": receipt["cohort"]["repository_count"],
                "request_budget": receipt["request_budget"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
