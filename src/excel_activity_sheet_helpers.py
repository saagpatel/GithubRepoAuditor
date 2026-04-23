"""Helpers for Activity workbook content."""

from __future__ import annotations

from typing import Any

ACTIVITY_HEADERS = [
    "Repo",
    "Commit Pattern",
    "Days Since Push",
    "Total Commits",
    "Recent 3mo",
    "Bus Factor",
    "Release Count",
    "Activity Score",
    "Tier",
]


def build_activity_rows(audits: list[dict[str, Any]]) -> list[list[Any]]:
    sorted_audits = sorted(
        audits,
        key=lambda audit: next(
            (
                result.get("details", {}).get("days_since_push", 9999)
                for result in audit.get("analyzer_results", [])
                if result["dimension"] == "activity"
            ),
            9999,
        ),
    )

    rows: list[list[Any]] = []
    for audit in sorted_audits:
        details = {result["dimension"]: result.get("details", {}) for result in audit.get("analyzer_results", [])}
        scores = {result["dimension"]: result["score"] for result in audit.get("analyzer_results", [])}
        activity = details.get("activity", {})
        pattern = activity.get("commit_pattern", "—")
        rows.append(
            [
                audit["metadata"]["name"],
                pattern,
                activity.get("days_since_push", "—"),
                activity.get("total_commits", "—"),
                activity.get("recent_3mo_commits", "—"),
                activity.get("bus_factor", "—"),
                activity.get("release_count", "—"),
                round(scores.get("activity", 0), 2),
                audit.get("completeness_tier", ""),
            ]
        )
    return rows


def write_activity_table(
    ws,
    rows: list[list[Any]],
    *,
    start_row: int,
    style_header_row,
    style_data_cell,
    apply_zebra_stripes,
    color_pattern_cell,
) -> int:
    for col, header in enumerate(ACTIVITY_HEADERS, 1):
        ws.cell(row=start_row, column=col, value=header)
    style_header_row(ws, start_row, len(ACTIVITY_HEADERS))
    ws.freeze_panes = "B2"

    for row_number, values in enumerate(rows, start_row + 1):
        for col, value in enumerate(values, 1):
            cell = ws.cell(row=row_number, column=col, value=value)
            style_data_cell(cell)
            if col == 2 and value and value != "—":
                color_pattern_cell(cell, str(value))

    max_row = start_row + len(rows)
    if rows:
        apply_zebra_stripes(ws, start_row + 1, max_row, len(ACTIVITY_HEADERS))
    return max_row


def build_activity_sheet(
    wb,
    data: dict[str, Any],
    *,
    get_or_create_sheet,
    configure_sheet_view,
    build_activity_rows_fn,
    write_activity_table_fn,
    style_header_row,
    style_data_cell,
    apply_zebra_stripes,
    color_pattern_cell,
    auto_width,
) -> None:
    ws = get_or_create_sheet(wb, "Activity")
    ws.sheet_properties.tabColor = "6A1B9A"
    configure_sheet_view(ws, zoom=105, show_grid_lines=True)
    rows = build_activity_rows_fn(data.get("audits", []))
    max_row = write_activity_table_fn(
        ws,
        rows,
        start_row=1,
        style_header_row=style_header_row,
        style_data_cell=style_data_cell,
        apply_zebra_stripes=apply_zebra_stripes,
        color_pattern_cell=color_pattern_cell,
    )
    auto_width(ws, len(ACTIVITY_HEADERS), max_row)
