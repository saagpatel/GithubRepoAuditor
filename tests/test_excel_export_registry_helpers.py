from __future__ import annotations

from src.excel_export_registry_helpers import build_excel_workbook_runtime
from src.excel_workbook_helpers import (
    CORE_VISIBLE_SHEETS,
    DEFAULT_PREFERRED_SHEET_ORDER,
    finalize_workbook_structure,
    run_workbook_build_steps,
)


def _noop(*_args, **_kwargs) -> None:
    return None


def _runtime_kwargs() -> dict:
    builders = {
        "build_dashboard": _noop,
        "build_all_repos": _noop,
        "build_portfolio_explorer": _noop,
        "build_portfolio_catalog_sheet": _noop,
        "build_scorecards_sheet": _noop,
        "build_repo_detail": _noop,
        "build_by_lens": _noop,
        "build_by_collection": _noop,
        "build_trend_summary": _noop,
        "build_run_changes": _noop,
        "build_heatmap": _noop,
        "build_quick_wins": _noop,
        "build_badges": _noop,
        "build_tech_stack": _noop,
        "build_trends": _noop,
        "build_tier_breakdown": _noop,
        "build_activity": _noop,
        "build_repo_profiles": _noop,
        "build_security": _noop,
        "build_security_controls": _noop,
        "build_supply_chain": _noop,
        "build_security_debt": _noop,
        "build_campaigns": _noop,
        "build_initiative_tracker": _noop,
        "build_writeback_audit": _noop,
        "build_governance_controls": _noop,
        "build_governance_audit": _noop,
        "build_review_queue": _noop,
        "build_review_history_sheet": _noop,
        "build_hotspots": _noop,
        "build_implementation_hotspots": _noop,
        "build_operator_outcomes": _noop,
        "build_approval_ledger": _noop,
        "build_historical_intelligence": _noop,
        "build_compare_sheet": _noop,
        "build_scenario_planner": _noop,
        "build_executive_summary": _noop,
        "build_print_pack": _noop,
        "build_changes": _noop,
        "build_reconciliation": _noop,
        "build_dependency_graph": _noop,
        "build_score_explainer": _noop,
        "build_action_items": _noop,
        "build_hidden_data_sheets": _noop,
        "build_navigation": _noop,
        "inject_sheet_navigation": _noop,
        "apply_workbook_named_ranges": _noop,
    }
    return {**builders, "template_info_sheet": "Template Info"}


def test_workbook_runtime_owns_default_structure_contracts() -> None:
    runtime = build_excel_workbook_runtime(**_runtime_kwargs())

    assert runtime["run_workbook_build_steps"] is run_workbook_build_steps
    assert runtime["finalize_workbook_structure"] is finalize_workbook_structure
    assert runtime["core_visible_sheets"] == CORE_VISIBLE_SHEETS
    assert runtime["core_visible_sheets"] is not CORE_VISIBLE_SHEETS
    assert runtime["preferred_order"] == DEFAULT_PREFERRED_SHEET_ORDER
    assert runtime["preferred_order"] is not DEFAULT_PREFERRED_SHEET_ORDER


def test_workbook_runtime_allows_explicit_structure_contracts() -> None:
    runtime = build_excel_workbook_runtime(
        **_runtime_kwargs(),
        run_workbook_build_steps=_noop,
        finalize_workbook_structure=_noop,
        core_visible_sheets={"Dashboard"},
        preferred_order=["Dashboard", "Index"],
    )

    assert runtime["run_workbook_build_steps"] is _noop
    assert runtime["finalize_workbook_structure"] is _noop
    assert runtime["core_visible_sheets"] == {"Dashboard"}
    assert runtime["preferred_order"] == ["Dashboard", "Index"]
