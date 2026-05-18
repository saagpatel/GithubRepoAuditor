"""Operator-centric hidden-sheet row builders for the Excel workbook."""

from __future__ import annotations


def build_operator_hidden_rows(
    data: dict,
) -> tuple[
    list[list[object]],
    list[list[object]],
    list[list[object]],
    list[list[object]],
    list[list[object]],
    list[list[object]],
]:
    operator_outcome_rows: list[list[object]] = []
    action_sync_outcome_rows: list[list[object]] = []
    campaign_tuning_rows: list[list[object]] = []
    intervention_ledger_rows: list[list[object]] = []
    action_sync_automation_rows: list[list[object]] = []
    approval_ledger_rows: list[list[object]] = []

    portfolio_outcomes = data.get("portfolio_outcomes_summary", {}) or {}
    operator_effectiveness = data.get("operator_effectiveness_summary", {}) or {}
    operator_summary = data.get("operator_summary", {}) or {}

    for label, metric in (
        (
            "review_to_action_closure_rate",
            portfolio_outcomes.get("review_to_action_closure_rate", {}),
        ),
        (
            "median_runs_to_quiet_after_escalation",
            portfolio_outcomes.get("median_runs_to_quiet_after_escalation", {}),
        ),
        ("repeated_regression_rate", portfolio_outcomes.get("repeated_regression_rate", {})),
        (
            "recommendation_validation_rate",
            operator_effectiveness.get("recommendation_validation_rate", {}),
        ),
        ("noisy_guidance_rate", operator_effectiveness.get("noisy_guidance_rate", {})),
    ):
        operator_outcome_rows.append(
            [
                label,
                metric.get("status", "insufficient-evidence"),
                metric.get("value", ""),
                metric.get("numerator", metric.get("episodes", "")),
                metric.get("denominator", ""),
                metric.get("summary", ""),
            ]
        )
    for item in data.get("high_pressure_queue_history", []) or []:
        operator_outcome_rows.append(
            [
                "high_pressure_queue_history",
                operator_summary.get("high_pressure_queue_trend_status", ""),
                item.get("high_pressure_count", 0),
                item.get("blocked_count", 0),
                item.get("urgent_count", 0),
                item.get("generated_at", ""),
            ]
        )
    for label, items in (
        ("recent_closed_actions", operator_summary.get("recent_closed_actions", [])),
        (
            "recent_reopened_recommendations",
            operator_summary.get("recent_reopened_recommendations", []),
        ),
        ("recent_regression_examples", operator_summary.get("recent_regression_examples", [])),
    ):
        for item in items[:3]:
            operator_outcome_rows.append(
                [
                    label,
                    "example",
                    item.get("repo", ""),
                    item.get("title", ""),
                    item.get("action_id", ""),
                    item.get("summary", ""),
                ]
            )

    for item in data.get("action_sync_outcomes", []) or []:
        action_sync_outcome_rows.append(
            [
                item.get("campaign_type", ""),
                item.get("label", ""),
                item.get("latest_target", ""),
                item.get("latest_run_mode", ""),
                item.get("recent_apply_count", 0),
                item.get("monitored_repo_count", 0),
                item.get("monitoring_state", "no-recent-apply"),
                item.get("pressure_effect", "insufficient-evidence"),
                item.get("drift_state", "insufficient-evidence"),
                item.get("reopen_state", "insufficient-evidence"),
                item.get("rollback_state", "not-applicable"),
                item.get("follow_up_recommendation", ""),
                ", ".join(item.get("top_repos", []) or []),
                item.get("summary", ""),
            ]
        )

    for item in data.get("action_sync_tuning", []) or []:
        campaign_tuning_rows.append(
            [
                item.get("campaign_type", ""),
                item.get("label", ""),
                item.get("tuning_status", "insufficient-evidence"),
                item.get("recommendation_bias", "neutral"),
                item.get("judged_count", 0),
                item.get("monitor_now_count", 0),
                item.get("holding_clean_rate", 0.0),
                item.get("drift_return_rate", 0.0),
                item.get("reopen_rate", 0.0),
                item.get("rollback_watch_rate", 0.0),
                item.get("pressure_reduction_rate", 0.0),
                item.get("summary", ""),
            ]
        )

    for item in data.get("historical_portfolio_intelligence", []) or []:
        intervention_ledger_rows.append(
            [
                item.get("repo", ""),
                item.get("latest_tier", ""),
                item.get("latest_score", 0.0),
                item.get("recent_intervention_count", 0),
                item.get("last_intervention", ""),
                item.get("pressure_trend", "insufficient-evidence"),
                item.get("hotspot_persistence", "insufficient-evidence"),
                item.get("scorecard_trend", "insufficient-evidence"),
                item.get("campaign_follow_through", "insufficient-evidence"),
                item.get("historical_intelligence_status", "insufficient-evidence"),
                item.get("summary", ""),
            ]
        )

    for item in data.get("action_sync_automation", []) or []:
        action_sync_automation_rows.append(
            [
                item.get("campaign_type", ""),
                item.get("label", ""),
                item.get("automation_posture", "manual-only"),
                "yes" if item.get("review_required") else "no",
                "yes" if item.get("requires_approval") else "no",
                item.get("recommended_command", ""),
                item.get("recommended_follow_up", ""),
                item.get("summary", ""),
            ]
        )

    for item in data.get("approval_ledger", []) or []:
        approval_ledger_rows.append(
            [
                item.get("approval_id", ""),
                item.get("approval_subject_type", ""),
                item.get("subject_key", ""),
                item.get("label", ""),
                item.get("approval_state", "not-applicable"),
                item.get("follow_up_state", "not-applicable"),
                item.get("source_run_id", ""),
                item.get("fingerprint", ""),
                item.get("approved_at", ""),
                item.get("approved_by", ""),
                item.get("last_reviewed_at", ""),
                item.get("last_reviewed_by", ""),
                item.get("follow_up_cadence_days", 0),
                item.get("next_follow_up_due_at", ""),
                "yes" if item.get("stale_approval") else "no",
                "yes" if item.get("approval_ready") else "no",
                "yes" if item.get("apply_ready_after_approval") else "no",
                item.get("approval_command", ""),
                item.get("follow_up_command", ""),
                item.get("manual_apply_command", ""),
                item.get("summary", ""),
            ]
        )

    return (
        operator_outcome_rows,
        action_sync_outcome_rows,
        campaign_tuning_rows,
        intervention_ledger_rows,
        action_sync_automation_rows,
        approval_ledger_rows,
    )
