def _repo_item_label(item: dict, *, fallback: str) -> str:
    return (
        f"{item.get('repo')}: {item.get('title')}"
        if item.get("repo")
        else item.get("title", "")
    ) or fallback


def operator_watch_values(data: dict) -> tuple[str, str, str]:
    summary = data.get("operator_summary") or {}
    next_mode = summary.get("next_recommended_run_mode", "") or "n/a"
    strategy = summary.get("watch_strategy", "") or "manual"
    decision = summary.get("watch_decision_summary", "") or "No watch guidance is recorded."
    return next_mode, strategy, decision


def operator_handoff_values(data: dict) -> tuple[str, str, str]:
    summary = data.get("operator_summary") or {}
    what_changed = summary.get("what_changed", "") or "No operator change summary is recorded."
    why_it_matters = (
        summary.get("why_it_matters", "") or "No additional operator impact is recorded."
    )
    next_action = summary.get("what_to_do_next", "") or "Continue the normal operator loop."
    return what_changed, why_it_matters, next_action


def operator_trend_values(data: dict) -> tuple[str, str, str, str]:
    summary = data.get("operator_summary") or {}
    trend_status = summary.get("trend_status", "") or "stable"
    trend_summary = summary.get("trend_summary", "") or "No trend summary is recorded yet."
    primary_target = summary.get("primary_target") or {}
    primary_target_label = _repo_item_label(primary_target, fallback="No active target")
    counts_summary = (
        f"New {summary.get('new_attention_count', 0)} | "
        f"Resolved {summary.get('resolved_attention_count', 0)} | "
        f"Persisting {summary.get('persisting_attention_count', 0)}"
    )
    if summary.get("quiet_streak_runs", 0):
        counts_summary += f" | Quiet streak {summary.get('quiet_streak_runs', 0)}"
    return (
        trend_status.replace("_", " ").title(),
        trend_summary,
        primary_target_label,
        counts_summary,
    )


def operator_accountability_values(data: dict) -> tuple[str, str, str]:
    summary = data.get("operator_summary") or {}
    primary_target_reason = (
        summary.get("primary_target_reason", "") or "No top-target rationale is recorded yet."
    )
    closure_guidance = summary.get("closure_guidance", "") or "No closure guidance is recorded yet."
    longest_item = summary.get("longest_persisting_item") or {}
    longest_label = _repo_item_label(longest_item, fallback="No persisting item")
    aging_pressure = (
        f"Chronic {summary.get('chronic_item_count', 0)} | "
        f"Newly stale {summary.get('newly_stale_count', 0)} | "
        f"Longest {longest_label}"
    )
    return primary_target_reason, closure_guidance, aging_pressure


def operator_decision_memory_values(data: dict) -> tuple[str, str, str, str]:
    summary = data.get("operator_summary") or {}
    last_intervention = summary.get("primary_target_last_intervention") or {}
    last_outcome = summary.get("primary_target_last_outcome", "") or "no-change"
    resolution_evidence = (
        summary.get("resolution_evidence_summary", "") or "No resolution evidence is recorded yet."
    )
    if last_intervention:
        when = (last_intervention.get("recorded_at") or "")[:10]
        event_type = last_intervention.get("event_type", "recorded")
        outcome = last_intervention.get("outcome", event_type)
        last_intervention_label = f"{when} {event_type} ({outcome})".strip()
    else:
        last_intervention_label = "No recent intervention recorded"
    recovery_counts = (
        f"Confirmed resolved {summary.get('confirmed_resolved_count', 0)} | "
        f"Reopened {summary.get('reopened_after_resolution_count', 0)}"
    )
    return (
        last_intervention_label,
        last_outcome.replace("-", " ").title(),
        resolution_evidence,
        recovery_counts,
    )


def operator_confidence_values(data: dict) -> tuple[str, str, str, str]:
    summary = data.get("operator_summary") or {}
    primary_confidence = (
        f"{summary.get('primary_target_confidence_label', 'low').title()} "
        f"({summary.get('primary_target_confidence_score', 0.0):.2f})"
    )
    reasons = summary.get("primary_target_confidence_reasons") or []
    confidence_reason = reasons[0] if reasons else "No confidence rationale is recorded yet."
    next_action_confidence = (
        f"{summary.get('next_action_confidence_label', 'low').title()} "
        f"({summary.get('next_action_confidence_score', 0.0):.2f})"
    )
    recommendation_quality = (
        summary.get("recommendation_quality_summary")
        or "No recommendation-quality summary is recorded yet."
    )
    return primary_confidence, confidence_reason, next_action_confidence, recommendation_quality


def operator_trust_values(data: dict) -> tuple[str, str, str]:
    summary = data.get("operator_summary") or {}
    trust_policy = (
        (summary.get("primary_target_trust_policy", "") or "monitor").replace("-", " ").title()
    )
    trust_reason = (
        summary.get("primary_target_trust_policy_reason")
        or "No trust-policy reason is recorded yet."
    )
    adaptive_summary = (
        summary.get("adaptive_confidence_summary")
        or "No adaptive confidence summary is recorded yet."
    )
    return trust_policy, trust_reason, adaptive_summary


def operator_exception_values(data: dict) -> tuple[str, str, str, str]:
    summary = data.get("operator_summary") or {}
    exception_status = (
        (summary.get("primary_target_exception_status", "") or "none").replace("-", " ").title()
    )
    exception_reason = (
        summary.get("primary_target_exception_reason")
        or "No trust-policy exception reason is recorded yet."
    )
    drift_status = (
        (summary.get("recommendation_drift_status", "") or "stable").replace("-", " ").title()
    )
    drift_summary = (
        summary.get("recommendation_drift_summary")
        or "No recommendation-drift summary is recorded yet."
    )
    return exception_status, exception_reason, drift_status, drift_summary


def operator_learning_values(data: dict) -> tuple[str, str, str, str]:
    summary = data.get("operator_summary") or {}
    recovery_status = (
        (summary.get("primary_target_trust_recovery_status", "") or "none")
        .replace("-", " ")
        .title()
    )
    recovery_reason = (
        summary.get("primary_target_trust_recovery_reason")
        or "No trust-recovery reason is recorded yet."
    )
    pattern_status = (
        (summary.get("primary_target_exception_pattern_status", "") or "none")
        .replace("-", " ")
        .title()
    )
    pattern_summary = (
        summary.get("exception_pattern_summary") or "No exception-pattern summary is recorded yet."
    )
    return recovery_status, recovery_reason, pattern_status, pattern_summary


def operator_retirement_values(data: dict) -> tuple[str, str, str, str]:
    summary = data.get("operator_summary") or {}
    recovery_confidence = (
        f"{summary.get('primary_target_recovery_confidence_label', 'low').title()} "
        f"({summary.get('primary_target_recovery_confidence_score', 0.0):.2f})"
    )
    retirement_status = (
        (summary.get("primary_target_exception_retirement_status", "") or "none")
        .replace("-", " ")
        .title()
    )
    retirement_reason = (
        summary.get("primary_target_exception_retirement_reason")
        or "No exception-retirement reason is recorded yet."
    )
    retirement_summary = (
        summary.get("exception_retirement_summary")
        or "No exception-retirement summary is recorded yet."
    )
    return recovery_confidence, retirement_status, retirement_reason, retirement_summary
