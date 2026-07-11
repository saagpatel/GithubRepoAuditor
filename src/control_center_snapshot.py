"""Catalog and scorecard enrichment for control-center snapshots."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.portfolio_catalog import (
    DEFAULT_CATALOG_PATH,
    build_catalog_line,
    catalog_entry_for_repo,
    evaluate_intent_alignment,
    load_portfolio_catalog,
)
from src.report_enrichment import build_operator_focus
from src.report_operating_paths import apply_operating_paths
from src.report_portfolio_catalog import apply_portfolio_catalog
from src.report_scorecards import apply_scorecards
from src.report_state import report_from_dict


def enrich_control_center_snapshot_from_report(
    report_data: dict,
    snapshot: dict,
    args: Any,
) -> dict:
    report = report_from_dict(
        {
            **report_data,
            "operator_summary": snapshot.get("operator_summary", {}),
            "operator_queue": snapshot.get("operator_queue", []),
        }
    )
    catalog_path = getattr(args, "catalog", None) or DEFAULT_CATALOG_PATH
    catalog_data = load_portfolio_catalog(Path(catalog_path))
    queue_by_repo = {
        str(item.get("repo") or item.get("repo_name") or "").strip(): item
        for item in report.operator_queue
        if str(item.get("repo") or item.get("repo_name") or "").strip()
    }
    for audit in report.audits:
        if (audit.portfolio_catalog or {}).get("has_explicit_entry"):
            continue
        base_entry = catalog_entry_for_repo(audit.metadata.to_dict(), catalog_data)
        if not base_entry.get("has_explicit_entry"):
            continue
        operator_focus = build_operator_focus(queue_by_repo.get(audit.metadata.name, {}))
        intent_alignment, intent_alignment_reason = evaluate_intent_alignment(
            base_entry,
            completeness_tier=audit.completeness_tier,
            archived=audit.metadata.archived,
            operator_focus=operator_focus,
        )
        audit.portfolio_catalog = {
            **base_entry,
            "catalog_line": build_catalog_line(base_entry),
            "intent_alignment": intent_alignment,
            "intent_alignment_reason": intent_alignment_reason,
            "intent_alignment_line": f"{intent_alignment}: {intent_alignment_reason}",
            "operator_focus": operator_focus,
        }
    if any(audit.portfolio_catalog for audit in report.audits):
        audit_lookup = {audit.metadata.name: audit.portfolio_catalog for audit in report.audits}
        for item in report.operator_queue:
            catalog_entry = audit_lookup.get(str(item.get("repo") or item.get("repo_name") or "").strip(), {})
            if catalog_entry:
                item["portfolio_catalog"] = dict(catalog_entry)
                item["catalog_line"] = catalog_entry.get("catalog_line", "")
                item["intent_alignment"] = catalog_entry.get("intent_alignment", "missing-contract")
                item["intent_alignment_reason"] = catalog_entry.get("intent_alignment_reason", "")
    else:
        report = apply_portfolio_catalog(report, args)
    report = apply_scorecards(report, args)
    report = apply_operating_paths(report)
    snapshot["operator_summary"] = report.operator_summary
    snapshot["operator_queue"] = report.operator_queue
    return snapshot
