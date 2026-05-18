from __future__ import annotations

from typing import Any

from src.action_sync_readiness import CAMPAIGN_DISPLAY_ORDER
from src.ops_writeback import CAMPAIGN_DEFINITIONS
from src.warehouse import (
    load_latest_audit_runs,
    load_recent_action_runs,
    load_recent_campaign_drift_events,
    load_recent_campaign_history,
    load_recent_campaign_runs,
    load_recent_rollback_runs,
)

FOLLOW_UP_WINDOW_RUNS = 6
MIN_HOLDING_POST_RUNS = 2

MONITORING_PRIORITY = {
    "drift-returned": 0,
    "reopened": 1,
    "rollback-watch": 2,
    "monitor-now": 3,
    "holding-clean": 4,
    "insufficient-evidence": 5,
    "no-recent-apply": 6,
}


def _current_run_id(report_data: dict[str, Any]) -> str:
    generated_at = str(report_data.get("generated_at") or "")
    username = str(report_data.get("username") or "current")
    return f"{username}:{generated_at}" if generated_at else f"{username}:current"


def _copy_mapping(value: Any) -> dict[str, Any]:
    return dict(value or {})


def _current_run_snapshot(report_data: dict[str, Any]) -> dict[str, Any]:
    operator_summary = _copy_mapping(report_data.get("operator_summary"))
    return {
        "run_id": _current_run_id(report_data),
        "generated_at": str(report_data.get("generated_at") or ""),
        "campaign_summary": _copy_mapping(report_data.get("campaign_summary")),
        "writeback_preview": _copy_mapping(report_data.get("writeback_preview")),
        "writeback_results": _copy_mapping(report_data.get("writeback_results")),
        "managed_state_drift": list(report_data.get("managed_state_drift") or []),
        "rollback_preview": _copy_mapping(report_data.get("rollback_preview")),
        "campaign_history": list(report_data.get("campaign_history") or []),
        "operator_summary": operator_summary,
        "operator_queue": list(report_data.get("operator_queue") or []),
        "campaign_outcomes_summary": _copy_mapping(report_data.get("campaign_outcomes_summary")),
    }


def _run_snapshots(
    report_data: dict[str, Any],
    recent_runs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    snapshots = [_current_run_snapshot(report_data)]
    seen = {snapshots[0]["run_id"]}
    for run in recent_runs:
        run_id = str(run.get("run_id") or "")
        if run_id and run_id not in seen:
            snapshots.append(run)
            seen.add(run_id)
        if len(snapshots) >= FOLLOW_UP_WINDOW_RUNS:
            break
    return snapshots[:FOLLOW_UP_WINDOW_RUNS]


def _current_campaign_run_event(report_data: dict[str, Any]) -> dict[str, Any] | None:
    campaign_summary = _copy_mapping(report_data.get("campaign_summary"))
    if not campaign_summary.get("campaign_type"):
        return None
    writeback_results = _copy_mapping(report_data.get("writeback_results"))
    writeback_preview = _copy_mapping(report_data.get("writeback_preview"))
    campaign_run = _copy_mapping(writeback_results.get("campaign_run"))
    mode = str(campaign_run.get("mode") or writeback_results.get("mode") or writeback_preview.get("mode") or "preview")
    target = str(campaign_run.get("writeback_target") or writeback_results.get("target") or writeback_preview.get("target") or "preview-only")
    generated_action_ids = list(campaign_run.get("generated_action_ids") or [])
    if not generated_action_ids:
        generated_action_ids = [str(action.get("action_id") or "") for action in report_data.get("action_runs") or [] if str(action.get("campaign_type") or "") == str(campaign_summary.get("campaign_type") or "")]
    return {
        "run_id": _current_run_id(report_data),
        "generated_at": str(report_data.get("generated_at") or ""),
        "campaign_type": str(campaign_summary.get("campaign_type") or ""),
        "label": str(campaign_summary.get("label") or CAMPAIGN_DEFINITIONS.get(campaign_summary.get("campaign_type"), {}).get("label", "Campaign")),
        "writeback_target": target,
        "mode": mode,
        "generated_action_ids": generated_action_ids,
    }


def _campaign_run_events(
    report_data: dict[str, Any],
    recent_campaign_runs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    events = []
    current_event = _current_campaign_run_event(report_data)
    if current_event:
        events.append(current_event)
    seen = {(current_event or {}).get("run_id"), (current_event or {}).get("campaign_type")}
    for event in recent_campaign_runs:
        key = (event.get("run_id"), event.get("campaign_type"))
        if key in seen:
            continue
        events.append(dict(event))
        seen.add(key)
    events.sort(key=lambda item: str(item.get("generated_at") or ""), reverse=True)
    return events


def _current_action_runs(report_data: dict[str, Any]) -> list[dict[str, Any]]:
    run_id = _current_run_id(report_data)
    generated_at = str(report_data.get("generated_at") or "")
    rows = []
    for item in report_data.get("action_runs") or []:
        row = dict(item)
        row["run_id"] = run_id
        row["generated_at"] = generated_at
        row["repo_id"] = row.get("repo_id") or row.get("repo_full_name") or ""
        rows.append(row)
    return rows


def _current_campaign_history(report_data: dict[str, Any]) -> list[dict[str, Any]]:
    generated_at = str(report_data.get("generated_at") or "")
    rows = []
    for item in report_data.get("campaign_history") or []:
        row = dict(item)
        row.setdefault("generated_at", generated_at)
        row.setdefault("repo_id", row.get("repo_full_name") or "")
        row.setdefault("repo", row.get("repo_full_name") or row.get("repo") or "")
        rows.append(row)
    return rows


def _current_drift_events(report_data: dict[str, Any]) -> list[dict[str, Any]]:
    run_id = _current_run_id(report_data)
    generated_at = str(report_data.get("generated_at") or "")
    events = []
    active_campaign = str((_copy_mapping(report_data.get("campaign_summary"))).get("campaign_type") or "")
    for item in report_data.get("managed_state_drift") or []:
        row = dict(item)
        row["run_id"] = run_id
        row["generated_at"] = generated_at
        row["campaign_type"] = str(item.get("campaign_type") or active_campaign)
        row["details"] = dict(item)
        events.append(row)
    return events


def _current_rollback_runs(report_data: dict[str, Any]) -> list[dict[str, Any]]:
    source_run_id = _current_run_id(report_data)
    generated_at = str(report_data.get("generated_at") or "")
    results = []
    for item in (_copy_mapping(report_data.get("rollback_preview")).get("items") or []):
        results.append(
            {
                "run_id": f"{source_run_id}:{item.get('action_id', item.get('repo_full_name', 'rollback'))}:{item.get('target', '')}",
                "source_run_id": source_run_id,
                "generated_at": generated_at,
                "preview": dict(item),
                "results": {},
                "status": item.get("rollback_state", "preview"),
            }
        )
    return results


def _high_pressure_count(snapshot: dict[str, Any]) -> int | None:
    summary = _copy_mapping(snapshot.get("operator_summary"))
    counts = _copy_mapping(summary.get("counts"))
    blocked = counts.get("blocked")
    urgent = counts.get("urgent")
    if blocked is None and urgent is None:
        queue = list(snapshot.get("operator_queue") or [])
        if not queue:
            return None
        blocked = sum(1 for item in queue if str(item.get("lane") or "") == "blocked")
        urgent = sum(1 for item in queue if str(item.get("lane") or "") == "urgent")
    return int(blocked or 0) + int(urgent or 0)


def _sort_by_generated(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda item: str(item.get("generated_at") or ""), reverse=True)


def _latest_apply_event(
    campaign_runs: list[dict[str, Any]],
    run_ids: set[str],
    campaign_type: str,
    *,
    allow_thin_history_fallback: bool = False,
) -> dict[str, Any]:
    matching = [
        row for row in campaign_runs
        if row.get("campaign_type") == campaign_type and row.get("mode") == "apply" and str(row.get("run_id") or "") in run_ids
    ]
    if matching:
        return _sort_by_generated(matching)[0]
    if not allow_thin_history_fallback:
        return {}
    fallback = [
        row for row in campaign_runs
        if row.get("campaign_type") == campaign_type and row.get("mode") == "apply"
    ]
    return _sort_by_generated(fallback)[0] if fallback else {}


def _latest_event(
    campaign_runs: list[dict[str, Any]],
    run_ids: set[str],
    campaign_type: str,
    *,
    allow_thin_history_fallback: bool = False,
) -> dict[str, Any]:
    matching = [
        row for row in campaign_runs
        if row.get("campaign_type") == campaign_type and str(row.get("run_id") or "") in run_ids
    ]
    if matching:
        return _sort_by_generated(matching)[0]
    if not allow_thin_history_fallback:
        return {}
    fallback = [row for row in campaign_runs if row.get("campaign_type") == campaign_type]
    return _sort_by_generated(fallback)[0] if fallback else {}


def _action_rows_for_run(action_runs: list[dict[str, Any]], run_id: str, campaign_type: str) -> list[dict[str, Any]]:
    return [
        row for row in action_runs
        if str(row.get("run_id") or "") == run_id and str(row.get("campaign_type") or "") == campaign_type
    ]


def _top_repos(action_rows: list[dict[str, Any]]) -> list[str]:
    repos: list[str] = []
    for row in action_rows:
        repo = str(row.get("repo_id") or row.get("repo_full_name") or row.get("repo") or "").strip()
        if repo and repo not in repos:
            repos.append(repo)
        if len(repos) == 3:
            break
    return repos


def _monitoring_run_slices(run_snapshots: list[dict[str, Any]], apply_run_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    apply_snapshot = {}
    post_runs: list[dict[str, Any]] = []
    for index, snapshot in enumerate(run_snapshots):
        if str(snapshot.get("run_id") or "") == apply_run_id:
            apply_snapshot = snapshot
            post_runs = run_snapshots[:index]
            break
    return apply_snapshot, post_runs


def _campaign_drift_returned(
    campaign_type: str,
    post_runs: list[dict[str, Any]],
    drift_events: list[dict[str, Any]],
    apply_generated_at: str,
    action_ids: set[str],
) -> bool:
    for run in post_runs:
        for drift in run.get("managed_state_drift") or []:
            drift_campaign = str(drift.get("campaign_type") or "").strip()
            if drift_campaign == campaign_type:
                return True
            if action_ids and str(drift.get("action_id") or "") in action_ids:
                return True
    for event in drift_events:
        if str(event.get("campaign_type") or "") != campaign_type:
            continue
        if str(event.get("generated_at") or "") <= apply_generated_at:
            continue
        if action_ids and str(event.get("action_id") or "") not in action_ids and str(event.get("action_id") or ""):
            continue
        return True
    return False


def _campaign_reopened(
    campaign_type: str,
    campaign_history: list[dict[str, Any]],
    apply_generated_at: str,
) -> bool:
    for item in campaign_history:
        if str(item.get("campaign_type") or "") != campaign_type:
            continue
        if str(item.get("generated_at") or "") <= apply_generated_at:
            continue
        if item.get("reopened_at") or str(item.get("lifecycle_state") or "") == "open" and str(item.get("reconciliation_outcome") or "") == "reopened":
            return True
        if str(item.get("reconciliation_outcome") or "") == "reopened":
            return True
    return False


def _rollback_state(
    action_rows: list[dict[str, Any]],
    rollback_runs: list[dict[str, Any]],
    apply_run_id: str,
) -> str:
    if any(str(item.get("source_run_id") or "") == apply_run_id and str(item.get("status") or "") not in {"preview", ""} for item in rollback_runs):
        return "used"
    if not action_rows:
        return "not-applicable"
    states = {str(item.get("rollback_state") or "") for item in action_rows}
    if not states:
        return "not-applicable"
    if states <= {"fully-reversible", "rollback-available"}:
        return "ready"
    if "partial" in states or "fully-reversible" in states or "rollback-available" in states:
        return "partial"
    if states <= {"non-reversible"}:
        return "missing"
    return "partial"


def _pressure_effect(apply_snapshot: dict[str, Any], post_runs: list[dict[str, Any]]) -> str:
    if not apply_snapshot or not post_runs:
        return "insufficient-evidence"
    apply_pressure = _high_pressure_count(apply_snapshot)
    latest_pressure = _high_pressure_count(post_runs[0])
    if apply_pressure is None or latest_pressure is None:
        return "insufficient-evidence"
    if latest_pressure < apply_pressure:
        return "reduced"
    if latest_pressure > apply_pressure:
        return "worse"
    return "flat"


def _monitoring_state(
    *,
    recent_apply_count: int,
    drift_state: str,
    reopen_state: str,
    rollback_state: str,
    has_apply_snapshot: bool,
    post_run_count: int,
    pressure_effect: str,
) -> str:
    if recent_apply_count <= 0:
        return "no-recent-apply"
    if drift_state == "returned":
        return "drift-returned"
    if reopen_state == "reopened":
        return "reopened"
    if rollback_state in {"partial", "missing", "used"}:
        return "rollback-watch"
    if not has_apply_snapshot:
        return "insufficient-evidence"
    if post_run_count < MIN_HOLDING_POST_RUNS:
        return "monitor-now"
    return "holding-clean"


def _follow_up_recommendation(record: dict[str, Any]) -> str:
    label = str(record.get("label") or record.get("campaign_type") or "Campaign")
    target = str(record.get("latest_target") or "managed targets")
    state = str(record.get("monitoring_state") or "no-recent-apply")
    pressure_effect = str(record.get("pressure_effect") or "insufficient-evidence")
    if state == "drift-returned":
        return f"Review managed drift in {label} before any further sync to {target}."
    if state == "reopened":
        return f"Review reopened action lifecycle in {label} before deciding on another sync to {target}."
    if state == "rollback-watch":
        return f"Keep {label} under rollback watch before trusting another apply to {target}."
    if state == "monitor-now":
        return f"Monitor {label} for at least {MIN_HOLDING_POST_RUNS} post-apply runs before treating it as stable."
    if state == "holding-clean":
        if pressure_effect == "insufficient-evidence":
            return f"{label} is holding clean after apply; keep monitoring while pressure evidence fills in."
        return f"{label} is holding clean after apply; keep monitoring while pressure looks {pressure_effect}."
    if state == "insufficient-evidence":
        return f"{label} has some recent apply evidence, but not enough follow-up data exists yet to judge whether it held."
    return f"No recent apply is recorded for {label}; keep the story local until that campaign is used."


def _summary(record: dict[str, Any]) -> str:
    label = str(record.get("label") or record.get("campaign_type") or "Campaign")
    state = str(record.get("monitoring_state") or "no-recent-apply")
    pressure_effect = str(record.get("pressure_effect") or "insufficient-evidence")
    if state == "drift-returned":
        return f"{label} drift returned after apply, so the managed mirror needs review before more Action Sync."
    if state == "reopened":
        return f"{label} reopened after apply, so the original sync did not hold cleanly."
    if state == "rollback-watch":
        return f"{label} needs rollback watch because the apply path was not fully reversible or rollback was used."
    if state == "monitor-now":
        return f"{label} was applied recently; monitor it now before treating it as stable."
    if state == "holding-clean":
        if pressure_effect == "insufficient-evidence":
            return f"{label} is holding clean after apply and the pressure trend is still filling in."
        return f"{label} is holding clean after apply and portfolio pressure looks {pressure_effect}."
    if state == "insufficient-evidence":
        return f"{label} has recent apply evidence, but there is not enough follow-up history yet to judge the outcome."
    return f"{label} has no recent apply in the follow-up window."


def _outcome_sort_key(record: dict[str, Any]) -> tuple[int, int, str]:
    return (
        MONITORING_PRIORITY.get(str(record.get("monitoring_state") or "no-recent-apply"), 99),
        -int(record.get("recent_apply_count", 0) or 0),
        str(record.get("campaign_type") or ""),
    )


def _next_monitoring_step(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    actionable = [
        record
        for record in outcomes
        if str(record.get("monitoring_state") or "") not in {"no-recent-apply", "insufficient-evidence"}
    ]
    if not actionable:
        return {
            "campaign_type": "",
            "monitoring_state": "stay-local",
            "summary": "Stay local for now; no recent Action Sync apply needs post-apply follow-up yet.",
        }
    record = sorted(actionable, key=_outcome_sort_key)[0]
    return {
        "campaign_type": record.get("campaign_type", ""),
        "label": record.get("label", ""),
        "monitoring_state": record.get("monitoring_state", ""),
        "latest_target": record.get("latest_target", ""),
        "summary": record.get("follow_up_recommendation", ""),
        "pressure_effect": record.get("pressure_effect", "insufficient-evidence"),
    }


def _summary_line(outcomes: list[dict[str, Any]]) -> str:
    step = _next_monitoring_step(outcomes)
    state = str(step.get("monitoring_state") or "stay-local")
    if state == "stay-local":
        return "No recent Action Sync apply needs post-apply monitoring yet, so the local weekly story can stay local."
    if state == "holding-clean":
        return f"Post-apply monitoring is quieting: {step.get('label', 'Campaign')} is holding clean and can stay under normal monitoring."
    return str(step.get("summary") or "Post-apply monitoring needs attention.")


def _queue_post_apply_lines(
    queue: list[dict[str, Any]],
    outcomes_by_campaign: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for item in queue:
        mapped = dict(item)
        campaign_type = str(mapped.get("suggested_campaign") or "").strip()
        outcome = outcomes_by_campaign.get(campaign_type, {})
        state = str(outcome.get("monitoring_state") or "no-recent-apply")
        mapped["post_apply_state"] = state
        mapped["post_apply_summary"] = str(outcome.get("summary") or "No post-apply monitoring is surfaced for this item yet.")
        mapped["post_apply_line"] = f"Post-Apply Monitoring: {mapped['post_apply_summary']}"
        enriched.append(mapped)
    return enriched


def build_action_sync_outcomes_bundle(
    report_data: dict[str, Any],
    queue: list[dict[str, Any]],
    *,
    recent_runs: list[dict[str, Any]],
    recent_campaign_runs: list[dict[str, Any]],
    recent_action_runs: list[dict[str, Any]],
    recent_campaign_history: list[dict[str, Any]],
    recent_drift_events: list[dict[str, Any]],
    recent_rollback_runs: list[dict[str, Any]],
) -> dict[str, Any]:
    run_snapshots = _run_snapshots(report_data, recent_runs)
    run_ids = {str(item.get("run_id") or "") for item in run_snapshots}
    campaign_runs = _campaign_run_events(report_data, recent_campaign_runs)
    action_runs = _current_action_runs(report_data) + list(recent_action_runs)
    campaign_history = _current_campaign_history(report_data) + list(recent_campaign_history)
    drift_events = _current_drift_events(report_data) + list(recent_drift_events)
    rollback_runs = _current_rollback_runs(report_data) + list(recent_rollback_runs)
    history_is_thin = len(run_snapshots) < FOLLOW_UP_WINDOW_RUNS

    outcomes: list[dict[str, Any]] = []
    outcomes_by_campaign: dict[str, dict[str, Any]] = {}
    for campaign_type in CAMPAIGN_DISPLAY_ORDER:
        latest_event = _latest_event(
            campaign_runs,
            run_ids,
            campaign_type,
            allow_thin_history_fallback=history_is_thin,
        )
        latest_apply = _latest_apply_event(
            campaign_runs,
            run_ids,
            campaign_type,
            allow_thin_history_fallback=history_is_thin,
        )
        latest_run_mode = str((latest_event or {}).get("mode") or "preview")
        latest_target = str((latest_apply or latest_event or {}).get("writeback_target") or "none")
        recent_apply_count = sum(
            1
            for event in campaign_runs
            if str(event.get("campaign_type") or "") == campaign_type
            and str(event.get("mode") or "") == "apply"
            and str(event.get("run_id") or "") in run_ids
        )
        if recent_apply_count <= 0 and history_is_thin and latest_apply:
            recent_apply_count = 1
        apply_run_id = str(latest_apply.get("run_id") or "")
        apply_snapshot, post_runs = _monitoring_run_slices(run_snapshots, apply_run_id) if apply_run_id else ({}, [])
        action_rows = _action_rows_for_run(action_runs, apply_run_id, campaign_type) if apply_run_id else []
        top_repos = _top_repos(action_rows)
        action_ids = {
            str(row.get("action_id") or "")
            for row in action_rows
            if str(row.get("action_id") or "")
        } or {
            str(action_id)
            for action_id in (latest_apply.get("generated_action_ids") or [])
            if str(action_id)
        }
        monitored_repo_count = len({str(row.get("repo_id") or "") for row in action_rows if str(row.get("repo_id") or "")})
        if not monitored_repo_count:
            monitored_repo_count = len(top_repos)
        if not top_repos:
            top_repos = [
                str(repo)
                for repo in (latest_apply.get("generated_action_ids") or [])[:3]
                if str(repo)
            ]
        drift_state = (
            "returned"
            if latest_apply and _campaign_drift_returned(
                campaign_type,
                post_runs,
                drift_events,
                str(latest_apply.get("generated_at") or ""),
                action_ids,
            )
            else ("clear" if latest_apply else "insufficient-evidence")
        )
        reopen_state = (
            "reopened"
            if latest_apply and _campaign_reopened(
                campaign_type,
                campaign_history,
                str(latest_apply.get("generated_at") or ""),
            )
            else ("none" if latest_apply else "insufficient-evidence")
        )
        rollback_state = _rollback_state(action_rows, rollback_runs, apply_run_id)
        pressure_effect = _pressure_effect(apply_snapshot, post_runs)
        monitoring_state = _monitoring_state(
            recent_apply_count=recent_apply_count,
            drift_state=drift_state,
            reopen_state=reopen_state,
            rollback_state=rollback_state,
            has_apply_snapshot=bool(apply_snapshot),
            post_run_count=len(post_runs),
            pressure_effect=pressure_effect,
        )
        record = {
            "campaign_type": campaign_type,
            "label": str(CAMPAIGN_DEFINITIONS[campaign_type]["label"]),
            "latest_target": latest_target,
            "latest_run_mode": latest_run_mode,
            "recent_apply_count": recent_apply_count,
            "monitored_repo_count": monitored_repo_count,
            "monitoring_state": monitoring_state,
            "pressure_effect": pressure_effect,
            "drift_state": drift_state,
            "reopen_state": reopen_state,
            "rollback_state": rollback_state,
            "top_repos": top_repos,
        }
        record["follow_up_recommendation"] = _follow_up_recommendation(record)
        record["summary"] = _summary(record)
        outcomes.append(record)
        outcomes_by_campaign[campaign_type] = record

    next_step = _next_monitoring_step(outcomes)
    ordered = sorted(outcomes, key=_outcome_sort_key)
    return {
        "action_sync_outcomes": outcomes,
        "campaign_outcomes_summary": {
            "summary": _summary_line(outcomes),
            "counts": {
                state: sum(1 for record in outcomes if record.get("monitoring_state") == state)
                for state in (
                    "no-recent-apply",
                    "monitor-now",
                    "holding-clean",
                    "drift-returned",
                    "reopened",
                    "rollback-watch",
                    "insufficient-evidence",
                )
            },
        },
        "next_monitoring_step": next_step,
        "top_monitor_now_campaigns": [record for record in ordered if record.get("monitoring_state") == "monitor-now"][:3],
        "top_holding_clean_campaigns": [record for record in ordered if record.get("monitoring_state") == "holding-clean"][:3],
        "top_reopened_campaigns": [record for record in ordered if record.get("monitoring_state") == "reopened"][:3],
        "top_drift_returned_campaigns": [record for record in ordered if record.get("monitoring_state") == "drift-returned"][:3],
        "operator_queue": _queue_post_apply_lines(queue, outcomes_by_campaign),
    }


def load_action_sync_outcomes_bundle(output_dir: Any, report_data: dict[str, Any], queue: list[dict[str, Any]]) -> dict[str, Any]:
    username = str(report_data.get("username") or "")
    return build_action_sync_outcomes_bundle(
        report_data,
        queue,
        recent_runs=load_latest_audit_runs(output_dir, username, limit=FOLLOW_UP_WINDOW_RUNS),
        recent_campaign_runs=load_recent_campaign_runs(output_dir, username, limit=30),
        recent_action_runs=load_recent_action_runs(output_dir, username, limit=400),
        recent_campaign_history=load_recent_campaign_history(output_dir, username, limit=200),
        recent_drift_events=load_recent_campaign_drift_events(output_dir, username, limit=200),
        recent_rollback_runs=load_recent_rollback_runs(output_dir, username, limit=200),
    )
