"""Producer-side gate for the portable PortfolioTruth consumer contract."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
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
from src.portfolio_truth_reconcile import _build_security_fields
from src.portfolio_truth_types import SCHEMA_VERSION
from src.portfolio_truth_validate import (
    _validate_security_fields,
    validate_truth_snapshot_payload,
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
    counts = fixture["projects"][0]["security"]["providers"]["dependabot"]["counts"]
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
    project = fixture["projects"][0]
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
    private_path = "/Users/d/private-repository"
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
                state, ("local", "path"), "/Users/d/private-local"
            ),
            "[Rr]epository",
        ),
        (
            lambda state: _set_nested_repository_value(
                state, ("worktrees", 0, "path"), "/Users/d/private-worktree"
            ),
            "[Rr]epository",
        ),
        (
            lambda state: _set_nested_repository_value(
                state,
                ("topology", "selection", "path"),
                "/Users/d/private-selection",
            ),
            "[Rr]epository",
        ),
        (
            lambda state: _set_nested_repository_value(
                state, ("topology", "configured_path"), "/Users/d/private-topology"
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
                state, ("local", "upstream"), "/Users/d/private"
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
    repository_state = fixture["projects"][0]["repository_state"]
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
        fixture["projects"][0]["repository_state"]["remote_default_branch"]
    )

    with pytest.raises(ValueError, match="production normalization"):
        validate_truth_snapshot_payload(fixture)


def test_portable_repository_state_rejects_private_observation_failure_reason() -> None:
    fixture = build_contract_fixture()
    repository_state = fixture["projects"][0]["repository_state"]
    fixture["projects"][0]["repository_state"] = {
        "state": "unknown",
        "observed_at": GENERATED_AT.isoformat(),
        "reason_code": "repository_observation_failed",
        "reason": "/Users/d/private-repository",
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
        (("declared", "notes"), "owner@example.com"),
        (("warnings",), ["/Users/d/private-warning"]),
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

    validate_truth_snapshot_payload(fixture)


@pytest.mark.parametrize(
    ("field", "value"), (("default_branch", None), ("head_sha", "short"))
)
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
    for forbidden in ("/users/", "saagpatel", "saagar", "@gmail.com", "gmail"):
        assert forbidden not in raw
