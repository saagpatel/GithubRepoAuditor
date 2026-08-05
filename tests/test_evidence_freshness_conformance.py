"""Producer gate for EvidenceFreshnessConformanceV1."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import pytest

from src.evidence_freshness_conformance import (
    AGING_AFTER_MS,
    CANONICAL_REASONS,
    CANONICAL_STATES,
    CONTRACT_SCHEMA,
    MANIFEST_RELATIVE_PATH,
    OWNER_REPOSITORY,
    SKEW_TOLERANCE_MS,
    STALE_AFTER_MS,
    VECTORS_RELATIVE_PATH,
    build_manifest,
    build_vectors,
    evaluate_freshness,
    manifest_bytes,
    vectors_bytes,
)


def test_committed_artifacts_match_deterministic_generator() -> None:
    assert Path(VECTORS_RELATIVE_PATH).read_bytes() == vectors_bytes()
    assert Path(MANIFEST_RELATIVE_PATH).read_bytes() == manifest_bytes()


def test_manifest_binds_owner_and_vector_digest() -> None:
    manifest = json.loads(Path(MANIFEST_RELATIVE_PATH).read_text())
    vector_raw = Path(VECTORS_RELATIVE_PATH).read_bytes()

    assert manifest == build_manifest()
    assert manifest["owner"]["repository"] == OWNER_REPOSITORY
    assert manifest["owner"]["artifact_sha256"] == hashlib.sha256(vector_raw).hexdigest()
    assert manifest["versioning"]["policy"] == "additive-minor-breaking-major"


def test_vectors_cover_every_canonical_state_and_reason() -> None:
    vectors = build_vectors()
    states = {case["expected"]["state"] for case in vectors["cases"]}
    reasons = {case["expected"]["reason"] for case in vectors["cases"]}

    assert vectors["schema"] == CONTRACT_SCHEMA
    assert states == set(CANONICAL_STATES)
    assert reasons == set(CANONICAL_REASONS)


def test_every_case_is_recomputed_by_the_reference_evaluator() -> None:
    vectors = build_vectors()
    clock = datetime.fromisoformat(vectors["evaluation_clock"].replace("Z", "+00:00"))
    policy = vectors["policy"]

    for case in vectors["cases"]:
        assert evaluate_freshness(
            generated_at=case["input"]["generated_at"],
            reader_clock=clock,
            read_state=case["input"]["read_state"],
            policy_state=case["input"]["policy_state"],
            aging_after_ms=policy["aging_after_ms"],
            stale_after_ms=policy["stale_after_ms"],
            skew_tolerance_ms=policy["skew_tolerance_ms"],
        ) == case["expected"], case["id"]


def test_exact_boundaries_and_future_tolerance_fail_closed() -> None:
    by_id = {case["id"]: case["expected"] for case in build_vectors()["cases"]}

    assert by_id["fresh_one_ms_before_aging_boundary"] == {
        "state": "fresh",
        "reason": "within_fresh_window",
        "age_ms": AGING_AFTER_MS - 1,
    }
    assert by_id["aging_at_exact_boundary"] == {
        "state": "aging",
        "reason": "within_aging_window",
        "age_ms": AGING_AFTER_MS,
    }
    assert by_id["aging_one_ms_before_stale_boundary"]["age_ms"] == STALE_AFTER_MS - 1
    assert by_id["stale_at_exact_boundary"] == {
        "state": "stale",
        "reason": "at_or_beyond_stale_boundary",
        "age_ms": STALE_AFTER_MS,
    }
    assert by_id["future_at_skew_tolerance"] == {
        "state": "fresh",
        "reason": "timestamp_future_within_tolerance",
        "age_ms": 0,
    }
    assert by_id["future_one_ms_beyond_skew_tolerance"] == {
        "state": "unknown",
        "reason": "timestamp_future_beyond_tolerance",
        "age_ms": None,
    }
    assert SKEW_TOLERANCE_MS == 60_000


def test_reader_clock_must_be_injected_with_timezone() -> None:
    with pytest.raises(ValueError, match="reader_clock"):
        evaluate_freshness(
            generated_at="2026-08-01T12:00:00Z",
            reader_clock=datetime(2026, 8, 1, 12, 0),
        )


def test_public_contract_does_not_name_private_repositories_or_paths() -> None:
    rendered = (vectors_bytes() + manifest_bytes()).decode().lower()

    assert "/users/" not in rendered


def test_consumer_profiles_map_reasons_without_branching_the_vectors() -> None:
    manifest = build_manifest()
    profiles = manifest["consumer_profiles"]

    assert set(profiles) == {
        "operator-control-plane",
        "desktop-command-center",
        "public-site-projection",
    }
    for profile in profiles.values():
        assert set(profile["state_mapping"]) == set(CANONICAL_STATES)
    assert manifest["non_goals"] == [
        "shared-runtime-library",
        "shared-alert-policy",
        "shared-ui-copy",
    ]
