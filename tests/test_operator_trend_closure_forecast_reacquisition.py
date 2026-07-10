from __future__ import annotations

from src.operator_trend_closure_forecast_reacquisition_controls import (
    apply_closure_forecast_reacquisition_control,
    apply_reacquisition_persistence_and_churn_control,
    closure_forecast_reacquisition_hotspots,
    closure_forecast_reacquisition_persistence_for_target,
    closure_forecast_reacquisition_side_from_status,
    closure_forecast_reacquisition_summary,
    closure_forecast_recovery_churn_for_target,
    closure_forecast_refresh_recovery_for_target,
)


def test_closure_forecast_refresh_recovery_for_target_detects_reacquired_confirmation() -> (
    None
):
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

    refresh_meta = closure_forecast_refresh_recovery_for_target(target, events, {})

    assert (
        refresh_meta["closure_forecast_refresh_recovery_status"]
        == "reacquiring-confirmation"
    )
    assert (
        refresh_meta["closure_forecast_reacquisition_status"]
        == "reacquired-confirmation"
    )


def test_apply_closure_forecast_reacquisition_control_confirms_clearance_resolution() -> (
    None
):
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


def test_closure_forecast_reacquisition_persistence_for_target_detects_sustained_confirmation() -> (
    None
):
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
    )

    assert (
        persistence_meta["closure_forecast_reacquisition_persistence_status"]
        == "sustained-confirmation"
    )
    assert persistence_meta["closure_forecast_reacquisition_age_runs"] == 3


def test_apply_reacquisition_persistence_and_churn_control_softens_churning_clearance() -> (
    None
):
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
    )

    summary = closure_forecast_reacquisition_summary(
        {
            "title": "Config lane",
            "closure_forecast_reacquisition_status": "none",
            "closure_forecast_reacquisition_reason": "",
        },
        recovering_confirmation_hotspots=[],
        recovering_clearance_hotspots=[{"label": "blocked:setup"}],
    )

    assert hotspots[0]["label"] == "blocked:setup"
    assert "blocked:setup" in summary


def test_closure_forecast_reacquisition_side_from_status_maps_hysteresis_labels() -> (
    None
):
    assert (
        closure_forecast_reacquisition_side_from_status("confirmed-confirmation")
        == "confirmation"
    )
    assert (
        closure_forecast_reacquisition_side_from_status("holding-clearance")
        == "clearance"
    )
