from __future__ import annotations


# Every project built by the production reconciler records these provenance
# entries. Portable fixtures must carry the same minimum contract so consumers
# never mistake an untraceable synthetic row for production-shaped truth.
REQUIRED_PROJECT_PROVENANCE_KEYS = frozenset(
    {
        "declared.category",
        "declared.criticality",
        "declared.doctor_standard",
        "declared.intended_disposition",
        "declared.lifecycle_state",
        "declared.maturity_program",
        "declared.notes",
        "declared.operating_path",
        "declared.owner",
        "declared.purpose",
        "declared.review_cadence",
        "declared.target_maturity",
        "declared.team",
        "declared.tool_provenance",
        "derived.activity_status",
        "derived.archived",
        "derived.attention_state",
        "derived.context_files",
        "derived.context_quality",
        "derived.current_state_present",
        "derived.known_risks_present",
        "derived.last_meaningful_activity_at",
        "derived.next_recommended_move_present",
        "derived.path_confidence",
        "derived.path_override",
        "derived.path_rationale",
        "derived.primary_context_file",
        "derived.project_summary_present",
        "derived.run_instructions_present",
        "derived.stack",
        "derived.stack_present",
        "risk.doctor_gap",
        "risk.risk_tier",
    }
)
