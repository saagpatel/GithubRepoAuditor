from __future__ import annotations


def build_resolution_run_context(
    queue: list[dict],
    history: list[dict],
    *,
    current_generated_at: str,
    snapshot_from_queue,
    snapshot_from_history,
    attention_items,
    history_window_runs: int,
) -> dict:
    recent_runs = [snapshot_from_queue(queue, generated_at=current_generated_at)] + [
        snapshot_from_history(entry) for entry in history[: history_window_runs - 1]
    ]
    recent_runs = [
        snapshot
        for snapshot in recent_runs
        if snapshot["items"] or snapshot["has_attention"] is not None
    ]
    current_snapshot = recent_runs[0] if recent_runs else {"items": {}, "has_attention": False}
    previous_snapshot = recent_runs[1] if len(recent_runs) > 1 else None
    current_attention = attention_items(current_snapshot)
    previous_attention = attention_items(previous_snapshot or {"items": {}, "has_attention": False})
    current_attention_keys = set(current_attention)
    previous_attention_keys = set(previous_attention)
    earlier_attention_keys = (
        set().union(*[set(attention_items(snapshot)) for snapshot in recent_runs[2:]])
        if len(recent_runs) > 2
        else set()
    )

    quiet_streak_runs = 0
    for snapshot in recent_runs:
        if snapshot["has_attention"]:
            break
        quiet_streak_runs += 1

    return {
        "recent_runs": recent_runs,
        "current_snapshot": current_snapshot,
        "previous_snapshot": previous_snapshot,
        "current_attention": current_attention,
        "previous_attention": previous_attention,
        "current_attention_keys": current_attention_keys,
        "previous_attention_keys": previous_attention_keys,
        "earlier_attention_keys": earlier_attention_keys,
        "quiet_streak_runs": quiet_streak_runs,
    }
