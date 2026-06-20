"""Top-level payload assembly for the operator resolution-trend god-function.

Extracted verbatim from ``operator_resolution_trend._build_resolution_trend``:
the 1,676-line ``payload.update({...})`` that assembles the 320+ per-target,
per-class, and per-recovery-tier keys of the resolution-trend payload from the
apply-chain and summary-context stages. The block is kept byte-identical (proven
by ``tests/test_resolution_trend_golden_contract.py``); only its container moved.

The three class-transition / hysteresis summary renderers it calls are defined in
``operator_resolution_trend`` and injected as callables here, to avoid a circular
import -- the same dependency-injection pattern the sibling extracted stages
(run-context, apply-chain, summary-context, topline-payload) already use.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def build_resolution_trend_payload(
    *,
    apply_chain: dict[str, Any],
    summary_context: dict[str, Any],
    decision_memory_map: dict[str, Any],
    class_transition_health_summary: Callable[..., Any],
    class_transition_resolution_summary: Callable[..., Any],
    closure_forecast_hysteresis_summary: Callable[..., Any],
) -> dict[str, Any]:
    class_transition_resolution = apply_chain['class_transition_resolution']
    class_trust_momentum = apply_chain['class_trust_momentum']
    closure_forecast_decay = apply_chain['closure_forecast_decay']
    closure_forecast_momentum = apply_chain['closure_forecast_momentum']
    closure_forecast_recovery = apply_chain['closure_forecast_recovery']
    decision_memory = summary_context['decision_memory']
    pending_debt_freshness = apply_chain['pending_debt_freshness']
    primary_target = summary_context['primary_target']
    reacquisition_freshness_decay = apply_chain['reacquisition_freshness_decay']
    reacquisition_persistence = apply_chain['reacquisition_persistence']
    reset_reentry_freshness_decay = apply_chain['reset_reentry_freshness_decay']
    reset_reentry_persistence = apply_chain['reset_reentry_persistence']
    reset_reentry_rebuild = apply_chain['reset_reentry_rebuild']
    reset_reentry_rebuild_freshness_decay = apply_chain['reset_reentry_rebuild_freshness_decay']
    reset_reentry_rebuild_persistence = apply_chain['reset_reentry_rebuild_persistence']
    reset_reentry_rebuild_recovery = apply_chain['reset_reentry_rebuild_recovery']
    reset_reentry_rebuild_reentry_freshness_decay = apply_chain['reset_reentry_rebuild_reentry_freshness_decay']
    reset_reentry_rebuild_reentry_persistence = apply_chain['reset_reentry_rebuild_reentry_persistence']
    reset_reentry_rebuild_reentry_recovery = apply_chain['reset_reentry_rebuild_reentry_recovery']
    reset_reentry_rebuild_reentry_restore_freshness_decay = apply_chain['reset_reentry_rebuild_reentry_restore_freshness_decay']
    reset_reentry_rebuild_reentry_restore_persistence = apply_chain['reset_reentry_rebuild_reentry_restore_persistence']
    reset_reentry_rebuild_reentry_restore_recovery = apply_chain['reset_reentry_rebuild_reentry_restore_recovery']
    reset_reentry_rebuild_reentry_restore_rerererestore_persistence = apply_chain['reset_reentry_rebuild_reentry_restore_rerererestore_persistence']
    reset_reentry_rebuild_reentry_restore_rererestore_freshness_decay = apply_chain['reset_reentry_rebuild_reentry_restore_rererestore_freshness_decay']
    reset_reentry_rebuild_reentry_restore_rererestore_persistence = apply_chain['reset_reentry_rebuild_reentry_restore_rererestore_persistence']
    reset_reentry_rebuild_reentry_restore_rererestore_recovery = apply_chain['reset_reentry_rebuild_reentry_restore_rererestore_recovery']
    reset_reentry_rebuild_reentry_restore_rerestore_freshness_decay = apply_chain['reset_reentry_rebuild_reentry_restore_rerestore_freshness_decay']
    reset_reentry_rebuild_reentry_restore_rerestore_persistence = apply_chain['reset_reentry_rebuild_reentry_restore_rerestore_persistence']
    reset_reentry_rebuild_reentry_restore_rerestore_recovery = apply_chain['reset_reentry_rebuild_reentry_restore_rerestore_recovery']
    reset_reentry_recovery = apply_chain['reset_reentry_recovery']
    _class_transition_health_summary = class_transition_health_summary
    _class_transition_resolution_summary = class_transition_resolution_summary
    _closure_forecast_hysteresis_summary = closure_forecast_hysteresis_summary
    payload: dict[str, Any] = {}
    payload.update({
        "primary_target_class_trust_momentum_score": class_trust_momentum[
            "primary_target_class_trust_momentum_score"
        ],
        "primary_target_class_trust_momentum_status": class_trust_momentum[
            "primary_target_class_trust_momentum_status"
        ],
        "primary_target_class_reweight_stability_status": class_trust_momentum[
            "primary_target_class_reweight_stability_status"
        ],
        "primary_target_class_reweight_transition_status": class_trust_momentum[
            "primary_target_class_reweight_transition_status"
        ],
        "primary_target_class_reweight_transition_reason": class_trust_momentum[
            "primary_target_class_reweight_transition_reason"
        ],
        "class_momentum_summary": class_trust_momentum["class_momentum_summary"],
        "class_reweight_stability_summary": class_trust_momentum[
            "class_reweight_stability_summary"
        ],
        "class_transition_window_runs": class_trust_momentum["class_transition_window_runs"],
        "primary_target_class_transition_health_status": primary_target.get(
            "class_transition_health_status",
            class_transition_resolution["primary_target_class_transition_health_status"],
        )
        if primary_target
        else class_transition_resolution["primary_target_class_transition_health_status"],
        "primary_target_class_transition_health_reason": primary_target.get(
            "class_transition_health_reason",
            class_transition_resolution["primary_target_class_transition_health_reason"],
        )
        if primary_target
        else class_transition_resolution["primary_target_class_transition_health_reason"],
        "primary_target_class_transition_resolution_status": primary_target.get(
            "class_transition_resolution_status",
            class_transition_resolution["primary_target_class_transition_resolution_status"],
        )
        if primary_target
        else class_transition_resolution["primary_target_class_transition_resolution_status"],
        "primary_target_class_transition_resolution_reason": primary_target.get(
            "class_transition_resolution_reason",
            class_transition_resolution["primary_target_class_transition_resolution_reason"],
        )
        if primary_target
        else class_transition_resolution["primary_target_class_transition_resolution_reason"],
        "class_transition_health_summary": _class_transition_health_summary(
            primary_target,
            class_transition_resolution["stalled_transition_hotspots"],
        )
        if primary_target
        else class_transition_resolution["class_transition_health_summary"],
        "class_transition_resolution_summary": _class_transition_resolution_summary(
            primary_target,
            class_transition_resolution["resolving_transition_hotspots"],
            class_transition_resolution["stalled_transition_hotspots"],
        )
        if primary_target
        else class_transition_resolution["class_transition_resolution_summary"],
        "class_transition_age_window_runs": class_transition_resolution[
            "class_transition_age_window_runs"
        ],
        "stalled_transition_hotspots": class_transition_resolution["stalled_transition_hotspots"],
        "resolving_transition_hotspots": class_transition_resolution[
            "resolving_transition_hotspots"
        ],
        "primary_target_transition_closure_confidence_score": primary_target.get(
            "transition_closure_confidence_score",
            pending_debt_freshness["primary_target_transition_closure_confidence_score"],
        )
        if primary_target
        else pending_debt_freshness["primary_target_transition_closure_confidence_score"],
        "primary_target_transition_closure_confidence_label": primary_target.get(
            "transition_closure_confidence_label",
            pending_debt_freshness["primary_target_transition_closure_confidence_label"],
        )
        if primary_target
        else pending_debt_freshness["primary_target_transition_closure_confidence_label"],
        "primary_target_transition_closure_likely_outcome": primary_target.get(
            "transition_closure_likely_outcome",
            closure_forecast_momentum["primary_target_transition_closure_likely_outcome"],
        )
        if primary_target
        else closure_forecast_momentum["primary_target_transition_closure_likely_outcome"],
        "primary_target_transition_closure_confidence_reasons": primary_target.get(
            "transition_closure_confidence_reasons",
            pending_debt_freshness["primary_target_transition_closure_confidence_reasons"],
        )
        if primary_target
        else pending_debt_freshness["primary_target_transition_closure_confidence_reasons"],
        "transition_closure_confidence_summary": closure_forecast_momentum[
            "transition_closure_confidence_summary"
        ],
        "transition_closure_window_runs": pending_debt_freshness["transition_closure_window_runs"],
        "primary_target_class_pending_debt_status": primary_target.get(
            "class_pending_debt_status",
            pending_debt_freshness["primary_target_class_pending_debt_status"],
        )
        if primary_target
        else pending_debt_freshness["primary_target_class_pending_debt_status"],
        "primary_target_class_pending_debt_reason": primary_target.get(
            "class_pending_debt_reason",
            pending_debt_freshness["primary_target_class_pending_debt_reason"],
        )
        if primary_target
        else pending_debt_freshness["primary_target_class_pending_debt_reason"],
        "class_pending_debt_summary": closure_forecast_momentum["class_pending_debt_summary"],
        "class_pending_resolution_summary": closure_forecast_momentum[
            "class_pending_resolution_summary"
        ],
        "class_pending_debt_window_runs": pending_debt_freshness["class_pending_debt_window_runs"],
        "pending_debt_hotspots": pending_debt_freshness["pending_debt_hotspots"],
        "healthy_pending_resolution_hotspots": pending_debt_freshness[
            "healthy_pending_resolution_hotspots"
        ],
        "primary_target_pending_debt_freshness_status": primary_target.get(
            "pending_debt_freshness_status",
            pending_debt_freshness["primary_target_pending_debt_freshness_status"],
        )
        if primary_target
        else pending_debt_freshness["primary_target_pending_debt_freshness_status"],
        "primary_target_pending_debt_freshness_reason": primary_target.get(
            "pending_debt_freshness_reason",
            pending_debt_freshness["primary_target_pending_debt_freshness_reason"],
        )
        if primary_target
        else pending_debt_freshness["primary_target_pending_debt_freshness_reason"],
        "pending_debt_freshness_summary": closure_forecast_momentum[
            "pending_debt_freshness_summary"
        ],
        "pending_debt_decay_summary": closure_forecast_momentum["pending_debt_decay_summary"],
        "stale_pending_debt_hotspots": pending_debt_freshness["stale_pending_debt_hotspots"],
        "fresh_pending_resolution_hotspots": pending_debt_freshness[
            "fresh_pending_resolution_hotspots"
        ],
        "pending_debt_decay_window_runs": pending_debt_freshness["pending_debt_decay_window_runs"],
        "primary_target_weighted_pending_resolution_support_score": primary_target.get(
            "weighted_pending_resolution_support_score",
            pending_debt_freshness["primary_target_weighted_pending_resolution_support_score"],
        )
        if primary_target
        else pending_debt_freshness["primary_target_weighted_pending_resolution_support_score"],
        "primary_target_weighted_pending_debt_caution_score": primary_target.get(
            "weighted_pending_debt_caution_score",
            pending_debt_freshness["primary_target_weighted_pending_debt_caution_score"],
        )
        if primary_target
        else pending_debt_freshness["primary_target_weighted_pending_debt_caution_score"],
        "primary_target_closure_forecast_reweight_score": primary_target.get(
            "closure_forecast_reweight_score",
            pending_debt_freshness["primary_target_closure_forecast_reweight_score"],
        )
        if primary_target
        else pending_debt_freshness["primary_target_closure_forecast_reweight_score"],
        "primary_target_closure_forecast_reweight_direction": primary_target.get(
            "closure_forecast_reweight_direction",
            pending_debt_freshness["primary_target_closure_forecast_reweight_direction"],
        )
        if primary_target
        else pending_debt_freshness["primary_target_closure_forecast_reweight_direction"],
        "primary_target_closure_forecast_reweight_reasons": primary_target.get(
            "closure_forecast_reweight_reasons",
            pending_debt_freshness["primary_target_closure_forecast_reweight_reasons"],
        )
        if primary_target
        else pending_debt_freshness["primary_target_closure_forecast_reweight_reasons"],
        "closure_forecast_reweighting_summary": closure_forecast_momentum[
            "closure_forecast_reweighting_summary"
        ],
        "closure_forecast_reweighting_window_runs": pending_debt_freshness[
            "closure_forecast_reweighting_window_runs"
        ],
        "supporting_pending_resolution_hotspots": pending_debt_freshness[
            "supporting_pending_resolution_hotspots"
        ],
        "caution_pending_debt_hotspots": pending_debt_freshness["caution_pending_debt_hotspots"],
        "primary_target_closure_forecast_momentum_score": closure_forecast_momentum[
            "primary_target_closure_forecast_momentum_score"
        ],
        "primary_target_closure_forecast_momentum_status": closure_forecast_momentum[
            "primary_target_closure_forecast_momentum_status"
        ],
        "primary_target_closure_forecast_stability_status": closure_forecast_momentum[
            "primary_target_closure_forecast_stability_status"
        ],
        "primary_target_closure_forecast_hysteresis_status": primary_target.get(
            "closure_forecast_hysteresis_status",
            closure_forecast_momentum["primary_target_closure_forecast_hysteresis_status"],
        )
        if primary_target
        else closure_forecast_momentum["primary_target_closure_forecast_hysteresis_status"],
        "primary_target_closure_forecast_hysteresis_reason": primary_target.get(
            "closure_forecast_hysteresis_reason",
            closure_forecast_momentum["primary_target_closure_forecast_hysteresis_reason"],
        )
        if primary_target
        else closure_forecast_momentum["primary_target_closure_forecast_hysteresis_reason"],
        "closure_forecast_momentum_summary": closure_forecast_momentum[
            "closure_forecast_momentum_summary"
        ],
        "closure_forecast_stability_summary": closure_forecast_momentum[
            "closure_forecast_stability_summary"
        ],
        "closure_forecast_hysteresis_summary": _closure_forecast_hysteresis_summary(
            primary_target,
            closure_forecast_momentum["sustained_confirmation_hotspots"],
            closure_forecast_momentum["sustained_clearance_hotspots"],
        )
        if primary_target
        else closure_forecast_momentum["closure_forecast_hysteresis_summary"],
        "closure_forecast_transition_window_runs": closure_forecast_momentum[
            "closure_forecast_transition_window_runs"
        ],
        "sustained_confirmation_hotspots": closure_forecast_momentum[
            "sustained_confirmation_hotspots"
        ],
        "sustained_clearance_hotspots": closure_forecast_momentum["sustained_clearance_hotspots"],
        "oscillating_closure_forecast_hotspots": closure_forecast_momentum[
            "oscillating_closure_forecast_hotspots"
        ],
        "primary_target_closure_forecast_freshness_status": closure_forecast_decay[
            "primary_target_closure_forecast_freshness_status"
        ],
        "primary_target_closure_forecast_freshness_reason": closure_forecast_decay[
            "primary_target_closure_forecast_freshness_reason"
        ],
        "primary_target_closure_forecast_decay_status": closure_forecast_decay[
            "primary_target_closure_forecast_decay_status"
        ],
        "primary_target_closure_forecast_decay_reason": closure_forecast_decay[
            "primary_target_closure_forecast_decay_reason"
        ],
        "closure_forecast_freshness_summary": closure_forecast_decay[
            "closure_forecast_freshness_summary"
        ],
        "closure_forecast_decay_summary": closure_forecast_decay["closure_forecast_decay_summary"],
        "stale_closure_forecast_hotspots": closure_forecast_decay[
            "stale_closure_forecast_hotspots"
        ],
        "fresh_closure_forecast_signal_hotspots": closure_forecast_decay[
            "fresh_closure_forecast_signal_hotspots"
        ],
        "closure_forecast_decay_window_runs": closure_forecast_decay[
            "closure_forecast_decay_window_runs"
        ],
        "primary_target_closure_forecast_refresh_recovery_score": closure_forecast_recovery[
            "primary_target_closure_forecast_refresh_recovery_score"
        ],
        "primary_target_closure_forecast_refresh_recovery_status": closure_forecast_recovery[
            "primary_target_closure_forecast_refresh_recovery_status"
        ],
        "primary_target_closure_forecast_reacquisition_status": primary_target.get(
            "closure_forecast_reacquisition_status",
            closure_forecast_recovery["primary_target_closure_forecast_reacquisition_status"],
        )
        if primary_target
        else closure_forecast_recovery["primary_target_closure_forecast_reacquisition_status"],
        "primary_target_closure_forecast_reacquisition_reason": primary_target.get(
            "closure_forecast_reacquisition_reason",
            closure_forecast_recovery["primary_target_closure_forecast_reacquisition_reason"],
        )
        if primary_target
        else closure_forecast_recovery["primary_target_closure_forecast_reacquisition_reason"],
        "closure_forecast_refresh_recovery_summary": closure_forecast_recovery[
            "closure_forecast_refresh_recovery_summary"
        ],
        "closure_forecast_reacquisition_summary": closure_forecast_recovery[
            "closure_forecast_reacquisition_summary"
        ],
        "closure_forecast_refresh_window_runs": closure_forecast_recovery[
            "closure_forecast_refresh_window_runs"
        ],
        "recovering_confirmation_hotspots": closure_forecast_recovery[
            "recovering_confirmation_hotspots"
        ],
        "recovering_clearance_hotspots": closure_forecast_recovery["recovering_clearance_hotspots"],
        "primary_target_closure_forecast_reacquisition_age_runs": primary_target.get(
            "closure_forecast_reacquisition_age_runs",
            reacquisition_persistence["primary_target_closure_forecast_reacquisition_age_runs"],
        )
        if primary_target
        else reacquisition_persistence["primary_target_closure_forecast_reacquisition_age_runs"],
        "primary_target_closure_forecast_reacquisition_persistence_score": primary_target.get(
            "closure_forecast_reacquisition_persistence_score",
            reacquisition_persistence[
                "primary_target_closure_forecast_reacquisition_persistence_score"
            ],
        )
        if primary_target
        else reacquisition_persistence[
            "primary_target_closure_forecast_reacquisition_persistence_score"
        ],
        "primary_target_closure_forecast_reacquisition_persistence_status": primary_target.get(
            "closure_forecast_reacquisition_persistence_status",
            reacquisition_persistence[
                "primary_target_closure_forecast_reacquisition_persistence_status"
            ],
        )
        if primary_target
        else reacquisition_persistence[
            "primary_target_closure_forecast_reacquisition_persistence_status"
        ],
        "primary_target_closure_forecast_reacquisition_persistence_reason": primary_target.get(
            "closure_forecast_reacquisition_persistence_reason",
            reacquisition_persistence[
                "primary_target_closure_forecast_reacquisition_persistence_reason"
            ],
        )
        if primary_target
        else reacquisition_persistence[
            "primary_target_closure_forecast_reacquisition_persistence_reason"
        ],
        "closure_forecast_reacquisition_persistence_summary": reacquisition_persistence[
            "closure_forecast_reacquisition_persistence_summary"
        ],
        "closure_forecast_reacquisition_window_runs": reacquisition_persistence[
            "closure_forecast_reacquisition_window_runs"
        ],
        "just_reacquired_hotspots": reacquisition_persistence["just_reacquired_hotspots"],
        "holding_reacquisition_hotspots": reacquisition_persistence[
            "holding_reacquisition_hotspots"
        ],
        "primary_target_closure_forecast_recovery_churn_score": primary_target.get(
            "closure_forecast_recovery_churn_score",
            reacquisition_persistence["primary_target_closure_forecast_recovery_churn_score"],
        )
        if primary_target
        else reacquisition_persistence["primary_target_closure_forecast_recovery_churn_score"],
        "primary_target_closure_forecast_recovery_churn_status": primary_target.get(
            "closure_forecast_recovery_churn_status",
            reacquisition_persistence["primary_target_closure_forecast_recovery_churn_status"],
        )
        if primary_target
        else reacquisition_persistence["primary_target_closure_forecast_recovery_churn_status"],
        "primary_target_closure_forecast_recovery_churn_reason": primary_target.get(
            "closure_forecast_recovery_churn_reason",
            reacquisition_persistence["primary_target_closure_forecast_recovery_churn_reason"],
        )
        if primary_target
        else reacquisition_persistence["primary_target_closure_forecast_recovery_churn_reason"],
        "closure_forecast_recovery_churn_summary": reacquisition_persistence[
            "closure_forecast_recovery_churn_summary"
        ],
        "recovery_churn_hotspots": reacquisition_persistence["recovery_churn_hotspots"],
        "primary_target_closure_forecast_reacquisition_freshness_status": reacquisition_freshness_decay[
            "primary_target_closure_forecast_reacquisition_freshness_status"
        ],
        "primary_target_closure_forecast_reacquisition_freshness_reason": reacquisition_freshness_decay[
            "primary_target_closure_forecast_reacquisition_freshness_reason"
        ],
        "closure_forecast_reacquisition_freshness_summary": reacquisition_freshness_decay[
            "closure_forecast_reacquisition_freshness_summary"
        ],
        "primary_target_closure_forecast_persistence_reset_status": reacquisition_freshness_decay[
            "primary_target_closure_forecast_persistence_reset_status"
        ],
        "primary_target_closure_forecast_persistence_reset_reason": reacquisition_freshness_decay[
            "primary_target_closure_forecast_persistence_reset_reason"
        ],
        "closure_forecast_persistence_reset_summary": reacquisition_freshness_decay[
            "closure_forecast_persistence_reset_summary"
        ],
        "stale_reacquisition_hotspots": reacquisition_freshness_decay[
            "stale_reacquisition_hotspots"
        ],
        "fresh_reacquisition_signal_hotspots": reacquisition_freshness_decay[
            "fresh_reacquisition_signal_hotspots"
        ],
        "closure_forecast_reacquisition_decay_window_runs": reacquisition_freshness_decay[
            "closure_forecast_reacquisition_decay_window_runs"
        ],
        "primary_target_closure_forecast_reset_refresh_recovery_score": primary_target.get(
            "closure_forecast_reset_refresh_recovery_score",
            reset_reentry_recovery["primary_target_closure_forecast_reset_refresh_recovery_score"],
        )
        if primary_target
        else reset_reentry_recovery["primary_target_closure_forecast_reset_refresh_recovery_score"],
        "primary_target_closure_forecast_reset_refresh_recovery_status": primary_target.get(
            "closure_forecast_reset_refresh_recovery_status",
            reset_reentry_recovery["primary_target_closure_forecast_reset_refresh_recovery_status"],
        )
        if primary_target
        else reset_reentry_recovery[
            "primary_target_closure_forecast_reset_refresh_recovery_status"
        ],
        "primary_target_closure_forecast_reset_reentry_status": primary_target.get(
            "closure_forecast_reset_reentry_status",
            reset_reentry_recovery["primary_target_closure_forecast_reset_reentry_status"],
        )
        if primary_target
        else reset_reentry_recovery["primary_target_closure_forecast_reset_reentry_status"],
        "primary_target_closure_forecast_reset_reentry_reason": primary_target.get(
            "closure_forecast_reset_reentry_reason",
            reset_reentry_recovery["primary_target_closure_forecast_reset_reentry_reason"],
        )
        if primary_target
        else reset_reentry_recovery["primary_target_closure_forecast_reset_reentry_reason"],
        "closure_forecast_reset_refresh_recovery_summary": reset_reentry_recovery[
            "closure_forecast_reset_refresh_recovery_summary"
        ],
        "closure_forecast_reset_reentry_summary": reset_reentry_recovery[
            "closure_forecast_reset_reentry_summary"
        ],
        "closure_forecast_reset_refresh_window_runs": reset_reentry_recovery[
            "closure_forecast_reset_refresh_window_runs"
        ],
        "recovering_from_confirmation_reset_hotspots": reset_reentry_recovery[
            "recovering_from_confirmation_reset_hotspots"
        ],
        "recovering_from_clearance_reset_hotspots": reset_reentry_recovery[
            "recovering_from_clearance_reset_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_age_runs": primary_target.get(
            "closure_forecast_reset_reentry_age_runs",
            reset_reentry_persistence["primary_target_closure_forecast_reset_reentry_age_runs"],
        )
        if primary_target
        else reset_reentry_persistence["primary_target_closure_forecast_reset_reentry_age_runs"],
        "primary_target_closure_forecast_reset_reentry_persistence_score": primary_target.get(
            "closure_forecast_reset_reentry_persistence_score",
            reset_reentry_persistence[
                "primary_target_closure_forecast_reset_reentry_persistence_score"
            ],
        )
        if primary_target
        else reset_reentry_persistence[
            "primary_target_closure_forecast_reset_reentry_persistence_score"
        ],
        "primary_target_closure_forecast_reset_reentry_persistence_status": primary_target.get(
            "closure_forecast_reset_reentry_persistence_status",
            reset_reentry_persistence[
                "primary_target_closure_forecast_reset_reentry_persistence_status"
            ],
        )
        if primary_target
        else reset_reentry_persistence[
            "primary_target_closure_forecast_reset_reentry_persistence_status"
        ],
        "primary_target_closure_forecast_reset_reentry_persistence_reason": primary_target.get(
            "closure_forecast_reset_reentry_persistence_reason",
            reset_reentry_persistence[
                "primary_target_closure_forecast_reset_reentry_persistence_reason"
            ],
        )
        if primary_target
        else reset_reentry_persistence[
            "primary_target_closure_forecast_reset_reentry_persistence_reason"
        ],
        "closure_forecast_reset_reentry_persistence_summary": reset_reentry_persistence[
            "closure_forecast_reset_reentry_persistence_summary"
        ],
        "closure_forecast_reset_reentry_window_runs": reset_reentry_persistence[
            "closure_forecast_reset_reentry_window_runs"
        ],
        "just_reentered_hotspots": reset_reentry_persistence["just_reentered_hotspots"],
        "holding_reset_reentry_hotspots": reset_reentry_persistence[
            "holding_reset_reentry_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_churn_score": primary_target.get(
            "closure_forecast_reset_reentry_churn_score",
            reset_reentry_persistence["primary_target_closure_forecast_reset_reentry_churn_score"],
        )
        if primary_target
        else reset_reentry_persistence["primary_target_closure_forecast_reset_reentry_churn_score"],
        "primary_target_closure_forecast_reset_reentry_churn_status": primary_target.get(
            "closure_forecast_reset_reentry_churn_status",
            reset_reentry_persistence["primary_target_closure_forecast_reset_reentry_churn_status"],
        )
        if primary_target
        else reset_reentry_persistence[
            "primary_target_closure_forecast_reset_reentry_churn_status"
        ],
        "primary_target_closure_forecast_reset_reentry_churn_reason": primary_target.get(
            "closure_forecast_reset_reentry_churn_reason",
            reset_reentry_persistence["primary_target_closure_forecast_reset_reentry_churn_reason"],
        )
        if primary_target
        else reset_reentry_persistence[
            "primary_target_closure_forecast_reset_reentry_churn_reason"
        ],
        "closure_forecast_reset_reentry_churn_summary": reset_reentry_persistence[
            "closure_forecast_reset_reentry_churn_summary"
        ],
        "reset_reentry_churn_hotspots": reset_reentry_persistence["reset_reentry_churn_hotspots"],
        "primary_target_closure_forecast_reset_reentry_freshness_status": primary_target.get(
            "closure_forecast_reset_reentry_freshness_status",
            reset_reentry_freshness_decay[
                "primary_target_closure_forecast_reset_reentry_freshness_status"
            ],
        )
        if primary_target
        else reset_reentry_freshness_decay[
            "primary_target_closure_forecast_reset_reentry_freshness_status"
        ],
        "primary_target_closure_forecast_reset_reentry_freshness_reason": primary_target.get(
            "closure_forecast_reset_reentry_freshness_reason",
            reset_reentry_freshness_decay[
                "primary_target_closure_forecast_reset_reentry_freshness_reason"
            ],
        )
        if primary_target
        else reset_reentry_freshness_decay[
            "primary_target_closure_forecast_reset_reentry_freshness_reason"
        ],
        "closure_forecast_reset_reentry_freshness_summary": reset_reentry_freshness_decay[
            "closure_forecast_reset_reentry_freshness_summary"
        ],
        "primary_target_closure_forecast_reset_reentry_reset_status": primary_target.get(
            "closure_forecast_reset_reentry_reset_status",
            reset_reentry_freshness_decay[
                "primary_target_closure_forecast_reset_reentry_reset_status"
            ],
        )
        if primary_target
        else reset_reentry_freshness_decay[
            "primary_target_closure_forecast_reset_reentry_reset_status"
        ],
        "primary_target_closure_forecast_reset_reentry_reset_reason": primary_target.get(
            "closure_forecast_reset_reentry_reset_reason",
            reset_reentry_freshness_decay[
                "primary_target_closure_forecast_reset_reentry_reset_reason"
            ],
        )
        if primary_target
        else reset_reentry_freshness_decay[
            "primary_target_closure_forecast_reset_reentry_reset_reason"
        ],
        "closure_forecast_reset_reentry_reset_summary": reset_reentry_freshness_decay[
            "closure_forecast_reset_reentry_reset_summary"
        ],
        "stale_reset_reentry_hotspots": reset_reentry_freshness_decay[
            "stale_reset_reentry_hotspots"
        ],
        "fresh_reset_reentry_signal_hotspots": reset_reentry_freshness_decay[
            "fresh_reset_reentry_signal_hotspots"
        ],
        "closure_forecast_reset_reentry_decay_window_runs": reset_reentry_freshness_decay[
            "closure_forecast_reset_reentry_decay_window_runs"
        ],
        "primary_target_closure_forecast_reset_reentry_refresh_recovery_score": primary_target.get(
            "closure_forecast_reset_reentry_refresh_recovery_score",
            reset_reentry_rebuild[
                "primary_target_closure_forecast_reset_reentry_refresh_recovery_score"
            ],
        )
        if primary_target
        else reset_reentry_rebuild[
            "primary_target_closure_forecast_reset_reentry_refresh_recovery_score"
        ],
        "primary_target_closure_forecast_reset_reentry_refresh_recovery_status": primary_target.get(
            "closure_forecast_reset_reentry_refresh_recovery_status",
            reset_reentry_rebuild[
                "primary_target_closure_forecast_reset_reentry_refresh_recovery_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild[
            "primary_target_closure_forecast_reset_reentry_refresh_recovery_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_status",
            reset_reentry_rebuild["primary_target_closure_forecast_reset_reentry_rebuild_status"],
        )
        if primary_target
        else reset_reentry_rebuild["primary_target_closure_forecast_reset_reentry_rebuild_status"],
        "primary_target_closure_forecast_reset_reentry_rebuild_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reason",
            reset_reentry_rebuild["primary_target_closure_forecast_reset_reentry_rebuild_reason"],
        )
        if primary_target
        else reset_reentry_rebuild["primary_target_closure_forecast_reset_reentry_rebuild_reason"],
        "closure_forecast_reset_reentry_refresh_recovery_summary": reset_reentry_rebuild[
            "closure_forecast_reset_reentry_refresh_recovery_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_summary": reset_reentry_rebuild[
            "closure_forecast_reset_reentry_rebuild_summary"
        ],
        "closure_forecast_reset_reentry_refresh_window_runs": reset_reentry_rebuild[
            "closure_forecast_reset_reentry_refresh_window_runs"
        ],
        "recovering_from_confirmation_reentry_reset_hotspots": reset_reentry_rebuild[
            "recovering_from_confirmation_reentry_reset_hotspots"
        ],
        "recovering_from_clearance_reentry_reset_hotspots": reset_reentry_rebuild[
            "recovering_from_clearance_reentry_reset_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_age_runs": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_age_runs",
            reset_reentry_rebuild_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_age_runs"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_age_runs"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_persistence_score": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_persistence_score",
            reset_reentry_rebuild_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_persistence_score"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_persistence_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_persistence_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_persistence_status",
            reset_reentry_rebuild_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_persistence_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_persistence_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_persistence_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_persistence_reason",
            reset_reentry_rebuild_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_persistence_reason"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_persistence_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_persistence_summary": reset_reentry_rebuild_persistence[
            "closure_forecast_reset_reentry_rebuild_persistence_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_window_runs": reset_reentry_rebuild_persistence[
            "closure_forecast_reset_reentry_rebuild_window_runs"
        ],
        "just_rebuilt_hotspots": reset_reentry_rebuild_persistence["just_rebuilt_hotspots"],
        "holding_reset_reentry_rebuild_hotspots": reset_reentry_rebuild_persistence[
            "holding_reset_reentry_rebuild_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_churn_score": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_churn_score",
            reset_reentry_rebuild_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_churn_score"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_churn_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_churn_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_churn_status",
            reset_reentry_rebuild_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_churn_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_churn_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_churn_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_churn_reason",
            reset_reentry_rebuild_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_churn_reason"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_churn_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_churn_summary": reset_reentry_rebuild_persistence[
            "closure_forecast_reset_reentry_rebuild_churn_summary"
        ],
        "reset_reentry_rebuild_churn_hotspots": reset_reentry_rebuild_persistence[
            "reset_reentry_rebuild_churn_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_freshness_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_freshness_status",
            reset_reentry_rebuild_freshness_decay[
                "primary_target_closure_forecast_reset_reentry_rebuild_freshness_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_freshness_decay[
            "primary_target_closure_forecast_reset_reentry_rebuild_freshness_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_freshness_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_freshness_reason",
            reset_reentry_rebuild_freshness_decay[
                "primary_target_closure_forecast_reset_reentry_rebuild_freshness_reason"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_freshness_decay[
            "primary_target_closure_forecast_reset_reentry_rebuild_freshness_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_freshness_summary": reset_reentry_rebuild_freshness_decay[
            "closure_forecast_reset_reentry_rebuild_freshness_summary"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reset_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reset_status",
            reset_reentry_rebuild_freshness_decay[
                "primary_target_closure_forecast_reset_reentry_rebuild_reset_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_freshness_decay[
            "primary_target_closure_forecast_reset_reentry_rebuild_reset_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reset_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reset_reason",
            reset_reentry_rebuild_freshness_decay[
                "primary_target_closure_forecast_reset_reentry_rebuild_reset_reason"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_freshness_decay[
            "primary_target_closure_forecast_reset_reentry_rebuild_reset_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reset_summary": reset_reentry_rebuild_freshness_decay[
            "closure_forecast_reset_reentry_rebuild_reset_summary"
        ],
        "stale_reset_reentry_rebuild_hotspots": reset_reentry_rebuild_freshness_decay[
            "stale_reset_reentry_rebuild_hotspots"
        ],
        "fresh_reset_reentry_rebuild_signal_hotspots": reset_reentry_rebuild_freshness_decay[
            "fresh_reset_reentry_rebuild_signal_hotspots"
        ],
        "closure_forecast_reset_reentry_rebuild_decay_window_runs": reset_reentry_rebuild_freshness_decay[
            "closure_forecast_reset_reentry_rebuild_decay_window_runs"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_refresh_recovery_score": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_refresh_recovery_score",
            reset_reentry_rebuild_recovery[
                "primary_target_closure_forecast_reset_reentry_rebuild_refresh_recovery_score"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_recovery[
            "primary_target_closure_forecast_reset_reentry_rebuild_refresh_recovery_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_refresh_recovery_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_refresh_recovery_status",
            reset_reentry_rebuild_recovery[
                "primary_target_closure_forecast_reset_reentry_rebuild_refresh_recovery_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_recovery[
            "primary_target_closure_forecast_reset_reentry_rebuild_refresh_recovery_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_status",
            reset_reentry_rebuild_recovery[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_recovery[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_reason",
            reset_reentry_rebuild_recovery[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_reason"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_recovery[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_refresh_recovery_summary": reset_reentry_rebuild_recovery[
            "closure_forecast_reset_reentry_rebuild_refresh_recovery_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_summary": reset_reentry_rebuild_recovery[
            "closure_forecast_reset_reentry_rebuild_reentry_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_refresh_window_runs": reset_reentry_rebuild_recovery[
            "closure_forecast_reset_reentry_rebuild_refresh_window_runs"
        ],
        "recovering_from_confirmation_rebuild_reset_hotspots": reset_reentry_rebuild_recovery[
            "recovering_from_confirmation_rebuild_reset_hotspots"
        ],
        "recovering_from_clearance_rebuild_reset_hotspots": reset_reentry_rebuild_recovery[
            "recovering_from_clearance_rebuild_reset_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_age_runs": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_age_runs",
            reset_reentry_rebuild_reentry_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_age_runs"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_age_runs"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_score": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_persistence_score",
            reset_reentry_rebuild_reentry_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_score"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_persistence_status",
            reset_reentry_rebuild_reentry_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_persistence_reason",
            reset_reentry_rebuild_reentry_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_reason"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_persistence_summary": reset_reentry_rebuild_reentry_persistence[
            "closure_forecast_reset_reentry_rebuild_reentry_persistence_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_window_runs": reset_reentry_rebuild_reentry_persistence[
            "closure_forecast_reset_reentry_rebuild_reentry_window_runs"
        ],
        "just_reentered_rebuild_hotspots": reset_reentry_rebuild_reentry_persistence[
            "just_reentered_rebuild_hotspots"
        ],
        "holding_reset_reentry_rebuild_reentry_hotspots": reset_reentry_rebuild_reentry_persistence[
            "holding_reset_reentry_rebuild_reentry_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_score": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_churn_score",
            reset_reentry_rebuild_reentry_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_score"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_churn_status",
            reset_reentry_rebuild_reentry_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_churn_reason",
            reset_reentry_rebuild_reentry_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_reason"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_churn_summary": reset_reentry_rebuild_reentry_persistence[
            "closure_forecast_reset_reentry_rebuild_reentry_churn_summary"
        ],
        "reset_reentry_rebuild_reentry_churn_hotspots": reset_reentry_rebuild_reentry_persistence[
            "reset_reentry_rebuild_reentry_churn_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_freshness_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_freshness_status",
            reset_reentry_rebuild_reentry_freshness_decay[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_freshness_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_freshness_decay[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_freshness_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_freshness_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_freshness_reason",
            reset_reentry_rebuild_reentry_freshness_decay[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_freshness_reason"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_freshness_decay[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_freshness_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_freshness_summary": reset_reentry_rebuild_reentry_freshness_decay[
            "closure_forecast_reset_reentry_rebuild_reentry_freshness_summary"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_reset_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_reset_status",
            reset_reentry_rebuild_reentry_freshness_decay[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_reset_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_freshness_decay[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_reset_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_reset_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_reset_reason",
            reset_reentry_rebuild_reentry_freshness_decay[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_reset_reason"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_freshness_decay[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_reset_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_reset_summary": reset_reentry_rebuild_reentry_freshness_decay[
            "closure_forecast_reset_reentry_rebuild_reentry_reset_summary"
        ],
        "stale_reset_reentry_rebuild_reentry_hotspots": reset_reentry_rebuild_reentry_freshness_decay[
            "stale_reset_reentry_rebuild_reentry_hotspots"
        ],
        "fresh_reset_reentry_rebuild_reentry_signal_hotspots": reset_reentry_rebuild_reentry_freshness_decay[
            "fresh_reset_reentry_rebuild_reentry_signal_hotspots"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_decay_window_runs": reset_reentry_rebuild_reentry_freshness_decay[
            "closure_forecast_reset_reentry_rebuild_reentry_decay_window_runs"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_score": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_score",
            reset_reentry_rebuild_reentry_recovery[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_score"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_recovery[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status",
            reset_reentry_rebuild_reentry_recovery[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_recovery[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_status",
            reset_reentry_rebuild_reentry_recovery[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_recovery[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_reason",
            reset_reentry_rebuild_reentry_recovery[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reason"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_recovery[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_summary": reset_reentry_rebuild_reentry_recovery[
            "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_summary": reset_reentry_rebuild_reentry_recovery[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_refresh_window_runs": reset_reentry_rebuild_reentry_recovery[
            "closure_forecast_reset_reentry_rebuild_reentry_refresh_window_runs"
        ],
        "recovering_from_confirmation_rebuild_reentry_reset_hotspots": reset_reentry_rebuild_reentry_recovery[
            "recovering_from_confirmation_rebuild_reentry_reset_hotspots"
        ],
        "recovering_from_clearance_rebuild_reentry_reset_hotspots": reset_reentry_rebuild_reentry_recovery[
            "recovering_from_clearance_rebuild_reentry_reset_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_age_runs": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_age_runs",
            reset_reentry_rebuild_reentry_restore_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_age_runs"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_age_runs"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_score": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_score",
            reset_reentry_rebuild_reentry_restore_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_score"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_status",
            reset_reentry_rebuild_reentry_restore_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_reason",
            reset_reentry_rebuild_reentry_restore_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_reason"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_summary": reset_reentry_rebuild_reentry_restore_persistence[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_window_runs": reset_reentry_rebuild_reentry_restore_persistence[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_window_runs"
        ],
        "just_restored_rebuild_reentry_hotspots": reset_reentry_rebuild_reentry_restore_persistence[
            "just_restored_rebuild_reentry_hotspots"
        ],
        "holding_reset_reentry_rebuild_reentry_restore_hotspots": reset_reentry_rebuild_reentry_restore_persistence[
            "holding_reset_reentry_rebuild_reentry_restore_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_churn_score": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_churn_score",
            reset_reentry_rebuild_reentry_restore_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_churn_score"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_churn_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_churn_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_churn_status",
            reset_reentry_rebuild_reentry_restore_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_churn_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_churn_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_churn_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_churn_reason",
            reset_reentry_rebuild_reentry_restore_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_churn_reason"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_churn_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_churn_summary": reset_reentry_rebuild_reentry_restore_persistence[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_churn_summary"
        ],
        "reset_reentry_rebuild_reentry_restore_churn_hotspots": reset_reentry_rebuild_reentry_restore_persistence[
            "reset_reentry_rebuild_reentry_restore_churn_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_status",
            reset_reentry_rebuild_reentry_restore_freshness_decay[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_freshness_decay[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_reason",
            reset_reentry_rebuild_reentry_restore_freshness_decay[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_reason"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_freshness_decay[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_summary": reset_reentry_rebuild_reentry_restore_freshness_decay[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_summary"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reset_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_reset_status",
            reset_reentry_rebuild_reentry_restore_freshness_decay[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reset_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_freshness_decay[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reset_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reset_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_reset_reason",
            reset_reentry_rebuild_reentry_restore_freshness_decay[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reset_reason"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_freshness_decay[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reset_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_reset_summary": reset_reentry_rebuild_reentry_restore_freshness_decay[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_reset_summary"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_score": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_score",
            reset_reentry_rebuild_reentry_restore_recovery[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_score"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_recovery[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_status",
            reset_reentry_rebuild_reentry_restore_recovery[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_recovery[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status",
            reset_reentry_rebuild_reentry_restore_recovery[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_recovery[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason",
            reset_reentry_rebuild_reentry_restore_recovery[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_recovery[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_summary": reset_reentry_rebuild_reentry_restore_recovery[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_summary": reset_reentry_rebuild_reentry_restore_recovery[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_window_runs": reset_reentry_rebuild_reentry_restore_recovery[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_window_runs"
        ],
        "recovering_from_confirmation_rebuild_reentry_restore_reset_hotspots": reset_reentry_rebuild_reentry_restore_recovery[
            "recovering_from_confirmation_rebuild_reentry_restore_reset_hotspots"
        ],
        "recovering_from_clearance_rebuild_reentry_restore_reset_hotspots": reset_reentry_rebuild_reentry_restore_recovery[
            "recovering_from_clearance_rebuild_reentry_restore_reset_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_age_runs": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_age_runs",
            reset_reentry_rebuild_reentry_restore_rerestore_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_age_runs"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rerestore_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_age_runs"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_score": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_score",
            reset_reentry_rebuild_reentry_restore_rerestore_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_score"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rerestore_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_status",
            reset_reentry_rebuild_reentry_restore_rerestore_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rerestore_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_reason",
            reset_reentry_rebuild_reentry_restore_rerestore_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_reason"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rerestore_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_summary": reset_reentry_rebuild_reentry_restore_rerestore_persistence[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_window_runs": reset_reentry_rebuild_reentry_restore_rerestore_persistence[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_window_runs"
        ],
        "just_rerestored_rebuild_reentry_hotspots": reset_reentry_rebuild_reentry_restore_rerestore_persistence[
            "just_rerestored_rebuild_reentry_hotspots"
        ],
        "holding_reset_reentry_rebuild_reentry_restore_rerestore_hotspots": reset_reentry_rebuild_reentry_restore_rerestore_persistence[
            "holding_reset_reentry_rebuild_reentry_restore_rerestore_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_score": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_score",
            reset_reentry_rebuild_reentry_restore_rerestore_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_score"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rerestore_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_status",
            reset_reentry_rebuild_reentry_restore_rerestore_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rerestore_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_reason",
            reset_reentry_rebuild_reentry_restore_rerestore_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_reason"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rerestore_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_summary": reset_reentry_rebuild_reentry_restore_rerestore_persistence[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_summary"
        ],
        "reset_reentry_rebuild_reentry_restore_rerestore_churn_hotspots": reset_reentry_rebuild_reentry_restore_rerestore_persistence[
            "reset_reentry_rebuild_reentry_restore_rerestore_churn_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status",
            reset_reentry_rebuild_reentry_restore_rerestore_freshness_decay[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rerestore_freshness_decay[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_reason",
            reset_reentry_rebuild_reentry_restore_rerestore_freshness_decay[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_reason"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rerestore_freshness_decay[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_summary": reset_reentry_rebuild_reentry_restore_rerestore_freshness_decay[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_summary"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_status",
            reset_reentry_rebuild_reentry_restore_rerestore_freshness_decay[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rerestore_freshness_decay[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_reason",
            reset_reentry_rebuild_reentry_restore_rerestore_freshness_decay[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_reason"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rerestore_freshness_decay[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_summary": reset_reentry_rebuild_reentry_restore_rerestore_freshness_decay[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_summary"
        ],
        "stale_reset_reentry_rebuild_reentry_restore_rerestore_hotspots": reset_reentry_rebuild_reentry_restore_rerestore_freshness_decay[
            "stale_reset_reentry_rebuild_reentry_restore_rerestore_hotspots"
        ],
        "fresh_reset_reentry_rebuild_reentry_restore_rerestore_signal_hotspots": reset_reentry_rebuild_reentry_restore_rerestore_freshness_decay[
            "fresh_reset_reentry_rebuild_reentry_restore_rerestore_signal_hotspots"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_decay_window_runs": reset_reentry_rebuild_reentry_restore_rerestore_freshness_decay[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_decay_window_runs"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_score": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_score",
            reset_reentry_rebuild_reentry_restore_rerestore_recovery[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_score"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rerestore_recovery[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_status",
            reset_reentry_rebuild_reentry_restore_rerestore_recovery[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rerestore_recovery[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status",
            reset_reentry_rebuild_reentry_restore_rerestore_recovery[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rerestore_recovery[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason",
            reset_reentry_rebuild_reentry_restore_rerestore_recovery[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rerestore_recovery[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_summary": reset_reentry_rebuild_reentry_restore_rerestore_recovery[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_summary": reset_reentry_rebuild_reentry_restore_rerestore_recovery[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_window_runs": reset_reentry_rebuild_reentry_restore_rerestore_recovery[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_window_runs"
        ],
        "recovering_from_confirmation_rebuild_reentry_rerestore_reset_hotspots": reset_reentry_rebuild_reentry_restore_rerestore_recovery[
            "recovering_from_confirmation_rebuild_reentry_rerestore_reset_hotspots"
        ],
        "recovering_from_clearance_rebuild_reentry_rerestore_reset_hotspots": reset_reentry_rebuild_reentry_restore_rerestore_recovery[
            "recovering_from_clearance_rebuild_reentry_rerestore_reset_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs",
            reset_reentry_rebuild_reentry_restore_rererestore_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rererestore_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score",
            reset_reentry_rebuild_reentry_restore_rererestore_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rererestore_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status",
            reset_reentry_rebuild_reentry_restore_rererestore_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rererestore_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason",
            reset_reentry_rebuild_reentry_restore_rererestore_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rererestore_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_summary": reset_reentry_rebuild_reentry_restore_rererestore_persistence[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_window_runs": reset_reentry_rebuild_reentry_restore_rererestore_persistence[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_window_runs"
        ],
        "just_rererestored_rebuild_reentry_hotspots": reset_reentry_rebuild_reentry_restore_rererestore_persistence[
            "just_rererestored_rebuild_reentry_hotspots"
        ],
        "holding_reset_reentry_rebuild_reentry_restore_rererestore_hotspots": reset_reentry_rebuild_reentry_restore_rererestore_persistence[
            "holding_reset_reentry_rebuild_reentry_restore_rererestore_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_score": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_score",
            reset_reentry_rebuild_reentry_restore_rererestore_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_score"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rererestore_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status",
            reset_reentry_rebuild_reentry_restore_rererestore_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rererestore_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason",
            reset_reentry_rebuild_reentry_restore_rererestore_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rererestore_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_summary": reset_reentry_rebuild_reentry_restore_rererestore_persistence[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_summary"
        ],
        "reset_reentry_rebuild_reentry_restore_rererestore_churn_hotspots": reset_reentry_rebuild_reentry_restore_rererestore_persistence[
            "reset_reentry_rebuild_reentry_restore_rererestore_churn_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status",
            reset_reentry_rebuild_reentry_restore_rererestore_freshness_decay[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rererestore_freshness_decay[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_reason",
            reset_reentry_rebuild_reentry_restore_rererestore_freshness_decay[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_reason"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rererestore_freshness_decay[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_summary": reset_reentry_rebuild_reentry_restore_rererestore_freshness_decay[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_summary"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status",
            reset_reentry_rebuild_reentry_restore_rererestore_freshness_decay[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rererestore_freshness_decay[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_reason",
            reset_reentry_rebuild_reentry_restore_rererestore_freshness_decay[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_reason"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rererestore_freshness_decay[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_summary": reset_reentry_rebuild_reentry_restore_rererestore_freshness_decay[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_summary"
        ],
        "stale_reset_reentry_rebuild_reentry_restore_rererestore_hotspots": reset_reentry_rebuild_reentry_restore_rererestore_freshness_decay[
            "stale_reset_reentry_rebuild_reentry_restore_rererestore_hotspots"
        ],
        "fresh_reset_reentry_rebuild_reentry_restore_rererestore_signal_hotspots": reset_reentry_rebuild_reentry_restore_rererestore_freshness_decay[
            "fresh_reset_reentry_rebuild_reentry_restore_rererestore_signal_hotspots"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_decay_window_runs": reset_reentry_rebuild_reentry_restore_rererestore_freshness_decay[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_decay_window_runs"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_score": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_score",
            reset_reentry_rebuild_reentry_restore_rererestore_recovery[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_score"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rererestore_recovery[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status",
            reset_reentry_rebuild_reentry_restore_rererestore_recovery[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rererestore_recovery[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status",
            reset_reentry_rebuild_reentry_restore_rererestore_recovery[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rererestore_recovery[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_reason",
            reset_reentry_rebuild_reentry_restore_rererestore_recovery[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_reason"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rererestore_recovery[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_summary": reset_reentry_rebuild_reentry_restore_rererestore_recovery[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_summary": reset_reentry_rebuild_reentry_restore_rererestore_recovery[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_window_runs": reset_reentry_rebuild_reentry_restore_rererestore_recovery[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_window_runs"
        ],
        "recovering_from_confirmation_rebuild_reentry_rererestore_reset_hotspots": reset_reentry_rebuild_reentry_restore_rererestore_recovery[
            "recovering_from_confirmation_rebuild_reentry_rererestore_reset_hotspots"
        ],
        "recovering_from_clearance_rebuild_reentry_rererestore_reset_hotspots": reset_reentry_rebuild_reentry_restore_rererestore_recovery[
            "recovering_from_clearance_rebuild_reentry_rererestore_reset_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs",
            reset_reentry_rebuild_reentry_restore_rerererestore_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rerererestore_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score",
            reset_reentry_rebuild_reentry_restore_rerererestore_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rerererestore_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status",
            reset_reentry_rebuild_reentry_restore_rerererestore_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rerererestore_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_reason",
            reset_reentry_rebuild_reentry_restore_rerererestore_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_reason"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rerererestore_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_summary": reset_reentry_rebuild_reentry_restore_rerererestore_persistence[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_summary"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_window_runs": reset_reentry_rebuild_reentry_restore_rerererestore_persistence[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_window_runs"
        ],
        "just_rerererestored_rebuild_reentry_hotspots": reset_reentry_rebuild_reentry_restore_rerererestore_persistence[
            "just_rerererestored_rebuild_reentry_hotspots"
        ],
        "holding_reset_reentry_rebuild_reentry_restore_rerererestore_hotspots": reset_reentry_rebuild_reentry_restore_rerererestore_persistence[
            "holding_reset_reentry_rebuild_reentry_restore_rerererestore_hotspots"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score",
            reset_reentry_rebuild_reentry_restore_rerererestore_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rerererestore_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status",
            reset_reentry_rebuild_reentry_restore_rerererestore_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rerererestore_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status"
        ],
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason",
            reset_reentry_rebuild_reentry_restore_rerererestore_persistence[
                "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason"
            ],
        )
        if primary_target
        else reset_reentry_rebuild_reentry_restore_rerererestore_persistence[
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_summary": reset_reentry_rebuild_reentry_restore_rerererestore_persistence[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_summary"
        ],
        "reset_reentry_rebuild_reentry_restore_rerererestore_churn_hotspots": reset_reentry_rebuild_reentry_restore_rerererestore_persistence[
            "reset_reentry_rebuild_reentry_restore_rerererestore_churn_hotspots"
        ],
        "stale_reset_reentry_rebuild_reentry_restore_hotspots": reset_reentry_rebuild_reentry_restore_freshness_decay[
            "stale_reset_reentry_rebuild_reentry_restore_hotspots"
        ],
        "fresh_reset_reentry_rebuild_reentry_restore_signal_hotspots": reset_reentry_rebuild_reentry_restore_freshness_decay[
            "fresh_reset_reentry_rebuild_reentry_restore_signal_hotspots"
        ],
        "closure_forecast_reset_reentry_rebuild_reentry_restore_decay_window_runs": reset_reentry_rebuild_reentry_restore_freshness_decay[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_decay_window_runs"
        ],
        "sustained_class_hotspots": class_trust_momentum["sustained_class_hotspots"],
        "oscillating_class_hotspots": class_trust_momentum["oscillating_class_hotspots"],
        "decision_memory_status": decision_memory["decision_memory_status"],
        "primary_target_last_seen_at": decision_memory["primary_target_last_seen_at"],
        "primary_target_last_intervention": decision_memory["primary_target_last_intervention"],
        "primary_target_last_outcome": decision_memory["primary_target_last_outcome"],
        "primary_target_resolution_evidence": decision_memory["primary_target_resolution_evidence"],
        "recent_interventions": decision_memory["recent_interventions"],
        "recently_quieted_count": decision_memory["recently_quieted_count"],
        "confirmed_resolved_count": decision_memory["confirmed_resolved_count"],
        "reopened_after_resolution_count": decision_memory["reopened_after_resolution_count"],
        "decision_memory_window_runs": decision_memory["decision_memory_window_runs"],
        "resolution_evidence_summary": decision_memory["resolution_evidence_summary"],
        "decision_memory_map": decision_memory_map,
    })
    return payload
