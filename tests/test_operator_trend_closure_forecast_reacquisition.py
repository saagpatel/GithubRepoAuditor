from __future__ import annotations

from src.operator_trend_closure_forecast_freshness import closure_forecast_event_has_evidence
from src.operator_trend_closure_forecast_reacquisition import (
    apply_closure_forecast_reacquisition_control,
    apply_reacquisition_persistence_and_churn_control,
    closure_forecast_reacquisition_hotspots,
    closure_forecast_reacquisition_persistence_for_target,
    closure_forecast_reacquisition_side_from_event,
    closure_forecast_reacquisition_side_from_status,
    closure_forecast_reacquisition_summary,
    closure_forecast_recovery_churn_for_target,
    closure_forecast_refresh_recovery_for_target,
    closure_forecast_refresh_signal_from_event,
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


def _recent_closure_forecast_weakened_side(events: list[dict]) -> str:
    for event in events:
        if event.get("closure_forecast_decay_status") == "confirmation-decayed":
            return "confirmation"
        if event.get("closure_forecast_decay_status") == "clearance-decayed":
            return "clearance"
    return "none"


def _target_specific_normalization_noise(target: dict, history_meta: dict) -> bool:
    return bool(target.get("local_noise") or history_meta.get("current_transition_reversed"))


def _clamp_round(value: float, lower: float, upper: float) -> float:
    return round(max(lower, min(upper, value)), 2)


def _class_direction_flip_count(directions: list[str]) -> int:
    non_neutral = [direction for direction in directions if direction != "neutral"]
    return sum(1 for previous, current in zip(non_neutral, non_neutral[1:]) if current != previous)


def _closure_forecast_refresh_path_label(event: dict) -> str:
    direction = _normalized_closure_forecast_direction(
        event.get("closure_forecast_reweight_direction", "neutral"),
        event.get("closure_forecast_reweight_score", 0.0),
    )
    if direction == "supporting-confirmation":
        return "fresh confirmation"
    if direction == "supporting-clearance":
        return "fresh clearance"
    return "neutral"


def _closure_forecast_reacquisition_path_label(event: dict) -> str:
    status = event.get("closure_forecast_reacquisition_status", "none") or "none"
    if status != "none":
        return status
    return event.get("transition_closure_likely_outcome", "hold") or "hold"


def test_closure_forecast_refresh_recovery_for_target_detects_reacquired_confirmation() -> None:
    target = {
        "lane": "urgent",
        "kind": "config",
        "closure_forecast_freshness_status": "fresh",
        "closure_forecast_momentum_status": "sustained-confirmation",
        "closure_forecast_stability_status": "stable",
    }
    events = [
        {
            "class_key": "urgent:config",
            "closure_forecast_reweight_direction": "supporting-confirmation",
            "closure_forecast_reweight_score": 0.6,
            "closure_forecast_freshness_status": "fresh",
            "closure_forecast_decay_status": "confirmation-decayed",
            "transition_closure_likely_outcome": "confirm-soon",
        },
        {
            "class_key": "urgent:config",
            "closure_forecast_reweight_direction": "supporting-confirmation",
            "closure_forecast_reweight_score": 0.5,
            "closure_forecast_freshness_status": "fresh",
            "transition_closure_likely_outcome": "confirm-soon",
        },
    ]

    refresh_meta = closure_forecast_refresh_recovery_for_target(
        target,
        events,
        {},
        target_class_key=_target_class_key,
        closure_forecast_event_has_evidence=lambda event: closure_forecast_event_has_evidence(
            event,
            normalized_closure_forecast_direction=_normalized_closure_forecast_direction,
        ),
        normalized_closure_forecast_direction=_normalized_closure_forecast_direction,
        closure_forecast_refresh_signal_from_event=lambda event: closure_forecast_refresh_signal_from_event(
            event,
            normalized_closure_forecast_direction=_normalized_closure_forecast_direction,
        ),
        clamp_round=_clamp_round,
        closure_forecast_direction_majority=_closure_forecast_direction_majority,
        recent_closure_forecast_weakened_side=_recent_closure_forecast_weakened_side,
        target_specific_normalization_noise=_target_specific_normalization_noise,
        closure_forecast_direction_reversing=_closure_forecast_direction_reversing,
        closure_forecast_refresh_path_label=_closure_forecast_refresh_path_label,
        class_closure_forecast_refresh_window_runs=4,
    )

    assert refresh_meta["closure_forecast_refresh_recovery_status"] == "reacquiring-confirmation"
    assert refresh_meta["closure_forecast_reacquisition_status"] == "reacquired-confirmation"


def test_apply_closure_forecast_reacquisition_control_confirms_clearance_resolution() -> None:
    updates = apply_closure_forecast_reacquisition_control(
        {
            "class_reweight_transition_status": "pending-caution",
            "decayed_clearance_forecast_rate": 0.7,
            "closure_forecast_freshness_status": "fresh",
            "closure_forecast_stability_status": "stable",
            "class_transition_age_runs": 3,
        },
        refresh_meta={
            "closure_forecast_refresh_recovery_status": "reacquiring-clearance",
            "closure_forecast_reacquisition_status": "reacquired-clearance",
            "closure_forecast_reacquisition_reason": "Clearance pressure held.",
            "recent_weakened_side": "clearance",
        },
        transition_history_meta={},
        trust_policy="monitor",
        trust_policy_reason="",
        transition_status="pending-caution",
        transition_reason="",
        resolution_status="none",
        resolution_reason="",
        pending_debt_status="watch",
        pending_debt_reason="",
        policy_debt_status="watch",
        policy_debt_reason="",
        class_normalization_status="candidate",
        class_normalization_reason="",
        closure_likely_outcome="clear-risk",
        closure_hysteresis_status="pending-clearance",
        closure_hysteresis_reason="",
    )

    assert updates[0] == "expire-risk"
    assert updates[5] == "cleared"
    assert updates[3] == "none"


def test_closure_forecast_reacquisition_persistence_for_target_detects_sustained_confirmation() -> None:
    target = {
        "lane": "urgent",
        "kind": "config",
        "closure_forecast_reacquisition_status": "reacquired-confirmation",
        "closure_forecast_momentum_status": "sustained-confirmation",
        "closure_forecast_stability_status": "stable",
        "closure_forecast_freshness_status": "fresh",
    }
    events = [
        {
            "class_key": "urgent:config",
            "closure_forecast_reacquisition_status": "reacquired-confirmation",
            "closure_forecast_momentum_status": "sustained-confirmation",
            "closure_forecast_stability_status": "stable",
            "closure_forecast_freshness_status": "fresh",
        },
        {
            "class_key": "urgent:config",
            "closure_forecast_reacquisition_status": "pending-confirmation-reacquisition",
            "closure_forecast_momentum_status": "sustained-confirmation",
            "closure_forecast_stability_status": "stable",
            "closure_forecast_freshness_status": "fresh",
        },
        {
            "class_key": "urgent:config",
            "closure_forecast_refresh_recovery_status": "recovering-confirmation",
            "closure_forecast_momentum_status": "sustained-confirmation",
            "closure_forecast_stability_status": "stable",
            "closure_forecast_freshness_status": "fresh",
        },
    ]

    persistence_meta = closure_forecast_reacquisition_persistence_for_target(
        target,
        events,
        {},
        target_class_key=_target_class_key,
        closure_forecast_reacquisition_side_from_event=closure_forecast_reacquisition_side_from_event,
        clamp_round=_clamp_round,
        closure_forecast_direction_majority=_closure_forecast_direction_majority,
        closure_forecast_direction_reversing=_closure_forecast_direction_reversing,
        closure_forecast_reacquisition_path_label=_closure_forecast_reacquisition_path_label,
        class_reacquisition_persistence_window_runs=4,
    )

    assert persistence_meta["closure_forecast_reacquisition_persistence_status"] == "sustained-confirmation"
    assert persistence_meta["closure_forecast_reacquisition_age_runs"] == 3


def test_apply_reacquisition_persistence_and_churn_control_softens_churning_clearance() -> None:
    updates = apply_reacquisition_persistence_and_churn_control(
        {
            "closure_forecast_reacquisition_status": "reacquired-clearance",
            "closure_forecast_freshness_status": "fresh",
            "class_transition_age_runs": 2,
        },
        persistence_meta={
            "closure_forecast_reacquisition_persistence_status": "reversing",
            "closure_forecast_reacquisition_persistence_reason": "Restored posture is weakening.",
        },
        churn_meta={
            "closure_forecast_recovery_churn_status": "churn",
            "closure_forecast_recovery_churn_reason": "Recovery is flipping.",
        },
        transition_history_meta={"recent_pending_status": "pending-caution"},
        trust_policy="monitor",
        trust_policy_reason="",
        transition_status="none",
        transition_reason="",
        resolution_status="cleared",
        resolution_reason="",
        pending_debt_status="watch",
        pending_debt_reason="",
        policy_debt_status="watch",
        policy_debt_reason="",
        class_normalization_status="candidate",
        class_normalization_reason="",
        closure_likely_outcome="expire-risk",
        closure_hysteresis_status="confirmed-clearance",
        closure_hysteresis_reason="",
    )

    assert updates[0] == "clear-risk"
    assert updates[1] == "pending-clearance"
    assert updates[5] == "none"


def test_closure_forecast_recovery_churn_for_target_detects_wobble() -> None:
    target = {
        "lane": "urgent",
        "kind": "config",
        "closure_forecast_stability_status": "oscillating",
        "closure_forecast_momentum_status": "reversing",
        "closure_forecast_decay_status": "confirmation-decayed",
    }
    events = [
        {
            "class_key": "urgent:config",
            "closure_forecast_reacquisition_status": "reacquired-confirmation",
            "closure_forecast_freshness_status": "fresh",
        },
        {
            "class_key": "urgent:config",
            "closure_forecast_reacquisition_status": "pending-clearance-reacquisition",
            "closure_forecast_freshness_status": "mixed-age",
        },
        {
            "class_key": "urgent:config",
            "closure_forecast_refresh_recovery_status": "recovering-confirmation",
            "closure_forecast_freshness_status": "stale",
        },
    ]

    churn_meta = closure_forecast_recovery_churn_for_target(
        target,
        events,
        {},
        target_class_key=_target_class_key,
        closure_forecast_reacquisition_side_from_event=closure_forecast_reacquisition_side_from_event,
        class_direction_flip_count=_class_direction_flip_count,
        clamp_round=_clamp_round,
        target_specific_normalization_noise=_target_specific_normalization_noise,
        closure_forecast_reacquisition_path_label=_closure_forecast_reacquisition_path_label,
        class_reacquisition_persistence_window_runs=4,
    )

    assert churn_meta["closure_forecast_recovery_churn_status"] == "churn"
    assert churn_meta["closure_forecast_recovery_churn_score"] >= 0.45


def test_closure_forecast_reacquisition_hotspots_and_summary_prefer_live_risk() -> None:
    hotspots = closure_forecast_reacquisition_hotspots(
        [
            {
                "lane": "urgent",
                "kind": "config",
                "closure_forecast_reacquisition_age_runs": 3,
                "closure_forecast_reacquisition_persistence_score": 0.45,
                "closure_forecast_reacquisition_persistence_status": "holding-confirmation",
                "closure_forecast_recovery_churn_score": 0.1,
                "closure_forecast_recovery_churn_status": "none",
            },
            {
                "lane": "blocked",
                "kind": "setup",
                "closure_forecast_reacquisition_age_runs": 2,
                "closure_forecast_reacquisition_persistence_score": -0.2,
                "closure_forecast_reacquisition_persistence_status": "holding-clearance",
                "closure_forecast_recovery_churn_score": 0.55,
                "closure_forecast_recovery_churn_status": "churn",
            },
        ],
        mode="churn",
        target_class_key=_target_class_key,
    )

    summary = closure_forecast_reacquisition_summary(
        {
            "title": "Config lane",
            "closure_forecast_reacquisition_status": "none",
            "closure_forecast_reacquisition_reason": "",
        },
        recovering_confirmation_hotspots=[],
        recovering_clearance_hotspots=[{"label": "blocked:setup"}],
        target_label=_target_label,
    )

    assert hotspots[0]["label"] == "blocked:setup"
    assert "blocked:setup" in summary


def test_closure_forecast_reacquisition_side_from_status_maps_hysteresis_labels() -> None:
    assert closure_forecast_reacquisition_side_from_status("confirmed-confirmation") == "confirmation"
    assert closure_forecast_reacquisition_side_from_status("holding-clearance") == "clearance"
