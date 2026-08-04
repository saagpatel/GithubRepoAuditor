from __future__ import annotations

import re
from pathlib import Path

from src.portfolio_checkout_authority import validate_checkout_authority_envelope
from src.portfolio_pathing import (
    VALID_MATURITY_PROGRAMS,
    VALID_OPERATING_PATHS,
    VALID_PATH_CONFIDENCE,
    VALID_PATH_OVERRIDES,
)
from src.portfolio_truth_render import registry_project_labels
from src.portfolio_truth_types import (
    CHECKOUT_COLLISION_SUMMARY_SCHEMA_VERSION,
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
    if snapshot.schema_version != SCHEMA_VERSION:
        raise ValueError(f"Unexpected schema version: {snapshot.schema_version}")
    if snapshot.derivation_policy_version != DERIVATION_POLICY_VERSION:
        raise ValueError(
            "Unexpected derivation policy version: "
            f"{snapshot.derivation_policy_version}"
        )
    _validate_contract_envelope(snapshot)
    _validate_checkout_collisions(snapshot)
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


def _validate_checkout_collisions(snapshot: PortfolioTruthSnapshot) -> None:
    summary = snapshot.source_summary.get("checkout_collisions")
    if not isinstance(summary, dict):
        raise ValueError("Portfolio truth checkout collision summary is required.")
    required_summary = {
        "schema_version",
        "state",
        "group_count",
        "full_clone_group_count",
        "ambiguous_group_count",
        "discarded_checkout_count",
        "groups",
    }
    missing = sorted(required_summary - summary.keys())
    if missing:
        raise ValueError(f"Checkout collision summary is missing fields: {missing}")
    if summary.get("schema_version") != CHECKOUT_COLLISION_SUMMARY_SCHEMA_VERSION:
        raise ValueError("Unexpected checkout collision summary schema version.")
    groups = summary.get("groups")
    if not isinstance(groups, list):
        raise ValueError("Checkout collision groups must be a list.")
    _require_nonnegative_count(summary, "group_count")
    _require_nonnegative_count(summary, "full_clone_group_count")
    _require_nonnegative_count(summary, "ambiguous_group_count")
    _require_nonnegative_count(summary, "discarded_checkout_count")
    if summary["group_count"] != len(groups):
        raise ValueError("Checkout collision group_count does not match groups.")

    project_by_origin = {}
    for project in snapshot.projects:
        origin_key = project.identity.repo_full_name.lower()
        if not origin_key:
            continue
        if origin_key in project_by_origin:
            raise ValueError(
                "Portfolio truth must contain one canonical project per origin: "
                f"{project.identity.repo_full_name}"
            )
        project_by_origin[origin_key] = project
    seen_origins: set[str] = set()
    ambiguous = 0
    full_clone_groups = 0
    discarded_count = 0
    for group in groups:
        if not isinstance(group, dict):
            raise ValueError("Checkout collision group must be an object.")
        origin = group.get("origin")
        if not isinstance(origin, str) or not origin.strip():
            raise ValueError("Checkout collision origin must be non-empty.")
        origin_key = origin.lower()
        project = project_by_origin.get(origin_key)
        if project is None:
            raise ValueError(f"Checkout collision has no canonical project: {origin}")
        validated = validate_checkout_authority_envelope(
            group,
            identity_path=project.identity.path,
            repo_full_name=project.identity.repo_full_name,
        )
        if origin_key in seen_origins:
            raise ValueError(f"Duplicate checkout collision origin: {origin}")
        seen_origins.add(origin_key)
        full_clone_groups += int(validated.full_clone_count > 1)
        ambiguous += int(validated.state == "unknown")
        discarded_count += validated.discarded_count
        if project.repository_state.get("checkout_authority") != group:
            raise ValueError(
                "Project checkout authority differs from collision summary."
            )

    if summary["full_clone_group_count"] != full_clone_groups:
        raise ValueError("Checkout full_clone_group_count does not match groups.")
    if summary["ambiguous_group_count"] != ambiguous:
        raise ValueError("Checkout ambiguous_group_count does not match groups.")
    if summary["discarded_checkout_count"] != discarded_count:
        raise ValueError("Checkout discarded_checkout_count does not match groups.")
    for project in snapshot.projects:
        authority = project.repository_state.get("checkout_authority")
        origin_key = project.identity.repo_full_name.lower()
        if authority is not None and origin_key not in seen_origins:
            raise ValueError(
                "Project checkout authority is missing from the collision summary."
            )
    expected_state = "unknown" if ambiguous else "observed"
    if summary.get("state") != expected_state:
        raise ValueError(
            "Checkout collision summary state does not match group authority."
        )


def _require_nonnegative_count(value: dict, key: str) -> int:
    count = value.get(key)
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError(f"{key} must be a non-negative integer.")
    return count


def _validate_contract_envelope(snapshot: PortfolioTruthSnapshot) -> None:
    producer = snapshot.producer
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
    if not snapshot.coverage:
        raise ValueError("Portfolio truth coverage envelope is required.")
    notion = (
        snapshot.inputs.get("notion") if isinstance(snapshot.inputs, dict) else None
    )
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
    github_security = (
        snapshot.inputs.get("github_security")
        if isinstance(snapshot.inputs, dict)
        else None
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
        "## Checkout Authority",
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
