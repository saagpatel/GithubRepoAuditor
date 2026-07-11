"""Regenerate shared operator artifacts from an enriched audit report."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.excel_export import export_excel
from src.history import load_repo_score_history, load_trend_data
from src.models import AuditReport
from src.operator_approval_artifacts import write_approval_center_artifacts
from src.operator_control_center_artifacts import write_control_center_artifacts
from src.report_state import report_artifact_datetime
from src.reporter import (
    write_json_report,
    write_markdown_report,
    write_pcc_export,
    write_raw_metadata,
)
from src.review_pack import export_review_pack
from src.warehouse import write_warehouse_snapshot
from src.web_export import export_html_dashboard


def refresh_shared_artifacts_from_report(
    report: AuditReport,
    output_dir: Path,
    args: Any,
    *,
    diff_dict: dict | None = None,
) -> dict[str, Path]:
    approval_json, approval_md, _payload = write_approval_center_artifacts(
        report, output_dir, approval_view=getattr(args, "approval_view", "all")
    )
    json_path = write_json_report(report, output_dir)
    write_markdown_report(report, output_dir, diff_data=diff_dict)
    write_pcc_export(report, output_dir)
    write_raw_metadata(report, output_dir)
    trend_data = load_trend_data()
    score_history = load_repo_score_history()
    export_excel(
        json_path,
        output_dir / f"audit-dashboard-{report.username}-{report.generated_at.strftime('%Y-%m-%d')}.xlsx",
        trend_data=trend_data, diff_data=diff_dict, score_history=score_history,
        portfolio_profile=args.portfolio_profile, collection=args.collection,
        excel_mode=args.excel_mode, truth_dir=output_dir,
    )
    export_review_pack(report.to_dict(), output_dir, diff_data=diff_dict,
                       portfolio_profile=args.portfolio_profile, collection=args.collection)
    export_html_dashboard(report.to_dict(), output_dir, trend_data, score_history,
                          diff_data=diff_dict, portfolio_profile=args.portfolio_profile,
                          collection=args.collection)
    artifact_generated_at = report_artifact_datetime(json_path, report.generated_at)
    snapshot = {"operator_summary": report.operator_summary, "operator_queue": report.operator_queue}
    control_json, control_md, weekly_json, weekly_md, _control_payload = write_control_center_artifacts(
        report.to_dict(), snapshot, output_dir, username=report.username,
        generated_at=artifact_generated_at, report_reference=str(json_path), diff_dict=diff_dict,
    )
    report.operator_summary["control_center_reference"] = str(control_json)
    write_warehouse_snapshot(report, output_dir, json_path)
    return {
        "json_path": json_path, "control_center_json": control_json,
        "control_center_md": control_md, "weekly_command_center_json": weekly_json,
        "weekly_command_center_md": weekly_md, "approval_center_json": approval_json,
        "approval_center_md": approval_md,
    }
