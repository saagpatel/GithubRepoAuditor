from __future__ import annotations


def build_trend_summary_context(
    *,
    current_attention: dict[str, dict],
    current_attention_keys: set[str],
    previous_attention_keys: set[str],
    earlier_attention_keys: set[str],
    previous_snapshot: dict | None,
    quiet_streak_runs: int,
    resolution_targets: list[dict],
    recommendation_drift: dict,
    recent_runs: list[dict],
    trend_status_fn,
    primary_target_fn,
    primary_target_reason_fn,
    primary_target_done_criteria_fn,
    closure_guidance_fn,
    accountability_summary_fn,
    summary_decision_memory_fn,
    trend_summary_fn,
    queue_identity,
) -> dict:
    new_attention_keys = current_attention_keys - previous_attention_keys
    resolved_attention_count = len(previous_attention_keys - current_attention_keys)
    persisting_attention_count = len(current_attention_keys & previous_attention_keys)
    reopened_attention_count = len(
        {key for key in new_attention_keys if key in earlier_attention_keys}
    )
    new_blocked_attention = any(
        current_attention.get(key, {}).get("lane") == "blocked" for key in new_attention_keys
    )
    current_attention_count = len(current_attention_keys)
    previous_attention_count = len(previous_attention_keys)

    trend_status = trend_status_fn(
        current_attention_count=current_attention_count,
        previous_attention_count=previous_attention_count,
        new_blocked_attention=new_blocked_attention,
        quiet_streak_runs=quiet_streak_runs,
        has_previous=previous_snapshot is not None,
    )
    primary_target = primary_target_fn(resolution_targets)
    primary_target_reason = primary_target_reason_fn(primary_target)
    primary_target_done_criteria = primary_target_done_criteria_fn(primary_target)
    closure_guidance = closure_guidance_fn(primary_target, primary_target_done_criteria)
    chronic_item_count = sum(
        1 for item in resolution_targets if item.get("aging_status") == "chronic"
    )
    newly_stale_count = sum(1 for item in resolution_targets if item.get("newly_stale"))
    accountability_summary = accountability_summary_fn(
        primary_target=primary_target,
        primary_target_reason=primary_target_reason,
        closure_guidance=closure_guidance,
        chronic_item_count=chronic_item_count,
        newly_stale_count=newly_stale_count,
        quiet_streak_runs=quiet_streak_runs,
    )
    if primary_target:
        primary_target = {
            **primary_target,
            "reason": primary_target_reason,
            "done_criteria": primary_target_done_criteria,
            "closure_guidance": closure_guidance,
            "recommendation_drift_status": recommendation_drift["recommendation_drift_status"],
        }
    decision_memory = summary_decision_memory_fn(
        primary_target,
        recent_runs,
        queue_identity=queue_identity,
    )
    trend_summary = trend_summary_fn(
        trend_status=trend_status,
        quiet_streak_runs=quiet_streak_runs,
        new_attention_count=len(new_attention_keys),
        resolved_attention_count=resolved_attention_count,
        persisting_attention_count=persisting_attention_count,
        reopened_attention_count=reopened_attention_count,
        primary_target=primary_target,
    )
    return {
        "new_attention_keys": new_attention_keys,
        "resolved_attention_count": resolved_attention_count,
        "persisting_attention_count": persisting_attention_count,
        "reopened_attention_count": reopened_attention_count,
        "current_attention_count": current_attention_count,
        "previous_attention_count": previous_attention_count,
        "trend_status": trend_status,
        "primary_target": primary_target,
        "primary_target_reason": primary_target_reason,
        "primary_target_done_criteria": primary_target_done_criteria,
        "closure_guidance": closure_guidance,
        "accountability_summary": accountability_summary,
        "decision_memory": decision_memory,
        "trend_summary": trend_summary,
        "chronic_item_count": chronic_item_count,
        "newly_stale_count": newly_stale_count,
    }
