from __future__ import annotations

from src.weekly_packaging import finalize_weekly_pack


def test_finalize_weekly_pack_adds_story_and_compact_explainability() -> None:
    weekly_pack = {
        "portfolio_headline": "Portfolio headline",
        "what_to_do_this_week": "Review Governance: all next.",
        "queue_pressure_summary": "Approval review is the clean next weekly step.",
        "next_best_workflow_step": "Open the workbook, then use --control-center.",
        "trust_actionability_summary": "Trust is stable enough for a review-first step.",
        "operator_focus_summary": "Act Now remains the top focus bucket.",
        "operator_outcomes_summary": "Recent operator work is improving outcomes.",
        "action_sync_summary": "Action Sync is preview-ready.",
        "next_action_sync_step": "Preview Security Review next.",
        "apply_readiness_summary": "Preview Security Review before deciding on apply.",
        "next_apply_candidate": "Preview Security Review next.",
        "campaign_outcomes_summary": "Security Review was applied recently; monitor it now.",
        "next_monitoring_step": "Monitor Security Review for 2 post-apply runs.",
        "campaign_tuning_summary": "Security Review should win ties because recent outcomes are proven.",
        "next_tie_break_candidate": "Security Review is the next tie-break candidate.",
        "historical_portfolio_intelligence": "RepoA is improving after intervention.",
        "next_historical_focus": "Read RepoA next.",
        "automation_guidance_summary": "Preview Security Review next; that is the strongest safe automation step.",
        "next_safe_automation_step": "Preview Security Review next.",
        "approval_workflow_summary": "Governance: all is the strongest approval review candidate right now.",
        "next_approval_review": "Review Governance: all next.",
        "follow_through_checkpoint_summary": "Use the next run to confirm the packet still matches.",
        "top_preview_ready_campaigns": [{"label": "Security Review", "reason": "1 action is ready for preview.", "recommended_target": "all"}],
        "top_ready_to_apply_packets": [
            {"label": "Security Review", "summary": "Preview first, then reassess apply.", "preview_command": "audit testuser --campaign security-review --writeback-target all"}
        ],
        "top_monitor_now_campaigns": [{"label": "Security Review", "summary": "Still inside the short monitoring window."}],
        "top_proven_campaigns": [{"label": "Security Review", "summary": "Recent outcomes are proven."}],
        "top_improving_repos": [{"repo": "RepoA", "summary": "Improving after intervention."}],
        "top_preview_safe_campaigns": [{"label": "Security Review", "summary": "Preview is the strongest safe automation posture.", "recommended_command": "audit testuser --campaign security-review --writeback-target all"}],
        "top_ready_for_review_approvals": [{"label": "Governance: all", "subject_key": "all", "summary": "Governance scope all is ready for review.", "approval_command": "audit testuser --approve-governance --governance-scope all"}],
        "top_attention": [
            {
                "repo": "RepoA",
                "why": "Approval review is now the clean next step.",
                "operator_focus_line": "Operator Focus: act now.",
                "action_sync_line": "Action Sync: preview-ready.",
                "automation_line": "Automation Guidance: preview-safe.",
                "automation_command": "audit testuser --campaign security-review --writeback-target all",
                "approval_line": "Approval Workflow: ready for review.",
                "follow_through_checkpoint": "Use the next run to confirm the packet still matches.",
            }
        ],
        "repo_briefings": [
            {
                "repo": "RepoA",
                "why_it_matters_line": "RepoA is the clearest current starting point.",
                "what_to_do_next_line": "Start with RepoA in src/core.py.",
                "where_to_start_summary": "Start with RepoA in src/core.py.",
                "operator_focus_line": "Operator Focus: act now.",
                "action_sync_line": "Action Sync: preview-ready.",
                "apply_packet_command": "audit testuser --campaign security-review --writeback-target all",
                "automation_line": "Automation Guidance: preview-safe.",
                "automation_command": "audit testuser --campaign security-review --writeback-target all",
                "approval_line": "Approval Workflow: ready for review.",
            }
        ],
    }

    finalized = finalize_weekly_pack(weekly_pack)

    assert finalized["weekly_story_v1"]["version"] == 1
    assert finalized["weekly_story_v1"]["section_order"][0] == "weekly-priority"
    assert finalized["weekly_story_v1"]["sections"][1]["reason_codes"] == ["action-sync", "readiness"]
    assert finalized["top_attention"][0]["why_it_won"] == "Approval review is now the clean next step."
    assert finalized["top_attention"][0]["evidence_strip"][2]["safe_posture"] == "bounded-command"
    assert finalized["repo_briefings"][0]["next_step"] == "Start with RepoA in src/core.py."
    assert finalized["repo_briefings"][0]["evidence_strip"][2]["command_hint"] == (
        "audit testuser --campaign security-review --writeback-target all"
    )
