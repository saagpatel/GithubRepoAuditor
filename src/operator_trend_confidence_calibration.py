from __future__ import annotations

from typing import Any, Callable

from src.operator_trend_support import (
    ATTENTION_LANES,
    CALIBRATION_WINDOW_RUNS,
    VALIDATION_WINDOW_RUNS,
)


def build_confidence_calibration(
    history: list[dict[str, Any]],
    *,
    queue_identity: Callable[[dict[str, Any]], str],
    target_label: Callable[[dict[str, Any]], str],
) -> dict[str, Any]:
    ordered_runs = sorted(
        [
            {
                "run_id": entry.get("run_id", ""),
                "generated_at": entry.get("generated_at", ""),
                "operator_summary": entry.get("operator_summary") or {},
                "operator_queue": entry.get("operator_queue") or [],
            }
            for entry in history[:CALIBRATION_WINDOW_RUNS]
        ],
        key=lambda item: item.get("generated_at", ""),
    )
    evaluations: list[dict[str, Any]] = []
    for index, run in enumerate(ordered_runs):
        summary = run.get("operator_summary") or {}
        target = summary.get("primary_target") or {}
        confidence_label = summary.get("primary_target_confidence_label", "")
        if not target or confidence_label not in {"high", "medium", "low"}:
            continue
        outcome, validated_in_runs = _calibration_outcome(
            run,
            ordered_runs[index + 1 : index + 1 + VALIDATION_WINDOW_RUNS],
            queue_identity=queue_identity,
        )
        evaluations.append(
            {
                "run_id": run.get("run_id", ""),
                "generated_at": run.get("generated_at", ""),
                "target_label": target_label(target),
                "confidence_label": confidence_label,
                "outcome": outcome,
                "validated_in_runs": validated_in_runs,
                "health_state": _confidence_health_state(confidence_label, outcome),
            }
        )

    judged = [item for item in evaluations if item.get("outcome") != "insufficient_future_runs"]
    high_judged = [item for item in judged if item.get("confidence_label") == "high"]
    medium_judged = [item for item in judged if item.get("confidence_label") == "medium"]
    low_all = [item for item in evaluations if item.get("confidence_label") == "low"]
    high_hits = sum(1 for item in high_judged if item.get("health_state") == "healthy")
    medium_hits = sum(1 for item in medium_judged if item.get("health_state") == "healthy")
    low_cautions = sum(1 for item in low_all if item.get("health_state") == "healthy")
    reopened_high_count = sum(
        1
        for item in evaluations
        if item.get("confidence_label") == "high" and item.get("outcome") == "reopened"
    )
    high_confidence_hit_rate = round(high_hits / len(high_judged), 2) if high_judged else 0.0
    medium_confidence_hit_rate = (
        round(medium_hits / len(medium_judged), 2) if medium_judged else 0.0
    )
    low_confidence_caution_rate = round(low_cautions / len(low_all), 2) if low_all else 0.0
    reopened_recommendation_count = sum(1 for item in judged if item.get("outcome") == "reopened")
    confidence_validation_status = _confidence_validation_status(
        judged_count=len(judged),
        high_confidence_hit_rate=high_confidence_hit_rate,
        reopened_recommendation_count=reopened_recommendation_count,
        reopened_high_count=reopened_high_count,
    )
    recent_validation_outcomes = [
        {
            "run_id": item.get("run_id", ""),
            "target_label": item.get("target_label", ""),
            "confidence_label": item.get("confidence_label", "low"),
            "outcome": item.get("outcome", "unresolved"),
            "validated_in_runs": item.get("validated_in_runs"),
        }
        for item in sorted(judged, key=lambda item: item.get("generated_at", ""), reverse=True)[:5]
    ]
    return {
        "confidence_validation_status": confidence_validation_status,
        "confidence_window_runs": len(ordered_runs),
        "validated_recommendation_count": sum(
            1 for item in evaluations if item.get("outcome") == "validated"
        ),
        "partially_validated_recommendation_count": sum(
            1 for item in evaluations if item.get("outcome") == "partially_validated"
        ),
        "unresolved_recommendation_count": sum(
            1 for item in evaluations if item.get("outcome") == "unresolved"
        ),
        "reopened_recommendation_count": sum(
            1 for item in evaluations if item.get("outcome") == "reopened"
        ),
        "insufficient_future_runs_count": sum(
            1 for item in evaluations if item.get("outcome") == "insufficient_future_runs"
        ),
        "high_confidence_hit_rate": high_confidence_hit_rate,
        "medium_confidence_hit_rate": medium_confidence_hit_rate,
        "low_confidence_caution_rate": low_confidence_caution_rate,
        "recent_validation_outcomes": recent_validation_outcomes,
        "confidence_calibration_summary": _confidence_calibration_summary(
            confidence_validation_status=confidence_validation_status,
            high_confidence_hit_rate=high_confidence_hit_rate,
            medium_confidence_hit_rate=medium_confidence_hit_rate,
            low_confidence_caution_rate=low_confidence_caution_rate,
            reopened_recommendation_count=sum(
                1 for item in evaluations if item.get("outcome") == "reopened"
            ),
            judged_count=len(judged),
        ),
    }


def _calibration_outcome(
    run: dict[str, Any],
    future_runs: list[dict[str, Any]],
    *,
    queue_identity: Callable[[dict[str, Any]], str],
) -> tuple[str, int | None]:
    if len(future_runs) < VALIDATION_WINDOW_RUNS:
        return "insufficient_future_runs", None
    summary = run.get("operator_summary") or {}
    target = summary.get("primary_target") or {}
    target_key = queue_identity(target)
    original_lane = _target_lane(run, target_key, target, queue_identity=queue_identity)
    future_matches = [
        _run_target_match(candidate, target_key, queue_identity=queue_identity)
        for candidate in future_runs
    ]
    future_lanes = [match.get("lane") if match else None for match in future_matches]
    clear_index = next(
        (
            index
            for index, lane in enumerate(future_lanes, start=1)
            if lane is None or lane not in ATTENTION_LANES
        ),
        None,
    )
    if clear_index is not None and any(
        lane in ATTENTION_LANES for lane in future_lanes[clear_index:]
    ):
        return "reopened", VALIDATION_WINDOW_RUNS
    if clear_index is not None:
        final_match = future_matches[-1]
        if final_match is None:
            return "validated", clear_index
        return "partially_validated", clear_index
    if _has_pressure_drop(original_lane, future_lanes):
        return "partially_validated", _first_pressure_drop_run(original_lane, future_lanes)
    return "unresolved", VALIDATION_WINDOW_RUNS


def _run_target_match(
    run: dict[str, Any],
    target_key: str,
    *,
    queue_identity: Callable[[dict[str, Any]], str],
) -> dict[str, Any] | None:
    for item in run.get("operator_queue") or []:
        if queue_identity(item) == target_key:
            return item
    return None


def _target_lane(
    run: dict[str, Any],
    target_key: str,
    target: dict[str, Any],
    *,
    queue_identity: Callable[[dict[str, Any]], str],
) -> str:
    match = _run_target_match(run, target_key, queue_identity=queue_identity)
    if match:
        return str(match.get("lane", ""))
    return str(target.get("lane", ""))


def _lane_pressure(lane: str | None) -> int:
    if lane == "blocked":
        return 3
    if lane == "urgent":
        return 2
    if lane == "ready":
        return 1
    if lane == "deferred":
        return 0
    return -1


def _has_pressure_drop(original_lane: str, future_lanes: list[str | None]) -> bool:
    origin_pressure = _lane_pressure(original_lane)
    return any(lane is not None and _lane_pressure(lane) < origin_pressure for lane in future_lanes)


def _first_pressure_drop_run(original_lane: str, future_lanes: list[str | None]) -> int | None:
    origin_pressure = _lane_pressure(original_lane)
    for index, lane in enumerate(future_lanes, start=1):
        if lane is not None and _lane_pressure(lane) < origin_pressure:
            return index
    return None


def _confidence_health_state(confidence_label: str, outcome: str) -> str:
    if confidence_label == "high":
        if outcome == "validated":
            return "healthy"
        if outcome in {"unresolved", "reopened"}:
            return "overstated"
        return "mixed"
    if confidence_label == "medium":
        if outcome in {"validated", "partially_validated"}:
            return "healthy"
        return "mixed"
    if confidence_label == "low":
        if outcome in {"unresolved", "reopened", "insufficient_future_runs"}:
            return "healthy"
        return "mixed"
    return "mixed"


def _confidence_validation_status(
    *,
    judged_count: int,
    high_confidence_hit_rate: float,
    reopened_recommendation_count: int,
    reopened_high_count: int,
) -> str:
    if judged_count < 4:
        return "insufficient-data"
    if high_confidence_hit_rate < 0.50 or reopened_high_count >= 2:
        return "noisy"
    if high_confidence_hit_rate >= 0.70 and reopened_recommendation_count == 0:
        return "healthy"
    return "mixed"


def _confidence_calibration_summary(
    *,
    confidence_validation_status: str,
    high_confidence_hit_rate: float,
    medium_confidence_hit_rate: float,
    low_confidence_caution_rate: float,
    reopened_recommendation_count: int,
    judged_count: int,
) -> str:
    if confidence_validation_status == "healthy":
        return (
            f"Recent high-confidence recommendations are validating well: "
            f"{high_confidence_hit_rate:.0%} high-confidence hit rate across {judged_count} judged runs with no reopen noise."
        )
    if confidence_validation_status == "mixed":
        return (
            f"Confidence is still useful, but recent outcomes are mixed: "
            f"{high_confidence_hit_rate:.0%} high-confidence hit rate, "
            f"{medium_confidence_hit_rate:.0%} medium-confidence hit rate, and {reopened_recommendation_count} reopened outcome(s)."
        )
    if confidence_validation_status == "noisy":
        return (
            f"Recent high-confidence guidance has been noisy: "
            f"{high_confidence_hit_rate:.0%} high-confidence hit rate and {reopened_recommendation_count} reopened outcome(s) in the judged window."
        )
    return (
        "The confidence model does not have enough judged history yet to say whether recent confidence has been validating. "
        f"Current low-confidence caution hit rate is {low_confidence_caution_rate:.0%}."
    )
