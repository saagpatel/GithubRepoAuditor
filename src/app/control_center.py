"""Control-center application flow."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.cli_output import print_info
from src.control_center_presentation import (
    _control_center_next_step_hint,
    _print_control_center_summary,
)
from src.control_center_snapshot import enrich_control_center_snapshot_from_report
from src.diff import diff_reports
from src.governance_activation import build_governance_summary
from src.history import find_previous
from src.operator_control_center import build_operator_snapshot, normalize_review_state
from src.operator_control_center_artifacts import write_control_center_artifacts
from src.report_state import load_latest_report, parse_iso_datetime, report_artifact_datetime


def run_control_center_mode(args: Any, parser: Any) -> None:
    output_dir = Path(args.output_dir)
    report_path, report_data = load_latest_report(output_dir)
    if not report_path or not report_data:
        parser.error("No existing audit report found in output directory")
    diff_dict = None
    previous_path = find_previous(report_path.name)
    if previous_path:
        diff_dict = diff_reports(
            previous_path, report_path, portfolio_profile=args.portfolio_profile,
            collection_name=args.collection,
        ).to_dict()
    report_data["latest_report_path"] = str(report_path)
    normalized = normalize_review_state(
        report_data, output_dir=output_dir, diff_data=diff_dict,
        portfolio_profile=args.portfolio_profile, collection_name=args.collection,
    )
    normalized["governance_summary"] = build_governance_summary(normalized)
    snapshot = build_operator_snapshot(normalized, output_dir=output_dir, triage_view=args.triage_view)
    snapshot = enrich_control_center_snapshot_from_report(normalized, snapshot, args)
    artifact_generated_at = report_artifact_datetime(
        report_path, parse_iso_datetime(normalized.get("generated_at")) or datetime.now(timezone.utc)
    )
    json_artifact, md_artifact, weekly_json, weekly_md, payload = write_control_center_artifacts(
        normalized, snapshot, output_dir, username=normalized.get("username", args.username),
        generated_at=artifact_generated_at, report_reference=str(report_path), diff_dict=diff_dict,
    )
    weekly_digest = payload.get("weekly_command_center_digest_v1", {})
    source_freshness = weekly_digest.get("source_freshness", {})
    if source_freshness.get("status") and source_freshness.get("status") != "current":
        print_info(weekly_digest.get("headline") or "Refresh the audit report before acting.")
        print_info(source_freshness.get("summary") or "Control-center source freshness could not be proven.")
        print_info(weekly_digest.get("decision") or "Refresh the audit report, then rerun.")
    else:
        _print_control_center_summary(snapshot)
    print_info(f"Control center JSON: {json_artifact}")
    print_info(f"Control center Markdown: {md_artifact}")
    print_info(f"Weekly command center JSON: {weekly_json}")
    print_info(f"Weekly command center Markdown: {weekly_md}")
    print_info(_control_center_next_step_hint())
