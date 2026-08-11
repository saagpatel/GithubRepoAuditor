"""Canonical field-level authority order for PortfolioTruth producers."""

from __future__ import annotations

PRECEDENCE_MATRIX: dict[str, list[str]] = {
    "declared.owner": ["catalog_repo", "catalog_group"],
    "declared.team": ["catalog_repo", "catalog_group"],
    "declared.purpose": ["catalog_repo", "catalog_group"],
    "declared.lifecycle_state": ["catalog_repo", "catalog_group"],
    "declared.criticality": ["catalog_repo", "catalog_group"],
    "declared.review_cadence": ["catalog_repo", "catalog_group"],
    "declared.intended_disposition": ["catalog_repo", "catalog_group"],
    "declared.maturity_program": [
        "catalog_repo",
        "catalog_group",
        "catalog_defaults",
    ],
    "declared.target_maturity": [
        "catalog_repo",
        "catalog_group",
        "catalog_defaults",
    ],
    "declared.operating_path": ["normalized"],
    "declared.category": ["catalog_repo", "catalog_group", "legacy_registry"],
    "declared.tool_provenance": [
        "catalog_repo",
        "catalog_group",
        "inference",
        "legacy_registry",
    ],
    "declared.notes": ["catalog_repo", "catalog_group", "legacy_registry"],
    "derived.stack": ["workspace", "legacy_registry"],
    "derived.context_quality": ["workspace", "catalog_repo", "catalog_group"],
    "derived.context_files": ["workspace"],
    "derived.primary_context_file": ["workspace"],
    "derived.project_summary_present": ["workspace"],
    "derived.current_state_present": ["workspace"],
    "derived.stack_present": ["workspace"],
    "derived.run_instructions_present": ["workspace"],
    "derived.known_risks_present": ["workspace"],
    "derived.next_recommended_move_present": ["workspace"],
    "derived.last_meaningful_activity_at": ["git", "workspace"],
    "derived.activity_status": ["derived"],
    "derived.archived": ["derived"],
    "derived.attention_state": ["derived"],
    "derived.path_override": ["normalized"],
    "derived.path_confidence": ["normalized"],
    "derived.path_rationale": ["normalized"],
    "derived.has_tests": ["workspace"],
    "derived.has_ci": ["workspace"],
    "derived.readme_char_count": ["workspace"],
}


def build_precedence_matrix() -> dict[str, list[str]]:
    """Return an independent serializable copy of the authority contract."""
    return {field: list(sources) for field, sources in PRECEDENCE_MATRIX.items()}
