from __future__ import annotations

from src.review_pack import export_review_pack


def _make_report() -> dict:
    return {
        "username": "testuser",
        "generated_at": "2026-04-12T10:00:00+00:00",
        "repos_audited": 1,
        "average_score": 0.62,
        "portfolio_grade": "C",
        "tier_distribution": {"functional": 1},
        "collections": {"showcase": {"description": "Best examples", "repos": [{"name": "RepoC", "reason": "Operator focus"}]}},
        "profiles": {
            "default": {
                "description": "Balanced",
                "lens_weights": {
                    "ship_readiness": 0.4,
                    "showcase_value": 0.3,
                    "security_posture": 0.3,
                },
            }
        },
        "scenario_summary": {"top_levers": [], "portfolio_projection": {}},
        "audits": [
            {
                "metadata": {
                    "name": "RepoC",
                    "full_name": "user/RepoC",
                    "description": "Phase 78 test repo",
                    "language": "Python",
                    "html_url": "https://github.com/user/RepoC",
                },
                "overall_score": 0.62,
                "interest_score": 0.3,
                "grade": "C",
                "completeness_tier": "functional",
                "badges": [],
                "flags": [],
                "lenses": {
                    "ship_readiness": {"score": 0.62, "orientation": "higher-is-better", "summary": "Ready enough", "drivers": []},
                    "showcase_value": {"score": 0.58, "orientation": "higher-is-better", "summary": "Good story", "drivers": []},
                    "security_posture": {"score": 0.55, "orientation": "higher-is-better", "summary": "Watch", "drivers": []},
                    "momentum": {"score": 0.52, "orientation": "higher-is-better", "summary": "Holding", "drivers": []},
                    "portfolio_fit": {"score": 0.64, "orientation": "higher-is-better", "summary": "Fits", "drivers": []},
                },
                "security_posture": {"label": "watch", "score": 0.55},
                "action_candidates": [{"title": "Recheck restored evidence"}],
                "hotspots": [{"title": "Restored confidence still needs confirmation"}],
                "analyzer_results": [],
            }
        ],
        "operator_summary": {
            "headline": "Restored confidence is coming back after revalidation.",
            "counts": {"blocked": 0, "urgent": 1, "ready": 0, "deferred": 0},
            "follow_through_reacquisition_revalidation_recovery_summary": "1 restored-confidence path has only just been re-earned and still needs another confirming run.",
            "top_just_reearned_confidence_items": [
                {"repo": "RepoC", "title": "RepoC drift needs review"}
            ],
        },
        "operator_queue": [
            {
                "repo": "RepoC",
                "title": "RepoC drift needs review",
                "lane": "urgent",
                "lane_label": "Urgent",
                "lane_reason": "Restored confidence is back, but still fragile after revalidation.",
                "recommended_action": "Wait for one more confirming run before retiring caution.",
                "follow_through_status": "waiting-on-evidence",
                "follow_through_summary": "RepoC has recent follow-up recorded and is now waiting for confirming evidence.",
                "follow_through_checkpoint": "Use the next run to confirm the rebuilt posture is still holding.",
                "follow_through_checkpoint_status": "due-soon",
                "follow_through_escalation_status": "none",
                "follow_through_escalation_summary": "No stronger follow-through escalation is currently surfaced.",
                "follow_through_recovery_status": "recovering",
                "follow_through_recovery_summary": "RepoC is recovering from recent escalation, but it still needs another calmer run before the stronger resurfacing retires.",
                "follow_through_recovery_reacquisition_status": "reacquired",
                "follow_through_recovery_reacquisition_summary": "RepoC has rebuilt the calmer posture after reset.",
                "follow_through_recovery_reacquisition_durability_status": "durable-reacquired",
                "follow_through_recovery_reacquisition_durability_summary": "RepoC has held the restored posture long enough to treat it as durable again.",
                "follow_through_recovery_reacquisition_consolidation_status": "holding-confidence",
                "follow_through_recovery_reacquisition_consolidation_summary": "RepoC has started holding restored confidence again.",
                "follow_through_reacquisition_softening_decay_status": "none",
                "follow_through_reacquisition_softening_decay_summary": "No reacquisition softening-decay signal is currently surfaced.",
                "follow_through_reacquisition_confidence_retirement_status": "none",
                "follow_through_reacquisition_confidence_retirement_summary": "No reacquisition confidence-retirement signal is currently surfaced.",
                "follow_through_reacquisition_revalidation_recovery_status": "just-reearned-confidence",
                "follow_through_reacquisition_revalidation_recovery_summary": "RepoC has only just re-earned restored confidence after revalidation.",
            }
        ],
    }


def test_review_pack_includes_revalidation_recovery_section(tmp_path):
    path = export_review_pack(_make_report(), tmp_path)["review_pack_path"]
    content = path.read_text()

    assert "### Operator Focus" in content
    assert "Operator Focus:" in content
    assert "Act Now" in content
    assert "Follow-Through Revalidation Recovery and Confidence Re-Earning" not in content
