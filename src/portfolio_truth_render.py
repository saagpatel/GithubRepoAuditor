from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timezone

from src.portfolio_truth_types import PortfolioTruthProject, PortfolioTruthSnapshot


def render_registry_markdown(snapshot: PortfolioTruthSnapshot) -> str:
    generated_date = snapshot.generated_at.astimezone(timezone.utc).strftime("%Y-%m-%d")
    grouped = _group_projects(snapshot.projects)
    project_labels = registry_project_labels(snapshot.projects)
    lines = [
        "# Project Registry",
        "",
        f"> Master index for Cowork automated tasks. Last generated: {generated_date}.",
        "> This file is generated from the portfolio truth snapshot and remains the compatibility surface for Cowork scheduled tasks.",
        "",
        "## How to Read This Registry",
        "",
        "- **Status**: `active` (touched in last 14 days) · `recent` (touched in last 30 days) · `parked` (30+ days untouched) · `archived` (legacy, no active development planned)",
        "- **Tool**: Primary development tool (`claude-code` · `codex` · `gpt` · `grok` · `claude-ai` · `unknown`)",
        "- **Context Quality**: `full` · `standard` · `minimum-viable` · `boilerplate` · `none`",
        "- **Category Tags**: `commercial` · `it-work` · `vanity` · `fun` · `learning` · `infrastructure`",
        "",
        "---",
        "",
    ]

    standalone = grouped.pop("Standalone Projects", [])
    lines.extend(_render_standalone_section(standalone, project_labels))

    for marker, projects in grouped.items():
        lines.extend(["", "---", ""])
        lines.extend(_render_group_section(marker, projects, project_labels))

    lines.extend(["", "---", ""])
    lines.extend(_render_summary_section(snapshot.projects))
    lines.extend(["", "---", ""])
    lines.extend(_render_cowork_notes())
    return "\n".join(lines) + "\n"


def render_portfolio_report_markdown(
    snapshot: PortfolioTruthSnapshot, latest_json_path: str
) -> str:
    generated = snapshot.generated_at.astimezone(timezone.utc).strftime("%Y-%m-%d")
    grouped = _group_projects(snapshot.projects)
    context_counts = Counter(project.derived.context_quality for project in snapshot.projects)
    registry_counts = Counter(project.derived.registry_status for project in snapshot.projects)
    operating_path_counts = Counter(
        project.declared.operating_path or "unspecified" for project in snapshot.projects
    )
    override_counts = Counter(
        project.derived.path_override
        for project in snapshot.projects
        if project.derived.path_override
    )
    risk_tier_counts = Counter(project.risk.risk_tier for project in snapshot.projects)
    lines = [
        "# Portfolio Audit Report",
        "",
        f"> Generated: {generated} | Projects in truth snapshot: {len(snapshot.projects)}",
        f"> The canonical machine-readable artifact is `{latest_json_path}`. This markdown report is derived from the portfolio truth snapshot for human review.",
        "",
        "---",
        "",
        "## Table of Contents",
        "",
        "1. [Portfolio truth summary](#portfolio-truth-summary)",
        "2. [Audit Methodology](#audit-methodology)",
        "3. [Canonical Portfolio Truth Table](#canonical-portfolio-truth-table)",
        "4. [Coverage Summary](#coverage-summary)",
        "5. [Breakdown by Portfolio Signals](#breakdown-by-portfolio-signals)",
        "6. [Accuracy Findings](#accuracy-findings)",
        "7. [Recommended Next Sync Steps](#recommended-next-sync-steps)",
        "",
        "---",
        "",
        "## Portfolio Truth Summary",
        "",
        f"- Portfolio truth schema: `{snapshot.schema_version}`",
        f"- Workspace root: `{snapshot.workspace_root}`",
        f"- Projects discovered: `{len(snapshot.projects)}`",
        f"- Grouped sections represented: `{len(grouped)}`",
        f"- Canonical source path: `{latest_json_path}`",
        "",
        "## Audit Methodology",
        "",
        "- The truth layer scans the local workspace first, using directory metadata and small allowlisted context files only.",
        "- Declared ownership, lifecycle, review cadence, category, and tool hints come from `portfolio-catalog.yaml` when present.",
        "- Local git recency and safe filesystem timestamps drive the derived activity and compatibility status fields.",
        "- Legacy registry values are treated as migration evidence only; they do not override derived activity or context truth.",
        "- Optional Notion fields are advisory and are not allowed to replace declared lifecycle or owner data.",
        "",
        "## Canonical Portfolio Truth Table",
        "",
        "| Project | Path | Group | Operating Path | Path Status | Lifecycle | Registry Status | Context | Tool | Category | Risk |",
        "|---------|------|-------|----------------|-------------|-----------|-----------------|---------|------|----------|------|",
    ]
    for project in snapshot.projects:
        path_status = project.derived.path_confidence
        if project.derived.path_override:
            path_status = f"{path_status} / {project.derived.path_override}"
        lines.append(
            f"| {project.identity.display_name} | `{project.identity.path}` | {project.identity.section_marker} | "
            f"{project.declared.operating_path or '—'} | {path_status} | "
            f"{project.declared.lifecycle_state or '—'} | {project.derived.registry_status} | "
            f"{project.derived.context_quality} | {project.declared.tool_provenance or 'unknown'} | {project.declared.category or 'unknown'} | {project.risk.risk_tier} |"
        )

    lines.extend(
        [
            "",
            "## Coverage Summary",
            "",
            f"- Context coverage: full `{context_counts.get('full', 0)}`, standard `{context_counts.get('standard', 0)}`, minimum-viable `{context_counts.get('minimum-viable', 0)}`, boilerplate `{context_counts.get('boilerplate', 0)}`, none `{context_counts.get('none', 0)}`",
            f"- Registry status distribution: active `{registry_counts.get('active', 0)}`, recent `{registry_counts.get('recent', 0)}`, parked `{registry_counts.get('parked', 0)}`, archived `{registry_counts.get('archived', 0)}`",
            f"- Operating path distribution: maintain `{operating_path_counts.get('maintain', 0)}`, finish `{operating_path_counts.get('finish', 0)}`, archive `{operating_path_counts.get('archive', 0)}`, experiment `{operating_path_counts.get('experiment', 0)}`, unspecified `{operating_path_counts.get('unspecified', 0)}`",
            f"- Investigate overrides currently surfaced: `{override_counts.get('investigate', 0)}`",
            f"- Risk posture: elevated `{risk_tier_counts.get('elevated', 0)}`, moderate `{risk_tier_counts.get('moderate', 0)}`, baseline `{risk_tier_counts.get('baseline', 0)}`, deferred `{risk_tier_counts.get('deferred', 0)}`",
            f"- Catalog warnings carried into the snapshot: `{len(snapshot.warnings)}`",
            "",
            "## Breakdown by Portfolio Signals",
            "",
        ]
    )
    for marker, projects in grouped.items():
        lines.append(f"### {marker}")
        lines.append("")
        lines.append(
            f"- Projects: `{len(projects)}` | Active `{sum(1 for item in projects if item.derived.registry_status == 'active')}`"
            f" | Recent `{sum(1 for item in projects if item.derived.registry_status == 'recent')}`"
            f" | Parked `{sum(1 for item in projects if item.derived.registry_status == 'parked')}`"
            f" | Archived `{sum(1 for item in projects if item.derived.registry_status == 'archived')}`"
        )
        lines.append(
            f"- Context: full `{sum(1 for item in projects if item.derived.context_quality == 'full')}`, "
            f"standard `{sum(1 for item in projects if item.derived.context_quality == 'standard')}`, "
            f"minimum-viable `{sum(1 for item in projects if item.derived.context_quality == 'minimum-viable')}`, "
            f"boilerplate `{sum(1 for item in projects if item.derived.context_quality == 'boilerplate')}`, "
            f"none `{sum(1 for item in projects if item.derived.context_quality == 'none')}`"
        )
        lines.append(
            f"- Operating paths: maintain `{sum(1 for item in projects if item.declared.operating_path == 'maintain')}`, "
            f"finish `{sum(1 for item in projects if item.declared.operating_path == 'finish')}`, "
            f"archive `{sum(1 for item in projects if item.declared.operating_path == 'archive')}`, "
            f"experiment `{sum(1 for item in projects if item.declared.operating_path == 'experiment')}`, "
            f"investigate override `{sum(1 for item in projects if item.derived.path_override == 'investigate')}`"
        )
        lines.append("")

    lines.extend(
        [
            "## Accuracy Findings",
            "",
        ]
    )
    mismatch_count = 0
    for project in snapshot.projects:
        if (
            project.advisory.legacy_status
            and project.advisory.legacy_status != project.derived.registry_status
        ):
            mismatch_count += 1
            lines.append(
                f"- `{project.identity.display_name}` legacy status `{project.advisory.legacy_status}` differs from derived status `{project.derived.registry_status}`."
            )
    if mismatch_count == 0:
        lines.append(
            "- No legacy status drift was detected between the prior registry evidence and the derived truth snapshot."
        )
    lines.extend(
        [
            "",
            "## Recommended Next Sync Steps",
            "",
            "- Use the canonical truth snapshot as the only machine-readable source for future portfolio consumers.",
            "- Keep `project-registry.md` and `PORTFOLIO-AUDIT-REPORT.md` generated from that truth snapshot rather than editing them directly.",
            "- Treat operating paths as normalized contract data from the truth layer rather than letting renderers infer path meaning locally.",
            "- Use catalog repo rules and group/path defaults to fill missing declared lifecycle and ownership data before future operating-path guidance expands.",
        ]
    )
    return "\n".join(lines) + "\n"


def _group_projects(
    projects: list[PortfolioTruthProject],
) -> dict[str, list[PortfolioTruthProject]]:
    grouped: dict[str, list[PortfolioTruthProject]] = defaultdict(list)
    for project in projects:
        grouped[project.identity.section_marker].append(project)
    ordered = dict(
        sorted(
            grouped.items(), key=lambda item: (item[0] != "Standalone Projects", item[0].lower())
        )
    )
    for marker, members in ordered.items():
        members.sort(key=lambda item: item.identity.display_name.lower())
    return ordered


def registry_project_labels(projects: list[PortfolioTruthProject]) -> dict[str, str]:
    duplicate_names = Counter(project.identity.display_name.strip() for project in projects)
    labels: dict[str, str] = {}
    for project in projects:
        display_name = project.identity.display_name.strip()
        label = display_name
        if duplicate_names[display_name] > 1:
            label = f"{display_name} [{project.identity.path}]"
        labels[project.identity.project_key] = label
    return labels


def _render_standalone_section(
    projects: list[PortfolioTruthProject],
    project_labels: dict[str, str],
) -> list[str]:
    lines = [
        "## Standalone Projects (Root Level)",
        "",
        "| Project | Status | Tool | Context Quality | Stack | Context Files | Category | Notes |",
        "|---------|--------|------|-----------------|-------|---------------|----------|-------|",
    ]
    for project in projects:
        lines.append(
            f"| {project_labels[project.identity.project_key]} | {project.derived.registry_status} | {project.declared.tool_provenance or 'unknown'} | "
            f"{project.derived.context_quality} | {', '.join(project.derived.stack) or 'Unknown'} | "
            f"{', '.join(project.derived.context_files) or '—'} | {project.declared.category or 'unknown'} | {_note_text(project)} |"
        )
    return lines


def _render_group_section(
    marker: str,
    projects: list[PortfolioTruthProject],
    project_labels: dict[str, str],
) -> list[str]:
    count = len(projects)
    title = marker if marker.endswith("Projects") or marker.endswith("/") else f"{marker}"
    if marker.startswith("ITPRJsViaClaude/"):
        lines = [
            f"## {title} (IT Tools — {count} projects)",
            "",
            "| Project | Status | Tool | Context Quality | Context Files | Notes |",
            "|---------|--------|------|-----------------|---------------|-------|",
        ]
        for project in projects:
            lines.append(
                f"| {project_labels[project.identity.project_key]} | {project.derived.registry_status} | {project.declared.tool_provenance or 'unknown'} | "
                f"{project.derived.context_quality} | {', '.join(project.derived.context_files) or '—'} | {_note_text(project)} |"
            )
        return lines

    section_note = _default_section_note(marker, projects)
    lines = [f"## {title} ({count} projects)", ""]
    if section_note:
        lines.extend([f"> {section_note}", ""])
    lines.extend(
        [
            "| Project | Status | Tool | Context Quality | Notes |",
            "|---------|--------|------|-----------------|-------|",
        ]
    )
    for project in projects:
        lines.append(
            f"| {project_labels[project.identity.project_key]} | {project.derived.registry_status} | {project.declared.tool_provenance or 'unknown'} | "
            f"{project.derived.context_quality} | {_note_text(project)} |"
        )
    return lines


def _default_section_note(marker: str, projects: list[PortfolioTruthProject]) -> str:
    if marker == "Fun:GamePrjs/":
        return "Most projects in this category still rely on boilerplate-only context and need deeper recovery work before they become reliable execution targets."
    if marker == "GrokPRJs/":
        return "Legacy Grok-built projects remain derived compatibility entries here; most still look archival rather than active."
    if marker == "MoneyPRJsViaGPT/":
        return "Legacy GPT-built projects remain represented for truth completeness, but most still read as archival rather than active."
    if marker == "iOS Projects":
        return "Swift and SwiftUI projects are kept visible here so Phase 104 can target their context gaps deliberately."
    if marker == "FunGamePrjs/":
        return "This staging section still exists as a compatibility view for build-ready game variants."
    return ""


def _note_text(project: PortfolioTruthProject) -> str:
    note_parts = []
    if project.declared.purpose:
        note_parts.append(project.declared.purpose)
    if project.declared.notes:
        note_parts.append(project.declared.notes)
    if not note_parts and project.warnings:
        note_parts.append(project.warnings[0])
    return " ".join(note_parts) or "—"


def _render_summary_section(projects: list[PortfolioTruthProject]) -> list[str]:
    total = len(projects)
    status_counts = Counter(project.derived.registry_status for project in projects)
    context_counts = Counter(project.derived.context_quality for project in projects)
    return [
        "## Portfolio Summary",
        "",
        "| Metric | Count |",
        "|--------|-------|",
        f"| Total projects | {total} |",
        f"| Active (touched last 14 days) | {status_counts.get('active', 0)} |",
        f"| Recent (touched last 30 days) | {status_counts.get('recent', 0)} |",
        f"| Parked (30+ days) | {status_counts.get('parked', 0)} |",
        f"| Archived (legacy, no plans) | {status_counts.get('archived', 0)} |",
        f"| Projects with full context | {context_counts.get('full', 0)} |",
        f"| Projects with standard context | {context_counts.get('standard', 0)} |",
        f"| Projects with minimum-viable context | {context_counts.get('minimum-viable', 0)} |",
        f"| Projects with boilerplate only | {context_counts.get('boilerplate', 0)} |",
        f"| Projects with no context | {context_counts.get('none', 0)} |",
    ]


def _render_cowork_notes() -> list[str]:
    return [
        "## Cowork Task Notes",
        "",
        "### For Accountability System",
        "- Scan git log recency across all non-archived projects to update status column.",
        "- Flag projects that have drifted from `active` or `recent` into `parked` since the last generated truth snapshot.",
        "- Compare current activity against stated portfolio intent when a catalog contract exists.",
        "",
        "### For Pre-Session Prep Briefs",
        "- Prefer briefs for projects with `full` or `standard` context quality; `minimum-viable` is planning-usable but still lower-confidence.",
        "- Prefer projects whose registry status is `active` or `recent` unless the weekly focus explicitly overrides that default.",
        "",
        "### For Session Planning Queue",
        "- Use the generated registry for compatibility only; treat the canonical truth snapshot JSON as the deeper machine-readable source.",
        "- Escalate projects that are active or recent but still have `boilerplate` or `none` context quality.",
        "- Treat `minimum-viable` as the floor for resumable work, not the end-state for deep handoff quality.",
    ]
