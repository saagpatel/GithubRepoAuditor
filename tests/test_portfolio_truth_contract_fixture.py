"""Producer-side gate for the portable PortfolioTruth consumer contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.demo_portfolio import resolved_coverage_state
from src.portfolio_truth_contract_fixture import (
    CONTRACT_VERSION,
    FIXTURE_RELATIVE_PATH,
    GENERATED_AT,
    MANIFEST_RELATIVE_PATH,
    PRODUCER_REPOSITORY,
    build_contract_fixture,
    build_contract_manifest,
    fixture_bytes,
    manifest_bytes,
)
from src.portfolio_truth_types import SCHEMA_VERSION
from src.portfolio_truth_validate import validate_truth_snapshot_payload


def test_committed_contract_artifacts_match_the_deterministic_generator() -> None:
    assert Path(FIXTURE_RELATIVE_PATH).read_bytes() == fixture_bytes()
    assert Path(MANIFEST_RELATIVE_PATH).read_bytes() == manifest_bytes()


def test_manifest_binds_schema_generator_and_fixture_digest() -> None:
    manifest = json.loads(Path(MANIFEST_RELATIVE_PATH).read_text())
    fixture_raw = Path(FIXTURE_RELATIVE_PATH).read_bytes()

    assert manifest == build_contract_manifest()
    assert manifest["contract_version"] == CONTRACT_VERSION
    assert manifest["portfolio_truth_schema_version"] == SCHEMA_VERSION
    assert manifest["producer"]["repository"] == PRODUCER_REPOSITORY
    assert manifest["producer"]["artifact_sha256"] == hashlib.sha256(
        fixture_raw
    ).hexdigest()


def test_fixture_spans_the_receipt_states_with_additive_canaries() -> None:
    fixture = build_contract_fixture()
    states = [
        resolved_coverage_state(project["security"])
        for project in fixture["projects"]
    ]

    assert fixture["schema_version"] == SCHEMA_VERSION
    assert fixture["generated_at"] == GENERATED_AT.isoformat()
    assert fixture["inputs"] == {
        "catalog": {
            "source_id": "portfolio-catalog",
            "sha256": None,
            "observed_at": GENERATED_AT.isoformat(),
        },
        "workspace": {
            "source_id": "projects-root",
            "observed_at": GENERATED_AT.isoformat(),
        },
        "notion": {
            "mode": "unavailable",
            "observed_at": None,
            "carried_from_generated_at": None,
        },
    }
    assert fixture["exclusions"] == {
        "policy_version": "workspace_discovery.v2",
        "counts": {},
    }
    assert states == ["complete", "partial", "stale", "unknown"]
    assert fixture["contract_fixture"]["contract_version"] == CONTRACT_VERSION
    assert fixture["contract_fixture"]["producer_evidence"] == "absent"
    assert "additive_contract_canary" in fixture["projects"][0]


def test_generated_and_committed_fixtures_pass_canonical_payload_validation() -> None:
    generated = build_contract_fixture()
    committed = json.loads(Path(FIXTURE_RELATIVE_PATH).read_text())

    assert generated["producer"] == {}
    assert committed["producer"] == {}
    validate_truth_snapshot_payload(generated)
    validate_truth_snapshot_payload(committed)


def test_canonical_payload_validation_rejects_partial_producer_evidence() -> None:
    fixture = build_contract_fixture()
    fixture["producer"] = {
        "repository": "demo-org/portfolio-auditor",
        "checkout_role": "demo-fixture",
        "worktree_clean": True,
        "dirty_path_count": 0,
        "verified_at": GENERATED_AT.isoformat(),
    }

    with pytest.raises(ValueError, match="Producer evidence is missing fields"):
        validate_truth_snapshot_payload(fixture)


def test_canonical_payload_validation_rejects_invalid_project_row() -> None:
    fixture = build_contract_fixture()
    fixture["projects"][0]["derived"]["primary_context_file"] = "README.md"

    with pytest.raises(ValueError, match="Invalid primary context file"):
        validate_truth_snapshot_payload(fixture)


def test_canonical_payload_validation_rejects_deleted_rollups() -> None:
    fixture = build_contract_fixture()
    del fixture["rollups"]

    with pytest.raises(ValueError, match=r"canonical reconstruction at \$\.rollups"):
        validate_truth_snapshot_payload(fixture)


def test_canonical_payload_validation_rejects_tampered_rollup_count() -> None:
    fixture = build_contract_fixture()
    fixture["rollups"]["security"]["complete_repo_count"] += 1

    with pytest.raises(
        ValueError,
        match=r"canonical reconstruction at \$\.rollups\.security\.complete_repo_count",
    ):
        validate_truth_snapshot_payload(fixture)


def test_canonical_payload_validation_rejects_tampered_project_rollup() -> None:
    fixture = build_contract_fixture()
    fixture["projects"][0]["security"]["open_high_critical"] += 1

    with pytest.raises(
        ValueError,
        match=r"canonical reconstruction at \$\.projects\[0\]\.security\.open_high_critical",
    ):
        validate_truth_snapshot_payload(fixture)


@pytest.mark.parametrize(
    ("section", "field"),
    ((None, "repository_state"), ("security", "cohort_member")),
)
def test_canonical_payload_validation_rejects_missing_project_fields(
    section: str | None,
    field: str,
) -> None:
    fixture = build_contract_fixture()
    project = fixture["projects"][0]
    target = project if section is None else project[section]
    del target[field]

    with pytest.raises(ValueError, match="canonical reconstruction"):
        validate_truth_snapshot_payload(fixture)


def test_fixture_contains_only_public_safe_synthetic_identity() -> None:
    raw = fixture_bytes().decode().lower()
    for forbidden in ("/users/", "saagpatel", "saagar", "@gmail.com", "gmail"):
        assert forbidden not in raw
