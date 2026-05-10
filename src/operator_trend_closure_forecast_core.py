from __future__ import annotations

from typing import Any, Callable

CLOSURE_FORECAST_EVENT_DEFAULTS: tuple[tuple[str, Any], ...] = (
    ("closure_forecast_reweight_score", 0.0),
    ("closure_forecast_reweight_direction", "neutral"),
    ("transition_closure_likely_outcome", "none"),
    ("class_reweight_transition_status", "none"),
    ("class_transition_resolution_status", "none"),
    ("closure_forecast_reweight_effect", "none"),
    ("closure_forecast_hysteresis_status", "none"),
    ("closure_forecast_momentum_status", "insufficient-data"),
    ("closure_forecast_stability_status", "watch"),
    ("closure_forecast_freshness_status", "insufficient-data"),
    ("closure_forecast_decay_status", "none"),
    ("closure_forecast_refresh_recovery_status", "none"),
    ("closure_forecast_reacquisition_status", "none"),
    ("closure_forecast_reacquisition_persistence_status", "none"),
    ("closure_forecast_recovery_churn_status", "none"),
    ("closure_forecast_reacquisition_freshness_status", "insufficient-data"),
    ("closure_forecast_persistence_reset_status", "none"),
    ("closure_forecast_reset_refresh_recovery_status", "none"),
    ("closure_forecast_reset_reentry_status", "none"),
    ("closure_forecast_reset_reentry_persistence_status", "none"),
    ("closure_forecast_reset_reentry_churn_status", "none"),
    ("closure_forecast_reset_reentry_freshness_status", "insufficient-data"),
    ("closure_forecast_reset_reentry_reset_status", "none"),
    ("closure_forecast_reset_reentry_refresh_recovery_status", "none"),
    ("closure_forecast_reset_reentry_rebuild_status", "none"),
    ("closure_forecast_reset_reentry_rebuild_persistence_status", "none"),
    ("closure_forecast_reset_reentry_rebuild_churn_status", "none"),
    ("closure_forecast_reset_reentry_rebuild_freshness_status", "insufficient-data"),
    ("closure_forecast_reset_reentry_rebuild_reset_status", "none"),
    ("closure_forecast_reset_reentry_rebuild_refresh_recovery_status", "none"),
    ("closure_forecast_reset_reentry_rebuild_reentry_status", "none"),
    ("closure_forecast_reset_reentry_rebuild_reentry_persistence_status", "none"),
    ("closure_forecast_reset_reentry_rebuild_reentry_churn_status", "none"),
    ("closure_forecast_reset_reentry_rebuild_reentry_freshness_status", "insufficient-data"),
    ("closure_forecast_reset_reentry_rebuild_reentry_reset_status", "none"),
    ("closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status", "none"),
    ("closure_forecast_reset_reentry_rebuild_reentry_restore_status", "none"),
    ("closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_status", "none"),
    ("closure_forecast_reset_reentry_rebuild_reentry_restore_churn_status", "none"),
    ("closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_status", "insufficient-data"),
    ("closure_forecast_reset_reentry_rebuild_reentry_restore_reset_status", "none"),
    ("closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_status", "none"),
    ("closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status", "none"),
    ("closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_status", "none"),
    ("closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_status", "none"),
    ("closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status", "insufficient-data"),
    ("closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_status", "none"),
    ("closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_status", "none"),
    ("closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status", "none"),
    ("closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status", "none"),
    ("closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status", "none"),
    ("closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status", "insufficient-data"),
    ("closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status", "none"),
    ("closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status", "none"),
    ("closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status", "none"),
    ("closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status", "none"),
    ("closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status", "none"),
)


def _event_payload_from_source(source: dict[str, Any]) -> dict[str, Any]:
    return {
        field: source.get(field, default)
        for field, default in CLOSURE_FORECAST_EVENT_DEFAULTS
    }


def class_closure_forecast_events(
    history: list[dict[str, Any]],
    *,
    current_primary_target: dict[str, Any],
    current_generated_at: str,
    queue_identity: Callable[[dict[str, Any]], str],
    target_class_key: Callable[[dict[str, Any]], str],
    target_label: Callable[[dict[str, Any]], str],
    history_window_runs: int,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    if current_primary_target and current_primary_target.get("trust_policy"):
        events.append(
            {
                "key": queue_identity(current_primary_target),
                "class_key": target_class_key(current_primary_target),
                "label": target_label(current_primary_target),
                "generated_at": current_generated_at or "",
                **_event_payload_from_source(current_primary_target),
            }
        )

    for entry in history[: history_window_runs - 1]:
        summary = entry.get("operator_summary") or {}
        primary_target = summary.get("primary_target") or {}
        if not primary_target:
            continue

        direction = summary.get(
            "primary_target_closure_forecast_reweight_direction",
            primary_target.get("closure_forecast_reweight_direction", "neutral"),
        )
        score = summary.get(
            "primary_target_closure_forecast_reweight_score",
            primary_target.get("closure_forecast_reweight_score", 0.0),
        )
        if score is None and not direction:
            continue

        event = {
            "key": queue_identity(primary_target),
            "class_key": target_class_key(primary_target),
            "label": target_label(primary_target),
            "generated_at": entry.get("generated_at", ""),
        }
        for field, default in CLOSURE_FORECAST_EVENT_DEFAULTS:
            event[field] = summary.get(
                f"primary_target_{field}",
                primary_target.get(field, default),
            )
        events.append(event)

    return sorted(events, key=lambda item: item.get("generated_at", ""), reverse=True)


def target_closure_forecast_history(
    target: dict[str, Any],
    closure_forecast_events: list[dict[str, Any]],
    *,
    target_class_key: Callable[[dict[str, Any]], str],
    closure_forecast_signal_from_event: Callable[[dict[str, Any]], float],
    normalized_closure_forecast_direction: Callable[[str, float], str],
    class_direction_flip_count: Callable[[list[str]], int],
    closure_forecast_direction_majority: Callable[[list[str]], str],
    closure_forecast_direction_reversing: Callable[[str, str], bool],
    clamp_round: Callable[..., float],
    class_closure_forecast_transition_window_runs: int,
) -> dict[str, Any]:
    class_key = target_class_key(target)
    matching_events = [
        event for event in closure_forecast_events if event.get("class_key") == class_key
    ][:class_closure_forecast_transition_window_runs]
    signals = [closure_forecast_signal_from_event(event) for event in matching_events]
    relevant_signals = [signal for signal in signals if abs(signal) >= 0.05]

    weighted_total = 0.0
    weight_sum = 0.0
    for index, signal in enumerate(signals):
        weight = (1.0, 0.8, 0.6, 0.4)[
            min(index, class_closure_forecast_transition_window_runs - 1)
        ]
        weighted_total += signal * weight
        weight_sum += weight

    momentum_score = clamp_round(
        weighted_total / max(weight_sum, 1.0),
        lower=-0.95,
        upper=0.95,
    )
    directions = [
        normalized_closure_forecast_direction(
            str(event.get("closure_forecast_reweight_direction", "neutral")),
            float(event.get("closure_forecast_reweight_score", 0.0) or 0.0),
        )
        for event in matching_events
    ]
    flip_count = class_direction_flip_count(directions)
    current_direction = directions[0] if directions else "neutral"
    earlier_majority = closure_forecast_direction_majority(directions[1:])
    positive_count = sum(1 for signal in relevant_signals if signal > 0)
    negative_count = sum(1 for signal in relevant_signals if signal < 0)

    if len(relevant_signals) < 2:
        momentum_status = "insufficient-data"
    elif flip_count >= 2:
        momentum_status = "unstable"
    elif closure_forecast_direction_reversing(current_direction, earlier_majority):
        momentum_status = "reversing"
    elif positive_count >= 2 and momentum_score >= 0.20:
        momentum_status = "sustained-confirmation"
    elif negative_count >= 2 and momentum_score <= -0.20:
        momentum_status = "sustained-clearance"
    else:
        momentum_status = "building"

    if flip_count >= 2:
        stability_status = "oscillating"
    elif flip_count == 1 or momentum_status in {"building", "insufficient-data", "reversing"}:
        stability_status = "watch"
    else:
        stability_status = "stable"

    return {
        "closure_forecast_momentum_score": momentum_score,
        "closure_forecast_momentum_status": momentum_status,
        "closure_forecast_stability_status": stability_status,
        "recent_closure_forecast_path": " -> ".join(directions) if directions else "",
        "closure_forecast_direction_flip_count": flip_count,
    }


def apply_closure_forecast_reweighting_control(
    target: dict[str, Any],
    *,
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
    closure_confidence_label: str,
    closure_likely_outcome: str,
    pending_debt_freshness_status: str,
    closure_forecast_reweight_direction: str,
    closure_forecast_reweight_score: float,
    target_specific_normalization_noise: Callable[[dict[str, Any], dict[str, Any]], bool],
) -> tuple[str, str, str, str, str, str, str, str, str, str, str, str, str, str, str]:
    effect = "none"
    effect_reason = ""
    local_noise = target_specific_normalization_noise(target, transition_history_meta)
    transition_age_runs = int(target.get("class_transition_age_runs", 0) or 0)
    current_strengthening = bool(
        transition_history_meta.get("current_transition_strengthening", False)
    )

    if transition_status not in {"pending-support", "pending-caution"}:
        return (
            effect,
            effect_reason,
            closure_likely_outcome,
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

    if closure_forecast_reweight_direction == "supporting-confirmation":
        if (
            pending_debt_freshness_status == "fresh"
            and not local_noise
            and pending_debt_status != "clearing"
        ):
            effect = "confirm-support-strengthened"
            effect_reason = (
                "Fresh class resolution behavior is clean enough to strengthen the pending "
                "forecast, but the pending state still needs Phase 39 persistence before it can confirm."
            )
        elif pending_debt_freshness_status in {"stale", "insufficient-data"}:
            effect = "confirm-support-softened"
            effect_reason = (
                "Older pending-transition evidence is aging out, so it cannot keep strengthening "
                "confirmation support from scratch."
            )
            if closure_likely_outcome == "confirm-soon":
                closure_likely_outcome = "hold"
    elif closure_forecast_reweight_direction == "supporting-clearance":
        if pending_debt_freshness_status in {"fresh", "mixed-age"}:
            effect = "clear-risk-strengthened"
            effect_reason = (
                "Fresh unresolved pending debt is still clustering, so the live pending signal "
                "should be treated as more likely to clear or expire than confirm."
            )
            if closure_likely_outcome not in {"blocked", "insufficient-data"}:
                closure_likely_outcome = (
                    "expire-risk"
                    if transition_age_runs >= 3 and not current_strengthening
                    else "clear-risk"
                )
        else:
            effect = "clear-risk-softened"
            effect_reason = (
                "Older pending-debt patterns are fading, so they should not strengthen "
                "clearance risk from scratch."
            )

    if (
        transition_status in {"pending-support", "pending-caution"}
        and closure_forecast_reweight_direction == "supporting-clearance"
        and closure_confidence_label == "low"
        and pending_debt_status == "active-debt"
    ):
        clear_reason = (
            "This pending class signal is low-confidence inside a class with fresh unresolved "
            "pending debt, so the pending state was cleared back to the weaker posture."
        )
        if transition_status == "pending-support":
            reverted_policy = target.get("pre_class_normalization_trust_policy", trust_policy)
            reverted_reason = target.get(
                "pre_class_normalization_trust_policy_reason", trust_policy_reason
            )
            return (
                "clear-risk-strengthened",
                clear_reason,
                closure_likely_outcome,
                "none",
                "",
                "cleared",
                clear_reason,
                reverted_policy,
                clear_reason if reverted_policy == "verify-first" else reverted_reason,
                pending_debt_status,
                pending_debt_reason,
                policy_debt_status,
                policy_debt_reason,
                "candidate",
                clear_reason,
            )
        return (
            "clear-risk-strengthened",
            clear_reason,
            closure_likely_outcome,
            "none",
            "",
            "cleared",
            clear_reason,
            trust_policy,
            trust_policy_reason,
            pending_debt_status,
            pending_debt_reason,
            "watch",
            clear_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    if local_noise and closure_forecast_reweight_direction == "supporting-confirmation":
        effect = "confirm-support-softened"
        effect_reason = (
            "Local target instability is still overriding healthier class evidence, so the "
            "pending forecast cannot strengthen beyond the existing posture."
        )
        if closure_likely_outcome == "confirm-soon":
            closure_likely_outcome = "hold"

    return (
        effect,
        effect_reason,
        closure_likely_outcome,
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


def pending_debt_freshness_hotspots(
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
            "pending_debt_freshness_status": target.get(
                "pending_debt_freshness_status", "insufficient-data"
            ),
            "decayed_pending_debt_rate": target.get("decayed_pending_debt_rate", 0.0),
            "decayed_pending_resolution_rate": target.get("decayed_pending_resolution_rate", 0.0),
            "recent_pending_signal_mix": target.get("recent_pending_signal_mix", ""),
            "recent_pending_debt_path": target.get("recent_pending_debt_path", ""),
            "dominant_count": target.get("decayed_pending_debt_rate", 0.0),
            "pending_entry_count": len(
                [
                    part
                    for part in (target.get("recent_pending_debt_path", "") or "").split(" -> ")
                    if part
                ]
            ),
        }
        if mode == "fresh":
            current["dominant_count"] = target.get("decayed_pending_resolution_rate", 0.0)
        existing = grouped.get(class_key)
        if existing is None or current["dominant_count"] > existing["dominant_count"]:
            grouped[class_key] = current

    hotspots = list(grouped.values())
    if mode == "fresh":
        hotspots = [
            item
            for item in hotspots
            if item.get("pending_debt_freshness_status") == "fresh"
            and float(item.get("decayed_pending_resolution_rate", 0.0) or 0.0) > 0.0
        ]
        hotspots.sort(
            key=lambda item: (
                -float(item.get("decayed_pending_resolution_rate", 0.0) or 0.0),
                -int(item.get("pending_entry_count", 0) or 0),
                str(item.get("label", "")),
            )
        )
    else:
        hotspots = [
            item
            for item in hotspots
            if item.get("pending_debt_freshness_status") == "stale"
            and float(item.get("decayed_pending_debt_rate", 0.0) or 0.0) > 0.0
        ]
        hotspots.sort(
            key=lambda item: (
                -float(item.get("decayed_pending_debt_rate", 0.0) or 0.0),
                -int(item.get("pending_entry_count", 0) or 0),
                str(item.get("label", "")),
            )
        )
    return hotspots[:5]


def closure_forecast_hotspots(
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
            "closure_forecast_reweight_direction": target.get(
                "closure_forecast_reweight_direction", "neutral"
            ),
            "weighted_pending_resolution_support_score": target.get(
                "weighted_pending_resolution_support_score", 0.0
            ),
            "weighted_pending_debt_caution_score": target.get(
                "weighted_pending_debt_caution_score", 0.0
            ),
            "recent_pending_signal_mix": target.get("recent_pending_signal_mix", ""),
            "recent_pending_debt_path": target.get("recent_pending_debt_path", ""),
            "pending_entry_count": len(
                [
                    part
                    for part in (target.get("recent_pending_debt_path", "") or "").split(" -> ")
                    if part
                ]
            ),
        }
        current["dominant_count"] = current["weighted_pending_resolution_support_score"]
        if mode == "caution":
            current["dominant_count"] = current["weighted_pending_debt_caution_score"]
        existing = grouped.get(class_key)
        if existing is None or current["dominant_count"] > existing["dominant_count"]:
            grouped[class_key] = current

    hotspots = list(grouped.values())
    if mode == "support":
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reweight_direction") == "supporting-confirmation"
        ]
        hotspots.sort(
            key=lambda item: (
                -float(item.get("weighted_pending_resolution_support_score", 0.0) or 0.0),
                -int(item.get("pending_entry_count", 0) or 0),
                str(item.get("label", "")),
            )
        )
    else:
        hotspots = [
            item
            for item in hotspots
            if item.get("closure_forecast_reweight_direction") == "supporting-clearance"
        ]
        hotspots.sort(
            key=lambda item: (
                -float(item.get("weighted_pending_debt_caution_score", 0.0) or 0.0),
                -int(item.get("pending_entry_count", 0) or 0),
                str(item.get("label", "")),
            )
        )
    return hotspots[:5]


__all__ = (
    "CLOSURE_FORECAST_EVENT_DEFAULTS",
    "apply_closure_forecast_reweighting_control",
    "class_closure_forecast_events",
    "closure_forecast_hotspots",
    "pending_debt_freshness_hotspots",
    "target_closure_forecast_history",
)
