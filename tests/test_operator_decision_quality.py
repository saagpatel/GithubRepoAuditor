from __future__ import annotations

from src.operator_decision_quality import (
    build_decision_quality_v1,
    decision_quality_from_summary,
)


def test_build_decision_quality_v1_marks_noisy_guidance_as_skeptical() -> None:
    decision_quality = build_decision_quality_v1(
        confidence_calibration={
            "confidence_validation_status": "noisy",
            "confidence_window_runs": 8,
            "validated_recommendation_count": 1,
            "partially_validated_recommendation_count": 1,
            "unresolved_recommendation_count": 2,
            "reopened_recommendation_count": 2,
            "high_confidence_hit_rate": 0.4,
            "medium_confidence_hit_rate": 0.5,
            "low_confidence_caution_rate": 1.0,
            "recent_validation_outcomes": [],
            "confidence_calibration_summary": "Recent high-confidence guidance has been noisy.",
        },
        confidence={
            "recommendation_quality_summary": "Tentative recommendation; verify before acting.",
            "primary_target_trust_policy": "verify-first",
            "primary_target_trust_policy_reason": "Recent calibration is noisy enough that this recommendation should be verified before acting on it.",
            "next_action_trust_policy": "verify-first",
            "next_action_trust_policy_reason": "Recent calibration is noisy enough that this recommendation should be verified before acting on it.",
            "adaptive_confidence_summary": "Calibration is noisy, so the recommendation was softened and should be verified before acting.",
        },
        resolution_trend={
            "primary_target": {"title": "Review RepoA"},
            "primary_target_exception_status": "softened-for-noise",
            "primary_target_trust_recovery_status": "blocked",
            "primary_target_exception_retirement_status": "blocked",
            "primary_target_policy_debt_status": "class-debt",
            "recommendation_drift_status": "drifting",
        },
    )

    assert decision_quality["decision_quality_status"] == "needs-skepticism"
    assert decision_quality["human_skepticism_required"] is True
    assert decision_quality["authority_cap"] == "bounded-automation"
    assert "noisy-calibration" in decision_quality["downgrade_reasons"]
    assert "primary-target-needs-verification" in decision_quality["downgrade_reasons"]
    assert "trust-recovery-blocked" in decision_quality["downgrade_reasons"]


def test_decision_quality_from_summary_backfills_legacy_operator_fields() -> None:
    summary = {
        "confidence_validation_status": "healthy",
        "confidence_window_runs": 6,
        "validated_recommendation_count": 3,
        "partially_validated_recommendation_count": 1,
        "unresolved_recommendation_count": 0,
        "reopened_recommendation_count": 0,
        "high_confidence_hit_rate": 0.75,
        "medium_confidence_hit_rate": 0.67,
        "low_confidence_caution_rate": 1.0,
        "recommendation_quality_summary": "Strong recommendation because the next step is tied directly to the current top target.",
        "confidence_calibration_summary": "Recent high-confidence recommendations are validating well.",
        "primary_target_trust_policy": "act-with-review",
        "primary_target_trust_policy_reason": "Healthy calibration supports a confident next step, with light operator judgment.",
        "next_action_trust_policy": "act-with-review",
        "next_action_trust_policy_reason": "Healthy calibration supports a confident next step, with light operator judgment.",
        "adaptive_confidence_summary": "Calibration is validating well, so the recommendation can be acted on with light operator review.",
        "recent_validation_outcomes": [],
    }

    decision_quality = decision_quality_from_summary(summary)

    assert decision_quality["contract_version"] == "decision_quality_v1"
    assert decision_quality["decision_quality_status"] == "trusted"
    assert decision_quality["judged_recommendation_count"] == 4
    assert decision_quality["recommendation_quality_summary"] == summary[
        "recommendation_quality_summary"
    ]


def test_build_decision_quality_trusts_healthy_quiet_monitor_runs() -> None:
    decision_quality = build_decision_quality_v1(
        confidence_calibration={
            "confidence_validation_status": "healthy",
            "confidence_window_runs": 8,
            "validated_recommendation_count": 3,
            "partially_validated_recommendation_count": 1,
            "unresolved_recommendation_count": 0,
            "reopened_recommendation_count": 0,
            "high_confidence_hit_rate": 1.0,
            "medium_confidence_hit_rate": 1.0,
            "low_confidence_caution_rate": 0.0,
            "recent_validation_outcomes": [],
            "confidence_calibration_summary": "Recent high-confidence recommendations are validating well.",
        },
        confidence={
            "recommendation_quality_summary": "Light-touch monitor guidance.",
            "primary_target_trust_policy": "monitor",
            "next_action_trust_policy": "verify-first",
            "adaptive_confidence_summary": "Keep monitoring instead of forcing action.",
        },
        resolution_trend={"primary_target": {}, "recommendation_drift_status": "stable"},
    )

    assert decision_quality["decision_quality_status"] == "trusted"
    assert decision_quality["human_skepticism_required"] is False
    assert decision_quality["downgrade_reasons"] == []
