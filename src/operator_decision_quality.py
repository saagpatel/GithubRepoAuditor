from __future__ import annotations

from typing import Any

CONTRACT_VERSION = "decision_quality_v1"
AUTHORITY_CAP = "bounded-automation"
DEFAULT_EVIDENCE_WINDOW_RUNS = 20
DEFAULT_VALIDATION_WINDOW_RUNS = 2


def build_confidence_calibration(history: list[dict[str, Any]]) -> dict[str, Any]:
    from src import operator_resolution_trend as _operator_resolution_trend

    return _operator_resolution_trend._build_confidence_calibration(history)


def confidence_validation_status(
    *,
    judged_count: int,
    high_confidence_hit_rate: float,
    reopened_recommendation_count: int,
    reopened_high_count: int,
) -> str:
    from src import operator_resolution_trend as _operator_resolution_trend

    return _operator_resolution_trend._confidence_validation_status(
        judged_count=judged_count,
        high_confidence_hit_rate=high_confidence_hit_rate,
        reopened_recommendation_count=reopened_recommendation_count,
        reopened_high_count=reopened_high_count,
    )


def confidence_calibration_summary(
    *,
    confidence_validation_status: str,
    high_confidence_hit_rate: float,
    medium_confidence_hit_rate: float,
    low_confidence_caution_rate: float,
    reopened_recommendation_count: int,
    judged_count: int,
) -> str:
    from src import operator_resolution_trend as _operator_resolution_trend

    return _operator_resolution_trend._confidence_calibration_summary(
        confidence_validation_status=confidence_validation_status,
        high_confidence_hit_rate=high_confidence_hit_rate,
        medium_confidence_hit_rate=medium_confidence_hit_rate,
        low_confidence_caution_rate=low_confidence_caution_rate,
        reopened_recommendation_count=reopened_recommendation_count,
        judged_count=judged_count,
    )


def build_decision_quality_v1(
    *,
    confidence_calibration: dict[str, Any],
    confidence: dict[str, Any],
    resolution_trend: dict[str, Any],
    evidence_window_runs: int = DEFAULT_EVIDENCE_WINDOW_RUNS,
    validation_window_runs: int = DEFAULT_VALIDATION_WINDOW_RUNS,
) -> dict[str, Any]:
    judged_recommendation_count = sum(
        int(confidence_calibration.get(key, 0) or 0)
        for key in (
            "validated_recommendation_count",
            "partially_validated_recommendation_count",
            "unresolved_recommendation_count",
            "reopened_recommendation_count",
        )
    )
    validation_status = str(
        confidence_calibration.get("confidence_validation_status", "insufficient-data")
    )
    downgrade_reasons = _downgrade_reasons(
        validation_status=validation_status,
        confidence=confidence,
        resolution_trend=resolution_trend,
    )
    human_skepticism_required = bool(
        validation_status in {"mixed", "noisy", "insufficient-data"}
        or confidence.get("primary_target_trust_policy") in {"verify-first", "monitor"}
        or confidence.get("next_action_trust_policy") in {"verify-first", "monitor"}
        or downgrade_reasons
    )
    return {
        "contract_version": CONTRACT_VERSION,
        "authority_cap": AUTHORITY_CAP,
        "evidence_window_runs": int(
            confidence_calibration.get("confidence_window_runs", evidence_window_runs)
            or evidence_window_runs
        ),
        "validation_window_runs": validation_window_runs,
        "judged_recommendation_count": judged_recommendation_count,
        "validated_recommendation_count": int(
            confidence_calibration.get("validated_recommendation_count", 0) or 0
        ),
        "partially_validated_recommendation_count": int(
            confidence_calibration.get("partially_validated_recommendation_count", 0) or 0
        ),
        "reopened_recommendation_count": int(
            confidence_calibration.get("reopened_recommendation_count", 0) or 0
        ),
        "unresolved_recommendation_count": int(
            confidence_calibration.get("unresolved_recommendation_count", 0) or 0
        ),
        "high_confidence_hit_rate": float(
            confidence_calibration.get("high_confidence_hit_rate", 0.0) or 0.0
        ),
        "medium_confidence_hit_rate": float(
            confidence_calibration.get("medium_confidence_hit_rate", 0.0) or 0.0
        ),
        "low_confidence_caution_rate": float(
            confidence_calibration.get("low_confidence_caution_rate", 0.0) or 0.0
        ),
        "confidence_validation_status": validation_status,
        "decision_quality_status": _decision_quality_status(
            validation_status=validation_status,
            human_skepticism_required=human_skepticism_required,
            confidence=confidence,
        ),
        "human_skepticism_required": human_skepticism_required,
        "downgrade_reasons": downgrade_reasons,
        "recommendation_quality_summary": str(
            confidence.get(
                "recommendation_quality_summary",
                "No recommendation-quality summary is recorded yet.",
            )
        ),
        "confidence_calibration_summary": str(
            confidence_calibration.get(
                "confidence_calibration_summary",
                "No confidence-calibration summary is recorded yet.",
            )
        ),
        "recent_validation_outcomes": list(
            confidence_calibration.get("recent_validation_outcomes") or []
        ),
        "primary_target_trust_policy": str(
            confidence.get("primary_target_trust_policy", "monitor")
        ),
        "primary_target_trust_policy_reason": str(
            confidence.get(
                "primary_target_trust_policy_reason",
                "No trust-policy reason is recorded yet.",
            )
        ),
        "next_action_trust_policy": str(confidence.get("next_action_trust_policy", "monitor")),
        "next_action_trust_policy_reason": str(
            confidence.get(
                "next_action_trust_policy_reason",
                "No trust-policy reason is recorded yet.",
            )
        ),
        "adaptive_confidence_summary": str(
            confidence.get(
                "adaptive_confidence_summary",
                "No adaptive confidence summary is recorded yet.",
            )
        ),
    }


def decision_quality_from_summary(summary: dict[str, Any]) -> dict[str, Any]:
    contract = summary.get("decision_quality_v1")
    if isinstance(contract, dict) and contract:
        return contract
    confidence_validation_status = str(
        summary.get("confidence_validation_status", "insufficient-data")
    )
    return {
        "contract_version": CONTRACT_VERSION,
        "authority_cap": AUTHORITY_CAP,
        "evidence_window_runs": int(
            summary.get("confidence_window_runs", DEFAULT_EVIDENCE_WINDOW_RUNS)
            or DEFAULT_EVIDENCE_WINDOW_RUNS
        ),
        "validation_window_runs": DEFAULT_VALIDATION_WINDOW_RUNS,
        "judged_recommendation_count": int(summary.get("validated_recommendation_count", 0) or 0)
        + int(summary.get("partially_validated_recommendation_count", 0) or 0)
        + int(summary.get("unresolved_recommendation_count", 0) or 0)
        + int(summary.get("reopened_recommendation_count", 0) or 0),
        "validated_recommendation_count": int(
            summary.get("validated_recommendation_count", 0) or 0
        ),
        "partially_validated_recommendation_count": int(
            summary.get("partially_validated_recommendation_count", 0) or 0
        ),
        "reopened_recommendation_count": int(summary.get("reopened_recommendation_count", 0) or 0),
        "unresolved_recommendation_count": int(
            summary.get("unresolved_recommendation_count", 0) or 0
        ),
        "high_confidence_hit_rate": float(summary.get("high_confidence_hit_rate", 0.0) or 0.0),
        "medium_confidence_hit_rate": float(summary.get("medium_confidence_hit_rate", 0.0) or 0.0),
        "low_confidence_caution_rate": float(
            summary.get("low_confidence_caution_rate", 0.0) or 0.0
        ),
        "confidence_validation_status": confidence_validation_status,
        "decision_quality_status": _decision_quality_status(
            validation_status=confidence_validation_status,
            human_skepticism_required=bool(
                summary.get("human_skepticism_required", False)
                or summary.get("primary_target_trust_policy") in {"verify-first", "monitor"}
                or summary.get("next_action_trust_policy") in {"verify-first", "monitor"}
            ),
            confidence=summary,
        ),
        "human_skepticism_required": bool(
            summary.get("human_skepticism_required", False)
            or confidence_validation_status in {"mixed", "noisy", "insufficient-data"}
        ),
        "downgrade_reasons": list(summary.get("downgrade_reasons") or []),
        "recommendation_quality_summary": str(
            summary.get(
                "recommendation_quality_summary",
                "No recommendation-quality summary is recorded yet.",
            )
        ),
        "confidence_calibration_summary": str(
            summary.get(
                "confidence_calibration_summary",
                "No confidence-calibration summary is recorded yet.",
            )
        ),
        "recent_validation_outcomes": list(summary.get("recent_validation_outcomes") or []),
        "primary_target_trust_policy": str(summary.get("primary_target_trust_policy", "monitor")),
        "primary_target_trust_policy_reason": str(
            summary.get(
                "primary_target_trust_policy_reason",
                "No trust-policy reason is recorded yet.",
            )
        ),
        "next_action_trust_policy": str(summary.get("next_action_trust_policy", "monitor")),
        "next_action_trust_policy_reason": str(
            summary.get(
                "next_action_trust_policy_reason",
                "No trust-policy reason is recorded yet.",
            )
        ),
        "adaptive_confidence_summary": str(
            summary.get(
                "adaptive_confidence_summary",
                "No adaptive confidence summary is recorded yet.",
            )
        ),
    }


def historical_decision_quality_from_summary(summary: dict[str, Any]) -> dict[str, Any]:
    contract = summary.get("decision_quality_v1")
    if isinstance(contract, dict) and contract:
        return contract
    legacy_summary = str(
        summary.get(
            "recommendation_quality_summary",
            "Legacy run predates the decision quality contract.",
        )
    )
    return {
        "contract_version": CONTRACT_VERSION,
        "authority_cap": AUTHORITY_CAP,
        "evidence_window_runs": int(summary.get("confidence_window_runs", 0) or 0),
        "validation_window_runs": 0,
        "judged_recommendation_count": 0,
        "validated_recommendation_count": 0,
        "partially_validated_recommendation_count": 0,
        "reopened_recommendation_count": 0,
        "unresolved_recommendation_count": 0,
        "high_confidence_hit_rate": 0.0,
        "medium_confidence_hit_rate": 0.0,
        "low_confidence_caution_rate": 0.0,
        "confidence_validation_status": "insufficient-data",
        "decision_quality_status": "insufficient-data",
        "human_skepticism_required": True,
        "downgrade_reasons": ["legacy-run-without-decision-quality-contract"],
        "recommendation_quality_summary": legacy_summary,
        "confidence_calibration_summary": (
            "Legacy run predates decision_quality_v1; treat calibration as insufficient-data."
        ),
        "recent_validation_outcomes": [],
        "primary_target_trust_policy": "monitor",
        "primary_target_trust_policy_reason": (
            "Legacy run predates decision_quality_v1, so trust policy is downgraded to monitor."
        ),
        "next_action_trust_policy": "monitor",
        "next_action_trust_policy_reason": (
            "Legacy run predates decision_quality_v1, so next-action trust is downgraded to monitor."
        ),
        "adaptive_confidence_summary": (
            "Decision quality is treated as insufficient-data for legacy runs that predate the contract."
        ),
    }


def _decision_quality_status(
    *,
    validation_status: str,
    human_skepticism_required: bool,
    confidence: dict[str, Any],
) -> str:
    if validation_status == "noisy":
        return "needs-skepticism"
    if validation_status == "insufficient-data":
        return "insufficient-data"
    if human_skepticism_required or confidence.get("primary_target_trust_policy") == "monitor":
        return "use-with-review"
    return "trusted"


def _downgrade_reasons(
    *,
    validation_status: str,
    confidence: dict[str, Any],
    resolution_trend: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if validation_status == "mixed":
        reasons.append("mixed-calibration")
    elif validation_status == "noisy":
        reasons.append("noisy-calibration")
    elif validation_status == "insufficient-data":
        reasons.append("insufficient-calibration-history")

    primary_policy = str(confidence.get("primary_target_trust_policy", "monitor"))
    next_policy = str(confidence.get("next_action_trust_policy", "monitor"))
    if primary_policy == "verify-first":
        reasons.append("primary-target-needs-verification")
    elif primary_policy == "monitor":
        reasons.append("primary-target-monitor-only")
    if next_policy == "verify-first":
        reasons.append("next-action-needs-verification")
    elif next_policy == "monitor":
        reasons.append("next-action-monitor-only")

    if str(resolution_trend.get("primary_target_exception_status", "none")) not in {"", "none"}:
        reasons.append("trust-exception-active")
    if str(resolution_trend.get("primary_target_trust_recovery_status", "none")) == "blocked":
        reasons.append("trust-recovery-blocked")
    if str(resolution_trend.get("primary_target_exception_retirement_status", "none")) == "blocked":
        reasons.append("exception-retirement-blocked")
    if str(resolution_trend.get("primary_target_policy_debt_status", "none")) == "class-debt":
        reasons.append("class-policy-debt")
    if str(resolution_trend.get("recommendation_drift_status", "")) == "drifting":
        reasons.append("recommendation-drift")
    return reasons
