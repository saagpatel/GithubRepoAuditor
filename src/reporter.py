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
        "username": report.username,
        "generated_at": report.generated_at.isoformat(),
        "total_repos": report.total_repos,
        "repos_audited": report.repos_audited,
        "average_score": report.average_score,
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


def write_markdown_report(report: AuditReport, output_dir: Path) -> Path:
    """Write human-readable Markdown audit report."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = _file_path(output_dir, "audit-report", report.username, report.generated_at, "md")

    lines: list[str] = []
    _w = lines.append

    # Header
    _w(f"# GitHub Repo Audit: {report.username}")
    _w("")
    _w(f"*Generated: {_date_str(report.generated_at)} | "
       f"Repos audited: {report.repos_audited} / {report.total_repos}*")
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
        _w("| Repo | Score | Language | Flags | Description |")
        _w("|------|-------|----------|-------|-------------|")
        for audit in tier_audits:
            m = audit.metadata
            name_link = f"[{m.name}]({m.html_url})"
            flags = ", ".join(audit.flags) if audit.flags else ""
            desc = _truncate(m.description)
            lang = m.language or "—"
            _w(f"| {name_link} | {audit.overall_score:.2f} | {lang} | {flags} | {desc} |")
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
        _w("")
        _w("</details>")
        _w("")

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
