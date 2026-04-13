from __future__ import annotations

from pathlib import Path
from typing import Any

from src.history import load_repo_score_history
from src.warehouse import (
    load_campaign_outcomes,
    load_latest_audit_runs,
    load_operator_state_history,
    load_recent_action_runs,
    load_recent_implementation_hotspots,
    load_recent_operator_evidence,
    load_recent_repo_scorecards,
    load_review_history,
)

HISTORY_LOOKBACK_RUNS = 20
DISPLAY_LOOKBACK_RUNS = 10
MIN_HISTORICAL_RUNS = 4

STATUS_PRIORITY = {
    "relapsing": 0,
    "persistent-pressure": 1,
    "improving-after-intervention": 2,
    "holding-steady": 3,
    "quiet": 4,
    "insufficient-evidence": 5,
}


def _copy_mapping(value: Any) -> dict[str, Any]:
    return dict(value or {})


def _current_run_id(report_data: dict[str, Any]) -> str:
    generated_at = str(report_data.get("generated_at") or "")
    username = str(report_data.get("username") or "current")
    return f"{username}:{generated_at}" if generated_at else f"{username}:current"


def _current_queue_snapshot(report_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": _current_run_id(report_data),
        "generated_at": str(report_data.get("generated_at") or ""),
        "operator_summary": _copy_mapping(report_data.get("operator_summary")),
        "operator_queue": list(report_data.get("operator_queue") or []),
    }


def _queue_pressure_weight(item: dict[str, Any]) -> float:
    lane = str(item.get("lane") or "")
    if lane == "blocked":
        return 2.0
    if lane == "urgent":
        return 1.5
    if lane == "ready":
        return 1.0
    if lane == "deferred":
        return 0.5
    return 0.0


def _dedupe_snapshots(current: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    snapshots = [current]
    seen = {str(current.get("run_id") or "")}
    for row in rows:
        run_id = str(row.get("run_id") or "")
        if run_id and run_id not in seen:
            snapshots.append(dict(row))
            seen.add(run_id)
        if len(snapshots) >= HISTORY_LOOKBACK_RUNS:
            break
    snapshots.sort(key=lambda item: str(item.get("generated_at") or ""))
    return snapshots[-HISTORY_LOOKBACK_RUNS:]


def _pressure_series(repo: str, snapshots: list[dict[str, Any]]) -> list[float]:
    series: list[float] = []
    for snapshot in snapshots:
        pressure = 0.0
        for item in snapshot.get("operator_queue") or []:
            repo_name = str(item.get("repo") or item.get("repo_name") or "").strip()
            if repo_name == repo:
                pressure += _queue_pressure_weight(item)
        series.append(pressure)
    return series


def _trend_from_series(series: list[float]) -> str:
    if len(series) < MIN_HISTORICAL_RUNS:
        return "insufficient-evidence"
    split = max(1, len(series) // 2)
    early = sum(series[:split]) / max(split, 1)
    late = sum(series[split:]) / max(len(series) - split, 1)
    delta = late - early
    if delta <= -0.35:
        return "improving"
    if delta >= 0.35:
        return "worsening"
    return "flat"


def _distinct_repo_names(report_data: dict[str, Any], sources: dict[str, list[dict[str, Any]]]) -> list[str]:
    names: list[str] = []
    for audit in report_data.get("audits") or []:
        repo = str(_copy_mapping(audit.get("metadata")).get("name") or "").strip()
        if repo and repo not in names:
            names.append(repo)
    for item in report_data.get("operator_queue") or []:
        repo = str(item.get("repo") or item.get("repo_name") or "").strip()
        if repo and repo not in names:
            names.append(repo)
    for key in ("scorecards", "hotspots", "actions"):
        for row in sources.get(key, []):
            repo = str(row.get("repo") or row.get("repo_name") or row.get("repo_id") or row.get("repo_full_name") or "").strip()
            if "/" in repo:
                repo = repo.rsplit("/", 1)[-1]
            if repo and repo not in names:
                names.append(repo)
    return names


def _current_audits_by_repo(report_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    audits: dict[str, dict[str, Any]] = {}
    for audit in report_data.get("audits") or []:
        repo = str(_copy_mapping(audit.get("metadata")).get("name") or "").strip()
        if repo:
            audits[repo] = audit
    return audits


def _repo_score_series(
    repo: str,
    audit_by_repo: dict[str, dict[str, Any]],
    score_rows: list[dict[str, Any]],
    history_output_dir: Any,
) -> list[float]:
    rows = sorted(
        [row for row in score_rows if str(row.get("repo") or row.get("repo_name") or "") == repo],
        key=lambda item: str(item.get("generated_at") or ""),
    )
    if rows:
        return [float(row.get("score", 0.0) or 0.0) for row in rows][-DISPLAY_LOOKBACK_RUNS:]
    if history_output_dir:
        history = load_repo_score_history(history_output_dir, max_runs=DISPLAY_LOOKBACK_RUNS)
        if repo in history:
            return [float(value or 0.0) for value in history[repo]][-DISPLAY_LOOKBACK_RUNS:]
    scorecard = _copy_mapping((audit_by_repo.get(repo) or {}).get("scorecard"))
    if scorecard:
        return [float(scorecard.get("score", 0.0) or 0.0)]
    return []


def _scorecard_trend(scores: list[float]) -> str:
    if len(scores) < MIN_HISTORICAL_RUNS:
        return "insufficient-evidence"
    delta = scores[-1] - scores[0]
    if delta >= 0.05:
        return "improving"
    if delta <= -0.05:
        return "worsening"
    return "flat"


def _hotspot_persistence(repo: str, hotspot_rows: list[dict[str, Any]], run_count: int) -> str:
    if run_count < MIN_HISTORICAL_RUNS:
        return "insufficient-evidence"
    repo_rows = [
        row for row in hotspot_rows
        if str(row.get("repo") or row.get("repo_name") or "").strip() == repo
    ]
    if not repo_rows:
        return "quiet"
    run_ids = {str(row.get("run_id") or "") for row in repo_rows if str(row.get("run_id") or "")}
    if len(run_ids) >= max(2, run_count // 2):
        latest_run = max(run_ids)
        if any(str(row.get("run_id") or "") == latest_run for row in repo_rows):
            return "persistent"
    return "changing"


def _recent_interventions(repo: str, action_rows: list[dict[str, Any]]) -> tuple[int, str]:
    repo_rows = []
    for row in action_rows:
        names = {
            str(row.get("repo") or "").split("/")[-1],
            str(row.get("repo_id") or "").split("/")[-1],
            str(row.get("repo_full_name") or "").split("/")[-1],
        }
        if repo in names:
            repo_rows.append(row)
    if not repo_rows:
        return 0, ""
    ordered = sorted(repo_rows, key=lambda item: str(item.get("generated_at") or ""), reverse=True)
    run_ids = {str(row.get("run_id") or "") for row in repo_rows if str(row.get("run_id") or "")}
    return len(run_ids), str(ordered[0].get("generated_at") or "")


def _has_reopened_action(repo: str, action_rows: list[dict[str, Any]]) -> bool:
    for row in action_rows:
        names = {
            str(row.get("repo") or "").split("/")[-1],
            str(row.get("repo_id") or "").split("/")[-1],
            str(row.get("repo_full_name") or "").split("/")[-1],
        }
        if repo in names and row.get("reopened_at"):
            return True
    return False


def _has_reopened_operator_event(repo: str, operator_evidence: dict[str, Any]) -> bool:
    for row in operator_evidence.get("events") or []:
        repo_name = str(row.get("repo") or "").strip()
        outcome = str(row.get("outcome") or "").strip()
        if repo_name == repo and outcome == "reopened":
            return True
    return False


def _campaign_follow_through(repo: str, action_rows: list[dict[str, Any]], outcome_rows: list[dict[str, Any]]) -> str:
    repo_campaigns: set[str] = set()
    for row in action_rows:
        names = {
            str(row.get("repo") or "").split("/")[-1],
            str(row.get("repo_id") or "").split("/")[-1],
            str(row.get("repo_full_name") or "").split("/")[-1],
        }
        if repo in names:
            repo_campaigns.add(str(row.get("campaign_type") or ""))
    repo_campaigns.discard("")
    if not repo_campaigns:
        return "not-applicable"
    relevant = [row for row in outcome_rows if str(row.get("campaign_type") or "") in repo_campaigns]
    if not relevant:
        return "insufficient-evidence"
    states = {str(row.get("monitoring_state") or "") for row in relevant}
    if states & {"drift-returned", "reopened"}:
        return "relapsing"
    if "holding-clean" in states and not (states & {"rollback-watch", "monitor-now"}):
        return "helping"
    if states:
        return "mixed"
    return "insufficient-evidence"


def _latest_tier_and_score(repo: str, audit_by_repo: dict[str, dict[str, Any]]) -> tuple[str, float]:
    audit = audit_by_repo.get(repo) or {}
    return (
        str(audit.get("completeness_tier") or ""),
        float(audit.get("overall_score", 0.0) or 0.0),
    )


def _status_for_repo(
    *,
    run_count: int,
    pressure_trend: str,
    current_pressure: bool,
    recurring_pressure_count: int,
    hotspot_persistence: str,
    scorecard_trend: str,
    campaign_follow_through: str,
    recent_intervention_count: int,
    reopened: bool,
) -> str:
    if run_count < MIN_HISTORICAL_RUNS:
        return "insufficient-evidence"
    if campaign_follow_through == "relapsing" or reopened or (
        recent_intervention_count > 0 and pressure_trend == "worsening"
    ):
        return "relapsing"
    if recurring_pressure_count >= max(3, run_count // 2) and (
        current_pressure or hotspot_persistence == "persistent" or scorecard_trend in {"flat", "worsening"}
    ):
        return "persistent-pressure"
    if recent_intervention_count > 0 and (
        pressure_trend == "improving"
        or scorecard_trend == "improving"
        or hotspot_persistence in {"changing", "quiet"}
        or campaign_follow_through == "helping"
    ):
        return "improving-after-intervention"
    if recent_intervention_count > 0 and not current_pressure and pressure_trend in {"flat", "improving"}:
        return "holding-steady"
    if not current_pressure and hotspot_persistence == "quiet":
        return "quiet"
    return "insufficient-evidence"


def _summary(record: dict[str, Any]) -> str:
    repo = str(record.get("repo") or "Repo")
    status = str(record.get("historical_intelligence_status") or "insufficient-evidence")
    if status == "relapsing":
        return f"{repo} is relapsing after intervention: recent pressure or follow-through has turned back upward and needs a closer historical read."
    if status == "persistent-pressure":
        return f"{repo} keeps consuming attention without durable quieting: recurring pressure and hotspot persistence are still stacking up."
    if status == "improving-after-intervention":
        return f"{repo} is improving after intervention: recent pressure, maturity, or hotspot signals are moving in the right direction without relapse."
    if status == "holding-steady":
        return f"{repo} looks stable after earlier pressure: the repo is holding steady enough to monitor instead of re-escalating."
    if status == "quiet":
        return f"{repo} is currently quiet and does not need a historical escalation story right now."
    return f"{repo} does not have enough cross-run evidence yet to support a confident historical judgment."


def _ledger_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {
        status: sum(1 for record in records if record.get("historical_intelligence_status") == status)
        for status in (
            "relapsing",
            "persistent-pressure",
            "improving-after-intervention",
            "holding-steady",
            "quiet",
            "insufficient-evidence",
        )
    }
    return {
        "summary": (
            f"{counts['relapsing']} repo(s) are relapsing, {counts['persistent-pressure']} show persistent pressure, "
            f"{counts['improving-after-intervention']} are improving after intervention, and {counts['holding-steady']} are holding steady."
        ) if records else "Historical portfolio intelligence is still empty because no repo-level evidence is available yet.",
        "counts": counts,
    }


def _next_focus(records: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(
        records,
        key=lambda item: (
            STATUS_PRIORITY.get(str(item.get("historical_intelligence_status") or "insufficient-evidence"), 99),
            -int(item.get("recent_intervention_count", 0) or 0),
            str(item.get("repo") or ""),
        ),
    )
    for record in ordered:
        status = str(record.get("historical_intelligence_status") or "")
        repo = str(record.get("repo") or "")
        if status == "relapsing":
            payload = dict(record)
            payload["summary"] = f"Read {repo} first: the historical story points to relapse after earlier intervention."
            return payload
        if status == "persistent-pressure":
            payload = dict(record)
            payload["summary"] = f"Read {repo} next: it keeps resurfacing and still lacks durable quieting."
            return payload
        if status == "improving-after-intervention":
            payload = dict(record)
            payload["summary"] = f"Read {repo} next: it is the clearest current example of improvement after intervention."
            return payload
        if status == "holding-steady":
            payload = dict(record)
            payload["summary"] = f"Read {repo} next if you want proof that earlier pressure is now holding steady."
            return payload
    return {"summary": "Stay local for now; no repo has enough cross-run intervention evidence to demand a historical follow-up read yet."}


def build_intervention_ledger_bundle(
    report_data: dict[str, Any],
    operator_queue: list[dict[str, Any]] | None = None,
    *,
    recent_runs: list[dict[str, Any]] | None = None,
    operator_history: list[dict[str, Any]] | None = None,
    operator_evidence: dict[str, Any] | None = None,
    review_history: list[dict[str, Any]] | None = None,
    campaign_outcomes: list[dict[str, Any]] | None = None,
    recent_action_runs: list[dict[str, Any]] | None = None,
    repo_scorecard_history: list[dict[str, Any]] | None = None,
    implementation_hotspot_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    data = dict(report_data)
    queue = list(operator_queue if operator_queue is not None else data.get("operator_queue") or [])
    output_dir = data.get("output_dir")
    username = str(data.get("username") or "")

    recent_runs = list(recent_runs or (load_latest_audit_runs(output_dir, username, limit=HISTORY_LOOKBACK_RUNS) if output_dir else []))
    operator_history = list(operator_history or (load_operator_state_history(output_dir, username, limit=HISTORY_LOOKBACK_RUNS) if output_dir else []))
    operator_evidence = dict(operator_evidence or (load_recent_operator_evidence(output_dir, username, snapshot_limit=DISPLAY_LOOKBACK_RUNS, event_limit=30) if output_dir else {"history": [], "events": []}))
    review_history = list(review_history or (load_review_history(output_dir, username, limit=DISPLAY_LOOKBACK_RUNS) if output_dir else []))
    campaign_outcomes = list(campaign_outcomes or (load_campaign_outcomes(output_dir, username, limit=60) if output_dir else []))
    recent_action_runs = list(recent_action_runs or (load_recent_action_runs(output_dir, username, limit=400) if output_dir else []))
    repo_scorecard_history = list(repo_scorecard_history or (load_recent_repo_scorecards(output_dir, username, limit=200) if output_dir else []))
    implementation_hotspot_history = list(implementation_hotspot_history or (load_recent_implementation_hotspots(output_dir, username, limit=400) if output_dir else []))
    _ = review_history

    snapshots = _dedupe_snapshots(_current_queue_snapshot(data), recent_runs)
    if operator_history:
        seen = {str(item.get("run_id") or "") for item in snapshots}
        for item in operator_history:
            run_id = str(item.get("run_id") or "")
            if run_id and run_id not in seen:
                snapshots.append(dict(item))
                seen.add(run_id)
        snapshots.sort(key=lambda item: str(item.get("generated_at") or ""))
        snapshots = snapshots[-HISTORY_LOOKBACK_RUNS:]

    audit_by_repo = _current_audits_by_repo(data)
    repo_names = _distinct_repo_names(
        data,
        {
            "scorecards": repo_scorecard_history,
            "hotspots": implementation_hotspot_history,
            "actions": recent_action_runs,
        },
    )
    history_output_dir = output_dir / "history" if output_dir else None

    records: list[dict[str, Any]] = []
    for repo in repo_names:
        pressure_series = _pressure_series(repo, snapshots)
        pressure_trend = _trend_from_series(pressure_series)
        current_pressure = bool(pressure_series and pressure_series[-1] > 0)
        recurring_pressure_count = sum(1 for value in pressure_series if value > 0)
        score_series = _repo_score_series(repo, audit_by_repo, repo_scorecard_history, history_output_dir)
        scorecard_trend = _scorecard_trend(score_series)
        hotspot_persistence = _hotspot_persistence(repo, implementation_hotspot_history, len(snapshots))
        campaign_follow_through = _campaign_follow_through(repo, recent_action_runs, campaign_outcomes)
        recent_intervention_count, last_intervention = _recent_interventions(repo, recent_action_runs)
        reopened = _has_reopened_action(repo, recent_action_runs) or _has_reopened_operator_event(
            repo, operator_evidence
        )
        latest_tier, latest_score = _latest_tier_and_score(repo, audit_by_repo)
        record = {
            "repo": repo,
            "latest_tier": latest_tier,
            "latest_score": round(latest_score, 3),
            "recent_intervention_count": recent_intervention_count,
            "last_intervention": last_intervention,
            "pressure_trend": pressure_trend,
            "hotspot_persistence": hotspot_persistence,
            "scorecard_trend": scorecard_trend,
            "campaign_follow_through": campaign_follow_through,
            "historical_intelligence_status": _status_for_repo(
                run_count=len(snapshots),
                pressure_trend=pressure_trend,
                current_pressure=current_pressure,
                recurring_pressure_count=recurring_pressure_count,
                hotspot_persistence=hotspot_persistence,
                scorecard_trend=scorecard_trend,
                campaign_follow_through=campaign_follow_through,
                recent_intervention_count=recent_intervention_count,
                reopened=reopened,
            ),
        }
        record["summary"] = _summary(record)
        records.append(record)

    records.sort(
        key=lambda item: (
            STATUS_PRIORITY.get(str(item.get("historical_intelligence_status") or "insufficient-evidence"), 99),
            -int(item.get("recent_intervention_count", 0) or 0),
            str(item.get("repo") or ""),
        )
    )

    grouped = {
        "top_relapsing_repos": [item for item in records if item.get("historical_intelligence_status") == "relapsing"][:5],
        "top_persistent_pressure_repos": [item for item in records if item.get("historical_intelligence_status") == "persistent-pressure"][:5],
        "top_improving_repos": [item for item in records if item.get("historical_intelligence_status") == "improving-after-intervention"][:5],
        "top_holding_repos": [item for item in records if item.get("historical_intelligence_status") == "holding-steady"][:5],
    }

    queue_by_repo = {str(item.get("repo") or item.get("repo_name") or ""): item for item in queue}
    for record in records:
        queue_item = queue_by_repo.get(str(record.get("repo") or ""))
        if queue_item is not None:
            queue_item["historical_intelligence_status"] = record["historical_intelligence_status"]
            queue_item["historical_intelligence_summary"] = record["summary"]
            queue_item["historical_intelligence_line"] = (
                f"Historical Portfolio Intelligence: {record['summary']}"
            )

    return {
        "operator_queue": queue,
        "historical_portfolio_intelligence": records,
        "intervention_ledger_summary": _ledger_summary(records),
        "next_historical_focus": _next_focus(records),
        **grouped,
    }


def load_intervention_ledger_bundle(
    output_dir: Path | None,
    report_data: dict[str, Any],
    operator_queue: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload = dict(report_data)
    if output_dir is not None:
        payload["output_dir"] = output_dir
    return build_intervention_ledger_bundle(payload, operator_queue)
