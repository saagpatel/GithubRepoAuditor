from __future__ import annotations

import argparse
import json
from pathlib import Path


ISSUE_LABEL = "scheduled-audit-handoff"


def _latest_artifact(output_dir: Path, pattern: str) -> Path | None:
    matches = sorted(output_dir.glob(pattern))
    return matches[-1] if matches else None


def _load_json(path: Path | None) -> dict:
    if not path or not path.exists():
        return {}
    return json.loads(path.read_text())


def _queue_counts(summary: dict) -> str:
    counts = summary.get("counts", {})
    return (
        f"{counts.get('blocked', 0)} blocked, "
        f"{counts.get('urgent', 0)} urgent, "
        f"{counts.get('ready', 0)} ready, "
        f"{counts.get('deferred', 0)} deferred"
    )


def _has_regressions(diff_data: dict) -> bool:
    regressions = diff_data.get("score_regressions", []) or []
    tier_changes = diff_data.get("tier_changes", []) or []
    downgrades = [
        item
        for item in tier_changes
        if item.get("old_tier") in {"shipped", "functional"}
        and item.get("new_tier") in {"wip", "skeleton", "abandoned"}
    ]
    return bool(regressions or downgrades)


def _issue_candidate(
    summary: dict,
    diff_data: dict,
    username: str,
    body_path: Path,
    *,
    issue_state: str = "absent",
    issue_number: str = "",
    issue_url: str = "",
) -> dict:
    urgency = summary.get("urgency", "quiet")
    regressions_detected = _has_regressions(diff_data)
    noisy = urgency in {"blocked", "urgent"} or regressions_detected
    reason = summary.get("escalation_reason", "quiet")
    if regressions_detected:
        reason = "regressions-detected"
    action = "quiet"
    reopen_existing = False
    close_reason = ""
    if noisy:
        if issue_state == "open":
            action = "update"
        elif issue_state == "closed":
            action = "update"
            reopen_existing = True
        else:
            action = "open"
    elif issue_state == "open":
        action = "close"
        close_reason = "quiet-recovery"
    return {
        "should_open": noisy,
        "reason": reason,
        "severity": urgency,
        "action": action,
        "reopen_existing": reopen_existing,
        "close_reason": close_reason,
        "label": ISSUE_LABEL,
        "title": f"Scheduled Audit Handoff: {username}",
        "marker": f"scheduled-audit-handoff:{username}",
        "issue_state": issue_state,
        "issue_number": issue_number,
        "issue_url": issue_url,
        "body_path": str(body_path),
    }


def render_scheduled_handoff_markdown(payload: dict) -> str:
    summary = payload.get("operator_summary", {})
    queue = payload.get("operator_queue", []) or []
    recent_changes = payload.get("operator_recent_changes", []) or []
    issue_candidate = payload.get("issue_candidate", {})
    primary_target = summary.get("primary_target") or {}
    primary_target_label = (
        f"{primary_target.get('repo')}: {primary_target.get('title')}"
        if primary_target.get("repo")
        else primary_target.get("title", "")
    )
    resolved_count = summary.get("resolved_attention_count", 0)
    persisting_count = summary.get("persisting_attention_count", 0)
    longest_persisting = summary.get("longest_persisting_item") or {}
    longest_label = (
        f"{longest_persisting.get('repo')}: {longest_persisting.get('title')}"
        if longest_persisting.get("repo")
        else longest_persisting.get("title", "")
    )
    lines = [
        f"# Scheduled Audit Handoff: {payload.get('username', 'unknown')}",
        "",
        f"<!-- {issue_candidate.get('marker', '')} -->",
        "",
        f"- Generated: `{payload.get('generated_at', '')}`",
        f"- Headline: {summary.get('headline', 'No operator triage items are currently surfaced.')}",
        f"- What changed: {summary.get('what_changed', 'No operator change summary is recorded.')}",
        f"- Why it matters: {summary.get('why_it_matters', 'No additional operator impact is recorded.')}",
        f"- What to do next: {summary.get('what_to_do_next', 'Continue the normal operator loop.')}",
        f"- Trend: `{summary.get('trend_status', 'stable')}` — {summary.get('trend_summary', 'No trend summary is recorded yet.')}",
        f"- Aging status: `{summary.get('aging_status', 'fresh')}`",
        f"- Attention counts: new={summary.get('new_attention_count', 0)}, resolved={resolved_count}, persisting={persisting_count}, reopened={summary.get('reopened_attention_count', 0)}",
        f"- Primary target: {primary_target_label or 'No active target'}",
        f"- Accountability: {summary.get('accountability_summary', 'No accountability summary is recorded yet.')}",
        f"- Decision memory: `{summary.get('decision_memory_status', 'new')}`",
        f"- Resolution evidence: {summary.get('resolution_evidence_summary', 'No resolution evidence is recorded yet.')}",
        f"- Recommendation confidence: `{summary.get('primary_target_confidence_label', 'low')}` ({summary.get('primary_target_confidence_score', 0.0):.2f})",
        f"- Next action confidence: `{summary.get('next_action_confidence_label', 'low')}` ({summary.get('next_action_confidence_score', 0.0):.2f})",
        f"- Trust policy: `{summary.get('primary_target_trust_policy', 'monitor')}` — {summary.get('primary_target_trust_policy_reason', 'No trust-policy reason is recorded yet.')}",
        f"- Trust policy exception: `{summary.get('primary_target_exception_status', 'none')}` — {summary.get('primary_target_exception_reason', 'No trust-policy exception reason is recorded yet.')}",
        f"- Exception pattern learning: `{summary.get('primary_target_exception_pattern_status', 'none')}` — {summary.get('primary_target_exception_pattern_reason', 'No exception-pattern reason is recorded yet.')}",
        f"- Trust recovery: `{summary.get('primary_target_trust_recovery_status', 'none')}` — {summary.get('primary_target_trust_recovery_reason', 'No trust-recovery reason is recorded yet.')}",
        f"- Recovery confidence: `{summary.get('primary_target_recovery_confidence_label', 'low')}` ({summary.get('primary_target_recovery_confidence_score', 0.0):.2f}) — {summary.get('recovery_confidence_summary', 'No recovery-confidence summary is recorded yet.')}",
        f"- Exception retirement: `{summary.get('primary_target_exception_retirement_status', 'none')}` — {summary.get('primary_target_exception_retirement_reason', 'No exception-retirement reason is recorded yet.')}",
        f"- Policy debt cleanup: `{summary.get('primary_target_policy_debt_status', 'none')}` — {summary.get('primary_target_policy_debt_reason', 'No policy-debt reason is recorded yet.')}",
        f"- Class-level trust normalization: `{summary.get('primary_target_class_normalization_status', 'none')}` — {summary.get('primary_target_class_normalization_reason', 'No class-normalization reason is recorded yet.')}",
        f"- Class memory freshness: `{summary.get('primary_target_class_memory_freshness_status', 'insufficient-data')}` — {summary.get('primary_target_class_memory_freshness_reason', 'No class-memory freshness reason is recorded yet.')}",
        f"- Trust decay controls: `{summary.get('primary_target_class_decay_status', 'none')}` — {summary.get('primary_target_class_decay_reason', 'No class-decay reason is recorded yet.')}",
        f"- Class trust reweighting: `{summary.get('primary_target_class_trust_reweight_direction', 'neutral')}` ({summary.get('primary_target_class_trust_reweight_score', 0.0):.2f})",
        f"- Class transition health: `{summary.get('primary_target_class_transition_health_status', 'none')}` — {summary.get('primary_target_class_transition_health_reason', 'No class transition health reason is recorded yet.')}",
        f"- Pending transition resolution: `{summary.get('primary_target_class_transition_resolution_status', 'none')}` — {summary.get('primary_target_class_transition_resolution_reason', 'No class transition resolution reason is recorded yet.')}",
        f"- Transition closure confidence: `{summary.get('primary_target_transition_closure_confidence_label', 'low')}` ({summary.get('primary_target_transition_closure_confidence_score', 0.0):.2f}) — {summary.get('primary_target_transition_closure_likely_outcome', 'none')}",
        f"- Class pending debt audit: `{summary.get('primary_target_class_pending_debt_status', 'none')}` — {summary.get('primary_target_class_pending_debt_reason', 'No class pending-debt reason is recorded yet.')}",
        f"- Closure forecast freshness: `{summary.get('primary_target_closure_forecast_freshness_status', 'insufficient-data')}` — {summary.get('primary_target_closure_forecast_freshness_reason', 'No closure-forecast freshness reason is recorded yet.')}",
        f"- Hysteresis decay controls: `{summary.get('primary_target_closure_forecast_decay_status', 'none')}` — {summary.get('primary_target_closure_forecast_decay_reason', 'No closure-forecast decay reason is recorded yet.')}",
        f"- Closure forecast refresh recovery: `{summary.get('primary_target_closure_forecast_refresh_recovery_status', 'none')}` — {summary.get('primary_target_closure_forecast_reacquisition_reason', 'No closure-forecast refresh-recovery reason is recorded yet.')}",
        f"- Reacquisition controls: `{summary.get('primary_target_closure_forecast_reacquisition_status', 'none')}` — {summary.get('primary_target_closure_forecast_reacquisition_reason', 'No closure-forecast reacquisition reason is recorded yet.')}",
        f"- Reacquisition persistence: `{summary.get('primary_target_closure_forecast_reacquisition_persistence_status', 'none')}` — {summary.get('primary_target_closure_forecast_reacquisition_persistence_reason', 'No reacquisition-persistence reason is recorded yet.')}",
        f"- Recovery churn controls: `{summary.get('primary_target_closure_forecast_recovery_churn_status', 'none')}` — {summary.get('primary_target_closure_forecast_recovery_churn_reason', 'No recovery-churn reason is recorded yet.')}",
        f"- Recommendation drift: `{summary.get('recommendation_drift_status', 'stable')}` — {summary.get('recommendation_drift_summary', 'No recommendation-drift summary is recorded yet.')}",
        f"- Exception pattern summary: {summary.get('exception_pattern_summary', 'No exception-pattern summary is recorded yet.')}",
        f"- Exception retirement summary: {summary.get('exception_retirement_summary', 'No exception-retirement summary is recorded yet.')}",
        f"- Policy debt summary: {summary.get('policy_debt_summary', 'No policy-debt summary is recorded yet.')}",
        f"- Trust normalization summary: {summary.get('trust_normalization_summary', 'No trust-normalization summary is recorded yet.')}",
        f"- Class memory summary: {summary.get('class_memory_summary', 'No class-memory summary is recorded yet.')}",
        f"- Class decay summary: {summary.get('class_decay_summary', 'No class-decay summary is recorded yet.')}",
        f"- Class reweighting summary: {summary.get('class_reweighting_summary', 'No class reweighting summary is recorded yet.')}",
        f"- Transition closure summary: {summary.get('transition_closure_confidence_summary', 'No transition-closure confidence summary is recorded yet.')}",
        f"- Class pending debt summary: {summary.get('class_pending_debt_summary', 'No class pending-debt summary is recorded yet.')}",
        f"- Class pending resolution summary: {summary.get('class_pending_resolution_summary', 'No class pending-resolution summary is recorded yet.')}",
        f"- Closure forecast freshness summary: {summary.get('closure_forecast_freshness_summary', 'No closure-forecast freshness summary is recorded yet.')}",
        f"- Closure forecast decay summary: {summary.get('closure_forecast_decay_summary', 'No closure-forecast decay summary is recorded yet.')}",
        f"- Closure forecast refresh recovery summary: {summary.get('closure_forecast_refresh_recovery_summary', 'No closure-forecast refresh-recovery summary is recorded yet.')}",
        f"- Closure forecast reacquisition summary: {summary.get('closure_forecast_reacquisition_summary', 'No closure-forecast reacquisition summary is recorded yet.')}",
        f"- Reacquisition persistence summary: {summary.get('closure_forecast_reacquisition_persistence_summary', 'No reacquisition-persistence summary is recorded yet.')}",
        f"- Recovery churn summary: {summary.get('closure_forecast_recovery_churn_summary', 'No recovery-churn summary is recorded yet.')}",
        f"- Confidence validation: `{summary.get('confidence_validation_status', 'insufficient-data')}` — {summary.get('confidence_calibration_summary', 'No confidence-calibration summary is recorded yet.')}",
        f"- Next recommended run: `{summary.get('next_recommended_run_mode', 'n/a')}`",
        f"- Watch strategy: `{summary.get('watch_strategy', 'manual')}`",
        f"- Watch decision: {summary.get('watch_decision_summary', 'No watch guidance is recorded.')}",
        f"- Queue counts: {_queue_counts(summary)}",
        f"- Issue automation: `{issue_candidate.get('action', 'quiet')}` ({issue_candidate.get('reason', 'quiet')})",
        *( [f"- Existing issue: #{issue_candidate.get('issue_number')}"] if issue_candidate.get("issue_number") else [] ),
        "",
    ]
    lines.append("## Recommendation Confidence")
    lines.append("")
    lines.append(
        f"- Primary target confidence: {summary.get('primary_target_confidence_label', 'low')} ({summary.get('primary_target_confidence_score', 0.0):.2f})"
    )
    lines.append(
        f"- Next action confidence: {summary.get('next_action_confidence_label', 'low')} ({summary.get('next_action_confidence_score', 0.0):.2f})"
    )
    lines.append(
        f"- Trust policy: {summary.get('primary_target_trust_policy', 'monitor')} ({summary.get('primary_target_trust_policy_reason', 'No trust-policy reason is recorded yet.')})"
    )
    if summary.get("primary_target_confidence_reasons"):
        lines.append(
            f"- Confidence reasons: {', '.join(summary.get('primary_target_confidence_reasons') or [])}"
        )
    lines.append(
        f"- {summary.get('recommendation_quality_summary', 'No recommendation-quality summary is recorded yet.')}"
    )
    lines.append(
        f"- Confidence validation: {summary.get('confidence_validation_status', 'insufficient-data')} "
        f"({summary.get('confidence_calibration_summary', 'No confidence-calibration summary is recorded yet.')})"
    )
    lines.append(
        f"- Hit / caution rates: high={summary.get('high_confidence_hit_rate', 0.0):.0%}, "
        f"medium={summary.get('medium_confidence_hit_rate', 0.0):.0%}, "
        f"low={summary.get('low_confidence_caution_rate', 0.0):.0%}"
    )
    for item in (summary.get("recent_validation_outcomes") or [])[:3]:
        lines.append(
            f"- {item.get('target_label', 'Operator target')} "
            f"[{item.get('confidence_label', 'low')}] -> "
            f"{str(item.get('outcome', 'unresolved')).replace('_', ' ')}"
        )
    lines.append("")
    lines.append("## Operator Trust Policy")
    lines.append("")
    lines.append(
        f"- Current tuned primary-target confidence: {summary.get('primary_target_confidence_label', 'low')} "
        f"({summary.get('primary_target_confidence_score', 0.0):.2f})"
    )
    lines.append(
        f"- Current tuned next-action confidence: {summary.get('next_action_confidence_label', 'low')} "
        f"({summary.get('next_action_confidence_score', 0.0):.2f})"
    )
    lines.append(
        f"- Target trust policy: {summary.get('primary_target_trust_policy', 'monitor')} "
        f"-> {summary.get('primary_target_trust_policy_reason', 'No trust-policy reason is recorded yet.')}"
    )
    lines.append(
        f"- Next-action trust policy: {summary.get('next_action_trust_policy', 'monitor')} "
        f"-> {summary.get('next_action_trust_policy_reason', 'No trust-policy reason is recorded yet.')}"
    )
    lines.append(
        f"- Calibration status: {summary.get('confidence_validation_status', 'insufficient-data')} "
        f"-> {summary.get('confidence_calibration_summary', 'No confidence-calibration summary is recorded yet.')}"
    )
    lines.append(
        f"- {summary.get('adaptive_confidence_summary', 'No adaptive confidence summary is recorded yet.')}"
    )
    lines.append("")
    lines.append("## Trust Policy Exception")
    lines.append("")
    lines.append(
        f"- Exception status: {summary.get('primary_target_exception_status', 'none')} "
        f"({summary.get('primary_target_exception_reason', 'No trust-policy exception reason is recorded yet.')})"
    )
    if primary_target.get("recent_policy_path"):
        lines.append(
            f"- Recent policy path: {primary_target.get('recent_policy_path')} "
            f"({primary_target.get('policy_flip_count', 0)} flip(s))"
        )
    else:
        lines.append("- Recent policy path: No recent trust-policy flip path is recorded for the current target.")
    lines.append("")
    lines.append("## Exception Pattern Learning")
    lines.append("")
    lines.append(
        f"- Pattern status: {summary.get('primary_target_exception_pattern_status', 'none')} "
        f"({summary.get('primary_target_exception_pattern_reason', 'No exception-pattern reason is recorded yet.')})"
    )
    lines.append(
        f"- {summary.get('exception_pattern_summary', 'No exception-pattern summary is recorded yet.')}"
    )
    hotspots = summary.get("false_positive_exception_hotspots") or []
    if hotspots:
        for hotspot in hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Recent hotspot')} [{hotspot.get('scope', 'target')}] -> "
                f"{hotspot.get('overcautious_count', 0)} overcautious case(s) across {hotspot.get('exception_count', 0)} exception case(s)"
            )
    else:
        lines.append("- No repeated overcautious exception hotspots are recorded in the recent window.")
    lines.append("")
    lines.append("## Trust Recovery")
    lines.append("")
    lines.append(
        f"- Recovery status: {summary.get('primary_target_trust_recovery_status', 'none')} "
        f"({summary.get('primary_target_trust_recovery_reason', 'No trust-recovery reason is recorded yet.')})"
    )
    lines.append(
        f"- Final trust policy: {summary.get('primary_target_trust_policy', 'monitor')} "
        f"({summary.get('primary_target_trust_policy_reason', 'No trust-policy reason is recorded yet.')})"
    )
    lines.append(
        f"- Recovery window: {summary.get('trust_recovery_window_runs', 3)} run(s)"
    )
    lines.append("")
    lines.append("## Recovery Confidence")
    lines.append("")
    lines.append(
        f"- Recovery confidence: {summary.get('primary_target_recovery_confidence_label', 'low')} "
        f"({summary.get('primary_target_recovery_confidence_score', 0.0):.2f})"
    )
    if summary.get("primary_target_recovery_confidence_reasons"):
        lines.append(
            f"- Recovery confidence reasons: {', '.join(summary.get('primary_target_recovery_confidence_reasons') or [])}"
        )
    lines.append(
        f"- {summary.get('recovery_confidence_summary', 'No recovery-confidence summary is recorded yet.')}"
    )
    lines.append("")
    lines.append("## Exception Retirement")
    lines.append("")
    lines.append(
        f"- Retirement status: {summary.get('primary_target_exception_retirement_status', 'none')} "
        f"({summary.get('primary_target_exception_retirement_reason', 'No exception-retirement reason is recorded yet.')})"
    )
    lines.append(
        f"- Final trust policy after retirement: {summary.get('primary_target_trust_policy', 'monitor')} "
        f"({summary.get('primary_target_trust_policy_reason', 'No trust-policy reason is recorded yet.')})"
    )
    lines.append(
        f"- Retirement window: {summary.get('exception_retirement_window_runs', 4)} run(s)"
    )
    lines.append(
        f"- {summary.get('exception_retirement_summary', 'No exception-retirement summary is recorded yet.')}"
    )
    retired_hotspots = summary.get("retired_exception_hotspots") or []
    if retired_hotspots:
        for hotspot in retired_hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Recent retirement hotspot')} [{hotspot.get('scope', 'class')}] -> "
                f"{hotspot.get('retired_count', 0)} retired case(s) across {hotspot.get('exception_count', 0)} exception case(s)"
            )
    sticky_hotspots = summary.get("sticky_exception_hotspots") or []
    if sticky_hotspots:
        for hotspot in sticky_hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Recent sticky hotspot')} [{hotspot.get('scope', 'class')}] -> "
                f"{hotspot.get('sticky_count', 0)} sticky case(s) across {hotspot.get('exception_count', 0)} exception case(s)"
            )
    lines.append("")
    lines.append("## Policy Debt Cleanup")
    lines.append("")
    lines.append(
        f"- Policy debt status: {summary.get('primary_target_policy_debt_status', 'none')} "
        f"({summary.get('primary_target_policy_debt_reason', 'No policy-debt reason is recorded yet.')})"
    )
    lines.append(
        f"- Class retirement / sticky rates: {summary.get('primary_target', {}).get('class_retirement_rate', 0.0):.0%} retired, "
        f"{summary.get('primary_target', {}).get('class_sticky_rate', 0.0):.0%} sticky"
    )
    lines.append(
        f"- {summary.get('policy_debt_summary', 'No policy-debt summary is recorded yet.')}"
    )
    debt_hotspots = summary.get("policy_debt_hotspots") or []
    if debt_hotspots:
        for hotspot in debt_hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Recent debt hotspot')} [{hotspot.get('scope', 'class')}] -> "
                f"{hotspot.get('match_count', 0)} sticky class signal(s) across {hotspot.get('exception_count', 0)} exception case(s)"
            )
    else:
        lines.append("- No repeated class-level policy debt hotspots are recorded in the recent window.")
    lines.append("")
    lines.append("## Class-Level Trust Normalization")
    lines.append("")
    lines.append(
        f"- Normalization status: {summary.get('primary_target_class_normalization_status', 'none')} "
        f"({summary.get('primary_target_class_normalization_reason', 'No class-normalization reason is recorded yet.')})"
    )
    lines.append(
        f"- Final trust policy after normalization: {summary.get('primary_target_trust_policy', 'monitor')} "
        f"({summary.get('primary_target_trust_policy_reason', 'No trust-policy reason is recorded yet.')})"
    )
    lines.append(
        f"- Normalization window: {summary.get('class_normalization_window_runs', 4)} run(s)"
    )
    lines.append(
        f"- {summary.get('trust_normalization_summary', 'No trust-normalization summary is recorded yet.')}"
    )
    normalized_hotspots = summary.get("normalized_class_hotspots") or []
    if normalized_hotspots:
        for hotspot in normalized_hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Recent normalization hotspot')} [{hotspot.get('scope', 'class')}] -> "
                f"{hotspot.get('match_count', 0)} normalization signal(s) across {hotspot.get('exception_count', 0)} exception case(s)"
            )
    else:
        lines.append("- No repeated class-level normalization hotspots are recorded in the recent window.")
    lines.append("")
    lines.append("## Class Memory Freshness")
    lines.append("")
    lines.append(
        f"- Freshness status: {summary.get('primary_target_class_memory_freshness_status', 'insufficient-data')} "
        f"({summary.get('primary_target_class_memory_freshness_reason', 'No class-memory freshness reason is recorded yet.')})"
    )
    lines.append(
        f"- Decayed retirement / sticky rates: {summary.get('primary_target', {}).get('decayed_class_retirement_rate', 0.0):.0%} retired-like, "
        f"{summary.get('primary_target', {}).get('decayed_class_sticky_rate', 0.0):.0%} sticky-like"
    )
    lines.append(
        f"- Freshness window: {summary.get('class_decay_window_runs', 4)} run(s)"
    )
    lines.append(
        f"- {summary.get('class_memory_summary', 'No class-memory summary is recorded yet.')}"
    )
    fresh_hotspots = summary.get("fresh_class_signal_hotspots") or []
    if fresh_hotspots:
        for hotspot in fresh_hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Fresh class hotspot')} [{hotspot.get('scope', 'class')}] -> "
                f"{hotspot.get('freshness_status', 'fresh')} with {hotspot.get('decayed_class_retirement_rate', 0.0):.0%} retired-like signal"
            )
    else:
        lines.append("- No unusually fresh class-memory hotspots are recorded in the recent window.")
    lines.append("")
    lines.append("## Trust Decay Controls")
    lines.append("")
    lines.append(
        f"- Decay status: {summary.get('primary_target_class_decay_status', 'none')} "
        f"({summary.get('primary_target_class_decay_reason', 'No class-decay reason is recorded yet.')})"
    )
    lines.append(
        f"- Final trust policy after decay: {summary.get('primary_target_trust_policy', 'monitor')} "
        f"({summary.get('primary_target_trust_policy_reason', 'No trust-policy reason is recorded yet.')})"
    )
    lines.append(
        f"- {summary.get('class_decay_summary', 'No class-decay summary is recorded yet.')}"
    )
    stale_hotspots = summary.get("stale_class_memory_hotspots") or []
    if stale_hotspots:
        for hotspot in stale_hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Stale class hotspot')} [{hotspot.get('scope', 'class')}] -> "
                f"{hotspot.get('freshness_status', 'stale')} with {hotspot.get('decayed_class_sticky_rate', 0.0):.0%} sticky-like signal"
            )
    else:
        lines.append("- No stale class-memory hotspots are recorded in the recent window.")
    lines.append("")
    lines.append("## Class Trust Reweighting")
    lines.append("")
    lines.append(
        f"- Reweight direction: {summary.get('primary_target_class_trust_reweight_direction', 'neutral')} "
        f"({summary.get('primary_target_class_trust_reweight_score', 0.0):.2f})"
    )
    lines.append(
        f"- Support / caution scores: {summary.get('primary_target_weighted_class_support_score', 0.0):.2f} support, "
        f"{summary.get('primary_target_weighted_class_caution_score', 0.0):.2f} caution"
    )
    if summary.get("primary_target_class_trust_reweight_reasons"):
        lines.append(
            f"- Why class guidance shifted: {', '.join(summary.get('primary_target_class_trust_reweight_reasons') or [])}"
        )
    lines.append(
        f"- {summary.get('class_reweighting_summary', 'No class reweighting summary is recorded yet.')}"
    )
    support_hotspots = summary.get("supporting_class_hotspots") or []
    if support_hotspots:
        for hotspot in support_hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Supporting class hotspot')} [{hotspot.get('scope', 'class')}] -> "
                f"{hotspot.get('reweight_score', 0.0):.2f} with {hotspot.get('weighted_class_support_score', 0.0):.2f} support"
            )
    caution_hotspots = summary.get("caution_class_hotspots") or []
    if caution_hotspots:
        for hotspot in caution_hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Caution class hotspot')} [{hotspot.get('scope', 'class')}] -> "
                f"{hotspot.get('reweight_score', 0.0):.2f} with {hotspot.get('weighted_class_caution_score', 0.0):.2f} caution"
            )
    if not support_hotspots and not caution_hotspots:
        lines.append("- No strong class reweighting hotspots are recorded in the recent window.")
    lines.append("")
    lines.append("## Class Trust Momentum")
    lines.append("")
    lines.append(
        f"- Momentum status: {summary.get('primary_target_class_trust_momentum_status', 'insufficient-data')} "
        f"({summary.get('primary_target_class_trust_momentum_score', 0.0):.2f})"
    )
    lines.append(
        f"- Transition status: {summary.get('primary_target_class_reweight_transition_status', 'none')} "
        f"({summary.get('primary_target_class_reweight_transition_reason', 'No class transition reason is recorded yet.')})"
    )
    lines.append(
        f"- Transition window: {summary.get('class_transition_window_runs', 4)} run(s)"
    )
    lines.append(
        f"- {summary.get('class_momentum_summary', 'No class momentum summary is recorded yet.')}"
    )
    sustained_hotspots = summary.get("sustained_class_hotspots") or []
    if sustained_hotspots:
        for hotspot in sustained_hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Sustained class hotspot')} [{hotspot.get('scope', 'class')}] -> "
                f"{hotspot.get('momentum_status', 'building')} at {hotspot.get('momentum_score', 0.0):.2f}"
            )
    else:
        lines.append("- No sustained class-momentum hotspots are recorded in the recent window.")
    lines.append("")
    lines.append("## Reweighting Stability")
    lines.append("")
    lines.append(
        f"- Stability status: {summary.get('primary_target_class_reweight_stability_status', 'watch')} "
        f"({summary.get('class_reweight_stability_summary', 'No reweighting stability summary is recorded yet.')})"
    )
    primary_target = summary.get("primary_target") or {}
    if primary_target.get("recent_class_reweight_path"):
        lines.append(
            f"- Recent class reweight path: {primary_target.get('recent_class_reweight_path')}"
        )
    oscillating_hotspots = summary.get("oscillating_class_hotspots") or []
    if oscillating_hotspots:
        for hotspot in oscillating_hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Oscillating class hotspot')} [{hotspot.get('scope', 'class')}] -> "
                f"{hotspot.get('stability_status', 'oscillating')} across {hotspot.get('recent_class_reweight_path', 'no path recorded')}"
            )
    else:
        lines.append("- No oscillating class-momentum hotspots are recorded in the recent window.")
    lines.append("")
    lines.append("## Class Transition Health")
    lines.append("")
    lines.append(
        f"- Transition health: {summary.get('primary_target_class_transition_health_status', 'none')} "
        f"({summary.get('primary_target_class_transition_health_reason', 'No class transition health reason is recorded yet.')})"
    )
    lines.append(
        f"- Transition age: {summary.get('primary_target', {}).get('class_transition_age_runs', 0)} run(s)"
    )
    lines.append(
        f"- Transition age window: {summary.get('class_transition_age_window_runs', 4)} run(s)"
    )
    lines.append(
        f"- {summary.get('class_transition_health_summary', 'No class transition health summary is recorded yet.')}"
    )
    if primary_target.get("recent_transition_path"):
        lines.append(f"- Recent transition path: {primary_target.get('recent_transition_path')}")
    stalled_transition_hotspots = summary.get("stalled_transition_hotspots") or []
    if stalled_transition_hotspots:
        for hotspot in stalled_transition_hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Stalled transition hotspot')} [{hotspot.get('scope', 'class')}] -> "
                f"{hotspot.get('health_status', 'stalled')} across {hotspot.get('transition_age_runs', 0)} run(s)"
            )
    else:
        lines.append("- No stalled pending-transition hotspots are recorded in the recent window.")
    lines.append("")
    lines.append("## Pending Transition Resolution")
    lines.append("")
    lines.append(
        f"- Resolution status: {summary.get('primary_target_class_transition_resolution_status', 'none')} "
        f"({summary.get('primary_target_class_transition_resolution_reason', 'No class transition resolution reason is recorded yet.')})"
    )
    lines.append(
        f"- {summary.get('class_transition_resolution_summary', 'No class transition resolution summary is recorded yet.')}"
    )
    resolving_transition_hotspots = summary.get("resolving_transition_hotspots") or []
    if resolving_transition_hotspots:
        for hotspot in resolving_transition_hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Resolving transition hotspot')} [{hotspot.get('scope', 'class')}] -> "
                f"{hotspot.get('resolution_status', 'confirmed')} across {hotspot.get('recent_transition_path', 'no transition path recorded')}"
            )
    else:
        lines.append("- No recent pending-transition resolutions are recorded in the recent window.")
    lines.append("")
    lines.append("## Transition Closure Confidence")
    lines.append("")
    lines.append(
        f"- Closure confidence: {summary.get('primary_target_transition_closure_confidence_label', 'low')} "
        f"({summary.get('primary_target_transition_closure_confidence_score', 0.0):.2f}; "
        f"{summary.get('primary_target_transition_closure_likely_outcome', 'none')})"
    )
    if summary.get("primary_target_transition_closure_confidence_reasons"):
        lines.append(
            "- Closure reasons: "
            + "; ".join(summary.get("primary_target_transition_closure_confidence_reasons") or [])
        )
    lines.append(
        f"- Closure window: {summary.get('transition_closure_window_runs', 4)} run(s)"
    )
    if primary_target.get("recent_transition_score_path"):
        lines.append(
            f"- Recent transition score path: {primary_target.get('recent_transition_score_path')}"
        )
    lines.append(
        f"- {summary.get('transition_closure_confidence_summary', 'No transition-closure confidence summary is recorded yet.')}"
    )
    lines.append("")
    lines.append("## Class Pending Debt Audit")
    lines.append("")
    lines.append(
        f"- Pending-debt status: {summary.get('primary_target_class_pending_debt_status', 'none')} "
        f"({summary.get('primary_target_class_pending_debt_reason', 'No class pending-debt reason is recorded yet.')})"
    )
    lines.append(
        f"- Pending-debt rate: {summary.get('primary_target', {}).get('class_pending_debt_rate', 0.0):.0%}"
    )
    lines.append(
        f"- Pending-resolution rate: {summary.get('primary_target', {}).get('class_pending_resolution_rate', 0.0):.0%}"
    )
    lines.append(
        f"- Pending-debt window: {summary.get('class_pending_debt_window_runs', 10)} run(s)"
    )
    lines.append(
        f"- {summary.get('class_pending_debt_summary', 'No class pending-debt summary is recorded yet.')}"
    )
    lines.append(
        f"- {summary.get('class_pending_resolution_summary', 'No class pending-resolution summary is recorded yet.')}"
    )
    if primary_target.get("recent_pending_debt_path"):
        lines.append(f"- Recent pending-debt path: {primary_target.get('recent_pending_debt_path')}")
    pending_debt_hotspots = summary.get("pending_debt_hotspots") or []
    healthy_pending_resolution_hotspots = summary.get("healthy_pending_resolution_hotspots") or []
    if pending_debt_hotspots:
        for hotspot in pending_debt_hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Pending debt hotspot')} [{hotspot.get('scope', 'class')}] -> "
                f"{hotspot.get('class_pending_debt_status', 'active-debt')} across "
                f"{hotspot.get('recent_pending_debt_path', 'no path recorded')}"
            )
    elif healthy_pending_resolution_hotspots:
        for hotspot in healthy_pending_resolution_hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Healthy pending hotspot')} [{hotspot.get('scope', 'class')}] -> "
                f"{hotspot.get('class_pending_debt_status', 'clearing')} across "
                f"{hotspot.get('recent_pending_debt_path', 'no path recorded')}"
            )
    else:
        lines.append("- No class pending-debt hotspots are recorded in the recent window.")
    lines.append("")
    lines.append("## Pending Debt Freshness")
    lines.append("")
    lines.append(
        f"- Pending-debt freshness: {summary.get('primary_target_pending_debt_freshness_status', 'insufficient-data')} "
        f"({summary.get('primary_target_pending_debt_freshness_reason', 'No pending-debt freshness reason is recorded yet.')})"
    )
    lines.append(
        f"- Pending-debt memory weight: {summary.get('primary_target', {}).get('pending_debt_memory_weight', 0.0):.0%}"
    )
    lines.append(
        f"- Decayed pending-debt rate: {summary.get('primary_target', {}).get('decayed_pending_debt_rate', 0.0):.0%}"
    )
    lines.append(
        f"- Decayed pending-resolution rate: {summary.get('primary_target', {}).get('decayed_pending_resolution_rate', 0.0):.0%}"
    )
    lines.append(
        f"- Freshness window: {summary.get('pending_debt_decay_window_runs', 4)} run(s)"
    )
    lines.append(
        f"- {summary.get('pending_debt_freshness_summary', 'No pending-debt freshness summary is recorded yet.')}"
    )
    lines.append(
        f"- {summary.get('pending_debt_decay_summary', 'No pending-debt decay summary is recorded yet.')}"
    )
    if primary_target.get("recent_pending_signal_mix"):
        lines.append(f"- Recent pending signal mix: {primary_target.get('recent_pending_signal_mix')}")
    stale_pending_debt_hotspots = summary.get("stale_pending_debt_hotspots") or []
    fresh_pending_resolution_hotspots = summary.get("fresh_pending_resolution_hotspots") or []
    if stale_pending_debt_hotspots:
        for hotspot in stale_pending_debt_hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Stale pending-debt hotspot')} [{hotspot.get('scope', 'class')}] -> "
                f"stale debt at {hotspot.get('decayed_pending_debt_rate', 0.0):.0%} across "
                f"{hotspot.get('recent_pending_signal_mix', 'no mix recorded')}"
            )
    elif fresh_pending_resolution_hotspots:
        for hotspot in fresh_pending_resolution_hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Fresh pending-resolution hotspot')} [{hotspot.get('scope', 'class')}] -> "
                f"fresh resolution at {hotspot.get('decayed_pending_resolution_rate', 0.0):.0%} across "
                f"{hotspot.get('recent_pending_signal_mix', 'no mix recorded')}"
            )
    else:
        lines.append("- No pending-debt freshness hotspots are recorded in the recent window.")
    lines.append("")
    lines.append("## Closure Forecast Reweighting")
    lines.append("")
    lines.append(
        f"- Forecast reweighting: {summary.get('primary_target_closure_forecast_reweight_direction', 'neutral')} "
        f"({summary.get('primary_target_closure_forecast_reweight_score', 0.0):.2f})"
    )
    lines.append(
        f"- Resolution-support score: {summary.get('primary_target_weighted_pending_resolution_support_score', 0.0):.2f}"
    )
    lines.append(
        f"- Pending-debt caution score: {summary.get('primary_target_weighted_pending_debt_caution_score', 0.0):.2f}"
    )
    if summary.get("primary_target_closure_forecast_reweight_reasons"):
        lines.append(
            "- Forecast reasons: "
            + "; ".join(summary.get("primary_target_closure_forecast_reweight_reasons") or [])
        )
    lines.append(
        f"- Reweighting window: {summary.get('closure_forecast_reweighting_window_runs', 4)} run(s)"
    )
    lines.append(
        f"- {summary.get('closure_forecast_reweighting_summary', 'No closure-forecast reweighting summary is recorded yet.')}"
    )
    supporting_pending_resolution_hotspots = summary.get("supporting_pending_resolution_hotspots") or []
    caution_pending_debt_hotspots = summary.get("caution_pending_debt_hotspots") or []
    if supporting_pending_resolution_hotspots:
        for hotspot in supporting_pending_resolution_hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Supporting pending-resolution hotspot')} [{hotspot.get('scope', 'class')}] -> "
                f"{hotspot.get('closure_forecast_reweight_direction', 'supporting-confirmation')} at "
                f"{hotspot.get('weighted_pending_resolution_support_score', 0.0):.2f}"
            )
    elif caution_pending_debt_hotspots:
        for hotspot in caution_pending_debt_hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Caution pending-debt hotspot')} [{hotspot.get('scope', 'class')}] -> "
                f"{hotspot.get('closure_forecast_reweight_direction', 'supporting-clearance')} at "
                f"{hotspot.get('weighted_pending_debt_caution_score', 0.0):.2f}"
            )
    else:
        lines.append("- No closure-forecast reweighting hotspots are recorded in the recent window.")
    lines.append("")
    lines.append("## Closure Forecast Freshness")
    lines.append("")
    lines.append(
        f"- Forecast freshness: {summary.get('primary_target_closure_forecast_freshness_status', 'insufficient-data')} "
        f"({summary.get('primary_target_closure_forecast_freshness_reason', 'No closure-forecast freshness reason is recorded yet.')})"
    )
    lines.append(
        f"- Decayed confirmation rate: {primary_target.get('decayed_confirmation_forecast_rate', 0.0):.0%}"
    )
    lines.append(
        f"- Decayed clearance rate: {primary_target.get('decayed_clearance_forecast_rate', 0.0):.0%}"
    )
    lines.append(
        f"- Forecast freshness window: {summary.get('closure_forecast_decay_window_runs', 4)} run(s)"
    )
    if primary_target.get("recent_closure_forecast_signal_mix"):
        lines.append(
            f"- Recent closure-forecast signal mix: {primary_target.get('recent_closure_forecast_signal_mix')}"
        )
    lines.append(
        f"- {summary.get('closure_forecast_freshness_summary', 'No closure-forecast freshness summary is recorded yet.')}"
    )
    stale_closure_forecast_hotspots = summary.get("stale_closure_forecast_hotspots") or []
    fresh_closure_forecast_signal_hotspots = summary.get("fresh_closure_forecast_signal_hotspots") or []
    if stale_closure_forecast_hotspots:
        for hotspot in stale_closure_forecast_hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Stale forecast hotspot')} [{hotspot.get('scope', 'class')}] -> "
                f"{hotspot.get('closure_forecast_freshness_status', 'stale')} at "
                f"{max(hotspot.get('decayed_confirmation_forecast_rate', 0.0), hotspot.get('decayed_clearance_forecast_rate', 0.0)):.0%}"
            )
    elif fresh_closure_forecast_signal_hotspots:
        for hotspot in fresh_closure_forecast_signal_hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Fresh forecast hotspot')} [{hotspot.get('scope', 'class')}] -> "
                f"{hotspot.get('closure_forecast_freshness_status', 'fresh')} at "
                f"{max(hotspot.get('decayed_confirmation_forecast_rate', 0.0), hotspot.get('decayed_clearance_forecast_rate', 0.0)):.0%}"
            )
    else:
        lines.append("- No closure-forecast freshness hotspots are recorded in the recent window.")
    lines.append("")
    lines.append("## Closure Forecast Momentum")
    lines.append("")
    lines.append(
        f"- Forecast momentum: {summary.get('primary_target_closure_forecast_momentum_status', 'insufficient-data')} "
        f"({summary.get('primary_target_closure_forecast_momentum_score', 0.0):.2f})"
    )
    lines.append(
        f"- Forecast stability: {summary.get('primary_target_closure_forecast_stability_status', 'watch')}"
    )
    lines.append(
        f"- Forecast transition window: {summary.get('closure_forecast_transition_window_runs', 4)} run(s)"
    )
    if primary_target.get("recent_closure_forecast_path"):
        lines.append(
            f"- Recent closure-forecast path: {primary_target.get('recent_closure_forecast_path')}"
        )
    lines.append(
        f"- {summary.get('closure_forecast_momentum_summary', 'No closure-forecast momentum summary is recorded yet.')}"
    )
    sustained_confirmation_hotspots = summary.get("sustained_confirmation_hotspots") or []
    sustained_clearance_hotspots = summary.get("sustained_clearance_hotspots") or []
    if sustained_confirmation_hotspots:
        for hotspot in sustained_confirmation_hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Confirmation hotspot')} [{hotspot.get('scope', 'class')}] -> "
                f"{hotspot.get('closure_forecast_momentum_status', 'sustained-confirmation')} at "
                f"{hotspot.get('closure_forecast_momentum_score', 0.0):.2f}"
            )
    elif sustained_clearance_hotspots:
        for hotspot in sustained_clearance_hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Clearance hotspot')} [{hotspot.get('scope', 'class')}] -> "
                f"{hotspot.get('closure_forecast_momentum_status', 'sustained-clearance')} at "
                f"{hotspot.get('closure_forecast_momentum_score', 0.0):.2f}"
            )
    else:
        lines.append("- No closure-forecast momentum hotspots are recorded in the recent window.")
    lines.append("")
    lines.append("## Hysteresis Decay Controls")
    lines.append("")
    lines.append(
        f"- Decay status: {summary.get('primary_target_closure_forecast_decay_status', 'none')} "
        f"({summary.get('primary_target_closure_forecast_decay_reason', 'No closure-forecast decay reason is recorded yet.')})"
    )
    lines.append(
        f"- {summary.get('closure_forecast_decay_summary', 'No closure-forecast decay summary is recorded yet.')}"
    )
    lines.append("")
    lines.append("## Closure Forecast Refresh Recovery")
    lines.append("")
    lines.append(
        f"- Refresh recovery: {summary.get('primary_target_closure_forecast_refresh_recovery_status', 'none')} "
        f"({summary.get('primary_target_closure_forecast_refresh_recovery_score', 0.0):.2f})"
    )
    if primary_target.get("recent_closure_forecast_refresh_path"):
        lines.append(
            f"- Recent closure-forecast refresh path: {primary_target.get('recent_closure_forecast_refresh_path')}"
        )
    lines.append(
        f"- {summary.get('closure_forecast_refresh_recovery_summary', 'No closure-forecast refresh-recovery summary is recorded yet.')}"
    )
    recovering_confirmation_hotspots = summary.get("recovering_confirmation_hotspots") or []
    recovering_clearance_hotspots = summary.get("recovering_clearance_hotspots") or []
    if recovering_confirmation_hotspots:
        for hotspot in recovering_confirmation_hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Confirmation recovery hotspot')} [{hotspot.get('scope', 'class')}] -> "
                f"{hotspot.get('closure_forecast_refresh_recovery_status', 'recovering-confirmation')} at "
                f"{hotspot.get('closure_forecast_refresh_recovery_score', 0.0):.2f}"
            )
    elif recovering_clearance_hotspots:
        for hotspot in recovering_clearance_hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Clearance recovery hotspot')} [{hotspot.get('scope', 'class')}] -> "
                f"{hotspot.get('closure_forecast_refresh_recovery_status', 'recovering-clearance')} at "
                f"{hotspot.get('closure_forecast_refresh_recovery_score', 0.0):.2f}"
            )
    else:
        lines.append("- No closure-forecast refresh-recovery hotspots are recorded in the recent window.")
    lines.append("")
    lines.append("## Reacquisition Controls")
    lines.append("")
    lines.append(
        f"- Reacquisition status: {summary.get('primary_target_closure_forecast_reacquisition_status', 'none')} "
        f"({summary.get('primary_target_closure_forecast_reacquisition_reason', 'No closure-forecast reacquisition reason is recorded yet.')})"
    )
    lines.append(
        f"- {summary.get('closure_forecast_reacquisition_summary', 'No closure-forecast reacquisition summary is recorded yet.')}"
    )
    lines.append("")
    lines.append("## Reacquisition Persistence")
    lines.append("")
    lines.append(
        f"- Persistence status: {summary.get('primary_target_closure_forecast_reacquisition_persistence_status', 'none')} "
        f"({summary.get('primary_target_closure_forecast_reacquisition_persistence_score', 0.0):.2f}; "
        f"{summary.get('primary_target_closure_forecast_reacquisition_age_runs', 0)} run(s))"
    )
    if primary_target.get("recent_reacquisition_persistence_path"):
        lines.append(
            f"- Recent reacquisition persistence path: {primary_target.get('recent_reacquisition_persistence_path')}"
        )
    lines.append(
        f"- {summary.get('closure_forecast_reacquisition_persistence_summary', 'No reacquisition-persistence summary is recorded yet.')}"
    )
    just_reacquired_hotspots = summary.get("just_reacquired_hotspots") or []
    holding_reacquisition_hotspots = summary.get("holding_reacquisition_hotspots") or []
    if just_reacquired_hotspots:
        for hotspot in just_reacquired_hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Just reacquired hotspot')} [{hotspot.get('scope', 'class')}] -> "
                f"{hotspot.get('closure_forecast_reacquisition_persistence_status', 'just-reacquired')} at "
                f"{hotspot.get('closure_forecast_reacquisition_persistence_score', 0.0):.2f}"
            )
    elif holding_reacquisition_hotspots:
        for hotspot in holding_reacquisition_hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Holding reacquisition hotspot')} [{hotspot.get('scope', 'class')}] -> "
                f"{hotspot.get('closure_forecast_reacquisition_persistence_status', 'holding-confirmation')} at "
                f"{hotspot.get('closure_forecast_reacquisition_persistence_score', 0.0):.2f}"
            )
    else:
        lines.append("- No reacquisition-persistence hotspots are recorded in the recent window.")
    lines.append("")
    lines.append("## Recovery Churn Controls")
    lines.append("")
    lines.append(
        f"- Churn status: {summary.get('primary_target_closure_forecast_recovery_churn_status', 'none')} "
        f"({summary.get('primary_target_closure_forecast_recovery_churn_reason', 'No recovery-churn reason is recorded yet.')})"
    )
    if primary_target.get("recent_recovery_churn_path"):
        lines.append(
            f"- Recent recovery churn path: {primary_target.get('recent_recovery_churn_path')}"
        )
    lines.append(
        f"- {summary.get('closure_forecast_recovery_churn_summary', 'No recovery-churn summary is recorded yet.')}"
    )
    recovery_churn_hotspots = summary.get("recovery_churn_hotspots") or []
    if recovery_churn_hotspots:
        for hotspot in recovery_churn_hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Recovery churn hotspot')} [{hotspot.get('scope', 'class')}] -> "
                f"{hotspot.get('closure_forecast_recovery_churn_status', 'watch')} at "
                f"{hotspot.get('closure_forecast_recovery_churn_score', 0.0):.2f}"
            )
    else:
        lines.append("- No recovery-churn hotspots are recorded in the recent window.")
    lines.append("")
    lines.append("## Closure Forecast Hysteresis")
    lines.append("")
    lines.append(
        f"- Hysteresis status: {summary.get('primary_target_closure_forecast_hysteresis_status', 'none')} "
        f"({summary.get('primary_target_closure_forecast_hysteresis_reason', 'No closure-forecast hysteresis reason is recorded yet.')})"
    )
    lines.append(
        f"- {summary.get('closure_forecast_stability_summary', 'No closure-forecast stability summary is recorded yet.')}"
    )
    lines.append(
        f"- {summary.get('closure_forecast_hysteresis_summary', 'No closure-forecast hysteresis summary is recorded yet.')}"
    )
    oscillating_closure_forecast_hotspots = summary.get("oscillating_closure_forecast_hotspots") or []
    if oscillating_closure_forecast_hotspots:
        for hotspot in oscillating_closure_forecast_hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Oscillating forecast hotspot')} [{hotspot.get('scope', 'class')}] -> "
                f"{hotspot.get('closure_forecast_stability_status', 'oscillating')} across "
                f"{hotspot.get('recent_closure_forecast_path', 'no forecast path recorded')}"
            )
    else:
        lines.append("- No oscillating closure-forecast hotspots are recorded in the recent window.")
    lines.append("")
    lines.append("## Recommendation Drift")
    lines.append("")
    lines.append(
        f"- Drift status: {summary.get('recommendation_drift_status', 'stable')} "
        f"({summary.get('recommendation_drift_summary', 'No recommendation-drift summary is recorded yet.')})"
    )
    hotspots = summary.get("policy_flip_hotspots") or []
    if hotspots:
        for hotspot in hotspots[:3]:
            lines.append(
                f"- {hotspot.get('label', 'Recent hotspot')} [{hotspot.get('scope', 'target')}] -> "
                f"{hotspot.get('flip_count', 0)} flip(s) across {hotspot.get('recent_policy_path', '')}"
            )
    else:
        lines.append("- No policy-flip hotspots are recorded in the recent window.")
    lines.append("")
    lines.append("## What Got Better")
    lines.append("")
    if resolved_count:
        lines.append(f"- {resolved_count} attention item(s) cleared since the last run.")
    elif summary.get("trend_status") == "quiet":
        lines.append(
            f"- The queue is quiet and has held for {summary.get('quiet_streak_runs', 0)} consecutive run(s)."
        )
    else:
        lines.append("- No meaningful recovery signal is recorded in this handoff.")
    lines.append("")
    lines.append("## What Needs Attention Now")
    lines.append("")
    if primary_target_label:
        lines.append(f"- Primary target: {primary_target_label}")
        if primary_target.get("recommended_action"):
            lines.append(f"- Next step: {primary_target.get('recommended_action')}")
    else:
        lines.append("- No blocked or urgent target is currently active.")
    if queue:
        for item in queue[:3]:
            repo = f"{item.get('repo')}: " if item.get("repo") else ""
            lines.append(
                f"- [{item.get('lane_label', item.get('lane', 'ready'))}] {repo}{item.get('title', 'Triage item')} -> {item.get('recommended_action', 'Review the latest state.')}"
            )
    lines.append("")
    lines.append("## What Is Still Stuck")
    lines.append("")
    if persisting_count:
        lines.append(f"- {persisting_count} attention item(s) are still open from the previous run.")
    if summary.get("follow_through_summary"):
        lines.append(f"- {summary.get('follow_through_summary')}")
    if not persisting_count and not summary.get("follow_through_summary"):
        lines.append("- Nothing currently looks sticky across the recent run window.")
    lines.append("")
    lines.append("## Why This Is Still Open")
    lines.append("")
    if summary.get("primary_target_reason"):
        lines.append(f"- {summary.get('primary_target_reason')}")
    else:
        lines.append("- No active top-target rationale is recorded.")
    lines.append("")
    lines.append("## What We Tried")
    lines.append("")
    if summary.get("primary_target_last_intervention"):
        intervention = summary.get("primary_target_last_intervention") or {}
        lines.append(
            f"- {_intervention_markdown(intervention)}"
        )
    elif summary.get("recent_interventions"):
        for intervention in (summary.get("recent_interventions") or [])[:3]:
            lines.append(f"- {_intervention_markdown(intervention)}")
    else:
        lines.append("- No recent intervention is recorded in the evidence window yet.")
    lines.append("")
    lines.append("## What Counts As Done")
    lines.append("")
    if summary.get("primary_target_done_criteria"):
        lines.append(f"- {summary.get('primary_target_done_criteria')}")
    if summary.get("closure_guidance"):
        lines.append(f"- {summary.get('closure_guidance')}")
    if not summary.get("primary_target_done_criteria") and not summary.get("closure_guidance"):
        lines.append("- No active done-state guidance is recorded.")
    lines.append("")
    lines.append("## Resolution Evidence")
    lines.append("")
    lines.append(f"- {summary.get('primary_target_resolution_evidence', 'No resolution evidence is recorded yet.')}")
    lines.append(f"- {summary.get('resolution_evidence_summary', 'No recent resolution-evidence rollup is recorded yet.')}")
    lines.append("")
    lines.append("## Aging Pressure")
    lines.append("")
    lines.append(
        f"- Chronic items: {summary.get('chronic_item_count', 0)} | Newly stale items: {summary.get('newly_stale_count', 0)}"
    )
    lines.append(
        f"- Attention age bands: {summary.get('attention_age_bands', {}) or {'0-1 days': 0, '2-7 days': 0, '8-21 days': 0, '22+ days': 0}}"
    )
    if longest_label:
        lines.append(
            f"- Longest persisting item: {longest_label} ({longest_persisting.get('age_days', 0)} day(s), {longest_persisting.get('aging_status', 'fresh')})"
        )
    else:
        lines.append("- No persisting item is currently recorded.")
    lines.append("")
    lines.append("## What Reopened")
    lines.append("")
    if summary.get("reopened_after_resolution_count", 0):
        lines.append(
            f"- {summary.get('reopened_after_resolution_count', 0)} item(s) reopened after an earlier quiet or resolved state."
        )
    else:
        lines.append("- No item reopened after an earlier quiet or resolved state in the recent window.")
    lines.append("")
    lines.append("## Confidence Validation")
    lines.append("")
    lines.append(
        f"- Current primary-target confidence: {summary.get('primary_target_confidence_label', 'low')} "
        f"({summary.get('primary_target_confidence_score', 0.0):.2f})"
    )
    lines.append(
        f"- Calibration status: {summary.get('confidence_validation_status', 'insufficient-data')} "
        f"-> {summary.get('confidence_calibration_summary', 'No confidence-calibration summary is recorded yet.')}"
    )
    lines.append(
        f"- High-confidence hit rate: {summary.get('high_confidence_hit_rate', 0.0):.0%} | "
        f"Medium-confidence hit rate: {summary.get('medium_confidence_hit_rate', 0.0):.0%} | "
        f"Low-confidence caution rate: {summary.get('low_confidence_caution_rate', 0.0):.0%}"
    )
    recent_validation_outcomes = summary.get("recent_validation_outcomes") or []
    if recent_validation_outcomes:
        for item in recent_validation_outcomes[:3]:
            lines.append(
                f"- {item.get('target_label', 'Operator target')} "
                f"[{item.get('confidence_label', 'low')}] -> "
                f"{str(item.get('outcome', 'unresolved')).replace('_', ' ')}"
            )
    else:
        lines.append("- No judged confidence outcomes are recorded yet.")
    lines.append("")
    if queue:
        lines.append("## Top Queue Items")
        lines.append("")
        for item in queue[:5]:
            repo = f"{item.get('repo')}: " if item.get("repo") else ""
            lines.append(f"- [{item.get('lane_label', item.get('lane', 'ready'))}] {repo}{item.get('title', 'Triage item')}")
            lines.append(f"  - Why: {item.get('summary', 'No summary available.')}")
            lines.append(f"  - Next: {item.get('recommended_action', 'Review the latest state.')}")
        lines.append("")
    if recent_changes:
        lines.append("## Recent Changes")
        lines.append("")
        for change in recent_changes[:5]:
            subject = change.get("repo") or change.get("repo_full_name") or change.get("item_id") or "portfolio"
            lines.append(f"- {change.get('generated_at', '')[:10]} {subject}: {change.get('summary', change.get('kind', 'change'))}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _intervention_markdown(intervention: dict) -> str:
    when = (intervention.get("recorded_at") or "")[:10]
    event_type = intervention.get("event_type", "recorded")
    outcome = intervention.get("outcome", event_type)
    repo = f"{intervention.get('repo')}: " if intervention.get("repo") else ""
    title = intervention.get("title", "")
    return f"{when} {event_type} for {repo}{title} ({outcome})".strip()


def build_scheduled_handoff(
    output_dir: Path,
    *,
    issue_state: str = "absent",
    issue_number: str = "",
    issue_url: str = "",
) -> dict:
    control_center_path = _latest_artifact(output_dir, "operator-control-center-*.json")
    control_center = _load_json(control_center_path)
    if not control_center:
        raise FileNotFoundError("No operator control-center artifact was found in the output directory.")

    diff_data = _load_json(_latest_artifact(output_dir, "audit-diff-*.json"))
    summary = control_center.get("operator_summary", {})
    username = control_center.get("username", "unknown")
    generated_at = control_center.get("generated_at", "")
    stamp = (generated_at or "unknown").split("T", 1)[0]
    markdown_path = output_dir / f"scheduled-handoff-{username}-{stamp}.md"
    json_path = output_dir / f"scheduled-handoff-{username}-{stamp}.json"
    issue_candidate = _issue_candidate(
        summary,
        diff_data,
        username,
        markdown_path,
        issue_state=issue_state,
        issue_number=issue_number,
        issue_url=issue_url,
    )
    payload = {
        "status": "ok",
        "username": username,
        "generated_at": generated_at,
        "control_center_reference": str(control_center_path),
        "report_reference": control_center.get("report_reference", ""),
        "operator_summary": summary,
        "operator_queue": control_center.get("operator_queue", []),
        "operator_recent_changes": control_center.get("operator_recent_changes", []),
        "issue_candidate": issue_candidate,
    }
    markdown_path.write_text(render_scheduled_handoff_markdown(payload))
    payload["markdown_path"] = str(markdown_path)
    json_path.write_text(json.dumps(payload, indent=2))
    payload["json_path"] = str(json_path)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="scheduled-handoff",
        description="Build scheduled operator handoff artifacts from the latest control-center output.",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory that contains the latest audit/control-center artifacts.",
    )
    parser.add_argument(
        "--issue-state",
        choices=["absent", "open", "closed"],
        default="absent",
        help="Current state of the canonical scheduled handoff issue, if one already exists.",
    )
    parser.add_argument(
        "--issue-number",
        default="",
        help="Existing canonical issue number when one is already present.",
    )
    parser.add_argument(
        "--issue-url",
        default="",
        help="Existing canonical issue URL when one is already present.",
    )
    args = parser.parse_args()
    payload = build_scheduled_handoff(
        Path(args.output_dir),
        issue_state=args.issue_state,
        issue_number=args.issue_number,
        issue_url=args.issue_url,
    )
    issue = payload.get("issue_candidate", {})
    print(f"Scheduled handoff: {payload.get('markdown_path', '')}")
    print(f"Issue automation: {issue.get('action', 'quiet')} ({issue.get('reason', 'quiet')})")


if __name__ == "__main__":
    main()
