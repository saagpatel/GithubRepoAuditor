from __future__ import annotations

import re
from pathlib import Path

from src.portfolio_pathing import (
    VALID_MATURITY_PROGRAMS,
    VALID_OPERATING_PATHS,
    VALID_PATH_CONFIDENCE,
    VALID_PATH_OVERRIDES,
)
from src.portfolio_truth_render import registry_project_labels
from src.portfolio_truth_types import (
    CHECKOUT_COLLISION_SCHEMA_VERSION,
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
        required_group = {
            "schema_version",
            "origin",
            "checkout_count",
            "full_clone_count",
            "declared_checkout_paths",
            "declared_path_evidence",
            "unresolved_declared_paths",
            "selection",
            "checkouts",
            "discarded_checkouts",
        }
        group_missing = sorted(required_group - group.keys())
        if group_missing:
            raise ValueError(
                f"Checkout collision group is missing fields: {group_missing}"
            )
        if group.get("schema_version") != CHECKOUT_COLLISION_SCHEMA_VERSION:
            raise ValueError("Unexpected checkout collision schema version.")
        origin = group.get("origin")
        if not isinstance(origin, str) or not origin.strip():
            raise ValueError("Checkout collision origin must be non-empty.")
        origin_key = origin.lower()
        if origin_key in seen_origins:
            raise ValueError(f"Duplicate checkout collision origin: {origin}")
        seen_origins.add(origin_key)

        checkout_count = _require_nonnegative_count(group, "checkout_count")
        full_clone_count = _require_nonnegative_count(group, "full_clone_count")
        if checkout_count < 2:
            raise ValueError(
                "Checkout collision groups require at least two checkouts."
            )
        if not 1 <= full_clone_count <= checkout_count:
            raise ValueError("Checkout collision full_clone_count is out of range.")
        full_clone_groups += int(full_clone_count > 1)

        selection = group.get("selection")
        if not isinstance(selection, dict):
            raise ValueError("Checkout collision selection must be an object.")
        for key in (
            "state",
            "reason_code",
            "reason",
            "representative_path",
            "selected_path",
            "rationale",
        ):
            if key not in selection:
                raise ValueError(f"Checkout collision selection is missing {key}.")
        state = selection.get("state")
        if state not in {"selected", "unknown"}:
            raise ValueError(f"Invalid checkout authority state: {state}")
        representative_path = _require_relative_path(
            selection.get("representative_path"),
            "checkout representative_path",
        )
        selected_path = selection.get("selected_path")
        if state == "unknown":
            ambiguous += 1
            if selected_path is not None:
                raise ValueError("UNKNOWN checkout authority cannot select a path.")
        elif selected_path != representative_path:
            raise ValueError(
                "Selected checkout path must equal the representative path."
            )
        for key in ("reason_code", "reason", "rationale"):
            if not isinstance(selection.get(key), str) or not selection[key].strip():
                raise ValueError(
                    f"Checkout collision selection {key} must be non-empty."
                )

        checkouts = group.get("checkouts")
        discarded = group.get("discarded_checkouts")
        if not isinstance(checkouts, list) or len(checkouts) != checkout_count:
            raise ValueError(
                "Checkout collision checkouts do not match checkout_count."
            )
        if not isinstance(discarded, list):
            raise ValueError("Discarded checkouts must be a list.")
        checkout_paths: set[str] = set()
        representative_count = 0
        for checkout in checkouts:
            if not isinstance(checkout, dict):
                raise ValueError("Checkout collision checkout must be an object.")
            required_checkout = {
                "path",
                "state",
                "relation",
                "head",
                "branch",
                "dirty",
                "dirty_path_count",
                "bare",
            }
            missing_checkout = sorted(required_checkout - checkout.keys())
            if missing_checkout:
                raise ValueError(
                    f"Checkout collision checkout is missing fields: {missing_checkout}"
                )
            path = _require_relative_path(checkout.get("path"), "checkout path")
            if path in checkout_paths:
                raise ValueError(f"Duplicate checkout collision path: {path}")
            checkout_paths.add(path)
            if checkout.get("state") not in {"observed", "unknown"}:
                raise ValueError("Invalid checkout observation state.")
            relation = checkout.get("relation")
            if relation not in {
                "representative",
                "linked_worktree",
                "independent_full_clone",
            }:
                raise ValueError("Invalid checkout relation.")
            representative_count += int(relation == "representative")
            head = checkout.get("head")
            if head is not None and not re.fullmatch(
                r"[0-9a-f]{40}|[0-9a-f]{64}", str(head)
            ):
                raise ValueError(f"Malformed checkout head for {path}.")
            branch = checkout.get("branch")
            if branch is not None and not isinstance(branch, str):
                raise ValueError(f"Malformed checkout branch for {path}.")
            dirty = checkout.get("dirty")
            if dirty is not None and not isinstance(dirty, bool):
                raise ValueError(f"Malformed checkout dirty state for {path}.")
            dirty_count = checkout.get("dirty_path_count")
            if dirty_count is not None and (
                isinstance(dirty_count, bool)
                or not isinstance(dirty_count, int)
                or dirty_count < 0
            ):
                raise ValueError(f"Malformed checkout dirty_path_count for {path}.")
            bare = checkout.get("bare")
            if bare is not None and not isinstance(bare, bool):
                raise ValueError(f"Malformed checkout bare state for {path}.")
            if checkout.get("state") == "observed" and not isinstance(bare, bool):
                raise ValueError(f"Observed checkout must declare bare state for {path}.")
        representative_checkout = next(
            (
                checkout
                for checkout in checkouts
                if checkout["path"] == representative_path
            ),
            None,
        )
        if (
            representative_count != 1
            or representative_checkout is None
            or representative_checkout["relation"] != "representative"
            or (state == "selected" and representative_checkout["bare"] is not False)
        ):
            raise ValueError("Checkout collision requires one observed representative.")
        expected_discarded = [
            checkout
            for checkout in checkouts
            if checkout["path"] != representative_path
        ]
        if discarded != expected_discarded:
            raise ValueError(
                "Discarded checkout evidence does not match the checkout set."
            )
        discarded_count += len(discarded)

        declared_paths = group.get("declared_checkout_paths")
        unresolved_paths = group.get("unresolved_declared_paths")
        declared_evidence = group.get("declared_path_evidence")
        if not isinstance(declared_paths, list) or not isinstance(
            unresolved_paths, list
        ):
            raise ValueError("Declared checkout paths must be lists.")
        for path in declared_paths + unresolved_paths:
            _require_relative_path(path, "declared checkout path")
        if not isinstance(declared_evidence, list):
            raise ValueError("Declared path evidence must be a list.")
        for item in declared_evidence:
            if not isinstance(item, dict):
                raise ValueError("Declared path evidence must be an object.")
            _require_relative_path(item.get("source_path"), "declared source path")
            target = _require_relative_path(
                item.get("target_checkout_path"), "declared target checkout path"
            )
            if target not in checkout_paths:
                raise ValueError(
                    "Declared checkout target is not in the collision group."
                )
        expected_declared_paths = sorted(
            {item["target_checkout_path"] for item in declared_evidence},
            key=str.lower,
        )
        if declared_paths != expected_declared_paths:
            raise ValueError(
                "Declared checkout paths do not match declared path evidence."
            )

        project = project_by_origin.get(origin_key)
        if project is None:
            raise ValueError(f"Checkout collision has no canonical project: {origin}")
        if project.identity.path != representative_path:
            raise ValueError(
                "Canonical project path differs from collision representative."
            )
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


def _require_relative_path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string.")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label} must stay workspace-relative.")
    return value


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
