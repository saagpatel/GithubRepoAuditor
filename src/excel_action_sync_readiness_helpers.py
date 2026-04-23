"""Shared Action Sync workbook summary helpers."""

from __future__ import annotations

from src.report_enrichment import build_action_sync_command_hint
from src.terminology import ACTION_SYNC_CANONICAL_LABELS


def action_sync_readiness_rows(data: dict) -> list[tuple[str, object]]:
    return [
        (
            ACTION_SYNC_CANONICAL_LABELS["readiness"],
            (data.get("action_sync_summary") or {}).get(
                "summary",
                "No current campaign needs Action Sync yet, so the safest next move is to keep the story local.",
            ),
        ),
        (
            "Next Action Sync Step",
            data.get(
                "next_action_sync_step",
                "Stay local for now; no current campaign needs preview or apply.",
            ),
        ),
        (
            "Apply Packet",
            (data.get("apply_readiness_summary") or {}).get(
                "summary",
                "No current campaign has a safe execution handoff yet, so the local story should stay local for now.",
            ),
        ),
        ("Command Hint", build_action_sync_command_hint(data)),
        (
            ACTION_SYNC_CANONICAL_LABELS["post_apply_monitoring"],
            (data.get("campaign_outcomes_summary") or {}).get(
                "summary",
                "No recent Action Sync apply needs post-apply monitoring yet, so the local weekly story can stay local.",
            ),
        ),
        (
            "Next Monitoring Step",
            (data.get("next_monitoring_step") or {}).get(
                "summary",
                "Stay local for now; no recent Action Sync apply needs post-apply follow-up yet.",
            ),
        ),
        (
            ACTION_SYNC_CANONICAL_LABELS["campaign_tuning"],
            (data.get("campaign_tuning_summary") or {}).get(
                "summary",
                "Campaign tuning is neutral because there is not enough outcome history yet to bias tied recommendations.",
            ),
        ),
        (
            ACTION_SYNC_CANONICAL_LABELS["next_tie_break_candidate"],
            (data.get("next_tuned_campaign") or {}).get(
                "summary",
                "No current campaign needs a tuning tie-break yet.",
            ),
        ),
        (
            ACTION_SYNC_CANONICAL_LABELS["historical_portfolio_intelligence"],
            (data.get("intervention_ledger_summary") or {}).get(
                "summary",
                "Historical portfolio intelligence is still thin, so the weekly story should stay grounded in the current run and recent operator queue.",
            ),
        ),
        (
            "Next Historical Focus",
            (data.get("next_historical_focus") or {}).get(
                "summary",
                "Stay local for now; no repo has enough cross-run intervention evidence to demand a historical follow-up read yet.",
            ),
        ),
        (
            ACTION_SYNC_CANONICAL_LABELS["automation_guidance"],
            (data.get("automation_guidance_summary") or {}).get(
                "summary",
                "Automation guidance stays quiet until a campaign has a clearly safe preview, follow-up, or manual-only posture.",
            ),
        ),
        (
            "Next Safe Automation Step",
            (data.get("next_safe_automation_step") or {}).get(
                "summary",
                "Stay local for now; no current campaign has a stronger safe automation posture than manual review.",
            ),
        ),
        (
            ACTION_SYNC_CANONICAL_LABELS["approval_workflow"],
            (data.get("approval_workflow_summary") or {}).get(
                "summary",
                "No current approval needs review yet, so the approval workflow can stay local for now.",
            ),
        ),
        (
            ACTION_SYNC_CANONICAL_LABELS["next_approval_review"],
            (data.get("next_approval_review") or {}).get(
                "summary",
                "Stay local for now; no current approval needs review.",
            ),
        ),
    ]
