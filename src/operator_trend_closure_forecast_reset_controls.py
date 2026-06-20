from __future__ import annotations

from typing import Any, Callable, Sequence


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


def closure_forecast_reset_reentry_refresh_recovery_for_target(
    target: dict[str, Any],
    closure_forecast_events: list[dict[str, Any]],
    transition_history_meta: dict[str, Any],
    *,
    ordered_reset_reentry_events_for_target: Callable[
        [dict[str, Any], list[dict[str, Any]]], list[dict[str, Any]]
    ],
    closure_forecast_reset_side_from_status: Callable[[str], str],
    normalized_closure_forecast_direction: Callable[[str, float], str],
    clamp_round: Callable[..., float],
    closure_forecast_direction_majority: Callable[[list[str]], str],
    target_specific_normalization_noise: Callable[[dict[str, Any], dict[str, Any]], bool],
    closure_forecast_direction_reversing: Callable[[str, str], bool],
    closure_forecast_reset_reentry_refresh_path_label: Callable[[dict[str, Any]], str],
    class_reset_reentry_refresh_rebuild_window_runs: int,
) -> dict[str, Any]:
    matching_events = ordered_reset_reentry_events_for_target(
        target,
        closure_forecast_events,
    )[:class_reset_reentry_refresh_rebuild_window_runs]
    recent_reset_reentry_side = "none"
    latest_reset_index: int | None = None
    for index, event in enumerate(matching_events):
        event_reset_side = closure_forecast_reset_side_from_status(
            str(event.get("closure_forecast_reset_reentry_reset_status", "none"))
        )
        if event_reset_side != "none":
            recent_reset_reentry_side = event_reset_side
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
                str(event.get("closure_forecast_reset_reentry_reset_status", "none"))
            )
            == "none"
            and direction == "neutral"
            and abs(score) < 0.05
        ):
            continue
        relevant_events.append(event)
        directions.append(direction)
        if len(relevant_events) > class_reset_reentry_refresh_rebuild_window_runs:
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
            str(event.get("closure_forecast_reset_reentry_freshness_status", "insufficient-data")),
            0.10,
        )
        weight = (1.0, 0.8, 0.6, 0.4)[
            min(len(relevant_events) - 1, class_reset_reentry_refresh_rebuild_window_runs - 1)
        ]
        weighted_total += sign * signal_strength * freshness_factor * weight
        weight_sum += weight

    recovery_score = clamp_round(
        weighted_total / max(weight_sum, 1.0),
        lower=-0.95,
        upper=0.95,
    )
    current_score = float(target.get("closure_forecast_reweight_score", 0.0) or 0.0)
    current_direction = normalized_closure_forecast_direction(
        str(target.get("closure_forecast_reweight_direction", "neutral")),
        current_score,
    )
    current_freshness = str(
        target.get("closure_forecast_reset_reentry_freshness_status", "insufficient-data")
    )
    current_momentum = str(target.get("closure_forecast_momentum_status", "insufficient-data"))
    current_stability = str(target.get("closure_forecast_stability_status", "watch"))
    earlier_majority = closure_forecast_direction_majority(directions[1:])
    local_noise = target_specific_normalization_noise(target, transition_history_meta)
    direction_reversing = closure_forecast_direction_reversing(
        current_direction,
        earlier_majority,
    )
    opposes_reset = (
        recent_reset_reentry_side == "confirmation"
        and current_direction == "supporting-clearance"
    ) or (
        recent_reset_reentry_side == "clearance"
        and current_direction == "supporting-confirmation"
    )
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
                event_side == recent_reset_reentry_side
                and event.get(
                    "closure_forecast_reset_reentry_freshness_status",
                    "insufficient-data",
                )
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
    if (
        current_side == recent_reset_reentry_side
        and current_freshness == "fresh"
        and not current_event_already_counted
    ):
        aligned_fresh_runs_after_reset += 1

    if len(relevant_events) < 2 or recent_reset_reentry_side == "none":
        recovery_status = "none"
    elif local_noise and current_direction == "supporting-confirmation":
        recovery_status = "blocked"
    elif opposes_reset or direction_reversing:
        recovery_status = "reversing"
    elif (
        recent_reset_reentry_side == "confirmation"
        and current_direction == "supporting-confirmation"
        and current_freshness == "fresh"
        and recovery_score >= 0.25
        and current_stability != "oscillating"
    ):
        recovery_status = "rebuilding-confirmation-reentry"
    elif (
        recent_reset_reentry_side == "clearance"
        and current_direction == "supporting-clearance"
        and current_freshness == "fresh"
        and recovery_score <= -0.25
        and current_stability != "oscillating"
    ):
        recovery_status = "rebuilding-clearance-reentry"
    elif (
        recent_reset_reentry_side == "confirmation"
        and current_direction == "supporting-confirmation"
        and current_freshness in {"fresh", "mixed-age"}
        and recovery_score >= 0.15
    ):
        recovery_status = "recovering-confirmation-reentry-reset"
    elif (
        recent_reset_reentry_side == "clearance"
        and current_direction == "supporting-clearance"
        and current_freshness in {"fresh", "mixed-age"}
        and recovery_score <= -0.15
    ):
        recovery_status = "recovering-clearance-reentry-reset"
    else:
        recovery_status = "none"

    if (
        recovery_status == "rebuilding-confirmation-reentry"
        and current_freshness == "fresh"
        and current_momentum == "sustained-confirmation"
        and current_stability == "stable"
        and not local_noise
        and aligned_fresh_runs_after_reset >= 2
    ):
        rebuild_status = "rebuilt-confirmation-reentry"
        rebuild_reason = (
            "Fresh confirmation-side follow-through has rebuilt stronger "
            "confirmation-side reset re-entry."
        )
    elif (
        recovery_status == "rebuilding-clearance-reentry"
        and current_freshness == "fresh"
        and current_momentum == "sustained-clearance"
        and current_stability == "stable"
        and aligned_fresh_runs_after_reset >= 2
    ):
        rebuild_status = "rebuilt-clearance-reentry"
        rebuild_reason = (
            "Fresh clearance-side pressure has rebuilt stronger clearance-side "
            "reset re-entry."
        )
    elif local_noise and recovery_status in {
        "recovering-confirmation-reentry-reset",
        "rebuilding-confirmation-reentry",
        "blocked",
    }:
        rebuild_status = "blocked"
        rebuild_reason = (
            "Local target instability is still preventing positive confirmation-side "
            "reset re-entry rebuild."
        )
    elif recovery_status in {
        "recovering-confirmation-reentry-reset",
        "rebuilding-confirmation-reentry",
    }:
        rebuild_status = "pending-confirmation-rebuild"
        rebuild_reason = (
            "Fresh confirmation-side evidence is returning after reset re-entry was "
            "softened or reset, but it has not yet rebuilt stronger reset re-entry."
        )
    elif recovery_status in {
        "recovering-clearance-reentry-reset",
        "rebuilding-clearance-reentry",
    }:
        rebuild_status = "pending-clearance-rebuild"
        rebuild_reason = (
            "Fresh clearance-side evidence is returning after reset re-entry was "
            "softened or reset, but it has not yet rebuilt stronger reset re-entry."
        )
    else:
        rebuild_status = "none"
        rebuild_reason = ""

    return {
        "closure_forecast_reset_reentry_refresh_recovery_score": recovery_score,
        "closure_forecast_reset_reentry_refresh_recovery_status": recovery_status,
        "closure_forecast_reset_reentry_rebuild_status": rebuild_status,
        "closure_forecast_reset_reentry_rebuild_reason": rebuild_reason,
        "recent_reset_reentry_refresh_path": " -> ".join(
            closure_forecast_reset_reentry_refresh_path_label(event)
            for event in matching_events
            if event
        ),
        "recent_reset_reentry_side": recent_reset_reentry_side,
        "aligned_fresh_runs_after_latest_reset_reentry_reset": aligned_fresh_runs_after_reset,
    }


def apply_reset_reentry_refresh_rebuild_control(
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
    reentry_status: str,
    reentry_reason: str,
    persistence_age_runs: int,
    persistence_score: float,
    persistence_status: str,
    persistence_reason: str,
) -> dict[str, Any]:
    recovery_status = str(
        refresh_meta.get("closure_forecast_reset_reentry_refresh_recovery_status", "none")
    )
    rebuild_status = str(refresh_meta.get("closure_forecast_reset_reentry_rebuild_status", "none"))
    rebuild_reason = str(refresh_meta.get("closure_forecast_reset_reentry_rebuild_reason", ""))
    recent_reset_reentry_side = str(refresh_meta.get("recent_reset_reentry_side", "none"))
    current_freshness = str(
        target.get("closure_forecast_reset_reentry_freshness_status", "insufficient-data")
    )
    current_stability = str(target.get("closure_forecast_stability_status", "watch"))
    transition_age_runs = int(target.get("class_transition_age_runs", 0) or 0)
    recent_pending_status = str(transition_history_meta.get("recent_pending_status", "none"))
    decayed_clearance_rate = float(
        target.get("decayed_reset_reentered_clearance_rate", 0.0) or 0.0
    )

    if rebuild_status == "blocked":
        if recent_reset_reentry_side == "confirmation":
            closure_likely_outcome = "hold"
            closure_hysteresis_status = "pending-confirmation"
            closure_hysteresis_reason = rebuild_reason
            if reacquisition_status == "reacquired-confirmation":
                reacquisition_status = "pending-confirmation-reacquisition"
                reacquisition_reason = rebuild_reason
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
            "closure_forecast_reset_reentry_status": reentry_status,
            "closure_forecast_reset_reentry_reason": reentry_reason,
            "closure_forecast_reset_reentry_age_runs": persistence_age_runs,
            "closure_forecast_reset_reentry_persistence_score": persistence_score,
            "closure_forecast_reset_reentry_persistence_status": persistence_status,
            "closure_forecast_reset_reentry_persistence_reason": persistence_reason,
        }

    if rebuild_status == "rebuilt-confirmation-reentry":
        return {
            "transition_closure_likely_outcome": "confirm-soon",
            "closure_forecast_hysteresis_status": "confirmed-confirmation",
            "closure_forecast_hysteresis_reason": rebuild_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reacquisition_status": "reacquired-confirmation",
            "closure_forecast_reacquisition_reason": rebuild_reason,
            "closure_forecast_reset_reentry_status": "reentered-confirmation",
            "closure_forecast_reset_reentry_reason": rebuild_reason,
            "closure_forecast_reset_reentry_age_runs": 0,
            "closure_forecast_reset_reentry_persistence_score": 0.0,
            "closure_forecast_reset_reentry_persistence_status": "none",
            "closure_forecast_reset_reentry_persistence_reason": "",
        }

    if rebuild_status == "rebuilt-clearance-reentry":
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
            resolution_reason = rebuild_reason
        return {
            "transition_closure_likely_outcome": restored_outcome,
            "closure_forecast_hysteresis_status": "confirmed-clearance",
            "closure_forecast_hysteresis_reason": rebuild_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reacquisition_status": "reacquired-clearance",
            "closure_forecast_reacquisition_reason": rebuild_reason,
            "closure_forecast_reset_reentry_status": "reentered-clearance",
            "closure_forecast_reset_reentry_reason": rebuild_reason,
            "closure_forecast_reset_reentry_age_runs": 0,
            "closure_forecast_reset_reentry_persistence_score": 0.0,
            "closure_forecast_reset_reentry_persistence_status": "none",
            "closure_forecast_reset_reentry_persistence_reason": "",
        }

    if recent_reset_reentry_side == "confirmation":
        if rebuild_status == "pending-confirmation-rebuild":
            return {
                "transition_closure_likely_outcome": "hold",
                "closure_forecast_hysteresis_status": "pending-confirmation",
                "closure_forecast_hysteresis_reason": rebuild_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reacquisition_status": "pending-confirmation-reacquisition",
                "closure_forecast_reacquisition_reason": rebuild_reason,
                "closure_forecast_reset_reentry_status": "pending-confirmation-reentry",
                "closure_forecast_reset_reentry_reason": rebuild_reason,
                "closure_forecast_reset_reentry_age_runs": 0,
                "closure_forecast_reset_reentry_persistence_score": 0.0,
                "closure_forecast_reset_reentry_persistence_status": "none",
                "closure_forecast_reset_reentry_persistence_reason": "",
            }
        if recovery_status == "reversing" or current_freshness in {"stale", "insufficient-data"}:
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
                "closure_forecast_reset_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_age_runs": persistence_age_runs,
                "closure_forecast_reset_reentry_persistence_score": persistence_score,
                "closure_forecast_reset_reentry_persistence_status": persistence_status,
                "closure_forecast_reset_reentry_persistence_reason": persistence_reason,
            }

    if recent_reset_reentry_side == "clearance":
        if rebuild_status == "pending-clearance-rebuild":
            weaker_outcome = closure_likely_outcome
            if weaker_outcome == "expire-risk":
                weaker_outcome = "clear-risk"
            return {
                "transition_closure_likely_outcome": weaker_outcome,
                "closure_forecast_hysteresis_status": "pending-clearance",
                "closure_forecast_hysteresis_reason": rebuild_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reacquisition_status": "pending-clearance-reacquisition",
                "closure_forecast_reacquisition_reason": rebuild_reason,
                "closure_forecast_reset_reentry_status": "pending-clearance-reentry",
                "closure_forecast_reset_reentry_reason": rebuild_reason,
                "closure_forecast_reset_reentry_age_runs": 0,
                "closure_forecast_reset_reentry_persistence_score": 0.0,
                "closure_forecast_reset_reentry_persistence_status": "none",
                "closure_forecast_reset_reentry_persistence_reason": "",
            }
        if recovery_status == "reversing" or current_freshness in {"stale", "insufficient-data"}:
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
                "closure_forecast_reset_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_age_runs": persistence_age_runs,
                "closure_forecast_reset_reentry_persistence_score": persistence_score,
                "closure_forecast_reset_reentry_persistence_status": persistence_status,
                "closure_forecast_reset_reentry_persistence_reason": persistence_reason,
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
        "closure_forecast_reset_reentry_status": reentry_status,
        "closure_forecast_reset_reentry_reason": reentry_reason,
        "closure_forecast_reset_reentry_age_runs": persistence_age_runs,
        "closure_forecast_reset_reentry_persistence_score": persistence_score,
        "closure_forecast_reset_reentry_persistence_status": persistence_status,
        "closure_forecast_reset_reentry_persistence_reason": persistence_reason,
    }


def closure_forecast_reset_reentry_refresh_hotspots(
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
            "closure_forecast_reset_reentry_refresh_recovery_score": target.get(
                "closure_forecast_reset_reentry_refresh_recovery_score",
                0.0,
            ),
            "closure_forecast_reset_reentry_refresh_recovery_status": target.get(
                "closure_forecast_reset_reentry_refresh_recovery_status",
                "none",
            ),
            "recent_reset_reentry_refresh_path": target.get(
                "recent_reset_reentry_refresh_path",
                "",
            ),
        }
        existing = grouped.get(class_key)
        if existing is None or abs(
            float(current["closure_forecast_reset_reentry_refresh_recovery_score"] or 0.0)
        ) > abs(float(existing["closure_forecast_reset_reentry_refresh_recovery_score"] or 0.0)):
            grouped[class_key] = current
    hotspots = list(grouped.values())
    if mode == "confirmation":
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reset_reentry_refresh_recovery_status")
            in {
                "recovering-confirmation-reentry-reset",
                "rebuilding-confirmation-reentry",
            }
        ]
        hotspots.sort(
            key=lambda item: (
                -float(item.get("closure_forecast_reset_reentry_refresh_recovery_score", 0.0) or 0.0),
                str(item.get("label", "")),
            )
        )
    else:
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reset_reentry_refresh_recovery_status")
            in {
                "recovering-clearance-reentry-reset",
                "rebuilding-clearance-reentry",
            }
        ]
        hotspots.sort(
            key=lambda item: (
                float(item.get("closure_forecast_reset_reentry_refresh_recovery_score", 0.0) or 0.0),
                str(item.get("label", "")),
            )
        )
    return hotspots[:5]


def closure_forecast_reset_reentry_refresh_recovery_summary(
    primary_target: dict[str, Any],
    recovering_confirmation_hotspots: list[dict[str, Any]],
    recovering_clearance_hotspots: list[dict[str, Any]],
    *,
    target_label: Callable[[dict[str, Any]], str],
) -> str:
    label = target_label(primary_target) or "The current target"
    status = str(
        primary_target.get("closure_forecast_reset_reentry_refresh_recovery_status", "none")
    )
    score = float(primary_target.get("closure_forecast_reset_reentry_refresh_recovery_score", 0.0) or 0.0)
    if status == "recovering-confirmation-reentry-reset":
        return (
            f"Fresh confirmation-side evidence is returning after reset re-entry softened or reset for {label}, "
            f"but it has not yet rebuilt stronger reset re-entry ({score:.2f})."
        )
    if status == "recovering-clearance-reentry-reset":
        return (
            f"Fresh clearance-side evidence is returning after reset re-entry softened or reset for {label}, "
            f"but it has not yet rebuilt stronger reset re-entry ({score:.2f})."
        )
    if status == "rebuilding-confirmation-reentry":
        return (
            f"Confirmation-side reset re-entry for {label} is rebuilding strongly enough "
            f"that stronger restored posture may be re-earned soon ({score:.2f})."
        )
    if status == "rebuilding-clearance-reentry":
        return (
            f"Clearance-side reset re-entry for {label} is rebuilding strongly enough "
            f"that stronger restored caution may be re-earned soon ({score:.2f})."
        )
    if status == "reversing":
        return (
            f"The post-reset reset re-entry recovery attempt for {label} is changing "
            f"direction, so rebuild stays blocked ({score:.2f})."
        )
    if status == "blocked":
        return str(
            primary_target.get(
                "closure_forecast_reset_reentry_rebuild_reason",
                f"Local target instability is still preventing positive confirmation-side "
                f"reset re-entry rebuild for {label}.",
            )
        )
    if recovering_confirmation_hotspots:
        hotspot = recovering_confirmation_hotspots[0]
        return (
            f"Confirmation-side reset re-entry recovery is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes are closest to rebuilding stronger restored confirmation posture."
        )
    if recovering_clearance_hotspots:
        hotspot = recovering_clearance_hotspots[0]
        return (
            f"Clearance-side reset re-entry recovery is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes are closest to rebuilding stronger restored clearance posture."
        )
    return "No reset re-entry rebuild attempt is active enough yet to re-earn stronger restored posture."


def closure_forecast_reset_reentry_rebuild_summary(
    primary_target: dict[str, Any],
    recovering_confirmation_hotspots: list[dict[str, Any]],
    recovering_clearance_hotspots: list[dict[str, Any]],
    *,
    target_label: Callable[[dict[str, Any]], str],
) -> str:
    label = target_label(primary_target) or "The current target"
    status = str(primary_target.get("closure_forecast_reset_reentry_rebuild_status", "none"))
    if status == "pending-confirmation-rebuild":
        return (
            f"Fresh confirmation-side evidence is returning after reset re-entry softened or reset for {label}, "
            "but stronger reset re-entry still needs more fresh follow-through before it is rebuilt."
        )
    if status == "pending-clearance-rebuild":
        return (
            f"Fresh clearance-side evidence is returning after reset re-entry softened or reset for {label}, "
            "but stronger reset re-entry still needs more fresh follow-through before it is rebuilt."
        )
    if status == "rebuilt-confirmation-reentry":
        return (
            f"Fresh confirmation-side follow-through for {label} has rebuilt stronger "
            "confirmation-side reset re-entry."
        )
    if status == "rebuilt-clearance-reentry":
        return (
            f"Fresh clearance-side pressure for {label} has rebuilt stronger clearance-side "
            "reset re-entry."
        )
    if status == "blocked":
        return str(
            primary_target.get(
                "closure_forecast_reset_reentry_rebuild_reason",
                f"Local target instability is still preventing positive confirmation-side "
                f"reset re-entry rebuild for {label}.",
            )
        )
    if recovering_confirmation_hotspots:
        hotspot = recovering_confirmation_hotspots[0]
        return (
            f"Confirmation-side reset re-entry rebuild is closest around {hotspot.get('label', 'recent hotspots')}, "
            "but it still needs one more layer of fresh confirmation follow-through."
        )
    if recovering_clearance_hotspots:
        hotspot = recovering_clearance_hotspots[0]
        return (
            f"Clearance-side reset re-entry rebuild is closest around {hotspot.get('label', 'recent hotspots')}, "
            "but it still needs one more layer of fresh clearance follow-through."
        )
    return "No reset re-entry rebuild is changing the current restored closure-forecast posture right now."


def _reset_reentry_rebuild_event_is_confirmation_like(
    event: dict[str, Any],
    *,
    closure_forecast_reset_reentry_rebuild_side_from_event: Callable[[dict[str, Any]], str],
) -> bool:
    event_side = closure_forecast_reset_reentry_rebuild_side_from_event(event)
    persistence_status = str(
        event.get("closure_forecast_reset_reentry_rebuild_persistence_status", "none")
    )
    return (
        event.get("closure_forecast_reset_reentry_rebuild_status", "none")
        in {"pending-confirmation-rebuild", "rebuilt-confirmation-reentry"}
        or (
            persistence_status
            in {
                "just-rebuilt",
                "holding-confirmation-rebuild",
                "sustained-confirmation-rebuild",
            }
            and event_side == "confirmation"
        )
        or event.get("closure_forecast_hysteresis_status", "none")
        in {"pending-confirmation", "confirmed-confirmation"}
        or event.get("transition_closure_likely_outcome", "none") == "confirm-soon"
    )


def _reset_reentry_rebuild_event_is_clearance_like(
    event: dict[str, Any],
    *,
    closure_forecast_reset_reentry_rebuild_side_from_event: Callable[[dict[str, Any]], str],
) -> bool:
    event_side = closure_forecast_reset_reentry_rebuild_side_from_event(event)
    persistence_status = str(
        event.get("closure_forecast_reset_reentry_rebuild_persistence_status", "none")
    )
    return (
        event.get("closure_forecast_reset_reentry_rebuild_status", "none")
        in {"pending-clearance-rebuild", "rebuilt-clearance-reentry"}
        or (
            persistence_status
            in {
                "just-rebuilt",
                "holding-clearance-rebuild",
                "sustained-clearance-rebuild",
            }
            and event_side == "clearance"
        )
        or event.get("closure_forecast_hysteresis_status", "none")
        in {"pending-clearance", "confirmed-clearance"}
        or event.get("transition_closure_likely_outcome", "none") in {"clear-risk", "expire-risk"}
    )


def _reset_reentry_rebuild_event_has_evidence(
    event: dict[str, Any],
    *,
    closure_forecast_reset_reentry_rebuild_side_from_event: Callable[[dict[str, Any]], str],
) -> bool:
    return (
        _reset_reentry_rebuild_event_is_confirmation_like(
            event,
            closure_forecast_reset_reentry_rebuild_side_from_event=(
                closure_forecast_reset_reentry_rebuild_side_from_event
            ),
        )
        or _reset_reentry_rebuild_event_is_clearance_like(
            event,
            closure_forecast_reset_reentry_rebuild_side_from_event=(
                closure_forecast_reset_reentry_rebuild_side_from_event
            ),
        )
        or event.get("closure_forecast_reset_reentry_rebuild_churn_status", "none")
        in {"watch", "churn", "blocked"}
    )


def _reset_reentry_rebuild_event_signal_label(
    event: dict[str, Any],
    *,
    closure_forecast_reset_reentry_rebuild_side_from_event: Callable[[dict[str, Any]], str],
) -> str:
    if _reset_reentry_rebuild_event_is_confirmation_like(
        event,
        closure_forecast_reset_reentry_rebuild_side_from_event=(
            closure_forecast_reset_reentry_rebuild_side_from_event
        ),
    ):
        return "confirmation-like"
    if _reset_reentry_rebuild_event_is_clearance_like(
        event,
        closure_forecast_reset_reentry_rebuild_side_from_event=(
            closure_forecast_reset_reentry_rebuild_side_from_event
        ),
    ):
        return "clearance-like"
    return "neutral"


def _closure_forecast_reset_reentry_rebuild_freshness_reason(
    freshness_status: str,
    weighted_rebuild_evidence_count: float,
    recent_window_weight_share: float,
    decayed_confirmation_rate: float,
    decayed_clearance_rate: float,
    *,
    class_reset_reentry_rebuild_freshness_window_runs: int,
) -> str:
    if freshness_status == "fresh":
        return (
            "Recent rebuilt reset re-entry evidence is still current enough to keep the "
            "restored posture trusted, with "
            f"{recent_window_weight_share:.0%} of the weighted signal coming from the latest "
            f"{class_reset_reentry_rebuild_freshness_window_runs} runs."
        )
    if freshness_status == "mixed-age":
        return (
            "Rebuilt reset re-entry memory is still useful, but it is partly aging: "
            f"{recent_window_weight_share:.0%} of the weighted signal is recent and the rest is "
            "older carry-forward."
        )
    if freshness_status == "stale":
        return (
            "Older rebuilt reset re-entry strength is carrying more of the signal than recent "
            "runs, so it should not keep stronger posture alive on memory alone."
        )
    return (
        "Rebuilt reset re-entry memory is still too lightly exercised to judge freshness, with "
        f"{weighted_rebuild_evidence_count:.2f} weighted rebuilt run(s), "
        f"{decayed_confirmation_rate:.0%} confirmation-like signal, and "
        f"{decayed_clearance_rate:.0%} clearance-like signal."
    )


def _recent_reset_reentry_rebuild_signal_mix(
    weighted_rebuild_evidence_count: float,
    weighted_confirmation_like: float,
    weighted_clearance_like: float,
    recent_window_weight_share: float,
) -> str:
    return (
        f"{weighted_rebuild_evidence_count:.2f} weighted rebuilt run(s) with "
        f"{weighted_confirmation_like:.2f} confirmation-like, "
        f"{weighted_clearance_like:.2f} clearance-like, and "
        f"{recent_window_weight_share:.0%} of the signal from the freshest runs."
    )


def closure_forecast_reset_reentry_rebuild_freshness_for_target(
    target: dict[str, Any],
    closure_forecast_events: list[dict[str, Any]],
    *,
    target_class_key: Callable[[dict[str, Any]], str],
    closure_forecast_reset_reentry_rebuild_side_from_event: Callable[[dict[str, Any]], str],
    closure_forecast_reset_reentry_rebuild_side_from_persistence_status: Callable[[str], str],
    closure_forecast_reset_reentry_rebuild_side_from_status: Callable[[str], str],
    closure_forecast_freshness_status: Callable[[float, float], str],
    class_memory_recency_weights: tuple[float, ...],
    class_reset_reentry_rebuild_freshness_window_runs: int,
    history_window_runs: int,
) -> dict[str, Any]:
    class_key = target_class_key(target)
    class_events = [event for event in closure_forecast_events if event.get("class_key") == class_key]
    relevant_events: list[dict[str, Any]] = []
    for event in class_events:
        if not _reset_reentry_rebuild_event_has_evidence(
            event,
            closure_forecast_reset_reentry_rebuild_side_from_event=(
                closure_forecast_reset_reentry_rebuild_side_from_event
            ),
        ):
            continue
        relevant_events.append(event)
        if len(relevant_events) >= history_window_runs:
            break

    weighted_rebuild_evidence_count = 0.0
    weighted_confirmation_like = 0.0
    weighted_clearance_like = 0.0
    recent_rebuild_weight = 0.0
    recent_signals = [
        _reset_reentry_rebuild_event_signal_label(
            event,
            closure_forecast_reset_reentry_rebuild_side_from_event=(
                closure_forecast_reset_reentry_rebuild_side_from_event
            ),
        )
        for event in relevant_events[:class_reset_reentry_rebuild_freshness_window_runs]
    ]
    current_side = closure_forecast_reset_reentry_rebuild_side_from_persistence_status(
        str(target.get("closure_forecast_reset_reentry_rebuild_persistence_status", "none"))
    )
    if current_side == "none":
        current_side = closure_forecast_reset_reentry_rebuild_side_from_status(
            str(target.get("closure_forecast_reset_reentry_rebuild_status", "none"))
        )

    for index, event in enumerate(relevant_events):
        weight = class_memory_recency_weights[min(index, history_window_runs - 1)]
        weighted_rebuild_evidence_count += weight
        event_side = closure_forecast_reset_reentry_rebuild_side_from_event(event)
        if index < class_reset_reentry_rebuild_freshness_window_runs and event_side == current_side:
            recent_rebuild_weight += weight
        if _reset_reentry_rebuild_event_is_confirmation_like(
            event,
            closure_forecast_reset_reentry_rebuild_side_from_event=(
                closure_forecast_reset_reentry_rebuild_side_from_event
            ),
        ):
            weighted_confirmation_like += weight
        if _reset_reentry_rebuild_event_is_clearance_like(
            event,
            closure_forecast_reset_reentry_rebuild_side_from_event=(
                closure_forecast_reset_reentry_rebuild_side_from_event
            ),
        ):
            weighted_clearance_like += weight

    recent_window_weight_share = recent_rebuild_weight / max(weighted_rebuild_evidence_count, 1.0)
    freshness_status = closure_forecast_freshness_status(
        weighted_rebuild_evidence_count,
        recent_window_weight_share,
    )
    decayed_confirmation_rate = weighted_confirmation_like / max(weighted_rebuild_evidence_count, 1.0)
    decayed_clearance_rate = weighted_clearance_like / max(weighted_rebuild_evidence_count, 1.0)
    return {
        "closure_forecast_reset_reentry_rebuild_freshness_status": freshness_status,
        "closure_forecast_reset_reentry_rebuild_freshness_reason": (
            _closure_forecast_reset_reentry_rebuild_freshness_reason(
                freshness_status,
                weighted_rebuild_evidence_count,
                recent_window_weight_share,
                decayed_confirmation_rate,
                decayed_clearance_rate,
                class_reset_reentry_rebuild_freshness_window_runs=(
                    class_reset_reentry_rebuild_freshness_window_runs
                ),
            )
        ),
        "closure_forecast_reset_reentry_rebuild_memory_weight": round(
            recent_window_weight_share,
            2,
        ),
        "decayed_rebuilt_confirmation_reentry_rate": round(decayed_confirmation_rate, 2),
        "decayed_rebuilt_clearance_reentry_rate": round(decayed_clearance_rate, 2),
        "recent_reset_reentry_rebuild_signal_mix": _recent_reset_reentry_rebuild_signal_mix(
            weighted_rebuild_evidence_count,
            weighted_confirmation_like,
            weighted_clearance_like,
            recent_window_weight_share,
        ),
        "recent_reset_reentry_rebuild_signal_path": " -> ".join(recent_signals),
        "has_fresh_aligned_recent_evidence": any(
            closure_forecast_reset_reentry_rebuild_side_from_event(event) == current_side
            and _reset_reentry_rebuild_event_signal_label(
                event,
                closure_forecast_reset_reentry_rebuild_side_from_event=(
                    closure_forecast_reset_reentry_rebuild_side_from_event
                ),
            )
            != "neutral"
            for event in relevant_events[:2]
        ),
    }


def apply_reset_reentry_rebuild_freshness_reset_control(
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
    rebuild_status: str,
    rebuild_reason: str,
    persistence_age_runs: int,
    persistence_score: float,
    persistence_status: str,
    persistence_reason: str,
    closure_forecast_reset_reentry_rebuild_side_from_persistence_status: Callable[[str], str],
    closure_forecast_reset_reentry_rebuild_side_from_status: Callable[[str], str],
    target_specific_normalization_noise: Callable[[dict[str, Any], dict[str, Any]], bool],
) -> dict[str, Any]:
    freshness_status = str(
        freshness_meta.get("closure_forecast_reset_reentry_rebuild_freshness_status", "insufficient-data")
    )
    decayed_clearance_rate = float(
        freshness_meta.get("decayed_rebuilt_clearance_reentry_rate", 0.0) or 0.0
    )
    churn_status = str(target.get("closure_forecast_reset_reentry_rebuild_churn_status", "none"))
    current_side = closure_forecast_reset_reentry_rebuild_side_from_persistence_status(
        persistence_status
    )
    if current_side == "none":
        current_side = closure_forecast_reset_reentry_rebuild_side_from_status(rebuild_status)
    local_noise = target_specific_normalization_noise(target, transition_history_meta)
    recent_pending_status = str(transition_history_meta.get("recent_pending_status", "none"))
    has_fresh_aligned_recent_evidence = bool(
        freshness_meta.get("has_fresh_aligned_recent_evidence", False)
    )

    def _restore_weaker_pending_posture(reset_reason: str) -> tuple[str, str, str, str]:
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
        blocked_reason = (
            "Local target instability still overrides healthy rebuilt reset re-entry freshness."
        )
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
            "closure_forecast_reset_reentry_rebuild_reset_status": "blocked",
            "closure_forecast_reset_reentry_rebuild_reset_reason": blocked_reason,
            "transition_closure_likely_outcome": closure_likely_outcome,
            "closure_forecast_hysteresis_status": closure_hysteresis_status,
            "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reset_reentry_rebuild_status": rebuild_status,
            "closure_forecast_reset_reentry_rebuild_reason": rebuild_reason,
            "closure_forecast_reset_reentry_rebuild_age_runs": persistence_age_runs,
            "closure_forecast_reset_reentry_rebuild_persistence_score": persistence_score,
            "closure_forecast_reset_reentry_rebuild_persistence_status": persistence_status,
            "closure_forecast_reset_reentry_rebuild_persistence_reason": persistence_reason,
        }

    if current_side == "confirmation" and freshness_status == "mixed-age":
        if persistence_status == "sustained-confirmation-rebuild" and (
            churn_status != "churn" or has_fresh_aligned_recent_evidence
        ):
            softened_reason = (
                "Restored confirmation-side rebuilt posture is still visible, but it is aging "
                "and has been stepped down from sustained strength."
            )
            softened_outcome = closure_likely_outcome
            if softened_outcome == "hold" and rebuild_status in {
                "pending-confirmation-rebuild",
                "rebuilt-confirmation-reentry",
            }:
                softened_outcome = "confirm-soon"
            return {
                "closure_forecast_reset_reentry_rebuild_reset_status": "confirmation-softened",
                "closure_forecast_reset_reentry_rebuild_reset_reason": softened_reason,
                "transition_closure_likely_outcome": softened_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": softened_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reset_reentry_rebuild_status": rebuild_status,
                "closure_forecast_reset_reentry_rebuild_reason": rebuild_reason,
                "closure_forecast_reset_reentry_rebuild_age_runs": persistence_age_runs,
                "closure_forecast_reset_reentry_rebuild_persistence_score": persistence_score,
                "closure_forecast_reset_reentry_rebuild_persistence_status": "holding-confirmation-rebuild",
                "closure_forecast_reset_reentry_rebuild_persistence_reason": softened_reason,
            }
        if persistence_status == "holding-confirmation-rebuild" and churn_status == "churn":
            freshness_status = "stale"

    if current_side == "clearance" and freshness_status == "mixed-age":
        if persistence_status == "sustained-clearance-rebuild" and (
            churn_status != "churn" or has_fresh_aligned_recent_evidence
        ):
            softened_reason = (
                "Restored clearance-side rebuilt posture is still visible, but it is aging and "
                "has been stepped down from sustained strength."
            )
            return {
                "closure_forecast_reset_reentry_rebuild_reset_status": "clearance-softened",
                "closure_forecast_reset_reentry_rebuild_reset_reason": softened_reason,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": softened_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reset_reentry_rebuild_status": rebuild_status,
                "closure_forecast_reset_reentry_rebuild_reason": rebuild_reason,
                "closure_forecast_reset_reentry_rebuild_age_runs": persistence_age_runs,
                "closure_forecast_reset_reentry_rebuild_persistence_score": persistence_score,
                "closure_forecast_reset_reentry_rebuild_persistence_status": "holding-clearance-rebuild",
                "closure_forecast_reset_reentry_rebuild_persistence_reason": softened_reason,
            }
        if persistence_status == "holding-clearance-rebuild" and churn_status == "churn":
            freshness_status = "stale"

    needs_reset = (
        current_side in {"confirmation", "clearance"}
        and persistence_status
        in {
            "holding-confirmation-rebuild",
            "holding-clearance-rebuild",
            "sustained-confirmation-rebuild",
            "sustained-clearance-rebuild",
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
                "Restored confirmation-side rebuilt posture has aged out enough that the "
                "stronger carry-forward has been withdrawn."
            )
            closure_likely_outcome = "hold"
            if closure_hysteresis_status == "confirmed-confirmation":
                closure_hysteresis_status = "pending-confirmation"
            closure_hysteresis_reason = reset_reason
            return {
                "closure_forecast_reset_reentry_rebuild_reset_status": "confirmation-reset",
                "closure_forecast_reset_reentry_rebuild_reset_reason": reset_reason,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reset_reentry_rebuild_status": "none",
                "closure_forecast_reset_reentry_rebuild_reason": reset_reason,
                "closure_forecast_reset_reentry_rebuild_age_runs": 0,
                "closure_forecast_reset_reentry_rebuild_persistence_score": 0.0,
                "closure_forecast_reset_reentry_rebuild_persistence_status": "none",
                "closure_forecast_reset_reentry_rebuild_persistence_reason": "",
            }

        reset_reason = (
            "Restored clearance-side rebuilt posture has aged out enough that the stronger "
            "carry-forward has been withdrawn."
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
        ) = _restore_weaker_pending_posture(reset_reason)
        return {
            "closure_forecast_reset_reentry_rebuild_reset_status": "clearance-reset",
            "closure_forecast_reset_reentry_rebuild_reset_reason": reset_reason,
            "transition_closure_likely_outcome": closure_likely_outcome,
            "closure_forecast_hysteresis_status": closure_hysteresis_status,
            "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reset_reentry_rebuild_status": "none",
            "closure_forecast_reset_reentry_rebuild_reason": reset_reason,
            "closure_forecast_reset_reentry_rebuild_age_runs": 0,
            "closure_forecast_reset_reentry_rebuild_persistence_score": 0.0,
            "closure_forecast_reset_reentry_rebuild_persistence_status": "none",
            "closure_forecast_reset_reentry_rebuild_persistence_reason": "",
        }

    if (
        current_side == "clearance"
        and resolution_status == "cleared"
        and recent_pending_status in {"pending-support", "pending-caution"}
        and (
            freshness_status not in {"fresh", "mixed-age"}
            or decayed_clearance_rate < 0.50
            or persistence_status
            not in {
                "holding-clearance-rebuild",
                "sustained-clearance-rebuild",
            }
            or churn_status == "churn"
        )
    ):
        reset_reason = (
            "Restored clearance-side rebuilt posture has aged out enough that the stronger "
            "carry-forward has been withdrawn."
        )
        (
            transition_status,
            transition_reason,
            resolution_status,
            resolution_reason,
        ) = _restore_weaker_pending_posture(reset_reason)
        return {
            "closure_forecast_reset_reentry_rebuild_reset_status": "clearance-reset",
            "closure_forecast_reset_reentry_rebuild_reset_reason": reset_reason,
            "transition_closure_likely_outcome": "hold",
            "closure_forecast_hysteresis_status": "pending-clearance",
            "closure_forecast_hysteresis_reason": reset_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reset_reentry_rebuild_status": "none",
            "closure_forecast_reset_reentry_rebuild_reason": reset_reason,
            "closure_forecast_reset_reentry_rebuild_age_runs": 0,
            "closure_forecast_reset_reentry_rebuild_persistence_score": 0.0,
            "closure_forecast_reset_reentry_rebuild_persistence_status": "none",
            "closure_forecast_reset_reentry_rebuild_persistence_reason": "",
        }

    return {
        "closure_forecast_reset_reentry_rebuild_reset_status": "none",
        "closure_forecast_reset_reentry_rebuild_reset_reason": "",
        "transition_closure_likely_outcome": closure_likely_outcome,
        "closure_forecast_hysteresis_status": closure_hysteresis_status,
        "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
        "class_reweight_transition_status": transition_status,
        "class_reweight_transition_reason": transition_reason,
        "class_transition_resolution_status": resolution_status,
        "class_transition_resolution_reason": resolution_reason,
        "closure_forecast_reset_reentry_rebuild_status": rebuild_status,
        "closure_forecast_reset_reentry_rebuild_reason": rebuild_reason,
        "closure_forecast_reset_reentry_rebuild_age_runs": persistence_age_runs,
        "closure_forecast_reset_reentry_rebuild_persistence_score": persistence_score,
        "closure_forecast_reset_reentry_rebuild_persistence_status": persistence_status,
        "closure_forecast_reset_reentry_rebuild_persistence_reason": persistence_reason,
    }


def closure_forecast_reset_reentry_rebuild_freshness_hotspots(
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
            "closure_forecast_reset_reentry_rebuild_freshness_status": target.get(
                "closure_forecast_reset_reentry_rebuild_freshness_status",
                "insufficient-data",
            ),
            "decayed_rebuilt_confirmation_reentry_rate": target.get(
                "decayed_rebuilt_confirmation_reentry_rate",
                0.0,
            ),
            "decayed_rebuilt_clearance_reentry_rate": target.get(
                "decayed_rebuilt_clearance_reentry_rate",
                0.0,
            ),
            "recent_reset_reentry_rebuild_signal_mix": target.get(
                "recent_reset_reentry_rebuild_signal_mix",
                "",
            ),
            "recent_reset_reentry_rebuild_persistence_path": target.get(
                "recent_reset_reentry_rebuild_persistence_path",
                "",
            ),
            "dominant_count": max(
                float(target.get("decayed_rebuilt_confirmation_reentry_rate", 0.0) or 0.0),
                float(target.get("decayed_rebuilt_clearance_reentry_rate", 0.0) or 0.0),
            ),
            "rebuild_event_count": len(
                [
                    part
                    for part in (
                        target.get("recent_reset_reentry_rebuild_persistence_path", "") or ""
                    ).split(" -> ")
                    if part
                ]
            ),
        }
        existing = grouped.get(class_key)
        if existing is None or float(current["dominant_count"]) > float(existing["dominant_count"]):
            grouped[class_key] = current

    hotspots = list(grouped.values())
    if mode == "fresh":
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reset_reentry_rebuild_freshness_status") == "fresh"
            and float(item.get("dominant_count", 0.0) or 0.0) > 0.0
        ]
    else:
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reset_reentry_rebuild_freshness_status") == "stale"
            and float(item.get("dominant_count", 0.0) or 0.0) > 0.0
        ]
    hotspots.sort(
        key=lambda item: (
            -float(item.get("dominant_count", 0.0) or 0.0),
            -int(item.get("rebuild_event_count", 0) or 0),
            str(item.get("label", "")),
        )
    )
    return hotspots[:5]


def closure_forecast_reset_reentry_rebuild_freshness_summary(
    primary_target: dict[str, Any],
    stale_reset_reentry_rebuild_hotspots: list[dict[str, Any]],
    fresh_reset_reentry_rebuild_signal_hotspots: list[dict[str, Any]],
    *,
    target_label: Callable[[dict[str, Any]], str],
) -> str:
    label = target_label(primary_target) or "The current target"
    freshness_status = str(
        primary_target.get("closure_forecast_reset_reentry_rebuild_freshness_status", "insufficient-data")
    )
    if freshness_status == "fresh":
        return (
            f"{label} still has recent rebuilt reset re-entry evidence that is current enough to "
            "keep the restored posture trusted."
        )
    if freshness_status == "mixed-age":
        return (
            f"{label} still has useful rebuilt reset re-entry memory, but the restored posture is "
            "no longer getting fully fresh reinforcement."
        )
    if freshness_status == "stale":
        return (
            f"{label} is leaning on older rebuilt reset re-entry strength more than fresh runs, "
            "so stronger restored posture should not keep carrying forward on memory alone."
        )
    if fresh_reset_reentry_rebuild_signal_hotspots:
        hotspot = fresh_reset_reentry_rebuild_signal_hotspots[0]
        return (
            f"Fresh rebuilt reset re-entry evidence is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes can keep restored posture more safely than older carry-forward."
        )
    if stale_reset_reentry_rebuild_hotspots:
        hotspot = stale_reset_reentry_rebuild_hotspots[0]
        return (
            f"Older rebuilt reset re-entry strength is lingering most around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes should keep resetting restored posture when fresh follow-through stops."
        )
    return (
        "Rebuilt reset re-entry memory is still too lightly exercised to say whether restored "
        "posture is being reinforced by fresh evidence or older carry-forward."
    )


def closure_forecast_reset_reentry_rebuild_reset_summary(
    primary_target: dict[str, Any],
    stale_reset_reentry_rebuild_hotspots: list[dict[str, Any]],
    fresh_reset_reentry_rebuild_signal_hotspots: list[dict[str, Any]],
    *,
    target_label: Callable[[dict[str, Any]], str],
) -> str:
    label = target_label(primary_target) or "The current target"
    reset_status = str(
        primary_target.get("closure_forecast_reset_reentry_rebuild_reset_status", "none")
    )
    freshness_status = str(
        primary_target.get("closure_forecast_reset_reentry_rebuild_freshness_status", "insufficient-data")
    )
    confirmation_rate = float(
        primary_target.get("decayed_rebuilt_confirmation_reentry_rate", 0.0) or 0.0
    )
    clearance_rate = float(
        primary_target.get("decayed_rebuilt_clearance_reentry_rate", 0.0) or 0.0
    )
    if reset_status == "confirmation-softened":
        return (
            f"Restored confirmation-side rebuilt posture for {label} is still visible, but it is "
            "aging and has been stepped down from sustained strength."
        )
    if reset_status == "clearance-softened":
        return (
            f"Restored clearance-side rebuilt posture for {label} is still visible, but it is "
            "aging and has been stepped down from sustained strength."
        )
    if reset_status == "confirmation-reset":
        return (
            f"Restored confirmation-side rebuilt posture for {label} has aged out enough that the "
            "stronger carry-forward has been withdrawn."
        )
    if reset_status == "clearance-reset":
        return (
            f"Restored clearance-side rebuilt posture for {label} has aged out enough that the "
            "stronger carry-forward has been withdrawn."
        )
    if reset_status == "blocked":
        return str(
            primary_target.get(
                "closure_forecast_reset_reentry_rebuild_reset_reason",
                f"Local target instability still overrides healthy rebuilt freshness for {label}.",
            )
        )
    if freshness_status == "fresh" and confirmation_rate >= clearance_rate:
        return (
            f"Fresh rebuilt evidence for {label} is still reinforcing confirmation-side restored "
            "posture more than clearance pressure."
        )
    if freshness_status == "fresh":
        return (
            f"Fresh rebuilt evidence for {label} is still reinforcing clearance-side restored "
            "posture more than confirmation-side carry-forward."
        )
    if freshness_status == "mixed-age":
        return (
            f"Rebuilt posture for {label} is aging enough that it can keep holding, but it should "
            "no longer stay indefinitely at sustained strength."
        )
    if stale_reset_reentry_rebuild_hotspots:
        hotspot = stale_reset_reentry_rebuild_hotspots[0]
        return (
            f"Rebuilt posture is aging out fastest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes should reset restored carry-forward instead of relying on older follow-through."
        )
    if fresh_reset_reentry_rebuild_signal_hotspots:
        hotspot = fresh_reset_reentry_rebuild_signal_hotspots[0]
        return (
            f"Fresh rebuilt follow-through is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes can preserve restored posture longer than aging carry-forward elsewhere."
        )
    return (
        "No rebuilt reset re-entry reset is changing the current restored closure-forecast "
        "posture right now."
    )


def apply_reset_reentry_rebuild_freshness_and_reset(
    resolution_targets: list[dict[str, Any]],
    history: list[dict[str, Any]],
    *,
    current_generated_at: str,
    confidence_calibration: dict[str, Any],
    recommendation_bucket: Callable[[dict[str, Any]], Any],
    class_closure_forecast_events: Callable[..., list[dict[str, Any]]],
    class_transition_events: Callable[..., list[dict[str, Any]]],
    target_class_transition_history: Callable[[dict[str, Any], list[dict[str, Any]]], dict[str, Any]],
    target_class_key: Callable[[dict[str, Any]], str],
    target_label: Callable[[dict[str, Any]], str],
    closure_forecast_reset_reentry_rebuild_side_from_event: Callable[[dict[str, Any]], str],
    closure_forecast_reset_reentry_rebuild_side_from_persistence_status: Callable[[str], str],
    closure_forecast_reset_reentry_rebuild_side_from_status: Callable[[str], str],
    closure_forecast_freshness_status: Callable[[float, float], str],
    target_specific_normalization_noise: Callable[[dict[str, Any], dict[str, Any]], bool],
    class_memory_recency_weights: tuple[float, ...],
    class_reset_reentry_rebuild_freshness_window_runs: int,
    history_window_runs: int,
) -> dict[str, Any]:
    del confidence_calibration
    if not resolution_targets:
        return {
            "primary_target_closure_forecast_reset_reentry_rebuild_freshness_status": "insufficient-data",
            "primary_target_closure_forecast_reset_reentry_rebuild_freshness_reason": "",
            "closure_forecast_reset_reentry_rebuild_freshness_summary": "No reset re-entry rebuild freshness is recorded because there is no active target.",
            "primary_target_closure_forecast_reset_reentry_rebuild_reset_status": "none",
            "primary_target_closure_forecast_reset_reentry_rebuild_reset_reason": "",
            "closure_forecast_reset_reentry_rebuild_reset_summary": "No reset re-entry rebuild reset is recorded because there is no active target.",
            "stale_reset_reentry_rebuild_hotspots": [],
            "fresh_reset_reentry_rebuild_signal_hotspots": [],
            "closure_forecast_reset_reentry_rebuild_decay_window_runs": class_reset_reentry_rebuild_freshness_window_runs,
        }

    current_primary_target = resolution_targets[0]
    current_bucket = recommendation_bucket(current_primary_target)
    closure_forecast_events = class_closure_forecast_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )
    transition_events = class_transition_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )

    updated_targets: list[dict[str, Any]] = []
    for target in resolution_targets:
        freshness_status = "insufficient-data"
        freshness_reason = ""
        memory_weight = 0.0
        decayed_confirmation_rate = 0.0
        decayed_clearance_rate = 0.0
        signal_mix = ""
        reset_status = "none"
        reset_reason = ""
        closure_likely_outcome = str(target.get("transition_closure_likely_outcome", "none"))
        closure_hysteresis_status = str(target.get("closure_forecast_hysteresis_status", "none"))
        closure_hysteresis_reason = str(target.get("closure_forecast_hysteresis_reason", ""))
        transition_status = str(target.get("class_reweight_transition_status", "none"))
        transition_reason = str(target.get("class_reweight_transition_reason", ""))
        resolution_status = str(target.get("class_transition_resolution_status", "none"))
        resolution_reason = str(target.get("class_transition_resolution_reason", ""))
        rebuild_status = str(target.get("closure_forecast_reset_reentry_rebuild_status", "none"))
        rebuild_reason = str(target.get("closure_forecast_reset_reentry_rebuild_reason", ""))
        persistence_age_runs = int(target.get("closure_forecast_reset_reentry_rebuild_age_runs", 0) or 0)
        persistence_score = float(
            target.get("closure_forecast_reset_reentry_rebuild_persistence_score", 0.0) or 0.0
        )
        persistence_status = str(
            target.get("closure_forecast_reset_reentry_rebuild_persistence_status", "none")
        )
        persistence_reason = str(
            target.get("closure_forecast_reset_reentry_rebuild_persistence_reason", "")
        )

        if recommendation_bucket(target) == current_bucket:
            transition_history_meta = target_class_transition_history(target, transition_events)
            freshness_meta = closure_forecast_reset_reentry_rebuild_freshness_for_target(
                target,
                closure_forecast_events,
                target_class_key=target_class_key,
                closure_forecast_reset_reentry_rebuild_side_from_event=(
                    closure_forecast_reset_reentry_rebuild_side_from_event
                ),
                closure_forecast_reset_reentry_rebuild_side_from_persistence_status=(
                    closure_forecast_reset_reentry_rebuild_side_from_persistence_status
                ),
                closure_forecast_reset_reentry_rebuild_side_from_status=(
                    closure_forecast_reset_reentry_rebuild_side_from_status
                ),
                closure_forecast_freshness_status=closure_forecast_freshness_status,
                class_memory_recency_weights=class_memory_recency_weights,
                class_reset_reentry_rebuild_freshness_window_runs=(
                    class_reset_reentry_rebuild_freshness_window_runs
                ),
                history_window_runs=history_window_runs,
            )
            freshness_status = str(
                freshness_meta["closure_forecast_reset_reentry_rebuild_freshness_status"]
            )
            freshness_reason = str(
                freshness_meta["closure_forecast_reset_reentry_rebuild_freshness_reason"]
            )
            memory_weight = float(
                freshness_meta["closure_forecast_reset_reentry_rebuild_memory_weight"]
            )
            decayed_confirmation_rate = float(
                freshness_meta["decayed_rebuilt_confirmation_reentry_rate"]
            )
            decayed_clearance_rate = float(
                freshness_meta["decayed_rebuilt_clearance_reentry_rate"]
            )
            signal_mix = str(freshness_meta["recent_reset_reentry_rebuild_signal_mix"])
            control_updates = apply_reset_reentry_rebuild_freshness_reset_control(
                target,
                freshness_meta=freshness_meta,
                transition_history_meta=transition_history_meta,
                closure_likely_outcome=closure_likely_outcome,
                closure_hysteresis_status=closure_hysteresis_status,
                closure_hysteresis_reason=closure_hysteresis_reason,
                transition_status=transition_status,
                transition_reason=transition_reason,
                resolution_status=resolution_status,
                resolution_reason=resolution_reason,
                rebuild_status=rebuild_status,
                rebuild_reason=rebuild_reason,
                persistence_age_runs=persistence_age_runs,
                persistence_score=persistence_score,
                persistence_status=persistence_status,
                persistence_reason=persistence_reason,
                closure_forecast_reset_reentry_rebuild_side_from_persistence_status=(
                    closure_forecast_reset_reentry_rebuild_side_from_persistence_status
                ),
                closure_forecast_reset_reentry_rebuild_side_from_status=(
                    closure_forecast_reset_reentry_rebuild_side_from_status
                ),
                target_specific_normalization_noise=target_specific_normalization_noise,
            )
            reset_status = str(control_updates["closure_forecast_reset_reentry_rebuild_reset_status"])
            reset_reason = str(control_updates["closure_forecast_reset_reentry_rebuild_reset_reason"])
            closure_likely_outcome = str(control_updates["transition_closure_likely_outcome"])
            closure_hysteresis_status = str(control_updates["closure_forecast_hysteresis_status"])
            closure_hysteresis_reason = str(control_updates["closure_forecast_hysteresis_reason"])
            transition_status = str(control_updates["class_reweight_transition_status"])
            transition_reason = str(control_updates["class_reweight_transition_reason"])
            resolution_status = str(control_updates["class_transition_resolution_status"])
            resolution_reason = str(control_updates["class_transition_resolution_reason"])
            rebuild_status = str(control_updates["closure_forecast_reset_reentry_rebuild_status"])
            rebuild_reason = str(control_updates["closure_forecast_reset_reentry_rebuild_reason"])
            persistence_age_runs = int(
                control_updates["closure_forecast_reset_reentry_rebuild_age_runs"]
            )
            persistence_score = float(
                control_updates["closure_forecast_reset_reentry_rebuild_persistence_score"]
            )
            persistence_status = str(
                control_updates["closure_forecast_reset_reentry_rebuild_persistence_status"]
            )
            persistence_reason = str(
                control_updates["closure_forecast_reset_reentry_rebuild_persistence_reason"]
            )

        updated_targets.append(
            {
                **target,
                "closure_forecast_reset_reentry_rebuild_freshness_status": freshness_status,
                "closure_forecast_reset_reentry_rebuild_freshness_reason": freshness_reason,
                "closure_forecast_reset_reentry_rebuild_memory_weight": memory_weight,
                "decayed_rebuilt_confirmation_reentry_rate": decayed_confirmation_rate,
                "decayed_rebuilt_clearance_reentry_rate": decayed_clearance_rate,
                "recent_reset_reentry_rebuild_signal_mix": signal_mix,
                "closure_forecast_reset_reentry_rebuild_reset_status": reset_status,
                "closure_forecast_reset_reentry_rebuild_reset_reason": reset_reason,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reset_reentry_rebuild_status": rebuild_status,
                "closure_forecast_reset_reentry_rebuild_reason": rebuild_reason,
                "closure_forecast_reset_reentry_rebuild_age_runs": persistence_age_runs,
                "closure_forecast_reset_reentry_rebuild_persistence_score": persistence_score,
                "closure_forecast_reset_reentry_rebuild_persistence_status": persistence_status,
                "closure_forecast_reset_reentry_rebuild_persistence_reason": persistence_reason,
            }
        )

    resolution_targets[:] = updated_targets
    primary_target = resolution_targets[0]
    stale_reset_reentry_rebuild_hotspots = closure_forecast_reset_reentry_rebuild_freshness_hotspots(
        resolution_targets,
        mode="stale",
        target_class_key=target_class_key,
    )
    fresh_reset_reentry_rebuild_signal_hotspots = (
        closure_forecast_reset_reentry_rebuild_freshness_hotspots(
            resolution_targets,
            mode="fresh",
            target_class_key=target_class_key,
        )
    )
    return {
        "primary_target_closure_forecast_reset_reentry_rebuild_freshness_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_freshness_status",
            "insufficient-data",
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_freshness_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_freshness_reason",
            "",
        ),
        "closure_forecast_reset_reentry_rebuild_freshness_summary": (
            closure_forecast_reset_reentry_rebuild_freshness_summary(
                primary_target,
                stale_reset_reentry_rebuild_hotspots,
                fresh_reset_reentry_rebuild_signal_hotspots,
                target_label=target_label,
            )
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_reset_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reset_status",
            "none",
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_reset_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reset_reason",
            "",
        ),
        "closure_forecast_reset_reentry_rebuild_reset_summary": (
            closure_forecast_reset_reentry_rebuild_reset_summary(
                primary_target,
                stale_reset_reentry_rebuild_hotspots,
                fresh_reset_reentry_rebuild_signal_hotspots,
                target_label=target_label,
            )
        ),
        "stale_reset_reentry_rebuild_hotspots": stale_reset_reentry_rebuild_hotspots,
        "fresh_reset_reentry_rebuild_signal_hotspots": fresh_reset_reentry_rebuild_signal_hotspots,
        "closure_forecast_reset_reentry_rebuild_decay_window_runs": class_reset_reentry_rebuild_freshness_window_runs,
    }


def closure_forecast_reset_reentry_rebuild_persistence_for_target(
    target: dict[str, Any],
    closure_forecast_events: list[dict[str, Any]],
    transition_history_meta: dict[str, Any],
    *,
    ordered_reset_reentry_events_for_target: Callable[
        [dict[str, Any], list[dict[str, Any]]], list[dict[str, Any]]
    ],
    closure_forecast_reset_reentry_rebuild_side_from_event: Callable[[dict[str, Any]], str],
    closure_forecast_direction_majority: Callable[[list[str]], str],
    closure_forecast_direction_reversing: Callable[[str, str], bool],
    clamp_round: Callable[..., float],
    closure_forecast_reset_reentry_rebuild_path_label: Callable[[dict[str, Any]], str],
    class_reset_reentry_rebuild_persistence_window_runs: int,
) -> dict[str, Any]:
    matching_events = ordered_reset_reentry_events_for_target(
        target,
        closure_forecast_events,
    )[:class_reset_reentry_rebuild_persistence_window_runs]
    relevant_events = [
        event
        for event in matching_events
        if closure_forecast_reset_reentry_rebuild_side_from_event(event) != "none"
    ]
    current_side = (
        closure_forecast_reset_reentry_rebuild_side_from_event(matching_events[0])
        if matching_events
        else "none"
    )
    persistence_age_runs = 0
    for event in matching_events:
        event_side = closure_forecast_reset_reentry_rebuild_side_from_event(event)
        if event_side != current_side or event_side == "none":
            break
        persistence_age_runs += 1

    weighted_total = 0.0
    weight_sum = 0.0
    directions: list[str] = []
    for index, event in enumerate(relevant_events[:class_reset_reentry_rebuild_persistence_window_runs]):
        weight = (1.0, 0.8, 0.6, 0.4)[
            min(index, class_reset_reentry_rebuild_persistence_window_runs - 1)
        ]
        event_side = closure_forecast_reset_reentry_rebuild_side_from_event(event)
        sign = 1.0 if event_side == "confirmation" else -1.0
        directions.append("supporting-confirmation" if sign > 0 else "supporting-clearance")
        magnitude = 0.0
        if event.get("closure_forecast_reset_reentry_rebuild_status", "none") in {
            "rebuilt-confirmation-reentry",
            "rebuilt-clearance-reentry",
        }:
            magnitude += 0.15
        if event.get("closure_forecast_reset_reentry_refresh_recovery_status", "none") in {
            "rebuilding-confirmation-reentry",
            "rebuilding-clearance-reentry",
        }:
            magnitude += 0.10
        momentum_status = event.get("closure_forecast_momentum_status", "insufficient-data")
        if (event_side == "confirmation" and momentum_status == "sustained-confirmation") or (
            event_side == "clearance" and momentum_status == "sustained-clearance"
        ):
            magnitude += 0.10
        stability_status = event.get("closure_forecast_stability_status", "watch")
        if stability_status == "stable":
            magnitude += 0.10
        freshness_status = event.get(
            "closure_forecast_reset_reentry_freshness_status",
            "insufficient-data",
        )
        if freshness_status == "fresh":
            magnitude += 0.10
        elif freshness_status == "mixed-age":
            magnitude = max(0.0, magnitude - 0.10)
        if momentum_status in {"reversing", "unstable"}:
            magnitude = max(0.0, magnitude - 0.15)
        if stability_status == "oscillating":
            magnitude = max(0.0, magnitude - 0.15)
        if event.get("closure_forecast_reset_reentry_reset_status", "none") != "none":
            magnitude = max(0.0, magnitude - 0.15)
        weighted_total += sign * magnitude * weight
        weight_sum += weight

    persistence_score = clamp_round(
        weighted_total / max(weight_sum, 1.0),
        lower=-0.95,
        upper=0.95,
    )
    current_momentum_status = target.get(
        "closure_forecast_momentum_status",
        "insufficient-data",
    )
    current_stability_status = target.get("closure_forecast_stability_status", "watch")
    current_freshness_status = target.get(
        "closure_forecast_reset_reentry_freshness_status",
        "insufficient-data",
    )
    earlier_majority = closure_forecast_direction_majority(directions[1:])
    current_direction = (
        "supporting-confirmation"
        if current_side == "confirmation"
        else "supporting-clearance"
        if current_side == "clearance"
        else "neutral"
    )

    if current_side == "none" and not relevant_events:
        persistence_status = "none"
    elif (
        target.get("closure_forecast_reset_reentry_rebuild_status", "none")
        in {"rebuilt-confirmation-reentry", "rebuilt-clearance-reentry"}
        and persistence_age_runs == 1
    ):
        persistence_status = "just-rebuilt"
    elif len(relevant_events) < 2:
        persistence_status = "insufficient-data"
    elif (
        closure_forecast_direction_reversing(current_direction, earlier_majority)
        or current_momentum_status in {"reversing", "unstable"}
        or target.get("closure_forecast_reset_reentry_reset_status", "none") != "none"
    ):
        persistence_status = "reversing"
    elif (
        current_side == "confirmation"
        and persistence_age_runs >= 3
        and current_freshness_status == "fresh"
        and current_momentum_status == "sustained-confirmation"
        and current_stability_status != "oscillating"
    ):
        persistence_status = "sustained-confirmation-rebuild"
    elif (
        current_side == "clearance"
        and persistence_age_runs >= 3
        and current_freshness_status == "fresh"
        and current_momentum_status == "sustained-clearance"
        and current_stability_status != "oscillating"
    ):
        persistence_status = "sustained-clearance-rebuild"
    elif current_side == "confirmation" and persistence_age_runs >= 2 and persistence_score > 0:
        persistence_status = "holding-confirmation-rebuild"
    elif current_side == "clearance" and persistence_age_runs >= 2 and persistence_score < 0:
        persistence_status = "holding-clearance-rebuild"
    else:
        persistence_status = "none"

    if persistence_status == "just-rebuilt":
        persistence_reason = (
            "Stronger reset re-entry posture has been rebuilt, but it has not yet proved it can hold."
        )
    elif persistence_status == "holding-confirmation-rebuild":
        persistence_reason = (
            "Confirmation-side rebuild has stayed aligned long enough to keep the restored forecast in place."
        )
    elif persistence_status == "holding-clearance-rebuild":
        persistence_reason = (
            "Clearance-side rebuild has stayed aligned long enough to keep the restored caution in place."
        )
    elif persistence_status == "sustained-confirmation-rebuild":
        persistence_reason = (
            "Confirmation-side rebuild is now holding with enough follow-through to trust the restored forecast more."
        )
    elif persistence_status == "sustained-clearance-rebuild":
        persistence_reason = (
            "Clearance-side rebuild is now holding with enough follow-through to trust the restored caution more."
        )
    elif persistence_status == "reversing":
        persistence_reason = (
            "The rebuilt posture is already weakening, so it is being softened again."
        )
    elif persistence_status == "insufficient-data":
        persistence_reason = (
            "Rebuilt reset re-entry is still too lightly exercised to say whether the restored forecast can hold."
        )
    else:
        persistence_reason = ""

    return {
        "closure_forecast_reset_reentry_rebuild_age_runs": persistence_age_runs,
        "closure_forecast_reset_reentry_rebuild_persistence_score": persistence_score,
        "closure_forecast_reset_reentry_rebuild_persistence_status": persistence_status,
        "closure_forecast_reset_reentry_rebuild_persistence_reason": persistence_reason,
        "recent_reset_reentry_rebuild_persistence_path": " -> ".join(
            closure_forecast_reset_reentry_rebuild_path_label(event)
            for event in matching_events
            if event
        ),
    }


def closure_forecast_reset_reentry_rebuild_churn_for_target(
    target: dict[str, Any],
    closure_forecast_events: list[dict[str, Any]],
    transition_history_meta: dict[str, Any],
    *,
    ordered_reset_reentry_events_for_target: Callable[
        [dict[str, Any], list[dict[str, Any]]], list[dict[str, Any]]
    ],
    closure_forecast_reset_reentry_rebuild_side_from_event: Callable[[dict[str, Any]], str],
    class_direction_flip_count: Callable[[list[str]], int],
    target_specific_normalization_noise: Callable[[dict[str, Any], dict[str, Any]], bool],
    clamp_round: Callable[..., float],
    closure_forecast_reset_reentry_rebuild_path_label: Callable[[dict[str, Any]], str],
    class_reset_reentry_rebuild_persistence_window_runs: int,
) -> dict[str, Any]:
    matching_events = ordered_reset_reentry_events_for_target(
        target,
        closure_forecast_events,
    )[:class_reset_reentry_rebuild_persistence_window_runs]
    relevant_events = [
        event
        for event in matching_events
        if closure_forecast_reset_reentry_rebuild_side_from_event(event) != "none"
    ]
    side_path = [
        closure_forecast_reset_reentry_rebuild_side_from_event(event) for event in relevant_events
    ]
    current_side = side_path[0] if side_path else "none"
    local_noise = target_specific_normalization_noise(target, transition_history_meta)
    if current_side == "none":
        churn_score = 0.0
        churn_status = "none"
        churn_reason = ""
    else:
        flip_count = class_direction_flip_count(
            [
                "supporting-confirmation" if side == "confirmation" else "supporting-clearance"
                for side in side_path
            ]
        )
        churn_score = float(flip_count) * 0.20
        stability_status = target.get("closure_forecast_stability_status", "watch")
        momentum_status = target.get("closure_forecast_momentum_status", "insufficient-data")
        if stability_status == "oscillating":
            churn_score += 0.15
        if momentum_status == "reversing":
            churn_score += 0.10
        if momentum_status == "unstable":
            churn_score += 0.10
        freshness_path = [
            event.get(
                "closure_forecast_reset_reentry_freshness_status",
                "insufficient-data",
            )
            for event in relevant_events
        ]
        if any(
            previous == "fresh" and current in {"mixed-age", "stale", "insufficient-data"}
            for previous, current in zip(freshness_path, freshness_path[1:])
        ):
            churn_score += 0.10
        if any(
            event.get("closure_forecast_reset_reentry_reset_status", "none") != "none"
            for event in relevant_events
        ):
            churn_score += 0.10
        if (
            len(relevant_events) >= 2
            and side_path[0] == side_path[1]
            and relevant_events[0].get(
                "closure_forecast_reset_reentry_freshness_status",
                "insufficient-data",
            )
            == "fresh"
            and relevant_events[1].get(
                "closure_forecast_reset_reentry_freshness_status",
                "insufficient-data",
            )
            == "fresh"
        ):
            churn_score -= 0.10
        churn_score = clamp_round(churn_score, lower=0.0, upper=0.95)
        if local_noise and current_side == "confirmation":
            churn_status = "blocked"
            churn_reason = (
                "Local target instability is preventing positive confirmation-side rebuild persistence."
            )
        elif churn_score >= 0.45 or flip_count >= 2:
            churn_status = "churn"
            churn_reason = (
                "Rebuilt reset re-entry is flipping enough that restored posture should be softened quickly."
            )
        elif churn_score >= 0.20:
            churn_status = "watch"
            churn_reason = (
                "Rebuilt reset re-entry is wobbling and may lose its restored strength soon."
            )
        else:
            churn_status = "none"
            churn_reason = ""

    return {
        "closure_forecast_reset_reentry_rebuild_churn_score": churn_score,
        "closure_forecast_reset_reentry_rebuild_churn_status": churn_status,
        "closure_forecast_reset_reentry_rebuild_churn_reason": churn_reason,
        "recent_reset_reentry_rebuild_churn_path": " -> ".join(
            closure_forecast_reset_reentry_rebuild_path_label(event)
            for event in matching_events
            if event
        ),
    }


def apply_reset_reentry_rebuild_persistence_and_churn_control(
    target: dict[str, Any],
    *,
    persistence_meta: dict[str, Any],
    churn_meta: dict[str, Any],
    transition_history_meta: dict[str, Any],
    closure_likely_outcome: str,
    closure_hysteresis_status: str,
    closure_hysteresis_reason: str,
    transition_status: str,
    transition_reason: str,
    resolution_status: str,
    resolution_reason: str,
    closure_forecast_reset_reentry_rebuild_side_from_status: Callable[[str], str],
    closure_forecast_reset_reentry_rebuild_side_from_recovery_status: Callable[[str], str],
) -> dict[str, Any]:
    persistence_status = str(
        persistence_meta.get("closure_forecast_reset_reentry_rebuild_persistence_status", "none")
    )
    persistence_reason = str(
        persistence_meta.get("closure_forecast_reset_reentry_rebuild_persistence_reason", "")
    )
    churn_status = str(churn_meta.get("closure_forecast_reset_reentry_rebuild_churn_status", "none"))
    churn_reason = str(churn_meta.get("closure_forecast_reset_reentry_rebuild_churn_reason", ""))
    current_rebuild_status = str(target.get("closure_forecast_reset_reentry_rebuild_status", "none"))
    current_freshness_status = str(
        target.get("closure_forecast_reset_reentry_freshness_status", "insufficient-data")
    )
    transition_age_runs = int(target.get("class_transition_age_runs", 0) or 0)
    recent_pending_status = str(transition_history_meta.get("recent_pending_status", "none"))
    current_side = closure_forecast_reset_reentry_rebuild_side_from_status(current_rebuild_status)
    if current_side == "none":
        current_side = closure_forecast_reset_reentry_rebuild_side_from_recovery_status(
            str(target.get("closure_forecast_reset_reentry_refresh_recovery_status", "none"))
        )
    if (
        current_side == "none"
        and persistence_status in {"none", "insufficient-data"}
        and churn_status == "none"
    ):
        return {
            "transition_closure_likely_outcome": closure_likely_outcome,
            "closure_forecast_hysteresis_status": closure_hysteresis_status,
            "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
        }

    if churn_status == "blocked" and current_side == "confirmation":
        if closure_likely_outcome == "confirm-soon":
            closure_likely_outcome = "hold"
        if closure_hysteresis_status == "confirmed-confirmation":
            closure_hysteresis_status = "pending-confirmation"
        closure_hysteresis_reason = churn_reason or persistence_reason or closure_hysteresis_reason
        return {
            "transition_closure_likely_outcome": closure_likely_outcome,
            "closure_forecast_hysteresis_status": closure_hysteresis_status,
            "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
        }

    if current_rebuild_status == "rebuilt-confirmation-reentry":
        if (
            persistence_status
            in {"holding-confirmation-rebuild", "sustained-confirmation-rebuild"}
            and churn_status != "churn"
        ):
            return {
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
            }
        if (
            persistence_status == "reversing"
            or churn_status == "churn"
            or (
                current_freshness_status in {"stale", "insufficient-data"}
                and persistence_status != "just-rebuilt"
            )
        ):
            closure_likely_outcome = "hold"
            if closure_hysteresis_status == "confirmed-confirmation":
                closure_hysteresis_status = "pending-confirmation"
            closure_hysteresis_reason = churn_reason or persistence_reason or closure_hysteresis_reason

    if current_rebuild_status == "rebuilt-clearance-reentry":
        if (
            persistence_status in {"holding-clearance-rebuild", "sustained-clearance-rebuild"}
            and churn_status != "churn"
        ):
            if closure_likely_outcome == "expire-risk" and transition_age_runs < 3:
                closure_likely_outcome = "clear-risk"
            return {
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
            }
        if (
            persistence_status in {"reversing", "none", "insufficient-data"}
            or churn_status == "churn"
            or (
                current_freshness_status in {"stale", "insufficient-data"}
                and persistence_status != "just-rebuilt"
            )
        ):
            if closure_likely_outcome == "expire-risk":
                closure_likely_outcome = "clear-risk"
            elif closure_likely_outcome == "clear-risk":
                closure_likely_outcome = "hold"
            if closure_hysteresis_status == "confirmed-clearance":
                closure_hysteresis_status = "pending-clearance"
            closure_hysteresis_reason = churn_reason or persistence_reason or closure_hysteresis_reason
        if (
            resolution_status == "cleared"
            and recent_pending_status in {"pending-support", "pending-caution"}
            and (
                persistence_status not in {"holding-clearance-rebuild", "sustained-clearance-rebuild"}
                or churn_status == "churn"
            )
        ):
            restore_reason = (
                churn_reason
                or persistence_reason
                or "Clearance-side rebuild stopped holding cleanly, so the earlier-clear posture has been withdrawn."
            )
            transition_status = recent_pending_status
            transition_reason = restore_reason
            resolution_status = "none"
            resolution_reason = ""

    return {
        "transition_closure_likely_outcome": closure_likely_outcome,
        "closure_forecast_hysteresis_status": closure_hysteresis_status,
        "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
        "class_reweight_transition_status": transition_status,
        "class_reweight_transition_reason": transition_reason,
        "class_transition_resolution_status": resolution_status,
        "class_transition_resolution_reason": resolution_reason,
    }


def closure_forecast_reset_reentry_rebuild_hotspots(
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
            "closure_forecast_reset_reentry_rebuild_age_runs": target.get(
                "closure_forecast_reset_reentry_rebuild_age_runs",
                0,
            ),
            "closure_forecast_reset_reentry_rebuild_persistence_score": target.get(
                "closure_forecast_reset_reentry_rebuild_persistence_score",
                0.0,
            ),
            "closure_forecast_reset_reentry_rebuild_persistence_status": target.get(
                "closure_forecast_reset_reentry_rebuild_persistence_status",
                "none",
            ),
            "closure_forecast_reset_reentry_rebuild_churn_score": target.get(
                "closure_forecast_reset_reentry_rebuild_churn_score",
                0.0,
            ),
            "closure_forecast_reset_reentry_rebuild_churn_status": target.get(
                "closure_forecast_reset_reentry_rebuild_churn_status",
                "none",
            ),
            "recent_reset_reentry_rebuild_persistence_path": target.get(
                "recent_reset_reentry_rebuild_persistence_path",
                "",
            ),
            "recent_reset_reentry_rebuild_churn_path": target.get(
                "recent_reset_reentry_rebuild_churn_path",
                "",
            ),
        }
        existing = grouped.get(class_key)
        if existing is None or abs(
            float(current["closure_forecast_reset_reentry_rebuild_persistence_score"] or 0.0)
        ) > abs(float(existing["closure_forecast_reset_reentry_rebuild_persistence_score"] or 0.0)):
            grouped[class_key] = current
    hotspots = list(grouped.values())
    if mode == "just-rebuilt":
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reset_reentry_rebuild_persistence_status")
            == "just-rebuilt"
        ]
        hotspots.sort(
            key=lambda item: (
                -int(item.get("closure_forecast_reset_reentry_rebuild_age_runs", 0) or 0),
                -abs(float(item.get("closure_forecast_reset_reentry_rebuild_persistence_score", 0.0) or 0.0)),
                str(item.get("label", "")),
            )
        )
    elif mode == "holding":
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reset_reentry_rebuild_persistence_status")
            in {
                "holding-confirmation-rebuild",
                "holding-clearance-rebuild",
                "sustained-confirmation-rebuild",
                "sustained-clearance-rebuild",
            }
        ]
        hotspots.sort(
            key=lambda item: (
                -int(item.get("closure_forecast_reset_reentry_rebuild_age_runs", 0) or 0),
                -abs(float(item.get("closure_forecast_reset_reentry_rebuild_persistence_score", 0.0) or 0.0)),
                str(item.get("label", "")),
            )
        )
    else:
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reset_reentry_rebuild_churn_status")
            in {"watch", "churn", "blocked"}
        ]
        hotspots.sort(
            key=lambda item: (
                -float(item.get("closure_forecast_reset_reentry_rebuild_churn_score", 0.0) or 0.0),
                -int(item.get("closure_forecast_reset_reentry_rebuild_age_runs", 0) or 0),
                str(item.get("label", "")),
            )
        )
    return hotspots[:5]


def closure_forecast_reset_reentry_rebuild_persistence_summary(
    primary_target: dict[str, Any],
    just_rebuilt_hotspots: list[dict[str, Any]],
    holding_reset_reentry_rebuild_hotspots: list[dict[str, Any]],
    *,
    target_label: Callable[[dict[str, Any]], str],
) -> str:
    label = target_label(primary_target) or "The current target"
    status = str(
        primary_target.get("closure_forecast_reset_reentry_rebuild_persistence_status", "none")
    )
    age_runs = int(primary_target.get("closure_forecast_reset_reentry_rebuild_age_runs", 0) or 0)
    score = float(primary_target.get("closure_forecast_reset_reentry_rebuild_persistence_score", 0.0) or 0.0)
    if status == "just-rebuilt":
        return (
            f"{label} has only just rebuilt stronger reset re-entry posture, so it is still fragile "
            f"({score:.2f}; {age_runs} run)."
        )
    if status == "holding-confirmation-rebuild":
        return (
            f"Confirmation-side rebuild for {label} has held long enough to keep the restored forecast in place "
            f"({score:.2f}; {age_runs} runs)."
        )
    if status == "holding-clearance-rebuild":
        return (
            f"Clearance-side rebuild for {label} has held long enough to keep the restored caution in place "
            f"({score:.2f}; {age_runs} runs)."
        )
    if status == "sustained-confirmation-rebuild":
        return (
            f"Confirmation-side rebuild for {label} is now holding with enough follow-through to trust the restored forecast more "
            f"({score:.2f}; {age_runs} runs)."
        )
    if status == "sustained-clearance-rebuild":
        return (
            f"Clearance-side rebuild for {label} is now holding with enough follow-through to trust the restored caution more "
            f"({score:.2f}; {age_runs} runs)."
        )
    if status == "reversing":
        return (
            f"The rebuilt reset re-entry posture for {label} is already weakening, so it is being softened again "
            f"({score:.2f})."
        )
    if status == "insufficient-data":
        return (
            f"Rebuilt reset re-entry for {label} is still too lightly exercised to say whether the restored forecast can hold."
        )
    if just_rebuilt_hotspots:
        hotspot = just_rebuilt_hotspots[0]
        return (
            f"Newly rebuilt reset re-entry posture is most fragile around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes still need follow-through before the restored forecast can be trusted."
        )
    if holding_reset_reentry_rebuild_hotspots:
        hotspot = holding_reset_reentry_rebuild_hotspots[0]
        return (
            f"Rebuilt reset re-entry posture is holding most cleanly around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes are closest to keeping restored rebuild strength safely."
        )
    return "No rebuilt reset re-entry posture is active enough yet to judge whether it can hold."


def closure_forecast_reset_reentry_rebuild_churn_summary(
    primary_target: dict[str, Any],
    reset_reentry_rebuild_churn_hotspots: list[dict[str, Any]],
    *,
    target_label: Callable[[dict[str, Any]], str],
) -> str:
    label = target_label(primary_target) or "The current target"
    status = str(primary_target.get("closure_forecast_reset_reentry_rebuild_churn_status", "none"))
    score = float(primary_target.get("closure_forecast_reset_reentry_rebuild_churn_score", 0.0) or 0.0)
    if status == "watch":
        return (
            f"Rebuilt reset re-entry for {label} is wobbling enough that restored forecast strength may soften soon "
            f"({score:.2f})."
        )
    if status == "churn":
        return (
            f"Rebuilt reset re-entry for {label} is flipping enough that restored posture should be softened quickly "
            f"({score:.2f})."
        )
    if status == "blocked":
        return str(
            primary_target.get(
                "closure_forecast_reset_reentry_rebuild_churn_reason",
                f"Local target instability is preventing positive confirmation-side rebuild persistence for {label}.",
            )
        )
    if reset_reentry_rebuild_churn_hotspots:
        hotspot = reset_reentry_rebuild_churn_hotspots[0]
        return (
            f"Rebuild churn is highest around {hotspot.get('label', 'recent hotspots')}, "
            "so restored posture there should soften quickly if the wobble continues."
        )
    return "No meaningful reset re-entry rebuild churn is active right now."


def closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_for_target(
    target: dict[str, Any],
    closure_forecast_events: list[dict[str, Any]],
    transition_history_meta: dict[str, Any],
    *,
    ordered_reset_reentry_events_for_target: Callable[
        [dict[str, Any], list[dict[str, Any]]], list[dict[str, Any]]
    ],
    closure_forecast_reset_side_from_status: Callable[[str], str],
    normalized_closure_forecast_direction: Callable[[str, float], str],
    clamp_round: Callable[..., float],
    closure_forecast_direction_majority: Callable[[list[str]], str],
    target_specific_normalization_noise: Callable[[dict[str, Any], dict[str, Any]], bool],
    closure_forecast_direction_reversing: Callable[[str, str], bool],
    closure_forecast_reset_reentry_rebuild_reentry_refresh_path_label: Callable[
        [dict[str, Any]], str
    ],
    class_reset_reentry_rebuild_reentry_refresh_restore_window_runs: int,
) -> dict[str, Any]:
    matching_events = ordered_reset_reentry_events_for_target(
        target,
        closure_forecast_events,
    )[:class_reset_reentry_rebuild_reentry_refresh_restore_window_runs]
    recent_rebuild_reentry_reset_side = "none"
    latest_reset_index: int | None = None
    for index, event in enumerate(matching_events):
        event_reset_side = closure_forecast_reset_side_from_status(
            str(event.get("closure_forecast_reset_reentry_rebuild_reentry_reset_status", "none"))
        )
        if event_reset_side != "none":
            recent_rebuild_reentry_reset_side = event_reset_side
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
                str(event.get("closure_forecast_reset_reentry_rebuild_reentry_reset_status", "none"))
            )
            == "none"
            and direction == "neutral"
            and abs(score) < 0.05
        ):
            continue
        relevant_events.append(event)
        directions.append(direction)
        if len(relevant_events) > class_reset_reentry_rebuild_reentry_refresh_restore_window_runs:
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
            str(
                event.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_freshness_status",
                    "insufficient-data",
                )
            ),
            0.10,
        )
        weight = (1.0, 0.8, 0.6, 0.4)[
            min(
                len(relevant_events) - 1,
                class_reset_reentry_rebuild_reentry_refresh_restore_window_runs - 1,
            )
        ]
        weighted_total += sign * signal_strength * freshness_factor * weight
        weight_sum += weight

    recovery_score = clamp_round(weighted_total / max(weight_sum, 1.0), lower=-0.95, upper=0.95)
    current_score = float(target.get("closure_forecast_reweight_score", 0.0) or 0.0)
    current_direction = normalized_closure_forecast_direction(
        str(target.get("closure_forecast_reweight_direction", "neutral")),
        current_score,
    )
    current_freshness = str(
        target.get("closure_forecast_reset_reentry_rebuild_reentry_freshness_status", "insufficient-data")
    )
    current_momentum = str(target.get("closure_forecast_momentum_status", "insufficient-data"))
    current_stability = str(target.get("closure_forecast_stability_status", "watch"))
    earlier_majority = closure_forecast_direction_majority(directions[1:])
    local_noise = target_specific_normalization_noise(target, transition_history_meta)
    direction_reversing = closure_forecast_direction_reversing(current_direction, earlier_majority)
    opposes_reset = (
        recent_rebuild_reentry_reset_side == "confirmation"
        and current_direction == "supporting-clearance"
    ) or (
        recent_rebuild_reentry_reset_side == "clearance"
        and current_direction == "supporting-confirmation"
    )
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
                event_side == recent_rebuild_reentry_reset_side
                and event.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_freshness_status",
                    "insufficient-data",
                )
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
    if (
        current_side == recent_rebuild_reentry_reset_side
        and current_freshness == "fresh"
        and not current_event_already_counted
    ):
        aligned_fresh_runs_after_reset += 1

    if len(relevant_events) < 2 or recent_rebuild_reentry_reset_side == "none":
        recovery_status = "none"
    elif local_noise and current_direction == "supporting-confirmation":
        recovery_status = "blocked"
    elif opposes_reset or direction_reversing:
        recovery_status = "reversing"
    elif (
        recent_rebuild_reentry_reset_side == "confirmation"
        and current_direction == "supporting-confirmation"
        and current_freshness == "fresh"
        and recovery_score >= 0.25
        and current_stability != "oscillating"
    ):
        recovery_status = "restoring-confirmation-rebuild-reentry"
    elif (
        recent_rebuild_reentry_reset_side == "clearance"
        and current_direction == "supporting-clearance"
        and current_freshness == "fresh"
        and recovery_score <= -0.25
        and current_stability != "oscillating"
    ):
        recovery_status = "restoring-clearance-rebuild-reentry"
    elif (
        recent_rebuild_reentry_reset_side == "confirmation"
        and current_direction == "supporting-confirmation"
        and current_freshness in {"fresh", "mixed-age"}
        and recovery_score >= 0.15
    ):
        recovery_status = "recovering-confirmation-rebuild-reentry-reset"
    elif (
        recent_rebuild_reentry_reset_side == "clearance"
        and current_direction == "supporting-clearance"
        and current_freshness in {"fresh", "mixed-age"}
        and recovery_score <= -0.15
    ):
        recovery_status = "recovering-clearance-rebuild-reentry-reset"
    else:
        recovery_status = "none"

    if (
        recovery_status == "restoring-confirmation-rebuild-reentry"
        and current_freshness == "fresh"
        and current_momentum == "sustained-confirmation"
        and current_stability == "stable"
        and not local_noise
        and aligned_fresh_runs_after_reset >= 2
    ):
        restore_status = "restored-confirmation-rebuild-reentry"
        restore_reason = "Fresh confirmation-side follow-through has restored stronger rebuilt re-entry posture."
    elif (
        recovery_status == "restoring-clearance-rebuild-reentry"
        and current_freshness == "fresh"
        and current_momentum == "sustained-clearance"
        and current_stability == "stable"
        and aligned_fresh_runs_after_reset >= 2
    ):
        restore_status = "restored-clearance-rebuild-reentry"
        restore_reason = "Fresh clearance-side pressure has restored stronger rebuilt re-entry posture."
    elif local_noise and recovery_status in {
        "recovering-confirmation-rebuild-reentry-reset",
        "restoring-confirmation-rebuild-reentry",
        "blocked",
    }:
        restore_status = "blocked"
        restore_reason = (
            "Local target instability is still preventing positive confirmation-side rebuilt re-entry restore."
        )
    elif recovery_status in {
        "recovering-confirmation-rebuild-reentry-reset",
        "restoring-confirmation-rebuild-reentry",
    }:
        restore_status = "pending-confirmation-rebuild-reentry-restore"
        restore_reason = (
            "Fresh confirmation-side evidence is returning after rebuilt re-entry was softened or "
            "reset, but it has not yet restored stronger rebuilt re-entry posture."
        )
    elif recovery_status in {
        "recovering-clearance-rebuild-reentry-reset",
        "restoring-clearance-rebuild-reentry",
    }:
        restore_status = "pending-clearance-rebuild-reentry-restore"
        restore_reason = (
            "Fresh clearance-side evidence is returning after rebuilt re-entry was softened or "
            "reset, but it has not yet restored stronger rebuilt re-entry posture."
        )
    else:
        restore_status = "none"
        restore_reason = ""

    return {
        "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_score": recovery_score,
        "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status": recovery_status,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_status": restore_status,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": restore_reason,
        "recent_reset_reentry_rebuild_reentry_refresh_path": " -> ".join(
            closure_forecast_reset_reentry_rebuild_reentry_refresh_path_label(event)
            for event in matching_events
            if event
        ),
        "recent_rebuild_reentry_reset_side": recent_rebuild_reentry_reset_side,
        "aligned_fresh_runs_after_latest_rebuild_reentry_reset": aligned_fresh_runs_after_reset,
    }


def apply_reset_reentry_rebuild_reentry_refresh_restore_control(
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
    reentry_status: str,
    reentry_reason: str,
    persistence_age_runs: int,
    persistence_score: float,
    persistence_status: str,
    persistence_reason: str,
) -> dict[str, Any]:
    recovery_status = str(
        refresh_meta.get("closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status", "none")
    )
    restore_status = str(
        refresh_meta.get("closure_forecast_reset_reentry_rebuild_reentry_restore_status", "none")
    )
    restore_reason = str(
        refresh_meta.get("closure_forecast_reset_reentry_rebuild_reentry_restore_reason", "")
    )
    recent_rebuild_reentry_reset_side = str(
        refresh_meta.get("recent_rebuild_reentry_reset_side", "none")
    )
    current_freshness = str(
        target.get("closure_forecast_reset_reentry_rebuild_reentry_freshness_status", "insufficient-data")
    )
    current_stability = str(target.get("closure_forecast_stability_status", "watch"))
    transition_age_runs = int(target.get("class_transition_age_runs", 0) or 0)
    recent_pending_status = str(transition_history_meta.get("recent_pending_status", "none"))
    decayed_clearance_rate = float(
        target.get("decayed_reentered_rebuild_clearance_rate", 0.0) or 0.0
    )

    if restore_status == "blocked":
        if closure_likely_outcome == "confirm-soon":
            closure_likely_outcome = "hold"
        if closure_hysteresis_status == "confirmed-confirmation":
            closure_hysteresis_status = "pending-confirmation"
        if recent_rebuild_reentry_reset_side == "confirmation":
            closure_hysteresis_reason = restore_reason
        return {
            "transition_closure_likely_outcome": closure_likely_outcome,
            "closure_forecast_hysteresis_status": closure_hysteresis_status,
            "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_status": reentry_status,
            "closure_forecast_reset_reentry_rebuild_reentry_reason": reentry_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_age_runs": persistence_age_runs,
            "closure_forecast_reset_reentry_rebuild_reentry_persistence_score": persistence_score,
            "closure_forecast_reset_reentry_rebuild_reentry_persistence_status": persistence_status,
            "closure_forecast_reset_reentry_rebuild_reentry_persistence_reason": persistence_reason,
        }

    if restore_status == "restored-confirmation-rebuild-reentry":
        return {
            "transition_closure_likely_outcome": "confirm-soon",
            "closure_forecast_hysteresis_status": "confirmed-confirmation",
            "closure_forecast_hysteresis_reason": restore_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_status": "reentered-confirmation-rebuild",
            "closure_forecast_reset_reentry_rebuild_reentry_reason": restore_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_age_runs": 0,
            "closure_forecast_reset_reentry_rebuild_reentry_persistence_score": 0.0,
            "closure_forecast_reset_reentry_rebuild_reentry_persistence_status": "none",
            "closure_forecast_reset_reentry_rebuild_reentry_persistence_reason": "",
        }

    if restore_status == "restored-clearance-rebuild-reentry":
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
            resolution_reason = restore_reason
        return {
            "transition_closure_likely_outcome": restored_outcome,
            "closure_forecast_hysteresis_status": "confirmed-clearance",
            "closure_forecast_hysteresis_reason": restore_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_status": "reentered-clearance-rebuild",
            "closure_forecast_reset_reentry_rebuild_reentry_reason": restore_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_age_runs": 0,
            "closure_forecast_reset_reentry_rebuild_reentry_persistence_score": 0.0,
            "closure_forecast_reset_reentry_rebuild_reentry_persistence_status": "none",
            "closure_forecast_reset_reentry_rebuild_reentry_persistence_reason": "",
        }

    if recent_rebuild_reentry_reset_side == "confirmation":
        if restore_status == "pending-confirmation-rebuild-reentry-restore":
            if reentry_status != "reentered-confirmation-rebuild":
                closure_likely_outcome = "hold"
                closure_hysteresis_status = "pending-confirmation"
                closure_hysteresis_reason = restore_reason
                reentry_status = "none"
                reentry_reason = ""
            return {
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_rebuild_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_age_runs": 0,
                "closure_forecast_reset_reentry_rebuild_reentry_persistence_score": 0.0,
                "closure_forecast_reset_reentry_rebuild_reentry_persistence_status": "none",
                "closure_forecast_reset_reentry_rebuild_reentry_persistence_reason": "",
            }
        if recovery_status == "reversing" or current_freshness in {"stale", "insufficient-data"}:
            return {
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_rebuild_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_age_runs": persistence_age_runs,
                "closure_forecast_reset_reentry_rebuild_reentry_persistence_score": persistence_score,
                "closure_forecast_reset_reentry_rebuild_reentry_persistence_status": persistence_status,
                "closure_forecast_reset_reentry_rebuild_reentry_persistence_reason": persistence_reason,
            }

    if recent_rebuild_reentry_reset_side == "clearance":
        if restore_status == "pending-clearance-rebuild-reentry-restore":
            weaker_outcome = closure_likely_outcome
            if weaker_outcome == "expire-risk":
                weaker_outcome = "clear-risk"
            if reentry_status != "reentered-clearance-rebuild":
                closure_likely_outcome = weaker_outcome
                closure_hysteresis_status = "pending-clearance"
                closure_hysteresis_reason = restore_reason
                reentry_status = "none"
                reentry_reason = ""
            return {
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_rebuild_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_age_runs": 0,
                "closure_forecast_reset_reentry_rebuild_reentry_persistence_score": 0.0,
                "closure_forecast_reset_reentry_rebuild_reentry_persistence_status": "none",
                "closure_forecast_reset_reentry_rebuild_reentry_persistence_reason": "",
            }
        if recovery_status == "reversing" or current_freshness in {"stale", "insufficient-data"}:
            return {
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_rebuild_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_age_runs": persistence_age_runs,
                "closure_forecast_reset_reentry_rebuild_reentry_persistence_score": persistence_score,
                "closure_forecast_reset_reentry_rebuild_reentry_persistence_status": persistence_status,
                "closure_forecast_reset_reentry_rebuild_reentry_persistence_reason": persistence_reason,
            }

    return {
        "transition_closure_likely_outcome": closure_likely_outcome,
        "closure_forecast_hysteresis_status": closure_hysteresis_status,
        "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
        "class_reweight_transition_status": transition_status,
        "class_reweight_transition_reason": transition_reason,
        "class_transition_resolution_status": resolution_status,
        "class_transition_resolution_reason": resolution_reason,
        "closure_forecast_reset_reentry_rebuild_reentry_status": reentry_status,
        "closure_forecast_reset_reentry_rebuild_reentry_reason": reentry_reason,
        "closure_forecast_reset_reentry_rebuild_reentry_age_runs": persistence_age_runs,
        "closure_forecast_reset_reentry_rebuild_reentry_persistence_score": persistence_score,
        "closure_forecast_reset_reentry_rebuild_reentry_persistence_status": persistence_status,
        "closure_forecast_reset_reentry_rebuild_reentry_persistence_reason": persistence_reason,
    }


def closure_forecast_reset_reentry_rebuild_reentry_refresh_hotspots(
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
            "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_score": target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_score",
                0.0,
            ),
            "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status": target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status",
                "none",
            ),
            "recent_reset_reentry_rebuild_reentry_refresh_path": target.get(
                "recent_reset_reentry_rebuild_reentry_refresh_path",
                "",
            ),
        }
        existing = grouped.get(class_key)
        if existing is None or abs(
            float(current["closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_score"] or 0.0)
        ) > abs(
            float(existing["closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_score"] or 0.0)
        ):
            grouped[class_key] = current
    hotspots = list(grouped.values())
    if mode == "confirmation":
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status")
            in {
                "recovering-confirmation-rebuild-reentry-reset",
                "restoring-confirmation-rebuild-reentry",
            }
        ]
        hotspots.sort(
            key=lambda item: (
                -float(item.get("closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_score", 0.0) or 0.0),
                str(item.get("label", "")),
            )
        )
    else:
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status")
            in {
                "recovering-clearance-rebuild-reentry-reset",
                "restoring-clearance-rebuild-reentry",
            }
        ]
        hotspots.sort(
            key=lambda item: (
                float(item.get("closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_score", 0.0) or 0.0),
                str(item.get("label", "")),
            )
        )
    return hotspots[:5]


def closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_summary(
    primary_target: dict[str, Any],
    recovering_confirmation_hotspots: list[dict[str, Any]],
    recovering_clearance_hotspots: list[dict[str, Any]],
    *,
    target_label: Callable[[dict[str, Any]], str],
) -> str:
    label = target_label(primary_target) or "The current target"
    status = str(
        primary_target.get("closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status", "none")
    )
    score = float(
        primary_target.get("closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_score", 0.0) or 0.0
    )
    if status == "recovering-confirmation-rebuild-reentry-reset":
        return (
            f"Fresh confirmation-side evidence is returning after rebuilt re-entry softened or "
            f"reset for {label}, but it has not yet restored stronger rebuilt re-entry posture "
            f"({score:.2f})."
        )
    if status == "recovering-clearance-rebuild-reentry-reset":
        return (
            f"Fresh clearance-side evidence is returning after rebuilt re-entry softened or reset "
            f"for {label}, but it has not yet restored stronger rebuilt re-entry posture ({score:.2f})."
        )
    if status == "restoring-confirmation-rebuild-reentry":
        return (
            f"Confirmation-side rebuilt re-entry for {label} is recovering strongly enough that "
            f"stronger rebuilt re-entry posture may be restored soon ({score:.2f})."
        )
    if status == "restoring-clearance-rebuild-reentry":
        return (
            f"Clearance-side rebuilt re-entry for {label} is recovering strongly enough that "
            f"stronger rebuilt re-entry posture may be restored soon ({score:.2f})."
        )
    if status == "reversing":
        return (
            f"The post-reset rebuilt re-entry recovery attempt for {label} is changing direction, "
            f"so stronger rebuilt re-entry posture stays blocked ({score:.2f})."
        )
    if status == "blocked":
        return str(
            primary_target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_reason",
                f"Local target instability is still preventing positive confirmation-side rebuilt re-entry restore for {label}.",
            )
        )
    if recovering_confirmation_hotspots:
        hotspot = recovering_confirmation_hotspots[0]
        return (
            f"Confirmation-side rebuilt re-entry recovery is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes are closest to restoring stronger rebuilt confirmation posture."
        )
    if recovering_clearance_hotspots:
        hotspot = recovering_clearance_hotspots[0]
        return (
            f"Clearance-side rebuilt re-entry recovery is strongest around {hotspot.get('label', 'recent hotspots')}, "
            "so those classes are closest to restoring stronger rebuilt clearance posture."
        )
    return "No rebuilt re-entry recovery attempt is active enough yet to restore stronger posture."


def closure_forecast_reset_reentry_rebuild_reentry_restore_summary(
    primary_target: dict[str, Any],
    recovering_confirmation_hotspots: list[dict[str, Any]],
    recovering_clearance_hotspots: list[dict[str, Any]],
    *,
    target_label: Callable[[dict[str, Any]], str],
) -> str:
    label = target_label(primary_target) or "The current target"
    status = str(
        primary_target.get("closure_forecast_reset_reentry_rebuild_reentry_restore_status", "none")
    )
    if status == "pending-confirmation-rebuild-reentry-restore":
        return (
            f"Fresh confirmation-side evidence is returning after rebuilt re-entry softened or "
            f"reset for {label}, but stronger rebuilt re-entry posture still needs more fresh "
            "follow-through before it is restored."
        )
    if status == "pending-clearance-rebuild-reentry-restore":
        return (
            f"Fresh clearance-side evidence is returning after rebuilt re-entry softened or reset "
            f"for {label}, but stronger rebuilt re-entry posture still needs more fresh "
            "follow-through before it is restored."
        )
    if status == "restored-confirmation-rebuild-reentry":
        return f"Fresh confirmation-side follow-through for {label} has restored stronger rebuilt re-entry posture."
    if status == "restored-clearance-rebuild-reentry":
        return f"Fresh clearance-side pressure for {label} has restored stronger rebuilt re-entry posture."
    if status == "blocked":
        return str(
            primary_target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_reason",
                f"Local target instability is still preventing positive confirmation-side rebuilt re-entry restore for {label}.",
            )
        )
    if recovering_confirmation_hotspots:
        hotspot = recovering_confirmation_hotspots[0]
        return (
            f"Confirmation-side rebuilt re-entry is closest to being restored around {hotspot.get('label', 'recent hotspots')}, "
            "but it still needs one more layer of fresh confirmation follow-through."
        )
    if recovering_clearance_hotspots:
        hotspot = recovering_clearance_hotspots[0]
        return (
            f"Clearance-side rebuilt re-entry is closest to being restored around {hotspot.get('label', 'recent hotspots')}, "
            "but it still needs one more layer of fresh clearance follow-through."
        )
    return "No rebuilt re-entry restore control is changing the current closure-forecast posture right now."


def apply_reset_reentry_rebuild_reentry_refresh_recovery_and_restore(
    resolution_targets: list[dict[str, Any]],
    history: list[dict[str, Any]],
    *,
    current_generated_at: str,
    confidence_calibration: dict[str, Any],
    recommendation_bucket: Callable[[dict[str, Any]], Any],
    class_closure_forecast_events: Callable[..., list[dict[str, Any]]],
    class_transition_events: Callable[..., list[dict[str, Any]]],
    target_class_transition_history: Callable[[dict[str, Any], list[dict[str, Any]]], dict[str, Any]],
    target_class_key: Callable[[dict[str, Any]], str],
    target_label: Callable[[dict[str, Any]], str],
    ordered_reset_reentry_events_for_target: Callable[
        [dict[str, Any], list[dict[str, Any]]], list[dict[str, Any]]
    ],
    closure_forecast_reset_side_from_status: Callable[[str], str],
    normalized_closure_forecast_direction: Callable[[str, float], str],
    clamp_round: Callable[..., float],
    closure_forecast_direction_majority: Callable[[list[str]], str],
    target_specific_normalization_noise: Callable[[dict[str, Any], dict[str, Any]], bool],
    closure_forecast_direction_reversing: Callable[[str, str], bool],
    closure_forecast_reset_reentry_rebuild_reentry_refresh_path_label: Callable[
        [dict[str, Any]], str
    ],
    class_reset_reentry_rebuild_reentry_refresh_restore_window_runs: int,
) -> dict[str, Any]:
    del confidence_calibration
    if not resolution_targets:
        return {
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_score": 0.0,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status": "none",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_status": "none",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reason": "",
            "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_summary": "No reset re-entry rebuild re-entry refresh recovery is recorded because there is no active target.",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_summary": "No reset re-entry rebuild re-entry restore is recorded because there is no active target.",
            "closure_forecast_reset_reentry_rebuild_reentry_refresh_window_runs": class_reset_reentry_rebuild_reentry_refresh_restore_window_runs,
            "recovering_from_confirmation_rebuild_reentry_reset_hotspots": [],
            "recovering_from_clearance_rebuild_reentry_reset_hotspots": [],
        }

    current_primary_target = resolution_targets[0]
    current_bucket = recommendation_bucket(current_primary_target)
    closure_forecast_events = class_closure_forecast_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )
    transition_events = class_transition_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )

    updated_targets: list[dict[str, Any]] = []
    for target in resolution_targets:
        refresh_recovery_score = 0.0
        refresh_recovery_status = "none"
        restore_status = "none"
        restore_reason = ""
        refresh_path = ""
        closure_likely_outcome = str(target.get("transition_closure_likely_outcome", "none"))
        closure_hysteresis_status = str(target.get("closure_forecast_hysteresis_status", "none"))
        closure_hysteresis_reason = str(target.get("closure_forecast_hysteresis_reason", ""))
        transition_status = str(target.get("class_reweight_transition_status", "none"))
        transition_reason = str(target.get("class_reweight_transition_reason", ""))
        resolution_status = str(target.get("class_transition_resolution_status", "none"))
        resolution_reason = str(target.get("class_transition_resolution_reason", ""))
        reentry_status = str(target.get("closure_forecast_reset_reentry_rebuild_reentry_status", "none"))
        reentry_reason = str(target.get("closure_forecast_reset_reentry_rebuild_reentry_reason", ""))
        persistence_age_runs = int(target.get("closure_forecast_reset_reentry_rebuild_reentry_age_runs", 0) or 0)
        persistence_score = float(
            target.get("closure_forecast_reset_reentry_rebuild_reentry_persistence_score", 0.0) or 0.0
        )
        persistence_status = str(
            target.get("closure_forecast_reset_reentry_rebuild_reentry_persistence_status", "none")
        )
        persistence_reason = str(
            target.get("closure_forecast_reset_reentry_rebuild_reentry_persistence_reason", "")
        )

        if recommendation_bucket(target) == current_bucket:
            transition_history_meta = target_class_transition_history(target, transition_events)
            refresh_meta = closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_for_target(
                target,
                closure_forecast_events,
                transition_history_meta,
                ordered_reset_reentry_events_for_target=ordered_reset_reentry_events_for_target,
                closure_forecast_reset_side_from_status=closure_forecast_reset_side_from_status,
                normalized_closure_forecast_direction=normalized_closure_forecast_direction,
                clamp_round=clamp_round,
                closure_forecast_direction_majority=closure_forecast_direction_majority,
                target_specific_normalization_noise=target_specific_normalization_noise,
                closure_forecast_direction_reversing=closure_forecast_direction_reversing,
                closure_forecast_reset_reentry_rebuild_reentry_refresh_path_label=(
                    closure_forecast_reset_reentry_rebuild_reentry_refresh_path_label
                ),
                class_reset_reentry_rebuild_reentry_refresh_restore_window_runs=(
                    class_reset_reentry_rebuild_reentry_refresh_restore_window_runs
                ),
            )
            refresh_recovery_score = float(
                refresh_meta["closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_score"]
            )
            refresh_recovery_status = str(
                refresh_meta["closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status"]
            )
            restore_status = str(
                refresh_meta["closure_forecast_reset_reentry_rebuild_reentry_restore_status"]
            )
            restore_reason = str(
                refresh_meta["closure_forecast_reset_reentry_rebuild_reentry_restore_reason"]
            )
            refresh_path = str(refresh_meta["recent_reset_reentry_rebuild_reentry_refresh_path"])
            control_updates = apply_reset_reentry_rebuild_reentry_refresh_restore_control(
                target,
                refresh_meta=refresh_meta,
                transition_history_meta=transition_history_meta,
                closure_likely_outcome=closure_likely_outcome,
                closure_hysteresis_status=closure_hysteresis_status,
                closure_hysteresis_reason=closure_hysteresis_reason,
                transition_status=transition_status,
                transition_reason=transition_reason,
                resolution_status=resolution_status,
                resolution_reason=resolution_reason,
                reentry_status=reentry_status,
                reentry_reason=reentry_reason,
                persistence_age_runs=persistence_age_runs,
                persistence_score=persistence_score,
                persistence_status=persistence_status,
                persistence_reason=persistence_reason,
            )
            closure_likely_outcome = str(control_updates["transition_closure_likely_outcome"])
            closure_hysteresis_status = str(control_updates["closure_forecast_hysteresis_status"])
            closure_hysteresis_reason = str(control_updates["closure_forecast_hysteresis_reason"])
            transition_status = str(control_updates["class_reweight_transition_status"])
            transition_reason = str(control_updates["class_reweight_transition_reason"])
            resolution_status = str(control_updates["class_transition_resolution_status"])
            resolution_reason = str(control_updates["class_transition_resolution_reason"])
            reentry_status = str(control_updates["closure_forecast_reset_reentry_rebuild_reentry_status"])
            reentry_reason = str(control_updates["closure_forecast_reset_reentry_rebuild_reentry_reason"])
            persistence_age_runs = int(
                control_updates["closure_forecast_reset_reentry_rebuild_reentry_age_runs"]
            )
            persistence_score = float(
                control_updates["closure_forecast_reset_reentry_rebuild_reentry_persistence_score"]
            )
            persistence_status = str(
                control_updates["closure_forecast_reset_reentry_rebuild_reentry_persistence_status"]
            )
            persistence_reason = str(
                control_updates["closure_forecast_reset_reentry_rebuild_reentry_persistence_reason"]
            )

        updated_targets.append(
            {
                **target,
                "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_score": refresh_recovery_score,
                "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status": refresh_recovery_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_status": restore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": restore_reason,
                "recent_reset_reentry_rebuild_reentry_refresh_path": refresh_path,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_rebuild_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_age_runs": persistence_age_runs,
                "closure_forecast_reset_reentry_rebuild_reentry_persistence_score": persistence_score,
                "closure_forecast_reset_reentry_rebuild_reentry_persistence_status": persistence_status,
                "closure_forecast_reset_reentry_rebuild_reentry_persistence_reason": persistence_reason,
            }
        )

    resolution_targets[:] = updated_targets
    primary_target = resolution_targets[0]
    recovering_confirmation_hotspots = closure_forecast_reset_reentry_rebuild_reentry_refresh_hotspots(
        resolution_targets,
        mode="confirmation",
        target_class_key=target_class_key,
    )
    recovering_clearance_hotspots = closure_forecast_reset_reentry_rebuild_reentry_refresh_hotspots(
        resolution_targets,
        mode="clearance",
        target_class_key=target_class_key,
    )
    return {
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_score": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_score",
            0.0,
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status",
            "none",
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_status",
            "none",
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_reason",
            "",
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_summary": (
            closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_summary(
                primary_target,
                recovering_confirmation_hotspots,
                recovering_clearance_hotspots,
                target_label=target_label,
            )
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_summary": (
            closure_forecast_reset_reentry_rebuild_reentry_restore_summary(
                primary_target,
                recovering_confirmation_hotspots,
                recovering_clearance_hotspots,
                target_label=target_label,
            )
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_refresh_window_runs": class_reset_reentry_rebuild_reentry_refresh_restore_window_runs,
        "recovering_from_confirmation_rebuild_reentry_reset_hotspots": recovering_confirmation_hotspots,
        "recovering_from_clearance_rebuild_reentry_reset_hotspots": recovering_clearance_hotspots,
    }


def _rererestore_event_is_confirmation_like(event: dict[str, Any]) -> bool:
    return (
        event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status",
            "none",
        )
        in {
            "pending-confirmation-rebuild-reentry-rererestore",
            "rererestored-confirmation-rebuild-reentry",
        }
        or event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status",
            "none",
        )
        in {
            "just-rererestored",
            "holding-confirmation-rebuild-reentry-rererestore",
            "sustained-confirmation-rebuild-reentry-rererestore",
        }
        or event.get("closure_forecast_hysteresis_status", "none")
        in {"pending-confirmation", "confirmed-confirmation"}
        or event.get("transition_closure_likely_outcome", "none") == "confirm-soon"
    )


def _rererestore_event_is_clearance_like(event: dict[str, Any]) -> bool:
    return (
        event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status",
            "none",
        )
        in {
            "pending-clearance-rebuild-reentry-rererestore",
            "rererestored-clearance-rebuild-reentry",
        }
        or event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status",
            "none",
        )
        in {
            "holding-clearance-rebuild-reentry-rererestore",
            "sustained-clearance-rebuild-reentry-rererestore",
        }
        or event.get("closure_forecast_hysteresis_status", "none")
        in {"pending-clearance", "confirmed-clearance"}
        or event.get("transition_closure_likely_outcome", "none")
        in {"clear-risk", "expire-risk"}
    )


def _rererestore_event_has_evidence(event: dict[str, Any]) -> bool:
    return (
        _rererestore_event_is_confirmation_like(event)
        or _rererestore_event_is_clearance_like(event)
        or event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status",
            "none",
        )
        in {"watch", "churn", "blocked"}
    )


def _rererestore_freshness_reason(
    freshness_status: str,
    weighted_rererestore_evidence_count: float,
    recent_window_weight_share: float,
    decayed_confirmation_rate: float,
    decayed_clearance_rate: float,
    *,
    class_reset_reentry_rebuild_reentry_restore_rererestore_freshness_window_runs: int,
) -> str:
    if freshness_status == "fresh":
        return (
            "Recent re-re-restored rebuilt re-entry evidence is still current enough to keep the stronger re-re-restored posture trusted, with "
            f"{recent_window_weight_share:.0%} of the weighted signal coming from the latest "
            f"{class_reset_reentry_rebuild_reentry_restore_rererestore_freshness_window_runs} runs."
        )
    if freshness_status == "mixed-age":
        return (
            "Re-re-restored rebuilt re-entry memory is still useful, but it is partly aging: "
            f"{recent_window_weight_share:.0%} of the weighted signal is recent and the rest is older carry-forward."
        )
    if freshness_status == "stale":
        return (
            "Older re-re-restored rebuilt re-entry strength is carrying more of the signal than recent runs, so it should not keep stronger posture alive on memory alone."
        )
    return (
        "Re-re-restored rebuilt re-entry memory is still too lightly exercised to judge freshness, with "
        f"{weighted_rererestore_evidence_count:.2f} weighted re-re-restored run(s), "
        f"{decayed_confirmation_rate:.0%} confirmation-like signal, and {decayed_clearance_rate:.0%} clearance-like signal."
    )


def _recent_rererestore_signal_mix(
    weighted_rererestore_evidence_count: float,
    weighted_confirmation_like: float,
    weighted_clearance_like: float,
    recent_window_weight_share: float,
) -> str:
    return (
        f"{weighted_rererestore_evidence_count:.2f} weighted re-re-restored run(s) with "
        f"{weighted_confirmation_like:.2f} confirmation-like, {weighted_clearance_like:.2f} clearance-like, "
        f"and {recent_window_weight_share:.0%} of the signal from the freshest runs."
    )


def closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_for_target(
    target: dict[str, Any],
    closure_forecast_events: list[dict[str, Any]],
    *,
    target_class_key: Callable[[dict[str, Any]], str],
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_status: Callable[
        [str], str
    ],
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_persistence_status: Callable[
        [str], str
    ],
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_event: Callable[
        [dict[str, Any]], str
    ],
    closure_forecast_freshness_status: Callable[[float, float], str],
    class_memory_recency_weights: tuple[float, ...],
    class_reset_reentry_rebuild_reentry_restore_rererestore_freshness_window_runs: int,
    history_window_runs: int,
) -> dict[str, Any]:
    class_key = target_class_key(target)
    class_events = [
        event for event in closure_forecast_events if event.get("class_key") == class_key
    ]
    relevant_events: list[dict[str, Any]] = []
    for event in class_events:
        if not _rererestore_event_has_evidence(event):
            continue
        relevant_events.append(event)
        if len(relevant_events) >= history_window_runs:
            break

    weighted_rererestore_evidence_count = 0.0
    weighted_confirmation_like = 0.0
    weighted_clearance_like = 0.0
    recent_rererestore_weight = 0.0
    current_side = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_persistence_status(
            str(
                target.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status",
                    "none",
                )
            )
        )
    )
    if current_side == "none":
        current_side = (
            closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_status(
                str(
                    target.get(
                        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status",
                        "none",
                    )
                )
            )
        )

    for index, event in enumerate(relevant_events):
        weight = class_memory_recency_weights[min(index, history_window_runs - 1)]
        weighted_rererestore_evidence_count += weight
        event_side = (
            closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_event(
                event
            )
        )
        if (
            index
            < class_reset_reentry_rebuild_reentry_restore_rererestore_freshness_window_runs
            and event_side == current_side
        ):
            recent_rererestore_weight += weight
        if _rererestore_event_is_confirmation_like(event):
            weighted_confirmation_like += weight
        if _rererestore_event_is_clearance_like(event):
            weighted_clearance_like += weight

    recent_window_weight_share = recent_rererestore_weight / max(
        weighted_rererestore_evidence_count,
        1.0,
    )
    freshness_status = closure_forecast_freshness_status(
        weighted_rererestore_evidence_count,
        recent_window_weight_share,
    )
    decayed_confirmation_rate = weighted_confirmation_like / max(
        weighted_rererestore_evidence_count,
        1.0,
    )
    decayed_clearance_rate = weighted_clearance_like / max(
        weighted_rererestore_evidence_count,
        1.0,
    )
    return {
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status": freshness_status,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_reason": _rererestore_freshness_reason(
            freshness_status,
            weighted_rererestore_evidence_count,
            recent_window_weight_share,
            decayed_confirmation_rate,
            decayed_clearance_rate,
            class_reset_reentry_rebuild_reentry_restore_rererestore_freshness_window_runs=(
                class_reset_reentry_rebuild_reentry_restore_rererestore_freshness_window_runs
            ),
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_memory_weight": round(
            recent_window_weight_share,
            2,
        ),
        "decayed_rererestored_rebuild_reentry_confirmation_rate": round(
            decayed_confirmation_rate,
            2,
        ),
        "decayed_rererestored_rebuild_reentry_clearance_rate": round(
            decayed_clearance_rate,
            2,
        ),
        "recent_reset_reentry_rebuild_reentry_restore_rererestore_signal_mix": _recent_rererestore_signal_mix(
            weighted_rererestore_evidence_count,
            weighted_confirmation_like,
            weighted_clearance_like,
            recent_window_weight_share,
        ),
        "has_fresh_aligned_recent_evidence": any(
            closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_event(
                event
            )
            == current_side
            and current_side != "none"
            for event in relevant_events[:2]
        ),
    }


def apply_reset_reentry_rebuild_reentry_restore_rererestore_freshness_reset_control(
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
    reentry_status: str,
    reentry_reason: str,
    restore_status: str,
    restore_reason: str,
    rerestore_status: str,
    rerestore_reason: str,
    rererestore_status: str,
    rererestore_reason: str,
    persistence_age_runs: int,
    persistence_score: float,
    persistence_status: str,
    persistence_reason: str,
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_persistence_status: Callable[
        [str], str
    ],
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_status: Callable[
        [str], str
    ],
    target_specific_normalization_noise: Callable[[dict[str, Any], dict[str, Any]], bool],
) -> dict[str, Any]:
    freshness_status = str(
        freshness_meta.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status",
            "insufficient-data",
        )
    )
    decayed_clearance_rate = float(
        freshness_meta.get(
            "decayed_rererestored_rebuild_reentry_clearance_rate",
            0.0,
        )
        or 0.0
    )
    churn_status = str(
        target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status",
            "none",
        )
    )
    current_side = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_persistence_status(
            persistence_status
        )
    )
    if current_side == "none":
        current_side = (
            closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_status(
                rererestore_status
            )
        )
    local_noise = target_specific_normalization_noise(target, transition_history_meta)
    recent_pending_status = str(
        transition_history_meta.get("recent_pending_status", "none")
    )
    has_fresh_aligned_recent_evidence = bool(
        freshness_meta.get("has_fresh_aligned_recent_evidence", False)
    )

    def _restore_weaker_pending_posture(
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
        blocked_reason = (
            "Local target instability still overrides healthy re-re-restored built re-entry freshness."
        )
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
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status": "blocked",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_reason": blocked_reason,
            "transition_closure_likely_outcome": closure_likely_outcome,
            "closure_forecast_hysteresis_status": closure_hysteresis_status,
            "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_status": reentry_status,
            "closure_forecast_reset_reentry_rebuild_reentry_reason": reentry_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_status": restore_status,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": restore_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": rerestore_status,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": rerestore_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": rererestore_status,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": rererestore_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs": persistence_age_runs,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score": persistence_score,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": persistence_status,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason": persistence_reason,
        }

    if current_side == "confirmation" and freshness_status == "mixed-age":
        if persistence_status == "sustained-confirmation-rebuild-reentry-rererestore" and (
            churn_status != "churn" or has_fresh_aligned_recent_evidence
        ):
            softened_reason = (
                "Re-re-restored confirmation-side rebuilt re-entry is still visible, but it is aging and has been stepped down from sustained strength."
            )
            return {
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status": "confirmation-softened",
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_reason": softened_reason,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": softened_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_rebuild_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_status": restore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": restore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": rerestore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": rerestore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": rererestore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": rererestore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs": persistence_age_runs,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score": persistence_score,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": "holding-confirmation-rebuild-reentry-rererestore",
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason": softened_reason,
            }
        if (
            persistence_status == "holding-confirmation-rebuild-reentry-rererestore"
            and churn_status == "churn"
        ):
            freshness_status = "stale"

    if current_side == "clearance" and freshness_status == "mixed-age":
        if persistence_status == "sustained-clearance-rebuild-reentry-rererestore" and (
            churn_status != "churn" or has_fresh_aligned_recent_evidence
        ):
            softened_reason = (
                "Re-re-restored clearance-side rebuilt re-entry is still visible, but it is aging and has been stepped down from sustained strength."
            )
            return {
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status": "clearance-softened",
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_reason": softened_reason,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": softened_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_rebuild_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_status": restore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": restore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": rerestore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": rerestore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": rererestore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": rererestore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs": persistence_age_runs,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score": persistence_score,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": "holding-clearance-rebuild-reentry-rererestore",
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason": softened_reason,
            }
        if (
            persistence_status == "holding-clearance-rebuild-reentry-rererestore"
            and churn_status == "churn"
        ):
            freshness_status = "stale"

    needs_reset = (
        current_side in {"confirmation", "clearance"}
        and persistence_status
        in {
            "holding-confirmation-rebuild-reentry-rererestore",
            "holding-clearance-rebuild-reentry-rererestore",
            "sustained-confirmation-rebuild-reentry-rererestore",
            "sustained-clearance-rebuild-reentry-rererestore",
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
                "Re-re-restored confirmation-side rebuilt re-entry has aged out enough that the stronger carry-forward has been withdrawn."
            )
            closure_likely_outcome = "hold"
            if closure_hysteresis_status == "confirmed-confirmation":
                closure_hysteresis_status = "pending-confirmation"
            closure_hysteresis_reason = reset_reason
            return {
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status": "confirmation-reset",
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_reason": reset_reason,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_status": "pending-confirmation-rebuild-reentry",
                "closure_forecast_reset_reentry_rebuild_reentry_reason": reset_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_status": "pending-confirmation-rebuild-reentry-restore",
                "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": reset_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": "pending-confirmation-rebuild-reentry-rerestore",
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": reset_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": "none",
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": "",
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs": 0,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score": 0.0,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": "none",
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason": "",
            }

        reset_reason = (
            "Re-re-restored clearance-side rebuilt re-entry has aged out enough that the stronger carry-forward has been withdrawn."
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
        ) = _restore_weaker_pending_posture(reset_reason)
        return {
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status": "clearance-reset",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_reason": reset_reason,
            "transition_closure_likely_outcome": closure_likely_outcome,
            "closure_forecast_hysteresis_status": closure_hysteresis_status,
            "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_status": "pending-clearance-rebuild-reentry",
            "closure_forecast_reset_reentry_rebuild_reentry_reason": reset_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_status": "pending-clearance-rebuild-reentry-restore",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": reset_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": "pending-clearance-rebuild-reentry-rerestore",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": reset_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": "none",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": "",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs": 0,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score": 0.0,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": "none",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason": "",
        }

    if (
        current_side == "clearance"
        and resolution_status == "cleared"
        and recent_pending_status in {"pending-support", "pending-caution"}
        and (
            freshness_status not in {"fresh", "mixed-age"}
            or decayed_clearance_rate < 0.50
            or persistence_status
            not in {
                "holding-clearance-rebuild-reentry-rererestore",
                "sustained-clearance-rebuild-reentry-rererestore",
            }
            or churn_status == "churn"
        )
    ):
        reset_reason = (
            "Re-re-restored clearance-side rebuilt re-entry has aged out enough that the stronger carry-forward has been withdrawn."
        )
        (
            transition_status,
            transition_reason,
            resolution_status,
            resolution_reason,
        ) = _restore_weaker_pending_posture(reset_reason)
        return {
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status": "clearance-reset",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_reason": reset_reason,
            "transition_closure_likely_outcome": "hold",
            "closure_forecast_hysteresis_status": "pending-clearance",
            "closure_forecast_hysteresis_reason": reset_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_status": "pending-clearance-rebuild-reentry",
            "closure_forecast_reset_reentry_rebuild_reentry_reason": reset_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_status": "pending-clearance-rebuild-reentry-restore",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": reset_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": "pending-clearance-rebuild-reentry-rerestore",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": reset_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": "none",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": "",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs": 0,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score": 0.0,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": "none",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason": "",
        }

    return {
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status": "none",
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_reason": "",
        "transition_closure_likely_outcome": closure_likely_outcome,
        "closure_forecast_hysteresis_status": closure_hysteresis_status,
        "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
        "class_reweight_transition_status": transition_status,
        "class_reweight_transition_reason": transition_reason,
        "class_transition_resolution_status": resolution_status,
        "class_transition_resolution_reason": resolution_reason,
        "closure_forecast_reset_reentry_rebuild_reentry_status": reentry_status,
        "closure_forecast_reset_reentry_rebuild_reentry_reason": reentry_reason,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_status": restore_status,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": restore_reason,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": rerestore_status,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": rerestore_reason,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": rererestore_status,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": rererestore_reason,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs": persistence_age_runs,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score": persistence_score,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": persistence_status,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason": persistence_reason,
    }


def closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_hotspots(
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
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status": target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status",
                "insufficient-data",
            ),
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status": target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status",
                "none",
            ),
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_memory_weight": target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_memory_weight",
                0.0,
            ),
            "decayed_rererestored_rebuild_reentry_confirmation_rate": target.get(
                "decayed_rererestored_rebuild_reentry_confirmation_rate",
                0.0,
            ),
            "decayed_rererestored_rebuild_reentry_clearance_rate": target.get(
                "decayed_rererestored_rebuild_reentry_clearance_rate",
                0.0,
            ),
            "recent_reset_reentry_rebuild_reentry_restore_rererestore_signal_mix": target.get(
                "recent_reset_reentry_rebuild_reentry_restore_rererestore_signal_mix",
                "",
            ),
            "dominant_count": max(
                target.get(
                    "decayed_rererestored_rebuild_reentry_confirmation_rate",
                    0.0,
                ),
                target.get(
                    "decayed_rererestored_rebuild_reentry_clearance_rate",
                    0.0,
                ),
            ),
            "rererestore_event_count": int(
                target.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs",
                    0,
                )
                or 0
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
            if item.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status"
            )
            == "fresh"
            and item.get("dominant_count", 0.0) > 0.0
        ]
    else:
        hotspots = [
            item
            for item in hotspots
            if item.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status"
            )
            == "stale"
            and item.get("dominant_count", 0.0) > 0.0
        ]
    hotspots.sort(
        key=lambda item: (
            -item.get("dominant_count", 0.0),
            -item.get("rererestore_event_count", 0),
            item.get("label", ""),
        )
    )
    return hotspots[:5]


def closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_summary(
    primary_target: dict[str, Any],
    stale_reset_reentry_rebuild_reentry_restore_rererestore_hotspots: list[dict[str, Any]],
    fresh_reset_reentry_rebuild_reentry_restore_rererestore_signal_hotspots: list[
        dict[str, Any]
    ],
    *,
    target_label: Callable[[dict[str, Any]], str],
) -> str:
    label = target_label(primary_target) or "The current target"
    freshness_status = primary_target.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status",
        "insufficient-data",
    )
    if freshness_status == "fresh":
        return (
            f"{label} still has recent re-re-restored rebuilt re-entry evidence that is current enough to keep the stronger re-re-restored posture trusted."
        )
    if freshness_status == "mixed-age":
        return (
            f"{label} still has useful re-re-restored rebuilt re-entry memory, but the stronger posture is no longer getting fully fresh reinforcement."
        )
    if freshness_status == "stale":
        return (
            f"{label} is leaning on older re-re-restored rebuilt re-entry strength more than fresh runs, so stronger re-re-restored posture should not keep carrying forward on memory alone."
        )
    if fresh_reset_reentry_rebuild_reentry_restore_rererestore_signal_hotspots:
        hotspot = fresh_reset_reentry_rebuild_reentry_restore_rererestore_signal_hotspots[0]
        return (
            f"Fresh re-re-restored rebuilt re-entry evidence is strongest around {hotspot.get('label', 'recent hotspots')}, so those classes can keep stronger re-re-restored posture more safely than older carry-forward."
        )
    if stale_reset_reentry_rebuild_reentry_restore_rererestore_hotspots:
        hotspot = stale_reset_reentry_rebuild_reentry_restore_rererestore_hotspots[0]
        return (
            f"Older re-re-restored rebuilt re-entry strength is lingering most around {hotspot.get('label', 'recent hotspots')}, so those classes should keep resetting re-re-restored posture when fresh follow-through stops."
        )
    return (
        "Re-re-restored rebuilt re-entry memory is still too lightly exercised to say whether stronger re-re-restored posture is being reinforced by fresh evidence or older carry-forward."
    )


def closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_summary(
    primary_target: dict[str, Any],
    stale_reset_reentry_rebuild_reentry_restore_rererestore_hotspots: list[dict[str, Any]],
    fresh_reset_reentry_rebuild_reentry_restore_rererestore_signal_hotspots: list[
        dict[str, Any]
    ],
    *,
    target_label: Callable[[dict[str, Any]], str],
) -> str:
    label = target_label(primary_target) or "The current target"
    reset_status = primary_target.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status",
        "none",
    )
    freshness_status = primary_target.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status",
        "insufficient-data",
    )
    confirmation_rate = primary_target.get(
        "decayed_rererestored_rebuild_reentry_confirmation_rate",
        0.0,
    )
    clearance_rate = primary_target.get(
        "decayed_rererestored_rebuild_reentry_clearance_rate",
        0.0,
    )
    if reset_status == "confirmation-softened":
        return (
            f"Re-re-restored confirmation-side rebuilt re-entry for {label} is still visible, but it is aging and has been stepped down from sustained strength."
        )
    if reset_status == "clearance-softened":
        return (
            f"Re-re-restored clearance-side rebuilt re-entry for {label} is still visible, but it is aging and has been stepped down from sustained strength."
        )
    if reset_status == "confirmation-reset":
        return (
            f"Re-re-restored confirmation-side rebuilt re-entry for {label} has aged out enough that the stronger carry-forward has been withdrawn."
        )
    if reset_status == "clearance-reset":
        return (
            f"Re-re-restored clearance-side rebuilt re-entry for {label} has aged out enough that the stronger carry-forward has been withdrawn."
        )
    if reset_status == "blocked":
        return str(
            primary_target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_reason",
                f"Local target instability still overrides healthy re-re-restored rebuilt re-entry freshness for {label}.",
            )
        )
    if freshness_status == "fresh" and confirmation_rate >= clearance_rate:
        return (
            f"Fresh re-re-restored rebuilt re-entry evidence for {label} is still reinforcing confirmation-side re-re-restored posture more than clearance pressure."
        )
    if freshness_status == "fresh":
        return (
            f"Fresh re-re-restored rebuilt re-entry evidence for {label} is still reinforcing clearance-side re-re-restored posture more than confirmation-side carry-forward."
        )
    if freshness_status == "mixed-age":
        return (
            f"Re-re-restored rebuilt re-entry posture for {label} is aging enough that it can keep holding, but it should no longer stay indefinitely at sustained strength."
        )
    if stale_reset_reentry_rebuild_reentry_restore_rererestore_hotspots:
        hotspot = stale_reset_reentry_rebuild_reentry_restore_rererestore_hotspots[0]
        return (
            f"Re-re-restored rebuilt re-entry posture is aging out fastest around {hotspot.get('label', 'recent hotspots')}, so those classes should reset re-re-restored carry-forward instead of relying on older follow-through."
        )
    if fresh_reset_reentry_rebuild_reentry_restore_rererestore_signal_hotspots:
        hotspot = fresh_reset_reentry_rebuild_reentry_restore_rererestore_signal_hotspots[0]
        return (
            f"Fresh re-re-restored rebuilt re-entry follow-through is strongest around {hotspot.get('label', 'recent hotspots')}, so those classes can preserve re-re-restored posture longer than aging carry-forward elsewhere."
        )
    return (
        "No re-re-restored rebuilt re-entry reset is changing the current stronger closure-forecast posture right now."
    )


def apply_reset_reentry_rebuild_reentry_restore_rererestore_freshness_and_reset(
    resolution_targets: list[dict[str, Any]],
    history: list[dict[str, Any]],
    *,
    current_generated_at: str,
    confidence_calibration: dict[str, Any],
    recommendation_bucket: Callable[[dict[str, Any]], object],
    class_closure_forecast_events: Callable[..., list[dict[str, Any]]],
    class_transition_events: Callable[..., list[dict[str, Any]]],
    target_class_transition_history: Callable[[dict[str, Any], list[dict[str, Any]]], dict[str, Any]],
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_for_target: Callable[
        [dict[str, Any], list[dict[str, Any]]], dict[str, Any]
    ],
    apply_reset_reentry_rebuild_reentry_restore_rererestore_freshness_reset_control: Callable[..., dict[str, Any]],
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_hotspots: Callable[
        ..., list[dict[str, Any]]
    ],
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_summary: Callable[
        [dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]], str
    ],
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_summary: Callable[
        [dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]], str
    ],
    class_reset_reentry_rebuild_reentry_restore_rererestore_freshness_window_runs: int,
) -> dict[str, Any]:
    if not resolution_targets:
        return {
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status": "insufficient-data",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_reason": "",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_summary": "No reset re-entry rebuild re-entry restore re-re-restore freshness is recorded because there is no active target.",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status": "none",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_reason": "",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_summary": "No reset re-entry rebuild re-entry restore re-re-restore reset is recorded because there is no active target.",
            "stale_reset_reentry_rebuild_reentry_restore_rererestore_hotspots": [],
            "fresh_reset_reentry_rebuild_reentry_restore_rererestore_signal_hotspots": [],
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_decay_window_runs": class_reset_reentry_rebuild_reentry_restore_rererestore_freshness_window_runs,
        }

    current_primary_target = resolution_targets[0]
    current_bucket = recommendation_bucket(current_primary_target)
    closure_forecast_events = class_closure_forecast_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )
    transition_events = class_transition_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )

    updated_targets: list[dict[str, Any]] = []
    for target in resolution_targets:
        freshness_status = "insufficient-data"
        freshness_reason = ""
        memory_weight = 0.0
        decayed_confirmation_rate = 0.0
        decayed_clearance_rate = 0.0
        signal_mix = ""
        reset_status = "none"
        reset_reason = ""
        closure_likely_outcome = str(
            target.get("transition_closure_likely_outcome", "none")
        )
        closure_hysteresis_status = str(
            target.get("closure_forecast_hysteresis_status", "none")
        )
        closure_hysteresis_reason = str(
            target.get("closure_forecast_hysteresis_reason", "")
        )
        transition_status = str(target.get("class_reweight_transition_status", "none"))
        transition_reason = str(target.get("class_reweight_transition_reason", ""))
        resolution_status = str(
            target.get("class_transition_resolution_status", "none")
        )
        resolution_reason = str(
            target.get("class_transition_resolution_reason", "")
        )
        reentry_status = str(
            target.get("closure_forecast_reset_reentry_rebuild_reentry_status", "none")
        )
        reentry_reason = str(
            target.get("closure_forecast_reset_reentry_rebuild_reentry_reason", "")
        )
        restore_status = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_status",
                "none",
            )
        )
        restore_reason = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_reason",
                "",
            )
        )
        rerestore_status = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status",
                "none",
            )
        )
        rerestore_reason = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason",
                "",
            )
        )
        rererestore_status = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status",
                "none",
            )
        )
        rererestore_reason = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason",
                "",
            )
        )
        persistence_age_runs = int(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs",
                0,
            )
            or 0
        )
        persistence_score = float(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score",
                0.0,
            )
            or 0.0
        )
        persistence_status = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status",
                "none",
            )
        )
        persistence_reason = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason",
                "",
            )
        )

        if recommendation_bucket(target) == current_bucket:
            transition_history_meta = target_class_transition_history(
                target,
                transition_events,
            )
            freshness_meta = (
                closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_for_target(
                    target,
                    closure_forecast_events,
                )
            )
            freshness_status = str(
                freshness_meta[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status"
                ]
            )
            freshness_reason = str(
                freshness_meta[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_reason"
                ]
            )
            memory_weight = float(
                freshness_meta[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_memory_weight"
                ]
            )
            decayed_confirmation_rate = float(
                freshness_meta[
                    "decayed_rererestored_rebuild_reentry_confirmation_rate"
                ]
            )
            decayed_clearance_rate = float(
                freshness_meta["decayed_rererestored_rebuild_reentry_clearance_rate"]
            )
            signal_mix = str(
                freshness_meta[
                    "recent_reset_reentry_rebuild_reentry_restore_rererestore_signal_mix"
                ]
            )
            control_updates = (
                apply_reset_reentry_rebuild_reentry_restore_rererestore_freshness_reset_control(
                    target,
                    freshness_meta=freshness_meta,
                    transition_history_meta=transition_history_meta,
                    closure_likely_outcome=closure_likely_outcome,
                    closure_hysteresis_status=closure_hysteresis_status,
                    closure_hysteresis_reason=closure_hysteresis_reason,
                    transition_status=transition_status,
                    transition_reason=transition_reason,
                    resolution_status=resolution_status,
                    resolution_reason=resolution_reason,
                    reentry_status=reentry_status,
                    reentry_reason=reentry_reason,
                    restore_status=restore_status,
                    restore_reason=restore_reason,
                    rerestore_status=rerestore_status,
                    rerestore_reason=rerestore_reason,
                    rererestore_status=rererestore_status,
                    rererestore_reason=rererestore_reason,
                    persistence_age_runs=persistence_age_runs,
                    persistence_score=persistence_score,
                    persistence_status=persistence_status,
                    persistence_reason=persistence_reason,
                )
            )
            reset_status = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status"
                ]
            )
            reset_reason = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_reason"
                ]
            )
            closure_likely_outcome = str(
                control_updates["transition_closure_likely_outcome"]
            )
            closure_hysteresis_status = str(
                control_updates["closure_forecast_hysteresis_status"]
            )
            closure_hysteresis_reason = str(
                control_updates["closure_forecast_hysteresis_reason"]
            )
            transition_status = str(control_updates["class_reweight_transition_status"])
            transition_reason = str(control_updates["class_reweight_transition_reason"])
            resolution_status = str(control_updates["class_transition_resolution_status"])
            resolution_reason = str(control_updates["class_transition_resolution_reason"])
            reentry_status = str(
                control_updates["closure_forecast_reset_reentry_rebuild_reentry_status"]
            )
            reentry_reason = str(
                control_updates["closure_forecast_reset_reentry_rebuild_reentry_reason"]
            )
            restore_status = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_status"
                ]
            )
            restore_reason = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_reason"
                ]
            )
            rerestore_status = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status"
                ]
            )
            rerestore_reason = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason"
                ]
            )
            rererestore_status = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status"
                ]
            )
            rererestore_reason = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason"
                ]
            )
            persistence_age_runs = int(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs"
                ]
            )
            persistence_score = float(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score"
                ]
            )
            persistence_status = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status"
                ]
            )
            persistence_reason = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason"
                ]
            )

        updated_targets.append(
            {
                **target,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status": freshness_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_reason": freshness_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_memory_weight": memory_weight,
                "decayed_rererestored_rebuild_reentry_confirmation_rate": decayed_confirmation_rate,
                "decayed_rererestored_rebuild_reentry_clearance_rate": decayed_clearance_rate,
                "recent_reset_reentry_rebuild_reentry_restore_rererestore_signal_mix": signal_mix,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status": reset_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_reason": reset_reason,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_rebuild_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_status": restore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": restore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": rerestore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": rerestore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": rererestore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": rererestore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs": persistence_age_runs,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score": persistence_score,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": persistence_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason": persistence_reason,
            }
        )

    resolution_targets[:] = updated_targets
    primary_target = resolution_targets[0]
    stale_hotspots = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_hotspots(
            resolution_targets,
            mode="stale",
        )
    )
    fresh_hotspots = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_hotspots(
            resolution_targets,
            mode="fresh",
        )
    )
    return {
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status",
            "insufficient-data",
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_reason",
            "",
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_summary": closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_summary(
            primary_target,
            stale_hotspots,
            fresh_hotspots,
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status",
            "none",
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_reason",
            "",
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_summary": closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_summary(
            primary_target,
            stale_hotspots,
            fresh_hotspots,
        ),
        "stale_reset_reentry_rebuild_reentry_restore_rererestore_hotspots": stale_hotspots,
        "fresh_reset_reentry_rebuild_reentry_restore_rererestore_signal_hotspots": fresh_hotspots,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_decay_window_runs": class_reset_reentry_rebuild_reentry_restore_rererestore_freshness_window_runs,
    }


def closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_for_target(
    target: dict[str, Any],
    closure_forecast_events: list[dict[str, Any]],
    transition_history_meta: dict[str, Any],
    *,
    ordered_reset_reentry_events_for_target: Callable[
        [dict[str, Any], list[dict[str, Any]]], list[dict[str, Any]]
    ],
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_event: Callable[
        [dict[str, Any]], str
    ],
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_path_label: Callable[
        [dict[str, Any]], str
    ],
    closure_forecast_direction_majority: Callable[[list[str]], str],
    closure_forecast_direction_reversing: Callable[[str, str], bool],
    clamp_round: Callable[..., float],
    class_reset_reentry_rebuild_reentry_restore_rererestore_window_runs: int,
) -> dict[str, Any]:
    matching_events = ordered_reset_reentry_events_for_target(
        target,
        closure_forecast_events,
    )[:class_reset_reentry_rebuild_reentry_restore_rererestore_window_runs]
    relevant_events = [
        event
        for event in matching_events
        if closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_event(
            event
        )
        != "none"
    ]
    current_side = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_event(
            matching_events[0]
        )
        if matching_events
        else "none"
    )
    persistence_age_runs = 0
    for event in matching_events:
        event_side = (
            closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_event(
                event
            )
        )
        if event_side != current_side or event_side == "none":
            break
        persistence_age_runs += 1

    weighted_total = 0.0
    weight_sum = 0.0
    directions: list[str] = []
    for index, event in enumerate(
        relevant_events[:class_reset_reentry_rebuild_reentry_restore_rererestore_window_runs]
    ):
        weight = (1.0, 0.8, 0.6, 0.4)[
            min(
                index,
                class_reset_reentry_rebuild_reentry_restore_rererestore_window_runs - 1,
            )
        ]
        event_side = (
            closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_event(
                event
            )
        )
        sign = 1.0 if event_side == "confirmation" else -1.0
        directions.append(
            "supporting-confirmation" if sign > 0 else "supporting-clearance"
        )
        magnitude = 0.0
        if event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status",
            "none",
        ) in {
            "rererestored-confirmation-rebuild-reentry",
            "rererestored-clearance-rebuild-reentry",
        }:
            magnitude += 0.15
        if event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_status",
            "none",
        ) in {
            "rererestoring-confirmation-rebuild-reentry",
            "rererestoring-clearance-rebuild-reentry",
        }:
            magnitude += 0.10
        momentum_status = str(
            event.get("closure_forecast_momentum_status", "insufficient-data")
        )
        if (event_side == "confirmation" and momentum_status == "sustained-confirmation") or (
            event_side == "clearance" and momentum_status == "sustained-clearance"
        ):
            magnitude += 0.10
        stability_status = str(event.get("closure_forecast_stability_status", "watch"))
        if stability_status == "stable":
            magnitude += 0.10
        freshness_status = str(
            event.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status",
                "insufficient-data",
            )
        )
        if freshness_status == "fresh":
            magnitude += 0.10
        elif freshness_status == "mixed-age":
            magnitude = max(0.0, magnitude - 0.10)
        if momentum_status in {"reversing", "unstable"}:
            magnitude = max(0.0, magnitude - 0.15)
        if stability_status == "oscillating":
            magnitude = max(0.0, magnitude - 0.15)
        if (
            event.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_status",
                "none",
            )
            != "none"
        ):
            magnitude = max(0.0, magnitude - 0.15)
        weighted_total += sign * magnitude * weight
        weight_sum += weight

    persistence_score = clamp_round(
        weighted_total / max(weight_sum, 1.0),
        lower=-0.95,
        upper=0.95,
    )
    current_momentum_status = str(
        target.get("closure_forecast_momentum_status", "insufficient-data")
    )
    current_stability_status = str(target.get("closure_forecast_stability_status", "watch"))
    current_freshness_status = str(
        target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status",
            "insufficient-data",
        )
    )
    earlier_majority = closure_forecast_direction_majority(directions[1:])
    current_direction = (
        "supporting-confirmation"
        if current_side == "confirmation"
        else "supporting-clearance"
        if current_side == "clearance"
        else "neutral"
    )

    if current_side == "none" and not relevant_events:
        persistence_status = "none"
    elif (
        target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status",
            "none",
        )
        in {
            "rererestored-confirmation-rebuild-reentry",
            "rererestored-clearance-rebuild-reentry",
        }
        and persistence_age_runs == 1
    ):
        persistence_status = "just-rererestored"
    elif len(relevant_events) < 2:
        persistence_status = "insufficient-data"
    elif (
        closure_forecast_direction_reversing(current_direction, earlier_majority)
        or current_momentum_status in {"reversing", "unstable"}
        or target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_status",
            "none",
        )
        != "none"
    ):
        persistence_status = "reversing"
    elif (
        current_side == "confirmation"
        and persistence_age_runs >= 3
        and current_freshness_status == "fresh"
        and current_momentum_status == "sustained-confirmation"
        and current_stability_status != "oscillating"
    ):
        persistence_status = "sustained-confirmation-rebuild-reentry-rererestore"
    elif (
        current_side == "clearance"
        and persistence_age_runs >= 3
        and current_freshness_status == "fresh"
        and current_momentum_status == "sustained-clearance"
        and current_stability_status != "oscillating"
    ):
        persistence_status = "sustained-clearance-rebuild-reentry-rererestore"
    elif current_side == "confirmation" and persistence_age_runs >= 2 and persistence_score > 0:
        persistence_status = "holding-confirmation-rebuild-reentry-rererestore"
    elif current_side == "clearance" and persistence_age_runs >= 2 and persistence_score < 0:
        persistence_status = "holding-clearance-rebuild-reentry-rererestore"
    else:
        persistence_status = "none"

    if persistence_status == "just-rererestored":
        persistence_reason = (
            "Stronger rerestored rebuilt re-entry posture has been re-re-restored, but it has not yet proved it can hold."
        )
    elif persistence_status == "holding-confirmation-rebuild-reentry-rererestore":
        persistence_reason = (
            "Confirmation-side re-re-restored posture has stayed aligned long enough to keep the stronger rerestored forecast in place."
        )
    elif persistence_status == "holding-clearance-rebuild-reentry-rererestore":
        persistence_reason = (
            "Clearance-side re-re-restored posture has stayed aligned long enough to keep the stronger rerestored caution in place."
        )
    elif persistence_status == "sustained-confirmation-rebuild-reentry-rererestore":
        persistence_reason = (
            "Confirmation-side re-re-restored posture is now holding with enough follow-through to trust the stronger rerestored forecast more."
        )
    elif persistence_status == "sustained-clearance-rebuild-reentry-rererestore":
        persistence_reason = (
            "Clearance-side re-re-restored posture is now holding with enough follow-through to trust the stronger rerestored caution more."
        )
    elif persistence_status == "reversing":
        persistence_reason = (
            "The re-re-restored rebuilt re-entry posture is already weakening, so it is being softened again."
        )
    elif persistence_status == "insufficient-data":
        persistence_reason = (
            "Re-re-restored rebuilt re-entry is still too lightly exercised to say whether the stronger posture can hold."
        )
    else:
        persistence_reason = ""

    return {
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs": persistence_age_runs,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score": persistence_score,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": persistence_status,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason": persistence_reason,
        "recent_reset_reentry_rebuild_reentry_restore_rererestore_persistence_path": " -> ".join(
            closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_path_label(
                event
            )
            for event in matching_events
            if event
        ),
    }


def closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_for_target(
    target: dict[str, Any],
    closure_forecast_events: list[dict[str, Any]],
    transition_history_meta: dict[str, Any],
    *,
    ordered_reset_reentry_events_for_target: Callable[
        [dict[str, Any], list[dict[str, Any]]], list[dict[str, Any]]
    ],
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_event: Callable[
        [dict[str, Any]], str
    ],
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_path_label: Callable[
        [dict[str, Any]], str
    ],
    class_direction_flip_count: Callable[[list[str]], int],
    target_specific_normalization_noise: Callable[[dict[str, Any], dict[str, Any]], bool],
    clamp_round: Callable[..., float],
    class_reset_reentry_rebuild_reentry_restore_rererestore_window_runs: int,
) -> dict[str, Any]:
    matching_events = ordered_reset_reentry_events_for_target(
        target,
        closure_forecast_events,
    )[:class_reset_reentry_rebuild_reentry_restore_rererestore_window_runs]
    relevant_events = [
        event
        for event in matching_events
        if closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_event(
            event
        )
        != "none"
    ]
    side_path = [
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_event(
            event
        )
        for event in relevant_events
    ]
    current_side = side_path[0] if side_path else "none"
    local_noise = target_specific_normalization_noise(target, transition_history_meta)
    if current_side == "none":
        churn_score = 0.0
        churn_status = "none"
        churn_reason = ""
    else:
        flip_count = class_direction_flip_count(
            [
                "supporting-confirmation" if side == "confirmation" else "supporting-clearance"
                for side in side_path
            ]
        )
        churn_score = float(flip_count) * 0.20
        stability_status = str(target.get("closure_forecast_stability_status", "watch"))
        momentum_status = str(
            target.get("closure_forecast_momentum_status", "insufficient-data")
        )
        if stability_status == "oscillating":
            churn_score += 0.15
        if momentum_status == "reversing":
            churn_score += 0.10
        if momentum_status == "unstable":
            churn_score += 0.10
        freshness_path = [
            str(
                event.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status",
                    "insufficient-data",
                )
            )
            for event in relevant_events
        ]
        if any(
            previous == "fresh" and current in {"mixed-age", "stale", "insufficient-data"}
            for previous, current in zip(freshness_path, freshness_path[1:])
        ):
            churn_score += 0.10
        if any(
            event.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_status",
                "none",
            )
            != "none"
            for event in relevant_events
        ):
            churn_score += 0.10
        if (
            len(relevant_events) >= 2
            and side_path[0] == side_path[1]
            and relevant_events[0].get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status",
                "insufficient-data",
            )
            == "fresh"
            and relevant_events[1].get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status",
                "insufficient-data",
            )
            == "fresh"
        ):
            churn_score -= 0.10
        churn_score = clamp_round(churn_score, lower=0.0, upper=0.95)
        if local_noise and current_side == "confirmation":
            churn_status = "blocked"
            churn_reason = (
                "Local target instability is preventing positive confirmation-side re-re-restored hold."
            )
        elif churn_score >= 0.45 or flip_count >= 2:
            churn_status = "churn"
            churn_reason = (
                "Re-re-restored rebuilt re-entry is flipping enough that stronger posture should be softened quickly."
            )
        elif churn_score >= 0.20:
            churn_status = "watch"
            churn_reason = (
                "Re-re-restored rebuilt re-entry is wobbling and may lose its stronger posture soon."
            )
        else:
            churn_status = "none"
            churn_reason = ""

    return {
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_score": churn_score,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status": churn_status,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason": churn_reason,
        "recent_reset_reentry_rebuild_reentry_restore_rererestore_churn_path": " -> ".join(
            closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_path_label(
                event
            )
            for event in matching_events
            if event
        ),
    }


def apply_reset_reentry_rebuild_reentry_restore_rererestore_persistence_and_churn_control(
    target: dict[str, Any],
    *,
    persistence_meta: dict[str, Any],
    churn_meta: dict[str, Any],
    transition_history_meta: dict[str, Any],
    closure_likely_outcome: str,
    closure_hysteresis_status: str,
    closure_hysteresis_reason: str,
    transition_status: str,
    transition_reason: str,
    resolution_status: str,
    resolution_reason: str,
    reentry_status: str,
    reentry_reason: str,
    restore_status: str,
    restore_reason: str,
    rerestore_status: str,
    rerestore_reason: str,
    rererestore_status: str,
    rererestore_reason: str,
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_status: Callable[
        [str], str
    ],
    closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_side_from_refresh_recovery_status: Callable[
        [str], str
    ],
) -> dict[str, Any]:
    persistence_status = str(
        persistence_meta.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status",
            "none",
        )
    )
    persistence_reason = str(
        persistence_meta.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason",
            "",
        )
    )
    churn_status = str(
        churn_meta.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status",
            "none",
        )
    )
    churn_reason = str(
        churn_meta.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason",
            "",
        )
    )
    current_freshness_status = str(
        target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status",
            "insufficient-data",
        )
    )
    transition_age_runs = int(target.get("class_transition_age_runs", 0) or 0)
    recent_pending_status = str(
        transition_history_meta.get("recent_pending_status", "none")
    )
    current_side = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_status(
            rererestore_status
        )
    )
    if current_side == "none":
        current_side = (
            closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_side_from_refresh_recovery_status(
                str(
                    target.get(
                        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_status",
                        "none",
                    )
                )
            )
        )
    if (
        current_side == "none"
        and persistence_status in {"none", "insufficient-data"}
        and churn_status == "none"
    ):
        return {
            "transition_closure_likely_outcome": closure_likely_outcome,
            "closure_forecast_hysteresis_status": closure_hysteresis_status,
            "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_status": reentry_status,
            "closure_forecast_reset_reentry_rebuild_reentry_reason": reentry_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_status": restore_status,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": restore_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": rerestore_status,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": rerestore_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": rererestore_status,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": rererestore_reason,
        }

    if current_side == "confirmation" and churn_status == "blocked":
        if closure_likely_outcome == "confirm-soon":
            closure_likely_outcome = "hold"
        if closure_hysteresis_status == "confirmed-confirmation":
            closure_hysteresis_status = "pending-confirmation"
        closure_hysteresis_reason = (
            churn_reason or persistence_reason or closure_hysteresis_reason
        )
        return {
            "transition_closure_likely_outcome": closure_likely_outcome,
            "closure_forecast_hysteresis_status": closure_hysteresis_status,
            "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_status": reentry_status,
            "closure_forecast_reset_reentry_rebuild_reentry_reason": reentry_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_status": restore_status,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": restore_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": "pending-confirmation-rebuild-reentry-rerestore",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": churn_reason
            or persistence_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": "pending-confirmation-rebuild-reentry-rererestore",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": churn_reason
            or persistence_reason,
        }

    if (
        current_side == "confirmation"
        and rererestore_status == "rererestored-confirmation-rebuild-reentry"
    ):
        if (
            persistence_status
            in {
                "just-rererestored",
                "holding-confirmation-rebuild-reentry-rererestore",
                "sustained-confirmation-rebuild-reentry-rererestore",
            }
            and churn_status != "churn"
        ):
            return {
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_rebuild_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_status": restore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": restore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": rerestore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": rerestore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": rererestore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": rererestore_reason,
            }
        if (
            persistence_status == "reversing"
            or churn_status == "churn"
            or (
                current_freshness_status in {"stale", "insufficient-data"}
                and persistence_status != "just-rererestored"
            )
        ):
            closure_likely_outcome = "hold"
            if closure_hysteresis_status == "confirmed-confirmation":
                closure_hysteresis_status = "pending-confirmation"
            closure_hysteresis_reason = (
                churn_reason or persistence_reason or closure_hysteresis_reason
            )
            return {
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_rebuild_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_status": restore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": restore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": "pending-confirmation-rebuild-reentry-rerestore",
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": churn_reason
                or persistence_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": "pending-confirmation-rebuild-reentry-rererestore",
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": churn_reason
                or persistence_reason,
            }

    if (
        current_side == "clearance"
        and rererestore_status == "rererestored-clearance-rebuild-reentry"
    ):
        if (
            persistence_status
            in {
                "just-rererestored",
                "holding-clearance-rebuild-reentry-rererestore",
                "sustained-clearance-rebuild-reentry-rererestore",
            }
            and churn_status != "churn"
        ):
            if (
                persistence_status
                in {
                    "holding-clearance-rebuild-reentry-rererestore",
                    "sustained-clearance-rebuild-reentry-rererestore",
                }
                and closure_likely_outcome == "expire-risk"
                and transition_age_runs < 3
            ):
                closure_likely_outcome = "clear-risk"
            return {
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_rebuild_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_status": restore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": restore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": rerestore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": rerestore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": rererestore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": rererestore_reason,
            }
        if (
            persistence_status in {"reversing", "none", "insufficient-data"}
            or churn_status == "churn"
            or (
                current_freshness_status in {"stale", "insufficient-data"}
                and persistence_status != "just-rererestored"
            )
        ):
            if closure_likely_outcome == "expire-risk":
                closure_likely_outcome = "clear-risk"
            elif closure_likely_outcome == "clear-risk":
                closure_likely_outcome = "hold"
            if closure_hysteresis_status == "confirmed-clearance":
                closure_hysteresis_status = "pending-clearance"
            closure_hysteresis_reason = (
                churn_reason or persistence_reason or closure_hysteresis_reason
            )
            if resolution_status == "cleared" and recent_pending_status in {
                "pending-support",
                "pending-caution",
            } and (
                persistence_status in {"reversing", "none", "insufficient-data"}
                or churn_status == "churn"
            ):
                transition_status = recent_pending_status
                transition_reason = (
                    churn_reason
                    or persistence_reason
                    or (
                        "Re-re-restored rebuilt re-entry stopped holding cleanly, so the earlier-clear posture has been withdrawn."
                    )
                )
                resolution_status = "none"
                resolution_reason = ""
            return {
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_rebuild_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_status": restore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": restore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": "pending-clearance-rebuild-reentry-rerestore",
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": churn_reason
                or persistence_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": "pending-clearance-rebuild-reentry-rererestore",
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": churn_reason
                or persistence_reason,
            }

    return {
        "transition_closure_likely_outcome": closure_likely_outcome,
        "closure_forecast_hysteresis_status": closure_hysteresis_status,
        "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
        "class_reweight_transition_status": transition_status,
        "class_reweight_transition_reason": transition_reason,
        "class_transition_resolution_status": resolution_status,
        "class_transition_resolution_reason": resolution_reason,
        "closure_forecast_reset_reentry_rebuild_reentry_status": reentry_status,
        "closure_forecast_reset_reentry_rebuild_reentry_reason": reentry_reason,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_status": restore_status,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": restore_reason,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": rerestore_status,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": rerestore_reason,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": rererestore_status,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": rererestore_reason,
    }


def closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_hotspots(
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
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs": target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs",
                0,
            ),
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score": target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score",
                0.0,
            ),
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status",
                "none",
            ),
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_score": target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_score",
                0.0,
            ),
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status": target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status",
                "none",
            ),
            "recent_reset_reentry_rebuild_reentry_restore_rererestore_persistence_path": target.get(
                "recent_reset_reentry_rebuild_reentry_restore_rererestore_persistence_path",
                "",
            ),
            "recent_reset_reentry_rebuild_reentry_restore_rererestore_churn_path": target.get(
                "recent_reset_reentry_rebuild_reentry_restore_rererestore_churn_path",
                "",
            ),
        }
        existing = grouped.get(class_key)
        if existing is None or abs(
            current[
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score"
            ]
        ) > abs(
            existing[
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score"
            ]
        ):
            grouped[class_key] = current
    hotspots = list(grouped.values())
    if mode == "just-rererestored":
        hotspots = [
            item
            for item in hotspots
            if item.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status"
            )
            == "just-rererestored"
        ]
        hotspots.sort(
            key=lambda item: (
                -item.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs",
                    0,
                ),
                -abs(
                    item.get(
                        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score",
                        0.0,
                    )
                ),
                item.get("label", ""),
            )
        )
    elif mode == "holding":
        hotspots = [
            item
            for item in hotspots
            if item.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status"
            )
            in {
                "holding-confirmation-rebuild-reentry-rererestore",
                "holding-clearance-rebuild-reentry-rererestore",
                "sustained-confirmation-rebuild-reentry-rererestore",
                "sustained-clearance-rebuild-reentry-rererestore",
            }
        ]
        hotspots.sort(
            key=lambda item: (
                -item.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs",
                    0,
                ),
                -abs(
                    item.get(
                        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score",
                        0.0,
                    )
                ),
                item.get("label", ""),
            )
        )
    else:
        hotspots = [
            item
            for item in hotspots
            if item.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status"
            )
            in {"watch", "churn", "blocked"}
        ]
        hotspots.sort(
            key=lambda item: (
                -item.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_score",
                    0.0,
                ),
                -item.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs",
                    0,
                ),
                item.get("label", ""),
            )
        )
    return hotspots[:5]


def closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_summary(
    primary_target: dict[str, Any],
    just_rererestored_rebuild_reentry_hotspots: list[dict[str, Any]],
    holding_reset_reentry_rebuild_reentry_restore_rererestore_hotspots: list[
        dict[str, Any]
    ],
    *,
    target_label: Callable[[dict[str, Any]], str],
) -> str:
    label = target_label(primary_target) or "The current target"
    status = str(
        primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status",
            "none",
        )
    )
    age_runs = primary_target.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs",
        0,
    )
    score = primary_target.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score",
        0.0,
    )
    if status == "just-rererestored":
        return (
            f"{label} has only just re-re-restored stronger rerestored posture, so it is still fragile ({score:.2f}; {age_runs} run)."
        )
    if status == "holding-confirmation-rebuild-reentry-rererestore":
        return (
            f"Confirmation-side re-re-restored posture for {label} has held long enough to keep the stronger rerestored forecast in place ({score:.2f}; {age_runs} runs)."
        )
    if status == "holding-clearance-rebuild-reentry-rererestore":
        return (
            f"Clearance-side re-re-restored posture for {label} has held long enough to keep the stronger rerestored caution in place ({score:.2f}; {age_runs} runs)."
        )
    if status == "sustained-confirmation-rebuild-reentry-rererestore":
        return (
            f"Confirmation-side re-re-restored posture for {label} is now holding with enough follow-through to trust the stronger rerestored forecast more ({score:.2f}; {age_runs} runs)."
        )
    if status == "sustained-clearance-rebuild-reentry-rererestore":
        return (
            f"Clearance-side re-re-restored posture for {label} is now holding with enough follow-through to trust the stronger rerestored caution more ({score:.2f}; {age_runs} runs)."
        )
    if status == "reversing":
        return (
            f"The re-re-restored rebuilt re-entry posture for {label} is already weakening, so it is being softened again ({score:.2f})."
        )
    if status == "insufficient-data":
        return (
            f"Re-re-restored rebuilt re-entry for {label} is still too lightly exercised to say whether the stronger posture can hold."
        )
    if just_rererestored_rebuild_reentry_hotspots:
        hotspot = just_rererestored_rebuild_reentry_hotspots[0]
        return (
            f"Newly re-re-restored posture is most fragile around {hotspot.get('label', 'recent hotspots')}, so those classes still need follow-through before the stronger rerestored posture can be trusted."
        )
    if holding_reset_reentry_rebuild_reentry_restore_rererestore_hotspots:
        hotspot = holding_reset_reentry_rebuild_reentry_restore_rererestore_hotspots[0]
        return (
            f"Re-re-restored posture is holding most cleanly around {hotspot.get('label', 'recent hotspots')}, so those classes are closest to keeping the stronger rerestored posture safely."
        )
    return (
        "No re-re-restored rebuilt re-entry posture is active enough yet to judge whether it can hold."
    )


def closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_summary(
    primary_target: dict[str, Any],
    reset_reentry_rebuild_reentry_restore_rererestore_churn_hotspots: list[
        dict[str, Any]
    ],
    *,
    target_label: Callable[[dict[str, Any]], str],
) -> str:
    label = target_label(primary_target) or "The current target"
    status = str(
        primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status",
            "none",
        )
    )
    score = primary_target.get(
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_score",
        0.0,
    )
    if status == "watch":
        return (
            f"Re-re-restored rebuilt re-entry for {label} is wobbling enough that stronger rerestored posture may soften soon ({score:.2f})."
        )
    if status == "churn":
        return (
            f"Re-re-restored rebuilt re-entry for {label} is flipping enough that stronger rerestored posture should be softened quickly ({score:.2f})."
        )
    if status == "blocked":
        return str(
            primary_target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason",
                f"Local target instability is preventing positive confirmation-side re-re-restored hold for {label}.",
            )
        )
    if reset_reentry_rebuild_reentry_restore_rererestore_churn_hotspots:
        hotspot = reset_reentry_rebuild_reentry_restore_rererestore_churn_hotspots[0]
        return (
            f"Re-re-restored rebuilt re-entry churn is highest around {hotspot.get('label', 'recent hotspots')}, so stronger rerestored posture there should soften quickly if the wobble continues."
        )
    return "No meaningful re-re-restored rebuilt re-entry churn is active right now."


def apply_reset_reentry_rebuild_reentry_restore_rererestore_persistence_and_churn(
    resolution_targets: list[dict[str, Any]],
    history: list[dict[str, Any]],
    *,
    current_generated_at: str,
    confidence_calibration: dict[str, Any],
    recommendation_bucket: Callable[[dict[str, Any]], object],
    class_closure_forecast_events: Callable[..., list[dict[str, Any]]],
    class_transition_events: Callable[..., list[dict[str, Any]]],
    target_class_transition_history: Callable[[dict[str, Any], list[dict[str, Any]]], dict[str, Any]],
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_for_target: Callable[
        [dict[str, Any], list[dict[str, Any]], dict[str, Any]], dict[str, Any]
    ],
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_for_target: Callable[
        [dict[str, Any], list[dict[str, Any]], dict[str, Any]], dict[str, Any]
    ],
    apply_reset_reentry_rebuild_reentry_restore_rererestore_persistence_and_churn_control: Callable[
        ...,
        dict[str, Any],
    ],
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_hotspots: Callable[
        ...,
        list[dict[str, Any]],
    ],
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_summary: Callable[
        [dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]], str
    ],
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_summary: Callable[
        [dict[str, Any], list[dict[str, Any]]], str
    ],
    class_reset_reentry_rebuild_reentry_restore_rererestore_window_runs: int,
) -> dict[str, Any]:
    if not resolution_targets:
        return {
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs": 0,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score": 0.0,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": "none",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason": "",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_summary": "No reset re-entry rebuild re-entry restore re-re-restore persistence is recorded because there is no active target.",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_window_runs": class_reset_reentry_rebuild_reentry_restore_rererestore_window_runs,
            "just_rererestored_rebuild_reentry_hotspots": [],
            "holding_reset_reentry_rebuild_reentry_restore_rererestore_hotspots": [],
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_score": 0.0,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status": "none",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason": "",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_summary": "No reset re-entry rebuild re-entry restore re-re-restore churn is recorded because there is no active target.",
            "reset_reentry_rebuild_reentry_restore_rererestore_churn_hotspots": [],
        }

    current_primary_target = resolution_targets[0]
    current_bucket = recommendation_bucket(current_primary_target)
    closure_forecast_events = class_closure_forecast_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )
    transition_events = class_transition_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )

    updated_targets: list[dict[str, Any]] = []
    for target in resolution_targets:
        persistence_age_runs = 0
        persistence_score = 0.0
        persistence_status = "none"
        persistence_reason = ""
        persistence_path = ""
        churn_score = 0.0
        churn_status = "none"
        churn_reason = ""
        churn_path = ""
        closure_likely_outcome = str(
            target.get("transition_closure_likely_outcome", "none")
        )
        closure_hysteresis_status = str(
            target.get("closure_forecast_hysteresis_status", "none")
        )
        closure_hysteresis_reason = str(
            target.get("closure_forecast_hysteresis_reason", "")
        )
        transition_status = str(target.get("class_reweight_transition_status", "none"))
        transition_reason = str(target.get("class_reweight_transition_reason", ""))
        resolution_status = str(
            target.get("class_transition_resolution_status", "none")
        )
        resolution_reason = str(
            target.get("class_transition_resolution_reason", "")
        )
        reentry_status = str(
            target.get("closure_forecast_reset_reentry_rebuild_reentry_status", "none")
        )
        reentry_reason = str(
            target.get("closure_forecast_reset_reentry_rebuild_reentry_reason", "")
        )
        restore_status = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_status",
                "none",
            )
        )
        restore_reason = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_reason",
                "",
            )
        )
        rerestore_status = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status",
                "none",
            )
        )
        rerestore_reason = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason",
                "",
            )
        )
        rererestore_status = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status",
                "none",
            )
        )
        rererestore_reason = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason",
                "",
            )
        )

        if recommendation_bucket(target) == current_bucket:
            transition_history_meta = target_class_transition_history(
                target,
                transition_events,
            )
            persistence_meta = (
                closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_for_target(
                    target,
                    closure_forecast_events,
                    transition_history_meta,
                )
            )
            churn_meta = (
                closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_for_target(
                    target,
                    closure_forecast_events,
                    transition_history_meta,
                )
            )
            persistence_age_runs = int(
                persistence_meta[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs"
                ]
            )
            persistence_score = float(
                persistence_meta[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score"
                ]
            )
            persistence_status = str(
                persistence_meta[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status"
                ]
            )
            persistence_reason = str(
                persistence_meta[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason"
                ]
            )
            persistence_path = str(
                persistence_meta[
                    "recent_reset_reentry_rebuild_reentry_restore_rererestore_persistence_path"
                ]
            )
            churn_score = float(
                churn_meta[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_score"
                ]
            )
            churn_status = str(
                churn_meta[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status"
                ]
            )
            churn_reason = str(
                churn_meta[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason"
                ]
            )
            churn_path = str(
                churn_meta[
                    "recent_reset_reentry_rebuild_reentry_restore_rererestore_churn_path"
                ]
            )
            control_updates = (
                apply_reset_reentry_rebuild_reentry_restore_rererestore_persistence_and_churn_control(
                    target,
                    persistence_meta=persistence_meta,
                    churn_meta=churn_meta,
                    transition_history_meta=transition_history_meta,
                    closure_likely_outcome=closure_likely_outcome,
                    closure_hysteresis_status=closure_hysteresis_status,
                    closure_hysteresis_reason=closure_hysteresis_reason,
                    transition_status=transition_status,
                    transition_reason=transition_reason,
                    resolution_status=resolution_status,
                    resolution_reason=resolution_reason,
                    reentry_status=reentry_status,
                    reentry_reason=reentry_reason,
                    restore_status=restore_status,
                    restore_reason=restore_reason,
                    rerestore_status=rerestore_status,
                    rerestore_reason=rerestore_reason,
                    rererestore_status=rererestore_status,
                    rererestore_reason=rererestore_reason,
                )
            )
            closure_likely_outcome = str(
                control_updates["transition_closure_likely_outcome"]
            )
            closure_hysteresis_status = str(
                control_updates["closure_forecast_hysteresis_status"]
            )
            closure_hysteresis_reason = str(
                control_updates["closure_forecast_hysteresis_reason"]
            )
            transition_status = str(control_updates["class_reweight_transition_status"])
            transition_reason = str(control_updates["class_reweight_transition_reason"])
            resolution_status = str(control_updates["class_transition_resolution_status"])
            resolution_reason = str(control_updates["class_transition_resolution_reason"])
            reentry_status = str(
                control_updates["closure_forecast_reset_reentry_rebuild_reentry_status"]
            )
            reentry_reason = str(
                control_updates["closure_forecast_reset_reentry_rebuild_reentry_reason"]
            )
            restore_status = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_status"
                ]
            )
            restore_reason = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_reason"
                ]
            )
            rerestore_status = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status"
                ]
            )
            rerestore_reason = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason"
                ]
            )
            rererestore_status = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status"
                ]
            )
            rererestore_reason = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason"
                ]
            )

        updated_targets.append(
            {
                **target,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs": persistence_age_runs,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score": persistence_score,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": persistence_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason": persistence_reason,
                "recent_reset_reentry_rebuild_reentry_restore_rererestore_persistence_path": persistence_path,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_score": churn_score,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status": churn_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason": churn_reason,
                "recent_reset_reentry_rebuild_reentry_restore_rererestore_churn_path": churn_path,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_rebuild_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_status": restore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": restore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": rerestore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": rerestore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": rererestore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": rererestore_reason,
            }
        )

    resolution_targets[:] = updated_targets
    primary_target = resolution_targets[0]
    just_rererestored_rebuild_reentry_hotspots = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_hotspots(
            resolution_targets,
            mode="just-rererestored",
        )
    )
    holding_reset_reentry_rebuild_reentry_restore_rererestore_hotspots = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_hotspots(
            resolution_targets,
            mode="holding",
        )
    )
    reset_reentry_rebuild_reentry_restore_rererestore_churn_hotspots = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_hotspots(
            resolution_targets,
            mode="churn",
        )
    )
    return {
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs",
            0,
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score",
            0.0,
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status",
            "none",
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason",
            "",
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_summary": closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_summary(
            primary_target,
            just_rererestored_rebuild_reentry_hotspots,
            holding_reset_reentry_rebuild_reentry_restore_rererestore_hotspots,
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_window_runs": class_reset_reentry_rebuild_reentry_restore_rererestore_window_runs,
        "just_rererestored_rebuild_reentry_hotspots": just_rererestored_rebuild_reentry_hotspots,
        "holding_reset_reentry_rebuild_reentry_restore_rererestore_hotspots": holding_reset_reentry_rebuild_reentry_restore_rererestore_hotspots,
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_score": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_score",
            0.0,
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status",
            "none",
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason",
            "",
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_summary": closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_summary(
            primary_target,
            reset_reentry_rebuild_reentry_restore_rererestore_churn_hotspots,
        ),
        "reset_reentry_rebuild_reentry_restore_rererestore_churn_hotspots": reset_reentry_rebuild_reentry_restore_rererestore_churn_hotspots,
    }


def closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_for_target(
    target: dict[str, Any],
    closure_forecast_events: list[dict[str, Any]],
    transition_history_meta: dict[str, Any],
    *,
    ordered_reset_reentry_events_for_target: Callable[
        [dict[str, Any], list[dict[str, Any]]], list[dict[str, Any]]
    ],
    closure_forecast_reset_side_from_status: Callable[[str], str],
    normalized_closure_forecast_direction: Callable[[str, float], str],
    clamp_round: Callable[..., float],
    closure_forecast_direction_majority: Callable[[list[str]], str],
    target_specific_normalization_noise: Callable[[dict[str, Any], dict[str, Any]], bool],
    closure_forecast_direction_reversing: Callable[[str, str], bool],
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_path_label: Callable[
        [dict[str, Any]], str
    ],
    class_reset_reentry_rebuild_reentry_restore_rererestore_refresh_window_runs: int,
) -> dict[str, Any]:
    matching_events = ordered_reset_reentry_events_for_target(
        target,
        closure_forecast_events,
    )[:class_reset_reentry_rebuild_reentry_restore_rererestore_refresh_window_runs]
    recent_rererestore_reset_side = "none"
    latest_reset_index: int | None = None
    for index, event in enumerate(matching_events):
        event_reset_side = closure_forecast_reset_side_from_status(
            str(
                event.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status",
                    "none",
                )
            )
        )
        if event_reset_side != "none":
            recent_rererestore_reset_side = event_reset_side
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
                str(
                    event.get(
                        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status",
                        "none",
                    )
                )
            )
            == "none"
            and direction == "neutral"
            and abs(score) < 0.05
        ):
            continue
        relevant_events.append(event)
        directions.append(direction)
        if (
            len(relevant_events)
            > class_reset_reentry_rebuild_reentry_restore_rererestore_refresh_window_runs
        ):
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
            str(
                event.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status",
                    "insufficient-data",
                )
            ),
            0.10,
        )
        weight = (1.0, 0.8, 0.6, 0.4)[
            min(
                len(relevant_events) - 1,
                class_reset_reentry_rebuild_reentry_restore_rererestore_refresh_window_runs
                - 1,
            )
        ]
        weighted_total += sign * signal_strength * freshness_factor * weight
        weight_sum += weight

    recovery_score = clamp_round(
        weighted_total / max(weight_sum, 1.0),
        lower=-0.95,
        upper=0.95,
    )
    current_score = float(target.get("closure_forecast_reweight_score", 0.0) or 0.0)
    current_direction = normalized_closure_forecast_direction(
        str(target.get("closure_forecast_reweight_direction", "neutral")),
        current_score,
    )
    current_freshness = str(
        target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status",
            "insufficient-data",
        )
    )
    current_momentum = str(
        target.get("closure_forecast_momentum_status", "insufficient-data")
    )
    current_stability = str(target.get("closure_forecast_stability_status", "watch"))
    earlier_majority = closure_forecast_direction_majority(directions[1:])
    local_noise = target_specific_normalization_noise(target, transition_history_meta)
    direction_reversing = closure_forecast_direction_reversing(
        current_direction,
        earlier_majority,
    )
    opposes_reset = (
        recent_rererestore_reset_side == "confirmation"
        and current_direction == "supporting-clearance"
    ) or (
        recent_rererestore_reset_side == "clearance"
        and current_direction == "supporting-confirmation"
    )
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
                event_side == recent_rererestore_reset_side
                and event.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status",
                    "insufficient-data",
                )
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
        and float(event.get("closure_forecast_reweight_score", 0.0) or 0.0)
        == current_score
        and event.get("closure_forecast_reweight_direction", "neutral")
        == target.get("closure_forecast_reweight_direction", "neutral")
        for event in matching_events[: latest_reset_index or 0]
    )
    if (
        current_side == recent_rererestore_reset_side
        and current_freshness == "fresh"
        and not current_event_already_counted
    ):
        aligned_fresh_runs_after_reset += 1

    if len(relevant_events) < 2 or recent_rererestore_reset_side == "none":
        recovery_status = "none"
    elif local_noise and current_direction == "supporting-confirmation":
        recovery_status = "blocked"
    elif opposes_reset or direction_reversing:
        recovery_status = "reversing"
    elif (
        recent_rererestore_reset_side == "confirmation"
        and current_direction == "supporting-confirmation"
        and current_freshness == "fresh"
        and recovery_score >= 0.25
        and current_stability != "oscillating"
    ):
        recovery_status = "rerererestoring-confirmation-rebuild-reentry"
    elif (
        recent_rererestore_reset_side == "clearance"
        and current_direction == "supporting-clearance"
        and current_freshness == "fresh"
        and recovery_score <= -0.25
        and current_stability != "oscillating"
    ):
        recovery_status = "rerererestoring-clearance-rebuild-reentry"
    elif (
        recent_rererestore_reset_side == "confirmation"
        and current_direction == "supporting-confirmation"
        and current_freshness in {"fresh", "mixed-age"}
        and recovery_score >= 0.15
    ):
        recovery_status = "recovering-confirmation-rebuild-reentry-rererestore-reset"
    elif (
        recent_rererestore_reset_side == "clearance"
        and current_direction == "supporting-clearance"
        and current_freshness in {"fresh", "mixed-age"}
        and recovery_score <= -0.15
    ):
        recovery_status = "recovering-clearance-rebuild-reentry-rererestore-reset"
    else:
        recovery_status = "none"

    if (
        recovery_status == "rerererestoring-confirmation-rebuild-reentry"
        and current_freshness == "fresh"
        and current_momentum == "sustained-confirmation"
        and current_stability == "stable"
        and not local_noise
        and aligned_fresh_runs_after_reset >= 2
    ):
        rerererestore_status = "rerererestored-confirmation-rebuild-reentry"
        rerererestore_reason = (
            "Fresh confirmation-side follow-through has re-re-re-restored stronger "
            "re-re-restored rebuilt re-entry posture."
        )
    elif (
        recovery_status == "rerererestoring-clearance-rebuild-reentry"
        and current_freshness == "fresh"
        and current_momentum == "sustained-clearance"
        and current_stability == "stable"
        and aligned_fresh_runs_after_reset >= 2
    ):
        rerererestore_status = "rerererestored-clearance-rebuild-reentry"
        rerererestore_reason = (
            "Fresh clearance-side pressure has re-re-re-restored stronger "
            "re-re-restored rebuilt re-entry posture."
        )
    elif local_noise and recovery_status in {
        "recovering-confirmation-rebuild-reentry-rererestore-reset",
        "rerererestoring-confirmation-rebuild-reentry",
        "blocked",
    }:
        rerererestore_status = "blocked"
        rerererestore_reason = (
            "Local target instability is still preventing positive confirmation-side "
            "re-re-restored rebuilt re-entry re-re-re-restore."
        )
    elif recovery_status in {
        "recovering-confirmation-rebuild-reentry-rererestore-reset",
        "rerererestoring-confirmation-rebuild-reentry",
    }:
        rerererestore_status = "pending-confirmation-rebuild-reentry-rerererestore"
        rerererestore_reason = (
            "Fresh confirmation-side evidence is returning after re-re-restored "
            "rebuilt re-entry softened or reset, but it has not yet re-re-re-restored "
            "stronger re-re-restored posture."
        )
    elif recovery_status in {
        "recovering-clearance-rebuild-reentry-rererestore-reset",
        "rerererestoring-clearance-rebuild-reentry",
    }:
        rerererestore_status = "pending-clearance-rebuild-reentry-rerererestore"
        rerererestore_reason = (
            "Fresh clearance-side evidence is returning after re-re-restored rebuilt "
            "re-entry softened or reset, but it has not yet re-re-re-restored "
            "stronger re-re-restored posture."
        )
    else:
        rerererestore_status = "none"
        rerererestore_reason = ""

    return {
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_score": recovery_score,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status": recovery_status,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status": rerererestore_status,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_reason": rerererestore_reason,
        "recent_reset_reentry_rebuild_reentry_restore_rererestore_refresh_path": " -> ".join(
            closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_path_label(
                event
            )
            for event in matching_events
            if event
        ),
        "recent_rererestore_reset_side": recent_rererestore_reset_side,
        "aligned_fresh_runs_after_latest_rererestore_reset": aligned_fresh_runs_after_reset,
    }


def apply_reset_reentry_rebuild_reentry_restore_rererestore_refresh_rerererestore_control(
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
    reentry_status: str,
    reentry_reason: str,
    restore_status: str,
    restore_reason: str,
    rerestore_status: str,
    rerestore_reason: str,
    rererestore_status: str,
    rererestore_reason: str,
    rererestore_age_runs: int,
    rererestore_persistence_score: float,
    rererestore_persistence_status: str,
    rererestore_persistence_reason: str,
    rererestore_churn_score: float,
    rererestore_churn_status: str,
    rererestore_churn_reason: str,
) -> dict[str, Any]:
    recovery_status = str(
        refresh_meta.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status",
            "none",
        )
    )
    rerererestore_status = str(
        refresh_meta.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status",
            "none",
        )
    )
    rerererestore_reason = str(
        refresh_meta.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_reason",
            "",
        )
    )
    recent_rererestore_reset_side = str(
        refresh_meta.get("recent_rererestore_reset_side", "none")
    )
    current_freshness = str(
        target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status",
            "insufficient-data",
        )
    )
    current_stability = str(target.get("closure_forecast_stability_status", "watch"))
    transition_age_runs = int(target.get("class_transition_age_runs", 0) or 0)
    recent_pending_status = str(
        transition_history_meta.get("recent_pending_status", "none")
    )
    decayed_clearance_rate = float(
        target.get("decayed_rererestored_rebuild_reentry_clearance_rate", 0.0) or 0.0
    )

    def _reset_rererestore_follow_through() -> dict[str, Any]:
        return {
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs": 0,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score": 0.0,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": "none",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason": "",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_score": 0.0,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status": "none",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason": "",
        }

    if rerererestore_status == "blocked":
        if closure_likely_outcome == "confirm-soon":
            closure_likely_outcome = "hold"
        if closure_hysteresis_status == "confirmed-confirmation":
            closure_hysteresis_status = "pending-confirmation"
        if recent_rererestore_reset_side == "confirmation":
            closure_hysteresis_reason = rerererestore_reason
        return {
            "transition_closure_likely_outcome": closure_likely_outcome,
            "closure_forecast_hysteresis_status": closure_hysteresis_status,
            "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_status": reentry_status,
            "closure_forecast_reset_reentry_rebuild_reentry_reason": reentry_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_status": restore_status,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": restore_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": rerestore_status,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": rerestore_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": rererestore_status,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": rererestore_reason,
            **_reset_rererestore_follow_through(),
        }

    if rerererestore_status == "rerererestored-confirmation-rebuild-reentry":
        return {
            "transition_closure_likely_outcome": "confirm-soon",
            "closure_forecast_hysteresis_status": "confirmed-confirmation",
            "closure_forecast_hysteresis_reason": rerererestore_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_status": "reentered-confirmation-rebuild",
            "closure_forecast_reset_reentry_rebuild_reentry_reason": rerererestore_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_status": "restored-confirmation-rebuild-reentry",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": rerererestore_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": "rerestored-confirmation-rebuild-reentry",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": rerererestore_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": "rererestored-confirmation-rebuild-reentry",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": rerererestore_reason,
            **_reset_rererestore_follow_through(),
        }

    if rerererestore_status == "rerererestored-clearance-rebuild-reentry":
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
            resolution_reason = rerererestore_reason
        return {
            "transition_closure_likely_outcome": restored_outcome,
            "closure_forecast_hysteresis_status": "confirmed-clearance",
            "closure_forecast_hysteresis_reason": rerererestore_reason,
            "class_reweight_transition_status": transition_status,
            "class_reweight_transition_reason": transition_reason,
            "class_transition_resolution_status": resolution_status,
            "class_transition_resolution_reason": resolution_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_status": "reentered-clearance-rebuild",
            "closure_forecast_reset_reentry_rebuild_reentry_reason": rerererestore_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_status": "restored-clearance-rebuild-reentry",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": rerererestore_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": "rerestored-clearance-rebuild-reentry",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": rerererestore_reason,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": "rererestored-clearance-rebuild-reentry",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": rerererestore_reason,
            **_reset_rererestore_follow_through(),
        }

    if recent_rererestore_reset_side == "confirmation":
        if rerererestore_status == "pending-confirmation-rebuild-reentry-rerererestore":
            return {
                "transition_closure_likely_outcome": "hold",
                "closure_forecast_hysteresis_status": "pending-confirmation",
                "closure_forecast_hysteresis_reason": rerererestore_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_rebuild_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_status": restore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": restore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": rerestore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": rerestore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": "pending-confirmation-rebuild-reentry-rererestore",
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": rerererestore_reason,
                **_reset_rererestore_follow_through(),
            }
        if recovery_status == "reversing" or current_freshness in {
            "stale",
            "insufficient-data",
        }:
            return {
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_rebuild_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_status": restore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": restore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": rerestore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": rerestore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": rererestore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": rererestore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs": rererestore_age_runs,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score": rererestore_persistence_score,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": rererestore_persistence_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason": rererestore_persistence_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_score": rererestore_churn_score,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status": rererestore_churn_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason": rererestore_churn_reason,
            }

    if recent_rererestore_reset_side == "clearance":
        if rerererestore_status == "pending-clearance-rebuild-reentry-rerererestore":
            weaker_outcome = closure_likely_outcome
            if weaker_outcome == "expire-risk":
                weaker_outcome = "clear-risk"
            return {
                "transition_closure_likely_outcome": weaker_outcome,
                "closure_forecast_hysteresis_status": "pending-clearance",
                "closure_forecast_hysteresis_reason": rerererestore_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_rebuild_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_status": restore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": restore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": rerestore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": rerestore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": "pending-clearance-rebuild-reentry-rererestore",
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": rerererestore_reason,
                **_reset_rererestore_follow_through(),
            }
        if recovery_status == "reversing" or current_freshness in {
            "stale",
            "insufficient-data",
        }:
            return {
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_rebuild_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_status": restore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": restore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": rerestore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": rerestore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": rererestore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": rererestore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs": rererestore_age_runs,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score": rererestore_persistence_score,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": rererestore_persistence_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason": rererestore_persistence_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_score": rererestore_churn_score,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status": rererestore_churn_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason": rererestore_churn_reason,
            }

    return {
        "transition_closure_likely_outcome": closure_likely_outcome,
        "closure_forecast_hysteresis_status": closure_hysteresis_status,
        "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
        "class_reweight_transition_status": transition_status,
        "class_reweight_transition_reason": transition_reason,
        "class_transition_resolution_status": resolution_status,
        "class_transition_resolution_reason": resolution_reason,
        "closure_forecast_reset_reentry_rebuild_reentry_status": reentry_status,
        "closure_forecast_reset_reentry_rebuild_reentry_reason": reentry_reason,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_status": restore_status,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": restore_reason,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": rerestore_status,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": rerestore_reason,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": rererestore_status,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": rererestore_reason,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs": rererestore_age_runs,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score": rererestore_persistence_score,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": rererestore_persistence_status,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason": rererestore_persistence_reason,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_score": rererestore_churn_score,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status": rererestore_churn_status,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason": rererestore_churn_reason,
    }


def closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_hotspots(
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
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_score": target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_score",
                0.0,
            ),
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status": target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status",
                "none",
            ),
            "recent_reset_reentry_rebuild_reentry_restore_rererestore_refresh_path": target.get(
                "recent_reset_reentry_rebuild_reentry_restore_rererestore_refresh_path",
                "",
            ),
        }
        existing = grouped.get(class_key)
        if existing is None or abs(
            current[
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_score"
            ]
        ) > abs(
            existing[
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_score"
            ]
        ):
            grouped[class_key] = current
    hotspots = list(grouped.values())
    if mode == "confirmation":
        hotspots = [
            item
            for item in hotspots
            if item.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status"
            )
            in {
                "recovering-confirmation-rebuild-reentry-rererestore-reset",
                "rerererestoring-confirmation-rebuild-reentry",
            }
        ]
        hotspots.sort(
            key=lambda item: (
                -item.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_score",
                    0.0,
                ),
                item.get("label", ""),
            )
        )
    else:
        hotspots = [
            item
            for item in hotspots
            if item.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status"
            )
            in {
                "recovering-clearance-rebuild-reentry-rererestore-reset",
                "rerererestoring-clearance-rebuild-reentry",
            }
        ]
        hotspots.sort(
            key=lambda item: (
                item.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_score",
                    0.0,
                ),
                item.get("label", ""),
            )
        )
    return hotspots[:5]


def closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_summary(
    primary_target: dict[str, Any],
    recovering_confirmation_hotspots: list[dict[str, Any]],
    recovering_clearance_hotspots: list[dict[str, Any]],
    *,
    target_label: Callable[[dict[str, Any]], str],
) -> str:
    label = target_label(primary_target) or "The current target"
    status = str(
        primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status",
            "none",
        )
    )
    score = float(
        primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_score",
            0.0,
        )
    )
    if status == "recovering-confirmation-rebuild-reentry-rererestore-reset":
        return (
            f"Fresh confirmation-side evidence is returning after re-re-restored "
            f"rebuilt re-entry softened or reset for {label}, but it has not yet "
            f"re-re-re-restored stronger re-re-restored posture ({score:.2f})."
        )
    if status == "recovering-clearance-rebuild-reentry-rererestore-reset":
        return (
            f"Fresh clearance-side evidence is returning after re-re-restored "
            f"rebuilt re-entry softened or reset for {label}, but it has not yet "
            f"re-re-re-restored stronger re-re-restored posture ({score:.2f})."
        )
    if status == "rerererestoring-confirmation-rebuild-reentry":
        return (
            f"Confirmation-side re-re-restored rebuilt re-entry for {label} is "
            f"recovering strongly enough that stronger re-re-restored posture may be "
            f"re-re-re-restored soon ({score:.2f})."
        )
    if status == "rerererestoring-clearance-rebuild-reentry":
        return (
            f"Clearance-side re-re-restored rebuilt re-entry for {label} is "
            f"recovering strongly enough that stronger re-re-restored posture may be "
            f"re-re-re-restored soon ({score:.2f})."
        )
    if status == "reversing":
        return (
            f"The post-reset re-re-restored rebuilt re-entry recovery attempt for "
            f"{label} is changing direction, so stronger posture stays blocked "
            f"({score:.2f})."
        )
    if status == "blocked":
        return str(
            primary_target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_reason",
                "Local target instability is still preventing positive "
                f"confirmation-side re-re-restored rebuilt re-entry re-re-re-restore for {label}.",
            )
        )
    if recovering_confirmation_hotspots:
        hotspot = recovering_confirmation_hotspots[0]
        return (
            "Confirmation-side re-re-restored rebuilt re-entry recovery is strongest "
            f"around {hotspot.get('label', 'recent hotspots')}, so those classes are "
            "closest to re-re-re-restoring stronger re-re-restored confirmation posture."
        )
    if recovering_clearance_hotspots:
        hotspot = recovering_clearance_hotspots[0]
        return (
            "Clearance-side re-re-restored rebuilt re-entry recovery is strongest "
            f"around {hotspot.get('label', 'recent hotspots')}, so those classes are "
            "closest to re-re-re-restoring stronger re-re-restored clearance posture."
        )
    return (
        "No re-re-restored rebuilt re-entry recovery attempt is active enough yet to "
        "re-re-re-restore stronger posture."
    )


def closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_summary(
    primary_target: dict[str, Any],
    recovering_confirmation_hotspots: list[dict[str, Any]],
    recovering_clearance_hotspots: list[dict[str, Any]],
    *,
    target_label: Callable[[dict[str, Any]], str],
) -> str:
    label = target_label(primary_target) or "The current target"
    status = str(
        primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status",
            "none",
        )
    )
    if status == "pending-confirmation-rebuild-reentry-rerererestore":
        return (
            f"Fresh confirmation-side evidence is returning after re-re-restored "
            f"rebuilt re-entry softened or reset for {label}, but stronger "
            "re-re-restored posture still needs more fresh follow-through before it is "
            "re-re-re-restored."
        )
    if status == "pending-clearance-rebuild-reentry-rerererestore":
        return (
            f"Fresh clearance-side evidence is returning after re-re-restored rebuilt "
            f"re-entry softened or reset for {label}, but stronger re-re-restored "
            "posture still needs more fresh follow-through before it is "
            "re-re-re-restored."
        )
    if status == "rerererestored-confirmation-rebuild-reentry":
        return (
            f"Fresh confirmation-side follow-through for {label} has re-re-re-restored "
            "stronger re-re-restored rebuilt re-entry posture."
        )
    if status == "rerererestored-clearance-rebuild-reentry":
        return (
            f"Fresh clearance-side pressure for {label} has re-re-re-restored "
            "stronger re-re-restored rebuilt re-entry posture."
        )
    if status == "blocked":
        return str(
            primary_target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_reason",
                "Local target instability is still preventing positive "
                f"confirmation-side re-re-restored rebuilt re-entry re-re-re-restore for {label}.",
            )
        )
    if recovering_confirmation_hotspots:
        hotspot = recovering_confirmation_hotspots[0]
        return (
            "Confirmation-side re-re-restored rebuilt re-entry is closest to being "
            f"re-re-re-restored around {hotspot.get('label', 'recent hotspots')}, but "
            "it still needs one more layer of fresh confirmation follow-through."
        )
    if recovering_clearance_hotspots:
        hotspot = recovering_clearance_hotspots[0]
        return (
            "Clearance-side re-re-restored rebuilt re-entry is closest to being "
            f"re-re-re-restored around {hotspot.get('label', 'recent hotspots')}, but "
            "it still needs one more layer of fresh clearance follow-through."
        )
    return (
        "No re-re-restored rebuilt re-entry re-re-re-restore control is changing the "
        "current closure-forecast posture right now."
    )


def apply_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_and_rerererestore(
    resolution_targets: list[dict[str, Any]],
    history: list[dict[str, Any]],
    *,
    current_generated_at: str,
    confidence_calibration: dict[str, Any],
    recommendation_bucket: Callable[[dict[str, Any]], Any],
    class_closure_forecast_events: Callable[..., list[dict[str, Any]]],
    class_transition_events: Callable[..., list[dict[str, Any]]],
    target_class_transition_history: Callable[
        [dict[str, Any], list[dict[str, Any]]], dict[str, Any]
    ],
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_for_target: Callable[
        [dict[str, Any], list[dict[str, Any]], dict[str, Any]], dict[str, Any]
    ],
    apply_reset_reentry_rebuild_reentry_restore_rererestore_refresh_rerererestore_control: Callable[
        ...,
        dict[str, Any],
    ],
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_hotspots: Callable[
        ...,
        list[dict[str, Any]],
    ],
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_summary: Callable[
        [dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]], str
    ],
    closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_summary: Callable[
        [dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]], str
    ],
    class_reset_reentry_rebuild_reentry_restore_rererestore_refresh_window_runs: int,
) -> dict[str, Any]:
    del confidence_calibration
    if not resolution_targets:
        return {
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_score": 0.0,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status": "none",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status": "none",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_reason": "",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_summary": "No reset re-entry rebuild re-entry restore re-re-restore refresh recovery is recorded because there is no active target.",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_summary": "No reset re-entry rebuild re-entry restore re-re-re-restore is recorded because there is no active target.",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_window_runs": class_reset_reentry_rebuild_reentry_restore_rererestore_refresh_window_runs,
            "recovering_from_confirmation_rebuild_reentry_rererestore_reset_hotspots": [],
            "recovering_from_clearance_rebuild_reentry_rererestore_reset_hotspots": [],
        }

    current_primary_target = resolution_targets[0]
    current_bucket = recommendation_bucket(current_primary_target)
    closure_forecast_events = class_closure_forecast_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )
    transition_events = class_transition_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )

    updated_targets: list[dict[str, Any]] = []
    for target in resolution_targets:
        refresh_recovery_score = 0.0
        refresh_recovery_status = "none"
        rerererestore_status = "none"
        rerererestore_reason = ""
        refresh_path = ""
        closure_likely_outcome = str(
            target.get("transition_closure_likely_outcome", "none")
        )
        closure_hysteresis_status = str(
            target.get("closure_forecast_hysteresis_status", "none")
        )
        closure_hysteresis_reason = str(
            target.get("closure_forecast_hysteresis_reason", "")
        )
        transition_status = str(target.get("class_reweight_transition_status", "none"))
        transition_reason = str(target.get("class_reweight_transition_reason", ""))
        resolution_status = str(target.get("class_transition_resolution_status", "none"))
        resolution_reason = str(target.get("class_transition_resolution_reason", ""))
        reentry_status = str(
            target.get("closure_forecast_reset_reentry_rebuild_reentry_status", "none")
        )
        reentry_reason = str(
            target.get("closure_forecast_reset_reentry_rebuild_reentry_reason", "")
        )
        restore_status = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_status",
                "none",
            )
        )
        restore_reason = str(
            target.get("closure_forecast_reset_reentry_rebuild_reentry_restore_reason", "")
        )
        rerestore_status = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status",
                "none",
            )
        )
        rerestore_reason = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason",
                "",
            )
        )
        rererestore_status = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status",
                "none",
            )
        )
        rererestore_reason = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason",
                "",
            )
        )
        rererestore_age_runs = int(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs",
                0,
            )
            or 0
        )
        rererestore_persistence_score = float(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score",
                0.0,
            )
            or 0.0
        )
        rererestore_persistence_status = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status",
                "none",
            )
        )
        rererestore_persistence_reason = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason",
                "",
            )
        )
        rererestore_churn_score = float(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_score",
                0.0,
            )
            or 0.0
        )
        rererestore_churn_status = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status",
                "none",
            )
        )
        rererestore_churn_reason = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason",
                "",
            )
        )

        if recommendation_bucket(target) == current_bucket:
            transition_history_meta = target_class_transition_history(
                target,
                transition_events,
            )
            refresh_meta = (
                closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_for_target(
                    target,
                    closure_forecast_events,
                    transition_history_meta,
                )
            )
            refresh_recovery_score = float(
                refresh_meta[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_score"
                ]
            )
            refresh_recovery_status = str(
                refresh_meta[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status"
                ]
            )
            rerererestore_status = str(
                refresh_meta[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status"
                ]
            )
            rerererestore_reason = str(
                refresh_meta[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_reason"
                ]
            )
            refresh_path = str(
                refresh_meta[
                    "recent_reset_reentry_rebuild_reentry_restore_rererestore_refresh_path"
                ]
            )
            control_updates = (
                apply_reset_reentry_rebuild_reentry_restore_rererestore_refresh_rerererestore_control(
                    target,
                    refresh_meta=refresh_meta,
                    transition_history_meta=transition_history_meta,
                    closure_likely_outcome=closure_likely_outcome,
                    closure_hysteresis_status=closure_hysteresis_status,
                    closure_hysteresis_reason=closure_hysteresis_reason,
                    transition_status=transition_status,
                    transition_reason=transition_reason,
                    resolution_status=resolution_status,
                    resolution_reason=resolution_reason,
                    reentry_status=reentry_status,
                    reentry_reason=reentry_reason,
                    restore_status=restore_status,
                    restore_reason=restore_reason,
                    rerestore_status=rerestore_status,
                    rerestore_reason=rerestore_reason,
                    rererestore_status=rererestore_status,
                    rererestore_reason=rererestore_reason,
                    rererestore_age_runs=rererestore_age_runs,
                    rererestore_persistence_score=rererestore_persistence_score,
                    rererestore_persistence_status=rererestore_persistence_status,
                    rererestore_persistence_reason=rererestore_persistence_reason,
                    rererestore_churn_score=rererestore_churn_score,
                    rererestore_churn_status=rererestore_churn_status,
                    rererestore_churn_reason=rererestore_churn_reason,
                )
            )
            closure_likely_outcome = str(control_updates["transition_closure_likely_outcome"])
            closure_hysteresis_status = str(
                control_updates["closure_forecast_hysteresis_status"]
            )
            closure_hysteresis_reason = str(
                control_updates["closure_forecast_hysteresis_reason"]
            )
            transition_status = str(control_updates["class_reweight_transition_status"])
            transition_reason = str(control_updates["class_reweight_transition_reason"])
            resolution_status = str(control_updates["class_transition_resolution_status"])
            resolution_reason = str(control_updates["class_transition_resolution_reason"])
            reentry_status = str(
                control_updates["closure_forecast_reset_reentry_rebuild_reentry_status"]
            )
            reentry_reason = str(
                control_updates["closure_forecast_reset_reentry_rebuild_reentry_reason"]
            )
            restore_status = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_status"
                ]
            )
            restore_reason = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_reason"
                ]
            )
            rerestore_status = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status"
                ]
            )
            rerestore_reason = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason"
                ]
            )
            rererestore_status = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status"
                ]
            )
            rererestore_reason = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason"
                ]
            )
            rererestore_age_runs = int(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs"
                ]
            )
            rererestore_persistence_score = float(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score"
                ]
            )
            rererestore_persistence_status = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status"
                ]
            )
            rererestore_persistence_reason = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason"
                ]
            )
            rererestore_churn_score = float(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_score"
                ]
            )
            rererestore_churn_status = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status"
                ]
            )
            rererestore_churn_reason = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason"
                ]
            )

        updated_targets.append(
            {
                **target,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_score": refresh_recovery_score,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status": refresh_recovery_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status": rerererestore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_reason": rerererestore_reason,
                "recent_reset_reentry_rebuild_reentry_restore_rererestore_refresh_path": refresh_path,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_rebuild_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_status": restore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": restore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": rerestore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": rerestore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": rererestore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": rererestore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs": rererestore_age_runs,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score": rererestore_persistence_score,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": rererestore_persistence_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason": rererestore_persistence_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_score": rererestore_churn_score,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status": rererestore_churn_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason": rererestore_churn_reason,
            }
        )

    resolution_targets[:] = updated_targets
    primary_target = resolution_targets[0]
    recovering_confirmation_hotspots = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_hotspots(
            resolution_targets,
            mode="confirmation",
        )
    )
    recovering_clearance_hotspots = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_hotspots(
            resolution_targets,
            mode="clearance",
        )
    )
    return {
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_score": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_score",
            0.0,
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status",
            "none",
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status",
            "none",
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_reason",
            "",
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_summary": (
            closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_summary(
                primary_target,
                recovering_confirmation_hotspots,
                recovering_clearance_hotspots,
            )
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_summary": (
            closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_summary(
                primary_target,
                recovering_confirmation_hotspots,
                recovering_clearance_hotspots,
            )
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_window_runs": class_reset_reentry_rebuild_reentry_restore_rererestore_refresh_window_runs,
        "recovering_from_confirmation_rebuild_reentry_rererestore_reset_hotspots": recovering_confirmation_hotspots,
        "recovering_from_clearance_rebuild_reentry_rererestore_reset_hotspots": recovering_clearance_hotspots,
    }


def _rerererestore_text(text: str) -> str:
    transformed = text or ""
    protected = (
        ("re-re-restored", "__RRR_RESTORED__"),
        ("Re-re-restored", "__RRR_RESTORED_CAP__"),
        ("re-re-restoring", "__RRR_RESTORING__"),
        ("Re-re-restoring", "__RRR_RESTORING_CAP__"),
        ("rererestored", "__RERERERESTORED__"),
        ("Rererestored", "__RERERERESTORED_CAP__"),
        ("rererestoring", "__RERERERESTORING__"),
        ("Rererestoring", "__RERERERESTORING_CAP__"),
    )
    for old, marker in protected:
        transformed = transformed.replace(old, marker)
    transformed = transformed.replace("rererestore", "rerererestore")
    transformed = transformed.replace("Rererestore", "Rerererestore")
    transformed = transformed.replace("re-re-restore", "re-re-re-restore")
    transformed = transformed.replace("Re-re-restore", "Re-re-re-restore")
    finalized = (
        ("__RRR_RESTORED__", "re-re-re-restored"),
        ("__RRR_RESTORED_CAP__", "Re-re-re-restored"),
        ("__RRR_RESTORING__", "re-re-re-restoring"),
        ("__RRR_RESTORING_CAP__", "Re-re-re-restoring"),
        ("__RERERERESTORED__", "rerererestored"),
        ("__RERERERESTORED_CAP__", "Rerererestored"),
        ("__RERERERESTORING__", "rerererestoring"),
        ("__RERERERESTORING_CAP__", "Rerererestoring"),
    )
    for marker, new in finalized:
        transformed = transformed.replace(marker, new)
    return transformed


# Restore-tier depth arithmetic. A restore-tier word is "store"/"stored"/"storing"
# prefixed by one "re" per depth level: restore(1) -> rerestore(2) -> rererestore(3)
# -> rerererestore(4). The translation shims below previously hand-spelled every
# depth-shifted output string; they now share this single primitive, which moves a
# status token's restore tier by `delta` levels (passthrough/unknown tokens carry no
# tier word and are returned unchanged).
_RESTORE_TIER_BASES = ("storing", "stored", "store")


def _shift_restore_tier(token: str, delta: int) -> str:
    parts = token.split("-")
    for index, part in enumerate(parts):
        for base in _RESTORE_TIER_BASES:
            if not part.endswith(base):
                continue
            prefix = part[: -len(base)]
            if not prefix or len(prefix) % 2 or prefix != "re" * (len(prefix) // 2):
                return token
            new_depth = len(prefix) // 2 + delta
            if new_depth < 1:
                return token
            parts[index] = "re" * new_depth + base
            return "-".join(parts)
    return token


def _translate_restore_tier_status(status: str, *, delta: int, recognized: frozenset[str]) -> str:
    # Recognized inputs are translated by shifting their restore tier `delta` levels.
    # Passthrough terms (none/blocked/reversing/insufficient-data) are recognized but
    # carry no tier word, so the shift returns them unchanged. Anything else -> "none".
    if status in recognized:
        return _shift_restore_tier(status, delta)
    return "none"


_STATUS_TO_RERERESTORE_INPUTS = frozenset(
    {
        "pending-confirmation-rebuild-reentry-rerererestore",
        "pending-clearance-rebuild-reentry-rerererestore",
        "rerererestored-confirmation-rebuild-reentry",
        "rerererestored-clearance-rebuild-reentry",
        "blocked",
        "none",
    }
)
_PERSISTENCE_TO_RERERESTORE_INPUTS = frozenset(
    {
        "just-rerererestored",
        "holding-confirmation-rebuild-reentry-rerererestore",
        "holding-clearance-rebuild-reentry-rerererestore",
        "sustained-confirmation-rebuild-reentry-rerererestore",
        "sustained-clearance-rebuild-reentry-rerererestore",
        "reversing",
        "insufficient-data",
        "none",
    }
)
_REFRESH_TO_RERERESTORE_INPUTS = frozenset(
    {
        "recovering-confirmation-rebuild-reentry-rererestore-reset",
        "recovering-clearance-rebuild-reentry-rererestore-reset",
        "rerererestoring-confirmation-rebuild-reentry",
        "rerererestoring-clearance-rebuild-reentry",
        "reversing",
        "blocked",
        "none",
    }
)
_PERSISTENCE_FROM_RERERESTORE_INPUTS = frozenset(
    {
        "just-rererestored",
        "holding-confirmation-rebuild-reentry-rererestore",
        "holding-clearance-rebuild-reentry-rererestore",
        "sustained-confirmation-rebuild-reentry-rererestore",
        "sustained-clearance-rebuild-reentry-rererestore",
        "reversing",
        "insufficient-data",
        "none",
    }
)


def _status_to_rererestore_status(status: str) -> str:
    return _translate_restore_tier_status(
        status, delta=-1, recognized=_STATUS_TO_RERERESTORE_INPUTS
    )


def _persistence_status_to_rererestore_status(status: str) -> str:
    return _translate_restore_tier_status(
        status, delta=-1, recognized=_PERSISTENCE_TO_RERERESTORE_INPUTS
    )


def _refresh_status_to_rererestore_refresh_status(status: str) -> str:
    return _translate_restore_tier_status(
        status, delta=-1, recognized=_REFRESH_TO_RERERESTORE_INPUTS
    )


def _persistence_status_from_rererestore_status(status: str) -> str:
    return _translate_restore_tier_status(
        status, delta=1, recognized=_PERSISTENCE_FROM_RERERESTORE_INPUTS
    )


def _translate_target_for_persistence(target: dict[str, Any]) -> dict[str, Any]:
    return {
        **target,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": (
            _status_to_rererestore_status(
                str(
                    target.get(
                        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status",
                        "none",
                    )
                )
            )
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": (
            _persistence_status_to_rererestore_status(
                str(
                    target.get(
                        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status",
                        "none",
                    )
                )
            )
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status": (
            str(
                target.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status",
                    "none",
                )
            )
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_status": (
            _refresh_status_to_rererestore_refresh_status(
                str(
                    target.get(
                        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status",
                        "none",
                    )
                )
            )
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status": (
            str(
                target.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status",
                    "insufficient-data",
                )
            )
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_status": (
            str(
                target.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status",
                    "none",
                )
            )
        ),
    }


def _translate_event_for_persistence(event: dict[str, Any]) -> dict[str, Any]:
    translated = _translate_target_for_persistence(event)
    translated["closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status"] = (
        _status_to_rererestore_status(
            str(
                event.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status",
                    "none",
                )
            )
        )
    )
    translated[
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status"
    ] = _persistence_status_to_rererestore_status(
        str(
            event.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status",
                "none",
            )
        )
    )
    translated[
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status"
    ] = str(
        event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status",
            "none",
        )
    )
    return translated


def closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_text(
    text: str,
) -> str:
    return _rerererestore_text(text)


def closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_for_target(
    target: dict[str, Any],
    closure_forecast_events: list[dict[str, Any]],
    transition_history_meta: dict[str, Any],
    *,
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_for_target: Callable[
        [dict[str, Any], list[dict[str, Any]], dict[str, Any]], dict[str, Any]
    ],
) -> dict[str, Any]:
    translated_target = _translate_target_for_persistence(target)
    translated_events = [
        _translate_event_for_persistence(event) for event in closure_forecast_events
    ]
    persistence_meta = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_for_target(
            translated_target,
            translated_events,
            transition_history_meta,
        )
    )
    return {
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs": (
            persistence_meta.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs",
                0,
            )
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score": (
            persistence_meta.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score",
                0.0,
            )
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status": (
            _persistence_status_from_rererestore_status(
                str(
                    persistence_meta.get(
                        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status",
                        "none",
                    )
                )
            )
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_reason": (
            _rerererestore_text(
                str(
                    persistence_meta.get(
                        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason",
                        "",
                    )
                )
            )
        ),
        "recent_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_path": (
            _rerererestore_text(
                str(
                    persistence_meta.get(
                        "recent_reset_reentry_rebuild_reentry_restore_rererestore_persistence_path",
                        "",
                    )
                )
            )
        ),
    }


def closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_for_target(
    target: dict[str, Any],
    closure_forecast_events: list[dict[str, Any]],
    transition_history_meta: dict[str, Any],
    *,
    closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_for_target: Callable[
        [dict[str, Any], list[dict[str, Any]], dict[str, Any]], dict[str, Any]
    ],
) -> dict[str, Any]:
    translated_target = _translate_target_for_persistence(target)
    translated_events = [
        _translate_event_for_persistence(event) for event in closure_forecast_events
    ]
    churn_meta = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_for_target(
            translated_target,
            translated_events,
            transition_history_meta,
        )
    )
    return {
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score": churn_meta.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_score",
            0.0,
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status": churn_meta.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status",
            "none",
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason": _rerererestore_text(
            str(
                churn_meta.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason",
                    "",
                )
            )
        ),
        "recent_reset_reentry_rebuild_reentry_restore_rerererestore_churn_path": _rerererestore_text(
            str(
                churn_meta.get(
                    "recent_reset_reentry_rebuild_reentry_restore_rererestore_churn_path",
                    "",
                )
            )
        ),
    }


def apply_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_and_churn_control(
    target: dict[str, Any],
    *,
    persistence_meta: dict[str, Any],
    churn_meta: dict[str, Any],
    transition_history_meta: dict[str, Any],
    closure_likely_outcome: str,
    closure_hysteresis_status: str,
    closure_hysteresis_reason: str,
    transition_status: str,
    transition_reason: str,
    resolution_status: str,
    resolution_reason: str,
    reentry_status: str,
    reentry_reason: str,
    restore_status: str,
    restore_reason: str,
    rerestore_status: str,
    rerestore_reason: str,
    rererestore_status: str,
    rererestore_reason: str,
    apply_reset_reentry_rebuild_reentry_restore_rererestore_persistence_and_churn_control: Callable[
        ...,
        dict[str, Any],
    ],
) -> dict[str, Any]:
    translated_target = _translate_target_for_persistence(target)
    translated_persistence_meta = {
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": (
            _persistence_status_to_rererestore_status(
                str(
                    persistence_meta.get(
                        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status",
                        "none",
                    )
                )
            )
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason": (
            persistence_meta.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_reason",
                "",
            )
        ),
    }
    translated_churn_meta = {
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status": (
            churn_meta.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status",
                "none",
            )
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason": (
            churn_meta.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason",
                "",
            )
        ),
    }
    return (
        apply_reset_reentry_rebuild_reentry_restore_rererestore_persistence_and_churn_control(
            translated_target,
            persistence_meta=translated_persistence_meta,
            churn_meta=translated_churn_meta,
            transition_history_meta=transition_history_meta,
            closure_likely_outcome=closure_likely_outcome,
            closure_hysteresis_status=closure_hysteresis_status,
            closure_hysteresis_reason=closure_hysteresis_reason,
            transition_status=transition_status,
            transition_reason=transition_reason,
            resolution_status=resolution_status,
            resolution_reason=resolution_reason,
            reentry_status=reentry_status,
            reentry_reason=reentry_reason,
            restore_status=restore_status,
            restore_reason=restore_reason,
            rerestore_status=rerestore_status,
            rerestore_reason=rerestore_reason,
            rererestore_status=rererestore_status,
            rererestore_reason=rererestore_reason,
        )
    )


def closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_hotspots(
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
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs": target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs",
                0,
            ),
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score": target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score",
                0.0,
            ),
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status": target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status",
                "none",
            ),
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score": target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score",
                0.0,
            ),
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status": target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status",
                "none",
            ),
            "recent_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_path": target.get(
                "recent_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_path",
                "",
            ),
            "recent_reset_reentry_rebuild_reentry_restore_rerererestore_churn_path": target.get(
                "recent_reset_reentry_rebuild_reentry_restore_rerererestore_churn_path",
                "",
            ),
        }
        existing = grouped.get(class_key)
        if existing is None or abs(
            current[
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score"
            ]
        ) > abs(
            existing[
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score"
            ]
        ):
            grouped[class_key] = current
    hotspots = list(grouped.values())
    if mode == "just-rerererestored":
        hotspots = [
            item
            for item in hotspots
            if item.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status"
            )
            == "just-rerererestored"
        ]
        hotspots.sort(
            key=lambda item: (
                -item.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs",
                    0,
                ),
                -abs(
                    item.get(
                        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score",
                        0.0,
                    )
                ),
                item.get("label", ""),
            )
        )
    elif mode == "holding":
        hotspots = [
            item
            for item in hotspots
            if item.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status"
            )
            in {
                "holding-confirmation-rebuild-reentry-rerererestore",
                "holding-clearance-rebuild-reentry-rerererestore",
                "sustained-confirmation-rebuild-reentry-rerererestore",
                "sustained-clearance-rebuild-reentry-rerererestore",
            }
        ]
        hotspots.sort(
            key=lambda item: (
                -item.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs",
                    0,
                ),
                -abs(
                    item.get(
                        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score",
                        0.0,
                    )
                ),
                item.get("label", ""),
            )
        )
    else:
        hotspots = [
            item
            for item in hotspots
            if item.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status"
            )
            in {"watch", "churn", "blocked"}
        ]
        hotspots.sort(
            key=lambda item: (
                -item.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score",
                    0.0,
                ),
                -item.get(
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs",
                    0,
                ),
                item.get("label", ""),
            )
        )
    return hotspots[:5]


def closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_summary(
    primary_target: dict[str, Any],
    just_rerererestored_rebuild_reentry_hotspots: list[dict[str, Any]],
    holding_reset_reentry_rebuild_reentry_restore_rerererestore_hotspots: list[
        dict[str, Any]
    ],
    *,
    target_label: Callable[[dict[str, Any]], str],
) -> str:
    label = target_label(primary_target) or "The current target"
    status = str(
        primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status",
            "none",
        )
    )
    age_runs = int(
        primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs",
            0,
        )
    )
    score = float(
        primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score",
            0.0,
        )
    )
    if status == "just-rerererestored":
        return (
            f"{label} has only just re-re-re-restored stronger re-re-restored posture, "
            f"so it is still fragile ({score:.2f}; {age_runs} run)."
        )
    if status == "holding-confirmation-rebuild-reentry-rerererestore":
        return (
            f"Confirmation-side re-re-re-restored posture for {label} has held long "
            f"enough to keep the stronger re-re-restored forecast in place "
            f"({score:.2f}; {age_runs} runs)."
        )
    if status == "holding-clearance-rebuild-reentry-rerererestore":
        return (
            f"Clearance-side re-re-re-restored posture for {label} has held long "
            f"enough to keep the stronger re-re-restored caution in place "
            f"({score:.2f}; {age_runs} runs)."
        )
    if status == "sustained-confirmation-rebuild-reentry-rerererestore":
        return (
            f"Confirmation-side re-re-re-restored posture for {label} is now holding "
            f"with enough follow-through to trust the stronger re-re-restored forecast "
            f"more ({score:.2f}; {age_runs} runs)."
        )
    if status == "sustained-clearance-rebuild-reentry-rerererestore":
        return (
            f"Clearance-side re-re-re-restored posture for {label} is now holding with "
            f"enough follow-through to trust the stronger re-re-restored caution more "
            f"({score:.2f}; {age_runs} runs)."
        )
    if status == "reversing":
        return (
            f"The re-re-re-restored rebuilt re-entry posture for {label} is already "
            f"weakening, so it is being softened again ({score:.2f})."
        )
    if status == "insufficient-data":
        return (
            f"Re-re-re-restored rebuilt re-entry for {label} is still too lightly "
            "exercised to say whether the stronger posture can hold."
        )
    if just_rerererestored_rebuild_reentry_hotspots:
        hotspot = just_rerererestored_rebuild_reentry_hotspots[0]
        return (
            "Newly re-re-re-restored posture is most fragile around "
            f"{hotspot.get('label', 'recent hotspots')}, so those classes still need "
            "follow-through before the stronger re-re-restored posture can be trusted."
        )
    if holding_reset_reentry_rebuild_reentry_restore_rerererestore_hotspots:
        hotspot = holding_reset_reentry_rebuild_reentry_restore_rerererestore_hotspots[0]
        return (
            "Re-re-re-restored posture is holding most cleanly around "
            f"{hotspot.get('label', 'recent hotspots')}, so those classes are closest "
            "to keeping the stronger re-re-restored posture safely."
        )
    return (
        "No re-re-re-restored rebuilt re-entry posture is active enough yet to judge "
        "whether it can hold."
    )


def closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_summary(
    primary_target: dict[str, Any],
    reset_reentry_rebuild_reentry_restore_rerererestore_churn_hotspots: list[
        dict[str, Any]
    ],
    *,
    target_label: Callable[[dict[str, Any]], str],
) -> str:
    label = target_label(primary_target) or "The current target"
    status = str(
        primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status",
            "none",
        )
    )
    score = float(
        primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score",
            0.0,
        )
    )
    if status == "watch":
        return (
            f"Re-re-re-restored rebuilt re-entry for {label} is wobbling enough that "
            f"stronger re-re-restored posture may soften soon ({score:.2f})."
        )
    if status == "churn":
        return (
            f"Re-re-re-restored rebuilt re-entry for {label} is flipping enough that "
            f"stronger re-re-restored posture should be softened quickly ({score:.2f})."
        )
    if status == "blocked":
        return str(
            primary_target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason",
                "Local target instability is preventing positive confirmation-side "
                f"re-re-re-restored hold for {label}.",
            )
        )
    if reset_reentry_rebuild_reentry_restore_rerererestore_churn_hotspots:
        hotspot = reset_reentry_rebuild_reentry_restore_rerererestore_churn_hotspots[0]
        return (
            "Re-re-re-restored rebuilt re-entry churn is highest around "
            f"{hotspot.get('label', 'recent hotspots')}, so stronger re-re-restored "
            "posture there should soften quickly if the wobble continues."
        )
    return "No meaningful re-re-re-restored rebuilt re-entry churn is active right now."


def apply_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_and_churn(
    resolution_targets: list[dict[str, Any]],
    history: list[dict[str, Any]],
    *,
    current_generated_at: str,
    confidence_calibration: dict[str, Any],
    recommendation_bucket: Callable[[dict[str, Any]], Any],
    class_closure_forecast_events: Callable[..., list[dict[str, Any]]],
    class_transition_events: Callable[..., list[dict[str, Any]]],
    target_class_transition_history: Callable[
        [dict[str, Any], list[dict[str, Any]]], dict[str, Any]
    ],
    closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_for_target: Callable[
        [dict[str, Any], list[dict[str, Any]], dict[str, Any]], dict[str, Any]
    ],
    closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_for_target: Callable[
        [dict[str, Any], list[dict[str, Any]], dict[str, Any]], dict[str, Any]
    ],
    apply_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_and_churn_control: Callable[
        ...,
        dict[str, Any],
    ],
    target_class_key: Callable[[dict[str, Any]], str],
    target_label: Callable[[dict[str, Any]], str],
    class_reset_reentry_rebuild_reentry_restore_rerererestore_window_runs: int,
) -> dict[str, Any]:
    del confidence_calibration
    if not resolution_targets:
        return {
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs": 0,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score": 0.0,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status": "none",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_reason": "",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_summary": "No reset re-entry rebuild re-entry restore re-re-re-restore persistence is recorded because there is no active target.",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_window_runs": class_reset_reentry_rebuild_reentry_restore_rerererestore_window_runs,
            "just_rerererestored_rebuild_reentry_hotspots": [],
            "holding_reset_reentry_rebuild_reentry_restore_rerererestore_hotspots": [],
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score": 0.0,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status": "none",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason": "",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_summary": "No reset re-entry rebuild re-entry restore re-re-re-restore churn is recorded because there is no active target.",
            "reset_reentry_rebuild_reentry_restore_rerererestore_churn_hotspots": [],
        }

    current_primary_target = resolution_targets[0]
    current_bucket = recommendation_bucket(current_primary_target)
    closure_forecast_events = class_closure_forecast_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )
    transition_events = class_transition_events(
        history,
        current_primary_target=current_primary_target,
        current_generated_at=current_generated_at,
    )

    updated_targets: list[dict[str, Any]] = []
    for target in resolution_targets:
        persistence_age_runs = 0
        persistence_score = 0.0
        persistence_status = "none"
        persistence_reason = ""
        persistence_path = ""
        churn_score = 0.0
        churn_status = "none"
        churn_reason = ""
        churn_path = ""
        closure_likely_outcome = str(
            target.get("transition_closure_likely_outcome", "none")
        )
        closure_hysteresis_status = str(
            target.get("closure_forecast_hysteresis_status", "none")
        )
        closure_hysteresis_reason = str(
            target.get("closure_forecast_hysteresis_reason", "")
        )
        transition_status = str(target.get("class_reweight_transition_status", "none"))
        transition_reason = str(target.get("class_reweight_transition_reason", ""))
        resolution_status = str(target.get("class_transition_resolution_status", "none"))
        resolution_reason = str(target.get("class_transition_resolution_reason", ""))
        reentry_status = str(
            target.get("closure_forecast_reset_reentry_rebuild_reentry_status", "none")
        )
        reentry_reason = str(
            target.get("closure_forecast_reset_reentry_rebuild_reentry_reason", "")
        )
        restore_status = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_status", "none"
            )
        )
        restore_reason = str(
            target.get("closure_forecast_reset_reentry_rebuild_reentry_restore_reason", "")
        )
        rerestore_status = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status",
                "none",
            )
        )
        rerestore_reason = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason",
                "",
            )
        )
        rererestore_status = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status",
                "none",
            )
        )
        rererestore_reason = str(
            target.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason",
                "",
            )
        )

        if recommendation_bucket(target) == current_bucket:
            transition_history_meta = target_class_transition_history(
                target,
                transition_events,
            )
            persistence_meta = (
                closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_for_target(
                    target,
                    closure_forecast_events,
                    transition_history_meta,
                )
            )
            churn_meta = (
                closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_for_target(
                    target,
                    closure_forecast_events,
                    transition_history_meta,
                )
            )
            persistence_age_runs = int(
                persistence_meta[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs"
                ]
            )
            persistence_score = float(
                persistence_meta[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score"
                ]
            )
            persistence_status = str(
                persistence_meta[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status"
                ]
            )
            persistence_reason = str(
                persistence_meta[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_reason"
                ]
            )
            persistence_path = str(
                persistence_meta[
                    "recent_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_path"
                ]
            )
            churn_score = float(
                churn_meta[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score"
                ]
            )
            churn_status = str(
                churn_meta[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status"
                ]
            )
            churn_reason = str(
                churn_meta[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason"
                ]
            )
            churn_path = str(
                churn_meta[
                    "recent_reset_reentry_rebuild_reentry_restore_rerererestore_churn_path"
                ]
            )
            control_updates = (
                apply_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_and_churn_control(
                    target,
                    persistence_meta=persistence_meta,
                    churn_meta=churn_meta,
                    transition_history_meta=transition_history_meta,
                    closure_likely_outcome=closure_likely_outcome,
                    closure_hysteresis_status=closure_hysteresis_status,
                    closure_hysteresis_reason=closure_hysteresis_reason,
                    transition_status=transition_status,
                    transition_reason=transition_reason,
                    resolution_status=resolution_status,
                    resolution_reason=resolution_reason,
                    reentry_status=reentry_status,
                    reentry_reason=reentry_reason,
                    restore_status=restore_status,
                    restore_reason=restore_reason,
                    rerestore_status=rerestore_status,
                    rerestore_reason=rerestore_reason,
                    rererestore_status=rererestore_status,
                    rererestore_reason=rererestore_reason,
                )
            )
            closure_likely_outcome = str(control_updates["transition_closure_likely_outcome"])
            closure_hysteresis_status = str(
                control_updates["closure_forecast_hysteresis_status"]
            )
            closure_hysteresis_reason = str(
                control_updates["closure_forecast_hysteresis_reason"]
            )
            transition_status = str(control_updates["class_reweight_transition_status"])
            transition_reason = str(control_updates["class_reweight_transition_reason"])
            resolution_status = str(control_updates["class_transition_resolution_status"])
            resolution_reason = str(control_updates["class_transition_resolution_reason"])
            reentry_status = str(
                control_updates["closure_forecast_reset_reentry_rebuild_reentry_status"]
            )
            reentry_reason = str(
                control_updates["closure_forecast_reset_reentry_rebuild_reentry_reason"]
            )
            restore_status = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_status"
                ]
            )
            restore_reason = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_reason"
                ]
            )
            rerestore_status = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status"
                ]
            )
            rerestore_reason = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason"
                ]
            )
            rererestore_status = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status"
                ]
            )
            rererestore_reason = str(
                control_updates[
                    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason"
                ]
            )

        updated_targets.append(
            {
                **target,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs": persistence_age_runs,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score": persistence_score,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status": persistence_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_reason": persistence_reason,
                "recent_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_path": persistence_path,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score": churn_score,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status": churn_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason": churn_reason,
                "recent_reset_reentry_rebuild_reentry_restore_rerererestore_churn_path": churn_path,
                "transition_closure_likely_outcome": closure_likely_outcome,
                "closure_forecast_hysteresis_status": closure_hysteresis_status,
                "closure_forecast_hysteresis_reason": closure_hysteresis_reason,
                "class_reweight_transition_status": transition_status,
                "class_reweight_transition_reason": transition_reason,
                "class_transition_resolution_status": resolution_status,
                "class_transition_resolution_reason": resolution_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_status": reentry_status,
                "closure_forecast_reset_reentry_rebuild_reentry_reason": reentry_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_status": restore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_reason": restore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": rerestore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": rerestore_reason,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": rererestore_status,
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": rererestore_reason,
            }
        )

    resolution_targets[:] = updated_targets
    primary_target = resolution_targets[0]
    just_hotspots = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_hotspots(
            resolution_targets,
            mode="just-rerererestored",
            target_class_key=target_class_key,
        )
    )
    holding_hotspots = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_hotspots(
            resolution_targets,
            mode="holding",
            target_class_key=target_class_key,
        )
    )
    churn_hotspots = (
        closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_hotspots(
            resolution_targets,
            mode="churn",
            target_class_key=target_class_key,
        )
    )
    return {
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs",
            0,
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score",
            0.0,
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status",
            "none",
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_reason",
            "",
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_summary": (
            closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_summary(
                primary_target,
                just_hotspots,
                holding_hotspots,
                target_label=target_label,
            )
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_window_runs": class_reset_reentry_rebuild_reentry_restore_rerererestore_window_runs,
        "just_rerererestored_rebuild_reentry_hotspots": just_hotspots,
        "holding_reset_reentry_rebuild_reentry_restore_rerererestore_hotspots": holding_hotspots,
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score",
            0.0,
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status",
            "none",
        ),
        "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason": primary_target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason",
            "",
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_summary": (
            closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_summary(
                primary_target,
                churn_hotspots,
                target_label=target_label,
            )
        ),
        "reset_reentry_rebuild_reentry_restore_rerererestore_churn_hotspots": churn_hotspots,
    }


__all__ = (
    "closure_forecast_reset_side_from_status",
    "closure_forecast_reset_refresh_path_label",
    "closure_forecast_reset_refresh_recovery_for_target",
    "apply_reset_refresh_reentry_control",
    "closure_forecast_reset_refresh_hotspots",
    "closure_forecast_reset_refresh_recovery_summary",
    "closure_forecast_reset_reentry_summary",
    "closure_forecast_reset_reentry_freshness_for_target",
    "apply_reset_reentry_freshness_reset_control",
    "closure_forecast_reset_reentry_freshness_hotspots",
    "closure_forecast_reset_reentry_freshness_summary",
    "closure_forecast_reset_reentry_reset_summary",
    "closure_forecast_reset_reentry_refresh_recovery_for_target",
    "apply_reset_reentry_refresh_rebuild_control",
    "closure_forecast_reset_reentry_refresh_hotspots",
    "closure_forecast_reset_reentry_refresh_recovery_summary",
    "closure_forecast_reset_reentry_rebuild_summary",
    "closure_forecast_reset_reentry_rebuild_freshness_for_target",
    "apply_reset_reentry_rebuild_freshness_reset_control",
    "closure_forecast_reset_reentry_rebuild_freshness_hotspots",
    "closure_forecast_reset_reentry_rebuild_freshness_summary",
    "closure_forecast_reset_reentry_rebuild_reset_summary",
    "apply_reset_reentry_rebuild_freshness_and_reset",
    "closure_forecast_reset_reentry_rebuild_persistence_for_target",
    "closure_forecast_reset_reentry_rebuild_churn_for_target",
    "apply_reset_reentry_rebuild_persistence_and_churn_control",
    "closure_forecast_reset_reentry_rebuild_hotspots",
    "closure_forecast_reset_reentry_rebuild_persistence_summary",
    "closure_forecast_reset_reentry_rebuild_churn_summary",
    "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_for_target",
    "apply_reset_reentry_rebuild_reentry_refresh_restore_control",
    "closure_forecast_reset_reentry_rebuild_reentry_refresh_hotspots",
    "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_summary",
    "closure_forecast_reset_reentry_rebuild_reentry_restore_summary",
    "apply_reset_reentry_rebuild_reentry_refresh_recovery_and_restore",
    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_for_target",
    "apply_reset_reentry_rebuild_reentry_restore_rererestore_freshness_reset_control",
    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_hotspots",
    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_summary",
    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_summary",
    "apply_reset_reentry_rebuild_reentry_restore_rererestore_freshness_and_reset",
    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_for_target",
    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_for_target",
    "apply_reset_reentry_rebuild_reentry_restore_rererestore_persistence_and_churn_control",
    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_hotspots",
    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_summary",
    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_summary",
    "apply_reset_reentry_rebuild_reentry_restore_rererestore_persistence_and_churn",
    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_for_target",
    "apply_reset_reentry_rebuild_reentry_restore_rererestore_refresh_rerererestore_control",
    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_hotspots",
    "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_summary",
    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_summary",
    "apply_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_and_rerererestore",
    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_text",
    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_for_target",
    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_for_target",
    "apply_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_and_churn_control",
    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_hotspots",
    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_summary",
    "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_summary",
    "apply_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_and_churn",
)
