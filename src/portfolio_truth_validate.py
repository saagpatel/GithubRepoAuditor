from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import fields, is_dataclass
from datetime import datetime
from pathlib import Path
from types import UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints

from src.github_security_coverage import (
    DEFAULT_COHORT_POLICY,
    GITHUB_SECURITY_RECEIPT_SCHEMA_VERSION,
    PROVIDER_NAMES,
    SecurityCoverageError,
    _valid_git_branch,
    _valid_git_oid,
    _valid_git_upstream,
    _validate_remote_repository,
    validate_normalized_security_provider,
)
from src.portfolio_pathing import (
    VALID_MATURITY_PROGRAMS,
    VALID_OPERATING_PATHS,
    VALID_PATH_CONFIDENCE,
    VALID_PATH_OVERRIDES,
)
from src.portfolio_repository_state import (
    _local_from_worktree,
    _select_remote_default_worktree,
    _selected_worktree,
    _tracks_nonmatching_branch,
)
from src.portfolio_truth_coverage import build_coverage_envelope
from src.portfolio_truth_decisions import build_project_decision
from src.portfolio_truth_metadata import (
    build_exclusions,
    build_source_summary,
    build_warnings,
)
from src.portfolio_truth_precedence import PRECEDENCE_MATRIX
from src.portfolio_truth_provenance import REQUIRED_PROJECT_PROVENANCE_KEYS
from src.portfolio_truth_render import registry_project_labels
from src.portfolio_truth_sources import WORKSPACE_EXCLUSION_REASONS
from src.portfolio_truth_types import (
    DERIVATION_POLICY_VERSION,
    SCHEMA_VERSION,
    VALID_ACTIVITY_STATUS,
    VALID_ATTENTION_STATES,
    VALID_CATEGORY_TAGS,
    VALID_CONTEXT_QUALITY,
    VALID_DOCTOR_STANDARDS,
    VALID_LIFECYCLE_STATES,
    VALID_RISK_TIERS,
    AdvisoryFields,
    DeclaredFields,
    DerivedFields,
    IdentityFields,
    PortfolioTruthSnapshot,
    PortfolioTruthProject,
    RiskFields,
    SecurityFields,
)
from src.producer_preflight import ProducerEvidence
from src.registry_parser import _normalize, parse_registry


def validate_truth_snapshot(
    snapshot: PortfolioTruthSnapshot,
    *,
    security_max_age_hours: int = 24,
    allow_synthetic_security_matrix: bool = False,
) -> None:
    if security_max_age_hours <= 0:
        raise ValueError("Security max age hours must be positive.")
    _validate_runtime_dataclass(snapshot, "snapshot")
    if snapshot.schema_version != SCHEMA_VERSION:
        raise ValueError(f"Unexpected schema version: {snapshot.schema_version}")
    if snapshot.derivation_policy_version != DERIVATION_POLICY_VERSION:
        raise ValueError(
            "Unexpected derivation policy version: "
            f"{snapshot.derivation_policy_version}"
        )
    _validate_contract_envelope(snapshot.to_dict())
    expected_order = sorted(
        snapshot.projects,
        key=lambda project: (
            project.identity.section_marker.lower(),
            project.identity.display_name.lower(),
        ),
    )
    if [project.identity.project_key for project in snapshot.projects] != [
        project.identity.project_key for project in expected_order
    ]:
        raise ValueError("PortfolioTruth projects differ from producer ordering.")
    seen_keys: set[str] = set()
    for project in snapshot.projects:
        key = project.identity.project_key
        if key in seen_keys:
            raise ValueError(f"Duplicate project key in truth snapshot: {key}")
        seen_keys.add(key)
        if Path(project.identity.path).is_absolute():
            raise ValueError(
                f"Project path must stay workspace-relative: {project.identity.path}"
            )
        if project.identity.project_key != project.identity.path:
            raise ValueError(
                f"Project key for {key} must exactly match its identity path."
            )
        required_identity = (
            project.identity.project_key,
            project.identity.display_name,
            project.identity.path,
            project.identity.top_level_dir,
            project.identity.group_key,
            project.identity.group_label,
            project.identity.section_marker,
            project.identity.section_label,
        )
        if any(not value.strip() for value in required_identity):
            raise ValueError(f"Project identity for {key!r} has empty required fields.")
        if not isinstance(project.warnings, list) or any(
            not isinstance(value, str) for value in project.warnings
        ):
            raise ValueError(f"Project warnings for {key} must be strings.")
        if not isinstance(project.provenance, dict) or any(
            not isinstance(field_name, str)
            or not field_name
            or not isinstance(source, Mapping)
            or set(source) != {"source", "detail"}
            or not isinstance(source.get("source"), str)
            or not isinstance(source.get("detail"), str)
            for field_name, source in project.provenance.items()
        ):
            raise ValueError(f"Project provenance for {key} is invalid.")
        missing_provenance = sorted(
            REQUIRED_PROJECT_PROVENANCE_KEYS - project.provenance.keys()
        )
        if missing_provenance:
            raise ValueError(
                f"Project provenance for {key} is missing required fields: "
                f"{missing_provenance}"
            )
        empty_sources = sorted(
            field_name
            for field_name in REQUIRED_PROJECT_PROVENANCE_KEYS
            if not project.provenance[field_name]["source"].strip()
        )
        if empty_sources:
            raise ValueError(
                f"Project provenance for {key} has empty required sources: "
                f"{empty_sources}"
            )
        if project.derived.context_quality not in VALID_CONTEXT_QUALITY:
            raise ValueError(
                f"Invalid context quality for {key}: {project.derived.context_quality}"
            )
        if project.derived.primary_context_file not in {"AGENTS.md", "CLAUDE.md"}:
            raise ValueError(
                f"Invalid primary context file for {key}: {project.derived.primary_context_file}"
            )
        if project.derived.activity_status not in VALID_ACTIVITY_STATUS:
            raise ValueError(
                f"Invalid activity status for {key}: {project.derived.activity_status}"
            )
        if project.derived.attention_state not in VALID_ATTENTION_STATES:
            raise ValueError(
                f"Invalid attention state for {key}: {project.derived.attention_state}"
            )
        category = project.declared.category
        if category and category not in VALID_CATEGORY_TAGS:
            raise ValueError(f"Invalid category for {key}: {category}")
        if (
            project.derived.attention_state == "active-infra"
            and category != "infrastructure"
        ):
            raise ValueError(
                f"Active infrastructure attention for {key} requires the "
                "infrastructure category."
            )
        if (
            project.derived.attention_state == "active-product"
            and category != "commercial"
        ):
            raise ValueError(
                f"Active product attention for {key} requires the commercial category."
            )
        completeness_flags = (
            project.derived.project_summary_present,
            project.derived.current_state_present,
            project.derived.stack_present,
            project.derived.run_instructions_present,
            project.derived.known_risks_present,
            project.derived.next_recommended_move_present,
        )
        if project.derived.context_quality in {
            "minimum-viable",
            "standard",
            "full",
        } and not all(completeness_flags):
            raise ValueError(
                f"Context quality for {key} requires all minimum-viable fields to be present."
            )
        lifecycle_state = project.declared.lifecycle_state
        if lifecycle_state and lifecycle_state not in VALID_LIFECYCLE_STATES:
            raise ValueError(f"Invalid lifecycle state for {key}: {lifecycle_state}")
        maturity_program = project.declared.maturity_program
        if maturity_program and maturity_program not in VALID_MATURITY_PROGRAMS:
            raise ValueError(f"Invalid maturity program for {key}: {maturity_program}")
        operating_path = project.declared.operating_path
        if operating_path and operating_path not in VALID_OPERATING_PATHS:
            raise ValueError(f"Invalid operating path for {key}: {operating_path}")
        path_override = project.derived.path_override
        if path_override and path_override not in VALID_PATH_OVERRIDES:
            raise ValueError(f"Invalid path override for {key}: {path_override}")
        if project.derived.path_confidence not in VALID_PATH_CONFIDENCE:
            raise ValueError(
                f"Invalid path confidence for {key}: {project.derived.path_confidence}"
            )
        if project.risk.risk_tier not in VALID_RISK_TIERS:
            raise ValueError(f"Invalid risk tier for {key}: {project.risk.risk_tier}")
        doctor_std = project.declared.doctor_standard
        if doctor_std and doctor_std not in VALID_DOCTOR_STANDARDS:
            raise ValueError(f"Invalid doctor standard for {key}: {doctor_std}")
        if not isinstance(project.identity.has_git, bool):
            raise ValueError(f"Identity has_git for {key} must be boolean.")
        if (
            project.identity.has_git is False
            and project.repository_state.get("state") != "not_a_repository"
        ):
            raise ValueError(
                f"Non-Git identity for {key} must have not_a_repository state."
            )
        _validate_security_fields(
            project.security,
            key,
            snapshot.generated_at,
            security_max_age_hours,
        )
        _validate_repository_state(
            project.repository_state,
            project.security,
            key,
            snapshot.generated_at,
            security_max_age_hours,
        )
        expected_risk, expected_attention = build_project_decision(
            display_name=project.identity.display_name,
            operating_path=project.declared.operating_path,
            path_override=project.derived.path_override,
            context_quality=project.derived.context_quality,
            activity_status=project.derived.activity_status,
            archived=project.derived.archived,
            lifecycle_state=project.declared.lifecycle_state,
            category=project.declared.category,
            criticality=project.declared.criticality,
            doctor_standard=project.declared.doctor_standard,
            known_risks_present=project.derived.known_risks_present,
            run_instructions_present=project.derived.run_instructions_present,
            security_coverage_state=project.security.coverage_state,
            security_high_alerts=project.security.dependabot_high or 0,
            security_critical_alerts=project.security.dependabot_critical or 0,
        )
        if project.risk.to_dict() != expected_risk:
            raise ValueError(
                f"Project risk for {key} differs from production derivation."
            )
        if project.derived.attention_state != expected_attention:
            raise ValueError(
                f"Project attention for {key} differs from production derivation."
            )

    notion_context_rows, notion_context_carried_forward = _validate_snapshot_metadata(
        snapshot,
        security_max_age_hours=security_max_age_hours,
        allow_synthetic_security_matrix=allow_synthetic_security_matrix,
    )
    expected_coverage = build_coverage_envelope(
        projects=snapshot.projects,
        notion_context_carried_forward=notion_context_carried_forward,
        notion_context_rows=notion_context_rows,
    )
    if snapshot.coverage != expected_coverage:
        raise ValueError("PortfolioTruth coverage differs from the producer envelope.")


def _validate_runtime_dataclass(value: object, path: str) -> None:
    """Recursively enforce postponed dataclass annotations at runtime."""
    hints = get_type_hints(type(value))
    for field in fields(value):
        _validate_runtime_value(
            getattr(value, field.name),
            hints[field.name],
            f"{path}.{field.name}",
        )
    if isinstance(value, DerivedFields):
        if value.context_file_count != len(value.context_files):
            raise ValueError(
                f"Portfolio truth {path}.context_file_count differs from context_files."
            )
        if value.readme_char_count < 0 or (
            value.release_count is not None and value.release_count < 0
        ):
            raise ValueError(
                f"Portfolio truth {path} observation counts must be non-negative."
            )
    if isinstance(value, SecurityFields):
        count_fields = (
            value.dependabot_critical,
            value.dependabot_high,
            value.dependabot_medium,
            value.dependabot_low,
            value.code_scanning_critical,
            value.code_scanning_high,
            value.secret_scanning_open,
        )
        if any(count is not None and count < 0 for count in count_fields):
            raise ValueError(
                f"Portfolio truth {path} observation counts must be non-negative."
            )


def _validate_runtime_value(value: object, annotation: object, path: str) -> None:
    if annotation is Any:
        return
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in {Union, UnionType}:
        if not any(_runtime_value_matches(value, option) for option in args):
            raise ValueError(f"Portfolio truth {path} has an invalid runtime type.")
        if value is not None:
            option = next(
                option for option in args if _runtime_value_matches(value, option)
            )
            _validate_runtime_value(value, option, path)
        return
    if origin is list:
        if type(value) is not list:
            raise ValueError(f"Portfolio truth {path} must be an array.")
        for index, item in enumerate(value):
            _validate_runtime_value(item, args[0], f"{path}[{index}]")
        return
    if origin is dict:
        if type(value) is not dict:
            raise ValueError(f"Portfolio truth {path} must be an object.")
        for key, item in value.items():
            _validate_runtime_value(key, args[0], f"{path}.<key>")
            _validate_runtime_value(item, args[1], f"{path}[{key!r}]")
        return
    if isinstance(annotation, type) and is_dataclass(annotation):
        if type(value) is not annotation:
            raise ValueError(f"Portfolio truth {path} has an invalid runtime type.")
        _validate_runtime_dataclass(value, path)
        return
    if not _runtime_value_matches(value, annotation):
        raise ValueError(f"Portfolio truth {path} has an invalid runtime type.")


def _runtime_value_matches(value: object, annotation: object) -> bool:
    if annotation is Any:
        return True
    origin = get_origin(annotation)
    if origin in {Union, UnionType}:
        return any(_runtime_value_matches(value, option) for option in get_args(annotation))
    if origin is list:
        return type(value) is list
    if origin is dict:
        return type(value) is dict
    if annotation is bool:
        return type(value) is bool
    if annotation is int:
        return type(value) is int
    if annotation is str:
        return type(value) is str
    if annotation is datetime:
        return isinstance(value, datetime)
    if annotation is type(None):
        return value is None
    return isinstance(annotation, type) and isinstance(value, annotation)


def _validate_snapshot_metadata(
    snapshot: PortfolioTruthSnapshot,
    *,
    security_max_age_hours: int,
    allow_synthetic_security_matrix: bool,
) -> tuple[int, bool]:
    if snapshot.precedence_matrix != PRECEDENCE_MATRIX:
        raise ValueError(
            "PortfolioTruth precedence matrix differs from the producer contract."
        )
    summary = snapshot.source_summary
    catalog_errors = summary.get("catalog_errors")
    catalog_warnings = summary.get("catalog_warnings")
    legacy_registry_rows = summary.get("legacy_registry_rows")
    notion_context_rows = summary.get("notion_context_rows")
    notion_context_carried_forward = summary.get("notion_context_carried_forward")
    if (
        not isinstance(catalog_errors, list)
        or any(not isinstance(value, str) for value in catalog_errors)
        or not isinstance(catalog_warnings, list)
        or any(not isinstance(value, str) for value in catalog_warnings)
        or not isinstance(legacy_registry_rows, int)
        or isinstance(legacy_registry_rows, bool)
        or legacy_registry_rows < 0
        or not isinstance(notion_context_rows, int)
        or isinstance(notion_context_rows, bool)
        or notion_context_rows < 0
        or not isinstance(notion_context_carried_forward, bool)
    ):
        raise ValueError("PortfolioTruth source summary has invalid bounded inputs.")
    expected_summary = build_source_summary(
        workspace_root=snapshot.workspace_root,
        projects=snapshot.projects,
        catalog_errors=catalog_errors,
        catalog_warnings=catalog_warnings,
        legacy_registry_rows=legacy_registry_rows,
        notion_context_rows=notion_context_rows,
        notion_context_carried_forward=notion_context_carried_forward,
    )
    if summary != expected_summary:
        raise ValueError("PortfolioTruth source summary differs from producer facts.")
    expected_warnings = build_warnings(
        catalog_errors=catalog_errors,
        catalog_warnings=catalog_warnings,
        unresolved_duplicates=summary["unresolved_duplicate_display_names"],
    )
    if snapshot.warnings != expected_warnings:
        raise ValueError("PortfolioTruth warnings differ from producer facts.")
    _validate_snapshot_inputs(
        snapshot,
        notion_context_rows=notion_context_rows,
        notion_context_carried_forward=notion_context_carried_forward,
        security_max_age_hours=security_max_age_hours,
        allow_synthetic_security_matrix=allow_synthetic_security_matrix,
    )
    _validate_snapshot_exclusions(snapshot.exclusions)
    return notion_context_rows, notion_context_carried_forward


def _validate_snapshot_inputs(
    snapshot: PortfolioTruthSnapshot,
    *,
    notion_context_rows: int,
    notion_context_carried_forward: bool,
    security_max_age_hours: int,
    allow_synthetic_security_matrix: bool,
) -> None:
    inputs = snapshot.inputs
    allowed_input_keys = {"catalog", "workspace", "notion", "github_security"}
    if not isinstance(inputs, dict) or not {
        "catalog",
        "workspace",
        "notion",
    }.issubset(inputs) or not set(inputs).issubset(allowed_input_keys):
        raise ValueError("PortfolioTruth input envelope fields are invalid.")
    generated_at = snapshot.generated_at.isoformat()
    catalog = inputs.get("catalog")
    workspace = inputs.get("workspace")
    notion = inputs.get("notion")
    if (
        not isinstance(catalog, dict)
        or set(catalog) != {"source_id", "sha256", "observed_at"}
        or catalog.get("source_id") != "portfolio-catalog"
        or catalog.get("observed_at") != generated_at
        or (
            catalog.get("sha256") is not None
            and (
                not isinstance(catalog.get("sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}", catalog["sha256"]) is None
            )
        )
    ):
        raise ValueError("PortfolioTruth catalog input is invalid.")
    if (
        not isinstance(workspace, dict)
        or workspace
        != {"source_id": "projects-root", "observed_at": generated_at}
    ):
        raise ValueError("PortfolioTruth workspace input is invalid.")
    if not isinstance(notion, dict) or set(notion) != {
        "mode",
        "observed_at",
        "carried_from_generated_at",
    }:
        raise ValueError("PortfolioTruth Notion input fields are invalid.")
    mode = notion.get("mode")
    observed_at = notion.get("observed_at")
    carried_from = notion.get("carried_from_generated_at")
    if notion_context_rows == 0:
        expected_notion = {
            "mode": "unavailable",
            "observed_at": None,
            "carried_from_generated_at": None,
        }
        if notion_context_carried_forward or notion != expected_notion:
            raise ValueError("PortfolioTruth empty Notion input is inconsistent.")
    elif notion_context_carried_forward:
        known_origin = (
            mode == "carried-forward"
            and isinstance(observed_at, str)
            and carried_from == observed_at
        )
        unknown_origin = (
            mode == "unavailable"
            and observed_at is None
            and carried_from is None
        )
        if not known_origin and not unknown_origin:
            raise ValueError("PortfolioTruth carried Notion input is inconsistent.")
        if known_origin and (
            _parse_datetime(observed_at, "inputs.notion.observed_at")
            > snapshot.generated_at
        ):
            raise ValueError("PortfolioTruth Notion input is future-dated.")
    else:
        if (
            mode not in {"live", "verified-snapshot"}
            or not isinstance(observed_at, str)
            or carried_from is not None
        ):
            raise ValueError("PortfolioTruth observed Notion input is inconsistent.")
        if _parse_datetime(observed_at, "inputs.notion.observed_at") > snapshot.generated_at:
            raise ValueError("PortfolioTruth Notion input is future-dated.")
    github_security = inputs.get("github_security")
    has_receipt_rows = any(
        project.security.receipt_state in {"fresh", "stale"}
        for project in snapshot.projects
    )
    if has_receipt_rows and github_security is None:
        raise ValueError(
            "PortfolioTruth GitHub security input is required for receipt-backed rows."
        )
    if github_security is not None:
        _validate_github_security_input(
            github_security,
            snapshot=snapshot,
            security_max_age_hours=security_max_age_hours,
            allow_synthetic_security_matrix=allow_synthetic_security_matrix,
        )


def _validate_github_security_input(
    value: Any,
    *,
    snapshot: PortfolioTruthSnapshot,
    security_max_age_hours: int,
    allow_synthetic_security_matrix: bool,
) -> None:
    allowed = {
        "source_id",
        "schema_version",
        "produced_at",
        "state",
        "age_hours",
        "producer_commit",
        "cohort_policy",
        "cohort_repository_count",
        "path",
        "receipt_id",
        "content_sha256",
    }
    required = allowed - {"receipt_id", "content_sha256"}
    if (
        not isinstance(value, dict)
        or not required.issubset(value)
        or not set(value).issubset(allowed)
    ):
        raise ValueError("PortfolioTruth GitHub security input fields are invalid.")
    text_fields = {
        "source_id",
        "schema_version",
        "producer_commit",
        "cohort_policy",
        "path",
    }
    if any(field in value and not _nonempty_text(value[field]) for field in text_fields):
        raise ValueError("PortfolioTruth GitHub security input text is invalid.")
    if value.get("source_id", "github-security-coverage-receipt") != (
        "github-security-coverage-receipt"
    ) or value.get("schema_version", GITHUB_SECURITY_RECEIPT_SCHEMA_VERSION) != (
        GITHUB_SECURITY_RECEIPT_SCHEMA_VERSION
    ):
        raise ValueError("PortfolioTruth GitHub security source identity is invalid.")
    producer_commit = value.get("producer_commit")
    if producer_commit is not None and (
        not isinstance(producer_commit, str)
        or re.fullmatch(r"[0-9a-f]{40}", producer_commit) is None
        or set(producer_commit) == {"0"}
    ):
        raise ValueError("PortfolioTruth GitHub security producer commit is invalid.")
    snapshot_producer_commit = snapshot.producer.get("commit")
    if snapshot_producer_commit and producer_commit != snapshot_producer_commit:
        raise ValueError(
            "PortfolioTruth GitHub security producer commit differs from producer evidence."
        )
    if value.get("cohort_policy", DEFAULT_COHORT_POLICY) != DEFAULT_COHORT_POLICY:
        raise ValueError("PortfolioTruth GitHub security cohort policy is invalid.")
    produced_at = _parse_datetime(
        value["produced_at"], "inputs.github_security.produced_at"
    )
    if produced_at > snapshot.generated_at:
        raise ValueError("PortfolioTruth GitHub security input is future-dated.")
    age = round((snapshot.generated_at - produced_at).total_seconds() / 3600, 3)
    expected_state = "stale" if age > security_max_age_hours else "fresh"
    if value["state"] != expected_state:
        raise ValueError("PortfolioTruth GitHub security input state is invalid.")
    age_hours = value.get("age_hours")
    if (
        not isinstance(age_hours, (int, float))
        or isinstance(age_hours, bool)
        or age_hours < 0
        or age_hours != age
    ):
        raise ValueError("PortfolioTruth GitHub security input age is invalid.")
    cohort_count = value.get("cohort_repository_count")
    expected_cohort_count = sum(
        project.security.cohort_member
        for project in snapshot.projects
        if not project.identity.project_key.startswith("supp:")
    )
    if (
        not isinstance(cohort_count, int)
        or isinstance(cohort_count, bool)
        or cohort_count < 0
        or cohort_count != expected_cohort_count
    ):
        raise ValueError("PortfolioTruth GitHub security cohort count is invalid.")
    receipt_id = value.get("receipt_id")
    content_sha256 = value.get("content_sha256")
    if (receipt_id is None) != (content_sha256 is None) or (
        receipt_id is not None
        and (
            not isinstance(receipt_id, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", receipt_id) is None
            or not isinstance(content_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", content_sha256) is None
        )
    ):
        raise ValueError("PortfolioTruth GitHub security input identity is invalid.")
    receipt_sources = {
        project.security.source_produced_at
        for project in snapshot.projects
        if project.security.receipt_state in {"fresh", "stale"}
    }
    receipt_states = {
        project.security.receipt_state
        for project in snapshot.projects
        if project.security.receipt_state in {"fresh", "stale"}
    }
    if receipt_sources and (
        value["produced_at"] not in receipt_sources
        if allow_synthetic_security_matrix
        else receipt_sources != {value["produced_at"]}
    ):
        raise ValueError("PortfolioTruth GitHub security source time is inconsistent.")
    if receipt_states and (
        value["state"] not in receipt_states
        if allow_synthetic_security_matrix
        else receipt_states != {value["state"]}
    ):
        raise ValueError("PortfolioTruth GitHub security receipt state is inconsistent.")


def _validate_snapshot_exclusions(exclusions: Any) -> None:
    if not isinstance(exclusions, dict) or set(exclusions) != {
        "policy_version",
        "counts",
    }:
        raise ValueError("PortfolioTruth exclusions envelope fields are invalid.")
    counts = exclusions.get("counts")
    if not isinstance(counts, dict) or any(
        not isinstance(key, str)
        or key not in WORKSPACE_EXCLUSION_REASONS
        or not isinstance(value, int)
        or isinstance(value, bool)
        or value <= 0
        for key, value in counts.items()
    ):
        raise ValueError("PortfolioTruth exclusion counts are invalid.")
    if exclusions != build_exclusions(counts):
        raise ValueError("PortfolioTruth exclusions differ from producer policy.")


def _validate_security_fields(
    security: SecurityFields,
    project_key: str,
    generated_at: datetime,
    security_max_age_hours: int = 24,
) -> None:
    """Validate receipt-backed provider envelopes after receipt normalization."""
    providers = security.providers
    if not isinstance(providers, Mapping):
        raise ValueError(f"Security providers for {project_key} must be an object.")
    if not isinstance(security.cohort_member, bool) or not isinstance(
        security.cohort_policy, str
    ):
        raise ValueError(
            f"Security cohort metadata for {project_key} has invalid types."
        )

    has_receipt_evidence = bool(
        security.receipt_schema_version
        or security.source_produced_at
        or security.receipt_state in {"fresh", "stale"}
    )
    if not has_receipt_evidence:
        if providers:
            _validate_legacy_security_fields(security, project_key)
        else:
            _validate_unattested_security_fields(security, project_key)
        return
    if security.receipt_schema_version != GITHUB_SECURITY_RECEIPT_SCHEMA_VERSION:
        raise ValueError(
            f"Invalid security receipt schema for {project_key}: "
            f"{security.receipt_schema_version}"
        )
    if security.receipt_state not in {"fresh", "stale"}:
        raise ValueError(
            f"Invalid security receipt state for {project_key}: "
            f"{security.receipt_state}"
        )
    if (
        security.cohort_member is not True
        or security.cohort_policy != DEFAULT_COHORT_POLICY
    ):
        raise ValueError(
            f"Receipt-backed security evidence for {project_key} must be a cohort "
            "member under the production cohort policy."
        )
    produced_at = _parse_datetime(
        security.source_produced_at,
        f"projects[{project_key}].security.source_produced_at",
    )
    receipt_age_hours = (generated_at - produced_at).total_seconds() / 3600
    if receipt_age_hours < -0.05:
        raise ValueError(f"Security receipt for {project_key} is future-dated.")
    expected_receipt_state = (
        "stale" if receipt_age_hours > security_max_age_hours else "fresh"
    )
    if security.receipt_state != expected_receipt_state:
        raise ValueError(
            f"Security receipt state for {project_key} does not match the "
            "configured freshness window."
        )
    if set(providers) != set(PROVIDER_NAMES):
        raise ValueError(
            f"Security providers for {project_key} must contain exactly: "
            f"{', '.join(PROVIDER_NAMES)}"
        )

    states: dict[str, str] = {}
    count_fields = {
        "dependabot": {
            "critical": "dependabot_critical",
            "high": "dependabot_high",
            "medium": "dependabot_medium",
            "low": "dependabot_low",
        },
        "code_scanning": {
            "critical": "code_scanning_critical",
            "high": "code_scanning_high",
        },
        "secret_scanning": {"open": "secret_scanning_open"},
    }
    for name in PROVIDER_NAMES:
        provider = providers[name]
        try:
            validate_normalized_security_provider(
                name,
                provider,
                produced_at=produced_at,
                current=generated_at,
                max_age_hours=security_max_age_hours,
                receipt_is_stale=security.receipt_state == "stale",
            )
        except SecurityCoverageError as exc:
            raise ValueError(
                f"Invalid security provider for {project_key}/{name}: {exc}"
            ) from exc
        state = str(provider["state"])
        states[name] = state
        counts = provider["counts"]
        if security.receipt_state == "stale" and state == "observed":
            raise ValueError(
                f"Stale security receipt for {project_key} cannot retain "
                f"an observed {name} provider."
            )

        for count_name, field_name in count_fields[name].items():
            expected = counts[count_name] if state == "observed" else None
            if getattr(security, field_name) != expected:
                raise ValueError(
                    f"Security count {field_name} for {project_key} does not "
                    f"match the normalized {name} provider."
                )

    observed_count = sum(state == "observed" for state in states.values())
    if security.receipt_state == "stale":
        expected_coverage = "stale"
    elif observed_count == len(PROVIDER_NAMES):
        expected_coverage = "complete"
    elif observed_count:
        expected_coverage = "partial"
    elif any(state == "stale" for state in states.values()):
        expected_coverage = "stale"
    else:
        expected_coverage = "unknown"
    if security.coverage_state != expected_coverage:
        raise ValueError(
            f"Security coverage state for {project_key} must be {expected_coverage}."
        )
    if security.alerts_available is not (expected_coverage == "complete"):
        raise ValueError(
            f"Security alerts_available for {project_key} does not match coverage."
        )


def _validate_legacy_security_fields(
    security: SecurityFields,
    project_key: str,
) -> None:
    if (
        security.receipt_schema_version
        or security.source_produced_at
        or security.receipt_state != "unknown"
        or set(security.providers) != set(PROVIDER_NAMES)
    ):
        raise ValueError(f"Legacy security evidence for {project_key} is invalid.")
    provider_keys = {
        "state",
        "observed_at",
        "http_status",
        "reason",
        "etag",
        "last_modified",
        "pagination_complete",
        "counts",
    }
    count_fields = {
        "dependabot": {
            "critical": "dependabot_critical",
            "high": "dependabot_high",
            "medium": "dependabot_medium",
            "low": "dependabot_low",
        },
        "code_scanning": {
            "critical": "code_scanning_critical",
            "high": "code_scanning_high",
        },
        "secret_scanning": {"open": "secret_scanning_open"},
    }
    states: dict[str, str] = {}
    for name in PROVIDER_NAMES:
        provider = security.providers[name]
        if not isinstance(provider, Mapping) or set(provider) != provider_keys:
            raise ValueError(
                f"Legacy security provider for {project_key}/{name} is invalid."
            )
        state = provider.get("state")
        if state not in {"observed", "not_requested"}:
            raise ValueError(
                f"Legacy security provider state for {project_key}/{name} is invalid."
            )
        states[name] = state
        if (
            provider.get("observed_at") is not None
            or provider.get("http_status") is not None
            or provider.get("reason") != "legacy_ghas_entry"
            or provider.get("etag") is not None
            or provider.get("last_modified") is not None
        ):
            raise ValueError(
                f"Legacy security provider envelope for {project_key}/{name} is invalid."
            )
        counts = provider.get("counts")
        if state == "observed":
            if (
                provider.get("pagination_complete") is not True
                or not isinstance(counts, Mapping)
                or any(
                    not isinstance(value, int) or isinstance(value, bool) or value < 0
                    for value in counts.values()
                )
            ):
                raise ValueError(
                    f"Legacy security provider counts for {project_key}/{name} are invalid."
                )
        elif provider.get("pagination_complete") is not False or counts is not None:
            raise ValueError(
                f"Legacy unobserved provider for {project_key}/{name} is invalid."
            )
        for count_name, field_name in count_fields[name].items():
            expected = counts.get(count_name, 0) if state == "observed" else None
            if getattr(security, field_name) != expected:
                raise ValueError(
                    f"Legacy security count for {project_key}/{field_name} "
                    "does not match its provider."
                )

    observed_count = sum(state == "observed" for state in states.values())
    expected_coverage = (
        "complete"
        if observed_count == 3
        else "partial"
        if observed_count
        else "unknown"
    )
    if (
        security.coverage_state != expected_coverage
        or security.alerts_available is not (expected_coverage == "complete")
    ):
        raise ValueError(f"Legacy security coverage for {project_key} is inconsistent.")


def _validate_unattested_security_fields(
    security: SecurityFields,
    project_key: str,
) -> None:
    count_values = (
        security.dependabot_critical,
        security.dependabot_high,
        security.dependabot_medium,
        security.dependabot_low,
        security.code_scanning_critical,
        security.code_scanning_high,
        security.secret_scanning_open,
    )
    if (
        security.alerts_available is not False
        or security.coverage_state != "unknown"
        or security.receipt_schema_version
        or security.receipt_state != "unknown"
        or security.source_produced_at
        or any(value is not None for value in count_values)
    ):
        raise ValueError(
            f"Unattested security evidence for {project_key} is inconsistent."
        )
    valid_cohort = (
        security.cohort_member is True
        and security.cohort_policy == "portfolio-default-attention-v1"
    ) or (security.cohort_member is False and not security.cohort_policy)
    if not valid_cohort:
        raise ValueError(
            f"Unattested security cohort metadata for {project_key} is inconsistent."
        )


def _validate_repository_state(
    repository_state: dict[str, Any],
    security: SecurityFields,
    project_key: str,
    generated_at: datetime,
    security_max_age_hours: int,
) -> None:
    if not isinstance(repository_state, Mapping):
        raise ValueError(f"Repository state for {project_key} must be an object.")
    has_receipt_evidence = bool(security.receipt_schema_version)
    remote = repository_state.get("remote_default_branch")
    if not isinstance(remote, dict):
        raise ValueError(
            f"Repository state for {project_key} requires remote_default_branch."
        )
    if has_receipt_evidence:
        produced_at = _parse_datetime(
            security.source_produced_at,
            f"projects[{project_key}].security.source_produced_at",
        )
        try:
            expected_remote = _validate_remote_repository(
                remote,
                receipt_is_stale=security.receipt_state == "stale",
                produced_at=produced_at,
                current=generated_at,
                max_age_hours=security_max_age_hours,
            )
        except SecurityCoverageError as exc:
            raise ValueError(
                f"Invalid remote default branch for {project_key}: {exc}"
            ) from exc
    else:
        expected_remote = {
            "state": "unknown",
            "reason_code": "not_requested",
            "reason": (
                "no independent live remote read was performed by portfolio generation"
            ),
        }
    if remote != expected_remote:
        raise ValueError(
            f"Remote default branch for {project_key} differs from production "
            "normalization."
        )
    _validate_repository_state_shape(
        repository_state,
        expected_remote=expected_remote,
        project_key=project_key,
        generated_at=generated_at,
    )


def _validate_repository_state_shape(
    repository_state: Mapping[str, Any],
    *,
    expected_remote: dict[str, Any],
    project_key: str,
    generated_at: datetime,
) -> None:
    state = repository_state.get("state")
    if state not in {"observed", "unknown", "not_a_repository"}:
        raise ValueError(f"Invalid repository state for {project_key}.")
    observed_at = _parse_datetime(
        repository_state.get("observed_at"),
        f"projects[{project_key}].repository_state.observed_at",
    )
    if observed_at != generated_at:
        raise ValueError(
            f"Repository state for {project_key} must match snapshot generated_at."
        )
    if state == "not_a_repository":
        _require_repository_keys(
            repository_state,
            {"state", "observed_at", "remote_default_branch"},
            project_key,
            "repository state",
        )
        return
    if state == "unknown" and "topology" not in repository_state:
        _require_repository_keys(
            repository_state,
            {
                "state",
                "observed_at",
                "reason_code",
                "reason",
                "remote_default_branch",
            },
            project_key,
            "repository state",
        )
        if repository_state.get(
            "reason_code"
        ) != "repository_observation_failed" or not _nonempty_text(
            repository_state.get("reason")
        ):
            raise ValueError(
                f"Repository observation failure for {project_key} is invalid."
            )
        return

    required = {
        "state",
        "observed_at",
        "local",
        "remote_default_branch",
        "topology",
        "worktrees",
    }
    if state == "unknown":
        required.remove("local")
        required.update({"reason_code", "reason"})
        if "local" in repository_state:
            if repository_state.get("local") is None:
                raise ValueError(
                    f"Unknown repository state for {project_key} must omit null local."
                )
            required.add("local")
    _require_repository_keys(
        repository_state,
        required,
        project_key,
        "repository state",
    )
    worktrees = repository_state.get("worktrees")
    if not isinstance(worktrees, list) or not worktrees:
        raise ValueError(f"Repository worktrees for {project_key} are invalid.")
    for index, worktree in enumerate(worktrees):
        _validate_worktree(worktree, project_key=project_key, index=index)
    paths = [worktree["path"] for worktree in worktrees]
    if len({Path(path).resolve() for path in paths}) != len(paths):
        raise ValueError(f"Repository worktree paths for {project_key} are duplicated.")

    topology = repository_state.get("topology")
    if not isinstance(topology, Mapping):
        raise ValueError(f"Repository topology for {project_key} is invalid.")
    kind = topology.get("kind")
    topology_keys = {
        "kind",
        "configured_path",
        "worktree_count",
        "linked_worktree_count",
        "selection",
    }
    if kind == "bare_coordinator":
        topology_keys.add("coordinator")
    elif kind != "working_repository":
        raise ValueError(f"Repository topology kind for {project_key} is invalid.")
    _require_repository_keys(topology, topology_keys, project_key, "topology")
    configured_path = topology.get("configured_path")
    if not any(_same_repository_path(configured_path, path) for path in paths):
        raise ValueError(
            f"Repository configured path for {project_key} is not a worktree."
        )
    worktree_count = topology.get("worktree_count")
    if (
        not isinstance(worktree_count, int)
        or isinstance(worktree_count, bool)
        or worktree_count != len(worktrees)
    ):
        raise ValueError(f"Repository worktree count for {project_key} is invalid.")
    coordinator_count = sum(item.get("state") == "coordinator" for item in worktrees)
    expected_linked_count = len(worktrees) - coordinator_count
    if kind == "working_repository":
        expected_linked_count -= 1
        if coordinator_count:
            raise ValueError(
                f"Working repository topology for {project_key} has a coordinator."
            )
    elif coordinator_count != 1:
        raise ValueError(
            f"Bare repository topology for {project_key} requires one coordinator."
        )
    linked_worktree_count = topology.get("linked_worktree_count")
    if (
        not isinstance(linked_worktree_count, int)
        or isinstance(linked_worktree_count, bool)
        or linked_worktree_count != expected_linked_count
    ):
        raise ValueError(
            f"Repository linked worktree count for {project_key} is invalid."
        )
    if kind == "bare_coordinator":
        _validate_coordinator(
            topology.get("coordinator"),
            worktrees,
            configured_path=str(configured_path),
            project_key=project_key,
        )

    selection = topology.get("selection")
    _validate_selection(selection, project_key=project_key)
    expected_selection = _select_remote_default_worktree(worktrees, expected_remote)
    if selection != expected_selection:
        raise ValueError(f"Repository selection for {project_key} is inconsistent.")

    local = repository_state.get("local")
    if local is not None:
        _validate_local(local, project_key=project_key, label="local")
    if selection.get("state") == "selected":
        if state != "observed" or local != _local_from_worktree(
            _selected_worktree(worktrees, selection)
        ):
            raise ValueError(
                f"Selected repository worktree for {project_key} does not match local."
            )
        return

    if kind == "bare_coordinator":
        if (
            state != "unknown"
            or local is not None
            or repository_state.get("reason_code") != selection.get("reason_code")
            or repository_state.get("reason") != selection.get("reason")
        ):
            raise ValueError(
                f"Bare repository uncertainty for {project_key} is inconsistent."
            )
        return

    configured = next(
        item
        for item in worktrees
        if _same_repository_path(item["path"], configured_path)
    )
    if configured.get("state") != "observed":
        raise ValueError(
            f"Configured repository worktree for {project_key} is not observed."
        )
    expected_local = _local_from_worktree(configured)
    if local != expected_local:
        raise ValueError(
            f"Configured repository worktree for {project_key} does not match local."
        )
    if expected_remote.get("state") == "observed":
        expected_state = "unknown"
        expected_reason_code = selection.get("reason_code")
        expected_reason = selection.get("reason")
    elif _tracks_nonmatching_branch(expected_local):
        expected_state = "unknown"
        expected_reason_code = "nonstandard_upstream_requires_remote_default_evidence"
        expected_reason = (
            "the configured worktree tracks a differently named branch, and "
            "independent remote-default evidence is unavailable"
        )
    else:
        expected_state = "observed"
        expected_reason_code = expected_reason = None
    if state != expected_state or (
        state == "unknown"
        and (
            repository_state.get("reason_code") != expected_reason_code
            or repository_state.get("reason") != expected_reason
        )
    ):
        raise ValueError(f"Repository state for {project_key} is inconsistent.")


def _validate_local(
    value: Any,
    *,
    project_key: str,
    label: str,
    require_exact_keys: bool = True,
) -> None:
    if not isinstance(value, Mapping):
        raise ValueError(f"Repository {label} for {project_key} is invalid.")
    local_keys = {
        "path",
        "head",
        "branch",
        "dirty",
        "dirty_path_count",
        "upstream",
        "upstream_branch",
        "upstream_remote",
        "upstream_observation_source",
        "ahead",
        "behind",
    }
    if require_exact_keys:
        _require_repository_keys(value, local_keys, project_key, label)
    elif not local_keys.issubset(value):
        raise ValueError(f"Repository {label} fields for {project_key} are invalid.")
    if not _nonempty_text(value.get("path")):
        raise ValueError(f"Repository {label} path for {project_key} is invalid.")
    if not _valid_git_oid(value.get("head")):
        raise ValueError(f"Repository {label} head for {project_key} is invalid.")
    branch = value.get("branch")
    if branch is not None and not _valid_git_branch(branch):
        raise ValueError(f"Repository {label} branch for {project_key} is invalid.")
    dirty = value.get("dirty")
    count = value.get("dirty_path_count")
    if (
        not isinstance(dirty, bool)
        or not isinstance(count, int)
        or isinstance(count, bool)
        or count < 0
        or dirty is not (count > 0)
    ):
        raise ValueError(
            f"Repository {label} dirty state for {project_key} is invalid."
        )
    upstream = value.get("upstream")
    upstream_branch = value.get("upstream_branch")
    upstream_remote = value.get("upstream_remote")
    expected_source = "local_tracking_ref" if upstream else "unavailable"
    if (upstream is not None and not _valid_git_upstream(upstream)) or value.get(
        "upstream_observation_source"
    ) != expected_source:
        raise ValueError(f"Repository {label} upstream for {project_key} is invalid.")
    if upstream is None:
        if upstream_branch is not None or upstream_remote is not None:
            raise ValueError(
                f"Repository {label} upstream identity for {project_key} is invalid."
            )
    elif not _valid_git_branch(upstream_branch) or not _valid_upstream_identity(
        upstream=upstream,
        upstream_branch=upstream_branch,
        upstream_remote=upstream_remote,
    ):
        raise ValueError(
            f"Repository {label} upstream identity for {project_key} is invalid."
        )
    if branch is None and any(
        item is not None for item in (upstream, upstream_branch, upstream_remote)
    ):
        raise ValueError(
            f"Repository {label} detached upstream for {project_key} is invalid."
        )
    for field_name in ("ahead", "behind"):
        count_value = value.get(field_name)
        if upstream is None:
            valid = count_value is None
        else:
            valid = (
                isinstance(count_value, int)
                and not isinstance(count_value, bool)
                and count_value >= 0
            )
        if not valid:
            raise ValueError(
                f"Repository {label} {field_name} for {project_key} is invalid."
            )


def _validate_worktree(value: Any, *, project_key: str, index: int) -> None:
    if not isinstance(value, Mapping):
        raise ValueError(f"Repository worktree {index} for {project_key} is invalid.")
    state = value.get("state")
    label = f"worktree {index}"
    if state == "observed":
        _require_repository_keys(
            value,
            {
                "state",
                "path",
                "head",
                "branch",
                "dirty",
                "dirty_path_count",
                "upstream",
                "upstream_branch",
                "upstream_remote",
                "upstream_observation_source",
                "ahead",
                "behind",
                "detached",
                "bare",
            },
            project_key,
            label,
        )
        _validate_local(
            value,
            project_key=project_key,
            label=label,
            require_exact_keys=False,
        )
        if value.get("bare") is not False or not isinstance(
            value.get("detached"), bool
        ):
            raise ValueError(f"Repository {label} flags for {project_key} are invalid.")
        if (value["branch"] is None) is not value["detached"]:
            raise ValueError(
                f"Repository {label} branch state for {project_key} is invalid."
            )
        return
    if state == "coordinator":
        _require_repository_keys(
            value,
            {
                "state",
                "path",
                "head",
                "branch",
                "detached",
                "bare",
                "dirty",
                "dirty_path_count",
            },
            project_key,
            label,
        )
        if (
            not _nonempty_text(value.get("path"))
            or value.get("detached") is not False
            or value.get("bare") is not True
            or value.get("dirty") is not None
            or value.get("dirty_path_count") is not None
            or not _optional_git_head(value.get("head"))
            or not _optional_git_branch(value.get("branch"))
        ):
            raise ValueError(f"Repository {label} for {project_key} is invalid.")
        return
    if state == "unknown":
        _require_repository_keys(
            value,
            {
                "state",
                "reason_code",
                "reason",
                "path",
                "head",
                "branch",
                "detached",
                "bare",
                "dirty",
                "dirty_path_count",
            },
            project_key,
            label,
        )
        if (
            value.get("reason_code") != "worktree_observation_failed"
            or value.get("reason") != "git could not observe the linked worktree"
            or not _nonempty_text(value.get("path"))
            or not _valid_git_oid(value.get("head"))
            or not _optional_git_branch(value.get("branch"))
            or not isinstance(value.get("detached"), bool)
            or value.get("bare") is not False
            or value.get("dirty") is not None
            or value.get("dirty_path_count") is not None
        ):
            raise ValueError(f"Repository {label} for {project_key} is invalid.")
        if (value["branch"] is None) is not value["detached"]:
            raise ValueError(
                f"Repository {label} branch state for {project_key} is invalid."
            )
        return
    raise ValueError(f"Repository {label} state for {project_key} is invalid.")


def _valid_upstream_identity(
    *,
    upstream: str,
    upstream_branch: str,
    upstream_remote: Any,
) -> bool:
    if upstream_remote == ".":
        return upstream == upstream_branch
    return (
        _valid_git_branch(upstream_remote)
        and upstream == f"{upstream_remote}/{upstream_branch}"
    )


def _validate_coordinator(
    value: Any,
    worktrees: list[dict[str, Any]],
    *,
    configured_path: str,
    project_key: str,
) -> None:
    if not isinstance(value, Mapping):
        raise ValueError(f"Repository coordinator for {project_key} is invalid.")
    _require_repository_keys(
        value,
        {"path", "head", "head_state", "branch"},
        project_key,
        "coordinator",
    )
    matching = [
        item
        for item in worktrees
        if item.get("state") == "coordinator"
        and _same_repository_path(item.get("path"), configured_path)
    ]
    if len(matching) != 1:
        raise ValueError(f"Repository coordinator for {project_key} is inconsistent.")
    head = value.get("head")
    expected_head_state = "observed" if head else "dangling"
    if (
        value.get("path") != configured_path
        or value.get("head_state") != expected_head_state
        or not _optional_git_head(head)
        or not _optional_git_branch(value.get("branch"))
    ):
        raise ValueError(f"Repository coordinator for {project_key} is inconsistent.")


def _validate_selection(value: Any, *, project_key: str) -> None:
    if not isinstance(value, Mapping):
        raise ValueError(f"Repository selection for {project_key} is invalid.")
    state = value.get("state")
    keys = {"source", "state", "reason_code", "reason", "candidate_count"}
    if state == "selected":
        keys.update({"path", "head", "branch"})
    elif state != "unknown":
        raise ValueError(f"Repository selection for {project_key} is invalid.")
    _require_repository_keys(value, keys, project_key, "selection")
    candidate_count = value.get("candidate_count")
    if (
        not _nonempty_text(value.get("source"))
        or not _nonempty_text(value.get("reason_code"))
        or not isinstance(candidate_count, int)
        or isinstance(candidate_count, bool)
        or candidate_count < 0
    ):
        raise ValueError(f"Repository selection for {project_key} is invalid.")
    if state == "selected":
        if (
            value.get("reason") is not None
            or not _nonempty_text(value.get("path"))
            or not _valid_git_oid(value.get("head"))
            or not _optional_git_branch(value.get("branch"))
        ):
            raise ValueError(f"Repository selection for {project_key} is invalid.")
    elif not _nonempty_text(value.get("reason")):
        raise ValueError(f"Repository selection for {project_key} is invalid.")


def _require_repository_keys(
    value: Mapping[str, Any],
    expected: set[str],
    project_key: str,
    label: str,
) -> None:
    if set(value) != expected:
        raise ValueError(f"Repository {label} fields for {project_key} are invalid.")


def _nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _optional_git_head(value: Any) -> bool:
    return value is None or _valid_git_oid(value)


def _optional_git_branch(value: Any) -> bool:
    return value is None or _valid_git_branch(value)


def _same_repository_path(left: Any, right: Any) -> bool:
    return (
        isinstance(left, str)
        and isinstance(right, str)
        and Path(left).resolve() == Path(right).resolve()
    )


def validate_truth_snapshot_payload(
    payload: Mapping[str, Any],
    *,
    security_max_age_hours: int = 24,
    allow_synthetic_security_matrix: bool = False,
) -> None:
    """Fully validate serialized truth, including canonical byte-shape fidelity."""
    if payload.get("workspace_root") != "/demo-workspace":
        raise ValueError(
            "Portable PortfolioTruth workspace_root must be exactly /demo-workspace."
        )
    if _contains_private_identity(payload):
        raise ValueError(
            "Portable Repository/upstream paths are not public-safe: payload contains "
            "a private user path or email identity."
        )
    contract_fixture = payload.get("contract_fixture")
    is_documented_contract_matrix = (
        isinstance(contract_fixture, Mapping)
        and contract_fixture
        == {
            "contract_version": "ghra-pcc-portfolio-truth.v1",
            "deterministic": True,
            "producer_evidence": "absent",
            "security_evidence_semantics": (
                "synthetic-cross-receipt-state-matrix"
            ),
        }
        and payload.get("producer") == {}
    )
    github_security = (
        payload.get("inputs", {}).get("github_security")
        if isinstance(payload.get("inputs"), Mapping)
        else None
    )
    if isinstance(github_security, Mapping) and (
        github_security.get("receipt_id") is None
        or github_security.get("content_sha256") is None
    ):
        raise ValueError(
            "Portable PortfolioTruth GitHub security input requires both receipt_id "
            "and content_sha256."
        )
    canonical = canonicalize_truth_snapshot_payload(
        payload,
        security_max_age_hours=security_max_age_hours,
        allow_synthetic_security_matrix=(
            allow_synthetic_security_matrix or is_documented_contract_matrix
        ),
    )
    for project in canonical["projects"]:
        _validate_portable_repository_paths(
            project["repository_state"],
            project_key=project["identity"]["project_key"],
            project_path=project["identity"]["path"],
        )
    supplied = _without_documented_contract_canaries(payload)
    mismatch = _first_payload_mismatch(supplied, canonical)
    if mismatch is not None:
        raise ValueError(
            "Serialized PortfolioTruth snapshot differs from canonical "
            f"reconstruction at {mismatch}."
        )


def _validate_portable_repository_paths(
    repository_state: Mapping[str, Any],
    *,
    project_key: str,
    project_path: str,
) -> None:
    paths: list[Any] = []
    local = repository_state.get("local")
    if isinstance(local, Mapping):
        paths.append(local.get("path"))
    topology = repository_state.get("topology")
    if isinstance(topology, Mapping):
        paths.append(topology.get("configured_path"))
        selection = topology.get("selection")
        if isinstance(selection, Mapping) and selection.get("state") == "selected":
            paths.append(selection.get("path"))
        coordinator = topology.get("coordinator")
        if isinstance(coordinator, Mapping):
            paths.append(coordinator.get("path"))
    worktrees = repository_state.get("worktrees")
    if isinstance(worktrees, list):
        paths.extend(
            worktree.get("path")
            for worktree in worktrees
            if isinstance(worktree, Mapping)
        )
    if any(
        not isinstance(path, str)
        or not path.startswith("/demo-workspace/")
        or ".." in Path(path).parts
        for path in paths
    ):
        raise ValueError(
            f"Portable repository paths for {project_key} are not public-safe."
        )
    if isinstance(topology, Mapping) and topology.get("configured_path") != str(
        Path("/demo-workspace") / project_path
    ):
        raise ValueError(
            f"Portable configured path for {project_key} does not match identity."
        )


def _contains_private_identity(value: Any) -> bool:
    if isinstance(value, str):
        return (
            re.search(
                r"(?:^|[/\\])(?:users|home|root)[/\\]", value, re.IGNORECASE
            )
            is not None
            or re.search(
                r"(?:^|[/\\])private[/\\]var[/\\]folders(?:[/\\]|$)",
                value,
                re.IGNORECASE,
            )
            is not None
            or re.search(
                r"(?:^|[/\\])documents and settings[/\\]",
                value,
                re.IGNORECASE,
            )
            is not None
            or re.search(
                r"[A-Z0-9._%+-]+@[A-Z0-9.-]+",
                value,
                re.IGNORECASE,
            )
            is not None
        )
    if isinstance(value, Mapping):
        return any(
            _contains_private_identity(item)
            for pair in value.items()
            for item in pair
        )
    if isinstance(value, list):
        return any(_contains_private_identity(item) for item in value)
    return False


def canonicalize_truth_snapshot_payload(
    payload: Mapping[str, Any],
    *,
    security_max_age_hours: int = 24,
    allow_synthetic_security_matrix: bool = False,
) -> dict[str, Any]:
    """Return the canonical serializer output for one raw truth snapshot."""
    snapshot = _snapshot_from_payload(payload)
    validate_truth_snapshot(
        snapshot,
        security_max_age_hours=security_max_age_hours,
        allow_synthetic_security_matrix=allow_synthetic_security_matrix,
    )
    return snapshot.to_dict()


def _without_documented_contract_canaries(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Remove only the two additive paths documented by the fixture manifest."""
    supplied = deepcopy(dict(payload))
    supplied.pop("contract_fixture", None)
    projects = supplied.get("projects")
    if projects and isinstance(projects, list) and isinstance(projects[0], dict):
        projects[0].pop("additive_contract_canary", None)
    return supplied


def _first_payload_mismatch(
    supplied: object,
    canonical: object,
    path: str = "$",
) -> str | None:
    if isinstance(supplied, dict) and isinstance(canonical, dict):
        for key in sorted(set(supplied) | set(canonical)):
            child = f"{path}.{key}"
            if key not in supplied or key not in canonical:
                return child
            mismatch = _first_payload_mismatch(supplied[key], canonical[key], child)
            if mismatch is not None:
                return mismatch
        return None
    if isinstance(supplied, list) and isinstance(canonical, list):
        if len(supplied) != len(canonical):
            return path
        for index, (supplied_item, canonical_item) in enumerate(
            zip(supplied, canonical, strict=True)
        ):
            mismatch = _first_payload_mismatch(
                supplied_item, canonical_item, f"{path}[{index}]"
            )
            if mismatch is not None:
                return mismatch
        return None
    return None if supplied == canonical else path


def _snapshot_from_payload(payload: Mapping[str, Any]) -> PortfolioTruthSnapshot:
    try:
        raw_projects = payload["projects"]
        if not isinstance(raw_projects, list):
            raise ValueError("Portfolio truth projects must be an array.")
        projects = [_project_from_payload(project) for project in raw_projects]
        return PortfolioTruthSnapshot(
            schema_version=str(payload["schema_version"]),
            generated_at=_parse_datetime(payload["generated_at"], "generated_at"),
            workspace_root=str(payload["workspace_root"]),
            source_summary=dict(payload["source_summary"]),
            precedence_matrix=dict(payload["precedence_matrix"]),
            warnings=list(payload["warnings"]),
            projects=projects,
            derivation_policy_version=str(payload["derivation_policy_version"]),
            producer=dict(payload["producer"]),
            inputs=dict(payload["inputs"]),
            coverage=list(payload["coverage"]),
            exclusions=dict(payload["exclusions"]),
        )
    except KeyError as exc:
        raise ValueError(
            f"Portfolio truth payload is missing field: {exc.args[0]}"
        ) from exc
    except TypeError as exc:
        raise ValueError(
            f"Portfolio truth payload has an invalid field type: {exc}"
        ) from exc


def _project_from_payload(payload: object) -> PortfolioTruthProject:
    if not isinstance(payload, Mapping):
        raise ValueError("Portfolio truth project must be an object.")
    try:
        derived = dict(payload["derived"])
        last_activity = derived.get("last_meaningful_activity_at")
        if last_activity is not None:
            derived["last_meaningful_activity_at"] = _parse_datetime(
                last_activity, "projects[].derived.last_meaningful_activity_at"
            )
        return PortfolioTruthProject(
            identity=IdentityFields(
                **_model_kwargs(IdentityFields, payload["identity"])
            ),
            declared=DeclaredFields(
                **_model_kwargs(DeclaredFields, payload["declared"])
            ),
            derived=DerivedFields(**_model_kwargs(DerivedFields, derived)),
            risk=RiskFields(**_model_kwargs(RiskFields, payload.get("risk", {}))),
            security=SecurityFields(
                **_model_kwargs(SecurityFields, payload.get("security", {}))
            ),
            advisory=AdvisoryFields(
                **_model_kwargs(AdvisoryFields, payload.get("advisory", {}))
            ),
            repository_state=dict(payload.get("repository_state", {})),
            provenance=dict(payload.get("provenance", {})),
            warnings=list(payload.get("warnings", [])),
        )
    except KeyError as exc:
        raise ValueError(
            f"Portfolio truth project is missing field: {exc.args[0]}"
        ) from exc
    except TypeError as exc:
        raise ValueError(
            f"Portfolio truth project has an invalid field type: {exc}"
        ) from exc


def _model_kwargs(model: type, payload: object) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError(f"{model.__name__} payload must be an object.")
    allowed = {field.name for field in fields(model) if field.init}
    return {key: value for key, value in payload.items() if key in allowed}


def _parse_datetime(value: object, field_name: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ValueError(f"Portfolio truth {field_name} must be an ISO-8601 timestamp.")
    normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(
            f"Portfolio truth {field_name} must be an ISO-8601 timestamp."
        ) from exc
    if parsed.tzinfo is None:
        raise ValueError(f"Portfolio truth {field_name} must include a timezone.")
    return parsed


def _validate_contract_envelope(payload: Mapping[str, Any]) -> None:
    producer = payload.get("producer")
    if not isinstance(producer, dict):
        raise ValueError("Portfolio truth producer evidence must be an object.")
    if producer:
        required = {
            "repository",
            "expected_repository",
            "commit",
            "ref",
            "checkout_role",
            "checkout_path",
            "worktree_clean",
            "dirty_path_count",
            "verified_at",
            "receipt_id",
        }
        if set(producer) != required:
            missing = sorted(required - producer.keys())
            if missing:
                raise ValueError(f"Producer evidence is missing fields: {missing}")
            raise ValueError("Producer evidence contains unexpected fields.")
        commit = producer.get("commit")
        if (
            not isinstance(commit, str)
            or len(commit) != 40
            or any(char not in "0123456789abcdef" for char in commit)
            or set(commit) == {"0"}
        ):
            raise ValueError("Producer commit must be a lowercase 40-character SHA.")
        for field_name in (
            "repository",
            "expected_repository",
            "ref",
            "checkout_role",
        ):
            if not _nonempty_text(producer.get(field_name)):
                raise ValueError(f"Producer {field_name} must be a nonempty string.")
        checkout_path = producer.get("checkout_path")
        if not isinstance(checkout_path, str) or not Path(checkout_path).is_absolute():
            raise ValueError("Producer checkout_path must be an absolute path.")
        if producer.get("worktree_clean") is not True:
            raise ValueError(
                "Canonical producer evidence must declare a clean worktree."
            )
        if (
            not isinstance(producer.get("dirty_path_count"), int)
            or isinstance(producer.get("dirty_path_count"), bool)
            or producer.get("dirty_path_count") != 0
        ):
            raise ValueError(
                "Canonical producer evidence must declare zero dirty paths."
            )
        receipt_id = producer.get("receipt_id")
        if not isinstance(receipt_id, str) or re.fullmatch(
            r"sha256:[0-9a-f]{64}", receipt_id
        ) is None:
            raise ValueError("Producer receipt_id must be a SHA-256 identity.")
        verified_at = _parse_datetime(
            producer.get("verified_at"), "producer.verified_at"
        )
        generated_at = _parse_datetime(payload.get("generated_at"), "generated_at")
        if verified_at > generated_at:
            raise ValueError("Producer evidence is future-dated.")
        try:
            normalized_producer = ProducerEvidence.from_dict(producer).to_dict()
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Producer evidence is invalid: {exc}") from exc
        if normalized_producer != producer:
            raise ValueError("Producer evidence differs from its canonical shape.")
    coverage = payload.get("coverage")
    if not isinstance(coverage, list) or not coverage:
        raise ValueError("Portfolio truth coverage envelope is required.")
    inputs = payload.get("inputs")
    notion = inputs.get("notion") if isinstance(inputs, dict) else None
    if not isinstance(notion, dict):
        raise ValueError("Portfolio truth inputs.notion is required.")
    mode = notion.get("mode")
    if mode not in {"live", "verified-snapshot", "carried-forward", "unavailable"}:
        raise ValueError(f"Invalid Notion input mode: {mode}")
    if mode == "carried-forward" and not notion.get("carried_from_generated_at"):
        raise ValueError("Carried-forward Notion input requires an origin timestamp.")
    if mode == "live" and notion.get("carried_from_generated_at") is not None:
        raise ValueError("Live Notion input cannot declare a carried-forward origin.")
    if mode == "verified-snapshot" and not notion.get("observed_at"):
        raise ValueError(
            "Verified Notion snapshot input requires an observation timestamp."
        )
    github_security = (
        inputs.get("github_security") if isinstance(inputs, dict) else None
    )
    if isinstance(github_security, dict):
        receipt_id = github_security.get("receipt_id")
        content_sha256 = github_security.get("content_sha256")
        if (receipt_id is None) != (content_sha256 is None):
            raise ValueError(
                "GitHub security input identity requires both receipt_id and "
                "content_sha256."
            )
        if receipt_id is not None and not re.fullmatch(
            r"sha256:[0-9a-f]{64}", str(receipt_id)
        ):
            raise ValueError("GitHub security receipt_id is malformed.")
        if content_sha256 is not None and not re.fullmatch(
            r"[0-9a-f]{64}", str(content_sha256)
        ):
            raise ValueError("GitHub security content_sha256 is malformed.")


def validate_publish_targets(
    *,
    workspace_root: Path,
    output_dir: Path,
    registry_output: Path,
    portfolio_report_output: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    if not _is_within(workspace_root, registry_output):
        raise ValueError("Registry output must stay within the workspace root.")
    if not _is_within(workspace_root, portfolio_report_output):
        raise ValueError("Portfolio report output must stay within the workspace root.")
    for path in (output_dir, registry_output.parent, portfolio_report_output.parent):
        path.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            raise ValueError(f"Publish target is not available: {path}")


def validate_registry_markdown(
    markdown: str, snapshot: PortfolioTruthSnapshot, temp_path: Path
) -> None:
    temp_path.write_text(markdown)
    try:
        parsed = parse_registry(temp_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    expected_labels = registry_project_labels(snapshot.projects).values()
    expected = {_normalize(label.strip()) for label in expected_labels}
    parsed_names = {_normalize(name) for name in parsed}
    if len(parsed) != len(snapshot.projects):
        raise ValueError(
            "Generated registry markdown changed the project row count during round-trip: "
            f"expected {len(snapshot.projects)}, got {len(parsed)}"
        )
    missing = sorted(expected - parsed_names)
    if missing:
        raise ValueError(
            f"Generated registry markdown lost project rows during round-trip: {', '.join(missing[:5])}"
        )
    required_headers = (
        "# Project Registry",
        "## Standalone Projects",
        "## Portfolio Summary",
        "## Cowork Task Notes",
    )
    for header in required_headers:
        if header not in markdown:
            raise ValueError(f"Registry markdown is missing required section: {header}")


def validate_portfolio_report_markdown(markdown: str) -> None:
    required_markers = (
        "# Portfolio Audit Report",
        "canonical machine-readable artifact",
        "derived from the portfolio truth snapshot",
        "## Audit Methodology",
        "## Canonical Portfolio Truth Table",
        "## Coverage Summary",
        "## Security Posture",
        "## Accuracy Findings",
        "## Recommended Next Sync Steps",
    )
    for marker in required_markers:
        if marker not in markdown:
            raise ValueError(f"Portfolio report is missing required content: {marker}")


def _is_within(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False
