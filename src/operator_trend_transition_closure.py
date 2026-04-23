from __future__ import annotations

from typing import Any, Callable


def transition_closure_confidence_for_target(
    target: dict[str, Any],
    history_meta: dict[str, Any],
    *,
    target_specific_normalization_noise: Callable[[dict[str, Any], dict[str, Any]], bool],
    clamp_round: Callable[[float, float, float], float],
) -> tuple[float, str, str, list[str]]:
    transition_status = target.get("class_reweight_transition_status", "none")
    health_status = target.get(
        "class_transition_health_status",
        history_meta.get("current_transition_health_status", "none"),
    )
    resolution_status = target.get(
        "class_transition_resolution_status",
        history_meta.get("current_transition_resolution_status", "none"),
    )
    momentum_status = target.get("class_trust_momentum_status", "insufficient-data")
    stability_status = target.get("class_reweight_stability_status", "watch")
    reweight_score = float(target.get("class_trust_reweight_score", 0.0) or 0.0)
    transition_age_runs = int(
        target.get("class_transition_age_runs", history_meta.get("class_transition_age_runs", 0))
        or 0
    )
    transition_score_delta = float(history_meta.get("transition_score_delta", 0.0) or 0.0)
    current_strengthening = bool(history_meta.get("current_transition_strengthening", False))
    active_pending = transition_status in {"pending-support", "pending-caution"}
    local_noise = target_specific_normalization_noise(target, history_meta)
    blocked = (
        transition_status == "blocked"
        or health_status == "blocked"
        or resolution_status == "blocked"
        or (transition_status == "pending-support" and local_noise)
    )
    matching_momentum = (
        transition_status == "pending-support" and momentum_status == "sustained-support"
    ) or (transition_status == "pending-caution" and momentum_status == "sustained-caution")

    if not active_pending:
        if blocked:
            blocked_reason = (
                target.get("class_transition_resolution_reason")
                or target.get("class_transition_health_reason")
                or "Local target instability is preventing positive class strengthening."
            )
            return 0.05, "low", "blocked", [blocked_reason]
        return 0.05, "low", "none", []

    if history_meta.get("matching_transition_event_count", 0) < 2:
        return (
            0.25,
            "low",
            "insufficient-data",
            [
                "Not enough pending-transition history exists yet to judge whether this class signal is likely to confirm."
            ],
        )

    score = 0.25
    if health_status == "building":
        score += 0.15
    if matching_momentum:
        score += 0.10
    if stability_status == "stable":
        score += 0.10
    if transition_score_delta >= 0.05:
        score += 0.10
    if transition_age_runs in {1, 2}:
        score += 0.05
    if health_status == "holding":
        score -= 0.10
    if health_status == "stalled":
        score -= 0.20
    if transition_age_runs >= 3 and not current_strengthening:
        score -= 0.10
    if abs(reweight_score) < 0.10:
        score -= 0.10
    if momentum_status == "reversing":
        score -= 0.10
    if blocked:
        score -= 0.20

    score = clamp_round(score, 0.05, 0.95)
    if score >= 0.75:
        label = "high"
    elif score >= 0.45:
        label = "medium"
    else:
        label = "low"

    if blocked:
        outcome = "blocked"
    elif transition_age_runs >= 3 and not current_strengthening:
        outcome = "expire-risk"
    elif label == "high" and matching_momentum:
        outcome = "confirm-soon"
    elif label == "low" and (
        abs(reweight_score) < 0.10
        or history_meta.get("current_lost_pending_support", False)
        or history_meta.get("current_transition_neutral", False)
        or history_meta.get("current_transition_reversed", False)
    ):
        outcome = "clear-risk"
    else:
        outcome = "hold"

    reasons: list[str] = []
    health_reason = target.get("class_transition_health_reason", "")
    if health_status == "building":
        reasons.append(
            health_reason or "The pending class signal is still building in the same direction."
        )
    elif health_status == "holding":
        reasons.append(
            health_reason
            or "The pending class signal is still visible, but it is no longer getting stronger."
        )
    elif health_status == "stalled":
        reasons.append(
            health_reason or "The pending class signal has lingered without enough strengthening."
        )
    elif health_status == "blocked":
        reasons.append(
            health_reason or "Local target instability is blocking this pending class transition."
        )

    if matching_momentum:
        reasons.append("Recent class momentum is still aligned with the pending direction.")
    elif stability_status == "stable":
        reasons.append(
            "Class guidance is stable even though the pending signal has not confirmed yet."
        )
    elif momentum_status == "reversing":
        reasons.append("Recent class momentum is reversing against the pending direction.")

    if transition_score_delta >= 0.05:
        reasons.append(
            f"The reweight score improved by {transition_score_delta:.2f} in the pending direction."
        )
    elif transition_age_runs >= 3 and not current_strengthening:
        reasons.append(
            "The pending signal has lasted three or more runs without same-direction strengthening."
        )
    elif abs(reweight_score) < 0.10:
        reasons.append("The live reweight score is now close to neutral.")

    if blocked:
        reasons.append(
            target.get("class_transition_resolution_reason")
            or health_reason
            or "Local target instability is still overriding positive class strengthening."
        )

    return score, label, outcome, reasons[:4]


def apply_transition_closure_control(
    target: dict[str, Any],
    *,
    trust_policy: str,
    trust_policy_reason: str,
    health_status: str,
    health_reason: str,
    resolution_status: str,
    resolution_reason: str,
    transition_status: str,
    transition_reason: str,
    policy_debt_status: str,
    policy_debt_reason: str,
    class_normalization_status: str,
    class_normalization_reason: str,
    closure_confidence_label: str,
    closure_likely_outcome: str,
    pending_debt_status: str,
) -> tuple[str, str, str, str, str, str, str, str, str, str, str, str]:
    if (
        transition_status in {"pending-support", "pending-caution"}
        and closure_likely_outcome in {"clear-risk", "expire-risk"}
        and closure_confidence_label == "low"
        and pending_debt_status == "active-debt"
    ):
        clear_reason = (
            "This pending class signal is low-confidence inside a class that keeps accumulating "
            "unresolved pending states, so the pending state was cleared back to the weaker posture."
        )
        if transition_status == "pending-support":
            reverted_policy = target.get("pre_class_normalization_trust_policy", trust_policy)
            reverted_reason = target.get(
                "pre_class_normalization_trust_policy_reason", trust_policy_reason
            )
            return (
                "none",
                "",
                "cleared",
                clear_reason,
                "none",
                clear_reason,
                reverted_policy,
                clear_reason if reverted_policy == "verify-first" else reverted_reason,
                policy_debt_status,
                policy_debt_reason,
                "candidate",
                clear_reason,
            )
        return (
            "none",
            "",
            "cleared",
            clear_reason,
            "none",
            clear_reason,
            trust_policy,
            trust_policy_reason,
            "watch",
            clear_reason,
            class_normalization_status,
            class_normalization_reason,
        )

    return (
        health_status,
        health_reason,
        resolution_status,
        resolution_reason,
        transition_status,
        transition_reason,
        trust_policy,
        trust_policy_reason,
        policy_debt_status,
        policy_debt_reason,
        class_normalization_status,
        class_normalization_reason,
    )
