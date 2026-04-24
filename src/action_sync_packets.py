from __future__ import annotations

from typing import Any

from src.action_sync_readiness import (
    CAMPAIGN_DISPLAY_ORDER,
    QUEUE_CAMPAIGN_PRIORITY,
    _github_projects_ready,
    _github_ready,
    _governance_ready,
    _infer_campaign,
    _notion_ready,
)
from src.ops_writeback import build_campaign_bundle

EXECUTION_PRIORITY = {
    "review-drift": 0,
    "needs-approval": 1,
    "ready-to-apply": 2,
    "preview-next": 3,
    "stay-local": 4,
}


def _campaign_actions(report_data: dict[str, Any], campaign_type: str) -> list[dict[str, Any]]:
    _summary, actions = build_campaign_bundle(
        report_data,
        campaign_type=campaign_type,
        portfolio_profile=report_data.get("selected_portfolio_profile", "default"),
        collection_name=report_data.get("selected_collection"),
        max_actions=20,
        writeback_target=None,
    )
    return actions


def _automation_eligible_repo_names(report_data: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for audit in report_data.get("audits", []) or []:
        catalog = audit.get("portfolio_catalog") or {}
        if not catalog.get("automation_eligible"):
            continue
        repo_name = str(
            catalog.get("repo")
            or audit.get("metadata", {}).get("name")
            or ""
        ).strip()
        if repo_name:
            names.add(repo_name)
    return names


def _automation_subset(
    report_data: dict[str, Any],
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    eligible_repos = _automation_eligible_repo_names(report_data)
    eligible_action_repos = sorted(
        {
            str(action.get("repo") or "")
            for action in actions
            if str(action.get("repo") or "") in eligible_repos
        }
    )
    eligible_action_count = sum(
        1 for action in actions if str(action.get("repo") or "") in eligible_repos
    )
    return {
        "automation_eligible_repos": sorted(eligible_repos),
        "automation_eligible_repo_count": len(eligible_repos),
        "automation_eligible_action_repos": eligible_action_repos,
        "automation_eligible_action_repo_count": len(eligible_action_repos),
        "automation_eligible_action_count": eligible_action_count,
        "non_eligible_action_count": max(0, len(actions) - eligible_action_count),
    }


def _github_projects_enabled_and_healthy(report_data: dict[str, Any]) -> bool:
    github_projects = ((report_data.get("writeback_preview") or {}).get("github_projects") or {})
    return bool(github_projects.get("enabled")) and _github_projects_ready(report_data)


def _command_prefix(report_data: dict[str, Any], campaign_type: str, target: str, sync_mode: str) -> str:
    username = str(report_data.get("username") or "<github-username>")
    command = f"audit {username} --campaign {campaign_type}"
    if target and target != "none":
        command += f" --writeback-target {target}"
    if sync_mode and sync_mode != "reconcile":
        command += f" --campaign-sync-mode {sync_mode}"
    if target in {"github", "all"} and _github_projects_enabled_and_healthy(report_data):
        command += " --github-projects"
    return command


def _rollback_status(report_data: dict[str, Any], campaign_type: str, actions: list[dict[str, Any]]) -> str:
    if not actions:
        return "not-applicable"

    rollback_preview = report_data.get("rollback_preview") or {}
    items = list(rollback_preview.get("items") or [])
    action_ids = {str(action.get("action_id") or "") for action in actions}
    matching = [item for item in items if str(item.get("action_id") or "") in action_ids]
    if not matching:
        active_campaign = campaign_type == str((report_data.get("campaign_summary") or {}).get("campaign_type") or "")
        mode = str((report_data.get("writeback_results") or {}).get("mode") or "")
        if active_campaign and mode == "apply":
            return "missing"
        return "not-applicable"

    states = {str(item.get("rollback_state") or "") for item in matching}
    if states == {"fully-reversible"}:
        return "ready"
    if "fully-reversible" in states or "partial" in states:
        return "partial"
    return "missing"


def _blockers(
    report_data: dict[str, Any],
    record: dict[str, Any],
    rollback_status: str,
) -> tuple[list[str], list[str], list[str]]:
    blocker_types: list[str] = []
    blockers: list[str] = []
    approvals_required: list[str] = []
    campaign_type = str(record.get("campaign_type") or "")
    recommended_target = str(record.get("recommended_target") or "none")
    action_count = int(record.get("action_count", 0) or 0)

    if action_count <= 0:
        blocker_types.append("no-actions")
        blockers.append("No meaningful actions are currently staged for this campaign.")

    if str(record.get("readiness_stage") or "") == "drift-review":
        blocker_types.append("managed-drift")
        blockers.append(str(record.get("reason") or "Managed drift needs review before any further sync."))

    if action_count > 0 and recommended_target == "none":
        if not _github_ready(report_data):
            blocker_types.append("github-access")
            blockers.append("GitHub writeback prerequisites are not healthy yet.")
        if not _notion_ready(report_data):
            blocker_types.append("notion-access")
            blockers.append("Notion writeback prerequisites are not healthy yet.")

    if action_count > 0 and campaign_type == "security-review" and not _governance_ready(report_data, campaign_type):
        blocker_types.append("governance-approval")
        blockers.append("Governed security controls still need approval or re-approval before apply.")
        approvals_required.append("governance")

    if action_count > 0 and recommended_target in {"github", "all"} and not _github_projects_ready(report_data):
        github_projects = ((report_data.get("writeback_preview") or {}).get("github_projects") or {})
        if github_projects.get("enabled"):
            blocker_types.append("github-projects")
            blockers.append("GitHub Projects mirroring is enabled but not healthy yet.")

    if action_count > 0 and rollback_status in {"partial", "missing"}:
        blocker_types.append("rollback-coverage")
        if rollback_status == "partial":
            blockers.append("Rollback coverage is only partial for the current managed action path.")
        else:
            blockers.append("Rollback coverage is missing for the current managed action path.")

    deduped_types = list(dict.fromkeys(blocker_types))
    deduped_blockers = list(dict.fromkeys(blockers))
    deduped_approvals = list(dict.fromkeys(approvals_required))
    return deduped_types, deduped_blockers, deduped_approvals


def _execution_state(record: dict[str, Any], blocker_types: list[str]) -> str:
    readiness_stage = str(record.get("readiness_stage") or "idle")
    blocker_set = set(blocker_types)
    if readiness_stage == "drift-review":
        return "review-drift"
    if blocker_set and blocker_set.issubset({"governance-approval", "rollback-coverage"}):
        return "needs-approval"
    if readiness_stage == "apply-ready" and not blocker_set:
        return "ready-to-apply"
    if readiness_stage == "preview-ready":
        return "preview-next"
    return "stay-local"


def _packet_summary(packet: dict[str, Any]) -> str:
    label = str(packet.get("label") or packet.get("campaign_type") or "Campaign")
    target = str(packet.get("recommended_target") or "none")
    execution_state = str(packet.get("execution_state") or "stay-local")
    blockers = list(packet.get("blockers") or [])

    if execution_state == "review-drift":
        return f"{label} should stop at drift review before any further sync to {target}."
    if execution_state == "needs-approval":
        reason = blockers[0] if blockers else "Approval or rollback review is still needed."
        return f"{label} still needs approval or rollback review before apply to {target}. {reason}"
    if execution_state == "ready-to-apply":
        return f"{label} is ready to apply to {target} when you are."
    if execution_state == "preview-next":
        return f"{label} is the best campaign to preview next before deciding on apply to {target}."
    return f"{label} should stay local for now."


def _packet_sort_key(packet: dict[str, Any]) -> tuple[int, int, str]:
    return (
        EXECUTION_PRIORITY.get(str(packet.get("execution_state") or "stay-local"), 99),
        -int(packet.get("action_count", 0) or 0),
        str(packet.get("campaign_type") or ""),
    )


def _next_candidate_summary(packet: dict[str, Any]) -> str:
    label = str(packet.get("label") or packet.get("campaign_type") or "Campaign")
    target = str(packet.get("recommended_target") or "none")
    execution_state = str(packet.get("execution_state") or "stay-local")
    if execution_state == "review-drift":
        return f"Review managed drift in {label} before any further Action Sync to {target}."
    if execution_state == "needs-approval":
        return f"{label} needs approval or rollback review before it is safe to apply to {target}."
    if execution_state == "ready-to-apply":
        return f"{label} is ready to apply to {target}; use the apply packet when you are comfortable."
    if execution_state == "preview-next":
        return f"Preview {label} next, then decide whether it is ready to apply to {target}."
    return "Stay local for now; no current campaign has a safe execution handoff."


def _summary_line(packets: list[dict[str, Any]]) -> str:
    actionable = [packet for packet in packets if packet.get("execution_state") != "stay-local"]
    if not actionable:
        return "No current campaign has a safe execution handoff yet, so the local weekly story should stay local for now."
    packet = sorted(actionable, key=_packet_sort_key)[0]
    label = str(packet.get("label") or packet.get("campaign_type") or "Campaign")
    execution_state = str(packet.get("execution_state") or "stay-local")
    target = str(packet.get("recommended_target") or "none")
    if execution_state == "review-drift":
        return f"Apply handoff says drift review comes first: {label} needs managed mirror review before any further sync to {target}."
    if execution_state == "needs-approval":
        return f"Apply handoff says {label} still needs approval or rollback review before apply to {target}."
    if execution_state == "ready-to-apply":
        return f"Apply handoff says {label} is ready to apply to {target} when you are."
    return f"Apply handoff says preview {label} next before deciding on apply to {target}."


def _queue_apply_packets(
    queue: list[dict[str, Any]],
    report_data: dict[str, Any],
    packets_by_campaign: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    repo_to_campaign: dict[str, str] = {}
    for campaign_type in QUEUE_CAMPAIGN_PRIORITY:
        packet = packets_by_campaign.get(campaign_type) or {}
        for repo in packet.get("top_repos") or []:
            if repo and repo not in repo_to_campaign:
                repo_to_campaign[str(repo)] = campaign_type

    for item in queue:
        mapped = dict(item)
        repo_name = str(mapped.get("repo") or mapped.get("repo_name") or "").strip()
        campaign_type = str(mapped.get("suggested_campaign") or repo_to_campaign.get(repo_name) or _infer_campaign(repo_name, mapped, report_data))
        packet = packets_by_campaign.get(campaign_type, {})
        execution_state = str(packet.get("execution_state") or "stay-local")
        mapped["apply_packet_state"] = execution_state
        mapped["apply_packet_summary"] = str(packet.get("summary") or "No current apply packet is surfaced for this item.")
        if execution_state == "ready-to-apply":
            mapped["apply_packet_command"] = str(packet.get("apply_command") or "")
        elif execution_state == "preview-next":
            mapped["apply_packet_command"] = str(packet.get("preview_command") or "")
        else:
            mapped["apply_packet_command"] = ""
        enriched.append(mapped)
    return enriched


def build_action_sync_packets_bundle(
    report_data: dict[str, Any],
    readiness_bundle: dict[str, Any],
    queue: list[dict[str, Any]],
) -> dict[str, Any]:
    readiness_by_campaign = {
        str(record.get("campaign_type") or ""): record
        for record in ((readiness_bundle.get("campaign_readiness_summary") or {}).get("campaigns") or [])
    }

    packets: list[dict[str, Any]] = []
    packets_by_campaign: dict[str, dict[str, Any]] = {}
    for campaign_type in CAMPAIGN_DISPLAY_ORDER:
        readiness_record = dict(readiness_by_campaign.get(campaign_type) or {})
        actions = _campaign_actions(report_data, campaign_type)
        rollback_status = _rollback_status(report_data, campaign_type, actions)
        blocker_types, blockers, approvals_required = _blockers(report_data, readiness_record, rollback_status)
        execution_state = _execution_state(readiness_record, blocker_types)
        recommended_target = str(readiness_record.get("recommended_target") or "none")
        sync_mode = str(readiness_record.get("sync_mode") or "reconcile")
        preview_command = ""
        if readiness_record.get("action_count", 0):
            preview_command = _command_prefix(report_data, campaign_type, recommended_target, sync_mode)
        apply_command = ""
        if execution_state == "ready-to-apply" and recommended_target != "none":
            apply_command = f"{_command_prefix(report_data, campaign_type, recommended_target, sync_mode)} --writeback-apply"

        packet = {
            "campaign_type": campaign_type,
            "label": str(readiness_record.get("label") or campaign_type.replace("-", " ").title()),
            "readiness_stage": str(readiness_record.get("readiness_stage") or "idle"),
            "execution_state": execution_state,
            "recommended_target": recommended_target,
            "sync_mode": sync_mode,
            "action_count": int(readiness_record.get("action_count", 0) or 0),
            "repo_count": int(readiness_record.get("repo_count", 0) or 0),
            "blocker_types": blocker_types,
            "blockers": blockers,
            "approvals_required": approvals_required,
            "rollback_status": rollback_status,
            "preview_command": preview_command,
            "apply_command": apply_command,
            "top_repos": list(readiness_record.get("top_repos") or []),
            "automation_subset": _automation_subset(report_data, actions),
        }
        packet["summary"] = _packet_summary(packet)
        packets.append(packet)
        packets_by_campaign[campaign_type] = packet

    actionable = [packet for packet in packets if packet.get("execution_state") != "stay-local"]
    next_candidate = sorted(actionable, key=_packet_sort_key)[0] if actionable else {}
    top_ready = [packet for packet in sorted(packets, key=_packet_sort_key) if packet.get("execution_state") == "ready-to-apply"][:3]
    top_needs_approval = [packet for packet in sorted(packets, key=_packet_sort_key) if packet.get("execution_state") == "needs-approval"][:3]
    top_review_drift = [packet for packet in sorted(packets, key=_packet_sort_key) if packet.get("execution_state") == "review-drift"][:3]

    return {
        "action_sync_packets": packets,
        "apply_readiness_summary": {
            "summary": _summary_line(packets),
            "counts": {
                state: sum(1 for packet in packets if packet.get("execution_state") == state)
                for state in ("stay-local", "preview-next", "review-drift", "needs-approval", "ready-to-apply")
            },
        },
        "next_apply_candidate": next_candidate,
        "top_ready_to_apply_packets": top_ready,
        "top_needs_approval_packets": top_needs_approval,
        "top_review_drift_packets": top_review_drift,
        "next_apply_candidate_line": _next_candidate_summary(next_candidate) if next_candidate else "Stay local for now; no current campaign has a safe execution handoff.",
        "operator_queue": _queue_apply_packets(queue, report_data, packets_by_campaign),
    }
