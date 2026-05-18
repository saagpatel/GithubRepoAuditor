from __future__ import annotations

from src.operator_trend_pending_debt import (
    class_pending_debt_for_target,
    class_pending_debt_hotspots,
    closure_forecast_reweight_scores_for_target,
    pending_debt_event_outcome,
    pending_debt_freshness_for_target,
)


def _target_class_key(item: dict) -> str:
    return f"{item.get('lane', '')}:{item.get('kind', '') or 'unknown'}"


def _clamp_round(value: float, lower: float, upper: float) -> float:
    return round(max(lower, min(upper, value)), 2)


def _target_specific_normalization_noise(target: dict, history_meta: dict) -> bool:
    return bool(target.get("local_noise") or history_meta.get("current_transition_reversed"))


def test_pending_debt_event_outcome_classifies_resolution_states() -> None:
    assert pending_debt_event_outcome({"class_transition_resolution_status": "confirmed"}) == "confirmed"
    assert pending_debt_event_outcome({"class_transition_health_status": "stalled"}) == "stalled"
    assert pending_debt_event_outcome({"class_reweight_transition_status": "pending-support"}) == "pending"
    assert pending_debt_event_outcome({"class_transition_resolution_status": "blocked"}) == "blocked"


def test_class_pending_debt_for_target_detects_active_debt() -> None:
    target = {"lane": "urgent", "kind": "config"}
    transition_events = [
        {
            "class_key": "urgent:config",
            "class_transition_health_status": "stalled",
        },
        {
            "class_key": "urgent:config",
            "class_transition_resolution_status": "expired",
        },
        {
            "class_key": "urgent:config",
            "class_transition_resolution_status": "blocked",
        },
    ]

    status, _reason, debt_rate, resolution_rate, path = class_pending_debt_for_target(
        target,
        transition_events,
        target_class_key=_target_class_key,
        clamp_round=_clamp_round,
        class_pending_debt_window_runs=5,
    )

    assert status == "active-debt"
    assert debt_rate == 1.0
    assert resolution_rate == 0.0
    assert path == "stalled -> expired -> blocked"


def test_pending_debt_freshness_for_target_reports_mixed_age_signal() -> None:
    target = {"lane": "urgent", "kind": "config"}
    transition_events = [
        {
            "class_key": "urgent:config",
            "class_transition_resolution_status": "confirmed",
        },
        {
            "class_key": "urgent:config",
            "class_transition_health_status": "stalled",
        },
        {
            "class_key": "urgent:config",
            "class_transition_resolution_status": "cleared",
        },
        {
            "class_key": "urgent:config",
            "class_transition_health_status": "holding",
        },
    ]

    history_meta = pending_debt_freshness_for_target(
        target,
        transition_events,
        target_class_key=_target_class_key,
        class_memory_recency_weights=[1.0, 0.8, 0.7, 0.6],
        history_window_runs=4,
        class_pending_debt_window_runs=4,
        pending_debt_freshness_window_runs=2,
    )

    assert history_meta["pending_debt_freshness_status"] == "mixed-age"
    assert history_meta["pending_debt_memory_weight"] == 0.58
    assert history_meta["recent_pending_debt_path"] == "confirmed -> stalled"


def test_class_pending_debt_hotspots_prefers_strongest_class_signal() -> None:
    hotspots = class_pending_debt_hotspots(
        [
            {
                "lane": "urgent",
                "kind": "config",
                "class_pending_debt_status": "active-debt",
                "class_pending_debt_rate": 0.9,
                "recent_pending_debt_path": "blocked -> stalled -> expired",
            },
            {
                "lane": "urgent",
                "kind": "config",
                "class_pending_debt_status": "active-debt",
                "class_pending_debt_rate": 0.7,
                "recent_pending_debt_path": "stalled -> expired",
            },
            {
                "lane": "blocked",
                "kind": "setup",
                "class_pending_debt_status": "clearing",
                "class_pending_resolution_rate": 0.8,
                "recent_pending_debt_path": "confirmed -> cleared",
            },
        ],
        mode="debt",
        target_class_key=_target_class_key,
    )

    assert hotspots[0]["label"] == "urgent:config"
    assert hotspots[0]["class_pending_debt_rate"] == 0.9


def test_closure_forecast_reweight_scores_for_target_balances_support_and_caution() -> None:
    target = {
        "class_reweight_transition_status": "pending-support",
        "class_transition_health_status": "building",
        "transition_closure_likely_outcome": "confirm-soon",
        "class_pending_debt_status": "clearing",
        "class_reweight_stability_status": "stable",
        "class_transition_age_runs": 2,
        "class_transition_resolution_status": "none",
    }
    transition_history_meta = {
        "transition_score_delta": 0.12,
        "current_transition_strengthening": True,
    }
    pending_history_meta = {
        "pending_debt_freshness_status": "fresh",
        "decayed_pending_resolution_rate": 0.6,
        "decayed_pending_debt_rate": 0.2,
        "pending_debt_freshness_reason": "Recent pending signal is fresh.",
    }

    support_score, caution_score, reweight_score, direction, reasons = (
        closure_forecast_reweight_scores_for_target(
            target,
            transition_history_meta,
            pending_history_meta,
            target_specific_normalization_noise=_target_specific_normalization_noise,
            clamp_round=_clamp_round,
        )
    )

    assert support_score == 0.9
    assert caution_score == 0.1
    assert reweight_score == 0.8
    assert direction == "supporting-confirmation"
    assert reasons[0] == "Recent pending signal is fresh."
