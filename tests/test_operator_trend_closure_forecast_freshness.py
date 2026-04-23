from __future__ import annotations

from src.operator_trend_closure_forecast_freshness import (
    apply_closure_forecast_decay_control,
    closure_forecast_event_has_evidence,
    closure_forecast_event_is_clearance_like,
    closure_forecast_event_is_confirmation_like,
    closure_forecast_event_signal_label,
    closure_forecast_freshness_for_target,
    closure_forecast_freshness_hotspots,
    closure_forecast_freshness_reason,
    closure_forecast_freshness_status,
    recent_closure_forecast_signal_mix,
)


def _target_class_key(item: dict) -> str:
    return f"{item.get('lane', '')}:{item.get('kind', '') or 'unknown'}"


def _normalized_closure_forecast_direction(direction: str, score: float) -> str:
    normalized = (direction or "neutral").strip().lower()
    if normalized in {"supporting-confirmation", "supporting-clearance", "neutral"}:
        return normalized
    if score >= 0.05:
        return "supporting-confirmation"
    if score <= -0.05:
        return "supporting-clearance"
    return "neutral"


def _target_specific_normalization_noise(target: dict, history_meta: dict) -> bool:
    return bool(target.get("local_noise") or history_meta.get("current_transition_reversed"))


def test_closure_forecast_freshness_for_target_reports_mixed_age_signal() -> None:
    target = {"lane": "urgent", "kind": "config"}
    events = [
        {
            "class_key": "urgent:config",
            "closure_forecast_reweight_score": 0.4,
            "closure_forecast_reweight_direction": "supporting-confirmation",
            "transition_closure_likely_outcome": "confirm-soon",
        },
        {
            "class_key": "urgent:config",
            "closure_forecast_reweight_score": -0.3,
            "closure_forecast_reweight_direction": "supporting-clearance",
            "transition_closure_likely_outcome": "clear-risk",
        },
        {
            "class_key": "urgent:config",
            "closure_forecast_hysteresis_status": "pending-confirmation",
        },
    ]

    freshness_meta = closure_forecast_freshness_for_target(
        target,
        events,
        target_class_key=_target_class_key,
        closure_forecast_event_has_evidence=lambda event: closure_forecast_event_has_evidence(
            event,
            normalized_closure_forecast_direction=_normalized_closure_forecast_direction,
        ),
        closure_forecast_event_signal_label=lambda event: closure_forecast_event_signal_label(
            event,
            closure_forecast_event_is_confirmation_like=lambda value: closure_forecast_event_is_confirmation_like(
                value,
                normalized_closure_forecast_direction=_normalized_closure_forecast_direction,
            ),
            closure_forecast_event_is_clearance_like=lambda value: closure_forecast_event_is_clearance_like(
                value,
                normalized_closure_forecast_direction=_normalized_closure_forecast_direction,
            ),
        ),
        closure_forecast_event_is_confirmation_like=lambda event: closure_forecast_event_is_confirmation_like(
            event,
            normalized_closure_forecast_direction=_normalized_closure_forecast_direction,
        ),
        closure_forecast_event_is_clearance_like=lambda event: closure_forecast_event_is_clearance_like(
            event,
            normalized_closure_forecast_direction=_normalized_closure_forecast_direction,
        ),
        class_memory_recency_weights=[1.0, 0.8, 0.6, 0.4],
        history_window_runs=4,
        class_closure_forecast_freshness_window_runs=2,
        freshness_status=closure_forecast_freshness_status,
        freshness_reason=lambda *args: closure_forecast_freshness_reason(
            *args,
            class_closure_forecast_freshness_window_runs=2,
        ),
        recent_signal_mix=recent_closure_forecast_signal_mix,
    )

    assert freshness_meta["closure_forecast_freshness_status"] == "fresh"
    assert freshness_meta["closure_forecast_memory_weight"] == 0.75
    assert freshness_meta["recent_closure_forecast_path"] == "confirmation-like -> clearance-like"


def test_apply_closure_forecast_decay_control_blocks_confirmation_under_local_noise() -> None:
    updates = apply_closure_forecast_decay_control(
        {
            "closure_forecast_reweight_direction": "supporting-confirmation",
            "local_noise": True,
        },
        freshness_meta={
            "closure_forecast_freshness_status": "fresh",
            "decayed_clearance_forecast_rate": 0.0,
        },
        transition_history_meta={"current_transition_reversed": False},
        trust_policy="act-with-review",
        trust_policy_reason="Current signal is actionable.",
        transition_status="pending-support",
        transition_reason="Pending support is active.",
        resolution_status="none",
        resolution_reason="",
        closure_likely_outcome="confirm-soon",
        closure_hysteresis_status="confirmed-confirmation",
        closure_hysteresis_reason="Strong confirmation carry-forward.",
        pending_debt_status="watch",
        pending_debt_reason="",
        policy_debt_status="watch",
        policy_debt_reason="",
        class_normalization_status="active",
        class_normalization_reason="",
        target_specific_normalization_noise=_target_specific_normalization_noise,
    )

    assert updates[0] == "blocked"
    assert updates[2] == "hold"
    assert updates[3] == "pending-confirmation"


def test_apply_closure_forecast_decay_control_softens_confirmed_clearance_when_stale() -> None:
    updates = apply_closure_forecast_decay_control(
        {
            "closure_forecast_reweight_direction": "supporting-clearance",
            "closure_forecast_reweight_effect": "clear-risk-strengthened",
        },
        freshness_meta={
            "closure_forecast_freshness_status": "stale",
            "decayed_clearance_forecast_rate": 0.2,
        },
        transition_history_meta={"recent_pending_status": "pending-caution"},
        trust_policy="verify-first",
        trust_policy_reason="Stay verification aware.",
        transition_status="pending-caution",
        transition_reason="Pending caution is active.",
        resolution_status="none",
        resolution_reason="",
        closure_likely_outcome="expire-risk",
        closure_hysteresis_status="confirmed-clearance",
        closure_hysteresis_reason="Strong clearance carry-forward.",
        pending_debt_status="active-debt",
        pending_debt_reason="Fresh debt has been clustering.",
        policy_debt_status="watch",
        policy_debt_reason="",
        class_normalization_status="candidate",
        class_normalization_reason="",
        target_specific_normalization_noise=_target_specific_normalization_noise,
    )

    assert updates[0] == "clearance-decayed"
    assert updates[2] == "clear-risk"
    assert updates[3] == "pending-clearance"


def test_closure_forecast_freshness_hotspots_prefers_dominant_class_signal() -> None:
    hotspots = closure_forecast_freshness_hotspots(
        [
            {
                "lane": "urgent",
                "kind": "config",
                "closure_forecast_freshness_status": "fresh",
                "decayed_confirmation_forecast_rate": 0.8,
                "decayed_clearance_forecast_rate": 0.1,
                "recent_closure_forecast_path": "confirmation-like -> confirmation-like",
            },
            {
                "lane": "blocked",
                "kind": "setup",
                "closure_forecast_freshness_status": "stale",
                "decayed_confirmation_forecast_rate": 0.1,
                "decayed_clearance_forecast_rate": 0.7,
                "recent_closure_forecast_path": "clearance-like -> clearance-like",
            },
        ],
        mode="fresh",
        target_class_key=_target_class_key,
    )

    assert hotspots[0]["label"] == "urgent:config"
