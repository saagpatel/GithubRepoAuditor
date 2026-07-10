from __future__ import annotations

from src.operator_trend_closure_forecast_reset_controls import (
    apply_reset_reentry_rebuild_reentry_restore_rererestore_persistence_and_churn,
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_hotspots,
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_for_target,
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_summary,
)
from src.operator_trend_support import current_closure_forecast_event_for_target


def test_rererestore_persistence_uses_synthesized_current_event() -> None:
    target = {
        "lane": "urgent",
        "kind": "review",
        "item_id": "T-synthesized",
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": (
            "rererestored-confirmation-rebuild-reentry"
        ),
    }

    event = current_closure_forecast_event_for_target(target)
    meta = closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_for_target(
        target, [], {}
    )

    assert (
        event[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status"
        ]
        == "rererestored-confirmation-rebuild-reentry"
    )
    assert (
        meta[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status"
        ]
        == "just-rererestored"
    )


def test_rererestore_persistence_for_target_keeps_status_and_text() -> None:
    # `item_id`/`key`/`generated_at` line up so ordered_reset_reentry_events_for_target's
    # current_index==0 shortcut fires and returns this one event unchanged (no synthesized
    # "current" event); the target's own settled status + a single aligned run drives the
    # base builder's "just-*" branch, matching the original stand-in's scripted intent.
    target = {
        "lane": "urgent",
        "kind": "review",
        "item_id": "T1",
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": (
            "rererestored-confirmation-rebuild-reentry"
        ),
    }
    event = {
        "class_key": "urgent:review",
        "key": "T1",
        "generated_at": "",
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": (
            "rererestored-confirmation-rebuild-reentry"
        ),
    }

    meta = closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_for_target(
        target, [event], {}
    )

    assert (
        meta[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status"
        ]
        == "just-rererestored"
    )
    assert (
        "has been re-re-restored"
        in meta[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason"
        ]
    )
    assert (
        meta[
            "recent_reset_reentry_rebuild_reentry_restore_rererestore_persistence_path"
        ]
        == "rererestored-confirmation-rebuild-reentry"
    )


def test_rererestore_hotspots_and_summary_use_labels() -> None:
    targets = [
        {
            "lane": "urgent",
            "kind": "review",
            "title": "RepoA",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs": 2,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score": 0.34,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": (
                "holding-confirmation-rebuild-reentry-rererestore"
            ),
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_score": 0.0,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status": "none",
        },
        {
            "lane": "blocked",
            "kind": "setup",
            "title": "RepoB",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs": 1,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score": 0.19,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": (
                "just-rererestored"
            ),
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_score": 0.22,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status": "watch",
        },
    ]

    just_hotspots = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_hotspots(
            targets,
            mode="just-rererestored",
        )
    )
    holding_hotspots = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_hotspots(
            targets,
            mode="holding",
        )
    )
    summary = closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_summary(
        targets[0],
        just_hotspots,
        holding_hotspots,
    )

    assert just_hotspots[0]["label"] == "blocked:setup"
    assert holding_hotspots[0]["label"] == "urgent:review"
    assert "RepoA" in summary


def test_rererestore_apply_returns_empty_defaults_without_targets() -> None:
    summary = (
        apply_reset_reentry_rebuild_reentry_restore_rererestore_persistence_and_churn(
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
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status"
        ]
        == "none"
    )
    assert (
        summary[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_window_runs"
        ]
        == 4
    )
