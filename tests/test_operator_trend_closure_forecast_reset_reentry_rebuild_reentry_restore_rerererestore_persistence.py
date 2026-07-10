from __future__ import annotations

from src.operator_trend_closure_forecast_reset_controls import (
    apply_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_and_churn,
    closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_hotspots,
    closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_for_target,
    closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_summary,
)


def test_rerererestore_persistence_for_target_translates_status_and_text() -> None:
    # This wrapper translates rerererestore-vocab target/events down a tier and delegates
    # to the real rererestore persistence builder (no longer an injected stand-in), then
    # translates the result back up. Two aligned confirmation runs -- one with `key`/
    # `generated_at` matching the target's queue_identity so
    # ordered_reset_reentry_events_for_target's current_index==0 shortcut fires -- drive
    # the shared base builder's "holding" branch, hand-verified against the real code path.
    target = {
        "lane": "urgent",
        "kind": "review",
        "item_id": "T1",
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status": (
            "rerererestored-confirmation-rebuild-reentry"
        ),
    }
    events = [
        {
            "class_key": "urgent:review",
            "key": "T1",
            "generated_at": "",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status": (
                "rerererestored-confirmation-rebuild-reentry"
            ),
        },
        {
            "class_key": "urgent:review",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status": (
                "rerererestored-confirmation-rebuild-reentry"
            ),
        },
    ]

    meta = closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_for_target(
        target, events, {}
    )

    assert (
        meta[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status"
        ]
        == "holding-confirmation-rebuild-reentry-rerererestore"
    )
    assert (
        "re-re-re-restored posture"
        in meta[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_reason"
        ]
    )
    assert (
        meta[
            "recent_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_path"
        ]
        == "rerererestored-confirmation-rebuild-reentry -> rerererestored-confirmation-rebuild-reentry"
    )


def test_rerererestore_hotspots_and_summary_use_labels() -> None:
    targets = [
        {
            "lane": "urgent",
            "kind": "review",
            "title": "RepoA",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs": 2,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score": 0.34,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status": (
                "holding-confirmation-rebuild-reentry-rerererestore"
            ),
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score": 0.0,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status": "none",
        },
        {
            "lane": "blocked",
            "kind": "setup",
            "title": "RepoB",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs": 1,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score": 0.19,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status": (
                "just-rerererestored"
            ),
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score": 0.22,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status": "watch",
        },
    ]

    just_hotspots = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_hotspots(
            targets,
            mode="just-rerererestored",
        )
    )
    holding_hotspots = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_hotspots(
            targets,
            mode="holding",
        )
    )
    summary = closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_summary(
        targets[0],
        just_hotspots,
        holding_hotspots,
    )

    assert just_hotspots[0]["label"] == "blocked:setup"
    assert holding_hotspots[0]["label"] == "urgent:review"
    assert "RepoA" in summary


def test_rerererestore_apply_returns_empty_defaults_without_targets() -> None:
    summary = (
        apply_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_and_churn(
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
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status"
        ]
        == "none"
    )
    assert (
        summary[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_window_runs"
        ]
        == 4
    )
