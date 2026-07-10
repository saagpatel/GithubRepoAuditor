from __future__ import annotations

from src.operator_trend_closure_forecast_freshness_controls import (
    apply_closure_forecast_decay_control,
    closure_forecast_freshness_for_target,
    closure_forecast_freshness_hotspots,
)


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

    freshness_meta = closure_forecast_freshness_for_target(target, events)

    assert freshness_meta["closure_forecast_freshness_status"] == "fresh"
    assert freshness_meta["closure_forecast_memory_weight"] == 1.0
    assert (
        freshness_meta["recent_closure_forecast_path"]
        == "confirmation-like -> clearance-like -> confirmation-like"
    )
    assert freshness_meta["decayed_confirmation_forecast_rate"] == 0.63
    assert freshness_meta["decayed_clearance_forecast_rate"] == 0.37


def test_apply_closure_forecast_decay_control_blocks_confirmation_under_local_noise() -> (
    None
):
    updates = apply_closure_forecast_decay_control(
        {
            "closure_forecast_reweight_direction": "supporting-confirmation",
        },
        freshness_meta={
            "closure_forecast_freshness_status": "fresh",
            "decayed_clearance_forecast_rate": 0.0,
        },
        transition_history_meta={"recent_reopened": True},
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
    )

    assert updates[0] == "blocked"
    assert updates[2] == "hold"
    assert updates[3] == "pending-confirmation"


def test_apply_closure_forecast_decay_control_softens_confirmed_clearance_when_stale() -> (
    None
):
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
    )

    assert hotspots[0]["label"] == "urgent:config"
