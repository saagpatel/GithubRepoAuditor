from __future__ import annotations

from typing import Any

from src.operator_trend_closure_forecast_freshness_controls import (
    closure_forecast_event_has_evidence,
    closure_forecast_freshness_status,
)
from src.operator_trend_support import (
    CLASS_CLOSURE_FORECAST_REFRESH_WINDOW_RUNS,
    CLASS_MEMORY_RECENCY_WEIGHTS,
    CLASS_REACQUISITION_FRESHNESS_WINDOW_RUNS,
    CLASS_REACQUISITION_PERSISTENCE_WINDOW_RUNS,
    HISTORY_WINDOW_RUNS,
    clamp_round,
    class_direction_flip_count,
    closure_forecast_direction_majority,
    closure_forecast_direction_reversing,
    normalized_closure_forecast_direction,
    target_class_key,
    target_label,
    target_specific_normalization_noise,
)


def closure_forecast_refresh_signal_from_event(
    event: dict[str, Any],
) -> float:
    score = float(event.get("closure_forecast_reweight_score", 0.0) or 0.0)
    direction = normalized_closure_forecast_direction(
        str(event.get("closure_forecast_reweight_direction", "neutral")),
        score,
    )
    freshness_factor = {
        "fresh": 1.00,
        "mixed-age": 0.60,
        "stale": 0.25,
        "insufficient-data": 0.10,
    }.get(
        str(event.get("closure_forecast_freshness_status", "insufficient-data")), 0.10
    )
    signal_strength = max(abs(score), 0.05) if direction != "neutral" else 0.0
    if direction == "supporting-confirmation":
        return signal_strength * freshness_factor
    if direction == "supporting-clearance":
        return -signal_strength * freshness_factor
    return 0.0


def recent_closure_forecast_weakened_side(events: list[dict[str, Any]]) -> str:
    for event in events:
        decay_status = str(event.get("closure_forecast_decay_status", "none") or "none")
        freshness_status = str(
            event.get("closure_forecast_freshness_status", "insufficient-data")
            or "insufficient-data"
        )
        hysteresis_status = str(
            event.get("closure_forecast_hysteresis_status", "none") or "none"
        )
        if decay_status == "confirmation-decayed" or (
            freshness_status in {"stale", "insufficient-data"}
            and hysteresis_status in {"pending-confirmation", "confirmed-confirmation"}
        ):
            return "confirmation"
        if decay_status == "clearance-decayed" or (
            freshness_status in {"stale", "insufficient-data"}
            and hysteresis_status in {"pending-clearance", "confirmed-clearance"}
        ):
            return "clearance"
    return "none"


def closure_forecast_refresh_path_label(
    event: dict[str, Any],
) -> str:
    direction = normalized_closure_forecast_direction(
        str(event.get("closure_forecast_reweight_direction", "neutral")),
        float(event.get("closure_forecast_reweight_score", 0.0) or 0.0),
    )
    freshness = str(
        event.get("closure_forecast_freshness_status", "insufficient-data")
        or "insufficient-data"
    )
    if direction == "supporting-confirmation":
        return f"{freshness} confirmation"
    if direction == "supporting-clearance":
        return f"{freshness} clearance"
    return "neutral"


def closure_forecast_refresh_recovery_for_target(
    target: dict[str, Any],
    closure_forecast_events: list[dict[str, Any]],
    transition_history_meta: dict[str, Any],
) -> dict[str, Any]:
    class_key = target_class_key(target)
    matching_events = [
        event
        for event in closure_forecast_events
        if event.get("class_key") == class_key
    ][:CLASS_CLOSURE_FORECAST_REFRESH_WINDOW_RUNS]
    relevant_events = [
        event for event in matching_events if closure_forecast_event_has_evidence(event)
    ]
    directions = [
        normalized_closure_forecast_direction(
            str(event.get("closure_forecast_reweight_direction", "neutral")),
            float(event.get("closure_forecast_reweight_score", 0.0) or 0.0),
        )
        for event in matching_events
    ]
    weighted_total = 0.0
    weight_sum = 0.0
    for index, event in enumerate(matching_events):
        weight = (1.0, 0.8, 0.6, 0.4)[
            min(index, CLASS_CLOSURE_FORECAST_REFRESH_WINDOW_RUNS - 1)
        ]
        weighted_total += closure_forecast_refresh_signal_from_event(event) * weight
        weight_sum += weight
    refresh_recovery_score = clamp_round(
        weighted_total / max(weight_sum, 1.0),
        lower=-0.95,
        upper=0.95,
    )
    current_direction = directions[0] if directions else "neutral"
    earlier_majority = closure_forecast_direction_majority(directions[1:])
    recent_weakened = recent_closure_forecast_weakened_side(matching_events)
    freshness_status = str(
        target.get("closure_forecast_freshness_status", "insufficient-data")
    )
    momentum_status = str(
        target.get("closure_forecast_momentum_status", "insufficient-data")
    )
    stability_status = str(target.get("closure_forecast_stability_status", "watch"))
    local_noise = target_specific_normalization_noise(target, transition_history_meta)

    if len(relevant_events) < 2 or recent_weakened == "none":
        refresh_recovery_status = "none"
    elif local_noise and current_direction == "supporting-confirmation":
        refresh_recovery_status = "blocked"
    elif (
        (
            recent_weakened == "confirmation"
            and current_direction == "supporting-clearance"
        )
        or (
            recent_weakened == "clearance"
            and current_direction == "supporting-confirmation"
        )
        or closure_forecast_direction_reversing(current_direction, earlier_majority)
    ):
        refresh_recovery_status = "reversing"
    elif (
        recent_weakened == "confirmation"
        and current_direction == "supporting-confirmation"
        and freshness_status == "fresh"
        and refresh_recovery_score >= 0.25
        and stability_status != "oscillating"
    ):
        refresh_recovery_status = "reacquiring-confirmation"
    elif (
        recent_weakened == "clearance"
        and current_direction == "supporting-clearance"
        and freshness_status == "fresh"
        and refresh_recovery_score <= -0.25
        and stability_status != "oscillating"
    ):
        refresh_recovery_status = "reacquiring-clearance"
    elif (
        recent_weakened == "confirmation"
        and current_direction == "supporting-confirmation"
        and freshness_status in {"fresh", "mixed-age"}
        and refresh_recovery_score >= 0.15
    ):
        refresh_recovery_status = "recovering-confirmation"
    elif (
        recent_weakened == "clearance"
        and current_direction == "supporting-clearance"
        and freshness_status in {"fresh", "mixed-age"}
        and refresh_recovery_score <= -0.15
    ):
        refresh_recovery_status = "recovering-clearance"
    else:
        refresh_recovery_status = "none"

    if local_noise and current_direction == "supporting-confirmation":
        reacquisition_status = "blocked"
        reacquisition_reason = "Local target instability is still preventing positive confirmation-side reacquisition."
    elif (
        refresh_recovery_status == "reacquiring-confirmation"
        and freshness_status == "fresh"
        and momentum_status == "sustained-confirmation"
        and stability_status == "stable"
        and not local_noise
    ):
        reacquisition_status = "reacquired-confirmation"
        reacquisition_reason = (
            "Fresh confirmation-side support has stayed strong enough to earn back stronger "
            "confirmation forecasting."
        )
    elif (
        refresh_recovery_status == "reacquiring-clearance"
        and freshness_status == "fresh"
        and momentum_status == "sustained-clearance"
        and stability_status == "stable"
    ):
        reacquisition_status = "reacquired-clearance"
        reacquisition_reason = (
            "Fresh clearance-side pressure has stayed strong enough to earn back stronger "
            "clearance forecasting."
        )
    elif refresh_recovery_status in {
        "recovering-confirmation",
        "reacquiring-confirmation",
    }:
        reacquisition_status = "pending-confirmation-reacquisition"
        reacquisition_reason = (
            "Fresh confirmation-side forecast evidence is returning, but it has not fully "
            "re-earned stronger carry-forward yet."
        )
    elif refresh_recovery_status in {"recovering-clearance", "reacquiring-clearance"}:
        reacquisition_status = "pending-clearance-reacquisition"
        reacquisition_reason = (
            "Fresh clearance-side forecast evidence is returning, but it has not fully "
            "re-earned stronger carry-forward yet."
        )
    else:
        reacquisition_status = "none"
        reacquisition_reason = ""

    if refresh_recovery_status == "reversing":
        reacquisition_reason = (
            "The fresh recovery attempt is changing direction, so stronger carry-forward "
            "stays softened."
        )

    return {
        "closure_forecast_refresh_recovery_score": refresh_recovery_score,
        "closure_forecast_refresh_recovery_status": refresh_recovery_status,
        "closure_forecast_reacquisition_status": reacquisition_status,
        "closure_forecast_reacquisition_reason": reacquisition_reason,
        "recent_closure_forecast_refresh_path": " -> ".join(
            closure_forecast_refresh_path_label(event)
            for event in matching_events
            if event
        ),
        "recent_weakened_side": recent_weakened,
    }


def apply_closure_forecast_reacquisition_control(
    target: dict[str, Any],
    *,
    refresh_meta: dict[str, Any],
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
) -> tuple[str, str, str, str, str, str, str, str, str, str, str, str, str, str, str]:
    refresh_status = str(
        refresh_meta.get("closure_forecast_refresh_recovery_status", "none")
    )
    reacquisition_status = str(
        refresh_meta.get("closure_forecast_reacquisition_status", "none")
    )
    reacquisition_reason = str(
        refresh_meta.get("closure_forecast_reacquisition_reason", "")
    )
    recent_weakened_side = str(refresh_meta.get("recent_weakened_side", "none"))
    freshness_status = str(
        target.get("closure_forecast_freshness_status", "insufficient-data")
    )
    stability_status = str(target.get("closure_forecast_stability_status", "watch"))
    decayed_clearance_rate = float(
        target.get("decayed_clearance_forecast_rate", 0.0) or 0.0
    )
    transition_age_runs = int(target.get("class_transition_age_runs", 0) or 0)

    if reacquisition_status == "reacquired-confirmation":
        closure_likely_outcome = "confirm-soon"
        closure_hysteresis_status = "confirmed-confirmation"
        closure_hysteresis_reason = reacquisition_reason
    elif reacquisition_status == "pending-confirmation-reacquisition":
        closure_likely_outcome = "hold"
        if recent_weakened_side == "confirmation":
            closure_hysteresis_status = "pending-confirmation"
            closure_hysteresis_reason = reacquisition_reason
    elif reacquisition_status == "reacquired-clearance":
        if closure_likely_outcome == "hold":
            closure_likely_outcome = "clear-risk"
        elif closure_likely_outcome == "clear-risk" and transition_age_runs >= 3:
            closure_likely_outcome = "expire-risk"
        closure_hysteresis_status = "confirmed-clearance"
        closure_hysteresis_reason = reacquisition_reason
        if (
            transition_status in {"pending-support", "pending-caution"}
            and decayed_clearance_rate >= 0.50
            and stability_status != "oscillating"
        ):
            clear_reason = (
                "Fresh clearance-side pressure has stayed strong enough to re-earn the "
                "earlier forecast-driven clearance posture."
            )
            resolution_status = "cleared"
            resolution_reason = clear_reason
            transition_status = "none"
            transition_reason = clear_reason
            if target.get("class_reweight_transition_status") == "pending-support":
                reverted_policy = target.get(
                    "pre_class_normalization_trust_policy", trust_policy
                )
                reverted_reason = target.get(
                    "pre_class_normalization_trust_policy_reason",
                    trust_policy_reason,
                )
                trust_policy = str(reverted_policy)
                trust_policy_reason = (
                    clear_reason
                    if reverted_policy == "verify-first"
                    else str(reverted_reason)
                )
                class_normalization_status = "candidate"
                class_normalization_reason = clear_reason
            else:
                pending_debt_status = pending_debt_status or "watch"
                pending_debt_reason = pending_debt_reason or clear_reason
                policy_debt_status = "watch"
                policy_debt_reason = clear_reason
    elif reacquisition_status == "pending-clearance-reacquisition":
        if recent_weakened_side == "clearance":
            closure_hysteresis_status = "pending-clearance"
            closure_hysteresis_reason = reacquisition_reason
    elif reacquisition_status == "blocked":
        closure_hysteresis_reason = reacquisition_reason or closure_hysteresis_reason
    elif refresh_status == "reversing":
        closure_hysteresis_reason = reacquisition_reason or closure_hysteresis_reason

    if freshness_status in {
        "stale",
        "insufficient-data",
    } and reacquisition_status.startswith("reacquired"):
        if reacquisition_status == "reacquired-confirmation":
            closure_likely_outcome = "hold"
            closure_hysteresis_status = "pending-confirmation"
        elif closure_likely_outcome == "expire-risk":
            closure_likely_outcome = "clear-risk"
        elif closure_likely_outcome == "clear-risk":
            closure_likely_outcome = "hold"
            closure_hysteresis_status = "pending-clearance"

    return (
        closure_likely_outcome,
        closure_hysteresis_status,
        closure_hysteresis_reason,
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
    )


def closure_forecast_refresh_hotspots(
    resolution_targets: list[dict[str, Any]],
    *,
    mode: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for target in resolution_targets:
        class_key = target_class_key(target)
        if not class_key:
            continue
        current = {
            "scope": "class",
            "label": class_key,
            "closure_forecast_refresh_recovery_score": target.get(
                "closure_forecast_refresh_recovery_score",
                0.0,
            ),
            "closure_forecast_refresh_recovery_status": target.get(
                "closure_forecast_refresh_recovery_status",
                "none",
            ),
            "closure_forecast_reacquisition_status": target.get(
                "closure_forecast_reacquisition_status",
                "none",
            ),
            "recent_closure_forecast_refresh_path": target.get(
                "recent_closure_forecast_refresh_path",
                "",
            ),
        }
        existing = grouped.get(class_key)
        if existing is None or abs(
            float(current["closure_forecast_refresh_recovery_score"] or 0.0)
        ) > abs(float(existing["closure_forecast_refresh_recovery_score"] or 0.0)):
            grouped[class_key] = current

    hotspots = list(grouped.values())
    if mode == "confirmation":
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_refresh_recovery_status")
            in {"recovering-confirmation", "reacquiring-confirmation"}
            or item.get("closure_forecast_reacquisition_status")
            in {"pending-confirmation-reacquisition", "reacquired-confirmation"}
        ]
        hotspots.sort(
            key=lambda item: (
                -float(item.get("closure_forecast_refresh_recovery_score", 0.0) or 0.0),
                str(item.get("label", "")),
            )
        )
    else:
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_refresh_recovery_status")
            in {"recovering-clearance", "reacquiring-clearance"}
            or item.get("closure_forecast_reacquisition_status")
            in {"pending-clearance-reacquisition", "reacquired-clearance"}
        ]
        hotspots.sort(
            key=lambda item: (
                float(item.get("closure_forecast_refresh_recovery_score", 0.0) or 0.0),
                str(item.get("label", "")),
            )
        )
    return hotspots[:5]


def closure_forecast_refresh_recovery_summary(
    primary_target: dict[str, Any],
    recovering_confirmation_hotspots: list[dict[str, Any]],
    recovering_clearance_hotspots: list[dict[str, Any]],
) -> str:
    label = target_label(primary_target) or "The current target"
    status = str(primary_target.get("closure_forecast_refresh_recovery_status", "none"))
    score = float(
        primary_target.get("closure_forecast_refresh_recovery_score", 0.0) or 0.0
    )
    if status == "recovering-confirmation":
        return (
            f"Fresh confirmation-side forecast evidence is returning for {label}, but it has "
            f"not fully re-earned stronger carry-forward yet ({score:.2f})."
        )
    if status == "recovering-clearance":
        return (
            f"Fresh clearance-side forecast evidence is returning for {label}, but it has "
            f"not fully re-earned stronger carry-forward yet ({score:.2f})."
        )
    if status == "reacquiring-confirmation":
        return (
            f"Fresh confirmation-side support around {label} is strong enough that stronger "
            f"forecast carry-forward may be earned back soon ({score:.2f})."
        )
    if status == "reacquiring-clearance":
        return (
            f"Fresh clearance-side pressure around {label} is strong enough that stronger "
            f"forecast carry-forward may be earned back soon ({score:.2f})."
        )
    if status == "reversing":
        return (
            f"The fresh recovery attempt around {label} is changing direction, so stronger "
            f"carry-forward stays softened ({score:.2f})."
        )
    if status == "blocked":
        return (
            f"Local target instability is still preventing positive confirmation-side "
            f"reacquisition for {label}."
        )
    if recovering_confirmation_hotspots:
        hotspot = recovering_confirmation_hotspots[0]
        return (
            f"Confirmation-side refresh recovery is strongest around "
            f"{hotspot.get('label', 'recent hotspots')}, but the current target has not "
            "re-earned stronger carry-forward yet."
        )
    if recovering_clearance_hotspots:
        hotspot = recovering_clearance_hotspots[0]
        return (
            f"Clearance-side refresh recovery is strongest around "
            f"{hotspot.get('label', 'recent hotspots')}, so those classes are closest to "
            "re-earning stronger clearance forecasting."
        )
    return "No closure-forecast refresh recovery is strong enough yet to re-earn stronger carry-forward."


def closure_forecast_reacquisition_summary(
    primary_target: dict[str, Any],
    recovering_confirmation_hotspots: list[dict[str, Any]],
    recovering_clearance_hotspots: list[dict[str, Any]],
) -> str:
    label = target_label(primary_target) or "The current target"
    status = str(primary_target.get("closure_forecast_reacquisition_status", "none"))
    reason = str(primary_target.get("closure_forecast_reacquisition_reason", ""))
    if status == "reacquired-confirmation":
        return (
            reason
            or f"Fresh confirmation-side support has stayed strong enough to earn back "
            f"stronger confirmation forecasting for {label}."
        )
    if status == "reacquired-clearance":
        return (
            reason
            or f"Fresh clearance-side pressure has stayed strong enough to earn back stronger "
            f"clearance forecasting for {label}."
        )
    if status == "pending-confirmation-reacquisition":
        return (
            reason
            or f"Confirmation-side recovery is visible for {label}, but stronger "
            "carry-forward has not been fully re-earned yet."
        )
    if status == "pending-clearance-reacquisition":
        return (
            reason
            or f"Clearance-side recovery is visible for {label}, but stronger carry-forward "
            "has not been fully re-earned yet."
        )
    if status == "blocked":
        return (
            reason
            or f"Local target instability is still preventing positive confirmation-side "
            f"reacquisition for {label}."
        )
    if recovering_confirmation_hotspots:
        hotspot = recovering_confirmation_hotspots[0]
        return (
            f"Confirmation-side reacquisition is most active around "
            f"{hotspot.get('label', 'recent hotspots')}, but those classes still need fresh, "
            "stable follow-through before stronger carry-forward is restored."
        )
    if recovering_clearance_hotspots:
        hotspot = recovering_clearance_hotspots[0]
        return (
            f"Clearance-side reacquisition is most active around "
            f"{hotspot.get('label', 'recent hotspots')}, so those classes can only restore "
            "stronger clearance posture when fresh pressure keeps holding."
        )
    return "No closure-forecast reacquisition is re-earning stronger carry-forward right now."


def closure_forecast_reacquisition_side_from_event(event: dict[str, Any]) -> str:
    reacquisition_status = str(
        event.get("closure_forecast_reacquisition_status", "none") or "none"
    )
    if reacquisition_status in {
        "pending-confirmation-reacquisition",
        "reacquired-confirmation",
    }:
        return "confirmation"
    if reacquisition_status in {
        "pending-clearance-reacquisition",
        "reacquired-clearance",
    }:
        return "clearance"
    refresh_status = str(
        event.get("closure_forecast_refresh_recovery_status", "none") or "none"
    )
    if refresh_status in {"recovering-confirmation", "reacquiring-confirmation"}:
        return "confirmation"
    if refresh_status in {"recovering-clearance", "reacquiring-clearance"}:
        return "clearance"
    return "none"


def closure_forecast_reacquisition_side_from_status(status: str) -> str:
    if status in {
        "holding-confirmation",
        "sustained-confirmation",
        "pending-confirmation",
        "confirmed-confirmation",
    }:
        return "confirmation"
    if status in {
        "holding-clearance",
        "sustained-clearance",
        "pending-clearance",
        "confirmed-clearance",
    }:
        return "clearance"
    return "none"


def closure_forecast_reacquisition_path_label(event: dict[str, Any]) -> str:
    status = str(event.get("closure_forecast_reacquisition_status", "none") or "none")
    if status != "none":
        return status
    likely_outcome = str(
        event.get("transition_closure_likely_outcome", "none") or "none"
    )
    if likely_outcome != "none":
        return likely_outcome
    return "hold"


def closure_forecast_reacquisition_persistence_for_target(
    target: dict[str, Any],
    closure_forecast_events: list[dict[str, Any]],
    transition_history_meta: dict[str, Any],
) -> dict[str, Any]:
    del transition_history_meta
    class_key = target_class_key(target)
    matching_events = [
        event
        for event in closure_forecast_events
        if event.get("class_key") == class_key
    ][:CLASS_REACQUISITION_PERSISTENCE_WINDOW_RUNS]
    relevant_events = [
        event
        for event in matching_events
        if closure_forecast_reacquisition_side_from_event(event) != "none"
    ]
    current_side = (
        closure_forecast_reacquisition_side_from_event(matching_events[0])
        if matching_events
        else "none"
    )
    persistence_age_runs = 0
    for event in matching_events:
        event_side = closure_forecast_reacquisition_side_from_event(event)
        if event_side != current_side or event_side == "none":
            break
        persistence_age_runs += 1

    weighted_total = 0.0
    weight_sum = 0.0
    sides: list[str] = []
    for index, event in enumerate(
        relevant_events[:CLASS_REACQUISITION_PERSISTENCE_WINDOW_RUNS]
    ):
        weight = (1.0, 0.8, 0.6, 0.4)[
            min(index, CLASS_REACQUISITION_PERSISTENCE_WINDOW_RUNS - 1)
        ]
        event_side = closure_forecast_reacquisition_side_from_event(event)
        sign = 1.0 if event_side == "confirmation" else -1.0
        sides.append("supporting-confirmation" if sign > 0 else "supporting-clearance")
        magnitude = 0.0
        if event.get("closure_forecast_reacquisition_status", "none") in {
            "reacquired-confirmation",
            "reacquired-clearance",
        }:
            magnitude += 0.15
        momentum_status = str(
            event.get("closure_forecast_momentum_status", "insufficient-data")
        )
        if (
            event_side == "confirmation" and momentum_status == "sustained-confirmation"
        ) or (event_side == "clearance" and momentum_status == "sustained-clearance"):
            magnitude += 0.10
        stability_status = str(event.get("closure_forecast_stability_status", "watch"))
        if stability_status == "stable":
            magnitude += 0.10
        freshness_status = str(
            event.get("closure_forecast_freshness_status", "insufficient-data")
        )
        if freshness_status == "fresh":
            magnitude += 0.10
        elif freshness_status == "mixed-age":
            magnitude = max(0.0, magnitude - 0.10)
        if momentum_status in {"reversing", "unstable"}:
            magnitude = max(0.0, magnitude - 0.15)
        if stability_status == "oscillating":
            magnitude = max(0.0, magnitude - 0.15)
        if event.get("closure_forecast_decay_status", "none") != "none":
            magnitude = max(0.0, magnitude - 0.15)
        weighted_total += sign * magnitude * weight
        weight_sum += weight

    persistence_score = clamp_round(
        weighted_total / max(weight_sum, 1.0), lower=-0.95, upper=0.95
    )
    current_momentum_status = str(
        target.get("closure_forecast_momentum_status", "insufficient-data")
    )
    current_stability_status = str(
        target.get("closure_forecast_stability_status", "watch")
    )
    current_freshness_status = str(
        target.get("closure_forecast_freshness_status", "insufficient-data")
    )
    earlier_majority = closure_forecast_direction_majority(sides[1:])
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
        target.get("closure_forecast_reacquisition_status", "none")
        in {"reacquired-confirmation", "reacquired-clearance"}
        and persistence_age_runs == 1
    ):
        persistence_status = "just-reacquired"
    elif len(relevant_events) < 2:
        persistence_status = "insufficient-data"
    elif (
        closure_forecast_direction_reversing(current_direction, earlier_majority)
        or current_momentum_status in {"reversing", "unstable"}
        or target.get("closure_forecast_decay_status", "none") != "none"
    ):
        persistence_status = "reversing"
    elif (
        current_side == "confirmation"
        and persistence_age_runs >= 3
        and current_freshness_status == "fresh"
        and current_momentum_status == "sustained-confirmation"
        and current_stability_status != "oscillating"
    ):
        persistence_status = "sustained-confirmation"
    elif (
        current_side == "clearance"
        and persistence_age_runs >= 3
        and current_freshness_status == "fresh"
        and current_momentum_status == "sustained-clearance"
        and current_stability_status != "oscillating"
    ):
        persistence_status = "sustained-clearance"
    elif (
        current_side == "confirmation"
        and persistence_age_runs >= 2
        and persistence_score > 0
    ):
        persistence_status = "holding-confirmation"
    elif (
        current_side == "clearance"
        and persistence_age_runs >= 2
        and persistence_score < 0
    ):
        persistence_status = "holding-clearance"
    else:
        persistence_status = "none"

    if persistence_status == "just-reacquired":
        persistence_reason = "Stronger closure-forecast posture has returned, but it has not yet proved it can hold."
    elif persistence_status == "holding-confirmation":
        persistence_reason = (
            "Confirmation-side recovery has stayed aligned long enough to keep the restored "
            "forecast in place."
        )
    elif persistence_status == "holding-clearance":
        persistence_reason = (
            "Clearance-side recovery has stayed aligned long enough to keep the restored "
            "forecast in place."
        )
    elif persistence_status == "sustained-confirmation":
        persistence_reason = (
            "Confirmation-side reacquisition is now holding with enough follow-through to trust "
            "the restored forecast more."
        )
    elif persistence_status == "sustained-clearance":
        persistence_reason = (
            "Clearance-side reacquisition is now holding with enough follow-through to trust "
            "the restored caution more."
        )
    elif persistence_status == "reversing":
        persistence_reason = "The restored forecast posture is already weakening, so it is being softened again."
    elif persistence_status == "insufficient-data":
        persistence_reason = (
            "Reacquisition is still too lightly exercised to say whether the restored forecast "
            "can hold."
        )
    else:
        persistence_reason = ""

    return {
        "closure_forecast_reacquisition_age_runs": persistence_age_runs,
        "closure_forecast_reacquisition_persistence_score": persistence_score,
        "closure_forecast_reacquisition_persistence_status": persistence_status,
        "closure_forecast_reacquisition_persistence_reason": persistence_reason,
        "recent_reacquisition_persistence_path": " -> ".join(
            closure_forecast_reacquisition_path_label(event)
            for event in matching_events
            if event
        ),
    }


def closure_forecast_recovery_churn_for_target(
    target: dict[str, Any],
    closure_forecast_events: list[dict[str, Any]],
    transition_history_meta: dict[str, Any],
) -> dict[str, Any]:
    class_key = target_class_key(target)
    matching_events = [
        event
        for event in closure_forecast_events
        if event.get("class_key") == class_key
    ][:CLASS_REACQUISITION_PERSISTENCE_WINDOW_RUNS]
    side_path = [
        closure_forecast_reacquisition_side_from_event(event)
        for event in matching_events
        if closure_forecast_reacquisition_side_from_event(event) != "none"
    ]
    current_side = side_path[0] if side_path else "none"
    local_noise = target_specific_normalization_noise(target, transition_history_meta)
    if current_side == "none":
        churn_status = "none"
        churn_reason = ""
        churn_score = 0.0
    else:
        flip_count = class_direction_flip_count(
            [
                "supporting-confirmation"
                if side == "confirmation"
                else "supporting-clearance"
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
            str(event.get("closure_forecast_freshness_status", "insufficient-data"))
            for event in matching_events
        ]
        if any(
            previous == "fresh"
            and current in {"mixed-age", "stale", "insufficient-data"}
            for previous, current in zip(freshness_path, freshness_path[1:])
        ):
            churn_score += 0.10
        if target.get("closure_forecast_decay_status", "none") != "none":
            churn_score += 0.10
        if (
            len(side_path) >= 2
            and side_path[0] == side_path[1]
            and matching_events[0].get(
                "closure_forecast_freshness_status", "insufficient-data"
            )
            == "fresh"
            and matching_events[1].get(
                "closure_forecast_freshness_status", "insufficient-data"
            )
            == "fresh"
        ):
            churn_score -= 0.10
        churn_score = clamp_round(churn_score, lower=0.0, upper=0.95)
        if local_noise and current_side == "confirmation":
            churn_status = "blocked"
            churn_reason = "Local target instability is preventing positive confirmation-side persistence."
        elif churn_score >= 0.45 or flip_count >= 2:
            churn_status = "churn"
            churn_reason = (
                "Recovery is flipping enough that restored forecast posture should be "
                "softened quickly."
            )
        elif churn_score >= 0.20:
            churn_status = "watch"
            churn_reason = (
                "Recovery is wobbling and may lose its restored strength soon."
            )
        else:
            churn_status = "none"
            churn_reason = ""
    return {
        "closure_forecast_recovery_churn_score": churn_score,
        "closure_forecast_recovery_churn_status": churn_status,
        "closure_forecast_recovery_churn_reason": churn_reason,
        "recent_recovery_churn_path": " -> ".join(
            closure_forecast_reacquisition_path_label(event)
            for event in matching_events
            if event
        ),
    }


def apply_reacquisition_persistence_and_churn_control(
    target: dict[str, Any],
    *,
    persistence_meta: dict[str, Any],
    churn_meta: dict[str, Any],
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
) -> tuple[str, str, str, str, str, str, str, str, str, str, str, str, str, str, str]:
    persistence_status = str(
        persistence_meta.get(
            "closure_forecast_reacquisition_persistence_status", "none"
        )
    )
    persistence_reason = str(
        persistence_meta.get("closure_forecast_reacquisition_persistence_reason", "")
    )
    churn_status = str(churn_meta.get("closure_forecast_recovery_churn_status", "none"))
    churn_reason = str(churn_meta.get("closure_forecast_recovery_churn_reason", ""))
    current_reacquisition_status = str(
        target.get("closure_forecast_reacquisition_status", "none")
    )
    current_freshness_status = str(
        target.get("closure_forecast_freshness_status", "insufficient-data")
    )
    transition_age_runs = int(target.get("class_transition_age_runs", 0) or 0)
    recent_pending_status = str(
        transition_history_meta.get("recent_pending_status", "none")
    )

    if churn_status == "blocked":
        closure_likely_outcome = "hold"
        if closure_hysteresis_status == "confirmed-confirmation":
            closure_hysteresis_status = "pending-confirmation"
        closure_hysteresis_reason = churn_reason or closure_hysteresis_reason
        return (
            closure_likely_outcome,
            closure_hysteresis_status,
            closure_hysteresis_reason,
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
        )

    if current_freshness_status in {"stale", "insufficient-data"}:
        if closure_likely_outcome == "confirm-soon":
            closure_likely_outcome = "hold"
            if closure_hysteresis_status == "confirmed-confirmation":
                closure_hysteresis_status = "pending-confirmation"
                closure_hysteresis_reason = (
                    persistence_reason or churn_reason or closure_hysteresis_reason
                )
        elif closure_likely_outcome == "expire-risk":
            closure_likely_outcome = "clear-risk"
            closure_hysteresis_status = "pending-clearance"
            closure_hysteresis_reason = (
                persistence_reason or churn_reason or closure_hysteresis_reason
            )
        elif closure_likely_outcome == "clear-risk":
            closure_likely_outcome = "hold"
            if closure_hysteresis_status == "confirmed-clearance":
                closure_hysteresis_status = "pending-clearance"
                closure_hysteresis_reason = (
                    persistence_reason or churn_reason or closure_hysteresis_reason
                )

    if current_reacquisition_status == "reacquired-confirmation":
        if (
            persistence_status in {"holding-confirmation", "sustained-confirmation"}
            and churn_status != "churn"
        ):
            return (
                closure_likely_outcome,
                closure_hysteresis_status,
                closure_hysteresis_reason,
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
            )
        if persistence_status == "reversing" or churn_status == "churn":
            closure_likely_outcome = "hold"
            if closure_hysteresis_status == "confirmed-confirmation":
                closure_hysteresis_status = "pending-confirmation"
            closure_hysteresis_reason = (
                churn_reason or persistence_reason or closure_hysteresis_reason
            )

    if current_reacquisition_status == "reacquired-clearance":
        if (
            persistence_status in {"holding-clearance", "sustained-clearance"}
            and churn_status != "churn"
        ):
            if closure_likely_outcome == "expire-risk" and transition_age_runs < 3:
                closure_likely_outcome = "clear-risk"
            return (
                closure_likely_outcome,
                closure_hysteresis_status,
                closure_hysteresis_reason,
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
            )
        if persistence_status == "reversing" or churn_status == "churn":
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
            }:
                restore_reason = (
                    churn_reason
                    or persistence_reason
                    or (
                        "Reacquired clearance pressure stopped holding cleanly, so the "
                        "earlier-clear posture has been withdrawn."
                    )
                )
                transition_status = recent_pending_status
                transition_reason = restore_reason
                resolution_status = "none"
                resolution_reason = ""
                if recent_pending_status == "pending-support":
                    reverted_policy = target.get(
                        "pre_class_normalization_trust_policy",
                        trust_policy,
                    )
                    reverted_reason = target.get(
                        "pre_class_normalization_trust_policy_reason",
                        trust_policy_reason,
                    )
                    trust_policy = str(reverted_policy)
                    trust_policy_reason = (
                        restore_reason
                        if reverted_policy == "verify-first"
                        else str(reverted_reason)
                    )
                    class_normalization_status = "candidate"
                    class_normalization_reason = restore_reason
                else:
                    pending_debt_status = pending_debt_status or "watch"
                    pending_debt_reason = pending_debt_reason or restore_reason
                    policy_debt_status = "watch"
                    policy_debt_reason = restore_reason

    return (
        closure_likely_outcome,
        closure_hysteresis_status,
        closure_hysteresis_reason,
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
    )


def closure_forecast_reacquisition_hotspots(
    resolution_targets: list[dict[str, Any]],
    *,
    mode: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for target in resolution_targets:
        class_key = target_class_key(target)
        if not class_key:
            continue
        current = {
            "scope": "class",
            "label": class_key,
            "closure_forecast_reacquisition_age_runs": target.get(
                "closure_forecast_reacquisition_age_runs",
                0,
            ),
            "closure_forecast_reacquisition_persistence_score": target.get(
                "closure_forecast_reacquisition_persistence_score",
                0.0,
            ),
            "closure_forecast_reacquisition_persistence_status": target.get(
                "closure_forecast_reacquisition_persistence_status",
                "none",
            ),
            "closure_forecast_recovery_churn_score": target.get(
                "closure_forecast_recovery_churn_score",
                0.0,
            ),
            "closure_forecast_recovery_churn_status": target.get(
                "closure_forecast_recovery_churn_status",
                "none",
            ),
            "recent_reacquisition_persistence_path": target.get(
                "recent_reacquisition_persistence_path",
                "",
            ),
            "recent_recovery_churn_path": target.get("recent_recovery_churn_path", ""),
        }
        existing = grouped.get(class_key)
        if existing is None or abs(
            float(current["closure_forecast_reacquisition_persistence_score"] or 0.0)
        ) > abs(
            float(existing["closure_forecast_reacquisition_persistence_score"] or 0.0)
        ):
            grouped[class_key] = current

    hotspots = list(grouped.values())
    if mode == "just-reacquired":
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reacquisition_persistence_status")
            == "just-reacquired"
        ]
        hotspots.sort(
            key=lambda item: (
                -int(item.get("closure_forecast_reacquisition_age_runs", 0) or 0),
                -abs(
                    float(
                        item.get(
                            "closure_forecast_reacquisition_persistence_score", 0.0
                        )
                        or 0.0
                    )
                ),
                str(item.get("label", "")),
            )
        )
    elif mode == "holding":
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reacquisition_persistence_status")
            in {
                "holding-confirmation",
                "holding-clearance",
                "sustained-confirmation",
                "sustained-clearance",
            }
        ]
        hotspots.sort(
            key=lambda item: (
                -int(item.get("closure_forecast_reacquisition_age_runs", 0) or 0),
                -abs(
                    float(
                        item.get(
                            "closure_forecast_reacquisition_persistence_score", 0.0
                        )
                        or 0.0
                    )
                ),
                str(item.get("label", "")),
            )
        )
    else:
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_recovery_churn_status")
            in {"watch", "churn", "blocked"}
        ]
        hotspots.sort(
            key=lambda item: (
                -float(item.get("closure_forecast_recovery_churn_score", 0.0) or 0.0),
                -int(item.get("closure_forecast_reacquisition_age_runs", 0) or 0),
                str(item.get("label", "")),
            )
        )
    return hotspots[:5]


def closure_forecast_reacquisition_persistence_summary(
    primary_target: dict[str, Any],
    just_reacquired_hotspots: list[dict[str, Any]],
    holding_reacquisition_hotspots: list[dict[str, Any]],
) -> str:
    label = target_label(primary_target) or "The current target"
    status = str(
        primary_target.get("closure_forecast_reacquisition_persistence_status", "none")
    )
    age_runs = int(
        primary_target.get("closure_forecast_reacquisition_age_runs", 0) or 0
    )
    score = float(
        primary_target.get("closure_forecast_reacquisition_persistence_score", 0.0)
        or 0.0
    )
    if status == "just-reacquired":
        return (
            f"{label} has only just re-earned stronger closure-forecast posture, so it is still "
            f"fragile ({score:.2f}; {age_runs} run)."
        )
    if status == "holding-confirmation":
        return (
            f"Confirmation-side reacquisition for {label} has held long enough to keep the "
            f"restored forecast in place ({score:.2f}; {age_runs} runs)."
        )
    if status == "holding-clearance":
        return (
            f"Clearance-side reacquisition for {label} has held long enough to keep the restored "
            f"caution in place ({score:.2f}; {age_runs} runs)."
        )
    if status == "sustained-confirmation":
        return (
            f"Confirmation-side reacquisition for {label} is now holding with enough "
            f"follow-through to trust the restored forecast more ({score:.2f}; {age_runs} runs)."
        )
    if status == "sustained-clearance":
        return (
            f"Clearance-side reacquisition for {label} is now holding with enough follow-through "
            f"to trust the restored caution more ({score:.2f}; {age_runs} runs)."
        )
    if status == "reversing":
        return (
            f"The restored closure-forecast posture for {label} is already weakening, so it is "
            f"being softened again ({score:.2f})."
        )
    if status == "insufficient-data":
        return (
            f"Reacquisition for {label} is still too lightly exercised to say whether the "
            "restored forecast can hold."
        )
    if just_reacquired_hotspots:
        hotspot = just_reacquired_hotspots[0]
        return (
            f"Newly restored forecast posture is most fragile around "
            f"{hotspot.get('label', 'recent hotspots')}, so those classes still need "
            "follow-through before the restored forecast can be trusted."
        )
    if holding_reacquisition_hotspots:
        hotspot = holding_reacquisition_hotspots[0]
        return (
            f"Restored forecast posture is holding most cleanly around "
            f"{hotspot.get('label', 'recent hotspots')}, so those classes are closest to "
            "keeping reacquired strength safely."
        )
    return "No reacquired closure-forecast posture is active enough yet to judge whether it can hold."


def closure_forecast_recovery_churn_summary(
    primary_target: dict[str, Any],
    recovery_churn_hotspots: list[dict[str, Any]],
) -> str:
    label = target_label(primary_target) or "The current target"
    status = str(primary_target.get("closure_forecast_recovery_churn_status", "none"))
    score = float(
        primary_target.get("closure_forecast_recovery_churn_score", 0.0) or 0.0
    )
    if status == "watch":
        return (
            f"Recovery for {label} is wobbling enough that restored forecast strength may "
            f"soften soon ({score:.2f})."
        )
    if status == "churn":
        return (
            f"Recovery for {label} is flipping enough that restored forecast posture should "
            f"soften quickly ({score:.2f})."
        )
    if status == "blocked":
        return str(
            primary_target.get(
                "closure_forecast_recovery_churn_reason",
                "Local target instability is preventing positive confirmation-side persistence "
                f"for {label}.",
            )
        )
    if recovery_churn_hotspots:
        hotspot = recovery_churn_hotspots[0]
        return (
            f"Recovery churn is highest around {hotspot.get('label', 'recent hotspots')}, "
            "so restored forecast posture there should soften quickly if the wobble continues."
        )
    return "No meaningful recovery churn is active right now."


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
        or event.get("transition_closure_likely_outcome", "none")
        in {"clear-risk", "expire-risk"}
    )


def reacquisition_event_has_evidence(event: dict[str, Any]) -> bool:
    return (
        reacquisition_event_is_confirmation_like(event)
        or reacquisition_event_is_clearance_like(event)
        or event.get("closure_forecast_recovery_churn_status", "none")
        in {"watch", "churn", "blocked"}
    )


def reacquisition_event_signal_label(event: dict[str, Any]) -> str:
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
) -> str:
    if freshness_status == "fresh":
        return (
            "Recent reacquired closure-forecast evidence is still current enough to trust, with "
            f"{recent_window_weight_share:.0%} of the weighted signal coming from the latest "
            f"{CLASS_REACQUISITION_FRESHNESS_WINDOW_RUNS} runs."
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
) -> dict[str, Any]:
    class_key = target_class_key(target)
    class_events = [
        event
        for event in closure_forecast_events
        if event.get("class_key") == class_key
    ]
    relevant_events: list[dict[str, Any]] = []
    for event in class_events:
        if not reacquisition_event_has_evidence(event):
            continue
        relevant_events.append(event)
        if len(relevant_events) >= HISTORY_WINDOW_RUNS:
            break

    weighted_reacquisition_evidence_count = 0.0
    weighted_confirmation_like = 0.0
    weighted_clearance_like = 0.0
    recent_reacquisition_weight = 0.0
    recent_signals = [
        reacquisition_event_signal_label(event)
        for event in relevant_events[:CLASS_REACQUISITION_FRESHNESS_WINDOW_RUNS]
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
        weight = CLASS_MEMORY_RECENCY_WEIGHTS[min(index, HISTORY_WINDOW_RUNS - 1)]
        weighted_reacquisition_evidence_count += weight
        event_side = closure_forecast_reacquisition_side_from_event(event)
        if (
            index < CLASS_REACQUISITION_FRESHNESS_WINDOW_RUNS
            and event_side == current_side
        ):
            recent_reacquisition_weight += weight
        if reacquisition_event_is_confirmation_like(event):
            weighted_confirmation_like += weight
        if reacquisition_event_is_clearance_like(event):
            weighted_clearance_like += weight

    recent_window_weight_share = recent_reacquisition_weight / max(
        weighted_reacquisition_evidence_count,
        1.0,
    )
    computed_freshness_status = closure_forecast_freshness_status(
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
        "closure_forecast_reacquisition_freshness_reason": closure_forecast_reacquisition_freshness_reason(
            computed_freshness_status,
            weighted_reacquisition_evidence_count,
            recent_window_weight_share,
            decayed_confirmation_rate,
            decayed_clearance_rate,
        ),
        "closure_forecast_reacquisition_memory_weight": round(
            recent_window_weight_share, 2
        ),
        "decayed_reacquired_confirmation_rate": round(decayed_confirmation_rate, 2),
        "decayed_reacquired_clearance_rate": round(decayed_clearance_rate, 2),
        "recent_reacquisition_signal_mix": recent_reacquisition_signal_mix(
            weighted_reacquisition_evidence_count,
            weighted_confirmation_like,
            weighted_clearance_like,
            recent_window_weight_share,
        ),
        "recent_reacquisition_signal_path": " -> ".join(recent_signals),
        "has_fresh_aligned_recent_evidence": any(
            event.get("closure_forecast_freshness_status", "insufficient-data")
            == "fresh"
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
                reverted_policy = target.get(
                    "pre_class_normalization_trust_policy", trust_policy
                )
                reverted_reason = target.get(
                    "pre_class_normalization_trust_policy_reason",
                    trust_policy_reason,
                )
                next_trust_policy = str(reverted_policy)
                next_trust_policy_reason = (
                    reset_reason
                    if reverted_policy == "verify-first"
                    else str(reverted_reason)
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
        blocked_reason = (
            "Local target instability still overrides healthy reacquisition freshness."
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
            "recent_reacquisition_signal_mix": target.get(
                "recent_reacquisition_signal_mix", ""
            ),
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
                    for part in (
                        target.get("recent_reacquisition_persistence_path", "") or ""
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
) -> str:
    label = target_label(primary_target) or "The current target"
    reset_status = primary_target.get(
        "closure_forecast_persistence_reset_status", "none"
    )
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


__all__ = (
    "apply_closure_forecast_reacquisition_control",
    "apply_reacquisition_freshness_reset_control",
    "apply_reacquisition_persistence_and_churn_control",
    "closure_forecast_persistence_reset_summary",
    "closure_forecast_reacquisition_freshness_for_target",
    "closure_forecast_reacquisition_freshness_hotspots",
    "closure_forecast_reacquisition_freshness_reason",
    "closure_forecast_reacquisition_freshness_summary",
    "closure_forecast_reacquisition_hotspots",
    "closure_forecast_reacquisition_path_label",
    "closure_forecast_reacquisition_persistence_for_target",
    "closure_forecast_reacquisition_persistence_summary",
    "closure_forecast_reacquisition_side_from_event",
    "closure_forecast_reacquisition_side_from_status",
    "closure_forecast_reacquisition_summary",
    "closure_forecast_recovery_churn_for_target",
    "closure_forecast_recovery_churn_summary",
    "closure_forecast_refresh_hotspots",
    "closure_forecast_refresh_path_label",
    "closure_forecast_refresh_recovery_for_target",
    "closure_forecast_refresh_recovery_summary",
    "closure_forecast_refresh_signal_from_event",
    "reacquisition_event_has_evidence",
    "reacquisition_event_is_clearance_like",
    "reacquisition_event_is_confirmation_like",
    "reacquisition_event_signal_label",
    "recent_closure_forecast_weakened_side",
    "recent_reacquisition_signal_mix",
)
