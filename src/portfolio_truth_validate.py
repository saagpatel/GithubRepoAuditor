from __future__ import annotations

import re
from collections.abc import Mapping
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
    PortfolioTruthSnapshot,
)
from src.registry_parser import _normalize, parse_registry


def validate_truth_snapshot(snapshot: PortfolioTruthSnapshot) -> None:
    validate_truth_snapshot_payload(snapshot.to_dict())
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
    """Validate the serialized contract shared by publication and fixtures."""
    schema_version = payload.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        raise ValueError(f"Unexpected schema version: {schema_version}")
    derivation_policy_version = payload.get("derivation_policy_version")
    if derivation_policy_version != DERIVATION_POLICY_VERSION:
        raise ValueError(
            "Unexpected derivation policy version: "
            f"{derivation_policy_version}"
        )
    _validate_contract_envelope(payload)


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
