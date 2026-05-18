"""Helpers for profile and trend workbook sheets."""

from __future__ import annotations

from typing import Any

BY_LENS_HEADERS = [
    "Repo",
    "Profile Score",
    "Tier",
    "Ship Readiness",
    "Maintenance Risk",
    "Showcase",
    "Security",
    "Momentum",
    "Portfolio Fit",
]

BY_COLLECTION_HEADERS = ["Collection", "Repos", "Description", "Top Repo", "Top Score"]
TREND_SUMMARY_HEADERS = [
    "Date",
    "Average Score",
    "Repos",
    "Shipped",
    "Functional",
    "Review Emitted",
    "Campaign Drift",
    "Governance Drift",
]
TREND_SUMMARY_TOP_REPO_HEADERS = ["Repo", "Trendline", "Latest Score"]


def build_by_lens_rows(ranked_audits: list[dict[str, Any]]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for entry in ranked_audits:
        lenses = entry["audit"].get("lenses", {})
        rows.append(
            [
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
        )
    return rows


def build_by_lens_sheet(
    wb,
    data: dict[str, Any],
    *,
    portfolio_profile: str,
    collection: str | None,
    build_analyst_context,
    get_or_create_sheet,
    configure_sheet_view,
    set_sheet_header,
    subtitle_font,
    wrap_alignment,
    build_by_lens_rows_fn,
    write_portfolio_table,
    style_header_row,
    style_data_cell,
    apply_zebra_stripes,
    add_table,
    auto_width,
) -> None:
    context = build_analyst_context(
        data, profile_name=portfolio_profile, collection_name=collection
    )
    ws = get_or_create_sheet(wb, "By Lens")
    ws.sheet_properties.tabColor = "0F766E"
    configure_sheet_view(ws, zoom=110, show_grid_lines=True)
    set_sheet_header(
        ws,
        "By Lens",
        "Compare the same repos through different decision lenses so you can separate shipped work, risk, momentum, and showcase value.",
        width=9,
    )
    ws.merge_cells("A3:I3")
    ws["A3"] = (
        f"Current view: profile {portfolio_profile} | collection {collection or 'all'} | use this sheet to compare the same repo through multiple decision lenses."
    )
    ws["A3"].font = subtitle_font
    ws["A3"].alignment = wrap_alignment
    start_row = 5

    lens_rows = build_by_lens_rows_fn(context["ranked_audits"])
    write_portfolio_table(
        ws,
        lens_rows,
        start_row=start_row,
        headers=BY_LENS_HEADERS,
        freeze_panes="B6",
        table_name="tblByLens",
        centered_columns={2, 3, 4, 5, 6, 7, 8, 9},
        style_header_row=style_header_row,
        style_data_cell=style_data_cell,
        apply_zebra_stripes=apply_zebra_stripes,
        add_table=add_table,
        auto_width=auto_width,
    )


def build_by_collection_rows(
    data: dict[str, Any],
    *,
    portfolio_profile: str,
    build_analyst_context,
) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for collection_name in data.get("collections", {}).keys():
        context = build_analyst_context(
            data, profile_name=portfolio_profile, collection_name=collection_name
        )
        leaders = context.get("profile_leaderboard", {}).get("leaders", [])
        collection_data = data.get("collections", {}).get(collection_name, {})
        rows.append(
            [
                collection_name,
                len(collection_data.get("repos", [])),
                collection_data.get("description", ""),
                leaders[0]["name"] if leaders else "",
                leaders[0]["profile_score"] if leaders else 0.0,
            ]
        )
    return rows


def build_by_collection_sheet(
    wb,
    data: dict[str, Any],
    *,
    portfolio_profile: str,
    build_analyst_context,
    get_or_create_sheet,
    configure_sheet_view,
    set_sheet_header,
    subtitle_font,
    wrap_alignment,
    build_by_collection_rows_fn,
    write_portfolio_table,
    style_header_row,
    style_data_cell,
    apply_zebra_stripes,
    add_table,
    auto_width,
) -> None:
    ws = get_or_create_sheet(wb, "By Collection")
    ws.sheet_properties.tabColor = "7C3AED"
    configure_sheet_view(ws, zoom=115, show_grid_lines=True)
    set_sheet_header(
        ws,
        "By Collection",
        "Use this sheet to understand which collections are concentrated, which repos lead them, and where your showcase value is clustered.",
        width=5,
    )
    ws.merge_cells("A3:E3")
    ws["A3"] = (
        f"Current profile: {portfolio_profile}. Use this sheet to see how each collection groups related repos and where its best work sits."
    )
    ws["A3"].font = subtitle_font
    ws["A3"].alignment = wrap_alignment
    start_row = 5

    collection_rows = build_by_collection_rows_fn(
        data,
        portfolio_profile=portfolio_profile,
        build_analyst_context=build_analyst_context,
    )
    write_portfolio_table(
        ws,
        collection_rows,
        start_row=start_row,
        headers=BY_COLLECTION_HEADERS,
        freeze_panes="B6",
        table_name="tblByCollection",
        centered_columns={2, 5},
        style_header_row=style_header_row,
        style_data_cell=style_data_cell,
        apply_zebra_stripes=apply_zebra_stripes,
        add_table=add_table,
        auto_width=auto_width,
    )


def build_trend_summary_content(
    *,
    extended_trends: list[dict[str, Any]],
    extended_score_history: dict[str, list[float]],
    render_sparkline,
) -> dict[str, Any]:
    trend_rows = [
        [
            trend.get("date", ""),
            trend.get("average_score", 0.0),
            trend.get("repos_audited", 0),
            trend.get("tier_distribution", {}).get("shipped", 0),
            trend.get("tier_distribution", {}).get("functional", 0),
            "yes" if trend.get("review_emitted") else "no",
            trend.get("campaign_drift_count", 0),
            trend.get("governance_drift_count", 0),
        ]
        for trend in extended_trends
    ]
    top_repo_rows = [
        [repo_name, render_sparkline(scores), scores[-1] if scores else 0.0]
        for repo_name, scores in sorted(extended_score_history.items())[:10]
    ]
    return {
        "trend_rows": trend_rows,
        "top_repo_rows": top_repo_rows,
    }


def write_trend_summary_sections(
    ws,
    content: dict[str, Any],
    *,
    start_row: int,
    style_header_row,
    style_data_cell,
    section_font,
) -> int:
    for col, header in enumerate(TREND_SUMMARY_HEADERS, 1):
        ws.cell(row=start_row, column=col, value=header)
    style_header_row(ws, start_row, len(TREND_SUMMARY_HEADERS))
    ws.freeze_panes = "A6"

    for offset, values in enumerate(content["trend_rows"], 1):
        for col, value in enumerate(values, 1):
            style_data_cell(
                ws.cell(row=start_row + offset, column=col, value=value),
                "center" if col != 1 else "left",
            )

    summary_row = start_row + len(content["trend_rows"]) + 3
    ws.cell(row=summary_row, column=1, value="Top Repo Trendlines").font = section_font
    for col, header in enumerate(TREND_SUMMARY_TOP_REPO_HEADERS, 1):
        ws.cell(row=summary_row + 1, column=col, value=header)
    style_header_row(ws, summary_row + 1, len(TREND_SUMMARY_TOP_REPO_HEADERS))
    for offset, values in enumerate(content["top_repo_rows"], 2):
        for col, value in enumerate(values, 1):
            style_data_cell(
                ws.cell(row=summary_row + offset, column=col, value=value),
                "center" if col == 3 else "left",
            )

    return summary_row + len(content["top_repo_rows"]) + 1


def build_trend_summary_sheet(
    wb,
    data: dict[str, Any],
    *,
    trend_data: list[dict[str, Any]] | None = None,
    score_history: dict[str, list[float]] | None = None,
    extend_portfolio_trend_with_current,
    extend_score_history_with_current,
    get_or_create_sheet,
    configure_sheet_view,
    set_sheet_header,
    subtitle_font,
    wrap_alignment,
    build_trend_summary_content_fn,
    write_trend_summary_sections_fn,
    render_sparkline,
    style_header_row,
    style_data_cell,
    section_font,
    add_table,
    auto_width,
) -> None:
    extended_trends = extend_portfolio_trend_with_current(data, trend_data)
    extended_score_history = extend_score_history_with_current(data, score_history)
    ws = get_or_create_sheet(wb, "Trend Summary")
    ws.sheet_properties.tabColor = "0EA5E9"
    configure_sheet_view(ws, zoom=115, show_grid_lines=False)
    set_sheet_header(
        ws,
        "Trend Summary",
        "Track portfolio movement over time, then scan the short repo trendlines below to see who is actually improving or drifting.",
        width=8,
    )
    ws.merge_cells("A3:H3")
    ws["A3"] = (
        "Use this sheet when you want portfolio-wide movement first, then repo-level trendlines second."
    )
    ws["A3"].font = subtitle_font
    ws["A3"].alignment = wrap_alignment
    start_row = 5

    content = build_trend_summary_content_fn(
        extended_trends=extended_trends,
        extended_score_history=extended_score_history,
        render_sparkline=render_sparkline,
    )
    max_row = write_trend_summary_sections_fn(
        ws,
        content,
        start_row=start_row,
        style_header_row=style_header_row,
        style_data_cell=style_data_cell,
        section_font=section_font,
    )
    if content["trend_rows"]:
        add_table(
            ws,
            "tblTrendSummary",
            len(TREND_SUMMARY_HEADERS),
            start_row + len(content["trend_rows"]),
            start_row=start_row,
        )
    auto_width(ws, max(8, len(TREND_SUMMARY_HEADERS)), max_row)
