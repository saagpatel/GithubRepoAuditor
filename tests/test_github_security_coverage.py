from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from src.github_security_coverage import (
    DEFAULT_BASE_REQUEST_LIMIT,
    GITHUB_SECURITY_RECEIPT_FILENAME,
    SecurityCoverageError,
    collect_security_coverage,
    derive_default_attention_cohort,
    load_security_coverage_receipt,
    main,
    validate_security_coverage_receipt,
)
from src.portfolio_truth_reconcile import _select_security_entry
from src.portfolio_truth_status import load_security_coverage_by_full_name

NOW = datetime(2026, 7, 16, 12, tzinfo=timezone.utc)


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


def _collect(
    *,
    session: _Session | None = None,
    prior: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return collect_security_coverage(
        _truth(),
        token="opaque-test-token",
        session=session or _Session(),
        prior_receipt=prior,
        now=NOW,
        producer_commit="a" * 40,
        api_base_url="https://api.example.test",
    )


def test_default_attention_cohort_is_exact_and_fail_closed() -> None:
    cohort = derive_default_attention_cohort(_truth())

    assert len(cohort) == 16
    assert "owner/parked" not in cohort
    with pytest.raises(SecurityCoverageError, match="expected 16, observed 17"):
        derive_default_attention_cohort(_truth(17))


def test_no_token_never_attempts_collection() -> None:
    session = _Session()

    with pytest.raises(SecurityCoverageError, match="credential unavailable"):
        collect_security_coverage(_truth(), token=None, session=session)

    assert session.calls == []


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
    assert receipt["request_budget"]["stop_reason"] is None
    assert all("/alerts/" not in url for url, _ in session.calls)
    for repository in receipt["repositories"].values():
        for provider in repository["providers"].values():
            assert provider["state"] == "observed"
            assert provider["counts"] is not None
            assert provider["pagination_complete"] is True


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
    session = _Session(
        [
            _Response(
                403,
                {"message": "API rate limit exceeded"},
                headers={"X-RateLimit-Remaining": "0"},
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


def test_quota_reserve_stops_before_following_request() -> None:
    session = _Session(
        [_Response(headers={"X-RateLimit-Remaining": "100"})]
    )

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
    session = _Session(
        [
            _Response(403, {"message": "Resource not accessible by integration"}),
            _Response(403, {"message": "Advanced Security must be enabled"}),
        ]
    )

    receipt = _collect(session=session)
    first = receipt["repositories"]["owner/repo-00"]["providers"]

    assert first["dependabot"]["state"] == "forbidden"
    assert first["dependabot"]["counts"] is None
    assert first["code_scanning"]["state"] == "feature_unavailable"
    assert first["code_scanning"]["counts"] is None


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
    receipt = _collect()
    receipt["produced_at"] = NOW.isoformat()
    provider = receipt["repositories"]["owner/repo-00"]["providers"]["dependabot"]
    provider["observed_at"] = (NOW - timedelta(hours=25)).isoformat()

    loaded = validate_security_coverage_receipt(receipt, now=NOW)
    normalized = loaded.entries_by_full_name["owner/repo-00"]["providers"][
        "dependabot"
    ]

    assert normalized["state"] == "stale"
    assert normalized["counts"] is None


def test_receipt_loader_uses_embedded_provenance_not_newer_mtime(
    tmp_path: Path,
) -> None:
    receipt = _collect()
    canonical = tmp_path / GITHUB_SECURITY_RECEIPT_FILENAME
    canonical.write_text(json.dumps(receipt))
    decoy = tmp_path / "github-security-coverage-newer.json"
    decoy.write_text(json.dumps({"schema_version": "forged"}))
    decoy.touch()

    loaded = load_security_coverage_by_full_name(output_dir=tmp_path, now=NOW)

    assert loaded is not None
    assert loaded.source_path == str(canonical)
    assert len(loaded.entries_by_full_name) == 16


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
        validate_security_coverage_receipt(receipt, now=NOW)


def test_canonical_receipt_join_does_not_fall_back_to_repo_basename() -> None:
    entry = {
        "receipt_schema_version": "GitHubSecurityCoverageReceiptV1",
        "providers": {},
    }

    assert _select_security_entry(
        {"other/shared": entry}, "owner/shared", "shared"
    ) is None
    assert _select_security_entry(
        {"owner/shared": entry}, "owner/shared", "different display"
    ) is entry
