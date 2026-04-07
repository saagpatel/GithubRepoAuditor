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


def test_operator_snapshot_includes_watch_guidance(tmp_path: Path):
    snapshot = build_operator_snapshot(_make_report(), output_dir=tmp_path)
    summary = snapshot["operator_summary"]
    assert summary["watch_strategy"] == "adaptive"
    assert summary["next_recommended_run_mode"] == "full"
    assert summary["watch_decision_summary"].startswith("The next run should be full")
    assert summary["what_changed"].startswith("GitHub authentication is required.")
    assert summary["why_it_matters"]
    assert summary["what_to_do_next"].startswith("Act now: Set GITHUB_TOKEN")
    assert summary["urgency"] == "blocked"
    assert summary["trend_status"] == "stable"
    assert summary["primary_target"]["title"] == "GitHub authentication is required."
    assert summary["aging_status"] == "stale"
    assert "setup blocker" in summary["primary_target_reason"].lower()
    assert "rerun the relevant command" in summary["primary_target_done_criteria"].lower()
    assert "Set GITHUB_TOKEN" in summary["closure_guidance"]
    assert summary["decision_memory_status"] == "new"
    assert summary["primary_target_last_outcome"] == "no-change"
    assert "no earlier intervention" in summary["primary_target_resolution_evidence"].lower()
    assert summary["primary_target_confidence_label"] == "high"
    assert summary["primary_target_confidence_score"] >= 0.75
    assert summary["next_action_confidence_label"] == "high"
    assert summary["primary_target_trust_policy"] == "act-now"
    assert "blocked" in summary["primary_target_trust_policy_reason"].lower()
    assert "guidance" in summary["adaptive_confidence_summary"].lower() or "immediate action" in summary["adaptive_confidence_summary"].lower()
    assert summary["recommendation_quality_summary"].startswith("Strong recommendation because")


def test_operator_snapshot_adds_follow_through_from_recent_history(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "src.operator_control_center.load_operator_state_history",
        lambda *_args, **_kwargs: [
            {
                "operator_summary": {"counts": {"blocked": 0, "urgent": 1, "ready": 0, "deferred": 0}},
                "operator_queue": [
                    {
                        "item_id": "campaign-drift:campaign-1:github-issue",
                        "lane": "urgent",
                        "age_days": 8,
                        "repo": "RepoD",
                        "title": "RepoD drift needs review",
                    }
                ],
            },
            {
                "operator_summary": {"counts": {"blocked": 0, "urgent": 1, "ready": 0, "deferred": 0}},
                "operator_queue": [
                    {
                        "item_id": "campaign-drift:campaign-1:github-issue",
                        "lane": "urgent",
                        "age_days": 9,
                        "repo": "RepoD",
                        "title": "RepoD drift needs review",
                    }
                ],
            },
        ],
    )

    snapshot = build_operator_snapshot(_make_report(preflight_summary={}), output_dir=tmp_path)
    summary = snapshot["operator_summary"]

    assert summary["repeat_urgent_count"] >= 1
    assert summary["stale_item_count"] >= 1
    assert summary["oldest_open_item_days"] >= 8
    assert "urgent item" in summary["follow_through_summary"]
    assert summary["persisting_attention_count"] >= 1
    assert summary["trend_status"] == "worsening"


def test_operator_snapshot_marks_quiet_recovery_as_improving(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "src.operator_control_center.load_operator_state_history",
        lambda *_args, **_kwargs: [
            {
                "operator_summary": {"counts": {"blocked": 0, "urgent": 1, "ready": 0, "deferred": 0}},
                "operator_queue": [
                    {
                        "item_id": "campaign-drift:campaign-1:github-issue",
                        "lane": "urgent",
                        "age_days": 1,
                        "repo": "RepoD",
                        "title": "RepoD drift needs review",
                    }
                ],
            }
        ],
    )

    snapshot = build_operator_snapshot(
        _make_report(
            preflight_summary={},
            material_changes=[],
            managed_state_drift=[],
            governance_drift=[],
            governance_preview={},
            rollback_preview={},
            review_targets=[
                {
                    "repo": "RepoB",
                    "reason": "Nothing crossed the threshold",
                    "severity": 0.2,
                    "recommended_next_step": "Safe to defer.",
                }
            ],
        ),
        output_dir=tmp_path,
    )
    summary = snapshot["operator_summary"]

    assert summary["trend_status"] == "improving"
    assert summary["resolved_attention_count"] == 1
    assert "cleared" in summary["trend_summary"]


def test_operator_snapshot_tracks_reopened_attention_items(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "src.operator_control_center.load_operator_state_history",
        lambda *_args, **_kwargs: [
            {
                "operator_summary": {"counts": {"blocked": 0, "urgent": 0, "ready": 0, "deferred": 0}},
                "operator_queue": [],
            },
            {
                "operator_summary": {"counts": {"blocked": 0, "urgent": 1, "ready": 0, "deferred": 0}},
                "operator_queue": [
                    {
                        "item_id": "campaign-drift:campaign-1:github-issue",
                        "lane": "urgent",
                        "age_days": 4,
                        "repo": "RepoD",
                        "title": "RepoD drift needs review",
                    }
                ],
            },
        ],
    )

    snapshot = build_operator_snapshot(
        _make_report(
            preflight_summary={},
            governance_drift=[],
            governance_preview={},
            rollback_preview={},
            review_targets=[],
            material_changes=[],
        ),
        output_dir=tmp_path,
    )
    summary = snapshot["operator_summary"]

    assert summary["trend_status"] == "worsening"
    assert summary["reopened_attention_count"] >= 1
    assert summary["primary_target"]["title"] == "RepoD drift needs review"


def test_operator_snapshot_prefers_reopened_urgent_over_fresh_urgent(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "src.operator_control_center.load_operator_state_history",
        lambda *_args, **_kwargs: [
            {
                "operator_summary": {"counts": {"blocked": 0, "urgent": 0, "ready": 0, "deferred": 0}},
                "operator_queue": [],
            },
            {
                "operator_summary": {"counts": {"blocked": 0, "urgent": 1, "ready": 0, "deferred": 0}},
                "operator_queue": [
                    {
                        "item_id": "campaign-drift:campaign-1:github-issue",
                        "lane": "urgent",
                        "age_days": 4,
                        "repo": "RepoD",
                        "title": "RepoD drift needs review",
                    }
                ],
            },
        ],
    )

    snapshot = build_operator_snapshot(
        _make_report(
            preflight_summary={},
            governance_drift=[],
            governance_preview={},
            rollback_preview={},
            review_targets=[],
        ),
        output_dir=tmp_path,
    )
    summary = snapshot["operator_summary"]
    resolution_targets = summary["resolution_targets"]

    assert resolution_targets[0]["title"] == "RepoD drift needs review"
    assert resolution_targets[0]["confidence_score"] >= resolution_targets[1]["confidence_score"]
    assert summary["primary_target"]["title"] == "RepoD drift needs review"
    assert summary["primary_target"]["item_id"] == resolution_targets[0]["item_id"]


def test_operator_snapshot_marks_chronic_targets_and_longest_persisting_item(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "src.operator_control_center.load_operator_state_history",
        lambda *_args, **_kwargs: [
            {
                "operator_summary": {"counts": {"blocked": 0, "urgent": 1, "ready": 0, "deferred": 0}},
                "operator_queue": [
                    {
                        "item_id": "campaign-drift:campaign-1:github-issue",
                        "lane": "urgent",
                        "age_days": 22,
                        "repo": "RepoD",
                        "title": "RepoD drift needs review",
                    }
                ],
            },
            {
                "operator_summary": {"counts": {"blocked": 0, "urgent": 1, "ready": 0, "deferred": 0}},
                "operator_queue": [
                    {
                        "item_id": "campaign-drift:campaign-1:github-issue",
                        "lane": "urgent",
                        "age_days": 23,
                        "repo": "RepoD",
                        "title": "RepoD drift needs review",
                    }
                ],
            },
            {
                "operator_summary": {"counts": {"blocked": 0, "urgent": 1, "ready": 0, "deferred": 0}},
                "operator_queue": [
                    {
                        "item_id": "campaign-drift:campaign-1:github-issue",
                        "lane": "urgent",
                        "age_days": 24,
                        "repo": "RepoD",
                        "title": "RepoD drift needs review",
                    }
                ],
            },
            {
                "operator_summary": {"counts": {"blocked": 0, "urgent": 1, "ready": 0, "deferred": 0}},
                "operator_queue": [
                    {
                        "item_id": "campaign-drift:campaign-1:github-issue",
                        "lane": "urgent",
                        "age_days": 25,
                        "repo": "RepoD",
                        "title": "RepoD drift needs review",
                    }
                ],
            },
        ],
    )

    snapshot = build_operator_snapshot(
        _make_report(
            preflight_summary={},
            governance_drift=[],
            governance_preview={},
            rollback_preview={},
            review_targets=[],
            material_changes=[],
        ),
        output_dir=tmp_path,
    )
    summary = snapshot["operator_summary"]

    assert summary["aging_status"] == "chronic"
    assert summary["chronic_item_count"] >= 1
    assert summary["longest_persisting_item"]["title"] == "RepoD drift needs review"
    assert "multiple cycles" in summary["primary_target_reason"]
    assert "reconcile the drift" in summary["primary_target_done_criteria"].lower()
    assert "aging pressure" in summary["accountability_summary"].lower()


def test_operator_snapshot_marks_attempted_when_recent_intervention_exists(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "src.operator_control_center.load_recent_operator_evidence",
        lambda *_args, **_kwargs: {
            "history": [
                {
                    "generated_at": "2026-03-28T12:00:00+00:00",
                    "operator_summary": {"counts": {"blocked": 0, "urgent": 1, "ready": 0, "deferred": 0}},
                    "operator_queue": [
                        {
                            "item_id": "campaign-drift:campaign-1:github-issue",
                            "lane": "urgent",
                            "age_days": 2,
                            "repo": "RepoD",
                            "title": "RepoD drift needs review",
                        }
                    ],
                }
            ],
            "events": [
                {
                    "item_id": "campaign-drift:campaign-1:github-issue",
                    "repo": "RepoD",
                    "title": "RepoD drift needs review",
                    "event_type": "drifted",
                    "recorded_at": "2026-03-29T12:00:00+00:00",
                    "outcome": "drifted",
                }
            ],
        },
    )

    snapshot = build_operator_snapshot(_make_report(preflight_summary={}, material_changes=[], governance_drift=[], governance_preview={}, rollback_preview={}, review_targets=[]), output_dir=tmp_path)
    summary = snapshot["operator_summary"]

    assert summary["decision_memory_status"] == "attempted"
    assert summary["primary_target_last_intervention"]["event_type"] == "drifted"
    assert summary["primary_target_last_outcome"] == "no-change"
    assert "still open" in summary["primary_target_resolution_evidence"].lower()


def test_operator_snapshot_tracks_confirmed_resolution_and_reopen_evidence(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "src.operator_control_center.load_recent_operator_evidence",
        lambda *_args, **_kwargs: {
            "history": [
                {
                    "generated_at": "2026-04-06T12:00:00+00:00",
                    "operator_summary": {"counts": {"blocked": 0, "urgent": 0, "ready": 0, "deferred": 0}},
                    "operator_queue": [],
                },
                {
                    "generated_at": "2026-04-05T12:00:00+00:00",
                    "operator_summary": {"counts": {"blocked": 0, "urgent": 0, "ready": 0, "deferred": 0}},
                    "operator_queue": [],
                },
                {
                    "generated_at": "2026-04-04T12:00:00+00:00",
                    "operator_summary": {"counts": {"blocked": 0, "urgent": 1, "ready": 0, "deferred": 0}},
                    "operator_queue": [
                        {
                            "item_id": "campaign-drift:campaign-1:github-issue",
                            "lane": "urgent",
                            "age_days": 4,
                            "repo": "RepoD",
                            "title": "RepoD drift needs review",
                        }
                    ],
                },
            ],
            "events": [],
        },
    )

    quiet_snapshot = build_operator_snapshot(
        _make_report(
            preflight_summary={},
            managed_state_drift=[],
            governance_drift=[],
            governance_preview={},
            rollback_preview={},
            campaign_summary={},
            writeback_preview={},
            review_targets=[],
            material_changes=[],
        ),
        output_dir=tmp_path,
    )
    quiet_summary = quiet_snapshot["operator_summary"]
    assert quiet_summary["decision_memory_status"] == "confirmed_resolved"
    assert quiet_summary["confirmed_resolved_count"] >= 1
    assert "confirmed resolved" in quiet_summary["resolution_evidence_summary"].lower()

    monkeypatch.setattr(
        "src.operator_control_center.load_recent_operator_evidence",
        lambda *_args, **_kwargs: {
            "history": [
                {
                    "generated_at": "2026-04-06T12:00:00+00:00",
                    "operator_summary": {"counts": {"blocked": 0, "urgent": 0, "ready": 0, "deferred": 0}},
                    "operator_queue": [],
                },
                {
                    "generated_at": "2026-04-05T12:00:00+00:00",
                    "operator_summary": {"counts": {"blocked": 0, "urgent": 0, "ready": 0, "deferred": 0}},
                    "operator_queue": [],
                },
                {
                    "generated_at": "2026-04-04T12:00:00+00:00",
                    "operator_summary": {"counts": {"blocked": 0, "urgent": 1, "ready": 0, "deferred": 0}},
                    "operator_queue": [
                        {
                            "item_id": "campaign-drift:campaign-1:github-issue",
                            "lane": "urgent",
                            "age_days": 4,
                            "repo": "RepoD",
                            "title": "RepoD drift needs review",
                        }
                    ],
                },
            ],
            "events": [],
        },
    )
    reopened_snapshot = build_operator_snapshot(
        _make_report(
            preflight_summary={},
            governance_drift=[],
            governance_preview={},
            rollback_preview={},
            review_targets=[],
            material_changes=[],
        ),
        output_dir=tmp_path,
    )
    reopened_summary = reopened_snapshot["operator_summary"]
    assert reopened_summary["decision_memory_status"] == "reopened"
    assert reopened_summary["primary_target_last_outcome"] == "reopened"
    assert reopened_summary["reopened_after_resolution_count"] >= 1


def test_operator_snapshot_marks_generic_low_priority_ready_work_as_low_confidence(tmp_path: Path):
    snapshot = build_operator_snapshot(
        _make_report(
            preflight_summary={},
            material_changes=[],
            managed_state_drift=[],
            governance_drift=[],
            governance_preview={},
            rollback_preview={},
            campaign_summary={},
            writeback_preview={},
            review_targets=[
                {
                    "repo": "RepoZ",
                    "reason": "Needs a manual look",
                    "severity": 0.1,
                    "recommended_next_step": "Review the latest state.",
                }
            ],
        ),
        output_dir=tmp_path,
    )
    summary = snapshot["operator_summary"]
    target = summary["resolution_targets"][0]

    assert target["lane"] == "ready"
    assert target["confidence_label"] == "low"
    assert target["confidence_score"] < 0.45
    assert summary["next_action_confidence_label"] == "low"
    assert summary["recommendation_quality_summary"].startswith("Tentative recommendation;")


def test_operator_snapshot_calibrates_healthy_confidence_history(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "src.operator_control_center.load_operator_calibration_history",
        lambda *_args, **_kwargs: [
            {
                "run_id": "run-6",
                "generated_at": "2026-04-06T12:00:00+00:00",
                "operator_summary": {},
                "operator_queue": [],
            },
            {
                "run_id": "run-5",
                "generated_at": "2026-04-05T12:00:00+00:00",
                "operator_summary": {},
                "operator_queue": [],
            },
            {
                "run_id": "run-4",
                "generated_at": "2026-04-04T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {"item_id": "target-d", "repo": "RepoD", "title": "Drift D", "lane": "urgent"},
                    "primary_target_confidence_label": "high",
                },
                "operator_queue": [{"item_id": "target-d", "repo": "RepoD", "title": "Drift D", "lane": "urgent"}],
            },
            {
                "run_id": "run-3",
                "generated_at": "2026-04-03T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {"item_id": "target-c", "repo": "RepoC", "title": "Drift C", "lane": "urgent"},
                    "primary_target_confidence_label": "high",
                },
                "operator_queue": [{"item_id": "target-c", "repo": "RepoC", "title": "Drift C", "lane": "urgent"}],
            },
            {
                "run_id": "run-2",
                "generated_at": "2026-04-02T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {"item_id": "target-b", "repo": "RepoB", "title": "Drift B", "lane": "urgent"},
                    "primary_target_confidence_label": "high",
                },
                "operator_queue": [{"item_id": "target-b", "repo": "RepoB", "title": "Drift B", "lane": "urgent"}],
            },
            {
                "run_id": "run-1",
                "generated_at": "2026-04-01T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {"item_id": "target-a", "repo": "RepoA", "title": "Drift A", "lane": "urgent"},
                    "primary_target_confidence_label": "high",
                },
                "operator_queue": [{"item_id": "target-a", "repo": "RepoA", "title": "Drift A", "lane": "urgent"}],
            },
        ],
    )

    snapshot = build_operator_snapshot(_make_report(), output_dir=tmp_path)
    summary = snapshot["operator_summary"]

    assert summary["confidence_validation_status"] == "healthy"
    assert summary["validated_recommendation_count"] == 4
    assert summary["high_confidence_hit_rate"] == 1.0
    assert summary["recent_validation_outcomes"]
    assert "validating well" in summary["confidence_calibration_summary"].lower()


def test_operator_snapshot_marks_noisy_calibration_when_reopens_repeat(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "src.operator_control_center.load_operator_calibration_history",
        lambda *_args, **_kwargs: [
            {
                "run_id": "run-6",
                "generated_at": "2026-04-06T12:00:00+00:00",
                "operator_summary": {},
                "operator_queue": [],
            },
            {
                "run_id": "run-5",
                "generated_at": "2026-04-05T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {"item_id": "target-c", "repo": "RepoC", "title": "Drift C", "lane": "urgent"},
                    "primary_target_confidence_label": "high",
                },
                "operator_queue": [{"item_id": "target-c", "repo": "RepoC", "title": "Drift C", "lane": "urgent"}],
            },
            {
                "run_id": "run-4",
                "generated_at": "2026-04-04T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {"item_id": "target-b", "repo": "RepoB", "title": "Drift B", "lane": "urgent"},
                    "primary_target_confidence_label": "high",
                },
                "operator_queue": [{"item_id": "target-b", "repo": "RepoB", "title": "Drift B", "lane": "urgent"}],
            },
            {
                "run_id": "run-3",
                "generated_at": "2026-04-03T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {"item_id": "target-a", "repo": "RepoA", "title": "Drift A", "lane": "urgent"},
                    "primary_target_confidence_label": "high",
                },
                "operator_queue": [{"item_id": "target-a", "repo": "RepoA", "title": "Drift A", "lane": "urgent"}],
            },
            {
                "run_id": "run-2",
                "generated_at": "2026-04-02T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {"item_id": "target-b", "repo": "RepoB", "title": "Drift B", "lane": "urgent"},
                    "primary_target_confidence_label": "high",
                },
                "operator_queue": [{"item_id": "target-b", "repo": "RepoB", "title": "Drift B", "lane": "urgent"}],
            },
            {
                "run_id": "run-1",
                "generated_at": "2026-04-01T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {"item_id": "target-a", "repo": "RepoA", "title": "Drift A", "lane": "urgent"},
                    "primary_target_confidence_label": "high",
                },
                "operator_queue": [{"item_id": "target-a", "repo": "RepoA", "title": "Drift A", "lane": "urgent"}],
            },
        ],
    )

    snapshot = build_operator_snapshot(_make_report(), output_dir=tmp_path)
    summary = snapshot["operator_summary"]

    assert summary["confidence_validation_status"] == "noisy"
    assert summary["reopened_recommendation_count"] >= 2
    assert summary["high_confidence_hit_rate"] == 0.5
    assert "noisy" in summary["confidence_calibration_summary"].lower()


def test_operator_snapshot_tracks_partially_validated_recommendations(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "src.operator_control_center.load_operator_calibration_history",
        lambda *_args, **_kwargs: [
            {
                "run_id": "run-5",
                "generated_at": "2026-04-05T12:00:00+00:00",
                "operator_summary": {},
                "operator_queue": [],
            },
            {
                "run_id": "run-4",
                "generated_at": "2026-04-04T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {"item_id": "target-c", "repo": "RepoC", "title": "Drift C", "lane": "urgent"},
                    "primary_target_confidence_label": "high",
                },
                "operator_queue": [{"item_id": "target-c", "repo": "RepoC", "title": "Drift C", "lane": "urgent"}],
            },
            {
                "run_id": "run-3",
                "generated_at": "2026-04-03T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {"item_id": "target-b", "repo": "RepoB", "title": "Drift B", "lane": "urgent"},
                    "primary_target_confidence_label": "high",
                },
                "operator_queue": [
                    {"item_id": "target-a", "repo": "RepoA", "title": "Drift A", "lane": "ready"},
                    {"item_id": "target-b", "repo": "RepoB", "title": "Drift B", "lane": "urgent"},
                ],
            },
            {
                "run_id": "run-2",
                "generated_at": "2026-04-02T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {"item_id": "target-b", "repo": "RepoB", "title": "Drift B", "lane": "urgent"},
                    "primary_target_confidence_label": "high",
                },
                "operator_queue": [
                    {"item_id": "target-a", "repo": "RepoA", "title": "Drift A", "lane": "urgent"},
                    {"item_id": "target-b", "repo": "RepoB", "title": "Drift B", "lane": "urgent"},
                ],
            },
            {
                "run_id": "run-1",
                "generated_at": "2026-04-01T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {"item_id": "target-a", "repo": "RepoA", "title": "Drift A", "lane": "blocked"},
                    "primary_target_confidence_label": "medium",
                },
                "operator_queue": [{"item_id": "target-a", "repo": "RepoA", "title": "Drift A", "lane": "blocked"}],
            },
        ],
    )

    snapshot = build_operator_snapshot(_make_report(), output_dir=tmp_path)
    summary = snapshot["operator_summary"]

    assert summary["partially_validated_recommendation_count"] >= 1
    assert any(
        item["outcome"] == "partially_validated"
        for item in summary["recent_validation_outcomes"]
    )


def test_operator_snapshot_healthy_calibration_boosts_urgent_confidence(tmp_path: Path, monkeypatch):
    report = _make_report(
        preflight_summary={},
        material_changes=[
            {
                "change_key": "high-1",
                "change_type": "security-change",
                "repo_name": "RepoC",
                "severity": 0.9,
                "title": "RepoC security posture changed",
                "summary": "critical -> watch",
                "recommended_next_step": "Review RepoC security posture changed now.",
            }
        ],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
    )
    monkeypatch.setattr("src.operator_control_center.load_operator_state_history", lambda *_args, **_kwargs: [])

    monkeypatch.setattr(
        "src.operator_control_center._build_confidence_calibration",
        lambda _history: {
            "confidence_validation_status": "healthy",
            "confidence_window_runs": 8,
            "validated_recommendation_count": 4,
            "partially_validated_recommendation_count": 1,
            "unresolved_recommendation_count": 1,
            "reopened_recommendation_count": 0,
            "insufficient_future_runs_count": 2,
            "high_confidence_hit_rate": 0.75,
            "medium_confidence_hit_rate": 0.5,
            "low_confidence_caution_rate": 1.0,
            "recent_validation_outcomes": [],
            "confidence_calibration_summary": "Recent high-confidence recommendations are validating well.",
        },
    )
    healthy_snapshot = build_operator_snapshot(report, output_dir=tmp_path)

    monkeypatch.setattr(
        "src.operator_control_center._build_confidence_calibration",
        lambda _history: {
            "confidence_validation_status": "mixed",
            "confidence_window_runs": 8,
            "validated_recommendation_count": 2,
            "partially_validated_recommendation_count": 1,
            "unresolved_recommendation_count": 1,
            "reopened_recommendation_count": 1,
            "insufficient_future_runs_count": 2,
            "high_confidence_hit_rate": 0.5,
            "medium_confidence_hit_rate": 0.67,
            "low_confidence_caution_rate": 1.0,
            "recent_validation_outcomes": [],
            "confidence_calibration_summary": "Confidence is still useful, but recent outcomes are mixed.",
        },
    )
    mixed_snapshot = build_operator_snapshot(report, output_dir=tmp_path)

    assert healthy_snapshot["operator_summary"]["confidence_validation_status"] == "healthy"
    assert mixed_snapshot["operator_summary"]["confidence_validation_status"] == "mixed"
    assert (
        healthy_snapshot["operator_summary"]["primary_target_confidence_score"]
        == mixed_snapshot["operator_summary"]["primary_target_confidence_score"] + 0.05
    )


def test_operator_snapshot_uses_verify_first_for_noisy_reopened_targets(tmp_path: Path, monkeypatch):
    report = _make_report(
        preflight_summary={},
        material_changes=[
            {
                "change_key": "high-1",
                "change_type": "security-change",
                "repo_name": "RepoC",
                "severity": 0.9,
                "title": "RepoC security posture changed",
                "summary": "critical -> watch",
                "recommended_next_step": "Review RepoC security posture changed now.",
            }
        ],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
    )
    monkeypatch.setattr(
        "src.operator_control_center.load_operator_state_history",
        lambda *_args, **_kwargs: [
            {"operator_summary": {"counts": {"blocked": 0, "urgent": 0, "ready": 0, "deferred": 0}}, "operator_queue": []},
            {
                "operator_summary": {"counts": {"blocked": 0, "urgent": 1, "ready": 0, "deferred": 0}},
                    "operator_queue": [
                        {
                            "lane": "urgent",
                            "priority": 90,
                            "repo": "RepoC",
                            "title": "RepoC security posture changed",
                            "age_days": 2,
                    }
                ],
            },
        ],
    )
    monkeypatch.setattr(
        "src.operator_control_center._build_confidence_calibration",
        lambda _history: {
            "confidence_validation_status": "noisy",
            "confidence_window_runs": 8,
            "validated_recommendation_count": 1,
            "partially_validated_recommendation_count": 1,
            "unresolved_recommendation_count": 2,
            "reopened_recommendation_count": 2,
            "insufficient_future_runs_count": 1,
            "high_confidence_hit_rate": 0.4,
            "medium_confidence_hit_rate": 0.5,
            "low_confidence_caution_rate": 1.0,
            "recent_validation_outcomes": [],
            "confidence_calibration_summary": "Recent high-confidence guidance has missed often enough that operators should verify before overcommitting.",
        },
    )
    monkeypatch.setattr("src.operator_control_center._was_resolved_then_reopened", lambda *_args, **_kwargs: True)

    snapshot = build_operator_snapshot(report, output_dir=tmp_path)
    summary = snapshot["operator_summary"]

    assert summary["confidence_validation_status"] == "noisy"
    assert summary["decision_memory_status"] == "reopened"
    assert summary["primary_target_trust_policy"] == "verify-first"
    assert summary["next_action_trust_policy"] == "verify-first"
    assert summary["what_to_do_next"].startswith("Verify before acting:")


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
