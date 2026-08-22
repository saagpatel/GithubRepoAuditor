from __future__ import annotations

from statistics import median
from typing import Any

LOOKBACK_RUNS = 20
DISPLAY_WINDOW_RUNS = 10
MIN_HISTORY_RUNS = 4
MIN_JUDGED_RECOMMENDATIONS = 3
MAX_EXAMPLES = 3


def build_operator_effectiveness_bundle(
    *,
    state_history: list[dict],
    calibration_history: list[dict],
    campaign_history: list[dict],
    review_history: list[dict],
    evidence_events: list[dict],
) -> dict[str, Any]:
    ordered_history = _chronological(state_history)[:LOOKBACK_RUNS]
    sufficient_history = len(ordered_history) >= MIN_HISTORY_RUNS
    high_pressure_history = _high_pressure_history(ordered_history)
    high_pressure_series = [item["high_pressure_count"] for item in high_pressure_history]
    high_pressure_trend_status = _high_pressure_trend_status(high_pressure_series)
    high_pressure_trend_summary = _high_pressure_trend_summary(
        high_pressure_trend_status,
        high_pressure_history,
    )

    judged = _judged_recommendation_counts(calibration_history)
    judged_count = judged["judged"]
    enough_calibration = judged_count >= MIN_JUDGED_RECOMMENDATIONS
    review_to_action_closure_rate = _review_to_action_closure_rate(campaign_history, sufficient_history)
    median_runs_to_quiet_after_escalation = _median_runs_to_quiet_after_escalation(
        high_pressure_series,
        sufficient_history,
    )
    repeated_regression_rate = _repeated_regression_rate(ordered_history, sufficient_history)
    recommendation_validation_rate = _recommendation_validation_rate(judged, enough_calibration)
    noisy_guidance_rate = _noisy_guidance_rate(judged, enough_calibration)

    recent_reopened_recommendations = _recent_reopened_recommendations(calibration_history)
    recent_closed_actions = _recent_closed_actions(campaign_history)
    recent_regression_examples = _recent_regression_examples(evidence_events, ordered_history, review_history)

    portfolio_outcomes_summary = {
        "review_to_action_closure_rate": review_to_action_closure_rate,
        "median_runs_to_quiet_after_escalation": median_runs_to_quiet_after_escalation,
        "repeated_regression_rate": repeated_regression_rate,
        "summary": _portfolio_outcomes_summary(
            review_to_action_closure_rate,
            median_runs_to_quiet_after_escalation,
            repeated_regression_rate,
        ),
    }
    operator_effectiveness_summary = {
        "recommendation_validation_rate": recommendation_validation_rate,
        "noisy_guidance_rate": noisy_guidance_rate,
        "summary": _operator_effectiveness_summary(
            recommendation_validation_rate,
            noisy_guidance_rate,
        ),
    }
    return {
        "portfolio_outcomes_summary": portfolio_outcomes_summary,
        "operator_effectiveness_summary": operator_effectiveness_summary,
        "high_pressure_queue_history": high_pressure_history[-DISPLAY_WINDOW_RUNS:],
        "high_pressure_queue_trend_status": high_pressure_trend_status,
        "high_pressure_queue_trend_summary": high_pressure_trend_summary,
        "recent_reopened_recommendations": recent_reopened_recommendations,
        "recent_closed_actions": recent_closed_actions,
        "recent_regression_examples": recent_regression_examples,
    }


def _chronological(history: list[dict]) -> list[dict]:
    return sorted(history or [], key=lambda item: str(item.get("generated_at") or item.get("run_id") or ""))


def _high_pressure_history(history: list[dict]) -> list[dict]:
    points: list[dict] = []
    for item in history:
        summary = item.get("operator_summary") or {}
        blocked = int(summary.get("blocked_count", 0) or 0)
        urgent = int(summary.get("urgent_count", 0) or 0)
        points.append(
            {
                "run_id": item.get("run_id", ""),
                "generated_at": item.get("generated_at", ""),
                "blocked_count": blocked,
                "urgent_count": urgent,
                "high_pressure_count": blocked + urgent,
            }
        )
    return points


def _high_pressure_trend_status(series: list[int]) -> str:
    if len(series) < MIN_HISTORY_RUNS:
        return "insufficient-evidence"
    if max(series) == 0:
        return "quiet"
    if len(series) >= 3 and sum(series[-3:]) == 0:
        return "quiet"
    midpoint = max(1, len(series) // 2)
    first_half = series[:midpoint]
    second_half = series[midpoint:]
    first_avg = sum(first_half) / len(first_half)
    second_avg = sum(second_half) / len(second_half)
    if second_avg <= first_avg - 0.75 or series[-1] <= max(0, series[0] - 1):
        return "improving"
    if second_avg >= first_avg + 0.75 or series[-1] >= series[0] + 1:
        return "worsening"
    return "stable"


def _high_pressure_trend_summary(status: str, history: list[dict]) -> str:
    if status == "insufficient-evidence":
        return "Not enough historical operator runs are recorded yet to judge whether blocked and urgent queue pressure is improving."
    if not history:
        return "No high-pressure queue history is recorded yet."
    latest = history[-1]["high_pressure_count"]
    if status == "quiet":
        return "Blocked and urgent queue pressure is quiet across the recent operator window."
    if status == "improving":
        return f"Blocked and urgent queue pressure is improving, with {latest} high-pressure item(s) in the latest run."
    if status == "worsening":
        return f"Blocked and urgent queue pressure is worsening, with {latest} high-pressure item(s) in the latest run."
    return f"Blocked and urgent queue pressure is stable, with {latest} high-pressure item(s) in the latest run."


def _review_to_action_closure_rate(campaign_history: list[dict], sufficient_history: bool) -> dict[str, Any]:
    if not sufficient_history:
        return _insufficient_rate("Not enough recent operator history is available to judge whether reviewed actions are closing cleanly.")
    actions: dict[str, dict] = {}
    ordered = sorted(
        campaign_history or [],
        key=lambda item: (str(item.get("generated_at", "")), str(item.get("action_id", ""))),
    )[-200:]
    for item in ordered:
        action_id = str(item.get("action_id") or "").strip()
        if not action_id:
            continue
        actions[action_id] = item
    if not actions:
        return _insufficient_rate("No managed campaign actions were recorded in the recent window, so closure rate cannot be judged yet.")
    closed_states = {"resolved", "cancelled", "closed"}
    closed = sum(
        1
        for item in actions.values()
        if str(item.get("lifecycle_state") or "").strip() in closed_states
        and str(item.get("reconciliation_outcome") or "").strip() != "reopened"
        and not item.get("reopened_at")
    )
    denominator = len(actions)
    value = closed / denominator if denominator else None
    return {
        "status": "measured",
        "value": value,
        "numerator": closed,
        "denominator": denominator,
        "summary": f"{closed} of {denominator} recently managed campaign actions are currently closed without a later reopen.",
    }


def _median_runs_to_quiet_after_escalation(series: list[int], sufficient_history: bool) -> dict[str, Any]:
    if not sufficient_history:
        return {
            "status": "insufficient-evidence",
            "value": None,
            "episodes": 0,
            "summary": "Not enough recent operator history is available to judge how quickly escalation pressure quiets down.",
        }
    episodes: list[int] = []
    open_run: int | None = None
    for idx, count in enumerate(series):
        previous = series[idx - 1] if idx > 0 else 0
        if previous == 0 and count > 0 and open_run is None:
            open_run = idx
        elif open_run is not None and count == 0:
            episodes.append(idx - open_run)
            open_run = None
    if not episodes:
        return {
            "status": "insufficient-evidence",
            "value": None,
            "episodes": 0,
            "summary": "No completed escalation-to-quiet episode was recorded in the recent operator window.",
        }
    value = float(median(episodes))
    return {
        "status": "measured",
        "value": value,
        "episodes": len(episodes),
        "summary": f"Recent escalation episodes returned to a quiet blocked+urgent queue in a median of {value:.1f} run(s).",
    }


def _repeated_regression_rate(history: list[dict], sufficient_history: bool) -> dict[str, Any]:
    if not sufficient_history:
        return _insufficient_rate("Not enough recent operator history is available to judge whether attention is reopening after resolution.")
    reopened = 0
    resolved = 0
    for item in history:
        summary = item.get("operator_summary") or {}
        reopened += int(summary.get("reopened_attention_count", 0) or 0)
        resolved += int(summary.get("resolved_attention_count", 0) or 0)
    value = reopened / max(resolved, 1)
    return {
        "status": "measured",
        "value": value,
        "numerator": reopened,
        "denominator": max(resolved, 1),
        "summary": f"Repeated regressions reopened {reopened} attention item(s) against {resolved} resolved item(s) in the recent operator window.",
    }


def _judged_recommendation_counts(calibration_history: list[dict]) -> dict[str, int]:
    if calibration_history:
        latest = _chronological(calibration_history)[-1].get("operator_summary") or {}
        validated = int(latest.get("validated_recommendation_count", 0) or 0)
        partial = int(latest.get("partially_validated_recommendation_count", 0) or 0)
        unresolved = int(latest.get("unresolved_recommendation_count", 0) or 0)
        reopened = int(latest.get("reopened_recommendation_count", 0) or 0)
        judged = validated + partial + unresolved + reopened
        return {
            "validated": validated,
            "partial": partial,
            "unresolved": unresolved,
            "reopened": reopened,
            "judged": judged,
        }
    return {"validated": 0, "partial": 0, "unresolved": 0, "reopened": 0, "judged": 0}


def _recommendation_validation_rate(counts: dict[str, int], enough_calibration: bool) -> dict[str, Any]:
    if not enough_calibration:
        return _insufficient_rate("Fewer than three judged recommendations are available, so validation rate is still too noisy to trust.")
    value = (counts["validated"] + counts["partial"]) / max(counts["judged"], 1)
    return {
        "status": "measured",
        "value": value,
        "numerator": counts["validated"] + counts["partial"],
        "denominator": counts["judged"],
        "summary": (
            f"{counts['validated'] + counts['partial']} of {counts['judged']} judged recommendations validated "
            "fully or partially in the recent confidence window."
        ),
    }


def _noisy_guidance_rate(counts: dict[str, int], enough_calibration: bool) -> dict[str, Any]:
    if not enough_calibration:
        return _insufficient_rate("Fewer than three judged recommendations are available, so guidance noise cannot be judged confidently yet.")
    value = counts["reopened"] / max(counts["judged"], 1)
    return {
        "status": "measured",
        "value": value,
        "numerator": counts["reopened"],
        "denominator": counts["judged"],
        "summary": f"{counts['reopened']} of {counts['judged']} judged recommendations reopened in the recent confidence window.",
    }


def _recent_reopened_recommendations(calibration_history: list[dict]) -> list[dict]:
    if not calibration_history:
        return []
    latest = _chronological(calibration_history)[-1].get("operator_summary") or {}
    items = []
    for item in latest.get("recent_validation_outcomes") or []:
        if item.get("outcome") != "reopened":
            continue
        items.append(
            {
                "repo": item.get("repo", ""),
                "title": item.get("title") or item.get("item_id") or "Recommendation reopened",
                "confidence_label": item.get("confidence_label", ""),
                "summary": item.get("summary")
                or "A recently judged recommendation reopened after an earlier positive signal.",
            }
        )
        if len(items) == MAX_EXAMPLES:
            break
    return items


def _recent_closed_actions(campaign_history: list[dict]) -> list[dict]:
    closed = []
    ordered = sorted(campaign_history or [], key=lambda item: str(item.get("generated_at") or ""), reverse=True)
    seen: set[str] = set()
    for item in ordered:
        action_id = str(item.get("action_id") or "").strip()
        if not action_id or action_id in seen:
            continue
        if str(item.get("lifecycle_state") or "") not in {"resolved", "cancelled", "closed"}:
            continue
        seen.add(action_id)
        closed.append(
            {
                "repo": item.get("repo", item.get("repo_id", "")),
                "action_id": action_id,
                "title": item.get("title") or item.get("summary") or "Managed action closed",
                "summary": item.get("closed_reason")
                or item.get("summary")
                or "A managed campaign action closed in the recent window.",
            }
        )
        if len(closed) == MAX_EXAMPLES:
            break
    return closed


def _recent_regression_examples(
    evidence_events: list[dict],
    history: list[dict],
    review_history: list[dict],
) -> list[dict]:
    examples = []
    for item in evidence_events or []:
        outcome = str(item.get("outcome") or "").strip()
        event_type = str(item.get("event_type") or "").strip()
        if outcome not in {"reopened", "drifted"} and event_type not in {"open", "reopened"}:
            continue
        examples.append(
            {
                "repo": item.get("repo", item.get("repo_id", "")),
                "title": item.get("title") or item.get("action_id") or "Recent regression",
                "summary": item.get("summary")
                or item.get("drift_state")
                or "A previously moving item reopened or drifted again.",
            }
        )
        if len(examples) == MAX_EXAMPLES:
            return examples
    for item in reversed(history):
        summary = item.get("operator_summary") or {}
        if int(summary.get("reopened_attention_count", 0) or 0) <= 0:
            continue
        examples.append(
            {
                "repo": summary.get("primary_target", {}).get("repo", ""),
                "title": summary.get("primary_target", {}).get("title", "Reopened operator attention"),
                "summary": summary.get("resolution_evidence_summary")
                or "An attention item reopened after an earlier quiet or resolved state.",
            }
        )
        if len(examples) == MAX_EXAMPLES:
            return examples
    for item in review_history or []:
        if not item:
            continue
        reason = str(item.get("reason") or item.get("summary") or "").lower()
        if "reopen" not in reason and "regress" not in reason:
            continue
        examples.append(
            {
                "repo": item.get("repo", ""),
                "title": item.get("title", "Recent regression"),
                "summary": item.get("summary") or item.get("reason") or "A reviewed item regressed again in the recent window.",
            }
        )
        if len(examples) == MAX_EXAMPLES:
            return examples
    return examples


def _portfolio_outcomes_summary(
    closure_rate: dict[str, Any],
    quiet_median: dict[str, Any],
    regression_rate: dict[str, Any],
) -> str:
    if (
        closure_rate.get("status") == "insufficient-evidence"
        and quiet_median.get("status") == "insufficient-evidence"
        and regression_rate.get("status") == "insufficient-evidence"
    ):
        return "Operator outcomes need a little more history before closure and regression patterns can be judged confidently."
    parts = []
    if closure_rate.get("status") == "measured" and closure_rate.get("value") is not None:
        parts.append(f"Managed action closure is at {closure_rate['value']:.0%}")
    if quiet_median.get("status") == "measured" and quiet_median.get("value") is not None:
        parts.append(f"blocked and urgent pressure quiets in about {quiet_median['value']:.1f} run(s)")
    if regression_rate.get("status") == "measured" and regression_rate.get("value") is not None:
        parts.append(f"repeated regression is running at {regression_rate['value']:.0%}")
    if not parts:
        return "Operator outcomes are recorded, but the current window is still too thin for a confident summary."
    return "; ".join(parts) + "."


def _operator_effectiveness_summary(
    validation_rate: dict[str, Any],
    noisy_guidance_rate: dict[str, Any],
) -> str:
    if (
        validation_rate.get("status") == "insufficient-evidence"
        and noisy_guidance_rate.get("status") == "insufficient-evidence"
    ):
        return "Recommendation effectiveness needs more judged outcomes before the confidence calibration can be trusted."
    parts = []
    if validation_rate.get("status") == "measured" and validation_rate.get("value") is not None:
        parts.append(f"recommendation validation is at {validation_rate['value']:.0%}")
    if noisy_guidance_rate.get("status") == "measured" and noisy_guidance_rate.get("value") is not None:
        parts.append(f"guidance noise is at {noisy_guidance_rate['value']:.0%}")
    if not parts:
        return "Recommendation effectiveness is recorded, but the judged window is still too small for a confident read."
    return "; ".join(parts) + "."


def _insufficient_rate(summary: str) -> dict[str, Any]:
    return {
        "status": "insufficient-evidence",
        "value": None,
        "numerator": 0,
        "denominator": 0,
        "summary": summary,
    }
