"""Helpers for scoring heatmap workbook content."""

from __future__ import annotations

from typing import Any

HEATMAP_DIMENSIONS = [
    "readme",
    "structure",
    "code_quality",
    "testing",
    "cicd",
    "dependencies",
    "activity",
    "documentation",
    "build_readiness",
    "community_profile",
    "interest",
]
HEATMAP_HEADERS = ["Repo", "Grade", "Overall"] + [dimension.replace("_", " ").title() for dimension in HEATMAP_DIMENSIONS]


def build_heatmap_rows(audits: list[dict[str, Any]]) -> list[list[Any]]:
    sorted_audits = sorted(audits, key=lambda audit: audit.get("overall_score", 0), reverse=True)
    rows: list[list[Any]] = []
    for audit in sorted_audits:
        score_map = {result["dimension"]: result["score"] for result in audit.get("analyzer_results", [])}
        rows.append(
            [
                audit["metadata"]["name"],
                audit.get("grade", "F"),
                round(audit.get("overall_score", 0), 2),
                *[round(score_map.get(dimension, 0), 2) for dimension in HEATMAP_DIMENSIONS],
            ]
        )
    return rows


def write_heatmap_table(
    ws,
    rows: list[list[Any]],
    *,
    start_row: int,
    center_alignment,
    thin_border,
    style_header_row,
    style_data_cell,
    color_grade_cell,
) -> int:
    for col, header in enumerate(HEATMAP_HEADERS, 1):
        ws.cell(row=start_row, column=col, value=header)
    style_header_row(ws, start_row, len(HEATMAP_HEADERS))
    ws.freeze_panes = "B2"

    for row_number, values in enumerate(rows, start_row + 1):
        ws.cell(row=row_number, column=1, value=values[0])
        style_data_cell(ws.cell(row=row_number, column=1))

        grade_cell = ws.cell(row=row_number, column=2, value=values[1])
        color_grade_cell(grade_cell, str(values[1]))

        overall_cell = ws.cell(row=row_number, column=3, value=values[2])
        style_data_cell(overall_cell, "center")

        for col, value in enumerate(values[3:], start=4):
            cell = ws.cell(row=row_number, column=col, value=value)
            cell.alignment = center_alignment
            cell.border = thin_border

    return start_row + len(rows)


def build_heatmap_sheet(
    wb,
    data: dict[str, Any],
    *,
    get_or_create_sheet,
    configure_sheet_view,
    build_heatmap_rows_fn,
    write_heatmap_table_fn,
    get_column_letter,
    color_scale_rule,
    heatmap_headers: list[str],
    heatmap_red: str,
    heatmap_amber: str,
    heatmap_green: str,
    center_alignment,
    thin_border,
    style_header_row,
    style_data_cell,
    color_grade_cell,
    auto_width,
) -> None:
    ws = get_or_create_sheet(wb, "Scoring Heatmap")
    ws.sheet_properties.tabColor = "D97706"
    configure_sheet_view(ws, zoom=105, show_grid_lines=True)
    max_row = write_heatmap_table_fn(
        ws,
        build_heatmap_rows_fn(data.get("audits", [])),
        start_row=1,
        center_alignment=center_alignment,
        thin_border=thin_border,
        style_header_row=style_header_row,
        style_data_cell=style_data_cell,
        color_grade_cell=color_grade_cell,
    )

    if max_row > 1:
        for col in range(3, len(heatmap_headers) + 1):
            col_letter = get_column_letter(col)
            ws.conditional_formatting.add(
                f"{col_letter}2:{col_letter}{max_row}",
                color_scale_rule(
                    start_type="num",
                    start_value=0,
                    start_color=heatmap_red,
                    mid_type="num",
                    mid_value=0.5,
                    mid_color=heatmap_amber,
                    end_type="num",
                    end_value=1,
                    end_color=heatmap_green,
                ),
            )

    auto_width(ws, len(heatmap_headers), max_row)
