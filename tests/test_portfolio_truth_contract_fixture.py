"""Producer-side gate for the portable PortfolioTruth consumer contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

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
    assert states == ["complete", "partial", "stale", "unknown"]
    assert fixture["contract_fixture"]["contract_version"] == CONTRACT_VERSION
    assert "additive_contract_canary" in fixture["projects"][0]


def test_fixture_contains_only_public_safe_synthetic_identity() -> None:
    raw = fixture_bytes().decode().lower()
    for forbidden in ("/users/", "saagpatel", "saagar", "@gmail.com", "gmail"):
        assert forbidden not in raw
