from __future__ import annotations

from typing import Any, Callable


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
