"""Operating-path enrichment for reconstructed audit reports."""

from __future__ import annotations

from src.models import AuditReport
from src.portfolio_pathing import (
    build_operating_path_entry,
    build_operating_path_line,
    build_operating_paths_summary,
)


def apply_operating_paths(report: AuditReport) -> AuditReport:
    for audit in report.audits:
        catalog_entry = dict(audit.portfolio_catalog or {})
        if not catalog_entry:
            continue
        path_entry = build_operating_path_entry(
            catalog_entry,
            intent_alignment=catalog_entry.get("intent_alignment", ""),
            archived=audit.metadata.archived,
            completeness_tier=audit.completeness_tier,
            decision_quality_status=(report.operator_summary or {})
            .get("decision_quality_v1", {})
            .get("decision_quality_status", ""),
        )
        path_line = build_operating_path_line(path_entry)
        audit.portfolio_catalog = {
            **path_entry,
            "operating_path_line": path_line,
            "operator_focus": catalog_entry.get("operator_focus", ""),
        }
        if audit.scorecard:
            audit.portfolio_catalog["scorecard"] = dict(audit.scorecard)
    audit_lookup = {audit.metadata.name: audit.portfolio_catalog for audit in report.audits}
    for item in report.operator_queue:
        repo_name = str(item.get("repo") or item.get("repo_name") or "").strip()
        catalog_entry = audit_lookup.get(repo_name, {})
        if not catalog_entry:
            continue
        item["portfolio_catalog"] = dict(catalog_entry)
        item["operating_path"] = catalog_entry.get("operating_path", "")
        item["path_override"] = catalog_entry.get("path_override", "")
        item["path_confidence"] = catalog_entry.get("path_confidence", "")
        item["path_rationale"] = catalog_entry.get("path_rationale", "")
        item["operating_path_line"] = catalog_entry.get("operating_path_line", "")
    report.operating_paths_summary = build_operating_paths_summary(report.audits)
    return report
