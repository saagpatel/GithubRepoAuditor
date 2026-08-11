"""Helpers for Print Pack workbook layout content."""

from __future__ import annotations

from typing import Any


def build_print_pack_summary_rows(
    *,
    data: dict[str, Any],
    weekly_pack: dict[str, Any],
    weekly_story: dict[str, Any],
    operator_summary: dict[str, Any],
    counts: dict[str, Any],
    operator_context: dict[str, Any],
    excel_mode: str,
    build_run_change_summary,
    build_queue_pressure_summary,
    build_top_recommendation_summary,
    build_trust_actionability_summary,
    diff_data: dict[str, Any] | None,
) -> tuple[list[tuple[str, Any]], int, int]:
    next_action = operator_context["next_action"]
    what_changed = operator_context["what_changed"]
    why_it_matters = operator_context["why_it_matters"]
    follow_through_checkpoint = operator_context["follow_through_checkpoint"]
    operator_focus = operator_context["operator_focus"]
    operator_focus_summary = operator_context["operator_focus_summary"]
    operator_focus_line = operator_context["operator_focus_line"]
    rows: list[tuple[str, Any]] = [
        ("Portfolio Grade", data.get("portfolio_grade", "F")),
        ("Average Score", round(data.get("average_score", 0.0), 3)),
        (
            "Portfolio Headline",
            weekly_pack.get(
                "portfolio_headline",
                operator_summary.get(
                    "headline", "Review the latest workbook surfaces for change and drift."
                ),
            ),
        ),
        (
            "Queue Pressure",
            weekly_pack.get(
                "queue_pressure_summary",
                (
                    f"{counts.get('blocked', 0)} blocked, {counts.get('urgent', 0)} need attention now, "
                    f"and {counts.get('ready', 0)} are ready for manual action."
                )
                if operator_summary
                else "",
            ),
        ),
        ("Run Changes", weekly_pack.get("run_change_summary", build_run_change_summary(diff_data))),
        (
            "What To Do This Week",
            weekly_story.get("decision", weekly_pack.get("what_to_do_this_week", next_action)),
        ),
        (
            "Trust / Actionability",
            weekly_pack.get(
                "trust_actionability_summary", build_trust_actionability_summary(data)
            ),
        ),
        ("Top Attention Items", len(weekly_pack.get("top_attention", []))),
        (
            "What Changed",
            what_changed or weekly_pack.get("run_change_summary", build_run_change_summary(diff_data)),
        ),
        (
            "Why It Matters",
            why_it_matters
            or weekly_story.get(
                "why_this_week",
                weekly_pack.get("queue_pressure_summary", build_queue_pressure_summary(data, diff_data)),
            ),
        ),
        (
            "Decision This Week",
            next_action
            or weekly_story.get(
                "decision",
                weekly_pack.get("what_to_do_this_week", build_top_recommendation_summary(data)),
            ),
        ),
        (
            "Follow-Through",
            f"{operator_focus_line} Next checkpoint: {follow_through_checkpoint}".strip(),
        ),
    ]
    top_attention_header_row = 17
    page2_row = 26
    if excel_mode == "standard":
        rows.extend(
            [
                ("Primary Target", operator_context["primary_target"]),
                ("Why Top Target", operator_context["primary_target_reason"]),
                ("Recovery / Retirement", operator_context["follow_through_recovery"]),
                (
                    "Recovery Persistence",
                    operator_context["follow_through_recovery_persistence"],
                ),
                ("Relapse Churn", operator_context["follow_through_relapse_churn"]),
                (
                    "Recovery Freshness",
                    operator_context["follow_through_recovery_freshness"],
                ),
                (
                    "Recovery Memory Reset",
                    operator_context["follow_through_recovery_memory_reset"],
                ),
                (
                    "Recovery Rebuild Strength",
                    operator_context["follow_through_rebuild_strength"],
                ),
                ("Recovery Reacquisition", operator_context["follow_through_reacquisition"]),
                (
                    "Reacquisition Durability",
                    operator_context["follow_through_reacquisition_durability"],
                ),
                (
                    "Reacquisition Confidence",
                    operator_context["follow_through_reacquisition_confidence"],
                ),
                ("Operator Focus", operator_focus),
                ("Focus Summary", operator_focus_summary),
                ("Focus Line", operator_focus_line),
                ("What We Tried", operator_context["last_intervention"]),
                ("Last Outcome", operator_context["last_outcome"]),
                ("Resolution Evidence", operator_context["resolution_evidence"]),
                ("Recovery Counts", operator_context["recovery_counts"]),
                ("Recommendation Confidence", operator_context["primary_confidence"]),
                ("Confidence Rationale", operator_context["confidence_reason"]),
                ("Next Action Confidence", operator_context["next_action_confidence"]),
                ("Trust Policy", operator_context["trust_policy"]),
                ("Trust Rationale", operator_context["trust_policy_reason"]),
                (
                    "Trust Exception",
                    f"{operator_context['exception_status']} — {operator_context['exception_reason']}",
                ),
                (
                    "Trust Recovery",
                    f"{operator_context['trust_recovery_status']} — {operator_context['trust_recovery_reason']}",
                ),
                ("Recovery Confidence", operator_context["recovery_confidence"]),
                (
                    "Exception Retirement",
                    f"{operator_context['retirement_status']} — {operator_context['retirement_reason']}",
                ),
                ("Retirement Summary", operator_context["retirement_summary"]),
                (
                    "Policy Debt",
                    f"{operator_context['policy_debt_status']} — {operator_context['policy_debt_reason']}",
                ),
                (
                    "Class Normalization",
                    f"{operator_context['class_normalization_status']} — {operator_context['trust_normalization_summary']}",
                ),
                (
                    "Class Memory",
                    f"{operator_context['class_memory_status']} — {operator_context['class_memory_reason']}",
                ),
                (
                    "Trust Decay",
                    f"{operator_context['class_decay_status']} — {operator_context['class_decay_summary']}",
                ),
                (
                    "Class Reweighting",
                    f"{operator_context['class_reweight_direction']} ({operator_context['class_reweight_score']}) — {operator_context['class_reweight_summary']}",
                ),
                ("Class Reweighting Why", operator_context["class_reweight_reason"]),
                ("Class Momentum", operator_context["class_momentum_status"]),
                ("Reweight Stability", operator_context["class_reweight_stability"]),
                ("Transition Health", operator_context["class_transition_health"]),
                ("Transition Resolution", operator_context["class_transition_resolution"]),
                ("Transition Summary", operator_context["class_transition_summary"]),
                ("Transition Closure", operator_context["transition_closure_confidence"]),
                (
                    "Transition Likely Outcome",
                    operator_context["transition_likely_outcome"],
                ),
                ("Pending Debt Freshness", operator_context["pending_debt_freshness"]),
                ("Closure Forecast", operator_context["closure_forecast_direction"]),
                (
                    "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Persistence",
                    operator_context[
                        "reset_reentry_rebuild_reentry_restore_rerererestore_persistence"
                    ],
                ),
                (
                    "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Churn Controls",
                    operator_context[
                        "reset_reentry_rebuild_reentry_restore_rerererestore_churn"
                    ],
                ),
                ("Closure Forecast Summary", operator_context["transition_closure_summary"]),
                ("Momentum Summary", operator_context["class_momentum_summary"]),
                (
                    "Exception Learning",
                    f"{operator_context['exception_pattern_status']} — {operator_context['exception_pattern_summary']}",
                ),
                (
                    "Recommendation Drift",
                    f"{operator_context['drift_status']} — {operator_context['drift_summary']}",
                ),
                ("Adaptive Confidence", operator_context["adaptive_confidence_summary"]),
                ("Recommendation Quality", operator_context["recommendation_quality"]),
                (
                    "Confidence Validation",
                    f"{operator_context['calibration_status']} — {operator_context['calibration_summary']}",
                ),
                (
                    "Calibration Snapshot",
                    f"High-confidence hit rate {operator_context['high_hit_rate']} | {operator_context['reopened_recommendations']}",
                ),
            ]
        )
        top_attention_header_row = 70
        page2_row = 76
    return rows, top_attention_header_row, page2_row


def build_print_pack_top_attention_rows(
    weekly_pack: dict[str, Any],
) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    for item in weekly_pack.get("top_attention", [])[:5]:
        rows.append(
            (
                item.get("repo", "Portfolio"),
                item.get("operator_focus", item.get("lane", "ready")),
                item.get("why_it_won", item.get("why", "Operator pressure is active.")),
                item.get("next_step", "Review the latest state."),
            )
        )
    return rows


def build_print_pack_drilldown_rows(weekly_pack: dict[str, Any]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for briefing in weekly_pack.get("repo_briefings", [])[:3]:
        rows.append(
            (
                briefing.get("repo", ""),
                briefing.get(
                    "next_step",
                    briefing.get(
                        "operator_focus_line",
                        "Watch Closely: No operator focus bucket is currently surfaced.",
                    ),
                ),
            )
        )
    return rows


def build_print_pack_page2_content(
    *,
    data: dict[str, Any],
    diff_data: dict[str, Any] | None,
    display_operator_state,
    summarize_top_issue_families,
) -> dict[str, Any]:
    governance_summary = data.get("governance_summary", {}) or {}
    preflight = data.get("preflight_summary") or {}
    return {
        "change_rows": [
            [label, count]
            for label, count in summarize_top_issue_families(
                data.get("material_changes", []) or [], limit=6
            )
        ],
        "governance_rows": [
            ("Status", display_operator_state(governance_summary.get("status", "preview"))),
            ("Needs Re-Approval", "yes" if governance_summary.get("needs_reapproval") else "no"),
            (
                "Drift Count",
                governance_summary.get("drift_count", len(data.get("governance_drift", []) or [])),
            ),
            ("Rollback Available", governance_summary.get("rollback_available_count", 0)),
        ],
        "compare_snapshot_rows": []
        if not diff_data
        else [
            ("Average Score Delta", diff_data.get("average_score_delta", 0.0)),
            ("Repo Changes", len(diff_data.get("repo_changes", []) or [])),
        ],
        "preflight_rows": []
        if not (preflight and (preflight.get("blocking_errors", 0) or preflight.get("warnings", 0)))
        else [
            ("Status", preflight.get("status", "unknown")),
            ("Errors", preflight.get("blocking_errors", 0)),
            ("Warnings", preflight.get("warnings", 0)),
        ],
    }


def build_print_pack_sheet_content(
    *,
    data: dict[str, Any],
    diff_data: dict[str, Any] | None,
    excel_mode: str,
    build_weekly_review_pack,
    build_executive_operator_context,
    print_pack_workflow_guidance_rows,
    build_run_change_summary,
    build_queue_pressure_summary,
    build_top_recommendation_summary,
    build_trust_actionability_summary,
    display_operator_state,
    summarize_top_issue_families,
) -> dict[str, Any]:
    operator_summary = data.get("operator_summary") or {}
    counts = operator_summary.get("counts", {})
    weekly_pack = build_weekly_review_pack(data, diff_data)
    weekly_story = weekly_pack.get("weekly_story_v1") or {}
    weekly_sections = {section.get("id"): section for section in weekly_story.get("sections") or []}
    operator_context = build_executive_operator_context(data, weekly_pack)
    summary_rows, top_attention_header_row, page2_row = build_print_pack_summary_rows(
        data=data,
        weekly_pack=weekly_pack,
        weekly_story=weekly_story,
        operator_summary=operator_summary,
        counts=counts,
        operator_context=operator_context,
        excel_mode=excel_mode,
        build_run_change_summary=build_run_change_summary,
        build_queue_pressure_summary=build_queue_pressure_summary,
        build_top_recommendation_summary=build_top_recommendation_summary,
        build_trust_actionability_summary=build_trust_actionability_summary,
        diff_data=diff_data,
    )
    page2_content = build_print_pack_page2_content(
        data=data,
        diff_data=diff_data,
        display_operator_state=display_operator_state,
        summarize_top_issue_families=summarize_top_issue_families,
    )
    max_print_row = page2_row + 12
    if page2_content["compare_snapshot_rows"]:
        max_print_row = max(max_print_row, page2_row + 10)
    if page2_content["preflight_rows"]:
        max_print_row = max(max_print_row, page2_row + 15)
    return {
        "workflow_rows": print_pack_workflow_guidance_rows(weekly_pack, weekly_sections),
        "summary_rows": summary_rows,
        "top_attention_header_row": top_attention_header_row,
        "top_attention_rows": build_print_pack_top_attention_rows(weekly_pack),
        "drilldown_rows": build_print_pack_drilldown_rows(weekly_pack),
        "page2_row": page2_row,
        "page2_content": page2_content,
        "max_print_row": max_print_row,
    }


def write_print_pack_sheet(
    ws,
    content: dict[str, Any],
    *,
    section_font,
    subheader_font,
) -> None:
    ws.freeze_panes = "A5"
    ws["A4"] = "Page 1: Leadership Brief"
    ws["A4"].font = section_font
    ws["D4"] = "Workflow Guidance"
    ws["D4"].font = section_font

    for row, (label, value) in enumerate(content["workflow_rows"], start=5):
        ws.cell(row=row, column=4, value=label)
        ws.cell(row=row, column=5, value=value)
    for offset, (label, value) in enumerate(content["summary_rows"], start=5):
        ws.cell(row=offset, column=1, value=label)
        ws.cell(row=offset, column=2, value=value)

    _write_print_pack_attention_section(
        ws,
        header_row=content["top_attention_header_row"],
        top_attention_rows=content["top_attention_rows"],
        drilldown_rows=content["drilldown_rows"],
        section_font=section_font,
    )
    _write_print_pack_page2(
        ws,
        page2_row=content["page2_row"],
        page2_content=content["page2_content"],
        section_font=section_font,
        subheader_font=subheader_font,
    )


def build_print_pack_sheet(
    wb,
    data: dict[str, Any],
    diff_data: dict[str, Any] | None,
    *,
    portfolio_profile: str = "default",
    collection: str | None = None,
    excel_mode: str = "standard",
    get_or_create_sheet,
    configure_sheet_view,
    set_sheet_header,
    build_print_pack_sheet_content_fn,
    write_print_pack_sheet_fn,
    build_weekly_review_pack,
    build_executive_operator_context,
    print_pack_workflow_guidance_rows,
    build_run_change_summary,
    build_queue_pressure_summary,
    build_top_recommendation_summary,
    build_trust_actionability_summary,
    display_operator_state,
    summarize_top_issue_families,
    section_font,
    subheader_font,
    auto_width,
) -> None:
    ws = get_or_create_sheet(wb, "Print Pack")
    ws.sheet_properties.tabColor = "CA8A04"
    configure_sheet_view(ws, zoom=125, show_grid_lines=False)
    set_sheet_header(
        ws,
        "Print Pack",
        f"Profile: {portfolio_profile} | Collection: {collection or 'all'}",
        width=6,
    )
    content = build_print_pack_sheet_content_fn(
        data=data,
        diff_data=diff_data,
        excel_mode=excel_mode,
        build_weekly_review_pack=build_weekly_review_pack,
        build_executive_operator_context=build_executive_operator_context,
        print_pack_workflow_guidance_rows=print_pack_workflow_guidance_rows,
        build_run_change_summary=build_run_change_summary,
        build_queue_pressure_summary=build_queue_pressure_summary,
        build_top_recommendation_summary=build_top_recommendation_summary,
        build_trust_actionability_summary=build_trust_actionability_summary,
        display_operator_state=display_operator_state,
        summarize_top_issue_families=summarize_top_issue_families,
    )
    write_print_pack_sheet_fn(
        ws,
        content,
        section_font=section_font,
        subheader_font=subheader_font,
    )
    auto_width(ws, 6, content["max_print_row"])
    ws.page_setup.orientation = "landscape"
    ws.print_area = f"A1:F{content['max_print_row']}"
    ws.print_title_rows = "1:4"


def build_print_pack_workbook_sheet(
    wb,
    data: dict[str, Any],
    diff_data: dict[str, Any] | None,
    *,
    portfolio_profile: str = "default",
    collection: str | None = None,
    excel_mode: str = "standard",
    get_or_create_sheet,
    configure_sheet_view,
    set_sheet_header,
    build_print_pack_sheet_content_fn,
    write_print_pack_sheet_fn,
    build_weekly_review_pack,
    build_executive_operator_context,
    print_pack_workflow_guidance_rows,
    build_run_change_summary,
    build_queue_pressure_summary,
    build_top_recommendation_summary,
    build_trust_actionability_summary,
    display_operator_state,
    summarize_top_issue_families,
    section_font,
    subheader_font,
    auto_width,
) -> None:
    build_print_pack_sheet(
        wb,
        data,
        diff_data,
        portfolio_profile=portfolio_profile,
        collection=collection,
        excel_mode=excel_mode,
        get_or_create_sheet=get_or_create_sheet,
        configure_sheet_view=configure_sheet_view,
        set_sheet_header=set_sheet_header,
        build_print_pack_sheet_content_fn=build_print_pack_sheet_content_fn,
        write_print_pack_sheet_fn=write_print_pack_sheet_fn,
        build_weekly_review_pack=build_weekly_review_pack,
        build_executive_operator_context=build_executive_operator_context,
        print_pack_workflow_guidance_rows=print_pack_workflow_guidance_rows,
        build_run_change_summary=build_run_change_summary,
        build_queue_pressure_summary=build_queue_pressure_summary,
        build_top_recommendation_summary=build_top_recommendation_summary,
        build_trust_actionability_summary=build_trust_actionability_summary,
        display_operator_state=display_operator_state,
        summarize_top_issue_families=summarize_top_issue_families,
        section_font=section_font,
        subheader_font=subheader_font,
        auto_width=auto_width,
    )


def _write_print_pack_attention_section(
    ws,
    *,
    header_row: int,
    top_attention_rows: list[tuple[str, str, str, str]],
    drilldown_rows: list[tuple[str, str]],
    section_font,
) -> None:
    ws.cell(row=header_row, column=1, value="Top Attention").font = section_font
    for offset, (repo, focus, reason, next_step) in enumerate(top_attention_rows, 1):
        ws.cell(row=header_row + offset, column=1, value=repo)
        ws.cell(row=header_row + offset, column=2, value=focus)
        ws.cell(row=header_row + offset, column=3, value=reason)
        ws.cell(row=header_row + offset, column=4, value=next_step)

    ws.cell(row=header_row, column=5, value="Top Repo Drilldowns").font = section_font
    for offset, (repo, next_step) in enumerate(drilldown_rows, 1):
        ws.cell(row=header_row + offset, column=5, value=repo)
        ws.cell(row=header_row + offset, column=6, value=next_step)


def _write_print_pack_page2(
    ws,
    *,
    page2_row: int,
    page2_content: dict[str, Any],
    section_font,
    subheader_font,
) -> None:
    ws.cell(row=page2_row, column=1, value="Page 2: Changes and Governance").font = section_font
    ws.cell(row=page2_row + 1, column=1, value="Top Material Change Families").font = subheader_font
    for offset, (label, count) in enumerate(page2_content["change_rows"], 1):
        ws.cell(row=page2_row + 1 + offset, column=1, value=label)
        ws.cell(row=page2_row + 1 + offset, column=2, value=count)

    ws.cell(row=page2_row + 1, column=4, value="Governance Highlights").font = subheader_font
    for offset, (label, value) in enumerate(page2_content["governance_rows"], 1):
        ws.cell(row=page2_row + 1 + offset, column=4, value=label)
        ws.cell(row=page2_row + 1 + offset, column=5, value=value)

    if page2_content["compare_snapshot_rows"]:
        row = page2_row + 8
        ws.cell(row=row, column=1, value="Compare Snapshot").font = section_font
        for offset, (label, value) in enumerate(page2_content["compare_snapshot_rows"], 1):
            ws.cell(row=row + offset, column=1, value=label)
            ws.cell(row=row + offset, column=2, value=value)

    if page2_content["preflight_rows"]:
        row = page2_row + 12
        ws.cell(row=row, column=1, value="Preflight Diagnostics").font = section_font
        for offset, (label, value) in enumerate(page2_content["preflight_rows"], 1):
            ws.cell(row=row + offset, column=1, value=label)
            ws.cell(row=row + offset, column=2, value=value)
