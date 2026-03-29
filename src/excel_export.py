"""Flagship Excel dashboard generator.

Produces a 10-sheet workbook that serves as the primary way to understand
the portfolio: KPI dashboard, master table, heatmap, quick wins, badges,
tech stack, trends, tier breakdown, activity, and registry reconciliation.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, PieChart, Reference, ScatterChart
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.series import DataPoint
from openpyxl.drawing.line import LineProperties
from openpyxl.formatting.rule import ColorScaleRule, DataBarRule
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from src.sparkline import sparkline as render_sparkline

from src.excel_styles import (
    CENTER,
    GRADE_COLORS,
    HEATMAP_AMBER,
    HEATMAP_GREEN,
    HEATMAP_RED,
    NAVY,
    PATTERN_COLORS,
    SECTION_FONT,
    SLATE,
    SUBHEADER_FILL,
    SUBHEADER_FONT,
    SUBTITLE_FONT,
    TEAL,
    THIN_BORDER,
    TIER_FILLS,
    TITLE_FONT,
    WRAP,
    WHITE,
    NARRATIVE_FONT,
    SPARKLINE_FONT,
    apply_zebra_stripes,
    auto_width,
    color_grade_cell,
    color_pattern_cell,
    color_tier_cell,
    style_data_cell,
    style_header_row,
    write_kpi_card,
)

# Tier display order
TIER_ORDER = ["shipped", "functional", "wip", "skeleton", "abandoned"]
PIE_COLORS = ["166534", "1565C0", "D97706", "C2410C", "6B7280"]


# ═══════════════════════════════════════════════════════════════════════
# Sheet 1: Dashboard (Executive Overview)
# ═══════════════════════════════════════════════════════════════════════


def _generate_narrative(data: dict, diff_data: dict | None) -> str:
    """Auto-generate a one-line dashboard narrative."""
    if not diff_data:
        tiers = data.get("tier_distribution", {})
        return (
            f"Portfolio: {data['repos_audited']} repos analyzed. "
            f"{tiers.get('shipped', 0)} shipped, avg score {data['average_score']:.2f}."
        )

    parts = [f"Since last audit ({diff_data.get('previous_date', '')[:10]}):"]
    shipped_d = diff_data.get("tier_distribution_delta", {}).get("shipped", 0)
    avg_d = diff_data.get("average_score_delta", 0)
    promos = len(diff_data.get("tier_changes", []))
    new_count = len(diff_data.get("new_repos", []))

    if shipped_d:
        parts.append(f"{shipped_d:+d} shipped")
    if abs(avg_d) > 0.005:
        parts.append(f"avg score {avg_d:+.3f}")
    if promos:
        parts.append(f"{promos} tier changes")
    if new_count:
        parts.append(f"{new_count} new repos")

    # Find closest promotion
    tier_next = {"functional": 0.75, "wip": 0.55, "skeleton": 0.35}
    closest_name, closest_gap = None, 1.0
    for a in data.get("audits", []):
        tier = a.get("completeness_tier", "")
        if tier in tier_next:
            gap = tier_next[tier] - a.get("overall_score", 0)
            if 0 < gap < closest_gap:
                closest_gap = gap
                closest_name = a["metadata"]["name"]
    if closest_name:
        parts.append(f"Priority: {closest_name} needs {closest_gap:.3f} to promote")

    return " | ".join(parts)


def _build_dashboard(wb: Workbook, data: dict, diff_data: dict | None = None, score_history: dict[str, list[float]] | None = None) -> None:
    ws = wb.active
    ws.title = "Dashboard"
    ws.sheet_properties.tabColor = NAVY

    # Title
    ws.merge_cells("A1:L1")
    c = ws["A1"]
    c.value = f"GitHub Portfolio Dashboard: {data['username']}"
    c.font = TITLE_FONT
    c.alignment = CENTER

    ws.merge_cells("A2:L2")
    c = ws["A2"]
    c.value = f"Generated: {data['generated_at'][:10]} | {data['repos_audited']} repos audited"
    c.font = SUBTITLE_FONT
    c.alignment = CENTER

    # Narrative row
    ws.merge_cells("A3:L3")
    c = ws["A3"]
    c.value = _generate_narrative(data, diff_data)
    c.font = NARRATIVE_FONT
    c.alignment = WRAP
    ws.row_dimensions[3].height = 30

    # KPI Cards (row 5-6)
    grade = data.get("portfolio_grade", "?")
    grade_color = GRADE_COLORS.get(grade, NAVY)
    write_kpi_card(ws, 5, 1, "Portfolio Grade", grade, grade_color)
    write_kpi_card(ws, 5, 3, "Avg Score", f"{data['average_score']:.2f}")
    tiers = data.get("tier_distribution", {})
    write_kpi_card(ws, 5, 5, "Shipped", tiers.get("shipped", 0), "166534", "#Tier Breakdown!A1")
    write_kpi_card(ws, 5, 7, "Functional", tiers.get("functional", 0), "1565C0", "#Tier Breakdown!A1")
    write_kpi_card(ws, 5, 9, "WIP", tiers.get("wip", 0), "D97706", "#Quick Wins!A1")
    skel_aband = tiers.get("skeleton", 0) + tiers.get("abandoned", 0)
    write_kpi_card(ws, 5, 11, "Needs Work", skel_aband, "C2410C")

    # Row height
    ws.row_dimensions[5].height = 20
    ws.row_dimensions[6].height = 40

    # Portfolio score sparkline (row 7, next to KPI cards)
    if score_history:
        from src.history import load_trend_data as _load_trends
        avg_scores = [t.get("average_score", 0) for t in (_load_trends() or [])]
        spark = render_sparkline(avg_scores)
        if spark:
            cell = ws.cell(row=7, column=3, value=f"Trend: {spark}")
            cell.font = SPARKLINE_FONT

    # Portfolio DNA row (row 8) — one colored cell per repo
    dna_row = 8
    ws.cell(row=dna_row, column=1, value="Portfolio DNA").font = SUBHEADER_FONT
    audits_sorted = sorted(data.get("audits", []), key=lambda a: a.get("overall_score", 0), reverse=True)
    for i, audit in enumerate(audits_sorted[:120]):
        cell = ws.cell(row=dna_row, column=2 + i, value="")
        tier = audit.get("completeness_tier", "abandoned")
        if tier in TIER_FILLS:
            cell.fill = TIER_FILLS[tier]

    # Tier Pie Chart
    pie_start = 10
    for i, tier in enumerate(TIER_ORDER):
        ws.cell(row=pie_start + i, column=1, value=tier.capitalize())
        ws.cell(row=pie_start + i, column=2, value=tiers.get(tier, 0))

    pie = PieChart()
    pie.title = "Tier Distribution"
    pie.style = 10
    labels = Reference(ws, min_col=1, min_row=pie_start, max_row=pie_start + 4)
    values = Reference(ws, min_col=2, min_row=pie_start, max_row=pie_start + 4)
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
    ws.add_chart(pie, "A16")

    # Grade Distribution Bar Chart
    grade_dist = Counter(a.get("grade", "F") for a in data.get("audits", []))
    grade_row = 10
    for i, g in enumerate(["A", "B", "C", "D", "F"]):
        ws.cell(row=grade_row + i, column=5, value=g)
        ws.cell(row=grade_row + i, column=6, value=grade_dist.get(g, 0))

    bar = BarChart()
    bar.type = "col"
    bar.title = "Grade Distribution"
    bar.style = 10
    bar_data = Reference(ws, min_col=6, min_row=grade_row, max_row=grade_row + 4)
    bar_cats = Reference(ws, min_col=5, min_row=grade_row, max_row=grade_row + 4)
    bar.add_data(bar_data, titles_from_data=False)
    bar.set_categories(bar_cats)
    bar.width = 16
    bar.height = 12
    ws.add_chart(bar, "G16")

    # Highlights section
    highlight_row = 30
    ws.cell(row=highlight_row, column=1, value="Highlights").font = SECTION_FONT

    best_work = data.get("best_work") or data.get("summary", {}).get("highest_scored", [])
    if best_work:
        ws.cell(row=highlight_row + 1, column=1, value="Best Work:").font = SUBHEADER_FONT
        for i, name in enumerate(best_work[:5]):
            ws.cell(row=highlight_row + 1, column=2 + i, value=name)

    lowest = data.get("summary", {}).get("lowest_scored", [])
    if lowest:
        ws.cell(row=highlight_row + 2, column=1, value="Needs Attention:").font = SUBHEADER_FONT
        for i, name in enumerate(lowest[:5]):
            ws.cell(row=highlight_row + 2, column=2 + i, value=name)

    # Language distribution
    lang_dist = data.get("language_distribution", {})
    lang_row = 10
    for i, (lang, count) in enumerate(list(lang_dist.items())[:8]):
        ws.cell(row=lang_row + i, column=9, value=lang)
        ws.cell(row=lang_row + i, column=10, value=count)

    if lang_dist:
        lang_bar = BarChart()
        lang_bar.type = "bar"
        lang_bar.title = "Top Languages"
        lang_bar.style = 10
        lang_data = Reference(ws, min_col=10, min_row=lang_row, max_row=lang_row + min(7, len(lang_dist) - 1))
        lang_cats = Reference(ws, min_col=9, min_row=lang_row, max_row=lang_row + min(7, len(lang_dist) - 1))
        lang_bar.add_data(lang_data, titles_from_data=False)
        lang_bar.set_categories(lang_cats)
        lang_bar.width = 16
        lang_bar.height = 10
        ws.add_chart(lang_bar, "A34")

    # Scatter chart: Completeness vs Interest
    _build_scatter_on_dashboard(ws, data)


def _build_scatter_on_dashboard(ws, data: dict) -> None:
    """Add completeness vs interest scatter chart with quadrant lines."""
    audits = data.get("audits", [])
    if len(audits) < 2:
        return

    # Write scatter data to cols L-N (12-14) starting at row 10
    data_start_row = 10
    col_name = 12  # L: repo name (reference)
    col_x = 13     # M: completeness
    col_y = 14     # N: interest

    for i, audit in enumerate(audits):
        row = data_start_row + i
        ws.cell(row=row, column=col_name, value=audit["metadata"]["name"])
        ws.cell(row=row, column=col_x, value=round(audit.get("overall_score", 0), 3))
        ws.cell(row=row, column=col_y, value=round(audit.get("interest_score", 0), 3))

    data_end_row = data_start_row + len(audits) - 1

    chart = ScatterChart()
    chart.title = "Completeness vs Interest"
    chart.x_axis.title = "Completeness"
    chart.y_axis.title = "Interest"
    chart.x_axis.scaling.min = 0
    chart.x_axis.scaling.max = 1
    chart.y_axis.scaling.min = 0
    chart.y_axis.scaling.max = 1
    chart.style = 13

    # Main data series — use add_data + set_categories (openpyxl scatter API)
    xvalues = Reference(ws, min_col=col_x, min_row=data_start_row, max_row=data_end_row)
    yvalues = Reference(ws, min_col=col_y, min_row=data_start_row, max_row=data_end_row)
    chart.add_data(yvalues, titles_from_data=False)
    chart.set_categories(xvalues)
    if chart.series:
        chart.series[0].graphicalProperties.line.noFill = True

    # Quadrant lines — vertical at x=0.55, horizontal at y=0.45
    line_col = 16  # col P for line data
    ws.cell(row=data_start_row, column=line_col, value=0.55)
    ws.cell(row=data_start_row, column=line_col + 1, value=0.0)
    ws.cell(row=data_start_row + 1, column=line_col, value=0.55)
    ws.cell(row=data_start_row + 1, column=line_col + 1, value=1.0)

    vline_y = Reference(ws, min_col=line_col + 1, min_row=data_start_row, max_row=data_start_row + 1)
    vline_x = Reference(ws, min_col=line_col, min_row=data_start_row, max_row=data_start_row + 1)
    chart.add_data(vline_y, titles_from_data=False)
    chart.set_categories(vline_x)
    if len(chart.series) > 1:
        chart.series[-1].graphicalProperties.line = LineProperties(w=12700, prstDash="dash", solidFill="808080")

    ws.cell(row=data_start_row, column=line_col + 2, value=0.0)
    ws.cell(row=data_start_row, column=line_col + 3, value=0.45)
    ws.cell(row=data_start_row + 1, column=line_col + 2, value=1.0)
    ws.cell(row=data_start_row + 1, column=line_col + 3, value=0.45)

    hline_y = Reference(ws, min_col=line_col + 3, min_row=data_start_row, max_row=data_start_row + 1)
    hline_x = Reference(ws, min_col=line_col + 2, min_row=data_start_row, max_row=data_start_row + 1)
    chart.add_data(hline_y, titles_from_data=False)
    chart.set_categories(hline_x)
    if len(chart.series) > 2:
        chart.series[-1].graphicalProperties.line = LineProperties(w=12700, prstDash="dash", solidFill="808080")

    chart.width = 18
    chart.height = 14
    ws.add_chart(chart, "G34")

    # Quadrant summary table
    _write_quadrant_table(ws, audits, legend_row=49)


X_MID = 0.55
Y_MID = 0.45

QUADRANT_NAMES = [
    ("Flagships", "high completeness + high interest"),
    ("Hidden Gems", "high interest, incomplete — worth finishing"),
    ("Workhorses", "solid but routine — bread and butter"),
    ("Archive Candidates", "low both — consider archiving"),
]


def _write_quadrant_table(ws, audits: list[dict], legend_row: int) -> None:
    """Write a quadrant summary table below the scatter chart."""
    buckets: list[list[str]] = [[], [], [], []]
    for a in audits:
        x = a.get("overall_score", 0)
        y = a.get("interest_score", 0)
        if x >= X_MID and y >= Y_MID:
            buckets[0].append(a["metadata"]["name"])
        elif x < X_MID and y >= Y_MID:
            buckets[1].append(a["metadata"]["name"])
        elif x >= X_MID and y < Y_MID:
            buckets[2].append(a["metadata"]["name"])
        else:
            buckets[3].append(a["metadata"]["name"])

    ws.cell(row=legend_row, column=7, value="Scatter Quadrants").font = SECTION_FONT
    headers = ["Quadrant", "Count", "Repos"]
    for j, h in enumerate(headers):
        ws.cell(row=legend_row + 1, column=7 + j, value=h).font = SUBHEADER_FONT

    for i, ((name, desc), repos) in enumerate(zip(QUADRANT_NAMES, buckets)):
        row = legend_row + 2 + i
        ws.cell(row=row, column=7, value=f"{name}").font = Font("Calibri", 10, bold=True)
        ws.cell(row=row, column=8, value=len(repos))
        ws.cell(row=row, column=9, value=", ".join(repos[:8]) + ("..." if len(repos) > 8 else ""))


# ═══════════════════════════════════════════════════════════════════════
# Sheet 2: All Repos (Master Table)
# ═══════════════════════════════════════════════════════════════════════


def _build_all_repos(wb: Workbook, data: dict, score_history: dict[str, list[float]] | None = None) -> None:
    ws = wb.create_sheet("All Repos")
    ws.sheet_properties.tabColor = "1565C0"

    headers = [
        "Repo", "Grade", "Score", "Interest", "Tier", "Badges",
        "Next Badge", "Language", "Commit Pattern", "Bus Factor",
        "Days Since Push", "Commits", "Releases", "Test Files",
        "LOC", "Libyears", "Stars", "Private", "Flags", "Description",
        "Biggest Drag", "Why This Grade", "Trend",
    ]
    for col, h in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=h)
    style_header_row(ws, 1, len(headers))
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(data.get('audits', [])) + 1}"

    audits = sorted(data.get("audits", []), key=lambda a: a.get("overall_score", 0), reverse=True)

    for row, audit in enumerate(audits, 2):
        m = audit.get("metadata", {})
        details = {r["dimension"]: r.get("details", {}) for r in audit.get("analyzer_results", [])}
        act = details.get("activity", {})
        cq = details.get("code_quality", {})
        test = details.get("testing", {})
        dep = details.get("dependencies", {})

        badges = audit.get("badges", [])
        next_badges = audit.get("next_badges", [])
        next_badge_str = next_badges[0]["action"] if next_badges else ""

        values = [
            m.get("name", ""),
            audit.get("grade", "F"),
            round(audit.get("overall_score", 0), 3),
            round(audit.get("interest_score", 0), 3),
            audit.get("completeness_tier", ""),
            ", ".join(badges[:4]),
            next_badge_str[:50],
            m.get("language") or "—",
            act.get("commit_pattern", "—"),
            act.get("bus_factor", "—"),
            act.get("days_since_push", "—"),
            act.get("total_commits", "—"),
            act.get("release_count", "—"),
            test.get("test_file_count", 0),
            cq.get("total_loc", 0),
            dep.get("total_libyears", "—"),
            m.get("stars", 0),
            "Yes" if m.get("private") else "No",
            ", ".join(audit.get("flags", [])),
            (m.get("description") or "")[:60],
        ]

        # Biggest Drag: lowest-scoring completeness dimension
        dim_scores = {
            r["dimension"]: r["score"]
            for r in audit.get("analyzer_results", [])
            if r["dimension"] != "interest"
        }
        if dim_scores:
            worst = min(dim_scores, key=dim_scores.get)
            values.append(f"{worst} ({dim_scores[worst]:.1f})")
        else:
            values.append("—")

        # Why This Grade
        from src.scorer import WEIGHTS as _W
        if dim_scores:
            sorted_dims = sorted(dim_scores.items(), key=lambda x: x[1])[:2]
            g = audit.get("grade", "F")
            if len(sorted_dims) >= 2:
                values.append(f"{g}: {sorted_dims[0][0]}={sorted_dims[0][1]:.1f}, {sorted_dims[1][0]}={sorted_dims[1][1]:.1f}")
            else:
                values.append(g)
        else:
            values.append(audit.get("grade", "F"))

        for col, val in enumerate(values, 1):
            cell = ws.cell(row=row, column=col, value=val)
            style_data_cell(cell)

        # Repo name hyperlink to GitHub
        name_cell = ws.cell(row=row, column=1)
        html_url = m.get("html_url", "")
        if html_url:
            name_cell.hyperlink = html_url
            name_cell.font = Font("Calibri", 10, color=TEAL, underline="single")

        # Grade coloring
        color_grade_cell(ws.cell(row=row, column=2), audit.get("grade", "F"))
        # Tier coloring
        color_tier_cell(ws.cell(row=row, column=5), audit.get("completeness_tier", ""))
        # Pattern coloring
        pattern = act.get("commit_pattern", "")
        if pattern and pattern != "—":
            color_pattern_cell(ws.cell(row=row, column=9), pattern)

        # Sparkline trend (column 23)
        if score_history:
            repo_name = m.get("name", "")
            scores = score_history.get(repo_name, [])
            spark = render_sparkline(scores)
            if spark:
                cell = ws.cell(row=row, column=23, value=spark)
                cell.font = SPARKLINE_FONT

    max_row = len(audits) + 1
    apply_zebra_stripes(ws, 2, max_row, len(headers))

    # DataBar on Score and Interest columns
    if max_row > 1:
        ws.conditional_formatting.add(
            f"C2:C{max_row}",
            DataBarRule(start_type='num', start_value=0, end_type='num', end_value=1, color='166534'),
        )
        ws.conditional_formatting.add(
            f"D2:D{max_row}",
            DataBarRule(start_type='num', start_value=0, end_type='num', end_value=1, color='0EA5E9'),
        )

    # Tooltips on key columns
    score_dv = DataValidation(allow_blank=True, prompt="Weighted average of 10 dimensions. See Score Explainer sheet.", promptTitle="Overall Score")
    score_dv.sqref = f"C2:C{max_row}"
    ws.add_data_validation(score_dv)
    interest_dv = DataValidation(allow_blank=True, prompt="How interesting/ambitious (separate from completeness). Based on tech novelty, commit patterns, scope.", promptTitle="Interest Score")
    interest_dv.sqref = f"D2:D{max_row}"
    ws.add_data_validation(interest_dv)
    grade_dv = DataValidation(allow_blank=True, prompt="A (>=85%) B (>=70%) C (>=55%) D (>=35%) F (<35%)", promptTitle="Letter Grade")
    grade_dv.sqref = f"B2:B{max_row}"
    ws.add_data_validation(grade_dv)

    # Summary row
    sr = max_row + 2
    ws.cell(row=sr, column=1, value="SUMMARY").font = SUBHEADER_FONT
    ws.cell(row=sr, column=3, value=f"=AVERAGE(C2:C{max_row})").font = SUBHEADER_FONT
    ws.cell(row=sr, column=4, value=f"=AVERAGE(D2:D{max_row})").font = SUBHEADER_FONT

    auto_width(ws, len(headers), max_row + 2)


# ═══════════════════════════════════════════════════════════════════════
# Sheet 3: Scoring Heatmap
# ═══════════════════════════════════════════════════════════════════════


def _build_heatmap(wb: Workbook, data: dict) -> None:
    ws = wb.create_sheet("Scoring Heatmap")
    ws.sheet_properties.tabColor = "D97706"

    dimensions = [
        "readme", "structure", "code_quality", "testing", "cicd",
        "dependencies", "activity", "documentation", "build_readiness",
        "community_profile", "interest",
    ]
    dim_labels = [d.replace("_", " ").title() for d in dimensions]
    headers = ["Repo", "Grade", "Overall"] + dim_labels

    for col, h in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=h)
    style_header_row(ws, 1, len(headers))
    ws.freeze_panes = "B2"

    audits = sorted(data.get("audits", []), key=lambda a: a.get("overall_score", 0), reverse=True)

    for row, audit in enumerate(audits, 2):
        score_map = {r["dimension"]: r["score"] for r in audit.get("analyzer_results", [])}

        ws.cell(row=row, column=1, value=audit["metadata"]["name"])
        style_data_cell(ws.cell(row=row, column=1))

        grade_cell = ws.cell(row=row, column=2, value=audit.get("grade", "F"))
        color_grade_cell(grade_cell, audit.get("grade", "F"))

        ws.cell(row=row, column=3, value=round(audit.get("overall_score", 0), 2))
        style_data_cell(ws.cell(row=row, column=3), "center")

        for i, dim in enumerate(dimensions, 4):
            score = round(score_map.get(dim, 0), 2)
            cell = ws.cell(row=row, column=i, value=score)
            cell.alignment = CENTER
            cell.border = THIN_BORDER

    max_row = len(audits) + 1

    # ColorScaleRule on all dimension columns (cols 3 through end)
    if max_row > 1:
        for col in range(3, len(headers) + 1):
            col_letter = get_column_letter(col)
            ws.conditional_formatting.add(
                f"{col_letter}2:{col_letter}{max_row}",
                ColorScaleRule(
                    start_type='num', start_value=0, start_color=HEATMAP_RED,
                    mid_type='num', mid_value=0.5, mid_color=HEATMAP_AMBER,
                    end_type='num', end_value=1, end_color=HEATMAP_GREEN,
                ),
            )

    auto_width(ws, len(headers), max_row)


# ═══════════════════════════════════════════════════════════════════════
# Sheet 4: Quick Wins
# ═══════════════════════════════════════════════════════════════════════


def _build_quick_wins(wb: Workbook, data: dict) -> None:
    ws = wb.create_sheet("Quick Wins")
    ws.sheet_properties.tabColor = "0891B2"

    tier_next = {
        "abandoned": ("skeleton", 0.15),
        "skeleton": ("wip", 0.35),
        "wip": ("functional", 0.55),
        "functional": ("shipped", 0.75),
    }

    wins: list[dict] = []
    for audit in data.get("audits", []):
        current_tier = audit.get("completeness_tier", "")
        if current_tier not in tier_next:
            continue
        next_name, threshold = tier_next[current_tier]
        gap = threshold - audit.get("overall_score", 0)
        if gap > 0.20 or gap <= 0:
            continue

        dim_scores = {r["dimension"]: r["score"] for r in audit.get("analyzer_results", [])}
        sorted_dims = sorted(dim_scores.items(), key=lambda x: x[1])
        actions = [f"Improve {d} ({s:.1f})" for d, s in sorted_dims[:3]]

        wins.append({
            "name": audit["metadata"]["name"],
            "grade": audit.get("grade", "F"),
            "tier": current_tier,
            "score": audit.get("overall_score", 0),
            "next_tier": next_name,
            "gap": gap,
            "actions": actions,
            "badges": len(audit.get("badges", [])),
        })

    wins.sort(key=lambda w: w["gap"])

    # Title
    ws.merge_cells("A1:H1")
    ws["A1"].value = f"Quick Wins — {len(wins)} repos near the next tier"
    ws["A1"].font = SECTION_FONT

    if not wins:
        ws.cell(row=3, column=1, value="No repos within striking distance of the next tier.")
        return

    headers = ["Repo", "Grade", "Current", "Score", "Next Tier", "Gap", "Top Actions", "Badges"]
    for col, h in enumerate(headers, 1):
        ws.cell(row=3, column=col, value=h)
    style_header_row(ws, 3, len(headers))

    for row, win in enumerate(wins, 4):
        ws.cell(row=row, column=1, value=win["name"])
        grade_cell = ws.cell(row=row, column=2, value=win["grade"])
        color_grade_cell(grade_cell, win["grade"])
        tier_cell = ws.cell(row=row, column=3, value=win["tier"])
        color_tier_cell(tier_cell, win["tier"])
        ws.cell(row=row, column=4, value=round(win["score"], 3))
        ws.cell(row=row, column=5, value=win["next_tier"])
        ws.cell(row=row, column=6, value=round(win["gap"], 3))
        ws.cell(row=row, column=7, value="; ".join(win["actions"]))
        ws.cell(row=row, column=8, value=win["badges"])

        for col in range(1, 9):
            style_data_cell(ws.cell(row=row, column=col))

    max_row = len(wins) + 3
    if max_row > 4:
        ws.conditional_formatting.add(
            f"F4:F{max_row}",
            DataBarRule(start_type='num', start_value=0, end_type='num', end_value=0.20, color='0EA5E9'),
        )

    apply_zebra_stripes(ws, 4, max_row, len(headers))
    auto_width(ws, len(headers), max_row)


# ═══════════════════════════════════════════════════════════════════════
# Sheet 5: Badges Dashboard
# ═══════════════════════════════════════════════════════════════════════


def _build_badges(wb: Workbook, data: dict) -> None:
    ws = wb.create_sheet("Badges")
    ws.sheet_properties.tabColor = "7C3AED"

    # Collect badge stats
    badge_counts: Counter = Counter()
    repo_badge_counts: list[tuple[str, int]] = []

    for audit in data.get("audits", []):
        badges = audit.get("badges", [])
        for b in badges:
            badge_counts[b] += 1
        repo_badge_counts.append((audit["metadata"]["name"], len(badges)))

    total_repos = len(data.get("audits", []))

    # Title
    ws.merge_cells("A1:E1")
    ws["A1"].value = "Badge Dashboard"
    ws["A1"].font = SECTION_FONT

    total_badges = sum(badge_counts.values())
    ws.cell(row=2, column=1, value=f"Total badges earned: {total_badges} across {total_repos} repos")
    ws.cell(row=2, column=1).font = SUBTITLE_FONT

    # Badge distribution table
    headers = ["Badge", "Repos Earned", "% of Portfolio"]
    for col, h in enumerate(headers, 1):
        ws.cell(row=4, column=col, value=h)
    style_header_row(ws, 4, len(headers))

    for row, (badge, count) in enumerate(badge_counts.most_common(), 5):
        ws.cell(row=row, column=1, value=badge)
        ws.cell(row=row, column=2, value=count)
        ws.cell(row=row, column=3, value=f"{count/total_repos*100:.0f}%")
        for col in range(1, 4):
            style_data_cell(ws.cell(row=row, column=col))

    # Bar chart
    badge_end = 4 + len(badge_counts)
    if badge_counts:
        chart = BarChart()
        chart.type = "bar"
        chart.title = "Badge Distribution"
        chart.style = 10
        chart_data = Reference(ws, min_col=2, min_row=5, max_row=badge_end)
        chart_cats = Reference(ws, min_col=1, min_row=5, max_row=badge_end)
        chart.add_data(chart_data, titles_from_data=False)
        chart.set_categories(chart_cats)
        chart.series[0].graphicalProperties.solidFill = "7C3AED"
        chart.width = 20
        chart.height = max(8, len(badge_counts) * 0.6)
        ws.add_chart(chart, "E4")

    # Achievement board — repos by badge count
    board_row = badge_end + 3
    ws.cell(row=board_row, column=1, value="Achievement Board").font = SECTION_FONT
    board_row += 1
    ws.cell(row=board_row, column=1, value="Repo").font = SUBHEADER_FONT
    ws.cell(row=board_row, column=2, value="Badges").font = SUBHEADER_FONT
    ws.cell(row=board_row, column=1).fill = SUBHEADER_FILL
    ws.cell(row=board_row, column=2).fill = SUBHEADER_FILL

    repo_badge_counts.sort(key=lambda x: x[1], reverse=True)
    for i, (name, count) in enumerate(repo_badge_counts[:20], board_row + 1):
        ws.cell(row=i, column=1, value=name).border = THIN_BORDER
        ws.cell(row=i, column=2, value=count).border = THIN_BORDER

    auto_width(ws, 3, board_row + 21)


# ═══════════════════════════════════════════════════════════════════════
# Sheet 6: Tech Stack
# ═══════════════════════════════════════════════════════════════════════


def _build_tech_stack(wb: Workbook, data: dict) -> None:
    tech_stack = data.get("tech_stack", {})
    if not tech_stack:
        return

    ws = wb.create_sheet("Tech Stack")
    ws.sheet_properties.tabColor = "4A148C"

    ws.merge_cells("A1:E1")
    ws["A1"].value = "Technology Stack"
    ws["A1"].font = SECTION_FONT

    headers = ["Language", "Repos", "Bytes", "Avg Score", "Proficiency"]
    for col, h in enumerate(headers, 1):
        ws.cell(row=3, column=col, value=h)
    style_header_row(ws, 3, len(headers))

    for row, (lang, info) in enumerate(tech_stack.items(), 4):
        ws.cell(row=row, column=1, value=lang)
        ws.cell(row=row, column=2, value=info.get("repos", 0))
        ws.cell(row=row, column=3, value=info.get("bytes", 0))
        ws.cell(row=row, column=4, value=info.get("avg_score", 0))
        ws.cell(row=row, column=5, value=info.get("proficiency", 0))
        for col in range(1, 6):
            style_data_cell(ws.cell(row=row, column=col))

    max_row = 3 + len(tech_stack)
    if len(tech_stack) > 1:
        chart = BarChart()
        chart.type = "col"
        chart.title = "Language Proficiency (bytes x quality)"
        chart.style = 10
        chart_data = Reference(ws, min_col=5, min_row=3, max_row=max_row)
        chart_cats = Reference(ws, min_col=1, min_row=4, max_row=max_row)
        chart.add_data(chart_data, titles_from_data=True)
        chart.set_categories(chart_cats)
        chart.width = 20
        chart.height = 12
        ws.add_chart(chart, "G3")

    # Best work
    best_work = data.get("best_work", [])
    if best_work:
        bw_row = max_row + 3
        ws.cell(row=bw_row, column=1, value="Best Work (Top 5)").font = SECTION_FONT
        for i, name in enumerate(best_work, bw_row + 1):
            ws.cell(row=i, column=1, value=f"{i - bw_row}. {name}").border = THIN_BORDER

    auto_width(ws, 5, max_row + 10)


# ═══════════════════════════════════════════════════════════════════════
# Sheet 7: Trends
# ═══════════════════════════════════════════════════════════════════════


def _build_trends(wb: Workbook, data: dict, trend_data: list[dict] | None = None) -> None:
    ws = wb.create_sheet("Trends")
    ws.sheet_properties.tabColor = "311B92"

    ws.merge_cells("A1:F1")
    ws["A1"].value = "Portfolio Trends"
    ws["A1"].font = SECTION_FONT

    if not trend_data or len(trend_data) < 2:
        ws.cell(row=3, column=1, value="Run more audits to see trends (need 2+ historical runs)")
        ws.cell(row=3, column=1).font = SUBTITLE_FONT
        return

    ws.cell(row=3, column=1, value="Date").font = SUBHEADER_FONT
    ws.cell(row=4, column=1, value="Avg Score").font = SUBHEADER_FONT
    ws.cell(row=5, column=1, value="Repos").font = SUBHEADER_FONT
    for col, run in enumerate(trend_data, 2):
        ws.cell(row=3, column=col, value=run["date"]).border = THIN_BORDER
        ws.cell(row=4, column=col, value=run["average_score"]).border = THIN_BORDER
        ws.cell(row=5, column=col, value=run["repos_audited"]).border = THIN_BORDER

    row = 7
    ws.cell(row=row, column=1, value="Tier").font = SUBHEADER_FONT
    for i, tier in enumerate(TIER_ORDER):
        ws.cell(row=row + 1 + i, column=1, value=tier.capitalize())
        for col, run in enumerate(trend_data, 2):
            ws.cell(row=row + 1 + i, column=col, value=run.get("tier_distribution", {}).get(tier, 0))

    auto_width(ws, len(trend_data) + 1, 15)


# ═══════════════════════════════════════════════════════════════════════
# Sheet 8: Tier Breakdown
# ═══════════════════════════════════════════════════════════════════════


def _build_tier_breakdown(wb: Workbook, data: dict) -> None:
    ws = wb.create_sheet("Tier Breakdown")
    ws.sheet_properties.tabColor = "166534"

    from openpyxl.styles import Font as XFont

    audits_by_tier: dict[str, list] = {}
    for a in data.get("audits", []):
        audits_by_tier.setdefault(a.get("completeness_tier", ""), []).append(a)

    current_row = 1
    for tier in TIER_ORDER:
        tier_audits = audits_by_tier.get(tier, [])
        if not tier_audits:
            continue
        tier_audits.sort(key=lambda a: a.get("overall_score", 0), reverse=True)

        from src.excel_styles import TIER_FILLS, TIER_FONT
        ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=6)
        h = ws.cell(row=current_row, column=1, value=f"{tier.upper()} ({len(tier_audits)} repos)")
        h.font = XFont(bold=True, size=13, color=WHITE)
        h.fill = TIER_FILLS.get(tier)
        h.alignment = CENTER
        current_row += 1

        cols = ["Repo", "Grade", "Score", "Language", "Badges", "Description"]
        for col, ch in enumerate(cols, 1):
            ws.cell(row=current_row, column=col, value=ch)
        style_header_row(ws, current_row, len(cols))
        current_row += 1

        for audit in tier_audits:
            m = audit["metadata"]
            ws.cell(row=current_row, column=1, value=m["name"])
            g_cell = ws.cell(row=current_row, column=2, value=audit.get("grade", "F"))
            color_grade_cell(g_cell, audit.get("grade", "F"))
            ws.cell(row=current_row, column=3, value=round(audit.get("overall_score", 0), 2))
            ws.cell(row=current_row, column=4, value=m.get("language") or "—")
            ws.cell(row=current_row, column=5, value=len(audit.get("badges", [])))
            ws.cell(row=current_row, column=6, value=(m.get("description") or "")[:50])
            for col in range(1, 7):
                style_data_cell(ws.cell(row=current_row, column=col))
            current_row += 1

        current_row += 2

    auto_width(ws, 6, current_row)


# ═══════════════════════════════════════════════════════════════════════
# Sheet 9: Activity
# ═══════════════════════════════════════════════════════════════════════


def _build_activity(wb: Workbook, data: dict) -> None:
    ws = wb.create_sheet("Activity")
    ws.sheet_properties.tabColor = "6A1B9A"

    headers = [
        "Repo", "Commit Pattern", "Days Since Push", "Total Commits",
        "Recent 3mo", "Bus Factor", "Release Count", "Activity Score", "Tier",
    ]
    for col, h in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=h)
    style_header_row(ws, 1, len(headers))
    ws.freeze_panes = "B2"

    audits = sorted(
        data.get("audits", []),
        key=lambda a: next(
            (r.get("details", {}).get("days_since_push", 9999)
             for r in a.get("analyzer_results", []) if r["dimension"] == "activity"),
            9999,
        ),
    )

    for row, audit in enumerate(audits, 2):
        details = {r["dimension"]: r.get("details", {}) for r in audit.get("analyzer_results", [])}
        scores = {r["dimension"]: r["score"] for r in audit.get("analyzer_results", [])}
        act = details.get("activity", {})

        pattern = act.get("commit_pattern", "—")
        values = [
            audit["metadata"]["name"],
            pattern,
            act.get("days_since_push", "—"),
            act.get("total_commits", "—"),
            act.get("recent_3mo_commits", "—"),
            act.get("bus_factor", "—"),
            act.get("release_count", "—"),
            round(scores.get("activity", 0), 2),
            audit.get("completeness_tier", ""),
        ]
        for col, val in enumerate(values, 1):
            cell = ws.cell(row=row, column=col, value=val)
            style_data_cell(cell)

        if pattern and pattern != "—":
            color_pattern_cell(ws.cell(row=row, column=2), pattern)

    max_row = len(audits) + 1
    apply_zebra_stripes(ws, 2, max_row, len(headers))
    auto_width(ws, len(headers), max_row)


# ═══════════════════════════════════════════════════════════════════════
# Sheet 10: Registry Reconciliation
# ═══════════════════════════════════════════════════════════════════════


def _build_reconciliation(wb: Workbook, data: dict) -> None:
    recon = data.get("reconciliation")
    if not recon:
        return

    ws = wb.create_sheet("Registry")
    ws.sheet_properties.tabColor = "00695C"

    row = 1
    ws.merge_cells("A1:E1")
    ws["A1"].value = f"Registry Reconciliation ({recon.get('registry_total', 0)} projects)"
    ws["A1"].font = SECTION_FONT

    # Matched
    matched = recon.get("matched", [])
    if matched:
        row = 3
        ws.cell(row=row, column=1, value=f"Matched ({len(matched)})").font = SUBHEADER_FONT
        row += 1
        for col, h in enumerate(["GitHub", "Registry", "Status", "Tier", "Score"], 1):
            ws.cell(row=row, column=col, value=h)
        style_header_row(ws, row, 5)
        row += 1
        for m in matched:
            ws.cell(row=row, column=1, value=m.get("github_name", ""))
            ws.cell(row=row, column=2, value=m.get("registry_name", ""))
            ws.cell(row=row, column=3, value=m.get("registry_status", ""))
            t_cell = ws.cell(row=row, column=4, value=m.get("audit_tier", ""))
            color_tier_cell(t_cell, m.get("audit_tier", ""))
            ws.cell(row=row, column=5, value=m.get("score", 0))
            for col in range(1, 6):
                style_data_cell(ws.cell(row=row, column=col))
            row += 1

    # Unmatched
    unmatched_gh = recon.get("on_github_not_registry", [])
    if unmatched_gh:
        row += 2
        ws.cell(row=row, column=1, value=f"On GitHub, NOT in Registry ({len(unmatched_gh)})").font = SUBHEADER_FONT
        row += 1
        for name in unmatched_gh:
            ws.cell(row=row, column=1, value=name).border = THIN_BORDER
            row += 1

    unmatched_reg = recon.get("in_registry_not_github", [])
    if unmatched_reg:
        row += 1
        ws.cell(row=row, column=1, value=f"In Registry, NOT on GitHub ({len(unmatched_reg)})").font = SUBHEADER_FONT
        row += 1
        for name in unmatched_reg:
            ws.cell(row=row, column=1, value=name).border = THIN_BORDER
            row += 1

    auto_width(ws, 5, row)


# ═══════════════════════════════════════════════════════════════════════
# Main export
# ═══════════════════════════════════════════════════════════════════════


def _build_score_explainer(wb: Workbook) -> None:
    """Static reference sheet explaining the scoring system."""
    from src.scorer import WEIGHTS, GRADE_THRESHOLDS, COMPLETENESS_TIERS, INTEREST_TIERS

    ws = wb.create_sheet("Score Explainer")
    ws.sheet_properties.tabColor = "37474F"

    ws.merge_cells("A1:D1")
    ws["A1"].value = "Scoring System Reference"
    ws["A1"].font = TITLE_FONT

    DIMENSION_INFO = {
        "testing": ("Test directories, framework, test file count", "Add test/ with pytest/jest/vitest configured"),
        "code_quality": ("Entry points, TODO density, types, commit quality", "Add main entry point, reduce TODOs"),
        "activity": ("Push recency, commit count, releases, bus factor", "Push regularly, tag releases"),
        "readme": ("Exists, description, install instructions, examples", "Add usage section with code blocks"),
        "structure": (".gitignore, source dirs, config files, LICENSE", "Add .gitignore + LICENSE + package manifest"),
        "cicd": ("GitHub Actions, CI configs, build scripts", "Add .github/workflows/ci.yml"),
        "dependencies": ("Manifest + lockfile, dep count, libyears", "Add lockfile alongside manifest"),
        "build_readiness": ("Docker, Makefile, .env.example, deploy configs", "Add Dockerfile or Makefile"),
        "community_profile": ("LICENSE, CONTRIBUTING, CODE_OF_CONDUCT", "Add CONTRIBUTING.md"),
        "documentation": ("docs/ dir, CHANGELOG, comment density", "Add docs/ folder or CHANGELOG.md"),
    }

    ws.cell(row=3, column=1, value="Dimension Weights").font = SECTION_FONT
    for col, h in enumerate(["Dimension", "Weight", "What It Measures", "How to Improve"], 1):
        ws.cell(row=4, column=col, value=h)
    style_header_row(ws, 4, 4)

    row = 5
    for dim, weight in sorted(WEIGHTS.items(), key=lambda x: x[1], reverse=True):
        desc, improve = DIMENSION_INFO.get(dim, ("", ""))
        ws.cell(row=row, column=1, value=dim)
        ws.cell(row=row, column=2, value=f"{weight:.0%}")
        ws.cell(row=row, column=3, value=desc)
        ws.cell(row=row, column=4, value=improve)
        for c in range(1, 5):
            style_data_cell(ws.cell(row=row, column=c))
        row += 1

    row += 1
    ws.cell(row=row, column=1, value="Grade Thresholds").font = SECTION_FONT
    row += 1
    for threshold, g in GRADE_THRESHOLDS:
        ws.cell(row=row, column=1, value=g)
        ws.cell(row=row, column=2, value=f">= {threshold:.0%}")
        color_grade_cell(ws.cell(row=row, column=1), g)
        row += 1

    row += 1
    ws.cell(row=row, column=1, value="Tier Thresholds").font = SECTION_FONT
    row += 1
    for tier_name, threshold in COMPLETENESS_TIERS:
        ws.cell(row=row, column=1, value=tier_name.capitalize())
        ws.cell(row=row, column=2, value=f">= {threshold:.0%}")
        color_tier_cell(ws.cell(row=row, column=1), tier_name)
        row += 1

    auto_width(ws, 4, row)


# ── Effort map for action items
EFFORT_MAP = {
    "readme": "Low", "structure": "Low", "cicd": "Low",
    "documentation": "Low", "community_profile": "Low",
    "dependencies": "Low", "build_readiness": "Med",
    "testing": "Med", "code_quality": "Med", "activity": "High",
}

TIER_NEXT = {
    "abandoned": ("skeleton", 0.15),
    "skeleton": ("wip", 0.35),
    "wip": ("functional", 0.55),
    "functional": ("shipped", 0.75),
}


def _collect_all_actions(data: dict) -> list[dict]:
    """Collect and prioritize actions from audit data."""
    actions: list[dict] = []
    for audit in data.get("audits", []):
        tier = audit.get("completeness_tier", "")
        if tier not in TIER_NEXT:
            continue
        next_tier, threshold = TIER_NEXT[tier]
        gap = threshold - audit.get("overall_score", 0)
        if gap <= 0:
            continue

        dim_scores = {
            r["dimension"]: r["score"]
            for r in audit.get("analyzer_results", [])
            if r["dimension"] != "interest"
        }
        for dim, score in sorted(dim_scores.items(), key=lambda x: x[1])[:2]:
            actions.append({
                "repo": audit["metadata"]["name"],
                "action": f"Improve {dim} (currently {score:.1f})",
                "impact": f"Close {gap:.3f} gap to {next_tier}",
                "effort": EFFORT_MAP.get(dim, "Med"),
                "dimension": dim,
                "gap": gap,
            })

        for badge_s in audit.get("next_badges", [])[:1]:
            actions.append({
                "repo": audit["metadata"]["name"],
                "action": badge_s.get("action", ""),
                "impact": f"Earn '{badge_s.get('badge', '')}' badge",
                "effort": "Low" if badge_s.get("gap", 1) < 0.3 else "Med",
                "dimension": "badges",
                "gap": badge_s.get("gap", 1.0),
            })

    effort_order = {"Low": 0, "Med": 1, "High": 2}
    actions.sort(key=lambda a: (effort_order.get(a["effort"], 1), a["gap"]))

    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for a in actions:
        key = (a["repo"], a["dimension"])
        if key not in seen:
            seen.add(key)
            unique.append(a)
    return unique


def _build_action_items(wb: Workbook, data: dict) -> None:
    """Prioritized action item list with weekly sprint."""
    ws = wb.create_sheet("Action Items")
    ws.sheet_properties.tabColor = "E65100"

    actions = _collect_all_actions(data)

    ws.merge_cells("A1:F1")
    ws["A1"].value = f"Action Items — {len(actions)} prioritized improvements"
    ws["A1"].font = SECTION_FONT

    sprint = [a for a in actions if a["effort"] == "Low"][:5]
    headers = ["#", "Repo", "Action", "Impact", "Effort", "Dimension"]

    if sprint:
        ws.cell(row=3, column=1, value="Weekly Sprint (Top 5 Low-Effort)").font = SECTION_FONT
        for col, h in enumerate(headers, 1):
            ws.cell(row=4, column=col, value=h)
        style_header_row(ws, 4, len(headers))
        for i, item in enumerate(sprint, 5):
            for col, val in enumerate([i - 4, item["repo"], item["action"], item["impact"], item["effort"], item["dimension"]], 1):
                cell = ws.cell(row=i, column=col, value=val)
                style_data_cell(cell)

    full_start = len(sprint) + 7
    ws.cell(row=full_start, column=1, value="All Actions (Prioritized)").font = SECTION_FONT
    full_start += 1
    for col, h in enumerate(headers, 1):
        ws.cell(row=full_start, column=col, value=h)
    style_header_row(ws, full_start, len(headers))

    for i, item in enumerate(actions[:100], full_start + 1):
        for col, val in enumerate([i - full_start, item["repo"], item["action"], item["impact"], item["effort"], item["dimension"]], 1):
            cell = ws.cell(row=i, column=col, value=val)
            style_data_cell(cell)

    apply_zebra_stripes(ws, full_start + 1, full_start + min(len(actions), 100), len(headers))
    auto_width(ws, len(headers), full_start + min(len(actions), 100) + 1)


def _build_navigation(wb: Workbook, data: dict) -> None:
    """Navigation index as the first sheet."""
    ws = wb.create_sheet("Index", 0)
    ws.sheet_properties.tabColor = "263238"

    ws.merge_cells("A1:D1")
    ws["A1"].value = f"GitHub Portfolio Audit: {data['username']}"
    ws["A1"].font = TITLE_FONT

    ws.merge_cells("A2:D2")
    ws["A2"].value = f"Last updated: {data['generated_at'][:10]} | {data['repos_audited']} repos | Grade: {data.get('portfolio_grade', '?')}"
    ws["A2"].font = SUBTITLE_FONT

    ws.cell(row=4, column=1, value="Sheet Directory").font = SECTION_FONT

    sheets = [
        ("Dashboard", "Executive overview — KPI cards, charts, narrative"),
        ("All Repos", "Master table with scores, grades, badges, and explanations"),
        ("Scoring Heatmap", "Color-coded matrix of per-dimension scores"),
        ("Quick Wins", "Repos closest to the next tier promotion"),
        ("Badges", "Achievement badges earned and portfolio leaderboard"),
        ("Tech Stack", "Language proficiency weighted by project quality"),
        ("Trends", "Historical score and tier trends across audit runs"),
        ("Tier Breakdown", "Repos grouped by completeness tier"),
        ("Activity", "Commit patterns, bus factor, release cadence"),
        ("Registry", "Cross-reference with project registry"),
        ("Score Explainer", "How scoring, grades, and tiers work"),
        ("Action Items", "Prioritized improvements with effort estimates"),
    ]

    for col, h in enumerate(["Sheet", "Description"], 1):
        ws.cell(row=5, column=col, value=h)
    style_header_row(ws, 5, 2)

    for i, (name, desc) in enumerate(sheets, 6):
        cell = ws.cell(row=i, column=1, value=name)
        cell.hyperlink = f"#{name}!A1"
        cell.font = Font("Calibri", 11, bold=True, color=TEAL, underline="single")
        ws.cell(row=i, column=2, value=desc)
        style_data_cell(ws.cell(row=i, column=2))

    auto_width(ws, 2, 6 + len(sheets))


def export_excel(
    report_path: Path,
    output_path: Path,
    trend_data: list[dict] | None = None,
    diff_data: dict | None = None,
    score_history: dict[str, list[float]] | None = None,
) -> Path:
    """Generate the flagship Excel dashboard."""
    data = json.loads(report_path.read_text())

    wb = Workbook()
    _build_dashboard(wb, data, diff_data, score_history)
    _build_all_repos(wb, data, score_history)
    _build_heatmap(wb, data)
    _build_quick_wins(wb, data)
    _build_badges(wb, data)
    _build_tech_stack(wb, data)
    _build_trends(wb, data, trend_data)
    _build_tier_breakdown(wb, data)
    _build_activity(wb, data)
    _build_reconciliation(wb, data)
    _build_score_explainer(wb)
    _build_action_items(wb, data)
    _build_navigation(wb, data)

    wb.save(str(output_path))
    return output_path
