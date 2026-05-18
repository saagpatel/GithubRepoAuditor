"""Helpers for building run-changes workbook content."""

from __future__ import annotations

from src.report_enrichment import (
    build_run_change_counts,
    build_run_change_summary,
    no_baseline_summary,
)


def build_run_changes_content(
    data: dict,
    diff_data: dict | None,
) -> tuple[str, str, list[tuple[str, object]], list[tuple[str, list[list[object]], list[str]]]]:
    counts = build_run_change_counts(diff_data)
    summary = data.get("run_change_summary") or build_run_change_summary(diff_data)
    comparison_window = (
        f"{(diff_data or {}).get('previous_date', '')[:10]} -> "
        f"{(diff_data or {}).get('current_date', data.get('generated_at', ''))[:10]}"
        if diff_data
        else no_baseline_summary()
    )
    summary_cards = [
        ("Improvements", counts.get("score_improvements", 0)),
        ("Regressions", counts.get("score_regressions", 0)),
        ("Promotions", counts.get("tier_promotions", 0)),
        ("Demotions", counts.get("tier_demotions", 0)),
        ("Security", counts.get("security_changes", 0)),
        ("Governance", counts.get("collection_changes", 0)),
    ]

    sections: list[tuple[str, list[list[object]], list[str]]] = []
    improvements = sorted(
        (diff_data or {}).get("score_changes", []),
        key=lambda item: item.get("delta", 0.0),
        reverse=True,
    )
    regressions = sorted(
        (diff_data or {}).get("score_changes", []), key=lambda item: item.get("delta", 0.0)
    )[:5]
    sections.append(
        (
            "Biggest Score Gains",
            [
                [
                    item.get("name", ""),
                    round(item.get("delta", 0.0), 3),
                    round(item.get("new_score", 0.0), 3),
                ]
                for item in improvements[:5]
            ],
            ["Repo", "Delta", "New Score"],
        )
    )
    sections.append(
        (
            "Biggest Regressions",
            [
                [
                    item.get("name", ""),
                    round(item.get("delta", 0.0), 3),
                    round(item.get("new_score", 0.0), 3),
                ]
                for item in regressions[:5]
            ],
            ["Repo", "Delta", "New Score"],
        )
    )
    tier_changes = (diff_data or {}).get("tier_changes", [])
    promotions = [item for item in tier_changes if item.get("direction") == "promotion"][:5]
    demotions = [item for item in tier_changes if item.get("direction") == "demotion"][:5]
    sections.append(
        (
            "Tier Promotions / Demotions",
            [
                [
                    item.get("name", ""),
                    item.get("old_tier", ""),
                    item.get("new_tier", ""),
                    item.get("direction", ""),
                ]
                for item in promotions + demotions
            ],
            ["Repo", "Old Tier", "New Tier", "Movement"],
        )
    )
    blocked_items = [
        item for item in (data.get("operator_queue") or []) if item.get("lane") == "blocked"
    ][:5]
    sections.append(
        (
            "Newly Blocked Items",
            [
                [
                    item.get("repo", ""),
                    item.get("title", ""),
                    item.get("lane_reason", "") or item.get("summary", ""),
                ]
                for item in blocked_items
            ],
            ["Repo", "Item", "Why"],
        )
    )
    reopened = [
        item
        for item in (data.get("material_changes") or [])
        if "reopen" in str(item.get("change_type", "")).lower()
    ][:5]
    sections.append(
        (
            "Reopened Items",
            [
                [item.get("repo", ""), item.get("title", ""), item.get("change_type", "")]
                for item in reopened
            ],
            ["Repo", "Title", "Type"],
        )
    )
    pressure_rows = []
    for item in (data.get("governance_drift") or [])[:5]:
        pressure_rows.append(
            [item.get("repo_full_name", ""), item.get("drift_type", ""), "governance"]
        )
    for item in (diff_data or {}).get("security_changes", [])[:5]:
        pressure_rows.append([item.get("name", ""), item.get("new_label", ""), "security"])
    sections.append(
        (
            "New Security / Governance Pressure",
            pressure_rows[:5],
            ["Repo", "Signal", "Area"],
        )
    )
    return summary, comparison_window, summary_cards, sections


def normalize_run_changes_sections(
    sections: list[tuple[str, list[list[object]], list[str]]],
) -> list[tuple[str, list[list[object]], list[str]]]:
    normalized: list[tuple[str, list[list[object]], list[str]]] = []
    for title, rows, headers in sections:
        section_rows = rows or [["No movement to call out yet.", "", ""][: len(headers)]]
        normalized.append((title, section_rows, headers))
    return normalized


def write_run_changes_summary(
    ws,
    *,
    summary: str,
    comparison_window: str,
    summary_cards: list[tuple[str, object]],
    subtitle_font,
    subheader_font,
    wrap_alignment,
    write_kpi_card,
) -> None:
    ws.merge_cells("A3:I3")
    ws["A3"] = summary
    ws["A3"].font = subtitle_font
    ws["A3"].alignment = wrap_alignment
    ws["A5"] = "Comparison Window"
    ws["A5"].font = subheader_font
    ws["B5"] = comparison_window
    ws["B5"].alignment = wrap_alignment

    for offset, (label, value) in enumerate(summary_cards):
        write_kpi_card(ws, 6, 1 + offset * 2, label, value)


def write_run_changes_sections(
    ws,
    sections: list[tuple[str, list[list[object]], list[str]]],
    *,
    start_row: int,
    section_font,
    style_header_row,
    style_data_cell,
    apply_zebra_stripes,
) -> int:
    row = start_row
    for title, rows, headers in sections:
        ws.cell(row=row, column=1, value=title).font = section_font
        header_row = row + 1
        for col, header in enumerate(headers, 1):
            ws.cell(row=header_row, column=col, value=header)
        style_header_row(ws, header_row, len(headers))
        for offset, values in enumerate(rows, 1):
            for col, value in enumerate(values, 1):
                style_data_cell(
                    ws.cell(row=header_row + offset, column=col, value=value),
                    "center" if isinstance(value, (int, float)) else "left",
                )
        if rows:
            apply_zebra_stripes(ws, header_row + 1, header_row + len(rows), len(headers))
        row = header_row + len(rows) + 2
    return row


def build_run_changes_sheet(
    wb,
    data: dict,
    diff_data: dict | None,
    *,
    get_or_create_sheet,
    configure_sheet_view,
    set_sheet_header,
    write_instruction_banner,
    build_run_changes_content_fn,
    normalize_run_changes_sections_fn,
    write_run_changes_summary_fn,
    write_run_changes_sections_fn,
    subtitle_font,
    subheader_font,
    wrap_alignment,
    write_kpi_card,
    section_font,
    style_header_row,
    style_data_cell,
    apply_zebra_stripes,
    auto_width,
) -> None:
    ws = get_or_create_sheet(wb, "Run Changes")
    ws.sheet_properties.tabColor = "0891B2"
    configure_sheet_view(ws, zoom=115, show_grid_lines=False)
    set_sheet_header(
        ws,
        "Run Changes",
        "Use this sheet to answer one question quickly: what moved since the last run, and what actually needs follow-through now?",
        width=9,
    )
    write_instruction_banner(
        ws,
        4,
        9,
        "Read this page top to bottom: scan the summary cards first, then check regressions, blocked items, and new security or governance pressure.",
    )
    ws.freeze_panes = "A9"

    summary, comparison_window, summary_cards, sections = build_run_changes_content_fn(
        data, diff_data
    )
    sections = normalize_run_changes_sections_fn(sections)
    write_run_changes_summary_fn(
        ws,
        summary=summary,
        comparison_window=comparison_window,
        summary_cards=summary_cards,
        subtitle_font=subtitle_font,
        subheader_font=subheader_font,
        wrap_alignment=wrap_alignment,
        write_kpi_card=write_kpi_card,
    )
    row = write_run_changes_sections_fn(
        ws,
        sections,
        start_row=9,
        section_font=section_font,
        style_header_row=style_header_row,
        style_data_cell=style_data_cell,
        apply_zebra_stripes=apply_zebra_stripes,
    )

    auto_width(ws, 9, row)
