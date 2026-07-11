"""Portfolio-catalog enrichment for audit reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.models import AuditReport
from src.portfolio_catalog import (
    DEFAULT_CATALOG_PATH,
    build_catalog_line,
    build_intent_alignment_summary,
    build_portfolio_catalog_summary,
    catalog_entry_for_repo,
    evaluate_intent_alignment,
    load_portfolio_catalog,
)
from src.report_enrichment import build_operator_focus


def apply_portfolio_catalog(report: AuditReport, args: Any) -> AuditReport:
    catalog_path = getattr(args, "catalog", None) or DEFAULT_CATALOG_PATH
    catalog_data = load_portfolio_catalog(Path(catalog_path))
    queue_by_repo = {
        str(item.get("repo") or item.get("repo_name") or "").strip(): item
        for item in (report.operator_queue or [])
        if str(item.get("repo") or item.get("repo_name") or "").strip()
    }
    for audit in report.audits:
        base_entry = catalog_entry_for_repo(audit.metadata.to_dict(), catalog_data)
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
    audit_lookup = {audit.metadata.name: audit.portfolio_catalog for audit in report.audits}
    for item in report.operator_queue:
        repo_name = str(item.get("repo") or item.get("repo_name") or "").strip()
        catalog_entry = audit_lookup.get(repo_name, {})
        if catalog_entry:
            item["portfolio_catalog"] = dict(catalog_entry)
            item["catalog_line"] = catalog_entry.get("catalog_line", "")
            item["intent_alignment"] = catalog_entry.get("intent_alignment", "missing-contract")
            item["intent_alignment_reason"] = catalog_entry.get("intent_alignment_reason", "")
    report.portfolio_catalog_summary = build_portfolio_catalog_summary(
        report.audits,
        catalog_path=str(catalog_path),
    )
    report.portfolio_catalog_summary["catalog_exists"] = catalog_data.get("exists", False)
    report.portfolio_catalog_summary["errors"] = catalog_data.get("errors", [])
    report.portfolio_catalog_summary["warnings"] = catalog_data.get("warnings", [])
    report.intent_alignment_summary = build_intent_alignment_summary(report.audits)
    return report
