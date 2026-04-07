from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.baseline_context import build_watch_guidance
from src.governance_activation import build_governance_summary
from src.recurring_review import build_review_bundle
from src.warehouse import load_recent_operator_changes

LANE_ORDER = {"blocked": 0, "urgent": 1, "ready": 2, "deferred": 3}
LANE_LABELS = {
    "blocked": "Blocked",
    "urgent": "Needs Attention Now",
    "ready": "Ready for Manual Action",
    "deferred": "Safe to Defer",
}


def normalize_review_state(
    report_data: dict,
    *,
    output_dir: Path,
    diff_data: dict | None = None,
    portfolio_profile: str = "default",
    collection_name: str | None = None,
) -> dict:
    """Return report data with normalized review fields populated when possible."""
    data = dict(report_data)
    if _has_normalized_review_state(data):
        data["review_targets"] = [_normalize_review_target(item) for item in data.get("review_targets") or []]
        data["review_history"] = [_normalize_review_history_item(item) for item in data.get("review_history") or []]
        data["review_summary"] = _normalize_review_summary(data.get("review_summary") or {})
        return data
    try:
        bundle = build_review_bundle(
            data,
            output_dir=output_dir,
            diff_data=diff_data,
            materiality="standard",
            portfolio_profile=portfolio_profile,
            collection_name=collection_name,
            watch_state=data.get("watch_state") or {},
            emit_when_quiet=False,
        )
    except Exception:
        bundle = {
            "review_summary": {
                "status": "unavailable",
                "safe_to_defer": False,
                "material_change_count": 0,
                "reason": "Review state could not be reconstructed from the latest report.",
            },
            "review_alerts": [],
            "material_changes": [],
            "review_targets": [],
            "review_history": [],
            "watch_state": data.get("watch_state") or {},
        }
    bundle["review_targets"] = [_normalize_review_target(item) for item in bundle.get("review_targets") or []]
    bundle["review_history"] = [_normalize_review_history_item(item) for item in bundle.get("review_history") or []]
    bundle["review_summary"] = _normalize_review_summary(bundle.get("review_summary") or {})
    data.update(bundle)
    return data


def build_operator_snapshot(
    report_data: dict,
    *,
    output_dir: Path,
    triage_view: str = "all",
) -> dict:
    queue: list[dict] = []
    preflight = report_data.get("preflight_summary") or {}
    review_summary = report_data.get("review_summary") or {}
    review_targets = report_data.get("review_targets") or []
    managed_state_drift = report_data.get("managed_state_drift") or []
    governance_drift = report_data.get("governance_drift") or []
    governance_preview = report_data.get("governance_preview") or {}
    governance_summary = report_data.get("governance_summary") or build_governance_summary(report_data)
    campaign_summary = report_data.get("campaign_summary") or {}
    writeback_preview = report_data.get("writeback_preview") or {}
    rollback_preview = report_data.get("rollback_preview") or {}

    for check in preflight.get("checks") or []:
        status = check.get("status", check.get("severity", "warning"))
        if status != "error":
            continue
        queue.append(
            _queue_item(
                item_id=f"setup:{check.get('key', check.get('category', 'issue'))}",
                kind="setup",
                lane="blocked",
                priority=100,
                repo="",
                title=check.get("summary", "Setup issue"),
                summary=check.get("details") or check.get("summary", "Setup issue"),
                recommended_action=check.get("recommended_fix", "Resolve the setup blocker before the next run."),
                source_run_id=review_summary.get("source_run_id", ""),
                links=[],
            )
        )

    for drift in managed_state_drift:
        queue.append(
            _queue_item(
                item_id=f"campaign-drift:{drift.get('action_id', drift.get('repo_full_name', drift.get('repo', 'unknown')))}:{drift.get('target', '')}",
                kind="campaign",
                lane="urgent",
                priority=85,
                repo=_repo_name(drift),
                title=f"{_repo_name(drift) or 'Campaign'} drift needs review",
                summary=drift.get("drift_state", drift.get("drift_type", "Managed state drift detected.")),
                recommended_action="Inspect the managed issue, topics, or custom properties before closing or applying more campaign work.",
                source_run_id=review_summary.get("source_run_id", ""),
                links=_links_from_payload(drift),
            )
        )

    for drift in governance_drift:
        lane = "blocked" if drift.get("drift_type") in {"approval-invalidated", "requires-reapproval"} else "urgent"
        queue.append(
            _queue_item(
                item_id=f"governance-drift:{drift.get('action_id', drift.get('repo_full_name', drift.get('repo', 'unknown')))}:{drift.get('control_key', drift.get('target', ''))}",
                kind="governance",
                lane=lane,
                priority=90 if lane == "blocked" else 80,
                repo=_repo_name(drift),
                title=f"{_repo_name(drift) or 'Governance'} drift needs review",
                summary=drift.get("drift_type", "Governance drift detected."),
                recommended_action="Review the governed control state and re-approve before any apply step if the fingerprint changed.",
                source_run_id=review_summary.get("source_run_id", ""),
                links=_links_from_payload(drift),
            )
        )

    if governance_summary.get("needs_reapproval") and not governance_drift:
        queue.append(
            _queue_item(
                item_id="governance:needs-reapproval",
                kind="governance",
                lane="blocked",
                priority=92,
                repo="",
                title="Governed controls need re-approval",
                summary=governance_summary.get("headline", "Governed controls need re-approval before any apply step."),
                recommended_action="Review the governed controls and re-approve them before the next manual apply step.",
                source_run_id=review_summary.get("source_run_id", ""),
                links=[],
            )
        )

    for change in report_data.get("material_changes") or []:
        if change.get("severity", 0.0) < 0.8:
            continue
        queue.append(
            _queue_item(
                item_id=f"review-change:{change.get('change_key', change.get('title', 'change'))}",
                kind="review",
                lane="urgent",
                priority=int(round(change.get("severity", 0.0) * 100)),
                repo=change.get("repo_name", ""),
                title=change.get("title", "High-severity review change"),
                summary=change.get("summary", ""),
                recommended_action=change.get("recommended_next_step", "Review the repo before reprioritizing work."),
                source_run_id=review_summary.get("source_run_id", ""),
                links=[],
            )
        )

    for target in review_targets:
        recommended = target.get("recommended_next_step", "")
        safe_to_defer = "safe to defer" in recommended.lower()
        lane = "deferred" if safe_to_defer else "ready"
        priority = 30 if safe_to_defer else int(round(target.get("severity", 0.0) * 100)) or 60
        queue.append(
            _queue_item(
                item_id=f"review-target:{target.get('repo', 'portfolio')}:{target.get('reason', '')}",
                kind="review",
                lane=lane,
                priority=priority,
                repo=target.get("repo", ""),
                title=f"Review {_repo_or_portfolio(target)}",
                summary=target.get("reason", "Needs analyst review."),
                recommended_action=recommended or ("Safe to defer." if safe_to_defer else "Inspect the latest changes and decide on next action."),
                source_run_id=review_summary.get("source_run_id", ""),
                links=[],
            )
        )

    if campaign_summary.get("action_count", 0):
        queue.append(
            _queue_item(
                item_id=f"campaign-ready:{campaign_summary.get('campaign_type', 'campaign')}",
                kind="campaign",
                lane="ready",
                priority=70,
                repo="",
                title=f"{campaign_summary.get('label', campaign_summary.get('campaign_type', 'Campaign'))} is ready for review",
                summary=f"{campaign_summary.get('action_count', 0)} actions across {campaign_summary.get('repo_count', 0)} repos.",
                recommended_action=f"Review the {writeback_preview.get('sync_mode', 'reconcile')} queue before any manual writeback.",
                source_run_id=review_summary.get("source_run_id", ""),
                links=[],
            )
        )

    for action in governance_preview.get("actions", []) or []:
        if not action.get("applyable"):
            continue
        queue.append(
            _queue_item(
                item_id=f"governance-ready:{action.get('action_id', action.get('repo_full_name', 'governance'))}",
                kind="governance",
                lane="ready",
                priority=75,
                repo=_repo_name(action),
                title=action.get("title", "Governed control ready"),
                summary=action.get("why", "A governed control is ready for operator review."),
                recommended_action="Review prerequisites and approve the governed control if the repo is ready.",
                source_run_id=review_summary.get("source_run_id", ""),
                links=_links_from_payload(action),
            )
        )

    if rollback_preview.get("available") and not rollback_preview.get("fully_reversible_count", 0):
        queue.append(
            _queue_item(
                item_id="rollback-exposure",
                kind="campaign",
                lane="urgent",
                priority=78,
                repo="",
                title="Rollback coverage is only partial",
                summary=f"{rollback_preview.get('item_count', 0)} managed changes exist but not all are fully reversible.",
                recommended_action="Review rollback exposure before the next manual apply or close decision.",
                source_run_id=review_summary.get("source_run_id", ""),
                links=[],
            )
        )

    queue = _dedupe_queue(queue)
    queue.sort(
        key=lambda item: (
            LANE_ORDER.get(item["lane"], 99),
            -item["priority"],
            -item["age_days"],
            item["title"],
        )
    )
    if triage_view != "all":
        queue = [item for item in queue if item["lane"] == triage_view]

    recent_changes = load_recent_operator_changes(output_dir, report_data.get("username", ""), limit=12)
    setup_health = {
        "status": preflight.get("status", "unknown"),
        "blocking_errors": preflight.get("blocking_errors", 0),
        "warnings": preflight.get("warnings", 0),
    }
    counts = {lane: sum(1 for item in queue if item["lane"] == lane) for lane in LANE_ORDER}
    watch_guidance = build_watch_guidance(report_data.get("watch_state") or {})
    summary = {
        "headline": _headline_for_queue(queue, setup_health),
        "selected_view": triage_view,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_run_id": review_summary.get("source_run_id", ""),
        "report_reference": report_data.get("latest_report_path", ""),
        "counts": counts,
        "total_items": len(queue),
        "review_status": review_summary.get("status", "unavailable"),
        "operator_setup_health": setup_health,
        "operator_recent_changes": recent_changes,
        "watch_strategy": watch_guidance.get("requested_strategy", "manual"),
        "watch_enabled": watch_guidance.get("watch_enabled", False),
        "watch_chosen_mode": watch_guidance.get("chosen_mode", ""),
        "watch_decision_reason": watch_guidance.get("reason", ""),
        "watch_decision_summary": watch_guidance.get("reason_summary", ""),
        "next_recommended_run_mode": watch_guidance.get("next_recommended_run_mode", ""),
        "full_refresh_due": watch_guidance.get("full_refresh_due", False),
        "latest_trusted_baseline": watch_guidance.get("latest_trusted_baseline", {}),
        "operator_watch_decision": watch_guidance,
    }
    return {
        "operator_summary": summary,
        "operator_queue": queue,
        "operator_setup_health": setup_health,
        "operator_recent_changes": recent_changes,
    }


def render_control_center_markdown(snapshot: dict, username: str, generated_at: str) -> str:
    summary = snapshot.get("operator_summary", {})
    setup_health = snapshot.get("operator_setup_health", {})
    lines = [
        f"# Operator Control Center: {username}",
        "",
        f"*Generated:* {generated_at[:10]}",
        f"*Headline:* {summary.get('headline', 'No triage items available.')}",
        "",
    ]
    if summary.get("report_reference"):
        lines.append(f"*Latest Report:* `{summary['report_reference']}`")
    if summary.get("source_run_id"):
        lines.append(f"*Source Run:* `{summary['source_run_id']}`")
    if summary.get("next_recommended_run_mode"):
        lines.append(f"*Next Recommended Run:* `{summary['next_recommended_run_mode']}`")
    if summary.get("watch_strategy"):
        lines.append(f"*Watch Strategy:* `{summary['watch_strategy']}`")
    if summary.get("watch_decision_summary"):
        lines.append(f"*Watch Decision:* {summary['watch_decision_summary']}")
    if summary.get("control_center_reference"):
        lines.append(f"*Control Center Artifact:* `{summary['control_center_reference']}`")
    lines.append(
        f"*Setup Health:* {setup_health.get('status', 'unknown')} | "
        f"Errors: {setup_health.get('blocking_errors', 0)} | "
        f"Warnings: {setup_health.get('warnings', 0)}"
    )
    lines.append("")
    queue = snapshot.get("operator_queue", [])
    for lane in ("blocked", "urgent", "ready", "deferred"):
        items = [item for item in queue if item["lane"] == lane]
        if not items:
            continue
        lines.append(f"## {LANE_LABELS[lane]}")
        lines.append("")
        for item in items:
            repo = f"{item['repo']}: " if item.get("repo") else ""
            lines.append(f"- {repo}{item['title']} — {item['summary']}")
            lines.append(f"  Why this lane: {item.get('lane_reason', item.get('lane_label', LANE_LABELS.get(item['lane'], item['lane'])))}")
            lines.append(f"  Action: {item['recommended_action']}")
        lines.append("")
    recent_changes = snapshot.get("operator_recent_changes") or []
    if recent_changes:
        lines.append("## Recently Changed")
        lines.append("")
        for change in recent_changes[:6]:
            when = change.get("generated_at", "")[:10]
            subject = change.get("repo") or change.get("repo_full_name") or change.get("item_id") or "portfolio"
            lines.append(f"- {when}: {subject} — {change.get('summary', change.get('kind', 'Operator change'))}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def control_center_artifact_payload(report_data: dict, snapshot: dict) -> dict:
    return {
        "username": report_data.get("username", "unknown"),
        "generated_at": report_data.get("generated_at", ""),
        "report_reference": report_data.get("latest_report_path", ""),
        "watch_state": report_data.get("watch_state", {}),
        "operator_summary": snapshot.get("operator_summary", {}),
        "operator_queue": snapshot.get("operator_queue", []),
        "operator_setup_health": snapshot.get("operator_setup_health", {}),
        "operator_recent_changes": snapshot.get("operator_recent_changes", []),
        "review_summary": report_data.get("review_summary", {}),
        "preflight_summary": report_data.get("preflight_summary", {}),
    }


def _has_normalized_review_state(report_data: dict) -> bool:
    return any(
        report_data.get(key)
        for key in ("review_summary", "review_alerts", "material_changes", "review_targets", "review_history")
    )


def _queue_item(
    *,
    item_id: str,
    kind: str,
    lane: str,
    priority: int,
    repo: str,
    title: str,
    summary: str,
    recommended_action: str,
    source_run_id: str,
    links: list[dict],
) -> dict:
    age_days = _age_days_from_run_id(source_run_id)
    lane_label = LANE_LABELS.get(lane, lane.replace("-", " ").title())
    return {
        "item_id": item_id,
        "kind": kind,
        "lane": lane,
        "lane_label": lane_label,
        "lane_reason": _lane_reason(lane, kind),
        "priority": priority,
        "repo": repo,
        "title": title,
        "summary": summary,
        "recommended_action": recommended_action,
        "source_run_id": source_run_id,
        "age_days": age_days,
        "links": links,
    }


def _normalize_review_summary(summary: dict) -> dict:
    normalized = dict(summary)
    decision_state = normalized.get("decision_state")
    if not decision_state:
        decisions = normalized.get("decisions") or []
        decision_values = [item.get("decision") for item in decisions if isinstance(item, dict)]
        if "approve-governance" in decision_values:
            decision_state = "ready-for-governance-approval"
        elif "preview-campaign" in decision_values:
            decision_state = "ready-for-campaign-preview"
        elif normalized.get("safe_to_defer"):
            decision_state = "safe-to-defer"
        else:
            decision_state = "needs-review"
    normalized.setdefault("status", "open")
    normalized.setdefault("sync_state", "local-only")
    normalized["decision_state"] = decision_state
    normalized.setdefault("synced_targets", [])
    return normalized


def _normalize_review_target(item: dict) -> dict:
    normalized = dict(item)
    next_step = normalized.get("next_step") or normalized.get("recommended_next_step") or ""
    normalized.setdefault("title", normalized.get("repo", "Portfolio review target"))
    normalized.setdefault("reason", normalized.get("summary", normalized.get("reason", "")))
    normalized["recommended_next_step"] = next_step
    normalized["next_step"] = next_step
    normalized.setdefault("decision_hint", "safe-to-defer" if "safe to defer" in next_step.lower() else "needs-review")
    normalized.setdefault("safe_to_defer", "safe to defer" in next_step.lower())
    return normalized


def _normalize_review_history_item(item: dict) -> dict:
    normalized = dict(item)
    normalized.setdefault("status", "open")
    normalized.setdefault("decision_state", "needs-review")
    normalized.setdefault("sync_state", "local-only")
    normalized.setdefault("safe_to_defer", normalized.get("decision_state") == "safe-to-defer")
    return normalized


def _headline_for_queue(queue: list[dict], setup_health: dict) -> str:
    if setup_health.get("blocking_errors", 0):
        return "Setup blockers need to be cleared before the next trustworthy run."
    if any(item["lane"] == "blocked" for item in queue):
        return "A blocked operator item needs attention before more manual action."
    if any(item["lane"] == "urgent" for item in queue):
        return "There is live drift or high-severity change that needs attention now."
    if any(item["lane"] == "ready" for item in queue):
        return "Manual review and apply work is ready when you are."
    if any(item["lane"] == "deferred" for item in queue):
        return "Everything currently surfaced is safe to defer."
    return "No operator triage items are currently surfaced."


def _lane_reason(lane: str, kind: str) -> str:
    if lane == "blocked":
        return "This item cannot move forward safely until the blocker is cleared."
    if lane == "urgent":
        return "This item shows live drift, high-severity change, or rollback exposure."
    if lane == "ready":
        if kind == "review":
            return "This item is actionable now and ready for a human decision."
        return "This item is ready for manual preview, approval, or apply review."
    return "This item is explicitly safe to defer for now."


def _repo_name(payload: dict) -> str:
    repo = payload.get("repo") or payload.get("repo_name")
    if repo:
        return repo
    full_name = payload.get("repo_full_name", "")
    return full_name.split("/")[-1] if full_name else ""


def _repo_or_portfolio(payload: dict) -> str:
    return payload.get("repo", "") or "portfolio"


def _links_from_payload(payload: dict) -> list[dict]:
    links: list[dict] = []
    for key in ("url", "html_url"):
        if payload.get(key):
            links.append({"label": key, "url": payload[key]})
    return links


def _age_days_from_run_id(source_run_id: str) -> int:
    if not source_run_id or ":" not in source_run_id:
        return 0
    timestamp = source_run_id.split(":", 1)[1]
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0, (datetime.now(timezone.utc) - dt).days)


def _dedupe_queue(queue: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen: set[str] = set()
    for item in queue:
        if item["item_id"] in seen:
            continue
        seen.add(item["item_id"])
        deduped.append(item)
    return deduped
