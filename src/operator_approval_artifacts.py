"""Approval-center artifact construction independent of CLI dispatch."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.approval_ledger import load_approval_ledger_bundle, render_approval_center_markdown
from src.models import AuditReport
from src.operator_artifact_paths import (
    approval_center_paths,
    approval_receipt_paths,
    followup_review_receipt_paths,
)


def write_approval_center_artifacts(
    report: AuditReport,
    output_dir: Path,
    *,
    approval_view: str,
) -> tuple[Path, Path, dict]:
    report_data = report.to_dict()
    bundle = load_approval_ledger_bundle(
        output_dir,
        report_data,
        list(report.operator_queue or []),
        approval_view=approval_view,
    )
    report.approval_ledger = bundle["approval_ledger"]
    report.approval_workflow_summary = bundle["approval_workflow_summary"]
    report.next_approval_review = bundle["next_approval_review"]
    report.operator_queue = bundle.get("operator_queue", report.operator_queue)
    report.operator_summary = {
        **report.operator_summary,
        "approval_ledger": bundle["approval_ledger"],
        "approval_workflow_summary": bundle["approval_workflow_summary"],
        "next_approval_review": bundle["next_approval_review"],
        "top_ready_for_review_approvals": bundle["top_ready_for_review_approvals"],
        "top_needs_reapproval_approvals": bundle["top_needs_reapproval_approvals"],
        "top_overdue_approval_followups": bundle["top_overdue_approval_followups"],
        "top_due_soon_approval_followups": bundle["top_due_soon_approval_followups"],
        "top_approved_manual_approvals": bundle["top_approved_manual_approvals"],
        "top_blocked_approvals": bundle["top_blocked_approvals"],
    }
    generated_at = report.generated_at
    username = report.username
    json_path, md_path = approval_center_paths(output_dir, username, generated_at)
    payload = {
        "username": username,
        "generated_at": generated_at.isoformat(),
        "approval_view": approval_view,
        "approval_workflow_summary": bundle["approval_workflow_summary"],
        "next_approval_review": bundle["next_approval_review"],
        "approval_ledger": bundle["approval_ledger"],
        "top_ready_for_review_approvals": bundle["top_ready_for_review_approvals"],
        "top_needs_reapproval_approvals": bundle["top_needs_reapproval_approvals"],
        "top_overdue_approval_followups": bundle["top_overdue_approval_followups"],
        "top_due_soon_approval_followups": bundle["top_due_soon_approval_followups"],
        "top_approved_manual_approvals": bundle["top_approved_manual_approvals"],
        "top_blocked_approvals": bundle["top_blocked_approvals"],
        "operator_summary": report.operator_summary,
    }
    json_path.write_text(json.dumps(payload, indent=2))
    md_path.write_text(render_approval_center_markdown(payload))
    return json_path, md_path, payload


def write_approval_receipt(
    output_dir: Path,
    username: str,
    *,
    generated_at: datetime,
    receipt: dict,
) -> tuple[Path, Path]:
    json_path, md_path = approval_receipt_paths(output_dir, username, generated_at)
    json_path.write_text(json.dumps(receipt, indent=2))
    lines = [
        f"# Approval Receipt: {username}",
        "",
        f"- Generated: `{generated_at.isoformat()}`",
        f"- Subject: {receipt.get('label', 'Approval')}",
        f"- State: {receipt.get('approval_state', 'approved')}",
        f"- Reviewer: {receipt.get('approved_by', '') or 'local-operator'}",
        f"- Approved At: `{receipt.get('approved_at', '')}`",
        f"- Note: {receipt.get('approval_note', '') or '—'}",
        f"- Summary: {receipt.get('summary', 'Local approval captured.')}",
    ]
    if receipt.get("approval_command"):
        lines.append(f"- Approval Command: `{receipt.get('approval_command')}`")
    if receipt.get("manual_apply_command"):
        lines.append(f"- Manual Apply Command: `{receipt.get('manual_apply_command')}`")
    md_path.write_text("\n".join(lines) + "\n")
    return json_path, md_path


def write_followup_review_receipt(
    output_dir: Path,
    username: str,
    *,
    generated_at: datetime,
    receipt: dict,
) -> tuple[Path, Path]:
    json_path, md_path = followup_review_receipt_paths(output_dir, username, generated_at)
    json_path.write_text(json.dumps(receipt, indent=2))
    lines = [
        f"# Approval Follow-Up Receipt: {username}",
        "",
        f"- Generated: `{generated_at.isoformat()}`",
        f"- Subject: {receipt.get('label', 'Approval')}",
        f"- State: {receipt.get('approval_state', 'approved')} / {receipt.get('follow_up_state', 'not-applicable')}",
        f"- Reviewer: {receipt.get('reviewed_by', '') or 'local-operator'}",
        f"- Reviewed At: `{receipt.get('reviewed_at', '')}`",
        f"- Next Follow-Up Due: `{receipt.get('next_follow_up_due_at', '') or '—'}`",
        f"- Note: {receipt.get('review_note', '') or '—'}",
        f"- Summary: {receipt.get('summary', 'Local follow-up review captured.')}",
    ]
    if receipt.get("follow_up_command"):
        lines.append(f"- Follow-Up Command: `{receipt.get('follow_up_command')}`")
    if receipt.get("manual_apply_command"):
        lines.append(f"- Manual Apply Command: `{receipt.get('manual_apply_command')}`")
    md_path.write_text("\n".join(lines) + "\n")
    return json_path, md_path
