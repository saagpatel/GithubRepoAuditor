"""Producer-side gate for the portable PortfolioTruth consumer contract."""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import pytest

from src.demo_portfolio import resolved_coverage_state
from src.portfolio_truth_contract_fixture import (
    CONTRACT_VERSION,
    EVALUATED_AT,
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


def test_fixture_stale_receipt_is_stale_at_the_manifest_evaluation_time() -> None:
    fixture = build_contract_fixture()
    stale_security = next(
        project["security"]
        for project in fixture["projects"]
        if resolved_coverage_state(project["security"]) == "stale"
    )
    source_produced_at = datetime.fromisoformat(stale_security["source_produced_at"])
    age_hours = (EVALUATED_AT - source_produced_at).total_seconds() / 3600

    assert age_hours > 24


def test_fixture_receipt_rows_preserve_producer_repository_state() -> None:
    fixture = build_contract_fixture()
    receipt_rows = [
        project
        for project in fixture["projects"]
        if project["security"]["receipt_schema_version"]
    ]

    for project in receipt_rows:
        repository_state = project["repository_state"]
        remote = repository_state["remote_default_branch"]
        assert repository_state["state"] == "observed"
        assert repository_state["local"]["path"].startswith("/demo-workspace/")
        assert remote["source"] == "github-graphql-default-branch-head-v1"
        if project["security"]["receipt_state"] == "stale":
            assert remote["state"] == "stale"
            assert remote["default_branch"] is None
            assert remote["head_sha"] is None
        else:
            assert remote["state"] == "observed"
            assert remote["default_branch"] == "main"
            assert len(remote["head_sha"]) == 64

    raw = json.dumps([project["repository_state"] for project in receipt_rows]).lower()
    assert "/users/" not in raw
    assert "saagpatel" not in raw


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


def test_canonical_payload_validation_rejects_deleted_receipt_provider() -> None:
    fixture = build_contract_fixture()
    stale = next(
        project["security"]
        for project in fixture["projects"]
        if project["security"]["receipt_state"] == "stale"
    )
    del stale["providers"]["dependabot"]

    with pytest.raises(ValueError, match="must contain exactly"):
        validate_truth_snapshot_payload(fixture)


def test_canonical_payload_validation_rejects_stale_provider_counts() -> None:
    fixture = build_contract_fixture()
    stale = next(
        project["security"]
        for project in fixture["projects"]
        if project["security"]["receipt_state"] == "stale"
    )
    stale["providers"]["dependabot"]["counts"] = {
        "critical": 1,
        "high": 0,
        "medium": 0,
        "low": 0,
    }

    with pytest.raises(ValueError, match="must clear counts"):
        validate_truth_snapshot_payload(fixture)


def test_canonical_payload_validation_rejects_invalid_provider_state() -> None:
    fixture = build_contract_fixture()
    fixture["projects"][0]["security"]["providers"]["dependabot"]["state"] = (
        "fabricated"
    )

    with pytest.raises(ValueError, match="state is invalid"):
        validate_truth_snapshot_payload(fixture)


def test_canonical_payload_validation_rejects_observed_provider_count_shape() -> None:
    fixture = build_contract_fixture()
    counts = fixture["projects"][0]["security"]["providers"]["dependabot"][
        "counts"
    ]
    del counts["low"]

    with pytest.raises(ValueError, match="counts are invalid"):
        validate_truth_snapshot_payload(fixture)


def test_canonical_payload_validation_rejects_provider_classification_drift() -> None:
    fixture = build_contract_fixture()
    fixture["projects"][0]["security"]["providers"]["dependabot"][
        "http_classification"
    ] = "ok"

    with pytest.raises(ValueError, match="http_classification"):
        validate_truth_snapshot_payload(fixture)


def test_canonical_payload_validation_rejects_invalid_declared_category() -> None:
    fixture = build_contract_fixture()
    fixture["projects"][0]["declared"]["category"] = "platform"

    with pytest.raises(ValueError, match="Invalid category"):
        validate_truth_snapshot_payload(fixture)


def test_canonical_payload_validation_rejects_invalid_active_infra_category() -> None:
    fixture = build_contract_fixture()
    fixture["projects"][0]["declared"]["category"] = "learning"

    with pytest.raises(ValueError, match="requires the infrastructure category"):
        validate_truth_snapshot_payload(fixture)


def test_canonical_payload_validation_rejects_providers_without_receipt() -> None:
    fixture = build_contract_fixture()
    unknown = next(
        project["security"]
        for project in fixture["projects"]
        if project["security"]["receipt_state"] == "unknown"
    )
    stale = next(
        project["security"]
        for project in fixture["projects"]
        if project["security"]["receipt_state"] == "stale"
    )
    unknown["providers"] = deepcopy(stale["providers"])

    with pytest.raises(ValueError, match="require receipt evidence"):
        validate_truth_snapshot_payload(fixture)


def test_canonical_payload_validation_rejects_missing_remote_branch_state() -> None:
    fixture = build_contract_fixture()
    del fixture["projects"][0]["repository_state"]["remote_default_branch"]

    with pytest.raises(ValueError, match="requires remote_default_branch"):
        validate_truth_snapshot_payload(fixture)


@pytest.mark.parametrize(("field", "value"), (("default_branch", None), ("head_sha", "short")))
def test_canonical_payload_validation_rejects_invalid_remote_branch_shape(
    field: str,
    value: object,
) -> None:
    fixture = build_contract_fixture()
    fixture["projects"][0]["repository_state"]["remote_default_branch"][field] = value

    with pytest.raises(ValueError, match="Invalid remote default branch"):
        validate_truth_snapshot_payload(fixture)


@pytest.mark.parametrize(
    ("section", "field", "message"),
    (
        (None, "repository_state", "Invalid repository state"),
        ("security", "cohort_member", "canonical reconstruction"),
    ),
)
def test_canonical_payload_validation_rejects_missing_project_fields(
    section: str | None,
    field: str,
    message: str,
) -> None:
    fixture = build_contract_fixture()
    project = fixture["projects"][0]
    target = project if section is None else project[section]
    del target[field]

    with pytest.raises(ValueError, match=message):
        validate_truth_snapshot_payload(fixture)


def test_fixture_contains_only_public_safe_synthetic_identity() -> None:
    raw = fixture_bytes().decode().lower()
    _forbidden_extra = [
        token
        for token in os.environ.get("PORTFOLIO_FORBIDDEN_TOKENS", "").split(",")
        if token
    ]
    for forbidden in (
        "/users/",
        "saagpatel",
        "@gmail.com",
        "gmail",
        *_forbidden_extra,
    ):
        assert forbidden not in raw
