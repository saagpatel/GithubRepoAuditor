"""Scorecard enrichment for audit reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.models import AuditReport
from src.portfolio_catalog import build_intent_alignment_summary, evaluate_intent_alignment
from src.report_enrichment import (
    build_maturity_gap_summary,
    build_operator_focus,
    build_scorecard_line,
)
from src.scorecards import (
    DEFAULT_SCORECARDS_PATH,
    evaluate_scorecards_for_report,
    load_scorecards,
)


def apply_scorecards(report: AuditReport, args: Any) -> AuditReport:
    scorecards_path = getattr(args, "scorecards", None) or DEFAULT_SCORECARDS_PATH
    scorecards_data = load_scorecards(Path(scorecards_path))
    repo_results, summary, programs = evaluate_scorecards_for_report(report, scorecards_data)
    by_repo = {result.get("repo", ""): result for result in repo_results}
    queue_by_repo = {
        str(item.get("repo") or item.get("repo_name") or "").strip(): item
        for item in (report.operator_queue or [])
        if str(item.get("repo") or item.get("repo_name") or "").strip()
    }
    for audit in report.audits:
        result = by_repo.get(audit.metadata.name, {})
        audit.scorecard = dict(result)
        if audit.portfolio_catalog:
            audit.portfolio_catalog["scorecard"] = dict(result)
            operator_focus = audit.portfolio_catalog.get("operator_focus", "")
            if not operator_focus:
                operator_focus = build_operator_focus(
                    queue_by_repo.get(audit.metadata.name, {})
                )
            intent_alignment, intent_alignment_reason = evaluate_intent_alignment(
                audit.portfolio_catalog,
                completeness_tier=audit.completeness_tier,
                archived=audit.metadata.archived,
                operator_focus=operator_focus,
            )
            audit.portfolio_catalog.update(
                {
                    "intent_alignment": intent_alignment,
                    "intent_alignment_reason": intent_alignment_reason,
                    "intent_alignment_line": f"{intent_alignment}: {intent_alignment_reason}",
                    "operator_focus": operator_focus,
                }
            )
    catalog_by_repo = {audit.metadata.name: audit.portfolio_catalog for audit in report.audits}
    for item in report.operator_queue:
        repo_name = str(item.get("repo") or item.get("repo_name") or "").strip()
        result = by_repo.get(repo_name, {})
        catalog_entry = catalog_by_repo.get(repo_name, {})
        if catalog_entry:
            item["portfolio_catalog"] = dict(catalog_entry)
            item["intent_alignment"] = catalog_entry.get("intent_alignment", "")
            item["intent_alignment_reason"] = catalog_entry.get("intent_alignment_reason", "")
        if result:
            item["scorecard"] = dict(result)
            item["scorecard_line"] = build_scorecard_line(item)
            item["maturity_gap_summary"] = build_maturity_gap_summary(item)
    report.scorecards_summary = summary
    report.scorecard_programs = programs
    report.intent_alignment_summary = build_intent_alignment_summary(report.audits)
    return report
