from __future__ import annotations

from pathlib import Path

from src.analyst_views import build_analyst_context


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

    _w(f"# Review Pack: {username}")
    _w("")
    _w(f"*Profile:* {context['profile_name']}  ")
    _w(f"*Collection:* {context['collection_name'] or 'all'}  ")
    _w(f"*Generated:* {report_data.get('generated_at', '')[:10]}")
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
        _w("## Next Actions")
        _w("")
        _w(f"- Campaign: {campaign_summary.get('label', campaign_summary.get('campaign_type', '—'))}")
        _w(f"- Actions: {campaign_summary.get('action_count', 0)}")
        _w(f"- Repos: {campaign_summary.get('repo_count', 0)}")
        _w("")
        for item in report_data.get("writeback_preview", {}).get("repos", [])[:8]:
            _w(
                f"- {item.get('repo', '—')}: "
                f"{item.get('issue_title', 'no managed issue')} | "
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

    review_pack_path.write_text("\n".join(lines))
    return {"review_pack_path": review_pack_path}
