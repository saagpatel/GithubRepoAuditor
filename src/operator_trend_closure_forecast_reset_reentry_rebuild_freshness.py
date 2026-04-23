from __future__ import annotations

from typing import Any, Callable


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
