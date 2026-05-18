from collections import Counter

from src.report_enrichment import build_operator_focus, build_operator_focus_line


def _severity_rank(value: object) -> float:
    mapping = {"critical": 1.0, "high": 0.85, "medium": 0.55, "low": 0.25}
    return mapping.get(str(value).lower(), 0.0)


def operator_counts(data: dict) -> dict[str, int]:
    counts = {"blocked": 0, "urgent": 0, "ready": 0, "deferred": 0}
    operator_summary = data.get("operator_summary") or {}
    if operator_summary.get("counts"):
        counts.update({key: int(operator_summary["counts"].get(key, 0) or 0) for key in counts})
        return counts
    for item in data.get("operator_queue", []) or []:
        lane = item.get("lane")
        if lane in counts:
            counts[lane] += 1
    return counts


def format_lane_counts(counts: dict[str, int]) -> str:
    return (
        f"{counts.get('blocked', 0)} blocked, "
        f"{counts.get('urgent', 0)} urgent, "
        f"{counts.get('ready', 0)} ready, "
        f"{counts.get('deferred', 0)} deferred"
    )


def summarize_top_actions(queue: list[dict], *, limit: int = 5) -> list[tuple[str, int]]:
    action_counts = Counter(
        (item.get("recommended_action") or item.get("next_step") or "").strip()
        for item in queue
        if (item.get("recommended_action") or item.get("next_step"))
    )
    return action_counts.most_common(limit)


def summarize_top_issue_families(
    material_changes: list[dict], *, limit: int = 5
) -> list[tuple[str, int]]:
    issue_counts = Counter()
    for item in material_changes:
        change_type = item.get("change_type") or "other"
        issue_counts[str(change_type).replace("-", " ").title()] += 1
    return issue_counts.most_common(limit)


def primary_lane_label(blocked: object, urgent: object, ready: object, deferred: object) -> str:
    lane_counts = {
        "Blocked": int(blocked or 0),
        "Needs Attention Now": int(urgent or 0),
        "Ready for Manual Action": int(ready or 0),
        "Safe to Defer": int(deferred or 0),
    }
    return max(
        lane_counts.items(), key=lambda item: (item[1], -list(lane_counts.keys()).index(item[0]))
    )[0]


def format_repo_rollup_counts(
    blocked: object, urgent: object, ready: object, deferred: object
) -> str:
    return f"{int(blocked or 0)} blocked, {int(urgent or 0)} urgent, {int(ready or 0)} ready, {int(deferred or 0)} deferred"


def ordered_queue_items(queue: list[dict]) -> list[dict]:
    lane_order = {"blocked": 0, "urgent": 1, "ready": 2, "deferred": 3}

    def _sort_key(item: dict) -> tuple[object, ...]:
        lane = str(item.get("lane", "urgent")).lower()
        priority = _severity_rank(item.get("priority", item.get("severity", 0)))
        text = " ".join(
            str(item.get(key, "") or "")
            for key in ("title", "summary", "recommended_action", "next_step", "decision_hint")
        ).lower()
        strategic_signal = (
            1
            if any(token in text for token in ("drift", "security", "rollback", "approval"))
            else 0
        )
        return (
            lane_order.get(lane, 4),
            -strategic_signal,
            -priority,
            str(item.get("repo", item.get("repo_name", ""))),
            str(item.get("title", "")),
        )

    return sorted(queue, key=_sort_key)


def primary_operator_focus_item(weekly_pack: dict) -> dict:
    for key in (
        "top_act_now_items",
        "top_watch_closely_items",
        "top_improving_items",
        "top_fragile_items",
        "top_revalidate_items",
        "top_attention",
    ):
        items = weekly_pack.get(key) or []
        if items:
            return items[0]
    return {}


def operator_focus_snapshot(weekly_pack: dict) -> tuple[str, str, str]:
    focus_item = primary_operator_focus_item(weekly_pack)
    focus_summary = weekly_pack.get(
        "operator_focus_summary", "No operator focus bucket is currently surfaced."
    )
    focus = str(focus_item.get("operator_focus") or build_operator_focus(focus_item))
    focus_line = str(focus_item.get("operator_focus_line") or build_operator_focus_line(focus_item))
    if not focus_item:
        focus = "Watch Closely"
        focus_line = f"{focus}: {focus_summary}"
    return focus, focus_summary, focus_line
