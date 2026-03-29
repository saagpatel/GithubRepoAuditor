from __future__ import annotations

import json
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


# ── JSON Report ──────────────────────────────────────────────────────


def write_json_report(report: AuditReport, output_dir: Path) -> Path:
    """Write the full audit report as JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = _file_path(output_dir, "audit-report", report.username, report.generated_at, "json")

    with open(path, "w") as f:
        json.dump(report.to_dict(), f, indent=2)

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
        "tier_distribution": report.tier_distribution,
        "audits": [a.to_dict() for a in report.audits],
        "errors": report.errors,
    }

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

    if report.security_governance_preview:
        _w("### Security Governance Preview")
        _w("")

    if report.campaign_summary:
        _w("### Campaign Summary")
        _w("")
        _w(f"- Campaign: {report.campaign_summary.get('label', report.campaign_summary.get('campaign_type', '—'))}")
        _w(f"- Actions: {report.campaign_summary.get('action_count', 0)}")
        _w(f"- Repos: {report.campaign_summary.get('repo_count', 0)}")
        _w(f"- Mode: {report.writeback_results.get('mode', 'preview')}")
        _w(f"- Target: {report.writeback_results.get('target', 'preview-only')}")
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
        _w("| Repo | Priority | Action | Expected Lift | Source |")
        _w("|------|----------|--------|---------------|--------|")
        for item in report.security_governance_preview[:8]:
            _w(
                f"| {item.get('repo', '—')} | {item.get('priority', '—')} | "
                f"{item.get('title', '—')} | {item.get('expected_posture_lift', 0):.2f} | "
                f"{item.get('source', '—')} |"
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
