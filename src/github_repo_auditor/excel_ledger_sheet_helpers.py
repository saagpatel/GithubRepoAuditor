"""Helpers for ledger-style workbook sheets."""

from __future__ import annotations

from typing import Any

APPROVAL_LEDGER_HEADERS = [
    "Label",
    "State",
    "Follow-Up",
    "Subject",
    "Reviewer",
    "Approved At",
    "Next Follow-Up Due",
    "Summary",
]
HISTORICAL_INTELLIGENCE_HEADERS = [
    "Repo",
    "Status",
    "Pressure Trend",
    "Hotspot Persistence",
    "Scorecard Trend",
    "Summary",
]
REVIEW_HISTORY_HEADERS = [
    "Review ID",
    "Generated",
    "Changes",
    "Status",
    "Decision State",
    "Sync State",
    "Emitted",
]
GOVERNANCE_AUDIT_HEADERS = ["Control", "Value"]


def build_approval_ledger_content(
    data: dict[str, Any],
    *,
    approval_ledger_label: str,
    approved_but_manual_label: str,
) -> dict[str, Any]:
    sections = [
        ("Needs Re-Approval", data.get("top_needs_reapproval_approvals", []) or []),
        ("Overdue Follow-Up", data.get("top_overdue_approval_followups", []) or []),
        ("Ready For Review", data.get("top_ready_for_review_approvals", []) or []),
        ("Due Soon Follow-Up", data.get("top_due_soon_approval_followups", []) or []),
        (approved_but_manual_label, data.get("top_approved_manual_approvals", []) or []),
        ("Blocked", data.get("top_blocked_approvals", []) or []),
    ]
    section_rows: list[tuple[str, list[list[Any]]]] = []
    for label, items in sections:
        rows = [
            [
                item.get("label", item.get("subject_key", "Approval")),
                item.get("approval_state", "not-applicable"),
                item.get("follow_up_state", "not-applicable"),
                item.get("approval_subject_type", ""),
                item.get("last_reviewed_by", item.get("approved_by", "")),
                item.get("approved_at", ""),
                item.get("next_follow_up_due_at", ""),
                item.get("summary", ""),
            ]
            for item in items[:8]
        ]
        section_rows.append((label, rows))
    return {
        "title": approval_ledger_label,
        "summary": (data.get("approval_workflow_summary") or {}).get(
            "summary",
            "No current approval needs review yet, so the approval workflow can stay local for now.",
        ),
        "next_review": (data.get("next_approval_review") or {}).get(
            "summary",
            "Stay local for now; no current approval needs review.",
        ),
        "sections": section_rows,
    }


def build_historical_intelligence_content(data: dict[str, Any]) -> dict[str, Any]:
    sections = [
        ("Relapsing", data.get("top_relapsing_repos", []) or []),
        ("Persistent Pressure", data.get("top_persistent_pressure_repos", []) or []),
        ("Improving After Intervention", data.get("top_improving_repos", []) or []),
        ("Holding Steady", data.get("top_holding_repos", []) or []),
    ]
    section_rows: list[tuple[str, list[list[Any]], str]] = []
    for label, items in sections:
        rows = [
            [
                item.get("repo", ""),
                item.get("historical_intelligence_status", "insufficient-evidence"),
                item.get("pressure_trend", "insufficient-evidence"),
                item.get("hotspot_persistence", "insufficient-evidence"),
                item.get("scorecard_trend", "insufficient-evidence"),
                item.get("summary", ""),
            ]
            for item in items[:5]
        ]
        section_rows.append(
            (label, rows, f"No repos currently show a {label.lower()} story.")
        )
    return {
        "title": "Historical Intelligence",
        "summary": (data.get("intervention_ledger_summary") or {}).get(
            "summary",
            "Historical portfolio intelligence is still thin, so the weekly story should stay grounded in the current run and recent operator queue.",
        ),
        "next_focus": (data.get("next_historical_focus") or {}).get(
            "summary",
            "Stay local for now; no repo has enough cross-run intervention evidence to demand a historical follow-up read yet.",
        ),
        "sections": section_rows,
    }


def write_approval_ledger_sections(
    ws,
    content: dict[str, Any],
    *,
    start_row: int,
    subtitle_font,
    style_header_row,
    style_data_cell,
) -> int:
    for col, header in enumerate(APPROVAL_LEDGER_HEADERS, 1):
        ws.cell(row=start_row, column=col, value=header)
    style_header_row(ws, start_row, len(APPROVAL_LEDGER_HEADERS))
    ws.freeze_panes = "A6"

    row = start_row + 1
    for label, items in content["sections"]:
        ws.cell(row=row, column=1, value=label)
        ws.cell(row=row, column=1).font = subtitle_font
        row += 1
        if not items:
            ws.cell(row=row, column=1, value="None")
            row += 1
            continue
        for values in items:
            for col, value in enumerate(values, 1):
                cell = ws.cell(row=row, column=col, value=value)
                style_data_cell(cell, "center" if col in {2, 3, 4, 5, 6, 7} else "left")
            row += 1
    return row


def build_approval_ledger_sheet(
    wb,
    data: dict[str, Any],
    *,
    approval_ledger_label: str,
    approved_but_manual_label: str,
    get_or_create_sheet,
    configure_sheet_view,
    auto_width,
    section_font,
    subtitle_font,
    wrap_alignment,
    build_approval_ledger_content_fn,
    write_approval_ledger_sections_fn,
    style_header_row,
    style_data_cell,
) -> None:
    ws = get_or_create_sheet(wb, "Approval Ledger")
    ws.sheet_properties.tabColor = "6D28D9"
    configure_sheet_view(ws, zoom=105, show_grid_lines=True)

    content = build_approval_ledger_content_fn(
        data,
        approval_ledger_label=approval_ledger_label,
        approved_but_manual_label=approved_but_manual_label,
    )

    ws.merge_cells("A1:H1")
    ws["A1"].value = content["title"]
    ws["A1"].font = section_font
    ws.merge_cells("A2:H2")
    ws["A2"].value = content["summary"]
    ws["A2"].alignment = wrap_alignment
    ws.merge_cells("A3:H3")
    ws["A3"].value = content["next_review"]
    ws["A3"].alignment = wrap_alignment

    row = write_approval_ledger_sections_fn(
        ws,
        content,
        start_row=5,
        subtitle_font=subtitle_font,
        style_header_row=style_header_row,
        style_data_cell=style_data_cell,
    )

    auto_width(ws, len(APPROVAL_LEDGER_HEADERS), row)


def write_historical_intelligence_sections(
    ws,
    content: dict[str, Any],
    *,
    start_row: int,
    subtitle_font,
    wrap_alignment,
    style_data_cell,
) -> int:
    row = start_row
    for label, items, empty_message in content["sections"]:
        ws.cell(row=row, column=1, value=label)
        ws.cell(row=row, column=1).font = subtitle_font
        row += 1
        if not items:
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
            ws.cell(row=row, column=1, value=empty_message)
            ws.cell(row=row, column=1).alignment = wrap_alignment
            row += 2
            continue
        for values in items:
            for col, value in enumerate(values, 1):
                cell = ws.cell(row=row, column=col, value=value)
                style_data_cell(cell, "center" if col in {2, 3, 4, 5} else "left")
            row += 1
        row += 1
    return row


def write_historical_intelligence_sheet(
    ws,
    content: dict[str, Any],
    *,
    title: str,
    section_font,
    subtitle_font,
    wrap_alignment,
    style_header_row,
    style_data_cell,
) -> int:
    ws.merge_cells("A1:F1")
    ws["A1"].value = title
    ws["A1"].font = section_font
    ws.merge_cells("A2:F2")
    ws["A2"].value = content["summary"]
    ws["A2"].alignment = wrap_alignment
    ws.merge_cells("A3:F3")
    ws["A3"].value = content["next_focus"]
    ws["A3"].alignment = wrap_alignment

    for col, header in enumerate(HISTORICAL_INTELLIGENCE_HEADERS, 1):
        ws.cell(row=5, column=col, value=header)
    style_header_row(ws, 5, len(HISTORICAL_INTELLIGENCE_HEADERS))
    ws.freeze_panes = "A6"

    return write_historical_intelligence_sections(
        ws,
        content,
        start_row=6,
        subtitle_font=subtitle_font,
        wrap_alignment=wrap_alignment,
        style_data_cell=style_data_cell,
    )


def build_governance_audit_sheet(
    wb,
    data: dict[str, Any],
    *,
    display_operator_state,
    get_or_create_sheet,
    configure_sheet_view,
    set_sheet_header,
    build_governance_audit_rows_fn,
    write_governance_audit_table_fn,
    style_header_row,
    style_data_cell,
    apply_zebra_stripes,
    add_table,
    auto_width,
) -> None:
    ws = get_or_create_sheet(wb, "Governance Audit")
    ws.sheet_properties.tabColor = "6D28D9"
    configure_sheet_view(ws, zoom=110, show_grid_lines=False)
    set_sheet_header(
        ws,
        "Governance Audit",
        "Evidence summary for approval age, fingerprint drift, rollback coverage, and applied results.",
        width=3,
    )
    start_row = 4
    rows = build_governance_audit_rows_fn(
        data,
        display_operator_state=display_operator_state,
    )
    max_row = write_governance_audit_table_fn(
        ws,
        rows,
        start_row=start_row,
        style_header_row=style_header_row,
        style_data_cell=style_data_cell,
        apply_zebra_stripes=apply_zebra_stripes,
        add_table=add_table,
    )
    auto_width(ws, len(GOVERNANCE_AUDIT_HEADERS), max_row)


def build_review_history_rows(review_history: list[dict[str, Any]]) -> list[list[Any]]:
    return [
        [
            item.get("review_id", ""),
            item.get("generated_at", ""),
            item.get("material_change_count", 0),
            item.get("status", ""),
            item.get("decision_state", ""),
            item.get("sync_state", ""),
            "yes" if item.get("emitted") else "no",
        ]
        for item in review_history
    ]


def write_review_history_table(
    ws,
    history_rows: list[list[Any]],
    *,
    start_row: int,
    style_header_row,
    style_data_cell,
    apply_zebra_stripes,
    add_table,
) -> int:
    for col, header in enumerate(REVIEW_HISTORY_HEADERS, 1):
        ws.cell(row=start_row, column=col, value=header)
    style_header_row(ws, start_row, len(REVIEW_HISTORY_HEADERS))
    ws.freeze_panes = "A10"

    for row, values in enumerate(history_rows, start_row + 1):
        for col, value in enumerate(values, 1):
            style_data_cell(
                ws.cell(row=row, column=col, value=value),
                "center" if col not in {1, 2, 4, 5, 6} else "left",
            )

    max_row = len(history_rows) + start_row
    if history_rows:
        apply_zebra_stripes(ws, start_row + 1, max_row, len(REVIEW_HISTORY_HEADERS))
        add_table(ws, "tblReviewHistory", len(REVIEW_HISTORY_HEADERS), max_row, start_row=start_row)
    return max_row


def build_review_history_sheet(
    wb,
    data: dict[str, Any],
    *,
    get_or_create_sheet,
    configure_sheet_view,
    set_sheet_header,
    write_key_value_block,
    build_review_history_rows_fn,
    write_review_history_table_fn,
    style_header_row,
    style_data_cell,
    apply_zebra_stripes,
    add_table,
    auto_width,
) -> None:
    ws = get_or_create_sheet(wb, "Review History")
    ws.sheet_properties.tabColor = "1D4ED8"
    configure_sheet_view(ws, zoom=110, show_grid_lines=False)
    set_sheet_header(
        ws,
        "Review History",
        "Use this ledger to see which recurring review is active now and how prior review runs were resolved, deferred, or left local-only.",
        width=7,
    )
    active_review = data.get("review_summary") or {}
    write_key_value_block(
        ws,
        4,
        1,
        [
            ("Current Review", active_review.get("review_id", "—")),
            ("Current Status", active_review.get("status", "unknown")),
            ("History Rows", len(data.get("review_history", []) or [])),
            (
                "How To Read This",
                "The active review is summarized above; the ledger below is the historical trail.",
            ),
        ],
        title="Current State",
    )
    start_row = 9
    history_rows = build_review_history_rows_fn(data.get("review_history", []) or [])
    max_row = write_review_history_table_fn(
        ws,
        history_rows,
        start_row=start_row,
        style_header_row=style_header_row,
        style_data_cell=style_data_cell,
        apply_zebra_stripes=apply_zebra_stripes,
        add_table=add_table,
    )
    auto_width(ws, len(REVIEW_HISTORY_HEADERS), max_row)


def build_governance_audit_rows(
    data: dict[str, Any],
    *,
    display_operator_state,
) -> list[list[Any]]:
    governance_summary = data.get("governance_summary", {}) or {}
    preview_count = governance_summary.get("applyable_count")
    if preview_count is None:
        preview_count = len(data.get("security_governance_preview", []) or [])
    return [
        ["Status", display_operator_state(governance_summary.get("status", "preview"))],
        ["Headline", governance_summary.get("headline", "Governance state is being tracked.")],
        [
            "Approval Status",
            display_operator_state(governance_summary.get("approval_status", "preview-only")),
        ],
        ["Needs Re-Approval", "yes" if governance_summary.get("needs_reapproval") else "no"],
        ["Approval Age (days)", governance_summary.get("approval_age_days", "—")],
        ["Fingerprint Mismatch", "yes" if governance_summary.get("fingerprint_mismatch") else "no"],
        ["Applyable Count", preview_count],
        [
            "Drift Count",
            governance_summary.get("drift_count", len(data.get("governance_drift", []) or [])),
        ],
        [
            "Applied Count",
            governance_summary.get(
                "applied_count", len(data.get("governance_results", {}).get("results", []) or [])
            ),
        ],
        ["Rollback Available", governance_summary.get("rollback_available_count", 0)],
        ["Selected View", data.get("governance_preview", {}).get("selected_view", "all")],
    ]


def write_governance_audit_table(
    ws,
    rows: list[list[Any]],
    *,
    start_row: int,
    style_header_row,
    style_data_cell,
    apply_zebra_stripes,
    add_table,
) -> int:
    for col, header in enumerate(GOVERNANCE_AUDIT_HEADERS, 1):
        ws.cell(row=start_row, column=col, value=header)
    style_header_row(ws, start_row, len(GOVERNANCE_AUDIT_HEADERS))
    ws.freeze_panes = "A5"

    for row_index, values in enumerate(rows, start_row + 1):
        for col_index, value in enumerate(values, 1):
            style_data_cell(
                ws.cell(row=row_index, column=col_index, value=value),
                "center" if col_index == 2 else "left",
            )

    max_row = len(rows) + start_row
    if rows:
        apply_zebra_stripes(ws, start_row + 1, max_row, len(GOVERNANCE_AUDIT_HEADERS))
        add_table(
            ws,
            "tblGovernanceAudit",
            len(GOVERNANCE_AUDIT_HEADERS),
            max_row,
            start_row=start_row,
        )
    return max_row
