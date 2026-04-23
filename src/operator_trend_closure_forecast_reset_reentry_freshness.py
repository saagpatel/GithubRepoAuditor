from __future__ import annotations

from typing import Any, Callable, Sequence


def closure_forecast_reset_reentry_freshness_for_target(
    target: dict[str, Any],
    closure_forecast_events: list[dict[str, Any]],
    *,
    target_class_key: Callable[[dict[str, Any]], str],
    reset_reentry_event_has_evidence: Callable[[dict[str, Any]], bool],
    reset_reentry_event_signal_label: Callable[[dict[str, Any]], str],
    closure_forecast_reset_reentry_side_from_persistence_status: Callable[[str], str],
    closure_forecast_reset_reentry_side_from_status: Callable[[str], str],
    closure_forecast_reset_reentry_memory_side_from_event: Callable[[dict[str, Any]], str],
    class_memory_recency_weights: Sequence[float],
    history_window_runs: int,
    class_reset_reentry_freshness_window_runs: int,
    closure_forecast_freshness_status: Callable[[float, float], str],
    closure_forecast_reset_reentry_freshness_reason: Callable[
        [str, float, float, float, float], str
    ],
    recent_reset_reentry_signal_mix: Callable[[float, float, float, float], str],
    reset_reentry_event_is_confirmation_like: Callable[[dict[str, Any]], bool],
    reset_reentry_event_is_clearance_like: Callable[[dict[str, Any]], bool],
) -> dict[str, Any]:
    class_key = target_class_key(target)
    class_events = [
        event for event in closure_forecast_events if event.get("class_key") == class_key
    ]
    relevant_events: list[dict[str, Any]] = []
    for event in class_events:
        if not reset_reentry_event_has_evidence(event):
            continue
        relevant_events.append(event)
        if len(relevant_events) >= history_window_runs:
            break

    weighted_reset_reentry_evidence_count = 0.0
    weighted_confirmation_like = 0.0
    weighted_clearance_like = 0.0
    recent_reset_reentry_weight = 0.0
    recent_signals = [
        reset_reentry_event_signal_label(event)
        for event in relevant_events[:class_reset_reentry_freshness_window_runs]
    ]
    current_side = closure_forecast_reset_reentry_side_from_persistence_status(
        str(target.get("closure_forecast_reset_reentry_persistence_status", "none"))
    )
    if current_side == "none":
        current_side = closure_forecast_reset_reentry_side_from_status(
            str(target.get("closure_forecast_reset_reentry_status", "none"))
        )

    for index, event in enumerate(relevant_events):
        weight = class_memory_recency_weights[min(index, history_window_runs - 1)]
        weighted_reset_reentry_evidence_count += weight
        event_side = closure_forecast_reset_reentry_memory_side_from_event(event)
        if index < class_reset_reentry_freshness_window_runs and event_side == current_side:
            recent_reset_reentry_weight += weight
        if reset_reentry_event_is_confirmation_like(event):
            weighted_confirmation_like += weight
        if reset_reentry_event_is_clearance_like(event):
            weighted_clearance_like += weight

    recent_window_weight_share = recent_reset_reentry_weight / max(
        weighted_reset_reentry_evidence_count,
        1.0,
    )
    freshness_status = closure_forecast_freshness_status(
        weighted_reset_reentry_evidence_count,
        recent_window_weight_share,
    )
    decayed_confirmation_rate = weighted_confirmation_like / max(
        weighted_reset_reentry_evidence_count,
        1.0,
    )
    decayed_clearance_rate = weighted_clearance_like / max(
        weighted_reset_reentry_evidence_count,
        1.0,
    )
    return {
        "closure_forecast_reset_reentry_freshness_status": freshness_status,
        "closure_forecast_reset_reentry_freshness_reason": (
            closure_forecast_reset_reentry_freshness_reason(
                freshness_status,
                weighted_reset_reentry_evidence_count,
                recent_window_weight_share,
                decayed_confirmation_rate,
                decayed_clearance_rate,
            )
        ),
        "closure_forecast_reset_reentry_memory_weight": round(
            recent_window_weight_share,
            2,
        ),
        "decayed_reset_reentered_confirmation_rate": round(
            decayed_confirmation_rate,
            2,
        ),
        "decayed_reset_reentered_clearance_rate": round(
            decayed_clearance_rate,
            2,
        ),
        "recent_reset_reentry_signal_mix": recent_reset_reentry_signal_mix(
            weighted_reset_reentry_evidence_count,
            weighted_confirmation_like,
            weighted_clearance_like,
            recent_window_weight_share,
        ),
        "recent_reset_reentry_signal_path": " -> ".join(recent_signals),
        "has_fresh_aligned_recent_evidence": any(
            closure_forecast_reset_reentry_memory_side_from_event(event) == current_side
            and reset_reentry_event_signal_label(event) != "neutral"
            and event.get("closure_forecast_reacquisition_freshness_status", "insufficient-data")
            == "fresh"
            for event in relevant_events[:2]
        ),
    }


def apply_reset_reentry_freshness_reset_control(
    target: dict[str, Any],
    *,
    freshness_meta: dict[str, Any],
    transition_history_meta: dict[str, Any],
    closure_likely_outcome: str,
    closure_hysteresis_status: str,
    closure_hysteresis_reason: str,
    transition_status: str,
    transition_reason: str,
    resolution_status: str,
    resolution_reason: str,
    reacquisition_status: str,
    reacquisition_reason: str,
    reentry_status: str,
    reentry_reason: str,
    persistence_age_runs: int,
    persistence_score: float,
    persistence_status: str,
    persistence_reason: str,
    closure_forecast_reset_reentry_side_from_persistence_status: Callable[[str], str],
    closure_forecast_reset_reentry_side_from_status: Callable[[str], str],
    target_specific_normalization_noise: Callable[[dict[str, Any], dict[str, Any]], bool],
) -> dict[str, Any]:
    freshness_status = str(
        freshness_meta.get("closure_forecast_reset_reentry_freshness_status", "insufficient-data")
    )
    decayed_clearance_rate = float(
        freshness_meta.get("decayed_reset_reentered_clearance_rate", 0.0) or 0.0
    )
    churn_status = str(target.get("closure_forecast_reset_reentry_churn_status", "none"))
    current_side = closure_forecast_reset_reentry_side_from_persistence_status(persistence_status)
    if current_side == "none":
        current_side = closure_forecast_reset_reentry_side_from_status(reentry_status)
    local_noise = target_specific_normalization_noise(target, transition_history_meta)
    recent_pending_status = str(transition_history_meta.get("recent_pending_status", "none"))
    has_fresh_aligned_recent_evidence = bool(
        freshness_meta.get("has_fresh_aligned_recent_evidence", False)
    )

    def restore_weaker_pending_posture(
        reset_reason: str,
    ) -> tuple[str, str, str, str]:
        restored_transition_status = transition_status
        restored_transition_reason = transition_reason
        restored_resolution_status = resolution_status
        restored_resolution_reason = resolution_reason
        if resolution_status == "cleared" and recent_pending_status in {
            "pending-support",
            "pending-caution",
        }:
            restored_transition_status = recent_pending_status
            restored_transition_reason = reset_reason
            restored_resolution_status = "none"
            restored_resolution_reason = ""
        return (
            restored_transition_status,
            restored_transition_reason,
            restored_resolution_status,
            restored_resolution_reason,
        )

    if local_noise and current_side != "none":
        blocked_reason = "Local target instability still overrides healthy reset re-entry freshness."
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
            "closure_forecast_reset_reentry_reset_status": "blocked",
            "closure_forecast_reset_reentry_reset_reason": blocked_reason,
            "transition_closure_likely_outcome": closure_likely_outcome,
            "closure_forecast_hysteresis_status": closure_hysteresis_status,
            "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reacquisition_status": reacquisition_status,
            "closure_forecast_reacquisition_reason": reacquisition_reason,
            "closure_forecast_reset_reentry_status": reentry_status,
            "closure_forecast_reset_reentry_reason": reentry_reason,
            "closure_forecast_reset_reentry_age_runs": persistence_age_runs,
            "closure_forecast_reset_reentry_persistence_score": persistence_score,
            "closure_forecast_reset_reentry_persistence_status": persistence_status,
            "closure_forecast_reset_reentry_persistence_reason": persistence_reason,
        }

    if current_side == "confirmation" and freshness_status == "mixed-age":
        if persistence_status == "sustained-confirmation-reentry" and (
            churn_status != "churn" or has_fresh_aligned_recent_evidence
        ):
            softened_reason = (
                "Restored confirmation-side reset re-entry posture is still visible, "
                "but it is aging and has been stepped down from sustained strength."
            )
            softened_outcome = closure_likely_outcome
            if softened_outcome == "hold" and reentry_status in {
                "pending-confirmation-reentry",
                "reentered-confirmation",
            }:
                softened_outcome = "confirm-soon"
            return {
                "closure_forecast_reset_reentry_reset_status": "confirmation-softened",
                "closure_forecast_reset_reentry_reset_reason": softened_reason,
                "transition_closure_likely_outcome": softened_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": softened_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reacquisition_status": reacquisition_status,
                "closure_forecast_reacquisition_reason": reacquisition_reason,
                "closure_forecast_reset_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_age_runs": persistence_age_runs,
                "closure_forecast_reset_reentry_persistence_score": persistence_score,
                "closure_forecast_reset_reentry_persistence_status": (
                    "holding-confirmation-reentry"
                ),
                "closure_forecast_reset_reentry_persistence_reason": softened_reason,
            }
        if persistence_status == "holding-confirmation-reentry" and churn_status == "churn":
            freshness_status = "stale"

    if current_side == "clearance" and freshness_status == "mixed-age":
        if persistence_status == "sustained-clearance-reentry" and (
            churn_status != "churn" or has_fresh_aligned_recent_evidence
        ):
            softened_reason = (
                "Restored clearance-side reset re-entry posture is still visible, "
                "but it is aging and has been stepped down from sustained strength."
            )
            return {
                "closure_forecast_reset_reentry_reset_status": "clearance-softened",
                "closure_forecast_reset_reentry_reset_reason": softened_reason,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": softened_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reacquisition_status": reacquisition_status,
                "closure_forecast_reacquisition_reason": reacquisition_reason,
                "closure_forecast_reset_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_age_runs": persistence_age_runs,
                "closure_forecast_reset_reentry_persistence_score": persistence_score,
                "closure_forecast_reset_reentry_persistence_status": (
                    "holding-clearance-reentry"
                ),
                "closure_forecast_reset_reentry_persistence_reason": softened_reason,
            }
        if persistence_status == "holding-clearance-reentry" and churn_status == "churn":
            freshness_status = "stale"

    needs_reset = (
        current_side in {"confirmation", "clearance"}
        and persistence_status
        in {
            "holding-confirmation-reentry",
            "holding-clearance-reentry",
            "sustained-confirmation-reentry",
            "sustained-clearance-reentry",
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
                "Restored confirmation-side reset re-entry posture has aged out enough "
                "that the stronger carry-forward has been withdrawn."
            )
            closure_likely_outcome = "hold"
            if closure_hysteresis_status == "confirmed-confirmation":
                closure_hysteresis_status = "pending-confirmation"
            closure_hysteresis_reason = reset_reason
            return {
                "closure_forecast_reset_reentry_reset_status": "confirmation-reset",
                "closure_forecast_reset_reentry_reset_reason": reset_reason,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reacquisition_status": "none",
                "closure_forecast_reacquisition_reason": reset_reason,
                "closure_forecast_reset_reentry_status": "none",
                "closure_forecast_reset_reentry_reason": reset_reason,
                "closure_forecast_reset_reentry_age_runs": 0,
                "closure_forecast_reset_reentry_persistence_score": 0.0,
                "closure_forecast_reset_reentry_persistence_status": "none",
                "closure_forecast_reset_reentry_persistence_reason": "",
            }

        reset_reason = (
            "Restored clearance-side reset re-entry posture has aged out enough "
            "that the stronger carry-forward has been withdrawn."
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
        ) = restore_weaker_pending_posture(reset_reason)
        return {
            "closure_forecast_reset_reentry_reset_status": "clearance-reset",
            "closure_forecast_reset_reentry_reset_reason": reset_reason,
            "transition_closure_likely_outcome": closure_likely_outcome,
            "closure_forecast_hysteresis_status": closure_hysteresis_status,
            "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reacquisition_status": "none",
            "closure_forecast_reacquisition_reason": reset_reason,
            "closure_forecast_reset_reentry_status": "none",
            "closure_forecast_reset_reentry_reason": reset_reason,
            "closure_forecast_reset_reentry_age_runs": 0,
            "closure_forecast_reset_reentry_persistence_score": 0.0,
            "closure_forecast_reset_reentry_persistence_status": "none",
            "closure_forecast_reset_reentry_persistence_reason": "",
        }

    if (
        current_side == "clearance"
        and resolution_status == "cleared"
        and recent_pending_status in {"pending-support", "pending-caution"}
        and (
            freshness_status not in {"fresh", "mixed-age"}
            or decayed_clearance_rate < 0.50
            or persistence_status
            not in {"holding-clearance-reentry", "sustained-clearance-reentry"}
            or churn_status == "churn"
        )
    ):
        reset_reason = (
            "Restored clearance-side reset re-entry posture has aged out enough "
            "that the stronger carry-forward has been withdrawn."
        )
        (
            transition_status,
            transition_reason,
            resolution_status,
            resolution_reason,
        ) = restore_weaker_pending_posture(reset_reason)
        return {
            "closure_forecast_reset_reentry_reset_status": "clearance-reset",
            "closure_forecast_reset_reentry_reset_reason": reset_reason,
            "transition_closure_likely_outcome": "hold",
            "closure_forecast_hysteresis_status": "pending-clearance",
            "closure_forecast_hysteresis_reason": reset_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reacquisition_status": "none",
            "closure_forecast_reacquisition_reason": reset_reason,
            "closure_forecast_reset_reentry_status": "none",
            "closure_forecast_reset_reentry_reason": reset_reason,
            "closure_forecast_reset_reentry_age_runs": 0,
            "closure_forecast_reset_reentry_persistence_score": 0.0,
            "closure_forecast_reset_reentry_persistence_status": "none",
            "closure_forecast_reset_reentry_persistence_reason": "",
        }

    return {
        "closure_forecast_reset_reentry_reset_status": "none",
        "closure_forecast_reset_reentry_reset_reason": "",
        "transition_closure_likely_outcome": closure_likely_outcome,
        "closure_forecast_hysteresis_status": closure_hysteresis_status,
        "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
        "class_reweight_transition_status": transition_status,
        "class_reweight_transition_reason": transition_reason,
        "class_transition_resolution_status": resolution_status,
        "class_transition_resolution_reason": resolution_reason,
        "closure_forecast_reacquisition_status": reacquisition_status,
        "closure_forecast_reacquisition_reason": reacquisition_reason,
        "closure_forecast_reset_reentry_status": reentry_status,
        "closure_forecast_reset_reentry_reason": reentry_reason,
        "closure_forecast_reset_reentry_age_runs": persistence_age_runs,
        "closure_forecast_reset_reentry_persistence_score": persistence_score,
        "closure_forecast_reset_reentry_persistence_status": persistence_status,
        "closure_forecast_reset_reentry_persistence_reason": persistence_reason,
    }


def closure_forecast_reset_reentry_freshness_hotspots(
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
            "closure_forecast_reset_reentry_freshness_status": target.get(
                "closure_forecast_reset_reentry_freshness_status",
                "insufficient-data",
            ),
            "decayed_reset_reentered_confirmation_rate": target.get(
                "decayed_reset_reentered_confirmation_rate",
                0.0,
            ),
            "decayed_reset_reentered_clearance_rate": target.get(
                "decayed_reset_reentered_clearance_rate",
                0.0,
            ),
            "recent_reset_reentry_signal_mix": target.get(
                "recent_reset_reentry_signal_mix",
                "",
            ),
            "recent_reset_reentry_persistence_path": target.get(
                "recent_reset_reentry_persistence_path",
                "",
            ),
            "dominant_count": max(
                float(target.get("decayed_reset_reentered_confirmation_rate", 0.0) or 0.0),
                float(target.get("decayed_reset_reentered_clearance_rate", 0.0) or 0.0),
            ),
            "reset_reentry_event_count": len(
                [
                    part
                    for part in (
                        str(target.get("recent_reset_reentry_persistence_path", "") or "")
                    ).split(" -> ")
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
            if item.get("closure_forecast_reset_reentry_freshness_status") == "fresh"
            and item.get("dominant_count", 0.0) > 0.0
        ]
    else:
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reset_reentry_freshness_status") == "stale"
            and item.get("dominant_count", 0.0) > 0.0
        ]
    hotspots.sort(
        key=lambda item: (
            -float(item.get("dominant_count", 0.0) or 0.0),
            -int(item.get("reset_reentry_event_count", 0) or 0),
            str(item.get("label", "")),
        )
    )
    return hotspots[:5]


def closure_forecast_reset_reentry_freshness_summary(
    primary_target: dict[str, Any],
    stale_reset_reentry_hotspots: list[dict[str, Any]],
    fresh_reset_reentry_signal_hotspots: list[dict[str, Any]],
    *,
    target_label: Callable[[dict[str, Any]], str],
) -> str:
    label = target_label(primary_target) or "The current target"
    freshness_status = str(
        primary_target.get("closure_forecast_reset_reentry_freshness_status", "insufficient-data")
    )
    if freshness_status == "fresh":
        return (
            f"{label} still has recent reset re-entry evidence that is current enough "
            "to keep the restored posture trusted."
        )
    if freshness_status == "mixed-age":
        return (
            f"{label} still has useful reset re-entry memory, but the restored posture "
            "is no longer getting fully fresh reinforcement."
        )
    if freshness_status == "stale":
        return (
            f"{label} is leaning on older reset re-entry strength more than fresh runs, "
            "so stronger restored posture should not keep carrying forward on memory alone."
        )
    if fresh_reset_reentry_signal_hotspots:
        hotspot = fresh_reset_reentry_signal_hotspots[0]
        return (
            f"Fresh reset re-entry evidence is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes can keep restored posture more safely than older carry-forward."
        )
    if stale_reset_reentry_hotspots:
        hotspot = stale_reset_reentry_hotspots[0]
        return (
            f"Older reset re-entry strength is lingering most around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes should keep resetting restored posture when fresh follow-through stops."
        )
    return (
        "Reset re-entry memory is still too lightly exercised to say whether restored "
        "posture is being reinforced by fresh evidence or older carry-forward."
    )


def closure_forecast_reset_reentry_reset_summary(
    primary_target: dict[str, Any],
    stale_reset_reentry_hotspots: list[dict[str, Any]],
    fresh_reset_reentry_signal_hotspots: list[dict[str, Any]],
    *,
    target_label: Callable[[dict[str, Any]], str],
) -> str:
    label = target_label(primary_target) or "The current target"
    reset_status = str(primary_target.get("closure_forecast_reset_reentry_reset_status", "none"))
    freshness_status = str(
        primary_target.get("closure_forecast_reset_reentry_freshness_status", "insufficient-data")
    )
    confirmation_rate = float(
        primary_target.get("decayed_reset_reentered_confirmation_rate", 0.0) or 0.0
    )
    clearance_rate = float(
        primary_target.get("decayed_reset_reentered_clearance_rate", 0.0) or 0.0
    )
    if reset_status == "confirmation-softened":
        return (
            f"Restored confirmation-side reset re-entry posture for {label} is still visible, "
            "but it is aging and has been stepped down from sustained strength."
        )
    if reset_status == "clearance-softened":
        return (
            f"Restored clearance-side reset re-entry posture for {label} is still visible, "
            "but it is aging and has been stepped down from sustained strength."
        )
    if reset_status == "confirmation-reset":
        return (
            f"Restored confirmation-side reset re-entry posture for {label} has aged out "
            "enough that the stronger carry-forward has been withdrawn."
        )
    if reset_status == "clearance-reset":
        return (
            f"Restored clearance-side reset re-entry posture for {label} has aged out "
            "enough that the stronger carry-forward has been withdrawn."
        )
    if reset_status == "blocked":
        return str(
            primary_target.get(
                "closure_forecast_reset_reentry_reset_reason",
                f"Local target instability still overrides healthy reset re-entry freshness for {label}.",
            )
        )
    if freshness_status == "fresh" and confirmation_rate >= clearance_rate:
        return (
            f"Fresh reset re-entry evidence for {label} is still reinforcing "
            "confirmation-side restored posture more than clearance pressure."
        )
    if freshness_status == "fresh":
        return (
            f"Fresh reset re-entry evidence for {label} is still reinforcing "
            "clearance-side restored posture more than confirmation-side carry-forward."
        )
    if freshness_status == "mixed-age":
        return (
            f"Reset re-entry posture for {label} is aging enough that it can keep holding, "
            "but it should no longer stay indefinitely at sustained strength."
        )
    if stale_reset_reentry_hotspots:
        hotspot = stale_reset_reentry_hotspots[0]
        return (
            f"Reset re-entry posture is aging out fastest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes should reset restored carry-forward instead of relying on older follow-through."
        )
    if fresh_reset_reentry_signal_hotspots:
        hotspot = fresh_reset_reentry_signal_hotspots[0]
        return (
            f"Fresh reset re-entry follow-through is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes can preserve restored posture longer than aging carry-forward elsewhere."
        )
    return "No reset re-entry reset is changing the current restored closure-forecast posture right now."
