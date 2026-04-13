from __future__ import annotations

from typing import Any

from src.action_sync_packets import EXECUTION_PRIORITY
from src.action_sync_readiness import CAMPAIGN_DISPLAY_ORDER, READINESS_PRIORITY
from src.ops_writeback import CAMPAIGN_DEFINITIONS
from src.warehouse import (
    load_campaign_outcomes,
    load_latest_audit_runs,
    load_recent_campaign_runs,
)

OUTCOME_LOOKBACK = 12
RECENT_RUN_LOOKBACK = 20
JUDGED_STATES = frozenset({"holding-clean", "drift-returned", "reopened", "rollback-watch"})
BIAS_PRIORITY = {"promote": 0, "neutral": 1, "defer": 2}
READINESS_STAGE_LABELS = {
    "drift-review": "drift-review",
    "blocked": "blocked",
    "apply-ready": "apply-ready",
    "preview-ready": "preview-ready",
    "idle": "idle",
}


def _copy_mapping(value: Any) -> dict[str, Any]:
    return dict(value or {})


def _current_run_id(report_data: dict[str, Any]) -> str:
    generated_at = str(report_data.get("generated_at") or "")
    username = str(report_data.get("username") or "current")
    return f"{username}:{generated_at}" if generated_at else f"{username}:current"


def _campaign_order(campaign_type: str) -> int:
    try:
        return CAMPAIGN_DISPLAY_ORDER.index(campaign_type)
    except ValueError:
        return len(CAMPAIGN_DISPLAY_ORDER)


def _history_row(row: dict[str, Any]) -> dict[str, Any]:
    details = _copy_mapping(row.get("details"))
    payload = dict(details)
    payload.update(
        {
            "run_id": row.get("run_id", payload.get("run_id", "")),
            "generated_at": row.get("generated_at", payload.get("generated_at", "")),
            "campaign_type": row.get("campaign_type", payload.get("campaign_type", "")),
            "monitoring_state": row.get("monitoring_state", payload.get("monitoring_state", "no-recent-apply")),
            "pressure_effect": row.get("pressure_effect", payload.get("pressure_effect", "insufficient-evidence")),
            "drift_state": row.get("drift_state", payload.get("drift_state", "insufficient-evidence")),
            "reopen_state": row.get("reopen_state", payload.get("reopen_state", "insufficient-evidence")),
            "rollback_state": row.get("rollback_state", payload.get("rollback_state", "not-applicable")),
            "latest_target": row.get("latest_target", payload.get("latest_target", "")),
            "label": row.get("label", payload.get("label", "")),
            "summary": row.get("summary", payload.get("summary", "")),
        }
    )
    return payload


def _current_outcomes(report_data: dict[str, Any]) -> list[dict[str, Any]]:
    run_id = _current_run_id(report_data)
    generated_at = str(report_data.get("generated_at") or "")
    outcomes: list[dict[str, Any]] = []
    for item in report_data.get("action_sync_outcomes") or []:
        payload = dict(item)
        payload.setdefault("run_id", run_id)
        payload.setdefault("generated_at", generated_at)
        outcomes.append(payload)
    return outcomes


def _campaign_histories(report_data: dict[str, Any], outcome_history: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    rows = _current_outcomes(report_data) + [_history_row(row) for row in outcome_history]
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        campaign_type = str(row.get("campaign_type") or "").strip()
        if not campaign_type:
            continue
        key = (str(row.get("run_id") or ""), campaign_type)
        if key not in deduped:
            deduped[key] = row
    grouped: dict[str, list[dict[str, Any]]] = {campaign_type: [] for campaign_type in CAMPAIGN_DISPLAY_ORDER}
    for row in deduped.values():
        grouped.setdefault(str(row.get("campaign_type") or ""), []).append(row)
    for campaign_type in grouped:
        grouped[campaign_type] = sorted(
            grouped[campaign_type],
            key=lambda item: str(item.get("generated_at") or ""),
            reverse=True,
        )[:OUTCOME_LOOKBACK]
    return grouped


def _recent_activity_counts(report_data: dict[str, Any], recent_campaign_runs: list[dict[str, Any]]) -> dict[str, int]:
    counts = {campaign_type: 0 for campaign_type in CAMPAIGN_DISPLAY_ORDER}
    rows = list(recent_campaign_runs)
    campaign_summary = _copy_mapping(report_data.get("campaign_summary"))
    if campaign_summary.get("campaign_type"):
        rows.append(
            {
                "run_id": _current_run_id(report_data),
                "generated_at": str(report_data.get("generated_at") or ""),
                "campaign_type": str(campaign_summary.get("campaign_type") or ""),
            }
        )
    recent_runs = {
        str(item.get("run_id") or "")
        for item in (report_data.get("action_sync_outcomes") or [])
        if item.get("campaign_type")
    }
    for row in rows[:RECENT_RUN_LOOKBACK]:
        campaign_type = str(row.get("campaign_type") or "").strip()
        if campaign_type in counts:
            counts[campaign_type] += 1
            if str(row.get("run_id") or "") in recent_runs:
                counts[campaign_type] += 0
    return counts


def _rate(matched: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return matched / total


def _tuning_status(record: dict[str, Any]) -> str:
    judged_count = int(record.get("judged_count", 0) or 0)
    if judged_count < 3:
        return "insufficient-evidence"
    if (
        float(record.get("holding_clean_rate", 0.0) or 0.0) >= 0.60
        and float(record.get("drift_return_rate", 0.0) or 0.0) <= 0.20
        and float(record.get("reopen_rate", 0.0) or 0.0) <= 0.20
    ):
        return "proven"
    if (
        float(record.get("drift_return_rate", 0.0) or 0.0) >= 0.30
        or float(record.get("reopen_rate", 0.0) or 0.0) >= 0.30
        or float(record.get("rollback_watch_rate", 0.0) or 0.0) >= 0.40
    ):
        return "caution"
    return "mixed"


def _recommendation_bias(tuning_status: str) -> str:
    if tuning_status == "proven":
        return "promote"
    if tuning_status == "caution":
        return "defer"
    return "neutral"


def _summary(record: dict[str, Any]) -> str:
    label = str(record.get("label") or record.get("campaign_type") or "Campaign")
    judged_count = int(record.get("judged_count", 0) or 0)
    tuning_status = str(record.get("tuning_status") or "insufficient-evidence")
    holding_clean_rate = float(record.get("holding_clean_rate", 0.0) or 0.0)
    drift_return_rate = float(record.get("drift_return_rate", 0.0) or 0.0)
    reopen_rate = float(record.get("reopen_rate", 0.0) or 0.0)
    rollback_watch_rate = float(record.get("rollback_watch_rate", 0.0) or 0.0)
    pressure_reduction_rate = float(record.get("pressure_reduction_rate", 0.0) or 0.0)
    if tuning_status == "proven":
        return (
            f"{label} is outcome-proven: {holding_clean_rate:.0%} of {judged_count} judged outcomes held clean, "
            f"with {drift_return_rate:.0%} drift return and {reopen_rate:.0%} reopen rates."
        )
    if tuning_status == "caution":
        return (
            f"{label} needs caution: drift return is {drift_return_rate:.0%}, reopen is {reopen_rate:.0%}, "
            f"and rollback watch is {rollback_watch_rate:.0%} across {judged_count} judged outcomes."
        )
    if tuning_status == "mixed":
        return (
            f"{label} is mixed: {holding_clean_rate:.0%} held clean and {pressure_reduction_rate:.0%} reduced pressure "
            f"across {judged_count} judged outcomes."
        )
    monitor_now_count = int(record.get("monitor_now_count", 0) or 0)
    return (
        f"{label} still has thin outcome evidence: only {judged_count} judged outcome(s) and "
        f"{monitor_now_count} campaign(s) still in the monitor-now window."
    )


def _readiness_sort_key(record: dict[str, Any], tuning: dict[str, Any]) -> tuple[int, int, int, int, int]:
    return (
        READINESS_PRIORITY.get(str(record.get("readiness_stage") or "idle"), 99),
        BIAS_PRIORITY.get(str(tuning.get("recommendation_bias") or "neutral"), 99),
        -int(tuning.get("judged_count", 0) or 0),
        -int(record.get("action_count", 0) or 0),
        _campaign_order(str(record.get("campaign_type") or "")),
    )


def _packet_sort_key(packet: dict[str, Any], tuning: dict[str, Any]) -> tuple[int, int, int, int, int]:
    return (
        EXECUTION_PRIORITY.get(str(packet.get("execution_state") or "stay-local"), 99),
        BIAS_PRIORITY.get(str(tuning.get("recommendation_bias") or "neutral"), 99),
        -int(tuning.get("judged_count", 0) or 0),
        -int(packet.get("action_count", 0) or 0),
        _campaign_order(str(packet.get("campaign_type") or "")),
    )


def _tuned_next_action_sync_step(record: dict[str, Any]) -> str:
    label = str(record.get("label") or record.get("campaign_type") or "Campaign")
    target = str(record.get("recommended_target") or "none")
    stage = str(record.get("readiness_stage") or "idle")
    if stage == "drift-review":
        return f"Review managed drift in {label} before any further Action Sync."
    if stage == "blocked":
        return f"Unblock {label} first, then preview it again before any outward writeback."
    if stage == "apply-ready":
        return f"{label} is ready to apply to {target}; preview once more if needed, then run apply when you are comfortable."
    if stage == "preview-ready":
        return f"Preview {label} next, then decide whether it is ready to apply to {target}."
    return "Stay local for now; no current campaign needs preview or apply."


def _next_tuned_campaign_summary(record: dict[str, Any], tuning: dict[str, Any]) -> str:
    label = str(record.get("label") or record.get("campaign_type") or "Campaign")
    stage = READINESS_STAGE_LABELS.get(str(record.get("readiness_stage") or "idle"), "idle")
    bias = str(tuning.get("recommendation_bias") or "neutral")
    tuning_status = str(tuning.get("tuning_status") or "insufficient-evidence")
    judged_count = int(tuning.get("judged_count", 0) or 0)
    if str(record.get("readiness_stage") or "idle") == "idle":
        return "Stay local for now; no current campaign has enough local action to need a tuning tie-break."
    if bias == "promote":
        return f"{label} should win ties inside the current {stage} group because recent outcome history is proven across {judged_count} judged runs."
    if bias == "defer":
        return f"{label} should lose ties inside the current {stage} group because recent outcomes still show caution-level drift, reopen, or rollback risk."
    if tuning_status == "insufficient-evidence":
        return f"{label} is the current tie-break candidate in the {stage} group, but the outcome history is still thin and stage order still comes first."
    return f"{label} stays neutral inside the current {stage} group because recent outcome history is mixed."


def _campaign_tuning_summary(
    readiness_records: list[dict[str, Any]],
    tuning_by_campaign: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    actionable = [record for record in readiness_records if int(record.get("action_count", 0) or 0) > 0]
    if not actionable:
        return {
            "summary": "Campaign tuning is idle because no current campaign has meaningful actions that need a bounded tie-break yet.",
            "counts": {"proven": 0, "mixed": 0, "caution": 0, "insufficient-evidence": 0},
        }
    ordered = sorted(actionable, key=lambda record: _readiness_sort_key(record, tuning_by_campaign.get(str(record.get("campaign_type") or ""), {})))
    top_record = ordered[0]
    top_tuning = tuning_by_campaign.get(str(top_record.get("campaign_type") or ""), {})
    counts = {
        status: sum(1 for item in tuning_by_campaign.values() if item.get("tuning_status") == status)
        for status in ("proven", "mixed", "caution", "insufficient-evidence")
    }
    return {
        "summary": _next_tuned_campaign_summary(top_record, top_tuning),
        "counts": counts,
    }


def _top_tuning_group(
    tuning_records: list[dict[str, Any]],
    *,
    tuning_status: str,
    primary_key: str,
) -> list[dict[str, Any]]:
    filtered = [record for record in tuning_records if str(record.get("tuning_status") or "") == tuning_status]
    return sorted(
        filtered,
        key=lambda item: (
            -int(item.get(primary_key, 0) or 0),
            -int(item.get("judged_count", 0) or 0),
            _campaign_order(str(item.get("campaign_type") or "")),
        ),
    )[:3]


def _next_tuned_campaign(
    readiness_records: list[dict[str, Any]],
    tuning_by_campaign: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    actionable = [record for record in readiness_records if int(record.get("action_count", 0) or 0) > 0]
    if not actionable:
        return {
            "campaign_type": "",
            "summary": "Stay local for now; no current campaign has enough local action to need a tuning tie-break.",
            "recommendation_bias": "neutral",
            "tuning_status": "insufficient-evidence",
        }
    ordered = sorted(actionable, key=lambda record: _readiness_sort_key(record, tuning_by_campaign.get(str(record.get("campaign_type") or ""), {})))
    record = ordered[0]
    tuning = tuning_by_campaign.get(str(record.get("campaign_type") or ""), {})
    return {
        "campaign_type": record.get("campaign_type", ""),
        "label": record.get("label", ""),
        "readiness_stage": record.get("readiness_stage", "idle"),
        "recommendation_bias": tuning.get("recommendation_bias", "neutral"),
        "tuning_status": tuning.get("tuning_status", "insufficient-evidence"),
        "judged_count": tuning.get("judged_count", 0),
        "summary": _next_tuned_campaign_summary(record, tuning),
    }


def _queue_tuning_lines(queue: list[dict[str, Any]], tuning_by_campaign: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for item in queue:
        mapped = dict(item)
        campaign_type = str(mapped.get("suggested_campaign") or "").strip()
        tuning = tuning_by_campaign.get(campaign_type, {})
        mapped["campaign_tuning_status"] = str(tuning.get("tuning_status") or "insufficient-evidence")
        mapped["campaign_tuning_summary"] = str(tuning.get("summary") or "No campaign tuning evidence is surfaced for this item yet.")
        mapped["campaign_tuning_line"] = f"Campaign Tuning: {mapped['campaign_tuning_summary']}"
        enriched.append(mapped)
    return enriched


def _sorted_stage_group(
    records: list[dict[str, Any]],
    tuning_by_campaign: dict[str, dict[str, Any]],
    *,
    stage_key: str,
    stage_value: str,
    packet: bool = False,
) -> list[dict[str, Any]]:
    filtered = [record for record in records if str(record.get(stage_key) or "") == stage_value]
    sort_fn = _packet_sort_key if packet else _readiness_sort_key
    return sorted(filtered, key=lambda record: sort_fn(record, tuning_by_campaign.get(str(record.get("campaign_type") or ""), {})))


def build_action_sync_tuning_bundle(
    report_data: dict[str, Any],
    readiness_bundle: dict[str, Any],
    packets_bundle: dict[str, Any],
    _outcomes_bundle: dict[str, Any],
    queue: list[dict[str, Any]],
    *,
    recent_runs: list[dict[str, Any]],
    recent_campaign_runs: list[dict[str, Any]],
    outcome_history: list[dict[str, Any]],
) -> dict[str, Any]:
    histories = _campaign_histories(report_data, outcome_history)
    activity_counts = _recent_activity_counts(report_data, recent_campaign_runs)
    readiness_records = list((readiness_bundle.get("campaign_readiness_summary") or {}).get("campaigns") or [])
    packet_records = list(packets_bundle.get("action_sync_packets") or [])

    tuning_records: list[dict[str, Any]] = []
    tuning_by_campaign: dict[str, dict[str, Any]] = {}
    for campaign_type in CAMPAIGN_DISPLAY_ORDER:
        rows = histories.get(campaign_type, [])[:OUTCOME_LOOKBACK]
        judged_rows = [row for row in rows if str(row.get("monitoring_state") or "") in JUDGED_STATES]
        judged_count = len(judged_rows)
        monitor_now_count = sum(1 for row in rows if str(row.get("monitoring_state") or "") == "monitor-now")
        record = {
            "campaign_type": campaign_type,
            "label": str(CAMPAIGN_DEFINITIONS[campaign_type]["label"]),
            "judged_count": judged_count,
            "monitor_now_count": monitor_now_count,
            "holding_clean_rate": _rate(sum(1 for row in judged_rows if str(row.get("monitoring_state") or "") == "holding-clean"), judged_count),
            "drift_return_rate": _rate(sum(1 for row in judged_rows if str(row.get("monitoring_state") or "") == "drift-returned"), judged_count),
            "reopen_rate": _rate(sum(1 for row in judged_rows if str(row.get("monitoring_state") or "") == "reopened"), judged_count),
            "rollback_watch_rate": _rate(sum(1 for row in judged_rows if str(row.get("monitoring_state") or "") == "rollback-watch"), judged_count),
            "pressure_reduction_rate": _rate(sum(1 for row in judged_rows if str(row.get("pressure_effect") or "") == "reduced"), judged_count),
            "recent_activity_count": int(activity_counts.get(campaign_type, 0) or 0),
            "recent_run_count": min(len(recent_runs), RECENT_RUN_LOOKBACK),
        }
        record["tuning_status"] = _tuning_status(record)
        record["recommendation_bias"] = _recommendation_bias(str(record["tuning_status"]))
        record["summary"] = _summary(record)
        tuning_records.append(record)
        tuning_by_campaign[campaign_type] = record

    readiness_by_campaign = {
        str(record.get("campaign_type") or ""): record for record in readiness_records
    }
    tuned_packet_records = sorted(
        packet_records,
        key=lambda packet: _packet_sort_key(packet, tuning_by_campaign.get(str(packet.get("campaign_type") or ""), {})),
    )
    actionable_packets = [packet for packet in tuned_packet_records if str(packet.get("execution_state") or "") != "stay-local"]
    next_apply_candidate = actionable_packets[0] if actionable_packets else {
        "campaign_type": "",
        "execution_state": "stay-local",
        "summary": "Stay local for now; no current campaign has a safe execution handoff.",
    }
    next_tuned = _next_tuned_campaign(readiness_records, tuning_by_campaign)
    queue = _queue_tuning_lines(queue, tuning_by_campaign)
    return {
        "action_sync_tuning": tuning_records,
        "campaign_tuning_summary": _campaign_tuning_summary(readiness_records, tuning_by_campaign),
        "next_tuned_campaign": next_tuned,
        "next_action_sync_step": _tuned_next_action_sync_step(readiness_by_campaign.get(next_tuned.get("campaign_type", ""), {})) if next_tuned.get("campaign_type") else "Stay local for now; no current campaign needs preview or apply.",
        "next_apply_candidate": next_apply_candidate,
        "top_apply_ready_campaigns": _sorted_stage_group(readiness_records, tuning_by_campaign, stage_key="readiness_stage", stage_value="apply-ready"),
        "top_preview_ready_campaigns": _sorted_stage_group(readiness_records, tuning_by_campaign, stage_key="readiness_stage", stage_value="preview-ready"),
        "top_drift_review_campaigns": _sorted_stage_group(readiness_records, tuning_by_campaign, stage_key="readiness_stage", stage_value="drift-review"),
        "top_blocked_campaigns": _sorted_stage_group(readiness_records, tuning_by_campaign, stage_key="readiness_stage", stage_value="blocked"),
        "top_ready_to_apply_packets": _sorted_stage_group(packet_records, tuning_by_campaign, stage_key="execution_state", stage_value="ready-to-apply", packet=True),
        "top_needs_approval_packets": _sorted_stage_group(packet_records, tuning_by_campaign, stage_key="execution_state", stage_value="needs-approval", packet=True),
        "top_review_drift_packets": _sorted_stage_group(packet_records, tuning_by_campaign, stage_key="execution_state", stage_value="review-drift", packet=True),
        "top_proven_campaigns": _top_tuning_group(
            tuning_records,
            tuning_status="proven",
            primary_key="judged_count",
        ),
        "top_caution_campaigns": _top_tuning_group(
            tuning_records,
            tuning_status="caution",
            primary_key="judged_count",
        ),
        "top_thin_evidence_campaigns": _top_tuning_group(
            tuning_records,
            tuning_status="insufficient-evidence",
            primary_key="monitor_now_count",
        ),
        "operator_queue": queue,
    }


def load_action_sync_tuning_bundle(
    output_dir: Any,
    report_data: dict[str, Any],
    readiness_bundle: dict[str, Any],
    packets_bundle: dict[str, Any],
    outcomes_bundle: dict[str, Any],
    queue: list[dict[str, Any]],
) -> dict[str, Any]:
    username = str(report_data.get("username") or "")
    return build_action_sync_tuning_bundle(
        report_data,
        readiness_bundle,
        packets_bundle,
        outcomes_bundle,
        queue,
        recent_runs=load_latest_audit_runs(output_dir, username, limit=RECENT_RUN_LOOKBACK),
        recent_campaign_runs=load_recent_campaign_runs(output_dir, username, limit=RECENT_RUN_LOOKBACK),
        outcome_history=load_campaign_outcomes(output_dir, username, limit=OUTCOME_LOOKBACK * len(CAMPAIGN_DISPLAY_ORDER)),
    )
