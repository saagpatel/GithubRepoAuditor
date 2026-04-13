from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from src.models import AuditReport, RepoAudit
from src.report_enrichment import (
    build_follow_through_checkpoint,
    build_follow_through_checkpoint_status_label,
    build_follow_through_escalation_status_label,
    build_follow_through_escalation_summary,
    build_follow_through_reacquisition_confidence_retirement_status_label,
    build_follow_through_reacquisition_confidence_retirement_summary,
    build_follow_through_reacquisition_consolidation_status_label,
    build_follow_through_reacquisition_consolidation_summary,
    build_follow_through_reacquisition_durability_status_label,
    build_follow_through_reacquisition_durability_summary,
    build_follow_through_reacquisition_revalidation_recovery_status_label,
    build_follow_through_reacquisition_revalidation_recovery_summary,
    build_follow_through_reacquisition_softening_decay_status_label,
    build_follow_through_reacquisition_softening_decay_summary,
    build_follow_through_recovery_freshness_status_label,
    build_follow_through_recovery_freshness_summary,
    build_follow_through_recovery_memory_reset_status_label,
    build_follow_through_recovery_memory_reset_summary,
    build_follow_through_recovery_persistence_status_label,
    build_follow_through_recovery_persistence_summary,
    build_follow_through_recovery_reacquisition_status_label,
    build_follow_through_recovery_reacquisition_summary,
    build_follow_through_recovery_rebuild_strength_status_label,
    build_follow_through_recovery_rebuild_strength_summary,
    build_follow_through_recovery_status_label,
    build_follow_through_recovery_summary,
    build_follow_through_relapse_churn_status_label,
    build_follow_through_relapse_churn_summary,
    build_follow_through_status_label,
    build_follow_through_summary,
    build_last_movement_label,
    build_queue_pressure_summary,
    build_repo_briefing,
    build_run_change_counts,
    build_run_change_summary,
    build_top_recommendation_summary,
    build_trust_actionability_summary,
    build_weekly_review_pack,
    no_linked_artifact_summary,
)

TIER_ORDER = ["shipped", "functional", "wip", "skeleton", "abandoned"]


def _date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _truncate(text: str | None, length: int = 60) -> str:
    if not text:
        return "—"
    return text[:length] + "..." if len(text) > length else text


def _file_path(output_dir: Path, prefix: str, username: str, dt: datetime, ext: str) -> Path:
    return output_dir / f"{prefix}-{username}-{_date_str(dt)}.{ext}"


# ── JSON sanitization ───────────────────────────────────────────────

_CONTROL_CHAR_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')


def _sanitize_for_json(obj: object) -> object:
    """Recursively strip control characters from strings to prevent JSON corruption."""
    if isinstance(obj, str):
        return _CONTROL_CHAR_RE.sub('', obj)
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    return obj


def _has_preflight_issues(preflight_summary: dict) -> bool:
    return bool(preflight_summary and (preflight_summary.get("blocking_errors") or preflight_summary.get("warnings")))


# ── JSON Report ──────────────────────────────────────────────────────


def write_json_report(report: AuditReport, output_dir: Path) -> Path:
    """Write the full audit report as JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = _file_path(output_dir, "audit-report", report.username, report.generated_at, "json")

    with open(path, "w") as f:
        json.dump(_sanitize_for_json(report.to_dict()), f, indent=2)

    return path


# ── Raw metadata (backwards compat) ─────────────────────────────────


def write_raw_metadata(report: AuditReport, output_dir: Path) -> Path:
    """Write raw_metadata.json for backwards compatibility."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "raw_metadata.json"

    data = {
        "schema_version": report.schema_version,
        "username": report.username,
        "generated_at": report.generated_at.isoformat(),
        "total_repos": report.total_repos,
        "repos_audited": report.repos_audited,
        "average_score": report.average_score,
        "scoring_profile": report.scoring_profile,
        "run_mode": report.run_mode,
        "portfolio_baseline_size": report.portfolio_baseline_size,
        "baseline_signature": report.baseline_signature,
        "baseline_context": report.baseline_context,
        "lenses": report.lenses,
        "hotspots": report.hotspots,
        "implementation_hotspots": report.implementation_hotspots,
        "implementation_hotspots_summary": report.implementation_hotspots_summary,
        "security_posture": report.security_posture,
        "security_governance_preview": report.security_governance_preview,
        "collections": report.collections,
        "profiles": report.profiles,
        "scenario_summary": report.scenario_summary,
        "action_backlog": report.action_backlog,
        "campaign_summary": report.campaign_summary,
        "writeback_preview": report.writeback_preview,
        "writeback_results": report.writeback_results,
        "action_runs": report.action_runs,
        "external_refs": report.external_refs,
        "managed_state_drift": report.managed_state_drift,
        "rollback_preview": report.rollback_preview,
        "campaign_history": report.campaign_history,
        "governance_preview": report.governance_preview,
        "governance_approval": report.governance_approval,
        "governance_results": report.governance_results,
        "governance_history": report.governance_history,
        "governance_drift": report.governance_drift,
        "governance_summary": report.governance_summary,
        "review_summary": report.review_summary,
        "review_alerts": report.review_alerts,
        "material_changes": report.material_changes,
        "review_targets": report.review_targets,
        "review_history": report.review_history,
        "watch_state": report.watch_state,
        "operator_summary": report.operator_summary,
        "operator_queue": report.operator_queue,
        "portfolio_catalog_summary": report.portfolio_catalog_summary,
        "intent_alignment_summary": report.intent_alignment_summary,
        "scorecards_summary": report.scorecards_summary,
        "scorecard_programs": report.scorecard_programs,
        "run_change_summary": report.run_change_summary,
        "run_change_counts": report.run_change_counts,
        "runtime_breakdown": report.runtime_breakdown,
        "tier_distribution": report.tier_distribution,
        "audits": [a.to_dict() for a in report.audits],
        "errors": report.errors,
    }
    if report.preflight_summary:
        data["preflight_summary"] = report.preflight_summary

    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    return path


# ── PCC Export ───────────────────────────────────────────────────────


def write_pcc_export(report: AuditReport, output_dir: Path) -> Path:
    """Write PCC-compatible flat JSON array."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = _file_path(output_dir, "pcc-import", report.username, report.generated_at, "json")

    records = []
    for audit in report.audits:
        m = audit.metadata
        records.append({
            "name": m.name,
            "full_name": m.full_name,
            "status": audit.completeness_tier,
            "score": round(audit.overall_score, 3),
            "url": m.html_url,
            "last_activity": m.pushed_at.isoformat() if m.pushed_at else None,
            "language": m.language,
            "tier": audit.completeness_tier,
            "flags": audit.flags,
            "private": m.private,
            "description": m.description,
        })

    with open(path, "w") as f:
        json.dump(records, f, indent=2)

    return path


# ── Markdown Report ──────────────────────────────────────────────────


def write_markdown_report(
    report: AuditReport,
    output_dir: Path,
    diff_data: dict | None = None,
) -> Path:
    """Write human-readable Markdown audit report."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = _file_path(output_dir, "audit-report", report.username, report.generated_at, "md")

    lines: list[str] = []
    _w = lines.append

    # Header
    _w(f"# GitHub Repo Audit: {report.username}")
    _w("")
    _w(f"*Generated: {_date_str(report.generated_at)} | "
       f"Repos audited: {report.repos_audited} / {report.total_repos} | "
       f"Portfolio Grade: **{report.portfolio_grade}***")
    _w("")

    # Summary table
    _w("## Summary")
    _w("")
    _w("| Metric | Value |")
    _w("|--------|-------|")
    _w(f"| Total repos | {report.total_repos} |")
    _w(f"| Repos audited | {report.repos_audited} |")
    _w(f"| Average score | {report.average_score:.2f} |")
    _w(f"| Errors | {len(report.errors)} |")
    _w(f"| Schema version | {report.schema_version} |")
    _w("")

    if _has_preflight_issues(report.preflight_summary):
        _w("### Preflight Diagnostics")
        _w("")
        _w(
            f"- Status: **{report.preflight_summary.get('status', 'unknown')}** | "
            f"Errors: {report.preflight_summary.get('blocking_errors', 0)} | "
            f"Warnings: {report.preflight_summary.get('warnings', 0)}"
        )
        for check in (report.preflight_summary.get("checks") or [])[:5]:
            _w(f"- {check.get('summary', 'Issue detected')} ({check.get('category', 'setup')})")
        _w("")

    report_dict = report.to_dict()
    run_change_counts = report.run_change_counts or build_run_change_counts(diff_data)
    queue_pressure_summary = build_queue_pressure_summary(report_dict, diff_data)
    top_recommendation_summary = build_top_recommendation_summary(report_dict)
    trust_actionability_summary = build_trust_actionability_summary(report_dict)
    weekly_pack = build_weekly_review_pack(report_dict, diff_data)
    _w("### Run Changes")
    _w("")
    _w(f"- Summary: {report.run_change_summary or build_run_change_summary(diff_data)}")
    _w(f"- Why It Matters: {queue_pressure_summary}")
    _w(f"- What To Do Next: {top_recommendation_summary}")
    _w(
        "- Counts: "
        f"{run_change_counts.get('score_improvements', 0)} improvements, "
        f"{run_change_counts.get('score_regressions', 0)} regressions, "
        f"{run_change_counts.get('tier_promotions', 0)} promotions, "
        f"{run_change_counts.get('tier_demotions', 0)} demotions, "
        f"{run_change_counts.get('new_repos', 0)} new repos"
    )
    _w("")

    _w("## Weekly Review Pack")
    _w("")
    _w(f"- Portfolio Headline: {weekly_pack.get('portfolio_headline', 'No weekly headline is recorded yet.')}")
    _w(f"- Run Changes: {weekly_pack.get('run_change_summary', build_run_change_summary(diff_data))}")
    _w(f"- Queue Pressure: {weekly_pack.get('queue_pressure_summary', queue_pressure_summary)}")
    _w(f"- Trust / Actionability: {weekly_pack.get('trust_actionability_summary', trust_actionability_summary)}")
    _w(f"- What To Do This Week: {weekly_pack.get('what_to_do_this_week', top_recommendation_summary)}")
    _w(f"- Portfolio Catalog: {weekly_pack.get('portfolio_catalog_summary', 'No portfolio catalog contract is recorded yet.')}")
    _w(f"- Intent Alignment: {weekly_pack.get('intent_alignment_summary', 'Intent alignment cannot be judged until a portfolio catalog contract exists.')}")
    _w(f"- Scorecards: {weekly_pack.get('scorecards_summary', 'No maturity scorecard is recorded yet.')}")
    _w(f"- Implementation Hotspots: {weekly_pack.get('implementation_hotspots_summary', 'No meaningful implementation hotspots are currently surfaced.')}")
    _w("")
    _w("### Top Attention")
    _w("")
    for item in weekly_pack.get("top_attention", [])[:5]:
        _w(
            f"- [{item.get('lane', 'ready')}] {item.get('repo', 'Portfolio')}: {item.get('title', 'Operator attention item')}"
        )
        _w(f"  - What Changed: {item.get('last_movement', 'Current run')}")
        _w(f"  - Why It Matters: {item.get('why', 'Operator pressure is active.')}")
        _w(f"  - What To Do Next: {item.get('next_step', 'Review the latest state.')}")
        _w(f"  - Operator Focus: {item.get('operator_focus_line', 'Watch Closely: No operator focus bucket is currently surfaced.')}")
        _w(f"  - Catalog: {item.get('catalog_line', 'No portfolio catalog contract is recorded yet.')}")
        _w(f"  - Intent Alignment: {item.get('intent_alignment', 'missing-contract')} — {item.get('intent_alignment_summary', 'Intent alignment cannot be judged until a portfolio catalog contract exists.')}")
        _w(f"  - {item.get('scorecard_line', 'Scorecard: No maturity scorecard is recorded yet.')}")
        _w(f"  - Maturity Gap: {item.get('maturity_gap_summary', 'No maturity gap summary is recorded yet.')}")
        _w(f"  - Checkpoint Timing: {item.get('follow_through_checkpoint_timing', 'Unknown')}")
        _w(
            f"  - Next Checkpoint: {item.get('follow_through_checkpoint', 'Use the next run or linked artifact to confirm whether the recommendation moved.')}"
        )
    if not weekly_pack.get("top_attention"):
        _w("- No urgent attention items are currently surfaced.")
    _w("")
    _w("### Operator Focus")
    _w("")
    _w(f"- Summary: {weekly_pack.get('operator_focus_summary', 'No operator focus bucket is currently surfaced.')}")
    if weekly_pack.get("top_below_target_scorecard_items"):
        _w("- Scorecard Gaps:")
        for item in weekly_pack.get("top_below_target_scorecard_items", [])[:5]:
            _w(f"  - {item.get('repo', 'Repo')} — {item.get('summary', 'Below target.')}")
    _w(f"- Next Checkpoint: {weekly_pack.get('follow_through_checkpoint_summary', 'Use the next run or linked artifact to confirm whether the recommendation moved.')}")
    focus_sections = [
        ("Act Now", weekly_pack.get("top_act_now_items", []), "No immediate-action hotspots are currently surfaced."),
        ("Watch Closely", weekly_pack.get("top_watch_closely_items", []), "No watch-closely hotspots are currently surfaced."),
        ("Improving", weekly_pack.get("top_improving_items", []), "No clearly improving hotspots are currently surfaced."),
        ("Fragile", weekly_pack.get("top_fragile_items", []), "No fragile hotspots are currently surfaced."),
        ("Revalidate", weekly_pack.get("top_revalidate_items", []), "No revalidation hotspots are currently surfaced."),
    ]
    for label, items, empty_message in focus_sections:
        _w(f"- {label}:")
        if items:
            for item in items[:3]:
                item_label = f"{item.get('repo')}: {item.get('title')}" if item.get("repo") else item.get("title", "Operator item")
                _w(f"  - {item_label} — {item.get('operator_focus_summary', 'No operator focus bucket is currently surfaced.')}")
        else:
            _w(f"  - {empty_message}")
    _w("")
    _w("### Top Repo Drilldowns")
    _w("")
    for briefing in weekly_pack.get("repo_briefings", [])[:3]:
        _w(f"#### {briefing.get('headline', briefing.get('repo', 'Repo briefing'))}")
        _w("")
        _w(f"- Current State: {briefing.get('current_state_line', 'No current-state summary is recorded yet.')}")
        _w(f"- What Changed: {briefing.get('what_changed_line', 'No change summary is recorded yet.')}")
        _w(f"- Why It Matters: {briefing.get('why_it_matters_line', 'No explanation summary is recorded yet.')}")
        _w(f"- What To Do Next: {briefing.get('what_to_do_next_line', 'No next action is recorded yet.')}")
        _w(f"- Operator Focus: {briefing.get('operator_focus_line', 'Watch Closely: No operator focus bucket is currently surfaced.')}")
        _w(f"- Catalog: {briefing.get('catalog_line', 'No portfolio catalog contract is recorded yet.')}")
        _w(f"- Intent Alignment: {briefing.get('intent_alignment_line', 'missing-contract: Intent alignment cannot be judged until a portfolio catalog contract exists.')}")
        _w(f"- {briefing.get('scorecard_line', 'Scorecard: No maturity scorecard is recorded yet.')}")
        _w(f"- Maturity Gap: {briefing.get('maturity_gap_summary', 'No maturity gap summary is recorded yet.')}")
        _w(f"- Checkpoint Timing: {briefing.get('checkpoint_timing_line', 'Unknown')}")
        _w(f"- What Would Count As Progress: {briefing.get('checkpoint_line', 'Use the next run or linked artifact to confirm whether the recommendation moved.')}")
        _w("")

    if report.operator_summary or report.operator_queue:
        _w("### Operator Control Center")
        _w("")
        _w(f"- Headline: {report.operator_summary.get('headline', 'No operator triage items are currently surfaced.')}")
        if report.operator_summary.get("source_run_id"):
            _w(f"- Source Run: `{report.operator_summary.get('source_run_id')}`")
        if report.operator_summary.get("report_reference"):
            _w(f"- Latest Report: `{report.operator_summary.get('report_reference')}`")
        if report.operator_summary.get("next_recommended_run_mode"):
            _w(f"- Next Recommended Run: `{report.operator_summary.get('next_recommended_run_mode')}`")
        if report.operator_summary.get("watch_strategy"):
            _w(f"- Watch Strategy: `{report.operator_summary.get('watch_strategy')}`")
        if report.operator_summary.get("watch_decision_summary"):
            _w(f"- Watch Decision: {report.operator_summary.get('watch_decision_summary')}")
        if report.operator_summary.get("what_changed"):
            _w(f"- What Changed: {report.operator_summary.get('what_changed')}")
        if report.operator_summary.get("why_it_matters"):
            _w(f"- Why It Matters: {report.operator_summary.get('why_it_matters')}")
        if report.operator_summary.get("what_to_do_next"):
            _w(f"- What To Do Next: {report.operator_summary.get('what_to_do_next')}")
        _w(f"- Queue Pressure: {queue_pressure_summary}")
        if report.operator_summary.get("trend_summary"):
            _w(f"- Trend: {report.operator_summary.get('trend_summary')}")
        if report.operator_summary.get("accountability_summary"):
            _w(f"- Accountability: {report.operator_summary.get('accountability_summary')}")
        if report.operator_summary.get("follow_through_summary"):
            _w(f"- Follow-Through: {report.operator_summary.get('follow_through_summary')}")
        if report.operator_summary.get("follow_through_checkpoint_summary"):
            _w(f"- Next Checkpoint: {report.operator_summary.get('follow_through_checkpoint_summary')}")
        if report.operator_summary.get("follow_through_escalation_summary"):
            _w(f"- Follow-Through Aging and Escalation: {report.operator_summary.get('follow_through_escalation_summary')}")
        if report.operator_summary.get("follow_through_recovery_summary"):
            _w(f"- Follow-Through Recovery and Escalation Retirement: {report.operator_summary.get('follow_through_recovery_summary')}")
        if report.operator_summary.get("follow_through_recovery_persistence_summary"):
            _w(f"- Follow-Through Recovery Persistence: {report.operator_summary.get('follow_through_recovery_persistence_summary')}")
        if report.operator_summary.get("follow_through_relapse_churn_summary"):
            _w(f"- Follow-Through Relapse Churn: {report.operator_summary.get('follow_through_relapse_churn_summary')}")
        if report.operator_summary.get("follow_through_recovery_freshness_summary"):
            _w(f"- Follow-Through Recovery Freshness: {report.operator_summary.get('follow_through_recovery_freshness_summary')}")
        if report.operator_summary.get("follow_through_recovery_memory_reset_summary"):
            _w(f"- Follow-Through Recovery Memory Reset: {report.operator_summary.get('follow_through_recovery_memory_reset_summary')}")
        if report.operator_summary.get("follow_through_recovery_rebuild_strength_summary"):
            _w(f"- Follow-Through Recovery Rebuild Strength: {report.operator_summary.get('follow_through_recovery_rebuild_strength_summary')}")
        if report.operator_summary.get("follow_through_recovery_reacquisition_summary"):
            _w(f"- Follow-Through Recovery Reacquisition: {report.operator_summary.get('follow_through_recovery_reacquisition_summary')}")
        if report.operator_summary.get("follow_through_recovery_reacquisition_durability_summary"):
            _w(f"- Follow-Through Reacquisition Durability: {report.operator_summary.get('follow_through_recovery_reacquisition_durability_summary')}")
        if report.operator_summary.get("follow_through_recovery_reacquisition_consolidation_summary"):
            _w(f"- Follow-Through Reacquisition Confidence: {report.operator_summary.get('follow_through_recovery_reacquisition_consolidation_summary')}")
        primary_target = report.operator_summary.get("primary_target") or {}
        if primary_target:
            repo = f"{primary_target.get('repo')}: " if primary_target.get("repo") else ""
            _w(f"- Primary Target: {repo}{primary_target.get('title', 'Operator target')}")
        if report.operator_summary.get("primary_target_reason"):
            _w(f"- Why This Is The Top Target: {report.operator_summary.get('primary_target_reason')}")
        if report.operator_summary.get("primary_target_done_criteria"):
            _w(f"- What Counts As Done: {report.operator_summary.get('primary_target_done_criteria')}")
        if report.operator_summary.get("closure_guidance"):
            _w(f"- Closure Guidance: {report.operator_summary.get('closure_guidance')}")
        if report.operator_summary.get("primary_target_last_intervention"):
            intervention = report.operator_summary.get("primary_target_last_intervention") or {}
            when = (intervention.get("recorded_at") or "")[:10]
            repo = f"{intervention.get('repo')}: " if intervention.get("repo") else ""
            title = intervention.get("title", "")
            event_type = intervention.get("event_type", "recorded")
            outcome = intervention.get("outcome", event_type)
            _w(f"- What We Tried: {when} {event_type} for {repo}{title} ({outcome})".strip())
        if report.operator_summary.get("primary_target_resolution_evidence"):
            _w(f"- Resolution Evidence: {report.operator_summary.get('primary_target_resolution_evidence')}")
        if report.operator_summary.get("primary_target_confidence_label"):
            _w(
                f"- Primary Target Confidence: {report.operator_summary.get('primary_target_confidence_label')} "
                f"({report.operator_summary.get('primary_target_confidence_score', 0.0):.2f})"
            )
        if report.operator_summary.get("primary_target_confidence_reasons"):
            _w(
                "- Confidence Reasons: "
                + ", ".join(report.operator_summary.get("primary_target_confidence_reasons") or [])
            )
        if report.operator_summary.get("next_action_confidence_label"):
            _w(
                f"- Next Action Confidence: {report.operator_summary.get('next_action_confidence_label')} "
                f"({report.operator_summary.get('next_action_confidence_score', 0.0):.2f})"
            )
        if report.operator_summary.get("primary_target_trust_policy"):
            _w(
                f"- Trust Policy: {report.operator_summary.get('primary_target_trust_policy')} "
                f"({report.operator_summary.get('primary_target_trust_policy_reason', 'No trust-policy reason is recorded yet.')})"
            )
        _w(f"- Trust / Actionability: {trust_actionability_summary}")
        _w(f"- Top Recommendation: {top_recommendation_summary}")
        if report.operator_summary.get("adaptive_confidence_summary"):
            _w(f"- Why This Confidence Is Actionable: {report.operator_summary.get('adaptive_confidence_summary')}")
        if report.operator_summary.get("primary_target_exception_status") not in {None, "", "none"}:
            _w(
                f"- Trust Policy Exception: {report.operator_summary.get('primary_target_exception_status')} "
                f"({report.operator_summary.get('primary_target_exception_reason', 'No trust-policy exception reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_exception_pattern_status") not in {None, "", "none"}:
            _w(
                f"- Exception Pattern Learning: {report.operator_summary.get('primary_target_exception_pattern_status')} "
                f"({report.operator_summary.get('primary_target_exception_pattern_reason', 'No exception-pattern reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_trust_recovery_status") not in {None, "", "none"}:
            _w(
                f"- Trust Recovery: {report.operator_summary.get('primary_target_trust_recovery_status')} "
                f"({report.operator_summary.get('primary_target_trust_recovery_reason', 'No trust-recovery reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_recovery_confidence_label"):
            _w(
                f"- Recovery Confidence: {report.operator_summary.get('primary_target_recovery_confidence_label')} "
                f"({report.operator_summary.get('primary_target_recovery_confidence_score', 0.0):.2f})"
            )
        if report.operator_summary.get("recovery_confidence_summary"):
            _w(f"- Recovery Confidence Summary: {report.operator_summary.get('recovery_confidence_summary')}")
        if report.operator_summary.get("primary_target_exception_retirement_status") not in {None, "", "none"}:
            _w(
                f"- Exception Retirement: {report.operator_summary.get('primary_target_exception_retirement_status')} "
                f"({report.operator_summary.get('primary_target_exception_retirement_reason', 'No exception-retirement reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_policy_debt_status") not in {None, "", "none"}:
            _w(
                f"- Policy Debt Cleanup: {report.operator_summary.get('primary_target_policy_debt_status')} "
                f"({report.operator_summary.get('primary_target_policy_debt_reason', 'No policy-debt reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_class_normalization_status") not in {None, "", "none"}:
            _w(
                f"- Class-Level Trust Normalization: {report.operator_summary.get('primary_target_class_normalization_status')} "
                f"({report.operator_summary.get('primary_target_class_normalization_reason', 'No class-normalization reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_class_memory_freshness_status"):
            _w(
                f"- Class Memory Freshness: {report.operator_summary.get('primary_target_class_memory_freshness_status')} "
                f"({report.operator_summary.get('primary_target_class_memory_freshness_reason', 'No class-memory freshness reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_class_decay_status") is not None:
            _w(
                f"- Trust Decay Controls: {report.operator_summary.get('primary_target_class_decay_status')} "
                f"({report.operator_summary.get('primary_target_class_decay_reason', 'No class-decay reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_class_trust_reweight_direction"):
            _w(
                f"- Class Trust Reweighting: {report.operator_summary.get('primary_target_class_trust_reweight_direction')} "
                f"({report.operator_summary.get('primary_target_class_trust_reweight_score', 0.0):.2f})"
            )
        if report.operator_summary.get("primary_target_class_trust_reweight_reasons"):
            _w(
                "- Why Class Guidance Shifted: "
                + ", ".join(report.operator_summary.get("primary_target_class_trust_reweight_reasons") or [])
            )
        if report.operator_summary.get("primary_target_class_trust_momentum_status"):
            _w(
                f"- Class Trust Momentum: {report.operator_summary.get('primary_target_class_trust_momentum_status')} "
                f"({report.operator_summary.get('primary_target_class_trust_momentum_score', 0.0):.2f})"
            )
        if report.operator_summary.get("primary_target_class_reweight_stability_status"):
            _w(
                f"- Reweighting Stability: {report.operator_summary.get('primary_target_class_reweight_stability_status')} "
                f"({report.operator_summary.get('primary_target_class_reweight_transition_status', 'none')}: "
                f"{report.operator_summary.get('primary_target_class_reweight_transition_reason', 'No class transition reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_class_transition_health_status"):
            _w(
                f"- Class Transition Health: {report.operator_summary.get('primary_target_class_transition_health_status')} "
                f"({report.operator_summary.get('primary_target_class_transition_health_reason', 'No class transition health reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_class_transition_resolution_status"):
            _w(
                f"- Pending Transition Resolution: {report.operator_summary.get('primary_target_class_transition_resolution_status')} "
                f"({report.operator_summary.get('primary_target_class_transition_resolution_reason', 'No class transition resolution reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_transition_closure_confidence_label"):
            _w(
                f"- Transition Closure Confidence: {report.operator_summary.get('primary_target_transition_closure_confidence_label')} "
                f"({report.operator_summary.get('primary_target_transition_closure_confidence_score', 0.0):.2f}; "
                f"{report.operator_summary.get('primary_target_transition_closure_likely_outcome', 'none')})"
            )
        if report.operator_summary.get("primary_target_class_pending_debt_status"):
            _w(
                f"- Class Pending Debt Audit: {report.operator_summary.get('primary_target_class_pending_debt_status')} "
                f"({report.operator_summary.get('primary_target_class_pending_debt_reason', 'No class pending-debt reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_pending_debt_freshness_status"):
            _w(
                f"- Pending Debt Freshness: {report.operator_summary.get('primary_target_pending_debt_freshness_status')} "
                f"({report.operator_summary.get('primary_target_pending_debt_freshness_reason', 'No pending-debt freshness reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reweight_direction"):
            _w(
                f"- Closure Forecast Reweighting: {report.operator_summary.get('primary_target_closure_forecast_reweight_direction')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reweight_score', 0.0):.2f})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_momentum_status"):
            _w(
                f"- Closure Forecast Momentum: {report.operator_summary.get('primary_target_closure_forecast_momentum_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_momentum_score', 0.0):.2f})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_freshness_status"):
            _w(
                f"- Closure Forecast Freshness: {report.operator_summary.get('primary_target_closure_forecast_freshness_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_freshness_reason', 'No closure-forecast freshness reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_stability_status"):
            _w(
                f"- Closure Forecast Hysteresis: {report.operator_summary.get('primary_target_closure_forecast_stability_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_hysteresis_status', 'none')}: "
                f"{report.operator_summary.get('primary_target_closure_forecast_hysteresis_reason', 'No closure-forecast hysteresis reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_decay_status"):
            _w(
                f"- Hysteresis Decay Controls: {report.operator_summary.get('primary_target_closure_forecast_decay_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_decay_reason', 'No closure-forecast decay reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_refresh_recovery_status"):
            _w(
                f"- Closure Forecast Refresh Recovery: {report.operator_summary.get('primary_target_closure_forecast_refresh_recovery_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_refresh_recovery_score', 0.0):.2f})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reacquisition_status"):
            _w(
                f"- Reacquisition Controls: {report.operator_summary.get('primary_target_closure_forecast_reacquisition_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reacquisition_reason', 'No closure-forecast reacquisition reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reacquisition_persistence_status"):
            _w(
                f"- Reacquisition Persistence: {report.operator_summary.get('primary_target_closure_forecast_reacquisition_persistence_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reacquisition_persistence_score', 0.0):.2f}; "
                f"{report.operator_summary.get('primary_target_closure_forecast_reacquisition_age_runs', 0)} run(s))"
            )
        if report.operator_summary.get("primary_target_closure_forecast_recovery_churn_status"):
            _w(
                f"- Recovery Churn Controls: {report.operator_summary.get('primary_target_closure_forecast_recovery_churn_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_recovery_churn_reason', 'No recovery-churn reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reacquisition_freshness_status"):
            _w(
                f"- Reacquisition Freshness: {report.operator_summary.get('primary_target_closure_forecast_reacquisition_freshness_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reacquisition_freshness_reason', 'No reacquisition-freshness reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_persistence_reset_status"):
            _w(
                f"- Persistence Reset Controls: {report.operator_summary.get('primary_target_closure_forecast_persistence_reset_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_persistence_reset_reason', 'No persistence-reset reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_refresh_recovery_status"):
            _w(
                f"- Reset Refresh Recovery: {report.operator_summary.get('primary_target_closure_forecast_reset_refresh_recovery_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_refresh_recovery_score', 0.0):.2f})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_status"):
            _w(
                f"- Reset Re-entry Controls: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_reason', 'No reset re-entry reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_persistence_status"):
            _w(
                f"- Reset Re-entry Persistence: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_persistence_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_persistence_score', 0.0):.2f}; "
                f"{report.operator_summary.get('primary_target_closure_forecast_reset_reentry_age_runs', 0)} run(s))"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_churn_status"):
            _w(
                f"- Reset Re-entry Churn Controls: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_churn_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_churn_reason', 'No reset re-entry churn reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_freshness_status"):
            _w(
                f"- Reset Re-entry Freshness: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_freshness_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_freshness_reason', 'No reset re-entry freshness reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_reset_status"):
            _w(
                f"- Reset Re-entry Reset Controls: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_reset_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_reset_reason', 'No reset re-entry reset reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_refresh_recovery_status"):
            _w(
                f"- Reset Re-entry Refresh Recovery: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_refresh_recovery_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_refresh_recovery_score', 0.0):.2f})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_status"):
            _w(
                f"- Reset Re-entry Rebuild Controls: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reason', 'No reset re-entry rebuild reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_freshness_status"):
            _w(
                f"- Reset Re-entry Rebuild Freshness: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_freshness_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_freshness_reason', 'No reset re-entry rebuild freshness reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reset_status"):
            _w(
                f"- Reset Re-entry Rebuild Reset Controls: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reset_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reset_reason', 'No reset re-entry rebuild reset reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_refresh_recovery_status"):
            _w(
                f"- Reset Re-entry Rebuild Refresh Recovery: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_refresh_recovery_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_refresh_recovery_score', 0.0):.2f})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_status"):
            _w(
                f"- Reset Re-entry Rebuild Re-entry Controls: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_reason', 'No reset re-entry rebuild re-entry reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_status"):
            _w(
                f"- Reset Re-entry Rebuild Re-Entry Persistence: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_score', 0.0):.2f}; "
                f"{report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_age_runs', 0)} run(s))"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_status"):
            _w(
                f"- Reset Re-entry Rebuild Re-Entry Churn Controls: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_reason', 'No reset re-entry rebuild re-entry churn reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_freshness_status"):
            _w(
                f"- Reset Re-entry Rebuild Re-Entry Freshness: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_freshness_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_freshness_reason', 'No reset re-entry rebuild re-entry freshness reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_reset_status"):
            _w(
                f"- Reset Re-entry Rebuild Re-Entry Reset Controls: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_reset_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_reset_reason', 'No reset re-entry rebuild re-entry reset reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status"):
            _w(
                f"- Reset Re-entry Rebuild Re-Entry Refresh Recovery: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status')} "
                f"({report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_summary', 'No reset re-entry rebuild re-entry refresh recovery summary is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_status"):
            _w(
                f"- Reset Re-entry Rebuild Re-Entry Restore Controls: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reason', 'No reset re-entry rebuild re-entry restore reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_status"):
            _w(
                f"- Reset Re-entry Rebuild Re-Entry Restore Freshness: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_reason', 'No reset re-entry rebuild re-entry restore freshness reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reset_status"):
            _w(
                f"- Reset Re-entry Rebuild Re-Entry Restore Reset Controls: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reset_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reset_reason', 'No reset re-entry rebuild re-entry restore reset reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_status"):
            _w(
                f"- Reset Re-entry Rebuild Re-Entry Restore Refresh Recovery: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_status')} "
                f"({report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_summary', 'No reset re-entry rebuild re-entry restore refresh recovery summary is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status"):
            _w(
                f"- Reset Re-entry Rebuild Re-Entry Restore Re-Restore Controls: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason', 'No reset re-entry rebuild re-entry restore re-restore reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_status"):
            _w(
                f"- Reset Re-entry Rebuild Re-Entry Restore Re-Restore Persistence: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_score', 0.0):.2f}; "
                f"{report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_age_runs', 0)} run(s))"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_status"):
            _w(
                f"- Reset Re-entry Rebuild Re-Entry Restore Re-Restore Churn Controls: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_reason', 'No reset re-entry rebuild re-entry restore re-restore churn reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status"):
            _w(
                f"- Reset Re-entry Rebuild Re-Entry Restore Re-Restore Freshness: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_reason', 'No reset re-entry rebuild re-entry restore re-restore freshness reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_status"):
            _w(
                f"- Reset Re-entry Rebuild Re-Entry Restore Re-Restore Reset Controls: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_reason', 'No reset re-entry rebuild re-entry restore re-restore reset reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_status"):
            _w(
                f"- Reset Re-entry Rebuild Re-Entry Restore Re-Restore Refresh Recovery: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_status')} "
                f"({report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_summary', 'No reset re-entry rebuild re-entry restore re-restore refresh recovery summary is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status"):
            _w(
                f"- Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Controls: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason', 'No reset re-entry rebuild re-entry restore re-re-restore reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status"):
            _w(
                f"- Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Persistence: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score', 0.0):.2f}; "
                f"{report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs', 0)} run(s))"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status"):
            _w(
                f"- Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Churn Controls: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason', 'No reset re-entry rebuild re-entry restore re-re-restore churn reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status"):
            _w(
                f"- Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Freshness: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_reason', 'No reset re-entry rebuild re-entry restore re-re-restore freshness reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status"):
            _w(
                f"- Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Reset Controls: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_reason', 'No reset re-entry rebuild re-entry restore re-re-restore reset reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status"):
            _w(
                f"- Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Refresh Recovery: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status')} "
                f"({report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_summary', 'No reset re-entry rebuild re-entry restore re-re-restore refresh recovery summary is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status"):
            _w(
                f"- Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Controls: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_reason', 'No reset re-entry rebuild re-entry restore re-re-re-restore reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status"):
            _w(
                f"- Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Persistence: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score', 0.0):.2f}; "
                f"{report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs', 0)} run(s))"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status"):
            _w(
                f"- Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Churn Controls: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason', 'No reset re-entry rebuild re-entry restore re-re-re-restore churn reason is recorded yet.')})"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_persistence_status"):
            _w(
                f"- Reset Re-entry Rebuild Persistence: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_persistence_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_persistence_score', 0.0):.2f}; "
                f"{report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_age_runs', 0)} run(s))"
            )
        if report.operator_summary.get("primary_target_closure_forecast_reset_reentry_rebuild_churn_status"):
            _w(
                f"- Reset Re-entry Rebuild Churn Controls: {report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_churn_status')} "
                f"({report.operator_summary.get('primary_target_closure_forecast_reset_reentry_rebuild_churn_reason', 'No reset re-entry rebuild churn reason is recorded yet.')})"
            )
        if report.operator_summary.get("recommendation_drift_status"):
            _w(
                f"- Recommendation Drift: {report.operator_summary.get('recommendation_drift_status')} "
                f"({report.operator_summary.get('recommendation_drift_summary', 'No recommendation-drift summary is recorded yet.')})"
            )
        if report.operator_summary.get("exception_pattern_summary"):
            _w(f"- Exception Pattern Summary: {report.operator_summary.get('exception_pattern_summary')}")
        if report.operator_summary.get("exception_retirement_summary"):
            _w(f"- Exception Retirement Summary: {report.operator_summary.get('exception_retirement_summary')}")
        if report.operator_summary.get("policy_debt_summary"):
            _w(f"- Policy Debt Summary: {report.operator_summary.get('policy_debt_summary')}")
        if report.operator_summary.get("trust_normalization_summary"):
            _w(f"- Trust Normalization Summary: {report.operator_summary.get('trust_normalization_summary')}")
        if report.operator_summary.get("class_memory_summary"):
            _w(f"- Class Memory Summary: {report.operator_summary.get('class_memory_summary')}")
        if report.operator_summary.get("class_decay_summary"):
            _w(f"- Class Decay Summary: {report.operator_summary.get('class_decay_summary')}")
        if report.operator_summary.get("class_reweighting_summary"):
            _w(f"- Class Reweighting Summary: {report.operator_summary.get('class_reweighting_summary')}")
        if report.operator_summary.get("class_momentum_summary"):
            _w(f"- Class Momentum Summary: {report.operator_summary.get('class_momentum_summary')}")
        if report.operator_summary.get("class_reweight_stability_summary"):
            _w(f"- Reweighting Stability Summary: {report.operator_summary.get('class_reweight_stability_summary')}")
        if report.operator_summary.get("class_transition_health_summary"):
            _w(f"- Class Transition Health Summary: {report.operator_summary.get('class_transition_health_summary')}")
        if report.operator_summary.get("class_transition_resolution_summary"):
            _w(f"- Pending Transition Resolution Summary: {report.operator_summary.get('class_transition_resolution_summary')}")
        if report.operator_summary.get("transition_closure_confidence_summary"):
            _w(f"- Transition Closure Confidence Summary: {report.operator_summary.get('transition_closure_confidence_summary')}")
        if report.operator_summary.get("class_pending_debt_summary"):
            _w(f"- Class Pending Debt Summary: {report.operator_summary.get('class_pending_debt_summary')}")
        if report.operator_summary.get("class_pending_resolution_summary"):
            _w(f"- Class Pending Resolution Summary: {report.operator_summary.get('class_pending_resolution_summary')}")
        if report.operator_summary.get("pending_debt_freshness_summary"):
            _w(f"- Pending Debt Freshness Summary: {report.operator_summary.get('pending_debt_freshness_summary')}")
        if report.operator_summary.get("pending_debt_decay_summary"):
            _w(f"- Pending Debt Decay Summary: {report.operator_summary.get('pending_debt_decay_summary')}")
        if report.operator_summary.get("closure_forecast_reweighting_summary"):
            _w(f"- Closure Forecast Reweighting Summary: {report.operator_summary.get('closure_forecast_reweighting_summary')}")
        if report.operator_summary.get("closure_forecast_momentum_summary"):
            _w(f"- Closure Forecast Momentum Summary: {report.operator_summary.get('closure_forecast_momentum_summary')}")
        if report.operator_summary.get("closure_forecast_freshness_summary"):
            _w(f"- Closure Forecast Freshness Summary: {report.operator_summary.get('closure_forecast_freshness_summary')}")
        if report.operator_summary.get("closure_forecast_stability_summary"):
            _w(f"- Closure Forecast Stability Summary: {report.operator_summary.get('closure_forecast_stability_summary')}")
        if report.operator_summary.get("closure_forecast_hysteresis_summary"):
            _w(f"- Closure Forecast Hysteresis Summary: {report.operator_summary.get('closure_forecast_hysteresis_summary')}")
        if report.operator_summary.get("closure_forecast_decay_summary"):
            _w(f"- Closure Forecast Decay Summary: {report.operator_summary.get('closure_forecast_decay_summary')}")
        if report.operator_summary.get("closure_forecast_refresh_recovery_summary"):
            _w(f"- Closure Forecast Refresh Recovery Summary: {report.operator_summary.get('closure_forecast_refresh_recovery_summary')}")
        if report.operator_summary.get("closure_forecast_reacquisition_summary"):
            _w(f"- Closure Forecast Reacquisition Summary: {report.operator_summary.get('closure_forecast_reacquisition_summary')}")
        if report.operator_summary.get("closure_forecast_reacquisition_persistence_summary"):
            _w(f"- Reacquisition Persistence Summary: {report.operator_summary.get('closure_forecast_reacquisition_persistence_summary')}")
        if report.operator_summary.get("closure_forecast_recovery_churn_summary"):
            _w(f"- Recovery Churn Summary: {report.operator_summary.get('closure_forecast_recovery_churn_summary')}")
        if report.operator_summary.get("closure_forecast_reacquisition_freshness_summary"):
            _w(f"- Reacquisition Freshness Summary: {report.operator_summary.get('closure_forecast_reacquisition_freshness_summary')}")
        if report.operator_summary.get("closure_forecast_persistence_reset_summary"):
            _w(f"- Persistence Reset Summary: {report.operator_summary.get('closure_forecast_persistence_reset_summary')}")
        if report.operator_summary.get("closure_forecast_reset_refresh_recovery_summary"):
            _w(f"- Reset Refresh Recovery Summary: {report.operator_summary.get('closure_forecast_reset_refresh_recovery_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_summary"):
            _w(f"- Reset Re-entry Summary: {report.operator_summary.get('closure_forecast_reset_reentry_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_persistence_summary"):
            _w(f"- Reset Re-entry Persistence Summary: {report.operator_summary.get('closure_forecast_reset_reentry_persistence_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_churn_summary"):
            _w(f"- Reset Re-entry Churn Summary: {report.operator_summary.get('closure_forecast_reset_reentry_churn_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_freshness_summary"):
            _w(f"- Reset Re-entry Freshness Summary: {report.operator_summary.get('closure_forecast_reset_reentry_freshness_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_reset_summary"):
            _w(f"- Reset Re-entry Reset Summary: {report.operator_summary.get('closure_forecast_reset_reentry_reset_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_refresh_recovery_summary"):
            _w(f"- Reset Re-entry Refresh Recovery Summary: {report.operator_summary.get('closure_forecast_reset_reentry_refresh_recovery_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_summary"):
            _w(f"- Reset Re-entry Rebuild Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_freshness_summary"):
            _w(f"- Reset Re-entry Rebuild Freshness Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_freshness_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_reset_summary"):
            _w(f"- Reset Re-entry Rebuild Reset Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reset_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_refresh_recovery_summary"):
            _w(f"- Reset Re-entry Rebuild Refresh Recovery Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_refresh_recovery_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_reentry_summary"):
            _w(f"- Reset Re-entry Rebuild Re-entry Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reentry_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_reentry_persistence_summary"):
            _w(f"- Reset Re-entry Rebuild Re-Entry Persistence Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reentry_persistence_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_reentry_churn_summary"):
            _w(f"- Reset Re-entry Rebuild Re-Entry Churn Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reentry_churn_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_reentry_freshness_summary"):
            _w(f"- Reset Re-entry Rebuild Re-Entry Freshness Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reentry_freshness_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_reentry_reset_summary"):
            _w(f"- Reset Re-entry Rebuild Re-Entry Reset Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reentry_reset_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_summary"):
            _w(f"- Reset Re-entry Rebuild Re-Entry Refresh Recovery Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_summary"):
            _w(f"- Reset Re-entry Rebuild Re-Entry Restore Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_summary"):
            _w(f"- Reset Re-entry Rebuild Re-Entry Restore Freshness Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_reset_summary"):
            _w(f"- Reset Re-entry Rebuild Re-Entry Restore Reset Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_reset_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_summary"):
            _w(f"- Reset Re-entry Rebuild Re-Entry Restore Refresh Recovery Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_summary"):
            _w(f"- Reset Re-entry Rebuild Re-Entry Restore Re-Restore Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_summary"):
            _w(f"- Reset Re-entry Rebuild Re-Entry Restore Re-Restore Persistence Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_summary"):
            _w(f"- Reset Re-entry Rebuild Re-Entry Restore Re-Restore Churn Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_summary"):
            _w(f"- Reset Re-entry Rebuild Re-Entry Restore Re-Restore Freshness Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_summary"):
            _w(f"- Reset Re-entry Rebuild Re-Entry Restore Re-Restore Reset Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_summary"):
            _w(f"- Reset Re-entry Rebuild Re-Entry Restore Re-Restore Refresh Recovery Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_summary"):
            _w(f"- Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_summary"):
            _w(f"- Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Persistence Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_summary"):
            _w(f"- Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Churn Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_summary"):
            _w(f"- Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Freshness Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_summary"):
            _w(f"- Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Reset Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_summary"):
            _w(f"- Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Refresh Recovery Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_summary"):
            _w(f"- Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_summary"):
            _w(f"- Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Persistence Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_summary"):
            _w(f"- Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Churn Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_persistence_summary"):
            _w(f"- Reset Re-entry Rebuild Persistence Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_persistence_summary')}")
        if report.operator_summary.get("closure_forecast_reset_reentry_rebuild_churn_summary"):
            _w(f"- Reset Re-entry Rebuild Churn Summary: {report.operator_summary.get('closure_forecast_reset_reentry_rebuild_churn_summary')}")
        if report.operator_summary.get("recommendation_quality_summary"):
            _w(f"- Recommendation Quality: {report.operator_summary.get('recommendation_quality_summary')}")
        if report.operator_summary.get("confidence_validation_status"):
            _w(
                f"- Confidence Validation: {report.operator_summary.get('confidence_validation_status')} "
                f"({report.operator_summary.get('confidence_calibration_summary', 'No confidence-calibration summary is recorded yet.')})"
            )
        if report.operator_summary.get("recent_validation_outcomes"):
            recent_outcomes = []
            for item in (report.operator_summary.get("recent_validation_outcomes") or [])[:3]:
                recent_outcomes.append(
                    f"{item.get('target_label', 'Operator target')} "
                    f"[{item.get('confidence_label', 'low')}] -> {str(item.get('outcome', 'unresolved')).replace('_', ' ')}"
                )
            _w("- Recent Confidence Outcomes: " + "; ".join(recent_outcomes))
        if report.operator_summary.get("control_center_reference"):
            _w(f"- Control Center Artifact: `{report.operator_summary.get('control_center_reference')}`")
        counts = report.operator_summary.get("counts", {})
        _w(
            f"- Blocked: {counts.get('blocked', 0)} | Urgent: {counts.get('urgent', 0)} | "
            f"Ready: {counts.get('ready', 0)} | Deferred: {counts.get('deferred', 0)}"
        )
        if report.operator_queue:
            _w("- Top Attention:")
        for item in report.operator_queue[:6]:
            repo = f"{item.get('repo')}: " if item.get("repo") else ""
            _w(f"- [{item.get('lane_label', item.get('lane', 'ready'))}] {repo}{item.get('title', 'Triage item')}")
            _w(f"  - Why: {item.get('summary', 'No summary available.')}")
            _w(f"  - Lane Reason: {item.get('lane_reason', 'Operator triage')}")
            _w(f"  - Next: {item.get('recommended_action', 'Review the latest state.')}")
            _w(f"  - Last Movement: {build_last_movement_label(item, report.review_summary or {})}")
            _w(
                f"  - Follow-Through: {build_follow_through_status_label(item)} — "
                f"{build_follow_through_summary(item)}"
            )
            _w(f"  - Checkpoint Timing: {build_follow_through_checkpoint_status_label(item)}")
            _w(
                f"  - Escalation: {build_follow_through_escalation_status_label(item)} — "
                f"{build_follow_through_escalation_summary(item)}"
            )
            _w(
                f"  - Recovery / Retirement: {build_follow_through_recovery_status_label(item)} — "
                f"{build_follow_through_recovery_summary(item)}"
            )
            _w(
                f"  - Recovery Persistence: {build_follow_through_recovery_persistence_status_label(item)} — "
                f"{build_follow_through_recovery_persistence_summary(item)}"
            )
            _w(
                f"  - Relapse Churn: {build_follow_through_relapse_churn_status_label(item)} — "
                f"{build_follow_through_relapse_churn_summary(item)}"
            )
            _w(
                f"  - Recovery Freshness: {build_follow_through_recovery_freshness_status_label(item)} — "
                f"{build_follow_through_recovery_freshness_summary(item)}"
            )
            _w(
                f"  - Recovery Memory Reset: {build_follow_through_recovery_memory_reset_status_label(item)} — "
                f"{build_follow_through_recovery_memory_reset_summary(item)}"
            )
            _w(
                f"  - Recovery Rebuild Strength: {build_follow_through_recovery_rebuild_strength_status_label(item)} — "
                f"{build_follow_through_recovery_rebuild_strength_summary(item)}"
            )
            _w(
                f"  - Recovery Reacquisition: {build_follow_through_recovery_reacquisition_status_label(item)} — "
                f"{build_follow_through_recovery_reacquisition_summary(item)}"
            )
            _w(
                f"  - Reacquisition Durability: {build_follow_through_reacquisition_durability_status_label(item)} — "
                f"{build_follow_through_reacquisition_durability_summary(item)}"
            )
            _w(
                f"  - Reacquisition Confidence: {build_follow_through_reacquisition_consolidation_status_label(item)} — "
                f"{build_follow_through_reacquisition_consolidation_summary(item)}"
            )
            _w(
                f"  - Reacquisition Softening Decay: {build_follow_through_reacquisition_softening_decay_status_label(item)} — "
                f"{build_follow_through_reacquisition_softening_decay_summary(item)}"
            )
            _w(
                f"  - Reacquisition Confidence Retirement: {build_follow_through_reacquisition_confidence_retirement_status_label(item)} — "
                f"{build_follow_through_reacquisition_confidence_retirement_summary(item)}"
            )
            _w(
                f"  - Revalidation Recovery: {build_follow_through_reacquisition_revalidation_recovery_status_label(item)} — "
                f"{build_follow_through_reacquisition_revalidation_recovery_summary(item)}"
            )
            _w(f"  - Next Checkpoint: {build_follow_through_checkpoint(item)}")
            links = item.get("links") or []
            artifact = links[0].get("url", "") if links else ""
            _w(f"  - Artifact: {artifact or no_linked_artifact_summary()}")
        recent_changes = report.operator_summary.get("operator_recent_changes", [])
        if recent_changes:
            _w("- Recent Changes:")
            for change in recent_changes[:3]:
                subject = change.get("repo") or change.get("repo_full_name") or change.get("item_id") or "portfolio"
                _w(f"  - {change.get('generated_at', '')[:10]} {subject}: {change.get('summary', change.get('kind', 'change'))}")
        _w("")

    if report.lenses:
        _w("### Decision Lenses")
        _w("")
        _w("| Lens | Avg Score | Leaders | Attention |")
        _w("|------|-----------|---------|-----------|")
        for lens_name, lens_data in report.lenses.items():
            leaders = ", ".join(lens_data.get("leaders", [])) or "—"
            attention = ", ".join(lens_data.get("attention", [])) or "—"
            _w(
                f"| {lens_name.replace('_', ' ').title()} | "
                f"{lens_data.get('average_score', 0):.2f} | "
                f"{leaders} | {attention} |"
            )
        _w("")

    # Tier distribution
    _w("### Tier Distribution")
    _w("")
    _w("| Tier | Count | Percentage |")
    _w("|------|-------|------------|")
    for tier in TIER_ORDER:
        count = report.tier_distribution.get(tier, 0)
        pct = round(count / report.repos_audited * 100) if report.repos_audited else 0
        _w(f"| {tier.capitalize()} | {count} | {pct}% |")
    _w("")

    # Language distribution
    _w("### Language Distribution")
    _w("")
    _w("| Language | Count |")
    _w("|----------|-------|")
    for lang, count in report.language_distribution.items():
        _w(f"| {lang} | {count} |")
    _w("")

    # Highlights
    _w("### Highlights")
    _w("")
    _w("**Top 5 by Score:**")
    _write_ranked_list(lines, report.highest_scored, report.audits)
    _w("")
    _w("**Bottom 5 by Score:**")
    _write_ranked_list(lines, report.lowest_scored, report.audits)
    _w("")
    _w("**Most Active:**")
    _write_ranked_list(lines, report.most_active, report.audits)
    _w("")

    if report.hotspots:
        _w("### Portfolio Hotspots")
        _w("")
        _w("| Repo | Category | Severity | Recommended Action |")
        _w("|------|----------|----------|--------------------|")
        for hotspot in report.hotspots[:8]:
            _w(
                f"| {hotspot.get('repo', '—')} | {hotspot.get('category', '—')} | "
                f"{hotspot.get('severity', 0):.2f} | {hotspot.get('recommended_action', '—')} |"
            )
        _w("")

    if report.security_posture:
        _w("### Security Overview")
        _w("")
        provider_coverage = report.security_posture.get("provider_coverage", {})
        open_alerts = report.security_posture.get("open_alerts", {})
        _w(f"- Average posture score: {report.security_posture.get('average_score', 0):.2f}")
        _w(f"- Critical repos: {', '.join(report.security_posture.get('critical_repos', [])[:5]) or '—'}")
        _w(f"- Repos with secrets: {', '.join(report.security_posture.get('repos_with_secrets', [])[:5]) or '—'}")
        if provider_coverage:
            _w(
                f"- GitHub coverage: {provider_coverage.get('github', {}).get('available_repos', 0)}/"
                f"{provider_coverage.get('github', {}).get('total_repos', 0)} repos | "
                f"Scorecard coverage: {provider_coverage.get('scorecard', {}).get('available_repos', 0)}/"
                f"{provider_coverage.get('scorecard', {}).get('total_repos', 0)} repos"
            )
        if open_alerts:
            _w(
                f"- Open alerts: code scanning {open_alerts.get('code_scanning', 0)}, "
                f"secret scanning {open_alerts.get('secret_scanning', 0)}"
            )
        _w("")

    if report.campaign_summary:
        github_projects = report.writeback_preview.get("github_projects", {}) if isinstance(report.writeback_preview, dict) else {}
        _w("### Campaign Summary")
        _w("")
        _w(f"- Campaign: {report.campaign_summary.get('label', report.campaign_summary.get('campaign_type', '—'))}")
        _w(f"- Actions: {report.campaign_summary.get('action_count', 0)}")
        _w(f"- Repos: {report.campaign_summary.get('repo_count', 0)}")
        _w(f"- Mode: {report.writeback_results.get('mode', 'preview')}")
        _w(f"- Target: {report.writeback_results.get('target', 'preview-only')}")
        _w(f"- Sync Mode: {report.writeback_preview.get('sync_mode', 'reconcile')}")
        if github_projects.get("enabled"):
            _w(
                f"- GitHub Projects: {github_projects.get('status', 'disabled')} "
                f"({github_projects.get('project_owner', '—')} #{github_projects.get('project_number', 0)}, "
                f"{github_projects.get('item_count', 0)} items)"
            )
        _w("")

    if report.writeback_preview.get("repos"):
        _w("### Next Actions")
        _w("")
        _w("| Repo | Topics | Issue | GitHub Projects | Notion Actions |")
        _w("|------|--------|-------|-----------------|----------------|")
        for item in report.writeback_preview.get("repos", [])[:8]:
            topics = ", ".join(item.get("topics", [])[:4]) or "—"
            project_status = (
                f"{item.get('github_project_field_count', 0)} field(s)"
                if item.get("github_project_field_count")
                else "—"
            )
            _w(
                f"| {item.get('repo', '—')} | {topics} | "
                f"{item.get('issue_title', '—') or '—'} | {project_status} | {item.get('notion_action_count', 0)} |"
            )
        _w("")

    if report.writeback_results.get("results"):
        _w("### Writeback Results")
        _w("")
        _w("| Repo | Target | Status | Details |")
        _w("|------|--------|--------|---------|")
        for result in report.writeback_results.get("results", [])[:12]:
            detail = result.get("url") or result.get("status") or "—"
            _w(
                f"| {result.get('repo_full_name', '—')} | {result.get('target', '—')} | "
                f"{result.get('status', '—')} | {detail} |"
            )
        _w("")
    if report.managed_state_drift:
        _w("### Managed State Drift")
        _w("")
        _w("| Repo | Target | Drift | Details |")
        _w("|------|--------|-------|---------|")
        for item in report.managed_state_drift[:12]:
            _w(
                f"| {item.get('repo_full_name', '—')} | {item.get('target', '—')} | "
                f"{item.get('drift_state', '—')} | {json.dumps(item)} |"
            )
        _w("")

    if report.rollback_preview.get("items") or report.rollback_preview.get("item_count", 0):
        _w("### Rollback Preview")
        _w("")
        _w(f"- Available: {'yes' if report.rollback_preview.get('available') else 'no'}")
        _w(f"- Items: {report.rollback_preview.get('item_count', 0)}")
        _w(f"- Fully reversible: {report.rollback_preview.get('fully_reversible_count', 0)}")
        _w("")

    if report.security_governance_preview:
        _w("### Security Governance Preview")
        _w("")
        _w("| Repo | Priority | Action | Expected Lift | Source |")
        _w("|------|----------|--------|---------------|--------|")
        for item in report.security_governance_preview[:8]:
            _w(
                f"| {item.get('repo', '—')} | {item.get('priority', '—')} | "
                f"{item.get('title', '—')} | {item.get('expected_posture_lift', 0):.2f} | "
                f"{item.get('source', '—')} |"
            )
        _w("")

    governance_summary = report.governance_summary or {}
    if governance_summary or report.governance_results.get("results") or report.governance_drift:
        _w("### Governance Operator State")
        _w("")
        _w(f"- Headline: {governance_summary.get('headline', 'Governance state is being tracked.')}")
        _w(f"- Status: {governance_summary.get('status', 'preview')}")
        _w(f"- Approved: {'yes' if report.governance_approval else 'no'}")
        _w(f"- Needs Re-Approval: {'yes' if governance_summary.get('needs_reapproval') else 'no'}")
        _w(f"- Drift Count: {governance_summary.get('drift_count', len(report.governance_drift))}")
        _w(f"- Applyable Count: {governance_summary.get('applyable_count', report.governance_preview.get('applyable_count', 0) if isinstance(report.governance_preview, dict) else 0)}")
        _w(f"- Applied Count: {governance_summary.get('applied_count', len(report.governance_results.get('results', [])))}")
        _w(f"- Rollback Available: {governance_summary.get('rollback_available_count', 0)}")
        if governance_summary.get("approval_age_days") is not None:
            _w(f"- Approval Age (days): {governance_summary.get('approval_age_days')}")
        for item in governance_summary.get("top_actions", [])[:4]:
            _w(
                f"- {item.get('repo', '—')}: {item.get('title', 'Governed control')} "
                f"[{item.get('operator_state', 'preview')}]"
            )
        _w("")

    if report.collections:
        _w("### Collections")
        _w("")
        _w("| Collection | Count | Example Repos |")
        _w("|------------|-------|--------------|")
        for collection_name, collection_data in report.collections.items():
            repo_names = [
                repo_data["name"] if isinstance(repo_data, dict) else str(repo_data)
                for repo_data in collection_data.get("repos", [])[:4]
            ]
            _w(f"| {collection_name} | {len(collection_data.get('repos', []))} | {', '.join(repo_names) or '—'} |")
        _w("")

    preview = report.scenario_summary.get("portfolio_projection", {})
    if report.scenario_summary.get("top_levers"):
        _w("### Scenario Preview")
        _w("")
        _w("| Lever | Lens | Repo Count | Avg Lift | Promotions |")
        _w("|-------|------|------------|----------|------------|")
        for lever in report.scenario_summary.get("top_levers", [])[:5]:
            _w(
                f"| {lever.get('title', '—')} | {lever.get('lens', '—')} | "
                f"{lever.get('repo_count', 0)} | {lever.get('average_expected_lens_delta', 0):.3f} | "
                f"{lever.get('projected_tier_promotions', 0)} |"
            )
        if preview:
            _w("")
            _w(
                f"*Projected average score delta:* {preview.get('projected_average_score_delta', 0):+.3f}  "
                f"*Projected promotions:* {preview.get('projected_tier_promotions', 0)}"
            )
        _w("")

    if diff_data:
        _w("### Compare Summary")
        _w("")
        _w(f"*Average score delta:* {diff_data.get('average_score_delta', 0):+.3f}")
        _w("")
        if diff_data.get("lens_deltas"):
            _w("| Lens | Delta |")
            _w("|------|-------|")
            for lens_name, delta in diff_data.get("lens_deltas", {}).items():
                _w(f"| {lens_name} | {delta:+.3f} |")
            _w("")
        repo_changes = diff_data.get("repo_changes", [])
        if repo_changes:
            _w("| Repo | Score Delta | Tier |")
            _w("|------|-------------|------|")
            for change in repo_changes[:8]:
                _w(
                    f"| {change.get('name', '—')} | {change.get('delta', 0):+.3f} | "
                    f"{change.get('old_tier', '—')} → {change.get('new_tier', '—')} |"
                )
            _w("")

    _w("---")
    _w("")

    # Tier-grouped tables
    audits_by_tier = _group_by_tier(report.audits)
    for tier in TIER_ORDER:
        tier_audits = audits_by_tier.get(tier, [])
        if not tier_audits:
            continue
        _w(f"## {tier.capitalize()} ({len(tier_audits)} repos)")
        _w("")
        _w("| Repo | Grade | Score | Interest | Badges | Language | Description |")
        _w("|------|-------|-------|----------|--------|----------|-------------|")
        for audit in tier_audits:
            m = audit.metadata
            name_link = f"[{m.name}]({m.html_url})"
            badges_str = " ".join(f"`{b}`" for b in audit.badges[:3]) if audit.badges else "—"
            desc = _truncate(m.description)
            lang = m.language or "—"
            _w(f"| {name_link} | {audit.grade} | {audit.overall_score:.2f} | {audit.interest_score:.2f} | {badges_str} | {lang} | {desc} |")
        _w("")

    # Quick Wins section
    from src.quick_wins import find_quick_wins
    quick_wins = find_quick_wins(report.audits)
    if quick_wins:
        _w("---")
        _w("")
        _w(f"## Quick Wins ({len(quick_wins)} repos near next tier)")
        _w("")
        _w("| Repo | Current | Score | Next Tier | Gap | Top Action |")
        _w("|------|---------|-------|-----------|-----|------------|")
        for win in quick_wins:
            action = win["actions"][0] if win["actions"] else "—"
            _w(f"| {win['name']} | {win['current_tier']} | {win['score']:.2f} | "
               f"{win['next_tier']} | {win['gap']:.3f} | {action} |")
        _w("")

    # Per-repo details
    _w("---")
    _w("")
    _w("## Per-Repo Details")
    _w("")

    sorted_audits = sorted(report.audits, key=lambda a: a.overall_score, reverse=True)
    for audit in sorted_audits:
        m = audit.metadata
        briefing = build_repo_briefing(audit.to_dict(), report_dict, diff_data)
        _w("<details>")
        _w(f"<summary>{briefing.get('headline', f'{m.name} — {audit.overall_score:.2f} ({audit.completeness_tier})')}</summary>")
        _w("")
        _w("**Current State**")
        _w(f"- {briefing.get('current_state_line', 'No current-state summary is recorded yet.')}")
        _w(f"- URL: {m.html_url}")
        _w(f"- Description: {briefing.get('current_state', {}).get('description', m.description or 'No description recorded yet.')}")
        _w("")
        _w("**What Changed**")
        _w(f"- {briefing.get('what_changed', {}).get('last_movement', 'No change timing is recorded yet.')}")
        _w(f"- {briefing.get('what_changed', {}).get('recent_change_summary', 'No recent change summary is recorded yet.')}")
        _w(f"- Hotspot context: {briefing.get('what_changed', {}).get('top_hotspot_context', 'No hotspot context is recorded yet.')}")
        _w("")
        _w("**Why It Matters**")
        _w(f"- Strongest drivers: {briefing.get('why_this_repo_looks_this_way', {}).get('strongest_drivers', 'No strong positive drivers recorded yet.')}")
        _w(f"- Biggest drags: {briefing.get('why_this_repo_looks_this_way', {}).get('biggest_drags', 'No major drag factors recorded yet.')}")
        _w(f"- Next tier gap: {briefing.get('why_this_repo_looks_this_way', {}).get('next_tier_gap', 'No next-tier gap is recorded yet.')}")
        _w("")
        _w("**Where To Start**")
        _w(f"- {briefing.get('where_to_start_summary', 'No meaningful implementation hotspot is currently surfaced.')}")
        for hotspot in briefing.get("implementation_hotspots", [])[:3]:
            _w(f"- {_truncate(hotspot.get('path', 'repo root'), 80)}: {hotspot.get('signal_summary', 'No signal summary recorded yet.')}")
        _w("")
        _w("**What To Do Next**")
        _w(f"- Next best action: {briefing.get('what_to_do_next', {}).get('next_best_action', 'No clear next action is recorded yet.')}")
        _w(f"- Rationale: {briefing.get('what_to_do_next', {}).get('rationale', 'No action rationale is recorded yet.')}")
        if briefing.get("what_to_do_next", {}).get("top_action_candidates"):
            _w(f"- Other good candidates: {', '.join(briefing.get('what_to_do_next', {}).get('top_action_candidates', [])[:3])}")
        _w("")
        _w("| Dimension | Score | Key Findings |")
        _w("|-----------|-------|-------------|")
        for r in audit.analyzer_results:
            findings = ", ".join(r.findings[:2]) if r.findings else "—"
            _w(f"| {r.dimension} | {r.score:.2f} | {findings} |")
        _w("")
        _w(f"**Language:** {m.language or '—'} | "
           f"**Size:** {m.size_kb} KB | "
           f"**Stars:** {m.stars} | "
           f"**Private:** {'Yes' if m.private else 'No'}")
        if audit.lenses:
            _w("")
            _w("**Decision Lenses:**")
            for lens_name, lens_data in audit.lenses.items():
                _w(
                    f"- {lens_name.replace('_', ' ').title()}: "
                    f"{lens_data.get('score', 0):.2f} — {lens_data.get('summary', '')}"
                )
        if audit.action_candidates:
            _w("")
            _w("**Top Actions:**")
            for action in audit.action_candidates[:3]:
                _w(
                    f"- {action.get('title', 'Action')}: {action.get('action', '')} "
                    f"(lens: {action.get('lens', '—')}, confidence: {action.get('confidence', 0):.2f})"
                )
        if audit.score_explanation:
            _w("")
            _w("**Repo Briefing Summary:**")
            _w(f"- What Changed: {briefing.get('what_changed_line', 'No change summary is recorded yet.')}")
            _w(f"- Why It Matters: {briefing.get('why_it_matters_line', 'No explanation summary is recorded yet.')}")
            _w(f"- Where To Start: {briefing.get('where_to_start_summary', 'No meaningful implementation hotspot is currently surfaced.')}")
            _w(f"- What To Do Next: {briefing.get('what_to_do_next_line', 'No next action is recorded yet.')}")
            _w(f"- Follow-Through: {briefing.get('follow_through_line', 'No follow-through evidence is recorded yet.')}")
            _w(f"- Catalog: {briefing.get('catalog_line', 'No portfolio catalog contract is recorded yet.')}")
            _w(f"- Intent Alignment: {briefing.get('intent_alignment_line', 'missing-contract: Intent alignment cannot be judged until a portfolio catalog contract exists.')}")
            _w(f"- Checkpoint Timing: {briefing.get('checkpoint_timing_line', 'Unknown')}")
            _w(f"- Escalation: {briefing.get('escalation_line', 'Unknown: No stronger follow-through escalation is currently surfaced.')}")
            _w(f"- What Would Count As Progress: {briefing.get('checkpoint_line', 'Use the next run or linked artifact to confirm whether the recommendation moved.')}")
        if audit.security_posture:
            _w("")
            _w("**Security Posture:**")
            _w(
                f"- Label: {audit.security_posture.get('label', 'unknown')} | "
                f"Score: {audit.security_posture.get('score', 0):.2f} | "
                f"Secrets: {audit.security_posture.get('secrets_found', 0)}"
            )
            github = audit.security_posture.get("github", {})
            if github:
                _w(
                    f"- GitHub controls: code scanning {github.get('code_scanning_status', 'unavailable')}, "
                    f"secret scanning {github.get('secret_scanning_status', 'unavailable')}, "
                    f"SBOM {github.get('sbom_status', 'unavailable')}"
                )
            recommendations = audit.security_posture.get("recommendations", [])
            if recommendations:
                _w("- Governance preview:")
                for recommendation in recommendations[:3]:
                    _w(
                        f"  - {recommendation.get('title', 'Action')} "
                        f"({recommendation.get('priority', 'medium')}, "
                        f"lift {recommendation.get('expected_posture_lift', 0):.2f})"
                    )
        _w("")
        _w("</details>")
        _w("")

    # Registry reconciliation (only when --registry was used)
    if report.reconciliation:
        _write_reconciliation_section(lines, report)

    content = "\n".join(lines)
    with open(path, "w") as f:
        f.write(content)

    return path


# ── Helpers ──────────────────────────────────────────────────────────


def _write_ranked_list(
    lines: list[str],
    names: list[str],
    audits: list[RepoAudit],
) -> None:
    """Write a numbered list of repo names with their scores."""
    audit_map = {a.metadata.name: a for a in audits}
    for i, name in enumerate(names, 1):
        audit = audit_map.get(name)
        if audit:
            lines.append(
                f"{i}. {name} — {audit.overall_score:.2f} ({audit.completeness_tier})"
            )


def _group_by_tier(audits: list[RepoAudit]) -> dict[str, list[RepoAudit]]:
    """Group audits by tier, sorted by score descending within each tier."""
    groups: dict[str, list[RepoAudit]] = {}
    for audit in audits:
        tier = audit.completeness_tier
        groups.setdefault(tier, []).append(audit)
    for tier_audits in groups.values():
        tier_audits.sort(key=lambda a: a.overall_score, reverse=True)
    return groups


def _write_reconciliation_section(lines: list[str], report: AuditReport) -> None:
    """Write the registry reconciliation section to Markdown."""
    _w = lines.append
    recon = report.reconciliation
    audit_map = {a.metadata.name: a for a in report.audits}

    _w("---")
    _w("")
    _w("## Registry Reconciliation")
    _w("")
    _w(f"*Registry: {recon.registry_total} projects | "
       f"GitHub: {recon.github_total} repos | "
       f"Matched: {len(recon.matched)}*")
    _w("")

    # On GitHub but not in registry
    if recon.on_github_not_registry:
        _w(f"### On GitHub but NOT in Registry ({len(recon.on_github_not_registry)} repos)")
        _w("")
        _w("| Repo | Tier | Score | Language |")
        _w("|------|------|-------|----------|")
        for name in recon.on_github_not_registry:
            audit = audit_map.get(name)
            if audit:
                _w(f"| {name} | {audit.completeness_tier} | "
                   f"{audit.overall_score:.2f} | {audit.metadata.language or '—'} |")
        _w("")

    # In registry but not on GitHub
    if recon.in_registry_not_github:
        _w(f"### In Registry but NOT on GitHub ({len(recon.in_registry_not_github)} projects)")
        _w("")
        _w("| Project | Registry Status |")
        _w("|---------|----------------|")
        for name in recon.in_registry_not_github:
            _w(f"| {name} | — |")
        _w("")

    # Matched projects
    if recon.matched:
        _w(f"### Matched Projects ({len(recon.matched)})")
        _w("")
        _w("| Project | Registry Status | Audit Tier | Score |")
        _w("|---------|----------------|------------|-------|")
        for m in recon.matched:
            _w(f"| {m['github_name']} | {m['registry_status']} | "
               f"{m['audit_tier']} | {m['score']:.2f} |")
        _w("")

    # Status alignment cross-tab
    if recon.matched:
        _w("### Status Alignment")
        _w("")
        _w("| Registry Status | Shipped | Functional | WIP | Skeleton | Abandoned |")
        _w("|----------------|---------|------------|-----|----------|-----------|")

        for reg_status in ("active", "recent", "parked", "archived"):
            counts = {t: 0 for t in TIER_ORDER}
            for m in recon.matched:
                if m["registry_status"] == reg_status:
                    counts[m["audit_tier"]] = counts.get(m["audit_tier"], 0) + 1
            _w(f"| {reg_status} | {counts.get('shipped', 0)} | "
               f"{counts.get('functional', 0)} | {counts.get('wip', 0)} | "
               f"{counts.get('skeleton', 0)} | {counts.get('abandoned', 0)} |")
        _w("")
