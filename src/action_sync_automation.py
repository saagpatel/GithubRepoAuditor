from __future__ import annotations

from typing import Any

from src.action_sync_packets import EXECUTION_PRIORITY
from src.action_sync_readiness import CAMPAIGN_DISPLAY_ORDER, READINESS_PRIORITY
from src.terminology import ACTION_SYNC_CANONICAL_LABELS

AUTOMATION_PRIORITY = {
    "approval-first": 0,
    "manual-only": 1,
    "preview-safe": 2,
    "apply-manual": 3,
    "follow-up-safe": 4,
    "quiet-safe": 5,
}

MANUAL_MONITORING_STATES = frozenset({"drift-returned", "reopened", "rollback-watch"})
FOLLOW_UP_MONITORING_STATES = frozenset({"monitor-now", "holding-clean"})
HISTORICAL_MANUAL_STATUSES = frozenset({"relapsing", "persistent-pressure"})
HISTORICAL_QUIET_STATUSES = frozenset({"quiet", "holding-steady"})
FOLLOW_UP_COMMAND_SUFFIX = " --control-center"


def _copy_mapping(value: Any) -> dict[str, Any]:
    return dict(value or {})


def _username(report_data: dict[str, Any]) -> str:
    return str(report_data.get("username") or "<github-username>")


def _campaign_order(campaign_type: str) -> int:
    try:
        return CAMPAIGN_DISPLAY_ORDER.index(campaign_type)
    except ValueError:
        return len(CAMPAIGN_DISPLAY_ORDER)


def _historical_statuses(
    queue: list[dict[str, Any]],
    intervention_bundle: dict[str, Any],
) -> dict[str, set[str]]:
    statuses: dict[str, set[str]] = {campaign_type: set() for campaign_type in CAMPAIGN_DISPLAY_ORDER}
    for item in queue:
        campaign_type = str(item.get("suggested_campaign") or "").strip()
        status = str(item.get("historical_intelligence_status") or "").strip()
        if campaign_type and status:
            statuses.setdefault(campaign_type, set()).add(status)
    for bucket_key, status in (
        ("top_relapsing_repos", "relapsing"),
        ("top_persistent_pressure_repos", "persistent-pressure"),
        ("top_improving_repos", "improving-after-intervention"),
        ("top_holding_repos", "holding-steady"),
    ):
        for item in intervention_bundle.get(bucket_key) or []:
            campaign_type = str(item.get("suggested_campaign") or "").strip()
            if campaign_type:
                statuses.setdefault(campaign_type, set()).add(status)
    return statuses


def _follow_up_command(report_data: dict[str, Any]) -> str:
    return f"audit {_username(report_data)}{FOLLOW_UP_COMMAND_SUFFIX}"


def _review_required(
    posture: str,
    packet: dict[str, Any],
    monitoring: dict[str, Any],
    historical_statuses: set[str],
) -> bool:
    if posture in {"manual-only", "approval-first", "apply-manual"}:
        return True
    if str(monitoring.get("monitoring_state") or "") in MANUAL_MONITORING_STATES:
        return True
    if historical_statuses & HISTORICAL_MANUAL_STATUSES:
        return True
    return bool(packet.get("approvals_required"))


def _recommended_follow_up(
    posture: str,
    label: str,
    packet: dict[str, Any],
    monitoring: dict[str, Any],
) -> str:
    monitoring_state = str(monitoring.get("monitoring_state") or "")
    if posture == "approval-first":
        return f"Review approval prerequisites for {label} before any execution step."
    if posture == "manual-only":
        if monitoring_state == "drift-returned":
            return f"Review managed drift in {label} before any further sync."
        if monitoring_state == "reopened":
            return f"Review reopened follow-through in {label} before any further sync."
        if monitoring_state == "rollback-watch":
            return f"Review rollback coverage and aftermath in {label} before any further sync."
        return f"Keep {label} manual-only until the human review path is clear."
    if posture == "preview-safe":
        return f"Use the preview command for {label}, then review the refreshed artifact before any apply decision."
    if posture == "apply-manual":
        return f"Apply remains a manual decision for {label}; review the checklist and run it yourself if you are comfortable."
    if posture == "follow-up-safe":
        return f"Use a non-mutating follow-up for {label}, then review the refreshed workbook or control center."
    return f"Keep {label} quiet unless a future run surfaces stronger pressure."


def _recommended_command(
    posture: str,
    packet: dict[str, Any],
    report_data: dict[str, Any],
) -> str:
    if posture == "preview-safe":
        return str(packet.get("preview_command") or "")
    if posture == "apply-manual":
        command = str(packet.get("apply_command") or "")
        return f"Manual apply only: {command}" if command else ""
    if posture == "follow-up-safe":
        return _follow_up_command(report_data)
    return ""


def _automation_reason(
    posture: str,
    packet: dict[str, Any],
    monitoring: dict[str, Any],
    historical_statuses: set[str],
) -> str:
    execution_state = str(packet.get("execution_state") or "stay-local")
    monitoring_state = str(monitoring.get("monitoring_state") or "no-recent-apply")
    if posture == "approval-first":
        return "Approval review is the only remaining blocker before any execution step."
    if posture == "manual-only":
        if historical_statuses & HISTORICAL_MANUAL_STATUSES:
            return "Cross-run repo history still shows relapse or persistent pressure."
        if monitoring_state in MANUAL_MONITORING_STATES:
            return "Recent post-apply monitoring still needs human review."
        if execution_state == "review-drift":
            return "Managed drift still needs review before any further sync."
        return "Human judgment still outranks automation convenience here."
    if posture == "preview-safe":
        return "Preview is the strongest safe next step and does not widen write authority."
    if posture == "apply-manual":
        return "Apply is ready, but it must stay an explicit human action."
    if posture == "follow-up-safe":
        return "Only non-mutating follow-up is appropriate right now."
    return "The portfolio is quiet enough that only housekeeping or quiet-state automation is appropriate."


def _summary(
    label: str,
    posture: str,
    reason: str,
    command: str,
    follow_up: str,
) -> str:
    if posture == "approval-first":
        return f"{label} is approval-first: review the approval path before any command is surfaced. {reason}"
    if posture == "manual-only":
        return f"{label} is manual-only: keep investigation human-led for now. {reason}"
    if posture == "preview-safe":
        command_text = f" Safe preview command: {command}." if command else ""
        return f"{label} is preview-safe: use a preview-only step first.{command_text}"
    if posture == "apply-manual":
        command_text = f" Human-run command: {command}." if command else ""
        return f"{label} is apply-manual: the apply path is available, but it stays human-only.{command_text}"
    if posture == "follow-up-safe":
        command_text = f" Safe follow-up command: {command}." if command else ""
        return f"{label} is follow-up-safe: use a non-mutating refresh or control-center pass next.{command_text}"
    return f"{label} is quiet-safe: {follow_up}"


def _posture(
    packet: dict[str, Any],
    monitoring: dict[str, Any],
    historical_statuses: set[str],
) -> str:
    execution_state = str(packet.get("execution_state") or "stay-local")
    monitoring_state = str(monitoring.get("monitoring_state") or "no-recent-apply")
    blocker_types = set(packet.get("blocker_types") or [])

    if historical_statuses & HISTORICAL_MANUAL_STATUSES:
        return "manual-only"
    if monitoring_state in MANUAL_MONITORING_STATES:
        return "manual-only"
    if execution_state == "review-drift":
        return "manual-only"
    if execution_state == "needs-approval" and blocker_types and blocker_types.issubset({"governance-approval"}):
        return "approval-first"
    if execution_state == "needs-approval":
        return "manual-only"
    if execution_state == "preview-next":
        return "preview-safe"
    if execution_state == "ready-to-apply":
        return "apply-manual"
    if monitoring_state in FOLLOW_UP_MONITORING_STATES:
        return "follow-up-safe"
    if historical_statuses and historical_statuses.issubset(HISTORICAL_QUIET_STATUSES | {"improving-after-intervention"}):
        return "quiet-safe"
    return "quiet-safe"


def _sort_key(record: dict[str, Any]) -> tuple[int, int, int, int, int]:
    return (
        AUTOMATION_PRIORITY.get(str(record.get("automation_posture") or "quiet-safe"), 99),
        READINESS_PRIORITY.get(str(record.get("readiness_stage") or "idle"), 99),
        EXECUTION_PRIORITY.get(str(record.get("execution_state") or "stay-local"), 99),
        -int(record.get("action_count", 0) or 0),
        _campaign_order(str(record.get("campaign_type") or "")),
    )


def _next_safe_summary(record: dict[str, Any]) -> str:
    label = str(record.get("label") or record.get("campaign_type") or "Campaign")
    posture = str(record.get("automation_posture") or "quiet-safe")
    if posture == "approval-first":
        return f"Review approvals for {label} first; no execution command should run before that review is complete."
    if posture == "manual-only":
        return f"Keep {label} manual-only for now; human review is stronger than automation convenience here."
    if posture == "preview-safe":
        return f"Preview {label} next; that is the strongest safe automation step right now."
    if posture == "apply-manual":
        return f"{label} is ready, but apply still stays human-only."
    if posture == "follow-up-safe":
        return f"Use a non-mutating follow-up for {label} next."
    return f"Keep {label} quiet unless a later run surfaces stronger pressure."


def _guidance_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {
            "summary": "Automation guidance is quiet because no current campaign needs a bounded execution suggestion yet.",
            "counts": {posture: 0 for posture in AUTOMATION_PRIORITY},
        }
    ordered = sorted(records, key=_sort_key)
    top = ordered[0]
    counts = {
        posture: sum(1 for item in records if item.get("automation_posture") == posture)
        for posture in AUTOMATION_PRIORITY
    }
    return {
        "summary": _next_safe_summary(top),
        "counts": counts,
    }


def _queue_automation(
    queue: list[dict[str, Any]],
    automation_by_campaign: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for item in queue:
        mapped = dict(item)
        campaign_type = str(mapped.get("suggested_campaign") or "").strip()
        automation = automation_by_campaign.get(campaign_type, {})
        mapped["automation_posture"] = str(automation.get("automation_posture") or "manual-only")
        mapped["automation_summary"] = str(
            automation.get("summary") or "Automation Guidance: keep this item human-led for now."
        )
        mapped["automation_command"] = str(automation.get("recommended_command") or "")
        mapped["automation_line"] = (
            f"{ACTION_SYNC_CANONICAL_LABELS['automation_guidance']}: {mapped['automation_summary']}"
        )
        enriched.append(mapped)
    return enriched


def build_action_sync_automation_bundle(
    report_data: dict[str, Any],
    readiness_bundle: dict[str, Any],
    packets_bundle: dict[str, Any],
    outcomes_bundle: dict[str, Any],
    tuning_bundle: dict[str, Any],
    intervention_bundle: dict[str, Any],
    queue: list[dict[str, Any]],
) -> dict[str, Any]:
    readiness_by_campaign = {
        str(item.get("campaign_type") or ""): dict(item)
        for item in ((readiness_bundle.get("campaign_readiness_summary") or {}).get("campaigns") or [])
    }
    packets_by_campaign = {
        str(item.get("campaign_type") or ""): dict(item)
        for item in (packets_bundle.get("action_sync_packets") or [])
    }
    outcomes_by_campaign = {
        str(item.get("campaign_type") or ""): dict(item)
        for item in (outcomes_bundle.get("action_sync_outcomes") or [])
    }
    tuning_by_campaign = {
        str(item.get("campaign_type") or ""): dict(item)
        for item in (tuning_bundle.get("action_sync_tuning") or [])
    }
    historical_statuses = _historical_statuses(queue, intervention_bundle)

    records: list[dict[str, Any]] = []
    for campaign_type in CAMPAIGN_DISPLAY_ORDER:
        readiness = readiness_by_campaign.get(campaign_type, {})
        packet = packets_by_campaign.get(campaign_type, {})
        monitoring = outcomes_by_campaign.get(campaign_type, {})
        tuning = tuning_by_campaign.get(campaign_type, {})
        history = historical_statuses.get(campaign_type, set())
        label = str(
            packet.get("label")
            or readiness.get("label")
            or monitoring.get("label")
            or tuning.get("label")
            or campaign_type
        )
        posture = _posture(packet, monitoring, history)
        reason = _automation_reason(posture, packet, monitoring, history)
        command = _recommended_command(posture, packet, report_data)
        follow_up = _recommended_follow_up(posture, label, packet, monitoring)
        record = {
            "campaign_type": campaign_type,
            "label": label,
            "readiness_stage": str(readiness.get("readiness_stage") or "idle"),
            "execution_state": str(packet.get("execution_state") or "stay-local"),
            "monitoring_state": str(monitoring.get("monitoring_state") or "no-recent-apply"),
            "automation_posture": posture,
            "automation_reason": reason,
            "review_required": _review_required(posture, packet, monitoring, history),
            "recommended_command": command,
            "recommended_follow_up": follow_up,
            "requires_approval": bool(packet.get("approvals_required")),
            "action_count": int(packet.get("action_count", readiness.get("action_count", 0)) or 0),
            "summary": _summary(label, posture, reason, command, follow_up),
        }
        records.append(record)

    ordered = sorted(records, key=_sort_key)
    next_safe = dict(ordered[0]) if ordered else {}
    if next_safe:
        next_safe["summary"] = _next_safe_summary(next_safe)

    automation_by_campaign = {
        str(item.get("campaign_type") or ""): item
        for item in records
    }
    return {
        "action_sync_automation": records,
        "automation_guidance_summary": _guidance_summary(records),
        "next_safe_automation_step": next_safe,
        "top_preview_safe_campaigns": [item for item in ordered if item.get("automation_posture") == "preview-safe"][:3],
        "top_apply_manual_campaigns": [item for item in ordered if item.get("automation_posture") == "apply-manual"][:3],
        "top_approval_first_campaigns": [item for item in ordered if item.get("automation_posture") == "approval-first"][:3],
        "top_follow_up_safe_campaigns": [item for item in ordered if item.get("automation_posture") == "follow-up-safe"][:3],
        "top_manual_only_campaigns": [item for item in ordered if item.get("automation_posture") == "manual-only"][:3],
        "operator_queue": _queue_automation(queue, automation_by_campaign),
    }
