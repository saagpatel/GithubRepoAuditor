from __future__ import annotations

from src.operator_trend_closure_forecast_reset_reentry_rebuild_persistence import (
    closure_forecast_reset_reentry_rebuild_churn_for_target,
    closure_forecast_reset_reentry_rebuild_churn_summary,
    closure_forecast_reset_reentry_rebuild_hotspots,
    closure_forecast_reset_reentry_rebuild_persistence_for_target,
    closure_forecast_reset_reentry_rebuild_persistence_summary,
)


def _ordered_reset_reentry_events_for_target(target: dict, events: list[dict]) -> list[dict]:
    class_key = f"{target.get('lane', '')}:{target.get('kind', '') or 'unknown'}"
    return [event for event in events if event.get("class_key") == class_key]


def _closure_forecast_reset_reentry_rebuild_side_from_event(event: dict) -> str:
    status = event.get("closure_forecast_reset_reentry_rebuild_status", "none")
    if "confirmation" in status:
        return "confirmation"
    if "clearance" in status:
        return "clearance"
    recovery_status = event.get("closure_forecast_reset_reentry_refresh_recovery_status", "none")
    if "confirmation" in recovery_status:
        return "confirmation"
    if "clearance" in recovery_status:
        return "clearance"
    return "none"


def _closure_forecast_direction_majority(directions: list[str]) -> str:
    confirmation = sum(1 for direction in directions if direction == "supporting-confirmation")
    clearance = sum(1 for direction in directions if direction == "supporting-clearance")
    if confirmation > clearance:
        return "supporting-confirmation"
    if clearance > confirmation:
        return "supporting-clearance"
    return "neutral"


def _closure_forecast_direction_reversing(current_direction: str, earlier_majority: str) -> bool:
    if current_direction == "neutral" or earlier_majority == "neutral":
        return False
    return current_direction != earlier_majority


def _clamp_round(value: float, lower: float, upper: float) -> float:
    return round(max(lower, min(upper, value)), 2)


def _closure_forecast_reset_reentry_rebuild_path_label(event: dict) -> str:
    return event.get("closure_forecast_reset_reentry_rebuild_status", "hold")


def _class_direction_flip_count(directions: list[str]) -> int:
    flips = 0
    for previous, current in zip(directions, directions[1:]):
        if previous != current:
            flips += 1
    return flips


def _target_specific_normalization_noise(target: dict, history_meta: dict) -> bool:
    return bool(target.get("local_noise") or history_meta.get("current_transition_reversed"))


def _target_class_key(item: dict) -> str:
    return f"{item.get('lane', '')}:{item.get('kind', '') or 'unknown'}"


def _target_label(item: dict) -> str:
    return item.get("title", "") or item.get("kind", "") or "target"


def test_persistence_for_target_detects_just_rebuilt_confirmation() -> None:
    target = {
        "lane": "urgent",
        "kind": "config",
        "closure_forecast_reset_reentry_rebuild_status": "rebuilt-confirmation-reentry",
        "closure_forecast_reset_reentry_freshness_status": "fresh",
        "closure_forecast_momentum_status": "sustained-confirmation",
        "closure_forecast_stability_status": "stable",
    }
    events = [
        {
            "class_key": "urgent:config",
            "closure_forecast_reset_reentry_rebuild_status": "rebuilt-confirmation-reentry",
            "closure_forecast_reset_reentry_refresh_recovery_status": (
                "rebuilding-confirmation-reentry"
            ),
            "closure_forecast_reset_reentry_freshness_status": "fresh",
            "closure_forecast_momentum_status": "sustained-confirmation",
            "closure_forecast_stability_status": "stable",
        }
    ]

    meta = closure_forecast_reset_reentry_rebuild_persistence_for_target(
        target,
        events,
        {},
        ordered_reset_reentry_events_for_target=_ordered_reset_reentry_events_for_target,
        closure_forecast_reset_reentry_rebuild_side_from_event=(
            _closure_forecast_reset_reentry_rebuild_side_from_event
        ),
        closure_forecast_direction_majority=_closure_forecast_direction_majority,
        closure_forecast_direction_reversing=_closure_forecast_direction_reversing,
        clamp_round=_clamp_round,
        closure_forecast_reset_reentry_rebuild_path_label=(
            _closure_forecast_reset_reentry_rebuild_path_label
        ),
        class_reset_reentry_rebuild_persistence_window_runs=4,
    )

    assert meta["closure_forecast_reset_reentry_rebuild_persistence_status"] == "just-rebuilt"
    assert meta["closure_forecast_reset_reentry_rebuild_age_runs"] == 1


def test_churn_for_target_detects_flip_heavy_path() -> None:
    target = {
        "lane": "urgent",
        "kind": "config",
        "closure_forecast_stability_status": "oscillating",
        "closure_forecast_momentum_status": "reversing",
    }
    events = [
        {
            "class_key": "urgent:config",
            "closure_forecast_reset_reentry_rebuild_status": "rebuilt-confirmation-reentry",
            "closure_forecast_reset_reentry_freshness_status": "fresh",
        },
        {
            "class_key": "urgent:config",
            "closure_forecast_reset_reentry_rebuild_status": "rebuilt-clearance-reentry",
            "closure_forecast_reset_reentry_freshness_status": "mixed-age",
        },
        {
            "class_key": "urgent:config",
            "closure_forecast_reset_reentry_rebuild_status": "rebuilt-confirmation-reentry",
            "closure_forecast_reset_reentry_reset_status": "confirmation-reset",
            "closure_forecast_reset_reentry_freshness_status": "stale",
        },
    ]

    meta = closure_forecast_reset_reentry_rebuild_churn_for_target(
        target,
        events,
        {},
        ordered_reset_reentry_events_for_target=_ordered_reset_reentry_events_for_target,
        closure_forecast_reset_reentry_rebuild_side_from_event=(
            _closure_forecast_reset_reentry_rebuild_side_from_event
        ),
        class_direction_flip_count=_class_direction_flip_count,
        target_specific_normalization_noise=_target_specific_normalization_noise,
        clamp_round=_clamp_round,
        closure_forecast_reset_reentry_rebuild_path_label=(
            _closure_forecast_reset_reentry_rebuild_path_label
        ),
        class_reset_reentry_rebuild_persistence_window_runs=4,
    )

    assert meta["closure_forecast_reset_reentry_rebuild_churn_status"] == "churn"
    assert meta["closure_forecast_reset_reentry_rebuild_churn_score"] >= 0.45


def test_hotspots_and_summaries_track_rebuild_labels() -> None:
    targets = [
        {
            "lane": "urgent",
            "kind": "config",
            "title": "RepoA",
            "closure_forecast_reset_reentry_rebuild_age_runs": 3,
            "closure_forecast_reset_reentry_rebuild_persistence_score": 0.34,
            "closure_forecast_reset_reentry_rebuild_persistence_status": (
                "holding-confirmation-rebuild"
            ),
            "closure_forecast_reset_reentry_rebuild_churn_score": 0.0,
            "closure_forecast_reset_reentry_rebuild_churn_status": "none",
        },
        {
            "lane": "blocked",
            "kind": "setup",
            "title": "RepoB",
            "closure_forecast_reset_reentry_rebuild_age_runs": 2,
            "closure_forecast_reset_reentry_rebuild_persistence_score": -0.28,
            "closure_forecast_reset_reentry_rebuild_persistence_status": "just-rebuilt",
            "closure_forecast_reset_reentry_rebuild_churn_score": 0.5,
            "closure_forecast_reset_reentry_rebuild_churn_status": "churn",
        },
    ]

    holding_hotspots = closure_forecast_reset_reentry_rebuild_hotspots(
        targets,
        mode="holding",
        target_class_key=_target_class_key,
    )
    churn_hotspots = closure_forecast_reset_reentry_rebuild_hotspots(
        targets,
        mode="churn",
        target_class_key=_target_class_key,
    )
    persistence_summary = closure_forecast_reset_reentry_rebuild_persistence_summary(
        targets[0],
        [],
        holding_hotspots,
        target_label=_target_label,
    )
    churn_summary = closure_forecast_reset_reentry_rebuild_churn_summary(
        targets[1],
        churn_hotspots,
        target_label=_target_label,
    )

    assert holding_hotspots[0]["label"] == "urgent:config"
    assert churn_hotspots[0]["label"] == "blocked:setup"
    assert "RepoA" in persistence_summary
    assert "RepoB" in churn_summary
