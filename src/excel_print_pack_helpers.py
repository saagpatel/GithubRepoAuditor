"""Helpers for print-pack workbook sections."""

from __future__ import annotations

from src.terminology import ACTION_SYNC_CANONICAL_LABELS


def print_pack_workflow_guidance_rows(
    weekly_pack: dict,
    weekly_sections: dict[str, dict],
) -> list[tuple[str, object]]:
    action_sync_section = weekly_sections.get("action-sync-readiness") or {}
    apply_packet_section = weekly_sections.get("apply-packet") or {}
    post_apply_section = weekly_sections.get("post-apply-monitoring") or {}
    tuning_section = weekly_sections.get("campaign-tuning") or {}
    historical_section = weekly_sections.get("historical-portfolio-intelligence") or {}
    automation_section = weekly_sections.get("automation-guidance") or {}
    approval_section = weekly_sections.get("approval-workflow") or {}

    return [
        (
            "Product Mode",
            weekly_pack.get(
                "product_mode_summary",
                "Weekly Review: use this artifact for the normal workbook-first operator loop.",
            ),
        ),
        (
            "Artifact Role",
            weekly_pack.get(
                "artifact_role_summary",
                "This artifact is the shared weekly handoff across workbook, HTML, Markdown, and review-pack.",
            ),
        ),
        (
            "Reading Order",
            weekly_pack.get(
                "suggested_reading_order",
                "Read Dashboard, then Run Changes, then Review Queue.",
            ),
        ),
        (
            "Next Best Step",
            weekly_pack.get(
                "next_best_workflow_step",
                "Open the standard workbook first, then use --control-center for read-only triage.",
            ),
        ),
        (
            ACTION_SYNC_CANONICAL_LABELS["readiness"],
            action_sync_section.get(
                "headline",
                weekly_pack.get(
                    "action_sync_summary",
                    "No current campaign needs Action Sync yet, so the safest next move is to keep the story local.",
                ),
            ),
        ),
        (
            "Next Action Sync Step",
            action_sync_section.get(
                "next_step",
                weekly_pack.get(
                    "next_action_sync_step",
                    "Stay local for now; no current campaign needs preview or apply.",
                ),
            ),
        ),
        (
            "Apply Packet",
            apply_packet_section.get(
                "headline",
                weekly_pack.get(
                    "apply_readiness_summary",
                    "No current campaign has a safe execution handoff yet, so the local story should stay local for now.",
                ),
            ),
        ),
        (
            "Command Hint",
            weekly_pack.get(
                "action_sync_command_hint",
                "No Action Sync command is recommended yet.",
            ),
        ),
        (
            ACTION_SYNC_CANONICAL_LABELS["post_apply_monitoring"],
            weekly_pack.get(
                "campaign_outcomes_summary",
                "No recent Action Sync apply needs post-apply monitoring yet, so the local weekly story can stay local.",
            ),
        ),
        (
            "Next Monitoring Step",
            post_apply_section.get(
                "next_step",
                weekly_pack.get(
                    "next_monitoring_step",
                    "Stay local for now; no recent Action Sync apply needs post-apply follow-up yet.",
                ),
            ),
        ),
        (
            ACTION_SYNC_CANONICAL_LABELS["campaign_tuning"],
            tuning_section.get(
                "headline",
                weekly_pack.get(
                    "campaign_tuning_summary",
                    "Campaign tuning is neutral because there is not enough outcome history yet to bias tied recommendations.",
                ),
            ),
        ),
        (
            ACTION_SYNC_CANONICAL_LABELS["next_tie_break_candidate"],
            tuning_section.get(
                "next_step",
                weekly_pack.get(
                    "next_tuned_campaign",
                    "No current campaign needs a tuning tie-break yet.",
                ),
            ),
        ),
        (
            ACTION_SYNC_CANONICAL_LABELS["historical_portfolio_intelligence"],
            historical_section.get(
                "headline",
                weekly_pack.get(
                    "historical_portfolio_intelligence",
                    "Historical portfolio intelligence is still thin, so the weekly story should stay grounded in the current run and recent operator queue.",
                ),
            ),
        ),
        (
            "Next Historical Focus",
            historical_section.get(
                "next_step",
                weekly_pack.get(
                    "next_historical_focus",
                    "Stay local for now; no repo has enough cross-run intervention evidence to demand a historical follow-up read yet.",
                ),
            ),
        ),
        (
            ACTION_SYNC_CANONICAL_LABELS["automation_guidance"],
            automation_section.get(
                "headline",
                weekly_pack.get(
                    "automation_guidance_summary",
                    "Automation guidance stays quiet until a campaign has a clearly safe preview, follow-up, or manual-only posture.",
                ),
            ),
        ),
        (
            "Next Safe Automation Step",
            automation_section.get(
                "next_step",
                weekly_pack.get(
                    "next_safe_automation_step",
                    "Stay local for now; no current campaign has a stronger safe automation posture than manual review.",
                ),
            ),
        ),
        (
            ACTION_SYNC_CANONICAL_LABELS["approval_workflow"],
            approval_section.get(
                "headline",
                weekly_pack.get(
                    "approval_workflow_summary",
                    "No current approval needs review yet, so the approval workflow can stay local for now.",
                ),
            ),
        ),
        (
            ACTION_SYNC_CANONICAL_LABELS["next_approval_review"],
            approval_section.get(
                "next_step",
                weekly_pack.get(
                    "next_approval_review",
                    "Stay local for now; no current approval needs review.",
                ),
            ),
        ),
    ]
