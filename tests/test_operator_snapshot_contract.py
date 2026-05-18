from __future__ import annotations

from pathlib import Path

from src.operator_control_center import build_operator_snapshot, control_center_artifact_payload


def _make_contract_report(**overrides) -> dict:
    report = {
        "username": "contract-user",
        "generated_at": "2026-04-14T12:00:00+00:00",
        "preflight_summary": {
            "status": "error",
            "blocking_errors": 1,
            "warnings": 0,
            "checks": [
                {
                    "key": "github-token",
                    "category": "github-auth",
                    "status": "error",
                    "summary": "GitHub authentication is required.",
                    "details": "No token was found.",
                    "recommended_fix": "Set GITHUB_TOKEN.",
                }
            ],
        },
        "review_summary": {
            "review_id": "review-contract",
            "source_run_id": "contract-user:2026-04-14T12:00:00+00:00",
            "status": "open",
        },
        "watch_state": {
            "watch_enabled": True,
            "requested_strategy": "adaptive",
            "chosen_mode": "full",
            "next_recommended_run_mode": "full",
            "reason": "full-refresh-due",
            "reason_summary": "The next run should be full because the scheduled full refresh interval has been reached.",
            "full_refresh_due": True,
        },
        "review_targets": [
            {
                "repo": "RepoA",
                "reason": "Strong score movement",
                "severity": 0.6,
                "recommended_next_step": "Inspect the repo and decide whether to promote it.",
            }
        ],
        "material_changes": [
            {
                "change_key": "high-1",
                "change_type": "security-change",
                "repo_name": "RepoC",
                "severity": 0.9,
                "title": "RepoC security posture changed",
                "summary": "critical -> watch",
                "recommended_next_step": "Review this repo now.",
            }
        ],
        "managed_state_drift": [
            {
                "action_id": "campaign-1",
                "repo_full_name": "user/RepoD",
                "target": "github-issue",
                "drift_state": "managed-issue-edited",
            }
        ],
        "governance_drift": [],
        "campaign_summary": {
            "campaign_type": "security-review",
            "label": "Security Review",
            "action_count": 2,
            "repo_count": 2,
        },
        "writeback_preview": {"sync_mode": "reconcile"},
        "governance_preview": {"actions": []},
        "rollback_preview": {"available": False, "item_count": 0, "fully_reversible_count": 0},
        "audits": [],
    }
    report.update(overrides)
    return report


def test_operator_snapshot_contract_keys_and_invariants(tmp_path: Path):
    report = _make_contract_report()
    snapshot = build_operator_snapshot(report, output_dir=tmp_path)

    assert {
        "operator_queue",
        "operator_summary",
        "operator_setup_health",
        "operator_recent_changes",
        "portfolio_outcomes_summary",
        "operator_effectiveness_summary",
        "high_pressure_queue_history",
    }.issubset(snapshot)

    summary = snapshot["operator_summary"]
    assert {
        "headline",
        "counts",
        "primary_target",
        "what_to_do_next",
        "what_changed",
        "why_it_matters",
        "follow_through_summary",
    }.issubset(summary)

    queue = snapshot["operator_queue"]
    assert queue
    assert {
        "item_id",
        "lane",
        "lane_label",
        "lane_reason",
        "priority",
        "recommended_action",
        "summary",
        "title",
    }.issubset(queue[0])

    lane_order = {"blocked": 0, "urgent": 1, "ready": 2, "deferred": 3}
    queue_lanes = [lane_order[item["lane"]] for item in queue]
    assert queue_lanes == sorted(queue_lanes)

    primary_target = summary["primary_target"]
    assert primary_target
    assert primary_target["item_id"] == queue[0]["item_id"]
    assert summary["what_to_do_next"]

    payload = control_center_artifact_payload(report, snapshot)
    assert {
        "username",
        "generated_at",
        "operator_summary",
        "operator_queue",
        "operator_setup_health",
        "operator_recent_changes",
        "portfolio_outcomes_summary",
        "operator_effectiveness_summary",
    }.issubset(payload)
