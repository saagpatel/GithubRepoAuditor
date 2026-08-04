from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import fields
from datetime import datetime
from pathlib import Path
from typing import Any

from src.portfolio_pathing import (
    VALID_MATURITY_PROGRAMS,
    VALID_OPERATING_PATHS,
    VALID_PATH_CONFIDENCE,
    VALID_PATH_OVERRIDES,
)
from src.portfolio_truth_render import registry_project_labels
from src.portfolio_truth_types import (
    DERIVATION_POLICY_VERSION,
    SCHEMA_VERSION,
    VALID_ACTIVITY_STATUS,
    VALID_ATTENTION_STATES,
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
from src.registry_parser import _normalize, parse_registry


def validate_truth_snapshot(snapshot: PortfolioTruthSnapshot) -> None:
    if snapshot.schema_version != SCHEMA_VERSION:
        raise ValueError(f"Unexpected schema version: {snapshot.schema_version}")
    if snapshot.derivation_policy_version != DERIVATION_POLICY_VERSION:
        raise ValueError(
            "Unexpected derivation policy version: "
            f"{snapshot.derivation_policy_version}"
        )
    _validate_contract_envelope(snapshot.to_dict())
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


def validate_truth_snapshot_payload(payload: Mapping[str, Any]) -> None:
    """Construct and fully validate the serialized canonical truth contract."""
    validate_truth_snapshot(_snapshot_from_payload(payload))


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
        raise ValueError(f"Portfolio truth payload is missing field: {exc.args[0]}") from exc
    except TypeError as exc:
        raise ValueError(f"Portfolio truth payload has an invalid field type: {exc}") from exc


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
            identity=IdentityFields(**_model_kwargs(IdentityFields, payload["identity"])),
            declared=DeclaredFields(**_model_kwargs(DeclaredFields, payload["declared"])),
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
            "commit",
            "ref",
            "checkout_role",
            "checkout_path",
            "worktree_clean",
            "dirty_path_count",
            "verified_at",
            "receipt_id",
        }
        missing = sorted(required - producer.keys())
        if missing:
            raise ValueError(f"Producer evidence is missing fields: {missing}")
        commit = producer.get("commit")
        if (
            not isinstance(commit, str)
            or len(commit) != 40
            or any(char not in "0123456789abcdef" for char in commit)
        ):
            raise ValueError("Producer commit must be a lowercase 40-character SHA.")
        if producer.get("worktree_clean") is not True:
            raise ValueError(
                "Canonical producer evidence must declare a clean worktree."
            )
        if producer.get("dirty_path_count") != 0:
            raise ValueError(
                "Canonical producer evidence must declare zero dirty paths."
            )
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
        raise ValueError("Verified Notion snapshot input requires an observation timestamp.")
    github_security = inputs.get("github_security") if isinstance(inputs, dict) else None
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
