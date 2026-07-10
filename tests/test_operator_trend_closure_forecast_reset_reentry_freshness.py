from __future__ import annotations

from src.operator_trend_closure_forecast_reset_controls import (
    apply_reset_reentry_freshness_reset_control,
    closure_forecast_reset_reentry_freshness_for_target,
    closure_forecast_reset_reentry_freshness_hotspots,
    closure_forecast_reset_reentry_freshness_summary,
    closure_forecast_reset_reentry_reset_summary,
)


def test_closure_forecast_reset_reentry_freshness_for_target_reports_fresh_signal() -> (
    None
):
    target = {
        "lane": "urgent",
        "kind": "config",
        "closure_forecast_reset_reentry_status": "reentered-confirmation",
        "closure_forecast_reset_reentry_persistence_status": "holding-confirmation-reentry",
    }
    events = [
        {
            "class_key": "urgent:config",
            "closure_forecast_reset_reentry_status": "reentered-confirmation",
            "closure_forecast_reset_reentry_persistence_status": "holding-confirmation-reentry",
            "closure_forecast_reacquisition_freshness_status": "fresh",
        },
        {
            "class_key": "urgent:config",
            "closure_forecast_reset_reentry_status": "pending-confirmation-reentry",
            "transition_closure_likely_outcome": "confirm-soon",
            "closure_forecast_reacquisition_freshness_status": "fresh",
        },
        {
            "class_key": "urgent:config",
            "closure_forecast_reset_reentry_status": "pending-clearance-reentry",
            "transition_closure_likely_outcome": "clear-risk",
            "closure_forecast_reacquisition_freshness_status": "mixed-age",
        },
    ]

    freshness_meta = closure_forecast_reset_reentry_freshness_for_target(target, events)

    assert freshness_meta["closure_forecast_reset_reentry_freshness_status"] == "fresh"
    # 0.74 under the real production CLASS_RESET_REENTRY_FRESHNESS_WINDOW_RUNS/
    # CLASS_MEMORY_RECENCY_WEIGHTS (wider than the old 2-run/4-weight test stand-ins),
    # hand-verified by running the production code path.
    assert freshness_meta["closure_forecast_reset_reentry_memory_weight"] == 0.74
    assert freshness_meta["has_fresh_aligned_recent_evidence"] is True


def test_apply_reset_reentry_freshness_reset_control_resets_clearance_when_aged_out() -> (
    None
):
    updates = apply_reset_reentry_freshness_reset_control(
        {
            "closure_forecast_reset_reentry_churn_status": "churn",
        },
        freshness_meta={
            "closure_forecast_reset_reentry_freshness_status": "stale",
            "decayed_reset_reentered_clearance_rate": 0.3,
            "has_fresh_aligned_recent_evidence": False,
        },
        transition_history_meta={"recent_pending_status": "pending-caution"},
        closure_likely_outcome="clear-risk",
        closure_hysteresis_status="confirmed-clearance",
        closure_hysteresis_reason="",
        transition_status="none",
        transition_reason="",
        resolution_status="cleared",
        resolution_reason="",
        reacquisition_status="reacquired-clearance",
        reacquisition_reason="",
        reentry_status="reentered-clearance",
        reentry_reason="",
        persistence_age_runs=3,
        persistence_score=-0.4,
        persistence_status="sustained-clearance-reentry",
        persistence_reason="",
    )

    assert updates["closure_forecast_reset_reentry_reset_status"] == "clearance-reset"
    assert updates["transition_closure_likely_outcome"] == "hold"
    assert updates["closure_forecast_reacquisition_status"] == "none"


def test_closure_forecast_reset_reentry_freshness_hotspots_and_summaries_track_classes() -> (
    None
):
    targets = [
        {
            "lane": "urgent",
            "kind": "config",
            "closure_forecast_reset_reentry_freshness_status": "fresh",
            "decayed_reset_reentered_confirmation_rate": 0.8,
            "decayed_reset_reentered_clearance_rate": 0.1,
            "recent_reset_reentry_persistence_path": (
                "holding-confirmation-reentry -> holding-confirmation-reentry"
            ),
        },
        {
            "lane": "blocked",
            "kind": "setup",
            "closure_forecast_reset_reentry_freshness_status": "stale",
            "decayed_reset_reentered_confirmation_rate": 0.1,
            "decayed_reset_reentered_clearance_rate": 0.7,
            "recent_reset_reentry_persistence_path": (
                "holding-clearance-reentry -> holding-clearance-reentry"
            ),
        },
    ]

    stale_hotspots = closure_forecast_reset_reentry_freshness_hotspots(
        targets,
        mode="stale",
    )
    fresh_hotspots = closure_forecast_reset_reentry_freshness_hotspots(
        targets,
        mode="fresh",
    )
    freshness_summary = closure_forecast_reset_reentry_freshness_summary(
        {
            "title": "RepoC",
            "closure_forecast_reset_reentry_freshness_status": "mixed-age",
        },
        stale_hotspots,
        fresh_hotspots,
    )
    reset_summary = closure_forecast_reset_reentry_reset_summary(
        {
            "title": "RepoC",
            "closure_forecast_reset_reentry_reset_status": "none",
            "closure_forecast_reset_reentry_freshness_status": "mixed-age",
            "decayed_reset_reentered_confirmation_rate": 0.6,
            "decayed_reset_reentered_clearance_rate": 0.2,
        },
        stale_hotspots,
        fresh_hotspots,
    )

    assert stale_hotspots[0]["label"] == "blocked:setup"
    assert fresh_hotspots[0]["label"] == "urgent:config"
    assert "RepoC" in freshness_summary
    assert "RepoC" in reset_summary
