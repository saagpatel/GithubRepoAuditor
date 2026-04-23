from __future__ import annotations

from src.operator_trend_summary_context import build_trend_summary_context


def test_build_trend_summary_context_packages_attention_counts() -> None:
    resolution_targets = [
        {"id": "a", "aging_status": "chronic"},
        {"id": "b", "newly_stale": True},
    ]
    recommendation_drift = {"recommendation_drift_status": "drifting"}

    def _trend_status_fn(**kwargs):
        assert kwargs["current_attention_count"] == 1
        assert kwargs["previous_attention_count"] == 1
        return "watch"

    def _primary_target_fn(targets):
        return {"id": targets[0]["id"], "aging_status": "chronic"}

    def _primary_target_reason_fn(primary_target):
        return f"reason-{primary_target['id']}"

    def _primary_target_done_criteria_fn(primary_target):
        return f"done-{primary_target['id']}"

    def _closure_guidance_fn(primary_target, done_criteria):
        return f"guide-{done_criteria}"

    def _accountability_summary_fn(**kwargs):
        return f"acct-{kwargs['chronic_item_count']}-{kwargs['newly_stale_count']}"

    def _summary_decision_memory_fn(primary_target, recent_runs, queue_identity):
        return {
            "target": primary_target["id"],
            "run_count": len(recent_runs),
            "identity": queue_identity({"id": "x"}),
        }

    def _trend_summary_fn(**kwargs):
        return f"trend-{kwargs['new_attention_count']}-{kwargs['reopened_attention_count']}"

    context = build_trend_summary_context(
        current_attention={"alpha": {"lane": "blocked"}},
        current_attention_keys={"alpha"},
        previous_attention_keys={"beta"},
        earlier_attention_keys={"alpha"},
        previous_snapshot={"items": {"beta": {}}},
        quiet_streak_runs=0,
        resolution_targets=resolution_targets,
        recommendation_drift=recommendation_drift,
        recent_runs=[{"generated_at": "1"}, {"generated_at": "0"}],
        trend_status_fn=_trend_status_fn,
        primary_target_fn=_primary_target_fn,
        primary_target_reason_fn=_primary_target_reason_fn,
        primary_target_done_criteria_fn=_primary_target_done_criteria_fn,
        closure_guidance_fn=_closure_guidance_fn,
        accountability_summary_fn=_accountability_summary_fn,
        summary_decision_memory_fn=_summary_decision_memory_fn,
        trend_summary_fn=_trend_summary_fn,
        queue_identity=lambda item: item["id"],
    )

    assert context["resolved_attention_count"] == 1
    assert context["persisting_attention_count"] == 0
    assert context["reopened_attention_count"] == 1
    assert context["trend_status"] == "watch"
    assert context["primary_target"]["recommendation_drift_status"] == "drifting"
    assert context["accountability_summary"] == "acct-1-1"
    assert context["trend_summary"] == "trend-1-1"
    assert context["decision_memory"]["run_count"] == 2


def test_build_trend_summary_context_handles_missing_primary_target() -> None:
    context = build_trend_summary_context(
        current_attention={},
        current_attention_keys=set(),
        previous_attention_keys=set(),
        earlier_attention_keys=set(),
        previous_snapshot=None,
        quiet_streak_runs=3,
        resolution_targets=[],
        recommendation_drift={"recommendation_drift_status": "steady"},
        recent_runs=[],
        trend_status_fn=lambda **kwargs: "quiet",
        primary_target_fn=lambda targets: None,
        primary_target_reason_fn=lambda primary_target: "",
        primary_target_done_criteria_fn=lambda primary_target: "",
        closure_guidance_fn=lambda primary_target, done_criteria: "",
        accountability_summary_fn=lambda **kwargs: "acct",
        summary_decision_memory_fn=lambda primary_target, recent_runs, queue_identity: {},
        trend_summary_fn=lambda **kwargs: "trend",
        queue_identity=lambda item: item.get("id", ""),
    )

    assert context["trend_status"] == "quiet"
    assert context["primary_target"] is None
    assert context["chronic_item_count"] == 0
    assert context["newly_stale_count"] == 0
