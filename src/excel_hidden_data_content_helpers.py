"""Helpers for hidden workbook data payload assembly."""

from __future__ import annotations

from typing import Any


def build_hidden_data_payload(
    *,
    data: dict[str, Any],
    trend_data: list[dict[str, Any]] | None,
    score_history: dict[str, list[float]] | None,
    diff_data: dict[str, Any] | None,
    build_repo_detail_rows,
    build_run_change_rows,
    build_workbook_rollups,
    build_operator_hidden_rows,
    build_core_hidden_rows,
    trend_history_window: int,
    tier_order: list[str],
) -> dict[str, Any]:
    repo_detail_rows, repo_dimension_rollup_rows, repo_history_rollup_rows = build_repo_detail_rows(
        data, score_history
    )
    run_change_rollup_rows, run_change_repo_rows = build_run_change_rows(data, diff_data)
    operator_queue_rows, operator_repo_rollups, material_rollups = build_workbook_rollups(data)
    (
        operator_outcome_rows,
        action_sync_outcome_rows,
        campaign_tuning_rows,
        intervention_ledger_rows,
        action_sync_automation_rows,
        approval_ledger_rows,
    ) = build_operator_hidden_rows(data)
    core_hidden_rows = build_core_hidden_rows(
        data,
        trend_data,
        score_history,
        trend_history_window=trend_history_window,
        tier_order=tier_order,
    )
    lookup_rows = list(core_hidden_rows["lookup_rows"])
    return {
        **core_hidden_rows,
        "operator_outcome_rows": operator_outcome_rows,
        "action_sync_outcome_rows": action_sync_outcome_rows,
        "campaign_tuning_rows": campaign_tuning_rows,
        "intervention_ledger_rows": intervention_ledger_rows,
        "action_sync_automation_rows": action_sync_automation_rows,
        "approval_ledger_rows": approval_ledger_rows,
        "operator_queue_rows": operator_queue_rows,
        "operator_repo_rollups": operator_repo_rollups,
        "material_rollups": material_rollups,
        "repo_detail_rows": repo_detail_rows,
        "repo_dimension_rollup_rows": repo_dimension_rollup_rows,
        "repo_history_rollup_rows": repo_history_rollup_rows,
        "run_change_rollup_rows": run_change_rollup_rows,
        "run_change_repo_rows": run_change_repo_rows,
        "lookup_rows": lookup_rows,
    }


def build_hidden_data_sheets(
    wb,
    *,
    data: dict[str, Any],
    trend_data: list[dict[str, Any]] | None,
    score_history: dict[str, list[float]] | None,
    diff_data: dict[str, Any] | None,
    build_hidden_data_payload_fn,
    write_hidden_data_tables,
    build_repo_detail_rows,
    build_run_change_rows,
    build_workbook_rollups,
    build_operator_hidden_rows,
    build_core_hidden_rows,
    trend_history_window: int,
    tier_order: list[str],
) -> None:
    payload = build_hidden_data_payload_fn(
        data=data,
        trend_data=trend_data,
        score_history=score_history,
        diff_data=diff_data,
        build_repo_detail_rows=build_repo_detail_rows,
        build_run_change_rows=build_run_change_rows,
        build_workbook_rollups=build_workbook_rollups,
        build_operator_hidden_rows=build_operator_hidden_rows,
        build_core_hidden_rows=build_core_hidden_rows,
        trend_history_window=trend_history_window,
        tier_order=tier_order,
    )
    write_hidden_data_tables(
        wb,
        payload,
        trend_history_window=trend_history_window,
    )
