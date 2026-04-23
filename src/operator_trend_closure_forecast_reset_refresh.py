from __future__ import annotations

from typing import Any, Callable


def closure_forecast_reset_side_from_status(status: str) -> str:
    if status in {"confirmation-softened", "confirmation-reset"}:
        return "confirmation"
    if status in {"clearance-softened", "clearance-reset"}:
        return "clearance"
    return "none"


def closure_forecast_reset_refresh_path_label(
    event: dict[str, Any],
    *,
    normalized_closure_forecast_direction: Callable[[str, float], str],
) -> str:
    reset_status = event.get("closure_forecast_persistence_reset_status", "none") or "none"
    if reset_status != "none":
        return str(reset_status)
    score = float(event.get("closure_forecast_reweight_score", 0.0) or 0.0)
    direction = normalized_closure_forecast_direction(
        str(event.get("closure_forecast_reweight_direction", "neutral")),
        score,
    )
    freshness = str(
        event.get("closure_forecast_reacquisition_freshness_status", "insufficient-data")
    )
    if direction == "supporting-confirmation":
        return f"{freshness} confirmation"
    if direction == "supporting-clearance":
        return f"{freshness} clearance"
    likely_outcome = str(event.get("transition_closure_likely_outcome", "none") or "none")
    if likely_outcome != "none":
        return likely_outcome
    return "hold"


def closure_forecast_reset_refresh_recovery_for_target(
    target: dict[str, Any],
    closure_forecast_events: list[dict[str, Any]],
    transition_history_meta: dict[str, Any],
    *,
    target_class_key: Callable[[dict[str, Any]], str],
    closure_forecast_reset_side_from_status: Callable[[str], str],
    normalized_closure_forecast_direction: Callable[[str, float], str],
    clamp_round: Callable[[float, float, float], float],
    closure_forecast_direction_majority: Callable[[list[str]], str],
    target_specific_normalization_noise: Callable[[dict[str, Any], dict[str, Any]], bool],
    closure_forecast_direction_reversing: Callable[[str, str], bool],
    closure_forecast_reset_refresh_path_label: Callable[[dict[str, Any]], str],
    class_reset_reentry_window_runs: int,
) -> dict[str, Any]:
    class_key = target_class_key(target)
    matching_events = [
        event for event in closure_forecast_events if event.get("class_key") == class_key
    ][:class_reset_reentry_window_runs]
    recent_reset_side = "none"
    latest_reset_index: int | None = None
    for index, event in enumerate(matching_events):
        event_reset_side = closure_forecast_reset_side_from_status(
            str(event.get("closure_forecast_persistence_reset_status", "none"))
        )
        if event_reset_side != "none":
            recent_reset_side = event_reset_side
            latest_reset_index = index
            break

    relevant_events: list[dict[str, Any]] = []
    directions: list[str] = []
    weighted_total = 0.0
    weight_sum = 0.0
    for event in matching_events:
        score = float(event.get("closure_forecast_reweight_score", 0.0) or 0.0)
        direction = normalized_closure_forecast_direction(
            str(event.get("closure_forecast_reweight_direction", "neutral")),
            score,
        )
        if (
            closure_forecast_reset_side_from_status(
                str(event.get("closure_forecast_persistence_reset_status", "none"))
            )
            == "none"
            and direction == "neutral"
            and abs(score) < 0.05
        ):
            continue
        relevant_events.append(event)
        directions.append(direction)
        if len(relevant_events) > class_reset_reentry_window_runs:
            break
        if direction == "neutral":
            signal_strength = 0.0
            sign = 0.0
        else:
            signal_strength = max(abs(score), 0.05)
            sign = 1.0 if direction == "supporting-confirmation" else -1.0
        freshness_factor = {
            "fresh": 1.00,
            "mixed-age": 0.60,
            "stale": 0.25,
            "insufficient-data": 0.10,
        }.get(
            str(event.get("closure_forecast_reacquisition_freshness_status", "insufficient-data")),
            0.10,
        )
        weight = (1.0, 0.8, 0.6, 0.4)[min(len(relevant_events) - 1, class_reset_reentry_window_runs - 1)]
        weighted_total += sign * signal_strength * freshness_factor * weight
        weight_sum += weight

    recovery_score = clamp_round(weighted_total / max(weight_sum, 1.0), -0.95, 0.95)
    current_score = float(target.get("closure_forecast_reweight_score", 0.0) or 0.0)
    current_direction = normalized_closure_forecast_direction(
        str(target.get("closure_forecast_reweight_direction", "neutral")),
        current_score,
    )
    current_freshness = str(
        target.get("closure_forecast_reacquisition_freshness_status", "insufficient-data")
    )
    current_momentum = str(target.get("closure_forecast_momentum_status", "insufficient-data"))
    current_stability = str(target.get("closure_forecast_stability_status", "watch"))
    earlier_majority = closure_forecast_direction_majority(directions[1:])
    local_noise = target_specific_normalization_noise(target, transition_history_meta)
    direction_reversing = closure_forecast_direction_reversing(current_direction, earlier_majority)
    opposes_reset = (
        recent_reset_side == "confirmation" and current_direction == "supporting-clearance"
    ) or (recent_reset_side == "clearance" and current_direction == "supporting-confirmation")

    aligned_fresh_runs_after_reset = 0
    if latest_reset_index is not None and latest_reset_index > 0:
        for event in matching_events[:latest_reset_index]:
            score = float(event.get("closure_forecast_reweight_score", 0.0) or 0.0)
            direction = normalized_closure_forecast_direction(
                str(event.get("closure_forecast_reweight_direction", "neutral")),
                score,
            )
            event_side = (
                "confirmation"
                if direction == "supporting-confirmation"
                else "clearance"
                if direction == "supporting-clearance"
                else "none"
            )
            if (
                event_side == recent_reset_side
                and event.get("closure_forecast_reacquisition_freshness_status", "insufficient-data")
                == "fresh"
            ):
                aligned_fresh_runs_after_reset += 1
    current_side = (
        "confirmation"
        if current_direction == "supporting-confirmation"
        else "clearance"
        if current_direction == "supporting-clearance"
        else "none"
    )
    current_event_already_counted = any(
        event.get("generated_at", "") == ""
        and float(event.get("closure_forecast_reweight_score", 0.0) or 0.0) == current_score
        and event.get("closure_forecast_reweight_direction", "neutral")
        == target.get("closure_forecast_reweight_direction", "neutral")
        for event in matching_events[: latest_reset_index or 0]
    )
    if current_side == recent_reset_side and current_freshness == "fresh" and not current_event_already_counted:
        aligned_fresh_runs_after_reset += 1

    if len(relevant_events) < 2 or recent_reset_side == "none":
        recovery_status = "none"
    elif local_noise and current_direction == "supporting-confirmation":
        recovery_status = "blocked"
    elif opposes_reset or direction_reversing:
        recovery_status = "reversing"
    elif (
        recent_reset_side == "confirmation"
        and current_direction == "supporting-confirmation"
        and current_freshness == "fresh"
        and recovery_score >= 0.25
        and current_stability != "oscillating"
    ):
        recovery_status = "reentering-confirmation"
    elif (
        recent_reset_side == "clearance"
        and current_direction == "supporting-clearance"
        and current_freshness == "fresh"
        and recovery_score <= -0.25
        and current_stability != "oscillating"
    ):
        recovery_status = "reentering-clearance"
    elif (
        recent_reset_side == "confirmation"
        and current_direction == "supporting-confirmation"
        and current_freshness in {"fresh", "mixed-age"}
        and recovery_score >= 0.15
    ):
        recovery_status = "recovering-confirmation-reset"
    elif (
        recent_reset_side == "clearance"
        and current_direction == "supporting-clearance"
        and current_freshness in {"fresh", "mixed-age"}
        and recovery_score <= -0.15
    ):
        recovery_status = "recovering-clearance-reset"
    else:
        recovery_status = "none"

    if (
        recovery_status == "reentering-confirmation"
        and current_freshness == "fresh"
        and current_momentum == "sustained-confirmation"
        and current_stability == "stable"
        and not local_noise
        and aligned_fresh_runs_after_reset >= 2
    ):
        reentry_status = "reentered-confirmation"
        reentry_reason = (
            "Fresh confirmation-side follow-through has re-earned re-entry into stronger "
            "confirmation-side reacquisition."
        )
    elif (
        recovery_status == "reentering-clearance"
        and current_freshness == "fresh"
        and current_momentum == "sustained-clearance"
        and current_stability == "stable"
        and aligned_fresh_runs_after_reset >= 2
    ):
        reentry_status = "reentered-clearance"
        reentry_reason = (
            "Fresh clearance-side pressure has re-earned re-entry into stronger "
            "clearance-side reacquisition."
        )
    elif local_noise and recovery_status in {
        "recovering-confirmation-reset",
        "reentering-confirmation",
        "blocked",
    }:
        reentry_status = "blocked"
        reentry_reason = "Local target instability is still preventing positive confirmation-side re-entry."
    elif recovery_status in {"recovering-confirmation-reset", "reentering-confirmation"}:
        reentry_status = "pending-confirmation-reentry"
        reentry_reason = (
            "Fresh confirmation-side evidence is returning after a reset, but it has not yet "
            "re-earned re-entry."
        )
    elif recovery_status in {"recovering-clearance-reset", "reentering-clearance"}:
        reentry_status = "pending-clearance-reentry"
        reentry_reason = (
            "Fresh clearance-side evidence is returning after a reset, but it has not yet "
            "re-earned re-entry."
        )
    else:
        reentry_status = "none"
        reentry_reason = ""

    return {
        "closure_forecast_reset_refresh_recovery_score": recovery_score,
        "closure_forecast_reset_refresh_recovery_status": recovery_status,
        "closure_forecast_reset_reentry_status": reentry_status,
        "closure_forecast_reset_reentry_reason": reentry_reason,
        "recent_reset_refresh_path": " -> ".join(
            closure_forecast_reset_refresh_path_label(event) for event in matching_events if event
        ),
        "recent_reset_side": recent_reset_side,
        "aligned_fresh_runs_after_latest_reset": aligned_fresh_runs_after_reset,
    }


def apply_reset_refresh_reentry_control(
    target: dict[str, Any],
    *,
    refresh_meta: dict[str, Any],
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
) -> dict[str, Any]:
    recovery_status = str(refresh_meta.get("closure_forecast_reset_refresh_recovery_status", "none"))
    reentry_status = str(refresh_meta.get("closure_forecast_reset_reentry_status", "none"))
    reentry_reason = str(refresh_meta.get("closure_forecast_reset_reentry_reason", ""))
    recent_reset_side = str(refresh_meta.get("recent_reset_side", "none"))
    current_freshness = str(
        target.get("closure_forecast_reacquisition_freshness_status", "insufficient-data")
    )
    current_stability = str(target.get("closure_forecast_stability_status", "watch"))
    transition_age_runs = int(target.get("class_transition_age_runs", 0) or 0)
    recent_pending_status = str(transition_history_meta.get("recent_pending_status", "none"))
    decayed_clearance_rate = float(target.get("decayed_reacquired_clearance_rate", 0.0) or 0.0)
    persistence_status = "none"
    persistence_reason = ""
    persistence_age_runs = 0
    persistence_score = 0.0

    if reentry_status == "blocked":
        if recent_reset_side == "confirmation":
            closure_likely_outcome = "hold"
            closure_hysteresis_status = "pending-confirmation"
            closure_hysteresis_reason = reentry_reason
            if reacquisition_status == "reacquired-confirmation":
                reacquisition_status = "pending-confirmation-reacquisition"
                reacquisition_reason = reentry_reason
        return {
            "transition_closure_likely_outcome": closure_likely_outcome,
            "closure_forecast_hysteresis_status": closure_hysteresis_status,
            "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reacquisition_status": reacquisition_status,
            "closure_forecast_reacquisition_reason": reacquisition_reason,
            "closure_forecast_reacquisition_age_runs": persistence_age_runs,
            "closure_forecast_reacquisition_persistence_score": persistence_score,
            "closure_forecast_reacquisition_persistence_status": persistence_status,
            "closure_forecast_reacquisition_persistence_reason": persistence_reason,
        }

    if reentry_status == "reentered-confirmation":
        return {
            "transition_closure_likely_outcome": "confirm-soon",
            "closure_forecast_hysteresis_status": "confirmed-confirmation",
            "closure_forecast_hysteresis_reason": reentry_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reacquisition_status": "reacquired-confirmation",
            "closure_forecast_reacquisition_reason": reentry_reason,
            "closure_forecast_reacquisition_age_runs": 0,
            "closure_forecast_reacquisition_persistence_score": 0.0,
            "closure_forecast_reacquisition_persistence_status": "none",
            "closure_forecast_reacquisition_persistence_reason": "",
        }

    if reentry_status == "reentered-clearance":
        restored_outcome = closure_likely_outcome
        if restored_outcome == "hold":
            restored_outcome = "clear-risk"
        elif restored_outcome == "clear-risk" and transition_age_runs >= 3:
            restored_outcome = "expire-risk"
        if (
            resolution_status == "none"
            and recent_pending_status in {"pending-support", "pending-caution"}
            and decayed_clearance_rate >= 0.50
            and current_stability != "oscillating"
        ):
            transition_status = "none"
            transition_reason = ""
            resolution_status = "cleared"
            resolution_reason = reentry_reason
        return {
            "transition_closure_likely_outcome": restored_outcome,
            "closure_forecast_hysteresis_status": "confirmed-clearance",
            "closure_forecast_hysteresis_reason": reentry_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reacquisition_status": "reacquired-clearance",
            "closure_forecast_reacquisition_reason": reentry_reason,
            "closure_forecast_reacquisition_age_runs": 0,
            "closure_forecast_reacquisition_persistence_score": 0.0,
            "closure_forecast_reacquisition_persistence_status": "none",
            "closure_forecast_reacquisition_persistence_reason": "",
        }

    if recent_reset_side == "confirmation":
        if recovery_status in {"recovering-confirmation-reset", "reentering-confirmation"}:
            return {
                "transition_closure_likely_outcome": "hold",
                "closure_forecast_hysteresis_status": "pending-confirmation",
                "closure_forecast_hysteresis_reason": reentry_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reacquisition_status": "pending-confirmation-reacquisition",
                "closure_forecast_reacquisition_reason": reentry_reason,
                "closure_forecast_reacquisition_age_runs": 0,
                "closure_forecast_reacquisition_persistence_score": 0.0,
                "closure_forecast_reacquisition_persistence_status": "none",
                "closure_forecast_reacquisition_persistence_reason": "",
            }
        if recovery_status == "reversing" or current_freshness in {"stale", "insufficient-data"}:
            return {
                "transition_closure_likely_outcome": "hold",
                "closure_forecast_hysteresis_status": "pending-confirmation",
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reacquisition_status": reacquisition_status
                if reacquisition_status != "reacquired-confirmation"
                else "none",
                "closure_forecast_reacquisition_reason": reacquisition_reason,
                "closure_forecast_reacquisition_age_runs": 0,
                "closure_forecast_reacquisition_persistence_score": 0.0,
                "closure_forecast_reacquisition_persistence_status": "none",
                "closure_forecast_reacquisition_persistence_reason": "",
            }

    if recent_reset_side == "clearance":
        if recovery_status in {"recovering-clearance-reset", "reentering-clearance"}:
            weaker_outcome = closure_likely_outcome
            if weaker_outcome == "expire-risk":
                weaker_outcome = "clear-risk"
            return {
                "transition_closure_likely_outcome": weaker_outcome,
                "closure_forecast_hysteresis_status": "pending-clearance",
                "closure_forecast_hysteresis_reason": reentry_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reacquisition_status": "pending-clearance-reacquisition",
                "closure_forecast_reacquisition_reason": reentry_reason,
                "closure_forecast_reacquisition_age_runs": 0,
                "closure_forecast_reacquisition_persistence_score": 0.0,
                "closure_forecast_reacquisition_persistence_status": "none",
                "closure_forecast_reacquisition_persistence_reason": "",
            }
        if recovery_status == "reversing" or current_freshness in {"stale", "insufficient-data"}:
            weaker_outcome = closure_likely_outcome
            if weaker_outcome == "expire-risk":
                weaker_outcome = "clear-risk"
            return {
                "transition_closure_likely_outcome": weaker_outcome,
                "closure_forecast_hysteresis_status": "pending-clearance",
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reacquisition_status": reacquisition_status
                if reacquisition_status != "reacquired-clearance"
                else "none",
                "closure_forecast_reacquisition_reason": reacquisition_reason,
                "closure_forecast_reacquisition_age_runs": 0,
                "closure_forecast_reacquisition_persistence_score": 0.0,
                "closure_forecast_reacquisition_persistence_status": "none",
                "closure_forecast_reacquisition_persistence_reason": "",
            }

    return {
        "transition_closure_likely_outcome": closure_likely_outcome,
        "closure_forecast_hysteresis_status": closure_hysteresis_status,
        "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
        "class_reweight_transition_status": transition_status,
        "class_reweight_transition_reason": transition_reason,
        "class_transition_resolution_status": resolution_status,
        "class_transition_resolution_reason": resolution_reason,
        "closure_forecast_reacquisition_status": reacquisition_status,
        "closure_forecast_reacquisition_reason": reacquisition_reason,
        "closure_forecast_reacquisition_age_runs": target.get("closure_forecast_reacquisition_age_runs", 0),
        "closure_forecast_reacquisition_persistence_score": target.get(
            "closure_forecast_reacquisition_persistence_score",
            0.0,
        ),
        "closure_forecast_reacquisition_persistence_status": target.get(
            "closure_forecast_reacquisition_persistence_status",
            "none",
        ),
        "closure_forecast_reacquisition_persistence_reason": target.get(
            "closure_forecast_reacquisition_persistence_reason",
            "",
        ),
    }


def closure_forecast_reset_refresh_hotspots(
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
            "closure_forecast_reset_refresh_recovery_score": target.get(
                "closure_forecast_reset_refresh_recovery_score",
                0.0,
            ),
            "closure_forecast_reset_refresh_recovery_status": target.get(
                "closure_forecast_reset_refresh_recovery_status",
                "none",
            ),
            "closure_forecast_reset_reentry_status": target.get(
                "closure_forecast_reset_reentry_status",
                "none",
            ),
            "recent_reset_refresh_path": target.get("recent_reset_refresh_path", ""),
        }
        existing = grouped.get(class_key)
        if existing is None or abs(
            float(current["closure_forecast_reset_refresh_recovery_score"] or 0.0)
        ) > abs(float(existing["closure_forecast_reset_refresh_recovery_score"] or 0.0)):
            grouped[class_key] = current
    hotspots = list(grouped.values())
    if mode == "confirmation":
        allowed_statuses = {
            "recovering-confirmation-reset",
            "reentering-confirmation",
            "pending-confirmation-reentry",
            "reentered-confirmation",
        }
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reset_refresh_recovery_status")
            in {"recovering-confirmation-reset", "reentering-confirmation"}
            or item.get("closure_forecast_reset_reentry_status") in allowed_statuses
        ]
    else:
        allowed_statuses = {
            "recovering-clearance-reset",
            "reentering-clearance",
            "pending-clearance-reentry",
            "reentered-clearance",
        }
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reset_refresh_recovery_status")
            in {"recovering-clearance-reset", "reentering-clearance"}
            or item.get("closure_forecast_reset_reentry_status") in allowed_statuses
        ]
    hotspots.sort(
        key=lambda item: (
            -abs(float(item.get("closure_forecast_reset_refresh_recovery_score", 0.0) or 0.0)),
            str(item.get("label", "")),
        )
    )
    return hotspots[:5]


def closure_forecast_reset_refresh_recovery_summary(
    primary_target: dict[str, Any],
    recovering_confirmation_hotspots: list[dict[str, Any]],
    recovering_clearance_hotspots: list[dict[str, Any]],
    *,
    target_label: Callable[[dict[str, Any]], str],
) -> str:
    label = target_label(primary_target) or "The current target"
    status = primary_target.get("closure_forecast_reset_refresh_recovery_status", "none")
    score = float(primary_target.get("closure_forecast_reset_refresh_recovery_score", 0.0) or 0.0)
    if status == "recovering-confirmation-reset":
        return (
            f"Fresh confirmation-side evidence is returning for {label} after a reset, but it "
            f"has not yet re-earned re-entry ({score:.2f})."
        )
    if status == "recovering-clearance-reset":
        return (
            f"Fresh clearance-side evidence is returning for {label} after a reset, but it has "
            f"not yet re-earned re-entry ({score:.2f})."
        )
    if status == "reentering-confirmation":
        return (
            f"Fresh confirmation-side support is strong enough that {label} may re-enter "
            f"confirmation-side reacquisition soon ({score:.2f})."
        )
    if status == "reentering-clearance":
        return (
            f"Fresh clearance-side pressure is strong enough that {label} may re-enter "
            f"clearance-side reacquisition soon ({score:.2f})."
        )
    if status == "reversing":
        return (
            f"The post-reset recovery attempt for {label} is changing direction, so re-entry "
            f"stays blocked ({score:.2f})."
        )
    if status == "blocked":
        return f"Local target instability is still preventing positive confirmation-side re-entry for {label}."
    if recovering_confirmation_hotspots:
        hotspot = recovering_confirmation_hotspots[0]
        return (
            f"Confirmation-side reset recovery is strongest around "
            f"{hotspot.get('label', 'recent hotspots')}, but those classes still need fresh "
            "follow-through before they can re-enter stronger reacquisition."
        )
    if recovering_clearance_hotspots:
        hotspot = recovering_clearance_hotspots[0]
        return (
            f"Clearance-side reset recovery is strongest around "
            f"{hotspot.get('label', 'recent hotspots')}, so those classes are closest to "
            "re-entering stronger clearance-side reacquisition."
        )
    return "No reset-refresh recovery is strong enough yet to re-enter the reacquisition ladder."


def closure_forecast_reset_reentry_summary(
    primary_target: dict[str, Any],
    recovering_confirmation_hotspots: list[dict[str, Any]],
    recovering_clearance_hotspots: list[dict[str, Any]],
    *,
    target_label: Callable[[dict[str, Any]], str],
) -> str:
    label = target_label(primary_target) or "The current target"
    status = primary_target.get("closure_forecast_reset_reentry_status", "none")
    reason = primary_target.get("closure_forecast_reset_reentry_reason", "")
    if status == "reentered-confirmation":
        return (
            reason
            or f"Fresh confirmation-side follow-through has re-earned re-entry into stronger "
            f"confirmation-side reacquisition for {label}."
        )
    if status == "reentered-clearance":
        return (
            reason
            or f"Fresh clearance-side pressure has re-earned re-entry into stronger "
            f"clearance-side reacquisition for {label}."
        )
    if status == "pending-confirmation-reentry":
        return (
            reason
            or f"Confirmation-side evidence is returning for {label}, but re-entry has not been "
            "fully re-earned yet."
        )
    if status == "pending-clearance-reentry":
        return (
            reason
            or f"Clearance-side evidence is returning for {label}, but re-entry has not been "
            "fully re-earned yet."
        )
    if status == "blocked":
        return (
            reason
            or f"Local target instability is still preventing positive confirmation-side re-entry "
            f"for {label}."
        )
    if recovering_confirmation_hotspots:
        hotspot = recovering_confirmation_hotspots[0]
        return (
            f"Confirmation-side re-entry is most active around "
            f"{hotspot.get('label', 'recent hotspots')}, but those classes still need enough "
            "fresh follow-through to climb back into stronger reacquisition."
        )
    if recovering_clearance_hotspots:
        hotspot = recovering_clearance_hotspots[0]
        return (
            f"Clearance-side re-entry is most active around "
            f"{hotspot.get('label', 'recent hotspots')}, so those classes can only climb back "
            "into stronger clearance reacquisition when the fresh pressure keeps holding."
        )
    return "No reset re-entry is strong enough yet to restore stronger reacquisition."
