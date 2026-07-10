"""Approval-center application flow."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.cli_output import print_info
from src.control_center_report_state import refresh_latest_report_state
from src.operator_approval_artifacts import write_approval_center_artifacts
from src.operator_approval_artifacts import (
    write_approval_receipt,
    write_followup_review_receipt,
)
from src.operator_prefs import load_rejection_events, post_process_approval_session
from src.approval_ledger import (
    build_approval_followup_record,
    build_approval_record,
    load_approval_ledger_bundle,
)
from src.report_shared_artifacts import refresh_shared_artifacts_from_report
from src.warehouse import save_approval_followup_event, save_approval_record


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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


def run_approval_capture_mode(args: Any, parser: Any) -> None:
    report_output_dir = Path(args.output_dir)
    try:
        _report_path, diff_dict, report = refresh_latest_report_state(report_output_dir, args)
    except FileNotFoundError:
        parser.error("No existing audit report found in output directory")
    bundle = load_approval_ledger_bundle(report_output_dir, report.to_dict(), list(report.operator_queue or []), approval_view="all")
    ledger = {str(item.get("approval_id") or ""): item for item in bundle.get("approval_ledger", [])}
    approval_id = f"governance:{args.governance_scope}" if args.approve_governance or args.review_governance else f"campaign:{args.campaign}"
    ledger_record = ledger.get(approval_id)
    if not ledger_record:
        parser.error("No matching approval subject is surfaced in the latest report.")
    if args.approve_governance or args.approve_packet:
        if ledger_record.get("approval_state") == "blocked":
            parser.error("That approval subject is blocked by non-approval prerequisites and cannot be approved yet.")
        if ledger_record.get("approval_state") == "not-applicable":
            parser.error("That approval subject is not part of the current approval workflow.")
        approval_record = build_approval_record(ledger_record, reviewer=args.approval_reviewer, note=args.approval_note or "")
        save_approval_record(report_output_dir, approval_record)
    else:
        if ledger_record.get("approval_state") in {"ready-for-review", "needs-reapproval", "blocked", "not-applicable"}:
            parser.error("That approval subject is not currently eligible for a recurring local follow-up review.")
        if str(ledger_record.get("follow_up_command") or "").strip() == "":
            parser.error("That approval subject does not currently expose a follow-up review command.")
        followup_event = build_approval_followup_record(ledger_record, reviewer=args.approval_reviewer, note=args.approval_note or "")
        save_approval_followup_event(report_output_dir, followup_event)
    _report_path, diff_dict, report = refresh_latest_report_state(report_output_dir, args)
    refresh_shared_artifacts_from_report(report, report_output_dir, args, diff_dict=diff_dict)
    approval_json, approval_md, _payload = write_approval_center_artifacts(report, report_output_dir, approval_view="all")
    updated_bundle = load_approval_ledger_bundle(report_output_dir, report.to_dict(), list(report.operator_queue or []), approval_view="all")
    updated_record = next((item for item in updated_bundle.get("approval_ledger", []) if item.get("approval_id") == approval_id), ledger_record)
    if args.approve_governance or args.approve_packet:
        receipt_payload = {**updated_record, **approval_record}
        receipt_json, receipt_md = write_approval_receipt(report_output_dir, report.username, generated_at=_utcnow(), receipt=receipt_payload)
        print_info(receipt_payload.get("summary", "Local approval captured."))
        print_info(f"Approval receipt JSON: {receipt_json}")
        print_info(f"Approval receipt Markdown: {receipt_md}")
    else:
        receipt_payload = {**updated_record, **followup_event}
        receipt_json, receipt_md = write_followup_review_receipt(report_output_dir, report.username, generated_at=_utcnow(), receipt=receipt_payload)
        print_info(receipt_payload.get("summary", "Local follow-up review captured."))
        print_info(f"Approval follow-up receipt JSON: {receipt_json}")
        print_info(f"Approval follow-up receipt Markdown: {receipt_md}")
    print_info(f"Approval center JSON: {approval_json}")
    print_info(f"Approval center Markdown: {approval_md}")
