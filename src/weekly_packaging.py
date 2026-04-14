from __future__ import annotations

from typing import Any

from src.terminology import ACTION_SYNC_CANONICAL_LABELS

NO_FOLLOW_THROUGH_CHECKPOINT = "Use the next run or linked artifact to confirm whether the recommendation moved."
NO_OPERATOR_FOCUS_SUMMARY = "No operator focus bucket is currently surfaced."
NO_WHERE_TO_START_SUMMARY = "No meaningful implementation hotspot is currently surfaced."
NO_OPERATOR_OUTCOMES_SUMMARY = (
    "Not enough operator history is recorded yet to judge whether recent actions are improving portfolio outcomes."
)
NO_ACTION_SYNC_SUMMARY = "No current campaign needs Action Sync yet, so the safest next move is to keep the story local."
NO_ACTION_SYNC_STEP = "Stay local for now; no current campaign needs preview or apply."
NO_ACTION_SYNC_LINE = (
    "Action Sync: stay local until a campaign has meaningful actions and healthy writeback prerequisites."
)
NO_APPLY_READINESS_SUMMARY = (
    "No current campaign has a safe execution handoff yet, so the local story should stay local for now."
)
NO_NEXT_APPLY_CANDIDATE = "Stay local for now; no current campaign has a safe execution handoff."
NO_CAMPAIGN_OUTCOMES_SUMMARY = (
    "No recent Action Sync apply needs post-apply monitoring yet, so the local weekly story can stay local."
)
NO_NEXT_MONITORING_STEP = "Stay local for now; no recent Action Sync apply needs post-apply follow-up yet."
NO_CAMPAIGN_TUNING_SUMMARY = (
    "Campaign tuning stays neutral until there is enough outcome history to bias tied recommendations."
)
NO_NEXT_TUNED_CAMPAIGN = "No current campaign needs a tie-break candidate yet."
NO_HISTORICAL_PORTFOLIO_INTELLIGENCE_SUMMARY = (
    "Historical portfolio intelligence is still thin, so the weekly story should stay grounded in the current run and recent operator queue."
)
NO_NEXT_HISTORICAL_FOCUS = (
    "Stay local for now; no repo has enough cross-run intervention evidence to demand a historical follow-up read yet."
)
NO_AUTOMATION_GUIDANCE_SUMMARY = (
    "Automation guidance stays quiet until a campaign has a clearly safe preview, follow-up, or manual-only posture."
)
NO_NEXT_SAFE_AUTOMATION_STEP = (
    "Stay local for now; no current campaign has a stronger safe automation posture than manual review."
)
NO_AUTOMATION_GUIDANCE_LINE = (
    "Automation Guidance: keep the next step human-led until a bounded safe posture is surfaced."
)
NO_APPROVAL_WORKFLOW_SUMMARY = "No current approval needs review yet, so the approval workflow can stay local for now."
NO_NEXT_APPROVAL_REVIEW = "Stay local for now; no current approval needs review."
NO_APPROVAL_WORKFLOW_LINE = "Approval Workflow: no current approval needs review yet."


def _first_command_hint(*values: Any) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text and not text.lower().startswith("no "):
            return text
    return None


def _safe_posture_for_command(command_hint: str | None, *, default: str = "read-only") -> str:
    if not command_hint:
        return default
    if "--writeback-apply" in command_hint:
        return "manual-mutation"
    if "--approve-" in command_hint:
        return "local-approval-capture"
    return "bounded-command"


def _build_story_evidence_item(
    label: str,
    summary: str,
    kind: str,
    *,
    safe_posture: str = "read-only",
    command_hint: str | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "label": label,
        "summary": str(summary),
        "kind": kind,
        "safe_posture": safe_posture,
    }
    if command_hint:
        item["command_hint"] = command_hint
    return item


def _build_attention_explainability(item: dict[str, Any]) -> dict[str, Any]:
    evidence_strip = [
        _build_story_evidence_item(
            "Operator Focus",
            item.get("operator_focus_line", NO_OPERATOR_FOCUS_SUMMARY),
            "operator-focus",
        ),
        _build_story_evidence_item(
            "Action Sync",
            item.get("action_sync_line", NO_ACTION_SYNC_LINE),
            "action-sync",
        ),
        _build_story_evidence_item(
            "Automation Guidance",
            item.get("automation_line", NO_AUTOMATION_GUIDANCE_LINE),
            "automation-guidance",
            safe_posture=_safe_posture_for_command(item.get("automation_command")),
            command_hint=_first_command_hint(item.get("automation_command")),
        ),
        _build_story_evidence_item(
            "Approval Workflow",
            item.get("approval_line", NO_APPROVAL_WORKFLOW_LINE),
            "approval-workflow",
        ),
        _build_story_evidence_item(
            "Checkpoint",
            item.get("follow_through_checkpoint", NO_FOLLOW_THROUGH_CHECKPOINT),
            "follow-through",
        ),
    ]
    return {
        **item,
        "why_it_won": str(item.get("why") or "Operator pressure is active."),
        "evidence_strip": evidence_strip,
    }


def _build_repo_briefing_explainability(briefing: dict[str, Any]) -> dict[str, Any]:
    evidence_strip = [
        _build_story_evidence_item(
            "Where To Start",
            briefing.get("where_to_start_summary", NO_WHERE_TO_START_SUMMARY),
            "implementation-hotspot",
        ),
        _build_story_evidence_item(
            "Operator Focus",
            briefing.get("operator_focus_line", NO_OPERATOR_FOCUS_SUMMARY),
            "operator-focus",
        ),
        _build_story_evidence_item(
            "Action Sync",
            briefing.get("action_sync_line", NO_ACTION_SYNC_LINE),
            "action-sync",
            safe_posture=_safe_posture_for_command(briefing.get("apply_packet_command")),
            command_hint=_first_command_hint(briefing.get("apply_packet_command")),
        ),
        _build_story_evidence_item(
            "Automation Guidance",
            briefing.get("automation_line", NO_AUTOMATION_GUIDANCE_LINE),
            "automation-guidance",
            safe_posture=_safe_posture_for_command(briefing.get("automation_command")),
            command_hint=_first_command_hint(briefing.get("automation_command")),
        ),
        _build_story_evidence_item(
            "Approval Workflow",
            briefing.get("approval_line", NO_APPROVAL_WORKFLOW_LINE),
            "approval-workflow",
        ),
    ]
    return {
        **briefing,
        "why_it_won": str(briefing.get("why_it_matters_line") or "No explanation summary is recorded yet."),
        "next_step": str(briefing.get("what_to_do_next_line") or "No next action is recorded yet."),
        "evidence_strip": evidence_strip,
    }


def _campaign_evidence_items(
    items: list[dict[str, Any]],
    *,
    summary_key: str,
    kind: str,
    label_key: str = "label",
    fallback_label_key: str = "campaign_type",
    label_prefix: str | None = None,
    command_keys: tuple[str, ...] = (),
    extra_formatter: Any | None = None,
) -> list[dict[str, Any]]:
    evidence_items: list[dict[str, Any]] = []
    for item in items[:3]:
        label = str(item.get(label_key) or item.get(fallback_label_key) or "Campaign")
        if label_prefix:
            label = f"{label_prefix}: {label}"
        summary = str(item.get(summary_key) or "No supporting summary is recorded yet.")
        if extra_formatter is not None:
            summary = extra_formatter(item, summary)
        command_hint = _first_command_hint(*(item.get(key) for key in command_keys))
        evidence_items.append(
            _build_story_evidence_item(
                label,
                summary,
                kind,
                safe_posture=_safe_posture_for_command(command_hint),
                command_hint=command_hint,
            )
        )
    return evidence_items


def _approval_evidence_items(items: list[dict[str, Any]], *, label_prefix: str | None = None) -> list[dict[str, Any]]:
    evidence_items: list[dict[str, Any]] = []
    for item in items[:3]:
        label = str(item.get("label") or item.get("subject_key") or "Approval")
        if label_prefix:
            label = f"{label_prefix}: {label}"
        summary = str(item.get("summary") or "No approval summary is recorded yet.")
        command_hint = _first_command_hint(item.get("approval_command"), item.get("manual_apply_command"))
        evidence_items.append(
            _build_story_evidence_item(
                label,
                summary,
                "approval-workflow",
                safe_posture=_safe_posture_for_command(command_hint, default="approval-review"),
                command_hint=command_hint,
            )
        )
    return evidence_items


def _repo_evidence_items(items: list[dict[str, Any]], *, label_prefix: str | None = None) -> list[dict[str, Any]]:
    return [
        _build_story_evidence_item(
            f"{label_prefix}: {item.get('repo') or 'Repo'}" if label_prefix else str(item.get("repo") or "Repo"),
            str(item.get("summary") or "No historical intelligence summary is recorded yet."),
            "historical-portfolio-intelligence",
        )
        for item in items[:3]
    ]


def _determine_section_state(weekly_pack: dict[str, Any], options: list[tuple[str, str]]) -> str:
    for key, state in options:
        if weekly_pack.get(key):
            return state
    return "idle"


def _build_weekly_story_v1(weekly_pack: dict[str, Any]) -> dict[str, Any]:
    sections = [
        {
            "id": "weekly-priority",
            "label": "Weekly Priority",
            "state": "active",
            "headline": str(weekly_pack.get("queue_pressure_summary") or "No queue-pressure summary is recorded yet."),
            "next_step": str(weekly_pack.get("what_to_do_this_week") or "Continue the normal operator review loop."),
            "next_label": "Decision",
            "reason_codes": ["queue-pressure", "operator-priority"],
            "evidence_items": [
                _build_story_evidence_item(
                    "Trust / Actionability",
                    str(weekly_pack.get("trust_actionability_summary") or "No trust summary is recorded yet."),
                    "weekly-priority",
                ),
                _build_story_evidence_item(
                    "Operator Focus",
                    str(weekly_pack.get("operator_focus_summary") or NO_OPERATOR_FOCUS_SUMMARY),
                    "operator-focus",
                ),
                _build_story_evidence_item(
                    "Operator Outcomes",
                    str(weekly_pack.get("operator_outcomes_summary") or NO_OPERATOR_OUTCOMES_SUMMARY),
                    "operator-outcomes",
                ),
            ],
        },
        {
            "id": "action-sync-readiness",
            "label": ACTION_SYNC_CANONICAL_LABELS["readiness"],
            "state": _determine_section_state(
                weekly_pack,
                [
                    ("top_blocked_campaigns", "blocked"),
                    ("top_drift_review_campaigns", "drift-review"),
                    ("top_apply_ready_campaigns", "apply-ready"),
                    ("top_preview_ready_campaigns", "preview-ready"),
                ],
            ),
            "headline": str(weekly_pack.get("action_sync_summary") or NO_ACTION_SYNC_SUMMARY),
            "next_step": str(weekly_pack.get("next_action_sync_step") or NO_ACTION_SYNC_STEP),
            "next_label": "Next Step",
            "reason_codes": ["action-sync", "readiness"],
            "evidence_items": (
                _campaign_evidence_items(
                    list(weekly_pack.get("top_apply_ready_campaigns") or []),
                    summary_key="reason",
                    kind="action-sync-readiness",
                    label_prefix="Apply Ready",
                    extra_formatter=lambda item, summary: f"{summary} (target {item.get('recommended_target', 'none')})",
                )
                + _campaign_evidence_items(
                    list(weekly_pack.get("top_preview_ready_campaigns") or []),
                    summary_key="reason",
                    kind="action-sync-readiness",
                    label_prefix="Preview Ready",
                    extra_formatter=lambda item, summary: f"{summary} (target {item.get('recommended_target', 'none')})",
                )
                + _campaign_evidence_items(
                    list(weekly_pack.get("top_drift_review_campaigns") or []),
                    summary_key="reason",
                    kind="action-sync-readiness",
                    label_prefix="Drift Review",
                )
                + _campaign_evidence_items(
                    list(weekly_pack.get("top_blocked_campaigns") or []),
                    summary_key="reason",
                    kind="action-sync-readiness",
                    label_prefix="Blocked",
                )
            ),
        },
        {
            "id": "apply-packet",
            "label": ACTION_SYNC_CANONICAL_LABELS["apply_packet"],
            "state": _determine_section_state(
                weekly_pack,
                [
                    ("top_review_drift_packets", "review-drift"),
                    ("top_needs_approval_packets", "needs-approval"),
                    ("top_ready_to_apply_packets", "ready-to-apply"),
                ],
            ),
            "headline": str(weekly_pack.get("apply_readiness_summary") or NO_APPLY_READINESS_SUMMARY),
            "next_step": str(weekly_pack.get("next_apply_candidate") or NO_NEXT_APPLY_CANDIDATE),
            "next_label": "Next Candidate",
            "reason_codes": ["action-sync", "apply-packet"],
            "evidence_items": (
                _campaign_evidence_items(
                    list(weekly_pack.get("top_ready_to_apply_packets") or []),
                    summary_key="summary",
                    kind="apply-packet",
                    label_prefix="Ready To Apply",
                    command_keys=("apply_command", "preview_command"),
                )
                + _campaign_evidence_items(
                    list(weekly_pack.get("top_needs_approval_packets") or []),
                    summary_key="summary",
                    kind="apply-packet",
                    label_prefix="Needs Approval",
                    command_keys=("apply_command", "preview_command"),
                )
                + _campaign_evidence_items(
                    list(weekly_pack.get("top_review_drift_packets") or []),
                    summary_key="summary",
                    kind="apply-packet",
                    label_prefix="Review Drift",
                    command_keys=("apply_command", "preview_command"),
                )
            ),
        },
        {
            "id": "post-apply-monitoring",
            "label": ACTION_SYNC_CANONICAL_LABELS["post_apply_monitoring"],
            "state": _determine_section_state(
                weekly_pack,
                [
                    ("top_drift_returned_campaigns", "drift-returned"),
                    ("top_reopened_campaigns", "reopened"),
                    ("top_monitor_now_campaigns", "monitor-now"),
                    ("top_holding_clean_campaigns", "holding-clean"),
                ],
            ),
            "headline": str(weekly_pack.get("campaign_outcomes_summary") or NO_CAMPAIGN_OUTCOMES_SUMMARY),
            "next_step": str(weekly_pack.get("next_monitoring_step") or NO_NEXT_MONITORING_STEP),
            "next_label": "Next Step",
            "reason_codes": ["action-sync", "post-apply-monitoring"],
            "evidence_items": (
                _campaign_evidence_items(
                    list(weekly_pack.get("top_drift_returned_campaigns") or []),
                    summary_key="summary",
                    kind="post-apply-monitoring",
                )
                + _campaign_evidence_items(
                    list(weekly_pack.get("top_reopened_campaigns") or []),
                    summary_key="summary",
                    kind="post-apply-monitoring",
                    label_prefix="Reopened",
                )
                + _campaign_evidence_items(
                    list(weekly_pack.get("top_monitor_now_campaigns") or []),
                    summary_key="summary",
                    kind="post-apply-monitoring",
                    label_prefix="Monitor Now",
                )
                + _campaign_evidence_items(
                    list(weekly_pack.get("top_holding_clean_campaigns") or []),
                    summary_key="summary",
                    kind="post-apply-monitoring",
                    label_prefix="Holding Clean",
                )
            ),
        },
        {
            "id": "campaign-tuning",
            "label": ACTION_SYNC_CANONICAL_LABELS["campaign_tuning"],
            "state": _determine_section_state(
                weekly_pack,
                [
                    ("top_caution_campaigns", "caution"),
                    ("top_proven_campaigns", "proven"),
                    ("top_thin_evidence_campaigns", "thin-evidence"),
                ],
            ),
            "headline": str(weekly_pack.get("campaign_tuning_summary") or NO_CAMPAIGN_TUNING_SUMMARY),
            "next_step": str(
                weekly_pack.get("next_tie_break_candidate") or weekly_pack.get("next_tuned_campaign") or NO_NEXT_TUNED_CAMPAIGN
            ),
            "next_label": ACTION_SYNC_CANONICAL_LABELS["next_tie_break_candidate"],
            "reason_codes": ["action-sync", "campaign-tuning"],
            "evidence_items": (
                _campaign_evidence_items(
                    list(weekly_pack.get("top_proven_campaigns") or []),
                    summary_key="summary",
                    kind="campaign-tuning",
                    label_prefix="Proven",
                )
                + _campaign_evidence_items(
                    list(weekly_pack.get("top_caution_campaigns") or []),
                    summary_key="summary",
                    kind="campaign-tuning",
                    label_prefix="Caution",
                )
                + _campaign_evidence_items(
                    list(weekly_pack.get("top_thin_evidence_campaigns") or []),
                    summary_key="summary",
                    kind="campaign-tuning",
                    label_prefix="Thin Evidence",
                )
            ),
        },
        {
            "id": "historical-portfolio-intelligence",
            "label": ACTION_SYNC_CANONICAL_LABELS["historical_portfolio_intelligence"],
            "state": _determine_section_state(
                weekly_pack,
                [
                    ("top_relapsing_repos", "relapsing"),
                    ("top_persistent_pressure_repos", "persistent-pressure"),
                    ("top_improving_repos", "improving-after-intervention"),
                    ("top_holding_repos", "holding-steady"),
                ],
            ),
            "headline": str(weekly_pack.get("historical_portfolio_intelligence") or NO_HISTORICAL_PORTFOLIO_INTELLIGENCE_SUMMARY),
            "next_step": str(weekly_pack.get("next_historical_focus") or NO_NEXT_HISTORICAL_FOCUS),
            "next_label": "Next Focus",
            "reason_codes": ["historical-intelligence", "portfolio"],
            "evidence_items": (
                _repo_evidence_items(list(weekly_pack.get("top_relapsing_repos") or []), label_prefix="Relapsing")
                + _repo_evidence_items(
                    list(weekly_pack.get("top_persistent_pressure_repos") or []),
                    label_prefix="Persistent Pressure",
                )
                + _repo_evidence_items(
                    list(weekly_pack.get("top_improving_repos") or []),
                    label_prefix="Improving After Intervention",
                )
                + _repo_evidence_items(list(weekly_pack.get("top_holding_repos") or []), label_prefix="Holding Steady")
            ),
        },
        {
            "id": "automation-guidance",
            "label": ACTION_SYNC_CANONICAL_LABELS["automation_guidance"],
            "state": _determine_section_state(
                weekly_pack,
                [
                    ("top_approval_first_campaigns", "approval-first"),
                    ("top_apply_manual_campaigns", "apply-manual"),
                    ("top_preview_safe_campaigns", "preview-safe"),
                    ("top_follow_up_safe_campaigns", "follow-up-safe"),
                    ("top_manual_only_campaigns", "manual-only"),
                ],
            ),
            "headline": str(weekly_pack.get("automation_guidance_summary") or NO_AUTOMATION_GUIDANCE_SUMMARY),
            "next_step": str(weekly_pack.get("next_safe_automation_step") or NO_NEXT_SAFE_AUTOMATION_STEP),
            "next_label": "Next Step",
            "reason_codes": ["automation-guidance", "safe-posture"],
            "evidence_items": (
                _campaign_evidence_items(
                    list(weekly_pack.get("top_preview_safe_campaigns") or []),
                    summary_key="summary",
                    kind="automation-guidance",
                    label_prefix="Preview Safe",
                    command_keys=("recommended_command",),
                )
                + _campaign_evidence_items(
                    list(weekly_pack.get("top_apply_manual_campaigns") or []),
                    summary_key="summary",
                    kind="automation-guidance",
                    label_prefix="Apply Manual",
                    command_keys=("recommended_command",),
                )
                + _campaign_evidence_items(
                    list(weekly_pack.get("top_approval_first_campaigns") or []),
                    summary_key="summary",
                    kind="automation-guidance",
                    label_prefix="Approval First",
                    command_keys=("recommended_command",),
                )
                + _campaign_evidence_items(
                    list(weekly_pack.get("top_follow_up_safe_campaigns") or []),
                    summary_key="summary",
                    kind="automation-guidance",
                    label_prefix="Follow-Up Safe",
                    command_keys=("recommended_command",),
                )
                + _campaign_evidence_items(
                    list(weekly_pack.get("top_manual_only_campaigns") or []),
                    summary_key="summary",
                    kind="automation-guidance",
                    label_prefix="Manual Only",
                    command_keys=("recommended_command",),
                )
            ),
        },
        {
            "id": "approval-workflow",
            "label": ACTION_SYNC_CANONICAL_LABELS["approval_workflow"],
            "state": _determine_section_state(
                weekly_pack,
                [
                    ("top_needs_reapproval_approvals", "needs-reapproval"),
                    ("top_ready_for_review_approvals", "ready-for-review"),
                    ("top_approved_manual_approvals", "approved-manual"),
                    ("top_blocked_approvals", "blocked"),
                ],
            ),
            "headline": str(weekly_pack.get("approval_workflow_summary") or NO_APPROVAL_WORKFLOW_SUMMARY),
            "next_step": str(weekly_pack.get("next_approval_review") or NO_NEXT_APPROVAL_REVIEW),
            "next_label": ACTION_SYNC_CANONICAL_LABELS["next_approval_review"],
            "reason_codes": ["approval-workflow", "local-only"],
            "evidence_items": (
                _approval_evidence_items(
                    list(weekly_pack.get("top_needs_reapproval_approvals") or []),
                    label_prefix="Needs Re-Approval",
                )
                + _approval_evidence_items(
                    list(weekly_pack.get("top_ready_for_review_approvals") or []),
                    label_prefix="Ready For Review",
                )
                + _approval_evidence_items(
                    list(weekly_pack.get("top_approved_manual_approvals") or []),
                    label_prefix="Approved But Manual",
                )
                + _approval_evidence_items(list(weekly_pack.get("top_blocked_approvals") or []), label_prefix="Blocked")
            ),
        },
        {
            "id": "operator-focus",
            "label": "Operator Focus",
            "state": _determine_section_state(
                weekly_pack,
                [
                    ("top_act_now_items", "act-now"),
                    ("top_watch_closely_items", "watch-closely"),
                    ("top_improving_items", "improving"),
                    ("top_fragile_items", "fragile"),
                    ("top_revalidate_items", "revalidate"),
                ],
            ),
            "headline": str(weekly_pack.get("operator_focus_summary") or NO_OPERATOR_FOCUS_SUMMARY),
            "next_step": str(weekly_pack.get("follow_through_checkpoint_summary") or NO_FOLLOW_THROUGH_CHECKPOINT),
            "next_label": "Next Checkpoint",
            "reason_codes": ["operator-focus", "follow-through"],
            "evidence_items": (
                [
                    _build_story_evidence_item(
                        str(item.get("repo") or item.get("title") or "Operator item"),
                        str(item.get("operator_focus_summary") or NO_OPERATOR_FOCUS_SUMMARY),
                        "operator-focus",
                    )
                    for item in list(weekly_pack.get("top_act_now_items") or [])[:3]
                ]
                + [
                    _build_story_evidence_item(
                        str(item.get("repo") or item.get("title") or "Operator item"),
                        str(item.get("operator_focus_summary") or NO_OPERATOR_FOCUS_SUMMARY),
                        "operator-focus",
                    )
                    for item in list(weekly_pack.get("top_watch_closely_items") or [])[:3]
                ]
                + [
                    _build_story_evidence_item(
                        str(item.get("repo") or item.get("title") or "Operator item"),
                        str(item.get("operator_focus_summary") or NO_OPERATOR_FOCUS_SUMMARY),
                        "operator-focus",
                    )
                    for item in list(weekly_pack.get("top_improving_items") or [])[:3]
                ]
                + [
                    _build_story_evidence_item(
                        str(item.get("repo") or item.get("title") or "Operator item"),
                        str(item.get("operator_focus_summary") or NO_OPERATOR_FOCUS_SUMMARY),
                        "operator-focus",
                    )
                    for item in list(weekly_pack.get("top_fragile_items") or [])[:3]
                ]
                + [
                    _build_story_evidence_item(
                        str(item.get("repo") or item.get("title") or "Operator item"),
                        str(item.get("operator_focus_summary") or NO_OPERATOR_FOCUS_SUMMARY),
                        "operator-focus",
                    )
                    for item in list(weekly_pack.get("top_revalidate_items") or [])[:3]
                ]
            ),
        },
    ]

    return {
        "version": 1,
        "headline": str(weekly_pack.get("portfolio_headline") or "No weekly headline is recorded yet."),
        "decision": str(weekly_pack.get("what_to_do_this_week") or "Continue the normal operator review loop."),
        "why_this_week": str(weekly_pack.get("queue_pressure_summary") or "No queue-pressure summary is recorded yet."),
        "next_step": str(
            weekly_pack.get("next_best_workflow_step")
            or "Open the standard workbook first, then use --control-center for read-only triage."
        ),
        "section_order": [section["id"] for section in sections],
        "sections": sections,
    }


def finalize_weekly_pack(weekly_pack: dict[str, Any]) -> dict[str, Any]:
    finalized = dict(weekly_pack)
    finalized["top_attention"] = [
        _build_attention_explainability(item) for item in list(finalized.get("top_attention") or [])
    ]
    finalized["repo_briefings"] = [
        _build_repo_briefing_explainability(item) for item in list(finalized.get("repo_briefings") or [])
    ]
    finalized["weekly_story_v1"] = _build_weekly_story_v1(finalized)
    return finalized
