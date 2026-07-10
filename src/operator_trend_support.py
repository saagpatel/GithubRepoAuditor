from __future__ import annotations

LANE_LABELS = {
    "blocked": "Blocked",
    "urgent": "Needs Attention Now",
    "ready": "Ready for Manual Action",
    "deferred": "Safe to Defer",
}

ATTENTION_LANES = {"blocked", "urgent"}

HISTORY_WINDOW_RUNS = 10
CALIBRATION_WINDOW_RUNS = 20
VALIDATION_WINDOW_RUNS = 2
TRUST_RECOVERY_WINDOW_RUNS = 3
EXCEPTION_RETIREMENT_WINDOW_RUNS = 4

DEFAULT_CLASS_WINDOW_RUNS = 4
CLASS_PENDING_DEBT_WINDOW_RUNS = HISTORY_WINDOW_RUNS

(
    CLASS_NORMALIZATION_WINDOW_RUNS,
    CLASS_MEMORY_FRESHNESS_WINDOW_RUNS,
    CLASS_REWEIGHTING_WINDOW_RUNS,
    CLASS_TRANSITION_WINDOW_RUNS,
    CLASS_PENDING_RESOLUTION_WINDOW_RUNS,
    CLASS_TRANSITION_CLOSURE_WINDOW_RUNS,
    PENDING_DEBT_FRESHNESS_WINDOW_RUNS,
    CLASS_CLOSURE_FORECAST_REWEIGHTING_WINDOW_RUNS,
    CLASS_CLOSURE_FORECAST_TRANSITION_WINDOW_RUNS,
    CLASS_CLOSURE_FORECAST_FRESHNESS_WINDOW_RUNS,
    CLASS_CLOSURE_FORECAST_REFRESH_WINDOW_RUNS,
    CLASS_REACQUISITION_PERSISTENCE_WINDOW_RUNS,
    CLASS_REACQUISITION_FRESHNESS_WINDOW_RUNS,
    CLASS_RESET_REENTRY_WINDOW_RUNS,
    CLASS_RESET_REENTRY_PERSISTENCE_WINDOW_RUNS,
    CLASS_RESET_REENTRY_FRESHNESS_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REFRESH_REBUILD_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_PERSISTENCE_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_FRESHNESS_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_REFRESH_REENTRY_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_REENTRY_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_REENTRY_FRESHNESS_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_REENTRY_REFRESH_RESTORE_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_FRESHNESS_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_REFRESH_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_RERESTORE_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_RERESTORE_FRESHNESS_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_RERESTORE_REFRESH_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_RERERESTORE_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_RERERESTORE_FRESHNESS_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_RERERESTORE_REFRESH_WINDOW_RUNS,
    CLASS_RESET_REENTRY_REBUILD_REENTRY_RESTORE_RERERERESTORE_WINDOW_RUNS,
) = (DEFAULT_CLASS_WINDOW_RUNS,) * 33

CLASS_MEMORY_RECENCY_WEIGHTS = (1.0, 1.0, 0.7, 0.7, 0.4, 0.4, 0.4, 0.2, 0.2, 0.2)


def target_class_key(item: dict) -> str:
    return f"{item.get('lane', '')}:{item.get('kind', '') or 'unknown'}"


def normalized_closure_forecast_direction(direction: str, score: float) -> str:
    if direction in {"supporting-confirmation", "supporting-clearance", "neutral"}:
        return direction
    if score >= 0.20:
        return "supporting-confirmation"
    if score <= -0.20:
        return "supporting-clearance"
    return "neutral"


def target_specific_normalization_noise(target: dict, history_meta: dict) -> bool:
    return (
        history_meta.get("recent_reopened", False)
        or history_meta.get("recent_policy_flip_count", 0) > 0
        or target.get("trust_recovery_status") == "blocked"
    )


def clamp_round(value: float, *, lower: float, upper: float) -> float:
    return round(max(lower, min(upper, value)), 2)


def closure_forecast_direction_majority(directions: list[str]) -> str:
    confirmation_count = sum(
        1 for direction in directions if direction == "supporting-confirmation"
    )
    clearance_count = sum(
        1 for direction in directions if direction == "supporting-clearance"
    )
    if confirmation_count > clearance_count:
        return "supporting-confirmation"
    if clearance_count > confirmation_count:
        return "supporting-clearance"
    return "neutral"


def closure_forecast_direction_reversing(
    current_direction: str, earlier_majority: str
) -> bool:
    if current_direction == "neutral" or earlier_majority == "neutral":
        return False
    return current_direction != earlier_majority


def class_direction_flip_count(directions: list[str]) -> int:
    non_neutral = [direction for direction in directions if direction != "neutral"]
    if len(non_neutral) < 2:
        return 0
    return sum(
        1
        for previous, current in zip(non_neutral, non_neutral[1:])
        if current != previous
    )


def target_label(item: dict) -> str:
    repo = f"{item.get('repo')}: " if item.get("repo") else ""
    return f"{repo}{item.get('title', '')}".strip(": ")


GENERIC_RECOMMENDATION_PHRASES = (
    "continue the normal audit/control-center loop",
    "continue the normal operator loop",
    "review the latest state",
    "inspect the latest changes and decide on next action",
    "monitor future audits",
    "open the repo queue details",
)

GENERIC_MONITOR_PHRASES = (
    "keep the operator loop light",
    "keep the operator loop lightweight",
)

GENERIC_BASELINE_PHRASES = (
    "run the next full audit to refresh the baseline",
    "refresh the baseline before relying on incremental results",
)


def is_generic_recommendation(action: str) -> bool:
    normalized = (action or "").strip().lower()
    if not normalized:
        return True
    return any(phrase in normalized for phrase in GENERIC_RECOMMENDATION_PHRASES)


def is_generic_monitor_guidance(action: str) -> bool:
    normalized = (action or "").strip().lower()
    return bool(normalized) and any(
        phrase in normalized for phrase in GENERIC_MONITOR_PHRASES
    )


def is_generic_baseline_guidance(
    action: str, watch_guidance: dict | None = None
) -> bool:
    normalized = (action or "").strip().lower()
    if normalized and any(phrase in normalized for phrase in GENERIC_BASELINE_PHRASES):
        return True
    return not normalized and bool(
        watch_guidance and watch_guidance.get("full_refresh_due")
    )
