from __future__ import annotations

from src.operator_trend_closure_forecast_events import class_closure_forecast_events


def _queue_identity(item: dict) -> str:
    return item.get("id", "unknown")


def _target_class_key(item: dict) -> str:
    return f"{item.get('lane', '')}:{item.get('kind', '') or 'unknown'}"


def _target_label(item: dict) -> str:
    return item.get("title", "") or item.get("kind", "") or "target"


def test_class_closure_forecast_events_includes_current_target_payload() -> None:
    events = class_closure_forecast_events(
        [],
        current_primary_target={
            "id": "current-1",
            "lane": "urgent",
            "kind": "review",
            "title": "RepoA",
            "trust_policy": "strict",
            "closure_forecast_reweight_score": 0.42,
            "closure_forecast_reweight_direction": "up",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": (
                "rererestored-confirmation-rebuild-reentry"
            ),
        },
        current_generated_at="2026-04-17T12:00:00Z",
        queue_identity=_queue_identity,
        target_class_key=_target_class_key,
        target_label=_target_label,
        history_window_runs=5,
    )

    assert events[0]["key"] == "current-1"
    assert events[0]["class_key"] == "urgent:review"
    assert events[0]["label"] == "RepoA"
    assert events[0]["closure_forecast_reweight_score"] == 0.42
    assert (
        events[0][
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status"
        ]
        == "rererestored-confirmation-rebuild-reentry"
    )


def test_class_closure_forecast_events_prefers_summary_fields_for_history() -> None:
    events = class_closure_forecast_events(
        [
            {
                "generated_at": "2026-04-16T12:00:00Z",
                "operator_summary": {
                    "primary_target": {
                        "id": "hist-1",
                        "lane": "blocked",
                        "kind": "setup",
                        "title": "RepoB",
                        "closure_forecast_reweight_direction": "stale-primary",
                        "closure_forecast_reweight_score": 0.05,
                    },
                    "primary_target_closure_forecast_reweight_direction": "down",
                    "primary_target_closure_forecast_reweight_score": 0.33,
                    "primary_target_closure_forecast_hysteresis_status": "pending-clearance",
                },
            }
        ],
        current_primary_target={},
        current_generated_at="2026-04-17T12:00:00Z",
        queue_identity=_queue_identity,
        target_class_key=_target_class_key,
        target_label=_target_label,
        history_window_runs=5,
    )

    assert len(events) == 1
    assert events[0]["closure_forecast_reweight_direction"] == "down"
    assert events[0]["closure_forecast_reweight_score"] == 0.33
    assert events[0]["closure_forecast_hysteresis_status"] == "pending-clearance"
