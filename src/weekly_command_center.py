from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.report_enrichment import build_weekly_review_pack

CONTRACT_VERSION = "weekly_command_center_digest_v1"
AUTHORITY_CAP = "bounded-automation"
MAX_PATH_ATTENTION_ITEMS = 5
MAX_REPO_BRIEFINGS = 3
MAX_RISK_ATTENTION_ITEMS = 5


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return {}


def latest_portfolio_truth_path(output_dir: Path) -> Path | None:
    latest = output_dir / "portfolio-truth-latest.json"
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
    portfolio_truth_reference: str = "",
    control_center_reference: str = "",
    report_reference: str = "",
    generated_at: str = "",
) -> dict[str, Any]:
    weekly_pack = build_weekly_review_pack(report_data, diff_data)
    weekly_story = _mapping(weekly_pack.get("weekly_story_v1"))
    operator_summary = _mapping(snapshot.get("operator_summary"))
    repo_briefings = list(weekly_pack.get("repo_briefings") or [])
    decision_quality = _mapping(operator_summary.get("decision_quality_v1"))
    truth = portfolio_truth or {}
    truth_summary = _build_truth_summary(truth)

    return {
        "contract_version": CONTRACT_VERSION,
        "authority_cap": AUTHORITY_CAP,
        "workbook_first": True,
        "generated_at": generated_at or _safe_text(report_data.get("generated_at")),
        "username": _safe_text(report_data.get("username")) or "unknown",
        "report_reference": report_reference or _safe_text(report_data.get("latest_report_path")),
        "control_center_reference": control_center_reference,
        "portfolio_truth_reference": portfolio_truth_reference,
        "headline": _safe_text(weekly_story.get("headline"))
        or "No weekly headline is recorded yet.",
        "decision": _safe_text(weekly_story.get("decision"))
        or "Continue the normal operator review loop.",
        "why_this_week": _safe_text(weekly_story.get("why_this_week"))
        or "No weekly rationale is recorded yet.",
        "next_step": _safe_text(weekly_story.get("next_step"))
        or "Open the workbook first, then use the read-only control center.",
        "queue_pressure_summary": _safe_text(weekly_pack.get("queue_pressure_summary")),
        "operating_paths_summary": _safe_text(weekly_pack.get("operating_paths_summary")),
        "decision_quality": {
            "status": _safe_text(decision_quality.get("decision_quality_status"))
            or "insufficient-data",
            "human_skepticism_required": bool(
                decision_quality.get("human_skepticism_required", True)
            ),
            "summary": _safe_text(decision_quality.get("recommendation_quality_summary"))
            or _safe_text(decision_quality.get("confidence_calibration_summary"))
            or "Decision quality is not available yet.",
            "authority_cap": _safe_text(decision_quality.get("authority_cap")) or AUTHORITY_CAP,
        },
        "portfolio_truth": truth_summary,
        "path_attention": _build_path_attention_items(truth),
        "risk_posture": {
            "elevated_count": truth_summary.get("elevated_risk_count", 0),
            "risk_tier_counts": truth_summary.get("risk_tier_counts", {}),
            "top_elevated": _build_risk_attention_items(truth),
        },
        "section_digest": _build_section_digest(weekly_story),
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
            for item in repo_briefings[:MAX_REPO_BRIEFINGS]
        ],
        "report_only_guardrail": (
            "This digest is descriptive only. It may highlight path, trust, and pressure, "
            "but it does not widen approval, execution, or automation authority."
        ),
    }


def render_weekly_command_center_markdown(digest: dict[str, Any]) -> str:
    decision_quality = _mapping(digest.get("decision_quality"))
    portfolio_truth = _mapping(digest.get("portfolio_truth"))
    risk_posture = _mapping(digest.get("risk_posture"))
    tier_counts = _mapping(risk_posture.get("risk_tier_counts"))
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
        f"- Decision Quality: `{_safe_text(decision_quality.get('status'))}` — {_safe_text(decision_quality.get('summary'))}",
        f"- Operating Paths: {_safe_text(digest.get('operating_paths_summary')) or 'No operating-path summary is recorded yet.'}",
        f"- Portfolio Truth: {portfolio_truth.get('project_count', 0)} projects, {portfolio_truth.get('active_project_count', 0)} active, {portfolio_truth.get('investigate_override_count', 0)} with investigate override, {portfolio_truth.get('low_confidence_path_count', 0)} low-confidence paths",
        f"- Risk Posture: {risk_posture.get('elevated_count', 0)} elevated, {tier_counts.get('moderate', 0)} moderate, {tier_counts.get('baseline', 0)} baseline",
        "",
        "## Path Attention",
    ]

    path_attention = list(digest.get("path_attention") or [])
    if not path_attention:
        lines.append("- No active path clarifications are currently surfaced.")
    else:
        for item in path_attention:
            lines.append(
                f"- {item['repo']} — {item['headline']} ({item['registry_status']}, {item['context_quality']} context)"
            )

    lines.extend(["", "## Risk Posture"])
    risk_items = list(risk_posture.get("top_elevated") or [])
    if not risk_items:
        lines.append("- No elevated risk items are currently surfaced.")
    else:
        for item in risk_items:
            lines.append(f"- **{item['repo']}** [{item['risk_tier']}]: {item['risk_summary']}")

    lines.extend(["", "## Weekly Sections"])
    for section in list(digest.get("section_digest") or []):
        lines.append(
            f"- {section['label']} [{section['state']}]: {section['headline']} Next: {section['next_step']}"
        )

    repo_briefings = list(digest.get("top_repo_briefings") or [])
    if repo_briefings:
        lines.extend(["", "## Top Repo Briefings"])
        for item in repo_briefings:
            lines.append(f"- {item['repo']}: {item['why_it_matters']} Next: {item['next_step']}")

    lines.extend(["", f"_Guardrail: {_safe_text(digest.get('report_only_guardrail'))}_", ""])
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
        tier = _safe_text(risk.get("risk_tier")) or "baseline"
        risk_tier_counts[tier] = risk_tier_counts.get(tier, 0) + 1
        if _safe_text(derived.get("registry_status")) == "active":
            active_project_count += 1
        if _safe_text(derived.get("path_confidence")) == "low":
            low_confidence_path_count += 1

    return {
        "project_count": len(projects),
        "active_project_count": active_project_count,
        "context_quality_counts": context_counts,
        "operating_path_counts": path_counts,
        "path_override_counts": override_counts,
        "risk_tier_counts": risk_tier_counts,
        "elevated_risk_count": risk_tier_counts.get("elevated", 0),
        "low_confidence_path_count": low_confidence_path_count,
        "investigate_override_count": override_counts.get("investigate", 0),
    }


def _build_path_attention_items(portfolio_truth: dict[str, Any]) -> list[dict[str, Any]]:
    projects = list(portfolio_truth.get("projects") or [])
    candidates: list[dict[str, Any]] = []
    status_rank = {"active": 0, "candidate": 1, "parked": 2, "archived": 3}
    context_rank = {"none": 0, "boilerplate": 1, "minimum-viable": 2, "standard": 3, "full": 4}

    for project in projects:
        identity = _mapping(project.get("identity"))
        declared = _mapping(project.get("declared"))
        derived = _mapping(project.get("derived"))
        registry_status = _safe_text(derived.get("registry_status"))
        if registry_status not in {"active", "candidate"}:
            continue
        operating_path = _safe_text(declared.get("operating_path"))
        override = _safe_text(derived.get("path_override"))
        if operating_path and override != "investigate":
            continue
        context_quality = _safe_text(derived.get("context_quality")) or "unknown"
        rationale = (
            _safe_text(derived.get("path_rationale")) or "Path guidance still needs clarification."
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
                "registry_status": registry_status or "unknown",
                "context_quality": context_quality,
                "path_confidence": _safe_text(derived.get("path_confidence")) or "legacy",
                "rationale": rationale,
                "operating_path": operating_path or "unspecified",
                "path_override": override or "none",
            }
        )

    candidates.sort(
        key=lambda item: (
            status_rank.get(item["registry_status"], 9),
            0 if item["operating_path"] == "unspecified" else 1,
            0 if item["path_confidence"] == "low" else 1,
            context_rank.get(item["context_quality"], 9),
            item["repo"].lower(),
        )
    )
    return candidates[:MAX_PATH_ATTENTION_ITEMS]


def _build_risk_attention_items(portfolio_truth: dict[str, Any]) -> list[dict[str, Any]]:
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


def _build_section_digest(weekly_story: dict[str, Any]) -> list[dict[str, Any]]:
    sections = list(weekly_story.get("sections") or [])
    return [
        {
            "id": _safe_text(section.get("id")),
            "label": _safe_text(section.get("label")) or "Section",
            "state": _safe_text(section.get("state")) or "idle",
            "headline": _safe_text(section.get("headline"))
            or "No section headline is recorded yet.",
            "next_step": _safe_text(section.get("next_step"))
            or "No section next step is recorded yet.",
            "reason_codes": list(section.get("reason_codes") or []),
        }
        for section in sections
    ]
