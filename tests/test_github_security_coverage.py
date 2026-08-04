from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from src.github_security_coverage import (
    DEFAULT_BASE_REQUEST_LIMIT,
    DEFAULT_EXPECTED_GITHUB_COHORT_COUNT,
    GITHUB_SECURITY_RECEIPT_FILENAME,
    PROVIDER_STATES,
    SecurityCoverageError,
    _provider_result,
    _remote_repository_result,
    _valid_git_branch,
    _valid_git_upstream,
    collect_security_coverage,
    derive_default_attention_cohort,
    load_security_coverage_receipt,
    main,
    security_coverage_receipt_writer,
    validate_normalized_security_provider,
    validate_security_coverage_receipt,
    verified_security_coverage_receipt_binding,
    write_security_coverage_receipt,
)
from src.portfolio_truth_reconcile import _select_security_entry
from src.portfolio_truth_status import load_security_coverage_by_full_name

NOW = datetime(2026, 7, 16, 12, tzinfo=timezone.utc)
OUTCOME_FIXTURES = json.loads(
    (
        Path(__file__).parent
        / "fixtures"
        / "github_security_coverage"
        / "outcomes.json"
    ).read_text()
)

NORMALIZED_PROVIDER_STATE_FIXTURES = {
    "observed": {
        "observed_at": NOW.isoformat(),
        "http_status": 200,
        "pagination_complete": True,
        "counts": {"critical": 0, "high": 0, "medium": 0, "low": 0},
    },
    "not_requested": {"reason": "collection_halted"},
    "credential_unavailable": {
        "observed_at": NOW.isoformat(),
        "reason": "github_authentication_missing",
    },
    "forbidden": {
        "observed_at": NOW.isoformat(),
        "http_status": 403,
        "reason": "github_forbidden",
        "conditional_result": "failed",
    },
    "feature_unavailable": {
        "observed_at": NOW.isoformat(),
        "http_status": 403,
        "reason": "code_scanning_not_enabled",
        "conditional_result": "failed",
    },
    "not_found": {
        "observed_at": NOW.isoformat(),
        "http_status": 404,
        "reason": "github_not_found",
        "conditional_result": "failed",
    },
    "gone": {
        "observed_at": NOW.isoformat(),
        "http_status": 410,
        "reason": "github_gone",
        "conditional_result": "failed",
    },
    "rate_limited": {
        "observed_at": NOW.isoformat(),
        "http_status": 429,
        "reason": "github_rate_limit",
        "conditional_result": "failed",
    },
    "transient_error": {
        "observed_at": NOW.isoformat(),
        "reason": "network_error",
        "conditional_result": "failed",
    },
    "malformed": {
        "observed_at": NOW.isoformat(),
        "http_status": 200,
        "reason": "non_list_or_invalid_alert_payload",
        "conditional_result": "malformed",
    },
    "stale": {
        "observed_at": NOW.isoformat(),
        "http_status": 200,
        "reason": "receipt_stale",
        "pagination_complete": True,
    },
}


@pytest.mark.parametrize("state", sorted(PROVIDER_STATES))
def test_normalized_provider_state_fixture_matches_production_constructor(
    state: str,
) -> None:
    assert set(NORMALIZED_PROVIDER_STATE_FIXTURES) == set(PROVIDER_STATES)
    provider_name = "code_scanning" if state == "feature_unavailable" else "dependabot"
    provider = _provider_result(
        provider_name,
        state=state,
        **NORMALIZED_PROVIDER_STATE_FIXTURES[state],
    )

    assert validate_normalized_security_provider(provider_name, provider) == provider


@pytest.mark.parametrize(
    ("provider", "state", "kwargs"),
    (
        *(
            ("dependabot", "not_requested", {"reason": reason})
            for reason in (
                "authentication_missing",
                "base_request_limit",
                "collection_halted",
                "fixture_not_requested",
                "quota_reserve",
                "rate_limited",
                "total_request_limit",
            )
        ),
        (
            "dependabot",
            "not_requested",
            {
                "observed_at": NOW.isoformat(),
                "reason": "quota_reserve_before_pagination_complete",
                "conditional_request": True,
                "conditional_result": "incomplete",
            },
        ),
        (
            "dependabot",
            "credential_unavailable",
            {
                "observed_at": NOW.isoformat(),
                "http_status": 401,
                "reason": "github_authentication_missing",
                "conditional_result": "failed",
            },
        ),
        (
            "dependabot",
            "forbidden",
            {
                "observed_at": NOW.isoformat(),
                "http_status": 403,
                "reason": "github_forbidden",
                "conditional_result": "failed",
            },
        ),
        (
            "code_scanning",
            "feature_unavailable",
            {
                "observed_at": NOW.isoformat(),
                "http_status": 403,
                "reason": "code_scanning_not_enabled",
                "conditional_result": "failed",
            },
        ),
        (
            "secret_scanning",
            "feature_unavailable",
            {
                "observed_at": NOW.isoformat(),
                "http_status": 200,
                "http_classification": "eligibility",
                "reason": "private_user_repo_plan_unavailable",
            },
        ),
        (
            "dependabot",
            "not_found",
            {
                "observed_at": NOW.isoformat(),
                "http_status": 404,
                "reason": "github_not_found",
                "conditional_result": "failed",
            },
        ),
        (
            "dependabot",
            "gone",
            {
                "observed_at": NOW.isoformat(),
                "http_status": 410,
                "reason": "github_gone",
                "conditional_result": "failed",
            },
        ),
        *(
            (
                "dependabot",
                "rate_limited",
                {
                    "observed_at": NOW.isoformat(),
                    "http_status": status,
                    "reason": "github_rate_limit",
                    "conditional_result": "failed",
                },
            )
            for status in (403, 429)
        ),
        (
            "dependabot",
            "transient_error",
            {
                "observed_at": NOW.isoformat(),
                "reason": "network_error",
                "conditional_result": "failed",
            },
        ),
        (
            "dependabot",
            "transient_error",
            {
                "observed_at": NOW.isoformat(),
                "http_status": 503,
                "reason": "github_http_503",
                "conditional_result": "failed",
            },
        ),
        (
            "dependabot",
            "malformed",
            {
                "observed_at": NOW.isoformat(),
                "http_status": 304,
                "reason": "conditional_response_without_observed_prior",
                "conditional_request": True,
                "conditional_result": "invalid_prior",
            },
        ),
        (
            "dependabot",
            "malformed",
            {
                "observed_at": NOW.isoformat(),
                "http_status": 418,
                "reason": "unexpected_http_418",
                "conditional_result": "failed",
            },
        ),
    ),
)
def test_production_provider_reason_matrix_is_constructor_validated(
    provider: str,
    state: str,
    kwargs: dict[str, Any],
) -> None:
    result = _provider_result(provider, state=state, **kwargs)

    assert validate_normalized_security_provider(provider, result) == result


def test_provider_rejects_coherently_fabricated_failure_reason() -> None:
    provider = _provider_result(
        "code_scanning",
        state="not_found",
        observed_at=NOW.isoformat(),
        http_status=404,
        reason="github_not_found",
        conditional_result="failed",
    )
    provider["reason"] = "fabricated_reason"
    provider["http_classification"] = "fabricated_reason"

    with pytest.raises(SecurityCoverageError, match="producer reason domain"):
        validate_normalized_security_provider("code_scanning", provider)


@pytest.mark.parametrize(
    ("state", "mutation", "message"),
    (
        (
            "not_found",
            lambda value: value.update(
                http_status=200,
                http_classification="success",
            ),
            "not_found requires HTTP 404",
        ),
        (
            "not_found",
            lambda value: value.pop("conditional"),
            "missing fields",
        ),
        (
            "stale",
            lambda value: value.update(observed_at=None),
            "observed_at is required",
        ),
        (
            "not_found",
            lambda value: value.update(observed_at="not-a-timestamp"),
            "observed_at is invalid",
        ),
        (
            "not_found",
            lambda value: value.update(http_classification="success"),
            "http_classification",
        ),
        (
            "not_found",
            lambda value: value.update(pagination_complete=True),
            "cannot claim complete pagination",
        ),
    ),
)
def test_normalized_provider_state_machine_rejects_impossible_envelopes(
    state: str,
    mutation: Any,
    message: str,
) -> None:
    provider = _provider_result(
        "dependabot",
        state=state,
        **NORMALIZED_PROVIDER_STATE_FIXTURES[state],
    )
    tampered = deepcopy(provider)
    mutation(tampered)

    with pytest.raises(SecurityCoverageError, match=message):
        validate_normalized_security_provider("dependabot", tampered)


def test_normalized_provider_freshness_honors_configured_window() -> None:
    observed_at = NOW - timedelta(hours=30)
    observed = _provider_result(
        "dependabot",
        state="observed",
        observed_at=observed_at.isoformat(),
        http_status=200,
        pagination_complete=True,
        counts={"critical": 0, "high": 0, "medium": 0, "low": 0},
    )

    assert validate_normalized_security_provider(
        "dependabot",
        observed,
        produced_at=observed_at,
        current=NOW,
        max_age_hours=48,
    ) == observed
    with pytest.raises(SecurityCoverageError, match="freshness window"):
        validate_normalized_security_provider(
            "dependabot",
            observed,
            produced_at=observed_at,
            current=NOW,
            max_age_hours=24,
        )


def test_normalized_stale_provider_requires_receipt_or_provider_age() -> None:
    recent_stale = _provider_result(
        "dependabot",
        state="stale",
        observed_at=NOW.isoformat(),
        http_status=200,
        pagination_complete=True,
        reason="receipt_stale",
    )
    old_stale = deepcopy(recent_stale)
    old_stale["observed_at"] = (NOW - timedelta(hours=30)).isoformat()

    assert validate_normalized_security_provider(
        "dependabot",
        recent_stale,
        produced_at=NOW,
        current=NOW,
        max_age_hours=24,
        receipt_is_stale=True,
    ) == recent_stale
    assert validate_normalized_security_provider(
        "dependabot",
        old_stale,
        produced_at=NOW,
        current=NOW,
        max_age_hours=24,
    ) == old_stale
    with pytest.raises(SecurityCoverageError, match="not justified"):
        validate_normalized_security_provider(
            "dependabot",
            recent_stale,
            produced_at=NOW,
            current=NOW,
            max_age_hours=24,
        )


def test_normalized_unavailable_provider_preserves_old_observation() -> None:
    unavailable = _provider_result(
        "dependabot",
        state="not_found",
        observed_at=(NOW - timedelta(hours=30)).isoformat(),
        http_status=404,
        reason="github_not_found",
        conditional_result="failed",
    )

    assert validate_normalized_security_provider(
        "dependabot",
        unavailable,
        produced_at=NOW,
        current=NOW,
        max_age_hours=24,
    ) == unavailable


def _truth(count: int = 16) -> dict[str, Any]:
    attention = ("active-product", "active-infra", "decision-needed")
    projects = [
        {
            "identity": {"repo_full_name": f"owner/repo-{index:02d}"},
            "derived": {"attention_state": attention[index % len(attention)]},
        }
        for index in range(count)
    ]
    projects.append(
        {
            "identity": {"repo_full_name": "owner/parked"},
            "derived": {"attention_state": "parked"},
        }
    )
    return {"projects": projects}


class _Response:
    def __init__(
        self,
        status_code: int = 200,
        payload: Any = None,
        *,
        headers: dict[str, str] | None = None,
        next_url: str | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = [] if payload is None else payload
        self.headers = headers or {"X-RateLimit-Remaining": "4000"}
        self.links = {"next": {"url": next_url}} if next_url else {}

    def json(self) -> Any:
        return self._payload


class _Session:
    def __init__(self, responses: list[_Response] | None = None) -> None:
        self.headers: dict[str, str] = {}
        self.responses = list(responses or [])
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, url: str, **kwargs: Any) -> _Response:
        self.calls.append((url, kwargs))
        if self.responses:
            return self.responses.pop(0)
        return _Response()

    def post(self, url: str, **kwargs: Any) -> _Response:
        self.calls.append((url, kwargs))
        if self.responses:
            return self.responses.pop(0)
        return _Response()


def _collect(
    *,
    session: _Session | None = None,
    prior: dict[str, Any] | None = None,
    cohort_count: int = 16,
) -> dict[str, Any]:
    return collect_security_coverage(
        _truth(cohort_count),
        token="opaque-test-token",
        expected_cohort_count=cohort_count,
        session=session or _Session(),
        prior_receipt=prior,
        now=NOW,
        producer_commit="a" * 40,
        api_base_url="https://api.example.test",
    )


def _assert_binding_revalidation_fails_in_child(
    binding: Any,
    *,
    expected: str,
) -> None:
    script = """
import json
import sys

from src.github_security_coverage import (
    SecurityCoverageError,
    SecurityCoverageReceiptBinding,
    verified_security_coverage_receipt_binding,
)

binding = SecurityCoverageReceiptBinding(**json.loads(sys.stdin.read()))
try:
    with verified_security_coverage_receipt_binding(binding):
        pass
except SecurityCoverageError as exc:
    print(str(exc))
    raise SystemExit(0)
raise SystemExit("binding unexpectedly revalidated")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        input=json.dumps(binding.__dict__),
        text=True,
        capture_output=True,
        cwd=Path(__file__).resolve().parents[1],
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert expected in result.stdout


def _prior_with_private_unavailable(count: int = 6) -> dict[str, Any]:
    prior = _collect()
    for index in range(count):
        providers = prior["repositories"][f"owner/repo-{index:02d}"]["providers"]
        providers["code_scanning"] = {
            "state": "feature_unavailable",
            "observed_at": NOW.isoformat(),
            "http_status": 403,
            "http_classification": "code_scanning_not_enabled",
            "reason": "code_scanning_not_enabled",
            "etag": None,
            "last_modified": None,
            "conditional": {"requested": False, "result": "failed"},
            "pagination_complete": False,
            "counts": None,
        }
        providers["secret_scanning"] = {
            "state": "not_found",
            "observed_at": NOW.isoformat(),
            "http_status": 404,
            "http_classification": "github_not_found",
            "reason": "github_not_found",
            "etag": None,
            "last_modified": None,
            "conditional": {"requested": False, "result": "failed"},
            "pagination_complete": False,
            "counts": None,
        }
    return prior


def _eligibility_responses(count: int = 6) -> list[_Response]:
    repositories = {
        f"repo{index}": {
            "nameWithOwner": f"owner/repo-{index:02d}",
            "visibility": "PRIVATE",
            "owner": {"__typename": "User", "login": "owner"},
        }
        for index in range(count)
    }
    return [
        _Response(200, {"login": "owner", "plan": {"name": "pro"}}),
        _Response(200, {"data": repositories}),
    ]


def _remote_graphql_response(count: int) -> _Response:
    repositories = {
        f"repo{index}": {
            "nameWithOwner": f"owner/repo-{index:02d}",
            "isArchived": False,
            "defaultBranchRef": {
                "name": "main",
                "target": {"oid": f"{index + 1:040x}"},
            },
        }
        for index in range(count)
    }
    return _Response(200, {"data": repositories})


def test_default_attention_cohort_is_exact_and_fail_closed() -> None:
    truth = _truth(DEFAULT_EXPECTED_GITHUB_COHORT_COUNT)
    truth["projects"].append(
        {
            "identity": {
                "project_key": "supp:personal-ops",
                "repo_full_name": "",
            },
            "derived": {"attention_state": "active-infra"},
        }
    )
    cohort = derive_default_attention_cohort(truth)

    assert len(cohort) == DEFAULT_EXPECTED_GITHUB_COHORT_COUNT
    assert "owner/parked" not in cohort
    with pytest.raises(SecurityCoverageError, match="expected 9, observed 10"):
        derive_default_attention_cohort(_truth(10))


def test_repo_less_non_supplementary_attention_identity_fails_closed() -> None:
    truth = _truth(DEFAULT_EXPECTED_GITHUB_COHORT_COUNT)
    truth["projects"].append(
        {
            "identity": {"project_key": "repo:missing", "repo_full_name": ""},
            "derived": {"attention_state": "active-infra"},
        }
    )

    with pytest.raises(
        SecurityCoverageError, match="invalid canonical repository name"
    ):
        derive_default_attention_cohort(truth)


def test_no_token_writes_exact_fail_closed_outcomes_without_network() -> None:
    session = _Session()

    receipt = collect_security_coverage(
        _truth(DEFAULT_EXPECTED_GITHUB_COHORT_COUNT),
        token=None,
        session=session,
        now=NOW,
        producer_commit="a" * 40,
    )

    assert session.calls == []
    expected = OUTCOME_FIXTURES["authentication_missing"]
    for repository in receipt["repositories"].values():
        assert repository["repository"]["state"] == expected["state"]
        assert repository["repository"]["reason_code"] == expected["reason_code"]
        for provider in repository["providers"].values():
            assert provider["state"] == expected["state"]
            assert provider["reason_code"] == expected["reason_code"]
            assert provider["completed"] is False
            assert provider["zero_findings"] is None


def test_rejected_token_stops_after_first_request_and_marks_whole_cut_unknown() -> None:
    session = _Session([_Response(401, {"message": "Bad credentials"})])

    receipt = _collect(session=session)

    assert len(session.calls) == 1
    assert receipt["request_budget"]["stop_reason"] == "authentication_missing"
    assert all(
        repository["repository"]["reason_code"] == "authentication_missing"
        and all(
            provider["reason_code"] == "authentication_missing"
            for provider in repository["providers"].values()
        )
        for repository in receipt["repositories"].values()
    )


def test_valid_prior_for_old_cohort_is_ignored_during_contraction() -> None:
    old_prior = _collect(cohort_count=16)
    session = _Session()

    receipt = _collect(
        session=session,
        prior=old_prior,
        cohort_count=DEFAULT_EXPECTED_GITHUB_COHORT_COUNT,
    )

    assert receipt["cohort"]["repository_count"] == 9
    assert len(session.calls) == 28
    assert all(
        kwargs.get("headers") == {}
        for _, kwargs in session.calls[:27]
    )
    assert "headers" not in session.calls[27][1]


def test_invalid_prior_for_old_cohort_still_fails_closed() -> None:
    old_prior = _collect(cohort_count=16)
    old_prior["producer"]["commit"] = "invalid"

    with pytest.raises(SecurityCoverageError, match="producer commit"):
        _collect(
            prior=old_prior,
            cohort_count=DEFAULT_EXPECTED_GITHUB_COHORT_COUNT,
        )


def test_validate_only_requires_no_token_or_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    receipt = _collect()
    path = tmp_path / GITHUB_SECURITY_RECEIPT_FILENAME
    path.write_text(json.dumps(receipt))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "github_security_coverage",
            "--validate-only",
            "--output",
            str(path),
            "--max-age-hours",
            "24",
            "--expected-cohort-count",
            "16",
        ],
    )

    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "validated"
    assert payload["cohort_count"] == 16


def test_collector_is_serial_count_only_and_bounded_to_48_base_requests() -> None:
    session = _Session()

    receipt = _collect(session=session)

    assert len(session.calls) == DEFAULT_BASE_REQUEST_LIMIT == 48
    assert receipt["request_budget"]["base_requests"] == 48
    assert receipt["request_budget"]["total_requests"] == 48
    assert receipt["request_budget"]["stop_reason"] == "base_request_limit"
    assert all("/alerts/" not in url for url, _ in session.calls)
    for repository in receipt["repositories"].values():
        for provider in repository["providers"].values():
            assert provider["state"] == "observed"
            assert provider["counts"] is not None
            assert provider["pagination_complete"] is True
            assert provider["completed"] is True
            assert provider["zero_findings"] is True
    assert all(
        repository["repository"]["state"] == "not_requested"
        for repository in receipt["repositories"].values()
    )


def test_current_nine_repository_cut_binds_remote_branch_and_head() -> None:
    session = _Session(
        [
            *[_Response() for _ in range(27)],
            _remote_graphql_response(DEFAULT_EXPECTED_GITHUB_COHORT_COUNT),
        ]
    )
    receipt = _collect(
        session=session,
        cohort_count=DEFAULT_EXPECTED_GITHUB_COHORT_COUNT,
    )

    assert len(session.calls) == 28
    assert receipt["request_budget"]["stop_reason"] is None
    assert all(
        repository["repository"]["state"] == "observed"
        and repository["repository"]["reason_code"] == "observed"
        and repository["repository"]["default_branch"] == "main"
        and len(repository["repository"]["head_sha"]) == 40
        for repository in receipt["repositories"].values()
    )


@pytest.mark.parametrize(
    ("branch", "head_sha"),
    (("main", "a" * 40), ("feature/release-1.2", "b" * 64), ("@", "c" * 40)),
)
def test_remote_repository_accepts_canonical_git_tokens(
    branch: str,
    head_sha: str,
) -> None:
    receipt = _collect()
    receipt["repositories"]["owner/repo-00"]["repository"] = (
        _remote_repository_result(
            state="observed",
            observed_at=NOW.isoformat(),
            default_branch=branch,
            head_sha=head_sha,
            archived=False,
        )
    )

    loaded = validate_security_coverage_receipt(
        receipt,
        expected_cohort_count=16,
        now=NOW,
    )

    assert (
        loaded.entries_by_full_name["owner/repo-00"]["repository"]["head_sha"]
        == head_sha
    )


@pytest.mark.parametrize(
    ("state", "reason"),
    (
        ("partial", "default_branch_head_unavailable"),
        ("not_requested", "authentication_missing"),
        ("not_requested", "base_request_limit"),
        ("not_requested", "quota_reserve"),
        ("not_requested", "rate_limited"),
        ("not_requested", "remote_observation_not_in_receipt"),
        ("not_requested", "total_request_limit"),
        ("credential_unavailable", "github_authentication_missing"),
        ("credential_unavailable", "github_graphql_authentication_missing"),
        ("forbidden", "github_forbidden"),
        ("forbidden", "github_graphql_forbidden"),
        ("not_found", "github_graphql_repository_not_found"),
        ("not_found", "repository_not_returned"),
        ("rate_limited", "github_graphql_rate_limited"),
        ("rate_limited", "github_rate_limit"),
        ("transient_error", "network_error"),
        ("transient_error", "github_http_503"),
        ("malformed", "github_gone"),
        ("malformed", "github_graphql_error"),
        ("malformed", "github_not_found"),
        ("malformed", "non_object_payload"),
        ("malformed", "repository_archived_state_invalid"),
        ("malformed", "repository_identity_mismatch"),
        ("malformed", "unexpected_http_418"),
        ("stale", "receipt_stale"),
    ),
)
def test_production_remote_reason_matrix_is_constructor_validated(
    state: str,
    reason: str,
) -> None:
    result = _remote_repository_result(
        state=state,
        reason=reason,
        observed_at=NOW.isoformat() if state != "not_requested" else None,
        archived=False if state == "partial" else None,
    )

    assert result["reason"] == reason


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("head_sha", "a" * 41, "head_sha"),
        ("head_sha", "0" * 40, "head_sha"),
        ("head_sha", "A" * 40, "head_sha"),
        ("default_branch", "has space", "default_branch"),
        ("default_branch", "main.lock", "default_branch"),
        ("default_branch", "feature..topic", "default_branch"),
        ("default_branch", "HEAD", "default_branch"),
    ),
)
def test_remote_repository_rejects_impossible_git_tokens(
    field: str,
    value: str,
    message: str,
) -> None:
    receipt = _collect()
    repository = _remote_repository_result(
        state="observed",
        observed_at=NOW.isoformat(),
        default_branch="main",
        head_sha="a" * 40,
        archived=False,
    )
    repository[field] = value
    receipt["repositories"]["owner/repo-00"]["repository"] = repository

    with pytest.raises(SecurityCoverageError, match=message):
        validate_security_coverage_receipt(
            receipt,
            expected_cohort_count=16,
            now=NOW,
        )


@pytest.mark.parametrize(
    "branch",
    (
        "main",
        "feature/topic",
        "release-1.2",
        "@",
        "HEAD",
        "-topic",
        ".hidden",
        "feature/.hidden",
        "main.lock",
        "feature..topic",
        "feature@{topic",
        "feature//topic",
        "feature/topic.",
        "has space",
        "feature\\topic",
    ),
)
def test_shared_branch_validator_matches_git_check_ref_format(branch: str) -> None:
    git_accepts = subprocess.run(
        ["git", "check-ref-format", "--branch", branch],
        check=False,
        capture_output=True,
        text=True,
    ).returncode == 0

    assert _valid_git_branch(branch) is git_accepts


@pytest.mark.parametrize(
    "upstream",
    (
        "origin/main",
        "upstream/feature/topic",
        "@/main",
        "bad~remote/main",
        "../main",
        "origin/main.lock",
        "origin/has space",
        "origin/feature..topic",
    ),
)
def test_shared_upstream_validator_matches_git_ref_format(upstream: str) -> None:
    git_accepts = subprocess.run(
        ["git", "check-ref-format", f"refs/remotes/{upstream}"],
        check=False,
        capture_output=True,
        text=True,
    ).returncode == 0

    assert _valid_git_upstream(upstream) is git_accepts


def test_graphql_rate_limit_marks_remote_cut_with_exact_reason_code() -> None:
    outcome = OUTCOME_FIXTURES["rate_limited"]
    session = _Session(
        [
            *[_Response() for _ in range(27)],
            _Response(
                200,
                {
                    "data": None,
                    "errors": [{"message": outcome["message"]}],
                },
            ),
        ]
    )

    receipt = _collect(
        session=session,
        cohort_count=DEFAULT_EXPECTED_GITHUB_COHORT_COUNT,
    )

    assert receipt["request_budget"]["stop_reason"] == "rate_limited"
    assert all(
        repository["repository"]["state"] == "rate_limited"
        and repository["repository"]["reason_code"] == outcome["reason_code"]
        for repository in receipt["repositories"].values()
    )


def test_incremental_eligibility_preflight_skips_plan_blocked_providers() -> None:
    prior = _prior_with_private_unavailable()
    session = _Session([*_eligibility_responses(), *[_Response() for _ in range(36)]])

    receipt = _collect(session=session, prior=prior)

    assert len(session.calls) == 39
    assert receipt["request_budget"]["base_requests"] == 39
    assert receipt["request_budget"]["total_requests"] == 39
    assert receipt["request_budget"]["stop_reason"] is None
    assert receipt["eligibility"]["state"] == "observed"
    assert receipt["eligibility"]["request_count"] == 2
    assert len(receipt["eligibility"]["candidate_repositories"]) == 6
    called_urls = [url for url, _ in session.calls]
    for index in range(6):
        repo = f"owner/repo-{index:02d}"
        assert (
            f"https://api.example.test/repos/{repo}/code-scanning/alerts"
            not in called_urls
        )
        assert (
            f"https://api.example.test/repos/{repo}/secret-scanning/alerts"
            not in called_urls
        )
        providers = receipt["repositories"][repo]["providers"]
        for provider in ("code_scanning", "secret_scanning"):
            assert providers[provider]["state"] == "feature_unavailable"
            assert providers[provider]["reason"] == (
                "private_user_repo_plan_unavailable"
            )
            assert providers[provider]["http_status"] == 200
            assert providers[provider]["http_classification"] == "eligibility"
            assert providers[provider]["counts"] is None
    validate_security_coverage_receipt(
        receipt, expected_cohort_count=16, now=NOW
    )


def test_eligibility_claim_requires_matching_embedded_provenance() -> None:
    prior = _prior_with_private_unavailable()
    session = _Session([*_eligibility_responses(), *[_Response() for _ in range(36)]])
    receipt = _collect(session=session, prior=prior)
    receipt["eligibility"]["repositories"]["owner/repo-00"][
        "unavailable_providers"
    ] = []

    with pytest.raises(
        SecurityCoverageError,
        match="eligibility-based unavailability is unproven",
    ):
        validate_security_coverage_receipt(
            receipt, expected_cohort_count=16, now=NOW
        )


def test_malformed_eligibility_preflight_falls_back_without_exceeding_budget() -> None:
    prior = _prior_with_private_unavailable()
    session = _Session(
        [
            _Response(200, {"login": "owner", "plan": {"name": "pro"}}),
            _Response(200, {"errors": [{"message": "unavailable"}]}),
            *[_Response() for _ in range(46)],
        ]
    )

    receipt = _collect(session=session, prior=prior)
    states = [
        provider["state"]
        for repository in receipt["repositories"].values()
        for provider in repository["providers"].values()
    ]

    assert len(session.calls) == 48
    assert receipt["eligibility"]["state"] == "malformed"
    assert receipt["request_budget"]["base_requests"] == 48
    assert receipt["request_budget"]["stop_reason"] == "base_request_limit"
    assert states.count("observed") == 46
    assert states.count("not_requested") == 2
    assert states.count("feature_unavailable") == 0


def test_rate_limited_eligibility_preflight_stops_before_provider_calls() -> None:
    prior = _prior_with_private_unavailable()
    session = _Session(
        [
            _Response(
                403,
                {"message": "API rate limit exceeded"},
                headers={"X-RateLimit-Remaining": "0"},
            )
        ]
    )

    receipt = _collect(session=session, prior=prior)
    states = [
        provider["state"]
        for repository in receipt["repositories"].values()
        for provider in repository["providers"].values()
    ]

    assert len(session.calls) == 1
    assert receipt["eligibility"]["state"] == "rate_limited"
    assert receipt["request_budget"]["stop_reason"] == "rate_limited"
    assert states == ["not_requested"] * 48


@pytest.mark.parametrize(
    "limits",
    [
        {"base_request_limit": 49},
        {"total_request_limit": 76},
        {"base_request_limit": 48, "total_request_limit": 47},
        {"quota_reserve": -1},
    ],
)
def test_collector_rejects_relaxed_request_bounds_before_network(
    limits: dict[str, int],
) -> None:
    session = _Session()

    with pytest.raises(SecurityCoverageError, match="bounded contract"):
        collect_security_coverage(
            _truth(),
            token="opaque-test-token",
            session=session,
            producer_commit="a" * 40,
            **limits,
        )

    assert session.calls == []


def test_rate_limit_stops_immediately_and_leaves_remainder_not_requested() -> None:
    outcome = OUTCOME_FIXTURES["rate_limited"]
    session = _Session(
        [
            _Response(
                outcome["status_code"],
                {"message": outcome["message"]},
                headers={"X-RateLimit-Remaining": outcome["remaining"]},
            )
        ]
    )

    receipt = _collect(session=session)
    states = [
        provider["state"]
        for repository in receipt["repositories"].values()
        for provider in repository["providers"].values()
    ]

    assert len(session.calls) == 1
    assert states.count("rate_limited") == 1
    assert states.count("not_requested") == 47
    assert receipt["request_budget"]["stop_reason"] == "rate_limited"
    first = receipt["repositories"]["owner/repo-00"]["providers"]["dependabot"]
    assert first["reason_code"] == outcome["reason_code"]
    assert first["completed"] is False
    assert first["zero_findings"] is None


def test_quota_reserve_stops_before_following_request() -> None:
    session = _Session([_Response(headers={"X-RateLimit-Remaining": "100"})])

    receipt = _collect(session=session)
    states = [
        provider["state"]
        for repository in receipt["repositories"].values()
        for provider in repository["providers"].values()
    ]

    assert len(session.calls) == 1
    assert states.count("observed") == 1
    assert states.count("not_requested") == 47
    assert receipt["request_budget"]["stop_reason"] == "quota_reserve"


def test_total_request_ceiling_halts_incomplete_pagination() -> None:
    session = _Session(
        [
            _Response(next_url=f"https://api.example.test/page/{index + 1}")
            for index in range(75)
        ]
    )

    receipt = _collect(session=session)
    first = receipt["repositories"]["owner/repo-00"]["providers"]["dependabot"]

    assert len(session.calls) == 75
    assert receipt["request_budget"]["total_requests"] == 75
    assert receipt["request_budget"]["stop_reason"] == "total_request_limit"
    assert first["state"] == "not_requested"
    assert first["counts"] is None


def test_forbidden_and_feature_unavailable_are_distinct() -> None:
    outcome = OUTCOME_FIXTURES["partial_coverage"]
    session = _Session(
        [
            _Response(outcome["status_code"], {"message": outcome["message"]}),
            _Response(403, {"message": "Advanced Security must be enabled"}),
        ]
    )

    receipt = _collect(session=session)
    first = receipt["repositories"]["owner/repo-00"]["providers"]

    assert first["dependabot"]["state"] == "forbidden"
    assert first["dependabot"]["reason_code"] == outcome["reason_code"]
    assert first["dependabot"]["completed"] is False
    assert first["dependabot"]["zero_findings"] is None
    assert first["dependabot"]["counts"] is None
    assert first["code_scanning"]["state"] == "feature_unavailable"
    assert first["code_scanning"]["reason_code"] == "provider_unavailable"
    assert first["code_scanning"]["counts"] is None


def test_malformed_provider_payload_has_exact_fail_closed_reason_code() -> None:
    outcome = OUTCOME_FIXTURES["malformed_provider_data"]
    session = _Session([_Response(200, outcome["payload"])])

    receipt = _collect(session=session)
    provider = receipt["repositories"]["owner/repo-00"]["providers"]["dependabot"]

    assert provider["state"] == "malformed"
    assert provider["reason_code"] == outcome["reason_code"]
    assert provider["completed"] is False
    assert provider["zero_findings"] is None


def test_conditional_304_reuses_only_valid_prior_counts() -> None:
    prior = _collect()
    for repository in prior["repositories"].values():
        for provider in repository["providers"].values():
            provider["etag"] = '"stable"'
    session = _Session(
        [_Response(304, headers={"ETag": '"stable"'}) for _ in range(48)]
    )

    receipt = _collect(session=session, prior=prior)

    assert len(session.calls) == 48
    assert all(
        kwargs["headers"] == {"If-None-Match": '"stable"'}
        for _, kwargs in session.calls
    )
    assert all(
        provider["http_status"] == 304 and provider["state"] == "observed"
        for repository in receipt["repositories"].values()
        for provider in repository["providers"].values()
    )


def test_stale_provider_observation_becomes_unknown_count() -> None:
    outcome = OUTCOME_FIXTURES["stale_observation"]
    receipt = _collect()
    receipt["produced_at"] = NOW.isoformat()
    provider = receipt["repositories"]["owner/repo-00"]["providers"]["dependabot"]
    provider["observed_at"] = (
        NOW - timedelta(hours=outcome["age_hours"])
    ).isoformat()

    loaded = validate_security_coverage_receipt(
        receipt, expected_cohort_count=16, now=NOW
    )
    normalized = loaded.entries_by_full_name["owner/repo-00"]["providers"]["dependabot"]

    assert normalized["state"] == "stale"
    assert normalized["reason_code"] == outcome["reason_code"]
    assert normalized["completed"] is False
    assert normalized["zero_findings"] is None
    assert normalized["counts"] is None


def test_successful_empty_provider_response_is_explicit_completed_zero() -> None:
    outcome = OUTCOME_FIXTURES["successful_zero_findings"]
    receipt = _collect(session=_Session([_Response(200, outcome["payload"])]))
    provider = receipt["repositories"]["owner/repo-00"]["providers"]["dependabot"]

    assert provider["state"] == "observed"
    assert provider["reason_code"] == outcome["reason_code"]
    assert provider["completed"] is True
    assert provider["zero_findings"] is outcome["zero_findings"]
    assert provider["counts"] == {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
    }


def test_receipt_loader_uses_embedded_provenance_not_newer_mtime(
    tmp_path: Path,
) -> None:
    receipt = _collect(cohort_count=DEFAULT_EXPECTED_GITHUB_COHORT_COUNT)
    canonical = tmp_path / GITHUB_SECURITY_RECEIPT_FILENAME
    canonical.write_text(json.dumps(receipt))
    decoy = tmp_path / "github-security-coverage-newer.json"
    decoy.write_text(json.dumps({"schema_version": "forged"}))
    decoy.touch()

    loaded = load_security_coverage_by_full_name(output_dir=tmp_path, now=NOW)

    assert loaded is not None
    assert loaded.source_path == str(canonical)
    assert (
        len(loaded.entries_by_full_name)
        == DEFAULT_EXPECTED_GITHUB_COHORT_COUNT
    )


def test_written_receipt_binds_semantic_identity_and_exact_bytes(
    tmp_path: Path,
) -> None:
    receipt = _collect(cohort_count=DEFAULT_EXPECTED_GITHUB_COHORT_COUNT)
    canonical = tmp_path / GITHUB_SECURITY_RECEIPT_FILENAME

    written = write_security_coverage_receipt(receipt, canonical)
    loaded = load_security_coverage_receipt(canonical, now=NOW)

    assert written.receipt_id == loaded.receipt_id
    assert written.content_sha256 == loaded.content_sha256
    assert written.receipt_id is not None
    assert written.receipt_id.startswith("sha256:")
    assert written.content_sha256 is not None
    assert len(written.content_sha256) == 64
    assert json.loads(canonical.read_text())["receipt_id"] == written.receipt_id
    assert canonical.with_name(f".{canonical.name}.lock").is_file()


def test_collector_cli_holds_writer_intent_before_truth_read_and_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truth_path = tmp_path / "portfolio-truth-latest.json"
    receipt_path = tmp_path / GITHUB_SECURITY_RECEIPT_FILENAME
    truth = _truth(DEFAULT_EXPECTED_GITHUB_COHORT_COUNT)
    truth_path.write_text(json.dumps(truth))
    first = _collect(cohort_count=DEFAULT_EXPECTED_GITHUB_COHORT_COUNT)
    write_security_coverage_receipt(first, receipt_path)
    binding = load_security_coverage_receipt(receipt_path, now=NOW).binding()
    second = collect_security_coverage(
        truth,
        token="opaque-test-token",
        expected_cohort_count=DEFAULT_EXPECTED_GITHUB_COHORT_COUNT,
        session=_Session(),
        now=NOW + timedelta(minutes=1),
        producer_commit="a" * 40,
        api_base_url="https://api.example.test",
    )
    observed: dict[str, object] = {}
    from src import github_security_coverage as coverage_module

    original_load_json_object = coverage_module._load_json_object

    def load_json_with_truth_read_probe(path: Path) -> dict[str, Any]:
        if path == truth_path:
            _assert_binding_revalidation_fails_in_child(
                binding,
                expected="security coverage receipt collection is active",
            )
            observed["publisher_blocked_during_truth_read"] = True
        return original_load_json_object(path)

    def fake_collect_security_coverage(
        _truth_payload: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        prior_receipt = kwargs["prior_receipt"]
        assert prior_receipt is not None
        observed["prior_receipt_id"] = prior_receipt["receipt_id"]
        _assert_binding_revalidation_fails_in_child(
            binding,
            expected="security coverage receipt collection is active",
        )
        observed["publisher_blocked_during_collection"] = True
        return second

    monkeypatch.setattr(
        "src.github_security_coverage._load_json_object",
        load_json_with_truth_read_probe,
    )
    monkeypatch.setattr(
        "src.github_security_coverage.collect_security_coverage",
        fake_collect_security_coverage,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "github-security-coverage",
            "--truth",
            str(truth_path),
            "--output",
            str(receipt_path),
            "--expected-cohort-count",
            str(DEFAULT_EXPECTED_GITHUB_COHORT_COUNT),
        ],
    )

    main()
    loaded = load_security_coverage_receipt(receipt_path, now=NOW + timedelta(minutes=1))

    assert observed == {
        "publisher_blocked_during_truth_read": True,
        "prior_receipt_id": binding.receipt_id,
        "publisher_blocked_during_collection": True,
    }
    assert loaded.receipt_id != binding.receipt_id


def test_writer_intent_interruption_does_not_leave_stale_lock(
    tmp_path: Path,
) -> None:
    receipt = _collect(cohort_count=DEFAULT_EXPECTED_GITHUB_COHORT_COUNT)
    canonical = tmp_path / GITHUB_SECURITY_RECEIPT_FILENAME
    write_security_coverage_receipt(receipt, canonical)
    binding = load_security_coverage_receipt(
        canonical,
        max_age_hours=24 * 365,
        now=NOW,
    ).binding()

    with pytest.raises(RuntimeError, match="collector interrupted"):
        with security_coverage_receipt_writer(canonical):
            raise RuntimeError("collector interrupted")

    assert canonical.with_name(f".{canonical.name}.lock").is_file()
    with verified_security_coverage_receipt_binding(binding) as loaded:
        assert loaded.receipt_id == binding.receipt_id


def test_replacement_after_load_fails_bound_revalidation(tmp_path: Path) -> None:
    canonical = tmp_path / GITHUB_SECURITY_RECEIPT_FILENAME
    first = _collect(cohort_count=DEFAULT_EXPECTED_GITHUB_COHORT_COUNT)
    write_security_coverage_receipt(first, canonical)
    binding = load_security_coverage_receipt(canonical, now=NOW).binding()

    second = collect_security_coverage(
        _truth(DEFAULT_EXPECTED_GITHUB_COHORT_COUNT),
        token="opaque-test-token",
        expected_cohort_count=DEFAULT_EXPECTED_GITHUB_COHORT_COUNT,
        session=_Session(),
        now=NOW + timedelta(minutes=1),
        producer_commit="a" * 40,
        api_base_url="https://api.example.test",
    )
    write_security_coverage_receipt(second, canonical)

    with pytest.raises(SecurityCoverageError, match="changed after it was loaded"):
        with verified_security_coverage_receipt_binding(binding):
            pass


def test_byte_change_with_same_receipt_id_fails_bound_revalidation(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / GITHUB_SECURITY_RECEIPT_FILENAME
    write_security_coverage_receipt(
        _collect(cohort_count=DEFAULT_EXPECTED_GITHUB_COHORT_COUNT), canonical
    )
    binding = load_security_coverage_receipt(canonical, now=NOW).binding()
    payload = json.loads(canonical.read_text())
    canonical.write_text(json.dumps(payload, separators=(",", ":")))

    with pytest.raises(SecurityCoverageError, match="bytes changed"):
        with verified_security_coverage_receipt_binding(binding):
            pass


def test_legacy_receipt_remains_readable_but_cannot_authorize_publication(
    tmp_path: Path,
) -> None:
    legacy = _collect(cohort_count=DEFAULT_EXPECTED_GITHUB_COHORT_COUNT)
    canonical = tmp_path / GITHUB_SECURITY_RECEIPT_FILENAME
    canonical.write_text(json.dumps(legacy))

    loaded = load_security_coverage_receipt(canonical, now=NOW)

    assert loaded.receipt_id is None
    assert loaded.content_sha256 is not None
    with pytest.raises(SecurityCoverageError, match="missing immutable receipt_id"):
        loaded.binding()


def test_malformed_or_mismatched_receipt_identity_fails_closed() -> None:
    receipt = _collect()
    receipt["receipt_id"] = "sha256:" + "0" * 64

    with pytest.raises(SecurityCoverageError, match="does not match"):
        validate_security_coverage_receipt(
            receipt,
            expected_cohort_count=16,
            now=NOW,
        )


def test_receipt_loader_honors_explicit_nondefault_cohort_count(
    tmp_path: Path,
) -> None:
    receipt = _collect(cohort_count=3)
    canonical = tmp_path / GITHUB_SECURITY_RECEIPT_FILENAME
    canonical.write_text(json.dumps(receipt))

    assert load_security_coverage_by_full_name(output_dir=tmp_path, now=NOW) is None
    loaded = load_security_coverage_by_full_name(
        output_dir=tmp_path,
        expected_cohort_count=3,
        now=NOW,
    )

    assert loaded is not None
    assert len(loaded.cohort_repositories) == 3


def test_receipt_provenance_and_provider_timestamps_fail_closed(tmp_path: Path) -> None:
    receipt = _collect()
    receipt["producer"]["commit"] = "short"
    path = tmp_path / GITHUB_SECURITY_RECEIPT_FILENAME
    path.write_text(json.dumps(receipt))

    with pytest.raises(SecurityCoverageError, match="producer commit"):
        load_security_coverage_receipt(path, now=NOW)

    receipt = _collect()
    provider = receipt["repositories"]["owner/repo-00"]["providers"]["dependabot"]
    provider["observed_at"] = (NOW + timedelta(minutes=1)).isoformat()
    with pytest.raises(SecurityCoverageError, match="later than receipt produced_at"):
        validate_security_coverage_receipt(
            receipt, expected_cohort_count=16, now=NOW
        )


def test_receipt_producer_must_match_expected_canonical_commit() -> None:
    receipt = _collect()

    loaded = validate_security_coverage_receipt(
        receipt,
        expected_cohort_count=16,
        expected_producer_commit="a" * 40,
        now=NOW,
    )
    assert loaded.producer_commit == "a" * 40

    with pytest.raises(SecurityCoverageError, match="producer commit mismatch"):
        validate_security_coverage_receipt(
            receipt,
            expected_cohort_count=16,
            expected_producer_commit="b" * 40,
            now=NOW,
        )


def test_canonical_receipt_join_does_not_fall_back_to_repo_basename() -> None:
    entry = {
        "receipt_schema_version": "GitHubSecurityCoverageReceiptV1",
        "providers": {},
    }

    assert (
        _select_security_entry({"other/shared": entry}, "owner/shared", "shared")
        is None
    )
    assert (
        _select_security_entry(
            {"owner/shared": entry}, "owner/shared", "different display"
        )
        is entry
    )
