from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.governance_activation import SCOPE_TO_KEYS
from src.terminology import ACTION_SYNC_CANONICAL_LABELS
from src.warehouse import load_approval_records, load_recent_action_runs

APPROVAL_STATE_PRIORITY = {
    "needs-reapproval": 0,
    "ready-for-review": 1,
    "approved-manual": 2,
    "blocked": 3,
    "applied": 4,
    "not-applicable": 5,
}

APPROVAL_VIEW_TO_STATES = {
    "all": set(APPROVAL_STATE_PRIORITY),
    "ready": {"ready-for-review"},
    "approved": {"approved-manual"},
    "needs-reapproval": {"needs-reapproval"},
    "blocked": {"blocked"},
    "applied": {"applied"},
}

GOVERNANCE_SCOPES = (
    "all",
    "codeql",
    "secret-scanning",
    "push-protection",
    "code-security",
)


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return {}


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in (value or [])]


def _username(report_data: dict[str, Any]) -> str:
    return str(report_data.get("username") or "<github-username>")


def default_approval_reviewer() -> str:
    reviewer = os.environ.get("USER", "").strip()
    if reviewer:
        return reviewer
    try:
        result = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        result = None
    if result and result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return "local-operator"


def _latest_report_run_id(report_data: dict[str, Any]) -> str:
    operator_summary = _mapping(report_data.get("operator_summary"))
    return str(operator_summary.get("source_run_id") or report_data.get("run_id") or "")


def _governance_actions_for_scope(report_data: dict[str, Any], scope: str) -> list[dict[str, Any]]:
    preview = _mapping(report_data.get("governance_preview"))
    actions = _rows(preview.get("actions"))
    if not actions:
        return []
    if scope == "all":
        return actions
    allowed = SCOPE_TO_KEYS.get(scope, set())
    return [item for item in actions if str(item.get("control_key") or "") in allowed]


def _campaign_fingerprint(packet: dict[str, Any]) -> str:
    material = {
        "campaign_type": str(packet.get("campaign_type") or ""),
        "recommended_target": str(packet.get("recommended_target") or "none"),
        "sync_mode": str(packet.get("sync_mode") or "reconcile"),
        "blocker_types": sorted(str(item) for item in (packet.get("blocker_types") or [])),
        "rollback_status": str(packet.get("rollback_status") or "not-applicable"),
        "action_ids": sorted(str(item.get("action_id") or "") for item in (packet.get("actions") or [])),
        "top_repos": sorted(str(item) for item in (packet.get("top_repos") or [])),
    }
    return hashlib.sha1(json.dumps(material, sort_keys=True).encode("utf-8")).hexdigest()


def _approval_record_index(history: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for item in history:
        approval_id = str(item.get("approval_id") or "")
        if not approval_id:
            continue
        previous = grouped.get(approval_id)
        if previous is None or str(item.get("approved_at") or "") > str(previous.get("approved_at") or ""):
            grouped[approval_id] = item
    return grouped


def _recent_apply_seen(
    output_dir: Path,
    username: str,
    *,
    campaign_type: str | None = None,
) -> bool:
    rows = load_recent_action_runs(output_dir, username, limit=200)
    for row in rows:
        if campaign_type and str(row.get("campaign_type") or "") != campaign_type:
            continue
        if str(row.get("status") or "") in {"applied", "updated"} or str(row.get("reconciliation_outcome") or "") == "applied":
            return True
    return False


def _governance_apply_seen(report_data: dict[str, Any], scope: str) -> bool:
    results = _rows(_mapping(report_data.get("governance_results")).get("results"))
    if not results:
        return False
    if scope == "all":
        return any(str(item.get("status") or "") == "applied" for item in results)
    allowed = SCOPE_TO_KEYS.get(scope, set())
    return any(
        str(item.get("status") or "") == "applied"
        and str(item.get("control_key") or "") in allowed
        for item in results
    )


def _governance_record(
    report_data: dict[str, Any],
    scope: str,
    latest_record: dict[str, Any] | None,
    *,
    output_dir: Path,
) -> dict[str, Any]:
    actions = _governance_actions_for_scope(report_data, scope)
    preview = _mapping(report_data.get("governance_preview"))
    summary = _mapping(report_data.get("governance_summary"))
    drift_rows = _rows(report_data.get("governance_drift"))
    current_fingerprint = str(preview.get("fingerprint") or "")
    approval_id = f"governance:{scope}"
    source_run_id = _latest_report_run_id(report_data)
    record = dict(latest_record or {})
    approval_ready = bool(actions)
    apply_ready_after_approval = bool(sum(1 for item in actions if item.get("applyable")))
    blocked = summary.get("status") == "drifted" and not summary.get("needs_reapproval")
    has_matching = bool(record and current_fingerprint and record.get("fingerprint") == current_fingerprint)
    has_approval = bool(record)
    needs_reapproval = bool(
        has_approval
        and (
            summary.get("needs_reapproval")
            or (
                current_fingerprint
                and str(record.get("fingerprint") or "")
                and str(record.get("fingerprint") or "") != current_fingerprint
            )
        )
    )
    applied = has_matching and _governance_apply_seen(report_data, scope)

    if not actions:
        state = "not-applicable"
    elif needs_reapproval:
        state = "needs-reapproval"
    elif blocked:
        state = "blocked"
    elif applied:
        state = "applied"
    elif has_matching:
        state = "approved-manual"
    else:
        state = "ready-for-review"

    review_checklist = [
        "Confirm the governed controls and scope are still the intended next step.",
        "Review fingerprint drift, approval age, and any governance drift notes.",
        "Keep external mutation separate from approval capture.",
    ]
    review_command = f"audit {_username(report_data)} --approval-center --approval-view ready"
    approval_command = f"audit {_username(report_data)} --approve-governance --governance-scope {scope}"
    manual_apply_command = ""
    if state == "needs-reapproval":
        summary_line = f"Governance scope {scope} needs re-approval before any manual apply step."
    elif state == "ready-for-review":
        summary_line = f"Governance scope {scope} is ready for review."
    elif state == "approved-manual":
        summary_line = f"Governance scope {scope} is approved but still waits on an explicit manual apply step."
    elif state == "blocked":
        summary_line = f"Governance scope {scope} is blocked by drift or non-approval prerequisites."
    elif state == "applied":
        summary_line = f"Governance scope {scope} has already been applied and does not need a fresh approval yet."
    else:
        summary_line = f"Governance scope {scope} does not have an approval workflow in the current run."

    return {
        "approval_id": approval_id,
        "approval_subject_type": "governance",
        "subject_key": scope,
        "label": f"Governance: {scope}",
        "approval_state": state,
        "source_run_id": source_run_id,
        "fingerprint": current_fingerprint,
        "approved_at": record.get("approved_at"),
        "approved_by": record.get("approved_by", ""),
        "approval_note": record.get("approval_note", ""),
        "approval_ready": approval_ready,
        "apply_ready_after_approval": apply_ready_after_approval,
        "review_checklist": review_checklist,
        "review_command": review_command,
        "approval_command": approval_command,
        "manual_apply_command": manual_apply_command,
        "summary": summary_line,
        "control_family": scope,
        "action_count": len(actions),
        "applyable_count": sum(1 for item in actions if item.get("applyable")),
        "drift_count": len(drift_rows),
    }


def _campaign_record(
    report_data: dict[str, Any],
    packet: dict[str, Any],
    automation: dict[str, Any],
    latest_record: dict[str, Any] | None,
    *,
    output_dir: Path,
) -> dict[str, Any]:
    campaign_type = str(packet.get("campaign_type") or "")
    approval_id = f"campaign:{campaign_type}"
    source_run_id = _latest_report_run_id(report_data)
    blocker_types = set(str(item) for item in (packet.get("blocker_types") or []))
    eligible = bool(
        campaign_type
        and (
            str(packet.get("execution_state") or "") == "needs-approval"
            or str(automation.get("automation_posture") or "") == "approval-first"
        )
    )
    if not eligible:
        return {}

    allowed_blockers = blocker_types.issubset({"governance-approval", "rollback-coverage"})
    fingerprint = _campaign_fingerprint(packet)
    record = dict(latest_record or {})
    has_matching = bool(record and fingerprint and str(record.get("fingerprint") or "") == fingerprint)
    has_approval = bool(record)
    needs_reapproval = bool(
        has_approval
        and (
            fingerprint
            and str(record.get("fingerprint") or "")
            and str(record.get("fingerprint") or "") != fingerprint
        )
    )
    applied = has_matching and _recent_apply_seen(output_dir, _username(report_data), campaign_type=campaign_type)
    apply_ready_after_approval = allowed_blockers and bool(packet.get("action_count", 0))
    if needs_reapproval:
        state = "needs-reapproval"
    elif not allowed_blockers:
        state = "blocked"
    elif applied:
        state = "applied"
    elif has_matching:
        state = "approved-manual"
    elif apply_ready_after_approval:
        state = "ready-for-review"
    else:
        state = "blocked"

    label = str(packet.get("label") or campaign_type or "Campaign")
    review_checklist = [
        "Confirm the campaign target, sync mode, and top repos are still the intended next step.",
        "Review approval-only blockers and rollback coverage before capturing approval.",
        "Keep apply separate from approval capture.",
    ]
    review_command = f"audit {_username(report_data)} --approval-center --approval-view ready"
    approval_command = f"audit {_username(report_data)} --campaign {campaign_type} --approve-packet"
    manual_apply_command = ""
    if state in {"approved-manual", "applied"}:
        manual_apply_command = str(packet.get("apply_command") or "")
    if state == "needs-reapproval":
        summary_line = f"{label} needs re-approval because the approval fingerprint or approval-only blockers changed."
    elif state == "ready-for-review":
        summary_line = f"{label} is ready for approval review and would still remain a manual apply decision afterward."
    elif state == "approved-manual":
        summary_line = f"{label} is approved but still waits on an explicit manual apply step."
    elif state == "blocked":
        summary_line = f"{label} is blocked by non-approval prerequisites, so approval alone cannot clear the path."
    elif state == "applied":
        summary_line = f"{label} has already been applied with a matching approval and does not need a fresh approval yet."
    else:
        summary_line = f"{label} does not currently participate in the approval workflow."

    return {
        "approval_id": approval_id,
        "approval_subject_type": "campaign",
        "subject_key": campaign_type,
        "label": label,
        "approval_state": state,
        "source_run_id": source_run_id,
        "fingerprint": fingerprint,
        "approved_at": record.get("approved_at"),
        "approved_by": record.get("approved_by", ""),
        "approval_note": record.get("approval_note", ""),
        "approval_ready": allowed_blockers,
        "apply_ready_after_approval": apply_ready_after_approval,
        "review_checklist": review_checklist,
        "review_command": review_command,
        "approval_command": approval_command,
        "manual_apply_command": manual_apply_command,
        "summary": summary_line,
        "blocker_types": sorted(blocker_types),
        "recommended_target": packet.get("recommended_target", "none"),
        "sync_mode": packet.get("sync_mode", "reconcile"),
    }


def _queue_approval(
    queue: list[dict[str, Any]],
    approval_by_key: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    governance_record = approval_by_key.get("governance:all", {})
    for item in queue:
        mapped = dict(item)
        campaign_type = str(mapped.get("suggested_campaign") or "").strip()
        record = approval_by_key.get(f"campaign:{campaign_type}", {})
        if str(mapped.get("kind") or "") == "governance":
            record = governance_record
        mapped["approval_state"] = str(record.get("approval_state") or "not-applicable")
        mapped["approval_summary"] = str(record.get("summary") or "No approval workflow is surfaced for this item yet.")
        mapped["approval_line"] = f"{ACTION_SYNC_CANONICAL_LABELS['approval_workflow']}: {mapped['approval_summary']}"
        enriched.append(mapped)
    return enriched


def _summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    actionable = [item for item in records if item.get("approval_state") != "not-applicable"]
    if not actionable:
        return {
            "summary": "No current approval needs review yet, so the approval workflow can stay local for now.",
            "counts": {state: 0 for state in APPROVAL_STATE_PRIORITY},
        }
    ordered = sorted(
        actionable,
        key=lambda item: (
            APPROVAL_STATE_PRIORITY.get(str(item.get("approval_state") or "not-applicable"), 99),
            str(item.get("label") or ""),
        ),
    )
    top = ordered[0]
    state = str(top.get("approval_state") or "not-applicable")
    label = str(top.get("label") or top.get("subject_key") or "Approval")
    if state == "needs-reapproval":
        summary = f"{label} needs re-approval before the next manual apply step."
    elif state == "ready-for-review":
        summary = f"{label} is the strongest approval review candidate right now."
    elif state == "approved-manual":
        summary = f"{label} is already approved and now waits on an explicit manual apply step."
    elif state == "blocked":
        summary = f"{label} is blocked for reasons that approval alone cannot solve."
    else:
        summary = f"{label} has already been applied and does not need a new approval yet."
    return {
        "summary": summary,
        "counts": {
            state: sum(1 for item in actionable if item.get("approval_state") == state)
            for state in APPROVAL_STATE_PRIORITY
        },
    }


def _next_review(records: list[dict[str, Any]]) -> dict[str, Any]:
    actionable = [item for item in records if item.get("approval_state") != "not-applicable"]
    if not actionable:
        return {"summary": "Stay local for now; no current approval needs review."}
    ordered = sorted(
        actionable,
        key=lambda item: (
            APPROVAL_STATE_PRIORITY.get(str(item.get("approval_state") or "not-applicable"), 99),
            str(item.get("label") or ""),
        ),
    )
    top = dict(ordered[0])
    state = str(top.get("approval_state") or "not-applicable")
    label = str(top.get("label") or top.get("subject_key") or "Approval")
    if state == "needs-reapproval":
        top["summary"] = f"Re-approve {label} before any manual apply step."
    elif state == "ready-for-review":
        top["summary"] = f"Review {label} next and decide whether to capture approval."
    elif state == "approved-manual":
        top["summary"] = f"{label} is approved; the next move is still an explicit manual apply."
    elif state == "blocked":
        top["summary"] = f"{label} is blocked; resolve the non-approval blockers before expecting approval to help."
    else:
        top["summary"] = f"{label} has already been applied and does not need a fresh approval yet."
    return top


def build_approval_record(
    ledger_record: dict[str, Any],
    *,
    reviewer: str,
    note: str = "",
) -> dict[str, Any]:
    return {
        "approval_id": ledger_record.get("approval_id", ""),
        "approval_subject_type": ledger_record.get("approval_subject_type", ""),
        "subject_key": ledger_record.get("subject_key", ""),
        "source_run_id": ledger_record.get("source_run_id", ""),
        "fingerprint": ledger_record.get("fingerprint", ""),
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "approved_by": reviewer,
        "approval_note": note,
        "details_json": dict(ledger_record),
    }


def render_approval_center_markdown(payload: dict[str, Any]) -> str:
    summary = _mapping(payload.get("approval_workflow_summary"))
    next_review = _mapping(payload.get("next_approval_review"))
    records = _rows(payload.get("approval_ledger"))
    sections = (
        ("Needs Re-Approval", "needs-reapproval"),
        ("Ready For Review", "ready-for-review"),
        ("Approved But Manual", "approved-manual"),
        ("Blocked", "blocked"),
    )
    lines = [
        f"# {ACTION_SYNC_CANONICAL_LABELS['approval_workflow']}: {payload.get('username', 'unknown')}",
        "",
        f"- Generated: `{payload.get('generated_at', '')}`",
        f"- Summary: {summary.get('summary', 'No current approval needs review yet, so the approval workflow can stay local for now.')}",
        f"- {ACTION_SYNC_CANONICAL_LABELS['next_approval_review']}: {next_review.get('summary', 'Stay local for now; no current approval needs review.')}",
        "",
    ]
    for label, state in sections:
        lines.append(f"## {label}")
        bucket = [item for item in records if item.get("approval_state") == state]
        if not bucket:
            lines.append("- None")
            lines.append("")
            continue
        for item in bucket:
            lines.append(f"- {item.get('label', item.get('subject_key', 'Approval'))}: {item.get('summary', 'No approval summary is recorded yet.')}")
            if item.get("approval_command"):
                lines.append(f"  - Approval command: `{item.get('approval_command')}`")
            if item.get("manual_apply_command"):
                lines.append(f"  - Manual apply command: `{item.get('manual_apply_command')}`")
            if item.get("approved_by"):
                lines.append(f"  - Approved by: `{item.get('approved_by')}` at `{item.get('approved_at', '')}`")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def filter_approval_ledger(records: list[dict[str, Any]], approval_view: str) -> list[dict[str, Any]]:
    allowed = APPROVAL_VIEW_TO_STATES.get(approval_view, APPROVAL_VIEW_TO_STATES["all"])
    return [item for item in records if str(item.get("approval_state") or "not-applicable") in allowed]


def load_approval_ledger_bundle(
    output_dir: Path,
    report_data: dict[str, Any],
    queue: list[dict[str, Any]],
    *,
    approval_view: str = "all",
) -> dict[str, Any]:
    username = _username(report_data)
    history = load_approval_records(output_dir, username, limit=300)
    latest_by_id = _approval_record_index(history)
    packets = {
        str(item.get("campaign_type") or ""): item
        for item in _rows(_mapping(report_data.get("operator_summary")).get("action_sync_packets") or report_data.get("action_sync_packets"))
    }
    automation = {
        str(item.get("campaign_type") or ""): item
        for item in _rows(_mapping(report_data.get("operator_summary")).get("action_sync_automation") or report_data.get("action_sync_automation"))
    }

    records: list[dict[str, Any]] = []
    if _governance_actions_for_scope(report_data, "all"):
        for scope in GOVERNANCE_SCOPES:
            records.append(
                _governance_record(
                    report_data,
                    scope,
                    latest_by_id.get(f"governance:{scope}"),
                    output_dir=output_dir,
                )
            )
    for campaign_type, packet in packets.items():
        record = _campaign_record(
            report_data,
            packet,
            automation.get(campaign_type, {}),
            latest_by_id.get(f"campaign:{campaign_type}"),
            output_dir=output_dir,
        )
        if record:
            records.append(record)

    records = filter_approval_ledger(records, approval_view)
    summary = _summary(records)
    next_review = _next_review(records)
    approval_by_key = {str(item.get("approval_id") or ""): item for item in records}
    queue = _queue_approval(queue, approval_by_key)
    ordered = sorted(
        records,
        key=lambda item: (
            APPROVAL_STATE_PRIORITY.get(str(item.get("approval_state") or "not-applicable"), 99),
            str(item.get("label") or ""),
        ),
    )
    return {
        "approval_ledger": ordered,
        "approval_workflow_summary": summary,
        "next_approval_review": next_review,
        "top_ready_for_review_approvals": [item for item in ordered if item.get("approval_state") == "ready-for-review"][:5],
        "top_needs_reapproval_approvals": [item for item in ordered if item.get("approval_state") == "needs-reapproval"][:5],
        "top_approved_manual_approvals": [item for item in ordered if item.get("approval_state") == "approved-manual"][:5],
        "top_blocked_approvals": [item for item in ordered if item.get("approval_state") == "blocked"][:5],
        "operator_queue": queue,
    }
