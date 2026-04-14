"""Flagship Excel dashboard generator.

Produces a 10-sheet workbook that serves as the primary way to understand
the portfolio: KPI dashboard, master table, heatmap, quick wins, badges,
tech stack, trends, tier breakdown, activity, and registry reconciliation.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.chart import BarChart, BubbleChart, PieChart, RadarChart, Reference, ScatterChart
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.series import DataPoint
from openpyxl.chart.series import Series as BubbleSeries
from openpyxl.drawing.line import LineProperties
from openpyxl.formatting.rule import ColorScaleRule, DataBarRule, IconSetRule
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.hyperlink import Hyperlink
from openpyxl.worksheet.table import Table, TableStyleInfo

from src.excel_styles import (
    CENTER,
    GRADE_COLORS,
    HEATMAP_AMBER,
    HEATMAP_GREEN,
    HEATMAP_RED,
    LEFT,
    NARRATIVE_FONT,
    NAVY,
    SECTION_FONT,
    SPARKLINE_FONT,
    SUBHEADER_FILL,
    SUBHEADER_FONT,
    SUBTITLE_FONT,
    TEAL,
    THIN_BORDER,
    TIER_FILLS,
    TITLE_FONT,
    WHITE,
    WRAP,
    apply_zebra_stripes,
    auto_width,
    color_grade_cell,
    color_pattern_cell,
    color_tier_cell,
    style_data_cell,
    style_header_row,
    write_kpi_card,
)
from src.excel_template import (
    DEFAULT_TEMPLATE_PATH,
    TEMPLATE_INFO_SHEET,
    TREND_HISTORY_WINDOW,
    SparklineSpec,
    copy_template_to_output,
    inject_native_sparklines,
    resolve_template_path,
)
from src.report_enrichment import (
    build_follow_through_checkpoint_status_label,
    build_follow_through_escalation_status_label,
    build_follow_through_escalation_summary,
    build_follow_through_reacquisition_consolidation_status_label,
    build_follow_through_reacquisition_consolidation_summary,
    build_follow_through_reacquisition_durability_status_label,
    build_follow_through_reacquisition_durability_summary,
    build_follow_through_recovery_freshness_status_label,
    build_follow_through_recovery_freshness_summary,
    build_follow_through_recovery_memory_reset_status_label,
    build_follow_through_recovery_memory_reset_summary,
    build_follow_through_recovery_persistence_status_label,
    build_follow_through_recovery_persistence_summary,
    build_follow_through_recovery_reacquisition_status_label,
    build_follow_through_recovery_reacquisition_summary,
    build_follow_through_recovery_rebuild_strength_status_label,
    build_follow_through_recovery_rebuild_strength_summary,
    build_follow_through_recovery_status_label,
    build_follow_through_recovery_summary,
    build_follow_through_relapse_churn_status_label,
    build_follow_through_relapse_churn_summary,
    build_last_movement_label,
    build_maturity_gap_summary,
    build_operator_focus,
    build_operator_focus_line,
    build_operator_focus_summary,
    build_portfolio_catalog_summary,
    build_portfolio_intent_alignment_summary,
    build_queue_pressure_summary,
    build_repo_briefing,
    build_run_change_counts,
    build_run_change_summary,
    build_score_explanation,
    build_scorecards_summary,
    build_top_recommendation_summary,
    build_trust_actionability_summary,
    build_weekly_review_pack,
    no_baseline_summary,
    no_linked_artifact_summary,
)
from src.sparkline import sparkline as render_sparkline
from src.terminology import ACTION_SYNC_CANONICAL_LABELS

# Tier display order
TIER_ORDER = ["shipped", "functional", "wip", "skeleton", "abandoned"]
PIE_COLORS = ["166534", "1565C0", "D97706", "C2410C", "6B7280"]
CORE_VISIBLE_SHEETS = {
    "Index",
    "Dashboard",
    "All Repos",
    "Portfolio Explorer",
    "Portfolio Catalog",
    "Scorecards",
    "Implementation Hotspots",
    "Operator Outcomes",
    "Approval Ledger",
    "Historical Intelligence",
    "Repo Detail",
    "By Lens",
    "By Collection",
    "Trend Summary",
    "Run Changes",
    "Review Queue",
    "Campaigns",
    "Governance Controls",
    "Executive Summary",
    "Print Pack",
}

REVIEW_QUEUE_LANE_FILLS = {
    "blocked": "FEE2E2",
    "urgent": "FEF3C7",
    "ready": "DBEAFE",
    "deferred": "DCFCE7",
}


def _add_table(ws, table_name: str, max_col: int, max_row: int, start_row: int = 1) -> None:
    """Attach a structured table to hidden sheets and a plain filter to visible ones."""
    if max_row <= start_row:
        return
    if ws.sheet_state == "visible":
        _set_autofilter(ws, max_col, max_row, start_row=start_row)
        return
    ref = f"A{start_row}:{get_column_letter(max_col)}{max_row}"
    table = Table(displayName=table_name, ref=ref)
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    ws.add_table(table)


def _set_autofilter(ws, max_col: int, max_row: int, start_row: int = 1) -> None:
    """Attach a plain AutoFilter to an already-populated range."""
    if max_row <= start_row:
        return
    ws.auto_filter.ref = f"A{start_row}:{get_column_letter(max_col)}{max_row}"


def _clear_worksheet(ws) -> None:
    if ws.max_row:
        ws.delete_rows(1, ws.max_row)
    if ws.max_column:
        ws.delete_cols(1, ws.max_column)
    ws._charts = []
    ws.conditional_formatting._cf_rules.clear()
    ws.data_validations.dataValidation = []
    ws.merged_cells.ranges = set()
    ws.freeze_panes = None
    ws.auto_filter.ref = None
    if hasattr(ws, "_tables"):
        ws._tables.clear()


def _get_or_create_sheet(wb: Workbook, title: str):
    if title in wb.sheetnames:
        ws = wb[title]
        _clear_worksheet(ws)
        return ws
    return wb.create_sheet(title)


def _extend_score_history_with_current(
    data: dict,
    score_history: dict[str, list[float]] | None,
) -> dict[str, list[float]]:
    extended = {name: list(scores) for name, scores in (score_history or {}).items()}
    for audit in data.get("audits", []):
        name = audit.get("metadata", {}).get("name", "")
        if not name:
            continue
        current_score = round(audit.get("overall_score", 0), 3)
        history = extended.setdefault(name, [])
        if not history or abs(history[-1] - current_score) > 1e-9:
            history.append(current_score)
        extended[name] = history[-TREND_HISTORY_WINDOW:]
    return extended


def _extend_portfolio_trend_with_current(
    data: dict,
    trend_data: list[dict] | None,
) -> list[dict]:
    trends = [dict(item) for item in (trend_data or [])]
    current = {
        "date": data.get("generated_at", "")[:10],
        "average_score": data.get("average_score", 0.0),
        "repos_audited": data.get("repos_audited", 0),
        "tier_distribution": data.get("tier_distribution", {}),
        "review_emitted": bool(data.get("material_changes")),
        "campaign_drift_count": len(data.get("managed_state_drift", []) or []),
        "governance_drift_count": len(data.get("governance_drift", []) or []),
    }
    if not trends or trends[-1].get("date") != current["date"]:
        trends.append(current)
    else:
        trends[-1] = current
    return trends[-TREND_HISTORY_WINDOW:]


def _set_defined_name(wb: Workbook, name: str, attr_text: str) -> None:
    try:
        del wb.defined_names[name]
    except KeyError:
        pass
    wb.defined_names.add(DefinedName(name, attr_text=attr_text))


def _refresh_pivot_caches_on_load(wb: Workbook) -> None:
    for ws in wb.worksheets:
        for pivot in getattr(ws, "_pivots", []):
            cache = getattr(pivot, "cache", None)
            if cache and getattr(cache, "refreshOnLoad", None) is not None:
                cache.refreshOnLoad = True


def _configure_sheet_view(ws, *, zoom: int = 110, show_grid_lines: bool = True) -> None:
    ws.sheet_view.zoomScale = zoom
    ws.sheet_view.zoomScaleNormal = 100
    ws.sheet_view.showGridLines = show_grid_lines


def _apply_visible_sheet_profile(wb: Workbook) -> None:
    for ws in wb.worksheets:
        if ws.title.startswith("Data_") or ws.title in {TEMPLATE_INFO_SHEET, "Lookups"}:
            ws.sheet_state = "hidden"
            continue
        ws.sheet_state = "visible" if ws.title in CORE_VISIBLE_SHEETS else "hidden"


def _reorder_workbook_sheets(wb: Workbook) -> None:
    preferred_order = [
        "Index",
        "Dashboard",
        "Review Queue",
        "Portfolio Explorer",
        "Implementation Hotspots",
        "Operator Outcomes",
        "Approval Ledger",
        "Historical Intelligence",
        "Repo Detail",
        "Executive Summary",
        "By Lens",
        "By Collection",
        "Trend Summary",
        "Run Changes",
        "Campaigns",
        "Governance Controls",
        "Print Pack",
    ]
    order_index = {name: index for index, name in enumerate(preferred_order)}
    wb._sheets.sort(key=lambda ws: (order_index.get(ws.title, len(preferred_order)), ws.title))
    if "Index" in wb.sheetnames:
        wb.active = wb.sheetnames.index("Index")


def _review_status_counts(data: dict) -> dict[str, int]:
    counts = {"open": 0, "deferred": 0, "resolved": 0}
    for item in data.get("review_history", []):
        status = item.get("status")
        if status in counts:
            counts[status] += 1
    review_summary = data.get("review_summary", {})
    review_id = review_summary.get("review_id")
    if review_id and not any(item.get("review_id") == review_id for item in data.get("review_history", [])):
        status = review_summary.get("status")
        if status in counts:
            counts[status] += 1
    return counts


def _operator_watch_values(data: dict) -> tuple[str, str, str]:
    summary = data.get("operator_summary") or {}
    next_mode = summary.get("next_recommended_run_mode", "") or "n/a"
    strategy = summary.get("watch_strategy", "") or "manual"
    decision = summary.get("watch_decision_summary", "") or "No watch guidance is recorded."
    return next_mode, strategy, decision


def _operator_handoff_values(data: dict) -> tuple[str, str, str]:
    summary = data.get("operator_summary") or {}
    what_changed = summary.get("what_changed", "") or "No operator change summary is recorded."
    why_it_matters = summary.get("why_it_matters", "") or "No additional operator impact is recorded."
    next_action = summary.get("what_to_do_next", "") or "Continue the normal operator loop."
    return what_changed, why_it_matters, next_action


def _operator_follow_through_value(data: dict) -> str:
    summary = data.get("operator_summary") or {}
    return summary.get("follow_through_summary", "") or "No follow-through signal is recorded yet."


def _operator_follow_through_details(data: dict) -> tuple[str, str, str, str, str]:
    summary = data.get("operator_summary") or {}
    follow_through = summary.get("follow_through_summary", "") or "No follow-through signal is recorded yet."
    checkpoint = summary.get("follow_through_checkpoint_summary", "") or "Use the next run or linked artifact to confirm whether the recommendation moved."
    escalation = summary.get("follow_through_escalation_summary", "") or "No stronger follow-through escalation is currently surfaced."
    top_stale = list(summary.get("top_stale_follow_through_items") or [])
    top_unattempted = list(summary.get("top_unattempted_items") or [])
    top_overdue = list(summary.get("top_overdue_follow_through_items") or [])
    top_escalation = list(summary.get("top_escalation_items") or [])
    top_item = top_overdue[0] if top_overdue else (top_escalation[0] if top_escalation else (top_stale[0] if top_stale else (top_unattempted[0] if top_unattempted else {})))
    top_label = (
        f"{top_item.get('repo')}: {top_item.get('title')}"
        if top_item.get("repo")
        else top_item.get("title", "")
    ) or "No outstanding follow-through hotspot"
    return follow_through, checkpoint, escalation, top_label, top_item.get("follow_through_escalation_summary", "") or top_item.get("follow_through_summary", "") or "No outstanding follow-through hotspot"


def _operator_follow_through_recovery_details(data: dict) -> tuple[str, str, str, str, str, str]:
    summary = data.get("operator_summary") or {}
    recovery = summary.get("follow_through_recovery_summary", "") or "No follow-through recovery or escalation-retirement signal is currently surfaced."
    persistence = summary.get("follow_through_recovery_persistence_summary", "") or "No follow-through recovery persistence signal is currently surfaced."
    churn = summary.get("follow_through_relapse_churn_summary", "") or "No relapse churn is currently surfaced."
    top_relapsing = list(summary.get("top_relapsing_follow_through_items") or [])
    top_retiring = list(summary.get("top_retiring_follow_through_items") or [])
    top_fragile = list(summary.get("top_fragile_recovery_items") or [])
    top_churn = list(summary.get("top_churn_follow_through_items") or [])
    top_item = top_relapsing[0] if top_relapsing else (top_retiring[0] if top_retiring else (top_fragile[0] if top_fragile else {}))
    top_label = (
        f"{top_item.get('repo')}: {top_item.get('title')}"
        if top_item.get("repo")
        else top_item.get("title", "")
    ) or "No active recovery or retirement hotspot"
    top_summary = (
        top_item.get("follow_through_recovery_summary", "")
        or top_item.get("follow_through_recovery_persistence_summary", "")
        or top_item.get("follow_through_escalation_summary", "")
        or "No active recovery or retirement hotspot"
    )
    churn_item = top_churn[0] if top_churn else {}
    churn_label = (
        f"{churn_item.get('repo')}: {churn_item.get('title')}"
        if churn_item.get("repo")
        else churn_item.get("title", "")
    ) or "No relapse-churn hotspot"
    return recovery, persistence, churn, top_label, top_summary or persistence, churn_label


def _operator_follow_through_freshness_details(data: dict) -> tuple[str, str, str, str, str]:
    summary = data.get("operator_summary") or {}
    freshness = summary.get("follow_through_recovery_freshness_summary", "") or "No follow-through recovery freshness signal is currently surfaced."
    memory_reset = summary.get("follow_through_recovery_memory_reset_summary", "") or "No follow-through recovery memory reset signal is currently surfaced."
    top_stale = list(summary.get("top_stale_recovery_items") or [])
    top_reset = list(summary.get("top_reset_recovery_items") or [])
    top_rebuilding = list(summary.get("top_rebuilding_recovery_items") or [])
    top_item = top_stale[0] if top_stale else (top_reset[0] if top_reset else {})
    top_label = (
        f"{top_item.get('repo')}: {top_item.get('title')}"
        if top_item.get("repo")
        else top_item.get("title", "")
    ) or "No stale recovery-memory hotspot"
    top_summary = (
        top_item.get("follow_through_recovery_freshness_summary", "")
        or top_item.get("follow_through_recovery_memory_reset_summary", "")
        or freshness
    )
    rebuild_item = top_rebuilding[0] if top_rebuilding else {}
    rebuild_label = (
        f"{rebuild_item.get('repo')}: {rebuild_item.get('title')}"
        if rebuild_item.get("repo")
        else rebuild_item.get("title", "")
    ) or "No rebuilding recovery-memory hotspot"
    return freshness, memory_reset, top_label, top_summary, rebuild_label


def _operator_follow_through_rebuild_details(data: dict) -> tuple[str, str, str, str, str, str, str, str, str, str, str, str, str]:
    summary = data.get("operator_summary") or {}
    rebuild_strength = summary.get("follow_through_recovery_rebuild_strength_summary", "") or "No follow-through recovery rebuild-strength signal is currently surfaced."
    reacquisition = summary.get("follow_through_recovery_reacquisition_summary", "") or "No follow-through recovery reacquisition signal is currently surfaced."
    durability = summary.get("follow_through_recovery_reacquisition_durability_summary", "") or "No follow-through reacquisition durability signal is currently surfaced."
    confidence = summary.get("follow_through_recovery_reacquisition_consolidation_summary", "") or "No follow-through reacquisition confidence-consolidation signal is currently surfaced."
    top_rebuilding = list(summary.get("top_rebuilding_recovery_strength_items") or [])
    top_reacquiring = list(summary.get("top_reacquiring_recovery_items") or [])
    top_reacquired = list(summary.get("top_reacquired_recovery_items") or [])
    top_fragile = list(summary.get("top_fragile_reacquisition_items") or [])
    top_just = list(summary.get("top_just_reacquired_items") or [])
    top_holding = list(summary.get("top_holding_reacquired_items") or [])
    top_durable = list(summary.get("top_durable_reacquired_items") or [])
    top_softening = list(summary.get("top_softening_reacquired_items") or [])
    top_fragile_confidence = list(summary.get("top_fragile_reacquisition_confidence_items") or [])
    rebuilding_item = top_rebuilding[0] if top_rebuilding else {}
    rebuilding_label = (
        f"{rebuilding_item.get('repo')}: {rebuilding_item.get('title')}"
        if rebuilding_item.get("repo")
        else rebuilding_item.get("title", "")
    ) or "No rebuilding-after-reset hotspot"
    reacquiring_item = top_reacquiring[0] if top_reacquiring else {}
    reacquiring_label = (
        f"{reacquiring_item.get('repo')}: {reacquiring_item.get('title')}"
        if reacquiring_item.get("repo")
        else reacquiring_item.get("title", "")
    ) or "No near-reacquisition hotspot"
    reacquired_item = top_reacquired[0] if top_reacquired else {}
    reacquired_label = (
        f"{reacquired_item.get('repo')}: {reacquired_item.get('title')}"
        if reacquired_item.get("repo")
        else reacquired_item.get("title", "")
    ) or "No re-acquired hotspot"
    fragile_item = top_fragile[0] if top_fragile else {}
    fragile_label = (
        f"{fragile_item.get('repo')}: {fragile_item.get('title')}"
        if fragile_item.get("repo")
        else fragile_item.get("title", "")
    ) or "No fragile reacquisition hotspot"
    just_item = top_just[0] if top_just else {}
    just_label = (
        f"{just_item.get('repo')}: {just_item.get('title')}"
        if just_item.get("repo")
        else just_item.get("title", "")
    ) or "No newly re-acquired hotspot"
    holding_item = top_holding[0] if top_holding else {}
    holding_label = (
        f"{holding_item.get('repo')}: {holding_item.get('title')}"
        if holding_item.get("repo")
        else holding_item.get("title", "")
    ) or "No holding re-acquisition hotspot"
    durable_item = top_durable[0] if top_durable else {}
    durable_label = (
        f"{durable_item.get('repo')}: {durable_item.get('title')}"
        if durable_item.get("repo")
        else durable_item.get("title", "")
    ) or "No durable re-acquisition hotspot"
    softening_item = top_softening[0] if top_softening else {}
    softening_label = (
        f"{softening_item.get('repo')}: {softening_item.get('title')}"
        if softening_item.get("repo")
        else softening_item.get("title", "")
    ) or "No softening re-acquisition hotspot"
    fragile_confidence_item = top_fragile_confidence[0] if top_fragile_confidence else {}
    fragile_confidence_label = (
        f"{fragile_confidence_item.get('repo')}: {fragile_confidence_item.get('title')}"
        if fragile_confidence_item.get("repo")
        else fragile_confidence_item.get("title", "")
    ) or "No fragile re-acquisition confidence hotspot"
    return (
        rebuild_strength,
        reacquisition,
        durability,
        confidence,
        rebuilding_label,
        reacquiring_label,
        reacquired_label,
        fragile_label,
        just_label,
        holding_label,
        durable_label,
        softening_label,
        fragile_confidence_label,
    )


def _operator_follow_through_reacquisition_retirement_details(data: dict) -> tuple[str, str, str, str, str]:
    summary = data.get("operator_summary") or {}
    softening_decay = summary.get("follow_through_reacquisition_softening_decay_summary", "") or "No reacquisition softening-decay signal is currently surfaced."
    confidence_retirement = summary.get("follow_through_reacquisition_confidence_retirement_summary", "") or "No reacquisition confidence-retirement signal is currently surfaced."
    top_softening = list(summary.get("top_softening_reacquisition_items") or [])
    top_revalidation = list(summary.get("top_revalidation_needed_reacquisition_items") or [])
    top_retired = list(summary.get("top_retired_reacquisition_confidence_items") or [])
    softening_item = top_softening[0] if top_softening else {}
    softening_label = (
        f"{softening_item.get('repo')}: {softening_item.get('title')}"
        if softening_item.get("repo")
        else softening_item.get("title", "")
    ) or "No reacquisition softening hotspot"
    revalidation_item = top_revalidation[0] if top_revalidation else {}
    revalidation_label = (
        f"{revalidation_item.get('repo')}: {revalidation_item.get('title')}"
        if revalidation_item.get("repo")
        else revalidation_item.get("title", "")
    ) or "No reacquisition revalidation hotspot"
    retired_item = top_retired[0] if top_retired else {}
    retired_label = (
        f"{retired_item.get('repo')}: {retired_item.get('title')}"
        if retired_item.get("repo")
        else retired_item.get("title", "")
    ) or "No retired re-acquisition confidence hotspot"
    return (
        softening_decay,
        confidence_retirement,
        softening_label,
        revalidation_label,
        retired_label,
    )


def _operator_follow_through_revalidation_recovery_details(data: dict) -> tuple[str, str, str, str, str, str]:
    summary = data.get("operator_summary") or {}
    revalidation_recovery = summary.get("follow_through_reacquisition_revalidation_recovery_summary", "") or (
        "No post-revalidation recovery or confidence re-earning signal is currently surfaced."
    )
    top_under_revalidation = list(summary.get("top_under_revalidation_recovery_items") or [])
    top_rebuilding = list(summary.get("top_rebuilding_restored_confidence_items") or [])
    top_reearning = list(summary.get("top_reearning_confidence_items") or [])
    top_just_reearned = list(summary.get("top_just_reearned_confidence_items") or [])
    top_holding_reearned = list(summary.get("top_holding_reearned_confidence_items") or [])

    def _label(item: dict, fallback: str) -> str:
        return (
            f"{item.get('repo')}: {item.get('title')}"
            if item.get("repo")
            else item.get("title", "")
        ) or fallback

    return (
        revalidation_recovery,
        _label(top_under_revalidation[0] if top_under_revalidation else {}, "No under-revalidation recovery hotspot"),
        _label(top_rebuilding[0] if top_rebuilding else {}, "No rebuilding restored-confidence hotspot"),
        _label(top_reearning[0] if top_reearning else {}, "No confidence re-earning hotspot"),
        _label(top_just_reearned[0] if top_just_reearned else {}, "No just re-earned confidence hotspot"),
        _label(top_holding_reearned[0] if top_holding_reearned else {}, "No holding re-earned confidence hotspot"),
    )


def _operator_trend_values(data: dict) -> tuple[str, str, str, str]:
    summary = data.get("operator_summary") or {}
    trend_status = summary.get("trend_status", "") or "stable"
    trend_summary = summary.get("trend_summary", "") or "No trend summary is recorded yet."
    primary_target = summary.get("primary_target") or {}
    primary_target_label = (
        f"{primary_target.get('repo')}: {primary_target.get('title')}"
        if primary_target.get("repo")
        else primary_target.get("title", "")
    ) or "No active target"
    counts_summary = (
        f"New {summary.get('new_attention_count', 0)} | "
        f"Resolved {summary.get('resolved_attention_count', 0)} | "
        f"Persisting {summary.get('persisting_attention_count', 0)}"
    )
    if summary.get("quiet_streak_runs", 0):
        counts_summary += f" | Quiet streak {summary.get('quiet_streak_runs', 0)}"
    return trend_status.replace("_", " ").title(), trend_summary, primary_target_label, counts_summary


def _operator_accountability_values(data: dict) -> tuple[str, str, str]:
    summary = data.get("operator_summary") or {}
    primary_target_reason = summary.get("primary_target_reason", "") or "No top-target rationale is recorded yet."
    closure_guidance = summary.get("closure_guidance", "") or "No closure guidance is recorded yet."
    longest_item = summary.get("longest_persisting_item") or {}
    longest_label = (
        f"{longest_item.get('repo')}: {longest_item.get('title')}"
        if longest_item.get("repo")
        else longest_item.get("title", "")
    ) or "No persisting item"
    aging_pressure = (
        f"Chronic {summary.get('chronic_item_count', 0)} | "
        f"Newly stale {summary.get('newly_stale_count', 0)} | "
        f"Longest {longest_label}"
    )
    return primary_target_reason, closure_guidance, aging_pressure


def _operator_decision_memory_values(data: dict) -> tuple[str, str, str, str]:
    summary = data.get("operator_summary") or {}
    last_intervention = summary.get("primary_target_last_intervention") or {}
    last_outcome = summary.get("primary_target_last_outcome", "") or "no-change"
    resolution_evidence = summary.get("resolution_evidence_summary", "") or "No resolution evidence is recorded yet."
    if last_intervention:
        when = (last_intervention.get("recorded_at") or "")[:10]
        event_type = last_intervention.get("event_type", "recorded")
        outcome = last_intervention.get("outcome", event_type)
        last_intervention_label = f"{when} {event_type} ({outcome})".strip()
    else:
        last_intervention_label = "No recent intervention recorded"
    recovery_counts = (
        f"Confirmed resolved {summary.get('confirmed_resolved_count', 0)} | "
        f"Reopened {summary.get('reopened_after_resolution_count', 0)}"
    )
    return last_intervention_label, last_outcome.replace("-", " ").title(), resolution_evidence, recovery_counts


def _operator_confidence_values(data: dict) -> tuple[str, str, str, str]:
    summary = data.get("operator_summary") or {}
    primary_confidence = (
        f"{summary.get('primary_target_confidence_label', 'low').title()} "
        f"({summary.get('primary_target_confidence_score', 0.0):.2f})"
    )
    reasons = summary.get("primary_target_confidence_reasons") or []
    confidence_reason = reasons[0] if reasons else "No confidence rationale is recorded yet."
    next_action_confidence = (
        f"{summary.get('next_action_confidence_label', 'low').title()} "
        f"({summary.get('next_action_confidence_score', 0.0):.2f})"
    )
    recommendation_quality = (
        summary.get("recommendation_quality_summary")
        or "No recommendation-quality summary is recorded yet."
    )
    return primary_confidence, confidence_reason, next_action_confidence, recommendation_quality


def _operator_trust_values(data: dict) -> tuple[str, str, str]:
    summary = data.get("operator_summary") or {}
    trust_policy = (summary.get("primary_target_trust_policy", "") or "monitor").replace("-", " ").title()
    trust_reason = (
        summary.get("primary_target_trust_policy_reason")
        or "No trust-policy reason is recorded yet."
    )
    adaptive_summary = (
        summary.get("adaptive_confidence_summary")
        or "No adaptive confidence summary is recorded yet."
    )
    return trust_policy, trust_reason, adaptive_summary


def _operator_exception_values(data: dict) -> tuple[str, str, str, str]:
    summary = data.get("operator_summary") or {}
    exception_status = (
        summary.get("primary_target_exception_status", "") or "none"
    ).replace("-", " ").title()
    exception_reason = (
        summary.get("primary_target_exception_reason")
        or "No trust-policy exception reason is recorded yet."
    )
    drift_status = (
        summary.get("recommendation_drift_status", "") or "stable"
    ).replace("-", " ").title()
    drift_summary = (
        summary.get("recommendation_drift_summary")
        or "No recommendation-drift summary is recorded yet."
    )
    return exception_status, exception_reason, drift_status, drift_summary


def _operator_learning_values(data: dict) -> tuple[str, str, str, str]:
    summary = data.get("operator_summary") or {}
    recovery_status = (
        summary.get("primary_target_trust_recovery_status", "") or "none"
    ).replace("-", " ").title()
    recovery_reason = (
        summary.get("primary_target_trust_recovery_reason")
        or "No trust-recovery reason is recorded yet."
    )
    pattern_status = (
        summary.get("primary_target_exception_pattern_status", "") or "none"
    ).replace("-", " ").title()
    pattern_summary = (
        summary.get("exception_pattern_summary")
        or "No exception-pattern summary is recorded yet."
    )
    return recovery_status, recovery_reason, pattern_status, pattern_summary


def _operator_retirement_values(data: dict) -> tuple[str, str, str, str]:
    summary = data.get("operator_summary") or {}
    recovery_confidence = (
        f"{summary.get('primary_target_recovery_confidence_label', 'low').title()} "
        f"({summary.get('primary_target_recovery_confidence_score', 0.0):.2f})"
    )
    retirement_status = (
        summary.get("primary_target_exception_retirement_status", "") or "none"
    ).replace("-", " ").title()
    retirement_reason = (
        summary.get("primary_target_exception_retirement_reason")
        or "No exception-retirement reason is recorded yet."
    )
    retirement_summary = (
        summary.get("exception_retirement_summary")
        or "No exception-retirement summary is recorded yet."
    )
    return recovery_confidence, retirement_status, retirement_reason, retirement_summary


def _operator_class_normalization_values(data: dict) -> tuple[str, str, str, str]:
    summary = data.get("operator_summary") or {}
    policy_debt = (
        summary.get("primary_target_policy_debt_status", "") or "none"
    ).replace("-", " ").title()
    class_normalization = (
        summary.get("primary_target_class_normalization_status", "") or "none"
    ).replace("-", " ").title()
    debt_reason = (
        summary.get("primary_target_policy_debt_reason")
        or "No policy-debt reason is recorded yet."
    )
    normalization_summary = (
        summary.get("trust_normalization_summary")
        or summary.get("policy_debt_summary")
        or "No class-normalization summary is recorded yet."
    )
    return policy_debt, debt_reason, class_normalization, normalization_summary


def _operator_class_memory_values(data: dict) -> tuple[str, str, str, str]:
    summary = data.get("operator_summary") or {}
    freshness_status = (
        summary.get("primary_target_class_memory_freshness_status", "") or "insufficient-data"
    ).replace("-", " ").title()
    freshness_reason = (
        summary.get("primary_target_class_memory_freshness_reason")
        or "No class-memory freshness reason is recorded yet."
    )
    class_decay_status = (
        summary.get("primary_target_class_decay_status", "") or "none"
    ).replace("-", " ").title()
    class_decay_summary = (
        summary.get("class_decay_summary")
        or summary.get("class_memory_summary")
        or "No class-memory decay summary is recorded yet."
    )
    return freshness_status, freshness_reason, class_decay_status, class_decay_summary


def _operator_class_reweight_values(data: dict) -> tuple[str, str, str, str]:
    summary = data.get("operator_summary") or {}
    direction = (
        summary.get("primary_target_class_trust_reweight_direction", "") or "neutral"
    ).replace("-", " ").title()
    reweight_score = f"{summary.get('primary_target_class_trust_reweight_score', 0.0):.2f}"
    reasons = ", ".join(summary.get("primary_target_class_trust_reweight_reasons") or [])
    if not reasons:
        reasons = "No class reweighting rationale is recorded yet."
    reweight_summary = (
        summary.get("class_reweighting_summary")
        or "No class reweighting summary is recorded yet."
    )
    return direction, reweight_score, reasons, reweight_summary


def _operator_class_momentum_values(data: dict) -> tuple[str, str, str]:
    summary = data.get("operator_summary") or {}
    momentum_status = (
        summary.get("primary_target_class_trust_momentum_status", "") or "insufficient-data"
    ).replace("-", " ").title()
    stability_status = (
        summary.get("primary_target_class_reweight_stability_status", "") or "watch"
    ).replace("-", " ").title()
    transition_status = (
        summary.get("primary_target_class_reweight_transition_status", "") or "none"
    ).replace("-", " ").title()
    transition_reason = (
        summary.get("primary_target_class_reweight_transition_reason")
        or "No class transition reason is recorded yet."
    )
    stability_summary = f"{stability_status} — {transition_status}: {transition_reason}"
    momentum_summary = (
        summary.get("class_momentum_summary")
        or summary.get("class_reweight_stability_summary")
        or "No class momentum summary is recorded yet."
    )
    return momentum_status, stability_summary, momentum_summary


def _operator_class_transition_values(data: dict) -> tuple[str, str, str]:
    summary = data.get("operator_summary") or {}
    health_status = (
        summary.get("primary_target_class_transition_health_status", "") or "none"
    ).replace("-", " ").title()
    resolution_status = (
        summary.get("primary_target_class_transition_resolution_status", "") or "none"
    ).replace("-", " ").title()
    transition_summary = (
        summary.get("class_transition_resolution_summary")
        or summary.get("class_transition_health_summary")
        or "No pending transition summary is recorded yet."
    )
    return health_status, resolution_status, transition_summary


def _operator_transition_closure_values(
    data: dict,
) -> tuple[str, str, str, str, str, str, str, str, str]:
    summary = data.get("operator_summary") or {}
    closure_label = (
        summary.get("primary_target_transition_closure_confidence_label", "") or "low"
    ).replace("-", " ").title()
    likely_outcome = (
        summary.get("primary_target_transition_closure_likely_outcome", "") or "none"
    ).replace("-", " ").title()
    pending_debt_freshness = (
        summary.get("primary_target_pending_debt_freshness_status", "") or "insufficient-data"
    ).replace("-", " ").title()
    closure_forecast_direction = (
        summary.get("primary_target_closure_forecast_reweight_direction", "") or "neutral"
    ).replace("-", " ").title()
    reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery = (
        summary.get(
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status",
            "",
        )
        or "none"
    ).replace("-", " ").title()
    reset_reentry_rebuild_reentry_restore_rerererestore = (
        summary.get(
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status",
            "",
        )
        or "none"
    ).replace("-", " ").title()
    reset_reentry_rebuild_reentry_restore_rerererestore_persistence = (
        summary.get(
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status",
            "",
        )
        or "none"
    ).replace("-", " ").title()
    reset_reentry_rebuild_reentry_restore_rerererestore_churn = (
        summary.get(
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status",
            "",
        )
        or "none"
    ).replace("-", " ").title()
    closure_summary = (
        summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_reset_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_freshness_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_reset_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_persistence_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_churn_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_refresh_recovery_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_freshness_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reset_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_persistence_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_churn_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_summary")
        or summary.get("closure_forecast_reset_reentry_refresh_recovery_summary")
        or summary.get("closure_forecast_reset_reentry_freshness_summary")
        or summary.get("closure_forecast_reset_reentry_reset_summary")
        or summary.get("closure_forecast_reset_reentry_persistence_summary")
        or summary.get("closure_forecast_reset_reentry_churn_summary")
        or summary.get("closure_forecast_reset_reentry_summary")
        or summary.get("closure_forecast_reset_refresh_recovery_summary")
        or summary.get("closure_forecast_persistence_reset_summary")
        or summary.get("closure_forecast_reacquisition_freshness_summary")
        or summary.get("closure_forecast_reacquisition_persistence_summary")
        or summary.get("closure_forecast_recovery_churn_summary")
        or summary.get("closure_forecast_reacquisition_summary")
        or summary.get("closure_forecast_refresh_recovery_summary")
        or summary.get("closure_forecast_decay_summary")
        or summary.get("closure_forecast_freshness_summary")
        or summary.get("closure_forecast_hysteresis_summary")
        or summary.get("closure_forecast_momentum_summary")
        or summary.get("closure_forecast_stability_summary")
        or summary.get("closure_forecast_reweighting_summary")
        or summary.get("pending_debt_freshness_summary")
        or summary.get("transition_closure_confidence_summary")
        or "No closure-forecast summary is recorded yet."
    )
    return (
        closure_label,
        likely_outcome,
        pending_debt_freshness,
        closure_forecast_direction,
        reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery,
        reset_reentry_rebuild_reentry_restore_rerererestore,
        reset_reentry_rebuild_reentry_restore_rerererestore_persistence,
        reset_reentry_rebuild_reentry_restore_rerererestore_churn,
        closure_summary,
    )


def _operator_calibration_values(data: dict) -> tuple[str, str, str, str]:
    summary = data.get("operator_summary") or {}
    validation_status = summary.get("confidence_validation_status", "") or "insufficient-data"
    calibration_summary = (
        summary.get("confidence_calibration_summary")
        or "No confidence-calibration summary is recorded yet."
    )
    high_hit_rate = f"{summary.get('high_confidence_hit_rate', 0.0):.0%}"
    reopened_count = f"{summary.get('reopened_recommendation_count', 0)} reopened"
    return validation_status.replace("-", " ").title(), calibration_summary, high_hit_rate, reopened_count


def _apply_workbook_named_ranges(
    wb: Workbook,
    data: dict,
    *,
    portfolio_profile: str = "default",
    collection: str | None = None,
    excel_mode: str = "standard",
) -> None:
    _set_defined_name(wb, "nrGeneratedAt", "'Dashboard'!$A$2")
    _set_defined_name(wb, "nrReviewOpenCount", f"'{TEMPLATE_INFO_SHEET}'!$B$2")
    _set_defined_name(wb, "nrReviewDeferredCount", f"'{TEMPLATE_INFO_SHEET}'!$B$3")
    _set_defined_name(wb, "nrReviewResolvedCount", f"'{TEMPLATE_INFO_SHEET}'!$B$4")
    _set_defined_name(wb, "nrCampaignActionCount", f"'{TEMPLATE_INFO_SHEET}'!$B$5")
    _set_defined_name(wb, "nrCampaignRepoCount", f"'{TEMPLATE_INFO_SHEET}'!$B$6")
    _set_defined_name(wb, "nrGovernanceReadyCount", f"'{TEMPLATE_INFO_SHEET}'!$B$7")
    _set_defined_name(wb, "nrGovernanceDriftCount", f"'{TEMPLATE_INFO_SHEET}'!$B$8")
    _set_defined_name(wb, "nrPortfolioGrade", f"'{TEMPLATE_INFO_SHEET}'!$B$9")
    _set_defined_name(wb, "nrAverageScore", f"'{TEMPLATE_INFO_SHEET}'!$B$10")
    _set_defined_name(wb, "nrLatestReviewState", f"'{TEMPLATE_INFO_SHEET}'!$B$11")
    _set_defined_name(wb, "nrSelectedProfileLabel", f"'{TEMPLATE_INFO_SHEET}'!$B$12")
    _set_defined_name(wb, "nrSelectedCollectionLabel", f"'{TEMPLATE_INFO_SHEET}'!$B$13")

    dashboard = wb["Dashboard"]
    dashboard["A2"] = f"Generated: {data['generated_at'][:10]} | {data['repos_audited']} repos audited"

    counts = _review_status_counts(data)
    info = wb[TEMPLATE_INFO_SHEET] if TEMPLATE_INFO_SHEET in wb.sheetnames else wb.create_sheet(TEMPLATE_INFO_SHEET)
    info.sheet_state = "hidden"
    values = [
        ("Workbook Mode", excel_mode),
        ("Review Open Count", counts["open"]),
        ("Review Deferred Count", counts["deferred"]),
        ("Review Resolved Count", counts["resolved"]),
        ("Campaign Action Count", data.get("campaign_summary", {}).get("action_count", 0)),
        ("Campaign Repo Count", data.get("campaign_summary", {}).get("repo_count", 0)),
        (
            "Governance Ready Count",
            data.get("governance_preview", {}).get("applyable_count", len(data.get("security_governance_preview", []) or [])),
        ),
        ("Governance Drift Count", len(data.get("governance_drift", []) or [])),
        ("Latest Portfolio Grade", data.get("portfolio_grade", "F")),
        ("Latest Average Score", round(data.get("average_score", 0.0), 3)),
        ("Latest Review State", data.get("review_summary", {}).get("status", "open")),
        ("Selected Profile", portfolio_profile),
        ("Selected Collection", collection or "all"),
    ]
    for row_index, (label, value) in enumerate(values, 1):
        info.cell(row=row_index, column=1, value=label)
        info.cell(row=row_index, column=2, value=value)


def _collection_memberships(data: dict) -> dict[str, list[str]]:
    memberships: dict[str, list[str]] = {}
    for collection_name, collection_data in data.get("collections", {}).items():
        for repo_data in collection_data.get("repos", []):
            repo_name = repo_data["name"] if isinstance(repo_data, dict) else str(repo_data)
            memberships.setdefault(repo_name, []).append(collection_name)
    return memberships


def _sheet_location(sheet_name: str, cell: str = "A1") -> str:
    escaped = sheet_name.replace("'", "''")
    if any(ch in sheet_name for ch in {" ", "'", "!", "-"}):
        return f"'{escaped}'!{cell}"
    return f"{escaped}!{cell}"


def _display_operator_state(value: str | None) -> str:
    mapping = {
        "preview-only": "Preview only",
        "needs-reapproval": "Needs re-approval",
        "ready": "Ready",
        "approved": "Approved",
        "applied": "Applied",
        "blocked": "Blocked",
        "drifted": "Drifted",
        "failed": "Failed",
    }
    if not value:
        return "Unknown"
    return mapping.get(value, value.replace("-", " ").title())


def _severity_rank(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    mapping = {"critical": 1.0, "high": 0.85, "medium": 0.55, "low": 0.25}
    return mapping.get(str(value).lower(), 0.0)


def _operator_counts(data: dict) -> dict[str, int]:
    counts = {"blocked": 0, "urgent": 0, "ready": 0, "deferred": 0}
    operator_summary = data.get("operator_summary") or {}
    if operator_summary.get("counts"):
        counts.update({key: int(operator_summary["counts"].get(key, 0) or 0) for key in counts})
        return counts
    for item in data.get("operator_queue", []) or []:
        lane = item.get("lane")
        if lane in counts:
            counts[lane] += 1
    return counts


def _format_lane_counts(counts: dict[str, int]) -> str:
    return (
        f"{counts.get('blocked', 0)} blocked, "
        f"{counts.get('urgent', 0)} urgent, "
        f"{counts.get('ready', 0)} ready, "
        f"{counts.get('deferred', 0)} deferred"
    )


def _summarize_top_actions(queue: list[dict], *, limit: int = 5) -> list[tuple[str, int]]:
    action_counts = Counter(
        (item.get("recommended_action") or item.get("next_step") or "").strip()
        for item in queue
        if (item.get("recommended_action") or item.get("next_step"))
    )
    return action_counts.most_common(limit)


def _summarize_top_issue_families(material_changes: list[dict], *, limit: int = 5) -> list[tuple[str, int]]:
    issue_counts = Counter()
    for item in material_changes:
        change_type = item.get("change_type") or "other"
        issue_counts[str(change_type).replace("-", " ").title()] += 1
    return issue_counts.most_common(limit)


def _primary_lane_label(blocked: object, urgent: object, ready: object, deferred: object) -> str:
    lane_counts = {
        "Blocked": int(blocked or 0),
        "Needs Attention Now": int(urgent or 0),
        "Ready for Manual Action": int(ready or 0),
        "Safe to Defer": int(deferred or 0),
    }
    return max(lane_counts.items(), key=lambda item: (item[1], -list(lane_counts.keys()).index(item[0])))[0]


def _format_repo_rollup_counts(blocked: object, urgent: object, ready: object, deferred: object) -> str:
    return f"{int(blocked or 0)} blocked, {int(urgent or 0)} urgent, {int(ready or 0)} ready, {int(deferred or 0)} deferred"


def _ordered_queue_items(queue: list[dict]) -> list[dict]:
    lane_order = {"blocked": 0, "urgent": 1, "ready": 2, "deferred": 3}

    def _sort_key(item: dict) -> tuple[object, ...]:
        lane = str(item.get("lane", "urgent")).lower()
        priority = _severity_rank(item.get("priority", item.get("severity", 0)))
        text = " ".join(
            str(item.get(key, "") or "")
            for key in ("title", "summary", "recommended_action", "next_step", "decision_hint")
        ).lower()
        strategic_signal = 1 if any(token in text for token in ("drift", "security", "rollback", "approval")) else 0
        return (
            lane_order.get(lane, 4),
            -strategic_signal,
            -priority,
            str(item.get("repo", item.get("repo_name", ""))),
            str(item.get("title", "")),
        )

    return sorted(queue, key=_sort_key)


def _primary_operator_focus_item(weekly_pack: dict) -> dict:
    for key in (
        "top_act_now_items",
        "top_watch_closely_items",
        "top_improving_items",
        "top_fragile_items",
        "top_revalidate_items",
        "top_attention",
    ):
        items = weekly_pack.get(key) or []
        if items:
            return items[0]
    return {}


def _operator_focus_snapshot(weekly_pack: dict) -> tuple[str, str, str]:
    focus_item = _primary_operator_focus_item(weekly_pack)
    focus_summary = weekly_pack.get("operator_focus_summary", "No operator focus bucket is currently surfaced.")
    focus = str(focus_item.get("operator_focus") or build_operator_focus(focus_item))
    focus_line = str(focus_item.get("operator_focus_line") or build_operator_focus_line(focus_item))
    if not focus_item:
        focus = "Watch Closely"
        focus_line = f"{focus}: {focus_summary}"
    return focus, focus_summary, focus_line


def _build_workbook_rollups(data: dict) -> tuple[list[list[object]], list[list[object]], list[list[object]]]:
    queue = data.get("operator_queue", []) or []
    material_changes = data.get("material_changes", []) or []

    queue_rows: list[list[object]] = []
    for item in queue:
        queue_rows.append(
            [
                item.get("item_id", ""),
                item.get("repo", ""),
                item.get("kind", ""),
                item.get("lane", ""),
                item.get("priority", 0),
                item.get("title", ""),
                item.get("summary", ""),
                item.get("recommended_action", ""),
                item.get("source_run_id", ""),
                item.get("age_days", 0),
                json.dumps(item.get("links", [])),
                item.get("follow_through_age_runs", 0),
                item.get("follow_through_status", ""),
                item.get("follow_through_checkpoint_status", ""),
                item.get("follow_through_summary", ""),
                item.get("follow_through_last_touch", ""),
                item.get("follow_through_next_checkpoint", ""),
                item.get("follow_through_evidence_hint", ""),
                item.get("follow_through_escalation_status", ""),
                item.get("follow_through_escalation_summary", ""),
                item.get("follow_through_escalation_reason", ""),
                item.get("follow_through_recovery_age_runs", 0),
                item.get("follow_through_recovery_status", ""),
                item.get("follow_through_recovery_summary", ""),
                item.get("follow_through_recovery_reason", ""),
                item.get("follow_through_recovery_persistence_age_runs", 0),
                item.get("follow_through_recovery_persistence_status", ""),
                item.get("follow_through_recovery_persistence_summary", ""),
                item.get("follow_through_recovery_persistence_reason", ""),
                item.get("follow_through_relapse_churn_status", ""),
                item.get("follow_through_relapse_churn_summary", ""),
                item.get("follow_through_relapse_churn_reason", ""),
                item.get("follow_through_recovery_freshness_age_runs", 0),
                item.get("follow_through_recovery_freshness_status", ""),
                item.get("follow_through_recovery_freshness_summary", ""),
                item.get("follow_through_recovery_freshness_reason", ""),
                item.get("follow_through_recovery_decay_status", ""),
                item.get("follow_through_recovery_decay_summary", ""),
                item.get("follow_through_recovery_decay_reason", ""),
                item.get("follow_through_recovery_memory_reset_status", ""),
                item.get("follow_through_recovery_memory_reset_summary", ""),
                item.get("follow_through_recovery_memory_reset_reason", ""),
                item.get("follow_through_recovery_rebuild_strength_age_runs", 0),
                item.get("follow_through_recovery_rebuild_strength_status", ""),
                item.get("follow_through_recovery_rebuild_strength_summary", ""),
                item.get("follow_through_recovery_rebuild_strength_reason", ""),
                item.get("follow_through_recovery_reacquisition_status", ""),
                item.get("follow_through_recovery_reacquisition_summary", ""),
                item.get("follow_through_recovery_reacquisition_reason", ""),
                item.get("follow_through_recovery_reacquisition_durability_age_runs", 0),
                item.get("follow_through_recovery_reacquisition_durability_status", ""),
                item.get("follow_through_recovery_reacquisition_durability_summary", ""),
                item.get("follow_through_recovery_reacquisition_durability_reason", ""),
                item.get("follow_through_recovery_reacquisition_consolidation_status", ""),
                item.get("follow_through_recovery_reacquisition_consolidation_summary", ""),
                item.get("follow_through_recovery_reacquisition_consolidation_reason", ""),
                item.get("follow_through_reacquisition_softening_decay_age_runs", 0),
                item.get("follow_through_reacquisition_softening_decay_status", ""),
                item.get("follow_through_reacquisition_softening_decay_summary", ""),
                item.get("follow_through_reacquisition_softening_decay_reason", ""),
                item.get("follow_through_reacquisition_confidence_retirement_status", ""),
                item.get("follow_through_reacquisition_confidence_retirement_summary", ""),
                item.get("follow_through_reacquisition_confidence_retirement_reason", ""),
                item.get("follow_through_reacquisition_revalidation_recovery_age_runs", 0),
                item.get("follow_through_reacquisition_revalidation_recovery_status", ""),
                item.get("follow_through_reacquisition_revalidation_recovery_summary", ""),
                item.get("follow_through_reacquisition_revalidation_recovery_reason", ""),
                item.get("catalog_line", ""),
                item.get("intent_alignment", ""),
                item.get("intent_alignment_reason", ""),
                item.get("scorecard_line", ""),
                item.get("maturity_gap_summary", ""),
                item.get("action_sync_stage", ""),
                item.get("action_sync_reason", ""),
                item.get("suggested_campaign", ""),
                item.get("suggested_writeback_target", ""),
                item.get("action_sync_line", ""),
                item.get("apply_packet_state", ""),
                item.get("apply_packet_summary", ""),
                item.get("apply_packet_command", ""),
                item.get("post_apply_state", ""),
                item.get("post_apply_summary", ""),
                item.get("post_apply_line", ""),
                item.get("campaign_tuning_status", ""),
                item.get("campaign_tuning_summary", ""),
                item.get("campaign_tuning_line", ""),
                item.get("historical_intelligence_status", ""),
                item.get("historical_intelligence_summary", ""),
                item.get("historical_intelligence_line", ""),
                item.get("approval_state", ""),
                item.get("approval_summary", ""),
                item.get("approval_line", ""),
            ]
        )

    repo_rollups: dict[str, dict[str, object]] = {}
    for item in queue:
        repo = item.get("repo") or "(portfolio)"
        record = repo_rollups.setdefault(
            repo,
            {
                "blocked": 0,
                "urgent": 0,
                "ready": 0,
                "deferred": 0,
                "total": 0,
                "kind_counts": Counter(),
                "top_priority": 0,
                "top_title": "",
                "recommended_action": "",
            },
        )
        lane = item.get("lane", "")
        if lane in {"blocked", "urgent", "ready", "deferred"}:
            record[lane] += 1
        record["total"] += 1
        record["kind_counts"][item.get("kind", "review")] += 1
        priority = _severity_rank(item.get("priority", 0))
        if priority >= float(record["top_priority"]):
            record["top_priority"] = priority
            record["top_title"] = item.get("title", "")
            record["recommended_action"] = item.get("recommended_action", "")

    repo_rows: list[list[object]] = []
    for repo, record in sorted(
        repo_rollups.items(),
        key=lambda item: (
            -int(item[1]["blocked"]),
            -int(item[1]["urgent"]),
            -int(item[1]["ready"]),
            -int(item[1]["total"]),
            item[0],
        ),
    ):
        primary_kind = record["kind_counts"].most_common(1)[0][0] if record["kind_counts"] else "review"
        repo_rows.append(
            [
                repo,
                record["total"],
                record["blocked"],
                record["urgent"],
                record["ready"],
                record["deferred"],
                primary_kind,
                record["top_priority"],
                record["top_title"],
                record["recommended_action"],
            ]
        )

    material_rollups: dict[tuple[str, str], dict[str, object]] = {}
    for item in material_changes:
        repo = item.get("repo") or "(portfolio)"
        change_type = item.get("change_type") or "other"
        key = (repo, change_type)
        record = material_rollups.setdefault(
            key,
            {"count": 0, "max_severity": 0.0, "sample_title": ""},
        )
        record["count"] += 1
        severity = _severity_rank(item.get("severity"))
        if severity >= float(record["max_severity"]):
            record["max_severity"] = severity
            record["sample_title"] = item.get("title", "")

    material_rows: list[list[object]] = []
    for (repo, change_type), record in sorted(
        material_rollups.items(),
        key=lambda item: (-int(item[1]["count"]), -float(item[1]["max_severity"]), item[0][0], item[0][1]),
    ):
        material_rows.append(
            [
                repo,
                change_type,
                record["count"],
                record["max_severity"],
                record["sample_title"],
            ]
        )

    return queue_rows, repo_rows, material_rows


def _set_sheet_header(ws, title: str, subtitle: str, *, width: int = 8) -> None:
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=width)
    ws["A1"] = title
    ws["A1"].font = TITLE_FONT
    ws["A1"].alignment = CENTER
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=width)
    ws["A2"] = subtitle
    ws["A2"].font = SUBTITLE_FONT
    ws["A2"].alignment = WRAP


def _write_instruction_banner(ws, row: int, end_col: int, message: str) -> None:
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=end_col)
    cell = ws.cell(row=row, column=1, value=message)
    cell.font = SUBTITLE_FONT
    cell.alignment = WRAP
    cell.fill = PatternFill(fill_type="solid", fgColor="E0F2FE")


def _write_key_value_block(ws, start_row: int, start_col: int, rows: list[tuple[str, object]], *, title: str | None = None) -> int:
    row = start_row
    if title:
        ws.cell(row=row, column=start_col, value=title).font = SECTION_FONT
        row += 1
    for label, value in rows:
        ws.cell(row=row, column=start_col, value=label).font = SUBHEADER_FONT
        style_data_cell(ws.cell(row=row, column=start_col + 1, value=value), "left")
        row += 1
    return row - 1


def _write_ranked_list(
    ws,
    start_row: int,
    start_col: int,
    title: str,
    headers: list[str],
    rows: list[list[object]],
) -> int:
    ws.cell(row=start_row, column=start_col, value=title).font = SECTION_FONT
    header_row = start_row + 1
    for offset, header in enumerate(headers):
        cell = ws.cell(row=header_row, column=start_col + offset, value=header)
        cell.fill = SUBHEADER_FILL
        cell.font = SUBHEADER_FONT
        cell.alignment = CENTER
        cell.border = THIN_BORDER
    ws.row_dimensions[header_row].height = 24
    for row_index, values in enumerate(rows, header_row + 1):
        for col_offset, value in enumerate(values):
            align = "center" if isinstance(value, (int, float)) else "left"
            style_data_cell(ws.cell(row=row_index, column=start_col + col_offset, value=value), align)
    if rows:
        apply_zebra_stripes(ws, header_row + 1, header_row + len(rows), start_col + len(headers) - 1)
    return header_row + len(rows)


def _inject_sheet_navigation(wb: Workbook) -> None:
    strip_sheets = {
        "Dashboard",
        "All Repos",
        "Portfolio Explorer",
        "Repo Detail",
        "By Lens",
        "By Collection",
        "Trend Summary",
        "Run Changes",
        "Review Queue",
        "Campaigns",
        "Governance Controls",
        "Executive Summary",
        "Print Pack",
        "Index",
    }
    ordered_targets = [
        "Dashboard",
        "Review Queue",
        "Repo Detail",
        "Run Changes",
        "Executive Summary",
    ]
    for sheet_name in strip_sheets:
        if sheet_name not in wb.sheetnames:
            continue
        ws = wb[sheet_name]
        start_col = max(ws.max_column + 2, 10)
        title_cell = ws.cell(row=1, column=start_col, value="Quick Links")
        title_cell.font = SUBHEADER_FONT
        for offset, target_sheet in enumerate(ordered_targets, 1):
            if target_sheet not in wb.sheetnames:
                continue
            cell = ws.cell(row=offset + 1, column=start_col, value=target_sheet)
            cell.alignment = LEFT
            if target_sheet == sheet_name:
                cell.font = Font("Calibri", 10, bold=True, color=NAVY)
                continue
            _set_internal_hyperlink(cell, target_sheet, display=target_sheet)


# ═══════════════════════════════════════════════════════════════════════
# Sheet 1: Dashboard (Executive Overview)
# ═══════════════════════════════════════════════════════════════════════


def _generate_narrative(data: dict, diff_data: dict | None) -> str:
    """Auto-generate a one-line dashboard narrative."""
    if not diff_data:
        tiers = data.get("tier_distribution", {})
        return (
            f"Portfolio: {data['repos_audited']} repos analyzed. "
            f"{tiers.get('shipped', 0)} shipped, avg score {data['average_score']:.2f}."
        )

    parts = [f"Since last audit ({diff_data.get('previous_date', '')[:10]}):"]
    shipped_d = diff_data.get("tier_distribution_delta", {}).get("shipped", 0)
    avg_d = diff_data.get("average_score_delta", 0)
    promos = len(diff_data.get("tier_changes", []))
    new_count = len(diff_data.get("new_repos", []))

    if shipped_d:
        parts.append(f"{shipped_d:+d} shipped")
    if abs(avg_d) > 0.005:
        parts.append(f"avg score {avg_d:+.3f}")
    if promos:
        parts.append(f"{promos} tier changes")
    if new_count:
        parts.append(f"{new_count} new repos")

    # Find closest promotion
    tier_next = {"functional": 0.75, "wip": 0.55, "skeleton": 0.35}
    closest_name, closest_gap = None, 1.0
    for a in data.get("audits", []):
        tier = a.get("completeness_tier", "")
        if tier in tier_next:
            gap = tier_next[tier] - a.get("overall_score", 0)
            if 0 < gap < closest_gap:
                closest_gap = gap
                closest_name = a["metadata"]["name"]
    if closest_name:
        parts.append(f"Priority: {closest_name} needs {closest_gap:.3f} to promote")

    return " | ".join(parts)


def _build_dashboard(
    wb: Workbook,
    data: dict,
    diff_data: dict | None = None,
    score_history: dict[str, list[float]] | None = None,
    *,
    excel_mode: str = "standard",
) -> None:
    if "Dashboard" in wb.sheetnames:
        ws = _get_or_create_sheet(wb, "Dashboard")
    elif len(wb.sheetnames) == 1 and wb.active.title == "Sheet":
        ws = wb.active
        ws.title = "Dashboard"
        _clear_worksheet(ws)
    else:
        ws = _get_or_create_sheet(wb, "Dashboard")
    ws.sheet_properties.tabColor = NAVY
    _configure_sheet_view(ws, zoom=120, show_grid_lines=False)

    # Title
    ws.merge_cells("A1:L1")
    c = ws["A1"]
    c.value = f"GitHub Portfolio Dashboard: {data['username']}"
    c.font = TITLE_FONT
    c.alignment = CENTER

    ws.merge_cells("A2:L2")
    c = ws["A2"]
    c.value = f"Generated: {data['generated_at'][:10]} | {data['repos_audited']} repos audited"
    c.font = SUBTITLE_FONT
    c.alignment = CENTER

    # Narrative row
    ws.merge_cells("A3:L3")
    c = ws["A3"]
    c.value = _generate_narrative(data, diff_data)
    c.font = NARRATIVE_FONT
    c.alignment = WRAP
    ws.row_dimensions[3].height = 30
    ws.freeze_panes = "A5"
    ws["A4"] = "Portfolio Health Snapshot"
    ws["A4"].font = SECTION_FONT
    ws["O4"] = "Operator Attention Snapshot"
    ws["O4"].font = SECTION_FONT

    # KPI Cards (row 5-6)
    grade = data.get("portfolio_grade", "?")
    grade_color = GRADE_COLORS.get(grade, NAVY)
    write_kpi_card(ws, 5, 1, "Portfolio Grade", grade, grade_color)
    write_kpi_card(ws, 5, 3, "Avg Score", f"{data['average_score']:.2f}")
    tiers = data.get("tier_distribution", {})
    write_kpi_card(ws, 5, 5, "Shipped", tiers.get("shipped", 0), "166534", f"#{_sheet_location('Tier Breakdown')}")
    write_kpi_card(ws, 5, 7, "Functional", tiers.get("functional", 0), "1565C0", f"#{_sheet_location('Tier Breakdown')}")
    write_kpi_card(ws, 5, 9, "WIP", tiers.get("wip", 0), "D97706", f"#{_sheet_location('Quick Wins')}")
    skel_aband = tiers.get("skeleton", 0) + tiers.get("abandoned", 0)
    write_kpi_card(ws, 5, 11, "Needs Work", skel_aband, "C2410C")

    # Row height
    ws.row_dimensions[5].height = 20
    ws.row_dimensions[6].height = 40

    # Portfolio score sparkline (row 7, next to KPI cards)
    if score_history:
        from src.history import load_trend_data as _load_trends
        avg_scores = [t.get("average_score", 0) for t in (_load_trends() or [])]
        spark = render_sparkline(avg_scores)
        if spark:
            cell = ws.cell(row=7, column=3, value=f"Trend: {spark}")
            cell.font = SPARKLINE_FONT
    run_change_summary = data.get("run_change_summary") or build_run_change_summary(diff_data)
    queue_pressure_summary = build_queue_pressure_summary(data, diff_data)
    trust_actionability_summary = build_trust_actionability_summary(data)
    top_recommendation_summary = build_top_recommendation_summary(data)
    weekly_pack = build_weekly_review_pack(data, diff_data)
    operator_focus, operator_focus_summary, operator_focus_line = _operator_focus_snapshot(weekly_pack)
    ws["M8"] = "Run Summary"
    ws["M8"].font = SUBHEADER_FONT
    ws["N8"] = run_change_summary
    ws["N8"].alignment = WRAP
    ws["M9"] = "Queue Pressure"
    ws["M9"].font = SUBHEADER_FONT
    ws["N9"] = queue_pressure_summary

    operator_summary = data.get("operator_summary") or {}
    governance_summary = data.get("governance_summary") or {}
    campaign_summary = data.get("campaign_summary") or {}
    setup_health = operator_summary.get("operator_setup_health") or {}
    lane_counts = _operator_counts(data)
    next_mode, watch_strategy, watch_decision = _operator_watch_values(data)
    what_changed, why_it_matters, next_action = _operator_handoff_values(data)
    (
        follow_through,
        follow_through_checkpoint,
        follow_through_escalation,
        follow_through_hotspot,
        follow_through_escalation_hotspot,
    ) = _operator_follow_through_details(data)
    (
        follow_through_recovery,
        follow_through_recovery_persistence,
        follow_through_relapse_churn,
        follow_through_relapsing_hotspot,
        follow_through_retiring_hotspot,
        follow_through_churn_hotspot,
    ) = _operator_follow_through_recovery_details(data)
    (
        follow_through_recovery_freshness,
        follow_through_recovery_memory_reset,
        follow_through_recovery_freshness_hotspot,
        follow_through_recovery_freshness_hotspot_summary,
        follow_through_recovery_rebuild_hotspot,
    ) = _operator_follow_through_freshness_details(data)
    (
        follow_through_rebuild_strength,
        follow_through_reacquisition,
        follow_through_reacquisition_durability,
        follow_through_reacquisition_confidence,
        follow_through_rebuild_strength_hotspot,
        follow_through_reacquiring_hotspot,
        follow_through_reacquired_hotspot,
        follow_through_fragile_reacquisition_hotspot,
        follow_through_just_reacquired_hotspot,
        follow_through_holding_reacquired_hotspot,
        follow_through_durable_reacquired_hotspot,
        follow_through_softening_reacquired_hotspot,
        follow_through_fragile_reacquisition_confidence_hotspot,
    ) = _operator_follow_through_rebuild_details(data)
    (
        follow_through_reacquisition_softening_decay,
        follow_through_reacquisition_confidence_retirement,
        follow_through_reacquisition_softening_hotspot,
        follow_through_reacquisition_revalidation_hotspot,
        follow_through_reacquisition_retired_confidence_hotspot,
    ) = _operator_follow_through_reacquisition_retirement_details(data)
    (
        follow_through_revalidation_recovery,
        follow_through_under_revalidation_hotspot,
        follow_through_rebuilding_restored_confidence_hotspot,
        follow_through_reearning_confidence_hotspot,
        follow_through_just_reearned_confidence_hotspot,
        follow_through_holding_reearned_confidence_hotspot,
    ) = _operator_follow_through_revalidation_recovery_details(data)
    (
        follow_through_revalidation_recovery,
        follow_through_under_revalidation_hotspot,
        follow_through_rebuilding_restored_confidence_hotspot,
        follow_through_reearning_confidence_hotspot,
        follow_through_just_reearned_confidence_hotspot,
        follow_through_holding_reearned_confidence_hotspot,
    ) = _operator_follow_through_revalidation_recovery_details(data)
    (
        follow_through_revalidation_recovery,
        follow_through_under_revalidation_hotspot,
        follow_through_rebuilding_restored_confidence_hotspot,
        follow_through_reearning_confidence_hotspot,
        follow_through_just_reearned_confidence_hotspot,
        follow_through_holding_reearned_confidence_hotspot,
    ) = _operator_follow_through_revalidation_recovery_details(data)
    trend_status, trend_summary, primary_target, resolution_counts = _operator_trend_values(data)
    primary_target_reason, closure_guidance, aging_pressure = _operator_accountability_values(data)
    last_intervention, last_outcome, resolution_evidence, recovery_counts = _operator_decision_memory_values(data)
    primary_confidence, confidence_reason, next_action_confidence, recommendation_quality = _operator_confidence_values(data)
    trust_policy, trust_policy_reason, adaptive_confidence_summary = _operator_trust_values(data)
    exception_status, exception_reason, drift_status, drift_summary = _operator_exception_values(data)
    trust_recovery_status, trust_recovery_reason, exception_pattern_status, exception_pattern_summary = _operator_learning_values(data)
    recovery_confidence, retirement_status, retirement_reason, retirement_summary = _operator_retirement_values(data)
    policy_debt_status, policy_debt_reason, class_normalization_status, trust_normalization_summary = _operator_class_normalization_values(data)
    class_memory_status, class_memory_reason, class_decay_status, class_decay_summary = _operator_class_memory_values(data)
    class_reweight_direction, class_reweight_score, class_reweight_reason, class_reweight_summary = _operator_class_reweight_values(data)
    class_momentum_status, class_reweight_stability, class_momentum_summary = _operator_class_momentum_values(data)
    class_transition_health, class_transition_resolution, class_transition_summary = _operator_class_transition_values(data)
    (
        transition_closure_confidence,
        transition_likely_outcome,
        pending_debt_freshness,
        closure_forecast_direction,
        reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery,
        reset_reentry_rebuild_reentry_restore_rerererestore,
        reset_reentry_rebuild_reentry_restore_rerererestore_persistence,
        reset_reentry_rebuild_reentry_restore_rerererestore_churn,
        transition_closure_summary,
    ) = _operator_transition_closure_values(data)
    calibration_status, calibration_summary, high_hit_rate, reopened_recommendations = _operator_calibration_values(data)
    ws["M10"] = "Trust Summary"
    ws["M10"].font = SUBHEADER_FONT
    ws["N10"] = trust_actionability_summary
    ws["M11"] = "Top Recommendation"
    ws["M11"].font = SUBHEADER_FONT
    ws["N11"] = top_recommendation_summary
    ws["M12"] = "Use This Page"
    ws["M12"].font = SUBHEADER_FONT
    ws["N12"] = "Read the left side for portfolio shape, the right side for operator pressure, then jump into Review Queue or Repo Detail."

    operator_rows = [
        ("Setup Health", _display_operator_state(setup_health.get("status", "ok"))),
        ("Operator Headline", operator_summary.get("headline", "Portfolio health is stable.")),
        ("Queue Counts", _format_lane_counts(lane_counts)),
        ("Governance", governance_summary.get("headline", "Governance preview is aligned with the latest report.")),
        (
            "Campaign State",
            campaign_summary.get("label")
            or campaign_summary.get("campaign_type")
            or "No active managed campaign in this run.",
        ),
        ("Run Changes", run_change_summary),
        (
            "Queue Pressure",
            queue_pressure_summary,
        ),
        ("What Changed", what_changed),
        ("Why It Matters", why_it_matters),
        ("Follow-Through", follow_through),
        ("Next Checkpoint", follow_through_checkpoint),
        ("Escalation", follow_through_escalation),
        ("Recovery / Retirement", follow_through_recovery),
        ("Recovery Persistence", follow_through_recovery_persistence),
        ("Relapse Churn", follow_through_relapse_churn),
        ("Recovery Freshness", follow_through_recovery_freshness),
        ("Recovery Memory Reset", follow_through_recovery_memory_reset),
        ("Recovery Rebuild Strength", follow_through_rebuild_strength),
        ("Recovery Reacquisition", follow_through_reacquisition),
        ("Reacquisition Durability", follow_through_reacquisition_durability),
        ("Reacquisition Confidence", follow_through_reacquisition_confidence),
        ("Operator Focus", operator_focus),
        ("Focus Summary", operator_focus_summary),
        ("Focus Line", operator_focus_line),
        ("Portfolio Catalog", build_portfolio_catalog_summary(data)),
        ("Intent Alignment", build_portfolio_intent_alignment_summary(data)),
        ("Scorecards", build_scorecards_summary(data)),
        ("Next Action", next_action),
        ("Top Recommendation", top_recommendation_summary),
    ]
    if excel_mode == "standard":
        operator_rows.extend(
            [
                ("Trend", f"{trend_status} — {trend_summary}"),
                ("Primary Target", primary_target),
                ("Resolution Counts", resolution_counts),
                ("Recovery Hotspot", follow_through_relapsing_hotspot),
                ("Retiring Watch Hotspot", follow_through_retiring_hotspot),
                ("Churn Hotspot", follow_through_churn_hotspot),
                ("Freshness Hotspot", follow_through_recovery_freshness_hotspot),
                ("Freshness Detail", follow_through_recovery_freshness_hotspot_summary),
                ("Rebuild Hotspot", follow_through_recovery_rebuild_hotspot),
                ("Rebuild Strength Hotspot", follow_through_rebuild_strength_hotspot),
                ("Reacquiring Hotspot", follow_through_reacquiring_hotspot),
                ("Reacquired Hotspot", follow_through_reacquired_hotspot),
                ("Fragile Reacquisition Hotspot", follow_through_fragile_reacquisition_hotspot),
                ("Just Reacquired Hotspot", follow_through_just_reacquired_hotspot),
                ("Holding Reacquired Hotspot", follow_through_holding_reacquired_hotspot),
                ("Durable Reacquired Hotspot", follow_through_durable_reacquired_hotspot),
                ("Softening Reacquired Hotspot", follow_through_softening_reacquired_hotspot),
                ("Fragile Reacquisition Confidence Hotspot", follow_through_fragile_reacquisition_confidence_hotspot),
                ("Reacquisition Softening Hotspot", follow_through_reacquisition_softening_hotspot),
                ("Revalidation Needed Hotspot", follow_through_reacquisition_revalidation_hotspot),
                ("Retired Confidence Hotspot", follow_through_reacquisition_retired_confidence_hotspot),
                ("Under Revalidation Hotspot", follow_through_under_revalidation_hotspot),
                ("Rebuilding Restored Confidence Hotspot", follow_through_rebuilding_restored_confidence_hotspot),
                ("Re-Earning Confidence Hotspot", follow_through_reearning_confidence_hotspot),
                ("Just Re-Earned Confidence Hotspot", follow_through_just_reearned_confidence_hotspot),
                ("Holding Re-Earned Confidence Hotspot", follow_through_holding_reearned_confidence_hotspot),
            ]
        )
    operator_rows.extend(
        [
            ("Next Run", next_mode),
            ("Watch Strategy", watch_strategy),
            ("Watch Decision", watch_decision),
            ("Source Run", operator_summary.get("source_run_id", "")),
        ]
    )
    if excel_mode == "standard":
        operator_rows.extend(
            [
                ("Why Top Target", primary_target_reason),
                ("Follow-Through Hotspot", follow_through_hotspot),
                ("Escalation Hotspot", follow_through_escalation_hotspot),
                ("Recovery Hotspot", follow_through_relapsing_hotspot),
                ("Retiring Watch Hotspot", follow_through_retiring_hotspot),
                ("Closure Guidance", closure_guidance),
                ("Aging Pressure", aging_pressure),
                ("What We Tried", last_intervention),
                ("Last Outcome", last_outcome),
                ("Resolution Evidence", resolution_evidence),
                ("Recovery Counts", recovery_counts),
                ("Recommendation Confidence", primary_confidence),
                ("Confidence Rationale", confidence_reason),
                ("Next Action Confidence", next_action_confidence),
                ("Trust Policy", trust_policy),
                ("Trust Rationale", trust_policy_reason),
                ("Trust Exception", f"{exception_status} — {exception_reason}"),
                ("Trust Recovery", f"{trust_recovery_status} — {trust_recovery_reason}"),
                ("Recovery Confidence", recovery_confidence),
                ("Exception Retirement", f"{retirement_status} — {retirement_reason}"),
                ("Retirement Summary", retirement_summary),
                ("Policy Debt", f"{policy_debt_status} — {policy_debt_reason}"),
                ("Class Normalization", f"{class_normalization_status} — {trust_normalization_summary}"),
                ("Class Memory", f"{class_memory_status} — {class_memory_reason}"),
                ("Trust Decay", f"{class_decay_status} — {class_decay_summary}"),
                ("Class Reweighting", f"{class_reweight_direction} ({class_reweight_score}) — {class_reweight_summary}"),
                ("Class Reweighting Why", class_reweight_reason),
                ("Class Momentum", class_momentum_status),
                ("Reweight Stability", class_reweight_stability),
                ("Transition Health", class_transition_health),
                ("Transition Resolution", class_transition_resolution),
                ("Transition Summary", class_transition_summary),
                ("Transition Closure", transition_closure_confidence),
                ("Transition Likely Outcome", transition_likely_outcome),
                ("Pending Debt Freshness", pending_debt_freshness),
                ("Closure Forecast", closure_forecast_direction),
                ("Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Persistence", reset_reentry_rebuild_reentry_restore_rerererestore_persistence),
                ("Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Churn Controls", reset_reentry_rebuild_reentry_restore_rerererestore_churn),
                ("Closure Forecast Summary", transition_closure_summary),
                ("Momentum Summary", class_momentum_summary),
                ("Exception Learning", f"{exception_pattern_status} — {exception_pattern_summary}"),
                ("Recommendation Drift", f"{drift_status} — {drift_summary}"),
                ("Adaptive Confidence", adaptive_confidence_summary),
                ("Recommendation Quality", recommendation_quality),
                ("Confidence Validation", f"{calibration_status} — {calibration_summary}"),
                ("High-Confidence Hit Rate", high_hit_rate),
                ("Reopened Recommendations", reopened_recommendations),
            ]
        )
    operator_block_end = _write_key_value_block(ws, 5, 15, operator_rows, title="Operator Snapshot")

    repo_rollups = _build_workbook_rollups(data)[1]
    top_attention_rows = []
    for repo, total, blocked, urgent, ready, deferred, _kind, _priority, title, action in repo_rollups[:5]:
        top_attention_rows.append(
            [
                repo,
                f"B{blocked} / U{urgent} / R{ready}",
                title or "See detailed queue",
                action or "Review repo detail",
            ]
        )
    if not top_attention_rows:
        top_attention_rows.append(["Portfolio", "No open items", "Nothing is currently queued.", "Monitor future audits"])
    top_attention_start = max(19, operator_block_end + 2)
    _write_ranked_list(
        ws,
        top_attention_start,
        15,
        "Top Attention Items",
        ["Repo", "Counts", "Why Now", "Next Step"],
        top_attention_rows,
    )

    audits_sorted = sorted(data.get("audits", []), key=lambda audit: audit.get("overall_score", 0), reverse=True)
    top_opportunities: list[list[object]] = []
    for audit in audits_sorted:
        action = (audit.get("action_candidates") or [{}])[0]
        hotspots = audit.get("hotspots") or []
        best_next_move = action.get("title", "")
        if not best_next_move and hotspots:
            best_next_move = hotspots[0].get("recommended_action", "")
        top_opportunities.append(
            [
                audit.get("metadata", {}).get("name", ""),
                round(audit.get("overall_score", 0), 3),
                audit.get("completeness_tier", ""),
                best_next_move,
            ]
        )
        if len(top_opportunities) == 5:
            break
    _write_ranked_list(
        ws,
        top_attention_start + 8,
        15,
        "Top Opportunities",
        ["Repo", "Score", "Tier", "Best Next Move"],
        top_opportunities,
    )

    bottom_repos = sorted(data.get("audits", []), key=lambda audit: audit.get("overall_score", 0))[:5]
    laggard_rows = [
        [
            audit.get("metadata", {}).get("name", ""),
            round(audit.get("overall_score", 0), 3),
            audit.get("completeness_tier", ""),
            (audit.get("hotspots") or [{}])[0].get("title", "Needs follow-through"),
        ]
        for audit in bottom_repos
    ]
    _write_ranked_list(
        ws,
        top_attention_start + 16,
        15,
        "Top Laggards",
        ["Repo", "Score", "Tier", "What Is Dragging It Down"],
        laggard_rows,
    )

    # Portfolio DNA row (row 8) — one colored cell per repo
    dna_row = 8
    ws.cell(row=dna_row, column=1, value="Portfolio DNA").font = SUBHEADER_FONT
    audits_sorted = sorted(data.get("audits", []), key=lambda a: a.get("overall_score", 0), reverse=True)
    for i, audit in enumerate(audits_sorted[:24]):
        cell = ws.cell(row=dna_row, column=2 + i, value="")
        tier = audit.get("completeness_tier", "abandoned")
        if tier in TIER_FILLS:
            cell.fill = TIER_FILLS[tier]

    ws.merge_cells("A9:L10")
    ws["A9"] = (
        "Use the left side for portfolio shape and the right side for operator pressure. "
        "If you only have a minute, read the narrative, scan the queue snapshot, and then open Review Queue."
    )
    ws["A9"].font = SUBTITLE_FONT
    ws["A9"].alignment = WRAP

    # Tier Pie Chart
    pie_label_col = 24
    pie_value_col = 25
    pie_start = 10
    for i, tier in enumerate(TIER_ORDER):
        ws.cell(row=pie_start + i, column=pie_label_col, value=tier.capitalize())
        ws.cell(row=pie_start + i, column=pie_value_col, value=tiers.get(tier, 0))

    pie = PieChart()
    pie.title = "Tier Distribution"
    pie.style = 10
    labels = Reference(ws, min_col=pie_label_col, min_row=pie_start, max_row=pie_start + 4)
    values = Reference(ws, min_col=pie_value_col, min_row=pie_start, max_row=pie_start + 4)
    pie.add_data(values, titles_from_data=False)
    pie.set_categories(labels)
    pie.dataLabels = DataLabelList()
    pie.dataLabels.showPercent = True
    pie.dataLabels.showVal = True
    for i, color in enumerate(PIE_COLORS):
        pt = DataPoint(idx=i)
        pt.graphicalProperties.solidFill = color
        pie.series[0].data_points.append(pt)
    pie.width = 8.4
    pie.height = 6.5
    ws.add_chart(pie, "A17")

    # Grade Distribution Bar Chart
    grade_dist = Counter(a.get("grade", "F") for a in data.get("audits", []))
    grade_label_col = 27
    grade_value_col = 28
    grade_row = 10
    for i, g in enumerate(["A", "B", "C", "D", "F"]):
        ws.cell(row=grade_row + i, column=grade_label_col, value=g)
        ws.cell(row=grade_row + i, column=grade_value_col, value=grade_dist.get(g, 0))

    bar = BarChart()
    bar.type = "col"
    bar.title = "Grade Distribution"
    bar.style = 10
    bar_data = Reference(ws, min_col=grade_value_col, min_row=grade_row, max_row=grade_row + 4)
    bar_cats = Reference(ws, min_col=grade_label_col, min_row=grade_row, max_row=grade_row + 4)
    bar.add_data(bar_data, titles_from_data=False)
    bar.set_categories(bar_cats)
    bar.width = 8.4
    bar.height = 6.5
    ws.add_chart(bar, "J17")

    # Highlights section
    highlight_row = 31
    ws.cell(row=highlight_row, column=1, value="Highlights").font = SECTION_FONT

    best_work = data.get("best_work") or data.get("summary", {}).get("highest_scored", [])
    if best_work:
        ws.cell(row=highlight_row + 1, column=1, value="Best Work:").font = SUBHEADER_FONT
        for i, name in enumerate(best_work[:5]):
            ws.cell(row=highlight_row + 1, column=2 + i, value=name)

    for column_index in range(24, 42):
        ws.column_dimensions[get_column_letter(column_index)].hidden = True
    preferred_widths = {
        "A": 24,
        "B": 12,
        "C": 12,
        "D": 12,
        "E": 12,
        "F": 12,
        "G": 11,
        "H": 11,
        "I": 11,
        "J": 11,
        "K": 12,
        "L": 14,
        "O": 18,
        "P": 22,
        "Q": 16,
        "R": 24,
    }
    for column_letter, width in preferred_widths.items():
        ws.column_dimensions[column_letter].width = width

    lowest = data.get("summary", {}).get("lowest_scored", [])
    if lowest:
        ws.cell(row=highlight_row + 2, column=1, value="Needs Attention:").font = SUBHEADER_FONT
        for i, name in enumerate(lowest[:5]):
            ws.cell(row=highlight_row + 2, column=2 + i, value=name)

    # Language distribution
    lang_dist = data.get("language_distribution", {})
    lang_label_col = 30
    lang_value_col = 31
    lang_row = 10
    for i, (lang, count) in enumerate(list(lang_dist.items())[:8]):
        ws.cell(row=lang_row + i, column=lang_label_col, value=lang)
        ws.cell(row=lang_row + i, column=lang_value_col, value=count)

    if lang_dist:
        lang_bar = BarChart()
        lang_bar.type = "bar"
        lang_bar.title = "Top Languages"
        lang_bar.style = 10
        lang_data = Reference(ws, min_col=lang_value_col, min_row=lang_row, max_row=lang_row + min(7, len(lang_dist) - 1))
        lang_cats = Reference(ws, min_col=lang_label_col, min_row=lang_row, max_row=lang_row + min(7, len(lang_dist) - 1))
        lang_bar.add_data(lang_data, titles_from_data=False)
        lang_bar.set_categories(lang_cats)
        lang_bar.width = 8.0
        lang_bar.height = 6.5
        ws.add_chart(lang_bar, "A35")

    # Scatter chart: Completeness vs Interest
    _build_scatter_on_dashboard(ws, data)


def _build_scatter_on_dashboard(ws, data: dict) -> None:
    """Add completeness vs interest scatter chart with quadrant lines."""
    audits = data.get("audits", [])
    if len(audits) < 2:
        return

    # Write scatter data to hidden support columns starting at AG.
    data_start_row = 10
    col_name = 33  # AG: repo name (reference)
    col_x = 34     # AH: completeness
    col_y = 35     # AI: interest

    for i, audit in enumerate(audits):
        row = data_start_row + i
        ws.cell(row=row, column=col_name, value=audit["metadata"]["name"])
        ws.cell(row=row, column=col_x, value=round(audit.get("overall_score", 0), 3))
        ws.cell(row=row, column=col_y, value=round(audit.get("interest_score", 0), 3))

    data_end_row = data_start_row + len(audits) - 1

    chart = ScatterChart()
    chart.title = "Completeness vs Interest"
    chart.x_axis.title = "Completeness"
    chart.y_axis.title = "Interest"
    chart.x_axis.scaling.min = 0
    chart.x_axis.scaling.max = 1
    chart.y_axis.scaling.min = 0
    chart.y_axis.scaling.max = 1
    chart.style = 13

    # Main data series — use add_data + set_categories (openpyxl scatter API)
    xvalues = Reference(ws, min_col=col_x, min_row=data_start_row, max_row=data_end_row)
    yvalues = Reference(ws, min_col=col_y, min_row=data_start_row, max_row=data_end_row)
    chart.add_data(yvalues, titles_from_data=False)
    chart.set_categories(xvalues)
    if chart.series:
        chart.series[0].graphicalProperties.line.noFill = True

    # Quadrant lines — vertical at x=0.55, horizontal at y=0.45
    line_col = 36  # AJ for line data
    ws.cell(row=data_start_row, column=line_col, value=0.55)
    ws.cell(row=data_start_row, column=line_col + 1, value=0.0)
    ws.cell(row=data_start_row + 1, column=line_col, value=0.55)
    ws.cell(row=data_start_row + 1, column=line_col + 1, value=1.0)

    vline_y = Reference(ws, min_col=line_col + 1, min_row=data_start_row, max_row=data_start_row + 1)
    vline_x = Reference(ws, min_col=line_col, min_row=data_start_row, max_row=data_start_row + 1)
    chart.add_data(vline_y, titles_from_data=False)
    chart.set_categories(vline_x)
    if len(chart.series) > 1:
        chart.series[-1].graphicalProperties.line = LineProperties(w=12700, prstDash="dash", solidFill="808080")

    ws.cell(row=data_start_row, column=line_col + 2, value=0.0)
    ws.cell(row=data_start_row, column=line_col + 3, value=0.45)
    ws.cell(row=data_start_row + 1, column=line_col + 2, value=1.0)
    ws.cell(row=data_start_row + 1, column=line_col + 3, value=0.45)

    hline_y = Reference(ws, min_col=line_col + 3, min_row=data_start_row, max_row=data_start_row + 1)
    hline_x = Reference(ws, min_col=line_col + 2, min_row=data_start_row, max_row=data_start_row + 1)
    chart.add_data(hline_y, titles_from_data=False)
    chart.set_categories(hline_x)
    if len(chart.series) > 2:
        chart.series[-1].graphicalProperties.line = LineProperties(w=12700, prstDash="dash", solidFill="808080")

    chart.width = 10.5
    chart.height = 8
    ws.add_chart(chart, "J34")

    # Quadrant summary table
    _write_quadrant_table(ws, audits, legend_row=52)


X_MID = 0.55
Y_MID = 0.45

QUADRANT_NAMES = [
    ("Flagships", "high completeness + high interest"),
    ("Hidden Gems", "high interest, incomplete — worth finishing"),
    ("Workhorses", "solid but routine — bread and butter"),
    ("Archive Candidates", "low both — consider archiving"),
]


def _write_quadrant_table(ws, audits: list[dict], legend_row: int) -> None:
    """Write a quadrant summary table below the scatter chart."""
    buckets: list[list[str]] = [[], [], [], []]
    for a in audits:
        x = a.get("overall_score", 0)
        y = a.get("interest_score", 0)
        if x >= X_MID and y >= Y_MID:
            buckets[0].append(a["metadata"]["name"])
        elif x < X_MID and y >= Y_MID:
            buckets[1].append(a["metadata"]["name"])
        elif x >= X_MID and y < Y_MID:
            buckets[2].append(a["metadata"]["name"])
        else:
            buckets[3].append(a["metadata"]["name"])

    ws.cell(row=legend_row, column=10, value="Scatter Quadrants").font = SECTION_FONT
    headers = ["Quadrant", "Count", "Repos"]
    for j, h in enumerate(headers):
        ws.cell(row=legend_row + 1, column=10 + j, value=h).font = SUBHEADER_FONT

    for i, ((name, desc), repos) in enumerate(zip(QUADRANT_NAMES, buckets)):
        row = legend_row + 2 + i
        ws.cell(row=row, column=10, value=f"{name}").font = Font("Calibri", 11, bold=True)
        ws.cell(row=row, column=11, value=len(repos))
        ws.cell(row=row, column=12, value=", ".join(repos[:8]) + ("..." if len(repos) > 8 else ""))


# ═══════════════════════════════════════════════════════════════════════
# Sheet 2: All Repos (Master Table)
# ═══════════════════════════════════════════════════════════════════════


def _build_all_repos(wb: Workbook, data: dict, score_history: dict[str, list[float]] | None = None) -> None:
    ws = _get_or_create_sheet(wb, "All Repos")
    ws.sheet_properties.tabColor = "1565C0"
    _configure_sheet_view(ws, zoom=105, show_grid_lines=True)

    headers = [
        "Repo", "Grade", "Score", "Interest", "Interest Grade", "Interest Tier", "Tier", "Badges",
        "Next Badge", "Language", "Topics", "Commit Pattern", "Bus Factor",
        "Days Since Push", "Commits", "Releases", "Test Files", "Test Framework",
        "LOC", "TODO Density", "PR Merge %", "Comment Ratio",
        "Dep Count", "Libyears", "Stars", "Private", "Flags", "Description",
        "Biggest Drag", "Why This Grade", "Tech Novelty", "Burst", "Ambition", "Storytelling",
        "Created", "Size (KB)", "Trend",
    ]
    for col, h in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=h)
    style_header_row(ws, 1, len(headers))
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(data.get('audits', [])) + 1}"

    audits = sorted(data.get("audits", []), key=lambda a: a.get("overall_score", 0), reverse=True)

    for row, audit in enumerate(audits, 2):
        m = audit.get("metadata", {})
        details = {r["dimension"]: r.get("details", {}) for r in audit.get("analyzer_results", [])}
        act = details.get("activity", {})
        cq = details.get("code_quality", {})
        test = details.get("testing", {})
        dep = details.get("dependencies", {})

        badges = audit.get("badges", [])
        next_badges = audit.get("next_badges", [])
        next_badge_str = next_badges[0]["action"] if next_badges else ""

        doc = details.get("documentation", {})
        values = [
            m.get("name", ""),
            audit.get("grade", "F"),
            round(audit.get("overall_score", 0), 3),
            round(audit.get("interest_score", 0), 3),
            audit.get("interest_grade", "—"),
            audit.get("interest_tier", "—"),
            audit.get("completeness_tier", ""),
            ", ".join(badges[:4]),
            next_badge_str[:50],
            m.get("language") or "—",
            ", ".join(m.get("topics", [])[:8]) or "—",
            act.get("commit_pattern", "—"),
            act.get("bus_factor", "—"),
            act.get("days_since_push", "—"),
            act.get("total_commits", "—"),
            act.get("release_count", "—"),
            test.get("test_file_count", 0),
            test.get("framework", "—"),
            cq.get("total_loc", 0),
            round(cq.get("todo_density_per_1k", 0) or 0, 1),
            round((cq.get("pr_merge_ratio", 0) or 0) * 100, 0),
            round(doc.get("comment_ratio", 0) or 0, 2),
            dep.get("dep_count", "—") if dep.get("dep_count") is not None else "—",
            dep.get("total_libyears", "—"),
            m.get("stars", 0),
            "Yes" if m.get("private") else "No",
            ", ".join(audit.get("flags", [])),
            m.get("description") or "",
        ]

        # Biggest Drag: lowest-scoring completeness dimension
        dim_scores = {
            r["dimension"]: r["score"]
            for r in audit.get("analyzer_results", [])
            if r["dimension"] != "interest"
        }
        if dim_scores:
            worst = min(dim_scores, key=dim_scores.get)
            values.append(f"{worst} ({dim_scores[worst]:.1f})")
        else:
            values.append("—")

        # Why This Grade
        if dim_scores:
            sorted_dims = sorted(dim_scores.items(), key=lambda x: x[1])[:2]
            g = audit.get("grade", "F")
            if len(sorted_dims) >= 2:
                values.append(f"{g}: {sorted_dims[0][0]}={sorted_dims[0][1]:.1f}, {sorted_dims[1][0]}={sorted_dims[1][1]:.1f}")
            else:
                values.append(g)
        else:
            values.append(audit.get("grade", "F"))

        # Interest breakdown
        interest_d = details.get("interest", {})
        values.extend([
            round(interest_d.get("tech_novelty", 0), 2),
            round(interest_d.get("burst_coefficient", 0), 2),
            round(interest_d.get("ambition_score") or 0, 2),
            round(interest_d.get("readme_storytelling", 0), 2),
        ])

        # Created date and repo size
        created = m.get("created_at", "")
        if created and len(created) >= 10:
            created = created[:10]  # Just the date part
        values.extend([created, m.get("size_kb", 0)])

        for col, val in enumerate(values, 1):
            cell = ws.cell(row=row, column=col, value=val)
            style_data_cell(cell)

        # Repo name hyperlink to GitHub
        name_cell = ws.cell(row=row, column=1)
        html_url = m.get("html_url", "")
        if html_url:
            name_cell.hyperlink = html_url
            name_cell.font = Font("Calibri", 10, color=TEAL, underline="single")

        # Grade coloring
        color_grade_cell(ws.cell(row=row, column=2), audit.get("grade", "F"))
        # Tier coloring
        color_tier_cell(ws.cell(row=row, column=7), audit.get("completeness_tier", ""))
        # Pattern coloring
        pattern = act.get("commit_pattern", "")
        if pattern and pattern != "—":
            color_pattern_cell(ws.cell(row=row, column=12), pattern)

        # Sparkline trend (last column)
        if score_history:
            repo_name = m.get("name", "")
            scores = score_history.get(repo_name, [])
            spark = render_sparkline(scores)
            if spark:
                cell = ws.cell(row=row, column=len(headers), value=spark)
                cell.font = SPARKLINE_FONT

    max_row = len(audits) + 1
    apply_zebra_stripes(ws, 2, max_row, len(headers), skip_cols={2, 7})

    # Consistent number formatting
    for row in range(2, max_row + 1):
        ws.cell(row=row, column=3).number_format = '0.000'  # Score
        ws.cell(row=row, column=4).number_format = '0.000'  # Interest

    # DataBar on Score and Interest columns
    if max_row > 1:
        ws.conditional_formatting.add(
            f"C2:C{max_row}",
            DataBarRule(start_type='num', start_value=0, end_type='num', end_value=1, color='166534'),
        )
        ws.conditional_formatting.add(
            f"D2:D{max_row}",
            DataBarRule(start_type='num', start_value=0, end_type='num', end_value=1, color='0EA5E9'),
        )
        ws.conditional_formatting.add(
            f"C2:C{max_row}",
            IconSetRule('3TrafficLights1', 'num', [0, 0.55, 0.7]),
        )

    # Tooltips on key columns
    score_dv = DataValidation(allow_blank=True, prompt="Weighted average of 10 dimensions. See Score Explainer sheet.", promptTitle="Overall Score")
    score_dv.sqref = f"C2:C{max_row}"
    ws.add_data_validation(score_dv)
    interest_dv = DataValidation(allow_blank=True, prompt="How interesting/ambitious (separate from completeness). Based on tech novelty, commit patterns, scope.", promptTitle="Interest Score")
    interest_dv.sqref = f"D2:D{max_row}"
    ws.add_data_validation(interest_dv)
    grade_dv = DataValidation(allow_blank=True, prompt="A (>=85%) B (>=70%) C (>=55%) D (>=35%) F (<35%)", promptTitle="Letter Grade")
    grade_dv.sqref = f"B2:B{max_row}"
    ws.add_data_validation(grade_dv)

    # Summary row (immediately after data, no gap)
    sr = max_row + 1
    ws.cell(row=sr, column=1, value="SUMMARY").font = SUBHEADER_FONT
    ws.cell(row=sr, column=3, value=f"=AVERAGE(C2:C{max_row})").font = SUBHEADER_FONT
    ws.cell(row=sr, column=4, value=f"=AVERAGE(D2:D{max_row})").font = SUBHEADER_FONT

    _add_table(ws, "tblAllRepos", len(headers), max_row)
    auto_width(ws, len(headers), max_row + 2)

    # Compact numeric columns that auto_width made too wide
    ws.column_dimensions[get_column_letter(3)].width = 10  # Score
    ws.column_dimensions[get_column_letter(4)].width = 10  # Interest

    # Wrap text on long-content columns and set appropriate widths
    from openpyxl.styles import Alignment
    desc_col_idx = headers.index("Description") + 1
    topics_col_idx = headers.index("Topics") + 1
    badges_col_idx = headers.index("Badges") + 1
    for col_idx in (desc_col_idx, topics_col_idx, badges_col_idx):
        ws.column_dimensions[get_column_letter(col_idx)].width = 60
        for row in range(2, max_row + 1):
            ws.cell(row=row, column=col_idx).alignment = Alignment(wrap_text=True, vertical='top')


# ═══════════════════════════════════════════════════════════════════════
# Sheet 3: Scoring Heatmap
# ═══════════════════════════════════════════════════════════════════════


def _build_heatmap(wb: Workbook, data: dict) -> None:
    ws = _get_or_create_sheet(wb, "Scoring Heatmap")
    ws.sheet_properties.tabColor = "D97706"
    _configure_sheet_view(ws, zoom=105, show_grid_lines=True)

    dimensions = [
        "readme", "structure", "code_quality", "testing", "cicd",
        "dependencies", "activity", "documentation", "build_readiness",
        "community_profile", "interest",
    ]
    dim_labels = [d.replace("_", " ").title() for d in dimensions]
    headers = ["Repo", "Grade", "Overall"] + dim_labels

    for col, h in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=h)
    style_header_row(ws, 1, len(headers))
    ws.freeze_panes = "B2"

    audits = sorted(data.get("audits", []), key=lambda a: a.get("overall_score", 0), reverse=True)

    for row, audit in enumerate(audits, 2):
        score_map = {r["dimension"]: r["score"] for r in audit.get("analyzer_results", [])}

        ws.cell(row=row, column=1, value=audit["metadata"]["name"])
        style_data_cell(ws.cell(row=row, column=1))

        grade_cell = ws.cell(row=row, column=2, value=audit.get("grade", "F"))
        color_grade_cell(grade_cell, audit.get("grade", "F"))

        ws.cell(row=row, column=3, value=round(audit.get("overall_score", 0), 2))
        style_data_cell(ws.cell(row=row, column=3), "center")

        for i, dim in enumerate(dimensions, 4):
            score = round(score_map.get(dim, 0), 2)
            cell = ws.cell(row=row, column=i, value=score)
            cell.alignment = CENTER
            cell.border = THIN_BORDER

    max_row = len(audits) + 1

    # ColorScaleRule on all dimension columns (cols 3 through end)
    if max_row > 1:
        for col in range(3, len(headers) + 1):
            col_letter = get_column_letter(col)
            ws.conditional_formatting.add(
                f"{col_letter}2:{col_letter}{max_row}",
                ColorScaleRule(
                    start_type='num', start_value=0, start_color=HEATMAP_RED,
                    mid_type='num', mid_value=0.5, mid_color=HEATMAP_AMBER,
                    end_type='num', end_value=1, end_color=HEATMAP_GREEN,
                ),
            )

    auto_width(ws, len(headers), max_row)


# ═══════════════════════════════════════════════════════════════════════
# Sheet 4: Quick Wins
# ═══════════════════════════════════════════════════════════════════════


def _build_quick_wins(wb: Workbook, data: dict) -> None:
    ws = _get_or_create_sheet(wb, "Quick Wins")
    ws.sheet_properties.tabColor = "0891B2"
    _configure_sheet_view(ws, zoom=110, show_grid_lines=True)

    tier_next = {
        "abandoned": ("skeleton", 0.15),
        "skeleton": ("wip", 0.35),
        "wip": ("functional", 0.55),
        "functional": ("shipped", 0.75),
    }

    wins: list[dict] = []
    for audit in data.get("audits", []):
        current_tier = audit.get("completeness_tier", "")
        if current_tier not in tier_next:
            continue
        next_name, threshold = tier_next[current_tier]
        gap = threshold - audit.get("overall_score", 0)
        if gap > 0.20 or gap <= 0:
            continue

        dim_scores = {r["dimension"]: r["score"] for r in audit.get("analyzer_results", [])}
        sorted_dims = sorted(dim_scores.items(), key=lambda x: x[1])
        actions = [f"Improve {d} ({s:.1f})" for d, s in sorted_dims[:3]]

        wins.append({
            "name": audit["metadata"]["name"],
            "grade": audit.get("grade", "F"),
            "tier": current_tier,
            "score": audit.get("overall_score", 0),
            "next_tier": next_name,
            "gap": gap,
            "actions": actions,
            "badges": len(audit.get("badges", [])),
        })

    wins.sort(key=lambda w: w["gap"])

    # Title
    ws.merge_cells("A1:H1")
    ws["A1"].value = f"Quick Wins — {len(wins)} repos near the next tier"
    ws["A1"].font = SECTION_FONT

    if not wins:
        ws.cell(row=3, column=1, value="No repos within striking distance of the next tier.")
        return

    headers = ["Repo", "Grade", "Current", "Score", "Next Tier", "Gap", "Top Actions", "Badges"]
    for col, h in enumerate(headers, 1):
        ws.cell(row=3, column=col, value=h)
    style_header_row(ws, 3, len(headers))
    ws.freeze_panes = "B2"

    for row, win in enumerate(wins, 4):
        ws.cell(row=row, column=1, value=win["name"])
        grade_cell = ws.cell(row=row, column=2, value=win["grade"])
        color_grade_cell(grade_cell, win["grade"])
        tier_cell = ws.cell(row=row, column=3, value=win["tier"])
        color_tier_cell(tier_cell, win["tier"])
        ws.cell(row=row, column=4, value=round(win["score"], 3))
        ws.cell(row=row, column=5, value=win["next_tier"])
        ws.cell(row=row, column=6, value=round(win["gap"], 3))
        ws.cell(row=row, column=7, value="; ".join(win["actions"]))
        ws.cell(row=row, column=8, value=win["badges"])

        for col in range(1, 9):
            style_data_cell(ws.cell(row=row, column=col))

    max_row = len(wins) + 3
    if max_row > 4:
        ws.conditional_formatting.add(
            f"F4:F{max_row}",
            DataBarRule(start_type='num', start_value=0, end_type='num', end_value=0.20, color='0EA5E9'),
        )

    apply_zebra_stripes(ws, 4, max_row, len(headers))
    auto_width(ws, len(headers), max_row)


# ═══════════════════════════════════════════════════════════════════════
# Sheet 5: Badges Dashboard
# ═══════════════════════════════════════════════════════════════════════


def _build_badges(wb: Workbook, data: dict) -> None:
    ws = _get_or_create_sheet(wb, "Badges")
    ws.sheet_properties.tabColor = "7C3AED"
    _configure_sheet_view(ws, zoom=110, show_grid_lines=True)

    # Collect badge stats
    badge_counts: Counter = Counter()
    repo_badge_counts: list[tuple[str, int]] = []

    for audit in data.get("audits", []):
        badges = audit.get("badges", [])
        for b in badges:
            badge_counts[b] += 1
        repo_badge_counts.append((audit["metadata"]["name"], len(badges)))

    total_repos = len(data.get("audits", []))

    # Title
    ws.merge_cells("A1:E1")
    ws["A1"].value = "Badge Dashboard"
    ws["A1"].font = SECTION_FONT

    total_badges = sum(badge_counts.values())
    ws.cell(row=2, column=1, value=f"Total badges earned: {total_badges} across {total_repos} repos")
    ws.cell(row=2, column=1).font = SUBTITLE_FONT

    # Badge distribution table
    headers = ["Badge", "Repos Earned", "% of Portfolio"]
    for col, h in enumerate(headers, 1):
        ws.cell(row=4, column=col, value=h)
    style_header_row(ws, 4, len(headers))
    ws.freeze_panes = "B2"

    for row, (badge, count) in enumerate(badge_counts.most_common(), 5):
        ws.cell(row=row, column=1, value=badge)
        ws.cell(row=row, column=2, value=count)
        ws.cell(row=row, column=3, value=f"{count/total_repos*100:.0f}%")
        for col in range(1, 4):
            style_data_cell(ws.cell(row=row, column=col))

    # Bar chart
    badge_end = 4 + len(badge_counts)
    if badge_counts:
        chart = BarChart()
        chart.type = "bar"
        chart.title = "Badge Distribution"
        chart.style = 10
        chart_data = Reference(ws, min_col=2, min_row=5, max_row=badge_end)
        chart_cats = Reference(ws, min_col=1, min_row=5, max_row=badge_end)
        chart.add_data(chart_data, titles_from_data=False)
        chart.set_categories(chart_cats)
        chart.series[0].graphicalProperties.solidFill = "7C3AED"
        chart.width = 20
        chart.height = max(8, len(badge_counts) * 0.6)
        ws.add_chart(chart, "E4")

    # Achievement board — repos by badge count
    board_row = badge_end + 3
    ws.cell(row=board_row, column=1, value="Achievement Board").font = SECTION_FONT
    board_row += 1
    ws.cell(row=board_row, column=1, value="Repo").font = SUBHEADER_FONT
    ws.cell(row=board_row, column=2, value="Badges").font = SUBHEADER_FONT
    ws.cell(row=board_row, column=1).fill = SUBHEADER_FILL
    ws.cell(row=board_row, column=2).fill = SUBHEADER_FILL

    repo_badge_counts.sort(key=lambda x: x[1], reverse=True)
    for i, (name, count) in enumerate(repo_badge_counts[:20], board_row + 1):
        ws.cell(row=i, column=1, value=name).border = THIN_BORDER
        ws.cell(row=i, column=2, value=count).border = THIN_BORDER

    auto_width(ws, 3, board_row + 21)


# ═══════════════════════════════════════════════════════════════════════
# Sheet 6: Tech Stack
# ═══════════════════════════════════════════════════════════════════════


def _build_tech_stack(wb: Workbook, data: dict) -> None:
    tech_stack = data.get("tech_stack", {})
    if not tech_stack:
        return

    ws = _get_or_create_sheet(wb, "Tech Stack")
    ws.sheet_properties.tabColor = "4A148C"
    _configure_sheet_view(ws, zoom=110, show_grid_lines=True)

    ws.merge_cells("A1:E1")
    ws["A1"].value = "Technology Stack"
    ws["A1"].font = SECTION_FONT

    headers = ["Language", "Repos", "Bytes", "Avg Score", "Proficiency"]
    for col, h in enumerate(headers, 1):
        ws.cell(row=3, column=col, value=h)
    style_header_row(ws, 3, len(headers))
    ws.freeze_panes = "B2"

    for row, (lang, info) in enumerate(tech_stack.items(), 4):
        ws.cell(row=row, column=1, value=lang)
        ws.cell(row=row, column=2, value=info.get("repos", 0))
        ws.cell(row=row, column=3, value=info.get("bytes", 0))
        ws.cell(row=row, column=4, value=info.get("avg_score", 0))
        ws.cell(row=row, column=5, value=info.get("proficiency", 0))
        for col in range(1, 6):
            style_data_cell(ws.cell(row=row, column=col))

    max_row = 3 + len(tech_stack)
    if len(tech_stack) > 1:
        chart = BarChart()
        chart.type = "col"
        chart.title = "Language Proficiency (bytes x quality)"
        chart.style = 10
        chart_data = Reference(ws, min_col=5, min_row=3, max_row=max_row)
        chart_cats = Reference(ws, min_col=1, min_row=4, max_row=max_row)
        chart.add_data(chart_data, titles_from_data=True)
        chart.set_categories(chart_cats)
        chart.width = 20
        chart.height = 12
        ws.add_chart(chart, "G3")

    # Best work
    best_work = data.get("best_work", [])
    if best_work:
        bw_row = max_row + 3
        ws.cell(row=bw_row, column=1, value="Best Work (Top 5)").font = SECTION_FONT
        for i, name in enumerate(best_work, bw_row + 1):
            ws.cell(row=i, column=1, value=f"{i - bw_row}. {name}").border = THIN_BORDER

    auto_width(ws, 5, max_row + 10)


# ═══════════════════════════════════════════════════════════════════════
# Sheet 7: Trends
# ═══════════════════════════════════════════════════════════════════════


def _build_trends(wb: Workbook, data: dict, trend_data: list[dict] | None = None) -> None:
    ws = _get_or_create_sheet(wb, "Trends")
    ws.sheet_properties.tabColor = "311B92"
    _configure_sheet_view(ws, zoom=110, show_grid_lines=True)
    ws.freeze_panes = "B4"

    ws.merge_cells("A1:F1")
    ws["A1"].value = "Portfolio Trends"
    ws["A1"].font = SECTION_FONT

    if not trend_data or len(trend_data) < 2:
        ws.cell(row=3, column=1, value="Run more audits to see trends (need 2+ historical runs)")
        ws.cell(row=3, column=1).font = SUBTITLE_FONT
        return

    ws.cell(row=3, column=1, value="Date").font = SUBHEADER_FONT
    ws.cell(row=4, column=1, value="Avg Score").font = SUBHEADER_FONT
    ws.cell(row=5, column=1, value="Repos").font = SUBHEADER_FONT
    for col, run in enumerate(trend_data, 2):
        ws.cell(row=3, column=col, value=run["date"]).border = THIN_BORDER
        ws.cell(row=4, column=col, value=run["average_score"]).border = THIN_BORDER
        ws.cell(row=5, column=col, value=run["repos_audited"]).border = THIN_BORDER

    row = 7
    ws.cell(row=row, column=1, value="Tier").font = SUBHEADER_FONT
    for i, tier in enumerate(TIER_ORDER):
        ws.cell(row=row + 1 + i, column=1, value=tier.capitalize())
        for col, run in enumerate(trend_data, 2):
            ws.cell(row=row + 1 + i, column=col, value=run.get("tier_distribution", {}).get(tier, 0))

    auto_width(ws, len(trend_data) + 1, 15)


# ═══════════════════════════════════════════════════════════════════════
# Sheet 8: Tier Breakdown
# ═══════════════════════════════════════════════════════════════════════


def _build_tier_breakdown(wb: Workbook, data: dict) -> None:
    ws = _get_or_create_sheet(wb, "Tier Breakdown")
    ws.sheet_properties.tabColor = "166534"
    _configure_sheet_view(ws, zoom=105, show_grid_lines=True)
    ws.freeze_panes = "B2"

    from openpyxl.styles import Font as XFont

    audits_by_tier: dict[str, list] = {}
    for a in data.get("audits", []):
        audits_by_tier.setdefault(a.get("completeness_tier", ""), []).append(a)

    current_row = 1
    for tier in TIER_ORDER:
        tier_audits = audits_by_tier.get(tier, [])
        if not tier_audits:
            continue
        tier_audits.sort(key=lambda a: a.get("overall_score", 0), reverse=True)

        from src.excel_styles import TIER_FILLS
        ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=6)
        h = ws.cell(row=current_row, column=1, value=f"{tier.upper()} ({len(tier_audits)} repos)")
        h.font = XFont(bold=True, size=13, color=WHITE)
        h.fill = TIER_FILLS.get(tier)
        h.alignment = CENTER
        current_row += 1

        cols = ["Repo", "Grade", "Score", "Language", "Badges", "Description"]
        for col, ch in enumerate(cols, 1):
            ws.cell(row=current_row, column=col, value=ch)
        style_header_row(ws, current_row, len(cols))
        current_row += 1

        for audit in tier_audits:
            m = audit["metadata"]
            ws.cell(row=current_row, column=1, value=m["name"])
            g_cell = ws.cell(row=current_row, column=2, value=audit.get("grade", "F"))
            color_grade_cell(g_cell, audit.get("grade", "F"))
            ws.cell(row=current_row, column=3, value=round(audit.get("overall_score", 0), 2))
            ws.cell(row=current_row, column=4, value=m.get("language") or "—")
            ws.cell(row=current_row, column=5, value=len(audit.get("badges", [])))
            ws.cell(row=current_row, column=6, value=(m.get("description") or "")[:50])
            for col in range(1, 7):
                style_data_cell(ws.cell(row=current_row, column=col))
            current_row += 1

        current_row += 2

    auto_width(ws, 6, current_row)


# ═══════════════════════════════════════════════════════════════════════
# Sheet 9: Activity
# ═══════════════════════════════════════════════════════════════════════


def _build_activity(wb: Workbook, data: dict) -> None:
    ws = _get_or_create_sheet(wb, "Activity")
    ws.sheet_properties.tabColor = "6A1B9A"
    _configure_sheet_view(ws, zoom=105, show_grid_lines=True)

    headers = [
        "Repo", "Commit Pattern", "Days Since Push", "Total Commits",
        "Recent 3mo", "Bus Factor", "Release Count", "Activity Score", "Tier",
    ]
    for col, h in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=h)
    style_header_row(ws, 1, len(headers))
    ws.freeze_panes = "B2"

    audits = sorted(
        data.get("audits", []),
        key=lambda a: next(
            (r.get("details", {}).get("days_since_push", 9999)
             for r in a.get("analyzer_results", []) if r["dimension"] == "activity"),
            9999,
        ),
    )

    for row, audit in enumerate(audits, 2):
        details = {r["dimension"]: r.get("details", {}) for r in audit.get("analyzer_results", [])}
        scores = {r["dimension"]: r["score"] for r in audit.get("analyzer_results", [])}
        act = details.get("activity", {})

        pattern = act.get("commit_pattern", "—")
        values = [
            audit["metadata"]["name"],
            pattern,
            act.get("days_since_push", "—"),
            act.get("total_commits", "—"),
            act.get("recent_3mo_commits", "—"),
            act.get("bus_factor", "—"),
            act.get("release_count", "—"),
            round(scores.get("activity", 0), 2),
            audit.get("completeness_tier", ""),
        ]
        for col, val in enumerate(values, 1):
            cell = ws.cell(row=row, column=col, value=val)
            style_data_cell(cell)

        if pattern and pattern != "—":
            color_pattern_cell(ws.cell(row=row, column=2), pattern)

    max_row = len(audits) + 1
    apply_zebra_stripes(ws, 2, max_row, len(headers))
    auto_width(ws, len(headers), max_row)


# ═══════════════════════════════════════════════════════════════════════
# Sheet 10: Registry Reconciliation
# ═══════════════════════════════════════════════════════════════════════


def _build_reconciliation(wb: Workbook, data: dict) -> None:
    recon = data.get("reconciliation")
    if not recon:
        return

    ws = _get_or_create_sheet(wb, "Registry")
    ws.sheet_properties.tabColor = "00695C"

    row = 1
    ws.merge_cells("A1:E1")
    ws["A1"].value = f"Registry Reconciliation ({recon.get('registry_total', 0)} projects)"
    ws["A1"].font = SECTION_FONT

    # Matched
    matched = recon.get("matched", [])
    if matched:
        row = 3
        ws.cell(row=row, column=1, value=f"Matched ({len(matched)})").font = SUBHEADER_FONT
        row += 1
        for col, h in enumerate(["GitHub", "Registry", "Status", "Tier", "Score"], 1):
            ws.cell(row=row, column=col, value=h)
        style_header_row(ws, row, 5)
        row += 1
        for m in matched:
            ws.cell(row=row, column=1, value=m.get("github_name", ""))
            ws.cell(row=row, column=2, value=m.get("registry_name", ""))
            ws.cell(row=row, column=3, value=m.get("registry_status", ""))
            t_cell = ws.cell(row=row, column=4, value=m.get("audit_tier", ""))
            color_tier_cell(t_cell, m.get("audit_tier", ""))
            ws.cell(row=row, column=5, value=m.get("score", 0))
            for col in range(1, 6):
                style_data_cell(ws.cell(row=row, column=col))
            row += 1

    # Unmatched
    unmatched_gh = recon.get("on_github_not_registry", [])
    if unmatched_gh:
        row += 2
        ws.cell(row=row, column=1, value=f"On GitHub, NOT in Registry ({len(unmatched_gh)})").font = SUBHEADER_FONT
        row += 1
        for name in unmatched_gh:
            ws.cell(row=row, column=1, value=name).border = THIN_BORDER
            row += 1

    unmatched_reg = recon.get("in_registry_not_github", [])
    if unmatched_reg:
        row += 1
        ws.cell(row=row, column=1, value=f"In Registry, NOT on GitHub ({len(unmatched_reg)})").font = SUBHEADER_FONT
        row += 1
        for name in unmatched_reg:
            ws.cell(row=row, column=1, value=name).border = THIN_BORDER
            row += 1

    auto_width(ws, 5, row)


# ═══════════════════════════════════════════════════════════════════════
# Main export
# ═══════════════════════════════════════════════════════════════════════


def _build_score_explainer(wb: Workbook) -> None:
    """Static reference sheet explaining the scoring system."""
    from src.scorer import COMPLETENESS_TIERS, GRADE_THRESHOLDS, WEIGHTS

    ws = _get_or_create_sheet(wb, "Score Explainer")
    ws.sheet_properties.tabColor = "37474F"

    ws.merge_cells("A1:D1")
    ws["A1"].value = "Scoring System Reference"
    ws["A1"].font = TITLE_FONT

    DIMENSION_INFO = {
        "testing": ("Test directories, framework, test file count", "Add test/ with pytest/jest/vitest configured"),
        "code_quality": ("Entry points, TODO density, types, commit quality", "Add main entry point, reduce TODOs"),
        "activity": ("Push recency, commit count, releases, bus factor", "Push regularly, tag releases"),
        "readme": ("Exists, description, install instructions, examples", "Add usage section with code blocks"),
        "structure": (".gitignore, source dirs, config files, LICENSE", "Add .gitignore + LICENSE + package manifest"),
        "cicd": ("GitHub Actions, CI configs, build scripts", "Add .github/workflows/ci.yml"),
        "dependencies": ("Manifest + lockfile, dep count, libyears", "Add lockfile alongside manifest"),
        "build_readiness": ("Docker, Makefile, .env.example, deploy configs", "Add Dockerfile or Makefile"),
        "community_profile": ("LICENSE, CONTRIBUTING, CODE_OF_CONDUCT", "Add CONTRIBUTING.md"),
        "documentation": ("docs/ dir, CHANGELOG, comment density", "Add docs/ folder or CHANGELOG.md"),
    }

    ws.cell(row=3, column=1, value="Dimension Weights").font = SECTION_FONT
    for col, h in enumerate(["Dimension", "Weight", "What It Measures", "How to Improve"], 1):
        ws.cell(row=4, column=col, value=h)
    style_header_row(ws, 4, 4)
    ws.freeze_panes = "A5"

    row = 5
    for dim, weight in sorted(WEIGHTS.items(), key=lambda x: x[1], reverse=True):
        desc, improve = DIMENSION_INFO.get(dim, ("", ""))
        ws.cell(row=row, column=1, value=dim)
        ws.cell(row=row, column=2, value=f"{weight:.0%}")
        ws.cell(row=row, column=3, value=desc)
        ws.cell(row=row, column=4, value=improve)
        for c in range(1, 5):
            style_data_cell(ws.cell(row=row, column=c))
        row += 1

    row += 1
    ws.cell(row=row, column=1, value="Grade Thresholds").font = SECTION_FONT
    row += 1
    for threshold, g in GRADE_THRESHOLDS:
        ws.cell(row=row, column=1, value=g)
        ws.cell(row=row, column=2, value=f">= {threshold:.0%}")
        color_grade_cell(ws.cell(row=row, column=1), g)
        row += 1

    row += 1
    ws.cell(row=row, column=1, value="Tier Thresholds").font = SECTION_FONT
    row += 1
    for tier_name, threshold in COMPLETENESS_TIERS:
        ws.cell(row=row, column=1, value=tier_name.capitalize())
        ws.cell(row=row, column=2, value=f">= {threshold:.0%}")
        color_tier_cell(ws.cell(row=row, column=1), tier_name)
        row += 1

    auto_width(ws, 4, row)


# ── Effort map for action items
EFFORT_MAP = {
    "readme": "Low", "structure": "Low", "cicd": "Low",
    "documentation": "Low", "community_profile": "Low",
    "dependencies": "Low", "build_readiness": "Med",
    "testing": "Med", "code_quality": "Med", "activity": "High",
}

TIER_NEXT = {
    "abandoned": ("skeleton", 0.15),
    "skeleton": ("wip", 0.35),
    "wip": ("functional", 0.55),
    "functional": ("shipped", 0.75),
}


def _collect_all_actions(data: dict) -> list[dict]:
    """Collect and prioritize actions from audit data."""
    actions: list[dict] = []
    for audit in data.get("audits", []):
        tier = audit.get("completeness_tier", "")
        if tier not in TIER_NEXT:
            continue
        next_tier, threshold = TIER_NEXT[tier]
        gap = threshold - audit.get("overall_score", 0)
        if gap <= 0:
            continue

        dim_scores = {
            r["dimension"]: r["score"]
            for r in audit.get("analyzer_results", [])
            if r["dimension"] != "interest"
        }
        for dim, score in sorted(dim_scores.items(), key=lambda x: x[1])[:2]:
            actions.append({
                "repo": audit["metadata"]["name"],
                "action": f"Improve {dim} (currently {score:.1f})",
                "impact": f"Close {gap:.3f} gap to {next_tier}",
                "effort": EFFORT_MAP.get(dim, "Med"),
                "dimension": dim,
                "gap": gap,
            })

        for badge_s in audit.get("next_badges", [])[:1]:
            actions.append({
                "repo": audit["metadata"]["name"],
                "action": badge_s.get("action", ""),
                "impact": f"Earn '{badge_s.get('badge', '')}' badge",
                "effort": "Low" if badge_s.get("gap", 1) < 0.3 else "Med",
                "dimension": "badges",
                "gap": badge_s.get("gap", 1.0),
            })

    effort_order = {"Low": 0, "Med": 1, "High": 2}
    actions.sort(key=lambda a: (effort_order.get(a["effort"], 1), a["gap"]))

    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for a in actions:
        key = (a["repo"], a["dimension"])
        if key not in seen:
            seen.add(key)
            unique.append(a)
    return unique


def _build_action_items(wb: Workbook, data: dict) -> None:
    """Prioritized action item list with weekly sprint."""
    ws = _get_or_create_sheet(wb, "Action Items")
    ws.sheet_properties.tabColor = "E65100"
    _configure_sheet_view(ws, zoom=110, show_grid_lines=True)

    actions = _collect_all_actions(data)

    ws.merge_cells("A1:F1")
    ws["A1"].value = f"Action Items — {len(actions)} prioritized improvements"
    ws["A1"].font = SECTION_FONT
    ws.freeze_panes = "A5"

    sprint = [a for a in actions if a["effort"] == "Low"][:5]
    headers = ["#", "Repo", "Action", "Impact", "Effort", "Dimension"]

    if sprint:
        ws.cell(row=3, column=1, value="Weekly Sprint (Top 5 Low-Effort)").font = SECTION_FONT
        for col, h in enumerate(headers, 1):
            ws.cell(row=4, column=col, value=h)
        style_header_row(ws, 4, len(headers))
        for i, item in enumerate(sprint, 5):
            for col, val in enumerate([i - 4, item["repo"], item["action"], item["impact"], item["effort"], item["dimension"]], 1):
                cell = ws.cell(row=i, column=col, value=val)
                style_data_cell(cell)

    full_start = len(sprint) + 7
    ws.cell(row=full_start, column=1, value="All Actions (Prioritized)").font = SECTION_FONT
    full_start += 1
    for col, h in enumerate(headers, 1):
        ws.cell(row=full_start, column=col, value=h)
    style_header_row(ws, full_start, len(headers))

    for i, item in enumerate(actions[:100], full_start + 1):
        for col, val in enumerate([i - full_start, item["repo"], item["action"], item["impact"], item["effort"], item["dimension"]], 1):
            cell = ws.cell(row=i, column=col, value=val)
            style_data_cell(cell)

    final_row = full_start + min(len(actions), 100)
    apply_zebra_stripes(ws, full_start + 1, final_row, len(headers))
    if actions:
        _set_autofilter(ws, len(headers), final_row, start_row=full_start)
    auto_width(ws, len(headers), final_row + 1)


def _build_navigation(
    wb: Workbook,
    data: dict,
    *,
    excel_mode: str = "standard",
    portfolio_profile: str = "default",
    collection: str | None = None,
) -> None:
    """Navigation index as the first sheet."""
    ws = wb["Index"] if "Index" in wb.sheetnames else wb.create_sheet("Index", 0)
    _clear_worksheet(ws)
    ws.sheet_properties.tabColor = "263238"
    _configure_sheet_view(ws, zoom=125, show_grid_lines=False)
    ws.freeze_panes = "A12"

    ws.merge_cells("A1:G1")
    ws["A1"].value = f"GitHub Portfolio Audit: {data['username']}"
    ws["A1"].font = TITLE_FONT
    ws["A1"].alignment = CENTER

    ws.merge_cells("A2:G2")
    ws["A2"].value = f"Last updated: {data['generated_at'][:10]} | {data['repos_audited']} repos | Grade: {data.get('portfolio_grade', '?')}"
    ws["A2"].font = SUBTITLE_FONT
    ws["A2"].alignment = CENTER
    _write_instruction_banner(
        ws,
        3,
        7,
        "Use this workbook in order: Dashboard for the brief, Run Changes for movement, Review Queue for action, Repo Detail for one-repo context, and Executive Summary for a shareable recap.",
    )
    next_mode, watch_strategy, watch_decision = _operator_watch_values(data)
    what_changed, why_it_matters, next_action = _operator_handoff_values(data)
    (
        follow_through,
        follow_through_checkpoint,
        follow_through_escalation,
        follow_through_hotspot,
        _follow_through_escalation_hotspot,
    ) = _operator_follow_through_details(data)

    ws.cell(row=4, column=1, value="Start Here").font = SECTION_FONT
    ws.cell(row=5, column=1, value="Workbook Mode").font = SUBHEADER_FONT
    ws.cell(row=5, column=2, value=excel_mode)
    ws.cell(row=5, column=3, value="Profile").font = SUBHEADER_FONT
    ws.cell(row=5, column=4, value=portfolio_profile)
    ws.cell(row=6, column=1, value="Collection").font = SUBHEADER_FONT
    ws.cell(row=6, column=2, value=collection or "all")
    ws.cell(row=6, column=3, value="Source Run").font = SUBHEADER_FONT
    ws.cell(row=6, column=4, value=(data.get("operator_summary") or {}).get("source_run_id", ""))
    ws.cell(row=7, column=1, value="Report Reference").font = SUBHEADER_FONT
    ws.cell(row=7, column=2, value=(data.get("operator_summary") or {}).get("report_reference", ""))
    ws.cell(row=7, column=3, value="Operator Headline").font = SUBHEADER_FONT
    ws.cell(row=7, column=4, value=(data.get("operator_summary") or {}).get("headline", ""))
    ws.cell(row=8, column=1, value="Next Run").font = SUBHEADER_FONT
    ws.cell(row=8, column=2, value=next_mode)
    ws.cell(row=8, column=3, value="Watch Strategy").font = SUBHEADER_FONT
    ws.cell(row=8, column=4, value=watch_strategy)
    ws.merge_cells("A9:G9")
    ws["A9"] = watch_decision
    ws["A9"].font = SUBTITLE_FONT
    ws["A9"].alignment = WRAP
    ws.merge_cells("A10:G10")
    ws["A10"] = f"What changed: {what_changed}"
    ws["A10"].font = SUBTITLE_FONT
    ws["A10"].alignment = WRAP
    ws.merge_cells("A11:G11")
    ws["A11"] = f"Why it matters: {why_it_matters}"
    ws["A11"].font = SUBTITLE_FONT
    ws["A11"].alignment = WRAP
    ws.merge_cells("A12:G12")
    ws["A12"] = f"What to do next: {next_action}"
    ws["A12"].font = SUBTITLE_FONT
    ws["A12"].alignment = WRAP
    ws.merge_cells("A13:G13")
    ws["A13"] = f"Follow-through: {follow_through}"
    ws["A13"].font = SUBTITLE_FONT
    ws["A13"].alignment = WRAP
    ws.merge_cells("A14:G14")
    ws["A14"] = f"Escalation: {follow_through_escalation}"
    ws["A14"].font = SUBTITLE_FONT
    ws["A14"].alignment = WRAP
    ws.merge_cells("A15:G15")
    ws["A15"] = "Start with Dashboard for the portfolio brief, move to Review Queue for action, then drill into Portfolio Explorer and Executive Summary for detail."
    ws["A15"].font = SUBTITLE_FONT
    ws["A15"].alignment = WRAP
    ws.merge_cells("A16:G16")
    ws["A16"] = "Operating rules: standard mode is the default path, visible sheets stay filter-based, and hidden Data_* sheets remain the workbook contract. Advanced sheets are hidden by default; use Excel Unhide when you need deeper diagnostics."
    ws["A16"].font = SUBTITLE_FONT
    ws["A16"].alignment = WRAP

    groups = [
        (
            "Daily Triage",
            18,
            1,
            [
                ("Dashboard", "Start here for the big-picture health view and top attention items."),
                ("Review Queue", "Use this for blocked, urgent, ready, and safe-to-defer review work."),
                ("Run Changes", "See what changed since the last run before you decide where to spend attention."),
                ("Campaigns", "Check managed campaign state, reopen/closure context, and drift."),
                ("Governance Controls", "Review governed controls, approval posture, and rollback visibility."),
                ("Writeback Audit", "See what writeback changed and what is reversible."),
            ],
        ),
        (
            "Portfolio Analysis",
            17,
            5,
            [
                ("Portfolio Explorer", "Rank repos, compare score quality, and drill from summary into raw facts."),
                ("Repo Detail", "Select one repo and get a single-page briefing on score, risks, trend, and next action."),
                ("By Lens", "Compare the portfolio by ship readiness, momentum, security, and fit."),
                ("By Collection", "Understand collection-level leaders and concentration."),
                ("Trend Summary", "See portfolio-wide movement and repo trendlines over time."),
                ("All Repos", "Scan the full inventory with grades, tiers, and supporting evidence."),
            ],
        ),
        (
            "Executive Readout",
            27,
            1,
            [
                ("Executive Summary", "Readable leadership summary with what changed and what matters this week."),
                ("Print Pack", "Print-friendly handoff with risks, opportunities, and operator counts in plain language."),
            ],
        ),
        (
            "Deep Diagnostics",
            27,
            5,
            [
                ("Security", "Raw security posture, secrets, and dangerous-file findings."),
                ("Security Controls", "Control coverage and rollout detail by repo."),
                ("Supply Chain", "Dependency health, scorecard signals, and provider coverage."),
                ("Scoring Heatmap", "Dimension-by-dimension matrix for detailed score inspection."),
                ("Hotspots", "Highest-severity risks and opportunities across the portfolio."),
                ("Review History", "Recurring review history and decision-state ledger."),
                ("Governance Audit", "Approval, drift, and rollback evidence summary."),
                ("Score Explainer", "How scores, grades, and tiers are computed."),
                ("Action Items", "Prioritized improvement ideas with effort context."),
            ],
        ),
    ]

    for section, start_row, start_col, sheets in groups:
        ws.cell(row=start_row, column=start_col, value=section).font = SECTION_FONT
        header_row = start_row + 1
        for offset, header in enumerate(["Sheet", "Use This When", "Go"], 0):
            cell = ws.cell(row=header_row, column=start_col + offset, value=header)
            cell.fill = SUBHEADER_FILL
            cell.font = SUBHEADER_FONT
            cell.alignment = CENTER
            cell.border = THIN_BORDER
        row = header_row + 1
        for name, desc in sheets:
            if name not in wb.sheetnames:
                continue
            sheet_cell = ws.cell(row=row, column=start_col, value=name)
            sheet_cell.hyperlink = Hyperlink(
                ref=sheet_cell.coordinate,
                location=_sheet_location(name),
                display=str(name),
            )
            sheet_cell.font = Font("Calibri", 11, bold=True, color=TEAL, underline="single")
            sheet_cell.border = THIN_BORDER
            sheet_cell.alignment = LEFT
            style_data_cell(ws.cell(row=row, column=start_col + 1, value=desc), "left")
            go_cell = ws.cell(row=row, column=start_col + 2, value="Open")
            go_cell.hyperlink = Hyperlink(
                ref=go_cell.coordinate,
                location=_sheet_location(name),
                display="Open",
            )
            go_cell.font = Font("Calibri", 10, bold=True, color=TEAL, underline="single")
            go_cell.border = THIN_BORDER
            go_cell.alignment = CENTER
            row += 1

    auto_width(ws, 7, 35)


# ═══════════════════════════════════════════════════════════════════════
# Repo Profiles (Radar Charts)
# ═══════════════════════════════════════════════════════════════════════


RADAR_DIMS = ["readme", "structure", "code_quality", "testing", "cicd",
              "dependencies", "activity", "documentation", "build_readiness", "community_profile"]
RADAR_LABELS = ["README", "Structure", "Code Quality", "Testing", "CI/CD",
                "Deps", "Activity", "Docs", "Build Ready", "Community"]


def _build_repo_profiles(wb: Workbook, data: dict) -> None:
    ws = _get_or_create_sheet(wb, "Repo Profiles")
    ws.sheet_properties.tabColor = "7C3AED"
    _configure_sheet_view(ws, zoom=105, show_grid_lines=True)
    ws.freeze_panes = "B2"

    audits = sorted(data.get("audits", []), key=lambda a: a.get("overall_score", 0), reverse=True)[:20]
    if len(audits) < 2:
        return

    # Write dimension labels in column A
    for i, label in enumerate(RADAR_LABELS):
        ws.cell(row=i + 2, column=1, value=label)

    # Write scores for each repo
    for col_idx, audit in enumerate(audits):
        dim_scores = {r["dimension"]: r["score"] for r in audit.get("analyzer_results", [])}
        ws.cell(row=1, column=col_idx + 2, value=audit["metadata"]["name"])
        for row_idx, dim in enumerate(RADAR_DIMS):
            ws.cell(row=row_idx + 2, column=col_idx + 2, value=round(dim_scores.get(dim, 0), 2))

    # Create radar charts (4 repos per chart)
    labels = Reference(ws, min_col=1, min_row=2, max_row=len(RADAR_DIMS) + 1)
    chart_row = len(RADAR_DIMS) + 4

    for batch_start in range(0, min(len(audits), 20), 4):
        batch_end = min(batch_start + 4, len(audits))
        chart = RadarChart()
        chart.type = "filled"
        chart.style = 26
        chart.title = f"Repos {batch_start + 1}-{batch_end}"
        chart.y_axis.delete = True

        chart_data = Reference(ws, min_col=batch_start + 2, max_col=batch_end + 1,
                               min_row=1, max_row=len(RADAR_DIMS) + 1)
        chart.add_data(chart_data, titles_from_data=True)
        chart.set_categories(labels)
        chart.width = 18
        chart.height = 14

        col_letter = "A" if (batch_start // 4) % 2 == 0 else "K"
        ws.add_chart(chart, f"{col_letter}{chart_row}")
        if (batch_start // 4) % 2 == 1:
            chart_row += 18


# ═══════════════════════════════════════════════════════════════════════
# Security Sheet
# ═══════════════════════════════════════════════════════════════════════


def _build_security(wb: Workbook, data: dict) -> None:
    ws = _get_or_create_sheet(wb, "Security")
    ws.sheet_properties.tabColor = "991B1B"
    _configure_sheet_view(ws, zoom=105, show_grid_lines=True)

    headers = ["Repo", "Score", "Secrets", "Dangerous Files", "SECURITY.md", "Dependabot", "GitHub", "Findings"]
    for col, h in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=h)
    style_header_row(ws, 1, len(headers))
    ws.freeze_panes = "B2"

    audits = sorted(data.get("audits", []), key=lambda a: a.get("security_posture", {}).get("score", 1.0))

    for row, audit in enumerate(audits, 2):
        posture = audit.get("security_posture", {})
        local = posture.get("local", {})
        github = posture.get("github", {})
        m = audit.get("metadata", {})

        values = [
            m.get("name", ""),
            round(posture.get("score", 0), 2),
            local.get("secrets_found", posture.get("secrets_found", 0)),
            ", ".join(str(f) for f in local.get("dangerous_files", posture.get("dangerous_files", []))[:3]),
            "Yes" if posture.get("has_security_md") else "No",
            "Yes" if posture.get("has_dependabot") else "No",
            "Yes" if github.get("provider_available") else "No",
            "; ".join(posture.get("evidence", [])[:3]),
        ]
        for col, val in enumerate(values, 1):
            cell = ws.cell(row=row, column=col, value=val)
            style_data_cell(cell)

    max_row = len(audits) + 1
    if max_row > 1:
        ws.conditional_formatting.add(
            f"B2:B{max_row}",
            ColorScaleRule(start_type='num', start_value=0, start_color=HEATMAP_RED,
                           mid_type='num', mid_value=0.5, mid_color=HEATMAP_AMBER,
                           end_type='num', end_value=1, end_color=HEATMAP_GREEN),
        )
        ws.conditional_formatting.add(
            f"B2:B{max_row}",
            IconSetRule('3TrafficLights1', 'num', [0, 0.4, 0.7]),
        )

    apply_zebra_stripes(ws, 2, max_row, len(headers))
    _add_table(ws, "tblSecurity", len(headers), max_row)
    auto_width(ws, len(headers), max_row)


# ═══════════════════════════════════════════════════════════════════════
# Changes Since Last Audit (Diff Sheet)
# ═══════════════════════════════════════════════════════════════════════


def _build_changes(wb: Workbook, data: dict, diff_data: dict | None) -> None:
    if not diff_data:
        return

    ws = _get_or_create_sheet(wb, "Changes")
    ws.sheet_properties.tabColor = "0891B2"

    # Title
    ws.merge_cells("A1:F1")
    ws["A1"].value = "Changes Since Last Audit"
    ws["A1"].font = TITLE_FONT

    # KPI summary
    tier_changes = diff_data.get("tier_changes", [])
    promos = [c for c in tier_changes if c.get("direction") == "promotion"]
    demos = [c for c in tier_changes if c.get("direction") == "demotion"]
    avg_delta = diff_data.get("average_score_delta", 0)

    ws.cell(row=3, column=1, value="Promotions").font = SUBHEADER_FONT
    ws.cell(row=3, column=2, value=len(promos))
    ws.cell(row=3, column=3, value="Demotions").font = SUBHEADER_FONT
    ws.cell(row=3, column=4, value=len(demos))
    ws.cell(row=3, column=5, value="Avg Score Delta").font = SUBHEADER_FONT
    ws.cell(row=3, column=6, value=round(avg_delta, 4))

    # Tier changes table
    row = 5
    if tier_changes:
        ws.cell(row=row, column=1, value="Tier Changes").font = SECTION_FONT
        row += 1
        for col, h in enumerate(["Repo", "Old Tier", "New Tier", "Old Score", "New Score", "Direction"], 1):
            ws.cell(row=row, column=col, value=h)
        style_header_row(ws, row, 6)
        row += 1

        for change in tier_changes:
            ws.cell(row=row, column=1, value=change.get("name", ""))
            ws.cell(row=row, column=2, value=change.get("old_tier", ""))
            ws.cell(row=row, column=3, value=change.get("new_tier", ""))
            ws.cell(row=row, column=4, value=round(change.get("old_score", 0), 3))
            ws.cell(row=row, column=5, value=round(change.get("new_score", 0), 3))
            direction = change.get("direction", "")
            cell = ws.cell(row=row, column=6, value=direction)
            if direction == "promotion":
                cell.font = Font("Calibri", 10, bold=True, color="166534")
            elif direction == "demotion":
                cell.font = Font("Calibri", 10, bold=True, color="991B1B")
            row += 1

    # Significant score changes
    score_changes = [c for c in diff_data.get("score_changes", []) if abs(c.get("delta", 0)) > 0.05]
    if score_changes:
        row += 2
        ws.cell(row=row, column=1, value="Significant Score Changes").font = SECTION_FONT
        row += 1
        for col, h in enumerate(["Repo", "Old Score", "New Score", "Delta"], 1):
            ws.cell(row=row, column=col, value=h)
        style_header_row(ws, row, 4)
        row += 1

        for change in sorted(score_changes, key=lambda c: c.get("delta", 0), reverse=True):
            ws.cell(row=row, column=1, value=change.get("name", ""))
            ws.cell(row=row, column=2, value=round(change.get("old_score", 0), 3))
            ws.cell(row=row, column=3, value=round(change.get("new_score", 0), 3))
            delta = change.get("delta", 0)
            cell = ws.cell(row=row, column=4, value=round(delta, 4))
            cell.font = Font("Calibri", 10, bold=True, color="166534" if delta > 0 else "991B1B")
            row += 1

    # Material changes from the report
    material = data.get("material_changes", [])
    if material:
        row += 2
        ws.cell(row=row, column=1, value="Material Changes").font = SECTION_FONT
        row += 1
        for col, h in enumerate(["Repo", "Type", "Severity", "Title"], 1):
            ws.cell(row=row, column=col, value=h)
        style_header_row(ws, row, 4)
        row += 1

        # Group by type, show up to 30 per type to avoid sheet bloat
        by_type: dict[str, list] = {}
        for m in material:
            by_type.setdefault(m.get("change_type", "other"), []).append(m)

        for change_type in sorted(by_type):
            items = by_type[change_type]
            for item in items[:30]:
                ws.cell(row=row, column=1, value=item.get("repo", ""))
                ws.cell(row=row, column=2, value=change_type)
                severity = item.get("severity", "")
                cell = ws.cell(row=row, column=3, value=severity)
                if severity == "high":
                    cell.font = Font("Calibri", 10, bold=True, color="991B1B")
                elif severity == "medium":
                    cell.font = Font("Calibri", 10, color="92400E")
                ws.cell(row=row, column=4, value=item.get("title", ""))
                row += 1

    auto_width(ws, 6, row)


# ═══════════════════════════════════════════════════════════════════════
# Bubble Chart helper for Dashboard
# ═══════════════════════════════════════════════════════════════════════


def _build_bubble_on_dashboard(ws, data: dict) -> None:
    """Add a bubble chart: x=completeness, y=interest, size=LOC."""
    audits = data.get("audits", [])
    if len(audits) < 2:
        return

    # Write bubble data to spare columns (cols 20-22)
    bcol_x, bcol_y, bcol_z = 20, 21, 22
    data_start = 10

    for i, audit in enumerate(audits):
        row = data_start + i
        cq = next((r.get("details", {}) for r in audit.get("analyzer_results", []) if r["dimension"] == "code_quality"), {})
        loc = cq.get("total_loc", 100)
        ws.cell(row=row, column=bcol_x, value=round(audit.get("overall_score", 0), 3))
        ws.cell(row=row, column=bcol_y, value=round(audit.get("interest_score", 0), 3))
        ws.cell(row=row, column=bcol_z, value=max(loc, 10))  # Min size to be visible

    data_end = data_start + len(audits) - 1

    chart = BubbleChart()
    chart.title = "Portfolio Map (size = LOC)"
    chart.x_axis.title = "Completeness"
    chart.y_axis.title = "Interest"
    chart.x_axis.scaling.min = 0
    chart.x_axis.scaling.max = 1
    chart.y_axis.scaling.min = 0
    chart.y_axis.scaling.max = 1
    chart.style = 18

    xvalues = Reference(ws, min_col=bcol_x, min_row=data_start, max_row=data_end)
    yvalues = Reference(ws, min_col=bcol_y, min_row=data_start, max_row=data_end)
    sizes = Reference(ws, min_col=bcol_z, min_row=data_start, max_row=data_end)
    series = BubbleSeries(values=yvalues, xvalues=xvalues, zvalues=sizes, title="Repos")
    chart.series.append(series)

    chart.width = 16
    chart.height = 12
    ws.add_chart(chart, "A50")


# ═══════════════════════════════════════════════════════════════════════
# Dependency Graph Sheet
# ═══════════════════════════════════════════════════════════════════════


def _build_dependency_graph(wb: Workbook, data: dict) -> None:
    from src.dep_graph import build_dependency_graph

    ws = _get_or_create_sheet(wb, "Dep Graph")
    ws.sheet_properties.tabColor = "0277BD"
    _configure_sheet_view(ws, zoom=105, show_grid_lines=True)

    graph = build_dependency_graph(data.get("audits", []))
    shared = graph.get("shared_deps", [])

    ws.merge_cells("A1:C1")
    ws["A1"].value = f"Shared Dependencies ({len(shared)} across 2+ repos)"
    ws["A1"].font = SECTION_FONT

    headers = ["Dependency", "Repo Count", "Repos Using It"]
    for col, h in enumerate(headers, 1):
        ws.cell(row=2, column=col, value=h)
    style_header_row(ws, 2, len(headers))
    ws.freeze_panes = "A3"

    for row, dep in enumerate(shared, 3):
        ws.cell(row=row, column=1, value=dep["name"])
        ws.cell(row=row, column=2, value=dep["count"])
        ws.cell(row=row, column=3, value=", ".join(dep["repos"]))
        for col in range(1, 4):
            style_data_cell(ws.cell(row=row, column=col))

    max_row = len(shared) + 2
    if max_row > 2:
        ws.conditional_formatting.add(
            f"B3:B{max_row}",
            ColorScaleRule(
                start_type="min", start_color=HEATMAP_AMBER,
                end_type="max", end_color=HEATMAP_GREEN,
            ),
        )

    apply_zebra_stripes(ws, 3, max_row, len(headers))
    auto_width(ws, len(headers), max_row)


def _build_hotspots(wb: Workbook, data: dict) -> None:
    ws = _get_or_create_sheet(wb, "Hotspots")
    ws.sheet_properties.tabColor = "DC2626"
    _configure_sheet_view(ws, zoom=105, show_grid_lines=True)

    headers = ["Repo", "Category", "Severity", "Title", "Summary", "Recommended Action", "Tier"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws, 1, len(headers))
    ws.freeze_panes = "A2"

    hotspots = data.get("hotspots", [])
    for row, hotspot in enumerate(hotspots, 2):
        values = [
            hotspot.get("repo", ""),
            hotspot.get("category", ""),
            round(hotspot.get("severity", 0), 3),
            hotspot.get("title", ""),
            hotspot.get("summary", ""),
            hotspot.get("recommended_action", ""),
            hotspot.get("tier", ""),
        ]
        for col, value in enumerate(values, 1):
            cell = ws.cell(row=row, column=col, value=value)
            style_data_cell(cell, "center" if col in {3, 7} else "left")

    max_row = len(hotspots) + 1
    if max_row > 1:
        ws.conditional_formatting.add(
            f"C2:C{max_row}",
            DataBarRule(start_type="num", start_value=0, end_type="num", end_value=1, color="DC2626"),
        )
        apply_zebra_stripes(ws, 2, max_row, len(headers))
        _add_table(ws, "tblHotspots", len(headers), max_row)
    auto_width(ws, len(headers), max_row)


def _build_implementation_hotspots(wb: Workbook, data: dict) -> None:
    ws = _get_or_create_sheet(wb, "Implementation Hotspots")
    ws.sheet_properties.tabColor = "B45309"
    _configure_sheet_view(ws, zoom=105, show_grid_lines=True)

    summary = (data.get("implementation_hotspots_summary") or {}).get(
        "summary",
        "No meaningful implementation hotspots are currently surfaced.",
    )
    ws.merge_cells("A1:I1")
    ws["A1"].value = "Implementation Hotspots"
    ws["A1"].font = SECTION_FONT
    ws.merge_cells("A2:I2")
    ws["A2"].value = summary
    ws["A2"].alignment = WRAP

    headers = [
        "Repo",
        "Scope",
        "Path",
        "Module",
        "Category",
        "Pressure",
        "Suggestion",
        "Why It Matters",
        "Suggested First Move",
    ]
    for col, header in enumerate(headers, 1):
        ws.cell(row=4, column=col, value=header)
    style_header_row(ws, 4, len(headers))
    ws.freeze_panes = "A5"

    hotspots = data.get("implementation_hotspots", [])
    for row, hotspot in enumerate(hotspots, 5):
        values = [
            hotspot.get("repo", ""),
            hotspot.get("scope", ""),
            hotspot.get("path", ""),
            hotspot.get("module", ""),
            hotspot.get("category", ""),
            round(hotspot.get("pressure_score", 0), 3),
            hotspot.get("suggestion_type", ""),
            hotspot.get("why_it_matters", ""),
            hotspot.get("suggested_first_move", ""),
        ]
        for col, value in enumerate(values, 1):
            cell = ws.cell(row=row, column=col, value=value)
            style_data_cell(cell, "center" if col in {2, 6} else "left")

    max_row = len(hotspots) + 4
    if max_row > 4:
        ws.conditional_formatting.add(
            f"F5:F{max_row}",
            DataBarRule(start_type="num", start_value=0, end_type="num", end_value=1, color="B45309"),
        )
        apply_zebra_stripes(ws, 5, max_row, len(headers))
        _add_table(ws, "tblImplementationHotspots", len(headers), max_row, start_row=4)
    auto_width(ws, len(headers), max_row)


def _build_operator_outcomes(wb: Workbook, data: dict) -> None:
    ws = _get_or_create_sheet(wb, "Operator Outcomes")
    ws.sheet_properties.tabColor = "0369A1"
    _configure_sheet_view(ws, zoom=105, show_grid_lines=True)

    summary = (data.get("portfolio_outcomes_summary") or {}).get(
        "summary",
        "Not enough operator history is recorded yet to judge outcomes.",
    )
    effectiveness = (data.get("operator_effectiveness_summary") or {}).get(
        "summary",
        "Not enough judged recommendation history is recorded yet to judge operator effectiveness.",
    )
    trend_summary = (data.get("operator_summary") or {}).get(
        "high_pressure_queue_trend_summary",
        "High-pressure queue trend is not ready yet.",
    )
    campaign_outcomes_summary = (data.get("campaign_outcomes_summary") or {}).get(
        "summary",
        "No recent Action Sync apply needs post-apply monitoring yet, so the local weekly story can stay local.",
    )
    next_monitoring_step = (data.get("next_monitoring_step") or {}).get(
        "summary",
        "Stay local for now; no recent Action Sync apply needs post-apply follow-up yet.",
    )
    campaign_tuning_summary = (data.get("campaign_tuning_summary") or {}).get(
        "summary",
        "Campaign tuning is neutral because there is not enough outcome history yet to bias tied recommendations.",
    )
    next_tuned_campaign = (data.get("next_tuned_campaign") or {}).get(
        "summary",
        "No current campaign needs a tuning tie-break yet.",
    )
    automation_guidance_summary = (data.get("automation_guidance_summary") or {}).get(
        "summary",
        "Automation guidance stays quiet until a campaign has a clearly safe preview, follow-up, or manual-only posture.",
    )
    next_safe_automation_step = (data.get("next_safe_automation_step") or {}).get(
        "summary",
        "Stay local for now; no current campaign has a stronger safe automation posture than manual review.",
    )
    approval_workflow_summary = (data.get("approval_workflow_summary") or {}).get(
        "summary",
        "No current approval needs review yet, so the approval workflow can stay local for now.",
    )
    next_approval_review = (data.get("next_approval_review") or {}).get(
        "summary",
        "Stay local for now; no current approval needs review.",
    )
    ws.merge_cells("A1:F1")
    ws["A1"].value = "Operator Outcomes"
    ws["A1"].font = SECTION_FONT
    ws.merge_cells("A2:F2")
    ws["A2"].value = summary
    ws["A2"].alignment = WRAP
    ws.merge_cells("A3:F3")
    ws["A3"].value = effectiveness
    ws["A3"].alignment = WRAP
    ws.merge_cells("A4:F4")
    ws["A4"].value = trend_summary
    ws["A4"].alignment = WRAP
    ws.merge_cells("A5:F5")
    ws["A5"].value = campaign_outcomes_summary
    ws["A5"].alignment = WRAP
    ws.merge_cells("A6:F6")
    ws["A6"].value = next_monitoring_step
    ws["A6"].alignment = WRAP
    ws.merge_cells("A7:F7")
    ws["A7"].value = campaign_tuning_summary
    ws["A7"].alignment = WRAP
    ws.merge_cells("A8:F8")
    ws["A8"].value = next_tuned_campaign
    ws["A8"].alignment = WRAP
    ws.merge_cells("A9:F9")
    ws["A9"].value = automation_guidance_summary
    ws["A9"].alignment = WRAP
    ws.merge_cells("A10:F10")
    ws["A10"].value = next_safe_automation_step
    ws["A10"].alignment = WRAP
    ws.merge_cells("A11:F11")
    ws["A11"].value = approval_workflow_summary
    ws["A11"].alignment = WRAP
    ws.merge_cells("A12:F12")
    ws["A12"].value = next_approval_review
    ws["A12"].alignment = WRAP

    headers = ["Metric", "Status", "Value", "Numerator", "Denominator", "Summary"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=14, column=col, value=header)
    style_header_row(ws, 14, len(headers))
    ws.freeze_panes = "A15"

    metrics = [
        ("Review To Action Closure Rate", data.get("portfolio_outcomes_summary", {}).get("review_to_action_closure_rate", {})),
        ("Median Runs To Quiet After Escalation", data.get("portfolio_outcomes_summary", {}).get("median_runs_to_quiet_after_escalation", {})),
        ("Repeated Regression Rate", data.get("portfolio_outcomes_summary", {}).get("repeated_regression_rate", {})),
        ("Recommendation Validation Rate", data.get("operator_effectiveness_summary", {}).get("recommendation_validation_rate", {})),
        ("Noisy Guidance Rate", data.get("operator_effectiveness_summary", {}).get("noisy_guidance_rate", {})),
    ]
    for row, (label, metric) in enumerate(metrics, 15):
        value = metric.get("value")
        if isinstance(value, float):
            display_value = round(value, 3)
        else:
            display_value = value if value is not None else ""
        values = [
            label,
            metric.get("status", "insufficient-evidence"),
            display_value,
            metric.get("numerator", metric.get("episodes", "")),
            metric.get("denominator", ""),
            metric.get("summary", ""),
        ]
        for col, item in enumerate(values, 1):
            cell = ws.cell(row=row, column=col, value=item)
            style_data_cell(cell, "center" if col in {2, 3, 4, 5} else "left")

    monitoring_row = 22
    ws.cell(row=monitoring_row, column=1, value="Post-Apply Monitoring")
    style_header_row(ws, monitoring_row, 6)
    monitoring_headers = ["Campaign", "State", "Pressure Effect", "Drift", "Reopen", "Summary"]
    for col, header in enumerate(monitoring_headers, 1):
        ws.cell(row=monitoring_row + 1, column=col, value=header)
    style_header_row(ws, monitoring_row + 1, len(monitoring_headers))
    for row, item in enumerate(data.get("action_sync_outcomes", []) or [], monitoring_row + 2):
        values = [
            item.get("label", item.get("campaign_type", "Campaign")),
            item.get("monitoring_state", "no-recent-apply"),
            item.get("pressure_effect", "insufficient-evidence"),
            item.get("drift_state", "insufficient-evidence"),
            item.get("reopen_state", "insufficient-evidence"),
            item.get("summary", ""),
        ]
        for col, value in enumerate(values, 1):
            cell = ws.cell(row=row, column=col, value=value)
            style_data_cell(cell, "center" if col in {2, 3, 4, 5} else "left")

    example_row = monitoring_row + 8
    ws.cell(row=example_row, column=1, value="Recent Examples")
    style_header_row(ws, example_row, 3)
    ws.cell(row=example_row + 1, column=1, value="Closed Actions")
    ws.cell(row=example_row + 1, column=2, value=_join_outcome_examples(data.get("operator_summary", {}).get("recent_closed_actions", [])))
    ws.cell(row=example_row + 2, column=1, value="Reopened Recommendations")
    ws.cell(row=example_row + 2, column=2, value=_join_outcome_examples(data.get("operator_summary", {}).get("recent_reopened_recommendations", [])))
    ws.cell(row=example_row + 3, column=1, value="Regression Examples")
    ws.cell(row=example_row + 3, column=2, value=_join_outcome_examples(data.get("operator_summary", {}).get("recent_regression_examples", [])))

    history_row = example_row + 6
    history_headers = ["Run", "Generated", "Blocked", "Urgent", "High Pressure"]
    for col, header in enumerate(history_headers, 1):
        ws.cell(row=history_row, column=col, value=header)
    style_header_row(ws, history_row, len(history_headers))
    history = data.get("high_pressure_queue_history", []) or []
    for row, item in enumerate(history, history_row + 1):
        values = [
            item.get("run_id", ""),
            item.get("generated_at", ""),
            item.get("blocked_count", 0),
            item.get("urgent_count", 0),
            item.get("high_pressure_count", 0),
        ]
        for col, value in enumerate(values, 1):
            cell = ws.cell(row=row, column=col, value=value)
            style_data_cell(cell, "center" if col >= 3 else "left")

    max_row = max(history_row + len(history), example_row + 3, monitoring_row + 3, 15)
    auto_width(ws, 6, max_row)


def _build_approval_ledger(wb: Workbook, data: dict) -> None:
    ws = _get_or_create_sheet(wb, "Approval Ledger")
    ws.sheet_properties.tabColor = "6D28D9"
    _configure_sheet_view(ws, zoom=105, show_grid_lines=True)

    summary = (data.get("approval_workflow_summary") or {}).get(
        "summary",
        "No current approval needs review yet, so the approval workflow can stay local for now.",
    )
    next_review = (data.get("next_approval_review") or {}).get(
        "summary",
        "Stay local for now; no current approval needs review.",
    )

    ws.merge_cells("A1:F1")
    ws["A1"].value = ACTION_SYNC_CANONICAL_LABELS["approval_ledger"]
    ws["A1"].font = SECTION_FONT
    ws.merge_cells("A2:F2")
    ws["A2"].value = summary
    ws["A2"].alignment = WRAP
    ws.merge_cells("A3:F3")
    ws["A3"].value = next_review
    ws["A3"].alignment = WRAP

    headers = ["Label", "State", "Subject", "Reviewer", "Approved At", "Summary"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=5, column=col, value=header)
    style_header_row(ws, 5, len(headers))
    ws.freeze_panes = "A6"

    row = 6
    for label, items in (
        ("Needs Re-Approval", data.get("top_needs_reapproval_approvals", []) or []),
        ("Ready For Review", data.get("top_ready_for_review_approvals", []) or []),
        (ACTION_SYNC_CANONICAL_LABELS["approved_but_manual"], data.get("top_approved_manual_approvals", []) or []),
        ("Blocked", data.get("top_blocked_approvals", []) or []),
    ):
        ws.cell(row=row, column=1, value=label)
        ws.cell(row=row, column=1).font = SUBTITLE_FONT
        row += 1
        if not items:
            ws.cell(row=row, column=1, value="None")
            row += 1
            continue
        for item in items[:8]:
            values = [
                item.get("label", item.get("subject_key", "Approval")),
                item.get("approval_state", "not-applicable"),
                item.get("approval_subject_type", ""),
                item.get("approved_by", ""),
                item.get("approved_at", ""),
                item.get("summary", ""),
            ]
            for col, value in enumerate(values, 1):
                cell = ws.cell(row=row, column=col, value=value)
                style_data_cell(cell, "center" if col in {2, 3, 4, 5} else "left")
            row += 1

    auto_width(ws, 6, row)


def _build_historical_intelligence(wb: Workbook, data: dict) -> None:
    ws = _get_or_create_sheet(wb, "Historical Intelligence")
    ws.sheet_properties.tabColor = "0F766E"
    _configure_sheet_view(ws, zoom=105, show_grid_lines=True)

    summary = (data.get("intervention_ledger_summary") or {}).get(
        "summary",
        "Historical portfolio intelligence is still thin, so the weekly story should stay grounded in the current run and recent operator queue.",
    )
    next_focus = (data.get("next_historical_focus") or {}).get(
        "summary",
        "Stay local for now; no repo has enough cross-run intervention evidence to demand a historical follow-up read yet.",
    )

    ws.merge_cells("A1:F1")
    ws["A1"].value = ACTION_SYNC_CANONICAL_LABELS["historical_portfolio_intelligence"]
    ws["A1"].font = SECTION_FONT
    ws.merge_cells("A2:F2")
    ws["A2"].value = summary
    ws["A2"].alignment = WRAP
    ws.merge_cells("A3:F3")
    ws["A3"].value = next_focus
    ws["A3"].alignment = WRAP

    headers = ["Repo", "Status", "Pressure Trend", "Hotspot Persistence", "Scorecard Trend", "Summary"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=5, column=col, value=header)
    style_header_row(ws, 5, len(headers))
    ws.freeze_panes = "A6"

    row = 6
    for label, items in (
        ("Relapsing", data.get("top_relapsing_repos", []) or []),
        ("Persistent Pressure", data.get("top_persistent_pressure_repos", []) or []),
        ("Improving After Intervention", data.get("top_improving_repos", []) or []),
        ("Holding Steady", data.get("top_holding_repos", []) or []),
    ):
        ws.cell(row=row, column=1, value=label)
        ws.cell(row=row, column=1).font = SUBTITLE_FONT
        row += 1
        if not items:
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
            ws.cell(row=row, column=1, value=f"No repos currently show a {label.lower()} story.")
            ws.cell(row=row, column=1).alignment = WRAP
            row += 2
            continue
        for item in items[:5]:
            values = [
                item.get("repo", ""),
                item.get("historical_intelligence_status", "insufficient-evidence"),
                item.get("pressure_trend", "insufficient-evidence"),
                item.get("hotspot_persistence", "insufficient-evidence"),
                item.get("scorecard_trend", "insufficient-evidence"),
                item.get("summary", ""),
            ]
            for col, value in enumerate(values, 1):
                cell = ws.cell(row=row, column=col, value=value)
                style_data_cell(cell, "center" if col in {2, 3, 4, 5} else "left")
            row += 1
        row += 1

    auto_width(ws, len(headers), max(row - 1, 5))


def _join_outcome_examples(items: list[dict]) -> str:
    if not items:
        return "No recent examples are recorded yet."
    labels = []
    for item in items[:3]:
        repo = str(item.get("repo") or "").strip()
        title = str(item.get("title") or item.get("action_id") or "Operator outcome").strip()
        labels.append(f"{repo}: {title}" if repo else title)
    return "; ".join(labels)


def _write_hidden_table_sheet(
    wb: Workbook,
    title: str,
    table_name: str,
    headers: list[str],
    rows: list[list[object]],
) -> None:
    ws = wb.create_sheet(title)
    ws.sheet_state = "hidden"
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws, 1, len(headers))

    for row_index, row_values in enumerate(rows, 2):
        for col_index, value in enumerate(row_values, 1):
            cell = ws.cell(row=row_index, column=col_index, value=value)
            style_data_cell(cell, "center" if isinstance(value, (int, float)) else "left")

    max_row = len(rows) + 1
    if max_row > 1:
        _add_table(ws, table_name, len(headers), max_row)
        apply_zebra_stripes(ws, 2, max_row, len(headers))
    auto_width(ws, len(headers), max_row)


def _set_internal_hyperlink(cell, sheet_name: str, *, target_cell: str = "A1", display: str | None = None) -> None:
    cell.hyperlink = Hyperlink(
        ref=cell.coordinate,
        location=_sheet_location(sheet_name, target_cell),
        display=display or str(cell.value or ""),
    )
    cell.font = Font("Calibri", 10, bold=True, color=TEAL, underline="single")


def _repo_detail_lookup_formula(column_index: int, fallback: str, *, allow_blank: bool = False) -> str:
    escaped_fallback = fallback.replace('"', '""')
    lookup = f"VLOOKUP($B$4,Data_RepoDetail!$A:$BZ,{column_index},FALSE)"
    if allow_blank:
        return f'=IFERROR({lookup},"{escaped_fallback}")'
    return f'=IFERROR(IF({lookup}="","{escaped_fallback}",{lookup}),"{escaped_fallback}")'


def _repo_detail_last_movement(scores: list[float]) -> str:
    if len(scores) < 2:
        return "No prior comparison yet."
    delta = round(scores[-1] - scores[-2], 3)
    if abs(delta) < 0.005:
        return "Holding flat versus the last run."
    if delta > 0:
        return f"Up {delta:.3f} versus the last run."
    return f"Down {abs(delta):.3f} versus the last run."


def _lane_fill_hex(lane: str | None) -> str | None:
    if not lane:
        return None
    return REVIEW_QUEUE_LANE_FILLS.get(str(lane).strip().lower())


def _apply_lane_row_fill(ws, row: int, max_col: int, lane: str | None) -> None:
    fill_hex = _lane_fill_hex(lane)
    if not fill_hex:
        return
    for col in range(1, max_col + 1):
        ws.cell(row=row, column=col).fill = PatternFill(fill_type="solid", fgColor=fill_hex)


def _score_explanation_for_audit(audit: dict) -> dict:
    explanation = dict(audit.get("score_explanation") or {})
    if explanation:
        return explanation
    return build_score_explanation(audit)


def _repo_detail_rows(data: dict, score_history: dict[str, list[float]] | None) -> tuple[list[list[object]], list[list[object]], list[list[object]]]:
    memberships = _collection_memberships(data)
    history = _extend_score_history_with_current(data, score_history)
    detail_rows: list[list[object]] = []
    dimension_rows: list[list[object]] = []
    history_rows: list[list[object]] = []

    for audit in sorted(data.get("audits", []), key=lambda item: item.get("metadata", {}).get("name", "")):
        metadata = audit.get("metadata", {})
        repo_name = metadata.get("name", "")
        explanation = _score_explanation_for_audit(audit)
        briefing = build_repo_briefing(audit, data, None)
        hotspot_titles = [item.get("title", "") for item in (audit.get("hotspots") or [])[:3]]
        implementation_hotspot_lines = [
            f"{item.get('path', 'repo root')}: {item.get('signal_summary', 'No signal summary recorded yet.')}"
            for item in (briefing.get("implementation_hotspots") or [])[:3]
        ]
        action_titles = [item.get("title", "") for item in (audit.get("action_candidates") or [])[:3]]
        lenses = audit.get("lenses", {})
        scores = history.get(repo_name, [])
        detail_rows.append([
            repo_name,
            metadata.get("html_url", ""),
            metadata.get("language") or "Unknown",
            metadata.get("description") or "No description recorded yet.",
            round(audit.get("overall_score", 0.0), 3),
            round(audit.get("interest_score", 0.0), 3),
            audit.get("grade", ""),
            audit.get("completeness_tier", ""),
            ", ".join(audit.get("badges", [])[:6]) or "None",
            ", ".join(audit.get("flags", [])[:6]) or "None",
            ", ".join(memberships.get(repo_name, [])) or "—",
            audit.get("security_posture", {}).get("label", "unknown"),
            round(audit.get("security_posture", {}).get("score", 0.0), 3),
            lenses.get("ship_readiness", {}).get("summary", "") or "No ship-readiness summary recorded yet.",
            lenses.get("momentum", {}).get("summary", "") or "No momentum summary recorded yet.",
            lenses.get("security_posture", {}).get("summary", "") or "No security summary recorded yet.",
            lenses.get("portfolio_fit", {}).get("summary", "") or "No portfolio-fit summary recorded yet.",
            render_sparkline(scores) if scores else briefing.get("current_state", {}).get("trend", "No trend history yet."),
            briefing.get("why_this_repo_looks_this_way", {}).get("strongest_drivers", ", ".join(explanation.get("top_positive_drivers", [])[:3]) or "No strong positive drivers recorded yet."),
            briefing.get("why_this_repo_looks_this_way", {}).get("biggest_drags", ", ".join(explanation.get("top_negative_drivers", [])[:3]) or "No major drag factors recorded yet."),
            briefing.get("why_this_repo_looks_this_way", {}).get("next_tier_gap", explanation.get("next_tier_gap_summary", "") or "No next-tier gap is recorded yet."),
            briefing.get("what_to_do_next", {}).get("next_best_action", explanation.get("next_best_action", "") or "No clear next action is recorded yet."),
            briefing.get("what_to_do_next", {}).get("rationale", explanation.get("next_best_action_rationale", "") or "No action rationale is recorded yet."),
            briefing.get("what_changed", {}).get("top_hotspot_context", hotspot_titles[0] if len(hotspot_titles) > 0 else "No hotspot recorded yet."),
            hotspot_titles[1] if len(hotspot_titles) > 1 else "No secondary hotspot recorded yet.",
            hotspot_titles[2] if len(hotspot_titles) > 2 else "No third hotspot recorded yet.",
            briefing.get("what_to_do_next", {}).get("next_best_action", action_titles[0] if len(action_titles) > 0 else "No action candidate recorded yet."),
            action_titles[1] if len(action_titles) > 1 else "No second action candidate recorded yet.",
            action_titles[2] if len(action_titles) > 2 else "No third action candidate recorded yet.",
            briefing.get("what_changed", {}).get("last_movement", _repo_detail_last_movement(scores)),
            briefing.get("what_changed", {}).get("recent_change_summary", "No recent change summary is recorded yet."),
            briefing.get("what_to_do_next", {}).get("follow_through_status", "Unknown"),
            briefing.get("what_to_do_next", {}).get("follow_through_summary", "No follow-through evidence is recorded yet."),
            briefing.get("what_to_do_next", {}).get("checkpoint_timing", "Unknown"),
            briefing.get("what_to_do_next", {}).get("escalation", "Unknown"),
            briefing.get("what_to_do_next", {}).get("escalation_summary", "No stronger follow-through escalation is currently surfaced."),
            briefing.get("what_to_do_next", {}).get("recovery_retirement", "None"),
            briefing.get("what_to_do_next", {}).get("recovery_retirement_summary", "No follow-through recovery or escalation-retirement signal is currently surfaced."),
            briefing.get("what_to_do_next", {}).get("recovery_persistence", "None"),
            briefing.get("what_to_do_next", {}).get("recovery_persistence_summary", "No follow-through recovery persistence signal is currently surfaced."),
            briefing.get("what_to_do_next", {}).get("relapse_churn", "None"),
            briefing.get("what_to_do_next", {}).get("relapse_churn_summary", "No relapse churn is currently surfaced."),
            briefing.get("what_to_do_next", {}).get("recovery_freshness", "None"),
            briefing.get("what_to_do_next", {}).get("recovery_freshness_summary", "No follow-through recovery freshness signal is currently surfaced."),
            briefing.get("what_to_do_next", {}).get("recovery_memory_reset", "None"),
            briefing.get("what_to_do_next", {}).get("recovery_memory_reset_summary", "No follow-through recovery memory reset signal is currently surfaced."),
            briefing.get("what_to_do_next", {}).get("recovery_rebuild_strength", "None"),
            briefing.get("what_to_do_next", {}).get("recovery_rebuild_strength_summary", "No follow-through recovery rebuild-strength signal is currently surfaced."),
            briefing.get("what_to_do_next", {}).get("recovery_reacquisition", "None"),
            briefing.get("what_to_do_next", {}).get("recovery_reacquisition_summary", "No follow-through recovery reacquisition signal is currently surfaced."),
            briefing.get("what_to_do_next", {}).get("reacquisition_durability", "None"),
            briefing.get("what_to_do_next", {}).get("reacquisition_durability_summary", "No follow-through reacquisition durability signal is currently surfaced."),
            briefing.get("what_to_do_next", {}).get("reacquisition_confidence", "None"),
            briefing.get("what_to_do_next", {}).get("reacquisition_confidence_summary", "No follow-through reacquisition confidence-consolidation signal is currently surfaced."),
            briefing.get("what_to_do_next", {}).get("reacquisition_softening_decay", "None"),
            briefing.get("what_to_do_next", {}).get("reacquisition_softening_decay_summary", "No reacquisition softening-decay signal is currently surfaced."),
            briefing.get("what_to_do_next", {}).get("reacquisition_confidence_retirement", "None"),
            briefing.get("what_to_do_next", {}).get("reacquisition_confidence_retirement_summary", "No reacquisition confidence-retirement signal is currently surfaced."),
            briefing.get("what_to_do_next", {}).get("revalidation_recovery", "None"),
            briefing.get("what_to_do_next", {}).get("revalidation_recovery_summary", "No post-revalidation recovery or confidence re-earning signal is currently surfaced."),
            briefing.get("what_to_do_next", {}).get("what_would_count_as_progress", "Use the next run or linked artifact to confirm whether the recommendation moved."),
            briefing.get("catalog_line", "No portfolio catalog contract is recorded yet."),
            briefing.get("intent_alignment_line", "missing-contract: Intent alignment cannot be judged until a portfolio catalog contract exists."),
            briefing.get("scorecard_line", "Scorecard: No maturity scorecard is recorded yet."),
            briefing.get("maturity_gap_summary", "No maturity gap summary is recorded yet."),
            briefing.get("where_to_start_summary", "No meaningful implementation hotspot is currently surfaced."),
            implementation_hotspot_lines[0] if len(implementation_hotspot_lines) > 0 else "No implementation hotspot is currently surfaced.",
            implementation_hotspot_lines[1] if len(implementation_hotspot_lines) > 1 else "No second implementation hotspot is currently surfaced.",
            implementation_hotspot_lines[2] if len(implementation_hotspot_lines) > 2 else "No third implementation hotspot is currently surfaced.",
        ])

        ranked_dimensions = sorted(
            [
                (
                    result.get("dimension", ""),
                    round(result.get("score", 0.0), 3),
                    "; ".join((result.get("findings") or [])[:2]) or "No major concerns recorded.",
                )
                for result in audit.get("analyzer_results", [])
                if result.get("dimension") != "interest"
            ],
            key=lambda item: item[1],
        )
        for rank, (dimension, score, summary) in enumerate(ranked_dimensions, 1):
            lookup_key = f"{repo_name}::{rank}"
            dimension_rows.append([lookup_key, repo_name, rank, dimension, score, summary])

        for run_index, score in enumerate(scores, 1):
            history_rows.append([repo_name, run_index, score, render_sparkline(scores)])

    return detail_rows, dimension_rows, history_rows


def _run_change_rows(data: dict, diff_data: dict | None) -> tuple[list[list[object]], list[list[object]]]:
    counts = build_run_change_counts(diff_data)
    summary_rows = [
        ["Summary", build_run_change_summary(diff_data), ""],
        ["Score Improvements", counts.get("score_improvements", 0), "Repos that improved since the last run."],
        ["Score Regressions", counts.get("score_regressions", 0), "Repos that regressed since the last run."],
        ["Tier Promotions", counts.get("tier_promotions", 0), "Repos that moved up a tier."],
        ["Tier Demotions", counts.get("tier_demotions", 0), "Repos that moved down a tier."],
        ["New Repos", counts.get("new_repos", 0), "Repos that are new in this run."],
        ["Removed Repos", counts.get("removed_repos", 0), "Repos missing compared with the prior run."],
        ["Security Changes", counts.get("security_changes", 0), "Repos with security posture movement."],
        ["Governance Changes", counts.get("collection_changes", 0), "Repos with collection or governance drift."],
        ["Notable Repo Changes", counts.get("notable_repo_changes", 0), "Repos with notable diff rows."],
    ]

    repo_rows: list[list[object]] = []
    for change in diff_data.get("repo_changes", []) if diff_data else []:
        repo_rows.append([
            "repo-change",
            change.get("name", ""),
            round(change.get("delta", 0.0), 3),
            change.get("old_tier", ""),
            change.get("new_tier", ""),
            change.get("security_change", {}).get("new_label", ""),
            change.get("hotspot_change", {}).get("new_count", 0),
            ", ".join(change.get("collection_change", {}).get("new", []) or []),
            "General repo movement since the previous run.",
        ])
    for change in diff_data.get("tier_changes", []) if diff_data else []:
        repo_rows.append([
            f"tier-{change.get('direction', 'change')}",
            change.get("name", ""),
            round(change.get("new_score", 0.0) - change.get("old_score", 0.0), 3),
            change.get("old_tier", ""),
            change.get("new_tier", ""),
            "",
            "",
            "",
            f"Tier {change.get('direction', 'change')} detected in the comparison window.",
        ])
    for item in data.get("material_changes", []) or []:
        repo_rows.append([
            f"material-{item.get('change_type', 'other')}",
            item.get("repo", ""),
            _severity_rank(item.get("severity")),
            "",
            "",
            "",
            "",
            "",
            item.get("title", ""),
        ])
    return summary_rows, repo_rows


def _build_hidden_data_sheets(
    wb: Workbook,
    data: dict,
    trend_data: list[dict] | None = None,
    score_history: dict[str, list[float]] | None = None,
    diff_data: dict | None = None,
) -> None:
    from src.analyst_views import build_analyst_context

    audits = data.get("audits", [])
    memberships = _collection_memberships(data)
    extended_score_history = _extend_score_history_with_current(data, score_history)
    extended_trends = _extend_portfolio_trend_with_current(data, trend_data)

    repo_rows: list[list[object]] = []
    dimension_rows: list[list[object]] = []
    lens_rows: list[list[object]] = []
    history_rows: list[list[object]] = []
    trend_matrix_rows: list[list[object]] = []
    portfolio_history_rows: list[list[object]] = []
    rollup_rows: list[list[object]] = []
    review_target_rows: list[list[object]] = []
    review_history_rows: list[list[object]] = []
    security_rows: list[list[object]] = []
    security_control_rows: list[list[object]] = []
    security_provider_rows: list[list[object]] = []
    security_alert_rows: list[list[object]] = []
    action_rows: list[list[object]] = []
    collection_rows: list[list[object]] = []
    scenario_rows: list[list[object]] = []
    governance_rows: list[list[object]] = []
    campaign_rows: list[list[object]] = []
    writeback_rows: list[list[object]] = []
    portfolio_catalog_rows: list[list[object]] = []
    scorecard_rows: list[list[object]] = []
    implementation_hotspot_rows: list[list[object]] = []
    operator_outcome_rows: list[list[object]] = []
    action_sync_outcome_rows: list[list[object]] = []
    campaign_tuning_rows: list[list[object]] = []
    intervention_ledger_rows: list[list[object]] = []
    action_sync_automation_rows: list[list[object]] = []
    approval_ledger_rows: list[list[object]] = []
    lookup_rows: list[list[object]] = []
    repo_detail_rows, repo_dimension_rollup_rows, repo_history_rollup_rows = _repo_detail_rows(data, score_history)
    run_change_rollup_rows, run_change_repo_rows = _run_change_rows(data, diff_data)
    operator_queue_rows, operator_repo_rollups, material_rollups = _build_workbook_rollups(data)
    portfolio_outcomes = data.get("portfolio_outcomes_summary", {}) or {}
    operator_effectiveness = data.get("operator_effectiveness_summary", {}) or {}
    operator_summary = data.get("operator_summary", {}) or {}
    for label, metric in (
        ("review_to_action_closure_rate", portfolio_outcomes.get("review_to_action_closure_rate", {})),
        ("median_runs_to_quiet_after_escalation", portfolio_outcomes.get("median_runs_to_quiet_after_escalation", {})),
        ("repeated_regression_rate", portfolio_outcomes.get("repeated_regression_rate", {})),
        ("recommendation_validation_rate", operator_effectiveness.get("recommendation_validation_rate", {})),
        ("noisy_guidance_rate", operator_effectiveness.get("noisy_guidance_rate", {})),
    ):
        operator_outcome_rows.append([
            label,
            metric.get("status", "insufficient-evidence"),
            metric.get("value", ""),
            metric.get("numerator", metric.get("episodes", "")),
            metric.get("denominator", ""),
            metric.get("summary", ""),
        ])
    for item in data.get("high_pressure_queue_history", []) or []:
        operator_outcome_rows.append([
            "high_pressure_queue_history",
            operator_summary.get("high_pressure_queue_trend_status", ""),
            item.get("high_pressure_count", 0),
            item.get("blocked_count", 0),
            item.get("urgent_count", 0),
            item.get("generated_at", ""),
        ])
    for label, items in (
        ("recent_closed_actions", operator_summary.get("recent_closed_actions", [])),
        ("recent_reopened_recommendations", operator_summary.get("recent_reopened_recommendations", [])),
        ("recent_regression_examples", operator_summary.get("recent_regression_examples", [])),
    ):
        for item in items[:3]:
            operator_outcome_rows.append([
                label,
                "example",
                item.get("repo", ""),
                item.get("title", ""),
                item.get("action_id", ""),
                item.get("summary", ""),
            ])
    for item in data.get("action_sync_outcomes", []) or []:
        action_sync_outcome_rows.append([
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
        ])
    for item in data.get("action_sync_tuning", []) or []:
        campaign_tuning_rows.append([
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
        ])
    for item in data.get("historical_portfolio_intelligence", []) or []:
        intervention_ledger_rows.append([
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
        ])
    for item in data.get("action_sync_automation", []) or []:
        action_sync_automation_rows.append([
            item.get("campaign_type", ""),
            item.get("label", ""),
            item.get("automation_posture", "manual-only"),
            "yes" if item.get("review_required") else "no",
            "yes" if item.get("requires_approval") else "no",
            item.get("recommended_command", ""),
            item.get("recommended_follow_up", ""),
            item.get("summary", ""),
        ])
    for item in data.get("approval_ledger", []) or []:
        approval_ledger_rows.append([
            item.get("approval_id", ""),
            item.get("approval_subject_type", ""),
            item.get("subject_key", ""),
            item.get("label", ""),
            item.get("approval_state", "not-applicable"),
            item.get("source_run_id", ""),
            item.get("fingerprint", ""),
            item.get("approved_at", ""),
            item.get("approved_by", ""),
            "yes" if item.get("approval_ready") else "no",
            "yes" if item.get("apply_ready_after_approval") else "no",
            item.get("approval_command", ""),
            item.get("manual_apply_command", ""),
            item.get("summary", ""),
        ])

    for audit in audits:
        metadata = audit.get("metadata", {})
        repo_name = metadata.get("name", "")
        lenses = audit.get("lenses", {})
        repo_rows.append([
            repo_name,
            metadata.get("full_name", ""),
            metadata.get("language") or "Unknown",
            "Yes" if metadata.get("private") else "No",
            "Yes" if metadata.get("archived") else "No",
            round(audit.get("overall_score", 0), 3),
            round(audit.get("interest_score", 0), 3),
            audit.get("grade", ""),
            audit.get("completeness_tier", ""),
            audit.get("security_posture", {}).get("label", "unknown"),
            ", ".join(memberships.get(repo_name, [])),
            lenses.get("ship_readiness", {}).get("score", 0.0),
            lenses.get("maintenance_risk", {}).get("score", 0.0),
            lenses.get("showcase_value", {}).get("score", 0.0),
            lenses.get("security_posture", {}).get("score", 0.0),
            lenses.get("momentum", {}).get("score", 0.0),
            lenses.get("portfolio_fit", {}).get("score", 0.0),
        ])
        catalog = audit.get("portfolio_catalog", {})
        portfolio_catalog_rows.append([
            repo_name,
            metadata.get("full_name", ""),
            catalog.get("owner", ""),
            catalog.get("team", ""),
            catalog.get("purpose", ""),
            catalog.get("lifecycle_state", ""),
            catalog.get("criticality", ""),
            catalog.get("review_cadence", ""),
            catalog.get("intended_disposition", ""),
            catalog.get("maturity_program", ""),
            catalog.get("target_maturity", ""),
            catalog.get("notes", ""),
            catalog.get("intent_alignment", "missing-contract"),
            catalog.get("intent_alignment_reason", ""),
            catalog.get("catalog_line", ""),
        ])
        scorecard = audit.get("scorecard", {})
        scorecard_rows.append([
            repo_name,
            metadata.get("full_name", ""),
            scorecard.get("program", ""),
            scorecard.get("program_label", ""),
            scorecard.get("score", 0.0),
            scorecard.get("maturity_level", ""),
            scorecard.get("target_maturity", ""),
            scorecard.get("status", ""),
            scorecard.get("passed_rules", 0),
            scorecard.get("applicable_rules", 0),
            ", ".join(scorecard.get("failed_rule_keys", [])),
            ", ".join(scorecard.get("top_gaps", [])),
            scorecard.get("summary", ""),
        ])
        for hotspot in audit.get("implementation_hotspots", []):
            implementation_hotspot_rows.append([
                repo_name,
                metadata.get("full_name", ""),
                hotspot.get("scope", ""),
                hotspot.get("path", ""),
                hotspot.get("module", ""),
                hotspot.get("category", ""),
                hotspot.get("pressure_score", 0.0),
                hotspot.get("suggestion_type", ""),
                hotspot.get("why_it_matters", ""),
                hotspot.get("suggested_first_move", ""),
                hotspot.get("signal_summary", ""),
            ])

        for result in audit.get("analyzer_results", []):
            dimension_rows.append([
                repo_name,
                result.get("dimension", ""),
                result.get("score", 0.0),
                result.get("max_score", 1.0),
                "; ".join(result.get("findings", [])[:3]),
            ])

        for lens_name, lens_data in lenses.items():
            lens_rows.append([
                repo_name,
                lens_name,
                lens_data.get("score", 0.0),
                lens_data.get("orientation", ""),
                lens_data.get("summary", ""),
                ", ".join(lens_data.get("drivers", [])),
            ])

        posture = audit.get("security_posture", {})
        security_rows.append([
            repo_name,
            posture.get("label", "unknown"),
            posture.get("score", 0.0),
            posture.get("secrets_found", 0),
            len(posture.get("dangerous_files", [])),
            "Yes" if posture.get("has_security_md") else "No",
            "Yes" if posture.get("has_dependabot") else "No",
            "; ".join(posture.get("evidence", [])),
        ])
        github = posture.get("github", {})
        security_control_rows.extend([
            [repo_name, "security_md", "enabled" if posture.get("has_security_md") else "missing", "local", ""],
            [repo_name, "dependabot_config", "enabled" if posture.get("has_dependabot") else "missing", "local", ""],
            [repo_name, "dependency_graph", github.get("dependency_graph_status", "unavailable"), "github", str(github.get("dependency_graph_enabled"))],
            [repo_name, "sbom_export", github.get("sbom_status", "unavailable"), "github", str(github.get("sbom_exportable"))],
            [repo_name, "code_scanning", github.get("code_scanning_status", "unavailable"), "github", str(github.get("code_scanning_alerts"))],
            [repo_name, "secret_scanning", github.get("secret_scanning_status", "unavailable"), "github", str(github.get("secret_scanning_alerts"))],
        ])
        for provider_name, provider_data in (posture.get("providers") or {}).items():
            security_provider_rows.append([
                repo_name,
                provider_name,
                "Yes" if provider_data.get("available") else "No",
                provider_data.get("score", ""),
                posture.get(provider_name, {}).get("reason", "") if provider_name != "local" else "",
            ])
        security_alert_rows.append([
            repo_name,
            "code_scanning",
            github.get("code_scanning_alerts") or 0,
            github.get("code_scanning_status", "unavailable"),
        ])
        security_alert_rows.append([
            repo_name,
            "secret_scanning",
            github.get("secret_scanning_alerts") or 0,
            github.get("secret_scanning_status", "unavailable"),
        ])
        for recommendation in posture.get("recommendations", []):
            governance_rows.append([
                repo_name,
                recommendation.get("key", ""),
                recommendation.get("priority", "medium"),
                recommendation.get("title", ""),
                recommendation.get("expected_posture_lift", 0.0),
                recommendation.get("effort", ""),
                recommendation.get("source", ""),
                recommendation.get("why", ""),
            ])

        for action in audit.get("action_candidates", []):
            action_rows.append([
                repo_name,
                action.get("key", ""),
                action.get("title", ""),
                action.get("lens", ""),
                action.get("effort", ""),
                action.get("confidence", 0.0),
                action.get("expected_lens_delta", 0.0),
                action.get("expected_tier_movement", ""),
                action.get("rationale", ""),
            ])

    if extended_score_history:
        for repo_name, scores in extended_score_history.items():
            for run_index, score in enumerate(scores, 1):
                history_rows.append([repo_name, run_index, score])
            padded_scores = ([None] * TREND_HISTORY_WINDOW + list(scores))[-TREND_HISTORY_WINDOW:]
            trend_matrix_rows.append([repo_name] + padded_scores)

    if extended_trends:
        for run_index, trend in enumerate(extended_trends, 1):
            history_rows.append([
                "__portfolio__",
                run_index,
                trend.get("average_score", 0.0),
            ])
            portfolio_history_rows.append([
                run_index,
                trend.get("date", ""),
                trend.get("average_score", 0.0),
                trend.get("repos_audited", 0),
                trend.get("tier_distribution", {}).get("shipped", 0),
                trend.get("tier_distribution", {}).get("functional", 0),
                trend.get("security_average_score", data.get("security_posture", {}).get("average_score", 0.0)),
                "yes" if trend.get("review_emitted") else "no",
                trend.get("campaign_drift_count", 0),
                trend.get("governance_drift_count", 0),
            ])

    for collection_name, collection_data in data.get("collections", {}).items():
        for rank_index, repo_data in enumerate(collection_data.get("repos", []), 1):
            repo_name = repo_data["name"] if isinstance(repo_data, dict) else str(repo_data)
            reason = repo_data.get("reason", "") if isinstance(repo_data, dict) else ""
            collection_rows.append([
                collection_name,
                repo_name,
                rank_index,
                reason,
                collection_data.get("description", ""),
            ])

    scenario_summary = data.get("scenario_summary", {})
    for lever in scenario_summary.get("top_levers", []):
        scenario_rows.append([
            lever.get("key", ""),
            lever.get("title", ""),
            lever.get("lens", ""),
            lever.get("repo_count", 0),
            lever.get("average_expected_lens_delta", 0.0),
            lever.get("projected_tier_promotions", 0),
        ])
    projection = scenario_summary.get("portfolio_projection", {})
    if projection:
        scenario_rows.append([
            "portfolio_projection",
            "Portfolio projection",
            "portfolio_fit",
            projection.get("projected_shipped", 0),
            projection.get("projected_average_score_delta", 0.0),
            projection.get("current_shipped", 0),
        ])

    contexts: list[tuple[str, str | None, dict]] = []
    profile_names = list(data.get("profiles", {}).keys()) or ["default"]
    collection_names = [None] + list(data.get("collections", {}).keys())
    for profile_name in profile_names:
        for collection_name in collection_names:
            contexts.append(
                (
                    profile_name,
                    collection_name,
                    build_analyst_context(
                        data,
                        profile_name=profile_name,
                        collection_name=collection_name,
                    ),
                )
            )

    for profile_name, collection_name, context in contexts:
        leaders = context.get("profile_leaderboard", {}).get("leaders", [])
        top_repo = leaders[0]["name"] if leaders else ""
        for lens_name, lens_data in data.get("lenses", {}).items():
            selected = [item for item in context.get("ranked_audits", [])]
            scores = [
                item.get("audit", {}).get("lenses", {}).get(lens_name, {}).get("score", 0.0)
                for item in selected
            ]
            rollup_rows.append([
                profile_name,
                collection_name or "all",
                lens_name,
                len(selected),
                round(sum(scores) / len(scores), 3) if scores else 0.0,
                top_repo,
                leaders[0]["profile_score"] if leaders else 0.0,
            ])

    for item in data.get("review_targets", []):
        review_target_rows.append([
            item.get("repo", ""),
            item.get("title", ""),
            item.get("severity", 0.0),
            item.get("next_step", ""),
            item.get("decision_hint", ""),
            "yes" if item.get("safe_to_defer") else "no",
        ])

    for item in data.get("review_history", []):
        review_history_rows.append([
            item.get("review_id", ""),
            item.get("source_run_id", ""),
            item.get("generated_at", ""),
            item.get("materiality", ""),
            item.get("material_change_count", 0),
            item.get("status", ""),
            item.get("decision_state", ""),
            item.get("sync_state", ""),
            "yes" if item.get("safe_to_defer") else "no",
            "yes" if item.get("emitted") else "no",
        ])

    for lens_name, lens_data in data.get("lenses", {}).items():
        lookup_rows.append(["lens", lens_name, lens_data.get("description", "")])
    for profile_name, profile_data in data.get("profiles", {}).items():
        lookup_rows.append(["profile", profile_name, profile_data.get("description", "")])
    for tier_name in TIER_ORDER:
        lookup_rows.append(["tier", tier_name, str(data.get("tier_distribution", {}).get(tier_name, 0))])
    for audit in sorted(data.get("audits", []), key=lambda item: item.get("metadata", {}).get("name", "")):
        repo_name = audit.get("metadata", {}).get("name", "")
        if repo_name:
            lookup_rows.append(["repo-selector", repo_name, repo_name])
    campaign_summary = data.get("campaign_summary", {})
    if campaign_summary:
        campaign_rows.append([
            campaign_summary.get("campaign_type", ""),
            campaign_summary.get("label", ""),
            campaign_summary.get("portfolio_profile", "default"),
            campaign_summary.get("collection_name", ""),
            campaign_summary.get("action_count", 0),
            campaign_summary.get("repo_count", 0),
        ])
    for result in data.get("writeback_results", {}).get("results", []):
        writeback_rows.append([
            result.get("repo_full_name", ""),
            result.get("target", ""),
            result.get("status", ""),
            result.get("url", ""),
            json.dumps(result.get("before", {})),
            json.dumps(result.get("after", {})),
        ])

    _write_hidden_table_sheet(
        wb,
        "Data_Repos",
        "tblRepos",
        [
            "Repo", "Full Name", "Language", "Private", "Archived", "Overall Score",
            "Interest Score", "Grade", "Tier", "Security Label", "Collections",
            "Ship Readiness", "Maintenance Risk", "Showcase Value",
            "Security Posture", "Momentum", "Portfolio Fit",
        ],
        repo_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_Dimensions",
        "tblDimensions",
        ["Repo", "Dimension", "Score", "Max Score", "Findings"],
        dimension_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_Lenses",
        "tblLenses",
        ["Repo", "Lens", "Score", "Orientation", "Summary", "Drivers"],
        lens_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_History",
        "tblHistory",
        ["Series", "Run Index", "Score"],
        history_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_TrendMatrix",
        "tblTrendMatrix",
        ["Repo"] + [f"Run {index}" for index in range(1, TREND_HISTORY_WINDOW + 1)],
        trend_matrix_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_PortfolioHistory",
        "tblPortfolioHistory",
        [
            "Run Index",
            "Date",
            "Average Score",
            "Repos Audited",
            "Shipped",
            "Functional",
            "Security Avg",
            "Review Emitted",
            "Campaign Drift",
            "Governance Drift",
        ],
        portfolio_history_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_Rollups",
        "tblRollups",
        ["Profile", "Collection", "Lens", "Repo Count", "Average Lens Score", "Top Repo", "Top Profile Score"],
        rollup_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_ReviewTargets",
        "tblReviewTargets",
        ["Repo", "Title", "Severity", "Next Step", "Decision Hint", "Safe To Defer"],
        review_target_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_ReviewHistory",
        "tblReviewHistoryData",
        ["Review ID", "Source Run", "Generated", "Materiality", "Changes", "Status", "Decision State", "Sync State", "Safe To Defer", "Emitted"],
        review_history_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_Security",
        "tblSecurityData",
        ["Repo", "Label", "Score", "Secrets", "Dangerous Files", "SECURITY.md", "Dependabot", "Evidence"],
        security_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_SecurityControls",
        "tblSecurityControls",
        ["Repo", "Control", "Status", "Source", "Details"],
        security_control_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_SecurityProviders",
        "tblSecurityProviders",
        ["Repo", "Provider", "Available", "Score", "Reason"],
        security_provider_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_SecurityAlerts",
        "tblSecurityAlerts",
        ["Repo", "Alert Type", "Open Count", "Status"],
        security_alert_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_Actions",
        "tblActions",
        ["Repo", "Key", "Title", "Lens", "Effort", "Confidence", "Expected Lens Delta", "Expected Tier Movement", "Rationale"],
        action_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_Collections",
        "tblCollections",
        ["Collection", "Repo", "Rank", "Reason", "Description"],
        collection_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_PortfolioCatalog",
        "tblPortfolioCatalogData",
        [
            "Repo",
            "Full Name",
            "Owner",
            "Team",
            "Purpose",
            "Lifecycle",
            "Criticality",
            "Review Cadence",
            "Disposition",
            "Maturity Program",
            "Target Maturity",
            "Notes",
            "Intent Alignment",
            "Intent Alignment Reason",
            "Catalog Line",
        ],
        portfolio_catalog_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_Scorecards",
        "tblScorecardsData",
        [
            "Repo",
            "Full Name",
            "Program",
            "Program Label",
            "Score",
            "Maturity Level",
            "Target Maturity",
            "Status",
            "Passed Rules",
            "Applicable Rules",
            "Failed Rule Keys",
            "Top Gaps",
            "Summary",
        ],
        scorecard_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_ImplementationHotspots",
        "tblImplementationHotspotsData",
        [
            "Repo",
            "Full Name",
            "Scope",
            "Path",
            "Module",
            "Category",
            "Pressure Score",
            "Suggestion Type",
            "Why It Matters",
            "Suggested First Move",
            "Signal Summary",
        ],
        implementation_hotspot_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_OperatorOutcomes",
        "tblOperatorOutcomesData",
        ["Metric", "Status", "Value", "Numerator", "Denominator", "Summary"],
        operator_outcome_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_ActionSyncOutcomes",
        "tblActionSyncOutcomesData",
        [
            "Campaign Type",
            "Label",
            "Latest Target",
            "Latest Run Mode",
            "Recent Apply Count",
            "Monitored Repo Count",
            "Monitoring State",
            "Pressure Effect",
            "Drift State",
            "Reopen State",
            "Rollback State",
            "Follow-Up Recommendation",
            "Top Repos",
            "Summary",
        ],
        action_sync_outcome_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_CampaignTuning",
        "tblCampaignTuningData",
        [
            "Campaign Type",
            "Label",
            "Tuning Status",
            "Recommendation Bias",
            "Judged Count",
            "Monitor Now Count",
            "Holding Clean Rate",
            "Drift Return Rate",
            "Reopen Rate",
            "Rollback Watch Rate",
            "Pressure Reduction Rate",
            "Summary",
        ],
        campaign_tuning_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_InterventionLedger",
        "tblInterventionLedgerData",
        [
            "Repo",
            "Latest Tier",
            "Latest Score",
            "Recent Intervention Count",
            "Last Intervention",
            "Pressure Trend",
            "Hotspot Persistence",
            "Scorecard Trend",
            "Campaign Follow Through",
            "Historical Intelligence Status",
            "Summary",
        ],
        intervention_ledger_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_ActionSyncAutomation",
        "tblActionSyncAutomationData",
        [
            "Campaign Type",
            "Label",
            "Automation Posture",
            "Review Required",
            "Requires Approval",
            "Recommended Command",
            "Recommended Follow Up",
            "Summary",
        ],
        action_sync_automation_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_ApprovalLedger",
        "tblApprovalLedgerData",
        [
            "Approval ID",
            "Subject Type",
            "Subject Key",
            "Label",
            "Approval State",
            "Source Run ID",
            "Fingerprint",
            "Approved At",
            "Approved By",
            "Approval Ready",
            "Apply Ready After Approval",
            "Approval Command",
            "Manual Apply Command",
            "Summary",
        ],
        approval_ledger_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_Scenarios",
        "tblScenarios",
        ["Key", "Title", "Lens", "Repo Count", "Average Expected Lens Delta", "Projected Tier Promotions"],
        scenario_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_Governance",
        "tblGovernancePreview",
        ["Repo", "Key", "Priority", "Title", "Expected Lift", "Effort", "Source", "Why"],
        governance_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_Campaigns",
        "tblCampaigns",
        ["Campaign Type", "Label", "Profile", "Collection", "Actions", "Repos"],
        campaign_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_Writeback",
        "tblWriteback",
        ["Repo", "Target", "Status", "URL", "Before", "After"],
        writeback_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_OperatorQueue",
        "tblOperatorQueueData",
        [
            "Item ID",
            "Repo",
            "Kind",
            "Lane",
            "Priority",
            "Title",
            "Summary",
            "Recommended Action",
            "Source Run",
            "Age Days",
            "Links",
            "Follow-Through Age Runs",
            "Follow-Through Status",
            "Follow-Through Checkpoint Status",
            "Follow-Through Summary",
            "Follow-Through Last Touch",
            "Follow-Through Next Checkpoint",
            "Follow-Through Evidence Hint",
            "Follow-Through Escalation Status",
            "Follow-Through Escalation Summary",
            "Follow-Through Escalation Reason",
            "Follow-Through Recovery Age Runs",
            "Follow-Through Recovery Status",
            "Follow-Through Recovery Summary",
            "Follow-Through Recovery Reason",
            "Follow-Through Recovery Persistence Age Runs",
            "Follow-Through Recovery Persistence Status",
            "Follow-Through Recovery Persistence Summary",
            "Follow-Through Recovery Persistence Reason",
            "Follow-Through Relapse Churn Status",
            "Follow-Through Relapse Churn Summary",
            "Follow-Through Relapse Churn Reason",
            "Follow-Through Recovery Freshness Age Runs",
            "Follow-Through Recovery Freshness Status",
            "Follow-Through Recovery Freshness Summary",
            "Follow-Through Recovery Freshness Reason",
            "Follow-Through Recovery Decay Status",
            "Follow-Through Recovery Decay Summary",
            "Follow-Through Recovery Decay Reason",
            "Follow-Through Recovery Memory Reset Status",
            "Follow-Through Recovery Memory Reset Summary",
            "Follow-Through Recovery Memory Reset Reason",
            "Follow-Through Recovery Rebuild Strength Age Runs",
            "Follow-Through Recovery Rebuild Strength Status",
            "Follow-Through Recovery Rebuild Strength Summary",
            "Follow-Through Recovery Rebuild Strength Reason",
            "Follow-Through Recovery Reacquisition Status",
            "Follow-Through Recovery Reacquisition Summary",
            "Follow-Through Recovery Reacquisition Reason",
            "Follow-Through Recovery Reacquisition Durability Age Runs",
            "Follow-Through Recovery Reacquisition Durability Status",
            "Follow-Through Recovery Reacquisition Durability Summary",
            "Follow-Through Recovery Reacquisition Durability Reason",
            "Follow-Through Recovery Reacquisition Consolidation Status",
            "Follow-Through Recovery Reacquisition Consolidation Summary",
            "Follow-Through Recovery Reacquisition Consolidation Reason",
            "Follow-Through Reacquisition Softening Decay Age Runs",
            "Follow-Through Reacquisition Softening Decay Status",
            "Follow-Through Reacquisition Softening Decay Summary",
            "Follow-Through Reacquisition Softening Decay Reason",
            "Follow-Through Reacquisition Confidence Retirement Status",
            "Follow-Through Reacquisition Confidence Retirement Summary",
            "Follow-Through Reacquisition Confidence Retirement Reason",
            "Follow-Through Reacquisition Revalidation Recovery Age Runs",
            "Follow-Through Reacquisition Revalidation Recovery Status",
            "Follow-Through Reacquisition Revalidation Recovery Summary",
            "Follow-Through Reacquisition Revalidation Recovery Reason",
            "Catalog Line",
            "Intent Alignment",
            "Intent Alignment Reason",
            "Scorecard Line",
            "Maturity Gap Summary",
            "Action Sync Stage",
            "Action Sync Reason",
            "Suggested Campaign",
            "Suggested Writeback Target",
            "Action Sync Line",
            "Apply Packet State",
            "Apply Packet Summary",
            "Apply Packet Command",
            "Post-Apply State",
            "Post-Apply Summary",
            "Post-Apply Line",
            "Campaign Tuning Status",
            "Campaign Tuning Summary",
            "Campaign Tuning Line",
            "Historical Intelligence Status",
            "Historical Intelligence Summary",
            "Historical Intelligence Line",
            "Approval State",
            "Approval Summary",
            "Approval Line",
        ],
        operator_queue_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_OperatorRepoRollups",
        "tblOperatorRepoRollups",
        ["Repo", "Total Items", "Blocked", "Urgent", "Ready", "Deferred", "Primary Kind", "Top Priority", "Top Title", "Recommended Action"],
        operator_repo_rollups,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_MaterialChangeRollups",
        "tblMaterialChangeRollups",
        ["Repo", "Change Type", "Count", "Max Severity", "Sample Title"],
        material_rollups,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_RepoDetail",
        "tblRepoDetailData",
        [
            "Repo",
            "URL",
            "Language",
            "Description",
            "Overall Score",
            "Interest Score",
            "Grade",
            "Tier",
            "Badges",
            "Flags",
            "Collections",
            "Security Label",
            "Security Score",
            "Ship Lens Summary",
            "Momentum Lens Summary",
            "Security Lens Summary",
            "Portfolio Fit Summary",
            "Trend Sparkline",
            "Top Positive Drivers",
            "Top Negative Drivers",
            "Next Tier Gap Summary",
            "Next Best Action",
            "Next Best Action Rationale",
            "Top Hotspot 1",
            "Top Hotspot 2",
            "Top Hotspot 3",
            "Top Action 1",
            "Top Action 2",
            "Top Action 3",
            "Last Movement",
            "Recent Change Summary",
            "Follow-Through Status",
            "Follow-Through Summary",
            "Checkpoint Timing",
            "Escalation",
            "Escalation Summary",
            "Recovery / Retirement",
            "Recovery / Retirement Summary",
            "Recovery Persistence",
            "Recovery Persistence Summary",
            "Relapse Churn",
            "Relapse Churn Summary",
            "Recovery Freshness",
            "Recovery Freshness Summary",
            "Recovery Memory Reset",
            "Recovery Memory Reset Summary",
            "Recovery Rebuild Strength",
            "Recovery Rebuild Strength Summary",
            "Recovery Reacquisition",
            "Recovery Reacquisition Summary",
            "Reacquisition Durability",
            "Reacquisition Durability Summary",
            "Reacquisition Confidence",
            "Reacquisition Confidence Summary",
            "Reacquisition Softening Decay",
            "Reacquisition Softening Decay Summary",
            "Reacquisition Confidence Retirement",
            "Reacquisition Confidence Retirement Summary",
            "Revalidation Recovery",
            "Revalidation Recovery Summary",
            "What Would Count As Progress",
            "Catalog",
            "Intent Alignment",
            "Scorecard",
            "Maturity Gap",
            "Where To Start Summary",
            "Implementation Hotspot 1",
            "Implementation Hotspot 2",
            "Implementation Hotspot 3",
        ],
        repo_detail_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_RepoDimensionRollups",
        "tblRepoDimensionRollups",
        ["Lookup Key", "Repo", "Rank", "Dimension", "Score", "Summary"],
        repo_dimension_rollup_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_RepoHistoryRollups",
        "tblRepoHistoryRollups",
        ["Repo", "Run Index", "Score", "Sparkline"],
        repo_history_rollup_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_RunChangeRollups",
        "tblRunChangeRollups",
        ["Metric", "Value", "Summary"],
        run_change_rollup_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_RunChangeRepoData",
        "tblRunChangeRepoData",
        ["Section", "Repo", "Delta", "Old Tier", "New Tier", "Security", "Hotspots", "Collections", "Summary"],
        run_change_repo_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Lookups",
        "tblLookups",
        ["Type", "Key", "Value"],
        lookup_rows,
    )


def _build_security_controls(wb: Workbook, data: dict) -> None:
    ws = _get_or_create_sheet(wb, "Security Controls")
    ws.sheet_properties.tabColor = "0F766E"
    _configure_sheet_view(ws, zoom=105, show_grid_lines=True)
    headers = ["Repo", "SECURITY.md", "Dependabot", "Dependency Graph", "SBOM", "Code Scanning", "Secret Scanning"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws, 1, len(headers))
    ws.freeze_panes = "B2"

    audits = sorted(data.get("audits", []), key=lambda audit: audit.get("security_posture", {}).get("score", 0.0))
    for row, audit in enumerate(audits, 2):
        posture = audit.get("security_posture", {})
        github = posture.get("github", {})
        values = [
            audit.get("metadata", {}).get("name", ""),
            "Yes" if posture.get("has_security_md") else "No",
            "Yes" if posture.get("has_dependabot") else "No",
            github.get("dependency_graph_status", "unavailable"),
            github.get("sbom_status", "unavailable"),
            github.get("code_scanning_status", "unavailable"),
            github.get("secret_scanning_status", "unavailable"),
        ]
        for col, value in enumerate(values, 1):
            style_data_cell(ws.cell(row=row, column=col, value=value), "left" if col == 1 else "center")

    max_row = len(audits) + 1
    if max_row > 1:
        apply_zebra_stripes(ws, 2, max_row, len(headers))
        _add_table(ws, "tblSecurityControlsView", len(headers), max_row)
    auto_width(ws, len(headers), max_row)


def _build_supply_chain(wb: Workbook, data: dict) -> None:
    ws = _get_or_create_sheet(wb, "Supply Chain")
    ws.sheet_properties.tabColor = "7C3AED"
    _configure_sheet_view(ws, zoom=105, show_grid_lines=True)
    headers = ["Repo", "Security Score", "Dependency Graph", "SBOM", "Scorecard", "Top Recommendation"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws, 1, len(headers))
    ws.freeze_panes = "B2"

    audits = sorted(data.get("audits", []), key=lambda audit: audit.get("security_posture", {}).get("score", 0.0))
    for row, audit in enumerate(audits, 2):
        posture = audit.get("security_posture", {})
        github = posture.get("github", {})
        scorecard = posture.get("scorecard", {})
        recommendation = next(iter(posture.get("recommendations", [])), {})
        values = [
            audit.get("metadata", {}).get("name", ""),
            posture.get("score", 0.0),
            github.get("dependency_graph_status", "unavailable"),
            github.get("sbom_status", "unavailable"),
            scorecard.get("score", ""),
            recommendation.get("title", ""),
        ]
        for col, value in enumerate(values, 1):
            style_data_cell(ws.cell(row=row, column=col, value=value), "center" if col != 1 and col != 6 else "left")

    max_row = len(audits) + 1
    if max_row > 1:
        apply_zebra_stripes(ws, 2, max_row, len(headers))
        _add_table(ws, "tblSupplyChain", len(headers), max_row)
    auto_width(ws, len(headers), max_row)


def _build_security_debt(wb: Workbook, data: dict) -> None:
    ws = _get_or_create_sheet(wb, "Security Debt")
    ws.sheet_properties.tabColor = "B91C1C"
    _configure_sheet_view(ws, zoom=105, show_grid_lines=True)
    headers = ["Repo", "Priority", "Action", "Expected Lift", "Effort", "Source"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws, 1, len(headers))
    ws.freeze_panes = "A2"

    preview = data.get("security_governance_preview", [])
    for row, item in enumerate(preview, 2):
        values = [
            item.get("repo", ""),
            item.get("priority", "medium"),
            item.get("title", ""),
            item.get("expected_posture_lift", 0.0),
            item.get("effort", ""),
            item.get("source", ""),
        ]
        for col, value in enumerate(values, 1):
            style_data_cell(ws.cell(row=row, column=col, value=value), "center" if col in {2, 4, 5, 6} else "left")

    max_row = len(preview) + 1
    if max_row > 1:
        apply_zebra_stripes(ws, 2, max_row, len(headers))
        _add_table(ws, "tblSecurityDebt", len(headers), max_row)
    auto_width(ws, len(headers), max_row)


def _build_campaigns(wb: Workbook, data: dict) -> None:
    ws = _get_or_create_sheet(wb, "Campaigns")
    ws.sheet_properties.tabColor = "7C3AED"
    _configure_sheet_view(ws, zoom=115, show_grid_lines=False)
    summary = data.get("campaign_summary", {})
    _set_sheet_header(
        ws,
        "Campaigns",
        "Managed campaign state stays local-authoritative here. This sheet is where you see open work, stale items, and whether there is anything to reconcile.",
        width=8,
    )
    preview_rows = data.get("writeback_preview", {}).get("repos", [])
    github_projects = data.get("writeback_preview", {}).get("github_projects", {}) or {}
    campaign_requested = bool(summary.get("campaign_type") or summary.get("label"))
    if not campaign_requested:
        request_state = "No campaign requested in this run."
    else:
        request_state = "Campaign requested from the current report facts."
    if not preview_rows:
        row_state = "Campaign requested but no current rows matched." if campaign_requested else "No current rows because no managed campaign was requested."
    else:
        row_state = "Campaign rows are present. External mutation stays manual until writeback apply is explicitly requested."
    summary_end_row = _write_key_value_block(
        ws,
        4,
        1,
        [
            ("Campaign", summary.get("label", summary.get("campaign_type", "No active campaign"))),
            ("Request State", request_state),
            ("Row State", row_state),
            ("Profile", summary.get("portfolio_profile", "default")),
            ("Collection", summary.get("collection_name") or "all"),
            ("Actions", summary.get("action_count", 0)),
            ("Repos", summary.get("repo_count", 0)),
            ("Sync Mode", data.get("writeback_preview", {}).get("sync_mode", "reconcile")),
            (
                "GitHub Projects",
                (
                    f"{github_projects.get('status', 'disabled')} "
                    f"({github_projects.get('project_owner', '—')} #{github_projects.get('project_number', 0)})"
                    if github_projects.get("enabled")
                    else "disabled"
                ),
            ),
        ],
        title="Current Campaign State",
    )
    _write_key_value_block(
        ws,
        4,
        10,
        [
            (
                ACTION_SYNC_CANONICAL_LABELS["readiness"],
                (data.get("action_sync_summary") or {}).get(
                    "summary",
                    "No current campaign needs Action Sync yet, so the safest next move is to keep the story local.",
                ),
            ),
            (
                "Next Action Sync Step",
                data.get("next_action_sync_step", "Stay local for now; no current campaign needs preview or apply."),
            ),
            (
                "Apply Packet",
                (data.get("apply_readiness_summary") or {}).get(
                    "summary",
                    "No current campaign has a safe execution handoff yet, so the local story should stay local for now.",
                ),
            ),
            (
                "Command Hint",
                (data.get("next_apply_candidate") or {}).get("apply_command")
                or (data.get("next_apply_candidate") or {}).get("preview_command")
                or "No Action Sync command is recommended yet.",
            ),
            (
                ACTION_SYNC_CANONICAL_LABELS["post_apply_monitoring"],
                (data.get("campaign_outcomes_summary") or {}).get(
                    "summary",
                    "No recent Action Sync apply needs post-apply monitoring yet, so the local weekly story can stay local.",
                ),
            ),
            (
                "Next Monitoring Step",
                (data.get("next_monitoring_step") or {}).get(
                    "summary",
                    "Stay local for now; no recent Action Sync apply needs post-apply follow-up yet.",
                ),
            ),
            (
                ACTION_SYNC_CANONICAL_LABELS["campaign_tuning"],
                (data.get("campaign_tuning_summary") or {}).get(
                    "summary",
                    "Campaign tuning is neutral because there is not enough outcome history yet to bias tied recommendations.",
                ),
            ),
            (
                ACTION_SYNC_CANONICAL_LABELS["next_tie_break_candidate"],
                (data.get("next_tuned_campaign") or {}).get(
                    "summary",
                    "No current campaign needs a tuning tie-break yet.",
                ),
            ),
            (
                ACTION_SYNC_CANONICAL_LABELS["historical_portfolio_intelligence"],
                (data.get("intervention_ledger_summary") or {}).get(
                    "summary",
                    "Historical portfolio intelligence is still thin, so the weekly story should stay grounded in the current run and recent operator queue.",
                ),
            ),
            (
                "Next Historical Focus",
                (data.get("next_historical_focus") or {}).get(
                    "summary",
                    "Stay local for now; no repo has enough cross-run intervention evidence to demand a historical follow-up read yet.",
                ),
            ),
            (
                ACTION_SYNC_CANONICAL_LABELS["automation_guidance"],
                (data.get("automation_guidance_summary") or {}).get(
                    "summary",
                    "Automation guidance stays quiet until a campaign has a clearly safe preview, follow-up, or manual-only posture.",
                ),
            ),
            (
                "Next Safe Automation Step",
                (data.get("next_safe_automation_step") or {}).get(
                    "summary",
                    "Stay local for now; no current campaign has a stronger safe automation posture than manual review.",
                ),
            ),
            (
                ACTION_SYNC_CANONICAL_LABELS["approval_workflow"],
                (data.get("approval_workflow_summary") or {}).get(
                    "summary",
                    "No current approval needs review yet, so the approval workflow can stay local for now.",
                ),
            ),
            (
                ACTION_SYNC_CANONICAL_LABELS["next_approval_review"],
                (data.get("next_approval_review") or {}).get(
                    "summary",
                    "Stay local for now; no current approval needs review.",
                ),
            ),
        ],
        title=ACTION_SYNC_CANONICAL_LABELS["readiness"],
    )
    headers = ["Repo", "Issue", "Topics", "Projects", "Notion Actions", "Action IDs", "Drift", "Sync Mode"]
    start_row = summary_end_row + 2
    for col, header in enumerate(headers, 1):
        ws.cell(row=start_row, column=col, value=header)
    style_header_row(ws, start_row, len(headers))
    ws.freeze_panes = f"A{start_row + 1}"

    drift_repo_keys = {
        drift.get("repo_full_name") or drift.get("repo") or ""
        for drift in data.get("managed_state_drift", []) or []
    }
    for row, item in enumerate(preview_rows, start_row + 1):
        repo_key = item.get("repo_full_name") or item.get("repo") or ""
        ws.cell(row=row, column=1, value=item.get("repo", ""))
        ws.cell(row=row, column=2, value=item.get("issue_title", ""))
        ws.cell(row=row, column=3, value=", ".join(item.get("topics", [])))
        ws.cell(row=row, column=4, value=item.get("github_project_field_count", 0))
        ws.cell(row=row, column=5, value=item.get("notion_action_count", 0))
        ws.cell(row=row, column=6, value=", ".join(item.get("action_ids", [])))
        ws.cell(row=row, column=7, value="yes" if repo_key in drift_repo_keys else "no")
        ws.cell(row=row, column=8, value=data.get("writeback_preview", {}).get("sync_mode", "reconcile"))

    max_row = start_row + len(preview_rows)
    if preview_rows:
        apply_zebra_stripes(ws, start_row + 1, max_row, len(headers))
        _add_table(ws, "tblCampaignView", len(headers), max_row, start_row)
    else:
        ws.merge_cells(start_row=start_row + 1, start_column=1, end_row=start_row + 2, end_column=8)
        ws.cell(
            row=start_row + 1,
            column=1,
            value="No active campaign rows are present in this run. When campaign preview or apply is in use, managed repo rows will appear here with drift and sync context.",
        ).alignment = WRAP
        ws.cell(row=start_row + 1, column=1).font = SUBTITLE_FONT
    auto_width(ws, len(headers), max_row)


def _build_writeback_audit(wb: Workbook, data: dict) -> None:
    ws = _get_or_create_sheet(wb, "Writeback Audit")
    ws.sheet_properties.tabColor = "B91C1C"
    _configure_sheet_view(ws, zoom=110, show_grid_lines=False)
    _set_sheet_header(
        ws,
        "Writeback Audit",
        "This sheet summarizes writeback outcomes and rollback confidence without mutating anything by itself.",
        width=6,
    )
    results = data.get("writeback_results", {}).get("results", [])
    rollback_count = sum(1 for result in results if result.get("before") not in ({}, None, []))
    status_counts = Counter(result.get("status", "unknown") for result in results)
    _write_key_value_block(
        ws,
        4,
        1,
        [
            ("Writeback Rows", len(results)),
            ("Rollback Ready", rollback_count),
            ("Created / Updated / Closed", f"{status_counts.get('created', 0)} / {status_counts.get('updated', 0)} / {status_counts.get('closed', 0)}"),
        ],
        title="Current Writeback State",
    )
    _write_key_value_block(
        ws,
        4,
        5,
        [
            (
                ACTION_SYNC_CANONICAL_LABELS["readiness"],
                (data.get("action_sync_summary") or {}).get(
                    "summary",
                    "No current campaign needs Action Sync yet, so the safest next move is to keep the story local.",
                ),
            ),
            (
                "Next Action Sync Step",
                data.get("next_action_sync_step", "Stay local for now; no current campaign needs preview or apply."),
            ),
            (
                "Apply Packet",
                (data.get("apply_readiness_summary") or {}).get(
                    "summary",
                    "No current campaign has a safe execution handoff yet, so the local story should stay local for now.",
                ),
            ),
            (
                "Command Hint",
                (data.get("next_apply_candidate") or {}).get("apply_command")
                or (data.get("next_apply_candidate") or {}).get("preview_command")
                or "No Action Sync command is recommended yet.",
            ),
            (
                ACTION_SYNC_CANONICAL_LABELS["post_apply_monitoring"],
                (data.get("campaign_outcomes_summary") or {}).get(
                    "summary",
                    "No recent Action Sync apply needs post-apply monitoring yet, so the local weekly story can stay local.",
                ),
            ),
            (
                "Next Monitoring Step",
                (data.get("next_monitoring_step") or {}).get(
                    "summary",
                    "Stay local for now; no recent Action Sync apply needs post-apply follow-up yet.",
                ),
            ),
            (
                ACTION_SYNC_CANONICAL_LABELS["campaign_tuning"],
                (data.get("campaign_tuning_summary") or {}).get(
                    "summary",
                    "Campaign tuning is neutral because there is not enough outcome history yet to bias tied recommendations.",
                ),
            ),
            (
                ACTION_SYNC_CANONICAL_LABELS["next_tie_break_candidate"],
                (data.get("next_tuned_campaign") or {}).get(
                    "summary",
                    "No current campaign needs a tuning tie-break yet.",
                ),
            ),
            (
                ACTION_SYNC_CANONICAL_LABELS["historical_portfolio_intelligence"],
                (data.get("intervention_ledger_summary") or {}).get(
                    "summary",
                    "Historical portfolio intelligence is still thin, so the weekly story should stay grounded in the current run and recent operator queue.",
                ),
            ),
            (
                "Next Historical Focus",
                (data.get("next_historical_focus") or {}).get(
                    "summary",
                    "Stay local for now; no repo has enough cross-run intervention evidence to demand a historical follow-up read yet.",
                ),
            ),
            (
                ACTION_SYNC_CANONICAL_LABELS["automation_guidance"],
                (data.get("automation_guidance_summary") or {}).get(
                    "summary",
                    "Automation guidance stays quiet until a campaign has a clearly safe preview, follow-up, or manual-only posture.",
                ),
            ),
            (
                "Next Safe Automation Step",
                (data.get("next_safe_automation_step") or {}).get(
                    "summary",
                    "Stay local for now; no current campaign has a stronger safe automation posture than manual review.",
                ),
            ),
            (
                ACTION_SYNC_CANONICAL_LABELS["approval_workflow"],
                (data.get("approval_workflow_summary") or {}).get(
                    "summary",
                    "No current approval needs review yet, so the approval workflow can stay local for now.",
                ),
            ),
            (
                ACTION_SYNC_CANONICAL_LABELS["next_approval_review"],
                (data.get("next_approval_review") or {}).get(
                    "summary",
                    "Stay local for now; no current approval needs review.",
                ),
            ),
        ],
        title=ACTION_SYNC_CANONICAL_LABELS["readiness"],
    )
    headers = ["Repo", "Target", "Status", "Rollback", "URL", "Details"]
    start_row = 10
    for col, header in enumerate(headers, 1):
        ws.cell(row=start_row, column=col, value=header)
    style_header_row(ws, start_row, len(headers))
    ws.freeze_panes = "A11"

    for row, result in enumerate(results, start_row + 1):
        ws.cell(row=row, column=1, value=result.get("repo_full_name", ""))
        ws.cell(row=row, column=2, value=result.get("target", ""))
        ws.cell(row=row, column=3, value=result.get("status", ""))
        ws.cell(row=row, column=4, value="yes" if result.get("before") not in ({}, None, []) else "partial")
        ws.cell(row=row, column=5, value=result.get("url", ""))
        ws.cell(row=row, column=6, value=json.dumps(result))

    max_row = len(results) + start_row
    if results:
        apply_zebra_stripes(ws, start_row + 1, max_row, len(headers))
        _add_table(ws, "tblWritebackAudit", len(headers), max_row, start_row=start_row)
    else:
        ws.merge_cells(start_row=start_row + 1, start_column=1, end_row=start_row + 2, end_column=6)
        ws.cell(
            row=start_row + 1,
            column=1,
            value="No writeback results are recorded for this run. Preview-only workflows and audit-only runs will leave this sheet intentionally empty.",
        ).alignment = WRAP
        ws.cell(row=start_row + 1, column=1).font = SUBTITLE_FONT
    auto_width(ws, len(headers), max_row)


def _build_portfolio_explorer(
    wb: Workbook,
    data: dict,
    *,
    portfolio_profile: str = "default",
    collection: str | None = None,
) -> None:
    from src.analyst_views import build_analyst_context

    context = build_analyst_context(data, profile_name=portfolio_profile, collection_name=collection)
    ws = _get_or_create_sheet(wb, "Portfolio Explorer")
    ws.sheet_properties.tabColor = "1D4ED8"
    _configure_sheet_view(ws, zoom=110, show_grid_lines=True)
    _set_sheet_header(
        ws,
        "Portfolio Explorer",
        "Use this sheet to rank the portfolio, sort by profile-aware score, and drill from summary into repo-level facts.",
        width=10,
    )
    ws.merge_cells("A3:O3")
    ws["A3"] = "How to use this sheet: sort by Profile Score first, then use the catalog columns to separate intentional experiments from maintained assets before drilling in."
    ws["A3"].font = SUBTITLE_FONT
    ws["A3"].alignment = WRAP
    headers = [
        "Repo", "Profile Score", "Overall", "Interest", "Tier", "Collections",
        "Lifecycle", "Criticality", "Disposition", "Maturity", "Scorecard Gap", "Security", "Hotspots", "Top Hotspot", "Primary Action",
    ]
    start_row = 5
    for col, header in enumerate(headers, 1):
        ws.cell(row=start_row, column=col, value=header)
    style_header_row(ws, start_row, len(headers))
    ws.freeze_panes = "B6"

    for row, entry in enumerate(context["ranked_audits"], start_row + 1):
        audit = entry["audit"]
        top_action = audit.get("action_candidates", [{}])[0].get("title", "") if audit.get("action_candidates") else ""
        values = [
            entry["name"],
            entry["profile_score"],
            entry["overall_score"],
            entry["interest_score"],
            entry["tier"],
            ", ".join(entry["collections"]),
            audit.get("portfolio_catalog", {}).get("lifecycle_state", "") or "—",
            audit.get("portfolio_catalog", {}).get("criticality", "") or "—",
            audit.get("portfolio_catalog", {}).get("intended_disposition", "") or "—",
            audit.get("scorecard", {}).get("maturity_level", "") or "—",
            build_maturity_gap_summary(audit),
            entry["security_label"],
            entry["hotspot_count"],
            entry["primary_hotspot"],
            top_action,
        ]
        for col, value in enumerate(values, 1):
            style_data_cell(ws.cell(row=row, column=col, value=value), "center" if col in {2, 3, 4, 8} else "left")

    max_row = len(context["ranked_audits"]) + start_row
    if max_row > start_row:
        apply_zebra_stripes(ws, start_row + 1, max_row, len(headers))
        _add_table(ws, "tblPortfolioExplorer", len(headers), max_row, start_row=start_row)
    auto_width(ws, len(headers), max_row)


def _build_portfolio_catalog_sheet(wb: Workbook, data: dict) -> None:
    ws = _get_or_create_sheet(wb, "Portfolio Catalog")
    ws.sheet_properties.tabColor = "4F46E5"
    _configure_sheet_view(ws, zoom=110, show_grid_lines=True)
    _set_sheet_header(
        ws,
        "Portfolio Catalog",
        "Use this sheet to see what each repo is supposed to be, who owns it, and whether its current state still matches that intent.",
        width=10,
    )
    ws.merge_cells("A3:L3")
    ws["A3"] = build_portfolio_catalog_summary(data)
    ws["A3"].font = SUBTITLE_FONT
    ws["A3"].alignment = WRAP
    ws.merge_cells("A4:L4")
    ws["A4"] = build_portfolio_intent_alignment_summary(data)
    ws["A4"].font = SUBTITLE_FONT
    ws["A4"].alignment = WRAP
    headers = [
        "Repo",
        "Owner",
        "Team",
        "Purpose",
        "Lifecycle",
        "Criticality",
        "Review Cadence",
        "Disposition",
        "Maturity Program",
        "Target Maturity",
        "Intent Alignment",
        "Notes",
    ]
    start_row = 6
    for col, header in enumerate(headers, 1):
        ws.cell(row=start_row, column=col, value=header)
    style_header_row(ws, start_row, len(headers))
    ws.freeze_panes = "B7"

    audits = sorted(data.get("audits", []), key=lambda item: item.get("metadata", {}).get("name", ""))
    for row, audit in enumerate(audits, start_row + 1):
        catalog = audit.get("portfolio_catalog", {})
        values = [
            audit.get("metadata", {}).get("name", ""),
            catalog.get("owner", ""),
            catalog.get("team", ""),
            catalog.get("purpose", ""),
            catalog.get("lifecycle_state", "") or "—",
            catalog.get("criticality", "") or "—",
            catalog.get("review_cadence", "") or "—",
            catalog.get("intended_disposition", "") or "—",
            catalog.get("maturity_program", "") or "—",
            catalog.get("target_maturity", "") or "—",
            catalog.get("intent_alignment", "missing-contract"),
            catalog.get("notes", "") or "—",
        ]
        for col, value in enumerate(values, 1):
            style_data_cell(ws.cell(row=row, column=col, value=value), "left")

    max_row = start_row + len(audits)
    if audits:
        apply_zebra_stripes(ws, start_row + 1, max_row, len(headers))
        _add_table(ws, "tblPortfolioCatalog", len(headers), max_row, start_row=start_row)
    auto_width(ws, len(headers), max_row)


def _build_scorecards_sheet(wb: Workbook, data: dict) -> None:
    ws = _get_or_create_sheet(wb, "Scorecards")
    ws.sheet_properties.tabColor = "7C3AED"
    _configure_sheet_view(ws, zoom=110, show_grid_lines=True)
    _set_sheet_header(
        ws,
        "Scorecards",
        "Use this sheet to compare each repo against the maturity bar that matches its intended role.",
        width=10,
    )
    ws.merge_cells("A3:H3")
    ws["A3"] = build_scorecards_summary(data)
    ws["A3"].font = SUBTITLE_FONT
    ws["A3"].alignment = WRAP
    headers = [
        "Repo",
        "Program",
        "Maturity",
        "Target",
        "Status",
        "Score",
        "Top Gaps",
        "Summary",
    ]
    start_row = 5
    for col, header in enumerate(headers, 1):
        ws.cell(row=start_row, column=col, value=header)
    style_header_row(ws, start_row, len(headers))
    ws.freeze_panes = "B6"

    audits = sorted(data.get("audits", []), key=lambda item: item.get("metadata", {}).get("name", ""))
    for row, audit in enumerate(audits, start_row + 1):
        scorecard = audit.get("scorecard", {})
        values = [
            audit.get("metadata", {}).get("name", ""),
            scorecard.get("program_label", "") or "—",
            scorecard.get("maturity_level", "") or "—",
            scorecard.get("target_maturity", "") or "—",
            scorecard.get("status", "") or "—",
            scorecard.get("score", 0.0),
            ", ".join(scorecard.get("top_gaps", [])) or "—",
            scorecard.get("summary", "") or "—",
        ]
        for col, value in enumerate(values, 1):
            style_data_cell(ws.cell(row=row, column=col, value=value), "center" if col in {3, 4, 5, 6} else "left")

    max_row = start_row + len(audits)
    if audits:
        apply_zebra_stripes(ws, start_row + 1, max_row, len(headers))
        _add_table(ws, "tblScorecards", len(headers), max_row, start_row=start_row)
    auto_width(ws, len(headers), max_row)


def _build_by_lens(
    wb: Workbook,
    data: dict,
    *,
    portfolio_profile: str = "default",
    collection: str | None = None,
) -> None:
    from src.analyst_views import build_analyst_context

    context = build_analyst_context(data, profile_name=portfolio_profile, collection_name=collection)
    ws = _get_or_create_sheet(wb, "By Lens")
    ws.sheet_properties.tabColor = "0F766E"
    _configure_sheet_view(ws, zoom=110, show_grid_lines=True)
    _set_sheet_header(
        ws,
        "By Lens",
        "Compare the same repos through different decision lenses so you can separate shipped work, risk, momentum, and showcase value.",
        width=9,
    )
    ws.merge_cells("A3:I3")
    ws["A3"] = f"Current view: profile {portfolio_profile} | collection {collection or 'all'} | use this sheet to compare the same repo through multiple decision lenses."
    ws["A3"].font = SUBTITLE_FONT
    ws["A3"].alignment = WRAP
    lens_headers = ["Ship Readiness", "Maintenance Risk", "Showcase", "Security", "Momentum", "Portfolio Fit"]
    headers = ["Repo", "Profile Score", "Tier"] + lens_headers
    start_row = 5
    for col, header in enumerate(headers, 1):
        ws.cell(row=start_row, column=col, value=header)
    style_header_row(ws, start_row, len(headers))
    ws.freeze_panes = "B6"

    for row, entry in enumerate(context["ranked_audits"], start_row + 1):
        lenses = entry["audit"].get("lenses", {})
        values = [
            entry["name"],
            entry["profile_score"],
            entry["tier"],
            lenses.get("ship_readiness", {}).get("score", 0.0),
            lenses.get("maintenance_risk", {}).get("score", 0.0),
            lenses.get("showcase_value", {}).get("score", 0.0),
            lenses.get("security_posture", {}).get("score", 0.0),
            lenses.get("momentum", {}).get("score", 0.0),
            lenses.get("portfolio_fit", {}).get("score", 0.0),
        ]
        for col, value in enumerate(values, 1):
            style_data_cell(ws.cell(row=row, column=col, value=value), "center" if col >= 2 else "left")

    max_row = len(context["ranked_audits"]) + start_row
    if max_row > start_row:
        apply_zebra_stripes(ws, start_row + 1, max_row, len(headers))
        _add_table(ws, "tblByLens", len(headers), max_row, start_row=start_row)
    auto_width(ws, len(headers), max_row)


def _build_by_collection(
    wb: Workbook,
    data: dict,
    *,
    portfolio_profile: str = "default",
) -> None:
    from src.analyst_views import build_analyst_context

    ws = _get_or_create_sheet(wb, "By Collection")
    ws.sheet_properties.tabColor = "7C3AED"
    _configure_sheet_view(ws, zoom=115, show_grid_lines=True)
    _set_sheet_header(
        ws,
        "By Collection",
        "Use this sheet to understand which collections are concentrated, which repos lead them, and where your showcase value is clustered.",
        width=5,
    )
    ws.merge_cells("A3:E3")
    ws["A3"] = f"Current profile: {portfolio_profile}. Use this sheet to see how each collection groups related repos and where its best work sits."
    ws["A3"].font = SUBTITLE_FONT
    ws["A3"].alignment = WRAP
    headers = ["Collection", "Repos", "Description", "Top Repo", "Top Score"]
    start_row = 5
    for col, header in enumerate(headers, 1):
        ws.cell(row=start_row, column=col, value=header)
    style_header_row(ws, start_row, len(headers))
    ws.freeze_panes = "B6"

    for row, collection_name in enumerate(data.get("collections", {}).keys(), start_row + 1):
        context = build_analyst_context(data, profile_name=portfolio_profile, collection_name=collection_name)
        leaders = context.get("profile_leaderboard", {}).get("leaders", [])
        collection_data = data.get("collections", {}).get(collection_name, {})
        values = [
            collection_name,
            len(collection_data.get("repos", [])),
            collection_data.get("description", ""),
            leaders[0]["name"] if leaders else "",
            leaders[0]["profile_score"] if leaders else 0.0,
        ]
        for col, value in enumerate(values, 1):
            style_data_cell(ws.cell(row=row, column=col, value=value), "center" if col in {2, 5} else "left")

    max_row = len(data.get("collections", {})) + start_row
    if max_row > start_row:
        apply_zebra_stripes(ws, start_row + 1, max_row, len(headers))
        _add_table(ws, "tblByCollection", len(headers), max_row, start_row=start_row)
    auto_width(ws, len(headers), max_row)


def _build_trend_summary(
    wb: Workbook,
    data: dict,
    trend_data: list[dict] | None = None,
    score_history: dict[str, list[float]] | None = None,
) -> None:
    extended_trends = _extend_portfolio_trend_with_current(data, trend_data)
    extended_score_history = _extend_score_history_with_current(data, score_history)
    ws = _get_or_create_sheet(wb, "Trend Summary")
    ws.sheet_properties.tabColor = "0EA5E9"
    _configure_sheet_view(ws, zoom=115, show_grid_lines=False)
    _set_sheet_header(
        ws,
        "Trend Summary",
        "Track portfolio movement over time, then scan the short repo trendlines below to see who is actually improving or drifting.",
        width=8,
    )
    ws.merge_cells("A3:H3")
    ws["A3"] = "Use this sheet when you want portfolio-wide movement first, then repo-level trendlines second."
    ws["A3"].font = SUBTITLE_FONT
    ws["A3"].alignment = WRAP

    headers = ["Date", "Average Score", "Repos", "Shipped", "Functional", "Review Emitted", "Campaign Drift", "Governance Drift"]
    start_row = 5
    for col, header in enumerate(headers, 1):
        ws.cell(row=start_row, column=col, value=header)
    style_header_row(ws, start_row, len(headers))
    ws.freeze_panes = "A6"

    for offset, trend in enumerate(extended_trends, 1):
        values = [
            trend.get("date", ""),
            trend.get("average_score", 0.0),
            trend.get("repos_audited", 0),
            trend.get("tier_distribution", {}).get("shipped", 0),
            trend.get("tier_distribution", {}).get("functional", 0),
            "yes" if trend.get("review_emitted") else "no",
            trend.get("campaign_drift_count", 0),
            trend.get("governance_drift_count", 0),
        ]
        for col, value in enumerate(values, 1):
            style_data_cell(ws.cell(row=start_row + offset, column=col, value=value), "center" if col != 1 else "left")

    summary_row = start_row + len(extended_trends) + 3
    ws.cell(row=summary_row, column=1, value="Top Repo Trendlines").font = SECTION_FONT
    for offset, (repo_name, scores) in enumerate(sorted(extended_score_history.items())[:10], 1):
        ws.cell(row=summary_row + offset, column=1, value=repo_name)
        ws.cell(row=summary_row + offset, column=2, value=render_sparkline(scores))
        ws.cell(row=summary_row + offset, column=3, value=scores[-1] if scores else 0.0)

    max_row = summary_row + min(len(extended_score_history), 10)
    if extended_trends:
        _add_table(ws, "tblTrendSummary", len(headers), start_row + len(extended_trends), start_row=start_row)
    auto_width(ws, max(8, len(headers)), max_row)


def _build_repo_detail(wb: Workbook, data: dict) -> None:
    existing_selection = ""
    if "Repo Detail" in wb.sheetnames:
        existing_selection = str(wb["Repo Detail"]["B4"].value or "").strip()
    ws = _get_or_create_sheet(wb, "Repo Detail")
    ws.sheet_properties.tabColor = "1E40AF"
    _configure_sheet_view(ws, zoom=115, show_grid_lines=False)
    _set_sheet_header(
        ws,
        "Repo Detail",
        "Pick one repo, then use this page as the fastest single-repo briefing: score, tier, trend, risks, and next move.",
        width=10,
    )
    _write_instruction_banner(
        ws,
        3,
        8,
        "Choose one repo, skim the briefing blocks top to bottom, then jump to Run Changes or Review Queue if you need more context.",
    )
    ws.freeze_panes = "A6"

    repo_names = sorted(
        audit.get("metadata", {}).get("name", "")
        for audit in data.get("audits", [])
        if audit.get("metadata", {}).get("name")
    )
    default_repo = existing_selection if existing_selection in repo_names else (repo_names[0] if repo_names else "")
    ws["A4"] = "Select Repo"
    ws["A4"].font = SUBHEADER_FONT
    ws["B4"] = default_repo
    if repo_names:
        dv = DataValidation(
            type="list",
            formula1=f"=Data_RepoDetail!$A$2:$A${len(repo_names) + 1}",
            allow_blank=False,
            promptTitle="Repo Detail",
            prompt="Choose a repo to refresh this briefing page.",
        )
        dv.add("B4")
        ws.add_data_validation(dv)
    ws["D4"] = "GitHub"
    ws["D4"].font = SUBHEADER_FONT
    ws["E4"] = '=IFERROR(IF(VLOOKUP($B$4,Data_RepoDetail!$A:$BZ,2,FALSE)="","Repo URL unavailable",HYPERLINK(VLOOKUP($B$4,Data_RepoDetail!$A:$BZ,2,FALSE),"Open Repo")),"Repo URL unavailable")'
    ws["E4"].font = Font("Calibri", 10, bold=True, color=TEAL, underline="single")

    summary_fields = [
        ("Repo", 1, 1, 1, "No repo selected."),
        ("Language", 3, 1, 4, "Unknown"),
        ("Badges", 9, 1, 7, "None"),
        ("Overall Score", 5, 2, 1, ""),
        ("Interest Score", 6, 2, 4, ""),
        ("Flags", 10, 2, 7, "None"),
        ("Grade", 7, 3, 1, "—"),
        ("Tier", 8, 3, 4, "—"),
        ("Collections", 11, 3, 7, "—"),
        ("Security", 12, 4, 1, "unknown"),
        ("Security Score", 13, 4, 4, ""),
        ("Trend", 18, 4, 7, "No trend history yet."),
    ]
    for label, column_index, row_base, col_base, fallback in summary_fields:
        row = row_base + 5
        col = col_base
        ws.cell(row=row, column=col, value=label).font = SUBHEADER_FONT
        formula = _repo_detail_lookup_formula(column_index, fallback, allow_blank=column_index in {5, 6, 13})
        style_data_cell(ws.cell(row=row, column=col + 1, value=formula), "left")

    ws["A11"] = "Description"
    ws["A11"].font = SUBHEADER_FONT
    ws.merge_cells("B11:H11")
    ws["B11"] = _repo_detail_lookup_formula(4, "No description recorded yet.")
    ws["B11"].alignment = WRAP

    ws["A13"] = "Current State"
    ws["A13"].font = SECTION_FONT
    lens_rows = [
        ("Ship Readiness", 14),
        ("Momentum", 15),
        ("Security", 16),
        ("Portfolio Fit", 17),
    ]
    for offset, (label, column_index) in enumerate(lens_rows, 1):
        row = 13 + offset
        ws.cell(row=row, column=1, value=label).font = SUBHEADER_FONT
        style_data_cell(ws.cell(row=row, column=2, value=_repo_detail_lookup_formula(column_index, "No summary recorded yet.")), "left")

    ws["E13"] = "Why This Repo Looks This Way"
    ws["E13"].font = SECTION_FONT
    explanation_rows = [
        ("Strongest Drivers", 19),
        ("Biggest Drags", 20),
        ("Last Movement", 30),
        ("Next Tier Gap", 21),
        ("Next Best Action", 22),
        ("Why This Action", 23),
    ]
    for offset, (label, column_index) in enumerate(explanation_rows, 1):
        row = 13 + offset
        ws.cell(row=row, column=5, value=label).font = SUBHEADER_FONT
        style_data_cell(ws.cell(row=row, column=6, value=_repo_detail_lookup_formula(column_index, "No briefing detail recorded yet.")), "left")

    ws["A20"] = "Dimension Breakdown"
    ws["A20"].font = SECTION_FONT
    dimension_headers = ["Rank", "Dimension", "Score", "Summary"]
    for col, header in enumerate(dimension_headers, 1):
        ws.cell(row=21, column=col, value=header)
    style_header_row(ws, 21, len(dimension_headers))
    for rank in range(1, 7):
        row = 21 + rank
        ws.cell(row=row, column=1, value=rank)
        lookup_expr = f'$B$4&"::{rank}"'
        ws.cell(row=row, column=2, value=f'=IFERROR(VLOOKUP({lookup_expr},Data_RepoDimensionRollups!$A:$F,4,FALSE),"")')
        ws.cell(row=row, column=3, value=f'=IFERROR(VLOOKUP({lookup_expr},Data_RepoDimensionRollups!$A:$F,5,FALSE),"")')
        ws.cell(row=row, column=4, value=f'=IFERROR(VLOOKUP({lookup_expr},Data_RepoDimensionRollups!$A:$F,6,FALSE),"")')
        for col in range(1, 5):
            style_data_cell(ws.cell(row=row, column=col), "center" if col in {1, 3} else "left")

    ws["F20"] = "What Changed"
    ws["F20"].font = SECTION_FONT
    for idx in range(1, 4):
        row = 20 + idx
        ws.cell(row=row, column=6, value=f"Hotspot {idx}").font = SUBHEADER_FONT
        style_data_cell(ws.cell(row=row, column=7, value=_repo_detail_lookup_formula(23 + idx, "No hotspot recorded yet.")), "left")

    ws["A28"] = "Where To Start"
    ws["A28"].font = SECTION_FONT
    implementation_rows = [
        ("Summary", 66, "No meaningful implementation hotspot is currently surfaced."),
        ("Implementation Hotspot 1", 67, "No implementation hotspot is currently surfaced."),
        ("Implementation Hotspot 2", 68, "No second implementation hotspot is currently surfaced."),
        ("Implementation Hotspot 3", 69, "No third implementation hotspot is currently surfaced."),
    ]
    for offset, (label, column_index, fallback) in enumerate(implementation_rows, 1):
        row = 28 + offset
        ws.cell(row=row, column=1, value=label).font = SUBHEADER_FONT
        style_data_cell(ws.cell(row=row, column=2, value=_repo_detail_lookup_formula(column_index, fallback)), "left")

    ws["F25"] = "What To Do Next"
    ws["F25"].font = SECTION_FONT
    handoff_rows = [
        ("Recommended Action", 22, "No clear next action is recorded yet."),
        ("Why This Action", 23, "No action rationale is recorded yet."),
        ("Follow-Through Status", 32, "Unknown"),
        ("Follow-Through Summary", 33, "No follow-through evidence is recorded yet."),
        ("Checkpoint Timing", 34, "Unknown"),
        ("Escalation", 35, "Unknown"),
        ("Escalation Summary", 36, "No stronger follow-through escalation is currently surfaced."),
        ("Recovery / Retirement", 37, "None"),
        ("Recovery Summary", 38, "No follow-through recovery or escalation-retirement signal is currently surfaced."),
        ("Recovery Persistence", 39, "None"),
        ("Recovery Persistence Summary", 40, "No follow-through recovery persistence signal is currently surfaced."),
        ("Relapse Churn", 41, "None"),
        ("Relapse Churn Summary", 42, "No relapse churn is currently surfaced."),
        ("Recovery Freshness", 43, "None"),
        ("Recovery Freshness Summary", 44, "No follow-through recovery freshness signal is currently surfaced."),
        ("Recovery Memory Reset", 45, "None"),
        ("Recovery Memory Reset Summary", 46, "No follow-through recovery memory reset signal is currently surfaced."),
        ("Recovery Rebuild Strength", 47, "None"),
        ("Recovery Rebuild Strength Summary", 48, "No follow-through recovery rebuild-strength signal is currently surfaced."),
        ("Recovery Reacquisition", 49, "None"),
        ("Recovery Reacquisition Summary", 50, "No follow-through recovery reacquisition signal is currently surfaced."),
        ("Reacquisition Durability", 51, "None"),
        ("Reacquisition Durability Summary", 52, "No follow-through reacquisition durability signal is currently surfaced."),
        ("Reacquisition Confidence", 53, "None"),
        ("Reacquisition Confidence Summary", 54, "No follow-through reacquisition confidence-consolidation signal is currently surfaced."),
        ("Reacquisition Softening Decay", 55, "None"),
        ("Reacquisition Softening Decay Summary", 56, "No reacquisition softening-decay signal is currently surfaced."),
        ("Reacquisition Confidence Retirement", 57, "None"),
        ("Reacquisition Confidence Retirement Summary", 58, "No reacquisition confidence-retirement signal is currently surfaced."),
        ("Revalidation Recovery", 59, "None"),
        ("Revalidation Recovery Summary", 60, "No post-revalidation recovery or confidence re-earning signal is currently surfaced."),
        ("Progress Checkpoint", 61, "Use the next run or linked artifact to confirm whether the recommendation moved."),
        ("Portfolio Catalog", 62, "No portfolio catalog contract is recorded yet."),
        ("Intent Alignment", 63, "missing-contract: Intent alignment cannot be judged until a portfolio catalog contract exists."),
        ("Scorecard", 64, "Scorecard: No maturity scorecard is recorded yet."),
        ("Maturity Gap", 65, "No maturity gap summary is recorded yet."),
        ("Action Candidate 2", 28, "No second action candidate recorded yet."),
        ("Action Candidate 3", 29, "No third action candidate recorded yet."),
    ]
    for offset, (label, column_index, fallback) in enumerate(handoff_rows, 1):
        row = 25 + offset
        ws.cell(row=row, column=6, value=label).font = SUBHEADER_FONT
        style_data_cell(ws.cell(row=row, column=7, value=_repo_detail_lookup_formula(column_index, fallback)), "left")

    nav_row = 26 + len(handoff_rows)
    ws.cell(row=nav_row, column=1, value="Use Score Explainer")
    _set_internal_hyperlink(ws.cell(row=nav_row, column=2), "Score Explainer", display="Open Score Explainer")
    ws.cell(row=nav_row, column=4, value="Go To Explorer")
    _set_internal_hyperlink(ws.cell(row=nav_row, column=5), "Portfolio Explorer", display="Open Explorer")
    ws.cell(row=nav_row, column=6, value="Go To Queue")
    _set_internal_hyperlink(ws.cell(row=nav_row, column=7), "Review Queue", display="Open Review Queue")
    auto_width(ws, 8, nav_row)


def _build_run_changes(wb: Workbook, data: dict, diff_data: dict | None) -> None:
    ws = _get_or_create_sheet(wb, "Run Changes")
    ws.sheet_properties.tabColor = "0891B2"
    _configure_sheet_view(ws, zoom=115, show_grid_lines=False)
    _set_sheet_header(
        ws,
        "Run Changes",
        "Use this sheet to answer one question quickly: what moved since the last run, and what actually needs follow-through now?",
        width=9,
    )
    _write_instruction_banner(
        ws,
        4,
        9,
        "Read this page top to bottom: scan the summary cards first, then check regressions, blocked items, and new security or governance pressure.",
    )
    ws.freeze_panes = "A9"

    counts = build_run_change_counts(diff_data)
    summary = (data.get("run_change_summary") or build_run_change_summary(diff_data))
    ws.merge_cells("A3:I3")
    ws["A3"] = summary
    ws["A3"].font = SUBTITLE_FONT
    ws["A3"].alignment = WRAP
    ws["A5"] = "Comparison Window"
    ws["A5"].font = SUBHEADER_FONT
    ws["B5"] = (
        f"{(diff_data or {}).get('previous_date', '')[:10]} -> {(diff_data or {}).get('current_date', data.get('generated_at', ''))[:10]}"
        if diff_data
        else no_baseline_summary()
    )
    ws["B5"].alignment = WRAP

    summary_cards = [
        ("Improvements", counts.get("score_improvements", 0)),
        ("Regressions", counts.get("score_regressions", 0)),
        ("Promotions", counts.get("tier_promotions", 0)),
        ("Demotions", counts.get("tier_demotions", 0)),
        ("Security", counts.get("security_changes", 0)),
        ("Governance", counts.get("collection_changes", 0)),
    ]
    for offset, (label, value) in enumerate(summary_cards):
        write_kpi_card(ws, 6, 1 + offset * 2, label, value)

    row = 9
    sections: list[tuple[str, list[list[object]], list[str]]] = []
    improvements = sorted((diff_data or {}).get("score_changes", []), key=lambda item: item.get("delta", 0.0), reverse=True)
    regressions = sorted((diff_data or {}).get("score_changes", []), key=lambda item: item.get("delta", 0.0))[:5]
    sections.append((
        "Biggest Score Gains",
        [[item.get("name", ""), round(item.get("delta", 0.0), 3), round(item.get("new_score", 0.0), 3)] for item in improvements[:5]],
        ["Repo", "Delta", "New Score"],
    ))
    sections.append((
        "Biggest Regressions",
        [[item.get("name", ""), round(item.get("delta", 0.0), 3), round(item.get("new_score", 0.0), 3)] for item in regressions[:5]],
        ["Repo", "Delta", "New Score"],
    ))
    tier_changes = (diff_data or {}).get("tier_changes", [])
    promotions = [item for item in tier_changes if item.get("direction") == "promotion"][:5]
    demotions = [item for item in tier_changes if item.get("direction") == "demotion"][:5]
    sections.append((
        "Tier Promotions / Demotions",
        [[item.get("name", ""), item.get("old_tier", ""), item.get("new_tier", ""), item.get("direction", "")] for item in promotions + demotions],
        ["Repo", "Old Tier", "New Tier", "Movement"],
    ))
    blocked_items = [item for item in (data.get("operator_queue") or []) if item.get("lane") == "blocked"][:5]
    sections.append((
        "Newly Blocked Items",
        [[item.get("repo", ""), item.get("title", ""), item.get("lane_reason", "") or item.get("summary", "")] for item in blocked_items],
        ["Repo", "Item", "Why"],
    ))
    reopened = [item for item in (data.get("material_changes") or []) if "reopen" in str(item.get("change_type", "")).lower()][:5]
    sections.append((
        "Reopened Items",
        [[item.get("repo", ""), item.get("title", ""), item.get("change_type", "")] for item in reopened],
        ["Repo", "Title", "Type"],
    ))
    pressure_rows = []
    for item in (data.get("governance_drift") or [])[:5]:
        pressure_rows.append([item.get("repo_full_name", ""), item.get("drift_type", ""), "governance"])
    for item in (diff_data or {}).get("security_changes", [])[:5]:
        pressure_rows.append([item.get("name", ""), item.get("new_label", ""), "security"])
    sections.append((
        "New Security / Governance Pressure",
        pressure_rows[:5],
        ["Repo", "Signal", "Area"],
    ))

    for title, rows, headers in sections:
        ws.cell(row=row, column=1, value=title).font = SECTION_FONT
        header_row = row + 1
        for col, header in enumerate(headers, 1):
            ws.cell(row=header_row, column=col, value=header)
        style_header_row(ws, header_row, len(headers))
        if not rows:
            rows = [["No movement to call out yet.", "", ""][: len(headers)]]
        for offset, values in enumerate(rows, 1):
            for col, value in enumerate(values, 1):
                style_data_cell(ws.cell(row=header_row + offset, column=col, value=value), "center" if isinstance(value, (int, float)) else "left")
        if rows:
            apply_zebra_stripes(ws, header_row + 1, header_row + len(rows), len(headers))
        row = header_row + len(rows) + 2

    auto_width(ws, 9, row)


def _build_review_queue(wb: Workbook, data: dict, *, excel_mode: str = "standard") -> None:
    ws = _get_or_create_sheet(wb, "Review Queue")
    ws.sheet_properties.tabColor = "2563EB"
    _configure_sheet_view(ws, zoom=115, show_grid_lines=False)
    _set_sheet_header(
        ws,
        "Review Queue",
        "Start with the summary strip, then use the full queue below when you need row-level facts and decision context.",
        width=12,
    )
    _write_instruction_banner(
        ws,
        3,
        10,
        "Work this page in lane order: clear Blocked first, handle Needs Attention Now next, and only then move into Ready for Manual Action or Safe to Defer.",
    )
    counts = _operator_counts(data)
    queue = data.get("operator_queue", []) or []
    queue_pressure_summary = build_queue_pressure_summary(data)
    top_recommendation_summary = build_top_recommendation_summary(data)
    material_changes = data.get("material_changes", []) or []
    ordered_queue = _ordered_queue_items(queue)
    repo_rollups = _build_workbook_rollups(data)[1]
    top_issue_families = _summarize_top_issue_families(material_changes)
    trend_status, trend_summary, primary_target, resolution_counts = _operator_trend_values(data)
    primary_target_reason, closure_guidance, aging_pressure = _operator_accountability_values(data)
    last_intervention, last_outcome, resolution_evidence, recovery_counts = _operator_decision_memory_values(data)
    primary_confidence, confidence_reason, next_action_confidence, recommendation_quality = _operator_confidence_values(data)
    trust_policy, trust_policy_reason, adaptive_confidence_summary = _operator_trust_values(data)
    exception_status, exception_reason, drift_status, drift_summary = _operator_exception_values(data)
    trust_recovery_status, trust_recovery_reason, exception_pattern_status, exception_pattern_summary = _operator_learning_values(data)
    recovery_confidence, retirement_status, retirement_reason, retirement_summary = _operator_retirement_values(data)
    policy_debt_status, policy_debt_reason, class_normalization_status, trust_normalization_summary = _operator_class_normalization_values(data)
    class_memory_status, class_memory_reason, class_decay_status, class_decay_summary = _operator_class_memory_values(data)
    class_reweight_direction, class_reweight_score, class_reweight_reason, class_reweight_summary = _operator_class_reweight_values(data)
    class_momentum_status, class_reweight_stability, class_momentum_summary = _operator_class_momentum_values(data)
    class_transition_health, class_transition_resolution, class_transition_summary = _operator_class_transition_values(data)
    (
        transition_closure_confidence,
        transition_likely_outcome,
        pending_debt_freshness,
        closure_forecast_direction,
        reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery,
        reset_reentry_rebuild_reentry_restore_rerererestore,
        reset_reentry_rebuild_reentry_restore_rerererestore_persistence,
        reset_reentry_rebuild_reentry_restore_rerererestore_churn,
        transition_closure_summary,
    ) = _operator_transition_closure_values(data)
    calibration_status, calibration_summary, high_hit_rate, reopened_recommendations = _operator_calibration_values(data)
    summary_rows = [
        ("Headline", (data.get("operator_summary") or {}).get("headline", "Review activity is available below.")),
        ("Queue Counts", _format_lane_counts(counts)),
        ("Queue Pressure", queue_pressure_summary),
        ("Total Queue Items", len(queue)),
        (
            "Immediate Focus",
            (ordered_queue[0].get("recommended_action") or ordered_queue[0].get("title", "")) if ordered_queue else "No immediate queue item is open.",
        ),
        ("Top Recommendation", top_recommendation_summary),
        ("Top Issue Family", f"{top_issue_families[0][0]} ({top_issue_families[0][1]})" if top_issue_families else "No material change families"),
    ]
    if excel_mode == "standard":
        summary_rows.extend(
            [
                ("Trend", f"{trend_status} — {trend_summary}"),
                ("Primary Target", primary_target),
                ("Resolution Counts", resolution_counts),
                ("Why Top Target", primary_target_reason),
                ("Closure Guidance", closure_guidance),
                ("Aging Pressure", aging_pressure),
                ("What We Tried", last_intervention),
                ("Last Outcome", last_outcome),
                ("Resolution Evidence", resolution_evidence),
                ("Recovery Counts", recovery_counts),
                ("Recommendation Confidence", primary_confidence),
                ("Confidence Rationale", confidence_reason),
                ("Next Action Confidence", next_action_confidence),
                ("Trust Policy", trust_policy),
                ("Trust Rationale", trust_policy_reason),
                ("Trust Exception", f"{exception_status} — {exception_reason}"),
                ("Trust Recovery", f"{trust_recovery_status} — {trust_recovery_reason}"),
                ("Recovery Confidence", recovery_confidence),
                ("Exception Retirement", f"{retirement_status} — {retirement_reason}"),
                ("Retirement Summary", retirement_summary),
                ("Policy Debt", f"{policy_debt_status} — {policy_debt_reason}"),
                ("Class Normalization", f"{class_normalization_status} — {trust_normalization_summary}"),
                ("Class Memory", f"{class_memory_status} — {class_memory_reason}"),
                ("Trust Decay", f"{class_decay_status} — {class_decay_summary}"),
                ("Class Reweighting", f"{class_reweight_direction} ({class_reweight_score}) — {class_reweight_summary}"),
                ("Class Reweighting Why", class_reweight_reason),
                ("Class Momentum", class_momentum_status),
                ("Reweight Stability", class_reweight_stability),
                ("Transition Health", class_transition_health),
                ("Transition Resolution", class_transition_resolution),
                ("Transition Summary", class_transition_summary),
                ("Transition Closure", transition_closure_confidence),
                ("Transition Likely Outcome", transition_likely_outcome),
                ("Pending Debt Freshness", pending_debt_freshness),
                ("Closure Forecast", closure_forecast_direction),
                ("Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Persistence", reset_reentry_rebuild_reentry_restore_rerererestore_persistence),
                ("Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Churn Controls", reset_reentry_rebuild_reentry_restore_rerererestore_churn),
                ("Closure Forecast Summary", transition_closure_summary),
                ("Momentum Summary", class_momentum_summary),
                ("Exception Learning", f"{exception_pattern_status} — {exception_pattern_summary}"),
                ("Recommendation Drift", f"{drift_status} — {drift_summary}"),
                ("Adaptive Confidence", adaptive_confidence_summary),
                ("Recommendation Quality", recommendation_quality),
                ("Confidence Validation", f"{calibration_status} — {calibration_summary}"),
                ("High-Confidence Hit Rate", high_hit_rate),
                ("Reopened Recommendations", reopened_recommendations),
            ]
        )
    summary_rows.append(("Source Run", (data.get("operator_summary") or {}).get("source_run_id", "")))
    summary_end = _write_key_value_block(ws, 4, 1, summary_rows, title="Summary")
    top_repo_rows = [
        [
            repo,
            _primary_lane_label(blocked, urgent, ready, deferred),
            _format_repo_rollup_counts(blocked, urgent, ready, deferred),
            title or "See detailed queue rows below.",
            action or "Open the repo queue details.",
        ]
        for repo, _total, blocked, urgent, ready, deferred, _kind, _priority, title, action in repo_rollups[:10]
    ] or [["Portfolio", "Clear", "0 blocked, 0 urgent, 0 ready, 0 deferred", "No open review items.", "Monitor future audits."]]
    top_repo_end = _write_ranked_list(
        ws,
        4,
        5,
        "Top 10 To Act On",
        ["Repo", "Primary Lane", "Counts", "Why Now", "Next Step"],
        top_repo_rows,
    )
    secondary_start = max(summary_end, top_repo_end) + 2
    issue_family_rows = [[label, count] for label, count in top_issue_families]
    if not issue_family_rows:
        issue_family_rows = [["No material change families", 0]]
    issue_family_end = _write_ranked_list(
        ws,
        secondary_start,
        1,
        "Top Issue Families",
        ["Issue Family", "Count"],
        issue_family_rows,
    )
    action_rows = [[action, count] for action, count in _summarize_top_actions(queue)]
    if not action_rows:
        action_rows = [["No recommended actions", 0]]
    action_end = _write_ranked_list(
        ws,
        secondary_start,
        5,
        "Top Recommended Actions",
        ["Action", "Count"],
        action_rows,
    )
    guidance_row = max(issue_family_end, action_end) + 2
    ws.merge_cells(start_row=guidance_row, start_column=1, end_row=guidance_row, end_column=8)
    ws.cell(row=guidance_row, column=1, value="Read this table top-down: urgent items first, ready items second, and safe-to-defer rows last.").font = SUBTITLE_FONT
    ws.cell(row=guidance_row, column=1).alignment = WRAP
    headers = [
        "Repo",
        "Title",
        "Lane",
        "Kind",
        "Priority",
        "Why This Is Here",
        "What To Do Next",
        "Catalog",
        "Intent Alignment",
        "Maturity",
        "Scorecard Gap",
        "Last Movement",
        "Follow-Through",
        "Next Checkpoint",
        "Checkpoint Timing",
        "Escalation",
        "Escalation Summary",
        "Recovery / Retirement",
        "Recovery Summary",
        "Recovery Persistence",
        "Persistence Summary",
        "Relapse Churn",
        "Churn Summary",
        "Recovery Freshness",
        "Freshness Summary",
        "Recovery Memory Reset",
        "Reset Summary",
        "Recovery Rebuild Strength",
        "Rebuild Summary",
        "Recovery Reacquisition",
        "Reacquisition Summary",
        "Reacquisition Durability",
        "Durability Summary",
        "Reacquisition Confidence",
        "Confidence Summary",
        "Operator Focus",
        "Focus Summary",
        "Focus Line",
        "Open Artifact",
        "Safe To Defer",
    ]
    start_row = guidance_row + 1
    for col, header in enumerate(headers, 1):
        ws.cell(row=start_row, column=col, value=header)
    style_header_row(ws, start_row, len(headers))
    ws.freeze_panes = f"A{start_row + 1}"

    targets = ordered_queue or data.get("review_targets", [])
    for row, item in enumerate(targets, start_row + 1):
        next_step = item.get("recommended_action") or item.get("next_step") or "Open Repo Detail and choose the next concrete follow-through step."
        safe_to_defer = item.get("lane") == "deferred" or item.get("safe_to_defer")
        links = item.get("links") or []
        primary_link = links[0].get("url", "") if links else ""
        last_movement = build_last_movement_label(item, data.get("review_summary") or {})
        why_this_is_here = item.get("lane_reason", "") or item.get("summary", "") or item.get("decision_hint", "") or "This item is still open and needs operator follow-through."
        values = [
            item.get("repo", item.get("repo_name", "")),
            item.get("title", ""),
            item.get("lane", ""),
            item.get("kind", "review"),
            item.get("priority", item.get("severity", 0.0)),
            why_this_is_here,
            next_step,
            item.get("catalog_line", "No portfolio catalog contract is recorded yet."),
            (
                f"{item.get('intent_alignment', 'missing-contract')} — "
                f"{item.get('intent_alignment_reason', 'Intent alignment cannot be judged until a portfolio catalog contract exists.')}"
            ),
            item.get("scorecard", {}).get("maturity_level", "") or "—",
            item.get("maturity_gap_summary", "No maturity gap summary is recorded yet."),
            last_movement,
            item.get("follow_through_summary", "No follow-through evidence is recorded yet."),
            item.get("follow_through_next_checkpoint", "Use the next run or linked artifact to confirm whether the recommendation moved."),
            build_follow_through_checkpoint_status_label(item),
            build_follow_through_escalation_status_label(item),
            build_follow_through_escalation_summary(item),
            build_follow_through_recovery_status_label(item),
            build_follow_through_recovery_summary(item),
            build_follow_through_recovery_persistence_status_label(item),
            build_follow_through_recovery_persistence_summary(item),
            build_follow_through_relapse_churn_status_label(item),
            build_follow_through_relapse_churn_summary(item),
            build_follow_through_recovery_freshness_status_label(item),
            build_follow_through_recovery_freshness_summary(item),
            build_follow_through_recovery_memory_reset_status_label(item),
            build_follow_through_recovery_memory_reset_summary(item),
            build_follow_through_recovery_rebuild_strength_status_label(item),
            build_follow_through_recovery_rebuild_strength_summary(item),
            build_follow_through_recovery_reacquisition_status_label(item),
            build_follow_through_recovery_reacquisition_summary(item),
            build_follow_through_reacquisition_durability_status_label(item),
            build_follow_through_reacquisition_durability_summary(item),
            build_follow_through_reacquisition_consolidation_status_label(item),
            build_follow_through_reacquisition_consolidation_summary(item),
            build_operator_focus(item),
            build_operator_focus_summary(item),
            build_operator_focus_line(item),
            "Open linked artifact" if primary_link else no_linked_artifact_summary(),
            "yes" if safe_to_defer else "no",
        ]
        for col, value in enumerate(values, 1):
            align = "center" if col in {3, 4, 5, 10, 15, 16, 18, 20, 22, 24, 26, 28, 30, 32, 34, 36, 43} else "left"
            style_data_cell(ws.cell(row=row, column=col, value=value), align)
        repo_cell = ws.cell(row=row, column=1)
        if item.get("repo_url"):
            repo_cell.hyperlink = item.get("repo_url")
            repo_cell.font = Font("Calibri", 10, color=TEAL, underline="single")
        artifact_cell = ws.cell(row=row, column=40)
        if primary_link:
            artifact_cell.hyperlink = primary_link
            artifact_cell.font = Font("Calibri", 10, color=TEAL, underline="single")
        _apply_lane_row_fill(ws, row, len(headers), item.get("lane"))

    max_row = len(targets) + start_row
    if targets:
        apply_zebra_stripes(ws, start_row + 1, max_row, len(headers))
        for row, item in enumerate(targets, start_row + 1):
            _apply_lane_row_fill(ws, row, len(headers), item.get("lane"))
        _set_autofilter(ws, len(headers), max_row, start_row=start_row)
    auto_width(ws, len(headers), max_row)


def _build_review_history_sheet(wb: Workbook, data: dict) -> None:
    ws = _get_or_create_sheet(wb, "Review History")
    ws.sheet_properties.tabColor = "1D4ED8"
    _configure_sheet_view(ws, zoom=110, show_grid_lines=False)
    _set_sheet_header(
        ws,
        "Review History",
        "Use this ledger to see which recurring review is active now and how prior review runs were resolved, deferred, or left local-only.",
        width=7,
    )
    active_review = data.get("review_summary") or {}
    _write_key_value_block(
        ws,
        4,
        1,
        [
            ("Current Review", active_review.get("review_id", "—")),
            ("Current Status", active_review.get("status", "unknown")),
            ("History Rows", len(data.get("review_history", []) or [])),
            ("How To Read This", "The active review is summarized above; the ledger below is the historical trail."),
        ],
        title="Current State",
    )
    headers = ["Review ID", "Generated", "Changes", "Status", "Decision State", "Sync State", "Emitted"]
    start_row = 9
    for col, header in enumerate(headers, 1):
        ws.cell(row=start_row, column=col, value=header)
    style_header_row(ws, start_row, len(headers))
    ws.freeze_panes = "A10"

    history = data.get("review_history", [])
    for row, item in enumerate(history, start_row + 1):
        values = [
            item.get("review_id", ""),
            item.get("generated_at", ""),
            item.get("material_change_count", 0),
            item.get("status", ""),
            item.get("decision_state", ""),
            item.get("sync_state", ""),
            "yes" if item.get("emitted") else "no",
        ]
        for col, value in enumerate(values, 1):
            style_data_cell(ws.cell(row=row, column=col, value=value), "center" if col not in {1, 2, 4, 5, 6} else "left")

    max_row = len(history) + start_row
    if history:
        apply_zebra_stripes(ws, start_row + 1, max_row, len(headers))
        _add_table(ws, "tblReviewHistory", len(headers), max_row, start_row=start_row)
    auto_width(ws, len(headers), max_row)


def _build_governance_controls(wb: Workbook, data: dict) -> None:
    ws = _get_or_create_sheet(wb, "Governance Controls")
    ws.sheet_properties.tabColor = "7C3AED"
    _configure_sheet_view(ws, zoom=115, show_grid_lines=False)
    _set_sheet_header(
        ws,
        "Governance Controls",
        "This sheet shows the current governed control family only: readiness, drift, re-approval need, and rollback visibility.",
        width=7,
    )
    governance_summary = data.get("governance_summary", {}) or {}
    _write_key_value_block(
        ws,
        4,
        1,
        [
            ("Status", _display_operator_state(governance_summary.get("status", "preview"))),
            ("Selected View", governance_summary.get("selected_view", data.get("governance_preview", {}).get("selected_view", "all"))),
            ("Approval", _display_operator_state(governance_summary.get("approval_status", "preview-only"))),
            ("Needs Re-Approval", "yes" if governance_summary.get("needs_reapproval") else "no"),
            ("Rollback Available", governance_summary.get("rollback_available_count", 0)),
            ("Headline", governance_summary.get("headline", "Governed controls are being tracked locally.")),
            (
                ACTION_SYNC_CANONICAL_LABELS["approval_workflow"],
                (data.get("approval_workflow_summary") or {}).get(
                    "summary",
                    "No current approval needs review yet, so the approval workflow can stay local for now.",
                ),
            ),
            (
                ACTION_SYNC_CANONICAL_LABELS["next_approval_review"],
                (data.get("next_approval_review") or {}).get(
                    "summary",
                    "Stay local for now; no current approval needs review.",
                ),
            ),
        ],
        title="Governance Snapshot",
    )
    headers = ["Repo", "Action", "State", "Expected Lift", "Effort", "Source", "Why"]
    start_row = 11
    for col, header in enumerate(headers, 1):
        ws.cell(row=start_row, column=col, value=header)
    style_header_row(ws, start_row, len(headers))
    ws.freeze_panes = "A12"

    preview = governance_summary.get("top_actions") or data.get("security_governance_preview", [])
    preview_only_source = not governance_summary.get("top_actions")
    for row, item in enumerate(preview, start_row + 1):
        operator_state = item.get("operator_state")
        if not operator_state and preview_only_source:
            operator_state = "preview-only"
        if not operator_state and governance_summary.get("status") == "preview":
            operator_state = "preview-only"
        if not operator_state and item.get("preview_only"):
            operator_state = "preview-only"
        if not operator_state and item.get("applyable") is False:
            operator_state = "preview-only"
        values = [
            item.get("repo", ""),
            item.get("title", ""),
            _display_operator_state(operator_state or item.get("priority", "medium")),
            item.get("expected_posture_lift", 0.0),
            item.get("effort", ""),
            item.get("source", ""),
            item.get("why", ""),
        ]
        for col, value in enumerate(values, 1):
            style_data_cell(ws.cell(row=row, column=col, value=value), "center" if col in {3, 4} else "left")

    max_row = len(preview) + start_row
    if preview:
        apply_zebra_stripes(ws, start_row + 1, max_row, len(headers))
        _add_table(ws, "tblGovernanceControls", len(headers), max_row, start_row=start_row)
    else:
        ws.merge_cells(start_row=start_row + 1, start_column=1, end_row=start_row + 2, end_column=7)
        ws.cell(
            row=start_row + 1,
            column=1,
            value="No governed controls are in scope for this run. This can be expected for audit-only runs or when everything is already aligned.",
        ).alignment = WRAP
        ws.cell(row=start_row + 1, column=1).font = SUBTITLE_FONT
    auto_width(ws, len(headers), max_row)


def _build_governance_audit(wb: Workbook, data: dict) -> None:
    ws = _get_or_create_sheet(wb, "Governance Audit")
    ws.sheet_properties.tabColor = "6D28D9"
    _configure_sheet_view(ws, zoom=110, show_grid_lines=False)
    _set_sheet_header(
        ws,
        "Governance Audit",
        "Evidence summary for approval age, fingerprint drift, rollback coverage, and applied results.",
        width=3,
    )
    headers = ["Control", "Value"]
    start_row = 4
    for col, header in enumerate(headers, 1):
        ws.cell(row=start_row, column=col, value=header)
    style_header_row(ws, start_row, len(headers))
    ws.freeze_panes = "A5"

    governance_summary = data.get("governance_summary", {}) or {}
    preview_count = governance_summary.get("applyable_count")
    if preview_count is None:
        preview_count = len(data.get("security_governance_preview", []) or [])
    rows = [
        ["Status", _display_operator_state(governance_summary.get("status", "preview"))],
        ["Headline", governance_summary.get("headline", "Governance state is being tracked.")],
        ["Approval Status", _display_operator_state(governance_summary.get("approval_status", "preview-only"))],
        ["Needs Re-Approval", "yes" if governance_summary.get("needs_reapproval") else "no"],
        ["Approval Age (days)", governance_summary.get("approval_age_days", "—")],
        ["Fingerprint Mismatch", "yes" if governance_summary.get("fingerprint_mismatch") else "no"],
        ["Applyable Count", preview_count],
        ["Drift Count", governance_summary.get("drift_count", len(data.get("governance_drift", []) or []))],
        ["Applied Count", governance_summary.get("applied_count", len(data.get("governance_results", {}).get("results", []) or []))],
        ["Rollback Available", governance_summary.get("rollback_available_count", 0)],
        ["Selected View", data.get("governance_preview", {}).get("selected_view", "all")],
    ]
    for row_index, row in enumerate(rows, start_row + 1):
        for col_index, value in enumerate(row, 1):
            style_data_cell(ws.cell(row=row_index, column=col_index, value=value), "center" if col_index == 2 else "left")

    apply_zebra_stripes(ws, start_row + 1, len(rows) + start_row, len(headers))
    _add_table(ws, "tblGovernanceAudit", len(headers), len(rows) + start_row, start_row=start_row)
    auto_width(ws, len(headers), len(rows) + start_row)


def _build_compare_sheet(
    wb: Workbook,
    diff_data: dict | None,
) -> None:
    if not diff_data:
        return

    ws = _get_or_create_sheet(wb, "Compare")
    ws.sheet_properties.tabColor = "7C3AED"
    _configure_sheet_view(ws, zoom=110, show_grid_lines=True)
    ws["A1"] = "Compare Summary"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = f"Previous: {diff_data.get('previous_date', '')[:10]}"
    ws["A3"] = f"Current: {diff_data.get('current_date', '')[:10]}"
    ws["A4"] = f"Average score delta: {diff_data.get('average_score_delta', 0):+.3f}"

    row = 6
    if diff_data.get("lens_deltas"):
        ws.cell(row=row, column=1, value="Lens")
        ws.cell(row=row, column=2, value="Delta")
        style_header_row(ws, row, 2)
        for offset, (lens_name, delta) in enumerate(diff_data.get("lens_deltas", {}).items(), 1):
            ws.cell(row=row + offset, column=1, value=lens_name)
            ws.cell(row=row + offset, column=2, value=delta)
            style_data_cell(ws.cell(row=row + offset, column=1), "left")
            style_data_cell(ws.cell(row=row + offset, column=2), "center")
        row += len(diff_data.get("lens_deltas", {})) + 3

    headers = ["Repo", "Score Delta", "Tier Change", "Security", "Hotspots", "Collections"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=row, column=col, value=header)
    style_header_row(ws, row, len(headers))
    repo_changes = diff_data.get("repo_changes", [])
    for offset, change in enumerate(repo_changes[:15], 1):
        values = [
            change.get("name", ""),
            change.get("delta", 0.0),
            f"{change.get('old_tier', '—')} → {change.get('new_tier', '—')}",
            f"{change.get('security_change', {}).get('old_label', '—')} → {change.get('security_change', {}).get('new_label', '—')}",
            f"{change.get('hotspot_change', {}).get('old_count', 0)} → {change.get('hotspot_change', {}).get('new_count', 0)}",
            f"{', '.join(change.get('collection_change', {}).get('old', [])) or '—'} → {', '.join(change.get('collection_change', {}).get('new', [])) or '—'}",
        ]
        for col, value in enumerate(values, 1):
            style_data_cell(ws.cell(row=row + offset, column=col, value=value), "center" if col == 2 else "left")
    max_row = row + min(len(repo_changes), 15)
    if max_row > row:
        _add_table(ws, "tblCompare", len(headers), max_row, start_row=row)
    auto_width(ws, len(headers), max_row)


def _build_scenario_planner(
    wb: Workbook,
    data: dict,
    *,
    portfolio_profile: str = "default",
    collection: str | None = None,
) -> None:
    from src.analyst_views import build_analyst_context

    context = build_analyst_context(data, profile_name=portfolio_profile, collection_name=collection)
    preview = context["scenario_preview"]
    ws = _get_or_create_sheet(wb, "Scenario Planner")
    ws.sheet_properties.tabColor = "CA8A04"
    _configure_sheet_view(ws, zoom=110, show_grid_lines=False)

    ws["A1"] = "Scenario Planner"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = f"Profile: {context['profile_name']}"
    ws["A3"] = f"Collection: {context['collection_name'] or 'all'}"
    ws.freeze_panes = "B6"

    headers = ["Lever", "Lens", "Repo Count", "Avg Lift", "Weighted Impact", "Projected Promotions"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=5, column=col, value=header)
    style_header_row(ws, 5, len(headers))

    for row, lever in enumerate(preview.get("top_levers", []), 6):
        values = [
            lever.get("title", ""),
            lever.get("lens", ""),
            lever.get("repo_count", 0),
            lever.get("average_expected_lens_delta", 0.0),
            lever.get("weighted_impact", 0.0),
            lever.get("projected_tier_promotions", 0),
        ]
        for col, value in enumerate(values, 1):
            style_data_cell(ws.cell(row=row, column=col, value=value), "center" if col >= 3 else "left")

    projection = preview.get("portfolio_projection", {})
    summary_row = max(7, len(preview.get("top_levers", [])) + 7)
    ws.cell(row=summary_row, column=1, value="Selected Repos").font = SUBHEADER_FONT
    ws.cell(row=summary_row, column=2, value=projection.get("selected_repo_count", 0))
    ws.cell(row=summary_row + 1, column=1, value="Projected Avg Score Delta").font = SUBHEADER_FONT
    ws.cell(row=summary_row + 1, column=2, value=projection.get("projected_average_score_delta", 0.0))
    ws.cell(row=summary_row + 2, column=1, value="Projected Promotions").font = SUBHEADER_FONT
    ws.cell(row=summary_row + 2, column=2, value=projection.get("projected_tier_promotions", 0))

    max_row = max(summary_row + 2, len(preview.get("top_levers", [])) + 5)
    if len(preview.get("top_levers", [])) > 0:
        _add_table(
            ws,
            "tblScenarioPlanner",
            len(headers),
            len(preview.get("top_levers", [])) + 5,
            start_row=5,
        )
    auto_width(ws, len(headers), max_row)


def _build_executive_summary(
    wb: Workbook,
    data: dict,
    diff_data: dict | None,
    *,
    portfolio_profile: str = "default",
    collection: str | None = None,
    excel_mode: str = "standard",
) -> None:
    from src.analyst_views import build_analyst_context

    context = build_analyst_context(data, profile_name=portfolio_profile, collection_name=collection)
    ws = _get_or_create_sheet(wb, "Executive Summary")
    ws.sheet_properties.tabColor = NAVY
    _configure_sheet_view(ws, zoom=120, show_grid_lines=False)
    _set_sheet_header(
        ws,
        "Executive Summary",
        f"Profile: {context['profile_name']} | Collection: {context['collection_name'] or 'all'}",
        width=6,
    )
    _write_instruction_banner(
        ws,
        3,
        12,
        "Use the left side for the short leadership story and the right side for operator evidence you may need to defend the next move.",
    )
    ws.freeze_panes = "A4"

    leaders = context["profile_leaderboard"].get("leaders", [])[:5]
    critical_repos = data.get("security_posture", {}).get("critical_repos", []) or []
    operator_summary = data.get("operator_summary") or {}
    weekly_pack = build_weekly_review_pack(data, diff_data)
    operator_focus, operator_focus_summary, operator_focus_line = _operator_focus_snapshot(weekly_pack)
    preview = context["scenario_preview"].get("portfolio_projection", {})
    next_mode, watch_strategy, watch_decision = _operator_watch_values(data)
    what_changed, why_it_matters, next_action = _operator_handoff_values(data)
    (
        follow_through,
        follow_through_checkpoint,
        follow_through_escalation,
        follow_through_hotspot,
        follow_through_escalation_hotspot,
    ) = _operator_follow_through_details(data)
    (
        follow_through_recovery,
        follow_through_recovery_persistence,
        follow_through_relapse_churn,
        follow_through_relapsing_hotspot,
        follow_through_retiring_hotspot,
        follow_through_churn_hotspot,
    ) = _operator_follow_through_recovery_details(data)
    (
        follow_through_recovery_freshness,
        follow_through_recovery_memory_reset,
        follow_through_recovery_freshness_hotspot,
        follow_through_recovery_freshness_hotspot_summary,
        follow_through_recovery_rebuild_hotspot,
    ) = _operator_follow_through_freshness_details(data)
    (
        follow_through_rebuild_strength,
        follow_through_reacquisition,
        follow_through_reacquisition_durability,
        follow_through_reacquisition_confidence,
        follow_through_rebuild_strength_hotspot,
        follow_through_reacquiring_hotspot,
        follow_through_reacquired_hotspot,
        follow_through_fragile_reacquisition_hotspot,
        follow_through_just_reacquired_hotspot,
        follow_through_holding_reacquired_hotspot,
        follow_through_durable_reacquired_hotspot,
        follow_through_softening_reacquired_hotspot,
        follow_through_fragile_reacquisition_confidence_hotspot,
    ) = _operator_follow_through_rebuild_details(data)
    (
        follow_through_reacquisition_softening_decay,
        follow_through_reacquisition_confidence_retirement,
        follow_through_reacquisition_softening_hotspot,
        follow_through_reacquisition_revalidation_hotspot,
        follow_through_reacquisition_retired_confidence_hotspot,
    ) = _operator_follow_through_reacquisition_retirement_details(data)
    (
        follow_through_revalidation_recovery,
        follow_through_under_revalidation_hotspot,
        follow_through_rebuilding_restored_confidence_hotspot,
        follow_through_reearning_confidence_hotspot,
        follow_through_just_reearned_confidence_hotspot,
        follow_through_holding_reearned_confidence_hotspot,
    ) = _operator_follow_through_revalidation_recovery_details(data)
    trend_status, trend_summary, primary_target, resolution_counts = _operator_trend_values(data)
    primary_target_reason, closure_guidance, aging_pressure = _operator_accountability_values(data)
    last_intervention, last_outcome, resolution_evidence, recovery_counts = _operator_decision_memory_values(data)
    primary_confidence, confidence_reason, next_action_confidence, recommendation_quality = _operator_confidence_values(data)
    trust_policy, trust_policy_reason, adaptive_confidence_summary = _operator_trust_values(data)
    exception_status, exception_reason, drift_status, drift_summary = _operator_exception_values(data)
    trust_recovery_status, trust_recovery_reason, exception_pattern_status, exception_pattern_summary = _operator_learning_values(data)
    recovery_confidence, retirement_status, retirement_reason, retirement_summary = _operator_retirement_values(data)
    policy_debt_status, policy_debt_reason, class_normalization_status, trust_normalization_summary = _operator_class_normalization_values(data)
    class_memory_status, class_memory_reason, class_decay_status, class_decay_summary = _operator_class_memory_values(data)
    class_reweight_direction, class_reweight_score, class_reweight_reason, class_reweight_summary = _operator_class_reweight_values(data)
    class_momentum_status, class_reweight_stability, class_momentum_summary = _operator_class_momentum_values(data)
    class_transition_health, class_transition_resolution, class_transition_summary = _operator_class_transition_values(data)
    (
        transition_closure_confidence,
        transition_likely_outcome,
        pending_debt_freshness,
        closure_forecast_direction,
        reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery,
        reset_reentry_rebuild_reentry_restore_rerererestore,
        reset_reentry_rebuild_reentry_restore_rerererestore_persistence,
        reset_reentry_rebuild_reentry_restore_rerererestore_churn,
        transition_closure_summary,
    ) = _operator_transition_closure_values(data)
    calibration_status, calibration_summary, high_hit_rate, reopened_recommendations = _operator_calibration_values(data)
    recommended_focus = ""
    if data.get("operator_queue"):
        recommended_focus = data["operator_queue"][0].get("recommended_action", "")
    elif leaders:
        recommended_focus = f"Protect momentum around {leaders[0]['name']}"
    if diff_data:
        change_summary = (
            f"Average score moved {diff_data.get('average_score_delta', 0.0):+.3f} across "
            f"{len(diff_data.get('repo_changes', []) or [])} repos with notable changes."
        )
    else:
        change_summary = (
            f"{len(data.get('material_changes', []) or [])} material changes and "
            f"{len(data.get('governance_drift', []) or [])} governance drift signals were captured in this run."
        )
    run_change_counts = data.get("run_change_counts") or build_run_change_counts(diff_data)
    run_change_summary = data.get("run_change_summary") or build_run_change_summary(diff_data)
    queue_pressure_summary = build_queue_pressure_summary(data, diff_data)
    trust_actionability_summary = build_trust_actionability_summary(data)
    top_attention = _build_workbook_rollups(data)[1][:5]
    top_recommendation = build_top_recommendation_summary(data) or recommended_focus or "Start with the highest-pressure queue item, then protect the current leaders."
    biggest_opportunity = leaders[0]["name"] if leaders else "Portfolio-wide follow-through"
    narrative_rows = [
        (
            "Portfolio Health",
            f"{data.get('tier_distribution', {}).get('shipped', 0)} repos are shipped, the portfolio average is {data.get('average_score', 0):.2f}, and {leaders[0]['name'] if leaders else 'the current leaders'} set the current high-water mark.",
        ),
        (
            "Top Attention",
            operator_summary.get("headline", "No urgent operator headline is present.")
            + (f" Critical security pressure is concentrated in {len(critical_repos)} repos." if critical_repos else ""),
        ),
        ("Run Changes", run_change_summary or change_summary),
        (
            "Queue Pressure",
            queue_pressure_summary,
        ),
        ("What Changed", what_changed or change_summary),
        ("Why It Matters", why_it_matters),
        ("Top Recommendation", top_recommendation),
        ("Portfolio Catalog", build_portfolio_catalog_summary(data)),
        ("Intent Alignment", build_portfolio_intent_alignment_summary(data)),
        ("Scorecards", build_scorecards_summary(data)),
        ("Follow-Through", follow_through),
        ("Next Checkpoint", follow_through_checkpoint),
        ("Escalation", follow_through_escalation),
        ("Recovery / Retirement", follow_through_recovery),
        ("Recovery Persistence", follow_through_recovery_persistence),
        ("Relapse Churn", follow_through_relapse_churn),
        ("Recovery Freshness", follow_through_recovery_freshness),
        ("Recovery Memory Reset", follow_through_recovery_memory_reset),
        ("Recovery Rebuild Strength", follow_through_rebuild_strength),
        ("Recovery Reacquisition", follow_through_reacquisition),
        ("Reacquisition Durability", follow_through_reacquisition_durability),
        ("Reacquisition Confidence", follow_through_reacquisition_confidence),
        ("Operator Focus", operator_focus),
        ("Focus Summary", operator_focus_summary),
        ("Focus Line", operator_focus_line),
        ("Trust Summary", trust_actionability_summary),
        ("Biggest Opportunity", biggest_opportunity),
        ("Focus This Week", next_action or recommended_focus or "Review the top queue items first, then protect the highest-value repos from drift."),
    ]
    if excel_mode == "standard":
        narrative_rows.insert(5, ("Trend", f"{trend_status} — {trend_summary}"))
        narrative_rows.insert(6, ("Why Top Target", primary_target_reason))
        narrative_rows.insert(7, ("Follow-Through Hotspot", follow_through_hotspot))
        narrative_rows.insert(8, ("Escalation Hotspot", follow_through_escalation_hotspot))
        narrative_rows.insert(9, ("Recovery Hotspot", follow_through_relapsing_hotspot))
        narrative_rows.insert(10, ("Retiring Watch Hotspot", follow_through_retiring_hotspot))
        narrative_rows.insert(11, ("Churn Hotspot", follow_through_churn_hotspot))
        narrative_rows.insert(12, ("Freshness Hotspot", follow_through_recovery_freshness_hotspot))
        narrative_rows.insert(13, ("Freshness Detail", follow_through_recovery_freshness_hotspot_summary))
        narrative_rows.insert(14, ("Rebuild Hotspot", follow_through_recovery_rebuild_hotspot))
        narrative_rows.insert(15, ("Rebuild Strength Hotspot", follow_through_rebuild_strength_hotspot))
        narrative_rows.insert(16, ("Reacquiring Hotspot", follow_through_reacquiring_hotspot))
        narrative_rows.insert(17, ("Reacquired Hotspot", follow_through_reacquired_hotspot))
        narrative_rows.insert(18, ("Fragile Reacquisition Hotspot", follow_through_fragile_reacquisition_hotspot))
        narrative_rows.insert(19, ("Just Reacquired Hotspot", follow_through_just_reacquired_hotspot))
        narrative_rows.insert(20, ("Holding Reacquired Hotspot", follow_through_holding_reacquired_hotspot))
        narrative_rows.insert(21, ("Durable Reacquired Hotspot", follow_through_durable_reacquired_hotspot))
        narrative_rows.insert(22, ("Softening Reacquired Hotspot", follow_through_softening_reacquired_hotspot))
        narrative_rows.insert(23, ("Fragile Reacquisition Confidence Hotspot", follow_through_fragile_reacquisition_confidence_hotspot))
        narrative_rows.insert(24, ("Reacquisition Softening Hotspot", follow_through_reacquisition_softening_hotspot))
        narrative_rows.insert(25, ("Revalidation Needed Hotspot", follow_through_reacquisition_revalidation_hotspot))
        narrative_rows.insert(26, ("Retired Confidence Hotspot", follow_through_reacquisition_retired_confidence_hotspot))
        narrative_rows.insert(27, ("Under Revalidation Hotspot", follow_through_under_revalidation_hotspot))
        narrative_rows.insert(28, ("Rebuilding Restored Confidence Hotspot", follow_through_rebuilding_restored_confidence_hotspot))
        narrative_rows.insert(29, ("Re-Earning Confidence Hotspot", follow_through_reearning_confidence_hotspot))
        narrative_rows.insert(30, ("Just Re-Earned Confidence Hotspot", follow_through_just_reearned_confidence_hotspot))
        narrative_rows.insert(31, ("Holding Re-Earned Confidence Hotspot", follow_through_holding_reearned_confidence_hotspot))
        narrative_rows.insert(32, ("Closure Guidance", closure_guidance))
        narrative_rows.insert(33, ("What We Tried", last_intervention))
        narrative_rows.insert(34, ("Recommendation Confidence", primary_confidence))
        narrative_rows.insert(35, ("Resolution Evidence", resolution_evidence))
        narrative_rows.insert(36, ("Confidence Rationale", confidence_reason))
        narrative_rows.insert(37, ("Trust Policy", trust_policy))
        narrative_rows.insert(38, ("Trust Rationale", trust_policy_reason))
        narrative_rows.insert(39, ("Trust Exception", f"{exception_status} — {exception_reason}"))
        narrative_rows.insert(40, ("Trust Recovery", f"{trust_recovery_status} — {trust_recovery_reason}"))
        narrative_rows.insert(41, ("Recovery Confidence", recovery_confidence))
        narrative_rows.insert(42, ("Exception Retirement", f"{retirement_status} — {retirement_reason}"))
        narrative_rows.insert(43, ("Retirement Summary", retirement_summary))
        narrative_rows.insert(44, ("Policy Debt", f"{policy_debt_status} — {policy_debt_reason}"))
        narrative_rows.insert(45, ("Class Normalization", f"{class_normalization_status} — {trust_normalization_summary}"))
        narrative_rows.insert(46, ("Class Memory", f"{class_memory_status} — {class_memory_reason}"))
        narrative_rows.insert(47, ("Trust Decay", f"{class_decay_status} — {class_decay_summary}"))
        narrative_rows.insert(48, ("Class Reweighting", f"{class_reweight_direction} ({class_reweight_score}) — {class_reweight_summary}"))
        narrative_rows.insert(49, ("Class Reweighting Why", class_reweight_reason))
        narrative_rows.insert(50, ("Class Momentum", class_momentum_status))
        narrative_rows.insert(51, ("Reweight Stability", class_reweight_stability))
        narrative_rows.insert(47, ("Transition Health", class_transition_health))
        narrative_rows.insert(48, ("Transition Summary", class_transition_summary))
        narrative_rows.insert(49, ("Transition Closure", transition_closure_confidence))
        narrative_rows.insert(50, ("Transition Resolution", class_transition_resolution))
        narrative_rows.insert(51, ("Transition Likely Outcome", transition_likely_outcome))
        narrative_rows.insert(52, ("Pending Debt Freshness", pending_debt_freshness))
        narrative_rows.insert(50, ("Closure Forecast", closure_forecast_direction))
        narrative_rows.insert(51, ("Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Persistence", reset_reentry_rebuild_reentry_restore_rerererestore_persistence))
        narrative_rows.insert(52, ("Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Churn Controls", reset_reentry_rebuild_reentry_restore_rerererestore_churn))
        narrative_rows.insert(53, ("Closure Forecast Summary", transition_closure_summary))
        narrative_rows.insert(54, ("Momentum Summary", class_momentum_summary))
        narrative_rows.insert(55, ("Exception Learning", f"{exception_pattern_status} — {exception_pattern_summary}"))
        narrative_rows.insert(56, ("Recommendation Drift", f"{drift_status} — {drift_summary}"))
        narrative_rows.insert(57, ("Adaptive Confidence", adaptive_confidence_summary))
        narrative_rows.insert(58, ("Confidence Validation", f"{calibration_status} — {calibration_summary}"))
    _write_key_value_block(ws, 4, 1, narrative_rows, title="Leadership Brief")

    write_kpi_card(ws, 10, 1, "Portfolio Grade", data.get("portfolio_grade", "F"))
    write_kpi_card(ws, 10, 3, "Avg Score", f"{data.get('average_score', 0):.2f}")
    write_kpi_card(ws, 10, 5, "Critical Repos", len(critical_repos))
    write_kpi_card(ws, 10, 7, "Improving", run_change_counts.get("score_improvements", 0))
    write_kpi_card(ws, 10, 9, "Regressing", run_change_counts.get("score_regressions", 0), "C2410C")

    leader_rows = [[entry["name"], entry["profile_score"], entry["tier"]] for entry in leaders] or [["No leader", 0, "—"]]
    _write_ranked_list(ws, 14, 1, "Top Profile Leaders", ["Repo", "Profile Score", "Tier"], leader_rows)

    attention_rows = [
        [repo, f"B{blocked}/U{urgent}/R{ready}", title or "Queue pressure", action or "Review the repo detail page."]
        for repo, _total, blocked, urgent, ready, _deferred, _kind, _priority, title, action in top_attention
    ] or [["Portfolio", "No open items", "Queue is clear", "Monitor future runs."]]
    _write_ranked_list(ws, 14, 9, "Top 5 Attention Items", ["Repo", "Counts", "Why Now", "Next Step"], attention_rows)

    if diff_data:
        mover_rows = [
            [change.get("name", ""), round(change.get("delta", 0.0), 3), f"{change.get('old_tier', '—')} -> {change.get('new_tier', '—')}"]
            for change in (diff_data.get("repo_changes", []) or [])[:5]
        ] or [["No movers", 0.0, "—"]]
        _write_ranked_list(ws, 14, 5, "Top Movers", ["Repo", "Delta", "Tier Change"], mover_rows)

    ws.cell(row=22, column=1, value="Scenario Preview").font = SECTION_FONT
    ws.cell(row=23, column=1, value="Projected Avg Score Delta").font = SUBHEADER_FONT
    ws.cell(row=23, column=2, value=preview.get("projected_average_score_delta", 0.0))
    ws.cell(row=24, column=1, value="Projected Promotions").font = SUBHEADER_FONT
    ws.cell(row=24, column=2, value=preview.get("projected_tier_promotions", 0))

    if operator_summary:
        ws.cell(row=22, column=4, value="Operator Control Center").font = SECTION_FONT
        ws.cell(row=23, column=4, value="Headline").font = SUBHEADER_FONT
        ws.cell(row=23, column=5, value=operator_summary.get("headline", ""))
        ws.cell(row=24, column=4, value="Queue Counts").font = SUBHEADER_FONT
        ws.cell(row=24, column=5, value=_format_lane_counts(_operator_counts(data)))
        ws.cell(row=25, column=4, value="Source Run").font = SUBHEADER_FONT
        ws.cell(row=25, column=5, value=operator_summary.get("source_run_id", ""))
        ws.cell(row=26, column=4, value="Next Run").font = SUBHEADER_FONT
        ws.cell(row=26, column=5, value=f"{next_mode} via {watch_strategy}")
        ws.cell(row=27, column=4, value="Watch Decision").font = SUBHEADER_FONT
        ws.cell(row=27, column=5, value=watch_decision)
        ws.cell(row=28, column=4, value="What To Do Next").font = SUBHEADER_FONT
        ws.cell(
            row=28,
            column=5,
            value=next_action
            or (data.get("operator_queue", [{}])[0].get("recommended_action") if data.get("operator_queue") else "")
            or "Start with the top review queue item, then protect the current profile leaders.",
        )
        if excel_mode == "standard":
            ws.cell(row=29, column=4, value="Trend").font = SUBHEADER_FONT
            ws.cell(row=29, column=5, value=f"{trend_status} — {trend_summary}")
            ws.cell(row=30, column=4, value="Primary Target").font = SUBHEADER_FONT
            ws.cell(row=30, column=5, value=primary_target)
            ws.cell(row=31, column=4, value="Resolution Counts").font = SUBHEADER_FONT
            ws.cell(row=31, column=5, value=resolution_counts)
            ws.cell(row=32, column=4, value="Why Top Target").font = SUBHEADER_FONT
            ws.cell(row=32, column=5, value=primary_target_reason)
            ws.cell(row=33, column=4, value="Closure Guidance").font = SUBHEADER_FONT
            ws.cell(row=33, column=5, value=closure_guidance)
            ws.cell(row=34, column=4, value="Aging Pressure").font = SUBHEADER_FONT
            ws.cell(row=34, column=5, value=aging_pressure)
            ws.cell(row=35, column=4, value="What We Tried").font = SUBHEADER_FONT
            ws.cell(row=35, column=5, value=last_intervention)
            ws.cell(row=36, column=4, value="Last Outcome").font = SUBHEADER_FONT
            ws.cell(row=36, column=5, value=last_outcome)
            ws.cell(row=37, column=4, value="Resolution Evidence").font = SUBHEADER_FONT
            ws.cell(row=37, column=5, value=resolution_evidence)
            ws.cell(row=38, column=4, value="Recovery Counts").font = SUBHEADER_FONT
            ws.cell(row=38, column=5, value=recovery_counts)
            ws.cell(row=39, column=4, value="Recommendation Confidence").font = SUBHEADER_FONT
            ws.cell(row=39, column=5, value=primary_confidence)
            ws.cell(row=40, column=4, value="Confidence Rationale").font = SUBHEADER_FONT
            ws.cell(row=40, column=5, value=confidence_reason)
            ws.cell(row=41, column=4, value="Next Action Confidence").font = SUBHEADER_FONT
            ws.cell(row=41, column=5, value=next_action_confidence)
            ws.cell(row=42, column=4, value="Trust Policy").font = SUBHEADER_FONT
            ws.cell(row=42, column=5, value=trust_policy)
            ws.cell(row=43, column=4, value="Trust Rationale").font = SUBHEADER_FONT
            ws.cell(row=43, column=5, value=trust_policy_reason)
            ws.cell(row=44, column=4, value="Trust Recovery").font = SUBHEADER_FONT
            ws.cell(row=44, column=5, value=f"{trust_recovery_status} — {trust_recovery_reason}")
            ws.cell(row=45, column=4, value="Recovery Confidence").font = SUBHEADER_FONT
            ws.cell(row=45, column=5, value=recovery_confidence)
            ws.cell(row=46, column=4, value="Recovery Persistence").font = SUBHEADER_FONT
            ws.cell(row=46, column=5, value=follow_through_recovery_persistence)
            ws.cell(row=47, column=4, value="Relapse Churn").font = SUBHEADER_FONT
            ws.cell(row=47, column=5, value=follow_through_relapse_churn)
            ws.cell(row=48, column=4, value="Recovery Freshness").font = SUBHEADER_FONT
            ws.cell(row=48, column=5, value=follow_through_recovery_freshness)
            ws.cell(row=49, column=4, value="Recovery Memory Reset").font = SUBHEADER_FONT
            ws.cell(row=49, column=5, value=follow_through_recovery_memory_reset)
            ws.cell(row=50, column=4, value="Recovery Rebuild Strength").font = SUBHEADER_FONT
            ws.cell(row=50, column=5, value=follow_through_rebuild_strength)
            ws.cell(row=51, column=4, value="Recovery Reacquisition").font = SUBHEADER_FONT
            ws.cell(row=51, column=5, value=follow_through_reacquisition)
            ws.cell(row=52, column=4, value="Recovery Hotspot").font = SUBHEADER_FONT
            ws.cell(row=52, column=5, value=follow_through_relapsing_hotspot)
            ws.cell(row=53, column=4, value="Retiring Watch Hotspot").font = SUBHEADER_FONT
            ws.cell(row=53, column=5, value=follow_through_retiring_hotspot)
            ws.cell(row=54, column=4, value="Churn Hotspot").font = SUBHEADER_FONT
            ws.cell(row=54, column=5, value=follow_through_churn_hotspot)
            ws.cell(row=55, column=4, value="Freshness Hotspot").font = SUBHEADER_FONT
            ws.cell(row=55, column=5, value=follow_through_recovery_freshness_hotspot)
            ws.cell(row=56, column=4, value="Freshness Detail").font = SUBHEADER_FONT
            ws.cell(row=56, column=5, value=follow_through_recovery_freshness_hotspot_summary)
            ws.cell(row=57, column=4, value="Rebuild Hotspot").font = SUBHEADER_FONT
            ws.cell(row=57, column=5, value=follow_through_recovery_rebuild_hotspot)
            ws.cell(row=58, column=4, value="Rebuild Strength Hotspot").font = SUBHEADER_FONT
            ws.cell(row=58, column=5, value=follow_through_rebuild_strength_hotspot)
            ws.cell(row=59, column=4, value="Reacquiring Hotspot").font = SUBHEADER_FONT
            ws.cell(row=59, column=5, value=follow_through_reacquiring_hotspot)
            ws.cell(row=60, column=4, value="Reacquired Hotspot").font = SUBHEADER_FONT
            ws.cell(row=60, column=5, value=follow_through_reacquired_hotspot)
            ws.cell(row=61, column=4, value="Fragile Reacquisition Hotspot").font = SUBHEADER_FONT
            ws.cell(row=61, column=5, value=follow_through_fragile_reacquisition_hotspot)
            ws.cell(row=62, column=4, value="Exception Retirement").font = SUBHEADER_FONT
            ws.cell(row=62, column=5, value=f"{retirement_status} — {retirement_reason}")
            ws.cell(row=63, column=4, value="Retirement Summary").font = SUBHEADER_FONT
            ws.cell(row=63, column=5, value=retirement_summary)
            ws.cell(row=64, column=4, value="Policy Debt").font = SUBHEADER_FONT
            ws.cell(row=64, column=5, value=f"{policy_debt_status} — {policy_debt_reason}")
            ws.cell(row=65, column=4, value="Class Normalization").font = SUBHEADER_FONT
            ws.cell(row=65, column=5, value=f"{class_normalization_status} — {trust_normalization_summary}")
            ws.cell(row=66, column=4, value="Class Memory").font = SUBHEADER_FONT
            ws.cell(row=66, column=5, value=f"{class_memory_status} — {class_memory_reason}")
            ws.cell(row=67, column=4, value="Trust Decay").font = SUBHEADER_FONT
            ws.cell(row=67, column=5, value=f"{class_decay_status} — {class_decay_summary}")
            ws.cell(row=68, column=4, value="Class Reweighting").font = SUBHEADER_FONT
            ws.cell(row=68, column=5, value=f"{class_reweight_direction} ({class_reweight_score}) — {class_reweight_summary}")
            ws.cell(row=69, column=4, value="Class Reweighting Why").font = SUBHEADER_FONT
            ws.cell(row=69, column=5, value=class_reweight_reason)
            ws.cell(row=70, column=4, value="Class Momentum").font = SUBHEADER_FONT
            ws.cell(row=70, column=5, value=class_momentum_status)
            ws.cell(row=71, column=4, value="Reweight Stability").font = SUBHEADER_FONT
            ws.cell(row=71, column=5, value=class_reweight_stability)
            ws.cell(row=72, column=4, value="Transition Health").font = SUBHEADER_FONT
            ws.cell(row=72, column=5, value=class_transition_health)
            ws.cell(row=73, column=4, value="Transition Resolution").font = SUBHEADER_FONT
            ws.cell(row=73, column=5, value=class_transition_resolution)
            ws.cell(row=74, column=4, value="Transition Summary").font = SUBHEADER_FONT
            ws.cell(row=74, column=5, value=class_transition_summary)
            ws.cell(row=75, column=4, value="Transition Closure").font = SUBHEADER_FONT
            ws.cell(row=75, column=5, value=transition_closure_confidence)
            ws.cell(row=76, column=4, value="Transition Likely Outcome").font = SUBHEADER_FONT
            ws.cell(row=76, column=5, value=transition_likely_outcome)
            ws.cell(row=77, column=4, value="Pending Debt Freshness").font = SUBHEADER_FONT
            ws.cell(row=77, column=5, value=pending_debt_freshness)
            ws.cell(row=78, column=4, value="Closure Forecast").font = SUBHEADER_FONT
            ws.cell(row=78, column=5, value=closure_forecast_direction)
            ws.cell(row=79, column=4, value="Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Persistence").font = SUBHEADER_FONT
            ws.cell(row=79, column=5, value=reset_reentry_rebuild_reentry_restore_rerererestore_persistence)
            ws.cell(row=80, column=4, value="Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Churn Controls").font = SUBHEADER_FONT
            ws.cell(row=80, column=5, value=reset_reentry_rebuild_reentry_restore_rerererestore_churn)
            ws.cell(row=81, column=4, value="Closure Forecast Summary").font = SUBHEADER_FONT
            ws.cell(row=81, column=5, value=transition_closure_summary)
            ws.cell(row=82, column=4, value="Momentum Summary").font = SUBHEADER_FONT
            ws.cell(row=82, column=5, value=class_momentum_summary)
            ws.cell(row=83, column=4, value="Exception Learning").font = SUBHEADER_FONT
            ws.cell(row=83, column=5, value=f"{exception_pattern_status} — {exception_pattern_summary}")
            ws.cell(row=84, column=4, value="Recommendation Drift").font = SUBHEADER_FONT
            ws.cell(row=84, column=5, value=f"{drift_status} — {drift_summary}")
            ws.cell(row=85, column=4, value="Adaptive Confidence").font = SUBHEADER_FONT
            ws.cell(row=85, column=5, value=adaptive_confidence_summary)
            ws.cell(row=86, column=4, value="Recommendation Quality").font = SUBHEADER_FONT
            ws.cell(row=86, column=5, value=recommendation_quality)
            ws.cell(row=87, column=4, value="Confidence Validation").font = SUBHEADER_FONT
            ws.cell(row=87, column=5, value=f"{calibration_status} — {calibration_summary}")
            ws.cell(row=88, column=4, value="Calibration Snapshot").font = SUBHEADER_FONT
            ws.cell(row=88, column=5, value=f"High-confidence hit rate {high_hit_rate} | {reopened_recommendations}")
    preflight = data.get("preflight_summary") or {}
    if preflight and (preflight.get("blocking_errors", 0) or preflight.get("warnings", 0)):
        row_base = 59 if excel_mode == "standard" else 33
        ws.cell(row=row_base, column=1, value="Preflight Diagnostics").font = SECTION_FONT
        ws.cell(row=row_base + 1, column=1, value="Status").font = SUBHEADER_FONT
        ws.cell(row=row_base + 1, column=2, value=preflight.get("status", "unknown"))
        ws.cell(row=row_base + 2, column=1, value="Errors").font = SUBHEADER_FONT
        ws.cell(row=row_base + 2, column=2, value=preflight.get("blocking_errors", 0))
        ws.cell(row=row_base + 3, column=1, value="Warnings").font = SUBHEADER_FONT
        ws.cell(row=row_base + 3, column=2, value=preflight.get("warnings", 0))
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.print_title_rows = "1:4"
    ws.print_area = "A1:L40"
    auto_width(ws, 6, 88 if excel_mode == "standard" else 35)


def _build_print_pack(
    wb: Workbook,
    data: dict,
    diff_data: dict | None,
    *,
    portfolio_profile: str = "default",
    collection: str | None = None,
    excel_mode: str = "standard",
) -> None:
    ws = _get_or_create_sheet(wb, "Print Pack")
    ws.sheet_properties.tabColor = "CA8A04"
    _configure_sheet_view(ws, zoom=125, show_grid_lines=False)
    _set_sheet_header(
        ws,
        "Print Pack",
        f"Profile: {portfolio_profile} | Collection: {collection or 'all'}",
        width=6,
    )
    ws.freeze_panes = "A5"
    ws["A4"] = "Page 1: Leadership Brief"
    ws["A4"].font = SECTION_FONT
    ws["A5"] = "Portfolio Grade"
    ws["B5"] = data.get("portfolio_grade", "F")
    ws["A6"] = "Average Score"
    ws["B6"] = round(data.get("average_score", 0.0), 3)
    operator_summary = data.get("operator_summary") or {}
    counts = operator_summary.get("counts", {})
    next_mode, watch_strategy, watch_decision = _operator_watch_values(data)
    what_changed, why_it_matters, next_action = _operator_handoff_values(data)
    (
        follow_through,
        follow_through_checkpoint,
        follow_through_escalation,
        follow_through_hotspot,
        follow_through_escalation_hotspot,
    ) = _operator_follow_through_details(data)
    (
        follow_through_recovery,
        follow_through_recovery_persistence,
        follow_through_relapse_churn,
        follow_through_relapsing_hotspot,
        follow_through_retiring_hotspot,
        follow_through_churn_hotspot,
    ) = _operator_follow_through_recovery_details(data)
    (
        follow_through_recovery_freshness,
        follow_through_recovery_memory_reset,
        follow_through_recovery_freshness_hotspot,
        follow_through_recovery_freshness_hotspot_summary,
        follow_through_recovery_rebuild_hotspot,
    ) = _operator_follow_through_freshness_details(data)
    (
        follow_through_rebuild_strength,
        follow_through_reacquisition,
        follow_through_reacquisition_durability,
        follow_through_reacquisition_confidence,
        follow_through_rebuild_strength_hotspot,
        follow_through_reacquiring_hotspot,
        follow_through_reacquired_hotspot,
        follow_through_fragile_reacquisition_hotspot,
        follow_through_just_reacquired_hotspot,
        follow_through_holding_reacquired_hotspot,
        follow_through_durable_reacquired_hotspot,
        follow_through_softening_reacquired_hotspot,
        follow_through_fragile_reacquisition_confidence_hotspot,
    ) = _operator_follow_through_rebuild_details(data)
    (
        follow_through_reacquisition_softening_decay,
        follow_through_reacquisition_confidence_retirement,
        follow_through_reacquisition_softening_hotspot,
        follow_through_reacquisition_revalidation_hotspot,
        follow_through_reacquisition_retired_confidence_hotspot,
    ) = _operator_follow_through_reacquisition_retirement_details(data)
    trend_status, trend_summary, primary_target, resolution_counts = _operator_trend_values(data)
    primary_target_reason, closure_guidance, aging_pressure = _operator_accountability_values(data)
    last_intervention, last_outcome, resolution_evidence, recovery_counts = _operator_decision_memory_values(data)
    primary_confidence, confidence_reason, next_action_confidence, recommendation_quality = _operator_confidence_values(data)
    trust_policy, trust_policy_reason, adaptive_confidence_summary = _operator_trust_values(data)
    exception_status, exception_reason, drift_status, drift_summary = _operator_exception_values(data)
    trust_recovery_status, trust_recovery_reason, exception_pattern_status, exception_pattern_summary = _operator_learning_values(data)
    recovery_confidence, retirement_status, retirement_reason, retirement_summary = _operator_retirement_values(data)
    policy_debt_status, policy_debt_reason, class_normalization_status, trust_normalization_summary = _operator_class_normalization_values(data)
    class_memory_status, class_memory_reason, class_decay_status, class_decay_summary = _operator_class_memory_values(data)
    class_reweight_direction, class_reweight_score, class_reweight_reason, class_reweight_summary = _operator_class_reweight_values(data)
    class_momentum_status, class_reweight_stability, class_momentum_summary = _operator_class_momentum_values(data)
    class_transition_health, class_transition_resolution, class_transition_summary = _operator_class_transition_values(data)
    (
        transition_closure_confidence,
        transition_likely_outcome,
        pending_debt_freshness,
        closure_forecast_direction,
        reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery,
        reset_reentry_rebuild_reentry_restore_rerererestore,
        reset_reentry_rebuild_reentry_restore_rerererestore_persistence,
        reset_reentry_rebuild_reentry_restore_rerererestore_churn,
        transition_closure_summary,
    ) = _operator_transition_closure_values(data)
    calibration_status, calibration_summary, high_hit_rate, reopened_recommendations = _operator_calibration_values(data)
    weekly_pack = build_weekly_review_pack(data, diff_data)
    operator_focus, operator_focus_summary, operator_focus_line = _operator_focus_snapshot(weekly_pack)
    ws["D4"] = "Workflow Guidance"
    ws["D4"].font = SECTION_FONT
    ws["D5"] = "Product Mode"
    ws["E5"] = weekly_pack.get("product_mode_summary", "Weekly Review: use this artifact for the normal workbook-first operator loop.")
    ws["D6"] = "Artifact Role"
    ws["E6"] = weekly_pack.get(
        "artifact_role_summary",
        "This artifact is the shared weekly handoff across workbook, HTML, Markdown, and review-pack.",
    )
    ws["D7"] = "Reading Order"
    ws["E7"] = weekly_pack.get("suggested_reading_order", "Read Dashboard, then Run Changes, then Review Queue.")
    ws["D8"] = "Next Best Step"
    ws["E8"] = weekly_pack.get(
        "next_best_workflow_step",
        "Open the standard workbook first, then use --control-center for read-only triage.",
    )
    ws["D9"] = ACTION_SYNC_CANONICAL_LABELS["readiness"]
    ws["E9"] = weekly_pack.get(
        "action_sync_summary",
        "No current campaign needs Action Sync yet, so the safest next move is to keep the story local.",
    )
    ws["D10"] = "Next Action Sync Step"
    ws["E10"] = weekly_pack.get(
        "next_action_sync_step",
        "Stay local for now; no current campaign needs preview or apply.",
    )
    ws["D11"] = "Apply Packet"
    ws["E11"] = weekly_pack.get(
        "apply_readiness_summary",
        "No current campaign has a safe execution handoff yet, so the local story should stay local for now.",
    )
    ws["D12"] = "Command Hint"
    ws["E12"] = weekly_pack.get(
        "action_sync_command_hint",
        "No Action Sync command is recommended yet.",
    )
    ws["D13"] = ACTION_SYNC_CANONICAL_LABELS["post_apply_monitoring"]
    ws["E13"] = weekly_pack.get(
        "campaign_outcomes_summary",
        "No recent Action Sync apply needs post-apply monitoring yet, so the local weekly story can stay local.",
    )
    ws["D14"] = "Next Monitoring Step"
    ws["E14"] = weekly_pack.get(
        "next_monitoring_step",
        "Stay local for now; no recent Action Sync apply needs post-apply follow-up yet.",
    )
    ws["D15"] = ACTION_SYNC_CANONICAL_LABELS["campaign_tuning"]
    ws["E15"] = weekly_pack.get(
        "campaign_tuning_summary",
        "Campaign tuning is neutral because there is not enough outcome history yet to bias tied recommendations.",
    )
    ws["D16"] = ACTION_SYNC_CANONICAL_LABELS["next_tie_break_candidate"]
    ws["E16"] = weekly_pack.get(
        "next_tuned_campaign",
        "No current campaign needs a tuning tie-break yet.",
    )
    ws["D17"] = ACTION_SYNC_CANONICAL_LABELS["historical_portfolio_intelligence"]
    ws["E17"] = weekly_pack.get(
        "historical_portfolio_intelligence",
        "Historical portfolio intelligence is still thin, so the weekly story should stay grounded in the current run and recent operator queue.",
    )
    ws["D18"] = "Next Historical Focus"
    ws["E18"] = weekly_pack.get(
        "next_historical_focus",
        "Stay local for now; no repo has enough cross-run intervention evidence to demand a historical follow-up read yet.",
    )
    ws["D19"] = ACTION_SYNC_CANONICAL_LABELS["automation_guidance"]
    ws["E19"] = weekly_pack.get(
        "automation_guidance_summary",
        "Automation guidance stays quiet until a campaign has a clearly safe preview, follow-up, or manual-only posture.",
    )
    ws["D20"] = "Next Safe Automation Step"
    ws["E20"] = weekly_pack.get(
        "next_safe_automation_step",
        "Stay local for now; no current campaign has a stronger safe automation posture than manual review.",
    )
    ws["D21"] = ACTION_SYNC_CANONICAL_LABELS["approval_workflow"]
    ws["E21"] = weekly_pack.get(
        "approval_workflow_summary",
        "No current approval needs review yet, so the approval workflow can stay local for now.",
    )
    ws["D22"] = ACTION_SYNC_CANONICAL_LABELS["next_approval_review"]
    ws["E22"] = weekly_pack.get(
        "next_approval_review",
        "Stay local for now; no current approval needs review.",
    )
    ws["A7"] = "Portfolio Headline"
    ws["B7"] = weekly_pack.get("portfolio_headline", operator_summary.get("headline", "Review the latest workbook surfaces for change and drift."))
    ws["A8"] = "Queue Pressure"
    ws["B8"] = weekly_pack.get(
        "queue_pressure_summary",
        (
            f"{counts.get('blocked', 0)} blocked, {counts.get('urgent', 0)} need attention now, "
            f"and {counts.get('ready', 0)} are ready for manual action."
        ) if operator_summary else "",
    )
    ws["A9"] = "Run Changes"
    ws["B9"] = weekly_pack.get("run_change_summary", build_run_change_summary(diff_data))
    ws["A10"] = "What To Do This Week"
    ws["B10"] = weekly_pack.get("what_to_do_this_week", next_action)
    ws["A11"] = "Trust / Actionability"
    ws["B11"] = weekly_pack.get("trust_actionability_summary", build_trust_actionability_summary(data))
    ws["A12"] = "Top Attention Items"
    ws["B12"] = len(weekly_pack.get("top_attention", []))
    ws["A13"] = "What Changed"
    ws["B13"] = what_changed or weekly_pack.get("run_change_summary", build_run_change_summary(diff_data))
    ws["A14"] = "Why It Matters"
    ws["B14"] = why_it_matters or weekly_pack.get("queue_pressure_summary", build_queue_pressure_summary(data, diff_data))
    ws["A15"] = "Decision This Week"
    ws["B15"] = next_action or weekly_pack.get("what_to_do_this_week", build_top_recommendation_summary(data))
    ws["A16"] = "Follow-Through"
    ws["B16"] = f"{operator_focus_line} Next checkpoint: {follow_through_checkpoint}".strip()
    if excel_mode == "standard":
        ws["A17"] = "Primary Target"
        ws["B17"] = primary_target
        ws["A18"] = "Why Top Target"
        ws["B18"] = primary_target_reason
        ws["A19"] = "Recovery / Retirement"
        ws["B19"] = follow_through_recovery
        ws["A20"] = "Recovery Persistence"
        ws["B20"] = follow_through_recovery_persistence
        ws["A21"] = "Relapse Churn"
        ws["B21"] = follow_through_relapse_churn
        ws["A22"] = "Recovery Freshness"
        ws["B22"] = follow_through_recovery_freshness
        ws["A23"] = "Recovery Memory Reset"
        ws["B23"] = follow_through_recovery_memory_reset
        ws["A24"] = "Recovery Rebuild Strength"
        ws["B24"] = follow_through_rebuild_strength
        ws["A25"] = "Recovery Reacquisition"
        ws["B25"] = follow_through_reacquisition
        ws["A26"] = "Reacquisition Durability"
        ws["B26"] = follow_through_reacquisition_durability
        ws["A27"] = "Reacquisition Confidence"
        ws["B27"] = follow_through_reacquisition_confidence
        ws["A28"] = "Operator Focus"
        ws["B28"] = operator_focus
        ws["A29"] = "Focus Summary"
        ws["B29"] = operator_focus_summary
        ws["A30"] = "Focus Line"
        ws["B30"] = operator_focus_line
        ws["A31"] = "What We Tried"
        ws["B31"] = last_intervention
        ws["A32"] = "Last Outcome"
        ws["B32"] = last_outcome
        ws["A33"] = "Resolution Evidence"
        ws["B33"] = resolution_evidence
        ws["A34"] = "Recovery Counts"
        ws["B34"] = recovery_counts
        ws["A35"] = "Recommendation Confidence"
        ws["B35"] = primary_confidence
        ws["A36"] = "Confidence Rationale"
        ws["B36"] = confidence_reason
        ws["A37"] = "Next Action Confidence"
        ws["B37"] = next_action_confidence
        ws["A38"] = "Trust Policy"
        ws["B38"] = trust_policy
        ws["A39"] = "Trust Rationale"
        ws["B39"] = trust_policy_reason
        ws["A40"] = "Trust Exception"
        ws["B40"] = f"{exception_status} — {exception_reason}"
        ws["A41"] = "Trust Recovery"
        ws["B41"] = f"{trust_recovery_status} — {trust_recovery_reason}"
        ws["A42"] = "Recovery Confidence"
        ws["B42"] = recovery_confidence
        ws["A43"] = "Exception Retirement"
        ws["B43"] = f"{retirement_status} — {retirement_reason}"
        ws["A44"] = "Retirement Summary"
        ws["B44"] = retirement_summary
        ws["A45"] = "Policy Debt"
        ws["B45"] = f"{policy_debt_status} — {policy_debt_reason}"
        ws["A46"] = "Class Normalization"
        ws["B46"] = f"{class_normalization_status} — {trust_normalization_summary}"
        ws["A47"] = "Class Memory"
        ws["B47"] = f"{class_memory_status} — {class_memory_reason}"
        ws["A48"] = "Trust Decay"
        ws["B48"] = f"{class_decay_status} — {class_decay_summary}"
        ws["A49"] = "Class Reweighting"
        ws["B49"] = f"{class_reweight_direction} ({class_reweight_score}) — {class_reweight_summary}"
        ws["A50"] = "Class Reweighting Why"
        ws["B50"] = class_reweight_reason
        ws["A51"] = "Class Momentum"
        ws["B51"] = class_momentum_status
        ws["A52"] = "Reweight Stability"
        ws["B52"] = class_reweight_stability
        ws["A53"] = "Transition Health"
        ws["B53"] = class_transition_health
        ws["A54"] = "Transition Resolution"
        ws["B54"] = class_transition_resolution
        ws["A55"] = "Transition Summary"
        ws["B55"] = class_transition_summary
        ws["A56"] = "Transition Closure"
        ws["B56"] = transition_closure_confidence
        ws["A57"] = "Transition Likely Outcome"
        ws["B57"] = transition_likely_outcome
        ws["A58"] = "Pending Debt Freshness"
        ws["B58"] = pending_debt_freshness
        ws["A59"] = "Closure Forecast"
        ws["B59"] = closure_forecast_direction
        ws["A60"] = "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Persistence"
        ws["B60"] = reset_reentry_rebuild_reentry_restore_rerererestore_persistence
        ws["A61"] = "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Churn Controls"
        ws["B61"] = reset_reentry_rebuild_reentry_restore_rerererestore_churn
        ws["A62"] = "Closure Forecast Summary"
        ws["B62"] = transition_closure_summary
        ws["A63"] = "Momentum Summary"
        ws["B63"] = class_momentum_summary
        ws["A64"] = "Exception Learning"
        ws["B64"] = f"{exception_pattern_status} — {exception_pattern_summary}"
        ws["A65"] = "Recommendation Drift"
        ws["B65"] = f"{drift_status} — {drift_summary}"
        ws["A66"] = "Adaptive Confidence"
        ws["B66"] = adaptive_confidence_summary
        ws["A67"] = "Recommendation Quality"
        ws["B67"] = recommendation_quality
        ws["A68"] = "Confidence Validation"
        ws["B68"] = f"{calibration_status} — {calibration_summary}"
        ws["A69"] = "Calibration Snapshot"
        ws["B69"] = f"High-confidence hit rate {high_hit_rate} | {reopened_recommendations}"
        ws["A70"] = "Top Attention"
        ws["A70"].font = SECTION_FONT
        risk_start_row = 70
        opportunity_header_row = 70
        page2_row = 76
    else:
        ws["A17"] = "Top Attention"
        ws["A17"].font = SECTION_FONT
        risk_start_row = 17
        opportunity_header_row = 17
        page2_row = 26
    top_attention_rows = weekly_pack.get("top_attention", [])[:5]
    for offset, item in enumerate(top_attention_rows, 1):
        ws.cell(row=risk_start_row + offset, column=1, value=item.get("repo", "Portfolio"))
        ws.cell(row=risk_start_row + offset, column=2, value=item.get("operator_focus", item.get("lane", "ready")))
        ws.cell(row=risk_start_row + offset, column=3, value=item.get("why", "Operator pressure is active."))
        ws.cell(row=risk_start_row + offset, column=4, value=item.get("next_step", "Review the latest state."))
    ws[f"E{opportunity_header_row}"] = "Top Repo Drilldowns"
    ws[f"E{opportunity_header_row}"].font = SECTION_FONT
    top_repo_briefings = weekly_pack.get("repo_briefings", [])[:3]
    for offset, briefing in enumerate(top_repo_briefings, 1):
        ws.cell(row=opportunity_header_row + offset, column=5, value=briefing.get("repo", ""))
        ws.cell(row=opportunity_header_row + offset, column=6, value=briefing.get("operator_focus_line", "Watch Closely: No operator focus bucket is currently surfaced."))
    ws.cell(row=page2_row, column=1, value="Page 2: Changes and Governance").font = SECTION_FONT
    ws.cell(row=page2_row + 1, column=1, value="Top Material Change Families").font = SUBHEADER_FONT
    change_rows = [[label, count] for label, count in _summarize_top_issue_families(data.get("material_changes", []) or [], limit=6)]
    for offset, (label, count) in enumerate(change_rows, 1):
        ws.cell(row=page2_row + 1 + offset, column=1, value=label)
        ws.cell(row=page2_row + 1 + offset, column=2, value=count)
    ws.cell(row=page2_row + 1, column=4, value="Governance Highlights").font = SUBHEADER_FONT
    governance_summary = data.get("governance_summary", {}) or {}
    governance_rows = [
        ("Status", _display_operator_state(governance_summary.get("status", "preview"))),
        ("Needs Re-Approval", "yes" if governance_summary.get("needs_reapproval") else "no"),
        ("Drift Count", governance_summary.get("drift_count", len(data.get("governance_drift", []) or []))),
        ("Rollback Available", governance_summary.get("rollback_available_count", 0)),
    ]
    for offset, (label, value) in enumerate(governance_rows, 1):
        ws.cell(row=page2_row + 1 + offset, column=4, value=label)
        ws.cell(row=page2_row + 1 + offset, column=5, value=value)
    if diff_data:
        row = page2_row + 8
        ws.cell(row=row, column=1, value="Compare Snapshot").font = SECTION_FONT
        ws.cell(row=row + 1, column=1, value="Average Score Delta")
        ws.cell(row=row + 1, column=2, value=diff_data.get("average_score_delta", 0.0))
        ws.cell(row=row + 2, column=1, value="Repo Changes")
        ws.cell(row=row + 2, column=2, value=len(diff_data.get("repo_changes", []) or []))
    preflight = data.get("preflight_summary") or {}
    if preflight and (preflight.get("blocking_errors", 0) or preflight.get("warnings", 0)):
        row = page2_row + 12
        ws.cell(row=row, column=1, value="Preflight Diagnostics").font = SECTION_FONT
        ws.cell(row=row + 1, column=1, value="Status")
        ws.cell(row=row + 1, column=2, value=preflight.get("status", "unknown"))
        ws.cell(row=row + 2, column=1, value="Errors")
        ws.cell(row=row + 2, column=2, value=preflight.get("blocking_errors", 0))
        ws.cell(row=row + 3, column=1, value="Warnings")
        ws.cell(row=row + 3, column=2, value=preflight.get("warnings", 0))
    ws.page_setup.orientation = "landscape"
    max_print_row = page2_row + 12
    if diff_data:
        max_print_row = max(max_print_row, page2_row + 10)
    if preflight and (preflight.get("blocking_errors", 0) or preflight.get("warnings", 0)):
        max_print_row = max(max_print_row, page2_row + 15)
    ws.print_area = f"A1:F{max_print_row}"
    ws.print_title_rows = "1:4"
    auto_width(ws, 6, max_print_row)


def _build_template_sparkline_specs(
    data: dict,
    *,
    trend_data: list[dict] | None = None,
    score_history: dict[str, list[float]] | None = None,
) -> list[SparklineSpec]:
    specs: list[SparklineSpec] = []
    extended_score_history = _extend_score_history_with_current(data, score_history)
    row_map = {repo_name: index + 2 for index, repo_name in enumerate(extended_score_history.keys())}
    audits_sorted = sorted(data.get("audits", []), key=lambda audit: audit.get("overall_score", 0), reverse=True)

    for offset, audit in enumerate(audits_sorted, 2):
        repo_name = audit.get("metadata", {}).get("name", "")
        scores = extended_score_history.get(repo_name)
        matrix_row = row_map.get(repo_name)
        if scores and matrix_row:
            start = max(1, TREND_HISTORY_WINDOW - len(scores) + 1)
            end = TREND_HISTORY_WINDOW
            specs.append(
                SparklineSpec(
                    sheet_name="All Repos",
                    location=f"AA{offset}",
                    data_range=f"Data_TrendMatrix!{get_column_letter(start + 1)}{matrix_row}:{get_column_letter(end + 1)}{matrix_row}",
                )
            )

    extended_trends = _extend_portfolio_trend_with_current(data, trend_data)
    if extended_trends:
        specs.append(
            SparklineSpec(
                sheet_name="Dashboard",
                location="L7",
                data_range=f"Data_PortfolioHistory!C2:C{len(extended_trends) + 1}",
            )
        )
    return specs


def _build_excel_workbook(
    wb: Workbook,
    data: dict,
    *,
    trend_data: list[dict] | None = None,
    diff_data: dict | None = None,
    score_history: dict[str, list[float]] | None = None,
    portfolio_profile: str = "default",
    collection: str | None = None,
    excel_mode: str = "standard",
) -> None:
    _build_dashboard(wb, data, diff_data, score_history, excel_mode=excel_mode)
    _build_all_repos(wb, data, score_history)
    _build_portfolio_explorer(
        wb,
        data,
        portfolio_profile=portfolio_profile,
        collection=collection,
    )
    _build_portfolio_catalog_sheet(wb, data)
    _build_scorecards_sheet(wb, data)
    _build_repo_detail(wb, data)
    _build_by_lens(
        wb,
        data,
        portfolio_profile=portfolio_profile,
        collection=collection,
    )
    _build_by_collection(
        wb,
        data,
        portfolio_profile=portfolio_profile,
    )
    _build_trend_summary(wb, data, trend_data, score_history)
    _build_run_changes(wb, data, diff_data)
    _build_heatmap(wb, data)
    _build_quick_wins(wb, data)
    _build_badges(wb, data)
    _build_tech_stack(wb, data)
    _build_trends(wb, data, trend_data)
    _build_tier_breakdown(wb, data)
    _build_activity(wb, data)
    _build_repo_profiles(wb, data)
    _build_security(wb, data)
    _build_security_controls(wb, data)
    _build_supply_chain(wb, data)
    _build_security_debt(wb, data)
    _build_campaigns(wb, data)
    _build_writeback_audit(wb, data)
    _build_governance_controls(wb, data)
    _build_governance_audit(wb, data)
    _build_review_queue(wb, data, excel_mode=excel_mode)
    _build_review_history_sheet(wb, data)
    _build_hotspots(wb, data)
    _build_implementation_hotspots(wb, data)
    _build_operator_outcomes(wb, data)
    _build_approval_ledger(wb, data)
    _build_historical_intelligence(wb, data)
    _build_compare_sheet(wb, diff_data)
    _build_scenario_planner(
        wb,
        data,
        portfolio_profile=portfolio_profile,
        collection=collection,
    )
    _build_executive_summary(
        wb,
        data,
        diff_data,
        portfolio_profile=portfolio_profile,
        collection=collection,
        excel_mode=excel_mode,
    )
    _build_print_pack(
        wb,
        data,
        diff_data,
        portfolio_profile=portfolio_profile,
        collection=collection,
        excel_mode=excel_mode,
    )
    _build_changes(wb, data, diff_data)
    _build_reconciliation(wb, data)
    _build_dependency_graph(wb, data)
    _build_score_explainer(wb)
    _build_action_items(wb, data)
    _build_hidden_data_sheets(wb, data, trend_data, score_history, diff_data)
    _build_navigation(
        wb,
        data,
        excel_mode=excel_mode,
        portfolio_profile=portfolio_profile,
        collection=collection,
    )
    _inject_sheet_navigation(wb)
    _apply_workbook_named_ranges(
        wb,
        data,
        portfolio_profile=portfolio_profile,
        collection=collection,
        excel_mode=excel_mode,
    )
    _apply_visible_sheet_profile(wb)
    _reorder_workbook_sheets(wb)
    _refresh_pivot_caches_on_load(wb)
    wb.calculation.fullCalcOnLoad = True
    wb.calculation.forceFullCalc = True


def export_excel(
    report_path: Path,
    output_path: Path,
    trend_data: list[dict] | None = None,
    diff_data: dict | None = None,
    score_history: dict[str, list[float]] | None = None,
    portfolio_profile: str = "default",
    collection: str | None = None,
    excel_mode: str = "standard",
    template_path: Path | None = None,
) -> Path:
    """Generate the flagship Excel dashboard."""
    data = json.loads(report_path.read_text())

    if excel_mode not in {"template", "standard"}:
        raise ValueError(f"Unsupported excel mode: {excel_mode}")

    if excel_mode == "template":
        template = resolve_template_path(template_path or DEFAULT_TEMPLATE_PATH)
        copy_template_to_output(output_path, template)
        wb = load_workbook(output_path)
    else:
        wb = Workbook()

    _build_excel_workbook(
        wb,
        data,
        trend_data=trend_data,
        diff_data=diff_data,
        score_history=score_history,
        portfolio_profile=portfolio_profile,
        collection=collection,
        excel_mode=excel_mode,
    )

    wb.save(str(output_path))
    if excel_mode == "template":
        inject_native_sparklines(
            output_path,
            _build_template_sparkline_specs(
                data,
                trend_data=trend_data,
                score_history=score_history,
            ),
        )
    return output_path
