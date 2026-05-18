"""Helpers for detailed review-queue workbook rows."""

from __future__ import annotations

from typing import Any

from src.report_enrichment import (
    build_follow_through_checkpoint_status_label,
    build_follow_through_escalation_status_label,
    build_follow_through_escalation_summary,
    build_follow_through_reacquisition_consolidation_status_label,
    build_follow_through_reacquisition_consolidation_summary,
    build_follow_through_reacquisition_durability_status_label,
    build_follow_through_reacquisition_durability_summary,
    build_follow_through_recovery_freshness_status_label,
    build_follow_through_recovery_freshness_summary,
    build_follow_through_recovery_memory_reset_status_label,
    build_follow_through_recovery_memory_reset_summary,
    build_follow_through_recovery_persistence_status_label,
    build_follow_through_recovery_persistence_summary,
    build_follow_through_recovery_reacquisition_status_label,
    build_follow_through_recovery_reacquisition_summary,
    build_follow_through_recovery_rebuild_strength_status_label,
    build_follow_through_recovery_rebuild_strength_summary,
    build_follow_through_recovery_status_label,
    build_follow_through_recovery_summary,
    build_follow_through_relapse_churn_status_label,
    build_follow_through_relapse_churn_summary,
    build_last_movement_label,
    build_operator_focus,
    build_operator_focus_line,
    build_operator_focus_summary,
    no_linked_artifact_summary,
)

REVIEW_QUEUE_HEADERS = [
    "Repo",
    "Title",
    "Lane",
    "Kind",
    "Priority",
    "Why This Is Here",
    "What To Do Next",
    "Catalog",
    "Operating Path",
    "Intent Alignment",
    "Maturity",
    "Scorecard Gap",
    "Last Movement",
    "Follow-Through",
    "Next Checkpoint",
    "Checkpoint Timing",
    "Escalation",
    "Escalation Summary",
    "Recovery / Retirement",
    "Recovery Summary",
    "Recovery Persistence",
    "Persistence Summary",
    "Relapse Churn",
    "Churn Summary",
    "Recovery Freshness",
    "Freshness Summary",
    "Recovery Memory Reset",
    "Reset Summary",
    "Recovery Rebuild Strength",
    "Rebuild Summary",
    "Recovery Reacquisition",
    "Reacquisition Summary",
    "Reacquisition Durability",
    "Durability Summary",
    "Reacquisition Confidence",
    "Confidence Summary",
    "Operator Focus",
    "Focus Summary",
    "Focus Line",
    "Open Artifact",
    "Safe To Defer",
]

REVIEW_QUEUE_CENTER_ALIGNED_COLUMNS = {
    3,
    4,
    5,
    11,
    16,
    17,
    19,
    21,
    23,
    25,
    27,
    29,
    31,
    33,
    35,
    37,
    41,
}

REVIEW_QUEUE_GUIDANCE = (
    "Read this table top-down: urgent items first, ready items second, and safe-to-defer rows last."
)


def build_review_queue_table_rows(
    targets: list[dict[str, Any]], review_summary: dict[str, Any]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in targets:
        next_step = (
            item.get("recommended_action")
            or item.get("next_step")
            or "Open Repo Detail and choose the next concrete follow-through step."
        )
        safe_to_defer = item.get("lane") == "deferred" or item.get("safe_to_defer")
        links = item.get("links") or []
        primary_link = links[0].get("url", "") if links else ""
        last_movement = build_last_movement_label(item, review_summary)
        why_this_is_here = (
            item.get("lane_reason", "")
            or item.get("summary", "")
            or item.get("decision_hint", "")
            or "This item is still open and needs operator follow-through."
        )
        values = [
            item.get("repo", item.get("repo_name", "")),
            item.get("title", ""),
            item.get("lane", ""),
            item.get("kind", "review"),
            item.get("priority", item.get("severity", 0.0)),
            why_this_is_here,
            next_step,
            item.get("catalog_line", "No portfolio catalog contract is recorded yet."),
            item.get(
                "operating_path_line",
                "Operating Path: Unspecified (legacy confidence) — No operating-path rationale is recorded yet.",
            ),
            (
                f"{item.get('intent_alignment', 'missing-contract')} — "
                f"{item.get('intent_alignment_reason', 'Intent alignment cannot be judged until a portfolio catalog contract exists.')}"
            ),
            item.get("scorecard", {}).get("maturity_level", "") or "—",
            item.get("maturity_gap_summary", "No maturity gap summary is recorded yet."),
            last_movement,
            item.get("follow_through_summary", "No follow-through evidence is recorded yet."),
            item.get(
                "follow_through_next_checkpoint",
                "Use the next run or linked artifact to confirm whether the recommendation moved.",
            ),
            build_follow_through_checkpoint_status_label(item),
            build_follow_through_escalation_status_label(item),
            build_follow_through_escalation_summary(item),
            build_follow_through_recovery_status_label(item),
            build_follow_through_recovery_summary(item),
            build_follow_through_recovery_persistence_status_label(item),
            build_follow_through_recovery_persistence_summary(item),
            build_follow_through_relapse_churn_status_label(item),
            build_follow_through_relapse_churn_summary(item),
            build_follow_through_recovery_freshness_status_label(item),
            build_follow_through_recovery_freshness_summary(item),
            build_follow_through_recovery_memory_reset_status_label(item),
            build_follow_through_recovery_memory_reset_summary(item),
            build_follow_through_recovery_rebuild_strength_status_label(item),
            build_follow_through_recovery_rebuild_strength_summary(item),
            build_follow_through_recovery_reacquisition_status_label(item),
            build_follow_through_recovery_reacquisition_summary(item),
            build_follow_through_reacquisition_durability_status_label(item),
            build_follow_through_reacquisition_durability_summary(item),
            build_follow_through_reacquisition_consolidation_status_label(item),
            build_follow_through_reacquisition_consolidation_summary(item),
            build_operator_focus(item),
            build_operator_focus_summary(item),
            build_operator_focus_line(item),
            "Open linked artifact" if primary_link else no_linked_artifact_summary(),
            "yes" if safe_to_defer else "no",
        ]
        rows.append(
            {
                "values": values,
                "lane": item.get("lane"),
                "repo_url": item.get("repo_url", ""),
                "artifact_url": primary_link,
            }
        )
    return rows
