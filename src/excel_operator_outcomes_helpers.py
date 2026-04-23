"""Helpers for Operator Outcomes workbook content."""

from __future__ import annotations

from typing import Any

OPERATOR_OUTCOMES_METRIC_HEADERS = [
    "Metric",
    "Status",
    "Value",
    "Numerator",
    "Denominator",
    "Summary",
]
OPERATOR_OUTCOMES_MONITORING_HEADERS = [
    "Campaign",
    "State",
    "Pressure Effect",
    "Drift",
    "Reopen",
    "Summary",
]
OPERATOR_OUTCOMES_HISTORY_HEADERS = ["Run", "Generated", "Blocked", "Urgent", "High Pressure"]


def build_operator_outcomes_content(
    data: dict[str, Any],
    *,
    join_outcome_examples,
) -> dict[str, Any]:
    portfolio_outcomes = data.get("portfolio_outcomes_summary") or {}
    operator_effectiveness = data.get("operator_effectiveness_summary") or {}
    operator_summary = data.get("operator_summary") or {}

    summaries = [
        portfolio_outcomes.get(
            "summary",
            "Not enough operator history is recorded yet to judge outcomes.",
        ),
        operator_effectiveness.get(
            "summary",
            "Not enough judged recommendation history is recorded yet to judge operator effectiveness.",
        ),
        operator_summary.get(
            "high_pressure_queue_trend_summary",
            "High-pressure queue trend is not ready yet.",
        ),
        (data.get("campaign_outcomes_summary") or {}).get(
            "summary",
            "No recent Action Sync apply needs post-apply monitoring yet, so the local weekly story can stay local.",
        ),
        (data.get("next_monitoring_step") or {}).get(
            "summary",
            "Stay local for now; no recent Action Sync apply needs post-apply follow-up yet.",
        ),
        (data.get("campaign_tuning_summary") or {}).get(
            "summary",
            "Campaign tuning is neutral because there is not enough outcome history yet to bias tied recommendations.",
        ),
        (data.get("next_tuned_campaign") or {}).get(
            "summary",
            "No current campaign needs a tuning tie-break yet.",
        ),
        (data.get("automation_guidance_summary") or {}).get(
            "summary",
            "Automation guidance stays quiet until a campaign has a clearly safe preview, follow-up, or manual-only posture.",
        ),
        (data.get("next_safe_automation_step") or {}).get(
            "summary",
            "Stay local for now; no current campaign has a stronger safe automation posture than manual review.",
        ),
        (data.get("approval_workflow_summary") or {}).get(
            "summary",
            "No current approval needs review yet, so the approval workflow can stay local for now.",
        ),
        (data.get("next_approval_review") or {}).get(
            "summary",
            "Stay local for now; no current approval needs review.",
        ),
    ]

    metric_sources = [
        (
            "Review To Action Closure Rate",
            portfolio_outcomes.get("review_to_action_closure_rate", {}),
        ),
        (
            "Median Runs To Quiet After Escalation",
            portfolio_outcomes.get("median_runs_to_quiet_after_escalation", {}),
        ),
        (
            "Repeated Regression Rate",
            portfolio_outcomes.get("repeated_regression_rate", {}),
        ),
        (
            "Recommendation Validation Rate",
            operator_effectiveness.get("recommendation_validation_rate", {}),
        ),
        (
            "Noisy Guidance Rate",
            operator_effectiveness.get("noisy_guidance_rate", {}),
        ),
    ]
    metrics: list[list[Any]] = []
    for label, metric in metric_sources:
        value = metric.get("value")
        display_value = round(value, 3) if isinstance(value, float) else value
        metrics.append(
            [
                label,
                metric.get("status", "insufficient-evidence"),
                display_value if display_value is not None else "",
                metric.get("numerator", metric.get("episodes", "")),
                metric.get("denominator", ""),
                metric.get("summary", ""),
            ]
        )

    monitoring_rows = [
        [
            item.get("label", item.get("campaign_type", "Campaign")),
            item.get("monitoring_state", "no-recent-apply"),
            item.get("pressure_effect", "insufficient-evidence"),
            item.get("drift_state", "insufficient-evidence"),
            item.get("reopen_state", "insufficient-evidence"),
            item.get("summary", ""),
        ]
        for item in (data.get("action_sync_outcomes", []) or [])
    ]

    examples = [
        (
            "Closed Actions",
            join_outcome_examples(operator_summary.get("recent_closed_actions", [])),
        ),
        (
            "Reopened Recommendations",
            join_outcome_examples(
                operator_summary.get("recent_reopened_recommendations", [])
            ),
        ),
        (
            "Regression Examples",
            join_outcome_examples(operator_summary.get("recent_regression_examples", [])),
        ),
    ]

    history = [
        [
            item.get("run_id", ""),
            item.get("generated_at", ""),
            item.get("blocked_count", 0),
            item.get("urgent_count", 0),
            item.get("high_pressure_count", 0),
        ]
        for item in (data.get("high_pressure_queue_history", []) or [])
    ]

    return {
        "summaries": summaries,
        "metrics": metrics,
        "monitoring_rows": monitoring_rows,
        "examples": examples,
        "history": history,
    }


def write_operator_outcomes_sections(
    ws,
    content: dict[str, Any],
    *,
    section_font,
    wrap_alignment,
    style_header_row,
    style_data_cell,
) -> int:
    ws.merge_cells("A1:F1")
    ws["A1"].value = "Operator Outcomes"
    ws["A1"].font = section_font
    for row, summary in enumerate(content["summaries"], start=2):
        ws.merge_cells(f"A{row}:F{row}")
        ws[f"A{row}"].value = summary
        ws[f"A{row}"].alignment = wrap_alignment

    metric_row = 14
    for col, header in enumerate(OPERATOR_OUTCOMES_METRIC_HEADERS, 1):
        ws.cell(row=metric_row, column=col, value=header)
    style_header_row(ws, metric_row, len(OPERATOR_OUTCOMES_METRIC_HEADERS))
    ws.freeze_panes = "A15"

    for row, values in enumerate(content["metrics"], metric_row + 1):
        for col, item in enumerate(values, 1):
            cell = ws.cell(row=row, column=col, value=item)
            style_data_cell(cell, "center" if col in {2, 3, 4, 5} else "left")

    monitoring_row = 22
    ws.cell(row=monitoring_row, column=1, value="Post-Apply Monitoring")
    style_header_row(ws, monitoring_row, len(OPERATOR_OUTCOMES_MONITORING_HEADERS))
    for col, header in enumerate(OPERATOR_OUTCOMES_MONITORING_HEADERS, 1):
        ws.cell(row=monitoring_row + 1, column=col, value=header)
    style_header_row(ws, monitoring_row + 1, len(OPERATOR_OUTCOMES_MONITORING_HEADERS))
    for row, values in enumerate(content["monitoring_rows"], monitoring_row + 2):
        for col, value in enumerate(values, 1):
            cell = ws.cell(row=row, column=col, value=value)
            style_data_cell(cell, "center" if col in {2, 3, 4, 5} else "left")

    example_row = monitoring_row + 8
    ws.cell(row=example_row, column=1, value="Recent Examples")
    style_header_row(ws, example_row, 3)
    for offset, (label, value) in enumerate(content["examples"], start=1):
        ws.cell(row=example_row + offset, column=1, value=label)
        ws.cell(row=example_row + offset, column=2, value=value)

    history_row = example_row + 6
    for col, header in enumerate(OPERATOR_OUTCOMES_HISTORY_HEADERS, 1):
        ws.cell(row=history_row, column=col, value=header)
    style_header_row(ws, history_row, len(OPERATOR_OUTCOMES_HISTORY_HEADERS))
    for row, values in enumerate(content["history"], history_row + 1):
        for col, value in enumerate(values, 1):
            cell = ws.cell(row=row, column=col, value=value)
            style_data_cell(cell, "center" if col >= 3 else "left")

    return max(history_row + len(content["history"]), example_row + 3, monitoring_row + 3, 15)
