from __future__ import annotations

from pathlib import Path

from src.portfolio_pathing import (
    VALID_MATURITY_PROGRAMS,
    VALID_OPERATING_PATHS,
    VALID_PATH_CONFIDENCE,
    VALID_PATH_OVERRIDES,
)
from src.portfolio_truth_render import registry_project_labels
from src.portfolio_truth_types import (
    SCHEMA_VERSION,
    VALID_ACTIVITY_STATUS,
    VALID_CONTEXT_QUALITY,
    VALID_LIFECYCLE_STATES,
    VALID_REGISTRY_STATUS,
    PortfolioTruthSnapshot,
)
from src.registry_parser import _normalize, parse_registry


def validate_truth_snapshot(snapshot: PortfolioTruthSnapshot) -> None:
    if snapshot.schema_version != SCHEMA_VERSION:
        raise ValueError(f"Unexpected schema version: {snapshot.schema_version}")
    seen_keys: set[str] = set()
    for project in snapshot.projects:
        key = project.identity.project_key
        if key in seen_keys:
            raise ValueError(f"Duplicate project key in truth snapshot: {key}")
        seen_keys.add(key)
        if Path(project.identity.path).is_absolute():
            raise ValueError(f"Project path must stay workspace-relative: {project.identity.path}")
        if project.derived.context_quality not in VALID_CONTEXT_QUALITY:
            raise ValueError(f"Invalid context quality for {key}: {project.derived.context_quality}")
        if project.derived.primary_context_file not in {"AGENTS.md", "CLAUDE.md"}:
            raise ValueError(f"Invalid primary context file for {key}: {project.derived.primary_context_file}")
        if project.derived.activity_status not in VALID_ACTIVITY_STATUS:
            raise ValueError(f"Invalid activity status for {key}: {project.derived.activity_status}")
        if project.derived.registry_status not in VALID_REGISTRY_STATUS:
            raise ValueError(f"Invalid registry status for {key}: {project.derived.registry_status}")
        completeness_flags = (
            project.derived.project_summary_present,
            project.derived.current_state_present,
            project.derived.stack_present,
            project.derived.run_instructions_present,
            project.derived.known_risks_present,
            project.derived.next_recommended_move_present,
        )
        if project.derived.context_quality in {"minimum-viable", "standard", "full"} and not all(completeness_flags):
            raise ValueError(f"Context quality for {key} requires all minimum-viable fields to be present.")
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
            raise ValueError(f"Invalid path confidence for {key}: {project.derived.path_confidence}")


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


def validate_registry_markdown(markdown: str, snapshot: PortfolioTruthSnapshot, temp_path: Path) -> None:
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
        raise ValueError(f"Generated registry markdown lost project rows during round-trip: {', '.join(missing[:5])}")
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
