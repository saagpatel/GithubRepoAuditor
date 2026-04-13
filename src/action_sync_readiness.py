from __future__ import annotations

from typing import Any

from src.ops_writeback import CAMPAIGN_DEFINITIONS, build_campaign_bundle

CAMPAIGN_DISPLAY_ORDER = [
    "security-review",
    "promotion-push",
    "archive-sweep",
    "showcase-publish",
    "maintenance-cleanup",
]

READINESS_PRIORITY = {
    "drift-review": 0,
    "blocked": 1,
    "apply-ready": 2,
    "preview-ready": 3,
    "idle": 4,
}

QUEUE_CAMPAIGN_PRIORITY = [
    "security-review",
    "maintenance-cleanup",
    "promotion-push",
    "archive-sweep",
    "showcase-publish",
]


def _preflight_checks(report_data: dict[str, Any]) -> list[dict[str, Any]]:
    return list((report_data.get("preflight_summary") or {}).get("checks") or [])


def _has_blocking_check(report_data: dict[str, Any], keywords: tuple[str, ...]) -> bool:
    for check in _preflight_checks(report_data):
        status = str(check.get("status") or check.get("severity") or "").lower()
        if status != "error":
            continue
        haystack = " ".join(
            str(check.get(key) or "").lower()
            for key in ("key", "category", "summary", "details")
        )
        if any(keyword in haystack for keyword in keywords):
            return True
    return False


def _github_ready(report_data: dict[str, Any]) -> bool:
    return not _has_blocking_check(report_data, ("github", "writeback"))


def _notion_ready(report_data: dict[str, Any]) -> bool:
    return not _has_blocking_check(report_data, ("notion",))


def _github_projects_ready(report_data: dict[str, Any]) -> bool:
    github_projects = (
        (report_data.get("writeback_preview") or {}).get("github_projects") or {}
    )
    if not github_projects.get("enabled"):
        return True
    return str(github_projects.get("status") or "").strip().lower() in {
        "configured",
        "preview-ready",
        "mirrored",
        "applied",
    }


def _governance_ready(report_data: dict[str, Any], campaign_type: str) -> bool:
    if campaign_type != "security-review":
        return True
    governance_summary = report_data.get("governance_summary") or {}
    if governance_summary.get("needs_reapproval"):
        return False
    if report_data.get("governance_drift"):
        return False
    preview_actions = list((report_data.get("governance_preview") or {}).get("actions") or [])
    if preview_actions and not report_data.get("governance_approval"):
        return False
    return True


def _recommended_target(report_data: dict[str, Any]) -> str:
    github_ready = _github_ready(report_data)
    notion_ready = _notion_ready(report_data)
    if github_ready and notion_ready:
        return "all"
    if github_ready:
        return "github"
    if notion_ready:
        return "notion"
    return "none"


def _campaign_drift_items(report_data: dict[str, Any], campaign_type: str) -> list[dict[str, Any]]:
    active_campaign = str((report_data.get("campaign_summary") or {}).get("campaign_type") or "")
    drift_rows = []
    for item in report_data.get("managed_state_drift") or []:
        item_campaign = str(item.get("campaign_type") or "").strip()
        if item_campaign == campaign_type:
            drift_rows.append(item)
            continue
        if campaign_type == active_campaign and not item_campaign:
            drift_rows.append(item)
    if campaign_type == "security-review":
        for item in report_data.get("governance_drift") or []:
            drift_rows.append(
                {
                    "repo_full_name": item.get("repo_full_name") or item.get("repo") or "",
                    "target": "governance",
                    "drift_state": item.get("drift_type", "governance-drift"),
                }
            )
    return drift_rows


def _top_repos(actions: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for action in actions:
        repo = str(action.get("repo") or action.get("repo_full_name") or "").strip()
        if repo and repo not in seen:
            seen.append(repo)
        if len(seen) == 3:
            break
    return seen


def _blocking_reason(report_data: dict[str, Any], campaign_type: str, recommended_target: str) -> str:
    if recommended_target == "none":
        return "Writeback prerequisites are missing, so this campaign should stay local until target access is healthy."
    if campaign_type == "security-review" and not _governance_ready(report_data, campaign_type):
        return "Governed security controls still need approval or drift review before this campaign should sync outward."
    if recommended_target in {"github", "all"} and not _github_projects_ready(report_data):
        return "GitHub Projects mirror is enabled but not healthy yet, so the managed mirror should be reviewed before syncing."
    return ""


def _stage_reason(
    *,
    stage: str,
    label: str,
    recommended_target: str,
    drift_rows: list[dict[str, Any]],
    action_count: int,
) -> str:
    if stage == "idle":
        return f"No meaningful {label.lower()} actions are currently surfaced, so this campaign can stay local for now."
    if stage == "drift-review":
        repo = str((drift_rows[0] or {}).get("repo_full_name") or (drift_rows[0] or {}).get("repo") or "").strip()
        if repo:
            return f"Managed drift is active for {repo}, so {label} should be reviewed before any further sync."
        return f"Managed drift is active for {label}, so it should be reviewed before any further sync."
    if stage == "blocked":
        return ""
    if stage == "apply-ready":
        target = recommended_target if recommended_target != "none" else "managed targets"
        return f"{action_count} action(s) are already staged locally and {label} is healthy enough to apply to {target} if you choose."
    return f"{action_count} action(s) are ready for preview, but {label} should stay preview-first until you explicitly choose to sync it outward."


def _readiness_record(report_data: dict[str, Any], campaign_type: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    summary, actions = build_campaign_bundle(
        report_data,
        campaign_type=campaign_type,
        portfolio_profile=report_data.get("selected_portfolio_profile", "default"),
        collection_name=report_data.get("selected_collection"),
        max_actions=20,
        writeback_target=None,
    )
    drift_rows = _campaign_drift_items(report_data, campaign_type)
    actions_exist = bool(summary.get("action_count", 0))
    recommended_target = _recommended_target(report_data)
    blocking_reason = _blocking_reason(report_data, campaign_type, recommended_target) if actions_exist else ""
    active_campaign = campaign_type == str((report_data.get("campaign_summary") or {}).get("campaign_type") or "")

    if drift_rows:
        stage = "drift-review"
    elif actions_exist and blocking_reason:
        stage = "blocked"
    elif actions_exist and active_campaign:
        stage = "apply-ready"
    elif actions_exist:
        stage = "preview-ready"
    else:
        stage = "idle"

    record = {
        "campaign_type": campaign_type,
        "label": summary.get("label", CAMPAIGN_DEFINITIONS[campaign_type]["label"]),
        "action_count": int(summary.get("action_count", 0) or 0),
        "repo_count": int(summary.get("repo_count", 0) or 0),
        "readiness_stage": stage,
        "reason": blocking_reason
        if stage == "blocked"
        else _stage_reason(
            stage=stage,
            label=summary.get("label", CAMPAIGN_DEFINITIONS[campaign_type]["label"]),
            recommended_target=recommended_target,
            drift_rows=drift_rows,
            action_count=int(summary.get("action_count", 0) or 0),
        ),
        "recommended_target": recommended_target,
        "top_repos": _top_repos(actions),
        "sync_mode": str((report_data.get("writeback_preview") or {}).get("sync_mode") or "reconcile"),
    }
    return record, actions


def _campaign_sort_key(record: dict[str, Any]) -> tuple[int, int, str]:
    return (
        READINESS_PRIORITY.get(str(record.get("readiness_stage") or "idle"), 99),
        -int(record.get("action_count", 0) or 0),
        str(record.get("campaign_type") or ""),
    )


def _next_step(records: list[dict[str, Any]]) -> str:
    if not records:
        return "Stay local for now; no current campaign needs preview or apply."
    record = sorted(records, key=_campaign_sort_key)[0]
    label = record.get("label", record.get("campaign_type", "Campaign"))
    target = record.get("recommended_target", "none")
    stage = record.get("readiness_stage", "idle")
    if stage == "drift-review":
        return f"Review managed drift in {label} before any further Action Sync."
    if stage == "blocked":
        return f"Unblock {label} first, then preview it again before syncing outward."
    if stage == "apply-ready":
        return f"{label} is ready to apply to {target}; preview once more if needed, then sync it outward when you are comfortable."
    if stage == "preview-ready":
        return f"Preview {label} next, then decide whether it is ready to sync to {target}."
    return "Stay local for now; no current campaign needs preview or apply."


def _summary_line(records: list[dict[str, Any]]) -> str:
    if not records:
        return "No current campaign is ready for preview or apply, so weekly review can stay local for now."
    record = sorted(records, key=_campaign_sort_key)[0]
    label = record.get("label", record.get("campaign_type", "Campaign"))
    stage = record.get("readiness_stage", "idle")
    if stage == "drift-review":
        return f"Action Sync should pause on drift review first: {label} has managed mirror drift that needs human review."
    if stage == "blocked":
        return f"Action Sync is blocked right now: {label} has local actions, but prerequisites or approvals still need attention."
    if stage == "apply-ready":
        return f"Action Sync is ready when you are: {label} can move from local review to managed apply without blocking drift."
    if stage == "preview-ready":
        return f"Action Sync is preview-ready: {label} is the strongest next campaign to preview from the current local facts."
    return "No current campaign is worth syncing yet, so the safest next move is to keep the story local."


def _repo_catalog(report_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    audits = report_data.get("audits") or []
    return {
        str((audit.get("metadata") or {}).get("name") or ""): audit for audit in audits
    }


def _infer_campaign(repo_name: str, queue_item: dict[str, Any], report_data: dict[str, Any]) -> str:
    audits = _repo_catalog(report_data)
    audit = audits.get(repo_name, {})
    catalog = audit.get("portfolio_catalog") or {}
    collections = set(audit.get("collections") or [])
    if queue_item.get("kind") == "governance":
        return "security-review"
    lower_blob = " ".join(
        str(queue_item.get(key) or "").lower()
        for key in ("kind", "title", "summary", "recommended_action", "lane_reason")
    )
    if any(term in lower_blob for term in ("security", "governance", "secret", "dependency vulnerability")):
        return "security-review"
    if str(catalog.get("intended_disposition") or "").strip() == "archive" or "archive" in lower_blob:
        return "archive-sweep"
    if "showcase" in collections:
        return "showcase-publish"
    if str(queue_item.get("operator_focus") or "").strip() in {"fragile", "revalidate"}:
        return "maintenance-cleanup"
    if "hotspot" in lower_blob or "cleanup" in lower_blob or "maintenance" in lower_blob:
        return "maintenance-cleanup"
    return "promotion-push"


def _queue_advice(
    queue: list[dict[str, Any]],
    report_data: dict[str, Any],
    readiness_by_campaign: dict[str, dict[str, Any]],
    actions_by_campaign: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    repo_to_campaign: dict[str, str] = {}
    for campaign_type in QUEUE_CAMPAIGN_PRIORITY:
        for action in actions_by_campaign.get(campaign_type, []):
            repo = str(action.get("repo") or "").strip()
            if repo and repo not in repo_to_campaign:
                repo_to_campaign[repo] = campaign_type

    enriched: list[dict[str, Any]] = []
    for item in queue:
        mapped = dict(item)
        repo_name = str(mapped.get("repo") or mapped.get("repo_name") or "").strip()
        campaign_type = repo_to_campaign.get(repo_name) or _infer_campaign(repo_name, mapped, report_data)
        readiness = readiness_by_campaign.get(campaign_type, {})
        stage = str(readiness.get("readiness_stage") or "idle")
        reason = str(readiness.get("reason") or "No current Action Sync guidance is surfaced for this item.")
        target = str(readiness.get("recommended_target") or "none")
        label = readiness.get("label", campaign_type)
        mapped["action_sync_stage"] = stage
        mapped["action_sync_reason"] = reason
        mapped["suggested_campaign"] = campaign_type
        mapped["suggested_writeback_target"] = target
        if target == "none":
            mapped["action_sync_line"] = f"Action Sync: {label} is {stage} — stay local until prerequisites are healthy."
        else:
            mapped["action_sync_line"] = f"Action Sync: {label} is {stage} — recommended target {target}."
        enriched.append(mapped)
    return enriched


def build_action_sync_readiness_bundle(
    report_data: dict[str, Any],
    queue: list[dict[str, Any]],
) -> dict[str, Any]:
    readiness_records: list[dict[str, Any]] = []
    actions_by_campaign: dict[str, list[dict[str, Any]]] = {}
    readiness_by_campaign: dict[str, dict[str, Any]] = {}
    for campaign_type in CAMPAIGN_DISPLAY_ORDER:
        record, actions = _readiness_record(report_data, campaign_type)
        readiness_records.append(record)
        readiness_by_campaign[campaign_type] = record
        actions_by_campaign[campaign_type] = actions

    sorted_records = sorted(readiness_records, key=_campaign_sort_key)
    top_apply_ready = [item for item in sorted_records if item["readiness_stage"] == "apply-ready"][:3]
    top_preview_ready = [item for item in sorted_records if item["readiness_stage"] == "preview-ready"][:3]
    top_drift_review = [item for item in sorted_records if item["readiness_stage"] == "drift-review"][:3]
    top_blocked = [item for item in sorted_records if item["readiness_stage"] == "blocked"][:3]
    enriched_queue = _queue_advice(queue, report_data, readiness_by_campaign, actions_by_campaign)

    campaign_readiness_summary = {
        "campaigns": readiness_records,
        "counts": {
            stage: sum(1 for item in readiness_records if item["readiness_stage"] == stage)
            for stage in ("idle", "preview-ready", "apply-ready", "drift-review", "blocked")
        },
        "summary": _summary_line(
            [
                item
                for item in readiness_records
                if item["readiness_stage"] != "idle"
            ]
        ),
    }
    next_step = _next_step(
        [
            item
            for item in readiness_records
            if item["readiness_stage"] != "idle"
        ]
    )
    action_sync_summary = {
        "summary": campaign_readiness_summary["summary"],
        "top_apply_ready_campaigns": top_apply_ready,
        "top_preview_ready_campaigns": top_preview_ready,
        "top_drift_review_campaigns": top_drift_review,
        "top_blocked_campaigns": top_blocked,
    }
    return {
        "campaign_readiness_summary": campaign_readiness_summary,
        "action_sync_summary": action_sync_summary,
        "next_action_sync_step": next_step,
        "top_apply_ready_campaigns": top_apply_ready,
        "top_preview_ready_campaigns": top_preview_ready,
        "top_drift_review_campaigns": top_drift_review,
        "top_blocked_campaigns": top_blocked,
        "operator_queue": enriched_queue,
    }
