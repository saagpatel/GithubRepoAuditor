from __future__ import annotations

from src.operator_trend_closure_forecast_reset_reentry_rebuild_freshness import (
    apply_reset_reentry_rebuild_freshness_reset_control,
    closure_forecast_reset_reentry_rebuild_freshness_for_target,
    closure_forecast_reset_reentry_rebuild_freshness_hotspots,
    closure_forecast_reset_reentry_rebuild_freshness_summary,
    closure_forecast_reset_reentry_rebuild_reset_summary,
)


def _target_class_key(item: dict) -> str:
    return f"{item.get('lane', '')}:{item.get('kind', '') or 'unknown'}"


def _target_label(item: dict) -> str:
    return item.get("title", "") or item.get("kind", "") or "target"


def _closure_forecast_reset_reentry_rebuild_side_from_event(event: dict) -> str:
    status = event.get("closure_forecast_reset_reentry_rebuild_status", "none")
    if "confirmation" in status:
        return "confirmation"
    if "clearance" in status:
        return "clearance"
    persistence_status = event.get("closure_forecast_reset_reentry_rebuild_persistence_status", "none")
    if "confirmation" in persistence_status:
        return "confirmation"
    if "clearance" in persistence_status:
        return "clearance"
    return "none"


def _closure_forecast_reset_reentry_rebuild_side_from_persistence_status(status: str) -> str:
    if "confirmation" in status:
        return "confirmation"
    if "clearance" in status:
        return "clearance"
    return "none"


def _closure_forecast_reset_reentry_rebuild_side_from_status(status: str) -> str:
    if "confirmation" in status:
        return "confirmation"
    if "clearance" in status:
        return "clearance"
    return "none"


def _closure_forecast_freshness_status(weighted_count: float, recent_share: float) -> str:
    if weighted_count < 0.5:
        return "insufficient-data"
    if recent_share >= 0.6:
        return "fresh"
    if recent_share >= 0.35:
        return "mixed-age"
    return "stale"


def _target_specific_normalization_noise(target: dict, history_meta: dict) -> bool:
    return bool(target.get("local_noise") or history_meta.get("current_transition_reversed"))


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

    meta = closure_forecast_reset_reentry_rebuild_freshness_for_target(
        target,
        events,
        target_class_key=_target_class_key,
        closure_forecast_reset_reentry_rebuild_side_from_event=(
            _closure_forecast_reset_reentry_rebuild_side_from_event
        ),
        closure_forecast_reset_reentry_rebuild_side_from_persistence_status=(
            _closure_forecast_reset_reentry_rebuild_side_from_persistence_status
        ),
        closure_forecast_reset_reentry_rebuild_side_from_status=(
            _closure_forecast_reset_reentry_rebuild_side_from_status
        ),
        closure_forecast_freshness_status=_closure_forecast_freshness_status,
        class_memory_recency_weights=(1.0, 0.8, 0.6, 0.4),
        class_reset_reentry_rebuild_freshness_window_runs=2,
        history_window_runs=4,
    )

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
        closure_forecast_reset_reentry_rebuild_side_from_persistence_status=(
            _closure_forecast_reset_reentry_rebuild_side_from_persistence_status
        ),
        closure_forecast_reset_reentry_rebuild_side_from_status=(
            _closure_forecast_reset_reentry_rebuild_side_from_status
        ),
        target_specific_normalization_noise=_target_specific_normalization_noise,
    )

    assert updates["closure_forecast_reset_reentry_rebuild_reset_status"] == "confirmation-softened"
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
        target_class_key=_target_class_key,
    )
    stale_hotspots = closure_forecast_reset_reentry_rebuild_freshness_hotspots(
        targets,
        mode="stale",
        target_class_key=_target_class_key,
    )
    freshness_summary = closure_forecast_reset_reentry_rebuild_freshness_summary(
        targets[0],
        stale_hotspots,
        fresh_hotspots,
        target_label=_target_label,
    )
    reset_summary = closure_forecast_reset_reentry_rebuild_reset_summary(
        targets[1],
        stale_hotspots,
        fresh_hotspots,
        target_label=_target_label,
    )

    assert fresh_hotspots[0]["label"] == "urgent:review"
    assert stale_hotspots[0]["label"] == "blocked:setup"
    assert "RepoA" in freshness_summary
    assert "RepoB" in reset_summary
