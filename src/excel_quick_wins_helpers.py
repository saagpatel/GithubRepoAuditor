"""Helpers for Quick Wins workbook content."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

QUICK_WINS_HEADERS = ["Repo", "Grade", "Current", "Score", "Next Tier", "Gap", "Top Actions", "Badges"]

_TIER_NEXT = {
    "abandoned": ("skeleton", 0.15),
    "skeleton": ("wip", 0.35),
    "wip": ("functional", 0.55),
    "functional": ("shipped", 0.75),
}


def build_quick_wins_rows(audits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    wins: list[dict[str, Any]] = []
    for audit in audits:
        current_tier = audit.get("completeness_tier", "")
        if current_tier not in _TIER_NEXT:
            continue

        next_name, threshold = _TIER_NEXT[current_tier]
        gap = threshold - audit.get("overall_score", 0)
        if gap > 0.20 or gap <= 0:
            continue

        dim_scores = {result["dimension"]: result["score"] for result in audit.get("analyzer_results", [])}
        sorted_dims = sorted(dim_scores.items(), key=lambda item: item[1])
        wins.append(
            {
                "name": audit["metadata"]["name"],
                "grade": audit.get("grade", "F"),
                "tier": current_tier,
                "score": audit.get("overall_score", 0),
                "next_tier": next_name,
                "gap": gap,
                "actions": [f"Improve {dimension} ({score:.1f})" for dimension, score in sorted_dims[:3]],
                "badges": len(audit.get("badges", [])),
            }
        )

    return sorted(wins, key=lambda win: win["gap"])


def write_quick_wins_rows(
    ws: Any,
    wins: list[dict[str, Any]],
    *,
    start_row: int,
    style_data_cell: Callable[[Any], None],
    color_grade_cell: Callable[[Any, str], None],
    color_tier_cell: Callable[[Any, str], None],
) -> int:
    for row, win in enumerate(wins, start_row):
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

        for col in range(1, len(QUICK_WINS_HEADERS) + 1):
            style_data_cell(ws.cell(row=row, column=col))

    return start_row + len(wins) - 1


def write_quick_wins_sheet(
    ws: Any,
    wins: list[dict[str, Any]],
    *,
    section_font: Any,
    style_header_row: Callable[[Any, int, int], None],
    style_data_cell: Callable[[Any], None],
    color_grade_cell: Callable[[Any, str], None],
    color_tier_cell: Callable[[Any, str], None],
    apply_zebra_stripes: Callable[[Any, int, int, int], None],
) -> int:
    ws.merge_cells("A1:H1")
    ws["A1"].value = f"Quick Wins — {len(wins)} repos near the next tier"
    ws["A1"].font = section_font

    if not wins:
        ws.cell(row=3, column=1, value="No repos within striking distance of the next tier.")
        return 3

    for col, header in enumerate(QUICK_WINS_HEADERS, 1):
        ws.cell(row=3, column=col, value=header)
    style_header_row(ws, 3, len(QUICK_WINS_HEADERS))
    ws.freeze_panes = "B2"

    max_row = write_quick_wins_rows(
        ws,
        wins,
        start_row=4,
        style_data_cell=style_data_cell,
        color_grade_cell=color_grade_cell,
        color_tier_cell=color_tier_cell,
    )
    if max_row > 4:
        apply_zebra_stripes(ws, 4, max_row, len(QUICK_WINS_HEADERS))
    return max_row


def build_quick_wins_sheet(
    wb,
    data: dict[str, Any],
    *,
    get_or_create_sheet,
    configure_sheet_view,
    build_quick_wins_rows_fn,
    write_quick_wins_sheet_fn,
    data_bar_rule,
    section_font,
    style_header_row,
    style_data_cell,
    color_grade_cell,
    color_tier_cell,
    apply_zebra_stripes,
    auto_width,
) -> None:
    ws = get_or_create_sheet(wb, "Quick Wins")
    ws.sheet_properties.tabColor = "0891B2"
    configure_sheet_view(ws, zoom=110, show_grid_lines=True)
    wins = build_quick_wins_rows_fn(data.get("audits", []))
    max_row = write_quick_wins_sheet_fn(
        ws,
        wins,
        section_font=section_font,
        style_header_row=style_header_row,
        style_data_cell=style_data_cell,
        color_grade_cell=color_grade_cell,
        color_tier_cell=color_tier_cell,
        apply_zebra_stripes=apply_zebra_stripes,
    )
    if max_row > 4:
        ws.conditional_formatting.add(
            f"F4:F{max_row}",
            data_bar_rule(
                start_type="num", start_value=0, end_type="num", end_value=0.20, color="0EA5E9"
            ),
        )

    auto_width(ws, len(QUICK_WINS_HEADERS), max_row)
