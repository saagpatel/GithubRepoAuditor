from __future__ import annotations

from src.operator_trend_closure_forecast_reset_controls import (
    apply_reset_reentry_rebuild_reentry_restore_rererestore_freshness_and_reset,
    apply_reset_reentry_rebuild_reentry_restore_rererestore_freshness_reset_control,
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_for_target,
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_hotspots,
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_summary,
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_summary,
)


def test_rererestore_freshness_for_target_detects_fresh_confirmation_signal() -> None:
    target = {
        "lane": "urgent",
        "kind": "review",
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": (
            "rererestored-confirmation-rebuild-reentry"
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": (
            "sustained-confirmation-rebuild-reentry-rererestore"
        ),
    }
    events = [
        {
            "class_key": "urgent:review",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": (
                "rererestored-confirmation-rebuild-reentry"
            ),
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": (
                "holding-confirmation-rebuild-reentry-rererestore"
            ),
        },
        {
            "class_key": "urgent:review",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": (
                "pending-confirmation-rebuild-reentry-rererestore"
            ),
        },
    ]

    meta = closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_for_target(
        target, events
    )

    assert (
        meta[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status"
        ]
        == "fresh"
    )
    assert meta["has_fresh_aligned_recent_evidence"] is True


def test_rererestore_reset_control_softens_mixed_age_confirmation_signal() -> None:
    updates = apply_reset_reentry_rebuild_reentry_restore_rererestore_freshness_reset_control(
        {
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status": "watch"
        },
        freshness_meta={
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status": "mixed-age",
            "has_fresh_aligned_recent_evidence": True,
        },
        transition_history_meta={},
        closure_likely_outcome="confirm-soon",
        closure_hysteresis_status="confirmed-confirmation",
        closure_hysteresis_reason="",
        transition_status="supporting-confirmation",
        transition_reason="",
        resolution_status="none",
        resolution_reason="",
        reentry_status="reentered-confirmation",
        reentry_reason="",
        restore_status="restored-confirmation-rebuild-reentry",
        restore_reason="",
        rerestore_status="rererestored-confirmation-rebuild-reentry",
        rerestore_reason="",
        rererestore_status="none",
        rererestore_reason="",
        persistence_age_runs=3,
        persistence_score=0.62,
        persistence_status="sustained-confirmation-rebuild-reentry-rererestore",
        persistence_reason="",
    )

    assert (
        updates[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status"
        ]
        == "confirmation-softened"
    )


def test_rererestore_freshness_hotspots_and_summaries_use_labels() -> None:
    targets = [
        {
            "lane": "urgent",
            "kind": "review",
            "title": "RepoA",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status": "stale",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status": "confirmation-reset",
            "decayed_rererestored_rebuild_reentry_confirmation_rate": 0.7,
            "decayed_rererestored_rebuild_reentry_clearance_rate": 0.1,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs": 3,
        },
        {
            "lane": "blocked",
            "kind": "setup",
            "title": "RepoB",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status": "fresh",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status": "none",
            "decayed_rererestored_rebuild_reentry_confirmation_rate": 0.2,
            "decayed_rererestored_rebuild_reentry_clearance_rate": 0.8,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs": 2,
        },
    ]

    stale_hotspots = closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_hotspots(
        targets,
        mode="stale",
    )
    fresh_hotspots = closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_hotspots(
        targets,
        mode="fresh",
    )
    freshness_summary = closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_summary(
        targets[0],
        stale_hotspots,
        fresh_hotspots,
    )
    reset_summary = closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_summary(
        targets[0],
        stale_hotspots,
        fresh_hotspots,
    )

    assert stale_hotspots[0]["label"] == "urgent:review"
    assert fresh_hotspots[0]["label"] == "blocked:setup"
    assert "RepoA" in freshness_summary
    assert "RepoA" in reset_summary


def test_rererestore_freshness_apply_returns_empty_defaults_without_targets() -> None:
    summary = (
        apply_reset_reentry_rebuild_reentry_restore_rererestore_freshness_and_reset(
            [],
            [],
            current_generated_at="2026-04-17T00:00:00Z",
            confidence_calibration={},
            class_closure_forecast_events=lambda *_args, **_kwargs: [],
            class_transition_events=lambda *_args, **_kwargs: [],
            target_class_transition_history=lambda _target, _events: {},
        )
    )

    assert (
        summary[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status"
        ]
        == "insufficient-data"
    )
    assert (
        summary[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_decay_window_runs"
        ]
        == 4
    )
