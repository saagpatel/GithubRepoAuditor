from __future__ import annotations


def build_resolution_trend_topline_payload(
    *,
    trend_status: str,
    new_attention_count: int,
    resolved_attention_count: int,
    persisting_attention_count: int,
    reopened_attention_count: int,
    history_window_runs: int,
    quiet_streak_runs: int,
    primary_target: dict | None,
    primary_target_reason: str,
    primary_target_done_criteria: str,
    closure_guidance: str,
    current_attention: dict[str, dict],
    chronic_item_count: int,
    newly_stale_count: int,
    resolution_targets: list[dict],
    accountability_summary: str,
    trend_summary: str,
    recommendation_drift: dict,
    exception_learning: dict,
    exception_retirement: dict,
    class_normalization: dict,
    class_memory_decay: dict,
    class_trust_reweighting: dict,
    attention_age_bands_fn,
    longest_persisting_item_fn,
    policy_debt_summary_fn,
    trust_normalization_summary_fn,
) -> dict:
    return {
        "trend_status": trend_status,
        "new_attention_count": new_attention_count,
        "resolved_attention_count": resolved_attention_count,
        "persisting_attention_count": persisting_attention_count,
        "reopened_attention_count": reopened_attention_count,
        "history_window_runs": history_window_runs,
        "quiet_streak_runs": quiet_streak_runs,
        "aging_status": primary_target.get("aging_status", "fresh") if primary_target else "fresh",
        "primary_target_reason": primary_target_reason,
        "primary_target_done_criteria": primary_target_done_criteria,
        "closure_guidance": closure_guidance,
        "attention_age_bands": attention_age_bands_fn(current_attention),
        "chronic_item_count": chronic_item_count,
        "newly_stale_count": newly_stale_count,
        "longest_persisting_item": longest_persisting_item_fn(resolution_targets),
        "accountability_summary": accountability_summary,
        "primary_target": primary_target,
        "resolution_targets": resolution_targets[:5],
        "trend_summary": trend_summary,
        "primary_target_exception_status": recommendation_drift["primary_target_exception_status"],
        "primary_target_exception_reason": recommendation_drift["primary_target_exception_reason"],
        "recommendation_drift_status": recommendation_drift["recommendation_drift_status"],
        "recommendation_drift_summary": recommendation_drift["recommendation_drift_summary"],
        "policy_flip_hotspots": recommendation_drift["policy_flip_hotspots"],
        "primary_target_exception_pattern_status": exception_learning[
            "primary_target_exception_pattern_status"
        ],
        "primary_target_exception_pattern_reason": exception_learning[
            "primary_target_exception_pattern_reason"
        ],
        "primary_target_trust_recovery_status": exception_learning[
            "primary_target_trust_recovery_status"
        ],
        "primary_target_trust_recovery_reason": exception_learning[
            "primary_target_trust_recovery_reason"
        ],
        "exception_pattern_summary": exception_learning["exception_pattern_summary"],
        "false_positive_exception_hotspots": exception_learning[
            "false_positive_exception_hotspots"
        ],
        "trust_recovery_window_runs": exception_learning["trust_recovery_window_runs"],
        "primary_target_recovery_confidence_score": exception_retirement[
            "primary_target_recovery_confidence_score"
        ],
        "primary_target_recovery_confidence_label": exception_retirement[
            "primary_target_recovery_confidence_label"
        ],
        "primary_target_recovery_confidence_reasons": exception_retirement[
            "primary_target_recovery_confidence_reasons"
        ],
        "recovery_confidence_summary": exception_retirement["recovery_confidence_summary"],
        "primary_target_exception_retirement_status": exception_retirement[
            "primary_target_exception_retirement_status"
        ],
        "primary_target_exception_retirement_reason": exception_retirement[
            "primary_target_exception_retirement_reason"
        ],
        "exception_retirement_summary": exception_retirement["exception_retirement_summary"],
        "retired_exception_hotspots": exception_retirement["retired_exception_hotspots"],
        "sticky_exception_hotspots": exception_retirement["sticky_exception_hotspots"],
        "exception_retirement_window_runs": exception_retirement[
            "exception_retirement_window_runs"
        ],
        "primary_target_policy_debt_status": primary_target.get(
            "policy_debt_status", class_normalization["primary_target_policy_debt_status"]
        )
        if primary_target
        else class_normalization["primary_target_policy_debt_status"],
        "primary_target_policy_debt_reason": primary_target.get(
            "policy_debt_reason", class_normalization["primary_target_policy_debt_reason"]
        )
        if primary_target
        else class_normalization["primary_target_policy_debt_reason"],
        "primary_target_class_normalization_status": primary_target.get(
            "class_normalization_status",
            class_normalization["primary_target_class_normalization_status"],
        )
        if primary_target
        else class_normalization["primary_target_class_normalization_status"],
        "primary_target_class_normalization_reason": primary_target.get(
            "class_normalization_reason",
            class_normalization["primary_target_class_normalization_reason"],
        )
        if primary_target
        else class_normalization["primary_target_class_normalization_reason"],
        "policy_debt_summary": policy_debt_summary_fn(
            primary_target, class_normalization["policy_debt_hotspots"]
        )
        if primary_target
        else class_normalization["policy_debt_summary"],
        "trust_normalization_summary": trust_normalization_summary_fn(
            primary_target,
            class_normalization["normalized_class_hotspots"],
            class_normalization["policy_debt_hotspots"],
        )
        if primary_target
        else class_normalization["trust_normalization_summary"],
        "policy_debt_hotspots": class_normalization["policy_debt_hotspots"],
        "normalized_class_hotspots": class_normalization["normalized_class_hotspots"],
        "class_normalization_window_runs": class_normalization["class_normalization_window_runs"],
        "primary_target_class_memory_freshness_status": class_memory_decay[
            "primary_target_class_memory_freshness_status"
        ],
        "primary_target_class_memory_freshness_reason": class_memory_decay[
            "primary_target_class_memory_freshness_reason"
        ],
        "primary_target_class_decay_status": class_memory_decay[
            "primary_target_class_decay_status"
        ],
        "primary_target_class_decay_reason": class_memory_decay[
            "primary_target_class_decay_reason"
        ],
        "class_memory_summary": class_memory_decay["class_memory_summary"],
        "class_decay_summary": class_memory_decay["class_decay_summary"],
        "stale_class_memory_hotspots": class_memory_decay["stale_class_memory_hotspots"],
        "fresh_class_signal_hotspots": class_memory_decay["fresh_class_signal_hotspots"],
        "class_decay_window_runs": class_memory_decay["class_decay_window_runs"],
        "primary_target_weighted_class_support_score": class_trust_reweighting[
            "primary_target_weighted_class_support_score"
        ],
        "primary_target_weighted_class_caution_score": class_trust_reweighting[
            "primary_target_weighted_class_caution_score"
        ],
        "primary_target_class_trust_reweight_score": class_trust_reweighting[
            "primary_target_class_trust_reweight_score"
        ],
        "primary_target_class_trust_reweight_direction": class_trust_reweighting[
            "primary_target_class_trust_reweight_direction"
        ],
        "primary_target_class_trust_reweight_reasons": class_trust_reweighting[
            "primary_target_class_trust_reweight_reasons"
        ],
        "class_reweighting_summary": class_trust_reweighting["class_reweighting_summary"],
        "supporting_class_hotspots": class_trust_reweighting["supporting_class_hotspots"],
        "caution_class_hotspots": class_trust_reweighting["caution_class_hotspots"],
        "class_reweighting_window_runs": class_trust_reweighting["class_reweighting_window_runs"],
    }
