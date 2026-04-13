from __future__ import annotations

from src.operator_effectiveness import build_operator_effectiveness_bundle


def _state(run_id: str, generated_at: str, blocked: int, urgent: int, *, reopened: int = 0, resolved: int = 0) -> dict:
    return {
        "run_id": run_id,
        "generated_at": generated_at,
        "operator_summary": {
            "blocked_count": blocked,
            "urgent_count": urgent,
            "reopened_attention_count": reopened,
            "resolved_attention_count": resolved,
        },
        "operator_queue": [],
    }


def test_build_operator_effectiveness_bundle_computes_phase_84_metrics():
    bundle = build_operator_effectiveness_bundle(
        state_history=[
            _state("run-1", "2026-04-01T00:00:00+00:00", 0, 0, resolved=1),
            _state("run-2", "2026-04-02T00:00:00+00:00", 1, 1, reopened=1, resolved=1),
            _state("run-3", "2026-04-03T00:00:00+00:00", 1, 0, reopened=1, resolved=0),
            _state("run-4", "2026-04-04T00:00:00+00:00", 0, 0, reopened=0, resolved=1),
            _state("run-5", "2026-04-05T00:00:00+00:00", 0, 0, reopened=0, resolved=1),
        ],
        calibration_history=[
            {
                "run_id": "run-5",
                "generated_at": "2026-04-05T00:00:00+00:00",
                "operator_summary": {
                    "validated_recommendation_count": 2,
                    "partially_validated_recommendation_count": 1,
                    "unresolved_recommendation_count": 1,
                    "reopened_recommendation_count": 1,
                    "recent_validation_outcomes": [
                        {
                            "repo": "RepoA",
                            "target_label": "RepoA blocker",
                            "confidence_label": "high",
                            "outcome": "reopened",
                            "summary": "RepoA reopened after an earlier positive read.",
                        }
                    ],
                },
                "operator_queue": [],
            }
        ],
        campaign_history=[
            {
                "generated_at": "2026-04-02T00:00:00+00:00",
                "action_id": "action-1",
                "repo": "RepoA",
                "lifecycle_state": "resolved",
                "reconciliation_outcome": "closed",
                "closed_reason": "Completed",
                "title": "Close RepoA follow-up",
                "summary": "RepoA follow-up closed cleanly.",
            },
            {
                "generated_at": "2026-04-03T00:00:00+00:00",
                "action_id": "action-2",
                "repo": "RepoB",
                "lifecycle_state": "open",
                "reconciliation_outcome": "reopened",
                "reopened_at": "2026-04-03T00:00:00+00:00",
                "title": "RepoB reopened",
                "summary": "RepoB reopened.",
            },
        ],
        review_history=[{"repo": "RepoC", "title": "RepoC", "summary": "RepoC reopened after review."}],
        evidence_events=[
            {
                "repo": "RepoB",
                "action_id": "action-2",
                "outcome": "reopened",
                "event_type": "open",
                "summary": "RepoB reopened.",
            }
        ],
    )

    outcomes = bundle["portfolio_outcomes_summary"]
    effectiveness = bundle["operator_effectiveness_summary"]
    assert outcomes["review_to_action_closure_rate"]["status"] == "measured"
    assert outcomes["review_to_action_closure_rate"]["value"] == 0.5
    assert outcomes["median_runs_to_quiet_after_escalation"]["value"] == 2.0
    assert outcomes["repeated_regression_rate"]["value"] == 0.5
    assert effectiveness["recommendation_validation_rate"]["value"] == 0.6
    assert effectiveness["noisy_guidance_rate"]["value"] == 0.2
    assert bundle["high_pressure_queue_trend_status"] in {"quiet", "improving", "stable"}
    assert len(bundle["high_pressure_queue_history"]) <= 10
    assert bundle["recent_reopened_recommendations"][0]["repo"] == "RepoA"
    assert bundle["recent_closed_actions"][0]["repo"] == "RepoA"
    assert bundle["recent_regression_examples"][0]["repo"] == "RepoB"


def test_build_operator_effectiveness_bundle_handles_insufficient_evidence():
    bundle = build_operator_effectiveness_bundle(
        state_history=[_state("run-1", "2026-04-01T00:00:00+00:00", 0, 0)],
        calibration_history=[],
        campaign_history=[],
        review_history=[],
        evidence_events=[],
    )

    assert bundle["portfolio_outcomes_summary"]["review_to_action_closure_rate"]["status"] == "insufficient-evidence"
    assert bundle["portfolio_outcomes_summary"]["median_runs_to_quiet_after_escalation"]["status"] == "insufficient-evidence"
    assert bundle["operator_effectiveness_summary"]["recommendation_validation_rate"]["status"] == "insufficient-evidence"
    assert bundle["high_pressure_queue_trend_status"] == "insufficient-evidence"
