from __future__ import annotations

from typing import Any, Callable, Sequence


def class_pending_debt_for_target(
    target: dict[str, Any],
    transition_events: list[dict[str, Any]],
    *,
    target_class_key: Callable[[dict[str, Any]], str],
    clamp_round: Callable[[float, float, float], float],
    class_pending_debt_window_runs: int,
) -> tuple[str, str, float, float, str]:
    class_key = target_class_key(target)
    matching_events = [event for event in transition_events if event.get("class_key") == class_key][
        :class_pending_debt_window_runs
    ]
    outcomes = [pending_debt_event_outcome(event) for event in matching_events]
    relevant_outcomes = [outcome for outcome in outcomes if outcome != "none"]
    pending_entry_count = len(relevant_outcomes)
    confirmed_count = sum(1 for outcome in relevant_outcomes if outcome == "confirmed")
    cleared_count = sum(1 for outcome in relevant_outcomes if outcome == "cleared")
    expired_count = sum(1 for outcome in relevant_outcomes if outcome == "expired")
    stalled_count = sum(1 for outcome in relevant_outcomes if outcome == "stalled")
    blocked_count = sum(1 for outcome in relevant_outcomes if outcome == "blocked")
    debt_like_count = stalled_count + expired_count + blocked_count
    healthy_resolution_count = confirmed_count + cleared_count
    class_pending_debt_rate = clamp_round(
        debt_like_count / max(pending_entry_count, 1),
        0.0,
        1.0,
    )
    class_pending_resolution_rate = clamp_round(
        healthy_resolution_count / max(pending_entry_count, 1),
        0.0,
        1.0,
    )
    recent_pending_debt_path = " -> ".join(relevant_outcomes[:4])

    if pending_entry_count >= 3 and (
        debt_like_count >= healthy_resolution_count + 1 or class_pending_debt_rate >= 0.60
    ):
        return (
            "active-debt",
            "This class keeps accumulating stalled, expired, or blocked pending transitions, so new pending signals should be treated more cautiously.",
            class_pending_debt_rate,
            class_pending_resolution_rate,
            recent_pending_debt_path,
        )
    if pending_entry_count >= 2 and (
        healthy_resolution_count >= debt_like_count + 1 or class_pending_resolution_rate >= 0.60
    ):
        return (
            "clearing",
            "This class is resolving pending transitions more cleanly again, so newer pending signals are less likely to linger indefinitely.",
            class_pending_debt_rate,
            class_pending_resolution_rate,
            recent_pending_debt_path,
        )
    if pending_entry_count >= 2:
        return (
            "watch",
            "This class has mixed recent pending-transition outcomes, so watch whether new pending signals resolve cleanly or start to accumulate debt.",
            class_pending_debt_rate,
            class_pending_resolution_rate,
            recent_pending_debt_path,
        )
    return (
        "none",
        "",
        class_pending_debt_rate,
        class_pending_resolution_rate,
        recent_pending_debt_path,
    )


def pending_debt_event_outcome(event: dict[str, Any]) -> str:
    resolution_status = event.get("class_transition_resolution_status", "none")
    health_status = event.get("class_transition_health_status", "none")
    transition_status = event.get("class_reweight_transition_status", "none")
    if resolution_status == "confirmed":
        return "confirmed"
    if resolution_status == "cleared":
        return "cleared"
    if resolution_status == "expired":
        return "expired"
    if (
        resolution_status == "blocked"
        or health_status == "blocked"
        or transition_status == "blocked"
    ):
        return "blocked"
    if health_status == "stalled":
        return "stalled"
    if transition_status in {"pending-support", "pending-caution"} or health_status in {
        "building",
        "holding",
    }:
        return "pending"
    return "none"


def class_pending_debt_hotspots(
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
        dominant_count = target.get("class_pending_debt_rate", 0.0)
        if mode == "healthy":
            dominant_count = target.get("class_pending_resolution_rate", 0.0)
        current = {
            "scope": "class",
            "label": class_key,
            "class_pending_debt_status": target.get("class_pending_debt_status", "none"),
            "class_pending_debt_rate": target.get("class_pending_debt_rate", 0.0),
            "class_pending_resolution_rate": target.get("class_pending_resolution_rate", 0.0),
            "recent_pending_debt_path": target.get("recent_pending_debt_path", ""),
            "dominant_count": dominant_count,
            "pending_entry_count": len(
                [
                    part
                    for part in (target.get("recent_pending_debt_path", "") or "").split(" -> ")
                    if part
                ]
            ),
        }
        existing = grouped.get(class_key)
        if existing is None or current["dominant_count"] > existing["dominant_count"]:
            grouped[class_key] = current

    hotspots = list(grouped.values())
    if mode == "healthy":
        hotspots = [
            item for item in hotspots if item.get("class_pending_debt_status") == "clearing"
        ]
        hotspots.sort(
            key=lambda item: (
                -float(item.get("class_pending_resolution_rate", 0.0) or 0.0),
                -int(item.get("pending_entry_count", 0) or 0),
                str(item.get("label", "")),
            )
        )
    else:
        hotspots = [
            item for item in hotspots if item.get("class_pending_debt_status") == "active-debt"
        ]
        hotspots.sort(
            key=lambda item: (
                -float(item.get("class_pending_debt_rate", 0.0) or 0.0),
                -int(item.get("pending_entry_count", 0) or 0),
                str(item.get("label", "")),
            )
        )
    return hotspots[:5]


def pending_debt_freshness_for_target(
    target: dict[str, Any],
    transition_events: list[dict[str, Any]],
    *,
    target_class_key: Callable[[dict[str, Any]], str],
    class_memory_recency_weights: Sequence[float],
    history_window_runs: int,
    class_pending_debt_window_runs: int,
    pending_debt_freshness_window_runs: int,
) -> dict[str, Any]:
    class_key = target_class_key(target)
    class_events = [event for event in transition_events if event.get("class_key") == class_key]
    relevant_events: list[tuple[dict[str, Any], str]] = []
    for event in class_events:
        outcome = pending_debt_event_outcome(event)
        if outcome == "none":
            continue
        relevant_events.append((event, outcome))
        if len(relevant_events) >= class_pending_debt_window_runs:
            break

    weighted_pending_entry_count = 0.0
    weighted_debt_like = 0.0
    weighted_healthy_resolution = 0.0
    recent_pending_weight = 0.0
    recent_outcomes = [
        outcome for _, outcome in relevant_events[:pending_debt_freshness_window_runs]
    ]
    for index, (_event, outcome) in enumerate(relevant_events):
        weight = class_memory_recency_weights[min(index, history_window_runs - 1)]
        weighted_pending_entry_count += weight
        if index < pending_debt_freshness_window_runs:
            recent_pending_weight += weight
        if outcome in {"stalled", "expired", "blocked"}:
            weighted_debt_like += weight
        if outcome in {"confirmed", "cleared"}:
            weighted_healthy_resolution += weight

    recent_window_weight_share = recent_pending_weight / max(weighted_pending_entry_count, 1.0)
    freshness_status = pending_debt_freshness_status(
        weighted_pending_entry_count,
        recent_window_weight_share,
    )
    decayed_pending_debt_rate = weighted_debt_like / max(weighted_pending_entry_count, 1.0)
    decayed_pending_resolution_rate = weighted_healthy_resolution / max(
        weighted_pending_entry_count, 1.0
    )
    return {
        "pending_debt_freshness_status": freshness_status,
        "pending_debt_freshness_reason": pending_debt_freshness_reason(
            freshness_status,
            weighted_pending_entry_count,
            recent_window_weight_share,
            decayed_pending_debt_rate,
            decayed_pending_resolution_rate,
            pending_debt_freshness_window_runs=pending_debt_freshness_window_runs,
        ),
        "pending_debt_memory_weight": round(recent_window_weight_share, 2),
        "decayed_pending_debt_rate": round(decayed_pending_debt_rate, 2),
        "decayed_pending_resolution_rate": round(decayed_pending_resolution_rate, 2),
        "recent_pending_signal_mix": recent_pending_signal_mix(
            weighted_pending_entry_count,
            weighted_debt_like,
            weighted_healthy_resolution,
            recent_window_weight_share,
        ),
        "recent_pending_debt_path": " -> ".join(recent_outcomes),
    }


def pending_debt_freshness_status(
    weighted_pending_entry_count: float,
    recent_window_weight_share: float,
) -> str:
    if weighted_pending_entry_count < 2.0:
        return "insufficient-data"
    if recent_window_weight_share >= 0.60:
        return "fresh"
    if recent_window_weight_share >= 0.35:
        return "mixed-age"
    return "stale"


def pending_debt_freshness_reason(
    freshness_status: str,
    weighted_pending_entry_count: float,
    recent_window_weight_share: float,
    decayed_pending_debt_rate: float,
    decayed_pending_resolution_rate: float,
    *,
    pending_debt_freshness_window_runs: int,
) -> str:
    if freshness_status == "fresh":
        return (
            "Recent pending-transition evidence is still current enough to trust, with "
            f"{recent_window_weight_share:.0%} of the weighted signal coming from the latest {pending_debt_freshness_window_runs} runs."
        )
    if freshness_status == "mixed-age":
        return (
            "Pending-transition memory is still useful, but it is partly aging: "
            f"{recent_window_weight_share:.0%} of the weighted signal is recent and the rest is older carry-forward."
        )
    if freshness_status == "stale":
        return "Older pending-debt patterns are now carrying more of the signal than recent runs, so they should not dominate closure forecasting."
    return (
        "Pending-transition memory is still too lightly exercised to judge freshness, with "
        f"{weighted_pending_entry_count:.2f} weighted pending-entry run(s), "
        f"{decayed_pending_debt_rate:.0%} debt-like signal, and {decayed_pending_resolution_rate:.0%} healthy-resolution signal."
    )


def recent_pending_signal_mix(
    weighted_pending_entry_count: float,
    weighted_debt_like: float,
    weighted_healthy_resolution: float,
    recent_window_weight_share: float,
) -> str:
    return (
        f"{weighted_pending_entry_count:.2f} weighted pending-entry run(s) with "
        f"{weighted_debt_like:.2f} debt-like, {weighted_healthy_resolution:.2f} healthy-resolution, "
        f"and {recent_window_weight_share:.0%} of the signal from the freshest runs."
    )


def closure_forecast_reweight_scores_for_target(
    target: dict[str, Any],
    transition_history_meta: dict[str, Any],
    pending_history_meta: dict[str, Any],
    *,
    target_specific_normalization_noise: Callable[[dict[str, Any], dict[str, Any]], bool],
    clamp_round: Callable[[float, float, float], float],
) -> tuple[float, float, float, str, list[str]]:
    transition_status = target.get("class_reweight_transition_status", "none")
    if transition_status not in {"pending-support", "pending-caution"}:
        return 0.0, 0.0, 0.0, "neutral", []

    freshness_status = pending_history_meta.get(
        "pending_debt_freshness_status", "insufficient-data"
    )
    freshness_multiplier = {
        "fresh": 1.00,
        "mixed-age": 0.65,
        "stale": 0.35,
        "insufficient-data": 0.20,
    }.get(str(freshness_status), 0.20)
    transition_score_delta = float(
        transition_history_meta.get("transition_score_delta", 0.0) or 0.0
    )
    health_status = str(target.get("class_transition_health_status", "none"))
    likely_outcome = str(target.get("transition_closure_likely_outcome", "none"))
    pending_debt_status = str(target.get("class_pending_debt_status", "none"))
    local_noise = target_specific_normalization_noise(target, transition_history_meta)
    matching_transition_strengthening = transition_score_delta >= 0.05

    support_adjustments = 0.0
    if likely_outcome == "confirm-soon":
        support_adjustments += 0.10
    if health_status == "building":
        support_adjustments += 0.10
    if target.get("class_reweight_stability_status", "watch") == "stable":
        support_adjustments += 0.05
    if matching_transition_strengthening:
        support_adjustments += 0.05
    if health_status in {"stalled", "expired"}:
        support_adjustments -= 0.10
    if local_noise:
        support_adjustments -= 0.10

    caution_adjustments = 0.0
    if pending_debt_status == "active-debt":
        caution_adjustments += 0.10
    if likely_outcome in {"clear-risk", "expire-risk"}:
        caution_adjustments += 0.10
    if health_status == "holding":
        caution_adjustments += 0.05
    if int(target.get("class_transition_age_runs", 0) or 0) >= 3 and not transition_history_meta.get(
        "current_transition_strengthening",
        False,
    ):
        caution_adjustments += 0.05
    if pending_debt_status == "clearing":
        caution_adjustments -= 0.10
    if target.get("class_transition_resolution_status", "none") == "confirmed":
        caution_adjustments -= 0.05

    support_score = clamp_round(
        float(pending_history_meta.get("decayed_pending_resolution_rate", 0.0) or 0.0)
        * freshness_multiplier
        + support_adjustments,
        0.0,
        0.95,
    )
    caution_score = clamp_round(
        float(pending_history_meta.get("decayed_pending_debt_rate", 0.0) or 0.0)
        * freshness_multiplier
        + caution_adjustments,
        0.0,
        0.95,
    )
    reweight_score = clamp_round(
        support_score - caution_score,
        -0.95,
        0.95,
    )
    if reweight_score >= 0.20:
        direction = "supporting-confirmation"
    elif reweight_score <= -0.20:
        direction = "supporting-clearance"
    else:
        direction = "neutral"

    reasons: list[str] = []
    freshness_reason = pending_history_meta.get("pending_debt_freshness_reason", "")
    if freshness_reason:
        reasons.append(str(freshness_reason))
    if likely_outcome == "confirm-soon":
        reasons.append(
            "Recent class resolution behavior is still strong enough that this pending signal could confirm soon."
        )
    elif health_status == "building":
        reasons.append("The live pending signal is still building in the same direction.")
    elif target.get("class_reweight_stability_status", "watch") == "stable":
        reasons.append(
            "Class transition stability is still good enough to keep the pending forecast coherent."
        )
    if pending_debt_status == "active-debt":
        reasons.append("Fresh unresolved pending debt is still clustering in this class.")
    elif likely_outcome in {"clear-risk", "expire-risk"}:
        reasons.append(
            "The live pending signal is already leaning toward clearance or expiry risk."
        )
    elif health_status == "holding":
        reasons.append("The live pending signal is holding instead of strengthening.")
    if local_noise:
        reasons.append(
            "Local target instability is still limiting how much class evidence can strengthen the pending forecast."
        )
    return support_score, caution_score, reweight_score, direction, reasons[:4]
