"""Flagship Excel dashboard generator.

Produces a 10-sheet workbook that serves as the primary way to understand
the portfolio: KPI dashboard, master table, heatmap, quick wins, badges,
tech stack, trends, tier breakdown, activity, and registry reconciliation.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.chart import BarChart, BubbleChart, PieChart, RadarChart, Reference, ScatterChart
from openpyxl.chart.series import Series as BubbleSeries
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.series import DataPoint
from openpyxl.drawing.line import LineProperties
from openpyxl.formatting.rule import ColorScaleRule, DataBarRule, IconSetRule
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.workbook.defined_name import DefinedName

from src.sparkline import sparkline as render_sparkline

from src.excel_template import (
    DEFAULT_TEMPLATE_PATH,
    TREND_HISTORY_WINDOW,
    SparklineSpec,
    copy_template_to_output,
    inject_native_sparklines,
    resolve_template_path,
)
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


def _add_table(ws, table_name: str, max_col: int, max_row: int, start_row: int = 1) -> None:
    """Attach a structured table to an already-populated range."""
    if max_row <= start_row:
        return
    ref = f"A{start_row}:{get_column_letter(max_col)}{max_row}"
    table = Table(displayName=table_name, ref=ref)
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    ws.add_table(table)


def _clear_worksheet(ws) -> None:
    if ws.max_row:
        ws.delete_rows(1, ws.max_row)
    if ws.max_column:
        ws.delete_cols(1, ws.max_column)
    ws._charts = []
    ws.conditional_formatting._cf_rules.clear()
    ws.data_validations.dataValidation = []
    ws.merged_cells.ranges = set()
    ws.freeze_panes = None
    ws.auto_filter.ref = None
    if hasattr(ws, "_tables"):
        ws._tables.clear()


def _get_or_create_sheet(wb: Workbook, title: str):
    if title in wb.sheetnames:
        ws = wb[title]
        _clear_worksheet(ws)
        return ws
    return wb.create_sheet(title)


def _extend_score_history_with_current(
    data: dict,
    score_history: dict[str, list[float]] | None,
) -> dict[str, list[float]]:
    extended = {name: list(scores) for name, scores in (score_history or {}).items()}
    for audit in data.get("audits", []):
        name = audit.get("metadata", {}).get("name", "")
        if not name:
            continue
        current_score = round(audit.get("overall_score", 0), 3)
        history = extended.setdefault(name, [])
        if not history or abs(history[-1] - current_score) > 1e-9:
            history.append(current_score)
        extended[name] = history[-TREND_HISTORY_WINDOW:]
    return extended


def _extend_portfolio_trend_with_current(
    data: dict,
    trend_data: list[dict] | None,
) -> list[dict]:
    trends = [dict(item) for item in (trend_data or [])]
    current = {
        "date": data.get("generated_at", "")[:10],
        "average_score": data.get("average_score", 0.0),
        "repos_audited": data.get("repos_audited", 0),
        "tier_distribution": data.get("tier_distribution", {}),
        "top_repos": {
            audit.get("metadata", {}).get("name", ""): audit.get("overall_score", 0.0)
            for audit in sorted(
                data.get("audits", []),
                key=lambda item: item.get("overall_score", 0),
                reverse=True,
            )[:20]
            if audit.get("metadata", {}).get("name")
        },
    }
    if not trends or trends[-1].get("date") != current["date"]:
        trends.append(current)
    else:
        trends[-1] = current
    return trends[-TREND_HISTORY_WINDOW:]


def _set_defined_name(wb: Workbook, name: str, attr_text: str) -> None:
    try:
        del wb.defined_names[name]
    except KeyError:
        pass
    wb.defined_names.add(DefinedName(name, attr_text=attr_text))


def _refresh_pivot_caches_on_load(wb: Workbook) -> None:
    for ws in wb.worksheets:
        for pivot in getattr(ws, "_pivots", []):
            cache = getattr(pivot, "cache", None)
            if cache and getattr(cache, "refreshOnLoad", None) is not None:
                cache.refreshOnLoad = True


def _apply_workbook_named_ranges(
    wb: Workbook,
    data: dict,
    *,
    portfolio_profile: str = "default",
    collection: str | None = None,
) -> None:
    _set_defined_name(wb, "nrGeneratedAt", "'Dashboard'!$A$2")
    _set_defined_name(wb, "nrPortfolioGrade", "'Dashboard'!$A$6")
    _set_defined_name(wb, "nrAverageScore", "'Dashboard'!$C$6")
    _set_defined_name(wb, "nrPortfolioProfile", "'Executive Summary'!$F$6")
    _set_defined_name(wb, "nrCollectionFilter", "'Executive Summary'!$F$7")

    dashboard = wb["Dashboard"]
    dashboard["A2"] = f"Generated: {data['generated_at'][:10]} | {data['repos_audited']} repos audited"
    if "Executive Summary" in wb.sheetnames:
        executive = wb["Executive Summary"]
        executive["F6"] = portfolio_profile
        executive["F7"] = collection or "all"


def _collection_memberships(data: dict) -> dict[str, list[str]]:
    memberships: dict[str, list[str]] = {}
    for collection_name, collection_data in data.get("collections", {}).items():
        for repo_data in collection_data.get("repos", []):
            repo_name = repo_data["name"] if isinstance(repo_data, dict) else str(repo_data)
            memberships.setdefault(repo_name, []).append(collection_name)
    return memberships


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


def _build_dashboard(
    wb: Workbook,
    data: dict,
    diff_data: dict | None = None,
    score_history: dict[str, list[float]] | None = None,
    *,
    native_sparklines: bool = False,
) -> None:
    ws = wb.active
    _clear_worksheet(ws)
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
    if score_history and not native_sparklines:
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


def _build_all_repos(
    wb: Workbook,
    data: dict,
    score_history: dict[str, list[float]] | None = None,
    *,
    native_sparklines: bool = False,
) -> None:
    ws = wb.create_sheet("All Repos")
    ws.sheet_properties.tabColor = "1565C0"

    headers = [
        "Repo", "Grade", "Score", "Interest", "Tier", "Badges",
        "Next Badge", "Language", "Commit Pattern", "Bus Factor",
        "Days Since Push", "Commits", "Releases", "Test Files",
        "LOC", "Libyears", "Stars", "Private", "Flags", "Description",
        "Biggest Drag", "Why This Grade", "Tech Novelty", "Burst", "Ambition", "Storytelling", "Trend",
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

        # Interest breakdown
        interest_d = details.get("interest", {})
        values.extend([
            round(interest_d.get("tech_novelty", 0), 2),
            round(interest_d.get("burst_coefficient", 0), 2),
            round(interest_d.get("ambition_score", 0), 2),
            round(interest_d.get("readme_storytelling", 0), 2),
        ])

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

        # Sparkline trend (column 27)
        if score_history and not native_sparklines:
            repo_name = m.get("name", "")
            scores = score_history.get(repo_name, [])
            spark = render_sparkline(scores)
            if spark:
                cell = ws.cell(row=row, column=27, value=spark)
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
        ws.conditional_formatting.add(
            f"C2:C{max_row}",
            IconSetRule('3TrafficLights1', 'num', [0, 0.55, 0.7]),
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

    _add_table(ws, "tblAllRepos", len(headers), max_row)
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


def _build_navigation(wb: Workbook, data: dict, *, excel_mode: str = "standard") -> None:
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
    if excel_mode == "template":
        sheets.extend(
            [
                ("Portfolio Explorer", "Profile-aware ranking and operator context"),
                ("By Lens", "Repo rankings split by decision lens"),
                ("By Collection", "Collection summaries and leaders"),
                ("Trend Summary", "Portfolio trend rollups and native sparkline views"),
                ("Scenario Planner", "Profile and collection lift preview"),
                ("Executive Summary", "Analyst-friendly summary view"),
                ("Print Pack", "Condensed print-oriented workbook summary"),
                ("Review Queue", "Current material changes and next manual steps"),
                ("Review History", "Recurring review run history"),
                ("Campaigns", "Managed campaign state"),
                ("Writeback Audit", "Safe writeback results"),
                ("Governance Controls", "Governed control preview"),
                ("Governance Audit", "Governance results and rollback coverage"),
            ]
        )

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


# ═══════════════════════════════════════════════════════════════════════
# Repo Profiles (Radar Charts)
# ═══════════════════════════════════════════════════════════════════════


RADAR_DIMS = ["readme", "structure", "code_quality", "testing", "cicd",
              "dependencies", "activity", "documentation", "build_readiness", "community_profile"]
RADAR_LABELS = ["README", "Structure", "Code Quality", "Testing", "CI/CD",
                "Deps", "Activity", "Docs", "Build Ready", "Community"]


def _build_repo_profiles(wb: Workbook, data: dict) -> None:
    ws = wb.create_sheet("Repo Profiles")
    ws.sheet_properties.tabColor = "7C3AED"

    audits = sorted(data.get("audits", []), key=lambda a: a.get("overall_score", 0), reverse=True)[:20]
    if len(audits) < 2:
        return

    # Write dimension labels in column A
    for i, label in enumerate(RADAR_LABELS):
        ws.cell(row=i + 2, column=1, value=label)

    # Write scores for each repo
    for col_idx, audit in enumerate(audits):
        dim_scores = {r["dimension"]: r["score"] for r in audit.get("analyzer_results", [])}
        ws.cell(row=1, column=col_idx + 2, value=audit["metadata"]["name"])
        for row_idx, dim in enumerate(RADAR_DIMS):
            ws.cell(row=row_idx + 2, column=col_idx + 2, value=round(dim_scores.get(dim, 0), 2))

    # Create radar charts (4 repos per chart)
    labels = Reference(ws, min_col=1, min_row=2, max_row=len(RADAR_DIMS) + 1)
    chart_row = len(RADAR_DIMS) + 4

    for batch_start in range(0, min(len(audits), 20), 4):
        batch_end = min(batch_start + 4, len(audits))
        chart = RadarChart()
        chart.type = "filled"
        chart.style = 26
        chart.title = f"Repos {batch_start + 1}-{batch_end}"
        chart.y_axis.delete = True

        chart_data = Reference(ws, min_col=batch_start + 2, max_col=batch_end + 1,
                               min_row=1, max_row=len(RADAR_DIMS) + 1)
        chart.add_data(chart_data, titles_from_data=True)
        chart.set_categories(labels)
        chart.width = 18
        chart.height = 14

        col_letter = "A" if (batch_start // 4) % 2 == 0 else "K"
        ws.add_chart(chart, f"{col_letter}{chart_row}")
        if (batch_start // 4) % 2 == 1:
            chart_row += 18


# ═══════════════════════════════════════════════════════════════════════
# Security Sheet
# ═══════════════════════════════════════════════════════════════════════


def _build_security(wb: Workbook, data: dict) -> None:
    ws = wb.create_sheet("Security")
    ws.sheet_properties.tabColor = "991B1B"

    headers = ["Repo", "Score", "Secrets", "Dangerous Files", "SECURITY.md", "Dependabot", "GitHub", "Findings"]
    for col, h in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=h)
    style_header_row(ws, 1, len(headers))

    audits = sorted(data.get("audits", []), key=lambda a: a.get("security_posture", {}).get("score", 1.0))

    for row, audit in enumerate(audits, 2):
        posture = audit.get("security_posture", {})
        local = posture.get("local", {})
        github = posture.get("github", {})
        m = audit.get("metadata", {})

        values = [
            m.get("name", ""),
            round(posture.get("score", 0), 2),
            local.get("secrets_found", posture.get("secrets_found", 0)),
            ", ".join(str(f) for f in local.get("dangerous_files", posture.get("dangerous_files", []))[:3]),
            "Yes" if posture.get("has_security_md") else "No",
            "Yes" if posture.get("has_dependabot") else "No",
            "Yes" if github.get("provider_available") else "No",
            "; ".join(posture.get("evidence", [])[:3]),
        ]
        for col, val in enumerate(values, 1):
            cell = ws.cell(row=row, column=col, value=val)
            style_data_cell(cell)

    max_row = len(audits) + 1
    if max_row > 1:
        ws.conditional_formatting.add(
            f"B2:B{max_row}",
            ColorScaleRule(start_type='num', start_value=0, start_color=HEATMAP_RED,
                           mid_type='num', mid_value=0.5, mid_color=HEATMAP_AMBER,
                           end_type='num', end_value=1, end_color=HEATMAP_GREEN),
        )
        ws.conditional_formatting.add(
            f"B2:B{max_row}",
            IconSetRule('3TrafficLights1', 'num', [0, 0.4, 0.7]),
        )

    apply_zebra_stripes(ws, 2, max_row, len(headers))
    _add_table(ws, "tblSecurity", len(headers), max_row)
    auto_width(ws, len(headers), max_row)


# ═══════════════════════════════════════════════════════════════════════
# Changes Since Last Audit (Diff Sheet)
# ═══════════════════════════════════════════════════════════════════════


def _build_changes(wb: Workbook, data: dict, diff_data: dict | None) -> None:
    if not diff_data:
        return

    ws = wb.create_sheet("Changes")
    ws.sheet_properties.tabColor = "0891B2"

    # Title
    ws.merge_cells("A1:F1")
    ws["A1"].value = "Changes Since Last Audit"
    ws["A1"].font = TITLE_FONT

    # KPI summary
    tier_changes = diff_data.get("tier_changes", [])
    promos = [c for c in tier_changes if c.get("direction") == "promotion"]
    demos = [c for c in tier_changes if c.get("direction") == "demotion"]
    avg_delta = diff_data.get("average_score_delta", 0)

    ws.cell(row=3, column=1, value="Promotions").font = SUBHEADER_FONT
    ws.cell(row=3, column=2, value=len(promos))
    ws.cell(row=3, column=3, value="Demotions").font = SUBHEADER_FONT
    ws.cell(row=3, column=4, value=len(demos))
    ws.cell(row=3, column=5, value="Avg Score Delta").font = SUBHEADER_FONT
    ws.cell(row=3, column=6, value=round(avg_delta, 4))

    # Tier changes table
    row = 5
    if tier_changes:
        ws.cell(row=row, column=1, value="Tier Changes").font = SECTION_FONT
        row += 1
        for col, h in enumerate(["Repo", "Old Tier", "New Tier", "Old Score", "New Score", "Direction"], 1):
            ws.cell(row=row, column=col, value=h)
        style_header_row(ws, row, 6)
        row += 1

        for change in tier_changes:
            ws.cell(row=row, column=1, value=change.get("name", ""))
            ws.cell(row=row, column=2, value=change.get("old_tier", ""))
            ws.cell(row=row, column=3, value=change.get("new_tier", ""))
            ws.cell(row=row, column=4, value=round(change.get("old_score", 0), 3))
            ws.cell(row=row, column=5, value=round(change.get("new_score", 0), 3))
            direction = change.get("direction", "")
            cell = ws.cell(row=row, column=6, value=direction)
            if direction == "promotion":
                cell.font = Font("Calibri", 10, bold=True, color="166534")
            elif direction == "demotion":
                cell.font = Font("Calibri", 10, bold=True, color="991B1B")
            row += 1

    # Significant score changes
    score_changes = [c for c in diff_data.get("score_changes", []) if abs(c.get("delta", 0)) > 0.05]
    if score_changes:
        row += 2
        ws.cell(row=row, column=1, value="Significant Score Changes").font = SECTION_FONT
        row += 1
        for col, h in enumerate(["Repo", "Old Score", "New Score", "Delta"], 1):
            ws.cell(row=row, column=col, value=h)
        style_header_row(ws, row, 4)
        row += 1

        for change in sorted(score_changes, key=lambda c: c.get("delta", 0), reverse=True):
            ws.cell(row=row, column=1, value=change.get("name", ""))
            ws.cell(row=row, column=2, value=round(change.get("old_score", 0), 3))
            ws.cell(row=row, column=3, value=round(change.get("new_score", 0), 3))
            delta = change.get("delta", 0)
            cell = ws.cell(row=row, column=4, value=round(delta, 4))
            cell.font = Font("Calibri", 10, bold=True, color="166534" if delta > 0 else "991B1B")
            row += 1

    auto_width(ws, 6, row)


# ═══════════════════════════════════════════════════════════════════════
# Bubble Chart helper for Dashboard
# ═══════════════════════════════════════════════════════════════════════


def _build_bubble_on_dashboard(ws, data: dict) -> None:
    """Add a bubble chart: x=completeness, y=interest, size=LOC."""
    audits = data.get("audits", [])
    if len(audits) < 2:
        return

    # Write bubble data to spare columns (cols 20-22)
    bcol_x, bcol_y, bcol_z = 20, 21, 22
    data_start = 10

    for i, audit in enumerate(audits):
        row = data_start + i
        cq = next((r.get("details", {}) for r in audit.get("analyzer_results", []) if r["dimension"] == "code_quality"), {})
        loc = cq.get("total_loc", 100)
        ws.cell(row=row, column=bcol_x, value=round(audit.get("overall_score", 0), 3))
        ws.cell(row=row, column=bcol_y, value=round(audit.get("interest_score", 0), 3))
        ws.cell(row=row, column=bcol_z, value=max(loc, 10))  # Min size to be visible

    data_end = data_start + len(audits) - 1

    chart = BubbleChart()
    chart.title = "Portfolio Map (size = LOC)"
    chart.x_axis.title = "Completeness"
    chart.y_axis.title = "Interest"
    chart.x_axis.scaling.min = 0
    chart.x_axis.scaling.max = 1
    chart.y_axis.scaling.min = 0
    chart.y_axis.scaling.max = 1
    chart.style = 18

    xvalues = Reference(ws, min_col=bcol_x, min_row=data_start, max_row=data_end)
    yvalues = Reference(ws, min_col=bcol_y, min_row=data_start, max_row=data_end)
    sizes = Reference(ws, min_col=bcol_z, min_row=data_start, max_row=data_end)
    series = BubbleSeries(values=yvalues, xvalues=xvalues, zvalues=sizes, title="Repos")
    chart.series.append(series)

    chart.width = 16
    chart.height = 12
    ws.add_chart(chart, "A50")


# ═══════════════════════════════════════════════════════════════════════
# Dependency Graph Sheet
# ═══════════════════════════════════════════════════════════════════════


def _build_dependency_graph(wb: Workbook, data: dict) -> None:
    from src.dep_graph import build_dependency_graph

    ws = wb.create_sheet("Dep Graph")
    ws.sheet_properties.tabColor = "0277BD"

    graph = build_dependency_graph(data.get("audits", []))
    shared = graph.get("shared_deps", [])

    ws.merge_cells("A1:C1")
    ws["A1"].value = f"Shared Dependencies ({len(shared)} across 2+ repos)"
    ws["A1"].font = SECTION_FONT

    headers = ["Dependency", "Repo Count", "Repos Using It"]
    for col, h in enumerate(headers, 1):
        ws.cell(row=2, column=col, value=h)
    style_header_row(ws, 2, len(headers))
    ws.freeze_panes = "A3"

    for row, dep in enumerate(shared, 3):
        ws.cell(row=row, column=1, value=dep["name"])
        ws.cell(row=row, column=2, value=dep["count"])
        ws.cell(row=row, column=3, value=", ".join(dep["repos"]))
        for col in range(1, 4):
            style_data_cell(ws.cell(row=row, column=col))

    max_row = len(shared) + 2
    if max_row > 2:
        ws.conditional_formatting.add(
            f"B3:B{max_row}",
            ColorScaleRule(
                start_type="min", start_color=HEATMAP_AMBER,
                end_type="max", end_color=HEATMAP_GREEN,
            ),
        )

    apply_zebra_stripes(ws, 3, max_row, len(headers))
    auto_width(ws, len(headers), max_row)


def _build_hotspots(wb: Workbook, data: dict) -> None:
    ws = wb.create_sheet("Hotspots")
    ws.sheet_properties.tabColor = "DC2626"

    headers = ["Repo", "Category", "Severity", "Title", "Summary", "Recommended Action", "Tier"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws, 1, len(headers))

    hotspots = data.get("hotspots", [])
    for row, hotspot in enumerate(hotspots, 2):
        values = [
            hotspot.get("repo", ""),
            hotspot.get("category", ""),
            round(hotspot.get("severity", 0), 3),
            hotspot.get("title", ""),
            hotspot.get("summary", ""),
            hotspot.get("recommended_action", ""),
            hotspot.get("tier", ""),
        ]
        for col, value in enumerate(values, 1):
            cell = ws.cell(row=row, column=col, value=value)
            style_data_cell(cell, "center" if col in {3, 7} else "left")

    max_row = len(hotspots) + 1
    if max_row > 1:
        ws.conditional_formatting.add(
            f"C2:C{max_row}",
            DataBarRule(start_type="num", start_value=0, end_type="num", end_value=1, color="DC2626"),
        )
        apply_zebra_stripes(ws, 2, max_row, len(headers))
        _add_table(ws, "tblHotspots", len(headers), max_row)
    auto_width(ws, len(headers), max_row)


def _write_hidden_table_sheet(
    wb: Workbook,
    title: str,
    table_name: str,
    headers: list[str],
    rows: list[list[object]],
) -> None:
    ws = wb.create_sheet(title)
    ws.sheet_state = "hidden"
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws, 1, len(headers))

    for row_index, row_values in enumerate(rows, 2):
        for col_index, value in enumerate(row_values, 1):
            cell = ws.cell(row=row_index, column=col_index, value=value)
            style_data_cell(cell, "center" if isinstance(value, (int, float)) else "left")

    max_row = len(rows) + 1
    if max_row > 1:
        _add_table(ws, table_name, len(headers), max_row)
        apply_zebra_stripes(ws, 2, max_row, len(headers))
    auto_width(ws, len(headers), max_row)


def _build_hidden_data_sheets(
    wb: Workbook,
    data: dict,
    trend_data: list[dict] | None = None,
    score_history: dict[str, list[float]] | None = None,
) -> None:
    audits = data.get("audits", [])
    memberships = _collection_memberships(data)
    extended_score_history = _extend_score_history_with_current(data, score_history)
    extended_trends = _extend_portfolio_trend_with_current(data, trend_data)

    repo_rows: list[list[object]] = []
    dimension_rows: list[list[object]] = []
    lens_rows: list[list[object]] = []
    history_rows: list[list[object]] = []
    trend_matrix_rows: list[list[object]] = []
    portfolio_history_rows: list[list[object]] = []
    rollup_rows: list[list[object]] = []
    review_target_rows: list[list[object]] = []
    security_rows: list[list[object]] = []
    security_control_rows: list[list[object]] = []
    security_provider_rows: list[list[object]] = []
    security_alert_rows: list[list[object]] = []
    action_rows: list[list[object]] = []
    collection_rows: list[list[object]] = []
    scenario_rows: list[list[object]] = []
    governance_rows: list[list[object]] = []
    campaign_rows: list[list[object]] = []
    writeback_rows: list[list[object]] = []
    review_rows: list[list[object]] = []
    review_history_rows: list[list[object]] = []
    lookup_rows: list[list[object]] = []

    for audit in audits:
        metadata = audit.get("metadata", {})
        repo_name = metadata.get("name", "")
        lenses = audit.get("lenses", {})
        repo_rows.append([
            repo_name,
            metadata.get("full_name", ""),
            metadata.get("language") or "Unknown",
            "Yes" if metadata.get("private") else "No",
            "Yes" if metadata.get("archived") else "No",
            round(audit.get("overall_score", 0), 3),
            round(audit.get("interest_score", 0), 3),
            audit.get("grade", ""),
            audit.get("completeness_tier", ""),
            audit.get("security_posture", {}).get("label", "unknown"),
            ", ".join(memberships.get(repo_name, [])),
            lenses.get("ship_readiness", {}).get("score", 0.0),
            lenses.get("maintenance_risk", {}).get("score", 0.0),
            lenses.get("showcase_value", {}).get("score", 0.0),
            lenses.get("security_posture", {}).get("score", 0.0),
            lenses.get("momentum", {}).get("score", 0.0),
            lenses.get("portfolio_fit", {}).get("score", 0.0),
        ])

        for result in audit.get("analyzer_results", []):
            dimension_rows.append([
                repo_name,
                result.get("dimension", ""),
                result.get("score", 0.0),
                result.get("max_score", 1.0),
                "; ".join(result.get("findings", [])[:3]),
            ])

        for lens_name, lens_data in lenses.items():
            lens_rows.append([
                repo_name,
                lens_name,
                lens_data.get("score", 0.0),
                lens_data.get("orientation", ""),
                lens_data.get("summary", ""),
                ", ".join(lens_data.get("drivers", [])),
            ])

        posture = audit.get("security_posture", {})
        security_rows.append([
            repo_name,
            posture.get("label", "unknown"),
            posture.get("score", 0.0),
            posture.get("secrets_found", 0),
            len(posture.get("dangerous_files", [])),
            "Yes" if posture.get("has_security_md") else "No",
            "Yes" if posture.get("has_dependabot") else "No",
            "; ".join(posture.get("evidence", [])),
        ])
        github = posture.get("github", {})
        security_control_rows.extend([
            [repo_name, "security_md", "enabled" if posture.get("has_security_md") else "missing", "local", ""],
            [repo_name, "dependabot_config", "enabled" if posture.get("has_dependabot") else "missing", "local", ""],
            [repo_name, "dependency_graph", github.get("dependency_graph_status", "unavailable"), "github", str(github.get("dependency_graph_enabled"))],
            [repo_name, "sbom_export", github.get("sbom_status", "unavailable"), "github", str(github.get("sbom_exportable"))],
            [repo_name, "code_scanning", github.get("code_scanning_status", "unavailable"), "github", str(github.get("code_scanning_alerts"))],
            [repo_name, "secret_scanning", github.get("secret_scanning_status", "unavailable"), "github", str(github.get("secret_scanning_alerts"))],
        ])
        for provider_name, provider_data in (posture.get("providers") or {}).items():
            security_provider_rows.append([
                repo_name,
                provider_name,
                "Yes" if provider_data.get("available") else "No",
                provider_data.get("score", ""),
                posture.get(provider_name, {}).get("reason", "") if provider_name != "local" else "",
            ])
        security_alert_rows.append([
            repo_name,
            "code_scanning",
            github.get("code_scanning_alerts") or 0,
            github.get("code_scanning_status", "unavailable"),
        ])
        security_alert_rows.append([
            repo_name,
            "secret_scanning",
            github.get("secret_scanning_alerts") or 0,
            github.get("secret_scanning_status", "unavailable"),
        ])
        for recommendation in posture.get("recommendations", []):
            governance_rows.append([
                repo_name,
                recommendation.get("key", ""),
                recommendation.get("priority", "medium"),
                recommendation.get("title", ""),
                recommendation.get("expected_posture_lift", 0.0),
                recommendation.get("effort", ""),
                recommendation.get("source", ""),
                recommendation.get("why", ""),
            ])

        for action in audit.get("action_candidates", []):
            action_rows.append([
                repo_name,
                action.get("key", ""),
                action.get("title", ""),
                action.get("lens", ""),
                action.get("effort", ""),
                action.get("confidence", 0.0),
                action.get("expected_lens_delta", 0.0),
                action.get("expected_tier_movement", ""),
                action.get("rationale", ""),
            ])

    if extended_score_history:
        for repo_name, scores in extended_score_history.items():
            for run_index, score in enumerate(scores, 1):
                history_rows.append([repo_name, run_index, score])

    if extended_trends:
        for run_index, trend in enumerate(extended_trends, 1):
            history_rows.append([
                "__portfolio__",
                run_index,
                trend.get("average_score", 0.0),
            ])
            tier_distribution = trend.get("tier_distribution", {})
            portfolio_history_rows.append([
                run_index,
                trend.get("date", ""),
                round(trend.get("average_score", 0.0), 3),
                trend.get("repos_audited", 0),
                tier_distribution.get("shipped", 0),
                tier_distribution.get("functional", 0),
                round(data.get("security_posture", {}).get("average_score", 0.0), 3),
                "yes" if any(item.get("emitted") for item in data.get("review_history", [])) else "no",
                sum(1 for item in data.get("managed_state_drift", []) if item),
                sum(1 for item in data.get("governance_drift", []) if item),
            ])

    for audit in sorted(audits, key=lambda item: item.get("overall_score", 0), reverse=True):
        repo_name = audit.get("metadata", {}).get("name", "")
        scores = extended_score_history.get(repo_name, [])
        if not repo_name:
            continue
        trend_matrix_rows.append(
            [repo_name] + [round(score, 3) for score in scores[-TREND_HISTORY_WINDOW:]] + [""] * max(0, TREND_HISTORY_WINDOW - len(scores))
        )

    for collection_name, collection_data in data.get("collections", {}).items():
        for rank_index, repo_data in enumerate(collection_data.get("repos", []), 1):
            repo_name = repo_data["name"] if isinstance(repo_data, dict) else str(repo_data)
            reason = repo_data.get("reason", "") if isinstance(repo_data, dict) else ""
            collection_rows.append([
                collection_name,
                repo_name,
                rank_index,
                reason,
                collection_data.get("description", ""),
            ])

    scenario_summary = data.get("scenario_summary", {})
    for lever in scenario_summary.get("top_levers", []):
        scenario_rows.append([
            lever.get("key", ""),
            lever.get("title", ""),
            lever.get("lens", ""),
            lever.get("repo_count", 0),
            lever.get("average_expected_lens_delta", 0.0),
            lever.get("projected_tier_promotions", 0),
        ])
    projection = scenario_summary.get("portfolio_projection", {})
    if projection:
        scenario_rows.append([
            "portfolio_projection",
            "Portfolio projection",
            "portfolio_fit",
            projection.get("projected_shipped", 0),
            projection.get("projected_average_score_delta", 0.0),
            projection.get("current_shipped", 0),
        ])

    for lens_name, lens_data in data.get("lenses", {}).items():
        lookup_rows.append(["lens", lens_name, lens_data.get("description", "")])
    for profile_name, profile_data in data.get("profiles", {}).items():
        lookup_rows.append(["profile", profile_name, profile_data.get("description", "")])
    for tier_name in TIER_ORDER:
        lookup_rows.append(["tier", tier_name, str(data.get("tier_distribution", {}).get(tier_name, 0))])
    campaign_summary = data.get("campaign_summary", {})
    if campaign_summary:
        campaign_rows.append([
            campaign_summary.get("campaign_type", ""),
            campaign_summary.get("label", ""),
            campaign_summary.get("portfolio_profile", "default"),
            campaign_summary.get("collection_name", ""),
            campaign_summary.get("action_count", 0),
            campaign_summary.get("repo_count", 0),
        ])
    for result in data.get("writeback_results", {}).get("results", []):
        writeback_rows.append([
            result.get("repo_full_name", ""),
            result.get("target", ""),
            result.get("status", ""),
            result.get("url", ""),
            json.dumps(result.get("before", {})),
            json.dumps(result.get("after", {})),
        ])

    from src.analyst_views import build_analyst_context

    profile_names = list(data.get("profiles", {}).keys()) or ["default"]
    collection_names = [None] + list(data.get("collections", {}).keys())
    lens_names = list(data.get("lenses", {}).keys()) or [
        "ship_readiness",
        "maintenance_risk",
        "showcase_value",
        "security_posture",
        "momentum",
        "portfolio_fit",
    ]
    for profile_name in profile_names:
        for collection_name in collection_names:
            context = build_analyst_context(
                data,
                profile_name=profile_name,
                collection_name=collection_name,
            )
            ranked = context.get("ranked_audits", [])
            top_repo = ranked[0]["name"] if ranked else ""
            for lens_name in lens_names:
                scores = [
                    entry["audit"].get("lenses", {}).get(lens_name, {}).get("score", 0.0)
                    for entry in ranked
                ]
                rollup_rows.append([
                    profile_name,
                    collection_name or "all",
                    lens_name,
                    len(ranked),
                    round(sum(scores) / len(scores), 3) if scores else 0.0,
                    top_repo,
                    round(ranked[0]["profile_score"], 3) if ranked else 0.0,
                ])

    safe_to_defer = "yes" if data.get("review_summary", {}).get("safe_to_defer") else "no"
    for change in data.get("material_changes", []):
        review_rows.append([
            change.get("change_key", ""),
            change.get("change_type", ""),
            change.get("repo_name", ""),
            change.get("severity", 0.0),
            change.get("title", ""),
            change.get("recommended_next_step", ""),
        ])
    for target in data.get("review_targets", []):
        review_target_rows.append([
            target.get("repo_name", "") or "portfolio",
            target.get("title", ""),
            target.get("severity", 0.0),
            target.get("recommended_next_step", ""),
            target.get("decision_hint", ""),
            safe_to_defer,
        ])
    if not review_target_rows:
        for change in data.get("material_changes", []):
            review_target_rows.append([
                change.get("repo_name", "") or "portfolio",
                change.get("title", ""),
                change.get("severity", 0.0),
                change.get("recommended_next_step", ""),
                "inspect-change",
                safe_to_defer,
            ])
    for item in data.get("review_history", []):
        review_history_rows.append([
            item.get("review_id", ""),
            item.get("source_run_id", ""),
            item.get("generated_at", ""),
            item.get("materiality", ""),
            item.get("material_change_count", 0),
            "yes" if item.get("safe_to_defer") else "no",
            "yes" if item.get("emitted") else "no",
        ])

    _write_hidden_table_sheet(
        wb,
        "Data_Repos",
        "tblRepos",
        [
            "Repo", "Full Name", "Language", "Private", "Archived", "Overall Score",
            "Interest Score", "Grade", "Tier", "Security Label", "Collections",
            "Ship Readiness", "Maintenance Risk", "Showcase Value",
            "Security Posture", "Momentum", "Portfolio Fit",
        ],
        repo_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_Dimensions",
        "tblDimensions",
        ["Repo", "Dimension", "Score", "Max Score", "Findings"],
        dimension_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_Lenses",
        "tblLenses",
        ["Repo", "Lens", "Score", "Orientation", "Summary", "Drivers"],
        lens_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_History",
        "tblHistory",
        ["Series", "Run Index", "Score"],
        history_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_TrendMatrix",
        "tblTrendMatrix",
        ["Repo"] + [f"Run {index}" for index in range(1, TREND_HISTORY_WINDOW + 1)],
        trend_matrix_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_PortfolioHistory",
        "tblPortfolioHistory",
        [
            "Run Index",
            "Date",
            "Average Score",
            "Repos Audited",
            "Shipped",
            "Functional",
            "Security Avg",
            "Review Emitted",
            "Campaign Drift",
            "Governance Drift",
        ],
        portfolio_history_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_Rollups",
        "tblRollups",
        ["Profile", "Collection", "Lens", "Repo Count", "Average Lens Score", "Top Repo", "Top Profile Score"],
        rollup_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_ReviewTargets",
        "tblReviewTargets",
        ["Repo", "Title", "Severity", "Next Step", "Decision Hint", "Safe To Defer"],
        review_target_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_Security",
        "tblSecurityData",
        ["Repo", "Label", "Score", "Secrets", "Dangerous Files", "SECURITY.md", "Dependabot", "Evidence"],
        security_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_SecurityControls",
        "tblSecurityControls",
        ["Repo", "Control", "Status", "Source", "Details"],
        security_control_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_SecurityProviders",
        "tblSecurityProviders",
        ["Repo", "Provider", "Available", "Score", "Reason"],
        security_provider_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_SecurityAlerts",
        "tblSecurityAlerts",
        ["Repo", "Alert Type", "Open Count", "Status"],
        security_alert_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_Actions",
        "tblActions",
        ["Repo", "Key", "Title", "Lens", "Effort", "Confidence", "Expected Lens Delta", "Expected Tier Movement", "Rationale"],
        action_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_Collections",
        "tblCollections",
        ["Collection", "Repo", "Rank", "Reason", "Description"],
        collection_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_Scenarios",
        "tblScenarios",
        ["Key", "Title", "Lens", "Repo Count", "Average Expected Lens Delta", "Projected Tier Promotions"],
        scenario_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_Governance",
        "tblGovernancePreview",
        ["Repo", "Key", "Priority", "Title", "Expected Lift", "Effort", "Source", "Why"],
        governance_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_Campaigns",
        "tblCampaigns",
        ["Campaign Type", "Label", "Profile", "Collection", "Actions", "Repos"],
        campaign_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_Writeback",
        "tblWriteback",
        ["Repo", "Target", "Status", "URL", "Before", "After"],
        writeback_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_Review",
        "tblReview",
        ["Change Key", "Change Type", "Repo", "Severity", "Title", "Next Step"],
        review_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Data_ReviewHistory",
        "tblReviewHistoryData",
        ["Review ID", "Source Run", "Generated", "Materiality", "Changes", "Safe To Defer", "Emitted"],
        review_history_rows,
    )
    _write_hidden_table_sheet(
        wb,
        "Lookups",
        "tblLookups",
        ["Type", "Key", "Value"],
        lookup_rows,
    )


def _build_security_controls(wb: Workbook, data: dict) -> None:
    ws = wb.create_sheet("Security Controls")
    ws.sheet_properties.tabColor = "0F766E"
    headers = ["Repo", "SECURITY.md", "Dependabot", "Dependency Graph", "SBOM", "Code Scanning", "Secret Scanning"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws, 1, len(headers))

    audits = sorted(data.get("audits", []), key=lambda audit: audit.get("security_posture", {}).get("score", 0.0))
    for row, audit in enumerate(audits, 2):
        posture = audit.get("security_posture", {})
        github = posture.get("github", {})
        values = [
            audit.get("metadata", {}).get("name", ""),
            "Yes" if posture.get("has_security_md") else "No",
            "Yes" if posture.get("has_dependabot") else "No",
            github.get("dependency_graph_status", "unavailable"),
            github.get("sbom_status", "unavailable"),
            github.get("code_scanning_status", "unavailable"),
            github.get("secret_scanning_status", "unavailable"),
        ]
        for col, value in enumerate(values, 1):
            style_data_cell(ws.cell(row=row, column=col, value=value), "left" if col == 1 else "center")

    max_row = len(audits) + 1
    if max_row > 1:
        apply_zebra_stripes(ws, 2, max_row, len(headers))
        _add_table(ws, "tblSecurityControlsView", len(headers), max_row)
    auto_width(ws, len(headers), max_row)


def _build_supply_chain(wb: Workbook, data: dict) -> None:
    ws = wb.create_sheet("Supply Chain")
    ws.sheet_properties.tabColor = "7C3AED"
    headers = ["Repo", "Security Score", "Dependency Graph", "SBOM", "Scorecard", "Top Recommendation"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws, 1, len(headers))

    audits = sorted(data.get("audits", []), key=lambda audit: audit.get("security_posture", {}).get("score", 0.0))
    for row, audit in enumerate(audits, 2):
        posture = audit.get("security_posture", {})
        github = posture.get("github", {})
        scorecard = posture.get("scorecard", {})
        recommendation = next(iter(posture.get("recommendations", [])), {})
        values = [
            audit.get("metadata", {}).get("name", ""),
            posture.get("score", 0.0),
            github.get("dependency_graph_status", "unavailable"),
            github.get("sbom_status", "unavailable"),
            scorecard.get("score", ""),
            recommendation.get("title", ""),
        ]
        for col, value in enumerate(values, 1):
            style_data_cell(ws.cell(row=row, column=col, value=value), "center" if col != 1 and col != 6 else "left")

    max_row = len(audits) + 1
    if max_row > 1:
        apply_zebra_stripes(ws, 2, max_row, len(headers))
        _add_table(ws, "tblSupplyChain", len(headers), max_row)
    auto_width(ws, len(headers), max_row)


def _build_security_debt(wb: Workbook, data: dict) -> None:
    ws = wb.create_sheet("Security Debt")
    ws.sheet_properties.tabColor = "B91C1C"
    headers = ["Repo", "Priority", "Action", "Expected Lift", "Effort", "Source"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws, 1, len(headers))

    preview = data.get("security_governance_preview", [])
    for row, item in enumerate(preview, 2):
        values = [
            item.get("repo", ""),
            item.get("priority", "medium"),
            item.get("title", ""),
            item.get("expected_posture_lift", 0.0),
            item.get("effort", ""),
            item.get("source", ""),
        ]
        for col, value in enumerate(values, 1):
            style_data_cell(ws.cell(row=row, column=col, value=value), "center" if col in {2, 4, 5, 6} else "left")

    max_row = len(preview) + 1
    if max_row > 1:
        apply_zebra_stripes(ws, 2, max_row, len(headers))
        _add_table(ws, "tblSecurityDebt", len(headers), max_row)
    auto_width(ws, len(headers), max_row)


def _build_campaigns(wb: Workbook, data: dict) -> None:
    ws = wb.create_sheet("Campaigns")
    ws.sheet_properties.tabColor = "7C3AED"
    summary = data.get("campaign_summary", {})
    ws["A1"] = "Campaigns"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = f"Campaign: {summary.get('label', summary.get('campaign_type', '—'))}"
    ws["A3"] = f"Profile: {summary.get('portfolio_profile', 'default')}"
    ws["A4"] = f"Collection: {summary.get('collection_name') or 'all'}"
    ws["A5"] = f"Actions: {summary.get('action_count', 0)}"
    ws["A6"] = f"Repos: {summary.get('repo_count', 0)}"
    headers = ["Repo", "Issue", "Topics", "Notion Actions", "Action IDs"]
    start_row = 8
    for col, header in enumerate(headers, 1):
        ws.cell(row=start_row, column=col, value=header)
    style_header_row(ws, start_row, len(headers))

    preview_rows = data.get("writeback_preview", {}).get("repos", [])
    for row, item in enumerate(preview_rows, start_row + 1):
        ws.cell(row=row, column=1, value=item.get("repo", ""))
        ws.cell(row=row, column=2, value=item.get("issue_title", ""))
        ws.cell(row=row, column=3, value=", ".join(item.get("topics", [])))
        ws.cell(row=row, column=4, value=item.get("notion_action_count", 0))
        ws.cell(row=row, column=5, value=", ".join(item.get("action_ids", [])))

    max_row = start_row + len(preview_rows)
    if preview_rows:
        apply_zebra_stripes(ws, start_row + 1, max_row, len(headers))
        _add_table(ws, "tblCampaignView", len(headers), max_row, start_row)
    auto_width(ws, len(headers), max_row)


def _build_writeback_audit(wb: Workbook, data: dict) -> None:
    ws = wb.create_sheet("Writeback Audit")
    ws.sheet_properties.tabColor = "B91C1C"
    headers = ["Repo", "Target", "Status", "URL", "Details"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws, 1, len(headers))

    results = data.get("writeback_results", {}).get("results", [])
    for row, result in enumerate(results, 2):
        ws.cell(row=row, column=1, value=result.get("repo_full_name", ""))
        ws.cell(row=row, column=2, value=result.get("target", ""))
        ws.cell(row=row, column=3, value=result.get("status", ""))
        ws.cell(row=row, column=4, value=result.get("url", ""))
        ws.cell(row=row, column=5, value=json.dumps(result))

    max_row = len(results) + 1
    if results:
        apply_zebra_stripes(ws, 2, max_row, len(headers))
        _add_table(ws, "tblWritebackAudit", len(headers), max_row)
    auto_width(ws, len(headers), max_row)


def _build_governance_controls(wb: Workbook, data: dict) -> None:
    ws = wb.create_sheet("Governance Controls")
    ws.sheet_properties.tabColor = "0F766E"
    headers = ["Repo", "Control", "Applyable", "Preview Only", "Prerequisites", "Expected Lift", "Reason"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws, 1, len(headers))
    rows = data.get("governance_preview", {}).get("actions", [])
    for row, item in enumerate(rows, 2):
        ws.cell(row=row, column=1, value=item.get("repo", ""))
        ws.cell(row=row, column=2, value=item.get("control_key", ""))
        ws.cell(row=row, column=3, value="yes" if item.get("applyable") else "no")
        ws.cell(row=row, column=4, value="yes" if item.get("preview_only") else "no")
        ws.cell(row=row, column=5, value=", ".join(item.get("prerequisites", [])))
        ws.cell(row=row, column=6, value=item.get("expected_posture_lift", 0.0))
        ws.cell(row=row, column=7, value=item.get("skip_reason", item.get("why", "")))
    max_row = len(rows) + 1
    if rows:
        apply_zebra_stripes(ws, 2, max_row, len(headers))
        _add_table(ws, "tblGovernanceControls", len(headers), max_row)
    auto_width(ws, len(headers), max_row)


def _build_governance_audit(wb: Workbook, data: dict) -> None:
    ws = wb.create_sheet("Governance Audit")
    ws.sheet_properties.tabColor = "155E75"
    headers = ["Repo", "Target", "Status", "Control", "Rollback", "Reason"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws, 1, len(headers))
    rows = data.get("governance_results", {}).get("results", [])
    for row, item in enumerate(rows, 2):
        ws.cell(row=row, column=1, value=item.get("repo", item.get("repo_full_name", "")))
        ws.cell(row=row, column=2, value=item.get("target", ""))
        ws.cell(row=row, column=3, value=item.get("status", ""))
        ws.cell(row=row, column=4, value=item.get("control_key", ""))
        ws.cell(row=row, column=5, value="yes" if item.get("rollback_available") else "no")
        ws.cell(row=row, column=6, value=item.get("reason", item.get("drift_type", "")))
    max_row = len(rows) + 1
    if rows:
        apply_zebra_stripes(ws, 2, max_row, len(headers))
        _add_table(ws, "tblGovernanceAudit", len(headers), max_row)
    auto_width(ws, len(headers), max_row)


def _build_review_queue(wb: Workbook, data: dict) -> None:
    ws = wb.create_sheet("Review Queue")
    ws.sheet_properties.tabColor = "2563EB"
    headers = ["Change", "Repo", "Severity", "Next Step", "Safe To Defer"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws, 1, len(headers))
    rows = data.get("material_changes", [])
    safe = "yes" if data.get("review_summary", {}).get("safe_to_defer") else "no"
    for row, item in enumerate(rows, 2):
        values = [
            item.get("title", ""),
            item.get("repo_name", "") or "portfolio",
            item.get("severity", 0.0),
            item.get("recommended_next_step", ""),
            safe,
        ]
        for col, value in enumerate(values, 1):
            style_data_cell(ws.cell(row=row, column=col, value=value), "center" if col in {3, 5} else "left")
    max_row = len(rows) + 1
    if rows:
        apply_zebra_stripes(ws, 2, max_row, len(headers))
        _add_table(ws, "tblReviewQueue", len(headers), max_row)
    auto_width(ws, len(headers), max_row)


def _build_review_history_sheet(wb: Workbook, data: dict) -> None:
    ws = wb.create_sheet("Review History")
    ws.sheet_properties.tabColor = "1D4ED8"
    headers = ["Generated", "Source Run", "Materiality", "Changes", "Safe To Defer", "Emitted"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws, 1, len(headers))
    rows = data.get("review_history", [])
    for row, item in enumerate(rows, 2):
        values = [
            item.get("generated_at", ""),
            item.get("source_run_id", ""),
            item.get("materiality", ""),
            item.get("material_change_count", 0),
            "yes" if item.get("safe_to_defer") else "no",
            "yes" if item.get("emitted") else "no",
        ]
        for col, value in enumerate(values, 1):
            style_data_cell(ws.cell(row=row, column=col, value=value), "center" if col >= 3 else "left")
    max_row = len(rows) + 1
    if rows:
        apply_zebra_stripes(ws, 2, max_row, len(headers))
        _add_table(ws, "tblReviewHistory", len(headers), max_row)
    auto_width(ws, len(headers), max_row)


def _build_portfolio_explorer(
    wb: Workbook,
    data: dict,
    *,
    portfolio_profile: str = "default",
    collection: str | None = None,
) -> None:
    from src.analyst_views import build_analyst_context

    context = build_analyst_context(data, profile_name=portfolio_profile, collection_name=collection)
    ws = wb.create_sheet("Portfolio Explorer")
    ws.sheet_properties.tabColor = "1D4ED8"
    headers = [
        "Repo", "Profile Score", "Overall", "Interest", "Tier", "Collections",
        "Security", "Hotspots", "Top Hotspot", "Primary Action",
    ]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws, 1, len(headers))

    for row, entry in enumerate(context["ranked_audits"], 2):
        audit = entry["audit"]
        top_action = audit.get("action_candidates", [{}])[0].get("title", "") if audit.get("action_candidates") else ""
        values = [
            entry["name"],
            entry["profile_score"],
            entry["overall_score"],
            entry["interest_score"],
            entry["tier"],
            ", ".join(entry["collections"]),
            entry["security_label"],
            entry["hotspot_count"],
            entry["primary_hotspot"],
            top_action,
        ]
        for col, value in enumerate(values, 1):
            style_data_cell(ws.cell(row=row, column=col, value=value), "center" if col in {2, 3, 4, 8} else "left")

    max_row = len(context["ranked_audits"]) + 1
    if max_row > 1:
        apply_zebra_stripes(ws, 2, max_row, len(headers))
        _add_table(ws, "tblPortfolioExplorer", len(headers), max_row)
    auto_width(ws, len(headers), max_row)


def _build_by_lens(
    wb: Workbook,
    data: dict,
    *,
    portfolio_profile: str = "default",
    collection: str | None = None,
) -> None:
    from src.analyst_views import build_analyst_context

    context = build_analyst_context(data, profile_name=portfolio_profile, collection_name=collection)
    ws = wb.create_sheet("By Lens")
    ws.sheet_properties.tabColor = "0F766E"
    lens_headers = ["Ship Readiness", "Maintenance Risk", "Showcase", "Security", "Momentum", "Portfolio Fit"]
    headers = ["Repo", "Profile Score", "Tier"] + lens_headers
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws, 1, len(headers))

    for row, entry in enumerate(context["ranked_audits"], 2):
        lenses = entry["audit"].get("lenses", {})
        values = [
            entry["name"],
            entry["profile_score"],
            entry["tier"],
            lenses.get("ship_readiness", {}).get("score", 0.0),
            lenses.get("maintenance_risk", {}).get("score", 0.0),
            lenses.get("showcase_value", {}).get("score", 0.0),
            lenses.get("security_posture", {}).get("score", 0.0),
            lenses.get("momentum", {}).get("score", 0.0),
            lenses.get("portfolio_fit", {}).get("score", 0.0),
        ]
        for col, value in enumerate(values, 1):
            style_data_cell(ws.cell(row=row, column=col, value=value), "center" if col >= 2 else "left")

    max_row = len(context["ranked_audits"]) + 1
    if max_row > 1:
        apply_zebra_stripes(ws, 2, max_row, len(headers))
        _add_table(ws, "tblByLens", len(headers), max_row)
    auto_width(ws, len(headers), max_row)


def _build_by_collection(
    wb: Workbook,
    data: dict,
    *,
    portfolio_profile: str = "default",
) -> None:
    from src.analyst_views import build_analyst_context

    ws = wb.create_sheet("By Collection")
    ws.sheet_properties.tabColor = "2563EB"
    headers = ["Collection", "Description", "Repo Count", "Avg Profile Score", "Avg Overall", "Top Repo"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws, 1, len(headers))

    row = 2
    for collection_name, collection_data in data.get("collections", {}).items():
        context = build_analyst_context(data, profile_name=portfolio_profile, collection_name=collection_name)
        ranked = context.get("ranked_audits", [])
        avg_profile = round(sum(item["profile_score"] for item in ranked) / len(ranked), 3) if ranked else 0.0
        avg_overall = round(sum(item["overall_score"] for item in ranked) / len(ranked), 3) if ranked else 0.0
        values = [
            collection_name,
            collection_data.get("description", ""),
            len(ranked),
            avg_profile,
            avg_overall,
            ranked[0]["name"] if ranked else "",
        ]
        for col, value in enumerate(values, 1):
            style_data_cell(ws.cell(row=row, column=col, value=value), "center" if col in {3, 4, 5} else "left")
        row += 1

    max_row = row - 1
    if max_row > 1:
        apply_zebra_stripes(ws, 2, max_row, len(headers))
        _add_table(ws, "tblByCollection", len(headers), max_row)
    auto_width(ws, len(headers), max_row)


def _build_trend_summary(
    wb: Workbook,
    data: dict,
    trend_data: list[dict] | None = None,
    score_history: dict[str, list[float]] | None = None,
) -> None:
    ws = wb.create_sheet("Trend Summary")
    ws.sheet_properties.tabColor = "0EA5E9"

    history = _extend_portfolio_trend_with_current(data, trend_data)
    repo_history = _extend_score_history_with_current(data, score_history)

    ws["A1"] = "Trend Summary"
    ws["A1"].font = TITLE_FONT
    headers = ["Date", "Avg Score", "Repos", "Shipped", "Functional", "Security Avg"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=3, column=col, value=header)
    style_header_row(ws, 3, len(headers))

    for row, item in enumerate(history, 4):
        tier_distribution = item.get("tier_distribution", {})
        values = [
            item.get("date", ""),
            round(item.get("average_score", 0.0), 3),
            item.get("repos_audited", 0),
            tier_distribution.get("shipped", 0),
            tier_distribution.get("functional", 0),
            round(data.get("security_posture", {}).get("average_score", 0.0), 3),
        ]
        for col, value in enumerate(values, 1):
            style_data_cell(ws.cell(row=row, column=col, value=value), "center" if col >= 2 else "left")

    start_row = max(6, len(history) + 6)
    ws.cell(row=start_row, column=1, value="Repo Trends").font = SECTION_FONT
    repo_headers = ["Repo", "Latest Score", "Trend"]
    for col, header in enumerate(repo_headers, 1):
        ws.cell(row=start_row + 1, column=col, value=header)
    style_header_row(ws, start_row + 1, len(repo_headers))

    ranked = sorted(data.get("audits", []), key=lambda item: item.get("overall_score", 0), reverse=True)[:10]
    for offset, audit in enumerate(ranked, 1):
        repo_name = audit.get("metadata", {}).get("name", "")
        style_data_cell(ws.cell(row=start_row + 1 + offset, column=1, value=repo_name), "left")
        style_data_cell(ws.cell(row=start_row + 1 + offset, column=2, value=round(audit.get("overall_score", 0), 3)), "center")
        if repo_history.get(repo_name):
            style_data_cell(ws.cell(row=start_row + 1 + offset, column=3, value="native"), "center")

    max_row = start_row + 1 + len(ranked)
    if max_row > start_row + 1:
        apply_zebra_stripes(ws, start_row + 2, max_row, len(repo_headers))
        _add_table(ws, "tblTrendSummary", len(repo_headers), max_row, start_row=start_row + 1)
    auto_width(ws, 6, max_row)


def _build_compare_sheet(
    wb: Workbook,
    diff_data: dict | None,
) -> None:
    if not diff_data:
        return

    ws = wb.create_sheet("Compare")
    ws.sheet_properties.tabColor = "7C3AED"
    ws["A1"] = "Compare Summary"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = f"Previous: {diff_data.get('previous_date', '')[:10]}"
    ws["A3"] = f"Current: {diff_data.get('current_date', '')[:10]}"
    ws["A4"] = f"Average score delta: {diff_data.get('average_score_delta', 0):+.3f}"

    row = 6
    if diff_data.get("lens_deltas"):
        ws.cell(row=row, column=1, value="Lens")
        ws.cell(row=row, column=2, value="Delta")
        style_header_row(ws, row, 2)
        for offset, (lens_name, delta) in enumerate(diff_data.get("lens_deltas", {}).items(), 1):
            ws.cell(row=row + offset, column=1, value=lens_name)
            ws.cell(row=row + offset, column=2, value=delta)
            style_data_cell(ws.cell(row=row + offset, column=1), "left")
            style_data_cell(ws.cell(row=row + offset, column=2), "center")
        row += len(diff_data.get("lens_deltas", {})) + 3

    headers = ["Repo", "Score Delta", "Tier Change", "Security", "Hotspots", "Collections"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=row, column=col, value=header)
    style_header_row(ws, row, len(headers))
    repo_changes = diff_data.get("repo_changes", [])
    for offset, change in enumerate(repo_changes[:15], 1):
        values = [
            change.get("name", ""),
            change.get("delta", 0.0),
            f"{change.get('old_tier', '—')} → {change.get('new_tier', '—')}",
            f"{change.get('security_change', {}).get('old_label', '—')} → {change.get('security_change', {}).get('new_label', '—')}",
            f"{change.get('hotspot_change', {}).get('old_count', 0)} → {change.get('hotspot_change', {}).get('new_count', 0)}",
            f"{', '.join(change.get('collection_change', {}).get('old', [])) or '—'} → {', '.join(change.get('collection_change', {}).get('new', [])) or '—'}",
        ]
        for col, value in enumerate(values, 1):
            style_data_cell(ws.cell(row=row + offset, column=col, value=value), "center" if col == 2 else "left")
    max_row = row + min(len(repo_changes), 15)
    if max_row > row:
        _add_table(ws, "tblCompare", len(headers), max_row, start_row=row)
    auto_width(ws, len(headers), max_row)


def _build_scenario_planner(
    wb: Workbook,
    data: dict,
    *,
    portfolio_profile: str = "default",
    collection: str | None = None,
) -> None:
    from src.analyst_views import build_analyst_context

    context = build_analyst_context(data, profile_name=portfolio_profile, collection_name=collection)
    preview = context["scenario_preview"]
    ws = wb.create_sheet("Scenario Planner")
    ws.sheet_properties.tabColor = "CA8A04"

    ws["A1"] = "Scenario Planner"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = f"Profile: {context['profile_name']}"
    ws["A3"] = f"Collection: {context['collection_name'] or 'all'}"

    headers = ["Lever", "Lens", "Repo Count", "Avg Lift", "Weighted Impact", "Projected Promotions"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=5, column=col, value=header)
    style_header_row(ws, 5, len(headers))

    for row, lever in enumerate(preview.get("top_levers", []), 6):
        values = [
            lever.get("title", ""),
            lever.get("lens", ""),
            lever.get("repo_count", 0),
            lever.get("average_expected_lens_delta", 0.0),
            lever.get("weighted_impact", 0.0),
            lever.get("projected_tier_promotions", 0),
        ]
        for col, value in enumerate(values, 1):
            style_data_cell(ws.cell(row=row, column=col, value=value), "center" if col >= 3 else "left")

    projection = preview.get("portfolio_projection", {})
    summary_row = max(7, len(preview.get("top_levers", [])) + 7)
    ws.cell(row=summary_row, column=1, value="Selected Repos").font = SUBHEADER_FONT
    ws.cell(row=summary_row, column=2, value=projection.get("selected_repo_count", 0))
    ws.cell(row=summary_row + 1, column=1, value="Projected Avg Score Delta").font = SUBHEADER_FONT
    ws.cell(row=summary_row + 1, column=2, value=projection.get("projected_average_score_delta", 0.0))
    ws.cell(row=summary_row + 2, column=1, value="Projected Promotions").font = SUBHEADER_FONT
    ws.cell(row=summary_row + 2, column=2, value=projection.get("projected_tier_promotions", 0))

    max_row = max(summary_row + 2, len(preview.get("top_levers", [])) + 5)
    if len(preview.get("top_levers", [])) > 0:
        _add_table(
            ws,
            "tblScenarioPlanner",
            len(headers),
            len(preview.get("top_levers", [])) + 5,
            start_row=5,
        )
    auto_width(ws, len(headers), max_row)


def _build_executive_summary(
    wb: Workbook,
    data: dict,
    diff_data: dict | None,
    *,
    portfolio_profile: str = "default",
    collection: str | None = None,
) -> None:
    from src.analyst_views import build_analyst_context

    context = build_analyst_context(data, profile_name=portfolio_profile, collection_name=collection)
    ws = wb.create_sheet("Executive Summary")
    ws.sheet_properties.tabColor = NAVY
    ws.merge_cells("A1:F1")
    ws["A1"] = "Executive Summary"
    ws["A1"].font = TITLE_FONT

    write_kpi_card(ws, 3, 1, "Portfolio Grade", data.get("portfolio_grade", "F"))
    write_kpi_card(ws, 3, 3, "Avg Score", f"{data.get('average_score', 0):.2f}")
    write_kpi_card(ws, 3, 5, "Profile", context["profile_name"])

    ws.cell(row=7, column=1, value="Top Profile Leaders").font = SECTION_FONT
    for offset, entry in enumerate(context["profile_leaderboard"].get("leaders", [])[:5], 1):
        ws.cell(row=7 + offset, column=1, value=entry["name"])
        ws.cell(row=7 + offset, column=2, value=entry["profile_score"])
        ws.cell(row=7 + offset, column=3, value=entry["tier"])

    if diff_data:
        ws.cell(row=7, column=5, value="Top Movers").font = SECTION_FONT
        for offset, change in enumerate(diff_data.get("repo_changes", [])[:5], 1):
            ws.cell(row=7 + offset, column=5, value=change.get("name", ""))
            ws.cell(row=7 + offset, column=6, value=change.get("delta", 0.0))

    preview = context["scenario_preview"].get("portfolio_projection", {})
    ws.cell(row=15, column=1, value="Scenario Preview").font = SECTION_FONT
    ws.cell(row=16, column=1, value="Projected Avg Score Delta").font = SUBHEADER_FONT
    ws.cell(row=16, column=2, value=preview.get("projected_average_score_delta", 0.0))
    ws.cell(row=17, column=1, value="Projected Promotions").font = SUBHEADER_FONT
    ws.cell(row=17, column=2, value=preview.get("projected_tier_promotions", 0))
    auto_width(ws, 6, 20)


def _build_print_pack(
    wb: Workbook,
    data: dict,
    diff_data: dict | None,
    *,
    portfolio_profile: str = "default",
    collection: str | None = None,
) -> None:
    from src.analyst_views import build_analyst_context

    context = build_analyst_context(data, profile_name=portfolio_profile, collection_name=collection)
    ws = wb.create_sheet("Print Pack")
    ws.sheet_properties.tabColor = "1E293B"

    ws.merge_cells("A1:F1")
    ws["A1"] = "Print Pack"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = (
        f"Generated {data.get('generated_at', '')[:10]} | "
        f"Profile {context['profile_name']} | Collection {context['collection_name'] or 'all'}"
    )
    ws["A2"].font = SUBTITLE_FONT

    rows = [
        ("Portfolio Grade", data.get("portfolio_grade", "")),
        ("Average Score", round(data.get("average_score", 0.0), 3)),
        ("Material Changes", data.get("review_summary", {}).get("material_change_count", 0)),
        ("Safe To Defer", "yes" if data.get("review_summary", {}).get("safe_to_defer") else "no"),
    ]
    for offset, (label, value) in enumerate(rows, 4):
        ws.cell(row=offset, column=1, value=label).font = SUBHEADER_FONT
        ws.cell(row=offset, column=2, value=value)

    ws.cell(row=10, column=1, value="Top Leaders").font = SECTION_FONT
    headers = ["Repo", "Profile Score", "Tier"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=11, column=col, value=header)
    style_header_row(ws, 11, len(headers))
    for offset, entry in enumerate(context.get("profile_leaderboard", {}).get("leaders", [])[:5], 1):
        values = [entry["name"], entry["profile_score"], entry["tier"]]
        for col, value in enumerate(values, 1):
            style_data_cell(ws.cell(row=11 + offset, column=col, value=value), "center" if col >= 2 else "left")

    if diff_data:
        ws.cell(row=10, column=5, value="Compare").font = SECTION_FONT
        ws.cell(row=11, column=5, value="Avg Delta").font = SUBHEADER_FONT
        ws.cell(row=11, column=6, value=round(diff_data.get("average_score_delta", 0.0), 3))
        ws.cell(row=12, column=5, value="Top Mover").font = SUBHEADER_FONT
        top_mover = diff_data.get("repo_changes", [{}])[0] if diff_data.get("repo_changes") else {}
        ws.cell(row=12, column=6, value=top_mover.get("name", ""))

    auto_width(ws, 6, 20)


def _build_template_sparkline_specs(
    data: dict,
    *,
    trend_data: list[dict] | None = None,
    score_history: dict[str, list[float]] | None = None,
) -> list[SparklineSpec]:
    specs: list[SparklineSpec] = []
    extended_trends = _extend_portfolio_trend_with_current(data, trend_data)
    extended_score_history = _extend_score_history_with_current(data, score_history)
    if extended_trends:
        specs.append(
            SparklineSpec(
                sheet_name="Dashboard",
                location="C7",
                data_range=f"Data_PortfolioHistory!C2:C{len(extended_trends) + 1}",
            )
        )

    audits_sorted = sorted(data.get("audits", []), key=lambda item: item.get("overall_score", 0), reverse=True)
    row_map: dict[str, int] = {}
    for offset, audit in enumerate(audits_sorted, 2):
        repo_name = audit.get("metadata", {}).get("name", "")
        if not repo_name or not extended_score_history.get(repo_name):
            continue
        row_map[repo_name] = offset
        specs.append(
            SparklineSpec(
                sheet_name="All Repos",
                location=f"AA{offset}",
                data_range=f"Data_TrendMatrix!B{offset}:M{offset}",
            )
        )

    history_count = len(extended_trends)
    start_row = max(6, history_count + 6)
    for offset, audit in enumerate(audits_sorted[:10], 1):
        repo_name = audit.get("metadata", {}).get("name", "")
        matrix_row = row_map.get(repo_name)
        if not matrix_row:
            continue
        specs.append(
            SparklineSpec(
                sheet_name="Trend Summary",
                location=f"C{start_row + 1 + offset}",
                data_range=f"Data_TrendMatrix!B{matrix_row}:M{matrix_row}",
            )
        )
    return specs


def _build_excel_workbook(
    wb: Workbook,
    data: dict,
    *,
    trend_data: list[dict] | None = None,
    diff_data: dict | None = None,
    score_history: dict[str, list[float]] | None = None,
    portfolio_profile: str = "default",
    collection: str | None = None,
    excel_mode: str = "standard",
) -> None:
    native_sparklines = excel_mode == "template"
    _build_dashboard(wb, data, diff_data, score_history, native_sparklines=native_sparklines)
    _build_all_repos(wb, data, score_history, native_sparklines=native_sparklines)
    _build_portfolio_explorer(
        wb,
        data,
        portfolio_profile=portfolio_profile,
        collection=collection,
    )
    _build_by_lens(
        wb,
        data,
        portfolio_profile=portfolio_profile,
        collection=collection,
    )
    if excel_mode == "template":
        _build_by_collection(
            wb,
            data,
            portfolio_profile=portfolio_profile,
        )
        _build_trend_summary(wb, data, trend_data, score_history)
    _build_heatmap(wb, data)
    _build_quick_wins(wb, data)
    _build_badges(wb, data)
    _build_tech_stack(wb, data)
    _build_trends(wb, data, trend_data)
    _build_tier_breakdown(wb, data)
    _build_activity(wb, data)
    _build_repo_profiles(wb, data)
    _build_security(wb, data)
    _build_security_controls(wb, data)
    _build_supply_chain(wb, data)
    _build_security_debt(wb, data)
    _build_campaigns(wb, data)
    _build_writeback_audit(wb, data)
    _build_governance_controls(wb, data)
    _build_governance_audit(wb, data)
    _build_review_queue(wb, data)
    _build_review_history_sheet(wb, data)
    _build_hotspots(wb, data)
    _build_compare_sheet(wb, diff_data)
    _build_scenario_planner(
        wb,
        data,
        portfolio_profile=portfolio_profile,
        collection=collection,
    )
    _build_executive_summary(
        wb,
        data,
        diff_data,
        portfolio_profile=portfolio_profile,
        collection=collection,
    )
    if excel_mode == "template":
        _build_print_pack(
            wb,
            data,
            diff_data,
            portfolio_profile=portfolio_profile,
            collection=collection,
        )
    _build_changes(wb, data, diff_data)
    _build_reconciliation(wb, data)
    _build_dependency_graph(wb, data)
    _build_score_explainer(wb)
    _build_action_items(wb, data)
    _build_hidden_data_sheets(wb, data, trend_data, score_history)
    _build_navigation(wb, data, excel_mode=excel_mode)
    _apply_workbook_named_ranges(
        wb,
        data,
        portfolio_profile=portfolio_profile,
        collection=collection,
    )
    _refresh_pivot_caches_on_load(wb)
    wb.calculation.fullCalcOnLoad = True
    wb.calculation.forceFullCalc = True


def export_excel(
    report_path: Path,
    output_path: Path,
    trend_data: list[dict] | None = None,
    diff_data: dict | None = None,
    score_history: dict[str, list[float]] | None = None,
    portfolio_profile: str = "default",
    collection: str | None = None,
    excel_mode: str = "template",
    template_path: Path | None = None,
) -> Path:
    """Generate the flagship Excel dashboard."""
    data = json.loads(report_path.read_text())
    if excel_mode not in {"template", "standard"}:
        raise ValueError(f"Unsupported excel mode: {excel_mode}")

    if excel_mode == "template":
        template = resolve_template_path(template_path or DEFAULT_TEMPLATE_PATH)
        copy_template_to_output(output_path, template)
        wb = load_workbook(output_path)
    else:
        wb = Workbook()

    _build_excel_workbook(
        wb,
        data,
        trend_data=trend_data,
        diff_data=diff_data,
        score_history=score_history,
        portfolio_profile=portfolio_profile,
        collection=collection,
        excel_mode=excel_mode,
    )

    wb.save(str(output_path))
    if excel_mode == "template":
        inject_native_sparklines(
            output_path,
            _build_template_sparkline_specs(
                data,
                trend_data=trend_data,
                score_history=score_history,
            ),
        )
    return output_path
