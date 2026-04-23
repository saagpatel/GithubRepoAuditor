from __future__ import annotations

from src.operator_trend_run_context import build_resolution_run_context


def _snapshot_from_queue(queue: list[dict], *, generated_at: str = "") -> dict:
    return {"items": {item["id"]: item for item in queue}, "has_attention": bool(queue), "generated_at": generated_at}


def _snapshot_from_history(entry: dict) -> dict:
    return entry["snapshot"]


def _attention_items(snapshot: dict) -> dict[str, dict]:
    return {
        key: item
        for key, item in snapshot["items"].items()
        if item.get("lane") in {"blocked", "active", "ready"}
    }


def test_build_resolution_run_context_tracks_attention_sets() -> None:
    queue = [{"id": "current", "lane": "blocked"}]
    history = [
        {"snapshot": {"items": {"previous": {"lane": "ready"}}, "has_attention": True}},
        {"snapshot": {"items": {"current": {"lane": "blocked"}}, "has_attention": True}},
    ]

    context = build_resolution_run_context(
        queue,
        history,
        current_generated_at="2026-04-17T12:00:00Z",
        snapshot_from_queue=_snapshot_from_queue,
        snapshot_from_history=_snapshot_from_history,
        attention_items=_attention_items,
        history_window_runs=5,
    )

    assert context["current_attention_keys"] == {"current"}
    assert context["previous_attention_keys"] == {"previous"}
    assert context["earlier_attention_keys"] == {"current"}
    assert context["quiet_streak_runs"] == 0


def test_build_resolution_run_context_counts_quiet_streak() -> None:
    queue: list[dict] = []
    history = [
        {"snapshot": {"items": {}, "has_attention": False}},
        {"snapshot": {"items": {}, "has_attention": False}},
        {"snapshot": {"items": {"older": {"lane": "blocked"}}, "has_attention": True}},
    ]

    context = build_resolution_run_context(
        queue,
        history,
        current_generated_at="2026-04-17T12:00:00Z",
        snapshot_from_queue=_snapshot_from_queue,
        snapshot_from_history=_snapshot_from_history,
        attention_items=_attention_items,
        history_window_runs=5,
    )

    assert len(context["recent_runs"]) == 4
    assert context["quiet_streak_runs"] == 3
    assert context["current_attention"] == {}
