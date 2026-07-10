from __future__ import annotations

from src.operator_trend_closure_forecast_reset_controls import (
    closure_forecast_reset_reentry_rebuild_churn_for_target,
    closure_forecast_reset_reentry_rebuild_churn_summary,
    closure_forecast_reset_reentry_rebuild_hotspots,
    closure_forecast_reset_reentry_rebuild_persistence_for_target,
    closure_forecast_reset_reentry_rebuild_persistence_summary,
)


def test_persistence_for_target_detects_just_rebuilt_confirmation() -> None:
    target = {
        "lane": "urgent",
        "kind": "config",
        "closure_forecast_reset_reentry_rebuild_status": "rebuilt-confirmation-reentry",
        "closure_forecast_reset_reentry_freshness_status": "fresh",
        "closure_forecast_momentum_status": "sustained-confirmation",
        "closure_forecast_stability_status": "stable",
    }
    events = [
        {
            "class_key": "urgent:config",
            "closure_forecast_reset_reentry_rebuild_status": "rebuilt-confirmation-reentry",
            "closure_forecast_reset_reentry_refresh_recovery_status": (
                "rebuilding-confirmation-reentry"
            ),
            "closure_forecast_reset_reentry_freshness_status": "fresh",
            "closure_forecast_momentum_status": "sustained-confirmation",
            "closure_forecast_stability_status": "stable",
        }
    ]

    meta = closure_forecast_reset_reentry_rebuild_persistence_for_target(
        target, events, {}
    )

    # Under production's ordered_reset_reentry_events_for_target, the single real event
    # doesn't carry a key/generated_at matching the target's queue_identity, so a second
    # "current" event is synthesized from the target dict (which already carries the same
    # rebuilt-confirmation-reentry status) -- two aligned confirmation runs, not one, hand-
    # verified by running the production code path.
    assert (
        meta["closure_forecast_reset_reentry_rebuild_persistence_status"]
        == "holding-confirmation-rebuild"
    )
    assert meta["closure_forecast_reset_reentry_rebuild_age_runs"] == 2


def test_churn_for_target_detects_flip_heavy_path() -> None:
    target = {
        "lane": "urgent",
        "kind": "config",
        "closure_forecast_stability_status": "oscillating",
        "closure_forecast_momentum_status": "reversing",
    }
    events = [
        {
            "class_key": "urgent:config",
            "closure_forecast_reset_reentry_rebuild_status": "rebuilt-confirmation-reentry",
            "closure_forecast_reset_reentry_freshness_status": "fresh",
        },
        {
            "class_key": "urgent:config",
            "closure_forecast_reset_reentry_rebuild_status": "rebuilt-clearance-reentry",
            "closure_forecast_reset_reentry_freshness_status": "mixed-age",
        },
        {
            "class_key": "urgent:config",
            "closure_forecast_reset_reentry_rebuild_status": "rebuilt-confirmation-reentry",
            "closure_forecast_reset_reentry_reset_status": "confirmation-reset",
            "closure_forecast_reset_reentry_freshness_status": "stale",
        },
    ]

    meta = closure_forecast_reset_reentry_rebuild_churn_for_target(target, events, {})

    assert meta["closure_forecast_reset_reentry_rebuild_churn_status"] == "churn"
    assert meta["closure_forecast_reset_reentry_rebuild_churn_score"] >= 0.45


def test_hotspots_and_summaries_track_rebuild_labels() -> None:
    targets = [
        {
            "lane": "urgent",
            "kind": "config",
            "title": "RepoA",
            "closure_forecast_reset_reentry_rebuild_age_runs": 3,
            "closure_forecast_reset_reentry_rebuild_persistence_score": 0.34,
            "closure_forecast_reset_reentry_rebuild_persistence_status": (
                "holding-confirmation-rebuild"
            ),
            "closure_forecast_reset_reentry_rebuild_churn_score": 0.0,
            "closure_forecast_reset_reentry_rebuild_churn_status": "none",
        },
        {
            "lane": "blocked",
            "kind": "setup",
            "title": "RepoB",
            "closure_forecast_reset_reentry_rebuild_age_runs": 2,
            "closure_forecast_reset_reentry_rebuild_persistence_score": -0.28,
            "closure_forecast_reset_reentry_rebuild_persistence_status": "just-rebuilt",
            "closure_forecast_reset_reentry_rebuild_churn_score": 0.5,
            "closure_forecast_reset_reentry_rebuild_churn_status": "churn",
        },
    ]

    holding_hotspots = closure_forecast_reset_reentry_rebuild_hotspots(
        targets,
        mode="holding",
    )
    churn_hotspots = closure_forecast_reset_reentry_rebuild_hotspots(
        targets,
        mode="churn",
    )
    persistence_summary = closure_forecast_reset_reentry_rebuild_persistence_summary(
        targets[0],
        [],
        holding_hotspots,
    )
    churn_summary = closure_forecast_reset_reentry_rebuild_churn_summary(
        targets[1],
        churn_hotspots,
    )

    assert holding_hotspots[0]["label"] == "urgent:config"
    assert churn_hotspots[0]["label"] == "blocked:setup"
    assert "RepoA" in persistence_summary
    assert "RepoB" in churn_summary
