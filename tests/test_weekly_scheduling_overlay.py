from __future__ import annotations

import pytest

from src.weekly_scheduling_overlay import apply_weekly_scheduling_overlay


def _base_weekly_pack() -> dict:
    return {
        "what_to_do_this_week": "Protect the current queue winner first.",
        "queue_pressure_summary": "Urgent queue pressure still needs operator attention.",
        "next_best_workflow_step": "Open the standard workbook first, then inspect the current queue winner.",
        "top_recommendation_summary": "Protect the current queue winner first.",
        "approval_workflow_summary": "Governance: all is the strongest approval review candidate right now.",
        "next_approval_review": "Review Governance: all next and decide whether the approval still matches the packet.",
    }


def _operator_summary(*, blocked: int = 0, urgent: int = 0) -> dict:
    return {"counts": {"blocked": blocked, "urgent": urgent, "ready": 1, "deferred": 1}}


@pytest.mark.parametrize(
    ("blocked", "urgent"),
    [
        (1, 0),
        (0, 1),
    ],
)
def test_overlay_is_suppressed_by_blocked_or_urgent_pressure(blocked: int, urgent: int) -> None:
    weekly_pack = {
        **_base_weekly_pack(),
        "top_needs_reapproval_approvals": [
            {
                "label": "Governance: all",
                "summary": "Needs re-approval before any further action.",
                "approval_command": "audit testuser --approve-governance --governance-scope all",
            }
        ],
    }

    updated = apply_weekly_scheduling_overlay(weekly_pack, _operator_summary(blocked=blocked, urgent=urgent))

    assert updated["what_to_do_this_week"] == "Protect the current queue winner first."
    assert updated["queue_pressure_summary"] == "Urgent queue pressure still needs operator attention."
    assert "weekly_priority_reason_codes" not in updated


@pytest.mark.parametrize(
    ("bucket_key", "expected_state", "command_key", "command_text", "expected_posture"),
    [
        (
            "top_needs_reapproval_approvals",
            "needs-reapproval",
            "approval_command",
            "audit testuser --approve-governance --governance-scope all",
            "local-approval-capture",
        ),
        (
            "top_overdue_approval_followups",
            "overdue-follow-up",
            "follow_up_command",
            "audit testuser --review-governance --governance-scope all",
            "local-follow-up-review",
        ),
        (
            "top_ready_for_review_approvals",
            "ready-for-review",
            "approval_command",
            "audit testuser --approve-governance --governance-scope all",
            "local-approval-capture",
        ),
        (
            "top_due_soon_approval_followups",
            "due-soon-follow-up",
            "follow_up_command",
            "audit testuser --review-governance --governance-scope all",
            "local-follow-up-review",
        ),
    ],
)
def test_overlay_prioritizes_allowed_approval_buckets(
    bucket_key: str,
    expected_state: str,
    command_key: str,
    command_text: str,
    expected_posture: str,
) -> None:
    weekly_pack = {
        **_base_weekly_pack(),
        bucket_key: [
            {
                "label": "Governance: all",
                "summary": "Governance: all is the strongest approval candidate.",
                command_key: command_text,
            }
        ],
    }

    updated = apply_weekly_scheduling_overlay(weekly_pack, _operator_summary())

    assert updated["what_to_do_this_week"] == weekly_pack["next_approval_review"]
    assert updated["queue_pressure_summary"] == weekly_pack["approval_workflow_summary"]
    assert updated["top_recommendation_summary"] == weekly_pack["next_approval_review"]
    assert updated["next_best_workflow_step"].startswith("Open the standard workbook first, then review Governance")
    assert updated["weekly_priority_reason_codes"] == [
        "approval-aware-scheduling",
        "approval-workflow",
        expected_state,
    ]
    assert updated["weekly_priority_evidence_items"][0]["command_hint"] == command_text
    assert updated["weekly_priority_evidence_items"][0]["safe_posture"] == expected_posture


def test_overlay_preserves_current_decision_when_only_non_winning_approval_states_exist() -> None:
    weekly_pack = {
        **_base_weekly_pack(),
        "top_approved_manual_approvals": [
            {
                "label": "Governance: all",
                "summary": "Already approved manually and waiting for a separate apply step.",
                "manual_apply_command": "audit testuser --writeback-apply --governance-scope all",
            }
        ],
        "top_blocked_approvals": [
            {
                "label": "Governance: all",
                "summary": "Blocked on missing governance packet.",
            }
        ],
    }

    updated = apply_weekly_scheduling_overlay(weekly_pack, _operator_summary())

    assert updated["what_to_do_this_week"] == "Protect the current queue winner first."
    assert updated["top_recommendation_summary"] == "Protect the current queue winner first."
    assert "weekly_priority_evidence_items" not in updated
