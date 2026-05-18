from __future__ import annotations


def operator_class_normalization_values(data: dict) -> tuple[str, str, str, str]:
    summary = data.get("operator_summary") or {}
    policy_debt = (
        (summary.get("primary_target_policy_debt_status", "") or "none").replace("-", " ").title()
    )
    class_normalization = (
        (summary.get("primary_target_class_normalization_status", "") or "none")
        .replace("-", " ")
        .title()
    )
    debt_reason = (
        summary.get("primary_target_policy_debt_reason") or "No policy-debt reason is recorded yet."
    )
    normalization_summary = (
        summary.get("trust_normalization_summary")
        or summary.get("policy_debt_summary")
        or "No class-normalization summary is recorded yet."
    )
    return policy_debt, debt_reason, class_normalization, normalization_summary


def operator_class_memory_values(data: dict) -> tuple[str, str, str, str]:
    summary = data.get("operator_summary") or {}
    freshness_status = (
        (summary.get("primary_target_class_memory_freshness_status", "") or "insufficient-data")
        .replace("-", " ")
        .title()
    )
    freshness_reason = (
        summary.get("primary_target_class_memory_freshness_reason")
        or "No class-memory freshness reason is recorded yet."
    )
    class_decay_status = (
        (summary.get("primary_target_class_decay_status", "") or "none").replace("-", " ").title()
    )
    class_decay_summary = (
        summary.get("class_decay_summary")
        or summary.get("class_memory_summary")
        or "No class-memory decay summary is recorded yet."
    )
    return freshness_status, freshness_reason, class_decay_status, class_decay_summary


def operator_class_reweight_values(data: dict) -> tuple[str, str, str, str]:
    summary = data.get("operator_summary") or {}
    direction = (
        (summary.get("primary_target_class_trust_reweight_direction", "") or "neutral")
        .replace("-", " ")
        .title()
    )
    reweight_score = f"{summary.get('primary_target_class_trust_reweight_score', 0.0):.2f}"
    reasons = ", ".join(summary.get("primary_target_class_trust_reweight_reasons") or [])
    if not reasons:
        reasons = "No class reweighting rationale is recorded yet."
    reweight_summary = (
        summary.get("class_reweighting_summary") or "No class reweighting summary is recorded yet."
    )
    return direction, reweight_score, reasons, reweight_summary


def operator_class_momentum_values(data: dict) -> tuple[str, str, str]:
    summary = data.get("operator_summary") or {}
    momentum_status = (
        (summary.get("primary_target_class_trust_momentum_status", "") or "insufficient-data")
        .replace("-", " ")
        .title()
    )
    stability_status = (
        (summary.get("primary_target_class_reweight_stability_status", "") or "watch")
        .replace("-", " ")
        .title()
    )
    transition_status = (
        (summary.get("primary_target_class_reweight_transition_status", "") or "none")
        .replace("-", " ")
        .title()
    )
    transition_reason = (
        summary.get("primary_target_class_reweight_transition_reason")
        or "No class transition reason is recorded yet."
    )
    stability_summary = f"{stability_status} — {transition_status}: {transition_reason}"
    momentum_summary = (
        summary.get("class_momentum_summary")
        or summary.get("class_reweight_stability_summary")
        or "No class momentum summary is recorded yet."
    )
    return momentum_status, stability_summary, momentum_summary


def operator_class_transition_values(data: dict) -> tuple[str, str, str]:
    summary = data.get("operator_summary") or {}
    health_status = (
        (summary.get("primary_target_class_transition_health_status", "") or "none")
        .replace("-", " ")
        .title()
    )
    resolution_status = (
        (summary.get("primary_target_class_transition_resolution_status", "") or "none")
        .replace("-", " ")
        .title()
    )
    transition_summary = (
        summary.get("class_transition_resolution_summary")
        or summary.get("class_transition_health_summary")
        or "No pending transition summary is recorded yet."
    )
    return health_status, resolution_status, transition_summary


def operator_transition_closure_values(
    data: dict,
) -> tuple[str, str, str, str, str, str, str, str, str]:
    summary = data.get("operator_summary") or {}
    closure_label = (
        (summary.get("primary_target_transition_closure_confidence_label", "") or "low")
        .replace("-", " ")
        .title()
    )
    likely_outcome = (
        (summary.get("primary_target_transition_closure_likely_outcome", "") or "none")
        .replace("-", " ")
        .title()
    )
    pending_debt_freshness = (
        (summary.get("primary_target_pending_debt_freshness_status", "") or "insufficient-data")
        .replace("-", " ")
        .title()
    )
    closure_forecast_direction = (
        (summary.get("primary_target_closure_forecast_reweight_direction", "") or "neutral")
        .replace("-", " ")
        .title()
    )
    reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery = (
        (
            summary.get(
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status",
                "",
            )
            or "none"
        )
        .replace("-", " ")
        .title()
    )
    reset_reentry_rebuild_reentry_restore_rerererestore = (
        (
            summary.get(
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status",
                "",
            )
            or "none"
        )
        .replace("-", " ")
        .title()
    )
    reset_reentry_rebuild_reentry_restore_rerererestore_persistence = (
        (
            summary.get(
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status",
                "",
            )
            or "none"
        )
        .replace("-", " ")
        .title()
    )
    reset_reentry_rebuild_reentry_restore_rerererestore_churn = (
        (
            summary.get(
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status",
                "",
            )
            or "none"
        )
        .replace("-", " ")
        .title()
    )
    closure_summary = (
        summary.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_summary"
        )
        or summary.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_summary"
        )
        or summary.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_summary"
        )
        or summary.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_summary"
        )
        or summary.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_summary"
        )
        or summary.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_summary"
        )
        or summary.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_summary"
        )
        or summary.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_summary"
        )
        or summary.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_summary"
        )
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_summary")
        or summary.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_summary"
        )
        or summary.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_summary"
        )
        or summary.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_summary"
        )
        or summary.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_summary"
        )
        or summary.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_summary"
        )
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_reset_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_freshness_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_reset_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_persistence_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_churn_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_refresh_recovery_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reentry_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_freshness_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_reset_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_persistence_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_churn_summary")
        or summary.get("closure_forecast_reset_reentry_rebuild_summary")
        or summary.get("closure_forecast_reset_reentry_refresh_recovery_summary")
        or summary.get("closure_forecast_reset_reentry_freshness_summary")
        or summary.get("closure_forecast_reset_reentry_reset_summary")
        or summary.get("closure_forecast_reset_reentry_persistence_summary")
        or summary.get("closure_forecast_reset_reentry_churn_summary")
        or summary.get("closure_forecast_reset_reentry_summary")
        or summary.get("closure_forecast_reset_refresh_recovery_summary")
        or summary.get("closure_forecast_persistence_reset_summary")
        or summary.get("closure_forecast_reacquisition_freshness_summary")
        or summary.get("closure_forecast_reacquisition_persistence_summary")
        or summary.get("closure_forecast_recovery_churn_summary")
        or summary.get("closure_forecast_reacquisition_summary")
        or summary.get("closure_forecast_refresh_recovery_summary")
        or summary.get("closure_forecast_decay_summary")
        or summary.get("closure_forecast_freshness_summary")
        or summary.get("closure_forecast_hysteresis_summary")
        or summary.get("closure_forecast_momentum_summary")
        or summary.get("closure_forecast_stability_summary")
        or summary.get("closure_forecast_reweighting_summary")
        or summary.get("pending_debt_freshness_summary")
        or summary.get("transition_closure_confidence_summary")
        or "No closure-forecast summary is recorded yet."
    )
    return (
        closure_label,
        likely_outcome,
        pending_debt_freshness,
        closure_forecast_direction,
        reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery,
        reset_reentry_rebuild_reentry_restore_rerererestore,
        reset_reentry_rebuild_reentry_restore_rerererestore_persistence,
        reset_reentry_rebuild_reentry_restore_rerererestore_churn,
        closure_summary,
    )


def operator_calibration_values(data: dict) -> tuple[str, str, str, str]:
    summary = data.get("operator_summary") or {}
    validation_status = summary.get("confidence_validation_status", "") or "insufficient-data"
    calibration_summary = (
        summary.get("confidence_calibration_summary")
        or "No confidence-calibration summary is recorded yet."
    )
    high_hit_rate = f"{summary.get('high_confidence_hit_rate', 0.0):.0%}"
    reopened_count = f"{summary.get('reopened_recommendation_count', 0)} reopened"
    return (
        validation_status.replace("-", " ").title(),
        calibration_summary,
        high_hit_rate,
        reopened_count,
    )
