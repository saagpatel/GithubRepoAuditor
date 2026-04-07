from __future__ import annotations

import json

from src.scheduled_handoff import build_scheduled_handoff


def _control_center_payload(*, urgency: str = "urgent") -> dict:
    return {
        "username": "testuser",
        "generated_at": "2026-04-07T12:00:00+00:00",
        "report_reference": "output/audit-report-testuser-2026-04-07.json",
        "operator_summary": {
            "headline": "There is live drift or high-severity change that needs attention now.",
            "counts": {"blocked": 0, "urgent": 1, "ready": 0, "deferred": 0},
            "urgency": urgency,
            "escalation_reason": "drift-or-regression",
            "what_changed": "RepoC drift needs review — managed-issue-edited",
            "why_it_matters": "This has crossed into live drift, regression risk, or rollback exposure and should be reviewed before it spreads.",
            "what_to_do_next": "Inspect the managed issue before closing the campaign.",
            "trend_status": "stable",
            "trend_summary": "The queue is stable but still sticky: 1 attention item is persisting from the last run. Close RepoC: RepoC drift needs review next.",
            "new_attention_count": 0,
            "resolved_attention_count": 0,
            "persisting_attention_count": 1,
            "reopened_attention_count": 0,
            "quiet_streak_runs": 0,
            "aging_status": "watch",
            "primary_target_reason": "This urgent item is already being watched across recent runs, so it stays ahead of ready work until it clears.",
            "primary_target_done_criteria": "Inspect and reconcile the drift, then confirm this item no longer reappears on the next run.",
            "closure_guidance": "Inspect the managed issue before closing the campaign. Treat this as done only when inspect and reconcile the drift, then confirm this item no longer reappears on the next run.",
            "decision_memory_status": "attempted",
            "primary_target_last_intervention": {
                "item_id": "campaign-drift:repo-c",
                "repo": "RepoC",
                "title": "RepoC drift needs review",
                "event_type": "drifted",
                "recorded_at": "2026-04-07T12:00:00+00:00",
                "outcome": "drifted",
            },
            "primary_target_last_outcome": "no-change",
            "primary_target_resolution_evidence": "The last intervention was drifted for RepoC: RepoC drift needs review, but the item is still open.",
            "primary_target_confidence_score": 0.7,
            "primary_target_confidence_label": "medium",
            "primary_target_confidence_reasons": [
                "Urgent drift or regression needs attention before ready work.",
                "A prior intervention happened, but the item is still open.",
                "This item has repeated recently and is no longer brand new.",
            ],
            "recent_interventions": [
                {
                    "item_id": "campaign-drift:repo-c",
                    "repo": "RepoC",
                    "title": "RepoC drift needs review",
                    "event_type": "drifted",
                    "recorded_at": "2026-04-07T12:00:00+00:00",
                    "outcome": "drifted",
                }
            ],
            "recently_quieted_count": 0,
            "confirmed_resolved_count": 0,
            "reopened_after_resolution_count": 0,
            "decision_memory_window_runs": 3,
            "resolution_evidence_summary": "The last intervention was drifted for RepoC: RepoC drift needs review, but the item is still open.",
            "next_action_confidence_score": 0.75,
            "next_action_confidence_label": "high",
            "next_action_confidence_reasons": ["The next step is tied directly to the current top target."],
            "recommendation_quality_summary": "Strong recommendation because the next step is tied directly to the current top target.",
            "chronic_item_count": 0,
            "newly_stale_count": 0,
            "longest_persisting_item": {
                "repo": "RepoC",
                "title": "RepoC drift needs review",
                "age_days": 4,
                "aging_status": "watch",
            },
            "attention_age_bands": {"0-1 days": 0, "2-7 days": 1, "8-21 days": 0, "22+ days": 0},
            "accountability_summary": "This urgent item is already being watched across recent runs, so it stays ahead of ready work until it clears. Aging pressure: 0 chronic item(s) and 0 newly stale item(s).",
            "primary_target": {
                "item_id": "campaign-drift:repo-c",
                "repo": "RepoC",
                "title": "RepoC drift needs review",
                "recommended_action": "Inspect the managed issue before closing the campaign.",
            },
            "next_recommended_run_mode": "incremental",
            "watch_strategy": "adaptive",
            "watch_decision_summary": "The current baseline is still compatible, so incremental watch remains safe for the next run.",
        },
        "operator_queue": [
            {
                "lane": "urgent",
                "lane_label": "Needs Attention Now",
                "repo": "RepoC",
                "title": "RepoC drift needs review",
                "summary": "managed-issue-edited",
                "recommended_action": "Inspect the managed issue before closing the campaign.",
            }
        ],
        "operator_recent_changes": [
            {"generated_at": "2026-04-07T12:00:00+00:00", "repo": "RepoC", "summary": "managed-issue-edited"}
        ],
    }


def test_build_scheduled_handoff_writes_artifacts_and_issue_candidate(tmp_path):
    (tmp_path / "operator-control-center-testuser-2026-04-07.json").write_text(
        json.dumps(_control_center_payload())
    )

    payload = build_scheduled_handoff(tmp_path)

    assert payload["status"] == "ok"
    assert payload["issue_candidate"]["should_open"] is True
    assert payload["issue_candidate"]["action"] == "open"
    assert payload["issue_candidate"]["title"] == "Scheduled Audit Handoff: testuser"
    assert (tmp_path / "scheduled-handoff-testuser-2026-04-07.md").is_file()
    assert (tmp_path / "scheduled-handoff-testuser-2026-04-07.json").is_file()
    markdown = (tmp_path / "scheduled-handoff-testuser-2026-04-07.md").read_text()
    assert "What Got Better" in markdown
    assert "What Needs Attention Now" in markdown
    assert "Primary target: RepoC: RepoC drift needs review" in markdown
    assert "What We Tried" in markdown
    assert "Why This Is Still Open" in markdown
    assert "What Counts As Done" in markdown
    assert "Resolution Evidence" in markdown
    assert "Recommendation Confidence" in markdown
    assert "Primary target confidence: medium (0.70)" in markdown
    assert "Aging Pressure" in markdown
    assert "What Reopened" in markdown


def test_build_scheduled_handoff_stays_quiet_for_quiet_runs(tmp_path):
    payload = _control_center_payload(urgency="quiet")
    payload["operator_summary"]["headline"] = "No operator triage items are currently surfaced."
    payload["operator_summary"]["what_changed"] = "No new blocking or urgent drift is surfaced in the latest operator snapshot."
    payload["operator_summary"]["why_it_matters"] = "The latest run is quiet enough that no immediate operator intervention is required."
    payload["operator_summary"]["what_to_do_next"] = "Continue the normal audit/control-center loop and review the next artifact for change."
    payload["operator_summary"]["counts"] = {"blocked": 0, "urgent": 0, "ready": 0, "deferred": 0}
    payload["operator_summary"]["trend_status"] = "quiet"
    payload["operator_summary"]["trend_summary"] = "The queue is quiet and has stayed that way for 2 consecutive run(s)."
    payload["operator_summary"]["quiet_streak_runs"] = 2
    payload["operator_summary"]["resolved_attention_count"] = 1
    payload["operator_summary"]["persisting_attention_count"] = 0
    payload["operator_queue"] = []
    payload["operator_recent_changes"] = []
    (tmp_path / "operator-control-center-testuser-2026-04-07.json").write_text(json.dumps(payload))

    result = build_scheduled_handoff(tmp_path)

    assert result["issue_candidate"]["should_open"] is False
    assert result["issue_candidate"]["action"] == "quiet"
    markdown = (tmp_path / "scheduled-handoff-testuser-2026-04-07.md").read_text()
    assert "Issue automation: `quiet`" in markdown
    assert "2 consecutive run(s)" in markdown


def test_build_scheduled_handoff_closes_open_issue_when_run_turns_quiet(tmp_path):
    payload = _control_center_payload(urgency="quiet")
    payload["operator_summary"]["headline"] = "No operator triage items are currently surfaced."
    payload["operator_summary"]["counts"] = {"blocked": 0, "urgent": 0, "ready": 0, "deferred": 0}
    payload["operator_summary"]["what_changed"] = "No new blocking or urgent drift is surfaced in the latest operator snapshot."
    payload["operator_summary"]["why_it_matters"] = "The latest run is quiet enough that no immediate operator intervention is required."
    payload["operator_summary"]["what_to_do_next"] = "Continue the normal audit/control-center loop and review the next artifact for change."
    payload["operator_queue"] = []
    (tmp_path / "operator-control-center-testuser-2026-04-07.json").write_text(json.dumps(payload))

    result = build_scheduled_handoff(tmp_path, issue_state="open", issue_number="42", issue_url="https://example.com/42")

    assert result["issue_candidate"]["action"] == "close"
    assert result["issue_candidate"]["close_reason"] == "quiet-recovery"
    assert result["issue_candidate"]["issue_number"] == "42"


def test_build_scheduled_handoff_reopens_closed_canonical_issue_for_new_noise(tmp_path):
    (tmp_path / "operator-control-center-testuser-2026-04-07.json").write_text(
        json.dumps(_control_center_payload())
    )

    result = build_scheduled_handoff(tmp_path, issue_state="closed", issue_number="42", issue_url="https://example.com/42")

    assert result["issue_candidate"]["action"] == "update"
    assert result["issue_candidate"]["reopen_existing"] is True
