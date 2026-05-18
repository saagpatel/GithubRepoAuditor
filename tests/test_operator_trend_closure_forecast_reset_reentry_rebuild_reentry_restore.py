from __future__ import annotations

from src.operator_trend_closure_forecast_reset_reentry_rebuild_reentry_restore import (
    apply_reset_reentry_rebuild_reentry_refresh_restore_control,
    closure_forecast_reset_reentry_rebuild_reentry_refresh_hotspots,
    closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_for_target,
    closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_summary,
    closure_forecast_reset_reentry_rebuild_reentry_restore_summary,
)


def _ordered_reset_reentry_events_for_target(target: dict, events: list[dict]) -> list[dict]:
    class_key = f"{target.get('lane', '')}:{target.get('kind', '') or 'unknown'}"
    return [event for event in events if event.get("class_key") == class_key]


def _closure_forecast_reset_side_from_status(status: str) -> str:
    if "confirmation" in status:
        return "confirmation"
    if "clearance" in status:
        return "clearance"
    return "none"


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


def _closure_forecast_reset_reentry_rebuild_reentry_refresh_path_label(event: dict) -> str:
    return event.get("closure_forecast_reset_reentry_rebuild_reentry_restore_status", "hold")


def _target_class_key(item: dict) -> str:
    return f"{item.get('lane', '')}:{item.get('kind', '') or 'unknown'}"


def _target_label(item: dict) -> str:
    return item.get("title", "") or item.get("kind", "") or "target"


def test_refresh_recovery_for_target_detects_restoring_confirmation() -> None:
    target = {
        "lane": "urgent",
        "kind": "review",
        "closure_forecast_reweight_direction": "supporting-confirmation",
        "closure_forecast_reweight_score": 0.41,
        "closure_forecast_reset_reentry_rebuild_reentry_freshness_status": "fresh",
        "closure_forecast_momentum_status": "sustained-confirmation",
        "closure_forecast_stability_status": "stable",
    }
    events = [
        {
            "class_key": "urgent:review",
            "closure_forecast_reset_reentry_rebuild_reentry_reset_status": "confirmation-reset",
            "closure_forecast_reweight_direction": "supporting-confirmation",
            "closure_forecast_reweight_score": 0.31,
            "closure_forecast_reset_reentry_rebuild_reentry_freshness_status": "fresh",
        },
        {
            "class_key": "urgent:review",
            "closure_forecast_reweight_direction": "supporting-confirmation",
            "closure_forecast_reweight_score": 0.36,
            "closure_forecast_reset_reentry_rebuild_reentry_freshness_status": "fresh",
        },
    ]

    meta = closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_for_target(
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
        closure_forecast_reset_reentry_rebuild_reentry_refresh_path_label=(
            _closure_forecast_reset_reentry_rebuild_reentry_refresh_path_label
        ),
        class_reset_reentry_rebuild_reentry_refresh_restore_window_runs=4,
    )

    assert (
        meta["closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status"]
        == "restoring-confirmation-rebuild-reentry"
    )
    assert (
        meta["closure_forecast_reset_reentry_rebuild_reentry_restore_status"]
        == "pending-confirmation-rebuild-reentry-restore"
    )


def test_refresh_restore_control_restores_clearance_reentry() -> None:
    updates = apply_reset_reentry_rebuild_reentry_refresh_restore_control(
        {
            "closure_forecast_reset_reentry_rebuild_reentry_freshness_status": "fresh",
            "closure_forecast_stability_status": "stable",
            "class_transition_age_runs": 2,
            "decayed_reentered_rebuild_clearance_rate": 0.72,
        },
        refresh_meta={
            "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status": (
                "restoring-clearance-rebuild-reentry"
            ),
            "closure_forecast_reset_reentry_rebuild_reentry_restore_status": (
                "restored-clearance-rebuild-reentry"
            ),
            "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": (
                "Fresh clearance-side pressure has restored stronger rebuilt re-entry posture."
            ),
            "recent_rebuild_reentry_reset_side": "clearance",
        },
        transition_history_meta={"recent_pending_status": "pending-caution"},
        closure_likely_outcome="hold",
        closure_hysteresis_status="pending-clearance",
        closure_hysteresis_reason="",
        transition_status="pending-caution",
        transition_reason="",
        resolution_status="none",
        resolution_reason="",
        reentry_status="none",
        reentry_reason="",
        persistence_age_runs=0,
        persistence_score=0.0,
        persistence_status="none",
        persistence_reason="",
    )

    assert updates["transition_closure_likely_outcome"] == "clear-risk"
    assert (
        updates["closure_forecast_reset_reentry_rebuild_reentry_status"]
        == "reentered-clearance-rebuild"
    )


def test_refresh_hotspots_and_summaries_track_labels() -> None:
    targets = [
        {
            "lane": "urgent",
            "kind": "review",
            "title": "RepoA",
            "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_score": 0.33,
            "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status": (
                "restoring-confirmation-rebuild-reentry"
            ),
            "closure_forecast_reset_reentry_rebuild_reentry_restore_status": (
                "pending-confirmation-rebuild-reentry-restore"
            ),
        },
        {
            "lane": "blocked",
            "kind": "setup",
            "title": "RepoB",
            "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_score": -0.29,
            "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status": (
                "recovering-clearance-rebuild-reentry-reset"
            ),
            "closure_forecast_reset_reentry_rebuild_reentry_restore_status": (
                "restored-clearance-rebuild-reentry"
            ),
        },
    ]

    confirmation_hotspots = closure_forecast_reset_reentry_rebuild_reentry_refresh_hotspots(
        targets,
        mode="confirmation",
        target_class_key=_target_class_key,
    )
    clearance_hotspots = closure_forecast_reset_reentry_rebuild_reentry_refresh_hotspots(
        targets,
        mode="clearance",
        target_class_key=_target_class_key,
    )
    refresh_summary = closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_summary(
        targets[0],
        confirmation_hotspots,
        clearance_hotspots,
        target_label=_target_label,
    )
    restore_summary = closure_forecast_reset_reentry_rebuild_reentry_restore_summary(
        targets[1],
        confirmation_hotspots,
        clearance_hotspots,
        target_label=_target_label,
    )

    assert confirmation_hotspots[0]["label"] == "urgent:review"
    assert clearance_hotspots[0]["label"] == "blocked:setup"
    assert "RepoA" in refresh_summary
    assert "RepoB" in restore_summary
