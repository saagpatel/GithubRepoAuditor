from __future__ import annotations

import json
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
    if summary.get("recommendation_drift_status"):
        lines.append(
            f"*Recommendation Drift:* {summary.get('recommendation_drift_status')} — "
            f"{summary.get('recommendation_drift_summary', 'No recommendation-drift summary is recorded yet.')}"
        )
    if summary.get("exception_pattern_summary"):
        lines.append(f"*Exception Pattern Summary:* {summary['exception_pattern_summary']}")
    if summary.get("exception_retirement_summary"):
        lines.append(f"*Exception Retirement Summary:* {summary['exception_retirement_summary']}")
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
    recovery_confidence_label = primary_target.get("recovery_confidence_label", "low")
    drift_status = primary_target.get("recommendation_drift_status", "")
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
) -> str:
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
) -> str:
    if not summary:
        return summary
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
