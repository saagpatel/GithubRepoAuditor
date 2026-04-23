from __future__ import annotations

from collections.abc import Iterable


def current_item_last_outcome(
    current_item: dict,
    previous_match: dict | None,
    status: str,
    *,
    attention_lanes: set[str],
) -> str:
    if status == "reopened":
        return "reopened"
    if not previous_match:
        return "no-change"
    if (
        previous_match.get("lane") in attention_lanes
        and current_item.get("lane") not in attention_lanes
    ):
        return "quieted"
    if previous_match.get("lane") == "blocked" and current_item.get("lane") in {"urgent", "ready"}:
        return "improved"
    if previous_match.get("lane") == "urgent" and current_item.get("lane") == "ready":
        return "improved"
    return "no-change"


def current_item_resolution_evidence(
    item_key: str,
    current_item: dict,
    status: str,
    latest_event: dict | None,
    previous_match: dict | None,
    recent_runs: list[dict],
    *,
    attention_lanes: set[str],
) -> str:
    if status == "reopened":
        return "This item returned after an earlier quiet or resolved period, so treat it as a regression rather than a net-new issue."
    if status == "attempted" and latest_event:
        return (
            f"The last intervention was {format_intervention(latest_event).lower()}, "
            "but the item is still open."
        )
    if status == "persisting":
        appearances = sum(
            1
            for snapshot in recent_runs
            if (snapshot.get("items") or {}).get(item_key, {}).get("lane") != "deferred"
            and (snapshot.get("items") or {}).get(item_key)
        )
        return f"This item is still open after {appearances} recent run(s), with no confirmed recovery signal yet."
    if (
        previous_match
        and previous_match.get("lane") in attention_lanes
        and current_item.get("lane") not in attention_lanes
    ):
        return "The last run reduced this item out of blocked or urgent lanes, but it is not yet confirmed resolved."
    return "No earlier intervention or durable recovery evidence is recorded in the recent window yet."


def absent_decision_memory(
    key: str,
    attention_history: list[dict[str, dict]],
    recent_runs: list[dict],
    latest_event: dict | None,
) -> dict:
    current_absent = key not in attention_history[0]
    previous_present = len(attention_history) > 1 and key in attention_history[1]
    previous_absent = len(attention_history) > 1 and key not in attention_history[1]
    earlier_present = any(key in snapshot for snapshot in attention_history[2:])
    last_seen_at = ""
    for snapshot in recent_runs[1:]:
        match = (snapshot.get("items") or {}).get(key)
        if match:
            last_seen_at = snapshot.get("generated_at", "")
            break
    if current_absent and previous_present:
        return {
            "status": "quieted",
            "last_outcome": "quieted",
            "last_seen_at": last_seen_at,
            "resolution_evidence": "This item is absent for 1 run after prior attention, so it looks quieter but is not yet confirmed resolved.",
        }
    if current_absent and previous_absent and earlier_present:
        return {
            "status": "confirmed_resolved",
            "last_outcome": "confirmed-resolved",
            "last_seen_at": last_seen_at,
            "resolution_evidence": "This item has stayed absent from blocked or urgent lanes for 2 consecutive runs and now counts as confirmed resolved.",
        }
    if latest_event:
        return {
            "status": "attempted",
            "last_outcome": "no-change",
            "last_seen_at": last_seen_at,
            "resolution_evidence": "A recent intervention is recorded, but there is not enough absence history yet to count this as durable resolution.",
        }
    return {
        "status": "new",
        "last_outcome": "no-change",
        "last_seen_at": last_seen_at,
        "resolution_evidence": "No durable resolution evidence is recorded for this item yet.",
    }


def recent_interventions(evidence_events: Iterable[dict]) -> list[dict]:
    interventions: list[dict] = []
    for event in list(evidence_events)[:5]:
        interventions.append(
            {
                "item_id": event.get("item_id", ""),
                "repo": event.get("repo", ""),
                "title": event.get("title", ""),
                "event_type": event.get("event_type", ""),
                "recorded_at": event.get("recorded_at", ""),
                "outcome": event.get("outcome", ""),
            }
        )
    return interventions


def resolution_evidence_summary(
    decision_memory_status: str,
    primary_target_resolution_evidence: str,
    recently_quieted_count: int,
    confirmed_resolved_count: int,
    reopened_after_resolution_count: int,
) -> str:
    if decision_memory_status == "reopened":
        return (
            f"{primary_target_resolution_evidence} "
            f"{reopened_after_resolution_count} item(s) reopened after an earlier quiet or resolved state in the recent window."
        ).strip()
    if decision_memory_status == "confirmed_resolved":
        return f"{confirmed_resolved_count} item(s) now count as confirmed resolved in the recent window."
    if decision_memory_status == "quieted":
        return f"{recently_quieted_count} item(s) are quieter, but not yet confirmed resolved."
    if primary_target_resolution_evidence:
        return primary_target_resolution_evidence
    return (
        f"Resolution evidence in the recent window: {confirmed_resolved_count} confirmed resolved, "
        f"{recently_quieted_count} quieted, {reopened_after_resolution_count} reopened."
    )


def summary_decision_memory(
    primary_target: dict,
    decision_memory_map: dict[str, dict],
    recent_runs: list[dict],
    *,
    queue_identity,
) -> dict:
    summary = decision_memory_map.get("__summary__", {})
    recent_interventions_list = summary.get("recent_interventions", [])
    recently_quieted_count = summary.get("recently_quieted_count", 0)
    confirmed_resolved_count = summary.get("confirmed_resolved_count", 0)
    reopened_after_resolution_count = summary.get("reopened_after_resolution_count", 0)
    decision_memory_window_runs = summary.get("decision_memory_window_runs", len(recent_runs))

    if primary_target:
        key = queue_identity(primary_target)
        memory = decision_memory_map.get(key, {})
        decision_memory_status = memory.get("decision_memory_status", "new")
        primary_target_resolution_evidence = memory.get("resolution_evidence", "")
        return {
            "decision_memory_status": decision_memory_status,
            "primary_target_last_seen_at": memory.get(
                "last_seen_at", recent_runs[0].get("generated_at", "") if recent_runs else ""
            ),
            "primary_target_last_intervention": memory.get("last_intervention", {}),
            "primary_target_last_outcome": memory.get("last_outcome", "no-change"),
            "primary_target_resolution_evidence": primary_target_resolution_evidence,
            "recent_interventions": recent_interventions_list,
            "recently_quieted_count": recently_quieted_count,
            "confirmed_resolved_count": confirmed_resolved_count,
            "reopened_after_resolution_count": reopened_after_resolution_count,
            "decision_memory_window_runs": decision_memory_window_runs,
            "resolution_evidence_summary": resolution_evidence_summary(
                decision_memory_status,
                primary_target_resolution_evidence,
                recently_quieted_count,
                confirmed_resolved_count,
                reopened_after_resolution_count,
            ),
        }

    default_status = (
        "confirmed_resolved"
        if confirmed_resolved_count
        else "quieted"
        if recently_quieted_count
        else "new"
    )
    default_outcome = (
        "confirmed-resolved"
        if confirmed_resolved_count
        else "quieted"
        if recently_quieted_count
        else "no-change"
    )
    default_resolution_evidence = resolution_evidence_summary(
        default_status,
        "",
        recently_quieted_count,
        confirmed_resolved_count,
        reopened_after_resolution_count,
    )
    return {
        "decision_memory_status": default_status,
        "primary_target_last_seen_at": "",
        "primary_target_last_intervention": (
            recent_interventions_list[0] if recent_interventions_list else {}
        ),
        "primary_target_last_outcome": default_outcome,
        "primary_target_resolution_evidence": default_resolution_evidence,
        "recent_interventions": recent_interventions_list,
        "recently_quieted_count": recently_quieted_count,
        "confirmed_resolved_count": confirmed_resolved_count,
        "reopened_after_resolution_count": reopened_after_resolution_count,
        "decision_memory_window_runs": decision_memory_window_runs,
        "resolution_evidence_summary": default_resolution_evidence,
    }


def format_intervention(intervention: dict) -> str:
    if not intervention:
        return "No recent intervention is recorded yet."
    recorded_at = intervention.get("recorded_at", "")
    when = recorded_at[:10] if recorded_at else "recently"
    event_type = intervention.get("event_type", "recorded")
    outcome = intervention.get("outcome", event_type)
    repo = f"{intervention.get('repo')}: " if intervention.get("repo") else ""
    title = intervention.get("title", "").strip()
    subject = f"{repo}{title}".strip(": ")
    if subject:
        return f"{when} — {event_type} for {subject} ({outcome})"
    return f"{when} — {event_type} ({outcome})"
