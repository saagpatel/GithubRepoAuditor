from __future__ import annotations

from typing import Any, Callable


def build_class_reweight_events(
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
                "class_trust_reweight_score": current_primary_target.get(
                    "class_trust_reweight_score", 0.0
                ),
                "class_trust_reweight_direction": current_primary_target.get(
                    "class_trust_reweight_direction", "neutral"
                ),
                "policy_debt_status": current_primary_target.get("policy_debt_status", "none"),
                "class_normalization_status": current_primary_target.get(
                    "class_normalization_status", "none"
                ),
            }
        )
    for entry in history[: history_window_runs - 1]:
        summary = entry.get("operator_summary") or {}
        primary_target = summary.get("primary_target") or {}
        if not primary_target:
            continue
        reweight_direction = (
            summary.get("primary_target_class_trust_reweight_direction")
            or primary_target.get("class_trust_reweight_direction")
            or ""
        )
        reweight_score = summary.get("primary_target_class_trust_reweight_score")
        if reweight_score is None:
            reweight_score = primary_target.get("class_trust_reweight_score")
        if reweight_score is None and not reweight_direction:
            continue
        events.append(
            {
                "key": queue_identity(primary_target),
                "class_key": target_class_key(primary_target),
                "label": target_label(primary_target),
                "generated_at": entry.get("generated_at", ""),
                "class_trust_reweight_score": reweight_score or 0.0,
                "class_trust_reweight_direction": reweight_direction or "neutral",
                "policy_debt_status": summary.get("primary_target_policy_debt_status", "none"),
                "class_normalization_status": summary.get(
                    "primary_target_class_normalization_status", "none"
                ),
            }
        )
    return sorted(events, key=lambda item: item.get("generated_at", ""), reverse=True)


def build_class_transition_events(
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
                "class_trust_reweight_score": current_primary_target.get(
                    "class_trust_reweight_score", 0.0
                ),
                "class_trust_reweight_direction": current_primary_target.get(
                    "class_trust_reweight_direction", "neutral"
                ),
                "class_trust_momentum_status": current_primary_target.get(
                    "class_trust_momentum_status", "insufficient-data"
                ),
                "class_reweight_stability_status": current_primary_target.get(
                    "class_reweight_stability_status", "watch"
                ),
                "class_reweight_transition_status": current_primary_target.get(
                    "class_reweight_transition_status", "none"
                ),
                "class_reweight_transition_reason": current_primary_target.get(
                    "class_reweight_transition_reason", ""
                ),
                "class_transition_health_status": current_primary_target.get(
                    "class_transition_health_status", "none"
                ),
                "class_transition_resolution_status": current_primary_target.get(
                    "class_transition_resolution_status", "none"
                ),
                "trust_policy": current_primary_target.get("trust_policy", "monitor"),
                "decision_memory_status": current_primary_target.get(
                    "decision_memory_status", "new"
                ),
                "last_outcome": current_primary_target.get("last_outcome", "no-change"),
            }
        )
    historical_events: list[dict[str, Any]] = []
    for entry in history[: history_window_runs - 1]:
        summary = entry.get("operator_summary") or {}
        primary_target = summary.get("primary_target") or {}
        if not primary_target:
            continue
        historical_events.append(
            {
                "key": queue_identity(primary_target),
                "class_key": target_class_key(primary_target),
                "label": target_label(primary_target),
                "generated_at": entry.get("generated_at", ""),
                "class_trust_reweight_score": summary.get(
                    "primary_target_class_trust_reweight_score",
                    primary_target.get("class_trust_reweight_score", 0.0),
                ),
                "class_trust_reweight_direction": summary.get(
                    "primary_target_class_trust_reweight_direction",
                    primary_target.get("class_trust_reweight_direction", "neutral"),
                ),
                "class_trust_momentum_status": summary.get(
                    "primary_target_class_trust_momentum_status",
                    primary_target.get("class_trust_momentum_status", "insufficient-data"),
                ),
                "class_reweight_stability_status": summary.get(
                    "primary_target_class_reweight_stability_status",
                    primary_target.get("class_reweight_stability_status", "watch"),
                ),
                "class_reweight_transition_status": summary.get(
                    "primary_target_class_reweight_transition_status",
                    primary_target.get("class_reweight_transition_status", "none"),
                ),
                "class_reweight_transition_reason": summary.get(
                    "primary_target_class_reweight_transition_reason",
                    primary_target.get("class_reweight_transition_reason", ""),
                ),
                "class_transition_health_status": summary.get(
                    "primary_target_class_transition_health_status",
                    primary_target.get("class_transition_health_status", "none"),
                ),
                "class_transition_resolution_status": summary.get(
                    "primary_target_class_transition_resolution_status",
                    primary_target.get("class_transition_resolution_status", "none"),
                ),
                "trust_policy": summary.get(
                    "primary_target_trust_policy",
                    primary_target.get("trust_policy", "monitor"),
                ),
                "decision_memory_status": summary.get(
                    "decision_memory_status",
                    primary_target.get("decision_memory_status", "new"),
                ),
                "last_outcome": summary.get(
                    "primary_target_last_outcome",
                    primary_target.get("last_outcome", "no-change"),
                ),
            }
        )
    historical_events.sort(key=lambda item: item.get("generated_at", ""), reverse=True)
    return events + historical_events


def target_class_transition_history(
    target: dict[str, Any],
    transition_events: list[dict[str, Any]],
    *,
    target_class_key: Callable[[dict[str, Any]], str],
    normalized_class_reweight_direction: Callable[[str, float], str],
    consecutive_transition_runs: Callable[[list[str], str], int],
    current_transition_strengthening: Callable[[str, list[float]], bool],
    pending_transition_direction: Callable[[str], str],
    clamp_round: Callable[[float], float],
    policy_flip_count: Callable[[list[str]], int],
    class_pending_resolution_window_runs: int,
    class_transition_closure_window_runs: int,
) -> dict[str, Any]:
    class_key = target_class_key(target)
    matching_events = [event for event in transition_events if event.get("class_key") == class_key][
        : class_pending_resolution_window_runs + 1
    ]
    statuses = [
        event.get("class_reweight_transition_status", "none") or "none" for event in matching_events
    ]
    scores = [float(event.get("class_trust_reweight_score", 0.0) or 0.0) for event in matching_events]
    target_policies = [
        policy
        for policy in (
            event.get("trust_policy") for event in matching_events[:class_transition_closure_window_runs]
        )
        if policy
    ]
    directions = [
        normalized_class_reweight_direction(
            event.get("class_trust_reweight_direction", "neutral"),
            float(event.get("class_trust_reweight_score", 0.0) or 0.0),
        )
        for event in matching_events
    ]
    health_statuses = [event.get("class_transition_health_status", "none") or "none" for event in matching_events]
    resolution_statuses = [
        event.get("class_transition_resolution_status", "none") or "none"
        for event in matching_events
    ]
    current_status = statuses[0] if statuses else "none"
    class_transition_age_runs = 0
    current_strengthening_flag = False
    recent_pending_status = "none"
    recent_pending_age_runs = 0
    recent_pending_direction = "neutral"

    if current_status in {"pending-support", "pending-caution"}:
        class_transition_age_runs = consecutive_transition_runs(statuses, current_status)
        current_strengthening_flag = current_transition_strengthening(
            current_status,
            scores[:class_transition_age_runs],
        )
    elif len(statuses) > 1 and statuses[1] in {"pending-support", "pending-caution"}:
        recent_pending_status = statuses[1]
        recent_pending_age_runs = consecutive_transition_runs(statuses[1:], recent_pending_status)
        recent_pending_direction = pending_transition_direction(recent_pending_status)
        class_transition_age_runs = recent_pending_age_runs
    elif current_status == "none":
        class_transition_age_runs = 0

    if current_status in {"pending-support", "pending-caution"}:
        recent_pending_status = current_status
        recent_pending_age_runs = class_transition_age_runs
        recent_pending_direction = pending_transition_direction(current_status)

    current_direction = directions[0] if directions else "neutral"
    current_score = scores[0] if scores else 0.0
    current_neutral = abs(current_score) < 0.10 or current_direction == "neutral"
    pending_direction = (
        recent_pending_direction
        if recent_pending_direction != "neutral"
        else pending_transition_direction(current_status)
    )
    current_reversed = (
        pending_direction != "neutral"
        and current_direction != "neutral"
        and current_direction != pending_direction
    )
    current_lost_pending_support = False
    if recent_pending_status == "pending-support" and current_status not in {
        "pending-support",
        "confirmed-support",
    }:
        current_lost_pending_support = (
            current_score < 0.20 or current_direction != "supporting-normalization"
        )
    if recent_pending_status == "pending-caution" and current_status not in {
        "pending-caution",
        "confirmed-caution",
    }:
        current_lost_pending_support = (
            current_score > -0.20 or current_direction != "supporting-caution"
        )
    if current_status == "pending-support" and len(scores) > 1:
        transition_score_delta = clamp_round(scores[0] - scores[1])
    elif current_status == "pending-caution" and len(scores) > 1:
        transition_score_delta = clamp_round(scores[1] - scores[0])
    else:
        transition_score_delta = 0.0
    return {
        "class_transition_age_runs": class_transition_age_runs,
        "recent_transition_path": " -> ".join(statuses),
        "recent_transition_score_path": " -> ".join(
            f"{score:.2f}" for score in scores[:class_transition_closure_window_runs]
        ),
        "current_transition_status": current_status,
        "current_transition_health_status": health_statuses[0] if health_statuses else "none",
        "current_transition_resolution_status": resolution_statuses[0] if resolution_statuses else "none",
        "recent_pending_status": recent_pending_status,
        "recent_pending_age_runs": recent_pending_age_runs,
        "current_transition_strengthening": current_strengthening_flag,
        "current_transition_direction": current_direction,
        "current_transition_score": current_score,
        "transition_score_delta": transition_score_delta,
        "matching_transition_event_count": len(matching_events),
        "recent_policy_flip_count": policy_flip_count(target_policies),
        "recent_reopened": any(
            event.get("decision_memory_status") == "reopened"
            or event.get("last_outcome") == "reopened"
            for event in matching_events[:class_transition_closure_window_runs]
        ),
        "current_transition_neutral": current_neutral,
        "current_transition_reversed": current_reversed,
        "current_lost_pending_support": current_lost_pending_support,
    }


def consecutive_transition_runs(statuses: list[str], target_status: str) -> int:
    count = 0
    for status in statuses:
        if status != target_status:
            break
        count += 1
    return count


def pending_transition_direction(transition_status: str) -> str:
    if transition_status == "pending-support":
        return "supporting-normalization"
    if transition_status == "pending-caution":
        return "supporting-caution"
    return "neutral"


def current_transition_strengthening(transition_status: str, scores: list[float]) -> bool:
    if not scores:
        return False
    if len(scores) == 1:
        return True
    current_score = scores[0]
    previous_score = scores[1]
    if transition_status == "pending-support":
        return current_score - previous_score >= 0.05
    if transition_status == "pending-caution":
        return previous_score - current_score >= 0.05
    return False
