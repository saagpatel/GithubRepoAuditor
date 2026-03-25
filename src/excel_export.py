from __future__ import annotations

import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, PieChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.series import DataPoint
from openpyxl.formatting.rule import DataBarRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# ── Color palette ────────────────────────────────────────────────────

TIER_COLORS = {
    "shipped": "2E7D32",    # green
    "functional": "1565C0", # blue
    "wip": "F57F17",        # amber
    "skeleton": "BF360C",   # deep orange
    "abandoned": "424242",  # gray
}

TIER_FILLS = {k: PatternFill("solid", fgColor=v) for k, v in TIER_COLORS.items()}

HEADER_FILL = PatternFill("solid", fgColor="1A1A2E")
HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
SUBHEADER_FILL = PatternFill("solid", fgColor="E8EAF6")
SUBHEADER_FONT = Font(bold=True, size=10)

TIER_TEXT_FONT = Font(bold=True, color="FFFFFF", size=10)

THIN_BORDER = Border(
    left=Side(style="thin", color="CCCCCC"),
    right=Side(style="thin", color="CCCCCC"),
    top=Side(style="thin", color="CCCCCC"),
    bottom=Side(style="thin", color="CCCCCC"),
)

PIE_COLORS = ["2E7D32", "1565C0", "F57F17", "BF360C", "424242"]


def _style_header_row(ws, row: int, max_col: int) -> None:
    for col in range(1, max_col + 1):
        cell = ws.cell(row=row, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = THIN_BORDER


def _style_data_cell(ws, row: int, col: int, align: str = "left") -> None:
    cell = ws.cell(row=row, column=col)
    cell.border = THIN_BORDER
    cell.alignment = Alignment(horizontal=align, vertical="center")


def _auto_width(ws, max_col: int, max_row: int) -> None:
    for col in range(1, max_col + 1):
        max_len = 0
        for row in range(1, min(max_row + 1, 200)):
            val = ws.cell(row=row, column=col).value
            if val:
                max_len = max(max_len, len(str(val)))
        ws.column_dimensions[get_column_letter(col)].width = min(max_len + 3, 45)


# ── Sheet builders ───────────────────────────────────────────────────


def _build_overview(wb: Workbook, data: dict) -> None:
    """Sheet 1: Executive overview dashboard."""
    ws = wb.active
    ws.title = "Overview"
    ws.sheet_properties.tabColor = "1A1A2E"

    # Title
    ws.merge_cells("A1:F1")
    title_cell = ws["A1"]
    title_cell.value = f"GitHub Repo Audit: {data['username']}"
    title_cell.font = Font(bold=True, size=16, color="1A1A2E")
    title_cell.alignment = Alignment(horizontal="center")

    ws.merge_cells("A2:F2")
    ws["A2"].value = f"Generated: {data['generated_at'][:10]} | {data['repos_audited']} repos audited"
    ws["A2"].font = Font(size=11, color="666666")
    ws["A2"].alignment = Alignment(horizontal="center")

    # Summary metrics
    row = 4
    metrics = [
        ("Total Repos", data["total_repos"]),
        ("Repos Audited", data["repos_audited"]),
        ("Average Score", f"{data['average_score']:.2f}"),
        ("Errors", len(data.get("errors", []))),
    ]
    ws.cell(row=row, column=1, value="Metric").font = SUBHEADER_FONT
    ws.cell(row=row, column=2, value="Value").font = SUBHEADER_FONT
    ws.cell(row=row, column=1).fill = SUBHEADER_FILL
    ws.cell(row=row, column=2).fill = SUBHEADER_FILL
    for i, (metric, value) in enumerate(metrics, row + 1):
        ws.cell(row=i, column=1, value=metric).border = THIN_BORDER
        ws.cell(row=i, column=2, value=value).border = THIN_BORDER

    # Tier distribution table
    row = 10
    ws.cell(row=row, column=1, value="Tier").font = SUBHEADER_FONT
    ws.cell(row=row, column=2, value="Count").font = SUBHEADER_FONT
    ws.cell(row=row, column=3, value="Percentage").font = SUBHEADER_FONT
    for c in range(1, 4):
        ws.cell(row=row, column=c).fill = SUBHEADER_FILL
    tier_order = ["shipped", "functional", "wip", "skeleton", "abandoned"]
    total = data["repos_audited"]
    for i, tier in enumerate(tier_order, row + 1):
        count = data["tier_distribution"].get(tier, 0)
        pct = count / total * 100 if total else 0
        ws.cell(row=i, column=1, value=tier.capitalize())
        ws.cell(row=i, column=1).fill = TIER_FILLS.get(tier, PatternFill())
        ws.cell(row=i, column=1).font = TIER_TEXT_FONT
        ws.cell(row=i, column=2, value=count)
        ws.cell(row=i, column=3, value=f"{pct:.0f}%")
        for c in range(1, 4):
            ws.cell(row=i, column=c).border = THIN_BORDER

    # Tier pie chart
    pie = PieChart()
    pie.title = "Tier Distribution"
    pie.style = 10
    labels = Reference(ws, min_col=1, min_row=row + 1, max_row=row + 5)
    values = Reference(ws, min_col=2, min_row=row + 1, max_row=row + 5)
    pie.add_data(values, titles_from_data=False)
    pie.set_categories(labels)
    pie.dataLabels = DataLabelList()
    pie.dataLabels.showPercent = True
    pie.dataLabels.showVal = True
    for i, color in enumerate(PIE_COLORS):
        pt = DataPoint(idx=i)
        pt.graphicalProperties.solidFill = color
        pie.series[0].data_points.append(pt)
    pie.width = 16
    pie.height = 12
    ws.add_chart(pie, "E4")

    # Language distribution table
    row = 17
    ws.cell(row=row, column=1, value="Language").font = SUBHEADER_FONT
    ws.cell(row=row, column=2, value="Count").font = SUBHEADER_FONT
    ws.cell(row=row, column=1).fill = SUBHEADER_FILL
    ws.cell(row=row, column=2).fill = SUBHEADER_FILL
    for i, (lang, count) in enumerate(data.get("language_distribution", {}).items(), row + 1):
        ws.cell(row=i, column=1, value=lang).border = THIN_BORDER
        ws.cell(row=i, column=2, value=count).border = THIN_BORDER

    # Language bar chart
    lang_count = len(data.get("language_distribution", {}))
    if lang_count > 0:
        bar = BarChart()
        bar.type = "col"
        bar.title = "Language Distribution"
        bar.style = 10
        bar_data = Reference(ws, min_col=2, min_row=row, max_row=row + lang_count)
        bar_cats = Reference(ws, min_col=1, min_row=row + 1, max_row=row + lang_count)
        bar.add_data(bar_data, titles_from_data=True)
        bar.set_categories(bar_cats)
        bar.shape = 4
        bar.width = 16
        bar.height = 10
        ws.add_chart(bar, "E18")

    _auto_width(ws, 3, 30)


def _build_all_repos(wb: Workbook, data: dict) -> None:
    """Sheet 2: All repos with scores and metadata."""
    ws = wb.create_sheet("All Repos")
    ws.sheet_properties.tabColor = "1565C0"

    headers = [
        "Repo", "Grade", "Tier", "Score", "Interest", "Interest Tier", "Badges",
        "Language", "Private", "Stars", "Forks", "Size (KB)", "Days Since Push",
        "Total Commits", "Test Files", "Dep Count",
        "LOC", "TODO Density", "Flags", "Description",
    ]
    for col, h in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=h)
    _style_header_row(ws, 1, len(headers))

    # Freeze header + repo name column
    ws.freeze_panes = "B2"

    audits = sorted(data["audits"], key=lambda a: a["overall_score"], reverse=True)
    for row, audit in enumerate(audits, 2):
        m = audit["metadata"]
        details = {r["dimension"]: r.get("details", {}) for r in audit["analyzer_results"]}

        badges_str = ", ".join(audit.get("badges", [])[:4]) if audit.get("badges") else ""
        values = [
            m["name"],
            audit.get("grade", "F"),
            audit["completeness_tier"],
            round(audit["overall_score"], 3),
            round(audit.get("interest_score", 0), 3),
            audit.get("interest_tier", "mundane"),
            badges_str,
            m["language"] or "—",
            "Yes" if m["private"] else "No",
            m["stars"],
            m["forks"],
            m["size_kb"],
            details.get("activity", {}).get("days_since_push", "—"),
            details.get("activity", {}).get("total_commits", "—"),
            details.get("testing", {}).get("test_file_count", 0),
            details.get("dependencies", {}).get("dep_count", "—"),
            details.get("code_quality", {}).get("total_loc", 0),
            details.get("code_quality", {}).get("todo_density_per_1k", "—"),
            ", ".join(audit.get("flags", [])),
            (m["description"] or "")[:80],
        ]
        for col, val in enumerate(values, 1):
            ws.cell(row=row, column=col, value=val)
            _style_data_cell(ws, row, col)

        # Color tier cell (column 3 now)
        tier_cell = ws.cell(row=row, column=3)
        tier = audit["completeness_tier"]
        if tier in TIER_FILLS:
            tier_cell.fill = TIER_FILLS[tier]
            tier_cell.font = TIER_TEXT_FONT

    max_row = len(audits) + 1

    # DataBar on Score column (col 4) and Interest column (col 5)
    if max_row > 1:
        score_bar = DataBarRule(start_type='num', start_value=0, end_type='num', end_value=1, color='2E7D32')
        ws.conditional_formatting.add(f'D2:D{max_row}', score_bar)
        interest_bar = DataBarRule(start_type='num', start_value=0, end_type='num', end_value=1, color='1565C0')
        ws.conditional_formatting.add(f'E2:E{max_row}', interest_bar)

    # Summary row
    summary_row = max_row + 2
    ws.cell(row=summary_row, column=1, value="SUMMARY").font = Font(bold=True)
    ws.cell(row=summary_row, column=4, value=f"=AVERAGE(D2:D{max_row})").font = Font(bold=True)
    ws.cell(row=summary_row, column=5, value=f"=AVERAGE(E2:E{max_row})").font = Font(bold=True)

    _auto_width(ws, len(headers), max_row + 2)


def _build_dimension_heatmap(wb: Workbook, data: dict) -> None:
    """Sheet 3: Per-dimension scores as a heatmap grid."""
    ws = wb.create_sheet("Dimension Scores")
    ws.sheet_properties.tabColor = "F57F17"

    dimensions = [
        "readme", "structure", "code_quality", "testing", "cicd",
        "dependencies", "activity", "documentation", "build_readiness",
        "community_profile", "interest",
    ]
    headers = ["Repo", "Tier", "Overall"] + [d.replace("_", " ").title() for d in dimensions]
    for col, h in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=h)
    _style_header_row(ws, 1, len(headers))
    ws.freeze_panes = "B2"

    # Color scale: red (0) -> yellow (0.5) -> green (1.0)
    def _score_fill(score: float) -> PatternFill:
        if score >= 0.8:
            return PatternFill("solid", fgColor="C8E6C9")  # light green
        if score >= 0.6:
            return PatternFill("solid", fgColor="DCEDC8")  # lime
        if score >= 0.4:
            return PatternFill("solid", fgColor="FFF9C4")  # light yellow
        if score >= 0.2:
            return PatternFill("solid", fgColor="FFE0B2")  # light orange
        return PatternFill("solid", fgColor="FFCDD2")      # light red

    audits = sorted(data["audits"], key=lambda a: a["overall_score"], reverse=True)
    for row, audit in enumerate(audits, 2):
        score_map = {r["dimension"]: r["score"] for r in audit["analyzer_results"]}

        ws.cell(row=row, column=1, value=audit["metadata"]["name"]).border = THIN_BORDER
        ws.cell(row=row, column=2, value=audit["completeness_tier"]).border = THIN_BORDER
        if audit["completeness_tier"] in TIER_FILLS:
            ws.cell(row=row, column=2).fill = TIER_FILLS[audit["completeness_tier"]]
            ws.cell(row=row, column=2).font = TIER_TEXT_FONT

        overall = audit["overall_score"]
        cell = ws.cell(row=row, column=3, value=round(overall, 2))
        cell.fill = _score_fill(overall)
        cell.border = THIN_BORDER

        for i, dim in enumerate(dimensions, 4):
            score = score_map.get(dim, 0)
            cell = ws.cell(row=row, column=i, value=round(score, 2))
            cell.fill = _score_fill(score)
            cell.border = THIN_BORDER
            cell.alignment = Alignment(horizontal="center")

    _auto_width(ws, len(headers), len(audits) + 1)


def _build_tier_breakdown(wb: Workbook, data: dict) -> None:
    """Sheet 4: Separate tables per tier with bar charts."""
    ws = wb.create_sheet("Tier Breakdown")
    ws.sheet_properties.tabColor = "2E7D32"

    tier_order = ["shipped", "functional", "wip", "skeleton", "abandoned"]
    audits_by_tier: dict[str, list] = {}
    for a in data["audits"]:
        audits_by_tier.setdefault(a["completeness_tier"], []).append(a)

    current_row = 1
    for tier in tier_order:
        tier_audits = audits_by_tier.get(tier, [])
        if not tier_audits:
            continue

        tier_audits.sort(key=lambda a: a["overall_score"], reverse=True)

        # Tier header
        ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=5)
        header_cell = ws.cell(row=current_row, column=1, value=f"{tier.upper()} ({len(tier_audits)} repos)")
        header_cell.font = Font(bold=True, size=13, color="FFFFFF")
        header_cell.fill = TIER_FILLS.get(tier, PatternFill())
        header_cell.alignment = Alignment(horizontal="center")
        current_row += 1

        # Column headers
        cols = ["Repo", "Score", "Language", "Flags", "Description"]
        for col, h in enumerate(cols, 1):
            ws.cell(row=current_row, column=col, value=h)
        _style_header_row(ws, current_row, len(cols))
        chart_data_start = current_row
        current_row += 1

        for audit in tier_audits:
            m = audit["metadata"]
            ws.cell(row=current_row, column=1, value=m["name"]).border = THIN_BORDER
            ws.cell(row=current_row, column=2, value=round(audit["overall_score"], 2)).border = THIN_BORDER
            ws.cell(row=current_row, column=3, value=m["language"] or "—").border = THIN_BORDER
            ws.cell(row=current_row, column=4, value=", ".join(audit.get("flags", []))).border = THIN_BORDER
            ws.cell(row=current_row, column=5, value=(m["description"] or "")[:60]).border = THIN_BORDER
            current_row += 1

        # Bar chart for this tier
        if len(tier_audits) > 1:
            chart = BarChart()
            chart.type = "bar"
            chart.title = f"{tier.capitalize()} — Scores"
            chart.style = 10
            chart.y_axis.scaling.min = 0
            chart.y_axis.scaling.max = 1
            chart_values = Reference(ws, min_col=2, min_row=chart_data_start + 1, max_row=current_row - 1)
            chart_cats = Reference(ws, min_col=1, min_row=chart_data_start + 1, max_row=current_row - 1)
            chart.add_data(chart_values, titles_from_data=False)
            chart.set_categories(chart_cats)
            chart.series[0].graphicalProperties.solidFill = TIER_COLORS.get(tier, "666666")
            chart.width = 20
            chart.height = max(8, len(tier_audits) * 0.5)
            ws.add_chart(chart, f"G{chart_data_start}")

        current_row += 2  # gap between tiers

    _auto_width(ws, 5, current_row)


def _build_activity_dashboard(wb: Workbook, data: dict) -> None:
    """Sheet 5: Activity-focused view — commits, push recency, LOC."""
    ws = wb.create_sheet("Activity")
    ws.sheet_properties.tabColor = "6A1B9A"

    headers = [
        "Repo", "Days Since Push", "Total Commits", "Recent 3mo Commits",
        "LOC", "Test Files", "Activity Score", "Overall Score", "Tier",
    ]
    for col, h in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=h)
    _style_header_row(ws, 1, len(headers))
    ws.freeze_panes = "B2"

    audits = sorted(
        data["audits"],
        key=lambda a: next(
            (r["details"].get("days_since_push", 9999)
             for r in a["analyzer_results"] if r["dimension"] == "activity"),
            9999,
        ),
    )

    for row, audit in enumerate(audits, 2):
        details = {r["dimension"]: r.get("details", {}) for r in audit["analyzer_results"]}
        scores = {r["dimension"]: r["score"] for r in audit["analyzer_results"]}
        act = details.get("activity", {})
        cq = details.get("code_quality", {})
        test = details.get("testing", {})

        values = [
            audit["metadata"]["name"],
            act.get("days_since_push", "—"),
            act.get("total_commits", "—"),
            act.get("recent_3mo_commits", "—"),
            cq.get("total_loc", 0),
            test.get("test_file_count", 0),
            round(scores.get("activity", 0), 2),
            round(audit["overall_score"], 2),
            audit["completeness_tier"],
        ]
        for col, val in enumerate(values, 1):
            ws.cell(row=row, column=col, value=val)
            _style_data_cell(ws, row, col)

    _auto_width(ws, len(headers), len(audits) + 1)


def _build_reconciliation(wb: Workbook, data: dict) -> None:
    """Sheet 6: Registry reconciliation (only if data present)."""
    recon = data.get("reconciliation")
    if not recon:
        return

    ws = wb.create_sheet("Registry Reconciliation")
    ws.sheet_properties.tabColor = "00695C"

    # Matched projects
    row = 1
    ws.cell(row=row, column=1, value=f"Matched Projects ({len(recon['matched'])})")
    ws.cell(row=row, column=1).font = Font(bold=True, size=13)
    row += 1
    for col, h in enumerate(["GitHub Name", "Registry Name", "Registry Status", "Audit Tier", "Score"], 1):
        ws.cell(row=row, column=col, value=h)
    _style_header_row(ws, row, 5)
    row += 1
    for m in recon["matched"]:
        ws.cell(row=row, column=1, value=m["github_name"]).border = THIN_BORDER
        ws.cell(row=row, column=2, value=m["registry_name"]).border = THIN_BORDER
        ws.cell(row=row, column=3, value=m["registry_status"]).border = THIN_BORDER
        tier_cell = ws.cell(row=row, column=4, value=m["audit_tier"])
        tier_cell.border = THIN_BORDER
        if m["audit_tier"] in TIER_FILLS:
            tier_cell.fill = TIER_FILLS[m["audit_tier"]]
            tier_cell.font = TIER_TEXT_FONT
        ws.cell(row=row, column=5, value=m["score"]).border = THIN_BORDER
        row += 1

    row += 2

    # On GitHub not in registry
    if recon["on_github_not_registry"]:
        ws.cell(row=row, column=1, value=f"On GitHub, NOT in Registry ({len(recon['on_github_not_registry'])})")
        ws.cell(row=row, column=1).font = Font(bold=True, size=12)
        row += 1
        for name in recon["on_github_not_registry"]:
            ws.cell(row=row, column=1, value=name).border = THIN_BORDER
            row += 1
        row += 1

    # In registry not on GitHub
    if recon["in_registry_not_github"]:
        ws.cell(row=row, column=1, value=f"In Registry, NOT on GitHub ({len(recon['in_registry_not_github'])})")
        ws.cell(row=row, column=1).font = Font(bold=True, size=12)
        row += 1
        for name in recon["in_registry_not_github"]:
            ws.cell(row=row, column=1, value=name).border = THIN_BORDER
            row += 1

    _auto_width(ws, 5, row)


# ── Main entry point ─────────────────────────────────────────────────


def _build_quick_wins(wb: Workbook, data: dict) -> None:
    """Sheet 7: Quick Wins — repos closest to the next tier."""
    from src.quick_wins import find_quick_wins
    from src.models import AnalyzerResult, RepoAudit, RepoMetadata

    # Reconstruct audit objects for quick_wins (it needs RepoAudit objects)
    # For simplicity, use the JSON data directly
    ws = wb.create_sheet("Quick Wins")
    ws.sheet_properties.tabColor = "00695C"

    # Build quick wins from raw data
    audits_data = data.get("audits", [])
    wins: list[dict] = []

    tier_thresholds = {"abandoned": 0.15, "skeleton": 0.35, "wip": 0.55, "functional": 0.75, "shipped": 1.01}
    tier_next = {"abandoned": ("skeleton", 0.15), "skeleton": ("wip", 0.35), "wip": ("functional", 0.55), "functional": ("shipped", 0.75)}

    for audit in audits_data:
        current_tier = audit["completeness_tier"]
        if current_tier not in tier_next:
            continue
        next_name, threshold = tier_next[current_tier]
        gap = threshold - audit["overall_score"]
        if gap > 0.15 or gap <= 0:
            continue

        # Find lowest dimensions
        dim_scores = {r["dimension"]: r["score"] for r in audit.get("analyzer_results", [])}
        sorted_dims = sorted(dim_scores.items(), key=lambda x: x[1])
        actions = [f"{d}={s:.1f}" for d, s in sorted_dims[:3]]

        wins.append({
            "name": audit["metadata"]["name"],
            "grade": audit.get("grade", "F"),
            "current_tier": current_tier,
            "score": audit["overall_score"],
            "next_tier": next_name,
            "gap": gap,
            "actions": ", ".join(actions),
            "badges": len(audit.get("badges", [])),
        })

    wins.sort(key=lambda w: w["gap"])

    if not wins:
        ws.cell(row=1, column=1, value="No quick wins found — all repos are either at the top tier or too far from the next one.")
        return

    headers = ["Repo", "Grade", "Current Tier", "Score", "Next Tier", "Gap", "Lowest Dimensions", "Badges"]
    for col, h in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=h)
    _style_header_row(ws, 1, len(headers))

    for row, win in enumerate(wins, 2):
        ws.cell(row=row, column=1, value=win["name"]).border = THIN_BORDER
        ws.cell(row=row, column=2, value=win["grade"]).border = THIN_BORDER
        tier_cell = ws.cell(row=row, column=3, value=win["current_tier"])
        tier_cell.border = THIN_BORDER
        if win["current_tier"] in TIER_FILLS:
            tier_cell.fill = TIER_FILLS[win["current_tier"]]
            tier_cell.font = TIER_TEXT_FONT
        ws.cell(row=row, column=4, value=round(win["score"], 3)).border = THIN_BORDER
        ws.cell(row=row, column=5, value=win["next_tier"]).border = THIN_BORDER
        ws.cell(row=row, column=6, value=round(win["gap"], 3)).border = THIN_BORDER
        ws.cell(row=row, column=7, value=win["actions"]).border = THIN_BORDER
        ws.cell(row=row, column=8, value=win["badges"]).border = THIN_BORDER

    # DataBar on gap column (col 6) — green for small gaps
    max_row = len(wins) + 1
    if max_row > 1:
        gap_bar = DataBarRule(start_type='num', start_value=0, end_type='num', end_value=0.15, color='2E7D32')
        ws.conditional_formatting.add(f'F2:F{max_row}', gap_bar)

    _auto_width(ws, len(headers), max_row)


def export_excel(report_path: Path, output_path: Path) -> Path:
    """Generate a multi-sheet Excel workbook from an audit report JSON."""
    data = json.loads(report_path.read_text())

    wb = Workbook()
    _build_overview(wb, data)
    _build_all_repos(wb, data)
    _build_dimension_heatmap(wb, data)
    _build_quick_wins(wb, data)
    _build_tier_breakdown(wb, data)
    _build_activity_dashboard(wb, data)
    _build_reconciliation(wb, data)

    wb.save(str(output_path))
    return output_path
