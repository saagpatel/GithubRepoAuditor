from __future__ import annotations

from src.action_sync_outcomes import build_action_sync_outcomes_bundle


def _run_snapshot(
    run_id: str,
    generated_at: str,
    *,
    blocked: int | None = 0,
    urgent: int | None = 0,
    managed_state_drift: list[dict] | None = None,
) -> dict:
    operator_summary = {}
    if blocked is not None or urgent is not None:
        operator_summary = {
            "counts": {
                "blocked": blocked or 0,
                "urgent": urgent or 0,
            }
        }
    return {
        "run_id": run_id,
        "generated_at": generated_at,
        "campaign_summary": {},
        "writeback_preview": {},
        "writeback_results": {},
        "managed_state_drift": managed_state_drift or [],
        "rollback_preview": {},
        "campaign_history": [],
        "operator_summary": operator_summary,
        "operator_queue": [],
        "campaign_outcomes_summary": {},
    }


def _campaign_run(
    run_id: str,
    generated_at: str,
    campaign_type: str,
    *,
    mode: str = "apply",
    target: str = "github",
    label: str = "Security Review",
    action_ids: list[str] | None = None,
) -> dict:
    return {
        "run_id": run_id,
        "generated_at": generated_at,
        "campaign_type": campaign_type,
        "label": label,
        "writeback_target": target,
        "mode": mode,
        "generated_action_ids": action_ids or ["security-review-1"],
    }


def _action_run(
    run_id: str,
    generated_at: str,
    campaign_type: str,
    *,
    action_id: str = "security-review-1",
    repo_id: str = "user/RepoSecure",
    rollback_state: str = "fully-reversible",
) -> dict:
    return {
        "run_id": run_id,
        "generated_at": generated_at,
        "action_id": action_id,
        "repo_id": repo_id,
        "campaign_type": campaign_type,
        "target": "github",
        "status": "created",
        "lifecycle_state": "open",
        "reconciliation_outcome": "created",
        "closed_at": None,
        "closed_reason": None,
        "reopened_at": None,
        "drift_state": None,
        "rollback_state": rollback_state,
    }


def _report_data(**overrides) -> dict:
    data = {
        "username": "testuser",
        "generated_at": "2026-04-12T12:00:00+00:00",
        "campaign_summary": {},
        "writeback_preview": {},
        "writeback_results": {},
        "managed_state_drift": [],
        "rollback_preview": {},
        "action_runs": [],
        "campaign_history": [],
        "operator_summary": {"counts": {"blocked": 1, "urgent": 1}},
        "operator_queue": [{"repo": "RepoSecure", "suggested_campaign": "security-review"}],
        "campaign_outcomes_summary": {},
    }
    data.update(overrides)
    return data


def _bundle(report_data: dict, **history_overrides) -> dict:
    return build_action_sync_outcomes_bundle(
        report_data,
        report_data.get("operator_queue", []),
        recent_runs=history_overrides.get("recent_runs", []),
        recent_campaign_runs=history_overrides.get("recent_campaign_runs", []),
        recent_action_runs=history_overrides.get("recent_action_runs", []),
        recent_campaign_history=history_overrides.get("recent_campaign_history", []),
        recent_drift_events=history_overrides.get("recent_drift_events", []),
        recent_rollback_runs=history_overrides.get("recent_rollback_runs", []),
    )


def _outcome(bundle: dict, campaign_type: str) -> dict:
    return next(item for item in bundle["action_sync_outcomes"] if item["campaign_type"] == campaign_type)


def test_outcome_is_no_recent_apply_when_campaign_has_not_been_applied() -> None:
    bundle = _bundle(_report_data())
    outcome = _outcome(bundle, "security-review")

    assert outcome["monitoring_state"] == "no-recent-apply"
    assert outcome["pressure_effect"] == "insufficient-evidence"
    assert bundle["campaign_outcomes_summary"]["counts"]["no-recent-apply"] >= 1


def test_outcome_is_monitor_now_when_apply_is_recent() -> None:
    bundle = _bundle(
        _report_data(),
        recent_runs=[
            _run_snapshot("run-1", "2026-04-12T11:00:00+00:00", blocked=2, urgent=1),
        ],
        recent_campaign_runs=[
            _campaign_run("run-1", "2026-04-12T11:00:00+00:00", "security-review"),
        ],
        recent_action_runs=[
            _action_run("run-1", "2026-04-12T11:00:00+00:00", "security-review"),
        ],
    )
    outcome = _outcome(bundle, "security-review")

    assert outcome["monitoring_state"] == "monitor-now"
    assert outcome["pressure_effect"] == "reduced"


def test_outcome_is_holding_clean_with_two_post_apply_runs() -> None:
    bundle = _bundle(
        _report_data(),
        recent_runs=[
            _run_snapshot("run-2", "2026-04-12T11:00:00+00:00", blocked=1, urgent=0),
            _run_snapshot("run-1", "2026-04-12T10:00:00+00:00", blocked=1, urgent=0),
            _run_snapshot("run-apply", "2026-04-12T09:00:00+00:00", blocked=3, urgent=1),
        ],
        recent_campaign_runs=[
            _campaign_run("run-apply", "2026-04-12T09:00:00+00:00", "security-review"),
        ],
        recent_action_runs=[
            _action_run("run-apply", "2026-04-12T09:00:00+00:00", "security-review"),
        ],
    )
    outcome = _outcome(bundle, "security-review")

    assert outcome["monitoring_state"] == "holding-clean"
    assert outcome["pressure_effect"] == "reduced"
    assert bundle["next_monitoring_step"]["monitoring_state"] == "holding-clean"


def test_outcome_is_drift_returned_when_drift_reappears_after_apply() -> None:
    bundle = _bundle(
        _report_data(),
        recent_runs=[
            _run_snapshot("run-2", "2026-04-12T11:00:00+00:00", blocked=2, urgent=1),
            _run_snapshot("run-1", "2026-04-12T10:00:00+00:00", blocked=2, urgent=1),
            _run_snapshot("run-apply", "2026-04-12T09:00:00+00:00", blocked=2, urgent=1),
        ],
        recent_campaign_runs=[
            _campaign_run("run-apply", "2026-04-12T09:00:00+00:00", "security-review"),
        ],
        recent_action_runs=[
            _action_run("run-apply", "2026-04-12T09:00:00+00:00", "security-review"),
        ],
        recent_drift_events=[
            {
                "run_id": "run-2",
                "generated_at": "2026-04-12T11:00:00+00:00",
                "action_id": "security-review-1",
                "repo_id": "user/RepoSecure",
                "campaign_type": "security-review",
                "target": "github-issue",
                "drift_state": "managed-issue-drifted",
                "details": {},
            }
        ],
    )
    outcome = _outcome(bundle, "security-review")

    assert outcome["monitoring_state"] == "drift-returned"
    assert outcome["drift_state"] == "returned"
    assert bundle["next_monitoring_step"]["campaign_type"] == "security-review"


def test_outcome_is_reopened_when_lifecycle_reopens_after_apply() -> None:
    bundle = _bundle(
        _report_data(),
        recent_runs=[
            _run_snapshot("run-2", "2026-04-12T11:00:00+00:00", blocked=2, urgent=1),
            _run_snapshot("run-1", "2026-04-12T10:00:00+00:00", blocked=2, urgent=1),
            _run_snapshot("run-apply", "2026-04-12T09:00:00+00:00", blocked=2, urgent=1),
        ],
        recent_campaign_runs=[
            _campaign_run("run-apply", "2026-04-12T09:00:00+00:00", "security-review"),
        ],
        recent_action_runs=[
            _action_run("run-apply", "2026-04-12T09:00:00+00:00", "security-review"),
        ],
        recent_campaign_history=[
            {
                "generated_at": "2026-04-12T11:00:00+00:00",
                "campaign_type": "security-review",
                "reconciliation_outcome": "reopened",
                "reopened_at": "2026-04-12T11:00:00+00:00",
            }
        ],
    )
    outcome = _outcome(bundle, "security-review")

    assert outcome["monitoring_state"] == "reopened"
    assert outcome["reopen_state"] == "reopened"


def test_outcome_is_rollback_watch_when_rollback_gap_or_use_exists() -> None:
    partial_bundle = _bundle(
        _report_data(),
        recent_runs=[
            _run_snapshot("run-2", "2026-04-12T11:00:00+00:00", blocked=2, urgent=1),
            _run_snapshot("run-1", "2026-04-12T10:00:00+00:00", blocked=2, urgent=1),
            _run_snapshot("run-apply", "2026-04-12T09:00:00+00:00", blocked=2, urgent=1),
        ],
        recent_campaign_runs=[
            _campaign_run("run-apply", "2026-04-12T09:00:00+00:00", "security-review"),
        ],
        recent_action_runs=[
            _action_run("run-apply", "2026-04-12T09:00:00+00:00", "security-review", rollback_state="partial"),
        ],
    )
    partial_outcome = _outcome(partial_bundle, "security-review")
    assert partial_outcome["monitoring_state"] == "rollback-watch"
    assert partial_outcome["rollback_state"] == "partial"

    used_bundle = _bundle(
        _report_data(),
        recent_runs=[
            _run_snapshot("run-2", "2026-04-12T11:00:00+00:00", blocked=2, urgent=1),
            _run_snapshot("run-1", "2026-04-12T10:00:00+00:00", blocked=2, urgent=1),
            _run_snapshot("run-apply", "2026-04-12T09:00:00+00:00", blocked=2, urgent=1),
        ],
        recent_campaign_runs=[
            _campaign_run("run-apply", "2026-04-12T09:00:00+00:00", "security-review"),
        ],
        recent_action_runs=[
            _action_run("run-apply", "2026-04-12T09:00:00+00:00", "security-review"),
        ],
        recent_rollback_runs=[
            {
                "run_id": "rollback-1",
                "source_run_id": "run-apply",
                "generated_at": "2026-04-12T11:00:00+00:00",
                "preview": {},
                "results": {},
                "status": "used",
            }
        ],
    )
    used_outcome = _outcome(used_bundle, "security-review")
    assert used_outcome["monitoring_state"] == "rollback-watch"
    assert used_outcome["rollback_state"] == "used"


def test_outcome_uses_precedence_when_multiple_conditions_are_true() -> None:
    bundle = _bundle(
        _report_data(),
        recent_runs=[
            _run_snapshot("run-2", "2026-04-12T11:00:00+00:00", blocked=2, urgent=1),
            _run_snapshot("run-1", "2026-04-12T10:00:00+00:00", blocked=2, urgent=1),
            _run_snapshot("run-apply", "2026-04-12T09:00:00+00:00", blocked=2, urgent=1),
        ],
        recent_campaign_runs=[
            _campaign_run("run-apply", "2026-04-12T09:00:00+00:00", "security-review"),
        ],
        recent_action_runs=[
            _action_run("run-apply", "2026-04-12T09:00:00+00:00", "security-review", rollback_state="partial"),
        ],
        recent_campaign_history=[
            {
                "generated_at": "2026-04-12T11:00:00+00:00",
                "campaign_type": "security-review",
                "reconciliation_outcome": "reopened",
                "reopened_at": "2026-04-12T11:00:00+00:00",
            }
        ],
        recent_drift_events=[
            {
                "run_id": "run-2",
                "generated_at": "2026-04-12T11:00:00+00:00",
                "action_id": "security-review-1",
                "repo_id": "user/RepoSecure",
                "campaign_type": "security-review",
                "target": "github-issue",
                "drift_state": "managed-issue-drifted",
                "details": {},
            }
        ],
    )
    outcome = _outcome(bundle, "security-review")

    assert outcome["monitoring_state"] == "drift-returned"


def test_outcome_holds_clean_even_when_pressure_history_is_missing() -> None:
    bundle = _bundle(
        _report_data(operator_summary={}),
        recent_runs=[
            _run_snapshot("run-2", "2026-04-12T11:00:00+00:00", blocked=None, urgent=None),
            _run_snapshot("run-1", "2026-04-12T10:00:00+00:00", blocked=None, urgent=None),
            _run_snapshot("run-apply", "2026-04-12T09:00:00+00:00", blocked=None, urgent=None),
        ],
        recent_campaign_runs=[
            _campaign_run("run-apply", "2026-04-12T09:00:00+00:00", "security-review"),
        ],
        recent_action_runs=[
            _action_run("run-apply", "2026-04-12T09:00:00+00:00", "security-review"),
        ],
    )
    outcome = _outcome(bundle, "security-review")

    assert outcome["pressure_effect"] == "insufficient-evidence"
    assert outcome["monitoring_state"] == "holding-clean"


def test_outcome_returns_insufficient_evidence_when_apply_snapshot_is_missing() -> None:
    bundle = _bundle(
        _report_data(),
        recent_runs=[
            _run_snapshot("run-2", "2026-04-12T11:00:00+00:00", blocked=1, urgent=0),
            _run_snapshot("run-1", "2026-04-12T10:00:00+00:00", blocked=1, urgent=0),
        ],
        recent_campaign_runs=[
            _campaign_run("run-apply", "2026-04-12T09:00:00+00:00", "security-review"),
        ],
        recent_action_runs=[
            _action_run("run-apply", "2026-04-12T09:00:00+00:00", "security-review"),
        ],
    )
    outcome = _outcome(bundle, "security-review")

    assert outcome["monitoring_state"] == "insufficient-evidence"
    assert outcome["pressure_effect"] == "insufficient-evidence"
