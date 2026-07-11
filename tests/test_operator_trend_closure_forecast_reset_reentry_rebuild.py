from __future__ import annotations

from src.operator_trend_closure_forecast_reset_controls import (
    apply_reset_reentry_refresh_rebuild_control,
    closure_forecast_reset_reentry_rebuild_summary,
    closure_forecast_reset_reentry_refresh_hotspots,
    closure_forecast_reset_reentry_refresh_recovery_for_target,
    closure_forecast_reset_reentry_refresh_recovery_summary,
)


def test_refresh_recovery_for_target_detects_confirmation_rebuild() -> None:
    target = {
        "lane": "urgent",
        "kind": "config",
        "closure_forecast_reweight_direction": "supporting-confirmation",
        "closure_forecast_reweight_score": 0.42,
        "closure_forecast_reset_reentry_freshness_status": "fresh",
        "closure_forecast_momentum_status": "sustained-confirmation",
        "closure_forecast_stability_status": "stable",
    }
    events = [
        {
            "class_key": "urgent:config",
            "closure_forecast_reweight_direction": "supporting-confirmation",
            "closure_forecast_reweight_score": 0.36,
            "closure_forecast_reset_reentry_freshness_status": "fresh",
        },
        {
            "class_key": "urgent:config",
            "closure_forecast_reweight_direction": "supporting-confirmation",
            "closure_forecast_reweight_score": 0.32,
            "closure_forecast_reset_reentry_freshness_status": "fresh",
        },
        {
            "class_key": "urgent:config",
            "closure_forecast_reset_reentry_reset_status": "confirmation-reset",
            "closure_forecast_reweight_direction": "supporting-confirmation",
            "closure_forecast_reweight_score": 0.28,
            "closure_forecast_reset_reentry_freshness_status": "fresh",
        },
    ]

    refresh_meta = closure_forecast_reset_reentry_refresh_recovery_for_target(
        target, events, {}
    )

    assert (
        refresh_meta["closure_forecast_reset_reentry_refresh_recovery_status"]
        == "rebuilding-confirmation-reentry"
    )
    assert (
        refresh_meta["closure_forecast_reset_reentry_rebuild_status"]
        == "rebuilt-confirmation-reentry"
    )


def test_apply_reset_reentry_refresh_rebuild_control_softens_to_pending() -> None:
    updates = apply_reset_reentry_refresh_rebuild_control(
        {
            "closure_forecast_reset_reentry_freshness_status": "fresh",
            "closure_forecast_stability_status": "stable",
            "class_transition_age_runs": 1,
            "decayed_reset_reentered_clearance_rate": 0.0,
        },
        refresh_meta={
            "closure_forecast_reset_reentry_refresh_recovery_status": (
                "recovering-confirmation-reentry-reset"
            ),
            "closure_forecast_reset_reentry_rebuild_status": "pending-confirmation-rebuild",
            "closure_forecast_reset_reentry_rebuild_reason": "rebuilding",
            "recent_reset_reentry_side": "confirmation",
        },
        transition_history_meta={},
        closure_likely_outcome="hold",
        closure_hysteresis_status="pending-confirmation",
        closure_hysteresis_reason="",
        transition_status="pending-support",
        transition_reason="",
        resolution_status="none",
        resolution_reason="",
        reacquisition_status="none",
        reacquisition_reason="",
        reentry_status="none",
        reentry_reason="",
        persistence_age_runs=0,
        persistence_score=0.0,
        persistence_status="none",
        persistence_reason="",
    )

    assert (
        updates["closure_forecast_reacquisition_status"]
        == "pending-confirmation-reacquisition"
    )
    assert (
        updates["closure_forecast_reset_reentry_status"]
        == "pending-confirmation-reentry"
    )


def test_refresh_hotspots_and_summaries_track_active_classes() -> None:
    hotspots = closure_forecast_reset_reentry_refresh_hotspots(
        [
            {
                "lane": "urgent",
                "kind": "config",
                "closure_forecast_reset_reentry_refresh_recovery_score": 0.31,
                "closure_forecast_reset_reentry_refresh_recovery_status": (
                    "rebuilding-confirmation-reentry"
                ),
                "recent_reset_reentry_refresh_path": "confirmation-reset -> fresh confirmation",
            },
            {
                "lane": "blocked",
                "kind": "setup",
                "closure_forecast_reset_reentry_refresh_recovery_score": -0.27,
                "closure_forecast_reset_reentry_refresh_recovery_status": (
                    "recovering-clearance-reentry-reset"
                ),
                "recent_reset_reentry_refresh_path": "clearance-reset -> fresh clearance",
            },
        ],
        mode="confirmation",
    )
    refresh_summary = closure_forecast_reset_reentry_refresh_recovery_summary(
        {
            "title": "RepoC",
            "closure_forecast_reset_reentry_refresh_recovery_status": (
                "recovering-confirmation-reentry-reset"
            ),
            "closure_forecast_reset_reentry_refresh_recovery_score": 0.18,
        },
        hotspots,
        [],
    )
    rebuild_summary = closure_forecast_reset_reentry_rebuild_summary(
        {
            "title": "RepoC",
            "closure_forecast_reset_reentry_rebuild_status": "pending-confirmation-rebuild",
        },
        hotspots,
        [],
    )

    assert hotspots[0]["label"] == "urgent:config"
    assert "RepoC" in refresh_summary
    assert "RepoC" in rebuild_summary
