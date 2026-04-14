from __future__ import annotations

from datetime import datetime
from typing import Any

ATTENTION_LANES = {"blocked", "urgent"}

HISTORY_WINDOW_RUNS = 10

FOLLOW_THROUGH_RETIREMENT_WINDOW_RUNS = 3


def _build_follow_through(resolution_trend: dict) -> dict:
    return _build_follow_through_with_queue(resolution_trend, [])


def _build_follow_through_with_queue(resolution_trend: dict, queue: list[dict]) -> dict:
    resolution_targets = resolution_trend.get("resolution_targets", [])
    repeat_urgent_count = sum(1 for item in resolution_targets if item.get("repeat_urgent"))
    stale_item_count = sum(1 for item in resolution_targets if item.get("stale"))
    oldest_open_item_days = max((item.get("age_days", 0) for item in resolution_targets), default=0)
    quiet_streak_runs = resolution_trend.get("quiet_streak_runs", 0)
    status_counts = {
        "untouched": 0,
        "attempted": 0,
        "waiting-on-evidence": 0,
        "stale-follow-through": 0,
        "resolved": 0,
        "unknown": 0,
    }
    checkpoint_counts = {
        "not-due": 0,
        "due-soon": 0,
        "overdue": 0,
        "satisfied": 0,
        "unknown": 0,
    }
    escalation_counts = {
        "none": 0,
        "watch": 0,
        "nudge": 0,
        "escalate-now": 0,
        "resolved-watch": 0,
        "unknown": 0,
    }
    recovery_counts = {
        "none": 0,
        "recovering": 0,
        "retiring-watch": 0,
        "retired": 0,
        "relapsing": 0,
        "insufficient-evidence": 0,
    }
    recovery_persistence_counts = {
        "none": 0,
        "just-recovering": 0,
        "holding-recovery": 0,
        "holding-retiring-watch": 0,
        "sustained-retiring-watch": 0,
        "sustained-retired": 0,
        "fragile-recovery": 0,
        "insufficient-evidence": 0,
    }
    relapse_churn_counts = {
        "none": 0,
        "watch": 0,
        "fragile": 0,
        "churn": 0,
        "blocked": 0,
        "insufficient-evidence": 0,
    }
    recovery_freshness_counts = {
        "none": 0,
        "fresh": 0,
        "holding-fresh": 0,
        "mixed-age": 0,
        "stale": 0,
        "insufficient-evidence": 0,
    }
    recovery_decay_counts = {
        "none": 0,
        "softening": 0,
        "aging": 0,
        "fragile-aging": 0,
        "expired": 0,
        "insufficient-evidence": 0,
    }
    recovery_memory_reset_counts = {
        "none": 0,
        "reset-watch": 0,
        "resetting": 0,
        "reset": 0,
        "rebuilding": 0,
        "insufficient-evidence": 0,
    }
    recovery_rebuild_strength_counts = {
        "none": 0,
        "just-rebuilding": 0,
        "building": 0,
        "holding-rebuild": 0,
        "fragile-rebuild": 0,
        "insufficient-evidence": 0,
    }
    recovery_reacquisition_counts = {
        "none": 0,
        "reacquiring": 0,
        "just-reacquired": 0,
        "holding-reacquired": 0,
        "reacquired": 0,
        "fragile-reacquisition": 0,
        "insufficient-evidence": 0,
    }
    recovery_reacquisition_durability_counts = {
        "none": 0,
        "just-reacquired": 0,
        "consolidating": 0,
        "holding-reacquired": 0,
        "durable-reacquired": 0,
        "softening": 0,
        "insufficient-evidence": 0,
    }
    recovery_reacquisition_consolidation_counts = {
        "none": 0,
        "building-confidence": 0,
        "holding-confidence": 0,
        "durable-confidence": 0,
        "fragile-confidence": 0,
        "reversing": 0,
        "insufficient-evidence": 0,
    }
    reacquisition_softening_decay_counts = {
        "none": 0,
        "softening-watch": 0,
        "step-down": 0,
        "revalidation-needed": 0,
        "retired-softening": 0,
        "insufficient-evidence": 0,
    }
    reacquisition_confidence_retirement_counts = {
        "none": 0,
        "watch-retirement": 0,
        "retiring-confidence": 0,
        "retired-confidence": 0,
        "revalidation-needed": 0,
        "insufficient-evidence": 0,
    }
    reacquisition_revalidation_recovery_counts = {
        "none": 0,
        "under-revalidation": 0,
        "rebuilding-restored-confidence": 0,
        "reearning-confidence": 0,
        "just-reearned-confidence": 0,
        "holding-reearned-confidence": 0,
        "insufficient-evidence": 0,
    }
    top_unattempted_items: list[dict] = []
    top_stale_follow_through_items: list[dict] = []
    top_overdue_follow_through_items: list[dict] = []
    top_escalation_items: list[dict] = []
    top_recovering_follow_through_items: list[dict] = []
    top_retiring_follow_through_items: list[dict] = []
    top_relapsing_follow_through_items: list[dict] = []
    top_fragile_recovery_items: list[dict] = []
    top_sustained_recovery_items: list[dict] = []
    top_churn_follow_through_items: list[dict] = []
    top_fresh_recovery_items: list[dict] = []
    top_stale_recovery_items: list[dict] = []
    top_softening_recovery_items: list[dict] = []
    top_reset_recovery_items: list[dict] = []
    top_rebuilding_recovery_items: list[dict] = []
    top_rebuilding_recovery_strength_items: list[dict] = []
    top_reacquiring_recovery_items: list[dict] = []
    top_reacquired_recovery_items: list[dict] = []
    top_fragile_reacquisition_items: list[dict] = []
    top_just_reacquired_items: list[dict] = []
    top_holding_reacquired_items: list[dict] = []
    top_durable_reacquired_items: list[dict] = []
    top_softening_reacquired_items: list[dict] = []
    top_fragile_reacquisition_confidence_items: list[dict] = []
    top_softening_reacquisition_items: list[dict] = []
    top_revalidation_needed_reacquisition_items: list[dict] = []
    top_retired_reacquisition_confidence_items: list[dict] = []
    top_under_revalidation_recovery_items: list[dict] = []
    top_rebuilding_restored_confidence_items: list[dict] = []
    top_reearning_confidence_items: list[dict] = []
    top_just_reearned_confidence_items: list[dict] = []
    top_holding_reearned_confidence_items: list[dict] = []
    for item in queue:
        status = item.get("follow_through_status", "unknown")
        if status not in status_counts:
            status = "unknown"
        status_counts[status] += 1
        checkpoint_status = item.get("follow_through_checkpoint_status", "unknown")
        if checkpoint_status not in checkpoint_counts:
            checkpoint_status = "unknown"
        checkpoint_counts[checkpoint_status] += 1
        escalation_status = item.get("follow_through_escalation_status", "unknown")
        if escalation_status not in escalation_counts:
            escalation_status = "unknown"
        escalation_counts[escalation_status] += 1
        recovery_status = item.get("follow_through_recovery_status", "none")
        if recovery_status not in recovery_counts:
            recovery_status = "insufficient-evidence"
        recovery_counts[recovery_status] += 1
        recovery_persistence_status = item.get("follow_through_recovery_persistence_status", "none")
        if recovery_persistence_status not in recovery_persistence_counts:
            recovery_persistence_status = "insufficient-evidence"
        recovery_persistence_counts[recovery_persistence_status] += 1
        relapse_churn_status = item.get("follow_through_relapse_churn_status", "none")
        if relapse_churn_status not in relapse_churn_counts:
            relapse_churn_status = "insufficient-evidence"
        relapse_churn_counts[relapse_churn_status] += 1
        recovery_freshness_status = item.get("follow_through_recovery_freshness_status", "none")
        if recovery_freshness_status not in recovery_freshness_counts:
            recovery_freshness_status = "insufficient-evidence"
        recovery_freshness_counts[recovery_freshness_status] += 1
        recovery_decay_status = item.get("follow_through_recovery_decay_status", "none")
        if recovery_decay_status not in recovery_decay_counts:
            recovery_decay_status = "insufficient-evidence"
        recovery_decay_counts[recovery_decay_status] += 1
        recovery_memory_reset_status = item.get(
            "follow_through_recovery_memory_reset_status", "none"
        )
        if recovery_memory_reset_status not in recovery_memory_reset_counts:
            recovery_memory_reset_status = "insufficient-evidence"
        recovery_memory_reset_counts[recovery_memory_reset_status] += 1
        recovery_rebuild_strength_status = item.get(
            "follow_through_recovery_rebuild_strength_status", "none"
        )
        if recovery_rebuild_strength_status not in recovery_rebuild_strength_counts:
            recovery_rebuild_strength_status = "insufficient-evidence"
        recovery_rebuild_strength_counts[recovery_rebuild_strength_status] += 1
        recovery_reacquisition_status = item.get(
            "follow_through_recovery_reacquisition_status", "none"
        )
        if recovery_reacquisition_status not in recovery_reacquisition_counts:
            recovery_reacquisition_status = "insufficient-evidence"
        recovery_reacquisition_counts[recovery_reacquisition_status] += 1
        recovery_reacquisition_durability_status = item.get(
            "follow_through_recovery_reacquisition_durability_status",
            "none",
        )
        if recovery_reacquisition_durability_status not in recovery_reacquisition_durability_counts:
            recovery_reacquisition_durability_status = "insufficient-evidence"
        recovery_reacquisition_durability_counts[recovery_reacquisition_durability_status] += 1
        recovery_reacquisition_consolidation_status = item.get(
            "follow_through_recovery_reacquisition_consolidation_status",
            "none",
        )
        if (
            recovery_reacquisition_consolidation_status
            not in recovery_reacquisition_consolidation_counts
        ):
            recovery_reacquisition_consolidation_status = "insufficient-evidence"
        recovery_reacquisition_consolidation_counts[
            recovery_reacquisition_consolidation_status
        ] += 1
        reacquisition_softening_decay_status = item.get(
            "follow_through_reacquisition_softening_decay_status",
            "none",
        )
        if reacquisition_softening_decay_status not in reacquisition_softening_decay_counts:
            reacquisition_softening_decay_status = "insufficient-evidence"
        reacquisition_softening_decay_counts[reacquisition_softening_decay_status] += 1
        reacquisition_confidence_retirement_status = item.get(
            "follow_through_reacquisition_confidence_retirement_status",
            "none",
        )
        if (
            reacquisition_confidence_retirement_status
            not in reacquisition_confidence_retirement_counts
        ):
            reacquisition_confidence_retirement_status = "insufficient-evidence"
        reacquisition_confidence_retirement_counts[reacquisition_confidence_retirement_status] += 1
        reacquisition_revalidation_recovery_status = item.get(
            "follow_through_reacquisition_revalidation_recovery_status",
            "none",
        )
        if (
            reacquisition_revalidation_recovery_status
            not in reacquisition_revalidation_recovery_counts
        ):
            reacquisition_revalidation_recovery_status = "insufficient-evidence"
        reacquisition_revalidation_recovery_counts[reacquisition_revalidation_recovery_status] += 1
        compact_item = {
            "item_id": item.get("item_id", ""),
            "repo": item.get("repo", ""),
            "title": item.get("title", ""),
            "lane": item.get("lane", ""),
            "follow_through_status": status,
            "follow_through_age_runs": item.get("follow_through_age_runs", 0),
            "follow_through_checkpoint_status": checkpoint_status,
            "follow_through_summary": item.get("follow_through_summary", ""),
            "follow_through_next_checkpoint": item.get("follow_through_next_checkpoint", ""),
            "follow_through_escalation_status": escalation_status,
            "follow_through_escalation_summary": item.get("follow_through_escalation_summary", ""),
            "follow_through_escalation_reason": item.get("follow_through_escalation_reason", ""),
            "follow_through_recovery_age_runs": item.get("follow_through_recovery_age_runs", 0),
            "follow_through_recovery_status": recovery_status,
            "follow_through_recovery_summary": item.get("follow_through_recovery_summary", ""),
            "follow_through_recovery_reason": item.get("follow_through_recovery_reason", ""),
            "follow_through_recovery_persistence_age_runs": item.get(
                "follow_through_recovery_persistence_age_runs", 0
            ),
            "follow_through_recovery_persistence_status": recovery_persistence_status,
            "follow_through_recovery_persistence_summary": item.get(
                "follow_through_recovery_persistence_summary", ""
            ),
            "follow_through_recovery_persistence_reason": item.get(
                "follow_through_recovery_persistence_reason", ""
            ),
            "follow_through_relapse_churn_status": relapse_churn_status,
            "follow_through_relapse_churn_summary": item.get(
                "follow_through_relapse_churn_summary", ""
            ),
            "follow_through_relapse_churn_reason": item.get(
                "follow_through_relapse_churn_reason", ""
            ),
            "follow_through_recovery_freshness_age_runs": item.get(
                "follow_through_recovery_freshness_age_runs", 0
            ),
            "follow_through_recovery_freshness_status": recovery_freshness_status,
            "follow_through_recovery_freshness_summary": item.get(
                "follow_through_recovery_freshness_summary", ""
            ),
            "follow_through_recovery_freshness_reason": item.get(
                "follow_through_recovery_freshness_reason", ""
            ),
            "follow_through_recovery_decay_status": recovery_decay_status,
            "follow_through_recovery_decay_summary": item.get(
                "follow_through_recovery_decay_summary", ""
            ),
            "follow_through_recovery_decay_reason": item.get(
                "follow_through_recovery_decay_reason", ""
            ),
            "follow_through_recovery_memory_reset_status": recovery_memory_reset_status,
            "follow_through_recovery_memory_reset_summary": item.get(
                "follow_through_recovery_memory_reset_summary", ""
            ),
            "follow_through_recovery_memory_reset_reason": item.get(
                "follow_through_recovery_memory_reset_reason", ""
            ),
            "follow_through_recovery_rebuild_strength_age_runs": item.get(
                "follow_through_recovery_rebuild_strength_age_runs", 0
            ),
            "follow_through_recovery_rebuild_strength_status": recovery_rebuild_strength_status,
            "follow_through_recovery_rebuild_strength_summary": item.get(
                "follow_through_recovery_rebuild_strength_summary", ""
            ),
            "follow_through_recovery_rebuild_strength_reason": item.get(
                "follow_through_recovery_rebuild_strength_reason", ""
            ),
            "follow_through_recovery_reacquisition_status": recovery_reacquisition_status,
            "follow_through_recovery_reacquisition_summary": item.get(
                "follow_through_recovery_reacquisition_summary", ""
            ),
            "follow_through_recovery_reacquisition_reason": item.get(
                "follow_through_recovery_reacquisition_reason", ""
            ),
            "follow_through_recovery_reacquisition_durability_age_runs": item.get(
                "follow_through_recovery_reacquisition_durability_age_runs",
                0,
            ),
            "follow_through_recovery_reacquisition_durability_status": recovery_reacquisition_durability_status,
            "follow_through_recovery_reacquisition_durability_summary": item.get(
                "follow_through_recovery_reacquisition_durability_summary",
                "",
            ),
            "follow_through_recovery_reacquisition_durability_reason": item.get(
                "follow_through_recovery_reacquisition_durability_reason",
                "",
            ),
            "follow_through_recovery_reacquisition_consolidation_status": recovery_reacquisition_consolidation_status,
            "follow_through_recovery_reacquisition_consolidation_summary": item.get(
                "follow_through_recovery_reacquisition_consolidation_summary",
                "",
            ),
            "follow_through_recovery_reacquisition_consolidation_reason": item.get(
                "follow_through_recovery_reacquisition_consolidation_reason",
                "",
            ),
            "follow_through_reacquisition_softening_decay_age_runs": item.get(
                "follow_through_reacquisition_softening_decay_age_runs",
                0,
            ),
            "follow_through_reacquisition_softening_decay_status": reacquisition_softening_decay_status,
            "follow_through_reacquisition_softening_decay_summary": item.get(
                "follow_through_reacquisition_softening_decay_summary",
                "",
            ),
            "follow_through_reacquisition_softening_decay_reason": item.get(
                "follow_through_reacquisition_softening_decay_reason",
                "",
            ),
            "follow_through_reacquisition_confidence_retirement_status": reacquisition_confidence_retirement_status,
            "follow_through_reacquisition_confidence_retirement_summary": item.get(
                "follow_through_reacquisition_confidence_retirement_summary",
                "",
            ),
            "follow_through_reacquisition_confidence_retirement_reason": item.get(
                "follow_through_reacquisition_confidence_retirement_reason",
                "",
            ),
            "follow_through_reacquisition_revalidation_recovery_age_runs": item.get(
                "follow_through_reacquisition_revalidation_recovery_age_runs",
                0,
            ),
            "follow_through_reacquisition_revalidation_recovery_status": reacquisition_revalidation_recovery_status,
            "follow_through_reacquisition_revalidation_recovery_summary": item.get(
                "follow_through_reacquisition_revalidation_recovery_summary",
                "",
            ),
            "follow_through_reacquisition_revalidation_recovery_reason": item.get(
                "follow_through_reacquisition_revalidation_recovery_reason",
                "",
            ),
        }
        if status == "untouched" and len(top_unattempted_items) < 5:
            top_unattempted_items.append(compact_item)
        if status == "stale-follow-through" and len(top_stale_follow_through_items) < 5:
            top_stale_follow_through_items.append(compact_item)
        if checkpoint_status == "overdue" and len(top_overdue_follow_through_items) < 5:
            top_overdue_follow_through_items.append(compact_item)
        if escalation_status in {"escalate-now", "nudge"} and len(top_escalation_items) < 5:
            top_escalation_items.append(compact_item)
        if recovery_status == "recovering" and len(top_recovering_follow_through_items) < 5:
            top_recovering_follow_through_items.append(compact_item)
        if recovery_status == "retiring-watch" and len(top_retiring_follow_through_items) < 5:
            top_retiring_follow_through_items.append(compact_item)
        if recovery_status == "relapsing" and len(top_relapsing_follow_through_items) < 5:
            top_relapsing_follow_through_items.append(compact_item)
        if (
            recovery_persistence_status == "fragile-recovery"
            or relapse_churn_status in {"fragile", "blocked"}
        ) and len(top_fragile_recovery_items) < 5:
            top_fragile_recovery_items.append(compact_item)
        if (
            recovery_persistence_status
            in {
                "holding-recovery",
                "holding-retiring-watch",
                "sustained-retiring-watch",
                "sustained-retired",
            }
        ) and len(top_sustained_recovery_items) < 5:
            top_sustained_recovery_items.append(compact_item)
        if (
            relapse_churn_status in {"fragile", "churn", "blocked"}
            and len(top_churn_follow_through_items) < 5
        ):
            top_churn_follow_through_items.append(compact_item)
        if (
            recovery_freshness_status in {"fresh", "holding-fresh"}
            and len(top_fresh_recovery_items) < 5
        ):
            top_fresh_recovery_items.append(compact_item)
        if recovery_freshness_status == "stale" and len(top_stale_recovery_items) < 5:
            top_stale_recovery_items.append(compact_item)
        if (
            recovery_decay_status in {"softening", "aging", "fragile-aging"}
            and len(top_softening_recovery_items) < 5
        ):
            top_softening_recovery_items.append(compact_item)
        if (
            recovery_memory_reset_status in {"reset-watch", "resetting", "reset"}
            and len(top_reset_recovery_items) < 5
        ):
            top_reset_recovery_items.append(compact_item)
        if recovery_memory_reset_status == "rebuilding" and len(top_rebuilding_recovery_items) < 5:
            top_rebuilding_recovery_items.append(compact_item)
        if (
            recovery_rebuild_strength_status in {"just-rebuilding", "building", "holding-rebuild"}
            and len(top_rebuilding_recovery_strength_items) < 5
        ):
            top_rebuilding_recovery_strength_items.append(compact_item)
        if (
            recovery_reacquisition_status == "reacquiring"
            and len(top_reacquiring_recovery_items) < 5
        ):
            top_reacquiring_recovery_items.append(compact_item)
        if (
            recovery_reacquisition_status in {"just-reacquired", "holding-reacquired", "reacquired"}
            and len(top_reacquired_recovery_items) < 5
        ):
            top_reacquired_recovery_items.append(compact_item)
        if (
            recovery_reacquisition_status == "fragile-reacquisition"
            and len(top_fragile_reacquisition_items) < 5
        ):
            top_fragile_reacquisition_items.append(compact_item)
        if (
            recovery_reacquisition_durability_status == "just-reacquired"
            and len(top_just_reacquired_items) < 5
        ):
            top_just_reacquired_items.append(compact_item)
        if (
            recovery_reacquisition_durability_status in {"consolidating", "holding-reacquired"}
            and len(top_holding_reacquired_items) < 5
        ):
            top_holding_reacquired_items.append(compact_item)
        if (
            recovery_reacquisition_durability_status == "durable-reacquired"
            and len(top_durable_reacquired_items) < 5
        ):
            top_durable_reacquired_items.append(compact_item)
        if (
            recovery_reacquisition_durability_status == "softening"
            and len(top_softening_reacquired_items) < 5
        ):
            top_softening_reacquired_items.append(compact_item)
        if (
            recovery_reacquisition_consolidation_status in {"fragile-confidence", "reversing"}
            and len(top_fragile_reacquisition_confidence_items) < 5
        ):
            top_fragile_reacquisition_confidence_items.append(compact_item)
        if (
            reacquisition_softening_decay_status
            in {"softening-watch", "step-down", "revalidation-needed"}
            and len(top_softening_reacquisition_items) < 5
        ):
            top_softening_reacquisition_items.append(compact_item)
        if (
            reacquisition_softening_decay_status == "revalidation-needed"
            or reacquisition_confidence_retirement_status == "revalidation-needed"
        ) and len(top_revalidation_needed_reacquisition_items) < 5:
            top_revalidation_needed_reacquisition_items.append(compact_item)
        if (
            reacquisition_confidence_retirement_status == "retired-confidence"
            and len(top_retired_reacquisition_confidence_items) < 5
        ):
            top_retired_reacquisition_confidence_items.append(compact_item)
        if (
            reacquisition_revalidation_recovery_status == "under-revalidation"
            and len(top_under_revalidation_recovery_items) < 5
        ):
            top_under_revalidation_recovery_items.append(compact_item)
        if (
            reacquisition_revalidation_recovery_status == "rebuilding-restored-confidence"
            and len(top_rebuilding_restored_confidence_items) < 5
        ):
            top_rebuilding_restored_confidence_items.append(compact_item)
        if (
            reacquisition_revalidation_recovery_status == "reearning-confidence"
            and len(top_reearning_confidence_items) < 5
        ):
            top_reearning_confidence_items.append(compact_item)
        if (
            reacquisition_revalidation_recovery_status == "just-reearned-confidence"
            and len(top_just_reearned_confidence_items) < 5
        ):
            top_just_reearned_confidence_items.append(compact_item)
        if (
            reacquisition_revalidation_recovery_status == "holding-reearned-confidence"
            and len(top_holding_reearned_confidence_items) < 5
        ):
            top_holding_reearned_confidence_items.append(compact_item)
    status_counts["resolved"] += resolution_trend.get("confirmed_resolved_count", 0)
    follow_through_checkpoint_summary = _follow_through_checkpoint_summary(
        status_counts,
        top_unattempted_items,
        top_stale_follow_through_items,
    )
    follow_through_escalation_summary = _follow_through_escalation_summary(
        checkpoint_counts,
        escalation_counts,
        top_overdue_follow_through_items,
        top_escalation_items,
    )
    follow_through_recovery_summary = _follow_through_recovery_summary(
        recovery_counts,
        recovery_persistence_counts,
        top_recovering_follow_through_items,
        top_retiring_follow_through_items,
        top_relapsing_follow_through_items,
        top_fragile_recovery_items,
        top_sustained_recovery_items,
    )
    follow_through_recovery_persistence_summary = _follow_through_recovery_persistence_summary(
        recovery_persistence_counts,
        top_fragile_recovery_items,
        top_sustained_recovery_items,
    )
    follow_through_relapse_churn_summary = _follow_through_relapse_churn_summary(
        relapse_churn_counts,
        top_churn_follow_through_items,
    )
    follow_through_recovery_freshness_summary = _follow_through_recovery_freshness_summary(
        recovery_freshness_counts,
        top_fresh_recovery_items,
        top_stale_recovery_items,
        top_softening_recovery_items,
    )
    follow_through_recovery_memory_reset_summary = _follow_through_recovery_memory_reset_summary(
        recovery_memory_reset_counts,
        top_reset_recovery_items,
        top_rebuilding_recovery_items,
    )
    follow_through_recovery_rebuild_strength_summary = (
        _follow_through_recovery_rebuild_strength_summary(
            recovery_rebuild_strength_counts,
            top_rebuilding_recovery_strength_items,
            top_fragile_reacquisition_items,
        )
    )
    follow_through_recovery_reacquisition_summary = _follow_through_recovery_reacquisition_summary(
        recovery_reacquisition_counts,
        top_reacquiring_recovery_items,
        top_reacquired_recovery_items,
        top_fragile_reacquisition_items,
    )
    follow_through_recovery_reacquisition_durability_summary = (
        _follow_through_reacquisition_durability_summary(
            recovery_reacquisition_durability_counts,
            top_just_reacquired_items,
            top_holding_reacquired_items,
            top_durable_reacquired_items,
            top_softening_reacquired_items,
        )
    )
    follow_through_recovery_reacquisition_consolidation_summary = (
        _follow_through_reacquisition_consolidation_summary(
            recovery_reacquisition_consolidation_counts,
            top_holding_reacquired_items,
            top_durable_reacquired_items,
            top_softening_reacquired_items,
            top_fragile_reacquisition_confidence_items,
        )
    )
    follow_through_reacquisition_softening_decay_summary = (
        _follow_through_reacquisition_softening_decay_summary(
            reacquisition_softening_decay_counts,
            top_softening_reacquisition_items,
            top_revalidation_needed_reacquisition_items,
        )
    )
    follow_through_reacquisition_confidence_retirement_summary = (
        _follow_through_reacquisition_confidence_retirement_summary(
            reacquisition_confidence_retirement_counts,
            top_revalidation_needed_reacquisition_items,
            top_retired_reacquisition_confidence_items,
        )
    )
    follow_through_reacquisition_revalidation_recovery_summary = (
        _follow_through_reacquisition_revalidation_recovery_summary(
            reacquisition_revalidation_recovery_counts,
            top_under_revalidation_recovery_items,
            top_rebuilding_restored_confidence_items,
            top_reearning_confidence_items,
            top_just_reearned_confidence_items,
            top_holding_reearned_confidence_items,
        )
    )
    return {
        "repeat_urgent_count": repeat_urgent_count,
        "stale_item_count": stale_item_count,
        "oldest_open_item_days": oldest_open_item_days,
        "quiet_streak_runs": quiet_streak_runs,
        "follow_through_summary": _follow_through_summary(
            repeat_urgent_count,
            stale_item_count,
            oldest_open_item_days,
            quiet_streak_runs,
            status_counts=status_counts,
            checkpoint_counts=checkpoint_counts,
            escalation_counts=escalation_counts,
            recovery_counts=recovery_counts,
            recovery_persistence_counts=recovery_persistence_counts,
            relapse_churn_counts=relapse_churn_counts,
            top_unattempted_items=top_unattempted_items,
            top_stale_follow_through_items=top_stale_follow_through_items,
            top_overdue_follow_through_items=top_overdue_follow_through_items,
            top_escalation_items=top_escalation_items,
            top_recovering_follow_through_items=top_recovering_follow_through_items,
            top_retiring_follow_through_items=top_retiring_follow_through_items,
            top_relapsing_follow_through_items=top_relapsing_follow_through_items,
            top_fragile_recovery_items=top_fragile_recovery_items,
            top_sustained_recovery_items=top_sustained_recovery_items,
            top_churn_follow_through_items=top_churn_follow_through_items,
            recovery_freshness_counts=recovery_freshness_counts,
            recovery_decay_counts=recovery_decay_counts,
            recovery_memory_reset_counts=recovery_memory_reset_counts,
            recovery_rebuild_strength_counts=recovery_rebuild_strength_counts,
            recovery_reacquisition_counts=recovery_reacquisition_counts,
            recovery_reacquisition_durability_counts=recovery_reacquisition_durability_counts,
            recovery_reacquisition_consolidation_counts=recovery_reacquisition_consolidation_counts,
            reacquisition_softening_decay_counts=reacquisition_softening_decay_counts,
            reacquisition_confidence_retirement_counts=reacquisition_confidence_retirement_counts,
            top_fresh_recovery_items=top_fresh_recovery_items,
            top_stale_recovery_items=top_stale_recovery_items,
            top_softening_recovery_items=top_softening_recovery_items,
            top_reset_recovery_items=top_reset_recovery_items,
            top_rebuilding_recovery_items=top_rebuilding_recovery_items,
            top_rebuilding_recovery_strength_items=top_rebuilding_recovery_strength_items,
            top_reacquiring_recovery_items=top_reacquiring_recovery_items,
            top_reacquired_recovery_items=top_reacquired_recovery_items,
            top_fragile_reacquisition_items=top_fragile_reacquisition_items,
            top_just_reacquired_items=top_just_reacquired_items,
            top_holding_reacquired_items=top_holding_reacquired_items,
            top_durable_reacquired_items=top_durable_reacquired_items,
            top_softening_reacquired_items=top_softening_reacquired_items,
            top_fragile_reacquisition_confidence_items=top_fragile_reacquisition_confidence_items,
            top_softening_reacquisition_items=top_softening_reacquisition_items,
            top_revalidation_needed_reacquisition_items=top_revalidation_needed_reacquisition_items,
            top_retired_reacquisition_confidence_items=top_retired_reacquisition_confidence_items,
        ),
        "follow_through_status_counts": status_counts,
        "follow_through_checkpoint_counts": checkpoint_counts,
        "follow_through_escalation_counts": escalation_counts,
        "follow_through_recovery_counts": recovery_counts,
        "follow_through_recovery_persistence_counts": recovery_persistence_counts,
        "follow_through_relapse_churn_counts": relapse_churn_counts,
        "follow_through_recovery_freshness_counts": recovery_freshness_counts,
        "follow_through_recovery_decay_counts": recovery_decay_counts,
        "follow_through_recovery_memory_reset_counts": recovery_memory_reset_counts,
        "follow_through_recovery_rebuild_strength_counts": recovery_rebuild_strength_counts,
        "follow_through_recovery_reacquisition_counts": recovery_reacquisition_counts,
        "follow_through_recovery_reacquisition_durability_counts": recovery_reacquisition_durability_counts,
        "follow_through_recovery_reacquisition_consolidation_counts": recovery_reacquisition_consolidation_counts,
        "follow_through_reacquisition_softening_decay_counts": reacquisition_softening_decay_counts,
        "follow_through_reacquisition_confidence_retirement_counts": reacquisition_confidence_retirement_counts,
        "follow_through_reacquisition_revalidation_recovery_counts": reacquisition_revalidation_recovery_counts,
        "top_unattempted_items": top_unattempted_items,
        "top_stale_follow_through_items": top_stale_follow_through_items,
        "top_overdue_follow_through_items": top_overdue_follow_through_items,
        "top_escalation_items": top_escalation_items,
        "top_recovering_follow_through_items": top_recovering_follow_through_items,
        "top_retiring_follow_through_items": top_retiring_follow_through_items,
        "top_relapsing_follow_through_items": top_relapsing_follow_through_items,
        "top_fragile_recovery_items": top_fragile_recovery_items,
        "top_sustained_recovery_items": top_sustained_recovery_items,
        "top_churn_follow_through_items": top_churn_follow_through_items,
        "top_fresh_recovery_items": top_fresh_recovery_items,
        "top_stale_recovery_items": top_stale_recovery_items,
        "top_softening_recovery_items": top_softening_recovery_items,
        "top_reset_recovery_items": top_reset_recovery_items,
        "top_rebuilding_recovery_items": top_rebuilding_recovery_items,
        "top_rebuilding_recovery_strength_items": top_rebuilding_recovery_strength_items,
        "top_reacquiring_recovery_items": top_reacquiring_recovery_items,
        "top_reacquired_recovery_items": top_reacquired_recovery_items,
        "top_fragile_reacquisition_items": top_fragile_reacquisition_items,
        "top_just_reacquired_items": top_just_reacquired_items,
        "top_holding_reacquired_items": top_holding_reacquired_items,
        "top_durable_reacquired_items": top_durable_reacquired_items,
        "top_softening_reacquired_items": top_softening_reacquired_items,
        "top_fragile_reacquisition_confidence_items": top_fragile_reacquisition_confidence_items,
        "top_softening_reacquisition_items": top_softening_reacquisition_items,
        "top_revalidation_needed_reacquisition_items": top_revalidation_needed_reacquisition_items,
        "top_retired_reacquisition_confidence_items": top_retired_reacquisition_confidence_items,
        "top_under_revalidation_recovery_items": top_under_revalidation_recovery_items,
        "top_rebuilding_restored_confidence_items": top_rebuilding_restored_confidence_items,
        "top_reearning_confidence_items": top_reearning_confidence_items,
        "top_just_reearned_confidence_items": top_just_reearned_confidence_items,
        "top_holding_reearned_confidence_items": top_holding_reearned_confidence_items,
        "follow_through_checkpoint_summary": follow_through_checkpoint_summary,
        "follow_through_escalation_summary": follow_through_escalation_summary,
        "follow_through_recovery_summary": follow_through_recovery_summary,
        "follow_through_recovery_persistence_summary": follow_through_recovery_persistence_summary,
        "follow_through_relapse_churn_summary": follow_through_relapse_churn_summary,
        "follow_through_recovery_freshness_summary": follow_through_recovery_freshness_summary,
        "follow_through_recovery_decay_summary": _follow_through_recovery_decay_summary(
            recovery_decay_counts,
            top_softening_recovery_items,
            top_stale_recovery_items,
        ),
        "follow_through_recovery_memory_reset_summary": follow_through_recovery_memory_reset_summary,
        "follow_through_recovery_rebuild_strength_summary": follow_through_recovery_rebuild_strength_summary,
        "follow_through_recovery_reacquisition_summary": follow_through_recovery_reacquisition_summary,
        "follow_through_recovery_reacquisition_durability_summary": follow_through_recovery_reacquisition_durability_summary,
        "follow_through_recovery_reacquisition_consolidation_summary": follow_through_recovery_reacquisition_consolidation_summary,
        "follow_through_reacquisition_softening_decay_summary": follow_through_reacquisition_softening_decay_summary,
        "follow_through_reacquisition_confidence_retirement_summary": follow_through_reacquisition_confidence_retirement_summary,
        "follow_through_reacquisition_revalidation_recovery_summary": follow_through_reacquisition_revalidation_recovery_summary,
    }


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


def _project_queue_follow_through(
    queue: list[dict],
    *,
    recent_runs: list[dict],
    resolution_trend: dict,
    current_generated_at: str,
) -> list[dict]:
    recent_runs = [
        snapshot
        for snapshot in recent_runs
        if snapshot.get("items") or snapshot.get("has_attention") is not None
    ]
    decision_memory_map = resolution_trend.get("decision_memory_map") or {}
    enriched_queue: list[dict] = []
    for item in queue:
        key = _queue_identity(item)
        memory = decision_memory_map.get(key, {})
        previous_match = recent_runs[1]["items"].get(key) if len(recent_runs) > 1 else None
        prior_matches = [
            snapshot.get("items", {}).get(key)
            for snapshot in recent_runs[1:]
            if snapshot.get("items", {}).get(key)
        ]
        earliest_age_days = max(
            [int(item.get("age_days", 0) or 0)]
            + [int((match or {}).get("age_days", 0) or 0) for match in prior_matches],
            default=int(item.get("age_days", 0) or 0),
        )
        appearance_count = 1 + len(prior_matches)
        attention_appearances = sum(
            1
            for snapshot in recent_runs
            if (snapshot.get("items", {}).get(key) or {}).get("lane") in ATTENTION_LANES
        )
        follow_through_age_runs = appearance_count
        follow_through_status = _queue_item_follow_through_status(
            item,
            memory,
            previous_match=previous_match,
            appearance_count=appearance_count,
            attention_appearances=attention_appearances,
            earliest_age_days=earliest_age_days,
            current_generated_at=current_generated_at,
        )
        follow_through_last_touch = _follow_through_last_touch_label(item, memory)
        follow_through_evidence_hint = _follow_through_evidence_hint(item, memory)
        follow_through_next_checkpoint = _follow_through_next_checkpoint(
            item,
            memory,
            follow_through_status=follow_through_status,
        )
        follow_through_checkpoint_status = _follow_through_checkpoint_status(
            item,
            memory,
            follow_through_status=follow_through_status,
            follow_through_age_runs=follow_through_age_runs,
            earliest_age_days=earliest_age_days,
            current_generated_at=current_generated_at,
        )
        follow_through_escalation_status = _follow_through_escalation_status(
            follow_through_status=follow_through_status,
            follow_through_checkpoint_status=follow_through_checkpoint_status,
            follow_through_age_runs=follow_through_age_runs,
        )
        follow_through_escalation_reason = _follow_through_escalation_reason(
            item,
            memory,
            follow_through_status=follow_through_status,
            follow_through_checkpoint_status=follow_through_checkpoint_status,
            follow_through_age_runs=follow_through_age_runs,
        )
        follow_through_escalation_summary = _follow_through_escalation_item_summary(
            item,
            follow_through_checkpoint_status=follow_through_checkpoint_status,
            follow_through_escalation_status=follow_through_escalation_status,
            follow_through_escalation_reason=follow_through_escalation_reason,
        )
        (
            follow_through_recovery_age_runs,
            follow_through_recovery_status,
            follow_through_recovery_reason,
            follow_through_recovery_summary,
        ) = _follow_through_recovery_projection(
            item,
            prior_matches,
            follow_through_status=follow_through_status,
            follow_through_checkpoint_status=follow_through_checkpoint_status,
            follow_through_escalation_status=follow_through_escalation_status,
        )
        (
            follow_through_recovery_persistence_age_runs,
            follow_through_recovery_persistence_status,
            follow_through_recovery_persistence_reason,
            follow_through_recovery_persistence_summary,
        ) = _follow_through_recovery_persistence_projection(
            item,
            prior_matches,
            follow_through_status=follow_through_status,
            follow_through_checkpoint_status=follow_through_checkpoint_status,
            follow_through_escalation_status=follow_through_escalation_status,
            follow_through_recovery_status=follow_through_recovery_status,
        )
        (
            follow_through_relapse_churn_status,
            follow_through_relapse_churn_reason,
            follow_through_relapse_churn_summary,
        ) = _follow_through_relapse_churn_projection(
            item,
            prior_matches,
            follow_through_status=follow_through_status,
            follow_through_checkpoint_status=follow_through_checkpoint_status,
            follow_through_escalation_status=follow_through_escalation_status,
            follow_through_recovery_status=follow_through_recovery_status,
            follow_through_recovery_persistence_status=follow_through_recovery_persistence_status,
        )
        (
            follow_through_recovery_freshness_age_runs,
            follow_through_recovery_freshness_status,
            follow_through_recovery_freshness_reason,
            follow_through_recovery_freshness_summary,
        ) = _follow_through_recovery_freshness_projection(
            item,
            prior_matches,
            follow_through_status=follow_through_status,
            follow_through_checkpoint_status=follow_through_checkpoint_status,
            follow_through_escalation_status=follow_through_escalation_status,
            follow_through_recovery_status=follow_through_recovery_status,
            follow_through_recovery_persistence_status=follow_through_recovery_persistence_status,
            follow_through_relapse_churn_status=follow_through_relapse_churn_status,
        )
        (
            follow_through_recovery_decay_status,
            follow_through_recovery_decay_reason,
            follow_through_recovery_decay_summary,
        ) = _follow_through_recovery_decay_projection(
            item,
            prior_matches,
            follow_through_recovery_status=follow_through_recovery_status,
            follow_through_recovery_persistence_status=follow_through_recovery_persistence_status,
            follow_through_relapse_churn_status=follow_through_relapse_churn_status,
            follow_through_recovery_freshness_status=follow_through_recovery_freshness_status,
        )
        (
            follow_through_recovery_memory_reset_status,
            follow_through_recovery_memory_reset_reason,
            follow_through_recovery_memory_reset_summary,
        ) = _follow_through_recovery_memory_reset_projection(
            item,
            prior_matches,
            follow_through_recovery_status=follow_through_recovery_status,
            follow_through_recovery_freshness_status=follow_through_recovery_freshness_status,
            follow_through_recovery_decay_status=follow_through_recovery_decay_status,
        )
        (
            follow_through_recovery_rebuild_strength_age_runs,
            follow_through_recovery_rebuild_strength_status,
            follow_through_recovery_rebuild_strength_reason,
            follow_through_recovery_rebuild_strength_summary,
        ) = _follow_through_recovery_rebuild_strength_projection(
            item,
            prior_matches,
            follow_through_recovery_status=follow_through_recovery_status,
            follow_through_recovery_persistence_status=follow_through_recovery_persistence_status,
            follow_through_relapse_churn_status=follow_through_relapse_churn_status,
            follow_through_recovery_freshness_status=follow_through_recovery_freshness_status,
            follow_through_recovery_decay_status=follow_through_recovery_decay_status,
            follow_through_recovery_memory_reset_status=follow_through_recovery_memory_reset_status,
        )
        (
            follow_through_recovery_reacquisition_status,
            follow_through_recovery_reacquisition_reason,
            follow_through_recovery_reacquisition_summary,
        ) = _follow_through_recovery_reacquisition_projection(
            item,
            prior_matches,
            follow_through_recovery_persistence_status=follow_through_recovery_persistence_status,
            follow_through_relapse_churn_status=follow_through_relapse_churn_status,
            follow_through_recovery_freshness_status=follow_through_recovery_freshness_status,
            follow_through_recovery_decay_status=follow_through_recovery_decay_status,
            follow_through_recovery_memory_reset_status=follow_through_recovery_memory_reset_status,
            follow_through_recovery_rebuild_strength_status=follow_through_recovery_rebuild_strength_status,
        )
        (
            follow_through_recovery_reacquisition_durability_age_runs,
            follow_through_recovery_reacquisition_durability_status,
            follow_through_recovery_reacquisition_durability_reason,
            follow_through_recovery_reacquisition_durability_summary,
        ) = _follow_through_reacquisition_durability_projection(
            item,
            prior_matches,
            follow_through_recovery_reacquisition_status=follow_through_recovery_reacquisition_status,
            follow_through_relapse_churn_status=follow_through_relapse_churn_status,
            follow_through_recovery_freshness_status=follow_through_recovery_freshness_status,
            follow_through_recovery_decay_status=follow_through_recovery_decay_status,
            follow_through_recovery_memory_reset_status=follow_through_recovery_memory_reset_status,
        )
        (
            follow_through_recovery_reacquisition_consolidation_status,
            follow_through_recovery_reacquisition_consolidation_reason,
            follow_through_recovery_reacquisition_consolidation_summary,
        ) = _follow_through_reacquisition_consolidation_projection(
            item,
            prior_matches,
            follow_through_recovery_reacquisition_status=follow_through_recovery_reacquisition_status,
            follow_through_recovery_reacquisition_durability_status=follow_through_recovery_reacquisition_durability_status,
            follow_through_relapse_churn_status=follow_through_relapse_churn_status,
            follow_through_recovery_freshness_status=follow_through_recovery_freshness_status,
            follow_through_recovery_decay_status=follow_through_recovery_decay_status,
        )
        (
            follow_through_reacquisition_softening_decay_age_runs,
            follow_through_reacquisition_softening_decay_status,
            follow_through_reacquisition_softening_decay_reason,
            follow_through_reacquisition_softening_decay_summary,
        ) = _follow_through_reacquisition_softening_decay_projection(
            item,
            prior_matches,
            follow_through_recovery_reacquisition_durability_status=follow_through_recovery_reacquisition_durability_status,
            follow_through_recovery_reacquisition_consolidation_status=follow_through_recovery_reacquisition_consolidation_status,
            follow_through_recovery_freshness_status=follow_through_recovery_freshness_status,
            follow_through_recovery_decay_status=follow_through_recovery_decay_status,
            follow_through_relapse_churn_status=follow_through_relapse_churn_status,
        )
        (
            follow_through_reacquisition_confidence_retirement_status,
            follow_through_reacquisition_confidence_retirement_reason,
            follow_through_reacquisition_confidence_retirement_summary,
        ) = _follow_through_reacquisition_confidence_retirement_projection(
            item,
            prior_matches,
            follow_through_recovery_reacquisition_durability_status=follow_through_recovery_reacquisition_durability_status,
            follow_through_recovery_reacquisition_consolidation_status=follow_through_recovery_reacquisition_consolidation_status,
            follow_through_reacquisition_softening_decay_status=follow_through_reacquisition_softening_decay_status,
            follow_through_recovery_freshness_status=follow_through_recovery_freshness_status,
            follow_through_recovery_decay_status=follow_through_recovery_decay_status,
        )
        (
            follow_through_reacquisition_revalidation_recovery_age_runs,
            follow_through_reacquisition_revalidation_recovery_status,
            follow_through_reacquisition_revalidation_recovery_reason,
            follow_through_reacquisition_revalidation_recovery_summary,
        ) = _follow_through_reacquisition_revalidation_recovery_projection(
            item,
            prior_matches,
            follow_through_recovery_reacquisition_status=follow_through_recovery_reacquisition_status,
            follow_through_recovery_reacquisition_durability_status=follow_through_recovery_reacquisition_durability_status,
            follow_through_recovery_reacquisition_consolidation_status=follow_through_recovery_reacquisition_consolidation_status,
            follow_through_reacquisition_softening_decay_status=follow_through_reacquisition_softening_decay_status,
            follow_through_reacquisition_confidence_retirement_status=follow_through_reacquisition_confidence_retirement_status,
            follow_through_recovery_freshness_status=follow_through_recovery_freshness_status,
            follow_through_recovery_decay_status=follow_through_recovery_decay_status,
        )
        follow_through_summary = _follow_through_item_summary(
            item,
            memory,
            follow_through_status=follow_through_status,
            follow_through_last_touch=follow_through_last_touch,
            follow_through_next_checkpoint=follow_through_next_checkpoint,
            follow_through_evidence_hint=follow_through_evidence_hint,
        )
        enriched_queue.append(
            {
                **item,
                "follow_through_status": follow_through_status,
                "follow_through_age_runs": follow_through_age_runs,
                "follow_through_checkpoint_status": follow_through_checkpoint_status,
                "follow_through_summary": follow_through_summary,
                "follow_through_last_touch": follow_through_last_touch,
                "follow_through_next_checkpoint": follow_through_next_checkpoint,
                "follow_through_evidence_hint": follow_through_evidence_hint,
                "follow_through_escalation_status": follow_through_escalation_status,
                "follow_through_escalation_summary": follow_through_escalation_summary,
                "follow_through_escalation_reason": follow_through_escalation_reason,
                "follow_through_recovery_age_runs": follow_through_recovery_age_runs,
                "follow_through_recovery_status": follow_through_recovery_status,
                "follow_through_recovery_summary": follow_through_recovery_summary,
                "follow_through_recovery_reason": follow_through_recovery_reason,
                "follow_through_recovery_persistence_age_runs": follow_through_recovery_persistence_age_runs,
                "follow_through_recovery_persistence_status": follow_through_recovery_persistence_status,
                "follow_through_recovery_persistence_summary": follow_through_recovery_persistence_summary,
                "follow_through_recovery_persistence_reason": follow_through_recovery_persistence_reason,
                "follow_through_relapse_churn_status": follow_through_relapse_churn_status,
                "follow_through_relapse_churn_summary": follow_through_relapse_churn_summary,
                "follow_through_relapse_churn_reason": follow_through_relapse_churn_reason,
                "follow_through_recovery_freshness_age_runs": follow_through_recovery_freshness_age_runs,
                "follow_through_recovery_freshness_status": follow_through_recovery_freshness_status,
                "follow_through_recovery_freshness_summary": follow_through_recovery_freshness_summary,
                "follow_through_recovery_freshness_reason": follow_through_recovery_freshness_reason,
                "follow_through_recovery_decay_status": follow_through_recovery_decay_status,
                "follow_through_recovery_decay_summary": follow_through_recovery_decay_summary,
                "follow_through_recovery_decay_reason": follow_through_recovery_decay_reason,
                "follow_through_recovery_memory_reset_status": follow_through_recovery_memory_reset_status,
                "follow_through_recovery_memory_reset_summary": follow_through_recovery_memory_reset_summary,
                "follow_through_recovery_memory_reset_reason": follow_through_recovery_memory_reset_reason,
                "follow_through_recovery_rebuild_strength_age_runs": follow_through_recovery_rebuild_strength_age_runs,
                "follow_through_recovery_rebuild_strength_status": follow_through_recovery_rebuild_strength_status,
                "follow_through_recovery_rebuild_strength_summary": follow_through_recovery_rebuild_strength_summary,
                "follow_through_recovery_rebuild_strength_reason": follow_through_recovery_rebuild_strength_reason,
                "follow_through_recovery_reacquisition_status": follow_through_recovery_reacquisition_status,
                "follow_through_recovery_reacquisition_summary": follow_through_recovery_reacquisition_summary,
                "follow_through_recovery_reacquisition_reason": follow_through_recovery_reacquisition_reason,
                "follow_through_recovery_reacquisition_durability_age_runs": follow_through_recovery_reacquisition_durability_age_runs,
                "follow_through_recovery_reacquisition_durability_status": follow_through_recovery_reacquisition_durability_status,
                "follow_through_recovery_reacquisition_durability_summary": follow_through_recovery_reacquisition_durability_summary,
                "follow_through_recovery_reacquisition_durability_reason": follow_through_recovery_reacquisition_durability_reason,
                "follow_through_recovery_reacquisition_consolidation_status": follow_through_recovery_reacquisition_consolidation_status,
                "follow_through_recovery_reacquisition_consolidation_summary": follow_through_recovery_reacquisition_consolidation_summary,
                "follow_through_recovery_reacquisition_consolidation_reason": follow_through_recovery_reacquisition_consolidation_reason,
                "follow_through_reacquisition_softening_decay_age_runs": follow_through_reacquisition_softening_decay_age_runs,
                "follow_through_reacquisition_softening_decay_status": follow_through_reacquisition_softening_decay_status,
                "follow_through_reacquisition_softening_decay_summary": follow_through_reacquisition_softening_decay_summary,
                "follow_through_reacquisition_softening_decay_reason": follow_through_reacquisition_softening_decay_reason,
                "follow_through_reacquisition_confidence_retirement_status": follow_through_reacquisition_confidence_retirement_status,
                "follow_through_reacquisition_confidence_retirement_summary": follow_through_reacquisition_confidence_retirement_summary,
                "follow_through_reacquisition_confidence_retirement_reason": follow_through_reacquisition_confidence_retirement_reason,
                "follow_through_reacquisition_revalidation_recovery_age_runs": follow_through_reacquisition_revalidation_recovery_age_runs,
                "follow_through_reacquisition_revalidation_recovery_status": follow_through_reacquisition_revalidation_recovery_status,
                "follow_through_reacquisition_revalidation_recovery_summary": follow_through_reacquisition_revalidation_recovery_summary,
                "follow_through_reacquisition_revalidation_recovery_reason": follow_through_reacquisition_revalidation_recovery_reason,
            }
        )
    return enriched_queue


def _queue_item_follow_through_status(
    item: dict,
    memory: dict,
    *,
    previous_match: dict | None,
    appearance_count: int,
    attention_appearances: int,
    earliest_age_days: int,
    current_generated_at: str,
) -> str:
    if not item.get("title") and not item.get("summary"):
        return "unknown"
    latest_event = memory.get("last_intervention") or {}
    has_intervention = _has_follow_through_intervention(latest_event)
    lane = item.get("lane", "")
    last_outcome = memory.get("last_outcome", "no-change")
    decision_memory_status = memory.get("decision_memory_status", "new")
    aging_status = item.get("aging_status") or _aging_status(appearance_count, earliest_age_days)
    stale_signal = (
        item.get("newly_stale")
        or aging_status in {"stale", "chronic"}
        or earliest_age_days > 7
        or appearance_count >= 3
    )
    if not item.get("source_run_id") and not has_intervention and not previous_match:
        return "unknown"
    if has_intervention and (
        lane == "deferred"
        or (
            previous_match
            and _lane_pressure(lane) >= 0
            and _lane_pressure(lane) < _lane_pressure(previous_match.get("lane"))
        )
    ):
        return "resolved"
    if (
        has_intervention
        and not stale_signal
        and _is_recent_follow_through(latest_event, current_generated_at)
    ):
        return "waiting-on-evidence"
    if stale_signal and (has_intervention or decision_memory_status in {"attempted", "persisting"}):
        return "stale-follow-through"
    if has_intervention:
        return "attempted"
    if stale_signal or (decision_memory_status == "persisting" and attention_appearances >= 2):
        return "stale-follow-through"
    if decision_memory_status in {"reopened", "new", "persisting"} or attention_appearances >= 1:
        return "untouched"
    if last_outcome in {"improved", "quieted"}:
        return "waiting-on-evidence"
    return "unknown"


def _has_follow_through_intervention(event: dict | None) -> bool:
    if not event:
        return False
    return any(
        event.get(key) for key in ("recorded_at", "event_type", "outcome", "item_id", "title")
    )


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_recent_follow_through(event: dict, current_generated_at: str) -> bool:
    recorded_at = _parse_iso_datetime(event.get("recorded_at"))
    current_generated = _parse_iso_datetime(current_generated_at)
    if not recorded_at or not current_generated:
        return False
    return abs((current_generated - recorded_at).days) <= 3


def _follow_through_last_touch_label(item: dict, memory: dict) -> str:
    latest_event = memory.get("last_intervention") or {}
    recorded_at = (latest_event.get("recorded_at") or "")[:10]
    if recorded_at:
        return f"Follow-up recorded {recorded_at}"
    last_seen_at = (memory.get("last_seen_at") or "")[:10]
    if last_seen_at:
        return f"Still visible as of {last_seen_at}"
    source_run_id = item.get("source_run_id", "")
    if source_run_id:
        return f"First surfaced in {str(source_run_id).split(':')[-1][:10]}"
    return "No recorded follow-up yet."


def _follow_through_evidence_hint(item: dict, memory: dict) -> str:
    evidence = memory.get("resolution_evidence", "")
    if evidence:
        return evidence
    if item.get("summary"):
        return str(item.get("summary"))
    return "No follow-through evidence is recorded yet."


def _follow_through_next_checkpoint(
    item: dict,
    memory: dict,
    *,
    follow_through_status: str,
) -> str:
    recommended_action = item.get("recommended_action") or "Review the latest state."
    if follow_through_status == "untouched":
        return f"Take the recommended action next and record a visible follow-up after: {recommended_action}"
    if follow_through_status == "attempted":
        return "Check the next run or linked artifact to see whether the item drops in pressure or leaves the queue."
    if follow_through_status == "waiting-on-evidence":
        return "Wait for the next run or linked artifact update to confirm whether the recent follow-up actually moved the pressure."
    if follow_through_status == "stale-follow-through":
        return "Escalate, explicitly close, or reframe this item if the next review still shows no meaningful movement."
    if follow_through_status == "resolved":
        return "Keep this on watch until the quieter state holds for another run."
    evidence = memory.get("resolution_evidence", "")
    if evidence:
        return f"Review the latest evidence before changing the next action: {evidence}"
    return "Review the latest history or artifact before assuming this item moved."


def _follow_through_checkpoint_status(
    _item: dict,
    memory: dict,
    *,
    follow_through_status: str,
    follow_through_age_runs: int,
    earliest_age_days: int,
    current_generated_at: str,
) -> str:
    latest_event = memory.get("last_intervention") or {}
    recent_follow_up = _is_recent_follow_through(latest_event, current_generated_at)
    if follow_through_status == "resolved":
        return "satisfied"
    if follow_through_status == "stale-follow-through":
        return "overdue"
    if follow_through_status == "untouched":
        return "overdue" if follow_through_age_runs >= 2 or earliest_age_days > 7 else "due-soon"
    if follow_through_status == "attempted":
        if recent_follow_up and follow_through_age_runs <= 1 and earliest_age_days <= 7:
            return "due-soon"
        return "overdue"
    if follow_through_status == "waiting-on-evidence":
        if recent_follow_up and follow_through_age_runs <= 2 and earliest_age_days <= 7:
            return "due-soon"
        return "overdue"
    return "unknown"


def _follow_through_escalation_status(
    *,
    follow_through_status: str,
    follow_through_checkpoint_status: str,
    follow_through_age_runs: int,
) -> str:
    if follow_through_status == "unknown":
        return "unknown"
    if follow_through_status == "resolved":
        return "none" if follow_through_age_runs <= 1 else "resolved-watch"
    if (
        follow_through_status == "stale-follow-through"
        or follow_through_checkpoint_status == "overdue"
    ):
        return "escalate-now"
    if follow_through_status == "untouched":
        if follow_through_age_runs >= 3:
            return "escalate-now"
        if follow_through_age_runs == 2:
            return "nudge"
        return "watch"
    if follow_through_status == "attempted":
        return "nudge"
    if follow_through_status == "waiting-on-evidence":
        return "watch" if follow_through_age_runs <= 1 else "nudge"
    return "none"


def _follow_through_escalation_reason(
    item: dict,
    memory: dict,
    *,
    follow_through_status: str,
    follow_through_checkpoint_status: str,
    follow_through_age_runs: int,
) -> str:
    label = _target_label(item)
    latest_event = memory.get("last_intervention") or {}
    recent_follow_up = latest_event.get("recorded_at") or memory.get("last_seen_at") or ""
    if follow_through_status == "resolved":
        if follow_through_age_runs <= 1:
            return f"{label} looks calmer after recent follow-through and does not need extra escalation yet."
        return f"{label} looks calmer, but it still needs one more quiet read before it can fully fade from follow-through watch."
    if follow_through_status == "stale-follow-through":
        return f"{label} has stayed open long enough after earlier follow-up that the handoff now looks overdue and should be escalated."
    if follow_through_checkpoint_status == "overdue":
        return f"{label} is past its expected checkpoint window, so it should be resurfaced more strongly now."
    if follow_through_status == "untouched":
        if follow_through_age_runs == 1:
            return f"{label} is newly surfaced and should get a visible follow-up before the next review."
        return f"{label} is still active with no recorded follow-up after {follow_through_age_runs} run(s), so it is moving from watch into a nudge state."
    if follow_through_status == "attempted":
        return f"{label} has recorded follow-up, but the pressure is still active{f' since {str(recent_follow_up)[:10]}' if recent_follow_up else ''}, so it should be nudged again if it does not settle."
    if follow_through_status == "waiting-on-evidence":
        return f"{label} has recent follow-up in flight and should stay on watch until the next run confirms quieter pressure."
    return f"{label} does not have enough timing evidence yet to support a stronger follow-through escalation."


def _follow_through_escalation_item_summary(
    item: dict,
    *,
    follow_through_checkpoint_status: str,
    follow_through_escalation_status: str,
    follow_through_escalation_reason: str,
) -> str:
    label = _target_label(item)
    if follow_through_escalation_status == "escalate-now":
        return f"{label} should be resurfaced now because its follow-through checkpoint is {follow_through_checkpoint_status}. {follow_through_escalation_reason}"
    if follow_through_escalation_status == "nudge":
        return f"{label} should be nudged again soon because the follow-through is still active without settling. {follow_through_escalation_reason}"
    if follow_through_escalation_status == "watch":
        return (
            f"{label} is not late yet, but it should stay visible until the next checkpoint lands."
        )
    if follow_through_escalation_status == "resolved-watch":
        return f"{label} looks calmer, but it should stay on resolved watch until one more quiet run confirms it."
    if follow_through_escalation_status == "none":
        return f"{label} does not currently need stronger follow-through escalation."
    return f"{label} does not yet have enough timing evidence to support a clearer escalation call."


def _follow_through_is_elevated_state(
    *,
    follow_through_status: str,
    follow_through_checkpoint_status: str,
    follow_through_escalation_status: str,
) -> bool:
    return (
        follow_through_status == "stale-follow-through"
        or follow_through_checkpoint_status == "overdue"
        or follow_through_escalation_status in {"nudge", "escalate-now"}
    )


def _follow_through_is_calm_state(
    *,
    follow_through_status: str,
    follow_through_checkpoint_status: str,
    follow_through_escalation_status: str,
) -> bool:
    if follow_through_status == "unknown":
        return False
    if follow_through_checkpoint_status == "overdue":
        return False
    if follow_through_escalation_status in {"nudge", "escalate-now", "unknown"}:
        return False
    return (
        follow_through_checkpoint_status in {"not-due", "due-soon", "satisfied"}
        or follow_through_status == "resolved"
    )


def _follow_through_escalation_level(follow_through_escalation_status: str) -> int:
    if follow_through_escalation_status == "none":
        return 0
    if follow_through_escalation_status in {"watch", "resolved-watch"}:
        return 1
    if follow_through_escalation_status == "nudge":
        return 2
    if follow_through_escalation_status == "escalate-now":
        return 3
    return -1


def _follow_through_is_recovery_candidate_state(
    *,
    follow_through_status: str,
    follow_through_checkpoint_status: str,
    follow_through_escalation_status: str,
) -> bool:
    if follow_through_status == "unknown":
        return False
    if follow_through_checkpoint_status in {"overdue", "unknown"}:
        return False
    return _follow_through_escalation_level(follow_through_escalation_status) >= 0


def _follow_through_is_positive_recovery_status(follow_through_recovery_status: str) -> bool:
    return follow_through_recovery_status in {"recovering", "retiring-watch", "retired"}


def _follow_through_history_metrics(
    item: dict,
    prior_matches: list[dict],
    *,
    follow_through_status: str,
    follow_through_checkpoint_status: str,
    follow_through_escalation_status: str,
    follow_through_recovery_status: str,
) -> dict[str, Any]:
    prior_window = list(prior_matches[: HISTORY_WINDOW_RUNS - 1])
    current_entry = {
        **item,
        "follow_through_status": follow_through_status,
        "follow_through_checkpoint_status": follow_through_checkpoint_status,
        "follow_through_escalation_status": follow_through_escalation_status,
        "follow_through_recovery_status": follow_through_recovery_status,
    }
    recent_window = [current_entry, *prior_window]

    def _entry_recovery_status(entry: dict) -> str:
        return str(entry.get("follow_through_recovery_status", "none") or "none")

    positive_path_streak = 0
    for entry in recent_window:
        if _follow_through_is_positive_recovery_status(_entry_recovery_status(entry)):
            positive_path_streak += 1
            continue
        break

    recovering_streak = 0
    for entry in recent_window:
        if _entry_recovery_status(entry) == "recovering":
            recovering_streak += 1
            continue
        break

    retired_streak = 0
    for entry in recent_window:
        if _entry_recovery_status(entry) == "retired":
            retired_streak += 1
            continue
        break

    prior_has_recovery_shape = any(
        any(
            prior.get(key) not in {None, ""}
            for key in (
                "follow_through_status",
                "follow_through_checkpoint_status",
                "follow_through_escalation_status",
                "follow_through_recovery_status",
            )
        )
        for prior in prior_window[:FOLLOW_THROUGH_RETIREMENT_WINDOW_RUNS]
    )

    compressed_states: list[str] = []
    for entry in recent_window:
        recovery_status = _entry_recovery_status(entry)
        entry_status = str(entry.get("follow_through_status", "unknown") or "unknown")
        entry_checkpoint = str(
            entry.get("follow_through_checkpoint_status", "unknown") or "unknown"
        )
        entry_escalation = str(
            entry.get("follow_through_escalation_status", "unknown") or "unknown"
        )
        state = "other"
        if _follow_through_is_positive_recovery_status(recovery_status):
            state = "positive"
        elif recovery_status == "relapsing":
            state = "relapse"
        elif _follow_through_is_elevated_state(
            follow_through_status=entry_status,
            follow_through_checkpoint_status=entry_checkpoint,
            follow_through_escalation_status=entry_escalation,
        ):
            state = "elevated"
        elif _follow_through_is_calm_state(
            follow_through_status=entry_status,
            follow_through_checkpoint_status=entry_checkpoint,
            follow_through_escalation_status=entry_escalation,
        ):
            state = "calm"
        if state == "other":
            continue
        if not compressed_states or compressed_states[-1] != state:
            compressed_states.append(state)

    positive_segments = sum(1 for state in compressed_states if state == "positive")
    elevated_segments = sum(1 for state in compressed_states if state in {"elevated", "relapse"})
    repeated_flip = positive_segments >= 2 and elevated_segments >= 2
    mild_wobble = positive_segments >= 2 and elevated_segments == 1
    blocked_pressure = (
        _follow_through_is_positive_recovery_status(follow_through_recovery_status)
        and item.get("lane") in {"blocked", "urgent"}
        and follow_through_escalation_status in {"nudge", "escalate-now"}
        and not (item.get("links") or [])
    )
    return {
        "recent_window": recent_window,
        "prior_window": prior_window,
        "positive_path_streak": positive_path_streak,
        "recovering_streak": recovering_streak,
        "retired_streak": retired_streak,
        "prior_has_recovery_shape": prior_has_recovery_shape,
        "compressed_states": compressed_states,
        "positive_segments": positive_segments,
        "elevated_segments": elevated_segments,
        "repeated_flip": repeated_flip,
        "mild_wobble": mild_wobble,
        "blocked_pressure": blocked_pressure,
    }


def _follow_through_recovery_projection(
    item: dict,
    prior_matches: list[dict],
    *,
    follow_through_status: str,
    follow_through_checkpoint_status: str,
    follow_through_escalation_status: str,
) -> tuple[int, str, str, str]:
    label = _target_label(item)
    prior_window = list(prior_matches[: HISTORY_WINDOW_RUNS - 1])
    current_entry = {
        **item,
        "follow_through_status": follow_through_status,
        "follow_through_checkpoint_status": follow_through_checkpoint_status,
        "follow_through_escalation_status": follow_through_escalation_status,
    }
    recent_window = [current_entry, *prior_window]
    current_is_elevated = _follow_through_is_elevated_state(
        follow_through_status=follow_through_status,
        follow_through_checkpoint_status=follow_through_checkpoint_status,
        follow_through_escalation_status=follow_through_escalation_status,
    )
    current_is_calm = _follow_through_is_calm_state(
        follow_through_status=follow_through_status,
        follow_through_checkpoint_status=follow_through_checkpoint_status,
        follow_through_escalation_status=follow_through_escalation_status,
    )
    current_is_recovery_candidate = _follow_through_is_recovery_candidate_state(
        follow_through_status=follow_through_status,
        follow_through_checkpoint_status=follow_through_checkpoint_status,
        follow_through_escalation_status=follow_through_escalation_status,
    )
    prior_has_follow_through_shape = any(
        any(
            prior.get(key) not in {None, ""}
            for key in (
                "follow_through_status",
                "follow_through_checkpoint_status",
                "follow_through_escalation_status",
                "follow_through_recovery_status",
            )
        )
        for prior in prior_window[:FOLLOW_THROUGH_RETIREMENT_WINDOW_RUNS]
    )

    calm_streak = 0
    for entry in recent_window:
        entry_status = str(entry.get("follow_through_status", "unknown") or "unknown")
        entry_checkpoint = str(
            entry.get("follow_through_checkpoint_status", "unknown") or "unknown"
        )
        entry_escalation = str(
            entry.get("follow_through_escalation_status", "unknown") or "unknown"
        )
        if _follow_through_is_calm_state(
            follow_through_status=entry_status,
            follow_through_checkpoint_status=entry_checkpoint,
            follow_through_escalation_status=entry_escalation,
        ):
            calm_streak += 1
            continue
        break

    recovery_candidate_streak = 0
    for entry in recent_window:
        entry_status = str(entry.get("follow_through_status", "unknown") or "unknown")
        entry_checkpoint = str(
            entry.get("follow_through_checkpoint_status", "unknown") or "unknown"
        )
        entry_escalation = str(
            entry.get("follow_through_escalation_status", "unknown") or "unknown"
        )
        if _follow_through_is_recovery_candidate_state(
            follow_through_status=entry_status,
            follow_through_checkpoint_status=entry_checkpoint,
            follow_through_escalation_status=entry_escalation,
        ):
            recovery_candidate_streak += 1
            continue
        break

    prior_calm_streak = 0
    for entry in prior_window[:FOLLOW_THROUGH_RETIREMENT_WINDOW_RUNS]:
        entry_status = str(entry.get("follow_through_status", "unknown") or "unknown")
        entry_checkpoint = str(
            entry.get("follow_through_checkpoint_status", "unknown") or "unknown"
        )
        entry_escalation = str(
            entry.get("follow_through_escalation_status", "unknown") or "unknown"
        )
        if _follow_through_is_calm_state(
            follow_through_status=entry_status,
            follow_through_checkpoint_status=entry_checkpoint,
            follow_through_escalation_status=entry_escalation,
        ):
            prior_calm_streak += 1
            continue
        break

    recent_elevated_index: int | None = None
    recent_elevated_level = -1
    for index, entry in enumerate(recent_window[1:], start=1):
        entry_status = str(entry.get("follow_through_status", "unknown") or "unknown")
        entry_checkpoint = str(
            entry.get("follow_through_checkpoint_status", "unknown") or "unknown"
        )
        entry_escalation = str(
            entry.get("follow_through_escalation_status", "unknown") or "unknown"
        )
        if _follow_through_is_elevated_state(
            follow_through_status=entry_status,
            follow_through_checkpoint_status=entry_checkpoint,
            follow_through_escalation_status=entry_escalation,
        ):
            recent_elevated_index = index
            recent_elevated_level = _follow_through_escalation_level(entry_escalation)
            break
    has_recent_elevated_context = (
        recent_elevated_index is not None
        and recent_elevated_index <= FOLLOW_THROUGH_RETIREMENT_WINDOW_RUNS
    )
    current_escalation_level = _follow_through_escalation_level(follow_through_escalation_status)

    if current_is_elevated:
        prior_has_recent_calm = prior_calm_streak > 0
        prior_elevated_after_calm = False
        after_calm_index = prior_calm_streak
        if prior_has_recent_calm and after_calm_index < len(prior_window):
            entry = prior_window[after_calm_index]
            prior_elevated_after_calm = _follow_through_is_elevated_state(
                follow_through_status=str(
                    entry.get("follow_through_status", "unknown") or "unknown"
                ),
                follow_through_checkpoint_status=str(
                    entry.get("follow_through_checkpoint_status", "unknown") or "unknown"
                ),
                follow_through_escalation_status=str(
                    entry.get("follow_through_escalation_status", "unknown") or "unknown"
                ),
            )
        if prior_has_recent_calm and prior_elevated_after_calm:
            reason = f"{label} had started calming down after earlier escalation, but it has returned to an overdue or escalated state and now counts as a relapse."
            return (
                1,
                "relapsing",
                reason,
                f"{label} is relapsing after a brief calmer period and should stay surfaced until the pressure settles again.",
            )
        if (
            current_is_recovery_candidate
            and has_recent_elevated_context
            and recent_elevated_level > current_escalation_level >= 0
        ):
            recovery_age_runs = max(
                1, min(recovery_candidate_streak, FOLLOW_THROUGH_RETIREMENT_WINDOW_RUNS)
            )
            reason = f"{label} was recently escalated more strongly, but the checkpoint is no longer overdue and the escalation has stepped down, so it is actively recovering."
            return (
                recovery_age_runs,
                "recovering",
                reason,
                f"{label} is recovering from recent escalation, but the lower-pressure state still needs to hold.",
            )
        return (
            0,
            "none",
            f"{label} is still in active escalation and has not yet started a calmer recovery path.",
            f"{label} is still in active escalation.",
        )

    if current_is_calm and has_recent_elevated_context:
        recovery_age_runs = max(1, min(calm_streak, FOLLOW_THROUGH_RETIREMENT_WINDOW_RUNS))
        if follow_through_status == "resolved" or follow_through_checkpoint_status == "satisfied":
            if calm_streak >= 2:
                reason = f"{label} has stayed calm for {min(calm_streak, FOLLOW_THROUGH_RETIREMENT_WINDOW_RUNS)} consecutive run(s) after recent escalation, so the stronger resurfacing can retire."
                return (
                    recovery_age_runs,
                    "retired",
                    reason,
                    f"{label} has retired its recent escalation after holding a calmer state across consecutive runs.",
                )
            reason = f"{label} now looks calm after recent escalation, but it has only one quiet confirmation run so far and should stay on retirement watch."
            return (
                recovery_age_runs,
                "retiring-watch",
                reason,
                f"{label} is calmer now, but it needs one more quiet run before the escalation fully retires.",
            )
        reason = f"{label} was recently escalated, but the checkpoint is no longer overdue and the escalation has stepped down, so it is actively recovering."
        return (
            recovery_age_runs,
            "recovering",
            reason,
            f"{label} is recovering from recent escalation, but the lower-pressure state still needs to hold.",
        )

    if (
        current_is_recovery_candidate
        and has_recent_elevated_context
        and recent_elevated_level > current_escalation_level >= 0
    ):
        recovery_age_runs = max(
            1, min(recovery_candidate_streak, FOLLOW_THROUGH_RETIREMENT_WINDOW_RUNS)
        )
        reason = f"{label} was recently escalated more strongly, but the checkpoint is no longer overdue and the escalation has stepped down, so it is actively recovering."
        return (
            recovery_age_runs,
            "recovering",
            reason,
            f"{label} is recovering from recent escalation, but the lower-pressure state still needs to hold.",
        )

    if current_is_calm and prior_window and not prior_has_follow_through_shape:
        reason = f"{label} looks calmer now, but the older queue snapshots do not have enough follow-through detail to say whether this is a real recovery or a one-run blip."
        return (
            1,
            "insufficient-evidence",
            reason,
            f"{label} may be calming down, but there is not enough earlier follow-through evidence to retire the escalation confidently.",
        )

    return (
        0,
        "none",
        f"{label} does not have a recent escalated follow-through path to recover from.",
        f"{label} does not currently show a recent recovery or escalation-retirement pattern.",
    )


def _follow_through_recovery_persistence_projection(
    item: dict,
    prior_matches: list[dict],
    *,
    follow_through_status: str,
    follow_through_checkpoint_status: str,
    follow_through_escalation_status: str,
    follow_through_recovery_status: str,
) -> tuple[int, str, str, str]:
    label = _target_label(item)
    history = _follow_through_history_metrics(
        item,
        prior_matches,
        follow_through_status=follow_through_status,
        follow_through_checkpoint_status=follow_through_checkpoint_status,
        follow_through_escalation_status=follow_through_escalation_status,
        follow_through_recovery_status=follow_through_recovery_status,
    )
    positive_path_streak = int(history["positive_path_streak"])
    recovering_streak = int(history["recovering_streak"])
    retired_streak = int(history["retired_streak"])
    repeated_flip = bool(history["repeated_flip"])
    mild_wobble = bool(history["mild_wobble"])
    prior_has_recovery_shape = bool(history["prior_has_recovery_shape"])

    if follow_through_recovery_status == "none":
        return (
            0,
            "none",
            f"{label} does not currently have a recent recovery or retirement path to persist.",
            f"{label} does not currently show a recovery or retirement hold.",
        )
    if follow_through_recovery_status == "insufficient-evidence":
        return (
            1,
            "insufficient-evidence",
            f"{label} may be calming down, but the recent history is still too thin to judge whether the recovery is really holding.",
            f"{label} may be calming down, but there is not enough history yet to judge whether the recovery is really holding.",
        )
    if follow_through_recovery_status == "relapsing":
        return (
            0,
            "none",
            f"{label} has already slipped back into a relapse state, so the earlier calmer path is no longer holding.",
            f"{label} is no longer in a stable enough recovery state to count as holding.",
        )
    if not prior_has_recovery_shape and follow_through_recovery_status in {
        "recovering",
        "retiring-watch",
        "retired",
    }:
        return (
            1,
            "insufficient-evidence",
            f"{label} looks calmer now, but there is not enough earlier recovery history to judge whether the calmer path is genuinely holding.",
            f"{label} looks calmer, but there is not enough history yet to say whether that calmer path is really holding.",
        )
    if follow_through_recovery_status == "recovering":
        if repeated_flip or mild_wobble:
            age_runs = max(1, positive_path_streak)
            return (
                age_runs,
                "fragile-recovery",
                f"{label} is still in recovery, but the calmer path has already shown a wobble and now looks fragile rather than settled.",
                f"{label} is recovering, but the calmer path still looks fragile rather than settled.",
            )
        if recovering_streak >= 2:
            return (
                recovering_streak,
                "holding-recovery",
                f"{label} has held its recovery posture for {recovering_streak} consecutive run(s) without returning to overdue or escalated pressure.",
                f"{label} is actively holding a calmer recovery posture.",
            )
        return (
            1,
            "just-recovering",
            f"{label} has only one calmer confirmation run so far, so the recovery is newly back but not proven yet.",
            f"{label} is only newly back in recovery and still needs another calmer confirmation run.",
        )
    if follow_through_recovery_status == "retiring-watch":
        age_runs = max(1, positive_path_streak)
        if repeated_flip or mild_wobble:
            return (
                age_runs,
                "fragile-recovery",
                f"{label} is on retirement watch, but the calmer path has already shown enough wobble that the recovery still looks fragile.",
                f"{label} is on retirement watch, but the calmer path still looks fragile.",
            )
        if age_runs >= 2:
            return (
                age_runs,
                "sustained-retiring-watch",
                f"{label} has stayed calm across {age_runs} consecutive recovery-side runs and is now holding retirement watch more convincingly.",
                f"{label} is on retirement watch and that calmer state is actively holding.",
            )
        return (
            age_runs,
            "holding-retiring-watch",
            f"{label} has entered retirement watch, but it still has only one calm confirmation run after stepping down from escalation.",
            f"{label} is on retirement watch, but it still needs another calm confirmation run.",
        )
    if follow_through_recovery_status == "retired":
        if retired_streak >= 2:
            return (
                retired_streak,
                "sustained-retired",
                f"{label} has held a retired calm state for {retired_streak} consecutive runs after retirement, so the earlier escalation now looks genuinely retired.",
                f"{label} has sustained its retired follow-through state across multiple calm runs.",
            )
        age_runs = max(1, positive_path_streak)
        return (
            age_runs,
            "sustained-retiring-watch",
            f"{label} has just crossed into a retired calmer state, but it still needs another calm run before that retirement looks fully sustained.",
            f"{label} has just crossed into retirement and needs one more calm run before it looks fully sustained.",
        )
    return (
        0,
        "none",
        f"{label} does not currently have a recovery persistence path that needs a stronger classification.",
        f"{label} does not currently show a recovery persistence pattern.",
    )


def _follow_through_relapse_churn_projection(
    item: dict,
    prior_matches: list[dict],
    *,
    follow_through_status: str,
    follow_through_checkpoint_status: str,
    follow_through_escalation_status: str,
    follow_through_recovery_status: str,
    follow_through_recovery_persistence_status: str,
) -> tuple[str, str, str]:
    label = _target_label(item)
    history = _follow_through_history_metrics(
        item,
        prior_matches,
        follow_through_status=follow_through_status,
        follow_through_checkpoint_status=follow_through_checkpoint_status,
        follow_through_escalation_status=follow_through_escalation_status,
        follow_through_recovery_status=follow_through_recovery_status,
    )
    prior_has_recovery_shape = bool(history["prior_has_recovery_shape"])
    positive_segments = int(history["positive_segments"])
    elevated_segments = int(history["elevated_segments"])
    repeated_flip = bool(history["repeated_flip"])
    mild_wobble = bool(history["mild_wobble"])
    blocked_pressure = bool(history["blocked_pressure"])

    if follow_through_recovery_status == "none":
        return (
            "none",
            f"{label} does not currently have an active recovery path to judge for relapse churn.",
            f"{label} does not currently show relapse churn.",
        )
    if follow_through_recovery_status == "insufficient-evidence":
        return (
            "insufficient-evidence",
            f"{label} does not yet have enough recovery-side history to judge whether the calmer path is wobbling.",
            f"{label} does not yet have enough history to judge relapse churn.",
        )
    if not prior_has_recovery_shape and follow_through_recovery_status in {
        "recovering",
        "retiring-watch",
        "retired",
    }:
        return (
            "insufficient-evidence",
            f"{label} has started calming down, but there is not enough earlier recovery history to judge whether the calmer path is stable or noisy.",
            f"{label} does not yet have enough history to judge whether the calmer path is stable or noisy.",
        )
    if blocked_pressure:
        return (
            "blocked",
            f"{label} looks calmer locally, but the queue pressure is still active without linked evidence to confirm that the recovery is really holding.",
            f"{label} looks calmer locally, but unresolved pressure is still blocking confidence in the recovery hold.",
        )
    if repeated_flip or positive_segments >= 2 and elevated_segments >= 2:
        return (
            "churn",
            f"{label} has flipped between calmer and escalated states multiple times in the recent window, so the recovery path now looks churn-heavy.",
            f"{label} is churning between calmer and escalated states instead of holding a stable recovery path.",
        )
    if follow_through_recovery_status == "relapsing":
        return (
            "fragile",
            f"{label} has already slipped back into escalated pressure after looking calmer, so the recovery path now looks fragile rather than stable.",
            f"{label} has relapsed after a brief calmer period, which makes the overall recovery path fragile.",
        )
    if mild_wobble:
        if follow_through_recovery_persistence_status == "fragile-recovery":
            return (
                "fragile",
                f"{label} is still on a recovery path, but a recent wobble has softened confidence that the calmer state will hold.",
                f"{label} is still recovering, but the calmer path looks fragile after a recent wobble.",
            )
        return (
            "watch",
            f"{label} had one mild wobble after recovery began, so it should stay visible until another calmer run confirms that the recovery is holding.",
            f"{label} had one mild wobble and should stay on watch until the calmer path proves itself again.",
        )
    return (
        "none",
        f"{label} is not currently showing relapse churn beyond the normal recovery path.",
        f"{label} is not currently showing relapse churn.",
    )


def _follow_through_recovery_freshness_projection(
    item: dict,
    prior_matches: list[dict],
    *,
    follow_through_status: str,
    follow_through_checkpoint_status: str,
    follow_through_escalation_status: str,
    follow_through_recovery_status: str,
    follow_through_recovery_persistence_status: str,
    follow_through_relapse_churn_status: str,
) -> tuple[int, str, str, str]:
    label = _target_label(item)
    history = _follow_through_history_metrics(
        item,
        prior_matches,
        follow_through_status=follow_through_status,
        follow_through_checkpoint_status=follow_through_checkpoint_status,
        follow_through_escalation_status=follow_through_escalation_status,
        follow_through_recovery_status=follow_through_recovery_status,
    )
    positive_path_streak = int(history["positive_path_streak"])
    retired_streak = int(history["retired_streak"])
    prior_has_recovery_shape = bool(history["prior_has_recovery_shape"])
    repeated_flip = bool(history["repeated_flip"])
    mild_wobble = bool(history["mild_wobble"])
    strong_holding_statuses = {
        "holding-recovery",
        "holding-retiring-watch",
        "sustained-retiring-watch",
        "sustained-retired",
    }

    if follow_through_recovery_status == "none":
        return (
            0,
            "none",
            f"{label} does not currently have a recovery path whose freshness needs to be judged.",
            f"{label} does not currently show recovery freshness.",
        )
    if (
        follow_through_recovery_status == "insufficient-evidence"
        or follow_through_recovery_persistence_status == "insufficient-evidence"
        or (
            not prior_has_recovery_shape
            and follow_through_recovery_status in {"recovering", "retiring-watch", "retired"}
        )
    ):
        return (
            1,
            "insufficient-evidence",
            f"{label} may be calmer, but the recovery history is still too thin to judge whether that calmer memory is fresh or already aging.",
            f"{label} may be calmer, but there is not enough recovery history yet to judge freshness.",
        )
    if follow_through_recovery_status == "relapsing":
        return (
            0,
            "none",
            f"{label} is already relapsing, so the earlier calmer memory is no longer fresh enough to treat as active support.",
            f"{label} is no longer carrying fresh recovery memory.",
        )
    if retired_streak >= FOLLOW_THROUGH_RETIREMENT_WINDOW_RUNS:
        return (
            retired_streak,
            "stale",
            f"{label} is still calmer, but the recovery memory is now leaning mostly on older retired runs instead of fresh confirmation.",
            f"{label} still looks calmer, but that recovery memory is now aging out.",
        )
    if repeated_flip or follow_through_relapse_churn_status in {"churn"}:
        age_runs = max(1, positive_path_streak)
        return (
            age_runs,
            "mixed-age",
            f"{label} still has some recovery memory, but it is now mixed with recent elevated flips and should not count as fully fresh.",
            f"{label} still has some recovery memory, but that signal is now mixed-age rather than fully fresh.",
        )
    if (
        mild_wobble
        or follow_through_relapse_churn_status in {"watch", "fragile", "blocked"}
        or follow_through_recovery_persistence_status == "fragile-recovery"
    ):
        age_runs = max(1, positive_path_streak)
        return (
            age_runs,
            "mixed-age",
            f"{label} still has useful recovery memory, but a recent wobble has softened it into a mixed-age signal.",
            f"{label} still has useful recovery memory, but part of that calmer signal is already softening.",
        )
    if (
        follow_through_recovery_persistence_status in strong_holding_statuses
        and positive_path_streak >= 2
    ):
        return (
            positive_path_streak,
            "holding-fresh",
            f"{label} has held a calmer recovery posture across consecutive runs and that recovery memory still looks fresh.",
            f"{label} has fresh recovery memory that is actively holding.",
        )
    if follow_through_recovery_status in {"recovering", "retiring-watch", "retired"}:
        age_runs = max(1, positive_path_streak)
        return (
            age_runs,
            "fresh",
            f"{label} has a recent calmer path with no meaningful wobble yet, so the recovery memory still looks fresh.",
            f"{label} still has fresh recovery memory.",
        )
    return (
        0,
        "none",
        f"{label} does not currently have a recovery freshness posture to project.",
        f"{label} does not currently show recovery freshness.",
    )


def _follow_through_recovery_decay_projection(
    item: dict,
    prior_matches: list[dict],
    *,
    follow_through_recovery_status: str,
    follow_through_recovery_persistence_status: str,
    follow_through_relapse_churn_status: str,
    follow_through_recovery_freshness_status: str,
) -> tuple[str, str, str]:
    label = _target_label(item)
    if follow_through_recovery_freshness_status == "none":
        return (
            "none",
            f"{label} does not currently have fresh recovery memory to decay.",
            f"{label} is not currently showing recovery-memory decay.",
        )
    if follow_through_recovery_freshness_status == "insufficient-evidence":
        return (
            "insufficient-evidence",
            f"{label} may be calming down, but there is not enough history to tell whether the recovery memory is decaying yet.",
            f"{label} does not yet have enough history to judge freshness decay.",
        )
    if follow_through_recovery_freshness_status == "holding-fresh":
        return (
            "none",
            f"{label} still has strong fresh confirmation behind its calmer posture, so no recovery-memory decay needs to be surfaced yet.",
            f"{label} is holding a fresh recovery path without visible decay.",
        )
    if follow_through_recovery_freshness_status == "fresh":
        return (
            "none",
            f"{label} still has recent calmer confirmation behind it, so the recovery memory has not started decaying yet.",
            f"{label} still has fresh enough recovery memory.",
        )
    if follow_through_recovery_freshness_status == "mixed-age":
        if (
            follow_through_relapse_churn_status in {"fragile", "blocked", "churn"}
            or follow_through_recovery_persistence_status == "fragile-recovery"
        ):
            return (
                "fragile-aging",
                f"{label} still has some recovery memory, but wobble and mixed-age evidence now make that calmer path fragile and aging.",
                f"{label} still has some recovery memory, but it is aging in a fragile way.",
            )
        return (
            "softening",
            f"{label} still has useful recovery memory, but part of that calmer signal is aging and should now be weighted more cautiously.",
            f"{label} still looks calmer, but the recovery memory is already softening.",
        )
    if follow_through_recovery_freshness_status == "stale":
        if follow_through_recovery_status == "retired":
            return (
                "expired",
                f"{label} is still quieter, but the recovery memory is now old enough that the stronger holding posture should expire unless fresh evidence returns.",
                f"{label}'s older recovery confidence is now expiring.",
            )
        if (
            follow_through_relapse_churn_status in {"watch", "fragile", "blocked", "churn"}
            or follow_through_recovery_persistence_status == "fragile-recovery"
        ):
            return (
                "fragile-aging",
                f"{label} is leaning on older calmer memory while the live path still looks noisy, so the recovery confidence is aging in a fragile way.",
                f"{label}'s recovery memory is aging out and still looks fragile.",
            )
        return (
            "aging",
            f"{label} is still leaning on older recovery memory, but it no longer has enough fresh confirmation to keep the stronger hold posture on its own.",
            f"{label}'s recovery memory is aging out.",
        )
    return (
        "none",
        f"{label} does not currently have a recovery decay posture that needs a stronger label.",
        f"{label} is not currently showing recovery-memory decay.",
    )


def _follow_through_recovery_memory_reset_projection(
    item: dict,
    prior_matches: list[dict],
    *,
    follow_through_recovery_status: str,
    follow_through_recovery_freshness_status: str,
    follow_through_recovery_decay_status: str,
) -> tuple[str, str, str]:
    label = _target_label(item)
    prior_window = list(prior_matches[: HISTORY_WINDOW_RUNS - 1])
    prior_reset_statuses = [
        str(entry.get("follow_through_recovery_memory_reset_status", "none") or "none")
        for entry in prior_window
        if entry.get("follow_through_recovery_memory_reset_status") not in {None, ""}
    ]
    has_recent_reset = any(
        status in {"reset-watch", "resetting", "reset"}
        for status in prior_reset_statuses[:FOLLOW_THROUGH_RETIREMENT_WINDOW_RUNS]
    )

    if follow_through_recovery_freshness_status == "none":
        return (
            "none",
            f"{label} does not currently have a recovery-memory reset path to manage.",
            f"{label} is not currently showing a recovery-memory reset path.",
        )
    if (
        follow_through_recovery_freshness_status == "insufficient-evidence"
        or follow_through_recovery_decay_status == "insufficient-evidence"
    ):
        return (
            "insufficient-evidence",
            f"{label} may be calming down, but the recovery memory is still too thin to judge whether it should reset or rebuild.",
            f"{label} does not yet have enough history to judge recovery-memory reset.",
        )
    if has_recent_reset and follow_through_recovery_freshness_status in {"fresh", "mixed-age"}:
        return (
            "rebuilding",
            f"{label} had its older recovery confidence reset recently and is now rebuilding calmer support with fresh evidence.",
            f"{label} is rebuilding recovery memory after an earlier reset.",
        )
    if follow_through_recovery_decay_status in {"softening", "aging"}:
        return (
            "reset-watch",
            f"{label} still has some calmer carry-forward, but the recovery memory is softening enough that it should move onto reset watch if fresh confirmation does not return soon.",
            f"{label} still looks calmer, but its recovery memory is now on reset watch.",
        )
    if follow_through_recovery_decay_status == "fragile-aging":
        return (
            "resetting",
            f"{label} is still leaning on older calmer memory, but the mixed-age and wobble signals are strong enough that the earlier stronger hold is now stepping down.",
            f"{label}'s earlier recovery confidence is now actively resetting.",
        )
    if follow_through_recovery_decay_status == "expired":
        return (
            "reset",
            f"{label} no longer has enough fresh calmer confirmation to keep the earlier stronger recovery hold, so that older recovery memory should now be treated as reset.",
            f"{label}'s older recovery confidence has now reset.",
        )
    if has_recent_reset and follow_through_recovery_status in {"recovering", "retiring-watch"}:
        return (
            "rebuilding",
            f"{label} had older recovery confidence reset earlier and is now starting to accumulate calmer evidence again.",
            f"{label} is rebuilding recovery memory after a prior reset.",
        )
    return (
        "none",
        f"{label} still has enough fresh calmer support that no recovery-memory reset needs to be surfaced yet.",
        f"{label} is not currently showing a recovery-memory reset.",
    )


def _follow_through_recovery_rebuild_strength_projection(
    item: dict,
    prior_matches: list[dict],
    *,
    follow_through_recovery_status: str,
    follow_through_recovery_persistence_status: str,
    follow_through_relapse_churn_status: str,
    follow_through_recovery_freshness_status: str,
    follow_through_recovery_decay_status: str,
    follow_through_recovery_memory_reset_status: str,
) -> tuple[int, str, str, str]:
    label = _target_label(item)
    prior_window = list(prior_matches[: HISTORY_WINDOW_RUNS - 1])
    current_entry = {
        **item,
        "follow_through_recovery_status": follow_through_recovery_status,
        "follow_through_recovery_persistence_status": follow_through_recovery_persistence_status,
        "follow_through_relapse_churn_status": follow_through_relapse_churn_status,
        "follow_through_recovery_freshness_status": follow_through_recovery_freshness_status,
        "follow_through_recovery_decay_status": follow_through_recovery_decay_status,
        "follow_through_recovery_memory_reset_status": follow_through_recovery_memory_reset_status,
    }
    recent_window = [current_entry, *prior_window]

    rebuild_path_streak = 0
    for entry in recent_window:
        reset_status = str(
            entry.get("follow_through_recovery_memory_reset_status", "none") or "none"
        )
        if reset_status == "rebuilding":
            rebuild_path_streak += 1
            continue
        break

    if follow_through_recovery_memory_reset_status == "none":
        return (
            0,
            "none",
            f"{label} does not currently have an active post-reset rebuild path.",
            f"{label} is not currently rebuilding recovery confidence after reset.",
        )
    if follow_through_recovery_memory_reset_status == "insufficient-evidence":
        return (
            1,
            "insufficient-evidence",
            f"{label} may be starting to calm again after reset, but the history is still too thin to tell whether this is a real rebuild.",
            f"{label} may be rebuilding after reset, but there is not enough history yet to judge rebuild strength.",
        )
    if follow_through_recovery_memory_reset_status != "rebuilding":
        return (
            0,
            "none",
            f"{label} is not currently in the rebuilding phase of recovery-memory reset.",
            f"{label} is not currently rebuilding after reset.",
        )

    if (
        follow_through_recovery_status == "insufficient-evidence"
        or follow_through_recovery_freshness_status == "insufficient-evidence"
        or follow_through_recovery_decay_status == "insufficient-evidence"
    ):
        return (
            1,
            "insufficient-evidence",
            f"{label} is trying to rebuild calmer support after reset, but the available evidence is still too thin to judge whether that rebuild is real.",
            f"{label} is rebuilding after reset, but there is not enough evidence yet to judge its strength.",
        )

    if (
        follow_through_relapse_churn_status in {"fragile", "churn", "blocked"}
        or follow_through_recovery_persistence_status == "fragile-recovery"
        or follow_through_recovery_freshness_status in {"mixed-age", "stale"}
        or follow_through_recovery_decay_status
        in {"softening", "aging", "fragile-aging", "expired"}
    ):
        age_runs = max(1, rebuild_path_streak)
        return (
            age_runs,
            "fragile-rebuild",
            f"{label} is rebuilding after reset, but mixed-age support or recovery wobble is still making that calmer path fragile.",
            f"{label} is rebuilding after reset, but the rebuild still looks fragile rather than re-earned.",
        )

    if rebuild_path_streak >= 3:
        return (
            rebuild_path_streak,
            "holding-rebuild",
            f"{label} has rebuilt calmer support across {rebuild_path_streak} consecutive run(s) after reset without fresh reset pressure returning.",
            f"{label} is rebuilding well enough after reset that the calmer posture is starting to hold.",
        )
    if rebuild_path_streak >= 2:
        return (
            rebuild_path_streak,
            "building",
            f"{label} is adding another calmer confirmation run after reset, but the rebuilt posture has not held long enough to be trusted as stable yet.",
            f"{label} is actively strengthening its calmer support after reset, but it is not stable yet.",
        )
    return (
        max(1, rebuild_path_streak),
        "just-rebuilding",
        f"{label} has only one calmer confirmation run after reset, so the rebuild is just starting and still needs more proof.",
        f"{label} has only just started rebuilding calmer support after reset.",
    )


def _follow_through_recovery_reacquisition_projection(
    item: dict,
    prior_matches: list[dict],
    *,
    follow_through_recovery_persistence_status: str,
    follow_through_relapse_churn_status: str,
    follow_through_recovery_freshness_status: str,
    follow_through_recovery_decay_status: str,
    follow_through_recovery_memory_reset_status: str,
    follow_through_recovery_rebuild_strength_status: str,
) -> tuple[str, str, str]:
    label = _target_label(item)
    prior_window = list(prior_matches[: HISTORY_WINDOW_RUNS - 1])
    recent_window = [
        {
            **item,
            "follow_through_recovery_reacquisition_status": "",
        },
        *prior_window,
    ]

    current_is_candidate = (
        follow_through_recovery_memory_reset_status == "rebuilding"
        and follow_through_recovery_rebuild_strength_status in {"building", "holding-rebuild"}
        and follow_through_recovery_persistence_status
        in {
            "holding-recovery",
            "holding-retiring-watch",
            "sustained-retiring-watch",
            "sustained-retired",
        }
        and follow_through_recovery_freshness_status in {"fresh", "holding-fresh"}
    )

    prior_reacquisition_streak = 0
    for entry in recent_window[1:]:
        prior_status = str(
            entry.get("follow_through_recovery_reacquisition_status", "none") or "none"
        )
        if prior_status in {"reacquiring", "just-reacquired", "holding-reacquired", "reacquired"}:
            prior_reacquisition_streak += 1
            continue
        break

    if follow_through_recovery_rebuild_strength_status == "none":
        return (
            "none",
            f"{label} does not currently have a post-reset rebuild path that is close to re-earning stronger calmer support.",
            f"{label} has not started re-acquiring stronger calmer support yet.",
        )
    if (
        follow_through_recovery_rebuild_strength_status == "insufficient-evidence"
        or follow_through_recovery_memory_reset_status == "insufficient-evidence"
    ):
        return (
            "insufficient-evidence",
            f"{label} may be rebuilding after reset, but there is not enough evidence yet to judge whether stronger calmer support is being re-acquired.",
            f"{label} may be rebuilding after reset, but there is not enough evidence yet to judge reacquisition.",
        )
    if (
        follow_through_recovery_rebuild_strength_status == "fragile-rebuild"
        or follow_through_relapse_churn_status in {"fragile", "churn", "blocked"}
        or follow_through_recovery_freshness_status in {"mixed-age", "stale"}
        or follow_through_recovery_decay_status
        in {"softening", "aging", "fragile-aging", "expired"}
    ):
        return (
            "fragile-reacquisition",
            f"{label} is rebuilding after reset, but wobble or aging support still makes the would-be re-acquisition too fragile to trust as re-earned.",
            f"{label} is rebuilding after reset, but the stronger calmer posture still looks too fragile to call re-acquired.",
        )
    if not current_is_candidate:
        return (
            "none",
            f"{label} is rebuilding after reset, but it has not yet crossed the threshold where stronger calmer support looks close to being re-earned.",
            f"{label} is rebuilding after reset, but it has not started re-acquiring a stronger calmer posture yet.",
        )

    if follow_through_recovery_rebuild_strength_status == "building":
        return (
            "reacquiring",
            f"{label} is close to re-earning stronger calmer support after reset, but the rebuilt posture has not crossed the hold threshold yet.",
            f"{label} is close to re-acquiring stronger calmer support, but it still needs another confirming run.",
        )

    reacquisition_age = prior_reacquisition_streak + 1
    if reacquisition_age >= 3:
        return (
            "reacquired",
            f"{label} has kept its stronger post-reset calmer posture through the full reacquisition window, so that rebuilt support now looks genuinely re-earned.",
            f"{label} has re-acquired stronger calmer support and it is now holding across the full confirmation window.",
        )
    if reacquisition_age >= 2:
        return (
            "holding-reacquired",
            f"{label} re-earned stronger calmer support after reset and has now held that restored posture for {reacquisition_age} consecutive run(s), but it is not fully durable yet.",
            f"{label} has re-acquired stronger calmer support and it is actively holding.",
        )
    return (
        "just-reacquired",
        f"{label} has just crossed back into stronger calmer support after reset, but it still has only one confirmation run in the re-acquired posture.",
        f"{label} has only just re-acquired stronger calmer support after reset.",
    )


def _follow_through_reacquisition_durability_projection(
    item: dict,
    prior_matches: list[dict],
    *,
    follow_through_recovery_reacquisition_status: str,
    follow_through_relapse_churn_status: str,
    follow_through_recovery_freshness_status: str,
    follow_through_recovery_decay_status: str,
    follow_through_recovery_memory_reset_status: str,
) -> tuple[int, str, str, str]:
    label = _target_label(item)
    prior_window = list(prior_matches[: HISTORY_WINDOW_RUNS - 1])
    recent_window = [
        {
            **item,
            "follow_through_recovery_reacquisition_status": follow_through_recovery_reacquisition_status,
        },
        *prior_window,
    ]

    prior_durable_streak = 0
    for entry in recent_window[1:]:
        prior_status = str(
            entry.get("follow_through_recovery_reacquisition_status", "none") or "none"
        )
        if prior_status in {"just-reacquired", "holding-reacquired", "reacquired"}:
            prior_durable_streak += 1
            continue
        break

    had_recent_reacquisition = any(
        str(entry.get("follow_through_recovery_reacquisition_status", "none") or "none")
        in {"just-reacquired", "holding-reacquired", "reacquired", "fragile-reacquisition"}
        for entry in prior_window
    )
    weakening_signal = (
        follow_through_relapse_churn_status in {"fragile", "churn", "blocked"}
        or follow_through_recovery_freshness_status in {"mixed-age", "stale"}
        or follow_through_recovery_decay_status
        in {"softening", "aging", "fragile-aging", "expired"}
        or follow_through_recovery_memory_reset_status in {"reset-watch", "resetting", "reset"}
    )

    if follow_through_recovery_reacquisition_status == "none":
        return (
            0,
            "none",
            f"{label} does not currently have an active re-acquired calmer posture to judge for durability.",
            f"{label} is not currently holding a re-acquired calmer posture.",
        )
    if follow_through_recovery_reacquisition_status == "insufficient-evidence":
        return (
            1,
            "insufficient-evidence",
            f"{label} may be re-acquiring stronger calmer support, but there is not enough history yet to judge whether that restored posture can hold.",
            f"{label} may be re-acquiring stronger calmer support, but its durability is still unclear.",
        )
    if follow_through_recovery_reacquisition_status == "fragile-reacquisition":
        age_runs = max(1, prior_durable_streak)
        if had_recent_reacquisition or weakening_signal:
            return (
                age_runs,
                "softening",
                f"{label} had recently re-acquired stronger calmer support, but the restored posture is already softening under weaker freshness or wobble.",
                f"{label}'s restored calmer posture is already softening again.",
            )
        return (
            0,
            "none",
            f"{label} is still too fragile to count as actively re-acquired yet.",
            f"{label} has not reached an actively durable re-acquired posture yet.",
        )
    if follow_through_recovery_reacquisition_status == "reacquiring":
        if had_recent_reacquisition and weakening_signal:
            return (
                max(1, prior_durable_streak),
                "softening",
                f"{label} was closer to a restored calmer hold earlier, but the current re-acquisition path is softening before it could stabilize.",
                f"{label}'s re-acquired calmer posture is softening before it can hold.",
            )
        return (
            0,
            "none",
            f"{label} is close to re-acquiring stronger calmer support, but the restored posture is not active enough yet to judge durability.",
            f"{label} is near reacquisition, but the restored posture is not active enough to judge durability yet.",
        )

    if weakening_signal and had_recent_reacquisition:
        return (
            max(1, prior_durable_streak),
            "softening",
            f"{label} still has a re-acquired calmer posture, but mixed-age support or wobble is already softening how trustworthy that restored hold looks.",
            f"{label} still has a re-acquired calmer posture, but it is already softening again.",
        )

    if follow_through_recovery_reacquisition_status == "just-reacquired":
        return (
            1,
            "just-reacquired",
            f"{label} has only just re-entered stronger calmer support after reset, so the restored posture is still too new to treat as durable.",
            f"{label} has only just re-acquired stronger calmer support and still needs more confirmation.",
        )
    if follow_through_recovery_reacquisition_status == "holding-reacquired":
        age_runs = 1 + sum(
            1
            for entry in prior_window
            if str(entry.get("follow_through_recovery_reacquisition_status", "none") or "none")
            in {"just-reacquired", "holding-reacquired"}
        )
        return (
            age_runs,
            "consolidating",
            f"{label} has one additional confirming run after re-acquiring stronger calmer support, but the restored posture is still consolidating rather than stable.",
            f"{label} has re-acquired stronger calmer support and is now consolidating it.",
        )

    durability_streak = 1
    for entry in prior_window:
        prior_status = str(
            entry.get("follow_through_recovery_reacquisition_durability_status", "none") or "none"
        )
        if prior_status in {"holding-reacquired", "durable-reacquired"}:
            durability_streak += 1
            continue
        break
    if durability_streak >= 3:
        return (
            durability_streak,
            "durable-reacquired",
            f"{label} has kept its restored calmer posture stable for {durability_streak} consecutive durability runs, so that re-acquired support now looks durable enough to trust.",
            f"{label} now has a durably re-established calmer posture.",
        )
    return (
        durability_streak,
        "holding-reacquired",
        f"{label} has moved beyond initial re-acquisition and is now holding the restored calmer posture across {durability_streak} consecutive durability run(s), but it is not durable yet.",
        f"{label} has re-acquired stronger calmer support and it is now actively holding.",
    )


def _follow_through_reacquisition_consolidation_projection(
    item: dict,
    prior_matches: list[dict],
    *,
    follow_through_recovery_reacquisition_status: str,
    follow_through_recovery_reacquisition_durability_status: str,
    follow_through_relapse_churn_status: str,
    follow_through_recovery_freshness_status: str,
    follow_through_recovery_decay_status: str,
) -> tuple[str, str, str]:
    label = _target_label(item)
    prior_window = list(prior_matches[: HISTORY_WINDOW_RUNS - 1])
    weakening_signal = (
        follow_through_relapse_churn_status in {"fragile", "churn", "blocked"}
        or follow_through_recovery_freshness_status in {"mixed-age", "stale"}
        or follow_through_recovery_decay_status
        in {"softening", "aging", "fragile-aging", "expired"}
    )
    had_confident_reacquisition = any(
        str(
            entry.get("follow_through_recovery_reacquisition_consolidation_status", "none")
            or "none"
        )
        in {"holding-confidence", "durable-confidence"}
        or str(
            entry.get("follow_through_recovery_reacquisition_durability_status", "none") or "none"
        )
        in {"holding-reacquired", "durable-reacquired"}
        for entry in prior_window
    )

    if follow_through_recovery_reacquisition_status == "none":
        return (
            "none",
            f"{label} does not currently have an active re-acquired posture to consolidate.",
            f"{label} is not currently consolidating restored calmer confidence.",
        )
    if (
        follow_through_recovery_reacquisition_status == "insufficient-evidence"
        or follow_through_recovery_reacquisition_durability_status == "insufficient-evidence"
    ):
        return (
            "insufficient-evidence",
            f"{label} may be rebuilding restored calmer support, but the history is still too thin to judge whether that confidence is consolidating.",
            f"{label} may be rebuilding restored calmer support, but its confidence is still unclear.",
        )
    if weakening_signal and had_confident_reacquisition:
        return (
            "reversing",
            f"{label} had started to consolidate restored calmer confidence, but weaker freshness or churn is already pushing that confidence back down.",
            f"{label}'s restored calmer confidence is already reversing.",
        )
    if (
        follow_through_recovery_reacquisition_status == "fragile-reacquisition"
        or follow_through_recovery_reacquisition_durability_status == "softening"
        or weakening_signal
    ):
        return (
            "fragile-confidence",
            f"{label} technically still has a re-acquired calmer posture, but wobble or aging support makes that restored confidence too fragile to trust strongly.",
            f"{label}'s restored calmer confidence still looks fragile.",
        )
    if follow_through_recovery_reacquisition_durability_status in {
        "just-reacquired",
        "consolidating",
    }:
        return (
            "building-confidence",
            f"{label} has re-acquired stronger calmer support, but the restored confidence is still building and needs another confirming run before it should carry more weight.",
            f"{label} has re-acquired stronger calmer support, but its restored confidence is still building.",
        )
    if follow_through_recovery_reacquisition_durability_status == "holding-reacquired":
        return (
            "holding-confidence",
            f"{label} is holding its re-acquired calmer posture with net-positive support, so restored confidence is now consolidating cleanly.",
            f"{label}'s restored calmer confidence is now holding.",
        )
    if follow_through_recovery_reacquisition_durability_status == "durable-reacquired":
        if (
            follow_through_recovery_freshness_status in {"fresh", "holding-fresh"}
            and follow_through_recovery_decay_status == "none"
        ):
            return (
                "durable-confidence",
                f"{label} has kept the re-acquired calmer posture durable enough, with fresh enough support behind it, that the restored confidence now looks safely consolidated.",
                f"{label}'s restored calmer confidence now looks durable.",
            )
        return (
            "holding-confidence",
            f"{label} has a durable re-acquired posture, but the freshness behind that restored confidence is no longer strong enough to call fully durable.",
            f"{label}'s restored calmer confidence is holding, but it is not fully durable yet.",
        )
    return (
        "none",
        f"{label} has not reached a re-acquired posture that needs separate confidence-consolidation guidance yet.",
        f"{label} does not currently have separate re-acquisition confidence to consolidate.",
    )


def _follow_through_reacquisition_softening_decay_projection(
    item: dict,
    prior_matches: list[dict],
    *,
    follow_through_recovery_reacquisition_durability_status: str,
    follow_through_recovery_reacquisition_consolidation_status: str,
    follow_through_recovery_freshness_status: str,
    follow_through_recovery_decay_status: str,
    follow_through_relapse_churn_status: str,
) -> tuple[int, str, str, str]:
    label = _target_label(item)
    prior_window = list(prior_matches[: HISTORY_WINDOW_RUNS - 1])
    had_recent_strong_posture = any(
        str(entry.get("follow_through_recovery_reacquisition_durability_status", "none") or "none")
        in {"holding-reacquired", "durable-reacquired"}
        or str(
            entry.get("follow_through_recovery_reacquisition_consolidation_status", "none")
            or "none"
        )
        in {"holding-confidence", "durable-confidence"}
        for entry in prior_window
    )
    prior_softening_streak = 0
    for entry in prior_window:
        prior_status = str(
            entry.get("follow_through_reacquisition_softening_decay_status", "none") or "none"
        )
        if prior_status in {"softening-watch", "step-down", "revalidation-needed"}:
            prior_softening_streak += 1
            continue
        break

    weakening_signal = (
        follow_through_recovery_reacquisition_durability_status == "softening"
        or follow_through_recovery_reacquisition_consolidation_status
        in {"fragile-confidence", "reversing"}
        or follow_through_recovery_freshness_status in {"mixed-age", "stale"}
        or follow_through_recovery_decay_status
        in {"softening", "aging", "fragile-aging", "expired"}
        or follow_through_relapse_churn_status in {"fragile", "churn", "blocked"}
    )
    if not had_recent_strong_posture and not weakening_signal:
        return (
            0,
            "none",
            f"{label} does not currently have a once-restored calmer posture that is aging back down.",
            f"{label} is not currently carrying a softening restored posture.",
        )
    if (
        follow_through_recovery_reacquisition_durability_status == "insufficient-evidence"
        or follow_through_recovery_reacquisition_consolidation_status == "insufficient-evidence"
    ) and had_recent_strong_posture:
        return (
            1,
            "insufficient-evidence",
            f"{label} may be stepping down from a once-strong restored posture, but the recent history is still too thin to judge whether that softening is real.",
            f"{label} may be stepping down from restored calmer support, but the softening path is still unclear.",
        )
    if weakening_signal and had_recent_strong_posture:
        age_runs = prior_softening_streak + 1
        if age_runs >= 3:
            return (
                age_runs,
                "revalidation-needed",
                f"{label} has stayed weak for long enough after a once-strong restored posture that the earlier durable support now needs fresh confirmation before it should be trusted again.",
                f"{label}'s once-restored calmer posture now needs revalidation before it should be trusted again.",
            )
        if age_runs >= 2:
            return (
                age_runs,
                "step-down",
                f"{label} has spent a second confirming run in a weaker restored posture, so the earlier durable support should now be stepped down.",
                f"{label}'s once-restored calmer posture is now stepping down.",
            )
        return (
            age_runs,
            "softening-watch",
            f"{label} has started to soften after a once-strong restored posture, but it is still too early to retire that support completely.",
            f"{label}'s once-restored calmer posture is softening and should be watched.",
        )
    if (
        prior_softening_streak
        and not had_recent_strong_posture
        and follow_through_recovery_reacquisition_durability_status
        in {"none", "just-reacquired", "consolidating"}
        and follow_through_recovery_reacquisition_consolidation_status
        in {"none", "building-confidence"}
    ):
        return (
            prior_softening_streak,
            "retired-softening",
            f"{label}'s earlier softening signal has aged out enough that the old restored-hold memory is no longer active.",
            f"{label} is no longer carrying active softening memory from an earlier restored posture.",
        )
    return (
        0,
        "none",
        f"{label} does not currently have a softening restored posture that needs separate step-down guidance.",
        f"{label} is not currently softening out of a restored calmer posture.",
    )


def _follow_through_reacquisition_confidence_retirement_projection(
    item: dict,
    prior_matches: list[dict],
    *,
    follow_through_recovery_reacquisition_durability_status: str,
    follow_through_recovery_reacquisition_consolidation_status: str,
    follow_through_reacquisition_softening_decay_status: str,
    follow_through_recovery_freshness_status: str,
    follow_through_recovery_decay_status: str,
) -> tuple[str, str, str]:
    label = _target_label(item)
    prior_window = list(prior_matches[: HISTORY_WINDOW_RUNS - 1])
    had_recent_strong_confidence = any(
        str(
            entry.get("follow_through_recovery_reacquisition_consolidation_status", "none")
            or "none"
        )
        in {"holding-confidence", "durable-confidence"}
        for entry in prior_window
    )
    prior_retirement_streak = 0
    for entry in prior_window:
        prior_status = str(
            entry.get("follow_through_reacquisition_confidence_retirement_status", "none") or "none"
        )
        if prior_status in {"watch-retirement", "retiring-confidence", "revalidation-needed"}:
            prior_retirement_streak += 1
            continue
        break

    if (
        follow_through_recovery_reacquisition_consolidation_status
        in {"holding-confidence", "durable-confidence"}
        and follow_through_reacquisition_softening_decay_status == "none"
    ):
        return (
            "none",
            f"{label}'s restored confidence is still holding strongly enough that no retirement step-down is needed.",
            f"{label}'s restored calmer confidence is still active and does not need retirement.",
        )
    if (
        follow_through_recovery_reacquisition_consolidation_status == "insufficient-evidence"
        or follow_through_recovery_reacquisition_durability_status == "insufficient-evidence"
    ) and had_recent_strong_confidence:
        return (
            "insufficient-evidence",
            f"{label} may be retiring earlier restored confidence, but there is not enough recent history yet to judge whether that stronger carry-forward should really be withdrawn.",
            f"{label}'s restored calmer confidence may be retiring, but the evidence is still too thin to judge.",
        )

    weakening_confidence = (
        follow_through_recovery_reacquisition_consolidation_status
        in {"fragile-confidence", "reversing", "none"}
        or follow_through_reacquisition_softening_decay_status
        in {"softening-watch", "step-down", "revalidation-needed"}
        or follow_through_recovery_freshness_status in {"mixed-age", "stale"}
        or follow_through_recovery_decay_status
        in {"softening", "aging", "fragile-aging", "expired"}
    )
    if weakening_confidence and had_recent_strong_confidence:
        age_runs = prior_retirement_streak + 1
        if follow_through_recovery_reacquisition_consolidation_status == "none" and age_runs >= 3:
            return (
                "retired-confidence",
                f"{label}'s earlier restored-confidence posture is no longer supported by recent evidence, so that carry-forward confidence has now been retired.",
                f"{label}'s earlier restored calmer confidence has now been retired.",
            )
        if age_runs >= 2:
            if follow_through_reacquisition_softening_decay_status == "revalidation-needed":
                return (
                    "revalidation-needed",
                    f"{label}'s earlier restored-confidence posture was materially strong, but it now needs fresh confirmation before it should be trusted again.",
                    f"{label}'s earlier restored calmer confidence now needs revalidation before it should be trusted again.",
                )
            return (
                "retiring-confidence",
                f"{label}'s restored-confidence posture has stayed weak for a second confirming run, so the earlier stronger confidence is now retiring.",
                f"{label}'s earlier restored calmer confidence is now stepping down.",
            )
        return (
            "watch-retirement",
            f"{label}'s restored-confidence posture has started to weaken, but it has not yet spent long enough in that weaker state to retire immediately.",
            f"{label}'s restored calmer confidence is weakening and should be watched for retirement.",
        )

    if (
        prior_retirement_streak
        and follow_through_recovery_reacquisition_consolidation_status == "none"
        and not had_recent_strong_confidence
    ):
        return (
            "retired-confidence",
            f"{label}'s earlier restored-confidence posture has fully aged out of active carry-forward support.",
            f"{label}'s earlier restored calmer confidence has now fully retired.",
        )
    return (
        "none",
        f"{label} does not currently need separate restored-confidence retirement guidance.",
        f"{label}'s restored calmer confidence does not currently need retirement guidance.",
    )


def _follow_through_reacquisition_revalidation_recovery_projection(
    item: dict,
    prior_matches: list[dict],
    *,
    follow_through_recovery_reacquisition_status: str,
    follow_through_recovery_reacquisition_durability_status: str,
    follow_through_recovery_reacquisition_consolidation_status: str,
    follow_through_reacquisition_softening_decay_status: str,
    follow_through_reacquisition_confidence_retirement_status: str,
    follow_through_recovery_freshness_status: str,
    follow_through_recovery_decay_status: str,
) -> tuple[int, str, str, str]:
    label = _target_label(item)
    prior_window = list(prior_matches[: HISTORY_WINDOW_RUNS - 1])
    current_under_revalidation = (
        follow_through_reacquisition_softening_decay_status == "revalidation-needed"
        or follow_through_reacquisition_confidence_retirement_status == "revalidation-needed"
    )
    prior_reearned_streak = 0
    for entry in prior_window:
        prior_status = str(
            entry.get("follow_through_reacquisition_revalidation_recovery_status", "none") or "none"
        )
        if prior_status in {"just-reearned-confidence", "holding-reearned-confidence"}:
            prior_reearned_streak += 1
            continue
        break

    had_recent_revalidation = current_under_revalidation or any(
        str(entry.get("follow_through_reacquisition_softening_decay_status", "none") or "none")
        == "revalidation-needed"
        or str(
            entry.get("follow_through_reacquisition_confidence_retirement_status", "none") or "none"
        )
        == "revalidation-needed"
        or str(
            entry.get("follow_through_reacquisition_revalidation_recovery_status", "none") or "none"
        )
        in {
            "under-revalidation",
            "rebuilding-restored-confidence",
            "reearning-confidence",
            "just-reearned-confidence",
            "holding-reearned-confidence",
            "insufficient-evidence",
        }
        for entry in prior_window
    )
    if not had_recent_revalidation:
        return (
            0,
            "none",
            f"{label} does not currently have a post-revalidation recovery path to track.",
            f"{label} is not currently on a post-revalidation recovery path.",
        )
    if current_under_revalidation:
        return (
            0,
            "under-revalidation",
            f"{label} is still in the revalidation window, so stronger restored confidence should not be treated as re-earned yet.",
            f"{label} is still under revalidation before restored confidence can be re-earned.",
        )
    if (
        follow_through_recovery_reacquisition_durability_status == "insufficient-evidence"
        or follow_through_recovery_reacquisition_consolidation_status == "insufficient-evidence"
    ):
        return (
            0,
            "insufficient-evidence",
            f"{label} recently needed revalidation, but there is not enough post-revalidation history yet to judge whether restored confidence is returning cleanly.",
            f"{label} has recent revalidation history, but the post-revalidation recovery evidence is still too thin to classify.",
        )
    if follow_through_recovery_reacquisition_consolidation_status in {
        "holding-confidence",
        "durable-confidence",
    }:
        reearned_runs = prior_reearned_streak + 1
        if reearned_runs >= 2:
            return (
                reearned_runs,
                "holding-reearned-confidence",
                f"{label} has now held re-earned restored confidence for {reearned_runs} consecutive run(s) since revalidation cleared, so that stronger posture is starting to look dependable again.",
                f"{label} is now holding re-earned restored confidence after revalidation.",
            )
        return (
            1,
            "just-reearned-confidence",
            f"{label} has only just re-earned restored confidence after revalidation, so the stronger posture is back but still too new to trust fully.",
            f"{label} has only just re-earned restored confidence after revalidation.",
        )
    if (
        follow_through_recovery_reacquisition_durability_status
        in {"holding-reacquired", "durable-reacquired"}
        and follow_through_recovery_reacquisition_consolidation_status == "building-confidence"
    ):
        return (
            0,
            "reearning-confidence",
            f"{label} has rebuilt the restored posture far enough to start re-earning confidence again, but the stronger support is still only building.",
            f"{label} is actively re-earning restored confidence after revalidation.",
        )
    if (
        follow_through_recovery_reacquisition_status == "reacquiring"
        or follow_through_recovery_reacquisition_durability_status
        in {"just-reacquired", "consolidating"}
        or follow_through_recovery_reacquisition_consolidation_status
        in {"none", "fragile-confidence", "reversing"}
        or follow_through_recovery_freshness_status
        in {"fresh", "holding-fresh", "mixed-age", "stale"}
        or follow_through_recovery_decay_status
        in {"none", "softening", "aging", "fragile-aging", "expired"}
    ):
        return (
            0,
            "rebuilding-restored-confidence",
            f"{label} has cleared the formal revalidation step, but the restored posture is still rebuilding before confidence can be treated as re-earned.",
            f"{label} is rebuilding restored confidence after revalidation, but it has not started holding that confidence again yet.",
        )
    return (
        0,
        "insufficient-evidence",
        f"{label} has recent revalidation history, but the current post-revalidation signals do not line up cleanly enough to classify recovery yet.",
        f"{label} has recent revalidation history, but the post-revalidation recovery path is still too unclear to classify.",
    )


def _follow_through_item_summary(
    item: dict,
    memory: dict,
    *,
    follow_through_status: str,
    follow_through_last_touch: str,
    follow_through_next_checkpoint: str,
    follow_through_evidence_hint: str,
) -> str:
    label = _target_label(item)
    if follow_through_status == "untouched":
        return f"{label} is still surfaced with no recorded follow-up yet. {follow_through_last_touch}."
    if follow_through_status == "attempted":
        return f"{label} has recorded follow-up, but the pressure is still active. {follow_through_evidence_hint}"
    if follow_through_status == "waiting-on-evidence":
        return f"{label} has recent follow-up recorded and is now waiting for confirming evidence. {follow_through_next_checkpoint}"
    if follow_through_status == "stale-follow-through":
        return f"{label} has stayed open long enough that the follow-through now looks stale. {follow_through_last_touch}."
    if follow_through_status == "resolved":
        return f"{label} looks calmer after follow-through and is now in a lower-pressure state. {follow_through_next_checkpoint}"
    return f"{label} does not have enough follow-through evidence yet to classify cleanly."


def _target_label(item: dict) -> str:
    repo = f"{item.get('repo')}: " if item.get("repo") else ""
    return f"{repo}{item.get('title', '')}".strip(": ")


def _aging_status(appearances: int, age_days: int) -> str:
    if appearances >= 5 or age_days > 21:
        return "chronic"
    if appearances >= 3 or age_days > 7:
        return "stale"
    if appearances >= 2:
        return "watch"
    return "fresh"


def _queue_identity(item: dict) -> str:
    if item.get("item_id"):
        return item["item_id"]
    repo = item.get("repo", "")
    title = item.get("title", "")
    return f"{repo}:{title}"


def _follow_through_summary(
    repeat_urgent_count: int,
    stale_item_count: int,
    oldest_open_item_days: int,
    quiet_streak_runs: int,
    *,
    status_counts: dict[str, int] | None = None,
    checkpoint_counts: dict[str, int] | None = None,
    escalation_counts: dict[str, int] | None = None,
    recovery_counts: dict[str, int] | None = None,
    recovery_persistence_counts: dict[str, int] | None = None,
    relapse_churn_counts: dict[str, int] | None = None,
    top_unattempted_items: list[dict] | None = None,
    top_stale_follow_through_items: list[dict] | None = None,
    top_overdue_follow_through_items: list[dict] | None = None,
    top_escalation_items: list[dict] | None = None,
    top_recovering_follow_through_items: list[dict] | None = None,
    top_retiring_follow_through_items: list[dict] | None = None,
    top_relapsing_follow_through_items: list[dict] | None = None,
    top_fragile_recovery_items: list[dict] | None = None,
    top_sustained_recovery_items: list[dict] | None = None,
    top_churn_follow_through_items: list[dict] | None = None,
    recovery_freshness_counts: dict[str, int] | None = None,
    recovery_decay_counts: dict[str, int] | None = None,
    recovery_memory_reset_counts: dict[str, int] | None = None,
    recovery_rebuild_strength_counts: dict[str, int] | None = None,
    recovery_reacquisition_counts: dict[str, int] | None = None,
    recovery_reacquisition_durability_counts: dict[str, int] | None = None,
    recovery_reacquisition_consolidation_counts: dict[str, int] | None = None,
    reacquisition_softening_decay_counts: dict[str, int] | None = None,
    reacquisition_confidence_retirement_counts: dict[str, int] | None = None,
    top_fresh_recovery_items: list[dict] | None = None,
    top_stale_recovery_items: list[dict] | None = None,
    top_softening_recovery_items: list[dict] | None = None,
    top_reset_recovery_items: list[dict] | None = None,
    top_rebuilding_recovery_items: list[dict] | None = None,
    top_rebuilding_recovery_strength_items: list[dict] | None = None,
    top_reacquiring_recovery_items: list[dict] | None = None,
    top_reacquired_recovery_items: list[dict] | None = None,
    top_fragile_reacquisition_items: list[dict] | None = None,
    top_just_reacquired_items: list[dict] | None = None,
    top_holding_reacquired_items: list[dict] | None = None,
    top_durable_reacquired_items: list[dict] | None = None,
    top_softening_reacquired_items: list[dict] | None = None,
    top_fragile_reacquisition_confidence_items: list[dict] | None = None,
    top_softening_reacquisition_items: list[dict] | None = None,
    top_revalidation_needed_reacquisition_items: list[dict] | None = None,
    top_retired_reacquisition_confidence_items: list[dict] | None = None,
) -> str:
    status_counts = status_counts or {}
    checkpoint_counts = checkpoint_counts or {}
    escalation_counts = escalation_counts or {}
    recovery_counts = recovery_counts or {}
    recovery_persistence_counts = recovery_persistence_counts or {}
    relapse_churn_counts = relapse_churn_counts or {}
    top_unattempted_items = top_unattempted_items or []
    top_stale_follow_through_items = top_stale_follow_through_items or []
    top_overdue_follow_through_items = top_overdue_follow_through_items or []
    top_escalation_items = top_escalation_items or []
    top_recovering_follow_through_items = top_recovering_follow_through_items or []
    top_retiring_follow_through_items = top_retiring_follow_through_items or []
    top_relapsing_follow_through_items = top_relapsing_follow_through_items or []
    top_fragile_recovery_items = top_fragile_recovery_items or []
    top_sustained_recovery_items = top_sustained_recovery_items or []
    top_churn_follow_through_items = top_churn_follow_through_items or []
    recovery_freshness_counts = recovery_freshness_counts or {}
    recovery_decay_counts = recovery_decay_counts or {}
    recovery_memory_reset_counts = recovery_memory_reset_counts or {}
    recovery_rebuild_strength_counts = recovery_rebuild_strength_counts or {}
    recovery_reacquisition_counts = recovery_reacquisition_counts or {}
    recovery_reacquisition_durability_counts = recovery_reacquisition_durability_counts or {}
    recovery_reacquisition_consolidation_counts = recovery_reacquisition_consolidation_counts or {}
    reacquisition_softening_decay_counts = reacquisition_softening_decay_counts or {}
    reacquisition_confidence_retirement_counts = reacquisition_confidence_retirement_counts or {}
    top_fresh_recovery_items = top_fresh_recovery_items or []
    top_stale_recovery_items = top_stale_recovery_items or []
    top_softening_recovery_items = top_softening_recovery_items or []
    top_reset_recovery_items = top_reset_recovery_items or []
    top_rebuilding_recovery_items = top_rebuilding_recovery_items or []
    top_rebuilding_recovery_strength_items = top_rebuilding_recovery_strength_items or []
    top_reacquiring_recovery_items = top_reacquiring_recovery_items or []
    top_reacquired_recovery_items = top_reacquired_recovery_items or []
    top_fragile_reacquisition_items = top_fragile_reacquisition_items or []
    top_just_reacquired_items = top_just_reacquired_items or []
    top_holding_reacquired_items = top_holding_reacquired_items or []
    top_durable_reacquired_items = top_durable_reacquired_items or []
    top_softening_reacquired_items = top_softening_reacquired_items or []
    top_fragile_reacquisition_confidence_items = top_fragile_reacquisition_confidence_items or []
    top_softening_reacquisition_items = top_softening_reacquisition_items or []
    top_revalidation_needed_reacquisition_items = top_revalidation_needed_reacquisition_items or []
    top_retired_reacquisition_confidence_items = top_retired_reacquisition_confidence_items or []
    legacy_summary = ""
    if repeat_urgent_count or stale_item_count:
        legacy_summary = (
            f"{repeat_urgent_count} urgent item(s) repeated in the recent window, "
            f"{stale_item_count} open item(s) now look stale, and the oldest open item has been visible for about {oldest_open_item_days} day(s)."
        )
    if top_stale_follow_through_items:
        top_item = top_stale_follow_through_items[0]
        label = _target_label(top_item)
        detailed = (
            f"{status_counts.get('stale-follow-through', 0)} item(s) now look stalled after earlier review-to-action handoff, "
            f"and {label} is the strongest case to close or escalate next."
        )
        if checkpoint_counts.get("overdue", 0) or escalation_counts.get("escalate-now", 0):
            detailed = (
                f"{detailed} "
                f"{checkpoint_counts.get('overdue', 0)} item(s) are now overdue and "
                f"{escalation_counts.get('escalate-now', 0)} item(s) are in escalate-now."
            )
        return f"{legacy_summary} {detailed}".strip() if legacy_summary else detailed
    if top_unattempted_items:
        top_item = top_unattempted_items[0]
        label = _target_label(top_item)
        detailed = (
            f"{status_counts.get('untouched', 0)} surfaced item(s) still have no recorded follow-through, "
            f"and {label} is the clearest place to start."
        )
        if checkpoint_counts.get("overdue", 0) or escalation_counts.get("escalate-now", 0):
            detailed = (
                f"{detailed} "
                f"{checkpoint_counts.get('overdue', 0)} item(s) are overdue and "
                f"{escalation_counts.get('escalate-now', 0)} item(s) now need stronger resurfacing."
            )
        return f"{legacy_summary} {detailed}".strip() if legacy_summary else detailed
    if top_overdue_follow_through_items:
        top_item = top_overdue_follow_through_items[0]
        label = _target_label(top_item)
        return (
            f"{checkpoint_counts.get('overdue', 0)} item(s) are now overdue for visible follow-through, "
            f"and {label} is the top resurfacing hotspot."
        )
    if top_escalation_items:
        top_item = top_escalation_items[0]
        label = _target_label(top_item)
        return (
            f"{escalation_counts.get('escalate-now', 0)} item(s) now need stronger follow-through resurfacing, "
            f"and {label} is the clearest escalation target."
        )
    if top_relapsing_follow_through_items:
        top_item = top_relapsing_follow_through_items[0]
        label = _target_label(top_item)
        return (
            f"{recovery_counts.get('relapsing', 0)} item(s) looked calmer before slipping back into active follow-through pressure, "
            f"and {label} is the clearest relapse hotspot."
        )
    if top_churn_follow_through_items:
        top_item = top_churn_follow_through_items[0]
        label = _target_label(top_item)
        return (
            f"{relapse_churn_counts.get('churn', 0) + relapse_churn_counts.get('fragile', 0) + relapse_churn_counts.get('blocked', 0)} item(s) now look fragile or churn-prone after starting to recover, "
            f"and {label} is the clearest calmer-state hotspot to watch."
        )
    if top_reset_recovery_items:
        top_item = top_reset_recovery_items[0]
        label = _target_label(top_item)
        return (
            f"{recovery_memory_reset_counts.get('reset-watch', 0) + recovery_memory_reset_counts.get('resetting', 0) + recovery_memory_reset_counts.get('reset', 0)} item(s) now need their older recovery confidence stepped down, "
            f"and {label} is the clearest recovery-memory reset hotspot."
        )
    if top_softening_recovery_items:
        top_item = top_softening_recovery_items[0]
        label = _target_label(top_item)
        return (
            f"{recovery_decay_counts.get('softening', 0) + recovery_decay_counts.get('aging', 0) + recovery_decay_counts.get('fragile-aging', 0) + recovery_decay_counts.get('expired', 0)} item(s) still look calmer, but their recovery memory is softening or aging, "
            f"and {label} is the clearest place where that calmer posture is weakening."
        )
    if top_stale_recovery_items:
        top_item = top_stale_recovery_items[0]
        label = _target_label(top_item)
        return (
            f"{recovery_freshness_counts.get('stale', 0)} item(s) are still leaning on older calmer memory, "
            f"and {label} is the clearest place where that recovery support is now stale."
        )
    if top_rebuilding_recovery_items:
        top_item = top_rebuilding_recovery_items[0]
        label = _target_label(top_item)
        return (
            f"{recovery_memory_reset_counts.get('rebuilding', 0)} item(s) are rebuilding recovery confidence after an earlier reset, "
            f"and {label} is the clearest calmer path that is earning back fresher support."
        )
    if top_fragile_reacquisition_confidence_items:
        top_item = top_fragile_reacquisition_confidence_items[0]
        label = _target_label(top_item)
        return (
            f"{recovery_reacquisition_consolidation_counts.get('fragile-confidence', 0) + recovery_reacquisition_consolidation_counts.get('reversing', 0)} item(s) have technically re-acquired calmer support, "
            f"but {label} is the clearest place where that restored confidence still looks too fragile to trust."
        )
    if top_revalidation_needed_reacquisition_items:
        top_item = top_revalidation_needed_reacquisition_items[0]
        label = _target_label(top_item)
        return (
            f"{reacquisition_softening_decay_counts.get('revalidation-needed', 0) + reacquisition_confidence_retirement_counts.get('revalidation-needed', 0)} restored re-acquisition path(s) now need fresh confirmation before they should be trusted again, "
            f"and {label} is the clearest revalidation hotspot."
        )
    if top_retired_reacquisition_confidence_items:
        top_item = top_retired_reacquisition_confidence_items[0]
        label = _target_label(top_item)
        return (
            f"{reacquisition_confidence_retirement_counts.get('retired-confidence', 0)} restored-confidence path(s) have now aged out of active carry-forward support, "
            f"and {label} is the clearest place where earlier restored confidence has been retired."
        )
    if top_softening_reacquisition_items:
        top_item = top_softening_reacquisition_items[0]
        label = _target_label(top_item)
        return (
            f"{reacquisition_softening_decay_counts.get('softening-watch', 0) + reacquisition_softening_decay_counts.get('step-down', 0) + reacquisition_softening_decay_counts.get('revalidation-needed', 0)} once-restored re-acquisition path(s) are now softening enough to warrant closer revalidation, "
            f"and {label} is the clearest restored posture that is stepping back down."
        )
    if top_softening_reacquired_items:
        top_item = top_softening_reacquired_items[0]
        label = _target_label(top_item)
        return (
            f"{recovery_reacquisition_durability_counts.get('softening', 0)} re-acquired item(s) are already softening again, "
            f"and {label} is the clearest restored posture that may step back down soon."
        )
    if top_durable_reacquired_items:
        top_item = top_durable_reacquired_items[0]
        label = _target_label(top_item)
        return (
            f"{recovery_reacquisition_durability_counts.get('durable-reacquired', 0)} item(s) now have a re-acquired calmer posture that is holding durably, "
            f"and {label} is the clearest restored path you can trust more strongly."
        )
    if top_holding_reacquired_items:
        top_item = top_holding_reacquired_items[0]
        label = _target_label(top_item)
        return (
            f"{recovery_reacquisition_durability_counts.get('consolidating', 0) + recovery_reacquisition_durability_counts.get('holding-reacquired', 0)} re-acquired item(s) are actively consolidating, "
            f"and {label} is the clearest restored path that is now holding."
        )
    if top_just_reacquired_items:
        top_item = top_just_reacquired_items[0]
        label = _target_label(top_item)
        return (
            f"{recovery_reacquisition_durability_counts.get('just-reacquired', 0)} item(s) have only just re-acquired stronger calmer support, "
            f"and {label} is the clearest newly restored path that still needs more proof."
        )
    if top_fragile_reacquisition_items:
        top_item = top_fragile_reacquisition_items[0]
        label = _target_label(top_item)
        return (
            f"{recovery_reacquisition_counts.get('fragile-reacquisition', 0)} item(s) are trying to re-earn stronger calmer support after reset, "
            f"but {label} is the clearest place where that rebuilt posture still looks too fragile to trust."
        )
    if top_reacquired_recovery_items:
        top_item = top_reacquired_recovery_items[0]
        label = _target_label(top_item)
        return (
            f"{recovery_reacquisition_counts.get('just-reacquired', 0) + recovery_reacquisition_counts.get('holding-reacquired', 0) + recovery_reacquisition_counts.get('reacquired', 0)} item(s) have re-earned stronger calmer support after reset, "
            f"and {label} is the clearest re-acquired recovery path."
        )
    if top_reacquiring_recovery_items:
        top_item = top_reacquiring_recovery_items[0]
        label = _target_label(top_item)
        return (
            f"{recovery_reacquisition_counts.get('reacquiring', 0)} item(s) are close to re-earning stronger calmer support after reset, "
            f"and {label} is the clearest near-reacquisition path."
        )
    if top_rebuilding_recovery_strength_items:
        top_item = top_rebuilding_recovery_strength_items[0]
        label = _target_label(top_item)
        return (
            f"{recovery_rebuild_strength_counts.get('just-rebuilding', 0) + recovery_rebuild_strength_counts.get('building', 0) + recovery_rebuild_strength_counts.get('holding-rebuild', 0)} item(s) are rebuilding calmer support after reset, "
            f"and {label} is the clearest rebuild-strength hotspot."
        )
    if top_fresh_recovery_items:
        top_item = top_fresh_recovery_items[0]
        label = _target_label(top_item)
        return (
            f"{recovery_freshness_counts.get('fresh', 0) + recovery_freshness_counts.get('holding-fresh', 0)} item(s) still have fresh recovery support behind the calmer posture, "
            f"and {label} is the clearest fresh recovery handoff."
        )
    if top_fragile_recovery_items:
        top_item = top_fragile_recovery_items[0]
        label = _target_label(top_item)
        return (
            f"{recovery_persistence_counts.get('fragile-recovery', 0)} item(s) are recovering but still fragile, "
            f"and {label} is the clearest place where the calmer path needs another confirming run."
        )
    if top_retiring_follow_through_items:
        top_item = top_retiring_follow_through_items[0]
        label = _target_label(top_item)
        return (
            f"{recovery_counts.get('retiring-watch', 0)} item(s) now look calmer after recent escalation, "
            f"and {label} is closest to retiring its stronger resurfacing if the next quiet run holds."
        )
    if top_sustained_recovery_items:
        top_item = top_sustained_recovery_items[0]
        label = _target_label(top_item)
        return (
            f"{recovery_persistence_counts.get('holding-recovery', 0) + recovery_persistence_counts.get('holding-retiring-watch', 0) + recovery_persistence_counts.get('sustained-retiring-watch', 0) + recovery_persistence_counts.get('sustained-retired', 0)} item(s) are now holding a calmer recovery path, "
            f"and {label} is the clearest sustained recovery handoff."
        )
    if top_recovering_follow_through_items:
        top_item = top_recovering_follow_through_items[0]
        label = _target_label(top_item)
        return (
            f"{recovery_counts.get('recovering', 0)} item(s) are actively calming down after recent escalation, "
            f"and {label} is the clearest recovery path to watch."
        )
    if status_counts.get("waiting-on-evidence", 0):
        return f"{status_counts.get('waiting-on-evidence', 0)} item(s) have recent follow-up recorded and are now waiting for later evidence to confirm movement."
    if status_counts.get("attempted", 0):
        return f"{status_counts.get('attempted', 0)} item(s) show recorded follow-up, but the underlying pressure is still visible in the current queue."
    if status_counts.get("resolved", 0):
        return f"{status_counts.get('resolved', 0)} item(s) now look calmer or resolved after recent follow-through, but they still need one more confirming read before they fully disappear from memory."
    if legacy_summary:
        return legacy_summary
    if quiet_streak_runs >= 2:
        return f"The operator queue has stayed quiet for {quiet_streak_runs} consecutive run(s)."
    if quiet_streak_runs == 1:
        return "The latest run is quiet, but the recent window has not stayed quiet long enough to count as a streak yet."
    return "This is the first noisy run in the recent window, so follow-through pressure is still fresh."


def _follow_through_checkpoint_summary(
    status_counts: dict[str, int],
    top_unattempted_items: list[dict],
    top_stale_follow_through_items: list[dict],
) -> str:
    if top_stale_follow_through_items:
        top_item = top_stale_follow_through_items[0]
        label = _target_label(top_item)
        return f"Start with {label}. Progress should look like a concrete follow-up plus a quieter next run or a lower-pressure lane."
    if top_unattempted_items:
        top_item = top_unattempted_items[0]
        label = _target_label(top_item)
        return f"Start with {label}. Progress should look like a recorded intervention or a linked artifact update before the next review."
    if status_counts.get("waiting-on-evidence", 0):
        return "Recent follow-up is in flight, so the next checkpoint is whether the next run confirms quieter pressure."
    if status_counts.get("attempted", 0):
        return "Follow-up is recorded, but the next checkpoint is whether the pressure actually drops on the next run."
    if status_counts.get("resolved", 0):
        return "Some items already look calmer, so the next checkpoint is whether that calmer state holds for another run."
    return "Use the next run or linked artifact to confirm whether the current recommendation actually moved."


def _follow_through_escalation_summary(
    checkpoint_counts: dict[str, int],
    escalation_counts: dict[str, int],
    top_overdue_follow_through_items: list[dict],
    top_escalation_items: list[dict],
) -> str:
    if top_overdue_follow_through_items:
        top_item = top_overdue_follow_through_items[0]
        label = _target_label(top_item)
        return f"{checkpoint_counts.get('overdue', 0)} item(s) are now overdue for follow-through, and {label} should be resurfaced first."
    if top_escalation_items:
        top_item = top_escalation_items[0]
        label = _target_label(top_item)
        return f"{escalation_counts.get('escalate-now', 0)} item(s) are in escalate-now and {label} is the clearest next escalation target."
    if escalation_counts.get("nudge", 0):
        return f"{escalation_counts.get('nudge', 0)} item(s) are no longer fresh enough to just watch and should be nudged again soon."
    if escalation_counts.get("watch", 0):
        return f"{escalation_counts.get('watch', 0)} item(s) are still within their early checkpoint window and should stay visible on watch."
    if escalation_counts.get("resolved-watch", 0):
        return f"{escalation_counts.get('resolved-watch', 0)} item(s) look calmer but still need one more quiet run before they can fully fade from follow-through watch."
    return "No stronger follow-through escalation is currently surfaced."


def _follow_through_recovery_summary(
    recovery_counts: dict[str, int],
    recovery_persistence_counts: dict[str, int],
    top_recovering_follow_through_items: list[dict],
    top_retiring_follow_through_items: list[dict],
    top_relapsing_follow_through_items: list[dict],
    top_fragile_recovery_items: list[dict],
    top_sustained_recovery_items: list[dict],
) -> str:
    if top_relapsing_follow_through_items:
        top_item = top_relapsing_follow_through_items[0]
        label = _target_label(top_item)
        return f"{recovery_counts.get('relapsing', 0)} item(s) relapsed after seeming calmer, and {label} is the clearest place where escalation retirement failed to hold."
    if top_fragile_recovery_items:
        top_item = top_fragile_recovery_items[0]
        label = _target_label(top_item)
        return f"{recovery_persistence_counts.get('fragile-recovery', 0)} item(s) are recovering but still fragile, and {label} is the clearest calmer path that still needs more proof before it can be trusted."
    if top_retiring_follow_through_items:
        top_item = top_retiring_follow_through_items[0]
        label = _target_label(top_item)
        return f"{recovery_counts.get('retiring-watch', 0)} item(s) are on retirement watch after recent escalation, and {label} is closest to fully retiring if one more quiet run holds."
    if top_sustained_recovery_items:
        top_item = top_sustained_recovery_items[0]
        label = _target_label(top_item)
        return f"{recovery_persistence_counts.get('holding-recovery', 0) + recovery_persistence_counts.get('holding-retiring-watch', 0) + recovery_persistence_counts.get('sustained-retiring-watch', 0) + recovery_persistence_counts.get('sustained-retired', 0)} item(s) now look like their calmer recovery state is holding, and {label} is the clearest sustained recovery path."
    if top_recovering_follow_through_items:
        top_item = top_recovering_follow_through_items[0]
        label = _target_label(top_item)
        return f"{recovery_counts.get('recovering', 0)} item(s) are actively recovering from recent escalation, and {label} is the clearest calmer-but-still-open handoff."
    if recovery_counts.get("retired", 0):
        return f"{recovery_counts.get('retired', 0)} item(s) have now held a calm enough state to retire their stronger follow-through escalation."
    if recovery_counts.get("insufficient-evidence", 0):
        return f"{recovery_counts.get('insufficient-evidence', 0)} item(s) may be calming down, but the recent history is too thin to retire escalation with confidence yet."
    return "No follow-through recovery or escalation-retirement signal is currently surfaced."


def _follow_through_recovery_persistence_summary(
    recovery_persistence_counts: dict[str, int],
    top_fragile_recovery_items: list[dict],
    top_sustained_recovery_items: list[dict],
) -> str:
    if top_fragile_recovery_items:
        top_item = top_fragile_recovery_items[0]
        label = _target_label(top_item)
        return f"{recovery_persistence_counts.get('fragile-recovery', 0)} item(s) have started calming down but still look fragile, and {label} is the clearest recovery path that still needs another confirming run."
    if top_sustained_recovery_items:
        top_item = top_sustained_recovery_items[0]
        label = _target_label(top_item)
        return f"{recovery_persistence_counts.get('holding-recovery', 0) + recovery_persistence_counts.get('holding-retiring-watch', 0) + recovery_persistence_counts.get('sustained-retiring-watch', 0) + recovery_persistence_counts.get('sustained-retired', 0)} item(s) now have a calmer follow-through path that is actively holding, and {label} is the clearest sustained example."
    if recovery_persistence_counts.get("just-recovering", 0):
        return f"{recovery_persistence_counts.get('just-recovering', 0)} item(s) have only just started calming down and still need another quiet run before the recovery looks proven."
    if recovery_persistence_counts.get("insufficient-evidence", 0):
        return f"{recovery_persistence_counts.get('insufficient-evidence', 0)} item(s) may be calming down, but the recent history is too thin to judge whether that calmer state is holding."
    return "No follow-through recovery persistence signal is currently surfaced."


def _follow_through_relapse_churn_summary(
    relapse_churn_counts: dict[str, int],
    top_churn_follow_through_items: list[dict],
) -> str:
    if top_churn_follow_through_items:
        top_item = top_churn_follow_through_items[0]
        label = _target_label(top_item)
        return f"{relapse_churn_counts.get('churn', 0) + relapse_churn_counts.get('fragile', 0) + relapse_churn_counts.get('blocked', 0)} item(s) now look noisy after starting to recover, and {label} is the clearest relapse-churn hotspot."
    if relapse_churn_counts.get("watch", 0):
        return f"{relapse_churn_counts.get('watch', 0)} item(s) had a mild wobble after recovery began and should stay visible until another calmer run confirms the recovery is holding."
    if relapse_churn_counts.get("insufficient-evidence", 0):
        return f"{relapse_churn_counts.get('insufficient-evidence', 0)} item(s) do not yet have enough recovery-side history to judge whether the calmer path is wobbling."
    return "No relapse churn is currently surfaced."


def _follow_through_recovery_freshness_summary(
    recovery_freshness_counts: dict[str, int],
    top_fresh_recovery_items: list[dict],
    top_stale_recovery_items: list[dict],
    top_softening_recovery_items: list[dict],
) -> str:
    if top_softening_recovery_items:
        top_item = top_softening_recovery_items[0]
        label = _target_label(top_item)
        return f"{recovery_freshness_counts.get('mixed-age', 0) + recovery_freshness_counts.get('stale', 0)} item(s) still have some calmer carry-forward, but that recovery memory is now softening or aging, and {label} is the clearest mixed-age hotspot."
    if top_stale_recovery_items:
        top_item = top_stale_recovery_items[0]
        label = _target_label(top_item)
        return f"{recovery_freshness_counts.get('stale', 0)} item(s) are now leaning mostly on older recovery memory, and {label} is the clearest place where that calmer support has gone stale."
    if top_fresh_recovery_items:
        top_item = top_fresh_recovery_items[0]
        label = _target_label(top_item)
        return f"{recovery_freshness_counts.get('fresh', 0) + recovery_freshness_counts.get('holding-fresh', 0)} item(s) still have fresh calmer support behind them, and {label} is the clearest fresh recovery handoff."
    if recovery_freshness_counts.get("insufficient-evidence", 0):
        return f"{recovery_freshness_counts.get('insufficient-evidence', 0)} item(s) may be calming down, but there is not enough history yet to judge whether that recovery memory is fresh or aging out."
    return "No follow-through recovery freshness signal is currently surfaced."


def _follow_through_recovery_decay_summary(
    recovery_decay_counts: dict[str, int],
    top_softening_recovery_items: list[dict],
    top_stale_recovery_items: list[dict],
) -> str:
    if top_softening_recovery_items:
        top_item = top_softening_recovery_items[0]
        label = _target_label(top_item)
        return f"{recovery_decay_counts.get('softening', 0) + recovery_decay_counts.get('aging', 0) + recovery_decay_counts.get('fragile-aging', 0) + recovery_decay_counts.get('expired', 0)} item(s) still look calmer, but their recovery memory is weakening, and {label} is the clearest softening hotspot."
    if top_stale_recovery_items:
        top_item = top_stale_recovery_items[0]
        label = _target_label(top_item)
        return f"{recovery_decay_counts.get('aging', 0) + recovery_decay_counts.get('expired', 0)} item(s) are now relying mainly on older calmer carry-forward, and {label} is the clearest place where that recovery support is aging out."
    if recovery_decay_counts.get("insufficient-evidence", 0):
        return f"{recovery_decay_counts.get('insufficient-evidence', 0)} item(s) do not yet have enough recovery history to judge whether the calmer memory is decaying."
    return "No follow-through recovery freshness-decay signal is currently surfaced."


def _follow_through_recovery_memory_reset_summary(
    recovery_memory_reset_counts: dict[str, int],
    top_reset_recovery_items: list[dict],
    top_rebuilding_recovery_items: list[dict],
) -> str:
    if top_reset_recovery_items:
        top_item = top_reset_recovery_items[0]
        label = _target_label(top_item)
        return f"{recovery_memory_reset_counts.get('reset-watch', 0) + recovery_memory_reset_counts.get('resetting', 0) + recovery_memory_reset_counts.get('reset', 0)} item(s) now need older recovery confidence stepped down, and {label} is the clearest reset hotspot."
    if top_rebuilding_recovery_items:
        top_item = top_rebuilding_recovery_items[0]
        label = _target_label(top_item)
        return f"{recovery_memory_reset_counts.get('rebuilding', 0)} item(s) are rebuilding calmer support after an earlier reset, and {label} is the clearest recovery-memory rebuild."
    if recovery_memory_reset_counts.get("insufficient-evidence", 0):
        return f"{recovery_memory_reset_counts.get('insufficient-evidence', 0)} item(s) may be calming down, but there is not enough history yet to judge whether older recovery confidence should reset or rebuild."
    return "No follow-through recovery memory reset signal is currently surfaced."


def _follow_through_recovery_rebuild_strength_summary(
    recovery_rebuild_strength_counts: dict[str, int],
    top_rebuilding_recovery_strength_items: list[dict],
    top_fragile_reacquisition_items: list[dict],
) -> str:
    if top_fragile_reacquisition_items:
        top_item = top_fragile_reacquisition_items[0]
        label = _target_label(top_item)
        return f"{recovery_rebuild_strength_counts.get('fragile-rebuild', 0)} item(s) are rebuilding after reset, but {label} is the clearest place where that calmer path still looks fragile."
    if top_rebuilding_recovery_strength_items:
        top_item = top_rebuilding_recovery_strength_items[0]
        label = _target_label(top_item)
        return f"{recovery_rebuild_strength_counts.get('just-rebuilding', 0) + recovery_rebuild_strength_counts.get('building', 0) + recovery_rebuild_strength_counts.get('holding-rebuild', 0)} item(s) are actively rebuilding calmer support after reset, and {label} is the clearest rebuild-strength hotspot."
    if recovery_rebuild_strength_counts.get("insufficient-evidence", 0):
        return f"{recovery_rebuild_strength_counts.get('insufficient-evidence', 0)} item(s) may be rebuilding after reset, but there is not enough history yet to judge how strong that rebuild really is."
    return "No follow-through recovery rebuild-strength signal is currently surfaced."


def _follow_through_recovery_reacquisition_summary(
    recovery_reacquisition_counts: dict[str, int],
    top_reacquiring_recovery_items: list[dict],
    top_reacquired_recovery_items: list[dict],
    top_fragile_reacquisition_items: list[dict],
) -> str:
    if top_fragile_reacquisition_items:
        top_item = top_fragile_reacquisition_items[0]
        label = _target_label(top_item)
        return f"{recovery_reacquisition_counts.get('fragile-reacquisition', 0)} item(s) are close to re-earning stronger calmer support after reset, but {label} is the clearest place where that re-acquisition still looks fragile."
    if top_reacquired_recovery_items:
        top_item = top_reacquired_recovery_items[0]
        label = _target_label(top_item)
        return f"{recovery_reacquisition_counts.get('just-reacquired', 0) + recovery_reacquisition_counts.get('holding-reacquired', 0) + recovery_reacquisition_counts.get('reacquired', 0)} item(s) have re-earned stronger calmer support after reset, and {label} is the clearest re-acquired path."
    if top_reacquiring_recovery_items:
        top_item = top_reacquiring_recovery_items[0]
        label = _target_label(top_item)
        return f"{recovery_reacquisition_counts.get('reacquiring', 0)} item(s) are close to re-earning stronger calmer support after reset, and {label} is the clearest near-reacquisition path."
    if recovery_reacquisition_counts.get("insufficient-evidence", 0):
        return f"{recovery_reacquisition_counts.get('insufficient-evidence', 0)} item(s) may be rebuilding after reset, but there is not enough history yet to judge whether stronger calmer support has really been re-acquired."
    return "No follow-through recovery reacquisition signal is currently surfaced."


def _follow_through_reacquisition_durability_summary(
    recovery_reacquisition_durability_counts: dict[str, int],
    top_just_reacquired_items: list[dict],
    top_holding_reacquired_items: list[dict],
    top_durable_reacquired_items: list[dict],
    top_softening_reacquired_items: list[dict],
) -> str:
    if top_softening_reacquired_items:
        top_item = top_softening_reacquired_items[0]
        label = _target_label(top_item)
        return f"{recovery_reacquisition_durability_counts.get('softening', 0)} re-acquired item(s) are already weakening again, and {label} is the clearest restored calmer posture that is softening before it can be trusted as stable."
    if top_durable_reacquired_items:
        top_item = top_durable_reacquired_items[0]
        label = _target_label(top_item)
        return f"{recovery_reacquisition_durability_counts.get('durable-reacquired', 0)} item(s) now have a durably re-established calmer posture, and {label} is the clearest durable example."
    if top_holding_reacquired_items:
        top_item = top_holding_reacquired_items[0]
        label = _target_label(top_item)
        return f"{recovery_reacquisition_durability_counts.get('consolidating', 0) + recovery_reacquisition_durability_counts.get('holding-reacquired', 0)} item(s) are now consolidating or holding their restored calmer posture, and {label} is the clearest active durability path."
    if top_just_reacquired_items:
        top_item = top_just_reacquired_items[0]
        label = _target_label(top_item)
        return f"{recovery_reacquisition_durability_counts.get('just-reacquired', 0)} item(s) only just re-acquired stronger calmer support, and {label} is the clearest restored posture that is still too new to trust."
    if recovery_reacquisition_durability_counts.get("insufficient-evidence", 0):
        return f"{recovery_reacquisition_durability_counts.get('insufficient-evidence', 0)} item(s) may be re-acquiring stronger calmer support, but there is not enough history yet to judge durability."
    return "No follow-through reacquisition durability signal is currently surfaced."


def _follow_through_reacquisition_consolidation_summary(
    recovery_reacquisition_consolidation_counts: dict[str, int],
    top_holding_reacquired_items: list[dict],
    top_durable_reacquired_items: list[dict],
    top_softening_reacquired_items: list[dict],
    top_fragile_reacquisition_confidence_items: list[dict],
) -> str:
    if top_fragile_reacquisition_confidence_items:
        top_item = top_fragile_reacquisition_confidence_items[0]
        label = _target_label(top_item)
        return f"{recovery_reacquisition_consolidation_counts.get('fragile-confidence', 0) + recovery_reacquisition_consolidation_counts.get('reversing', 0)} item(s) have restored calmer confidence that still looks fragile or is already reversing, and {label} is the clearest weak-consolidation hotspot."
    if top_durable_reacquired_items:
        top_item = top_durable_reacquired_items[0]
        label = _target_label(top_item)
        return f"{recovery_reacquisition_consolidation_counts.get('durable-confidence', 0)} item(s) now have restored calmer confidence that looks durably consolidated, and {label} is the clearest high-trust restored path."
    if top_holding_reacquired_items:
        top_item = top_holding_reacquired_items[0]
        label = _target_label(top_item)
        return f"{recovery_reacquisition_consolidation_counts.get('building-confidence', 0) + recovery_reacquisition_consolidation_counts.get('holding-confidence', 0)} item(s) are actively consolidating restored calmer confidence, and {label} is the clearest path that is now holding."
    if top_softening_reacquired_items:
        top_item = top_softening_reacquired_items[0]
        label = _target_label(top_item)
        return f"{recovery_reacquisition_consolidation_counts.get('reversing', 0)} item(s) had started to consolidate restored calmer confidence, but {label} is the clearest path already stepping back down."
    if recovery_reacquisition_consolidation_counts.get("insufficient-evidence", 0):
        return f"{recovery_reacquisition_consolidation_counts.get('insufficient-evidence', 0)} item(s) may have restored calmer confidence building, but the recent evidence is still too thin to judge consolidation."
    return "No follow-through reacquisition confidence-consolidation signal is currently surfaced."


def _follow_through_reacquisition_softening_decay_summary(
    reacquisition_softening_decay_counts: dict[str, int],
    top_softening_reacquisition_items: list[dict],
    top_revalidation_needed_reacquisition_items: list[dict],
) -> str:
    if top_revalidation_needed_reacquisition_items:
        top_item = top_revalidation_needed_reacquisition_items[0]
        label = _target_label(top_item)
        return f"{reacquisition_softening_decay_counts.get('revalidation-needed', 0)} restored re-acquisition path(s) now need fresh confirmation before they should be trusted again, and {label} is the clearest revalidation hotspot."
    if top_softening_reacquisition_items:
        top_item = top_softening_reacquisition_items[0]
        label = _target_label(top_item)
        return f"{reacquisition_softening_decay_counts.get('softening-watch', 0) + reacquisition_softening_decay_counts.get('step-down', 0)} restored re-acquisition path(s) are now stepping down from an earlier stronger posture, and {label} is the clearest softening hotspot."
    if reacquisition_softening_decay_counts.get("retired-softening", 0):
        return f"{reacquisition_softening_decay_counts.get('retired-softening', 0)} earlier softening path(s) have fully aged out and no longer carry active restored-hold memory."
    if reacquisition_softening_decay_counts.get("insufficient-evidence", 0):
        return f"{reacquisition_softening_decay_counts.get('insufficient-evidence', 0)} restored re-acquisition path(s) may be stepping down, but the recent history is still too thin to judge that softening cleanly."
    return "No reacquisition softening-decay signal is currently surfaced."


def _follow_through_reacquisition_confidence_retirement_summary(
    reacquisition_confidence_retirement_counts: dict[str, int],
    top_revalidation_needed_reacquisition_items: list[dict],
    top_retired_reacquisition_confidence_items: list[dict],
) -> str:
    if top_revalidation_needed_reacquisition_items:
        top_item = top_revalidation_needed_reacquisition_items[0]
        label = _target_label(top_item)
        return f"{reacquisition_confidence_retirement_counts.get('revalidation-needed', 0)} restored-confidence path(s) now need fresh confirmation before they should be trusted again, and {label} is the clearest confidence-retirement hotspot."
    if top_retired_reacquisition_confidence_items:
        top_item = top_retired_reacquisition_confidence_items[0]
        label = _target_label(top_item)
        return f"{reacquisition_confidence_retirement_counts.get('retired-confidence', 0)} restored-confidence path(s) have now been retired out of active carry-forward support, and {label} is the clearest retired-confidence example."
    if reacquisition_confidence_retirement_counts.get(
        "watch-retirement", 0
    ) or reacquisition_confidence_retirement_counts.get("retiring-confidence", 0):
        return f"{reacquisition_confidence_retirement_counts.get('watch-retirement', 0) + reacquisition_confidence_retirement_counts.get('retiring-confidence', 0)} restored-confidence path(s) are now weakening enough that the earlier stronger posture is starting to retire."
    if reacquisition_confidence_retirement_counts.get("insufficient-evidence", 0):
        return f"{reacquisition_confidence_retirement_counts.get('insufficient-evidence', 0)} restored-confidence path(s) may be retiring, but the recent evidence is still too thin to judge that step-down confidently."
    return "No reacquisition confidence-retirement signal is currently surfaced."


def _follow_through_reacquisition_revalidation_recovery_summary(
    reacquisition_revalidation_recovery_counts: dict[str, int],
    top_under_revalidation_recovery_items: list[dict],
    top_rebuilding_restored_confidence_items: list[dict],
    top_reearning_confidence_items: list[dict],
    top_just_reearned_confidence_items: list[dict],
    top_holding_reearned_confidence_items: list[dict],
) -> str:
    if top_under_revalidation_recovery_items:
        top_item = top_under_revalidation_recovery_items[0]
        label = _target_label(top_item)
        return f"{reacquisition_revalidation_recovery_counts.get('under-revalidation', 0)} restored-confidence path(s) are still under revalidation, and {label} is the clearest place where stronger confidence has not reopened yet."
    if top_rebuilding_restored_confidence_items:
        top_item = top_rebuilding_restored_confidence_items[0]
        label = _target_label(top_item)
        return f"{reacquisition_revalidation_recovery_counts.get('rebuilding-restored-confidence', 0)} restored-confidence path(s) have cleared formal revalidation but are still rebuilding, and {label} is the clearest rebuild-after-revalidation hotspot."
    if top_reearning_confidence_items:
        top_item = top_reearning_confidence_items[0]
        label = _target_label(top_item)
        return f"{reacquisition_revalidation_recovery_counts.get('reearning-confidence', 0)} restored-confidence path(s) are actively being re-earned, and {label} is the clearest place where stronger confidence is returning."
    if top_just_reearned_confidence_items:
        top_item = top_just_reearned_confidence_items[0]
        label = _target_label(top_item)
        return f"{reacquisition_revalidation_recovery_counts.get('just-reearned-confidence', 0)} restored-confidence path(s) have only just been re-earned, and {label} is the clearest still-fragile re-earned path."
    if top_holding_reearned_confidence_items:
        top_item = top_holding_reearned_confidence_items[0]
        label = _target_label(top_item)
        return f"{reacquisition_revalidation_recovery_counts.get('holding-reearned-confidence', 0)} restored-confidence path(s) are now holding re-earned confidence, and {label} is the clearest post-revalidation path that is starting to look dependable again."
    if reacquisition_revalidation_recovery_counts.get("insufficient-evidence", 0):
        return f"{reacquisition_revalidation_recovery_counts.get('insufficient-evidence', 0)} path(s) have recent revalidation history, but there is still not enough post-revalidation evidence to judge whether confidence is really returning."
    return "No post-revalidation recovery or confidence re-earning signal is currently surfaced."
