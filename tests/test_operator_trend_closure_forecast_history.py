from __future__ import annotations

from src.operator_trend_closure_forecast_history import target_closure_forecast_history


def _target_class_key(item: dict) -> str:
    return item.get("class_key", "")


def _signal(event: dict) -> float:
    return float(event.get("signal", 0.0))


def _normalized(direction: str, _score: float) -> str:
    return direction


def _flip_count(directions: list[str]) -> int:
    return sum(1 for left, right in zip(directions, directions[1:]) if left != right)


def _majority(directions: list[str]) -> str:
    if not directions:
        return "neutral"
    return max(set(directions), key=directions.count)


def _reversing(current: str, earlier: str) -> bool:
    return current != "neutral" and earlier != "neutral" and current != earlier


def _clamp(value: float, *, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def test_target_closure_forecast_history_detects_sustained_confirmation() -> None:
    summary = target_closure_forecast_history(
        {"class_key": "lane:kind"},
        [
            {
                "class_key": "lane:kind",
                "signal": 0.40,
                "closure_forecast_reweight_direction": "supporting-confirmation",
                "closure_forecast_reweight_score": 0.40,
            },
            {
                "class_key": "lane:kind",
                "signal": 0.30,
                "closure_forecast_reweight_direction": "supporting-confirmation",
                "closure_forecast_reweight_score": 0.30,
            },
        ],
        target_class_key=_target_class_key,
        closure_forecast_signal_from_event=_signal,
        normalized_closure_forecast_direction=_normalized,
        class_direction_flip_count=_flip_count,
        closure_forecast_direction_majority=_majority,
        closure_forecast_direction_reversing=_reversing,
        clamp_round=_clamp,
        class_closure_forecast_transition_window_runs=4,
    )

    assert summary["closure_forecast_momentum_status"] == "sustained-confirmation"
    assert summary["closure_forecast_stability_status"] == "stable"


def test_target_closure_forecast_history_detects_unstable_when_flipping() -> None:
    summary = target_closure_forecast_history(
        {"class_key": "lane:kind"},
        [
            {
                "class_key": "lane:kind",
                "signal": 0.40,
                "closure_forecast_reweight_direction": "supporting-confirmation",
                "closure_forecast_reweight_score": 0.40,
            },
            {
                "class_key": "lane:kind",
                "signal": -0.35,
                "closure_forecast_reweight_direction": "supporting-clearance",
                "closure_forecast_reweight_score": -0.35,
            },
            {
                "class_key": "lane:kind",
                "signal": 0.25,
                "closure_forecast_reweight_direction": "supporting-confirmation",
                "closure_forecast_reweight_score": 0.25,
            },
        ],
        target_class_key=_target_class_key,
        closure_forecast_signal_from_event=_signal,
        normalized_closure_forecast_direction=_normalized,
        class_direction_flip_count=_flip_count,
        closure_forecast_direction_majority=_majority,
        closure_forecast_direction_reversing=_reversing,
        clamp_round=_clamp,
        class_closure_forecast_transition_window_runs=4,
    )

    assert summary["closure_forecast_momentum_status"] == "unstable"
    assert summary["closure_forecast_stability_status"] == "oscillating"
