from __future__ import annotations

from src.action_sync_tuning import build_action_sync_tuning_bundle


def _history_row(
    campaign_type: str,
    run_id: str,
    generated_at: str,
    *,
    monitoring_state: str,
    pressure_effect: str = "reduced",
) -> dict:
    return {
        "run_id": run_id,
        "generated_at": generated_at,
        "campaign_type": campaign_type,
        "monitoring_state": monitoring_state,
        "pressure_effect": pressure_effect,
        "drift_state": "returned" if monitoring_state == "drift-returned" else "clear",
        "reopen_state": "reopened" if monitoring_state == "reopened" else "none",
        "rollback_state": "partial" if monitoring_state == "rollback-watch" else "ready",
        "latest_target": "all",
        "details": {},
    }


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


def _packet_record(campaign_type: str, execution_state: str, *, action_count: int = 2) -> dict:
    return {
        "campaign_type": campaign_type,
        "label": campaign_type.replace("-", " ").title(),
        "readiness_stage": "preview-ready",
        "execution_state": execution_state,
        "recommended_target": "all",
        "sync_mode": "reconcile",
        "action_count": action_count,
        "repo_count": 1,
        "blocker_types": [],
        "blockers": [],
        "approvals_required": [],
        "rollback_status": "ready",
        "preview_command": f"audit testuser --campaign {campaign_type} --writeback-target all",
        "apply_command": f"audit testuser --campaign {campaign_type} --writeback-target all --writeback-apply",
        "top_repos": [f"user/{campaign_type}"],
        "summary": f"{campaign_type} packet summary",
    }


def _report_data(**overrides) -> dict:
    data = {
        "username": "testuser",
        "generated_at": "2026-04-13T12:00:00+00:00",
        "action_sync_outcomes": [],
        "campaign_summary": {},
    }
    data.update(overrides)
    return data


def _bundle(
    *,
    readiness_records: list[dict],
    packet_records: list[dict],
    outcome_history: list[dict],
) -> dict:
    return build_action_sync_tuning_bundle(
        _report_data(),
        {"campaign_readiness_summary": {"campaigns": readiness_records}},
        {"action_sync_packets": packet_records},
        {"action_sync_outcomes": []},
        [{"repo": "RepoSecure", "suggested_campaign": "security-review"}],
        recent_runs=[
            {"run_id": "run-4", "generated_at": "2026-04-13T11:00:00+00:00"},
            {"run_id": "run-3", "generated_at": "2026-04-13T10:00:00+00:00"},
        ],
        recent_campaign_runs=[],
        outcome_history=outcome_history,
    )


def _tuning(bundle: dict, campaign_type: str) -> dict:
    return next(item for item in bundle["action_sync_tuning"] if item["campaign_type"] == campaign_type)


def test_tuning_classifies_proven_mixed_caution_and_insufficient_evidence() -> None:
    bundle = _bundle(
        readiness_records=[
            _readiness_record("security-review", "preview-ready"),
            _readiness_record("promotion-push", "preview-ready"),
            _readiness_record("maintenance-cleanup", "preview-ready"),
            _readiness_record("archive-sweep", "preview-ready"),
        ],
        packet_records=[
            _packet_record("security-review", "preview-next"),
            _packet_record("promotion-push", "preview-next"),
            _packet_record("maintenance-cleanup", "preview-next"),
            _packet_record("archive-sweep", "preview-next"),
        ],
        outcome_history=[
            _history_row("security-review", "run-1", "2026-04-13T09:00:00+00:00", monitoring_state="holding-clean"),
            _history_row("security-review", "run-2", "2026-04-12T09:00:00+00:00", monitoring_state="holding-clean"),
            _history_row("security-review", "run-3", "2026-04-11T09:00:00+00:00", monitoring_state="holding-clean"),
            _history_row("promotion-push", "run-4", "2026-04-13T08:00:00+00:00", monitoring_state="holding-clean"),
            _history_row("promotion-push", "run-5", "2026-04-12T08:00:00+00:00", monitoring_state="holding-clean", pressure_effect="flat"),
            _history_row("promotion-push", "run-6", "2026-04-11T08:00:00+00:00", monitoring_state="rollback-watch", pressure_effect="flat"),
            _history_row("promotion-push", "run-12", "2026-04-10T08:00:00+00:00", monitoring_state="drift-returned", pressure_effect="flat"),
            _history_row("maintenance-cleanup", "run-7", "2026-04-13T07:00:00+00:00", monitoring_state="drift-returned", pressure_effect="worse"),
            _history_row("maintenance-cleanup", "run-8", "2026-04-12T07:00:00+00:00", monitoring_state="reopened", pressure_effect="flat"),
            _history_row("maintenance-cleanup", "run-9", "2026-04-11T07:00:00+00:00", monitoring_state="rollback-watch", pressure_effect="flat"),
            _history_row("archive-sweep", "run-10", "2026-04-13T06:00:00+00:00", monitoring_state="holding-clean"),
            _history_row("archive-sweep", "run-11", "2026-04-12T06:00:00+00:00", monitoring_state="monitor-now"),
        ],
    )

    assert _tuning(bundle, "security-review")["tuning_status"] == "proven"
    assert _tuning(bundle, "security-review")["recommendation_bias"] == "promote"
    assert _tuning(bundle, "security-review")["pressure_reduction_rate"] == 1.0
    assert _tuning(bundle, "promotion-push")["tuning_status"] == "mixed"
    assert _tuning(bundle, "promotion-push")["recommendation_bias"] == "neutral"
    assert _tuning(bundle, "promotion-push")["pressure_reduction_rate"] == 0.25
    assert _tuning(bundle, "maintenance-cleanup")["tuning_status"] == "caution"
    assert _tuning(bundle, "maintenance-cleanup")["recommendation_bias"] == "defer"
    assert _tuning(bundle, "archive-sweep")["tuning_status"] == "insufficient-evidence"
    assert _tuning(bundle, "archive-sweep")["recommendation_bias"] == "neutral"
    assert _tuning(bundle, "archive-sweep")["judged_count"] == 1


def test_tuning_breaks_ties_within_same_readiness_stage_but_not_across_stages() -> None:
    same_stage_bundle = _bundle(
        readiness_records=[
            _readiness_record("security-review", "preview-ready"),
            _readiness_record("promotion-push", "preview-ready"),
        ],
        packet_records=[
            _packet_record("security-review", "preview-next"),
            _packet_record("promotion-push", "preview-next"),
        ],
        outcome_history=[
            _history_row("security-review", "run-1", "2026-04-13T09:00:00+00:00", monitoring_state="holding-clean"),
            _history_row("security-review", "run-2", "2026-04-12T09:00:00+00:00", monitoring_state="holding-clean"),
            _history_row("security-review", "run-3", "2026-04-11T09:00:00+00:00", monitoring_state="holding-clean"),
            _history_row("promotion-push", "run-4", "2026-04-13T08:00:00+00:00", monitoring_state="drift-returned", pressure_effect="flat"),
            _history_row("promotion-push", "run-5", "2026-04-12T08:00:00+00:00", monitoring_state="reopened", pressure_effect="worse"),
            _history_row("promotion-push", "run-6", "2026-04-11T08:00:00+00:00", monitoring_state="rollback-watch", pressure_effect="flat"),
        ],
    )

    assert same_stage_bundle["next_tuned_campaign"]["campaign_type"] == "security-review"
    assert same_stage_bundle["top_preview_ready_campaigns"][0]["campaign_type"] == "security-review"
    assert same_stage_bundle["next_action_sync_step"].startswith("Preview Security Review")

    stronger_stage_bundle = _bundle(
        readiness_records=[
            _readiness_record("security-review", "preview-ready"),
            _readiness_record("promotion-push", "apply-ready"),
        ],
        packet_records=[
            _packet_record("security-review", "preview-next"),
            _packet_record("promotion-push", "ready-to-apply"),
        ],
        outcome_history=[
            _history_row("security-review", "run-1", "2026-04-13T09:00:00+00:00", monitoring_state="holding-clean"),
            _history_row("security-review", "run-2", "2026-04-12T09:00:00+00:00", monitoring_state="holding-clean"),
            _history_row("security-review", "run-3", "2026-04-11T09:00:00+00:00", monitoring_state="holding-clean"),
            _history_row("promotion-push", "run-4", "2026-04-13T08:00:00+00:00", monitoring_state="drift-returned", pressure_effect="flat"),
            _history_row("promotion-push", "run-5", "2026-04-12T08:00:00+00:00", monitoring_state="reopened", pressure_effect="worse"),
            _history_row("promotion-push", "run-6", "2026-04-11T08:00:00+00:00", monitoring_state="rollback-watch", pressure_effect="flat"),
        ],
    )

    assert stronger_stage_bundle["next_tuned_campaign"]["campaign_type"] == "promotion-push"
    assert stronger_stage_bundle["top_apply_ready_campaigns"][0]["campaign_type"] == "promotion-push"
    assert stronger_stage_bundle["next_action_sync_step"].startswith("Promotion Push is ready to apply")


def test_tuning_breaks_ties_within_same_execution_state_but_not_across_execution_states() -> None:
    same_state_bundle = _bundle(
        readiness_records=[
            _readiness_record("security-review", "preview-ready"),
            _readiness_record("promotion-push", "preview-ready"),
        ],
        packet_records=[
            _packet_record("security-review", "preview-next"),
            _packet_record("promotion-push", "preview-next"),
        ],
        outcome_history=[
            _history_row("security-review", "run-1", "2026-04-13T09:00:00+00:00", monitoring_state="holding-clean"),
            _history_row("security-review", "run-2", "2026-04-12T09:00:00+00:00", monitoring_state="holding-clean"),
            _history_row("security-review", "run-3", "2026-04-11T09:00:00+00:00", monitoring_state="holding-clean"),
            _history_row("promotion-push", "run-4", "2026-04-13T08:00:00+00:00", monitoring_state="drift-returned", pressure_effect="flat"),
            _history_row("promotion-push", "run-5", "2026-04-12T08:00:00+00:00", monitoring_state="reopened", pressure_effect="worse"),
            _history_row("promotion-push", "run-6", "2026-04-11T08:00:00+00:00", monitoring_state="rollback-watch", pressure_effect="flat"),
        ],
    )

    assert same_state_bundle["next_apply_candidate"]["campaign_type"] == "security-review"
    assert same_state_bundle["top_ready_to_apply_packets"] == []
    assert same_state_bundle["next_apply_candidate"]["execution_state"] == "preview-next"

    stronger_state_bundle = _bundle(
        readiness_records=[
            _readiness_record("security-review", "preview-ready"),
            _readiness_record("promotion-push", "apply-ready"),
        ],
        packet_records=[
            _packet_record("security-review", "preview-next"),
            _packet_record("promotion-push", "ready-to-apply"),
        ],
        outcome_history=[
            _history_row("security-review", "run-1", "2026-04-13T09:00:00+00:00", monitoring_state="holding-clean"),
            _history_row("security-review", "run-2", "2026-04-12T09:00:00+00:00", monitoring_state="holding-clean"),
            _history_row("security-review", "run-3", "2026-04-11T09:00:00+00:00", monitoring_state="holding-clean"),
            _history_row("promotion-push", "run-4", "2026-04-13T08:00:00+00:00", monitoring_state="drift-returned", pressure_effect="flat"),
            _history_row("promotion-push", "run-5", "2026-04-12T08:00:00+00:00", monitoring_state="reopened", pressure_effect="worse"),
            _history_row("promotion-push", "run-6", "2026-04-11T08:00:00+00:00", monitoring_state="rollback-watch", pressure_effect="flat"),
        ],
    )

    assert stronger_state_bundle["next_apply_candidate"]["campaign_type"] == "promotion-push"
    assert stronger_state_bundle["top_ready_to_apply_packets"][0]["campaign_type"] == "promotion-push"
    assert stronger_state_bundle["next_apply_candidate"]["execution_state"] == "ready-to-apply"
    assert stronger_state_bundle["operator_queue"][0]["campaign_tuning_status"] == "proven"
    assert stronger_state_bundle["operator_queue"][0]["campaign_tuning_line"].startswith("Campaign Tuning:")
