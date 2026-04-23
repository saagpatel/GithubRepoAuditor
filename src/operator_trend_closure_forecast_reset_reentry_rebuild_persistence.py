from __future__ import annotations

from typing import Any, Callable


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
