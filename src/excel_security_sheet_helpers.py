"""Helpers for Security workbook content."""

from __future__ import annotations

from typing import Any

SECURITY_HEADERS = [
    "Repo",
    "Score",
    "Secrets",
    "Dangerous Files",
    "SECURITY.md",
    "Dependabot",
    "GitHub",
    "Findings",
]

SECURITY_CONTROLS_HEADERS = [
    "Repo",
    "SECURITY.md",
    "Dependabot",
    "Dependency Graph",
    "SBOM",
    "Code Scanning",
    "Secret Scanning",
]

SUPPLY_CHAIN_HEADERS = [
    "Repo",
    "Security Score",
    "Dependency Graph",
    "SBOM",
    "Scorecard",
    "Top Recommendation",
]

SECURITY_DEBT_HEADERS = ["Repo", "Priority", "Action", "Expected Lift", "Effort", "Source"]


def build_security_sheet_rows(audits: list[dict[str, Any]]) -> list[list[Any]]:
    ranked_audits = sorted(
        audits, key=lambda audit: audit.get("security_posture", {}).get("score", 1.0)
    )
    rows: list[list[Any]] = []
    for audit in ranked_audits:
        posture = audit.get("security_posture", {})
        local = posture.get("local", {})
        github = posture.get("github", {})
        metadata = audit.get("metadata", {})
        rows.append(
            [
                metadata.get("name", ""),
                round(posture.get("score", 0), 2),
                local.get("secrets_found", posture.get("secrets_found", 0)),
                ", ".join(
                    str(file_name)
                    for file_name in local.get(
                        "dangerous_files", posture.get("dangerous_files", [])
                    )[:3]
                ),
                "Yes" if posture.get("has_security_md") else "No",
                "Yes" if posture.get("has_dependabot") else "No",
                "Yes" if github.get("provider_available") else "No",
                "; ".join(posture.get("evidence", [])[:3]),
            ]
        )
    return rows


def build_security_controls_rows(audits: list[dict[str, Any]]) -> list[list[Any]]:
    ranked_audits = sorted(
        audits, key=lambda audit: audit.get("security_posture", {}).get("score", 0.0)
    )
    return [
        [
            audit.get("metadata", {}).get("name", ""),
            "Yes" if posture.get("has_security_md") else "No",
            "Yes" if posture.get("has_dependabot") else "No",
            github.get("dependency_graph_status", "unavailable"),
            github.get("sbom_status", "unavailable"),
            github.get("code_scanning_status", "unavailable"),
            github.get("secret_scanning_status", "unavailable"),
        ]
        for audit in ranked_audits
        for posture in [audit.get("security_posture", {})]
        for github in [posture.get("github", {})]
    ]


def build_supply_chain_rows(audits: list[dict[str, Any]]) -> list[list[Any]]:
    ranked_audits = sorted(
        audits, key=lambda audit: audit.get("security_posture", {}).get("score", 0.0)
    )
    return [
        [
            audit.get("metadata", {}).get("name", ""),
            posture.get("score", 0.0),
            github.get("dependency_graph_status", "unavailable"),
            github.get("sbom_status", "unavailable"),
            scorecard.get("score", ""),
            recommendation.get("title", ""),
        ]
        for audit in ranked_audits
        for posture in [audit.get("security_posture", {})]
        for github in [posture.get("github", {})]
        for scorecard in [posture.get("scorecard", {})]
        for recommendation in [next(iter(posture.get("recommendations", [])), {})]
    ]


def build_security_debt_rows(preview: list[dict[str, Any]]) -> list[list[Any]]:
    return [
        [
            item.get("repo", ""),
            item.get("priority", "medium"),
            item.get("title", ""),
            item.get("expected_posture_lift", 0.0),
            item.get("effort", ""),
            item.get("source", ""),
        ]
        for item in preview
    ]


def write_security_table(
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


def build_security_sheet(
    wb,
    data: dict[str, Any],
    *,
    get_or_create_sheet,
    configure_sheet_view,
    build_security_sheet_rows_fn,
    write_security_table_fn,
    security_headers: list[str],
    style_header_row,
    style_data_cell,
    apply_zebra_stripes,
    add_table,
    color_scale_rule,
    icon_set_rule,
    heatmap_red: str,
    heatmap_amber: str,
    heatmap_green: str,
    auto_width,
) -> None:
    ws = get_or_create_sheet(wb, "Security")
    ws.sheet_properties.tabColor = "991B1B"
    configure_sheet_view(ws, zoom=105, show_grid_lines=True)
    rows = build_security_sheet_rows_fn(data.get("audits", []))
    max_row = write_security_table_fn(
        ws,
        rows,
        start_row=1,
        headers=security_headers,
        freeze_panes="B2",
        table_name="tblSecurity",
        centered_columns=set(),
        style_header_row=style_header_row,
        style_data_cell=style_data_cell,
        apply_zebra_stripes=apply_zebra_stripes,
        add_table=add_table,
    )
    if max_row > 1:
        ws.conditional_formatting.add(
            f"B2:B{max_row}",
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
        ws.conditional_formatting.add(
            f"B2:B{max_row}",
            icon_set_rule("3TrafficLights1", "num", [0, 0.4, 0.7]),
    )
    auto_width(ws, len(security_headers), max_row)


def build_security_controls_sheet(
    wb,
    data: dict[str, Any],
    *,
    get_or_create_sheet,
    configure_sheet_view,
    build_security_controls_rows_fn,
    write_security_table_fn,
    security_controls_headers: list[str],
    style_header_row,
    style_data_cell,
    apply_zebra_stripes,
    add_table,
    auto_width,
) -> None:
    ws = get_or_create_sheet(wb, "Security Controls")
    ws.sheet_properties.tabColor = "0F766E"
    configure_sheet_view(ws, zoom=105, show_grid_lines=True)
    rows = build_security_controls_rows_fn(data.get("audits", []))
    max_row = write_security_table_fn(
        ws,
        rows,
        start_row=1,
        headers=security_controls_headers,
        freeze_panes="B2",
        table_name="tblSecurityControlsView",
        centered_columns={2, 3, 4, 5, 6, 7},
        style_header_row=style_header_row,
        style_data_cell=style_data_cell,
        apply_zebra_stripes=apply_zebra_stripes,
        add_table=add_table,
    )
    auto_width(ws, len(security_controls_headers), max_row)


def build_supply_chain_sheet(
    wb,
    data: dict[str, Any],
    *,
    get_or_create_sheet,
    configure_sheet_view,
    build_supply_chain_rows_fn,
    write_security_table_fn,
    supply_chain_headers: list[str],
    style_header_row,
    style_data_cell,
    apply_zebra_stripes,
    add_table,
    auto_width,
) -> None:
    ws = get_or_create_sheet(wb, "Supply Chain")
    ws.sheet_properties.tabColor = "7C3AED"
    configure_sheet_view(ws, zoom=105, show_grid_lines=True)
    rows = build_supply_chain_rows_fn(data.get("audits", []))
    max_row = write_security_table_fn(
        ws,
        rows,
        start_row=1,
        headers=supply_chain_headers,
        freeze_panes="B2",
        table_name="tblSupplyChain",
        centered_columns={2, 3, 4, 5},
        style_header_row=style_header_row,
        style_data_cell=style_data_cell,
        apply_zebra_stripes=apply_zebra_stripes,
        add_table=add_table,
    )
    auto_width(ws, len(supply_chain_headers), max_row)


def build_security_debt_sheet(
    wb,
    data: dict[str, Any],
    *,
    get_or_create_sheet,
    configure_sheet_view,
    build_security_debt_rows_fn,
    write_security_table_fn,
    security_debt_headers: list[str],
    style_header_row,
    style_data_cell,
    apply_zebra_stripes,
    add_table,
    auto_width,
) -> None:
    ws = get_or_create_sheet(wb, "Security Debt")
    ws.sheet_properties.tabColor = "B91C1C"
    configure_sheet_view(ws, zoom=105, show_grid_lines=True)
    rows = build_security_debt_rows_fn(data.get("security_governance_preview", []))
    max_row = write_security_table_fn(
        ws,
        rows,
        start_row=1,
        headers=security_debt_headers,
        freeze_panes="A2",
        table_name="tblSecurityDebt",
        centered_columns={2, 4, 5, 6},
        style_header_row=style_header_row,
        style_data_cell=style_data_cell,
        apply_zebra_stripes=apply_zebra_stripes,
        add_table=add_table,
    )
    auto_width(ws, len(security_debt_headers), max_row)
