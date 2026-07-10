"""Refresh the report state consumed by control-center flows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.diff import diff_reports
from src.governance_activation import build_governance_summary
from src.history import find_previous
from src.models import AuditReport
from src.operator_control_center import normalize_review_state
from src.report_operator_state import enrich_report_with_operator_state
from src.report_portfolio_catalog import apply_portfolio_catalog
from src.report_state import load_latest_report, report_from_dict


def refresh_latest_report_state(
    output_dir: Path,
    args: Any,
) -> tuple[Path, dict, AuditReport]:
    report_path, report_data = load_latest_report(output_dir)
    if not report_path or not report_data:
        raise FileNotFoundError("No existing audit report found in output directory")
    diff_dict = None
    previous_path = find_previous(report_path.name)
    if previous_path:
        diff_dict = diff_reports(
            previous_path,
            report_path,
            portfolio_profile=args.portfolio_profile,
            collection_name=args.collection,
        ).to_dict()
    report = report_from_dict(report_data)
    report_data = normalize_review_state(
        report.to_dict(),
        output_dir=output_dir,
        diff_data=diff_dict,
        portfolio_profile=args.portfolio_profile,
        collection_name=args.collection,
    )
    report_data["latest_report_path"] = str(report_path)
    report_data["governance_summary"] = build_governance_summary(report_data)
    report = report_from_dict(report_data)
    report = apply_portfolio_catalog(report, args)
    report = enrich_report_with_operator_state(
        report,
        output_dir=output_dir,
        diff_dict=diff_dict,
        triage_view=getattr(args, "triage_view", "all"),
        portfolio_profile=args.portfolio_profile,
        collection=args.collection,
    )
    return report_path, diff_dict or {}, report
