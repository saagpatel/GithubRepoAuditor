from __future__ import annotations

from src.operator_trend_closure_forecast_reset_controls import (
    apply_reset_refresh_reentry_control,
    closure_forecast_reset_refresh_hotspots,
    closure_forecast_reset_refresh_recovery_for_target,
    closure_forecast_reset_refresh_recovery_summary,
)


def test_closure_forecast_reset_refresh_recovery_for_target_detects_confirmation_reentry() -> (
    None
):
    target = {
        "lane": "urgent",
        "kind": "config",
        "closure_forecast_reweight_direction": "supporting-confirmation",
        "closure_forecast_reweight_score": 0.45,
        "closure_forecast_reacquisition_freshness_status": "fresh",
        "closure_forecast_momentum_status": "sustained-confirmation",
        "closure_forecast_stability_status": "stable",
    }
    events = [
        {
            "class_key": "urgent:config",
            "closure_forecast_reweight_direction": "supporting-confirmation",
            "closure_forecast_reweight_score": 0.4,
            "closure_forecast_reacquisition_freshness_status": "fresh",
        },
        {
            "class_key": "urgent:config",
            "closure_forecast_reweight_direction": "supporting-confirmation",
            "closure_forecast_reweight_score": 0.35,
            "closure_forecast_reacquisition_freshness_status": "fresh",
        },
        {
            "class_key": "urgent:config",
            "closure_forecast_reweight_direction": "supporting-confirmation",
            "closure_forecast_reweight_score": 0.3,
            "closure_forecast_reacquisition_freshness_status": "fresh",
            "closure_forecast_persistence_reset_status": "confirmation-reset",
        },
    ]

    refresh_meta = closure_forecast_reset_refresh_recovery_for_target(
        target, events, {}
    )

    assert (
        refresh_meta["closure_forecast_reset_refresh_recovery_status"]
        == "reentering-confirmation"
    )
    assert (
        refresh_meta["closure_forecast_reset_reentry_status"]
        == "reentered-confirmation"
    )


def test_apply_reset_refresh_reentry_control_softens_confirmation_when_blocked() -> (
    None
):
    updates = apply_reset_refresh_reentry_control(
        {
            "closure_forecast_reacquisition_age_runs": 2,
            "closure_forecast_reacquisition_persistence_score": 0.2,
            "closure_forecast_reacquisition_persistence_status": "holding-confirmation",
            "closure_forecast_reacquisition_persistence_reason": "holding",
            "closure_forecast_reacquisition_freshness_status": "fresh",
            "closure_forecast_stability_status": "stable",
        },
        refresh_meta={
            "closure_forecast_reset_refresh_recovery_status": "blocked",
            "closure_forecast_reset_reentry_status": "blocked",
            "closure_forecast_reset_reentry_reason": "Local noise is blocking re-entry.",
            "recent_reset_side": "confirmation",
        },
        transition_history_meta={},
        closure_likely_outcome="confirm-soon",
        closure_hysteresis_status="confirmed-confirmation",
        closure_hysteresis_reason="",
        transition_status="pending-support",
        transition_reason="",
        resolution_status="none",
        resolution_reason="",
        reacquisition_status="reacquired-confirmation",
        reacquisition_reason="",
    )

    assert updates["transition_closure_likely_outcome"] == "hold"
    assert updates["closure_forecast_hysteresis_status"] == "pending-confirmation"
    assert (
        updates["closure_forecast_reacquisition_status"]
        == "pending-confirmation-reacquisition"
    )


def test_closure_forecast_reset_refresh_hotspots_and_summary_track_active_classes() -> (
    None
):
    hotspots = closure_forecast_reset_refresh_hotspots(
        [
            {
                "lane": "urgent",
                "kind": "config",
                "closure_forecast_reset_refresh_recovery_score": 0.28,
                "closure_forecast_reset_refresh_recovery_status": "reentering-confirmation",
                "closure_forecast_reset_reentry_status": "pending-confirmation-reentry",
            },
            {
                "lane": "blocked",
                "kind": "setup",
                "closure_forecast_reset_refresh_recovery_score": -0.33,
                "closure_forecast_reset_refresh_recovery_status": "reentering-clearance",
                "closure_forecast_reset_reentry_status": "reentered-clearance",
            },
        ],
        mode="clearance",
    )

    summary = closure_forecast_reset_refresh_recovery_summary(
        {
            "title": "RepoC",
            "closure_forecast_reset_refresh_recovery_status": "recovering-confirmation-reset",
            "closure_forecast_reset_refresh_recovery_score": 0.18,
        },
        recovering_confirmation_hotspots=[],
        recovering_clearance_hotspots=hotspots,
    )

    assert hotspots[0]["label"] == "blocked:setup"
    assert "RepoC" in summary
