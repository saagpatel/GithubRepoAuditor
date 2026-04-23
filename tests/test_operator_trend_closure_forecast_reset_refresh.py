from __future__ import annotations

from src.operator_trend_closure_forecast_reset_refresh import (
    apply_reset_refresh_reentry_control,
    closure_forecast_reset_refresh_hotspots,
    closure_forecast_reset_refresh_recovery_for_target,
    closure_forecast_reset_refresh_recovery_summary,
    closure_forecast_reset_side_from_status,
)


def _target_class_key(item: dict) -> str:
    return f"{item.get('lane', '')}:{item.get('kind', '') or 'unknown'}"


def _target_label(item: dict) -> str:
    return item.get("title", "") or item.get("kind", "") or "target"


def _normalized_closure_forecast_direction(direction: str, score: float) -> str:
    normalized = (direction or "neutral").strip().lower()
    if normalized in {"supporting-confirmation", "supporting-clearance", "neutral"}:
        return normalized
    if score >= 0.05:
        return "supporting-confirmation"
    if score <= -0.05:
        return "supporting-clearance"
    return "neutral"


def _closure_forecast_direction_majority(directions: list[str]) -> str:
    confirmation = sum(1 for direction in directions if direction == "supporting-confirmation")
    clearance = sum(1 for direction in directions if direction == "supporting-clearance")
    if confirmation > clearance:
        return "supporting-confirmation"
    if clearance > confirmation:
        return "supporting-clearance"
    return "neutral"


def _closure_forecast_direction_reversing(current_direction: str, earlier_majority: str) -> bool:
    if current_direction == "neutral" or earlier_majority == "neutral":
        return False
    return current_direction != earlier_majority


def _target_specific_normalization_noise(target: dict, history_meta: dict) -> bool:
    return bool(target.get("local_noise") or history_meta.get("current_transition_reversed"))


def _clamp_round(value: float, lower: float, upper: float) -> float:
    return round(max(lower, min(upper, value)), 2)


def test_closure_forecast_reset_refresh_recovery_for_target_detects_confirmation_reentry() -> None:
    target = {
        "lane": "urgent",
        "kind": "config",
        "closure_forecast_reweight_direction": "supporting-confirmation",
        "closure_forecast_reweight_score": 0.45,
        "closure_forecast_reacquisition_freshness_status": "fresh",
        "closure_forecast_momentum_status": "sustained-confirmation",
        "closure_forecast_stability_status": "stable",
    }
    events = [
        {
            "class_key": "urgent:config",
            "closure_forecast_reweight_direction": "supporting-confirmation",
            "closure_forecast_reweight_score": 0.4,
            "closure_forecast_reacquisition_freshness_status": "fresh",
        },
        {
            "class_key": "urgent:config",
            "closure_forecast_reweight_direction": "supporting-confirmation",
            "closure_forecast_reweight_score": 0.35,
            "closure_forecast_reacquisition_freshness_status": "fresh",
        },
        {
            "class_key": "urgent:config",
            "closure_forecast_reweight_direction": "supporting-confirmation",
            "closure_forecast_reweight_score": 0.3,
            "closure_forecast_reacquisition_freshness_status": "fresh",
            "closure_forecast_persistence_reset_status": "confirmation-reset",
        },
    ]

    refresh_meta = closure_forecast_reset_refresh_recovery_for_target(
        target,
        events,
        {},
        target_class_key=_target_class_key,
        closure_forecast_reset_side_from_status=closure_forecast_reset_side_from_status,
        normalized_closure_forecast_direction=_normalized_closure_forecast_direction,
        clamp_round=_clamp_round,
        closure_forecast_direction_majority=_closure_forecast_direction_majority,
        target_specific_normalization_noise=_target_specific_normalization_noise,
        closure_forecast_direction_reversing=_closure_forecast_direction_reversing,
        closure_forecast_reset_refresh_path_label=lambda event: "path",
        class_reset_reentry_window_runs=4,
    )

    assert refresh_meta["closure_forecast_reset_refresh_recovery_status"] == "reentering-confirmation"
    assert refresh_meta["closure_forecast_reset_reentry_status"] == "reentered-confirmation"


def test_apply_reset_refresh_reentry_control_softens_confirmation_when_blocked() -> None:
    updates = apply_reset_refresh_reentry_control(
        {
            "closure_forecast_reacquisition_age_runs": 2,
            "closure_forecast_reacquisition_persistence_score": 0.2,
            "closure_forecast_reacquisition_persistence_status": "holding-confirmation",
            "closure_forecast_reacquisition_persistence_reason": "holding",
            "closure_forecast_reacquisition_freshness_status": "fresh",
            "closure_forecast_stability_status": "stable",
        },
        refresh_meta={
            "closure_forecast_reset_refresh_recovery_status": "blocked",
            "closure_forecast_reset_reentry_status": "blocked",
            "closure_forecast_reset_reentry_reason": "Local noise is blocking re-entry.",
            "recent_reset_side": "confirmation",
        },
        transition_history_meta={},
        closure_likely_outcome="confirm-soon",
        closure_hysteresis_status="confirmed-confirmation",
        closure_hysteresis_reason="",
        transition_status="pending-support",
        transition_reason="",
        resolution_status="none",
        resolution_reason="",
        reacquisition_status="reacquired-confirmation",
        reacquisition_reason="",
    )

    assert updates["transition_closure_likely_outcome"] == "hold"
    assert updates["closure_forecast_hysteresis_status"] == "pending-confirmation"
    assert updates["closure_forecast_reacquisition_status"] == "pending-confirmation-reacquisition"


def test_closure_forecast_reset_refresh_hotspots_and_summary_track_active_classes() -> None:
    hotspots = closure_forecast_reset_refresh_hotspots(
        [
            {
                "lane": "urgent",
                "kind": "config",
                "closure_forecast_reset_refresh_recovery_score": 0.28,
                "closure_forecast_reset_refresh_recovery_status": "reentering-confirmation",
                "closure_forecast_reset_reentry_status": "pending-confirmation-reentry",
            },
            {
                "lane": "blocked",
                "kind": "setup",
                "closure_forecast_reset_refresh_recovery_score": -0.33,
                "closure_forecast_reset_refresh_recovery_status": "reentering-clearance",
                "closure_forecast_reset_reentry_status": "reentered-clearance",
            },
        ],
        mode="clearance",
        target_class_key=_target_class_key,
    )

    summary = closure_forecast_reset_refresh_recovery_summary(
        {
            "title": "RepoC",
            "closure_forecast_reset_refresh_recovery_status": "recovering-confirmation-reset",
            "closure_forecast_reset_refresh_recovery_score": 0.18,
        },
        recovering_confirmation_hotspots=[],
        recovering_clearance_hotspots=hotspots,
        target_label=_target_label,
    )

    assert hotspots[0]["label"] == "blocked:setup"
    assert "RepoC" in summary
