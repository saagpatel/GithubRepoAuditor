from __future__ import annotations

from src.operator_trend_closure_forecast_reset_reentry_rebuild import (
    apply_reset_reentry_refresh_rebuild_control,
    closure_forecast_reset_reentry_rebuild_summary,
    closure_forecast_reset_reentry_refresh_hotspots,
    closure_forecast_reset_reentry_refresh_recovery_for_target,
    closure_forecast_reset_reentry_refresh_recovery_summary,
)


def _ordered_reset_reentry_events_for_target(target: dict, events: list[dict]) -> list[dict]:
    class_key = f"{target.get('lane', '')}:{target.get('kind', '') or 'unknown'}"
    return [event for event in events if event.get("class_key") == class_key]


def _normalized_closure_forecast_direction(direction: str, score: float) -> str:
    normalized = (direction or "neutral").strip().lower()
    if normalized in {"supporting-confirmation", "supporting-clearance", "neutral"}:
        return normalized
    if score >= 0.05:
        return "supporting-confirmation"
    if score <= -0.05:
        return "supporting-clearance"
    return "neutral"


def _clamp_round(value: float, lower: float, upper: float) -> float:
    return round(max(lower, min(upper, value)), 2)


def _closure_forecast_direction_majority(directions: list[str]) -> str:
    confirmation = sum(1 for direction in directions if direction == "supporting-confirmation")
    clearance = sum(1 for direction in directions if direction == "supporting-clearance")
    if confirmation > clearance:
        return "supporting-confirmation"
    if clearance > confirmation:
        return "supporting-clearance"
    return "neutral"


def _target_specific_normalization_noise(target: dict, history_meta: dict) -> bool:
    return bool(target.get("local_noise") or history_meta.get("current_transition_reversed"))


def _closure_forecast_direction_reversing(current_direction: str, earlier_majority: str) -> bool:
    if current_direction == "neutral" or earlier_majority == "neutral":
        return False
    return current_direction != earlier_majority


def _closure_forecast_reset_side_from_status(status: str) -> str:
    if status in {"confirmation-softened", "confirmation-reset"}:
        return "confirmation"
    if status in {"clearance-softened", "clearance-reset"}:
        return "clearance"
    return "none"


def _closure_forecast_reset_reentry_refresh_path_label(event: dict) -> str:
    return event.get("closure_forecast_reset_reentry_reset_status", "hold")


def _target_class_key(item: dict) -> str:
    return f"{item.get('lane', '')}:{item.get('kind', '') or 'unknown'}"


def _target_label(item: dict) -> str:
    return item.get("title", "") or item.get("kind", "") or "target"


def test_refresh_recovery_for_target_detects_confirmation_rebuild() -> None:
    target = {
        "lane": "urgent",
        "kind": "config",
        "closure_forecast_reweight_direction": "supporting-confirmation",
        "closure_forecast_reweight_score": 0.42,
        "closure_forecast_reset_reentry_freshness_status": "fresh",
        "closure_forecast_momentum_status": "sustained-confirmation",
        "closure_forecast_stability_status": "stable",
    }
    events = [
        {
            "class_key": "urgent:config",
            "closure_forecast_reweight_direction": "supporting-confirmation",
            "closure_forecast_reweight_score": 0.36,
            "closure_forecast_reset_reentry_freshness_status": "fresh",
        },
        {
            "class_key": "urgent:config",
            "closure_forecast_reweight_direction": "supporting-confirmation",
            "closure_forecast_reweight_score": 0.32,
            "closure_forecast_reset_reentry_freshness_status": "fresh",
        },
        {
            "class_key": "urgent:config",
            "closure_forecast_reset_reentry_reset_status": "confirmation-reset",
            "closure_forecast_reweight_direction": "supporting-confirmation",
            "closure_forecast_reweight_score": 0.28,
            "closure_forecast_reset_reentry_freshness_status": "fresh",
        },
    ]

    refresh_meta = closure_forecast_reset_reentry_refresh_recovery_for_target(
        target,
        events,
        {},
        ordered_reset_reentry_events_for_target=_ordered_reset_reentry_events_for_target,
        closure_forecast_reset_side_from_status=_closure_forecast_reset_side_from_status,
        normalized_closure_forecast_direction=_normalized_closure_forecast_direction,
        clamp_round=_clamp_round,
        closure_forecast_direction_majority=_closure_forecast_direction_majority,
        target_specific_normalization_noise=_target_specific_normalization_noise,
        closure_forecast_direction_reversing=_closure_forecast_direction_reversing,
        closure_forecast_reset_reentry_refresh_path_label=(
            _closure_forecast_reset_reentry_refresh_path_label
        ),
        class_reset_reentry_refresh_rebuild_window_runs=4,
    )

    assert (
        refresh_meta["closure_forecast_reset_reentry_refresh_recovery_status"]
        == "rebuilding-confirmation-reentry"
    )
    assert (
        refresh_meta["closure_forecast_reset_reentry_rebuild_status"]
        == "rebuilt-confirmation-reentry"
    )


def test_apply_reset_reentry_refresh_rebuild_control_softens_to_pending() -> None:
    updates = apply_reset_reentry_refresh_rebuild_control(
        {
            "closure_forecast_reset_reentry_freshness_status": "fresh",
            "closure_forecast_stability_status": "stable",
            "class_transition_age_runs": 1,
            "decayed_reset_reentered_clearance_rate": 0.0,
        },
        refresh_meta={
            "closure_forecast_reset_reentry_refresh_recovery_status": (
                "recovering-confirmation-reentry-reset"
            ),
            "closure_forecast_reset_reentry_rebuild_status": "pending-confirmation-rebuild",
            "closure_forecast_reset_reentry_rebuild_reason": "rebuilding",
            "recent_reset_reentry_side": "confirmation",
        },
        transition_history_meta={},
        closure_likely_outcome="hold",
        closure_hysteresis_status="pending-confirmation",
        closure_hysteresis_reason="",
        transition_status="pending-support",
        transition_reason="",
        resolution_status="none",
        resolution_reason="",
        reacquisition_status="none",
        reacquisition_reason="",
        reentry_status="none",
        reentry_reason="",
        persistence_age_runs=0,
        persistence_score=0.0,
        persistence_status="none",
        persistence_reason="",
    )

    assert updates["closure_forecast_reacquisition_status"] == "pending-confirmation-reacquisition"
    assert updates["closure_forecast_reset_reentry_status"] == "pending-confirmation-reentry"


def test_refresh_hotspots_and_summaries_track_active_classes() -> None:
    hotspots = closure_forecast_reset_reentry_refresh_hotspots(
        [
            {
                "lane": "urgent",
                "kind": "config",
                "closure_forecast_reset_reentry_refresh_recovery_score": 0.31,
                "closure_forecast_reset_reentry_refresh_recovery_status": (
                    "rebuilding-confirmation-reentry"
                ),
                "recent_reset_reentry_refresh_path": "confirmation-reset -> fresh confirmation",
            },
            {
                "lane": "blocked",
                "kind": "setup",
                "closure_forecast_reset_reentry_refresh_recovery_score": -0.27,
                "closure_forecast_reset_reentry_refresh_recovery_status": (
                    "recovering-clearance-reentry-reset"
                ),
                "recent_reset_reentry_refresh_path": "clearance-reset -> fresh clearance",
            },
        ],
        mode="confirmation",
        target_class_key=_target_class_key,
    )
    refresh_summary = closure_forecast_reset_reentry_refresh_recovery_summary(
        {
            "title": "RepoC",
            "closure_forecast_reset_reentry_refresh_recovery_status": (
                "recovering-confirmation-reentry-reset"
            ),
            "closure_forecast_reset_reentry_refresh_recovery_score": 0.18,
        },
        hotspots,
        [],
        target_label=_target_label,
    )
    rebuild_summary = closure_forecast_reset_reentry_rebuild_summary(
        {
            "title": "RepoC",
            "closure_forecast_reset_reentry_rebuild_status": "pending-confirmation-rebuild",
        },
        hotspots,
        [],
        target_label=_target_label,
    )

    assert hotspots[0]["label"] == "urgent:config"
    assert "RepoC" in refresh_summary
    assert "RepoC" in rebuild_summary
