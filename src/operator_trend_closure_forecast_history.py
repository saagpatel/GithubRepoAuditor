from __future__ import annotations

from typing import Any, Callable


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
