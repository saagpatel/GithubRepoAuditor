from __future__ import annotations

from datetime import datetime, timezone

QUIET_HANDOFF = "No new blocking or urgent drift is surfaced in the latest operator snapshot."

GENERIC_RECOMMENDATION_PHRASES = (
    "continue the normal audit/control-center loop",
    "continue the normal operator loop",
    "review the latest state",
    "inspect the latest changes and decide on next action",
    "monitor future audits",
    "open the repo queue details",
)


def control_center_artifact_payload(report_data: dict, snapshot: dict) -> dict:
    return {
        "username": report_data.get("username", "unknown"),
        "generated_at": report_data.get("generated_at", ""),
        "report_reference": report_data.get("latest_report_path", ""),
        "watch_state": report_data.get("watch_state", {}),
        "campaign_summary": report_data.get("campaign_summary", {}),
        "writeback_preview": report_data.get("writeback_preview", {}),
        "writeback_results": report_data.get("writeback_results", {}),
        "managed_state_drift": report_data.get("managed_state_drift", []),
        "operator_summary": snapshot.get("operator_summary", {}),
        "operator_queue": snapshot.get("operator_queue", []),
        "portfolio_outcomes_summary": snapshot.get("portfolio_outcomes_summary", {}),
        "operator_effectiveness_summary": snapshot.get("operator_effectiveness_summary", {}),
        "high_pressure_queue_history": snapshot.get("high_pressure_queue_history", []),
        "operator_setup_health": snapshot.get("operator_setup_health", {}),
        "operator_recent_changes": snapshot.get("operator_recent_changes", []),
        "review_summary": report_data.get("review_summary", {}),
        "preflight_summary": report_data.get("preflight_summary", {}),
    }


def _headline_for_queue(queue: list[dict], setup_health: dict) -> str:
    if setup_health.get("blocking_errors", 0):
        return "Setup blockers need to be cleared before the next trustworthy run."
    if any(item["lane"] == "blocked" for item in queue):
        return "A blocked operator item needs attention before more manual action."
    if any(item["lane"] == "urgent" for item in queue):
        return "There is live drift or high-severity change that needs attention now."
    if any(item["lane"] == "ready" for item in queue):
        return "Manual review and apply work is ready when you are."
    if any(item["lane"] == "deferred" for item in queue):
        return "Everything currently surfaced is safe to defer."
    return "No operator triage items are currently surfaced."


def _build_operator_handoff(
    queue: list[dict],
    recent_changes: list[dict],
    setup_health: dict,
    watch_guidance: dict,
    follow_through: dict,
    resolution_trend: dict,
    confidence_calibration: dict,
    confidence: dict,
    raw_next_action: str,
) -> dict:
    primary_target = resolution_trend.get("primary_target") or {}
    top_item = primary_target or (queue[0] if queue else {})
    top_lane = top_item.get("lane", "")
    top_summary = _summarize_operator_change(top_item, recent_changes, resolution_trend)
    trust_policy = confidence.get("primary_target_trust_policy", "monitor")
    trust_policy_reason = confidence.get("primary_target_trust_policy_reason", "")
    what_changed = _with_trust_policy_brief(
        top_summary,
        trust_policy,
        resolution_trend.get("primary_target_exception_status", "none"),
        resolution_trend.get("primary_target_trust_recovery_status", "none"),
        resolution_trend.get("primary_target_exception_retirement_status", "none"),
        resolution_trend.get("primary_target_policy_debt_status", "none"),
        resolution_trend.get("primary_target_class_normalization_status", "none"),
        resolution_trend.get("primary_target_class_memory_freshness_status", "insufficient-data"),
        resolution_trend.get("primary_target_class_decay_status", "none"),
        resolution_trend.get("primary_target_class_trust_reweight_direction", "neutral"),
        primary_target.get("class_trust_reweight_effect", "none"),
        resolution_trend.get("primary_target_class_trust_momentum_status", "insufficient-data"),
        resolution_trend.get("primary_target_class_reweight_stability_status", "watch"),
        resolution_trend.get("primary_target_class_reweight_transition_status", "none"),
        resolution_trend.get("primary_target_class_transition_health_status", "none"),
        resolution_trend.get("primary_target_class_transition_resolution_status", "none"),
        resolution_trend.get("primary_target_pending_debt_freshness_status", "insufficient-data"),
        resolution_trend.get("primary_target_closure_forecast_reweight_direction", "neutral"),
        primary_target.get("closure_forecast_reweight_effect", "none"),
        resolution_trend.get(
            "primary_target_closure_forecast_freshness_status", "insufficient-data"
        ),
        resolution_trend.get("primary_target_closure_forecast_decay_status", "none"),
        resolution_trend.get("primary_target_closure_forecast_refresh_recovery_status", "none"),
        resolution_trend.get("primary_target_closure_forecast_reacquisition_status", "none"),
        resolution_trend.get(
            "primary_target_closure_forecast_momentum_status", "insufficient-data"
        ),
        resolution_trend.get("primary_target_closure_forecast_stability_status", "watch"),
        resolution_trend.get("primary_target_closure_forecast_hysteresis_status", "none"),
    )
    escalation_reason = _escalation_reason(queue, setup_health, watch_guidance)
    urgency = _handoff_urgency(queue, setup_health)
    why_it_matters = _why_it_matters(
        urgency,
        escalation_reason,
        watch_guidance,
        top_item,
        resolution_trend,
        confidence_calibration,
        trust_policy,
        trust_policy_reason,
    )
    next_action = _adapt_next_action(
        raw_next_action,
        confidence_calibration,
        trust_policy=confidence.get("next_action_trust_policy", trust_policy),
        trust_policy_reason=confidence.get("next_action_trust_policy_reason", trust_policy_reason),
    )
    operator_note = (
        f"{what_changed} {why_it_matters} "
        f"{resolution_trend.get('trend_summary', '')} "
        f"{resolution_trend.get('resolution_evidence_summary', '')} "
        f"{_trust_exception_note(resolution_trend)} "
        f"{_exception_pattern_note(resolution_trend)} "
        f"{_trust_recovery_note(resolution_trend)} "
        f"{_recovery_confidence_note(resolution_trend)} "
        f"{_exception_retirement_note(resolution_trend)} "
        f"{_policy_debt_note(resolution_trend)} "
        f"{_class_normalization_note(resolution_trend)} "
        f"{_class_memory_note(resolution_trend)} "
        f"{_class_decay_note(resolution_trend)} "
        f"{_class_reweighting_note(resolution_trend)} "
        f"{_class_momentum_note(resolution_trend)} "
        f"{_class_reweight_stability_note(resolution_trend)} "
        f"{_class_transition_health_note(resolution_trend)} "
        f"{_class_transition_resolution_note(resolution_trend)} "
        f"{_transition_closure_confidence_note(resolution_trend)} "
        f"{_class_pending_debt_note(resolution_trend)} "
        f"{_pending_debt_freshness_note(resolution_trend)} "
        f"{_closure_forecast_reweighting_note(resolution_trend)} "
        f"{_closure_forecast_freshness_note(resolution_trend)} "
        f"{_closure_forecast_momentum_note(resolution_trend)} "
        f"{_closure_forecast_decay_note(resolution_trend)} "
        f"{_closure_forecast_refresh_recovery_note(resolution_trend)} "
        f"{_closure_forecast_reacquisition_note(resolution_trend)} "
        f"{_closure_forecast_reacquisition_persistence_note(resolution_trend)} "
        f"{_closure_forecast_recovery_churn_note(resolution_trend)} "
        f"{_closure_forecast_reset_refresh_recovery_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_persistence_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_churn_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_freshness_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_reset_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_refresh_recovery_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_freshness_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_reset_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_refresh_recovery_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_reentry_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_reentry_persistence_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_reentry_churn_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_reentry_freshness_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_reentry_reset_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_reentry_restore_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_reentry_restore_churn_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_reentry_restore_reset_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_persistence_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_churn_note(resolution_trend)} "
        f"{_closure_forecast_hysteresis_note(resolution_trend)} "
        f"{_recommendation_drift_note(resolution_trend)} "
        f"{confidence_calibration.get('confidence_calibration_summary', '')} "
        f"{confidence.get('adaptive_confidence_summary', '')} "
        f"{follow_through.get('follow_through_summary', '')} "
        f"{follow_through.get('follow_through_recovery_summary', '')} "
        f"Next: {next_action}"
    ).strip()
    return {
        "urgency": urgency,
        "escalation_reason": escalation_reason,
        "what_changed": what_changed,
        "why_it_matters": why_it_matters,
        "what_to_do_next": next_action,
        "next_operator_action": next_action,
        "operator_note": operator_note,
        "top_lane": top_lane,
    }


def build_operator_summary(
    *,
    triage_view: str,
    review_summary: dict,
    report_data: dict,
    setup_health: dict,
    recent_changes: list[dict],
    watch_guidance: dict,
    handoff: dict,
    follow_through: dict,
    resolution_trend: dict,
    confidence_calibration: dict,
    confidence: dict,
    decision_quality: dict,
    operator_effectiveness: dict,
    action_sync: dict,
    action_sync_packets: dict,
    action_sync_outcomes: dict,
    action_sync_tuning: dict,
    intervention_ledger: dict,
    action_sync_automation: dict,
    approval_ledger: dict,
    queue: list[dict],
    counts: dict,
) -> dict:
    summary = {
        "headline": _headline_for_queue(queue, setup_health),
        "selected_view": triage_view,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_run_id": review_summary.get("source_run_id", ""),
        "report_reference": report_data.get("latest_report_path", ""),
        "counts": counts,
        "total_items": len(queue),
        "review_status": review_summary.get("status", "unavailable"),
        "operator_setup_health": setup_health,
        "operator_recent_changes": recent_changes,
        "watch_strategy": watch_guidance.get("requested_strategy", "manual"),
        "watch_enabled": watch_guidance.get("watch_enabled", False),
        "watch_chosen_mode": watch_guidance.get("chosen_mode", ""),
        "watch_decision_reason": watch_guidance.get("reason", ""),
        "watch_decision_summary": watch_guidance.get("reason_summary", ""),
        "next_recommended_run_mode": watch_guidance.get("next_recommended_run_mode", ""),
        "full_refresh_due": watch_guidance.get("full_refresh_due", False),
        "latest_trusted_baseline": watch_guidance.get("latest_trusted_baseline", {}),
        "operator_watch_decision": watch_guidance,
        "urgency": handoff["urgency"],
        "escalation_reason": handoff["escalation_reason"],
        "what_changed": handoff["what_changed"],
        "why_it_matters": handoff["why_it_matters"],
        "what_to_do_next": handoff["what_to_do_next"],
        "next_operator_action": handoff["next_operator_action"],
        "operator_note": handoff["operator_note"],
        "repeat_urgent_count": follow_through["repeat_urgent_count"],
        "stale_item_count": follow_through["stale_item_count"],
        "oldest_open_item_days": follow_through["oldest_open_item_days"],
        "quiet_streak_runs": follow_through["quiet_streak_runs"],
        "follow_through_summary": follow_through["follow_through_summary"],
        "follow_through_status_counts": follow_through["follow_through_status_counts"],
        "follow_through_checkpoint_counts": follow_through["follow_through_checkpoint_counts"],
        "follow_through_escalation_counts": follow_through["follow_through_escalation_counts"],
        "follow_through_recovery_counts": follow_through["follow_through_recovery_counts"],
        "follow_through_recovery_persistence_counts": follow_through[
            "follow_through_recovery_persistence_counts"
        ],
        "follow_through_relapse_churn_counts": follow_through[
            "follow_through_relapse_churn_counts"
        ],
        "follow_through_recovery_freshness_counts": follow_through[
            "follow_through_recovery_freshness_counts"
        ],
        "follow_through_recovery_decay_counts": follow_through[
            "follow_through_recovery_decay_counts"
        ],
        "follow_through_recovery_memory_reset_counts": follow_through[
            "follow_through_recovery_memory_reset_counts"
        ],
        "top_unattempted_items": follow_through["top_unattempted_items"],
        "top_stale_follow_through_items": follow_through["top_stale_follow_through_items"],
        "top_overdue_follow_through_items": follow_through["top_overdue_follow_through_items"],
        "top_escalation_items": follow_through["top_escalation_items"],
        "top_recovering_follow_through_items": follow_through[
            "top_recovering_follow_through_items"
        ],
        "top_retiring_follow_through_items": follow_through["top_retiring_follow_through_items"],
        "top_relapsing_follow_through_items": follow_through["top_relapsing_follow_through_items"],
        "top_fragile_recovery_items": follow_through["top_fragile_recovery_items"],
        "top_sustained_recovery_items": follow_through["top_sustained_recovery_items"],
        "top_churn_follow_through_items": follow_through["top_churn_follow_through_items"],
        "top_fresh_recovery_items": follow_through["top_fresh_recovery_items"],
        "top_stale_recovery_items": follow_through["top_stale_recovery_items"],
        "top_softening_recovery_items": follow_through["top_softening_recovery_items"],
        "top_reset_recovery_items": follow_through["top_reset_recovery_items"],
        "top_rebuilding_recovery_items": follow_through["top_rebuilding_recovery_items"],
        "follow_through_checkpoint_summary": follow_through["follow_through_checkpoint_summary"],
        "follow_through_escalation_summary": follow_through["follow_through_escalation_summary"],
        "follow_through_recovery_summary": follow_through["follow_through_recovery_summary"],
        "follow_through_recovery_persistence_summary": follow_through[
            "follow_through_recovery_persistence_summary"
        ],
        "follow_through_relapse_churn_summary": follow_through[
            "follow_through_relapse_churn_summary"
        ],
        "follow_through_recovery_freshness_summary": follow_through[
            "follow_through_recovery_freshness_summary"
        ],
        "follow_through_recovery_decay_summary": follow_through[
            "follow_through_recovery_decay_summary"
        ],
        "follow_through_recovery_memory_reset_summary": follow_through[
            "follow_through_recovery_memory_reset_summary"
        ],
        "trend_status": resolution_trend["trend_status"],
        "new_attention_count": resolution_trend["new_attention_count"],
        "resolved_attention_count": resolution_trend["resolved_attention_count"],
        "persisting_attention_count": resolution_trend["persisting_attention_count"],
        "reopened_attention_count": resolution_trend["reopened_attention_count"],
        "history_window_runs": resolution_trend["history_window_runs"],
        "aging_status": resolution_trend["aging_status"],
        "primary_target_reason": resolution_trend["primary_target_reason"],
        "primary_target_done_criteria": resolution_trend["primary_target_done_criteria"],
        "closure_guidance": resolution_trend["closure_guidance"],
        "attention_age_bands": resolution_trend["attention_age_bands"],
        "chronic_item_count": resolution_trend["chronic_item_count"],
        "newly_stale_count": resolution_trend["newly_stale_count"],
        "longest_persisting_item": resolution_trend["longest_persisting_item"],
        "accountability_summary": resolution_trend["accountability_summary"],
        "primary_target": resolution_trend["primary_target"],
        "resolution_targets": resolution_trend["resolution_targets"],
        "trend_summary": resolution_trend["trend_summary"],
        "primary_target_exception_status": resolution_trend["primary_target_exception_status"],
        "primary_target_exception_reason": resolution_trend["primary_target_exception_reason"],
        "recommendation_drift_status": resolution_trend["recommendation_drift_status"],
        "recommendation_drift_summary": resolution_trend["recommendation_drift_summary"],
        "policy_flip_hotspots": resolution_trend["policy_flip_hotspots"],
        "primary_target_exception_pattern_status": resolution_trend[
            "primary_target_exception_pattern_status"
        ],
        "primary_target_exception_pattern_reason": resolution_trend[
            "primary_target_exception_pattern_reason"
        ],
        "primary_target_trust_recovery_status": resolution_trend[
            "primary_target_trust_recovery_status"
        ],
        "primary_target_trust_recovery_reason": resolution_trend[
            "primary_target_trust_recovery_reason"
        ],
        "exception_pattern_summary": resolution_trend["exception_pattern_summary"],
        "false_positive_exception_hotspots": resolution_trend["false_positive_exception_hotspots"],
        "trust_recovery_window_runs": resolution_trend["trust_recovery_window_runs"],
        "primary_target_recovery_confidence_score": resolution_trend[
            "primary_target_recovery_confidence_score"
        ],
        "primary_target_recovery_confidence_label": resolution_trend[
            "primary_target_recovery_confidence_label"
        ],
        "primary_target_recovery_confidence_reasons": resolution_trend[
            "primary_target_recovery_confidence_reasons"
        ],
        "recovery_confidence_summary": resolution_trend["recovery_confidence_summary"],
        "primary_target_exception_retirement_status": resolution_trend[
            "primary_target_exception_retirement_status"
        ],
        "primary_target_exception_retirement_reason": resolution_trend[
            "primary_target_exception_retirement_reason"
        ],
        "exception_retirement_summary": resolution_trend["exception_retirement_summary"],
        "retired_exception_hotspots": resolution_trend["retired_exception_hotspots"],
        "sticky_exception_hotspots": resolution_trend["sticky_exception_hotspots"],
        "exception_retirement_window_runs": resolution_trend["exception_retirement_window_runs"],
        "primary_target_policy_debt_status": resolution_trend["primary_target_policy_debt_status"],
        "primary_target_policy_debt_reason": resolution_trend["primary_target_policy_debt_reason"],
        "primary_target_class_normalization_status": resolution_trend[
            "primary_target_class_normalization_status"
        ],
        "primary_target_class_normalization_reason": resolution_trend[
            "primary_target_class_normalization_reason"
        ],
        "policy_debt_summary": resolution_trend["policy_debt_summary"],
        "trust_normalization_summary": resolution_trend["trust_normalization_summary"],
        "policy_debt_hotspots": resolution_trend["policy_debt_hotspots"],
        "normalized_class_hotspots": resolution_trend["normalized_class_hotspots"],
        "class_normalization_window_runs": resolution_trend["class_normalization_window_runs"],
        "primary_target_class_memory_freshness_status": resolution_trend[
            "primary_target_class_memory_freshness_status"
        ],
        "primary_target_class_memory_freshness_reason": resolution_trend[
            "primary_target_class_memory_freshness_reason"
        ],
        "primary_target_class_decay_status": resolution_trend["primary_target_class_decay_status"],
        "primary_target_class_decay_reason": resolution_trend["primary_target_class_decay_reason"],
        "class_memory_summary": resolution_trend["class_memory_summary"],
        "class_decay_summary": resolution_trend["class_decay_summary"],
        "stale_class_memory_hotspots": resolution_trend["stale_class_memory_hotspots"],
        "fresh_class_signal_hotspots": resolution_trend["fresh_class_signal_hotspots"],
        "class_decay_window_runs": resolution_trend["class_decay_window_runs"],
        "primary_target_weighted_class_support_score": resolution_trend[
            "primary_target_weighted_class_support_score"
        ],
        "primary_target_weighted_class_caution_score": resolution_trend[
            "primary_target_weighted_class_caution_score"
        ],
        "primary_target_class_trust_reweight_score": resolution_trend[
            "primary_target_class_trust_reweight_score"
        ],
        "primary_target_class_trust_reweight_direction": resolution_trend[
            "primary_target_class_trust_reweight_direction"
        ],
        "primary_target_class_trust_reweight_reasons": resolution_trend[
            "primary_target_class_trust_reweight_reasons"
        ],
        "class_reweighting_summary": resolution_trend["class_reweighting_summary"],
        "supporting_class_hotspots": resolution_trend["supporting_class_hotspots"],
        "caution_class_hotspots": resolution_trend["caution_class_hotspots"],
        "class_reweighting_window_runs": resolution_trend["class_reweighting_window_runs"],
        "primary_target_class_trust_momentum_score": resolution_trend[
            "primary_target_class_trust_momentum_score"
        ],
        "primary_target_class_trust_momentum_status": resolution_trend[
            "primary_target_class_trust_momentum_status"
        ],
        "primary_target_class_reweight_stability_status": resolution_trend[
            "primary_target_class_reweight_stability_status"
        ],
        "primary_target_class_reweight_transition_status": resolution_trend["primary_target"].get(
            "class_reweight_transition_status",
            resolution_trend["primary_target_class_reweight_transition_status"],
        )
        if resolution_trend.get("primary_target")
        else resolution_trend["primary_target_class_reweight_transition_status"],
        "primary_target_class_reweight_transition_reason": resolution_trend["primary_target"].get(
            "class_reweight_transition_reason",
            resolution_trend["primary_target_class_reweight_transition_reason"],
        )
        if resolution_trend.get("primary_target")
        else resolution_trend["primary_target_class_reweight_transition_reason"],
        "class_momentum_summary": resolution_trend["class_momentum_summary"],
        "class_reweight_stability_summary": resolution_trend["class_reweight_stability_summary"],
        "class_transition_window_runs": resolution_trend["class_transition_window_runs"],
        "primary_target_class_transition_health_status": resolution_trend[
            "primary_target_class_transition_health_status"
        ],
        "primary_target_class_transition_health_reason": resolution_trend[
            "primary_target_class_transition_health_reason"
        ],
        "primary_target_class_transition_resolution_status": resolution_trend[
            "primary_target_class_transition_resolution_status"
        ],
        "primary_target_class_transition_resolution_reason": resolution_trend[
            "primary_target_class_transition_resolution_reason"
        ],
        "class_transition_health_summary": resolution_trend["class_transition_health_summary"],
        "class_transition_resolution_summary": resolution_trend[
            "class_transition_resolution_summary"
        ],
        "class_transition_age_window_runs": resolution_trend["class_transition_age_window_runs"],
        "stalled_transition_hotspots": resolution_trend["stalled_transition_hotspots"],
        "resolving_transition_hotspots": resolution_trend["resolving_transition_hotspots"],
        "primary_target_transition_closure_confidence_score": resolution_trend[
            "primary_target_transition_closure_confidence_score"
        ],
        "primary_target_transition_closure_confidence_label": resolution_trend[
            "primary_target_transition_closure_confidence_label"
        ],
        "primary_target_transition_closure_likely_outcome": resolution_trend["primary_target"].get(
            "transition_closure_likely_outcome",
            resolution_trend["primary_target_transition_closure_likely_outcome"],
        )
        if resolution_trend.get("primary_target")
        else resolution_trend["primary_target_transition_closure_likely_outcome"],
        "primary_target_transition_closure_confidence_reasons": resolution_trend[
            "primary_target_transition_closure_confidence_reasons"
        ],
        "transition_closure_confidence_summary": resolution_trend[
            "transition_closure_confidence_summary"
        ],
        "transition_closure_window_runs": resolution_trend["transition_closure_window_runs"],
        "primary_target_class_pending_debt_status": resolution_trend[
            "primary_target_class_pending_debt_status"
        ],
        "primary_target_class_pending_debt_reason": resolution_trend[
            "primary_target_class_pending_debt_reason"
        ],
        "class_pending_debt_summary": resolution_trend["class_pending_debt_summary"],
        "class_pending_resolution_summary": resolution_trend["class_pending_resolution_summary"],
        "class_pending_debt_window_runs": resolution_trend["class_pending_debt_window_runs"],
        "pending_debt_hotspots": resolution_trend["pending_debt_hotspots"],
        "healthy_pending_resolution_hotspots": resolution_trend[
            "healthy_pending_resolution_hotspots"
        ],
        "primary_target_pending_debt_freshness_status": resolution_trend[
            "primary_target_pending_debt_freshness_status"
        ],
        "primary_target_pending_debt_freshness_reason": resolution_trend[
            "primary_target_pending_debt_freshness_reason"
        ],
        "pending_debt_freshness_summary": resolution_trend["pending_debt_freshness_summary"],
        "pending_debt_decay_summary": resolution_trend["pending_debt_decay_summary"],
        "stale_pending_debt_hotspots": resolution_trend["stale_pending_debt_hotspots"],
        "fresh_pending_resolution_hotspots": resolution_trend["fresh_pending_resolution_hotspots"],
        "pending_debt_decay_window_runs": resolution_trend["pending_debt_decay_window_runs"],
        "primary_target_weighted_pending_resolution_support_score": resolution_trend[
            "primary_target_weighted_pending_resolution_support_score"
        ],
        "primary_target_weighted_pending_debt_caution_score": resolution_trend[
            "primary_target_weighted_pending_debt_caution_score"
        ],
        "primary_target_closure_forecast_reweight_score": resolution_trend[
            "primary_target_closure_forecast_reweight_score"
        ],
        "primary_target_closure_forecast_reweight_direction": resolution_trend[
            "primary_target_closure_forecast_reweight_direction"
        ],
        "primary_target_closure_forecast_reweight_reasons": resolution_trend[
            "primary_target_closure_forecast_reweight_reasons"
        ],
        "closure_forecast_reweighting_summary": resolution_trend[
            "closure_forecast_reweighting_summary"
        ],
        "closure_forecast_reweighting_window_runs": resolution_trend[
            "closure_forecast_reweighting_window_runs"
        ],
        "supporting_pending_resolution_hotspots": resolution_trend[
            "supporting_pending_resolution_hotspots"
        ],
        "caution_pending_debt_hotspots": resolution_trend["caution_pending_debt_hotspots"],
        "primary_target_closure_forecast_momentum_score": resolution_trend[
            "primary_target_closure_forecast_momentum_score"
        ],
        "primary_target_closure_forecast_momentum_status": resolution_trend[
            "primary_target_closure_forecast_momentum_status"
        ],
        "primary_target_closure_forecast_stability_status": resolution_trend[
            "primary_target_closure_forecast_stability_status"
        ],
        "primary_target_closure_forecast_hysteresis_status": resolution_trend[
            "primary_target_closure_forecast_hysteresis_status"
        ],
        "primary_target_closure_forecast_hysteresis_reason": resolution_trend[
            "primary_target_closure_forecast_hysteresis_reason"
        ],
        "closure_forecast_momentum_summary": resolution_trend["closure_forecast_momentum_summary"],
        "closure_forecast_stability_summary": resolution_trend[
            "closure_forecast_stability_summary"
        ],
        "closure_forecast_hysteresis_summary": resolution_trend[
            "closure_forecast_hysteresis_summary"
        ],
        "closure_forecast_transition_window_runs": resolution_trend[
            "closure_forecast_transition_window_runs"
        ],
        "sustained_confirmation_hotspots": resolution_trend["sustained_confirmation_hotspots"],
        "sustained_clearance_hotspots": resolution_trend["sustained_clearance_hotspots"],
        "oscillating_closure_forecast_hotspots": resolution_trend[
            "oscillating_closure_forecast_hotspots"
        ],
        "primary_target_closure_forecast_freshness_status": resolution_trend[
            "primary_target_closure_forecast_freshness_status"
        ],
        "primary_target_closure_forecast_freshness_reason": resolution_trend[
            "primary_target_closure_forecast_freshness_reason"
        ],
        "primary_target_closure_forecast_decay_status": resolution_trend[
            "primary_target_closure_forecast_decay_status"
        ],
        "primary_target_closure_forecast_decay_reason": resolution_trend[
            "primary_target_closure_forecast_decay_reason"
        ],
        "closure_forecast_freshness_summary": resolution_trend[
            "closure_forecast_freshness_summary"
        ],
        "closure_forecast_decay_summary": resolution_trend["closure_forecast_decay_summary"],
        "stale_closure_forecast_hotspots": resolution_trend["stale_closure_forecast_hotspots"],
        "fresh_closure_forecast_signal_hotspots": resolution_trend[
            "fresh_closure_forecast_signal_hotspots"
        ],
        "closure_forecast_decay_window_runs": resolution_trend[
            "closure_forecast_decay_window_runs"
        ],
        "primary_target_closure_forecast_refresh_recovery_score": resolution_trend[
            "primary_target_closure_forecast_refresh_recovery_score"
        ],
        "primary_target_closure_forecast_refresh_recovery_status": resolution_trend[
            "primary_target_closure_forecast_refresh_recovery_status"
        ],
        "primary_target_closure_forecast_reacquisition_status": resolution_trend[
            "primary_target_closure_forecast_reacquisition_status"
        ],
        "primary_target_closure_forecast_reacquisition_reason": resolution_trend[
            "primary_target_closure_forecast_reacquisition_reason"
        ],
        "closure_forecast_refresh_recovery_summary": resolution_trend[
            "closure_forecast_refresh_recovery_summary"
        ],
        "closure_forecast_reacquisition_summary": resolution_trend[
            "closure_forecast_reacquisition_summary"
        ],
        "closure_forecast_refresh_window_runs": resolution_trend[
            "closure_forecast_refresh_window_runs"
        ],
        "recovering_confirmation_hotspots": resolution_trend["recovering_confirmation_hotspots"],
        "recovering_clearance_hotspots": resolution_trend["recovering_clearance_hotspots"],
        "primary_target_closure_forecast_reacquisition_age_runs": resolution_trend[
            "primary_target_closure_forecast_reacquisition_age_runs"
        ],
        "primary_target_closure_forecast_reacquisition_persistence_score": resolution_trend[
            "primary_target_closure_forecast_reacquisition_persistence_score"
        ],
        "primary_target_closure_forecast_reacquisition_persistence_status": resolution_trend[
            "primary_target_closure_forecast_reacquisition_persistence_status"
        ],
        "primary_target_closure_forecast_reacquisition_persistence_reason": resolution_trend[
            "primary_target_closure_forecast_reacquisition_persistence_reason"
        ],
        "closure_forecast_reacquisition_persistence_summary": resolution_trend[
            "closure_forecast_reacquisition_persistence_summary"
        ],
        "closure_forecast_reacquisition_window_runs": resolution_trend[
            "closure_forecast_reacquisition_window_runs"
        ],
        "just_reacquired_hotspots": resolution_trend["just_reacquired_hotspots"],
        "holding_reacquisition_hotspots": resolution_trend["holding_reacquisition_hotspots"],
        "primary_target_closure_forecast_recovery_churn_score": resolution_trend[
            "primary_target_closure_forecast_recovery_churn_score"
        ],
        "primary_target_closure_forecast_recovery_churn_status": resolution_trend[
            "primary_target_closure_forecast_recovery_churn_status"
        ],
        "primary_target_closure_forecast_recovery_churn_reason": resolution_trend[
            "primary_target_closure_forecast_recovery_churn_reason"
        ],
        "closure_forecast_recovery_churn_summary": resolution_trend[
            "closure_forecast_recovery_churn_summary"
        ],
        "recovery_churn_hotspots": resolution_trend["recovery_churn_hotspots"],
        "primary_target_closure_forecast_reacquisition_freshness_status": resolution_trend[
            "primary_target_closure_forecast_reacquisition_freshness_status"
        ],
        "primary_target_closure_forecast_reacquisition_freshness_reason": resolution_trend[
            "primary_target_closure_forecast_reacquisition_freshness_reason"
        ],
        "closure_forecast_reacquisition_freshness_summary": resolution_trend[
            "closure_forecast_reacquisition_freshness_summary"
        ],
        "primary_target_closure_forecast_persistence_reset_status": resolution_trend[
            "primary_target_closure_forecast_persistence_reset_status"
        ],
        "primary_target_closure_forecast_persistence_reset_reason": resolution_trend[
            "primary_target_closure_forecast_persistence_reset_reason"
        ],
        "closure_forecast_persistence_reset_summary": resolution_trend[
            "closure_forecast_persistence_reset_summary"
        ],
        "stale_reacquisition_hotspots": resolution_trend["stale_reacquisition_hotspots"],
        "fresh_reacquisition_signal_hotspots": resolution_trend[
            "fresh_reacquisition_signal_hotspots"
        ],
        "closure_forecast_reacquisition_decay_window_runs": resolution_trend[
            "closure_forecast_reacquisition_decay_window_runs"
        ],
        "primary_target_closure_forecast_reset_refresh_recovery_score": resolution_trend[
            "primary_target_closure_forecast_reset_refresh_recovery_score"
        ],
        "primary_target_closure_forecast_reset_refresh_recovery_status": resolution_trend[
            "primary_target_closure_forecast_reset_refresh_recovery_status"
        ],
        "primary_target_closure_forecast_reset_reentry_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_status"
        ],
        "primary_target_closure_forecast_reset_reentry_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_reason"
        ],
        "closure_forecast_reset_refresh_recovery_summary": resolution_trend[
            "closure_forecast_reset_refresh_recovery_summary"
        ],
        "closure_forecast_reset_reentry_summary": resolution_trend[
            "closure_forecast_reset_reentry_summary"
        ],
        "closure_forecast_reset_refresh_window_runs": resolution_trend[
            "closure_forecast_reset_refresh_window_runs"
        ],
        "recovering_from_confirmation_reset_hotspots": resolution_trend[
            "recovering_from_confirmation_reset_hotspots"
        ],
        "recovering_from_clearance_reset_hotspots": resolution_trend[
            "recovering_from_clearance_reset_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_age_runs": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_age_runs"
        ],
        "primary_target_closure_forecast_reset_reentry_persistence_score": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_persistence_score"
        ],
        "primary_target_closure_forecast_reset_reentry_persistence_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_persistence_status"
        ],
        "primary_target_closure_forecast_reset_reentry_persistence_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_persistence_reason"
        ],
        "closure_forecast_reset_reentry_persistence_summary": resolution_trend[
            "closure_forecast_reset_reentry_persistence_summary"
        ],
        "closure_forecast_reset_reentry_window_runs": resolution_trend[
            "closure_forecast_reset_reentry_window_runs"
        ],
        "just_reentered_hotspots": resolution_trend["just_reentered_hotspots"],
        "holding_reset_reentry_hotspots": resolution_trend["holding_reset_reentry_hotspots"],
        "primary_target_closure_forecast_reset_reentry_churn_score": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_churn_score"
        ],
        "primary_target_closure_forecast_reset_reentry_churn_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_churn_status"
        ],
        "primary_target_closure_forecast_reset_reentry_churn_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_churn_reason"
        ],
        "closure_forecast_reset_reentry_churn_summary": resolution_trend[
            "closure_forecast_reset_reentry_churn_summary"
        ],
        "reset_reentry_churn_hotspots": resolution_trend["reset_reentry_churn_hotspots"],
        "primary_target_closure_forecast_reset_reentry_freshness_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_freshness_status"
        ],
        "primary_target_closure_forecast_reset_reentry_freshness_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_freshness_reason"
        ],
        "closure_forecast_reset_reentry_freshness_summary": resolution_trend[
            "closure_forecast_reset_reentry_freshness_summary"
        ],
        "primary_target_closure_forecast_reset_reentry_reset_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_reset_status"
        ],
        "primary_target_closure_forecast_reset_reentry_reset_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_reset_reason"
        ],
        "closure_forecast_reset_reentry_reset_summary": resolution_trend[
            "closure_forecast_reset_reentry_reset_summary"
        ],
        "stale_reset_reentry_hotspots": resolution_trend["stale_reset_reentry_hotspots"],
        "fresh_reset_reentry_signal_hotspots": resolution_trend[
            "fresh_reset_reentry_signal_hotspots"
        ],
        "closure_forecast_reset_reentry_decay_window_runs": resolution_trend[
            "closure_forecast_reset_reentry_decay_window_runs"
        ],
        "primary_target_closure_forecast_reset_reentry_refresh_recovery_score": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_refresh_recovery_score"
        ],
        "primary_target_closure_forecast_reset_reentry_refresh_recovery_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_refresh_recovery_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reason"
        ],
        "closure_forecast_reset_reentry_refresh_recovery_summary": resolution_trend[
            "closure_forecast_reset_reentry_refresh_recovery_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_summary"
        ],
        "closure_forecast_reset_reentry_refresh_window_runs": resolution_trend[
            "closure_forecast_reset_reentry_refresh_window_runs"
        ],
        "recovering_from_confirmation_reentry_reset_hotspots": resolution_trend[
            "recovering_from_confirmation_reentry_reset_hotspots"
        ],
        "recovering_from_clearance_reentry_reset_hotspots": resolution_trend[
            "recovering_from_clearance_reentry_reset_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_age_runs": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_age_runs"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_persistence_score": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_persistence_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_persistence_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_persistence_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_persistence_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_persistence_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_persistence_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_persistence_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_window_runs": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_window_runs"
        ],
        "just_rebuilt_hotspots": resolution_trend["just_rebuilt_hotspots"],
        "holding_reset_reentry_rebuild_hotspots": resolution_trend[
            "holding_reset_reentry_rebuild_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_churn_score": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_churn_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_churn_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_churn_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_churn_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_churn_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_churn_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_churn_summary"
        ],
        "reset_reentry_rebuild_churn_hotspots": resolution_trend[
            "reset_reentry_rebuild_churn_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_freshness_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_freshness_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_freshness_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_freshness_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_freshness_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_freshness_summary"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reset_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reset_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reset_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reset_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reset_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reset_summary"
        ],
        "stale_reset_reentry_rebuild_hotspots": resolution_trend[
            "stale_reset_reentry_rebuild_hotspots"
        ],
        "fresh_reset_reentry_rebuild_signal_hotspots": resolution_trend[
            "fresh_reset_reentry_rebuild_signal_hotspots"
        ],
        "closure_forecast_reset_reentry_rebuild_decay_window_runs": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_decay_window_runs"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_refresh_recovery_score": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_refresh_recovery_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_refresh_recovery_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_refresh_recovery_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_refresh_recovery_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_refresh_recovery_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_refresh_window_runs": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_refresh_window_runs"
        ],
        "recovering_from_confirmation_rebuild_reset_hotspots": resolution_trend[
            "recovering_from_confirmation_rebuild_reset_hotspots"
        ],
        "recovering_from_clearance_rebuild_reset_hotspots": resolution_trend[
            "recovering_from_clearance_rebuild_reset_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_age_runs": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_age_runs"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_score": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_persistence_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_persistence_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_window_runs": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_window_runs"
        ],
        "just_reentered_rebuild_hotspots": resolution_trend["just_reentered_rebuild_hotspots"],
        "holding_reset_reentry_rebuild_reentry_hotspots": resolution_trend[
            "holding_reset_reentry_rebuild_reentry_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_score": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_churn_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_churn_summary"
        ],
        "reset_reentry_rebuild_reentry_churn_hotspots": resolution_trend[
            "reset_reentry_rebuild_reentry_churn_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_freshness_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_freshness_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_freshness_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_freshness_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_freshness_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_freshness_summary"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_reset_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_reset_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_reset_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_reset_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_reset_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_reset_summary"
        ],
        "stale_reset_reentry_rebuild_reentry_hotspots": resolution_trend[
            "stale_reset_reentry_rebuild_reentry_hotspots"
        ],
        "fresh_reset_reentry_rebuild_reentry_signal_hotspots": resolution_trend[
            "fresh_reset_reentry_rebuild_reentry_signal_hotspots"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_decay_window_runs": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_decay_window_runs"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_score": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_refresh_window_runs": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_refresh_window_runs"
        ],
        "recovering_from_confirmation_rebuild_reentry_reset_hotspots": resolution_trend[
            "recovering_from_confirmation_rebuild_reentry_reset_hotspots"
        ],
        "recovering_from_clearance_rebuild_reentry_reset_hotspots": resolution_trend[
            "recovering_from_clearance_rebuild_reentry_reset_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_age_runs": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_age_runs"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_score": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_window_runs": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_window_runs"
        ],
        "just_restored_rebuild_reentry_hotspots": resolution_trend[
            "just_restored_rebuild_reentry_hotspots"
        ],
        "holding_reset_reentry_rebuild_reentry_restore_hotspots": resolution_trend[
            "holding_reset_reentry_rebuild_reentry_restore_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_churn_score": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_churn_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_churn_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_churn_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_churn_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_churn_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_churn_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_churn_summary"
        ],
        "reset_reentry_rebuild_reentry_restore_churn_hotspots": resolution_trend[
            "reset_reentry_rebuild_reentry_restore_churn_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_summary"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reset_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reset_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reset_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reset_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_reset_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_reset_summary"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_score": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_window_runs": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_window_runs"
        ],
        "recovering_from_confirmation_rebuild_reentry_restore_reset_hotspots": resolution_trend[
            "recovering_from_confirmation_rebuild_reentry_restore_reset_hotspots"
        ],
        "recovering_from_clearance_rebuild_reentry_restore_reset_hotspots": resolution_trend[
            "recovering_from_clearance_rebuild_reentry_restore_reset_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_age_runs": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_age_runs"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_score": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_window_runs": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_window_runs"
        ],
        "just_rerestored_rebuild_reentry_hotspots": resolution_trend[
            "just_rerestored_rebuild_reentry_hotspots"
        ],
        "holding_reset_reentry_rebuild_reentry_restore_rerestore_hotspots": resolution_trend[
            "holding_reset_reentry_rebuild_reentry_restore_rerestore_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_score": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_summary"
        ],
        "reset_reentry_rebuild_reentry_restore_rerestore_churn_hotspots": resolution_trend[
            "reset_reentry_rebuild_reentry_restore_rerestore_churn_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_summary"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_summary"
        ],
        "stale_reset_reentry_rebuild_reentry_restore_rerestore_hotspots": resolution_trend[
            "stale_reset_reentry_rebuild_reentry_restore_rerestore_hotspots"
        ],
        "fresh_reset_reentry_rebuild_reentry_restore_rerestore_signal_hotspots": resolution_trend[
            "fresh_reset_reentry_rebuild_reentry_restore_rerestore_signal_hotspots"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_decay_window_runs": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_decay_window_runs"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_score": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_window_runs": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_window_runs"
        ],
        "recovering_from_confirmation_rebuild_reentry_rerestore_reset_hotspots": resolution_trend[
            "recovering_from_confirmation_rebuild_reentry_rerestore_reset_hotspots"
        ],
        "recovering_from_clearance_rebuild_reentry_rerestore_reset_hotspots": resolution_trend[
            "recovering_from_clearance_rebuild_reentry_rerestore_reset_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_window_runs": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_window_runs"
        ],
        "just_rererestored_rebuild_reentry_hotspots": resolution_trend[
            "just_rererestored_rebuild_reentry_hotspots"
        ],
        "holding_reset_reentry_rebuild_reentry_restore_rererestore_hotspots": resolution_trend[
            "holding_reset_reentry_rebuild_reentry_restore_rererestore_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_score": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_summary"
        ],
        "reset_reentry_rebuild_reentry_restore_rererestore_churn_hotspots": resolution_trend[
            "reset_reentry_rebuild_reentry_restore_rererestore_churn_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_summary"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_summary"
        ],
        "stale_reset_reentry_rebuild_reentry_restore_rererestore_hotspots": resolution_trend[
            "stale_reset_reentry_rebuild_reentry_restore_rererestore_hotspots"
        ],
        "fresh_reset_reentry_rebuild_reentry_restore_rererestore_signal_hotspots": resolution_trend[
            "fresh_reset_reentry_rebuild_reentry_restore_rererestore_signal_hotspots"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_decay_window_runs": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_decay_window_runs"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_score": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_window_runs": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_window_runs"
        ],
        "recovering_from_confirmation_rebuild_reentry_rererestore_reset_hotspots": resolution_trend[
            "recovering_from_confirmation_rebuild_reentry_rererestore_reset_hotspots"
        ],
        "recovering_from_clearance_rebuild_reentry_rererestore_reset_hotspots": resolution_trend[
            "recovering_from_clearance_rebuild_reentry_rererestore_reset_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_window_runs": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_window_runs"
        ],
        "just_rerererestored_rebuild_reentry_hotspots": resolution_trend[
            "just_rerererestored_rebuild_reentry_hotspots"
        ],
        "holding_reset_reentry_rebuild_reentry_restore_rerererestore_hotspots": resolution_trend[
            "holding_reset_reentry_rebuild_reentry_restore_rerererestore_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason": resolution_trend[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_summary": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_summary"
        ],
        "reset_reentry_rebuild_reentry_restore_rerererestore_churn_hotspots": resolution_trend[
            "reset_reentry_rebuild_reentry_restore_rerererestore_churn_hotspots"
        ],
        "stale_reset_reentry_rebuild_reentry_restore_hotspots": resolution_trend[
            "stale_reset_reentry_rebuild_reentry_restore_hotspots"
        ],
        "fresh_reset_reentry_rebuild_reentry_restore_signal_hotspots": resolution_trend[
            "fresh_reset_reentry_rebuild_reentry_restore_signal_hotspots"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_decay_window_runs": resolution_trend[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_decay_window_runs"
        ],
        "sustained_class_hotspots": resolution_trend["sustained_class_hotspots"],
        "oscillating_class_hotspots": resolution_trend["oscillating_class_hotspots"],
        "decision_memory_status": resolution_trend["decision_memory_status"],
        "primary_target_last_seen_at": resolution_trend["primary_target_last_seen_at"],
        "primary_target_last_intervention": resolution_trend["primary_target_last_intervention"],
        "primary_target_last_outcome": resolution_trend["primary_target_last_outcome"],
        "primary_target_resolution_evidence": resolution_trend[
            "primary_target_resolution_evidence"
        ],
        "recent_interventions": resolution_trend["recent_interventions"],
        "recently_quieted_count": resolution_trend["recently_quieted_count"],
        "confirmed_resolved_count": resolution_trend["confirmed_resolved_count"],
        "reopened_after_resolution_count": resolution_trend["reopened_after_resolution_count"],
        "decision_memory_window_runs": resolution_trend["decision_memory_window_runs"],
        "resolution_evidence_summary": resolution_trend["resolution_evidence_summary"],
        "primary_target_confidence_score": confidence["primary_target_confidence_score"],
        "primary_target_confidence_label": confidence["primary_target_confidence_label"],
        "primary_target_confidence_reasons": confidence["primary_target_confidence_reasons"],
        "next_action_confidence_score": confidence["next_action_confidence_score"],
        "next_action_confidence_label": confidence["next_action_confidence_label"],
        "next_action_confidence_reasons": confidence["next_action_confidence_reasons"],
        "decision_quality_v1": decision_quality,
        "recommendation_quality_summary": decision_quality["recommendation_quality_summary"],
        "primary_target_trust_policy": decision_quality["primary_target_trust_policy"],
        "primary_target_trust_policy_reason": decision_quality[
            "primary_target_trust_policy_reason"
        ],
        "next_action_trust_policy": decision_quality["next_action_trust_policy"],
        "next_action_trust_policy_reason": decision_quality["next_action_trust_policy_reason"],
        "adaptive_confidence_summary": decision_quality["adaptive_confidence_summary"],
        "confidence_validation_status": decision_quality["confidence_validation_status"],
        "decision_quality_status": decision_quality["decision_quality_status"],
        "decision_quality_authority_cap": decision_quality["authority_cap"],
        "human_skepticism_required": decision_quality["human_skepticism_required"],
        "downgrade_reasons": decision_quality["downgrade_reasons"],
        "confidence_window_runs": decision_quality["evidence_window_runs"],
        "validation_window_runs": decision_quality["validation_window_runs"],
        "judged_recommendation_count": decision_quality["judged_recommendation_count"],
        "validated_recommendation_count": decision_quality["validated_recommendation_count"],
        "partially_validated_recommendation_count": decision_quality[
            "partially_validated_recommendation_count"
        ],
        "unresolved_recommendation_count": decision_quality["unresolved_recommendation_count"],
        "reopened_recommendation_count": decision_quality["reopened_recommendation_count"],
        "insufficient_future_runs_count": confidence_calibration["insufficient_future_runs_count"],
        "high_confidence_hit_rate": decision_quality["high_confidence_hit_rate"],
        "medium_confidence_hit_rate": decision_quality["medium_confidence_hit_rate"],
        "low_confidence_caution_rate": decision_quality["low_confidence_caution_rate"],
        "recent_validation_outcomes": decision_quality["recent_validation_outcomes"],
        "confidence_calibration_summary": decision_quality["confidence_calibration_summary"],
        "portfolio_outcomes_summary": operator_effectiveness["portfolio_outcomes_summary"],
        "operator_effectiveness_summary": operator_effectiveness["operator_effectiveness_summary"],
        "high_pressure_queue_history": operator_effectiveness["high_pressure_queue_history"],
        "high_pressure_queue_trend_status": operator_effectiveness[
            "high_pressure_queue_trend_status"
        ],
        "high_pressure_queue_trend_summary": operator_effectiveness[
            "high_pressure_queue_trend_summary"
        ],
        "recent_reopened_recommendations": operator_effectiveness[
            "recent_reopened_recommendations"
        ],
        "recent_closed_actions": operator_effectiveness["recent_closed_actions"],
        "recent_regression_examples": operator_effectiveness["recent_regression_examples"],
        "campaign_readiness_summary": action_sync["campaign_readiness_summary"],
        "action_sync_summary": action_sync["action_sync_summary"],
        "next_action_sync_step": action_sync_tuning["next_action_sync_step"],
        "action_sync_packets": action_sync_packets["action_sync_packets"],
        "apply_readiness_summary": action_sync_packets["apply_readiness_summary"],
        "next_apply_candidate": action_sync_tuning["next_apply_candidate"],
        "top_apply_ready_campaigns": action_sync_tuning["top_apply_ready_campaigns"],
        "top_preview_ready_campaigns": action_sync_tuning["top_preview_ready_campaigns"],
        "top_drift_review_campaigns": action_sync_tuning["top_drift_review_campaigns"],
        "top_blocked_campaigns": action_sync_tuning["top_blocked_campaigns"],
        "top_ready_to_apply_packets": action_sync_tuning["top_ready_to_apply_packets"],
        "top_needs_approval_packets": action_sync_tuning["top_needs_approval_packets"],
        "top_review_drift_packets": action_sync_tuning["top_review_drift_packets"],
        "action_sync_outcomes": action_sync_outcomes["action_sync_outcomes"],
        "campaign_outcomes_summary": action_sync_outcomes["campaign_outcomes_summary"],
        "next_monitoring_step": action_sync_outcomes["next_monitoring_step"],
        "top_monitor_now_campaigns": action_sync_outcomes["top_monitor_now_campaigns"],
        "top_holding_clean_campaigns": action_sync_outcomes["top_holding_clean_campaigns"],
        "top_reopened_campaigns": action_sync_outcomes["top_reopened_campaigns"],
        "top_drift_returned_campaigns": action_sync_outcomes["top_drift_returned_campaigns"],
        "action_sync_tuning": action_sync_tuning["action_sync_tuning"],
        "campaign_tuning_summary": action_sync_tuning["campaign_tuning_summary"],
        "next_tuned_campaign": action_sync_tuning["next_tuned_campaign"],
        "top_proven_campaigns": action_sync_tuning["top_proven_campaigns"],
        "top_caution_campaigns": action_sync_tuning["top_caution_campaigns"],
        "top_thin_evidence_campaigns": action_sync_tuning["top_thin_evidence_campaigns"],
        "historical_portfolio_intelligence": intervention_ledger[
            "historical_portfolio_intelligence"
        ],
        "intervention_ledger_summary": intervention_ledger["intervention_ledger_summary"],
        "next_historical_focus": intervention_ledger["next_historical_focus"],
        "top_relapsing_repos": intervention_ledger["top_relapsing_repos"],
        "top_persistent_pressure_repos": intervention_ledger["top_persistent_pressure_repos"],
        "top_improving_repos": intervention_ledger["top_improving_repos"],
        "top_holding_repos": intervention_ledger["top_holding_repos"],
        "action_sync_automation": action_sync_automation["action_sync_automation"],
        "automation_guidance_summary": action_sync_automation["automation_guidance_summary"],
        "next_safe_automation_step": action_sync_automation["next_safe_automation_step"],
        "top_preview_safe_campaigns": action_sync_automation["top_preview_safe_campaigns"],
        "top_apply_manual_campaigns": action_sync_automation["top_apply_manual_campaigns"],
        "top_approval_first_campaigns": action_sync_automation["top_approval_first_campaigns"],
        "top_follow_up_safe_campaigns": action_sync_automation["top_follow_up_safe_campaigns"],
        "top_manual_only_campaigns": action_sync_automation["top_manual_only_campaigns"],
        "approval_ledger": approval_ledger["approval_ledger"],
        "approval_workflow_summary": approval_ledger["approval_workflow_summary"],
        "next_approval_review": approval_ledger["next_approval_review"],
        "top_ready_for_review_approvals": approval_ledger["top_ready_for_review_approvals"],
        "top_needs_reapproval_approvals": approval_ledger["top_needs_reapproval_approvals"],
        "top_overdue_approval_followups": approval_ledger["top_overdue_approval_followups"],
        "top_due_soon_approval_followups": approval_ledger["top_due_soon_approval_followups"],
        "top_approved_manual_approvals": approval_ledger["top_approved_manual_approvals"],
        "top_blocked_approvals": approval_ledger["top_blocked_approvals"],
    }
    return summary


def _is_generic_recommendation(action: str) -> bool:
    normalized = (action or "").strip().lower()
    if not normalized:
        return True
    return any(phrase in normalized for phrase in GENERIC_RECOMMENDATION_PHRASES)


def _handoff_urgency(queue: list[dict], setup_health: dict) -> str:
    if setup_health.get("blocking_errors", 0):
        return "blocked"
    if any(item.get("lane") == "blocked" for item in queue):
        return "blocked"
    if any(item.get("lane") == "urgent" for item in queue):
        return "urgent"
    if any(item.get("lane") == "ready" for item in queue):
        return "ready"
    if any(item.get("lane") == "deferred" for item in queue):
        return "deferred"
    return "quiet"


def _summarize_operator_change(
    top_item: dict, recent_changes: list[dict], resolution_trend: dict
) -> str:
    trend_status = resolution_trend.get("trend_status", "stable")
    decision_memory_status = resolution_trend.get("decision_memory_status", "new")
    if trend_status == "quiet":
        return f"No new blocking or urgent drift is surfaced, and the queue has stayed quiet for {resolution_trend.get('quiet_streak_runs', 0)} consecutive run(s)."
    if top_item and decision_memory_status == "reopened":
        subject = f"{top_item.get('repo')}: " if top_item.get("repo") else ""
        return f"{subject}{top_item.get('title', 'Operator change')} returned after an earlier quiet or resolved period and is back at the top of the queue."
    if top_item and top_item.get("aging_status") == "chronic":
        subject = f"{top_item.get('repo')}: " if top_item.get("repo") else ""
        return f"{subject}{top_item.get('title', 'Operator change')} has survived multiple cycles and remains the top target."
    if top_item and decision_memory_status in {"attempted", "persisting"}:
        subject = f"{top_item.get('repo')}: " if top_item.get("repo") else ""
        return f"{subject}{top_item.get('title', 'Operator change')} is still open after earlier intervention and remains the main target."
    if top_item and top_item.get("newly_stale"):
        subject = f"{top_item.get('repo')}: " if top_item.get("repo") else ""
        return f"{subject}{top_item.get('title', 'Operator change')} has crossed into follow-through debt and is now the main target."
    if top_item and trend_status == "worsening":
        subject = f"{top_item.get('repo')}: " if top_item.get("repo") else ""
        return f"{subject}{top_item.get('title', 'Operator change')} is the new top priority."
    if top_item and trend_status == "improving":
        subject = f"{top_item.get('repo')}: " if top_item.get("repo") else ""
        return (
            f"{resolution_trend.get('resolved_attention_count', 0)} item(s) cleared since the last run; "
            f"{subject}{top_item.get('title', 'Operator change')} remains the highest-value unresolved target."
        )
    if (
        top_item
        and trend_status == "stable"
        and resolution_trend.get("persisting_attention_count", 0)
    ):
        subject = f"{top_item.get('repo')}: " if top_item.get("repo") else ""
        return f"{subject}{top_item.get('title', 'Operator change')} is still open from the prior run and remains the main target."
    if top_item:
        subject = f"{top_item.get('repo')}: " if top_item.get("repo") else ""
        detail = top_item.get("summary", "").strip()
        if detail:
            return f"{subject}{top_item.get('title', 'Operator change')} — {detail}"
        return f"{subject}{top_item.get('title', 'Operator change')}"
    if recent_changes:
        change = recent_changes[0]
        subject = (
            change.get("repo")
            or change.get("repo_full_name")
            or change.get("item_id")
            or "portfolio"
        )
        detail = change.get("summary", change.get("kind", "operator change"))
        return f"{subject}: {detail}"
    return QUIET_HANDOFF


def _next_operator_action(
    top_item: dict, watch_guidance: dict, follow_through: dict, resolution_trend: dict
) -> str:
    if top_item.get("kind") == "setup" and top_item.get("recommended_action"):
        return top_item["recommended_action"]
    if resolution_trend.get("trend_status") == "quiet":
        return f"Keep the operator loop light and only escalate if the next run breaks the {resolution_trend.get('quiet_streak_runs', 0)}-run quiet streak."
    if resolution_trend.get("decision_memory_status") == "reopened" and top_item.get(
        "closure_guidance"
    ):
        return top_item["closure_guidance"]
    if top_item.get("aging_status") == "chronic" and top_item.get("closure_guidance"):
        return top_item["closure_guidance"]
    if top_item.get("newly_stale") and top_item.get("closure_guidance"):
        return top_item["closure_guidance"]
    if resolution_trend.get("trend_status") == "worsening" and top_item.get("recommended_action"):
        return top_item["recommended_action"]
    if resolution_trend.get("trend_status") == "improving" and top_item.get("recommended_action"):
        return f"Close the remaining top target next: {top_item['recommended_action']}"
    if follow_through.get("stale_item_count", 0):
        return "Start with the oldest repeated blocked or urgent item before taking on newly ready work."
    if follow_through.get("quiet_streak_runs", 0) >= 2:
        return "Keep the operator loop lightweight and only escalate if the next scheduled run breaks the quiet streak."
    if top_item.get("recommended_action"):
        return top_item["recommended_action"]
    if watch_guidance.get("full_refresh_due"):
        return (
            "Run the next full audit to refresh the baseline before relying on incremental results."
        )
    return "Continue the normal audit/control-center loop and review the next artifact for change."


def _adapt_next_action(
    next_action: str,
    confidence_calibration: dict,
    *,
    trust_policy: str,
    trust_policy_reason: str,
) -> str:
    status = confidence_calibration.get("confidence_validation_status", "insufficient-data")
    if not next_action:
        return next_action
    if trust_policy == "act-now":
        return f"Act now: {next_action}"
    if trust_policy == "act-with-review":
        return f"Act with review: {next_action}"
    if trust_policy == "verify-first":
        return f"Verify before acting: {next_action}"
    if trust_policy_reason:
        return f"Monitor for now: {trust_policy_reason}"
    if status == "healthy" and not _is_generic_recommendation(next_action):
        return f"Monitor for now: {next_action}"
    return next_action


def _escalation_reason(queue: list[dict], setup_health: dict, watch_guidance: dict) -> str:
    if setup_health.get("blocking_errors", 0):
        return "setup-blocker"
    watch_reason = watch_guidance.get("reason", "")
    if watch_reason == "full-refresh-due":
        return "scheduled-full-refresh"
    if watch_reason in {"filter-or-profile-changed", "missing-trustworthy-baseline"}:
        return "stale-baseline"
    if any(item.get("lane") == "blocked" for item in queue):
        return "blocked-operator-item"
    if any(item.get("lane") == "urgent" for item in queue):
        return "drift-or-regression"
    if any(item.get("lane") == "ready" for item in queue):
        return "manual-review-ready"
    if any(item.get("lane") == "deferred" for item in queue):
        return "safe-to-defer"
    return "quiet"


def _why_it_matters(
    urgency: str,
    escalation_reason: str,
    watch_guidance: dict,
    top_item: dict,
    resolution_trend: dict,
    confidence_calibration: dict,
    trust_policy: str,
    trust_policy_reason: str,
) -> str:
    calibration_status = confidence_calibration.get(
        "confidence_validation_status", "insufficient-data"
    )
    calibration_sentence = _confidence_validation_sentence(calibration_status)
    primary_target = resolution_trend.get("primary_target") or top_item or {}
    trust_sentence = _trust_policy_sentence(
        trust_policy,
        trust_policy_reason,
        resolution_trend.get("primary_target_exception_status", "none"),
        resolution_trend.get("primary_target_exception_reason", ""),
        resolution_trend.get("recommendation_drift_status", "stable"),
        resolution_trend.get("primary_target_exception_pattern_status", "none"),
        resolution_trend.get("primary_target_exception_pattern_reason", ""),
        resolution_trend.get("primary_target_trust_recovery_status", "none"),
        resolution_trend.get("primary_target_trust_recovery_reason", ""),
        resolution_trend.get("primary_target_exception_retirement_status", "none"),
        resolution_trend.get("primary_target_exception_retirement_reason", ""),
        resolution_trend.get("primary_target_recovery_confidence_label", "low"),
        resolution_trend.get("primary_target_policy_debt_status", "none"),
        resolution_trend.get("primary_target_policy_debt_reason", ""),
        resolution_trend.get("primary_target_class_normalization_status", "none"),
        resolution_trend.get("primary_target_class_normalization_reason", ""),
        resolution_trend.get("primary_target_class_memory_freshness_status", "insufficient-data"),
        resolution_trend.get("primary_target_class_memory_freshness_reason", ""),
        resolution_trend.get("primary_target_class_decay_status", "none"),
        resolution_trend.get("primary_target_class_decay_reason", ""),
        resolution_trend.get("primary_target_class_trust_reweight_direction", "neutral"),
        primary_target.get("class_trust_reweight_effect", "none"),
        primary_target.get("class_trust_reweight_effect_reason", ""),
        resolution_trend.get("primary_target_class_transition_health_status", "none"),
        resolution_trend.get("primary_target_class_transition_health_reason", ""),
        resolution_trend.get("primary_target_class_transition_resolution_status", "none"),
        resolution_trend.get("primary_target_class_transition_resolution_reason", ""),
        resolution_trend.get("primary_target_pending_debt_freshness_status", "insufficient-data"),
        resolution_trend.get("primary_target_pending_debt_freshness_reason", ""),
        resolution_trend.get("primary_target_closure_forecast_reweight_direction", "neutral"),
        primary_target.get("closure_forecast_reweight_effect", "none"),
        primary_target.get("closure_forecast_reweight_effect_reason", ""),
        resolution_trend.get(
            "primary_target_closure_forecast_freshness_status", "insufficient-data"
        ),
        resolution_trend.get("primary_target_closure_forecast_decay_status", "none"),
        resolution_trend.get("primary_target_closure_forecast_refresh_recovery_status", "none"),
        resolution_trend.get("primary_target_closure_forecast_reacquisition_status", "none"),
        resolution_trend.get("primary_target_closure_forecast_reacquisition_reason", ""),
        resolution_trend.get(
            "primary_target_closure_forecast_reacquisition_persistence_status", "none"
        ),
        resolution_trend.get(
            "primary_target_closure_forecast_reacquisition_persistence_reason", ""
        ),
        resolution_trend.get("primary_target_closure_forecast_recovery_churn_status", "none"),
        resolution_trend.get("primary_target_closure_forecast_recovery_churn_reason", ""),
    )
    if urgency == "blocked":
        return f"A trustworthy next step is blocked until this is cleared. {trust_sentence} {calibration_sentence}".strip()
    if escalation_reason == "stale-baseline":
        return (
            "The latest baseline contract no longer matches, so incremental results should not be trusted until a full refresh completes. "
            f"{trust_sentence} {calibration_sentence}"
        ).strip()
    if escalation_reason == "scheduled-full-refresh":
        return (
            "The normal full-refresh cadence is due, so the next run should refresh portfolio truth before more incremental monitoring. "
            f"{trust_sentence} {calibration_sentence}"
        ).strip()
    if urgency == "urgent":
        if resolution_trend.get("decision_memory_status") == "reopened":
            return (
                "This item came back after earlier quiet or resolution, so it should be treated as a regression instead of a net-new issue. "
                f"{trust_sentence} {calibration_sentence}"
            ).strip()
        if resolution_trend.get("decision_memory_status") in {"attempted", "persisting"}:
            return (
                "A prior intervention has not cleared this item yet, so the next action should focus on proving closure instead of adding more noise. "
                f"{trust_sentence} {calibration_sentence}"
            ).strip()
        if top_item.get("aging_status") == "chronic":
            return (
                "This target has survived multiple cycles, so closing it now matters more than picking up newly ready work. "
                f"{trust_sentence} {calibration_sentence}"
            ).strip()
        if top_item.get("newly_stale"):
            return (
                "This target has crossed from routine monitoring into follow-through debt and should be closed before it turns chronic. "
                f"{trust_sentence} {calibration_sentence}"
            ).strip()
        if resolution_trend.get("trend_status") == "worsening":
            return (
                "The queue is moving in the wrong direction, so this should be reviewed before new noise compounds. "
                f"{trust_sentence} {calibration_sentence}"
            ).strip()
        if resolution_trend.get("trend_status") == "stable" and resolution_trend.get(
            "persisting_attention_count", 0
        ):
            return (
                "The same attention item is still open, so closing it now is more valuable than picking up newly ready work. "
                f"{trust_sentence} {calibration_sentence}"
            ).strip()
        return (
            "This has crossed into live drift, regression risk, or rollback exposure and should be reviewed before it spreads. "
            f"{trust_sentence} {calibration_sentence}"
        ).strip()
    if urgency == "ready":
        return f"Nothing is blocked, but there is manual review or apply work ready to move forward. {trust_sentence} {calibration_sentence}".strip()
    if urgency == "deferred":
        return f"The current queue is stable enough to defer without losing important context. {trust_sentence} {calibration_sentence}".strip()
    if resolution_trend.get("trend_status") == "quiet":
        return (
            f"The queue has stayed quiet for {resolution_trend.get('quiet_streak_runs', 0)} run(s), so no immediate intervention is needed. "
            f"{trust_sentence} {calibration_sentence}"
        ).strip()
    if watch_guidance.get("next_recommended_run_mode") == "incremental":
        return (
            "The latest baseline is still compatible, so the operator loop can stay lightweight for now. "
            f"{trust_sentence} {calibration_sentence}"
        ).strip()
    if top_item:
        return f"This remains worth a quick manual review before the next cycle. {trust_sentence} {calibration_sentence}".strip()
    return f"The latest run is quiet enough that no immediate operator intervention is required. {trust_sentence} {calibration_sentence}".strip()


def _confidence_validation_sentence(status: str) -> str:
    if status == "healthy":
        return "Recent high-confidence recommendations are mostly validating, so the current confidence signal has been earning trust."
    if status == "mixed":
        return "Recent confidence is still useful, but some outcomes have stayed judgment-heavy."
    if status == "noisy":
        return "Recent high-confidence guidance has missed often enough that this target should be verified before overcommitting."
    return "The confidence model is still too lightly exercised to judge whether the current signal is earning trust."


def _trust_policy_sentence(
    policy: str,
    reason: str,
    exception_status: str,
    exception_reason: str,
    drift_status: str,
    exception_pattern_status: str,
    exception_pattern_reason: str,
    trust_recovery_status: str,
    trust_recovery_reason: str,
    exception_retirement_status: str,
    exception_retirement_reason: str,
    recovery_confidence_label: str,
    policy_debt_status: str,
    policy_debt_reason: str,
    class_normalization_status: str,
    class_normalization_reason: str,
    class_memory_freshness_status: str,
    class_memory_freshness_reason: str,
    class_decay_status: str,
    class_decay_reason: str,
    class_trust_reweight_direction: str,
    class_trust_reweight_effect: str,
    class_trust_reweight_effect_reason: str,
    class_transition_health_status: str,
    class_transition_health_reason: str,
    class_transition_resolution_status: str,
    class_transition_resolution_reason: str,
    pending_debt_freshness_status: str,
    pending_debt_freshness_reason: str,
    closure_forecast_reweight_direction: str,
    closure_forecast_reweight_effect: str,
    closure_forecast_reweight_effect_reason: str,
    closure_forecast_freshness_status: str,
    closure_forecast_decay_status: str,
    closure_forecast_refresh_recovery_status: str,
    closure_forecast_reacquisition_status: str,
    closure_forecast_reacquisition_reason: str,
    closure_forecast_reacquisition_persistence_status: str,
    closure_forecast_reacquisition_persistence_reason: str,
    closure_forecast_recovery_churn_status: str,
    closure_forecast_recovery_churn_reason: str,
) -> str:
    if closure_forecast_recovery_churn_status == "blocked":
        detail = closure_forecast_recovery_churn_reason or reason
        return (
            f"Trust policy: keep the weaker class posture because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: keep the weaker class posture because local target instability is preventing restored confirmation-side forecasting from holding."
        )
    if closure_forecast_reacquisition_persistence_status == "sustained-confirmation":
        detail = (
            closure_forecast_reacquisition_persistence_reason
            or closure_forecast_reacquisition_reason
            or reason
        )
        return (
            f"Trust policy: keep the restored confirmation posture because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: keep the restored confirmation posture because fresh confirmation-side reacquisition has now held long enough to trust."
        )
    if closure_forecast_reacquisition_persistence_status == "sustained-clearance":
        detail = (
            closure_forecast_reacquisition_persistence_reason
            or closure_forecast_reacquisition_reason
            or reason
        )
        return (
            f"Trust policy: keep the restored clearance posture because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: keep the restored clearance posture because fresh clearance-side reacquisition has now held long enough to trust."
        )
    if closure_forecast_reacquisition_persistence_status in {
        "holding-confirmation",
        "holding-clearance",
    }:
        detail = (
            closure_forecast_reacquisition_persistence_reason
            or closure_forecast_reacquisition_reason
            or reason
        )
        return (
            f"Trust policy: keep the restored posture for now because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: keep the restored posture for now because fresh reacquisition is holding and has not started churning."
        )
    if closure_forecast_reacquisition_persistence_status == "just-reacquired":
        detail = (
            closure_forecast_reacquisition_persistence_reason
            or closure_forecast_reacquisition_reason
            or reason
        )
        return (
            f"Trust policy: keep the restored posture visible for now because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: keep the restored posture visible for now because it has only just been reacquired and still looks fragile."
        )
    if (
        closure_forecast_reacquisition_persistence_status == "reversing"
        or closure_forecast_recovery_churn_status == "churn"
    ):
        detail = (
            closure_forecast_recovery_churn_reason
            or closure_forecast_reacquisition_persistence_reason
            or reason
        )
        return (
            f"Trust policy: soften the restored posture again because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: soften the restored posture again because recovery is already wobbling too much to trust."
        )
    if closure_forecast_recovery_churn_status == "watch":
        detail = (
            closure_forecast_recovery_churn_reason
            or closure_forecast_reacquisition_persistence_reason
            or reason
        )
        return (
            f"Trust policy: keep the restored posture cautious because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: keep the restored posture cautious because recovery is wobbling and still needs follow-through."
        )
    if closure_forecast_reacquisition_status == "reacquired-confirmation":
        detail = closure_forecast_reacquisition_reason or reason
        return (
            f"Trust policy: keep the weaker class posture for now because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: keep the weaker class posture for now because stronger confirmation forecasting was re-earned safely."
        )
    if closure_forecast_reacquisition_status == "reacquired-clearance":
        detail = closure_forecast_reacquisition_reason or reason
        return (
            f"Trust policy: keep the weaker class posture because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: keep the weaker class posture because stronger clearance forecasting was re-earned safely."
        )
    if closure_forecast_reacquisition_status == "pending-confirmation-reacquisition":
        detail = closure_forecast_reacquisition_reason or reason
        return (
            f"Trust policy: keep the weaker class posture for now because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: keep the weaker class posture for now because confirmation-side recovery is visible, but stronger carry-forward has not been fully re-earned yet."
        )
    if closure_forecast_reacquisition_status == "pending-clearance-reacquisition":
        detail = closure_forecast_reacquisition_reason or reason
        return (
            f"Trust policy: keep the weaker class posture because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: keep the weaker class posture because clearance-side recovery is visible, but stronger carry-forward has not been fully re-earned yet."
        )
    if closure_forecast_reacquisition_status == "blocked":
        detail = closure_forecast_reacquisition_reason or reason
        return (
            f"Trust policy: keep the weaker class posture because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: keep the weaker class posture because local target instability is still preventing positive confirmation-side reacquisition."
        )
    if closure_forecast_refresh_recovery_status == "recovering-confirmation":
        return "Trust policy: keep the weaker class posture for now because fresh confirmation-side forecast evidence is returning, but it has not fully re-earned stronger carry-forward yet."
    if closure_forecast_refresh_recovery_status == "recovering-clearance":
        return "Trust policy: keep the weaker class posture because fresh clearance-side forecast evidence is returning, but it has not fully re-earned stronger carry-forward yet."
    if closure_forecast_refresh_recovery_status == "reacquiring-confirmation":
        return "Trust policy: keep the weaker class posture for now because fresh confirmation-side support is getting strong enough to re-earn stronger carry-forward soon."
    if closure_forecast_refresh_recovery_status == "reacquiring-clearance":
        return "Trust policy: keep the weaker class posture because fresh clearance-side pressure is getting strong enough to re-earn stronger carry-forward soon."
    if closure_forecast_refresh_recovery_status == "reversing":
        return "Trust policy: keep the weaker class posture because the fresh recovery attempt is changing direction and stronger carry-forward should stay softened."
    if closure_forecast_refresh_recovery_status == "blocked":
        return "Trust policy: keep the weaker class posture because local target instability is still preventing positive confirmation-side reacquisition."
    if class_transition_resolution_status == "confirmed":
        detail = class_transition_resolution_reason or reason
        return (
            f"Trust policy: keep the stronger class posture because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: keep the stronger class posture because the earlier pending class signal finally confirmed."
        )
    if class_transition_resolution_status == "cleared":
        detail = class_transition_resolution_reason or reason
        return (
            f"Trust policy: keep the weaker class posture because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: keep the weaker class posture because the earlier pending class signal faded before confirmation."
        )
    if class_transition_resolution_status == "expired":
        detail = class_transition_resolution_reason or reason
        return (
            f"Trust policy: keep the weaker class posture because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: keep the weaker class posture because the earlier pending class signal aged out."
        )
    if class_transition_resolution_status == "blocked":
        detail = class_transition_resolution_reason or class_transition_health_reason or reason
        return (
            f"Trust policy: keep the weaker class posture because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: keep the weaker class posture because local target instability is blocking a pending class transition."
        )
    if class_transition_health_status == "stalled":
        detail = class_transition_health_reason or reason
        return (
            f"Trust policy: keep the weaker class posture because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: keep the weaker class posture because the pending class signal has stalled."
        )
    if class_transition_health_status == "holding":
        detail = class_transition_health_reason or reason
        return (
            f"Trust policy: keep the weaker class posture because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: keep the weaker class posture because the pending class signal is holding but not strengthening."
        )
    if class_transition_health_status == "building":
        return "Trust policy: keep the weaker class posture for now because the pending class signal is still building and has not confirmed yet."
    if class_transition_health_status == "expired":
        detail = class_transition_health_reason or reason
        return (
            f"Trust policy: keep the weaker class posture because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: keep the weaker class posture because the earlier pending class signal expired."
        )
    if class_transition_health_status == "blocked":
        detail = class_transition_health_reason or reason
        return (
            f"Trust policy: keep the weaker class posture because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: keep the weaker class posture because local target instability is blocking a pending class transition."
        )
    if closure_forecast_reweight_effect == "clear-risk-strengthened":
        detail = closure_forecast_reweight_effect_reason or reason
        return (
            f"Trust policy: keep the weaker class posture because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: keep the weaker class posture because fresh pending debt is pushing the class signal toward clearance risk."
        )
    if closure_forecast_reweight_effect == "confirm-support-softened":
        detail = closure_forecast_reweight_effect_reason or pending_debt_freshness_reason or reason
        return (
            f"Trust policy: keep the weaker class posture because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: keep the weaker class posture because the pending forecast is aging and cannot support stronger confirmation from scratch."
        )
    if closure_forecast_reweight_effect == "clear-risk-softened":
        return "Trust policy: keep the current weaker posture, but older pending-debt patterns are fading rather than fully driving the forecast."
    if closure_forecast_decay_status == "confirmation-decayed":
        return "Trust policy: keep the weaker class posture because older confirmation-side forecast memory has started to age out."
    if closure_forecast_decay_status == "clearance-decayed":
        return "Trust policy: keep the weaker class posture because stronger clearance carry-forward has started to age out."
    if closure_forecast_decay_status == "blocked":
        return "Trust policy: keep the weaker class posture because local target instability still overrides closure-forecast freshness."
    if class_trust_reweight_effect == "normalization-boosted":
        detail = class_trust_reweight_effect_reason or reason
        return (
            f"Trust policy: act with review because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: act with review because fresh class support crossed the reweight threshold."
        )
    if class_trust_reweight_effect == "normalization-softened":
        detail = class_trust_reweight_effect_reason or reason
        return (
            f"Trust policy: verify first because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: verify first because class normalization weakened after reweighting."
        )
    if class_trust_reweight_effect == "policy-debt-strengthened":
        detail = class_trust_reweight_effect_reason or policy_debt_reason or reason
        return (
            f"Trust policy: verify first because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: verify first because fresh class caution is still heavy enough to matter."
        )
    if class_trust_reweight_effect == "policy-debt-softened":
        return "Trust policy: verify first for now, but class-level caution is fading rather than staying fully sticky."
    if class_trust_reweight_direction == "supporting-normalization":
        if policy == "act-with-review":
            return "Trust policy: act with review because fresh class evidence is still leaning healthier and supports the current stronger posture."
        return "Trust policy: verify first for now because class evidence is improving, but not strongly enough to move posture by itself yet."
    if class_trust_reweight_direction == "supporting-caution":
        return "Trust policy: verify first because recent class evidence is still caution-heavy enough to keep class trust conservative."
    if closure_forecast_reweight_effect == "confirm-support-strengthened":
        detail = closure_forecast_reweight_effect_reason or reason
        return (
            f"Trust policy: keep the weaker class posture for now because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: keep the weaker class posture for now because fresh pending-resolution evidence is strengthening the forecast without confirming it yet."
        )
    if closure_forecast_reweight_direction == "supporting-confirmation":
        return "Trust policy: keep the weaker class posture for now because fresh pending-resolution evidence is making the pending forecast healthier, but it has not confirmed yet."
    if closure_forecast_reweight_direction == "supporting-clearance":
        return "Trust policy: keep the weaker class posture because fresh pending debt is still pushing this class signal toward clearance or expiry risk."
    if closure_forecast_freshness_status == "stale":
        return "Trust policy: keep the weaker class posture because older closure-forecast momentum is being down-weighted."
    if closure_forecast_freshness_status == "mixed-age":
        return "Trust policy: keep the weaker class posture because closure-forecast memory is still useful, but part of it is aging."
    if class_decay_status == "normalization-decayed":
        detail = class_decay_reason or class_memory_freshness_reason or reason
        return (
            f"Trust policy: verify first because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: verify first because stale class memory pulled back class-level normalization."
        )
    if class_decay_status == "policy-debt-decayed":
        return "Trust policy: verify first for now, but earlier sticky class caution is starting to age out."
    if class_decay_status == "blocked":
        detail = (
            class_decay_reason
            or class_memory_freshness_reason
            or class_normalization_reason
            or policy_debt_reason
            or reason
        )
        return (
            f"Trust policy: verify first because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: verify first because local target noise still overrides class freshness."
        )
    if class_memory_freshness_status == "stale":
        detail = class_memory_freshness_reason or reason
        return (
            f"Trust policy: verify first because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: verify first because older class evidence is being down-weighted."
        )
    if class_memory_freshness_status == "mixed-age":
        return "Trust policy: verify first because class memory is still useful, but part of the class signal is aging out."
    if pending_debt_freshness_status == "stale":
        detail = pending_debt_freshness_reason or reason
        return (
            f"Trust policy: verify first because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: verify first because older pending-debt patterns are being down-weighted."
        )
    if pending_debt_freshness_status == "mixed-age":
        return "Trust policy: verify first because recent pending-transition evidence is still useful, but part of the pending-debt signal is aging out."
    if class_normalization_status == "applied":
        return "Trust policy: act with review because this class has repeatedly earned clean retirement and the current target can inherit a stronger posture."
    if class_normalization_status == "candidate":
        return "Trust policy: verify first for now because the class is improving, but the current target has not earned class-level normalization yet."
    if class_normalization_status == "blocked":
        detail = (
            class_normalization_reason
            or policy_debt_reason
            or exception_retirement_reason
            or trust_recovery_reason
            or exception_reason
            or reason
        )
        return (
            f"Trust policy: verify first because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: verify first because class-level normalization is still blocked."
        )
    if policy_debt_status == "class-debt":
        detail = policy_debt_reason or reason
        return (
            f"Trust policy: verify first because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: verify first because this class still carries sticky caution."
        )
    if policy_debt_status == "one-off-noise":
        detail = policy_debt_reason or reason
        return (
            f"Trust policy: verify first because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: verify first because this target is noisier than its broader class."
        )
    if exception_retirement_status == "retired":
        return "Trust policy: the earlier soft caution has now been formally retired, so the stronger live policy is back in place."
    if exception_retirement_status == "candidate":
        return "Trust policy: keep the current posture for now because the target is trending toward retirement, but it has not earned it yet."
    if exception_retirement_status == "blocked":
        detail = exception_retirement_reason or trust_recovery_reason or exception_reason or reason
        return (
            f"Trust policy: keep caution in place because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: keep caution in place because exception retirement is still blocked."
        )
    if trust_recovery_status == "earned":
        return "Trust policy: act with review because recent stability has earned this target back from verify-first."
    if trust_recovery_status == "candidate":
        return "Trust policy: verify first because the target is stabilizing, but it has not held steady long enough to earn stronger trust yet."
    if trust_recovery_status == "blocked":
        detail = trust_recovery_reason or exception_reason or reason
        return (
            f"Trust policy: verify first because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: verify first because trust recovery is still blocked."
        )
    if exception_pattern_status == "useful-caution":
        return "Trust policy: verify first because recent soft caution has been justified and still looks appropriate."
    if exception_pattern_status == "overcautious":
        if recovery_confidence_label == "high":
            return "Trust policy: verify first for now, but recovery confidence is high enough that the softer posture may soon retire."
        return "Trust policy: verify first for now, but recent evidence suggests the softer posture may be more cautious than necessary."
    if exception_status == "softened-for-noise":
        return "Trust policy: verify first because the target still matters, but recent trust noise warrants a verification step."
    if exception_status == "softened-for-flip-churn":
        return "Trust policy: verify first because recent recommendation flips mean the signal is still bouncing."
    if exception_status == "softened-for-reopen-risk":
        return "Trust policy: verify first because recent reopen behavior means closure evidence should be confirmed before overcommitting."
    if drift_status == "drifting":
        return "Trust policy: verify first because recent trust-policy behavior has been unstable."
    if policy == "act-now":
        return "Trust policy: act now because the current signal is strong and high-pressure."
    if policy == "act-with-review":
        return "Trust policy: act with review because the signal is strong enough to move, with light operator judgment."
    if policy == "verify-first":
        detail = exception_reason or reason
        return (
            f"Trust policy: verify first because {detail[0].lower() + detail[1:]}"
            if detail
            else "Trust policy: verify first because recent signal quality is softer."
        )
    return (
        f"Trust policy: monitor because {reason[0].lower() + reason[1:]}"
        if reason
        else "Trust policy: monitor because no strong closure move is supported yet."
    )


def _with_trust_policy_brief(
    summary: str,
    policy: str,
    exception_status: str,
    trust_recovery_status: str,
    exception_retirement_status: str,
    policy_debt_status: str,
    class_normalization_status: str,
    class_memory_freshness_status: str,
    class_decay_status: str,
    class_trust_reweight_direction: str,
    class_trust_reweight_effect: str,
    class_trust_momentum_status: str,
    class_reweight_stability_status: str,
    class_reweight_transition_status: str,
    class_transition_health_status: str,
    class_transition_resolution_status: str,
    pending_debt_freshness_status: str,
    closure_forecast_reweight_direction: str,
    closure_forecast_reweight_effect: str,
    closure_forecast_freshness_status: str,
    closure_forecast_decay_status: str,
    closure_forecast_refresh_recovery_status: str,
    closure_forecast_reacquisition_status: str,
    closure_forecast_momentum_status: str,
    closure_forecast_stability_status: str,
    closure_forecast_hysteresis_status: str,
) -> str:
    if not summary:
        return summary
    if closure_forecast_reacquisition_status == "reacquired-confirmation":
        return f"{summary} Trust policy: stronger confirmation forecasting was safely re-earned."
    if closure_forecast_reacquisition_status == "reacquired-clearance":
        return f"{summary} Trust policy: stronger clearance forecasting was safely re-earned."
    if closure_forecast_reacquisition_status == "pending-confirmation-reacquisition":
        return f"{summary} Trust policy: confirmation-side recovery is visible, but stronger carry-forward has not been fully re-earned yet."
    if closure_forecast_reacquisition_status == "pending-clearance-reacquisition":
        return f"{summary} Trust policy: clearance-side recovery is visible, but stronger carry-forward has not been fully re-earned yet."
    if closure_forecast_reacquisition_status == "blocked":
        return f"{summary} Trust policy: local target instability is still preventing positive confirmation-side reacquisition."
    if closure_forecast_refresh_recovery_status == "recovering-confirmation":
        return f"{summary} Trust policy: fresh confirmation-side forecast evidence is returning, but it has not fully re-earned stronger carry-forward yet."
    if closure_forecast_refresh_recovery_status == "recovering-clearance":
        return f"{summary} Trust policy: fresh clearance-side forecast evidence is returning, but it has not fully re-earned stronger carry-forward yet."
    if closure_forecast_refresh_recovery_status == "reacquiring-confirmation":
        return f"{summary} Trust policy: fresh confirmation-side support is getting strong enough to re-earn stronger carry-forward soon."
    if closure_forecast_refresh_recovery_status == "reacquiring-clearance":
        return f"{summary} Trust policy: fresh clearance-side pressure is getting strong enough to re-earn stronger carry-forward soon."
    if closure_forecast_refresh_recovery_status == "reversing":
        return f"{summary} Trust policy: the fresh recovery attempt is changing direction, so stronger carry-forward stays softened."
    if closure_forecast_refresh_recovery_status == "blocked":
        return f"{summary} Trust policy: local target instability is still preventing positive confirmation-side reacquisition."
    if class_transition_resolution_status == "confirmed":
        return f"{summary} Trust policy: the earlier pending class signal finally confirmed."
    if class_transition_resolution_status == "cleared":
        return f"{summary} Trust policy: the earlier pending class signal faded before confirmation and was cleared."
    if class_transition_resolution_status == "expired":
        return f"{summary} Trust policy: the earlier pending class signal aged out and no longer changes posture."
    if class_transition_resolution_status == "blocked":
        return f"{summary} Trust policy: local target instability is blocking a pending class transition."
    if class_transition_health_status == "stalled":
        return f"{summary} Trust policy: the pending class signal has stalled and should stay visible but unconfirmed."
    if class_transition_health_status == "holding":
        return f"{summary} Trust policy: the pending class signal is still visible, but it is no longer getting stronger."
    if class_transition_health_status == "building":
        return f"{summary} Trust policy: the pending class signal is still building and may confirm soon."
    if class_transition_health_status == "expired":
        return f"{summary} Trust policy: the earlier pending class signal aged out."
    if class_transition_health_status == "blocked":
        return f"{summary} Trust policy: local target instability is still blocking a pending class transition."
    if closure_forecast_reweight_effect == "clear-risk-strengthened":
        return f"{summary} Trust policy: fresh pending debt is pushing the live pending signal toward clearance or expiry risk."
    if closure_forecast_reweight_effect == "confirm-support-strengthened":
        return f"{summary} Trust policy: fresh pending-resolution evidence is strengthening the forecast, but the pending class signal still has to confirm."
    if closure_forecast_reweight_effect == "confirm-support-softened":
        return f"{summary} Trust policy: older pending-transition evidence is softening how much trust the live pending forecast deserves."
    if closure_forecast_reweight_effect == "clear-risk-softened":
        return f"{summary} Trust policy: older pending-debt patterns are fading instead of dominating the forecast."
    if closure_forecast_decay_status == "confirmation-decayed":
        return f"{summary} Trust policy: stronger confirmation carry-forward is aging out."
    if closure_forecast_decay_status == "clearance-decayed":
        return f"{summary} Trust policy: stronger clearance carry-forward is aging out."
    if closure_forecast_decay_status == "blocked":
        return f"{summary} Trust policy: local target instability still overrides closure-forecast freshness."
    if closure_forecast_hysteresis_status == "confirmed-confirmation":
        return f"{summary} Trust policy: the stronger confirmation forecast is now backed by persistent class follow-through."
    if closure_forecast_hysteresis_status == "confirmed-clearance":
        return f"{summary} Trust policy: the stronger clearance forecast is now backed by persistent unresolved pending debt."
    if closure_forecast_hysteresis_status == "pending-confirmation":
        return f"{summary} Trust policy: the healthier closure forecast is visible, but it has not stayed persistent enough to trust fully."
    if closure_forecast_hysteresis_status == "pending-clearance":
        return f"{summary} Trust policy: the more cautious closure forecast is visible, but it has not stayed persistent enough to clear early."
    if closure_forecast_hysteresis_status == "blocked":
        return f"{summary} Trust policy: local target instability is blocking positive closure-forecast strengthening."
    if class_reweight_transition_status == "confirmed-support":
        return f"{summary} Trust policy: broader normalization is now confirmed by sustained class support."
    if class_reweight_transition_status == "confirmed-caution":
        return f"{summary} Trust policy: broader class caution is now confirmed by sustained caution-heavy evidence."
    if class_reweight_transition_status == "pending-support":
        return f"{summary} Trust policy: healthier class support is visible, but it has not persisted long enough to confirm yet."
    if class_reweight_transition_status == "pending-caution":
        return f"{summary} Trust policy: caution-heavy class evidence is visible, but it has not persisted long enough to confirm yet."
    if class_reweight_transition_status == "blocked":
        return f"{summary} Trust policy: positive class strengthening is blocked by local target noise."
    if class_reweight_stability_status == "oscillating":
        return f"{summary} Trust policy: class guidance is bouncing too much to strengthen safely right now."
    if class_trust_momentum_status == "reversing":
        return f"{summary} Trust policy: recent class evidence is changing direction, so earlier class guidance is softening."
    if class_trust_momentum_status == "building":
        return f"{summary} Trust policy: class evidence is trending in one direction, but it has not held long enough to lock in."
    if class_trust_reweight_effect == "normalization-boosted":
        return f"{summary} Trust policy: fresh class support strengthened class guidance."
    if class_trust_reweight_effect == "normalization-softened":
        return (
            f"{summary} Trust policy: class normalization stayed visible, but its support weakened."
        )
    if class_trust_reweight_effect == "policy-debt-strengthened":
        return f"{summary} Trust policy: fresh class caution is still strong enough to matter."
    if class_trust_reweight_effect == "policy-debt-softened":
        return f"{summary} Trust policy: class-level caution is fading instead of staying fully sticky."
    if class_trust_reweight_direction == "supporting-normalization":
        return f"{summary} Trust policy: class evidence is leaning healthier, but not strongly enough to move posture by itself yet."
    if class_trust_reweight_direction == "supporting-caution":
        return f"{summary} Trust policy: recent class evidence is still caution-heavy."
    if closure_forecast_reweight_direction == "supporting-confirmation":
        return f"{summary} Trust policy: fresh pending-resolution evidence is making the live pending forecast look healthier."
    if closure_forecast_reweight_direction == "supporting-clearance":
        return f"{summary} Trust policy: fresh pending debt is making the live pending forecast more cautious."
    if closure_forecast_freshness_status == "stale":
        return f"{summary} Trust policy: older closure-forecast momentum is being down-weighted."
    if closure_forecast_freshness_status == "mixed-age":
        return f"{summary} Trust policy: closure-forecast memory is still useful, but part of it is aging."
    if closure_forecast_stability_status == "oscillating":
        return f"{summary} Trust policy: closure-forecast guidance is bouncing too much to strengthen safely right now."
    if closure_forecast_momentum_status == "reversing":
        return f"{summary} Trust policy: recent pending-resolution evidence is changing direction, so forecast strength is softening."
    if closure_forecast_momentum_status == "building":
        return f"{summary} Trust policy: the closure forecast is trending in one direction, but it has not held long enough to lock in."
    if class_decay_status == "normalization-decayed":
        return f"{summary} Trust policy: stale class memory pulled back class-level normalization."
    if class_decay_status == "policy-debt-decayed":
        return f"{summary} Trust policy: earlier sticky class caution is aging out."
    if class_decay_status == "blocked":
        return f"{summary} Trust policy: local target noise still overrides healthier class memory."
    if class_memory_freshness_status == "stale":
        return f"{summary} Trust policy: older class evidence is being down-weighted."
    if class_memory_freshness_status == "mixed-age":
        return f"{summary} Trust policy: class memory is still useful, but part of it is aging."
    if pending_debt_freshness_status == "stale":
        return f"{summary} Trust policy: older pending-debt patterns are being down-weighted."
    if pending_debt_freshness_status == "mixed-age":
        return f"{summary} Trust policy: recent pending-transition evidence is still useful, but part of it is aging."
    if class_normalization_status == "applied":
        return f"{summary} Trust policy: class-level normalization applied."
    if class_normalization_status == "candidate":
        return f"{summary} Trust policy: class-level normalization is trending, but not earned yet."
    if class_normalization_status == "blocked":
        return f"{summary} Trust policy: class-level normalization is blocked."
    if policy_debt_status == "class-debt":
        return f"{summary} Trust policy: class-level caution still looks sticky."
    if policy_debt_status == "one-off-noise":
        return f"{summary} Trust policy: this target still looks noisier than its broader class."
    if exception_retirement_status == "retired":
        return f"{summary} Trust policy: earlier caution retired."
    if exception_retirement_status == "candidate":
        return f"{summary} Trust policy: exception retirement is in progress, but not earned yet."
    if exception_retirement_status == "blocked":
        return f"{summary} Trust policy: exception retirement is blocked."
    if trust_recovery_status == "earned":
        return f"{summary} Trust policy: act with review because recent stability has earned stronger trust again."
    if trust_recovery_status == "candidate":
        return f"{summary} Trust policy: verify first because the target is stabilizing, but it has not earned stronger trust yet."
    if trust_recovery_status == "blocked":
        return f"{summary} Trust policy: verify first because trust recovery is still blocked."
    if exception_status == "softened-for-noise":
        return f"{summary} Trust policy: verify first because recent trust noise softened the recommendation."
    if exception_status == "softened-for-flip-churn":
        return f"{summary} Trust policy: verify first because recent recommendation flips softened the recommendation."
    if exception_status == "softened-for-reopen-risk":
        return f"{summary} Trust policy: verify first because recent reopen risk softened the recommendation."
    if policy == "act-now":
        return f"{summary} Trust policy: act now."
    if policy == "act-with-review":
        return f"{summary} Trust policy: act with review."
    if policy == "verify-first":
        return f"{summary} Trust policy: verify first."
    return f"{summary} Trust policy: monitor."


def _trust_exception_note(resolution_trend: dict) -> str:
    status = resolution_trend.get("primary_target_exception_status", "none")
    reason = resolution_trend.get("primary_target_exception_reason", "")
    if status in {None, "", "none"}:
        return ""
    return f"Trust policy exception: {status} — {reason}"


def _exception_pattern_note(resolution_trend: dict) -> str:
    status = resolution_trend.get("primary_target_exception_pattern_status", "none")
    reason = resolution_trend.get("primary_target_exception_pattern_reason", "")
    if status in {None, "", "none"}:
        return ""
    return f"Exception pattern learning: {status} — {reason}".strip()


def _trust_recovery_note(resolution_trend: dict) -> str:
    status = resolution_trend.get("primary_target_trust_recovery_status", "none")
    reason = resolution_trend.get("primary_target_trust_recovery_reason", "")
    if status in {None, "", "none"}:
        return ""
    return f"Trust recovery: {status} — {reason}".strip()


def _recovery_confidence_note(resolution_trend: dict) -> str:
    label = resolution_trend.get("primary_target_recovery_confidence_label", "")
    if not label:
        return ""
    score = resolution_trend.get("primary_target_recovery_confidence_score", 0.0)
    summary = resolution_trend.get("recovery_confidence_summary", "")
    return f"Recovery confidence: {label} ({score:.2f}) — {summary}".strip()


def _exception_retirement_note(resolution_trend: dict) -> str:
    status = resolution_trend.get("primary_target_exception_retirement_status", "none")
    reason = resolution_trend.get("primary_target_exception_retirement_reason", "")
    if status in {None, "", "none"}:
        return ""
    return f"Exception retirement: {status} — {reason}".strip()


def _policy_debt_note(resolution_trend: dict) -> str:
    status = resolution_trend.get("primary_target_policy_debt_status", "none")
    reason = resolution_trend.get("primary_target_policy_debt_reason", "")
    if status in {None, "", "none"}:
        return ""
    return f"Policy debt cleanup: {status} — {reason}".strip()


def _class_normalization_note(resolution_trend: dict) -> str:
    status = resolution_trend.get("primary_target_class_normalization_status", "none")
    reason = resolution_trend.get("primary_target_class_normalization_reason", "")
    if status in {None, "", "none"}:
        return ""
    return f"Class-level trust normalization: {status} — {reason}".strip()


def _class_memory_note(resolution_trend: dict) -> str:
    status = resolution_trend.get(
        "primary_target_class_memory_freshness_status", "insufficient-data"
    )
    reason = resolution_trend.get("primary_target_class_memory_freshness_reason", "")
    if not status:
        return ""
    return f"Class memory freshness: {status} — {reason}".strip()


def _class_decay_note(resolution_trend: dict) -> str:
    status = resolution_trend.get("primary_target_class_decay_status", "none")
    reason = resolution_trend.get("primary_target_class_decay_reason", "")
    if status in {None, "", "none"}:
        return ""
    return f"Trust decay controls: {status} — {reason}".strip()


def _class_reweighting_note(resolution_trend: dict) -> str:
    direction = resolution_trend.get("primary_target_class_trust_reweight_direction", "neutral")
    summary = resolution_trend.get("class_reweighting_summary", "")
    if direction in {None, "", "neutral"} and not summary:
        return ""
    return f"Class trust reweighting: {direction} — {summary}".strip()


def _class_momentum_note(resolution_trend: dict) -> str:
    status = resolution_trend.get("primary_target_class_trust_momentum_status", "insufficient-data")
    summary = resolution_trend.get("class_momentum_summary", "")
    if status in {None, ""} and not summary:
        return ""
    return f"Class trust momentum: {status} — {summary}".strip()


def _class_reweight_stability_note(resolution_trend: dict) -> str:
    status = resolution_trend.get("primary_target_class_reweight_stability_status", "watch")
    summary = resolution_trend.get("class_reweight_stability_summary", "")
    if status in {None, ""} and not summary:
        return ""
    return f"Reweighting stability: {status} — {summary}".strip()


def _class_transition_health_note(resolution_trend: dict) -> str:
    status = resolution_trend.get("primary_target_class_transition_health_status", "none")
    summary = resolution_trend.get("class_transition_health_summary", "")
    if status in {None, "", "none"} and not summary:
        return ""
    return f"Class transition health: {status} — {summary}".strip()


def _class_transition_resolution_note(resolution_trend: dict) -> str:
    status = resolution_trend.get("primary_target_class_transition_resolution_status", "none")
    summary = resolution_trend.get("class_transition_resolution_summary", "")
    if status in {None, "", "none"} and not summary:
        return ""
    return f"Pending transition resolution: {status} — {summary}".strip()


def _transition_closure_confidence_note(resolution_trend: dict) -> str:
    label = resolution_trend.get("primary_target_transition_closure_confidence_label", "")
    if not label:
        return ""
    score = resolution_trend.get("primary_target_transition_closure_confidence_score", 0.0)
    summary = resolution_trend.get("transition_closure_confidence_summary", "")
    return f"Transition closure confidence: {label} ({score:.2f}) — {summary}".strip()


def _class_pending_debt_note(resolution_trend: dict) -> str:
    status = resolution_trend.get("primary_target_class_pending_debt_status", "none")
    summary = resolution_trend.get("class_pending_debt_summary", "")
    if status in {None, "", "none"} and not summary:
        return ""
    return f"Class pending debt audit: {status} — {summary}".strip()


def _pending_debt_freshness_note(resolution_trend: dict) -> str:
    status = resolution_trend.get(
        "primary_target_pending_debt_freshness_status", "insufficient-data"
    )
    summary = resolution_trend.get("pending_debt_freshness_summary", "")
    if status in {None, ""} and not summary:
        return ""
    return f"Pending debt freshness: {status} — {summary}".strip()


def _closure_forecast_reweighting_note(resolution_trend: dict) -> str:
    direction = resolution_trend.get(
        "primary_target_closure_forecast_reweight_direction", "neutral"
    )
    summary = resolution_trend.get("closure_forecast_reweighting_summary", "")
    if direction in {None, ""} and not summary:
        return ""
    return f"Closure forecast reweighting: {direction} — {summary}".strip()


def _closure_forecast_freshness_note(resolution_trend: dict) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_freshness_status", "insufficient-data"
    )
    summary = resolution_trend.get("closure_forecast_freshness_summary", "")
    if status in {None, ""} and not summary:
        return ""
    return f"Closure forecast freshness: {status} — {summary}".strip()


def _closure_forecast_momentum_note(resolution_trend: dict) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_momentum_status", "insufficient-data"
    )
    summary = resolution_trend.get("closure_forecast_momentum_summary", "")
    if status in {None, ""} and not summary:
        return ""
    return f"Closure forecast momentum: {status} — {summary}".strip()


def _closure_forecast_decay_note(resolution_trend: dict) -> str:
    status = resolution_trend.get("primary_target_closure_forecast_decay_status", "none")
    summary = resolution_trend.get("closure_forecast_decay_summary", "")
    if status in {None, "", "none"} and not summary:
        return ""
    return f"Hysteresis decay controls: {status} — {summary}".strip()


def _closure_forecast_refresh_recovery_note(resolution_trend: dict) -> str:
    status = resolution_trend.get("primary_target_closure_forecast_refresh_recovery_status", "none")
    summary = resolution_trend.get("closure_forecast_refresh_recovery_summary", "")
    if status in {None, "", "none"} and not summary:
        return ""
    return f"Closure forecast refresh recovery: {status} — {summary}".strip()


def _closure_forecast_reacquisition_note(resolution_trend: dict) -> str:
    status = resolution_trend.get("primary_target_closure_forecast_reacquisition_status", "none")
    summary = resolution_trend.get("closure_forecast_reacquisition_summary", "")
    if status in {None, "", "none"} and not summary:
        return ""
    return f"Reacquisition controls: {status} — {summary}".strip()


def _closure_forecast_reacquisition_persistence_note(resolution_trend: dict) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reacquisition_persistence_status", "none"
    )
    summary = resolution_trend.get("closure_forecast_reacquisition_persistence_summary", "")
    if status in {None, "", "none"} and not summary:
        return ""
    return f"Reacquisition persistence: {status} — {summary}".strip()


def _closure_forecast_recovery_churn_note(resolution_trend: dict) -> str:
    status = resolution_trend.get("primary_target_closure_forecast_recovery_churn_status", "none")
    summary = resolution_trend.get("closure_forecast_recovery_churn_summary", "")
    if status in {None, "", "none"} and not summary:
        return ""
    return f"Recovery churn controls: {status} — {summary}".strip()


def _closure_forecast_reset_refresh_recovery_note(resolution_trend: dict) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_refresh_recovery_status", "none"
    )
    summary = resolution_trend.get("closure_forecast_reset_refresh_recovery_summary", "")
    if status in {None, "", "none"} and not summary:
        return ""
    return f"Reset refresh recovery: {status} — {summary}".strip()


def _closure_forecast_reset_reentry_note(resolution_trend: dict) -> str:
    status = resolution_trend.get("primary_target_closure_forecast_reset_reentry_status", "none")
    summary = resolution_trend.get("closure_forecast_reset_reentry_summary", "")
    if status in {None, "", "none"} and not summary:
        return ""
    return f"Reset re-entry controls: {status} — {summary}".strip()


def _closure_forecast_reset_reentry_persistence_note(resolution_trend: dict) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_persistence_status",
        "none",
    )
    summary = resolution_trend.get("closure_forecast_reset_reentry_persistence_summary", "")
    if status in {None, "", "none"} and not summary:
        return ""
    return f"Reset re-entry persistence: {status} — {summary}".strip()


def _closure_forecast_reset_reentry_churn_note(resolution_trend: dict) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_churn_status",
        "none",
    )
    summary = resolution_trend.get("closure_forecast_reset_reentry_churn_summary", "")
    if status in {None, "", "none"} and not summary:
        return ""
    return f"Reset re-entry churn controls: {status} — {summary}".strip()


def _closure_forecast_reset_reentry_freshness_note(resolution_trend: dict) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_freshness_status",
        "insufficient-data",
    )
    summary = resolution_trend.get("closure_forecast_reset_reentry_freshness_summary", "")
    if status in {None, "", "none"} and not summary:
        return ""
    return f"Reset re-entry freshness: {status} — {summary}".strip()


def _closure_forecast_reset_reentry_reset_note(resolution_trend: dict) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_reset_status",
        "none",
    )
    summary = resolution_trend.get("closure_forecast_reset_reentry_reset_summary", "")
    if status in {None, "", "none"} and not summary:
        return ""
    return f"Reset re-entry reset controls: {status} — {summary}".strip()


def _closure_forecast_reset_reentry_refresh_recovery_note(resolution_trend: dict) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_refresh_recovery_status",
        "none",
    )
    summary = resolution_trend.get("closure_forecast_reset_reentry_refresh_recovery_summary", "")
    if status in {None, "", "none"} and not summary:
        return ""
    return f"Reset re-entry refresh recovery: {status} — {summary}".strip()


def _closure_forecast_reset_reentry_rebuild_note(resolution_trend: dict) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_status",
        "none",
    )
    summary = resolution_trend.get("closure_forecast_reset_reentry_rebuild_summary", "")
    if status in {None, "", "none"} and not summary:
        return ""
    return f"Reset re-entry rebuild controls: {status} — {summary}".strip()


def _closure_forecast_reset_reentry_rebuild_freshness_note(resolution_trend: dict) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_freshness_status",
        "insufficient-data",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_freshness_summary",
        "",
    )
    if status in {None, "", "none", "insufficient-data"} and not summary:
        return ""
    return f"Reset re-entry rebuild freshness: {status} — {summary}".strip()


def _closure_forecast_reset_reentry_rebuild_reset_note(resolution_trend: dict) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reset_status",
        "none",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_reset_summary",
        "",
    )
    if status in {None, "", "none"} and not summary:
        return ""
    return f"Reset re-entry rebuild reset controls: {status} — {summary}".strip()


def _closure_forecast_reset_reentry_rebuild_refresh_recovery_note(
    resolution_trend: dict,
) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_refresh_recovery_status",
        "none",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_refresh_recovery_summary",
        "",
    )
    if status in {None, "", "none"} and not summary:
        return ""
    return f"Reset re-entry rebuild refresh recovery: {status} — {summary}".strip()


def _closure_forecast_reset_reentry_rebuild_reentry_note(resolution_trend: dict) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_status",
        "none",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_reentry_summary",
        "",
    )
    if status in {None, "", "none"} and not summary:
        return ""
    return f"Reset re-entry rebuild re-entry controls: {status} — {summary}".strip()


def _closure_forecast_reset_reentry_rebuild_reentry_persistence_note(
    resolution_trend: dict,
) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_status",
        "none",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_reentry_persistence_summary",
        "",
    )
    if status in {None, "", "none"} and not summary:
        return ""
    return f"Reset re-entry rebuild re-entry persistence: {status} — {summary}".strip()


def _closure_forecast_reset_reentry_rebuild_reentry_churn_note(
    resolution_trend: dict,
) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_status",
        "none",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_reentry_churn_summary",
        "",
    )
    if status in {None, "", "none"} and not summary:
        return ""
    return f"Reset re-entry rebuild re-entry churn controls: {status} — {summary}".strip()


def _closure_forecast_reset_reentry_rebuild_reentry_freshness_note(
    resolution_trend: dict,
) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_freshness_status",
        "insufficient-data",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_reentry_freshness_summary",
        "",
    )
    if status in {None, "", "none", "insufficient-data"} and not summary:
        return ""
    return f"Reset re-entry rebuild re-entry freshness: {status} — {summary}".strip()


def _closure_forecast_reset_reentry_rebuild_reentry_reset_note(
    resolution_trend: dict,
) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_reset_status",
        "none",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_reentry_reset_summary",
        "",
    )
    if status in {None, "", "none"} and not summary:
        return ""
    return f"Reset re-entry rebuild re-entry reset controls: {status} — {summary}".strip()


def _closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_note(
    resolution_trend: dict,
) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status",
        "none",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_summary",
        "",
    )
    if status in {None, "", "none"} and not summary:
        return ""
    return (f"Reset re-entry rebuild re-entry refresh recovery: {status} — {summary}").strip()


def _closure_forecast_reset_reentry_rebuild_reentry_restore_note(
    resolution_trend: dict,
) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_status",
        "none",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_summary",
        "",
    )
    if status in {None, "", "none"} and not summary:
        return ""
    return (f"Reset re-entry rebuild re-entry restore controls: {status} — {summary}").strip()


def _closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_note(
    resolution_trend: dict,
) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_status",
        "none",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_summary",
        "",
    )
    if status in {None, "", "none"} and not summary:
        return ""
    return (f"Reset re-entry rebuild re-entry restore persistence: {status} — {summary}").strip()


def _closure_forecast_reset_reentry_rebuild_reentry_restore_churn_note(
    resolution_trend: dict,
) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_churn_status",
        "none",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_churn_summary",
        "",
    )
    if status in {None, "", "none"} and not summary:
        return ""
    return (f"Reset re-entry rebuild re-entry restore churn controls: {status} — {summary}").strip()


def _closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_note(
    resolution_trend: dict,
) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_status",
        "insufficient-data",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_summary",
        "",
    )
    if status in {None, "", "none", "insufficient-data"} and not summary:
        return ""
    return (f"Reset re-entry rebuild re-entry restore freshness: {status} — {summary}").strip()


def _closure_forecast_reset_reentry_rebuild_reentry_restore_reset_note(
    resolution_trend: dict,
) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reset_status",
        "none",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_reset_summary",
        "",
    )
    if status in {None, "", "none"} and not summary:
        return ""
    return (f"Reset re-entry rebuild re-entry restore reset controls: {status} — {summary}").strip()


def _closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_note(
    resolution_trend: dict,
) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_status",
        "none",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_summary",
        "",
    )
    if status in {None, "", "none"} and not summary:
        return ""
    return (
        f"Reset re-entry rebuild re-entry restore refresh recovery: {status} — {summary}"
    ).strip()


def _closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_note(
    resolution_trend: dict,
) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status",
        "none",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_summary",
        "",
    )
    if status in {None, "", "none"} and not summary:
        return ""
    return (
        f"Reset re-entry rebuild re-entry restore re-restore controls: {status} — {summary}"
    ).strip()


def _closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_note(
    resolution_trend: dict,
) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_status",
        "none",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_summary",
        "",
    )
    if status in {None, "", "none"} and not summary:
        return ""
    return (
        f"Reset re-entry rebuild re-entry restore re-restore persistence: {status} — {summary}"
    ).strip()


def _closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_note(
    resolution_trend: dict,
) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_status",
        "none",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_summary",
        "",
    )
    if status in {None, "", "none"} and not summary:
        return ""
    return (
        f"Reset re-entry rebuild re-entry restore re-restore churn controls: {status} — {summary}"
    ).strip()


def _closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_note(
    resolution_trend: dict,
) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status",
        "insufficient-data",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_summary",
        "",
    )
    if status in {None, "", "insufficient-data"} and not summary:
        return ""
    return (
        f"Reset re-entry rebuild re-entry restore re-restore freshness: {status} — {summary}"
    ).strip()


def _closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_note(
    resolution_trend: dict,
) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_status",
        "none",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_summary",
        "",
    )
    if status in {None, "", "none"} and not summary:
        return ""
    return (
        f"Reset re-entry rebuild re-entry restore re-restore reset controls: {status} — {summary}"
    ).strip()


def _closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_note(
    resolution_trend: dict,
) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_status",
        "none",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_summary",
        "",
    )
    if status in {None, "", "none"} and not summary:
        return ""
    return (
        f"Reset re-entry rebuild re-entry restore re-restore refresh recovery: {status} — {summary}"
    ).strip()


def _closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_note(
    resolution_trend: dict,
) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status",
        "none",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_summary",
        "",
    )
    if status in {None, "", "none"} and not summary:
        return ""
    return (
        f"Reset re-entry rebuild re-entry restore re-re-restore controls: {status} — {summary}"
    ).strip()


def _closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_note(
    resolution_trend: dict,
) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status",
        "none",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_summary",
        "",
    )
    if status in {None, "", "none"} and not summary:
        return ""
    return (
        f"Reset re-entry rebuild re-entry restore re-re-restore persistence: {status} — {summary}"
    ).strip()


def _closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_note(
    resolution_trend: dict,
) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status",
        "none",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_summary",
        "",
    )
    if status in {None, "", "none"} and not summary:
        return ""
    return (
        f"Reset re-entry rebuild re-entry restore re-re-restore churn controls: {status} — {summary}"
    ).strip()


def _closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_note(
    resolution_trend: dict,
) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status",
        "insufficient-data",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_summary",
        "",
    )
    if status in {None, "", "insufficient-data"} and not summary:
        return ""
    return (
        f"Reset re-entry rebuild re-entry restore re-re-restore freshness: {status} — {summary}"
    ).strip()


def _closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_note(
    resolution_trend: dict,
) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status",
        "none",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_summary",
        "",
    )
    if status in {None, "", "none"} and not summary:
        return ""
    return (
        f"Reset re-entry rebuild re-entry restore re-re-restore reset controls: {status} — {summary}"
    ).strip()


def _closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_note(
    resolution_trend: dict,
) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status",
        "none",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_summary",
        "",
    )
    if status in {None, "", "none"} and not summary:
        return ""
    return (
        f"Reset re-entry rebuild re-entry restore re-re-restore refresh recovery: {status} — {summary}"
    ).strip()


def _closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_note(
    resolution_trend: dict,
) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status",
        "none",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_summary",
        "",
    )
    if status in {None, "", "none"} and not summary:
        return ""
    return (
        f"Reset re-entry rebuild re-entry restore re-re-re-restore controls: {status} — {summary}"
    ).strip()


def _closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_note(
    resolution_trend: dict,
) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status",
        "none",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_summary",
        "",
    )
    if status in {None, "", "none"} and not summary:
        return ""
    return (
        f"Reset re-entry rebuild re-entry restore re-re-re-restore persistence: {status} — {summary}"
    ).strip()


def _closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_note(
    resolution_trend: dict,
) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status",
        "none",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_summary",
        "",
    )
    if status in {None, "", "none"} and not summary:
        return ""
    return (
        f"Reset re-entry rebuild re-entry restore re-re-re-restore churn controls: {status} — {summary}"
    ).strip()


def _closure_forecast_reset_reentry_rebuild_persistence_note(resolution_trend: dict) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_persistence_status",
        "none",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_persistence_summary",
        "",
    )
    if status in {None, "", "none"} and not summary:
        return ""
    return f"Reset re-entry rebuild persistence: {status} — {summary}".strip()


def _closure_forecast_reset_reentry_rebuild_churn_note(resolution_trend: dict) -> str:
    status = resolution_trend.get(
        "primary_target_closure_forecast_reset_reentry_rebuild_churn_status",
        "none",
    )
    summary = resolution_trend.get(
        "closure_forecast_reset_reentry_rebuild_churn_summary",
        "",
    )
    if status in {None, "", "none"} and not summary:
        return ""
    return f"Reset re-entry rebuild churn controls: {status} — {summary}".strip()


def _closure_forecast_hysteresis_note(resolution_trend: dict) -> str:
    status = resolution_trend.get("primary_target_closure_forecast_hysteresis_status", "none")
    summary = resolution_trend.get("closure_forecast_hysteresis_summary", "")
    if status in {None, "", "none"} and not summary:
        return ""
    return f"Closure forecast hysteresis: {status} — {summary}".strip()


def _recommendation_drift_note(resolution_trend: dict) -> str:
    status = resolution_trend.get("recommendation_drift_status", "stable")
    summary = resolution_trend.get("recommendation_drift_summary", "")
    if status == "stable" and not summary:
        return ""
    return f"Recommendation drift: {status} — {summary}".strip()
