from __future__ import annotations

from src.operator_trend_closure_forecast_reweighting import (
    apply_closure_forecast_reweighting_control,
    closure_forecast_hotspots,
    pending_debt_freshness_hotspots,
)


def _target_class_key(item: dict) -> str:
    return f"{item.get('lane', '')}:{item.get('kind', '') or 'unknown'}"


def _target_specific_normalization_noise(target: dict, history_meta: dict) -> bool:
    return bool(target.get("local_noise") or history_meta.get("current_transition_reversed"))


def test_apply_closure_forecast_reweighting_control_softens_confirmation_when_noise_blocks_it() -> None:
    updates = apply_closure_forecast_reweighting_control(
        {
            "class_transition_age_runs": 2,
            "local_noise": True,
        },
        transition_history_meta={"current_transition_strengthening": True},
        trust_policy="act-with-review",
        trust_policy_reason="Current signal is actionable.",
        transition_status="pending-support",
        transition_reason="Pending support is active.",
        resolution_status="none",
        resolution_reason="",
        pending_debt_status="watch",
        pending_debt_reason="",
        policy_debt_status="watch",
        policy_debt_reason="",
        class_normalization_status="active",
        class_normalization_reason="",
        closure_confidence_label="high",
        closure_likely_outcome="confirm-soon",
        pending_debt_freshness_status="fresh",
        closure_forecast_reweight_direction="supporting-confirmation",
        closure_forecast_reweight_score=0.52,
        target_specific_normalization_noise=_target_specific_normalization_noise,
    )

    assert updates[0] == "confirm-support-softened"
    assert updates[2] == "hold"


def test_apply_closure_forecast_reweighting_control_clears_low_confidence_support_on_fresh_debt() -> None:
    updates = apply_closure_forecast_reweighting_control(
        {
            "class_transition_age_runs": 4,
            "pre_class_normalization_trust_policy": "verify-first",
            "pre_class_normalization_trust_policy_reason": "Return to verification.",
        },
        transition_history_meta={"current_transition_strengthening": False},
        trust_policy="act-with-review",
        trust_policy_reason="Current signal is actionable.",
        transition_status="pending-support",
        transition_reason="Pending support is active.",
        resolution_status="none",
        resolution_reason="",
        pending_debt_status="active-debt",
        pending_debt_reason="Debt is clustering.",
        policy_debt_status="watch",
        policy_debt_reason="",
        class_normalization_status="active",
        class_normalization_reason="",
        closure_confidence_label="low",
        closure_likely_outcome="hold",
        pending_debt_freshness_status="fresh",
        closure_forecast_reweight_direction="supporting-clearance",
        closure_forecast_reweight_score=-0.41,
        target_specific_normalization_noise=_target_specific_normalization_noise,
    )

    assert updates[0] == "clear-risk-strengthened"
    assert updates[2] == "expire-risk"
    assert updates[3] == "none"
    assert updates[5] == "cleared"
    assert updates[7] == "verify-first"


def test_pending_debt_freshness_hotspots_prefers_highest_stale_and_fresh_groups() -> None:
    stale_hotspots = pending_debt_freshness_hotspots(
        [
            {
                "lane": "urgent",
                "kind": "config",
                "pending_debt_freshness_status": "stale",
                "decayed_pending_debt_rate": 0.7,
                "recent_pending_debt_path": "blocked -> stalled",
            },
            {
                "lane": "urgent",
                "kind": "config",
                "pending_debt_freshness_status": "stale",
                "decayed_pending_debt_rate": 0.5,
                "recent_pending_debt_path": "expired",
            },
        ],
        mode="stale",
        target_class_key=_target_class_key,
    )
    fresh_hotspots = pending_debt_freshness_hotspots(
        [
            {
                "lane": "blocked",
                "kind": "setup",
                "pending_debt_freshness_status": "fresh",
                "decayed_pending_resolution_rate": 0.8,
                "recent_pending_debt_path": "confirmed -> cleared",
            }
        ],
        mode="fresh",
        target_class_key=_target_class_key,
    )

    assert stale_hotspots[0]["label"] == "urgent:config"
    assert stale_hotspots[0]["decayed_pending_debt_rate"] == 0.7
    assert fresh_hotspots[0]["label"] == "blocked:setup"


def test_closure_forecast_hotspots_groups_by_direction_and_score() -> None:
    support_hotspots = closure_forecast_hotspots(
        [
            {
                "lane": "urgent",
                "kind": "config",
                "closure_forecast_reweight_direction": "supporting-confirmation",
                "weighted_pending_resolution_support_score": 0.81,
                "recent_pending_debt_path": "confirmed -> pending",
            }
        ],
        mode="support",
        target_class_key=_target_class_key,
    )
    caution_hotspots = closure_forecast_hotspots(
        [
            {
                "lane": "blocked",
                "kind": "setup",
                "closure_forecast_reweight_direction": "supporting-clearance",
                "weighted_pending_debt_caution_score": 0.74,
                "recent_pending_debt_path": "blocked -> stalled -> expired",
            }
        ],
        mode="caution",
        target_class_key=_target_class_key,
    )

    assert support_hotspots[0]["label"] == "urgent:config"
    assert caution_hotspots[0]["label"] == "blocked:setup"
