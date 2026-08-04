"""Producer-side gate for the portable PortfolioTruth consumer contract."""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.demo_portfolio import resolved_coverage_state
from src.portfolio_truth_coverage import build_coverage_envelope
from src.portfolio_truth_metadata import build_source_summary, build_warnings
from src.portfolio_pathing import build_operating_path_entry
from src.portfolio_truth_precedence import PRECEDENCE_MATRIX
from src.portfolio_truth_provenance import REQUIRED_PROJECT_PROVENANCE_KEYS
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
from src.portfolio_truth_reconcile import _build_security_fields
from src.portfolio_truth_types import SCHEMA_VERSION
from src.portfolio_truth_validate import (
    _snapshot_from_payload,
    _validate_security_fields,
    validate_truth_snapshot,
    validate_truth_snapshot_payload,
)
from src.producer_preflight import (
    ProducerEvidence,
    producer_evidence_receipt_id,
)


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
    assert (
        manifest["producer"]["artifact_sha256"]
        == hashlib.sha256(fixture_raw).hexdigest()
    )


def test_fixture_spans_the_receipt_states_with_additive_canaries() -> None:
    fixture = build_contract_fixture()
    states = [
        resolved_coverage_state(project["security"]) for project in fixture["projects"]
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
        "github_security": {
            "source_id": "github-security-coverage-receipt",
            "schema_version": "GitHubSecurityCoverageReceiptV1",
            "produced_at": GENERATED_AT.isoformat(),
            "state": "fresh",
            "age_hours": 0.0,
            "producer_commit": "a" * 40,
            "cohort_policy": "portfolio-default-attention-v1",
            "cohort_repository_count": 3,
            "path": "/demo-workspace/github-security-coverage.json",
            "receipt_id": "sha256:" + "b" * 64,
            "content_sha256": "b" * 64,
        },
    }
    assert fixture["exclusions"] == {
        "policy_version": "workspace_discovery.v2",
        "counts": {},
    }
    assert sorted(states) == ["complete", "partial", "stale", "unknown"]
    assert fixture["contract_fixture"]["contract_version"] == CONTRACT_VERSION
    assert fixture["contract_fixture"]["producer_evidence"] == "absent"
    assert "additive_contract_canary" in fixture["projects"][0]


def test_contract_fixture_paths_match_the_production_helper() -> None:
    fixture = build_contract_fixture()
    projects = {
        project["identity"]["display_name"]: project
        for project in fixture["projects"]
    }

    for project in projects.values():
        declared = project["declared"]
        derived = project["derived"]
        expected = build_operating_path_entry(
            {**declared, "has_explicit_entry": True},
            context_quality=derived["context_quality"],
            archived=derived["archived"],
        )
        assert expected["operating_path_source"] == "explicit-operating-path"
        assert declared["operating_path"] == expected["operating_path"]
        assert derived["path_confidence"] == expected["path_confidence"]
        assert derived["path_override"] == expected["path_override"]
        assert derived["path_rationale"] == expected["path_rationale"]

    assert {
        name: (
            project["derived"]["path_confidence"],
            project["derived"]["path_override"],
        )
        for name, project in projects.items()
    } == {
        "Dovetail Forge": ("high", ""),
        "Kestrel Loom": ("high", ""),
        "Quartz Signal": ("medium", ""),
        "Solstice Cairn": ("low", "investigate"),
    }
    assert projects["Solstice Cairn"]["risk"]["path_risk"] is True
    assert projects["Solstice Cairn"]["risk"]["risk_tier"] == "elevated"
    assert projects["Solstice Cairn"]["derived"]["attention_state"] == "manual-only"


def test_contract_fixture_carries_the_required_project_provenance_set() -> None:
    fixture = build_contract_fixture()

    for project in fixture["projects"]:
        provenance = project["provenance"]
        assert REQUIRED_PROJECT_PROVENANCE_KEYS <= provenance.keys()
        assert all(
            provenance[key]["source"].strip()
            for key in REQUIRED_PROJECT_PROVENANCE_KEYS
        )


def test_contract_rejects_missing_required_project_provenance() -> None:
    fixture = build_contract_fixture()
    fixture["projects"][0]["provenance"] = {}

    with pytest.raises(ValueError, match="missing required fields"):
        validate_truth_snapshot_payload(fixture)


def test_contract_allows_optional_github_archived_provenance() -> None:
    fixture = build_contract_fixture()
    fixture["projects"][0]["provenance"]["github.archived"] = {
        "source": "github_api",
        "detail": "false",
    }

    validate_truth_snapshot_payload(fixture)


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


def test_fixture_repository_state_spans_fresh_stale_and_no_receipt_rows() -> None:
    fixture = build_contract_fixture()
    by_receipt_state = {
        project["security"]["receipt_state"]: project["repository_state"]
        for project in fixture["projects"]
    }

    assert {"fresh", "stale", "unknown"}.issubset(by_receipt_state)
    for repository_state in by_receipt_state.values():
        assert repository_state["state"] == "observed"
        assert repository_state["local"] == {
            key: repository_state["worktrees"][0][key]
            for key in repository_state["local"]
        }
        assert repository_state["topology"]["worktree_count"] == len(
            repository_state["worktrees"]
        )
    assert by_receipt_state["fresh"]["remote_default_branch"]["state"] == "observed"
    assert by_receipt_state["stale"]["remote_default_branch"]["state"] == "stale"
    assert by_receipt_state["unknown"]["remote_default_branch"]["state"] == "unknown"


def test_generated_and_committed_fixtures_pass_canonical_payload_validation() -> None:
    generated = build_contract_fixture()
    committed = json.loads(Path(FIXTURE_RELATIVE_PATH).read_text())

    assert generated["producer"] == {}
    assert committed["producer"] == {}
    validate_truth_snapshot_payload(generated)
    validate_truth_snapshot_payload(committed)


def test_observed_provider_requires_response_bound_reason() -> None:
    fixture = build_contract_fixture()
    provider = _complete_project(fixture)["security"]["providers"]["dependabot"]
    provider.update(
        http_status=304,
        http_classification="not_modified",
        reason="not_modified",
        conditional={"requested": True, "result": "not_modified"},
    )
    validate_truth_snapshot_payload(fixture)

    provider["reason"] = "fabricated"
    with pytest.raises(ValueError, match="reason does not match observed response"):
        validate_truth_snapshot_payload(fixture)


def test_kestrel_rejects_coherently_fabricated_not_found_reason() -> None:
    fixture = build_contract_fixture()
    kestrel = next(
        project
        for project in fixture["projects"]
        if project["identity"]["display_name"] == "Kestrel Loom"
    )
    provider = kestrel["security"]["providers"]["code_scanning"]
    assert (provider["state"], provider["http_status"]) == ("not_found", 404)
    provider["reason"] = "fabricated_reason"
    provider["http_classification"] = "fabricated_reason"

    with pytest.raises(ValueError, match="producer reason domain"):
        validate_truth_snapshot_payload(fixture)


def test_kestrel_rejects_modified_conditional_for_not_found_response() -> None:
    fixture = build_contract_fixture()
    kestrel = next(
        project
        for project in fixture["projects"]
        if project["identity"]["display_name"] == "Kestrel Loom"
    )
    provider = kestrel["security"]["providers"]["code_scanning"]
    assert (provider["state"], provider["http_status"]) == ("not_found", 404)
    provider["conditional"] = {"requested": True, "result": "modified"}

    with pytest.raises(ValueError, match="conditional metadata.*producer domain"):
        validate_truth_snapshot_payload(fixture)


def test_kestrel_rejects_fabricated_partial_remote_reason() -> None:
    fixture = build_contract_fixture()
    kestrel = next(
        project
        for project in fixture["projects"]
        if project["identity"]["display_name"] == "Kestrel Loom"
    )
    remote = kestrel["repository_state"]["remote_default_branch"]
    remote.update(
        state="partial",
        reason_code="default_branch_head_unavailable",
        reason="fabricated_reason",
        default_branch=None,
        head_sha=None,
        archived=False,
    )

    with pytest.raises(ValueError, match="producer reason domain"):
        validate_truth_snapshot_payload(fixture)


def test_contract_fixture_uses_the_shared_producer_coverage_envelope() -> None:
    fixture = build_contract_fixture()

    assert fixture["coverage"] == build_coverage_envelope(
        projects=fixture["projects"],
        notion_context_carried_forward=False,
        notion_context_rows=0,
    )
    assert [row["source"] for row in fixture["coverage"]] == [
        "workspace",
        "git",
        "github_security",
        "notion",
    ]


def test_contract_fixture_uses_the_shared_producer_precedence_matrix() -> None:
    fixture = build_contract_fixture()

    assert fixture["precedence_matrix"] == PRECEDENCE_MATRIX


@pytest.mark.parametrize(
    "duplicate_path",
    ("platform/dovetail-forge-copy", "supp:dovetail-forge-copy"),
)
def test_shared_source_summary_exposes_workspace_and_supplementary_duplicates(
    duplicate_path: str,
) -> None:
    fixture = build_contract_fixture()
    original = _complete_project(fixture)
    duplicate = deepcopy(original)
    duplicate["identity"]["project_key"] = duplicate_path
    duplicate["identity"]["path"] = duplicate_path

    summary = build_source_summary(
        workspace_root=fixture["workspace_root"],
        projects=[original, duplicate],
        catalog_errors=[],
        catalog_warnings=[],
        legacy_registry_rows=0,
        notion_context_rows=0,
        notion_context_carried_forward=False,
    )
    warnings = build_warnings(
        catalog_errors=[],
        catalog_warnings=[],
        unresolved_duplicates=summary["unresolved_duplicate_display_names"],
    )

    assert summary["duplicate_display_names"] == ["Dovetail Forge"]
    assert summary["unresolved_duplicate_display_names"] == ["Dovetail Forge"]
    assert warnings == [
        "Duplicate project display names require path-qualified registry labels: "
        "Dovetail Forge"
    ]


def _complete_project(fixture: dict[str, object]) -> dict[str, object]:
    return next(
        project
        for project in fixture["projects"]
        if project["security"]["coverage_state"] == "complete"
    )


def test_generic_snapshot_validation_rejects_synthetic_mixed_receipt_batch() -> None:
    fixture = build_contract_fixture()

    with pytest.raises(ValueError, match="source time is inconsistent"):
        validate_truth_snapshot(_snapshot_from_payload(fixture))


def test_contract_rejects_tampered_synthetic_matrix_marker() -> None:
    fixture = build_contract_fixture()
    fixture["contract_fixture"]["deterministic"] = False

    with pytest.raises(ValueError, match="source time is inconsistent"):
        validate_truth_snapshot_payload(fixture)


def test_contract_matrix_marker_does_not_auto_enable_with_producer_evidence() -> None:
    fixture = build_contract_fixture()
    fixture["producer"] = _valid_producer_evidence()

    with pytest.raises(ValueError, match="source time is inconsistent"):
        validate_truth_snapshot_payload(fixture)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (
            lambda payload: payload["precedence_matrix"].pop("declared.owner"),
            "precedence matrix",
        ),
        (
            lambda payload: payload["precedence_matrix"]["declared.owner"].append(
                "demo-fixture"
            ),
            "precedence matrix",
        ),
        (
            lambda payload: payload["source_summary"].update(project_count=99),
            "source summary",
        ),
        (
            lambda payload: payload["source_summary"].pop(
                "activity_status_counts"
            ),
            "source summary",
        ),
        (
            lambda payload: payload["source_summary"][
                "context_quality_counts"
            ].update(full=99),
            "source summary",
        ),
        (
            lambda payload: payload["source_summary"][
                "attention_state_counts"
            ].update(parked=99),
            "source summary",
        ),
        (
            lambda payload: payload["source_summary"].update(archived_count=99),
            "source summary",
        ),
        (
            lambda payload: payload["source_summary"].update(
                github_archived_count=99
            ),
            "source summary",
        ),
        (
            lambda payload: payload["source_summary"].update(
                duplicate_display_names=["fabricated"]
            ),
            "source summary",
        ),
        (
            lambda payload: payload["source_summary"].update(
                catalog_errors=["fabricated catalog error"]
            ),
            "warnings",
        ),
        (
            lambda payload: payload.update(workspace_root="/demo-other"),
            "workspace_root",
        ),
        (
            lambda payload: payload["inputs"]["catalog"].update(
                source_id="fabricated"
            ),
            "catalog input",
        ),
        (
            lambda payload: payload["inputs"].pop("catalog"),
            "input envelope",
        ),
        (
            lambda payload: payload["inputs"]["catalog"].update(
                observed_at=(GENERATED_AT - timedelta(minutes=1)).isoformat()
            ),
            "catalog input",
        ),
        (
            lambda payload: payload["inputs"]["workspace"].update(
                source_id="fabricated"
            ),
            "workspace input",
        ),
        (
            lambda payload: payload["inputs"].pop("workspace"),
            "input envelope",
        ),
        (
            lambda payload: payload["inputs"]["workspace"].update(
                observed_at=(GENERATED_AT - timedelta(minutes=1)).isoformat()
            ),
            "workspace input",
        ),
        (
            lambda payload: payload["source_summary"].update(
                notion_context_rows=1
            ),
            "Notion input",
        ),
        (
            lambda payload: payload["source_summary"].update(
                notion_context_carried_forward=True
            ),
            "Notion input",
        ),
        (
            lambda payload: payload["inputs"]["notion"].update(
                mode="live", observed_at=GENERATED_AT.isoformat()
            ),
            "Notion input",
        ),
        (
            lambda payload: payload["exclusions"].update(policy_version="fabricated"),
            "exclusions",
        ),
        (
            lambda payload: payload["exclusions"]["counts"].update(hidden=-1),
            "exclusion counts",
        ),
        (
            lambda payload: payload["warnings"].append("fabricated warning"),
            "warnings",
        ),
    ),
)
def test_contract_validation_rejects_top_level_envelope_drift(
    mutation: object,
    message: str,
) -> None:
    fixture = build_contract_fixture()
    mutation(fixture)

    with pytest.raises(ValueError, match=message):
        validate_truth_snapshot_payload(fixture)


@pytest.mark.parametrize(
    ("reason", "count"),
    (("fabricated", 1), ("scratch-container", 0)),
)
def test_contract_rejects_nonproducer_exclusion_counts(
    reason: str,
    count: int,
) -> None:
    fixture = build_contract_fixture()
    fixture["exclusions"]["counts"] = {reason: count}

    with pytest.raises(ValueError, match="exclusion counts"):
        validate_truth_snapshot_payload(fixture)


def test_contract_validation_rejects_cross_envelope_notion_drift() -> None:
    fixture = build_contract_fixture()
    observed_at = (GENERATED_AT - timedelta(hours=1)).isoformat()
    fixture["source_summary"].update(
        notion_context_rows=1,
        notion_context_carried_forward=True,
    )
    fixture["inputs"]["notion"] = {
        "mode": "carried-forward",
        "observed_at": observed_at,
        "carried_from_generated_at": observed_at,
    }

    with pytest.raises(ValueError, match="coverage differs"):
        validate_truth_snapshot_payload(fixture)


def test_portable_contract_rejects_coherent_non_demo_workspace_root() -> None:
    fixture = build_contract_fixture()
    fixture["workspace_root"] = "/demo-other"
    fixture["source_summary"]["workspace_root"] = "/demo-other"

    with pytest.raises(ValueError, match="exactly /demo-workspace"):
        validate_truth_snapshot_payload(fixture)


@pytest.mark.parametrize(
    "github_security",
    (
        {},
        {
            "path": "/evidence/security.json",
            "receipt_id": "sha256:" + "a" * 64,
            "content_sha256": "b" * 64,
        },
    ),
)
def test_contract_rejects_partial_github_security_input(
    github_security: dict[str, object],
) -> None:
    fixture = build_contract_fixture()
    fixture["inputs"]["github_security"] = github_security

    with pytest.raises(ValueError, match="GitHub security input"):
        validate_truth_snapshot_payload(fixture)


def test_contract_requires_github_security_input_for_receipt_rows() -> None:
    fixture = build_contract_fixture()
    fixture["inputs"].pop("github_security")

    with pytest.raises(ValueError, match="required for receipt-backed rows"):
        validate_truth_snapshot_payload(fixture)


@pytest.mark.parametrize("missing", ("receipt_id", "content_sha256"))
def test_portable_contract_requires_security_receipt_binding(missing: str) -> None:
    fixture = build_contract_fixture()
    fixture["inputs"]["github_security"].pop(missing)

    with pytest.raises(ValueError, match="requires both receipt_id"):
        validate_truth_snapshot_payload(fixture)


def _valid_producer_evidence() -> dict[str, object]:
    verified_at = GENERATED_AT.isoformat()
    return ProducerEvidence(
        repository="saagpatel/GithubRepoAuditor",
        expected_repository="saagpatel/GithubRepoAuditor",
        commit="a" * 40,
        ref="refs/heads/main",
        checkout_role="canonical-producer",
        checkout_path="/demo-workspace/producer",
        worktree_clean=True,
        dirty_path_count=0,
        verified_at=GENERATED_AT,
        receipt_id=producer_evidence_receipt_id(
            repository="saagpatel/GithubRepoAuditor",
            expected_repository="saagpatel/GithubRepoAuditor",
            commit="a" * 40,
            ref="refs/heads/main",
            checkout_role="canonical-producer",
            checkout_path="/demo-workspace/producer",
            verified_at=verified_at,
        ),
    ).to_dict()


def test_contract_accepts_canonical_producer_evidence_shape() -> None:
    fixture = build_contract_fixture()
    fixture["producer"] = _valid_producer_evidence()

    validate_truth_snapshot_payload(fixture, allow_synthetic_security_matrix=True)


def test_contract_rejects_future_producer_evidence() -> None:
    fixture = build_contract_fixture()
    fixture["producer"] = _valid_producer_evidence()
    fixture["producer"]["verified_at"] = (GENERATED_AT + timedelta(seconds=1)).isoformat()

    with pytest.raises(ValueError, match="future-dated"):
        validate_truth_snapshot_payload(
            fixture, allow_synthetic_security_matrix=True
        )


def test_contract_binds_github_security_commit_to_producer_evidence() -> None:
    fixture = build_contract_fixture()
    fixture["producer"] = _valid_producer_evidence()
    fixture["inputs"]["github_security"] = {
        "source_id": "github-security-coverage-receipt",
        "schema_version": "GitHubSecurityCoverageReceiptV1",
        "produced_at": GENERATED_AT.isoformat(),
        "state": "fresh",
        "age_hours": 0.0,
        "producer_commit": "b" * 40,
        "cohort_policy": "portfolio-default-attention-v1",
        "cohort_repository_count": 2,
        "path": "/demo-workspace/github-security.json",
        "receipt_id": "sha256:" + "b" * 64,
        "content_sha256": "b" * 64,
    }

    with pytest.raises(ValueError, match="differs from producer evidence"):
        validate_truth_snapshot_payload(
            fixture, allow_synthetic_security_matrix=True
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (lambda value: value.update(repository=7), "repository"),
        (
            lambda value: value.update(expected_repository="other/repository"),
            "does not match expected_repository",
        ),
        (lambda value: value.update(ref=None), "ref"),
        (lambda value: value.update(checkout_role={}), "checkout_role"),
        (lambda value: value.update(checkout_path=7), "checkout_path"),
        (lambda value: value.update(verified_at="not-a-time"), "verified_at"),
        (lambda value: value.update(receipt_id=[]), "receipt_id"),
        (lambda value: value.update(commit="0" * 40), "commit"),
        (lambda value: value.update(extra="fabricated"), "unexpected fields"),
    ),
)
def test_contract_rejects_malformed_producer_evidence(
    mutation: object,
    message: str,
) -> None:
    fixture = build_contract_fixture()
    fixture["producer"] = _valid_producer_evidence()
    mutation(fixture["producer"])

    with pytest.raises(ValueError, match=message):
        validate_truth_snapshot_payload(
            fixture, allow_synthetic_security_matrix=True
        )


@pytest.mark.parametrize(
    ("ref", "checkout_role"),
    (
        ("refs/heads/main\ncanonical", "producer"),
        ("refs/heads/main", "canonical\nproducer"),
    ),
)
def test_contract_rejects_old_delimiter_collision_producer_identities(
    ref: str,
    checkout_role: str,
) -> None:
    fixture = build_contract_fixture()
    producer = _valid_producer_evidence()
    producer.update(ref=ref, checkout_role=checkout_role)
    producer["receipt_id"] = producer_evidence_receipt_id(
        repository=str(producer["repository"]),
        expected_repository=str(producer["expected_repository"]),
        commit=str(producer["commit"]),
        ref=ref,
        checkout_role=checkout_role,
        checkout_path=str(producer["checkout_path"]),
        verified_at=str(producer["verified_at"]),
    )
    fixture["producer"] = producer

    with pytest.raises(ValueError, match="control-free text"):
        validate_truth_snapshot_payload(
            fixture, allow_synthetic_security_matrix=True
        )


def test_contract_rejects_forged_supplementary_project_key() -> None:
    fixture = build_contract_fixture()
    fixture["projects"][0]["identity"]["project_key"] = "supp:forged"

    with pytest.raises(ValueError, match="exactly match"):
        validate_truth_snapshot_payload(fixture)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("warnings", [7], "warnings"),
        (
            "provenance",
            {"derived.activity_status": {"source": 7, "detail": "active"}},
            "provenance",
        ),
        (
            "provenance",
            {
                "derived.activity_status": {
                    "source": "derived",
                    "detail": "active",
                    "extra": "fabricated",
                }
            },
            "provenance",
        ),
    ),
)
def test_contract_rejects_malformed_project_metadata(
    field: str,
    value: object,
    message: str,
) -> None:
    fixture = build_contract_fixture()
    fixture["projects"][0][field] = value

    with pytest.raises(ValueError, match=message):
        validate_truth_snapshot_payload(fixture)


@pytest.mark.parametrize(
    ("section", "field", "value", "message"),
    (
        ("identity", "display_name", 7, "display_name"),
        ("declared", "owner", {}, "owner"),
        ("declared", "automation_eligible", "yes", "automation_eligible"),
        ("derived", "context_files", 7, "context_files"),
        ("derived", "context_file_count", -99, "context_file_count"),
        ("derived", "has_ci", "yes", "has_ci"),
        ("advisory", "notion_momentum", 7, "notion_momentum"),
        ("risk", "risk_factors", {}, "risk_factors"),
        ("risk", "security_risk", "false", "security_risk"),
    ),
)
def test_contract_rejects_malformed_nested_dataclass_types(
    section: str,
    field: str,
    value: object,
    message: str,
) -> None:
    fixture = build_contract_fixture()
    fixture["projects"][0][section][field] = value

    with pytest.raises(ValueError, match=message):
        validate_truth_snapshot_payload(fixture)


def test_contract_rejects_erased_security_risk_and_decision() -> None:
    fixture = build_contract_fixture()
    kestrel = next(
        project
        for project in fixture["projects"]
        if project["identity"]["display_name"] == "Kestrel Loom"
    )
    assert kestrel["security"]["dependabot_high"] == 3
    kestrel["risk"] = {
        "risk_tier": "baseline",
        "risk_factors": [],
        "risk_summary": (
            "No non-security risk factors detected; GitHub security coverage is "
            "partial."
        ),
        "doctor_gap": False,
        "context_risk": False,
        "path_risk": False,
        "security_risk": False,
    }
    kestrel["derived"]["attention_state"] = "active-infra"
    kestrel["declared"]["category"] = "infrastructure"

    with pytest.raises(ValueError, match="risk.*production derivation"):
        validate_truth_snapshot_payload(fixture)


def _append_hidden_duplicate(fixture: dict[str, object]) -> None:
    projects = fixture["projects"]
    duplicate = deepcopy(projects[0])
    duplicate["identity"]["project_key"] = "supp:duplicate-hidden"
    duplicate["identity"]["path"] = "supp:duplicate-hidden"
    projects.append(duplicate)


def test_contract_rejects_appended_hidden_duplicate_by_ordering() -> None:
    fixture = build_contract_fixture()
    _append_hidden_duplicate(fixture)

    with pytest.raises(ValueError, match="producer ordering"):
        validate_truth_snapshot_payload(fixture)


def test_contract_rejects_sorted_hidden_duplicate_by_source_summary() -> None:
    fixture = build_contract_fixture()
    _append_hidden_duplicate(fixture)
    fixture["projects"].sort(
        key=lambda project: (
            project["identity"]["section_marker"].lower(),
            project["identity"]["display_name"].lower(),
        )
    )

    with pytest.raises(ValueError, match="source summary"):
        validate_truth_snapshot_payload(fixture)


@pytest.mark.parametrize(
    "mutation",
    (
        lambda coverage: coverage.pop(1),
        lambda coverage: coverage.pop(3),
        lambda coverage: next(
            row for row in coverage if row["source"] == "github_security"
        ).pop("provider_observed_counts"),
        lambda coverage: next(
            row for row in coverage if row["source"] == "github_security"
        )["provider_observed_counts"].update(dependabot=99),
        lambda coverage: next(
            row for row in coverage if row["source"] == "github_security"
        )["remote_default_branch_counts"].update(observed=99),
        lambda coverage: next(
            row for row in coverage if row["source"] == "github_security"
        ).update(cohort_complete_count=99),
    ),
)
def test_contract_validation_rejects_reduced_or_tampered_coverage(
    mutation: object,
) -> None:
    fixture = build_contract_fixture()
    mutation(fixture["coverage"])

    with pytest.raises(ValueError, match="producer envelope"):
        validate_truth_snapshot_payload(fixture)


def test_shared_coverage_envelope_preserves_supplementary_behavior() -> None:
    fixture = build_contract_fixture()
    supplementary = deepcopy(fixture["projects"][0])
    supplementary["identity"]["project_key"] = "supp:operator-surface"
    projects = [*fixture["projects"], supplementary]

    coverage = build_coverage_envelope(
        projects=projects,
        notion_context_carried_forward=False,
        notion_context_rows=0,
    )
    by_source = {row["source"]: row for row in coverage}

    assert by_source["workspace"]["project_count"] == 4
    assert by_source["github_security"]["project_count"] == 4
    assert by_source["supplementary_registry"] == {
        "source": "supplementary_registry",
        "state": "observed",
        "project_count": 1,
    }


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
    counts = _complete_project(fixture)["security"]["providers"]["dependabot"][
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
    _complete_project(fixture)["declared"]["category"] = "learning"

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

    with pytest.raises(ValueError, match="Legacy security provider"):
        validate_truth_snapshot_payload(fixture)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("coverage_state", "complete"),
        ("alerts_available", True),
        ("receipt_state", "fabricated"),
        ("dependabot_high", 1),
        ("cohort_policy", "portfolio-default-attention-v1"),
    ),
)
def test_unattested_security_validation_rejects_fabricated_metadata(
    field: str,
    value: object,
) -> None:
    fixture = build_contract_fixture()
    security = next(
        project["security"]
        for project in fixture["projects"]
        if project["security"]["receipt_state"] == "unknown"
    )
    security[field] = value

    with pytest.raises(ValueError, match="Unattested security"):
        validate_truth_snapshot_payload(fixture)


def test_receipt_security_validation_rejects_false_cohort_membership() -> None:
    fixture = build_contract_fixture()
    fixture["projects"][0]["security"]["cohort_member"] = False

    with pytest.raises(ValueError, match="cohort member"):
        validate_truth_snapshot_payload(fixture)


@pytest.mark.parametrize("cohort_policy", ("other-policy", 123))
def test_receipt_security_requires_exact_production_cohort_policy(
    cohort_policy: object,
) -> None:
    fixture = build_contract_fixture()
    fixture["projects"][0]["security"]["cohort_policy"] = cohort_policy

    with pytest.raises(ValueError, match="cohort"):
        validate_truth_snapshot_payload(fixture)


def test_legacy_security_accepts_boolean_member_and_string_policy() -> None:
    fields = replace(
        _legacy_security_fields(),
        cohort_member=True,
        cohort_policy="legacy-import-v1",
    )

    _validate_security_fields(fields, "fixture/legacy", GENERATED_AT)


@pytest.mark.parametrize(
    ("cohort_member", "cohort_policy"),
    (("yes", "legacy-import-v1"), (True, 123)),
)
def test_legacy_security_rejects_noncanonical_cohort_types(
    cohort_member: object,
    cohort_policy: object,
) -> None:
    fields = replace(
        _legacy_security_fields(),
        cohort_member=cohort_member,
        cohort_policy=cohort_policy,
    )

    with pytest.raises(ValueError, match="invalid types"):
        _validate_security_fields(fields, "fixture/legacy", GENERATED_AT)


def test_serialized_security_freshness_honors_explicit_validation_context() -> None:
    fixture = build_contract_fixture()
    project = _complete_project(fixture)
    observed_at = GENERATED_AT - timedelta(hours=30)
    project["security"]["source_produced_at"] = observed_at.isoformat()
    for provider in project["security"]["providers"].values():
        provider["observed_at"] = observed_at.isoformat()
    project["repository_state"]["remote_default_branch"]["observed_at"] = (
        observed_at.isoformat()
    )
    stale_project = next(
        item
        for item in fixture["projects"]
        if item["security"]["receipt_state"] == "stale"
    )
    stale_at = GENERATED_AT - timedelta(hours=49)
    stale_project["security"]["source_produced_at"] = stale_at.isoformat()
    for provider in stale_project["security"]["providers"].values():
        provider["observed_at"] = stale_at.isoformat()
    stale_project["repository_state"]["remote_default_branch"]["observed_at"] = (
        stale_at.isoformat()
    )

    validate_truth_snapshot_payload(fixture, security_max_age_hours=48)
    with pytest.raises(ValueError, match="configured freshness window"):
        validate_truth_snapshot_payload(fixture)


def _legacy_security_fields():
    return _build_security_fields(
        {
            "dependabot": {
                "critical": 1,
                "high": 2,
                "receipt_id": 7,
                "available": True,
            },
            "code_scanning": {"available": True},
            "secret_scanning": {"open": 0, "available": True},
        }
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (
            lambda fields: fields.providers["dependabot"].update(reason="fabricated"),
            "envelope",
        ),
        (
            lambda fields: fields.providers["dependabot"].update(
                undocumented_canary=True
            ),
            "provider",
        ),
        (
            lambda fields: fields.providers["dependabot"].update(
                observed_at=GENERATED_AT.isoformat()
            ),
            "envelope",
        ),
        (
            lambda fields: fields.providers["dependabot"].update(
                reason_code="observed"
            ),
            "provider",
        ),
        (
            lambda fields: fields.providers["dependabot"].update(
                pagination_complete=False
            ),
            "counts",
        ),
        (
            lambda fields: fields.providers["dependabot"]["counts"].update(high=-1),
            "counts",
        ),
        (
            lambda fields: fields.providers["dependabot"]["counts"].update(high=True),
            "counts",
        ),
        (
            lambda fields: fields.providers["dependabot"].update(
                state="not_requested", pagination_complete=False, counts={}
            ),
            "unobserved",
        ),
        (
            lambda fields: object.__setattr__(fields, "dependabot_high", 99),
            "does not match",
        ),
        (
            lambda fields: object.__setattr__(fields, "coverage_state", "unknown"),
            "coverage",
        ),
    ),
)
def test_legacy_security_validation_rejects_tampered_envelopes(
    mutation: object,
    message: str,
) -> None:
    fields = _legacy_security_fields()
    mutation(fields)

    with pytest.raises(ValueError, match=message):
        _validate_security_fields(fields, "fixture/legacy", GENERATED_AT)


def test_canonical_payload_validation_rejects_missing_remote_branch_state() -> None:
    fixture = build_contract_fixture()
    del fixture["projects"][0]["repository_state"]["remote_default_branch"]

    with pytest.raises(ValueError, match="requires remote_default_branch"):
        validate_truth_snapshot_payload(fixture)


def _delete_repository_field(repository_state: dict[str, object], field: str) -> None:
    del repository_state[field]


def _set_nested_repository_value(
    repository_state: dict[str, object],
    path: tuple[str | int, ...],
    value: object,
) -> None:
    target: object = repository_state
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


def _delete_nested_repository_value(
    repository_state: dict[str, object],
    path: tuple[str | int, ...],
) -> None:
    target: object = repository_state
    for key in path[:-1]:
        target = target[key]
    del target[path[-1]]


def _replace_all_repository_paths(repository_state: dict[str, object]) -> None:
    private_path = "/Users/example-user/private-repository"
    repository_state["local"]["path"] = private_path
    repository_state["worktrees"][0]["path"] = private_path
    repository_state["topology"]["configured_path"] = private_path
    repository_state["topology"]["selection"]["path"] = private_path


def _replace_all_repository_paths_with_other_demo_path(
    repository_state: dict[str, object],
) -> None:
    other_path = "/demo-workspace/other/project"
    repository_state["local"]["path"] = other_path
    repository_state["worktrees"][0]["path"] = other_path
    repository_state["topology"]["configured_path"] = other_path
    repository_state["topology"]["selection"]["path"] = other_path


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (lambda state: _delete_repository_field(state, "local"), "fields"),
        (lambda state: _delete_repository_field(state, "worktrees"), "fields"),
        (lambda state: _delete_repository_field(state, "topology"), "fields"),
        (
            lambda state: _delete_nested_repository_value(state, ("local", "upstream")),
            "fields",
        ),
        (
            lambda state: _delete_nested_repository_value(
                state, ("worktrees", 0, "dirty")
            ),
            "fields",
        ),
        (
            lambda state: _delete_nested_repository_value(
                state, ("topology", "selection")
            ),
            "fields",
        ),
        (
            lambda state: _set_nested_repository_value(
                state, ("local", "path"), "/Users/example-user/private-local"
            ),
            "[Rr]epository",
        ),
        (
            lambda state: _set_nested_repository_value(
                state, ("worktrees", 0, "path"), "/Users/example-user/private-worktree"
            ),
            "[Rr]epository",
        ),
        (
            lambda state: _set_nested_repository_value(
                state,
                ("topology", "selection", "path"),
                "/Users/example-user/private-selection",
            ),
            "[Rr]epository",
        ),
        (
            lambda state: _set_nested_repository_value(
                state, ("topology", "configured_path"), "/Users/example-user/private-topology"
            ),
            "[Rr]epository",
        ),
        (_replace_all_repository_paths, "public-safe"),
        (_replace_all_repository_paths_with_other_demo_path, "match identity"),
        (
            lambda state: _set_nested_repository_value(
                state, ("local", "head"), "short"
            ),
            "head",
        ),
        (
            lambda state: _set_nested_repository_value(
                state, ("local", "head"), "a" * 41
            ),
            "head",
        ),
        (
            lambda state: _set_nested_repository_value(
                state, ("local", "head"), "0" * 40
            ),
            "head",
        ),
        (
            lambda state: _set_nested_repository_value(
                state, ("worktrees", 0, "head"), "short"
            ),
            "head",
        ),
        (
            lambda state: _set_nested_repository_value(
                state, ("worktrees", 0, "head"), "a" * 41
            ),
            "head",
        ),
        (
            lambda state: _set_nested_repository_value(state, ("local", "dirty"), True),
            "dirty state",
        ),
        (
            lambda state: _set_nested_repository_value(
                state, ("worktrees", 0, "dirty_path_count"), 1
            ),
            "dirty state",
        ),
        (
            lambda state: _set_nested_repository_value(
                state, ("local", "upstream_observation_source"), "unavailable"
            ),
            "upstream",
        ),
        (
            lambda state: _set_nested_repository_value(
                state, ("worktrees", 0, "branch"), None
            ),
            "detached upstream",
        ),
        (
            lambda state: _set_nested_repository_value(
                state, ("worktrees", 0, "branch"), "   "
            ),
            "branch",
        ),
        (
            lambda state: _set_nested_repository_value(
                state, ("worktrees", 0, "branch"), "main.lock"
            ),
            "branch",
        ),
        (
            lambda state: _set_nested_repository_value(
                state, ("local", "upstream"), "origin/"
            ),
            "upstream",
        ),
        (
            lambda state: _set_nested_repository_value(
                state, ("local", "upstream"), "/Users/example-user/private"
            ),
            "upstream",
        ),
        (
            lambda state: _set_nested_repository_value(
                state, ("local", "upstream"), "bad~remote/main"
            ),
            "upstream",
        ),
        (
            lambda state: _set_nested_repository_value(
                state, ("local", "upstream"), "../main"
            ),
            "upstream",
        ),
        (
            lambda state: _set_nested_repository_value(
                state, ("local", "upstream"), "origin/main.lock"
            ),
            "upstream",
        ),
        (
            lambda state: _set_nested_repository_value(
                state, ("topology", "kind"), "fabricated"
            ),
            "topology kind",
        ),
        (
            lambda state: _set_nested_repository_value(
                state, ("topology", "worktree_count"), 99
            ),
            "worktree count",
        ),
        (
            lambda state: _set_nested_repository_value(
                state, ("topology", "worktree_count"), True
            ),
            "worktree count",
        ),
        (
            lambda state: _set_nested_repository_value(
                state, ("topology", "linked_worktree_count"), 99
            ),
            "linked worktree count",
        ),
        (
            lambda state: _set_nested_repository_value(
                state, ("topology", "selection", "candidate_count"), 99
            ),
            "selection",
        ),
        (
            lambda state: _set_nested_repository_value(
                state, ("topology", "selection", "head"), "a" * 41
            ),
            "selection",
        ),
        (
            lambda state: _set_nested_repository_value(
                state, ("topology", "selection", "candidate_count"), True
            ),
            "selection",
        ),
        (
            lambda state: state.update(
                observed_at=(GENERATED_AT + timedelta(minutes=1)).isoformat()
            ),
            "match snapshot generated_at",
        ),
        (
            lambda state: state.update(
                observed_at=(GENERATED_AT - timedelta(days=1)).isoformat()
            ),
            "match snapshot generated_at",
        ),
    ),
)
def test_canonical_payload_validation_rejects_repository_state_attacks(
    mutation: object,
    message: str,
) -> None:
    fixture = build_contract_fixture()
    repository_state = _complete_project(fixture)["repository_state"]
    mutation(repository_state)

    with pytest.raises(ValueError, match=message):
        validate_truth_snapshot_payload(fixture)


def test_canonical_payload_validation_rejects_remote_evidence_without_receipt() -> None:
    fixture = build_contract_fixture()
    unknown = next(
        project
        for project in fixture["projects"]
        if project["security"]["receipt_state"] == "unknown"
    )
    unknown["repository_state"]["remote_default_branch"] = deepcopy(
        _complete_project(fixture)["repository_state"]["remote_default_branch"]
    )

    with pytest.raises(ValueError, match="production normalization"):
        validate_truth_snapshot_payload(fixture)


def test_observed_remote_repository_requires_null_reason() -> None:
    fixture = build_contract_fixture()
    _complete_project(fixture)["repository_state"]["remote_default_branch"][
        "reason"
    ] = "fabricated"

    with pytest.raises(ValueError, match="reason must be null when observed"):
        validate_truth_snapshot_payload(fixture)


def test_stale_remote_repository_requires_observation_time() -> None:
    fixture = build_contract_fixture()
    stale = next(
        project
        for project in fixture["projects"]
        if project["security"]["receipt_state"] == "stale"
    )
    stale["repository_state"]["remote_default_branch"]["observed_at"] = None

    with pytest.raises(ValueError, match="observed_at.*stale"):
        validate_truth_snapshot_payload(fixture)


def test_portable_repository_state_rejects_private_observation_failure_reason() -> None:
    fixture = build_contract_fixture()
    repository_state = fixture["projects"][0]["repository_state"]
    fixture["projects"][0]["repository_state"] = {
        "state": "unknown",
        "observed_at": GENERATED_AT.isoformat(),
        "reason_code": "repository_observation_failed",
        "reason": "/Users/example-user/private-repository",
        "remote_default_branch": repository_state["remote_default_branch"],
    }

    with pytest.raises(ValueError, match="private user path"):
        validate_truth_snapshot_payload(fixture)


@pytest.mark.parametrize(
    ("field_path", "value"),
    (
        (("security", "cohort_policy"), "/home/d/private-policy"),
        (
            ("repository_state", "remote_default_branch", "reason"),
            r"C:\Users\d\private-reason",
        ),
        (
            ("repository_state", "remote_default_branch", "reason"),
            "/private/var/folders/zz/private-reason",
        ),
        (
            ("repository_state", "remote_default_branch", "reason"),
            r"C:\Documents and Settings\d\private-reason",
        ),
        (("declared", "notes"), "owner@example.com"),
        (("declared", "notes"), "owner@localhost"),
        (("declared", "notes"), "/root/private-note"),
        (("warnings",), ["/Users/example-user/private-warning"]),
    ),
)
def test_portable_payload_rejects_private_identity_patterns(
    field_path: tuple[str, ...],
    value: object,
) -> None:
    fixture = build_contract_fixture()
    target = fixture["projects"][0]
    for key in field_path[:-1]:
        target = target[key]
    target[field_path[-1]] = value

    with pytest.raises(ValueError, match="private user path or email"):
        validate_truth_snapshot_payload(fixture)


def test_non_git_identity_cannot_claim_observed_repository_state() -> None:
    fixture = build_contract_fixture()
    fixture["projects"][0]["identity"]["has_git"] = False

    with pytest.raises(ValueError, match="Non-Git identity"):
        validate_truth_snapshot_payload(fixture)


def test_git_identity_can_observe_not_a_repository_race() -> None:
    fixture = build_contract_fixture()
    project = fixture["projects"][0]
    remote = project["repository_state"]["remote_default_branch"]
    project["repository_state"] = {
        "state": "not_a_repository",
        "observed_at": GENERATED_AT.isoformat(),
        "remote_default_branch": remote,
    }
    fixture["coverage"] = build_coverage_envelope(
        projects=fixture["projects"],
        notion_context_carried_forward=False,
        notion_context_rows=0,
    )

    validate_truth_snapshot_payload(fixture)


@pytest.mark.parametrize(
    ("field", "value"), (("default_branch", None), ("head_sha", "short"))
)
def test_canonical_payload_validation_rejects_invalid_remote_branch_shape(
    field: str,
    value: object,
) -> None:
    fixture = build_contract_fixture()
    _complete_project(fixture)["repository_state"]["remote_default_branch"][
        field
    ] = value

    with pytest.raises(ValueError, match="Invalid remote default branch"):
        validate_truth_snapshot_payload(fixture)


@pytest.mark.parametrize(
    ("section", "field", "message"),
    (
        (None, "repository_state", "requires remote_default_branch"),
        ("security", "cohort_member", "cohort member"),
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
