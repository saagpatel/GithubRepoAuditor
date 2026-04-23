"""Helpers for compare and scenario workbook sheets."""

from __future__ import annotations

from typing import Any

COMPARE_REPO_HEADERS = ["Repo", "Score Delta", "Tier Change", "Security", "Hotspots", "Collections"]
SCENARIO_PLANNER_HEADERS = [
    "Lever",
    "Lens",
    "Repo Count",
    "Avg Lift",
    "Weighted Impact",
    "Projected Promotions",
]


def build_compare_lens_rows(diff_data: dict[str, Any]) -> list[list[Any]]:
    return [
        [lens_name, delta]
        for lens_name, delta in (diff_data.get("lens_deltas", {}) or {}).items()
    ]


def build_compare_repo_rows(diff_data: dict[str, Any]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for change in (diff_data.get("repo_changes", []) or [])[:15]:
        rows.append(
            [
                change.get("name", ""),
                change.get("delta", 0.0),
                f"{change.get('old_tier', '—')} -> {change.get('new_tier', '—')}",
                f"{change.get('security_change', {}).get('old_label', '—')} -> {change.get('security_change', {}).get('new_label', '—')}",
                f"{change.get('hotspot_change', {}).get('old_count', 0)} -> {change.get('hotspot_change', {}).get('new_count', 0)}",
                f"{', '.join(change.get('collection_change', {}).get('old', [])) or '—'} -> {', '.join(change.get('collection_change', {}).get('new', [])) or '—'}",
            ]
        )
    return rows


def build_scenario_planner_rows(preview: dict[str, Any]) -> dict[str, Any]:
    lever_rows = [
        [
            lever.get("title", ""),
            lever.get("lens", ""),
            lever.get("repo_count", 0),
            lever.get("average_expected_lens_delta", 0.0),
            lever.get("weighted_impact", 0.0),
            lever.get("projected_tier_promotions", 0),
        ]
        for lever in (preview.get("top_levers", []) or [])
    ]
    projection = preview.get("portfolio_projection", {})
    projection_rows = [
        ("Selected Repos", projection.get("selected_repo_count", 0)),
        ("Projected Avg Score Delta", projection.get("projected_average_score_delta", 0.0)),
        ("Projected Promotions", projection.get("projected_tier_promotions", 0)),
    ]
    return {
        "lever_rows": lever_rows,
        "projection_rows": projection_rows,
    }


def write_compare_sections(
    ws,
    *,
    row: int,
    lens_rows: list[list[Any]],
    repo_rows: list[list[Any]],
    style_header_row,
    style_data_cell,
) -> int:
    if lens_rows:
        ws.cell(row=row, column=1, value="Lens")
        ws.cell(row=row, column=2, value="Delta")
        style_header_row(ws, row, 2)
        for offset, (lens_name, delta) in enumerate(lens_rows, 1):
            ws.cell(row=row + offset, column=1, value=lens_name)
            ws.cell(row=row + offset, column=2, value=delta)
            style_data_cell(ws.cell(row=row + offset, column=1), "left")
            style_data_cell(ws.cell(row=row + offset, column=2), "center")
        row += len(lens_rows) + 3

    for col, header in enumerate(COMPARE_REPO_HEADERS, 1):
        ws.cell(row=row, column=col, value=header)
    style_header_row(ws, row, len(COMPARE_REPO_HEADERS))
    for offset, values in enumerate(repo_rows, 1):
        for col, value in enumerate(values, 1):
            style_data_cell(
                ws.cell(row=row + offset, column=col, value=value),
                "center" if col == 2 else "left",
            )
    return row + len(repo_rows)


def build_compare_sheet(
    wb,
    diff_data: dict[str, Any] | None,
    *,
    get_or_create_sheet,
    configure_sheet_view,
    title_font,
    build_compare_lens_rows_fn,
    build_compare_repo_rows_fn,
    write_compare_sections_fn,
    style_header_row,
    style_data_cell,
    add_table,
    auto_width,
) -> None:
    if not diff_data:
        return

    ws = get_or_create_sheet(wb, "Compare")
    ws.sheet_properties.tabColor = "7C3AED"
    configure_sheet_view(ws, zoom=110, show_grid_lines=True)
    ws["A1"] = "Compare Summary"
    ws["A1"].font = title_font
    ws["A2"] = f"Previous: {diff_data.get('previous_date', '')[:10]}"
    ws["A3"] = f"Current: {diff_data.get('current_date', '')[:10]}"
    ws["A4"] = f"Average score delta: {diff_data.get('average_score_delta', 0):+.3f}"

    row = 6
    lens_rows = build_compare_lens_rows_fn(diff_data)
    repo_rows = build_compare_repo_rows_fn(diff_data)
    max_row = write_compare_sections_fn(
        ws,
        row=row,
        lens_rows=lens_rows,
        repo_rows=repo_rows,
        style_header_row=style_header_row,
        style_data_cell=style_data_cell,
    )
    if max_row > row:
        compare_start_row = 6 + len(lens_rows) + 3 if lens_rows else 6
        add_table(
            ws,
            "tblCompare",
            len(COMPARE_REPO_HEADERS),
            max_row,
            start_row=compare_start_row,
        )
    auto_width(ws, len(COMPARE_REPO_HEADERS), max_row)


def write_scenario_planner_sections(
    ws,
    content: dict[str, Any],
    *,
    start_row: int,
    style_header_row,
    style_data_cell,
    subheader_font,
) -> int:
    for col, header in enumerate(SCENARIO_PLANNER_HEADERS, 1):
        ws.cell(row=start_row, column=col, value=header)
    style_header_row(ws, start_row, len(SCENARIO_PLANNER_HEADERS))
    ws.freeze_panes = "B6"

    for row, values in enumerate(content["lever_rows"], start_row + 1):
        for col, value in enumerate(values, 1):
            style_data_cell(
                ws.cell(row=row, column=col, value=value), "center" if col >= 3 else "left"
            )

    summary_row = max(start_row + 2, len(content["lever_rows"]) + start_row + 2)
    for offset, (label, value) in enumerate(content["projection_rows"]):
        ws.cell(row=summary_row + offset, column=1, value=label).font = subheader_font
        ws.cell(row=summary_row + offset, column=2, value=value)
    return max(summary_row + 2, len(content["lever_rows"]) + start_row)


def build_scenario_planner_sheet(
    wb,
    data: dict[str, Any],
    *,
    portfolio_profile: str = "default",
    collection: str | None = None,
    build_analyst_context,
    get_or_create_sheet,
    configure_sheet_view,
    title_font,
    subheader_font,
    build_scenario_planner_rows_fn,
    write_scenario_planner_sections_fn,
    style_header_row,
    style_data_cell,
    add_table,
    auto_width,
) -> None:
    context = build_analyst_context(
        data,
        profile_name=portfolio_profile,
        collection_name=collection,
    )
    preview = context["scenario_preview"]
    ws = get_or_create_sheet(wb, "Scenario Planner")
    ws.sheet_properties.tabColor = "CA8A04"
    configure_sheet_view(ws, zoom=110, show_grid_lines=False)

    ws["A1"] = "Scenario Planner"
    ws["A1"].font = title_font
    ws["A2"] = f"Profile: {context['profile_name']}"
    ws["A3"] = f"Collection: {context['collection_name'] or 'all'}"

    content = build_scenario_planner_rows_fn(preview)
    max_row = write_scenario_planner_sections_fn(
        ws,
        content,
        start_row=5,
        style_header_row=style_header_row,
        style_data_cell=style_data_cell,
        subheader_font=subheader_font,
    )
    if content["lever_rows"]:
        add_table(
            ws,
            "tblScenarioPlanner",
            len(SCENARIO_PLANNER_HEADERS),
            len(content["lever_rows"]) + 5,
            start_row=5,
        )
    auto_width(ws, len(SCENARIO_PLANNER_HEADERS), max_row)
