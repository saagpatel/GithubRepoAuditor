from __future__ import annotations

from functools import lru_cache

LANE_LABELS = {
    "blocked": "Blocked",
    "urgent": "Needs Attention Now",
    "ready": "Ready for Manual Action",
    "deferred": "Safe to Defer",
}

ATTENTION_LANES = {"blocked", "urgent"}

HISTORY_WINDOW_RUNS = 10
CALIBRATION_WINDOW_RUNS = 20
VALIDATION_WINDOW_RUNS = 2
TRUST_RECOVERY_WINDOW_RUNS = 3
EXCEPTION_RETIREMENT_WINDOW_RUNS = 4

DEFAULT_CLASS_WINDOW_RUNS = 4
CLASS_PENDING_DEBT_WINDOW_RUNS = HISTORY_WINDOW_RUNS

(
    CLASS_NORMALIZATION_WINDOW_RUNS,
    CLASS_MEMORY_FRESHNESS_WINDOW_RUNS,
    CLASS_REWEIGHTING_WINDOW_RUNS,
    CLASS_TRANSITION_WINDOW_RUNS,
    CLASS_PENDING_RESOLUTION_WINDOW_RUNS,
    CLASS_TRANSITION_CLOSURE_WINDOW_RUNS,
    PENDING_DEBT_FRESHNESS_WINDOW_RUNS,
    CLASS_CLOSURE_FORECAST_REWEIGHTING_WINDOW_RUNS,
    CLASS_CLOSURE_FORECAST_TRANSITION_WINDOW_RUNS,
    CLASS_CLOSURE_FORECAST_FRESHNESS_WINDOW_RUNS,
    CLASS_CLOSURE_FORECAST_REFRESH_WINDOW_RUNS,
    CLASS_REACQUISITION_PERSISTENCE_WINDOW_RUNS,
    CLASS_REACQUISITION_FRESHNESS_WINDOW_RUNS,
    CLASS_RESET_REENTRY_WINDOW_RUNS,
    CLASS_RESET_REENTRY_PERSISTENCE_WINDOW_RUNS,
    CLASS_RESET_REENTRY_FRESHNESS_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REFRESH_REBUILD_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_PERSISTENCE_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_FRESHNESS_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_REFRESH_REENTRY_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_REENTRY_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_REENTRY_FRESHNESS_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_REENTRY_REFRESH_RESTORE_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_FRESHNESS_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_REFRESH_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_RERESTORE_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_RERESTORE_FRESHNESS_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_RERESTORE_REFRESH_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_RERERESTORE_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_RERERESTORE_FRESHNESS_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_RERERESTORE_REFRESH_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_RERERERESTORE_WINDOW_RUNS,
) = (DEFAULT_CLASS_WINDOW_RUNS,) * 33

CLASS_MEMORY_RECENCY_WEIGHTS = (1.0, 1.0, 0.7, 0.7, 0.4, 0.4, 0.4, 0.2, 0.2, 0.2)


def target_class_key(item: dict) -> str:
    return f"{item.get('lane', '')}:{item.get('kind', '') or 'unknown'}"


def normalized_closure_forecast_direction(direction: str, score: float) -> str:
    if direction in {"supporting-confirmation", "supporting-clearance", "neutral"}:
        return direction
    if score >= 0.20:
        return "supporting-confirmation"
    if score <= -0.20:
        return "supporting-clearance"
    return "neutral"


def target_specific_normalization_noise(target: dict, history_meta: dict) -> bool:
    return (
        history_meta.get("recent_reopened", False)
        or history_meta.get("recent_policy_flip_count", 0) > 0
        or target.get("trust_recovery_status") == "blocked"
    )


def clamp_round(value: float, *, lower: float, upper: float) -> float:
    return round(max(lower, min(upper, value)), 2)


def closure_forecast_direction_majority(directions: list[str]) -> str:
    confirmation_count = sum(
        1 for direction in directions if direction == "supporting-confirmation"
    )
    clearance_count = sum(
        1 for direction in directions if direction == "supporting-clearance"
    )
    if confirmation_count > clearance_count:
        return "supporting-confirmation"
    if clearance_count > confirmation_count:
        return "supporting-clearance"
    return "neutral"


def closure_forecast_direction_reversing(
    current_direction: str, earlier_majority: str
) -> bool:
    if current_direction == "neutral" or earlier_majority == "neutral":
        return False
    return current_direction != earlier_majority


def class_direction_flip_count(directions: list[str]) -> int:
    non_neutral = [direction for direction in directions if direction != "neutral"]
    if len(non_neutral) < 2:
        return 0
    return sum(
        1
        for previous, current in zip(non_neutral, non_neutral[1:])
        if current != previous
    )


def target_label(item: dict) -> str:
    repo = f"{item.get('repo')}: " if item.get("repo") else ""
    return f"{repo}{item.get('title', '')}".strip(": ")


GENERIC_RECOMMENDATION_PHRASES = (
    "continue the normal audit/control-center loop",
    "continue the normal operator loop",
    "review the latest state",
    "inspect the latest changes and decide on next action",
    "monitor future audits",
    "open the repo queue details",
)

GENERIC_MONITOR_PHRASES = (
    "keep the operator loop light",
    "keep the operator loop lightweight",
)

GENERIC_BASELINE_PHRASES = (
    "run the next full audit to refresh the baseline",
    "refresh the baseline before relying on incremental results",
)


def is_generic_recommendation(action: str) -> bool:
    normalized = (action or "").strip().lower()
    if not normalized:
        return True
    return any(phrase in normalized for phrase in GENERIC_RECOMMENDATION_PHRASES)


def is_generic_monitor_guidance(action: str) -> bool:
    normalized = (action or "").strip().lower()
    return bool(normalized) and any(
        phrase in normalized for phrase in GENERIC_MONITOR_PHRASES
    )


def is_generic_baseline_guidance(
    action: str, watch_guidance: dict | None = None
) -> bool:
    normalized = (action or "").strip().lower()
    if normalized and any(phrase in normalized for phrase in GENERIC_BASELINE_PHRASES):
        return True
    return not normalized and bool(
        watch_guidance and watch_guidance.get("full_refresh_due")
    )


@lru_cache(maxsize=None)
def _side_sets(
    confirmation_members: tuple[str, ...],
) -> tuple[frozenset[str], frozenset[str]]:
    return (
        frozenset(confirmation_members),
        frozenset(
            member.replace("confirmation", "clearance")
            for member in confirmation_members
        ),
    )


def resolve_side(status: str, *confirmation_members: str) -> str:
    # Shared side classifier for the reset/reentry/rebuild/restore status families. The
    # clearance-side set is the confirmation-side set with "confirmation" swapped for
    # "clearance"; confirmation membership wins, so a confirmation-only token (e.g.
    # "just-rererestored") resolves to confirmation even though the swap also lands it
    # in clearance. Returns "none" for anything unrecognized.
    confirmation, clearance = _side_sets(confirmation_members)
    if status in confirmation:
        return "confirmation"
    if status in clearance:
        return "clearance"
    return "none"


def closure_forecast_reset_reentry_side_from_status(status: str) -> str:
    return resolve_side(
        status,
        "pending-confirmation-reentry",
        "reentered-confirmation",
    )


def closure_forecast_reset_reentry_side_from_recovery_status(status: str) -> str:
    return resolve_side(
        status,
        "recovering-confirmation-reset",
        "reentering-confirmation",
    )


def closure_forecast_reset_reentry_side_from_event(event: dict) -> str:
    side = closure_forecast_reset_reentry_side_from_status(
        event.get("closure_forecast_reset_reentry_status", "none")
    )
    if side != "none":
        return side
    return closure_forecast_reset_reentry_side_from_recovery_status(
        event.get("closure_forecast_reset_refresh_recovery_status", "none")
    )


def closure_forecast_event_matches_target_state(event: dict, target: dict) -> bool:
    return (
        event.get("key") == queue_identity(target)
        and event.get("class_key") == target_class_key(target)
        and float(event.get("closure_forecast_reweight_score", 0.0) or 0.0)
        == float(target.get("closure_forecast_reweight_score", 0.0) or 0.0)
        and event.get("closure_forecast_reweight_direction", "neutral")
        == target.get("closure_forecast_reweight_direction", "neutral")
        and event.get("closure_forecast_reset_refresh_recovery_status", "none")
        == target.get("closure_forecast_reset_refresh_recovery_status", "none")
        and event.get("closure_forecast_reset_reentry_status", "none")
        == target.get("closure_forecast_reset_reentry_status", "none")
        and event.get("closure_forecast_reset_reentry_persistence_status", "none")
        == target.get("closure_forecast_reset_reentry_persistence_status", "none")
        and event.get("closure_forecast_reset_reentry_churn_status", "none")
        == target.get("closure_forecast_reset_reentry_churn_status", "none")
        and event.get(
            "closure_forecast_reset_reentry_freshness_status", "insufficient-data"
        )
        == target.get(
            "closure_forecast_reset_reentry_freshness_status", "insufficient-data"
        )
        and event.get("closure_forecast_reset_reentry_reset_status", "none")
        == target.get("closure_forecast_reset_reentry_reset_status", "none")
        and event.get("closure_forecast_reset_reentry_refresh_recovery_status", "none")
        == target.get("closure_forecast_reset_reentry_refresh_recovery_status", "none")
        and event.get("closure_forecast_reset_reentry_rebuild_status", "none")
        == target.get("closure_forecast_reset_reentry_rebuild_status", "none")
        and event.get(
            "closure_forecast_reset_reentry_rebuild_persistence_status", "none"
        )
        == target.get(
            "closure_forecast_reset_reentry_rebuild_persistence_status", "none"
        )
        and event.get("closure_forecast_reset_reentry_rebuild_churn_status", "none")
        == target.get("closure_forecast_reset_reentry_rebuild_churn_status", "none")
        and event.get(
            "closure_forecast_reset_reentry_rebuild_freshness_status",
            "insufficient-data",
        )
        == target.get(
            "closure_forecast_reset_reentry_rebuild_freshness_status",
            "insufficient-data",
        )
        and event.get("closure_forecast_reset_reentry_rebuild_reset_status", "none")
        == target.get("closure_forecast_reset_reentry_rebuild_reset_status", "none")
        and event.get(
            "closure_forecast_reset_reentry_rebuild_refresh_recovery_status", "none"
        )
        == target.get(
            "closure_forecast_reset_reentry_rebuild_refresh_recovery_status", "none"
        )
        and event.get("closure_forecast_reset_reentry_rebuild_reentry_status", "none")
        == target.get("closure_forecast_reset_reentry_rebuild_reentry_status", "none")
        and event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_persistence_status", "none"
        )
        == target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_persistence_status", "none"
        )
        and event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_churn_status", "none"
        )
        == target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_churn_status", "none"
        )
        and event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_freshness_status",
            "insufficient-data",
        )
        == target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_freshness_status",
            "insufficient-data",
        )
        and event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_reset_status", "none"
        )
        == target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_reset_status", "none"
        )
        and event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status",
            "none",
        )
        == target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status",
            "none",
        )
        and event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_status", "none"
        )
        == target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_status", "none"
        )
        and event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_status",
            "none",
        )
        == target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_status",
            "none",
        )
        and event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_churn_status",
            "none",
        )
        == target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_churn_status",
            "none",
        )
        and event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_status",
            "insufficient-data",
        )
        == target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_status",
            "insufficient-data",
        )
        and event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_reset_status",
            "none",
        )
        == target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_reset_status",
            "none",
        )
        and event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_status",
            "none",
        )
        == target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_status",
            "none",
        )
        and event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status",
            "none",
        )
        == target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status",
            "none",
        )
        and event.get(
            "closure_forecast_reacquisition_freshness_status", "insufficient-data"
        )
        == target.get(
            "closure_forecast_reacquisition_freshness_status", "insufficient-data"
        )
        and event.get("closure_forecast_persistence_reset_status", "none")
        == target.get("closure_forecast_persistence_reset_status", "none")
        and event.get("transition_closure_likely_outcome", "none")
        == target.get("transition_closure_likely_outcome", "none")
    )


def current_closure_forecast_event_for_target(target: dict) -> dict:
    return {
        "key": queue_identity(target),
        "class_key": target_class_key(target),
        "label": target_label(target),
        "generated_at": "",
        "closure_forecast_reweight_score": target.get(
            "closure_forecast_reweight_score", 0.0
        ),
        "closure_forecast_reweight_direction": target.get(
            "closure_forecast_reweight_direction",
            "neutral",
        ),
        "transition_closure_likely_outcome": target.get(
            "transition_closure_likely_outcome",
            "none",
        ),
        "class_reweight_transition_status": target.get(
            "class_reweight_transition_status",
            "none",
        ),
        "class_transition_resolution_status": target.get(
            "class_transition_resolution_status",
            "none",
        ),
        "closure_forecast_hysteresis_status": target.get(
            "closure_forecast_hysteresis_status",
            "none",
        ),
        "closure_forecast_momentum_status": target.get(
            "closure_forecast_momentum_status",
            "insufficient-data",
        ),
        "closure_forecast_stability_status": target.get(
            "closure_forecast_stability_status",
            "watch",
        ),
        "closure_forecast_freshness_status": target.get(
            "closure_forecast_freshness_status",
            "insufficient-data",
        ),
        "closure_forecast_decay_status": target.get(
            "closure_forecast_decay_status",
            "none",
        ),
        "closure_forecast_refresh_recovery_status": target.get(
            "closure_forecast_refresh_recovery_status",
            "none",
        ),
        "closure_forecast_reacquisition_status": target.get(
            "closure_forecast_reacquisition_status",
            "none",
        ),
        "closure_forecast_reacquisition_persistence_status": target.get(
            "closure_forecast_reacquisition_persistence_status",
            "none",
        ),
        "closure_forecast_recovery_churn_status": target.get(
            "closure_forecast_recovery_churn_status",
            "none",
        ),
        "closure_forecast_reacquisition_freshness_status": target.get(
            "closure_forecast_reacquisition_freshness_status",
            "insufficient-data",
        ),
        "closure_forecast_persistence_reset_status": target.get(
            "closure_forecast_persistence_reset_status",
            "none",
        ),
        "closure_forecast_reset_refresh_recovery_status": target.get(
            "closure_forecast_reset_refresh_recovery_status",
            "none",
        ),
        "closure_forecast_reset_reentry_status": target.get(
            "closure_forecast_reset_reentry_status",
            "none",
        ),
        "closure_forecast_reset_reentry_persistence_status": target.get(
            "closure_forecast_reset_reentry_persistence_status",
            "none",
        ),
        "closure_forecast_reset_reentry_churn_status": target.get(
            "closure_forecast_reset_reentry_churn_status",
            "none",
        ),
        "closure_forecast_reset_reentry_freshness_status": target.get(
            "closure_forecast_reset_reentry_freshness_status",
            "insufficient-data",
        ),
        "closure_forecast_reset_reentry_reset_status": target.get(
            "closure_forecast_reset_reentry_reset_status",
            "none",
        ),
        "closure_forecast_reset_reentry_refresh_recovery_status": target.get(
            "closure_forecast_reset_reentry_refresh_recovery_status",
            "none",
        ),
        "closure_forecast_reset_reentry_rebuild_status": target.get(
            "closure_forecast_reset_reentry_rebuild_status",
            "none",
        ),
        "closure_forecast_reset_reentry_rebuild_persistence_status": target.get(
            "closure_forecast_reset_reentry_rebuild_persistence_status",
            "none",
        ),
        "closure_forecast_reset_reentry_rebuild_churn_status": target.get(
            "closure_forecast_reset_reentry_rebuild_churn_status",
            "none",
        ),
        "closure_forecast_reset_reentry_rebuild_freshness_status": target.get(
            "closure_forecast_reset_reentry_rebuild_freshness_status",
            "insufficient-data",
        ),
        "closure_forecast_reset_reentry_rebuild_reset_status": target.get(
            "closure_forecast_reset_reentry_rebuild_reset_status",
            "none",
        ),
        "closure_forecast_reset_reentry_rebuild_refresh_recovery_status": target.get(
            "closure_forecast_reset_reentry_rebuild_refresh_recovery_status",
            "none",
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_status": target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_status",
            "none",
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_persistence_status": target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_persistence_status",
            "none",
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_churn_status": target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_churn_status",
            "none",
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_freshness_status": target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_freshness_status",
            "insufficient-data",
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_reset_status": target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_reset_status",
            "none",
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status": target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status",
            "none",
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_status": target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_status",
            "none",
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_status": target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_status",
            "none",
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_churn_status": target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_churn_status",
            "none",
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_status": target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_status",
            "insufficient-data",
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_reset_status": target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_reset_status",
            "none",
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_status": target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_status",
            "none",
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status",
            "none",
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": target.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status",
            "none",
        ),
    }


def ordered_reset_reentry_events_for_target(
    target: dict,
    closure_forecast_events: list[dict],
) -> list[dict]:
    class_key = target_class_key(target)
    matching_events = [
        event
        for event in closure_forecast_events
        if event.get("class_key") == class_key
    ][:CLASS_RESET_REENTRY_PERSISTENCE_WINDOW_RUNS]
    if not matching_events:
        return [current_closure_forecast_event_for_target(target)]

    current_index = next(
        (
            index
            for index, event in enumerate(matching_events)
            if event.get("generated_at", "") == ""
            and event.get("key") == queue_identity(target)
        ),
        None,
    )
    if current_index is not None:
        if current_index == 0:
            return matching_events
        current_event = matching_events[current_index]
        remainder = (
            matching_events[:current_index] + matching_events[current_index + 1 :]
        )
        return [current_event, *remainder][:CLASS_RESET_REENTRY_PERSISTENCE_WINDOW_RUNS]

    matching_index = next(
        (
            index
            for index, event in enumerate(matching_events)
            if closure_forecast_event_matches_target_state(event, target)
        ),
        None,
    )
    if matching_index is not None:
        if matching_index == 0:
            return matching_events
        current_event = matching_events[matching_index]
        remainder = (
            matching_events[:matching_index] + matching_events[matching_index + 1 :]
        )
        return [current_event, *remainder][:CLASS_RESET_REENTRY_PERSISTENCE_WINDOW_RUNS]

    return [
        current_closure_forecast_event_for_target(target),
        *matching_events,
    ][:CLASS_RESET_REENTRY_PERSISTENCE_WINDOW_RUNS]


def closure_forecast_reset_reentry_side_from_persistence_status(status: str) -> str:
    return resolve_side(
        status,
        "holding-confirmation-reentry",
        "sustained-confirmation-reentry",
    )


def closure_forecast_reset_reentry_memory_side_from_event(event: dict) -> str:
    side = closure_forecast_reset_reentry_side_from_persistence_status(
        event.get("closure_forecast_reset_reentry_persistence_status", "none")
    )
    if side != "none":
        return side
    return closure_forecast_reset_reentry_side_from_event(event)


def reset_reentry_event_is_confirmation_like(event: dict) -> bool:
    event_side = closure_forecast_reset_reentry_memory_side_from_event(event)
    persistence_status = event.get(
        "closure_forecast_reset_reentry_persistence_status", "none"
    )
    return (
        event.get("closure_forecast_reset_reentry_status", "none")
        in {"pending-confirmation-reentry", "reentered-confirmation"}
        or (
            persistence_status
            in {
                "just-reentered",
                "holding-confirmation-reentry",
                "sustained-confirmation-reentry",
            }
            and event_side == "confirmation"
        )
        or event.get("closure_forecast_hysteresis_status", "none")
        in {"pending-confirmation", "confirmed-confirmation"}
        or event.get("transition_closure_likely_outcome", "none") == "confirm-soon"
    )


def reset_reentry_event_is_clearance_like(event: dict) -> bool:
    event_side = closure_forecast_reset_reentry_memory_side_from_event(event)
    persistence_status = event.get(
        "closure_forecast_reset_reentry_persistence_status", "none"
    )
    return (
        event.get("closure_forecast_reset_reentry_status", "none")
        in {"pending-clearance-reentry", "reentered-clearance"}
        or (
            persistence_status
            in {
                "just-reentered",
                "holding-clearance-reentry",
                "sustained-clearance-reentry",
            }
            and event_side == "clearance"
        )
        or event.get("closure_forecast_hysteresis_status", "none")
        in {"pending-clearance", "confirmed-clearance"}
        or event.get("transition_closure_likely_outcome", "none")
        in {"clear-risk", "expire-risk"}
    )


def reset_reentry_event_has_evidence(event: dict) -> bool:
    return (
        reset_reentry_event_is_confirmation_like(event)
        or reset_reentry_event_is_clearance_like(event)
        or event.get("closure_forecast_reset_reentry_churn_status", "none")
        in {"watch", "churn", "blocked"}
    )


def reset_reentry_event_signal_label(event: dict) -> str:
    if reset_reentry_event_is_confirmation_like(event):
        return "confirmation-like"
    if reset_reentry_event_is_clearance_like(event):
        return "clearance-like"
    return "neutral"


def closure_forecast_reset_reentry_freshness_reason(
    freshness_status: str,
    weighted_reset_reentry_evidence_count: float,
    recent_window_weight_share: float,
    decayed_confirmation_rate: float,
    decayed_clearance_rate: float,
) -> str:
    if freshness_status == "fresh":
        return (
            "Recent reset re-entry evidence is still current enough to trust, with "
            f"{recent_window_weight_share:.0%} of the weighted signal coming from the latest "
            f"{CLASS_RESET_REENTRY_FRESHNESS_WINDOW_RUNS} runs."
        )
    if freshness_status == "mixed-age":
        return (
            "Reset re-entry memory is still useful, but it is partly aging: "
            f"{recent_window_weight_share:.0%} of the weighted signal is recent and the rest is older carry-forward."
        )
    if freshness_status == "stale":
        return "Older reset re-entry strength is carrying more of the signal than recent runs, so it should not keep stronger posture alive on memory alone."
    return (
        "Reset re-entry memory is still too lightly exercised to judge freshness, with "
        f"{weighted_reset_reentry_evidence_count:.2f} weighted reset re-entry run(s), "
        f"{decayed_confirmation_rate:.0%} confirmation-like signal, and {decayed_clearance_rate:.0%} clearance-like signal."
    )


def recent_reset_reentry_signal_mix(
    weighted_reset_reentry_evidence_count: float,
    weighted_confirmation_like: float,
    weighted_clearance_like: float,
    recent_window_weight_share: float,
) -> str:
    return (
        f"{weighted_reset_reentry_evidence_count:.2f} weighted reset re-entry run(s) with "
        f"{weighted_confirmation_like:.2f} confirmation-like, {weighted_clearance_like:.2f} clearance-like, "
        f"and {recent_window_weight_share:.0%} of the signal from the freshest runs."
    )


def closure_forecast_reset_reentry_rebuild_side_from_status(status: str) -> str:
    return resolve_side(
        status,
        "pending-confirmation-rebuild",
        "rebuilt-confirmation-reentry",
    )


def closure_forecast_reset_reentry_rebuild_side_from_recovery_status(
    status: str,
) -> str:
    return resolve_side(
        status,
        "recovering-confirmation-reentry-reset",
        "rebuilding-confirmation-reentry",
    )


def closure_forecast_reset_reentry_refresh_path_label(event: dict) -> str:
    rebuild_status = (
        event.get("closure_forecast_reset_reentry_rebuild_status", "none") or "none"
    )
    if rebuild_status != "none":
        return rebuild_status
    recovery_status = (
        event.get("closure_forecast_reset_reentry_refresh_recovery_status", "none")
        or "none"
    )
    if recovery_status != "none":
        return recovery_status
    reset_status = (
        event.get("closure_forecast_reset_reentry_reset_status", "none") or "none"
    )
    if reset_status != "none":
        return reset_status
    reentry_status = (
        event.get("closure_forecast_reset_reentry_status", "none") or "none"
    )
    if reentry_status != "none":
        return reentry_status
    likely_outcome = event.get("transition_closure_likely_outcome", "none") or "none"
    if likely_outcome != "none":
        return likely_outcome
    return "hold"


def closure_forecast_reset_reentry_rebuild_side_from_persistence_status(
    status: str,
) -> str:
    return resolve_side(
        status,
        "holding-confirmation-rebuild",
        "sustained-confirmation-rebuild",
    )


def closure_forecast_reset_reentry_rebuild_side_from_event(event: dict) -> str:
    side = closure_forecast_reset_reentry_rebuild_side_from_persistence_status(
        event.get("closure_forecast_reset_reentry_rebuild_persistence_status", "none")
    )
    if side != "none":
        return side
    side = closure_forecast_reset_reentry_rebuild_side_from_status(
        event.get("closure_forecast_reset_reentry_rebuild_status", "none")
    )
    if side != "none":
        return side
    return closure_forecast_reset_reentry_rebuild_side_from_recovery_status(
        event.get("closure_forecast_reset_reentry_refresh_recovery_status", "none")
    )


def closure_forecast_reset_reentry_rebuild_path_label(event: dict) -> str:
    persistence_status = (
        event.get("closure_forecast_reset_reentry_rebuild_persistence_status", "none")
        or "none"
    )
    if persistence_status != "none":
        return persistence_status
    churn_status = (
        event.get("closure_forecast_reset_reentry_rebuild_churn_status", "none")
        or "none"
    )
    if churn_status != "none":
        return churn_status
    rebuild_status = (
        event.get("closure_forecast_reset_reentry_rebuild_status", "none") or "none"
    )
    if rebuild_status != "none":
        return rebuild_status
    recovery_status = (
        event.get("closure_forecast_reset_reentry_refresh_recovery_status", "none")
        or "none"
    )
    if recovery_status != "none":
        return recovery_status
    reset_status = (
        event.get("closure_forecast_reset_reentry_reset_status", "none") or "none"
    )
    if reset_status != "none":
        return reset_status
    reentry_status = (
        event.get("closure_forecast_reset_reentry_status", "none") or "none"
    )
    if reentry_status != "none":
        return reentry_status
    likely_outcome = event.get("transition_closure_likely_outcome", "none") or "none"
    if likely_outcome != "none":
        return likely_outcome
    return "hold"


def closure_forecast_reset_reentry_rebuild_reentry_refresh_path_label(
    event: dict,
) -> str:
    restore_status = (
        event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_status", "none"
        )
        or "none"
    )
    if restore_status != "none":
        return restore_status
    refresh_status = (
        event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status",
            "none",
        )
        or "none"
    )
    if refresh_status != "none":
        return refresh_status
    reset_status = (
        event.get("closure_forecast_reset_reentry_rebuild_reentry_reset_status", "none")
        or "none"
    )
    if reset_status != "none":
        return reset_status
    score = float(event.get("closure_forecast_reweight_score", 0.0) or 0.0)
    direction = normalized_closure_forecast_direction(
        event.get("closure_forecast_reweight_direction", "neutral"),
        score,
    )
    freshness = event.get(
        "closure_forecast_reset_reentry_rebuild_reentry_freshness_status",
        "insufficient-data",
    )
    if direction == "supporting-confirmation":
        return f"{freshness} confirmation"
    if direction == "supporting-clearance":
        return f"{freshness} clearance"
    likely_outcome = event.get("transition_closure_likely_outcome", "none") or "none"
    if likely_outcome != "none":
        return likely_outcome
    return "hold"


def closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_status(
    status: str,
) -> str:
    return resolve_side(
        status,
        "pending-confirmation-rebuild-reentry-rererestore",
        "rererestored-confirmation-rebuild-reentry",
    )


def closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_side_from_refresh_recovery_status(
    status: str,
) -> str:
    return resolve_side(
        status,
        "recovering-confirmation-rebuild-reentry-rerestore-reset",
        "rererestoring-confirmation-rebuild-reentry",
    )


def closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_persistence_status(
    status: str,
) -> str:
    return resolve_side(
        status,
        "just-rererestored",
        "holding-confirmation-rebuild-reentry-rererestore",
        "sustained-confirmation-rebuild-reentry-rererestore",
    )


def closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_event(
    event: dict,
) -> str:
    side = closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_persistence_status(
        event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status",
            "none",
        )
    )
    if side != "none":
        return side
    side = closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_status(
        event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status",
            "none",
        )
    )
    if side != "none":
        return side
    return closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_side_from_refresh_recovery_status(
        event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_status",
            "none",
        )
    )


def closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_path_label(
    event: dict,
) -> str:
    persistence_status = (
        event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status",
            "none",
        )
        or "none"
    )
    if persistence_status != "none":
        return persistence_status
    churn_status = (
        event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status",
            "none",
        )
        or "none"
    )
    if churn_status != "none":
        return churn_status
    rererestore_status = (
        event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status",
            "none",
        )
        or "none"
    )
    if rererestore_status != "none":
        return rererestore_status
    refresh_status = (
        event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_status",
            "none",
        )
        or "none"
    )
    if refresh_status != "none":
        return refresh_status
    rerestore_status = (
        event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status",
            "none",
        )
        or "none"
    )
    if rerestore_status != "none":
        return rerestore_status
    rerestore_reset_status = (
        event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_status",
            "none",
        )
        or "none"
    )
    if rerestore_reset_status != "none":
        return rerestore_reset_status
    likely_outcome = event.get("transition_closure_likely_outcome", "none") or "none"
    if likely_outcome != "none":
        return likely_outcome
    return "hold"


def closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_path_label(
    event: dict,
) -> str:
    rerererestore_status = (
        event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status",
            "none",
        )
        or "none"
    )
    if rerererestore_status != "none":
        return rerererestore_status
    refresh_status = (
        event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status",
            "none",
        )
        or "none"
    )
    if refresh_status != "none":
        return refresh_status
    rererestore_status = (
        event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status",
            "none",
        )
        or "none"
    )
    if rererestore_status != "none":
        return rererestore_status
    rererestore_reset_status = (
        event.get(
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status",
            "none",
        )
        or "none"
    )
    if rererestore_reset_status != "none":
        return rererestore_reset_status
    likely_outcome = event.get("transition_closure_likely_outcome", "none") or "none"
    if likely_outcome != "none":
        return likely_outcome
    return "hold"


def recommendation_bucket(item: dict) -> int:
    lane = item.get("lane", "")
    if lane == "blocked" and item.get("kind") == "setup":
        return 0
    if lane == "blocked":
        return 1
    if lane == "urgent" and item.get("aging_status") in {"stale", "chronic"}:
        return 2
    if lane == "urgent" and item.get("reopened"):
        return 3
    if lane == "urgent":
        return 4
    if lane == "ready":
        return 5
    return 6


def queue_identity(item: dict) -> str:
    if item.get("item_id"):
        return item["item_id"]
    repo = item.get("repo", "")
    title = item.get("title", "")
    return f"{repo}:{title}"
