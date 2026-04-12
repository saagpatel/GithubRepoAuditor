from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.baseline_context import build_watch_guidance
from src.governance_activation import build_governance_summary
from src.recurring_review import build_review_bundle
from src.warehouse import (
    load_operator_calibration_history,
    load_operator_state_history,
    load_recent_operator_changes,
    load_recent_operator_evidence,
)

LANE_ORDER = {"blocked": 0, "urgent": 1, "ready": 2, "deferred": 3}
LANE_LABELS = {
    "blocked": "Blocked",
    "urgent": "Needs Attention Now",
    "ready": "Ready for Manual Action",
    "deferred": "Safe to Defer",
}
QUIET_HANDOFF = "No new blocking or urgent drift is surfaced in the latest operator snapshot."
ATTENTION_LANES = {"blocked", "urgent"}
HISTORY_WINDOW_RUNS = 10
CALIBRATION_WINDOW_RUNS = 20
VALIDATION_WINDOW_RUNS = 2
TRUST_RECOVERY_WINDOW_RUNS = 3
EXCEPTION_RETIREMENT_WINDOW_RUNS = 4
CLASS_NORMALIZATION_WINDOW_RUNS = 4
CLASS_MEMORY_FRESHNESS_WINDOW_RUNS = 4
CLASS_REWEIGHTING_WINDOW_RUNS = 4
CLASS_TRANSITION_WINDOW_RUNS = 4
CLASS_PENDING_RESOLUTION_WINDOW_RUNS = 4
CLASS_TRANSITION_CLOSURE_WINDOW_RUNS = 4
CLASS_PENDING_DEBT_WINDOW_RUNS = HISTORY_WINDOW_RUNS
PENDING_DEBT_FRESHNESS_WINDOW_RUNS = 4
CLASS_CLOSURE_FORECAST_REWEIGHTING_WINDOW_RUNS = 4
CLASS_CLOSURE_FORECAST_TRANSITION_WINDOW_RUNS = 4
CLASS_CLOSURE_FORECAST_FRESHNESS_WINDOW_RUNS = 4
CLASS_CLOSURE_FORECAST_REFRESH_WINDOW_RUNS = 4
CLASS_REACQUISITION_PERSISTENCE_WINDOW_RUNS = 4
CLASS_REACQUISITION_FRESHNESS_WINDOW_RUNS = 4
CLASS_RESET_REENTRY_WINDOW_RUNS = 4
CLASS_RESET_REENTRY_PERSISTENCE_WINDOW_RUNS = 4
CLASS_RESET_REENTRY_FRESHNESS_WINDOW_RUNS = 4
CLASS_RESET_REENTRY_REFRESH_REBUILD_WINDOW_RUNS = 4
CLASS_RESET_REENTRY_REBUILD_PERSISTENCE_WINDOW_RUNS = 4
CLASS_RESET_REENTRY_REBUILD_FRESHNESS_WINDOW_RUNS = 4
CLASS_MEMORY_RECENCY_WEIGHTS = (1.0, 1.0, 0.7, 0.7, 0.4, 0.4, 0.4, 0.2, 0.2, 0.2)
GENERIC_RECOMMENDATION_PHRASES = (
    "continue the normal audit/control-center loop",
    "continue the normal operator loop",
    "review the latest state",
    "inspect the latest changes and decide on next action",
    "monitor future audits",
    "open the repo queue details",
)
GENERIC_MONITOR_PHRASES = ("keep the operator loop light", "keep the operator loop lightweight")
GENERIC_BASELINE_PHRASES = (
    "run the next full audit to refresh the baseline",
    "refresh the baseline before relying on incremental results",
)


def normalize_review_state(
    report_data: dict,
    *,
    output_dir: Path,
    diff_data: dict | None = None,
    portfolio_profile: str = "default",
    collection_name: str | None = None,
) -> dict:
    """Return report data with normalized review fields populated when possible."""
    data = dict(report_data)
    if _has_normalized_review_state(data):
        data["review_targets"] = [_normalize_review_target(item) for item in data.get("review_targets") or []]
        data["review_history"] = [_normalize_review_history_item(item) for item in data.get("review_history") or []]
        data["review_summary"] = _normalize_review_summary(data.get("review_summary") or {})
        return data
    try:
        bundle = build_review_bundle(
            data,
            output_dir=output_dir,
            diff_data=diff_data,
            materiality="standard",
            portfolio_profile=portfolio_profile,
            collection_name=collection_name,
            watch_state=data.get("watch_state") or {},
            emit_when_quiet=False,
        )
    except Exception:
        bundle = {
            "review_summary": {
                "status": "unavailable",
                "safe_to_defer": False,
                "material_change_count": 0,
                "reason": "Review state could not be reconstructed from the latest report.",
            },
            "review_alerts": [],
            "material_changes": [],
            "review_targets": [],
            "review_history": [],
            "watch_state": data.get("watch_state") or {},
        }
    bundle["review_targets"] = [_normalize_review_target(item) for item in bundle.get("review_targets") or []]
    bundle["review_history"] = [_normalize_review_history_item(item) for item in bundle.get("review_history") or []]
    bundle["review_summary"] = _normalize_review_summary(bundle.get("review_summary") or {})
    data.update(bundle)
    return data


def build_operator_snapshot(
    report_data: dict,
    *,
    output_dir: Path,
    triage_view: str = "all",
) -> dict:
    queue: list[dict] = []
    preflight = report_data.get("preflight_summary") or {}
    review_summary = report_data.get("review_summary") or {}
    review_targets = report_data.get("review_targets") or []
    managed_state_drift = report_data.get("managed_state_drift") or []
    governance_drift = report_data.get("governance_drift") or []
    governance_preview = report_data.get("governance_preview") or {}
    governance_summary = report_data.get("governance_summary") or build_governance_summary(report_data)
    campaign_summary = report_data.get("campaign_summary") or {}
    writeback_preview = report_data.get("writeback_preview") or {}
    rollback_preview = report_data.get("rollback_preview") or {}

    for check in preflight.get("checks") or []:
        status = check.get("status", check.get("severity", "warning"))
        if status != "error":
            continue
        queue.append(
            _queue_item(
                item_id=f"setup:{check.get('key', check.get('category', 'issue'))}",
                kind="setup",
                lane="blocked",
                priority=100,
                repo="",
                title=check.get("summary", "Setup issue"),
                summary=check.get("details") or check.get("summary", "Setup issue"),
                recommended_action=check.get("recommended_fix", "Resolve the setup blocker before the next run."),
                source_run_id=review_summary.get("source_run_id", ""),
                links=[],
            )
        )

    for drift in managed_state_drift:
        queue.append(
            _queue_item(
                item_id=f"campaign-drift:{drift.get('action_id', drift.get('repo_full_name', drift.get('repo', 'unknown')))}:{drift.get('target', '')}",
                kind="campaign",
                lane="urgent",
                priority=85,
                repo=_repo_name(drift),
                title=f"{_repo_name(drift) or 'Campaign'} drift needs review",
                summary=drift.get("drift_state", drift.get("drift_type", "Managed state drift detected.")),
                recommended_action="Inspect the managed issue, topics, or custom properties before closing or applying more campaign work.",
                source_run_id=review_summary.get("source_run_id", ""),
                links=_links_from_payload(drift),
            )
        )

    for drift in governance_drift:
        lane = "blocked" if drift.get("drift_type") in {"approval-invalidated", "requires-reapproval"} else "urgent"
        queue.append(
            _queue_item(
                item_id=f"governance-drift:{drift.get('action_id', drift.get('repo_full_name', drift.get('repo', 'unknown')))}:{drift.get('control_key', drift.get('target', ''))}",
                kind="governance",
                lane=lane,
                priority=90 if lane == "blocked" else 80,
                repo=_repo_name(drift),
                title=f"{_repo_name(drift) or 'Governance'} drift needs review",
                summary=drift.get("drift_type", "Governance drift detected."),
                recommended_action="Review the governed control state and re-approve before any apply step if the fingerprint changed.",
                source_run_id=review_summary.get("source_run_id", ""),
                links=_links_from_payload(drift),
            )
        )

    if governance_summary.get("needs_reapproval") and not governance_drift:
        queue.append(
            _queue_item(
                item_id="governance:needs-reapproval",
                kind="governance",
                lane="blocked",
                priority=92,
                repo="",
                title="Governed controls need re-approval",
                summary=governance_summary.get("headline", "Governed controls need re-approval before any apply step."),
                recommended_action="Review the governed controls and re-approve them before the next manual apply step.",
                source_run_id=review_summary.get("source_run_id", ""),
                links=[],
            )
        )

    for change in report_data.get("material_changes") or []:
        if change.get("severity", 0.0) < 0.8:
            continue
        queue.append(
            _queue_item(
                item_id=f"review-change:{change.get('change_key', change.get('title', 'change'))}",
                kind="review",
                lane="urgent",
                priority=int(round(change.get("severity", 0.0) * 100)),
                repo=change.get("repo_name", ""),
                title=change.get("title", "High-severity review change"),
                summary=change.get("summary", ""),
                recommended_action=change.get("recommended_next_step", "Review the repo before reprioritizing work."),
                source_run_id=review_summary.get("source_run_id", ""),
                links=[],
            )
        )

    for target in review_targets:
        recommended = target.get("recommended_next_step", "")
        safe_to_defer = "safe to defer" in recommended.lower()
        lane = "deferred" if safe_to_defer else "ready"
        priority = 30 if safe_to_defer else int(round(target.get("severity", 0.0) * 100)) or 60
        queue.append(
            _queue_item(
                item_id=f"review-target:{target.get('repo', 'portfolio')}:{target.get('reason', '')}",
                kind="review",
                lane=lane,
                priority=priority,
                repo=target.get("repo", ""),
                title=f"Review {_repo_or_portfolio(target)}",
                summary=target.get("reason", "Needs analyst review."),
                recommended_action=recommended or ("Safe to defer." if safe_to_defer else "Inspect the latest changes and decide on next action."),
                source_run_id=review_summary.get("source_run_id", ""),
                links=[],
            )
        )

    if campaign_summary.get("action_count", 0):
        queue.append(
            _queue_item(
                item_id=f"campaign-ready:{campaign_summary.get('campaign_type', 'campaign')}",
                kind="campaign",
                lane="ready",
                priority=70,
                repo="",
                title=f"{campaign_summary.get('label', campaign_summary.get('campaign_type', 'Campaign'))} is ready for review",
                summary=f"{campaign_summary.get('action_count', 0)} actions across {campaign_summary.get('repo_count', 0)} repos.",
                recommended_action=f"Review the {writeback_preview.get('sync_mode', 'reconcile')} queue before any manual writeback.",
                source_run_id=review_summary.get("source_run_id", ""),
                links=[],
            )
        )

    for action in governance_preview.get("actions", []) or []:
        if not action.get("applyable"):
            continue
        queue.append(
            _queue_item(
                item_id=f"governance-ready:{action.get('action_id', action.get('repo_full_name', 'governance'))}",
                kind="governance",
                lane="ready",
                priority=75,
                repo=_repo_name(action),
                title=action.get("title", "Governed control ready"),
                summary=action.get("why", "A governed control is ready for operator review."),
                recommended_action="Review prerequisites and approve the governed control if the repo is ready.",
                source_run_id=review_summary.get("source_run_id", ""),
                links=_links_from_payload(action),
            )
        )

    if rollback_preview.get("available") and not rollback_preview.get("fully_reversible_count", 0):
        queue.append(
            _queue_item(
                item_id="rollback-exposure",
                kind="campaign",
                lane="urgent",
                priority=78,
                repo="",
                title="Rollback coverage is only partial",
                summary=f"{rollback_preview.get('item_count', 0)} managed changes exist but not all are fully reversible.",
                recommended_action="Review rollback exposure before the next manual apply or close decision.",
                source_run_id=review_summary.get("source_run_id", ""),
                links=[],
            )
        )

    queue = _dedupe_queue(queue)
    queue.sort(
        key=lambda item: (
            LANE_ORDER.get(item["lane"], 99),
            -item["priority"],
            -item["age_days"],
            item["title"],
        )
    )
    if triage_view != "all":
        queue = [item for item in queue if item["lane"] == triage_view]

    recent_changes = load_recent_operator_changes(output_dir, report_data.get("username", ""), limit=12)
    evidence_bundle = load_recent_operator_evidence(
        output_dir,
        report_data.get("username", ""),
        snapshot_limit=HISTORY_WINDOW_RUNS,
        event_limit=30,
    )
    history = evidence_bundle.get("history") or load_operator_state_history(
        output_dir,
        report_data.get("username", ""),
        limit=HISTORY_WINDOW_RUNS - 1,
    )
    setup_health = {
        "status": preflight.get("status", "unknown"),
        "blocking_errors": preflight.get("blocking_errors", 0),
        "warnings": preflight.get("warnings", 0),
    }
    counts = {lane: sum(1 for item in queue if item["lane"] == lane) for lane in LANE_ORDER}
    watch_guidance = build_watch_guidance(report_data.get("watch_state") or {})
    confidence_calibration = _build_confidence_calibration(
        load_operator_calibration_history(
            output_dir,
            report_data.get("username", ""),
            limit=CALIBRATION_WINDOW_RUNS,
        )
    )
    resolution_trend = _build_resolution_trend(
        queue,
        history,
        evidence_bundle.get("events") or [],
        confidence_calibration=confidence_calibration,
        current_generated_at=report_data.get("generated_at", ""),
    )
    follow_through = _build_follow_through(resolution_trend)
    raw_next_action = _next_operator_action(
        resolution_trend.get("primary_target") or (queue[0] if queue else {}),
        watch_guidance,
        follow_through,
        resolution_trend,
    )
    confidence = _operator_confidence_summary(
        resolution_trend.get("primary_target") or {},
        raw_next_action,
        watch_guidance,
        confidence_calibration,
    )
    handoff = _build_operator_handoff(
        queue,
        recent_changes,
        setup_health,
        watch_guidance,
        follow_through,
        resolution_trend,
        confidence_calibration,
        confidence,
        raw_next_action,
    )
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
        "primary_target_exception_pattern_status": resolution_trend["primary_target_exception_pattern_status"],
        "primary_target_exception_pattern_reason": resolution_trend["primary_target_exception_pattern_reason"],
        "primary_target_trust_recovery_status": resolution_trend["primary_target_trust_recovery_status"],
        "primary_target_trust_recovery_reason": resolution_trend["primary_target_trust_recovery_reason"],
        "exception_pattern_summary": resolution_trend["exception_pattern_summary"],
        "false_positive_exception_hotspots": resolution_trend["false_positive_exception_hotspots"],
        "trust_recovery_window_runs": resolution_trend["trust_recovery_window_runs"],
        "primary_target_recovery_confidence_score": resolution_trend["primary_target_recovery_confidence_score"],
        "primary_target_recovery_confidence_label": resolution_trend["primary_target_recovery_confidence_label"],
        "primary_target_recovery_confidence_reasons": resolution_trend["primary_target_recovery_confidence_reasons"],
        "recovery_confidence_summary": resolution_trend["recovery_confidence_summary"],
        "primary_target_exception_retirement_status": resolution_trend["primary_target_exception_retirement_status"],
        "primary_target_exception_retirement_reason": resolution_trend["primary_target_exception_retirement_reason"],
        "exception_retirement_summary": resolution_trend["exception_retirement_summary"],
        "retired_exception_hotspots": resolution_trend["retired_exception_hotspots"],
        "sticky_exception_hotspots": resolution_trend["sticky_exception_hotspots"],
        "exception_retirement_window_runs": resolution_trend["exception_retirement_window_runs"],
        "primary_target_policy_debt_status": resolution_trend["primary_target_policy_debt_status"],
        "primary_target_policy_debt_reason": resolution_trend["primary_target_policy_debt_reason"],
        "primary_target_class_normalization_status": resolution_trend["primary_target_class_normalization_status"],
        "primary_target_class_normalization_reason": resolution_trend["primary_target_class_normalization_reason"],
        "policy_debt_summary": resolution_trend["policy_debt_summary"],
        "trust_normalization_summary": resolution_trend["trust_normalization_summary"],
        "policy_debt_hotspots": resolution_trend["policy_debt_hotspots"],
        "normalized_class_hotspots": resolution_trend["normalized_class_hotspots"],
        "class_normalization_window_runs": resolution_trend["class_normalization_window_runs"],
        "primary_target_class_memory_freshness_status": resolution_trend["primary_target_class_memory_freshness_status"],
        "primary_target_class_memory_freshness_reason": resolution_trend["primary_target_class_memory_freshness_reason"],
        "primary_target_class_decay_status": resolution_trend["primary_target_class_decay_status"],
        "primary_target_class_decay_reason": resolution_trend["primary_target_class_decay_reason"],
        "class_memory_summary": resolution_trend["class_memory_summary"],
        "class_decay_summary": resolution_trend["class_decay_summary"],
        "stale_class_memory_hotspots": resolution_trend["stale_class_memory_hotspots"],
        "fresh_class_signal_hotspots": resolution_trend["fresh_class_signal_hotspots"],
        "class_decay_window_runs": resolution_trend["class_decay_window_runs"],
        "primary_target_weighted_class_support_score": resolution_trend["primary_target_weighted_class_support_score"],
        "primary_target_weighted_class_caution_score": resolution_trend["primary_target_weighted_class_caution_score"],
        "primary_target_class_trust_reweight_score": resolution_trend["primary_target_class_trust_reweight_score"],
        "primary_target_class_trust_reweight_direction": resolution_trend["primary_target_class_trust_reweight_direction"],
        "primary_target_class_trust_reweight_reasons": resolution_trend["primary_target_class_trust_reweight_reasons"],
        "class_reweighting_summary": resolution_trend["class_reweighting_summary"],
        "supporting_class_hotspots": resolution_trend["supporting_class_hotspots"],
        "caution_class_hotspots": resolution_trend["caution_class_hotspots"],
        "class_reweighting_window_runs": resolution_trend["class_reweighting_window_runs"],
        "primary_target_class_trust_momentum_score": resolution_trend["primary_target_class_trust_momentum_score"],
        "primary_target_class_trust_momentum_status": resolution_trend["primary_target_class_trust_momentum_status"],
        "primary_target_class_reweight_stability_status": resolution_trend["primary_target_class_reweight_stability_status"],
        "primary_target_class_reweight_transition_status": resolution_trend["primary_target"].get("class_reweight_transition_status", resolution_trend["primary_target_class_reweight_transition_status"]) if resolution_trend.get("primary_target") else resolution_trend["primary_target_class_reweight_transition_status"],
        "primary_target_class_reweight_transition_reason": resolution_trend["primary_target"].get("class_reweight_transition_reason", resolution_trend["primary_target_class_reweight_transition_reason"]) if resolution_trend.get("primary_target") else resolution_trend["primary_target_class_reweight_transition_reason"],
        "class_momentum_summary": resolution_trend["class_momentum_summary"],
        "class_reweight_stability_summary": resolution_trend["class_reweight_stability_summary"],
        "class_transition_window_runs": resolution_trend["class_transition_window_runs"],
        "primary_target_class_transition_health_status": resolution_trend["primary_target_class_transition_health_status"],
        "primary_target_class_transition_health_reason": resolution_trend["primary_target_class_transition_health_reason"],
        "primary_target_class_transition_resolution_status": resolution_trend["primary_target_class_transition_resolution_status"],
        "primary_target_class_transition_resolution_reason": resolution_trend["primary_target_class_transition_resolution_reason"],
        "class_transition_health_summary": resolution_trend["class_transition_health_summary"],
        "class_transition_resolution_summary": resolution_trend["class_transition_resolution_summary"],
        "class_transition_age_window_runs": resolution_trend["class_transition_age_window_runs"],
        "stalled_transition_hotspots": resolution_trend["stalled_transition_hotspots"],
        "resolving_transition_hotspots": resolution_trend["resolving_transition_hotspots"],
        "primary_target_transition_closure_confidence_score": resolution_trend["primary_target_transition_closure_confidence_score"],
        "primary_target_transition_closure_confidence_label": resolution_trend["primary_target_transition_closure_confidence_label"],
        "primary_target_transition_closure_likely_outcome": resolution_trend["primary_target"].get("transition_closure_likely_outcome", resolution_trend["primary_target_transition_closure_likely_outcome"]) if resolution_trend.get("primary_target") else resolution_trend["primary_target_transition_closure_likely_outcome"],
        "primary_target_transition_closure_confidence_reasons": resolution_trend["primary_target_transition_closure_confidence_reasons"],
        "transition_closure_confidence_summary": resolution_trend["transition_closure_confidence_summary"],
        "transition_closure_window_runs": resolution_trend["transition_closure_window_runs"],
        "primary_target_class_pending_debt_status": resolution_trend["primary_target_class_pending_debt_status"],
        "primary_target_class_pending_debt_reason": resolution_trend["primary_target_class_pending_debt_reason"],
        "class_pending_debt_summary": resolution_trend["class_pending_debt_summary"],
        "class_pending_resolution_summary": resolution_trend["class_pending_resolution_summary"],
        "class_pending_debt_window_runs": resolution_trend["class_pending_debt_window_runs"],
        "pending_debt_hotspots": resolution_trend["pending_debt_hotspots"],
        "healthy_pending_resolution_hotspots": resolution_trend["healthy_pending_resolution_hotspots"],
        "primary_target_pending_debt_freshness_status": resolution_trend["primary_target_pending_debt_freshness_status"],
        "primary_target_pending_debt_freshness_reason": resolution_trend["primary_target_pending_debt_freshness_reason"],
        "pending_debt_freshness_summary": resolution_trend["pending_debt_freshness_summary"],
        "pending_debt_decay_summary": resolution_trend["pending_debt_decay_summary"],
        "stale_pending_debt_hotspots": resolution_trend["stale_pending_debt_hotspots"],
        "fresh_pending_resolution_hotspots": resolution_trend["fresh_pending_resolution_hotspots"],
        "pending_debt_decay_window_runs": resolution_trend["pending_debt_decay_window_runs"],
        "primary_target_weighted_pending_resolution_support_score": resolution_trend["primary_target_weighted_pending_resolution_support_score"],
        "primary_target_weighted_pending_debt_caution_score": resolution_trend["primary_target_weighted_pending_debt_caution_score"],
        "primary_target_closure_forecast_reweight_score": resolution_trend["primary_target_closure_forecast_reweight_score"],
        "primary_target_closure_forecast_reweight_direction": resolution_trend["primary_target_closure_forecast_reweight_direction"],
        "primary_target_closure_forecast_reweight_reasons": resolution_trend["primary_target_closure_forecast_reweight_reasons"],
        "closure_forecast_reweighting_summary": resolution_trend["closure_forecast_reweighting_summary"],
        "closure_forecast_reweighting_window_runs": resolution_trend["closure_forecast_reweighting_window_runs"],
        "supporting_pending_resolution_hotspots": resolution_trend["supporting_pending_resolution_hotspots"],
        "caution_pending_debt_hotspots": resolution_trend["caution_pending_debt_hotspots"],
        "primary_target_closure_forecast_momentum_score": resolution_trend["primary_target_closure_forecast_momentum_score"],
        "primary_target_closure_forecast_momentum_status": resolution_trend["primary_target_closure_forecast_momentum_status"],
        "primary_target_closure_forecast_stability_status": resolution_trend["primary_target_closure_forecast_stability_status"],
        "primary_target_closure_forecast_hysteresis_status": resolution_trend["primary_target_closure_forecast_hysteresis_status"],
        "primary_target_closure_forecast_hysteresis_reason": resolution_trend["primary_target_closure_forecast_hysteresis_reason"],
        "closure_forecast_momentum_summary": resolution_trend["closure_forecast_momentum_summary"],
        "closure_forecast_stability_summary": resolution_trend["closure_forecast_stability_summary"],
        "closure_forecast_hysteresis_summary": resolution_trend["closure_forecast_hysteresis_summary"],
        "closure_forecast_transition_window_runs": resolution_trend["closure_forecast_transition_window_runs"],
        "sustained_confirmation_hotspots": resolution_trend["sustained_confirmation_hotspots"],
        "sustained_clearance_hotspots": resolution_trend["sustained_clearance_hotspots"],
        "oscillating_closure_forecast_hotspots": resolution_trend["oscillating_closure_forecast_hotspots"],
        "primary_target_closure_forecast_freshness_status": resolution_trend["primary_target_closure_forecast_freshness_status"],
        "primary_target_closure_forecast_freshness_reason": resolution_trend["primary_target_closure_forecast_freshness_reason"],
        "primary_target_closure_forecast_decay_status": resolution_trend["primary_target_closure_forecast_decay_status"],
        "primary_target_closure_forecast_decay_reason": resolution_trend["primary_target_closure_forecast_decay_reason"],
        "closure_forecast_freshness_summary": resolution_trend["closure_forecast_freshness_summary"],
        "closure_forecast_decay_summary": resolution_trend["closure_forecast_decay_summary"],
        "stale_closure_forecast_hotspots": resolution_trend["stale_closure_forecast_hotspots"],
        "fresh_closure_forecast_signal_hotspots": resolution_trend["fresh_closure_forecast_signal_hotspots"],
        "closure_forecast_decay_window_runs": resolution_trend["closure_forecast_decay_window_runs"],
        "primary_target_closure_forecast_refresh_recovery_score": resolution_trend["primary_target_closure_forecast_refresh_recovery_score"],
        "primary_target_closure_forecast_refresh_recovery_status": resolution_trend["primary_target_closure_forecast_refresh_recovery_status"],
        "primary_target_closure_forecast_reacquisition_status": resolution_trend["primary_target_closure_forecast_reacquisition_status"],
        "primary_target_closure_forecast_reacquisition_reason": resolution_trend["primary_target_closure_forecast_reacquisition_reason"],
        "closure_forecast_refresh_recovery_summary": resolution_trend["closure_forecast_refresh_recovery_summary"],
        "closure_forecast_reacquisition_summary": resolution_trend["closure_forecast_reacquisition_summary"],
        "closure_forecast_refresh_window_runs": resolution_trend["closure_forecast_refresh_window_runs"],
        "recovering_confirmation_hotspots": resolution_trend["recovering_confirmation_hotspots"],
        "recovering_clearance_hotspots": resolution_trend["recovering_clearance_hotspots"],
        "primary_target_closure_forecast_reacquisition_age_runs": resolution_trend["primary_target_closure_forecast_reacquisition_age_runs"],
        "primary_target_closure_forecast_reacquisition_persistence_score": resolution_trend["primary_target_closure_forecast_reacquisition_persistence_score"],
        "primary_target_closure_forecast_reacquisition_persistence_status": resolution_trend["primary_target_closure_forecast_reacquisition_persistence_status"],
        "primary_target_closure_forecast_reacquisition_persistence_reason": resolution_trend["primary_target_closure_forecast_reacquisition_persistence_reason"],
        "closure_forecast_reacquisition_persistence_summary": resolution_trend["closure_forecast_reacquisition_persistence_summary"],
        "closure_forecast_reacquisition_window_runs": resolution_trend["closure_forecast_reacquisition_window_runs"],
        "just_reacquired_hotspots": resolution_trend["just_reacquired_hotspots"],
        "holding_reacquisition_hotspots": resolution_trend["holding_reacquisition_hotspots"],
        "primary_target_closure_forecast_recovery_churn_score": resolution_trend["primary_target_closure_forecast_recovery_churn_score"],
        "primary_target_closure_forecast_recovery_churn_status": resolution_trend["primary_target_closure_forecast_recovery_churn_status"],
        "primary_target_closure_forecast_recovery_churn_reason": resolution_trend["primary_target_closure_forecast_recovery_churn_reason"],
        "closure_forecast_recovery_churn_summary": resolution_trend["closure_forecast_recovery_churn_summary"],
        "recovery_churn_hotspots": resolution_trend["recovery_churn_hotspots"],
        "primary_target_closure_forecast_reacquisition_freshness_status": resolution_trend["primary_target_closure_forecast_reacquisition_freshness_status"],
        "primary_target_closure_forecast_reacquisition_freshness_reason": resolution_trend["primary_target_closure_forecast_reacquisition_freshness_reason"],
        "closure_forecast_reacquisition_freshness_summary": resolution_trend["closure_forecast_reacquisition_freshness_summary"],
        "primary_target_closure_forecast_persistence_reset_status": resolution_trend["primary_target_closure_forecast_persistence_reset_status"],
        "primary_target_closure_forecast_persistence_reset_reason": resolution_trend["primary_target_closure_forecast_persistence_reset_reason"],
        "closure_forecast_persistence_reset_summary": resolution_trend["closure_forecast_persistence_reset_summary"],
        "stale_reacquisition_hotspots": resolution_trend["stale_reacquisition_hotspots"],
        "fresh_reacquisition_signal_hotspots": resolution_trend["fresh_reacquisition_signal_hotspots"],
        "closure_forecast_reacquisition_decay_window_runs": resolution_trend["closure_forecast_reacquisition_decay_window_runs"],
        "primary_target_closure_forecast_reset_refresh_recovery_score": resolution_trend["primary_target_closure_forecast_reset_refresh_recovery_score"],
        "primary_target_closure_forecast_reset_refresh_recovery_status": resolution_trend["primary_target_closure_forecast_reset_refresh_recovery_status"],
        "primary_target_closure_forecast_reset_reentry_status": resolution_trend["primary_target_closure_forecast_reset_reentry_status"],
        "primary_target_closure_forecast_reset_reentry_reason": resolution_trend["primary_target_closure_forecast_reset_reentry_reason"],
        "closure_forecast_reset_refresh_recovery_summary": resolution_trend["closure_forecast_reset_refresh_recovery_summary"],
        "closure_forecast_reset_reentry_summary": resolution_trend["closure_forecast_reset_reentry_summary"],
        "closure_forecast_reset_refresh_window_runs": resolution_trend["closure_forecast_reset_refresh_window_runs"],
        "recovering_from_confirmation_reset_hotspots": resolution_trend["recovering_from_confirmation_reset_hotspots"],
        "recovering_from_clearance_reset_hotspots": resolution_trend["recovering_from_clearance_reset_hotspots"],
        "primary_target_closure_forecast_reset_reentry_age_runs": resolution_trend["primary_target_closure_forecast_reset_reentry_age_runs"],
        "primary_target_closure_forecast_reset_reentry_persistence_score": resolution_trend["primary_target_closure_forecast_reset_reentry_persistence_score"],
        "primary_target_closure_forecast_reset_reentry_persistence_status": resolution_trend["primary_target_closure_forecast_reset_reentry_persistence_status"],
        "primary_target_closure_forecast_reset_reentry_persistence_reason": resolution_trend["primary_target_closure_forecast_reset_reentry_persistence_reason"],
        "closure_forecast_reset_reentry_persistence_summary": resolution_trend["closure_forecast_reset_reentry_persistence_summary"],
        "closure_forecast_reset_reentry_window_runs": resolution_trend["closure_forecast_reset_reentry_window_runs"],
        "just_reentered_hotspots": resolution_trend["just_reentered_hotspots"],
        "holding_reset_reentry_hotspots": resolution_trend["holding_reset_reentry_hotspots"],
        "primary_target_closure_forecast_reset_reentry_churn_score": resolution_trend["primary_target_closure_forecast_reset_reentry_churn_score"],
        "primary_target_closure_forecast_reset_reentry_churn_status": resolution_trend["primary_target_closure_forecast_reset_reentry_churn_status"],
        "primary_target_closure_forecast_reset_reentry_churn_reason": resolution_trend["primary_target_closure_forecast_reset_reentry_churn_reason"],
        "closure_forecast_reset_reentry_churn_summary": resolution_trend["closure_forecast_reset_reentry_churn_summary"],
        "reset_reentry_churn_hotspots": resolution_trend["reset_reentry_churn_hotspots"],
        "primary_target_closure_forecast_reset_reentry_freshness_status": resolution_trend["primary_target_closure_forecast_reset_reentry_freshness_status"],
        "primary_target_closure_forecast_reset_reentry_freshness_reason": resolution_trend["primary_target_closure_forecast_reset_reentry_freshness_reason"],
        "closure_forecast_reset_reentry_freshness_summary": resolution_trend["closure_forecast_reset_reentry_freshness_summary"],
        "primary_target_closure_forecast_reset_reentry_reset_status": resolution_trend["primary_target_closure_forecast_reset_reentry_reset_status"],
        "primary_target_closure_forecast_reset_reentry_reset_reason": resolution_trend["primary_target_closure_forecast_reset_reentry_reset_reason"],
        "closure_forecast_reset_reentry_reset_summary": resolution_trend["closure_forecast_reset_reentry_reset_summary"],
        "stale_reset_reentry_hotspots": resolution_trend["stale_reset_reentry_hotspots"],
        "fresh_reset_reentry_signal_hotspots": resolution_trend["fresh_reset_reentry_signal_hotspots"],
        "closure_forecast_reset_reentry_decay_window_runs": resolution_trend["closure_forecast_reset_reentry_decay_window_runs"],
        "primary_target_closure_forecast_reset_reentry_refresh_recovery_score": resolution_trend["primary_target_closure_forecast_reset_reentry_refresh_recovery_score"],
        "primary_target_closure_forecast_reset_reentry_refresh_recovery_status": resolution_trend["primary_target_closure_forecast_reset_reentry_refresh_recovery_status"],
        "primary_target_closure_forecast_reset_reentry_rebuild_status": resolution_trend["primary_target_closure_forecast_reset_reentry_rebuild_status"],
        "primary_target_closure_forecast_reset_reentry_rebuild_reason": resolution_trend["primary_target_closure_forecast_reset_reentry_rebuild_reason"],
        "closure_forecast_reset_reentry_refresh_recovery_summary": resolution_trend["closure_forecast_reset_reentry_refresh_recovery_summary"],
        "closure_forecast_reset_reentry_rebuild_summary": resolution_trend["closure_forecast_reset_reentry_rebuild_summary"],
        "closure_forecast_reset_reentry_refresh_window_runs": resolution_trend["closure_forecast_reset_reentry_refresh_window_runs"],
        "recovering_from_confirmation_reentry_reset_hotspots": resolution_trend["recovering_from_confirmation_reentry_reset_hotspots"],
        "recovering_from_clearance_reentry_reset_hotspots": resolution_trend["recovering_from_clearance_reentry_reset_hotspots"],
        "primary_target_closure_forecast_reset_reentry_rebuild_age_runs": resolution_trend["primary_target_closure_forecast_reset_reentry_rebuild_age_runs"],
        "primary_target_closure_forecast_reset_reentry_rebuild_persistence_score": resolution_trend["primary_target_closure_forecast_reset_reentry_rebuild_persistence_score"],
        "primary_target_closure_forecast_reset_reentry_rebuild_persistence_status": resolution_trend["primary_target_closure_forecast_reset_reentry_rebuild_persistence_status"],
        "primary_target_closure_forecast_reset_reentry_rebuild_persistence_reason": resolution_trend["primary_target_closure_forecast_reset_reentry_rebuild_persistence_reason"],
        "closure_forecast_reset_reentry_rebuild_persistence_summary": resolution_trend["closure_forecast_reset_reentry_rebuild_persistence_summary"],
        "closure_forecast_reset_reentry_rebuild_window_runs": resolution_trend["closure_forecast_reset_reentry_rebuild_window_runs"],
        "just_rebuilt_hotspots": resolution_trend["just_rebuilt_hotspots"],
        "holding_reset_reentry_rebuild_hotspots": resolution_trend["holding_reset_reentry_rebuild_hotspots"],
        "primary_target_closure_forecast_reset_reentry_rebuild_churn_score": resolution_trend["primary_target_closure_forecast_reset_reentry_rebuild_churn_score"],
        "primary_target_closure_forecast_reset_reentry_rebuild_churn_status": resolution_trend["primary_target_closure_forecast_reset_reentry_rebuild_churn_status"],
        "primary_target_closure_forecast_reset_reentry_rebuild_churn_reason": resolution_trend["primary_target_closure_forecast_reset_reentry_rebuild_churn_reason"],
        "closure_forecast_reset_reentry_rebuild_churn_summary": resolution_trend["closure_forecast_reset_reentry_rebuild_churn_summary"],
        "reset_reentry_rebuild_churn_hotspots": resolution_trend["reset_reentry_rebuild_churn_hotspots"],
        "primary_target_closure_forecast_reset_reentry_rebuild_freshness_status": resolution_trend["primary_target_closure_forecast_reset_reentry_rebuild_freshness_status"],
        "primary_target_closure_forecast_reset_reentry_rebuild_freshness_reason": resolution_trend["primary_target_closure_forecast_reset_reentry_rebuild_freshness_reason"],
        "closure_forecast_reset_reentry_rebuild_freshness_summary": resolution_trend["closure_forecast_reset_reentry_rebuild_freshness_summary"],
        "primary_target_closure_forecast_reset_reentry_rebuild_reset_status": resolution_trend["primary_target_closure_forecast_reset_reentry_rebuild_reset_status"],
        "primary_target_closure_forecast_reset_reentry_rebuild_reset_reason": resolution_trend["primary_target_closure_forecast_reset_reentry_rebuild_reset_reason"],
        "closure_forecast_reset_reentry_rebuild_reset_summary": resolution_trend["closure_forecast_reset_reentry_rebuild_reset_summary"],
        "stale_reset_reentry_rebuild_hotspots": resolution_trend["stale_reset_reentry_rebuild_hotspots"],
        "fresh_reset_reentry_rebuild_signal_hotspots": resolution_trend["fresh_reset_reentry_rebuild_signal_hotspots"],
        "closure_forecast_reset_reentry_rebuild_decay_window_runs": resolution_trend["closure_forecast_reset_reentry_rebuild_decay_window_runs"],
        "sustained_class_hotspots": resolution_trend["sustained_class_hotspots"],
        "oscillating_class_hotspots": resolution_trend["oscillating_class_hotspots"],
        "decision_memory_status": resolution_trend["decision_memory_status"],
        "primary_target_last_seen_at": resolution_trend["primary_target_last_seen_at"],
        "primary_target_last_intervention": resolution_trend["primary_target_last_intervention"],
        "primary_target_last_outcome": resolution_trend["primary_target_last_outcome"],
        "primary_target_resolution_evidence": resolution_trend["primary_target_resolution_evidence"],
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
        "recommendation_quality_summary": confidence["recommendation_quality_summary"],
        "primary_target_trust_policy": confidence["primary_target_trust_policy"],
        "primary_target_trust_policy_reason": confidence["primary_target_trust_policy_reason"],
        "next_action_trust_policy": confidence["next_action_trust_policy"],
        "next_action_trust_policy_reason": confidence["next_action_trust_policy_reason"],
        "adaptive_confidence_summary": confidence["adaptive_confidence_summary"],
        "confidence_validation_status": confidence_calibration["confidence_validation_status"],
        "confidence_window_runs": confidence_calibration["confidence_window_runs"],
        "validated_recommendation_count": confidence_calibration["validated_recommendation_count"],
        "partially_validated_recommendation_count": confidence_calibration["partially_validated_recommendation_count"],
        "unresolved_recommendation_count": confidence_calibration["unresolved_recommendation_count"],
        "reopened_recommendation_count": confidence_calibration["reopened_recommendation_count"],
        "insufficient_future_runs_count": confidence_calibration["insufficient_future_runs_count"],
        "high_confidence_hit_rate": confidence_calibration["high_confidence_hit_rate"],
        "medium_confidence_hit_rate": confidence_calibration["medium_confidence_hit_rate"],
        "low_confidence_caution_rate": confidence_calibration["low_confidence_caution_rate"],
        "recent_validation_outcomes": confidence_calibration["recent_validation_outcomes"],
        "confidence_calibration_summary": confidence_calibration["confidence_calibration_summary"],
    }
    return {
        "operator_summary": summary,
        "operator_queue": queue,
        "operator_setup_health": setup_health,
        "operator_recent_changes": recent_changes,
    }


def render_control_center_markdown(snapshot: dict, username: str, generated_at: str) -> str:
    summary = snapshot.get("operator_summary", {})
    setup_health = snapshot.get("operator_setup_health", {})
    lines = [
        f"# Operator Control Center: {username}",
        "",
        f"*Generated:* {generated_at[:10]}",
        f"*Headline:* {summary.get('headline', 'No triage items available.')}",
        "",
    ]
    if summary.get("report_reference"):
        lines.append(f"*Latest Report:* `{summary['report_reference']}`")
    if summary.get("source_run_id"):
        lines.append(f"*Source Run:* `{summary['source_run_id']}`")
    if summary.get("next_recommended_run_mode"):
        lines.append(f"*Next Recommended Run:* `{summary['next_recommended_run_mode']}`")
    if summary.get("watch_strategy"):
        lines.append(f"*Watch Strategy:* `{summary['watch_strategy']}`")
    if summary.get("watch_decision_summary"):
        lines.append(f"*Watch Decision:* {summary['watch_decision_summary']}")
    if summary.get("what_changed"):
        lines.append(f"*What Changed:* {summary['what_changed']}")
    if summary.get("why_it_matters"):
        lines.append(f"*Why It Matters:* {summary['why_it_matters']}")
    if summary.get("what_to_do_next"):
        lines.append(f"*What To Do Next:* {summary['what_to_do_next']}")
    if summary.get("trend_summary"):
        lines.append(f"*Trend:* {summary['trend_summary']}")
    if summary.get("accountability_summary"):
        lines.append(f"*Accountability:* {summary['accountability_summary']}")
    if summary.get("follow_through_summary"):
        lines.append(f"*Follow-Through:* {summary['follow_through_summary']}")
    if summary.get("primary_target"):
        target = summary["primary_target"]
        repo = f"{target.get('repo')}: " if target.get("repo") else ""
        lines.append(f"*Primary Target:* {repo}{target.get('title', 'Operator target')}")
    if summary.get("primary_target_reason"):
        lines.append(f"*Why This Is The Top Target:* {summary['primary_target_reason']}")
    if summary.get("primary_target_done_criteria"):
        lines.append(f"*What Counts As Done:* {summary['primary_target_done_criteria']}")
    if summary.get("closure_guidance"):
        lines.append(f"*Closure Guidance:* {summary['closure_guidance']}")
    if summary.get("primary_target_last_intervention"):
        lines.append(
            f"*What We Tried:* {_format_intervention(summary['primary_target_last_intervention'])}"
        )
    if summary.get("primary_target_resolution_evidence"):
        lines.append(f"*Resolution Evidence:* {summary['primary_target_resolution_evidence']}")
    if summary.get("primary_target_confidence_label"):
        lines.append(
            f"*Primary Target Confidence:* {summary['primary_target_confidence_label']} "
            f"({summary.get('primary_target_confidence_score', 0.0):.2f})"
        )
    if summary.get("primary_target_confidence_reasons"):
        lines.append(
            f"*Confidence Reasons:* {', '.join(summary.get('primary_target_confidence_reasons') or [])}"
        )
    if summary.get("next_action_confidence_label"):
        lines.append(
            f"*Next Action Confidence:* {summary['next_action_confidence_label']} "
            f"({summary.get('next_action_confidence_score', 0.0):.2f})"
        )
    if summary.get("primary_target_trust_policy"):
        lines.append(
            f"*Trust Policy:* {summary.get('primary_target_trust_policy')} — "
            f"{summary.get('primary_target_trust_policy_reason', 'No trust-policy reason is recorded yet.')}"
        )
    if summary.get("adaptive_confidence_summary"):
        lines.append(f"*Why This Confidence Is Actionable:* {summary['adaptive_confidence_summary']}")
    if summary.get("primary_target_exception_status") and summary.get("primary_target_exception_status") != "none":
        lines.append(
            f"*Trust Policy Exception:* {summary.get('primary_target_exception_status')} — "
            f"{summary.get('primary_target_exception_reason', 'No trust-policy exception reason is recorded yet.')}"
        )
    if summary.get("primary_target_exception_pattern_status") and summary.get("primary_target_exception_pattern_status") != "none":
        lines.append(
            f"*Exception Pattern Learning:* {summary.get('primary_target_exception_pattern_status')} — "
            f"{summary.get('primary_target_exception_pattern_reason', 'No exception-pattern reason is recorded yet.')}"
        )
    if summary.get("primary_target_trust_recovery_status") and summary.get("primary_target_trust_recovery_status") != "none":
        lines.append(
            f"*Trust Recovery:* {summary.get('primary_target_trust_recovery_status')} — "
            f"{summary.get('primary_target_trust_recovery_reason', 'No trust-recovery reason is recorded yet.')}"
        )
    if summary.get("primary_target_recovery_confidence_label"):
        lines.append(
            f"*Recovery Confidence:* {summary.get('primary_target_recovery_confidence_label')} "
            f"({summary.get('primary_target_recovery_confidence_score', 0.0):.2f}) — "
            f"{summary.get('recovery_confidence_summary', 'No recovery-confidence summary is recorded yet.')}"
        )
    if summary.get("primary_target_exception_retirement_status") and summary.get("primary_target_exception_retirement_status") != "none":
        lines.append(
            f"*Exception Retirement:* {summary.get('primary_target_exception_retirement_status')} — "
            f"{summary.get('primary_target_exception_retirement_reason', 'No exception-retirement reason is recorded yet.')}"
        )
    if summary.get("primary_target_policy_debt_status") and summary.get("primary_target_policy_debt_status") != "none":
        lines.append(
            f"*Policy Debt Cleanup:* {summary.get('primary_target_policy_debt_status')} — "
            f"{summary.get('primary_target_policy_debt_reason', 'No policy-debt reason is recorded yet.')}"
        )
    if summary.get("primary_target_class_normalization_status") and summary.get("primary_target_class_normalization_status") != "none":
        lines.append(
            f"*Class-Level Trust Normalization:* {summary.get('primary_target_class_normalization_status')} — "
            f"{summary.get('primary_target_class_normalization_reason', 'No class-normalization reason is recorded yet.')}"
        )
    if summary.get("primary_target_class_memory_freshness_status"):
        lines.append(
            f"*Class Memory Freshness:* {summary.get('primary_target_class_memory_freshness_status')} — "
            f"{summary.get('primary_target_class_memory_freshness_reason', 'No class-memory freshness reason is recorded yet.')}"
        )
    if summary.get("primary_target_class_decay_status") is not None:
        lines.append(
            f"*Trust Decay Controls:* {summary.get('primary_target_class_decay_status')} — "
            f"{summary.get('primary_target_class_decay_reason', 'No class-decay reason is recorded yet.')}"
        )
    if summary.get("primary_target_class_trust_reweight_direction"):
        lines.append(
            f"*Class Trust Reweighting:* {summary.get('primary_target_class_trust_reweight_direction')} "
            f"({summary.get('primary_target_class_trust_reweight_score', 0.0):.2f}) — "
            f"{summary.get('class_reweighting_summary', 'No class reweighting summary is recorded yet.')}"
        )
    if summary.get("primary_target_class_trust_reweight_reasons"):
        lines.append(
            f"*Why Class Guidance Shifted:* {', '.join(summary.get('primary_target_class_trust_reweight_reasons') or [])}"
        )
    if summary.get("primary_target_class_trust_momentum_status"):
        lines.append(
            f"*Class Trust Momentum:* {summary.get('primary_target_class_trust_momentum_status')} "
            f"({summary.get('primary_target_class_trust_momentum_score', 0.0):.2f}) — "
            f"{summary.get('class_momentum_summary', 'No class momentum summary is recorded yet.')}"
        )
    if summary.get("primary_target_class_reweight_stability_status"):
        lines.append(
            f"*Reweighting Stability:* {summary.get('primary_target_class_reweight_stability_status')} — "
            f"{summary.get('class_reweight_stability_summary', 'No reweighting stability summary is recorded yet.')}"
        )
    if summary.get("primary_target_class_transition_health_status"):
        lines.append(
            f"*Class Transition Health:* {summary.get('primary_target_class_transition_health_status')} — "
            f"{summary.get('class_transition_health_summary', 'No class transition health summary is recorded yet.')}"
        )
    if summary.get("primary_target_class_transition_resolution_status"):
        lines.append(
            f"*Pending Transition Resolution:* {summary.get('primary_target_class_transition_resolution_status')} — "
            f"{summary.get('class_transition_resolution_summary', 'No class transition resolution summary is recorded yet.')}"
        )
    if summary.get("primary_target_transition_closure_confidence_label"):
        lines.append(
            f"*Transition Closure Confidence:* {summary.get('primary_target_transition_closure_confidence_label')} "
            f"({summary.get('primary_target_transition_closure_confidence_score', 0.0):.2f}) — "
            f"{summary.get('transition_closure_confidence_summary', 'No transition-closure confidence summary is recorded yet.')}"
        )
    if summary.get("primary_target_class_pending_debt_status"):
        lines.append(
            f"*Class Pending Debt Audit:* {summary.get('primary_target_class_pending_debt_status')} — "
            f"{summary.get('class_pending_debt_summary', 'No class pending-debt summary is recorded yet.')}"
        )
    if summary.get("primary_target_pending_debt_freshness_status"):
        lines.append(
            f"*Pending Debt Freshness:* {summary.get('primary_target_pending_debt_freshness_status')} — "
            f"{summary.get('primary_target_pending_debt_freshness_reason', 'No pending-debt freshness reason is recorded yet.')}"
        )
    if summary.get("primary_target_closure_forecast_reweight_direction"):
        lines.append(
            f"*Closure Forecast Reweighting:* {summary.get('primary_target_closure_forecast_reweight_direction')} "
            f"({summary.get('primary_target_closure_forecast_reweight_score', 0.0):.2f}) — "
            f"{summary.get('closure_forecast_reweighting_summary', 'No closure forecast reweighting summary is recorded yet.')}"
        )
    if summary.get("recommendation_drift_status"):
        lines.append(
            f"*Recommendation Drift:* {summary.get('recommendation_drift_status')} — "
            f"{summary.get('recommendation_drift_summary', 'No recommendation-drift summary is recorded yet.')}"
        )
    if summary.get("exception_pattern_summary"):
        lines.append(f"*Exception Pattern Summary:* {summary['exception_pattern_summary']}")
    if summary.get("exception_retirement_summary"):
        lines.append(f"*Exception Retirement Summary:* {summary['exception_retirement_summary']}")
    if summary.get("policy_debt_summary"):
        lines.append(f"*Policy Debt Summary:* {summary['policy_debt_summary']}")
    if summary.get("trust_normalization_summary"):
        lines.append(f"*Trust Normalization Summary:* {summary['trust_normalization_summary']}")
    if summary.get("class_memory_summary"):
        lines.append(f"*Class Memory Summary:* {summary['class_memory_summary']}")
    if summary.get("class_decay_summary"):
        lines.append(f"*Class Decay Summary:* {summary['class_decay_summary']}")
    if summary.get("class_reweighting_summary"):
        lines.append(f"*Class Reweighting Summary:* {summary['class_reweighting_summary']}")
    if summary.get("class_momentum_summary"):
        lines.append(f"*Class Momentum Summary:* {summary['class_momentum_summary']}")
    if summary.get("class_reweight_stability_summary"):
        lines.append(f"*Reweighting Stability Summary:* {summary['class_reweight_stability_summary']}")
    if summary.get("class_transition_health_summary"):
        lines.append(f"*Class Transition Health Summary:* {summary['class_transition_health_summary']}")
    if summary.get("class_transition_resolution_summary"):
        lines.append(f"*Pending Transition Resolution Summary:* {summary['class_transition_resolution_summary']}")
    if summary.get("transition_closure_confidence_summary"):
        lines.append(f"*Transition Closure Confidence Summary:* {summary['transition_closure_confidence_summary']}")
    if summary.get("class_pending_debt_summary"):
        lines.append(f"*Class Pending Debt Summary:* {summary['class_pending_debt_summary']}")
    if summary.get("class_pending_resolution_summary"):
        lines.append(f"*Class Pending Resolution Summary:* {summary['class_pending_resolution_summary']}")
    if summary.get("pending_debt_freshness_summary"):
        lines.append(f"*Pending Debt Freshness Summary:* {summary['pending_debt_freshness_summary']}")
    if summary.get("pending_debt_decay_summary"):
        lines.append(f"*Pending Debt Decay Summary:* {summary['pending_debt_decay_summary']}")
    if summary.get("closure_forecast_reweighting_summary"):
        lines.append(f"*Closure Forecast Reweighting Summary:* {summary['closure_forecast_reweighting_summary']}")
    if summary.get("recommendation_quality_summary"):
        lines.append(f"*Recommendation Quality:* {summary['recommendation_quality_summary']}")
    if summary.get("confidence_validation_status"):
        lines.append(
            f"*Confidence Validation:* {summary.get('confidence_validation_status')} — "
            f"{summary.get('confidence_calibration_summary', 'No confidence-calibration summary is recorded yet.')}"
        )
    recent_outcomes_line = _recent_validation_outcomes_line(summary.get("recent_validation_outcomes") or [])
    if recent_outcomes_line:
        lines.append(f"*Recent Confidence Outcomes:* {recent_outcomes_line}")
    if summary.get("control_center_reference"):
        lines.append(f"*Control Center Artifact:* `{summary['control_center_reference']}`")
    lines.append(
        f"*Setup Health:* {setup_health.get('status', 'unknown')} | "
        f"Errors: {setup_health.get('blocking_errors', 0)} | "
        f"Warnings: {setup_health.get('warnings', 0)}"
    )
    lines.append("")
    queue = snapshot.get("operator_queue", [])
    for lane in ("blocked", "urgent", "ready", "deferred"):
        items = [item for item in queue if item["lane"] == lane]
        if not items:
            continue
        lines.append(f"## {LANE_LABELS[lane]}")
        lines.append("")
        for item in items:
            repo = f"{item['repo']}: " if item.get("repo") else ""
            lines.append(f"- {repo}{item['title']} — {item['summary']}")
            lines.append(f"  Why this lane: {item.get('lane_reason', item.get('lane_label', LANE_LABELS.get(item['lane'], item['lane'])))}")
            lines.append(f"  Action: {item['recommended_action']}")
        lines.append("")
    recent_changes = snapshot.get("operator_recent_changes") or []
    if recent_changes:
        lines.append("## Recently Changed")
        lines.append("")
        for change in recent_changes[:6]:
            when = change.get("generated_at", "")[:10]
            subject = change.get("repo") or change.get("repo_full_name") or change.get("item_id") or "portfolio"
            lines.append(f"- {when}: {subject} — {change.get('summary', change.get('kind', 'Operator change'))}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def control_center_artifact_payload(report_data: dict, snapshot: dict) -> dict:
    return {
        "username": report_data.get("username", "unknown"),
        "generated_at": report_data.get("generated_at", ""),
        "report_reference": report_data.get("latest_report_path", ""),
        "watch_state": report_data.get("watch_state", {}),
        "operator_summary": snapshot.get("operator_summary", {}),
        "operator_queue": snapshot.get("operator_queue", []),
        "operator_setup_health": snapshot.get("operator_setup_health", {}),
        "operator_recent_changes": snapshot.get("operator_recent_changes", []),
        "review_summary": report_data.get("review_summary", {}),
        "preflight_summary": report_data.get("preflight_summary", {}),
    }


def _has_normalized_review_state(report_data: dict) -> bool:
    return any(
        report_data.get(key)
        for key in ("review_summary", "review_alerts", "material_changes", "review_targets", "review_history")
    )


def _queue_item(
    *,
    item_id: str,
    kind: str,
    lane: str,
    priority: int,
    repo: str,
    title: str,
    summary: str,
    recommended_action: str,
    source_run_id: str,
    links: list[dict],
) -> dict:
    age_days = _age_days_from_run_id(source_run_id)
    lane_label = LANE_LABELS.get(lane, lane.replace("-", " ").title())
    return {
        "item_id": item_id,
        "kind": kind,
        "lane": lane,
        "lane_label": lane_label,
        "lane_reason": _lane_reason(lane, kind),
        "priority": priority,
        "repo": repo,
        "title": title,
        "summary": summary,
        "recommended_action": recommended_action,
        "source_run_id": source_run_id,
        "age_days": age_days,
        "links": links,
    }


def _normalize_review_summary(summary: dict) -> dict:
    normalized = dict(summary)
    decision_state = normalized.get("decision_state")
    if not decision_state:
        decisions = normalized.get("decisions") or []
        decision_values = [item.get("decision") for item in decisions if isinstance(item, dict)]
        if "approve-governance" in decision_values:
            decision_state = "ready-for-governance-approval"
        elif "preview-campaign" in decision_values:
            decision_state = "ready-for-campaign-preview"
        elif normalized.get("safe_to_defer"):
            decision_state = "safe-to-defer"
        else:
            decision_state = "needs-review"
    normalized.setdefault("status", "open")
    normalized.setdefault("sync_state", "local-only")
    normalized["decision_state"] = decision_state
    normalized.setdefault("synced_targets", [])
    return normalized


def _normalize_review_target(item: dict) -> dict:
    normalized = dict(item)
    next_step = normalized.get("next_step") or normalized.get("recommended_next_step") or ""
    normalized.setdefault("title", normalized.get("repo", "Portfolio review target"))
    normalized.setdefault("reason", normalized.get("summary", normalized.get("reason", "")))
    normalized["recommended_next_step"] = next_step
    normalized["next_step"] = next_step
    normalized.setdefault("decision_hint", "safe-to-defer" if "safe to defer" in next_step.lower() else "needs-review")
    normalized.setdefault("safe_to_defer", "safe to defer" in next_step.lower())
    return normalized


def _normalize_review_history_item(item: dict) -> dict:
    normalized = dict(item)
    normalized.setdefault("status", "open")
    normalized.setdefault("decision_state", "needs-review")
    normalized.setdefault("sync_state", "local-only")
    normalized.setdefault("safe_to_defer", normalized.get("decision_state") == "safe-to-defer")
    return normalized


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
        resolution_trend.get("primary_target_closure_forecast_freshness_status", "insufficient-data"),
        resolution_trend.get("primary_target_closure_forecast_decay_status", "none"),
        resolution_trend.get("primary_target_closure_forecast_refresh_recovery_status", "none"),
        resolution_trend.get("primary_target_closure_forecast_reacquisition_status", "none"),
        resolution_trend.get("primary_target_closure_forecast_momentum_status", "insufficient-data"),
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
        f"{_closure_forecast_reset_reentry_rebuild_persistence_note(resolution_trend)} "
        f"{_closure_forecast_reset_reentry_rebuild_churn_note(resolution_trend)} "
        f"{_closure_forecast_hysteresis_note(resolution_trend)} "
        f"{_recommendation_drift_note(resolution_trend)} "
        f"{confidence_calibration.get('confidence_calibration_summary', '')} "
        f"{confidence.get('adaptive_confidence_summary', '')} "
        f"{follow_through.get('follow_through_summary', '')} "
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


def _build_follow_through(resolution_trend: dict) -> dict:
    resolution_targets = resolution_trend.get("resolution_targets", [])
    repeat_urgent_count = sum(1 for item in resolution_targets if item.get("repeat_urgent"))
    stale_item_count = sum(1 for item in resolution_targets if item.get("stale"))
    oldest_open_item_days = max((item.get("age_days", 0) for item in resolution_targets), default=0)
    quiet_streak_runs = resolution_trend.get("quiet_streak_runs", 0)
    return {
        "repeat_urgent_count": repeat_urgent_count,
        "stale_item_count": stale_item_count,
        "oldest_open_item_days": oldest_open_item_days,
        "quiet_streak_runs": quiet_streak_runs,
        "follow_through_summary": _follow_through_summary(
            repeat_urgent_count,
            stale_item_count,
            oldest_open_item_days,
            quiet_streak_runs,
        ),
    }


def _build_confidence_calibration(history: list[dict]) -> dict:
    ordered_runs = sorted(
        [
            {
                "run_id": entry.get("run_id", ""),
                "generated_at": entry.get("generated_at", ""),
                "operator_summary": entry.get("operator_summary") or {},
                "operator_queue": entry.get("operator_queue") or [],
            }
            for entry in history[:CALIBRATION_WINDOW_RUNS]
        ],
        key=lambda item: item.get("generated_at", ""),
    )
    evaluations: list[dict] = []
    for index, run in enumerate(ordered_runs):
        summary = run.get("operator_summary") or {}
        target = summary.get("primary_target") or {}
        confidence_label = summary.get("primary_target_confidence_label", "")
        if not target or confidence_label not in {"high", "medium", "low"}:
            continue
        outcome, validated_in_runs = _calibration_outcome(
            run,
            ordered_runs[index + 1 : index + 1 + VALIDATION_WINDOW_RUNS],
        )
        target_label = _target_label(target)
        evaluations.append(
            {
                "run_id": run.get("run_id", ""),
                "generated_at": run.get("generated_at", ""),
                "target_label": target_label,
                "confidence_label": confidence_label,
                "outcome": outcome,
                "validated_in_runs": validated_in_runs,
                "health_state": _confidence_health_state(confidence_label, outcome),
            }
        )

    judged = [item for item in evaluations if item.get("outcome") != "insufficient_future_runs"]
    high_judged = [item for item in judged if item.get("confidence_label") == "high"]
    medium_judged = [item for item in judged if item.get("confidence_label") == "medium"]
    low_all = [item for item in evaluations if item.get("confidence_label") == "low"]
    high_hits = sum(1 for item in high_judged if item.get("health_state") == "healthy")
    medium_hits = sum(1 for item in medium_judged if item.get("health_state") == "healthy")
    low_cautions = sum(1 for item in low_all if item.get("health_state") == "healthy")
    reopened_high_count = sum(
        1
        for item in evaluations
        if item.get("confidence_label") == "high" and item.get("outcome") == "reopened"
    )
    high_confidence_hit_rate = round(high_hits / len(high_judged), 2) if high_judged else 0.0
    medium_confidence_hit_rate = round(medium_hits / len(medium_judged), 2) if medium_judged else 0.0
    low_confidence_caution_rate = round(low_cautions / len(low_all), 2) if low_all else 0.0
    confidence_validation_status = _confidence_validation_status(
        judged_count=len(judged),
        high_confidence_hit_rate=high_confidence_hit_rate,
        reopened_recommendation_count=sum(1 for item in judged if item.get("outcome") == "reopened"),
        reopened_high_count=reopened_high_count,
    )
    recent_validation_outcomes = [
        {
            "run_id": item.get("run_id", ""),
            "target_label": item.get("target_label", ""),
            "confidence_label": item.get("confidence_label", "low"),
            "outcome": item.get("outcome", "unresolved"),
            "validated_in_runs": item.get("validated_in_runs"),
        }
        for item in sorted(judged, key=lambda item: item.get("generated_at", ""), reverse=True)[:5]
    ]
    return {
        "confidence_validation_status": confidence_validation_status,
        "confidence_window_runs": len(ordered_runs),
        "validated_recommendation_count": sum(1 for item in evaluations if item.get("outcome") == "validated"),
        "partially_validated_recommendation_count": sum(
            1 for item in evaluations if item.get("outcome") == "partially_validated"
        ),
        "unresolved_recommendation_count": sum(1 for item in evaluations if item.get("outcome") == "unresolved"),
        "reopened_recommendation_count": sum(1 for item in evaluations if item.get("outcome") == "reopened"),
        "insufficient_future_runs_count": sum(
            1 for item in evaluations if item.get("outcome") == "insufficient_future_runs"
        ),
        "high_confidence_hit_rate": high_confidence_hit_rate,
        "medium_confidence_hit_rate": medium_confidence_hit_rate,
        "low_confidence_caution_rate": low_confidence_caution_rate,
        "recent_validation_outcomes": recent_validation_outcomes,
        "confidence_calibration_summary": _confidence_calibration_summary(
            confidence_validation_status=confidence_validation_status,
            high_confidence_hit_rate=high_confidence_hit_rate,
            medium_confidence_hit_rate=medium_confidence_hit_rate,
            low_confidence_caution_rate=low_confidence_caution_rate,
            reopened_recommendation_count=sum(1 for item in evaluations if item.get("outcome") == "reopened"),
            judged_count=len(judged),
        ),
    }


def _calibration_outcome(run: dict, future_runs: list[dict]) -> tuple[str, int | None]:
    if len(future_runs) < VALIDATION_WINDOW_RUNS:
        return "insufficient_future_runs", None
    summary = run.get("operator_summary") or {}
    target = summary.get("primary_target") or {}
    target_key = _queue_identity(target)
    original_lane = _target_lane(run, target_key, target)
    future_matches = [_run_target_match(candidate, target_key) for candidate in future_runs]
    future_lanes = [match.get("lane") if match else None for match in future_matches]
    clear_index = next(
        (
            index
            for index, lane in enumerate(future_lanes, start=1)
            if lane is None or lane not in ATTENTION_LANES
        ),
        None,
    )
    if clear_index is not None and any(
        lane in ATTENTION_LANES for lane in future_lanes[clear_index:]
    ):
        return "reopened", VALIDATION_WINDOW_RUNS
    if clear_index is not None:
        final_match = future_matches[-1]
        if final_match is None:
            return "validated", clear_index
        return "partially_validated", clear_index
    if _has_pressure_drop(original_lane, future_lanes):
        return "partially_validated", _first_pressure_drop_run(original_lane, future_lanes)
    return "unresolved", VALIDATION_WINDOW_RUNS


def _target_label(target: dict) -> str:
    repo = target.get("repo", "")
    title = target.get("title", "")
    if repo and title:
        return f"{repo}: {title}"
    return title or repo or "Operator target"


def _run_target_match(run: dict, target_key: str) -> dict | None:
    for item in run.get("operator_queue") or []:
        if _queue_identity(item) == target_key:
            return item
    return None


def _target_lane(run: dict, target_key: str, target: dict) -> str:
    match = _run_target_match(run, target_key)
    if match:
        return match.get("lane", "")
    return target.get("lane", "")


def _lane_pressure(lane: str | None) -> int:
    if lane == "blocked":
        return 3
    if lane == "urgent":
        return 2
    if lane == "ready":
        return 1
    if lane == "deferred":
        return 0
    return -1


def _has_pressure_drop(original_lane: str, future_lanes: list[str | None]) -> bool:
    origin_pressure = _lane_pressure(original_lane)
    return any(
        lane is not None and _lane_pressure(lane) < origin_pressure
        for lane in future_lanes
    )


def _first_pressure_drop_run(original_lane: str, future_lanes: list[str | None]) -> int | None:
    origin_pressure = _lane_pressure(original_lane)
    for index, lane in enumerate(future_lanes, start=1):
        if lane is not None and _lane_pressure(lane) < origin_pressure:
            return index
    return None


def _confidence_health_state(confidence_label: str, outcome: str) -> str:
    if confidence_label == "high":
        if outcome == "validated":
            return "healthy"
        if outcome in {"unresolved", "reopened"}:
            return "overstated"
        return "mixed"
    if confidence_label == "medium":
        if outcome in {"validated", "partially_validated"}:
            return "healthy"
        return "mixed"
    if confidence_label == "low":
        if outcome in {"unresolved", "reopened", "insufficient_future_runs"}:
            return "healthy"
        return "mixed"
    return "mixed"


def _confidence_validation_status(
    *,
    judged_count: int,
    high_confidence_hit_rate: float,
    reopened_recommendation_count: int,
    reopened_high_count: int,
) -> str:
    if judged_count < 4:
        return "insufficient-data"
    if high_confidence_hit_rate < 0.50 or reopened_high_count >= 2:
        return "noisy"
    if high_confidence_hit_rate >= 0.70 and reopened_recommendation_count == 0:
        return "healthy"
    return "mixed"


def _confidence_calibration_summary(
    *,
    confidence_validation_status: str,
    high_confidence_hit_rate: float,
    medium_confidence_hit_rate: float,
    low_confidence_caution_rate: float,
    reopened_recommendation_count: int,
    judged_count: int,
) -> str:
    if confidence_validation_status == "healthy":
        return (
            f"Recent high-confidence recommendations are validating well: "
            f"{high_confidence_hit_rate:.0%} high-confidence hit rate across {judged_count} judged runs with no reopen noise."
        )
    if confidence_validation_status == "mixed":
        return (
            f"Confidence is still useful, but recent outcomes are mixed: "
            f"{high_confidence_hit_rate:.0%} high-confidence hit rate, "
            f"{medium_confidence_hit_rate:.0%} medium-confidence hit rate, and {reopened_recommendation_count} reopened outcome(s)."
        )
    if confidence_validation_status == "noisy":
        return (
            f"Recent high-confidence guidance has been noisy: "
            f"{high_confidence_hit_rate:.0%} high-confidence hit rate and {reopened_recommendation_count} reopened outcome(s) in the judged window."
        )
    return (
        "The confidence model does not have enough judged history yet to say whether recent confidence has been validating. "
        f"Low-confidence caution rate so far: {low_confidence_caution_rate:.0%}."
    )


def _build_resolution_trend(
    queue: list[dict],
    history: list[dict],
    evidence_events: list[dict],
    confidence_calibration: dict,
    *,
    current_generated_at: str = "",
) -> dict:
    recent_runs = [_snapshot_from_queue(queue, generated_at=current_generated_at)] + [
        _snapshot_from_history(entry) for entry in history[: HISTORY_WINDOW_RUNS - 1]
    ]
    recent_runs = [snapshot for snapshot in recent_runs if snapshot["items"] or snapshot["has_attention"] is not None]
    current_snapshot = recent_runs[0] if recent_runs else {"items": {}, "has_attention": False}
    previous_snapshot = recent_runs[1] if len(recent_runs) > 1 else None
    current_attention = _attention_items(current_snapshot)
    previous_attention = _attention_items(previous_snapshot or {"items": {}, "has_attention": False})
    current_attention_keys = set(current_attention)
    previous_attention_keys = set(previous_attention)
    earlier_attention_keys = set().union(
        *[set(_attention_items(snapshot)) for snapshot in recent_runs[2:]]
    ) if len(recent_runs) > 2 else set()

    decision_memory_map = _decision_memory_map(recent_runs, evidence_events)
    resolution_targets = _resolution_targets(
        queue,
        recent_runs,
        decision_memory_map,
        confidence_calibration,
    )
    recommendation_drift = _apply_trust_policy_exceptions(
        resolution_targets,
        history,
        current_generated_at=current_generated_at,
        confidence_calibration=confidence_calibration,
    )
    exception_learning = _apply_exception_pattern_learning(
        resolution_targets,
        history,
        current_generated_at=current_generated_at,
        confidence_calibration=confidence_calibration,
    )
    exception_retirement = _apply_exception_retirement(
        resolution_targets,
        history,
        current_generated_at=current_generated_at,
        confidence_calibration=confidence_calibration,
    )
    class_normalization = _apply_class_trust_normalization(
        resolution_targets,
        history,
        current_generated_at=current_generated_at,
        confidence_calibration=confidence_calibration,
    )
    class_memory_decay = _apply_class_memory_decay(
        resolution_targets,
        history,
        current_generated_at=current_generated_at,
        confidence_calibration=confidence_calibration,
    )
    class_trust_reweighting = _apply_class_trust_reweighting(
        resolution_targets,
        history,
        current_generated_at=current_generated_at,
        confidence_calibration=confidence_calibration,
    )
    class_trust_momentum = _apply_class_trust_momentum(
        resolution_targets,
        history,
        current_generated_at=current_generated_at,
        confidence_calibration=confidence_calibration,
    )
    class_transition_resolution = _apply_class_transition_resolution(
        resolution_targets,
        history,
        current_generated_at=current_generated_at,
        confidence_calibration=confidence_calibration,
    )
    _apply_transition_closure_confidence(
        resolution_targets,
        history,
        current_generated_at=current_generated_at,
        confidence_calibration=confidence_calibration,
    )
    pending_debt_freshness = _apply_pending_debt_freshness_and_closure_forecast_reweighting(
        resolution_targets,
        history,
        current_generated_at=current_generated_at,
        confidence_calibration=confidence_calibration,
    )
    closure_forecast_momentum = _apply_closure_forecast_momentum_and_hysteresis(
        resolution_targets,
        history,
        current_generated_at=current_generated_at,
        confidence_calibration=confidence_calibration,
    )
    closure_forecast_decay = _apply_closure_forecast_freshness_and_decay(
        resolution_targets,
        history,
        current_generated_at=current_generated_at,
        confidence_calibration=confidence_calibration,
    )
    closure_forecast_recovery = _apply_closure_forecast_refresh_recovery_and_reacquisition(
        resolution_targets,
        history,
        current_generated_at=current_generated_at,
        confidence_calibration=confidence_calibration,
    )
    reacquisition_persistence = _apply_reacquisition_persistence_and_recovery_churn(
        resolution_targets,
        history,
        current_generated_at=current_generated_at,
        confidence_calibration=confidence_calibration,
    )
    reacquisition_freshness_decay = _apply_reacquisition_freshness_and_persistence_reset(
        resolution_targets,
        history,
        current_generated_at=current_generated_at,
        confidence_calibration=confidence_calibration,
    )
    reset_reentry_recovery = _apply_reacquisition_reset_refresh_recovery_and_reentry(
        resolution_targets,
        history,
        current_generated_at=current_generated_at,
        confidence_calibration=confidence_calibration,
    )
    reset_reentry_persistence = _apply_reset_reentry_persistence_and_churn(
        resolution_targets,
        history,
        current_generated_at=current_generated_at,
        confidence_calibration=confidence_calibration,
    )
    reset_reentry_freshness_decay = _apply_reset_reentry_freshness_and_reset(
        resolution_targets,
        history,
        current_generated_at=current_generated_at,
        confidence_calibration=confidence_calibration,
    )
    reset_reentry_rebuild = _apply_reset_reentry_refresh_recovery_and_rebuild(
        resolution_targets,
        history,
        current_generated_at=current_generated_at,
        confidence_calibration=confidence_calibration,
    )
    reset_reentry_rebuild_persistence = _apply_reset_reentry_rebuild_persistence_and_churn(
        resolution_targets,
        history,
        current_generated_at=current_generated_at,
        confidence_calibration=confidence_calibration,
    )
    reset_reentry_rebuild_freshness_decay = _apply_reset_reentry_rebuild_freshness_and_reset(
        resolution_targets,
        history,
        current_generated_at=current_generated_at,
        confidence_calibration=confidence_calibration,
    )
    new_attention_keys = current_attention_keys - previous_attention_keys
    resolved_attention_count = len(previous_attention_keys - current_attention_keys)
    persisting_attention_count = len(current_attention_keys & previous_attention_keys)
    reopened_attention_count = len(
        {
            key
            for key in new_attention_keys
            if key in earlier_attention_keys
        }
    )
    new_blocked_attention = any(
        current_attention.get(key, {}).get("lane") == "blocked"
        for key in new_attention_keys
    )
    current_attention_count = len(current_attention_keys)
    previous_attention_count = len(previous_attention_keys)

    quiet_streak_runs = 0
    for snapshot in recent_runs:
        if snapshot["has_attention"]:
            break
        quiet_streak_runs += 1

    trend_status = _trend_status(
        current_attention_count=current_attention_count,
        previous_attention_count=previous_attention_count,
        new_blocked_attention=new_blocked_attention,
        quiet_streak_runs=quiet_streak_runs,
        has_previous=previous_snapshot is not None,
    )
    primary_target = _primary_target(resolution_targets)
    primary_target_reason = _primary_target_reason(primary_target)
    primary_target_done_criteria = _primary_target_done_criteria(primary_target)
    closure_guidance = _closure_guidance(primary_target, primary_target_done_criteria)
    accountability_summary = _accountability_summary(
        primary_target=primary_target,
        primary_target_reason=primary_target_reason,
        closure_guidance=closure_guidance,
        chronic_item_count=sum(1 for item in resolution_targets if item.get("aging_status") == "chronic"),
        newly_stale_count=sum(1 for item in resolution_targets if item.get("newly_stale")),
        quiet_streak_runs=quiet_streak_runs,
    )
    if primary_target:
        primary_target = {
            **primary_target,
            "reason": primary_target_reason,
            "done_criteria": primary_target_done_criteria,
            "closure_guidance": closure_guidance,
            "recommendation_drift_status": recommendation_drift["recommendation_drift_status"],
        }
    decision_memory = _summary_decision_memory(primary_target, decision_memory_map, recent_runs)
    trend_summary = _trend_summary(
        trend_status=trend_status,
        quiet_streak_runs=quiet_streak_runs,
        new_attention_count=len(new_attention_keys),
        resolved_attention_count=resolved_attention_count,
        persisting_attention_count=persisting_attention_count,
        reopened_attention_count=reopened_attention_count,
        primary_target=primary_target,
    )
    return {
        "trend_status": trend_status,
        "new_attention_count": len(new_attention_keys),
        "resolved_attention_count": resolved_attention_count,
        "persisting_attention_count": persisting_attention_count,
        "reopened_attention_count": reopened_attention_count,
        "history_window_runs": len(recent_runs),
        "quiet_streak_runs": quiet_streak_runs,
        "aging_status": primary_target.get("aging_status", "fresh") if primary_target else "fresh",
        "primary_target_reason": primary_target_reason,
        "primary_target_done_criteria": primary_target_done_criteria,
        "closure_guidance": closure_guidance,
        "attention_age_bands": _attention_age_bands(current_attention),
        "chronic_item_count": sum(1 for item in resolution_targets if item.get("aging_status") == "chronic"),
        "newly_stale_count": sum(1 for item in resolution_targets if item.get("newly_stale")),
        "longest_persisting_item": _longest_persisting_item(resolution_targets),
        "accountability_summary": accountability_summary,
        "primary_target": primary_target,
        "resolution_targets": resolution_targets[:5],
        "trend_summary": trend_summary,
        "primary_target_exception_status": recommendation_drift["primary_target_exception_status"],
        "primary_target_exception_reason": recommendation_drift["primary_target_exception_reason"],
        "recommendation_drift_status": recommendation_drift["recommendation_drift_status"],
        "recommendation_drift_summary": recommendation_drift["recommendation_drift_summary"],
        "policy_flip_hotspots": recommendation_drift["policy_flip_hotspots"],
        "primary_target_exception_pattern_status": exception_learning["primary_target_exception_pattern_status"],
        "primary_target_exception_pattern_reason": exception_learning["primary_target_exception_pattern_reason"],
        "primary_target_trust_recovery_status": exception_learning["primary_target_trust_recovery_status"],
        "primary_target_trust_recovery_reason": exception_learning["primary_target_trust_recovery_reason"],
        "exception_pattern_summary": exception_learning["exception_pattern_summary"],
        "false_positive_exception_hotspots": exception_learning["false_positive_exception_hotspots"],
        "trust_recovery_window_runs": exception_learning["trust_recovery_window_runs"],
        "primary_target_recovery_confidence_score": exception_retirement["primary_target_recovery_confidence_score"],
        "primary_target_recovery_confidence_label": exception_retirement["primary_target_recovery_confidence_label"],
        "primary_target_recovery_confidence_reasons": exception_retirement["primary_target_recovery_confidence_reasons"],
        "recovery_confidence_summary": exception_retirement["recovery_confidence_summary"],
        "primary_target_exception_retirement_status": exception_retirement["primary_target_exception_retirement_status"],
        "primary_target_exception_retirement_reason": exception_retirement["primary_target_exception_retirement_reason"],
        "exception_retirement_summary": exception_retirement["exception_retirement_summary"],
        "retired_exception_hotspots": exception_retirement["retired_exception_hotspots"],
        "sticky_exception_hotspots": exception_retirement["sticky_exception_hotspots"],
        "exception_retirement_window_runs": exception_retirement["exception_retirement_window_runs"],
        "primary_target_policy_debt_status": primary_target.get("policy_debt_status", class_normalization["primary_target_policy_debt_status"]) if primary_target else class_normalization["primary_target_policy_debt_status"],
        "primary_target_policy_debt_reason": primary_target.get("policy_debt_reason", class_normalization["primary_target_policy_debt_reason"]) if primary_target else class_normalization["primary_target_policy_debt_reason"],
        "primary_target_class_normalization_status": primary_target.get("class_normalization_status", class_normalization["primary_target_class_normalization_status"]) if primary_target else class_normalization["primary_target_class_normalization_status"],
        "primary_target_class_normalization_reason": primary_target.get("class_normalization_reason", class_normalization["primary_target_class_normalization_reason"]) if primary_target else class_normalization["primary_target_class_normalization_reason"],
        "policy_debt_summary": _policy_debt_summary(primary_target, class_normalization["policy_debt_hotspots"]) if primary_target else class_normalization["policy_debt_summary"],
        "trust_normalization_summary": _trust_normalization_summary(
            primary_target,
            class_normalization["normalized_class_hotspots"],
            class_normalization["policy_debt_hotspots"],
        ) if primary_target else class_normalization["trust_normalization_summary"],
        "policy_debt_hotspots": class_normalization["policy_debt_hotspots"],
        "normalized_class_hotspots": class_normalization["normalized_class_hotspots"],
        "class_normalization_window_runs": class_normalization["class_normalization_window_runs"],
        "primary_target_class_memory_freshness_status": class_memory_decay["primary_target_class_memory_freshness_status"],
        "primary_target_class_memory_freshness_reason": class_memory_decay["primary_target_class_memory_freshness_reason"],
        "primary_target_class_decay_status": class_memory_decay["primary_target_class_decay_status"],
        "primary_target_class_decay_reason": class_memory_decay["primary_target_class_decay_reason"],
        "class_memory_summary": class_memory_decay["class_memory_summary"],
        "class_decay_summary": class_memory_decay["class_decay_summary"],
        "stale_class_memory_hotspots": class_memory_decay["stale_class_memory_hotspots"],
        "fresh_class_signal_hotspots": class_memory_decay["fresh_class_signal_hotspots"],
        "class_decay_window_runs": class_memory_decay["class_decay_window_runs"],
        "primary_target_weighted_class_support_score": class_trust_reweighting["primary_target_weighted_class_support_score"],
        "primary_target_weighted_class_caution_score": class_trust_reweighting["primary_target_weighted_class_caution_score"],
        "primary_target_class_trust_reweight_score": class_trust_reweighting["primary_target_class_trust_reweight_score"],
        "primary_target_class_trust_reweight_direction": class_trust_reweighting["primary_target_class_trust_reweight_direction"],
        "primary_target_class_trust_reweight_reasons": class_trust_reweighting["primary_target_class_trust_reweight_reasons"],
        "class_reweighting_summary": class_trust_reweighting["class_reweighting_summary"],
        "supporting_class_hotspots": class_trust_reweighting["supporting_class_hotspots"],
        "caution_class_hotspots": class_trust_reweighting["caution_class_hotspots"],
        "class_reweighting_window_runs": class_trust_reweighting["class_reweighting_window_runs"],
        "primary_target_class_trust_momentum_score": class_trust_momentum["primary_target_class_trust_momentum_score"],
        "primary_target_class_trust_momentum_status": class_trust_momentum["primary_target_class_trust_momentum_status"],
        "primary_target_class_reweight_stability_status": class_trust_momentum["primary_target_class_reweight_stability_status"],
        "primary_target_class_reweight_transition_status": class_trust_momentum["primary_target_class_reweight_transition_status"],
        "primary_target_class_reweight_transition_reason": class_trust_momentum["primary_target_class_reweight_transition_reason"],
        "class_momentum_summary": class_trust_momentum["class_momentum_summary"],
        "class_reweight_stability_summary": class_trust_momentum["class_reweight_stability_summary"],
        "class_transition_window_runs": class_trust_momentum["class_transition_window_runs"],
        "primary_target_class_transition_health_status": primary_target.get("class_transition_health_status", class_transition_resolution["primary_target_class_transition_health_status"]) if primary_target else class_transition_resolution["primary_target_class_transition_health_status"],
        "primary_target_class_transition_health_reason": primary_target.get("class_transition_health_reason", class_transition_resolution["primary_target_class_transition_health_reason"]) if primary_target else class_transition_resolution["primary_target_class_transition_health_reason"],
        "primary_target_class_transition_resolution_status": primary_target.get("class_transition_resolution_status", class_transition_resolution["primary_target_class_transition_resolution_status"]) if primary_target else class_transition_resolution["primary_target_class_transition_resolution_status"],
        "primary_target_class_transition_resolution_reason": primary_target.get("class_transition_resolution_reason", class_transition_resolution["primary_target_class_transition_resolution_reason"]) if primary_target else class_transition_resolution["primary_target_class_transition_resolution_reason"],
        "class_transition_health_summary": _class_transition_health_summary(
            primary_target,
            class_transition_resolution["stalled_transition_hotspots"],
        ) if primary_target else class_transition_resolution["class_transition_health_summary"],
        "class_transition_resolution_summary": _class_transition_resolution_summary(
            primary_target,
            class_transition_resolution["resolving_transition_hotspots"],
            class_transition_resolution["stalled_transition_hotspots"],
        ) if primary_target else class_transition_resolution["class_transition_resolution_summary"],
        "class_transition_age_window_runs": class_transition_resolution["class_transition_age_window_runs"],
        "stalled_transition_hotspots": class_transition_resolution["stalled_transition_hotspots"],
        "resolving_transition_hotspots": class_transition_resolution["resolving_transition_hotspots"],
        "primary_target_transition_closure_confidence_score": primary_target.get("transition_closure_confidence_score", pending_debt_freshness["primary_target_transition_closure_confidence_score"]) if primary_target else pending_debt_freshness["primary_target_transition_closure_confidence_score"],
        "primary_target_transition_closure_confidence_label": primary_target.get("transition_closure_confidence_label", pending_debt_freshness["primary_target_transition_closure_confidence_label"]) if primary_target else pending_debt_freshness["primary_target_transition_closure_confidence_label"],
        "primary_target_transition_closure_likely_outcome": primary_target.get("transition_closure_likely_outcome", closure_forecast_momentum["primary_target_transition_closure_likely_outcome"]) if primary_target else closure_forecast_momentum["primary_target_transition_closure_likely_outcome"],
        "primary_target_transition_closure_confidence_reasons": primary_target.get("transition_closure_confidence_reasons", pending_debt_freshness["primary_target_transition_closure_confidence_reasons"]) if primary_target else pending_debt_freshness["primary_target_transition_closure_confidence_reasons"],
        "transition_closure_confidence_summary": closure_forecast_momentum["transition_closure_confidence_summary"],
        "transition_closure_window_runs": pending_debt_freshness["transition_closure_window_runs"],
        "primary_target_class_pending_debt_status": primary_target.get("class_pending_debt_status", pending_debt_freshness["primary_target_class_pending_debt_status"]) if primary_target else pending_debt_freshness["primary_target_class_pending_debt_status"],
        "primary_target_class_pending_debt_reason": primary_target.get("class_pending_debt_reason", pending_debt_freshness["primary_target_class_pending_debt_reason"]) if primary_target else pending_debt_freshness["primary_target_class_pending_debt_reason"],
        "class_pending_debt_summary": closure_forecast_momentum["class_pending_debt_summary"],
        "class_pending_resolution_summary": closure_forecast_momentum["class_pending_resolution_summary"],
        "class_pending_debt_window_runs": pending_debt_freshness["class_pending_debt_window_runs"],
        "pending_debt_hotspots": pending_debt_freshness["pending_debt_hotspots"],
        "healthy_pending_resolution_hotspots": pending_debt_freshness["healthy_pending_resolution_hotspots"],
        "primary_target_pending_debt_freshness_status": primary_target.get("pending_debt_freshness_status", pending_debt_freshness["primary_target_pending_debt_freshness_status"]) if primary_target else pending_debt_freshness["primary_target_pending_debt_freshness_status"],
        "primary_target_pending_debt_freshness_reason": primary_target.get("pending_debt_freshness_reason", pending_debt_freshness["primary_target_pending_debt_freshness_reason"]) if primary_target else pending_debt_freshness["primary_target_pending_debt_freshness_reason"],
        "pending_debt_freshness_summary": closure_forecast_momentum["pending_debt_freshness_summary"],
        "pending_debt_decay_summary": closure_forecast_momentum["pending_debt_decay_summary"],
        "stale_pending_debt_hotspots": pending_debt_freshness["stale_pending_debt_hotspots"],
        "fresh_pending_resolution_hotspots": pending_debt_freshness["fresh_pending_resolution_hotspots"],
        "pending_debt_decay_window_runs": pending_debt_freshness["pending_debt_decay_window_runs"],
        "primary_target_weighted_pending_resolution_support_score": primary_target.get("weighted_pending_resolution_support_score", pending_debt_freshness["primary_target_weighted_pending_resolution_support_score"]) if primary_target else pending_debt_freshness["primary_target_weighted_pending_resolution_support_score"],
        "primary_target_weighted_pending_debt_caution_score": primary_target.get("weighted_pending_debt_caution_score", pending_debt_freshness["primary_target_weighted_pending_debt_caution_score"]) if primary_target else pending_debt_freshness["primary_target_weighted_pending_debt_caution_score"],
        "primary_target_closure_forecast_reweight_score": primary_target.get("closure_forecast_reweight_score", pending_debt_freshness["primary_target_closure_forecast_reweight_score"]) if primary_target else pending_debt_freshness["primary_target_closure_forecast_reweight_score"],
        "primary_target_closure_forecast_reweight_direction": primary_target.get("closure_forecast_reweight_direction", pending_debt_freshness["primary_target_closure_forecast_reweight_direction"]) if primary_target else pending_debt_freshness["primary_target_closure_forecast_reweight_direction"],
        "primary_target_closure_forecast_reweight_reasons": primary_target.get("closure_forecast_reweight_reasons", pending_debt_freshness["primary_target_closure_forecast_reweight_reasons"]) if primary_target else pending_debt_freshness["primary_target_closure_forecast_reweight_reasons"],
        "closure_forecast_reweighting_summary": closure_forecast_momentum["closure_forecast_reweighting_summary"],
        "closure_forecast_reweighting_window_runs": pending_debt_freshness["closure_forecast_reweighting_window_runs"],
        "supporting_pending_resolution_hotspots": pending_debt_freshness["supporting_pending_resolution_hotspots"],
        "caution_pending_debt_hotspots": pending_debt_freshness["caution_pending_debt_hotspots"],
        "primary_target_closure_forecast_momentum_score": closure_forecast_momentum["primary_target_closure_forecast_momentum_score"],
        "primary_target_closure_forecast_momentum_status": closure_forecast_momentum["primary_target_closure_forecast_momentum_status"],
        "primary_target_closure_forecast_stability_status": closure_forecast_momentum["primary_target_closure_forecast_stability_status"],
        "primary_target_closure_forecast_hysteresis_status": primary_target.get("closure_forecast_hysteresis_status", closure_forecast_momentum["primary_target_closure_forecast_hysteresis_status"]) if primary_target else closure_forecast_momentum["primary_target_closure_forecast_hysteresis_status"],
        "primary_target_closure_forecast_hysteresis_reason": primary_target.get("closure_forecast_hysteresis_reason", closure_forecast_momentum["primary_target_closure_forecast_hysteresis_reason"]) if primary_target else closure_forecast_momentum["primary_target_closure_forecast_hysteresis_reason"],
        "closure_forecast_momentum_summary": closure_forecast_momentum["closure_forecast_momentum_summary"],
        "closure_forecast_stability_summary": closure_forecast_momentum["closure_forecast_stability_summary"],
        "closure_forecast_hysteresis_summary": _closure_forecast_hysteresis_summary(
            primary_target,
            closure_forecast_momentum["sustained_confirmation_hotspots"],
            closure_forecast_momentum["sustained_clearance_hotspots"],
        ) if primary_target else closure_forecast_momentum["closure_forecast_hysteresis_summary"],
        "closure_forecast_transition_window_runs": closure_forecast_momentum["closure_forecast_transition_window_runs"],
        "sustained_confirmation_hotspots": closure_forecast_momentum["sustained_confirmation_hotspots"],
        "sustained_clearance_hotspots": closure_forecast_momentum["sustained_clearance_hotspots"],
        "oscillating_closure_forecast_hotspots": closure_forecast_momentum["oscillating_closure_forecast_hotspots"],
        "primary_target_closure_forecast_freshness_status": closure_forecast_decay["primary_target_closure_forecast_freshness_status"],
        "primary_target_closure_forecast_freshness_reason": closure_forecast_decay["primary_target_closure_forecast_freshness_reason"],
        "primary_target_closure_forecast_decay_status": closure_forecast_decay["primary_target_closure_forecast_decay_status"],
        "primary_target_closure_forecast_decay_reason": closure_forecast_decay["primary_target_closure_forecast_decay_reason"],
        "closure_forecast_freshness_summary": closure_forecast_decay["closure_forecast_freshness_summary"],
        "closure_forecast_decay_summary": closure_forecast_decay["closure_forecast_decay_summary"],
        "stale_closure_forecast_hotspots": closure_forecast_decay["stale_closure_forecast_hotspots"],
        "fresh_closure_forecast_signal_hotspots": closure_forecast_decay["fresh_closure_forecast_signal_hotspots"],
        "closure_forecast_decay_window_runs": closure_forecast_decay["closure_forecast_decay_window_runs"],
        "primary_target_closure_forecast_refresh_recovery_score": closure_forecast_recovery["primary_target_closure_forecast_refresh_recovery_score"],
        "primary_target_closure_forecast_refresh_recovery_status": closure_forecast_recovery["primary_target_closure_forecast_refresh_recovery_status"],
        "primary_target_closure_forecast_reacquisition_status": primary_target.get("closure_forecast_reacquisition_status", closure_forecast_recovery["primary_target_closure_forecast_reacquisition_status"]) if primary_target else closure_forecast_recovery["primary_target_closure_forecast_reacquisition_status"],
        "primary_target_closure_forecast_reacquisition_reason": primary_target.get("closure_forecast_reacquisition_reason", closure_forecast_recovery["primary_target_closure_forecast_reacquisition_reason"]) if primary_target else closure_forecast_recovery["primary_target_closure_forecast_reacquisition_reason"],
        "closure_forecast_refresh_recovery_summary": closure_forecast_recovery["closure_forecast_refresh_recovery_summary"],
        "closure_forecast_reacquisition_summary": closure_forecast_recovery["closure_forecast_reacquisition_summary"],
        "closure_forecast_refresh_window_runs": closure_forecast_recovery["closure_forecast_refresh_window_runs"],
        "recovering_confirmation_hotspots": closure_forecast_recovery["recovering_confirmation_hotspots"],
        "recovering_clearance_hotspots": closure_forecast_recovery["recovering_clearance_hotspots"],
        "primary_target_closure_forecast_reacquisition_age_runs": primary_target.get("closure_forecast_reacquisition_age_runs", reacquisition_persistence["primary_target_closure_forecast_reacquisition_age_runs"]) if primary_target else reacquisition_persistence["primary_target_closure_forecast_reacquisition_age_runs"],
        "primary_target_closure_forecast_reacquisition_persistence_score": primary_target.get("closure_forecast_reacquisition_persistence_score", reacquisition_persistence["primary_target_closure_forecast_reacquisition_persistence_score"]) if primary_target else reacquisition_persistence["primary_target_closure_forecast_reacquisition_persistence_score"],
        "primary_target_closure_forecast_reacquisition_persistence_status": primary_target.get("closure_forecast_reacquisition_persistence_status", reacquisition_persistence["primary_target_closure_forecast_reacquisition_persistence_status"]) if primary_target else reacquisition_persistence["primary_target_closure_forecast_reacquisition_persistence_status"],
        "primary_target_closure_forecast_reacquisition_persistence_reason": primary_target.get("closure_forecast_reacquisition_persistence_reason", reacquisition_persistence["primary_target_closure_forecast_reacquisition_persistence_reason"]) if primary_target else reacquisition_persistence["primary_target_closure_forecast_reacquisition_persistence_reason"],
        "closure_forecast_reacquisition_persistence_summary": reacquisition_persistence["closure_forecast_reacquisition_persistence_summary"],
        "closure_forecast_reacquisition_window_runs": reacquisition_persistence["closure_forecast_reacquisition_window_runs"],
        "just_reacquired_hotspots": reacquisition_persistence["just_reacquired_hotspots"],
        "holding_reacquisition_hotspots": reacquisition_persistence["holding_reacquisition_hotspots"],
        "primary_target_closure_forecast_recovery_churn_score": primary_target.get("closure_forecast_recovery_churn_score", reacquisition_persistence["primary_target_closure_forecast_recovery_churn_score"]) if primary_target else reacquisition_persistence["primary_target_closure_forecast_recovery_churn_score"],
        "primary_target_closure_forecast_recovery_churn_status": primary_target.get("closure_forecast_recovery_churn_status", reacquisition_persistence["primary_target_closure_forecast_recovery_churn_status"]) if primary_target else reacquisition_persistence["primary_target_closure_forecast_recovery_churn_status"],
        "primary_target_closure_forecast_recovery_churn_reason": primary_target.get("closure_forecast_recovery_churn_reason", reacquisition_persistence["primary_target_closure_forecast_recovery_churn_reason"]) if primary_target else reacquisition_persistence["primary_target_closure_forecast_recovery_churn_reason"],
        "closure_forecast_recovery_churn_summary": reacquisition_persistence["closure_forecast_recovery_churn_summary"],
        "recovery_churn_hotspots": reacquisition_persistence["recovery_churn_hotspots"],
        "primary_target_closure_forecast_reacquisition_freshness_status": reacquisition_freshness_decay["primary_target_closure_forecast_reacquisition_freshness_status"],
        "primary_target_closure_forecast_reacquisition_freshness_reason": reacquisition_freshness_decay["primary_target_closure_forecast_reacquisition_freshness_reason"],
        "closure_forecast_reacquisition_freshness_summary": reacquisition_freshness_decay["closure_forecast_reacquisition_freshness_summary"],
        "primary_target_closure_forecast_persistence_reset_status": reacquisition_freshness_decay["primary_target_closure_forecast_persistence_reset_status"],
        "primary_target_closure_forecast_persistence_reset_reason": reacquisition_freshness_decay["primary_target_closure_forecast_persistence_reset_reason"],
        "closure_forecast_persistence_reset_summary": reacquisition_freshness_decay["closure_forecast_persistence_reset_summary"],
        "stale_reacquisition_hotspots": reacquisition_freshness_decay["stale_reacquisition_hotspots"],
        "fresh_reacquisition_signal_hotspots": reacquisition_freshness_decay["fresh_reacquisition_signal_hotspots"],
        "closure_forecast_reacquisition_decay_window_runs": reacquisition_freshness_decay["closure_forecast_reacquisition_decay_window_runs"],
        "primary_target_closure_forecast_reset_refresh_recovery_score": primary_target.get("closure_forecast_reset_refresh_recovery_score", reset_reentry_recovery["primary_target_closure_forecast_reset_refresh_recovery_score"]) if primary_target else reset_reentry_recovery["primary_target_closure_forecast_reset_refresh_recovery_score"],
        "primary_target_closure_forecast_reset_refresh_recovery_status": primary_target.get("closure_forecast_reset_refresh_recovery_status", reset_reentry_recovery["primary_target_closure_forecast_reset_refresh_recovery_status"]) if primary_target else reset_reentry_recovery["primary_target_closure_forecast_reset_refresh_recovery_status"],
        "primary_target_closure_forecast_reset_reentry_status": primary_target.get("closure_forecast_reset_reentry_status", reset_reentry_recovery["primary_target_closure_forecast_reset_reentry_status"]) if primary_target else reset_reentry_recovery["primary_target_closure_forecast_reset_reentry_status"],
        "primary_target_closure_forecast_reset_reentry_reason": primary_target.get("closure_forecast_reset_reentry_reason", reset_reentry_recovery["primary_target_closure_forecast_reset_reentry_reason"]) if primary_target else reset_reentry_recovery["primary_target_closure_forecast_reset_reentry_reason"],
        "closure_forecast_reset_refresh_recovery_summary": reset_reentry_recovery["closure_forecast_reset_refresh_recovery_summary"],
        "closure_forecast_reset_reentry_summary": reset_reentry_recovery["closure_forecast_reset_reentry_summary"],
        "closure_forecast_reset_refresh_window_runs": reset_reentry_recovery["closure_forecast_reset_refresh_window_runs"],
        "recovering_from_confirmation_reset_hotspots": reset_reentry_recovery["recovering_from_confirmation_reset_hotspots"],
        "recovering_from_clearance_reset_hotspots": reset_reentry_recovery["recovering_from_clearance_reset_hotspots"],
        "primary_target_closure_forecast_reset_reentry_age_runs": primary_target.get("closure_forecast_reset_reentry_age_runs", reset_reentry_persistence["primary_target_closure_forecast_reset_reentry_age_runs"]) if primary_target else reset_reentry_persistence["primary_target_closure_forecast_reset_reentry_age_runs"],
        "primary_target_closure_forecast_reset_reentry_persistence_score": primary_target.get("closure_forecast_reset_reentry_persistence_score", reset_reentry_persistence["primary_target_closure_forecast_reset_reentry_persistence_score"]) if primary_target else reset_reentry_persistence["primary_target_closure_forecast_reset_reentry_persistence_score"],
        "primary_target_closure_forecast_reset_reentry_persistence_status": primary_target.get("closure_forecast_reset_reentry_persistence_status", reset_reentry_persistence["primary_target_closure_forecast_reset_reentry_persistence_status"]) if primary_target else reset_reentry_persistence["primary_target_closure_forecast_reset_reentry_persistence_status"],
        "primary_target_closure_forecast_reset_reentry_persistence_reason": primary_target.get("closure_forecast_reset_reentry_persistence_reason", reset_reentry_persistence["primary_target_closure_forecast_reset_reentry_persistence_reason"]) if primary_target else reset_reentry_persistence["primary_target_closure_forecast_reset_reentry_persistence_reason"],
        "closure_forecast_reset_reentry_persistence_summary": reset_reentry_persistence["closure_forecast_reset_reentry_persistence_summary"],
        "closure_forecast_reset_reentry_window_runs": reset_reentry_persistence["closure_forecast_reset_reentry_window_runs"],
        "just_reentered_hotspots": reset_reentry_persistence["just_reentered_hotspots"],
        "holding_reset_reentry_hotspots": reset_reentry_persistence["holding_reset_reentry_hotspots"],
        "primary_target_closure_forecast_reset_reentry_churn_score": primary_target.get("closure_forecast_reset_reentry_churn_score", reset_reentry_persistence["primary_target_closure_forecast_reset_reentry_churn_score"]) if primary_target else reset_reentry_persistence["primary_target_closure_forecast_reset_reentry_churn_score"],
        "primary_target_closure_forecast_reset_reentry_churn_status": primary_target.get("closure_forecast_reset_reentry_churn_status", reset_reentry_persistence["primary_target_closure_forecast_reset_reentry_churn_status"]) if primary_target else reset_reentry_persistence["primary_target_closure_forecast_reset_reentry_churn_status"],
        "primary_target_closure_forecast_reset_reentry_churn_reason": primary_target.get("closure_forecast_reset_reentry_churn_reason", reset_reentry_persistence["primary_target_closure_forecast_reset_reentry_churn_reason"]) if primary_target else reset_reentry_persistence["primary_target_closure_forecast_reset_reentry_churn_reason"],
        "closure_forecast_reset_reentry_churn_summary": reset_reentry_persistence["closure_forecast_reset_reentry_churn_summary"],
        "reset_reentry_churn_hotspots": reset_reentry_persistence["reset_reentry_churn_hotspots"],
        "primary_target_closure_forecast_reset_reentry_freshness_status": primary_target.get("closure_forecast_reset_reentry_freshness_status", reset_reentry_freshness_decay["primary_target_closure_forecast_reset_reentry_freshness_status"]) if primary_target else reset_reentry_freshness_decay["primary_target_closure_forecast_reset_reentry_freshness_status"],
        "primary_target_closure_forecast_reset_reentry_freshness_reason": primary_target.get("closure_forecast_reset_reentry_freshness_reason", reset_reentry_freshness_decay["primary_target_closure_forecast_reset_reentry_freshness_reason"]) if primary_target else reset_reentry_freshness_decay["primary_target_closure_forecast_reset_reentry_freshness_reason"],
        "closure_forecast_reset_reentry_freshness_summary": reset_reentry_freshness_decay["closure_forecast_reset_reentry_freshness_summary"],
        "primary_target_closure_forecast_reset_reentry_reset_status": primary_target.get("closure_forecast_reset_reentry_reset_status", reset_reentry_freshness_decay["primary_target_closure_forecast_reset_reentry_reset_status"]) if primary_target else reset_reentry_freshness_decay["primary_target_closure_forecast_reset_reentry_reset_status"],
        "primary_target_closure_forecast_reset_reentry_reset_reason": primary_target.get("closure_forecast_reset_reentry_reset_reason", reset_reentry_freshness_decay["primary_target_closure_forecast_reset_reentry_reset_reason"]) if primary_target else reset_reentry_freshness_decay["primary_target_closure_forecast_reset_reentry_reset_reason"],
        "closure_forecast_reset_reentry_reset_summary": reset_reentry_freshness_decay["closure_forecast_reset_reentry_reset_summary"],
        "stale_reset_reentry_hotspots": reset_reentry_freshness_decay["stale_reset_reentry_hotspots"],
        "fresh_reset_reentry_signal_hotspots": reset_reentry_freshness_decay["fresh_reset_reentry_signal_hotspots"],
        "closure_forecast_reset_reentry_decay_window_runs": reset_reentry_freshness_decay["closure_forecast_reset_reentry_decay_window_runs"],
        "primary_target_closure_forecast_reset_reentry_refresh_recovery_score": primary_target.get("closure_forecast_reset_reentry_refresh_recovery_score", reset_reentry_rebuild["primary_target_closure_forecast_reset_reentry_refresh_recovery_score"]) if primary_target else reset_reentry_rebuild["primary_target_closure_forecast_reset_reentry_refresh_recovery_score"],
        "primary_target_closure_forecast_reset_reentry_refresh_recovery_status": primary_target.get("closure_forecast_reset_reentry_refresh_recovery_status", reset_reentry_rebuild["primary_target_closure_forecast_reset_reentry_refresh_recovery_status"]) if primary_target else reset_reentry_rebuild["primary_target_closure_forecast_reset_reentry_refresh_recovery_status"],
        "primary_target_closure_forecast_reset_reentry_rebuild_status": primary_target.get("closure_forecast_reset_reentry_rebuild_status", reset_reentry_rebuild["primary_target_closure_forecast_reset_reentry_rebuild_status"]) if primary_target else reset_reentry_rebuild["primary_target_closure_forecast_reset_reentry_rebuild_status"],
        "primary_target_closure_forecast_reset_reentry_rebuild_reason": primary_target.get("closure_forecast_reset_reentry_rebuild_reason", reset_reentry_rebuild["primary_target_closure_forecast_reset_reentry_rebuild_reason"]) if primary_target else reset_reentry_rebuild["primary_target_closure_forecast_reset_reentry_rebuild_reason"],
        "closure_forecast_reset_reentry_refresh_recovery_summary": reset_reentry_rebuild["closure_forecast_reset_reentry_refresh_recovery_summary"],
        "closure_forecast_reset_reentry_rebuild_summary": reset_reentry_rebuild["closure_forecast_reset_reentry_rebuild_summary"],
        "closure_forecast_reset_reentry_refresh_window_runs": reset_reentry_rebuild["closure_forecast_reset_reentry_refresh_window_runs"],
        "recovering_from_confirmation_reentry_reset_hotspots": reset_reentry_rebuild["recovering_from_confirmation_reentry_reset_hotspots"],
        "recovering_from_clearance_reentry_reset_hotspots": reset_reentry_rebuild["recovering_from_clearance_reentry_reset_hotspots"],
        "primary_target_closure_forecast_reset_reentry_rebuild_age_runs": primary_target.get("closure_forecast_reset_reentry_rebuild_age_runs", reset_reentry_rebuild_persistence["primary_target_closure_forecast_reset_reentry_rebuild_age_runs"]) if primary_target else reset_reentry_rebuild_persistence["primary_target_closure_forecast_reset_reentry_rebuild_age_runs"],
        "primary_target_closure_forecast_reset_reentry_rebuild_persistence_score": primary_target.get("closure_forecast_reset_reentry_rebuild_persistence_score", reset_reentry_rebuild_persistence["primary_target_closure_forecast_reset_reentry_rebuild_persistence_score"]) if primary_target else reset_reentry_rebuild_persistence["primary_target_closure_forecast_reset_reentry_rebuild_persistence_score"],
        "primary_target_closure_forecast_reset_reentry_rebuild_persistence_status": primary_target.get("closure_forecast_reset_reentry_rebuild_persistence_status", reset_reentry_rebuild_persistence["primary_target_closure_forecast_reset_reentry_rebuild_persistence_status"]) if primary_target else reset_reentry_rebuild_persistence["primary_target_closure_forecast_reset_reentry_rebuild_persistence_status"],
        "primary_target_closure_forecast_reset_reentry_rebuild_persistence_reason": primary_target.get("closure_forecast_reset_reentry_rebuild_persistence_reason", reset_reentry_rebuild_persistence["primary_target_closure_forecast_reset_reentry_rebuild_persistence_reason"]) if primary_target else reset_reentry_rebuild_persistence["primary_target_closure_forecast_reset_reentry_rebuild_persistence_reason"],
        "closure_forecast_reset_reentry_rebuild_persistence_summary": reset_reentry_rebuild_persistence["closure_forecast_reset_reentry_rebuild_persistence_summary"],
        "closure_forecast_reset_reentry_rebuild_window_runs": reset_reentry_rebuild_persistence["closure_forecast_reset_reentry_rebuild_window_runs"],
        "just_rebuilt_hotspots": reset_reentry_rebuild_persistence["just_rebuilt_hotspots"],
        "holding_reset_reentry_rebuild_hotspots": reset_reentry_rebuild_persistence["holding_reset_reentry_rebuild_hotspots"],
        "primary_target_closure_forecast_reset_reentry_rebuild_churn_score": primary_target.get("closure_forecast_reset_reentry_rebuild_churn_score", reset_reentry_rebuild_persistence["primary_target_closure_forecast_reset_reentry_rebuild_churn_score"]) if primary_target else reset_reentry_rebuild_persistence["primary_target_closure_forecast_reset_reentry_rebuild_churn_score"],
        "primary_target_closure_forecast_reset_reentry_rebuild_churn_status": primary_target.get("closure_forecast_reset_reentry_rebuild_churn_status", reset_reentry_rebuild_persistence["primary_target_closure_forecast_reset_reentry_rebuild_churn_status"]) if primary_target else reset_reentry_rebuild_persistence["primary_target_closure_forecast_reset_reentry_rebuild_churn_status"],
        "primary_target_closure_forecast_reset_reentry_rebuild_churn_reason": primary_target.get("closure_forecast_reset_reentry_rebuild_churn_reason", reset_reentry_rebuild_persistence["primary_target_closure_forecast_reset_reentry_rebuild_churn_reason"]) if primary_target else reset_reentry_rebuild_persistence["primary_target_closure_forecast_reset_reentry_rebuild_churn_reason"],
        "closure_forecast_reset_reentry_rebuild_churn_summary": reset_reentry_rebuild_persistence["closure_forecast_reset_reentry_rebuild_churn_summary"],
        "reset_reentry_rebuild_churn_hotspots": reset_reentry_rebuild_persistence["reset_reentry_rebuild_churn_hotspots"],
        "primary_target_closure_forecast_reset_reentry_rebuild_freshness_status": primary_target.get("closure_forecast_reset_reentry_rebuild_freshness_status", reset_reentry_rebuild_freshness_decay["primary_target_closure_forecast_reset_reentry_rebuild_freshness_status"]) if primary_target else reset_reentry_rebuild_freshness_decay["primary_target_closure_forecast_reset_reentry_rebuild_freshness_status"],
        "primary_target_closure_forecast_reset_reentry_rebuild_freshness_reason": primary_target.get("closure_forecast_reset_reentry_rebuild_freshness_reason", reset_reentry_rebuild_freshness_decay["primary_target_closure_forecast_reset_reentry_rebuild_freshness_reason"]) if primary_target else reset_reentry_rebuild_freshness_decay["primary_target_closure_forecast_reset_reentry_rebuild_freshness_reason"],
        "closure_forecast_reset_reentry_rebuild_freshness_summary": reset_reentry_rebuild_freshness_decay["closure_forecast_reset_reentry_rebuild_freshness_summary"],
        "primary_target_closure_forecast_reset_reentry_rebuild_reset_status": primary_target.get("closure_forecast_reset_reentry_rebuild_reset_status", reset_reentry_rebuild_freshness_decay["primary_target_closure_forecast_reset_reentry_rebuild_reset_status"]) if primary_target else reset_reentry_rebuild_freshness_decay["primary_target_closure_forecast_reset_reentry_rebuild_reset_status"],
        "primary_target_closure_forecast_reset_reentry_rebuild_reset_reason": primary_target.get("closure_forecast_reset_reentry_rebuild_reset_reason", reset_reentry_rebuild_freshness_decay["primary_target_closure_forecast_reset_reentry_rebuild_reset_reason"]) if primary_target else reset_reentry_rebuild_freshness_decay["primary_target_closure_forecast_reset_reentry_rebuild_reset_reason"],
        "closure_forecast_reset_reentry_rebuild_reset_summary": reset_reentry_rebuild_freshness_decay["closure_forecast_reset_reentry_rebuild_reset_summary"],
        "stale_reset_reentry_rebuild_hotspots": reset_reentry_rebuild_freshness_decay["stale_reset_reentry_rebuild_hotspots"],
        "fresh_reset_reentry_rebuild_signal_hotspots": reset_reentry_rebuild_freshness_decay["fresh_reset_reentry_rebuild_signal_hotspots"],
        "closure_forecast_reset_reentry_rebuild_decay_window_runs": reset_reentry_rebuild_freshness_decay["closure_forecast_reset_reentry_rebuild_decay_window_runs"],
        "sustained_class_hotspots": class_trust_momentum["sustained_class_hotspots"],
        "oscillating_class_hotspots": class_trust_momentum["oscillating_class_hotspots"],
        "decision_memory_status": decision_memory["decision_memory_status"],
        "primary_target_last_seen_at": decision_memory["primary_target_last_seen_at"],
        "primary_target_last_intervention": decision_memory["primary_target_last_intervention"],
        "primary_target_last_outcome": decision_memory["primary_target_last_outcome"],
        "primary_target_resolution_evidence": decision_memory["primary_target_resolution_evidence"],
        "recent_interventions": decision_memory["recent_interventions"],
        "recently_quieted_count": decision_memory["recently_quieted_count"],
        "confirmed_resolved_count": decision_memory["confirmed_resolved_count"],
        "reopened_after_resolution_count": decision_memory["reopened_after_resolution_count"],
        "decision_memory_window_runs": decision_memory["decision_memory_window_runs"],
        "resolution_evidence_summary": decision_memory["resolution_evidence_summary"],
    }


def _snapshot_from_queue(queue: list[dict], *, generated_at: str = "") -> dict:
    items = {_queue_identity(item): item for item in queue}
    return {
        "items": items,
        "has_attention": any(item.get("lane") in ATTENTION_LANES for item in queue),
        "generated_at": generated_at,
    }


def _snapshot_from_history(entry: dict) -> dict:
    queue = entry.get("operator_queue", []) or []
    items = {_queue_identity(item): item for item in queue}
    summary = entry.get("operator_summary", {}) or {}
    has_attention = summary.get("counts", {}).get("blocked", 0) or summary.get("counts", {}).get("urgent", 0)
    return {
        "items": items,
        "has_attention": bool(has_attention),
        "generated_at": entry.get("generated_at", ""),
    }


def _attention_items(snapshot: dict) -> dict[str, dict]:
    return {
        key: item
        for key, item in (snapshot.get("items") or {}).items()
        if item.get("lane") in ATTENTION_LANES
    }


def _resolution_targets(
    queue: list[dict],
    recent_runs: list[dict],
    decision_memory_map: dict[str, dict],
    confidence_calibration: dict,
) -> list[dict]:
    previous_attention_keys = set(_attention_items(recent_runs[1])) if len(recent_runs) > 1 else set()
    earlier_attention_keys = set().union(
        *[set(_attention_items(snapshot)) for snapshot in recent_runs[2:]]
    ) if len(recent_runs) > 2 else set()
    targets: list[dict] = []
    for item in queue:
        if item.get("lane") == "deferred":
            continue
        key = _queue_identity(item)
        earliest_days = item.get("age_days", 0)
        non_deferred_appearances = 0
        repeat_attention_appearances = 0
        for snapshot in recent_runs:
            match = snapshot["items"].get(key)
            if not match:
                continue
            earliest_days = max(earliest_days, match.get("age_days", 0))
            if match.get("lane") != "deferred":
                non_deferred_appearances += 1
            if match.get("lane") in ATTENTION_LANES:
                repeat_attention_appearances += 1
        is_stale = non_deferred_appearances >= 3 or earliest_days > 7
        previous_earliest_days = max(
            (
                match.get("age_days", 0)
                for snapshot in recent_runs[1:]
                if (match := snapshot["items"].get(key)) and match.get("lane") != "deferred"
            ),
            default=0,
        )
        previous_non_deferred_appearances = sum(
            1
            for snapshot in recent_runs[1:]
            if (match := snapshot["items"].get(key)) and match.get("lane") != "deferred"
        )
        is_repeat_urgent = item.get("lane") in ATTENTION_LANES and repeat_attention_appearances >= 2
        is_reopened = (
            item.get("lane") in ATTENTION_LANES
            and key not in previous_attention_keys
            and key in earlier_attention_keys
        )
        current_aging_status = _aging_status(non_deferred_appearances, earliest_days)
        previous_aging_status = _aging_status(previous_non_deferred_appearances, previous_earliest_days)
        newly_stale = current_aging_status in {"stale", "chronic"} and previous_aging_status in {"fresh", "watch"}
        targets.append(
            {
                "item_id": item.get("item_id", key),
                "repo": item.get("repo", ""),
                "title": item.get("title", ""),
                "lane": item.get("lane", ""),
                "lane_label": item.get("lane_label", LANE_LABELS.get(item.get("lane", ""), "")),
                "kind": item.get("kind", ""),
                "priority": item.get("priority", 0),
                "recommended_action": item.get("recommended_action", ""),
                "summary": item.get("summary", ""),
                "age_days": earliest_days,
                "aging_status": current_aging_status,
                "stale": is_stale,
                "reopened": is_reopened,
                "repeat_urgent": is_repeat_urgent,
                "newly_stale": newly_stale,
                **decision_memory_map.get(key, {}),
            }
        )
    targets = [_with_confidence(target, confidence_calibration) for target in targets]
    targets.sort(key=_resolution_target_sort_key)
    return targets


def _with_confidence(item: dict, confidence_calibration: dict) -> dict:
    score, _label, reasons = _recommendation_confidence(item)
    (
        tuned_score,
        tuned_label,
        calibration_adjustment,
        calibration_adjustment_reason,
    ) = _apply_calibration_adjustment(item, score, confidence_calibration)
    trust_policy, trust_policy_reason = _trust_policy_for_item(
        item,
        tuned_score,
        tuned_label,
        confidence_calibration,
        item.get("recommended_action", ""),
    )
    return {
        **item,
        "confidence_score": tuned_score,
        "confidence_label": tuned_label,
        "confidence_reasons": reasons,
        "calibration_adjustment": calibration_adjustment,
        "calibration_adjustment_reason": calibration_adjustment_reason,
        "base_trust_policy": trust_policy,
        "base_trust_policy_reason": trust_policy_reason,
        "trust_policy": trust_policy,
        "trust_policy_reason": trust_policy_reason,
    }


def _apply_trust_policy_exceptions(
    resolution_targets: list[dict],
    history: list[dict],
    *,
    current_generated_at: str,
    confidence_calibration: dict,
) -> dict:
    if not resolution_targets:
        return {
            "primary_target_exception_status": "none",
            "primary_target_exception_reason": "",
            "recommendation_drift_status": "stable",
            "recommendation_drift_summary": "No active trust-policy drift is recorded because there is no active target.",
            "policy_flip_hotspots": [],
        }

    primary_target = resolution_targets[0]
    current_bucket = _recommendation_bucket(primary_target)
    policy_events = _trust_policy_events(
        history,
        current_primary_target=primary_target,
        current_generated_at=current_generated_at,
    )
    policy_flip_hotspots = _policy_flip_hotspots(policy_events)

    updated_targets: list[dict] = []
    for target in resolution_targets:
        history_meta = _target_policy_history(target, policy_events)
        exception_status = "none"
        exception_reason = ""
        final_policy = target.get("trust_policy", "monitor")
        final_reason = target.get("trust_policy_reason", "No trust-policy reason is recorded yet.")

        if _recommendation_bucket(target) == current_bucket:
            (
                exception_status,
                exception_reason,
                final_policy,
                final_reason,
            ) = _trust_policy_exception_for_target(
                target,
                history_meta,
                confidence_calibration,
                current_bucket=current_bucket,
            )

        updated_targets.append(
            {
                **target,
                "policy_flip_count": history_meta["policy_flip_count"],
                "recent_policy_path": history_meta["recent_policy_path"],
                "trust_exception_status": exception_status,
                "trust_exception_reason": exception_reason,
                "trust_policy": final_policy,
                "trust_policy_reason": final_reason,
            }
        )

    resolution_targets[:] = updated_targets
    primary_target = resolution_targets[0]
    return {
        "primary_target_exception_status": primary_target.get("trust_exception_status", "none"),
        "primary_target_exception_reason": primary_target.get("trust_exception_reason", ""),
        "recommendation_drift_status": _recommendation_drift_status(
            primary_target.get("policy_flip_count", 0),
            primary_target.get("recent_policy_path", ""),
            policy_flip_hotspots,
        ),
        "recommendation_drift_summary": _recommendation_drift_summary(
            primary_target,
            policy_flip_hotspots,
        ),
        "policy_flip_hotspots": policy_flip_hotspots,
    }


def _apply_exception_pattern_learning(
    resolution_targets: list[dict],
    history: list[dict],
    *,
    current_generated_at: str,
    confidence_calibration: dict,
) -> dict:
    if not resolution_targets:
        return {
            "primary_target_exception_pattern_status": "none",
            "primary_target_exception_pattern_reason": "",
            "primary_target_trust_recovery_status": "none",
            "primary_target_trust_recovery_reason": "",
            "exception_pattern_summary": "No exception-pattern learning is recorded because there is no active target.",
            "false_positive_exception_hotspots": [],
            "trust_recovery_window_runs": TRUST_RECOVERY_WINDOW_RUNS,
        }

    current_primary_target = resolution_targets[0]
    current_bucket = _recommendation_bucket(current_primary_target)
    exception_events = _trust_exception_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )
    historical_cases = _historical_exception_cases(history)
    false_positive_hotspots = _false_positive_exception_hotspots(historical_cases)

    updated_targets: list[dict] = []
    for target in resolution_targets:
        pattern_status = "none"
        pattern_reason = ""
        recovery_status = "none"
        recovery_reason = ""
        stable_policy_run_count = 0
        recent_exception_path = ""
        final_policy = target.get("trust_policy", "monitor")
        final_reason = target.get("trust_policy_reason", "No trust-policy reason is recorded yet.")
        pre_retirement_policy = final_policy
        pre_retirement_reason = final_reason

        if _recommendation_bucket(target) == current_bucket:
            history_meta = _target_exception_history(target, exception_events, historical_cases)
            stable_policy_run_count = history_meta["stable_policy_run_count"]
            recent_exception_path = history_meta["recent_exception_path"]
            pattern_status, pattern_reason = _exception_pattern_for_target(target, history_meta)
            pre_retirement_policy = final_policy
            pre_retirement_reason = final_reason
            (
                recovery_status,
                recovery_reason,
                final_policy,
                final_reason,
            ) = _trust_recovery_for_target(
                target,
                history_meta,
                confidence_calibration,
                trust_policy=final_policy,
                trust_policy_reason=final_reason,
            )
            if recovery_status in {"candidate", "earned"}:
                pattern_status = "recovering"
                pattern_reason = _recovery_pattern_reason(recovery_status, recovery_reason)
            elif recovery_status == "blocked" and pattern_status == "none":
                pattern_status = "recovering"
                pattern_reason = recovery_reason

        updated_targets.append(
            {
                **target,
                "exception_pattern_status": pattern_status,
                "exception_pattern_reason": pattern_reason,
                "trust_recovery_status": recovery_status,
                "trust_recovery_reason": recovery_reason,
                "stable_policy_run_count": stable_policy_run_count,
                "recent_exception_path": recent_exception_path,
                "pre_retirement_trust_policy": pre_retirement_policy,
                "pre_retirement_trust_policy_reason": pre_retirement_reason,
                "trust_policy": final_policy,
                "trust_policy_reason": final_reason,
            }
        )

    resolution_targets[:] = updated_targets
    primary_target = resolution_targets[0]
    return {
        "primary_target_exception_pattern_status": primary_target.get("exception_pattern_status", "none"),
        "primary_target_exception_pattern_reason": primary_target.get("exception_pattern_reason", ""),
        "primary_target_trust_recovery_status": primary_target.get("trust_recovery_status", "none"),
        "primary_target_trust_recovery_reason": primary_target.get("trust_recovery_reason", ""),
        "exception_pattern_summary": _exception_pattern_summary(primary_target, false_positive_hotspots),
        "false_positive_exception_hotspots": false_positive_hotspots,
        "trust_recovery_window_runs": TRUST_RECOVERY_WINDOW_RUNS,
    }


def _apply_exception_retirement(
    resolution_targets: list[dict],
    history: list[dict],
    *,
    current_generated_at: str,
    confidence_calibration: dict,
) -> dict:
    if not resolution_targets:
        return {
            "primary_target_recovery_confidence_score": 0.05,
            "primary_target_recovery_confidence_label": "low",
            "primary_target_recovery_confidence_reasons": [],
            "recovery_confidence_summary": "No recovery-confidence signal is recorded because there is no active target.",
            "primary_target_exception_retirement_status": "none",
            "primary_target_exception_retirement_reason": "",
            "exception_retirement_summary": "No exception retirement is recorded because there is no active target.",
            "retired_exception_hotspots": [],
            "sticky_exception_hotspots": [],
            "exception_retirement_window_runs": EXCEPTION_RETIREMENT_WINDOW_RUNS,
        }

    current_primary_target = resolution_targets[0]
    current_bucket = _recommendation_bucket(current_primary_target)
    retirement_events = _retirement_policy_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )
    historical_cases = _historical_exception_cases(history)

    updated_targets: list[dict] = []
    for target in resolution_targets:
        recovery_score = 0.05
        recovery_label = "low"
        recovery_reasons: list[str] = []
        stable_after_exception_runs = 0
        recent_retirement_path = ""
        retirement_status = "none"
        retirement_reason = ""
        final_policy = target.get("trust_policy", "monitor")
        final_reason = target.get("trust_policy_reason", "No trust-policy reason is recorded yet.")

        if _recommendation_bucket(target) == current_bucket:
            history_meta = _target_retirement_history(target, retirement_events, historical_cases)
            stable_after_exception_runs = history_meta["stable_after_exception_runs"]
            recent_retirement_path = history_meta["recent_retirement_path"]
            recovery_score, recovery_label, recovery_reasons = _recovery_confidence_for_target(
                target,
                history_meta,
                confidence_calibration,
            )
            (
                retirement_status,
                retirement_reason,
                final_policy,
                final_reason,
            ) = _exception_retirement_for_target(
                target,
                history_meta,
                confidence_calibration,
                recovery_confidence_label=recovery_label,
                trust_policy=final_policy,
                trust_policy_reason=final_reason,
            )

        updated_targets.append(
            {
                **target,
                "recovery_confidence_score": recovery_score,
                "recovery_confidence_label": recovery_label,
                "recovery_confidence_reasons": recovery_reasons,
                "stable_after_exception_runs": stable_after_exception_runs,
                "recent_retirement_path": recent_retirement_path,
                "exception_retirement_status": retirement_status,
                "exception_retirement_reason": retirement_reason,
                "trust_policy": final_policy,
                "trust_policy_reason": final_reason,
            }
        )

    resolution_targets[:] = updated_targets
    primary_target = resolution_targets[0]
    retired_exception_hotspots = _retirement_hotspots(
        historical_cases,
        resolution_targets,
        mode="retired",
    )
    sticky_exception_hotspots = _retirement_hotspots(
        historical_cases,
        resolution_targets,
        mode="sticky",
    )
    return {
        "primary_target_recovery_confidence_score": primary_target.get("recovery_confidence_score", 0.05),
        "primary_target_recovery_confidence_label": primary_target.get("recovery_confidence_label", "low"),
        "primary_target_recovery_confidence_reasons": primary_target.get("recovery_confidence_reasons", []),
        "recovery_confidence_summary": _recovery_confidence_summary(
            primary_target,
            sticky_exception_hotspots,
        ),
        "primary_target_exception_retirement_status": primary_target.get("exception_retirement_status", "none"),
        "primary_target_exception_retirement_reason": primary_target.get("exception_retirement_reason", ""),
        "exception_retirement_summary": _exception_retirement_summary(
            primary_target,
            retired_exception_hotspots,
            sticky_exception_hotspots,
        ),
        "retired_exception_hotspots": retired_exception_hotspots,
        "sticky_exception_hotspots": sticky_exception_hotspots,
        "exception_retirement_window_runs": EXCEPTION_RETIREMENT_WINDOW_RUNS,
    }


def _apply_class_trust_normalization(
    resolution_targets: list[dict],
    history: list[dict],
    *,
    current_generated_at: str,
    confidence_calibration: dict,
) -> dict:
    if not resolution_targets:
        return {
            "primary_target_policy_debt_status": "none",
            "primary_target_policy_debt_reason": "",
            "primary_target_class_normalization_status": "none",
            "primary_target_class_normalization_reason": "",
            "policy_debt_summary": "No class-level policy debt is recorded because there is no active target.",
            "trust_normalization_summary": "No class-level trust normalization is recorded because there is no active target.",
            "policy_debt_hotspots": [],
            "normalized_class_hotspots": [],
            "class_normalization_window_runs": CLASS_NORMALIZATION_WINDOW_RUNS,
        }

    current_primary_target = resolution_targets[0]
    current_bucket = _recommendation_bucket(current_primary_target)
    class_events = _class_normalization_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )
    historical_cases = _historical_exception_cases(history)

    updated_targets: list[dict] = []
    for target in resolution_targets:
        policy_debt_status = "none"
        policy_debt_reason = ""
        class_normalization_status = "none"
        class_normalization_reason = ""
        class_retirement_rate = 0.0
        class_sticky_rate = 0.0
        recent_class_policy_path = ""
        final_policy = target.get("trust_policy", "monitor")
        final_reason = target.get("trust_policy_reason", "No trust-policy reason is recorded yet.")

        if _recommendation_bucket(target) == current_bucket:
            history_meta = _target_class_normalization_history(target, class_events, historical_cases)
            class_retirement_rate = history_meta["class_retirement_rate"]
            class_sticky_rate = history_meta["class_sticky_rate"]
            recent_class_policy_path = history_meta["recent_class_policy_path"]
            policy_debt_status, policy_debt_reason = _policy_debt_for_target(
                target,
                history_meta,
            )
            (
                class_normalization_status,
                class_normalization_reason,
                final_policy,
                final_reason,
            ) = _class_normalization_for_target(
                target,
                history_meta,
                confidence_calibration,
                policy_debt_status=policy_debt_status,
                trust_policy=final_policy,
                trust_policy_reason=final_reason,
            )

        updated_targets.append(
            {
                **target,
                "pre_class_normalization_trust_policy": target.get("trust_policy", "monitor"),
                "pre_class_normalization_trust_policy_reason": target.get(
                    "trust_policy_reason",
                    "No trust-policy reason is recorded yet.",
                ),
                "policy_debt_status": policy_debt_status,
                "policy_debt_reason": policy_debt_reason,
                "class_normalization_status": class_normalization_status,
                "class_normalization_reason": class_normalization_reason,
                "class_retirement_rate": class_retirement_rate,
                "class_sticky_rate": class_sticky_rate,
                "recent_class_policy_path": recent_class_policy_path,
                "trust_policy": final_policy,
                "trust_policy_reason": final_reason,
            }
        )

    resolution_targets[:] = updated_targets
    primary_target = resolution_targets[0]
    policy_debt_hotspots = _class_normalization_hotspots(
        historical_cases,
        resolution_targets,
        mode="policy-debt",
    )
    normalized_class_hotspots = _class_normalization_hotspots(
        historical_cases,
        resolution_targets,
        mode="normalized",
    )
    return {
        "primary_target_policy_debt_status": primary_target.get("policy_debt_status", "none"),
        "primary_target_policy_debt_reason": primary_target.get("policy_debt_reason", ""),
        "primary_target_class_normalization_status": primary_target.get("class_normalization_status", "none"),
        "primary_target_class_normalization_reason": primary_target.get("class_normalization_reason", ""),
        "policy_debt_summary": _policy_debt_summary(primary_target, policy_debt_hotspots),
        "trust_normalization_summary": _trust_normalization_summary(
            primary_target,
            normalized_class_hotspots,
            policy_debt_hotspots,
        ),
        "policy_debt_hotspots": policy_debt_hotspots,
        "normalized_class_hotspots": normalized_class_hotspots,
        "class_normalization_window_runs": CLASS_NORMALIZATION_WINDOW_RUNS,
    }


def _apply_class_memory_decay(
    resolution_targets: list[dict],
    history: list[dict],
    *,
    current_generated_at: str,
    confidence_calibration: dict,
) -> dict:
    if not resolution_targets:
        return {
            "primary_target_class_memory_freshness_status": "insufficient-data",
            "primary_target_class_memory_freshness_reason": "",
            "primary_target_class_decay_status": "none",
            "primary_target_class_decay_reason": "",
            "class_memory_summary": "No class-memory freshness is recorded because there is no active target.",
            "class_decay_summary": "No class-decay controls are recorded because there is no active target.",
            "stale_class_memory_hotspots": [],
            "fresh_class_signal_hotspots": [],
            "class_decay_window_runs": CLASS_MEMORY_FRESHNESS_WINDOW_RUNS,
        }

    current_primary_target = resolution_targets[0]
    current_bucket = _recommendation_bucket(current_primary_target)
    class_events = _class_normalization_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )
    historical_cases = _historical_exception_cases(history)

    updated_targets: list[dict] = []
    for target in resolution_targets:
        freshness_status = "insufficient-data"
        freshness_reason = ""
        class_memory_weight = 0.0
        decayed_class_retirement_rate = 0.0
        decayed_class_sticky_rate = 0.0
        recent_class_signal_mix = ""
        class_decay_status = "none"
        class_decay_reason = ""
        final_policy = target.get("trust_policy", "monitor")
        final_reason = target.get("trust_policy_reason", "No trust-policy reason is recorded yet.")
        policy_debt_status = target.get("policy_debt_status", "none")
        policy_debt_reason = target.get("policy_debt_reason", "")
        class_normalization_status = target.get("class_normalization_status", "none")
        class_normalization_reason = target.get("class_normalization_reason", "")

        if _recommendation_bucket(target) == current_bucket:
            history_meta = _target_class_normalization_history(target, class_events, historical_cases)
            freshness_status = history_meta["class_memory_freshness_status"]
            freshness_reason = history_meta["class_memory_freshness_reason"]
            class_memory_weight = history_meta["class_memory_weight"]
            decayed_class_retirement_rate = history_meta["decayed_class_retirement_rate"]
            decayed_class_sticky_rate = history_meta["decayed_class_sticky_rate"]
            recent_class_signal_mix = history_meta["recent_class_signal_mix"]
            (
                class_decay_status,
                class_decay_reason,
                final_policy,
                final_reason,
                policy_debt_status,
                policy_debt_reason,
                class_normalization_status,
                class_normalization_reason,
            ) = _class_memory_decay_for_target(
                target,
                history_meta,
                confidence_calibration,
                trust_policy=final_policy,
                trust_policy_reason=final_reason,
                policy_debt_status=policy_debt_status,
                policy_debt_reason=policy_debt_reason,
                class_normalization_status=class_normalization_status,
                class_normalization_reason=class_normalization_reason,
            )

        updated_targets.append(
            {
                **target,
                "class_memory_freshness_status": freshness_status,
                "class_memory_freshness_reason": freshness_reason,
                "class_memory_weight": class_memory_weight,
                "decayed_class_retirement_rate": decayed_class_retirement_rate,
                "decayed_class_sticky_rate": decayed_class_sticky_rate,
                "recent_class_signal_mix": recent_class_signal_mix,
                "class_decay_status": class_decay_status,
                "class_decay_reason": class_decay_reason,
                "policy_debt_status": policy_debt_status,
                "policy_debt_reason": policy_debt_reason,
                "class_normalization_status": class_normalization_status,
                "class_normalization_reason": class_normalization_reason,
                "trust_policy": final_policy,
                "trust_policy_reason": final_reason,
            }
        )

    resolution_targets[:] = updated_targets
    primary_target = resolution_targets[0]
    stale_class_memory_hotspots = _class_memory_hotspots(resolution_targets, mode="stale")
    fresh_class_signal_hotspots = _class_memory_hotspots(resolution_targets, mode="fresh")
    return {
        "primary_target_class_memory_freshness_status": primary_target.get("class_memory_freshness_status", "insufficient-data"),
        "primary_target_class_memory_freshness_reason": primary_target.get("class_memory_freshness_reason", ""),
        "primary_target_class_decay_status": primary_target.get("class_decay_status", "none"),
        "primary_target_class_decay_reason": primary_target.get("class_decay_reason", ""),
        "class_memory_summary": _class_memory_summary(primary_target, fresh_class_signal_hotspots, stale_class_memory_hotspots),
        "class_decay_summary": _class_decay_summary(primary_target, stale_class_memory_hotspots, fresh_class_signal_hotspots),
        "stale_class_memory_hotspots": stale_class_memory_hotspots,
        "fresh_class_signal_hotspots": fresh_class_signal_hotspots,
        "class_decay_window_runs": CLASS_MEMORY_FRESHNESS_WINDOW_RUNS,
    }


def _apply_class_trust_reweighting(
    resolution_targets: list[dict],
    history: list[dict],
    *,
    current_generated_at: str,
    confidence_calibration: dict,
) -> dict:
    if not resolution_targets:
        return {
            "primary_target_weighted_class_support_score": 0.0,
            "primary_target_weighted_class_caution_score": 0.0,
            "primary_target_class_trust_reweight_score": 0.0,
            "primary_target_class_trust_reweight_direction": "neutral",
            "primary_target_class_trust_reweight_reasons": [],
            "class_reweighting_summary": "No class trust reweighting is recorded because there is no active target.",
            "supporting_class_hotspots": [],
            "caution_class_hotspots": [],
            "class_reweighting_window_runs": CLASS_REWEIGHTING_WINDOW_RUNS,
        }

    current_primary_target = resolution_targets[0]
    current_bucket = _recommendation_bucket(current_primary_target)
    class_events = _class_normalization_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )
    historical_cases = _historical_exception_cases(history)

    updated_targets: list[dict] = []
    for target in resolution_targets:
        weighted_class_support_score = 0.0
        weighted_class_caution_score = 0.0
        class_trust_reweight_score = 0.0
        class_trust_reweight_direction = "neutral"
        class_trust_reweight_reasons: list[str] = []
        class_trust_reweight_effect = "none"
        class_trust_reweight_effect_reason = ""
        final_policy = target.get("trust_policy", "monitor")
        final_reason = target.get("trust_policy_reason", "No trust-policy reason is recorded yet.")
        policy_debt_status = target.get("policy_debt_status", "none")
        policy_debt_reason = target.get("policy_debt_reason", "")
        class_normalization_status = target.get("class_normalization_status", "none")
        class_normalization_reason = target.get("class_normalization_reason", "")

        if _recommendation_bucket(target) == current_bucket:
            history_meta = _target_class_normalization_history(target, class_events, historical_cases)
            (
                weighted_class_support_score,
                weighted_class_caution_score,
                class_trust_reweight_score,
                class_trust_reweight_direction,
                class_trust_reweight_reasons,
            ) = _class_trust_reweight_scores_for_target(target, history_meta)
            (
                class_trust_reweight_effect,
                class_trust_reweight_effect_reason,
                final_policy,
                final_reason,
                policy_debt_status,
                policy_debt_reason,
                class_normalization_status,
                class_normalization_reason,
            ) = _class_trust_reweight_for_target(
                target,
                history_meta,
                confidence_calibration,
                weighted_class_support_score=weighted_class_support_score,
                weighted_class_caution_score=weighted_class_caution_score,
                class_trust_reweight_score=class_trust_reweight_score,
                class_trust_reweight_direction=class_trust_reweight_direction,
                trust_policy=final_policy,
                trust_policy_reason=final_reason,
                policy_debt_status=policy_debt_status,
                policy_debt_reason=policy_debt_reason,
                class_normalization_status=class_normalization_status,
                class_normalization_reason=class_normalization_reason,
            )

        updated_targets.append(
            {
                **target,
                "weighted_class_support_score": weighted_class_support_score,
                "weighted_class_caution_score": weighted_class_caution_score,
                "class_trust_reweight_score": class_trust_reweight_score,
                "class_trust_reweight_direction": class_trust_reweight_direction,
                "class_trust_reweight_reasons": class_trust_reweight_reasons,
                "class_trust_reweight_effect": class_trust_reweight_effect,
                "class_trust_reweight_effect_reason": class_trust_reweight_effect_reason,
                "policy_debt_status": policy_debt_status,
                "policy_debt_reason": policy_debt_reason,
                "class_normalization_status": class_normalization_status,
                "class_normalization_reason": class_normalization_reason,
                "trust_policy": final_policy,
                "trust_policy_reason": final_reason,
            }
        )

    resolution_targets[:] = updated_targets
    primary_target = resolution_targets[0]
    supporting_class_hotspots = _class_reweight_hotspots(resolution_targets, mode="supporting")
    caution_class_hotspots = _class_reweight_hotspots(resolution_targets, mode="caution")
    return {
        "primary_target_weighted_class_support_score": primary_target.get("weighted_class_support_score", 0.0),
        "primary_target_weighted_class_caution_score": primary_target.get("weighted_class_caution_score", 0.0),
        "primary_target_class_trust_reweight_score": primary_target.get("class_trust_reweight_score", 0.0),
        "primary_target_class_trust_reweight_direction": primary_target.get("class_trust_reweight_direction", "neutral"),
        "primary_target_class_trust_reweight_reasons": primary_target.get("class_trust_reweight_reasons", []),
        "class_reweighting_summary": _class_reweighting_summary(
            primary_target,
            supporting_class_hotspots,
            caution_class_hotspots,
        ),
        "supporting_class_hotspots": supporting_class_hotspots,
        "caution_class_hotspots": caution_class_hotspots,
        "class_reweighting_window_runs": CLASS_REWEIGHTING_WINDOW_RUNS,
    }


def _class_memory_freshness_multiplier(freshness_status: str) -> float:
    if freshness_status == "fresh":
        return 1.00
    if freshness_status == "mixed-age":
        return 0.65
    if freshness_status == "stale":
        return 0.35
    return 0.20


def _class_trust_reweight_scores_for_target(
    target: dict,
    history_meta: dict,
) -> tuple[float, float, float, str, list[str]]:
    freshness_status = target.get(
        "class_memory_freshness_status",
        history_meta.get("class_memory_freshness_status", "insufficient-data"),
    )
    freshness_reason = target.get(
        "class_memory_freshness_reason",
        history_meta.get("class_memory_freshness_reason", ""),
    )
    freshness_multiplier = _class_memory_freshness_multiplier(freshness_status)
    decayed_class_retirement_rate = target.get(
        "decayed_class_retirement_rate",
        history_meta.get("decayed_class_retirement_rate", 0.0),
    )
    decayed_class_sticky_rate = target.get(
        "decayed_class_sticky_rate",
        history_meta.get("decayed_class_sticky_rate", 0.0),
    )
    local_blocker = _target_specific_normalization_noise(target, history_meta)

    support_adjustment = 0.0
    caution_adjustment = 0.0
    if target.get("class_normalization_status") in {"candidate", "applied"}:
        support_adjustment += 0.10
    if target.get("trust_recovery_status") in {"candidate", "earned"}:
        support_adjustment += 0.05
    if target.get("class_decay_status") == "normalization-decayed":
        support_adjustment -= 0.10
    if local_blocker:
        support_adjustment -= 0.10

    if target.get("policy_debt_status") == "class-debt":
        caution_adjustment += 0.10
    if target.get("class_decay_status") == "blocked":
        caution_adjustment += 0.05
    if target.get("exception_pattern_status") == "useful-caution":
        caution_adjustment += 0.05
    if target.get("class_decay_status") == "policy-debt-decayed":
        caution_adjustment -= 0.10
    if target.get("exception_pattern_status") == "overcautious":
        caution_adjustment -= 0.05

    weighted_class_support_score = _clamp_round(
        decayed_class_retirement_rate * freshness_multiplier + support_adjustment,
        lower=0.0,
        upper=0.95,
    )
    weighted_class_caution_score = _clamp_round(
        decayed_class_sticky_rate * freshness_multiplier + caution_adjustment,
        lower=0.0,
        upper=0.95,
    )
    class_trust_reweight_score = _clamp_round(
        weighted_class_support_score - weighted_class_caution_score,
        lower=-0.95,
        upper=0.95,
    )
    if class_trust_reweight_score >= 0.20:
        direction = "supporting-normalization"
    elif class_trust_reweight_score <= -0.20:
        direction = "supporting-caution"
    else:
        direction = "neutral"

    reasons = [reason for reason in (
        freshness_reason,
        _class_trust_support_reason(
            target,
            decayed_class_retirement_rate=decayed_class_retirement_rate,
            freshness_multiplier=freshness_multiplier,
        ),
        _class_trust_caution_reason(
            target,
            decayed_class_sticky_rate=decayed_class_sticky_rate,
            freshness_multiplier=freshness_multiplier,
        ),
        "Local reopen, flip, or blocked-recovery noise still overrides positive class carry-forward."
        if local_blocker
        else "",
    ) if reason]
    return (
        weighted_class_support_score,
        weighted_class_caution_score,
        class_trust_reweight_score,
        direction,
        reasons[:4],
    )


def _class_trust_support_reason(
    target: dict,
    *,
    decayed_class_retirement_rate: float,
    freshness_multiplier: float,
) -> str:
    if target.get("class_normalization_status") in {"candidate", "applied"}:
        return "Existing class normalization support is still contributing to a stronger posture."
    if target.get("trust_recovery_status") in {"candidate", "earned"}:
        return "Trust recovery is reinforcing healthier class behavior."
    if decayed_class_retirement_rate * freshness_multiplier >= 0.30:
        return "Fresh retired-like class evidence is still carrying meaningful normalization support."
    return ""


def _class_trust_caution_reason(
    target: dict,
    *,
    decayed_class_sticky_rate: float,
    freshness_multiplier: float,
) -> str:
    if target.get("policy_debt_status") == "class-debt":
        return "Sticky class caution is still weighing against broader relaxation."
    if target.get("class_decay_status") == "blocked":
        return "Local target noise is still blocking healthier class carry-forward."
    if target.get("exception_pattern_status") == "useful-caution":
        return "Recent useful-caution history still supports a softer posture."
    if decayed_class_sticky_rate * freshness_multiplier >= 0.30:
        return "Fresh sticky class evidence is still carrying meaningful caution."
    return ""


def _class_trust_reweight_for_target(
    target: dict,
    history_meta: dict,
    confidence_calibration: dict,
    *,
    weighted_class_support_score: float,
    weighted_class_caution_score: float,
    class_trust_reweight_score: float,
    class_trust_reweight_direction: str,
    trust_policy: str,
    trust_policy_reason: str,
    policy_debt_status: str,
    policy_debt_reason: str,
    class_normalization_status: str,
    class_normalization_reason: str,
) -> tuple[str, str, str, str, str, str, str, str]:
    _ = weighted_class_support_score
    _ = weighted_class_caution_score
    freshness_status = target.get(
        "class_memory_freshness_status",
        history_meta.get("class_memory_freshness_status", "insufficient-data"),
    )
    local_noise = _target_specific_normalization_noise(target, history_meta)
    calibration_status = confidence_calibration.get("confidence_validation_status", "insufficient-data")

    if (
        local_noise
        and class_trust_reweight_direction == "supporting-normalization"
    ):
        return (
            "none",
            "Positive class reweighting is blocked because local reopen, flip, or blocked-recovery noise still overrides class support.",
            trust_policy,
            trust_policy_reason,
            policy_debt_status,
            policy_debt_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    can_strengthen = freshness_status == "fresh" and not local_noise and calibration_status == "healthy"
    can_soften = freshness_status in {"fresh", "mixed-age", "stale", "insufficient-data"}

    if (
        class_normalization_status == "candidate"
        and class_trust_reweight_score >= 0.20
        and can_strengthen
    ):
        boosted_reason = (
            "Fresh class support crossed the reweight threshold, so this target inherits a stronger act-with-review posture."
        )
        return (
            "normalization-boosted",
            boosted_reason,
            "act-with-review",
            boosted_reason,
            policy_debt_status,
            policy_debt_reason,
            "applied",
            boosted_reason,
        )

    if (
        class_normalization_status == "applied"
        and class_trust_reweight_score < 0.10
        and can_soften
    ):
        softened_reason = (
            "Class normalization stayed visible, but fresh support is no longer strong enough to keep the full stronger posture in place."
        )
        reverted_policy = target.get("pre_class_normalization_trust_policy", trust_policy)
        if trust_policy == "act-with-review" and reverted_policy == "verify-first":
            trust_policy = reverted_policy
            trust_policy_reason = softened_reason
        return (
            "normalization-softened",
            softened_reason,
            trust_policy,
            trust_policy_reason if trust_policy != "verify-first" else softened_reason,
            policy_debt_status,
            policy_debt_reason,
            "candidate",
            softened_reason,
        )

    if (
        policy_debt_status == "watch"
        and class_trust_reweight_score <= -0.20
        and freshness_status == "fresh"
    ):
        strengthened_reason = "Fresh class caution is still strong enough to keep this class in sticky caution."
        return (
            "policy-debt-strengthened",
            strengthened_reason,
            trust_policy,
            trust_policy_reason,
            "class-debt",
            strengthened_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    if (
        policy_debt_status == "class-debt"
        and class_trust_reweight_score > -0.10
        and can_soften
    ):
        softened_reason = "Class-level caution is fading rather than disappearing all at once, so this class softens from class-debt to watch."
        return (
            "policy-debt-softened",
            softened_reason,
            trust_policy,
            trust_policy_reason,
            "watch",
            softened_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    return (
        "none",
        "",
        trust_policy,
        trust_policy_reason,
        policy_debt_status,
        policy_debt_reason,
        class_normalization_status,
        class_normalization_reason,
    )


def _class_reweight_hotspots(resolution_targets: list[dict], *, mode: str) -> list[dict]:
    grouped: dict[str, dict] = {}
    for target in resolution_targets:
        class_key = _target_class_key(target)
        if not class_key:
            continue
        existing = grouped.get(class_key)
        current = {
            "scope": "class",
            "label": class_key,
            "direction": target.get("class_trust_reweight_direction", "neutral"),
            "reweight_score": target.get("class_trust_reweight_score", 0.0),
            "weighted_class_support_score": target.get("weighted_class_support_score", 0.0),
            "weighted_class_caution_score": target.get("weighted_class_caution_score", 0.0),
            "class_memory_freshness_status": target.get("class_memory_freshness_status", "insufficient-data"),
            "effect": target.get("class_trust_reweight_effect", "none"),
        }
        if existing is None or abs(current["reweight_score"]) > abs(existing["reweight_score"]):
            grouped[class_key] = current

    hotspots = list(grouped.values())
    if mode == "supporting":
        hotspots = [item for item in hotspots if item.get("reweight_score", 0.0) >= 0.20]
        hotspots.sort(
            key=lambda item: (
                -item.get("reweight_score", 0.0),
                -item.get("weighted_class_support_score", 0.0),
                item.get("label", ""),
            )
        )
    else:
        hotspots = [item for item in hotspots if item.get("reweight_score", 0.0) <= -0.20]
        hotspots.sort(
            key=lambda item: (
                item.get("reweight_score", 0.0),
                -item.get("weighted_class_caution_score", 0.0),
                item.get("label", ""),
            )
        )
    return hotspots[:5]


def _class_reweighting_summary(
    primary_target: dict,
    supporting_class_hotspots: list[dict],
    caution_class_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    effect = primary_target.get("class_trust_reweight_effect", "none")
    direction = primary_target.get("class_trust_reweight_direction", "neutral")
    score = primary_target.get("class_trust_reweight_score", 0.0)
    if effect == "normalization-boosted":
        return f"{label} inherited a stronger posture because fresh class support crossed the reweight threshold ({score:.2f})."
    if effect == "normalization-softened":
        return f"{label} kept class normalization visible, but its support weakened enough that the stronger posture was softened ({score:.2f})."
    if effect == "policy-debt-strengthened":
        return f"{label} still sits in fresh caution-heavy class evidence, so sticky class caution stayed strong ({score:.2f})."
    if effect == "policy-debt-softened":
        return f"{label} still carries class-level caution, but that caution is fading instead of disappearing all at once ({score:.2f})."
    if direction == "supporting-normalization":
        return f"Fresh class evidence is consistently improving around {label}, so class guidance is actively leaning toward normalization ({score:.2f})."
    if direction == "supporting-caution":
        return f"Recent class evidence around {label} is still caution-heavy enough to keep class trust conservative ({score:.2f})."
    if supporting_class_hotspots:
        hotspot = supporting_class_hotspots[0]
        return (
            f"Fresh class support is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "but the current target has not crossed the reweight threshold yet."
        )
    if caution_class_hotspots:
        hotspot = caution_class_hotspots[0]
        return (
            f"Fresh class caution is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so broader trust relaxation should stay conservative there."
        )
    return "Class evidence is informative, but not strong enough to move posture by itself yet."


def _apply_class_trust_momentum(
    resolution_targets: list[dict],
    history: list[dict],
    *,
    current_generated_at: str,
    confidence_calibration: dict,
) -> dict:
    if not resolution_targets:
        return {
            "primary_target_class_trust_momentum_score": 0.0,
            "primary_target_class_trust_momentum_status": "insufficient-data",
            "primary_target_class_reweight_stability_status": "watch",
            "primary_target_class_reweight_transition_status": "none",
            "primary_target_class_reweight_transition_reason": "",
            "class_momentum_summary": "No class trust momentum is recorded because there is no active target.",
            "class_reweight_stability_summary": "No class reweighting stability signal is recorded because there is no active target.",
            "class_transition_window_runs": CLASS_TRANSITION_WINDOW_RUNS,
            "sustained_class_hotspots": [],
            "oscillating_class_hotspots": [],
        }

    current_primary_target = resolution_targets[0]
    current_bucket = _recommendation_bucket(current_primary_target)
    reweight_events = _class_reweight_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )

    updated_targets: list[dict] = []
    for target in resolution_targets:
        momentum_score = 0.0
        momentum_status = "insufficient-data"
        stability_status = "watch"
        transition_status = "none"
        transition_reason = ""
        recent_path = ""
        final_policy = target.get("trust_policy", "monitor")
        final_reason = target.get("trust_policy_reason", "No trust-policy reason is recorded yet.")
        policy_debt_status = target.get("policy_debt_status", "none")
        policy_debt_reason = target.get("policy_debt_reason", "")
        class_normalization_status = target.get("class_normalization_status", "none")
        class_normalization_reason = target.get("class_normalization_reason", "")

        if _recommendation_bucket(target) == current_bucket:
            history_meta = _target_class_reweight_history(target, reweight_events)
            momentum_score = history_meta.get("class_trust_momentum_score", 0.0)
            momentum_status = history_meta.get("class_trust_momentum_status", "insufficient-data")
            stability_status = history_meta.get("class_reweight_stability_status", "watch")
            recent_path = history_meta.get("recent_class_reweight_path", "")
            (
                transition_status,
                transition_reason,
                final_policy,
                final_reason,
                policy_debt_status,
                policy_debt_reason,
                class_normalization_status,
                class_normalization_reason,
            ) = _class_trust_momentum_for_target(
                target,
                history_meta,
                confidence_calibration,
                trust_policy=final_policy,
                trust_policy_reason=final_reason,
                policy_debt_status=policy_debt_status,
                policy_debt_reason=policy_debt_reason,
                class_normalization_status=class_normalization_status,
                class_normalization_reason=class_normalization_reason,
            )

        updated_targets.append(
            {
                **target,
                "class_trust_momentum_score": momentum_score,
                "class_trust_momentum_status": momentum_status,
                "class_reweight_stability_status": stability_status,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "recent_class_reweight_path": recent_path,
                "policy_debt_status": policy_debt_status,
                "policy_debt_reason": policy_debt_reason,
                "class_normalization_status": class_normalization_status,
                "class_normalization_reason": class_normalization_reason,
                "trust_policy": final_policy,
                "trust_policy_reason": final_reason,
            }
        )

    resolution_targets[:] = updated_targets
    primary_target = resolution_targets[0]
    sustained_class_hotspots = _class_momentum_hotspots(resolution_targets, mode="sustained")
    oscillating_class_hotspots = _class_momentum_hotspots(resolution_targets, mode="oscillating")
    return {
        "primary_target_class_trust_momentum_score": primary_target.get("class_trust_momentum_score", 0.0),
        "primary_target_class_trust_momentum_status": primary_target.get("class_trust_momentum_status", "insufficient-data"),
        "primary_target_class_reweight_stability_status": primary_target.get("class_reweight_stability_status", "watch"),
        "primary_target_class_reweight_transition_status": primary_target.get("class_reweight_transition_status", "none"),
        "primary_target_class_reweight_transition_reason": primary_target.get("class_reweight_transition_reason", ""),
        "class_momentum_summary": _class_momentum_summary(
            primary_target,
            sustained_class_hotspots,
            oscillating_class_hotspots,
        ),
        "class_reweight_stability_summary": _class_reweight_stability_summary(
            primary_target,
            oscillating_class_hotspots,
        ),
        "class_transition_window_runs": CLASS_TRANSITION_WINDOW_RUNS,
        "sustained_class_hotspots": sustained_class_hotspots,
        "oscillating_class_hotspots": oscillating_class_hotspots,
    }


def _apply_class_transition_resolution(
    resolution_targets: list[dict],
    history: list[dict],
    *,
    current_generated_at: str,
    confidence_calibration: dict,
) -> dict:
    if not resolution_targets:
        return {
            "primary_target_class_transition_health_status": "none",
            "primary_target_class_transition_health_reason": "",
            "primary_target_class_transition_resolution_status": "none",
            "primary_target_class_transition_resolution_reason": "",
            "class_transition_health_summary": "No class transition health is recorded because there is no active target.",
            "class_transition_resolution_summary": "No pending transition resolution is recorded because there is no active target.",
            "class_transition_age_window_runs": CLASS_PENDING_RESOLUTION_WINDOW_RUNS,
            "stalled_transition_hotspots": [],
            "resolving_transition_hotspots": [],
        }

    current_primary_target = resolution_targets[0]
    current_bucket = _recommendation_bucket(current_primary_target)
    transition_events = _class_transition_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )

    updated_targets: list[dict] = []
    for target in resolution_targets:
        health_status = "none"
        health_reason = ""
        resolution_status = "none"
        resolution_reason = ""
        transition_age_runs = 0
        recent_transition_path = ""
        final_policy = target.get("trust_policy", "monitor")
        final_reason = target.get("trust_policy_reason", "No trust-policy reason is recorded yet.")
        transition_status = target.get("class_reweight_transition_status", "none")
        transition_reason = target.get("class_reweight_transition_reason", "")
        policy_debt_status = target.get("policy_debt_status", "none")
        policy_debt_reason = target.get("policy_debt_reason", "")
        class_normalization_status = target.get("class_normalization_status", "none")
        class_normalization_reason = target.get("class_normalization_reason", "")

        if _recommendation_bucket(target) == current_bucket:
            history_meta = _target_class_transition_history(target, transition_events)
            transition_age_runs = history_meta["class_transition_age_runs"]
            recent_transition_path = history_meta["recent_transition_path"]
            (
                health_status,
                health_reason,
                resolution_status,
                resolution_reason,
                transition_status,
                transition_reason,
                final_policy,
                final_reason,
                policy_debt_status,
                policy_debt_reason,
                class_normalization_status,
                class_normalization_reason,
            ) = _class_transition_resolution_for_target(
                target,
                history_meta,
                confidence_calibration,
                trust_policy=final_policy,
                trust_policy_reason=final_reason,
                transition_status=transition_status,
                transition_reason=transition_reason,
                policy_debt_status=policy_debt_status,
                policy_debt_reason=policy_debt_reason,
                class_normalization_status=class_normalization_status,
                class_normalization_reason=class_normalization_reason,
            )

        updated_targets.append(
            {
                **target,
                "class_transition_age_runs": transition_age_runs,
                "class_transition_health_status": health_status,
                "class_transition_health_reason": health_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "recent_transition_path": recent_transition_path,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "policy_debt_status": policy_debt_status,
                "policy_debt_reason": policy_debt_reason,
                "class_normalization_status": class_normalization_status,
                "class_normalization_reason": class_normalization_reason,
                "trust_policy": final_policy,
                "trust_policy_reason": final_reason,
            }
        )

    resolution_targets[:] = updated_targets
    primary_target = resolution_targets[0]
    stalled_transition_hotspots = _class_transition_hotspots(resolution_targets, mode="stalled")
    resolving_transition_hotspots = _class_transition_hotspots(resolution_targets, mode="resolving")
    return {
        "primary_target_class_transition_health_status": primary_target.get("class_transition_health_status", "none"),
        "primary_target_class_transition_health_reason": primary_target.get("class_transition_health_reason", ""),
        "primary_target_class_transition_resolution_status": primary_target.get("class_transition_resolution_status", "none"),
        "primary_target_class_transition_resolution_reason": primary_target.get("class_transition_resolution_reason", ""),
        "class_transition_health_summary": _class_transition_health_summary(
            primary_target,
            stalled_transition_hotspots,
        ),
        "class_transition_resolution_summary": _class_transition_resolution_summary(
            primary_target,
            resolving_transition_hotspots,
            stalled_transition_hotspots,
        ),
        "class_transition_age_window_runs": CLASS_PENDING_RESOLUTION_WINDOW_RUNS,
        "stalled_transition_hotspots": stalled_transition_hotspots,
        "resolving_transition_hotspots": resolving_transition_hotspots,
    }


def _apply_transition_closure_confidence(
    resolution_targets: list[dict],
    history: list[dict],
    *,
    current_generated_at: str,
    confidence_calibration: dict,
) -> dict:
    if not resolution_targets:
        return {
            "primary_target_transition_closure_confidence_score": 0.05,
            "primary_target_transition_closure_confidence_label": "low",
            "primary_target_transition_closure_likely_outcome": "none",
            "primary_target_transition_closure_confidence_reasons": [],
            "transition_closure_confidence_summary": "No transition-closure confidence is recorded because there is no active target.",
            "transition_closure_window_runs": CLASS_TRANSITION_CLOSURE_WINDOW_RUNS,
            "primary_target_class_pending_debt_status": "none",
            "primary_target_class_pending_debt_reason": "",
            "class_pending_debt_summary": "No class pending-debt signal is recorded because there is no active target.",
            "class_pending_resolution_summary": "No class pending-resolution signal is recorded because there is no active target.",
            "class_pending_debt_window_runs": CLASS_PENDING_DEBT_WINDOW_RUNS,
            "pending_debt_hotspots": [],
            "healthy_pending_resolution_hotspots": [],
        }

    current_primary_target = resolution_targets[0]
    current_bucket = _recommendation_bucket(current_primary_target)
    transition_events = _class_transition_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )
    historical_transition_events = transition_events[1:]

    updated_targets: list[dict] = []
    for target in resolution_targets:
        closure_score = 0.05
        closure_label = "low"
        likely_outcome = "none"
        closure_reasons: list[str] = []
        transition_score_delta = 0.0
        recent_transition_score_path = ""
        pending_debt_status = "none"
        pending_debt_reason = ""
        pending_debt_rate = 0.0
        pending_resolution_rate = 0.0
        recent_pending_debt_path = ""
        final_policy = target.get("trust_policy", "monitor")
        final_reason = target.get("trust_policy_reason", "No trust-policy reason is recorded yet.")
        health_status = target.get("class_transition_health_status", "none")
        health_reason = target.get("class_transition_health_reason", "")
        resolution_status = target.get("class_transition_resolution_status", "none")
        resolution_reason = target.get("class_transition_resolution_reason", "")
        transition_status = target.get("class_reweight_transition_status", "none")
        transition_reason = target.get("class_reweight_transition_reason", "")
        policy_debt_status = target.get("policy_debt_status", "none")
        policy_debt_reason = target.get("policy_debt_reason", "")
        class_normalization_status = target.get("class_normalization_status", "none")
        class_normalization_reason = target.get("class_normalization_reason", "")

        if _recommendation_bucket(target) == current_bucket:
            history_meta = _target_class_transition_history(target, transition_events)
            transition_score_delta = history_meta.get("transition_score_delta", 0.0)
            recent_transition_score_path = history_meta.get("recent_transition_score_path", "")
            (
                closure_score,
                closure_label,
                likely_outcome,
                closure_reasons,
            ) = _transition_closure_confidence_for_target(
                target,
                history_meta,
            )
            (
                pending_debt_status,
                pending_debt_reason,
                pending_debt_rate,
                pending_resolution_rate,
                recent_pending_debt_path,
            ) = _class_pending_debt_for_target(
                target,
                historical_transition_events,
            )
            (
                health_status,
                health_reason,
                resolution_status,
                resolution_reason,
                transition_status,
                transition_reason,
                final_policy,
                final_reason,
                policy_debt_status,
                policy_debt_reason,
                class_normalization_status,
                class_normalization_reason,
            ) = _apply_transition_closure_control(
                target,
                trust_policy=final_policy,
                trust_policy_reason=final_reason,
                health_status=health_status,
                health_reason=health_reason,
                resolution_status=resolution_status,
                resolution_reason=resolution_reason,
                transition_status=transition_status,
                transition_reason=transition_reason,
                policy_debt_status=policy_debt_status,
                policy_debt_reason=policy_debt_reason,
                class_normalization_status=class_normalization_status,
                class_normalization_reason=class_normalization_reason,
                closure_confidence_label=closure_label,
                closure_likely_outcome=likely_outcome,
                pending_debt_status=pending_debt_status,
            )

        updated_targets.append(
            {
                **target,
                "transition_closure_confidence_score": closure_score,
                "transition_closure_confidence_label": closure_label,
                "transition_closure_likely_outcome": likely_outcome,
                "transition_closure_confidence_reasons": closure_reasons,
                "transition_score_delta": transition_score_delta,
                "recent_transition_score_path": recent_transition_score_path,
                "class_pending_debt_status": pending_debt_status,
                "class_pending_debt_reason": pending_debt_reason,
                "class_pending_debt_rate": pending_debt_rate,
                "class_pending_resolution_rate": pending_resolution_rate,
                "recent_pending_debt_path": recent_pending_debt_path,
                "class_transition_health_status": health_status,
                "class_transition_health_reason": health_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "policy_debt_status": policy_debt_status,
                "policy_debt_reason": policy_debt_reason,
                "class_normalization_status": class_normalization_status,
                "class_normalization_reason": class_normalization_reason,
                "trust_policy": final_policy,
                "trust_policy_reason": final_reason,
            }
        )

    resolution_targets[:] = updated_targets
    primary_target = resolution_targets[0]
    pending_debt_hotspots = _class_pending_debt_hotspots(resolution_targets, mode="debt")
    healthy_pending_resolution_hotspots = _class_pending_debt_hotspots(
        resolution_targets,
        mode="healthy",
    )
    return {
        "primary_target_transition_closure_confidence_score": primary_target.get("transition_closure_confidence_score", 0.05),
        "primary_target_transition_closure_confidence_label": primary_target.get("transition_closure_confidence_label", "low"),
        "primary_target_transition_closure_likely_outcome": primary_target.get("transition_closure_likely_outcome", "none"),
        "primary_target_transition_closure_confidence_reasons": primary_target.get("transition_closure_confidence_reasons", []),
        "transition_closure_confidence_summary": _transition_closure_confidence_summary(
            primary_target,
            pending_debt_hotspots,
        ),
        "transition_closure_window_runs": CLASS_TRANSITION_CLOSURE_WINDOW_RUNS,
        "primary_target_class_pending_debt_status": primary_target.get("class_pending_debt_status", "none"),
        "primary_target_class_pending_debt_reason": primary_target.get("class_pending_debt_reason", ""),
        "class_pending_debt_summary": _class_pending_debt_summary(
            primary_target,
            pending_debt_hotspots,
            healthy_pending_resolution_hotspots,
        ),
        "class_pending_resolution_summary": _class_pending_resolution_summary(
            primary_target,
            healthy_pending_resolution_hotspots,
            pending_debt_hotspots,
        ),
        "class_pending_debt_window_runs": CLASS_PENDING_DEBT_WINDOW_RUNS,
        "pending_debt_hotspots": pending_debt_hotspots,
        "healthy_pending_resolution_hotspots": healthy_pending_resolution_hotspots,
    }


def _apply_pending_debt_freshness_and_closure_forecast_reweighting(
    resolution_targets: list[dict],
    history: list[dict],
    *,
    current_generated_at: str,
    confidence_calibration: dict,
) -> dict:
    if not resolution_targets:
        return {
            "primary_target_transition_closure_confidence_score": 0.05,
            "primary_target_transition_closure_confidence_label": "low",
            "primary_target_transition_closure_likely_outcome": "none",
            "primary_target_transition_closure_confidence_reasons": [],
            "transition_closure_confidence_summary": "No transition-closure confidence is recorded because there is no active target.",
            "transition_closure_window_runs": CLASS_TRANSITION_CLOSURE_WINDOW_RUNS,
            "primary_target_class_pending_debt_status": "none",
            "primary_target_class_pending_debt_reason": "",
            "class_pending_debt_summary": "No class pending-debt signal is recorded because there is no active target.",
            "class_pending_resolution_summary": "No class pending-resolution signal is recorded because there is no active target.",
            "class_pending_debt_window_runs": CLASS_PENDING_DEBT_WINDOW_RUNS,
            "pending_debt_hotspots": [],
            "healthy_pending_resolution_hotspots": [],
            "primary_target_pending_debt_freshness_status": "insufficient-data",
            "primary_target_pending_debt_freshness_reason": "",
            "pending_debt_freshness_summary": "No pending-debt freshness is recorded because there is no active target.",
            "pending_debt_decay_summary": "No pending-debt decay is recorded because there is no active target.",
            "stale_pending_debt_hotspots": [],
            "fresh_pending_resolution_hotspots": [],
            "pending_debt_decay_window_runs": PENDING_DEBT_FRESHNESS_WINDOW_RUNS,
            "primary_target_weighted_pending_resolution_support_score": 0.0,
            "primary_target_weighted_pending_debt_caution_score": 0.0,
            "primary_target_closure_forecast_reweight_score": 0.0,
            "primary_target_closure_forecast_reweight_direction": "neutral",
            "primary_target_closure_forecast_reweight_reasons": [],
            "closure_forecast_reweighting_summary": "No closure-forecast reweighting is recorded because there is no active target.",
            "closure_forecast_reweighting_window_runs": CLASS_CLOSURE_FORECAST_REWEIGHTING_WINDOW_RUNS,
            "supporting_pending_resolution_hotspots": [],
            "caution_pending_debt_hotspots": [],
        }

    current_primary_target = resolution_targets[0]
    current_bucket = _recommendation_bucket(current_primary_target)
    transition_events = _class_transition_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )
    historical_transition_events = transition_events[1:]

    updated_targets: list[dict] = []
    for target in resolution_targets:
        pending_debt_freshness_status = "insufficient-data"
        pending_debt_freshness_reason = ""
        pending_debt_memory_weight = 0.0
        decayed_pending_debt_rate = 0.0
        decayed_pending_resolution_rate = 0.0
        recent_pending_signal_mix = ""
        weighted_pending_resolution_support_score = 0.0
        weighted_pending_debt_caution_score = 0.0
        closure_forecast_reweight_score = 0.0
        closure_forecast_reweight_direction = "neutral"
        closure_forecast_reweight_reasons: list[str] = []
        closure_forecast_reweight_effect = "none"
        closure_forecast_reweight_effect_reason = ""
        transition_closure_likely_outcome = target.get("transition_closure_likely_outcome", "none")
        transition_closure_confidence_label = target.get("transition_closure_confidence_label", "low")
        transition_status = target.get("class_reweight_transition_status", "none")
        transition_reason = target.get("class_reweight_transition_reason", "")
        resolution_status = target.get("class_transition_resolution_status", "none")
        resolution_reason = target.get("class_transition_resolution_reason", "")
        trust_policy = target.get("trust_policy", "monitor")
        trust_policy_reason = target.get("trust_policy_reason", "No trust-policy reason is recorded yet.")
        pending_debt_status = target.get("class_pending_debt_status", "none")
        pending_debt_reason = target.get("class_pending_debt_reason", "")
        policy_debt_status = target.get("policy_debt_status", "none")
        policy_debt_reason = target.get("policy_debt_reason", "")
        class_normalization_status = target.get("class_normalization_status", "none")
        class_normalization_reason = target.get("class_normalization_reason", "")

        if _recommendation_bucket(target) == current_bucket:
            transition_history_meta = _target_class_transition_history(target, transition_events)
            pending_history_meta = _pending_debt_freshness_for_target(
                target,
                historical_transition_events,
            )
            pending_debt_freshness_status = pending_history_meta["pending_debt_freshness_status"]
            pending_debt_freshness_reason = pending_history_meta["pending_debt_freshness_reason"]
            pending_debt_memory_weight = pending_history_meta["pending_debt_memory_weight"]
            decayed_pending_debt_rate = pending_history_meta["decayed_pending_debt_rate"]
            decayed_pending_resolution_rate = pending_history_meta["decayed_pending_resolution_rate"]
            recent_pending_signal_mix = pending_history_meta["recent_pending_signal_mix"]
            (
                weighted_pending_resolution_support_score,
                weighted_pending_debt_caution_score,
                closure_forecast_reweight_score,
                closure_forecast_reweight_direction,
                closure_forecast_reweight_reasons,
            ) = _closure_forecast_reweight_scores_for_target(
                target,
                transition_history_meta,
                pending_history_meta,
            )
            (
                closure_forecast_reweight_effect,
                closure_forecast_reweight_effect_reason,
                transition_closure_likely_outcome,
                transition_status,
                transition_reason,
                resolution_status,
                resolution_reason,
                trust_policy,
                trust_policy_reason,
                pending_debt_status,
                pending_debt_reason,
                policy_debt_status,
                policy_debt_reason,
                class_normalization_status,
                class_normalization_reason,
            ) = _apply_closure_forecast_reweighting_control(
                target,
                transition_history_meta=transition_history_meta,
                trust_policy=trust_policy,
                trust_policy_reason=trust_policy_reason,
                transition_status=transition_status,
                transition_reason=transition_reason,
                resolution_status=resolution_status,
                resolution_reason=resolution_reason,
                pending_debt_status=pending_debt_status,
                pending_debt_reason=pending_debt_reason,
                policy_debt_status=policy_debt_status,
                policy_debt_reason=policy_debt_reason,
                class_normalization_status=class_normalization_status,
                class_normalization_reason=class_normalization_reason,
                closure_confidence_label=transition_closure_confidence_label,
                closure_likely_outcome=transition_closure_likely_outcome,
                pending_debt_freshness_status=pending_debt_freshness_status,
                closure_forecast_reweight_direction=closure_forecast_reweight_direction,
                closure_forecast_reweight_score=closure_forecast_reweight_score,
            )

        updated_targets.append(
            {
                **target,
                "pending_debt_freshness_status": pending_debt_freshness_status,
                "pending_debt_freshness_reason": pending_debt_freshness_reason,
                "pending_debt_memory_weight": pending_debt_memory_weight,
                "decayed_pending_debt_rate": decayed_pending_debt_rate,
                "decayed_pending_resolution_rate": decayed_pending_resolution_rate,
                "recent_pending_signal_mix": recent_pending_signal_mix,
                "weighted_pending_resolution_support_score": weighted_pending_resolution_support_score,
                "weighted_pending_debt_caution_score": weighted_pending_debt_caution_score,
                "closure_forecast_reweight_score": closure_forecast_reweight_score,
                "closure_forecast_reweight_direction": closure_forecast_reweight_direction,
                "closure_forecast_reweight_reasons": closure_forecast_reweight_reasons,
                "closure_forecast_reweight_effect": closure_forecast_reweight_effect,
                "closure_forecast_reweight_effect_reason": closure_forecast_reweight_effect_reason,
                "transition_closure_likely_outcome": transition_closure_likely_outcome,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "class_pending_debt_status": pending_debt_status,
                "class_pending_debt_reason": pending_debt_reason,
                "policy_debt_status": policy_debt_status,
                "policy_debt_reason": policy_debt_reason,
                "class_normalization_status": class_normalization_status,
                "class_normalization_reason": class_normalization_reason,
                "trust_policy": trust_policy,
                "trust_policy_reason": trust_policy_reason,
            }
        )

    resolution_targets[:] = updated_targets
    primary_target = resolution_targets[0]
    pending_debt_hotspots = _class_pending_debt_hotspots(resolution_targets, mode="debt")
    healthy_pending_resolution_hotspots = _class_pending_debt_hotspots(
        resolution_targets,
        mode="healthy",
    )
    stale_pending_debt_hotspots = _pending_debt_freshness_hotspots(
        resolution_targets,
        mode="stale",
    )
    fresh_pending_resolution_hotspots = _pending_debt_freshness_hotspots(
        resolution_targets,
        mode="fresh",
    )
    supporting_pending_resolution_hotspots = _closure_forecast_hotspots(
        resolution_targets,
        mode="support",
    )
    caution_pending_debt_hotspots = _closure_forecast_hotspots(
        resolution_targets,
        mode="caution",
    )
    return {
        "primary_target_transition_closure_confidence_score": primary_target.get("transition_closure_confidence_score", 0.05),
        "primary_target_transition_closure_confidence_label": primary_target.get("transition_closure_confidence_label", "low"),
        "primary_target_transition_closure_likely_outcome": primary_target.get("transition_closure_likely_outcome", "none"),
        "primary_target_transition_closure_confidence_reasons": primary_target.get("transition_closure_confidence_reasons", []),
        "transition_closure_confidence_summary": _transition_closure_confidence_summary(
            primary_target,
            pending_debt_hotspots,
        ),
        "transition_closure_window_runs": CLASS_TRANSITION_CLOSURE_WINDOW_RUNS,
        "primary_target_class_pending_debt_status": primary_target.get("class_pending_debt_status", "none"),
        "primary_target_class_pending_debt_reason": primary_target.get("class_pending_debt_reason", ""),
        "class_pending_debt_summary": _class_pending_debt_summary(
            primary_target,
            pending_debt_hotspots,
            healthy_pending_resolution_hotspots,
        ),
        "class_pending_resolution_summary": _class_pending_resolution_summary(
            primary_target,
            healthy_pending_resolution_hotspots,
            pending_debt_hotspots,
        ),
        "class_pending_debt_window_runs": CLASS_PENDING_DEBT_WINDOW_RUNS,
        "pending_debt_hotspots": pending_debt_hotspots,
        "healthy_pending_resolution_hotspots": healthy_pending_resolution_hotspots,
        "primary_target_pending_debt_freshness_status": primary_target.get("pending_debt_freshness_status", "insufficient-data"),
        "primary_target_pending_debt_freshness_reason": primary_target.get("pending_debt_freshness_reason", ""),
        "pending_debt_freshness_summary": _pending_debt_freshness_summary(
            primary_target,
            stale_pending_debt_hotspots,
            fresh_pending_resolution_hotspots,
        ),
        "pending_debt_decay_summary": _pending_debt_decay_summary(
            primary_target,
            fresh_pending_resolution_hotspots,
            stale_pending_debt_hotspots,
        ),
        "stale_pending_debt_hotspots": stale_pending_debt_hotspots,
        "fresh_pending_resolution_hotspots": fresh_pending_resolution_hotspots,
        "pending_debt_decay_window_runs": PENDING_DEBT_FRESHNESS_WINDOW_RUNS,
        "primary_target_weighted_pending_resolution_support_score": primary_target.get("weighted_pending_resolution_support_score", 0.0),
        "primary_target_weighted_pending_debt_caution_score": primary_target.get("weighted_pending_debt_caution_score", 0.0),
        "primary_target_closure_forecast_reweight_score": primary_target.get("closure_forecast_reweight_score", 0.0),
        "primary_target_closure_forecast_reweight_direction": primary_target.get("closure_forecast_reweight_direction", "neutral"),
        "primary_target_closure_forecast_reweight_reasons": primary_target.get("closure_forecast_reweight_reasons", []),
        "closure_forecast_reweighting_summary": _closure_forecast_reweighting_summary(
            primary_target,
            supporting_pending_resolution_hotspots,
            caution_pending_debt_hotspots,
        ),
        "closure_forecast_reweighting_window_runs": CLASS_CLOSURE_FORECAST_REWEIGHTING_WINDOW_RUNS,
        "supporting_pending_resolution_hotspots": supporting_pending_resolution_hotspots,
        "caution_pending_debt_hotspots": caution_pending_debt_hotspots,
    }


def _class_reweight_events(
    history: list[dict],
    *,
    current_primary_target: dict,
    current_generated_at: str,
) -> list[dict]:
    events: list[dict] = []
    if current_primary_target and current_primary_target.get("trust_policy"):
        events.append(
            {
                "key": _queue_identity(current_primary_target),
                "class_key": _target_class_key(current_primary_target),
                "label": _target_label(current_primary_target),
                "generated_at": current_generated_at or "",
                "class_trust_reweight_score": current_primary_target.get("class_trust_reweight_score", 0.0),
                "class_trust_reweight_direction": current_primary_target.get("class_trust_reweight_direction", "neutral"),
                "policy_debt_status": current_primary_target.get("policy_debt_status", "none"),
                "class_normalization_status": current_primary_target.get("class_normalization_status", "none"),
            }
        )
    for entry in history[: HISTORY_WINDOW_RUNS - 1]:
        summary = entry.get("operator_summary") or {}
        primary_target = summary.get("primary_target") or {}
        if not primary_target:
            continue
        reweight_direction = (
            summary.get("primary_target_class_trust_reweight_direction")
            or primary_target.get("class_trust_reweight_direction")
            or ""
        )
        reweight_score = summary.get("primary_target_class_trust_reweight_score")
        if reweight_score is None:
            reweight_score = primary_target.get("class_trust_reweight_score")
        if reweight_score is None and not reweight_direction:
            continue
        events.append(
            {
                "key": _queue_identity(primary_target),
                "class_key": _target_class_key(primary_target),
                "label": _target_label(primary_target),
                "generated_at": entry.get("generated_at", ""),
                "class_trust_reweight_score": reweight_score or 0.0,
                "class_trust_reweight_direction": reweight_direction or "neutral",
                "policy_debt_status": summary.get("primary_target_policy_debt_status", "none"),
                "class_normalization_status": summary.get("primary_target_class_normalization_status", "none"),
            }
        )
    return sorted(events, key=lambda item: item.get("generated_at", ""), reverse=True)


def _class_transition_events(
    history: list[dict],
    *,
    current_primary_target: dict,
    current_generated_at: str,
) -> list[dict]:
    events: list[dict] = []
    if current_primary_target and current_primary_target.get("trust_policy"):
        events.append(
            {
                "key": _queue_identity(current_primary_target),
                "class_key": _target_class_key(current_primary_target),
                "label": _target_label(current_primary_target),
                "generated_at": current_generated_at or "",
                "class_trust_reweight_score": current_primary_target.get("class_trust_reweight_score", 0.0),
                "class_trust_reweight_direction": current_primary_target.get("class_trust_reweight_direction", "neutral"),
                "class_trust_momentum_status": current_primary_target.get("class_trust_momentum_status", "insufficient-data"),
                "class_reweight_stability_status": current_primary_target.get("class_reweight_stability_status", "watch"),
                "class_reweight_transition_status": current_primary_target.get("class_reweight_transition_status", "none"),
                "class_reweight_transition_reason": current_primary_target.get("class_reweight_transition_reason", ""),
                "class_transition_health_status": current_primary_target.get("class_transition_health_status", "none"),
                "class_transition_resolution_status": current_primary_target.get("class_transition_resolution_status", "none"),
                "trust_policy": current_primary_target.get("trust_policy", "monitor"),
                "decision_memory_status": current_primary_target.get("decision_memory_status", "new"),
                "last_outcome": current_primary_target.get("last_outcome", "no-change"),
            }
        )
    historical_events: list[dict] = []
    for entry in history[: HISTORY_WINDOW_RUNS - 1]:
        summary = entry.get("operator_summary") or {}
        primary_target = summary.get("primary_target") or {}
        if not primary_target:
            continue
        historical_events.append(
            {
                "key": _queue_identity(primary_target),
                "class_key": _target_class_key(primary_target),
                "label": _target_label(primary_target),
                "generated_at": entry.get("generated_at", ""),
                "class_trust_reweight_score": summary.get(
                    "primary_target_class_trust_reweight_score",
                    primary_target.get("class_trust_reweight_score", 0.0),
                ),
                "class_trust_reweight_direction": summary.get(
                    "primary_target_class_trust_reweight_direction",
                    primary_target.get("class_trust_reweight_direction", "neutral"),
                ),
                "class_trust_momentum_status": summary.get(
                    "primary_target_class_trust_momentum_status",
                    primary_target.get("class_trust_momentum_status", "insufficient-data"),
                ),
                "class_reweight_stability_status": summary.get(
                    "primary_target_class_reweight_stability_status",
                    primary_target.get("class_reweight_stability_status", "watch"),
                ),
                "class_reweight_transition_status": summary.get(
                    "primary_target_class_reweight_transition_status",
                    primary_target.get("class_reweight_transition_status", "none"),
                ),
                "class_reweight_transition_reason": summary.get(
                    "primary_target_class_reweight_transition_reason",
                    primary_target.get("class_reweight_transition_reason", ""),
                ),
                "class_transition_health_status": summary.get(
                    "primary_target_class_transition_health_status",
                    primary_target.get("class_transition_health_status", "none"),
                ),
                "class_transition_resolution_status": summary.get(
                    "primary_target_class_transition_resolution_status",
                    primary_target.get("class_transition_resolution_status", "none"),
                ),
                "trust_policy": summary.get(
                    "primary_target_trust_policy",
                    primary_target.get("trust_policy", "monitor"),
                ),
                "decision_memory_status": summary.get(
                    "decision_memory_status",
                    primary_target.get("decision_memory_status", "new"),
                ),
                "last_outcome": summary.get(
                    "primary_target_last_outcome",
                    primary_target.get("last_outcome", "no-change"),
                ),
            }
        )
    historical_events.sort(key=lambda item: item.get("generated_at", ""), reverse=True)
    return events + historical_events


def _target_class_transition_history(target: dict, transition_events: list[dict]) -> dict:
    class_key = _target_class_key(target)
    matching_events = [event for event in transition_events if event.get("class_key") == class_key][
        : CLASS_PENDING_RESOLUTION_WINDOW_RUNS + 1
    ]
    statuses = [event.get("class_reweight_transition_status", "none") or "none" for event in matching_events]
    scores = [float(event.get("class_trust_reweight_score", 0.0) or 0.0) for event in matching_events]
    target_policies = [
        policy
        for policy in (
            event.get("trust_policy")
            for event in matching_events[:CLASS_TRANSITION_CLOSURE_WINDOW_RUNS]
        )
        if policy
    ]
    directions = [
        _normalized_class_reweight_direction(
            event.get("class_trust_reweight_direction", "neutral"),
            event.get("class_trust_reweight_score", 0.0),
        )
        for event in matching_events
    ]
    health_statuses = [
        event.get("class_transition_health_status", "none") or "none"
        for event in matching_events
    ]
    resolution_statuses = [
        event.get("class_transition_resolution_status", "none") or "none"
        for event in matching_events
    ]
    current_status = statuses[0] if statuses else "none"
    class_transition_age_runs = 0
    current_strengthening = False
    recent_pending_status = "none"
    recent_pending_age_runs = 0
    recent_pending_direction = "neutral"

    if current_status in {"pending-support", "pending-caution"}:
        class_transition_age_runs = _consecutive_transition_runs(statuses, current_status)
        current_strengthening = _current_transition_strengthening(
            current_status,
            scores[:class_transition_age_runs],
        )
    elif len(statuses) > 1 and statuses[1] in {"pending-support", "pending-caution"}:
        recent_pending_status = statuses[1]
        recent_pending_age_runs = _consecutive_transition_runs(statuses[1:], recent_pending_status)
        recent_pending_direction = _pending_transition_direction(recent_pending_status)
        class_transition_age_runs = recent_pending_age_runs
    elif current_status == "none":
        class_transition_age_runs = 0

    if current_status in {"pending-support", "pending-caution"}:
        recent_pending_status = current_status
        recent_pending_age_runs = class_transition_age_runs
        recent_pending_direction = _pending_transition_direction(current_status)

    current_direction = directions[0] if directions else "neutral"
    current_score = scores[0] if scores else 0.0
    current_neutral = abs(current_score) < 0.10 or current_direction == "neutral"
    pending_direction = recent_pending_direction if recent_pending_direction != "neutral" else _pending_transition_direction(current_status)
    current_reversed = (
        pending_direction != "neutral"
        and current_direction != "neutral"
        and current_direction != pending_direction
    )
    current_lost_pending_support = False
    if recent_pending_status == "pending-support" and current_status not in {"pending-support", "confirmed-support"}:
        current_lost_pending_support = current_score < 0.20 or current_direction != "supporting-normalization"
    if recent_pending_status == "pending-caution" and current_status not in {"pending-caution", "confirmed-caution"}:
        current_lost_pending_support = current_score > -0.20 or current_direction != "supporting-caution"
    if current_status == "pending-support" and len(scores) > 1:
        transition_score_delta = _clamp_round(scores[0] - scores[1], lower=-0.95, upper=0.95)
    elif current_status == "pending-caution" and len(scores) > 1:
        transition_score_delta = _clamp_round(scores[1] - scores[0], lower=-0.95, upper=0.95)
    else:
        transition_score_delta = 0.0
    return {
        "class_transition_age_runs": class_transition_age_runs,
        "recent_transition_path": " -> ".join(statuses),
        "recent_transition_score_path": " -> ".join(f"{score:.2f}" for score in scores[:CLASS_TRANSITION_CLOSURE_WINDOW_RUNS]),
        "current_transition_status": current_status,
        "current_transition_health_status": health_statuses[0] if health_statuses else "none",
        "current_transition_resolution_status": resolution_statuses[0] if resolution_statuses else "none",
        "recent_pending_status": recent_pending_status,
        "recent_pending_age_runs": recent_pending_age_runs,
        "current_transition_strengthening": current_strengthening,
        "current_transition_direction": current_direction,
        "current_transition_score": current_score,
        "transition_score_delta": transition_score_delta,
        "matching_transition_event_count": len(matching_events),
        "recent_policy_flip_count": _policy_flip_count(target_policies),
        "recent_reopened": any(
            event.get("decision_memory_status") == "reopened" or event.get("last_outcome") == "reopened"
            for event in matching_events[:CLASS_TRANSITION_CLOSURE_WINDOW_RUNS]
        ),
        "current_transition_neutral": current_neutral,
        "current_transition_reversed": current_reversed,
        "current_lost_pending_support": current_lost_pending_support,
    }


def _consecutive_transition_runs(statuses: list[str], target_status: str) -> int:
    count = 0
    for status in statuses:
        if status != target_status:
            break
        count += 1
    return count


def _pending_transition_direction(transition_status: str) -> str:
    if transition_status == "pending-support":
        return "supporting-normalization"
    if transition_status == "pending-caution":
        return "supporting-caution"
    return "neutral"


def _current_transition_strengthening(transition_status: str, scores: list[float]) -> bool:
    if not scores:
        return False
    if len(scores) == 1:
        return True
    current_score = scores[0]
    previous_score = scores[1]
    if transition_status == "pending-support":
        return current_score - previous_score >= 0.05
    if transition_status == "pending-caution":
        return previous_score - current_score >= 0.05
    return False


def _transition_closure_confidence_for_target(
    target: dict,
    history_meta: dict,
) -> tuple[float, str, str, list[str]]:
    transition_status = target.get("class_reweight_transition_status", "none")
    health_status = target.get(
        "class_transition_health_status",
        history_meta.get("current_transition_health_status", "none"),
    )
    resolution_status = target.get(
        "class_transition_resolution_status",
        history_meta.get("current_transition_resolution_status", "none"),
    )
    momentum_status = target.get("class_trust_momentum_status", "insufficient-data")
    stability_status = target.get("class_reweight_stability_status", "watch")
    reweight_score = float(target.get("class_trust_reweight_score", 0.0) or 0.0)
    transition_age_runs = int(target.get("class_transition_age_runs", history_meta.get("class_transition_age_runs", 0)) or 0)
    transition_score_delta = float(history_meta.get("transition_score_delta", 0.0) or 0.0)
    current_strengthening = history_meta.get("current_transition_strengthening", False)
    active_pending = transition_status in {"pending-support", "pending-caution"}
    local_noise = _target_specific_normalization_noise(target, history_meta)
    blocked = (
        transition_status == "blocked"
        or health_status == "blocked"
        or resolution_status == "blocked"
        or (transition_status == "pending-support" and local_noise)
    )
    matching_momentum = (
        transition_status == "pending-support" and momentum_status == "sustained-support"
    ) or (
        transition_status == "pending-caution" and momentum_status == "sustained-caution"
    )

    if not active_pending:
        if blocked:
            blocked_reason = (
                target.get("class_transition_resolution_reason")
                or target.get("class_transition_health_reason")
                or "Local target instability is preventing positive class strengthening."
            )
            return 0.05, "low", "blocked", [blocked_reason]
        return 0.05, "low", "none", []

    if history_meta.get("matching_transition_event_count", 0) < 2:
        return (
            0.25,
            "low",
            "insufficient-data",
            ["Not enough pending-transition history exists yet to judge whether this class signal is likely to confirm."],
        )

    score = 0.25
    if health_status == "building":
        score += 0.15
    if matching_momentum:
        score += 0.10
    if stability_status == "stable":
        score += 0.10
    if transition_score_delta >= 0.05:
        score += 0.10
    if transition_age_runs in {1, 2}:
        score += 0.05
    if health_status == "holding":
        score -= 0.10
    if health_status == "stalled":
        score -= 0.20
    if transition_age_runs >= 3 and not current_strengthening:
        score -= 0.10
    if abs(reweight_score) < 0.10:
        score -= 0.10
    if momentum_status == "reversing":
        score -= 0.10
    if blocked:
        score -= 0.20

    score = _clamp_round(score, lower=0.05, upper=0.95)
    if score >= 0.75:
        label = "high"
    elif score >= 0.45:
        label = "medium"
    else:
        label = "low"

    if blocked:
        outcome = "blocked"
    elif transition_age_runs >= 3 and not current_strengthening:
        outcome = "expire-risk"
    elif label == "high" and matching_momentum:
        outcome = "confirm-soon"
    elif label == "low" and (
        abs(reweight_score) < 0.10
        or history_meta.get("current_lost_pending_support", False)
        or history_meta.get("current_transition_neutral", False)
        or history_meta.get("current_transition_reversed", False)
    ):
        outcome = "clear-risk"
    elif label == "medium":
        outcome = "hold"
    else:
        outcome = "hold"

    reasons: list[str] = []
    health_reason = target.get("class_transition_health_reason", "")
    if health_status == "building":
        reasons.append(health_reason or "The pending class signal is still building in the same direction.")
    elif health_status == "holding":
        reasons.append(health_reason or "The pending class signal is still visible, but it is no longer getting stronger.")
    elif health_status == "stalled":
        reasons.append(health_reason or "The pending class signal has lingered without enough strengthening.")
    elif health_status == "blocked":
        reasons.append(health_reason or "Local target instability is blocking this pending class transition.")

    if matching_momentum:
        reasons.append("Recent class momentum is still aligned with the pending direction.")
    elif stability_status == "stable":
        reasons.append("Class guidance is stable even though the pending signal has not confirmed yet.")
    elif momentum_status == "reversing":
        reasons.append("Recent class momentum is reversing against the pending direction.")

    if transition_score_delta >= 0.05:
        reasons.append(f"The reweight score improved by {transition_score_delta:.2f} in the pending direction.")
    elif transition_age_runs >= 3 and not current_strengthening:
        reasons.append("The pending signal has lasted three or more runs without same-direction strengthening.")
    elif abs(reweight_score) < 0.10:
        reasons.append("The live reweight score is now close to neutral.")

    if blocked:
        reasons.append(
            target.get("class_transition_resolution_reason")
            or health_reason
            or "Local target instability is still overriding positive class strengthening."
        )

    return score, label, outcome, reasons[:4]


def _apply_transition_closure_control(
    target: dict,
    *,
    trust_policy: str,
    trust_policy_reason: str,
    health_status: str,
    health_reason: str,
    resolution_status: str,
    resolution_reason: str,
    transition_status: str,
    transition_reason: str,
    policy_debt_status: str,
    policy_debt_reason: str,
    class_normalization_status: str,
    class_normalization_reason: str,
    closure_confidence_label: str,
    closure_likely_outcome: str,
    pending_debt_status: str,
) -> tuple[str, str, str, str, str, str, str, str, str, str, str, str]:
    if (
        transition_status in {"pending-support", "pending-caution"}
        and closure_likely_outcome in {"clear-risk", "expire-risk"}
        and closure_confidence_label == "low"
        and pending_debt_status == "active-debt"
    ):
        clear_reason = (
            "This pending class signal is low-confidence inside a class that keeps accumulating unresolved pending states, so the pending state was cleared back to the weaker posture."
        )
        if transition_status == "pending-support":
            reverted_policy = target.get("pre_class_normalization_trust_policy", trust_policy)
            reverted_reason = target.get("pre_class_normalization_trust_policy_reason", trust_policy_reason)
            return (
                "none",
                "",
                "cleared",
                clear_reason,
                "none",
                clear_reason,
                reverted_policy,
                clear_reason if reverted_policy == "verify-first" else reverted_reason,
                policy_debt_status,
                policy_debt_reason,
                "candidate",
                clear_reason,
            )
        return (
            "none",
            "",
            "cleared",
            clear_reason,
            "none",
            clear_reason,
            trust_policy,
            trust_policy_reason,
            "watch",
            clear_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    return (
        health_status,
        health_reason,
        resolution_status,
        resolution_reason,
        transition_status,
        transition_reason,
        trust_policy,
        trust_policy_reason,
        policy_debt_status,
        policy_debt_reason,
        class_normalization_status,
        class_normalization_reason,
    )


def _class_pending_debt_for_target(
    target: dict,
    transition_events: list[dict],
) -> tuple[str, str, float, float, str]:
    class_key = _target_class_key(target)
    matching_events = [event for event in transition_events if event.get("class_key") == class_key][
        : CLASS_PENDING_DEBT_WINDOW_RUNS
    ]
    outcomes = [_pending_debt_event_outcome(event) for event in matching_events]
    relevant_outcomes = [outcome for outcome in outcomes if outcome != "none"]
    pending_entry_count = len(relevant_outcomes)
    confirmed_count = sum(1 for outcome in relevant_outcomes if outcome == "confirmed")
    cleared_count = sum(1 for outcome in relevant_outcomes if outcome == "cleared")
    expired_count = sum(1 for outcome in relevant_outcomes if outcome == "expired")
    stalled_count = sum(1 for outcome in relevant_outcomes if outcome == "stalled")
    blocked_count = sum(1 for outcome in relevant_outcomes if outcome == "blocked")
    debt_like_count = stalled_count + expired_count + blocked_count
    healthy_resolution_count = confirmed_count + cleared_count
    class_pending_debt_rate = _clamp_round(
        debt_like_count / max(pending_entry_count, 1),
        lower=0.0,
        upper=1.0,
    )
    class_pending_resolution_rate = _clamp_round(
        healthy_resolution_count / max(pending_entry_count, 1),
        lower=0.0,
        upper=1.0,
    )
    recent_pending_debt_path = " -> ".join(relevant_outcomes[:4])

    if pending_entry_count >= 3 and (
        debt_like_count >= healthy_resolution_count + 1 or class_pending_debt_rate >= 0.60
    ):
        return (
            "active-debt",
            "This class keeps accumulating stalled, expired, or blocked pending transitions, so new pending signals should be treated more cautiously.",
            class_pending_debt_rate,
            class_pending_resolution_rate,
            recent_pending_debt_path,
        )
    if pending_entry_count >= 2 and (
        healthy_resolution_count >= debt_like_count + 1 or class_pending_resolution_rate >= 0.60
    ):
        return (
            "clearing",
            "This class is resolving pending transitions more cleanly again, so newer pending signals are less likely to linger indefinitely.",
            class_pending_debt_rate,
            class_pending_resolution_rate,
            recent_pending_debt_path,
        )
    if pending_entry_count >= 2:
        return (
            "watch",
            "This class has mixed recent pending-transition outcomes, so watch whether new pending signals resolve cleanly or start to accumulate debt.",
            class_pending_debt_rate,
            class_pending_resolution_rate,
            recent_pending_debt_path,
        )
    return "none", "", class_pending_debt_rate, class_pending_resolution_rate, recent_pending_debt_path


def _pending_debt_event_outcome(event: dict) -> str:
    resolution_status = event.get("class_transition_resolution_status", "none")
    health_status = event.get("class_transition_health_status", "none")
    transition_status = event.get("class_reweight_transition_status", "none")
    if resolution_status == "confirmed":
        return "confirmed"
    if resolution_status == "cleared":
        return "cleared"
    if resolution_status == "expired":
        return "expired"
    if resolution_status == "blocked" or health_status == "blocked" or transition_status == "blocked":
        return "blocked"
    if health_status == "stalled":
        return "stalled"
    if transition_status in {"pending-support", "pending-caution"} or health_status in {"building", "holding"}:
        return "pending"
    return "none"


def _class_pending_debt_hotspots(resolution_targets: list[dict], *, mode: str) -> list[dict]:
    grouped: dict[str, dict] = {}
    for target in resolution_targets:
        class_key = _target_class_key(target)
        if not class_key:
            continue
        dominant_count = target.get("class_pending_debt_rate", 0.0)
        if mode == "healthy":
            dominant_count = target.get("class_pending_resolution_rate", 0.0)
        current = {
            "scope": "class",
            "label": class_key,
            "class_pending_debt_status": target.get("class_pending_debt_status", "none"),
            "class_pending_debt_rate": target.get("class_pending_debt_rate", 0.0),
            "class_pending_resolution_rate": target.get("class_pending_resolution_rate", 0.0),
            "recent_pending_debt_path": target.get("recent_pending_debt_path", ""),
            "dominant_count": dominant_count,
            "pending_entry_count": len(
                [part for part in (target.get("recent_pending_debt_path", "") or "").split(" -> ") if part]
            ),
        }
        existing = grouped.get(class_key)
        if existing is None or current["dominant_count"] > existing["dominant_count"]:
            grouped[class_key] = current

    hotspots = list(grouped.values())
    if mode == "healthy":
        hotspots = [
            item for item in hotspots if item.get("class_pending_debt_status") == "clearing"
        ]
        hotspots.sort(
            key=lambda item: (
                -item.get("class_pending_resolution_rate", 0.0),
                -item.get("pending_entry_count", 0),
                item.get("label", ""),
            )
        )
    else:
        hotspots = [
            item for item in hotspots if item.get("class_pending_debt_status") == "active-debt"
        ]
        hotspots.sort(
            key=lambda item: (
                -item.get("class_pending_debt_rate", 0.0),
                -item.get("pending_entry_count", 0),
                item.get("label", ""),
            )
        )
    return hotspots[:5]


def _pending_debt_freshness_for_target(target: dict, transition_events: list[dict]) -> dict:
    class_key = _target_class_key(target)
    class_events = [event for event in transition_events if event.get("class_key") == class_key]
    relevant_events: list[tuple[dict, str]] = []
    for event in class_events:
        outcome = _pending_debt_event_outcome(event)
        if outcome == "none":
            continue
        relevant_events.append((event, outcome))
        if len(relevant_events) >= CLASS_PENDING_DEBT_WINDOW_RUNS:
            break

    weighted_pending_entry_count = 0.0
    weighted_debt_like = 0.0
    weighted_healthy_resolution = 0.0
    recent_pending_weight = 0.0
    recent_outcomes = [outcome for _, outcome in relevant_events[:PENDING_DEBT_FRESHNESS_WINDOW_RUNS]]
    for index, (_event, outcome) in enumerate(relevant_events):
        weight = CLASS_MEMORY_RECENCY_WEIGHTS[min(index, HISTORY_WINDOW_RUNS - 1)]
        weighted_pending_entry_count += weight
        if index < PENDING_DEBT_FRESHNESS_WINDOW_RUNS:
            recent_pending_weight += weight
        if outcome in {"stalled", "expired", "blocked"}:
            weighted_debt_like += weight
        if outcome in {"confirmed", "cleared"}:
            weighted_healthy_resolution += weight

    recent_window_weight_share = recent_pending_weight / max(weighted_pending_entry_count, 1.0)
    freshness_status = _pending_debt_freshness_status(
        weighted_pending_entry_count,
        recent_window_weight_share,
    )
    decayed_pending_debt_rate = weighted_debt_like / max(weighted_pending_entry_count, 1.0)
    decayed_pending_resolution_rate = weighted_healthy_resolution / max(weighted_pending_entry_count, 1.0)
    return {
        "pending_debt_freshness_status": freshness_status,
        "pending_debt_freshness_reason": _pending_debt_freshness_reason(
            freshness_status,
            weighted_pending_entry_count,
            recent_window_weight_share,
            decayed_pending_debt_rate,
            decayed_pending_resolution_rate,
        ),
        "pending_debt_memory_weight": round(recent_window_weight_share, 2),
        "decayed_pending_debt_rate": round(decayed_pending_debt_rate, 2),
        "decayed_pending_resolution_rate": round(decayed_pending_resolution_rate, 2),
        "recent_pending_signal_mix": _recent_pending_signal_mix(
            weighted_pending_entry_count,
            weighted_debt_like,
            weighted_healthy_resolution,
            recent_window_weight_share,
        ),
        "recent_pending_debt_path": " -> ".join(recent_outcomes),
    }


def _pending_debt_freshness_status(weighted_pending_entry_count: float, recent_window_weight_share: float) -> str:
    if weighted_pending_entry_count < 2.0:
        return "insufficient-data"
    if recent_window_weight_share >= 0.60:
        return "fresh"
    if recent_window_weight_share >= 0.35:
        return "mixed-age"
    return "stale"


def _pending_debt_freshness_reason(
    freshness_status: str,
    weighted_pending_entry_count: float,
    recent_window_weight_share: float,
    decayed_pending_debt_rate: float,
    decayed_pending_resolution_rate: float,
) -> str:
    if freshness_status == "fresh":
        return (
            "Recent pending-transition evidence is still current enough to trust, with "
            f"{recent_window_weight_share:.0%} of the weighted signal coming from the latest {PENDING_DEBT_FRESHNESS_WINDOW_RUNS} runs."
        )
    if freshness_status == "mixed-age":
        return (
            "Pending-transition memory is still useful, but it is partly aging: "
            f"{recent_window_weight_share:.0%} of the weighted signal is recent and the rest is older carry-forward."
        )
    if freshness_status == "stale":
        return (
            "Older pending-debt patterns are now carrying more of the signal than recent runs, so they should not dominate closure forecasting."
        )
    return (
        "Pending-transition memory is still too lightly exercised to judge freshness, with "
        f"{weighted_pending_entry_count:.2f} weighted pending-entry run(s), "
        f"{decayed_pending_debt_rate:.0%} debt-like signal, and {decayed_pending_resolution_rate:.0%} healthy-resolution signal."
    )


def _recent_pending_signal_mix(
    weighted_pending_entry_count: float,
    weighted_debt_like: float,
    weighted_healthy_resolution: float,
    recent_window_weight_share: float,
) -> str:
    return (
        f"{weighted_pending_entry_count:.2f} weighted pending-entry run(s) with "
        f"{weighted_debt_like:.2f} debt-like, {weighted_healthy_resolution:.2f} healthy-resolution, "
        f"and {recent_window_weight_share:.0%} of the signal from the freshest runs."
    )


def _closure_forecast_reweight_scores_for_target(
    target: dict,
    transition_history_meta: dict,
    pending_history_meta: dict,
) -> tuple[float, float, float, str, list[str]]:
    transition_status = target.get("class_reweight_transition_status", "none")
    if transition_status not in {"pending-support", "pending-caution"}:
        return 0.0, 0.0, 0.0, "neutral", []

    freshness_status = pending_history_meta.get("pending_debt_freshness_status", "insufficient-data")
    freshness_multiplier = {
        "fresh": 1.00,
        "mixed-age": 0.65,
        "stale": 0.35,
        "insufficient-data": 0.20,
    }.get(freshness_status, 0.20)
    transition_score_delta = float(transition_history_meta.get("transition_score_delta", 0.0) or 0.0)
    health_status = target.get("class_transition_health_status", "none")
    likely_outcome = target.get("transition_closure_likely_outcome", "none")
    pending_debt_status = target.get("class_pending_debt_status", "none")
    local_noise = _target_specific_normalization_noise(target, transition_history_meta)
    matching_transition_strengthening = (
        transition_status == "pending-support" and transition_score_delta >= 0.05
    ) or (
        transition_status == "pending-caution" and transition_score_delta >= 0.05
    )

    support_adjustments = 0.0
    if likely_outcome == "confirm-soon":
        support_adjustments += 0.10
    if health_status == "building":
        support_adjustments += 0.10
    if target.get("class_reweight_stability_status", "watch") == "stable":
        support_adjustments += 0.05
    if matching_transition_strengthening:
        support_adjustments += 0.05
    if health_status in {"stalled", "expired"}:
        support_adjustments -= 0.10
    if local_noise:
        support_adjustments -= 0.10

    caution_adjustments = 0.0
    if pending_debt_status == "active-debt":
        caution_adjustments += 0.10
    if likely_outcome in {"clear-risk", "expire-risk"}:
        caution_adjustments += 0.10
    if health_status == "holding":
        caution_adjustments += 0.05
    if int(target.get("class_transition_age_runs", 0) or 0) >= 3 and not transition_history_meta.get(
        "current_transition_strengthening",
        False,
    ):
        caution_adjustments += 0.05
    if pending_debt_status == "clearing":
        caution_adjustments -= 0.10
    if target.get("class_transition_resolution_status", "none") == "confirmed":
        caution_adjustments -= 0.05

    support_score = _clamp_round(
        pending_history_meta.get("decayed_pending_resolution_rate", 0.0) * freshness_multiplier
        + support_adjustments,
        lower=0.0,
        upper=0.95,
    )
    caution_score = _clamp_round(
        pending_history_meta.get("decayed_pending_debt_rate", 0.0) * freshness_multiplier
        + caution_adjustments,
        lower=0.0,
        upper=0.95,
    )
    reweight_score = _clamp_round(
        support_score - caution_score,
        lower=-0.95,
        upper=0.95,
    )
    if reweight_score >= 0.20:
        direction = "supporting-confirmation"
    elif reweight_score <= -0.20:
        direction = "supporting-clearance"
    else:
        direction = "neutral"

    reasons: list[str] = []
    freshness_reason = pending_history_meta.get("pending_debt_freshness_reason", "")
    if freshness_reason:
        reasons.append(freshness_reason)
    if likely_outcome == "confirm-soon":
        reasons.append("Recent class resolution behavior is still strong enough that this pending signal could confirm soon.")
    elif health_status == "building":
        reasons.append("The live pending signal is still building in the same direction.")
    elif target.get("class_reweight_stability_status", "watch") == "stable":
        reasons.append("Class transition stability is still good enough to keep the pending forecast coherent.")
    if pending_debt_status == "active-debt":
        reasons.append("Fresh unresolved pending debt is still clustering in this class.")
    elif likely_outcome in {"clear-risk", "expire-risk"}:
        reasons.append("The live pending signal is already leaning toward clearance or expiry risk.")
    elif health_status == "holding":
        reasons.append("The live pending signal is holding instead of strengthening.")
    if local_noise:
        reasons.append("Local target instability is still limiting how much class evidence can strengthen the pending forecast.")
    return support_score, caution_score, reweight_score, direction, reasons[:4]


def _apply_closure_forecast_reweighting_control(
    target: dict,
    *,
    transition_history_meta: dict,
    trust_policy: str,
    trust_policy_reason: str,
    transition_status: str,
    transition_reason: str,
    resolution_status: str,
    resolution_reason: str,
    pending_debt_status: str,
    pending_debt_reason: str,
    policy_debt_status: str,
    policy_debt_reason: str,
    class_normalization_status: str,
    class_normalization_reason: str,
    closure_confidence_label: str,
    closure_likely_outcome: str,
    pending_debt_freshness_status: str,
    closure_forecast_reweight_direction: str,
    closure_forecast_reweight_score: float,
) -> tuple[str, str, str, str, str, str, str, str, str, str, str, str, str, str, str]:
    effect = "none"
    effect_reason = ""
    local_noise = _target_specific_normalization_noise(target, transition_history_meta)
    transition_age_runs = int(target.get("class_transition_age_runs", 0) or 0)
    current_strengthening = transition_history_meta.get("current_transition_strengthening", False)

    if transition_status not in {"pending-support", "pending-caution"}:
        return (
            effect,
            effect_reason,
            closure_likely_outcome,
            transition_status,
            transition_reason,
            resolution_status,
            resolution_reason,
            trust_policy,
            trust_policy_reason,
            pending_debt_status,
            pending_debt_reason,
            policy_debt_status,
            policy_debt_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    if closure_forecast_reweight_direction == "supporting-confirmation":
        if pending_debt_freshness_status == "fresh" and not local_noise and pending_debt_status != "clearing":
            effect = "confirm-support-strengthened"
            effect_reason = (
                "Fresh class resolution behavior is clean enough to strengthen the pending forecast, but the pending state still needs Phase 39 persistence before it can confirm."
            )
        elif pending_debt_freshness_status in {"stale", "insufficient-data"}:
            effect = "confirm-support-softened"
            effect_reason = (
                "Older pending-transition evidence is aging out, so it cannot keep strengthening confirmation support from scratch."
            )
            if closure_likely_outcome == "confirm-soon":
                closure_likely_outcome = "hold"
    elif closure_forecast_reweight_direction == "supporting-clearance":
        if pending_debt_freshness_status in {"fresh", "mixed-age"}:
            effect = "clear-risk-strengthened"
            effect_reason = (
                "Fresh unresolved pending debt is still clustering, so the live pending signal should be treated as more likely to clear or expire than confirm."
            )
            if closure_likely_outcome not in {"blocked", "insufficient-data"}:
                closure_likely_outcome = "expire-risk" if transition_age_runs >= 3 and not current_strengthening else "clear-risk"
        else:
            effect = "clear-risk-softened"
            effect_reason = (
                "Older pending-debt patterns are fading, so they should not strengthen clearance risk from scratch."
            )

    if (
        transition_status in {"pending-support", "pending-caution"}
        and closure_forecast_reweight_direction == "supporting-clearance"
        and closure_confidence_label == "low"
        and pending_debt_status == "active-debt"
    ):
        clear_reason = (
            "This pending class signal is low-confidence inside a class with fresh unresolved pending debt, so the pending state was cleared back to the weaker posture."
        )
        if transition_status == "pending-support":
            reverted_policy = target.get("pre_class_normalization_trust_policy", trust_policy)
            reverted_reason = target.get("pre_class_normalization_trust_policy_reason", trust_policy_reason)
            return (
                "clear-risk-strengthened",
                clear_reason,
                closure_likely_outcome,
                "none",
                "",
                "cleared",
                clear_reason,
                reverted_policy,
                clear_reason if reverted_policy == "verify-first" else reverted_reason,
                pending_debt_status,
                pending_debt_reason,
                policy_debt_status,
                policy_debt_reason,
                "candidate",
                clear_reason,
            )
        return (
            "clear-risk-strengthened",
            clear_reason,
            closure_likely_outcome,
            "none",
            "",
            "cleared",
            clear_reason,
            trust_policy,
            trust_policy_reason,
            pending_debt_status,
            pending_debt_reason,
            "watch",
            clear_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    if local_noise and closure_forecast_reweight_direction == "supporting-confirmation":
        effect = "confirm-support-softened"
        effect_reason = (
            "Local target instability is still overriding healthier class evidence, so the pending forecast cannot strengthen beyond the existing posture."
        )
        if closure_likely_outcome == "confirm-soon":
            closure_likely_outcome = "hold"

    return (
        effect,
        effect_reason,
        closure_likely_outcome,
        transition_status,
        transition_reason,
        resolution_status,
        resolution_reason,
        trust_policy,
        trust_policy_reason,
        pending_debt_status,
        pending_debt_reason,
        policy_debt_status,
        policy_debt_reason,
        class_normalization_status,
        class_normalization_reason,
    )


def _pending_debt_freshness_hotspots(resolution_targets: list[dict], *, mode: str) -> list[dict]:
    grouped: dict[str, dict] = {}
    for target in resolution_targets:
        class_key = _target_class_key(target)
        if not class_key:
            continue
        current = {
            "scope": "class",
            "label": class_key,
            "pending_debt_freshness_status": target.get("pending_debt_freshness_status", "insufficient-data"),
            "decayed_pending_debt_rate": target.get("decayed_pending_debt_rate", 0.0),
            "decayed_pending_resolution_rate": target.get("decayed_pending_resolution_rate", 0.0),
            "recent_pending_signal_mix": target.get("recent_pending_signal_mix", ""),
            "recent_pending_debt_path": target.get("recent_pending_debt_path", ""),
            "dominant_count": target.get("decayed_pending_debt_rate", 0.0),
            "pending_entry_count": len(
                [part for part in (target.get("recent_pending_debt_path", "") or "").split(" -> ") if part]
            ),
        }
        if mode == "fresh":
            current["dominant_count"] = target.get("decayed_pending_resolution_rate", 0.0)
        existing = grouped.get(class_key)
        if existing is None or current["dominant_count"] > existing["dominant_count"]:
            grouped[class_key] = current

    hotspots = list(grouped.values())
    if mode == "fresh":
        hotspots = [
            item
            for item in hotspots
            if item.get("pending_debt_freshness_status") == "fresh"
            and item.get("decayed_pending_resolution_rate", 0.0) > 0.0
        ]
        hotspots.sort(
            key=lambda item: (
                -item.get("decayed_pending_resolution_rate", 0.0),
                -item.get("pending_entry_count", 0),
                item.get("label", ""),
            )
        )
    else:
        hotspots = [
            item
            for item in hotspots
            if item.get("pending_debt_freshness_status") == "stale"
            and item.get("decayed_pending_debt_rate", 0.0) > 0.0
        ]
        hotspots.sort(
            key=lambda item: (
                -item.get("decayed_pending_debt_rate", 0.0),
                -item.get("pending_entry_count", 0),
                item.get("label", ""),
            )
        )
    return hotspots[:5]


def _closure_forecast_hotspots(resolution_targets: list[dict], *, mode: str) -> list[dict]:
    grouped: dict[str, dict] = {}
    for target in resolution_targets:
        class_key = _target_class_key(target)
        if not class_key:
            continue
        current = {
            "scope": "class",
            "label": class_key,
            "closure_forecast_reweight_direction": target.get("closure_forecast_reweight_direction", "neutral"),
            "weighted_pending_resolution_support_score": target.get("weighted_pending_resolution_support_score", 0.0),
            "weighted_pending_debt_caution_score": target.get("weighted_pending_debt_caution_score", 0.0),
            "recent_pending_signal_mix": target.get("recent_pending_signal_mix", ""),
            "recent_pending_debt_path": target.get("recent_pending_debt_path", ""),
            "pending_entry_count": len(
                [part for part in (target.get("recent_pending_debt_path", "") or "").split(" -> ") if part]
            ),
        }
        current["dominant_count"] = current["weighted_pending_resolution_support_score"]
        if mode == "caution":
            current["dominant_count"] = current["weighted_pending_debt_caution_score"]
        existing = grouped.get(class_key)
        if existing is None or current["dominant_count"] > existing["dominant_count"]:
            grouped[class_key] = current

    hotspots = list(grouped.values())
    if mode == "support":
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reweight_direction") == "supporting-confirmation"
        ]
        hotspots.sort(
            key=lambda item: (
                -item.get("weighted_pending_resolution_support_score", 0.0),
                -item.get("pending_entry_count", 0),
                item.get("label", ""),
            )
        )
    else:
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reweight_direction") == "supporting-clearance"
        ]
        hotspots.sort(
            key=lambda item: (
                -item.get("weighted_pending_debt_caution_score", 0.0),
                -item.get("pending_entry_count", 0),
                item.get("label", ""),
            )
        )
    return hotspots[:5]


def _transition_closure_confidence_summary(
    primary_target: dict,
    pending_debt_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    likely_outcome = primary_target.get("transition_closure_likely_outcome", "none")
    score = primary_target.get("transition_closure_confidence_score", 0.05)
    if likely_outcome == "confirm-soon":
        return f"{label} still has a pending class signal that looks strong enough to confirm soon if the next run stays aligned ({score:.2f})."
    if likely_outcome == "hold":
        return f"{label} still has a viable pending class signal, but it is not strong enough to trust fully yet ({score:.2f})."
    if likely_outcome == "clear-risk":
        return f"{label} has a pending class signal that is fading and may clear before it confirms ({score:.2f})."
    if likely_outcome == "expire-risk":
        return f"{label} has a pending class signal that has lingered long enough to risk aging out ({score:.2f})."
    if likely_outcome == "blocked":
        reasons = primary_target.get("transition_closure_confidence_reasons") or []
        return reasons[0] if reasons else f"{label} still has local target instability blocking positive class strengthening."
    if likely_outcome == "insufficient-data":
        return f"{label} still has too little pending-transition history to judge whether the class signal is likely to confirm."
    if pending_debt_hotspots:
        hotspot = pending_debt_hotspots[0]
        return (
            f"Pending class signals are accumulating unresolved debt most around {hotspot.get('label', 'recent hotspots')}, "
            "so new pending states there should be treated more cautiously."
        )
    return "No active pending class transition needs closure-confidence scoring right now."


def _class_pending_debt_summary(
    primary_target: dict,
    pending_debt_hotspots: list[dict],
    healthy_pending_resolution_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    status = primary_target.get("class_pending_debt_status", "none")
    if status == "active-debt":
        return f"{label} belongs to a class that keeps accumulating unresolved pending transitions, so fresh pending signals there should be treated more cautiously."
    if status == "clearing":
        return f"{label} belongs to a class that is resolving pending transitions more cleanly again, so pending debt is easing."
    if status == "watch":
        return f"{label} belongs to a class with mixed pending-transition outcomes, so watch whether new pending signals confirm or start to linger."
    if pending_debt_hotspots:
        hotspot = pending_debt_hotspots[0]
        return (
            f"Pending-transition debt is accumulating most around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes should not let weak pending states linger."
        )
    if healthy_pending_resolution_hotspots:
        hotspot = healthy_pending_resolution_hotspots[0]
        return (
            f"Pending transitions are resolving most cleanly around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes are showing healthier follow-through."
        )
    return "No class pending-debt pattern is strong enough to change how pending signals are interpreted yet."


def _class_pending_resolution_summary(
    primary_target: dict,
    healthy_pending_resolution_hotspots: list[dict],
    pending_debt_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    status = primary_target.get("class_pending_debt_status", "none")
    if status == "clearing":
        return f"{label} belongs to a class that is resolving pending transitions more cleanly than it is stalling them."
    if status == "active-debt":
        return f"{label} belongs to a class where pending transitions are still stalling, expiring, or blocking more often than they resolve cleanly."
    if healthy_pending_resolution_hotspots:
        hotspot = healthy_pending_resolution_hotspots[0]
        return (
            f"Healthy pending-transition resolution is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes are proving whether pending signals can clear or confirm cleanly."
        )
    if pending_debt_hotspots:
        hotspot = pending_debt_hotspots[0]
        return (
            f"Unresolved pending-transition debt is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes should clear weak pending signals earlier."
        )
    return "No class-level pending-resolution pattern is strong enough to call out yet."


def _pending_debt_freshness_summary(
    primary_target: dict,
    stale_pending_debt_hotspots: list[dict],
    fresh_pending_resolution_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    freshness_status = primary_target.get("pending_debt_freshness_status", "insufficient-data")
    if freshness_status == "fresh":
        return f"{label} still has fresh pending-transition memory, so recent class evidence should carry most of the closure forecast."
    if freshness_status == "mixed-age":
        return f"{label} still has useful pending-transition memory, but some of that signal is aging and should be weighted more cautiously."
    if freshness_status == "stale":
        return f"{label} is leaning on older pending-debt patterns more than fresh runs, so those class signals should not dominate the closure forecast."
    if fresh_pending_resolution_hotspots:
        hotspot = fresh_pending_resolution_hotspots[0]
        return (
            f"Fresh pending-resolution evidence is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes deserve more trust than older pending-debt carry-forward."
        )
    if stale_pending_debt_hotspots:
        hotspot = stale_pending_debt_hotspots[0]
        return (
            f"Older pending-debt memory is lingering most around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes should not let stale debt dominate new pending forecasts."
        )
    return "Pending-transition memory is still too lightly exercised to say whether fresh or stale class debt should lead the forecast."


def _pending_debt_decay_summary(
    primary_target: dict,
    fresh_pending_resolution_hotspots: list[dict],
    stale_pending_debt_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    freshness_status = primary_target.get("pending_debt_freshness_status", "insufficient-data")
    resolution_rate = primary_target.get("decayed_pending_resolution_rate", 0.0)
    debt_rate = primary_target.get("decayed_pending_debt_rate", 0.0)
    if freshness_status == "fresh" and resolution_rate >= debt_rate:
        return f"Fresh pending-transition evidence for {label} is resolving more cleanly than it is stalling, so the closure forecast can lean more on recent healthy outcomes."
    if freshness_status == "fresh":
        return f"Fresh pending-transition debt for {label} is still clustering, so unresolved pending states should be treated more cautiously than older clean outcomes suggest."
    if freshness_status == "stale":
        return f"Older pending-debt patterns are being down-weighted for {label}, so stale class drag should not control the live closure forecast."
    if fresh_pending_resolution_hotspots:
        hotspot = fresh_pending_resolution_hotspots[0]
        return (
            f"Fresh pending-resolution behavior is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes are earning cleaner closure forecasts."
        )
    if stale_pending_debt_hotspots:
        hotspot = stale_pending_debt_hotspots[0]
        return (
            f"Stale pending-debt memory is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those older caution patterns should keep decaying instead of carrying forward indefinitely."
        )
    return "No strong pending-debt freshness trend is dominating the closure forecast yet."


def _closure_forecast_reweighting_summary(
    primary_target: dict,
    supporting_pending_resolution_hotspots: list[dict],
    caution_pending_debt_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    direction = primary_target.get("closure_forecast_reweight_direction", "neutral")
    effect = primary_target.get("closure_forecast_reweight_effect", "none")
    score = primary_target.get("closure_forecast_reweight_score", 0.0)
    if effect == "confirm-support-strengthened":
        return f"{label} still needs persistence before confirmation, but fresh class resolution behavior is strengthening the pending forecast ({score:.2f})."
    if effect == "confirm-support-softened":
        return f"{label} still has a pending class signal, but older pending-transition evidence is softening how much confidence that forecast deserves ({score:.2f})."
    if effect == "clear-risk-strengthened":
        return f"{label} is seeing fresher unresolved pending debt, so the live pending forecast is leaning more strongly toward clearance or expiry risk ({score:.2f})."
    if effect == "clear-risk-softened":
        return f"{label} still carries some pending-debt caution, but older debt patterns are fading instead of fully driving the forecast ({score:.2f})."
    if direction == "supporting-confirmation":
        return f"Recent class resolution behavior around {label} is clean enough to strengthen the pending forecast, but not enough to confirm it yet ({score:.2f})."
    if direction == "supporting-clearance":
        return f"Recent class pending debt around {label} is still fresh enough to push the pending forecast toward clearance or expiry risk ({score:.2f})."
    if supporting_pending_resolution_hotspots:
        hotspot = supporting_pending_resolution_hotspots[0]
        return (
            f"Fresh closure support is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes are closest to cleaner pending confirmation paths."
        )
    if caution_pending_debt_hotspots:
        hotspot = caution_pending_debt_hotspots[0]
        return (
            f"Fresh pending-debt caution is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes should keep weak pending states from lingering."
        )
    return "Class evidence is informative, but it is not strong enough to move the closure forecast by itself yet."


def _apply_closure_forecast_momentum_and_hysteresis(
    resolution_targets: list[dict],
    history: list[dict],
    *,
    current_generated_at: str,
    confidence_calibration: dict,
) -> dict:
    if not resolution_targets:
        return {
            "primary_target_transition_closure_likely_outcome": "none",
            "transition_closure_confidence_summary": "No transition-closure confidence is recorded because there is no active target.",
            "class_pending_debt_summary": "No class pending-debt signal is recorded because there is no active target.",
            "class_pending_resolution_summary": "No class pending-resolution signal is recorded because there is no active target.",
            "pending_debt_freshness_summary": "No pending-debt freshness is recorded because there is no active target.",
            "pending_debt_decay_summary": "No pending-debt decay is recorded because there is no active target.",
            "closure_forecast_reweighting_summary": "No closure-forecast reweighting is recorded because there is no active target.",
            "primary_target_closure_forecast_momentum_score": 0.0,
            "primary_target_closure_forecast_momentum_status": "insufficient-data",
            "primary_target_closure_forecast_stability_status": "watch",
            "primary_target_closure_forecast_hysteresis_status": "none",
            "primary_target_closure_forecast_hysteresis_reason": "",
            "closure_forecast_momentum_summary": "No closure-forecast momentum is recorded because there is no active target.",
            "closure_forecast_stability_summary": "No closure-forecast stability is recorded because there is no active target.",
            "closure_forecast_hysteresis_summary": "No closure-forecast hysteresis is recorded because there is no active target.",
            "closure_forecast_transition_window_runs": CLASS_CLOSURE_FORECAST_TRANSITION_WINDOW_RUNS,
            "sustained_confirmation_hotspots": [],
            "sustained_clearance_hotspots": [],
            "oscillating_closure_forecast_hotspots": [],
        }

    current_primary_target = resolution_targets[0]
    current_bucket = _recommendation_bucket(current_primary_target)
    transition_events = _class_transition_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )
    closure_forecast_events = _class_closure_forecast_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )

    updated_targets: list[dict] = []
    for target in resolution_targets:
        momentum_score = 0.0
        momentum_status = "insufficient-data"
        stability_status = "watch"
        hysteresis_status = "none"
        hysteresis_reason = ""
        recent_path = ""
        transition_closure_likely_outcome = target.get("transition_closure_likely_outcome", "none")
        transition_status = target.get("class_reweight_transition_status", "none")
        transition_reason = target.get("class_reweight_transition_reason", "")
        resolution_status = target.get("class_transition_resolution_status", "none")
        resolution_reason = target.get("class_transition_resolution_reason", "")
        trust_policy = target.get("trust_policy", "monitor")
        trust_policy_reason = target.get("trust_policy_reason", "No trust-policy reason is recorded yet.")
        pending_debt_status = target.get("class_pending_debt_status", "none")
        pending_debt_reason = target.get("class_pending_debt_reason", "")
        policy_debt_status = target.get("policy_debt_status", "none")
        policy_debt_reason = target.get("policy_debt_reason", "")
        class_normalization_status = target.get("class_normalization_status", "none")
        class_normalization_reason = target.get("class_normalization_reason", "")
        transition_history_meta: dict = {}

        if _recommendation_bucket(target) == current_bucket:
            transition_history_meta = _target_class_transition_history(target, transition_events)
            history_meta = _target_closure_forecast_history(target, closure_forecast_events)
            momentum_score = history_meta["closure_forecast_momentum_score"]
            momentum_status = history_meta["closure_forecast_momentum_status"]
            stability_status = history_meta["closure_forecast_stability_status"]
            recent_path = history_meta["recent_closure_forecast_path"]
            (
                hysteresis_status,
                hysteresis_reason,
                transition_closure_likely_outcome,
                transition_status,
                transition_reason,
                resolution_status,
                resolution_reason,
                trust_policy,
                trust_policy_reason,
                pending_debt_status,
                pending_debt_reason,
                policy_debt_status,
                policy_debt_reason,
                class_normalization_status,
                class_normalization_reason,
            ) = _apply_closure_forecast_hysteresis_control(
                target,
                history_meta=history_meta,
                transition_history_meta=transition_history_meta,
                trust_policy=trust_policy,
                trust_policy_reason=trust_policy_reason,
                transition_status=transition_status,
                transition_reason=transition_reason,
                resolution_status=resolution_status,
                resolution_reason=resolution_reason,
                pending_debt_status=pending_debt_status,
                pending_debt_reason=pending_debt_reason,
                policy_debt_status=policy_debt_status,
                policy_debt_reason=policy_debt_reason,
                class_normalization_status=class_normalization_status,
                class_normalization_reason=class_normalization_reason,
                closure_likely_outcome=transition_closure_likely_outcome,
            )

        updated_targets.append(
            {
                **target,
                "closure_forecast_momentum_score": momentum_score,
                "closure_forecast_momentum_status": momentum_status,
                "closure_forecast_stability_status": stability_status,
                "closure_forecast_hysteresis_status": hysteresis_status,
                "closure_forecast_hysteresis_reason": hysteresis_reason,
                "recent_closure_forecast_path": recent_path,
                "transition_closure_likely_outcome": transition_closure_likely_outcome,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "class_pending_debt_status": pending_debt_status,
                "class_pending_debt_reason": pending_debt_reason,
                "policy_debt_status": policy_debt_status,
                "policy_debt_reason": policy_debt_reason,
                "class_normalization_status": class_normalization_status,
                "class_normalization_reason": class_normalization_reason,
                "trust_policy": trust_policy,
                "trust_policy_reason": trust_policy_reason,
            }
        )

    resolution_targets[:] = updated_targets
    primary_target = resolution_targets[0]
    pending_debt_hotspots = _class_pending_debt_hotspots(resolution_targets, mode="debt")
    healthy_pending_resolution_hotspots = _class_pending_debt_hotspots(
        resolution_targets,
        mode="healthy",
    )
    stale_pending_debt_hotspots = _pending_debt_freshness_hotspots(
        resolution_targets,
        mode="stale",
    )
    fresh_pending_resolution_hotspots = _pending_debt_freshness_hotspots(
        resolution_targets,
        mode="fresh",
    )
    supporting_pending_resolution_hotspots = _closure_forecast_hotspots(
        resolution_targets,
        mode="support",
    )
    caution_pending_debt_hotspots = _closure_forecast_hotspots(
        resolution_targets,
        mode="caution",
    )
    sustained_confirmation_hotspots = _closure_forecast_momentum_hotspots(
        resolution_targets,
        mode="confirmation",
    )
    sustained_clearance_hotspots = _closure_forecast_momentum_hotspots(
        resolution_targets,
        mode="clearance",
    )
    oscillating_closure_forecast_hotspots = _closure_forecast_momentum_hotspots(
        resolution_targets,
        mode="oscillating",
    )
    return {
        "primary_target_transition_closure_likely_outcome": primary_target.get("transition_closure_likely_outcome", "none"),
        "transition_closure_confidence_summary": _transition_closure_confidence_summary(
            primary_target,
            pending_debt_hotspots,
        ),
        "class_pending_debt_summary": _class_pending_debt_summary(
            primary_target,
            pending_debt_hotspots,
            healthy_pending_resolution_hotspots,
        ),
        "class_pending_resolution_summary": _class_pending_resolution_summary(
            primary_target,
            healthy_pending_resolution_hotspots,
            pending_debt_hotspots,
        ),
        "pending_debt_freshness_summary": _pending_debt_freshness_summary(
            primary_target,
            stale_pending_debt_hotspots,
            fresh_pending_resolution_hotspots,
        ),
        "pending_debt_decay_summary": _pending_debt_decay_summary(
            primary_target,
            fresh_pending_resolution_hotspots,
            stale_pending_debt_hotspots,
        ),
        "closure_forecast_reweighting_summary": _closure_forecast_reweighting_summary(
            primary_target,
            supporting_pending_resolution_hotspots,
            caution_pending_debt_hotspots,
        ),
        "primary_target_closure_forecast_momentum_score": primary_target.get("closure_forecast_momentum_score", 0.0),
        "primary_target_closure_forecast_momentum_status": primary_target.get("closure_forecast_momentum_status", "insufficient-data"),
        "primary_target_closure_forecast_stability_status": primary_target.get("closure_forecast_stability_status", "watch"),
        "primary_target_closure_forecast_hysteresis_status": primary_target.get("closure_forecast_hysteresis_status", "none"),
        "primary_target_closure_forecast_hysteresis_reason": primary_target.get("closure_forecast_hysteresis_reason", ""),
        "closure_forecast_momentum_summary": _closure_forecast_momentum_summary(
            primary_target,
            sustained_confirmation_hotspots,
            sustained_clearance_hotspots,
            oscillating_closure_forecast_hotspots,
        ),
        "closure_forecast_stability_summary": _closure_forecast_stability_summary(
            primary_target,
            oscillating_closure_forecast_hotspots,
        ),
        "closure_forecast_hysteresis_summary": _closure_forecast_hysteresis_summary(
            primary_target,
            sustained_confirmation_hotspots,
            sustained_clearance_hotspots,
        ),
        "closure_forecast_transition_window_runs": CLASS_CLOSURE_FORECAST_TRANSITION_WINDOW_RUNS,
        "sustained_confirmation_hotspots": sustained_confirmation_hotspots,
        "sustained_clearance_hotspots": sustained_clearance_hotspots,
        "oscillating_closure_forecast_hotspots": oscillating_closure_forecast_hotspots,
    }


def _apply_closure_forecast_freshness_and_decay(
    resolution_targets: list[dict],
    history: list[dict],
    *,
    current_generated_at: str,
    confidence_calibration: dict,
) -> dict:
    if not resolution_targets:
        return {
            "primary_target_closure_forecast_freshness_status": "insufficient-data",
            "primary_target_closure_forecast_freshness_reason": "",
            "primary_target_closure_forecast_decay_status": "none",
            "primary_target_closure_forecast_decay_reason": "",
            "closure_forecast_freshness_summary": "No closure-forecast freshness is recorded because there is no active target.",
            "closure_forecast_decay_summary": "No closure-forecast decay is recorded because there is no active target.",
            "stale_closure_forecast_hotspots": [],
            "fresh_closure_forecast_signal_hotspots": [],
            "closure_forecast_decay_window_runs": CLASS_CLOSURE_FORECAST_FRESHNESS_WINDOW_RUNS,
        }

    current_primary_target = resolution_targets[0]
    current_bucket = _recommendation_bucket(current_primary_target)
    closure_forecast_events = _class_closure_forecast_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )
    transition_events = _class_transition_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )

    updated_targets: list[dict] = []
    for target in resolution_targets:
        freshness_status = "insufficient-data"
        freshness_reason = ""
        memory_weight = 0.0
        decayed_confirmation_rate = 0.0
        decayed_clearance_rate = 0.0
        signal_mix = ""
        decay_status = "none"
        decay_reason = ""
        closure_likely_outcome = target.get("transition_closure_likely_outcome", "none")
        closure_hysteresis_status = target.get("closure_forecast_hysteresis_status", "none")
        closure_hysteresis_reason = target.get("closure_forecast_hysteresis_reason", "")
        transition_status = target.get("class_reweight_transition_status", "none")
        transition_reason = target.get("class_reweight_transition_reason", "")
        resolution_status = target.get("class_transition_resolution_status", "none")
        resolution_reason = target.get("class_transition_resolution_reason", "")
        trust_policy = target.get("trust_policy", "monitor")
        trust_policy_reason = target.get("trust_policy_reason", "No trust-policy reason is recorded yet.")
        pending_debt_status = target.get("class_pending_debt_status", "none")
        pending_debt_reason = target.get("class_pending_debt_reason", "")
        policy_debt_status = target.get("policy_debt_status", "none")
        policy_debt_reason = target.get("policy_debt_reason", "")
        class_normalization_status = target.get("class_normalization_status", "none")
        class_normalization_reason = target.get("class_normalization_reason", "")

        if _recommendation_bucket(target) == current_bucket:
            freshness_meta = _closure_forecast_freshness_for_target(target, closure_forecast_events)
            transition_history_meta = _target_class_transition_history(target, transition_events)
            freshness_status = freshness_meta["closure_forecast_freshness_status"]
            freshness_reason = freshness_meta["closure_forecast_freshness_reason"]
            memory_weight = freshness_meta["closure_forecast_memory_weight"]
            decayed_confirmation_rate = freshness_meta["decayed_confirmation_forecast_rate"]
            decayed_clearance_rate = freshness_meta["decayed_clearance_forecast_rate"]
            signal_mix = freshness_meta["recent_closure_forecast_signal_mix"]
            (
                decay_status,
                decay_reason,
                closure_likely_outcome,
                closure_hysteresis_status,
                closure_hysteresis_reason,
                transition_status,
                transition_reason,
                resolution_status,
                resolution_reason,
                trust_policy,
                trust_policy_reason,
                pending_debt_status,
                pending_debt_reason,
                policy_debt_status,
                policy_debt_reason,
                class_normalization_status,
                class_normalization_reason,
            ) = _apply_closure_forecast_decay_control(
                target,
                freshness_meta=freshness_meta,
                transition_history_meta=transition_history_meta,
                trust_policy=trust_policy,
                trust_policy_reason=trust_policy_reason,
                transition_status=transition_status,
                transition_reason=transition_reason,
                resolution_status=resolution_status,
                resolution_reason=resolution_reason,
                closure_likely_outcome=closure_likely_outcome,
                closure_hysteresis_status=closure_hysteresis_status,
                closure_hysteresis_reason=closure_hysteresis_reason,
                pending_debt_status=pending_debt_status,
                pending_debt_reason=pending_debt_reason,
                policy_debt_status=policy_debt_status,
                policy_debt_reason=policy_debt_reason,
                class_normalization_status=class_normalization_status,
                class_normalization_reason=class_normalization_reason,
            )

        updated_targets.append(
            {
                **target,
                "closure_forecast_freshness_status": freshness_status,
                "closure_forecast_freshness_reason": freshness_reason,
                "closure_forecast_memory_weight": memory_weight,
                "decayed_confirmation_forecast_rate": decayed_confirmation_rate,
                "decayed_clearance_forecast_rate": decayed_clearance_rate,
                "recent_closure_forecast_signal_mix": signal_mix,
                "closure_forecast_decay_status": decay_status,
                "closure_forecast_decay_reason": decay_reason,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "class_pending_debt_status": pending_debt_status,
                "class_pending_debt_reason": pending_debt_reason,
                "policy_debt_status": policy_debt_status,
                "policy_debt_reason": policy_debt_reason,
                "class_normalization_status": class_normalization_status,
                "class_normalization_reason": class_normalization_reason,
                "trust_policy": trust_policy,
                "trust_policy_reason": trust_policy_reason,
            }
        )

    resolution_targets[:] = updated_targets
    primary_target = resolution_targets[0]
    stale_closure_forecast_hotspots = _closure_forecast_freshness_hotspots(
        resolution_targets,
        mode="stale",
    )
    fresh_closure_forecast_signal_hotspots = _closure_forecast_freshness_hotspots(
        resolution_targets,
        mode="fresh",
    )
    return {
        "primary_target_closure_forecast_freshness_status": primary_target.get("closure_forecast_freshness_status", "insufficient-data"),
        "primary_target_closure_forecast_freshness_reason": primary_target.get("closure_forecast_freshness_reason", ""),
        "primary_target_closure_forecast_decay_status": primary_target.get("closure_forecast_decay_status", "none"),
        "primary_target_closure_forecast_decay_reason": primary_target.get("closure_forecast_decay_reason", ""),
        "closure_forecast_freshness_summary": _closure_forecast_freshness_summary(
            primary_target,
            stale_closure_forecast_hotspots,
            fresh_closure_forecast_signal_hotspots,
        ),
        "closure_forecast_decay_summary": _closure_forecast_decay_summary(
            primary_target,
            fresh_closure_forecast_signal_hotspots,
            stale_closure_forecast_hotspots,
        ),
        "stale_closure_forecast_hotspots": stale_closure_forecast_hotspots,
        "fresh_closure_forecast_signal_hotspots": fresh_closure_forecast_signal_hotspots,
        "closure_forecast_decay_window_runs": CLASS_CLOSURE_FORECAST_FRESHNESS_WINDOW_RUNS,
    }


def _apply_closure_forecast_refresh_recovery_and_reacquisition(
    resolution_targets: list[dict],
    history: list[dict],
    *,
    current_generated_at: str,
    confidence_calibration: dict,
) -> dict:
    if not resolution_targets:
        return {
            "primary_target_closure_forecast_refresh_recovery_score": 0.0,
            "primary_target_closure_forecast_refresh_recovery_status": "none",
            "primary_target_closure_forecast_reacquisition_status": "none",
            "primary_target_closure_forecast_reacquisition_reason": "",
            "closure_forecast_refresh_recovery_summary": "No closure-forecast refresh recovery is recorded because there is no active target.",
            "closure_forecast_reacquisition_summary": "No closure-forecast reacquisition is recorded because there is no active target.",
            "closure_forecast_refresh_window_runs": CLASS_CLOSURE_FORECAST_REFRESH_WINDOW_RUNS,
            "recovering_confirmation_hotspots": [],
            "recovering_clearance_hotspots": [],
        }

    current_primary_target = resolution_targets[0]
    current_bucket = _recommendation_bucket(current_primary_target)
    closure_forecast_events = _class_closure_forecast_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )
    transition_events = _class_transition_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )

    updated_targets: list[dict] = []
    for target in resolution_targets:
        refresh_recovery_score = 0.0
        refresh_recovery_status = "none"
        reacquisition_status = "none"
        reacquisition_reason = ""
        refresh_path = ""
        closure_likely_outcome = target.get("transition_closure_likely_outcome", "none")
        closure_hysteresis_status = target.get("closure_forecast_hysteresis_status", "none")
        closure_hysteresis_reason = target.get("closure_forecast_hysteresis_reason", "")
        transition_status = target.get("class_reweight_transition_status", "none")
        transition_reason = target.get("class_reweight_transition_reason", "")
        resolution_status = target.get("class_transition_resolution_status", "none")
        resolution_reason = target.get("class_transition_resolution_reason", "")
        trust_policy = target.get("trust_policy", "monitor")
        trust_policy_reason = target.get("trust_policy_reason", "No trust-policy reason is recorded yet.")
        pending_debt_status = target.get("class_pending_debt_status", "none")
        pending_debt_reason = target.get("class_pending_debt_reason", "")
        policy_debt_status = target.get("policy_debt_status", "none")
        policy_debt_reason = target.get("policy_debt_reason", "")
        class_normalization_status = target.get("class_normalization_status", "none")
        class_normalization_reason = target.get("class_normalization_reason", "")

        if _recommendation_bucket(target) == current_bucket:
            transition_history_meta = _target_class_transition_history(target, transition_events)
            refresh_meta = _closure_forecast_refresh_recovery_for_target(
                target,
                closure_forecast_events,
                transition_history_meta,
            )
            refresh_recovery_score = refresh_meta["closure_forecast_refresh_recovery_score"]
            refresh_recovery_status = refresh_meta["closure_forecast_refresh_recovery_status"]
            reacquisition_status = refresh_meta["closure_forecast_reacquisition_status"]
            reacquisition_reason = refresh_meta["closure_forecast_reacquisition_reason"]
            refresh_path = refresh_meta["recent_closure_forecast_refresh_path"]
            (
                closure_likely_outcome,
                closure_hysteresis_status,
                closure_hysteresis_reason,
                transition_status,
                transition_reason,
                resolution_status,
                resolution_reason,
                trust_policy,
                trust_policy_reason,
                pending_debt_status,
                pending_debt_reason,
                policy_debt_status,
                policy_debt_reason,
                class_normalization_status,
                class_normalization_reason,
            ) = _apply_closure_forecast_reacquisition_control(
                target,
                refresh_meta=refresh_meta,
                transition_history_meta=transition_history_meta,
                trust_policy=trust_policy,
                trust_policy_reason=trust_policy_reason,
                transition_status=transition_status,
                transition_reason=transition_reason,
                resolution_status=resolution_status,
                resolution_reason=resolution_reason,
                pending_debt_status=pending_debt_status,
                pending_debt_reason=pending_debt_reason,
                policy_debt_status=policy_debt_status,
                policy_debt_reason=policy_debt_reason,
                class_normalization_status=class_normalization_status,
                class_normalization_reason=class_normalization_reason,
                closure_likely_outcome=closure_likely_outcome,
                closure_hysteresis_status=closure_hysteresis_status,
                closure_hysteresis_reason=closure_hysteresis_reason,
            )

        updated_targets.append(
            {
                **target,
                "closure_forecast_refresh_recovery_score": refresh_recovery_score,
                "closure_forecast_refresh_recovery_status": refresh_recovery_status,
                "closure_forecast_reacquisition_status": reacquisition_status,
                "closure_forecast_reacquisition_reason": reacquisition_reason,
                "recent_closure_forecast_refresh_path": refresh_path,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "class_pending_debt_status": pending_debt_status,
                "class_pending_debt_reason": pending_debt_reason,
                "policy_debt_status": policy_debt_status,
                "policy_debt_reason": policy_debt_reason,
                "class_normalization_status": class_normalization_status,
                "class_normalization_reason": class_normalization_reason,
                "trust_policy": trust_policy,
                "trust_policy_reason": trust_policy_reason,
            }
        )

    resolution_targets[:] = updated_targets
    primary_target = resolution_targets[0]
    recovering_confirmation_hotspots = _closure_forecast_refresh_hotspots(
        resolution_targets,
        mode="confirmation",
    )
    recovering_clearance_hotspots = _closure_forecast_refresh_hotspots(
        resolution_targets,
        mode="clearance",
    )
    return {
        "primary_target_closure_forecast_refresh_recovery_score": primary_target.get("closure_forecast_refresh_recovery_score", 0.0),
        "primary_target_closure_forecast_refresh_recovery_status": primary_target.get("closure_forecast_refresh_recovery_status", "none"),
        "primary_target_closure_forecast_reacquisition_status": primary_target.get("closure_forecast_reacquisition_status", "none"),
        "primary_target_closure_forecast_reacquisition_reason": primary_target.get("closure_forecast_reacquisition_reason", ""),
        "closure_forecast_refresh_recovery_summary": _closure_forecast_refresh_recovery_summary(
            primary_target,
            recovering_confirmation_hotspots,
            recovering_clearance_hotspots,
        ),
        "closure_forecast_reacquisition_summary": _closure_forecast_reacquisition_summary(
            primary_target,
            recovering_confirmation_hotspots,
            recovering_clearance_hotspots,
        ),
        "closure_forecast_refresh_window_runs": CLASS_CLOSURE_FORECAST_REFRESH_WINDOW_RUNS,
        "recovering_confirmation_hotspots": recovering_confirmation_hotspots,
        "recovering_clearance_hotspots": recovering_clearance_hotspots,
    }


def _apply_reacquisition_persistence_and_recovery_churn(
    resolution_targets: list[dict],
    history: list[dict],
    *,
    current_generated_at: str,
    confidence_calibration: dict,
) -> dict:
    if not resolution_targets:
        return {
            "primary_target_closure_forecast_reacquisition_age_runs": 0,
            "primary_target_closure_forecast_reacquisition_persistence_score": 0.0,
            "primary_target_closure_forecast_reacquisition_persistence_status": "none",
            "primary_target_closure_forecast_reacquisition_persistence_reason": "",
            "closure_forecast_reacquisition_persistence_summary": "No reacquisition persistence is recorded because there is no active target.",
            "closure_forecast_reacquisition_window_runs": CLASS_REACQUISITION_PERSISTENCE_WINDOW_RUNS,
            "just_reacquired_hotspots": [],
            "holding_reacquisition_hotspots": [],
            "primary_target_closure_forecast_recovery_churn_score": 0.0,
            "primary_target_closure_forecast_recovery_churn_status": "none",
            "primary_target_closure_forecast_recovery_churn_reason": "",
            "closure_forecast_recovery_churn_summary": "No recovery churn is recorded because there is no active target.",
            "recovery_churn_hotspots": [],
        }

    current_primary_target = resolution_targets[0]
    current_bucket = _recommendation_bucket(current_primary_target)
    closure_forecast_events = _class_closure_forecast_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )
    transition_events = _class_transition_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )

    updated_targets: list[dict] = []
    for target in resolution_targets:
        persistence_age_runs = 0
        persistence_score = 0.0
        persistence_status = "none"
        persistence_reason = ""
        persistence_path = ""
        churn_score = 0.0
        churn_status = "none"
        churn_reason = ""
        churn_path = ""
        closure_likely_outcome = target.get("transition_closure_likely_outcome", "none")
        closure_hysteresis_status = target.get("closure_forecast_hysteresis_status", "none")
        closure_hysteresis_reason = target.get("closure_forecast_hysteresis_reason", "")
        transition_status = target.get("class_reweight_transition_status", "none")
        transition_reason = target.get("class_reweight_transition_reason", "")
        resolution_status = target.get("class_transition_resolution_status", "none")
        resolution_reason = target.get("class_transition_resolution_reason", "")
        trust_policy = target.get("trust_policy", "monitor")
        trust_policy_reason = target.get("trust_policy_reason", "No trust-policy reason is recorded yet.")
        pending_debt_status = target.get("class_pending_debt_status", "none")
        pending_debt_reason = target.get("class_pending_debt_reason", "")
        policy_debt_status = target.get("policy_debt_status", "none")
        policy_debt_reason = target.get("policy_debt_reason", "")
        class_normalization_status = target.get("class_normalization_status", "none")
        class_normalization_reason = target.get("class_normalization_reason", "")

        if _recommendation_bucket(target) == current_bucket:
            transition_history_meta = _target_class_transition_history(target, transition_events)
            persistence_meta = _closure_forecast_reacquisition_persistence_for_target(
                target,
                closure_forecast_events,
                transition_history_meta,
            )
            churn_meta = _closure_forecast_recovery_churn_for_target(
                target,
                closure_forecast_events,
                transition_history_meta,
            )
            persistence_age_runs = persistence_meta["closure_forecast_reacquisition_age_runs"]
            persistence_score = persistence_meta["closure_forecast_reacquisition_persistence_score"]
            persistence_status = persistence_meta["closure_forecast_reacquisition_persistence_status"]
            persistence_reason = persistence_meta["closure_forecast_reacquisition_persistence_reason"]
            persistence_path = persistence_meta["recent_reacquisition_persistence_path"]
            churn_score = churn_meta["closure_forecast_recovery_churn_score"]
            churn_status = churn_meta["closure_forecast_recovery_churn_status"]
            churn_reason = churn_meta["closure_forecast_recovery_churn_reason"]
            churn_path = churn_meta["recent_recovery_churn_path"]
            (
                closure_likely_outcome,
                closure_hysteresis_status,
                closure_hysteresis_reason,
                transition_status,
                transition_reason,
                resolution_status,
                resolution_reason,
                trust_policy,
                trust_policy_reason,
                pending_debt_status,
                pending_debt_reason,
                policy_debt_status,
                policy_debt_reason,
                class_normalization_status,
                class_normalization_reason,
            ) = _apply_reacquisition_persistence_and_churn_control(
                target,
                persistence_meta=persistence_meta,
                churn_meta=churn_meta,
                transition_history_meta=transition_history_meta,
                trust_policy=trust_policy,
                trust_policy_reason=trust_policy_reason,
                transition_status=transition_status,
                transition_reason=transition_reason,
                resolution_status=resolution_status,
                resolution_reason=resolution_reason,
                pending_debt_status=pending_debt_status,
                pending_debt_reason=pending_debt_reason,
                policy_debt_status=policy_debt_status,
                policy_debt_reason=policy_debt_reason,
                class_normalization_status=class_normalization_status,
                class_normalization_reason=class_normalization_reason,
                closure_likely_outcome=closure_likely_outcome,
                closure_hysteresis_status=closure_hysteresis_status,
                closure_hysteresis_reason=closure_hysteresis_reason,
            )

        updated_targets.append(
            {
                **target,
                "closure_forecast_reacquisition_age_runs": persistence_age_runs,
                "closure_forecast_reacquisition_persistence_score": persistence_score,
                "closure_forecast_reacquisition_persistence_status": persistence_status,
                "closure_forecast_reacquisition_persistence_reason": persistence_reason,
                "recent_reacquisition_persistence_path": persistence_path,
                "closure_forecast_recovery_churn_score": churn_score,
                "closure_forecast_recovery_churn_status": churn_status,
                "closure_forecast_recovery_churn_reason": churn_reason,
                "recent_recovery_churn_path": churn_path,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "class_pending_debt_status": pending_debt_status,
                "class_pending_debt_reason": pending_debt_reason,
                "policy_debt_status": policy_debt_status,
                "policy_debt_reason": policy_debt_reason,
                "class_normalization_status": class_normalization_status,
                "class_normalization_reason": class_normalization_reason,
                "trust_policy": trust_policy,
                "trust_policy_reason": trust_policy_reason,
            }
        )

    resolution_targets[:] = updated_targets
    primary_target = resolution_targets[0]
    just_reacquired_hotspots = _closure_forecast_reacquisition_hotspots(
        resolution_targets,
        mode="just-reacquired",
    )
    holding_reacquisition_hotspots = _closure_forecast_reacquisition_hotspots(
        resolution_targets,
        mode="holding",
    )
    recovery_churn_hotspots = _closure_forecast_reacquisition_hotspots(
        resolution_targets,
        mode="churn",
    )
    return {
        "primary_target_closure_forecast_reacquisition_age_runs": primary_target.get("closure_forecast_reacquisition_age_runs", 0),
        "primary_target_closure_forecast_reacquisition_persistence_score": primary_target.get("closure_forecast_reacquisition_persistence_score", 0.0),
        "primary_target_closure_forecast_reacquisition_persistence_status": primary_target.get("closure_forecast_reacquisition_persistence_status", "none"),
        "primary_target_closure_forecast_reacquisition_persistence_reason": primary_target.get("closure_forecast_reacquisition_persistence_reason", ""),
        "closure_forecast_reacquisition_persistence_summary": _closure_forecast_reacquisition_persistence_summary(
            primary_target,
            just_reacquired_hotspots,
            holding_reacquisition_hotspots,
        ),
        "closure_forecast_reacquisition_window_runs": CLASS_REACQUISITION_PERSISTENCE_WINDOW_RUNS,
        "just_reacquired_hotspots": just_reacquired_hotspots,
        "holding_reacquisition_hotspots": holding_reacquisition_hotspots,
        "primary_target_closure_forecast_recovery_churn_score": primary_target.get("closure_forecast_recovery_churn_score", 0.0),
        "primary_target_closure_forecast_recovery_churn_status": primary_target.get("closure_forecast_recovery_churn_status", "none"),
        "primary_target_closure_forecast_recovery_churn_reason": primary_target.get("closure_forecast_recovery_churn_reason", ""),
        "closure_forecast_recovery_churn_summary": _closure_forecast_recovery_churn_summary(
            primary_target,
            recovery_churn_hotspots,
        ),
        "recovery_churn_hotspots": recovery_churn_hotspots,
    }


def _apply_reacquisition_freshness_and_persistence_reset(
    resolution_targets: list[dict],
    history: list[dict],
    *,
    current_generated_at: str,
    confidence_calibration: dict,
) -> dict:
    if not resolution_targets:
        return {
            "primary_target_closure_forecast_reacquisition_freshness_status": "insufficient-data",
            "primary_target_closure_forecast_reacquisition_freshness_reason": "",
            "closure_forecast_reacquisition_freshness_summary": "No reacquisition freshness is recorded because there is no active target.",
            "primary_target_closure_forecast_persistence_reset_status": "none",
            "primary_target_closure_forecast_persistence_reset_reason": "",
            "closure_forecast_persistence_reset_summary": "No persistence reset is recorded because there is no active target.",
            "stale_reacquisition_hotspots": [],
            "fresh_reacquisition_signal_hotspots": [],
            "closure_forecast_reacquisition_decay_window_runs": CLASS_REACQUISITION_FRESHNESS_WINDOW_RUNS,
        }

    current_primary_target = resolution_targets[0]
    current_bucket = _recommendation_bucket(current_primary_target)
    closure_forecast_events = _class_closure_forecast_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )
    transition_events = _class_transition_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )

    updated_targets: list[dict] = []
    for target in resolution_targets:
        reacquisition_freshness_status = "insufficient-data"
        reacquisition_freshness_reason = ""
        reacquisition_memory_weight = 0.0
        decayed_reacquired_confirmation_rate = 0.0
        decayed_reacquired_clearance_rate = 0.0
        recent_reacquisition_signal_mix = ""
        persistence_reset_status = "none"
        persistence_reset_reason = ""
        closure_likely_outcome = target.get("transition_closure_likely_outcome", "none")
        closure_hysteresis_status = target.get("closure_forecast_hysteresis_status", "none")
        closure_hysteresis_reason = target.get("closure_forecast_hysteresis_reason", "")
        transition_status = target.get("class_reweight_transition_status", "none")
        transition_reason = target.get("class_reweight_transition_reason", "")
        resolution_status = target.get("class_transition_resolution_status", "none")
        resolution_reason = target.get("class_transition_resolution_reason", "")
        trust_policy = target.get("trust_policy", "monitor")
        trust_policy_reason = target.get("trust_policy_reason", "No trust-policy reason is recorded yet.")
        pending_debt_status = target.get("class_pending_debt_status", "none")
        pending_debt_reason = target.get("class_pending_debt_reason", "")
        policy_debt_status = target.get("policy_debt_status", "none")
        policy_debt_reason = target.get("policy_debt_reason", "")
        class_normalization_status = target.get("class_normalization_status", "none")
        class_normalization_reason = target.get("class_normalization_reason", "")
        reacquisition_status = target.get("closure_forecast_reacquisition_status", "none")
        reacquisition_reason = target.get("closure_forecast_reacquisition_reason", "")
        persistence_age_runs = target.get("closure_forecast_reacquisition_age_runs", 0)
        persistence_score = target.get("closure_forecast_reacquisition_persistence_score", 0.0)
        persistence_status = target.get("closure_forecast_reacquisition_persistence_status", "none")
        persistence_reason = target.get("closure_forecast_reacquisition_persistence_reason", "")

        if _recommendation_bucket(target) == current_bucket:
            transition_history_meta = _target_class_transition_history(target, transition_events)
            freshness_meta = _closure_forecast_reacquisition_freshness_for_target(
                target,
                closure_forecast_events,
            )
            reacquisition_freshness_status = freshness_meta["closure_forecast_reacquisition_freshness_status"]
            reacquisition_freshness_reason = freshness_meta["closure_forecast_reacquisition_freshness_reason"]
            reacquisition_memory_weight = freshness_meta["closure_forecast_reacquisition_memory_weight"]
            decayed_reacquired_confirmation_rate = freshness_meta["decayed_reacquired_confirmation_rate"]
            decayed_reacquired_clearance_rate = freshness_meta["decayed_reacquired_clearance_rate"]
            recent_reacquisition_signal_mix = freshness_meta["recent_reacquisition_signal_mix"]
            control_updates = _apply_reacquisition_freshness_reset_control(
                target,
                freshness_meta=freshness_meta,
                transition_history_meta=transition_history_meta,
                trust_policy=trust_policy,
                trust_policy_reason=trust_policy_reason,
                transition_status=transition_status,
                transition_reason=transition_reason,
                resolution_status=resolution_status,
                resolution_reason=resolution_reason,
                pending_debt_status=pending_debt_status,
                pending_debt_reason=pending_debt_reason,
                policy_debt_status=policy_debt_status,
                policy_debt_reason=policy_debt_reason,
                class_normalization_status=class_normalization_status,
                class_normalization_reason=class_normalization_reason,
                closure_likely_outcome=closure_likely_outcome,
                closure_hysteresis_status=closure_hysteresis_status,
                closure_hysteresis_reason=closure_hysteresis_reason,
                reacquisition_status=reacquisition_status,
                reacquisition_reason=reacquisition_reason,
                persistence_age_runs=persistence_age_runs,
                persistence_score=persistence_score,
                persistence_status=persistence_status,
                persistence_reason=persistence_reason,
            )
            persistence_reset_status = control_updates["closure_forecast_persistence_reset_status"]
            persistence_reset_reason = control_updates["closure_forecast_persistence_reset_reason"]
            closure_likely_outcome = control_updates["transition_closure_likely_outcome"]
            closure_hysteresis_status = control_updates["closure_forecast_hysteresis_status"]
            closure_hysteresis_reason = control_updates["closure_forecast_hysteresis_reason"]
            transition_status = control_updates["class_reweight_transition_status"]
            transition_reason = control_updates["class_reweight_transition_reason"]
            resolution_status = control_updates["class_transition_resolution_status"]
            resolution_reason = control_updates["class_transition_resolution_reason"]
            trust_policy = control_updates["trust_policy"]
            trust_policy_reason = control_updates["trust_policy_reason"]
            pending_debt_status = control_updates["class_pending_debt_status"]
            pending_debt_reason = control_updates["class_pending_debt_reason"]
            policy_debt_status = control_updates["policy_debt_status"]
            policy_debt_reason = control_updates["policy_debt_reason"]
            class_normalization_status = control_updates["class_normalization_status"]
            class_normalization_reason = control_updates["class_normalization_reason"]
            reacquisition_status = control_updates["closure_forecast_reacquisition_status"]
            reacquisition_reason = control_updates["closure_forecast_reacquisition_reason"]
            persistence_age_runs = control_updates["closure_forecast_reacquisition_age_runs"]
            persistence_score = control_updates["closure_forecast_reacquisition_persistence_score"]
            persistence_status = control_updates["closure_forecast_reacquisition_persistence_status"]
            persistence_reason = control_updates["closure_forecast_reacquisition_persistence_reason"]

        updated_targets.append(
            {
                **target,
                "closure_forecast_reacquisition_freshness_status": reacquisition_freshness_status,
                "closure_forecast_reacquisition_freshness_reason": reacquisition_freshness_reason,
                "closure_forecast_reacquisition_memory_weight": reacquisition_memory_weight,
                "decayed_reacquired_confirmation_rate": decayed_reacquired_confirmation_rate,
                "decayed_reacquired_clearance_rate": decayed_reacquired_clearance_rate,
                "recent_reacquisition_signal_mix": recent_reacquisition_signal_mix,
                "closure_forecast_persistence_reset_status": persistence_reset_status,
                "closure_forecast_persistence_reset_reason": persistence_reset_reason,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "class_pending_debt_status": pending_debt_status,
                "class_pending_debt_reason": pending_debt_reason,
                "policy_debt_status": policy_debt_status,
                "policy_debt_reason": policy_debt_reason,
                "class_normalization_status": class_normalization_status,
                "class_normalization_reason": class_normalization_reason,
                "trust_policy": trust_policy,
                "trust_policy_reason": trust_policy_reason,
                "closure_forecast_reacquisition_status": reacquisition_status,
                "closure_forecast_reacquisition_reason": reacquisition_reason,
                "closure_forecast_reacquisition_age_runs": persistence_age_runs,
                "closure_forecast_reacquisition_persistence_score": persistence_score,
                "closure_forecast_reacquisition_persistence_status": persistence_status,
                "closure_forecast_reacquisition_persistence_reason": persistence_reason,
            }
        )

    resolution_targets[:] = updated_targets
    primary_target = resolution_targets[0]
    stale_reacquisition_hotspots = _closure_forecast_reacquisition_freshness_hotspots(
        resolution_targets,
        mode="stale",
    )
    fresh_reacquisition_signal_hotspots = _closure_forecast_reacquisition_freshness_hotspots(
        resolution_targets,
        mode="fresh",
    )
    return {
        "primary_target_closure_forecast_reacquisition_freshness_status": primary_target.get(
            "closure_forecast_reacquisition_freshness_status",
            "insufficient-data",
        ),
        "primary_target_closure_forecast_reacquisition_freshness_reason": primary_target.get(
            "closure_forecast_reacquisition_freshness_reason",
            "",
        ),
        "closure_forecast_reacquisition_freshness_summary": _closure_forecast_reacquisition_freshness_summary(
            primary_target,
            stale_reacquisition_hotspots,
            fresh_reacquisition_signal_hotspots,
        ),
        "primary_target_closure_forecast_persistence_reset_status": primary_target.get(
            "closure_forecast_persistence_reset_status",
            "none",
        ),
        "primary_target_closure_forecast_persistence_reset_reason": primary_target.get(
            "closure_forecast_persistence_reset_reason",
            "",
        ),
        "closure_forecast_persistence_reset_summary": _closure_forecast_persistence_reset_summary(
            primary_target,
            stale_reacquisition_hotspots,
            fresh_reacquisition_signal_hotspots,
        ),
        "stale_reacquisition_hotspots": stale_reacquisition_hotspots,
        "fresh_reacquisition_signal_hotspots": fresh_reacquisition_signal_hotspots,
        "closure_forecast_reacquisition_decay_window_runs": CLASS_REACQUISITION_FRESHNESS_WINDOW_RUNS,
    }


def _closure_forecast_reset_side_from_status(status: str) -> str:
    if status in {"confirmation-softened", "confirmation-reset"}:
        return "confirmation"
    if status in {"clearance-softened", "clearance-reset"}:
        return "clearance"
    return "none"


def _closure_forecast_reset_refresh_path_label(event: dict) -> str:
    reset_status = event.get("closure_forecast_persistence_reset_status", "none") or "none"
    if reset_status != "none":
        return reset_status
    score = float(event.get("closure_forecast_reweight_score", 0.0) or 0.0)
    direction = _normalized_closure_forecast_direction(
        event.get("closure_forecast_reweight_direction", "neutral"),
        score,
    )
    freshness = event.get("closure_forecast_reacquisition_freshness_status", "insufficient-data")
    if direction == "supporting-confirmation":
        return f"{freshness} confirmation"
    if direction == "supporting-clearance":
        return f"{freshness} clearance"
    likely_outcome = event.get("transition_closure_likely_outcome", "none") or "none"
    if likely_outcome != "none":
        return likely_outcome
    return "hold"


def _closure_forecast_reset_refresh_recovery_for_target(
    target: dict,
    closure_forecast_events: list[dict],
    transition_history_meta: dict,
) -> dict:
    class_key = _target_class_key(target)
    matching_events = [
        event for event in closure_forecast_events if event.get("class_key") == class_key
    ][:CLASS_RESET_REENTRY_WINDOW_RUNS]
    recent_reset_side = "none"
    latest_reset_index: int | None = None
    for index, event in enumerate(matching_events):
        event_reset_side = _closure_forecast_reset_side_from_status(
            event.get("closure_forecast_persistence_reset_status", "none")
        )
        if event_reset_side != "none":
            recent_reset_side = event_reset_side
            latest_reset_index = index
            break

    relevant_events: list[dict] = []
    directions: list[str] = []
    weighted_total = 0.0
    weight_sum = 0.0
    for index, event in enumerate(matching_events):
        score = float(event.get("closure_forecast_reweight_score", 0.0) or 0.0)
        direction = _normalized_closure_forecast_direction(
            event.get("closure_forecast_reweight_direction", "neutral"),
            score,
        )
        if (
            _closure_forecast_reset_side_from_status(
                event.get("closure_forecast_persistence_reset_status", "none")
            )
            == "none"
            and direction == "neutral"
            and abs(score) < 0.05
        ):
            continue
        relevant_events.append(event)
        directions.append(direction)
        if len(relevant_events) > CLASS_RESET_REENTRY_WINDOW_RUNS:
            break
        if direction == "neutral":
            signal_strength = 0.0
            sign = 0.0
        else:
            signal_strength = max(abs(score), 0.05)
            sign = 1.0 if direction == "supporting-confirmation" else -1.0
        freshness_factor = {
            "fresh": 1.00,
            "mixed-age": 0.60,
            "stale": 0.25,
            "insufficient-data": 0.10,
        }.get(
            event.get("closure_forecast_reacquisition_freshness_status", "insufficient-data"),
            0.10,
        )
        weight = (1.0, 0.8, 0.6, 0.4)[min(len(relevant_events) - 1, CLASS_RESET_REENTRY_WINDOW_RUNS - 1)]
        weighted_total += sign * signal_strength * freshness_factor * weight
        weight_sum += weight

    recovery_score = _clamp_round(
        weighted_total / max(weight_sum, 1.0),
        lower=-0.95,
        upper=0.95,
    )
    current_score = float(target.get("closure_forecast_reweight_score", 0.0) or 0.0)
    current_direction = _normalized_closure_forecast_direction(
        target.get("closure_forecast_reweight_direction", "neutral"),
        current_score,
    )
    current_freshness = target.get(
        "closure_forecast_reacquisition_freshness_status",
        "insufficient-data",
    )
    current_momentum = target.get("closure_forecast_momentum_status", "insufficient-data")
    current_stability = target.get("closure_forecast_stability_status", "watch")
    earlier_majority = _closure_forecast_direction_majority(directions[1:])
    local_noise = _target_specific_normalization_noise(target, transition_history_meta)
    direction_reversing = _closure_forecast_direction_reversing(
        current_direction,
        earlier_majority,
    )
    opposes_reset = (
        (recent_reset_side == "confirmation" and current_direction == "supporting-clearance")
        or (recent_reset_side == "clearance" and current_direction == "supporting-confirmation")
    )
    aligned_fresh_runs_after_reset = 0
    if latest_reset_index is not None and latest_reset_index > 0:
        for event in matching_events[:latest_reset_index]:
            score = float(event.get("closure_forecast_reweight_score", 0.0) or 0.0)
            direction = _normalized_closure_forecast_direction(
                event.get("closure_forecast_reweight_direction", "neutral"),
                score,
            )
            event_side = (
                "confirmation"
                if direction == "supporting-confirmation"
                else "clearance"
                if direction == "supporting-clearance"
                else "none"
            )
            if (
                event_side == recent_reset_side
                and event.get("closure_forecast_reacquisition_freshness_status", "insufficient-data")
                == "fresh"
            ):
                aligned_fresh_runs_after_reset += 1
    current_side = (
        "confirmation"
        if current_direction == "supporting-confirmation"
        else "clearance"
        if current_direction == "supporting-clearance"
        else "none"
    )
    current_event_already_counted = any(
        event.get("generated_at", "") == ""
        and float(event.get("closure_forecast_reweight_score", 0.0) or 0.0) == current_score
        and event.get("closure_forecast_reweight_direction", "neutral")
        == target.get("closure_forecast_reweight_direction", "neutral")
        for event in matching_events[: latest_reset_index or 0]
    )
    if (
        current_side == recent_reset_side
        and current_freshness == "fresh"
        and not current_event_already_counted
    ):
        aligned_fresh_runs_after_reset += 1

    if len(relevant_events) < 2 or recent_reset_side == "none":
        recovery_status = "none"
    elif local_noise and current_direction == "supporting-confirmation":
        recovery_status = "blocked"
    elif opposes_reset or direction_reversing:
        recovery_status = "reversing"
    elif (
        recent_reset_side == "confirmation"
        and current_direction == "supporting-confirmation"
        and current_freshness == "fresh"
        and recovery_score >= 0.25
        and current_stability != "oscillating"
    ):
        recovery_status = "reentering-confirmation"
    elif (
        recent_reset_side == "clearance"
        and current_direction == "supporting-clearance"
        and current_freshness == "fresh"
        and recovery_score <= -0.25
        and current_stability != "oscillating"
    ):
        recovery_status = "reentering-clearance"
    elif (
        recent_reset_side == "confirmation"
        and current_direction == "supporting-confirmation"
        and current_freshness in {"fresh", "mixed-age"}
        and recovery_score >= 0.15
    ):
        recovery_status = "recovering-confirmation-reset"
    elif (
        recent_reset_side == "clearance"
        and current_direction == "supporting-clearance"
        and current_freshness in {"fresh", "mixed-age"}
        and recovery_score <= -0.15
    ):
        recovery_status = "recovering-clearance-reset"
    else:
        recovery_status = "none"

    if (
        recovery_status == "reentering-confirmation"
        and current_freshness == "fresh"
        and current_momentum == "sustained-confirmation"
        and current_stability == "stable"
        and not local_noise
        and aligned_fresh_runs_after_reset >= 2
    ):
        reentry_status = "reentered-confirmation"
        reentry_reason = (
            "Fresh confirmation-side follow-through has re-earned re-entry into stronger confirmation-side reacquisition."
        )
    elif (
        recovery_status == "reentering-clearance"
        and current_freshness == "fresh"
        and current_momentum == "sustained-clearance"
        and current_stability == "stable"
        and aligned_fresh_runs_after_reset >= 2
    ):
        reentry_status = "reentered-clearance"
        reentry_reason = (
            "Fresh clearance-side pressure has re-earned re-entry into stronger clearance-side reacquisition."
        )
    elif local_noise and recovery_status in {"recovering-confirmation-reset", "reentering-confirmation", "blocked"}:
        reentry_status = "blocked"
        reentry_reason = "Local target instability is still preventing positive confirmation-side re-entry."
    elif recovery_status in {"recovering-confirmation-reset", "reentering-confirmation"}:
        reentry_status = "pending-confirmation-reentry"
        reentry_reason = (
            "Fresh confirmation-side evidence is returning after a reset, but it has not yet re-earned re-entry."
        )
    elif recovery_status in {"recovering-clearance-reset", "reentering-clearance"}:
        reentry_status = "pending-clearance-reentry"
        reentry_reason = (
            "Fresh clearance-side evidence is returning after a reset, but it has not yet re-earned re-entry."
        )
    else:
        reentry_status = "none"
        reentry_reason = ""

    return {
        "closure_forecast_reset_refresh_recovery_score": recovery_score,
        "closure_forecast_reset_refresh_recovery_status": recovery_status,
        "closure_forecast_reset_reentry_status": reentry_status,
        "closure_forecast_reset_reentry_reason": reentry_reason,
        "recent_reset_refresh_path": " -> ".join(
            _closure_forecast_reset_refresh_path_label(event) for event in matching_events if event
        ),
        "recent_reset_side": recent_reset_side,
        "aligned_fresh_runs_after_latest_reset": aligned_fresh_runs_after_reset,
    }


def _apply_reset_refresh_reentry_control(
    target: dict,
    *,
    refresh_meta: dict,
    transition_history_meta: dict,
    closure_likely_outcome: str,
    closure_hysteresis_status: str,
    closure_hysteresis_reason: str,
    transition_status: str,
    transition_reason: str,
    resolution_status: str,
    resolution_reason: str,
    reacquisition_status: str,
    reacquisition_reason: str,
) -> dict:
    recovery_status = refresh_meta.get("closure_forecast_reset_refresh_recovery_status", "none")
    reentry_status = refresh_meta.get("closure_forecast_reset_reentry_status", "none")
    reentry_reason = refresh_meta.get("closure_forecast_reset_reentry_reason", "")
    recent_reset_side = refresh_meta.get("recent_reset_side", "none")
    current_freshness = target.get(
        "closure_forecast_reacquisition_freshness_status",
        "insufficient-data",
    )
    current_stability = target.get("closure_forecast_stability_status", "watch")
    transition_age_runs = int(target.get("class_transition_age_runs", 0) or 0)
    recent_pending_status = transition_history_meta.get("recent_pending_status", "none")
    decayed_clearance_rate = float(target.get("decayed_reacquired_clearance_rate", 0.0) or 0.0)
    persistence_status = "none"
    persistence_reason = ""
    persistence_age_runs = 0
    persistence_score = 0.0

    if reentry_status == "blocked":
        if recent_reset_side == "confirmation":
            closure_likely_outcome = "hold"
            closure_hysteresis_status = "pending-confirmation"
            closure_hysteresis_reason = reentry_reason
            if reacquisition_status == "reacquired-confirmation":
                reacquisition_status = "pending-confirmation-reacquisition"
                reacquisition_reason = reentry_reason
        return {
            "transition_closure_likely_outcome": closure_likely_outcome,
            "closure_forecast_hysteresis_status": closure_hysteresis_status,
            "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reacquisition_status": reacquisition_status,
            "closure_forecast_reacquisition_reason": reacquisition_reason,
            "closure_forecast_reacquisition_age_runs": persistence_age_runs,
            "closure_forecast_reacquisition_persistence_score": persistence_score,
            "closure_forecast_reacquisition_persistence_status": persistence_status,
            "closure_forecast_reacquisition_persistence_reason": persistence_reason,
        }

    if reentry_status == "reentered-confirmation":
        return {
            "transition_closure_likely_outcome": "confirm-soon",
            "closure_forecast_hysteresis_status": "confirmed-confirmation",
            "closure_forecast_hysteresis_reason": reentry_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reacquisition_status": "reacquired-confirmation",
            "closure_forecast_reacquisition_reason": reentry_reason,
            "closure_forecast_reacquisition_age_runs": 0,
            "closure_forecast_reacquisition_persistence_score": 0.0,
            "closure_forecast_reacquisition_persistence_status": "none",
            "closure_forecast_reacquisition_persistence_reason": "",
        }

    if reentry_status == "reentered-clearance":
        restored_outcome = closure_likely_outcome
        if restored_outcome == "hold":
            restored_outcome = "clear-risk"
        elif restored_outcome == "clear-risk" and transition_age_runs >= 3:
            restored_outcome = "expire-risk"
        if (
            resolution_status == "none"
            and recent_pending_status in {"pending-support", "pending-caution"}
            and decayed_clearance_rate >= 0.50
            and current_stability != "oscillating"
        ):
            transition_status = "none"
            transition_reason = ""
            resolution_status = "cleared"
            resolution_reason = reentry_reason
        return {
            "transition_closure_likely_outcome": restored_outcome,
            "closure_forecast_hysteresis_status": "confirmed-clearance",
            "closure_forecast_hysteresis_reason": reentry_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reacquisition_status": "reacquired-clearance",
            "closure_forecast_reacquisition_reason": reentry_reason,
            "closure_forecast_reacquisition_age_runs": 0,
            "closure_forecast_reacquisition_persistence_score": 0.0,
            "closure_forecast_reacquisition_persistence_status": "none",
            "closure_forecast_reacquisition_persistence_reason": "",
        }

    if recent_reset_side == "confirmation":
        if recovery_status in {"recovering-confirmation-reset", "reentering-confirmation"}:
            return {
                "transition_closure_likely_outcome": "hold",
                "closure_forecast_hysteresis_status": "pending-confirmation",
                "closure_forecast_hysteresis_reason": reentry_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reacquisition_status": "pending-confirmation-reacquisition",
                "closure_forecast_reacquisition_reason": reentry_reason,
                "closure_forecast_reacquisition_age_runs": 0,
                "closure_forecast_reacquisition_persistence_score": 0.0,
                "closure_forecast_reacquisition_persistence_status": "none",
                "closure_forecast_reacquisition_persistence_reason": "",
            }
        if recovery_status == "reversing" or current_freshness in {"stale", "insufficient-data"}:
            return {
                "transition_closure_likely_outcome": "hold",
                "closure_forecast_hysteresis_status": "pending-confirmation",
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reacquisition_status": reacquisition_status if reacquisition_status != "reacquired-confirmation" else "none",
                "closure_forecast_reacquisition_reason": reacquisition_reason,
                "closure_forecast_reacquisition_age_runs": 0,
                "closure_forecast_reacquisition_persistence_score": 0.0,
                "closure_forecast_reacquisition_persistence_status": "none",
                "closure_forecast_reacquisition_persistence_reason": "",
            }

    if recent_reset_side == "clearance":
        if recovery_status in {"recovering-clearance-reset", "reentering-clearance"}:
            weaker_outcome = closure_likely_outcome
            if weaker_outcome == "expire-risk":
                weaker_outcome = "clear-risk"
            return {
                "transition_closure_likely_outcome": weaker_outcome,
                "closure_forecast_hysteresis_status": "pending-clearance",
                "closure_forecast_hysteresis_reason": reentry_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reacquisition_status": "pending-clearance-reacquisition",
                "closure_forecast_reacquisition_reason": reentry_reason,
                "closure_forecast_reacquisition_age_runs": 0,
                "closure_forecast_reacquisition_persistence_score": 0.0,
                "closure_forecast_reacquisition_persistence_status": "none",
                "closure_forecast_reacquisition_persistence_reason": "",
            }
        if recovery_status == "reversing" or current_freshness in {"stale", "insufficient-data"}:
            weaker_outcome = closure_likely_outcome
            if weaker_outcome == "expire-risk":
                weaker_outcome = "clear-risk"
            return {
                "transition_closure_likely_outcome": weaker_outcome,
                "closure_forecast_hysteresis_status": "pending-clearance",
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reacquisition_status": reacquisition_status if reacquisition_status != "reacquired-clearance" else "none",
                "closure_forecast_reacquisition_reason": reacquisition_reason,
                "closure_forecast_reacquisition_age_runs": 0,
                "closure_forecast_reacquisition_persistence_score": 0.0,
                "closure_forecast_reacquisition_persistence_status": "none",
                "closure_forecast_reacquisition_persistence_reason": "",
            }

    return {
        "transition_closure_likely_outcome": closure_likely_outcome,
        "closure_forecast_hysteresis_status": closure_hysteresis_status,
        "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
        "class_reweight_transition_status": transition_status,
        "class_reweight_transition_reason": transition_reason,
        "class_transition_resolution_status": resolution_status,
        "class_transition_resolution_reason": resolution_reason,
        "closure_forecast_reacquisition_status": reacquisition_status,
        "closure_forecast_reacquisition_reason": reacquisition_reason,
        "closure_forecast_reacquisition_age_runs": target.get("closure_forecast_reacquisition_age_runs", 0),
        "closure_forecast_reacquisition_persistence_score": target.get(
            "closure_forecast_reacquisition_persistence_score",
            0.0,
        ),
        "closure_forecast_reacquisition_persistence_status": target.get(
            "closure_forecast_reacquisition_persistence_status",
            "none",
        ),
        "closure_forecast_reacquisition_persistence_reason": target.get(
            "closure_forecast_reacquisition_persistence_reason",
            "",
        ),
    }


def _closure_forecast_reset_refresh_hotspots(
    resolution_targets: list[dict],
    *,
    mode: str,
) -> list[dict]:
    grouped: dict[str, dict] = {}
    for target in resolution_targets:
        class_key = _target_class_key(target)
        if not class_key:
            continue
        current = {
            "scope": "class",
            "label": class_key,
            "closure_forecast_reset_refresh_recovery_score": target.get(
                "closure_forecast_reset_refresh_recovery_score",
                0.0,
            ),
            "closure_forecast_reset_refresh_recovery_status": target.get(
                "closure_forecast_reset_refresh_recovery_status",
                "none",
            ),
            "closure_forecast_reset_reentry_status": target.get(
                "closure_forecast_reset_reentry_status",
                "none",
            ),
            "recent_reset_refresh_path": target.get("recent_reset_refresh_path", ""),
        }
        existing = grouped.get(class_key)
        if existing is None or abs(current["closure_forecast_reset_refresh_recovery_score"]) > abs(
            existing["closure_forecast_reset_refresh_recovery_score"]
        ):
            grouped[class_key] = current
    hotspots = list(grouped.values())
    if mode == "confirmation":
        allowed_statuses = {
            "recovering-confirmation-reset",
            "reentering-confirmation",
            "pending-confirmation-reentry",
            "reentered-confirmation",
        }
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reset_refresh_recovery_status") in {
                "recovering-confirmation-reset",
                "reentering-confirmation",
            }
            or item.get("closure_forecast_reset_reentry_status") in allowed_statuses
        ]
    else:
        allowed_statuses = {
            "recovering-clearance-reset",
            "reentering-clearance",
            "pending-clearance-reentry",
            "reentered-clearance",
        }
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reset_refresh_recovery_status") in {
                "recovering-clearance-reset",
                "reentering-clearance",
            }
            or item.get("closure_forecast_reset_reentry_status") in allowed_statuses
        ]
    hotspots.sort(
        key=lambda item: (
            -abs(item.get("closure_forecast_reset_refresh_recovery_score", 0.0)),
            item.get("label", ""),
        )
    )
    return hotspots[:5]


def _closure_forecast_reset_refresh_recovery_summary(
    primary_target: dict,
    recovering_confirmation_hotspots: list[dict],
    recovering_clearance_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    status = primary_target.get("closure_forecast_reset_refresh_recovery_status", "none")
    score = primary_target.get("closure_forecast_reset_refresh_recovery_score", 0.0)
    if status == "recovering-confirmation-reset":
        return f"Fresh confirmation-side evidence is returning for {label} after a reset, but it has not yet re-earned re-entry ({score:.2f})."
    if status == "recovering-clearance-reset":
        return f"Fresh clearance-side evidence is returning for {label} after a reset, but it has not yet re-earned re-entry ({score:.2f})."
    if status == "reentering-confirmation":
        return f"Fresh confirmation-side support is strong enough that {label} may re-enter confirmation-side reacquisition soon ({score:.2f})."
    if status == "reentering-clearance":
        return f"Fresh clearance-side pressure is strong enough that {label} may re-enter clearance-side reacquisition soon ({score:.2f})."
    if status == "reversing":
        return f"The post-reset recovery attempt for {label} is changing direction, so re-entry stays blocked ({score:.2f})."
    if status == "blocked":
        return f"Local target instability is still preventing positive confirmation-side re-entry for {label}."
    if recovering_confirmation_hotspots:
        hotspot = recovering_confirmation_hotspots[0]
        return (
            f"Confirmation-side reset recovery is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "but those classes still need fresh follow-through before they can re-enter stronger reacquisition."
        )
    if recovering_clearance_hotspots:
        hotspot = recovering_clearance_hotspots[0]
        return (
            f"Clearance-side reset recovery is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes are closest to re-entering stronger clearance-side reacquisition."
        )
    return "No reset-refresh recovery is strong enough yet to re-enter the reacquisition ladder."


def _closure_forecast_reset_reentry_summary(
    primary_target: dict,
    recovering_confirmation_hotspots: list[dict],
    recovering_clearance_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    status = primary_target.get("closure_forecast_reset_reentry_status", "none")
    reason = primary_target.get("closure_forecast_reset_reentry_reason", "")
    if status == "reentered-confirmation":
        return reason or f"Fresh confirmation-side follow-through has re-earned re-entry into stronger confirmation-side reacquisition for {label}."
    if status == "reentered-clearance":
        return reason or f"Fresh clearance-side pressure has re-earned re-entry into stronger clearance-side reacquisition for {label}."
    if status == "pending-confirmation-reentry":
        return reason or f"Confirmation-side evidence is returning for {label}, but re-entry has not been fully re-earned yet."
    if status == "pending-clearance-reentry":
        return reason or f"Clearance-side evidence is returning for {label}, but re-entry has not been fully re-earned yet."
    if status == "blocked":
        return reason or f"Local target instability is still preventing positive confirmation-side re-entry for {label}."
    if recovering_confirmation_hotspots:
        hotspot = recovering_confirmation_hotspots[0]
        return (
            f"Confirmation-side reset re-entry is most active around {hotspot.get('label', 'recent hotspots')}, "
            "but those classes still need fresh, stable follow-through before stronger reacquisition returns."
        )
    if recovering_clearance_hotspots:
        hotspot = recovering_clearance_hotspots[0]
        return (
            f"Clearance-side reset re-entry is most active around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes still need fresh pressure to keep rebuilding stronger clearance-side reacquisition."
        )
    return "No reset re-entry is re-earning stronger reacquisition posture right now."


def _apply_reacquisition_reset_refresh_recovery_and_reentry(
    resolution_targets: list[dict],
    history: list[dict],
    *,
    current_generated_at: str,
    confidence_calibration: dict,
) -> dict:
    if not resolution_targets:
        return {
            "primary_target_closure_forecast_reset_refresh_recovery_score": 0.0,
            "primary_target_closure_forecast_reset_refresh_recovery_status": "none",
            "primary_target_closure_forecast_reset_reentry_status": "none",
            "primary_target_closure_forecast_reset_reentry_reason": "",
            "closure_forecast_reset_refresh_recovery_summary": "No reset-refresh recovery is recorded because there is no active target.",
            "closure_forecast_reset_reentry_summary": "No reset re-entry is recorded because there is no active target.",
            "closure_forecast_reset_refresh_window_runs": CLASS_RESET_REENTRY_WINDOW_RUNS,
            "recovering_from_confirmation_reset_hotspots": [],
            "recovering_from_clearance_reset_hotspots": [],
        }

    current_primary_target = resolution_targets[0]
    current_bucket = _recommendation_bucket(current_primary_target)
    closure_forecast_events = _class_closure_forecast_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )
    transition_events = _class_transition_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )

    updated_targets: list[dict] = []
    for target in resolution_targets:
        reset_refresh_recovery_score = 0.0
        reset_refresh_recovery_status = "none"
        reset_reentry_status = "none"
        reset_reentry_reason = ""
        reset_refresh_path = ""
        closure_likely_outcome = target.get("transition_closure_likely_outcome", "none")
        closure_hysteresis_status = target.get("closure_forecast_hysteresis_status", "none")
        closure_hysteresis_reason = target.get("closure_forecast_hysteresis_reason", "")
        transition_status = target.get("class_reweight_transition_status", "none")
        transition_reason = target.get("class_reweight_transition_reason", "")
        resolution_status = target.get("class_transition_resolution_status", "none")
        resolution_reason = target.get("class_transition_resolution_reason", "")
        reacquisition_status = target.get("closure_forecast_reacquisition_status", "none")
        reacquisition_reason = target.get("closure_forecast_reacquisition_reason", "")
        reacquisition_age_runs = target.get("closure_forecast_reacquisition_age_runs", 0)
        persistence_score = target.get("closure_forecast_reacquisition_persistence_score", 0.0)
        persistence_status = target.get("closure_forecast_reacquisition_persistence_status", "none")
        persistence_reason = target.get("closure_forecast_reacquisition_persistence_reason", "")

        if _recommendation_bucket(target) == current_bucket:
            transition_history_meta = _target_class_transition_history(target, transition_events)
            refresh_meta = _closure_forecast_reset_refresh_recovery_for_target(
                target,
                closure_forecast_events,
                transition_history_meta,
            )
            reset_refresh_recovery_score = refresh_meta["closure_forecast_reset_refresh_recovery_score"]
            reset_refresh_recovery_status = refresh_meta["closure_forecast_reset_refresh_recovery_status"]
            reset_reentry_status = refresh_meta["closure_forecast_reset_reentry_status"]
            reset_reentry_reason = refresh_meta["closure_forecast_reset_reentry_reason"]
            reset_refresh_path = refresh_meta["recent_reset_refresh_path"]
            control_updates = _apply_reset_refresh_reentry_control(
                target,
                refresh_meta=refresh_meta,
                transition_history_meta=transition_history_meta,
                closure_likely_outcome=closure_likely_outcome,
                closure_hysteresis_status=closure_hysteresis_status,
                closure_hysteresis_reason=closure_hysteresis_reason,
                transition_status=transition_status,
                transition_reason=transition_reason,
                resolution_status=resolution_status,
                resolution_reason=resolution_reason,
                reacquisition_status=reacquisition_status,
                reacquisition_reason=reacquisition_reason,
            )
            closure_likely_outcome = control_updates["transition_closure_likely_outcome"]
            closure_hysteresis_status = control_updates["closure_forecast_hysteresis_status"]
            closure_hysteresis_reason = control_updates["closure_forecast_hysteresis_reason"]
            transition_status = control_updates["class_reweight_transition_status"]
            transition_reason = control_updates["class_reweight_transition_reason"]
            resolution_status = control_updates["class_transition_resolution_status"]
            resolution_reason = control_updates["class_transition_resolution_reason"]
            reacquisition_status = control_updates["closure_forecast_reacquisition_status"]
            reacquisition_reason = control_updates["closure_forecast_reacquisition_reason"]
            reacquisition_age_runs = control_updates["closure_forecast_reacquisition_age_runs"]
            persistence_score = control_updates["closure_forecast_reacquisition_persistence_score"]
            persistence_status = control_updates["closure_forecast_reacquisition_persistence_status"]
            persistence_reason = control_updates["closure_forecast_reacquisition_persistence_reason"]

        updated_targets.append(
            {
                **target,
                "closure_forecast_reset_refresh_recovery_score": reset_refresh_recovery_score,
                "closure_forecast_reset_refresh_recovery_status": reset_refresh_recovery_status,
                "closure_forecast_reset_reentry_status": reset_reentry_status,
                "closure_forecast_reset_reentry_reason": reset_reentry_reason,
                "recent_reset_refresh_path": reset_refresh_path,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reacquisition_status": reacquisition_status,
                "closure_forecast_reacquisition_reason": reacquisition_reason,
                "closure_forecast_reacquisition_age_runs": reacquisition_age_runs,
                "closure_forecast_reacquisition_persistence_score": persistence_score,
                "closure_forecast_reacquisition_persistence_status": persistence_status,
                "closure_forecast_reacquisition_persistence_reason": persistence_reason,
            }
        )

    resolution_targets[:] = updated_targets
    primary_target = resolution_targets[0]
    recovering_from_confirmation_reset_hotspots = _closure_forecast_reset_refresh_hotspots(
        resolution_targets,
        mode="confirmation",
    )
    recovering_from_clearance_reset_hotspots = _closure_forecast_reset_refresh_hotspots(
        resolution_targets,
        mode="clearance",
    )
    return {
        "primary_target_closure_forecast_reset_refresh_recovery_score": primary_target.get(
            "closure_forecast_reset_refresh_recovery_score",
            0.0,
        ),
        "primary_target_closure_forecast_reset_refresh_recovery_status": primary_target.get(
            "closure_forecast_reset_refresh_recovery_status",
            "none",
        ),
        "primary_target_closure_forecast_reset_reentry_status": primary_target.get(
            "closure_forecast_reset_reentry_status",
            "none",
        ),
        "primary_target_closure_forecast_reset_reentry_reason": primary_target.get(
            "closure_forecast_reset_reentry_reason",
            "",
        ),
        "closure_forecast_reset_refresh_recovery_summary": _closure_forecast_reset_refresh_recovery_summary(
            primary_target,
            recovering_from_confirmation_reset_hotspots,
            recovering_from_clearance_reset_hotspots,
        ),
        "closure_forecast_reset_reentry_summary": _closure_forecast_reset_reentry_summary(
            primary_target,
            recovering_from_confirmation_reset_hotspots,
            recovering_from_clearance_reset_hotspots,
        ),
        "closure_forecast_reset_refresh_window_runs": CLASS_RESET_REENTRY_WINDOW_RUNS,
        "recovering_from_confirmation_reset_hotspots": recovering_from_confirmation_reset_hotspots,
        "recovering_from_clearance_reset_hotspots": recovering_from_clearance_reset_hotspots,
    }


def _closure_forecast_reset_reentry_side_from_status(status: str) -> str:
    if status in {"pending-confirmation-reentry", "reentered-confirmation"}:
        return "confirmation"
    if status in {"pending-clearance-reentry", "reentered-clearance"}:
        return "clearance"
    return "none"


def _closure_forecast_reset_reentry_side_from_recovery_status(status: str) -> str:
    if status in {"recovering-confirmation-reset", "reentering-confirmation"}:
        return "confirmation"
    if status in {"recovering-clearance-reset", "reentering-clearance"}:
        return "clearance"
    return "none"


def _closure_forecast_reset_reentry_side_from_event(event: dict) -> str:
    side = _closure_forecast_reset_reentry_side_from_status(
        event.get("closure_forecast_reset_reentry_status", "none")
    )
    if side != "none":
        return side
    return _closure_forecast_reset_reentry_side_from_recovery_status(
        event.get("closure_forecast_reset_refresh_recovery_status", "none")
    )


def _closure_forecast_reset_reentry_path_label(event: dict) -> str:
    reentry_status = event.get("closure_forecast_reset_reentry_status", "none") or "none"
    if reentry_status != "none":
        return reentry_status
    recovery_status = event.get("closure_forecast_reset_refresh_recovery_status", "none") or "none"
    if recovery_status != "none":
        return recovery_status
    reset_status = event.get("closure_forecast_persistence_reset_status", "none") or "none"
    if reset_status != "none":
        return reset_status
    likely_outcome = event.get("transition_closure_likely_outcome", "none") or "none"
    if likely_outcome != "none":
        return likely_outcome
    return "hold"


def _closure_forecast_event_matches_target_state(event: dict, target: dict) -> bool:
    return (
        event.get("key") == _queue_identity(target)
        and event.get("class_key") == _target_class_key(target)
        and float(event.get("closure_forecast_reweight_score", 0.0) or 0.0)
        == float(target.get("closure_forecast_reweight_score", 0.0) or 0.0)
        and event.get("closure_forecast_reweight_direction", "neutral")
        == target.get("closure_forecast_reweight_direction", "neutral")
        and event.get("closure_forecast_reset_refresh_recovery_status", "none")
        == target.get("closure_forecast_reset_refresh_recovery_status", "none")
        and event.get("closure_forecast_reset_reentry_status", "none")
        == target.get("closure_forecast_reset_reentry_status", "none")
        and event.get("closure_forecast_reset_reentry_persistence_status", "none")
        == target.get("closure_forecast_reset_reentry_persistence_status", "none")
        and event.get("closure_forecast_reset_reentry_churn_status", "none")
        == target.get("closure_forecast_reset_reentry_churn_status", "none")
        and event.get("closure_forecast_reset_reentry_freshness_status", "insufficient-data")
        == target.get("closure_forecast_reset_reentry_freshness_status", "insufficient-data")
        and event.get("closure_forecast_reset_reentry_reset_status", "none")
        == target.get("closure_forecast_reset_reentry_reset_status", "none")
        and event.get("closure_forecast_reset_reentry_refresh_recovery_status", "none")
        == target.get("closure_forecast_reset_reentry_refresh_recovery_status", "none")
        and event.get("closure_forecast_reset_reentry_rebuild_status", "none")
        == target.get("closure_forecast_reset_reentry_rebuild_status", "none")
        and event.get("closure_forecast_reset_reentry_rebuild_persistence_status", "none")
        == target.get("closure_forecast_reset_reentry_rebuild_persistence_status", "none")
        and event.get("closure_forecast_reset_reentry_rebuild_churn_status", "none")
        == target.get("closure_forecast_reset_reentry_rebuild_churn_status", "none")
        and event.get("closure_forecast_reset_reentry_rebuild_freshness_status", "insufficient-data")
        == target.get("closure_forecast_reset_reentry_rebuild_freshness_status", "insufficient-data")
        and event.get("closure_forecast_reset_reentry_rebuild_reset_status", "none")
        == target.get("closure_forecast_reset_reentry_rebuild_reset_status", "none")
        and event.get("closure_forecast_reacquisition_freshness_status", "insufficient-data")
        == target.get("closure_forecast_reacquisition_freshness_status", "insufficient-data")
        and event.get("closure_forecast_persistence_reset_status", "none")
        == target.get("closure_forecast_persistence_reset_status", "none")
        and event.get("transition_closure_likely_outcome", "none")
        == target.get("transition_closure_likely_outcome", "none")
    )


def _current_closure_forecast_event_for_target(target: dict) -> dict:
    return {
        "key": _queue_identity(target),
        "class_key": _target_class_key(target),
        "label": _target_label(target),
        "generated_at": "",
        "closure_forecast_reweight_score": target.get("closure_forecast_reweight_score", 0.0),
        "closure_forecast_reweight_direction": target.get(
            "closure_forecast_reweight_direction",
            "neutral",
        ),
        "transition_closure_likely_outcome": target.get(
            "transition_closure_likely_outcome",
            "none",
        ),
        "class_reweight_transition_status": target.get(
            "class_reweight_transition_status",
            "none",
        ),
        "class_transition_resolution_status": target.get(
            "class_transition_resolution_status",
            "none",
        ),
        "closure_forecast_hysteresis_status": target.get(
            "closure_forecast_hysteresis_status",
            "none",
        ),
        "closure_forecast_momentum_status": target.get(
            "closure_forecast_momentum_status",
            "insufficient-data",
        ),
        "closure_forecast_stability_status": target.get(
            "closure_forecast_stability_status",
            "watch",
        ),
        "closure_forecast_freshness_status": target.get(
            "closure_forecast_freshness_status",
            "insufficient-data",
        ),
        "closure_forecast_decay_status": target.get(
            "closure_forecast_decay_status",
            "none",
        ),
        "closure_forecast_refresh_recovery_status": target.get(
            "closure_forecast_refresh_recovery_status",
            "none",
        ),
        "closure_forecast_reacquisition_status": target.get(
            "closure_forecast_reacquisition_status",
            "none",
        ),
        "closure_forecast_reacquisition_persistence_status": target.get(
            "closure_forecast_reacquisition_persistence_status",
            "none",
        ),
        "closure_forecast_recovery_churn_status": target.get(
            "closure_forecast_recovery_churn_status",
            "none",
        ),
        "closure_forecast_reacquisition_freshness_status": target.get(
            "closure_forecast_reacquisition_freshness_status",
            "insufficient-data",
        ),
        "closure_forecast_persistence_reset_status": target.get(
            "closure_forecast_persistence_reset_status",
            "none",
        ),
        "closure_forecast_reset_refresh_recovery_status": target.get(
            "closure_forecast_reset_refresh_recovery_status",
            "none",
        ),
        "closure_forecast_reset_reentry_status": target.get(
            "closure_forecast_reset_reentry_status",
            "none",
        ),
        "closure_forecast_reset_reentry_persistence_status": target.get(
            "closure_forecast_reset_reentry_persistence_status",
            "none",
        ),
        "closure_forecast_reset_reentry_churn_status": target.get(
            "closure_forecast_reset_reentry_churn_status",
            "none",
        ),
        "closure_forecast_reset_reentry_freshness_status": target.get(
            "closure_forecast_reset_reentry_freshness_status",
            "insufficient-data",
        ),
        "closure_forecast_reset_reentry_reset_status": target.get(
            "closure_forecast_reset_reentry_reset_status",
            "none",
        ),
        "closure_forecast_reset_reentry_refresh_recovery_status": target.get(
            "closure_forecast_reset_reentry_refresh_recovery_status",
            "none",
        ),
        "closure_forecast_reset_reentry_rebuild_status": target.get(
            "closure_forecast_reset_reentry_rebuild_status",
            "none",
        ),
        "closure_forecast_reset_reentry_rebuild_persistence_status": target.get(
            "closure_forecast_reset_reentry_rebuild_persistence_status",
            "none",
        ),
        "closure_forecast_reset_reentry_rebuild_churn_status": target.get(
            "closure_forecast_reset_reentry_rebuild_churn_status",
            "none",
        ),
        "closure_forecast_reset_reentry_rebuild_freshness_status": target.get(
            "closure_forecast_reset_reentry_rebuild_freshness_status",
            "insufficient-data",
        ),
        "closure_forecast_reset_reentry_rebuild_reset_status": target.get(
            "closure_forecast_reset_reentry_rebuild_reset_status",
            "none",
        ),
    }


def _ordered_reset_reentry_events_for_target(
    target: dict,
    closure_forecast_events: list[dict],
) -> list[dict]:
    class_key = _target_class_key(target)
    matching_events = [
        event for event in closure_forecast_events if event.get("class_key") == class_key
    ][:CLASS_RESET_REENTRY_PERSISTENCE_WINDOW_RUNS]
    if not matching_events:
        return [_current_closure_forecast_event_for_target(target)]

    current_index = next(
        (
            index
            for index, event in enumerate(matching_events)
            if event.get("generated_at", "") == ""
            and event.get("key") == _queue_identity(target)
        ),
        None,
    )
    if current_index is not None:
        if current_index == 0:
            return matching_events
        current_event = matching_events[current_index]
        remainder = matching_events[:current_index] + matching_events[current_index + 1 :]
        return [current_event, *remainder][:CLASS_RESET_REENTRY_PERSISTENCE_WINDOW_RUNS]

    matching_index = next(
        (
            index
            for index, event in enumerate(matching_events)
            if _closure_forecast_event_matches_target_state(event, target)
        ),
        None,
    )
    if matching_index is not None:
        if matching_index == 0:
            return matching_events
        current_event = matching_events[matching_index]
        remainder = matching_events[:matching_index] + matching_events[matching_index + 1 :]
        return [current_event, *remainder][:CLASS_RESET_REENTRY_PERSISTENCE_WINDOW_RUNS]

    return [
        _current_closure_forecast_event_for_target(target),
        *matching_events,
    ][:CLASS_RESET_REENTRY_PERSISTENCE_WINDOW_RUNS]


def _closure_forecast_reset_reentry_persistence_for_target(
    target: dict,
    closure_forecast_events: list[dict],
    transition_history_meta: dict,
) -> dict:
    matching_events = _ordered_reset_reentry_events_for_target(
        target,
        closure_forecast_events,
    )
    relevant_events = [
        event for event in matching_events if _closure_forecast_reset_reentry_side_from_event(event) != "none"
    ]
    current_side = (
        _closure_forecast_reset_reentry_side_from_event(matching_events[0]) if matching_events else "none"
    )
    persistence_age_runs = 0
    for event in matching_events:
        event_side = _closure_forecast_reset_reentry_side_from_event(event)
        if event_side != current_side or event_side == "none":
            break
        persistence_age_runs += 1

    weighted_total = 0.0
    weight_sum = 0.0
    directions: list[str] = []
    for index, event in enumerate(relevant_events[:CLASS_RESET_REENTRY_PERSISTENCE_WINDOW_RUNS]):
        weight = (1.0, 0.8, 0.6, 0.4)[
            min(index, CLASS_RESET_REENTRY_PERSISTENCE_WINDOW_RUNS - 1)
        ]
        event_side = _closure_forecast_reset_reentry_side_from_event(event)
        sign = 1.0 if event_side == "confirmation" else -1.0
        directions.append(
            "supporting-confirmation" if sign > 0 else "supporting-clearance"
        )
        magnitude = 0.0
        if event.get("closure_forecast_reset_reentry_status", "none") in {
            "reentered-confirmation",
            "reentered-clearance",
        }:
            magnitude += 0.15
        if event.get("closure_forecast_reset_refresh_recovery_status", "none") in {
            "reentering-confirmation",
            "reentering-clearance",
        }:
            magnitude += 0.10
        momentum_status = event.get("closure_forecast_momentum_status", "insufficient-data")
        if (
            event_side == "confirmation" and momentum_status == "sustained-confirmation"
        ) or (
            event_side == "clearance" and momentum_status == "sustained-clearance"
        ):
            magnitude += 0.10
        stability_status = event.get("closure_forecast_stability_status", "watch")
        if stability_status == "stable":
            magnitude += 0.10
        freshness_status = event.get(
            "closure_forecast_reacquisition_freshness_status",
            "insufficient-data",
        )
        if freshness_status == "fresh":
            magnitude += 0.10
        elif freshness_status == "mixed-age":
            magnitude = max(0.0, magnitude - 0.10)
        if momentum_status in {"reversing", "unstable"}:
            magnitude = max(0.0, magnitude - 0.15)
        if stability_status == "oscillating":
            magnitude = max(0.0, magnitude - 0.15)
        if event.get("closure_forecast_persistence_reset_status", "none") != "none":
            magnitude = max(0.0, magnitude - 0.15)
        weighted_total += sign * magnitude * weight
        weight_sum += weight

    persistence_score = _clamp_round(
        weighted_total / max(weight_sum, 1.0),
        lower=-0.95,
        upper=0.95,
    )
    current_momentum_status = target.get("closure_forecast_momentum_status", "insufficient-data")
    current_stability_status = target.get("closure_forecast_stability_status", "watch")
    current_freshness_status = target.get(
        "closure_forecast_reacquisition_freshness_status",
        "insufficient-data",
    )
    earlier_majority = _closure_forecast_direction_majority(directions[1:])
    current_direction = (
        "supporting-confirmation"
        if current_side == "confirmation"
        else "supporting-clearance"
        if current_side == "clearance"
        else "neutral"
    )

    if current_side == "none" and not relevant_events:
        persistence_status = "none"
    elif (
        target.get("closure_forecast_reset_reentry_status", "none")
        in {"reentered-confirmation", "reentered-clearance"}
        and persistence_age_runs == 1
    ):
        persistence_status = "just-reentered"
    elif len(relevant_events) < 2:
        persistence_status = "insufficient-data"
    elif (
        _closure_forecast_direction_reversing(current_direction, earlier_majority)
        or current_momentum_status in {"reversing", "unstable"}
        or target.get("closure_forecast_persistence_reset_status", "none") != "none"
    ):
        persistence_status = "reversing"
    elif (
        current_side == "confirmation"
        and persistence_age_runs >= 3
        and current_freshness_status == "fresh"
        and current_momentum_status == "sustained-confirmation"
        and current_stability_status != "oscillating"
    ):
        persistence_status = "sustained-confirmation-reentry"
    elif (
        current_side == "clearance"
        and persistence_age_runs >= 3
        and current_freshness_status == "fresh"
        and current_momentum_status == "sustained-clearance"
        and current_stability_status != "oscillating"
    ):
        persistence_status = "sustained-clearance-reentry"
    elif current_side == "confirmation" and persistence_age_runs >= 2 and persistence_score > 0:
        persistence_status = "holding-confirmation-reentry"
    elif current_side == "clearance" and persistence_age_runs >= 2 and persistence_score < 0:
        persistence_status = "holding-clearance-reentry"
    else:
        persistence_status = "none"

    if persistence_status == "just-reentered":
        persistence_reason = "Stronger closure-forecast posture has re-entered after reset, but it has not yet proved it can hold."
    elif persistence_status == "holding-confirmation-reentry":
        persistence_reason = "Confirmation-side reset re-entry has stayed aligned long enough to keep the restored forecast in place."
    elif persistence_status == "holding-clearance-reentry":
        persistence_reason = "Clearance-side reset re-entry has stayed aligned long enough to keep the restored forecast in place."
    elif persistence_status == "sustained-confirmation-reentry":
        persistence_reason = "Confirmation-side reset re-entry is now holding with enough follow-through to trust the restored forecast more."
    elif persistence_status == "sustained-clearance-reentry":
        persistence_reason = "Clearance-side reset re-entry is now holding with enough follow-through to trust the restored caution more."
    elif persistence_status == "reversing":
        persistence_reason = "The restored reset re-entry posture is already weakening, so it is being softened again."
    elif persistence_status == "insufficient-data":
        persistence_reason = "Reset re-entry is still too lightly exercised to say whether the restored forecast can hold."
    else:
        persistence_reason = ""

    return {
        "closure_forecast_reset_reentry_age_runs": persistence_age_runs,
        "closure_forecast_reset_reentry_persistence_score": persistence_score,
        "closure_forecast_reset_reentry_persistence_status": persistence_status,
        "closure_forecast_reset_reentry_persistence_reason": persistence_reason,
        "recent_reset_reentry_persistence_path": " -> ".join(
            _closure_forecast_reset_reentry_path_label(event) for event in matching_events if event
        ),
    }


def _closure_forecast_reset_reentry_churn_for_target(
    target: dict,
    closure_forecast_events: list[dict],
    transition_history_meta: dict,
) -> dict:
    matching_events = _ordered_reset_reentry_events_for_target(
        target,
        closure_forecast_events,
    )
    relevant_events = [
        event for event in matching_events if _closure_forecast_reset_reentry_side_from_event(event) != "none"
    ]
    side_path = [
        _closure_forecast_reset_reentry_side_from_event(event) for event in relevant_events
    ]
    current_side = side_path[0] if side_path else "none"
    local_noise = _target_specific_normalization_noise(target, transition_history_meta)
    if current_side == "none":
        churn_score = 0.0
        churn_status = "none"
        churn_reason = ""
    else:
        flip_count = _class_direction_flip_count(
            [
                "supporting-confirmation" if side == "confirmation" else "supporting-clearance"
                for side in side_path
            ]
        )
        churn_score = float(flip_count) * 0.20
        stability_status = target.get("closure_forecast_stability_status", "watch")
        momentum_status = target.get("closure_forecast_momentum_status", "insufficient-data")
        if stability_status == "oscillating":
            churn_score += 0.15
        if momentum_status == "reversing":
            churn_score += 0.10
        if momentum_status == "unstable":
            churn_score += 0.10
        freshness_path = [
            event.get("closure_forecast_reacquisition_freshness_status", "insufficient-data")
            for event in relevant_events
        ]
        if any(
            previous == "fresh" and current in {"mixed-age", "stale", "insufficient-data"}
            for previous, current in zip(freshness_path, freshness_path[1:])
        ):
            churn_score += 0.10
        if any(
            event.get("closure_forecast_persistence_reset_status", "none") != "none"
            for event in relevant_events
        ):
            churn_score += 0.10
        if (
            len(relevant_events) >= 2
            and side_path[0] == side_path[1]
            and relevant_events[0].get("closure_forecast_reacquisition_freshness_status", "insufficient-data") == "fresh"
            and relevant_events[1].get("closure_forecast_reacquisition_freshness_status", "insufficient-data") == "fresh"
        ):
            churn_score -= 0.10
        churn_score = _clamp_round(churn_score, lower=0.0, upper=0.95)
        if local_noise and current_side == "confirmation":
            churn_status = "blocked"
            churn_reason = "Local target instability is preventing positive confirmation-side reset re-entry persistence."
        elif churn_score >= 0.45 or flip_count >= 2:
            churn_status = "churn"
            churn_reason = "Reset re-entry recovery is flipping enough that restored posture should be softened quickly."
        elif churn_score >= 0.20:
            churn_status = "watch"
            churn_reason = "Reset re-entry recovery is wobbling and may lose its restored strength soon."
        else:
            churn_status = "none"
            churn_reason = ""

    return {
        "closure_forecast_reset_reentry_churn_score": churn_score,
        "closure_forecast_reset_reentry_churn_status": churn_status,
        "closure_forecast_reset_reentry_churn_reason": churn_reason,
        "recent_reset_reentry_churn_path": " -> ".join(
            _closure_forecast_reset_reentry_path_label(event) for event in matching_events if event
        ),
    }


def _apply_reset_reentry_persistence_and_churn_control(
    target: dict,
    *,
    persistence_meta: dict,
    churn_meta: dict,
    transition_history_meta: dict,
    closure_likely_outcome: str,
    closure_hysteresis_status: str,
    closure_hysteresis_reason: str,
    transition_status: str,
    transition_reason: str,
    resolution_status: str,
    resolution_reason: str,
) -> dict:
    persistence_status = persistence_meta.get(
        "closure_forecast_reset_reentry_persistence_status",
        "none",
    )
    persistence_reason = persistence_meta.get(
        "closure_forecast_reset_reentry_persistence_reason",
        "",
    )
    churn_status = churn_meta.get("closure_forecast_reset_reentry_churn_status", "none")
    churn_reason = churn_meta.get("closure_forecast_reset_reentry_churn_reason", "")
    current_reentry_status = target.get("closure_forecast_reset_reentry_status", "none")
    current_freshness_status = target.get(
        "closure_forecast_reacquisition_freshness_status",
        "insufficient-data",
    )
    transition_age_runs = int(target.get("class_transition_age_runs", 0) or 0)
    recent_pending_status = transition_history_meta.get("recent_pending_status", "none")
    current_side = _closure_forecast_reset_reentry_side_from_status(current_reentry_status)
    if current_side == "none":
        current_side = _closure_forecast_reset_reentry_side_from_recovery_status(
            target.get("closure_forecast_reset_refresh_recovery_status", "none")
        )
    if (
        current_side == "none"
        and persistence_status in {"none", "insufficient-data"}
        and churn_status == "none"
    ):
        return {
            "transition_closure_likely_outcome": closure_likely_outcome,
            "closure_forecast_hysteresis_status": closure_hysteresis_status,
            "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
        }

    if churn_status == "blocked" and current_side == "confirmation":
        if closure_likely_outcome == "confirm-soon":
            closure_likely_outcome = "hold"
        if closure_hysteresis_status == "confirmed-confirmation":
            closure_hysteresis_status = "pending-confirmation"
        closure_hysteresis_reason = churn_reason or persistence_reason or closure_hysteresis_reason
        return {
            "transition_closure_likely_outcome": closure_likely_outcome,
            "closure_forecast_hysteresis_status": closure_hysteresis_status,
            "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
        }

    if current_freshness_status in {"stale", "insufficient-data"}:
        if closure_likely_outcome == "confirm-soon":
            closure_likely_outcome = "hold"
            if closure_hysteresis_status == "confirmed-confirmation":
                closure_hysteresis_status = "pending-confirmation"
                closure_hysteresis_reason = persistence_reason or churn_reason or closure_hysteresis_reason
        elif closure_likely_outcome == "expire-risk":
            closure_likely_outcome = "clear-risk"
            if closure_hysteresis_status == "confirmed-clearance":
                closure_hysteresis_status = "pending-clearance"
                closure_hysteresis_reason = persistence_reason or churn_reason or closure_hysteresis_reason
        elif closure_likely_outcome == "clear-risk":
            closure_likely_outcome = "hold"
            if closure_hysteresis_status == "confirmed-clearance":
                closure_hysteresis_status = "pending-clearance"
                closure_hysteresis_reason = persistence_reason or churn_reason or closure_hysteresis_reason

    if current_reentry_status == "reentered-confirmation":
        if persistence_status in {
            "holding-confirmation-reentry",
            "sustained-confirmation-reentry",
        } and churn_status != "churn":
            return {
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
            }
        if persistence_status == "reversing" or churn_status == "churn":
            closure_likely_outcome = "hold"
            if closure_hysteresis_status == "confirmed-confirmation":
                closure_hysteresis_status = "pending-confirmation"
            closure_hysteresis_reason = churn_reason or persistence_reason or closure_hysteresis_reason

    if current_reentry_status == "reentered-clearance":
        if persistence_status in {
            "holding-clearance-reentry",
            "sustained-clearance-reentry",
        } and churn_status != "churn":
            if closure_likely_outcome == "expire-risk" and transition_age_runs < 3:
                closure_likely_outcome = "clear-risk"
            return {
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
            }
        if (
            persistence_status in {"reversing", "none", "insufficient-data"}
            or churn_status == "churn"
            or current_freshness_status in {"stale", "insufficient-data"}
        ):
            if closure_likely_outcome == "expire-risk":
                closure_likely_outcome = "clear-risk"
            elif closure_likely_outcome == "clear-risk":
                closure_likely_outcome = "hold"
            if closure_hysteresis_status == "confirmed-clearance":
                closure_hysteresis_status = "pending-clearance"
            closure_hysteresis_reason = churn_reason or persistence_reason or closure_hysteresis_reason
            if resolution_status == "cleared" and recent_pending_status in {
                "pending-support",
                "pending-caution",
            }:
                restore_reason = churn_reason or persistence_reason or (
                    "Reset re-entry stopped holding cleanly, so the earlier-clear posture has been withdrawn."
                )
                transition_status = recent_pending_status
                transition_reason = restore_reason
                resolution_status = "none"
                resolution_reason = ""

    return {
        "transition_closure_likely_outcome": closure_likely_outcome,
        "closure_forecast_hysteresis_status": closure_hysteresis_status,
        "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
        "class_reweight_transition_status": transition_status,
        "class_reweight_transition_reason": transition_reason,
        "class_transition_resolution_status": resolution_status,
        "class_transition_resolution_reason": resolution_reason,
    }


def _closure_forecast_reset_reentry_hotspots(
    resolution_targets: list[dict],
    *,
    mode: str,
) -> list[dict]:
    grouped: dict[str, dict] = {}
    for target in resolution_targets:
        class_key = _target_class_key(target)
        if not class_key:
            continue
        current = {
            "scope": "class",
            "label": class_key,
            "closure_forecast_reset_reentry_age_runs": target.get(
                "closure_forecast_reset_reentry_age_runs",
                0,
            ),
            "closure_forecast_reset_reentry_persistence_score": target.get(
                "closure_forecast_reset_reentry_persistence_score",
                0.0,
            ),
            "closure_forecast_reset_reentry_persistence_status": target.get(
                "closure_forecast_reset_reentry_persistence_status",
                "none",
            ),
            "closure_forecast_reset_reentry_churn_score": target.get(
                "closure_forecast_reset_reentry_churn_score",
                0.0,
            ),
            "closure_forecast_reset_reentry_churn_status": target.get(
                "closure_forecast_reset_reentry_churn_status",
                "none",
            ),
            "recent_reset_reentry_persistence_path": target.get(
                "recent_reset_reentry_persistence_path",
                "",
            ),
            "recent_reset_reentry_churn_path": target.get(
                "recent_reset_reentry_churn_path",
                "",
            ),
        }
        existing = grouped.get(class_key)
        if existing is None or abs(
            current["closure_forecast_reset_reentry_persistence_score"]
        ) > abs(existing["closure_forecast_reset_reentry_persistence_score"]):
            grouped[class_key] = current
    hotspots = list(grouped.values())
    if mode == "just-reentered":
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reset_reentry_persistence_status")
            == "just-reentered"
        ]
        hotspots.sort(
            key=lambda item: (
                -item.get("closure_forecast_reset_reentry_age_runs", 0),
                -abs(item.get("closure_forecast_reset_reentry_persistence_score", 0.0)),
                item.get("label", ""),
            )
        )
    elif mode == "holding":
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reset_reentry_persistence_status")
            in {
                "holding-confirmation-reentry",
                "holding-clearance-reentry",
                "sustained-confirmation-reentry",
                "sustained-clearance-reentry",
            }
        ]
        hotspots.sort(
            key=lambda item: (
                -item.get("closure_forecast_reset_reentry_age_runs", 0),
                -abs(item.get("closure_forecast_reset_reentry_persistence_score", 0.0)),
                item.get("label", ""),
            )
        )
    else:
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reset_reentry_churn_status")
            in {"watch", "churn", "blocked"}
        ]
        hotspots.sort(
            key=lambda item: (
                -item.get("closure_forecast_reset_reentry_churn_score", 0.0),
                -item.get("closure_forecast_reset_reentry_age_runs", 0),
                item.get("label", ""),
            )
        )
    return hotspots[:5]


def _closure_forecast_reset_reentry_persistence_summary(
    primary_target: dict,
    just_reentered_hotspots: list[dict],
    holding_reset_reentry_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    status = primary_target.get(
        "closure_forecast_reset_reentry_persistence_status",
        "none",
    )
    age_runs = primary_target.get("closure_forecast_reset_reentry_age_runs", 0)
    score = primary_target.get("closure_forecast_reset_reentry_persistence_score", 0.0)
    if status == "just-reentered":
        return f"{label} has only just re-entered stronger closure-forecast posture after reset, so it is still fragile ({score:.2f}; {age_runs} run)."
    if status == "holding-confirmation-reentry":
        return f"Confirmation-side reset re-entry for {label} has held long enough to keep the restored forecast in place ({score:.2f}; {age_runs} runs)."
    if status == "holding-clearance-reentry":
        return f"Clearance-side reset re-entry for {label} has held long enough to keep the restored caution in place ({score:.2f}; {age_runs} runs)."
    if status == "sustained-confirmation-reentry":
        return f"Confirmation-side reset re-entry for {label} is now holding with enough follow-through to trust the restored forecast more ({score:.2f}; {age_runs} runs)."
    if status == "sustained-clearance-reentry":
        return f"Clearance-side reset re-entry for {label} is now holding with enough follow-through to trust the restored caution more ({score:.2f}; {age_runs} runs)."
    if status == "reversing":
        return f"The restored reset re-entry posture for {label} is already weakening, so it is being softened again ({score:.2f})."
    if status == "insufficient-data":
        return f"Reset re-entry for {label} is still too lightly exercised to say whether the restored forecast can hold."
    if just_reentered_hotspots:
        hotspot = just_reentered_hotspots[0]
        return (
            f"Newly re-entered forecast posture is most fragile around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes still need follow-through before the restored forecast can be trusted."
        )
    if holding_reset_reentry_hotspots:
        hotspot = holding_reset_reentry_hotspots[0]
        return (
            f"Reset re-entry posture is holding most cleanly around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes are closest to keeping restored re-entry strength safely."
        )
    return "No reset re-entry posture is active enough yet to judge whether it can hold."


def _closure_forecast_reset_reentry_churn_summary(
    primary_target: dict,
    reset_reentry_churn_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    status = primary_target.get("closure_forecast_reset_reentry_churn_status", "none")
    score = primary_target.get("closure_forecast_reset_reentry_churn_score", 0.0)
    if status == "watch":
        return f"Reset re-entry recovery for {label} is wobbling enough that restored forecast strength may soften soon ({score:.2f})."
    if status == "churn":
        return f"Reset re-entry recovery for {label} is flipping enough that restored posture should be softened quickly ({score:.2f})."
    if status == "blocked":
        return primary_target.get(
            "closure_forecast_reset_reentry_churn_reason",
            f"Local target instability is preventing positive confirmation-side reset re-entry persistence for {label}.",
        )
    if reset_reentry_churn_hotspots:
        hotspot = reset_reentry_churn_hotspots[0]
        return (
            f"Reset re-entry churn is highest around {hotspot.get('label', 'recent hotspots')}, "
            "so restored posture there should soften quickly if the wobble continues."
        )
    return "No meaningful reset re-entry churn is active right now."


def _apply_reset_reentry_persistence_and_churn(
    resolution_targets: list[dict],
    history: list[dict],
    *,
    current_generated_at: str,
    confidence_calibration: dict,
) -> dict:
    if not resolution_targets:
        return {
            "primary_target_closure_forecast_reset_reentry_age_runs": 0,
            "primary_target_closure_forecast_reset_reentry_persistence_score": 0.0,
            "primary_target_closure_forecast_reset_reentry_persistence_status": "none",
            "primary_target_closure_forecast_reset_reentry_persistence_reason": "",
            "closure_forecast_reset_reentry_persistence_summary": "No reset re-entry persistence is recorded because there is no active target.",
            "closure_forecast_reset_reentry_window_runs": CLASS_RESET_REENTRY_PERSISTENCE_WINDOW_RUNS,
            "just_reentered_hotspots": [],
            "holding_reset_reentry_hotspots": [],
            "primary_target_closure_forecast_reset_reentry_churn_score": 0.0,
            "primary_target_closure_forecast_reset_reentry_churn_status": "none",
            "primary_target_closure_forecast_reset_reentry_churn_reason": "",
            "closure_forecast_reset_reentry_churn_summary": "No reset re-entry churn is recorded because there is no active target.",
            "reset_reentry_churn_hotspots": [],
        }

    current_primary_target = resolution_targets[0]
    current_bucket = _recommendation_bucket(current_primary_target)
    closure_forecast_events = _class_closure_forecast_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )
    transition_events = _class_transition_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )

    updated_targets: list[dict] = []
    for target in resolution_targets:
        persistence_age_runs = 0
        persistence_score = 0.0
        persistence_status = "none"
        persistence_reason = ""
        persistence_path = ""
        churn_score = 0.0
        churn_status = "none"
        churn_reason = ""
        churn_path = ""
        closure_likely_outcome = target.get("transition_closure_likely_outcome", "none")
        closure_hysteresis_status = target.get("closure_forecast_hysteresis_status", "none")
        closure_hysteresis_reason = target.get("closure_forecast_hysteresis_reason", "")
        transition_status = target.get("class_reweight_transition_status", "none")
        transition_reason = target.get("class_reweight_transition_reason", "")
        resolution_status = target.get("class_transition_resolution_status", "none")
        resolution_reason = target.get("class_transition_resolution_reason", "")

        if _recommendation_bucket(target) == current_bucket:
            transition_history_meta = _target_class_transition_history(target, transition_events)
            persistence_meta = _closure_forecast_reset_reentry_persistence_for_target(
                target,
                closure_forecast_events,
                transition_history_meta,
            )
            churn_meta = _closure_forecast_reset_reentry_churn_for_target(
                target,
                closure_forecast_events,
                transition_history_meta,
            )
            persistence_age_runs = persistence_meta["closure_forecast_reset_reentry_age_runs"]
            persistence_score = persistence_meta["closure_forecast_reset_reentry_persistence_score"]
            persistence_status = persistence_meta["closure_forecast_reset_reentry_persistence_status"]
            persistence_reason = persistence_meta["closure_forecast_reset_reentry_persistence_reason"]
            persistence_path = persistence_meta["recent_reset_reentry_persistence_path"]
            churn_score = churn_meta["closure_forecast_reset_reentry_churn_score"]
            churn_status = churn_meta["closure_forecast_reset_reentry_churn_status"]
            churn_reason = churn_meta["closure_forecast_reset_reentry_churn_reason"]
            churn_path = churn_meta["recent_reset_reentry_churn_path"]
            control_updates = _apply_reset_reentry_persistence_and_churn_control(
                target,
                persistence_meta=persistence_meta,
                churn_meta=churn_meta,
                transition_history_meta=transition_history_meta,
                closure_likely_outcome=closure_likely_outcome,
                closure_hysteresis_status=closure_hysteresis_status,
                closure_hysteresis_reason=closure_hysteresis_reason,
                transition_status=transition_status,
                transition_reason=transition_reason,
                resolution_status=resolution_status,
                resolution_reason=resolution_reason,
            )
            closure_likely_outcome = control_updates["transition_closure_likely_outcome"]
            closure_hysteresis_status = control_updates["closure_forecast_hysteresis_status"]
            closure_hysteresis_reason = control_updates["closure_forecast_hysteresis_reason"]
            transition_status = control_updates["class_reweight_transition_status"]
            transition_reason = control_updates["class_reweight_transition_reason"]
            resolution_status = control_updates["class_transition_resolution_status"]
            resolution_reason = control_updates["class_transition_resolution_reason"]

        updated_targets.append(
            {
                **target,
                "closure_forecast_reset_reentry_age_runs": persistence_age_runs,
                "closure_forecast_reset_reentry_persistence_score": persistence_score,
                "closure_forecast_reset_reentry_persistence_status": persistence_status,
                "closure_forecast_reset_reentry_persistence_reason": persistence_reason,
                "recent_reset_reentry_persistence_path": persistence_path,
                "closure_forecast_reset_reentry_churn_score": churn_score,
                "closure_forecast_reset_reentry_churn_status": churn_status,
                "closure_forecast_reset_reentry_churn_reason": churn_reason,
                "recent_reset_reentry_churn_path": churn_path,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
            }
        )

    resolution_targets[:] = updated_targets
    primary_target = resolution_targets[0]
    just_reentered_hotspots = _closure_forecast_reset_reentry_hotspots(
        resolution_targets,
        mode="just-reentered",
    )
    holding_reset_reentry_hotspots = _closure_forecast_reset_reentry_hotspots(
        resolution_targets,
        mode="holding",
    )
    reset_reentry_churn_hotspots = _closure_forecast_reset_reentry_hotspots(
        resolution_targets,
        mode="churn",
    )
    return {
        "primary_target_closure_forecast_reset_reentry_age_runs": primary_target.get(
            "closure_forecast_reset_reentry_age_runs",
            0,
        ),
        "primary_target_closure_forecast_reset_reentry_persistence_score": primary_target.get(
            "closure_forecast_reset_reentry_persistence_score",
            0.0,
        ),
        "primary_target_closure_forecast_reset_reentry_persistence_status": primary_target.get(
            "closure_forecast_reset_reentry_persistence_status",
            "none",
        ),
        "primary_target_closure_forecast_reset_reentry_persistence_reason": primary_target.get(
            "closure_forecast_reset_reentry_persistence_reason",
            "",
        ),
        "closure_forecast_reset_reentry_persistence_summary": _closure_forecast_reset_reentry_persistence_summary(
            primary_target,
            just_reentered_hotspots,
            holding_reset_reentry_hotspots,
        ),
        "closure_forecast_reset_reentry_window_runs": CLASS_RESET_REENTRY_PERSISTENCE_WINDOW_RUNS,
        "just_reentered_hotspots": just_reentered_hotspots,
        "holding_reset_reentry_hotspots": holding_reset_reentry_hotspots,
        "primary_target_closure_forecast_reset_reentry_churn_score": primary_target.get(
            "closure_forecast_reset_reentry_churn_score",
            0.0,
        ),
        "primary_target_closure_forecast_reset_reentry_churn_status": primary_target.get(
            "closure_forecast_reset_reentry_churn_status",
            "none",
        ),
        "primary_target_closure_forecast_reset_reentry_churn_reason": primary_target.get(
            "closure_forecast_reset_reentry_churn_reason",
            "",
        ),
        "closure_forecast_reset_reentry_churn_summary": _closure_forecast_reset_reentry_churn_summary(
            primary_target,
            reset_reentry_churn_hotspots,
        ),
        "reset_reentry_churn_hotspots": reset_reentry_churn_hotspots,
    }


def _closure_forecast_reset_reentry_side_from_persistence_status(status: str) -> str:
    if status in {
        "holding-confirmation-reentry",
        "sustained-confirmation-reentry",
    }:
        return "confirmation"
    if status in {
        "holding-clearance-reentry",
        "sustained-clearance-reentry",
    }:
        return "clearance"
    return "none"


def _closure_forecast_reset_reentry_memory_side_from_event(event: dict) -> str:
    side = _closure_forecast_reset_reentry_side_from_persistence_status(
        event.get("closure_forecast_reset_reentry_persistence_status", "none")
    )
    if side != "none":
        return side
    return _closure_forecast_reset_reentry_side_from_event(event)


def _reset_reentry_event_is_confirmation_like(event: dict) -> bool:
    event_side = _closure_forecast_reset_reentry_memory_side_from_event(event)
    persistence_status = event.get("closure_forecast_reset_reentry_persistence_status", "none")
    return (
        event.get("closure_forecast_reset_reentry_status", "none")
        in {"pending-confirmation-reentry", "reentered-confirmation"}
        or (
            persistence_status
            in {
                "just-reentered",
                "holding-confirmation-reentry",
                "sustained-confirmation-reentry",
            }
            and event_side == "confirmation"
        )
        or event.get("closure_forecast_hysteresis_status", "none")
        in {"pending-confirmation", "confirmed-confirmation"}
        or event.get("transition_closure_likely_outcome", "none") == "confirm-soon"
    )


def _reset_reentry_event_is_clearance_like(event: dict) -> bool:
    event_side = _closure_forecast_reset_reentry_memory_side_from_event(event)
    persistence_status = event.get("closure_forecast_reset_reentry_persistence_status", "none")
    return (
        event.get("closure_forecast_reset_reentry_status", "none")
        in {"pending-clearance-reentry", "reentered-clearance"}
        or (
            persistence_status
            in {
                "just-reentered",
                "holding-clearance-reentry",
                "sustained-clearance-reentry",
            }
            and event_side == "clearance"
        )
        or event.get("closure_forecast_hysteresis_status", "none")
        in {"pending-clearance", "confirmed-clearance"}
        or event.get("transition_closure_likely_outcome", "none")
        in {"clear-risk", "expire-risk"}
    )


def _reset_reentry_event_has_evidence(event: dict) -> bool:
    return (
        _reset_reentry_event_is_confirmation_like(event)
        or _reset_reentry_event_is_clearance_like(event)
        or event.get("closure_forecast_reset_reentry_churn_status", "none")
        in {"watch", "churn", "blocked"}
    )


def _reset_reentry_event_signal_label(event: dict) -> str:
    if _reset_reentry_event_is_confirmation_like(event):
        return "confirmation-like"
    if _reset_reentry_event_is_clearance_like(event):
        return "clearance-like"
    return "neutral"


def _closure_forecast_reset_reentry_freshness_reason(
    freshness_status: str,
    weighted_reset_reentry_evidence_count: float,
    recent_window_weight_share: float,
    decayed_confirmation_rate: float,
    decayed_clearance_rate: float,
) -> str:
    if freshness_status == "fresh":
        return (
            "Recent reset re-entry evidence is still current enough to trust, with "
            f"{recent_window_weight_share:.0%} of the weighted signal coming from the latest "
            f"{CLASS_RESET_REENTRY_FRESHNESS_WINDOW_RUNS} runs."
        )
    if freshness_status == "mixed-age":
        return (
            "Reset re-entry memory is still useful, but it is partly aging: "
            f"{recent_window_weight_share:.0%} of the weighted signal is recent and the rest is older carry-forward."
        )
    if freshness_status == "stale":
        return (
            "Older reset re-entry strength is carrying more of the signal than recent runs, so it should not keep stronger posture alive on memory alone."
        )
    return (
        "Reset re-entry memory is still too lightly exercised to judge freshness, with "
        f"{weighted_reset_reentry_evidence_count:.2f} weighted reset re-entry run(s), "
        f"{decayed_confirmation_rate:.0%} confirmation-like signal, and {decayed_clearance_rate:.0%} clearance-like signal."
    )


def _recent_reset_reentry_signal_mix(
    weighted_reset_reentry_evidence_count: float,
    weighted_confirmation_like: float,
    weighted_clearance_like: float,
    recent_window_weight_share: float,
) -> str:
    return (
        f"{weighted_reset_reentry_evidence_count:.2f} weighted reset re-entry run(s) with "
        f"{weighted_confirmation_like:.2f} confirmation-like, {weighted_clearance_like:.2f} clearance-like, "
        f"and {recent_window_weight_share:.0%} of the signal from the freshest runs."
    )


def _closure_forecast_reset_reentry_freshness_for_target(
    target: dict,
    closure_forecast_events: list[dict],
) -> dict:
    class_key = _target_class_key(target)
    class_events = [event for event in closure_forecast_events if event.get("class_key") == class_key]
    relevant_events: list[dict] = []
    for event in class_events:
        if not _reset_reentry_event_has_evidence(event):
            continue
        relevant_events.append(event)
        if len(relevant_events) >= HISTORY_WINDOW_RUNS:
            break

    weighted_reset_reentry_evidence_count = 0.0
    weighted_confirmation_like = 0.0
    weighted_clearance_like = 0.0
    recent_reset_reentry_weight = 0.0
    recent_signals = [
        _reset_reentry_event_signal_label(event)
        for event in relevant_events[:CLASS_RESET_REENTRY_FRESHNESS_WINDOW_RUNS]
    ]
    current_side = _closure_forecast_reset_reentry_side_from_persistence_status(
        target.get("closure_forecast_reset_reentry_persistence_status", "none")
    )
    if current_side == "none":
        current_side = _closure_forecast_reset_reentry_side_from_status(
            target.get("closure_forecast_reset_reentry_status", "none")
        )

    for index, event in enumerate(relevant_events):
        weight = CLASS_MEMORY_RECENCY_WEIGHTS[min(index, HISTORY_WINDOW_RUNS - 1)]
        weighted_reset_reentry_evidence_count += weight
        event_side = _closure_forecast_reset_reentry_memory_side_from_event(event)
        if (
            index < CLASS_RESET_REENTRY_FRESHNESS_WINDOW_RUNS
            and event_side == current_side
        ):
            recent_reset_reentry_weight += weight
        if _reset_reentry_event_is_confirmation_like(event):
            weighted_confirmation_like += weight
        if _reset_reentry_event_is_clearance_like(event):
            weighted_clearance_like += weight

    recent_window_weight_share = recent_reset_reentry_weight / max(
        weighted_reset_reentry_evidence_count,
        1.0,
    )
    freshness_status = _closure_forecast_freshness_status(
        weighted_reset_reentry_evidence_count,
        recent_window_weight_share,
    )
    decayed_confirmation_rate = weighted_confirmation_like / max(
        weighted_reset_reentry_evidence_count,
        1.0,
    )
    decayed_clearance_rate = weighted_clearance_like / max(
        weighted_reset_reentry_evidence_count,
        1.0,
    )
    return {
        "closure_forecast_reset_reentry_freshness_status": freshness_status,
        "closure_forecast_reset_reentry_freshness_reason": _closure_forecast_reset_reentry_freshness_reason(
            freshness_status,
            weighted_reset_reentry_evidence_count,
            recent_window_weight_share,
            decayed_confirmation_rate,
            decayed_clearance_rate,
        ),
        "closure_forecast_reset_reentry_memory_weight": round(
            recent_window_weight_share,
            2,
        ),
        "decayed_reset_reentered_confirmation_rate": round(
            decayed_confirmation_rate,
            2,
        ),
        "decayed_reset_reentered_clearance_rate": round(
            decayed_clearance_rate,
            2,
        ),
        "recent_reset_reentry_signal_mix": _recent_reset_reentry_signal_mix(
            weighted_reset_reentry_evidence_count,
            weighted_confirmation_like,
            weighted_clearance_like,
            recent_window_weight_share,
        ),
        "recent_reset_reentry_signal_path": " -> ".join(recent_signals),
        "has_fresh_aligned_recent_evidence": any(
            _closure_forecast_reset_reentry_memory_side_from_event(event) == current_side
            and _reset_reentry_event_signal_label(event) != "neutral"
            and event.get("closure_forecast_reacquisition_freshness_status", "insufficient-data")
            == "fresh"
            for event in relevant_events[:2]
        ),
    }


def _apply_reset_reentry_freshness_reset_control(
    target: dict,
    *,
    freshness_meta: dict,
    transition_history_meta: dict,
    closure_likely_outcome: str,
    closure_hysteresis_status: str,
    closure_hysteresis_reason: str,
    transition_status: str,
    transition_reason: str,
    resolution_status: str,
    resolution_reason: str,
    reacquisition_status: str,
    reacquisition_reason: str,
    reentry_status: str,
    reentry_reason: str,
    persistence_age_runs: int,
    persistence_score: float,
    persistence_status: str,
    persistence_reason: str,
) -> dict:
    freshness_status = freshness_meta.get(
        "closure_forecast_reset_reentry_freshness_status",
        "insufficient-data",
    )
    decayed_clearance_rate = float(
        freshness_meta.get("decayed_reset_reentered_clearance_rate", 0.0) or 0.0
    )
    churn_status = target.get("closure_forecast_reset_reentry_churn_status", "none")
    current_side = _closure_forecast_reset_reentry_side_from_persistence_status(
        persistence_status
    )
    if current_side == "none":
        current_side = _closure_forecast_reset_reentry_side_from_status(reentry_status)
    local_noise = _target_specific_normalization_noise(target, transition_history_meta)
    recent_pending_status = transition_history_meta.get("recent_pending_status", "none")
    has_fresh_aligned_recent_evidence = freshness_meta.get(
        "has_fresh_aligned_recent_evidence",
        False,
    )

    def _restore_weaker_pending_posture(
        reset_reason: str,
    ) -> tuple[str, str, str, str]:
        restored_transition_status = transition_status
        restored_transition_reason = transition_reason
        restored_resolution_status = resolution_status
        restored_resolution_reason = resolution_reason
        if (
            resolution_status == "cleared"
            and recent_pending_status in {"pending-support", "pending-caution"}
        ):
            restored_transition_status = recent_pending_status
            restored_transition_reason = reset_reason
            restored_resolution_status = "none"
            restored_resolution_reason = ""
        return (
            restored_transition_status,
            restored_transition_reason,
            restored_resolution_status,
            restored_resolution_reason,
        )

    if local_noise and current_side != "none":
        blocked_reason = "Local target instability still overrides healthy reset re-entry freshness."
        if closure_likely_outcome == "confirm-soon":
            closure_likely_outcome = "hold"
        elif closure_likely_outcome == "expire-risk":
            closure_likely_outcome = "clear-risk"
        if closure_hysteresis_status == "confirmed-confirmation":
            closure_hysteresis_status = "pending-confirmation"
        elif closure_hysteresis_status == "confirmed-clearance":
            closure_hysteresis_status = "pending-clearance"
        closure_hysteresis_reason = blocked_reason
        return {
            "closure_forecast_reset_reentry_reset_status": "blocked",
            "closure_forecast_reset_reentry_reset_reason": blocked_reason,
            "transition_closure_likely_outcome": closure_likely_outcome,
            "closure_forecast_hysteresis_status": closure_hysteresis_status,
            "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reacquisition_status": reacquisition_status,
            "closure_forecast_reacquisition_reason": reacquisition_reason,
            "closure_forecast_reset_reentry_status": reentry_status,
            "closure_forecast_reset_reentry_reason": reentry_reason,
            "closure_forecast_reset_reentry_age_runs": persistence_age_runs,
            "closure_forecast_reset_reentry_persistence_score": persistence_score,
            "closure_forecast_reset_reentry_persistence_status": persistence_status,
            "closure_forecast_reset_reentry_persistence_reason": persistence_reason,
        }

    if current_side == "confirmation" and freshness_status == "mixed-age":
        if persistence_status == "sustained-confirmation-reentry" and (
            churn_status != "churn" or has_fresh_aligned_recent_evidence
        ):
            softened_reason = (
                "Restored confirmation-side reset re-entry posture is still visible, but it is aging and has been stepped down from sustained strength."
            )
            softened_outcome = closure_likely_outcome
            if softened_outcome == "hold" and reentry_status in {
                "pending-confirmation-reentry",
                "reentered-confirmation",
            }:
                softened_outcome = "confirm-soon"
            return {
                "closure_forecast_reset_reentry_reset_status": "confirmation-softened",
                "closure_forecast_reset_reentry_reset_reason": softened_reason,
                "transition_closure_likely_outcome": softened_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": softened_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reacquisition_status": reacquisition_status,
                "closure_forecast_reacquisition_reason": reacquisition_reason,
                "closure_forecast_reset_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_age_runs": persistence_age_runs,
                "closure_forecast_reset_reentry_persistence_score": persistence_score,
                "closure_forecast_reset_reentry_persistence_status": "holding-confirmation-reentry",
                "closure_forecast_reset_reentry_persistence_reason": softened_reason,
            }
        if persistence_status == "holding-confirmation-reentry" and churn_status == "churn":
            freshness_status = "stale"

    if current_side == "clearance" and freshness_status == "mixed-age":
        if persistence_status == "sustained-clearance-reentry" and (
            churn_status != "churn" or has_fresh_aligned_recent_evidence
        ):
            softened_reason = (
                "Restored clearance-side reset re-entry posture is still visible, but it is aging and has been stepped down from sustained strength."
            )
            return {
                "closure_forecast_reset_reentry_reset_status": "clearance-softened",
                "closure_forecast_reset_reentry_reset_reason": softened_reason,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": softened_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reacquisition_status": reacquisition_status,
                "closure_forecast_reacquisition_reason": reacquisition_reason,
                "closure_forecast_reset_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_age_runs": persistence_age_runs,
                "closure_forecast_reset_reentry_persistence_score": persistence_score,
                "closure_forecast_reset_reentry_persistence_status": "holding-clearance-reentry",
                "closure_forecast_reset_reentry_persistence_reason": softened_reason,
            }
        if persistence_status == "holding-clearance-reentry" and churn_status == "churn":
            freshness_status = "stale"

    needs_reset = (
        current_side in {"confirmation", "clearance"}
        and persistence_status
        in {
            "holding-confirmation-reentry",
            "holding-clearance-reentry",
            "sustained-confirmation-reentry",
            "sustained-clearance-reentry",
        }
        and (
            freshness_status in {"stale", "insufficient-data"}
            or not has_fresh_aligned_recent_evidence
            or (
                freshness_status == "mixed-age"
                and churn_status == "churn"
                and not has_fresh_aligned_recent_evidence
            )
        )
    )

    if needs_reset:
        if current_side == "confirmation":
            reset_reason = (
                "Restored confirmation-side reset re-entry posture has aged out enough that the stronger carry-forward has been withdrawn."
            )
            closure_likely_outcome = "hold"
            if closure_hysteresis_status == "confirmed-confirmation":
                closure_hysteresis_status = "pending-confirmation"
            closure_hysteresis_reason = reset_reason
            return {
                "closure_forecast_reset_reentry_reset_status": "confirmation-reset",
                "closure_forecast_reset_reentry_reset_reason": reset_reason,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reacquisition_status": "none",
                "closure_forecast_reacquisition_reason": reset_reason,
                "closure_forecast_reset_reentry_status": "none",
                "closure_forecast_reset_reentry_reason": reset_reason,
                "closure_forecast_reset_reentry_age_runs": 0,
                "closure_forecast_reset_reentry_persistence_score": 0.0,
                "closure_forecast_reset_reentry_persistence_status": "none",
                "closure_forecast_reset_reentry_persistence_reason": "",
            }

        reset_reason = (
            "Restored clearance-side reset re-entry posture has aged out enough that the stronger carry-forward has been withdrawn."
        )
        if closure_likely_outcome == "expire-risk":
            closure_likely_outcome = "clear-risk"
        elif closure_likely_outcome == "clear-risk":
            closure_likely_outcome = "hold"
        if closure_hysteresis_status == "confirmed-clearance":
            closure_hysteresis_status = "pending-clearance"
        closure_hysteresis_reason = reset_reason
        (
            transition_status,
            transition_reason,
            resolution_status,
            resolution_reason,
        ) = _restore_weaker_pending_posture(reset_reason)
        return {
            "closure_forecast_reset_reentry_reset_status": "clearance-reset",
            "closure_forecast_reset_reentry_reset_reason": reset_reason,
            "transition_closure_likely_outcome": closure_likely_outcome,
            "closure_forecast_hysteresis_status": closure_hysteresis_status,
            "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reacquisition_status": "none",
            "closure_forecast_reacquisition_reason": reset_reason,
            "closure_forecast_reset_reentry_status": "none",
            "closure_forecast_reset_reentry_reason": reset_reason,
            "closure_forecast_reset_reentry_age_runs": 0,
            "closure_forecast_reset_reentry_persistence_score": 0.0,
            "closure_forecast_reset_reentry_persistence_status": "none",
            "closure_forecast_reset_reentry_persistence_reason": "",
        }

    if (
        current_side == "clearance"
        and resolution_status == "cleared"
        and recent_pending_status in {"pending-support", "pending-caution"}
        and (
            freshness_status not in {"fresh", "mixed-age"}
            or decayed_clearance_rate < 0.50
            or persistence_status
            not in {
                "holding-clearance-reentry",
                "sustained-clearance-reentry",
            }
            or churn_status == "churn"
        )
    ):
        reset_reason = (
            "Restored clearance-side reset re-entry posture has aged out enough that the stronger carry-forward has been withdrawn."
        )
        (
            transition_status,
            transition_reason,
            resolution_status,
            resolution_reason,
        ) = _restore_weaker_pending_posture(reset_reason)
        return {
            "closure_forecast_reset_reentry_reset_status": "clearance-reset",
            "closure_forecast_reset_reentry_reset_reason": reset_reason,
            "transition_closure_likely_outcome": "hold",
            "closure_forecast_hysteresis_status": "pending-clearance",
            "closure_forecast_hysteresis_reason": reset_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reacquisition_status": "none",
            "closure_forecast_reacquisition_reason": reset_reason,
            "closure_forecast_reset_reentry_status": "none",
            "closure_forecast_reset_reentry_reason": reset_reason,
            "closure_forecast_reset_reentry_age_runs": 0,
            "closure_forecast_reset_reentry_persistence_score": 0.0,
            "closure_forecast_reset_reentry_persistence_status": "none",
            "closure_forecast_reset_reentry_persistence_reason": "",
        }

    return {
        "closure_forecast_reset_reentry_reset_status": "none",
        "closure_forecast_reset_reentry_reset_reason": "",
        "transition_closure_likely_outcome": closure_likely_outcome,
        "closure_forecast_hysteresis_status": closure_hysteresis_status,
        "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
        "class_reweight_transition_status": transition_status,
        "class_reweight_transition_reason": transition_reason,
        "class_transition_resolution_status": resolution_status,
        "class_transition_resolution_reason": resolution_reason,
        "closure_forecast_reacquisition_status": reacquisition_status,
        "closure_forecast_reacquisition_reason": reacquisition_reason,
        "closure_forecast_reset_reentry_status": reentry_status,
        "closure_forecast_reset_reentry_reason": reentry_reason,
        "closure_forecast_reset_reentry_age_runs": persistence_age_runs,
        "closure_forecast_reset_reentry_persistence_score": persistence_score,
        "closure_forecast_reset_reentry_persistence_status": persistence_status,
        "closure_forecast_reset_reentry_persistence_reason": persistence_reason,
    }


def _closure_forecast_reset_reentry_freshness_hotspots(
    resolution_targets: list[dict],
    *,
    mode: str,
) -> list[dict]:
    grouped: dict[str, dict] = {}
    for target in resolution_targets:
        class_key = _target_class_key(target)
        if not class_key:
            continue
        current = {
            "scope": "class",
            "label": class_key,
            "closure_forecast_reset_reentry_freshness_status": target.get(
                "closure_forecast_reset_reentry_freshness_status",
                "insufficient-data",
            ),
            "decayed_reset_reentered_confirmation_rate": target.get(
                "decayed_reset_reentered_confirmation_rate",
                0.0,
            ),
            "decayed_reset_reentered_clearance_rate": target.get(
                "decayed_reset_reentered_clearance_rate",
                0.0,
            ),
            "recent_reset_reentry_signal_mix": target.get(
                "recent_reset_reentry_signal_mix",
                "",
            ),
            "recent_reset_reentry_persistence_path": target.get(
                "recent_reset_reentry_persistence_path",
                "",
            ),
            "dominant_count": max(
                target.get("decayed_reset_reentered_confirmation_rate", 0.0),
                target.get("decayed_reset_reentered_clearance_rate", 0.0),
            ),
            "reset_reentry_event_count": len(
                [
                    part
                    for part in (
                        target.get("recent_reset_reentry_persistence_path", "") or ""
                    ).split(" -> ")
                    if part
                ]
            ),
        }
        existing = grouped.get(class_key)
        if existing is None or current["dominant_count"] > existing["dominant_count"]:
            grouped[class_key] = current

    hotspots = list(grouped.values())
    if mode == "fresh":
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reset_reentry_freshness_status") == "fresh"
            and item.get("dominant_count", 0.0) > 0.0
        ]
    else:
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reset_reentry_freshness_status") == "stale"
            and item.get("dominant_count", 0.0) > 0.0
        ]
    hotspots.sort(
        key=lambda item: (
            -item.get("dominant_count", 0.0),
            -item.get("reset_reentry_event_count", 0),
            item.get("label", ""),
        )
    )
    return hotspots[:5]


def _closure_forecast_reset_reentry_freshness_summary(
    primary_target: dict,
    stale_reset_reentry_hotspots: list[dict],
    fresh_reset_reentry_signal_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    freshness_status = primary_target.get(
        "closure_forecast_reset_reentry_freshness_status",
        "insufficient-data",
    )
    if freshness_status == "fresh":
        return f"{label} still has recent reset re-entry evidence that is current enough to keep the restored posture trusted."
    if freshness_status == "mixed-age":
        return f"{label} still has useful reset re-entry memory, but the restored posture is no longer getting fully fresh reinforcement."
    if freshness_status == "stale":
        return f"{label} is leaning on older reset re-entry strength more than fresh runs, so stronger restored posture should not keep carrying forward on memory alone."
    if fresh_reset_reentry_signal_hotspots:
        hotspot = fresh_reset_reentry_signal_hotspots[0]
        return (
            f"Fresh reset re-entry evidence is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes can keep restored posture more safely than older carry-forward."
        )
    if stale_reset_reentry_hotspots:
        hotspot = stale_reset_reentry_hotspots[0]
        return (
            f"Older reset re-entry strength is lingering most around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes should keep resetting restored posture when fresh follow-through stops."
        )
    return "Reset re-entry memory is still too lightly exercised to say whether restored posture is being reinforced by fresh evidence or older carry-forward."


def _closure_forecast_reset_reentry_reset_summary(
    primary_target: dict,
    stale_reset_reentry_hotspots: list[dict],
    fresh_reset_reentry_signal_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    reset_status = primary_target.get("closure_forecast_reset_reentry_reset_status", "none")
    freshness_status = primary_target.get(
        "closure_forecast_reset_reentry_freshness_status",
        "insufficient-data",
    )
    confirmation_rate = primary_target.get(
        "decayed_reset_reentered_confirmation_rate",
        0.0,
    )
    clearance_rate = primary_target.get(
        "decayed_reset_reentered_clearance_rate",
        0.0,
    )
    if reset_status == "confirmation-softened":
        return f"Restored confirmation-side reset re-entry posture for {label} is still visible, but it is aging and has been stepped down from sustained strength."
    if reset_status == "clearance-softened":
        return f"Restored clearance-side reset re-entry posture for {label} is still visible, but it is aging and has been stepped down from sustained strength."
    if reset_status == "confirmation-reset":
        return f"Restored confirmation-side reset re-entry posture for {label} has aged out enough that the stronger carry-forward has been withdrawn."
    if reset_status == "clearance-reset":
        return f"Restored clearance-side reset re-entry posture for {label} has aged out enough that the stronger carry-forward has been withdrawn."
    if reset_status == "blocked":
        return primary_target.get(
            "closure_forecast_reset_reentry_reset_reason",
            f"Local target instability still overrides healthy reset re-entry freshness for {label}.",
        )
    if freshness_status == "fresh" and confirmation_rate >= clearance_rate:
        return f"Fresh reset re-entry evidence for {label} is still reinforcing confirmation-side restored posture more than clearance pressure."
    if freshness_status == "fresh":
        return f"Fresh reset re-entry evidence for {label} is still reinforcing clearance-side restored posture more than confirmation-side carry-forward."
    if freshness_status == "mixed-age":
        return f"Reset re-entry posture for {label} is aging enough that it can keep holding, but it should no longer stay indefinitely at sustained strength."
    if stale_reset_reentry_hotspots:
        hotspot = stale_reset_reentry_hotspots[0]
        return (
            f"Reset re-entry posture is aging out fastest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes should reset restored carry-forward instead of relying on older follow-through."
        )
    if fresh_reset_reentry_signal_hotspots:
        hotspot = fresh_reset_reentry_signal_hotspots[0]
        return (
            f"Fresh reset re-entry follow-through is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes can preserve restored posture longer than aging carry-forward elsewhere."
        )
    return "No reset re-entry reset is changing the current restored closure-forecast posture right now."


def _apply_reset_reentry_freshness_and_reset(
    resolution_targets: list[dict],
    history: list[dict],
    *,
    current_generated_at: str,
    confidence_calibration: dict,
) -> dict:
    if not resolution_targets:
        return {
            "primary_target_closure_forecast_reset_reentry_freshness_status": "insufficient-data",
            "primary_target_closure_forecast_reset_reentry_freshness_reason": "",
            "closure_forecast_reset_reentry_freshness_summary": "No reset re-entry freshness is recorded because there is no active target.",
            "primary_target_closure_forecast_reset_reentry_reset_status": "none",
            "primary_target_closure_forecast_reset_reentry_reset_reason": "",
            "closure_forecast_reset_reentry_reset_summary": "No reset re-entry reset is recorded because there is no active target.",
            "stale_reset_reentry_hotspots": [],
            "fresh_reset_reentry_signal_hotspots": [],
            "closure_forecast_reset_reentry_decay_window_runs": CLASS_RESET_REENTRY_FRESHNESS_WINDOW_RUNS,
        }

    current_primary_target = resolution_targets[0]
    current_bucket = _recommendation_bucket(current_primary_target)
    closure_forecast_events = _class_closure_forecast_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )
    transition_events = _class_transition_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )

    updated_targets: list[dict] = []
    for target in resolution_targets:
        freshness_status = "insufficient-data"
        freshness_reason = ""
        memory_weight = 0.0
        decayed_confirmation_rate = 0.0
        decayed_clearance_rate = 0.0
        signal_mix = ""
        reset_status = "none"
        reset_reason = ""
        closure_likely_outcome = target.get("transition_closure_likely_outcome", "none")
        closure_hysteresis_status = target.get("closure_forecast_hysteresis_status", "none")
        closure_hysteresis_reason = target.get("closure_forecast_hysteresis_reason", "")
        transition_status = target.get("class_reweight_transition_status", "none")
        transition_reason = target.get("class_reweight_transition_reason", "")
        resolution_status = target.get("class_transition_resolution_status", "none")
        resolution_reason = target.get("class_transition_resolution_reason", "")
        reacquisition_status = target.get("closure_forecast_reacquisition_status", "none")
        reacquisition_reason = target.get("closure_forecast_reacquisition_reason", "")
        reentry_status = target.get("closure_forecast_reset_reentry_status", "none")
        reentry_reason = target.get("closure_forecast_reset_reentry_reason", "")
        persistence_age_runs = target.get("closure_forecast_reset_reentry_age_runs", 0)
        persistence_score = target.get("closure_forecast_reset_reentry_persistence_score", 0.0)
        persistence_status = target.get("closure_forecast_reset_reentry_persistence_status", "none")
        persistence_reason = target.get("closure_forecast_reset_reentry_persistence_reason", "")

        if _recommendation_bucket(target) == current_bucket:
            transition_history_meta = _target_class_transition_history(target, transition_events)
            freshness_meta = _closure_forecast_reset_reentry_freshness_for_target(
                target,
                closure_forecast_events,
            )
            freshness_status = freshness_meta["closure_forecast_reset_reentry_freshness_status"]
            freshness_reason = freshness_meta["closure_forecast_reset_reentry_freshness_reason"]
            memory_weight = freshness_meta["closure_forecast_reset_reentry_memory_weight"]
            decayed_confirmation_rate = freshness_meta["decayed_reset_reentered_confirmation_rate"]
            decayed_clearance_rate = freshness_meta["decayed_reset_reentered_clearance_rate"]
            signal_mix = freshness_meta["recent_reset_reentry_signal_mix"]
            control_updates = _apply_reset_reentry_freshness_reset_control(
                target,
                freshness_meta=freshness_meta,
                transition_history_meta=transition_history_meta,
                closure_likely_outcome=closure_likely_outcome,
                closure_hysteresis_status=closure_hysteresis_status,
                closure_hysteresis_reason=closure_hysteresis_reason,
                transition_status=transition_status,
                transition_reason=transition_reason,
                resolution_status=resolution_status,
                resolution_reason=resolution_reason,
                reacquisition_status=reacquisition_status,
                reacquisition_reason=reacquisition_reason,
                reentry_status=reentry_status,
                reentry_reason=reentry_reason,
                persistence_age_runs=persistence_age_runs,
                persistence_score=persistence_score,
                persistence_status=persistence_status,
                persistence_reason=persistence_reason,
            )
            reset_status = control_updates["closure_forecast_reset_reentry_reset_status"]
            reset_reason = control_updates["closure_forecast_reset_reentry_reset_reason"]
            closure_likely_outcome = control_updates["transition_closure_likely_outcome"]
            closure_hysteresis_status = control_updates["closure_forecast_hysteresis_status"]
            closure_hysteresis_reason = control_updates["closure_forecast_hysteresis_reason"]
            transition_status = control_updates["class_reweight_transition_status"]
            transition_reason = control_updates["class_reweight_transition_reason"]
            resolution_status = control_updates["class_transition_resolution_status"]
            resolution_reason = control_updates["class_transition_resolution_reason"]
            reacquisition_status = control_updates["closure_forecast_reacquisition_status"]
            reacquisition_reason = control_updates["closure_forecast_reacquisition_reason"]
            reentry_status = control_updates["closure_forecast_reset_reentry_status"]
            reentry_reason = control_updates["closure_forecast_reset_reentry_reason"]
            persistence_age_runs = control_updates["closure_forecast_reset_reentry_age_runs"]
            persistence_score = control_updates["closure_forecast_reset_reentry_persistence_score"]
            persistence_status = control_updates["closure_forecast_reset_reentry_persistence_status"]
            persistence_reason = control_updates["closure_forecast_reset_reentry_persistence_reason"]

        updated_targets.append(
            {
                **target,
                "closure_forecast_reset_reentry_freshness_status": freshness_status,
                "closure_forecast_reset_reentry_freshness_reason": freshness_reason,
                "closure_forecast_reset_reentry_memory_weight": memory_weight,
                "decayed_reset_reentered_confirmation_rate": decayed_confirmation_rate,
                "decayed_reset_reentered_clearance_rate": decayed_clearance_rate,
                "recent_reset_reentry_signal_mix": signal_mix,
                "closure_forecast_reset_reentry_reset_status": reset_status,
                "closure_forecast_reset_reentry_reset_reason": reset_reason,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reacquisition_status": reacquisition_status,
                "closure_forecast_reacquisition_reason": reacquisition_reason,
                "closure_forecast_reset_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_age_runs": persistence_age_runs,
                "closure_forecast_reset_reentry_persistence_score": persistence_score,
                "closure_forecast_reset_reentry_persistence_status": persistence_status,
                "closure_forecast_reset_reentry_persistence_reason": persistence_reason,
            }
        )

    resolution_targets[:] = updated_targets
    primary_target = resolution_targets[0]
    stale_reset_reentry_hotspots = _closure_forecast_reset_reentry_freshness_hotspots(
        resolution_targets,
        mode="stale",
    )
    fresh_reset_reentry_signal_hotspots = _closure_forecast_reset_reentry_freshness_hotspots(
        resolution_targets,
        mode="fresh",
    )
    return {
        "primary_target_closure_forecast_reset_reentry_freshness_status": primary_target.get(
            "closure_forecast_reset_reentry_freshness_status",
            "insufficient-data",
        ),
        "primary_target_closure_forecast_reset_reentry_freshness_reason": primary_target.get(
            "closure_forecast_reset_reentry_freshness_reason",
            "",
        ),
        "closure_forecast_reset_reentry_freshness_summary": _closure_forecast_reset_reentry_freshness_summary(
            primary_target,
            stale_reset_reentry_hotspots,
            fresh_reset_reentry_signal_hotspots,
        ),
        "primary_target_closure_forecast_reset_reentry_reset_status": primary_target.get(
            "closure_forecast_reset_reentry_reset_status",
            "none",
        ),
        "primary_target_closure_forecast_reset_reentry_reset_reason": primary_target.get(
            "closure_forecast_reset_reentry_reset_reason",
            "",
        ),
        "closure_forecast_reset_reentry_reset_summary": _closure_forecast_reset_reentry_reset_summary(
            primary_target,
            stale_reset_reentry_hotspots,
            fresh_reset_reentry_signal_hotspots,
        ),
        "stale_reset_reentry_hotspots": stale_reset_reentry_hotspots,
        "fresh_reset_reentry_signal_hotspots": fresh_reset_reentry_signal_hotspots,
        "closure_forecast_reset_reentry_decay_window_runs": CLASS_RESET_REENTRY_FRESHNESS_WINDOW_RUNS,
    }


def _closure_forecast_reset_reentry_rebuild_side_from_status(status: str) -> str:
    if status in {"pending-confirmation-rebuild", "rebuilt-confirmation-reentry"}:
        return "confirmation"
    if status in {"pending-clearance-rebuild", "rebuilt-clearance-reentry"}:
        return "clearance"
    return "none"


def _closure_forecast_reset_reentry_rebuild_side_from_recovery_status(status: str) -> str:
    if status in {
        "recovering-confirmation-reentry-reset",
        "rebuilding-confirmation-reentry",
    }:
        return "confirmation"
    if status in {
        "recovering-clearance-reentry-reset",
        "rebuilding-clearance-reentry",
    }:
        return "clearance"
    return "none"


def _closure_forecast_reset_reentry_refresh_path_label(event: dict) -> str:
    rebuild_status = event.get("closure_forecast_reset_reentry_rebuild_status", "none") or "none"
    if rebuild_status != "none":
        return rebuild_status
    recovery_status = (
        event.get("closure_forecast_reset_reentry_refresh_recovery_status", "none") or "none"
    )
    if recovery_status != "none":
        return recovery_status
    reset_status = event.get("closure_forecast_reset_reentry_reset_status", "none") or "none"
    if reset_status != "none":
        return reset_status
    reentry_status = event.get("closure_forecast_reset_reentry_status", "none") or "none"
    if reentry_status != "none":
        return reentry_status
    likely_outcome = event.get("transition_closure_likely_outcome", "none") or "none"
    if likely_outcome != "none":
        return likely_outcome
    return "hold"


def _closure_forecast_reset_reentry_refresh_recovery_for_target(
    target: dict,
    closure_forecast_events: list[dict],
    transition_history_meta: dict,
) -> dict:
    matching_events = _ordered_reset_reentry_events_for_target(
        target,
        closure_forecast_events,
    )[:CLASS_RESET_REENTRY_REFRESH_REBUILD_WINDOW_RUNS]
    recent_reset_reentry_side = "none"
    latest_reset_index: int | None = None
    for index, event in enumerate(matching_events):
        event_reset_side = _closure_forecast_reset_side_from_status(
            event.get("closure_forecast_reset_reentry_reset_status", "none")
        )
        if event_reset_side != "none":
            recent_reset_reentry_side = event_reset_side
            latest_reset_index = index
            break

    relevant_events: list[dict] = []
    directions: list[str] = []
    weighted_total = 0.0
    weight_sum = 0.0
    for event in matching_events:
        score = float(event.get("closure_forecast_reweight_score", 0.0) or 0.0)
        direction = _normalized_closure_forecast_direction(
            event.get("closure_forecast_reweight_direction", "neutral"),
            score,
        )
        if (
            _closure_forecast_reset_side_from_status(
                event.get("closure_forecast_reset_reentry_reset_status", "none")
            )
            == "none"
            and direction == "neutral"
            and abs(score) < 0.05
        ):
            continue
        relevant_events.append(event)
        directions.append(direction)
        if len(relevant_events) > CLASS_RESET_REENTRY_REFRESH_REBUILD_WINDOW_RUNS:
            break
        if direction == "neutral":
            signal_strength = 0.0
            sign = 0.0
        else:
            signal_strength = max(abs(score), 0.05)
            sign = 1.0 if direction == "supporting-confirmation" else -1.0
        freshness_factor = {
            "fresh": 1.00,
            "mixed-age": 0.60,
            "stale": 0.25,
            "insufficient-data": 0.10,
        }.get(
            event.get("closure_forecast_reset_reentry_freshness_status", "insufficient-data"),
            0.10,
        )
        weight = (1.0, 0.8, 0.6, 0.4)[
            min(
                len(relevant_events) - 1,
                CLASS_RESET_REENTRY_REFRESH_REBUILD_WINDOW_RUNS - 1,
            )
        ]
        weighted_total += sign * signal_strength * freshness_factor * weight
        weight_sum += weight

    recovery_score = _clamp_round(
        weighted_total / max(weight_sum, 1.0),
        lower=-0.95,
        upper=0.95,
    )
    current_score = float(target.get("closure_forecast_reweight_score", 0.0) or 0.0)
    current_direction = _normalized_closure_forecast_direction(
        target.get("closure_forecast_reweight_direction", "neutral"),
        current_score,
    )
    current_freshness = target.get(
        "closure_forecast_reset_reentry_freshness_status",
        "insufficient-data",
    )
    current_momentum = target.get("closure_forecast_momentum_status", "insufficient-data")
    current_stability = target.get("closure_forecast_stability_status", "watch")
    earlier_majority = _closure_forecast_direction_majority(directions[1:])
    local_noise = _target_specific_normalization_noise(target, transition_history_meta)
    direction_reversing = _closure_forecast_direction_reversing(
        current_direction,
        earlier_majority,
    )
    opposes_reset = (
        (
            recent_reset_reentry_side == "confirmation"
            and current_direction == "supporting-clearance"
        )
        or (
            recent_reset_reentry_side == "clearance"
            and current_direction == "supporting-confirmation"
        )
    )
    aligned_fresh_runs_after_reset = 0
    if latest_reset_index is not None and latest_reset_index > 0:
        for event in matching_events[:latest_reset_index]:
            score = float(event.get("closure_forecast_reweight_score", 0.0) or 0.0)
            direction = _normalized_closure_forecast_direction(
                event.get("closure_forecast_reweight_direction", "neutral"),
                score,
            )
            event_side = (
                "confirmation"
                if direction == "supporting-confirmation"
                else "clearance"
                if direction == "supporting-clearance"
                else "none"
            )
            if (
                event_side == recent_reset_reentry_side
                and event.get(
                    "closure_forecast_reset_reentry_freshness_status",
                    "insufficient-data",
                )
                == "fresh"
            ):
                aligned_fresh_runs_after_reset += 1
    current_side = (
        "confirmation"
        if current_direction == "supporting-confirmation"
        else "clearance"
        if current_direction == "supporting-clearance"
        else "none"
    )
    current_event_already_counted = any(
        event.get("generated_at", "") == ""
        and float(event.get("closure_forecast_reweight_score", 0.0) or 0.0)
        == current_score
        and event.get("closure_forecast_reweight_direction", "neutral")
        == target.get("closure_forecast_reweight_direction", "neutral")
        for event in matching_events[: latest_reset_index or 0]
    )
    if (
        current_side == recent_reset_reentry_side
        and current_freshness == "fresh"
        and not current_event_already_counted
    ):
        aligned_fresh_runs_after_reset += 1

    if len(relevant_events) < 2 or recent_reset_reentry_side == "none":
        recovery_status = "none"
    elif local_noise and current_direction == "supporting-confirmation":
        recovery_status = "blocked"
    elif opposes_reset or direction_reversing:
        recovery_status = "reversing"
    elif (
        recent_reset_reentry_side == "confirmation"
        and current_direction == "supporting-confirmation"
        and current_freshness == "fresh"
        and recovery_score >= 0.25
        and current_stability != "oscillating"
    ):
        recovery_status = "rebuilding-confirmation-reentry"
    elif (
        recent_reset_reentry_side == "clearance"
        and current_direction == "supporting-clearance"
        and current_freshness == "fresh"
        and recovery_score <= -0.25
        and current_stability != "oscillating"
    ):
        recovery_status = "rebuilding-clearance-reentry"
    elif (
        recent_reset_reentry_side == "confirmation"
        and current_direction == "supporting-confirmation"
        and current_freshness in {"fresh", "mixed-age"}
        and recovery_score >= 0.15
    ):
        recovery_status = "recovering-confirmation-reentry-reset"
    elif (
        recent_reset_reentry_side == "clearance"
        and current_direction == "supporting-clearance"
        and current_freshness in {"fresh", "mixed-age"}
        and recovery_score <= -0.15
    ):
        recovery_status = "recovering-clearance-reentry-reset"
    else:
        recovery_status = "none"

    if (
        recovery_status == "rebuilding-confirmation-reentry"
        and current_freshness == "fresh"
        and current_momentum == "sustained-confirmation"
        and current_stability == "stable"
        and not local_noise
        and aligned_fresh_runs_after_reset >= 2
    ):
        rebuild_status = "rebuilt-confirmation-reentry"
        rebuild_reason = (
            "Fresh confirmation-side follow-through has rebuilt stronger confirmation-side reset re-entry."
        )
    elif (
        recovery_status == "rebuilding-clearance-reentry"
        and current_freshness == "fresh"
        and current_momentum == "sustained-clearance"
        and current_stability == "stable"
        and aligned_fresh_runs_after_reset >= 2
    ):
        rebuild_status = "rebuilt-clearance-reentry"
        rebuild_reason = (
            "Fresh clearance-side pressure has rebuilt stronger clearance-side reset re-entry."
        )
    elif local_noise and recovery_status in {
        "recovering-confirmation-reentry-reset",
        "rebuilding-confirmation-reentry",
        "blocked",
    }:
        rebuild_status = "blocked"
        rebuild_reason = (
            "Local target instability is still preventing positive confirmation-side reset re-entry rebuild."
        )
    elif recovery_status in {
        "recovering-confirmation-reentry-reset",
        "rebuilding-confirmation-reentry",
    }:
        rebuild_status = "pending-confirmation-rebuild"
        rebuild_reason = (
            "Fresh confirmation-side evidence is returning after reset re-entry was softened or reset, but it has not yet rebuilt stronger reset re-entry."
        )
    elif recovery_status in {
        "recovering-clearance-reentry-reset",
        "rebuilding-clearance-reentry",
    }:
        rebuild_status = "pending-clearance-rebuild"
        rebuild_reason = (
            "Fresh clearance-side evidence is returning after reset re-entry was softened or reset, but it has not yet rebuilt stronger reset re-entry."
        )
    else:
        rebuild_status = "none"
        rebuild_reason = ""

    return {
        "closure_forecast_reset_reentry_refresh_recovery_score": recovery_score,
        "closure_forecast_reset_reentry_refresh_recovery_status": recovery_status,
        "closure_forecast_reset_reentry_rebuild_status": rebuild_status,
        "closure_forecast_reset_reentry_rebuild_reason": rebuild_reason,
        "recent_reset_reentry_refresh_path": " -> ".join(
            _closure_forecast_reset_reentry_refresh_path_label(event)
            for event in matching_events
            if event
        ),
        "recent_reset_reentry_side": recent_reset_reentry_side,
        "aligned_fresh_runs_after_latest_reset_reentry_reset": aligned_fresh_runs_after_reset,
    }


def _apply_reset_reentry_refresh_rebuild_control(
    target: dict,
    *,
    refresh_meta: dict,
    transition_history_meta: dict,
    closure_likely_outcome: str,
    closure_hysteresis_status: str,
    closure_hysteresis_reason: str,
    transition_status: str,
    transition_reason: str,
    resolution_status: str,
    resolution_reason: str,
    reacquisition_status: str,
    reacquisition_reason: str,
    reentry_status: str,
    reentry_reason: str,
    persistence_age_runs: int,
    persistence_score: float,
    persistence_status: str,
    persistence_reason: str,
) -> dict:
    recovery_status = refresh_meta.get(
        "closure_forecast_reset_reentry_refresh_recovery_status",
        "none",
    )
    rebuild_status = refresh_meta.get("closure_forecast_reset_reentry_rebuild_status", "none")
    rebuild_reason = refresh_meta.get("closure_forecast_reset_reentry_rebuild_reason", "")
    recent_reset_reentry_side = refresh_meta.get("recent_reset_reentry_side", "none")
    current_freshness = target.get(
        "closure_forecast_reset_reentry_freshness_status",
        "insufficient-data",
    )
    current_stability = target.get("closure_forecast_stability_status", "watch")
    transition_age_runs = int(target.get("class_transition_age_runs", 0) or 0)
    recent_pending_status = transition_history_meta.get("recent_pending_status", "none")
    decayed_clearance_rate = float(
        target.get("decayed_reset_reentered_clearance_rate", 0.0) or 0.0
    )

    if rebuild_status == "blocked":
        if recent_reset_reentry_side == "confirmation":
            closure_likely_outcome = "hold"
            closure_hysteresis_status = "pending-confirmation"
            closure_hysteresis_reason = rebuild_reason
            if reacquisition_status == "reacquired-confirmation":
                reacquisition_status = "pending-confirmation-reacquisition"
                reacquisition_reason = rebuild_reason
        return {
            "transition_closure_likely_outcome": closure_likely_outcome,
            "closure_forecast_hysteresis_status": closure_hysteresis_status,
            "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reacquisition_status": reacquisition_status,
            "closure_forecast_reacquisition_reason": reacquisition_reason,
            "closure_forecast_reset_reentry_status": reentry_status,
            "closure_forecast_reset_reentry_reason": reentry_reason,
            "closure_forecast_reset_reentry_age_runs": persistence_age_runs,
            "closure_forecast_reset_reentry_persistence_score": persistence_score,
            "closure_forecast_reset_reentry_persistence_status": persistence_status,
            "closure_forecast_reset_reentry_persistence_reason": persistence_reason,
        }

    if rebuild_status == "rebuilt-confirmation-reentry":
        return {
            "transition_closure_likely_outcome": "confirm-soon",
            "closure_forecast_hysteresis_status": "confirmed-confirmation",
            "closure_forecast_hysteresis_reason": rebuild_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reacquisition_status": "reacquired-confirmation",
            "closure_forecast_reacquisition_reason": rebuild_reason,
            "closure_forecast_reset_reentry_status": "reentered-confirmation",
            "closure_forecast_reset_reentry_reason": rebuild_reason,
            "closure_forecast_reset_reentry_age_runs": 0,
            "closure_forecast_reset_reentry_persistence_score": 0.0,
            "closure_forecast_reset_reentry_persistence_status": "none",
            "closure_forecast_reset_reentry_persistence_reason": "",
        }

    if rebuild_status == "rebuilt-clearance-reentry":
        restored_outcome = closure_likely_outcome
        if restored_outcome == "hold":
            restored_outcome = "clear-risk"
        elif restored_outcome == "clear-risk" and transition_age_runs >= 3:
            restored_outcome = "expire-risk"
        if (
            resolution_status == "none"
            and recent_pending_status in {"pending-support", "pending-caution"}
            and decayed_clearance_rate >= 0.50
            and current_stability != "oscillating"
        ):
            transition_status = "none"
            transition_reason = ""
            resolution_status = "cleared"
            resolution_reason = rebuild_reason
        return {
            "transition_closure_likely_outcome": restored_outcome,
            "closure_forecast_hysteresis_status": "confirmed-clearance",
            "closure_forecast_hysteresis_reason": rebuild_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reacquisition_status": "reacquired-clearance",
            "closure_forecast_reacquisition_reason": rebuild_reason,
            "closure_forecast_reset_reentry_status": "reentered-clearance",
            "closure_forecast_reset_reentry_reason": rebuild_reason,
            "closure_forecast_reset_reentry_age_runs": 0,
            "closure_forecast_reset_reentry_persistence_score": 0.0,
            "closure_forecast_reset_reentry_persistence_status": "none",
            "closure_forecast_reset_reentry_persistence_reason": "",
        }

    if recent_reset_reentry_side == "confirmation":
        if rebuild_status == "pending-confirmation-rebuild":
            return {
                "transition_closure_likely_outcome": "hold",
                "closure_forecast_hysteresis_status": "pending-confirmation",
                "closure_forecast_hysteresis_reason": rebuild_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reacquisition_status": "pending-confirmation-reacquisition",
                "closure_forecast_reacquisition_reason": rebuild_reason,
                "closure_forecast_reset_reentry_status": "pending-confirmation-reentry",
                "closure_forecast_reset_reentry_reason": rebuild_reason,
                "closure_forecast_reset_reentry_age_runs": 0,
                "closure_forecast_reset_reentry_persistence_score": 0.0,
                "closure_forecast_reset_reentry_persistence_status": "none",
                "closure_forecast_reset_reentry_persistence_reason": "",
            }
        if recovery_status == "reversing" or current_freshness in {"stale", "insufficient-data"}:
            return {
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reacquisition_status": reacquisition_status,
                "closure_forecast_reacquisition_reason": reacquisition_reason,
                "closure_forecast_reset_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_age_runs": persistence_age_runs,
                "closure_forecast_reset_reentry_persistence_score": persistence_score,
                "closure_forecast_reset_reentry_persistence_status": persistence_status,
                "closure_forecast_reset_reentry_persistence_reason": persistence_reason,
            }

    if recent_reset_reentry_side == "clearance":
        if rebuild_status == "pending-clearance-rebuild":
            weaker_outcome = closure_likely_outcome
            if weaker_outcome == "expire-risk":
                weaker_outcome = "clear-risk"
            return {
                "transition_closure_likely_outcome": weaker_outcome,
                "closure_forecast_hysteresis_status": "pending-clearance",
                "closure_forecast_hysteresis_reason": rebuild_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reacquisition_status": "pending-clearance-reacquisition",
                "closure_forecast_reacquisition_reason": rebuild_reason,
                "closure_forecast_reset_reentry_status": "pending-clearance-reentry",
                "closure_forecast_reset_reentry_reason": rebuild_reason,
                "closure_forecast_reset_reentry_age_runs": 0,
                "closure_forecast_reset_reentry_persistence_score": 0.0,
                "closure_forecast_reset_reentry_persistence_status": "none",
                "closure_forecast_reset_reentry_persistence_reason": "",
            }
        if recovery_status == "reversing" or current_freshness in {"stale", "insufficient-data"}:
            return {
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reacquisition_status": reacquisition_status,
                "closure_forecast_reacquisition_reason": reacquisition_reason,
                "closure_forecast_reset_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_age_runs": persistence_age_runs,
                "closure_forecast_reset_reentry_persistence_score": persistence_score,
                "closure_forecast_reset_reentry_persistence_status": persistence_status,
                "closure_forecast_reset_reentry_persistence_reason": persistence_reason,
            }

    return {
        "transition_closure_likely_outcome": closure_likely_outcome,
        "closure_forecast_hysteresis_status": closure_hysteresis_status,
        "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
        "class_reweight_transition_status": transition_status,
        "class_reweight_transition_reason": transition_reason,
        "class_transition_resolution_status": resolution_status,
        "class_transition_resolution_reason": resolution_reason,
        "closure_forecast_reacquisition_status": reacquisition_status,
        "closure_forecast_reacquisition_reason": reacquisition_reason,
        "closure_forecast_reset_reentry_status": reentry_status,
        "closure_forecast_reset_reentry_reason": reentry_reason,
        "closure_forecast_reset_reentry_age_runs": persistence_age_runs,
        "closure_forecast_reset_reentry_persistence_score": persistence_score,
        "closure_forecast_reset_reentry_persistence_status": persistence_status,
        "closure_forecast_reset_reentry_persistence_reason": persistence_reason,
    }


def _closure_forecast_reset_reentry_refresh_hotspots(
    resolution_targets: list[dict],
    *,
    mode: str,
) -> list[dict]:
    grouped: dict[str, dict] = {}
    for target in resolution_targets:
        class_key = _target_class_key(target)
        if not class_key:
            continue
        current = {
            "scope": "class",
            "label": class_key,
            "closure_forecast_reset_reentry_refresh_recovery_score": target.get(
                "closure_forecast_reset_reentry_refresh_recovery_score",
                0.0,
            ),
            "closure_forecast_reset_reentry_refresh_recovery_status": target.get(
                "closure_forecast_reset_reentry_refresh_recovery_status",
                "none",
            ),
            "recent_reset_reentry_refresh_path": target.get(
                "recent_reset_reentry_refresh_path",
                "",
            ),
        }
        existing = grouped.get(class_key)
        if existing is None or abs(
            current["closure_forecast_reset_reentry_refresh_recovery_score"]
        ) > abs(existing["closure_forecast_reset_reentry_refresh_recovery_score"]):
            grouped[class_key] = current
    hotspots = list(grouped.values())
    if mode == "confirmation":
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reset_reentry_refresh_recovery_status")
            in {
                "recovering-confirmation-reentry-reset",
                "rebuilding-confirmation-reentry",
            }
        ]
        hotspots.sort(
            key=lambda item: (
                -item.get("closure_forecast_reset_reentry_refresh_recovery_score", 0.0),
                item.get("label", ""),
            )
        )
    else:
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reset_reentry_refresh_recovery_status")
            in {
                "recovering-clearance-reentry-reset",
                "rebuilding-clearance-reentry",
            }
        ]
        hotspots.sort(
            key=lambda item: (
                item.get("closure_forecast_reset_reentry_refresh_recovery_score", 0.0),
                item.get("label", ""),
            )
        )
    return hotspots[:5]


def _closure_forecast_reset_reentry_refresh_recovery_summary(
    primary_target: dict,
    recovering_confirmation_hotspots: list[dict],
    recovering_clearance_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    status = primary_target.get(
        "closure_forecast_reset_reentry_refresh_recovery_status",
        "none",
    )
    score = primary_target.get("closure_forecast_reset_reentry_refresh_recovery_score", 0.0)
    if status == "recovering-confirmation-reentry-reset":
        return (
            f"Fresh confirmation-side evidence is returning after reset re-entry softened or reset for {label}, "
            f"but it has not yet rebuilt stronger reset re-entry ({score:.2f})."
        )
    if status == "recovering-clearance-reentry-reset":
        return (
            f"Fresh clearance-side evidence is returning after reset re-entry softened or reset for {label}, "
            f"but it has not yet rebuilt stronger reset re-entry ({score:.2f})."
        )
    if status == "rebuilding-confirmation-reentry":
        return (
            f"Confirmation-side reset re-entry for {label} is rebuilding strongly enough that stronger restored posture may be re-earned soon ({score:.2f})."
        )
    if status == "rebuilding-clearance-reentry":
        return (
            f"Clearance-side reset re-entry for {label} is rebuilding strongly enough that stronger restored caution may be re-earned soon ({score:.2f})."
        )
    if status == "reversing":
        return (
            f"The post-reset reset re-entry recovery attempt for {label} is changing direction, so rebuild stays blocked ({score:.2f})."
        )
    if status == "blocked":
        return primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reason",
            f"Local target instability is still preventing positive confirmation-side reset re-entry rebuild for {label}.",
        )
    if recovering_confirmation_hotspots:
        hotspot = recovering_confirmation_hotspots[0]
        return (
            f"Confirmation-side reset re-entry recovery is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes are closest to rebuilding stronger restored confirmation posture."
        )
    if recovering_clearance_hotspots:
        hotspot = recovering_clearance_hotspots[0]
        return (
            f"Clearance-side reset re-entry recovery is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes are closest to rebuilding stronger restored clearance posture."
        )
    return "No reset re-entry rebuild attempt is active enough yet to re-earn stronger restored posture."


def _closure_forecast_reset_reentry_rebuild_summary(
    primary_target: dict,
    recovering_confirmation_hotspots: list[dict],
    recovering_clearance_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    status = primary_target.get("closure_forecast_reset_reentry_rebuild_status", "none")
    if status == "pending-confirmation-rebuild":
        return (
            f"Fresh confirmation-side evidence is returning after reset re-entry softened or reset for {label}, "
            "but stronger reset re-entry still needs more fresh follow-through before it is rebuilt."
        )
    if status == "pending-clearance-rebuild":
        return (
            f"Fresh clearance-side evidence is returning after reset re-entry softened or reset for {label}, "
            "but stronger reset re-entry still needs more fresh follow-through before it is rebuilt."
        )
    if status == "rebuilt-confirmation-reentry":
        return (
            f"Fresh confirmation-side follow-through for {label} has rebuilt stronger confirmation-side reset re-entry."
        )
    if status == "rebuilt-clearance-reentry":
        return (
            f"Fresh clearance-side pressure for {label} has rebuilt stronger clearance-side reset re-entry."
        )
    if status == "blocked":
        return primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reason",
            f"Local target instability is still preventing positive confirmation-side reset re-entry rebuild for {label}.",
        )
    if recovering_confirmation_hotspots:
        hotspot = recovering_confirmation_hotspots[0]
        return (
            f"Confirmation-side reset re-entry rebuild is closest around {hotspot.get('label', 'recent hotspots')}, "
            "but it still needs one more layer of fresh confirmation follow-through."
        )
    if recovering_clearance_hotspots:
        hotspot = recovering_clearance_hotspots[0]
        return (
            f"Clearance-side reset re-entry rebuild is closest around {hotspot.get('label', 'recent hotspots')}, "
            "but it still needs one more layer of fresh clearance follow-through."
        )
    return "No reset re-entry rebuild is changing the current restored closure-forecast posture right now."


def _apply_reset_reentry_refresh_recovery_and_rebuild(
    resolution_targets: list[dict],
    history: list[dict],
    *,
    current_generated_at: str,
    confidence_calibration: dict,
) -> dict:
    if not resolution_targets:
        return {
            "primary_target_closure_forecast_reset_reentry_refresh_recovery_score": 0.0,
            "primary_target_closure_forecast_reset_reentry_refresh_recovery_status": "none",
            "primary_target_closure_forecast_reset_reentry_rebuild_status": "none",
            "primary_target_closure_forecast_reset_reentry_rebuild_reason": "",
            "closure_forecast_reset_reentry_refresh_recovery_summary": "No reset re-entry refresh recovery is recorded because there is no active target.",
            "closure_forecast_reset_reentry_rebuild_summary": "No reset re-entry rebuild is recorded because there is no active target.",
            "closure_forecast_reset_reentry_refresh_window_runs": CLASS_RESET_REENTRY_REFRESH_REBUILD_WINDOW_RUNS,
            "recovering_from_confirmation_reentry_reset_hotspots": [],
            "recovering_from_clearance_reentry_reset_hotspots": [],
        }

    current_primary_target = resolution_targets[0]
    current_bucket = _recommendation_bucket(current_primary_target)
    closure_forecast_events = _class_closure_forecast_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )
    transition_events = _class_transition_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )

    updated_targets: list[dict] = []
    for target in resolution_targets:
        refresh_recovery_score = 0.0
        refresh_recovery_status = "none"
        rebuild_status = "none"
        rebuild_reason = ""
        refresh_path = ""
        closure_likely_outcome = target.get("transition_closure_likely_outcome", "none")
        closure_hysteresis_status = target.get("closure_forecast_hysteresis_status", "none")
        closure_hysteresis_reason = target.get("closure_forecast_hysteresis_reason", "")
        transition_status = target.get("class_reweight_transition_status", "none")
        transition_reason = target.get("class_reweight_transition_reason", "")
        resolution_status = target.get("class_transition_resolution_status", "none")
        resolution_reason = target.get("class_transition_resolution_reason", "")
        reacquisition_status = target.get("closure_forecast_reacquisition_status", "none")
        reacquisition_reason = target.get("closure_forecast_reacquisition_reason", "")
        reentry_status = target.get("closure_forecast_reset_reentry_status", "none")
        reentry_reason = target.get("closure_forecast_reset_reentry_reason", "")
        persistence_age_runs = target.get("closure_forecast_reset_reentry_age_runs", 0)
        persistence_score = target.get("closure_forecast_reset_reentry_persistence_score", 0.0)
        persistence_status = target.get("closure_forecast_reset_reentry_persistence_status", "none")
        persistence_reason = target.get("closure_forecast_reset_reentry_persistence_reason", "")

        if _recommendation_bucket(target) == current_bucket:
            transition_history_meta = _target_class_transition_history(target, transition_events)
            refresh_meta = _closure_forecast_reset_reentry_refresh_recovery_for_target(
                target,
                closure_forecast_events,
                transition_history_meta,
            )
            refresh_recovery_score = refresh_meta[
                "closure_forecast_reset_reentry_refresh_recovery_score"
            ]
            refresh_recovery_status = refresh_meta[
                "closure_forecast_reset_reentry_refresh_recovery_status"
            ]
            rebuild_status = refresh_meta["closure_forecast_reset_reentry_rebuild_status"]
            rebuild_reason = refresh_meta["closure_forecast_reset_reentry_rebuild_reason"]
            refresh_path = refresh_meta["recent_reset_reentry_refresh_path"]
            control_updates = _apply_reset_reentry_refresh_rebuild_control(
                target,
                refresh_meta=refresh_meta,
                transition_history_meta=transition_history_meta,
                closure_likely_outcome=closure_likely_outcome,
                closure_hysteresis_status=closure_hysteresis_status,
                closure_hysteresis_reason=closure_hysteresis_reason,
                transition_status=transition_status,
                transition_reason=transition_reason,
                resolution_status=resolution_status,
                resolution_reason=resolution_reason,
                reacquisition_status=reacquisition_status,
                reacquisition_reason=reacquisition_reason,
                reentry_status=reentry_status,
                reentry_reason=reentry_reason,
                persistence_age_runs=persistence_age_runs,
                persistence_score=persistence_score,
                persistence_status=persistence_status,
                persistence_reason=persistence_reason,
            )
            closure_likely_outcome = control_updates["transition_closure_likely_outcome"]
            closure_hysteresis_status = control_updates["closure_forecast_hysteresis_status"]
            closure_hysteresis_reason = control_updates["closure_forecast_hysteresis_reason"]
            transition_status = control_updates["class_reweight_transition_status"]
            transition_reason = control_updates["class_reweight_transition_reason"]
            resolution_status = control_updates["class_transition_resolution_status"]
            resolution_reason = control_updates["class_transition_resolution_reason"]
            reacquisition_status = control_updates["closure_forecast_reacquisition_status"]
            reacquisition_reason = control_updates["closure_forecast_reacquisition_reason"]
            reentry_status = control_updates["closure_forecast_reset_reentry_status"]
            reentry_reason = control_updates["closure_forecast_reset_reentry_reason"]
            persistence_age_runs = control_updates["closure_forecast_reset_reentry_age_runs"]
            persistence_score = control_updates["closure_forecast_reset_reentry_persistence_score"]
            persistence_status = control_updates["closure_forecast_reset_reentry_persistence_status"]
            persistence_reason = control_updates["closure_forecast_reset_reentry_persistence_reason"]

        updated_targets.append(
            {
                **target,
                "closure_forecast_reset_reentry_refresh_recovery_score": refresh_recovery_score,
                "closure_forecast_reset_reentry_refresh_recovery_status": refresh_recovery_status,
                "closure_forecast_reset_reentry_rebuild_status": rebuild_status,
                "closure_forecast_reset_reentry_rebuild_reason": rebuild_reason,
                "recent_reset_reentry_refresh_path": refresh_path,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reacquisition_status": reacquisition_status,
                "closure_forecast_reacquisition_reason": reacquisition_reason,
                "closure_forecast_reset_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_age_runs": persistence_age_runs,
                "closure_forecast_reset_reentry_persistence_score": persistence_score,
                "closure_forecast_reset_reentry_persistence_status": persistence_status,
                "closure_forecast_reset_reentry_persistence_reason": persistence_reason,
            }
        )

    resolution_targets[:] = updated_targets
    primary_target = resolution_targets[0]
    recovering_confirmation_hotspots = _closure_forecast_reset_reentry_refresh_hotspots(
        resolution_targets,
        mode="confirmation",
    )
    recovering_clearance_hotspots = _closure_forecast_reset_reentry_refresh_hotspots(
        resolution_targets,
        mode="clearance",
    )
    return {
        "primary_target_closure_forecast_reset_reentry_refresh_recovery_score": primary_target.get(
            "closure_forecast_reset_reentry_refresh_recovery_score",
            0.0,
        ),
        "primary_target_closure_forecast_reset_reentry_refresh_recovery_status": primary_target.get(
            "closure_forecast_reset_reentry_refresh_recovery_status",
            "none",
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_status",
            "none",
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reason",
            "",
        ),
        "closure_forecast_reset_reentry_refresh_recovery_summary": _closure_forecast_reset_reentry_refresh_recovery_summary(
            primary_target,
            recovering_confirmation_hotspots,
            recovering_clearance_hotspots,
        ),
        "closure_forecast_reset_reentry_rebuild_summary": _closure_forecast_reset_reentry_rebuild_summary(
            primary_target,
            recovering_confirmation_hotspots,
            recovering_clearance_hotspots,
        ),
        "closure_forecast_reset_reentry_refresh_window_runs": CLASS_RESET_REENTRY_REFRESH_REBUILD_WINDOW_RUNS,
        "recovering_from_confirmation_reentry_reset_hotspots": recovering_confirmation_hotspots,
        "recovering_from_clearance_reentry_reset_hotspots": recovering_clearance_hotspots,
    }


def _closure_forecast_reset_reentry_rebuild_side_from_persistence_status(status: str) -> str:
    if status in {
        "holding-confirmation-rebuild",
        "sustained-confirmation-rebuild",
    }:
        return "confirmation"
    if status in {
        "holding-clearance-rebuild",
        "sustained-clearance-rebuild",
    }:
        return "clearance"
    return "none"


def _closure_forecast_reset_reentry_rebuild_side_from_event(event: dict) -> str:
    side = _closure_forecast_reset_reentry_rebuild_side_from_persistence_status(
        event.get("closure_forecast_reset_reentry_rebuild_persistence_status", "none")
    )
    if side != "none":
        return side
    side = _closure_forecast_reset_reentry_rebuild_side_from_status(
        event.get("closure_forecast_reset_reentry_rebuild_status", "none")
    )
    if side != "none":
        return side
    return _closure_forecast_reset_reentry_rebuild_side_from_recovery_status(
        event.get("closure_forecast_reset_reentry_refresh_recovery_status", "none")
    )


def _closure_forecast_reset_reentry_rebuild_path_label(event: dict) -> str:
    persistence_status = (
        event.get("closure_forecast_reset_reentry_rebuild_persistence_status", "none")
        or "none"
    )
    if persistence_status != "none":
        return persistence_status
    churn_status = event.get("closure_forecast_reset_reentry_rebuild_churn_status", "none") or "none"
    if churn_status != "none":
        return churn_status
    rebuild_status = event.get("closure_forecast_reset_reentry_rebuild_status", "none") or "none"
    if rebuild_status != "none":
        return rebuild_status
    recovery_status = (
        event.get("closure_forecast_reset_reentry_refresh_recovery_status", "none")
        or "none"
    )
    if recovery_status != "none":
        return recovery_status
    reset_status = event.get("closure_forecast_reset_reentry_reset_status", "none") or "none"
    if reset_status != "none":
        return reset_status
    reentry_status = event.get("closure_forecast_reset_reentry_status", "none") or "none"
    if reentry_status != "none":
        return reentry_status
    likely_outcome = event.get("transition_closure_likely_outcome", "none") or "none"
    if likely_outcome != "none":
        return likely_outcome
    return "hold"


def _closure_forecast_reset_reentry_rebuild_persistence_for_target(
    target: dict,
    closure_forecast_events: list[dict],
    transition_history_meta: dict,
) -> dict:
    matching_events = _ordered_reset_reentry_events_for_target(
        target,
        closure_forecast_events,
    )[:CLASS_RESET_REENTRY_REBUILD_PERSISTENCE_WINDOW_RUNS]
    relevant_events = [
        event
        for event in matching_events
        if _closure_forecast_reset_reentry_rebuild_side_from_event(event) != "none"
    ]
    current_side = (
        _closure_forecast_reset_reentry_rebuild_side_from_event(matching_events[0])
        if matching_events
        else "none"
    )
    persistence_age_runs = 0
    for event in matching_events:
        event_side = _closure_forecast_reset_reentry_rebuild_side_from_event(event)
        if event_side != current_side or event_side == "none":
            break
        persistence_age_runs += 1

    weighted_total = 0.0
    weight_sum = 0.0
    directions: list[str] = []
    for index, event in enumerate(
        relevant_events[:CLASS_RESET_REENTRY_REBUILD_PERSISTENCE_WINDOW_RUNS]
    ):
        weight = (1.0, 0.8, 0.6, 0.4)[
            min(index, CLASS_RESET_REENTRY_REBUILD_PERSISTENCE_WINDOW_RUNS - 1)
        ]
        event_side = _closure_forecast_reset_reentry_rebuild_side_from_event(event)
        sign = 1.0 if event_side == "confirmation" else -1.0
        directions.append(
            "supporting-confirmation" if sign > 0 else "supporting-clearance"
        )
        magnitude = 0.0
        if event.get("closure_forecast_reset_reentry_rebuild_status", "none") in {
            "rebuilt-confirmation-reentry",
            "rebuilt-clearance-reentry",
        }:
            magnitude += 0.15
        if event.get("closure_forecast_reset_reentry_refresh_recovery_status", "none") in {
            "rebuilding-confirmation-reentry",
            "rebuilding-clearance-reentry",
        }:
            magnitude += 0.10
        momentum_status = event.get("closure_forecast_momentum_status", "insufficient-data")
        if (
            event_side == "confirmation" and momentum_status == "sustained-confirmation"
        ) or (
            event_side == "clearance" and momentum_status == "sustained-clearance"
        ):
            magnitude += 0.10
        stability_status = event.get("closure_forecast_stability_status", "watch")
        if stability_status == "stable":
            magnitude += 0.10
        freshness_status = event.get(
            "closure_forecast_reset_reentry_freshness_status",
            "insufficient-data",
        )
        if freshness_status == "fresh":
            magnitude += 0.10
        elif freshness_status == "mixed-age":
            magnitude = max(0.0, magnitude - 0.10)
        if momentum_status in {"reversing", "unstable"}:
            magnitude = max(0.0, magnitude - 0.15)
        if stability_status == "oscillating":
            magnitude = max(0.0, magnitude - 0.15)
        if event.get("closure_forecast_reset_reentry_reset_status", "none") != "none":
            magnitude = max(0.0, magnitude - 0.15)
        weighted_total += sign * magnitude * weight
        weight_sum += weight

    persistence_score = _clamp_round(
        weighted_total / max(weight_sum, 1.0),
        lower=-0.95,
        upper=0.95,
    )
    current_momentum_status = target.get(
        "closure_forecast_momentum_status",
        "insufficient-data",
    )
    current_stability_status = target.get("closure_forecast_stability_status", "watch")
    current_freshness_status = target.get(
        "closure_forecast_reset_reentry_freshness_status",
        "insufficient-data",
    )
    earlier_majority = _closure_forecast_direction_majority(directions[1:])
    current_direction = (
        "supporting-confirmation"
        if current_side == "confirmation"
        else "supporting-clearance"
        if current_side == "clearance"
        else "neutral"
    )

    if current_side == "none" and not relevant_events:
        persistence_status = "none"
    elif (
        target.get("closure_forecast_reset_reentry_rebuild_status", "none")
        in {"rebuilt-confirmation-reentry", "rebuilt-clearance-reentry"}
        and persistence_age_runs == 1
    ):
        persistence_status = "just-rebuilt"
    elif len(relevant_events) < 2:
        persistence_status = "insufficient-data"
    elif (
        _closure_forecast_direction_reversing(current_direction, earlier_majority)
        or current_momentum_status in {"reversing", "unstable"}
        or target.get("closure_forecast_reset_reentry_reset_status", "none") != "none"
    ):
        persistence_status = "reversing"
    elif (
        current_side == "confirmation"
        and persistence_age_runs >= 3
        and current_freshness_status == "fresh"
        and current_momentum_status == "sustained-confirmation"
        and current_stability_status != "oscillating"
    ):
        persistence_status = "sustained-confirmation-rebuild"
    elif (
        current_side == "clearance"
        and persistence_age_runs >= 3
        and current_freshness_status == "fresh"
        and current_momentum_status == "sustained-clearance"
        and current_stability_status != "oscillating"
    ):
        persistence_status = "sustained-clearance-rebuild"
    elif current_side == "confirmation" and persistence_age_runs >= 2 and persistence_score > 0:
        persistence_status = "holding-confirmation-rebuild"
    elif current_side == "clearance" and persistence_age_runs >= 2 and persistence_score < 0:
        persistence_status = "holding-clearance-rebuild"
    else:
        persistence_status = "none"

    if persistence_status == "just-rebuilt":
        persistence_reason = "Stronger reset re-entry posture has been rebuilt, but it has not yet proved it can hold."
    elif persistence_status == "holding-confirmation-rebuild":
        persistence_reason = "Confirmation-side rebuild has stayed aligned long enough to keep the restored forecast in place."
    elif persistence_status == "holding-clearance-rebuild":
        persistence_reason = "Clearance-side rebuild has stayed aligned long enough to keep the restored forecast in place."
    elif persistence_status == "sustained-confirmation-rebuild":
        persistence_reason = "Confirmation-side rebuild is now holding with enough follow-through to trust the restored forecast more."
    elif persistence_status == "sustained-clearance-rebuild":
        persistence_reason = "Clearance-side rebuild is now holding with enough follow-through to trust the restored caution more."
    elif persistence_status == "reversing":
        persistence_reason = "The rebuilt posture is already weakening, so it is being softened again."
    elif persistence_status == "insufficient-data":
        persistence_reason = "Rebuilt reset re-entry is still too lightly exercised to say whether the restored forecast can hold."
    else:
        persistence_reason = ""

    return {
        "closure_forecast_reset_reentry_rebuild_age_runs": persistence_age_runs,
        "closure_forecast_reset_reentry_rebuild_persistence_score": persistence_score,
        "closure_forecast_reset_reentry_rebuild_persistence_status": persistence_status,
        "closure_forecast_reset_reentry_rebuild_persistence_reason": persistence_reason,
        "recent_reset_reentry_rebuild_persistence_path": " -> ".join(
            _closure_forecast_reset_reentry_rebuild_path_label(event)
            for event in matching_events
            if event
        ),
    }


def _closure_forecast_reset_reentry_rebuild_churn_for_target(
    target: dict,
    closure_forecast_events: list[dict],
    transition_history_meta: dict,
) -> dict:
    matching_events = _ordered_reset_reentry_events_for_target(
        target,
        closure_forecast_events,
    )[:CLASS_RESET_REENTRY_REBUILD_PERSISTENCE_WINDOW_RUNS]
    relevant_events = [
        event
        for event in matching_events
        if _closure_forecast_reset_reentry_rebuild_side_from_event(event) != "none"
    ]
    side_path = [
        _closure_forecast_reset_reentry_rebuild_side_from_event(event)
        for event in relevant_events
    ]
    current_side = side_path[0] if side_path else "none"
    local_noise = _target_specific_normalization_noise(target, transition_history_meta)
    if current_side == "none":
        churn_score = 0.0
        churn_status = "none"
        churn_reason = ""
    else:
        flip_count = _class_direction_flip_count(
            [
                "supporting-confirmation"
                if side == "confirmation"
                else "supporting-clearance"
                for side in side_path
            ]
        )
        churn_score = float(flip_count) * 0.20
        stability_status = target.get("closure_forecast_stability_status", "watch")
        momentum_status = target.get("closure_forecast_momentum_status", "insufficient-data")
        if stability_status == "oscillating":
            churn_score += 0.15
        if momentum_status == "reversing":
            churn_score += 0.10
        if momentum_status == "unstable":
            churn_score += 0.10
        freshness_path = [
            event.get(
                "closure_forecast_reset_reentry_freshness_status",
                "insufficient-data",
            )
            for event in relevant_events
        ]
        if any(
            previous == "fresh" and current in {"mixed-age", "stale", "insufficient-data"}
            for previous, current in zip(freshness_path, freshness_path[1:])
        ):
            churn_score += 0.10
        if any(
            event.get("closure_forecast_reset_reentry_reset_status", "none") != "none"
            for event in relevant_events
        ):
            churn_score += 0.10
        if (
            len(relevant_events) >= 2
            and side_path[0] == side_path[1]
            and relevant_events[0].get(
                "closure_forecast_reset_reentry_freshness_status",
                "insufficient-data",
            )
            == "fresh"
            and relevant_events[1].get(
                "closure_forecast_reset_reentry_freshness_status",
                "insufficient-data",
            )
            == "fresh"
        ):
            churn_score -= 0.10
        churn_score = _clamp_round(churn_score, lower=0.0, upper=0.95)
        if local_noise and current_side == "confirmation":
            churn_status = "blocked"
            churn_reason = "Local target instability is preventing positive confirmation-side rebuild persistence."
        elif churn_score >= 0.45 or flip_count >= 2:
            churn_status = "churn"
            churn_reason = "Rebuilt reset re-entry is flipping enough that restored posture should be softened quickly."
        elif churn_score >= 0.20:
            churn_status = "watch"
            churn_reason = "Rebuilt reset re-entry is wobbling and may lose its restored strength soon."
        else:
            churn_status = "none"
            churn_reason = ""

    return {
        "closure_forecast_reset_reentry_rebuild_churn_score": churn_score,
        "closure_forecast_reset_reentry_rebuild_churn_status": churn_status,
        "closure_forecast_reset_reentry_rebuild_churn_reason": churn_reason,
        "recent_reset_reentry_rebuild_churn_path": " -> ".join(
            _closure_forecast_reset_reentry_rebuild_path_label(event)
            for event in matching_events
            if event
        ),
    }


def _apply_reset_reentry_rebuild_persistence_and_churn_control(
    target: dict,
    *,
    persistence_meta: dict,
    churn_meta: dict,
    transition_history_meta: dict,
    closure_likely_outcome: str,
    closure_hysteresis_status: str,
    closure_hysteresis_reason: str,
    transition_status: str,
    transition_reason: str,
    resolution_status: str,
    resolution_reason: str,
) -> dict:
    persistence_status = persistence_meta.get(
        "closure_forecast_reset_reentry_rebuild_persistence_status",
        "none",
    )
    persistence_reason = persistence_meta.get(
        "closure_forecast_reset_reentry_rebuild_persistence_reason",
        "",
    )
    churn_status = churn_meta.get(
        "closure_forecast_reset_reentry_rebuild_churn_status",
        "none",
    )
    churn_reason = churn_meta.get("closure_forecast_reset_reentry_rebuild_churn_reason", "")
    current_rebuild_status = target.get("closure_forecast_reset_reentry_rebuild_status", "none")
    current_freshness_status = target.get(
        "closure_forecast_reset_reentry_freshness_status",
        "insufficient-data",
    )
    transition_age_runs = int(target.get("class_transition_age_runs", 0) or 0)
    recent_pending_status = transition_history_meta.get("recent_pending_status", "none")
    current_side = _closure_forecast_reset_reentry_rebuild_side_from_status(
        current_rebuild_status
    )
    if current_side == "none":
        current_side = _closure_forecast_reset_reentry_rebuild_side_from_recovery_status(
            target.get("closure_forecast_reset_reentry_refresh_recovery_status", "none")
        )
    if (
        current_side == "none"
        and persistence_status in {"none", "insufficient-data"}
        and churn_status == "none"
    ):
        return {
            "transition_closure_likely_outcome": closure_likely_outcome,
            "closure_forecast_hysteresis_status": closure_hysteresis_status,
            "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
        }

    if churn_status == "blocked" and current_side == "confirmation":
        if closure_likely_outcome == "confirm-soon":
            closure_likely_outcome = "hold"
        if closure_hysteresis_status == "confirmed-confirmation":
            closure_hysteresis_status = "pending-confirmation"
        closure_hysteresis_reason = churn_reason or persistence_reason or closure_hysteresis_reason
        return {
            "transition_closure_likely_outcome": closure_likely_outcome,
            "closure_forecast_hysteresis_status": closure_hysteresis_status,
            "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
        }

    if current_rebuild_status == "rebuilt-confirmation-reentry":
        if persistence_status in {
            "holding-confirmation-rebuild",
            "sustained-confirmation-rebuild",
        } and churn_status != "churn":
            return {
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
            }
        if (
            persistence_status == "reversing"
            or churn_status == "churn"
            or (
                current_freshness_status in {"stale", "insufficient-data"}
                and persistence_status != "just-rebuilt"
            )
        ):
            closure_likely_outcome = "hold"
            if closure_hysteresis_status == "confirmed-confirmation":
                closure_hysteresis_status = "pending-confirmation"
            closure_hysteresis_reason = churn_reason or persistence_reason or closure_hysteresis_reason

    if current_rebuild_status == "rebuilt-clearance-reentry":
        if persistence_status in {
            "holding-clearance-rebuild",
            "sustained-clearance-rebuild",
        } and churn_status != "churn":
            if closure_likely_outcome == "expire-risk" and transition_age_runs < 3:
                closure_likely_outcome = "clear-risk"
            return {
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
            }
        if (
            persistence_status in {"reversing", "none", "insufficient-data"}
            or churn_status == "churn"
            or (
                current_freshness_status in {"stale", "insufficient-data"}
                and persistence_status != "just-rebuilt"
            )
        ):
            if closure_likely_outcome == "expire-risk":
                closure_likely_outcome = "clear-risk"
            elif closure_likely_outcome == "clear-risk":
                closure_likely_outcome = "hold"
            if closure_hysteresis_status == "confirmed-clearance":
                closure_hysteresis_status = "pending-clearance"
            closure_hysteresis_reason = churn_reason or persistence_reason or closure_hysteresis_reason
        if (
            resolution_status == "cleared"
            and recent_pending_status in {"pending-support", "pending-caution"}
            and (
                persistence_status not in {
                    "holding-clearance-rebuild",
                    "sustained-clearance-rebuild",
                }
                or churn_status == "churn"
            )
        ):
            restore_reason = churn_reason or persistence_reason or (
                "Clearance-side rebuild stopped holding cleanly, so the earlier-clear posture has been withdrawn."
            )
            transition_status = recent_pending_status
            transition_reason = restore_reason
            resolution_status = "none"
            resolution_reason = ""

    return {
        "transition_closure_likely_outcome": closure_likely_outcome,
        "closure_forecast_hysteresis_status": closure_hysteresis_status,
        "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
        "class_reweight_transition_status": transition_status,
        "class_reweight_transition_reason": transition_reason,
        "class_transition_resolution_status": resolution_status,
        "class_transition_resolution_reason": resolution_reason,
    }


def _closure_forecast_reset_reentry_rebuild_hotspots(
    resolution_targets: list[dict],
    *,
    mode: str,
) -> list[dict]:
    grouped: dict[str, dict] = {}
    for target in resolution_targets:
        class_key = _target_class_key(target)
        if not class_key:
            continue
        current = {
            "scope": "class",
            "label": class_key,
            "closure_forecast_reset_reentry_rebuild_age_runs": target.get(
                "closure_forecast_reset_reentry_rebuild_age_runs",
                0,
            ),
            "closure_forecast_reset_reentry_rebuild_persistence_score": target.get(
                "closure_forecast_reset_reentry_rebuild_persistence_score",
                0.0,
            ),
            "closure_forecast_reset_reentry_rebuild_persistence_status": target.get(
                "closure_forecast_reset_reentry_rebuild_persistence_status",
                "none",
            ),
            "closure_forecast_reset_reentry_rebuild_churn_score": target.get(
                "closure_forecast_reset_reentry_rebuild_churn_score",
                0.0,
            ),
            "closure_forecast_reset_reentry_rebuild_churn_status": target.get(
                "closure_forecast_reset_reentry_rebuild_churn_status",
                "none",
            ),
            "recent_reset_reentry_rebuild_persistence_path": target.get(
                "recent_reset_reentry_rebuild_persistence_path",
                "",
            ),
            "recent_reset_reentry_rebuild_churn_path": target.get(
                "recent_reset_reentry_rebuild_churn_path",
                "",
            ),
        }
        existing = grouped.get(class_key)
        if existing is None or abs(
            current["closure_forecast_reset_reentry_rebuild_persistence_score"]
        ) > abs(existing["closure_forecast_reset_reentry_rebuild_persistence_score"]):
            grouped[class_key] = current
    hotspots = list(grouped.values())
    if mode == "just-rebuilt":
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reset_reentry_rebuild_persistence_status")
            == "just-rebuilt"
        ]
        hotspots.sort(
            key=lambda item: (
                -item.get("closure_forecast_reset_reentry_rebuild_age_runs", 0),
                -abs(item.get("closure_forecast_reset_reentry_rebuild_persistence_score", 0.0)),
                item.get("label", ""),
            )
        )
    elif mode == "holding":
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reset_reentry_rebuild_persistence_status")
            in {
                "holding-confirmation-rebuild",
                "holding-clearance-rebuild",
                "sustained-confirmation-rebuild",
                "sustained-clearance-rebuild",
            }
        ]
        hotspots.sort(
            key=lambda item: (
                -item.get("closure_forecast_reset_reentry_rebuild_age_runs", 0),
                -abs(item.get("closure_forecast_reset_reentry_rebuild_persistence_score", 0.0)),
                item.get("label", ""),
            )
        )
    else:
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reset_reentry_rebuild_churn_status")
            in {"watch", "churn", "blocked"}
        ]
        hotspots.sort(
            key=lambda item: (
                -item.get("closure_forecast_reset_reentry_rebuild_churn_score", 0.0),
                -item.get("closure_forecast_reset_reentry_rebuild_age_runs", 0),
                item.get("label", ""),
            )
        )
    return hotspots[:5]


def _closure_forecast_reset_reentry_rebuild_persistence_summary(
    primary_target: dict,
    just_rebuilt_hotspots: list[dict],
    holding_reset_reentry_rebuild_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    status = primary_target.get(
        "closure_forecast_reset_reentry_rebuild_persistence_status",
        "none",
    )
    age_runs = primary_target.get("closure_forecast_reset_reentry_rebuild_age_runs", 0)
    score = primary_target.get(
        "closure_forecast_reset_reentry_rebuild_persistence_score",
        0.0,
    )
    if status == "just-rebuilt":
        return f"{label} has only just rebuilt stronger reset re-entry posture, so it is still fragile ({score:.2f}; {age_runs} run)."
    if status == "holding-confirmation-rebuild":
        return f"Confirmation-side rebuild for {label} has held long enough to keep the restored forecast in place ({score:.2f}; {age_runs} runs)."
    if status == "holding-clearance-rebuild":
        return f"Clearance-side rebuild for {label} has held long enough to keep the restored caution in place ({score:.2f}; {age_runs} runs)."
    if status == "sustained-confirmation-rebuild":
        return f"Confirmation-side rebuild for {label} is now holding with enough follow-through to trust the restored forecast more ({score:.2f}; {age_runs} runs)."
    if status == "sustained-clearance-rebuild":
        return f"Clearance-side rebuild for {label} is now holding with enough follow-through to trust the restored caution more ({score:.2f}; {age_runs} runs)."
    if status == "reversing":
        return f"The rebuilt reset re-entry posture for {label} is already weakening, so it is being softened again ({score:.2f})."
    if status == "insufficient-data":
        return f"Rebuilt reset re-entry for {label} is still too lightly exercised to say whether the restored forecast can hold."
    if just_rebuilt_hotspots:
        hotspot = just_rebuilt_hotspots[0]
        return (
            f"Newly rebuilt reset re-entry posture is most fragile around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes still need follow-through before the restored forecast can be trusted."
        )
    if holding_reset_reentry_rebuild_hotspots:
        hotspot = holding_reset_reentry_rebuild_hotspots[0]
        return (
            f"Rebuilt reset re-entry posture is holding most cleanly around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes are closest to keeping restored rebuild strength safely."
        )
    return "No rebuilt reset re-entry posture is active enough yet to judge whether it can hold."


def _closure_forecast_reset_reentry_rebuild_churn_summary(
    primary_target: dict,
    reset_reentry_rebuild_churn_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    status = primary_target.get(
        "closure_forecast_reset_reentry_rebuild_churn_status",
        "none",
    )
    score = primary_target.get(
        "closure_forecast_reset_reentry_rebuild_churn_score",
        0.0,
    )
    if status == "watch":
        return f"Rebuilt reset re-entry for {label} is wobbling enough that restored forecast strength may soften soon ({score:.2f})."
    if status == "churn":
        return f"Rebuilt reset re-entry for {label} is flipping enough that restored posture should be softened quickly ({score:.2f})."
    if status == "blocked":
        return primary_target.get(
            "closure_forecast_reset_reentry_rebuild_churn_reason",
            f"Local target instability is preventing positive confirmation-side rebuild persistence for {label}.",
        )
    if reset_reentry_rebuild_churn_hotspots:
        hotspot = reset_reentry_rebuild_churn_hotspots[0]
        return (
            f"Rebuild churn is highest around {hotspot.get('label', 'recent hotspots')}, "
            "so restored posture there should soften quickly if the wobble continues."
        )
    return "No meaningful reset re-entry rebuild churn is active right now."


def _apply_reset_reentry_rebuild_persistence_and_churn(
    resolution_targets: list[dict],
    history: list[dict],
    *,
    current_generated_at: str,
    confidence_calibration: dict,
) -> dict:
    if not resolution_targets:
        return {
            "primary_target_closure_forecast_reset_reentry_rebuild_age_runs": 0,
            "primary_target_closure_forecast_reset_reentry_rebuild_persistence_score": 0.0,
            "primary_target_closure_forecast_reset_reentry_rebuild_persistence_status": "none",
            "primary_target_closure_forecast_reset_reentry_rebuild_persistence_reason": "",
            "closure_forecast_reset_reentry_rebuild_persistence_summary": "No reset re-entry rebuild persistence is recorded because there is no active target.",
            "closure_forecast_reset_reentry_rebuild_window_runs": CLASS_RESET_REENTRY_REBUILD_PERSISTENCE_WINDOW_RUNS,
            "just_rebuilt_hotspots": [],
            "holding_reset_reentry_rebuild_hotspots": [],
            "primary_target_closure_forecast_reset_reentry_rebuild_churn_score": 0.0,
            "primary_target_closure_forecast_reset_reentry_rebuild_churn_status": "none",
            "primary_target_closure_forecast_reset_reentry_rebuild_churn_reason": "",
            "closure_forecast_reset_reentry_rebuild_churn_summary": "No reset re-entry rebuild churn is recorded because there is no active target.",
            "reset_reentry_rebuild_churn_hotspots": [],
        }

    current_primary_target = resolution_targets[0]
    current_bucket = _recommendation_bucket(current_primary_target)
    closure_forecast_events = _class_closure_forecast_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )
    transition_events = _class_transition_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )

    updated_targets: list[dict] = []
    for target in resolution_targets:
        persistence_age_runs = 0
        persistence_score = 0.0
        persistence_status = "none"
        persistence_reason = ""
        persistence_path = ""
        churn_score = 0.0
        churn_status = "none"
        churn_reason = ""
        churn_path = ""
        closure_likely_outcome = target.get("transition_closure_likely_outcome", "none")
        closure_hysteresis_status = target.get("closure_forecast_hysteresis_status", "none")
        closure_hysteresis_reason = target.get("closure_forecast_hysteresis_reason", "")
        transition_status = target.get("class_reweight_transition_status", "none")
        transition_reason = target.get("class_reweight_transition_reason", "")
        resolution_status = target.get("class_transition_resolution_status", "none")
        resolution_reason = target.get("class_transition_resolution_reason", "")

        if _recommendation_bucket(target) == current_bucket:
            transition_history_meta = _target_class_transition_history(target, transition_events)
            persistence_meta = _closure_forecast_reset_reentry_rebuild_persistence_for_target(
                target,
                closure_forecast_events,
                transition_history_meta,
            )
            churn_meta = _closure_forecast_reset_reentry_rebuild_churn_for_target(
                target,
                closure_forecast_events,
                transition_history_meta,
            )
            persistence_age_runs = persistence_meta[
                "closure_forecast_reset_reentry_rebuild_age_runs"
            ]
            persistence_score = persistence_meta[
                "closure_forecast_reset_reentry_rebuild_persistence_score"
            ]
            persistence_status = persistence_meta[
                "closure_forecast_reset_reentry_rebuild_persistence_status"
            ]
            persistence_reason = persistence_meta[
                "closure_forecast_reset_reentry_rebuild_persistence_reason"
            ]
            persistence_path = persistence_meta[
                "recent_reset_reentry_rebuild_persistence_path"
            ]
            churn_score = churn_meta["closure_forecast_reset_reentry_rebuild_churn_score"]
            churn_status = churn_meta["closure_forecast_reset_reentry_rebuild_churn_status"]
            churn_reason = churn_meta["closure_forecast_reset_reentry_rebuild_churn_reason"]
            churn_path = churn_meta["recent_reset_reentry_rebuild_churn_path"]
            control_updates = _apply_reset_reentry_rebuild_persistence_and_churn_control(
                target,
                persistence_meta=persistence_meta,
                churn_meta=churn_meta,
                transition_history_meta=transition_history_meta,
                closure_likely_outcome=closure_likely_outcome,
                closure_hysteresis_status=closure_hysteresis_status,
                closure_hysteresis_reason=closure_hysteresis_reason,
                transition_status=transition_status,
                transition_reason=transition_reason,
                resolution_status=resolution_status,
                resolution_reason=resolution_reason,
            )
            closure_likely_outcome = control_updates["transition_closure_likely_outcome"]
            closure_hysteresis_status = control_updates["closure_forecast_hysteresis_status"]
            closure_hysteresis_reason = control_updates["closure_forecast_hysteresis_reason"]
            transition_status = control_updates["class_reweight_transition_status"]
            transition_reason = control_updates["class_reweight_transition_reason"]
            resolution_status = control_updates["class_transition_resolution_status"]
            resolution_reason = control_updates["class_transition_resolution_reason"]

        updated_targets.append(
            {
                **target,
                "closure_forecast_reset_reentry_rebuild_age_runs": persistence_age_runs,
                "closure_forecast_reset_reentry_rebuild_persistence_score": persistence_score,
                "closure_forecast_reset_reentry_rebuild_persistence_status": persistence_status,
                "closure_forecast_reset_reentry_rebuild_persistence_reason": persistence_reason,
                "recent_reset_reentry_rebuild_persistence_path": persistence_path,
                "closure_forecast_reset_reentry_rebuild_churn_score": churn_score,
                "closure_forecast_reset_reentry_rebuild_churn_status": churn_status,
                "closure_forecast_reset_reentry_rebuild_churn_reason": churn_reason,
                "recent_reset_reentry_rebuild_churn_path": churn_path,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
            }
        )

    resolution_targets[:] = updated_targets
    primary_target = resolution_targets[0]
    just_rebuilt_hotspots = _closure_forecast_reset_reentry_rebuild_hotspots(
        resolution_targets,
        mode="just-rebuilt",
    )
    holding_reset_reentry_rebuild_hotspots = _closure_forecast_reset_reentry_rebuild_hotspots(
        resolution_targets,
        mode="holding",
    )
    reset_reentry_rebuild_churn_hotspots = _closure_forecast_reset_reentry_rebuild_hotspots(
        resolution_targets,
        mode="churn",
    )
    return {
        "primary_target_closure_forecast_reset_reentry_rebuild_age_runs": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_age_runs",
            0,
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_persistence_score": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_persistence_score",
            0.0,
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_persistence_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_persistence_status",
            "none",
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_persistence_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_persistence_reason",
            "",
        ),
        "closure_forecast_reset_reentry_rebuild_persistence_summary": _closure_forecast_reset_reentry_rebuild_persistence_summary(
            primary_target,
            just_rebuilt_hotspots,
            holding_reset_reentry_rebuild_hotspots,
        ),
        "closure_forecast_reset_reentry_rebuild_window_runs": CLASS_RESET_REENTRY_REBUILD_PERSISTENCE_WINDOW_RUNS,
        "just_rebuilt_hotspots": just_rebuilt_hotspots,
        "holding_reset_reentry_rebuild_hotspots": holding_reset_reentry_rebuild_hotspots,
        "primary_target_closure_forecast_reset_reentry_rebuild_churn_score": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_churn_score",
            0.0,
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_churn_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_churn_status",
            "none",
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_churn_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_churn_reason",
            "",
        ),
        "closure_forecast_reset_reentry_rebuild_churn_summary": _closure_forecast_reset_reentry_rebuild_churn_summary(
            primary_target,
            reset_reentry_rebuild_churn_hotspots,
        ),
        "reset_reentry_rebuild_churn_hotspots": reset_reentry_rebuild_churn_hotspots,
    }


def _reset_reentry_rebuild_event_is_confirmation_like(event: dict) -> bool:
    event_side = _closure_forecast_reset_reentry_rebuild_side_from_event(event)
    persistence_status = event.get(
        "closure_forecast_reset_reentry_rebuild_persistence_status",
        "none",
    )
    return (
        event.get("closure_forecast_reset_reentry_rebuild_status", "none")
        in {"pending-confirmation-rebuild", "rebuilt-confirmation-reentry"}
        or (
            persistence_status
            in {
                "just-rebuilt",
                "holding-confirmation-rebuild",
                "sustained-confirmation-rebuild",
            }
            and event_side == "confirmation"
        )
        or event.get("closure_forecast_hysteresis_status", "none")
        in {"pending-confirmation", "confirmed-confirmation"}
        or event.get("transition_closure_likely_outcome", "none") == "confirm-soon"
    )


def _reset_reentry_rebuild_event_is_clearance_like(event: dict) -> bool:
    event_side = _closure_forecast_reset_reentry_rebuild_side_from_event(event)
    persistence_status = event.get(
        "closure_forecast_reset_reentry_rebuild_persistence_status",
        "none",
    )
    return (
        event.get("closure_forecast_reset_reentry_rebuild_status", "none")
        in {"pending-clearance-rebuild", "rebuilt-clearance-reentry"}
        or (
            persistence_status
            in {
                "just-rebuilt",
                "holding-clearance-rebuild",
                "sustained-clearance-rebuild",
            }
            and event_side == "clearance"
        )
        or event.get("closure_forecast_hysteresis_status", "none")
        in {"pending-clearance", "confirmed-clearance"}
        or event.get("transition_closure_likely_outcome", "none")
        in {"clear-risk", "expire-risk"}
    )


def _reset_reentry_rebuild_event_has_evidence(event: dict) -> bool:
    return (
        _reset_reentry_rebuild_event_is_confirmation_like(event)
        or _reset_reentry_rebuild_event_is_clearance_like(event)
        or event.get("closure_forecast_reset_reentry_rebuild_churn_status", "none")
        in {"watch", "churn", "blocked"}
    )


def _reset_reentry_rebuild_event_signal_label(event: dict) -> str:
    if _reset_reentry_rebuild_event_is_confirmation_like(event):
        return "confirmation-like"
    if _reset_reentry_rebuild_event_is_clearance_like(event):
        return "clearance-like"
    return "neutral"


def _closure_forecast_reset_reentry_rebuild_freshness_reason(
    freshness_status: str,
    weighted_rebuild_evidence_count: float,
    recent_window_weight_share: float,
    decayed_confirmation_rate: float,
    decayed_clearance_rate: float,
) -> str:
    if freshness_status == "fresh":
        return (
            "Recent rebuilt reset re-entry evidence is still current enough to keep the restored posture trusted, with "
            f"{recent_window_weight_share:.0%} of the weighted signal coming from the latest "
            f"{CLASS_RESET_REENTRY_REBUILD_FRESHNESS_WINDOW_RUNS} runs."
        )
    if freshness_status == "mixed-age":
        return (
            "Rebuilt reset re-entry memory is still useful, but it is partly aging: "
            f"{recent_window_weight_share:.0%} of the weighted signal is recent and the rest is older carry-forward."
        )
    if freshness_status == "stale":
        return (
            "Older rebuilt reset re-entry strength is carrying more of the signal than recent runs, so it should not keep stronger posture alive on memory alone."
        )
    return (
        "Rebuilt reset re-entry memory is still too lightly exercised to judge freshness, with "
        f"{weighted_rebuild_evidence_count:.2f} weighted rebuilt run(s), "
        f"{decayed_confirmation_rate:.0%} confirmation-like signal, and {decayed_clearance_rate:.0%} clearance-like signal."
    )


def _recent_reset_reentry_rebuild_signal_mix(
    weighted_rebuild_evidence_count: float,
    weighted_confirmation_like: float,
    weighted_clearance_like: float,
    recent_window_weight_share: float,
) -> str:
    return (
        f"{weighted_rebuild_evidence_count:.2f} weighted rebuilt run(s) with "
        f"{weighted_confirmation_like:.2f} confirmation-like, {weighted_clearance_like:.2f} clearance-like, "
        f"and {recent_window_weight_share:.0%} of the signal from the freshest runs."
    )


def _closure_forecast_reset_reentry_rebuild_freshness_for_target(
    target: dict,
    closure_forecast_events: list[dict],
) -> dict:
    class_key = _target_class_key(target)
    class_events = [
        event for event in closure_forecast_events if event.get("class_key") == class_key
    ]
    relevant_events: list[dict] = []
    for event in class_events:
        if not _reset_reentry_rebuild_event_has_evidence(event):
            continue
        relevant_events.append(event)
        if len(relevant_events) >= HISTORY_WINDOW_RUNS:
            break

    weighted_rebuild_evidence_count = 0.0
    weighted_confirmation_like = 0.0
    weighted_clearance_like = 0.0
    recent_rebuild_weight = 0.0
    recent_signals = [
        _reset_reentry_rebuild_event_signal_label(event)
        for event in relevant_events[:CLASS_RESET_REENTRY_REBUILD_FRESHNESS_WINDOW_RUNS]
    ]
    current_side = _closure_forecast_reset_reentry_rebuild_side_from_persistence_status(
        target.get(
            "closure_forecast_reset_reentry_rebuild_persistence_status",
            "none",
        )
    )
    if current_side == "none":
        current_side = _closure_forecast_reset_reentry_rebuild_side_from_status(
            target.get("closure_forecast_reset_reentry_rebuild_status", "none")
        )

    for index, event in enumerate(relevant_events):
        weight = CLASS_MEMORY_RECENCY_WEIGHTS[min(index, HISTORY_WINDOW_RUNS - 1)]
        weighted_rebuild_evidence_count += weight
        event_side = _closure_forecast_reset_reentry_rebuild_side_from_event(event)
        if (
            index < CLASS_RESET_REENTRY_REBUILD_FRESHNESS_WINDOW_RUNS
            and event_side == current_side
        ):
            recent_rebuild_weight += weight
        if _reset_reentry_rebuild_event_is_confirmation_like(event):
            weighted_confirmation_like += weight
        if _reset_reentry_rebuild_event_is_clearance_like(event):
            weighted_clearance_like += weight

    recent_window_weight_share = recent_rebuild_weight / max(
        weighted_rebuild_evidence_count,
        1.0,
    )
    freshness_status = _closure_forecast_freshness_status(
        weighted_rebuild_evidence_count,
        recent_window_weight_share,
    )
    decayed_confirmation_rate = weighted_confirmation_like / max(
        weighted_rebuild_evidence_count,
        1.0,
    )
    decayed_clearance_rate = weighted_clearance_like / max(
        weighted_rebuild_evidence_count,
        1.0,
    )
    return {
        "closure_forecast_reset_reentry_rebuild_freshness_status": freshness_status,
        "closure_forecast_reset_reentry_rebuild_freshness_reason": _closure_forecast_reset_reentry_rebuild_freshness_reason(
            freshness_status,
            weighted_rebuild_evidence_count,
            recent_window_weight_share,
            decayed_confirmation_rate,
            decayed_clearance_rate,
        ),
        "closure_forecast_reset_reentry_rebuild_memory_weight": round(
            recent_window_weight_share,
            2,
        ),
        "decayed_rebuilt_confirmation_reentry_rate": round(
            decayed_confirmation_rate,
            2,
        ),
        "decayed_rebuilt_clearance_reentry_rate": round(
            decayed_clearance_rate,
            2,
        ),
        "recent_reset_reentry_rebuild_signal_mix": _recent_reset_reentry_rebuild_signal_mix(
            weighted_rebuild_evidence_count,
            weighted_confirmation_like,
            weighted_clearance_like,
            recent_window_weight_share,
        ),
        "recent_reset_reentry_rebuild_signal_path": " -> ".join(recent_signals),
        "has_fresh_aligned_recent_evidence": any(
            _closure_forecast_reset_reentry_rebuild_side_from_event(event) == current_side
            and _reset_reentry_rebuild_event_signal_label(event) != "neutral"
            for event in relevant_events[:2]
        ),
    }


def _apply_reset_reentry_rebuild_freshness_reset_control(
    target: dict,
    *,
    freshness_meta: dict,
    transition_history_meta: dict,
    closure_likely_outcome: str,
    closure_hysteresis_status: str,
    closure_hysteresis_reason: str,
    transition_status: str,
    transition_reason: str,
    resolution_status: str,
    resolution_reason: str,
    rebuild_status: str,
    rebuild_reason: str,
    persistence_age_runs: int,
    persistence_score: float,
    persistence_status: str,
    persistence_reason: str,
) -> dict:
    freshness_status = freshness_meta.get(
        "closure_forecast_reset_reentry_rebuild_freshness_status",
        "insufficient-data",
    )
    decayed_clearance_rate = float(
        freshness_meta.get("decayed_rebuilt_clearance_reentry_rate", 0.0) or 0.0
    )
    churn_status = target.get("closure_forecast_reset_reentry_rebuild_churn_status", "none")
    current_side = _closure_forecast_reset_reentry_rebuild_side_from_persistence_status(
        persistence_status
    )
    if current_side == "none":
        current_side = _closure_forecast_reset_reentry_rebuild_side_from_status(
            rebuild_status
        )
    local_noise = _target_specific_normalization_noise(target, transition_history_meta)
    recent_pending_status = transition_history_meta.get("recent_pending_status", "none")
    has_fresh_aligned_recent_evidence = freshness_meta.get(
        "has_fresh_aligned_recent_evidence",
        False,
    )

    def _restore_weaker_pending_posture(
        reset_reason: str,
    ) -> tuple[str, str, str, str]:
        restored_transition_status = transition_status
        restored_transition_reason = transition_reason
        restored_resolution_status = resolution_status
        restored_resolution_reason = resolution_reason
        if (
            resolution_status == "cleared"
            and recent_pending_status in {"pending-support", "pending-caution"}
        ):
            restored_transition_status = recent_pending_status
            restored_transition_reason = reset_reason
            restored_resolution_status = "none"
            restored_resolution_reason = ""
        return (
            restored_transition_status,
            restored_transition_reason,
            restored_resolution_status,
            restored_resolution_reason,
        )

    if local_noise and current_side != "none":
        blocked_reason = "Local target instability still overrides healthy rebuilt reset re-entry freshness."
        if closure_likely_outcome == "confirm-soon":
            closure_likely_outcome = "hold"
        elif closure_likely_outcome == "expire-risk":
            closure_likely_outcome = "clear-risk"
        if closure_hysteresis_status == "confirmed-confirmation":
            closure_hysteresis_status = "pending-confirmation"
        elif closure_hysteresis_status == "confirmed-clearance":
            closure_hysteresis_status = "pending-clearance"
        closure_hysteresis_reason = blocked_reason
        return {
            "closure_forecast_reset_reentry_rebuild_reset_status": "blocked",
            "closure_forecast_reset_reentry_rebuild_reset_reason": blocked_reason,
            "transition_closure_likely_outcome": closure_likely_outcome,
            "closure_forecast_hysteresis_status": closure_hysteresis_status,
            "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reset_reentry_rebuild_status": rebuild_status,
            "closure_forecast_reset_reentry_rebuild_reason": rebuild_reason,
            "closure_forecast_reset_reentry_rebuild_age_runs": persistence_age_runs,
            "closure_forecast_reset_reentry_rebuild_persistence_score": persistence_score,
            "closure_forecast_reset_reentry_rebuild_persistence_status": persistence_status,
            "closure_forecast_reset_reentry_rebuild_persistence_reason": persistence_reason,
        }

    if current_side == "confirmation" and freshness_status == "mixed-age":
        if persistence_status == "sustained-confirmation-rebuild" and (
            churn_status != "churn" or has_fresh_aligned_recent_evidence
        ):
            softened_reason = (
                "Restored confirmation-side rebuilt posture is still visible, but it is aging and has been stepped down from sustained strength."
            )
            softened_outcome = closure_likely_outcome
            if softened_outcome == "hold" and rebuild_status in {
                "pending-confirmation-rebuild",
                "rebuilt-confirmation-reentry",
            }:
                softened_outcome = "confirm-soon"
            return {
                "closure_forecast_reset_reentry_rebuild_reset_status": "confirmation-softened",
                "closure_forecast_reset_reentry_rebuild_reset_reason": softened_reason,
                "transition_closure_likely_outcome": softened_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": softened_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reset_reentry_rebuild_status": rebuild_status,
                "closure_forecast_reset_reentry_rebuild_reason": rebuild_reason,
                "closure_forecast_reset_reentry_rebuild_age_runs": persistence_age_runs,
                "closure_forecast_reset_reentry_rebuild_persistence_score": persistence_score,
                "closure_forecast_reset_reentry_rebuild_persistence_status": "holding-confirmation-rebuild",
                "closure_forecast_reset_reentry_rebuild_persistence_reason": softened_reason,
            }
        if persistence_status == "holding-confirmation-rebuild" and churn_status == "churn":
            freshness_status = "stale"

    if current_side == "clearance" and freshness_status == "mixed-age":
        if persistence_status == "sustained-clearance-rebuild" and (
            churn_status != "churn" or has_fresh_aligned_recent_evidence
        ):
            softened_reason = (
                "Restored clearance-side rebuilt posture is still visible, but it is aging and has been stepped down from sustained strength."
            )
            return {
                "closure_forecast_reset_reentry_rebuild_reset_status": "clearance-softened",
                "closure_forecast_reset_reentry_rebuild_reset_reason": softened_reason,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": softened_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reset_reentry_rebuild_status": rebuild_status,
                "closure_forecast_reset_reentry_rebuild_reason": rebuild_reason,
                "closure_forecast_reset_reentry_rebuild_age_runs": persistence_age_runs,
                "closure_forecast_reset_reentry_rebuild_persistence_score": persistence_score,
                "closure_forecast_reset_reentry_rebuild_persistence_status": "holding-clearance-rebuild",
                "closure_forecast_reset_reentry_rebuild_persistence_reason": softened_reason,
            }
        if persistence_status == "holding-clearance-rebuild" and churn_status == "churn":
            freshness_status = "stale"

    needs_reset = (
        current_side in {"confirmation", "clearance"}
        and persistence_status
        in {
            "holding-confirmation-rebuild",
            "holding-clearance-rebuild",
            "sustained-confirmation-rebuild",
            "sustained-clearance-rebuild",
        }
        and (
            freshness_status in {"stale", "insufficient-data"}
            or not has_fresh_aligned_recent_evidence
            or (
                freshness_status == "mixed-age"
                and churn_status == "churn"
                and not has_fresh_aligned_recent_evidence
            )
        )
    )

    if needs_reset:
        if current_side == "confirmation":
            reset_reason = (
                "Restored confirmation-side rebuilt posture has aged out enough that the stronger carry-forward has been withdrawn."
            )
            closure_likely_outcome = "hold"
            if closure_hysteresis_status == "confirmed-confirmation":
                closure_hysteresis_status = "pending-confirmation"
            closure_hysteresis_reason = reset_reason
            return {
                "closure_forecast_reset_reentry_rebuild_reset_status": "confirmation-reset",
                "closure_forecast_reset_reentry_rebuild_reset_reason": reset_reason,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reset_reentry_rebuild_status": "none",
                "closure_forecast_reset_reentry_rebuild_reason": reset_reason,
                "closure_forecast_reset_reentry_rebuild_age_runs": 0,
                "closure_forecast_reset_reentry_rebuild_persistence_score": 0.0,
                "closure_forecast_reset_reentry_rebuild_persistence_status": "none",
                "closure_forecast_reset_reentry_rebuild_persistence_reason": "",
            }

        reset_reason = (
            "Restored clearance-side rebuilt posture has aged out enough that the stronger carry-forward has been withdrawn."
        )
        if closure_likely_outcome == "expire-risk":
            closure_likely_outcome = "clear-risk"
        elif closure_likely_outcome == "clear-risk":
            closure_likely_outcome = "hold"
        if closure_hysteresis_status == "confirmed-clearance":
            closure_hysteresis_status = "pending-clearance"
        closure_hysteresis_reason = reset_reason
        (
            transition_status,
            transition_reason,
            resolution_status,
            resolution_reason,
        ) = _restore_weaker_pending_posture(reset_reason)
        return {
            "closure_forecast_reset_reentry_rebuild_reset_status": "clearance-reset",
            "closure_forecast_reset_reentry_rebuild_reset_reason": reset_reason,
            "transition_closure_likely_outcome": closure_likely_outcome,
            "closure_forecast_hysteresis_status": closure_hysteresis_status,
            "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reset_reentry_rebuild_status": "none",
            "closure_forecast_reset_reentry_rebuild_reason": reset_reason,
            "closure_forecast_reset_reentry_rebuild_age_runs": 0,
            "closure_forecast_reset_reentry_rebuild_persistence_score": 0.0,
            "closure_forecast_reset_reentry_rebuild_persistence_status": "none",
            "closure_forecast_reset_reentry_rebuild_persistence_reason": "",
        }

    if (
        current_side == "clearance"
        and resolution_status == "cleared"
        and recent_pending_status in {"pending-support", "pending-caution"}
        and (
            freshness_status not in {"fresh", "mixed-age"}
            or decayed_clearance_rate < 0.50
            or persistence_status
            not in {
                "holding-clearance-rebuild",
                "sustained-clearance-rebuild",
            }
            or churn_status == "churn"
        )
    ):
        reset_reason = (
            "Restored clearance-side rebuilt posture has aged out enough that the stronger carry-forward has been withdrawn."
        )
        (
            transition_status,
            transition_reason,
            resolution_status,
            resolution_reason,
        ) = _restore_weaker_pending_posture(reset_reason)
        return {
            "closure_forecast_reset_reentry_rebuild_reset_status": "clearance-reset",
            "closure_forecast_reset_reentry_rebuild_reset_reason": reset_reason,
            "transition_closure_likely_outcome": "hold",
            "closure_forecast_hysteresis_status": "pending-clearance",
            "closure_forecast_hysteresis_reason": reset_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reset_reentry_rebuild_status": "none",
            "closure_forecast_reset_reentry_rebuild_reason": reset_reason,
            "closure_forecast_reset_reentry_rebuild_age_runs": 0,
            "closure_forecast_reset_reentry_rebuild_persistence_score": 0.0,
            "closure_forecast_reset_reentry_rebuild_persistence_status": "none",
            "closure_forecast_reset_reentry_rebuild_persistence_reason": "",
        }

    return {
        "closure_forecast_reset_reentry_rebuild_reset_status": "none",
        "closure_forecast_reset_reentry_rebuild_reset_reason": "",
        "transition_closure_likely_outcome": closure_likely_outcome,
        "closure_forecast_hysteresis_status": closure_hysteresis_status,
        "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
        "class_reweight_transition_status": transition_status,
        "class_reweight_transition_reason": transition_reason,
        "class_transition_resolution_status": resolution_status,
        "class_transition_resolution_reason": resolution_reason,
        "closure_forecast_reset_reentry_rebuild_status": rebuild_status,
        "closure_forecast_reset_reentry_rebuild_reason": rebuild_reason,
        "closure_forecast_reset_reentry_rebuild_age_runs": persistence_age_runs,
        "closure_forecast_reset_reentry_rebuild_persistence_score": persistence_score,
        "closure_forecast_reset_reentry_rebuild_persistence_status": persistence_status,
        "closure_forecast_reset_reentry_rebuild_persistence_reason": persistence_reason,
    }


def _closure_forecast_reset_reentry_rebuild_freshness_hotspots(
    resolution_targets: list[dict],
    *,
    mode: str,
) -> list[dict]:
    grouped: dict[str, dict] = {}
    for target in resolution_targets:
        class_key = _target_class_key(target)
        if not class_key:
            continue
        current = {
            "scope": "class",
            "label": class_key,
            "closure_forecast_reset_reentry_rebuild_freshness_status": target.get(
                "closure_forecast_reset_reentry_rebuild_freshness_status",
                "insufficient-data",
            ),
            "decayed_rebuilt_confirmation_reentry_rate": target.get(
                "decayed_rebuilt_confirmation_reentry_rate",
                0.0,
            ),
            "decayed_rebuilt_clearance_reentry_rate": target.get(
                "decayed_rebuilt_clearance_reentry_rate",
                0.0,
            ),
            "recent_reset_reentry_rebuild_signal_mix": target.get(
                "recent_reset_reentry_rebuild_signal_mix",
                "",
            ),
            "recent_reset_reentry_rebuild_persistence_path": target.get(
                "recent_reset_reentry_rebuild_persistence_path",
                "",
            ),
            "dominant_count": max(
                target.get("decayed_rebuilt_confirmation_reentry_rate", 0.0),
                target.get("decayed_rebuilt_clearance_reentry_rate", 0.0),
            ),
            "rebuild_event_count": len(
                [
                    part
                    for part in (
                        target.get("recent_reset_reentry_rebuild_persistence_path", "") or ""
                    ).split(" -> ")
                    if part
                ]
            ),
        }
        existing = grouped.get(class_key)
        if existing is None or current["dominant_count"] > existing["dominant_count"]:
            grouped[class_key] = current

    hotspots = list(grouped.values())
    if mode == "fresh":
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reset_reentry_rebuild_freshness_status")
            == "fresh"
            and item.get("dominant_count", 0.0) > 0.0
        ]
    else:
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reset_reentry_rebuild_freshness_status")
            == "stale"
            and item.get("dominant_count", 0.0) > 0.0
        ]
    hotspots.sort(
        key=lambda item: (
            -item.get("dominant_count", 0.0),
            -item.get("rebuild_event_count", 0),
            item.get("label", ""),
        )
    )
    return hotspots[:5]


def _closure_forecast_reset_reentry_rebuild_freshness_summary(
    primary_target: dict,
    stale_reset_reentry_rebuild_hotspots: list[dict],
    fresh_reset_reentry_rebuild_signal_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    freshness_status = primary_target.get(
        "closure_forecast_reset_reentry_rebuild_freshness_status",
        "insufficient-data",
    )
    if freshness_status == "fresh":
        return f"{label} still has recent rebuilt reset re-entry evidence that is current enough to keep the restored posture trusted."
    if freshness_status == "mixed-age":
        return f"{label} still has useful rebuilt reset re-entry memory, but the restored posture is no longer getting fully fresh reinforcement."
    if freshness_status == "stale":
        return f"{label} is leaning on older rebuilt reset re-entry strength more than fresh runs, so stronger restored posture should not keep carrying forward on memory alone."
    if fresh_reset_reentry_rebuild_signal_hotspots:
        hotspot = fresh_reset_reentry_rebuild_signal_hotspots[0]
        return (
            f"Fresh rebuilt reset re-entry evidence is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes can keep restored posture more safely than older carry-forward."
        )
    if stale_reset_reentry_rebuild_hotspots:
        hotspot = stale_reset_reentry_rebuild_hotspots[0]
        return (
            f"Older rebuilt reset re-entry strength is lingering most around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes should keep resetting restored posture when fresh follow-through stops."
        )
    return "Rebuilt reset re-entry memory is still too lightly exercised to say whether restored posture is being reinforced by fresh evidence or older carry-forward."


def _closure_forecast_reset_reentry_rebuild_reset_summary(
    primary_target: dict,
    stale_reset_reentry_rebuild_hotspots: list[dict],
    fresh_reset_reentry_rebuild_signal_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    reset_status = primary_target.get(
        "closure_forecast_reset_reentry_rebuild_reset_status",
        "none",
    )
    freshness_status = primary_target.get(
        "closure_forecast_reset_reentry_rebuild_freshness_status",
        "insufficient-data",
    )
    confirmation_rate = primary_target.get(
        "decayed_rebuilt_confirmation_reentry_rate",
        0.0,
    )
    clearance_rate = primary_target.get(
        "decayed_rebuilt_clearance_reentry_rate",
        0.0,
    )
    if reset_status == "confirmation-softened":
        return f"Restored confirmation-side rebuilt posture for {label} is still visible, but it is aging and has been stepped down from sustained strength."
    if reset_status == "clearance-softened":
        return f"Restored clearance-side rebuilt posture for {label} is still visible, but it is aging and has been stepped down from sustained strength."
    if reset_status == "confirmation-reset":
        return f"Restored confirmation-side rebuilt posture for {label} has aged out enough that the stronger carry-forward has been withdrawn."
    if reset_status == "clearance-reset":
        return f"Restored clearance-side rebuilt posture for {label} has aged out enough that the stronger carry-forward has been withdrawn."
    if reset_status == "blocked":
        return primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reset_reason",
            f"Local target instability still overrides healthy rebuilt freshness for {label}.",
        )
    if freshness_status == "fresh" and confirmation_rate >= clearance_rate:
        return f"Fresh rebuilt evidence for {label} is still reinforcing confirmation-side restored posture more than clearance pressure."
    if freshness_status == "fresh":
        return f"Fresh rebuilt evidence for {label} is still reinforcing clearance-side restored posture more than confirmation-side carry-forward."
    if freshness_status == "mixed-age":
        return f"Rebuilt posture for {label} is aging enough that it can keep holding, but it should no longer stay indefinitely at sustained strength."
    if stale_reset_reentry_rebuild_hotspots:
        hotspot = stale_reset_reentry_rebuild_hotspots[0]
        return (
            f"Rebuilt posture is aging out fastest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes should reset restored carry-forward instead of relying on older follow-through."
        )
    if fresh_reset_reentry_rebuild_signal_hotspots:
        hotspot = fresh_reset_reentry_rebuild_signal_hotspots[0]
        return (
            f"Fresh rebuilt follow-through is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes can preserve restored posture longer than aging carry-forward elsewhere."
        )
    return "No rebuilt reset re-entry reset is changing the current restored closure-forecast posture right now."


def _apply_reset_reentry_rebuild_freshness_and_reset(
    resolution_targets: list[dict],
    history: list[dict],
    *,
    current_generated_at: str,
    confidence_calibration: dict,
) -> dict:
    if not resolution_targets:
        return {
            "primary_target_closure_forecast_reset_reentry_rebuild_freshness_status": "insufficient-data",
            "primary_target_closure_forecast_reset_reentry_rebuild_freshness_reason": "",
            "closure_forecast_reset_reentry_rebuild_freshness_summary": "No reset re-entry rebuild freshness is recorded because there is no active target.",
            "primary_target_closure_forecast_reset_reentry_rebuild_reset_status": "none",
            "primary_target_closure_forecast_reset_reentry_rebuild_reset_reason": "",
            "closure_forecast_reset_reentry_rebuild_reset_summary": "No reset re-entry rebuild reset is recorded because there is no active target.",
            "stale_reset_reentry_rebuild_hotspots": [],
            "fresh_reset_reentry_rebuild_signal_hotspots": [],
            "closure_forecast_reset_reentry_rebuild_decay_window_runs": CLASS_RESET_REENTRY_REBUILD_FRESHNESS_WINDOW_RUNS,
        }

    current_primary_target = resolution_targets[0]
    current_bucket = _recommendation_bucket(current_primary_target)
    closure_forecast_events = _class_closure_forecast_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )
    transition_events = _class_transition_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )

    updated_targets: list[dict] = []
    for target in resolution_targets:
        freshness_status = "insufficient-data"
        freshness_reason = ""
        memory_weight = 0.0
        decayed_confirmation_rate = 0.0
        decayed_clearance_rate = 0.0
        signal_mix = ""
        reset_status = "none"
        reset_reason = ""
        closure_likely_outcome = target.get("transition_closure_likely_outcome", "none")
        closure_hysteresis_status = target.get("closure_forecast_hysteresis_status", "none")
        closure_hysteresis_reason = target.get("closure_forecast_hysteresis_reason", "")
        transition_status = target.get("class_reweight_transition_status", "none")
        transition_reason = target.get("class_reweight_transition_reason", "")
        resolution_status = target.get("class_transition_resolution_status", "none")
        resolution_reason = target.get("class_transition_resolution_reason", "")
        rebuild_status = target.get("closure_forecast_reset_reentry_rebuild_status", "none")
        rebuild_reason = target.get("closure_forecast_reset_reentry_rebuild_reason", "")
        persistence_age_runs = target.get("closure_forecast_reset_reentry_rebuild_age_runs", 0)
        persistence_score = target.get(
            "closure_forecast_reset_reentry_rebuild_persistence_score",
            0.0,
        )
        persistence_status = target.get(
            "closure_forecast_reset_reentry_rebuild_persistence_status",
            "none",
        )
        persistence_reason = target.get(
            "closure_forecast_reset_reentry_rebuild_persistence_reason",
            "",
        )

        if _recommendation_bucket(target) == current_bucket:
            transition_history_meta = _target_class_transition_history(
                target,
                transition_events,
            )
            freshness_meta = _closure_forecast_reset_reentry_rebuild_freshness_for_target(
                target,
                closure_forecast_events,
            )
            freshness_status = freshness_meta[
                "closure_forecast_reset_reentry_rebuild_freshness_status"
            ]
            freshness_reason = freshness_meta[
                "closure_forecast_reset_reentry_rebuild_freshness_reason"
            ]
            memory_weight = freshness_meta[
                "closure_forecast_reset_reentry_rebuild_memory_weight"
            ]
            decayed_confirmation_rate = freshness_meta[
                "decayed_rebuilt_confirmation_reentry_rate"
            ]
            decayed_clearance_rate = freshness_meta[
                "decayed_rebuilt_clearance_reentry_rate"
            ]
            signal_mix = freshness_meta["recent_reset_reentry_rebuild_signal_mix"]
            control_updates = _apply_reset_reentry_rebuild_freshness_reset_control(
                target,
                freshness_meta=freshness_meta,
                transition_history_meta=transition_history_meta,
                closure_likely_outcome=closure_likely_outcome,
                closure_hysteresis_status=closure_hysteresis_status,
                closure_hysteresis_reason=closure_hysteresis_reason,
                transition_status=transition_status,
                transition_reason=transition_reason,
                resolution_status=resolution_status,
                resolution_reason=resolution_reason,
                rebuild_status=rebuild_status,
                rebuild_reason=rebuild_reason,
                persistence_age_runs=persistence_age_runs,
                persistence_score=persistence_score,
                persistence_status=persistence_status,
                persistence_reason=persistence_reason,
            )
            reset_status = control_updates[
                "closure_forecast_reset_reentry_rebuild_reset_status"
            ]
            reset_reason = control_updates[
                "closure_forecast_reset_reentry_rebuild_reset_reason"
            ]
            closure_likely_outcome = control_updates["transition_closure_likely_outcome"]
            closure_hysteresis_status = control_updates[
                "closure_forecast_hysteresis_status"
            ]
            closure_hysteresis_reason = control_updates[
                "closure_forecast_hysteresis_reason"
            ]
            transition_status = control_updates["class_reweight_transition_status"]
            transition_reason = control_updates["class_reweight_transition_reason"]
            resolution_status = control_updates["class_transition_resolution_status"]
            resolution_reason = control_updates["class_transition_resolution_reason"]
            rebuild_status = control_updates["closure_forecast_reset_reentry_rebuild_status"]
            rebuild_reason = control_updates["closure_forecast_reset_reentry_rebuild_reason"]
            persistence_age_runs = control_updates[
                "closure_forecast_reset_reentry_rebuild_age_runs"
            ]
            persistence_score = control_updates[
                "closure_forecast_reset_reentry_rebuild_persistence_score"
            ]
            persistence_status = control_updates[
                "closure_forecast_reset_reentry_rebuild_persistence_status"
            ]
            persistence_reason = control_updates[
                "closure_forecast_reset_reentry_rebuild_persistence_reason"
            ]

        updated_targets.append(
            {
                **target,
                "closure_forecast_reset_reentry_rebuild_freshness_status": freshness_status,
                "closure_forecast_reset_reentry_rebuild_freshness_reason": freshness_reason,
                "closure_forecast_reset_reentry_rebuild_memory_weight": memory_weight,
                "decayed_rebuilt_confirmation_reentry_rate": decayed_confirmation_rate,
                "decayed_rebuilt_clearance_reentry_rate": decayed_clearance_rate,
                "recent_reset_reentry_rebuild_signal_mix": signal_mix,
                "closure_forecast_reset_reentry_rebuild_reset_status": reset_status,
                "closure_forecast_reset_reentry_rebuild_reset_reason": reset_reason,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reset_reentry_rebuild_status": rebuild_status,
                "closure_forecast_reset_reentry_rebuild_reason": rebuild_reason,
                "closure_forecast_reset_reentry_rebuild_age_runs": persistence_age_runs,
                "closure_forecast_reset_reentry_rebuild_persistence_score": persistence_score,
                "closure_forecast_reset_reentry_rebuild_persistence_status": persistence_status,
                "closure_forecast_reset_reentry_rebuild_persistence_reason": persistence_reason,
            }
        )

    resolution_targets[:] = updated_targets
    primary_target = resolution_targets[0]
    stale_reset_reentry_rebuild_hotspots = (
        _closure_forecast_reset_reentry_rebuild_freshness_hotspots(
            resolution_targets,
            mode="stale",
        )
    )
    fresh_reset_reentry_rebuild_signal_hotspots = (
        _closure_forecast_reset_reentry_rebuild_freshness_hotspots(
            resolution_targets,
            mode="fresh",
        )
    )
    return {
        "primary_target_closure_forecast_reset_reentry_rebuild_freshness_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_freshness_status",
            "insufficient-data",
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_freshness_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_freshness_reason",
            "",
        ),
        "closure_forecast_reset_reentry_rebuild_freshness_summary": _closure_forecast_reset_reentry_rebuild_freshness_summary(
            primary_target,
            stale_reset_reentry_rebuild_hotspots,
            fresh_reset_reentry_rebuild_signal_hotspots,
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_reset_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reset_status",
            "none",
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_reset_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reset_reason",
            "",
        ),
        "closure_forecast_reset_reentry_rebuild_reset_summary": _closure_forecast_reset_reentry_rebuild_reset_summary(
            primary_target,
            stale_reset_reentry_rebuild_hotspots,
            fresh_reset_reentry_rebuild_signal_hotspots,
        ),
        "stale_reset_reentry_rebuild_hotspots": stale_reset_reentry_rebuild_hotspots,
        "fresh_reset_reentry_rebuild_signal_hotspots": fresh_reset_reentry_rebuild_signal_hotspots,
        "closure_forecast_reset_reentry_rebuild_decay_window_runs": CLASS_RESET_REENTRY_REBUILD_FRESHNESS_WINDOW_RUNS,
    }


def _class_closure_forecast_events(
    history: list[dict],
    *,
    current_primary_target: dict,
    current_generated_at: str,
) -> list[dict]:
    events: list[dict] = []
    if current_primary_target and current_primary_target.get("trust_policy"):
        events.append(
            {
                "key": _queue_identity(current_primary_target),
                "class_key": _target_class_key(current_primary_target),
                "label": _target_label(current_primary_target),
                "generated_at": current_generated_at or "",
                "closure_forecast_reweight_score": current_primary_target.get("closure_forecast_reweight_score", 0.0),
                "closure_forecast_reweight_direction": current_primary_target.get("closure_forecast_reweight_direction", "neutral"),
                "transition_closure_likely_outcome": current_primary_target.get("transition_closure_likely_outcome", "none"),
                "class_reweight_transition_status": current_primary_target.get("class_reweight_transition_status", "none"),
                "class_transition_resolution_status": current_primary_target.get("class_transition_resolution_status", "none"),
                "closure_forecast_reweight_effect": current_primary_target.get("closure_forecast_reweight_effect", "none"),
                "closure_forecast_hysteresis_status": current_primary_target.get("closure_forecast_hysteresis_status", "none"),
                "closure_forecast_momentum_status": current_primary_target.get("closure_forecast_momentum_status", "insufficient-data"),
                "closure_forecast_stability_status": current_primary_target.get("closure_forecast_stability_status", "watch"),
                "closure_forecast_freshness_status": current_primary_target.get("closure_forecast_freshness_status", "insufficient-data"),
                "closure_forecast_decay_status": current_primary_target.get("closure_forecast_decay_status", "none"),
                "closure_forecast_refresh_recovery_status": current_primary_target.get("closure_forecast_refresh_recovery_status", "none"),
                "closure_forecast_reacquisition_status": current_primary_target.get("closure_forecast_reacquisition_status", "none"),
                "closure_forecast_reacquisition_persistence_status": current_primary_target.get(
                    "closure_forecast_reacquisition_persistence_status",
                    "none",
                ),
                "closure_forecast_recovery_churn_status": current_primary_target.get(
                    "closure_forecast_recovery_churn_status",
                    "none",
                ),
                "closure_forecast_reacquisition_freshness_status": current_primary_target.get(
                    "closure_forecast_reacquisition_freshness_status",
                    "insufficient-data",
                ),
                "closure_forecast_persistence_reset_status": current_primary_target.get(
                    "closure_forecast_persistence_reset_status",
                    "none",
                ),
                "closure_forecast_reset_refresh_recovery_status": current_primary_target.get(
                    "closure_forecast_reset_refresh_recovery_status",
                    "none",
                ),
                "closure_forecast_reset_reentry_status": current_primary_target.get(
                    "closure_forecast_reset_reentry_status",
                    "none",
                ),
                "closure_forecast_reset_reentry_persistence_status": current_primary_target.get(
                    "closure_forecast_reset_reentry_persistence_status",
                    "none",
                ),
                "closure_forecast_reset_reentry_churn_status": current_primary_target.get(
                    "closure_forecast_reset_reentry_churn_status",
                    "none",
                ),
                "closure_forecast_reset_reentry_freshness_status": current_primary_target.get(
                    "closure_forecast_reset_reentry_freshness_status",
                    "insufficient-data",
                ),
                "closure_forecast_reset_reentry_reset_status": current_primary_target.get(
                    "closure_forecast_reset_reentry_reset_status",
                    "none",
                ),
                "closure_forecast_reset_reentry_refresh_recovery_status": current_primary_target.get(
                    "closure_forecast_reset_reentry_refresh_recovery_status",
                    "none",
                ),
                "closure_forecast_reset_reentry_rebuild_status": current_primary_target.get(
                    "closure_forecast_reset_reentry_rebuild_status",
                    "none",
                ),
                "closure_forecast_reset_reentry_rebuild_persistence_status": current_primary_target.get(
                    "closure_forecast_reset_reentry_rebuild_persistence_status",
                    "none",
                ),
                "closure_forecast_reset_reentry_rebuild_churn_status": current_primary_target.get(
                    "closure_forecast_reset_reentry_rebuild_churn_status",
                    "none",
                ),
                "closure_forecast_reset_reentry_rebuild_freshness_status": current_primary_target.get(
                    "closure_forecast_reset_reentry_rebuild_freshness_status",
                    "insufficient-data",
                ),
                "closure_forecast_reset_reentry_rebuild_reset_status": current_primary_target.get(
                    "closure_forecast_reset_reentry_rebuild_reset_status",
                    "none",
                ),
            }
        )
    for entry in history[: HISTORY_WINDOW_RUNS - 1]:
        summary = entry.get("operator_summary") or {}
        primary_target = summary.get("primary_target") or {}
        if not primary_target:
            continue
        direction = summary.get(
            "primary_target_closure_forecast_reweight_direction",
            primary_target.get("closure_forecast_reweight_direction", "neutral"),
        )
        score = summary.get(
            "primary_target_closure_forecast_reweight_score",
            primary_target.get("closure_forecast_reweight_score", 0.0),
        )
        if score is None and not direction:
            continue
        events.append(
            {
                "key": _queue_identity(primary_target),
                "class_key": _target_class_key(primary_target),
                "label": _target_label(primary_target),
                "generated_at": entry.get("generated_at", ""),
                "closure_forecast_reweight_score": score or 0.0,
                "closure_forecast_reweight_direction": direction or "neutral",
                "transition_closure_likely_outcome": summary.get(
                    "primary_target_transition_closure_likely_outcome",
                    primary_target.get("transition_closure_likely_outcome", "none"),
                ),
                "class_reweight_transition_status": summary.get(
                    "primary_target_class_reweight_transition_status",
                    primary_target.get("class_reweight_transition_status", "none"),
                ),
                "class_transition_resolution_status": summary.get(
                    "primary_target_class_transition_resolution_status",
                    primary_target.get("class_transition_resolution_status", "none"),
                ),
                "closure_forecast_reweight_effect": primary_target.get("closure_forecast_reweight_effect", "none"),
                "closure_forecast_hysteresis_status": summary.get(
                    "primary_target_closure_forecast_hysteresis_status",
                    primary_target.get("closure_forecast_hysteresis_status", "none"),
                ),
                "closure_forecast_momentum_status": summary.get(
                    "primary_target_closure_forecast_momentum_status",
                    primary_target.get("closure_forecast_momentum_status", "insufficient-data"),
                ),
                "closure_forecast_stability_status": summary.get(
                    "primary_target_closure_forecast_stability_status",
                    primary_target.get("closure_forecast_stability_status", "watch"),
                ),
                "closure_forecast_freshness_status": summary.get(
                    "primary_target_closure_forecast_freshness_status",
                    primary_target.get("closure_forecast_freshness_status", "insufficient-data"),
                ),
                "closure_forecast_decay_status": summary.get(
                    "primary_target_closure_forecast_decay_status",
                    primary_target.get("closure_forecast_decay_status", "none"),
                ),
                "closure_forecast_refresh_recovery_status": summary.get(
                    "primary_target_closure_forecast_refresh_recovery_status",
                    primary_target.get("closure_forecast_refresh_recovery_status", "none"),
                ),
                "closure_forecast_reacquisition_status": summary.get(
                    "primary_target_closure_forecast_reacquisition_status",
                    primary_target.get("closure_forecast_reacquisition_status", "none"),
                ),
                "closure_forecast_reacquisition_persistence_status": summary.get(
                    "primary_target_closure_forecast_reacquisition_persistence_status",
                    primary_target.get("closure_forecast_reacquisition_persistence_status", "none"),
                ),
                "closure_forecast_recovery_churn_status": summary.get(
                    "primary_target_closure_forecast_recovery_churn_status",
                    primary_target.get("closure_forecast_recovery_churn_status", "none"),
                ),
                "closure_forecast_reacquisition_freshness_status": summary.get(
                    "primary_target_closure_forecast_reacquisition_freshness_status",
                    primary_target.get(
                        "closure_forecast_reacquisition_freshness_status",
                        "insufficient-data",
                    ),
                ),
                "closure_forecast_persistence_reset_status": summary.get(
                    "primary_target_closure_forecast_persistence_reset_status",
                    primary_target.get("closure_forecast_persistence_reset_status", "none"),
                ),
                "closure_forecast_reset_refresh_recovery_status": summary.get(
                    "primary_target_closure_forecast_reset_refresh_recovery_status",
                    primary_target.get("closure_forecast_reset_refresh_recovery_status", "none"),
                ),
                "closure_forecast_reset_reentry_status": summary.get(
                    "primary_target_closure_forecast_reset_reentry_status",
                    primary_target.get("closure_forecast_reset_reentry_status", "none"),
                ),
                "closure_forecast_reset_reentry_persistence_status": summary.get(
                    "primary_target_closure_forecast_reset_reentry_persistence_status",
                    primary_target.get(
                        "closure_forecast_reset_reentry_persistence_status",
                        "none",
                    ),
                ),
                "closure_forecast_reset_reentry_churn_status": summary.get(
                    "primary_target_closure_forecast_reset_reentry_churn_status",
                    primary_target.get(
                        "closure_forecast_reset_reentry_churn_status",
                        "none",
                    ),
                ),
                "closure_forecast_reset_reentry_freshness_status": summary.get(
                    "primary_target_closure_forecast_reset_reentry_freshness_status",
                    primary_target.get(
                        "closure_forecast_reset_reentry_freshness_status",
                        "insufficient-data",
                    ),
                ),
                "closure_forecast_reset_reentry_reset_status": summary.get(
                    "primary_target_closure_forecast_reset_reentry_reset_status",
                    primary_target.get(
                        "closure_forecast_reset_reentry_reset_status",
                        "none",
                    ),
                ),
                "closure_forecast_reset_reentry_refresh_recovery_status": summary.get(
                    "primary_target_closure_forecast_reset_reentry_refresh_recovery_status",
                    primary_target.get(
                        "closure_forecast_reset_reentry_refresh_recovery_status",
                        "none",
                    ),
                ),
                "closure_forecast_reset_reentry_rebuild_status": summary.get(
                    "primary_target_closure_forecast_reset_reentry_rebuild_status",
                    primary_target.get(
                        "closure_forecast_reset_reentry_rebuild_status",
                        "none",
                    ),
                ),
                "closure_forecast_reset_reentry_rebuild_persistence_status": summary.get(
                    "primary_target_closure_forecast_reset_reentry_rebuild_persistence_status",
                    primary_target.get(
                        "closure_forecast_reset_reentry_rebuild_persistence_status",
                        "none",
                    ),
                ),
                "closure_forecast_reset_reentry_rebuild_churn_status": summary.get(
                    "primary_target_closure_forecast_reset_reentry_rebuild_churn_status",
                    primary_target.get(
                        "closure_forecast_reset_reentry_rebuild_churn_status",
                        "none",
                    ),
                ),
                "closure_forecast_reset_reentry_rebuild_freshness_status": summary.get(
                    "primary_target_closure_forecast_reset_reentry_rebuild_freshness_status",
                    primary_target.get(
                        "closure_forecast_reset_reentry_rebuild_freshness_status",
                        "insufficient-data",
                    ),
                ),
                "closure_forecast_reset_reentry_rebuild_reset_status": summary.get(
                    "primary_target_closure_forecast_reset_reentry_rebuild_reset_status",
                    primary_target.get(
                        "closure_forecast_reset_reentry_rebuild_reset_status",
                        "none",
                    ),
                ),
            }
        )
    return sorted(events, key=lambda item: item.get("generated_at", ""), reverse=True)


def _target_closure_forecast_history(target: dict, closure_forecast_events: list[dict]) -> dict:
    class_key = _target_class_key(target)
    matching_events = [
        event for event in closure_forecast_events if event.get("class_key") == class_key
    ][:CLASS_CLOSURE_FORECAST_TRANSITION_WINDOW_RUNS]
    signals = [_closure_forecast_signal_from_event(event) for event in matching_events]
    relevant_signals = [signal for signal in signals if abs(signal) >= 0.05]
    weighted_total = 0.0
    weight_sum = 0.0
    for index, signal in enumerate(signals):
        weight = (1.0, 0.8, 0.6, 0.4)[min(index, CLASS_CLOSURE_FORECAST_TRANSITION_WINDOW_RUNS - 1)]
        weighted_total += signal * weight
        weight_sum += weight
    momentum_score = _clamp_round(weighted_total / max(weight_sum, 1.0), lower=-0.95, upper=0.95)
    directions = [
        _normalized_closure_forecast_direction(
            event.get("closure_forecast_reweight_direction", "neutral"),
            event.get("closure_forecast_reweight_score", 0.0),
        )
        for event in matching_events
    ]
    flip_count = _class_direction_flip_count(directions)
    current_direction = directions[0] if directions else "neutral"
    earlier_majority = _closure_forecast_direction_majority(directions[1:])
    positive_count = sum(1 for signal in relevant_signals if signal > 0)
    negative_count = sum(1 for signal in relevant_signals if signal < 0)

    if len(relevant_signals) < 2:
        momentum_status = "insufficient-data"
    elif flip_count >= 2:
        momentum_status = "unstable"
    elif _closure_forecast_direction_reversing(current_direction, earlier_majority):
        momentum_status = "reversing"
    elif positive_count >= 2 and momentum_score >= 0.20:
        momentum_status = "sustained-confirmation"
    elif negative_count >= 2 and momentum_score <= -0.20:
        momentum_status = "sustained-clearance"
    else:
        momentum_status = "building"

    if flip_count >= 2:
        stability_status = "oscillating"
    elif flip_count == 1 or momentum_status in {"building", "insufficient-data", "reversing"}:
        stability_status = "watch"
    else:
        stability_status = "stable"

    return {
        "closure_forecast_momentum_score": momentum_score,
        "closure_forecast_momentum_status": momentum_status,
        "closure_forecast_stability_status": stability_status,
        "recent_closure_forecast_path": " -> ".join(directions) if directions else "",
        "closure_forecast_direction_flip_count": flip_count,
    }


def _closure_forecast_freshness_for_target(target: dict, closure_forecast_events: list[dict]) -> dict:
    class_key = _target_class_key(target)
    class_events = [event for event in closure_forecast_events if event.get("class_key") == class_key]
    relevant_events: list[dict] = []
    for event in class_events:
        if not _closure_forecast_event_has_evidence(event):
            continue
        relevant_events.append(event)
        if len(relevant_events) >= HISTORY_WINDOW_RUNS:
            break

    weighted_forecast_evidence_count = 0.0
    weighted_confirmation_like = 0.0
    weighted_clearance_like = 0.0
    recent_forecast_weight = 0.0
    recent_signals = [
        _closure_forecast_event_signal_label(event)
        for event in relevant_events[:CLASS_CLOSURE_FORECAST_FRESHNESS_WINDOW_RUNS]
    ]
    for index, event in enumerate(relevant_events):
        weight = CLASS_MEMORY_RECENCY_WEIGHTS[min(index, HISTORY_WINDOW_RUNS - 1)]
        weighted_forecast_evidence_count += weight
        if index < CLASS_CLOSURE_FORECAST_FRESHNESS_WINDOW_RUNS:
            recent_forecast_weight += weight
        if _closure_forecast_event_is_confirmation_like(event):
            weighted_confirmation_like += weight
        if _closure_forecast_event_is_clearance_like(event):
            weighted_clearance_like += weight

    recent_window_weight_share = recent_forecast_weight / max(weighted_forecast_evidence_count, 1.0)
    freshness_status = _closure_forecast_freshness_status(
        weighted_forecast_evidence_count,
        recent_window_weight_share,
    )
    decayed_confirmation_rate = weighted_confirmation_like / max(weighted_forecast_evidence_count, 1.0)
    decayed_clearance_rate = weighted_clearance_like / max(weighted_forecast_evidence_count, 1.0)
    return {
        "closure_forecast_freshness_status": freshness_status,
        "closure_forecast_freshness_reason": _closure_forecast_freshness_reason(
            freshness_status,
            weighted_forecast_evidence_count,
            recent_window_weight_share,
            decayed_confirmation_rate,
            decayed_clearance_rate,
        ),
        "closure_forecast_memory_weight": round(recent_window_weight_share, 2),
        "decayed_confirmation_forecast_rate": round(decayed_confirmation_rate, 2),
        "decayed_clearance_forecast_rate": round(decayed_clearance_rate, 2),
        "recent_closure_forecast_signal_mix": _recent_closure_forecast_signal_mix(
            weighted_forecast_evidence_count,
            weighted_confirmation_like,
            weighted_clearance_like,
            recent_window_weight_share,
        ),
        "recent_closure_forecast_path": " -> ".join(recent_signals),
    }


def _closure_forecast_event_has_evidence(event: dict) -> bool:
    score = float(event.get("closure_forecast_reweight_score", 0.0) or 0.0)
    direction = _normalized_closure_forecast_direction(
        event.get("closure_forecast_reweight_direction", "neutral"),
        score,
    )
    likely_outcome = event.get("transition_closure_likely_outcome", "none") or "none"
    hysteresis_status = event.get("closure_forecast_hysteresis_status", "none") or "none"
    return (
        abs(score) >= 0.05
        or direction in {"supporting-confirmation", "supporting-clearance"}
        or likely_outcome in {"confirm-soon", "clear-risk", "expire-risk"}
        or hysteresis_status
        in {
            "pending-confirmation",
            "pending-clearance",
            "confirmed-confirmation",
            "confirmed-clearance",
        }
    )


def _closure_forecast_event_is_confirmation_like(event: dict) -> bool:
    score = float(event.get("closure_forecast_reweight_score", 0.0) or 0.0)
    direction = _normalized_closure_forecast_direction(
        event.get("closure_forecast_reweight_direction", "neutral"),
        score,
    )
    return (
        direction == "supporting-confirmation"
        or event.get("transition_closure_likely_outcome", "none") == "confirm-soon"
        or event.get("closure_forecast_hysteresis_status", "none")
        in {"pending-confirmation", "confirmed-confirmation"}
    )


def _closure_forecast_event_is_clearance_like(event: dict) -> bool:
    score = float(event.get("closure_forecast_reweight_score", 0.0) or 0.0)
    direction = _normalized_closure_forecast_direction(
        event.get("closure_forecast_reweight_direction", "neutral"),
        score,
    )
    return (
        direction == "supporting-clearance"
        or event.get("transition_closure_likely_outcome", "none") in {"clear-risk", "expire-risk"}
        or event.get("closure_forecast_hysteresis_status", "none")
        in {"pending-clearance", "confirmed-clearance"}
    )


def _closure_forecast_event_signal_label(event: dict) -> str:
    if _closure_forecast_event_is_confirmation_like(event):
        return "confirmation-like"
    if _closure_forecast_event_is_clearance_like(event):
        return "clearance-like"
    return "neutral"


def _closure_forecast_reacquisition_freshness_for_target(
    target: dict,
    closure_forecast_events: list[dict],
) -> dict:
    class_key = _target_class_key(target)
    class_events = [event for event in closure_forecast_events if event.get("class_key") == class_key]
    relevant_events: list[dict] = []
    for event in class_events:
        if not _reacquisition_event_has_evidence(event):
            continue
        relevant_events.append(event)
        if len(relevant_events) >= HISTORY_WINDOW_RUNS:
            break

    weighted_reacquisition_evidence_count = 0.0
    weighted_confirmation_like = 0.0
    weighted_clearance_like = 0.0
    recent_reacquisition_weight = 0.0
    recent_signals = [
        _reacquisition_event_signal_label(event)
        for event in relevant_events[:CLASS_REACQUISITION_FRESHNESS_WINDOW_RUNS]
    ]
    current_side = _closure_forecast_reacquisition_side_from_status(
        target.get("closure_forecast_reacquisition_persistence_status", "none")
    )
    if current_side == "none":
        current_side = _closure_forecast_reacquisition_side_from_event(
            {
                "closure_forecast_reacquisition_status": target.get(
                    "closure_forecast_reacquisition_status",
                    "none",
                ),
                "closure_forecast_refresh_recovery_status": target.get(
                    "closure_forecast_refresh_recovery_status",
                    "none",
                ),
            }
        )
    for index, event in enumerate(relevant_events):
        weight = CLASS_MEMORY_RECENCY_WEIGHTS[min(index, HISTORY_WINDOW_RUNS - 1)]
        weighted_reacquisition_evidence_count += weight
        event_side = _closure_forecast_reacquisition_side_from_event(event)
        if (
            index < CLASS_REACQUISITION_FRESHNESS_WINDOW_RUNS
            and event_side == current_side
        ):
            recent_reacquisition_weight += weight
        if _reacquisition_event_is_confirmation_like(event):
            weighted_confirmation_like += weight
        if _reacquisition_event_is_clearance_like(event):
            weighted_clearance_like += weight

    recent_window_weight_share = recent_reacquisition_weight / max(
        weighted_reacquisition_evidence_count,
        1.0,
    )
    freshness_status = _closure_forecast_freshness_status(
        weighted_reacquisition_evidence_count,
        recent_window_weight_share,
    )
    decayed_confirmation_rate = weighted_confirmation_like / max(
        weighted_reacquisition_evidence_count,
        1.0,
    )
    decayed_clearance_rate = weighted_clearance_like / max(
        weighted_reacquisition_evidence_count,
        1.0,
    )
    return {
        "closure_forecast_reacquisition_freshness_status": freshness_status,
        "closure_forecast_reacquisition_freshness_reason": _closure_forecast_reacquisition_freshness_reason(
            freshness_status,
            weighted_reacquisition_evidence_count,
            recent_window_weight_share,
            decayed_confirmation_rate,
            decayed_clearance_rate,
        ),
        "closure_forecast_reacquisition_memory_weight": round(recent_window_weight_share, 2),
        "decayed_reacquired_confirmation_rate": round(decayed_confirmation_rate, 2),
        "decayed_reacquired_clearance_rate": round(decayed_clearance_rate, 2),
        "recent_reacquisition_signal_mix": _recent_reacquisition_signal_mix(
            weighted_reacquisition_evidence_count,
            weighted_confirmation_like,
            weighted_clearance_like,
            recent_window_weight_share,
        ),
        "recent_reacquisition_signal_path": " -> ".join(recent_signals),
        "has_fresh_aligned_recent_evidence": any(
            event.get("closure_forecast_freshness_status", "insufficient-data") == "fresh"
            and _closure_forecast_reacquisition_side_from_event(event) == current_side
            for event in relevant_events[:2]
        ),
    }


def _reacquisition_event_has_evidence(event: dict) -> bool:
    return (
        _reacquisition_event_is_confirmation_like(event)
        or _reacquisition_event_is_clearance_like(event)
        or event.get("closure_forecast_recovery_churn_status", "none") in {"watch", "churn", "blocked"}
    )


def _reacquisition_event_is_confirmation_like(event: dict) -> bool:
    return (
        event.get("closure_forecast_reacquisition_status", "none")
        in {"pending-confirmation-reacquisition", "reacquired-confirmation"}
        or event.get("closure_forecast_reacquisition_persistence_status", "none")
        in {"just-reacquired", "holding-confirmation", "sustained-confirmation"}
        or event.get("closure_forecast_hysteresis_status", "none")
        in {"pending-confirmation", "confirmed-confirmation"}
        or event.get("transition_closure_likely_outcome", "none") == "confirm-soon"
    )


def _reacquisition_event_is_clearance_like(event: dict) -> bool:
    return (
        event.get("closure_forecast_reacquisition_status", "none")
        in {"pending-clearance-reacquisition", "reacquired-clearance"}
        or event.get("closure_forecast_reacquisition_persistence_status", "none")
        in {"holding-clearance", "sustained-clearance"}
        or event.get("closure_forecast_hysteresis_status", "none")
        in {"pending-clearance", "confirmed-clearance"}
        or event.get("transition_closure_likely_outcome", "none")
        in {"clear-risk", "expire-risk"}
    )


def _reacquisition_event_signal_label(event: dict) -> str:
    if _reacquisition_event_is_confirmation_like(event):
        return "confirmation-like"
    if _reacquisition_event_is_clearance_like(event):
        return "clearance-like"
    return "neutral"


def _closure_forecast_reacquisition_freshness_reason(
    freshness_status: str,
    weighted_reacquisition_evidence_count: float,
    recent_window_weight_share: float,
    decayed_confirmation_rate: float,
    decayed_clearance_rate: float,
) -> str:
    if freshness_status == "fresh":
        return (
            "Recent reacquired closure-forecast evidence is still current enough to trust, with "
            f"{recent_window_weight_share:.0%} of the weighted signal coming from the latest "
            f"{CLASS_REACQUISITION_FRESHNESS_WINDOW_RUNS} runs."
        )
    if freshness_status == "mixed-age":
        return (
            "Reacquired closure-forecast memory is still useful, but it is partly aging: "
            f"{recent_window_weight_share:.0%} of the weighted signal is recent and the rest is older carry-forward."
        )
    if freshness_status == "stale":
        return (
            "Older reacquired forecast strength is carrying more of the signal than recent runs, so it should not keep stronger posture alive on memory alone."
        )
    return (
        "Reacquired closure-forecast memory is still too lightly exercised to judge freshness, with "
        f"{weighted_reacquisition_evidence_count:.2f} weighted reacquisition run(s), "
        f"{decayed_confirmation_rate:.0%} confirmation-like signal, and {decayed_clearance_rate:.0%} clearance-like signal."
    )


def _recent_reacquisition_signal_mix(
    weighted_reacquisition_evidence_count: float,
    weighted_confirmation_like: float,
    weighted_clearance_like: float,
    recent_window_weight_share: float,
) -> str:
    return (
        f"{weighted_reacquisition_evidence_count:.2f} weighted reacquisition run(s) with "
        f"{weighted_confirmation_like:.2f} confirmation-like, {weighted_clearance_like:.2f} clearance-like, "
        f"and {recent_window_weight_share:.0%} of the signal from the freshest runs."
    )


def _closure_forecast_freshness_status(
    weighted_forecast_evidence_count: float,
    recent_window_weight_share: float,
) -> str:
    if weighted_forecast_evidence_count < 2.0:
        return "insufficient-data"
    if recent_window_weight_share >= 0.60:
        return "fresh"
    if recent_window_weight_share >= 0.35:
        return "mixed-age"
    return "stale"


def _closure_forecast_freshness_reason(
    freshness_status: str,
    weighted_forecast_evidence_count: float,
    recent_window_weight_share: float,
    decayed_confirmation_rate: float,
    decayed_clearance_rate: float,
) -> str:
    if freshness_status == "fresh":
        return (
            "Recent closure-forecast evidence is still current enough to trust, with "
            f"{recent_window_weight_share:.0%} of the weighted signal coming from the latest {CLASS_CLOSURE_FORECAST_FRESHNESS_WINDOW_RUNS} runs."
        )
    if freshness_status == "mixed-age":
        return (
            "Closure-forecast memory is still useful, but it is partly aging: "
            f"{recent_window_weight_share:.0%} of the weighted signal is recent and the rest is older carry-forward."
        )
    if freshness_status == "stale":
        return (
            "Older closure-forecast momentum is carrying more of the signal than recent runs, so it should not dominate the current forecast."
        )
    return (
        "Closure-forecast memory is still too lightly exercised to judge freshness, with "
        f"{weighted_forecast_evidence_count:.2f} weighted forecast run(s), "
        f"{decayed_confirmation_rate:.0%} confirmation-like signal, and {decayed_clearance_rate:.0%} clearance-like signal."
    )


def _recent_closure_forecast_signal_mix(
    weighted_forecast_evidence_count: float,
    weighted_confirmation_like: float,
    weighted_clearance_like: float,
    recent_window_weight_share: float,
) -> str:
    return (
        f"{weighted_forecast_evidence_count:.2f} weighted forecast run(s) with "
        f"{weighted_confirmation_like:.2f} confirmation-like, {weighted_clearance_like:.2f} clearance-like, "
        f"and {recent_window_weight_share:.0%} of the signal from the freshest runs."
    )


def _closure_forecast_signal_from_event(event: dict) -> float:
    score = float(event.get("closure_forecast_reweight_score", 0.0) or 0.0)
    direction = _normalized_closure_forecast_direction(
        event.get("closure_forecast_reweight_direction", "neutral"),
        score,
    )
    if direction == "supporting-confirmation":
        return abs(score) if abs(score) >= 0.05 else 0.05
    if direction == "supporting-clearance":
        return -abs(score) if abs(score) >= 0.05 else -0.05
    return _clamp_round(score, lower=-0.19, upper=0.19)


def _normalized_closure_forecast_direction(direction: str, score: float) -> str:
    if direction in {"supporting-confirmation", "supporting-clearance", "neutral"}:
        return direction
    if score >= 0.20:
        return "supporting-confirmation"
    if score <= -0.20:
        return "supporting-clearance"
    return "neutral"


def _closure_forecast_direction_majority(directions: list[str]) -> str:
    confirmation_count = sum(1 for direction in directions if direction == "supporting-confirmation")
    clearance_count = sum(1 for direction in directions if direction == "supporting-clearance")
    if confirmation_count > clearance_count:
        return "supporting-confirmation"
    if clearance_count > confirmation_count:
        return "supporting-clearance"
    return "neutral"


def _closure_forecast_direction_reversing(current_direction: str, earlier_majority: str) -> bool:
    if current_direction == "neutral" or earlier_majority == "neutral":
        return False
    return current_direction != earlier_majority


def _apply_closure_forecast_hysteresis_control(
    target: dict,
    *,
    history_meta: dict,
    transition_history_meta: dict,
    trust_policy: str,
    trust_policy_reason: str,
    transition_status: str,
    transition_reason: str,
    resolution_status: str,
    resolution_reason: str,
    pending_debt_status: str,
    pending_debt_reason: str,
    policy_debt_status: str,
    policy_debt_reason: str,
    class_normalization_status: str,
    class_normalization_reason: str,
    closure_likely_outcome: str,
) -> tuple[str, str, str, str, str, str, str, str, str, str, str, str, str, str, str]:
    momentum_status = history_meta.get("closure_forecast_momentum_status", "insufficient-data")
    stability_status = history_meta.get("closure_forecast_stability_status", "watch")
    direction = target.get("closure_forecast_reweight_direction", "neutral")
    freshness_status = target.get("pending_debt_freshness_status", "insufficient-data")
    local_noise = _target_specific_normalization_noise(target, transition_history_meta)
    transition_age_runs = int(target.get("class_transition_age_runs", 0) or 0)
    recent_pending_status = transition_history_meta.get("recent_pending_status", "none")
    reweight_effect = target.get("closure_forecast_reweight_effect", "none")

    if local_noise and direction == "supporting-confirmation":
        blocked_reason = "Local target instability is preventing positive forecast strengthening."
        if closure_likely_outcome == "confirm-soon":
            closure_likely_outcome = "hold"
        return (
            "blocked",
            blocked_reason,
            closure_likely_outcome,
            transition_status,
            transition_reason,
            resolution_status,
            resolution_reason,
            trust_policy,
            trust_policy_reason,
            pending_debt_status,
            pending_debt_reason,
            policy_debt_status,
            policy_debt_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    if (
        resolution_status == "cleared"
        and reweight_effect == "clear-risk-strengthened"
        and recent_pending_status in {"pending-support", "pending-caution"}
        and (momentum_status != "sustained-clearance" or stability_status == "oscillating")
    ):
        pending_reason = (
            "Clearance pressure is visible, but it has not stayed persistent enough to clear the pending state early."
        )
        return (
            "pending-clearance",
            pending_reason,
            "hold",
            recent_pending_status,
            pending_reason,
            "none",
            "",
            trust_policy,
            trust_policy_reason,
            pending_debt_status,
            pending_debt_reason,
            policy_debt_status,
            policy_debt_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    if resolution_status == "cleared" and reweight_effect == "clear-risk-strengthened":
        confirmed_reason = (
            "Fresh unresolved pending debt has stayed strong enough to keep the earlier clearance decision in place."
        )
        return (
            "confirmed-clearance",
            confirmed_reason,
            closure_likely_outcome,
            transition_status,
            transition_reason,
            resolution_status,
            resolution_reason,
            trust_policy,
            trust_policy_reason,
            pending_debt_status,
            pending_debt_reason,
            policy_debt_status,
            policy_debt_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    if closure_likely_outcome == "confirm-soon":
        if momentum_status == "sustained-confirmation" and stability_status != "oscillating":
            return (
                "confirmed-confirmation",
                "Fresh class follow-through has stayed strong enough to keep the stronger confirmation forecast in place.",
                closure_likely_outcome,
                transition_status,
                transition_reason,
                resolution_status,
                resolution_reason,
                trust_policy,
                trust_policy_reason,
                pending_debt_status,
                pending_debt_reason,
                policy_debt_status,
                policy_debt_reason,
                class_normalization_status,
                class_normalization_reason,
            )
        return (
            "pending-confirmation",
            "The confirmation-leaning forecast is visible, but it has not stayed persistent enough to trust fully yet.",
            "hold",
            transition_status,
            transition_reason,
            resolution_status,
            resolution_reason,
            trust_policy,
            trust_policy_reason,
            pending_debt_status,
            pending_debt_reason,
            policy_debt_status,
            policy_debt_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    if (
        closure_likely_outcome == "hold"
        and direction == "supporting-confirmation"
        and freshness_status == "fresh"
        and momentum_status == "sustained-confirmation"
        and stability_status == "stable"
        and not local_noise
    ):
        return (
            "confirmed-confirmation",
            "Fresh class follow-through has stayed strong enough to keep the stronger confirmation forecast in place.",
            "confirm-soon",
            transition_status,
            transition_reason,
            resolution_status,
            resolution_reason,
            trust_policy,
            trust_policy_reason,
            pending_debt_status,
            pending_debt_reason,
            policy_debt_status,
            policy_debt_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    if closure_likely_outcome == "clear-risk":
        if momentum_status == "sustained-clearance" and stability_status != "oscillating":
            return (
                "confirmed-clearance",
                "Fresh unresolved pending debt has stayed strong enough to keep the stronger clearance forecast in place.",
                closure_likely_outcome,
                transition_status,
                transition_reason,
                resolution_status,
                resolution_reason,
                trust_policy,
                trust_policy_reason,
                pending_debt_status,
                pending_debt_reason,
                policy_debt_status,
                policy_debt_reason,
                class_normalization_status,
                class_normalization_reason,
            )
        return (
            "pending-clearance",
            "The clearance-leaning forecast is visible, but it has not stayed persistent enough to clear early yet.",
            "hold",
            transition_status,
            transition_reason,
            resolution_status,
            resolution_reason,
            trust_policy,
            trust_policy_reason,
            pending_debt_status,
            pending_debt_reason,
            policy_debt_status,
            policy_debt_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    if closure_likely_outcome == "expire-risk":
        if (
            momentum_status == "sustained-clearance"
            and stability_status != "oscillating"
            and transition_age_runs >= 3
        ):
            return (
                "confirmed-clearance",
                "Fresh unresolved pending debt has stayed strong long enough to keep expiry risk elevated.",
                closure_likely_outcome,
                transition_status,
                transition_reason,
                resolution_status,
                resolution_reason,
                trust_policy,
                trust_policy_reason,
                pending_debt_status,
                pending_debt_reason,
                policy_debt_status,
                policy_debt_reason,
                class_normalization_status,
                class_normalization_reason,
            )
        if momentum_status == "sustained-clearance" and stability_status != "oscillating":
            return (
                "pending-clearance",
                "Clearance pressure is visible, but expiry risk has not stayed stable enough to stay fully elevated yet.",
                "clear-risk",
                transition_status,
                transition_reason,
                resolution_status,
                resolution_reason,
                trust_policy,
                trust_policy_reason,
                pending_debt_status,
                pending_debt_reason,
                policy_debt_status,
                policy_debt_reason,
                class_normalization_status,
                class_normalization_reason,
            )
        return (
            "pending-clearance",
            "Expiry pressure is visible, but it has not stayed persistent enough to trust fully yet.",
            "hold",
            transition_status,
            transition_reason,
            resolution_status,
            resolution_reason,
            trust_policy,
            trust_policy_reason,
            pending_debt_status,
            pending_debt_reason,
            policy_debt_status,
            policy_debt_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    if momentum_status in {"reversing", "unstable"}:
        softened_outcome = closure_likely_outcome
        softened_reason = (
            "Recent pending-resolution evidence is changing direction, so earlier forecast strength is being softened."
        )
        if closure_likely_outcome == "confirm-soon":
            softened_outcome = "hold"
        elif closure_likely_outcome == "expire-risk":
            softened_outcome = "clear-risk"
        elif closure_likely_outcome == "clear-risk":
            softened_outcome = "hold"
        return (
            "pending-confirmation" if softened_outcome == "hold" and direction == "supporting-confirmation" else "pending-clearance" if softened_outcome in {"hold", "clear-risk"} and direction == "supporting-clearance" else "none",
            softened_reason,
            softened_outcome,
            transition_status,
            transition_reason,
            resolution_status,
            resolution_reason,
            trust_policy,
            trust_policy_reason,
            pending_debt_status,
            pending_debt_reason,
            policy_debt_status,
            policy_debt_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    return (
        "none",
        "",
        closure_likely_outcome,
        transition_status,
        transition_reason,
        resolution_status,
        resolution_reason,
        trust_policy,
        trust_policy_reason,
        pending_debt_status,
        pending_debt_reason,
        policy_debt_status,
        policy_debt_reason,
        class_normalization_status,
        class_normalization_reason,
    )


def _apply_closure_forecast_decay_control(
    target: dict,
    *,
    freshness_meta: dict,
    transition_history_meta: dict,
    trust_policy: str,
    trust_policy_reason: str,
    transition_status: str,
    transition_reason: str,
    resolution_status: str,
    resolution_reason: str,
    closure_likely_outcome: str,
    closure_hysteresis_status: str,
    closure_hysteresis_reason: str,
    pending_debt_status: str,
    pending_debt_reason: str,
    policy_debt_status: str,
    policy_debt_reason: str,
    class_normalization_status: str,
    class_normalization_reason: str,
) -> tuple[str, str, str, str, str, str, str, str, str, str, str, str, str, str, str, str, str]:
    freshness_status = freshness_meta.get("closure_forecast_freshness_status", "insufficient-data")
    decayed_clearance_rate = float(freshness_meta.get("decayed_clearance_forecast_rate", 0.0) or 0.0)
    local_noise = _target_specific_normalization_noise(target, transition_history_meta)
    direction = target.get("closure_forecast_reweight_direction", "neutral")
    recent_pending_status = transition_history_meta.get("recent_pending_status", "none")
    reweight_effect = target.get("closure_forecast_reweight_effect", "none")

    if local_noise and (
        direction == "supporting-confirmation"
        or closure_hysteresis_status in {"pending-confirmation", "confirmed-confirmation"}
    ):
        blocked_reason = "Local target instability still overrides closure-forecast freshness."
        if closure_likely_outcome == "confirm-soon":
            closure_likely_outcome = "hold"
        if closure_hysteresis_status == "confirmed-confirmation":
            closure_hysteresis_status = "pending-confirmation"
        closure_hysteresis_reason = blocked_reason
        return (
            "blocked",
            blocked_reason,
            closure_likely_outcome,
            closure_hysteresis_status,
            closure_hysteresis_reason,
            transition_status,
            transition_reason,
            resolution_status,
            resolution_reason,
            trust_policy,
            trust_policy_reason,
            pending_debt_status,
            pending_debt_reason,
            policy_debt_status,
            policy_debt_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    if (
        resolution_status == "cleared"
        and reweight_effect == "clear-risk-strengthened"
        and (freshness_status not in {"fresh", "mixed-age"} or decayed_clearance_rate < 0.50)
        and recent_pending_status in {"pending-support", "pending-caution"}
    ):
        decay_reason = (
            "The earlier forecast-driven clearance posture was pulled back because fresh unresolved pending-debt support is no longer strong enough."
        )
        transition_status = recent_pending_status
        transition_reason = decay_reason
        resolution_status = "none"
        resolution_reason = ""
        closure_likely_outcome = "hold"
        closure_hysteresis_status = "none"
        closure_hysteresis_reason = decay_reason
        if recent_pending_status == "pending-support":
            trust_policy = target.get("pre_class_normalization_trust_policy", trust_policy)
            trust_policy_reason = target.get("pre_class_normalization_trust_policy_reason", trust_policy_reason)
            class_normalization_status = "candidate"
            class_normalization_reason = decay_reason
        else:
            pending_debt_status = pending_debt_status or "watch"
            pending_debt_reason = pending_debt_reason or decay_reason
            policy_debt_status = "watch"
            policy_debt_reason = decay_reason
        return (
            "clearance-decayed",
            decay_reason,
            closure_likely_outcome,
            closure_hysteresis_status,
            closure_hysteresis_reason,
            transition_status,
            transition_reason,
            resolution_status,
            resolution_reason,
            trust_policy,
            trust_policy_reason,
            pending_debt_status,
            pending_debt_reason,
            policy_debt_status,
            policy_debt_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    if freshness_status not in {"stale", "insufficient-data"}:
        return (
            "none",
            "",
            closure_likely_outcome,
            closure_hysteresis_status,
            closure_hysteresis_reason,
            transition_status,
            transition_reason,
            resolution_status,
            resolution_reason,
            trust_policy,
            trust_policy_reason,
            pending_debt_status,
            pending_debt_reason,
            policy_debt_status,
            policy_debt_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    if closure_hysteresis_status == "confirmed-confirmation":
        decay_reason = (
            "Stronger confirmation wording was pulled back because the supporting forecast memory is too old or too lightly refreshed."
        )
        return (
            "confirmation-decayed",
            decay_reason,
            "hold",
            "pending-confirmation",
            decay_reason,
            transition_status,
            transition_reason,
            resolution_status,
            resolution_reason,
            trust_policy,
            trust_policy_reason,
            pending_debt_status,
            pending_debt_reason,
            policy_debt_status,
            policy_debt_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    if closure_hysteresis_status == "confirmed-clearance":
        decay_reason = (
            "Stronger clearance wording was pulled back because fresh unresolved pending-debt support is no longer strong enough."
        )
        softened_outcome = "clear-risk" if closure_likely_outcome == "expire-risk" else "hold"
        return (
            "clearance-decayed",
            decay_reason,
            softened_outcome,
            "pending-clearance",
            decay_reason,
            transition_status,
            transition_reason,
            resolution_status,
            resolution_reason,
            trust_policy,
            trust_policy_reason,
            pending_debt_status,
            pending_debt_reason,
            policy_debt_status,
            policy_debt_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    if closure_hysteresis_status == "pending-confirmation":
        decay_reason = (
            "Older confirmation-leaning forecast memory is no longer fresh enough to keep stronger carry-forward in place."
        )
        return (
            "confirmation-decayed",
            decay_reason,
            "hold",
            "none",
            decay_reason,
            transition_status,
            transition_reason,
            resolution_status,
            resolution_reason,
            trust_policy,
            trust_policy_reason,
            pending_debt_status,
            pending_debt_reason,
            policy_debt_status,
            policy_debt_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    if closure_hysteresis_status == "pending-clearance":
        decay_reason = (
            "Older clearance-leaning forecast memory is no longer fresh enough to keep stronger carry-forward in place."
        )
        softened_outcome = "clear-risk" if closure_likely_outcome == "expire-risk" else "hold"
        return (
            "clearance-decayed",
            decay_reason,
            softened_outcome,
            "none",
            decay_reason,
            transition_status,
            transition_reason,
            resolution_status,
            resolution_reason,
            trust_policy,
            trust_policy_reason,
            pending_debt_status,
            pending_debt_reason,
            policy_debt_status,
            policy_debt_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    return (
        "none",
        "",
        closure_likely_outcome,
        closure_hysteresis_status,
        closure_hysteresis_reason,
        transition_status,
        transition_reason,
        resolution_status,
        resolution_reason,
        trust_policy,
        trust_policy_reason,
        pending_debt_status,
        pending_debt_reason,
        policy_debt_status,
        policy_debt_reason,
        class_normalization_status,
        class_normalization_reason,
    )


def _closure_forecast_refresh_recovery_for_target(
    target: dict,
    closure_forecast_events: list[dict],
    transition_history_meta: dict,
) -> dict:
    class_key = _target_class_key(target)
    matching_events = [
        event for event in closure_forecast_events if event.get("class_key") == class_key
    ][:CLASS_CLOSURE_FORECAST_REFRESH_WINDOW_RUNS]
    relevant_events = [
        event for event in matching_events if _closure_forecast_event_has_evidence(event)
    ]
    directions = [
        _normalized_closure_forecast_direction(
            event.get("closure_forecast_reweight_direction", "neutral"),
            event.get("closure_forecast_reweight_score", 0.0),
        )
        for event in matching_events
    ]
    weighted_total = 0.0
    weight_sum = 0.0
    for index, event in enumerate(matching_events):
        weight = (1.0, 0.8, 0.6, 0.4)[min(index, CLASS_CLOSURE_FORECAST_REFRESH_WINDOW_RUNS - 1)]
        weighted_total += _closure_forecast_refresh_signal_from_event(event) * weight
        weight_sum += weight
    refresh_recovery_score = _clamp_round(
        weighted_total / max(weight_sum, 1.0),
        lower=-0.95,
        upper=0.95,
    )
    current_direction = directions[0] if directions else "neutral"
    earlier_majority = _closure_forecast_direction_majority(directions[1:])
    recent_weakened_side = _recent_closure_forecast_weakened_side(matching_events)
    freshness_status = target.get("closure_forecast_freshness_status", "insufficient-data")
    momentum_status = target.get("closure_forecast_momentum_status", "insufficient-data")
    stability_status = target.get("closure_forecast_stability_status", "watch")
    local_noise = _target_specific_normalization_noise(target, transition_history_meta)

    if len(relevant_events) < 2 or recent_weakened_side == "none":
        refresh_recovery_status = "none"
    elif local_noise and current_direction == "supporting-confirmation":
        refresh_recovery_status = "blocked"
    elif (
        recent_weakened_side == "confirmation"
        and current_direction == "supporting-clearance"
    ) or (
        recent_weakened_side == "clearance"
        and current_direction == "supporting-confirmation"
    ) or _closure_forecast_direction_reversing(current_direction, earlier_majority):
        refresh_recovery_status = "reversing"
    elif (
        recent_weakened_side == "confirmation"
        and current_direction == "supporting-confirmation"
        and freshness_status == "fresh"
        and refresh_recovery_score >= 0.25
        and stability_status != "oscillating"
    ):
        refresh_recovery_status = "reacquiring-confirmation"
    elif (
        recent_weakened_side == "clearance"
        and current_direction == "supporting-clearance"
        and freshness_status == "fresh"
        and refresh_recovery_score <= -0.25
        and stability_status != "oscillating"
    ):
        refresh_recovery_status = "reacquiring-clearance"
    elif (
        recent_weakened_side == "confirmation"
        and current_direction == "supporting-confirmation"
        and freshness_status in {"fresh", "mixed-age"}
        and refresh_recovery_score >= 0.15
    ):
        refresh_recovery_status = "recovering-confirmation"
    elif (
        recent_weakened_side == "clearance"
        and current_direction == "supporting-clearance"
        and freshness_status in {"fresh", "mixed-age"}
        and refresh_recovery_score <= -0.15
    ):
        refresh_recovery_status = "recovering-clearance"
    else:
        refresh_recovery_status = "none"

    if local_noise and current_direction == "supporting-confirmation":
        reacquisition_status = "blocked"
        reacquisition_reason = (
            "Local target instability is still preventing positive confirmation-side reacquisition."
        )
    elif (
        refresh_recovery_status == "reacquiring-confirmation"
        and freshness_status == "fresh"
        and momentum_status == "sustained-confirmation"
        and stability_status == "stable"
        and not local_noise
    ):
        reacquisition_status = "reacquired-confirmation"
        reacquisition_reason = (
            "Fresh confirmation-side support has stayed strong enough to earn back stronger confirmation forecasting."
        )
    elif (
        refresh_recovery_status == "reacquiring-clearance"
        and freshness_status == "fresh"
        and momentum_status == "sustained-clearance"
        and stability_status == "stable"
    ):
        reacquisition_status = "reacquired-clearance"
        reacquisition_reason = (
            "Fresh clearance-side pressure has stayed strong enough to earn back stronger clearance forecasting."
        )
    elif refresh_recovery_status in {"recovering-confirmation", "reacquiring-confirmation"}:
        reacquisition_status = "pending-confirmation-reacquisition"
        reacquisition_reason = (
            "Fresh confirmation-side forecast evidence is returning, but it has not fully re-earned stronger carry-forward yet."
        )
    elif refresh_recovery_status in {"recovering-clearance", "reacquiring-clearance"}:
        reacquisition_status = "pending-clearance-reacquisition"
        reacquisition_reason = (
            "Fresh clearance-side forecast evidence is returning, but it has not fully re-earned stronger carry-forward yet."
        )
    else:
        reacquisition_status = "none"
        reacquisition_reason = ""

    if refresh_recovery_status == "reversing":
        reacquisition_reason = (
            "The fresh recovery attempt is changing direction, so stronger carry-forward stays softened."
        )

    return {
        "closure_forecast_refresh_recovery_score": refresh_recovery_score,
        "closure_forecast_refresh_recovery_status": refresh_recovery_status,
        "closure_forecast_reacquisition_status": reacquisition_status,
        "closure_forecast_reacquisition_reason": reacquisition_reason,
        "recent_closure_forecast_refresh_path": " -> ".join(
            _closure_forecast_refresh_path_label(event) for event in matching_events if event
        ),
        "recent_weakened_side": recent_weakened_side,
    }


def _closure_forecast_refresh_signal_from_event(event: dict) -> float:
    score = float(event.get("closure_forecast_reweight_score", 0.0) or 0.0)
    direction = _normalized_closure_forecast_direction(
        event.get("closure_forecast_reweight_direction", "neutral"),
        score,
    )
    freshness_factor = {
        "fresh": 1.00,
        "mixed-age": 0.60,
        "stale": 0.25,
        "insufficient-data": 0.10,
    }.get(event.get("closure_forecast_freshness_status", "insufficient-data"), 0.10)
    signal_strength = max(abs(score), 0.05) if direction != "neutral" else 0.0
    if direction == "supporting-confirmation":
        return signal_strength * freshness_factor
    if direction == "supporting-clearance":
        return -signal_strength * freshness_factor
    return 0.0


def _recent_closure_forecast_weakened_side(events: list[dict]) -> str:
    for event in events:
        decay_status = event.get("closure_forecast_decay_status", "none") or "none"
        freshness_status = event.get("closure_forecast_freshness_status", "insufficient-data") or "insufficient-data"
        hysteresis_status = event.get("closure_forecast_hysteresis_status", "none") or "none"
        if decay_status == "confirmation-decayed" or (
            freshness_status in {"stale", "insufficient-data"}
            and hysteresis_status in {"pending-confirmation", "confirmed-confirmation"}
        ):
            return "confirmation"
        if decay_status == "clearance-decayed" or (
            freshness_status in {"stale", "insufficient-data"}
            and hysteresis_status in {"pending-clearance", "confirmed-clearance"}
        ):
            return "clearance"
    return "none"


def _closure_forecast_refresh_path_label(event: dict) -> str:
    direction = _normalized_closure_forecast_direction(
        event.get("closure_forecast_reweight_direction", "neutral"),
        event.get("closure_forecast_reweight_score", 0.0),
    )
    freshness = event.get("closure_forecast_freshness_status", "insufficient-data") or "insufficient-data"
    if direction == "supporting-confirmation":
        return f"{freshness} confirmation"
    if direction == "supporting-clearance":
        return f"{freshness} clearance"
    return "neutral"


def _apply_closure_forecast_reacquisition_control(
    target: dict,
    *,
    refresh_meta: dict,
    transition_history_meta: dict,
    trust_policy: str,
    trust_policy_reason: str,
    transition_status: str,
    transition_reason: str,
    resolution_status: str,
    resolution_reason: str,
    pending_debt_status: str,
    pending_debt_reason: str,
    policy_debt_status: str,
    policy_debt_reason: str,
    class_normalization_status: str,
    class_normalization_reason: str,
    closure_likely_outcome: str,
    closure_hysteresis_status: str,
    closure_hysteresis_reason: str,
) -> tuple[str, str, str, str, str, str, str, str, str, str, str, str, str, str, str]:
    refresh_status = refresh_meta.get("closure_forecast_refresh_recovery_status", "none")
    reacquisition_status = refresh_meta.get("closure_forecast_reacquisition_status", "none")
    reacquisition_reason = refresh_meta.get("closure_forecast_reacquisition_reason", "")
    recent_weakened_side = refresh_meta.get("recent_weakened_side", "none")
    freshness_status = target.get("closure_forecast_freshness_status", "insufficient-data")
    stability_status = target.get("closure_forecast_stability_status", "watch")
    decayed_clearance_rate = float(target.get("decayed_clearance_forecast_rate", 0.0) or 0.0)
    transition_age_runs = int(target.get("class_transition_age_runs", 0) or 0)

    if reacquisition_status == "reacquired-confirmation":
        closure_likely_outcome = "confirm-soon"
        closure_hysteresis_status = "confirmed-confirmation"
        closure_hysteresis_reason = reacquisition_reason
    elif reacquisition_status == "pending-confirmation-reacquisition":
        closure_likely_outcome = "hold"
        if recent_weakened_side == "confirmation":
            closure_hysteresis_status = "pending-confirmation"
            closure_hysteresis_reason = reacquisition_reason
    elif reacquisition_status == "reacquired-clearance":
        if closure_likely_outcome == "hold":
            closure_likely_outcome = "clear-risk"
        elif closure_likely_outcome == "clear-risk" and transition_age_runs >= 3:
            closure_likely_outcome = "expire-risk"
        closure_hysteresis_status = "confirmed-clearance"
        closure_hysteresis_reason = reacquisition_reason
        if (
            transition_status in {"pending-support", "pending-caution"}
            and decayed_clearance_rate >= 0.50
            and stability_status != "oscillating"
        ):
            clear_reason = (
                "Fresh clearance-side pressure has stayed strong enough to re-earn the earlier forecast-driven clearance posture."
            )
            resolution_status = "cleared"
            resolution_reason = clear_reason
            transition_status = "none"
            transition_reason = clear_reason
            if target.get("class_reweight_transition_status") == "pending-support":
                reverted_policy = target.get("pre_class_normalization_trust_policy", trust_policy)
                reverted_reason = target.get("pre_class_normalization_trust_policy_reason", trust_policy_reason)
                trust_policy = reverted_policy
                trust_policy_reason = (
                    clear_reason if reverted_policy == "verify-first" else reverted_reason
                )
                class_normalization_status = "candidate"
                class_normalization_reason = clear_reason
            else:
                pending_debt_status = pending_debt_status or "watch"
                pending_debt_reason = pending_debt_reason or clear_reason
                policy_debt_status = "watch"
                policy_debt_reason = clear_reason
    elif reacquisition_status == "pending-clearance-reacquisition":
        if recent_weakened_side == "clearance":
            closure_hysteresis_status = "pending-clearance"
            closure_hysteresis_reason = reacquisition_reason
    elif reacquisition_status == "blocked":
        closure_hysteresis_reason = reacquisition_reason or closure_hysteresis_reason
    elif refresh_status == "reversing":
        closure_hysteresis_reason = reacquisition_reason or closure_hysteresis_reason

    if freshness_status in {"stale", "insufficient-data"} and reacquisition_status.startswith("reacquired"):
        if reacquisition_status == "reacquired-confirmation":
            closure_likely_outcome = "hold"
            closure_hysteresis_status = "pending-confirmation"
        elif closure_likely_outcome == "expire-risk":
            closure_likely_outcome = "clear-risk"
        elif closure_likely_outcome == "clear-risk":
            closure_likely_outcome = "hold"
            closure_hysteresis_status = "pending-clearance"

    return (
        closure_likely_outcome,
        closure_hysteresis_status,
        closure_hysteresis_reason,
        transition_status,
        transition_reason,
        resolution_status,
        resolution_reason,
        trust_policy,
        trust_policy_reason,
        pending_debt_status,
        pending_debt_reason,
        policy_debt_status,
        policy_debt_reason,
        class_normalization_status,
        class_normalization_reason,
    )


def _closure_forecast_momentum_hotspots(resolution_targets: list[dict], *, mode: str) -> list[dict]:
    grouped: dict[str, dict] = {}
    for target in resolution_targets:
        class_key = _target_class_key(target)
        if not class_key:
            continue
        current = {
            "scope": "class",
            "label": class_key,
            "closure_forecast_momentum_score": target.get("closure_forecast_momentum_score", 0.0),
            "closure_forecast_momentum_status": target.get("closure_forecast_momentum_status", "insufficient-data"),
            "closure_forecast_stability_status": target.get("closure_forecast_stability_status", "watch"),
            "recent_closure_forecast_path": target.get("recent_closure_forecast_path", ""),
        }
        existing = grouped.get(class_key)
        if existing is None or abs(current["closure_forecast_momentum_score"]) > abs(existing["closure_forecast_momentum_score"]):
            grouped[class_key] = current

    hotspots = list(grouped.values())
    if mode == "confirmation":
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_momentum_status") == "sustained-confirmation"
        ]
        hotspots.sort(
            key=lambda item: (
                -item.get("closure_forecast_momentum_score", 0.0),
                item.get("label", ""),
            )
        )
    elif mode == "clearance":
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_momentum_status") == "sustained-clearance"
        ]
        hotspots.sort(
            key=lambda item: (
                item.get("closure_forecast_momentum_score", 0.0),
                item.get("label", ""),
            )
        )
    else:
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_stability_status") == "oscillating"
        ]
        hotspots.sort(
            key=lambda item: (
                -abs(item.get("closure_forecast_momentum_score", 0.0)),
                item.get("label", ""),
            )
        )
    return hotspots[:5]


def _closure_forecast_momentum_summary(
    primary_target: dict,
    sustained_confirmation_hotspots: list[dict],
    sustained_clearance_hotspots: list[dict],
    oscillating_closure_forecast_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    status = primary_target.get("closure_forecast_momentum_status", "insufficient-data")
    score = primary_target.get("closure_forecast_momentum_score", 0.0)
    if status == "sustained-confirmation":
        return f"Recent pending-resolution behavior around {label} has stayed strong long enough to keep the confirmation forecast credible ({score:.2f})."
    if status == "sustained-clearance":
        return f"Unresolved pending debt around {label} has stayed strong long enough to keep clearance or expiry risk elevated ({score:.2f})."
    if status == "building":
        return f"The closure forecast for {label} is trending in one direction, but it has not held long enough to lock in ({score:.2f})."
    if status == "reversing":
        return f"Recent pending-resolution evidence around {label} is changing direction, so earlier forecast strength is being softened ({score:.2f})."
    if status == "unstable":
        return f"Recent closure-forecast evidence around {label} is bouncing too much to strengthen safely right now ({score:.2f})."
    if sustained_confirmation_hotspots:
        hotspot = sustained_confirmation_hotspots[0]
        return (
            f"Confirmation-leaning closure momentum is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "but the current target has not built enough persistence yet."
        )
    if sustained_clearance_hotspots:
        hotspot = sustained_clearance_hotspots[0]
        return (
            f"Clearance-heavy closure momentum is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so weaker pending states there should keep proving follow-through."
        )
    if oscillating_closure_forecast_hotspots:
        hotspot = oscillating_closure_forecast_hotspots[0]
        return (
            f"Closure-forecast stability is weakest around {hotspot.get('label', 'recent hotspots')}, "
            "so stronger forecast changes there should wait for persistence."
        )
    return "Closure-forecast momentum is still too lightly exercised to say whether recent pending-resolution behavior is sustained or unstable."


def _closure_forecast_stability_summary(
    primary_target: dict,
    oscillating_closure_forecast_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    stability_status = primary_target.get("closure_forecast_stability_status", "watch")
    recent_path = primary_target.get("recent_closure_forecast_path", "")
    if stability_status == "oscillating":
        return f"Closure forecasting for {label} is bouncing too much to strengthen safely right now: {recent_path or 'no stable path yet'}."
    if stability_status == "watch":
        return f"Closure forecasting for {label} is still settling and should be watched for one more stable stretch: {recent_path or 'signal is still building'}."
    if recent_path:
        return f"Closure forecasting for {label} is stable across the recent path: {recent_path}."
    if oscillating_closure_forecast_hotspots:
        hotspot = oscillating_closure_forecast_hotspots[0]
        return (
            f"Closure-forecast stability is weakest around {hotspot.get('label', 'recent hotspots')}, "
            "so stronger forecast shifts should wait there."
        )
    return "Recent closure-forecast guidance is stable enough that no extra hysteresis warning is needed."


def _closure_forecast_hysteresis_summary(
    primary_target: dict,
    sustained_confirmation_hotspots: list[dict],
    sustained_clearance_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    status = primary_target.get("closure_forecast_hysteresis_status", "none")
    reason = primary_target.get("closure_forecast_hysteresis_reason", "")
    if status == "confirmed-confirmation":
        return reason or f"Fresh class follow-through has stayed strong enough to keep the stronger confirmation forecast in place for {label}."
    if status == "confirmed-clearance":
        return reason or f"Fresh unresolved pending debt has stayed strong enough to keep the stronger clearance forecast in place for {label}."
    if status == "pending-confirmation":
        return reason or f"The confirmation-leaning forecast for {label} is visible but not yet persistent enough to trust fully."
    if status == "pending-clearance":
        return reason or f"The clearance-leaning forecast for {label} is visible but not yet persistent enough to clear early."
    if status == "blocked":
        return reason or f"Local target instability is preventing positive closure-forecast strengthening for {label}."
    if sustained_confirmation_hotspots:
        hotspot = sustained_confirmation_hotspots[0]
        return (
            f"Confirmation-side closure hysteresis is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes are closest to holding stronger confirmation forecasts safely."
        )
    if sustained_clearance_hotspots:
        hotspot = sustained_clearance_hotspots[0]
        return (
            f"Clearance-side closure hysteresis is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes can hold stronger clearance forecasts only when that pressure keeps persisting."
        )
    return "No closure-forecast hysteresis adjustment is changing the live pending forecast right now."


def _closure_forecast_freshness_hotspots(resolution_targets: list[dict], *, mode: str) -> list[dict]:
    grouped: dict[str, dict] = {}
    for target in resolution_targets:
        class_key = _target_class_key(target)
        if not class_key:
            continue
        current = {
            "scope": "class",
            "label": class_key,
            "closure_forecast_freshness_status": target.get("closure_forecast_freshness_status", "insufficient-data"),
            "decayed_confirmation_forecast_rate": target.get("decayed_confirmation_forecast_rate", 0.0),
            "decayed_clearance_forecast_rate": target.get("decayed_clearance_forecast_rate", 0.0),
            "recent_closure_forecast_signal_mix": target.get("recent_closure_forecast_signal_mix", ""),
            "recent_closure_forecast_path": target.get("recent_closure_forecast_path", ""),
            "dominant_count": max(
                target.get("decayed_confirmation_forecast_rate", 0.0),
                target.get("decayed_clearance_forecast_rate", 0.0),
            ),
            "forecast_event_count": len(
                [
                    part
                    for part in (target.get("recent_closure_forecast_path", "") or "").split(" -> ")
                    if part
                ]
            ),
        }
        existing = grouped.get(class_key)
        if existing is None or current["dominant_count"] > existing["dominant_count"]:
            grouped[class_key] = current

    hotspots = list(grouped.values())
    if mode == "fresh":
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_freshness_status") == "fresh"
            and item.get("dominant_count", 0.0) > 0.0
        ]
    else:
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_freshness_status") == "stale"
            and item.get("dominant_count", 0.0) > 0.0
        ]
    hotspots.sort(
        key=lambda item: (
            -item.get("dominant_count", 0.0),
            -item.get("forecast_event_count", 0),
            item.get("label", ""),
        )
    )
    return hotspots[:5]


def _closure_forecast_freshness_summary(
    primary_target: dict,
    stale_closure_forecast_hotspots: list[dict],
    fresh_closure_forecast_signal_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    freshness_status = primary_target.get("closure_forecast_freshness_status", "insufficient-data")
    if freshness_status == "fresh":
        return f"{label} still has recent closure-forecast evidence that is current enough to trust."
    if freshness_status == "mixed-age":
        return f"{label} still has useful closure-forecast memory, but part of that signal is aging and should be weighted more cautiously."
    if freshness_status == "stale":
        return f"{label} is leaning on older closure-forecast momentum more than fresh runs, so stale class carry-forward should not dominate the current forecast."
    if fresh_closure_forecast_signal_hotspots:
        hotspot = fresh_closure_forecast_signal_hotspots[0]
        return (
            f"Fresh closure-forecast evidence is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes deserve more trust than older forecast carry-forward."
        )
    if stale_closure_forecast_hotspots:
        hotspot = stale_closure_forecast_hotspots[0]
        return (
            f"Older closure-forecast momentum is lingering most around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes should keep letting stale forecast strength decay."
        )
    return "Closure-forecast memory is still too lightly exercised to say whether fresh or stale forecast evidence should lead the current posture."


def _closure_forecast_decay_summary(
    primary_target: dict,
    fresh_closure_forecast_signal_hotspots: list[dict],
    stale_closure_forecast_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    decay_status = primary_target.get("closure_forecast_decay_status", "none")
    freshness_status = primary_target.get("closure_forecast_freshness_status", "insufficient-data")
    confirmation_rate = primary_target.get("decayed_confirmation_forecast_rate", 0.0)
    clearance_rate = primary_target.get("decayed_clearance_forecast_rate", 0.0)
    if decay_status == "confirmation-decayed":
        return f"Stronger confirmation wording for {label} was pulled back because the supporting closure-forecast memory is too old or too lightly refreshed."
    if decay_status == "clearance-decayed":
        return f"Stronger clearance wording for {label} was pulled back because fresh unresolved pending-debt support is no longer strong enough."
    if decay_status == "blocked":
        return f"Local target instability still overrides closure-forecast freshness for {label}, so forecast carry-forward should stay conservative."
    if freshness_status == "fresh" and confirmation_rate >= clearance_rate:
        return f"Fresh closure-forecast evidence for {label} is still reinforcing confirmation-side posture more than clearance pressure."
    if freshness_status == "fresh":
        return f"Fresh closure-forecast evidence for {label} is still reinforcing clearance pressure more than confirmation-side carry-forward."
    if freshness_status == "stale":
        return f"Older closure-forecast momentum is being down-weighted for {label}, so stale forecast strength should keep decaying instead of carrying forward indefinitely."
    if fresh_closure_forecast_signal_hotspots:
        hotspot = fresh_closure_forecast_signal_hotspots[0]
        return (
            f"Fresh closure-forecast reinforcement is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes are earning stronger live forecasting than older carry-forward."
        )
    if stale_closure_forecast_hotspots:
        hotspot = stale_closure_forecast_hotspots[0]
        return (
            f"Stale closure-forecast carry-forward is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those older forecast patterns should keep decaying."
        )
    return "No strong closure-forecast freshness trend is dominating the live hysteresis posture yet."


def _closure_forecast_refresh_hotspots(resolution_targets: list[dict], *, mode: str) -> list[dict]:
    grouped: dict[str, dict] = {}
    for target in resolution_targets:
        class_key = _target_class_key(target)
        if not class_key:
            continue
        current = {
            "scope": "class",
            "label": class_key,
            "closure_forecast_refresh_recovery_score": target.get("closure_forecast_refresh_recovery_score", 0.0),
            "closure_forecast_refresh_recovery_status": target.get("closure_forecast_refresh_recovery_status", "none"),
            "closure_forecast_reacquisition_status": target.get("closure_forecast_reacquisition_status", "none"),
            "recent_closure_forecast_refresh_path": target.get("recent_closure_forecast_refresh_path", ""),
        }
        existing = grouped.get(class_key)
        if existing is None or abs(current["closure_forecast_refresh_recovery_score"]) > abs(
            existing["closure_forecast_refresh_recovery_score"]
        ):
            grouped[class_key] = current

    hotspots = list(grouped.values())
    if mode == "confirmation":
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_refresh_recovery_status")
            in {"recovering-confirmation", "reacquiring-confirmation"}
            or item.get("closure_forecast_reacquisition_status")
            in {"pending-confirmation-reacquisition", "reacquired-confirmation"}
        ]
        hotspots.sort(
            key=lambda item: (
                -item.get("closure_forecast_refresh_recovery_score", 0.0),
                item.get("label", ""),
            )
        )
    else:
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_refresh_recovery_status")
            in {"recovering-clearance", "reacquiring-clearance"}
            or item.get("closure_forecast_reacquisition_status")
            in {"pending-clearance-reacquisition", "reacquired-clearance"}
        ]
        hotspots.sort(
            key=lambda item: (
                item.get("closure_forecast_refresh_recovery_score", 0.0),
                item.get("label", ""),
            )
        )
    return hotspots[:5]


def _closure_forecast_refresh_recovery_summary(
    primary_target: dict,
    recovering_confirmation_hotspots: list[dict],
    recovering_clearance_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    status = primary_target.get("closure_forecast_refresh_recovery_status", "none")
    score = primary_target.get("closure_forecast_refresh_recovery_score", 0.0)
    if status == "recovering-confirmation":
        return f"Fresh confirmation-side forecast evidence is returning for {label}, but it has not fully re-earned stronger carry-forward yet ({score:.2f})."
    if status == "recovering-clearance":
        return f"Fresh clearance-side forecast evidence is returning for {label}, but it has not fully re-earned stronger carry-forward yet ({score:.2f})."
    if status == "reacquiring-confirmation":
        return f"Fresh confirmation-side support around {label} is strong enough that stronger forecast carry-forward may be earned back soon ({score:.2f})."
    if status == "reacquiring-clearance":
        return f"Fresh clearance-side pressure around {label} is strong enough that stronger forecast carry-forward may be earned back soon ({score:.2f})."
    if status == "reversing":
        return f"The fresh recovery attempt around {label} is changing direction, so stronger carry-forward stays softened ({score:.2f})."
    if status == "blocked":
        return f"Local target instability is still preventing positive confirmation-side reacquisition for {label}."
    if recovering_confirmation_hotspots:
        hotspot = recovering_confirmation_hotspots[0]
        return (
            f"Confirmation-side refresh recovery is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "but the current target has not re-earned stronger carry-forward yet."
        )
    if recovering_clearance_hotspots:
        hotspot = recovering_clearance_hotspots[0]
        return (
            f"Clearance-side refresh recovery is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes are closest to re-earning stronger clearance forecasting."
        )
    return "No closure-forecast refresh recovery is strong enough yet to re-earn stronger carry-forward."


def _closure_forecast_reacquisition_summary(
    primary_target: dict,
    recovering_confirmation_hotspots: list[dict],
    recovering_clearance_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    status = primary_target.get("closure_forecast_reacquisition_status", "none")
    reason = primary_target.get("closure_forecast_reacquisition_reason", "")
    if status == "reacquired-confirmation":
        return reason or f"Fresh confirmation-side support has stayed strong enough to earn back stronger confirmation forecasting for {label}."
    if status == "reacquired-clearance":
        return reason or f"Fresh clearance-side pressure has stayed strong enough to earn back stronger clearance forecasting for {label}."
    if status == "pending-confirmation-reacquisition":
        return reason or f"Confirmation-side recovery is visible for {label}, but stronger carry-forward has not been fully re-earned yet."
    if status == "pending-clearance-reacquisition":
        return reason or f"Clearance-side recovery is visible for {label}, but stronger carry-forward has not been fully re-earned yet."
    if status == "blocked":
        return reason or f"Local target instability is still preventing positive confirmation-side reacquisition for {label}."
    if recovering_confirmation_hotspots:
        hotspot = recovering_confirmation_hotspots[0]
        return (
            f"Confirmation-side reacquisition is most active around {hotspot.get('label', 'recent hotspots')}, "
            "but those classes still need fresh, stable follow-through before stronger carry-forward is restored."
        )
    if recovering_clearance_hotspots:
        hotspot = recovering_clearance_hotspots[0]
        return (
            f"Clearance-side reacquisition is most active around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes can only restore stronger clearance posture when fresh pressure keeps holding."
        )
    return "No closure-forecast reacquisition is re-earning stronger carry-forward right now."


def _closure_forecast_reacquisition_side_from_event(event: dict) -> str:
    reacquisition_status = event.get("closure_forecast_reacquisition_status", "none") or "none"
    if reacquisition_status in {
        "pending-confirmation-reacquisition",
        "reacquired-confirmation",
    }:
        return "confirmation"
    if reacquisition_status in {
        "pending-clearance-reacquisition",
        "reacquired-clearance",
    }:
        return "clearance"
    refresh_status = event.get("closure_forecast_refresh_recovery_status", "none") or "none"
    if refresh_status in {"recovering-confirmation", "reacquiring-confirmation"}:
        return "confirmation"
    if refresh_status in {"recovering-clearance", "reacquiring-clearance"}:
        return "clearance"
    return "none"


def _closure_forecast_reacquisition_side_from_status(status: str) -> str:
    if status in {
        "holding-confirmation",
        "sustained-confirmation",
        "pending-confirmation",
        "confirmed-confirmation",
    }:
        return "confirmation"
    if status in {
        "holding-clearance",
        "sustained-clearance",
        "pending-clearance",
        "confirmed-clearance",
    }:
        return "clearance"
    return "none"


def _closure_forecast_reacquisition_path_label(event: dict) -> str:
    status = event.get("closure_forecast_reacquisition_status", "none") or "none"
    if status != "none":
        return status
    likely_outcome = event.get("transition_closure_likely_outcome", "none") or "none"
    if likely_outcome != "none":
        return likely_outcome
    return "hold"


def _closure_forecast_reacquisition_persistence_for_target(
    target: dict,
    closure_forecast_events: list[dict],
    transition_history_meta: dict,
) -> dict:
    class_key = _target_class_key(target)
    matching_events = [
        event for event in closure_forecast_events if event.get("class_key") == class_key
    ][:CLASS_REACQUISITION_PERSISTENCE_WINDOW_RUNS]
    relevant_events = [
        event for event in matching_events if _closure_forecast_reacquisition_side_from_event(event) != "none"
    ]
    current_side = _closure_forecast_reacquisition_side_from_event(matching_events[0]) if matching_events else "none"
    persistence_age_runs = 0
    for event in matching_events:
        event_side = _closure_forecast_reacquisition_side_from_event(event)
        if event_side != current_side or event_side == "none":
            break
        persistence_age_runs += 1

    weighted_total = 0.0
    weight_sum = 0.0
    sides: list[str] = []
    for index, event in enumerate(relevant_events[:CLASS_REACQUISITION_PERSISTENCE_WINDOW_RUNS]):
        weight = (1.0, 0.8, 0.6, 0.4)[min(index, CLASS_REACQUISITION_PERSISTENCE_WINDOW_RUNS - 1)]
        event_side = _closure_forecast_reacquisition_side_from_event(event)
        sign = 1.0 if event_side == "confirmation" else -1.0
        sides.append("supporting-confirmation" if sign > 0 else "supporting-clearance")
        magnitude = 0.0
        if event.get("closure_forecast_reacquisition_status", "none") in {
            "reacquired-confirmation",
            "reacquired-clearance",
        }:
            magnitude += 0.15
        momentum_status = event.get("closure_forecast_momentum_status", "insufficient-data")
        if (
            event_side == "confirmation" and momentum_status == "sustained-confirmation"
        ) or (
            event_side == "clearance" and momentum_status == "sustained-clearance"
        ):
            magnitude += 0.10
        stability_status = event.get("closure_forecast_stability_status", "watch")
        if stability_status == "stable":
            magnitude += 0.10
        freshness_status = event.get("closure_forecast_freshness_status", "insufficient-data")
        if freshness_status == "fresh":
            magnitude += 0.10
        elif freshness_status == "mixed-age":
            magnitude = max(0.0, magnitude - 0.10)
        if momentum_status in {"reversing", "unstable"}:
            magnitude = max(0.0, magnitude - 0.15)
        if stability_status == "oscillating":
            magnitude = max(0.0, magnitude - 0.15)
        if event.get("closure_forecast_decay_status", "none") != "none":
            magnitude = max(0.0, magnitude - 0.15)
        weighted_total += sign * magnitude * weight
        weight_sum += weight

    persistence_score = _clamp_round(weighted_total / max(weight_sum, 1.0), lower=-0.95, upper=0.95)
    current_momentum_status = target.get("closure_forecast_momentum_status", "insufficient-data")
    current_stability_status = target.get("closure_forecast_stability_status", "watch")
    current_freshness_status = target.get("closure_forecast_freshness_status", "insufficient-data")
    earlier_majority = _closure_forecast_direction_majority(sides[1:])
    current_direction = "supporting-confirmation" if current_side == "confirmation" else "supporting-clearance" if current_side == "clearance" else "neutral"

    if current_side == "none" and not relevant_events:
        persistence_status = "none"
    elif (
        target.get("closure_forecast_reacquisition_status", "none") in {"reacquired-confirmation", "reacquired-clearance"}
        and persistence_age_runs == 1
    ):
        persistence_status = "just-reacquired"
    elif len(relevant_events) < 2:
        persistence_status = "insufficient-data"
    elif _closure_forecast_direction_reversing(current_direction, earlier_majority) or current_momentum_status in {"reversing", "unstable"} or target.get("closure_forecast_decay_status", "none") != "none":
        persistence_status = "reversing"
    elif (
        current_side == "confirmation"
        and persistence_age_runs >= 3
        and current_freshness_status == "fresh"
        and current_momentum_status == "sustained-confirmation"
        and current_stability_status != "oscillating"
    ):
        persistence_status = "sustained-confirmation"
    elif (
        current_side == "clearance"
        and persistence_age_runs >= 3
        and current_freshness_status == "fresh"
        and current_momentum_status == "sustained-clearance"
        and current_stability_status != "oscillating"
    ):
        persistence_status = "sustained-clearance"
    elif current_side == "confirmation" and persistence_age_runs >= 2 and persistence_score > 0:
        persistence_status = "holding-confirmation"
    elif current_side == "clearance" and persistence_age_runs >= 2 and persistence_score < 0:
        persistence_status = "holding-clearance"
    else:
        persistence_status = "none"

    if persistence_status == "just-reacquired":
        persistence_reason = "Stronger closure-forecast posture has returned, but it has not yet proved it can hold."
    elif persistence_status == "holding-confirmation":
        persistence_reason = "Confirmation-side recovery has stayed aligned long enough to keep the restored forecast in place."
    elif persistence_status == "holding-clearance":
        persistence_reason = "Clearance-side recovery has stayed aligned long enough to keep the restored forecast in place."
    elif persistence_status == "sustained-confirmation":
        persistence_reason = "Confirmation-side reacquisition is now holding with enough follow-through to trust the restored forecast more."
    elif persistence_status == "sustained-clearance":
        persistence_reason = "Clearance-side reacquisition is now holding with enough follow-through to trust the restored caution more."
    elif persistence_status == "reversing":
        persistence_reason = "The restored forecast posture is already weakening, so it is being softened again."
    elif persistence_status == "insufficient-data":
        persistence_reason = "Reacquisition is still too lightly exercised to say whether the restored forecast can hold."
    else:
        persistence_reason = ""

    return {
        "closure_forecast_reacquisition_age_runs": persistence_age_runs,
        "closure_forecast_reacquisition_persistence_score": persistence_score,
        "closure_forecast_reacquisition_persistence_status": persistence_status,
        "closure_forecast_reacquisition_persistence_reason": persistence_reason,
        "recent_reacquisition_persistence_path": " -> ".join(
            _closure_forecast_reacquisition_path_label(event) for event in matching_events if event
        ),
    }


def _closure_forecast_recovery_churn_for_target(
    target: dict,
    closure_forecast_events: list[dict],
    transition_history_meta: dict,
) -> dict:
    class_key = _target_class_key(target)
    matching_events = [
        event for event in closure_forecast_events if event.get("class_key") == class_key
    ][:CLASS_REACQUISITION_PERSISTENCE_WINDOW_RUNS]
    side_path = [
        _closure_forecast_reacquisition_side_from_event(event)
        for event in matching_events
        if _closure_forecast_reacquisition_side_from_event(event) != "none"
    ]
    current_side = side_path[0] if side_path else "none"
    local_noise = _target_specific_normalization_noise(target, transition_history_meta)
    if current_side == "none":
        churn_status = "none"
        churn_reason = ""
        churn_score = 0.0
    else:
        flip_count = _class_direction_flip_count(
            [
                "supporting-confirmation" if side == "confirmation" else "supporting-clearance"
                for side in side_path
            ]
        )
        churn_score = float(flip_count) * 0.20
        stability_status = target.get("closure_forecast_stability_status", "watch")
        momentum_status = target.get("closure_forecast_momentum_status", "insufficient-data")
        if stability_status == "oscillating":
            churn_score += 0.15
        if momentum_status == "reversing":
            churn_score += 0.10
        if momentum_status == "unstable":
            churn_score += 0.10
        freshness_path = [event.get("closure_forecast_freshness_status", "insufficient-data") for event in matching_events]
        if any(
            previous == "fresh" and current in {"mixed-age", "stale", "insufficient-data"}
            for previous, current in zip(freshness_path, freshness_path[1:])
        ):
            churn_score += 0.10
        if target.get("closure_forecast_decay_status", "none") != "none":
            churn_score += 0.10
        if (
            len(side_path) >= 2
            and side_path[0] == side_path[1]
            and matching_events[0].get("closure_forecast_freshness_status", "insufficient-data") == "fresh"
            and matching_events[1].get("closure_forecast_freshness_status", "insufficient-data") == "fresh"
        ):
            churn_score -= 0.10
        churn_score = _clamp_round(churn_score, lower=0.0, upper=0.95)
        if local_noise and current_side == "confirmation":
            churn_status = "blocked"
            churn_reason = "Local target instability is preventing positive confirmation-side persistence."
        elif churn_score >= 0.45 or flip_count >= 2:
            churn_status = "churn"
            churn_reason = "Recovery is flipping enough that restored forecast posture should be softened quickly."
        elif churn_score >= 0.20:
            churn_status = "watch"
            churn_reason = "Recovery is wobbling and may lose its restored strength soon."
        else:
            churn_status = "none"
            churn_reason = ""
    return {
        "closure_forecast_recovery_churn_score": churn_score,
        "closure_forecast_recovery_churn_status": churn_status,
        "closure_forecast_recovery_churn_reason": churn_reason,
        "recent_recovery_churn_path": " -> ".join(
            _closure_forecast_reacquisition_path_label(event) for event in matching_events if event
        ),
    }


def _apply_reacquisition_persistence_and_churn_control(
    target: dict,
    *,
    persistence_meta: dict,
    churn_meta: dict,
    transition_history_meta: dict,
    trust_policy: str,
    trust_policy_reason: str,
    transition_status: str,
    transition_reason: str,
    resolution_status: str,
    resolution_reason: str,
    pending_debt_status: str,
    pending_debt_reason: str,
    policy_debt_status: str,
    policy_debt_reason: str,
    class_normalization_status: str,
    class_normalization_reason: str,
    closure_likely_outcome: str,
    closure_hysteresis_status: str,
    closure_hysteresis_reason: str,
) -> tuple[str, str, str, str, str, str, str, str, str, str, str, str, str, str, str]:
    persistence_status = persistence_meta.get("closure_forecast_reacquisition_persistence_status", "none")
    persistence_reason = persistence_meta.get("closure_forecast_reacquisition_persistence_reason", "")
    churn_status = churn_meta.get("closure_forecast_recovery_churn_status", "none")
    churn_reason = churn_meta.get("closure_forecast_recovery_churn_reason", "")
    current_reacquisition_status = target.get("closure_forecast_reacquisition_status", "none")
    current_freshness_status = target.get("closure_forecast_freshness_status", "insufficient-data")
    transition_age_runs = int(target.get("class_transition_age_runs", 0) or 0)
    recent_pending_status = transition_history_meta.get("recent_pending_status", "none")

    if churn_status == "blocked":
        closure_likely_outcome = "hold"
        if closure_hysteresis_status == "confirmed-confirmation":
            closure_hysteresis_status = "pending-confirmation"
        closure_hysteresis_reason = churn_reason or closure_hysteresis_reason
        return (
            closure_likely_outcome,
            closure_hysteresis_status,
            closure_hysteresis_reason,
            transition_status,
            transition_reason,
            resolution_status,
            resolution_reason,
            trust_policy,
            trust_policy_reason,
            pending_debt_status,
            pending_debt_reason,
            policy_debt_status,
            policy_debt_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    if current_freshness_status in {"stale", "insufficient-data"}:
        if closure_likely_outcome == "confirm-soon":
            closure_likely_outcome = "hold"
            if closure_hysteresis_status == "confirmed-confirmation":
                closure_hysteresis_status = "pending-confirmation"
                closure_hysteresis_reason = persistence_reason or churn_reason or closure_hysteresis_reason
        elif closure_likely_outcome == "expire-risk":
            closure_likely_outcome = "clear-risk"
            closure_hysteresis_status = "pending-clearance"
            closure_hysteresis_reason = persistence_reason or churn_reason or closure_hysteresis_reason
        elif closure_likely_outcome == "clear-risk":
            closure_likely_outcome = "hold"
            if closure_hysteresis_status == "confirmed-clearance":
                closure_hysteresis_status = "pending-clearance"
                closure_hysteresis_reason = persistence_reason or churn_reason or closure_hysteresis_reason

    if current_reacquisition_status == "reacquired-confirmation":
        if persistence_status in {"holding-confirmation", "sustained-confirmation"} and churn_status != "churn":
            return (
                closure_likely_outcome,
                closure_hysteresis_status,
                closure_hysteresis_reason,
                transition_status,
                transition_reason,
                resolution_status,
                resolution_reason,
                trust_policy,
                trust_policy_reason,
                pending_debt_status,
                pending_debt_reason,
                policy_debt_status,
                policy_debt_reason,
                class_normalization_status,
                class_normalization_reason,
            )
        if persistence_status == "reversing" or churn_status == "churn":
            closure_likely_outcome = "hold"
            if closure_hysteresis_status == "confirmed-confirmation":
                closure_hysteresis_status = "pending-confirmation"
            closure_hysteresis_reason = churn_reason or persistence_reason or closure_hysteresis_reason

    if current_reacquisition_status == "reacquired-clearance":
        if persistence_status in {"holding-clearance", "sustained-clearance"} and churn_status != "churn":
            if closure_likely_outcome == "expire-risk" and transition_age_runs < 3:
                closure_likely_outcome = "clear-risk"
            return (
                closure_likely_outcome,
                closure_hysteresis_status,
                closure_hysteresis_reason,
                transition_status,
                transition_reason,
                resolution_status,
                resolution_reason,
                trust_policy,
                trust_policy_reason,
                pending_debt_status,
                pending_debt_reason,
                policy_debt_status,
                policy_debt_reason,
                class_normalization_status,
                class_normalization_reason,
            )
        if persistence_status == "reversing" or churn_status == "churn":
            if closure_likely_outcome == "expire-risk":
                closure_likely_outcome = "clear-risk"
            elif closure_likely_outcome == "clear-risk":
                closure_likely_outcome = "hold"
            if closure_hysteresis_status == "confirmed-clearance":
                closure_hysteresis_status = "pending-clearance"
            closure_hysteresis_reason = churn_reason or persistence_reason or closure_hysteresis_reason
            if resolution_status == "cleared" and recent_pending_status in {"pending-support", "pending-caution"}:
                restore_reason = churn_reason or persistence_reason or (
                    "Reacquired clearance pressure stopped holding cleanly, so the earlier-clear posture has been withdrawn."
                )
                transition_status = recent_pending_status
                transition_reason = restore_reason
                resolution_status = "none"
                resolution_reason = ""
                if recent_pending_status == "pending-support":
                    reverted_policy = target.get("pre_class_normalization_trust_policy", trust_policy)
                    reverted_reason = target.get("pre_class_normalization_trust_policy_reason", trust_policy_reason)
                    trust_policy = reverted_policy
                    trust_policy_reason = restore_reason if reverted_policy == "verify-first" else reverted_reason
                    class_normalization_status = "candidate"
                    class_normalization_reason = restore_reason
                else:
                    pending_debt_status = pending_debt_status or "watch"
                    pending_debt_reason = pending_debt_reason or restore_reason
                    policy_debt_status = "watch"
                    policy_debt_reason = restore_reason

    return (
        closure_likely_outcome,
        closure_hysteresis_status,
        closure_hysteresis_reason,
        transition_status,
        transition_reason,
        resolution_status,
        resolution_reason,
        trust_policy,
        trust_policy_reason,
        pending_debt_status,
        pending_debt_reason,
        policy_debt_status,
        policy_debt_reason,
        class_normalization_status,
        class_normalization_reason,
    )


def _apply_reacquisition_freshness_reset_control(
    target: dict,
    *,
    freshness_meta: dict,
    transition_history_meta: dict,
    trust_policy: str,
    trust_policy_reason: str,
    transition_status: str,
    transition_reason: str,
    resolution_status: str,
    resolution_reason: str,
    pending_debt_status: str,
    pending_debt_reason: str,
    policy_debt_status: str,
    policy_debt_reason: str,
    class_normalization_status: str,
    class_normalization_reason: str,
    closure_likely_outcome: str,
    closure_hysteresis_status: str,
    closure_hysteresis_reason: str,
    reacquisition_status: str,
    reacquisition_reason: str,
    persistence_age_runs: int,
    persistence_score: float,
    persistence_status: str,
    persistence_reason: str,
) -> dict:
    freshness_status = freshness_meta.get(
        "closure_forecast_reacquisition_freshness_status",
        "insufficient-data",
    )
    decayed_clearance_rate = float(
        freshness_meta.get("decayed_reacquired_clearance_rate", 0.0) or 0.0
    )
    churn_status = target.get("closure_forecast_recovery_churn_status", "none")
    recent_pending_status = transition_history_meta.get("recent_pending_status", "none")
    current_side = _closure_forecast_reacquisition_side_from_status(persistence_status)
    if current_side == "none":
        current_side = _closure_forecast_reacquisition_side_from_event(
            {
                "closure_forecast_reacquisition_status": reacquisition_status,
                "closure_forecast_refresh_recovery_status": target.get(
                    "closure_forecast_refresh_recovery_status",
                    "none",
                ),
            }
        )
    local_noise = _target_specific_normalization_noise(target, transition_history_meta)
    has_fresh_aligned_recent_evidence = freshness_meta.get(
        "has_fresh_aligned_recent_evidence",
        False,
    )

    def _restore_weaker_pending_posture(reset_reason: str) -> tuple[str, str, str, str, str, str, str, str]:
        nonlocal trust_policy, trust_policy_reason
        nonlocal pending_debt_status, pending_debt_reason
        nonlocal policy_debt_status, policy_debt_reason
        nonlocal class_normalization_status, class_normalization_reason
        restored_transition_status = transition_status
        restored_transition_reason = transition_reason
        restored_resolution_status = resolution_status
        restored_resolution_reason = resolution_reason
        if resolution_status == "cleared" and recent_pending_status in {"pending-support", "pending-caution"}:
            restored_transition_status = recent_pending_status
            restored_transition_reason = reset_reason
            restored_resolution_status = "none"
            restored_resolution_reason = ""
            if recent_pending_status == "pending-support":
                reverted_policy = target.get("pre_class_normalization_trust_policy", trust_policy)
                reverted_reason = target.get(
                    "pre_class_normalization_trust_policy_reason",
                    trust_policy_reason,
                )
                trust_policy = reverted_policy
                trust_policy_reason = (
                    reset_reason if reverted_policy == "verify-first" else reverted_reason
                )
                class_normalization_status = "candidate"
                class_normalization_reason = reset_reason
            else:
                pending_debt_status = pending_debt_status or "watch"
                pending_debt_reason = pending_debt_reason or reset_reason
                policy_debt_status = "watch"
                policy_debt_reason = reset_reason
        return (
            restored_transition_status,
            restored_transition_reason,
            restored_resolution_status,
            restored_resolution_reason,
            trust_policy,
            trust_policy_reason,
            pending_debt_status,
            pending_debt_reason,
        )

    if local_noise and current_side != "none":
        blocked_reason = "Local target instability still overrides healthy reacquisition freshness."
        if closure_likely_outcome == "confirm-soon":
            closure_likely_outcome = "hold"
        elif closure_likely_outcome == "expire-risk":
            closure_likely_outcome = "clear-risk"
        if closure_hysteresis_status == "confirmed-confirmation":
            closure_hysteresis_status = "pending-confirmation"
        elif closure_hysteresis_status == "confirmed-clearance":
            closure_hysteresis_status = "pending-clearance"
        closure_hysteresis_reason = blocked_reason
        return {
            "closure_forecast_persistence_reset_status": "blocked",
            "closure_forecast_persistence_reset_reason": blocked_reason,
            "transition_closure_likely_outcome": closure_likely_outcome,
            "closure_forecast_hysteresis_status": closure_hysteresis_status,
            "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "trust_policy": trust_policy,
            "trust_policy_reason": trust_policy_reason,
            "class_pending_debt_status": pending_debt_status,
            "class_pending_debt_reason": pending_debt_reason,
            "policy_debt_status": policy_debt_status,
            "policy_debt_reason": policy_debt_reason,
            "class_normalization_status": class_normalization_status,
            "class_normalization_reason": class_normalization_reason,
            "closure_forecast_reacquisition_status": reacquisition_status,
            "closure_forecast_reacquisition_reason": reacquisition_reason,
            "closure_forecast_reacquisition_age_runs": persistence_age_runs,
            "closure_forecast_reacquisition_persistence_score": persistence_score,
            "closure_forecast_reacquisition_persistence_status": persistence_status,
            "closure_forecast_reacquisition_persistence_reason": persistence_reason,
        }

    if current_side == "confirmation" and freshness_status == "mixed-age":
        if persistence_status in {
            "sustained-confirmation",
            "holding-confirmation",
        } and (
            churn_status != "churn" or has_fresh_aligned_recent_evidence
        ):
            softened_reason = (
                "Restored confirmation-side posture is still visible, but it is aging and has been stepped down from sustained strength."
            )
            softened_outcome = closure_likely_outcome
            if (
                softened_outcome == "hold"
                and reacquisition_status in {
                    "pending-confirmation-reacquisition",
                    "reacquired-confirmation",
                }
            ):
                softened_outcome = "confirm-soon"
            return {
                "closure_forecast_persistence_reset_status": "confirmation-softened",
                "closure_forecast_persistence_reset_reason": softened_reason,
                "transition_closure_likely_outcome": softened_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": softened_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "trust_policy": trust_policy,
                "trust_policy_reason": trust_policy_reason,
                "class_pending_debt_status": pending_debt_status,
                "class_pending_debt_reason": pending_debt_reason,
                "policy_debt_status": policy_debt_status,
                "policy_debt_reason": policy_debt_reason,
                "class_normalization_status": class_normalization_status,
                "class_normalization_reason": class_normalization_reason,
                "closure_forecast_reacquisition_status": reacquisition_status,
                "closure_forecast_reacquisition_reason": reacquisition_reason,
                "closure_forecast_reacquisition_age_runs": persistence_age_runs,
                "closure_forecast_reacquisition_persistence_score": persistence_score,
                "closure_forecast_reacquisition_persistence_status": "holding-confirmation",
                "closure_forecast_reacquisition_persistence_reason": softened_reason,
            }
        if persistence_status == "holding-confirmation" and churn_status == "churn":
            freshness_status = "stale"

    if current_side == "clearance" and freshness_status == "mixed-age":
        if persistence_status == "sustained-clearance" and (
            churn_status != "churn" or has_fresh_aligned_recent_evidence
        ):
            softened_reason = (
                "Restored clearance-side posture is still visible, but it is aging and has been stepped down from sustained strength."
            )
            return {
                "closure_forecast_persistence_reset_status": "clearance-softened",
                "closure_forecast_persistence_reset_reason": softened_reason,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": softened_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "trust_policy": trust_policy,
                "trust_policy_reason": trust_policy_reason,
                "class_pending_debt_status": pending_debt_status,
                "class_pending_debt_reason": pending_debt_reason,
                "policy_debt_status": policy_debt_status,
                "policy_debt_reason": policy_debt_reason,
                "class_normalization_status": class_normalization_status,
                "class_normalization_reason": class_normalization_reason,
                "closure_forecast_reacquisition_status": reacquisition_status,
                "closure_forecast_reacquisition_reason": reacquisition_reason,
                "closure_forecast_reacquisition_age_runs": persistence_age_runs,
                "closure_forecast_reacquisition_persistence_score": persistence_score,
                "closure_forecast_reacquisition_persistence_status": "holding-clearance",
                "closure_forecast_reacquisition_persistence_reason": softened_reason,
            }
        if persistence_status == "holding-clearance" and churn_status == "churn":
            freshness_status = "stale"

    needs_reset = (
        current_side in {"confirmation", "clearance"}
        and persistence_status
        in {
            "holding-confirmation",
            "holding-clearance",
            "sustained-confirmation",
            "sustained-clearance",
        }
        and (
            freshness_status in {"stale", "insufficient-data"}
            or not has_fresh_aligned_recent_evidence
            or (
                freshness_status == "mixed-age"
                and churn_status == "churn"
                and not has_fresh_aligned_recent_evidence
            )
        )
    )

    if needs_reset:
        if current_side == "confirmation":
            reset_reason = (
                "Restored confirmation-side posture has aged out enough that the stronger carry-forward has been withdrawn."
            )
            closure_likely_outcome = "hold"
            if closure_hysteresis_status == "confirmed-confirmation":
                closure_hysteresis_status = "pending-confirmation"
            closure_hysteresis_reason = reset_reason
            return {
                "closure_forecast_persistence_reset_status": "confirmation-reset",
                "closure_forecast_persistence_reset_reason": reset_reason,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "trust_policy": trust_policy,
                "trust_policy_reason": trust_policy_reason,
                "class_pending_debt_status": pending_debt_status,
                "class_pending_debt_reason": pending_debt_reason,
                "policy_debt_status": policy_debt_status,
                "policy_debt_reason": policy_debt_reason,
                "class_normalization_status": class_normalization_status,
                "class_normalization_reason": class_normalization_reason,
                "closure_forecast_reacquisition_status": "none",
                "closure_forecast_reacquisition_reason": reset_reason,
                "closure_forecast_reacquisition_age_runs": 0,
                "closure_forecast_reacquisition_persistence_score": 0.0,
                "closure_forecast_reacquisition_persistence_status": "none",
                "closure_forecast_reacquisition_persistence_reason": "",
            }

        reset_reason = (
            "Restored clearance-side posture has aged out enough that the stronger carry-forward has been withdrawn."
        )
        if closure_likely_outcome == "expire-risk":
            closure_likely_outcome = "clear-risk"
        elif closure_likely_outcome == "clear-risk":
            closure_likely_outcome = "hold"
        if closure_hysteresis_status == "confirmed-clearance":
            closure_hysteresis_status = "pending-clearance"
        closure_hysteresis_reason = reset_reason
        (
            transition_status,
            transition_reason,
            resolution_status,
            resolution_reason,
            trust_policy,
            trust_policy_reason,
            pending_debt_status,
            pending_debt_reason,
        ) = _restore_weaker_pending_posture(reset_reason)
        return {
            "closure_forecast_persistence_reset_status": "clearance-reset",
            "closure_forecast_persistence_reset_reason": reset_reason,
            "transition_closure_likely_outcome": closure_likely_outcome,
            "closure_forecast_hysteresis_status": closure_hysteresis_status,
            "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "trust_policy": trust_policy,
            "trust_policy_reason": trust_policy_reason,
            "class_pending_debt_status": pending_debt_status,
            "class_pending_debt_reason": pending_debt_reason,
            "policy_debt_status": policy_debt_status,
            "policy_debt_reason": policy_debt_reason,
            "class_normalization_status": class_normalization_status,
            "class_normalization_reason": class_normalization_reason,
            "closure_forecast_reacquisition_status": "none",
            "closure_forecast_reacquisition_reason": reset_reason,
            "closure_forecast_reacquisition_age_runs": 0,
            "closure_forecast_reacquisition_persistence_score": 0.0,
            "closure_forecast_reacquisition_persistence_status": "none",
            "closure_forecast_reacquisition_persistence_reason": "",
        }

    if (
        current_side == "clearance"
        and resolution_status == "cleared"
        and recent_pending_status in {"pending-support", "pending-caution"}
        and (
            freshness_status not in {"fresh", "mixed-age"}
            or decayed_clearance_rate < 0.50
            or persistence_status not in {"holding-clearance", "sustained-clearance"}
            or churn_status == "churn"
        )
    ):
        reset_reason = (
            "Restored clearance-side posture has aged out enough that the stronger carry-forward has been withdrawn."
        )
        (
            transition_status,
            transition_reason,
            resolution_status,
            resolution_reason,
            trust_policy,
            trust_policy_reason,
            pending_debt_status,
            pending_debt_reason,
        ) = _restore_weaker_pending_posture(reset_reason)
        return {
            "closure_forecast_persistence_reset_status": "clearance-reset",
            "closure_forecast_persistence_reset_reason": reset_reason,
            "transition_closure_likely_outcome": "hold",
            "closure_forecast_hysteresis_status": "pending-clearance",
            "closure_forecast_hysteresis_reason": reset_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "trust_policy": trust_policy,
            "trust_policy_reason": trust_policy_reason,
            "class_pending_debt_status": pending_debt_status,
            "class_pending_debt_reason": pending_debt_reason,
            "policy_debt_status": policy_debt_status,
            "policy_debt_reason": policy_debt_reason,
            "class_normalization_status": class_normalization_status,
            "class_normalization_reason": class_normalization_reason,
            "closure_forecast_reacquisition_status": "none",
            "closure_forecast_reacquisition_reason": reset_reason,
            "closure_forecast_reacquisition_age_runs": 0,
            "closure_forecast_reacquisition_persistence_score": 0.0,
            "closure_forecast_reacquisition_persistence_status": "none",
            "closure_forecast_reacquisition_persistence_reason": "",
        }

    return {
        "closure_forecast_persistence_reset_status": "none",
        "closure_forecast_persistence_reset_reason": "",
        "transition_closure_likely_outcome": closure_likely_outcome,
        "closure_forecast_hysteresis_status": closure_hysteresis_status,
        "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
        "class_reweight_transition_status": transition_status,
        "class_reweight_transition_reason": transition_reason,
        "class_transition_resolution_status": resolution_status,
        "class_transition_resolution_reason": resolution_reason,
        "trust_policy": trust_policy,
        "trust_policy_reason": trust_policy_reason,
        "class_pending_debt_status": pending_debt_status,
        "class_pending_debt_reason": pending_debt_reason,
        "policy_debt_status": policy_debt_status,
        "policy_debt_reason": policy_debt_reason,
        "class_normalization_status": class_normalization_status,
        "class_normalization_reason": class_normalization_reason,
        "closure_forecast_reacquisition_status": reacquisition_status,
        "closure_forecast_reacquisition_reason": reacquisition_reason,
        "closure_forecast_reacquisition_age_runs": persistence_age_runs,
        "closure_forecast_reacquisition_persistence_score": persistence_score,
        "closure_forecast_reacquisition_persistence_status": persistence_status,
        "closure_forecast_reacquisition_persistence_reason": persistence_reason,
    }


def _closure_forecast_reacquisition_hotspots(resolution_targets: list[dict], *, mode: str) -> list[dict]:
    grouped: dict[str, dict] = {}
    for target in resolution_targets:
        class_key = _target_class_key(target)
        if not class_key:
            continue
        current = {
            "scope": "class",
            "label": class_key,
            "closure_forecast_reacquisition_age_runs": target.get("closure_forecast_reacquisition_age_runs", 0),
            "closure_forecast_reacquisition_persistence_score": target.get("closure_forecast_reacquisition_persistence_score", 0.0),
            "closure_forecast_reacquisition_persistence_status": target.get("closure_forecast_reacquisition_persistence_status", "none"),
            "closure_forecast_recovery_churn_score": target.get("closure_forecast_recovery_churn_score", 0.0),
            "closure_forecast_recovery_churn_status": target.get("closure_forecast_recovery_churn_status", "none"),
            "recent_reacquisition_persistence_path": target.get("recent_reacquisition_persistence_path", ""),
            "recent_recovery_churn_path": target.get("recent_recovery_churn_path", ""),
        }
        existing = grouped.get(class_key)
        if existing is None or abs(current["closure_forecast_reacquisition_persistence_score"]) > abs(
            existing["closure_forecast_reacquisition_persistence_score"]
        ):
            grouped[class_key] = current
    hotspots = list(grouped.values())
    if mode == "just-reacquired":
        hotspots = [
            item for item in hotspots if item.get("closure_forecast_reacquisition_persistence_status") == "just-reacquired"
        ]
        hotspots.sort(
            key=lambda item: (
                -item.get("closure_forecast_reacquisition_age_runs", 0),
                -abs(item.get("closure_forecast_reacquisition_persistence_score", 0.0)),
                item.get("label", ""),
            )
        )
    elif mode == "holding":
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reacquisition_persistence_status")
            in {
                "holding-confirmation",
                "holding-clearance",
                "sustained-confirmation",
                "sustained-clearance",
            }
        ]
        hotspots.sort(
            key=lambda item: (
                -item.get("closure_forecast_reacquisition_age_runs", 0),
                -abs(item.get("closure_forecast_reacquisition_persistence_score", 0.0)),
                item.get("label", ""),
            )
        )
    else:
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_recovery_churn_status") in {"watch", "churn", "blocked"}
        ]
        hotspots.sort(
            key=lambda item: (
                -item.get("closure_forecast_recovery_churn_score", 0.0),
                -item.get("closure_forecast_reacquisition_age_runs", 0),
                item.get("label", ""),
            )
        )
    return hotspots[:5]


def _closure_forecast_reacquisition_freshness_hotspots(
    resolution_targets: list[dict],
    *,
    mode: str,
) -> list[dict]:
    grouped: dict[str, dict] = {}
    for target in resolution_targets:
        class_key = _target_class_key(target)
        if not class_key:
            continue
        current = {
            "scope": "class",
            "label": class_key,
            "closure_forecast_reacquisition_freshness_status": target.get(
                "closure_forecast_reacquisition_freshness_status",
                "insufficient-data",
            ),
            "decayed_reacquired_confirmation_rate": target.get(
                "decayed_reacquired_confirmation_rate",
                0.0,
            ),
            "decayed_reacquired_clearance_rate": target.get(
                "decayed_reacquired_clearance_rate",
                0.0,
            ),
            "recent_reacquisition_signal_mix": target.get("recent_reacquisition_signal_mix", ""),
            "recent_reacquisition_persistence_path": target.get(
                "recent_reacquisition_persistence_path",
                "",
            ),
            "dominant_count": max(
                target.get("decayed_reacquired_confirmation_rate", 0.0),
                target.get("decayed_reacquired_clearance_rate", 0.0),
            ),
            "reacquisition_event_count": len(
                [
                    part
                    for part in (target.get("recent_reacquisition_persistence_path", "") or "").split(" -> ")
                    if part
                ]
            ),
        }
        existing = grouped.get(class_key)
        if existing is None or current["dominant_count"] > existing["dominant_count"]:
            grouped[class_key] = current

    hotspots = list(grouped.values())
    if mode == "fresh":
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reacquisition_freshness_status") == "fresh"
            and item.get("dominant_count", 0.0) > 0.0
        ]
    else:
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reacquisition_freshness_status") == "stale"
            and item.get("dominant_count", 0.0) > 0.0
        ]
    hotspots.sort(
        key=lambda item: (
            -item.get("dominant_count", 0.0),
            -item.get("reacquisition_event_count", 0),
            item.get("label", ""),
        )
    )
    return hotspots[:5]


def _closure_forecast_reacquisition_freshness_summary(
    primary_target: dict,
    stale_reacquisition_hotspots: list[dict],
    fresh_reacquisition_signal_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    freshness_status = primary_target.get(
        "closure_forecast_reacquisition_freshness_status",
        "insufficient-data",
    )
    if freshness_status == "fresh":
        return f"{label} still has recent reacquired closure-forecast evidence that is current enough to keep the restored posture trusted."
    if freshness_status == "mixed-age":
        return f"{label} still has useful reacquired closure-forecast memory, but the restored posture is no longer getting fully fresh reinforcement."
    if freshness_status == "stale":
        return f"{label} is leaning on older reacquired forecast strength more than fresh runs, so stronger restored posture should not keep carrying forward on memory alone."
    if fresh_reacquisition_signal_hotspots:
        hotspot = fresh_reacquisition_signal_hotspots[0]
        return (
            f"Fresh reacquisition evidence is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes can keep restored posture more safely than older carry-forward."
        )
    if stale_reacquisition_hotspots:
        hotspot = stale_reacquisition_hotspots[0]
        return (
            f"Older reacquired forecast strength is lingering most around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes should keep resetting restored posture when fresh follow-through stops."
        )
    return "Reacquired closure-forecast memory is still too lightly exercised to say whether restored posture is being reinforced by fresh evidence or older carry-forward."


def _closure_forecast_persistence_reset_summary(
    primary_target: dict,
    stale_reacquisition_hotspots: list[dict],
    fresh_reacquisition_signal_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    reset_status = primary_target.get("closure_forecast_persistence_reset_status", "none")
    freshness_status = primary_target.get(
        "closure_forecast_reacquisition_freshness_status",
        "insufficient-data",
    )
    confirmation_rate = primary_target.get("decayed_reacquired_confirmation_rate", 0.0)
    clearance_rate = primary_target.get("decayed_reacquired_clearance_rate", 0.0)
    if reset_status == "confirmation-softened":
        return f"Restored confirmation-side posture for {label} is still visible, but it is aging and has been stepped down from sustained strength."
    if reset_status == "clearance-softened":
        return f"Restored clearance-side posture for {label} is still visible, but it is aging and has been stepped down from sustained strength."
    if reset_status == "confirmation-reset":
        return f"Restored confirmation-side posture for {label} has aged out enough that the stronger carry-forward has been withdrawn."
    if reset_status == "clearance-reset":
        return f"Restored clearance-side posture for {label} has aged out enough that the stronger carry-forward has been withdrawn."
    if reset_status == "blocked":
        return primary_target.get(
            "closure_forecast_persistence_reset_reason",
            f"Local target instability still overrides healthy reacquisition freshness for {label}.",
        )
    if freshness_status == "fresh" and confirmation_rate >= clearance_rate:
        return f"Fresh reacquisition evidence for {label} is still reinforcing confirmation-side restored posture more than clearance pressure."
    if freshness_status == "fresh":
        return f"Fresh reacquisition evidence for {label} is still reinforcing clearance-side restored posture more than confirmation-side carry-forward."
    if freshness_status == "mixed-age":
        return f"Reacquired posture for {label} is aging enough that it can keep holding, but it should no longer stay indefinitely at sustained strength."
    if stale_reacquisition_hotspots:
        hotspot = stale_reacquisition_hotspots[0]
        return (
            f"Reacquired posture is aging out fastest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes should reset restored carry-forward instead of relying on older follow-through."
        )
    if fresh_reacquisition_signal_hotspots:
        hotspot = fresh_reacquisition_signal_hotspots[0]
        return (
            f"Fresh reacquisition follow-through is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes can preserve restored posture longer than aging carry-forward elsewhere."
        )
    return "No persistence reset is changing the current restored closure-forecast posture right now."



def _closure_forecast_reacquisition_persistence_summary(
    primary_target: dict,
    just_reacquired_hotspots: list[dict],
    holding_reacquisition_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    status = primary_target.get("closure_forecast_reacquisition_persistence_status", "none")
    age_runs = primary_target.get("closure_forecast_reacquisition_age_runs", 0)
    score = primary_target.get("closure_forecast_reacquisition_persistence_score", 0.0)
    if status == "just-reacquired":
        return f"{label} has only just re-earned stronger closure-forecast posture, so it is still fragile ({score:.2f}; {age_runs} run)."
    if status == "holding-confirmation":
        return f"Confirmation-side reacquisition for {label} has held long enough to keep the restored forecast in place ({score:.2f}; {age_runs} runs)."
    if status == "holding-clearance":
        return f"Clearance-side reacquisition for {label} has held long enough to keep the restored caution in place ({score:.2f}; {age_runs} runs)."
    if status == "sustained-confirmation":
        return f"Confirmation-side reacquisition for {label} is now holding with enough follow-through to trust the restored forecast more ({score:.2f}; {age_runs} runs)."
    if status == "sustained-clearance":
        return f"Clearance-side reacquisition for {label} is now holding with enough follow-through to trust the restored caution more ({score:.2f}; {age_runs} runs)."
    if status == "reversing":
        return f"The restored closure-forecast posture for {label} is already weakening, so it is being softened again ({score:.2f})."
    if status == "insufficient-data":
        return f"Reacquisition for {label} is still too lightly exercised to say whether the restored forecast can hold."
    if just_reacquired_hotspots:
        hotspot = just_reacquired_hotspots[0]
        return (
            f"Newly restored forecast posture is most fragile around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes still need follow-through before the restored forecast can be trusted."
        )
    if holding_reacquisition_hotspots:
        hotspot = holding_reacquisition_hotspots[0]
        return (
            f"Restored forecast posture is holding most cleanly around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes are closest to keeping reacquired strength safely."
        )
    return "No reacquired closure-forecast posture is active enough yet to judge whether it can hold."


def _closure_forecast_recovery_churn_summary(
    primary_target: dict,
    recovery_churn_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    status = primary_target.get("closure_forecast_recovery_churn_status", "none")
    score = primary_target.get("closure_forecast_recovery_churn_score", 0.0)
    if status == "watch":
        return f"Recovery for {label} is wobbling enough that restored forecast strength may soften soon ({score:.2f})."
    if status == "churn":
        return f"Recovery for {label} is flipping enough that restored forecast posture should soften quickly ({score:.2f})."
    if status == "blocked":
        return primary_target.get(
            "closure_forecast_recovery_churn_reason",
            f"Local target instability is preventing positive confirmation-side persistence for {label}.",
        )
    if recovery_churn_hotspots:
        hotspot = recovery_churn_hotspots[0]
        return (
            f"Recovery churn is highest around {hotspot.get('label', 'recent hotspots')}, "
            "so restored forecast posture there should soften quickly if the wobble continues."
        )
    return "No meaningful recovery churn is active right now."


def _target_class_reweight_history(target: dict, reweight_events: list[dict]) -> dict:
    class_key = _target_class_key(target)
    matching_events = [event for event in reweight_events if event.get("class_key") == class_key][:CLASS_TRANSITION_WINDOW_RUNS]
    signals = [_class_signal_from_reweight_event(event) for event in matching_events]
    relevant_signals = [signal for signal in signals if abs(signal) >= 0.05]
    weighted_total = 0.0
    weight_sum = 0.0
    for index, signal in enumerate(signals):
        weight = (1.0, 0.8, 0.6, 0.4)[min(index, CLASS_TRANSITION_WINDOW_RUNS - 1)]
        weighted_total += signal * weight
        weight_sum += weight
    momentum_score = _clamp_round(
        weighted_total / max(weight_sum, 1.0),
        lower=-0.95,
        upper=0.95,
    )
    directions = [
        _normalized_class_reweight_direction(
            event.get("class_trust_reweight_direction", "neutral"),
            event.get("class_trust_reweight_score", 0.0),
        )
        for event in matching_events
    ]
    flip_count = _class_direction_flip_count(directions)
    current_direction = directions[0] if directions else "neutral"
    earlier_majority = _class_direction_majority(directions[1:])
    positive_count = sum(1 for signal in relevant_signals if signal > 0)
    negative_count = sum(1 for signal in relevant_signals if signal < 0)

    if len(relevant_signals) < 2:
        momentum_status = "insufficient-data"
    elif flip_count >= 2:
        momentum_status = "unstable"
    elif _class_direction_reversing(current_direction, earlier_majority):
        momentum_status = "reversing"
    elif positive_count >= 2 and momentum_score >= 0.20:
        momentum_status = "sustained-support"
    elif negative_count >= 2 and momentum_score <= -0.20:
        momentum_status = "sustained-caution"
    else:
        momentum_status = "building"

    if flip_count >= 2:
        stability_status = "oscillating"
    elif flip_count == 1 or momentum_status in {"building", "insufficient-data", "reversing"}:
        stability_status = "watch"
    else:
        stability_status = "stable"

    return {
        "class_trust_momentum_score": momentum_score,
        "class_trust_momentum_status": momentum_status,
        "class_reweight_stability_status": stability_status,
        "recent_class_reweight_path": " -> ".join(directions) if directions else "",
        "class_direction_flip_count": flip_count,
    }


def _class_signal_from_reweight_event(event: dict) -> float:
    score = float(event.get("class_trust_reweight_score", 0.0) or 0.0)
    direction = _normalized_class_reweight_direction(
        event.get("class_trust_reweight_direction", "neutral"),
        score,
    )
    if direction == "supporting-normalization":
        return abs(score) if abs(score) >= 0.05 else 0.05
    if direction == "supporting-caution":
        return -abs(score) if abs(score) >= 0.05 else -0.05
    return _clamp_round(score, lower=-0.19, upper=0.19)


def _normalized_class_reweight_direction(direction: str, score: float) -> str:
    if direction in {"supporting-normalization", "supporting-caution", "neutral"}:
        return direction
    if score >= 0.20:
        return "supporting-normalization"
    if score <= -0.20:
        return "supporting-caution"
    return "neutral"


def _class_direction_flip_count(directions: list[str]) -> int:
    non_neutral = [direction for direction in directions if direction != "neutral"]
    if len(non_neutral) < 2:
        return 0
    return sum(
        1 for previous, current in zip(non_neutral, non_neutral[1:]) if current != previous
    )


def _class_direction_majority(directions: list[str]) -> str:
    support_count = sum(1 for direction in directions if direction == "supporting-normalization")
    caution_count = sum(1 for direction in directions if direction == "supporting-caution")
    if support_count > caution_count:
        return "supporting-normalization"
    if caution_count > support_count:
        return "supporting-caution"
    return "neutral"


def _class_direction_reversing(current_direction: str, earlier_majority: str) -> bool:
    if current_direction == "neutral" or earlier_majority == "neutral":
        return False
    return current_direction != earlier_majority


def _class_trust_momentum_for_target(
    target: dict,
    history_meta: dict,
    confidence_calibration: dict,
    *,
    trust_policy: str,
    trust_policy_reason: str,
    policy_debt_status: str,
    policy_debt_reason: str,
    class_normalization_status: str,
    class_normalization_reason: str,
) -> tuple[str, str, str, str, str, str, str, str]:
    momentum_status = history_meta.get("class_trust_momentum_status", "insufficient-data")
    stability_status = history_meta.get("class_reweight_stability_status", "watch")
    local_noise = _target_specific_normalization_noise(target, history_meta)
    calibration_status = confidence_calibration.get("confidence_validation_status", "insufficient-data")
    reweight_effect = target.get("class_trust_reweight_effect", "none")

    if (
        local_noise
        and target.get("class_trust_reweight_direction") == "supporting-normalization"
        and target.get("class_trust_reweight_score", 0.0) >= 0.20
    ):
        reverted_policy = target.get("pre_class_normalization_trust_policy", trust_policy)
        reverted_reason = target.get("pre_class_normalization_trust_policy_reason", trust_policy_reason)
        blocked_reason = (
            "Positive class strengthening is blocked because local reopen, flip, or blocked-recovery noise still overrides the class signal."
        )
        if reweight_effect == "normalization-boosted":
            return (
                "blocked",
                blocked_reason,
                reverted_policy,
                blocked_reason if reverted_policy == "verify-first" else reverted_reason,
                policy_debt_status,
                policy_debt_reason,
                "candidate",
                blocked_reason,
            )
        return (
            "blocked",
            blocked_reason,
            trust_policy,
            trust_policy_reason,
            policy_debt_status,
            policy_debt_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    if reweight_effect == "normalization-boosted":
        if momentum_status == "sustained-support" and stability_status != "oscillating":
            confirmed_reason = (
                "Fresh class support has stayed strong long enough to confirm broader normalization for this target."
            )
            return (
                "confirmed-support",
                confirmed_reason,
                trust_policy,
                confirmed_reason,
                policy_debt_status,
                policy_debt_reason,
                class_normalization_status,
                confirmed_reason,
            )
        pending_reason = (
            "The class signal is visible, but it has not stayed strong long enough to confirm broader normalization yet."
        )
        reverted_policy = target.get("pre_class_normalization_trust_policy", trust_policy)
        reverted_reason = target.get("pre_class_normalization_trust_policy_reason", trust_policy_reason)
        return (
            "pending-support",
            pending_reason,
            reverted_policy,
            pending_reason if reverted_policy == "verify-first" else reverted_reason,
            policy_debt_status,
            policy_debt_reason,
            "candidate",
            pending_reason,
        )

    if reweight_effect == "policy-debt-strengthened":
        if momentum_status == "sustained-caution" and stability_status != "oscillating":
            confirmed_reason = (
                "Caution-heavy class evidence has stayed strong long enough to confirm broader class caution."
            )
            return (
                "confirmed-caution",
                confirmed_reason,
                trust_policy,
                trust_policy_reason,
                policy_debt_status,
                confirmed_reason,
                class_normalization_status,
                class_normalization_reason,
            )
        pending_reason = (
            "The caution-heavy class signal is visible, but it has not stayed strong long enough to confirm sticky class caution yet."
        )
        return (
            "pending-caution",
            pending_reason,
            trust_policy,
            trust_policy_reason,
            "watch",
            pending_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    if class_normalization_status == "applied" and momentum_status in {"reversing", "unstable"}:
        softened_reason = (
            "Recent class evidence is changing direction, so earlier class normalization is being softened back to candidate."
        )
        reverted_policy = target.get("pre_class_normalization_trust_policy", trust_policy)
        reverted_reason = target.get("pre_class_normalization_trust_policy_reason", trust_policy_reason)
        if trust_policy == "act-with-review" and reverted_policy == "verify-first":
            trust_policy = reverted_policy
            trust_policy_reason = softened_reason
        else:
            trust_policy_reason = softened_reason
        return (
            "none",
            softened_reason,
            trust_policy,
            trust_policy_reason,
            policy_debt_status,
            policy_debt_reason,
            "candidate",
            softened_reason,
        )

    if policy_debt_status == "class-debt" and momentum_status in {"reversing", "unstable"}:
        softened_reason = (
            "Recent class evidence is changing direction, so sticky class caution is being softened back to watch."
        )
        return (
            "none",
            softened_reason,
            trust_policy,
            trust_policy_reason,
            "watch",
            softened_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    if calibration_status != "healthy" and reweight_effect == "normalization-boosted":
        blocked_reason = "Positive class strengthening remains visible, but calibration is not healthy enough to confirm it."
        reverted_policy = target.get("pre_class_normalization_trust_policy", trust_policy)
        reverted_reason = target.get("pre_class_normalization_trust_policy_reason", trust_policy_reason)
        return (
            "blocked",
            blocked_reason,
            reverted_policy,
            blocked_reason if reverted_policy == "verify-first" else reverted_reason,
            policy_debt_status,
            policy_debt_reason,
            "candidate",
            blocked_reason,
        )

    return (
        "none",
        "",
        trust_policy,
        trust_policy_reason,
        policy_debt_status,
        policy_debt_reason,
        class_normalization_status,
        class_normalization_reason,
    )


def _class_transition_resolution_for_target(
    target: dict,
    history_meta: dict,
    confidence_calibration: dict,
    *,
    trust_policy: str,
    trust_policy_reason: str,
    transition_status: str,
    transition_reason: str,
    policy_debt_status: str,
    policy_debt_reason: str,
    class_normalization_status: str,
    class_normalization_reason: str,
) -> tuple[str, str, str, str, str, str, str, str, str, str, str, str]:
    current_transition_status = history_meta.get("current_transition_status", transition_status)
    transition_age_runs = history_meta.get("class_transition_age_runs", 0)
    current_strengthening = history_meta.get("current_transition_strengthening", False)
    current_neutral = history_meta.get("current_transition_neutral", False)
    current_reversed = history_meta.get("current_transition_reversed", False)
    current_lost_pending_support = history_meta.get("current_lost_pending_support", False)
    recent_pending_status = history_meta.get("recent_pending_status", "none")
    recent_pending_age_runs = history_meta.get("recent_pending_age_runs", 0)
    if current_transition_status == "blocked":
        blocked_reason = transition_reason or (
            "Local target instability is preventing positive class strengthening."
        )
        return (
            "blocked",
            blocked_reason,
            "blocked",
            blocked_reason,
            "blocked",
            blocked_reason,
            trust_policy,
            trust_policy_reason,
            policy_debt_status,
            policy_debt_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    if current_transition_status in {"confirmed-support", "confirmed-caution"}:
        confirmed_reason = transition_reason or (
            "The earlier pending class signal persisted long enough to confirm a broader class posture."
        )
        return (
            "none",
            "",
            "confirmed",
            confirmed_reason,
            current_transition_status,
            confirmed_reason,
            trust_policy,
            trust_policy_reason,
            policy_debt_status,
            policy_debt_reason,
            class_normalization_status,
            class_normalization_reason,
        )
    if current_transition_status in {"pending-support", "pending-caution"}:
        if transition_age_runs >= 3 and not current_strengthening:
            stalled_reason = (
                "The same pending class signal has lingered without enough strengthening, so it should stay visible but unconfirmed."
            )
            return (
                "stalled",
                stalled_reason,
                "none",
                "",
                current_transition_status,
                transition_reason or stalled_reason,
                trust_policy,
                trust_policy_reason,
                policy_debt_status,
                policy_debt_reason,
                class_normalization_status,
                class_normalization_reason,
            )
        if transition_age_runs >= 2 and not current_strengthening:
            holding_reason = (
                "The pending class signal is still visible, but it is no longer strengthening enough to confirm yet."
            )
            return (
                "holding",
                holding_reason,
                "none",
                "",
                current_transition_status,
                transition_reason or holding_reason,
                trust_policy,
                trust_policy_reason,
                policy_debt_status,
                policy_debt_reason,
                class_normalization_status,
                class_normalization_reason,
            )
        building_reason = (
            "The pending class signal is still accumulating in the same direction and may confirm soon."
        )
        return (
            "building",
            building_reason,
            "none",
            "",
            current_transition_status,
            transition_reason or building_reason,
            trust_policy,
            trust_policy_reason,
            policy_debt_status,
            policy_debt_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    if recent_pending_status in {"pending-support", "pending-caution"}:
        if recent_pending_age_runs >= CLASS_PENDING_RESOLUTION_WINDOW_RUNS and (
            current_neutral or current_reversed or current_lost_pending_support
        ):
            expired_reason = (
                "The earlier pending class signal lasted through the full resolution window without confirmation and has now aged out."
            )
            return (
                "expired",
                expired_reason,
                "expired",
                expired_reason,
                "none",
                expired_reason,
                trust_policy,
                trust_policy_reason,
                policy_debt_status,
                policy_debt_reason,
                class_normalization_status,
                class_normalization_reason,
            )
        if current_neutral or current_reversed or current_lost_pending_support:
            cleared_reason = (
                "The earlier pending class signal faded before it earned confirmation, so it has been cleared."
            )
            return (
                "none",
                "",
                "cleared",
                cleared_reason,
                "none",
                cleared_reason,
                trust_policy,
                trust_policy_reason,
                policy_debt_status,
                policy_debt_reason,
                class_normalization_status,
                class_normalization_reason,
            )

    return (
        "none",
        "",
        "none",
        "",
        current_transition_status,
        transition_reason,
        trust_policy,
        trust_policy_reason,
        policy_debt_status,
        policy_debt_reason,
        class_normalization_status,
        class_normalization_reason,
    )


def _class_momentum_hotspots(resolution_targets: list[dict], *, mode: str) -> list[dict]:
    grouped: dict[str, dict] = {}
    for target in resolution_targets:
        class_key = _target_class_key(target)
        if not class_key:
            continue
        existing = grouped.get(class_key)
        current = {
            "scope": "class",
            "label": class_key,
            "momentum_score": target.get("class_trust_momentum_score", 0.0),
            "momentum_status": target.get("class_trust_momentum_status", "insufficient-data"),
            "stability_status": target.get("class_reweight_stability_status", "watch"),
            "recent_class_reweight_path": target.get("recent_class_reweight_path", ""),
        }
        if existing is None or abs(current["momentum_score"]) > abs(existing["momentum_score"]):
            grouped[class_key] = current
    hotspots = list(grouped.values())
    if mode == "sustained":
        hotspots = [
            item
            for item in hotspots
            if item.get("momentum_status") in {"sustained-support", "sustained-caution"}
        ]
        hotspots.sort(
            key=lambda item: (
                -abs(item.get("momentum_score", 0.0)),
                item.get("label", ""),
            )
        )
    else:
        hotspots = [item for item in hotspots if item.get("stability_status") == "oscillating"]
        hotspots.sort(
            key=lambda item: (
                -abs(item.get("momentum_score", 0.0)),
                item.get("label", ""),
            )
        )
    return hotspots[:5]


def _class_transition_hotspots(resolution_targets: list[dict], *, mode: str) -> list[dict]:
    grouped: dict[str, dict] = {}
    for target in resolution_targets:
        class_key = _target_class_key(target)
        if not class_key:
            continue
        existing = grouped.get(class_key)
        current = {
            "scope": "class",
            "label": class_key,
            "transition_age_runs": target.get("class_transition_age_runs", 0),
            "health_status": target.get("class_transition_health_status", "none"),
            "resolution_status": target.get("class_transition_resolution_status", "none"),
            "recent_transition_path": target.get("recent_transition_path", ""),
        }
        if existing is None or current["transition_age_runs"] > existing["transition_age_runs"]:
            grouped[class_key] = current

    hotspots = list(grouped.values())
    if mode == "stalled":
        hotspots = [
            item
            for item in hotspots
            if item.get("health_status") in {"stalled", "expired"}
        ]
    else:
        hotspots = [
            item
            for item in hotspots
            if item.get("resolution_status") in {"confirmed", "cleared", "expired"}
        ]
    hotspots.sort(
        key=lambda item: (
            -item.get("transition_age_runs", 0),
            item.get("label", ""),
        )
    )
    return hotspots[:5]


def _class_momentum_summary(
    primary_target: dict,
    sustained_class_hotspots: list[dict],
    oscillating_class_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    status = primary_target.get("class_trust_momentum_status", "insufficient-data")
    transition_status = primary_target.get("class_reweight_transition_status", "none")
    score = primary_target.get("class_trust_momentum_score", 0.0)
    if transition_status == "confirmed-support":
        return f"{label} now has class support that stayed strong long enough to confirm broader normalization ({score:.2f})."
    if transition_status == "confirmed-caution":
        return f"{label} now has caution-heavy class evidence that stayed strong long enough to confirm broader caution ({score:.2f})."
    if transition_status == "pending-support":
        return f"{label} shows healthier class support, but it has not stayed persistent enough to confirm broader normalization yet ({score:.2f})."
    if transition_status == "pending-caution":
        return f"{label} shows caution-heavy class evidence, but it has not stayed persistent enough to confirm sticky class caution yet ({score:.2f})."
    if transition_status == "blocked":
        return primary_target.get(
            "class_reweight_transition_reason",
            f"{label} still has local target noise blocking positive class strengthening.",
        )
    if status == "sustained-support":
        return f"Fresh class evidence around {label} has stayed strong long enough to support broader normalization ({score:.2f})."
    if status == "sustained-caution":
        return f"Caution-heavy class evidence around {label} has stayed strong long enough to support broader caution ({score:.2f})."
    if status == "building":
        return f"{label} is trending in one class direction, but the signal has not held long enough to lock in ({score:.2f})."
    if status == "reversing":
        return f"Recent class evidence around {label} is changing direction, so earlier class guidance is being softened ({score:.2f})."
    if status == "unstable":
        return f"Recent class evidence around {label} is oscillating too much to safely strengthen class posture ({score:.2f})."
    if sustained_class_hotspots:
        hotspot = sustained_class_hotspots[0]
        return (
            f"Recent class momentum is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "but the current target has not built enough sustained class direction yet."
        )
    if oscillating_class_hotspots:
        hotspot = oscillating_class_hotspots[0]
        return (
            f"Recent class guidance is bouncing most around {hotspot.get('label', 'recent hotspots')}, "
            "so stronger class shifts there should wait for persistence."
        )
    return "Class momentum is still too lightly exercised to say whether recent class guidance is sustained or unstable."


def _class_reweight_stability_summary(
    primary_target: dict,
    oscillating_class_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    stability_status = primary_target.get("class_reweight_stability_status", "watch")
    recent_path = primary_target.get("recent_class_reweight_path", "")
    if stability_status == "oscillating":
        return f"Class guidance for {label} is bouncing too much to strengthen safely right now: {recent_path or 'no stable path yet'}."
    if stability_status == "watch":
        return f"Class guidance for {label} is still settling and should be watched for one more stable stretch: {recent_path or 'signal is still building'}."
    if recent_path:
        return f"Class guidance for {label} is stable across the recent path: {recent_path}."
    if oscillating_class_hotspots:
        hotspot = oscillating_class_hotspots[0]
        return (
            f"Class stability is weakest around {hotspot.get('label', 'recent hotspots')}, "
            "so broader class strengthening should wait there."
        )
    return "Recent class guidance is stable enough that no extra hysteresis warning is needed."


def _class_transition_health_summary(
    primary_target: dict,
    stalled_transition_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    health_status = primary_target.get("class_transition_health_status", "none")
    age_runs = primary_target.get("class_transition_age_runs", 0)
    if health_status == "building":
        return f"{label} still has a pending class signal that is accumulating and may confirm soon ({age_runs} run(s))."
    if health_status == "holding":
        return f"{label} still has a visible pending class signal, but it is no longer getting stronger ({age_runs} run(s))."
    if health_status == "stalled":
        return f"{label} has kept the same pending class signal for {age_runs} run(s) without enough strengthening, so it stays unconfirmed."
    if health_status == "expired":
        return f"{label} let its pending class signal age out after {age_runs} run(s), so that pending state should no longer influence posture."
    if health_status == "blocked":
        return primary_target.get(
            "class_transition_health_reason",
            f"{label} still has local target instability blocking positive class strengthening.",
        )
    if stalled_transition_hotspots:
        hotspot = stalled_transition_hotspots[0]
        return (
            f"Pending class transitions are stalling most around {hotspot.get('label', 'recent hotspots')}, "
            "so those pending states should be watched for expiry."
        )
    return "No active pending class transition is building or stalling right now."


def _class_transition_resolution_summary(
    primary_target: dict,
    resolving_transition_hotspots: list[dict],
    stalled_transition_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    resolution_status = primary_target.get("class_transition_resolution_status", "none")
    if resolution_status == "confirmed":
        return f"{label} resolved its earlier pending class transition into a confirmed broader class posture."
    if resolution_status == "cleared":
        return f"{label} lost the earlier pending class signal before it earned confirmation, so the pending state was cleared."
    if resolution_status == "expired":
        return f"{label} let the earlier pending class signal age out without confirmation, so the pending state expired."
    if resolution_status == "blocked":
        return primary_target.get(
            "class_transition_resolution_reason",
            f"{label} still has local target instability blocking positive class strengthening.",
        )
    if resolving_transition_hotspots:
        hotspot = resolving_transition_hotspots[0]
        return (
            f"Recent pending class transitions are resolving most clearly around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes are proving whether pending support should confirm or clear."
        )
    if stalled_transition_hotspots:
        hotspot = stalled_transition_hotspots[0]
        return (
            f"Pending class transitions are stalling most around {hotspot.get('label', 'recent hotspots')}, "
            "so those pending states should not linger indefinitely."
        )
    return "No pending class transition has just confirmed, cleared, or expired in the recent window."


def _clamp_round(value: float, *, lower: float, upper: float) -> float:
    return round(max(lower, min(upper, value)), 2)


def _retirement_policy_events(
    history: list[dict],
    *,
    current_primary_target: dict,
    current_generated_at: str,
) -> list[dict]:
    events: list[dict] = []
    if current_primary_target and current_primary_target.get("trust_policy"):
        events.append(
            {
                "key": _queue_identity(current_primary_target),
                "class_key": _target_class_key(current_primary_target),
                "label": _target_label(current_primary_target),
                "trust_policy": _retirement_source_policy(current_primary_target),
                "generated_at": current_generated_at or "",
                "lane": current_primary_target.get("lane", ""),
                "kind": current_primary_target.get("kind", ""),
                "decision_memory_status": current_primary_target.get("decision_memory_status", ""),
                "last_outcome": current_primary_target.get("last_outcome", ""),
                "trust_exception_status": current_primary_target.get("trust_exception_status", "none"),
                "trust_recovery_status": current_primary_target.get("trust_recovery_status", "none"),
            }
        )
    for entry in history[: HISTORY_WINDOW_RUNS - 1]:
        summary = entry.get("operator_summary") or {}
        primary_target = summary.get("primary_target") or {}
        trust_policy = summary.get("primary_target_trust_policy", "")
        if not primary_target or not trust_policy:
            continue
        events.append(
            {
                "key": _queue_identity(primary_target),
                "class_key": _target_class_key(primary_target),
                "label": _target_label(primary_target),
                "trust_policy": trust_policy,
                "generated_at": entry.get("generated_at", ""),
                "lane": primary_target.get("lane", ""),
                "kind": primary_target.get("kind", ""),
                "decision_memory_status": summary.get("decision_memory_status", ""),
                "last_outcome": summary.get("primary_target_last_outcome", ""),
                "trust_exception_status": summary.get("primary_target_exception_status", "none"),
                "trust_recovery_status": summary.get("primary_target_trust_recovery_status", "none"),
            }
        )
    return sorted(events, key=lambda item: item.get("generated_at", ""), reverse=True)


def _retirement_source_policy(target: dict) -> str:
    return (
        target.get("pre_retirement_trust_policy")
        or target.get("trust_policy")
        or target.get("base_trust_policy")
        or "monitor"
    )


def _target_retirement_history(
    target: dict,
    retirement_events: list[dict],
    historical_cases: list[dict],
) -> dict:
    key = _queue_identity(target)
    class_key = _target_class_key(target)
    target_events = [event for event in retirement_events if event.get("key") == key]
    class_events = [event for event in retirement_events if event.get("class_key") == class_key]
    target_cases = [case for case in historical_cases if case.get("key") == key]
    class_cases = [case for case in historical_cases if case.get("class_key") == class_key]
    target_policies = [event.get("trust_policy", "monitor") for event in target_events[:EXCEPTION_RETIREMENT_WINDOW_RUNS]]
    class_policies = [event.get("trust_policy", "monitor") for event in class_events[:EXCEPTION_RETIREMENT_WINDOW_RUNS]]
    target_lanes = [event.get("lane", "") for event in target_events[:EXCEPTION_RETIREMENT_WINDOW_RUNS]]
    return {
        "stable_after_exception_runs": _stable_policy_run_count(target_policies),
        "recent_retirement_path": " -> ".join(target_policies[:EXCEPTION_RETIREMENT_WINDOW_RUNS])
        or " -> ".join(class_policies[:EXCEPTION_RETIREMENT_WINDOW_RUNS]),
        "recent_policy_flip_count": _policy_flip_count(target_policies),
        "same_or_lower_pressure_path": _same_or_lower_pressure_path(target_lanes),
        "recent_reopened": any(
            event.get("decision_memory_status") == "reopened" or event.get("last_outcome") == "reopened"
            for event in target_events[:EXCEPTION_RETIREMENT_WINDOW_RUNS]
        ),
        "latest_case_outcome": _latest_case_outcome(target_cases, class_cases),
        "target_cases": target_cases,
        "class_cases": class_cases,
    }


def _recovery_confidence_for_target(
    target: dict,
    history_meta: dict,
    confidence_calibration: dict,
) -> tuple[float, str, list[str]]:
    score = 0.20
    calibration_status = confidence_calibration.get("confidence_validation_status", "insufficient-data")
    calibration_reason = ""
    stability_reason = ""
    exception_reason = ""
    blockers: list[tuple[float, str]] = []

    if calibration_status == "healthy":
        score += 0.20
        calibration_reason = "Healthy calibration supports relaxing the earlier soft caution."
    elif calibration_status == "noisy":
        score -= 0.10
        calibration_reason = "Noisy calibration still argues for keeping caution in place."
        blockers.append((-0.10, "Calibration is still noisy, so retiring the softer posture would be premature."))
    elif calibration_status == "insufficient-data":
        score -= 0.05
        calibration_reason = "Calibration is still lightly exercised, so retirement confidence stays softer."
        blockers.append((-0.05, "Calibration history is still too light to prove the softer posture can retire."))
    else:
        calibration_reason = "Mixed calibration keeps retirement confidence in the middle for now."

    recent_reopened = history_meta.get("recent_reopened", False)
    recent_policy_flip_count = history_meta.get("recent_policy_flip_count", 0)
    same_or_lower_pressure_path = history_meta.get("same_or_lower_pressure_path", True)
    stable_after_exception_runs = history_meta.get("stable_after_exception_runs", 0)
    latest_case_outcome = history_meta.get("latest_case_outcome")

    if not recent_reopened:
        score += 0.15
    else:
        score -= 0.15
        blockers.append((-0.15, "The target reopened inside the retirement window, so caution still needs to stay in place."))

    if recent_policy_flip_count == 0:
        score += 0.15
    else:
        score -= 0.10
        blockers.append((-0.10, "Trust policy is still flipping inside the retirement window, so the softer posture has not settled yet."))

    if same_or_lower_pressure_path:
        score += 0.10
    if stable_after_exception_runs >= 3:
        score += 0.10
        stability_reason = "Recent runs stayed stable after the exception without new pressure spikes."
    elif stable_after_exception_runs >= 2 or same_or_lower_pressure_path:
        stability_reason = "Recent runs are stabilizing, but the retirement window is still short."

    if latest_case_outcome == "overcautious":
        score += 0.10
        exception_reason = "Recent exception history looks overcautious, so relaxing the softer posture is safer."
    elif latest_case_outcome == "useful-caution":
        score -= 0.15
        exception_reason = "Recent exception history still shows useful caution, so the softer posture remains justified."
        blockers.append((-0.15, "Recent exception history still looks useful-caution rather than ready for retirement."))
    elif latest_case_outcome == "insufficient-data":
        exception_reason = "Recent exception history is still too light to prove the softer posture can retire."

    if target.get("trust_recovery_status") == "earned":
        score += 0.05

    score = max(0.05, min(0.95, round(score, 2)))
    reasons = [reason for reason in (calibration_reason, stability_reason, exception_reason) if reason]
    if blockers:
        strongest_blocker = sorted(blockers, key=lambda item: item[0])[0][1]
        if strongest_blocker not in reasons:
            reasons.append(strongest_blocker)
    return score, _confidence_label(score), reasons[:4]


def _exception_retirement_for_target(
    target: dict,
    history_meta: dict,
    confidence_calibration: dict,
    *,
    recovery_confidence_label: str,
    trust_policy: str,
    trust_policy_reason: str,
) -> tuple[str, str, str, str]:
    if not _is_exception_affected_target(target):
        return "none", "", trust_policy, trust_policy_reason

    calibration_status = confidence_calibration.get("confidence_validation_status", "insufficient-data")
    stable_after_exception_runs = history_meta.get("stable_after_exception_runs", 0)
    recent_reopened = history_meta.get("recent_reopened", False)
    recent_policy_flip_count = history_meta.get("recent_policy_flip_count", 0)
    recovery_status = target.get("trust_recovery_status", "none")

    if (
        recovery_status == "blocked"
        or recent_reopened
        or recent_policy_flip_count > 0
        or calibration_status != "healthy"
    ):
        if recovery_status == "blocked":
            reason = target.get(
                "trust_recovery_reason",
                "Exception retirement is blocked because trust recovery has not cleared yet.",
            )
        elif recent_reopened:
            reason = "Exception retirement is blocked because the target reopened inside the retirement window."
        elif recent_policy_flip_count > 0:
            reason = "Exception retirement is blocked because trust policy is still flipping inside the retirement window."
        else:
            reason = "Exception retirement is blocked because calibration is not healthy enough yet."
        return "blocked", reason, trust_policy, trust_policy_reason

    if (
        recovery_status in {"candidate", "earned"}
        and stable_after_exception_runs >= 2
        and recovery_confidence_label in {"medium", "high"}
    ):
        if (
            recovery_status == "earned"
            and recovery_confidence_label == "high"
            and stable_after_exception_runs >= EXCEPTION_RETIREMENT_WINDOW_RUNS
            and not recent_reopened
            and recent_policy_flip_count == 0
            and calibration_status == "healthy"
        ):
            retired_policy, retired_reason = _restore_retired_trust_policy(target)
            return (
                "retired",
                "Recent evidence is stable enough that the earlier soft caution has been formally retired.",
                retired_policy,
                retired_reason,
            )
        return (
            "candidate",
            "This target is trending toward retirement, but it has not earned it yet.",
            trust_policy,
            trust_policy_reason,
        )

    return "none", "", trust_policy, trust_policy_reason


def _is_exception_affected_target(target: dict) -> bool:
    return (
        target.get("trust_exception_status") not in {None, "", "none"}
        or target.get("trust_recovery_status") in {"candidate", "earned", "blocked"}
    )


def _restore_retired_trust_policy(target: dict) -> tuple[str, str]:
    restored_policy = target.get("base_trust_policy", target.get("trust_policy", "monitor"))
    if target.get("lane") == "blocked" and target.get("kind") == "setup" and restored_policy == "act-now":
        restored_policy = "act-with-review"
    if restored_policy == "act-now":
        return restored_policy, "Recent evidence is stable enough to retire the earlier caution and return this target to act-now."
    if restored_policy == "act-with-review":
        return restored_policy, "Recent evidence is stable enough to retire the earlier caution and return this target to act-with-review."
    if restored_policy == "verify-first":
        return restored_policy, "The earlier soft caution can retire, but the strongest supported policy is still verify-first."
    return restored_policy, "The earlier soft caution can retire, but the current signal still only supports monitoring."


def _recovery_confidence_summary(primary_target: dict, sticky_exception_hotspots: list[dict]) -> str:
    label = _target_label(primary_target) or "The current target"
    retirement_status = primary_target.get("exception_retirement_status", "none")
    confidence_label = primary_target.get("recovery_confidence_label", "low")
    confidence_score = primary_target.get("recovery_confidence_score", 0.05)
    if retirement_status == "retired":
        return f"{label} has high recovery confidence ({confidence_score:.2f}), so the earlier caution can now retire."
    if retirement_status == "candidate":
        return f"{label} is building recovery confidence ({confidence_label}, {confidence_score:.2f}), but the earlier caution has not retired yet."
    if retirement_status == "blocked":
        return primary_target.get(
            "exception_retirement_reason",
            f"{label} still has reopen, flip, or calibration noise blocking exception retirement.",
        )
    if confidence_label == "high":
        return f"{label} has high recovery confidence ({confidence_score:.2f}), so caution can start relaxing when the retirement rules are met."
    if confidence_label == "medium":
        return f"{label} has medium recovery confidence ({confidence_score:.2f}), so caution may relax soon but still needs more proof."
    if sticky_exception_hotspots:
        hotspot = sticky_exception_hotspots[0]
        return (
            f"Recent soft exceptions are still sticking around {hotspot.get('label', 'recent hotspots')}, "
            "so caution still needs stronger proof before it can retire."
        )
    return f"{label} still has low recovery confidence ({confidence_score:.2f}), so the softer caution should stay in place."


def _exception_retirement_summary(
    primary_target: dict,
    retired_exception_hotspots: list[dict],
    sticky_exception_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    retirement_status = primary_target.get("exception_retirement_status", "none")
    if retirement_status == "retired":
        return f"{label} has formally retired the earlier soft caution and returned to {primary_target.get('trust_policy', 'monitor')}."
    if retirement_status == "candidate":
        return f"{label} is trending toward exception retirement, but the evidence is not strong enough to retire it yet."
    if retirement_status == "blocked":
        return primary_target.get(
            "exception_retirement_reason",
            f"{label} still has reopen, flip, or calibration noise blocking exception retirement.",
        )
    if retired_exception_hotspots:
        hotspot = retired_exception_hotspots[0]
        return (
            f"Recent soft exceptions have retired most often around {hotspot.get('label', 'recent hotspots')}, "
            "so verify-first should not linger there longer than the evidence supports."
        )
    if sticky_exception_hotspots:
        hotspot = sticky_exception_hotspots[0]
        return (
            f"Recent soft exceptions are still sticky around {hotspot.get('label', 'recent hotspots')}, "
            "so caution still looks justified there."
        )
    return "Recent exception retirement behavior does not yet show a strong retire-or-stay pattern."


def _policy_debt_summary(primary_target: dict, policy_debt_hotspots: list[dict]) -> str:
    label = _target_label(primary_target) or "The current target"
    debt_status = primary_target.get("policy_debt_status", "none")
    if debt_status == "class-debt":
        return f"{label} belongs to a class that keeps carrying sticky caution, so class-level normalization should stay conservative for now."
    if debt_status == "one-off-noise":
        return f"{label} looks noisier than its broader class, so the softer caution remains target-specific instead of class-wide."
    if debt_status == "watch":
        return f"{label} sits in a class with mixed recent caution behavior, so watch for policy debt before normalizing further."
    if policy_debt_hotspots:
        hotspot = policy_debt_hotspots[0]
        return (
            f"Sticky caution is lingering most around {hotspot.get('label', 'recent hotspots')}, "
            "so verify-first should not be normalized there without stronger evidence."
        )
    return "Recent class behavior does not yet show meaningful policy debt."


def _trust_normalization_summary(
    primary_target: dict,
    normalized_class_hotspots: list[dict],
    policy_debt_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    normalization_status = primary_target.get("class_normalization_status", "none")
    if normalization_status == "applied":
        return f"{label} inherits a stronger trust posture because its class has repeatedly earned clean retirement."
    if normalization_status == "candidate":
        return f"{label} belongs to a healthier class trend, but it has not earned class-level normalization yet."
    if normalization_status == "blocked":
        return primary_target.get(
            "class_normalization_reason",
            f"{label} is blocked from class-level normalization by local reopen, flip, or calibration noise.",
        )
    if normalized_class_hotspots:
        hotspot = normalized_class_hotspots[0]
        return (
            f"Recent soft caution has normalized most cleanly around {hotspot.get('label', 'recent hotspots')}, "
            "so verify-first should not linger there longer than the evidence supports."
        )
    if policy_debt_hotspots:
        hotspot = policy_debt_hotspots[0]
        return (
            f"Class-level normalization still looks constrained around {hotspot.get('label', 'recent hotspots')}, "
            "so broader trust relaxation should stay conservative there."
        )
    return "Recent class behavior does not yet show a strong normalization pattern."


def _retirement_hotspots(
    historical_cases: list[dict],
    resolution_targets: list[dict],
    *,
    mode: str,
) -> list[dict]:
    grouped: dict[str, list[str]] = {}
    for case in historical_cases:
        class_key = case.get("class_key", "")
        if not class_key:
            continue
        grouped.setdefault(class_key, []).append(case.get("case_outcome", ""))

    for target in resolution_targets:
        class_key = _target_class_key(target)
        if not class_key:
            continue
        if mode == "retired" and target.get("exception_retirement_status") == "retired":
            grouped.setdefault(class_key, []).append("retired")
        if mode == "sticky" and target.get("exception_retirement_status") == "blocked":
            grouped.setdefault(class_key, []).append("blocked")

    hotspots: list[dict] = []
    target_outcomes = {"overcautious", "retired"} if mode == "retired" else {"useful-caution", "blocked"}
    count_key = "retired_count" if mode == "retired" else "sticky_count"
    for label, outcomes in grouped.items():
        match_count = sum(1 for outcome in outcomes if outcome in target_outcomes)
        if match_count <= 0:
            continue
        hotspots.append(
            {
                "scope": "class",
                "label": label,
                count_key: match_count,
                "exception_count": len(outcomes),
            }
        )
    hotspots.sort(
        key=lambda item: (
            -item.get(count_key, 0),
            -item.get("exception_count", 0),
            item.get("label", ""),
        )
    )
    return hotspots[:5]


def _class_normalization_events(
    history: list[dict],
    *,
    current_primary_target: dict,
    current_generated_at: str,
) -> list[dict]:
    events: list[dict] = []
    if current_primary_target and current_primary_target.get("trust_policy"):
        events.append(
            {
                "key": _queue_identity(current_primary_target),
                "class_key": _target_class_key(current_primary_target),
                "label": _target_label(current_primary_target),
                "trust_policy": current_primary_target.get("trust_policy", "monitor"),
                "generated_at": current_generated_at or "",
                "lane": current_primary_target.get("lane", ""),
                "kind": current_primary_target.get("kind", ""),
                "decision_memory_status": current_primary_target.get("decision_memory_status", ""),
                "last_outcome": current_primary_target.get("last_outcome", ""),
                "trust_exception_status": current_primary_target.get("trust_exception_status", "none"),
                "trust_recovery_status": current_primary_target.get("trust_recovery_status", "none"),
                "exception_retirement_status": current_primary_target.get("exception_retirement_status", "none"),
                "confidence_validation_status": current_primary_target.get("confidence_validation_status", ""),
                "exception_pattern_status": current_primary_target.get("exception_pattern_status", "none"),
                "policy_debt_status": current_primary_target.get("policy_debt_status", "none"),
                "class_normalization_status": current_primary_target.get("class_normalization_status", "none"),
                "recency_index": 0,
            }
        )
    for index, entry in enumerate(history[: HISTORY_WINDOW_RUNS - 1], start=1):
        summary = entry.get("operator_summary") or {}
        primary_target = summary.get("primary_target") or {}
        trust_policy = summary.get("primary_target_trust_policy", "")
        if not primary_target or not trust_policy:
            continue
        events.append(
            {
                "key": _queue_identity(primary_target),
                "class_key": _target_class_key(primary_target),
                "label": _target_label(primary_target),
                "trust_policy": trust_policy,
                "generated_at": entry.get("generated_at", ""),
                "lane": primary_target.get("lane", ""),
                "kind": primary_target.get("kind", ""),
                "decision_memory_status": summary.get("decision_memory_status", ""),
                "last_outcome": summary.get("primary_target_last_outcome", ""),
                "trust_exception_status": summary.get("primary_target_exception_status", "none"),
                "trust_recovery_status": summary.get("primary_target_trust_recovery_status", "none"),
                "exception_retirement_status": summary.get("primary_target_exception_retirement_status", "none"),
                "confidence_validation_status": summary.get("confidence_validation_status", ""),
                "exception_pattern_status": summary.get("primary_target_exception_pattern_status", "none"),
                "policy_debt_status": summary.get("primary_target_policy_debt_status", "none"),
                "class_normalization_status": summary.get("primary_target_class_normalization_status", "none"),
                "recency_index": index,
            }
        )
    return sorted(events, key=lambda item: item.get("generated_at", ""), reverse=True)


def _target_class_normalization_history(
    target: dict,
    class_events: list[dict],
    historical_cases: list[dict],
) -> dict:
    key = _queue_identity(target)
    class_key = _target_class_key(target)
    target_events = [event for event in class_events if event.get("key") == key]
    matching_class_events = [event for event in class_events if event.get("class_key") == class_key]
    target_policies = [event.get("trust_policy", "monitor") for event in target_events[:CLASS_NORMALIZATION_WINDOW_RUNS]]
    class_policies = [event.get("trust_policy", "monitor") for event in matching_class_events[:CLASS_NORMALIZATION_WINDOW_RUNS]]
    target_lanes = [event.get("lane", "") for event in target_events[:CLASS_NORMALIZATION_WINDOW_RUNS]]
    class_exception_events = [
        event
        for event in matching_class_events
        if event.get("trust_exception_status") not in {None, "", "none"}
        or event.get("exception_retirement_status") not in {None, "", "none"}
    ]
    target_cases = [case for case in historical_cases if case.get("key") == key]
    class_cases = [case for case in historical_cases if case.get("class_key") == class_key]
    exception_count = len(class_exception_events)
    retired_count = sum(1 for event in class_exception_events if event.get("exception_retirement_status") == "retired")
    sticky_count = sum(1 for event in class_exception_events if event.get("exception_retirement_status") == "blocked")
    overcautious_count = sum(1 for case in class_cases if case.get("case_outcome") == "overcautious")
    useful_caution_count = sum(1 for case in class_cases if case.get("case_outcome") == "useful-caution")
    verify_first_count = sum(1 for event in matching_class_events if event.get("trust_policy") == "verify-first")
    if target.get("trust_exception_status") not in {None, "", "none"} or target.get("exception_retirement_status") not in {None, "", "none"}:
        exception_count += 1
    if target.get("exception_retirement_status") == "retired":
        retired_count += 1
    if target.get("exception_retirement_status") == "blocked":
        sticky_count += 1
    if target.get("exception_pattern_status") == "overcautious":
        overcautious_count += 1
    if target.get("exception_pattern_status") == "useful-caution":
        useful_caution_count += 1
    if target.get("trust_policy") == "verify-first":
        verify_first_count += 1
    class_retirement_rate = retired_count / max(exception_count, 1)
    class_sticky_rate = sticky_count / max(exception_count, 1)
    weighted_exception_count = 0.0
    weighted_retired_like = 0.0
    weighted_sticky_like = 0.0
    recent_exception_weight = 0.0
    for event in matching_class_events[:HISTORY_WINDOW_RUNS]:
        recency_index = min(event.get("recency_index", HISTORY_WINDOW_RUNS - 1), HISTORY_WINDOW_RUNS - 1)
        if recency_index == 0:
            continue
        weight = CLASS_MEMORY_RECENCY_WEIGHTS[recency_index]
        if not _is_class_memory_event(event):
            continue
        weighted_exception_count += weight
        if recency_index <= CLASS_MEMORY_FRESHNESS_WINDOW_RUNS:
            recent_exception_weight += weight
        if _is_retired_like_class_event(event):
            weighted_retired_like += weight
        if _is_sticky_like_class_event(event):
            weighted_sticky_like += weight
    recent_window_weight_share = recent_exception_weight / max(weighted_exception_count, 1.0)
    decayed_class_retirement_rate = weighted_retired_like / max(weighted_exception_count, 1.0)
    decayed_class_sticky_rate = weighted_sticky_like / max(weighted_exception_count, 1.0)
    freshness_status = _class_memory_freshness_status(weighted_exception_count, recent_window_weight_share)
    return {
        "exception_count": exception_count,
        "retired_count": retired_count,
        "sticky_count": sticky_count,
        "overcautious_count": overcautious_count,
        "useful_caution_count": useful_caution_count,
        "verify_first_count": verify_first_count,
        "class_retirement_rate": class_retirement_rate,
        "class_sticky_rate": class_sticky_rate,
        "weighted_exception_count": round(weighted_exception_count, 2),
        "weighted_retired_like": round(weighted_retired_like, 2),
        "weighted_sticky_like": round(weighted_sticky_like, 2),
        "recent_window_weight_share": round(recent_window_weight_share, 2),
        "class_memory_freshness_status": freshness_status,
        "class_memory_freshness_reason": _class_memory_freshness_reason(
            freshness_status,
            weighted_exception_count,
            recent_window_weight_share,
            decayed_class_retirement_rate,
            decayed_class_sticky_rate,
        ),
        "class_memory_weight": round(recent_window_weight_share, 2),
        "decayed_class_retirement_rate": round(decayed_class_retirement_rate, 2),
        "decayed_class_sticky_rate": round(decayed_class_sticky_rate, 2),
        "recent_class_signal_mix": _recent_class_signal_mix(
            weighted_exception_count,
            weighted_retired_like,
            weighted_sticky_like,
            recent_window_weight_share,
        ),
        "stable_after_exception_runs": target.get("stable_after_exception_runs", _stable_policy_run_count(target_policies)),
        "recent_class_policy_path": " -> ".join(class_policies[:CLASS_NORMALIZATION_WINDOW_RUNS]),
        "recent_policy_flip_count": _policy_flip_count(target_policies),
        "recent_class_policy_flip_count": _policy_flip_count(class_policies),
        "same_or_lower_pressure_path": _same_or_lower_pressure_path(target_lanes),
        "recent_reopened": any(
            event.get("decision_memory_status") == "reopened" or event.get("last_outcome") == "reopened"
            for event in target_events[:CLASS_NORMALIZATION_WINDOW_RUNS]
        ),
        "latest_case_outcome": _latest_case_outcome(target_cases, class_cases),
    }


def _is_class_memory_event(item: dict) -> bool:
    return (
        item.get("trust_exception_status") not in {None, "", "none"}
        or item.get("exception_retirement_status") not in {None, "", "none"}
        or item.get("class_normalization_status") not in {None, "", "none"}
        or item.get("policy_debt_status") not in {None, "", "none"}
    )


def _is_class_memory_target(target: dict) -> bool:
    return (
        target.get("trust_exception_status") not in {None, "", "none"}
        or target.get("exception_retirement_status") not in {None, "", "none"}
        or target.get("class_normalization_status") not in {None, "", "none"}
        or target.get("policy_debt_status") not in {None, "", "none"}
    )


def _is_retired_like_class_event(item: dict) -> bool:
    return (
        item.get("exception_retirement_status") == "retired"
        or item.get("exception_pattern_status") == "overcautious"
        or item.get("class_normalization_status") == "applied"
    )


def _is_sticky_like_class_event(item: dict) -> bool:
    return (
        item.get("exception_retirement_status") == "blocked"
        or item.get("exception_pattern_status") == "useful-caution"
        or item.get("policy_debt_status") == "class-debt"
    )


def _class_memory_freshness_status(weighted_exception_count: float, recent_window_weight_share: float) -> str:
    if weighted_exception_count < 2.0:
        return "insufficient-data"
    if recent_window_weight_share >= 0.60:
        return "fresh"
    if recent_window_weight_share >= 0.35:
        return "mixed-age"
    return "stale"


def _class_memory_freshness_reason(
    freshness_status: str,
    weighted_exception_count: float,
    recent_window_weight_share: float,
    decayed_class_retirement_rate: float,
    decayed_class_sticky_rate: float,
) -> str:
    if freshness_status == "fresh":
        return (
            "Recent class evidence is still current enough to trust, with "
            f"{recent_window_weight_share:.0%} of the weighted signal coming from the latest {CLASS_MEMORY_FRESHNESS_WINDOW_RUNS} runs."
        )
    if freshness_status == "mixed-age":
        return (
            "Class memory is still useful, but it is partly aging: "
            f"{recent_window_weight_share:.0%} of the weighted signal is recent and the rest is older carry-forward."
        )
    if freshness_status == "stale":
        return (
            "Older class evidence is now carrying more of the signal than recent runs, so class-level trust should not lean on it too heavily."
        )
    return (
        "Class memory is still too lightly exercised to judge freshness, with "
        f"{weighted_exception_count:.2f} weighted exception run(s), "
        f"{decayed_class_retirement_rate:.0%} retired-like signal, and {decayed_class_sticky_rate:.0%} sticky signal."
    )


def _recent_class_signal_mix(
    weighted_exception_count: float,
    weighted_retired_like: float,
    weighted_sticky_like: float,
    recent_window_weight_share: float,
) -> str:
    return (
        f"{weighted_exception_count:.2f} weighted exception run(s) with "
        f"{weighted_retired_like:.2f} retired-like, {weighted_sticky_like:.2f} sticky-like, "
        f"and {recent_window_weight_share:.0%} of the signal from the freshest runs."
    )


def _class_normalization_friendly(history_meta: dict) -> bool:
    return history_meta.get("exception_count", 0) >= 3 and (
        history_meta.get("retired_count", 0) >= history_meta.get("sticky_count", 0) + 2
        or history_meta.get("class_retirement_rate", 0.0) >= 0.60
    )


def _class_normalization_candidate(history_meta: dict) -> bool:
    return history_meta.get("exception_count", 0) >= 2 and history_meta.get("class_retirement_rate", 0.0) >= 0.50


def _target_specific_normalization_noise(target: dict, history_meta: dict) -> bool:
    return (
        history_meta.get("recent_reopened", False)
        or history_meta.get("recent_policy_flip_count", 0) > 0
        or target.get("trust_recovery_status") == "blocked"
    )


def _policy_debt_for_target(target: dict, history_meta: dict) -> tuple[str, str]:
    exception_count = history_meta.get("exception_count", 0)
    retired_count = history_meta.get("retired_count", 0)
    sticky_count = history_meta.get("sticky_count", 0)
    class_sticky_rate = history_meta.get("class_sticky_rate", 0.0)
    if _class_normalization_friendly(history_meta) and _target_specific_normalization_noise(target, history_meta):
        return (
            "one-off-noise",
            "This class has been earning clean retirement more often, but this target still has local reopen, flip, or blocked-recovery noise keeping the softer posture target-specific.",
        )
    if exception_count >= 3 and (
        sticky_count >= retired_count + 2 or class_sticky_rate >= 0.60
    ):
        return (
            "class-debt",
            "This class keeps carrying sticky caution across recent runs, so class-level normalization would be premature.",
        )
    if exception_count >= 2:
        return (
            "watch",
            "This class has enough recent exception activity to watch for lingering caution, but it is not yet clearly sticky or clearly normalization-friendly.",
        )
    return "none", ""


def _class_normalization_for_target(
    target: dict,
    history_meta: dict,
    confidence_calibration: dict,
    *,
    policy_debt_status: str,
    trust_policy: str,
    trust_policy_reason: str,
) -> tuple[str, str, str, str]:
    exception_affected = (
        target.get("trust_exception_status") not in {None, "", "none"}
        or target.get("exception_retirement_status") not in {None, "", "none"}
        or target.get("trust_recovery_status") in {"candidate", "earned", "blocked"}
    )
    if not exception_affected or trust_policy != "verify-first":
        return "none", "", trust_policy, trust_policy_reason

    local_noise = _target_specific_normalization_noise(target, history_meta)
    if (
        local_noise
        or confidence_calibration.get("confidence_validation_status") != "healthy"
        or policy_debt_status == "class-debt"
    ):
        return (
            "blocked",
            "Class-level normalization is blocked by local reopen, flip, blocked-recovery, or calibration noise.",
            trust_policy,
            trust_policy_reason,
        )

    if (
        _class_normalization_friendly(history_meta)
        and (
            target.get("trust_recovery_status") in {"candidate", "earned"}
            or target.get("exception_retirement_status") == "candidate"
        )
    ):
        normalized_policy = "act-with-review"
        normalized_reason = (
            "This class has repeatedly earned clean retirement, so the current target can inherit a stronger act-with-review posture."
        )
        if target.get("lane") == "blocked" and target.get("kind") == "setup":
            normalized_reason = (
                "This blocked setup class has repeatedly earned clean retirement, but setup blockers still should not skip review."
            )
        return "applied", normalized_reason, normalized_policy, normalized_reason

    if _class_normalization_candidate(history_meta):
        return (
            "candidate",
            "This class is trending healthier, but the current target has not earned class-level normalization yet.",
            trust_policy,
            trust_policy_reason,
        )
    return "none", "", trust_policy, trust_policy_reason


def _class_normalization_hotspots(
    historical_cases: list[dict],
    resolution_targets: list[dict],
    *,
    mode: str,
) -> list[dict]:
    grouped: dict[str, dict[str, int]] = {}
    for case in historical_cases:
        class_key = case.get("class_key", "")
        if not class_key:
            continue
        group = grouped.setdefault(
            class_key,
            {
                "exception_count": 0,
                "match_count": 0,
                "retired_count": 0,
                "sticky_count": 0,
                "overcautious_count": 0,
                "useful_caution_count": 0,
            },
        )
        group["exception_count"] += 1
        if case.get("case_outcome") == "overcautious":
            group["overcautious_count"] += 1
        if case.get("case_outcome") == "useful-caution":
            group["useful_caution_count"] += 1

    for target in resolution_targets:
        class_key = _target_class_key(target)
        if not class_key:
            continue
        group = grouped.setdefault(
            class_key,
            {
                "exception_count": 0,
                "match_count": 0,
                "retired_count": 0,
                "sticky_count": 0,
                "overcautious_count": 0,
                "useful_caution_count": 0,
            },
        )
        if target.get("trust_exception_status") not in {None, "", "none"} or target.get("exception_retirement_status") not in {None, "", "none"}:
            group["exception_count"] += 1
        if target.get("exception_retirement_status") == "retired":
            group["retired_count"] += 1
        if target.get("exception_retirement_status") == "blocked":
            group["sticky_count"] += 1
        if target.get("exception_pattern_status") == "overcautious":
            group["overcautious_count"] += 1
        if target.get("exception_pattern_status") == "useful-caution":
            group["useful_caution_count"] += 1
        if mode == "policy-debt" and target.get("policy_debt_status") == "class-debt":
            group["sticky_count"] += 1
        if mode == "normalized" and target.get("class_normalization_status") == "applied":
            group["retired_count"] += 1

    hotspots: list[dict] = []
    for class_key, group in grouped.items():
        if mode == "policy-debt":
            match_count = group["sticky_count"] + group["useful_caution_count"]
        else:
            match_count = group["retired_count"] + group["overcautious_count"]
        if match_count <= 0:
            continue
        hotspots.append(
            {
                "scope": "class",
                "label": class_key,
                "match_count": match_count,
                "exception_count": group["exception_count"],
                "retired_count": group["retired_count"],
                "sticky_count": group["sticky_count"],
                "overcautious_count": group["overcautious_count"],
                "useful_caution_count": group["useful_caution_count"],
            }
        )
    hotspots.sort(
        key=lambda item: (
            -item.get("match_count", 0),
            -item.get("exception_count", 0),
            item.get("label", ""),
        )
    )
    return hotspots[:5]


def _class_memory_decay_for_target(
    target: dict,
    history_meta: dict,
    confidence_calibration: dict,
    *,
    trust_policy: str,
    trust_policy_reason: str,
    policy_debt_status: str,
    policy_debt_reason: str,
    class_normalization_status: str,
    class_normalization_reason: str,
) -> tuple[str, str, str, str, str, str, str, str]:
    freshness_status = history_meta.get("class_memory_freshness_status", "insufficient-data")
    decayed_class_retirement_rate = history_meta.get("decayed_class_retirement_rate", 0.0)
    decayed_class_sticky_rate = history_meta.get("decayed_class_sticky_rate", 0.0)
    local_noise = _target_specific_normalization_noise(target, history_meta)
    calibration_status = confidence_calibration.get("confidence_validation_status", "insufficient-data")

    if local_noise:
        return (
            "blocked",
            "Local reopen, flip, or blocked-recovery noise still overrides healthier class memory for this target.",
            trust_policy,
            trust_policy_reason,
            policy_debt_status,
            policy_debt_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    if (
        class_normalization_status == "applied"
        and freshness_status in {"stale", "insufficient-data"}
    ):
        reverted_policy = target.get("pre_class_normalization_trust_policy", trust_policy)
        reverted_reason = target.get(
            "pre_class_normalization_trust_policy_reason",
            trust_policy_reason,
        )
        if target.get("lane") == "blocked" and target.get("kind") == "setup" and reverted_policy == "act-now":
            reverted_policy = "act-with-review"
            reverted_reason = (
                "Class normalization was pulled back because the class lesson is aging out, and blocked setup items still should not skip review."
            )
        return (
            "normalization-decayed",
            "Class normalization was pulled back because the class lesson is too old or too lightly refreshed to keep carrying forward on its own.",
            reverted_policy,
            reverted_reason,
            policy_debt_status,
            policy_debt_reason,
            "candidate",
            "Class-level normalization is aging out, so the class trend remains promising but no longer strong enough to keep the stronger posture on its own.",
        )

    if (
        policy_debt_status == "class-debt"
        and decayed_class_sticky_rate < 0.50
        and decayed_class_retirement_rate >= 0.50
        and calibration_status == "healthy"
    ):
        return (
            "policy-debt-decayed",
            "Earlier sticky caution no longer has enough fresh class support to stay strong.",
            trust_policy,
            trust_policy_reason,
            "watch",
            "Fresh class evidence now looks mixed enough that sticky class-level caution should soften to watch.",
            class_normalization_status,
            class_normalization_reason,
        )

    if (
        freshness_status == "fresh"
        and (
            class_normalization_status == "applied"
            or policy_debt_status == "class-debt"
        )
    ):
        return (
            "none",
            "",
            trust_policy,
            trust_policy_reason,
            policy_debt_status,
            policy_debt_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    if calibration_status != "healthy" and policy_debt_status == "class-debt":
        return (
            "blocked",
            "Class freshness is present, but calibration is not healthy enough to relax class-level caution any further.",
            trust_policy,
            trust_policy_reason,
            policy_debt_status,
            policy_debt_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    return (
        "none",
        "",
        trust_policy,
        trust_policy_reason,
        policy_debt_status,
        policy_debt_reason,
        class_normalization_status,
        class_normalization_reason,
    )


def _class_memory_hotspots(resolution_targets: list[dict], *, mode: str) -> list[dict]:
    grouped: dict[str, dict] = {}
    for target in resolution_targets:
        class_key = _target_class_key(target)
        if not class_key:
            continue
        grouped[class_key] = {
            "scope": "class",
            "label": class_key,
            "freshness_status": target.get("class_memory_freshness_status", "insufficient-data"),
            "class_memory_weight": target.get("class_memory_weight", 0.0),
            "weighted_exception_count": target.get("class_memory_weight", 0.0),
            "decayed_class_retirement_rate": target.get("decayed_class_retirement_rate", 0.0),
            "decayed_class_sticky_rate": target.get("decayed_class_sticky_rate", 0.0),
            "recent_class_signal_mix": target.get("recent_class_signal_mix", ""),
        }
    hotspots = list(grouped.values())
    if mode == "stale":
        hotspots = [
            item
            for item in hotspots
            if item.get("freshness_status") in {"stale", "insufficient-data"}
        ]
        hotspots.sort(
            key=lambda item: (
                item.get("class_memory_weight", 0.0),
                -item.get("decayed_class_sticky_rate", 0.0),
                item.get("label", ""),
            )
        )
    else:
        hotspots = [item for item in hotspots if item.get("freshness_status") == "fresh"]
        hotspots.sort(
            key=lambda item: (
                -item.get("class_memory_weight", 0.0),
                -item.get("decayed_class_retirement_rate", 0.0),
                item.get("label", ""),
            )
        )
    return hotspots[:5]


def _class_memory_summary(
    primary_target: dict,
    fresh_class_signal_hotspots: list[dict],
    stale_class_memory_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    freshness_status = primary_target.get("class_memory_freshness_status", "insufficient-data")
    if freshness_status == "fresh":
        return f"{label} sits in class evidence that is still fresh enough to trust, so recent class behavior should carry more weight than older lessons."
    if freshness_status == "mixed-age":
        return f"{label} still has useful class memory, but part of that signal is aging and should be treated more cautiously."
    if freshness_status == "stale":
        return f"{label} is leaning on older class evidence that is now being down-weighted so it does not dominate the current trust posture."
    if fresh_class_signal_hotspots:
        hotspot = fresh_class_signal_hotspots[0]
        return (
            f"Fresh class evidence is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so recent lessons there are still current enough to matter."
        )
    if stale_class_memory_hotspots:
        hotspot = stale_class_memory_hotspots[0]
        return (
            f"Class memory is aging out most visibly around {hotspot.get('label', 'recent hotspots')}, "
            "so older class lessons should not keep carrying forward there."
        )
    return "Class memory is still too lightly exercised to say whether recent class lessons are fresh or aging out."


def _class_decay_summary(
    primary_target: dict,
    stale_class_memory_hotspots: list[dict],
    fresh_class_signal_hotspots: list[dict],
) -> str:
    label = _target_label(primary_target) or "The current target"
    decay_status = primary_target.get("class_decay_status", "none")
    if decay_status == "normalization-decayed":
        return f"{label} had class-level normalization pulled back because the class lesson is too old or too lightly refreshed to keep the stronger posture."
    if decay_status == "policy-debt-decayed":
        return f"{label} no longer has enough fresh sticky class evidence to keep strong class-debt caution in place."
    if decay_status == "blocked":
        return primary_target.get(
            "class_decay_reason",
            f"{label} still has local target noise blocking healthier class memory from changing the live posture.",
        )
    if stale_class_memory_hotspots:
        hotspot = stale_class_memory_hotspots[0]
        return (
            f"Older class lessons are aging out around {hotspot.get('label', 'recent hotspots')}, "
            "so trust posture there should rely less on stale carry-forward."
        )
    if fresh_class_signal_hotspots:
        hotspot = fresh_class_signal_hotspots[0]
        return (
            f"Fresh class signals are still strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so current class posture there still has enough recent support."
        )
    return "Recent class evidence does not yet show a strong decay-or-stay pattern."


def _trust_exception_events(
    history: list[dict],
    *,
    current_primary_target: dict,
    current_generated_at: str,
) -> list[dict]:
    events: list[dict] = []
    if current_primary_target and current_primary_target.get("trust_policy"):
        events.append(
            {
                "key": _queue_identity(current_primary_target),
                "class_key": _target_class_key(current_primary_target),
                "label": _target_label(current_primary_target),
                "trust_policy": current_primary_target.get("trust_policy", "monitor"),
                "trust_exception_status": current_primary_target.get("trust_exception_status", "none"),
                "generated_at": current_generated_at or "",
                "lane": current_primary_target.get("lane", ""),
                "kind": current_primary_target.get("kind", ""),
                "decision_memory_status": current_primary_target.get("decision_memory_status", ""),
                "last_outcome": current_primary_target.get("last_outcome", ""),
                "confidence_validation_status": current_primary_target.get("confidence_validation_status", ""),
            }
        )
    for entry in history[: HISTORY_WINDOW_RUNS - 1]:
        summary = entry.get("operator_summary") or {}
        primary_target = summary.get("primary_target") or {}
        trust_policy = summary.get("primary_target_trust_policy", "")
        if not primary_target or not trust_policy:
            continue
        events.append(
            {
                "key": _queue_identity(primary_target),
                "class_key": _target_class_key(primary_target),
                "label": _target_label(primary_target),
                "trust_policy": trust_policy,
                "trust_exception_status": summary.get("primary_target_exception_status", "none"),
                "generated_at": entry.get("generated_at", ""),
                "lane": primary_target.get("lane", ""),
                "kind": primary_target.get("kind", ""),
                "decision_memory_status": summary.get("decision_memory_status", ""),
                "last_outcome": summary.get("primary_target_last_outcome", ""),
                "confidence_validation_status": summary.get("confidence_validation_status", ""),
            }
        )
    return sorted(events, key=lambda item: item.get("generated_at", ""), reverse=True)


def _historical_exception_cases(history: list[dict]) -> list[dict]:
    ordered_runs = sorted(
        [
            {
                "generated_at": entry.get("generated_at", ""),
                "operator_summary": entry.get("operator_summary") or {},
                "operator_queue": entry.get("operator_queue") or [],
            }
            for entry in history[: HISTORY_WINDOW_RUNS - 1]
        ],
        key=lambda item: item.get("generated_at", ""),
    )
    cases: list[dict] = []
    for index, run in enumerate(ordered_runs):
        summary = run.get("operator_summary") or {}
        target = summary.get("primary_target") or {}
        exception_status = summary.get("primary_target_exception_status", "none")
        if not target or exception_status in {None, "", "none"}:
            continue
        future_runs = ordered_runs[index + 1 : index + 1 + TRUST_RECOVERY_WINDOW_RUNS]
        cases.append(
            {
                "key": _queue_identity(target),
                "class_key": _target_class_key(target),
                "label": _target_label(target),
                "generated_at": run.get("generated_at", ""),
                "lane": target.get("lane", ""),
                "kind": target.get("kind", ""),
                "trust_exception_status": exception_status,
                "case_outcome": _exception_case_outcome(run, future_runs),
            }
        )
    return sorted(cases, key=lambda item: item.get("generated_at", ""), reverse=True)


def _exception_case_outcome(run: dict, future_runs: list[dict]) -> str:
    if len(future_runs) < TRUST_RECOVERY_WINDOW_RUNS:
        return "insufficient-data"
    summary = run.get("operator_summary") or {}
    target = summary.get("primary_target") or {}
    target_key = _queue_identity(target)
    future_matches = [_run_target_match(candidate, target_key) for candidate in future_runs]
    future_lanes = [match.get("lane") if match else None for match in future_matches]
    reopened = any(
        (
            (candidate.get("operator_summary") or {}).get("decision_memory_status") == "reopened"
            or (candidate.get("operator_summary") or {}).get("primary_target_last_outcome") == "reopened"
        )
        and _queue_identity((candidate.get("operator_summary") or {}).get("primary_target") or {}) == target_key
        for candidate in future_runs
    )
    if reopened or any(lane in ATTENTION_LANES for lane in future_lanes):
        return "useful-caution"
    return "overcautious"


def _target_exception_history(
    target: dict,
    exception_events: list[dict],
    historical_cases: list[dict],
) -> dict:
    key = _queue_identity(target)
    class_key = _target_class_key(target)
    target_events = [event for event in exception_events if event.get("key") == key]
    class_events = [event for event in exception_events if event.get("class_key") == class_key]
    target_exception_events = [event for event in target_events if event.get("trust_exception_status") not in {None, "", "none"}]
    class_exception_events = [event for event in class_events if event.get("trust_exception_status") not in {None, "", "none"}]
    target_cases = [case for case in historical_cases if case.get("key") == key]
    class_cases = [case for case in historical_cases if case.get("class_key") == class_key]
    target_policies = [event.get("trust_policy", "monitor") for event in target_events[:TRUST_RECOVERY_WINDOW_RUNS]]
    target_lanes = [event.get("lane", "") for event in target_events[:TRUST_RECOVERY_WINDOW_RUNS]]
    recent_exception_path = " -> ".join(
        event.get("trust_exception_status", "none") for event in target_exception_events[:4]
    ) or " -> ".join(event.get("trust_exception_status", "none") for event in class_exception_events[:4])
    return {
        "stable_policy_run_count": _stable_policy_run_count(target_policies),
        "recent_exception_path": recent_exception_path,
        "recent_policy_flip_count": _policy_flip_count(target_policies),
        "same_or_lower_pressure_path": _same_or_lower_pressure_path(target_lanes),
        "recent_reopened": any(
            event.get("decision_memory_status") == "reopened" or event.get("last_outcome") == "reopened"
            for event in target_events[:TRUST_RECOVERY_WINDOW_RUNS]
        ),
        "latest_case_outcome": _latest_case_outcome(target_cases, class_cases),
        "total_exception_count": len(target_cases) or len(class_cases),
        "overcautious_count": sum(1 for case in target_cases if case.get("case_outcome") == "overcautious"),
        "target_cases": target_cases,
        "class_cases": class_cases,
    }


def _stable_policy_run_count(policies: list[str]) -> int:
    if not policies:
        return 0
    first = policies[0]
    count = 0
    for policy in policies:
        if policy != first:
            break
        count += 1
    return count


def _same_or_lower_pressure_path(lanes: list[str]) -> bool:
    if len(lanes) < 2:
        return True
    chronological = [_lane_pressure(lane or None) for lane in reversed(lanes)]
    return all(current <= previous for previous, current in zip(chronological, chronological[1:]))


def _latest_case_outcome(target_cases: list[dict], class_cases: list[dict]) -> str | None:
    if target_cases:
        return target_cases[0].get("case_outcome")
    if class_cases:
        return class_cases[0].get("case_outcome")
    return None


def _exception_pattern_for_target(target: dict, history_meta: dict) -> tuple[str, str]:
    latest_case_outcome = history_meta.get("latest_case_outcome")
    if latest_case_outcome == "useful-caution":
        return (
            "useful-caution",
            "Recent soft caution was followed by renewed instability or unresolved pressure, so the softer posture still looks justified.",
        )
    if latest_case_outcome == "overcautious":
        return (
            "overcautious",
            "Recent soft caution was followed by stable recovery without renewed pressure, so the softer posture may now be more cautious than the evidence supports.",
        )
    if target.get("trust_exception_status") not in {None, "", "none"}:
        return (
            "insufficient-data",
            "There is not enough target-specific exception history yet to say whether recent soft caution is helping.",
        )
    return "none", ""


def _trust_recovery_for_target(
    target: dict,
    history_meta: dict,
    confidence_calibration: dict,
    *,
    trust_policy: str,
    trust_policy_reason: str,
) -> tuple[str, str, str, str]:
    if target.get("trust_exception_status") in {None, "", "none"} or trust_policy != "verify-first":
        return "none", "", trust_policy, trust_policy_reason

    if confidence_calibration.get("confidence_validation_status") != "healthy":
        return (
            "blocked",
            "Trust recovery is blocked because confidence calibration has not stayed healthy enough yet.",
            trust_policy,
            trust_policy_reason,
        )
    if history_meta.get("recent_reopened"):
        return (
            "blocked",
            "Trust recovery is blocked because this target reopened again inside the recent recovery window.",
            trust_policy,
            trust_policy_reason,
        )
    if history_meta.get("recent_policy_flip_count", 0) > 0:
        return (
            "blocked",
            "Trust recovery is blocked because the target is still flipping trust policy inside the recent recovery window.",
            trust_policy,
            trust_policy_reason,
        )
    if not history_meta.get("same_or_lower_pressure_path", True):
        return (
            "blocked",
            "Trust recovery is blocked because the target has not stayed on the same or lower-pressure path yet.",
            trust_policy,
            trust_policy_reason,
        )
    if history_meta.get("stable_policy_run_count", 0) >= TRUST_RECOVERY_WINDOW_RUNS:
        recovered_policy = "act-with-review"
        recovered_reason = "Recent stability has earned this target back from verify-first to act-with-review."
        if target.get("lane") == "blocked" and target.get("kind") == "setup":
            recovered_reason = "Recent stability has earned this blocked setup target back to act-with-review, but setup blockers still should not skip review."
        return "earned", recovered_reason, recovered_policy, recovered_reason
    return (
        "candidate",
        "This target is stabilizing under healthy calibration, but it has not held steady long enough to earn stronger trust yet.",
        trust_policy,
        trust_policy_reason,
    )


def _recovery_pattern_reason(recovery_status: str, recovery_reason: str) -> str:
    if recovery_status == "earned":
        return recovery_reason or "Recent stability has earned stronger trust again."
    if recovery_status == "candidate":
        return recovery_reason or "This target is stabilizing, but it has not yet earned stronger trust."
    return recovery_reason or "Trust recovery is still being evaluated."


def _exception_pattern_summary(primary_target: dict, false_positive_hotspots: list[dict]) -> str:
    pattern_status = primary_target.get("exception_pattern_status", "none")
    recovery_status = primary_target.get("trust_recovery_status", "none")
    label = _target_label(primary_target) or "The current target"
    if recovery_status == "earned":
        return f"{label} has stayed stable long enough to earn trust back from verify-first to act-with-review."
    if recovery_status == "candidate":
        return f"{label} is stabilizing, but it has not yet earned stronger trust."
    if recovery_status == "blocked":
        return primary_target.get(
            "trust_recovery_reason",
            f"{label} still has fresh reopen, flip, or calibration noise blocking trust recovery.",
        )
    if pattern_status == "useful-caution":
        return f"Recent soft caution for {label} has been justified and still looks appropriate."
    if pattern_status == "overcautious":
        return f"Recent soft caution for {label} may now be more cautious than the evidence supports."
    if false_positive_hotspots:
        hotspot = false_positive_hotspots[0]
        return (
            f"Recent soft exceptions have been most overcautious around {hotspot.get('label', 'recent hotspots')}, "
            f"so verify-first guidance should not linger there longer than the evidence supports."
        )
    if pattern_status == "insufficient-data":
        return "Exception learning is still too lightly exercised to say whether recent soft caution is helping."
    return "Recent exception behavior does not yet show a strong overcautious or recovery pattern."


def _false_positive_exception_hotspots(historical_cases: list[dict]) -> list[dict]:
    target_groups = _group_exception_hotspots(historical_cases, key_name="key", label_name="label", scope="target")
    class_groups = _group_exception_hotspots(historical_cases, key_name="class_key", label_name="class_key", scope="class")
    hotspots = target_groups + class_groups
    hotspots.sort(
        key=lambda item: (
            -item.get("overcautious_count", 0),
            -item.get("exception_count", 0),
            item.get("label", ""),
        )
    )
    return [item for item in hotspots if item.get("overcautious_count", 0) > 0][:5]


def _group_exception_hotspots(
    historical_cases: list[dict],
    *,
    key_name: str,
    label_name: str,
    scope: str,
) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for case in historical_cases:
        key = case.get(key_name, "")
        if not key:
            continue
        grouped.setdefault(key, []).append(case)

    hotspots: list[dict] = []
    for cases in grouped.values():
        overcautious_count = sum(1 for case in cases if case.get("case_outcome") == "overcautious")
        if overcautious_count <= 0:
            continue
        hotspots.append(
            {
                "scope": scope,
                "label": cases[0].get(label_name, ""),
                "overcautious_count": overcautious_count,
                "exception_count": len(cases),
                "recent_exception_path": " -> ".join(case.get("trust_exception_status", "none") for case in cases[:4]),
            }
        )
    return hotspots


def _trust_policy_events(
    history: list[dict],
    *,
    current_primary_target: dict,
    current_generated_at: str,
) -> list[dict]:
    events: list[dict] = []
    if current_primary_target and current_primary_target.get("trust_policy"):
        events.append(
            {
                "key": _queue_identity(current_primary_target),
                "class_key": _target_class_key(current_primary_target),
                "label": _target_label(current_primary_target),
                "trust_policy": current_primary_target.get("trust_policy", "monitor"),
                "generated_at": current_generated_at or "",
                "decision_memory_status": current_primary_target.get("decision_memory_status", ""),
                "last_outcome": current_primary_target.get("last_outcome", ""),
            }
        )
    for entry in history[: HISTORY_WINDOW_RUNS - 1]:
        summary = entry.get("operator_summary") or {}
        primary_target = summary.get("primary_target") or {}
        trust_policy = summary.get("primary_target_trust_policy", "")
        if not primary_target or not trust_policy:
            continue
        events.append(
            {
                "key": _queue_identity(primary_target),
                "class_key": _target_class_key(primary_target),
                "label": _target_label(primary_target),
                "trust_policy": trust_policy,
                "generated_at": entry.get("generated_at", ""),
                "decision_memory_status": summary.get("decision_memory_status", ""),
                "last_outcome": summary.get("primary_target_last_outcome", ""),
            }
        )
    return sorted(events, key=lambda item: item.get("generated_at", ""), reverse=True)


def _target_policy_history(target: dict, policy_events: list[dict]) -> dict:
    key = _queue_identity(target)
    class_key = _target_class_key(target)
    target_events = [event for event in policy_events if event.get("key") == key]
    class_events = [event for event in policy_events if event.get("class_key") == class_key]
    target_policies = [event.get("trust_policy", "monitor") for event in target_events]
    class_policies = [event.get("trust_policy", "monitor") for event in class_events]
    recent_policy_path = " -> ".join(target_policies[:4]) if target_policies else ""
    class_policy_path = " -> ".join(class_policies[:4]) if class_policies else ""
    return {
        "policy_flip_count": _policy_flip_count(target_policies),
        "recent_policy_path": recent_policy_path or class_policy_path,
        "class_policy_flip_count": _policy_flip_count(class_policies),
        "class_policy_path": class_policy_path,
        "strong_policy_failure_count": _strong_policy_failure_count(target, policy_events),
    }


def _policy_flip_hotspots(policy_events: list[dict]) -> list[dict]:
    target_hotspots = _group_policy_hotspots(policy_events, key_name="key", label_name="label", scope="target")
    class_hotspots = _group_policy_hotspots(policy_events, key_name="class_key", label_name="class_key", scope="class")
    hotspots = target_hotspots + [item for item in class_hotspots if item.get("flip_count", 0) >= 2]
    hotspots.sort(key=lambda item: (-item.get("flip_count", 0), item.get("label", ""), item.get("scope", "")))
    return hotspots[:5]


def _group_policy_hotspots(
    policy_events: list[dict],
    *,
    key_name: str,
    label_name: str,
    scope: str,
) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for event in policy_events:
        key = event.get(key_name, "")
        if not key:
            continue
        grouped.setdefault(key, []).append(event)

    hotspots: list[dict] = []
    for events in grouped.values():
        policies = [event.get("trust_policy", "monitor") for event in events]
        flip_count = _policy_flip_count(policies)
        if flip_count <= 0:
            continue
        label = events[0].get(label_name, "")
        hotspots.append(
            {
                "scope": scope,
                "label": label,
                "flip_count": flip_count,
                "recent_policy_path": " -> ".join(policies[:4]),
            }
        )
    return hotspots


def _policy_flip_count(policies: list[str]) -> int:
    if len(policies) < 2:
        return 0
    flips = 0
    for previous, current in zip(policies, policies[1:]):
        if previous != current:
            flips += 1
    return flips


def _strong_policy_failure_count(target: dict, policy_events: list[dict]) -> int:
    strong_policies = {"act-now", "act-with-review"}
    key = _queue_identity(target)
    statuses = {"reopened", "persisting", "attempted"}
    count = 0
    for event in policy_events:
        if event.get("key") != key or event.get("trust_policy") not in strong_policies:
            continue
        history_status = event.get("decision_memory_status", "")
        last_outcome = event.get("last_outcome", "")
        if history_status in statuses or last_outcome in {"reopened", "no-change"}:
            count += 1
    return count


def _trust_policy_exception_for_target(
    target: dict,
    history_meta: dict,
    confidence_calibration: dict,
    *,
    current_bucket: int,
) -> tuple[str, str, str, str]:
    status = confidence_calibration.get("confidence_validation_status", "insufficient-data")
    policy = target.get("trust_policy", "monitor")
    floor = "act-with-review" if target.get("lane") == "blocked" and target.get("kind") == "setup" else "verify-first"

    if (
        status == "noisy"
        and target.get("decision_memory_status") == "reopened"
        and current_bucket == _recommendation_bucket(target)
    ):
        softened = _soften_trust_policy(policy, floor=floor)
        if softened == policy:
            return (
                "none",
                "",
                policy,
                target.get("trust_policy_reason", "No trust-policy reason is recorded yet."),
            )
        return (
            "softened-for-noise",
            "Recent trust noise plus a reopened target warrants a softer verification-first posture.",
            softened,
            "Recent trust noise warrants verifying the latest state before treating this recommendation as fully stable.",
        )

    if history_meta.get("strong_policy_failure_count", 0) >= 2 and current_bucket == _recommendation_bucket(target):
        softened = _soften_trust_policy(policy, floor=floor)
        if softened == policy:
            return (
                "none",
                "",
                policy,
                target.get("trust_policy_reason", "No trust-policy reason is recorded yet."),
            )
        return (
            "softened-for-reopen-risk",
            "Repeated reopen or unresolved behavior after earlier strong recommendations warrants a softer trust posture.",
            softened,
            "Recent reopen or unresolved behavior means closure evidence should be re-verified before overcommitting.",
        )

    if max(history_meta.get("policy_flip_count", 0), history_meta.get("class_policy_flip_count", 0)) >= 2 and current_bucket == _recommendation_bucket(target):
        softened = _soften_trust_policy(policy, floor=floor)
        if softened == policy:
            return (
                "none",
                "",
                policy,
                target.get("trust_policy_reason", "No trust-policy reason is recorded yet."),
            )
        return (
            "softened-for-flip-churn",
            "Recent trust-policy flips have been bouncing enough that this recommendation should not be treated as fully stable yet.",
            softened,
            "Recent trust-policy churn means this target should be handled with a softer, verification-aware posture.",
        )

    return (
        "none",
        "",
        policy,
        target.get("trust_policy_reason", "No trust-policy reason is recorded yet."),
    )


def _soften_trust_policy(policy: str, *, floor: str) -> str:
    order = ["act-now", "act-with-review", "verify-first", "monitor"]
    if floor not in order:
        floor = "verify-first"
    if policy not in order:
        return floor
    softened_index = min(order.index(policy) + 1, len(order) - 1)
    floor_index = order.index(floor)
    if softened_index > floor_index:
        softened_index = floor_index
    return order[softened_index]


def _recommendation_drift_status(
    primary_target_flip_count: int,
    primary_recent_policy_path: str,
    policy_flip_hotspots: list[dict],
) -> str:
    _ = primary_recent_policy_path
    repeated_hotspots = sum(1 for hotspot in policy_flip_hotspots if hotspot.get("flip_count", 0) >= 2)
    if primary_target_flip_count >= 2 or repeated_hotspots >= 2:
        return "drifting"
    if primary_target_flip_count == 1 or repeated_hotspots == 1:
        return "watch"
    return "stable"


def _recommendation_drift_summary(primary_target: dict, policy_flip_hotspots: list[dict]) -> str:
    flip_count = primary_target.get("policy_flip_count", 0)
    path = primary_target.get("recent_policy_path", "")
    label = _target_label(primary_target) or "The current target"
    if flip_count >= 2 and path:
        return f"{label} has flipped trust policy {flip_count} time(s) in the recent window: {path}."
    if flip_count == 1 and path:
        return f"{label} has started to wobble between trust policies in the recent window: {path}."
    if policy_flip_hotspots:
        hotspot = policy_flip_hotspots[0]
        return (
            f"Trust-policy drift is currently led by {hotspot.get('label', 'recent hotspots')} "
            f"with {hotspot.get('flip_count', 0)} flip(s) across {hotspot.get('recent_policy_path', '')}."
        )
    return "Recent trust-policy behavior is stable enough that no meaningful recommendation drift is recorded."


def _target_class_key(item: dict) -> str:
    return f"{item.get('lane', '')}:{item.get('kind', '') or 'unknown'}"


def _target_label(item: dict) -> str:
    repo = f"{item.get('repo')}: " if item.get("repo") else ""
    return f"{repo}{item.get('title', '')}".strip(": ")


def _recommendation_confidence(item: dict) -> tuple[float, str, list[str]]:
    score = 0.20
    lane_reason = ""
    decision_reason = ""
    aging_reason = ""
    penalties: list[tuple[float, str]] = []

    lane = item.get("lane", "")
    kind = item.get("kind", "")
    if lane == "blocked" and kind == "setup":
        score += 0.40
        lane_reason = "Blocked setup issue is directly stopping a trustworthy next step."
    elif lane == "blocked":
        score += 0.30
        lane_reason = "Blocked operator work outranks urgent and ready items."
    elif lane == "urgent":
        score += 0.20
        lane_reason = "Urgent drift or regression needs attention before ready work."
    elif lane == "ready":
        score += 0.05
        lane_reason = "Ready work is actionable, but lower pressure than blocked or urgent items."

    decision_memory_status = item.get("decision_memory_status", "")
    if decision_memory_status == "reopened":
        score += 0.20
        decision_reason = "This item reopened after an earlier quiet or resolved period."
    elif decision_memory_status == "persisting":
        score += 0.15
        decision_reason = "This item has persisted across multiple runs without clearing."
    elif decision_memory_status == "attempted":
        score += 0.10
        decision_reason = "A prior intervention happened, but the item is still open."

    aging_status = item.get("aging_status", "")
    if aging_status == "chronic":
        score += 0.15
        aging_reason = "This item is now chronic, so follow-through pressure is high."
    elif aging_status == "stale":
        score += 0.10
        aging_reason = "This item is stale and should be closed before it gets older."
    elif aging_status == "watch":
        score += 0.05
        aging_reason = "This item has repeated recently and is no longer brand new."

    if item.get("repeat_urgent"):
        score += 0.10
    if item.get("newly_stale"):
        score += 0.10
    priority = item.get("priority", 0)
    if priority >= 85:
        score += 0.10
    elif priority >= 70:
        score += 0.05

    if lane == "ready" and priority < 60:
        penalties.append((-0.15, "This is a lower-priority ready item, so the recommendation is less certain."))
    if not item.get("last_intervention") and not _has_recent_change_evidence(item):
        penalties.append((-0.10, "There is little recent change evidence behind this recommendation yet."))
    if _is_generic_recommendation(item.get("recommended_action", "")):
        penalties.append((-0.10, "The suggested next step is still generic rather than tightly item-specific."))

    for penalty, _reason in penalties:
        score += penalty
    score = max(0.05, min(0.95, round(score, 2)))
    label = _confidence_label(score)

    reasons = [reason for reason in (lane_reason, decision_reason, aging_reason) if reason]
    if penalties:
        reasons.append(sorted(penalties, key=lambda item: item[0])[0][1])
    return score, label, reasons[:4]


def _apply_calibration_adjustment(
    item: dict,
    score: float,
    confidence_calibration: dict,
) -> tuple[float, str, float, str]:
    status = confidence_calibration.get("confidence_validation_status", "insufficient-data")
    current_label = _confidence_label(score)
    adjustment = 0.0
    reason = "Calibration is too lightly exercised to change the live score yet."

    if status == "healthy" and item.get("lane") in {"blocked", "urgent"}:
        adjustment += 0.05
        reason = "Healthy calibration slightly strengthens blocked and urgent recommendations."
    elif status == "mixed":
        reason = "Mixed calibration keeps the live score unchanged for now."
    elif status == "noisy":
        if current_label == "high":
            adjustment -= 0.10
            reason = "Noisy calibration softens a previously high-confidence recommendation."
        elif current_label == "medium":
            adjustment -= 0.05
            reason = "Noisy calibration slightly softens a medium-confidence recommendation."
        else:
            reason = "Noisy calibration leaves already low-confidence recommendations unchanged."

    if status == "noisy" and item.get("decision_memory_status") == "reopened":
        adjustment -= 0.05
        reason = "Noisy calibration further softens reopened recommendations until they are re-verified."

    tuned_score = max(0.05, min(0.95, round(score + adjustment, 2)))
    return tuned_score, _confidence_label(tuned_score), round(adjustment, 2), reason


def _confidence_label(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.45:
        return "medium"
    return "low"


def _has_recent_change_evidence(item: dict) -> bool:
    return any(
        [
            item.get("repeat_urgent"),
            item.get("newly_stale"),
            item.get("reopened"),
            item.get("stale"),
            item.get("aging_status") in {"stale", "chronic"},
            item.get("decision_memory_status") in {"reopened", "attempted", "persisting"},
        ]
    )


def _is_generic_recommendation(action: str) -> bool:
    normalized = (action or "").strip().lower()
    if not normalized:
        return True
    return any(phrase in normalized for phrase in GENERIC_RECOMMENDATION_PHRASES)


def _is_generic_monitor_guidance(action: str) -> bool:
    normalized = (action or "").strip().lower()
    return bool(normalized) and any(phrase in normalized for phrase in GENERIC_MONITOR_PHRASES)


def _is_generic_baseline_guidance(action: str, watch_guidance: dict | None = None) -> bool:
    normalized = (action or "").strip().lower()
    if normalized and any(phrase in normalized for phrase in GENERIC_BASELINE_PHRASES):
        return True
    return not normalized and bool(watch_guidance and watch_guidance.get("full_refresh_due"))


def _trust_policy_for_item(
    item: dict,
    tuned_score: float,
    tuned_label: str,
    confidence_calibration: dict,
    action_text: str,
    *,
    watch_guidance: dict | None = None,
) -> tuple[str, str]:
    status = confidence_calibration.get("confidence_validation_status", "insufficient-data")
    lane = item.get("lane", "")
    decision_memory_status = item.get("decision_memory_status", "")
    generic_baseline = _is_generic_baseline_guidance(action_text, watch_guidance)
    generic_monitor = _is_generic_monitor_guidance(action_text)

    if lane == "deferred" or (lane == "ready" and tuned_label == "low"):
        return "monitor", "This is low-pressure work, so monitoring is safer than forcing a strong closure move."
    if generic_baseline or generic_monitor:
        return "verify-first", "The next step is generic baseline or monitor guidance, so verify the latest state before treating it as decisive."
    if decision_memory_status == "reopened" and status in {"mixed", "noisy"}:
        return "verify-first", "This item reopened under less-trustworthy calibration, so verify the latest state before acting."
    if status == "noisy" and tuned_score < 0.75:
        return "verify-first", "Recent calibration is noisy, so this recommendation should be verified before acting on it."
    if lane == "blocked" and tuned_score >= 0.75:
        return "act-now", "Blocked work with tuned high confidence should be cleared before new work."
    if lane == "urgent" and tuned_score >= 0.60:
        return "act-with-review", "Urgent work has enough tuned confidence to act, with a quick operator review."
    if lane == "ready" and tuned_score >= 0.75:
        return "act-with-review", "Ready work is strong enough to act on, but it still benefits from a quick human review."
    if status == "healthy":
        return "act-with-review", "Healthy calibration supports a confident next step, with light operator judgment."
    return "monitor", "The current signal is not strong enough to force immediate action, so monitor and reassess on the next cycle."


def _recommendation_bucket(item: dict) -> int:
    lane = item.get("lane", "")
    if lane == "blocked" and item.get("kind") == "setup":
        return 0
    if lane == "blocked":
        return 1
    if lane == "urgent" and item.get("aging_status") in {"stale", "chronic"}:
        return 2
    if lane == "urgent" and item.get("reopened"):
        return 3
    if lane == "urgent":
        return 4
    if lane == "ready":
        return 5
    return 6


def _decision_memory_map(recent_runs: list[dict], evidence_events: list[dict]) -> dict[str, dict]:
    evidence_by_key: dict[str, list[dict]] = {}
    for event in evidence_events:
        key = event.get("item_id") or _queue_identity(event)
        evidence_by_key.setdefault(key, []).append(event)
    for events in evidence_by_key.values():
        events.sort(key=lambda item: item.get("recorded_at", ""), reverse=True)

    history_keys = {
        key
        for snapshot in recent_runs
        for key, item in (snapshot.get("items") or {}).items()
        if item.get("lane") != "deferred"
    }
    current_snapshot = recent_runs[0] if recent_runs else {"items": {}, "generated_at": ""}
    current_items = {
        key: item
        for key, item in (current_snapshot.get("items") or {}).items()
        if item.get("lane") != "deferred"
    }
    attention_history = [_attention_items(snapshot) for snapshot in recent_runs]
    memory: dict[str, dict] = {}

    recently_quieted_count = 0
    confirmed_resolved_count = 0
    for key in history_keys:
        current_item = current_items.get(key)
        latest_event = (evidence_by_key.get(key) or [None])[0]
        if current_item:
            status = _current_decision_memory_status(key, current_item, recent_runs, latest_event)
            previous_match = recent_runs[1]["items"].get(key) if len(recent_runs) > 1 else None
            outcome = _current_item_last_outcome(current_item, previous_match, status)
            resolution_evidence = _current_item_resolution_evidence(
                current_item,
                status,
                latest_event,
                previous_match,
                recent_runs,
            )
            memory[key] = {
                "decision_memory_status": status,
                "last_seen_at": current_snapshot.get("generated_at", ""),
                "last_intervention": latest_event or {},
                "last_outcome": outcome,
                "resolution_evidence": resolution_evidence,
            }
            continue

        absent_info = _absent_decision_memory(key, attention_history, recent_runs, latest_event)
        if absent_info["status"] == "quieted":
            recently_quieted_count += 1
        elif absent_info["status"] == "confirmed_resolved":
            confirmed_resolved_count += 1
        memory[key] = {
            "decision_memory_status": absent_info["status"],
            "last_seen_at": absent_info["last_seen_at"],
            "last_intervention": latest_event or {},
            "last_outcome": absent_info["last_outcome"],
            "resolution_evidence": absent_info["resolution_evidence"],
        }

    recent_interventions = _recent_interventions(evidence_events)
    reopened_after_resolution_count = sum(
        1 for item in current_items.values() if memory.get(_queue_identity(item), {}).get("decision_memory_status") == "reopened"
    )
    return {
        **{
            key: {
                "decision_memory_status": value.get("decision_memory_status", "new"),
                "last_seen_at": value.get("last_seen_at", ""),
                "last_intervention": value.get("last_intervention", {}),
                "last_outcome": value.get("last_outcome", "no-change"),
                "resolution_evidence": value.get("resolution_evidence", ""),
            }
            for key, value in memory.items()
        },
        "__summary__": {
            "recently_quieted_count": recently_quieted_count,
            "confirmed_resolved_count": confirmed_resolved_count,
            "reopened_after_resolution_count": reopened_after_resolution_count,
            "recent_interventions": recent_interventions,
            "decision_memory_window_runs": len(recent_runs),
        },
    }


def _current_decision_memory_status(
    key: str,
    current_item: dict,
    recent_runs: list[dict],
    latest_event: dict | None,
) -> str:
    if _was_resolved_then_reopened(key, recent_runs, current_item):
        return "reopened"
    prior_matches = [
        snapshot["items"].get(key)
        for snapshot in recent_runs[1:]
        if snapshot["items"].get(key) and snapshot["items"][key].get("lane") != "deferred"
    ]
    if not prior_matches:
        return "new"
    if latest_event:
        return "attempted"
    return "persisting"


def _was_resolved_then_reopened(key: str, recent_runs: list[dict], current_item: dict) -> bool:
    if current_item.get("lane") not in ATTENTION_LANES:
        return False
    absent_streak = 0
    saw_earlier_attention = False
    for snapshot in recent_runs[1:]:
        match = (snapshot.get("items") or {}).get(key)
        if match and match.get("lane") in ATTENTION_LANES:
            saw_earlier_attention = True
            break
        absent_streak += 1
    return absent_streak >= 1 and saw_earlier_attention


def _current_item_last_outcome(current_item: dict, previous_match: dict | None, status: str) -> str:
    if status == "reopened":
        return "reopened"
    if not previous_match:
        return "no-change"
    if previous_match.get("lane") in ATTENTION_LANES and current_item.get("lane") not in ATTENTION_LANES:
        return "quieted"
    if previous_match.get("lane") == "blocked" and current_item.get("lane") in {"urgent", "ready"}:
        return "improved"
    if previous_match.get("lane") == "urgent" and current_item.get("lane") == "ready":
        return "improved"
    return "no-change"


def _current_item_resolution_evidence(
    current_item: dict,
    status: str,
    latest_event: dict | None,
    previous_match: dict | None,
    recent_runs: list[dict],
) -> str:
    if status == "reopened":
        return "This item returned after an earlier quiet or resolved period, so treat it as a regression rather than a net-new issue."
    if status == "attempted" and latest_event:
        return (
            f"The last intervention was {_format_intervention(latest_event).lower()}, "
            "but the item is still open."
        )
    if status == "persisting":
        appearances = sum(
            1
            for snapshot in recent_runs
            if (snapshot.get("items") or {}).get(_queue_identity(current_item), {}).get("lane") != "deferred"
            and (snapshot.get("items") or {}).get(_queue_identity(current_item))
        )
        return f"This item is still open after {appearances} recent run(s), with no confirmed recovery signal yet."
    if previous_match and previous_match.get("lane") in ATTENTION_LANES and current_item.get("lane") not in ATTENTION_LANES:
        return "The last run reduced this item out of blocked or urgent lanes, but it is not yet confirmed resolved."
    return "No earlier intervention or durable recovery evidence is recorded in the recent window yet."


def _absent_decision_memory(
    key: str,
    attention_history: list[dict[str, dict]],
    recent_runs: list[dict],
    latest_event: dict | None,
) -> dict:
    current_absent = key not in attention_history[0]
    previous_present = len(attention_history) > 1 and key in attention_history[1]
    previous_absent = len(attention_history) > 1 and key not in attention_history[1]
    earlier_present = any(key in snapshot for snapshot in attention_history[2:])
    last_seen_at = ""
    for snapshot in recent_runs[1:]:
        match = (snapshot.get("items") or {}).get(key)
        if match:
            last_seen_at = snapshot.get("generated_at", "")
            break
    if current_absent and previous_present:
        return {
            "status": "quieted",
            "last_outcome": "quieted",
            "last_seen_at": last_seen_at,
            "resolution_evidence": "This item is absent for 1 run after prior attention, so it looks quieter but is not yet confirmed resolved.",
        }
    if current_absent and previous_absent and earlier_present:
        return {
            "status": "confirmed_resolved",
            "last_outcome": "confirmed-resolved",
            "last_seen_at": last_seen_at,
            "resolution_evidence": "This item has stayed absent from blocked or urgent lanes for 2 consecutive runs and now counts as confirmed resolved.",
        }
    if latest_event:
        return {
            "status": "attempted",
            "last_outcome": "no-change",
            "last_seen_at": last_seen_at,
            "resolution_evidence": "A recent intervention is recorded, but there is not enough absence history yet to count this as durable resolution.",
        }
    return {
        "status": "new",
        "last_outcome": "no-change",
        "last_seen_at": last_seen_at,
        "resolution_evidence": "No durable resolution evidence is recorded for this item yet.",
    }


def _recent_interventions(evidence_events: list[dict]) -> list[dict]:
    interventions: list[dict] = []
    for event in evidence_events[:5]:
        interventions.append(
            {
                "item_id": event.get("item_id", ""),
                "repo": event.get("repo", ""),
                "title": event.get("title", ""),
                "event_type": event.get("event_type", ""),
                "recorded_at": event.get("recorded_at", ""),
                "outcome": event.get("outcome", ""),
            }
        )
    return interventions


def _summary_decision_memory(primary_target: dict, decision_memory_map: dict[str, dict], recent_runs: list[dict]) -> dict:
    summary = decision_memory_map.get("__summary__", {})
    recent_interventions = summary.get("recent_interventions", [])
    if primary_target:
        key = _queue_identity(primary_target)
        memory = decision_memory_map.get(key, {})
        return {
            "decision_memory_status": memory.get("decision_memory_status", "new"),
            "primary_target_last_seen_at": memory.get("last_seen_at", recent_runs[0].get("generated_at", "") if recent_runs else ""),
            "primary_target_last_intervention": memory.get("last_intervention", {}),
            "primary_target_last_outcome": memory.get("last_outcome", "no-change"),
            "primary_target_resolution_evidence": memory.get("resolution_evidence", ""),
            "recent_interventions": recent_interventions,
            "recently_quieted_count": summary.get("recently_quieted_count", 0),
            "confirmed_resolved_count": summary.get("confirmed_resolved_count", 0),
            "reopened_after_resolution_count": summary.get("reopened_after_resolution_count", 0),
            "decision_memory_window_runs": summary.get("decision_memory_window_runs", len(recent_runs)),
            "resolution_evidence_summary": _resolution_evidence_summary(
                memory.get("decision_memory_status", "new"),
                memory.get("resolution_evidence", ""),
                summary.get("recently_quieted_count", 0),
                summary.get("confirmed_resolved_count", 0),
                summary.get("reopened_after_resolution_count", 0),
            ),
        }
    default_status = "confirmed_resolved" if summary.get("confirmed_resolved_count", 0) else "quieted" if summary.get("recently_quieted_count", 0) else "new"
    default_outcome = "confirmed-resolved" if summary.get("confirmed_resolved_count", 0) else "quieted" if summary.get("recently_quieted_count", 0) else "no-change"
    return {
        "decision_memory_status": default_status,
        "primary_target_last_seen_at": "",
        "primary_target_last_intervention": recent_interventions[0] if recent_interventions else {},
        "primary_target_last_outcome": default_outcome,
        "primary_target_resolution_evidence": _resolution_evidence_summary(
            default_status,
            "",
            summary.get("recently_quieted_count", 0),
            summary.get("confirmed_resolved_count", 0),
            summary.get("reopened_after_resolution_count", 0),
        ),
        "recent_interventions": recent_interventions,
        "recently_quieted_count": summary.get("recently_quieted_count", 0),
        "confirmed_resolved_count": summary.get("confirmed_resolved_count", 0),
        "reopened_after_resolution_count": summary.get("reopened_after_resolution_count", 0),
        "decision_memory_window_runs": summary.get("decision_memory_window_runs", len(recent_runs)),
        "resolution_evidence_summary": _resolution_evidence_summary(
            default_status,
            "",
            summary.get("recently_quieted_count", 0),
            summary.get("confirmed_resolved_count", 0),
            summary.get("reopened_after_resolution_count", 0),
        ),
    }


def _resolution_evidence_summary(
    decision_memory_status: str,
    primary_target_resolution_evidence: str,
    recently_quieted_count: int,
    confirmed_resolved_count: int,
    reopened_after_resolution_count: int,
) -> str:
    if decision_memory_status == "reopened":
        return (
            f"{primary_target_resolution_evidence} "
            f"{reopened_after_resolution_count} item(s) reopened after an earlier quiet or resolved state in the recent window."
        ).strip()
    if decision_memory_status == "confirmed_resolved":
        return f"{confirmed_resolved_count} item(s) now count as confirmed resolved in the recent window."
    if decision_memory_status == "quieted":
        return f"{recently_quieted_count} item(s) are quieter, but not yet confirmed resolved."
    if primary_target_resolution_evidence:
        return primary_target_resolution_evidence
    return (
        f"Resolution evidence in the recent window: {confirmed_resolved_count} confirmed resolved, "
        f"{recently_quieted_count} quieted, {reopened_after_resolution_count} reopened."
    )


def _format_intervention(intervention: dict) -> str:
    if not intervention:
        return "No recent intervention is recorded yet."
    recorded_at = intervention.get("recorded_at", "")
    when = recorded_at[:10] if recorded_at else "recently"
    event_type = intervention.get("event_type", "recorded")
    outcome = intervention.get("outcome", event_type)
    repo = f"{intervention.get('repo')}: " if intervention.get("repo") else ""
    title = intervention.get("title", "").strip()
    subject = f"{repo}{title}".strip(": ")
    if subject:
        return f"{when} — {event_type} for {subject} ({outcome})"
    return f"{when} — {event_type} ({outcome})"


def _recent_validation_outcomes_line(outcomes: list[dict]) -> str:
    if not outcomes:
        return ""
    parts = []
    for item in outcomes[:3]:
        target_label = item.get("target_label", "Operator target")
        confidence_label = item.get("confidence_label", "low")
        outcome = str(item.get("outcome", "unresolved")).replace("_", " ")
        parts.append(f"{target_label} [{confidence_label}] -> {outcome}")
    return "; ".join(parts)


def _aging_status(appearances: int, age_days: int) -> str:
    if appearances >= 5 or age_days > 21:
        return "chronic"
    if appearances >= 3 or age_days > 7:
        return "stale"
    if appearances >= 2:
        return "watch"
    return "fresh"


def _attention_age_bands(current_attention: dict[str, dict]) -> dict[str, int]:
    bands = {"0-1 days": 0, "2-7 days": 0, "8-21 days": 0, "22+ days": 0}
    for item in current_attention.values():
        age_days = item.get("age_days", 0)
        if age_days <= 1:
            bands["0-1 days"] += 1
        elif age_days <= 7:
            bands["2-7 days"] += 1
        elif age_days <= 21:
            bands["8-21 days"] += 1
        else:
            bands["22+ days"] += 1
    return bands


def _longest_persisting_item(resolution_targets: list[dict]) -> dict:
    if not resolution_targets:
        return {}
    item = max(
        resolution_targets,
        key=lambda target: (
            target.get("age_days", 0),
            target.get("priority", 0),
            target.get("repo", ""),
            target.get("title", ""),
        ),
    )
    return {
        "item_id": item.get("item_id", ""),
        "repo": item.get("repo", ""),
        "title": item.get("title", ""),
        "lane": item.get("lane", ""),
        "age_days": item.get("age_days", 0),
        "aging_status": item.get("aging_status", "fresh"),
    }


def _resolution_target_sort_key(item: dict) -> tuple:
    return (
        _recommendation_bucket(item),
        -item.get("confidence_score", 0.0),
        -item.get("age_days", 0),
        -item.get("priority", 0),
        item.get("repo", ""),
        item.get("title", ""),
    )


def _primary_target(resolution_targets: list[dict]) -> dict:
    return resolution_targets[0] if resolution_targets else {}


def _primary_target_reason(primary_target: dict) -> str:
    if not primary_target:
        return ""
    if primary_target.get("lane") == "blocked" and primary_target.get("kind") == "setup":
        return "This is a setup blocker, so nothing trustworthy can proceed until the prerequisite is cleared."
    if primary_target.get("lane") == "blocked":
        return "This is the highest blocked item, so it outranks urgent and ready work."
    if primary_target.get("lane") == "urgent" and primary_target.get("aging_status") == "chronic":
        return "This urgent item has survived multiple cycles, so follow-through debt now outweighs newer ready work."
    if primary_target.get("lane") == "urgent" and primary_target.get("newly_stale"):
        return "This urgent item has just crossed into follow-through debt, so it should be closed before it turns chronic."
    if primary_target.get("lane") == "urgent" and primary_target.get("stale"):
        return "This urgent item is already stale, so it outranks fresher urgent items and ready work."
    if primary_target.get("lane") == "urgent" and primary_target.get("reopened"):
        return "This urgent item reappeared after disappearing, so it should be closed before it churns again."
    if primary_target.get("lane") == "urgent":
        return "This is the live urgent item with the highest current pressure, so it outranks ready work."
    if primary_target.get("lane") == "ready":
        return "Nothing is blocked or urgent, so this is the highest-value ready item to close next."
    return "This remains the highest-value target in the current queue."


def _primary_target_done_criteria(primary_target: dict) -> str:
    if not primary_target:
        return ""
    if primary_target.get("lane") == "blocked" and primary_target.get("kind") == "setup":
        return "Clear the failing prerequisite, rerun the relevant command, and confirm the blocker no longer appears on the next run."
    if primary_target.get("kind") in {"campaign", "governance"} and primary_target.get("lane") in {"blocked", "urgent"}:
        return "Inspect and reconcile the drift, then confirm this item no longer reappears on the next run."
    if primary_target.get("lane") in {"blocked", "urgent"}:
        return "Complete the recommended action and confirm the item exits the blocked or urgent queue on the next run."
    if primary_target.get("lane") == "ready":
        return "Make the manual decision and confirm the item either clears or moves into a lower-pressure lane on the next run."
    return "Confirm this item no longer requires blocked, urgent, or ready attention on the next run."


def _closure_guidance(primary_target: dict, done_criteria: str) -> str:
    if not primary_target:
        return "No active closure target is open right now."
    action = primary_target.get("recommended_action", "")
    if action:
        return f"{action} Treat this as done only when {done_criteria[0].lower() + done_criteria[1:]}"
    return f"Treat this as done only when {done_criteria[0].lower() + done_criteria[1:]}"


def _operator_confidence_summary(
    primary_target: dict,
    next_action: str,
    watch_guidance: dict,
    confidence_calibration: dict,
) -> dict:
    primary_score = primary_target.get("confidence_score", 0.05) if primary_target else 0.05
    primary_label = primary_target.get("confidence_label", _confidence_label(primary_score)) if primary_target else "low"
    primary_reasons = primary_target.get("confidence_reasons", []) if primary_target else []
    primary_trust_policy = primary_target.get("trust_policy", "monitor") if primary_target else "monitor"
    primary_trust_policy_reason = (
        primary_target.get("trust_policy_reason", "No trust-policy reason is recorded yet.")
        if primary_target
        else "No trust-policy reason is recorded yet."
    )
    next_score, next_label, next_reasons = _next_action_confidence(
        primary_target,
        next_action,
        watch_guidance,
    )
    next_trust_policy, next_trust_policy_reason = _trust_policy_for_item(
        primary_target,
        next_score,
        next_label,
        confidence_calibration,
        next_action,
        watch_guidance=watch_guidance,
    )
    if (
        primary_target.get("trust_exception_status") not in {None, "", "none"}
        and primary_target.get("class_normalization_status") != "applied"
        and primary_target.get("trust_recovery_status") != "earned"
    ):
        next_trust_policy, next_trust_policy_reason = _soften_next_action_policy(
            next_trust_policy,
            next_trust_policy_reason,
            target_policy=primary_trust_policy,
            exception_reason=primary_target.get("trust_exception_reason", ""),
        )
    return {
        "primary_target_confidence_score": primary_score,
        "primary_target_confidence_label": primary_label,
        "primary_target_confidence_reasons": primary_reasons,
        "next_action_confidence_score": next_score,
        "next_action_confidence_label": next_label,
        "next_action_confidence_reasons": next_reasons,
        "recommendation_quality_summary": _recommendation_quality_summary(
            next_label,
            next_reasons,
            next_trust_policy,
        ),
        "primary_target_trust_policy": primary_trust_policy,
        "primary_target_trust_policy_reason": primary_trust_policy_reason,
        "next_action_trust_policy": next_trust_policy,
        "next_action_trust_policy_reason": next_trust_policy_reason,
        "adaptive_confidence_summary": _adaptive_confidence_summary(
            confidence_calibration.get("confidence_validation_status", "insufficient-data"),
            primary_target,
            primary_trust_policy,
            next_trust_policy,
        ),
    }


def _next_action_confidence(primary_target: dict, next_action: str, watch_guidance: dict) -> tuple[float, str, list[str]]:
    base_score = primary_target.get("confidence_score", 0.05) if primary_target else 0.05
    action = (next_action or "").strip()
    reasons: list[str] = []
    normalized = action.lower()
    if _is_item_specific_action(primary_target, action):
        base_score += 0.05
        reasons.append("The next step is tied directly to the current top target.")
    elif any(phrase in normalized for phrase in GENERIC_MONITOR_PHRASES):
        base_score -= 0.10
        reasons.append("The next step is mostly watch-and-monitor guidance, so it is less decisive.")
    elif any(phrase in normalized for phrase in GENERIC_BASELINE_PHRASES) or watch_guidance.get("full_refresh_due"):
        base_score -= 0.10
        reasons.append("The next step is baseline-refresh guidance rather than a direct closure action.")
    else:
        reasons.append("The next step follows the current top target closely enough to guide the next move.")
    score = max(0.05, min(0.95, round(base_score, 2)))
    label = _confidence_label(score)
    return score, label, reasons[:3]


def _soften_next_action_policy(
    next_policy: str,
    next_reason: str,
    *,
    target_policy: str,
    exception_reason: str,
) -> tuple[str, str]:
    order = {"act-now": 0, "act-with-review": 1, "verify-first": 2, "monitor": 3}
    if order.get(next_policy, 99) < order.get(target_policy, 99):
        return (
            target_policy,
            exception_reason or next_reason or "The current target warrants a softer trust posture before acting.",
        )
    return next_policy, next_reason


def _is_item_specific_action(primary_target: dict, next_action: str) -> bool:
    if not primary_target or not next_action:
        return False
    normalized = next_action.lower()
    title = (primary_target.get("title") or "").lower()
    repo = (primary_target.get("repo") or "").lower()
    recommended_action = (primary_target.get("recommended_action") or "").lower()
    if title and title in normalized:
        return True
    if repo and repo in normalized:
        return True
    if recommended_action and recommended_action == normalized:
        return True
    if normalized.startswith("close the remaining top target next:"):
        return True
    return False


def _recommendation_quality_summary(label: str, reasons: list[str], trust_policy: str) -> str:
    reason = reasons[0] if reasons else "the current evidence is limited."
    if trust_policy == "verify-first":
        return (
            "Tentative recommendation; verify before acting because "
            f"{reason[0].lower() + reason[1:]}"
        )
    if trust_policy == "monitor":
        return (
            "Tentative recommendation; monitor before forcing a closure move because "
            f"{reason[0].lower() + reason[1:]}"
        )
    if label == "high":
        return f"Strong recommendation because {reason[0].lower() + reason[1:]}"
    if label == "medium":
        return f"Useful recommendation, but still partly judgment-based because {reason[0].lower() + reason[1:]}"
    return f"Tentative recommendation; monitor or verify before treating it as the single top priority because {reason[0].lower() + reason[1:]}"


def _adaptive_confidence_summary(
    calibration_status: str,
    primary_target: dict,
    primary_trust_policy: str,
    next_trust_policy: str,
) -> str:
    lane = primary_target.get("lane", "")
    exception_status = primary_target.get("trust_exception_status", "none")
    exception_pattern_status = primary_target.get("exception_pattern_status", "none")
    trust_recovery_status = primary_target.get("trust_recovery_status", "none")
    exception_retirement_status = primary_target.get("exception_retirement_status", "none")
    policy_debt_status = primary_target.get("policy_debt_status", "none")
    class_normalization_status = primary_target.get("class_normalization_status", "none")
    class_memory_freshness_status = primary_target.get("class_memory_freshness_status", "insufficient-data")
    class_decay_status = primary_target.get("class_decay_status", "none")
    class_trust_reweight_direction = primary_target.get("class_trust_reweight_direction", "neutral")
    class_trust_reweight_effect = primary_target.get("class_trust_reweight_effect", "none")
    class_trust_momentum_status = primary_target.get("class_trust_momentum_status", "insufficient-data")
    class_reweight_stability_status = primary_target.get("class_reweight_stability_status", "watch")
    class_reweight_transition_status = primary_target.get("class_reweight_transition_status", "none")
    class_transition_health_status = primary_target.get("class_transition_health_status", "none")
    class_transition_resolution_status = primary_target.get("class_transition_resolution_status", "none")
    transition_closure_likely_outcome = primary_target.get("transition_closure_likely_outcome", "none")
    class_pending_debt_status = primary_target.get("class_pending_debt_status", "none")
    recovery_confidence_label = primary_target.get("recovery_confidence_label", "low")
    drift_status = primary_target.get("recommendation_drift_status", "")
    if class_transition_resolution_status == "confirmed":
        return "The earlier pending class signal persisted long enough to confirm a broader class posture."
    if class_transition_resolution_status == "cleared":
        return "The earlier pending class signal faded before it earned confirmation, so it has been cleared."
    if class_transition_resolution_status == "expired":
        return "The earlier pending class signal aged out without confirmation, so it no longer changes the live posture."
    if class_transition_resolution_status == "blocked":
        return "Local target instability is preventing a pending class transition from confirming."
    if transition_closure_likely_outcome == "confirm-soon":
        return "The current pending class signal looks strong enough to confirm soon if the next run stays aligned."
    if transition_closure_likely_outcome == "hold":
        return "The current pending class signal is still viable, but it is not strong enough to trust fully yet."
    if transition_closure_likely_outcome == "clear-risk":
        return "The current pending class signal is fading and may be cleared before it confirms."
    if transition_closure_likely_outcome == "expire-risk":
        return "The current pending class signal has lingered long enough that it is at risk of aging out."
    if transition_closure_likely_outcome == "blocked":
        return "Local target instability is still blocking this pending class signal from confirming."
    if class_pending_debt_status == "active-debt":
        return "This class keeps accumulating unresolved pending states, so new pending signals there should be treated more cautiously."
    if class_pending_debt_status == "clearing":
        return "This class is resolving pending transitions more cleanly again, so pending debt is easing."
    if class_transition_health_status == "stalled":
        return "The current pending class signal is still visible, but it has lingered without enough strengthening to confirm safely."
    if class_transition_health_status == "holding":
        return "The current pending class signal remains visible, but it is no longer getting stronger."
    if class_transition_health_status == "building":
        return "The current pending class signal is still accumulating and may confirm if it stays consistent."
    if class_transition_health_status == "expired":
        return "An earlier pending class signal aged out, so the weaker class posture stays in place."
    if class_transition_health_status == "blocked":
        return "Local target instability is keeping a pending class strengthening attempt blocked."
    if class_reweight_transition_status == "confirmed-support":
        return "Fresh class evidence has stayed strong long enough to confirm broader normalization for this target."
    if class_reweight_transition_status == "confirmed-caution":
        return "Caution-heavy class evidence has stayed strong long enough to confirm broader caution for this target."
    if class_reweight_transition_status == "pending-support":
        return "Healthier class support is visible, but it has not stayed persistent long enough to confirm broader normalization yet."
    if class_reweight_transition_status == "pending-caution":
        return "Caution-heavy class evidence is visible, but it has not stayed persistent long enough to confirm sticky class caution yet."
    if class_reweight_transition_status == "blocked":
        return "Positive class strengthening is still blocked by local reopen, flip, or blocked-recovery noise."
    if class_reweight_stability_status == "oscillating":
        return "Class guidance is bouncing too much to strengthen safely right now, so keep the class signal visible but unconfirmed."
    if class_trust_momentum_status == "sustained-support":
        return "Fresh class evidence has stayed strong long enough to confirm broader normalization."
    if class_trust_momentum_status == "sustained-caution":
        return "Caution-heavy class evidence has stayed strong long enough to confirm broader caution."
    if class_trust_momentum_status == "building":
        return "Class evidence is trending in one direction, but it has not held long enough to lock in yet."
    if class_trust_momentum_status == "reversing":
        return "Recent class evidence is changing direction, so earlier class guidance is being softened."
    if class_trust_momentum_status == "unstable":
        return "Recent class evidence is oscillating too much to safely strengthen class posture."
    if class_trust_reweight_effect == "normalization-boosted":
        return "Fresh class evidence is consistently improving and actively strengthened class guidance for this target."
    if class_trust_reweight_effect == "normalization-softened":
        return "Class normalization stayed visible, but fresh class support is no longer strong enough to keep the full stronger posture in place."
    if class_trust_reweight_effect == "policy-debt-strengthened":
        return "Fresh class caution is still heavy enough to keep class-level trust conservative."
    if class_trust_reweight_effect == "policy-debt-softened":
        return "Class-level caution is fading rather than disappearing all at once, so the class posture softened."
    if class_trust_reweight_direction == "supporting-normalization":
        return "Fresh class evidence is consistently improving, but it is not yet strong enough to move the final posture by itself."
    if class_trust_reweight_direction == "supporting-caution":
        return "Recent class evidence is still caution-heavy enough to keep class trust conservative."
    if class_decay_status == "normalization-decayed":
        return "Class normalization was pulled back because the class lesson is too old or too lightly refreshed to keep carrying the stronger posture."
    if class_decay_status == "policy-debt-decayed":
        return "Earlier sticky class caution no longer has enough fresh support to stay strong, so class-debt pressure is softening."
    if class_decay_status == "blocked":
        return "Local target noise still overrides healthier class memory, so class freshness is not changing the live posture yet."
    if class_memory_freshness_status == "stale":
        return "Older class evidence is being down-weighted, so stale class lessons should not dominate the current trust posture."
    if class_memory_freshness_status == "mixed-age":
        return "Class memory is still useful, but part of the class signal is aging and should be treated more cautiously."
    if class_normalization_status == "applied":
        return "This class has repeatedly earned clean retirement, so the current target inherits a stronger act-with-review posture without changing lane priority."
    if class_normalization_status == "candidate":
        return "This class is trending healthier, but the current target still needs a little more local stability before class-level normalization can apply."
    if class_normalization_status == "blocked":
        return "Class-level normalization is blocked by local reopen, flip, or calibration noise, so the softer caution should stay target-specific."
    if policy_debt_status == "class-debt":
        return "This class keeps carrying sticky caution, so class-level trust relaxation should stay conservative for now."
    if policy_debt_status == "one-off-noise":
        return "The broader class looks healthier than this target, so the softer caution remains target-specific instead of class-wide."
    if exception_retirement_status == "retired":
        return "Recovery confidence is high enough that the earlier soft caution has been formally retired, so the stronger trust policy is back in place."
    if exception_retirement_status == "candidate":
        return "Recovery confidence is building, but the target has not earned exception retirement yet, so keep the current caution in place."
    if exception_retirement_status == "blocked":
        return "Exception retirement is still blocked by reopen, flip, or calibration noise, so the softer caution should stay in place."
    if trust_recovery_status == "earned":
        return "Recent stability has earned this recommendation back from verify-first to act-with-review, so the softer caution can start relaxing."
    if trust_recovery_status == "candidate":
        return "Recent stability is improving, but the target has not held steady long enough to earn stronger trust yet."
    if trust_recovery_status == "blocked":
        return "Trust recovery is still blocked by fresh reopen, flip, or calibration noise, so keep the softer posture in place."
    if exception_pattern_status == "useful-caution":
        return "Recent soft caution has been justified, so the verification-aware posture still looks appropriate."
    if exception_pattern_status == "overcautious":
        if recovery_confidence_label == "high":
            return "Recent soft caution may now be more cautious than the evidence supports, and recovery confidence is high enough that retirement is coming into view."
        return "Recent soft caution may now be more cautious than the evidence supports, so watch for trust recovery instead of leaving verify-first in place by default."
    if exception_status == "softened-for-noise":
        return "Recent trust noise softened the recommendation, so verify the latest state before treating it as fully stable."
    if exception_status == "softened-for-flip-churn":
        return "Recent trust-policy flip churn softened the recommendation, so use it with extra verification instead of treating it as fully settled."
    if exception_status == "softened-for-reopen-risk":
        return "Recent reopen or unresolved behavior softened the recommendation, so confirm closure evidence before overcommitting."
    if drift_status == "drifting":
        return "Trust-policy behavior has been unstable recently, so keep the recommendation visible but verify before leaning too hard on it."
    if primary_trust_policy == "monitor":
        return "The current signal stays light-touch, so keep monitoring instead of forcing action."
    if calibration_status == "healthy" and primary_trust_policy == "act-now" and lane in {"blocked", "urgent"}:
        return "Calibration is validating well, so the live recommendation was strengthened and is ready for immediate action."
    if calibration_status == "healthy":
        return "Calibration is validating well, so the recommendation can be acted on with light operator review."
    if calibration_status == "mixed":
        return "Calibration is mixed, so the recommendation is still useful but should be treated with operator judgment."
    if calibration_status == "noisy" and next_trust_policy == "verify-first":
        return "Calibration is noisy, so the recommendation was softened and should be verified before acting."
    return "Calibration is still lightly exercised, so use the recommendation as guidance rather than as hard proof."


def _accountability_summary(
    *,
    primary_target: dict,
    primary_target_reason: str,
    closure_guidance: str,
    chronic_item_count: int,
    newly_stale_count: int,
    quiet_streak_runs: int,
) -> str:
    if not primary_target:
        if quiet_streak_runs >= 2:
            return f"No active accountability target is open, and the queue has stayed quiet for {quiet_streak_runs} consecutive run(s)."
        return "No active accountability target is open right now."
    return (
        f"{primary_target_reason} {closure_guidance} "
        f"Aging pressure: {chronic_item_count} chronic item(s) and {newly_stale_count} newly stale item(s)."
    ).strip()


def _trend_status(
    *,
    current_attention_count: int,
    previous_attention_count: int,
    new_blocked_attention: bool,
    quiet_streak_runs: int,
    has_previous: bool,
) -> str:
    if current_attention_count == 0 and quiet_streak_runs >= 2:
        return "quiet"
    if not has_previous:
        return "stable"
    if new_blocked_attention or current_attention_count > previous_attention_count:
        return "worsening"
    if current_attention_count < previous_attention_count or (
        current_attention_count == 0 and previous_attention_count > 0
    ):
        return "improving"
    return "stable"


def _trend_summary(
    *,
    trend_status: str,
    quiet_streak_runs: int,
    new_attention_count: int,
    resolved_attention_count: int,
    persisting_attention_count: int,
    reopened_attention_count: int,
    primary_target: dict,
) -> str:
    repo = f"{primary_target.get('repo')}: " if primary_target.get("repo") else ""
    target_label = f"{repo}{primary_target.get('title', '')}".strip(": ")
    if trend_status == "quiet":
        return f"The queue is quiet and has stayed that way for {quiet_streak_runs} consecutive run(s)."
    if trend_status == "worsening":
        target_text = f" Focus first on {target_label}." if target_label else ""
        return (
            f"The operator picture is worsening: {new_attention_count} new attention item(s) appeared, "
            f"{persisting_attention_count} still remain open, and {reopened_attention_count} reopened inside the recent window."
            f"{target_text}"
        )
    if trend_status == "improving":
        target_text = f" Remaining focus: {target_label}." if target_label else ""
        return (
            f"The operator picture is improving: {resolved_attention_count} attention item(s) cleared since the last run, "
            f"and {persisting_attention_count} still remain open."
            f"{target_text}"
        )
    if persisting_attention_count:
        target_text = f" Close {target_label} next." if target_label else ""
        return (
            f"The queue is stable but still sticky: {persisting_attention_count} attention item(s) are persisting from the last run."
            f"{target_text}"
        )
    return "The queue changed only lightly since the last run, with no clear worsening or recovery trend."


def _queue_identity(item: dict) -> str:
    if item.get("item_id"):
        return item["item_id"]
    repo = item.get("repo", "")
    title = item.get("title", "")
    return f"{repo}:{title}"


def _follow_through_summary(
    repeat_urgent_count: int,
    stale_item_count: int,
    oldest_open_item_days: int,
    quiet_streak_runs: int,
) -> str:
    if repeat_urgent_count or stale_item_count:
        return (
            f"{repeat_urgent_count} urgent item(s) repeated in the recent window, "
            f"{stale_item_count} open item(s) now look stale, and the oldest open item has been visible for about {oldest_open_item_days} day(s)."
        )
    if quiet_streak_runs >= 2:
        return f"The operator queue has stayed quiet for {quiet_streak_runs} consecutive run(s)."
    if quiet_streak_runs == 1:
        return "The latest run is quiet, but the recent window has not stayed quiet long enough to count as a streak yet."
    return "This is the first noisy run in the recent window, so follow-through pressure is still fresh."


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


def _summarize_operator_change(top_item: dict, recent_changes: list[dict], resolution_trend: dict) -> str:
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
    if top_item and trend_status == "stable" and resolution_trend.get("persisting_attention_count", 0):
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
        subject = change.get("repo") or change.get("repo_full_name") or change.get("item_id") or "portfolio"
        detail = change.get("summary", change.get("kind", "operator change"))
        return f"{subject}: {detail}"
    return QUIET_HANDOFF


def _next_operator_action(top_item: dict, watch_guidance: dict, follow_through: dict, resolution_trend: dict) -> str:
    if top_item.get("kind") == "setup" and top_item.get("recommended_action"):
        return top_item["recommended_action"]
    if resolution_trend.get("trend_status") == "quiet":
        return f"Keep the operator loop light and only escalate if the next run breaks the {resolution_trend.get('quiet_streak_runs', 0)}-run quiet streak."
    if resolution_trend.get("decision_memory_status") == "reopened" and top_item.get("closure_guidance"):
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
        return "Run the next full audit to refresh the baseline before relying on incremental results."
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
    calibration_status = confidence_calibration.get("confidence_validation_status", "insufficient-data")
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
        resolution_trend.get("primary_target_closure_forecast_freshness_status", "insufficient-data"),
        resolution_trend.get("primary_target_closure_forecast_decay_status", "none"),
        resolution_trend.get("primary_target_closure_forecast_refresh_recovery_status", "none"),
        resolution_trend.get("primary_target_closure_forecast_reacquisition_status", "none"),
        resolution_trend.get("primary_target_closure_forecast_reacquisition_reason", ""),
        resolution_trend.get("primary_target_closure_forecast_reacquisition_persistence_status", "none"),
        resolution_trend.get("primary_target_closure_forecast_reacquisition_persistence_reason", ""),
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
        if resolution_trend.get("trend_status") == "stable" and resolution_trend.get("persisting_attention_count", 0):
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
        return f"Trust policy: keep the weaker class posture because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: keep the weaker class posture because local target instability is preventing restored confirmation-side forecasting from holding."
    if closure_forecast_reacquisition_persistence_status == "sustained-confirmation":
        detail = closure_forecast_reacquisition_persistence_reason or closure_forecast_reacquisition_reason or reason
        return f"Trust policy: keep the restored confirmation posture because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: keep the restored confirmation posture because fresh confirmation-side reacquisition has now held long enough to trust."
    if closure_forecast_reacquisition_persistence_status == "sustained-clearance":
        detail = closure_forecast_reacquisition_persistence_reason or closure_forecast_reacquisition_reason or reason
        return f"Trust policy: keep the restored clearance posture because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: keep the restored clearance posture because fresh clearance-side reacquisition has now held long enough to trust."
    if closure_forecast_reacquisition_persistence_status in {"holding-confirmation", "holding-clearance"}:
        detail = closure_forecast_reacquisition_persistence_reason or closure_forecast_reacquisition_reason or reason
        return f"Trust policy: keep the restored posture for now because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: keep the restored posture for now because fresh reacquisition is holding and has not started churning."
    if closure_forecast_reacquisition_persistence_status == "just-reacquired":
        detail = closure_forecast_reacquisition_persistence_reason or closure_forecast_reacquisition_reason or reason
        return f"Trust policy: keep the restored posture visible for now because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: keep the restored posture visible for now because it has only just been reacquired and still looks fragile."
    if closure_forecast_reacquisition_persistence_status == "reversing" or closure_forecast_recovery_churn_status == "churn":
        detail = closure_forecast_recovery_churn_reason or closure_forecast_reacquisition_persistence_reason or reason
        return f"Trust policy: soften the restored posture again because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: soften the restored posture again because recovery is already wobbling too much to trust."
    if closure_forecast_recovery_churn_status == "watch":
        detail = closure_forecast_recovery_churn_reason or closure_forecast_reacquisition_persistence_reason or reason
        return f"Trust policy: keep the restored posture cautious because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: keep the restored posture cautious because recovery is wobbling and still needs follow-through."
    if closure_forecast_reacquisition_status == "reacquired-confirmation":
        detail = closure_forecast_reacquisition_reason or reason
        return f"Trust policy: keep the weaker class posture for now because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: keep the weaker class posture for now because stronger confirmation forecasting was re-earned safely."
    if closure_forecast_reacquisition_status == "reacquired-clearance":
        detail = closure_forecast_reacquisition_reason or reason
        return f"Trust policy: keep the weaker class posture because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: keep the weaker class posture because stronger clearance forecasting was re-earned safely."
    if closure_forecast_reacquisition_status == "pending-confirmation-reacquisition":
        detail = closure_forecast_reacquisition_reason or reason
        return f"Trust policy: keep the weaker class posture for now because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: keep the weaker class posture for now because confirmation-side recovery is visible, but stronger carry-forward has not been fully re-earned yet."
    if closure_forecast_reacquisition_status == "pending-clearance-reacquisition":
        detail = closure_forecast_reacquisition_reason or reason
        return f"Trust policy: keep the weaker class posture because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: keep the weaker class posture because clearance-side recovery is visible, but stronger carry-forward has not been fully re-earned yet."
    if closure_forecast_reacquisition_status == "blocked":
        detail = closure_forecast_reacquisition_reason or reason
        return f"Trust policy: keep the weaker class posture because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: keep the weaker class posture because local target instability is still preventing positive confirmation-side reacquisition."
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
        return f"Trust policy: keep the stronger class posture because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: keep the stronger class posture because the earlier pending class signal finally confirmed."
    if class_transition_resolution_status == "cleared":
        detail = class_transition_resolution_reason or reason
        return f"Trust policy: keep the weaker class posture because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: keep the weaker class posture because the earlier pending class signal faded before confirmation."
    if class_transition_resolution_status == "expired":
        detail = class_transition_resolution_reason or reason
        return f"Trust policy: keep the weaker class posture because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: keep the weaker class posture because the earlier pending class signal aged out."
    if class_transition_resolution_status == "blocked":
        detail = class_transition_resolution_reason or class_transition_health_reason or reason
        return f"Trust policy: keep the weaker class posture because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: keep the weaker class posture because local target instability is blocking a pending class transition."
    if class_transition_health_status == "stalled":
        detail = class_transition_health_reason or reason
        return f"Trust policy: keep the weaker class posture because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: keep the weaker class posture because the pending class signal has stalled."
    if class_transition_health_status == "holding":
        detail = class_transition_health_reason or reason
        return f"Trust policy: keep the weaker class posture because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: keep the weaker class posture because the pending class signal is holding but not strengthening."
    if class_transition_health_status == "building":
        return "Trust policy: keep the weaker class posture for now because the pending class signal is still building and has not confirmed yet."
    if class_transition_health_status == "expired":
        detail = class_transition_health_reason or reason
        return f"Trust policy: keep the weaker class posture because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: keep the weaker class posture because the earlier pending class signal expired."
    if class_transition_health_status == "blocked":
        detail = class_transition_health_reason or reason
        return f"Trust policy: keep the weaker class posture because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: keep the weaker class posture because local target instability is blocking a pending class transition."
    if closure_forecast_reweight_effect == "clear-risk-strengthened":
        detail = closure_forecast_reweight_effect_reason or reason
        return f"Trust policy: keep the weaker class posture because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: keep the weaker class posture because fresh pending debt is pushing the class signal toward clearance risk."
    if closure_forecast_reweight_effect == "confirm-support-softened":
        detail = closure_forecast_reweight_effect_reason or pending_debt_freshness_reason or reason
        return f"Trust policy: keep the weaker class posture because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: keep the weaker class posture because the pending forecast is aging and cannot support stronger confirmation from scratch."
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
        return f"Trust policy: act with review because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: act with review because fresh class support crossed the reweight threshold."
    if class_trust_reweight_effect == "normalization-softened":
        detail = class_trust_reweight_effect_reason or reason
        return f"Trust policy: verify first because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: verify first because class normalization weakened after reweighting."
    if class_trust_reweight_effect == "policy-debt-strengthened":
        detail = class_trust_reweight_effect_reason or policy_debt_reason or reason
        return f"Trust policy: verify first because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: verify first because fresh class caution is still heavy enough to matter."
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
        return f"Trust policy: keep the weaker class posture for now because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: keep the weaker class posture for now because fresh pending-resolution evidence is strengthening the forecast without confirming it yet."
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
        return f"Trust policy: verify first because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: verify first because stale class memory pulled back class-level normalization."
    if class_decay_status == "policy-debt-decayed":
        return "Trust policy: verify first for now, but earlier sticky class caution is starting to age out."
    if class_decay_status == "blocked":
        detail = class_decay_reason or class_memory_freshness_reason or class_normalization_reason or policy_debt_reason or reason
        return f"Trust policy: verify first because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: verify first because local target noise still overrides class freshness."
    if class_memory_freshness_status == "stale":
        detail = class_memory_freshness_reason or reason
        return f"Trust policy: verify first because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: verify first because older class evidence is being down-weighted."
    if class_memory_freshness_status == "mixed-age":
        return "Trust policy: verify first because class memory is still useful, but part of the class signal is aging out."
    if pending_debt_freshness_status == "stale":
        detail = pending_debt_freshness_reason or reason
        return f"Trust policy: verify first because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: verify first because older pending-debt patterns are being down-weighted."
    if pending_debt_freshness_status == "mixed-age":
        return "Trust policy: verify first because recent pending-transition evidence is still useful, but part of the pending-debt signal is aging out."
    if class_normalization_status == "applied":
        return "Trust policy: act with review because this class has repeatedly earned clean retirement and the current target can inherit a stronger posture."
    if class_normalization_status == "candidate":
        return "Trust policy: verify first for now because the class is improving, but the current target has not earned class-level normalization yet."
    if class_normalization_status == "blocked":
        detail = class_normalization_reason or policy_debt_reason or exception_retirement_reason or trust_recovery_reason or exception_reason or reason
        return f"Trust policy: verify first because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: verify first because class-level normalization is still blocked."
    if policy_debt_status == "class-debt":
        detail = policy_debt_reason or reason
        return f"Trust policy: verify first because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: verify first because this class still carries sticky caution."
    if policy_debt_status == "one-off-noise":
        detail = policy_debt_reason or reason
        return f"Trust policy: verify first because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: verify first because this target is noisier than its broader class."
    if exception_retirement_status == "retired":
        return "Trust policy: the earlier soft caution has now been formally retired, so the stronger live policy is back in place."
    if exception_retirement_status == "candidate":
        return "Trust policy: keep the current posture for now because the target is trending toward retirement, but it has not earned it yet."
    if exception_retirement_status == "blocked":
        detail = exception_retirement_reason or trust_recovery_reason or exception_reason or reason
        return f"Trust policy: keep caution in place because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: keep caution in place because exception retirement is still blocked."
    if trust_recovery_status == "earned":
        return "Trust policy: act with review because recent stability has earned this target back from verify-first."
    if trust_recovery_status == "candidate":
        return "Trust policy: verify first because the target is stabilizing, but it has not held steady long enough to earn stronger trust yet."
    if trust_recovery_status == "blocked":
        detail = trust_recovery_reason or exception_reason or reason
        return f"Trust policy: verify first because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: verify first because trust recovery is still blocked."
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
        return f"Trust policy: verify first because {detail[0].lower() + detail[1:]}" if detail else "Trust policy: verify first because recent signal quality is softer."
    return f"Trust policy: monitor because {reason[0].lower() + reason[1:]}" if reason else "Trust policy: monitor because no strong closure move is supported yet."


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
        return f"{summary} Trust policy: class normalization stayed visible, but its support weakened."
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
    status = resolution_trend.get("primary_target_class_memory_freshness_status", "insufficient-data")
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
    status = resolution_trend.get("primary_target_pending_debt_freshness_status", "insufficient-data")
    summary = resolution_trend.get("pending_debt_freshness_summary", "")
    if status in {None, ""} and not summary:
        return ""
    return f"Pending debt freshness: {status} — {summary}".strip()


def _closure_forecast_reweighting_note(resolution_trend: dict) -> str:
    direction = resolution_trend.get("primary_target_closure_forecast_reweight_direction", "neutral")
    summary = resolution_trend.get("closure_forecast_reweighting_summary", "")
    if direction in {None, ""} and not summary:
        return ""
    return f"Closure forecast reweighting: {direction} — {summary}".strip()


def _closure_forecast_freshness_note(resolution_trend: dict) -> str:
    status = resolution_trend.get("primary_target_closure_forecast_freshness_status", "insufficient-data")
    summary = resolution_trend.get("closure_forecast_freshness_summary", "")
    if status in {None, ""} and not summary:
        return ""
    return f"Closure forecast freshness: {status} — {summary}".strip()


def _closure_forecast_momentum_note(resolution_trend: dict) -> str:
    status = resolution_trend.get("primary_target_closure_forecast_momentum_status", "insufficient-data")
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
    status = resolution_trend.get("primary_target_closure_forecast_reacquisition_persistence_status", "none")
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
    status = resolution_trend.get("primary_target_closure_forecast_reset_refresh_recovery_status", "none")
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


def _lane_reason(lane: str, kind: str) -> str:
    if lane == "blocked":
        return "This item cannot move forward safely until the blocker is cleared."
    if lane == "urgent":
        return "This item shows live drift, high-severity change, or rollback exposure."
    if lane == "ready":
        if kind == "review":
            return "This item is actionable now and ready for a human decision."
        return "This item is ready for manual preview, approval, or apply review."
    return "This item is explicitly safe to defer for now."


def _repo_name(payload: dict) -> str:
    repo = payload.get("repo") or payload.get("repo_name")
    if repo:
        return repo
    full_name = payload.get("repo_full_name", "")
    return full_name.split("/")[-1] if full_name else ""


def _repo_or_portfolio(payload: dict) -> str:
    return payload.get("repo", "") or "portfolio"


def _links_from_payload(payload: dict) -> list[dict]:
    links: list[dict] = []
    for key in ("url", "html_url"):
        if payload.get(key):
            links.append({"label": key, "url": payload[key]})
    return links


def _age_days_from_run_id(source_run_id: str) -> int:
    if not source_run_id or ":" not in source_run_id:
        return 0
    timestamp = source_run_id.split(":", 1)[1]
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0, (datetime.now(timezone.utc) - dt).days)


def _dedupe_queue(queue: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen: set[str] = set()
    for item in queue:
        if item["item_id"] in seen:
            continue
        seen.add(item["item_id"])
        deduped.append(item)
    return deduped
