from __future__ import annotations

from typing import Any, Callable, Sequence


def closure_forecast_freshness_for_target(
    target: dict[str, Any],
    closure_forecast_events: list[dict[str, Any]],
    *,
    target_class_key: Callable[[dict[str, Any]], str],
    closure_forecast_event_has_evidence: Callable[[dict[str, Any]], bool],
    closure_forecast_event_signal_label: Callable[[dict[str, Any]], str],
    closure_forecast_event_is_confirmation_like: Callable[[dict[str, Any]], bool],
    closure_forecast_event_is_clearance_like: Callable[[dict[str, Any]], bool],
    class_memory_recency_weights: Sequence[float],
    history_window_runs: int,
    class_closure_forecast_freshness_window_runs: int,
    freshness_status: Callable[[float, float], str],
    freshness_reason: Callable[[str, float, float, float, float], str],
    recent_signal_mix: Callable[[float, float, float, float], str],
) -> dict[str, Any]:
    class_key = target_class_key(target)
    class_events = [event for event in closure_forecast_events if event.get("class_key") == class_key]
    relevant_events: list[dict[str, Any]] = []
    for event in class_events:
        if not closure_forecast_event_has_evidence(event):
            continue
        relevant_events.append(event)
        if len(relevant_events) >= history_window_runs:
            break

    weighted_forecast_evidence_count = 0.0
    weighted_confirmation_like = 0.0
    weighted_clearance_like = 0.0
    recent_forecast_weight = 0.0
    recent_signals = [
        closure_forecast_event_signal_label(event)
        for event in relevant_events[:class_closure_forecast_freshness_window_runs]
    ]
    for index, event in enumerate(relevant_events):
        weight = class_memory_recency_weights[min(index, history_window_runs - 1)]
        weighted_forecast_evidence_count += weight
        if index < class_closure_forecast_freshness_window_runs:
            recent_forecast_weight += weight
        if closure_forecast_event_is_confirmation_like(event):
            weighted_confirmation_like += weight
        if closure_forecast_event_is_clearance_like(event):
            weighted_clearance_like += weight

    recent_window_weight_share = recent_forecast_weight / max(weighted_forecast_evidence_count, 1.0)
    computed_freshness_status = freshness_status(
        weighted_forecast_evidence_count,
        recent_window_weight_share,
    )
    decayed_confirmation_rate = weighted_confirmation_like / max(weighted_forecast_evidence_count, 1.0)
    decayed_clearance_rate = weighted_clearance_like / max(weighted_forecast_evidence_count, 1.0)
    return {
        "closure_forecast_freshness_status": computed_freshness_status,
        "closure_forecast_freshness_reason": freshness_reason(
            computed_freshness_status,
            weighted_forecast_evidence_count,
            recent_window_weight_share,
            decayed_confirmation_rate,
            decayed_clearance_rate,
        ),
        "closure_forecast_memory_weight": round(recent_window_weight_share, 2),
        "decayed_confirmation_forecast_rate": round(decayed_confirmation_rate, 2),
        "decayed_clearance_forecast_rate": round(decayed_clearance_rate, 2),
        "recent_closure_forecast_signal_mix": recent_signal_mix(
            weighted_forecast_evidence_count,
            weighted_confirmation_like,
            weighted_clearance_like,
            recent_window_weight_share,
        ),
        "recent_closure_forecast_path": " -> ".join(recent_signals),
    }


def closure_forecast_event_has_evidence(
    event: dict[str, Any],
    *,
    normalized_closure_forecast_direction: Callable[[str, float], str],
) -> bool:
    score = float(event.get("closure_forecast_reweight_score", 0.0) or 0.0)
    direction = normalized_closure_forecast_direction(
        str(event.get("closure_forecast_reweight_direction", "neutral")),
        score,
    )
    likely_outcome = event.get("transition_closure_likely_outcome", "none") or "none"
    hysteresis_status = event.get("closure_forecast_hysteresis_status", "none") or "none"
    return (
        abs(score) >= 0.05
        or direction in {"supporting-confirmation", "supporting-clearance"}
        or likely_outcome in {"confirm-soon", "clear-risk", "expire-risk"}
        or hysteresis_status
        in {
            "pending-confirmation",
            "pending-clearance",
            "confirmed-confirmation",
            "confirmed-clearance",
        }
    )


def closure_forecast_event_is_confirmation_like(
    event: dict[str, Any],
    *,
    normalized_closure_forecast_direction: Callable[[str, float], str],
) -> bool:
    score = float(event.get("closure_forecast_reweight_score", 0.0) or 0.0)
    direction = normalized_closure_forecast_direction(
        str(event.get("closure_forecast_reweight_direction", "neutral")),
        score,
    )
    return (
        direction == "supporting-confirmation"
        or event.get("transition_closure_likely_outcome", "none") == "confirm-soon"
        or event.get("closure_forecast_hysteresis_status", "none")
        in {"pending-confirmation", "confirmed-confirmation"}
    )


def closure_forecast_event_is_clearance_like(
    event: dict[str, Any],
    *,
    normalized_closure_forecast_direction: Callable[[str, float], str],
) -> bool:
    score = float(event.get("closure_forecast_reweight_score", 0.0) or 0.0)
    direction = normalized_closure_forecast_direction(
        str(event.get("closure_forecast_reweight_direction", "neutral")),
        score,
    )
    return (
        direction == "supporting-clearance"
        or event.get("transition_closure_likely_outcome", "none") in {"clear-risk", "expire-risk"}
        or event.get("closure_forecast_hysteresis_status", "none")
        in {"pending-clearance", "confirmed-clearance"}
    )


def closure_forecast_event_signal_label(
    event: dict[str, Any],
    *,
    closure_forecast_event_is_confirmation_like: Callable[[dict[str, Any]], bool],
    closure_forecast_event_is_clearance_like: Callable[[dict[str, Any]], bool],
) -> str:
    if closure_forecast_event_is_confirmation_like(event):
        return "confirmation-like"
    if closure_forecast_event_is_clearance_like(event):
        return "clearance-like"
    return "neutral"


def closure_forecast_freshness_status(
    weighted_forecast_evidence_count: float,
    recent_window_weight_share: float,
) -> str:
    if weighted_forecast_evidence_count < 2.0:
        return "insufficient-data"
    if recent_window_weight_share >= 0.60:
        return "fresh"
    if recent_window_weight_share >= 0.35:
        return "mixed-age"
    return "stale"


def closure_forecast_freshness_reason(
    freshness_status: str,
    weighted_forecast_evidence_count: float,
    recent_window_weight_share: float,
    decayed_confirmation_rate: float,
    decayed_clearance_rate: float,
    *,
    class_closure_forecast_freshness_window_runs: int,
) -> str:
    if freshness_status == "fresh":
        return (
            "Recent closure-forecast evidence is still current enough to trust, with "
            f"{recent_window_weight_share:.0%} of the weighted signal coming from the latest {class_closure_forecast_freshness_window_runs} runs."
        )
    if freshness_status == "mixed-age":
        return (
            "Closure-forecast memory is still useful, but it is partly aging: "
            f"{recent_window_weight_share:.0%} of the weighted signal is recent and the rest is older carry-forward."
        )
    if freshness_status == "stale":
        return "Older closure-forecast momentum is carrying more of the signal than recent runs, so it should not dominate the current forecast."
    return (
        "Closure-forecast memory is still too lightly exercised to judge freshness, with "
        f"{weighted_forecast_evidence_count:.2f} weighted forecast run(s), "
        f"{decayed_confirmation_rate:.0%} confirmation-like signal, and {decayed_clearance_rate:.0%} clearance-like signal."
    )


def recent_closure_forecast_signal_mix(
    weighted_forecast_evidence_count: float,
    weighted_confirmation_like: float,
    weighted_clearance_like: float,
    recent_window_weight_share: float,
) -> str:
    return (
        f"{weighted_forecast_evidence_count:.2f} weighted forecast run(s) with "
        f"{weighted_confirmation_like:.2f} confirmation-like, {weighted_clearance_like:.2f} clearance-like, "
        f"and {recent_window_weight_share:.0%} of the signal from the freshest runs."
    )


def apply_closure_forecast_decay_control(
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
    closure_likely_outcome: str,
    closure_hysteresis_status: str,
    closure_hysteresis_reason: str,
    pending_debt_status: str,
    pending_debt_reason: str,
    policy_debt_status: str,
    policy_debt_reason: str,
    class_normalization_status: str,
    class_normalization_reason: str,
    target_specific_normalization_noise: Callable[[dict[str, Any], dict[str, Any]], bool],
) -> tuple[str, str, str, str, str, str, str, str, str, str, str, str, str, str, str, str, str]:
    freshness_status = freshness_meta.get("closure_forecast_freshness_status", "insufficient-data")
    decayed_clearance_rate = float(
        freshness_meta.get("decayed_clearance_forecast_rate", 0.0) or 0.0
    )
    local_noise = target_specific_normalization_noise(target, transition_history_meta)
    direction = target.get("closure_forecast_reweight_direction", "neutral")
    recent_pending_status = transition_history_meta.get("recent_pending_status", "none")
    reweight_effect = target.get("closure_forecast_reweight_effect", "none")

    if local_noise and (
        direction == "supporting-confirmation"
        or closure_hysteresis_status in {"pending-confirmation", "confirmed-confirmation"}
    ):
        blocked_reason = "Local target instability still overrides closure-forecast freshness."
        if closure_likely_outcome == "confirm-soon":
            closure_likely_outcome = "hold"
        if closure_hysteresis_status == "confirmed-confirmation":
            closure_hysteresis_status = "pending-confirmation"
        closure_hysteresis_reason = blocked_reason
        return (
            "blocked",
            blocked_reason,
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

    if (
        resolution_status == "cleared"
        and reweight_effect == "clear-risk-strengthened"
        and (freshness_status not in {"fresh", "mixed-age"} or decayed_clearance_rate < 0.50)
        and recent_pending_status in {"pending-support", "pending-caution"}
    ):
        decay_reason = "The earlier forecast-driven clearance posture was pulled back because fresh unresolved pending-debt support is no longer strong enough."
        transition_status = recent_pending_status
        transition_reason = decay_reason
        resolution_status = "none"
        resolution_reason = ""
        closure_likely_outcome = "hold"
        closure_hysteresis_status = "none"
        closure_hysteresis_reason = decay_reason
        if recent_pending_status == "pending-support":
            trust_policy = target.get("pre_class_normalization_trust_policy", trust_policy)
            trust_policy_reason = target.get(
                "pre_class_normalization_trust_policy_reason", trust_policy_reason
            )
            class_normalization_status = "candidate"
            class_normalization_reason = decay_reason
        else:
            pending_debt_status = pending_debt_status or "watch"
            pending_debt_reason = pending_debt_reason or decay_reason
            policy_debt_status = "watch"
            policy_debt_reason = decay_reason
        return (
            "clearance-decayed",
            decay_reason,
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

    if freshness_status not in {"stale", "insufficient-data"}:
        return (
            "none",
            "",
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

    if closure_hysteresis_status == "confirmed-confirmation":
        decay_reason = "Stronger confirmation wording was pulled back because the supporting forecast memory is too old or too lightly refreshed."
        return (
            "confirmation-decayed",
            decay_reason,
            "hold",
            "pending-confirmation",
            decay_reason,
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

    if closure_hysteresis_status == "confirmed-clearance":
        decay_reason = "Stronger clearance wording was pulled back because fresh unresolved pending-debt support is no longer strong enough."
        softened_outcome = "clear-risk" if closure_likely_outcome == "expire-risk" else "hold"
        return (
            "clearance-decayed",
            decay_reason,
            softened_outcome,
            "pending-clearance",
            decay_reason,
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

    if closure_hysteresis_status == "pending-confirmation":
        decay_reason = "Older confirmation-leaning forecast memory is no longer fresh enough to keep stronger carry-forward in place."
        return (
            "confirmation-decayed",
            decay_reason,
            "hold",
            "none",
            decay_reason,
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

    if closure_hysteresis_status == "pending-clearance":
        decay_reason = "Older clearance-leaning forecast memory is no longer fresh enough to keep stronger carry-forward in place."
        softened_outcome = "clear-risk" if closure_likely_outcome == "expire-risk" else "hold"
        return (
            "clearance-decayed",
            decay_reason,
            softened_outcome,
            "none",
            decay_reason,
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

    return (
        "none",
        "",
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


def closure_forecast_freshness_hotspots(
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
            "closure_forecast_freshness_status": target.get(
                "closure_forecast_freshness_status", "insufficient-data"
            ),
            "decayed_confirmation_forecast_rate": target.get(
                "decayed_confirmation_forecast_rate", 0.0
            ),
            "decayed_clearance_forecast_rate": target.get("decayed_clearance_forecast_rate", 0.0),
            "recent_closure_forecast_signal_mix": target.get(
                "recent_closure_forecast_signal_mix", ""
            ),
            "recent_closure_forecast_path": target.get("recent_closure_forecast_path", ""),
            "dominant_count": max(
                float(target.get("decayed_confirmation_forecast_rate", 0.0) or 0.0),
                float(target.get("decayed_clearance_forecast_rate", 0.0) or 0.0),
            ),
            "forecast_event_count": len(
                [
                    part
                    for part in (target.get("recent_closure_forecast_path", "") or "").split(" -> ")
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
            if item.get("closure_forecast_freshness_status") == "fresh"
            and float(item.get("dominant_count", 0.0) or 0.0) > 0.0
        ]
    else:
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_freshness_status") == "stale"
            and float(item.get("dominant_count", 0.0) or 0.0) > 0.0
        ]
    hotspots.sort(
        key=lambda item: (
            -float(item.get("dominant_count", 0.0) or 0.0),
            -int(item.get("forecast_event_count", 0) or 0),
            str(item.get("label", "")),
        )
    )
    return hotspots[:5]
