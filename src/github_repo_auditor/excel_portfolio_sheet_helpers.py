"""Helpers for visible portfolio-oriented workbook sheets."""

from __future__ import annotations

from typing import Any

PORTFOLIO_EXPLORER_HEADERS = [
    "Repo",
    "Profile Score",
    "Overall",
    "Interest",
    "Tier",
    "Collections",
    "Lifecycle",
    "Criticality",
    "Disposition",
    "Operating Path",
    "Maturity",
    "Scorecard Gap",
    "Security",
    "Hotspots",
    "Top Hotspot",
    "Primary Action",
]

PORTFOLIO_CATALOG_HEADERS = [
    "Repo",
    "Owner",
    "Team",
    "Purpose",
    "Lifecycle",
    "Criticality",
    "Review Cadence",
    "Disposition",
    "Maturity Program",
    "Target Maturity",
    "Operating Path",
    "Path Override",
    "Path Confidence",
    "Intent Alignment",
    "Notes",
]

SCORECARDS_HEADERS = [
    "Repo",
    "Program",
    "Maturity",
    "Target",
    "Status",
    "Score",
    "Top Gaps",
    "Summary",
]


def build_portfolio_explorer_rows(
    ranked_audits: list[dict[str, Any]],
    *,
    build_maturity_gap_summary,
) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for entry in ranked_audits:
        audit = entry["audit"]
        top_action = (
            audit.get("action_candidates", [{}])[0].get("title", "")
            if audit.get("action_candidates")
            else ""
        )
        rows.append(
            [
                entry["name"],
                entry["profile_score"],
                entry["overall_score"],
                entry["interest_score"],
                entry["tier"],
                ", ".join(entry["collections"]),
                audit.get("portfolio_catalog", {}).get("lifecycle_state", "") or "—",
                audit.get("portfolio_catalog", {}).get("criticality", "") or "—",
                audit.get("portfolio_catalog", {}).get("intended_disposition", "") or "—",
                audit.get("portfolio_catalog", {}).get("operating_path", "") or "—",
                audit.get("scorecard", {}).get("maturity_level", "") or "—",
                build_maturity_gap_summary(audit),
                entry["security_label"],
                entry["hotspot_count"],
                entry["primary_hotspot"],
                top_action,
            ]
        )
    return rows


def build_portfolio_catalog_table_rows(audits: list[dict[str, Any]]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for audit in sorted(audits, key=lambda item: item.get("metadata", {}).get("name", "")):
        catalog = audit.get("portfolio_catalog", {})
        rows.append(
            [
                audit.get("metadata", {}).get("name", ""),
                catalog.get("owner", ""),
                catalog.get("team", ""),
                catalog.get("purpose", ""),
                catalog.get("lifecycle_state", "") or "—",
                catalog.get("criticality", "") or "—",
                catalog.get("review_cadence", "") or "—",
                catalog.get("intended_disposition", "") or "—",
                catalog.get("maturity_program", "") or "—",
                catalog.get("target_maturity", "") or "—",
                catalog.get("operating_path", "") or "—",
                catalog.get("path_override", "") or "—",
                catalog.get("path_confidence", "") or "—",
                catalog.get("intent_alignment", "missing-contract"),
                catalog.get("notes", "") or "—",
            ]
        )
    return rows


def build_scorecard_table_rows(audits: list[dict[str, Any]]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for audit in sorted(audits, key=lambda item: item.get("metadata", {}).get("name", "")):
        scorecard = audit.get("scorecard", {})
        rows.append(
            [
                audit.get("metadata", {}).get("name", ""),
                scorecard.get("program_label", "") or "—",
                scorecard.get("maturity_level", "") or "—",
                scorecard.get("target_maturity", "") or "—",
                scorecard.get("status", "") or "—",
                scorecard.get("score", 0.0),
                ", ".join(scorecard.get("top_gaps", [])) or "—",
                scorecard.get("summary", "") or "—",
            ]
        )
    return rows


def build_scorecards_sheet(
    wb,
    data: dict[str, Any],
    *,
    get_or_create_sheet,
    configure_sheet_view,
    set_sheet_header,
    build_scorecards_summary,
    subtitle_font,
    wrap_alignment,
    build_scorecard_table_rows_fn,
    write_portfolio_table,
    style_header_row,
    style_data_cell,
    apply_zebra_stripes,
    add_table,
    auto_width,
) -> None:
    ws = get_or_create_sheet(wb, "Scorecards")
    ws.sheet_properties.tabColor = "7C3AED"
    configure_sheet_view(ws, zoom=110, show_grid_lines=True)
    set_sheet_header(
        ws,
        "Scorecards",
        "Use this sheet to compare each repo against the maturity bar that matches its intended role.",
        width=10,
    )
    ws.merge_cells("A3:H3")
    ws["A3"] = build_scorecards_summary(data)
    ws["A3"].font = subtitle_font
    ws["A3"].alignment = wrap_alignment
    start_row = 5

    scorecard_rows = build_scorecard_table_rows_fn(data.get("audits", []))
    write_portfolio_table(
        ws,
        scorecard_rows,
        start_row=start_row,
        headers=SCORECARDS_HEADERS,
        freeze_panes="B6",
        table_name="tblScorecards",
        centered_columns={3, 4, 5, 6},
        style_header_row=style_header_row,
        style_data_cell=style_data_cell,
        apply_zebra_stripes=apply_zebra_stripes,
        add_table=add_table,
        auto_width=auto_width,
    )


def write_portfolio_table(
    ws,
    rows: list[list[Any]],
    *,
    start_row: int,
    headers: list[str],
    freeze_panes: str,
    table_name: str,
    centered_columns: set[int],
    style_header_row,
    style_data_cell,
    apply_zebra_stripes,
    add_table,
    auto_width,
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
    auto_width(ws, len(headers), max_row)
    return max_row


def build_portfolio_explorer_sheet(
    wb,
    data: dict[str, Any],
    *,
    portfolio_profile: str = "default",
    collection: str | None = None,
    build_analyst_context,
    get_or_create_sheet,
    configure_sheet_view,
    set_sheet_header,
    subtitle_font,
    wrap_alignment,
    style_header_row,
    style_data_cell,
    apply_zebra_stripes,
    add_table,
    auto_width,
    build_maturity_gap_summary,
) -> None:
    context = build_analyst_context(
        data,
        profile_name=portfolio_profile,
        collection_name=collection,
    )
    ws = get_or_create_sheet(wb, "Portfolio Explorer")
    ws.sheet_properties.tabColor = "1D4ED8"
    configure_sheet_view(ws, zoom=110, show_grid_lines=True)
    set_sheet_header(
        ws,
        "Portfolio Explorer",
        "Use this sheet to rank the portfolio, sort by profile-aware score, and drill from summary into repo-level facts.",
        width=10,
    )
    ws.merge_cells("A3:P3")
    ws["A3"] = (
        "How to use this sheet: sort by Profile Score first, then use the catalog columns to separate intentional experiments from maintained assets before drilling in."
    )
    ws["A3"].font = subtitle_font
    ws["A3"].alignment = wrap_alignment
    start_row = 5

    explorer_rows = build_portfolio_explorer_rows(
        context["ranked_audits"],
        build_maturity_gap_summary=build_maturity_gap_summary,
    )
    write_portfolio_table(
        ws,
        explorer_rows,
        start_row=start_row,
        headers=PORTFOLIO_EXPLORER_HEADERS,
        freeze_panes="B6",
        table_name="tblPortfolioExplorer",
        centered_columns={2, 3, 4, 8},
        style_header_row=style_header_row,
        style_data_cell=style_data_cell,
        apply_zebra_stripes=apply_zebra_stripes,
        add_table=add_table,
        auto_width=auto_width,
    )


def build_portfolio_catalog_sheet(
    wb,
    data: dict[str, Any],
    *,
    get_or_create_sheet,
    configure_sheet_view,
    set_sheet_header,
    build_portfolio_catalog_summary,
    build_portfolio_intent_alignment_summary,
    build_operating_paths_summary,
    subtitle_font,
    wrap_alignment,
    style_header_row,
    style_data_cell,
    apply_zebra_stripes,
    add_table,
    auto_width,
) -> None:
    ws = get_or_create_sheet(wb, "Portfolio Catalog")
    ws.sheet_properties.tabColor = "4F46E5"
    configure_sheet_view(ws, zoom=110, show_grid_lines=True)
    set_sheet_header(
        ws,
        "Portfolio Catalog",
        "Use this sheet to see what each repo is supposed to be, who owns it, and whether its current state still matches that intent.",
        width=10,
    )
    ws.merge_cells("A3:O3")
    ws["A3"] = build_portfolio_catalog_summary(data)
    ws["A3"].font = subtitle_font
    ws["A3"].alignment = wrap_alignment
    ws.merge_cells("A4:O4")
    ws["A4"] = build_portfolio_intent_alignment_summary(data)
    ws["A4"].font = subtitle_font
    ws["A4"].alignment = wrap_alignment
    ws.merge_cells("A5:O5")
    ws["A5"] = build_operating_paths_summary(data)
    ws["A5"].font = subtitle_font
    ws["A5"].alignment = wrap_alignment
    start_row = 7

    catalog_rows = build_portfolio_catalog_table_rows(data.get("audits", []))
    write_portfolio_table(
        ws,
        catalog_rows,
        start_row=start_row,
        headers=PORTFOLIO_CATALOG_HEADERS,
        freeze_panes="B8",
        table_name="tblPortfolioCatalog",
        centered_columns=set(),
        style_header_row=style_header_row,
        style_data_cell=style_data_cell,
        apply_zebra_stripes=apply_zebra_stripes,
        add_table=add_table,
        auto_width=auto_width,
    )
