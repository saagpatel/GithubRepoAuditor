from __future__ import annotations

from src.operator_trend_closure_forecast_freshness import closure_forecast_freshness_status
from src.operator_trend_closure_forecast_reacquisition import (
    closure_forecast_reacquisition_side_from_event,
    closure_forecast_reacquisition_side_from_status,
)
from src.operator_trend_closure_forecast_reacquisition_freshness import (
    apply_reacquisition_freshness_reset_control,
    closure_forecast_persistence_reset_summary,
    closure_forecast_reacquisition_freshness_for_target,
    closure_forecast_reacquisition_freshness_hotspots,
    closure_forecast_reacquisition_freshness_reason,
    closure_forecast_reacquisition_freshness_summary,
    reacquisition_event_has_evidence,
    reacquisition_event_is_clearance_like,
    reacquisition_event_is_confirmation_like,
    reacquisition_event_signal_label,
    recent_reacquisition_signal_mix,
)


def _target_class_key(item: dict) -> str:
    return f"{item.get('lane', '')}:{item.get('kind', '') or 'unknown'}"


def _target_label(item: dict) -> str:
    return item.get("title", "") or item.get("kind", "") or "target"


def _target_specific_normalization_noise(target: dict, history_meta: dict) -> bool:
    return bool(target.get("local_noise") or history_meta.get("current_transition_reversed"))


def test_closure_forecast_reacquisition_freshness_for_target_reports_fresh_signal() -> None:
    target = {
        "lane": "urgent",
        "kind": "config",
        "closure_forecast_reacquisition_status": "reacquired-confirmation",
        "closure_forecast_reacquisition_persistence_status": "holding-confirmation",
    }
    events = [
        {
            "class_key": "urgent:config",
            "closure_forecast_reacquisition_status": "reacquired-confirmation",
            "closure_forecast_reacquisition_persistence_status": "holding-confirmation",
            "closure_forecast_freshness_status": "fresh",
        },
        {
            "class_key": "urgent:config",
            "closure_forecast_refresh_recovery_status": "recovering-confirmation",
            "transition_closure_likely_outcome": "confirm-soon",
            "closure_forecast_freshness_status": "fresh",
        },
        {
            "class_key": "urgent:config",
            "closure_forecast_recovery_churn_status": "watch",
            "closure_forecast_freshness_status": "mixed-age",
        },
    ]

    freshness_meta = closure_forecast_reacquisition_freshness_for_target(
        target,
        events,
        target_class_key=_target_class_key,
        reacquisition_event_has_evidence=lambda event: reacquisition_event_has_evidence(
            event,
            reacquisition_event_is_confirmation_like=reacquisition_event_is_confirmation_like,
            reacquisition_event_is_clearance_like=reacquisition_event_is_clearance_like,
        ),
        reacquisition_event_signal_label=lambda event: reacquisition_event_signal_label(
            event,
            reacquisition_event_is_confirmation_like=reacquisition_event_is_confirmation_like,
            reacquisition_event_is_clearance_like=reacquisition_event_is_clearance_like,
        ),
        closure_forecast_reacquisition_side_from_status=closure_forecast_reacquisition_side_from_status,
        closure_forecast_reacquisition_side_from_event=closure_forecast_reacquisition_side_from_event,
        class_memory_recency_weights=[1.0, 0.8, 0.6, 0.4],
        history_window_runs=4,
        class_reacquisition_freshness_window_runs=2,
        freshness_status=closure_forecast_freshness_status,
        freshness_reason=lambda *args: closure_forecast_reacquisition_freshness_reason(
            *args,
            class_reacquisition_freshness_window_runs=2,
        ),
        recent_signal_mix=recent_reacquisition_signal_mix,
        reacquisition_event_is_confirmation_like=reacquisition_event_is_confirmation_like,
        reacquisition_event_is_clearance_like=reacquisition_event_is_clearance_like,
    )

    assert freshness_meta["closure_forecast_reacquisition_freshness_status"] == "fresh"
    assert freshness_meta["closure_forecast_reacquisition_memory_weight"] == 0.75
    assert freshness_meta["has_fresh_aligned_recent_evidence"] is True


def test_apply_reacquisition_freshness_reset_control_resets_clearance_when_aged_out() -> None:
    updates = apply_reacquisition_freshness_reset_control(
        {
            "closure_forecast_recovery_churn_status": "churn",
            "closure_forecast_refresh_recovery_status": "recovering-clearance",
        },
        freshness_meta={
            "closure_forecast_reacquisition_freshness_status": "stale",
            "decayed_reacquired_clearance_rate": 0.3,
            "has_fresh_aligned_recent_evidence": False,
        },
        transition_history_meta={"recent_pending_status": "pending-caution"},
        trust_policy="monitor",
        trust_policy_reason="",
        transition_status="none",
        transition_reason="",
        resolution_status="cleared",
        resolution_reason="",
        pending_debt_status="watch",
        pending_debt_reason="",
        policy_debt_status="watch",
        policy_debt_reason="",
        class_normalization_status="candidate",
        class_normalization_reason="",
        closure_likely_outcome="clear-risk",
        closure_hysteresis_status="confirmed-clearance",
        closure_hysteresis_reason="",
        reacquisition_status="reacquired-clearance",
        reacquisition_reason="",
        persistence_age_runs=3,
        persistence_score=-0.4,
        persistence_status="sustained-clearance",
        persistence_reason="",
        closure_forecast_reacquisition_side_from_status=closure_forecast_reacquisition_side_from_status,
        closure_forecast_reacquisition_side_from_event=closure_forecast_reacquisition_side_from_event,
        target_specific_normalization_noise=_target_specific_normalization_noise,
    )

    assert updates["closure_forecast_persistence_reset_status"] == "clearance-reset"
    assert updates["transition_closure_likely_outcome"] == "hold"
    assert updates["closure_forecast_reacquisition_status"] == "none"


def test_closure_forecast_reacquisition_freshness_hotspots_and_summaries_track_dominant_classes() -> None:
    targets = [
        {
            "lane": "urgent",
            "kind": "config",
            "closure_forecast_reacquisition_freshness_status": "fresh",
            "decayed_reacquired_confirmation_rate": 0.8,
            "decayed_reacquired_clearance_rate": 0.1,
            "recent_reacquisition_persistence_path": "holding-confirmation -> holding-confirmation",
        },
        {
            "lane": "blocked",
            "kind": "setup",
            "closure_forecast_reacquisition_freshness_status": "stale",
            "decayed_reacquired_confirmation_rate": 0.1,
            "decayed_reacquired_clearance_rate": 0.7,
            "recent_reacquisition_persistence_path": "holding-clearance -> holding-clearance",
        },
    ]

    stale_hotspots = closure_forecast_reacquisition_freshness_hotspots(
        targets,
        mode="stale",
        target_class_key=_target_class_key,
    )
    fresh_hotspots = closure_forecast_reacquisition_freshness_hotspots(
        targets,
        mode="fresh",
        target_class_key=_target_class_key,
    )
    freshness_summary = closure_forecast_reacquisition_freshness_summary(
        {"title": "RepoC", "closure_forecast_reacquisition_freshness_status": "mixed-age"},
        stale_hotspots,
        fresh_hotspots,
        target_label=_target_label,
    )
    reset_summary = closure_forecast_persistence_reset_summary(
        {
            "title": "RepoC",
            "closure_forecast_persistence_reset_status": "none",
            "closure_forecast_reacquisition_freshness_status": "mixed-age",
            "decayed_reacquired_confirmation_rate": 0.6,
            "decayed_reacquired_clearance_rate": 0.2,
        },
        stale_hotspots,
        fresh_hotspots,
        target_label=_target_label,
    )

    assert stale_hotspots[0]["label"] == "blocked:setup"
    assert fresh_hotspots[0]["label"] == "urgent:config"
    assert "RepoC" in freshness_summary
    assert "RepoC" in reset_summary
