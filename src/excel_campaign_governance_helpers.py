"""Helpers for campaign and governance workbook sheets."""

from __future__ import annotations

from typing import Any

CAMPAIGN_HEADERS = [
    "Repo",
    "Issue",
    "Topics",
    "Projects",
    "Notion Actions",
    "Action IDs",
    "Drift",
    "Sync Mode",
]

WRITEBACK_AUDIT_HEADERS = ["Repo", "Target", "Status", "Rollback", "URL", "Details"]
GOVERNANCE_CONTROLS_HEADERS = [
    "Repo",
    "Action",
    "State",
    "Expected Lift",
    "Effort",
    "Source",
    "Why",
]


def build_campaign_sheet_content(
    data: dict[str, Any],
) -> dict[str, Any]:
    summary = data.get("campaign_summary", {}) or {}
    preview_rows = data.get("writeback_preview", {}).get("repos", []) or []
    github_projects = data.get("writeback_preview", {}).get("github_projects", {}) or {}
    sync_mode = data.get("writeback_preview", {}).get("sync_mode", "reconcile")
    campaign_requested = bool(summary.get("campaign_type") or summary.get("label"))
    request_state = (
        "Campaign requested from the current report facts."
        if campaign_requested
        else "No campaign requested in this run."
    )
    row_state = (
        "Campaign rows are present. External mutation stays manual until writeback apply is explicitly requested."
        if preview_rows
        else (
            "Campaign requested but no current rows matched."
            if campaign_requested
            else "No current rows because no managed campaign was requested."
        )
    )
    github_projects_summary = (
        f"{github_projects.get('status', 'disabled')} "
        f"({github_projects.get('project_owner', '—')} #{github_projects.get('project_number', 0)})"
        if github_projects.get("enabled")
        else "disabled"
    )
    drift_repo_keys = {
        drift.get("repo_full_name") or drift.get("repo") or ""
        for drift in data.get("managed_state_drift", []) or []
    }
    table_rows = [
        [
            item.get("repo", ""),
            item.get("issue_title", ""),
            ", ".join(item.get("topics", [])),
            item.get("github_project_field_count", 0),
            item.get("notion_action_count", 0),
            ", ".join(item.get("action_ids", [])),
            "yes"
            if (item.get("repo_full_name") or item.get("repo") or "") in drift_repo_keys
            else "no",
            sync_mode,
        ]
        for item in preview_rows
    ]
    return {
        "summary_rows": [
            ("Campaign", summary.get("label", summary.get("campaign_type", "No active campaign"))),
            ("Request State", request_state),
            ("Row State", row_state),
            ("Profile", summary.get("portfolio_profile", "default")),
            ("Collection", summary.get("collection_name") or "all"),
            ("Actions", summary.get("action_count", 0)),
            ("Repos", summary.get("repo_count", 0)),
            ("Sync Mode", sync_mode),
            ("GitHub Projects", github_projects_summary),
        ],
        "table_rows": table_rows,
        "empty_message": "No active campaign rows are present in this run. When campaign preview or apply is in use, managed repo rows will appear here with drift and sync context.",
    }


def build_governance_controls_content(
    data: dict[str, Any],
    *,
    display_operator_state,
    approval_workflow_label: str,
    next_approval_review_label: str,
) -> dict[str, Any]:
    governance_summary = data.get("governance_summary", {}) or {}
    preview = governance_summary.get("top_actions") or data.get(
        "security_governance_preview", []
    )
    preview_only_source = not governance_summary.get("top_actions")

    table_rows: list[list[Any]] = []
    for item in preview:
        operator_state = item.get("operator_state")
        if not operator_state and preview_only_source:
            operator_state = "preview-only"
        if not operator_state and governance_summary.get("status") == "preview":
            operator_state = "preview-only"
        if not operator_state and item.get("preview_only"):
            operator_state = "preview-only"
        if not operator_state and item.get("applyable") is False:
            operator_state = "preview-only"
        table_rows.append(
            [
                item.get("repo", ""),
                item.get("title", ""),
                display_operator_state(operator_state or item.get("priority", "medium")),
                item.get("expected_posture_lift", 0.0),
                item.get("effort", ""),
                item.get("source", ""),
                item.get("why", ""),
            ]
        )

    return {
        "summary_rows": [
            ("Status", display_operator_state(governance_summary.get("status", "preview"))),
            (
                "Selected View",
                governance_summary.get(
                    "selected_view",
                    data.get("governance_preview", {}).get("selected_view", "all"),
                ),
            ),
            (
                "Approval",
                display_operator_state(
                    governance_summary.get("approval_status", "preview-only")
                ),
            ),
            ("Needs Re-Approval", "yes" if governance_summary.get("needs_reapproval") else "no"),
            ("Rollback Available", governance_summary.get("rollback_available_count", 0)),
            (
                "Headline",
                governance_summary.get(
                    "headline", "Governed controls are being tracked locally."
                ),
            ),
            (
                approval_workflow_label,
                (data.get("approval_workflow_summary") or {}).get(
                    "summary",
                    "No current approval needs review yet, so the approval workflow can stay local for now.",
                ),
            ),
            (
                next_approval_review_label,
                (data.get("next_approval_review") or {}).get(
                    "summary",
                    "Stay local for now; no current approval needs review.",
                ),
            ),
        ],
        "table_rows": table_rows,
        "empty_message": "No governed controls are in scope for this run. This can be expected for audit-only runs or when everything is already aligned.",
    }


def write_campaign_table(
    ws,
    *,
    start_row: int,
    preview_rows: list[list[Any]],
    empty_message: str,
    style_header_row,
    add_table,
    apply_zebra_stripes,
    wrap_alignment,
    subtitle_font,
) -> int:
    for col, header in enumerate(CAMPAIGN_HEADERS, 1):
        ws.cell(row=start_row, column=col, value=header)
    style_header_row(ws, start_row, len(CAMPAIGN_HEADERS))
    ws.freeze_panes = f"A{start_row + 1}"

    for row, values in enumerate(preview_rows, start_row + 1):
        for col, value in enumerate(values, 1):
            ws.cell(row=row, column=col, value=value)

    max_row = start_row + len(preview_rows)
    if preview_rows:
        apply_zebra_stripes(ws, start_row + 1, max_row, len(CAMPAIGN_HEADERS))
        add_table(ws, "tblCampaignView", len(CAMPAIGN_HEADERS), max_row, start_row)
    else:
        ws.merge_cells(start_row=start_row + 1, start_column=1, end_row=start_row + 2, end_column=8)
        ws.cell(row=start_row + 1, column=1, value=empty_message).alignment = wrap_alignment
        ws.cell(row=start_row + 1, column=1).font = subtitle_font
    return max_row


def build_campaigns_sheet(
    wb,
    data: dict[str, Any],
    *,
    get_or_create_sheet,
    configure_sheet_view,
    set_sheet_header,
    build_campaign_sheet_content_fn,
    write_key_value_block,
    action_sync_readiness_rows,
    action_sync_readiness_title: str,
    write_campaign_table_fn,
    style_header_row,
    add_table,
    apply_zebra_stripes,
    wrap_alignment,
    subtitle_font,
    auto_width,
) -> None:
    ws = get_or_create_sheet(wb, "Campaigns")
    ws.sheet_properties.tabColor = "7C3AED"
    configure_sheet_view(ws, zoom=115, show_grid_lines=False)
    content = build_campaign_sheet_content_fn(data)
    set_sheet_header(
        ws,
        "Campaigns",
        "Managed campaign state stays local-authoritative here. This sheet is where you see open work, stale items, and whether there is anything to reconcile.",
        width=8,
    )
    summary_end_row = write_key_value_block(
        ws,
        4,
        1,
        content["summary_rows"],
        title="Current Campaign State",
    )
    write_key_value_block(
        ws,
        4,
        10,
        action_sync_readiness_rows(data),
        title=action_sync_readiness_title,
    )
    start_row = summary_end_row + 2
    max_row = write_campaign_table_fn(
        ws,
        start_row=start_row,
        preview_rows=content["table_rows"],
        empty_message=content["empty_message"],
        style_header_row=style_header_row,
        add_table=add_table,
        apply_zebra_stripes=apply_zebra_stripes,
        wrap_alignment=wrap_alignment,
        subtitle_font=subtitle_font,
    )
    auto_width(ws, len(CAMPAIGN_HEADERS), max_row)


def build_writeback_audit_content(results: list[dict[str, Any]]) -> dict[str, Any]:
    created = sum(1 for result in results if result.get("status") == "created")
    updated = sum(1 for result in results if result.get("status") == "updated")
    closed = sum(1 for result in results if result.get("status") == "closed")
    rollback_ready = sum(1 for result in results if result.get("before") not in ({}, None, []))
    return {
        "summary_rows": [
            ("Writeback Rows", len(results)),
            ("Rollback Ready", rollback_ready),
            ("Created / Updated / Closed", f"{created} / {updated} / {closed}"),
        ],
        "table_rows": [
            [
                result.get("repo_full_name", ""),
                result.get("target", ""),
                result.get("status", ""),
                "yes" if result.get("before") not in ({}, None, []) else "partial",
                result.get("url", ""),
                result,
            ]
            for result in results
        ],
        "empty_message": "No writeback results are recorded for this run. Preview-only workflows and audit-only runs will leave this sheet intentionally empty.",
    }


def write_writeback_audit_table(
    ws,
    *,
    start_row: int,
    table_rows: list[list[Any]],
    empty_message: str,
    style_header_row,
    add_table,
    apply_zebra_stripes,
    wrap_alignment,
    subtitle_font,
    serialize_details,
) -> int:
    for col, header in enumerate(WRITEBACK_AUDIT_HEADERS, 1):
        ws.cell(row=start_row, column=col, value=header)
    style_header_row(ws, start_row, len(WRITEBACK_AUDIT_HEADERS))
    ws.freeze_panes = "A11"

    for row_number, values in enumerate(table_rows, start_row + 1):
        for col, value in enumerate(values, 1):
            if col == 6:
                value = serialize_details(value)
            ws.cell(row=row_number, column=col, value=value)

    max_row = len(table_rows) + start_row
    if table_rows:
        apply_zebra_stripes(ws, start_row + 1, max_row, len(WRITEBACK_AUDIT_HEADERS))
        add_table(ws, "tblWritebackAudit", len(WRITEBACK_AUDIT_HEADERS), max_row, start_row=start_row)
    else:
        ws.merge_cells(start_row=start_row + 1, start_column=1, end_row=start_row + 2, end_column=6)
        ws.cell(row=start_row + 1, column=1, value=empty_message).alignment = wrap_alignment
        ws.cell(row=start_row + 1, column=1).font = subtitle_font
    return max_row


def build_writeback_audit_sheet(
    wb,
    data: dict[str, Any],
    *,
    get_or_create_sheet,
    configure_sheet_view,
    set_sheet_header,
    build_writeback_audit_content_fn,
    write_key_value_block,
    action_sync_readiness_rows,
    action_sync_readiness_title: str,
    write_writeback_audit_table_fn,
    style_header_row,
    add_table,
    apply_zebra_stripes,
    wrap_alignment,
    subtitle_font,
    auto_width,
    serialize_details,
) -> None:
    ws = get_or_create_sheet(wb, "Writeback Audit")
    ws.sheet_properties.tabColor = "B91C1C"
    configure_sheet_view(ws, zoom=110, show_grid_lines=False)
    set_sheet_header(
        ws,
        "Writeback Audit",
        "This sheet summarizes writeback outcomes and rollback confidence without mutating anything by itself.",
        width=6,
    )
    content = build_writeback_audit_content_fn(
        data.get("writeback_results", {}).get("results", [])
    )
    write_key_value_block(
        ws,
        4,
        1,
        content["summary_rows"],
        title="Current Writeback State",
    )
    write_key_value_block(
        ws,
        4,
        5,
        action_sync_readiness_rows(data),
        title=action_sync_readiness_title,
    )
    start_row = 10
    max_row = write_writeback_audit_table_fn(
        ws,
        start_row=start_row,
        table_rows=content["table_rows"],
        empty_message=content["empty_message"],
        style_header_row=style_header_row,
        add_table=add_table,
        apply_zebra_stripes=apply_zebra_stripes,
        wrap_alignment=wrap_alignment,
        subtitle_font=subtitle_font,
        serialize_details=serialize_details,
    )
    auto_width(ws, len(WRITEBACK_AUDIT_HEADERS), max_row)


def write_governance_controls_table(
    ws,
    *,
    start_row: int,
    preview_rows: list[list[Any]],
    empty_message: str,
    style_header_row,
    style_data_cell,
    add_table,
    apply_zebra_stripes,
    wrap_alignment,
    subtitle_font,
) -> int:
    for col, header in enumerate(GOVERNANCE_CONTROLS_HEADERS, 1):
        ws.cell(row=start_row, column=col, value=header)
    style_header_row(ws, start_row, len(GOVERNANCE_CONTROLS_HEADERS))
    ws.freeze_panes = "A12"

    for row, values in enumerate(preview_rows, start_row + 1):
        for col, value in enumerate(values, 1):
            style_data_cell(
                ws.cell(row=row, column=col, value=value),
                "center" if col in {3, 4} else "left",
            )

    max_row = len(preview_rows) + start_row
    if preview_rows:
        apply_zebra_stripes(ws, start_row + 1, max_row, len(GOVERNANCE_CONTROLS_HEADERS))
        add_table(
            ws,
            "tblGovernanceControls",
            len(GOVERNANCE_CONTROLS_HEADERS),
            max_row,
            start_row=start_row,
        )
    else:
        ws.merge_cells(start_row=start_row + 1, start_column=1, end_row=start_row + 2, end_column=7)
        ws.cell(row=start_row + 1, column=1, value=empty_message).alignment = wrap_alignment
        ws.cell(row=start_row + 1, column=1).font = subtitle_font
    return max_row


def build_governance_controls_sheet(
    wb,
    data: dict[str, Any],
    *,
    get_or_create_sheet,
    configure_sheet_view,
    set_sheet_header,
    build_governance_controls_content_fn,
    display_operator_state,
    approval_workflow_label: str,
    next_approval_review_label: str,
    write_key_value_block,
    write_governance_controls_table_fn,
    style_header_row,
    style_data_cell,
    add_table,
    apply_zebra_stripes,
    wrap_alignment,
    subtitle_font,
    auto_width,
) -> None:
    ws = get_or_create_sheet(wb, "Governance Controls")
    ws.sheet_properties.tabColor = "7C3AED"
    configure_sheet_view(ws, zoom=115, show_grid_lines=False)
    set_sheet_header(
        ws,
        "Governance Controls",
        "This sheet shows the current governed control family only: readiness, drift, re-approval need, and rollback visibility.",
        width=7,
    )
    content = build_governance_controls_content_fn(
        data,
        display_operator_state=display_operator_state,
        approval_workflow_label=approval_workflow_label,
        next_approval_review_label=next_approval_review_label,
    )
    write_key_value_block(
        ws,
        4,
        1,
        content["summary_rows"],
        title="Governance Snapshot",
    )
    start_row = 11
    max_row = write_governance_controls_table_fn(
        ws,
        start_row=start_row,
        preview_rows=content["table_rows"],
        empty_message=content["empty_message"],
        style_header_row=style_header_row,
        style_data_cell=style_data_cell,
        add_table=add_table,
        apply_zebra_stripes=apply_zebra_stripes,
        wrap_alignment=wrap_alignment,
        subtitle_font=subtitle_font,
    )
    auto_width(ws, len(GOVERNANCE_CONTROLS_HEADERS), max_row)
