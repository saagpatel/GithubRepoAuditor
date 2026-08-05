from __future__ import annotations

import copy

import pytest

from src.security_admission import derive_security_admission


OBSERVED_AT = "2026-08-05T05:47:30+00:00"
PRODUCED_AT = "2026-08-05T05:48:00+00:00"


def _provider(counts: dict[str, int]) -> dict:
    return {
        "state": "observed",
        "reason_code": "observed",
        "observed_at": OBSERVED_AT,
        "pagination_complete": True,
        "completed": True,
        "zero_findings": sum(counts.values()) == 0,
        "counts": counts,
    }


def _security(
    *,
    dependabot_critical: int = 0,
    dependabot_high: int = 0,
    code_scanning_critical: int = 0,
    code_scanning_high: int = 0,
    secret_scanning_open: int = 0,
) -> dict:
    return {
        "alerts_available": True,
        "coverage_state": "complete",
        "receipt_state": "fresh",
        "source_produced_at": PRODUCED_AT,
        "dependabot_critical": dependabot_critical,
        "dependabot_high": dependabot_high,
        "code_scanning_critical": code_scanning_critical,
        "code_scanning_high": code_scanning_high,
        "secret_scanning_open": secret_scanning_open,
        "providers": {
            "dependabot": _provider(
                {
                    "critical": dependabot_critical,
                    "high": dependabot_high,
                    "medium": 0,
                    "low": 0,
                }
            ),
            "code_scanning": _provider(
                {
                    "critical": code_scanning_critical,
                    "high": code_scanning_high,
                    "warning": 0,
                    "note": 0,
                }
            ),
            "secret_scanning": _provider({"open": secret_scanning_open}),
        },
    }


def test_complete_fresh_alert_free_evidence_is_admitted_clear() -> None:
    admission = derive_security_admission(_security())

    assert admission.schema_version == "SecurityAdmissionV1"
    assert admission.status == "pass"
    assert admission.evidence_complete is True
    assert admission.has_findings is False
    assert admission.reason_codes == ("SECURITY_ADMISSION_CLEAR",)
    assert admission.evidence_observed_at == OBSERVED_AT
    assert admission.total_blocking_findings == 0


@pytest.mark.parametrize(
    ("changes", "critical", "high", "secrets"),
    [
        ({"dependabot_critical": 1}, 1, 0, 0),
        ({"dependabot_high": 2}, 0, 2, 0),
        ({"code_scanning_critical": 1}, 1, 0, 0),
        ({"code_scanning_high": 3}, 0, 3, 0),
        ({"secret_scanning_open": 1}, 0, 0, 1),
    ],
)
def test_each_provider_can_fail_admission_without_dependabot_findings(
    changes: dict[str, int], critical: int, high: int, secrets: int
) -> None:
    admission = derive_security_admission(_security(**changes))

    assert admission.status == "fail"
    assert admission.evidence_complete is True
    assert admission.has_findings is True
    assert admission.total_open_critical == critical
    assert admission.total_open_high == high
    assert admission.total_open_secrets == secrets
    assert admission.reason_codes == ("SECURITY_ADMISSION_FINDINGS",)


@pytest.mark.parametrize(
    ("coverage_state", "reason_code"),
    [
        ("partial", "SECURITY_COVERAGE_PARTIAL"),
        ("stale", "SECURITY_COVERAGE_STALE"),
        ("unknown", "SECURITY_COVERAGE_UNKNOWN"),
        ("malformed", "SECURITY_COVERAGE_INVALID"),
    ],
)
def test_non_complete_coverage_is_unknown(
    coverage_state: str, reason_code: str
) -> None:
    security = _security()
    security["coverage_state"] = coverage_state

    admission = derive_security_admission(security)

    assert admission.status == "unknown"
    assert admission.evidence_complete is False
    assert admission.reason_codes[0] == "SECURITY_ADMISSION_UNKNOWN"
    assert reason_code in admission.reason_codes


def test_missing_provider_and_unavailable_provider_are_unknown() -> None:
    missing = _security()
    del missing["providers"]["secret_scanning"]
    missing_result = derive_security_admission(missing)
    assert missing_result.status == "unknown"
    assert "SECURITY_PROVIDER_SET_INCOMPLETE" in missing_result.reason_codes

    unavailable = _security()
    unavailable["coverage_state"] = "partial"
    unavailable["alerts_available"] = False
    unavailable["providers"]["code_scanning"] = {
        "state": "forbidden",
        "reason_code": "forbidden",
        "observed_at": OBSERVED_AT,
        "pagination_complete": False,
        "completed": False,
        "zero_findings": None,
        "counts": None,
    }
    unavailable_result = derive_security_admission(unavailable)
    assert unavailable_result.status == "unknown"
    assert (
        "SECURITY_PROVIDER_CODE_SCANNING_NOT_OBSERVED"
        in unavailable_result.reason_codes
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "negative_count",
        "boolean_count",
        "compatibility_count_conflict",
        "zero_findings_conflict",
        "clock_conflict",
        "receipt_conflict",
    ],
)
def test_malformed_and_contradictory_evidence_is_unknown(mutation: str) -> None:
    security = _security()
    if mutation == "negative_count":
        security["providers"]["dependabot"]["counts"]["high"] = -1
    elif mutation == "boolean_count":
        security["providers"]["code_scanning"]["counts"]["critical"] = True
    elif mutation == "compatibility_count_conflict":
        security["code_scanning_high"] = 7
    elif mutation == "zero_findings_conflict":
        security["providers"]["secret_scanning"]["zero_findings"] = False
    elif mutation == "clock_conflict":
        security["providers"]["dependabot"]["observed_at"] = "2026-08-05T05:49:00+00:00"
    elif mutation == "receipt_conflict":
        security["receipt_state"] = "stale"

    admission = derive_security_admission(security)

    assert admission.status == "unknown"
    assert admission.evidence_complete is False
    assert admission.reason_codes[0] == "SECURITY_ADMISSION_UNKNOWN"


def test_known_findings_remain_visible_when_other_coverage_is_unknown() -> None:
    security = _security(dependabot_high=1)
    security["coverage_state"] = "partial"
    security["alerts_available"] = False
    security["providers"]["secret_scanning"] = {
        "state": "forbidden",
        "reason_code": "forbidden",
        "observed_at": OBSERVED_AT,
        "pagination_complete": False,
        "completed": False,
        "zero_findings": None,
        "counts": None,
    }

    admission = derive_security_admission(security)

    assert admission.status == "fail"
    assert admission.evidence_complete is False
    assert admission.has_findings is True
    assert admission.total_open_high == 1
    assert admission.reason_codes[0] == "SECURITY_ADMISSION_FINDINGS"
    assert "SECURITY_COVERAGE_PARTIAL" in admission.reason_codes


def test_provider_finding_remains_visible_when_compatibility_count_conflicts() -> None:
    security = _security(code_scanning_high=2)
    security["code_scanning_high"] = 0

    admission = derive_security_admission(security)

    assert admission.status == "fail"
    assert admission.evidence_complete is False
    assert admission.has_findings is True
    assert admission.total_open_high == 2
    assert admission.reason_codes[0] == "SECURITY_ADMISSION_FINDINGS"
    assert "SECURITY_PROVIDER_CODE_SCANNING_COUNT_CONFLICT" in (admission.reason_codes)


def test_derivation_is_deterministic_and_does_not_mutate_input() -> None:
    security = _security(code_scanning_high=1)
    before = copy.deepcopy(security)

    first = derive_security_admission(security)
    second = derive_security_admission(copy.deepcopy(security))

    assert first == second
    assert first.to_dict() == second.to_dict()
    assert security == before


def test_additive_envelope_fields_remain_backward_compatible_when_absent() -> None:
    security = _security()
    security.pop("alerts_available")
    for provider in security["providers"].values():
        provider.pop("reason_code")
        provider.pop("completed")
        provider.pop("zero_findings")

    admission = derive_security_admission(security)

    assert admission.status == "pass"
    assert admission.evidence_complete is True
