import json
from collections import Counter


def _severity_rank(value: object) -> float:
    mapping = {"critical": 1.0, "high": 0.85, "medium": 0.55, "low": 0.25}
    return mapping.get(str(value).lower(), 0.0)


def _build_queue_rows(queue: list[dict]) -> list[list[object]]:
    queue_rows: list[list[object]] = []
    for item in queue:
        queue_rows.append(
            [
                item.get("item_id", ""),
                item.get("repo", ""),
                item.get("kind", ""),
                item.get("lane", ""),
                item.get("priority", 0),
                item.get("title", ""),
                item.get("summary", ""),
                item.get("recommended_action", ""),
                item.get("source_run_id", ""),
                item.get("age_days", 0),
                json.dumps(item.get("links", [])),
                item.get("follow_through_age_runs", 0),
                item.get("follow_through_status", ""),
                item.get("follow_through_checkpoint_status", ""),
                item.get("follow_through_summary", ""),
                item.get("follow_through_last_touch", ""),
                item.get("follow_through_next_checkpoint", ""),
                item.get("follow_through_evidence_hint", ""),
                item.get("follow_through_escalation_status", ""),
                item.get("follow_through_escalation_summary", ""),
                item.get("follow_through_escalation_reason", ""),
                item.get("follow_through_recovery_age_runs", 0),
                item.get("follow_through_recovery_status", ""),
                item.get("follow_through_recovery_summary", ""),
                item.get("follow_through_recovery_reason", ""),
                item.get("follow_through_recovery_persistence_age_runs", 0),
                item.get("follow_through_recovery_persistence_status", ""),
                item.get("follow_through_recovery_persistence_summary", ""),
                item.get("follow_through_recovery_persistence_reason", ""),
                item.get("follow_through_relapse_churn_status", ""),
                item.get("follow_through_relapse_churn_summary", ""),
                item.get("follow_through_relapse_churn_reason", ""),
                item.get("follow_through_recovery_freshness_age_runs", 0),
                item.get("follow_through_recovery_freshness_status", ""),
                item.get("follow_through_recovery_freshness_summary", ""),
                item.get("follow_through_recovery_freshness_reason", ""),
                item.get("follow_through_recovery_decay_status", ""),
                item.get("follow_through_recovery_decay_summary", ""),
                item.get("follow_through_recovery_decay_reason", ""),
                item.get("follow_through_recovery_memory_reset_status", ""),
                item.get("follow_through_recovery_memory_reset_summary", ""),
                item.get("follow_through_recovery_memory_reset_reason", ""),
                item.get("follow_through_recovery_rebuild_strength_age_runs", 0),
                item.get("follow_through_recovery_rebuild_strength_status", ""),
                item.get("follow_through_recovery_rebuild_strength_summary", ""),
                item.get("follow_through_recovery_rebuild_strength_reason", ""),
                item.get("follow_through_recovery_reacquisition_status", ""),
                item.get("follow_through_recovery_reacquisition_summary", ""),
                item.get("follow_through_recovery_reacquisition_reason", ""),
                item.get("follow_through_recovery_reacquisition_durability_age_runs", 0),
                item.get("follow_through_recovery_reacquisition_durability_status", ""),
                item.get("follow_through_recovery_reacquisition_durability_summary", ""),
                item.get("follow_through_recovery_reacquisition_durability_reason", ""),
                item.get("follow_through_recovery_reacquisition_consolidation_status", ""),
                item.get("follow_through_recovery_reacquisition_consolidation_summary", ""),
                item.get("follow_through_recovery_reacquisition_consolidation_reason", ""),
                item.get("follow_through_reacquisition_softening_decay_age_runs", 0),
                item.get("follow_through_reacquisition_softening_decay_status", ""),
                item.get("follow_through_reacquisition_softening_decay_summary", ""),
                item.get("follow_through_reacquisition_softening_decay_reason", ""),
                item.get("follow_through_reacquisition_confidence_retirement_status", ""),
                item.get("follow_through_reacquisition_confidence_retirement_summary", ""),
                item.get("follow_through_reacquisition_confidence_retirement_reason", ""),
                item.get("follow_through_reacquisition_revalidation_recovery_age_runs", 0),
                item.get("follow_through_reacquisition_revalidation_recovery_status", ""),
                item.get("follow_through_reacquisition_revalidation_recovery_summary", ""),
                item.get("follow_through_reacquisition_revalidation_recovery_reason", ""),
                item.get("catalog_line", ""),
                item.get("operating_path_line", ""),
                item.get("intent_alignment", ""),
                item.get("intent_alignment_reason", ""),
                item.get("scorecard_line", ""),
                item.get("maturity_gap_summary", ""),
                item.get("action_sync_stage", ""),
                item.get("action_sync_reason", ""),
                item.get("suggested_campaign", ""),
                item.get("suggested_writeback_target", ""),
                item.get("action_sync_line", ""),
                item.get("apply_packet_state", ""),
                item.get("apply_packet_summary", ""),
                item.get("apply_packet_command", ""),
                item.get("post_apply_state", ""),
                item.get("post_apply_summary", ""),
                item.get("post_apply_line", ""),
                item.get("campaign_tuning_status", ""),
                item.get("campaign_tuning_summary", ""),
                item.get("campaign_tuning_line", ""),
                item.get("historical_intelligence_status", ""),
                item.get("historical_intelligence_summary", ""),
                item.get("historical_intelligence_line", ""),
                item.get("approval_state", ""),
                item.get("approval_summary", ""),
                item.get("approval_line", ""),
            ]
        )
    return queue_rows


def _build_repo_rollup_rows(queue: list[dict]) -> list[list[object]]:
    repo_rollups: dict[str, dict[str, object]] = {}
    for item in queue:
        repo = item.get("repo") or "(portfolio)"
        record = repo_rollups.setdefault(
            repo,
            {
                "blocked": 0,
                "urgent": 0,
                "ready": 0,
                "deferred": 0,
                "total": 0,
                "kind_counts": Counter(),
                "top_priority": 0,
                "top_title": "",
                "recommended_action": "",
            },
        )
        lane = item.get("lane", "")
        if lane in {"blocked", "urgent", "ready", "deferred"}:
            record[lane] += 1
        record["total"] += 1
        record["kind_counts"][item.get("kind", "review")] += 1
        priority = _severity_rank(item.get("priority", 0))
        if priority >= float(record["top_priority"]):
            record["top_priority"] = priority
            record["top_title"] = item.get("title", "")
            record["recommended_action"] = item.get("recommended_action", "")

    repo_rows: list[list[object]] = []
    for repo, record in sorted(
        repo_rollups.items(),
        key=lambda item: (
            -int(item[1]["blocked"]),
            -int(item[1]["urgent"]),
            -int(item[1]["ready"]),
            -int(item[1]["total"]),
            item[0],
        ),
    ):
        primary_kind = (
            record["kind_counts"].most_common(1)[0][0] if record["kind_counts"] else "review"
        )
        repo_rows.append(
            [
                repo,
                record["total"],
                record["blocked"],
                record["urgent"],
                record["ready"],
                record["deferred"],
                primary_kind,
                record["top_priority"],
                record["top_title"],
                record["recommended_action"],
            ]
        )
    return repo_rows


def _build_material_rollup_rows(material_changes: list[dict]) -> list[list[object]]:
    material_rollups: dict[tuple[str, str], dict[str, object]] = {}
    for item in material_changes:
        repo = item.get("repo") or "(portfolio)"
        change_type = item.get("change_type") or "other"
        key = (repo, change_type)
        record = material_rollups.setdefault(
            key,
            {"count": 0, "max_severity": 0.0, "sample_title": ""},
        )
        record["count"] += 1
        severity = _severity_rank(item.get("severity"))
        if severity >= float(record["max_severity"]):
            record["max_severity"] = severity
            record["sample_title"] = item.get("title", "")

    material_rows: list[list[object]] = []
    for (repo, change_type), record in sorted(
        material_rollups.items(),
        key=lambda item: (
            -int(item[1]["count"]),
            -float(item[1]["max_severity"]),
            item[0][0],
            item[0][1],
        ),
    ):
        material_rows.append(
            [
                repo,
                change_type,
                record["count"],
                record["max_severity"],
                record["sample_title"],
            ]
        )
    return material_rows


def build_workbook_rollups(
    data: dict,
) -> tuple[list[list[object]], list[list[object]], list[list[object]]]:
    queue = data.get("operator_queue", []) or []
    material_changes = data.get("material_changes", []) or []
    return (
        _build_queue_rows(queue),
        _build_repo_rollup_rows(queue),
        _build_material_rollup_rows(material_changes),
    )
