from __future__ import annotations

from src.terminology import ACTION_SYNC_CANONICAL_LABELS

LANE_LABELS = {
    "blocked": "Blocked",
    "urgent": "Needs Attention Now",
    "ready": "Ready for Manual Action",
    "deferred": "Safe to Defer",
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
    if (summary.get("action_sync_summary") or {}).get("summary"):
        lines.append(
            f"*{ACTION_SYNC_CANONICAL_LABELS['readiness']}:* {(summary.get('action_sync_summary') or {}).get('summary')}"
        )
    if summary.get("next_action_sync_step"):
        lines.append(f"*Next Action Sync Step:* {summary['next_action_sync_step']}")
    if (summary.get("apply_readiness_summary") or {}).get("summary"):
        lines.append(
            f"*{ACTION_SYNC_CANONICAL_LABELS['apply_packet']}:* {(summary.get('apply_readiness_summary') or {}).get('summary')}"
        )
    if (summary.get("next_apply_candidate") or {}).get("summary"):
        lines.append(
            f"*Next Apply Candidate:* {(summary.get('next_apply_candidate') or {}).get('summary')}"
        )
    if (summary.get("next_apply_candidate") or {}).get("preview_command") or (
        summary.get("next_apply_candidate") or {}
    ).get("apply_command"):
        command_hint = (summary.get("next_apply_candidate") or {}).get("apply_command") or (
            summary.get("next_apply_candidate") or {}
        ).get("preview_command")
        lines.append(f"*Action Sync Command Hint:* `{command_hint}`")
    if (summary.get("campaign_outcomes_summary") or {}).get("summary"):
        lines.append(
            f"*{ACTION_SYNC_CANONICAL_LABELS['post_apply_monitoring']}:* {(summary.get('campaign_outcomes_summary') or {}).get('summary')}"
        )
    if (summary.get("next_monitoring_step") or {}).get("summary"):
        lines.append(
            f"*Next Monitoring Step:* {(summary.get('next_monitoring_step') or {}).get('summary')}"
        )
    if (summary.get("campaign_tuning_summary") or {}).get("summary"):
        lines.append(
            f"*{ACTION_SYNC_CANONICAL_LABELS['campaign_tuning']}:* {(summary.get('campaign_tuning_summary') or {}).get('summary')}"
        )
    if (summary.get("next_tuned_campaign") or {}).get("summary"):
        lines.append(
            f"*{ACTION_SYNC_CANONICAL_LABELS['next_tie_break_candidate']}:* {(summary.get('next_tuned_campaign') or {}).get('summary')}"
        )
    if (summary.get("intervention_ledger_summary") or {}).get("summary"):
        lines.append(
            f"*{ACTION_SYNC_CANONICAL_LABELS['historical_portfolio_intelligence']}:* {(summary.get('intervention_ledger_summary') or {}).get('summary')}"
        )
    if (summary.get("next_historical_focus") or {}).get("summary"):
        lines.append(
            f"*Next Historical Focus:* {(summary.get('next_historical_focus') or {}).get('summary')}"
        )
    if (summary.get("automation_guidance_summary") or {}).get("summary"):
        lines.append(
            f"*{ACTION_SYNC_CANONICAL_LABELS['automation_guidance']}:* {(summary.get('automation_guidance_summary') or {}).get('summary')}"
        )
    if (summary.get("next_safe_automation_step") or {}).get("summary"):
        lines.append(
            f"*Next Safe Automation Step:* {(summary.get('next_safe_automation_step') or {}).get('summary')}"
        )
    if (summary.get("next_safe_automation_step") or {}).get("recommended_command"):
        lines.append(
            f"*Safe Automation Command:* `{(summary.get('next_safe_automation_step') or {}).get('recommended_command')}`"
        )
    if (summary.get("approval_workflow_summary") or {}).get("summary"):
        lines.append(
            f"*{ACTION_SYNC_CANONICAL_LABELS['approval_workflow']}:* {(summary.get('approval_workflow_summary') or {}).get('summary')}"
        )
    if (summary.get("next_approval_review") or {}).get("summary"):
        lines.append(
            f"*{ACTION_SYNC_CANONICAL_LABELS['next_approval_review']}:* {(summary.get('next_approval_review') or {}).get('summary')}"
        )
    if summary.get("trend_summary"):
        lines.append(f"*Trend:* {summary['trend_summary']}")
    if summary.get("accountability_summary"):
        lines.append(f"*Accountability:* {summary['accountability_summary']}")
    if summary.get("follow_through_summary"):
        lines.append(f"*Follow-Through:* {summary['follow_through_summary']}")
    if summary.get("follow_through_recovery_summary"):
        lines.append(f"*Follow-Through Recovery:* {summary['follow_through_recovery_summary']}")
    if summary.get("follow_through_recovery_persistence_summary"):
        lines.append(
            f"*Recovery Persistence:* {summary['follow_through_recovery_persistence_summary']}"
        )
    if summary.get("follow_through_relapse_churn_summary"):
        lines.append(f"*Relapse Churn:* {summary['follow_through_relapse_churn_summary']}")
    if summary.get("follow_through_recovery_freshness_summary"):
        lines.append(
            f"*Recovery Freshness:* {summary['follow_through_recovery_freshness_summary']}"
        )
    if summary.get("follow_through_recovery_memory_reset_summary"):
        lines.append(
            f"*Recovery Memory Reset:* {summary['follow_through_recovery_memory_reset_summary']}"
        )
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
        lines.append(
            f"*Why This Confidence Is Actionable:* {summary['adaptive_confidence_summary']}"
        )
    if (
        summary.get("primary_target_exception_status")
        and summary.get("primary_target_exception_status") != "none"
    ):
        lines.append(
            f"*Trust Policy Exception:* {summary.get('primary_target_exception_status')} — "
            f"{summary.get('primary_target_exception_reason', 'No trust-policy exception reason is recorded yet.')}"
        )
    if (
        summary.get("primary_target_exception_pattern_status")
        and summary.get("primary_target_exception_pattern_status") != "none"
    ):
        lines.append(
            f"*Exception Pattern Learning:* {summary.get('primary_target_exception_pattern_status')} — "
            f"{summary.get('primary_target_exception_pattern_reason', 'No exception-pattern reason is recorded yet.')}"
        )
    if (
        summary.get("primary_target_trust_recovery_status")
        and summary.get("primary_target_trust_recovery_status") != "none"
    ):
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
    if (
        summary.get("primary_target_exception_retirement_status")
        and summary.get("primary_target_exception_retirement_status") != "none"
    ):
        lines.append(
            f"*Exception Retirement:* {summary.get('primary_target_exception_retirement_status')} — "
            f"{summary.get('primary_target_exception_retirement_reason', 'No exception-retirement reason is recorded yet.')}"
        )
    if (
        summary.get("primary_target_policy_debt_status")
        and summary.get("primary_target_policy_debt_status") != "none"
    ):
        lines.append(
            f"*Policy Debt Cleanup:* {summary.get('primary_target_policy_debt_status')} — "
            f"{summary.get('primary_target_policy_debt_reason', 'No policy-debt reason is recorded yet.')}"
        )
    if (
        summary.get("primary_target_class_normalization_status")
        and summary.get("primary_target_class_normalization_status") != "none"
    ):
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
        lines.append(
            f"*Reweighting Stability Summary:* {summary['class_reweight_stability_summary']}"
        )
    if summary.get("class_transition_health_summary"):
        lines.append(
            f"*Class Transition Health Summary:* {summary['class_transition_health_summary']}"
        )
    if summary.get("class_transition_resolution_summary"):
        lines.append(
            f"*Pending Transition Resolution Summary:* {summary['class_transition_resolution_summary']}"
        )
    if summary.get("transition_closure_confidence_summary"):
        lines.append(
            f"*Transition Closure Confidence Summary:* {summary['transition_closure_confidence_summary']}"
        )
    if summary.get("class_pending_debt_summary"):
        lines.append(f"*Class Pending Debt Summary:* {summary['class_pending_debt_summary']}")
    if summary.get("class_pending_resolution_summary"):
        lines.append(
            f"*Class Pending Resolution Summary:* {summary['class_pending_resolution_summary']}"
        )
    if summary.get("pending_debt_freshness_summary"):
        lines.append(
            f"*Pending Debt Freshness Summary:* {summary['pending_debt_freshness_summary']}"
        )
    if summary.get("pending_debt_decay_summary"):
        lines.append(f"*Pending Debt Decay Summary:* {summary['pending_debt_decay_summary']}")
    if summary.get("closure_forecast_reweighting_summary"):
        lines.append(
            f"*Closure Forecast Reweighting Summary:* {summary['closure_forecast_reweighting_summary']}"
        )
    if summary.get("recommendation_quality_summary"):
        lines.append(f"*Recommendation Quality:* {summary['recommendation_quality_summary']}")
    if summary.get("confidence_validation_status"):
        lines.append(
            f"*Confidence Validation:* {summary.get('confidence_validation_status')} — "
            f"{summary.get('confidence_calibration_summary', 'No confidence-calibration summary is recorded yet.')}"
        )
    recent_outcomes_line = _recent_validation_outcomes_line(
        summary.get("recent_validation_outcomes") or []
    )
    if recent_outcomes_line:
        lines.append(f"*Recent Confidence Outcomes:* {recent_outcomes_line}")
    if summary.get("portfolio_outcomes_summary"):
        lines.append(
            f"*Operator Outcomes:* {(summary.get('portfolio_outcomes_summary') or {}).get('summary', 'No operator outcomes summary is recorded yet.')}"
        )
    if summary.get("operator_effectiveness_summary"):
        lines.append(
            f"*Operator Effectiveness:* {(summary.get('operator_effectiveness_summary') or {}).get('summary', 'No operator effectiveness summary is recorded yet.')}"
        )
    if summary.get("high_pressure_queue_trend_status"):
        lines.append(
            f"*High-Pressure Queue Trend:* {summary.get('high_pressure_queue_trend_status')} — "
            f"{summary.get('high_pressure_queue_trend_summary', 'No high-pressure queue trend is recorded yet.')}"
        )
    if summary.get("recent_closed_actions"):
        lines.append(
            f"*Recent Closed Actions:* {_operator_outcome_examples_line(summary.get('recent_closed_actions') or [])}"
        )
    if summary.get("recent_reopened_recommendations"):
        lines.append(
            f"*Recent Reopened Recommendations:* {_operator_outcome_examples_line(summary.get('recent_reopened_recommendations') or [])}"
        )
    if summary.get("recent_regression_examples"):
        lines.append(
            f"*Recent Regression Examples:* {_operator_outcome_examples_line(summary.get('recent_regression_examples') or [])}"
        )
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
            lines.append(
                f"  Why this lane: {item.get('lane_reason', item.get('lane_label', LANE_LABELS.get(item['lane'], item['lane'])))}"
            )
            lines.append(f"  Action: {item['recommended_action']}")
            if item.get("catalog_line"):
                lines.append(f"  Catalog: {item['catalog_line']}")
            if item.get("operating_path_line"):
                lines.append(f"  {item['operating_path_line']}")
            if item.get("intent_alignment"):
                lines.append(
                    f"  Intent Alignment: {item.get('intent_alignment')} — "
                    f"{item.get('intent_alignment_reason', 'No alignment reason is recorded yet.')}"
                )
            if item.get("scorecard_line"):
                lines.append(f"  {item.get('scorecard_line')}")
            if item.get("maturity_gap_summary"):
                lines.append(f"  Maturity Gap: {item.get('maturity_gap_summary')}")
            if item.get("action_sync_line"):
                lines.append(f"  {item.get('action_sync_line')}")
            if item.get("apply_packet_line"):
                lines.append(f"  {item.get('apply_packet_line')}")
            if item.get("post_apply_line"):
                lines.append(f"  {item.get('post_apply_line')}")
            if item.get("campaign_tuning_line"):
                lines.append(f"  {item.get('campaign_tuning_line')}")
        lines.append("")
    recent_changes = snapshot.get("operator_recent_changes") or []
    if recent_changes:
        lines.append("## Recently Changed")
        lines.append("")
        for change in recent_changes[:6]:
            when = change.get("generated_at", "")[:10]
            subject = (
                change.get("repo")
                or change.get("repo_full_name")
                or change.get("item_id")
                or "portfolio"
            )
            lines.append(
                f"- {when}: {subject} — {change.get('summary', change.get('kind', 'Operator change'))}"
            )
        lines.append("")
    return "\n".join(lines).strip() + "\n"


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


def _operator_outcome_examples_line(items: list[dict]) -> str:
    if not items:
        return ""
    parts = []
    for item in items[:3]:
        repo = str(item.get("repo") or "").strip()
        title = str(item.get("title") or item.get("action_id") or "Operator outcome").strip()
        label = f"{repo}: {title}" if repo else title
        parts.append(label)
    return "; ".join(parts)
