from __future__ import annotations

from src.operator_trend_transition_closure import (
    apply_transition_closure_control,
    transition_closure_confidence_for_target,
)


def _target_specific_normalization_noise(target: dict, history_meta: dict) -> bool:
    return bool(target.get("local_noise") or history_meta.get("current_transition_reversed"))


def _clamp_round(value: float, lower: float, upper: float) -> float:
    return round(max(lower, min(upper, value)), 2)


def test_transition_closure_confidence_marks_confirm_soon_when_signal_is_strong() -> None:
    target = {
        "class_reweight_transition_status": "pending-support",
        "class_transition_health_status": "building",
        "class_trust_momentum_status": "sustained-support",
        "class_reweight_stability_status": "stable",
        "class_trust_reweight_score": 0.42,
        "class_transition_age_runs": 2,
    }
    history_meta = {
        "matching_transition_event_count": 3,
        "transition_score_delta": 0.11,
        "current_transition_strengthening": True,
        "current_transition_health_status": "building",
        "current_transition_resolution_status": "none",
    }

    score, label, outcome, reasons = transition_closure_confidence_for_target(
        target,
        history_meta,
        target_specific_normalization_noise=_target_specific_normalization_noise,
        clamp_round=_clamp_round,
    )

    assert score == 0.75
    assert label == "high"
    assert outcome == "confirm-soon"
    assert "Recent class momentum is still aligned" in reasons[1]


def test_transition_closure_confidence_marks_blocked_when_support_signal_reverses_with_noise() -> None:
    target = {
        "class_reweight_transition_status": "pending-support",
        "class_transition_health_status": "holding",
        "class_trust_momentum_status": "reversing",
        "class_reweight_stability_status": "watch",
        "class_trust_reweight_score": 0.04,
        "class_transition_age_runs": 3,
    }
    history_meta = {
        "matching_transition_event_count": 4,
        "transition_score_delta": 0.0,
        "current_transition_strengthening": False,
        "current_transition_neutral": True,
        "current_transition_reversed": True,
        "current_lost_pending_support": True,
    }

    score, label, outcome, reasons = transition_closure_confidence_for_target(
        target,
        history_meta,
        target_specific_normalization_noise=_target_specific_normalization_noise,
        clamp_round=_clamp_round,
    )

    assert score == 0.05
    assert label == "low"
    assert outcome == "blocked"
    assert any("overriding positive class strengthening" in reason for reason in reasons)


def test_apply_transition_closure_control_clears_low_confidence_pending_support() -> None:
    updates = apply_transition_closure_control(
        {
            "pre_class_normalization_trust_policy": "verify-first",
            "pre_class_normalization_trust_policy_reason": "Fall back to verification.",
        },
        trust_policy="act-with-review",
        trust_policy_reason="Current signal is actionable.",
        health_status="building",
        health_reason="",
        resolution_status="none",
        resolution_reason="",
        transition_status="pending-support",
        transition_reason="Recent class signal is leaning positive.",
        policy_debt_status="watch",
        policy_debt_reason="",
        class_normalization_status="active",
        class_normalization_reason="",
        closure_confidence_label="low",
        closure_likely_outcome="clear-risk",
        pending_debt_status="active-debt",
    )

    assert updates[2] == "cleared"
    assert updates[6] == "verify-first"
    assert updates[10] == "candidate"


def test_apply_transition_closure_control_leaves_non_triggered_state_unchanged() -> None:
    updates = apply_transition_closure_control(
        {},
        trust_policy="act-with-review",
        trust_policy_reason="Current signal is actionable.",
        health_status="building",
        health_reason="Still building.",
        resolution_status="none",
        resolution_reason="",
        transition_status="pending-support",
        transition_reason="Recent class signal is leaning positive.",
        policy_debt_status="watch",
        policy_debt_reason="",
        class_normalization_status="active",
        class_normalization_reason="",
        closure_confidence_label="high",
        closure_likely_outcome="confirm-soon",
        pending_debt_status="watch",
    )

    assert updates[0] == "building"
    assert updates[2] == "none"
    assert updates[6] == "act-with-review"
