"""Helpers for workbook export runtime configuration."""

from __future__ import annotations

from typing import Any, Callable

from src.excel_workbook_helpers import (
    CORE_VISIBLE_SHEETS,
    DEFAULT_PREFERRED_SHEET_ORDER,
)
from src.excel_workbook_helpers import (
    finalize_workbook_structure as default_finalize_workbook_structure,
)
from src.excel_workbook_helpers import (
    run_workbook_build_steps as default_run_workbook_build_steps,
)


def build_excel_workbook_runtime(
    *,
    build_dashboard,
    build_all_repos,
    build_portfolio_explorer,
    build_portfolio_catalog_sheet,
    build_scorecards_sheet,
    build_repo_detail,
    build_by_lens,
    build_by_collection,
    build_trend_summary,
    build_run_changes,
    build_heatmap,
    build_quick_wins,
    build_badges,
    build_tech_stack,
    build_trends,
    build_tier_breakdown,
    build_activity,
    build_repo_profiles,
    build_security,
    build_security_controls,
    build_supply_chain,
    build_security_debt,
    build_campaigns,
    build_initiative_tracker,
    build_writeback_audit,
    build_governance_controls,
    build_governance_audit,
    build_review_queue,
    build_review_history_sheet,
    build_hotspots,
    build_implementation_hotspots,
    build_operator_outcomes,
    build_approval_ledger,
    build_historical_intelligence,
    build_compare_sheet,
    build_scenario_planner,
    build_executive_summary,
    build_print_pack,
    build_changes,
    build_reconciliation,
    build_dependency_graph,
    build_score_explainer,
    build_action_items,
    build_hidden_data_sheets,
    build_navigation,
    inject_sheet_navigation,
    apply_workbook_named_ranges,
    template_info_sheet: str,
    run_workbook_build_steps: Callable[..., Any] | None = None,
    finalize_workbook_structure: Callable[..., Any] | None = None,
    core_visible_sheets: set[str] | None = None,
    preferred_order: list[str] | None = None,
) -> dict[str, Any]:
    build_steps_runner = run_workbook_build_steps or default_run_workbook_build_steps
    workbook_finalizer = finalize_workbook_structure or default_finalize_workbook_structure
    visible_sheets = set(
        CORE_VISIBLE_SHEETS if core_visible_sheets is None else core_visible_sheets
    )
    sheet_order = list(
        DEFAULT_PREFERRED_SHEET_ORDER if preferred_order is None else preferred_order
    )

    return {
        "run_workbook_build_steps": build_steps_runner,
        "build_dashboard": build_dashboard,
        "build_all_repos": build_all_repos,
        "build_portfolio_explorer": build_portfolio_explorer,
        "build_portfolio_catalog_sheet": build_portfolio_catalog_sheet,
        "build_scorecards_sheet": build_scorecards_sheet,
        "build_repo_detail": build_repo_detail,
        "build_by_lens": build_by_lens,
        "build_by_collection": build_by_collection,
        "build_trend_summary": build_trend_summary,
        "build_run_changes": build_run_changes,
        "build_heatmap": build_heatmap,
        "build_quick_wins": build_quick_wins,
        "build_badges": build_badges,
        "build_tech_stack": build_tech_stack,
        "build_trends": build_trends,
        "build_tier_breakdown": build_tier_breakdown,
        "build_activity": build_activity,
        "build_repo_profiles": build_repo_profiles,
        "build_security": build_security,
        "build_security_controls": build_security_controls,
        "build_supply_chain": build_supply_chain,
        "build_security_debt": build_security_debt,
        "build_campaigns": build_campaigns,
        "build_initiative_tracker": build_initiative_tracker,
        "build_writeback_audit": build_writeback_audit,
        "build_governance_controls": build_governance_controls,
        "build_governance_audit": build_governance_audit,
        "build_review_queue": build_review_queue,
        "build_review_history_sheet": build_review_history_sheet,
        "build_hotspots": build_hotspots,
        "build_implementation_hotspots": build_implementation_hotspots,
        "build_operator_outcomes": build_operator_outcomes,
        "build_approval_ledger": build_approval_ledger,
        "build_historical_intelligence": build_historical_intelligence,
        "build_compare_sheet": build_compare_sheet,
        "build_scenario_planner": build_scenario_planner,
        "build_executive_summary": build_executive_summary,
        "build_print_pack": build_print_pack,
        "build_changes": build_changes,
        "build_reconciliation": build_reconciliation,
        "build_dependency_graph": build_dependency_graph,
        "build_score_explainer": build_score_explainer,
        "build_action_items": build_action_items,
        "build_hidden_data_sheets": build_hidden_data_sheets,
        "build_navigation": build_navigation,
        "inject_sheet_navigation": inject_sheet_navigation,
        "apply_workbook_named_ranges": apply_workbook_named_ranges,
        "finalize_workbook_structure": workbook_finalizer,
        "core_visible_sheets": visible_sheets,
        "template_info_sheet": template_info_sheet,
        "preferred_order": sheet_order,
    }
