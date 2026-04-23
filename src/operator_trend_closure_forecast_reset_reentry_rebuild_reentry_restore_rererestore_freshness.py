from __future__ import annotations

from typing import Any, Callable


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
    aligned_recent_event_count = sum(
        1
        for event in relevant_events[
            :class_reset_reentry_rebuild_reentry_restore_rererestore_freshness_window_runs
        ][:2]
        if (
            closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_side_from_event(
                event
            )
            == current_side
            and current_side != "none"
        )
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
        "has_fresh_aligned_recent_evidence": (
            freshness_status == "fresh" and aligned_recent_event_count >= 2
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
