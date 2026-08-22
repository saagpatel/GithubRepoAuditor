"""Canonical security evidence admission shared by PortfolioTruth consumers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


SECURITY_ADMISSION_SCHEMA_VERSION = "SecurityAdmissionV1"
SECURITY_PROVIDERS = ("dependabot", "code_scanning", "secret_scanning")

_BLOCKING_COUNT_FIELDS: dict[str, dict[str, str]] = {
    "dependabot": {
        "critical": "dependabot_critical",
        "high": "dependabot_high",
    },
    "code_scanning": {
        "critical": "code_scanning_critical",
        "high": "code_scanning_high",
    },
    "secret_scanning": {"open": "secret_scanning_open"},
}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _parse_datetime(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _reason_provider(provider: str, suffix: str) -> str:
    return f"SECURITY_PROVIDER_{provider.upper()}_{suffix}"


def _append_once(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


@dataclass(frozen=True)
class SecurityAdmissionV1:
    """One deterministic interpretation of normalized security evidence."""

    schema_version: str
    status: str
    evidence_complete: bool
    has_findings: bool
    reason_codes: tuple[str, ...]
    coverage_state: str
    receipt_state: str
    source_produced_at: str | None
    evidence_observed_at: str | None
    provider_states: dict[str, str]
    provider_observed_at: dict[str, str | None]
    dependabot_critical: int
    dependabot_high: int
    code_scanning_critical: int
    code_scanning_high: int
    secret_scanning_open: int

    @property
    def total_open_critical(self) -> int:
        return self.dependabot_critical + self.code_scanning_critical

    @property
    def total_open_high(self) -> int:
        return self.dependabot_high + self.code_scanning_high

    @property
    def total_open_secrets(self) -> int:
        return self.secret_scanning_open

    @property
    def total_blocking_findings(self) -> int:
        return self.total_open_critical + self.total_open_high + self.total_open_secrets

    @property
    def effective_coverage_state(self) -> str:
        if self.evidence_complete:
            return "complete"
        if self.coverage_state in {"partial", "stale", "unknown"}:
            return self.coverage_state
        return "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "evidence_complete": self.evidence_complete,
            "has_findings": self.has_findings,
            "reason_codes": list(self.reason_codes),
            "coverage_state": self.coverage_state,
            "receipt_state": self.receipt_state,
            "source_produced_at": self.source_produced_at,
            "evidence_observed_at": self.evidence_observed_at,
            "provider_states": dict(self.provider_states),
            "provider_observed_at": dict(self.provider_observed_at),
            "dependabot_critical": self.dependabot_critical,
            "dependabot_high": self.dependabot_high,
            "code_scanning_critical": self.code_scanning_critical,
            "code_scanning_high": self.code_scanning_high,
            "secret_scanning_open": self.secret_scanning_open,
            "total_open_critical": self.total_open_critical,
            "total_open_high": self.total_open_high,
            "total_open_secrets": self.total_open_secrets,
            "total_blocking_findings": self.total_blocking_findings,
            "effective_coverage_state": self.effective_coverage_state,
        }


def derive_security_admission(security_value: Any) -> SecurityAdmissionV1:
    """Derive a fail-closed admission result from one project security envelope.

    Known blocking findings remain visible even when another provider is unknown,
    but ``evidence_complete`` stays false and no consumer may describe the repo as
    clear or create a fully admitted decision from incomplete evidence.
    """

    security = _mapping(security_value)
    evidence_reasons: list[str] = []

    coverage_state = _text(security.get("coverage_state")) or "unknown"
    if coverage_state != "complete":
        coverage_reason = {
            "partial": "SECURITY_COVERAGE_PARTIAL",
            "stale": "SECURITY_COVERAGE_STALE",
            "unknown": "SECURITY_COVERAGE_UNKNOWN",
        }.get(coverage_state, "SECURITY_COVERAGE_INVALID")
        _append_once(evidence_reasons, coverage_reason)

    receipt_state = _text(security.get("receipt_state")) or "unknown"
    if receipt_state != "fresh":
        receipt_reason = {
            "stale": "SECURITY_RECEIPT_STALE",
            "unknown": "SECURITY_RECEIPT_UNKNOWN",
        }.get(receipt_state, "SECURITY_RECEIPT_STATE_INVALID")
        _append_once(evidence_reasons, receipt_reason)

    alerts_available = security.get("alerts_available")
    if alerts_available is not None and (
        (coverage_state == "complete") is not (alerts_available is True)
    ):
        _append_once(
            evidence_reasons,
            "SECURITY_ALERTS_AVAILABILITY_CONFLICT",
        )

    source_produced_text = _text(security.get("source_produced_at"))
    source_produced = _parse_datetime(source_produced_text)
    if not source_produced_text:
        _append_once(evidence_reasons, "SECURITY_RECEIPT_CLOCK_MISSING")
    elif source_produced is None:
        _append_once(evidence_reasons, "SECURITY_RECEIPT_CLOCK_INVALID")

    providers = _mapping(security.get("providers"))
    if set(providers) != set(SECURITY_PROVIDERS):
        _append_once(evidence_reasons, "SECURITY_PROVIDER_SET_INCOMPLETE")

    provider_states: dict[str, str] = {}
    provider_observed_at: dict[str, str | None] = {}
    valid_observed_times: list[datetime] = []
    admitted_counts = {
        "dependabot_critical": 0,
        "dependabot_high": 0,
        "code_scanning_critical": 0,
        "code_scanning_high": 0,
        "secret_scanning_open": 0,
    }

    for provider_name in SECURITY_PROVIDERS:
        provider = _mapping(providers.get(provider_name))
        state = _text(provider.get("state")) or "missing"
        provider_states[provider_name] = state
        observed_at_text = _text(provider.get("observed_at"))
        provider_observed_at[provider_name] = observed_at_text or None

        if state != "observed":
            _append_once(
                evidence_reasons,
                _reason_provider(provider_name, "NOT_OBSERVED"),
            )
            continue
        if provider.get("reason_code") not in {None, "observed"}:
            _append_once(
                evidence_reasons,
                _reason_provider(provider_name, "REASON_CONFLICT"),
            )
        if provider.get("pagination_complete") is not True:
            _append_once(
                evidence_reasons,
                _reason_provider(provider_name, "PAGINATION_INCOMPLETE"),
            )
        completed = provider.get("completed")
        if completed is not None and completed is not True:
            _append_once(
                evidence_reasons,
                _reason_provider(provider_name, "OBSERVATION_INCOMPLETE"),
            )

        observed_at = _parse_datetime(observed_at_text)
        if not observed_at_text:
            _append_once(
                evidence_reasons,
                _reason_provider(provider_name, "CLOCK_MISSING"),
            )
        elif observed_at is None:
            _append_once(
                evidence_reasons,
                _reason_provider(provider_name, "CLOCK_INVALID"),
            )
        else:
            valid_observed_times.append(observed_at)
            if source_produced is not None and observed_at > source_produced:
                _append_once(
                    evidence_reasons,
                    _reason_provider(provider_name, "CLOCK_CONFLICT"),
                )

        raw_counts = provider.get("counts")
        counts = _mapping(raw_counts)
        if isinstance(raw_counts, Mapping):
            for count_name, compatibility_name in _BLOCKING_COUNT_FIELDS[
                provider_name
            ].items():
                count = counts.get(count_name)
                if (
                    isinstance(count, int)
                    and not isinstance(count, bool)
                    and count >= 0
                ):
                    # Preserve a provider-observed positive finding even when a
                    # compatibility field or another count is contradictory.
                    # Admission still fails closed via the reason code below.
                    admitted_counts[compatibility_name] = count
        counts_valid = isinstance(raw_counts, Mapping) and all(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0
            for value in counts.values()
        )
        required_count_names = set(_BLOCKING_COUNT_FIELDS[provider_name])
        if not counts_valid or not required_count_names.issubset(counts):
            _append_once(
                evidence_reasons,
                _reason_provider(provider_name, "COUNTS_INVALID"),
            )
            continue

        count_total = sum(counts.values())
        zero_findings = provider.get("zero_findings")
        if zero_findings is not None and zero_findings is not (count_total == 0):
            _append_once(
                evidence_reasons,
                _reason_provider(provider_name, "ZERO_FINDINGS_CONFLICT"),
            )

        for count_name, compatibility_name in _BLOCKING_COUNT_FIELDS[
            provider_name
        ].items():
            count = counts[count_name]
            compatibility_count = security.get(compatibility_name)
            if (
                not isinstance(compatibility_count, int)
                or isinstance(compatibility_count, bool)
                or compatibility_count < 0
                or compatibility_count != count
            ):
                _append_once(
                    evidence_reasons,
                    _reason_provider(provider_name, "COUNT_CONFLICT"),
                )
                continue
    evidence_observed_at = (
        min(valid_observed_times).isoformat() if valid_observed_times else None
    )
    total_findings = sum(admitted_counts.values())
    has_findings = total_findings > 0
    evidence_complete = not evidence_reasons
    if has_findings:
        status = "fail"
        reason_codes = ("SECURITY_ADMISSION_FINDINGS", *evidence_reasons)
    elif evidence_reasons:
        status = "unknown"
        reason_codes = ("SECURITY_ADMISSION_UNKNOWN", *evidence_reasons)
    else:
        status = "pass"
        reason_codes = ("SECURITY_ADMISSION_CLEAR",)

    return SecurityAdmissionV1(
        schema_version=SECURITY_ADMISSION_SCHEMA_VERSION,
        status=status,
        evidence_complete=evidence_complete,
        has_findings=has_findings,
        reason_codes=tuple(reason_codes),
        coverage_state=coverage_state,
        receipt_state=receipt_state,
        source_produced_at=source_produced_text or None,
        evidence_observed_at=evidence_observed_at,
        provider_states=provider_states,
        provider_observed_at=provider_observed_at,
        dependabot_critical=admitted_counts["dependabot_critical"],
        dependabot_high=admitted_counts["dependabot_high"],
        code_scanning_critical=admitted_counts["code_scanning_critical"],
        code_scanning_high=admitted_counts["code_scanning_high"],
        secret_scanning_open=admitted_counts["secret_scanning_open"],
    )
