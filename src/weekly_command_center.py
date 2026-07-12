from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.portfolio_automation import select_automation_candidates
from src.portfolio_decision_queue import build_decision_queue, summarize_decision_queue
from src.portfolio_truth_types import display_activity_status, truth_latest_path
from src.portfolio_truth_trends import (
    build_verdict_transition_ledger,
    render_movement_summary,
)
from src.report_enrichment import build_weekly_review_pack

CONTRACT_VERSION = "weekly_command_center_digest_v1"
AUTHORITY_CAP = "bounded-automation"
MAX_PATH_ATTENTION_ITEMS = 5
MAX_REPO_BRIEFINGS = 3
MAX_RISK_ATTENTION_ITEMS = 5
MAX_SECURITY_ATTENTION_ITEMS = 5


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return {}


def _parse_datetime(value: Any) -> datetime | None:
    text = _safe_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _source_freshness(
    report_data: dict[str, Any], portfolio_truth: dict[str, Any]
) -> dict[str, Any]:
    report_generated_at = _parse_datetime(report_data.get("generated_at"))
    truth_generated_at = _parse_datetime(portfolio_truth.get("generated_at"))
    status = "current"
    summary = "Control-center source report and portfolio truth are aligned enough to read together."
    if (
        truth_generated_at
        and report_generated_at
        and truth_generated_at > report_generated_at
    ):
        status = "portfolio-truth-newer"
        summary = (
            "Portfolio truth is newer than the audit report feeding the control-center queue; "
            "refresh the audit report before acting on queue pressure."
        )
    elif truth_generated_at and not report_generated_at:
        status = "unknown-report-age"
        summary = (
            "Portfolio truth is available, but the audit report timestamp is missing; "
            "refresh the audit report before treating queue pressure as current."
        )
    return {
        "status": status,
        "summary": summary,
        "report_generated_at": report_generated_at.isoformat()
        if report_generated_at
        else "",
        "portfolio_truth_generated_at": truth_generated_at.isoformat()
        if truth_generated_at
        else "",
    }


def _weekly_pack_source(
    report_data: dict[str, Any], snapshot: dict[str, Any]
) -> dict[str, Any]:
    source = dict(report_data)
    snapshot_summary = _mapping(snapshot.get("operator_summary"))
    if snapshot_summary:
        source["operator_summary"] = snapshot_summary
    if "operator_queue" in snapshot:
        source["operator_queue"] = list(snapshot.get("operator_queue") or [])
    return source


def _operator_primary_repo(
    operator_summary: dict[str, Any], operator_queue: list[dict[str, Any]]
) -> str:
    primary_target = _mapping(operator_summary.get("primary_target"))
    repo = _safe_text(primary_target.get("repo"))
    if repo:
        return repo
    if operator_queue:
        return _safe_text(_mapping(operator_queue[0]).get("repo"))
    return ""


def _operator_decision(
    operator_summary: dict[str, Any], operator_queue: list[dict[str, Any]]
) -> str:
    decision = _safe_text(operator_summary.get("what_to_do_next"))
    repo = _operator_primary_repo(operator_summary, operator_queue)
    if decision and repo and repo.lower() not in decision.lower():
        return f"{decision} Start with {repo}."
    return decision


def latest_portfolio_truth_path(output_dir: Path) -> Path | None:
    latest = truth_latest_path(output_dir)
    return latest if latest.is_file() else None


def load_latest_portfolio_truth(output_dir: Path) -> tuple[Path | None, dict[str, Any]]:
    path = latest_portfolio_truth_path(output_dir)
    if not path:
        return None, {}
    return path, json.loads(path.read_text())


def build_weekly_command_center_digest(
    report_data: dict[str, Any],
    snapshot: dict[str, Any],
    *,
    diff_data: dict[str, Any] | None = None,
    portfolio_truth: dict[str, Any] | None = None,
    portfolio_truth_history_dir: Path | None = None,
    portfolio_truth_reference: str = "",
    control_center_reference: str = "",
    report_reference: str = "",
    generated_at: str = "",
) -> dict[str, Any]:
    weekly_pack = build_weekly_review_pack(
        _weekly_pack_source(report_data, snapshot), diff_data
    )
    weekly_story = _mapping(weekly_pack.get("weekly_story_v1"))
    operator_summary = _mapping(snapshot.get("operator_summary"))
    operator_queue = list(snapshot.get("operator_queue") or [])
    repo_briefings = list(weekly_pack.get("repo_briefings") or [])
    decision_quality = _mapping(operator_summary.get("decision_quality_v1"))
    decision_quality_status = (
        _safe_text(decision_quality.get("decision_quality_status"))
        or "insufficient-data"
    )
    truth = portfolio_truth or {}
    freshness = _source_freshness(report_data, truth)
    source_is_stale = freshness["status"] != "current"
    truth_summary = _build_truth_summary(truth)
    movement = (
        build_verdict_transition_ledger(
            portfolio_truth_history_dir,
            max_snapshots=8,
            current_snapshot=truth,
            current_path=Path(portfolio_truth_reference)
            if portfolio_truth_reference
            else None,
        )
        if portfolio_truth_history_dir
        else build_verdict_transition_ledger(max_snapshots=0)
    )
    movement["summary_text"] = render_movement_summary(movement)
    decision_queue = build_decision_queue(truth)
    decision_queue_summary = summarize_decision_queue(decision_queue)
    operator_decision = _operator_decision(operator_summary, operator_queue)
    operator_why = _safe_text(operator_summary.get("trend_summary")) or _safe_text(
        operator_summary.get("why_it_matters")
    )
    queue_pressure_summary = operator_why or _safe_text(
        weekly_pack.get("queue_pressure_summary")
    )

    headline = (
        "Refresh the audit report before acting on control-center queue pressure."
        if source_is_stale
        else _safe_text(operator_summary.get("headline"))
        or _safe_text(weekly_story.get("headline"))
        or "No weekly headline is recorded yet."
    )
    decision = (
        "Refresh the audit report, then rerun the read-only control center before choosing a repo action."
        if source_is_stale
        else operator_decision
        or _safe_text(weekly_story.get("decision"))
        or "Continue the normal operator review loop."
    )
    why_this_week = (
        freshness["summary"]
        if source_is_stale
        else operator_why
        or _safe_text(weekly_story.get("why_this_week"))
        or "No weekly rationale is recorded yet."
    )
    section_digest = (
        [
            {
                "id": "source-freshness",
                "label": "Source Freshness",
                "state": "refresh-needed",
                "headline": freshness["summary"],
                "next_step": (
                    "Refresh the audit report, then rerun the read-only control center."
                ),
                "reason_codes": [freshness["status"]],
            }
        ]
        if source_is_stale
        else _build_section_digest(
            weekly_story,
            operator_decision=operator_decision,
            operator_why=operator_why,
        )
    )
    top_repo_briefings = [] if source_is_stale else repo_briefings[:MAX_REPO_BRIEFINGS]

    return {
        "contract_version": CONTRACT_VERSION,
        "authority_cap": AUTHORITY_CAP,
        "workbook_first": True,
        "generated_at": generated_at or _safe_text(report_data.get("generated_at")),
        "username": _safe_text(report_data.get("username")) or "unknown",
        "report_reference": report_reference
        or _safe_text(report_data.get("latest_report_path")),
        "control_center_reference": control_center_reference,
        "portfolio_truth_reference": portfolio_truth_reference,
        "source_freshness": freshness,
        "headline": headline,
        "decision": decision,
        "why_this_week": why_this_week,
        "next_step": _safe_text(weekly_story.get("next_step"))
        or "Open the workbook first, then use the read-only control center.",
        "queue_pressure_summary": freshness["summary"]
        if source_is_stale
        else queue_pressure_summary,
        "operating_paths_summary": _safe_text(
            weekly_pack.get("operating_paths_summary")
        ),
        "decision_quality": {
            "status": decision_quality_status,
            "human_skepticism_required": bool(
                decision_quality.get("human_skepticism_required", True)
            ),
            "summary": _safe_text(
                decision_quality.get("recommendation_quality_summary")
            )
            or _safe_text(decision_quality.get("confidence_calibration_summary"))
            or "Decision quality is not available yet.",
            "authority_cap": _safe_text(decision_quality.get("authority_cap"))
            or AUTHORITY_CAP,
        },
        "portfolio_truth": {**truth_summary, **decision_queue_summary},
        "movement": movement,
        "decision_queue": decision_queue,
        "path_attention": _build_path_attention_items(truth),
        "automation_candidates": [
            candidate.to_dict()
            for candidate in select_automation_candidates(
                truth,
                decision_quality_status=decision_quality_status,
            )
        ],
        "risk_posture": {
            "elevated_count": truth_summary.get("elevated_risk_count", 0),
            "risk_tier_counts": truth_summary.get("risk_tier_counts", {}),
            "top_elevated": _build_risk_attention_items(truth),
        },
        "security_posture": {
            **_build_security_summary(truth),
            "top_alerts": _build_security_attention_items(truth),
        },
        "section_digest": section_digest,
        "top_repo_briefings": [
            {
                "repo": _safe_text(item.get("repo")) or "Repo",
                "why_it_matters": _safe_text(item.get("why_it_matters_line"))
                or "No repo rationale is recorded yet.",
                "next_step": _safe_text(item.get("what_to_do_next_line"))
                or "No repo next step is recorded yet.",
                "operating_path_line": _safe_text(item.get("operating_path_line")),
                "operator_focus_line": _safe_text(item.get("operator_focus_line")),
            }
            for item in top_repo_briefings
        ],
        "report_only_guardrail": (
            "This digest is descriptive only. It may highlight path, trust, and pressure, "
            "but it does not widen approval, execution, or automation authority."
        ),
    }


def render_weekly_command_center_markdown(digest: dict[str, Any]) -> str:
    decision_quality = _mapping(digest.get("decision_quality"))
    source_freshness = _mapping(digest.get("source_freshness"))
    portfolio_truth = _mapping(digest.get("portfolio_truth"))
    risk_posture = _mapping(digest.get("risk_posture"))
    tier_counts = _mapping(risk_posture.get("risk_tier_counts"))
    security_posture = _mapping(digest.get("security_posture"))
    movement = _mapping(digest.get("movement"))
    lines = [
        f"# Weekly Command Center: {_safe_text(digest.get('username')) or 'unknown'}",
        "",
        f"- Generated: `{_safe_text(digest.get('generated_at'))}`",
        f"- Contract: `{_safe_text(digest.get('contract_version'))}`",
        f"- Authority Cap: `{_safe_text(digest.get('authority_cap'))}`",
        f"- Headline: {_safe_text(digest.get('headline'))}",
        f"- Decision: {_safe_text(digest.get('decision'))}",
        f"- Why This Week: {_safe_text(digest.get('why_this_week'))}",
        f"- Next Step: {_safe_text(digest.get('next_step'))}",
        f"- Source Freshness: `{_safe_text(source_freshness.get('status')) or 'unknown'}` — {_safe_text(source_freshness.get('summary')) or 'No source freshness summary is recorded yet.'}",
        f"- Decision Quality: `{_safe_text(decision_quality.get('status'))}` — {_safe_text(decision_quality.get('summary'))}",
        f"- Operating Paths: {_safe_text(digest.get('operating_paths_summary')) or 'No operating-path summary is recorded yet.'}",
        f"- Portfolio Truth: {portfolio_truth.get('project_count', 0)} projects, {portfolio_truth.get('active_project_count', 0)} active registry entries, {portfolio_truth.get('default_attention_count', 0)} default attention, {portfolio_truth.get('decision_queue_count', 0)} decision queue",
        f"- Risk Posture: {risk_posture.get('elevated_count', 0)} elevated, {tier_counts.get('moderate', 0)} moderate, {tier_counts.get('baseline', 0)} baseline",
        f"- Security Posture: {security_posture.get('scanned_count', 0)} scanned, {security_posture.get('repos_with_open_high_critical', 0)} with open high/critical Dependabot alerts ({security_posture.get('total_open_critical', 0)} critical, {security_posture.get('total_open_high', 0)} high)",
        "",
        "## Decision Queue",
    ]

    decision_queue = list(digest.get("decision_queue") or [])
    if not decision_queue:
        lines.append("- No portfolio decisions clear the current evidence bar.")
    else:
        for item in decision_queue:
            lines.append(
                f"- **{item['project']}** [{item['decision_type']}]: "
                f"{item['why_now']} Next: {item['recommended_action']}"
            )

    lines.extend(
        [
            "",
            "## Path Attention",
        ]
    )

    path_attention = list(digest.get("path_attention") or [])
    if not path_attention:
        lines.append("- No active path clarifications are currently surfaced.")
    else:
        for item in path_attention:
            lines.append(
                f"- {item['repo']} — {item['headline']} ({item['attention_state']}, {item['activity_status']} registry, {item['context_quality']} context)"
            )

    lines.extend(["", "## Automation Candidates"])
    automation_candidates = list(digest.get("automation_candidates") or [])
    if not automation_candidates:
        lines.append("- No repos currently clear the automation trust bar.")
    else:
        for item in automation_candidates:
            lines.append(
                f"- {item['repo']} ({item['activity_status']}, "
                f"{item['path_confidence']} path confidence, {item['context_quality']} context)"
            )

    lines.extend(["", "## Risk Posture"])
    risk_items = list(risk_posture.get("top_elevated") or [])
    if not risk_items:
        lines.append("- No elevated risk items are currently surfaced.")
    else:
        for item in risk_items:
            lines.append(
                f"- **{item['repo']}** [{item['risk_tier']}]: {item['risk_summary']}"
            )

    lines.extend(["", "## Security Posture"])
    security_items = list(security_posture.get("top_alerts") or [])
    scanned_count = int(security_posture.get("scanned_count", 0) or 0)
    if security_items:
        for item in security_items:
            lines.append(
                f"- **{item['repo']}** [{item['risk_tier']}]: "
                f"{item['dependabot_critical']} critical, {item['dependabot_high']} high "
                "open Dependabot alerts"
            )
    elif scanned_count > 0:
        lines.append(
            f"- All {scanned_count} scanned repos are clear of open high/critical Dependabot alerts."
        )
    else:
        lines.append(
            "- Security overlay not run for this snapshot "
            "(re-run with `--portfolio-truth-include-security`)."
        )

    lines.extend(["", "## Movement"])
    lines.append(
        f"- {_safe_text(movement.get('summary_text')) or 'No verdict movement is recorded across the available truth snapshots.'}"
    )
    for item in list(movement.get("transitions") or []):
        if item.get("kind") == "repo_lifecycle":
            continue
        lines.append(
            f"- **{_safe_text(item.get('repo'))}** [{_safe_text(item.get('kind'))}]: "
            f"{_safe_text(item.get('from')) or 'unknown'}→{_safe_text(item.get('to')) or 'unknown'} "
            f"({_safe_text(item.get('to_date')) or 'undated'})"
        )

    lines.extend(["", "## Weekly Sections"])
    for section in list(digest.get("section_digest") or []):
        lines.append(
            f"- {section['label']} [{section['state']}]: {section['headline']} Next: {section['next_step']}"
        )

    repo_briefings = list(digest.get("top_repo_briefings") or [])
    if repo_briefings:
        lines.extend(["", "## Top Repo Briefings"])
        for item in repo_briefings:
            lines.append(
                f"- {item['repo']}: {item['why_it_matters']} Next: {item['next_step']}"
            )

    lines.extend(
        ["", f"_Guardrail: {_safe_text(digest.get('report_only_guardrail'))}_", ""]
    )
    return "\n".join(lines)


def write_weekly_command_center_artifacts(
    output_dir: Path,
    *,
    username: str,
    generated_at: datetime,
    digest: dict[str, Any],
) -> tuple[Path, Path]:
    stamp = generated_at.date().isoformat()
    json_path = output_dir / f"weekly-command-center-{username}-{stamp}.json"
    markdown_path = output_dir / f"weekly-command-center-{username}-{stamp}.md"
    json_path.write_text(json.dumps(digest, indent=2))
    markdown_path.write_text(render_weekly_command_center_markdown(digest))
    return json_path, markdown_path


def _build_truth_summary(portfolio_truth: dict[str, Any]) -> dict[str, Any]:
    projects = list(portfolio_truth.get("projects") or [])
    context_counts: dict[str, int] = {}
    path_counts: dict[str, int] = {}
    override_counts: dict[str, int] = {}
    risk_tier_counts: dict[str, int] = {}
    attention_state_counts: dict[str, int] = {}
    active_project_count = 0
    low_confidence_path_count = 0

    for project in projects:
        declared = _mapping(project.get("declared"))
        derived = _mapping(project.get("derived"))
        risk = _mapping(project.get("risk"))
        context_quality = _safe_text(derived.get("context_quality")) or "unknown"
        context_counts[context_quality] = context_counts.get(context_quality, 0) + 1
        operating_path = _safe_text(declared.get("operating_path")) or "unspecified"
        path_counts[operating_path] = path_counts.get(operating_path, 0) + 1
        override = _safe_text(derived.get("path_override")) or "none"
        override_counts[override] = override_counts.get(override, 0) + 1
        attention_state = _safe_text(derived.get("attention_state")) or "manual-only"
        attention_state_counts[attention_state] = (
            attention_state_counts.get(attention_state, 0) + 1
        )
        tier = _safe_text(risk.get("risk_tier")) or "baseline"
        risk_tier_counts[tier] = risk_tier_counts.get(tier, 0) + 1
        if _safe_text(derived.get("activity_status")) == "active":
            active_project_count += 1
        if _safe_text(derived.get("path_confidence")) == "low":
            low_confidence_path_count += 1

    return {
        "project_count": len(projects),
        "active_project_count": active_project_count,
        "context_quality_counts": context_counts,
        "operating_path_counts": path_counts,
        "path_override_counts": override_counts,
        "attention_state_counts": attention_state_counts,
        "risk_tier_counts": risk_tier_counts,
        "elevated_risk_count": risk_tier_counts.get("elevated", 0),
        "default_attention_count": sum(
            attention_state_counts.get(state, 0)
            for state in ("active-product", "active-infra", "decision-needed")
        ),
        "decision_needed_count": attention_state_counts.get("decision-needed", 0),
        "low_confidence_path_count": low_confidence_path_count,
        "investigate_override_count": override_counts.get("investigate", 0),
    }


def _build_path_attention_items(
    portfolio_truth: dict[str, Any],
) -> list[dict[str, Any]]:
    projects = list(portfolio_truth.get("projects") or [])
    candidates: list[dict[str, Any]] = []
    status_rank = {"decision-needed": 0, "active-product": 1, "active-infra": 2}
    context_rank = {
        "none": 0,
        "boilerplate": 1,
        "minimum-viable": 2,
        "standard": 3,
        "full": 4,
    }

    for project in projects:
        identity = _mapping(project.get("identity"))
        declared = _mapping(project.get("declared"))
        derived = _mapping(project.get("derived"))
        activity_status = display_activity_status(
            _safe_text(derived.get("activity_status")),
            archived=bool(derived.get("archived")),
        )
        attention_state = _safe_text(derived.get("attention_state"))
        if attention_state != "decision-needed":
            continue
        operating_path = _safe_text(declared.get("operating_path"))
        override = _safe_text(derived.get("path_override"))
        if operating_path and override != "investigate":
            continue
        context_quality = _safe_text(derived.get("context_quality")) or "unknown"
        rationale = (
            _safe_text(derived.get("path_rationale"))
            or "Path guidance still needs clarification."
        )
        headline = (
            "Unspecified stable path"
            if not operating_path
            else f"{operating_path.title()} with investigate override"
        )
        candidates.append(
            {
                "repo": _safe_text(identity.get("display_name")) or "Repo",
                "headline": headline,
                "attention_state": attention_state,
                "activity_status": activity_status or "unknown",
                "context_quality": context_quality,
                "path_confidence": _safe_text(derived.get("path_confidence"))
                or "legacy",
                "rationale": rationale,
                "operating_path": operating_path or "unspecified",
                "path_override": override or "none",
            }
        )

    candidates.sort(
        key=lambda item: (
            status_rank.get(item["attention_state"], 9),
            0 if item["operating_path"] == "unspecified" else 1,
            0 if item["path_confidence"] == "low" else 1,
            context_rank.get(item["context_quality"], 9),
            item["repo"].lower(),
        )
    )
    return candidates[:MAX_PATH_ATTENTION_ITEMS]


def _build_risk_attention_items(
    portfolio_truth: dict[str, Any],
) -> list[dict[str, Any]]:
    projects = list(portfolio_truth.get("projects") or [])
    items: list[dict[str, Any]] = []
    status_rank = {"active": 0, "recent": 1, "stale": 2, "archived": 3}
    for project in projects:
        risk = _mapping(project.get("risk"))
        if _safe_text(risk.get("risk_tier")) != "elevated":
            continue
        identity = _mapping(project.get("identity"))
        derived = _mapping(project.get("derived"))
        items.append(
            {
                "repo": _safe_text(identity.get("display_name")),
                "risk_tier": "elevated",
                "risk_summary": _safe_text(risk.get("risk_summary")),
                "risk_factors": risk.get("risk_factors") or [],
                "_sort_key": (
                    status_rank.get(_safe_text(derived.get("activity_status")), 9),
                    _safe_text(identity.get("display_name")),
                ),
            }
        )
    items.sort(key=lambda x: x["_sort_key"])
    for item in items:
        del item["_sort_key"]
    return items[:MAX_RISK_ATTENTION_ITEMS]


def _build_security_summary(portfolio_truth: dict[str, Any]) -> dict[str, Any]:
    """Aggregate the opt-in security overlay across scanned repos. scanned_count is
    repos with alerts_available=True (the security overlay ran for them); a scanned
    repo with zero open alerts is genuinely clear, distinct from an unscanned one."""
    projects = list(portfolio_truth.get("projects") or [])
    scanned = 0
    repos_with_open = 0
    total_critical = 0
    total_high = 0
    for project in projects:
        security = _mapping(project.get("security"))
        if not security.get("alerts_available"):
            continue
        scanned += 1
        critical = int(security.get("dependabot_critical") or 0)
        high = int(security.get("dependabot_high") or 0)
        total_critical += critical
        total_high += high
        if critical > 0 or high > 0:
            repos_with_open += 1
    return {
        "scanned_count": scanned,
        "repos_with_open_high_critical": repos_with_open,
        "total_open_critical": total_critical,
        "total_open_high": total_high,
    }


def _build_security_attention_items(
    portfolio_truth: dict[str, Any],
) -> list[dict[str, Any]]:
    """Top scanned repos carrying open high/critical Dependabot alerts, critical-first."""
    projects = list(portfolio_truth.get("projects") or [])
    items: list[dict[str, Any]] = []
    for project in projects:
        security = _mapping(project.get("security"))
        if not security.get("alerts_available"):
            continue
        critical = int(security.get("dependabot_critical") or 0)
        high = int(security.get("dependabot_high") or 0)
        if critical <= 0 and high <= 0:
            continue
        identity = _mapping(project.get("identity"))
        risk = _mapping(project.get("risk"))
        repo = _safe_text(identity.get("display_name"))
        items.append(
            {
                "repo": repo,
                "dependabot_critical": critical,
                "dependabot_high": high,
                "risk_tier": _safe_text(risk.get("risk_tier")) or "baseline",
                "_sort_key": (-critical, -high, repo),
            }
        )
    items.sort(key=lambda x: x["_sort_key"])
    for item in items:
        del item["_sort_key"]
    return items[:MAX_SECURITY_ATTENTION_ITEMS]


def _build_section_digest(
    weekly_story: dict[str, Any],
    *,
    operator_decision: str = "",
    operator_why: str = "",
) -> list[dict[str, Any]]:
    sections = list(weekly_story.get("sections") or [])
    digest = []
    for section in sections:
        section_id = _safe_text(section.get("id"))
        headline = (
            _safe_text(section.get("headline"))
            or "No section headline is recorded yet."
        )
        next_step = (
            _safe_text(section.get("next_step"))
            or "No section next step is recorded yet."
        )
        if section_id == "weekly-priority":
            headline = operator_why or headline
            next_step = operator_decision or next_step
        digest.append(
            {
                "id": section_id,
                "label": _safe_text(section.get("label")) or "Section",
                "state": _safe_text(section.get("state")) or "idle",
                "headline": headline,
                "next_step": next_step,
                "reason_codes": list(section.get("reason_codes") or []),
            }
        )
    return digest
