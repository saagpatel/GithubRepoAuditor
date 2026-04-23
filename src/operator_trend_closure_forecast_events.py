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
