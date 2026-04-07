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
    assert payload["issue_candidate"]["title"] == "Scheduled Audit Handoff: testuser"
    assert (tmp_path / "scheduled-handoff-testuser-2026-04-07.md").is_file()
    assert (tmp_path / "scheduled-handoff-testuser-2026-04-07.json").is_file()


def test_build_scheduled_handoff_stays_quiet_for_quiet_runs(tmp_path):
    payload = _control_center_payload(urgency="quiet")
    payload["operator_summary"]["headline"] = "No operator triage items are currently surfaced."
    payload["operator_summary"]["what_changed"] = "No new blocking or urgent drift is surfaced in the latest operator snapshot."
    payload["operator_summary"]["why_it_matters"] = "The latest run is quiet enough that no immediate operator intervention is required."
    payload["operator_summary"]["what_to_do_next"] = "Continue the normal audit/control-center loop and review the next artifact for change."
    payload["operator_summary"]["counts"] = {"blocked": 0, "urgent": 0, "ready": 0, "deferred": 0}
    payload["operator_queue"] = []
    payload["operator_recent_changes"] = []
    (tmp_path / "operator-control-center-testuser-2026-04-07.json").write_text(json.dumps(payload))

    result = build_scheduled_handoff(tmp_path)

    assert result["issue_candidate"]["should_open"] is False
    markdown = (tmp_path / "scheduled-handoff-testuser-2026-04-07.md").read_text()
    assert "Issue automation: `quiet`" in markdown
