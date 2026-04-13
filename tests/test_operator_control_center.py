from __future__ import annotations

from pathlib import Path

import src.operator_control_center as operator_control_center
from src.operator_control_center import build_operator_snapshot, normalize_review_state, render_control_center_markdown


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


def test_operator_snapshot_treats_project_mirror_drift_as_campaign_drift(tmp_path: Path):
    snapshot = build_operator_snapshot(
        _make_report(
            managed_state_drift=[
                {
                    "action_id": "campaign-1",
                    "repo_full_name": "user/RepoD",
                    "target": "github-project-item",
                    "drift_state": "managed-project-item-missing",
                }
            ]
        ),
        output_dir=tmp_path,
    )

    project_item = next(item for item in snapshot["operator_queue"] if item["repo"] == "RepoD")
    assert project_item["title"] == "RepoD drift needs review"
    assert project_item["lane"] == "urgent"


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
    assert summary["primary_target_exception_status"] == "none"
    assert summary["recommendation_drift_status"] == "stable"
    assert summary["primary_target_recovery_confidence_label"] in {"low", "medium", "high"}
    assert "recovery confidence" in summary["recovery_confidence_summary"].lower()
    assert summary["primary_target_exception_retirement_status"] in {"none", "candidate", "blocked", "retired"}
    assert summary["primary_target_policy_debt_status"] in {"none", "watch", "class-debt", "one-off-noise"}
    assert summary["primary_target_class_normalization_status"] in {"none", "candidate", "applied", "blocked"}
    assert summary["primary_target_class_memory_freshness_status"] in {"fresh", "mixed-age", "stale", "insufficient-data"}
    assert summary["primary_target_class_decay_status"] in {"none", "normalization-decayed", "policy-debt-decayed", "blocked"}
    assert summary["primary_target_class_trust_reweight_direction"] in {"supporting-normalization", "neutral", "supporting-caution"}
    assert -0.95 <= summary["primary_target_class_trust_reweight_score"] <= 0.95
    assert 0.0 <= summary["primary_target_weighted_class_support_score"] <= 0.95
    assert 0.0 <= summary["primary_target_weighted_class_caution_score"] <= 0.95
    assert summary["primary_target_class_trust_momentum_status"] in {
        "sustained-support",
        "sustained-caution",
        "building",
        "reversing",
        "unstable",
        "insufficient-data",
    }
    assert summary["primary_target_class_reweight_stability_status"] in {"stable", "watch", "oscillating"}
    assert summary["primary_target_class_reweight_transition_status"] in {
        "none",
        "pending-support",
        "pending-caution",
        "confirmed-support",
        "confirmed-caution",
        "blocked",
    }
    assert summary["primary_target_class_transition_health_status"] in {
        "building",
        "holding",
        "stalled",
        "expired",
        "blocked",
        "none",
    }
    assert summary["primary_target_class_transition_resolution_status"] in {
        "none",
        "confirmed",
        "cleared",
        "expired",
        "blocked",
    }
    assert summary["primary_target_transition_closure_confidence_label"] in {"high", "medium", "low"}
    assert summary["primary_target_transition_closure_likely_outcome"] in {
        "none",
        "confirm-soon",
        "hold",
        "clear-risk",
        "expire-risk",
        "blocked",
        "insufficient-data",
    }
    assert 0.05 <= summary["primary_target_transition_closure_confidence_score"] <= 0.95
    assert summary["primary_target_class_pending_debt_status"] in {
        "none",
        "watch",
        "active-debt",
        "clearing",
    }
    assert summary["primary_target_pending_debt_freshness_status"] in {
        "fresh",
        "mixed-age",
        "stale",
        "insufficient-data",
    }
    assert summary["primary_target_closure_forecast_reweight_direction"] in {
        "supporting-confirmation",
        "neutral",
        "supporting-clearance",
    }
    assert summary["primary_target_closure_forecast_momentum_status"] in {
        "sustained-confirmation",
        "sustained-clearance",
        "building",
        "reversing",
        "unstable",
        "insufficient-data",
    }
    assert summary["primary_target_closure_forecast_stability_status"] in {
        "stable",
        "watch",
        "oscillating",
    }
    assert summary["primary_target_closure_forecast_hysteresis_status"] in {
        "none",
        "pending-confirmation",
        "pending-clearance",
        "confirmed-confirmation",
        "confirmed-clearance",
        "blocked",
    }
    assert summary["primary_target_closure_forecast_freshness_status"] in {
        "fresh",
        "mixed-age",
        "stale",
        "insufficient-data",
    }
    assert summary["primary_target_closure_forecast_decay_status"] in {
        "none",
        "confirmation-decayed",
        "clearance-decayed",
        "blocked",
    }
    assert summary["primary_target_closure_forecast_refresh_recovery_status"] in {
        "none",
        "recovering-confirmation",
        "recovering-clearance",
        "reacquiring-confirmation",
        "reacquiring-clearance",
        "reversing",
        "blocked",
    }
    assert summary["primary_target_closure_forecast_reacquisition_status"] in {
        "none",
        "pending-confirmation-reacquisition",
        "pending-clearance-reacquisition",
        "reacquired-confirmation",
        "reacquired-clearance",
        "blocked",
    }
    assert summary["primary_target_closure_forecast_reacquisition_persistence_status"] in {
        "none",
        "just-reacquired",
        "holding-confirmation",
        "holding-clearance",
        "sustained-confirmation",
        "sustained-clearance",
        "reversing",
        "insufficient-data",
    }
    assert summary["primary_target_closure_forecast_recovery_churn_status"] in {
        "none",
        "watch",
        "churn",
        "blocked",
    }
    assert summary["primary_target_closure_forecast_reacquisition_freshness_status"] in {
        "fresh",
        "mixed-age",
        "stale",
        "insufficient-data",
    }
    assert summary["primary_target_closure_forecast_persistence_reset_status"] in {
        "none",
        "confirmation-softened",
        "clearance-softened",
        "confirmation-reset",
        "clearance-reset",
        "blocked",
    }
    assert summary["primary_target_closure_forecast_reset_refresh_recovery_status"] in {
        "none",
        "recovering-confirmation-reset",
        "recovering-clearance-reset",
        "reentering-confirmation",
        "reentering-clearance",
        "reversing",
        "blocked",
    }
    assert summary["primary_target_closure_forecast_reset_reentry_status"] in {
        "none",
        "pending-confirmation-reentry",
        "pending-clearance-reentry",
        "reentered-confirmation",
        "reentered-clearance",
        "blocked",
    }
    assert summary["primary_target_closure_forecast_reset_reentry_persistence_status"] in {
        "none",
        "just-reentered",
        "holding-confirmation-reentry",
        "holding-clearance-reentry",
        "sustained-confirmation-reentry",
        "sustained-clearance-reentry",
        "reversing",
        "insufficient-data",
    }
    assert summary["primary_target_closure_forecast_reset_reentry_churn_status"] in {
        "none",
        "watch",
        "churn",
        "blocked",
    }
    assert summary["primary_target_closure_forecast_reset_reentry_freshness_status"] in {
        "fresh",
        "mixed-age",
        "stale",
        "insufficient-data",
    }
    assert summary["primary_target_closure_forecast_reset_reentry_reset_status"] in {
        "none",
        "confirmation-softened",
        "clearance-softened",
        "confirmation-reset",
        "clearance-reset",
        "blocked",
    }
    assert summary["primary_target_closure_forecast_reset_reentry_refresh_recovery_status"] in {
        "none",
        "recovering-confirmation-reentry-reset",
        "recovering-clearance-reentry-reset",
        "rebuilding-confirmation-reentry",
        "rebuilding-clearance-reentry",
        "reversing",
        "blocked",
    }
    assert summary["primary_target_closure_forecast_reset_reentry_rebuild_status"] in {
        "none",
        "pending-confirmation-rebuild",
        "pending-clearance-rebuild",
        "rebuilt-confirmation-reentry",
        "rebuilt-clearance-reentry",
        "blocked",
    }
    assert summary["primary_target_closure_forecast_reset_reentry_rebuild_persistence_status"] in {
        "none",
        "just-rebuilt",
        "holding-confirmation-rebuild",
        "holding-clearance-rebuild",
        "sustained-confirmation-rebuild",
        "sustained-clearance-rebuild",
        "reversing",
        "insufficient-data",
    }
    assert summary["primary_target_closure_forecast_reset_reentry_rebuild_churn_status"] in {
        "none",
        "watch",
        "churn",
        "blocked",
    }
    assert summary["primary_target_closure_forecast_reset_reentry_rebuild_freshness_status"] in {
        "fresh",
        "mixed-age",
        "stale",
        "insufficient-data",
    }
    assert summary["primary_target_closure_forecast_reset_reentry_rebuild_reset_status"] in {
        "none",
        "confirmation-softened",
        "clearance-softened",
        "confirmation-reset",
        "clearance-reset",
        "blocked",
    }
    assert summary["primary_target_closure_forecast_reset_reentry_rebuild_refresh_recovery_status"] in {
        "none",
        "recovering-confirmation-rebuild-reset",
        "recovering-clearance-rebuild-reset",
        "reentering-confirmation-rebuild",
        "reentering-clearance-rebuild",
        "reversing",
        "blocked",
    }
    assert summary["primary_target_closure_forecast_reset_reentry_rebuild_reentry_status"] in {
        "none",
        "pending-confirmation-rebuild-reentry",
        "pending-clearance-rebuild-reentry",
        "reentered-confirmation-rebuild",
        "reentered-clearance-rebuild",
        "blocked",
    }
    assert summary["primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_status"] in {
        "none",
        "just-reentered",
        "holding-confirmation-rebuild-reentry",
        "holding-clearance-rebuild-reentry",
        "sustained-confirmation-rebuild-reentry",
        "sustained-clearance-rebuild-reentry",
        "reversing",
        "insufficient-data",
    }
    assert summary["primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_status"] in {
        "none",
        "watch",
        "churn",
        "blocked",
    }
    assert summary["primary_target_closure_forecast_reset_reentry_rebuild_reentry_freshness_status"] in {
        "fresh",
        "mixed-age",
        "stale",
        "insufficient-data",
    }
    assert summary["primary_target_closure_forecast_reset_reentry_rebuild_reentry_reset_status"] in {
        "none",
        "confirmation-softened",
        "clearance-softened",
        "confirmation-reset",
        "clearance-reset",
        "blocked",
    }
    assert summary["primary_target_closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status"] in {
        "none",
        "recovering-confirmation-rebuild-reentry-reset",
        "recovering-clearance-rebuild-reentry-reset",
        "restoring-confirmation-rebuild-reentry",
        "restoring-clearance-rebuild-reentry",
        "reversing",
        "blocked",
    }
    assert summary["primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_status"] in {
        "none",
        "pending-confirmation-rebuild-reentry-restore",
        "pending-clearance-rebuild-reentry-restore",
        "restored-confirmation-rebuild-reentry",
        "restored-clearance-rebuild-reentry",
        "blocked",
    }
    assert summary["primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_status"] in {
        "fresh",
        "mixed-age",
        "stale",
        "insufficient-data",
    }
    assert summary["primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reset_status"] in {
        "none",
        "confirmation-softened",
        "clearance-softened",
        "confirmation-reset",
        "clearance-reset",
        "blocked",
    }
    assert summary[
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_status"
    ] in {
        "none",
        "recovering-confirmation-rebuild-reentry-restore-reset",
        "recovering-clearance-rebuild-reentry-restore-reset",
        "rerestoring-confirmation-rebuild-reentry",
        "rerestoring-clearance-rebuild-reentry",
        "reversing",
        "blocked",
    }
    assert summary[
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status"
    ] in {
        "none",
        "pending-confirmation-rebuild-reentry-rerestore",
        "pending-clearance-rebuild-reentry-rerestore",
        "rerestored-confirmation-rebuild-reentry",
        "rerestored-clearance-rebuild-reentry",
        "blocked",
    }
    assert summary[
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_status"
    ] in {
        "none",
        "just-rerestored",
        "holding-confirmation-rebuild-reentry-rerestore",
        "holding-clearance-rebuild-reentry-rerestore",
        "sustained-confirmation-rebuild-reentry-rerestore",
        "sustained-clearance-rebuild-reentry-rerestore",
        "reversing",
        "insufficient-data",
    }
    assert summary[
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_status"
    ] in {
        "none",
        "watch",
        "churn",
        "blocked",
    }
    assert summary[
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status"
    ] in {
        "fresh",
        "mixed-age",
        "stale",
        "insufficient-data",
    }
    assert summary[
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_status"
    ] in {
        "none",
        "confirmation-softened",
        "clearance-softened",
        "confirmation-reset",
        "clearance-reset",
        "blocked",
    }
    assert summary[
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_status"
    ] in {
        "none",
        "recovering-confirmation-rebuild-reentry-rerestore-reset",
        "recovering-clearance-rebuild-reentry-rerestore-reset",
        "rererestoring-confirmation-rebuild-reentry",
        "rererestoring-clearance-rebuild-reentry",
        "reversing",
        "blocked",
    }
    assert summary[
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status"
    ] in {
        "none",
        "pending-confirmation-rebuild-reentry-rererestore",
        "pending-clearance-rebuild-reentry-rererestore",
        "rererestored-confirmation-rebuild-reentry",
        "rererestored-clearance-rebuild-reentry",
        "blocked",
    }
    assert summary[
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status"
    ] in {
        "none",
        "just-rererestored",
        "holding-confirmation-rebuild-reentry-rererestore",
        "holding-clearance-rebuild-reentry-rererestore",
        "sustained-confirmation-rebuild-reentry-rererestore",
        "sustained-clearance-rebuild-reentry-rererestore",
        "reversing",
        "insufficient-data",
    }
    assert summary[
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status"
    ] in {
        "none",
        "watch",
        "churn",
        "blocked",
    }
    assert summary[
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status"
    ] in {
        "fresh",
        "mixed-age",
        "stale",
        "insufficient-data",
    }
    assert summary[
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status"
    ] in {
        "none",
        "confirmation-softened",
        "clearance-softened",
        "confirmation-reset",
        "clearance-reset",
        "blocked",
    }
    assert summary[
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status"
    ] in {
        "none",
        "recovering-confirmation-rebuild-reentry-rererestore-reset",
        "recovering-clearance-rebuild-reentry-rererestore-reset",
        "rerererestoring-confirmation-rebuild-reentry",
        "rerererestoring-clearance-rebuild-reentry",
        "reversing",
        "blocked",
    }
    assert summary[
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status"
    ] in {
        "none",
        "pending-confirmation-rebuild-reentry-rerererestore",
        "pending-clearance-rebuild-reentry-rerererestore",
        "rerererestored-confirmation-rebuild-reentry",
        "rerererestored-clearance-rebuild-reentry",
        "blocked",
    }
    assert summary[
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status"
    ] in {
        "none",
        "just-rerererestored",
        "holding-confirmation-rebuild-reentry-rerererestore",
        "holding-clearance-rebuild-reentry-rerererestore",
        "sustained-confirmation-rebuild-reentry-rerererestore",
        "sustained-clearance-rebuild-reentry-rerererestore",
        "reversing",
        "insufficient-data",
    }
    assert summary[
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status"
    ] in {
        "none",
        "watch",
        "churn",
        "blocked",
    }
    assert summary["primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_status"] in {
        "none",
        "just-restored",
        "holding-confirmation-rebuild-reentry-restore",
        "holding-clearance-rebuild-reentry-restore",
        "sustained-confirmation-rebuild-reentry-restore",
        "sustained-clearance-rebuild-reentry-restore",
        "reversing",
        "insufficient-data",
    }
    assert summary["primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_churn_status"] in {
        "none",
        "watch",
        "churn",
        "blocked",
    }
    assert -0.95 <= summary["primary_target_closure_forecast_reweight_score"] <= 0.95
    assert -0.95 <= summary["primary_target_closure_forecast_momentum_score"] <= 0.95
    assert -0.95 <= summary["primary_target_closure_forecast_refresh_recovery_score"] <= 0.95
    assert -0.95 <= summary["primary_target_closure_forecast_reacquisition_persistence_score"] <= 0.95
    assert -0.95 <= summary["primary_target_closure_forecast_reset_refresh_recovery_score"] <= 0.95
    assert -0.95 <= summary["primary_target_closure_forecast_reset_reentry_persistence_score"] <= 0.95
    assert -0.95 <= summary["primary_target_closure_forecast_reset_reentry_refresh_recovery_score"] <= 0.95
    assert -0.95 <= summary["primary_target_closure_forecast_reset_reentry_rebuild_persistence_score"] <= 0.95
    assert -0.95 <= summary["primary_target_closure_forecast_reset_reentry_rebuild_refresh_recovery_score"] <= 0.95
    assert -0.95 <= summary["primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_score"] <= 0.95
    assert -0.95 <= summary["primary_target_closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_score"] <= 0.95
    assert -0.95 <= summary["primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_score"] <= 0.95
    assert -0.95 <= summary["primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_score"] <= 0.95
    assert -0.95 <= summary["primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_score"] <= 0.95
    assert -0.95 <= summary["primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score"] <= 0.95
    assert -0.95 <= summary["primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_score"] <= 0.95
    assert -0.95 <= summary["primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score"] <= 0.95
    assert 0.0 <= summary["primary_target_closure_forecast_recovery_churn_score"] <= 0.95
    assert 0.0 <= summary["primary_target_closure_forecast_reset_reentry_churn_score"] <= 0.95
    assert 0.0 <= summary["primary_target_closure_forecast_reset_reentry_rebuild_churn_score"] <= 0.95
    assert 0.0 <= summary["primary_target"]["decayed_rerestored_rebuild_reentry_confirmation_rate"] <= 1.0
    assert 0.0 <= summary["primary_target"]["decayed_rerestored_rebuild_reentry_clearance_rate"] <= 1.0
    assert 0.0 <= summary["primary_target"]["decayed_rererestored_rebuild_reentry_confirmation_rate"] <= 1.0
    assert 0.0 <= summary["primary_target"]["decayed_rererestored_rebuild_reentry_clearance_rate"] <= 1.0
    assert (
        summary["closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_decay_window_runs"]
        == 4
    )
    assert 0.0 <= summary["primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_score"] <= 0.95
    assert 0.0 <= summary["primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_churn_score"] <= 0.95
    assert 0.0 <= summary["primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_score"] <= 0.95
    assert 0.0 <= summary["primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_score"] <= 0.95
    assert 0.0 <= summary["primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score"] <= 0.95
    assert 0.0 <= summary["primary_target"]["decayed_confirmation_forecast_rate"] <= 1.0
    assert 0.0 <= summary["primary_target"]["decayed_clearance_forecast_rate"] <= 1.0
    assert 0.0 <= summary["primary_target"]["decayed_rebuilt_confirmation_reentry_rate"] <= 1.0
    assert 0.0 <= summary["primary_target"]["decayed_rebuilt_clearance_reentry_rate"] <= 1.0
    assert 0.0 <= summary["primary_target"]["decayed_restored_rebuild_reentry_confirmation_rate"] <= 1.0
    assert 0.0 <= summary["primary_target"]["decayed_restored_rebuild_reentry_clearance_rate"] <= 1.0
    assert 0.0 <= summary["primary_target_weighted_pending_resolution_support_score"] <= 0.95
    assert 0.0 <= summary["primary_target_weighted_pending_debt_caution_score"] <= 0.95
    assert summary["class_decay_window_runs"] == 4
    assert summary["closure_forecast_reset_reentry_rebuild_decay_window_runs"] == 4
    assert summary["closure_forecast_reset_reentry_rebuild_refresh_window_runs"] == 4
    assert summary["closure_forecast_reset_reentry_rebuild_reentry_window_runs"] == 4
    assert summary["closure_forecast_reset_reentry_rebuild_reentry_decay_window_runs"] == 4
    assert summary["closure_forecast_reset_reentry_rebuild_reentry_refresh_window_runs"] == 4
    assert summary["closure_forecast_reset_reentry_rebuild_reentry_restore_window_runs"] == 4
    assert summary["closure_forecast_reset_reentry_rebuild_reentry_restore_decay_window_runs"] == 4
    assert summary["closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_window_runs"] == 4
    assert summary["closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_window_runs"] == 4
    assert summary["closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_window_runs"] == 4
    assert summary["closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_window_runs"] == 4
    assert summary["closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_decay_window_runs"] == 4
    assert summary["closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_window_runs"] == 4
    assert summary["class_normalization_window_runs"] == 4
    assert summary["class_reweighting_window_runs"] == 4
    assert summary["class_transition_window_runs"] == 4
    assert summary["class_transition_age_window_runs"] == 4
    assert summary["transition_closure_window_runs"] == 4
    assert summary["class_pending_debt_window_runs"] == 10
    assert summary["pending_debt_decay_window_runs"] == 4
    assert summary["closure_forecast_reweighting_window_runs"] == 4
    assert summary["closure_forecast_transition_window_runs"] == 4
    assert summary["closure_forecast_decay_window_runs"] == 4
    assert summary["closure_forecast_refresh_window_runs"] == 4
    assert summary["closure_forecast_reacquisition_window_runs"] == 4
    assert summary["closure_forecast_reset_reentry_window_runs"] == 4
    assert summary["closure_forecast_reset_reentry_decay_window_runs"] == 4
    assert summary["closure_forecast_reset_reentry_refresh_window_runs"] == 4
    assert summary["closure_forecast_reset_reentry_rebuild_window_runs"] == 4
    assert "guidance" in summary["adaptive_confidence_summary"].lower() or "immediate action" in summary["adaptive_confidence_summary"].lower()
    assert summary["recommendation_quality_summary"].startswith("Strong recommendation because")


def test_operator_snapshot_attaches_portfolio_catalog_context(tmp_path: Path):
    report = _make_report(
        audits=[
            {
                "metadata": {"name": "RepoC", "archived": False},
                "completeness_tier": "functional",
                "portfolio_catalog": {
                    "has_explicit_entry": True,
                    "owner": "d",
                    "team": "operator-loop",
                    "purpose": "flagship queue item",
                    "lifecycle_state": "active",
                    "criticality": "high",
                    "review_cadence": "weekly",
                    "intended_disposition": "maintain",
                    "catalog_line": "operator-loop | flagship queue item | lifecycle active | criticality high | cadence weekly | disposition maintain",
                },
                "scorecard": {
                    "program": "maintain",
                    "program_label": "Maintain",
                    "maturity_level": "operating",
                    "target_maturity": "strong",
                    "status": "below-target",
                    "top_gaps": ["Testing", "CI"],
                    "summary": "Maintain is at Operating and still below the Strong target because testing and ci are behind.",
                },
            }
        ]
    )

    snapshot = build_operator_snapshot(report, output_dir=tmp_path)
    urgent_item = next(item for item in snapshot["operator_queue"] if item.get("repo") == "RepoC")
    markdown = render_control_center_markdown(snapshot, "testuser", "2026-03-29")

    assert urgent_item["catalog_line"].startswith("operator-loop | flagship queue item")
    assert urgent_item["intent_alignment"] == "needs-review"
    assert urgent_item["scorecard_line"] == "Scorecard: Maintain — Operating (target Strong)"
    assert urgent_item["maturity_gap_summary"] == "testing, ci are still below the maintain bar."
    assert "Catalog: operator-loop | flagship queue item" in markdown
    assert "Intent Alignment: needs-review" in markdown
    assert "Scorecard: Maintain — Operating (target Strong)" in markdown
    assert "Maturity Gap: testing, ci are still below the maintain bar." in markdown


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
    assert summary["follow_through_checkpoint_counts"]["overdue"] >= 1
    assert summary["follow_through_escalation_counts"]["escalate-now"] >= 1
    assert summary["persisting_attention_count"] >= 1
    assert summary["trend_status"] == "worsening"


def test_project_queue_follow_through_marks_overdue_untouched_items_for_escalation():
    queue = [
        {
            "item_id": "campaign-drift:campaign-1:github-issue",
            "lane": "urgent",
            "age_days": 8,
            "repo": "RepoD",
            "title": "RepoD drift needs review",
            "summary": "Drift is still open.",
            "recommended_action": "Inspect the managed issue.",
            "source_run_id": "testuser:2026-03-29T12:00:00+00:00",
        }
    ]
    key = operator_control_center._queue_identity(queue[0])
    recent_runs = [
        {"items": {key: queue[0]}, "has_attention": True},
        {"items": {key: {"lane": "urgent", "age_days": 7}}, "has_attention": True},
        {"items": {key: {"lane": "urgent", "age_days": 6}}, "has_attention": True},
    ]
    resolution_trend = {
        "decision_memory_map": {
            key: {
                "decision_memory_status": "persisting",
                "last_seen_at": "2026-03-29T12:00:00+00:00",
                "last_outcome": "no-change",
            }
        }
    }

    enriched = operator_control_center._project_queue_follow_through(
        queue,
        recent_runs=recent_runs,
        resolution_trend=resolution_trend,
        current_generated_at="2026-03-29T12:00:00+00:00",
    )

    item = enriched[0]
    assert item["follow_through_status"] == "stale-follow-through"
    assert item["follow_through_age_runs"] == 3
    assert item["follow_through_checkpoint_status"] == "overdue"
    assert item["follow_through_escalation_status"] == "escalate-now"
    assert "resurfaced now" in item["follow_through_escalation_summary"]


def test_project_queue_follow_through_keeps_recent_waiting_items_on_watch():
    queue = [
        {
            "item_id": "campaign-drift:campaign-1:github-issue",
            "lane": "urgent",
            "age_days": 1,
            "repo": "RepoD",
            "title": "RepoD drift needs review",
            "summary": "Drift is still open.",
            "recommended_action": "Inspect the managed issue.",
            "source_run_id": "testuser:2026-03-29T12:00:00+00:00",
        }
    ]
    key = operator_control_center._queue_identity(queue[0])
    recent_runs = [{"items": {key: queue[0]}, "has_attention": True}]
    resolution_trend = {
        "decision_memory_map": {
            key: {
                "decision_memory_status": "attempted",
                "last_seen_at": "2026-03-29T12:00:00+00:00",
                "last_outcome": "no-change",
                "last_intervention": {
                    "recorded_at": "2026-03-29T10:00:00+00:00",
                    "event_type": "issue-updated",
                    "outcome": "no-change",
                    "title": "RepoD drift needs review",
                },
            }
        }
    }

    enriched = operator_control_center._project_queue_follow_through(
        queue,
        recent_runs=recent_runs,
        resolution_trend=resolution_trend,
        current_generated_at="2026-03-29T12:00:00+00:00",
    )

    item = enriched[0]
    assert item["follow_through_status"] == "waiting-on-evidence"
    assert item["follow_through_checkpoint_status"] == "due-soon"
    assert item["follow_through_escalation_status"] == "watch"
    assert "stay on watch" in item["follow_through_escalation_reason"]


def test_project_queue_follow_through_marks_calmer_post_escalation_items_as_recovering():
    queue = [
        {
            "item_id": "campaign-drift:campaign-1:github-issue",
            "lane": "urgent",
            "age_days": 1,
            "repo": "RepoD",
            "title": "RepoD drift needs review",
            "summary": "Drift is still open.",
            "recommended_action": "Inspect the managed issue.",
            "source_run_id": "testuser:2026-03-29T12:00:00+00:00",
        }
    ]
    key = operator_control_center._queue_identity(queue[0])
    recent_runs = [
        {"items": {key: queue[0]}, "has_attention": True},
        {
            "items": {
                    key: {
                        "lane": "urgent",
                        "age_days": 6,
                        "follow_through_status": "stale-follow-through",
                        "follow_through_checkpoint_status": "overdue",
                        "follow_through_escalation_status": "escalate-now",
                }
            },
            "has_attention": True,
        },
    ]
    resolution_trend = {
        "decision_memory_map": {
            key: {
                "decision_memory_status": "attempted",
                "last_seen_at": "2026-03-29T12:00:00+00:00",
                "last_outcome": "no-change",
                "last_intervention": {
                    "recorded_at": "2026-03-29T10:00:00+00:00",
                    "event_type": "issue-updated",
                    "outcome": "no-change",
                    "title": "RepoD drift needs review",
                },
            }
        }
    }

    enriched = operator_control_center._project_queue_follow_through(
        queue,
        recent_runs=recent_runs,
        resolution_trend=resolution_trend,
        current_generated_at="2026-03-29T12:00:00+00:00",
    )

    item = enriched[0]
    assert item["follow_through_recovery_status"] == "recovering"
    assert item["follow_through_recovery_age_runs"] == 1
    assert "recovering from recent escalation" in item["follow_through_recovery_summary"]
    assert item["follow_through_recovery_persistence_status"] == "just-recovering"
    assert item["follow_through_relapse_churn_status"] == "blocked"


def test_project_queue_follow_through_marks_one_quiet_run_as_retiring_watch():
    queue = [
        {
            "item_id": "campaign-drift:campaign-1:github-issue",
            "lane": "deferred",
            "age_days": 0,
            "repo": "RepoD",
            "title": "RepoD drift needs review",
            "summary": "Drift has quieted.",
            "recommended_action": "Keep watching the managed issue.",
            "source_run_id": "testuser:2026-03-29T12:00:00+00:00",
        }
    ]
    key = operator_control_center._queue_identity(queue[0])
    recent_runs = [
        {"items": {key: queue[0]}, "has_attention": False},
        {
            "items": {
                key: {
                    "lane": "urgent",
                    "age_days": 6,
                    "follow_through_status": "stale-follow-through",
                    "follow_through_checkpoint_status": "overdue",
                    "follow_through_escalation_status": "escalate-now",
                }
            },
            "has_attention": True,
        },
    ]
    resolution_trend = {
        "decision_memory_map": {
            key: {
                "decision_memory_status": "attempted",
                "last_seen_at": "2026-03-29T12:00:00+00:00",
                "last_outcome": "improved",
                "last_intervention": {
                    "recorded_at": "2026-03-29T11:00:00+00:00",
                    "event_type": "issue-updated",
                    "outcome": "improved",
                    "title": "RepoD drift needs review",
                },
            }
        }
    }

    enriched = operator_control_center._project_queue_follow_through(
        queue,
        recent_runs=recent_runs,
        resolution_trend=resolution_trend,
        current_generated_at="2026-03-29T12:00:00+00:00",
    )

    item = enriched[0]
    assert item["follow_through_status"] == "resolved"
    assert item["follow_through_recovery_status"] == "retiring-watch"
    assert "one more quiet run" in item["follow_through_recovery_summary"]
    assert item["follow_through_recovery_persistence_status"] == "holding-retiring-watch"
    assert item["follow_through_relapse_churn_status"] == "none"


def test_project_queue_follow_through_marks_two_quiet_runs_as_retired():
    queue = [
        {
            "item_id": "campaign-drift:campaign-1:github-issue",
            "lane": "deferred",
            "age_days": 0,
            "repo": "RepoD",
            "title": "RepoD drift needs review",
            "summary": "Drift has quieted.",
            "recommended_action": "Keep watching the managed issue.",
            "source_run_id": "testuser:2026-03-30T12:00:00+00:00",
        }
    ]
    key = operator_control_center._queue_identity(queue[0])
    recent_runs = [
        {"items": {key: queue[0]}, "has_attention": False},
        {
            "items": {
                key: {
                    "lane": "deferred",
                    "age_days": 0,
                    "follow_through_status": "resolved",
                    "follow_through_checkpoint_status": "satisfied",
                    "follow_through_escalation_status": "resolved-watch",
                }
            },
            "has_attention": False,
        },
        {
            "items": {
                key: {
                    "lane": "urgent",
                    "age_days": 7,
                    "follow_through_status": "stale-follow-through",
                    "follow_through_checkpoint_status": "overdue",
                    "follow_through_escalation_status": "escalate-now",
                }
            },
            "has_attention": True,
        },
    ]
    resolution_trend = {
        "decision_memory_map": {
            key: {
                "decision_memory_status": "attempted",
                "last_seen_at": "2026-03-30T12:00:00+00:00",
                "last_outcome": "improved",
                "last_intervention": {
                    "recorded_at": "2026-03-30T11:00:00+00:00",
                    "event_type": "issue-updated",
                    "outcome": "improved",
                    "title": "RepoD drift needs review",
                },
            }
        }
    }

    enriched = operator_control_center._project_queue_follow_through(
        queue,
        recent_runs=recent_runs,
        resolution_trend=resolution_trend,
        current_generated_at="2026-03-30T12:00:00+00:00",
    )

    item = enriched[0]
    assert item["follow_through_recovery_status"] == "retired"
    assert item["follow_through_recovery_age_runs"] == 2
    assert "retired its recent escalation" in item["follow_through_recovery_summary"]
    assert item["follow_through_recovery_persistence_status"] == "sustained-retiring-watch"
    assert item["follow_through_relapse_churn_status"] == "none"


def test_project_queue_follow_through_marks_relapses_after_quiet_runs():
    queue = [
        {
            "item_id": "campaign-drift:campaign-1:github-issue",
            "lane": "urgent",
            "age_days": 8,
            "repo": "RepoD",
            "title": "RepoD drift needs review",
            "summary": "Drift reopened.",
            "recommended_action": "Inspect the managed issue again.",
            "source_run_id": "testuser:2026-03-31T12:00:00+00:00",
        }
    ]
    key = operator_control_center._queue_identity(queue[0])
    recent_runs = [
        {"items": {key: queue[0]}, "has_attention": True},
        {
            "items": {
                key: {
                    "lane": "deferred",
                    "age_days": 0,
                    "follow_through_status": "resolved",
                    "follow_through_checkpoint_status": "satisfied",
                    "follow_through_escalation_status": "resolved-watch",
                }
            },
            "has_attention": False,
        },
        {
            "items": {
                key: {
                    "lane": "urgent",
                    "age_days": 7,
                    "follow_through_status": "stale-follow-through",
                    "follow_through_checkpoint_status": "overdue",
                    "follow_through_escalation_status": "escalate-now",
                }
            },
            "has_attention": True,
        },
    ]
    resolution_trend = {
        "decision_memory_map": {
            key: {
                "decision_memory_status": "persisting",
                "last_seen_at": "2026-03-31T12:00:00+00:00",
                "last_outcome": "no-change",
            }
        }
    }

    enriched = operator_control_center._project_queue_follow_through(
        queue,
        recent_runs=recent_runs,
        resolution_trend=resolution_trend,
        current_generated_at="2026-03-31T12:00:00+00:00",
    )

    item = enriched[0]
    assert item["follow_through_recovery_status"] == "relapsing"
    assert "counts as a relapse" in item["follow_through_recovery_reason"]
    assert item["follow_through_recovery_persistence_status"] == "none"
    assert item["follow_through_relapse_churn_status"] == "fragile"


def test_project_queue_follow_through_marks_multi_run_retired_states_as_sustained_retired():
    queue = [
        {
            "item_id": "campaign-drift:campaign-1:github-issue",
            "lane": "deferred",
            "age_days": 0,
            "repo": "RepoD",
            "title": "RepoD drift needs review",
            "summary": "Drift has stayed quiet.",
            "recommended_action": "Keep watching the managed issue.",
            "source_run_id": "testuser:2026-03-31T12:00:00+00:00",
        }
    ]
    key = operator_control_center._queue_identity(queue[0])
    recent_runs = [
        {"items": {key: queue[0]}, "has_attention": False},
        {
            "items": {
                key: {
                    "lane": "deferred",
                    "age_days": 0,
                    "follow_through_status": "resolved",
                    "follow_through_checkpoint_status": "satisfied",
                    "follow_through_escalation_status": "resolved-watch",
                    "follow_through_recovery_status": "retired",
                }
            },
            "has_attention": False,
        },
        {
            "items": {
                key: {
                    "lane": "deferred",
                    "age_days": 0,
                    "follow_through_status": "resolved",
                    "follow_through_checkpoint_status": "satisfied",
                    "follow_through_escalation_status": "resolved-watch",
                    "follow_through_recovery_status": "retired",
                }
            },
            "has_attention": False,
        },
        {
            "items": {
                key: {
                    "lane": "urgent",
                    "age_days": 7,
                    "follow_through_status": "stale-follow-through",
                    "follow_through_checkpoint_status": "overdue",
                    "follow_through_escalation_status": "escalate-now",
                }
            },
            "has_attention": True,
        },
    ]
    resolution_trend = {
        "decision_memory_map": {
            key: {
                "decision_memory_status": "attempted",
                "last_seen_at": "2026-03-31T12:00:00+00:00",
                "last_outcome": "improved",
                "last_intervention": {
                    "recorded_at": "2026-03-31T11:00:00+00:00",
                    "event_type": "issue-updated",
                    "outcome": "improved",
                    "title": "RepoD drift needs review",
                },
            }
        }
    }

    enriched = operator_control_center._project_queue_follow_through(
        queue,
        recent_runs=recent_runs,
        resolution_trend=resolution_trend,
        current_generated_at="2026-03-31T12:00:00+00:00",
    )

    item = enriched[0]
    assert item["follow_through_recovery_status"] == "retired"
    assert item["follow_through_recovery_persistence_status"] == "sustained-retired"
    assert item["follow_through_recovery_persistence_age_runs"] == 3
    assert item["follow_through_relapse_churn_status"] == "none"


def test_project_queue_follow_through_marks_repeated_recovery_flips_as_churn():
    queue = [
        {
            "item_id": "campaign-drift:campaign-1:github-issue",
            "lane": "urgent",
            "age_days": 1,
            "repo": "RepoD",
            "title": "RepoD drift needs review",
            "summary": "Drift is still open.",
            "recommended_action": "Inspect the managed issue again.",
            "source_run_id": "testuser:2026-03-31T12:00:00+00:00",
        }
    ]
    key = operator_control_center._queue_identity(queue[0])
    recent_runs = [
        {"items": {key: queue[0]}, "has_attention": True},
        {
            "items": {
                key: {
                    "lane": "deferred",
                    "age_days": 0,
                    "follow_through_status": "resolved",
                    "follow_through_checkpoint_status": "satisfied",
                    "follow_through_escalation_status": "resolved-watch",
                    "follow_through_recovery_status": "retiring-watch",
                }
            },
            "has_attention": False,
        },
        {
            "items": {
                key: {
                    "lane": "urgent",
                    "age_days": 7,
                    "follow_through_status": "stale-follow-through",
                    "follow_through_checkpoint_status": "overdue",
                    "follow_through_escalation_status": "escalate-now",
                }
            },
            "has_attention": True,
        },
        {
            "items": {
                key: {
                    "lane": "deferred",
                    "age_days": 0,
                    "follow_through_status": "resolved",
                    "follow_through_checkpoint_status": "satisfied",
                    "follow_through_escalation_status": "resolved-watch",
                    "follow_through_recovery_status": "retiring-watch",
                }
            },
            "has_attention": False,
        },
        {
            "items": {
                key: {
                    "lane": "urgent",
                    "age_days": 7,
                    "follow_through_status": "stale-follow-through",
                    "follow_through_checkpoint_status": "overdue",
                    "follow_through_escalation_status": "escalate-now",
                }
            },
            "has_attention": True,
        },
    ]
    resolution_trend = {
        "decision_memory_map": {
            key: {
                "decision_memory_status": "attempted",
                "last_seen_at": "2026-03-31T12:00:00+00:00",
                "last_outcome": "no-change",
                "last_intervention": {
                    "recorded_at": "2026-03-31T10:00:00+00:00",
                    "event_type": "issue-updated",
                    "outcome": "no-change",
                    "title": "RepoD drift needs review",
                },
            }
        }
    }

    enriched = operator_control_center._project_queue_follow_through(
        queue,
        recent_runs=recent_runs,
        resolution_trend=resolution_trend,
        current_generated_at="2026-03-31T12:00:00+00:00",
    )

    item = enriched[0]
    assert item["follow_through_recovery_status"] == "relapsing"
    assert item["follow_through_relapse_churn_status"] == "churn"
    assert "churning between calmer and escalated states" in item["follow_through_relapse_churn_summary"]


def test_follow_through_reacquisition_durability_progresses_from_new_to_durable():
    item = {"repo": "RepoD", "title": "RepoD drift needs review"}

    age_runs, status, reason, summary = operator_control_center._follow_through_reacquisition_durability_projection(
        item,
        [],
        follow_through_recovery_reacquisition_status="just-reacquired",
        follow_through_relapse_churn_status="none",
        follow_through_recovery_freshness_status="fresh",
        follow_through_recovery_decay_status="none",
        follow_through_recovery_memory_reset_status="rebuilding",
    )
    assert age_runs == 1
    assert status == "just-reacquired"
    assert "too new to treat as durable" in reason
    assert "still needs more confirmation" in summary

    age_runs, status, reason, summary = operator_control_center._follow_through_reacquisition_durability_projection(
        item,
        [{"follow_through_recovery_reacquisition_status": "just-reacquired"}],
        follow_through_recovery_reacquisition_status="holding-reacquired",
        follow_through_relapse_churn_status="none",
        follow_through_recovery_freshness_status="fresh",
        follow_through_recovery_decay_status="none",
        follow_through_recovery_memory_reset_status="rebuilding",
    )
    assert age_runs == 2
    assert status == "consolidating"
    assert "still consolidating rather than stable" in reason
    assert "now consolidating it" in summary

    age_runs, status, reason, summary = operator_control_center._follow_through_reacquisition_durability_projection(
        item,
        [
            {"follow_through_recovery_reacquisition_durability_status": "holding-reacquired"},
            {"follow_through_recovery_reacquisition_durability_status": "holding-reacquired"},
        ],
        follow_through_recovery_reacquisition_status="reacquired",
        follow_through_relapse_churn_status="none",
        follow_through_recovery_freshness_status="holding-fresh",
        follow_through_recovery_decay_status="none",
        follow_through_recovery_memory_reset_status="rebuilding",
    )
    assert age_runs == 3
    assert status == "durable-reacquired"
    assert "durable enough to trust" in reason
    assert "durably re-established calmer posture" in summary


def test_follow_through_reacquisition_durability_softens_when_reacquisition_wobbles():
    item = {"repo": "RepoD", "title": "RepoD drift needs review"}

    age_runs, status, reason, summary = operator_control_center._follow_through_reacquisition_durability_projection(
        item,
        [{"follow_through_recovery_reacquisition_status": "holding-reacquired"}],
        follow_through_recovery_reacquisition_status="fragile-reacquisition",
        follow_through_relapse_churn_status="fragile",
        follow_through_recovery_freshness_status="mixed-age",
        follow_through_recovery_decay_status="softening",
        follow_through_recovery_memory_reset_status="reset-watch",
    )
    assert age_runs == 1
    assert status == "softening"
    assert "already softening under weaker freshness or wobble" in reason
    assert "already softening again" in summary


def test_follow_through_reacquisition_consolidation_tracks_holding_durable_and_reversing_states():
    item = {"repo": "RepoD", "title": "RepoD drift needs review"}

    status, reason, summary = operator_control_center._follow_through_reacquisition_consolidation_projection(
        item,
        [{"follow_through_recovery_reacquisition_durability_status": "holding-reacquired"}],
        follow_through_recovery_reacquisition_status="holding-reacquired",
        follow_through_recovery_reacquisition_durability_status="holding-reacquired",
        follow_through_relapse_churn_status="none",
        follow_through_recovery_freshness_status="fresh",
        follow_through_recovery_decay_status="none",
    )
    assert status == "holding-confidence"
    assert "restored confidence is now consolidating cleanly" in reason
    assert "restored calmer confidence is now holding" in summary

    status, reason, summary = operator_control_center._follow_through_reacquisition_consolidation_projection(
        item,
        [],
        follow_through_recovery_reacquisition_status="reacquired",
        follow_through_recovery_reacquisition_durability_status="durable-reacquired",
        follow_through_relapse_churn_status="none",
        follow_through_recovery_freshness_status="fresh",
        follow_through_recovery_decay_status="none",
    )
    assert status == "durable-confidence"
    assert "safely consolidated" in reason
    assert "now looks durable" in summary

    status, reason, summary = operator_control_center._follow_through_reacquisition_consolidation_projection(
        item,
        [{"follow_through_recovery_reacquisition_consolidation_status": "holding-confidence"}],
        follow_through_recovery_reacquisition_status="holding-reacquired",
        follow_through_recovery_reacquisition_durability_status="holding-reacquired",
        follow_through_relapse_churn_status="fragile",
        follow_through_recovery_freshness_status="mixed-age",
        follow_through_recovery_decay_status="softening",
    )
    assert status == "reversing"
    assert "already pushing that confidence back down" in reason
    assert "already reversing" in summary


def test_follow_through_revalidation_recovery_stays_under_revalidation_while_revalidation_is_active():
    age_runs, status, reason, summary = operator_control_center._follow_through_reacquisition_revalidation_recovery_projection(
        {"repo": "RepoD", "title": "RepoD drift needs review"},
        [],
        follow_through_recovery_reacquisition_status="reacquiring",
        follow_through_recovery_reacquisition_durability_status="consolidating",
        follow_through_recovery_reacquisition_consolidation_status="fragile-confidence",
        follow_through_reacquisition_softening_decay_status="revalidation-needed",
        follow_through_reacquisition_confidence_retirement_status="revalidation-needed",
        follow_through_recovery_freshness_status="fresh",
        follow_through_recovery_decay_status="none",
    )

    assert age_runs == 0
    assert status == "under-revalidation"
    assert "still in the revalidation window" in reason
    assert "still under revalidation" in summary


def test_follow_through_revalidation_recovery_marks_rebuilding_when_revalidation_clears_but_confidence_is_not_back():
    age_runs, status, reason, summary = operator_control_center._follow_through_reacquisition_revalidation_recovery_projection(
        {"repo": "RepoD", "title": "RepoD drift needs review"},
        [{"follow_through_reacquisition_confidence_retirement_status": "revalidation-needed"}],
        follow_through_recovery_reacquisition_status="reacquiring",
        follow_through_recovery_reacquisition_durability_status="consolidating",
        follow_through_recovery_reacquisition_consolidation_status="fragile-confidence",
        follow_through_reacquisition_softening_decay_status="none",
        follow_through_reacquisition_confidence_retirement_status="none",
        follow_through_recovery_freshness_status="fresh",
        follow_through_recovery_decay_status="none",
    )

    assert age_runs == 0
    assert status == "rebuilding-restored-confidence"
    assert "still rebuilding before confidence can be treated as re-earned" in reason
    assert "rebuilding restored confidence after revalidation" in summary


def test_follow_through_revalidation_recovery_marks_reearning_when_confidence_is_building_again():
    age_runs, status, reason, summary = operator_control_center._follow_through_reacquisition_revalidation_recovery_projection(
        {"repo": "RepoD", "title": "RepoD drift needs review"},
        [{"follow_through_reacquisition_confidence_retirement_status": "revalidation-needed"}],
        follow_through_recovery_reacquisition_status="reacquired",
        follow_through_recovery_reacquisition_durability_status="holding-reacquired",
        follow_through_recovery_reacquisition_consolidation_status="building-confidence",
        follow_through_reacquisition_softening_decay_status="none",
        follow_through_reacquisition_confidence_retirement_status="none",
        follow_through_recovery_freshness_status="holding-fresh",
        follow_through_recovery_decay_status="none",
    )

    assert age_runs == 0
    assert status == "reearning-confidence"
    assert "start re-earning confidence again" in reason
    assert "actively re-earning restored confidence" in summary


def test_follow_through_revalidation_recovery_marks_just_reearned_on_first_restored_confidence_run():
    age_runs, status, reason, summary = operator_control_center._follow_through_reacquisition_revalidation_recovery_projection(
        {"repo": "RepoD", "title": "RepoD drift needs review"},
        [{"follow_through_reacquisition_confidence_retirement_status": "revalidation-needed"}],
        follow_through_recovery_reacquisition_status="reacquired",
        follow_through_recovery_reacquisition_durability_status="durable-reacquired",
        follow_through_recovery_reacquisition_consolidation_status="holding-confidence",
        follow_through_reacquisition_softening_decay_status="none",
        follow_through_reacquisition_confidence_retirement_status="none",
        follow_through_recovery_freshness_status="holding-fresh",
        follow_through_recovery_decay_status="none",
    )

    assert age_runs == 1
    assert status == "just-reearned-confidence"
    assert "only just re-earned restored confidence" in reason
    assert "only just re-earned restored confidence" in summary


def test_follow_through_revalidation_recovery_marks_holding_reearned_after_confirming_run():
    age_runs, status, reason, summary = operator_control_center._follow_through_reacquisition_revalidation_recovery_projection(
        {"repo": "RepoD", "title": "RepoD drift needs review"},
        [
            {"follow_through_reacquisition_revalidation_recovery_status": "just-reearned-confidence"},
            {"follow_through_reacquisition_confidence_retirement_status": "revalidation-needed"},
        ],
        follow_through_recovery_reacquisition_status="reacquired",
        follow_through_recovery_reacquisition_durability_status="durable-reacquired",
        follow_through_recovery_reacquisition_consolidation_status="durable-confidence",
        follow_through_reacquisition_softening_decay_status="none",
        follow_through_reacquisition_confidence_retirement_status="none",
        follow_through_recovery_freshness_status="holding-fresh",
        follow_through_recovery_decay_status="none",
    )

    assert age_runs == 2
    assert status == "holding-reearned-confidence"
    assert "held re-earned restored confidence for 2 consecutive run(s)" in reason
    assert "holding re-earned restored confidence after revalidation" in summary


def test_follow_through_revalidation_recovery_falls_back_to_insufficient_evidence_when_history_is_thin():
    age_runs, status, reason, summary = operator_control_center._follow_through_reacquisition_revalidation_recovery_projection(
        {"repo": "RepoD", "title": "RepoD drift needs review"},
        [{"follow_through_reacquisition_softening_decay_status": "revalidation-needed"}],
        follow_through_recovery_reacquisition_status="reacquired",
        follow_through_recovery_reacquisition_durability_status="insufficient-evidence",
        follow_through_recovery_reacquisition_consolidation_status="insufficient-evidence",
        follow_through_reacquisition_softening_decay_status="none",
        follow_through_reacquisition_confidence_retirement_status="none",
        follow_through_recovery_freshness_status="mixed-age",
        follow_through_recovery_decay_status="aging",
    )

    assert age_runs == 0
    assert status == "insufficient-evidence"
    assert "not enough post-revalidation history yet" in reason
    assert "post-revalidation recovery evidence is still too thin" in summary


def test_follow_through_revalidation_recovery_summary_prioritizes_under_revalidation_hotspots():
    summary = operator_control_center._follow_through_reacquisition_revalidation_recovery_summary(
        {
            "under-revalidation": 2,
            "rebuilding-restored-confidence": 1,
            "reearning-confidence": 0,
            "just-reearned-confidence": 0,
            "holding-reearned-confidence": 0,
            "insufficient-evidence": 0,
        },
        [{"repo": "RepoC", "title": "RepoC drift needs review"}],
        [{"repo": "RepoD", "title": "RepoD drift needs review"}],
        [],
        [],
        [],
    )

    assert "2 restored-confidence path(s) are still under revalidation" in summary
    assert "RepoC: RepoC drift needs review" in summary


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


def test_operator_snapshot_softens_for_policy_flip_churn(tmp_path: Path, monkeypatch):
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
            {
                "generated_at": "2026-04-06T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-change:high-1",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_trust_policy": "act-with-review",
                    "decision_memory_status": "new",
                    "primary_target_last_outcome": "improved",
                },
                "operator_queue": [],
            },
            {
                "generated_at": "2026-04-05T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-change:high-1",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_trust_policy": "verify-first",
                    "decision_memory_status": "new",
                    "primary_target_last_outcome": "improved",
                },
                "operator_queue": [],
            },
            {
                "generated_at": "2026-04-04T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-change:high-1",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_trust_policy": "act-with-review",
                    "decision_memory_status": "new",
                    "primary_target_last_outcome": "improved",
                },
                "operator_queue": [],
            },
            {
                "generated_at": "2026-04-04T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-target:RepoC",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_closure_forecast_reweight_direction": "supporting-confirmation",
                    "primary_target_closure_forecast_reweight_score": 0.20,
                    "primary_target_closure_forecast_reacquisition_freshness_status": "fresh",
                    "primary_target_closure_forecast_persistence_reset_status": "confirmation-reset",
                    "primary_target_transition_closure_likely_outcome": "hold",
                },
                "operator_queue": [],
            },
            {
                "generated_at": "2026-04-04T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-target:RepoC",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_closure_forecast_reweight_direction": "supporting-confirmation",
                    "primary_target_closure_forecast_reweight_score": 0.20,
                    "primary_target_closure_forecast_reacquisition_freshness_status": "fresh",
                    "primary_target_closure_forecast_persistence_reset_status": "confirmation-reset",
                    "primary_target_transition_closure_likely_outcome": "hold",
                },
                "operator_queue": [],
            },
        ],
    )
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
    monkeypatch.setattr(
        "src.operator_control_center._trust_policy_exception_for_target",
        lambda target, *_args, **_kwargs: (
            "softened-for-flip-churn",
            "Recent trust-policy flips have been bouncing enough that this recommendation should not be treated as fully stable yet.",
            "verify-first",
            "Recent trust-policy churn means this target should be handled with a softer, verification-aware posture.",
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._trust_recovery_for_target",
        lambda target, *_args, **_kwargs: (
            "candidate",
            "This target is stabilizing under healthy calibration, but it has not held steady long enough to earn stronger trust yet.",
            "verify-first",
            "Recent trust-policy churn means this target should be handled with a softer, verification-aware posture.",
        ),
    )

    snapshot = build_operator_snapshot(report, output_dir=tmp_path)
    summary = snapshot["operator_summary"]

    assert summary["primary_target_exception_status"] == "softened-for-flip-churn"
    assert summary["recommendation_drift_status"] == "drifting"
    assert summary["primary_target_trust_policy"] == "verify-first"
    assert summary["primary_target"].get("policy_flip_count", 0) >= 2


def test_operator_snapshot_never_softens_blocked_setup_below_act_with_review(tmp_path: Path, monkeypatch):
    report = _make_report()
    monkeypatch.setattr(
        "src.operator_control_center.load_operator_state_history",
        lambda *_args, **_kwargs: [
            {
                "generated_at": "2026-04-06T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "setup:github-token",
                        "title": "GitHub authentication is required.",
                        "lane": "blocked",
                        "kind": "setup",
                    },
                    "primary_target_trust_policy": "act-now",
                    "decision_memory_status": "reopened",
                    "primary_target_last_outcome": "reopened",
                },
                "operator_queue": [],
            },
            {
                "generated_at": "2026-04-05T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "setup:github-token",
                        "title": "GitHub authentication is required.",
                        "lane": "blocked",
                        "kind": "setup",
                    },
                    "primary_target_trust_policy": "verify-first",
                    "decision_memory_status": "reopened",
                    "primary_target_last_outcome": "reopened",
                },
                "operator_queue": [],
            },
            {
                "generated_at": "2026-04-04T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "setup:github-token",
                        "title": "GitHub authentication is required.",
                        "lane": "blocked",
                        "kind": "setup",
                    },
                    "primary_target_trust_policy": "act-now",
                    "decision_memory_status": "reopened",
                    "primary_target_last_outcome": "reopened",
                },
                "operator_queue": [],
            },
            {
                "generated_at": "2026-04-04T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-target:RepoC",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_closure_forecast_reweight_direction": "supporting-clearance",
                    "primary_target_closure_forecast_reweight_score": -0.18,
                    "primary_target_closure_forecast_reacquisition_freshness_status": "fresh",
                    "primary_target_closure_forecast_persistence_reset_status": "clearance-reset",
                    "primary_target_transition_closure_likely_outcome": "hold",
                    "primary_target_class_reweight_transition_status": "pending-caution",
                },
                "operator_queue": [],
            },
            {
                "generated_at": "2026-04-04T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-target:RepoC",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_closure_forecast_reweight_direction": "supporting-clearance",
                    "primary_target_closure_forecast_reweight_score": -0.18,
                    "primary_target_closure_forecast_reacquisition_freshness_status": "fresh",
                    "primary_target_closure_forecast_persistence_reset_status": "clearance-reset",
                    "primary_target_transition_closure_likely_outcome": "hold",
                    "primary_target_class_reweight_transition_status": "pending-caution",
                },
                "operator_queue": [],
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

    assert summary["primary_target_exception_status"] in {"softened-for-noise", "softened-for-flip-churn", "softened-for-reopen-risk"}
    assert summary["primary_target_trust_policy"] == "act-with-review"


def test_operator_snapshot_recovers_stable_verify_first_target(tmp_path: Path, monkeypatch):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    monkeypatch.setattr(
        "src.operator_control_center.load_operator_state_history",
        lambda *_args, **_kwargs: [
            {
                "generated_at": "2026-04-06T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-change:high-1",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_trust_policy": "verify-first",
                    "primary_target_exception_status": "softened-for-flip-churn",
                    "decision_memory_status": "attempted",
                    "primary_target_last_outcome": "improved",
                },
                "operator_queue": [],
            },
            {
                "generated_at": "2026-04-05T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-change:other",
                        "repo": "RepoX",
                        "title": "RepoX security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_trust_policy": "act-with-review",
                    "primary_target_exception_status": "none",
                    "decision_memory_status": "new",
                    "primary_target_last_outcome": "improved",
                },
                "operator_queue": [],
            },
            {
                "generated_at": "2026-04-04T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-change:high-1",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_trust_policy": "verify-first",
                    "primary_target_exception_status": "softened-for-flip-churn",
                    "decision_memory_status": "attempted",
                    "primary_target_last_outcome": "improved",
                },
                "operator_queue": [],
            },
        ],
    )
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
    monkeypatch.setattr(
        "src.operator_control_center._trust_policy_exception_for_target",
        lambda target, *_args, **_kwargs: (
            "softened-for-flip-churn",
            "Recent trust-policy flips have been bouncing enough that this recommendation should not be treated as fully stable yet.",
            "verify-first",
            "Recent trust-policy churn means this target should be handled with a softer, verification-aware posture.",
        ),
    )

    snapshot = build_operator_snapshot(report, output_dir=tmp_path)
    summary = snapshot["operator_summary"]

    assert summary["primary_target_exception_status"] == "softened-for-flip-churn"
    assert summary["primary_target_trust_recovery_status"] == "earned"
    assert summary["primary_target_exception_pattern_status"] == "recovering"
    assert summary["primary_target_trust_policy"] == "act-with-review"
    assert summary["primary_target_recovery_confidence_label"] in {"medium", "high"}
    assert summary["primary_target_exception_retirement_status"] == "candidate"


def test_operator_snapshot_retires_exception_after_stable_window(tmp_path: Path, monkeypatch):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    monkeypatch.setattr(
        "src.operator_control_center.load_operator_state_history",
        lambda *_args, **_kwargs: [
            {
                "generated_at": "2026-04-06T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-change:high-1",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_trust_policy": "verify-first",
                    "primary_target_exception_status": "softened-for-flip-churn",
                    "decision_memory_status": "attempted",
                    "primary_target_last_outcome": "improved",
                },
                "operator_queue": [],
            },
            {
                "generated_at": "2026-04-05T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-change:high-1",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_trust_policy": "verify-first",
                    "primary_target_exception_status": "softened-for-flip-churn",
                    "decision_memory_status": "attempted",
                    "primary_target_last_outcome": "improved",
                },
                "operator_queue": [],
            },
            {
                "generated_at": "2026-04-04T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-change:high-1",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_trust_policy": "verify-first",
                    "primary_target_exception_status": "softened-for-flip-churn",
                    "decision_memory_status": "attempted",
                    "primary_target_last_outcome": "improved",
                },
                "operator_queue": [],
            },
        ],
    )
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
    monkeypatch.setattr(
        "src.operator_control_center._trust_policy_exception_for_target",
        lambda target, *_args, **_kwargs: (
            "softened-for-flip-churn",
            "Recent trust-policy flips have been bouncing enough that this recommendation should not be treated as fully stable yet.",
            "verify-first",
            "Recent trust-policy churn means this target should be handled with a softer, verification-aware posture.",
        ),
    )

    snapshot = build_operator_snapshot(report, output_dir=tmp_path)
    summary = snapshot["operator_summary"]

    assert summary["primary_target_trust_recovery_status"] == "earned"
    assert summary["primary_target_recovery_confidence_label"] == "high"
    assert summary["primary_target_exception_retirement_status"] == "retired"
    assert summary["primary_target_trust_policy"] == "act-with-review"


def test_operator_snapshot_applies_class_level_normalization_for_healthy_class(tmp_path: Path, monkeypatch):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    monkeypatch.setattr(
        "src.operator_control_center.load_operator_state_history",
        lambda *_args, **_kwargs: [
            {
                "generated_at": "2026-04-06T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-change:old-1",
                        "repo": "RepoX",
                        "title": "RepoX security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_trust_policy": "act-with-review",
                    "primary_target_exception_status": "softened-for-flip-churn",
                    "primary_target_exception_pattern_status": "overcautious",
                    "primary_target_exception_retirement_status": "retired",
                    "primary_target_trust_recovery_status": "earned",
                    "confidence_validation_status": "healthy",
                    "decision_memory_status": "attempted",
                    "primary_target_last_outcome": "improved",
                },
                "operator_queue": [],
            },
            {
                "generated_at": "2026-04-05T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-change:old-2",
                        "repo": "RepoY",
                        "title": "RepoY security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_trust_policy": "act-with-review",
                    "primary_target_exception_status": "softened-for-flip-churn",
                    "primary_target_exception_pattern_status": "overcautious",
                    "primary_target_exception_retirement_status": "retired",
                    "primary_target_trust_recovery_status": "earned",
                    "confidence_validation_status": "healthy",
                    "decision_memory_status": "attempted",
                    "primary_target_last_outcome": "improved",
                },
                "operator_queue": [],
            },
            {
                "generated_at": "2026-04-04T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-change:old-3",
                        "repo": "RepoZ",
                        "title": "RepoZ security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_trust_policy": "act-with-review",
                    "primary_target_exception_status": "softened-for-flip-churn",
                    "primary_target_exception_pattern_status": "overcautious",
                    "primary_target_exception_retirement_status": "retired",
                    "primary_target_trust_recovery_status": "earned",
                    "confidence_validation_status": "healthy",
                    "decision_memory_status": "attempted",
                    "primary_target_last_outcome": "improved",
                },
                "operator_queue": [],
            },
        ],
    )
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
    monkeypatch.setattr(
        "src.operator_control_center._trust_policy_exception_for_target",
        lambda target, *_args, **_kwargs: (
            "softened-for-flip-churn",
            "Recent trust-policy flips have been bouncing enough that this recommendation should not be treated as fully stable yet.",
            "verify-first",
            "Recent trust-policy churn means this target should be handled with a softer, verification-aware posture.",
        ),
    )

    snapshot = build_operator_snapshot(report, output_dir=tmp_path)
    summary = snapshot["operator_summary"]

    assert summary["primary_target_policy_debt_status"] == "watch"
    assert summary["primary_target_class_normalization_status"] == "applied"
    assert summary["primary_target_trust_policy"] == "act-with-review"
    assert "clean retirement" in summary["trust_normalization_summary"].lower()


def test_operator_snapshot_keeps_one_off_noise_from_class_normalization(tmp_path: Path, monkeypatch):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    monkeypatch.setattr(
        "src.operator_control_center.load_operator_state_history",
        lambda *_args, **_kwargs: [
            {
                "generated_at": "2026-04-06T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-change:old-1",
                        "repo": "RepoX",
                        "title": "RepoX security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_trust_policy": "act-with-review",
                    "primary_target_exception_status": "softened-for-flip-churn",
                    "primary_target_exception_pattern_status": "overcautious",
                    "primary_target_exception_retirement_status": "retired",
                    "primary_target_trust_recovery_status": "earned",
                    "confidence_validation_status": "healthy",
                    "decision_memory_status": "attempted",
                    "primary_target_last_outcome": "improved",
                },
                "operator_queue": [],
            },
            {
                "generated_at": "2026-04-05T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-change:old-2",
                        "repo": "RepoY",
                        "title": "RepoY security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_trust_policy": "act-with-review",
                    "primary_target_exception_status": "softened-for-flip-churn",
                    "primary_target_exception_pattern_status": "overcautious",
                    "primary_target_exception_retirement_status": "retired",
                    "primary_target_trust_recovery_status": "earned",
                    "confidence_validation_status": "healthy",
                    "decision_memory_status": "attempted",
                    "primary_target_last_outcome": "improved",
                },
                "operator_queue": [],
            },
            {
                "generated_at": "2026-04-04T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-change:old-3",
                        "repo": "RepoZ",
                        "title": "RepoZ security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_trust_policy": "act-with-review",
                    "primary_target_exception_status": "softened-for-flip-churn",
                    "primary_target_exception_pattern_status": "overcautious",
                    "primary_target_exception_retirement_status": "retired",
                    "primary_target_trust_recovery_status": "earned",
                    "confidence_validation_status": "healthy",
                    "decision_memory_status": "attempted",
                    "primary_target_last_outcome": "improved",
                },
                "operator_queue": [],
            },
        ],
    )
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
    monkeypatch.setattr(
        "src.operator_control_center._trust_policy_exception_for_target",
        lambda target, *_args, **_kwargs: (
            "softened-for-reopen-risk",
            "Recent reopen or unresolved behavior softened the recommendation, so confirm closure evidence before overcommitting.",
            "verify-first",
            "Recent reopen behavior means closure evidence should be confirmed before overcommitting.",
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._trust_recovery_for_target",
        lambda target, *_args, **_kwargs: (
            "blocked",
            "Trust recovery is blocked because this target reopened again inside the recent recovery window.",
            "verify-first",
            "Recent reopen behavior means closure evidence should be confirmed before overcommitting.",
        ),
    )

    snapshot = build_operator_snapshot(report, output_dir=tmp_path)
    summary = snapshot["operator_summary"]

    assert summary["primary_target_policy_debt_status"] == "one-off-noise"
    assert summary["primary_target_class_normalization_status"] == "blocked"
    assert summary["primary_target_trust_policy"] == "verify-first"
    assert "target-specific" in summary["policy_debt_summary"].lower()


def test_operator_snapshot_decays_stale_class_normalization(tmp_path: Path, monkeypatch):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    history = []
    for day in range(1, 10):
        if day <= 3:
            history.append(
                {
                    "generated_at": f"2026-04-0{10 - day}T12:00:00+00:00",
                    "operator_summary": {
                        "primary_target": {
                            "item_id": f"other:{day}",
                            "repo": f"Repo{day}",
                            "title": f"Other target {day}",
                            "lane": "urgent",
                            "kind": "campaign",
                        },
                        "primary_target_trust_policy": "verify-first",
                    },
                    "operator_queue": [],
                }
            )
            continue
        history.append(
            {
                "generated_at": f"2026-03-{20 - day:02d}T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": f"review-change:old-{day}",
                        "repo": f"Repo{day}",
                        "title": f"Repo{day} security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_trust_policy": "act-with-review",
                    "primary_target_exception_status": "softened-for-flip-churn",
                    "primary_target_exception_pattern_status": "overcautious",
                    "primary_target_exception_retirement_status": "retired",
                    "primary_target_trust_recovery_status": "earned",
                    "primary_target_policy_debt_status": "watch",
                    "primary_target_class_normalization_status": "candidate",
                    "primary_target_class_trust_reweight_direction": "supporting-normalization",
                    "primary_target_class_trust_reweight_score": 0.32,
                    "confidence_validation_status": "healthy",
                    "decision_memory_status": "attempted",
                    "primary_target_last_outcome": "improved",
                },
                "operator_queue": [],
            }
        )
    monkeypatch.setattr("src.operator_control_center.load_operator_state_history", lambda *_args, **_kwargs: history)
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
    monkeypatch.setattr(
        "src.operator_control_center._trust_policy_exception_for_target",
        lambda target, *_args, **_kwargs: (
            "softened-for-flip-churn",
            "Recent trust-policy flips have been bouncing enough that this recommendation should not be treated as fully stable yet.",
            "verify-first",
            "Recent trust-policy churn means this target should be handled with a softer, verification-aware posture.",
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._trust_recovery_for_target",
        lambda target, *_args, **_kwargs: (
            "candidate",
            "This target is stabilizing under healthy calibration, but it has not held steady long enough to earn stronger trust yet.",
            "verify-first",
            "Recent trust-policy churn means this target should be handled with a softer, verification-aware posture.",
        ),
    )

    snapshot = build_operator_snapshot(report, output_dir=tmp_path)
    summary = snapshot["operator_summary"]

    assert summary["primary_target_class_normalization_status"] == "candidate"
    assert summary["primary_target_class_memory_freshness_status"] == "insufficient-data"
    assert summary["primary_target_class_decay_status"] == "normalization-decayed"
    assert summary["primary_target_trust_policy"] == "verify-first"
    assert "aging out" in summary["class_decay_summary"].lower() or "too old" in summary["class_decay_summary"].lower()


def test_operator_snapshot_softens_class_debt_when_fresh_sticky_signal_ages_out(tmp_path: Path, monkeypatch):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    history = []
    for day in range(1, 10):
        summary = {
            "primary_target": {
                "item_id": f"review-change:old-{day}",
                "repo": f"Repo{day}",
                "title": f"Repo{day} security posture changed",
                "lane": "urgent",
                "kind": "review",
            },
            "primary_target_trust_policy": "verify-first",
            "primary_target_exception_status": "softened-for-flip-churn",
            "confidence_validation_status": "healthy",
            "decision_memory_status": "attempted",
            "primary_target_last_outcome": "improved",
        }
        if day <= 3:
            summary["primary_target_exception_pattern_status"] = "overcautious"
            summary["primary_target_exception_retirement_status"] = "retired"
            summary["primary_target_trust_recovery_status"] = "earned"
        elif day >= 5:
            summary["primary_target_exception_pattern_status"] = "useful-caution"
            summary["primary_target_exception_retirement_status"] = "blocked"
            summary["primary_target_trust_recovery_status"] = "blocked"
        history.append(
            {
                "generated_at": f"2026-04-{10 - day:02d}T12:00:00+00:00",
                "operator_summary": summary,
                "operator_queue": [],
            }
        )
    monkeypatch.setattr("src.operator_control_center.load_operator_state_history", lambda *_args, **_kwargs: history)
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
    monkeypatch.setattr(
        "src.operator_control_center._trust_policy_exception_for_target",
        lambda target, *_args, **_kwargs: (
            "softened-for-flip-churn",
            "Recent trust-policy flips have been bouncing enough that this recommendation should not be treated as fully stable yet.",
            "verify-first",
            "Recent trust-policy churn means this target should be handled with a softer, verification-aware posture.",
        ),
    )

    snapshot = build_operator_snapshot(report, output_dir=tmp_path)
    summary = snapshot["operator_summary"]

    assert summary["primary_target_policy_debt_status"] == "watch"
    assert summary["primary_target_class_decay_status"] == "policy-debt-decayed"
    assert summary["primary_target_class_memory_freshness_status"] == "fresh"
    assert "no longer has enough fresh sticky class evidence" in summary["class_decay_summary"].lower()


def test_operator_snapshot_boosts_candidate_normalization_when_fresh_support_crosses_threshold(tmp_path: Path, monkeypatch):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    history = []
    for day in range(1, 4):
        history.append(
            {
                "generated_at": f"2026-04-0{7 - day}T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": f"review-change:old-{day}",
                        "repo": f"Repo{day}",
                        "title": f"Repo{day} security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_trust_policy": "act-with-review",
                    "primary_target_exception_status": "softened-for-flip-churn",
                    "primary_target_exception_pattern_status": "overcautious",
                    "primary_target_exception_retirement_status": "retired",
                    "primary_target_trust_recovery_status": "earned",
                    "primary_target_policy_debt_status": "watch",
                    "primary_target_class_normalization_status": "candidate",
                    "primary_target_class_trust_reweight_direction": "supporting-normalization",
                    "primary_target_class_trust_reweight_score": 0.32,
                    "confidence_validation_status": "healthy",
                    "decision_memory_status": "attempted",
                    "primary_target_last_outcome": "improved",
                },
                "operator_queue": [],
            }
        )
    monkeypatch.setattr("src.operator_control_center.load_operator_state_history", lambda *_args, **_kwargs: history)
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
    monkeypatch.setattr(
        "src.operator_control_center._trust_policy_exception_for_target",
        lambda target, *_args, **_kwargs: (
            "softened-for-flip-churn",
            "Recent trust-policy flips have been bouncing enough that this recommendation should not be treated as fully stable yet.",
            "verify-first",
            "Recent trust-policy churn means this target should be handled with a softer, verification-aware posture.",
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._trust_recovery_for_target",
        lambda target, *_args, **_kwargs: (
            "candidate",
            "This target is stabilizing under healthy calibration, but it has not held steady long enough to earn stronger trust yet.",
            "verify-first",
            "Recent trust-policy churn means this target should be handled with a softer, verification-aware posture.",
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._class_normalization_for_target",
        lambda target, *_args, **_kwargs: (
            "candidate",
            "This class is trending healthier, but the current target has not earned class-level normalization yet.",
            "verify-first",
            "Recent trust-policy churn means this target should be handled with a softer, verification-aware posture.",
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._class_memory_decay_for_target",
        lambda target, _history_meta, _calibration, **kwargs: (
            "none",
            "",
            kwargs["trust_policy"],
            kwargs["trust_policy_reason"],
            kwargs["policy_debt_status"],
            kwargs["policy_debt_reason"],
            kwargs["class_normalization_status"],
            kwargs["class_normalization_reason"],
        ),
    )

    snapshot = build_operator_snapshot(report, output_dir=tmp_path)
    summary = snapshot["operator_summary"]

    assert summary["primary_target_class_trust_reweight_direction"] == "supporting-normalization"
    assert summary["primary_target_weighted_class_support_score"] > summary["primary_target_weighted_class_caution_score"]
    assert summary["primary_target_class_normalization_status"] == "applied"
    assert summary["primary_target_class_trust_momentum_status"] == "sustained-support"
    assert summary["primary_target_class_reweight_transition_status"] == "confirmed-support"
    assert summary["primary_target_class_transition_resolution_status"] == "confirmed"
    assert summary["primary_target_trust_policy"] == "act-with-review"
    assert "confirm broader normalization" in summary["class_momentum_summary"].lower()


def test_operator_snapshot_strengthens_watch_into_class_debt_when_fresh_caution_stays_heavy(tmp_path: Path, monkeypatch):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    history = []
    for day in range(1, 4):
        history.append(
            {
                "generated_at": f"2026-04-0{7 - day}T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": f"review-change:old-{day}",
                        "repo": f"Repo{day}",
                        "title": f"Repo{day} security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_trust_policy": "verify-first",
                    "primary_target_exception_status": "softened-for-reopen-risk",
                    "primary_target_exception_pattern_status": "useful-caution",
                    "primary_target_exception_retirement_status": "blocked",
                    "primary_target_trust_recovery_status": "blocked",
                    "primary_target_policy_debt_status": "watch",
                    "primary_target_class_normalization_status": "none",
                    "primary_target_class_trust_reweight_direction": "supporting-caution",
                    "primary_target_class_trust_reweight_score": -0.34,
                    "confidence_validation_status": "healthy",
                    "decision_memory_status": "reopened",
                    "primary_target_last_outcome": "reopened",
                },
                "operator_queue": [],
            }
        )
    monkeypatch.setattr("src.operator_control_center.load_operator_state_history", lambda *_args, **_kwargs: history)
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
    monkeypatch.setattr(
        "src.operator_control_center._trust_policy_exception_for_target",
        lambda target, *_args, **_kwargs: (
            "softened-for-reopen-risk",
            "Recent reopen or unresolved behavior softened the recommendation, so confirm closure evidence before overcommitting.",
            "verify-first",
            "Recent reopen behavior means closure evidence should be confirmed before overcommitting.",
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._trust_recovery_for_target",
        lambda target, *_args, **_kwargs: (
            "blocked",
            "Trust recovery is blocked because this target reopened again inside the recent recovery window.",
            "verify-first",
            "Recent reopen behavior means closure evidence should be confirmed before overcommitting.",
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._policy_debt_for_target",
        lambda target, _history_meta: (
            "watch",
            "This class has enough recent exception activity to watch for lingering caution, but it is not yet clearly sticky or clearly normalization-friendly.",
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._class_memory_decay_for_target",
        lambda target, _history_meta, _calibration, **kwargs: (
            "none",
            "",
            kwargs["trust_policy"],
            kwargs["trust_policy_reason"],
            kwargs["policy_debt_status"],
            kwargs["policy_debt_reason"],
            kwargs["class_normalization_status"],
            kwargs["class_normalization_reason"],
        ),
    )
    snapshot = build_operator_snapshot(report, output_dir=tmp_path)
    summary = snapshot["operator_summary"]

    assert summary["primary_target_class_trust_reweight_direction"] == "supporting-caution"
    assert summary["primary_target_weighted_class_caution_score"] > summary["primary_target_weighted_class_support_score"]
    assert summary["primary_target_policy_debt_status"] == "class-debt"
    assert summary["primary_target_class_trust_momentum_status"] == "sustained-caution"
    assert summary["primary_target_class_reweight_transition_status"] == "confirmed-caution"
    assert summary["primary_target_class_transition_resolution_status"] == "confirmed"
    assert summary["primary_target_trust_policy"] == "verify-first"
    assert "confirm broader caution" in summary["class_momentum_summary"].lower()


def test_operator_snapshot_holds_class_normalization_pending_until_support_persists(tmp_path: Path, monkeypatch):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    history = []
    monkeypatch.setattr("src.operator_control_center.load_operator_state_history", lambda *_args, **_kwargs: history)
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
    monkeypatch.setattr(
        "src.operator_control_center._trust_policy_exception_for_target",
        lambda target, *_args, **_kwargs: (
            "softened-for-flip-churn",
            "Recent trust-policy flips have been bouncing enough that this recommendation should not be treated as fully stable yet.",
            "verify-first",
            "Recent trust-policy churn means this target should be handled with a softer, verification-aware posture.",
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._trust_recovery_for_target",
        lambda target, *_args, **_kwargs: (
            "candidate",
            "This target is stabilizing under healthy calibration, but it has not held steady long enough to earn stronger trust yet.",
            "verify-first",
            "Recent trust-policy churn means this target should be handled with a softer, verification-aware posture.",
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._class_memory_decay_for_target",
        lambda target, _history_meta, _calibration, **kwargs: (
            "none",
            "",
            kwargs["trust_policy"],
            kwargs["trust_policy_reason"],
            kwargs["policy_debt_status"],
            kwargs["policy_debt_reason"],
            kwargs["class_normalization_status"],
            kwargs["class_normalization_reason"],
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._class_trust_reweight_for_target",
        lambda target, _history_meta, _calibration, **kwargs: (
            "normalization-boosted",
            "Fresh class support crossed the reweight threshold, so this target inherits a stronger act-with-review posture.",
            "act-with-review",
            "Fresh class support crossed the reweight threshold, so this target inherits a stronger act-with-review posture.",
            kwargs["policy_debt_status"],
            kwargs["policy_debt_reason"],
            "applied",
            "Fresh class support crossed the reweight threshold, so this target inherits a stronger act-with-review posture.",
        ),
    )

    snapshot = build_operator_snapshot(report, output_dir=tmp_path)
    summary = snapshot["operator_summary"]

    assert summary["primary_target_class_trust_momentum_status"] == "insufficient-data"
    assert summary["primary_target_class_reweight_transition_status"] == "pending-support"
    assert summary["primary_target_class_transition_health_status"] == "building"
    assert summary["primary_target_class_transition_resolution_status"] == "none"
    assert summary["primary_target_class_normalization_status"] == "candidate"
    assert summary["primary_target_trust_policy"] == "verify-first"
    assert "not stayed persistent enough" in summary["class_momentum_summary"].lower()


def test_operator_snapshot_marks_flat_pending_support_as_holding_then_stalled(tmp_path: Path, monkeypatch):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    history = [
        {
            "generated_at": "2026-04-06T12:00:00+00:00",
            "operator_summary": {
                "primary_target": {
                    "item_id": "review-target:RepoC",
                    "repo": "RepoC",
                    "title": "RepoC security posture changed",
                    "lane": "urgent",
                    "kind": "review",
                },
                "primary_target_class_reweight_transition_status": "pending-support",
                "primary_target_class_reweight_transition_reason": "Pending support is still visible.",
                "primary_target_class_trust_reweight_direction": "supporting-normalization",
                "primary_target_class_trust_reweight_score": 0.24,
                "primary_target_class_trust_momentum_status": "building",
                "primary_target_class_reweight_stability_status": "watch",
            },
            "operator_queue": [],
        }
    ]
    monkeypatch.setattr("src.operator_control_center.load_operator_state_history", lambda *_args, **_kwargs: history)
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
    monkeypatch.setattr(
        "src.operator_control_center._trust_policy_exception_for_target",
        lambda target, *_args, **_kwargs: (
            "softened-for-flip-churn",
            "Recent trust-policy flips have been bouncing enough that this recommendation should not be treated as fully stable yet.",
            "verify-first",
            "Recent trust-policy churn means this target should be handled with a softer, verification-aware posture.",
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._trust_recovery_for_target",
        lambda target, *_args, **_kwargs: (
            "candidate",
            "This target is stabilizing under healthy calibration, but it has not held steady long enough to earn stronger trust yet.",
            "verify-first",
            "Recent trust-policy churn means this target should be handled with a softer, verification-aware posture.",
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._class_memory_decay_for_target",
        lambda target, _history_meta, _calibration, **kwargs: (
            "none",
            "",
            kwargs["trust_policy"],
            kwargs["trust_policy_reason"],
            kwargs["policy_debt_status"],
            kwargs["policy_debt_reason"],
            kwargs["class_normalization_status"],
            kwargs["class_normalization_reason"],
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._class_trust_reweight_for_target",
        lambda target, _history_meta, _calibration, **kwargs: (
            "normalization-boosted",
            "Fresh class support crossed the reweight threshold, so this target inherits a stronger act-with-review posture.",
            "act-with-review",
            "Fresh class support crossed the reweight threshold, so this target inherits a stronger act-with-review posture.",
            kwargs["policy_debt_status"],
            kwargs["policy_debt_reason"],
            "applied",
            "Fresh class support crossed the reweight threshold, so this target inherits a stronger act-with-review posture.",
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._class_trust_reweight_scores_for_target",
        lambda target, _history_meta: (0.48, 0.24, 0.24, "supporting-normalization", []),
    )
    monkeypatch.setattr(
        "src.operator_control_center._class_trust_momentum_for_target",
        lambda target, _history_meta, _calibration, **kwargs: (
            "pending-support",
            "The class signal is visible, but it has not stayed strong long enough to confirm broader normalization yet.",
            kwargs["trust_policy"],
            kwargs["trust_policy_reason"],
            kwargs["policy_debt_status"],
            kwargs["policy_debt_reason"],
            "candidate",
            "The class signal is visible, but it has not stayed strong long enough to confirm broader normalization yet.",
        ),
    )

    summary = build_operator_snapshot(report, output_dir=tmp_path)["operator_summary"]

    assert summary["primary_target_class_transition_health_status"] == "holding"
    assert summary["primary_target_class_transition_resolution_status"] == "none"
    assert summary["primary_target_class_reweight_transition_status"] == "pending-support"
    assert summary["primary_target_class_normalization_status"] == "candidate"

    history.insert(
        0,
        {
            "generated_at": "2026-04-05T12:00:00+00:00",
            "operator_summary": {
                "primary_target": {
                    "item_id": "review-target:RepoC",
                    "repo": "RepoC",
                    "title": "RepoC security posture changed",
                    "lane": "urgent",
                    "kind": "review",
                },
                "primary_target_class_reweight_transition_status": "pending-support",
                "primary_target_class_reweight_transition_reason": "Pending support is still visible.",
                "primary_target_class_trust_reweight_direction": "supporting-normalization",
                "primary_target_class_trust_reweight_score": 0.24,
                "primary_target_class_trust_momentum_status": "building",
                "primary_target_class_reweight_stability_status": "watch",
            },
            "operator_queue": [],
        },
    )

    summary = build_operator_snapshot(report, output_dir=tmp_path)["operator_summary"]
    assert summary["primary_target_class_transition_health_status"] == "stalled"
    assert summary["primary_target_class_transition_resolution_status"] == "none"


def test_operator_snapshot_expires_old_pending_support_when_signal_fades(tmp_path: Path, monkeypatch):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    history = []
    for day in range(1, 5):
        history.append(
            {
                "generated_at": f"2026-04-0{7 - day}T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-target:RepoC",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_class_reweight_transition_status": "pending-support",
                    "primary_target_class_reweight_transition_reason": "The class signal is visible, but it has not stayed strong long enough to confirm broader normalization yet.",
                    "primary_target_class_trust_reweight_direction": "supporting-normalization",
                    "primary_target_class_trust_reweight_score": 0.24,
                    "primary_target_class_trust_momentum_status": "building",
                    "primary_target_class_reweight_stability_status": "watch",
                },
                "operator_queue": [],
            }
        )
    monkeypatch.setattr("src.operator_control_center.load_operator_state_history", lambda *_args, **_kwargs: history)
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
    monkeypatch.setattr(
        "src.operator_control_center._trust_policy_exception_for_target",
        lambda target, *_args, **_kwargs: (
            "softened-for-flip-churn",
            "Recent trust-policy flips have been bouncing enough that this recommendation should not be treated as fully stable yet.",
            "verify-first",
            "Recent trust-policy churn means this target should be handled with a softer, verification-aware posture.",
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._trust_recovery_for_target",
        lambda target, *_args, **_kwargs: (
            "candidate",
            "This target is stabilizing under healthy calibration, but it has not held steady long enough to earn stronger trust yet.",
            "verify-first",
            "Recent trust-policy churn means this target should be handled with a softer, verification-aware posture.",
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._class_memory_decay_for_target",
        lambda target, _history_meta, _calibration, **kwargs: (
            "none",
            "",
            kwargs["trust_policy"],
            kwargs["trust_policy_reason"],
            kwargs["policy_debt_status"],
            kwargs["policy_debt_reason"],
            kwargs["class_normalization_status"],
            kwargs["class_normalization_reason"],
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._class_trust_reweight_scores_for_target",
        lambda target, _history_meta: (0.05, 0.02, 0.03, "neutral", []),
    )
    monkeypatch.setattr(
        "src.operator_control_center._class_trust_reweight_for_target",
        lambda target, _history_meta, _calibration, **kwargs: (
            "none",
            "",
            kwargs["trust_policy"],
            kwargs["trust_policy_reason"],
            kwargs["policy_debt_status"],
            kwargs["policy_debt_reason"],
            kwargs["class_normalization_status"],
            kwargs["class_normalization_reason"],
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._class_trust_momentum_for_target",
        lambda target, _history_meta, _calibration, **kwargs: (
            "none",
            "",
            kwargs["trust_policy"],
            kwargs["trust_policy_reason"],
            kwargs["policy_debt_status"],
            kwargs["policy_debt_reason"],
            kwargs["class_normalization_status"],
            kwargs["class_normalization_reason"],
        ),
    )

    summary = build_operator_snapshot(report, output_dir=tmp_path)["operator_summary"]

    assert summary["primary_target_class_transition_health_status"] == "expired"
    assert summary["primary_target_class_transition_resolution_status"] == "expired"
    assert summary["primary_target_class_reweight_transition_status"] == "none"
    assert summary["primary_target_trust_policy"] == "verify-first"


def test_operator_snapshot_marks_blocked_pending_support_when_local_noise_overrides(tmp_path: Path, monkeypatch):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    monkeypatch.setattr(
        "src.operator_control_center._trust_policy_exception_for_target",
        lambda target, *_args, **_kwargs: (
            "softened-for-reopen-risk",
            "Recent reopen or unresolved behavior softened the recommendation, so confirm closure evidence before overcommitting.",
            "verify-first",
            "Recent reopen behavior means closure evidence should be confirmed before overcommitting.",
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._trust_recovery_for_target",
        lambda target, *_args, **_kwargs: (
            "blocked",
            "Trust recovery is blocked because this target reopened again inside the recent recovery window.",
            "verify-first",
            "Recent reopen behavior means closure evidence should be confirmed before overcommitting.",
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._class_memory_decay_for_target",
        lambda target, _history_meta, _calibration, **kwargs: (
            "none",
            "",
            kwargs["trust_policy"],
            kwargs["trust_policy_reason"],
            kwargs["policy_debt_status"],
            kwargs["policy_debt_reason"],
            kwargs["class_normalization_status"],
            kwargs["class_normalization_reason"],
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._class_trust_reweight_for_target",
        lambda target, _history_meta, _calibration, **kwargs: (
            "normalization-boosted",
            "Fresh class support crossed the reweight threshold, so this target inherits a stronger act-with-review posture.",
            "act-with-review",
            "Fresh class support crossed the reweight threshold, so this target inherits a stronger act-with-review posture.",
            kwargs["policy_debt_status"],
            kwargs["policy_debt_reason"],
            "applied",
            "Fresh class support crossed the reweight threshold, so this target inherits a stronger act-with-review posture.",
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._class_trust_momentum_for_target",
        lambda target, _history_meta, _calibration, **kwargs: (
            "blocked",
            "Positive class strengthening is blocked because local reopen, flip, or blocked-recovery noise still overrides the class signal.",
            kwargs["trust_policy"],
            kwargs["trust_policy_reason"],
            kwargs["policy_debt_status"],
            kwargs["policy_debt_reason"],
            "candidate",
            "Positive class strengthening is blocked because local reopen, flip, or blocked-recovery noise still overrides the class signal.",
        ),
    )

    summary = build_operator_snapshot(report, output_dir=tmp_path)["operator_summary"]

    assert summary["primary_target_class_transition_health_status"] == "blocked"
    assert summary["primary_target_class_transition_resolution_status"] == "blocked"
    assert summary["primary_target_class_reweight_transition_status"] == "blocked"
    assert summary["primary_target_class_normalization_status"] == "candidate"


def test_operator_snapshot_scores_pending_support_as_confirm_soon_without_auto_confirming(
    tmp_path: Path, monkeypatch
):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    history = [
        {
            "generated_at": "2026-04-06T12:00:00+00:00",
            "operator_summary": {
                "primary_target": {
                    "item_id": "review-target:RepoC",
                    "repo": "RepoC",
                    "title": "RepoC security posture changed",
                    "lane": "urgent",
                    "kind": "review",
                },
                "primary_target_class_trust_reweight_direction": "supporting-normalization",
                "primary_target_class_trust_reweight_score": 0.20,
                "primary_target_class_trust_momentum_status": "sustained-support",
                "primary_target_class_reweight_stability_status": "stable",
                "primary_target_class_reweight_transition_status": "pending-support",
                "primary_target_class_reweight_transition_reason": "Pending support is still visible.",
                "primary_target_class_transition_health_status": "building",
                "primary_target_class_transition_resolution_status": "none",
                "primary_target_trust_policy": "verify-first",
            },
            "operator_queue": [],
        }
    ]
    monkeypatch.setattr("src.operator_control_center.load_operator_state_history", lambda *_args, **_kwargs: history)
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
    monkeypatch.setattr(
        "src.operator_control_center._trust_policy_exception_for_target",
        lambda target, *_args, **_kwargs: (
            "softened-for-flip-churn",
            "Recent trust-policy flips have been bouncing enough that this recommendation should not be treated as fully stable yet.",
            "verify-first",
            "Recent trust-policy churn means this target should be handled with a softer, verification-aware posture.",
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._trust_recovery_for_target",
        lambda target, *_args, **_kwargs: (
            "candidate",
            "This target is stabilizing under healthy calibration, but it has not held steady long enough to earn stronger trust yet.",
            "verify-first",
            "Recent trust-policy churn means this target should be handled with a softer, verification-aware posture.",
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._class_memory_decay_for_target",
        lambda target, _history_meta, _calibration, **kwargs: (
            "none",
            "",
            kwargs["trust_policy"],
            kwargs["trust_policy_reason"],
            kwargs["policy_debt_status"],
            kwargs["policy_debt_reason"],
            kwargs["class_normalization_status"],
            kwargs["class_normalization_reason"],
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._class_trust_reweight_scores_for_target",
        lambda target, _history_meta: (0.55, 0.20, 0.35, "supporting-normalization", []),
    )
    monkeypatch.setattr(
        "src.operator_control_center._class_trust_reweight_for_target",
        lambda target, _history_meta, _calibration, **kwargs: (
            "normalization-boosted",
            "Fresh class support crossed the reweight threshold, so this target inherits a stronger act-with-review posture.",
            "act-with-review",
            "Fresh class support crossed the reweight threshold, so this target inherits a stronger act-with-review posture.",
            kwargs["policy_debt_status"],
            kwargs["policy_debt_reason"],
            "applied",
            "Fresh class support crossed the reweight threshold, so this target inherits a stronger act-with-review posture.",
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._class_trust_momentum_for_target",
        lambda target, _history_meta, _calibration, **kwargs: (
            "pending-support",
            "The class signal is visible, but it has not stayed strong long enough to confirm broader normalization yet.",
            "verify-first",
            "The class signal is visible, but it has not stayed strong long enough to confirm broader normalization yet.",
            kwargs["policy_debt_status"],
            kwargs["policy_debt_reason"],
            "candidate",
            "The class signal is visible, but it has not stayed strong long enough to confirm broader normalization yet.",
        ),
    )

    summary = build_operator_snapshot(report, output_dir=tmp_path)["operator_summary"]

    assert summary["primary_target_class_reweight_transition_status"] == "pending-support"
    assert summary["primary_target_transition_closure_confidence_label"] == "high"
    assert summary["primary_target_transition_closure_likely_outcome"] in {"confirm-soon", "hold"}
    assert summary["primary_target_closure_forecast_reweight_direction"] in {
        "neutral",
        "supporting-confirmation",
    }
    assert summary["primary_target_closure_forecast_momentum_status"] in {
        "building",
        "sustained-confirmation",
        "insufficient-data",
    }
    assert summary["primary_target_closure_forecast_hysteresis_status"] in {
        "none",
        "pending-confirmation",
        "confirmed-confirmation",
    }
    assert summary["primary_target_class_transition_resolution_status"] == "none"


def test_operator_snapshot_clears_low_confidence_pending_support_with_active_pending_debt(
    tmp_path: Path, monkeypatch
):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    history = [
        {
            "generated_at": "2026-04-06T12:00:00+00:00",
            "operator_summary": {
                "primary_target": {
                    "item_id": "review-target:RepoC",
                    "repo": "RepoC",
                    "title": "RepoC security posture changed",
                    "lane": "urgent",
                    "kind": "review",
                },
                "primary_target_class_trust_reweight_direction": "supporting-normalization",
                "primary_target_class_trust_reweight_score": 0.06,
                "primary_target_class_trust_momentum_status": "building",
                "primary_target_class_reweight_stability_status": "watch",
                "primary_target_class_reweight_transition_status": "pending-support",
                "primary_target_class_reweight_transition_reason": "Pending support is still visible.",
                "primary_target_class_transition_health_status": "stalled",
                "primary_target_class_transition_resolution_status": "none",
                "primary_target_closure_forecast_reweight_direction": "supporting-clearance",
                "primary_target_closure_forecast_reweight_score": -0.34,
                "primary_target_trust_policy": "verify-first",
            },
            "operator_queue": [],
        },
        {
            "generated_at": "2026-04-05T12:00:00+00:00",
            "operator_summary": {
                "primary_target": {
                    "item_id": "review-target:RepoC",
                    "repo": "RepoC",
                    "title": "RepoC security posture changed",
                    "lane": "urgent",
                    "kind": "review",
                },
                "primary_target_class_trust_reweight_direction": "supporting-normalization",
                "primary_target_class_trust_reweight_score": 0.05,
                "primary_target_class_trust_momentum_status": "building",
                "primary_target_class_reweight_stability_status": "watch",
                "primary_target_class_reweight_transition_status": "pending-support",
                "primary_target_class_reweight_transition_reason": "Pending support is still visible.",
                "primary_target_class_transition_health_status": "stalled",
                "primary_target_class_transition_resolution_status": "none",
                "primary_target_closure_forecast_reweight_direction": "supporting-clearance",
                "primary_target_closure_forecast_reweight_score": -0.29,
                "primary_target_trust_policy": "verify-first",
            },
            "operator_queue": [],
        },
        {
            "generated_at": "2026-04-04T12:00:00+00:00",
            "operator_summary": {
                "primary_target": {
                    "item_id": "review-target:RepoC",
                    "repo": "RepoC",
                    "title": "RepoC security posture changed",
                    "lane": "urgent",
                    "kind": "review",
                },
                "primary_target_class_trust_reweight_direction": "neutral",
                "primary_target_class_trust_reweight_score": 0.02,
                "primary_target_class_trust_momentum_status": "reversing",
                "primary_target_class_reweight_stability_status": "watch",
                "primary_target_class_reweight_transition_status": "none",
                "primary_target_class_reweight_transition_reason": "",
                "primary_target_class_transition_health_status": "expired",
                "primary_target_class_transition_resolution_status": "expired",
                "primary_target_closure_forecast_reweight_direction": "supporting-clearance",
                "primary_target_closure_forecast_reweight_score": -0.24,
                "primary_target_trust_policy": "verify-first",
            },
            "operator_queue": [],
        },
    ]
    monkeypatch.setattr("src.operator_control_center.load_operator_state_history", lambda *_args, **_kwargs: history)
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
    monkeypatch.setattr(
        "src.operator_control_center._trust_policy_exception_for_target",
        lambda target, *_args, **_kwargs: (
            "softened-for-flip-churn",
            "Recent trust-policy flips have been bouncing enough that this recommendation should not be treated as fully stable yet.",
            "verify-first",
            "Recent trust-policy churn means this target should be handled with a softer, verification-aware posture.",
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._trust_recovery_for_target",
        lambda target, *_args, **_kwargs: (
            "candidate",
            "This target is stabilizing under healthy calibration, but it has not held steady long enough to earn stronger trust yet.",
            "verify-first",
            "Recent trust-policy churn means this target should be handled with a softer, verification-aware posture.",
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._class_memory_decay_for_target",
        lambda target, _history_meta, _calibration, **kwargs: (
            "none",
            "",
            kwargs["trust_policy"],
            kwargs["trust_policy_reason"],
            kwargs["policy_debt_status"],
            kwargs["policy_debt_reason"],
            kwargs["class_normalization_status"],
            kwargs["class_normalization_reason"],
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._class_trust_reweight_scores_for_target",
        lambda target, _history_meta: (0.08, 0.03, 0.05, "neutral", []),
    )
    monkeypatch.setattr(
        "src.operator_control_center._class_trust_reweight_for_target",
        lambda target, _history_meta, _calibration, **kwargs: (
            "none",
            "",
            kwargs["trust_policy"],
            kwargs["trust_policy_reason"],
            kwargs["policy_debt_status"],
            kwargs["policy_debt_reason"],
            kwargs["class_normalization_status"],
            kwargs["class_normalization_reason"],
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._class_trust_momentum_for_target",
        lambda target, _history_meta, _calibration, **kwargs: (
            "pending-support",
            "The class signal is visible, but it has not stayed strong long enough to confirm broader normalization yet.",
            "verify-first",
            "The class signal is visible, but it has not stayed strong long enough to confirm broader normalization yet.",
            kwargs["policy_debt_status"],
            kwargs["policy_debt_reason"],
            "candidate",
            "The class signal is visible, but it has not stayed strong long enough to confirm broader normalization yet.",
        ),
    )

    summary = build_operator_snapshot(report, output_dir=tmp_path)["operator_summary"]

    assert summary["primary_target_class_pending_debt_status"] == "active-debt"
    assert summary["primary_target_pending_debt_freshness_status"] == "fresh"
    assert summary["primary_target_transition_closure_confidence_label"] == "low"
    assert summary["primary_target_transition_closure_likely_outcome"] in {"clear-risk", "expire-risk"}
    assert summary["primary_target_closure_forecast_reweight_direction"] in {
        "neutral",
        "supporting-clearance",
    }
    assert summary["primary_target_closure_forecast_momentum_status"] == "sustained-clearance"
    assert summary["primary_target_closure_forecast_hysteresis_status"] == "confirmed-clearance"
    assert summary["primary_target_class_transition_resolution_status"] == "cleared"
    assert summary["primary_target_class_reweight_transition_status"] == "none"
    assert summary["primary_target_trust_policy"] == "verify-first"


def test_operator_snapshot_marks_class_pending_debt_as_clearing(tmp_path: Path, monkeypatch):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    history = [
        {
            "generated_at": "2026-04-06T12:00:00+00:00",
            "operator_summary": {
                "primary_target": {
                    "item_id": "review-target:RepoC",
                    "repo": "RepoC",
                    "title": "RepoC security posture changed",
                    "lane": "urgent",
                    "kind": "review",
                },
                "primary_target_class_transition_resolution_status": "confirmed",
            },
            "operator_queue": [],
        },
        {
            "generated_at": "2026-04-05T12:00:00+00:00",
            "operator_summary": {
                "primary_target": {
                    "item_id": "review-target:RepoC",
                    "repo": "RepoC",
                    "title": "RepoC security posture changed",
                    "lane": "urgent",
                    "kind": "review",
                },
                "primary_target_class_transition_resolution_status": "cleared",
            },
            "operator_queue": [],
        },
    ]
    monkeypatch.setattr("src.operator_control_center.load_operator_state_history", lambda *_args, **_kwargs: history)

    summary = build_operator_snapshot(report, output_dir=tmp_path)["operator_summary"]

    assert summary["primary_target_class_pending_debt_status"] == "clearing"
    assert summary["primary_target_pending_debt_freshness_status"] == "fresh"
    assert "resolving pending transitions more cleanly" in summary["class_pending_debt_summary"].lower()


def test_operator_snapshot_reacquires_confirmation_forecast_after_decay(tmp_path: Path, monkeypatch):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    history = [
        {
            "generated_at": "2026-04-06T12:00:00+00:00",
            "operator_summary": {
                "primary_target": {
                    "item_id": "review-target:RepoC",
                    "repo": "RepoC",
                    "title": "RepoC security posture changed",
                    "lane": "urgent",
                    "kind": "review",
                },
                "primary_target_closure_forecast_reweight_direction": "supporting-confirmation",
                "primary_target_closure_forecast_reweight_score": 0.44,
                "primary_target_closure_forecast_momentum_status": "sustained-confirmation",
                "primary_target_closure_forecast_stability_status": "stable",
                "primary_target_closure_forecast_hysteresis_status": "pending-confirmation",
                "primary_target_closure_forecast_freshness_status": "fresh",
                "primary_target_closure_forecast_decay_status": "none",
                "primary_target_transition_closure_likely_outcome": "hold",
                "primary_target_class_reweight_transition_status": "pending-support",
                "primary_target_class_transition_resolution_status": "none",
            },
            "operator_queue": [],
        },
        {
            "generated_at": "2026-04-05T12:00:00+00:00",
            "operator_summary": {
                "primary_target": {
                    "item_id": "review-target:RepoC",
                    "repo": "RepoC",
                    "title": "RepoC security posture changed",
                    "lane": "urgent",
                    "kind": "review",
                },
                "primary_target_closure_forecast_reweight_direction": "supporting-confirmation",
                "primary_target_closure_forecast_reweight_score": 0.38,
                "primary_target_closure_forecast_momentum_status": "sustained-confirmation",
                "primary_target_closure_forecast_stability_status": "stable",
                "primary_target_closure_forecast_hysteresis_status": "pending-confirmation",
                "primary_target_closure_forecast_freshness_status": "fresh",
                "primary_target_closure_forecast_decay_status": "none",
                "primary_target_transition_closure_likely_outcome": "hold",
                "primary_target_class_reweight_transition_status": "pending-support",
                "primary_target_class_transition_resolution_status": "none",
            },
            "operator_queue": [],
        },
        {
            "generated_at": "2026-04-04T12:00:00+00:00",
            "operator_summary": {
                "primary_target": {
                    "item_id": "review-target:RepoC",
                    "repo": "RepoC",
                    "title": "RepoC security posture changed",
                    "lane": "urgent",
                    "kind": "review",
                },
                "primary_target_closure_forecast_reweight_direction": "supporting-confirmation",
                "primary_target_closure_forecast_reweight_score": 0.31,
                "primary_target_closure_forecast_momentum_status": "building",
                "primary_target_closure_forecast_stability_status": "watch",
                "primary_target_closure_forecast_hysteresis_status": "pending-confirmation",
                "primary_target_closure_forecast_freshness_status": "stale",
                "primary_target_closure_forecast_decay_status": "confirmation-decayed",
                "primary_target_transition_closure_likely_outcome": "hold",
                "primary_target_class_reweight_transition_status": "pending-support",
                "primary_target_class_transition_resolution_status": "none",
            },
            "operator_queue": [],
        },
    ]
    monkeypatch.setattr("src.operator_control_center.load_operator_state_history", lambda *_args, **_kwargs: history)

    def _phase43_seed(
        resolution_targets, _history, *, current_generated_at, confidence_calibration
    ):
        resolution_targets[:] = [
            {
                **target,
                "trust_policy": "verify-first",
                "trust_policy_reason": "The pending class signal is visible, but it has not stayed strong long enough to confirm broader normalization yet.",
                "class_reweight_transition_status": "pending-support",
                "class_reweight_transition_reason": "The class signal is visible, but it has not stayed strong long enough to confirm broader normalization yet.",
                "class_transition_resolution_status": "none",
                "class_transition_resolution_reason": "",
                "class_transition_age_runs": 2,
                "closure_forecast_reweight_score": 0.48,
                "closure_forecast_reweight_direction": "supporting-confirmation",
                "closure_forecast_momentum_status": "sustained-confirmation",
                "closure_forecast_stability_status": "stable",
                "closure_forecast_hysteresis_status": "none",
                "closure_forecast_hysteresis_reason": "",
                "closure_forecast_freshness_status": "fresh",
                "closure_forecast_freshness_reason": "Recent closure-forecast evidence is still current enough to trust.",
                "closure_forecast_decay_status": "none",
                "closure_forecast_decay_reason": "",
                "decayed_confirmation_forecast_rate": 0.72,
                "decayed_clearance_forecast_rate": 0.18,
                "transition_closure_likely_outcome": "hold",
            }
            for target in resolution_targets
        ]
        return {
            "primary_target_closure_forecast_freshness_status": "fresh",
            "primary_target_closure_forecast_freshness_reason": "Recent closure-forecast evidence is still current enough to trust.",
            "primary_target_closure_forecast_decay_status": "none",
            "primary_target_closure_forecast_decay_reason": "",
            "closure_forecast_freshness_summary": "RepoC still has fresh closure-forecast evidence.",
            "closure_forecast_decay_summary": "No closure-forecast decay is active right now.",
            "stale_closure_forecast_hotspots": [],
            "fresh_closure_forecast_signal_hotspots": [],
            "closure_forecast_decay_window_runs": 4,
        }

    monkeypatch.setattr(
        "src.operator_control_center._apply_closure_forecast_freshness_and_decay",
        _phase43_seed,
    )
    monkeypatch.setattr(
        "src.operator_control_center._target_specific_normalization_noise",
        lambda *_args, **_kwargs: False,
    )

    summary = build_operator_snapshot(report, output_dir=tmp_path)["operator_summary"]

    assert summary["primary_target_closure_forecast_refresh_recovery_status"] == "reacquiring-confirmation"
    assert summary["primary_target_closure_forecast_reacquisition_status"] == "reacquired-confirmation"
    assert summary["primary_target_transition_closure_likely_outcome"] == "confirm-soon"
    assert summary["primary_target_closure_forecast_hysteresis_status"] == "confirmed-confirmation"


def test_operator_snapshot_reenables_early_clear_when_clearance_is_reacquired(tmp_path: Path, monkeypatch):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    history = [
        {
            "generated_at": "2026-04-06T12:00:00+00:00",
            "operator_summary": {
                "primary_target": {
                    "item_id": "review-target:RepoC",
                    "repo": "RepoC",
                    "title": "RepoC security posture changed",
                    "lane": "urgent",
                    "kind": "review",
                },
                "primary_target_closure_forecast_reweight_direction": "supporting-clearance",
                "primary_target_closure_forecast_reweight_score": -0.42,
                "primary_target_closure_forecast_momentum_status": "sustained-clearance",
                "primary_target_closure_forecast_stability_status": "stable",
                "primary_target_closure_forecast_hysteresis_status": "pending-clearance",
                "primary_target_closure_forecast_freshness_status": "fresh",
                "primary_target_closure_forecast_decay_status": "none",
                "primary_target_transition_closure_likely_outcome": "clear-risk",
                "primary_target_class_reweight_transition_status": "pending-caution",
                "primary_target_class_transition_resolution_status": "none",
            },
            "operator_queue": [],
        },
        {
            "generated_at": "2026-04-05T12:00:00+00:00",
            "operator_summary": {
                "primary_target": {
                    "item_id": "review-target:RepoC",
                    "repo": "RepoC",
                    "title": "RepoC security posture changed",
                    "lane": "urgent",
                    "kind": "review",
                },
                "primary_target_closure_forecast_reweight_direction": "supporting-clearance",
                "primary_target_closure_forecast_reweight_score": -0.37,
                "primary_target_closure_forecast_momentum_status": "sustained-clearance",
                "primary_target_closure_forecast_stability_status": "stable",
                "primary_target_closure_forecast_hysteresis_status": "pending-clearance",
                "primary_target_closure_forecast_freshness_status": "fresh",
                "primary_target_closure_forecast_decay_status": "none",
                "primary_target_transition_closure_likely_outcome": "clear-risk",
                "primary_target_class_reweight_transition_status": "pending-caution",
                "primary_target_class_transition_resolution_status": "none",
            },
            "operator_queue": [],
        },
        {
            "generated_at": "2026-04-04T12:00:00+00:00",
            "operator_summary": {
                "primary_target": {
                    "item_id": "review-target:RepoC",
                    "repo": "RepoC",
                    "title": "RepoC security posture changed",
                    "lane": "urgent",
                    "kind": "review",
                },
                "primary_target_closure_forecast_reweight_direction": "supporting-clearance",
                "primary_target_closure_forecast_reweight_score": -0.29,
                "primary_target_closure_forecast_momentum_status": "building",
                "primary_target_closure_forecast_stability_status": "watch",
                "primary_target_closure_forecast_hysteresis_status": "pending-clearance",
                "primary_target_closure_forecast_freshness_status": "stale",
                "primary_target_closure_forecast_decay_status": "clearance-decayed",
                "primary_target_transition_closure_likely_outcome": "hold",
                "primary_target_class_reweight_transition_status": "pending-caution",
                "primary_target_class_transition_resolution_status": "none",
            },
            "operator_queue": [],
        },
    ]
    monkeypatch.setattr("src.operator_control_center.load_operator_state_history", lambda *_args, **_kwargs: history)

    def _phase43_seed(
        resolution_targets, _history, *, current_generated_at, confidence_calibration
    ):
        resolution_targets[:] = [
            {
                **target,
                "trust_policy": "verify-first",
                "trust_policy_reason": "Fresh pending debt is still making the live pending forecast more cautious.",
                "class_reweight_transition_status": "pending-caution",
                "class_reweight_transition_reason": "Caution-heavy class evidence is visible, but it has not persisted long enough to confirm yet.",
                "class_transition_resolution_status": "none",
                "class_transition_resolution_reason": "",
                "class_transition_age_runs": 3,
                "class_pending_debt_status": "active-debt",
                "class_pending_debt_reason": "This class keeps accumulating unresolved pending states.",
                "policy_debt_status": "watch",
                "policy_debt_reason": "",
                "closure_forecast_reweight_score": -0.46,
                "closure_forecast_reweight_direction": "supporting-clearance",
                "closure_forecast_momentum_status": "sustained-clearance",
                "closure_forecast_stability_status": "stable",
                "closure_forecast_hysteresis_status": "none",
                "closure_forecast_hysteresis_reason": "",
                "closure_forecast_freshness_status": "fresh",
                "closure_forecast_freshness_reason": "Recent closure-forecast evidence is still current enough to trust.",
                "closure_forecast_decay_status": "none",
                "closure_forecast_decay_reason": "",
                "decayed_confirmation_forecast_rate": 0.15,
                "decayed_clearance_forecast_rate": 0.78,
                "transition_closure_likely_outcome": "hold",
            }
            for target in resolution_targets
        ]
        return {
            "primary_target_closure_forecast_freshness_status": "fresh",
            "primary_target_closure_forecast_freshness_reason": "Recent closure-forecast evidence is still current enough to trust.",
            "primary_target_closure_forecast_decay_status": "none",
            "primary_target_closure_forecast_decay_reason": "",
            "closure_forecast_freshness_summary": "RepoC still has fresh closure-forecast evidence.",
            "closure_forecast_decay_summary": "No closure-forecast decay is active right now.",
            "stale_closure_forecast_hotspots": [],
            "fresh_closure_forecast_signal_hotspots": [],
            "closure_forecast_decay_window_runs": 4,
        }

    monkeypatch.setattr(
        "src.operator_control_center._apply_closure_forecast_freshness_and_decay",
        _phase43_seed,
    )

    summary = build_operator_snapshot(report, output_dir=tmp_path)["operator_summary"]

    assert summary["primary_target_closure_forecast_refresh_recovery_status"] == "reacquiring-clearance"
    assert summary["primary_target_closure_forecast_reacquisition_status"] == "reacquired-clearance"
    assert summary["primary_target_transition_closure_likely_outcome"] in {"clear-risk", "expire-risk"}
    assert summary["primary_target_class_transition_resolution_status"] == "cleared"
    assert summary["primary_target_class_reweight_transition_status"] == "none"


def test_operator_snapshot_marks_new_confirmation_reacquisition_as_fragile(tmp_path: Path, monkeypatch):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    monkeypatch.setattr("src.operator_control_center.load_operator_state_history", lambda *_args, **_kwargs: [])

    def _phase44_seed(
        resolution_targets, _history, *, current_generated_at, confidence_calibration
    ):
        resolution_targets[:] = [
            {
                **target,
                "trust_policy": "verify-first",
                "trust_policy_reason": "Fresh confirmation-side support just re-earned a stronger forecast posture.",
                "class_reweight_transition_status": "pending-support",
                "class_reweight_transition_reason": "The class signal is still visible while confirmation-side recovery rebuilds.",
                "class_transition_resolution_status": "none",
                "class_transition_resolution_reason": "",
                "class_transition_age_runs": 2,
                "closure_forecast_reweight_score": 0.48,
                "closure_forecast_reweight_direction": "supporting-confirmation",
                "closure_forecast_momentum_status": "sustained-confirmation",
                "closure_forecast_stability_status": "stable",
                "closure_forecast_hysteresis_status": "confirmed-confirmation",
                "closure_forecast_hysteresis_reason": "Fresh class follow-through has stayed strong enough to keep the stronger confirmation forecast in place.",
                "closure_forecast_freshness_status": "fresh",
                "closure_forecast_freshness_reason": "Recent closure-forecast evidence is still current enough to trust.",
                "closure_forecast_decay_status": "none",
                "closure_forecast_decay_reason": "",
                "closure_forecast_refresh_recovery_score": 0.29,
                "closure_forecast_refresh_recovery_status": "reacquiring-confirmation",
                "closure_forecast_reacquisition_status": "reacquired-confirmation",
                "closure_forecast_reacquisition_reason": "Fresh confirmation-side support has stayed strong enough to earn back stronger confirmation forecasting.",
                "transition_closure_likely_outcome": "confirm-soon",
            }
            for target in resolution_targets
        ]
        return {
            "primary_target_closure_forecast_refresh_recovery_score": 0.29,
            "primary_target_closure_forecast_refresh_recovery_status": "reacquiring-confirmation",
            "primary_target_closure_forecast_reacquisition_status": "reacquired-confirmation",
            "primary_target_closure_forecast_reacquisition_reason": "Fresh confirmation-side support has stayed strong enough to earn back stronger confirmation forecasting.",
            "closure_forecast_refresh_recovery_summary": "Fresh confirmation-side support around RepoC is strong enough that stronger forecast carry-forward may be earned back soon (0.29).",
            "closure_forecast_reacquisition_summary": "Fresh confirmation-side support has stayed strong enough to earn back stronger confirmation forecasting.",
            "closure_forecast_refresh_window_runs": 4,
            "recovering_confirmation_hotspots": [],
            "recovering_clearance_hotspots": [],
        }

    monkeypatch.setattr(
        "src.operator_control_center._apply_closure_forecast_refresh_recovery_and_reacquisition",
        _phase44_seed,
    )
    monkeypatch.setattr(
        "src.operator_control_center._target_specific_normalization_noise",
        lambda *_args, **_kwargs: False,
    )

    summary = build_operator_snapshot(report, output_dir=tmp_path)["operator_summary"]

    assert summary["primary_target_closure_forecast_reacquisition_persistence_status"] == "just-reacquired"
    assert summary["primary_target_closure_forecast_recovery_churn_status"] == "none"
    assert summary["primary_target_transition_closure_likely_outcome"] == "confirm-soon"


def test_operator_snapshot_keeps_confirmation_reacquisition_when_it_is_holding(tmp_path: Path, monkeypatch):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    history = [
        {
            "generated_at": "2026-04-06T12:00:00+00:00",
            "operator_summary": {
                "primary_target": {
                    "item_id": "review-target:RepoC",
                    "repo": "RepoC",
                    "title": "RepoC security posture changed",
                    "lane": "urgent",
                    "kind": "review",
                },
                "primary_target_closure_forecast_reweight_direction": "supporting-confirmation",
                "primary_target_closure_forecast_reweight_score": 0.42,
                "primary_target_closure_forecast_momentum_status": "sustained-confirmation",
                "primary_target_closure_forecast_stability_status": "stable",
                "primary_target_closure_forecast_freshness_status": "fresh",
                "primary_target_closure_forecast_decay_status": "none",
                "primary_target_closure_forecast_refresh_recovery_status": "reacquiring-confirmation",
                "primary_target_closure_forecast_reacquisition_status": "reacquired-confirmation",
                "primary_target_transition_closure_likely_outcome": "confirm-soon",
            },
            "operator_queue": [],
        },
        {
            "generated_at": "2026-04-05T12:00:00+00:00",
            "operator_summary": {
                "primary_target": {
                    "item_id": "review-target:RepoC",
                    "repo": "RepoC",
                    "title": "RepoC security posture changed",
                    "lane": "urgent",
                    "kind": "review",
                },
                "primary_target_closure_forecast_reweight_direction": "supporting-confirmation",
                "primary_target_closure_forecast_reweight_score": 0.37,
                "primary_target_closure_forecast_momentum_status": "sustained-confirmation",
                "primary_target_closure_forecast_stability_status": "stable",
                "primary_target_closure_forecast_freshness_status": "fresh",
                "primary_target_closure_forecast_decay_status": "none",
                "primary_target_closure_forecast_refresh_recovery_status": "recovering-confirmation",
                "primary_target_closure_forecast_reacquisition_status": "pending-confirmation-reacquisition",
                "primary_target_transition_closure_likely_outcome": "hold",
            },
            "operator_queue": [],
        },
    ]
    monkeypatch.setattr("src.operator_control_center.load_operator_state_history", lambda *_args, **_kwargs: history)

    def _phase44_seed(
        resolution_targets, _history, *, current_generated_at, confidence_calibration
    ):
        resolution_targets[:] = [
            {
                **target,
                "trust_policy": "verify-first",
                "trust_policy_reason": "Fresh confirmation-side support re-earned a stronger forecast posture.",
                "class_reweight_transition_status": "pending-support",
                "class_reweight_transition_reason": "The class signal is still visible while confirmation-side recovery holds.",
                "class_transition_resolution_status": "none",
                "class_transition_resolution_reason": "",
                "class_transition_age_runs": 2,
                "closure_forecast_reweight_score": 0.51,
                "closure_forecast_reweight_direction": "supporting-confirmation",
                "closure_forecast_momentum_status": "sustained-confirmation",
                "closure_forecast_stability_status": "stable",
                "closure_forecast_hysteresis_status": "confirmed-confirmation",
                "closure_forecast_hysteresis_reason": "Fresh class follow-through has stayed strong enough to keep the stronger confirmation forecast in place.",
                "closure_forecast_freshness_status": "fresh",
                "closure_forecast_freshness_reason": "Recent closure-forecast evidence is still current enough to trust.",
                "closure_forecast_decay_status": "none",
                "closure_forecast_decay_reason": "",
                "closure_forecast_refresh_recovery_score": 0.31,
                "closure_forecast_refresh_recovery_status": "reacquiring-confirmation",
                "closure_forecast_reacquisition_status": "reacquired-confirmation",
                "closure_forecast_reacquisition_reason": "Fresh confirmation-side support has stayed strong enough to earn back stronger confirmation forecasting.",
                "transition_closure_likely_outcome": "confirm-soon",
            }
            for target in resolution_targets
        ]
        return {
            "primary_target_closure_forecast_refresh_recovery_score": 0.31,
            "primary_target_closure_forecast_refresh_recovery_status": "reacquiring-confirmation",
            "primary_target_closure_forecast_reacquisition_status": "reacquired-confirmation",
            "primary_target_closure_forecast_reacquisition_reason": "Fresh confirmation-side support has stayed strong enough to earn back stronger confirmation forecasting.",
            "closure_forecast_refresh_recovery_summary": "Fresh confirmation-side support around RepoC is strong enough that stronger forecast carry-forward may be earned back soon (0.31).",
            "closure_forecast_reacquisition_summary": "Fresh confirmation-side support has stayed strong enough to earn back stronger confirmation forecasting.",
            "closure_forecast_refresh_window_runs": 4,
            "recovering_confirmation_hotspots": [],
            "recovering_clearance_hotspots": [],
        }

    monkeypatch.setattr(
        "src.operator_control_center._apply_closure_forecast_refresh_recovery_and_reacquisition",
        _phase44_seed,
    )
    monkeypatch.setattr(
        "src.operator_control_center._target_specific_normalization_noise",
        lambda *_args, **_kwargs: False,
    )

    summary = build_operator_snapshot(report, output_dir=tmp_path)["operator_summary"]

    assert summary["primary_target_closure_forecast_reacquisition_persistence_status"] == "sustained-confirmation"
    assert summary["primary_target_closure_forecast_recovery_churn_status"] == "none"
    assert summary["primary_target_transition_closure_likely_outcome"] == "confirm-soon"


def test_operator_snapshot_softens_reacquired_clearance_when_recovery_churns(tmp_path: Path, monkeypatch):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    history = [
        {
            "generated_at": "2026-04-06T12:00:00+00:00",
            "operator_summary": {
                "primary_target": {
                    "item_id": "review-target:RepoC",
                    "repo": "RepoC",
                    "title": "RepoC security posture changed",
                    "lane": "urgent",
                    "kind": "review",
                },
                "primary_target_closure_forecast_reweight_direction": "supporting-confirmation",
                "primary_target_closure_forecast_reweight_score": 0.34,
                "primary_target_closure_forecast_momentum_status": "reversing",
                "primary_target_closure_forecast_stability_status": "oscillating",
                "primary_target_closure_forecast_freshness_status": "fresh",
                "primary_target_closure_forecast_decay_status": "none",
                "primary_target_closure_forecast_refresh_recovery_status": "recovering-confirmation",
                "primary_target_closure_forecast_reacquisition_status": "pending-confirmation-reacquisition",
                "primary_target_transition_closure_likely_outcome": "hold",
                "primary_target_class_reweight_transition_status": "pending-caution",
                "primary_target_class_transition_resolution_status": "none",
            },
            "operator_queue": [],
        },
        {
            "generated_at": "2026-04-05T12:00:00+00:00",
            "operator_summary": {
                "primary_target": {
                    "item_id": "review-target:RepoC",
                    "repo": "RepoC",
                    "title": "RepoC security posture changed",
                    "lane": "urgent",
                    "kind": "review",
                },
                "primary_target_closure_forecast_reweight_direction": "supporting-clearance",
                "primary_target_closure_forecast_reweight_score": -0.39,
                "primary_target_closure_forecast_momentum_status": "sustained-clearance",
                "primary_target_closure_forecast_stability_status": "stable",
                "primary_target_closure_forecast_freshness_status": "fresh",
                "primary_target_closure_forecast_decay_status": "none",
                "primary_target_closure_forecast_refresh_recovery_status": "reacquiring-clearance",
                "primary_target_closure_forecast_reacquisition_status": "reacquired-clearance",
                "primary_target_transition_closure_likely_outcome": "clear-risk",
                "primary_target_class_reweight_transition_status": "none",
                "primary_target_class_transition_resolution_status": "cleared",
            },
            "operator_queue": [],
        },
    ]
    monkeypatch.setattr("src.operator_control_center.load_operator_state_history", lambda *_args, **_kwargs: history)

    def _phase44_seed(
        resolution_targets, _history, *, current_generated_at, confidence_calibration
    ):
        resolution_targets[:] = [
            {
                **target,
                "trust_policy": "verify-first",
                "trust_policy_reason": "Fresh clearance-side pressure re-earned a stronger forecast posture.",
                "class_reweight_transition_status": "none",
                "class_reweight_transition_reason": "Fresh clearance-side pressure had re-enabled an earlier clear.",
                "class_transition_resolution_status": "cleared",
                "class_transition_resolution_reason": "Fresh clearance-side pressure had re-earned the earlier forecast-driven clearance posture.",
                "class_transition_age_runs": 3,
                "closure_forecast_reweight_score": -0.43,
                "closure_forecast_reweight_direction": "supporting-clearance",
                "closure_forecast_momentum_status": "reversing",
                "closure_forecast_stability_status": "oscillating",
                "closure_forecast_hysteresis_status": "confirmed-clearance",
                "closure_forecast_hysteresis_reason": "Fresh unresolved pending debt has stayed strong enough to keep the stronger clearance forecast in place.",
                "closure_forecast_freshness_status": "fresh",
                "closure_forecast_freshness_reason": "Recent closure-forecast evidence is still current enough to trust.",
                "closure_forecast_decay_status": "none",
                "closure_forecast_decay_reason": "",
                "closure_forecast_refresh_recovery_score": -0.31,
                "closure_forecast_refresh_recovery_status": "reacquiring-clearance",
                "closure_forecast_reacquisition_status": "reacquired-clearance",
                "closure_forecast_reacquisition_reason": "Fresh clearance-side pressure has stayed strong enough to earn back stronger clearance forecasting.",
                "transition_closure_likely_outcome": "clear-risk",
            }
            for target in resolution_targets
        ]
        return {
            "primary_target_closure_forecast_refresh_recovery_score": -0.31,
            "primary_target_closure_forecast_refresh_recovery_status": "reacquiring-clearance",
            "primary_target_closure_forecast_reacquisition_status": "reacquired-clearance",
            "primary_target_closure_forecast_reacquisition_reason": "Fresh clearance-side pressure has stayed strong enough to earn back stronger clearance forecasting.",
            "closure_forecast_refresh_recovery_summary": "Fresh clearance-side pressure around RepoC is strong enough that stronger forecast carry-forward may be earned back soon (-0.31).",
            "closure_forecast_reacquisition_summary": "Fresh clearance-side pressure has stayed strong enough to earn back stronger clearance forecasting.",
            "closure_forecast_refresh_window_runs": 4,
            "recovering_confirmation_hotspots": [],
            "recovering_clearance_hotspots": [],
        }

    monkeypatch.setattr(
        "src.operator_control_center._apply_closure_forecast_refresh_recovery_and_reacquisition",
        _phase44_seed,
    )
    monkeypatch.setattr(
        "src.operator_control_center._target_specific_normalization_noise",
        lambda *_args, **_kwargs: False,
    )

    summary = build_operator_snapshot(report, output_dir=tmp_path)["operator_summary"]

    assert summary["primary_target_closure_forecast_recovery_churn_status"] == "churn"
    assert summary["primary_target_transition_closure_likely_outcome"] == "hold"
    assert summary["primary_target_class_transition_resolution_status"] == "none"
    assert summary["primary_target_class_reweight_transition_status"] == "pending-caution"


def test_operator_snapshot_softens_sustained_reacquisition_when_freshness_turns_mixed_age(
    tmp_path: Path,
    monkeypatch,
):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    history = []
    for day, direction, reacq_status, persistence_status, outcome in [
        (6, "supporting-confirmation", "reacquired-confirmation", "sustained-confirmation", "confirm-soon"),
        (5, "supporting-confirmation", "reacquired-confirmation", "holding-confirmation", "confirm-soon"),
        (4, "supporting-clearance", "pending-clearance-reacquisition", "holding-clearance", "clear-risk"),
        (3, "supporting-confirmation", "reacquired-confirmation", "holding-confirmation", "confirm-soon"),
        (2, "supporting-confirmation", "reacquired-confirmation", "holding-confirmation", "confirm-soon"),
        (1, "supporting-confirmation", "reacquired-confirmation", "holding-confirmation", "confirm-soon"),
    ]:
        history.append(
            {
                "generated_at": f"2026-04-{day:02d}T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-target:RepoC",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_closure_forecast_reweight_direction": direction,
                    "primary_target_closure_forecast_reweight_score": 0.44 if direction == "supporting-confirmation" else -0.28,
                    "primary_target_closure_forecast_momentum_status": "sustained-confirmation" if direction == "supporting-confirmation" else "building",
                    "primary_target_closure_forecast_stability_status": "stable",
                    "primary_target_closure_forecast_freshness_status": "fresh",
                    "primary_target_closure_forecast_decay_status": "none",
                    "primary_target_closure_forecast_refresh_recovery_status": "reacquiring-confirmation" if direction == "supporting-confirmation" else "recovering-clearance",
                    "primary_target_closure_forecast_reacquisition_status": reacq_status,
                    "primary_target_closure_forecast_reacquisition_persistence_status": persistence_status,
                    "primary_target_closure_forecast_recovery_churn_status": "none",
                    "primary_target_transition_closure_likely_outcome": outcome,
                },
                "operator_queue": [],
            }
        )
    monkeypatch.setattr("src.operator_control_center.load_operator_state_history", lambda *_args, **_kwargs: history)

    def _phase44_seed(
        resolution_targets, _history, *, current_generated_at, confidence_calibration
    ):
        resolution_targets[:] = [
            {
                **target,
                "trust_policy": "verify-first",
                "trust_policy_reason": "Fresh confirmation-side support re-earned a stronger forecast posture.",
                "class_reweight_transition_status": "pending-support",
                "class_reweight_transition_reason": "The class signal is still visible while confirmation-side recovery holds.",
                "class_transition_resolution_status": "none",
                "class_transition_resolution_reason": "",
                "class_transition_age_runs": 2,
                "closure_forecast_reweight_score": 0.52,
                "closure_forecast_reweight_direction": "supporting-confirmation",
                "closure_forecast_momentum_status": "sustained-confirmation",
                "closure_forecast_stability_status": "stable",
                "closure_forecast_hysteresis_status": "confirmed-confirmation",
                "closure_forecast_hysteresis_reason": "Fresh class follow-through has stayed strong enough to keep the stronger confirmation forecast in place.",
                "closure_forecast_freshness_status": "fresh",
                "closure_forecast_freshness_reason": "Recent closure-forecast evidence is still current enough to trust.",
                "closure_forecast_decay_status": "none",
                "closure_forecast_decay_reason": "",
                "closure_forecast_refresh_recovery_score": 0.31,
                "closure_forecast_refresh_recovery_status": "reacquiring-confirmation",
                "closure_forecast_reacquisition_status": "reacquired-confirmation",
                "closure_forecast_reacquisition_reason": "Fresh confirmation-side support has stayed strong enough to earn back stronger confirmation forecasting.",
                "transition_closure_likely_outcome": "confirm-soon",
            }
            for target in resolution_targets
        ]
        return {
            "primary_target_closure_forecast_refresh_recovery_score": 0.31,
            "primary_target_closure_forecast_refresh_recovery_status": "reacquiring-confirmation",
            "primary_target_closure_forecast_reacquisition_status": "reacquired-confirmation",
            "primary_target_closure_forecast_reacquisition_reason": "Fresh confirmation-side support has stayed strong enough to earn back stronger confirmation forecasting.",
            "closure_forecast_refresh_recovery_summary": "Fresh confirmation-side support around RepoC is strong enough that stronger forecast carry-forward may be earned back soon (0.31).",
            "closure_forecast_reacquisition_summary": "Fresh confirmation-side support has stayed strong enough to earn back stronger confirmation forecasting.",
            "closure_forecast_refresh_window_runs": 4,
            "recovering_confirmation_hotspots": [],
            "recovering_clearance_hotspots": [],
        }

    monkeypatch.setattr(
        "src.operator_control_center._apply_closure_forecast_refresh_recovery_and_reacquisition",
        _phase44_seed,
    )
    monkeypatch.setattr(
        "src.operator_control_center._target_specific_normalization_noise",
        lambda *_args, **_kwargs: False,
    )

    summary = build_operator_snapshot(report, output_dir=tmp_path)["operator_summary"]

    assert summary["primary_target_closure_forecast_reacquisition_freshness_status"] == "mixed-age"
    assert summary["primary_target_closure_forecast_reacquisition_persistence_status"] == "holding-confirmation"
    assert summary["primary_target_closure_forecast_persistence_reset_status"] == "confirmation-softened"
    assert summary["primary_target_transition_closure_likely_outcome"] == "confirm-soon"


def test_operator_snapshot_resets_stale_reacquired_clearance_and_restores_pending_posture(
    tmp_path: Path,
    monkeypatch,
):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    history = []
    for day, direction, reacq_status, persistence_status, outcome, transition_status, resolution_status in [
        (6, "supporting-clearance", "pending-clearance-reacquisition", "holding-clearance", "clear-risk", "pending-caution", "none"),
        (5, "supporting-confirmation", "pending-confirmation-reacquisition", "holding-confirmation", "hold", "pending-caution", "none"),
        (4, "supporting-confirmation", "pending-confirmation-reacquisition", "holding-confirmation", "hold", "pending-caution", "none"),
        (3, "supporting-confirmation", "pending-confirmation-reacquisition", "holding-confirmation", "hold", "pending-caution", "none"),
        (2, "supporting-clearance", "reacquired-clearance", "holding-clearance", "clear-risk", "none", "cleared"),
        (1, "supporting-clearance", "reacquired-clearance", "holding-clearance", "clear-risk", "none", "cleared"),
    ]:
        history.append(
            {
                "generated_at": f"2026-04-{day:02d}T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-target:RepoC",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_closure_forecast_reweight_direction": direction,
                    "primary_target_closure_forecast_reweight_score": -0.43 if direction == "supporting-clearance" else 0.18,
                    "primary_target_closure_forecast_momentum_status": "sustained-clearance" if direction == "supporting-clearance" else "building",
                    "primary_target_closure_forecast_stability_status": "stable",
                    "primary_target_closure_forecast_freshness_status": "fresh",
                    "primary_target_closure_forecast_decay_status": "none",
                    "primary_target_closure_forecast_refresh_recovery_status": "reacquiring-clearance" if direction == "supporting-clearance" else "recovering-confirmation",
                    "primary_target_closure_forecast_reacquisition_status": reacq_status,
                    "primary_target_closure_forecast_reacquisition_persistence_status": persistence_status,
                    "primary_target_closure_forecast_recovery_churn_status": "none",
                    "primary_target_transition_closure_likely_outcome": outcome,
                    "primary_target_class_reweight_transition_status": transition_status,
                    "primary_target_class_transition_resolution_status": resolution_status,
                },
                "operator_queue": [],
            }
        )
    monkeypatch.setattr("src.operator_control_center.load_operator_state_history", lambda *_args, **_kwargs: history)

    def _phase44_seed(
        resolution_targets, _history, *, current_generated_at, confidence_calibration
    ):
        resolution_targets[:] = [
            {
                **target,
                "trust_policy": "verify-first",
                "trust_policy_reason": "Fresh clearance-side pressure re-earned a stronger forecast posture.",
                "class_reweight_transition_status": "none",
                "class_reweight_transition_reason": "Fresh clearance-side pressure had re-enabled an earlier clear.",
                "class_transition_resolution_status": "cleared",
                "class_transition_resolution_reason": "Fresh clearance-side pressure had re-earned the earlier forecast-driven clearance posture.",
                "class_transition_age_runs": 3,
                "closure_forecast_reweight_score": -0.46,
                "closure_forecast_reweight_direction": "supporting-clearance",
                "closure_forecast_momentum_status": "sustained-clearance",
                "closure_forecast_stability_status": "stable",
                "closure_forecast_hysteresis_status": "confirmed-clearance",
                "closure_forecast_hysteresis_reason": "Fresh unresolved pending debt has stayed strong enough to keep the stronger clearance forecast in place.",
                "closure_forecast_freshness_status": "fresh",
                "closure_forecast_freshness_reason": "Recent closure-forecast evidence is still current enough to trust.",
                "closure_forecast_decay_status": "none",
                "closure_forecast_decay_reason": "",
                "closure_forecast_refresh_recovery_score": -0.31,
                "closure_forecast_refresh_recovery_status": "reacquiring-clearance",
                "closure_forecast_reacquisition_status": "reacquired-clearance",
                "closure_forecast_reacquisition_reason": "Fresh clearance-side pressure has stayed strong enough to earn back stronger clearance forecasting.",
                "transition_closure_likely_outcome": "clear-risk",
            }
            for target in resolution_targets
        ]
        return {
            "primary_target_closure_forecast_refresh_recovery_score": -0.31,
            "primary_target_closure_forecast_refresh_recovery_status": "reacquiring-clearance",
            "primary_target_closure_forecast_reacquisition_status": "reacquired-clearance",
            "primary_target_closure_forecast_reacquisition_reason": "Fresh clearance-side pressure has stayed strong enough to earn back stronger clearance forecasting.",
            "closure_forecast_refresh_recovery_summary": "Fresh clearance-side pressure around RepoC is strong enough that stronger forecast carry-forward may be earned back soon (-0.31).",
            "closure_forecast_reacquisition_summary": "Fresh clearance-side pressure has stayed strong enough to earn back stronger clearance forecasting.",
            "closure_forecast_refresh_window_runs": 4,
            "recovering_confirmation_hotspots": [],
            "recovering_clearance_hotspots": [],
        }

    monkeypatch.setattr(
        "src.operator_control_center._apply_closure_forecast_refresh_recovery_and_reacquisition",
        _phase44_seed,
    )
    monkeypatch.setattr(
        "src.operator_control_center._target_specific_normalization_noise",
        lambda *_args, **_kwargs: False,
    )

    summary = build_operator_snapshot(report, output_dir=tmp_path)["operator_summary"]

    assert summary["primary_target_closure_forecast_reacquisition_freshness_status"] == "stale"
    assert summary["primary_target_closure_forecast_persistence_reset_status"] == "clearance-reset"
    assert summary["primary_target_closure_forecast_reacquisition_status"] == "none"
    assert summary["primary_target_closure_forecast_reacquisition_persistence_status"] == "none"
    assert summary["primary_target_transition_closure_likely_outcome"] == "hold"
    assert summary["primary_target_class_transition_resolution_status"] == "none"
    assert summary["primary_target_class_reweight_transition_status"] == "pending-caution"


def test_operator_snapshot_sets_pending_confirmation_reentry_after_confirmation_reset(
    tmp_path: Path,
    monkeypatch,
):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    monkeypatch.setattr(
        "src.operator_control_center.load_operator_state_history",
        lambda *_args, **_kwargs: [
            {
                "generated_at": "2026-04-06T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-target:RepoC",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_closure_forecast_reweight_direction": "supporting-confirmation",
                    "primary_target_closure_forecast_reweight_score": 0.18,
                    "primary_target_closure_forecast_reacquisition_freshness_status": "fresh",
                    "primary_target_closure_forecast_persistence_reset_status": "confirmation-reset",
                    "primary_target_transition_closure_likely_outcome": "hold",
                },
                "operator_queue": [],
            }
        ],
    )

    def _phase46_seed(
        resolution_targets, _history, *, current_generated_at, confidence_calibration
    ):
        resolution_targets[:] = [
            {
                **target,
                "closure_forecast_reweight_score": 0.22,
                "closure_forecast_reweight_direction": "supporting-confirmation",
                "closure_forecast_momentum_status": "building",
                "closure_forecast_stability_status": "stable",
                "closure_forecast_hysteresis_status": "pending-confirmation",
                "closure_forecast_hysteresis_reason": "The stronger confirmation posture was reset while fresh evidence was still rebuilding.",
                "closure_forecast_reacquisition_freshness_status": "fresh",
                "closure_forecast_reacquisition_freshness_reason": "Recent reacquired closure-forecast evidence is current enough to rebuild safely.",
                "closure_forecast_reacquisition_memory_weight": 0.6,
                "decayed_reacquired_confirmation_rate": 0.62,
                "decayed_reacquired_clearance_rate": 0.08,
                "recent_reacquisition_signal_mix": "confirmation-led",
                "closure_forecast_persistence_reset_status": "confirmation-reset",
                "closure_forecast_persistence_reset_reason": "Restored confirmation-side posture has aged out enough that the stronger carry-forward has been withdrawn.",
                "closure_forecast_reacquisition_status": "none",
                "closure_forecast_reacquisition_reason": "Restored confirmation-side posture has aged out enough that the stronger carry-forward has been withdrawn.",
                "closure_forecast_reacquisition_age_runs": 0,
                "closure_forecast_reacquisition_persistence_score": 0.0,
                "closure_forecast_reacquisition_persistence_status": "none",
                "closure_forecast_reacquisition_persistence_reason": "",
                "transition_closure_likely_outcome": "hold",
                "class_reweight_transition_status": "pending-support",
                "class_reweight_transition_reason": "The pending confirmation posture is still the weaker current-run state.",
                "class_transition_resolution_status": "none",
                "class_transition_resolution_reason": "",
            }
            for target in resolution_targets
        ]
        return {
            "primary_target_closure_forecast_reacquisition_freshness_status": "fresh",
            "primary_target_closure_forecast_reacquisition_freshness_reason": "Recent reacquired closure-forecast evidence is current enough to rebuild safely.",
            "closure_forecast_reacquisition_freshness_summary": "RepoC still has fresh reacquired closure-forecast evidence that is current enough to rebuild safely.",
            "primary_target_closure_forecast_persistence_reset_status": "confirmation-reset",
            "primary_target_closure_forecast_persistence_reset_reason": "Restored confirmation-side posture has aged out enough that the stronger carry-forward has been withdrawn.",
            "closure_forecast_persistence_reset_summary": "Restored confirmation-side posture for RepoC has aged out enough that the stronger carry-forward has been withdrawn.",
            "stale_reacquisition_hotspots": [],
            "fresh_reacquisition_signal_hotspots": [],
            "closure_forecast_reacquisition_decay_window_runs": 4,
        }

    monkeypatch.setattr(
        "src.operator_control_center._apply_reacquisition_freshness_and_persistence_reset",
        _phase46_seed,
    )
    monkeypatch.setattr(
        "src.operator_control_center._target_specific_normalization_noise",
        lambda *_args, **_kwargs: False,
    )

    summary = build_operator_snapshot(report, output_dir=tmp_path)["operator_summary"]

    assert summary["primary_target_closure_forecast_reset_refresh_recovery_status"] == "recovering-confirmation-reset"
    assert summary["primary_target_closure_forecast_reset_reentry_status"] == "pending-confirmation-reentry"
    assert summary["primary_target_closure_forecast_reset_reentry_persistence_status"] in {"none", "insufficient-data"}
    assert summary["primary_target_closure_forecast_reset_reentry_churn_status"] == "none"
    assert summary["primary_target_closure_forecast_reacquisition_status"] == "pending-confirmation-reacquisition"
    assert summary["primary_target_transition_closure_likely_outcome"] == "hold"
    assert summary["primary_target_closure_forecast_hysteresis_status"] == "pending-confirmation"


def test_operator_snapshot_reenters_confirmation_after_fresh_follow_through(
    tmp_path: Path,
    monkeypatch,
):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    monkeypatch.setattr(
        "src.operator_control_center.load_operator_state_history",
        lambda *_args, **_kwargs: [
            {
                "generated_at": "2026-04-06T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-target:RepoC",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_closure_forecast_reweight_direction": "supporting-confirmation",
                    "primary_target_closure_forecast_reweight_score": 0.38,
                    "primary_target_closure_forecast_reacquisition_freshness_status": "fresh",
                    "primary_target_closure_forecast_persistence_reset_status": "none",
                    "primary_target_transition_closure_likely_outcome": "hold",
                },
                "operator_queue": [],
            },
            {
                "generated_at": "2026-04-05T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-target:RepoC",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_closure_forecast_reweight_direction": "supporting-confirmation",
                    "primary_target_closure_forecast_reweight_score": 0.20,
                    "primary_target_closure_forecast_reacquisition_freshness_status": "fresh",
                    "primary_target_closure_forecast_persistence_reset_status": "confirmation-reset",
                    "primary_target_transition_closure_likely_outcome": "hold",
                },
                "operator_queue": [],
            },
        ],
    )

    def _phase46_seed(
        resolution_targets, _history, *, current_generated_at, confidence_calibration
    ):
        resolution_targets[:] = [
            {
                **target,
                "closure_forecast_reweight_score": 0.42,
                "closure_forecast_reweight_direction": "supporting-confirmation",
                "closure_forecast_momentum_status": "sustained-confirmation",
                "closure_forecast_stability_status": "stable",
                "closure_forecast_hysteresis_status": "pending-confirmation",
                "closure_forecast_hysteresis_reason": "Fresh confirmation-side follow-through is rebuilding after the reset.",
                "closure_forecast_reacquisition_freshness_status": "fresh",
                "closure_forecast_reacquisition_freshness_reason": "Recent reacquired closure-forecast evidence is current enough to rebuild safely.",
                "closure_forecast_reacquisition_memory_weight": 0.7,
                "decayed_reacquired_confirmation_rate": 0.71,
                "decayed_reacquired_clearance_rate": 0.04,
                "recent_reacquisition_signal_mix": "confirmation-led",
                "closure_forecast_persistence_reset_status": "none",
                "closure_forecast_persistence_reset_reason": "",
                "closure_forecast_reacquisition_status": "none",
                "closure_forecast_reacquisition_reason": "",
                "closure_forecast_reacquisition_age_runs": 0,
                "closure_forecast_reacquisition_persistence_score": 0.0,
                "closure_forecast_reacquisition_persistence_status": "none",
                "closure_forecast_reacquisition_persistence_reason": "",
                "transition_closure_likely_outcome": "hold",
                "class_reweight_transition_status": "pending-support",
                "class_reweight_transition_reason": "The pending confirmation posture is still the weaker current-run state.",
                "class_transition_resolution_status": "none",
                "class_transition_resolution_reason": "",
            }
            for target in resolution_targets
        ]
        return {
            "primary_target_closure_forecast_reacquisition_freshness_status": "fresh",
            "primary_target_closure_forecast_reacquisition_freshness_reason": "Recent reacquired closure-forecast evidence is current enough to rebuild safely.",
            "closure_forecast_reacquisition_freshness_summary": "RepoC still has fresh reacquired closure-forecast evidence that is current enough to rebuild safely.",
            "primary_target_closure_forecast_persistence_reset_status": "none",
            "primary_target_closure_forecast_persistence_reset_reason": "",
            "closure_forecast_persistence_reset_summary": "No persistence reset is changing the current restored closure-forecast posture right now.",
            "stale_reacquisition_hotspots": [],
            "fresh_reacquisition_signal_hotspots": [],
            "closure_forecast_reacquisition_decay_window_runs": 4,
        }

    monkeypatch.setattr(
        "src.operator_control_center._apply_reacquisition_freshness_and_persistence_reset",
        _phase46_seed,
    )
    monkeypatch.setattr(
        "src.operator_control_center._target_specific_normalization_noise",
        lambda *_args, **_kwargs: False,
    )

    summary = build_operator_snapshot(report, output_dir=tmp_path)["operator_summary"]

    assert summary["primary_target_closure_forecast_reset_refresh_recovery_status"] == "reentering-confirmation"
    assert summary["primary_target_closure_forecast_reset_reentry_status"] == "reentered-confirmation"
    assert summary["primary_target_closure_forecast_reset_reentry_persistence_status"] == "just-reentered"
    assert summary["primary_target_closure_forecast_reset_reentry_churn_status"] == "none"
    assert summary["primary_target_closure_forecast_reacquisition_status"] == "reacquired-confirmation"
    assert summary["primary_target_transition_closure_likely_outcome"] == "confirm-soon"
    assert summary["primary_target_closure_forecast_hysteresis_status"] == "confirmed-confirmation"


def test_operator_snapshot_reenters_clearance_after_fresh_follow_through(
    tmp_path: Path,
    monkeypatch,
):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    monkeypatch.setattr(
        "src.operator_control_center.load_operator_state_history",
        lambda *_args, **_kwargs: [
            {
                "generated_at": "2026-04-06T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-target:RepoC",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_closure_forecast_reweight_direction": "supporting-clearance",
                    "primary_target_closure_forecast_reweight_score": -0.34,
                    "primary_target_closure_forecast_reacquisition_freshness_status": "fresh",
                    "primary_target_closure_forecast_reset_reentry_status": "reentered-clearance",
                    "primary_target_closure_forecast_reset_reentry_persistence_status": "holding-clearance-reentry",
                    "primary_target_closure_forecast_reset_reentry_churn_status": "none",
                    "primary_target_closure_forecast_persistence_reset_status": "none",
                    "primary_target_closure_forecast_hysteresis_status": "confirmed-clearance",
                    "primary_target_transition_closure_likely_outcome": "clear-risk",
                    "primary_target_class_reweight_transition_status": "pending-caution",
                },
                "operator_queue": [],
            },
            {
                "generated_at": "2026-04-05T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-target:RepoC",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_closure_forecast_reweight_direction": "supporting-clearance",
                    "primary_target_closure_forecast_reweight_score": -0.18,
                    "primary_target_closure_forecast_reacquisition_freshness_status": "fresh",
                    "primary_target_closure_forecast_persistence_reset_status": "clearance-reset",
                    "primary_target_transition_closure_likely_outcome": "hold",
                    "primary_target_class_reweight_transition_status": "pending-caution",
                },
                "operator_queue": [],
            },
        ],
    )

    def _phase46_seed(
        resolution_targets, _history, *, current_generated_at, confidence_calibration
    ):
        resolution_targets[:] = [
            {
                **target,
                "class_transition_age_runs": 3,
                "closure_forecast_reweight_score": -0.41,
                "closure_forecast_reweight_direction": "supporting-clearance",
                "closure_forecast_momentum_status": "sustained-clearance",
                "closure_forecast_stability_status": "stable",
                "closure_forecast_hysteresis_status": "pending-clearance",
                "closure_forecast_hysteresis_reason": "Fresh clearance-side pressure is rebuilding after the reset.",
                "closure_forecast_reacquisition_freshness_status": "fresh",
                "closure_forecast_reacquisition_freshness_reason": "Recent reacquired closure-forecast evidence is current enough to rebuild safely.",
                "closure_forecast_reacquisition_memory_weight": 0.7,
                "decayed_reacquired_confirmation_rate": 0.04,
                "decayed_reacquired_clearance_rate": 0.61,
                "recent_reacquisition_signal_mix": "clearance-led",
                "closure_forecast_persistence_reset_status": "none",
                "closure_forecast_persistence_reset_reason": "",
                "closure_forecast_reacquisition_status": "none",
                "closure_forecast_reacquisition_reason": "",
                "closure_forecast_reacquisition_age_runs": 0,
                "closure_forecast_reacquisition_persistence_score": 0.0,
                "closure_forecast_reacquisition_persistence_status": "none",
                "closure_forecast_reacquisition_persistence_reason": "",
                "transition_closure_likely_outcome": "hold",
                "class_reweight_transition_status": "none",
                "class_reweight_transition_reason": "",
                "class_transition_resolution_status": "none",
                "class_transition_resolution_reason": "",
            }
            for target in resolution_targets
        ]
        return {
            "primary_target_closure_forecast_reacquisition_freshness_status": "fresh",
            "primary_target_closure_forecast_reacquisition_freshness_reason": "Recent reacquired closure-forecast evidence is current enough to rebuild safely.",
            "closure_forecast_reacquisition_freshness_summary": "RepoC still has fresh reacquired closure-forecast evidence that is current enough to rebuild safely.",
            "primary_target_closure_forecast_persistence_reset_status": "none",
            "primary_target_closure_forecast_persistence_reset_reason": "",
            "closure_forecast_persistence_reset_summary": "No persistence reset is changing the current restored closure-forecast posture right now.",
            "stale_reacquisition_hotspots": [],
            "fresh_reacquisition_signal_hotspots": [],
            "closure_forecast_reacquisition_decay_window_runs": 4,
        }

    monkeypatch.setattr(
        "src.operator_control_center._apply_reacquisition_freshness_and_persistence_reset",
        _phase46_seed,
    )
    monkeypatch.setattr(
        "src.operator_control_center._target_specific_normalization_noise",
        lambda *_args, **_kwargs: False,
    )

    summary = build_operator_snapshot(report, output_dir=tmp_path)["operator_summary"]

    assert summary["primary_target_closure_forecast_reset_refresh_recovery_status"] == "reentering-clearance"
    assert summary["primary_target_closure_forecast_reset_reentry_status"] == "reentered-clearance"
    assert summary["primary_target_closure_forecast_reset_reentry_persistence_status"] == "holding-clearance-reentry"
    assert summary["primary_target_closure_forecast_reset_reentry_churn_status"] == "none"
    assert summary["primary_target_closure_forecast_reset_reentry_freshness_status"] == "fresh"
    assert summary["primary_target_closure_forecast_reset_reentry_reset_status"] == "none"
    assert summary["primary_target_closure_forecast_reacquisition_status"] == "reacquired-clearance"
    assert summary["primary_target_transition_closure_likely_outcome"] == "clear-risk"
    assert summary["primary_target_closure_forecast_hysteresis_status"] == "confirmed-clearance"


def test_operator_snapshot_holds_reset_reentry_when_follow_through_stays_aligned(
    tmp_path: Path,
    monkeypatch,
):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    monkeypatch.setattr(
        "src.operator_control_center.load_operator_state_history",
        lambda *_args, **_kwargs: [
            {
                "generated_at": "2026-04-06T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-target:RepoC",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_closure_forecast_reweight_direction": "supporting-confirmation",
                    "primary_target_closure_forecast_reweight_score": 0.36,
                    "primary_target_closure_forecast_momentum_status": "sustained-confirmation",
                    "primary_target_closure_forecast_stability_status": "stable",
                    "primary_target_closure_forecast_reacquisition_freshness_status": "fresh",
                    "primary_target_closure_forecast_reset_refresh_recovery_status": "reentering-confirmation",
                    "primary_target_closure_forecast_reset_reentry_status": "reentered-confirmation",
                    "primary_target_transition_closure_likely_outcome": "confirm-soon",
                },
                "operator_queue": [],
            }
        ],
    )

    def _phase47_seed(
        resolution_targets, _history, *, current_generated_at, confidence_calibration
    ):
        resolution_targets[:] = [
            {
                **target,
                "closure_forecast_reweight_score": 0.42,
                "closure_forecast_reweight_direction": "supporting-confirmation",
                "closure_forecast_momentum_status": "sustained-confirmation",
                "closure_forecast_stability_status": "stable",
                "closure_forecast_reacquisition_freshness_status": "fresh",
                "closure_forecast_hysteresis_status": "confirmed-confirmation",
                "closure_forecast_hysteresis_reason": "Fresh confirmation-side follow-through has re-earned re-entry into stronger confirmation-side reacquisition.",
                "closure_forecast_reset_refresh_recovery_score": 0.33,
                "closure_forecast_reset_refresh_recovery_status": "reentering-confirmation",
                "closure_forecast_reset_reentry_status": "reentered-confirmation",
                "closure_forecast_reset_reentry_reason": "Fresh confirmation-side follow-through has re-earned re-entry into stronger confirmation-side reacquisition.",
                "recent_reset_refresh_path": "confirmation-reset -> fresh confirmation -> fresh confirmation",
                "closure_forecast_reacquisition_status": "reacquired-confirmation",
                "closure_forecast_reacquisition_reason": "Fresh confirmation-side follow-through has re-earned re-entry into stronger confirmation-side reacquisition.",
                "transition_closure_likely_outcome": "confirm-soon",
                "class_reweight_transition_status": "pending-support",
                "class_reweight_transition_reason": "The pending confirmation posture is still the live weaker state before re-entry follow-through holds.",
                "class_transition_resolution_status": "none",
                "class_transition_resolution_reason": "",
            }
            for target in resolution_targets
        ]
        return {
            "primary_target_closure_forecast_reset_refresh_recovery_score": 0.33,
            "primary_target_closure_forecast_reset_refresh_recovery_status": "reentering-confirmation",
            "primary_target_closure_forecast_reset_reentry_status": "reentered-confirmation",
            "primary_target_closure_forecast_reset_reentry_reason": "Fresh confirmation-side follow-through has re-earned re-entry into stronger confirmation-side reacquisition.",
            "closure_forecast_reset_refresh_recovery_summary": "Fresh confirmation-side support is strong enough that RepoC may re-enter confirmation-side reacquisition soon (0.33).",
            "closure_forecast_reset_reentry_summary": "Fresh confirmation-side follow-through has re-earned re-entry into stronger confirmation-side reacquisition.",
            "closure_forecast_reset_refresh_window_runs": 4,
            "recovering_from_confirmation_reset_hotspots": [],
            "recovering_from_clearance_reset_hotspots": [],
        }

    monkeypatch.setattr(
        "src.operator_control_center._apply_reacquisition_reset_refresh_recovery_and_reentry",
        _phase47_seed,
    )
    monkeypatch.setattr(
        "src.operator_control_center._target_specific_normalization_noise",
        lambda *_args, **_kwargs: False,
    )

    summary = build_operator_snapshot(report, output_dir=tmp_path)["operator_summary"]

    assert summary["primary_target_closure_forecast_reset_reentry_persistence_status"] == "holding-confirmation-reentry"
    assert summary["primary_target_closure_forecast_reset_reentry_churn_status"] == "none"
    assert summary["primary_target_transition_closure_likely_outcome"] == "confirm-soon"
    assert summary["primary_target_closure_forecast_hysteresis_status"] == "confirmed-confirmation"


def test_operator_snapshot_softens_reset_reentry_when_reentry_starts_churning(
    tmp_path: Path,
    monkeypatch,
):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    monkeypatch.setattr(
        "src.operator_control_center.load_operator_state_history",
        lambda *_args, **_kwargs: [
            {
                "generated_at": "2026-04-06T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-target:RepoC",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_closure_forecast_reweight_direction": "supporting-confirmation",
                    "primary_target_closure_forecast_reweight_score": 0.24,
                    "primary_target_closure_forecast_momentum_status": "reversing",
                    "primary_target_closure_forecast_stability_status": "oscillating",
                    "primary_target_closure_forecast_reacquisition_freshness_status": "mixed-age",
                    "primary_target_closure_forecast_reset_refresh_recovery_status": "reentering-confirmation",
                    "primary_target_closure_forecast_reset_reentry_status": "reentered-confirmation",
                    "primary_target_transition_closure_likely_outcome": "confirm-soon",
                },
                "operator_queue": [],
            },
            {
                "generated_at": "2026-04-05T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-target:RepoC",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_closure_forecast_reweight_direction": "supporting-clearance",
                    "primary_target_closure_forecast_reweight_score": -0.22,
                    "primary_target_closure_forecast_momentum_status": "reversing",
                    "primary_target_closure_forecast_stability_status": "oscillating",
                    "primary_target_closure_forecast_reacquisition_freshness_status": "mixed-age",
                    "primary_target_closure_forecast_reset_refresh_recovery_status": "reentering-clearance",
                    "primary_target_closure_forecast_reset_reentry_status": "reentered-clearance",
                    "primary_target_transition_closure_likely_outcome": "clear-risk",
                },
                "operator_queue": [],
            },
            {
                "generated_at": "2026-04-04T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-target:RepoC",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_closure_forecast_reweight_direction": "supporting-confirmation",
                    "primary_target_closure_forecast_reweight_score": 0.21,
                    "primary_target_closure_forecast_momentum_status": "building",
                    "primary_target_closure_forecast_stability_status": "watch",
                    "primary_target_closure_forecast_reacquisition_freshness_status": "fresh",
                    "primary_target_closure_forecast_reset_refresh_recovery_status": "reentering-confirmation",
                    "primary_target_closure_forecast_reset_reentry_status": "reentered-confirmation",
                    "primary_target_transition_closure_likely_outcome": "confirm-soon",
                },
                "operator_queue": [],
            },
        ],
    )

    def _phase47_seed(
        resolution_targets, _history, *, current_generated_at, confidence_calibration
    ):
        resolution_targets[:] = [
            {
                **target,
                "closure_forecast_reweight_score": 0.28,
                "closure_forecast_reweight_direction": "supporting-confirmation",
                "closure_forecast_momentum_status": "reversing",
                "closure_forecast_stability_status": "oscillating",
                "closure_forecast_reacquisition_freshness_status": "mixed-age",
                "closure_forecast_hysteresis_status": "confirmed-confirmation",
                "closure_forecast_hysteresis_reason": "Fresh confirmation-side follow-through had briefly re-earned re-entry into stronger confirmation-side reacquisition.",
                "closure_forecast_reset_refresh_recovery_score": 0.28,
                "closure_forecast_reset_refresh_recovery_status": "reentering-confirmation",
                "closure_forecast_reset_reentry_status": "reentered-confirmation",
                "closure_forecast_reset_reentry_reason": "Fresh confirmation-side follow-through had briefly re-earned re-entry into stronger confirmation-side reacquisition.",
                "recent_reset_refresh_path": "confirmation-reset -> fresh confirmation -> mixed-age confirmation",
                "closure_forecast_reacquisition_status": "reacquired-confirmation",
                "closure_forecast_reacquisition_reason": "Fresh confirmation-side follow-through had briefly re-earned re-entry into stronger confirmation-side reacquisition.",
                "transition_closure_likely_outcome": "confirm-soon",
                "class_reweight_transition_status": "pending-support",
                "class_reweight_transition_reason": "The pending confirmation posture remains active beneath the briefly restored posture.",
                "class_transition_resolution_status": "none",
                "class_transition_resolution_reason": "",
            }
            for target in resolution_targets
        ]
        return {
            "primary_target_closure_forecast_reset_refresh_recovery_score": 0.28,
            "primary_target_closure_forecast_reset_refresh_recovery_status": "reentering-confirmation",
            "primary_target_closure_forecast_reset_reentry_status": "reentered-confirmation",
            "primary_target_closure_forecast_reset_reentry_reason": "Fresh confirmation-side follow-through had briefly re-earned re-entry into stronger confirmation-side reacquisition.",
            "closure_forecast_reset_refresh_recovery_summary": "Fresh confirmation-side support is strong enough that RepoC may re-enter confirmation-side reacquisition soon (0.28).",
            "closure_forecast_reset_reentry_summary": "Fresh confirmation-side follow-through had briefly re-earned re-entry into stronger confirmation-side reacquisition.",
            "closure_forecast_reset_refresh_window_runs": 4,
            "recovering_from_confirmation_reset_hotspots": [],
            "recovering_from_clearance_reset_hotspots": [],
        }

    monkeypatch.setattr(
        "src.operator_control_center._apply_reacquisition_reset_refresh_recovery_and_reentry",
        _phase47_seed,
    )
    monkeypatch.setattr(
        "src.operator_control_center._target_specific_normalization_noise",
        lambda *_args, **_kwargs: False,
    )

    summary = build_operator_snapshot(report, output_dir=tmp_path)["operator_summary"]

    assert summary["primary_target_closure_forecast_reset_reentry_churn_status"] == "churn"
    assert summary["primary_target_transition_closure_likely_outcome"] == "hold"
    assert summary["primary_target_closure_forecast_hysteresis_status"] == "pending-confirmation"


def test_operator_snapshot_starts_pending_confirmation_rebuild_after_reset_reentry_reset(
    tmp_path: Path,
    monkeypatch,
):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    monkeypatch.setattr(
        "src.operator_control_center.load_operator_state_history",
        lambda *_args, **_kwargs: [
            {
                "generated_at": "2026-04-06T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-target:RepoC",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_closure_forecast_reweight_direction": "supporting-confirmation",
                    "primary_target_closure_forecast_reweight_score": 0.22,
                    "primary_target_closure_forecast_reset_reentry_freshness_status": "fresh",
                    "primary_target_closure_forecast_reset_reentry_reset_status": "confirmation-reset",
                    "primary_target_transition_closure_likely_outcome": "hold",
                },
                "operator_queue": [],
            }
        ],
    )

    def _phase49_seed(
        resolution_targets, _history, *, current_generated_at, confidence_calibration
    ):
        resolution_targets[:] = [
            {
                **target,
                "closure_forecast_reweight_score": 0.34,
                "closure_forecast_reweight_direction": "supporting-confirmation",
                "closure_forecast_momentum_status": "building",
                "closure_forecast_stability_status": "watch",
                "closure_forecast_hysteresis_status": "pending-confirmation",
                "closure_forecast_hysteresis_reason": "Fresh confirmation-side evidence is returning after reset re-entry aged out.",
                "closure_forecast_reset_reentry_freshness_status": "fresh",
                "closure_forecast_reset_reentry_freshness_reason": "Recent reset re-entry evidence is fresh enough to start rebuilding carefully.",
                "closure_forecast_reset_reentry_memory_weight": 0.74,
                "decayed_reset_reentered_confirmation_rate": 0.69,
                "decayed_reset_reentered_clearance_rate": 0.05,
                "recent_reset_reentry_signal_mix": "confirmation-led",
                "closure_forecast_reset_reentry_reset_status": "none",
                "closure_forecast_reset_reentry_reset_reason": "",
                "closure_forecast_reacquisition_status": "none",
                "closure_forecast_reacquisition_reason": "",
                "closure_forecast_reset_reentry_status": "none",
                "closure_forecast_reset_reentry_reason": "",
                "closure_forecast_reset_reentry_age_runs": 0,
                "closure_forecast_reset_reentry_persistence_score": 0.0,
                "closure_forecast_reset_reentry_persistence_status": "none",
                "closure_forecast_reset_reentry_persistence_reason": "",
                "transition_closure_likely_outcome": "hold",
                "class_reweight_transition_status": "pending-support",
                "class_reweight_transition_reason": "The weaker confirmation-side posture is still active while rebuild is being earned.",
                "class_transition_resolution_status": "none",
                "class_transition_resolution_reason": "",
            }
            for target in resolution_targets
        ]
        return {
            "primary_target_closure_forecast_reset_reentry_freshness_status": "fresh",
            "primary_target_closure_forecast_reset_reentry_freshness_reason": "Recent reset re-entry evidence is fresh enough to start rebuilding carefully.",
            "closure_forecast_reset_reentry_freshness_summary": "RepoC still has fresh reset re-entry evidence that is beginning to rebuild after the recent reset.",
            "primary_target_closure_forecast_reset_reentry_reset_status": "none",
            "primary_target_closure_forecast_reset_reentry_reset_reason": "",
            "closure_forecast_reset_reentry_reset_summary": "No new reset is changing the current reset re-entry posture right now.",
            "stale_reset_reentry_hotspots": [],
            "fresh_reset_reentry_signal_hotspots": [],
            "closure_forecast_reset_reentry_decay_window_runs": 4,
        }

    monkeypatch.setattr(
        "src.operator_control_center._apply_reset_reentry_freshness_and_reset",
        _phase49_seed,
    )
    monkeypatch.setattr(
        "src.operator_control_center._target_specific_normalization_noise",
        lambda *_args, **_kwargs: False,
    )

    summary = build_operator_snapshot(report, output_dir=tmp_path)["operator_summary"]

    assert summary["primary_target_closure_forecast_reset_reentry_refresh_recovery_status"] == "rebuilding-confirmation-reentry"
    assert summary["primary_target_closure_forecast_reset_reentry_rebuild_status"] == "pending-confirmation-rebuild"
    assert summary["primary_target_closure_forecast_reset_reentry_status"] == "pending-confirmation-reentry"
    assert summary["primary_target_closure_forecast_reacquisition_status"] == "pending-confirmation-reacquisition"
    assert summary["primary_target_transition_closure_likely_outcome"] == "hold"
    assert summary["primary_target_closure_forecast_hysteresis_status"] == "pending-confirmation"


def test_operator_snapshot_rebuilds_confirmation_reentry_after_fresh_follow_through(
    tmp_path: Path,
    monkeypatch,
):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    monkeypatch.setattr(
        "src.operator_control_center.load_operator_state_history",
        lambda *_args, **_kwargs: [
            {
                "generated_at": "2026-04-06T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-target:RepoC",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_closure_forecast_reweight_direction": "supporting-confirmation",
                    "primary_target_closure_forecast_reweight_score": 0.33,
                    "primary_target_closure_forecast_reset_reentry_freshness_status": "fresh",
                    "primary_target_closure_forecast_reset_reentry_reset_status": "none",
                    "primary_target_transition_closure_likely_outcome": "hold",
                },
                "operator_queue": [],
            },
            {
                "generated_at": "2026-04-05T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-target:RepoC",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_closure_forecast_reweight_direction": "supporting-confirmation",
                    "primary_target_closure_forecast_reweight_score": 0.22,
                    "primary_target_closure_forecast_reset_reentry_freshness_status": "fresh",
                    "primary_target_closure_forecast_reset_reentry_reset_status": "confirmation-reset",
                    "primary_target_transition_closure_likely_outcome": "hold",
                },
                "operator_queue": [],
            },
        ],
    )

    def _phase49_seed(
        resolution_targets, _history, *, current_generated_at, confidence_calibration
    ):
        resolution_targets[:] = [
            {
                **target,
                "closure_forecast_reweight_score": 0.42,
                "closure_forecast_reweight_direction": "supporting-confirmation",
                "closure_forecast_momentum_status": "sustained-confirmation",
                "closure_forecast_stability_status": "stable",
                "closure_forecast_hysteresis_status": "pending-confirmation",
                "closure_forecast_hysteresis_reason": "Fresh confirmation-side support is rebuilding after reset re-entry aged out.",
                "closure_forecast_reset_reentry_freshness_status": "fresh",
                "closure_forecast_reset_reentry_freshness_reason": "Recent reset re-entry evidence is current enough to rebuild safely.",
                "closure_forecast_reset_reentry_memory_weight": 0.79,
                "decayed_reset_reentered_confirmation_rate": 0.74,
                "decayed_reset_reentered_clearance_rate": 0.03,
                "recent_reset_reentry_signal_mix": "confirmation-led",
                "closure_forecast_reset_reentry_reset_status": "none",
                "closure_forecast_reset_reentry_reset_reason": "",
                "closure_forecast_reacquisition_status": "none",
                "closure_forecast_reacquisition_reason": "",
                "closure_forecast_reset_reentry_status": "none",
                "closure_forecast_reset_reentry_reason": "",
                "closure_forecast_reset_reentry_age_runs": 0,
                "closure_forecast_reset_reentry_persistence_score": 0.0,
                "closure_forecast_reset_reentry_persistence_status": "none",
                "closure_forecast_reset_reentry_persistence_reason": "",
                "transition_closure_likely_outcome": "hold",
                "class_reweight_transition_status": "pending-support",
                "class_reweight_transition_reason": "The weaker confirmation-side posture is still active until rebuild is fully re-earned.",
                "class_transition_resolution_status": "none",
                "class_transition_resolution_reason": "",
            }
            for target in resolution_targets
        ]
        return {
            "primary_target_closure_forecast_reset_reentry_freshness_status": "fresh",
            "primary_target_closure_forecast_reset_reentry_freshness_reason": "Recent reset re-entry evidence is current enough to rebuild safely.",
            "closure_forecast_reset_reentry_freshness_summary": "RepoC still has fresh reset re-entry evidence that is current enough to rebuild safely.",
            "primary_target_closure_forecast_reset_reentry_reset_status": "none",
            "primary_target_closure_forecast_reset_reentry_reset_reason": "",
            "closure_forecast_reset_reentry_reset_summary": "No new reset is changing the current reset re-entry posture right now.",
            "stale_reset_reentry_hotspots": [],
            "fresh_reset_reentry_signal_hotspots": [],
            "closure_forecast_reset_reentry_decay_window_runs": 4,
        }

    monkeypatch.setattr(
        "src.operator_control_center._apply_reset_reentry_freshness_and_reset",
        _phase49_seed,
    )
    monkeypatch.setattr(
        "src.operator_control_center._target_specific_normalization_noise",
        lambda *_args, **_kwargs: False,
    )

    summary = build_operator_snapshot(report, output_dir=tmp_path)["operator_summary"]

    assert summary["primary_target_closure_forecast_reset_reentry_refresh_recovery_status"] == "rebuilding-confirmation-reentry"
    assert summary["primary_target_closure_forecast_reset_reentry_rebuild_status"] == "rebuilt-confirmation-reentry"
    assert summary["primary_target_closure_forecast_reset_reentry_status"] == "reentered-confirmation"
    assert summary["primary_target_closure_forecast_reacquisition_status"] == "reacquired-confirmation"
    assert summary["primary_target_transition_closure_likely_outcome"] == "confirm-soon"
    assert summary["primary_target_closure_forecast_hysteresis_status"] == "confirmed-confirmation"


def test_operator_snapshot_rebuilds_clearance_reentry_after_fresh_follow_through(
    tmp_path: Path,
    monkeypatch,
):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    monkeypatch.setattr(
        "src.operator_control_center.load_operator_state_history",
        lambda *_args, **_kwargs: [
            {
                "generated_at": "2026-04-06T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-target:RepoC",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_closure_forecast_reweight_direction": "supporting-clearance",
                    "primary_target_closure_forecast_reweight_score": -0.31,
                    "primary_target_closure_forecast_reset_reentry_freshness_status": "fresh",
                    "primary_target_closure_forecast_reset_reentry_reset_status": "none",
                    "primary_target_transition_closure_likely_outcome": "hold",
                },
                "operator_queue": [],
            },
            {
                "generated_at": "2026-04-05T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-target:RepoC",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_closure_forecast_reweight_direction": "supporting-clearance",
                    "primary_target_closure_forecast_reweight_score": -0.22,
                    "primary_target_closure_forecast_reset_reentry_freshness_status": "fresh",
                    "primary_target_closure_forecast_reset_reentry_reset_status": "clearance-reset",
                    "primary_target_transition_closure_likely_outcome": "hold",
                },
                "operator_queue": [],
            },
        ],
    )

    def _phase49_seed(
        resolution_targets, _history, *, current_generated_at, confidence_calibration
    ):
        resolution_targets[:] = [
            {
                **target,
                "closure_forecast_reweight_score": -0.39,
                "closure_forecast_reweight_direction": "supporting-clearance",
                "closure_forecast_momentum_status": "sustained-clearance",
                "closure_forecast_stability_status": "stable",
                "closure_forecast_hysteresis_status": "pending-clearance",
                "closure_forecast_hysteresis_reason": "Fresh clearance-side pressure is rebuilding after reset re-entry aged out.",
                "closure_forecast_reset_reentry_freshness_status": "fresh",
                "closure_forecast_reset_reentry_freshness_reason": "Recent reset re-entry evidence is current enough to rebuild safely.",
                "closure_forecast_reset_reentry_memory_weight": 0.77,
                "decayed_reset_reentered_confirmation_rate": 0.04,
                "decayed_reset_reentered_clearance_rate": 0.72,
                "recent_reset_reentry_signal_mix": "clearance-led",
                "closure_forecast_reset_reentry_reset_status": "none",
                "closure_forecast_reset_reentry_reset_reason": "",
                "closure_forecast_reacquisition_status": "none",
                "closure_forecast_reacquisition_reason": "",
                "closure_forecast_reset_reentry_status": "none",
                "closure_forecast_reset_reentry_reason": "",
                "closure_forecast_reset_reentry_age_runs": 0,
                "closure_forecast_reset_reentry_persistence_score": 0.0,
                "closure_forecast_reset_reentry_persistence_status": "none",
                "closure_forecast_reset_reentry_persistence_reason": "",
                "transition_closure_likely_outcome": "hold",
                "class_reweight_transition_status": "pending-caution",
                "class_reweight_transition_reason": "The weaker clearance-side posture is still active until rebuild is fully re-earned.",
                "class_transition_resolution_status": "none",
                "class_transition_resolution_reason": "",
            }
            for target in resolution_targets
        ]
        return {
            "primary_target_closure_forecast_reset_reentry_freshness_status": "fresh",
            "primary_target_closure_forecast_reset_reentry_freshness_reason": "Recent reset re-entry evidence is current enough to rebuild safely.",
            "closure_forecast_reset_reentry_freshness_summary": "RepoC still has fresh reset re-entry evidence that is current enough to rebuild safely.",
            "primary_target_closure_forecast_reset_reentry_reset_status": "none",
            "primary_target_closure_forecast_reset_reentry_reset_reason": "",
            "closure_forecast_reset_reentry_reset_summary": "No new reset is changing the current reset re-entry posture right now.",
            "stale_reset_reentry_hotspots": [],
            "fresh_reset_reentry_signal_hotspots": [],
            "closure_forecast_reset_reentry_decay_window_runs": 4,
        }

    monkeypatch.setattr(
        "src.operator_control_center._apply_reset_reentry_freshness_and_reset",
        _phase49_seed,
    )
    monkeypatch.setattr(
        "src.operator_control_center._target_specific_normalization_noise",
        lambda *_args, **_kwargs: False,
    )

    summary = build_operator_snapshot(report, output_dir=tmp_path)["operator_summary"]

    assert summary["primary_target_closure_forecast_reset_reentry_refresh_recovery_status"] == "rebuilding-clearance-reentry"
    assert summary["primary_target_closure_forecast_reset_reentry_rebuild_status"] == "rebuilt-clearance-reentry"
    assert summary["primary_target_closure_forecast_reset_reentry_status"] == "reentered-clearance"
    assert summary["primary_target_closure_forecast_reacquisition_status"] == "reacquired-clearance"
    assert summary["primary_target_transition_closure_likely_outcome"] == "clear-risk"
    assert summary["primary_target_closure_forecast_hysteresis_status"] == "confirmed-clearance"


def test_operator_snapshot_marks_rebuilt_confirmation_as_just_rebuilt(
    tmp_path: Path,
    monkeypatch,
):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )

    monkeypatch.setattr(
        "src.operator_control_center._apply_reset_reentry_refresh_recovery_and_rebuild",
        lambda resolution_targets, _history, **_kwargs: (
            resolution_targets.__setitem__(
                slice(None),
                [
                    {
                        **target,
                        "transition_closure_likely_outcome": "confirm-soon",
                        "closure_forecast_hysteresis_status": "confirmed-confirmation",
                        "closure_forecast_hysteresis_reason": "Fresh confirmation-side follow-through has rebuilt stronger confirmation-side reset re-entry.",
                        "closure_forecast_reset_reentry_freshness_status": "fresh",
                        "closure_forecast_reset_reentry_refresh_recovery_status": "rebuilding-confirmation-reentry",
                        "closure_forecast_reset_reentry_rebuild_status": "rebuilt-confirmation-reentry",
                        "closure_forecast_reset_reentry_rebuild_reason": "Fresh confirmation-side follow-through has rebuilt stronger confirmation-side reset re-entry.",
                        "closure_forecast_reset_reentry_status": "reentered-confirmation",
                        "closure_forecast_reset_reentry_reason": "Fresh confirmation-side follow-through has rebuilt stronger confirmation-side reset re-entry.",
                    }
                    for target in resolution_targets
                ],
            )
            or {
                "primary_target_closure_forecast_reset_reentry_refresh_recovery_score": 0.34,
                "primary_target_closure_forecast_reset_reentry_refresh_recovery_status": "rebuilding-confirmation-reentry",
                "primary_target_closure_forecast_reset_reentry_rebuild_status": "rebuilt-confirmation-reentry",
                "primary_target_closure_forecast_reset_reentry_rebuild_reason": "Fresh confirmation-side follow-through has rebuilt stronger confirmation-side reset re-entry.",
                "closure_forecast_reset_reentry_refresh_recovery_summary": "Fresh confirmation-side evidence is rebuilding strongly for RepoC.",
                "closure_forecast_reset_reentry_rebuild_summary": "RepoC has rebuilt stronger confirmation-side reset re-entry.",
                "closure_forecast_reset_reentry_refresh_window_runs": 4,
                "recovering_from_confirmation_reentry_reset_hotspots": [],
                "recovering_from_clearance_reentry_reset_hotspots": [],
            }
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._closure_forecast_reset_reentry_rebuild_persistence_for_target",
        lambda *_args, **_kwargs: {
            "closure_forecast_reset_reentry_rebuild_age_runs": 1,
            "closure_forecast_reset_reentry_rebuild_persistence_score": 0.29,
            "closure_forecast_reset_reentry_rebuild_persistence_status": "just-rebuilt",
            "closure_forecast_reset_reentry_rebuild_persistence_reason": "Stronger reset re-entry posture has been rebuilt, but it has not yet proved it can hold.",
            "recent_reset_reentry_rebuild_persistence_path": "rebuilt-confirmation-reentry",
        },
    )
    monkeypatch.setattr(
        "src.operator_control_center._closure_forecast_reset_reentry_rebuild_churn_for_target",
        lambda *_args, **_kwargs: {
            "closure_forecast_reset_reentry_rebuild_churn_score": 0.10,
            "closure_forecast_reset_reentry_rebuild_churn_status": "none",
            "closure_forecast_reset_reentry_rebuild_churn_reason": "",
            "recent_reset_reentry_rebuild_churn_path": "rebuilt-confirmation-reentry",
        },
    )

    summary = build_operator_snapshot(report, output_dir=tmp_path)["operator_summary"]

    assert summary["primary_target_closure_forecast_reset_reentry_rebuild_persistence_status"] == "just-rebuilt"
    assert summary["primary_target_closure_forecast_reset_reentry_rebuild_churn_status"] == "none"
    assert summary["primary_target_transition_closure_likely_outcome"] == "confirm-soon"
    assert summary["primary_target_closure_forecast_hysteresis_status"] == "confirmed-confirmation"


def test_operator_snapshot_softens_rebuilt_clearance_when_rebuild_churn_is_high(
    tmp_path: Path,
    monkeypatch,
):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )

    monkeypatch.setattr(
        "src.operator_control_center._apply_reset_reentry_refresh_recovery_and_rebuild",
        lambda resolution_targets, _history, **_kwargs: (
            resolution_targets.__setitem__(
                slice(None),
                [
                    {
                        **target,
                        "transition_closure_likely_outcome": "clear-risk",
                        "closure_forecast_hysteresis_status": "confirmed-clearance",
                        "closure_forecast_hysteresis_reason": "Fresh clearance-side pressure rebuilt stronger caution.",
                        "closure_forecast_reset_reentry_freshness_status": "fresh",
                        "closure_forecast_reset_reentry_refresh_recovery_status": "rebuilding-clearance-reentry",
                        "closure_forecast_reset_reentry_rebuild_status": "rebuilt-clearance-reentry",
                        "closure_forecast_reset_reentry_rebuild_reason": "Fresh clearance-side pressure has rebuilt stronger clearance-side reset re-entry.",
                        "closure_forecast_reset_reentry_status": "reentered-clearance",
                        "closure_forecast_reset_reentry_reason": "Fresh clearance-side pressure has rebuilt stronger clearance-side reset re-entry.",
                    }
                    for target in resolution_targets
                ],
            )
            or {
                "primary_target_closure_forecast_reset_reentry_refresh_recovery_score": -0.35,
                "primary_target_closure_forecast_reset_reentry_refresh_recovery_status": "rebuilding-clearance-reentry",
                "primary_target_closure_forecast_reset_reentry_rebuild_status": "rebuilt-clearance-reentry",
                "primary_target_closure_forecast_reset_reentry_rebuild_reason": "Fresh clearance-side pressure has rebuilt stronger clearance-side reset re-entry.",
                "closure_forecast_reset_reentry_refresh_recovery_summary": "Fresh clearance-side evidence is rebuilding strongly for RepoC.",
                "closure_forecast_reset_reentry_rebuild_summary": "RepoC has rebuilt stronger clearance-side reset re-entry.",
                "closure_forecast_reset_reentry_refresh_window_runs": 4,
                "recovering_from_confirmation_reentry_reset_hotspots": [],
                "recovering_from_clearance_reentry_reset_hotspots": [],
            }
        ),
    )
    monkeypatch.setattr(
        "src.operator_control_center._closure_forecast_reset_reentry_rebuild_persistence_for_target",
        lambda *_args, **_kwargs: {
            "closure_forecast_reset_reentry_rebuild_age_runs": 2,
            "closure_forecast_reset_reentry_rebuild_persistence_score": -0.11,
            "closure_forecast_reset_reentry_rebuild_persistence_status": "reversing",
            "closure_forecast_reset_reentry_rebuild_persistence_reason": "The rebuilt posture is already weakening, so it is being softened again.",
            "recent_reset_reentry_rebuild_persistence_path": "rebuilt-clearance-reentry -> hold",
        },
    )
    monkeypatch.setattr(
        "src.operator_control_center._closure_forecast_reset_reentry_rebuild_churn_for_target",
        lambda *_args, **_kwargs: {
            "closure_forecast_reset_reentry_rebuild_churn_score": 0.52,
            "closure_forecast_reset_reentry_rebuild_churn_status": "churn",
            "closure_forecast_reset_reentry_rebuild_churn_reason": "Rebuilt reset re-entry is flipping enough that restored posture should be softened quickly.",
            "recent_reset_reentry_rebuild_churn_path": "rebuilt-clearance-reentry -> churn",
        },
    )

    summary = build_operator_snapshot(report, output_dir=tmp_path)["operator_summary"]

    assert summary["primary_target_closure_forecast_reset_reentry_rebuild_churn_status"] == "churn"
    assert summary["primary_target_closure_forecast_reset_reentry_rebuild_persistence_status"] == "reversing"
    assert summary["primary_target_transition_closure_likely_outcome"] == "hold"
    assert summary["primary_target_closure_forecast_hysteresis_status"] == "pending-clearance"


def test_rebuild_freshness_softens_mixed_age_sustained_confirmation_rebuild():
    updates = operator_control_center._apply_reset_reentry_rebuild_freshness_reset_control(
        {
            "closure_forecast_reset_reentry_rebuild_churn_status": "none",
        },
        freshness_meta={
            "closure_forecast_reset_reentry_rebuild_freshness_status": "mixed-age",
            "decayed_rebuilt_clearance_reentry_rate": 0.10,
            "has_fresh_aligned_recent_evidence": True,
        },
        transition_history_meta={"recent_pending_status": "none"},
        closure_likely_outcome="confirm-soon",
        closure_hysteresis_status="confirmed-confirmation",
        closure_hysteresis_reason="Fresh confirmation-side follow-through rebuilt stronger posture.",
        transition_status="none",
        transition_reason="",
        resolution_status="none",
        resolution_reason="",
        rebuild_status="rebuilt-confirmation-reentry",
        rebuild_reason="Fresh confirmation-side follow-through rebuilt stronger posture.",
        persistence_age_runs=3,
        persistence_score=0.33,
        persistence_status="sustained-confirmation-rebuild",
        persistence_reason="Confirmation-side rebuild is now holding with enough follow-through to trust the restored forecast more.",
    )

    assert updates["closure_forecast_reset_reentry_rebuild_reset_status"] == "confirmation-softened"
    assert updates["closure_forecast_reset_reentry_rebuild_persistence_status"] == "holding-confirmation-rebuild"
    assert updates["transition_closure_likely_outcome"] == "confirm-soon"


def test_rebuild_freshness_resets_stale_clearance_and_restores_pending_posture():
    updates = operator_control_center._apply_reset_reentry_rebuild_freshness_reset_control(
        {
            "closure_forecast_reset_reentry_rebuild_churn_status": "none",
        },
        freshness_meta={
            "closure_forecast_reset_reentry_rebuild_freshness_status": "stale",
            "decayed_rebuilt_clearance_reentry_rate": 0.22,
            "has_fresh_aligned_recent_evidence": False,
        },
        transition_history_meta={"recent_pending_status": "pending-caution"},
        closure_likely_outcome="expire-risk",
        closure_hysteresis_status="confirmed-clearance",
        closure_hysteresis_reason="Fresh clearance-side pressure rebuilt stronger caution.",
        transition_status="none",
        transition_reason="",
        resolution_status="cleared",
        resolution_reason="Earlier clear was re-enabled after rebuild.",
        rebuild_status="rebuilt-clearance-reentry",
        rebuild_reason="Fresh clearance-side pressure rebuilt stronger caution.",
        persistence_age_runs=3,
        persistence_score=-0.34,
        persistence_status="sustained-clearance-rebuild",
        persistence_reason="Clearance-side rebuild is now holding with enough follow-through to trust the restored caution more.",
    )

    assert updates["closure_forecast_reset_reentry_rebuild_reset_status"] == "clearance-reset"
    assert updates["closure_forecast_reset_reentry_rebuild_status"] == "none"
    assert updates["closure_forecast_reset_reentry_rebuild_persistence_status"] == "none"
    assert updates["transition_closure_likely_outcome"] == "clear-risk"
    assert updates["class_reweight_transition_status"] == "pending-caution"
    assert updates["class_transition_resolution_status"] == "none"
    assert updates["class_reweight_transition_status"] == "pending-caution"


def test_rebuild_refresh_sets_pending_confirmation_reentry_until_fully_reearned():
    updates = operator_control_center._apply_reset_reentry_rebuild_refresh_reentry_control(
        {
            "closure_forecast_reset_reentry_rebuild_freshness_status": "mixed-age",
            "decayed_rebuilt_clearance_reentry_rate": 0.10,
        },
        refresh_meta={
            "closure_forecast_reset_reentry_rebuild_refresh_recovery_status": "recovering-confirmation-rebuild-reset",
            "closure_forecast_reset_reentry_rebuild_reentry_status": "pending-confirmation-rebuild-reentry",
            "closure_forecast_reset_reentry_rebuild_reentry_reason": "Fresh confirmation-side evidence is returning after rebuilt posture was softened or reset, but it has not yet re-earned stronger rebuilt posture.",
            "recent_rebuild_reset_side": "confirmation",
        },
        transition_history_meta={"recent_pending_status": "none"},
        closure_likely_outcome="hold",
        closure_hysteresis_status="pending-confirmation",
        closure_hysteresis_reason="",
        transition_status="none",
        transition_reason="",
        resolution_status="none",
        resolution_reason="",
        rebuild_status="none",
        rebuild_reason="",
        persistence_age_runs=0,
        persistence_score=0.0,
        persistence_status="none",
        persistence_reason="",
    )

    assert updates["closure_forecast_reset_reentry_rebuild_status"] == "pending-confirmation-rebuild"
    assert updates["closure_forecast_reset_reentry_rebuild_persistence_status"] == "none"
    assert updates["transition_closure_likely_outcome"] == "hold"
    assert updates["closure_forecast_hysteresis_status"] == "pending-confirmation"


def test_rebuild_refresh_reenters_clearance_and_restores_earlier_clear_when_fully_earned():
    updates = operator_control_center._apply_reset_reentry_rebuild_refresh_reentry_control(
        {
            "closure_forecast_reset_reentry_rebuild_freshness_status": "fresh",
            "closure_forecast_stability_status": "stable",
            "decayed_rebuilt_clearance_reentry_rate": 0.62,
        },
        refresh_meta={
            "closure_forecast_reset_reentry_rebuild_refresh_recovery_status": "reentering-clearance-rebuild",
            "closure_forecast_reset_reentry_rebuild_reentry_status": "reentered-clearance-rebuild",
            "closure_forecast_reset_reentry_rebuild_reentry_reason": "Fresh clearance-side pressure has re-earned stronger rebuilt clearance posture.",
            "recent_rebuild_reset_side": "clearance",
        },
        transition_history_meta={"recent_pending_status": "pending-caution"},
        closure_likely_outcome="hold",
        closure_hysteresis_status="pending-clearance",
        closure_hysteresis_reason="",
        transition_status="pending-caution",
        transition_reason="Earlier clear was withdrawn when rebuilt posture aged out.",
        resolution_status="none",
        resolution_reason="",
        rebuild_status="pending-clearance-rebuild",
        rebuild_reason="Fresh clearance-side evidence is returning after rebuilt posture was softened or reset, but it has not yet re-earned stronger rebuilt posture.",
        persistence_age_runs=0,
        persistence_score=0.0,
        persistence_status="none",
        persistence_reason="",
    )

    assert updates["closure_forecast_reset_reentry_rebuild_status"] == "rebuilt-clearance-reentry"
    assert updates["transition_closure_likely_outcome"] == "clear-risk"
    assert updates["closure_forecast_hysteresis_status"] == "confirmed-clearance"
    assert updates["class_transition_resolution_status"] == "cleared"


def test_rebuild_reentry_persistence_keeps_confirm_soon_while_holding():
    updates = operator_control_center._apply_reset_reentry_rebuild_reentry_persistence_and_churn_control(
        {
            "closure_forecast_reset_reentry_rebuild_reentry_status": "reentered-confirmation-rebuild",
            "closure_forecast_reset_reentry_rebuild_refresh_recovery_status": "reentering-confirmation-rebuild",
            "closure_forecast_reset_reentry_rebuild_freshness_status": "fresh",
            "class_transition_age_runs": 3,
        },
        persistence_meta={
            "closure_forecast_reset_reentry_rebuild_reentry_persistence_status": "holding-confirmation-rebuild-reentry",
            "closure_forecast_reset_reentry_rebuild_reentry_persistence_reason": "Confirmation-side rebuilt re-entry has stayed aligned long enough to keep the restored forecast in place.",
        },
        churn_meta={
            "closure_forecast_reset_reentry_rebuild_reentry_churn_status": "none",
            "closure_forecast_reset_reentry_rebuild_reentry_churn_reason": "",
        },
        transition_history_meta={"recent_pending_status": "none"},
        closure_likely_outcome="confirm-soon",
        closure_hysteresis_status="confirmed-confirmation",
        closure_hysteresis_reason="Fresh confirmation-side follow-through has re-earned stronger rebuilt posture.",
        transition_status="none",
        transition_reason="",
        resolution_status="none",
        resolution_reason="",
    )

    assert updates["transition_closure_likely_outcome"] == "confirm-soon"
    assert updates["closure_forecast_hysteresis_status"] == "confirmed-confirmation"


def test_rebuild_reentry_churn_softens_clearance_back_toward_hold():
    updates = operator_control_center._apply_reset_reentry_rebuild_reentry_persistence_and_churn_control(
        {
            "closure_forecast_reset_reentry_rebuild_reentry_status": "reentered-clearance-rebuild",
            "closure_forecast_reset_reentry_rebuild_refresh_recovery_status": "reentering-clearance-rebuild",
            "closure_forecast_reset_reentry_rebuild_freshness_status": "fresh",
            "class_transition_age_runs": 4,
        },
        persistence_meta={
            "closure_forecast_reset_reentry_rebuild_reentry_persistence_status": "reversing",
            "closure_forecast_reset_reentry_rebuild_reentry_persistence_reason": "The re-earned rebuilt posture is already weakening, so it is being softened again.",
        },
        churn_meta={
            "closure_forecast_reset_reentry_rebuild_reentry_churn_status": "churn",
            "closure_forecast_reset_reentry_rebuild_reentry_churn_reason": "Rebuilt re-entry is flipping enough that restored posture should be softened quickly.",
        },
        transition_history_meta={"recent_pending_status": "pending-caution"},
        closure_likely_outcome="expire-risk",
        closure_hysteresis_status="confirmed-clearance",
        closure_hysteresis_reason="Fresh clearance-side pressure has re-earned stronger rebuilt caution.",
        transition_status="pending-caution",
        transition_reason="Earlier clear was re-enabled once rebuilt re-entry was re-earned.",
        resolution_status="cleared",
        resolution_reason="Earlier clear was re-enabled after rebuilt re-entry was re-earned.",
    )

    assert updates["transition_closure_likely_outcome"] == "clear-risk"
    assert updates["closure_forecast_hysteresis_status"] == "pending-clearance"
    assert updates["class_transition_resolution_status"] == "none"
    assert updates["class_reweight_transition_status"] == "pending-caution"


def test_rebuild_reentry_refresh_sets_pending_confirmation_restore_until_fully_restored():
    updates = operator_control_center._apply_reset_reentry_rebuild_reentry_refresh_restore_control(
        {
            "closure_forecast_reset_reentry_rebuild_reentry_freshness_status": "mixed-age",
            "decayed_reentered_rebuild_clearance_rate": 0.12,
        },
        refresh_meta={
            "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status": "recovering-confirmation-rebuild-reentry-reset",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_status": "pending-confirmation-rebuild-reentry-restore",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": "Fresh confirmation-side evidence is returning after rebuilt re-entry was softened or reset, but it has not yet restored stronger rebuilt re-entry posture.",
            "recent_rebuild_reentry_reset_side": "confirmation",
        },
        transition_history_meta={"recent_pending_status": "none"},
        closure_likely_outcome="hold",
        closure_hysteresis_status="pending-confirmation",
        closure_hysteresis_reason="",
        transition_status="none",
        transition_reason="",
        resolution_status="none",
        resolution_reason="",
        reentry_status="none",
        reentry_reason="",
        persistence_age_runs=0,
        persistence_score=0.0,
        persistence_status="none",
        persistence_reason="",
    )

    assert updates["closure_forecast_reset_reentry_rebuild_reentry_status"] == "none"
    assert updates["closure_forecast_reset_reentry_rebuild_reentry_persistence_status"] == "none"
    assert updates["transition_closure_likely_outcome"] == "hold"
    assert updates["closure_forecast_hysteresis_status"] == "pending-confirmation"


def test_rebuild_reentry_refresh_restores_clearance_and_earlier_clear_when_fully_earned():
    updates = operator_control_center._apply_reset_reentry_rebuild_reentry_refresh_restore_control(
        {
            "closure_forecast_reset_reentry_rebuild_reentry_freshness_status": "fresh",
            "closure_forecast_stability_status": "stable",
            "decayed_reentered_rebuild_clearance_rate": 0.61,
            "class_transition_age_runs": 4,
        },
        refresh_meta={
            "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status": "restoring-clearance-rebuild-reentry",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_status": "restored-clearance-rebuild-reentry",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": "Fresh clearance-side pressure has restored stronger rebuilt re-entry posture.",
            "recent_rebuild_reentry_reset_side": "clearance",
        },
        transition_history_meta={"recent_pending_status": "pending-caution"},
        closure_likely_outcome="hold",
        closure_hysteresis_status="pending-clearance",
        closure_hysteresis_reason="",
        transition_status="pending-caution",
        transition_reason="Earlier clear was withdrawn when rebuilt re-entry aged out.",
        resolution_status="none",
        resolution_reason="",
        reentry_status="none",
        reentry_reason="",
        persistence_age_runs=0,
        persistence_score=0.0,
        persistence_status="none",
        persistence_reason="",
    )

    assert updates["closure_forecast_reset_reentry_rebuild_reentry_status"] == "reentered-clearance-rebuild"
    assert updates["transition_closure_likely_outcome"] == "clear-risk"
    assert updates["closure_forecast_hysteresis_status"] == "confirmed-clearance"
    assert updates["class_transition_resolution_status"] == "cleared"


def test_rebuild_reentry_restore_persistence_keeps_confirm_soon_while_holding():
    updates = operator_control_center._apply_reset_reentry_rebuild_reentry_restore_persistence_and_churn_control(
        {
            "closure_forecast_reset_reentry_rebuild_reentry_status": "reentered-confirmation-rebuild",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_status": "restored-confirmation-rebuild-reentry",
            "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status": "restoring-confirmation-rebuild-reentry",
            "closure_forecast_reset_reentry_rebuild_reentry_freshness_status": "fresh",
            "class_transition_age_runs": 3,
        },
        persistence_meta={
            "closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_status": "holding-confirmation-rebuild-reentry-restore",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_reason": "Confirmation-side rebuilt re-entry restore has stayed aligned long enough to keep the restored forecast in place.",
        },
        churn_meta={
            "closure_forecast_reset_reentry_rebuild_reentry_restore_churn_status": "none",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_churn_reason": "",
        },
        transition_history_meta={"recent_pending_status": "none"},
        closure_likely_outcome="confirm-soon",
        closure_hysteresis_status="confirmed-confirmation",
        closure_hysteresis_reason="Fresh confirmation-side follow-through has restored stronger rebuilt re-entry posture.",
        transition_status="none",
        transition_reason="",
        resolution_status="none",
        resolution_reason="",
    )

    assert updates["transition_closure_likely_outcome"] == "confirm-soon"
    assert updates["closure_forecast_hysteresis_status"] == "confirmed-confirmation"


def test_rebuild_reentry_restore_churn_softens_clearance_back_toward_hold():
    updates = operator_control_center._apply_reset_reentry_rebuild_reentry_restore_persistence_and_churn_control(
        {
            "closure_forecast_reset_reentry_rebuild_reentry_status": "reentered-clearance-rebuild",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_status": "restored-clearance-rebuild-reentry",
            "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status": "restoring-clearance-rebuild-reentry",
            "closure_forecast_reset_reentry_rebuild_reentry_freshness_status": "fresh",
            "class_transition_age_runs": 4,
        },
        persistence_meta={
            "closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_status": "reversing",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_reason": "The restored rebuilt re-entry posture is already weakening, so it is being softened again.",
        },
        churn_meta={
            "closure_forecast_reset_reentry_rebuild_reentry_restore_churn_status": "churn",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_churn_reason": "Restored rebuilt re-entry is flipping enough that restored posture should be softened quickly.",
        },
        transition_history_meta={"recent_pending_status": "pending-caution"},
        closure_likely_outcome="expire-risk",
        closure_hysteresis_status="confirmed-clearance",
        closure_hysteresis_reason="Fresh clearance-side pressure has restored stronger rebuilt re-entry posture.",
        transition_status="pending-caution",
        transition_reason="Earlier clear was re-enabled once rebuilt re-entry restore was earned.",
        resolution_status="cleared",
        resolution_reason="Earlier clear was re-enabled after rebuilt re-entry restore was earned.",
    )

    assert updates["transition_closure_likely_outcome"] == "clear-risk"
    assert updates["closure_forecast_hysteresis_status"] == "pending-clearance"
    assert updates["closure_forecast_reset_reentry_rebuild_reentry_status"] == "pending-clearance-rebuild-reentry"
    assert updates["class_transition_resolution_status"] == "none"
    assert updates["class_reweight_transition_status"] == "pending-caution"


def test_rebuild_reentry_restore_freshness_mixed_age_softens_confirmation_restore():
    updates = operator_control_center._apply_reset_reentry_rebuild_reentry_restore_freshness_reset_control(
        {
            "closure_forecast_reset_reentry_rebuild_reentry_restore_churn_status": "none",
        },
        freshness_meta={
            "closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_status": "mixed-age",
            "decayed_restored_rebuild_reentry_clearance_rate": 0.20,
            "has_fresh_aligned_recent_evidence": True,
        },
        transition_history_meta={"recent_pending_status": "none"},
        closure_likely_outcome="confirm-soon",
        closure_hysteresis_status="confirmed-confirmation",
        closure_hysteresis_reason="Fresh confirmation-side follow-through restored stronger rebuilt re-entry posture.",
        transition_status="none",
        transition_reason="",
        resolution_status="none",
        resolution_reason="",
        reentry_status="reentered-confirmation-rebuild",
        reentry_reason="Confirmation-side rebuilt re-entry is active.",
        restore_status="restored-confirmation-rebuild-reentry",
        restore_reason="Fresh confirmation-side follow-through has restored stronger rebuilt re-entry posture.",
        persistence_age_runs=3,
        persistence_score=0.66,
        persistence_status="sustained-confirmation-rebuild-reentry-restore",
        persistence_reason="Confirmation-side rebuilt re-entry restore is now holding with enough follow-through to trust the restored forecast more.",
    )

    assert updates["closure_forecast_reset_reentry_rebuild_reentry_restore_reset_status"] == "confirmation-softened"
    assert updates["closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_status"] == "holding-confirmation-rebuild-reentry-restore"
    assert updates["transition_closure_likely_outcome"] == "confirm-soon"


def test_rebuild_reentry_restore_freshness_stale_resets_clearance_restore():
    updates = operator_control_center._apply_reset_reentry_rebuild_reentry_restore_freshness_reset_control(
        {
            "closure_forecast_reset_reentry_rebuild_reentry_restore_churn_status": "none",
        },
        freshness_meta={
            "closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_status": "stale",
            "decayed_restored_rebuild_reentry_clearance_rate": 0.35,
            "has_fresh_aligned_recent_evidence": False,
        },
        transition_history_meta={"recent_pending_status": "pending-caution"},
        closure_likely_outcome="expire-risk",
        closure_hysteresis_status="confirmed-clearance",
        closure_hysteresis_reason="Fresh clearance-side pressure restored stronger rebuilt re-entry posture.",
        transition_status="pending-caution",
        transition_reason="Earlier clear was re-enabled once rebuilt re-entry restore was earned.",
        resolution_status="cleared",
        resolution_reason="Earlier clear was re-enabled after rebuilt re-entry restore was earned.",
        reentry_status="reentered-clearance-rebuild",
        reentry_reason="Clearance-side rebuilt re-entry is active.",
        restore_status="restored-clearance-rebuild-reentry",
        restore_reason="Fresh clearance-side pressure has restored stronger rebuilt re-entry posture.",
        persistence_age_runs=2,
        persistence_score=0.52,
        persistence_status="holding-clearance-rebuild-reentry-restore",
        persistence_reason="Clearance-side rebuilt re-entry restore has stayed aligned long enough to keep the restored forecast in place.",
    )

    assert updates["closure_forecast_reset_reentry_rebuild_reentry_restore_reset_status"] == "clearance-reset"
    assert updates["transition_closure_likely_outcome"] == "clear-risk"
    assert updates["closure_forecast_hysteresis_status"] == "pending-clearance"
    assert updates["closure_forecast_reset_reentry_rebuild_reentry_status"] == "pending-clearance-rebuild-reentry"
    assert updates["closure_forecast_reset_reentry_rebuild_reentry_restore_status"] == "none"
    assert updates["class_transition_resolution_status"] == "none"


def test_rebuild_reentry_restore_refresh_pending_confirmation_rerestore_holds_weaker_posture():
    updates = operator_control_center._apply_reset_reentry_rebuild_reentry_restore_refresh_rerestore_control(
        {
            "closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_status": "mixed-age",
            "decayed_restored_rebuild_reentry_clearance_rate": 0.22,
            "class_transition_age_runs": 1,
        },
        refresh_meta={
            "closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_status": "recovering-confirmation-rebuild-reentry-restore-reset",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": "pending-confirmation-rebuild-reentry-rerestore",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": "Fresh confirmation-side evidence is returning after restored rebuilt re-entry softened or reset, but it has not yet re-restored stronger restored posture.",
            "recent_restore_reset_side": "confirmation",
        },
        transition_history_meta={"recent_pending_status": "none"},
        closure_likely_outcome="hold",
        closure_hysteresis_status="pending-confirmation",
        closure_hysteresis_reason="The confirmation-leaning forecast is visible, but it has not stayed persistent enough to trust fully yet.",
        transition_status="none",
        transition_reason="",
        resolution_status="none",
        resolution_reason="",
        reentry_status="pending-confirmation-rebuild-reentry",
        reentry_reason="Restored confirmation posture has not yet been re-restored.",
        restore_status="none",
        restore_reason="",
        restore_age_runs=0,
        restore_persistence_score=0.0,
        restore_persistence_status="none",
        restore_persistence_reason="",
        restore_churn_score=0.0,
        restore_churn_status="none",
        restore_churn_reason="",
    )

    assert updates["transition_closure_likely_outcome"] == "hold"
    assert updates["closure_forecast_hysteresis_status"] == "pending-confirmation"
    assert updates["closure_forecast_reset_reentry_rebuild_reentry_status"] == "pending-confirmation-rebuild-reentry"
    assert updates["closure_forecast_reset_reentry_rebuild_reentry_restore_status"] == "pending-confirmation-rebuild-reentry-restore"
    assert updates["closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_status"] == "none"


def test_rebuild_reentry_restore_refresh_rerestored_clearance_reenables_clear_posture():
    updates = operator_control_center._apply_reset_reentry_rebuild_reentry_restore_refresh_rerestore_control(
        {
            "closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_status": "fresh",
            "decayed_restored_rebuild_reentry_clearance_rate": 0.63,
            "closure_forecast_stability_status": "stable",
            "class_transition_age_runs": 3,
        },
        refresh_meta={
            "closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_status": "rerestoring-clearance-rebuild-reentry",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": "rerestored-clearance-rebuild-reentry",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": "Fresh clearance-side pressure has re-restored stronger restored rebuilt re-entry posture.",
            "recent_restore_reset_side": "clearance",
        },
        transition_history_meta={"recent_pending_status": "pending-caution"},
        closure_likely_outcome="clear-risk",
        closure_hysteresis_status="pending-clearance",
        closure_hysteresis_reason="Clearance pressure is visible, but it has not stayed persistent enough to trust fully yet.",
        transition_status="pending-caution",
        transition_reason="Earlier clear was withdrawn when restored posture aged out.",
        resolution_status="none",
        resolution_reason="",
        reentry_status="pending-clearance-rebuild-reentry",
        reentry_reason="Restored clearance posture has not yet been re-restored.",
        restore_status="none",
        restore_reason="",
        restore_age_runs=0,
        restore_persistence_score=0.0,
        restore_persistence_status="none",
        restore_persistence_reason="",
        restore_churn_score=0.0,
        restore_churn_status="none",
        restore_churn_reason="",
    )

    assert updates["transition_closure_likely_outcome"] == "expire-risk"
    assert updates["closure_forecast_hysteresis_status"] == "confirmed-clearance"
    assert updates["closure_forecast_reset_reentry_rebuild_reentry_status"] == "reentered-clearance-rebuild"
    assert updates["closure_forecast_reset_reentry_rebuild_reentry_restore_status"] == "restored-clearance-rebuild-reentry"
    assert updates["class_transition_resolution_status"] == "cleared"
    assert updates["closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_status"] == "none"


def test_rererestore_refresh_pending_confirmation_rerererestore_holds_weaker_posture():
    updates = operator_control_center._apply_reset_reentry_rebuild_reentry_restore_rererestore_refresh_rerererestore_control(
        {
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status": "mixed-age",
            "decayed_rererestored_rebuild_reentry_clearance_rate": 0.18,
            "closure_forecast_stability_status": "watch",
            "class_transition_age_runs": 1,
        },
        refresh_meta={
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status": "recovering-confirmation-rebuild-reentry-rererestore-reset",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status": "pending-confirmation-rebuild-reentry-rerererestore",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_reason": "Fresh confirmation-side evidence is returning after stronger re-re-restored posture softened or reset, but it has not yet re-re-re-restored stronger posture.",
            "recent_rererestore_reset_side": "confirmation",
        },
        transition_history_meta={"recent_pending_status": "none"},
        closure_likely_outcome="hold",
        closure_hysteresis_status="pending-confirmation",
        closure_hysteresis_reason="The confirmation-leaning forecast is visible, but it has not stayed persistent enough to trust fully yet.",
        transition_status="none",
        transition_reason="",
        resolution_status="none",
        resolution_reason="",
        reentry_status="pending-confirmation-rebuild-reentry",
        reentry_reason="Re-re-restored confirmation posture has not yet been re-re-re-restored.",
        restore_status="pending-confirmation-rebuild-reentry-restore",
        restore_reason="Restore posture is still weaker while re-re-re-restore is pending.",
        rerestore_status="pending-confirmation-rebuild-reentry-rerestore",
        rerestore_reason="Rerestore posture is still weaker while re-re-re-restore is pending.",
        rererestore_status="pending-confirmation-rebuild-reentry-rererestore",
        rererestore_reason="Fresh confirmation-side evidence is returning after stronger re-re-restored posture softened or reset, but it has not yet re-re-re-restored stronger posture.",
        rererestore_age_runs=2,
        rererestore_persistence_score=0.28,
        rererestore_persistence_status="holding-confirmation-rebuild-reentry-rererestore",
        rererestore_persistence_reason="Confirmation-side re-re-restored posture has stayed aligned long enough to keep the stronger rerestored forecast in place.",
        rererestore_churn_score=0.0,
        rererestore_churn_status="none",
        rererestore_churn_reason="",
    )

    assert updates["transition_closure_likely_outcome"] == "hold"
    assert updates["closure_forecast_hysteresis_status"] == "pending-confirmation"
    assert updates["closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status"] == "pending-confirmation-rebuild-reentry-rererestore"
    assert updates["closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status"] == "none"


def test_rererestore_refresh_rerererestored_clearance_reenables_clear_posture():
    updates = operator_control_center._apply_reset_reentry_rebuild_reentry_restore_rererestore_refresh_rerererestore_control(
        {
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status": "fresh",
            "decayed_rererestored_rebuild_reentry_clearance_rate": 0.61,
            "closure_forecast_stability_status": "stable",
            "class_transition_age_runs": 3,
        },
        refresh_meta={
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status": "rerererestoring-clearance-rebuild-reentry",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status": "rerererestored-clearance-rebuild-reentry",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_reason": "Fresh clearance-side pressure has re-re-re-restored stronger re-re-restored posture.",
            "recent_rererestore_reset_side": "clearance",
        },
        transition_history_meta={"recent_pending_status": "pending-caution"},
        closure_likely_outcome="clear-risk",
        closure_hysteresis_status="pending-clearance",
        closure_hysteresis_reason="Clearance pressure is visible, but it has not stayed persistent enough to trust fully yet.",
        transition_status="pending-caution",
        transition_reason="Earlier clear was withdrawn when re-re-restored posture aged out.",
        resolution_status="none",
        resolution_reason="",
        reentry_status="pending-clearance-rebuild-reentry",
        reentry_reason="Re-re-restored clearance posture has not yet been re-re-re-restored.",
        restore_status="pending-clearance-rebuild-reentry-restore",
        restore_reason="Restore posture is still weaker while re-re-re-restore is pending.",
        rerestore_status="pending-clearance-rebuild-reentry-rerestore",
        rerestore_reason="Rerestore posture is still weaker while re-re-re-restore is pending.",
        rererestore_status="pending-clearance-rebuild-reentry-rererestore",
        rererestore_reason="Fresh clearance-side evidence is returning after stronger re-re-restored posture softened or reset, but it has not yet re-re-re-restored stronger posture.",
        rererestore_age_runs=2,
        rererestore_persistence_score=0.31,
        rererestore_persistence_status="holding-clearance-rebuild-reentry-rererestore",
        rererestore_persistence_reason="Clearance-side re-re-restored posture has stayed aligned long enough to keep the stronger rerestored caution in place.",
        rererestore_churn_score=0.0,
        rererestore_churn_status="none",
        rererestore_churn_reason="",
    )

    assert updates["transition_closure_likely_outcome"] == "expire-risk"
    assert updates["closure_forecast_hysteresis_status"] == "confirmed-clearance"
    assert updates["closure_forecast_reset_reentry_rebuild_reentry_status"] == "reentered-clearance-rebuild"
    assert updates["closure_forecast_reset_reentry_rebuild_reentry_restore_status"] == "restored-clearance-rebuild-reentry"
    assert updates["closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status"] == "rerestored-clearance-rebuild-reentry"
    assert updates["closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status"] == "rererestored-clearance-rebuild-reentry"
    assert updates["class_transition_resolution_status"] == "cleared"


def test_rerererestore_persistence_holding_confirmation_keeps_stronger_posture():
    updates = operator_control_center._apply_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_and_churn_control(
        {
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status": "fresh",
        },
        persistence_meta={
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status": "holding-confirmation-rebuild-reentry-rerererestore",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_reason": "Confirmation-side re-re-re-restored posture has stayed aligned long enough to keep the stronger re-re-restored forecast in place.",
        },
        churn_meta={
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status": "none",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason": "",
        },
        transition_history_meta={"recent_pending_status": "none"},
        closure_likely_outcome="confirm-soon",
        closure_hysteresis_status="confirmed-confirmation",
        closure_hysteresis_reason="Fresh confirmation posture is holding.",
        transition_status="none",
        transition_reason="",
        resolution_status="none",
        resolution_reason="",
        reentry_status="reentered-confirmation-rebuild",
        reentry_reason="Fresh confirmation posture is active.",
        restore_status="restored-confirmation-rebuild-reentry",
        restore_reason="Fresh confirmation posture is active.",
        rerestore_status="rerestored-confirmation-rebuild-reentry",
        rerestore_reason="Fresh confirmation posture is active.",
        rererestore_status="rererestored-confirmation-rebuild-reentry",
        rererestore_reason="Fresh confirmation-side follow-through has re-re-re-restored stronger re-re-restored posture.",
    )

    assert updates["transition_closure_likely_outcome"] == "confirm-soon"
    assert updates["closure_forecast_hysteresis_status"] == "confirmed-confirmation"
    assert updates["closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status"] == "rererestored-confirmation-rebuild-reentry"


def test_rerererestore_churn_softens_clearance_posture():
    updates = operator_control_center._apply_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_and_churn_control(
        {
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status": "mixed-age",
        },
        persistence_meta={
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status": "reversing",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_reason": "The re-re-re-restored rebuilt re-entry posture is already weakening, so it is being softened again.",
        },
        churn_meta={
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status": "churn",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason": "Re-re-re-restored rebuilt re-entry is flipping enough that stronger re-re-restored posture should be softened quickly.",
        },
        transition_history_meta={"recent_pending_status": "pending-caution"},
        closure_likely_outcome="expire-risk",
        closure_hysteresis_status="confirmed-clearance",
        closure_hysteresis_reason="Fresh clearance posture is holding.",
        transition_status="pending-caution",
        transition_reason="Earlier clear remains tentative.",
        resolution_status="cleared",
        resolution_reason="Earlier clear is active.",
        reentry_status="reentered-clearance-rebuild",
        reentry_reason="Fresh clearance posture is active.",
        restore_status="restored-clearance-rebuild-reentry",
        restore_reason="Fresh clearance posture is active.",
        rerestore_status="rerestored-clearance-rebuild-reentry",
        rerestore_reason="Fresh clearance posture is active.",
        rererestore_status="rererestored-clearance-rebuild-reentry",
        rererestore_reason="Fresh clearance-side pressure has re-re-re-restored stronger re-re-restored posture.",
    )

    assert updates["transition_closure_likely_outcome"] == "clear-risk"
    assert updates["closure_forecast_hysteresis_status"] == "pending-clearance"
    assert updates["closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status"] == "pending-clearance-rebuild-reentry-rererestore"


def test_operator_snapshot_learns_when_soft_exception_was_overcautious(tmp_path: Path, monkeypatch):
    report = _make_report(
        preflight_summary={"status": "ok", "blocking_errors": 0, "warnings": 0, "checks": []},
        review_targets=[],
        managed_state_drift=[],
        governance_drift=[],
        governance_preview={},
        rollback_preview={},
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
    )
    monkeypatch.setattr(
        "src.operator_control_center.load_operator_state_history",
        lambda *_args, **_kwargs: [
            {
                "generated_at": "2026-04-06T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "other-target",
                        "repo": "RepoOther",
                        "title": "Another target",
                        "lane": "ready",
                        "kind": "review",
                    },
                    "primary_target_trust_policy": "monitor",
                    "primary_target_exception_status": "none",
                    "decision_memory_status": "new",
                    "primary_target_last_outcome": "no-change",
                },
                "operator_queue": [],
            },
            {
                "generated_at": "2026-04-05T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "other-target-2",
                        "repo": "RepoOther",
                        "title": "Another target 2",
                        "lane": "ready",
                        "kind": "review",
                    },
                    "primary_target_trust_policy": "monitor",
                    "primary_target_exception_status": "none",
                    "decision_memory_status": "new",
                    "primary_target_last_outcome": "no-change",
                },
                "operator_queue": [],
            },
            {
                "generated_at": "2026-04-04T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "other-target-3",
                        "repo": "RepoOther",
                        "title": "Another target 3",
                        "lane": "ready",
                        "kind": "review",
                    },
                    "primary_target_trust_policy": "monitor",
                    "primary_target_exception_status": "none",
                    "decision_memory_status": "new",
                    "primary_target_last_outcome": "no-change",
                },
                "operator_queue": [],
            },
            {
                "generated_at": "2026-04-03T12:00:00+00:00",
                "operator_summary": {
                    "primary_target": {
                        "item_id": "review-change:high-1",
                        "repo": "RepoC",
                        "title": "RepoC security posture changed",
                        "lane": "urgent",
                        "kind": "review",
                    },
                    "primary_target_trust_policy": "verify-first",
                    "primary_target_exception_status": "softened-for-noise",
                    "decision_memory_status": "attempted",
                    "primary_target_last_outcome": "improved",
                },
                "operator_queue": [],
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

    assert summary["primary_target_exception_pattern_status"] == "overcautious"
    assert summary["false_positive_exception_hotspots"][0]["label"] == "RepoC: RepoC security posture changed"


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
