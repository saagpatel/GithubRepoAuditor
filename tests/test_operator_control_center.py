from __future__ import annotations

from pathlib import Path

from src.operator_control_center import build_operator_snapshot, normalize_review_state


def _make_report(**overrides) -> dict:
    data = {
        "username": "testuser",
        "generated_at": "2026-03-29T12:00:00+00:00",
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
            "review_id": "review-1",
            "source_run_id": "testuser:2026-03-29T12:00:00+00:00",
            "status": "open",
        },
        "review_targets": [
            {
                "repo": "RepoA",
                "reason": "Strong score movement",
                "severity": 0.6,
                "recommended_next_step": "Inspect the repo and decide whether to promote it.",
            },
            {
                "repo": "RepoB",
                "reason": "Nothing crossed the threshold",
                "severity": 0.2,
                "recommended_next_step": "Safe to defer.",
            },
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
        "governance_drift": [
            {
                "action_id": "gov-1",
                "repo_full_name": "user/RepoE",
                "control_key": "secret_scanning",
                "drift_type": "approval-invalidated",
            }
        ],
        "campaign_summary": {"campaign_type": "security-review", "label": "Security Review", "action_count": 2, "repo_count": 2},
        "writeback_preview": {"sync_mode": "reconcile"},
        "governance_preview": {
            "actions": [
                {
                    "action_id": "gov-ready",
                    "repo_full_name": "user/RepoF",
                    "title": "Enable secret scanning",
                    "why": "This repo is ready for governed review.",
                    "applyable": True,
                }
            ]
        },
        "rollback_preview": {"available": True, "item_count": 1, "fully_reversible_count": 0},
        "audits": [],
    }
    data.update(overrides)
    return data


def test_operator_snapshot_assigns_expected_lanes(tmp_path: Path):
    snapshot = build_operator_snapshot(_make_report(), output_dir=tmp_path)
    lanes = {item["title"]: item["lane"] for item in snapshot["operator_queue"]}
    assert lanes["GitHub authentication is required."] == "blocked"
    assert lanes["RepoC security posture changed"] == "urgent"
    assert lanes["RepoD drift needs review"] == "urgent"
    assert lanes["Enable secret scanning"] == "ready"
    assert lanes["Review RepoB"] == "deferred"


def test_operator_snapshot_filters_by_triage_view(tmp_path: Path):
    snapshot = build_operator_snapshot(_make_report(), output_dir=tmp_path, triage_view="ready")
    assert snapshot["operator_queue"]
    assert all(item["lane"] == "ready" for item in snapshot["operator_queue"])


def test_normalize_review_state_backfills_missing_fields(tmp_path: Path):
    report = normalize_review_state(
        {
            "username": "testuser",
            "generated_at": "2026-03-29T12:00:00+00:00",
            "audits": [],
        },
        output_dir=tmp_path,
        diff_data=None,
    )
    assert "review_summary" in report
    assert "review_targets" in report
    assert isinstance(report["review_history"], list)
