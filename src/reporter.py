from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from src.models import AuditReport, RepoAudit

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
        if report.operator_summary.get("trend_summary"):
            _w(f"- Trend: {report.operator_summary.get('trend_summary')}")
        if report.operator_summary.get("accountability_summary"):
            _w(f"- Accountability: {report.operator_summary.get('accountability_summary')}")
        if report.operator_summary.get("follow_through_summary"):
            _w(f"- Follow-Through: {report.operator_summary.get('follow_through_summary')}")
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
        if report.operator_summary.get("recommendation_drift_status"):
            _w(
                f"- Recommendation Drift: {report.operator_summary.get('recommendation_drift_status')} "
                f"({report.operator_summary.get('recommendation_drift_summary', 'No recommendation-drift summary is recorded yet.')})"
            )
        if report.operator_summary.get("exception_pattern_summary"):
            _w(f"- Exception Pattern Summary: {report.operator_summary.get('exception_pattern_summary')}")
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
        for item in report.operator_queue[:6]:
            repo = f"{item.get('repo')}: " if item.get("repo") else ""
            _w(f"- [{item.get('lane_label', item.get('lane', 'ready'))}] {repo}{item.get('title', 'Triage item')}")
            _w(f"  - Why: {item.get('summary', 'No summary available.')}")
            _w(f"  - Lane Reason: {item.get('lane_reason', 'Operator triage')}")
            _w(f"  - Next: {item.get('recommended_action', 'Review the latest state.')}")
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
        _w("### Campaign Summary")
        _w("")
        _w(f"- Campaign: {report.campaign_summary.get('label', report.campaign_summary.get('campaign_type', '—'))}")
        _w(f"- Actions: {report.campaign_summary.get('action_count', 0)}")
        _w(f"- Repos: {report.campaign_summary.get('repo_count', 0)}")
        _w(f"- Mode: {report.writeback_results.get('mode', 'preview')}")
        _w(f"- Target: {report.writeback_results.get('target', 'preview-only')}")
        _w(f"- Sync Mode: {report.writeback_preview.get('sync_mode', 'reconcile')}")
        _w("")

    if report.writeback_preview.get("repos"):
        _w("### Next Actions")
        _w("")
        _w("| Repo | Topics | Issue | Notion Actions |")
        _w("|------|--------|-------|----------------|")
        for item in report.writeback_preview.get("repos", [])[:8]:
            topics = ", ".join(item.get("topics", [])[:4]) or "—"
            _w(
                f"| {item.get('repo', '—')} | {topics} | "
                f"{item.get('issue_title', '—') or '—'} | {item.get('notion_action_count', 0)} |"
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
        _w(f"<details>")
        _w(f"<summary>{m.name} — {audit.overall_score:.2f} ({audit.completeness_tier})</summary>")
        _w("")
        _w("| Dimension | Score | Key Findings |")
        _w("|-----------|-------|-------------|")
        for r in audit.analyzer_results:
            findings = ", ".join(r.findings[:2]) if r.findings else "—"
            _w(f"| {r.dimension} | {r.score:.2f} | {findings} |")
        _w("")
        _w(f"**URL:** {m.html_url}  ")
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
