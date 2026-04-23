from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.baseline_context import build_watch_guidance
from src.governance_activation import build_governance_summary
from src.intervention_ledger import load_intervention_ledger_bundle
from src.operator_effectiveness import build_operator_effectiveness_bundle
from src.recurring_review import build_review_bundle
from src.warehouse import (
    load_operator_calibration_history,
    load_operator_state_history,
    load_recent_campaign_history,
    load_recent_operator_changes,
    load_recent_operator_evidence,
    load_review_history,
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
FOLLOW_THROUGH_RETIREMENT_WINDOW_RUNS = 3
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
CLASS_RESET_REENTRY_REBUILD_REFRESH_REENTRY_WINDOW_RUNS = 4
CLASS_RESET_REENTRY_REBUILD_REENTRY_WINDOW_RUNS = 4
CLASS_RESET_REENTRY_REBUILD_REENTRY_FRESHNESS_WINDOW_RUNS = 4
CLASS_RESET_REENTRY_REBUILD_REENTRY_REFRESH_RESTORE_WINDOW_RUNS = 4
CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_WINDOW_RUNS = 4
CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_FRESHNESS_WINDOW_RUNS = 4
CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_REFRESH_WINDOW_RUNS = 4
CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_RERESTORE_WINDOW_RUNS = 4
CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_RERESTORE_FRESHNESS_WINDOW_RUNS = 4
CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_RERESTORE_REFRESH_WINDOW_RUNS = 4
CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_RERERESTORE_WINDOW_RUNS = 4
CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_RERERESTORE_FRESHNESS_WINDOW_RUNS = 4
CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_RERERESTORE_REFRESH_WINDOW_RUNS = 4
CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_RERERERESTORE_WINDOW_RUNS = 4
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
        data["review_targets"] = [
            _normalize_review_target(item) for item in data.get("review_targets") or []
        ]
        data["review_history"] = [
            _normalize_review_history_item(item) for item in data.get("review_history") or []
        ]
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
    bundle["review_targets"] = [
        _normalize_review_target(item) for item in bundle.get("review_targets") or []
    ]
    bundle["review_history"] = [
        _normalize_review_history_item(item) for item in bundle.get("review_history") or []
    ]
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
    age_reference = _parse_report_datetime(report_data.get("generated_at")) or datetime.now(
        timezone.utc
    )
    preflight = report_data.get("preflight_summary") or {}
    review_summary = report_data.get("review_summary") or {}
    review_targets = report_data.get("review_targets") or []
    managed_state_drift = report_data.get("managed_state_drift") or []
    governance_drift = report_data.get("governance_drift") or []
    governance_preview = report_data.get("governance_preview") or {}
    governance_summary = report_data.get("governance_summary") or build_governance_summary(
        report_data
    )
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
                recommended_action=check.get(
                    "recommended_fix", "Resolve the setup blocker before the next run."
                ),
                source_run_id=review_summary.get("source_run_id", ""),
                age_reference=age_reference,
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
                summary=drift.get(
                    "drift_state", drift.get("drift_type", "Managed state drift detected.")
                ),
                recommended_action="Inspect the managed issue, topics, or custom properties before closing or applying more campaign work.",
                source_run_id=review_summary.get("source_run_id", ""),
                age_reference=age_reference,
                links=_links_from_payload(drift),
            )
        )

    for drift in governance_drift:
        lane = (
            "blocked"
            if drift.get("drift_type") in {"approval-invalidated", "requires-reapproval"}
            else "urgent"
        )
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
                age_reference=age_reference,
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
                summary=governance_summary.get(
                    "headline", "Governed controls need re-approval before any apply step."
                ),
                recommended_action="Review the governed controls and re-approve them before the next manual apply step.",
                source_run_id=review_summary.get("source_run_id", ""),
                age_reference=age_reference,
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
                recommended_action=change.get(
                    "recommended_next_step", "Review the repo before reprioritizing work."
                ),
                source_run_id=review_summary.get("source_run_id", ""),
                age_reference=age_reference,
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
                recommended_action=recommended
                or (
                    "Safe to defer."
                    if safe_to_defer
                    else "Inspect the latest changes and decide on next action."
                ),
                source_run_id=review_summary.get("source_run_id", ""),
                age_reference=age_reference,
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
                age_reference=age_reference,
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
                age_reference=age_reference,
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
                age_reference=age_reference,
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

    recent_changes = load_recent_operator_changes(
        output_dir, report_data.get("username", ""), limit=12
    )
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
    calibration_history = load_operator_calibration_history(
        output_dir,
        report_data.get("username", ""),
        limit=CALIBRATION_WINDOW_RUNS,
    )
    from src import operator_decision_quality as _operator_decision_quality
    from src import operator_follow_through as _operator_follow_through
    from src import operator_resolution_trend as _operator_resolution_trend
    from src import operator_snapshot_packaging as _operator_snapshot_packaging

    confidence_calibration = _operator_decision_quality.build_confidence_calibration(
        calibration_history
    )
    operator_effectiveness = build_operator_effectiveness_bundle(
        state_history=[
            _operator_resolution_trend._snapshot_from_queue(
                queue, generated_at=report_data.get("generated_at", "")
            )
        ]
        + history[: CALIBRATION_WINDOW_RUNS - 1],
        calibration_history=calibration_history,
        campaign_history=load_recent_campaign_history(
            output_dir,
            report_data.get("username", ""),
            limit=200,
        ),
        review_history=load_review_history(
            output_dir,
            report_data.get("username", ""),
            limit=CALIBRATION_WINDOW_RUNS,
        ),
        evidence_events=evidence_bundle.get("events") or [],
    )
    resolution_trend = _operator_resolution_trend._build_resolution_trend(
        queue,
        history,
        evidence_bundle.get("events") or [],
        confidence_calibration=confidence_calibration,
        current_generated_at=report_data.get("generated_at", ""),
    )
    queue = _operator_follow_through._project_queue_follow_through(
        queue,
        recent_runs=[
            _operator_resolution_trend._snapshot_from_queue(
                queue,
                generated_at=report_data.get("generated_at", ""),
            )
        ]
        + [
            _operator_resolution_trend._snapshot_from_history(entry)
            for entry in history[: HISTORY_WINDOW_RUNS - 1]
        ],
        resolution_trend=resolution_trend,
        current_generated_at=report_data.get("generated_at", ""),
    )
    queue = _operator_resolution_trend._attach_portfolio_catalog_context(queue, report_data)
    from src.action_sync_automation import build_action_sync_automation_bundle
    from src.action_sync_outcomes import load_action_sync_outcomes_bundle
    from src.action_sync_packets import build_action_sync_packets_bundle
    from src.action_sync_readiness import build_action_sync_readiness_bundle
    from src.action_sync_tuning import load_action_sync_tuning_bundle
    from src.approval_ledger import load_approval_ledger_bundle

    action_sync = build_action_sync_readiness_bundle(report_data, queue)
    action_sync_packets = build_action_sync_packets_bundle(
        report_data,
        action_sync,
        action_sync.get("operator_queue", queue),
    )
    queue = action_sync_packets.get("operator_queue", action_sync.get("operator_queue", queue))
    action_sync_outcomes = load_action_sync_outcomes_bundle(output_dir, report_data, queue)
    queue = action_sync_outcomes.get("operator_queue", queue)
    action_sync_tuning = load_action_sync_tuning_bundle(
        output_dir,
        report_data,
        action_sync,
        action_sync_packets,
        action_sync_outcomes,
        queue,
    )
    queue = action_sync_tuning.get("operator_queue", queue)
    intervention_ledger = load_intervention_ledger_bundle(output_dir, report_data, queue)
    queue = intervention_ledger.get("operator_queue", queue) or queue
    action_sync_automation = build_action_sync_automation_bundle(
        report_data,
        action_sync,
        action_sync_packets,
        action_sync_outcomes,
        action_sync_tuning,
        intervention_ledger,
        queue,
    )
    queue = action_sync_automation.get("operator_queue", queue) or queue
    approval_ledger = load_approval_ledger_bundle(output_dir, report_data, queue)
    queue = approval_ledger.get("operator_queue", queue) or queue
    follow_through = _operator_follow_through._build_follow_through_with_queue(
        resolution_trend, queue
    )
    raw_next_action = _operator_snapshot_packaging._next_operator_action(
        resolution_trend.get("primary_target") or (queue[0] if queue else {}),
        watch_guidance,
        follow_through,
        resolution_trend,
    )
    confidence = _operator_resolution_trend._operator_confidence_summary(
        resolution_trend.get("primary_target") or {},
        raw_next_action,
        watch_guidance,
        confidence_calibration,
    )
    decision_quality = _operator_decision_quality.build_decision_quality_v1(
        confidence_calibration=confidence_calibration,
        confidence=confidence,
        resolution_trend=resolution_trend,
        evidence_window_runs=CALIBRATION_WINDOW_RUNS,
        validation_window_runs=VALIDATION_WINDOW_RUNS,
    )
    handoff = _operator_snapshot_packaging._build_operator_handoff(
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
    summary = _operator_snapshot_packaging.build_operator_summary(
        triage_view=triage_view,
        review_summary=review_summary,
        report_data=report_data,
        setup_health=setup_health,
        recent_changes=recent_changes,
        watch_guidance=watch_guidance,
        handoff=handoff,
        follow_through=follow_through,
        resolution_trend=resolution_trend,
        confidence_calibration=confidence_calibration,
        confidence=confidence,
        decision_quality=decision_quality,
        operator_effectiveness=operator_effectiveness,
        action_sync=action_sync,
        action_sync_packets=action_sync_packets,
        action_sync_outcomes=action_sync_outcomes,
        action_sync_tuning=action_sync_tuning,
        intervention_ledger=intervention_ledger,
        action_sync_automation=action_sync_automation,
        approval_ledger=approval_ledger,
        queue=queue,
        counts=counts,
    )
    return {
        "operator_summary": summary,
        "operator_queue": queue,
        "operator_setup_health": setup_health,
        "operator_recent_changes": recent_changes,
        "portfolio_outcomes_summary": operator_effectiveness["portfolio_outcomes_summary"],
        "operator_effectiveness_summary": operator_effectiveness["operator_effectiveness_summary"],
        "high_pressure_queue_history": operator_effectiveness["high_pressure_queue_history"],
        "campaign_readiness_summary": action_sync["campaign_readiness_summary"],
        "action_sync_summary": action_sync["action_sync_summary"],
        "next_action_sync_step": action_sync_tuning["next_action_sync_step"],
        "action_sync_packets": action_sync_packets["action_sync_packets"],
        "apply_readiness_summary": action_sync_packets["apply_readiness_summary"],
        "next_apply_candidate": action_sync_tuning["next_apply_candidate"],
        "action_sync_outcomes": action_sync_outcomes["action_sync_outcomes"],
        "campaign_outcomes_summary": action_sync_outcomes["campaign_outcomes_summary"],
        "next_monitoring_step": action_sync_outcomes["next_monitoring_step"],
        "action_sync_tuning": action_sync_tuning["action_sync_tuning"],
        "campaign_tuning_summary": action_sync_tuning["campaign_tuning_summary"],
        "next_tuned_campaign": action_sync_tuning["next_tuned_campaign"],
        "top_ready_to_apply_packets": action_sync_tuning["top_ready_to_apply_packets"],
        "top_needs_approval_packets": action_sync_tuning["top_needs_approval_packets"],
        "top_review_drift_packets": action_sync_tuning["top_review_drift_packets"],
        "top_monitor_now_campaigns": action_sync_outcomes["top_monitor_now_campaigns"],
        "top_holding_clean_campaigns": action_sync_outcomes["top_holding_clean_campaigns"],
        "top_reopened_campaigns": action_sync_outcomes["top_reopened_campaigns"],
        "top_drift_returned_campaigns": action_sync_outcomes["top_drift_returned_campaigns"],
        "top_apply_ready_campaigns": action_sync_tuning["top_apply_ready_campaigns"],
        "top_preview_ready_campaigns": action_sync_tuning["top_preview_ready_campaigns"],
        "top_drift_review_campaigns": action_sync_tuning["top_drift_review_campaigns"],
        "top_blocked_campaigns": action_sync_tuning["top_blocked_campaigns"],
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


def render_control_center_markdown(snapshot: dict, username: str, generated_at: str) -> str:
    from src.operator_control_center_rendering import (
        render_control_center_markdown as _render_control_center_markdown,
    )

    return _render_control_center_markdown(snapshot, username, generated_at)


def control_center_artifact_payload(report_data: dict, snapshot: dict) -> dict:
    from src.operator_snapshot_packaging import (
        control_center_artifact_payload as _control_center_artifact_payload,
    )

    return _control_center_artifact_payload(report_data, snapshot)


def _has_normalized_review_state(report_data: dict) -> bool:
    return any(
        report_data.get(key)
        for key in (
            "review_summary",
            "review_alerts",
            "material_changes",
            "review_targets",
            "review_history",
        )
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
    age_reference: datetime | None = None,
    links: list[dict],
) -> dict:
    age_days = _age_days_from_run_id(source_run_id, age_reference=age_reference)
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
    normalized.setdefault(
        "decision_hint", "safe-to-defer" if "safe to defer" in next_step.lower() else "needs-review"
    )
    normalized.setdefault("safe_to_defer", "safe to defer" in next_step.lower())
    return normalized


def _normalize_review_history_item(item: dict) -> dict:
    normalized = dict(item)
    normalized.setdefault("status", "open")
    normalized.setdefault("decision_state", "needs-review")
    normalized.setdefault("sync_state", "local-only")
    normalized.setdefault("safe_to_defer", normalized.get("decision_state") == "safe-to-defer")
    return normalized


def _build_confidence_calibration(history: list[dict]) -> dict:
    from src import operator_decision_quality as _operator_decision_quality

    return _operator_decision_quality.build_confidence_calibration(history)


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


def _queue_identity(item: dict) -> str:
    if item.get("item_id"):
        return item["item_id"]
    repo = item.get("repo", "")
    title = item.get("title", "")
    return f"{repo}:{title}"


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
    return any(lane is not None and _lane_pressure(lane) < origin_pressure for lane in future_lanes)


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
    from src import operator_decision_quality as _operator_decision_quality

    return _operator_decision_quality.confidence_validation_status(
        judged_count=judged_count,
        high_confidence_hit_rate=high_confidence_hit_rate,
        reopened_recommendation_count=reopened_recommendation_count,
        reopened_high_count=reopened_high_count,
    )


def _confidence_calibration_summary(
    *,
    confidence_validation_status: str,
    high_confidence_hit_rate: float,
    medium_confidence_hit_rate: float,
    low_confidence_caution_rate: float,
    reopened_recommendation_count: int,
    judged_count: int,
) -> str:
    from src import operator_decision_quality as _operator_decision_quality

    return _operator_decision_quality.confidence_calibration_summary(
        confidence_validation_status=confidence_validation_status,
        high_confidence_hit_rate=high_confidence_hit_rate,
        medium_confidence_hit_rate=medium_confidence_hit_rate,
        low_confidence_caution_rate=low_confidence_caution_rate,
        reopened_recommendation_count=reopened_recommendation_count,
        judged_count=judged_count,
    )


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


def _parse_report_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _age_days_from_run_id(source_run_id: str, *, age_reference: datetime | None = None) -> int:
    if not source_run_id or ":" not in source_run_id:
        return 0
    timestamp = source_run_id.split(":", 1)[1]
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    reference = age_reference or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return max(0, (reference.astimezone(timezone.utc) - dt.astimezone(timezone.utc)).days)


def _dedupe_queue(queue: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen: set[str] = set()
    for item in queue:
        if item["item_id"] in seen:
            continue
        seen.add(item["item_id"])
        deduped.append(item)
    return deduped
