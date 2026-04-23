from __future__ import annotations

from typing import Any, Callable


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
