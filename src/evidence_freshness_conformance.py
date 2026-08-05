"""Deterministic, language-neutral evidence freshness conformance vectors.

The contract standardizes only the edge semantics that must not drift between
consumers: timestamp parsing, an injected reader clock, skew handling, exact
threshold boundaries, unavailable reads, and canonical reason codes. Threshold
values, product labels, alert policy, and build-versus-reader behavior remain
consumer owned.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

CONTRACT_SCHEMA = "EvidenceFreshnessConformanceV1"
MANIFEST_SCHEMA = "EvidenceFreshnessConformanceManifestV1"
CONTRACT_VERSION = "1.0.0"
OWNER_REPOSITORY = "saagpatel/GithubRepoAuditor"
VECTORS_RELATIVE_PATH = (
    "fixtures/contracts/evidence-freshness-conformance-v1/vectors.json"
)
MANIFEST_RELATIVE_PATH = (
    "fixtures/contracts/evidence-freshness-conformance-v1/manifest.json"
)

EVALUATION_CLOCK = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
AGING_AFTER_MS = 7 * 24 * 60 * 60 * 1000
STALE_AFTER_MS = 14 * 24 * 60 * 60 * 1000
SKEW_TOLERANCE_MS = 60_000

CANONICAL_STATES = ("fresh", "aging", "stale", "unknown", "unavailable")
CANONICAL_REASONS = (
    "within_fresh_window",
    "within_aging_window",
    "at_or_beyond_stale_boundary",
    "timestamp_missing",
    "timestamp_unparseable",
    "timestamp_timezone_missing",
    "timestamp_future_within_tolerance",
    "timestamp_future_beyond_tolerance",
    "read_unavailable",
    "policy_not_applicable",
)

_EXPLICIT_TIMEZONE = re.compile(r"(?:[zZ]|[+-]\d{2}:\d{2})$")


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    rendered = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    return f"{rendered}\n".encode()


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _parse_timestamp(value: object) -> tuple[datetime | None, str | None]:
    if value is None:
        return None, "timestamp_missing"
    if not isinstance(value, str) or not value.strip():
        return None, "timestamp_unparseable"
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        return None, "timestamp_unparseable"
    if _EXPLICIT_TIMEZONE.search(raw) is None or parsed.tzinfo is None:
        return None, "timestamp_timezone_missing"
    return parsed.astimezone(timezone.utc), None


def evaluate_freshness(
    *,
    generated_at: object,
    reader_clock: datetime,
    read_state: str = "available",
    policy_state: str = "configured",
    aging_after_ms: int = AGING_AFTER_MS,
    stale_after_ms: int = STALE_AFTER_MS,
    skew_tolerance_ms: int = SKEW_TOLERANCE_MS,
) -> dict[str, Any]:
    """Evaluate the canonical state and reason without reading wall time."""
    if reader_clock.tzinfo is None:
        raise ValueError("reader_clock must include an explicit timezone")
    if read_state not in {"available", "unavailable"}:
        raise ValueError("read_state must be available or unavailable")
    if policy_state not in {"configured", "not_applicable"}:
        raise ValueError("policy_state must be configured or not_applicable")
    if aging_after_ms <= 0 or stale_after_ms <= aging_after_ms:
        raise ValueError("freshness thresholds must be positive and strictly ordered")
    if skew_tolerance_ms < 0:
        raise ValueError("skew_tolerance_ms must be non-negative")

    if read_state == "unavailable":
        return {"state": "unavailable", "reason": "read_unavailable", "age_ms": None}

    generated, parse_reason = _parse_timestamp(generated_at)
    if parse_reason is not None:
        return {"state": "unknown", "reason": parse_reason, "age_ms": None}
    assert generated is not None

    raw_age_ms = round(
        (reader_clock.astimezone(timezone.utc) - generated).total_seconds() * 1000
    )
    if raw_age_ms < -skew_tolerance_ms:
        return {
            "state": "unknown",
            "reason": "timestamp_future_beyond_tolerance",
            "age_ms": None,
        }
    age_ms = max(0, raw_age_ms)
    if policy_state == "not_applicable":
        return {
            "state": "unknown",
            "reason": "policy_not_applicable",
            "age_ms": age_ms,
        }
    if raw_age_ms < 0:
        return {
            "state": "fresh",
            "reason": "timestamp_future_within_tolerance",
            "age_ms": 0,
        }
    if age_ms < aging_after_ms:
        return {
            "state": "fresh",
            "reason": "within_fresh_window",
            "age_ms": age_ms,
        }
    if age_ms < stale_after_ms:
        return {
            "state": "aging",
            "reason": "within_aging_window",
            "age_ms": age_ms,
        }
    return {
        "state": "stale",
        "reason": "at_or_beyond_stale_boundary",
        "age_ms": age_ms,
    }


def _case(
    case_id: str,
    *,
    generated_at: object,
    read_state: str = "available",
    policy_state: str = "configured",
) -> dict[str, Any]:
    expected = evaluate_freshness(
        generated_at=generated_at,
        reader_clock=EVALUATION_CLOCK,
        read_state=read_state,
        policy_state=policy_state,
    )
    return {
        "id": case_id,
        "input": {
            "generated_at": generated_at,
            "policy_state": policy_state,
            "read_state": read_state,
        },
        "expected": expected,
    }


def build_vectors() -> dict[str, Any]:
    clock = EVALUATION_CLOCK
    return {
        "schema": CONTRACT_SCHEMA,
        "contract_version": CONTRACT_VERSION,
        "evaluation_clock": _iso(clock),
        "policy": {
            "aging_after_ms": AGING_AFTER_MS,
            "stale_after_ms": STALE_AFTER_MS,
            "skew_tolerance_ms": SKEW_TOLERANCE_MS,
            "boundary_semantics": (
                "fresh_when_age_lt_aging;aging_when_age_lt_stale;"
                "stale_when_age_gte_stale"
            ),
        },
        "canonical_states": list(CANONICAL_STATES),
        "canonical_reasons": list(CANONICAL_REASONS),
        "timestamp_contract": {
            "timezone": "explicit-Z-or-offset-required",
            "reader_clock": "injected-never-wall-clock",
            "normalization": "UTC",
        },
        "cases": [
            _case("fresh_at_reader_clock", generated_at=_iso(clock)),
            _case(
                "fresh_one_ms_before_aging_boundary",
                generated_at=_iso(clock - timedelta(milliseconds=AGING_AFTER_MS - 1)),
            ),
            _case(
                "aging_at_exact_boundary",
                generated_at=_iso(clock - timedelta(milliseconds=AGING_AFTER_MS)),
            ),
            _case(
                "aging_one_ms_before_stale_boundary",
                generated_at=_iso(clock - timedelta(milliseconds=STALE_AFTER_MS - 1)),
            ),
            _case(
                "stale_at_exact_boundary",
                generated_at=_iso(clock - timedelta(milliseconds=STALE_AFTER_MS)),
            ),
            _case(
                "stale_beyond_boundary",
                generated_at=_iso(clock - timedelta(milliseconds=STALE_AFTER_MS + 1)),
            ),
            _case("missing_timestamp", generated_at=None),
            _case("empty_timestamp", generated_at=""),
            _case("unparseable_timestamp", generated_at="not-a-timestamp"),
            _case("timezone_missing", generated_at="2026-08-01T12:00:00.000"),
            _case(
                "offset_normalizes_to_reader_clock",
                generated_at="2026-08-01T07:00:00.000-05:00",
            ),
            _case(
                "future_at_skew_tolerance",
                generated_at=_iso(clock + timedelta(milliseconds=SKEW_TOLERANCE_MS)),
            ),
            _case(
                "future_one_ms_beyond_skew_tolerance",
                generated_at=_iso(clock + timedelta(milliseconds=SKEW_TOLERANCE_MS + 1)),
            ),
            _case(
                "unavailable_read_wins",
                generated_at=_iso(clock),
                read_state="unavailable",
            ),
            _case(
                "policy_not_applicable_preserves_age",
                generated_at=_iso(clock - timedelta(minutes=1)),
                policy_state="not_applicable",
            ),
        ],
        "additive_canary": {"consumer_behavior": "ignore-compatible-addition"},
    }


def vectors_bytes() -> bytes:
    return canonical_json_bytes(build_vectors())


def vectors_sha256() -> str:
    return hashlib.sha256(vectors_bytes()).hexdigest()


def build_manifest() -> dict[str, Any]:
    return {
        "schema": MANIFEST_SCHEMA,
        "contract_version": CONTRACT_VERSION,
        "owner": {
            "repository": OWNER_REPOSITORY,
            "artifact_path": VECTORS_RELATIVE_PATH,
            "artifact_sha256": vectors_sha256(),
            "generator": "src.evidence_freshness_conformance:build_vectors",
            "manifest_path": MANIFEST_RELATIVE_PATH,
        },
        "versioning": {
            "policy": "additive-minor-breaking-major",
            "compatibility": (
                "consumers-must-ignore-unknown-top-level-fields-and-new-cases"
            ),
        },
        "consumer_profiles": {
            "operator-control-plane": {
                "state_mapping": {
                    "fresh": "fresh",
                    "aging": "aging",
                    "stale": "stale",
                    "unknown": "unverified",
                    "unavailable": "unavailable",
                }
            },
            "desktop-command-center": {
                "state_mapping": {
                    "fresh": "fresh",
                    "aging": "aging",
                    "stale": "stale",
                    "unknown": "unknown",
                    "unavailable": "unknown",
                }
            },
            "public-site-projection": {
                "state_mapping": {
                    "fresh": "fresh",
                    "aging": "resting",
                    "stale": "cold",
                    "unknown": "unknown",
                    "unavailable": "unknown",
                }
            },
        },
        "consumer_owned": [
            "threshold-values",
            "ui-language",
            "alert-policy",
            "build-versus-reader-behavior",
            "production-calculator",
        ],
        "non_goals": [
            "shared-runtime-library",
            "shared-alert-policy",
            "shared-ui-copy",
        ],
    }


def manifest_bytes() -> bytes:
    return canonical_json_bytes(build_manifest())
