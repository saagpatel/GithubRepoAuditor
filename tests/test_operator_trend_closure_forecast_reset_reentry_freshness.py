from __future__ import annotations

from src.operator_trend_closure_forecast_freshness import closure_forecast_freshness_status
from src.operator_trend_closure_forecast_reset_reentry_freshness import (
    apply_reset_reentry_freshness_reset_control,
    closure_forecast_reset_reentry_freshness_for_target,
    closure_forecast_reset_reentry_freshness_hotspots,
    closure_forecast_reset_reentry_freshness_summary,
    closure_forecast_reset_reentry_reset_summary,
)


def _target_class_key(item: dict) -> str:
    return f"{item.get('lane', '')}:{item.get('kind', '') or 'unknown'}"


def _target_label(item: dict) -> str:
    return item.get("title", "") or item.get("kind", "") or "target"


def _reset_reentry_side_from_persistence_status(status: str) -> str:
    if status in {"holding-confirmation-reentry", "sustained-confirmation-reentry"}:
        return "confirmation"
    if status in {"holding-clearance-reentry", "sustained-clearance-reentry"}:
        return "clearance"
    return "none"


def _reset_reentry_side_from_status(status: str) -> str:
    if status in {"pending-confirmation-reentry", "reentered-confirmation"}:
        return "confirmation"
    if status in {"pending-clearance-reentry", "reentered-clearance"}:
        return "clearance"
    return "none"


def _reset_reentry_memory_side_from_event(event: dict) -> str:
    side = _reset_reentry_side_from_persistence_status(
        event.get("closure_forecast_reset_reentry_persistence_status", "none")
    )
    if side != "none":
        return side
    return _reset_reentry_side_from_status(
        event.get("closure_forecast_reset_reentry_status", "none")
    )


def _reset_reentry_event_is_confirmation_like(event: dict) -> bool:
    return _reset_reentry_memory_side_from_event(event) == "confirmation" or event.get(
        "transition_closure_likely_outcome", "none"
    ) == "confirm-soon"


def _reset_reentry_event_is_clearance_like(event: dict) -> bool:
    return _reset_reentry_memory_side_from_event(event) == "clearance" or event.get(
        "transition_closure_likely_outcome", "none"
    ) in {"clear-risk", "expire-risk"}


def _reset_reentry_event_has_evidence(event: dict) -> bool:
    return _reset_reentry_event_is_confirmation_like(
        event
    ) or _reset_reentry_event_is_clearance_like(event)


def _reset_reentry_event_signal_label(event: dict) -> str:
    if _reset_reentry_event_is_confirmation_like(event):
        return "confirmation-like"
    if _reset_reentry_event_is_clearance_like(event):
        return "clearance-like"
    return "neutral"


def _reset_reentry_freshness_reason(
    freshness_status: str,
    weighted_count: float,
    recent_share: float,
    confirmation_rate: float,
    clearance_rate: float,
) -> str:
    return (
        f"{freshness_status}:{weighted_count:.2f}:{recent_share:.2f}:"
        f"{confirmation_rate:.2f}:{clearance_rate:.2f}"
    )


def _recent_reset_reentry_signal_mix(
    weighted_count: float,
    confirmation_like: float,
    clearance_like: float,
    recent_share: float,
) -> str:
    return (
        f"{weighted_count:.2f}:{confirmation_like:.2f}:"
        f"{clearance_like:.2f}:{recent_share:.2f}"
    )


def _target_specific_normalization_noise(target: dict, history_meta: dict) -> bool:
    return bool(target.get("local_noise") or history_meta.get("current_transition_reversed"))


def test_closure_forecast_reset_reentry_freshness_for_target_reports_fresh_signal() -> None:
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

    freshness_meta = closure_forecast_reset_reentry_freshness_for_target(
        target,
        events,
        target_class_key=_target_class_key,
        reset_reentry_event_has_evidence=_reset_reentry_event_has_evidence,
        reset_reentry_event_signal_label=_reset_reentry_event_signal_label,
        closure_forecast_reset_reentry_side_from_persistence_status=(
            _reset_reentry_side_from_persistence_status
        ),
        closure_forecast_reset_reentry_side_from_status=_reset_reentry_side_from_status,
        closure_forecast_reset_reentry_memory_side_from_event=(
            _reset_reentry_memory_side_from_event
        ),
        class_memory_recency_weights=[1.0, 0.8, 0.6, 0.4],
        history_window_runs=4,
        class_reset_reentry_freshness_window_runs=2,
        closure_forecast_freshness_status=closure_forecast_freshness_status,
        closure_forecast_reset_reentry_freshness_reason=_reset_reentry_freshness_reason,
        recent_reset_reentry_signal_mix=_recent_reset_reentry_signal_mix,
        reset_reentry_event_is_confirmation_like=(
            _reset_reentry_event_is_confirmation_like
        ),
        reset_reentry_event_is_clearance_like=_reset_reentry_event_is_clearance_like,
    )

    assert freshness_meta["closure_forecast_reset_reentry_freshness_status"] == "fresh"
    assert freshness_meta["closure_forecast_reset_reentry_memory_weight"] == 0.75
    assert freshness_meta["has_fresh_aligned_recent_evidence"] is True


def test_apply_reset_reentry_freshness_reset_control_resets_clearance_when_aged_out() -> None:
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
        closure_forecast_reset_reentry_side_from_persistence_status=(
            _reset_reentry_side_from_persistence_status
        ),
        closure_forecast_reset_reentry_side_from_status=_reset_reentry_side_from_status,
        target_specific_normalization_noise=_target_specific_normalization_noise,
    )

    assert updates["closure_forecast_reset_reentry_reset_status"] == "clearance-reset"
    assert updates["transition_closure_likely_outcome"] == "hold"
    assert updates["closure_forecast_reacquisition_status"] == "none"


def test_closure_forecast_reset_reentry_freshness_hotspots_and_summaries_track_classes() -> None:
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
        target_class_key=_target_class_key,
    )
    fresh_hotspots = closure_forecast_reset_reentry_freshness_hotspots(
        targets,
        mode="fresh",
        target_class_key=_target_class_key,
    )
    freshness_summary = closure_forecast_reset_reentry_freshness_summary(
        {"title": "RepoC", "closure_forecast_reset_reentry_freshness_status": "mixed-age"},
        stale_hotspots,
        fresh_hotspots,
        target_label=_target_label,
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
        target_label=_target_label,
    )

    assert stale_hotspots[0]["label"] == "blocked:setup"
    assert fresh_hotspots[0]["label"] == "urgent:config"
    assert "RepoC" in freshness_summary
    assert "RepoC" in reset_summary
