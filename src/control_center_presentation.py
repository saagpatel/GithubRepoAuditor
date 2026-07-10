"""User-facing control-center presentation helpers."""

from __future__ import annotations

from src.operator_control_center_artifacts import should_print_control_center_item


def _control_center_next_step_hint() -> str:
    return (
        "Reading order: workbook Dashboard -> Run Changes -> Review Queue -> Repo Detail. "
        "Move into Action Sync only when the local weekly story is already settled."
    )


def _normal_audit_next_step_hint(username: str) -> str:
    return (
        f"Next step: open the standard workbook first, then run `audit {username} --control-center` "
        "for the read-only operator queue."
    )


def _print_control_center_summary(snapshot: dict) -> None:
    summary = snapshot.get("operator_summary", {})
    queue = snapshot.get("operator_queue", [])
    recent_changes = snapshot.get("operator_recent_changes", [])
    print(
        f"\nOperator Control Center\n  {summary.get('headline', 'No operator triage items are currently surfaced.')}"
    )
    if summary.get("report_reference"):
        print(f"  Latest report: {summary['report_reference']}")
    if summary.get("source_run_id"):
        print(f"  Source run: {summary['source_run_id']}")
    if summary.get("next_recommended_run_mode"):
        print(
            "  Next recommended run: "
            f"{summary.get('next_recommended_run_mode', 'unknown')}"
            f" ({summary.get('watch_decision_summary', 'No watch decision summary available.')})"
        )
    if summary.get("watch_strategy"):
        print(f"  Watch strategy: {summary['watch_strategy']}")
    if summary.get("what_changed"):
        print(f"  What changed: {summary['what_changed']}")
    if summary.get("why_it_matters"):
        print(f"  Why it matters: {summary['why_it_matters']}")
    if summary.get("what_to_do_next"):
        print(f"  What to do next: {summary['what_to_do_next']}")
    if summary.get("trend_summary"):
        print(f"  Trend: {summary['trend_summary']}")
    if summary.get("accountability_summary"):
        print(f"  Accountability: {summary['accountability_summary']}")
    primary_target = summary.get("primary_target") or {}
    if primary_target:
        repo = f"{primary_target.get('repo')}: " if primary_target.get("repo") else ""
        print(f"  Primary target: {repo}{primary_target.get('title', 'Operator target')}")
    if summary.get("primary_target_reason"):
        print(f"  Why this is the top target: {summary['primary_target_reason']}")
    if summary.get("primary_target_done_criteria"):
        print(f"  What counts as done: {summary['primary_target_done_criteria']}")
    if summary.get("closure_guidance"):
        print(f"  Closure guidance: {summary['closure_guidance']}")
    if summary.get("primary_target_last_intervention"):
        intervention = summary.get("primary_target_last_intervention") or {}
        when = (intervention.get("recorded_at") or "")[:10]
        event_type = intervention.get("event_type", "recorded")
        outcome = intervention.get("outcome", event_type)
        print(f"  What we tried: {when} {event_type} ({outcome})".strip())
    if summary.get("primary_target_resolution_evidence"):
        print(f"  Resolution evidence: {summary['primary_target_resolution_evidence']}")
    if summary.get("primary_target_confidence_label"):
        print(
            "  Primary target confidence: "
            f"{summary.get('primary_target_confidence_label', 'low')} "
            f"({summary.get('primary_target_confidence_score', 0.0):.2f})"
        )
    if summary.get("primary_target_confidence_reasons"):
        print(
            "  Confidence reasons: "
            + ", ".join(summary.get("primary_target_confidence_reasons") or [])
        )
    if summary.get("next_action_confidence_label"):
        print(
            "  Next action confidence: "
            f"{summary.get('next_action_confidence_label', 'low')} "
            f"({summary.get('next_action_confidence_score', 0.0):.2f})"
        )
    if summary.get("primary_target_trust_policy"):
        print(
            "  Trust policy: "
            f"{summary.get('primary_target_trust_policy', 'monitor')} "
            f"({summary.get('primary_target_trust_policy_reason', 'No trust-policy reason is recorded yet.')})"
        )
    if summary.get("adaptive_confidence_summary"):
        print(f"  Why this confidence is actionable: {summary['adaptive_confidence_summary']}")
    if summary.get("primary_target_exception_status") not in {None, "", "none"}:
        print(
            "  Trust policy exception: "
            f"{summary.get('primary_target_exception_status', 'none')} "
            f"({summary.get('primary_target_exception_reason', 'No trust-policy exception reason is recorded yet.')})"
        )
    if summary.get("primary_target_exception_pattern_status") not in {None, "", "none"}:
        print(
            "  Exception pattern learning: "
            f"{summary.get('primary_target_exception_pattern_status', 'none')} "
            f"({summary.get('primary_target_exception_pattern_reason', 'No exception-pattern reason is recorded yet.')})"
        )
    if summary.get("primary_target_trust_recovery_status") not in {None, "", "none"}:
        print(
            "  Trust recovery: "
            f"{summary.get('primary_target_trust_recovery_status', 'none')} "
            f"({summary.get('primary_target_trust_recovery_reason', 'No trust-recovery reason is recorded yet.')})"
        )
    if summary.get("primary_target_recovery_confidence_label"):
        print(
            "  Recovery confidence: "
            f"{summary.get('primary_target_recovery_confidence_label', 'low')} "
            f"({summary.get('primary_target_recovery_confidence_score', 0.0):.2f})"
        )
    if summary.get("recovery_confidence_summary"):
        print(f"  Recovery confidence summary: {summary['recovery_confidence_summary']}")
    if summary.get("primary_target_exception_retirement_status") not in {None, "", "none"}:
        print(
            "  Exception retirement: "
            f"{summary.get('primary_target_exception_retirement_status', 'none')} "
            f"({summary.get('primary_target_exception_retirement_reason', 'No exception-retirement reason is recorded yet.')})"
        )
    if summary.get("primary_target_policy_debt_status") not in {None, "", "none"}:
        print(
            "  Policy debt cleanup: "
            f"{summary.get('primary_target_policy_debt_status', 'none')} "
            f"({summary.get('primary_target_policy_debt_reason', 'No policy-debt reason is recorded yet.')})"
        )
    if summary.get("primary_target_class_normalization_status") not in {None, "", "none"}:
        print(
            "  Class-level trust normalization: "
            f"{summary.get('primary_target_class_normalization_status', 'none')} "
            f"({summary.get('primary_target_class_normalization_reason', 'No class-normalization reason is recorded yet.')})"
        )
    if summary.get("primary_target_class_memory_freshness_status"):
        print(
            "  Class memory freshness: "
            f"{summary.get('primary_target_class_memory_freshness_status', 'insufficient-data')} "
            f"({summary.get('primary_target_class_memory_freshness_reason', 'No class-memory freshness reason is recorded yet.')})"
        )
    if summary.get("primary_target_class_decay_status") is not None:
        print(
            "  Trust decay controls: "
            f"{summary.get('primary_target_class_decay_status', 'none')} "
            f"({summary.get('primary_target_class_decay_reason', 'No class-decay reason is recorded yet.')})"
        )
    if summary.get("primary_target_transition_closure_confidence_label"):
        print(
            "  Transition closure confidence: "
            f"{summary.get('primary_target_transition_closure_confidence_label', 'low')} "
            f"({summary.get('primary_target_transition_closure_confidence_score', 0.0):.2f}; "
            f"{summary.get('primary_target_transition_closure_likely_outcome', 'none')})"
        )
    if summary.get("transition_closure_confidence_summary"):
        print(f"  Transition closure summary: {summary['transition_closure_confidence_summary']}")
    if summary.get("primary_target_class_pending_debt_status") not in {None, "", "none"}:
        print(
            "  Class pending debt audit: "
            f"{summary.get('primary_target_class_pending_debt_status', 'none')} "
            f"({summary.get('primary_target_class_pending_debt_reason', 'No class pending-debt reason is recorded yet.')})"
        )
    if summary.get("class_pending_debt_summary"):
        print(f"  Class pending debt summary: {summary['class_pending_debt_summary']}")
    if summary.get("class_pending_resolution_summary"):
        print(f"  Class pending resolution summary: {summary['class_pending_resolution_summary']}")
    if summary.get("primary_target_pending_debt_freshness_status"):
        print(
            "  Pending debt freshness: "
            f"{summary.get('primary_target_pending_debt_freshness_status', 'insufficient-data')} "
            f"({summary.get('primary_target_pending_debt_freshness_reason', 'No pending-debt freshness reason is recorded yet.')})"
        )
    if summary.get("pending_debt_freshness_summary"):
        print(f"  Pending debt freshness summary: {summary['pending_debt_freshness_summary']}")
    if summary.get("pending_debt_decay_summary"):
        print(f"  Pending debt decay summary: {summary['pending_debt_decay_summary']}")
    if summary.get("primary_target_closure_forecast_reweight_direction"):
        print(
            "  Closure forecast reweighting: "
            f"{summary.get('primary_target_closure_forecast_reweight_direction', 'neutral')} "
            f"({summary.get('primary_target_closure_forecast_reweight_score', 0.0):.2f})"
        )
    if summary.get("closure_forecast_reweighting_summary"):
        print(
            f"  Closure forecast reweighting summary: {summary['closure_forecast_reweighting_summary']}"
        )
    if summary.get("primary_target_closure_forecast_momentum_status"):
        print(
            "  Closure forecast momentum: "
            f"{summary.get('primary_target_closure_forecast_momentum_status', 'insufficient-data')} "
            f"({summary.get('primary_target_closure_forecast_momentum_score', 0.0):.2f})"
        )
    if summary.get("closure_forecast_momentum_summary"):
        print(
            f"  Closure forecast momentum summary: {summary['closure_forecast_momentum_summary']}"
        )
    if summary.get("primary_target_closure_forecast_freshness_status"):
        print(
            "  Closure forecast freshness: "
            f"{summary.get('primary_target_closure_forecast_freshness_status', 'insufficient-data')} "
            f"({summary.get('primary_target_closure_forecast_freshness_reason', 'No closure-forecast freshness reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_freshness_summary"):
        print(
            f"  Closure forecast freshness summary: {summary['closure_forecast_freshness_summary']}"
        )
    if summary.get("primary_target_closure_forecast_stability_status"):
        print(
            "  Closure forecast hysteresis: "
            f"{summary.get('primary_target_closure_forecast_stability_status', 'watch')} "
            f"({summary.get('primary_target_closure_forecast_hysteresis_status', 'none')}: "
            f"{summary.get('primary_target_closure_forecast_hysteresis_reason', 'No closure-forecast hysteresis reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_hysteresis_summary"):
        print(
            f"  Closure forecast hysteresis summary: {summary['closure_forecast_hysteresis_summary']}"
        )
    if summary.get("primary_target_closure_forecast_decay_status") not in {None, "", "none"}:
        print(
            "  Hysteresis decay controls: "
            f"{summary.get('primary_target_closure_forecast_decay_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_decay_reason', 'No closure-forecast decay reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_decay_summary"):
        print(f"  Closure forecast decay summary: {summary['closure_forecast_decay_summary']}")
    if summary.get("primary_target_closure_forecast_refresh_recovery_status") not in {
        None,
        "",
        "none",
    }:
        print(
            "  Closure forecast refresh recovery: "
            f"{summary.get('primary_target_closure_forecast_refresh_recovery_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_refresh_recovery_score', 0.0):.2f})"
        )
    if summary.get("closure_forecast_refresh_recovery_summary"):
        print(
            f"  Closure forecast refresh recovery summary: {summary['closure_forecast_refresh_recovery_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reacquisition_status") not in {
        None,
        "",
        "none",
    }:
        print(
            "  Reacquisition controls: "
            f"{summary.get('primary_target_closure_forecast_reacquisition_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reacquisition_reason', 'No closure-forecast reacquisition reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reacquisition_summary"):
        print(
            f"  Closure forecast reacquisition summary: {summary['closure_forecast_reacquisition_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reacquisition_persistence_status") not in {
        None,
        "",
        "none",
    }:
        print(
            "  Reacquisition persistence: "
            f"{summary.get('primary_target_closure_forecast_reacquisition_persistence_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reacquisition_persistence_score', 0.0):.2f}; "
            f"{summary.get('primary_target_closure_forecast_reacquisition_age_runs', 0)} run(s))"
        )
    if summary.get("closure_forecast_reacquisition_persistence_summary"):
        print(
            f"  Reacquisition persistence summary: {summary['closure_forecast_reacquisition_persistence_summary']}"
        )
    if summary.get("primary_target_closure_forecast_recovery_churn_status") not in {
        None,
        "",
        "none",
    }:
        print(
            "  Recovery churn controls: "
            f"{summary.get('primary_target_closure_forecast_recovery_churn_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_recovery_churn_reason', 'No recovery-churn reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_recovery_churn_summary"):
        print(f"  Recovery churn summary: {summary['closure_forecast_recovery_churn_summary']}")
    if summary.get("primary_target_closure_forecast_reacquisition_freshness_status") not in {
        None,
        "",
        "insufficient-data",
    }:
        print(
            "  Reacquisition freshness: "
            f"{summary.get('primary_target_closure_forecast_reacquisition_freshness_status', 'insufficient-data')} "
            f"({summary.get('primary_target_closure_forecast_reacquisition_freshness_reason', 'No reacquisition-freshness reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reacquisition_freshness_summary"):
        print(
            f"  Reacquisition freshness summary: {summary['closure_forecast_reacquisition_freshness_summary']}"
        )
    if summary.get("primary_target_closure_forecast_persistence_reset_status") not in {
        None,
        "",
        "none",
    }:
        print(
            "  Persistence reset controls: "
            f"{summary.get('primary_target_closure_forecast_persistence_reset_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_persistence_reset_reason', 'No persistence-reset reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_persistence_reset_summary"):
        print(
            f"  Persistence reset summary: {summary['closure_forecast_persistence_reset_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_refresh_recovery_status") not in {
        None,
        "",
        "none",
    }:
        print(
            "  Reset refresh recovery: "
            f"{summary.get('primary_target_closure_forecast_reset_refresh_recovery_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_refresh_recovery_score', 0.0):.2f})"
        )
    if summary.get("closure_forecast_reset_refresh_recovery_summary"):
        print(
            f"  Reset refresh recovery summary: {summary['closure_forecast_reset_refresh_recovery_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_status") not in {
        None,
        "",
        "none",
    }:
        print(
            "  Reset re-entry controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_reason', 'No reset re-entry reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_summary"):
        print(f"  Reset re-entry summary: {summary['closure_forecast_reset_reentry_summary']}")
    if summary.get("primary_target_closure_forecast_reset_reentry_persistence_status") not in {
        None,
        "",
        "none",
    }:
        print(
            "  Reset re-entry persistence: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_persistence_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_persistence_score', 0.0):.2f}; "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_age_runs', 0)} run(s))"
        )
    if summary.get("closure_forecast_reset_reentry_persistence_summary"):
        print(
            "  Reset re-entry persistence summary: "
            f"{summary['closure_forecast_reset_reentry_persistence_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_churn_status") not in {
        None,
        "",
        "none",
    }:
        print(
            "  Reset re-entry churn controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_churn_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_churn_reason', 'No reset re-entry churn reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_churn_summary"):
        print(
            "  Reset re-entry churn summary: "
            f"{summary['closure_forecast_reset_reentry_churn_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_freshness_status") not in {
        None,
        "",
        "none",
    }:
        print(
            "  Reset re-entry freshness: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_freshness_status', 'insufficient-data')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_freshness_reason', 'No reset re-entry freshness reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_freshness_summary"):
        print(
            "  Reset re-entry freshness summary: "
            f"{summary['closure_forecast_reset_reentry_freshness_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_reset_status") not in {
        None,
        "",
        "none",
    }:
        print(
            "  Reset re-entry reset controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_reset_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_reset_reason', 'No reset re-entry reset reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_reset_summary"):
        print(
            "  Reset re-entry reset summary: "
            f"{summary['closure_forecast_reset_reentry_reset_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_refresh_recovery_status") not in {
        None,
        "",
        "none",
    }:
        print(
            "  Reset re-entry refresh recovery: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_refresh_recovery_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_refresh_recovery_score', 0.0):.2f})"
        )
    if summary.get("closure_forecast_reset_reentry_refresh_recovery_summary"):
        print(
            "  Reset re-entry refresh recovery summary: "
            f"{summary['closure_forecast_reset_reentry_refresh_recovery_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_status") not in {
        None,
        "",
        "none",
    }:
        print(
            "  Reset re-entry rebuild controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reason', 'No reset re-entry rebuild reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_summary"):
        print(
            "  Reset re-entry rebuild summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_freshness_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild freshness: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_freshness_status', 'insufficient-data')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_freshness_reason', 'No reset re-entry rebuild freshness reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_freshness_summary"):
        print(
            "  Reset re-entry rebuild freshness summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_freshness_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reset_status") not in {
        None,
        "",
        "none",
    }:
        print(
            "  Reset re-entry rebuild reset controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reset_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reset_reason', 'No reset re-entry rebuild reset reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reset_summary"):
        print(
            "  Reset re-entry rebuild reset summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reset_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_refresh_recovery_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild refresh recovery: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_refresh_recovery_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_refresh_recovery_score', 0.0):.2f})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_refresh_recovery_summary"):
        print(
            "  Reset re-entry rebuild refresh recovery summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_refresh_recovery_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_status") not in {
        None,
        "",
        "none",
    }:
        print(
            "  Reset re-entry rebuild re-entry controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_reason', 'No reset re-entry rebuild re-entry reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_summary"):
        print(
            "  Reset re-entry rebuild re-entry summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry persistence: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_score', 0.0):.2f}; "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_age_runs', 0)} run(s))"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_persistence_summary"):
        print(
            "  Reset re-entry rebuild re-entry persistence summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_persistence_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry churn controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_reason', 'No reset re-entry rebuild re-entry churn reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_churn_summary"):
        print(
            "  Reset re-entry rebuild re-entry churn summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_churn_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_freshness_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry freshness: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_freshness_status', 'insufficient-data')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_freshness_reason', 'No reset re-entry rebuild re-entry freshness reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_freshness_summary"):
        print(
            "  Reset re-entry rebuild re-entry freshness summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_freshness_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_reset_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry reset controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_reset_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_reset_reason', 'No reset re-entry rebuild re-entry reset reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_reset_summary"):
        print(
            "  Reset re-entry rebuild re-entry reset summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_reset_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry refresh recovery: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status', 'none')} "
            f"({summary.get('closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_summary', 'No reset re-entry rebuild re-entry refresh recovery summary is recorded yet.')})"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reason', 'No reset re-entry rebuild re-entry restore reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_summary"):
        print(
            "  Reset re-entry rebuild re-entry restore summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_status"
    ) not in {None, "", "insufficient-data"}:
        print(
            "  Reset re-entry rebuild re-entry restore freshness: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_status', 'insufficient-data')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_reason', 'No reset re-entry rebuild re-entry restore freshness reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_summary"):
        print(
            "  Reset re-entry rebuild re-entry restore freshness summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reset_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore reset controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reset_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reset_reason', 'No reset re-entry rebuild re-entry restore reset reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_reset_summary"):
        print(
            "  Reset re-entry rebuild re-entry restore reset summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_reset_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore refresh recovery: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_status', 'none')} "
            f"({summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_summary', 'No reset re-entry rebuild re-entry restore refresh recovery summary is recorded yet.')})"
        )
    if summary.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_summary"
    ):
        print(
            "  Reset re-entry rebuild re-entry restore refresh recovery summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-restore controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason', 'No reset re-entry rebuild re-entry restore re-restore reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_summary"):
        print(
            "  Reset re-entry rebuild re-entry restore re-restore summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-restore persistence: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_score', 0.0):.2f}; "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_age_runs', 0)} run(s))"
        )
    if summary.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_summary"
    ):
        print(
            "  Reset re-entry rebuild re-entry restore re-restore persistence summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-restore churn controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_reason', 'No reset re-entry rebuild re-entry restore re-restore churn reason is recorded yet.')})"
        )
    if summary.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_summary"
    ):
        print(
            "  Reset re-entry rebuild re-entry restore re-restore churn summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status"
    ) not in {None, "", "insufficient-data"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-restore freshness: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status', 'insufficient-data')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_reason', 'No reset re-entry rebuild re-entry restore re-restore freshness reason is recorded yet.')})"
        )
    if summary.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_summary"
    ):
        print(
            "  Reset re-entry rebuild re-entry restore re-restore freshness summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-restore reset controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_reason', 'No reset re-entry rebuild re-entry restore re-restore reset reason is recorded yet.')})"
        )
    if summary.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_summary"
    ):
        print(
            "  Reset re-entry rebuild re-entry restore re-restore reset summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-restore refresh recovery: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_status', 'none')} "
            f"({summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_summary', 'No reset re-entry rebuild re-entry restore re-restore refresh recovery summary is recorded yet.')})"
        )
    if summary.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_summary"
    ):
        print(
            "  Reset re-entry rebuild re-entry restore re-restore refresh recovery summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-re-restore controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason', 'No reset re-entry rebuild re-entry restore re-re-restore reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_summary"):
        print(
            "  Reset re-entry rebuild re-entry restore re-re-restore summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-re-restore persistence: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score', 0.0):.2f}; "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs', 0)} run(s))"
        )
    if summary.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_summary"
    ):
        print(
            "  Reset re-entry rebuild re-entry restore re-re-restore persistence summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-re-restore churn controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason', 'No reset re-entry rebuild re-entry restore re-re-restore churn reason is recorded yet.')})"
        )
    if summary.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_summary"
    ):
        print(
            "  Reset re-entry rebuild re-entry restore re-re-restore churn summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-re-restore refresh recovery: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status', 'none')} "
            f"({summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_summary', 'No reset re-entry rebuild re-entry restore re-re-restore refresh recovery summary is recorded yet.')})"
        )
    if summary.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_summary"
    ):
        print(
            "  Reset re-entry rebuild re-entry restore re-re-restore refresh recovery summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-re-re-restore controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_reason', 'No reset re-entry rebuild re-entry restore re-re-re-restore reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_summary"):
        print(
            "  Reset re-entry rebuild re-entry restore re-re-re-restore summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-re-re-restore persistence: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score', 0.0):.2f}; "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs', 0)} run(s))"
        )
    if summary.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_summary"
    ):
        print(
            "  Reset re-entry rebuild re-entry restore re-re-re-restore persistence summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild re-entry restore re-re-re-restore churn controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason', 'No reset re-entry rebuild re-entry restore re-re-re-restore churn reason is recorded yet.')})"
        )
    if summary.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_summary"
    ):
        print(
            "  Reset re-entry rebuild re-entry restore re-re-re-restore churn summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_summary']}"
        )
    if summary.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_persistence_status"
    ) not in {None, "", "none"}:
        print(
            "  Reset re-entry rebuild persistence: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_persistence_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_persistence_score', 0.0):.2f}; "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_age_runs', 0)} run(s))"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_persistence_summary"):
        print(
            "  Reset re-entry rebuild persistence summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_persistence_summary']}"
        )
    if summary.get("primary_target_closure_forecast_reset_reentry_rebuild_churn_status") not in {
        None,
        "",
        "none",
    }:
        print(
            "  Reset re-entry rebuild churn controls: "
            f"{summary.get('primary_target_closure_forecast_reset_reentry_rebuild_churn_status', 'none')} "
            f"({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_churn_reason', 'No reset re-entry rebuild churn reason is recorded yet.')})"
        )
    if summary.get("closure_forecast_reset_reentry_rebuild_churn_summary"):
        print(
            "  Reset re-entry rebuild churn summary: "
            f"{summary['closure_forecast_reset_reentry_rebuild_churn_summary']}"
        )
    if summary.get("recommendation_drift_status"):
        print(
            "  Recommendation drift: "
            f"{summary.get('recommendation_drift_status', 'stable')} "
            f"({summary.get('recommendation_drift_summary', 'No recommendation-drift summary is recorded yet.')})"
        )
    if summary.get("exception_pattern_summary"):
        print(f"  Exception pattern summary: {summary['exception_pattern_summary']}")
    if summary.get("exception_retirement_summary"):
        print(f"  Exception retirement summary: {summary['exception_retirement_summary']}")
    if summary.get("policy_debt_summary"):
        print(f"  Policy debt summary: {summary['policy_debt_summary']}")
    if summary.get("trust_normalization_summary"):
        print(f"  Trust normalization summary: {summary['trust_normalization_summary']}")
    if summary.get("class_memory_summary"):
        print(f"  Class memory summary: {summary['class_memory_summary']}")
    if summary.get("class_decay_summary"):
        print(f"  Class decay summary: {summary['class_decay_summary']}")
    if summary.get("recommendation_quality_summary"):
        print(f"  Recommendation quality: {summary['recommendation_quality_summary']}")
    if summary.get("confidence_validation_status"):
        print(
            "  Confidence validation: "
            f"{summary.get('confidence_validation_status', 'insufficient-data')} "
            f"({summary.get('confidence_calibration_summary', 'No confidence-calibration summary is recorded yet.')})"
        )
    if summary.get("recent_validation_outcomes"):
        recent_bits = []
        for item in (summary.get("recent_validation_outcomes") or [])[:3]:
            recent_bits.append(
                f"{item.get('target_label', 'Operator target')} "
                f"[{item.get('confidence_label', 'low')}] -> {str(item.get('outcome', 'unresolved')).replace('_', ' ')}"
            )
        print("  Recent confidence outcomes: " + "; ".join(recent_bits))
    if summary.get("follow_through_summary"):
        print(f"  Follow-through: {summary['follow_through_summary']}")
    lane_labels = [
        ("blocked", "Blocked"),
        ("urgent", "Needs Attention Now"),
        ("ready", "Ready for Manual Action"),
        ("deferred", "Safe to Defer"),
    ]
    for lane, label in lane_labels:
        lane_items = [item for item in queue if item.get("lane") == lane]
        items = [item for item in lane_items if should_print_control_center_item(item)]
        if not items:
            continue
        print(f"\n{label}")
        for item in items[:8]:
            repo = f"{item['repo']}: " if item.get("repo") else ""
            print(f"  - {repo}{item.get('title', 'Triage item')}")
            print(f"    {item.get('summary', '')}")
            print(f"    Why: {item.get('lane_reason', item.get('lane_label', ''))}")
            print(f"    Next: {item.get('recommended_action', '')}")
            if item.get("catalog_line"):
                print(f"    Catalog: {item.get('catalog_line')}")
            if item.get("intent_alignment"):
                print(
                    "    Intent alignment: "
                    f"{item.get('intent_alignment')} ({item.get('intent_alignment_reason', 'No alignment reason is recorded yet.')})"
                )
        omitted_count = len(lane_items) - len(items)
        if omitted_count > 0:
            print(f"    ({omitted_count} experiment/manual-only item(s) hidden from default view.)")
    if recent_changes:
        print("\nRecently Changed")
        for item in recent_changes[:5]:
            subject = (
                item.get("repo") or item.get("repo_full_name") or item.get("item_id") or "portfolio"
            )
            print(
                f"  - {item.get('generated_at', '')[:10]} {subject}: {item.get('summary', item.get('kind', 'change'))}"
            )


