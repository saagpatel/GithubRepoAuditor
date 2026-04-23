from __future__ import annotations

from typing import Any, Callable, Sequence


def reacquisition_event_is_confirmation_like(event: dict[str, Any]) -> bool:
    return (
        event.get("closure_forecast_reacquisition_status", "none")
        in {"pending-confirmation-reacquisition", "reacquired-confirmation"}
        or event.get("closure_forecast_reacquisition_persistence_status", "none")
        in {"just-reacquired", "holding-confirmation", "sustained-confirmation"}
        or event.get("closure_forecast_hysteresis_status", "none")
        in {"pending-confirmation", "confirmed-confirmation"}
        or event.get("transition_closure_likely_outcome", "none") == "confirm-soon"
    )


def reacquisition_event_is_clearance_like(event: dict[str, Any]) -> bool:
    return (
        event.get("closure_forecast_reacquisition_status", "none")
        in {"pending-clearance-reacquisition", "reacquired-clearance"}
        or event.get("closure_forecast_reacquisition_persistence_status", "none")
        in {"holding-clearance", "sustained-clearance"}
        or event.get("closure_forecast_hysteresis_status", "none")
        in {"pending-clearance", "confirmed-clearance"}
        or event.get("transition_closure_likely_outcome", "none") in {"clear-risk", "expire-risk"}
    )


def reacquisition_event_has_evidence(
    event: dict[str, Any],
    *,
    reacquisition_event_is_confirmation_like: Callable[[dict[str, Any]], bool],
    reacquisition_event_is_clearance_like: Callable[[dict[str, Any]], bool],
) -> bool:
    return (
        reacquisition_event_is_confirmation_like(event)
        or reacquisition_event_is_clearance_like(event)
        or event.get("closure_forecast_recovery_churn_status", "none")
        in {"watch", "churn", "blocked"}
    )


def reacquisition_event_signal_label(
    event: dict[str, Any],
    *,
    reacquisition_event_is_confirmation_like: Callable[[dict[str, Any]], bool],
    reacquisition_event_is_clearance_like: Callable[[dict[str, Any]], bool],
) -> str:
    if reacquisition_event_is_confirmation_like(event):
        return "confirmation-like"
    if reacquisition_event_is_clearance_like(event):
        return "clearance-like"
    return "neutral"


def closure_forecast_reacquisition_freshness_reason(
    freshness_status: str,
    weighted_reacquisition_evidence_count: float,
    recent_window_weight_share: float,
    decayed_confirmation_rate: float,
    decayed_clearance_rate: float,
    *,
    class_reacquisition_freshness_window_runs: int,
) -> str:
    if freshness_status == "fresh":
        return (
            "Recent reacquired closure-forecast evidence is still current enough to trust, with "
            f"{recent_window_weight_share:.0%} of the weighted signal coming from the latest "
            f"{class_reacquisition_freshness_window_runs} runs."
        )
    if freshness_status == "mixed-age":
        return (
            "Reacquired closure-forecast memory is still useful, but it is partly aging: "
            f"{recent_window_weight_share:.0%} of the weighted signal is recent and the rest is "
            "older carry-forward."
        )
    if freshness_status == "stale":
        return (
            "Older reacquired forecast strength is carrying more of the signal than recent runs, "
            "so it should not keep stronger posture alive on memory alone."
        )
    return (
        "Reacquired closure-forecast memory is still too lightly exercised to judge freshness, "
        f"with {weighted_reacquisition_evidence_count:.2f} weighted reacquisition run(s), "
        f"{decayed_confirmation_rate:.0%} confirmation-like signal, and "
        f"{decayed_clearance_rate:.0%} clearance-like signal."
    )


def recent_reacquisition_signal_mix(
    weighted_reacquisition_evidence_count: float,
    weighted_confirmation_like: float,
    weighted_clearance_like: float,
    recent_window_weight_share: float,
) -> str:
    return (
        f"{weighted_reacquisition_evidence_count:.2f} weighted reacquisition run(s) with "
        f"{weighted_confirmation_like:.2f} confirmation-like, {weighted_clearance_like:.2f} "
        f"clearance-like, and {recent_window_weight_share:.0%} of the signal from the freshest "
        "runs."
    )


def closure_forecast_reacquisition_freshness_for_target(
    target: dict[str, Any],
    closure_forecast_events: list[dict[str, Any]],
    *,
    target_class_key: Callable[[dict[str, Any]], str],
    reacquisition_event_has_evidence: Callable[[dict[str, Any]], bool],
    reacquisition_event_signal_label: Callable[[dict[str, Any]], str],
    closure_forecast_reacquisition_side_from_status: Callable[[str], str],
    closure_forecast_reacquisition_side_from_event: Callable[[dict[str, Any]], str],
    class_memory_recency_weights: Sequence[float],
    history_window_runs: int,
    class_reacquisition_freshness_window_runs: int,
    freshness_status: Callable[[float, float], str],
    freshness_reason: Callable[[str, float, float, float, float], str],
    recent_signal_mix: Callable[[float, float, float, float], str],
    reacquisition_event_is_confirmation_like: Callable[[dict[str, Any]], bool],
    reacquisition_event_is_clearance_like: Callable[[dict[str, Any]], bool],
) -> dict[str, Any]:
    class_key = target_class_key(target)
    class_events = [event for event in closure_forecast_events if event.get("class_key") == class_key]
    relevant_events: list[dict[str, Any]] = []
    for event in class_events:
        if not reacquisition_event_has_evidence(event):
            continue
        relevant_events.append(event)
        if len(relevant_events) >= history_window_runs:
            break

    weighted_reacquisition_evidence_count = 0.0
    weighted_confirmation_like = 0.0
    weighted_clearance_like = 0.0
    recent_reacquisition_weight = 0.0
    recent_signals = [
        reacquisition_event_signal_label(event)
        for event in relevant_events[:class_reacquisition_freshness_window_runs]
    ]
    current_side = closure_forecast_reacquisition_side_from_status(
        str(target.get("closure_forecast_reacquisition_persistence_status", "none"))
    )
    if current_side == "none":
        current_side = closure_forecast_reacquisition_side_from_event(
            {
                "closure_forecast_reacquisition_status": target.get(
                    "closure_forecast_reacquisition_status",
                    "none",
                ),
                "closure_forecast_refresh_recovery_status": target.get(
                    "closure_forecast_refresh_recovery_status",
                    "none",
                ),
            }
        )

    for index, event in enumerate(relevant_events):
        weight = class_memory_recency_weights[min(index, history_window_runs - 1)]
        weighted_reacquisition_evidence_count += weight
        event_side = closure_forecast_reacquisition_side_from_event(event)
        if index < class_reacquisition_freshness_window_runs and event_side == current_side:
            recent_reacquisition_weight += weight
        if reacquisition_event_is_confirmation_like(event):
            weighted_confirmation_like += weight
        if reacquisition_event_is_clearance_like(event):
            weighted_clearance_like += weight

    recent_window_weight_share = recent_reacquisition_weight / max(
        weighted_reacquisition_evidence_count,
        1.0,
    )
    computed_freshness_status = freshness_status(
        weighted_reacquisition_evidence_count,
        recent_window_weight_share,
    )
    decayed_confirmation_rate = weighted_confirmation_like / max(
        weighted_reacquisition_evidence_count,
        1.0,
    )
    decayed_clearance_rate = weighted_clearance_like / max(
        weighted_reacquisition_evidence_count,
        1.0,
    )
    return {
        "closure_forecast_reacquisition_freshness_status": computed_freshness_status,
        "closure_forecast_reacquisition_freshness_reason": freshness_reason(
            computed_freshness_status,
            weighted_reacquisition_evidence_count,
            recent_window_weight_share,
            decayed_confirmation_rate,
            decayed_clearance_rate,
        ),
        "closure_forecast_reacquisition_memory_weight": round(recent_window_weight_share, 2),
        "decayed_reacquired_confirmation_rate": round(decayed_confirmation_rate, 2),
        "decayed_reacquired_clearance_rate": round(decayed_clearance_rate, 2),
        "recent_reacquisition_signal_mix": recent_signal_mix(
            weighted_reacquisition_evidence_count,
            weighted_confirmation_like,
            weighted_clearance_like,
            recent_window_weight_share,
        ),
        "recent_reacquisition_signal_path": " -> ".join(recent_signals),
        "has_fresh_aligned_recent_evidence": any(
            event.get("closure_forecast_freshness_status", "insufficient-data") == "fresh"
            and closure_forecast_reacquisition_side_from_event(event) == current_side
            for event in relevant_events[:2]
        ),
    }


def apply_reacquisition_freshness_reset_control(
    target: dict[str, Any],
    *,
    freshness_meta: dict[str, Any],
    transition_history_meta: dict[str, Any],
    trust_policy: str,
    trust_policy_reason: str,
    transition_status: str,
    transition_reason: str,
    resolution_status: str,
    resolution_reason: str,
    pending_debt_status: str,
    pending_debt_reason: str,
    policy_debt_status: str,
    policy_debt_reason: str,
    class_normalization_status: str,
    class_normalization_reason: str,
    closure_likely_outcome: str,
    closure_hysteresis_status: str,
    closure_hysteresis_reason: str,
    reacquisition_status: str,
    reacquisition_reason: str,
    persistence_age_runs: int,
    persistence_score: float,
    persistence_status: str,
    persistence_reason: str,
    closure_forecast_reacquisition_side_from_status: Callable[[str], str],
    closure_forecast_reacquisition_side_from_event: Callable[[dict[str, Any]], str],
    target_specific_normalization_noise: Callable[[dict[str, Any], dict[str, Any]], bool],
) -> dict[str, Any]:
    freshness_status = freshness_meta.get(
        "closure_forecast_reacquisition_freshness_status",
        "insufficient-data",
    )
    decayed_clearance_rate = float(
        freshness_meta.get("decayed_reacquired_clearance_rate", 0.0) or 0.0
    )
    churn_status = target.get("closure_forecast_recovery_churn_status", "none")
    recent_pending_status = transition_history_meta.get("recent_pending_status", "none")
    current_side = closure_forecast_reacquisition_side_from_status(persistence_status)
    if current_side == "none":
        current_side = closure_forecast_reacquisition_side_from_event(
            {
                "closure_forecast_reacquisition_status": reacquisition_status,
                "closure_forecast_refresh_recovery_status": target.get(
                    "closure_forecast_refresh_recovery_status",
                    "none",
                ),
            }
        )
    local_noise = target_specific_normalization_noise(target, transition_history_meta)
    has_fresh_aligned_recent_evidence = freshness_meta.get(
        "has_fresh_aligned_recent_evidence",
        False,
    )

    def restore_weaker_pending_posture(
        reset_reason: str,
    ) -> tuple[str, str, str, str, str, str, str, str, str, str, str, str]:
        restored_transition_status = transition_status
        restored_transition_reason = transition_reason
        restored_resolution_status = resolution_status
        restored_resolution_reason = resolution_reason
        next_trust_policy = trust_policy
        next_trust_policy_reason = trust_policy_reason
        next_pending_debt_status = pending_debt_status
        next_pending_debt_reason = pending_debt_reason
        next_policy_debt_status = policy_debt_status
        next_policy_debt_reason = policy_debt_reason
        next_class_normalization_status = class_normalization_status
        next_class_normalization_reason = class_normalization_reason
        if resolution_status == "cleared" and recent_pending_status in {
            "pending-support",
            "pending-caution",
        }:
            restored_transition_status = recent_pending_status
            restored_transition_reason = reset_reason
            restored_resolution_status = "none"
            restored_resolution_reason = ""
            if recent_pending_status == "pending-support":
                reverted_policy = target.get("pre_class_normalization_trust_policy", trust_policy)
                reverted_reason = target.get(
                    "pre_class_normalization_trust_policy_reason",
                    trust_policy_reason,
                )
                next_trust_policy = str(reverted_policy)
                next_trust_policy_reason = (
                    reset_reason if reverted_policy == "verify-first" else str(reverted_reason)
                )
                next_class_normalization_status = "candidate"
                next_class_normalization_reason = reset_reason
            else:
                next_pending_debt_status = next_pending_debt_status or "watch"
                next_pending_debt_reason = next_pending_debt_reason or reset_reason
                next_policy_debt_status = "watch"
                next_policy_debt_reason = reset_reason
        return (
            restored_transition_status,
            restored_transition_reason,
            restored_resolution_status,
            restored_resolution_reason,
            next_trust_policy,
            next_trust_policy_reason,
            next_pending_debt_status,
            next_pending_debt_reason,
            next_policy_debt_status,
            next_policy_debt_reason,
            next_class_normalization_status,
            next_class_normalization_reason,
        )

    if local_noise and current_side != "none":
        blocked_reason = "Local target instability still overrides healthy reacquisition freshness."
        if closure_likely_outcome == "confirm-soon":
            closure_likely_outcome = "hold"
        elif closure_likely_outcome == "expire-risk":
            closure_likely_outcome = "clear-risk"
        if closure_hysteresis_status == "confirmed-confirmation":
            closure_hysteresis_status = "pending-confirmation"
        elif closure_hysteresis_status == "confirmed-clearance":
            closure_hysteresis_status = "pending-clearance"
        closure_hysteresis_reason = blocked_reason
        return {
            "closure_forecast_persistence_reset_status": "blocked",
            "closure_forecast_persistence_reset_reason": blocked_reason,
            "transition_closure_likely_outcome": closure_likely_outcome,
            "closure_forecast_hysteresis_status": closure_hysteresis_status,
            "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "trust_policy": trust_policy,
            "trust_policy_reason": trust_policy_reason,
            "class_pending_debt_status": pending_debt_status,
            "class_pending_debt_reason": pending_debt_reason,
            "policy_debt_status": policy_debt_status,
            "policy_debt_reason": policy_debt_reason,
            "class_normalization_status": class_normalization_status,
            "class_normalization_reason": class_normalization_reason,
            "closure_forecast_reacquisition_status": reacquisition_status,
            "closure_forecast_reacquisition_reason": reacquisition_reason,
            "closure_forecast_reacquisition_age_runs": persistence_age_runs,
            "closure_forecast_reacquisition_persistence_score": persistence_score,
            "closure_forecast_reacquisition_persistence_status": persistence_status,
            "closure_forecast_reacquisition_persistence_reason": persistence_reason,
        }

    if current_side == "confirmation" and freshness_status == "mixed-age":
        if persistence_status in {
            "sustained-confirmation",
            "holding-confirmation",
        } and (churn_status != "churn" or has_fresh_aligned_recent_evidence):
            softened_reason = (
                "Restored confirmation-side posture is still visible, but it is aging and has "
                "been stepped down from sustained strength."
            )
            softened_outcome = closure_likely_outcome
            if softened_outcome == "hold" and reacquisition_status in {
                "pending-confirmation-reacquisition",
                "reacquired-confirmation",
            }:
                softened_outcome = "confirm-soon"
            return {
                "closure_forecast_persistence_reset_status": "confirmation-softened",
                "closure_forecast_persistence_reset_reason": softened_reason,
                "transition_closure_likely_outcome": softened_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": softened_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "trust_policy": trust_policy,
                "trust_policy_reason": trust_policy_reason,
                "class_pending_debt_status": pending_debt_status,
                "class_pending_debt_reason": pending_debt_reason,
                "policy_debt_status": policy_debt_status,
                "policy_debt_reason": policy_debt_reason,
                "class_normalization_status": class_normalization_status,
                "class_normalization_reason": class_normalization_reason,
                "closure_forecast_reacquisition_status": reacquisition_status,
                "closure_forecast_reacquisition_reason": reacquisition_reason,
                "closure_forecast_reacquisition_age_runs": persistence_age_runs,
                "closure_forecast_reacquisition_persistence_score": persistence_score,
                "closure_forecast_reacquisition_persistence_status": "holding-confirmation",
                "closure_forecast_reacquisition_persistence_reason": softened_reason,
            }
        if persistence_status == "holding-confirmation" and churn_status == "churn":
            freshness_status = "stale"

    if current_side == "clearance" and freshness_status == "mixed-age":
        if persistence_status == "sustained-clearance" and (
            churn_status != "churn" or has_fresh_aligned_recent_evidence
        ):
            softened_reason = (
                "Restored clearance-side posture is still visible, but it is aging and has "
                "been stepped down from sustained strength."
            )
            return {
                "closure_forecast_persistence_reset_status": "clearance-softened",
                "closure_forecast_persistence_reset_reason": softened_reason,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": softened_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "trust_policy": trust_policy,
                "trust_policy_reason": trust_policy_reason,
                "class_pending_debt_status": pending_debt_status,
                "class_pending_debt_reason": pending_debt_reason,
                "policy_debt_status": policy_debt_status,
                "policy_debt_reason": policy_debt_reason,
                "class_normalization_status": class_normalization_status,
                "class_normalization_reason": class_normalization_reason,
                "closure_forecast_reacquisition_status": reacquisition_status,
                "closure_forecast_reacquisition_reason": reacquisition_reason,
                "closure_forecast_reacquisition_age_runs": persistence_age_runs,
                "closure_forecast_reacquisition_persistence_score": persistence_score,
                "closure_forecast_reacquisition_persistence_status": "holding-clearance",
                "closure_forecast_reacquisition_persistence_reason": softened_reason,
            }
        if persistence_status == "holding-clearance" and churn_status == "churn":
            freshness_status = "stale"

    needs_reset = (
        current_side in {"confirmation", "clearance"}
        and persistence_status
        in {
            "holding-confirmation",
            "holding-clearance",
            "sustained-confirmation",
            "sustained-clearance",
        }
        and (
            freshness_status in {"stale", "insufficient-data"}
            or not has_fresh_aligned_recent_evidence
            or (
                freshness_status == "mixed-age"
                and churn_status == "churn"
                and not has_fresh_aligned_recent_evidence
            )
        )
    )

    if needs_reset:
        if current_side == "confirmation":
            reset_reason = (
                "Restored confirmation-side posture has aged out enough that the stronger "
                "carry-forward has been withdrawn."
            )
            closure_likely_outcome = "hold"
            if closure_hysteresis_status == "confirmed-confirmation":
                closure_hysteresis_status = "pending-confirmation"
            closure_hysteresis_reason = reset_reason
            return {
                "closure_forecast_persistence_reset_status": "confirmation-reset",
                "closure_forecast_persistence_reset_reason": reset_reason,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "trust_policy": trust_policy,
                "trust_policy_reason": trust_policy_reason,
                "class_pending_debt_status": pending_debt_status,
                "class_pending_debt_reason": pending_debt_reason,
                "policy_debt_status": policy_debt_status,
                "policy_debt_reason": policy_debt_reason,
                "class_normalization_status": class_normalization_status,
                "class_normalization_reason": class_normalization_reason,
                "closure_forecast_reacquisition_status": "none",
                "closure_forecast_reacquisition_reason": reset_reason,
                "closure_forecast_reacquisition_age_runs": 0,
                "closure_forecast_reacquisition_persistence_score": 0.0,
                "closure_forecast_reacquisition_persistence_status": "none",
                "closure_forecast_reacquisition_persistence_reason": "",
            }

        reset_reason = (
            "Restored clearance-side posture has aged out enough that the stronger carry-forward "
            "has been withdrawn."
        )
        if closure_likely_outcome == "expire-risk":
            closure_likely_outcome = "clear-risk"
        elif closure_likely_outcome == "clear-risk":
            closure_likely_outcome = "hold"
        if closure_hysteresis_status == "confirmed-clearance":
            closure_hysteresis_status = "pending-clearance"
        closure_hysteresis_reason = reset_reason
        (
            transition_status,
            transition_reason,
            resolution_status,
            resolution_reason,
            trust_policy,
            trust_policy_reason,
            pending_debt_status,
            pending_debt_reason,
            policy_debt_status,
            policy_debt_reason,
            class_normalization_status,
            class_normalization_reason,
        ) = restore_weaker_pending_posture(reset_reason)
        return {
            "closure_forecast_persistence_reset_status": "clearance-reset",
            "closure_forecast_persistence_reset_reason": reset_reason,
            "transition_closure_likely_outcome": closure_likely_outcome,
            "closure_forecast_hysteresis_status": closure_hysteresis_status,
            "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "trust_policy": trust_policy,
            "trust_policy_reason": trust_policy_reason,
            "class_pending_debt_status": pending_debt_status,
            "class_pending_debt_reason": pending_debt_reason,
            "policy_debt_status": policy_debt_status,
            "policy_debt_reason": policy_debt_reason,
            "class_normalization_status": class_normalization_status,
            "class_normalization_reason": class_normalization_reason,
            "closure_forecast_reacquisition_status": "none",
            "closure_forecast_reacquisition_reason": reset_reason,
            "closure_forecast_reacquisition_age_runs": 0,
            "closure_forecast_reacquisition_persistence_score": 0.0,
            "closure_forecast_reacquisition_persistence_status": "none",
            "closure_forecast_reacquisition_persistence_reason": "",
        }

    if (
        current_side == "clearance"
        and resolution_status == "cleared"
        and recent_pending_status in {"pending-support", "pending-caution"}
        and (
            freshness_status not in {"fresh", "mixed-age"}
            or decayed_clearance_rate < 0.50
            or persistence_status not in {"holding-clearance", "sustained-clearance"}
            or churn_status == "churn"
        )
    ):
        reset_reason = (
            "Restored clearance-side posture has aged out enough that the stronger carry-forward "
            "has been withdrawn."
        )
        (
            transition_status,
            transition_reason,
            resolution_status,
            resolution_reason,
            trust_policy,
            trust_policy_reason,
            pending_debt_status,
            pending_debt_reason,
            policy_debt_status,
            policy_debt_reason,
            class_normalization_status,
            class_normalization_reason,
        ) = restore_weaker_pending_posture(reset_reason)
        return {
            "closure_forecast_persistence_reset_status": "clearance-reset",
            "closure_forecast_persistence_reset_reason": reset_reason,
            "transition_closure_likely_outcome": "hold",
            "closure_forecast_hysteresis_status": "pending-clearance",
            "closure_forecast_hysteresis_reason": reset_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "trust_policy": trust_policy,
            "trust_policy_reason": trust_policy_reason,
            "class_pending_debt_status": pending_debt_status,
            "class_pending_debt_reason": pending_debt_reason,
            "policy_debt_status": policy_debt_status,
            "policy_debt_reason": policy_debt_reason,
            "class_normalization_status": class_normalization_status,
            "class_normalization_reason": class_normalization_reason,
            "closure_forecast_reacquisition_status": "none",
            "closure_forecast_reacquisition_reason": reset_reason,
            "closure_forecast_reacquisition_age_runs": 0,
            "closure_forecast_reacquisition_persistence_score": 0.0,
            "closure_forecast_reacquisition_persistence_status": "none",
            "closure_forecast_reacquisition_persistence_reason": "",
        }

    return {
        "closure_forecast_persistence_reset_status": "none",
        "closure_forecast_persistence_reset_reason": "",
        "transition_closure_likely_outcome": closure_likely_outcome,
        "closure_forecast_hysteresis_status": closure_hysteresis_status,
        "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
        "class_reweight_transition_status": transition_status,
        "class_reweight_transition_reason": transition_reason,
        "class_transition_resolution_status": resolution_status,
        "class_transition_resolution_reason": resolution_reason,
        "trust_policy": trust_policy,
        "trust_policy_reason": trust_policy_reason,
        "class_pending_debt_status": pending_debt_status,
        "class_pending_debt_reason": pending_debt_reason,
        "policy_debt_status": policy_debt_status,
        "policy_debt_reason": policy_debt_reason,
        "class_normalization_status": class_normalization_status,
        "class_normalization_reason": class_normalization_reason,
        "closure_forecast_reacquisition_status": reacquisition_status,
        "closure_forecast_reacquisition_reason": reacquisition_reason,
        "closure_forecast_reacquisition_age_runs": persistence_age_runs,
        "closure_forecast_reacquisition_persistence_score": persistence_score,
        "closure_forecast_reacquisition_persistence_status": persistence_status,
        "closure_forecast_reacquisition_persistence_reason": persistence_reason,
    }


def closure_forecast_reacquisition_freshness_hotspots(
    resolution_targets: list[dict[str, Any]],
    *,
    mode: str,
    target_class_key: Callable[[dict[str, Any]], str],
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for target in resolution_targets:
        class_key = target_class_key(target)
        if not class_key:
            continue
        current = {
            "scope": "class",
            "label": class_key,
            "closure_forecast_reacquisition_freshness_status": target.get(
                "closure_forecast_reacquisition_freshness_status",
                "insufficient-data",
            ),
            "decayed_reacquired_confirmation_rate": target.get(
                "decayed_reacquired_confirmation_rate",
                0.0,
            ),
            "decayed_reacquired_clearance_rate": target.get(
                "decayed_reacquired_clearance_rate",
                0.0,
            ),
            "recent_reacquisition_signal_mix": target.get("recent_reacquisition_signal_mix", ""),
            "recent_reacquisition_persistence_path": target.get(
                "recent_reacquisition_persistence_path",
                "",
            ),
            "dominant_count": max(
                target.get("decayed_reacquired_confirmation_rate", 0.0),
                target.get("decayed_reacquired_clearance_rate", 0.0),
            ),
            "reacquisition_event_count": len(
                [
                    part
                    for part in (target.get("recent_reacquisition_persistence_path", "") or "").split(" -> ")
                    if part
                ]
            ),
        }
        existing = grouped.get(class_key)
        if existing is None or current["dominant_count"] > existing["dominant_count"]:
            grouped[class_key] = current

    hotspots = list(grouped.values())
    if mode == "fresh":
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reacquisition_freshness_status") == "fresh"
            and item.get("dominant_count", 0.0) > 0.0
        ]
    else:
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reacquisition_freshness_status") == "stale"
            and item.get("dominant_count", 0.0) > 0.0
        ]
    hotspots.sort(
        key=lambda item: (
            -float(item.get("dominant_count", 0.0) or 0.0),
            -int(item.get("reacquisition_event_count", 0) or 0),
            str(item.get("label", "")),
        )
    )
    return hotspots[:5]


def closure_forecast_reacquisition_freshness_summary(
    primary_target: dict[str, Any],
    stale_reacquisition_hotspots: list[dict[str, Any]],
    fresh_reacquisition_signal_hotspots: list[dict[str, Any]],
    *,
    target_label: Callable[[dict[str, Any]], str],
) -> str:
    label = target_label(primary_target) or "The current target"
    freshness_status = primary_target.get(
        "closure_forecast_reacquisition_freshness_status",
        "insufficient-data",
    )
    if freshness_status == "fresh":
        return (
            f"{label} still has recent reacquired closure-forecast evidence that is current "
            "enough to keep the restored posture trusted."
        )
    if freshness_status == "mixed-age":
        return (
            f"{label} still has useful reacquired closure-forecast memory, but the restored "
            "posture is no longer getting fully fresh reinforcement."
        )
    if freshness_status == "stale":
        return (
            f"{label} is leaning on older reacquired forecast strength more than fresh runs, so "
            "stronger restored posture should not keep carrying forward on memory alone."
        )
    if fresh_reacquisition_signal_hotspots:
        hotspot = fresh_reacquisition_signal_hotspots[0]
        return (
            f"Fresh reacquisition evidence is strongest around "
            f"{hotspot.get('label', 'recent hotspots')}, so those classes can keep restored "
            "posture more safely than older carry-forward."
        )
    if stale_reacquisition_hotspots:
        hotspot = stale_reacquisition_hotspots[0]
        return (
            f"Older reacquired forecast strength is lingering most around "
            f"{hotspot.get('label', 'recent hotspots')}, so those classes should keep resetting "
            "restored posture when fresh follow-through stops."
        )
    return (
        "Reacquired closure-forecast memory is still too lightly exercised to say whether "
        "restored posture is being reinforced by fresh evidence or older carry-forward."
    )


def closure_forecast_persistence_reset_summary(
    primary_target: dict[str, Any],
    stale_reacquisition_hotspots: list[dict[str, Any]],
    fresh_reacquisition_signal_hotspots: list[dict[str, Any]],
    *,
    target_label: Callable[[dict[str, Any]], str],
) -> str:
    label = target_label(primary_target) or "The current target"
    reset_status = primary_target.get("closure_forecast_persistence_reset_status", "none")
    freshness_status = primary_target.get(
        "closure_forecast_reacquisition_freshness_status",
        "insufficient-data",
    )
    confirmation_rate = primary_target.get("decayed_reacquired_confirmation_rate", 0.0)
    clearance_rate = primary_target.get("decayed_reacquired_clearance_rate", 0.0)
    if reset_status == "confirmation-softened":
        return (
            f"Restored confirmation-side posture for {label} is still visible, but it is aging "
            "and has been stepped down from sustained strength."
        )
    if reset_status == "clearance-softened":
        return (
            f"Restored clearance-side posture for {label} is still visible, but it is aging and "
            "has been stepped down from sustained strength."
        )
    if reset_status == "confirmation-reset":
        return (
            f"Restored confirmation-side posture for {label} has aged out enough that the "
            "stronger carry-forward has been withdrawn."
        )
    if reset_status == "clearance-reset":
        return (
            f"Restored clearance-side posture for {label} has aged out enough that the stronger "
            "carry-forward has been withdrawn."
        )
    if reset_status == "blocked":
        return str(
            primary_target.get(
                "closure_forecast_persistence_reset_reason",
                f"Local target instability still overrides healthy reacquisition freshness for {label}.",
            )
        )
    if freshness_status == "fresh" and confirmation_rate >= clearance_rate:
        return (
            f"Fresh reacquisition evidence for {label} is still reinforcing confirmation-side "
            "restored posture more than clearance pressure."
        )
    if freshness_status == "fresh":
        return (
            f"Fresh reacquisition evidence for {label} is still reinforcing clearance-side "
            "restored posture more than confirmation-side carry-forward."
        )
    if freshness_status == "mixed-age":
        return (
            f"Reacquired posture for {label} is aging enough that it can keep holding, but it "
            "should no longer stay indefinitely at sustained strength."
        )
    if stale_reacquisition_hotspots:
        hotspot = stale_reacquisition_hotspots[0]
        return (
            f"Reacquired posture is aging out fastest around "
            f"{hotspot.get('label', 'recent hotspots')}, so those classes should reset restored "
            "carry-forward instead of relying on older follow-through."
        )
    if fresh_reacquisition_signal_hotspots:
        hotspot = fresh_reacquisition_signal_hotspots[0]
        return (
            f"Fresh reacquisition follow-through is strongest around "
            f"{hotspot.get('label', 'recent hotspots')}, so those classes can preserve restored "
            "posture longer than aging carry-forward elsewhere."
        )
    return "No persistence reset is changing the current restored closure-forecast posture right now."
