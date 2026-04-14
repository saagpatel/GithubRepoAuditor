from __future__ import annotations

from src.action_sync_automation import build_action_sync_automation_bundle


def _readiness_record(campaign_type: str, readiness_stage: str, *, action_count: int = 2) -> dict:
    return {
        "campaign_type": campaign_type,
        "label": campaign_type.replace("-", " ").title(),
        "action_count": action_count,
        "repo_count": 1,
        "readiness_stage": readiness_stage,
        "reason": f"{campaign_type} is {readiness_stage}.",
        "recommended_target": "all",
        "top_repos": [f"user/{campaign_type}"],
        "sync_mode": "reconcile",
    }


def _packet_record(
    campaign_type: str,
    execution_state: str,
    *,
    blockers: list[str] | None = None,
    approvals_required: list[dict] | None = None,
) -> dict:
    blockers = blockers or []
    return {
        "campaign_type": campaign_type,
        "label": campaign_type.replace("-", " ").title(),
        "readiness_stage": "preview-ready",
        "execution_state": execution_state,
        "recommended_target": "all",
        "sync_mode": "reconcile",
        "action_count": 2,
        "repo_count": 1,
        "blocker_types": blockers,
        "blockers": blockers,
        "approvals_required": approvals_required or [],
        "rollback_status": "ready",
        "preview_command": f"audit testuser --campaign {campaign_type} --writeback-target all",
        "apply_command": f"audit testuser --campaign {campaign_type} --writeback-target all --writeback-apply",
        "top_repos": [f"user/{campaign_type}"],
        "summary": f"{campaign_type} packet summary",
    }


def _outcome_record(campaign_type: str, monitoring_state: str) -> dict:
    return {
        "campaign_type": campaign_type,
        "label": campaign_type.replace("-", " ").title(),
        "latest_target": "all",
        "latest_run_mode": "apply",
        "recent_apply_count": 1,
        "monitored_repo_count": 1,
        "monitoring_state": monitoring_state,
        "pressure_effect": "reduced",
        "drift_state": "returned" if monitoring_state == "drift-returned" else "clear",
        "reopen_state": "reopened" if monitoring_state == "reopened" else "none",
        "rollback_state": "partial" if monitoring_state == "rollback-watch" else "ready",
        "follow_up_recommendation": f"Follow up on {campaign_type}.",
        "top_repos": [f"user/{campaign_type}"],
        "summary": f"{campaign_type} monitoring summary",
    }


def _tuning_record(campaign_type: str) -> dict:
    return {
        "campaign_type": campaign_type,
        "label": campaign_type.replace("-", " ").title(),
        "judged_count": 3,
        "monitor_now_count": 0,
        "holding_clean_rate": 1.0,
        "drift_return_rate": 0.0,
        "reopen_rate": 0.0,
        "rollback_watch_rate": 0.0,
        "pressure_reduction_rate": 1.0,
        "tuning_status": "proven",
        "recommendation_bias": "promote",
        "summary": f"{campaign_type} should win ties because recent outcomes are proven.",
    }


def _bundle(
    *,
    packet_overrides: dict[str, dict] | None = None,
    outcome_overrides: dict[str, dict] | None = None,
    intervention_bundle: dict | None = None,
    queue: list[dict] | None = None,
) -> dict:
    packet_overrides = packet_overrides or {}
    outcome_overrides = outcome_overrides or {}
    queue = queue or [{"repo": "RepoSecure", "suggested_campaign": "security-review"}]
    campaign_types = [
        "security-review",
        "promotion-push",
        "archive-sweep",
        "showcase-publish",
        "maintenance-cleanup",
    ]
    readiness = [_readiness_record(campaign, "idle", action_count=0) for campaign in campaign_types]
    packets = [_packet_record(campaign, "stay-local") for campaign in campaign_types]
    outcomes = [_outcome_record(campaign, "no-recent-apply") for campaign in campaign_types]
    tuning = [_tuning_record(campaign) for campaign in campaign_types]

    for record in packets:
        if record["campaign_type"] in packet_overrides:
            record.update(packet_overrides[record["campaign_type"]])
    for record in outcomes:
        if record["campaign_type"] in outcome_overrides:
            record.update(outcome_overrides[record["campaign_type"]])

    return build_action_sync_automation_bundle(
        {"username": "testuser"},
        {"campaign_readiness_summary": {"campaigns": readiness}},
        {"action_sync_packets": packets},
        {"action_sync_outcomes": outcomes},
        {"action_sync_tuning": tuning},
        intervention_bundle
        or {
            "top_relapsing_repos": [],
            "top_persistent_pressure_repos": [],
            "top_improving_repos": [],
            "top_holding_repos": [],
        },
        queue,
    )


def _automation(bundle: dict, campaign_type: str) -> dict:
    return next(item for item in bundle["action_sync_automation"] if item["campaign_type"] == campaign_type)


def test_automation_classifies_preview_apply_approval_follow_up_and_quiet() -> None:
    bundle = _bundle(
        packet_overrides={
            "security-review": _packet_record("security-review", "preview-next"),
            "promotion-push": _packet_record("promotion-push", "ready-to-apply"),
            "archive-sweep": _packet_record(
                "archive-sweep",
                "needs-approval",
                blockers=["governance-approval"],
                approvals_required=[{"kind": "governance"}],
            ),
        },
        outcome_overrides={
            "showcase-publish": _outcome_record("showcase-publish", "monitor-now"),
        },
    )

    assert _automation(bundle, "security-review")["automation_posture"] == "preview-safe"
    assert _automation(bundle, "security-review")["recommended_command"].endswith("--writeback-target all")
    assert "--writeback-apply" not in _automation(bundle, "security-review")["recommended_command"]

    assert _automation(bundle, "promotion-push")["automation_posture"] == "apply-manual"
    assert _automation(bundle, "promotion-push")["recommended_command"].startswith("Manual apply only: audit testuser")
    assert "--writeback-apply" in _automation(bundle, "promotion-push")["recommended_command"]

    assert _automation(bundle, "archive-sweep")["automation_posture"] == "approval-first"
    assert _automation(bundle, "archive-sweep")["recommended_command"] == ""
    assert _automation(bundle, "archive-sweep")["requires_approval"] is True

    assert _automation(bundle, "showcase-publish")["automation_posture"] == "follow-up-safe"
    assert _automation(bundle, "showcase-publish")["recommended_command"] == "audit testuser --control-center"

    assert _automation(bundle, "maintenance-cleanup")["automation_posture"] == "quiet-safe"
    assert _automation(bundle, "maintenance-cleanup")["recommended_command"] == ""


def test_automation_downgrades_to_manual_only_for_monitoring_or_history_risk() -> None:
    monitoring_bundle = _bundle(
        packet_overrides={
            "security-review": _packet_record("security-review", "preview-next"),
        },
        outcome_overrides={
            "security-review": _outcome_record("security-review", "drift-returned"),
        },
    )
    assert _automation(monitoring_bundle, "security-review")["automation_posture"] == "manual-only"

    history_bundle = _bundle(
        packet_overrides={
            "security-review": _packet_record("security-review", "preview-next"),
        },
        intervention_bundle={
            "top_relapsing_repos": [{"repo": "RepoSecure", "suggested_campaign": "security-review"}],
            "top_persistent_pressure_repos": [],
            "top_improving_repos": [],
            "top_holding_repos": [],
        },
    )
    automation = _automation(history_bundle, "security-review")
    assert automation["automation_posture"] == "manual-only"
    assert "relapse or persistent pressure" in automation["automation_reason"].lower()


def test_automation_next_step_priority_prefers_approval_then_manual_then_preview() -> None:
    bundle = _bundle(
        packet_overrides={
            "security-review": _packet_record("security-review", "preview-next"),
            "promotion-push": _packet_record(
                "promotion-push",
                "needs-approval",
                blockers=["governance-approval"],
                approvals_required=[{"kind": "governance"}],
            ),
            "archive-sweep": _packet_record("archive-sweep", "preview-next"),
        },
        outcome_overrides={
            "archive-sweep": _outcome_record("archive-sweep", "reopened"),
        },
    )

    assert bundle["next_safe_automation_step"]["campaign_type"] == "promotion-push"
    assert bundle["next_safe_automation_step"]["automation_posture"] == "approval-first"
    assert bundle["top_manual_only_campaigns"][0]["campaign_type"] == "archive-sweep"


def test_queue_items_receive_automation_fields() -> None:
    bundle = _bundle(
        packet_overrides={
            "security-review": _packet_record("security-review", "preview-next"),
        },
        queue=[{"repo": "RepoSecure", "suggested_campaign": "security-review"}],
    )

    queue_item = bundle["operator_queue"][0]
    assert queue_item["automation_posture"] == "preview-safe"
    assert queue_item["automation_summary"].startswith("Security Review is preview-safe")
    assert queue_item["automation_line"].startswith("Automation Guidance:")
    assert queue_item["automation_command"].endswith("--writeback-target all")
