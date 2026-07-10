"""Approval-center application flow."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.cli_output import print_info
from src.control_center_report_state import refresh_latest_report_state
from src.operator_approval_artifacts import write_approval_center_artifacts
from src.operator_prefs import load_rejection_events, post_process_approval_session


def _post_process_approval_center_prefs(payload: dict, output_dir: Path) -> None:
    try:
        rejection_records = load_rejection_events(output_dir)
        total, newly_added = post_process_approval_session(rejection_records, output_dir)
        print_info(f"Suppressions: {total} action type(s) suppressed ({newly_added} newly added).")
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).warning(
            "operator_prefs post-process failed (non-fatal): %s", exc
        )


def run_approval_center_mode(args: Any, parser: Any) -> None:
    report_output_dir = Path(args.output_dir)
    try:
        _report_path, _diff_dict, report = refresh_latest_report_state(report_output_dir, args)
    except FileNotFoundError:
        parser.error("No existing audit report found in output directory")
    approval_json, approval_md, payload = write_approval_center_artifacts(
        report, report_output_dir, approval_view=args.approval_view
    )
    print_info(payload.get("approval_workflow_summary", {}).get("summary", "No current approval needs review yet."))
    print_info(payload.get("next_approval_review", {}).get("summary", "Stay local for now; no current approval needs review."))
    print_info(f"Approval center JSON: {approval_json}")
    print_info(f"Approval center Markdown: {approval_md}")
    _post_process_approval_center_prefs(payload, report_output_dir)
