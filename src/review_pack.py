from __future__ import annotations

from pathlib import Path

from src.analyst_views import build_analyst_context
from src.report_enrichment import build_weekly_review_pack


def export_review_pack(
    report_data: dict,
    output_dir: Path,
    *,
    diff_data: dict | None = None,
    portfolio_profile: str = "default",
    collection: str | None = None,
) -> dict:
    """Write a concise analyst-facing markdown review pack."""
    context = build_analyst_context(
        report_data,
        profile_name=portfolio_profile,
        collection_name=collection,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    date = report_data.get("generated_at", "")[:10]
    username = report_data.get("username", "unknown")
    review_pack_path = output_dir / f"review-pack-{username}-{date}.md"

    lines: list[str] = []
    _w = lines.append
    weekly_pack = build_weekly_review_pack(report_data, diff_data)

    _w(f"# Review Pack: {username}")
    _w("")
    _w(f"*Profile:* {context['profile_name']}  ")
    _w(f"*Collection:* {context['collection_name'] or 'all'}  ")
    _w(f"*Generated:* {report_data.get('generated_at', '')[:10]}")
    _w("")

    _w("## Weekly Review Pack")
    _w("")
    _w(f"- Portfolio Headline: {weekly_pack.get('portfolio_headline', 'No weekly headline is recorded yet.')}")
    _w(f"- Run Changes: {weekly_pack.get('run_change_summary', 'No run-change summary is recorded yet.')}")
    _w(f"- Queue Pressure: {weekly_pack.get('queue_pressure_summary', 'No queue-pressure summary is recorded yet.')}")
    _w(f"- Trust / Actionability: {weekly_pack.get('trust_actionability_summary', 'No trust summary is recorded yet.')}")
    _w(f"- What To Do This Week: {weekly_pack.get('what_to_do_this_week', 'Continue the normal operator review loop.')}")
    _w(f"- Portfolio Catalog: {weekly_pack.get('portfolio_catalog_summary', 'No portfolio catalog contract is recorded yet.')}")
    _w(f"- Intent Alignment: {weekly_pack.get('intent_alignment_summary', 'Intent alignment cannot be judged until a portfolio catalog contract exists.')}")
    _w(f"- Scorecards: {weekly_pack.get('scorecards_summary', 'No maturity scorecard is recorded yet.')}")
    _w("")
    _w("### Top Attention")
    _w("")
    for item in weekly_pack.get("top_attention", [])[:5]:
        _w(f"- [{item.get('lane', 'ready')}] {item.get('repo', 'Portfolio')}: {item.get('title', 'Operator attention item')}")
        _w(f"  Why: {item.get('why', 'Operator pressure is active.')}")
        _w(f"  Action: {item.get('next_step', 'Review the latest state.')}")
        _w(f"  Operator Focus: {item.get('operator_focus_line', 'Watch Closely: No operator focus bucket is currently surfaced.')}")
        _w(f"  Catalog: {item.get('catalog_line', 'No portfolio catalog contract is recorded yet.')}")
        _w(f"  Intent Alignment: {item.get('intent_alignment', 'missing-contract')} — {item.get('intent_alignment_summary', 'Intent alignment cannot be judged until a portfolio catalog contract exists.')}")
        _w(f"  {item.get('scorecard_line', 'Scorecard: No maturity scorecard is recorded yet.')}")
        _w(f"  Maturity Gap: {item.get('maturity_gap_summary', 'No maturity gap summary is recorded yet.')}")
        _w(f"  Checkpoint Timing: {item.get('follow_through_checkpoint_timing', 'Unknown')}")
        _w(f"  Next Checkpoint: {item.get('follow_through_checkpoint', 'Use the next run or linked artifact to confirm whether the recommendation moved.')}")
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
        _w(f"- {briefing.get('headline', briefing.get('repo', 'Repo briefing'))}")
        _w(f"  Current State: {briefing.get('current_state_line', 'No current-state summary is recorded yet.')}")
        _w(f"  What Changed: {briefing.get('what_changed_line', 'No change summary is recorded yet.')}")
        _w(f"  Why It Matters: {briefing.get('why_it_matters_line', 'No explanation summary is recorded yet.')}")
        _w(f"  What To Do Next: {briefing.get('what_to_do_next_line', 'No next action is recorded yet.')}")
        _w(f"  Operator Focus: {briefing.get('operator_focus_line', 'Watch Closely: No operator focus bucket is currently surfaced.')}")
        _w(f"  Catalog: {briefing.get('catalog_line', 'No portfolio catalog contract is recorded yet.')}")
        _w(f"  Intent Alignment: {briefing.get('intent_alignment_line', 'missing-contract: Intent alignment cannot be judged until a portfolio catalog contract exists.')}")
        _w(f"  {briefing.get('scorecard_line', 'Scorecard: No maturity scorecard is recorded yet.')}")
        _w(f"  Maturity Gap: {briefing.get('maturity_gap_summary', 'No maturity gap summary is recorded yet.')}")
        _w(f"  Checkpoint Timing: {briefing.get('checkpoint_timing_line', 'Unknown')}")
        _w(f"  What Would Count As Progress: {briefing.get('checkpoint_line', 'Use the next run or linked artifact to confirm whether the recommendation moved.')}")
    _w("")

    operator_summary = report_data.get("operator_summary", {})
    operator_queue = report_data.get("operator_queue", [])
    if operator_summary or operator_queue:
        _w("## Operator Control Center")
        _w("")
        _w(f"- Headline: {operator_summary.get('headline', 'No operator triage items are currently surfaced.')}")
        if operator_summary.get("source_run_id"):
            _w(f"- Source Run: `{operator_summary.get('source_run_id')}`")
        counts = operator_summary.get("counts", {})
        _w(
            f"- Blocked: {counts.get('blocked', 0)} | Urgent: {counts.get('urgent', 0)} | "
            f"Ready: {counts.get('ready', 0)} | Deferred: {counts.get('deferred', 0)}"
        )
        for item in operator_queue[:8]:
            repo = f"{item.get('repo', '')}: " if item.get("repo") else ""
            _w(f"- [{item.get('lane_label', item.get('lane', 'ready'))}] {repo}{item.get('title', 'Triage item')}")
            _w(f"  Why: {item.get('lane_reason', item.get('summary', 'Operator triage item.'))}")
            _w(f"  Action: {item.get('recommended_action', 'Review the latest state.')}")
        recent_changes = operator_summary.get("operator_recent_changes", [])
        for change in recent_changes[:3]:
            subject = change.get("repo") or change.get("repo_full_name") or change.get("item_id") or "portfolio"
            _w(f"- Recent: {change.get('generated_at', '')[:10]} {subject} — {change.get('summary', change.get('kind', 'change'))}")
        _w("")

    _w("## Snapshot")
    _w("")
    _w(f"- Avg score: {report_data.get('average_score', 0):.2f}")
    _w(f"- Portfolio grade: {report_data.get('portfolio_grade', 'F')}")
    _w(f"- Repos audited: {report_data.get('repos_audited', 0)}")
    _w("")

    _w("## Profile Leaders")
    _w("")
    for item in context["profile_leaderboard"].get("leaders", []):
        _w(
            f"- {item['name']} — profile {item['profile_score']:.3f}, "
            f"overall {item['overall_score']:.3f}, {item['tier']}"
        )
    _w("")

    _w("## Collections")
    _w("")
    for item in context["collection_summary"]:
        _w(f"- {item['name']} ({item['count']}): {', '.join(item['repos']) or '—'}")
    _w("")

    security = report_data.get("security_posture", {})
    if security:
        _w("## Security")
        _w("")
        _w(f"- Average posture score: {security.get('average_score', 0):.2f}")
        _w(f"- Critical repos: {', '.join(security.get('critical_repos', [])[:5]) or '—'}")
        provider_coverage = security.get("provider_coverage", {})
        if provider_coverage:
            _w(
                f"- GitHub coverage: {provider_coverage.get('github', {}).get('available_repos', 0)}/"
                f"{provider_coverage.get('github', {}).get('total_repos', 0)}"
            )
            _w(
                f"- Scorecard coverage: {provider_coverage.get('scorecard', {}).get('available_repos', 0)}/"
                f"{provider_coverage.get('scorecard', {}).get('total_repos', 0)}"
            )
        _w("")

    if diff_data:
        _w("## Compare")
        _w("")
        _w(f"- Average score delta: {diff_data.get('average_score_delta', 0):+.3f}")
        for change in diff_data.get("repo_changes", [])[:5]:
            _w(
                f"- {change.get('name', '—')}: {change.get('delta', 0):+.3f} "
                f"({change.get('old_tier', '—')} → {change.get('new_tier', '—')})"
            )
        _w("")

    preview = context["scenario_preview"]
    _w("## Scenario Preview")
    _w("")
    for lever in preview.get("top_levers", []):
        _w(
            f"- {lever.get('title', '—')}: {lever.get('repo_count', 0)} repos, "
            f"avg lift {lever.get('average_expected_lens_delta', 0):.3f}, "
            f"promotions {lever.get('projected_tier_promotions', 0)}"
        )
    projection = preview.get("portfolio_projection", {})
    if projection:
        _w("")
        _w(f"- Selected repos: {projection.get('selected_repo_count', 0)}")
        _w(f"- Projected average score delta: {projection.get('projected_average_score_delta', 0):+.3f}")
        _w(f"- Projected tier promotions: {projection.get('projected_tier_promotions', 0)}")
    _w("")

    governance_preview = report_data.get("security_governance_preview", [])
    if governance_preview:
        _w("## Security Governance Preview")
        _w("")
        for item in governance_preview[:8]:
            _w(
                f"- {item.get('repo', '—')}: {item.get('title', 'Action')} "
                f"({item.get('priority', 'medium')}, lift {item.get('expected_posture_lift', 0):.2f}, source {item.get('source', 'merged')})"
            )
        _w("")

    campaign_summary = report_data.get("campaign_summary", {})
    if campaign_summary:
        github_projects = report_data.get("writeback_preview", {}).get("github_projects", {}) or {}
        _w("## Next Actions")
        _w("")
        _w(f"- Campaign: {campaign_summary.get('label', campaign_summary.get('campaign_type', '—'))}")
        _w(f"- Actions: {campaign_summary.get('action_count', 0)}")
        _w(f"- Repos: {campaign_summary.get('repo_count', 0)}")
        _w(f"- Sync Mode: {report_data.get('writeback_preview', {}).get('sync_mode', 'reconcile')}")
        if github_projects.get("enabled"):
            _w(
                f"- GitHub Projects: {github_projects.get('status', 'disabled')} "
                f"({github_projects.get('project_owner', '—')} #{github_projects.get('project_number', 0)}, "
                f"{github_projects.get('item_count', 0)} items)"
            )
        _w("")
        for item in report_data.get("writeback_preview", {}).get("repos", [])[:8]:
            _w(
                f"- {item.get('repo', '—')}: "
                f"{item.get('issue_title', 'no managed issue')} | "
                f"{item.get('github_project_field_count', 0)} project fields | "
                f"{len(item.get('topics', []))} managed topics | "
                f"{item.get('notion_action_count', 0)} Notion actions"
            )
        _w("")

    writeback_results = report_data.get("writeback_results", {})
    if writeback_results.get("results"):
        _w("## Writeback Results")
        _w("")
        _w(
            f"- Mode: {writeback_results.get('mode', 'preview')} | "
            f"Target: {writeback_results.get('target', 'preview-only')}"
        )
        for result in writeback_results.get("results", [])[:10]:
            _w(
                f"- {result.get('repo_full_name', '—')}: "
                f"{result.get('target', '—')} -> {result.get('status', '—')}"
            )
        _w("")

    if report_data.get("managed_state_drift"):
        _w("## Managed Drift")
        _w("")
        for item in report_data.get("managed_state_drift", [])[:8]:
            _w(
                f"- {item.get('repo_full_name', '—')}: "
                f"{item.get('target', '—')} -> {item.get('drift_state', 'drifted')}"
            )
        _w("")

    if report_data.get("governance_results", {}).get("results") or report_data.get("governance_drift"):
        _w("## Governance Operator State")
        _w("")
        governance_summary = report_data.get("governance_summary", {})
        _w(f"- Headline: {governance_summary.get('headline', 'Governance state is being tracked.')}")
        _w(f"- Status: {governance_summary.get('status', 'preview')}")
        _w(f"- Approved: {'yes' if report_data.get('governance_approval') else 'no'}")
        _w(f"- Needs Re-Approval: {'yes' if governance_summary.get('needs_reapproval') else 'no'}")
        _w(f"- Drift Count: {governance_summary.get('drift_count', len(report_data.get('governance_drift', []) or []))}")
        _w(f"- Applied Count: {governance_summary.get('applied_count', len(report_data.get('governance_results', {}).get('results', []) or []))}")
        for item in governance_summary.get("top_actions", [])[:4]:
            _w(f"- {item.get('repo', '—')}: {item.get('title', 'Governed control')} [{item.get('operator_state', 'preview')}]")
        _w("")

    review_pack_path.write_text("\n".join(lines))
    return {"review_pack_path": review_pack_path}
