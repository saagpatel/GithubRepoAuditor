from __future__ import annotations

from src.operator_trend_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence import (
    apply_reset_reentry_rebuild_reentry_restore_rererestore_persistence_and_churn,
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_hotspots,
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_for_target,
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_summary,
)


def _target_class_key(item: dict) -> str:
    return f"{item.get('lane', '')}:{item.get('kind', '') or 'unknown'}"


def _target_label(item: dict) -> str:
    return item.get("title", "") or item.get("kind", "") or "target"


def test_rererestore_persistence_for_target_keeps_status_and_text() -> None:
    meta = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_for_target(
            {
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": (
                    "rererestored-confirmation-rebuild-reentry"
                ),
            },
            [],
            {},
            ordered_reset_reentry_events_for_target=lambda _target, _events: [
                {
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": (
                        "rererestored-confirmation-rebuild-reentry"
                    )
                }
            ],
            closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_event=(
                lambda _event: "confirmation"
            ),
            closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_path_label=(
                lambda _event: "rererestored-confirmation-rebuild-reentry"
            ),
            closure_forecast_direction_majority=lambda _directions: "neutral",
            closure_forecast_direction_reversing=lambda _current, _earlier: False,
            clamp_round=lambda value, **_kwargs: float(value),
            class_reset_reentry_rebuild_reentry_restore_rererestore_window_runs=4,
        )
    )

    assert (
        meta[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status"
        ]
        == "just-rererestored"
    )
    assert "has been re-re-restored" in meta[
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason"
    ]
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
            target_class_key=_target_class_key,
        )
    )
    holding_hotspots = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_hotspots(
            targets,
            mode="holding",
            target_class_key=_target_class_key,
        )
    )
    summary = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_summary(
            targets[0],
            just_hotspots,
            holding_hotspots,
            target_label=_target_label,
        )
    )

    assert just_hotspots[0]["label"] == "blocked:setup"
    assert holding_hotspots[0]["label"] == "urgent:review"
    assert "RepoA" in summary


def test_rererestore_apply_returns_empty_defaults_without_targets() -> None:
    summary = apply_reset_reentry_rebuild_reentry_restore_rererestore_persistence_and_churn(
        [],
        [],
        current_generated_at="2026-04-17T00:00:00Z",
        confidence_calibration={},
        recommendation_bucket=lambda _target: "focus",
        class_closure_forecast_events=lambda *_args, **_kwargs: [],
        class_transition_events=lambda *_args, **_kwargs: [],
        target_class_transition_history=lambda _target, _events: {},
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_for_target=(
            lambda _target, _events, _history: {}
        ),
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_for_target=(
            lambda _target, _events, _history: {}
        ),
        apply_reset_reentry_rebuild_reentry_restore_rererestore_persistence_and_churn_control=(
            lambda *_args, **_kwargs: {}
        ),
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_hotspots=(
            lambda *_args, **_kwargs: []
        ),
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_summary=(
            lambda *_args, **_kwargs: ""
        ),
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_summary=(
            lambda *_args, **_kwargs: ""
        ),
        class_reset_reentry_rebuild_reentry_restore_rererestore_window_runs=4,
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
