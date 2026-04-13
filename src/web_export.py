"""Self-contained HTML dashboard generator.

Produces a single .html file with embedded CSS, JS, and data.
No external dependencies — works offline, shareable as one file.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from urllib.parse import urlparse

from src.analyst_views import build_analyst_context
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
    build_operator_focus_line,
    build_queue_pressure_summary,
    build_repo_briefing,
    build_run_change_counts,
    build_run_change_summary,
    build_score_explanation,
    build_top_recommendation_summary,
    build_trust_actionability_summary,
    build_weekly_review_pack,
    no_baseline_summary,
    no_linked_artifact_summary,
)
from src.sparkline import sparkline as render_sparkline

# ── Color constants (matching Excel design system) ──────────────────

TIER_COLORS_CSS = {
    "shipped": "#166534",
    "functional": "#1565C0",
    "wip": "#D97706",
    "skeleton": "#C2410C",
    "abandoned": "#6B7280",
}

GRADE_COLORS_CSS = {
    "A": "#166534",
    "B": "#15803D",
    "C": "#CA8A04",
    "D": "#C2410C",
    "F": "#991B1B",
}

RADAR_COLORS = {
    "Adopt": "#166534",
    "Trial": "#1565C0",
    "Hold": "#6B7280",
    "Decline": "#991B1B",
}


# ── Public API ────────────────────────────────────────────────────────
def export_html_dashboard(
    report_data: dict,
    output_dir: Path,
    trend_data: list[dict] | None = None,
    score_history: dict[str, list[float]] | None = None,
    diff_data: dict | None = None,
    portfolio_profile: str = "default",
    collection: str | None = None,
) -> dict:
    """Generate interactive HTML dashboard. Returns {html_path}."""
    html = _render_html(
        report_data,
        trend_data,
        score_history,
        diff_data=diff_data,
        portfolio_profile=portfolio_profile,
        collection=collection,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    date = report_data.get("generated_at", "")[:10] or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    username = report_data.get("username", "unknown")
    html_path = output_dir / f"dashboard-{username}-{date}.html"
    html_path.write_text(html)
    return {"html_path": html_path}


# ── HTML rendering ────────────────────────────────────────────────────
def _render_html(
    report_data: dict,
    trend_data: list[dict] | None = None,
    score_history: dict[str, list[float]] | None = None,
    diff_data: dict | None = None,
    portfolio_profile: str = "default",
    collection: str | None = None,
) -> str:
    """Build the complete HTML string."""
    username = report_data.get("username", "unknown")
    date = report_data.get("generated_at", "")[:10]
    repos_audited = report_data.get("repos_audited", 0)
    grade = report_data.get("portfolio_grade", "F")
    analyst_context = build_analyst_context(
        report_data,
        profile_name=portfolio_profile,
        collection_name=collection,
    )
    collection_names = sorted(report_data.get("collections", {}).keys())

    # Prepare minimal data payload for JS
    js_data = {
        "username": username,
        "date": date,
        "grade": grade,
        "average_score": report_data.get("average_score", 0),
        "repos_audited": repos_audited,
        "tier_distribution": report_data.get("tier_distribution", {}),
        "selected_profile": analyst_context["profile_name"],
        "selected_collection": analyst_context["collection_name"],
        "profile_leaders": analyst_context["profile_leaderboard"].get("leaders", []),
        "collection_names": collection_names,
        "audits": [
            {
                "name": entry["name"],
                "grade": a.get("grade", "F"),
                "score": round(a.get("overall_score", 0), 3),
                "interest": round(a.get("interest_score", 0), 3),
                "tier": a.get("completeness_tier", ""),
                "language": a.get("metadata", {}).get("language") or "",
                "description": (a.get("metadata", {}).get("description") or "")[:80],
                "url": a.get("metadata", {}).get("html_url", ""),
                "badges": len(a.get("badges", [])),
                "profile_score": round(entry["profile_score"], 3),
                "collections": entry["collections"],
                "security_label": entry["security_label"],
                "hotspot_count": entry["hotspot_count"],
            }
            for entry in analyst_context["ranked_audits"]
            for a in [entry["audit"]]
        ],
    }

    parts = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head>",
        "<meta charset='utf-8'>",
        f"<title>Portfolio Dashboard: {escape(username)}</title>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        f"<style>{_css()}</style>",
        "</head>",
        "<body>",
        _header_section(username, date, repos_audited, grade),
        _kpi_section(report_data),
        _preflight_section(report_data),
        _operator_section(report_data),
        _weekly_review_pack_section(report_data, diff_data),
        _top_attention_section(report_data),
        _analyst_summary_section(analyst_context),
        _lens_summary_section(report_data),
        _security_overview_section(report_data),
        '<div class="section"><h2>Completeness vs Interest</h2>',
        '<canvas id="scatter" width="800" height="500"></canvas>',
        '<div id="tooltip" class="tooltip"></div>',
        '</div>',
        _repo_table(analyst_context, score_history),
        _repo_drilldown_section(report_data, diff_data),
        _portfolio_trends_section(trend_data or []),
        _run_changes_section(report_data, diff_data),
        _compare_section(diff_data),
        _scenario_section(analyst_context),
        _governance_section(report_data),
        _campaign_section(report_data),
        _writeback_results_section(report_data),
        _tech_radar_section(report_data, trend_data),
        _distribution_section(report_data),
        _footer(),
        f'<script id="dashboard-data" type="application/json">{_json_script_data(js_data)}</script>',
        f"<script>{_js()}</script>",
        "</body>",
        "</html>",
    ]
    return "\n".join(parts)


# ── KPI and header sections ───────────────────────────────────────────
def _header_section(username: str, date: str, repos: int, grade: str) -> str:
    color = GRADE_COLORS_CSS.get(grade, "#6B7280")
    return f"""
    <header>
      <h1>Portfolio Dashboard: {escape(username)}</h1>
      <p>Generated {escape(date)} | {repos} repos audited | Grade <span style="color:{color};font-weight:bold">{escape(grade)}</span></p>
    </header>"""


def _kpi_section(data: dict) -> str:
    tiers = data.get("tier_distribution", {})
    avg = data.get("average_score", 0)
    shipped = tiers.get("shipped", 0)
    functional = tiers.get("functional", 0)
    needs_work = tiers.get("skeleton", 0) + tiers.get("abandoned", 0)
    return f"""
    <div class="kpi-row">
      <div class="kpi-card"><div class="kpi-label">Avg Score</div><div class="kpi-value">{avg:.2f}</div></div>
      <div class="kpi-card"><div class="kpi-label">Shipped</div><div class="kpi-value" style="color:#166534">{shipped}</div></div>
      <div class="kpi-card"><div class="kpi-label">Functional</div><div class="kpi-value" style="color:#1565C0">{functional}</div></div>
      <div class="kpi-card"><div class="kpi-label">Needs Work</div><div class="kpi-value" style="color:#C2410C">{needs_work}</div></div>
    </div>"""


def _preflight_section(data: dict) -> str:
    summary = data.get("preflight_summary") or {}
    warnings = summary.get("warnings", 0)
    errors = summary.get("blocking_errors", 0)
    if not summary or (warnings == 0 and errors == 0):
        return ""
    rows = []
    for check in (summary.get("checks") or [])[:6]:
        rows.append(
            f"<li><strong>{escape(check.get('category', 'setup'))}</strong>: "
            f"{escape(check.get('summary', 'Issue detected'))}</li>"
        )
    return f"""
    <div class="section">
      <h2>Preflight Diagnostics</h2>
      <div class="panel">
        <div class="meta-line"><strong>Status:</strong> {escape(summary.get('status', 'unknown'))}</div>
        <div class="meta-line"><strong>Errors:</strong> {errors} | <strong>Warnings:</strong> {warnings}</div>
        <ul class="bullet-list">{''.join(rows)}</ul>
      </div>
    </div>"""


def _operator_section(data: dict) -> str:
    summary = data.get("operator_summary") or {}
    queue = data.get("operator_queue") or []
    if not summary and not queue:
        return ""
    queue_pressure_summary = build_queue_pressure_summary(data)
    top_recommendation_summary = build_top_recommendation_summary(data)
    trust_actionability_summary = build_trust_actionability_summary(data)
    run_change_summary = data.get("run_change_summary") or build_run_change_summary(None)
    counts = summary.get("counts", {})
    rows = []
    for item in queue[:8]:
        repo = f"{escape(item.get('repo', ''))}: " if item.get("repo") else ""
        links = item.get("links") or []
        artifact = links[0].get("url", "") if links else ""
        artifact_label = artifact or no_linked_artifact_summary()
        last_movement = build_last_movement_label(item, data.get("review_summary") or {})
        rows.append(
            "<li>"
            f"<strong>[{escape(item.get('lane_label', item.get('lane', 'ready')))}]</strong> {repo}{escape(item.get('title', 'Triage item'))}"
            f"<br><span class='muted'>{escape(item.get('summary', 'No summary available.'))}</span>"
            f"<br><span class='muted'><strong>Why this lane:</strong> {escape(item.get('lane_reason', 'Operator triage item.'))}</span>"
            f"<br><span class='muted'><strong>Next:</strong> {escape(item.get('recommended_action', 'Review the latest state.'))}</span>"
            f"<br><span class='muted'><strong>Last movement:</strong> {escape(last_movement)}</span>"
            f"<br><span class='muted'><strong>Follow-through:</strong> {escape(build_follow_through_status_label(item))} — {escape(build_follow_through_summary(item))}</span>"
            f"<br><span class='muted'><strong>Checkpoint timing:</strong> {escape(build_follow_through_checkpoint_status_label(item))}</span>"
            f"<br><span class='muted'><strong>Escalation:</strong> {escape(build_follow_through_escalation_status_label(item))} — {escape(build_follow_through_escalation_summary(item))}</span>"
            f"<br><span class='muted'><strong>Recovery / Retirement:</strong> {escape(build_follow_through_recovery_status_label(item))} — {escape(build_follow_through_recovery_summary(item))}</span>"
            f"<br><span class='muted'><strong>Recovery Persistence:</strong> {escape(build_follow_through_recovery_persistence_status_label(item))} — {escape(build_follow_through_recovery_persistence_summary(item))}</span>"
            f"<br><span class='muted'><strong>Relapse Churn:</strong> {escape(build_follow_through_relapse_churn_status_label(item))} — {escape(build_follow_through_relapse_churn_summary(item))}</span>"
            f"<br><span class='muted'><strong>Recovery Freshness:</strong> {escape(build_follow_through_recovery_freshness_status_label(item))} — {escape(build_follow_through_recovery_freshness_summary(item))}</span>"
            f"<br><span class='muted'><strong>Recovery Memory Reset:</strong> {escape(build_follow_through_recovery_memory_reset_status_label(item))} — {escape(build_follow_through_recovery_memory_reset_summary(item))}</span>"
            f"<br><span class='muted'><strong>Recovery Rebuild Strength:</strong> {escape(build_follow_through_recovery_rebuild_strength_status_label(item))} — {escape(build_follow_through_recovery_rebuild_strength_summary(item))}</span>"
            f"<br><span class='muted'><strong>Recovery Reacquisition:</strong> {escape(build_follow_through_recovery_reacquisition_status_label(item))} — {escape(build_follow_through_recovery_reacquisition_summary(item))}</span>"
            f"<br><span class='muted'><strong>Reacquisition Durability:</strong> {escape(build_follow_through_reacquisition_durability_status_label(item))} — {escape(build_follow_through_reacquisition_durability_summary(item))}</span>"
            f"<br><span class='muted'><strong>Reacquisition Confidence:</strong> {escape(build_follow_through_reacquisition_consolidation_status_label(item))} — {escape(build_follow_through_reacquisition_consolidation_summary(item))}</span>"
            f"<br><span class='muted'><strong>Reacquisition Softening Decay:</strong> {escape(build_follow_through_reacquisition_softening_decay_status_label(item))} — {escape(build_follow_through_reacquisition_softening_decay_summary(item))}</span>"
            f"<br><span class='muted'><strong>Reacquisition Confidence Retirement:</strong> {escape(build_follow_through_reacquisition_confidence_retirement_status_label(item))} — {escape(build_follow_through_reacquisition_confidence_retirement_summary(item))}</span>"
            f"<br><span class='muted'><strong>Revalidation Recovery:</strong> {escape(build_follow_through_reacquisition_revalidation_recovery_status_label(item))} — {escape(build_follow_through_reacquisition_revalidation_recovery_summary(item))}</span>"
            f"<br><span class='muted'><strong>Next checkpoint:</strong> {escape(build_follow_through_checkpoint(item))}</span>"
            f"<br><span class='muted'><strong>Artifact:</strong> {escape(artifact_label)}</span>"
            "</li>"
        )
    recent_changes = summary.get("operator_recent_changes", [])
    primary_target = summary.get("primary_target") or {}
    primary_target_label = (
        f"{primary_target.get('repo')}: {primary_target.get('title')}"
        if primary_target.get("repo")
        else primary_target.get("title", "")
    )
    recent_markup = "".join(
        f"<li>{escape(change.get('generated_at', '')[:10])} "
        f"{escape(change.get('repo') or change.get('repo_full_name') or change.get('item_id') or 'portfolio')}: "
        f"{escape(change.get('summary', change.get('kind', 'change')))}</li>"
        for change in recent_changes[:4]
    )
    intervention_label = _intervention_label(summary.get("primary_target_last_intervention") or {})
    return f"""
    <div class="section">
      <h2>Operator Control Center</h2>
      <div class="panel">
        <div class="meta-line"><strong>Headline:</strong> {escape(summary.get('headline', 'No operator triage items are currently surfaced.'))}</div>
        <div class="meta-line"><strong>Run Changes:</strong> {escape(run_change_summary)}</div>
        <div class="meta-line"><strong>Queue Pressure:</strong> {escape(queue_pressure_summary)}</div>
        <div class="meta-line"><strong>Trust / Actionability:</strong> {escape(trust_actionability_summary)}</div>
        <div class="meta-line"><strong>Top Recommendation:</strong> {escape(top_recommendation_summary)}</div>
        <div class="meta-line"><strong>Source Run:</strong> {escape(summary.get('source_run_id', 'n/a'))}</div>
        <div class="meta-line"><strong>Next Recommended Run:</strong> {escape(summary.get('next_recommended_run_mode', 'n/a'))}</div>
        <div class="meta-line"><strong>Watch Strategy:</strong> {escape(summary.get('watch_strategy', 'manual'))}</div>
        <div class="meta-line"><strong>Watch Decision:</strong> {escape(summary.get('watch_decision_summary', 'No watch guidance is recorded.'))}</div>
        <div class="meta-line"><strong>What Changed:</strong> {escape(summary.get('what_changed', 'No operator change summary is recorded.'))}</div>
        <div class="meta-line"><strong>Why It Matters:</strong> {escape(summary.get('why_it_matters', 'No additional operator impact is recorded.'))}</div>
        <div class="meta-line"><strong>What To Do Next:</strong> {escape(summary.get('what_to_do_next', 'Continue the normal operator loop.'))}</div>
        <div class="meta-line"><strong>Trend:</strong> {escape(summary.get('trend_summary', 'No trend summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Accountability:</strong> {escape(summary.get('accountability_summary', 'No accountability summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Follow-Through:</strong> {escape(summary.get('follow_through_summary', 'No follow-through signal is recorded yet.'))}</div>
        <div class="meta-line"><strong>Next Checkpoint:</strong> {escape(summary.get('follow_through_checkpoint_summary', 'Use the next run or linked artifact to confirm whether the recommendation moved.'))}</div>
        <div class="meta-line"><strong>Escalation:</strong> {escape(summary.get('follow_through_escalation_summary', 'No stronger follow-through escalation is currently surfaced.'))}</div>
        <div class="meta-line"><strong>Recovery / Retirement:</strong> {escape(summary.get('follow_through_recovery_summary', 'No follow-through recovery or escalation-retirement signal is currently surfaced.'))}</div>
        <div class="meta-line"><strong>Recovery Persistence:</strong> {escape(summary.get('follow_through_recovery_persistence_summary', 'No follow-through recovery persistence signal is currently surfaced.'))}</div>
        <div class="meta-line"><strong>Relapse Churn:</strong> {escape(summary.get('follow_through_relapse_churn_summary', 'No relapse churn is currently surfaced.'))}</div>
        <div class="meta-line"><strong>Recovery Freshness:</strong> {escape(summary.get('follow_through_recovery_freshness_summary', 'No follow-through recovery freshness signal is currently surfaced.'))}</div>
        <div class="meta-line"><strong>Recovery Memory Reset:</strong> {escape(summary.get('follow_through_recovery_memory_reset_summary', 'No follow-through recovery memory reset signal is currently surfaced.'))}</div>
        <div class="meta-line"><strong>Recovery Rebuild Strength:</strong> {escape(summary.get('follow_through_recovery_rebuild_strength_summary', 'No follow-through recovery rebuild-strength signal is currently surfaced.'))}</div>
        <div class="meta-line"><strong>Recovery Reacquisition:</strong> {escape(summary.get('follow_through_recovery_reacquisition_summary', 'No follow-through recovery reacquisition signal is currently surfaced.'))}</div>
        <div class="meta-line"><strong>Reacquisition Durability:</strong> {escape(summary.get('follow_through_recovery_reacquisition_durability_summary', 'No follow-through reacquisition durability signal is currently surfaced.'))}</div>
        <div class="meta-line"><strong>Reacquisition Confidence:</strong> {escape(summary.get('follow_through_recovery_reacquisition_consolidation_summary', 'No follow-through reacquisition confidence-consolidation signal is currently surfaced.'))}</div>
        <div class="meta-line"><strong>Reacquisition Softening Decay:</strong> {escape(summary.get('follow_through_reacquisition_softening_decay_summary', 'No reacquisition softening-decay signal is currently surfaced.'))}</div>
        <div class="meta-line"><strong>Reacquisition Confidence Retirement:</strong> {escape(summary.get('follow_through_reacquisition_confidence_retirement_summary', 'No reacquisition confidence-retirement signal is currently surfaced.'))}</div>
        <div class="meta-line"><strong>Revalidation Recovery:</strong> {escape(summary.get('follow_through_reacquisition_revalidation_recovery_summary', 'No post-revalidation recovery or confidence re-earning signal is currently surfaced.'))}</div>
        <div class="meta-line"><strong>Primary Target:</strong> {escape(primary_target_label or 'No active target')}</div>
        <div class="meta-line"><strong>Why This Is The Top Target:</strong> {escape(summary.get('primary_target_reason', 'No target rationale is recorded yet.'))}</div>
        <div class="meta-line"><strong>What Counts As Done:</strong> {escape(summary.get('primary_target_done_criteria', 'No done-state guidance is recorded yet.'))}</div>
        <div class="meta-line"><strong>Closure Guidance:</strong> {escape(summary.get('closure_guidance', 'No closure guidance is recorded yet.'))}</div>
        <div class="meta-line"><strong>What We Tried:</strong> {escape(intervention_label)}</div>
        <div class="meta-line"><strong>Resolution Evidence:</strong> {escape(summary.get('primary_target_resolution_evidence', 'No resolution evidence is recorded yet.'))}</div>
        <div class="meta-line"><strong>Primary Target Confidence:</strong> {escape(summary.get('primary_target_confidence_label', 'low'))} ({summary.get('primary_target_confidence_score', 0.0):.2f})</div>
        <div class="meta-line"><strong>Confidence Reasons:</strong> {escape(', '.join(summary.get('primary_target_confidence_reasons', []) or ['No confidence rationale is recorded yet.']))}</div>
        <div class="meta-line"><strong>Next Action Confidence:</strong> {escape(summary.get('next_action_confidence_label', 'low'))} ({summary.get('next_action_confidence_score', 0.0):.2f})</div>
        <div class="meta-line"><strong>Trust Policy:</strong> {escape(summary.get('primary_target_trust_policy', 'monitor'))} — {escape(summary.get('primary_target_trust_policy_reason', 'No trust-policy reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Why This Confidence Is Actionable:</strong> {escape(summary.get('adaptive_confidence_summary', 'No adaptive confidence summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Trust Policy Exception:</strong> {escape(summary.get('primary_target_exception_status', 'none'))} — {escape(summary.get('primary_target_exception_reason', 'No trust-policy exception reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Exception Pattern Learning:</strong> {escape(summary.get('primary_target_exception_pattern_status', 'none'))} — {escape(summary.get('primary_target_exception_pattern_reason', 'No exception-pattern reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Trust Recovery:</strong> {escape(summary.get('primary_target_trust_recovery_status', 'none'))} — {escape(summary.get('primary_target_trust_recovery_reason', 'No trust-recovery reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Recovery Confidence:</strong> {escape(summary.get('primary_target_recovery_confidence_label', 'low'))} ({summary.get('primary_target_recovery_confidence_score', 0.0):.2f}) — {escape(summary.get('recovery_confidence_summary', 'No recovery-confidence summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Exception Retirement:</strong> {escape(summary.get('primary_target_exception_retirement_status', 'none'))} — {escape(summary.get('primary_target_exception_retirement_reason', 'No exception-retirement reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Policy Debt Cleanup:</strong> {escape(summary.get('primary_target_policy_debt_status', 'none'))} — {escape(summary.get('primary_target_policy_debt_reason', 'No policy-debt reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Class-Level Trust Normalization:</strong> {escape(summary.get('primary_target_class_normalization_status', 'none'))} — {escape(summary.get('primary_target_class_normalization_reason', 'No class-normalization reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Class Memory Freshness:</strong> {escape(summary.get('primary_target_class_memory_freshness_status', 'insufficient-data'))} — {escape(summary.get('primary_target_class_memory_freshness_reason', 'No class-memory freshness reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Trust Decay Controls:</strong> {escape(summary.get('primary_target_class_decay_status', 'none'))} — {escape(summary.get('primary_target_class_decay_reason', 'No class-decay reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Class Trust Reweighting:</strong> {escape(summary.get('primary_target_class_trust_reweight_direction', 'neutral'))} ({summary.get('primary_target_class_trust_reweight_score', 0.0):.2f})</div>
        <div class="meta-line"><strong>Why Class Guidance Shifted:</strong> {escape(', '.join(summary.get('primary_target_class_trust_reweight_reasons', []) or ['No class reweighting rationale is recorded yet.']))}</div>
        <div class="meta-line"><strong>Class Trust Momentum:</strong> {escape(summary.get('primary_target_class_trust_momentum_status', 'insufficient-data'))} ({summary.get('primary_target_class_trust_momentum_score', 0.0):.2f})</div>
        <div class="meta-line"><strong>Reweighting Stability:</strong> {escape(summary.get('primary_target_class_reweight_stability_status', 'watch'))} — {escape(summary.get('primary_target_class_reweight_transition_status', 'none'))}: {escape(summary.get('primary_target_class_reweight_transition_reason', 'No class transition reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Class Transition Health:</strong> {escape(summary.get('primary_target_class_transition_health_status', 'none'))} — {escape(summary.get('primary_target_class_transition_health_reason', 'No class transition health reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Pending Transition Resolution:</strong> {escape(summary.get('primary_target_class_transition_resolution_status', 'none'))} — {escape(summary.get('primary_target_class_transition_resolution_reason', 'No class transition resolution reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Transition Closure Confidence:</strong> {escape(summary.get('primary_target_transition_closure_confidence_label', 'low'))} ({summary.get('primary_target_transition_closure_confidence_score', 0.0):.2f}) — {escape(summary.get('primary_target_transition_closure_likely_outcome', 'none'))}</div>
        <div class="meta-line"><strong>Class Pending Debt Audit:</strong> {escape(summary.get('primary_target_class_pending_debt_status', 'none'))} — {escape(summary.get('primary_target_class_pending_debt_reason', 'No class pending-debt reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Pending Debt Freshness:</strong> {escape(summary.get('primary_target_pending_debt_freshness_status', 'insufficient-data'))} — {escape(summary.get('primary_target_pending_debt_freshness_reason', 'No pending-debt freshness reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Closure Forecast Reweighting:</strong> {escape(summary.get('primary_target_closure_forecast_reweight_direction', 'neutral'))} ({summary.get('primary_target_closure_forecast_reweight_score', 0.0):.2f})</div>
        <div class="meta-line"><strong>Closure Forecast Momentum:</strong> {escape(summary.get('primary_target_closure_forecast_momentum_status', 'insufficient-data'))} ({summary.get('primary_target_closure_forecast_momentum_score', 0.0):.2f})</div>
        <div class="meta-line"><strong>Closure Forecast Freshness:</strong> {escape(summary.get('primary_target_closure_forecast_freshness_status', 'insufficient-data'))} — {escape(summary.get('primary_target_closure_forecast_freshness_reason', 'No closure-forecast freshness reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Closure Forecast Hysteresis:</strong> {escape(summary.get('primary_target_closure_forecast_stability_status', 'watch'))} — {escape(summary.get('primary_target_closure_forecast_hysteresis_status', 'none'))}: {escape(summary.get('primary_target_closure_forecast_hysteresis_reason', 'No closure-forecast hysteresis reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Hysteresis Decay Controls:</strong> {escape(summary.get('primary_target_closure_forecast_decay_status', 'none'))} — {escape(summary.get('primary_target_closure_forecast_decay_reason', 'No closure-forecast decay reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Closure Forecast Refresh Recovery:</strong> {escape(summary.get('primary_target_closure_forecast_refresh_recovery_status', 'none'))} ({summary.get('primary_target_closure_forecast_refresh_recovery_score', 0.0):.2f})</div>
        <div class="meta-line"><strong>Reacquisition Controls:</strong> {escape(summary.get('primary_target_closure_forecast_reacquisition_status', 'none'))} — {escape(summary.get('primary_target_closure_forecast_reacquisition_reason', 'No closure-forecast reacquisition reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reacquisition Persistence:</strong> {escape(summary.get('primary_target_closure_forecast_reacquisition_persistence_status', 'none'))} ({summary.get('primary_target_closure_forecast_reacquisition_persistence_score', 0.0):.2f}; {summary.get('primary_target_closure_forecast_reacquisition_age_runs', 0)} run(s))</div>
        <div class="meta-line"><strong>Recovery Churn Controls:</strong> {escape(summary.get('primary_target_closure_forecast_recovery_churn_status', 'none'))} — {escape(summary.get('primary_target_closure_forecast_recovery_churn_reason', 'No recovery-churn reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reacquisition Freshness:</strong> {escape(summary.get('primary_target_closure_forecast_reacquisition_freshness_status', 'insufficient-data'))} — {escape(summary.get('primary_target_closure_forecast_reacquisition_freshness_reason', 'No reacquisition-freshness reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Persistence Reset Controls:</strong> {escape(summary.get('primary_target_closure_forecast_persistence_reset_status', 'none'))} — {escape(summary.get('primary_target_closure_forecast_persistence_reset_reason', 'No persistence-reset reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Refresh Recovery:</strong> {escape(summary.get('primary_target_closure_forecast_reset_refresh_recovery_status', 'none'))} ({summary.get('primary_target_closure_forecast_reset_refresh_recovery_score', 0.0):.2f})</div>
        <div class="meta-line"><strong>Reset Re-entry Controls:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_status', 'none'))} — {escape(summary.get('primary_target_closure_forecast_reset_reentry_reason', 'No reset re-entry reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Persistence:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_persistence_status', 'none'))} ({summary.get('primary_target_closure_forecast_reset_reentry_persistence_score', 0.0):.2f}; {summary.get('primary_target_closure_forecast_reset_reentry_age_runs', 0)} run(s))</div>
        <div class="meta-line"><strong>Reset Re-entry Churn Controls:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_churn_status', 'none'))} — {escape(summary.get('primary_target_closure_forecast_reset_reentry_churn_reason', 'No reset re-entry churn reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Freshness:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_freshness_status', 'insufficient-data'))} — {escape(summary.get('primary_target_closure_forecast_reset_reentry_freshness_reason', 'No reset re-entry freshness reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Reset Controls:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_reset_status', 'none'))} — {escape(summary.get('primary_target_closure_forecast_reset_reentry_reset_reason', 'No reset re-entry reset reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Refresh Recovery:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_refresh_recovery_status', 'none'))} ({summary.get('primary_target_closure_forecast_reset_reentry_refresh_recovery_score', 0.0):.2f})</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Controls:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_status', 'none'))} — {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reason', 'No reset re-entry rebuild reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Freshness:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_freshness_status', 'insufficient-data'))} — {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_freshness_reason', 'No reset re-entry rebuild freshness reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Reset Controls:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reset_status', 'none'))} — {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reset_reason', 'No reset re-entry rebuild reset reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Refresh Recovery:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_refresh_recovery_status', 'none'))} ({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_refresh_recovery_score', 0.0):.2f})</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-entry Controls:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_status', 'none'))} — {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_reason', 'No reset re-entry rebuild re-entry reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Persistence:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_status', 'none'))} ({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_score', 0.0):.2f}; {summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_age_runs', 0)} run(s))</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Churn Controls:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_status', 'none'))} — {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_reason', 'No reset re-entry rebuild re-entry churn reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Freshness:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_freshness_status', 'insufficient-data'))} — {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_freshness_reason', 'No reset re-entry rebuild re-entry freshness reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Reset Controls:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_reset_status', 'none'))} — {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_reset_reason', 'No reset re-entry rebuild re-entry reset reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Refresh Recovery:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status', 'none'))} — {escape(summary.get('closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_summary', 'No reset re-entry rebuild re-entry refresh recovery summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Controls:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_status', 'none'))} — {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reason', 'No reset re-entry rebuild re-entry restore reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Freshness:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_status', 'insufficient-data'))} — {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_reason', 'No reset re-entry rebuild re-entry restore freshness reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Reset Controls:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reset_status', 'none'))} — {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reset_reason', 'No reset re-entry rebuild re-entry restore reset reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Refresh Recovery:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_status', 'none'))} — {escape(summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_summary', 'No reset re-entry rebuild re-entry restore refresh recovery summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Restore Controls:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status', 'none'))} — {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason', 'No reset re-entry rebuild re-entry restore re-restore reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Restore Persistence:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_status', 'none'))} ({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_score', 0.0):.2f}; {summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_age_runs', 0)} run(s))</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Restore Churn Controls:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_status', 'none'))} — {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_reason', 'No reset re-entry rebuild re-entry restore re-restore churn reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Restore Freshness:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status', 'insufficient-data'))} — {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_reason', 'No reset re-entry rebuild re-entry restore re-restore freshness reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Restore Reset Controls:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_status', 'none'))} — {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_reason', 'No reset re-entry rebuild re-entry restore re-restore reset reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Restore Refresh Recovery:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_status', 'none'))} — {escape(summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_summary', 'No reset re-entry rebuild re-entry restore re-restore refresh recovery summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Controls:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status', 'none'))} — {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason', 'No reset re-entry rebuild re-entry restore re-re-restore reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Persistence:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status', 'none'))} ({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score', 0.0):.2f}; {summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs', 0)} run(s))</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Churn Controls:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status', 'none'))} — {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason', 'No reset re-entry rebuild re-entry restore re-re-restore churn reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Freshness:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status', 'insufficient-data'))} — {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_reason', 'No reset re-entry rebuild re-entry restore re-re-restore freshness reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Reset Controls:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status', 'none'))} — {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_reason', 'No reset re-entry rebuild re-entry restore re-re-restore reset reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Refresh Recovery:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status', 'none'))} — {escape(summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_summary', 'No reset re-entry rebuild re-entry restore re-re-restore refresh recovery summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Controls:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status', 'none'))} — {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_reason', 'No reset re-entry rebuild re-entry restore re-re-re-restore reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Persistence:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status', 'none'))} ({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score', 0.0):.2f}; {summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs', 0)} run(s))</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Churn Controls:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status', 'none'))} — {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason', 'No reset re-entry rebuild re-entry restore re-re-re-restore churn reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Persistence:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_persistence_status', 'none'))} ({summary.get('primary_target_closure_forecast_reset_reentry_rebuild_persistence_score', 0.0):.2f}; {summary.get('primary_target_closure_forecast_reset_reentry_rebuild_age_runs', 0)} run(s))</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Churn Controls:</strong> {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_churn_status', 'none'))} — {escape(summary.get('primary_target_closure_forecast_reset_reentry_rebuild_churn_reason', 'No reset re-entry rebuild churn reason is recorded yet.'))}</div>
        <div class="meta-line"><strong>Recommendation Drift:</strong> {escape(summary.get('recommendation_drift_status', 'stable'))} — {escape(summary.get('recommendation_drift_summary', 'No recommendation-drift summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Exception Pattern Summary:</strong> {escape(summary.get('exception_pattern_summary', 'No exception-pattern summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Exception Retirement Summary:</strong> {escape(summary.get('exception_retirement_summary', 'No exception-retirement summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Policy Debt Summary:</strong> {escape(summary.get('policy_debt_summary', 'No policy-debt summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Trust Normalization Summary:</strong> {escape(summary.get('trust_normalization_summary', 'No trust-normalization summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Class Memory Summary:</strong> {escape(summary.get('class_memory_summary', 'No class-memory summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Class Decay Summary:</strong> {escape(summary.get('class_decay_summary', 'No class-decay summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Class Reweighting Summary:</strong> {escape(summary.get('class_reweighting_summary', 'No class reweighting summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Class Momentum Summary:</strong> {escape(summary.get('class_momentum_summary', 'No class momentum summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reweighting Stability Summary:</strong> {escape(summary.get('class_reweight_stability_summary', 'No reweighting stability summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Class Transition Health Summary:</strong> {escape(summary.get('class_transition_health_summary', 'No class transition health summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Pending Transition Resolution Summary:</strong> {escape(summary.get('class_transition_resolution_summary', 'No class transition resolution summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Transition Closure Confidence Summary:</strong> {escape(summary.get('transition_closure_confidence_summary', 'No transition-closure confidence summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Class Pending Debt Summary:</strong> {escape(summary.get('class_pending_debt_summary', 'No class pending-debt summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Class Pending Resolution Summary:</strong> {escape(summary.get('class_pending_resolution_summary', 'No class pending-resolution summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Pending Debt Freshness Summary:</strong> {escape(summary.get('pending_debt_freshness_summary', 'No pending-debt freshness summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Pending Debt Decay Summary:</strong> {escape(summary.get('pending_debt_decay_summary', 'No pending-debt decay summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Closure Forecast Reweighting Summary:</strong> {escape(summary.get('closure_forecast_reweighting_summary', 'No closure-forecast reweighting summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Closure Forecast Momentum Summary:</strong> {escape(summary.get('closure_forecast_momentum_summary', 'No closure-forecast momentum summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Closure Forecast Freshness Summary:</strong> {escape(summary.get('closure_forecast_freshness_summary', 'No closure-forecast freshness summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Closure Forecast Stability Summary:</strong> {escape(summary.get('closure_forecast_stability_summary', 'No closure-forecast stability summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Closure Forecast Hysteresis Summary:</strong> {escape(summary.get('closure_forecast_hysteresis_summary', 'No closure-forecast hysteresis summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Closure Forecast Decay Summary:</strong> {escape(summary.get('closure_forecast_decay_summary', 'No closure-forecast decay summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Closure Forecast Refresh Recovery Summary:</strong> {escape(summary.get('closure_forecast_refresh_recovery_summary', 'No closure-forecast refresh-recovery summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Closure Forecast Reacquisition Summary:</strong> {escape(summary.get('closure_forecast_reacquisition_summary', 'No closure-forecast reacquisition summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reacquisition Persistence Summary:</strong> {escape(summary.get('closure_forecast_reacquisition_persistence_summary', 'No reacquisition-persistence summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Recovery Churn Summary:</strong> {escape(summary.get('closure_forecast_recovery_churn_summary', 'No recovery-churn summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reacquisition Freshness Summary:</strong> {escape(summary.get('closure_forecast_reacquisition_freshness_summary', 'No reacquisition-freshness summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Persistence Reset Summary:</strong> {escape(summary.get('closure_forecast_persistence_reset_summary', 'No persistence-reset summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Refresh Recovery Summary:</strong> {escape(summary.get('closure_forecast_reset_refresh_recovery_summary', 'No reset-refresh recovery summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_summary', 'No reset re-entry summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Persistence Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_persistence_summary', 'No reset re-entry persistence summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Churn Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_churn_summary', 'No reset re-entry churn summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Freshness Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_freshness_summary', 'No reset re-entry freshness summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Reset Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_reset_summary', 'No reset re-entry reset summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Refresh Recovery Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_refresh_recovery_summary', 'No reset re-entry refresh-recovery summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_summary', 'No reset re-entry rebuild summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Freshness Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_freshness_summary', 'No reset re-entry rebuild-freshness summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Reset Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_reset_summary', 'No reset re-entry rebuild-reset summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Refresh Recovery Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_refresh_recovery_summary', 'No reset re-entry rebuild-refresh-recovery summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-entry Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_reentry_summary', 'No reset re-entry rebuild re-entry summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Persistence Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_reentry_persistence_summary', 'No reset re-entry rebuild re-entry persistence summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Churn Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_reentry_churn_summary', 'No reset re-entry rebuild re-entry churn summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Freshness Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_reentry_freshness_summary', 'No reset re-entry rebuild re-entry freshness summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Reset Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_reentry_reset_summary', 'No reset re-entry rebuild re-entry reset summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Refresh Recovery Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_summary', 'No reset re-entry rebuild re-entry refresh recovery summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_summary', 'No reset re-entry rebuild re-entry restore summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Freshness Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_summary', 'No reset re-entry rebuild re-entry restore freshness summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Reset Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_reset_summary', 'No reset re-entry rebuild re-entry restore reset summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Refresh Recovery Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_summary', 'No reset re-entry rebuild re-entry restore refresh recovery summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Restore Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_summary', 'No reset re-entry rebuild re-entry restore re-restore summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Restore Persistence Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_summary', 'No reset re-entry rebuild re-entry restore re-restore persistence summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Restore Churn Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_summary', 'No reset re-entry rebuild re-entry restore re-restore churn summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Restore Freshness Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_summary', 'No reset re-entry rebuild re-entry restore re-restore freshness summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Restore Reset Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_summary', 'No reset re-entry rebuild re-entry restore re-restore reset summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Restore Refresh Recovery Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_summary', 'No reset re-entry rebuild re-entry restore re-restore refresh recovery summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_summary', 'No reset re-entry rebuild re-entry restore re-re-restore summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Persistence Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_summary', 'No reset re-entry rebuild re-entry restore re-re-restore persistence summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Churn Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_summary', 'No reset re-entry rebuild re-entry restore re-re-restore churn summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Freshness Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_summary', 'No reset re-entry rebuild re-entry restore re-re-restore freshness summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Reset Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_summary', 'No reset re-entry rebuild re-entry restore re-re-restore reset summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Refresh Recovery Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_summary', 'No reset re-entry rebuild re-entry restore re-re-restore refresh recovery summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_summary', 'No reset re-entry rebuild re-entry restore re-re-re-restore summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Persistence Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_summary', 'No reset re-entry rebuild re-entry restore re-re-re-restore persistence summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Churn Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_summary', 'No reset re-entry rebuild re-entry restore re-re-re-restore churn summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Persistence Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_persistence_summary', 'No reset re-entry rebuild-persistence summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Reset Re-entry Rebuild Churn Summary:</strong> {escape(summary.get('closure_forecast_reset_reentry_rebuild_churn_summary', 'No reset re-entry rebuild-churn summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Recommendation Quality:</strong> {escape(summary.get('recommendation_quality_summary', 'No recommendation-quality summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Confidence Validation:</strong> {escape(summary.get('confidence_validation_status', 'insufficient-data'))} — {escape(summary.get('confidence_calibration_summary', 'No confidence-calibration summary is recorded yet.'))}</div>
        <div class="meta-line"><strong>Recent Confidence Outcomes:</strong> {escape(_recent_confidence_outcomes_label(summary.get('recent_validation_outcomes') or []))}</div>
        <div class="meta-line"><strong>Blocked:</strong> {counts.get('blocked', 0)} | <strong>Urgent:</strong> {counts.get('urgent', 0)} | <strong>Ready:</strong> {counts.get('ready', 0)} | <strong>Deferred:</strong> {counts.get('deferred', 0)}</div>
        <ul class="bullet-list">{''.join(rows) or '<li>No triage items are currently surfaced.</li>'}</ul>
        <div class="meta-line"><strong>Recently Changed:</strong></div>
        <ul class="bullet-list">{recent_markup or '<li>No recent operator changes were loaded.</li>'}</ul>
      </div>
    </div>"""


def _top_attention_section(data: dict) -> str:
    queue = data.get("operator_queue") or []
    if not queue:
        return ""

    rows = []
    for item in queue[:3]:
        repo = f"{escape(item.get('repo', ''))}: " if item.get("repo") else ""
        intent_alignment = (
            f"{item.get('intent_alignment', 'missing-contract')}: "
            f"{item.get('intent_alignment_reason', 'Intent alignment cannot be judged until a portfolio catalog contract exists.')}"
        )
        rows.append(
            "<li>"
            f"<strong>{repo}{escape(item.get('title', 'Triage item'))}</strong>"
            f"<br><span class='muted'><strong>Why it matters:</strong> {escape(item.get('lane_reason') or item.get('summary') or 'Operator attention is still needed.')}</span>"
            f"<br><span class='muted'><strong>What to do next:</strong> {escape(item.get('recommended_action') or item.get('next_step') or 'Review the latest state.')}</span>"
            f"<br><span class='muted'><strong>Operator Focus:</strong> {escape(build_operator_focus_line(item))}</span>"
            f"<br><span class='muted'><strong>Catalog:</strong> {escape(item.get('catalog_line', 'No portfolio catalog contract is recorded yet.'))}</span>"
            f"<br><span class='muted'><strong>Intent Alignment:</strong> {escape(intent_alignment)}</span>"
            f"<br><span class='muted'><strong>{escape(item.get('scorecard_line', 'Scorecard: No maturity scorecard is recorded yet.'))}</strong></span>"
            f"<br><span class='muted'><strong>Maturity Gap:</strong> {escape(item.get('maturity_gap_summary', 'No maturity gap summary is recorded yet.'))}</span>"
            f"<br><span class='muted'><strong>Action Sync:</strong> {escape(item.get('action_sync_line', 'Action Sync: stay local until a campaign has meaningful actions and healthy writeback prerequisites.'))}</span>"
            f"<br><span class='muted'><strong>Checkpoint timing:</strong> {escape(build_follow_through_checkpoint_status_label(item))}</span>"
            "</li>"
        )

    return f"""
    <div class="section">
      <h2>Top Attention / Next Action</h2>
      <div class="panel">
        <ul class="bullet-list">{''.join(rows)}</ul>
      </div>
    </div>"""


def _weekly_review_pack_section(report_data: dict, diff_data: dict | None) -> str:
    weekly_pack = build_weekly_review_pack(report_data, diff_data)
    attention_rows = []
    for item in weekly_pack.get("top_attention", [])[:5]:
        intent_alignment = (
            f"{item.get('intent_alignment', 'missing-contract')}: "
            f"{item.get('intent_alignment_summary', 'Intent alignment cannot be judged until a portfolio catalog contract exists.')}"
        )
        attention_rows.append(
            "<li>"
            f"<strong>{escape(item.get('repo', 'Portfolio'))}:</strong> {escape(item.get('title', 'Operator attention item'))}"
            f"<br><span class='muted'><strong>What Changed:</strong> {escape(item.get('last_movement', 'Current run'))}</span>"
            f"<br><span class='muted'><strong>Why It Matters:</strong> {escape(item.get('why', 'Operator pressure is active.'))}</span>"
            f"<br><span class='muted'><strong>What To Do Next:</strong> {escape(item.get('next_step', 'Review the latest state.'))}</span>"
            f"<br><span class='muted'><strong>Operator Focus:</strong> {escape(item.get('operator_focus_line', 'Watch Closely: No operator focus bucket is currently surfaced.'))}</span>"
            f"<br><span class='muted'><strong>Catalog:</strong> {escape(item.get('catalog_line', 'No portfolio catalog contract is recorded yet.'))}</span>"
            f"<br><span class='muted'><strong>Intent Alignment:</strong> {escape(intent_alignment)}</span>"
            f"<br><span class='muted'><strong>{escape(item.get('scorecard_line', 'Scorecard: No maturity scorecard is recorded yet.'))}</strong></span>"
            f"<br><span class='muted'><strong>Maturity Gap:</strong> {escape(item.get('maturity_gap_summary', 'No maturity gap summary is recorded yet.'))}</span>"
            f"<br><span class='muted'><strong>Action Sync:</strong> {escape(item.get('action_sync_line', 'Action Sync: stay local until a campaign has meaningful actions and healthy writeback prerequisites.'))}</span>"
            f"<br><span class='muted'><strong>Checkpoint Timing:</strong> {escape(item.get('follow_through_checkpoint_timing', 'Unknown'))}</span>"
            f"<br><span class='muted'><strong>Next Checkpoint:</strong> {escape(item.get('follow_through_checkpoint', 'Use the next run or linked artifact to confirm whether the recommendation moved.'))}</span>"
            "</li>"
        )

    focus_sections = [
        ("Act Now", weekly_pack.get("top_act_now_items", []), "No immediate-action hotspots are currently surfaced."),
        ("Watch Closely", weekly_pack.get("top_watch_closely_items", []), "No watch-closely hotspots are currently surfaced."),
        ("Improving", weekly_pack.get("top_improving_items", []), "No clearly improving hotspots are currently surfaced."),
        ("Fragile", weekly_pack.get("top_fragile_items", []), "No fragile hotspots are currently surfaced."),
        ("Revalidate", weekly_pack.get("top_revalidate_items", []), "No revalidation hotspots are currently surfaced."),
    ]
    focus_blocks = []
    for label, items, empty_message in focus_sections:
        rows = []
        for item in items[:3]:
            item_label = f"{item.get('repo')}: {item.get('title')}" if item.get("repo") else item.get("title", "Operator item")
            rows.append(
                f"<li><strong>{escape(item_label)}</strong> — {escape(item.get('operator_focus_summary', 'No operator focus bucket is currently surfaced.'))}</li>"
            )
        focus_blocks.append(
            f"<h3>{escape(label)}</h3><ul class='bullet-list'>{''.join(rows) or f'<li>{escape(empty_message)}</li>'}</ul>"
        )

    readiness_sections = [
        ("Apply Ready", weekly_pack.get("top_apply_ready_campaigns", []), "No campaigns are currently apply-ready."),
        ("Preview Ready", weekly_pack.get("top_preview_ready_campaigns", []), "No campaigns are currently preview-ready."),
        ("Drift Review", weekly_pack.get("top_drift_review_campaigns", []), "No campaigns are currently waiting on drift review."),
        ("Blocked", weekly_pack.get("top_blocked_campaigns", []), "No campaigns are currently blocked."),
    ]
    readiness_blocks = []
    for label, items, empty_message in readiness_sections:
        rows = []
        for item in items[:3]:
            rows.append(
                f"<li><strong>{escape(item.get('label', item.get('campaign_type', 'Campaign')))}</strong> — "
                f"{escape(item.get('reason', 'No readiness reason is recorded yet.'))} "
                f"<span class='muted'>(target {escape(item.get('recommended_target', 'none'))})</span></li>"
            )
        readiness_blocks.append(
            f"<h3>{escape(label)}</h3><ul class='bullet-list'>{''.join(rows) or f'<li>{escape(empty_message)}</li>'}</ul>"
        )

    repo_cards = []
    for briefing in weekly_pack.get("repo_briefings", [])[:3]:
        repo_cards.append(
            f"""
            <div class="panel">
              <h3><a href="#{escape(briefing.get('anchor', 'repo'), quote=True)}">{escape(briefing.get('headline', briefing.get('repo', 'Repo briefing')))}</a></h3>
              <div class="meta-line"><strong>Current State:</strong> {escape(briefing.get('current_state_line', 'No current-state summary is recorded yet.'))}</div>
              <div class="meta-line"><strong>What Changed:</strong> {escape(briefing.get('what_changed_line', 'No change summary is recorded yet.'))}</div>
              <div class="meta-line"><strong>Why It Matters:</strong> {escape(briefing.get('why_it_matters_line', 'No explanation summary is recorded yet.'))}</div>
              <div class="meta-line"><strong>Where To Start:</strong> {escape(briefing.get('where_to_start_summary', 'No meaningful implementation hotspot is currently surfaced.'))}</div>
              <div class="meta-line"><strong>What To Do Next:</strong> {escape(briefing.get('what_to_do_next_line', 'No next action is recorded yet.'))}</div>
              <div class="meta-line"><strong>Operator Focus:</strong> {escape(briefing.get('operator_focus_line', 'Watch Closely: No operator focus bucket is currently surfaced.'))}</div>
              <div class="meta-line"><strong>Catalog:</strong> {escape(briefing.get('catalog_line', 'No portfolio catalog contract is recorded yet.'))}</div>
              <div class="meta-line"><strong>Intent Alignment:</strong> {escape(briefing.get('intent_alignment_line', 'missing-contract: Intent alignment cannot be judged until a portfolio catalog contract exists.'))}</div>
              <div class="meta-line"><strong>{escape(briefing.get('scorecard_line', 'Scorecard: No maturity scorecard is recorded yet.'))}</strong></div>
              <div class="meta-line"><strong>Maturity Gap:</strong> {escape(briefing.get('maturity_gap_summary', 'No maturity gap summary is recorded yet.'))}</div>
              <div class="meta-line"><strong>Action Sync:</strong> {escape(briefing.get('action_sync_line', 'Action Sync: stay local until a campaign has meaningful actions and healthy writeback prerequisites.'))}</div>
              <div class="meta-line"><strong>Checkpoint Timing:</strong> {escape(briefing.get('checkpoint_timing_line', 'Unknown'))}</div>
              <div class="meta-line"><strong>What Would Count As Progress:</strong> {escape(briefing.get('checkpoint_line', 'Use the next run or linked artifact to confirm whether the recommendation moved.'))}</div>
            </div>
            """
        )
    return f"""
    <div class="section">
      <h2>Weekly Review Pack</h2>
      <div class="analyst-grid">
        <div class="panel">
          <div class="meta-line"><strong>Product Mode:</strong> {escape(weekly_pack.get('product_mode_summary', 'Weekly Review: use this artifact for the normal workbook-first operator loop.'))}</div>
          <div class="meta-line"><strong>Artifact Role:</strong> {escape(weekly_pack.get('artifact_role_summary', 'This artifact is the shared weekly handoff across workbook, HTML, Markdown, and review-pack.'))}</div>
          <div class="meta-line"><strong>Suggested Reading Order:</strong> {escape(weekly_pack.get('suggested_reading_order', 'Read Dashboard, then Run Changes, then Review Queue.'))}</div>
          <div class="meta-line"><strong>Next Best Workflow Step:</strong> {escape(weekly_pack.get('next_best_workflow_step', 'Open the standard workbook first, then use --control-center for read-only triage.'))}</div>
          <div class="meta-line"><strong>Portfolio Headline:</strong> {escape(weekly_pack.get('portfolio_headline', 'No weekly headline is recorded yet.'))}</div>
          <div class="meta-line"><strong>Run Changes:</strong> {escape(weekly_pack.get('run_change_summary', build_run_change_summary(diff_data)))}</div>
          <div class="meta-line"><strong>Queue Pressure:</strong> {escape(weekly_pack.get('queue_pressure_summary', build_queue_pressure_summary(report_data, diff_data)))}</div>
          <div class="meta-line"><strong>Trust / Actionability:</strong> {escape(weekly_pack.get('trust_actionability_summary', build_trust_actionability_summary(report_data)))}</div>
          <div class="meta-line"><strong>What To Do This Week:</strong> {escape(weekly_pack.get('what_to_do_this_week', build_top_recommendation_summary(report_data)))}</div>
          <div class="meta-line"><strong>Portfolio Catalog:</strong> {escape(weekly_pack.get('portfolio_catalog_summary', 'No portfolio catalog contract is recorded yet.'))}</div>
          <div class="meta-line"><strong>Intent Alignment:</strong> {escape(weekly_pack.get('intent_alignment_summary', 'Intent alignment cannot be judged until a portfolio catalog contract exists.'))}</div>
          <div class="meta-line"><strong>Scorecards:</strong> {escape(weekly_pack.get('scorecards_summary', 'No maturity scorecard is recorded yet.'))}</div>
          <div class="meta-line"><strong>Implementation Hotspots:</strong> {escape(weekly_pack.get('implementation_hotspots_summary', 'No meaningful implementation hotspots are currently surfaced.'))}</div>
          <div class="meta-line"><strong>Operator Outcomes:</strong> {escape(weekly_pack.get('operator_outcomes_summary', 'Not enough operator history is recorded yet to judge outcomes.'))}</div>
          <div class="meta-line"><strong>Operator Effectiveness:</strong> {escape(weekly_pack.get('operator_effectiveness_line', 'Not enough judged recommendation history is recorded yet to judge operator effectiveness.'))}</div>
          <div class="meta-line"><strong>High-Pressure Queue Trend:</strong> {escape(weekly_pack.get('high_pressure_queue_trend_line', 'High-pressure queue trend is not ready yet.'))}</div>
          <div class="meta-line"><strong>Action Sync Readiness:</strong> {escape(weekly_pack.get('action_sync_summary', 'No current campaign needs Action Sync yet, so the safest next move is to keep the story local.'))}</div>
          <div class="meta-line"><strong>Next Action Sync Step:</strong> {escape(weekly_pack.get('next_action_sync_step', 'Stay local for now; no current campaign needs preview or apply.'))}</div>
          <h3>Action Sync Readiness</h3>
          {''.join(readiness_blocks)}
          <div class="meta-line"><strong>Operator Focus:</strong> {escape(weekly_pack.get('operator_focus_summary', 'No operator focus bucket is currently surfaced.'))}</div>
          <div class="meta-line"><strong>Next Checkpoint:</strong> {escape(weekly_pack.get('follow_through_checkpoint_summary', 'Use the next run or linked artifact to confirm whether the recommendation moved.'))}</div>
          <h3>Operator Focus</h3>
          <div class="meta-line"><strong>Summary:</strong> {escape(weekly_pack.get('operator_focus_summary', 'No operator focus bucket is currently surfaced.'))}</div>
          {''.join(f"<div class='meta-line'><strong>Scorecard Gap:</strong> {escape(item.get('repo', 'Repo'))} — {escape(item.get('summary', 'Below target.'))}</div>" for item in weekly_pack.get('top_below_target_scorecard_items', [])[:5])}
          <div class="meta-line"><strong>Next Checkpoint:</strong> {escape(weekly_pack.get('follow_through_checkpoint_summary', 'Use the next run or linked artifact to confirm whether the recommendation moved.'))}</div>
          {''.join(focus_blocks)}
          <h3>Top Attention</h3>
          <ul class="bullet-list">{''.join(attention_rows) or '<li>No urgent attention items are currently surfaced.</li>'}</ul>
        </div>
        <div class="panel">
          <h3>Top Repo Drilldowns</h3>
          {''.join(repo_cards) or "<div class='meta-line'>No repo drilldowns are recorded yet.</div>"}
        </div>
      </div>
    </div>"""


def _intervention_label(intervention: dict) -> str:
    if not intervention:
        return "No intervention evidence is recorded yet."
    when = (intervention.get("recorded_at") or "")[:10]
    event_type = intervention.get("event_type", "recorded")
    outcome = intervention.get("outcome", event_type)
    return f"{when} — {event_type} ({outcome})".strip()


def _recent_confidence_outcomes_label(outcomes: list[dict]) -> str:
    if not outcomes:
        return "No recent judged confidence outcomes are recorded yet."
    parts = []
    for item in outcomes[:3]:
        parts.append(
            f"{item.get('target_label', 'Operator target')} "
            f"[{item.get('confidence_label', 'low')}] -> {str(item.get('outcome', 'unresolved')).replace('_', ' ')}"
        )
    return "; ".join(parts)


def _analyst_summary_section(context: dict) -> str:
    leaders = context["profile_leaderboard"].get("leaders", [])
    rows = []
    for entry in leaders[:5]:
        rows.append(
            f"<tr><td>{escape(entry['name'])}</td><td class=\"num\">{entry['profile_score']:.3f}</td>"
            f"<td>{escape(entry['tier'])}</td></tr>"
        )
    collection_bits = [
        f"<span class='pill'>{escape(item['name'])}: {item['count']}</span>"
        for item in context["collection_summary"]
    ]
    return f"""
    <div class="section">
      <h2>Analyst View</h2>
      <div class="analyst-grid">
        <div class="panel">
          <div class="meta-line"><strong>Profile:</strong> {escape(context['profile_name'])}</div>
          <div class="meta-line"><strong>Collection:</strong> {escape(context['collection_name'] or 'all')}</div>
          <div class="pill-row">{''.join(collection_bits) or "<span class='pill'>No collections</span>"}</div>
        </div>
        <div class="panel">
          <h3>Profile Leaders</h3>
          <table class="compact-table">
            <thead><tr><th>Repo</th><th>Profile Score</th><th>Tier</th></tr></thead>
            <tbody>{''.join(rows)}</tbody>
          </table>
        </div>
      </div>
    </div>"""


def _lens_summary_section(report_data: dict) -> str:
    cards = []
    for lens_name, lens_data in report_data.get("lenses", {}).items():
        avg_score = lens_data.get("average_score", 0.0)
        cards.append(
            f"<div class='lens-card'>"
            f"<div class='kpi-label'>{escape(lens_name.replace('_', ' '))}</div>"
            f"<div class='lens-score'>{avg_score:.2f}</div>"
            f"<div class='lens-text'>{escape(lens_data.get('description', ''))}</div>"
            f"</div>"
        )
    if not cards:
        return ""
    return f"""
    <div class="section">
      <h2>Decision Lenses</h2>
      <div class="lens-grid">{''.join(cards)}</div>
    </div>"""


def _security_overview_section(report_data: dict) -> str:
    posture = report_data.get("security_posture", {})
    coverage = posture.get("provider_coverage", {})
    alerts = posture.get("open_alerts", {})
    if not posture:
        return ""
    return f"""
    <div class="section">
      <h2>Security Overview</h2>
      <div class="lens-grid">
        <div class="lens-card">
          <div class="kpi-label">Avg Security Score</div>
          <div class="lens-score">{posture.get('average_score', 0):.2f}</div>
          <div class="lens-text">Portfolio-wide merged security posture.</div>
        </div>
        <div class="lens-card">
          <div class="kpi-label">GitHub Coverage</div>
          <div class="lens-score">{coverage.get('github', {}).get('available_repos', 0)}</div>
          <div class="lens-text">Repos with GitHub-native security evidence available.</div>
        </div>
        <div class="lens-card">
          <div class="kpi-label">Scorecard Coverage</div>
          <div class="lens-score">{coverage.get('scorecard', {}).get('available_repos', 0)}</div>
          <div class="lens-text">Repos with external Scorecard evidence loaded.</div>
        </div>
        <div class="lens-card">
          <div class="kpi-label">Open Alerts</div>
          <div class="lens-score">{alerts.get('code_scanning', 0) + alerts.get('secret_scanning', 0)}</div>
          <div class="lens-text">Combined code and secret scanning alerts.</div>
        </div>
      </div>
    </div>"""


# ── Repo table (sorted by score, with sparklines) ─────────────────────
def _repo_table(analyst_context: dict, score_history: dict[str, list[float]] | None = None) -> str:
    rows = []
    for entry in analyst_context["ranked_audits"]:
        a = entry["audit"]
        m = a.get("metadata", {})
        explanation = a.get("score_explanation") or build_score_explanation(a)
        name = m.get("name", "")
        grade = a.get("grade", "F")
        score = a.get("overall_score", 0)
        interest = a.get("interest_score", 0)
        profile_score = entry["profile_score"]
        tier = a.get("completeness_tier", "")
        lang = m.get("language") or ""
        desc = (m.get("description") or "")[:60]
        collections = ", ".join(entry["collections"])
        gc = GRADE_COLORS_CSS.get(grade, "#6B7280")
        tc = TIER_COLORS_CSS.get(tier, "#6B7280")

        spark = ""
        if score_history:
            scores = score_history.get(name, [])
            spark = render_sparkline(scores)

        safe_name = escape(name)
        safe_lang = escape(lang)
        safe_desc = escape(desc)
        safe_tier = escape(tier)
        safe_collections = escape(collections)
        next_action = escape(explanation.get("next_best_action", "") or "")
        score_note = escape(explanation.get("next_tier_gap_summary", "") or "")
        next_action_markup = f'<br><span class="muted"><strong>Next:</strong> {next_action}</span>' if next_action else ""
        score_note_markup = f'<br><span class="muted"><strong>Gap:</strong> {score_note}</span>' if score_note else ""
        repo_anchor = build_repo_briefing(a, {"audits": [a]}, None).get("anchor", f"repo-{escape(name.lower(), quote=True)}")
        link = f'<a href="#{escape(repo_anchor, quote=True)}">{safe_name}</a>'
        rows.append(
            f'<tr data-tier="{escape(tier, quote=True)}" '
            f'data-grade="{escape(grade, quote=True)}" '
            f'data-name="{escape(name, quote=True)}" '
            f'data-collections="{escape(collections.lower(), quote=True)}" '
            f'data-overall="{score:.3f}" '
            f'data-profile="{profile_score:.3f}">'
            f'<td>{link}</td>'
            f'<td class="num">{profile_score:.3f}</td>'
            f'<td style="color:{gc};font-weight:bold;text-align:center">{escape(grade)}</td>'
            f'<td class="num">{score:.3f}</td>'
            f'<td class="num">{interest:.3f}</td>'
            f'<td style="color:{tc};font-weight:bold">{safe_tier}</td>'
            f'<td>{safe_lang}</td>'
            f'<td>{safe_collections or "—"}</td>'
            f'<td class="sparkline">{escape(spark)}</td>'
            f'<td class="desc">{safe_desc}'
            f"{next_action_markup}"
            f"{score_note_markup}"
            f'</td>'
            f'</tr>'
        )

    collection_options = ['<option value="all">All Collections</option>']
    for item in analyst_context["collection_summary"]:
        selected = " selected" if analyst_context["collection_name"] == item["name"] else ""
        collection_options.append(
            f'<option value="{escape(item["name"], quote=True)}"{selected}>{escape(item["name"])}</option>'
        )

    return f"""
    <div class="section">
      <h2>All Repos</h2>
      <div class="filters">
        <select id="sort-mode" onchange="sortTable()">
          <option value="profile">Profile Rank</option>
          <option value="overall">Overall Score</option>
        </select>
        <select id="filter-tier" onchange="filterTable()">
          <option value="all">All Tiers</option>
          <option value="shipped">Shipped</option>
          <option value="functional">Functional</option>
          <option value="wip">WIP</option>
          <option value="skeleton">Skeleton</option>
          <option value="abandoned">Abandoned</option>
        </select>
        <select id="filter-grade" onchange="filterTable()">
          <option value="all">All Grades</option>
          <option value="A">A</option><option value="B">B</option>
          <option value="C">C</option><option value="D">D</option>
          <option value="F">F</option>
        </select>
        <select id="filter-collection" onchange="filterTable()">
          {''.join(collection_options)}
        </select>
        <input id="search" type="text" placeholder="Search repos..." oninput="filterTable()">
      </div>
      <table id="repo-table">
        <thead><tr>
          <th>Repo</th><th>Profile</th><th>Grade</th><th>Score</th><th>Interest</th>
          <th>Tier</th><th>Language</th><th>Collections</th><th>Trend</th><th>Description</th>
        </tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>"""


def _repo_drilldown_section(report_data: dict, diff_data: dict | None) -> str:
    audits = sorted(report_data.get("audits", []) or [], key=lambda audit: audit.get("overall_score", 0.0), reverse=True)
    cards = []
    for audit in audits:
        briefing = build_repo_briefing(audit, report_data, diff_data)
        current_state = briefing.get("current_state", {})
        why = briefing.get("why_this_repo_looks_this_way", {})
        changed = briefing.get("what_changed", {})
        next_steps = briefing.get("what_to_do_next", {})
        cards.append(
            f"""
            <div class="panel" id="{escape(briefing.get('anchor', 'repo'), quote=True)}">
              <h3>{escape(briefing.get('headline', briefing.get('repo', 'Repo briefing')))}</h3>
              <div class="meta-line"><strong>Current State:</strong> {escape(briefing.get('current_state_line', 'No current-state summary is recorded yet.'))}</div>
              <div class="meta-line"><strong>Description:</strong> {escape(current_state.get('description', 'No description recorded yet.'))}</div>
              <div class="meta-line"><strong>Why This Repo Looks This Way:</strong> Strongest drivers: {escape(why.get('strongest_drivers', 'No strong positive drivers recorded yet.'))}. Biggest drags: {escape(why.get('biggest_drags', 'No major drag factors recorded yet.'))}. Next tier gap: {escape(why.get('next_tier_gap', 'No next-tier gap is recorded yet.'))}</div>
              <div class="meta-line"><strong>What Changed:</strong> {escape(changed.get('last_movement', 'No change timing is recorded yet.'))} {escape(changed.get('recent_change_summary', 'No recent change summary is recorded yet.'))}</div>
              <div class="meta-line"><strong>Hotspot Context:</strong> {escape(changed.get('top_hotspot_context', 'No hotspot context is recorded yet.'))}</div>
              <div class="meta-line"><strong>Where To Start:</strong> {escape(briefing.get('where_to_start_summary', 'No meaningful implementation hotspot is currently surfaced.'))}</div>
              <ul class="bullet-list">{''.join(f"<li>{escape(item.get('path', 'repo root'))}: {escape(item.get('signal_summary', 'No signal summary recorded yet.'))}</li>" for item in briefing.get('implementation_hotspots', [])[:3]) or '<li>No implementation hotspots are currently surfaced.</li>'}</ul>
              <div class="meta-line"><strong>What To Do Next:</strong> {escape(next_steps.get('next_best_action', 'No clear next action is recorded yet.'))}</div>
              <div class="meta-line"><strong>Rationale:</strong> {escape(next_steps.get('rationale', 'No action rationale is recorded yet.'))}</div>
              <div class="meta-line"><strong>Follow-Through:</strong> {escape(briefing.get('follow_through_line', 'No follow-through evidence is recorded yet.'))}</div>
              <div class="meta-line"><strong>Checkpoint Timing:</strong> {escape(briefing.get('checkpoint_timing_line', 'Unknown'))}</div>
              <div class="meta-line"><strong>Escalation:</strong> {escape(briefing.get('escalation_line', 'Unknown: No stronger follow-through escalation is currently surfaced.'))}</div>
              <div class="meta-line"><strong>What Would Count As Progress:</strong> {escape(briefing.get('checkpoint_line', 'Use the next run or linked artifact to confirm whether the recommendation moved.'))}</div>
              <div class="meta-line"><strong>Linked Artifact:</strong> {escape(next_steps.get('linked_artifact', no_linked_artifact_summary()))}</div>
            </div>
            """
        )
    return f"""
    <div class="section">
      <h2>Repo Drilldowns</h2>
      <div class="analyst-grid">
        {''.join(cards) or "<div class='panel'>No repo drilldown content is recorded yet.</div>"}
      </div>
    </div>"""


def _run_changes_section(report_data: dict, diff_data: dict | None) -> str:
    counts = report_data.get("run_change_counts") or build_run_change_counts(diff_data)
    summary = report_data.get("run_change_summary") or build_run_change_summary(diff_data)
    if not summary and not diff_data:
        return ""

    detail_rows = []
    for change in (diff_data or {}).get("repo_changes", [])[:6]:
        detail_rows.append(
            f"<tr><td>{escape(change.get('name', ''))}</td>"
            f"<td class='num'>{change.get('delta', 0.0):+.3f}</td>"
            f"<td>{escape(change.get('old_tier', '—'))} → {escape(change.get('new_tier', '—'))}</td></tr>"
        )
    return f"""
    <div class="section">
      <h2>Run Changes</h2>
        <div class="analyst-grid">
        <div class="panel">
          <div class="meta-line"><strong>Summary:</strong> {escape(summary)}</div>
          <div class="meta-line"><strong>Why It Matters:</strong> {escape(build_queue_pressure_summary(report_data, diff_data))}</div>
          <div class="meta-line"><strong>What To Do Next:</strong> {escape(build_top_recommendation_summary(report_data))}</div>
          <div class="meta-line"><strong>Improving:</strong> {counts.get('score_improvements', 0)} | <strong>Regressing:</strong> {counts.get('score_regressions', 0)}</div>
          <div class="meta-line"><strong>Promotions:</strong> {counts.get('tier_promotions', 0)} | <strong>Demotions:</strong> {counts.get('tier_demotions', 0)}</div>
          <div class="meta-line"><strong>Security / Governance:</strong> {counts.get('security_changes', 0)} / {counts.get('collection_changes', 0)}</div>
        </div>
        <div class="panel">
          <table class="compact-table">
            <thead><tr><th>Repo</th><th>Delta</th><th>Tier Change</th></tr></thead>
            <tbody>{''.join(detail_rows) or f"<tr><td colspan='3'>{escape(no_baseline_summary())}</td></tr>"}</tbody>
          </table>
        </div>
      </div>
    </div>"""


def _compare_section(diff_data: dict | None) -> str:
    if not diff_data:
        return ""

    lens_rows = []
    for lens_name, delta in diff_data.get("lens_deltas", {}).items():
        lens_rows.append(f"<tr><td>{escape(lens_name)}</td><td class='num'>{delta:+.3f}</td></tr>")
    mover_rows = []
    for change in diff_data.get("repo_changes", [])[:8]:
        mover_rows.append(
            f"<tr><td>{escape(change.get('name', ''))}</td>"
            f"<td class='num'>{change.get('delta', 0):+.3f}</td>"
            f"<td>{escape(change.get('old_tier', '—'))} → {escape(change.get('new_tier', '—'))}</td></tr>"
        )
    return f"""
    <div class="section">
      <h2>Compare</h2>
      <div class="analyst-grid">
        <div class="panel">
          <div class="meta-line"><strong>Average score delta:</strong> {diff_data.get('average_score_delta', 0):+.3f}</div>
          <table class="compact-table">
            <thead><tr><th>Lens</th><th>Delta</th></tr></thead>
            <tbody>{''.join(lens_rows) or "<tr><td colspan='2'>No lens changes</td></tr>"}</tbody>
          </table>
        </div>
        <div class="panel">
          <h3>Top Movers</h3>
          <table class="compact-table">
            <thead><tr><th>Repo</th><th>Score Delta</th><th>Tier</th></tr></thead>
            <tbody>{''.join(mover_rows) or "<tr><td colspan='3'>No significant changes</td></tr>"}</tbody>
          </table>
        </div>
      </div>
    </div>"""


def _campaign_section(report_data: dict) -> str:
    summary = report_data.get("campaign_summary", {})
    if not summary:
        return ""
    github_projects = report_data.get("writeback_preview", {}).get("github_projects", {}) or {}
    rows = []
    for item in report_data.get("writeback_preview", {}).get("repos", [])[:10]:
        topic_count = len(item.get("topics", []))
        rows.append(
            f"<tr><td>{escape(item.get('repo', '—'))}</td>"
            f"<td>{escape(item.get('issue_title', '—') or '—')}</td>"
            f"<td class=\"num\">{topic_count}</td>"
            f"<td class=\"num\">{item.get('github_project_field_count', 0)}</td>"
            f"<td class=\"num\">{item.get('notion_action_count', 0)}</td></tr>"
        )
    return f"""
    <div class="section">
      <h2>Campaign</h2>
      <div class="analyst-grid">
        <div class="panel">
          <div class="meta-line"><strong>Campaign:</strong> {escape(summary.get('label', summary.get('campaign_type', '—')))}</div>
          <div class="meta-line"><strong>Actions:</strong> {summary.get('action_count', 0)}</div>
          <div class="meta-line"><strong>Repos:</strong> {summary.get('repo_count', 0)}</div>
          <div class="meta-line"><strong>Sync mode:</strong> {escape(report_data.get('writeback_preview', {}).get('sync_mode', 'reconcile'))}</div>
          <div class="meta-line"><strong>Drift:</strong> {len(report_data.get('managed_state_drift', []) or [])}</div>
          <div class="meta-line"><strong>Action Sync:</strong> {escape(report_data.get('next_action_sync_step', (report_data.get('operator_summary', {}).get('next_action_sync_step') or 'Stay local for now; no current campaign needs preview or apply.')))}</div>
          <div class="meta-line"><strong>GitHub Projects:</strong> {escape(github_projects.get('status', 'disabled'))}
            ({escape(github_projects.get('project_owner', '—'))} #{github_projects.get('project_number', 0)}, {github_projects.get('item_count', 0)} items)</div>
        </div>
        <div class="panel">
          <table class="compact-table">
            <thead><tr><th>Repo</th><th>Managed Issue</th><th>Topics</th><th>Projects</th><th>Notion</th></tr></thead>
            <tbody>{''.join(rows)}</tbody>
          </table>
        </div>
      </div>
    </div>"""


def _writeback_results_section(report_data: dict) -> str:
    writeback = report_data.get("writeback_results", {})
    drift_rows = report_data.get("managed_state_drift", []) or []
    if not writeback.get("results") and not drift_rows:
        return ""
    rows = []
    for result in writeback.get("results", [])[:12]:
        detail = result.get("url") or result.get("status") or "—"
        rows.append(
            f"<tr><td>{escape(result.get('repo_full_name', '—'))}</td>"
            f"<td>{escape(result.get('target', '—'))}</td>"
            f"<td>{escape(result.get('status', '—'))}</td>"
            f"<td>{escape(str(detail))}</td></tr>"
        )
    drift_markup = ""
    if drift_rows:
        drift_markup = f"<div class=\"meta-line\"><strong>Managed drift:</strong> {len(drift_rows)}</div>"
    return f"""
    <div class="section">
      <h2>Writeback Results</h2>
      <div class="meta-line"><strong>Mode:</strong> {escape(writeback.get('mode', 'preview'))} |
      <strong>Target:</strong> {escape(writeback.get('target', 'preview-only'))}</div>
      {drift_markup}
      <table class="compact-table">
        <thead><tr><th>Repo</th><th>Target</th><th>Status</th><th>Details</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>"""


def _scenario_section(analyst_context: dict) -> str:
    preview = analyst_context["scenario_preview"]
    levers = preview.get("top_levers", [])
    projection = preview.get("portfolio_projection", {})
    lever_rows = []
    for lever in levers[:5]:
        lever_rows.append(
            f"<tr><td>{escape(lever.get('title', ''))}</td>"
            f"<td>{escape(lever.get('lens', ''))}</td>"
            f"<td class='num'>{lever.get('repo_count', 0)}</td>"
            f"<td class='num'>{lever.get('average_expected_lens_delta', 0):+.3f}</td></tr>"
        )
    return f"""
    <div class="section">
      <h2>Scenario Preview</h2>
      <div class="analyst-grid">
        <div class="panel">
          <div class="meta-line"><strong>Projected average score delta:</strong> {projection.get('projected_average_score_delta', 0):+.3f}</div>
          <div class="meta-line"><strong>Projected promotions:</strong> {projection.get('projected_tier_promotions', 0)}</div>
          <div class="meta-line"><strong>Selected repos:</strong> {projection.get('selected_repo_count', 0)}</div>
        </div>
        <div class="panel">
          <table class="compact-table">
            <thead><tr><th>Lever</th><th>Lens</th><th>Repos</th><th>Avg Lift</th></tr></thead>
            <tbody>{''.join(lever_rows) or "<tr><td colspan='4'>No scenario data</td></tr>"}</tbody>
          </table>
        </div>
      </div>
    </div>"""


def _governance_section(report_data: dict) -> str:
    governance_summary = report_data.get("governance_summary", {}) or {}
    preview = governance_summary.get("top_actions") or report_data.get("security_governance_preview", [])
    governance_results = report_data.get("governance_results", {}).get("results", [])
    governance_drift = report_data.get("governance_drift", [])
    if not preview and not governance_results and not governance_drift:
        return ""

    rows = []
    for item in preview[:8]:
        rows.append(
            f"<tr><td>{escape(item.get('repo', ''))}</td>"
            f"<td>{escape(item.get('operator_state', item.get('priority', 'medium')))}</td>"
            f"<td>{escape(item.get('title', ''))}</td>"
            f"<td class='num'>{item.get('expected_posture_lift', 0):.2f}</td>"
            f"<td>{escape(item.get('source', ''))}</td></tr>"
        )
    summary = (
        f"<div class=\"meta-line\"><strong>Headline:</strong> {escape(governance_summary.get('headline', 'Governance state is being tracked.'))}</div>"
        f"<div class=\"meta-line\"><strong>Status:</strong> {escape(governance_summary.get('status', 'preview'))}</div>"
        f"<div class=\"meta-line\"><strong>Approved:</strong> {'yes' if report_data.get('governance_approval') else 'no'} | <strong>Needs Re-Approval:</strong> {'yes' if governance_summary.get('needs_reapproval') else 'no'}</div>"
        f"<div class=\"meta-line\"><strong>Drift Count:</strong> {governance_summary.get('drift_count', len(governance_drift))} | <strong>Applied Results:</strong> {governance_summary.get('applied_count', len(governance_results))} | <strong>Rollback Available:</strong> {governance_summary.get('rollback_available_count', 0)}</div>"
    )
    return f"""
    <div class="section">
      <h2>Governance Operator State</h2>
      {summary}
      <table class="compact-table">
        <thead><tr><th>Repo</th><th>State</th><th>Action</th><th>Expected Lift</th><th>Source</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>"""


# ── HTML section builders ─────────────────────────────────────────────
def _tech_radar_section(data: dict, trend_data: list[dict] | None) -> str:
    from src.history import load_language_trends
    trends = load_language_trends()

    if not trends:
        # Fall back to current language distribution
        lang_dist = data.get("language_distribution", {})
        if not lang_dist:
            return ""
        trends = [
            {"language": lang, "current_count": count, "category": "Hold", "repos_per_run": [count]}
            for lang, count in sorted(lang_dist.items(), key=lambda x: x[1], reverse=True)[:15]
        ]

    rows = []
    for t in trends[:20]:
        spark = render_sparkline([float(v) for v in t.get("repos_per_run", [])])
        cat = t.get("category", "Hold")
        color = RADAR_COLORS.get(cat, "#6B7280")
        rows.append(
            f'<tr><td>{escape(t["language"])}</td><td class="num">{t["current_count"]}</td>'
            f'<td class="sparkline">{escape(spark)}</td>'
            f'<td style="color:{color};font-weight:bold">{escape(cat)}</td></tr>'
        )

    return f"""
    <div class="section">
      <h2>Tech Radar</h2>
      <table>
        <thead><tr><th>Language</th><th>Repos</th><th>Trend</th><th>Category</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>"""


# ── Tier distribution bar chart ───────────────────────────────────────
def _distribution_section(data: dict) -> str:
    tiers = data.get("tier_distribution", {})
    total = sum(tiers.values()) or 1

    tier_bars = []
    for tier_name in ["shipped", "functional", "wip", "skeleton", "abandoned"]:
        count = tiers.get(tier_name, 0)
        pct = count / total * 100
        color = TIER_COLORS_CSS.get(tier_name, "#6B7280")
        tier_bars.append(
            f'<div class="bar-row">'
            f'<span class="bar-label">{tier_name.capitalize()}</span>'
            f'<div class="bar-bg"><div class="bar-fill" style="width:{pct:.0f}%;background:{color}"></div></div>'
            f'<span class="bar-count">{count}</span>'
            f'</div>'
        )

    return f"""
    <div class="section">
      <h2>Tier Distribution</h2>
      <div class="bar-chart">{''.join(tier_bars)}</div>
    </div>"""


# ── Portfolio trends section ──────────────────────────────────────────
def _portfolio_trends_section(trend_data: list[dict]) -> str:
    """Render a section showing portfolio score evolution over time."""
    if len(trend_data) < 2:
        return """
    <div class="section">
      <h2>Portfolio Trends</h2>
      <p class="empty-state">Not enough historical data for trends. Run audits over time to see portfolio evolution.</p>
    </div>"""

    first = trend_data[0]
    last = trend_data[-1]
    first_score = first.get("average_score", 0)
    last_score = last.get("average_score", 0)
    delta = last_score - first_score
    delta_sign = "+" if delta >= 0 else ""
    delta_color = "#166534" if delta >= 0 else "#C2410C"

    delta_html = (
        f'<p class="trends-delta">Score trend: '
        f'<strong>{first_score:.3f}</strong> → <strong>{last_score:.3f}</strong> '
        f'(<span style="color:{delta_color};font-weight:bold">{delta_sign}{delta:.3f}</span>)'
        f'</p>'
    )

    # Serialize trend points for the canvas script
    trend_points = json.dumps([
        {"date": t.get("date", ""), "score": round(t.get("average_score", 0), 4)}
        for t in trend_data
    ])

    # Summary table rows
    rows = []
    for t in trend_data:
        dist = t.get("tier_distribution", {})
        rows.append(
            f'<tr>'
            f'<td>{escape(t.get("date", ""))}</td>'
            f'<td class="num">{t.get("average_score", 0):.3f}</td>'
            f'<td class="num">{t.get("repos_audited", 0)}</td>'
            f'<td class="num" style="color:#166534">{dist.get("shipped", 0)}</td>'
            f'<td class="num" style="color:#1565C0">{dist.get("functional", 0)}</td>'
            f'<td class="num" style="color:#D97706">{dist.get("wip", 0)}</td>'
            f'<td class="num" style="color:#C2410C">{dist.get("skeleton", 0)}</td>'
            f'</tr>'
        )

    return f"""
    <div class="section">
      <h2>Portfolio Trends</h2>
      {delta_html}
      <canvas id="trends-chart" width="800" height="300"></canvas>
      <div style="margin-top:24px">
        <table>
          <thead><tr>
            <th>Date</th><th>Avg Score</th><th>Repos Audited</th>
            <th>Shipped</th><th>Functional</th><th>WIP</th><th>Skeleton</th>
          </tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
    </div>
    <script>
    document.addEventListener('DOMContentLoaded', function() {{
      var canvas = document.getElementById('trends-chart');
      if (!canvas) return;
      var ctx = canvas.getContext('2d');
      var W = canvas.width, H = canvas.height;
      var pad = {{top: 24, right: 24, bottom: 48, left: 56}};
      var points = {trend_points};
      if (!points.length) return;

      var scores = points.map(function(p) {{ return p.score; }});
      var minScore = Math.min.apply(null, scores);
      var maxScore = Math.max.apply(null, scores);
      // Give the Y axis a little breathing room
      var yPad = (maxScore - minScore) * 0.15 || 0.05;
      var yMin = Math.max(0, minScore - yPad);
      var yMax = Math.min(1, maxScore + yPad);

      var chartW = W - pad.left - pad.right;
      var chartH = H - pad.top - pad.bottom;

      function toX(i) {{ return pad.left + (i / (points.length - 1)) * chartW; }}
      function toY(v) {{ return pad.top + (1 - (v - yMin) / (yMax - yMin)) * chartH; }}

      // Background
      ctx.fillStyle = 'white';
      ctx.fillRect(0, 0, W, H);

      // Grid lines
      ctx.strokeStyle = '#E2E8F0'; ctx.lineWidth = 1;
      var gridSteps = 5;
      for (var gi = 0; gi <= gridSteps; gi++) {{
        var gv = yMin + (yMax - yMin) * gi / gridSteps;
        var gy = toY(gv);
        ctx.beginPath(); ctx.moveTo(pad.left, gy); ctx.lineTo(W - pad.right, gy); ctx.stroke();
        ctx.fillStyle = '#94A3B8'; ctx.font = '11px sans-serif'; ctx.textAlign = 'right';
        ctx.fillText(gv.toFixed(2), pad.left - 8, gy + 4);
      }}

      // X axis date labels
      ctx.fillStyle = '#94A3B8'; ctx.font = '11px sans-serif'; ctx.textAlign = 'center';
      points.forEach(function(p, i) {{
        var x = toX(i);
        ctx.fillText(p.date, x, H - pad.bottom + 16);
        // Vertical tick
        ctx.strokeStyle = '#E2E8F0'; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(x, pad.top); ctx.lineTo(x, H - pad.bottom); ctx.stroke();
      }});

      // Area fill under the line
      ctx.beginPath();
      ctx.moveTo(toX(0), toY(scores[0]));
      for (var i = 1; i < points.length; i++) {{
        ctx.lineTo(toX(i), toY(scores[i]));
      }}
      ctx.lineTo(toX(points.length - 1), H - pad.bottom);
      ctx.lineTo(toX(0), H - pad.bottom);
      ctx.closePath();
      ctx.fillStyle = 'rgba(14, 165, 233, 0.10)';
      ctx.fill();

      // Line
      ctx.beginPath();
      ctx.moveTo(toX(0), toY(scores[0]));
      for (var i = 1; i < points.length; i++) {{
        ctx.lineTo(toX(i), toY(scores[i]));
      }}
      ctx.strokeStyle = '#0EA5E9'; ctx.lineWidth = 2.5; ctx.lineJoin = 'round';
      ctx.stroke();

      // Dots
      scores.forEach(function(v, i) {{
        ctx.beginPath(); ctx.arc(toX(i), toY(v), 5, 0, Math.PI * 2);
        ctx.fillStyle = '#0EA5E9'; ctx.fill();
        ctx.strokeStyle = 'white'; ctx.lineWidth = 2; ctx.stroke();
      }});

      // Y axis label
      ctx.save();
      ctx.fillStyle = '#64748B'; ctx.font = '12px sans-serif'; ctx.textAlign = 'center';
      ctx.translate(14, pad.top + chartH / 2); ctx.rotate(-Math.PI / 2);
      ctx.fillText('Avg Score', 0, 0);
      ctx.restore();
    }});
    </script>"""


# ── Footer ────────────────────────────────────────────────────────────
def _footer() -> str:
    return """
    <footer>
      <p>Generated by <a href="https://github.com/saagpatel/GithubRepoAuditor">GithubRepoAuditor</a></p>
    </footer>"""


# ── Static assets (CSS + JS) ──────────────────────────────────────────
def _css() -> str:
    return """
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #F8FAFC; color: #1B2A4A; line-height: 1.6; }
    header { background: #1B2A4A; color: white; padding: 24px 32px; }
    header h1 { font-size: 24px; margin-bottom: 4px; }
    header p { color: #94A3B8; font-size: 14px; }
    .kpi-row { display: flex; gap: 16px; padding: 24px 32px; }
    .kpi-card { flex: 1; background: white; border: 1px solid #E2E8F0; border-radius: 8px; padding: 16px; text-align: center; }
    .kpi-label { font-size: 12px; color: #64748B; text-transform: uppercase; letter-spacing: 1px; }
    .kpi-value { font-size: 32px; font-weight: 700; color: #1B2A4A; }
    .lens-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
    .lens-card, .panel { background: white; border: 1px solid #E2E8F0; border-radius: 8px; padding: 16px; }
    .lens-score { font-size: 28px; font-weight: 700; color: #1D4ED8; margin: 8px 0; }
    .lens-text { color: #64748B; font-size: 13px; }
    .analyst-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }
    .meta-line { margin-bottom: 8px; color: #334155; }
    .pill-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
    .pill { display: inline-block; padding: 4px 10px; border-radius: 999px; background: #E0F2FE; color: #075985; font-size: 12px; }
    .bullet-list { margin: 12px 0 0 18px; color: #334155; }
    .bullet-list li { margin-bottom: 6px; }
    .muted { color: #64748B; }
    .compact-table { font-size: 12px; }
    .compact-table th, .compact-table td { padding: 6px 8px; }
    .section { padding: 24px 32px; }
    .section h2 { font-size: 18px; color: #1B2A4A; margin-bottom: 16px; border-bottom: 2px solid #E2E8F0; padding-bottom: 8px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th { background: #1B2A4A; color: white; padding: 8px 12px; text-align: left; font-weight: 600; }
    td { padding: 6px 12px; border-bottom: 1px solid #E2E8F0; }
    tr:nth-child(even) { background: #F8FAFC; }
    tr:hover { background: #EEF2FF; }
    .num { text-align: right; font-variant-numeric: tabular-nums; }
    .desc { color: #64748B; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .sparkline { font-family: 'Courier New', monospace; color: #0EA5E9; letter-spacing: 1px; }
    a { color: #0EA5E9; text-decoration: none; }
    a:hover { text-decoration: underline; }
    .filters { display: flex; gap: 8px; margin-bottom: 12px; }
    .filters select, .filters input { padding: 6px 12px; border: 1px solid #CBD5E1; border-radius: 4px; font-size: 13px; }
    .filters input { flex: 1; }
    canvas { width: 100%; max-width: 800px; border: 1px solid #E2E8F0; border-radius: 8px; background: white; }
    .tooltip { position: absolute; background: #1B2A4A; color: white; padding: 6px 10px; border-radius: 4px; font-size: 12px; pointer-events: none; display: none; z-index: 10; }
    .bar-chart { max-width: 500px; }
    .bar-row { display: flex; align-items: center; margin-bottom: 8px; }
    .bar-label { width: 90px; font-size: 13px; font-weight: 600; }
    .bar-bg { flex: 1; height: 24px; background: #E2E8F0; border-radius: 4px; overflow: hidden; }
    .bar-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
    .bar-count { width: 40px; text-align: right; font-size: 13px; color: #64748B; margin-left: 8px; }
    .empty-state { color: #64748B; font-style: italic; padding: 16px 0; }
    .trends-delta { margin-bottom: 16px; font-size: 14px; color: #1B2A4A; }
    footer { text-align: center; padding: 24px; color: #94A3B8; font-size: 12px; border-top: 1px solid #E2E8F0; margin-top: 32px; }
    @media print {
      .filters { display: none; }
      canvas { display: none; }
      header { background: white; color: #1B2A4A; border-bottom: 2px solid #1B2A4A; }
      header p { color: #64748B; }
      body { font-size: 10pt; }
      .kpi-card { break-inside: avoid; }
      .section { page-break-inside: avoid; }
    }
    """


# ── Data embedding helpers ────────────────────────────────────────────
def _json_script_data(data: dict) -> str:
    """Serialize JSON safely for embedding inside a non-executable script tag."""
    return json.dumps(data).replace("</", "<\\/")


def _safe_href(url: str) -> str:
    """Allow only absolute http(s) URLs in generated anchor tags."""
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return escape(url, quote=True)
    return ""


# ── Embedded JavaScript ───────────────────────────────────────────────
def _js() -> str:
    return """
    const DATA = JSON.parse(document.getElementById('dashboard-data').textContent);
    // Tier colors for scatter chart
    const TIER_COLORS = {shipped:'#166534',functional:'#1565C0',wip:'#D97706',skeleton:'#C2410C',abandoned:'#6B7280'};

    // Scatter chart
    (function() {
      const canvas = document.getElementById('scatter');
      if (!canvas || !DATA.audits.length) return;
      const ctx = canvas.getContext('2d');
      const W = canvas.width, H = canvas.height;
      const pad = 50;

      function draw() {
        ctx.clearRect(0,0,W,H);
        ctx.fillStyle = 'white'; ctx.fillRect(0,0,W,H);

        // Grid
        ctx.strokeStyle = '#E2E8F0'; ctx.lineWidth = 1;
        for (let i = 0; i <= 10; i++) {
          const x = pad + (W-2*pad)*i/10, y = pad + (H-2*pad)*i/10;
          ctx.beginPath(); ctx.moveTo(x, pad); ctx.lineTo(x, H-pad); ctx.stroke();
          ctx.beginPath(); ctx.moveTo(pad, y); ctx.lineTo(W-pad, y); ctx.stroke();
        }

        // Quadrant lines
        ctx.strokeStyle = '#808080'; ctx.lineWidth = 1.5; ctx.setLineDash([6,4]);
        const qx = pad + (W-2*pad)*0.55, qy = pad + (H-2*pad)*(1-0.45);
        ctx.beginPath(); ctx.moveTo(qx, pad); ctx.lineTo(qx, H-pad); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(pad, qy); ctx.lineTo(W-pad, qy); ctx.stroke();
        ctx.setLineDash([]);

        // Axis labels
        ctx.fillStyle = '#64748B'; ctx.font = '12px sans-serif'; ctx.textAlign = 'center';
        ctx.fillText('Completeness', W/2, H-8);
        ctx.save(); ctx.translate(12, H/2); ctx.rotate(-Math.PI/2); ctx.fillText('Interest', 0, 0); ctx.restore();

        // Axis ticks
        ctx.fillStyle = '#94A3B8'; ctx.font = '10px sans-serif';
        for (let i = 0; i <= 10; i += 2) {
          const v = i/10;
          ctx.textAlign = 'center'; ctx.fillText(v.toFixed(1), pad+(W-2*pad)*v, H-pad+16);
          ctx.textAlign = 'right'; ctx.fillText(v.toFixed(1), pad-8, pad+(H-2*pad)*(1-v)+4);
        }

        // Points
        DATA.audits.forEach(a => {
          const x = pad + (W-2*pad)*a.score;
          const y = pad + (H-2*pad)*(1-a.interest);
          ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI*2);
          ctx.fillStyle = TIER_COLORS[a.tier] || '#6B7280';
          ctx.fill();
          ctx.strokeStyle = 'white'; ctx.lineWidth = 1; ctx.stroke();
        });
      }
      draw();

      // Hover tooltip
      const tooltip = document.getElementById('tooltip');
      canvas.addEventListener('mousemove', e => {
        const rect = canvas.getBoundingClientRect();
        const mx = (e.clientX - rect.left) * (W / rect.width);
        const my = (e.clientY - rect.top) * (H / rect.height);
        let found = null;
        DATA.audits.forEach(a => {
          const x = pad + (W-2*pad)*a.score;
          const y = pad + (H-2*pad)*(1-a.interest);
          if (Math.hypot(mx-x, my-y) < 8) found = a;
        });
        if (found) {
          tooltip.style.display = 'block';
          tooltip.style.left = (e.clientX + 12) + 'px';
          tooltip.style.top = (e.clientY - 8) + 'px';
          tooltip.textContent = found.name + ' (score:' + found.score + ' interest:' + found.interest + ')';
        } else {
          tooltip.style.display = 'none';
        }
      });
      canvas.addEventListener('mouseleave', () => { tooltip.style.display = 'none'; });
    })();

    // Table filtering
    function filterTable() {
      const tier = document.getElementById('filter-tier').value;
      const grade = document.getElementById('filter-grade').value;
      const collection = document.getElementById('filter-collection').value;
      const search = document.getElementById('search').value.toLowerCase();
      document.querySelectorAll('#repo-table tbody tr').forEach(row => {
        const show = (tier === 'all' || row.dataset.tier === tier)
          && (grade === 'all' || row.dataset.grade === grade)
          && (collection === 'all' || row.dataset.collections.includes(collection.toLowerCase()))
          && row.dataset.name.toLowerCase().includes(search);
        row.style.display = show ? '' : 'none';
      });
    }

    function sortTable() {
      const mode = document.getElementById('sort-mode').value;
      const tbody = document.querySelector('#repo-table tbody');
      const rows = Array.from(tbody.querySelectorAll('tr'));
      rows.sort((a, b) => parseFloat(b.dataset[mode]) - parseFloat(a.dataset[mode]));
      rows.forEach(row => tbody.appendChild(row));
    }

    // Sortable columns
    document.querySelectorAll('#repo-table th').forEach((th, i) => {
      th.style.cursor = 'pointer';
      th.addEventListener('click', () => {
        const tbody = document.querySelector('#repo-table tbody');
        const rows = Array.from(tbody.querySelectorAll('tr'));
        const asc = th.dataset.sort !== 'asc';
        th.dataset.sort = asc ? 'asc' : 'desc';
        rows.sort((a, b) => {
          const va = a.children[i].textContent, vb = b.children[i].textContent;
          const na = parseFloat(va), nb = parseFloat(vb);
          if (!isNaN(na) && !isNaN(nb)) return asc ? na - nb : nb - na;
          return asc ? va.localeCompare(vb) : vb.localeCompare(va);
        });
        rows.forEach(r => tbody.appendChild(r));
      });
    });

    sortTable();
    """
