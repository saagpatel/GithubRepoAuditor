from __future__ import annotations

from src.operator_trend_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness import (
    apply_reset_reentry_rebuild_reentry_restore_rererestore_freshness_and_reset,
    apply_reset_reentry_rebuild_reentry_restore_rererestore_freshness_reset_control,
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_for_target,
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_hotspots,
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_summary,
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_summary,
)


def _target_class_key(item: dict) -> str:
    return f"{item.get('lane', '')}:{item.get('kind', '') or 'unknown'}"


def _side_from_status(status: str) -> str:
    if "confirmation" in status:
        return "confirmation"
    if "clearance" in status:
        return "clearance"
    return "none"


def _side_from_persistence_status(status: str) -> str:
    if "confirmation" in status:
        return "confirmation"
    if "clearance" in status:
        return "clearance"
    return "none"


def _side_from_event(event: dict) -> str:
    status = str(
        event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status",
            "none",
        )
    )
    side = _side_from_persistence_status(status)
    if side != "none":
        return side
    return _side_from_status(
        str(
            event.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status",
                "none",
            )
        )
    )


def _closure_forecast_freshness_status(weighted_count: float, recent_share: float) -> str:
    if weighted_count < 1.0:
        return "insufficient-data"
    if recent_share >= 0.65:
        return "fresh"
    if recent_share >= 0.35:
        return "mixed-age"
    return "stale"


def _target_label(item: dict) -> str:
    return item.get("title", "") or item.get("kind", "") or "target"


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

    meta = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_for_target(
            target,
            events,
            target_class_key=_target_class_key,
            closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_status=(
                _side_from_status
            ),
            closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_persistence_status=(
                _side_from_persistence_status
            ),
            closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_event=(
                _side_from_event
            ),
            closure_forecast_freshness_status=_closure_forecast_freshness_status,
            class_memory_recency_weights=(1.0, 0.8, 0.6, 0.4),
            class_reset_reentry_rebuild_reentry_restore_rererestore_freshness_window_runs=4,
            history_window_runs=4,
        )
    )

    assert (
        meta[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status"
        ]
        == "fresh"
    )
    assert meta["has_fresh_aligned_recent_evidence"] is True


def test_rererestore_reset_control_softens_mixed_age_confirmation_signal() -> None:
    updates = (
        apply_reset_reentry_rebuild_reentry_restore_rererestore_freshness_reset_control(
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
            closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_persistence_status=(
                _side_from_persistence_status
            ),
            closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_status=(
                _side_from_status
            ),
            target_specific_normalization_noise=lambda _target, _meta: False,
        )
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

    stale_hotspots = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_hotspots(
            targets,
            mode="stale",
            target_class_key=_target_class_key,
        )
    )
    fresh_hotspots = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_hotspots(
            targets,
            mode="fresh",
            target_class_key=_target_class_key,
        )
    )
    freshness_summary = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_summary(
            targets[0],
            stale_hotspots,
            fresh_hotspots,
            target_label=_target_label,
        )
    )
    reset_summary = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_summary(
            targets[0],
            stale_hotspots,
            fresh_hotspots,
            target_label=_target_label,
        )
    )

    assert stale_hotspots[0]["label"] == "urgent:review"
    assert fresh_hotspots[0]["label"] == "blocked:setup"
    assert "RepoA" in freshness_summary
    assert "RepoA" in reset_summary


def test_rererestore_freshness_apply_returns_empty_defaults_without_targets() -> None:
    summary = apply_reset_reentry_rebuild_reentry_restore_rererestore_freshness_and_reset(
        [],
        [],
        current_generated_at="2026-04-17T00:00:00Z",
        confidence_calibration={},
        recommendation_bucket=lambda _target: "focus",
        class_closure_forecast_events=lambda *_args, **_kwargs: [],
        class_transition_events=lambda *_args, **_kwargs: [],
        target_class_transition_history=lambda _target, _events: {},
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_for_target=(
            lambda _target, _events: {}
        ),
        apply_reset_reentry_rebuild_reentry_restore_rererestore_freshness_reset_control=(
            lambda *_args, **_kwargs: {}
        ),
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_hotspots=(
            lambda _targets, mode: []
        ),
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_summary=(
            lambda _primary, _stale, _fresh: ""
        ),
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_summary=(
            lambda _primary, _stale, _fresh: ""
        ),
        class_reset_reentry_rebuild_reentry_restore_rererestore_freshness_window_runs=4,
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
