from __future__ import annotations

from typing import Any, Callable


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
            magnitude -= 0.10
        if momentum_status in {"reversing", "unstable"}:
            magnitude -= 0.15
        if stability_status == "oscillating":
            magnitude -= 0.15
        if (
            event.get(
                "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_status",
                "none",
            )
            != "none"
        ):
            magnitude -= 0.15
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
