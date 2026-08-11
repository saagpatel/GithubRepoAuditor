"""Helpers for dependency and hotspot workbook sheets."""

from __future__ import annotations

from typing import Any

DEPENDENCY_GRAPH_HEADERS = ["Dependency", "Repo Count", "Repos Using It"]
HOTSPOTS_HEADERS = ["Repo", "Category", "Severity", "Title", "Summary", "Recommended Action", "Tier"]
IMPLEMENTATION_HOTSPOTS_HEADERS = [
    "Repo",
    "Scope",
    "Path",
    "Module",
    "Category",
    "Pressure",
    "Suggestion",
    "Why It Matters",
    "Suggested First Move",
]


def build_dependency_graph_rows(shared_dependencies: list[dict[str, Any]]) -> list[list[Any]]:
    return [
        [
            item.get("name", ""),
            item.get("count", 0),
            ", ".join(item.get("repos", []) or []),
        ]
        for item in shared_dependencies
    ]


def write_dependency_graph_table(
    ws,
    rows: list[list[Any]],
    *,
    start_row: int,
    style_header_row,
    style_data_cell,
    apply_zebra_stripes,
) -> int:
    for col, header in enumerate(DEPENDENCY_GRAPH_HEADERS, 1):
        ws.cell(row=start_row, column=col, value=header)
    style_header_row(ws, start_row, len(DEPENDENCY_GRAPH_HEADERS))
    ws.freeze_panes = "A3"

    for row_number, values in enumerate(rows, start_row + 1):
        for col, value in enumerate(values, 1):
            style_data_cell(ws.cell(row=row_number, column=col, value=value))

    max_row = start_row + len(rows)
    if rows:
        apply_zebra_stripes(ws, start_row + 1, max_row, len(DEPENDENCY_GRAPH_HEADERS))
    return max_row


def build_dependency_graph_sheet(
    wb,
    data: dict[str, Any],
    *,
    build_dependency_graph_fn,
    get_or_create_sheet,
    configure_sheet_view,
    color_scale_rule,
    heatmap_amber: str,
    heatmap_green: str,
    auto_width,
    section_font,
    style_header_row,
    style_data_cell,
    apply_zebra_stripes,
) -> None:
    ws = get_or_create_sheet(wb, "Dep Graph")
    ws.sheet_properties.tabColor = "0277BD"
    configure_sheet_view(ws, zoom=105, show_grid_lines=True)

    graph = build_dependency_graph_fn(data.get("audits", []))
    shared = graph.get("shared_deps", [])
    shared_rows = build_dependency_graph_rows(shared)

    ws.merge_cells("A1:C1")
    ws["A1"].value = f"Shared Dependencies ({len(shared)} across 2+ repos)"
    ws["A1"].font = section_font

    max_row = write_dependency_graph_table(
        ws,
        shared_rows,
        start_row=2,
        style_header_row=style_header_row,
        style_data_cell=style_data_cell,
        apply_zebra_stripes=apply_zebra_stripes,
    )
    if max_row > 2:
        ws.conditional_formatting.add(
            f"B3:B{max_row}",
            color_scale_rule(
                start_type="min",
                start_color=heatmap_amber,
                end_type="max",
                end_color=heatmap_green,
            ),
        )
    auto_width(ws, len(DEPENDENCY_GRAPH_HEADERS), max_row)


def build_hotspot_rows(hotspots: list[dict[str, Any]]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for hotspot in hotspots:
        rows.append(
            [
                hotspot.get("repo", ""),
                hotspot.get("category", ""),
                round(hotspot.get("severity", 0), 3),
                hotspot.get("title", ""),
                hotspot.get("summary", ""),
                hotspot.get("recommended_action", ""),
                hotspot.get("tier", ""),
            ]
        )
    return rows


def build_implementation_hotspot_rows(hotspots: list[dict[str, Any]]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for hotspot in hotspots:
        rows.append(
            [
                hotspot.get("repo", ""),
                hotspot.get("scope", ""),
                hotspot.get("path", ""),
                hotspot.get("module", ""),
                hotspot.get("category", ""),
                round(hotspot.get("pressure_score", 0), 3),
                hotspot.get("suggestion_type", ""),
                hotspot.get("why_it_matters", ""),
                hotspot.get("suggested_first_move", ""),
            ]
        )
    return rows


def write_hotspot_table(
    ws,
    rows: list[list[Any]],
    *,
    start_row: int,
    headers: list[str],
    centered_columns: set[int],
    table_name: str,
    freeze_panes: str,
    style_header_row,
    style_data_cell,
    apply_zebra_stripes,
    add_table,
) -> int:
    for col, header in enumerate(headers, 1):
        ws.cell(row=start_row, column=col, value=header)
    style_header_row(ws, start_row, len(headers))
    ws.freeze_panes = freeze_panes

    for row_number, values in enumerate(rows, start_row + 1):
        for col, value in enumerate(values, 1):
            style_data_cell(
                ws.cell(row=row_number, column=col, value=value),
                "center" if col in centered_columns else "left",
            )

    max_row = start_row + len(rows)
    if rows:
        apply_zebra_stripes(ws, start_row + 1, max_row, len(headers))
        add_table(ws, table_name, len(headers), max_row, start_row=start_row)
    return max_row


def build_hotspots_sheet(
    wb,
    data: dict[str, Any],
    *,
    get_or_create_sheet,
    configure_sheet_view,
    build_hotspot_rows_fn,
    write_hotspot_table_fn,
    data_bar_rule,
    style_header_row,
    style_data_cell,
    apply_zebra_stripes,
    add_table,
    auto_width,
) -> None:
    ws = get_or_create_sheet(wb, "Hotspots")
    ws.sheet_properties.tabColor = "DC2626"
    configure_sheet_view(ws, zoom=105, show_grid_lines=True)
    hotspot_rows = build_hotspot_rows_fn(data.get("hotspots", []))
    max_row = write_hotspot_table_fn(
        ws,
        hotspot_rows,
        start_row=1,
        headers=HOTSPOTS_HEADERS,
        centered_columns={3, 7},
        table_name="tblHotspots",
        freeze_panes="A2",
        style_header_row=style_header_row,
        style_data_cell=style_data_cell,
        apply_zebra_stripes=apply_zebra_stripes,
        add_table=add_table,
    )
    if max_row > 1:
        ws.conditional_formatting.add(
            f"C2:C{max_row}",
            data_bar_rule(
                start_type="num", start_value=0, end_type="num", end_value=1, color="DC2626"
            ),
        )
    auto_width(ws, len(HOTSPOTS_HEADERS), max_row)


def build_implementation_hotspots_sheet(
    wb,
    data: dict[str, Any],
    *,
    get_or_create_sheet,
    configure_sheet_view,
    section_font,
    wrap_alignment,
    build_implementation_hotspot_rows_fn,
    write_hotspot_table_fn,
    implementation_hotspots_headers: list[str],
    style_header_row,
    style_data_cell,
    apply_zebra_stripes,
    add_table,
    data_bar_rule,
    auto_width,
) -> None:
    ws = get_or_create_sheet(wb, "Implementation Hotspots")
    ws.sheet_properties.tabColor = "B45309"
    configure_sheet_view(ws, zoom=105, show_grid_lines=True)

    summary = (data.get("implementation_hotspots_summary") or {}).get(
        "summary",
        "No meaningful implementation hotspots are currently surfaced.",
    )
    ws.merge_cells("A1:I1")
    ws["A1"].value = "Implementation Hotspots"
    ws["A1"].font = section_font
    ws.merge_cells("A2:I2")
    ws["A2"].value = summary
    ws["A2"].alignment = wrap_alignment

    implementation_rows = build_implementation_hotspot_rows_fn(
        data.get("implementation_hotspots", [])
    )
    max_row = write_hotspot_table_fn(
        ws,
        implementation_rows,
        start_row=4,
        headers=implementation_hotspots_headers,
        centered_columns={2, 6},
        table_name="tblImplementationHotspots",
        freeze_panes="A5",
        style_header_row=style_header_row,
        style_data_cell=style_data_cell,
        apply_zebra_stripes=apply_zebra_stripes,
        add_table=add_table,
    )
    if max_row > 4:
        ws.conditional_formatting.add(
            f"F5:F{max_row}",
            data_bar_rule(
                start_type="num",
                start_value=0,
                end_type="num",
                end_value=1,
                color="B45309",
            ),
        )
    auto_width(ws, len(implementation_hotspots_headers), max_row)
