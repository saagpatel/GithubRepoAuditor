from __future__ import annotations

from src.operator_trend_closure_forecast_reset_controls import (
    apply_reset_reentry_rebuild_freshness_reset_control,
    closure_forecast_reset_reentry_rebuild_freshness_for_target,
    closure_forecast_reset_reentry_rebuild_freshness_hotspots,
    closure_forecast_reset_reentry_rebuild_freshness_summary,
    closure_forecast_reset_reentry_rebuild_reset_summary,
)


def test_rebuild_freshness_for_target_detects_fresh_confirmation_signal() -> None:
    target = {
        "lane": "urgent",
        "kind": "review",
        "closure_forecast_reset_reentry_rebuild_status": "rebuilt-confirmation-reentry",
        "closure_forecast_reset_reentry_rebuild_persistence_status": "holding-confirmation-rebuild",
    }
    events = [
        {
            "class_key": "urgent:review",
            "closure_forecast_reset_reentry_rebuild_status": "rebuilt-confirmation-reentry",
            "closure_forecast_reset_reentry_rebuild_persistence_status": "holding-confirmation-rebuild",
            "closure_forecast_hysteresis_status": "confirmed-confirmation",
            "transition_closure_likely_outcome": "confirm-soon",
        },
        {
            "class_key": "urgent:review",
            "closure_forecast_reset_reentry_rebuild_status": "rebuilt-confirmation-reentry",
            "closure_forecast_reset_reentry_rebuild_persistence_status": "holding-confirmation-rebuild",
            "closure_forecast_hysteresis_status": "pending-confirmation",
            "transition_closure_likely_outcome": "confirm-soon",
        },
    ]

    meta = closure_forecast_reset_reentry_rebuild_freshness_for_target(target, events)

    assert meta["closure_forecast_reset_reentry_rebuild_freshness_status"] == "fresh"
    assert meta["decayed_rebuilt_confirmation_reentry_rate"] > 0.8


def test_rebuild_freshness_reset_control_softens_sustained_confirmation() -> None:
    updates = apply_reset_reentry_rebuild_freshness_reset_control(
        {
            "closure_forecast_reset_reentry_rebuild_churn_status": "watch",
        },
        freshness_meta={
            "closure_forecast_reset_reentry_rebuild_freshness_status": "mixed-age",
            "decayed_rebuilt_clearance_reentry_rate": 0.1,
            "has_fresh_aligned_recent_evidence": True,
        },
        transition_history_meta={"recent_pending_status": "pending-support"},
        closure_likely_outcome="hold",
        closure_hysteresis_status="confirmed-confirmation",
        closure_hysteresis_reason="",
        transition_status="pending-support",
        transition_reason="",
        resolution_status="none",
        resolution_reason="",
        rebuild_status="rebuilt-confirmation-reentry",
        rebuild_reason="rebuilt",
        persistence_age_runs=3,
        persistence_score=0.42,
        persistence_status="sustained-confirmation-rebuild",
        persistence_reason="stable",
    )

    assert (
        updates["closure_forecast_reset_reentry_rebuild_reset_status"]
        == "confirmation-softened"
    )
    assert (
        updates["closure_forecast_reset_reentry_rebuild_persistence_status"]
        == "holding-confirmation-rebuild"
    )


def test_rebuild_freshness_hotspots_and_summaries_track_labels() -> None:
    targets = [
        {
            "lane": "urgent",
            "kind": "review",
            "title": "RepoA",
            "closure_forecast_reset_reentry_rebuild_freshness_status": "fresh",
            "decayed_rebuilt_confirmation_reentry_rate": 0.9,
            "decayed_rebuilt_clearance_reentry_rate": 0.1,
            "recent_reset_reentry_rebuild_persistence_path": "rebuilt-confirmation-reentry -> hold",
            "closure_forecast_reset_reentry_rebuild_reset_status": "none",
        },
        {
            "lane": "blocked",
            "kind": "setup",
            "title": "RepoB",
            "closure_forecast_reset_reentry_rebuild_freshness_status": "stale",
            "decayed_rebuilt_confirmation_reentry_rate": 0.1,
            "decayed_rebuilt_clearance_reentry_rate": 0.7,
            "recent_reset_reentry_rebuild_persistence_path": "rebuilt-clearance-reentry -> hold",
            "closure_forecast_reset_reentry_rebuild_reset_status": "clearance-reset",
        },
    ]

    fresh_hotspots = closure_forecast_reset_reentry_rebuild_freshness_hotspots(
        targets,
        mode="fresh",
    )
    stale_hotspots = closure_forecast_reset_reentry_rebuild_freshness_hotspots(
        targets,
        mode="stale",
    )
    freshness_summary = closure_forecast_reset_reentry_rebuild_freshness_summary(
        targets[0],
        stale_hotspots,
        fresh_hotspots,
    )
    reset_summary = closure_forecast_reset_reentry_rebuild_reset_summary(
        targets[1],
        stale_hotspots,
        fresh_hotspots,
    )

    assert fresh_hotspots[0]["label"] == "urgent:review"
    assert stale_hotspots[0]["label"] == "blocked:setup"
    assert "RepoA" in freshness_summary
    assert "RepoB" in reset_summary
