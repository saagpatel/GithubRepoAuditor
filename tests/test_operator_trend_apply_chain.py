from __future__ import annotations

from src.operator_trend_apply_chain import run_resolution_trend_apply_chain


def test_run_resolution_trend_apply_chain_returns_named_results() -> None:
    calls: list[str] = []

    def _make(name: str, payload=None):
        def _fn(resolution_targets, history, **kwargs):
            calls.append(name)
            return payload if payload is not None else {name: True}

        return _fn

    result = run_resolution_trend_apply_chain(
        resolution_targets=[{"id": "a"}],
        history=[{"id": "h"}],
        current_generated_at="2026-04-17T12:00:00Z",
        confidence_calibration={"score": 1.0},
        apply_trust_policy_exceptions=_make("recommendation_drift", {"status": "ok"}),
        apply_exception_pattern_learning=_make("exception_learning"),
        apply_exception_retirement=_make("exception_retirement"),
        apply_class_trust_normalization=_make("class_normalization"),
        apply_class_memory_decay=_make("class_memory_decay"),
        apply_class_trust_reweighting=_make("class_trust_reweighting"),
        apply_class_trust_momentum=_make("class_trust_momentum"),
        apply_class_transition_resolution=_make("class_transition_resolution"),
        apply_transition_closure_confidence=_make("transition_closure_confidence", None),
        apply_pending_debt_freshness_and_closure_forecast_reweighting=_make("pending_debt_freshness"),
        apply_closure_forecast_momentum_and_hysteresis=_make("closure_forecast_momentum"),
        apply_closure_forecast_freshness_and_decay=_make("closure_forecast_decay"),
        apply_closure_forecast_refresh_recovery_and_reacquisition=_make("closure_forecast_recovery"),
        apply_reacquisition_persistence_and_recovery_churn=_make("reacquisition_persistence"),
        apply_reacquisition_freshness_and_persistence_reset=_make("reacquisition_freshness_decay"),
        apply_reacquisition_reset_refresh_recovery_and_reentry=_make("reset_reentry_recovery"),
        apply_reset_reentry_persistence_and_churn=_make("reset_reentry_persistence"),
        apply_reset_reentry_freshness_and_reset=_make("reset_reentry_freshness_decay"),
        apply_reset_reentry_refresh_recovery_and_rebuild=_make("reset_reentry_rebuild"),
        apply_reset_reentry_rebuild_persistence_and_churn=_make("reset_reentry_rebuild_persistence"),
        apply_reset_reentry_rebuild_freshness_and_reset=_make("reset_reentry_rebuild_freshness_decay"),
        apply_reset_reentry_rebuild_refresh_recovery_and_reentry=_make("reset_reentry_rebuild_recovery"),
        apply_reset_reentry_rebuild_reentry_persistence_and_churn=_make("reset_reentry_rebuild_reentry_persistence"),
        apply_reset_reentry_rebuild_reentry_freshness_and_reset=_make("reset_reentry_rebuild_reentry_freshness_decay"),
        apply_reset_reentry_rebuild_reentry_refresh_recovery_and_restore=_make("reset_reentry_rebuild_reentry_recovery"),
        apply_reset_reentry_rebuild_reentry_restore_persistence_and_churn=_make("reset_reentry_rebuild_reentry_restore_persistence"),
        apply_reset_reentry_rebuild_reentry_restore_freshness_and_reset=_make("reset_reentry_rebuild_reentry_restore_freshness_decay"),
        apply_reset_reentry_rebuild_reentry_restore_refresh_recovery_and_rerestore=_make("reset_reentry_rebuild_reentry_restore_recovery"),
        apply_reset_reentry_rebuild_reentry_restore_rerestore_persistence_and_churn=_make("reset_reentry_rebuild_reentry_restore_rerestore_persistence"),
        apply_reset_reentry_rebuild_reentry_restore_rerestore_freshness_and_reset=_make("reset_reentry_rebuild_reentry_restore_rerestore_freshness_decay"),
        apply_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_and_rererestore=_make("reset_reentry_rebuild_reentry_restore_rerestore_recovery"),
        apply_reset_reentry_rebuild_reentry_restore_rererestore_persistence_and_churn=_make("reset_reentry_rebuild_reentry_restore_rererestore_persistence"),
        apply_reset_reentry_rebuild_reentry_restore_rererestore_freshness_and_reset=_make("reset_reentry_rebuild_reentry_restore_rererestore_freshness_decay"),
        apply_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_and_rerererestore=_make("reset_reentry_rebuild_reentry_restore_rererestore_recovery"),
        apply_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_and_churn=_make("reset_reentry_rebuild_reentry_restore_rerererestore_persistence"),
    )

    assert calls[0] == "recommendation_drift"
    assert result["recommendation_drift"] == {"status": "ok"}
    assert "reset_reentry_rebuild_reentry_restore_rerererestore_persistence" in result
