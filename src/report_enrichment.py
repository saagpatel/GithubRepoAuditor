from __future__ import annotations

import re
from typing import Any

from src.terminology import ACTION_SYNC_CANONICAL_LABELS
from src.weekly_packaging import finalize_weekly_pack

COMPLETENESS_THRESHOLDS = [
    ("shipped", 0.75),
    ("functional", 0.55),
    ("wip", 0.35),
    ("skeleton", 0.15),
]

DIMENSION_LABELS = {
    "readme": "README",
    "structure": "Structure",
    "code_quality": "Code Quality",
    "testing": "Testing",
    "cicd": "CI/CD",
    "dependencies": "Dependencies",
    "activity": "Activity",
    "documentation": "Documentation",
    "build_readiness": "Build Readiness",
    "community_profile": "Community Profile",
    "security": "Security",
}

NO_BASELINE_SUMMARY = (
    "No prior baseline was available, so this view shows the current run summary and operator pressure without before/after deltas."
)
NO_HISTORY_SUMMARY = (
    "No history is recorded yet, so this view is using the current run only."
)
NO_LINKED_ARTIFACT_SUMMARY = "No linked artifact available yet."
NO_FOLLOW_THROUGH_SUMMARY = "No follow-through evidence is recorded yet."
NO_FOLLOW_THROUGH_CHECKPOINT = "Use the next run or linked artifact to confirm whether the recommendation moved."
NO_FOLLOW_THROUGH_ESCALATION = "No stronger follow-through escalation is currently surfaced."
NO_FOLLOW_THROUGH_RECOVERY = "No follow-through recovery or escalation-retirement signal is currently surfaced."
NO_FOLLOW_THROUGH_RECOVERY_PERSISTENCE = "No follow-through recovery persistence signal is currently surfaced."
NO_FOLLOW_THROUGH_RELAPSE_CHURN = "No relapse churn is currently surfaced."
NO_FOLLOW_THROUGH_RECOVERY_FRESHNESS = "No follow-through recovery freshness signal is currently surfaced."
NO_FOLLOW_THROUGH_RECOVERY_DECAY = "No follow-through recovery freshness-decay signal is currently surfaced."
NO_FOLLOW_THROUGH_RECOVERY_MEMORY_RESET = "No follow-through recovery memory reset signal is currently surfaced."
NO_FOLLOW_THROUGH_RECOVERY_REBUILD_STRENGTH = "No follow-through recovery rebuild-strength signal is currently surfaced."
NO_FOLLOW_THROUGH_RECOVERY_REACQUISITION = "No follow-through recovery reacquisition signal is currently surfaced."
NO_FOLLOW_THROUGH_REACQUISITION_DURABILITY = "No follow-through reacquisition durability signal is currently surfaced."
NO_FOLLOW_THROUGH_REACQUISITION_CONSOLIDATION = "No follow-through reacquisition confidence-consolidation signal is currently surfaced."
NO_FOLLOW_THROUGH_REACQUISITION_SOFTENING_DECAY = "No reacquisition softening-decay signal is currently surfaced."
NO_FOLLOW_THROUGH_REACQUISITION_CONFIDENCE_RETIREMENT = "No reacquisition confidence-retirement signal is currently surfaced."
NO_FOLLOW_THROUGH_REACQUISITION_REVALIDATION_RECOVERY = "No post-revalidation recovery or confidence re-earning signal is currently surfaced."
NO_OPERATOR_FOCUS_SUMMARY = "No operator focus bucket is currently surfaced."
NO_PORTFOLIO_CATALOG_SUMMARY = "No portfolio catalog contract is recorded yet."
NO_INTENT_ALIGNMENT_SUMMARY = "Intent alignment cannot be judged until a portfolio catalog contract exists."
NO_SCORECARD_SUMMARY = "No maturity scorecard is recorded yet."
NO_MATURITY_GAP_SUMMARY = "No maturity gap summary is recorded yet."
NO_WHERE_TO_START_SUMMARY = "No meaningful implementation hotspot is currently surfaced."
NO_OPERATOR_OUTCOMES_SUMMARY = "Not enough operator history is recorded yet to judge whether recent actions are improving portfolio outcomes."
NO_OPERATOR_EFFECTIVENESS_SUMMARY = "Not enough judged recommendation history is recorded yet to judge operator effectiveness."
NO_HIGH_PRESSURE_QUEUE_TREND = "High-pressure queue trend is not ready yet."
NO_ACTION_SYNC_SUMMARY = "No current campaign needs Action Sync yet, so the safest next move is to keep the story local."
NO_ACTION_SYNC_STEP = "Stay local for now; no current campaign needs preview or apply."
NO_ACTION_SYNC_LINE = "Action Sync: stay local until a campaign has meaningful actions and healthy writeback prerequisites."
NO_APPLY_READINESS_SUMMARY = "No current campaign has a safe execution handoff yet, so the local story should stay local for now."
NO_NEXT_APPLY_CANDIDATE = "Stay local for now; no current campaign has a safe execution handoff."
NO_ACTION_SYNC_COMMAND_HINT = "No Action Sync command is recommended yet."
NO_CAMPAIGN_OUTCOMES_SUMMARY = "No recent Action Sync apply needs post-apply monitoring yet, so the local weekly story can stay local."
NO_NEXT_MONITORING_STEP = "Stay local for now; no recent Action Sync apply needs post-apply follow-up yet."
NO_POST_APPLY_MONITORING_LINE = "Post-Apply Monitoring: no recent Action Sync apply needs follow-up yet."
NO_CAMPAIGN_TUNING_SUMMARY = "Campaign tuning stays neutral until there is enough outcome history to bias tied recommendations."
NO_NEXT_TUNED_CAMPAIGN = "No current campaign needs a tie-break candidate yet."
NO_CAMPAIGN_TUNING_LINE = "Campaign Tuning: recommendations stay neutral until more outcome history is available."
NO_HISTORICAL_PORTFOLIO_INTELLIGENCE_SUMMARY = "Historical portfolio intelligence is still thin, so the weekly story should stay grounded in the current run and recent operator queue."
NO_NEXT_HISTORICAL_FOCUS = "Stay local for now; no repo has enough cross-run intervention evidence to demand a historical follow-up read yet."
NO_HISTORICAL_INTELLIGENCE_LINE = "Historical Portfolio Intelligence: keep the weekly story anchored in the current run until more cross-run evidence accumulates."
NO_AUTOMATION_GUIDANCE_SUMMARY = "Automation guidance stays quiet until a campaign has a clearly safe preview, follow-up, or manual-only posture."
NO_NEXT_SAFE_AUTOMATION_STEP = "Stay local for now; no current campaign has a stronger safe automation posture than manual review."
NO_AUTOMATION_GUIDANCE_LINE = "Automation Guidance: keep the next step human-led until a bounded safe posture is surfaced."
NO_APPROVAL_WORKFLOW_SUMMARY = "No current approval needs review yet, so the approval workflow can stay local for now."
NO_NEXT_APPROVAL_REVIEW = "Stay local for now; no current approval needs review."
NO_APPROVAL_WORKFLOW_LINE = "Approval Workflow: no current approval needs review yet."

OPERATOR_FOCUS_LABELS = {
    "act-now": "Act Now",
    "watch-closely": "Watch Closely",
    "improving": "Improving",
    "fragile": "Fragile",
    "revalidate": "Revalidate",
}
OPERATOR_FOCUS_DISPLAY_ORDER = [
    "act-now",
    "watch-closely",
    "improving",
    "fragile",
    "revalidate",
]
PRODUCT_MODE_LABELS = {
    "first-run": "First Run",
    "weekly-review": "Weekly Review",
    "deep-dive": "Deep Dive",
    "action-sync": "Action Sync",
}
def _metadata(audit: Any) -> dict[str, Any]:
    metadata = getattr(audit, "metadata", None)
    if metadata is None:
        return (audit or {}).get("metadata", {})
    if hasattr(metadata, "to_dict"):
        return metadata.to_dict()
    return metadata


def _mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return {}


def _overall_score(audit: Any) -> float:
    if hasattr(audit, "overall_score"):
        return float(getattr(audit, "overall_score", 0.0) or 0.0)
    return float((audit or {}).get("overall_score", 0.0) or 0.0)


def _results(audit: Any) -> list[Any]:
    if hasattr(audit, "analyzer_results"):
        return list(getattr(audit, "analyzer_results", []) or [])
    return list((audit or {}).get("analyzer_results", []) or [])


def _security_posture(audit: Any) -> dict[str, Any]:
    if hasattr(audit, "security_posture"):
        return dict(getattr(audit, "security_posture", {}) or {})
    return dict((audit or {}).get("security_posture", {}) or {})


def _action_candidates(audit: Any) -> list[dict[str, Any]]:
    if hasattr(audit, "action_candidates"):
        return list(getattr(audit, "action_candidates", []) or [])
    return list((audit or {}).get("action_candidates", []) or [])


def _hotspots(audit: Any) -> list[dict[str, Any]]:
    if hasattr(audit, "hotspots"):
        return list(getattr(audit, "hotspots", []) or [])
    return list((audit or {}).get("hotspots", []) or [])


def _implementation_hotspots(audit: Any) -> list[dict[str, Any]]:
    if hasattr(audit, "implementation_hotspots"):
        return list(getattr(audit, "implementation_hotspots", []) or [])
    return list((audit or {}).get("implementation_hotspots", []) or [])


def _string_list(items: list[str], *, fallback: str) -> str:
    cleaned = [str(item).strip() for item in items if str(item).strip()]
    return ", ".join(cleaned[:3]) if cleaned else fallback


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _repo_name(audit: Any) -> str:
    return str(_metadata(audit).get("name", "") or "")


def _repo_anchor(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "repo"


def _repo_queue_item(repo_name: str, report_data: Any) -> dict[str, Any]:
    queue = list(_mapping(report_data).get("operator_queue") or [])
    for item in queue:
        mapped = _mapping(item)
        if (mapped.get("repo") or mapped.get("repo_name") or "").strip() == repo_name:
            return mapped
    return {}


def _product_mode_key(report_data: Any, diff_data: dict | None = None) -> str:
    data = _mapping(report_data)
    operator_summary = _mapping(data.get("operator_summary"))
    audits = list(data.get("audits") or [])
    if (
        data.get("campaign_summary")
        or data.get("writeback_preview")
        or data.get("writeback_results")
        or data.get("campaign_actions")
    ):
        return "action-sync"
    if len(audits) == 1 and not operator_summary.get("source_run_id"):
        return "deep-dive"
    if diff_data is None and not data.get("diff_data") and not operator_summary.get("source_run_id"):
        return "first-run"
    return "weekly-review"


def build_product_mode_summary(report_data: Any, diff_data: dict | None = None) -> str:
    mode_key = _product_mode_key(report_data, diff_data)
    if mode_key == "action-sync":
        return (
            "Action Sync: use this artifact to confirm the local campaign story first, then preview or apply "
            "GitHub, GitHub Projects, or Notion mirrors only after the repo-level decision is settled."
        )
    if mode_key == "deep-dive":
        return (
            "Deep Dive: use this artifact to stay with one repo long enough to make a clear decision about the "
            "next move, not just to skim portfolio pressure."
        )
    if mode_key == "first-run":
        return (
            "First Run: use this artifact to confirm setup, create the baseline workbook, and take the first "
            "read-only pass through the operator story."
        )
    return (
        "Weekly Review: use this artifact for the normal workbook-first operator loop, then move to the "
        "read-only control center when you want a tighter triage queue."
    )


def build_artifact_role_summary(report_data: Any, diff_data: dict | None = None) -> str:
    mode_key = _product_mode_key(report_data, diff_data)
    if mode_key == "action-sync":
        return (
            "Local report remains authoritative; campaigns, writeback, and GitHub Projects are managed mirrors of "
            "the decision already made here."
        )
    if mode_key == "deep-dive":
        return (
            "This artifact is the repo drilldown handoff: use it to connect score, hotspots, follow-through, and "
            "maturity into one concrete next step."
        )
    if mode_key == "first-run":
        return (
            "This artifact is the onboarding handoff: it shows the first reliable portfolio snapshot and the "
            "reading order that will become the normal weekly loop."
        )
    return (
        "This artifact is the shared weekly handoff across workbook, HTML, Markdown, and review-pack: orient the "
        "portfolio here, then choose repo drilldown or Action Sync only when needed."
    )


def build_suggested_reading_order(report_data: Any, diff_data: dict | None = None) -> str:
    mode_key = _product_mode_key(report_data, diff_data)
    if mode_key == "action-sync":
        return (
            "Read Review Queue first, then the control-center headline and primary target, then the campaign preview "
            "or writeback section before syncing outward."
        )
    if mode_key == "deep-dive":
        return (
            "Read Repo Detail first, then Where To Start, implementation hotspots, maturity gap, and the next "
            "follow-through checkpoint."
        )
    if mode_key == "first-run":
        return (
            "Read Dashboard, then Run Changes, then Review Queue, then Repo Detail, and finish with "
            "--control-center for the read-only queue."
        )
    return (
        "Read Dashboard, then Run Changes, then Review Queue, then Portfolio Explorer, then Repo Detail, and finish "
        "with Executive Summary or --control-center if you need a tighter queue."
    )


def build_next_best_workflow_step(report_data: Any, diff_data: dict | None = None) -> str:
    mode_key = _product_mode_key(report_data, diff_data)
    if mode_key == "action-sync":
        return "Keep the local artifact as the source of truth, then use campaign preview or writeback only when the repo decision is already clear."
    if mode_key == "deep-dive":
        return "Stay with the single-repo drilldown until the hotspot, maturity gap, and follow-through checkpoint all point to the same next move."
    if mode_key == "first-run":
        return "Run --doctor first, generate the standard workbook next, then use --control-center for the first read-only triage pass."
    return "Open the standard workbook first, then use --control-center for read-only triage and Action Sync only when you are ready to mirror a settled campaign."


def _repo_review_target(repo_name: str, report_data: Any) -> dict[str, Any]:
    targets = list(_mapping(report_data).get("review_targets") or [])
    for item in targets:
        mapped = _mapping(item)
        if (mapped.get("repo") or mapped.get("repo_name") or "").strip() == repo_name:
            return mapped
    return {}


def _repo_change(repo_name: str, diff_data: dict | None) -> dict[str, Any]:
    if not diff_data:
        return {}
    for section_name in ("repo_changes", "tier_changes", "score_changes"):
        for item in diff_data.get(section_name, []) or []:
            mapped = _mapping(item)
            if (mapped.get("name") or mapped.get("repo") or "").strip() == repo_name:
                return mapped
    return {}


def _repo_trend_label(repo_name: str, audit: Any, report_data: Any) -> str:
    history = _mapping(report_data).get("score_history") or {}
    scores = list(history.get(repo_name) or [])
    current_score = round(_overall_score(audit), 3)
    if not scores:
        return no_history_summary()
    previous_score = float(scores[-1] or 0.0)
    delta = round(current_score - previous_score, 3)
    if abs(delta) < 0.005:
        return "Holding flat versus the last recorded run."
    if delta > 0:
        return f"Up {delta:.3f} versus the last recorded run."
    return f"Down {abs(delta):.3f} versus the last recorded run."


def _repo_last_movement(repo_name: str, report_data: Any, diff_data: dict | None) -> str:
    change = _repo_change(repo_name, diff_data)
    if change:
        delta = change.get("delta")
        if delta is None and change.get("new_score") is not None and change.get("old_score") is not None:
            delta = float(change.get("new_score", 0.0) or 0.0) - float(change.get("old_score", 0.0) or 0.0)
        if delta is not None:
            delta_value = round(float(delta or 0.0), 3)
            if abs(delta_value) < 0.005:
                movement = "Held flat versus the last run."
            elif delta_value > 0:
                movement = f"Improved {delta_value:.3f} versus the last run."
            else:
                movement = f"Regressed {abs(delta_value):.3f} versus the last run."
            old_tier = change.get("old_tier")
            new_tier = change.get("new_tier")
            if old_tier and new_tier and old_tier != new_tier:
                return f"{movement} Tier moved {old_tier} -> {new_tier}."
            return movement

    queue_item = _repo_queue_item(repo_name, report_data)
    review_summary = _mapping(_mapping(report_data).get("review_summary"))
    if queue_item:
        return build_last_movement_label(queue_item, review_summary)

    review_target = _repo_review_target(repo_name, report_data)
    if review_target:
        return build_last_movement_label(review_target, review_summary)

    return no_history_summary()


def _repo_change_summary(repo_name: str, audit: Any, report_data: Any, diff_data: dict | None) -> str:
    change = _repo_change(repo_name, diff_data)
    if change:
        delta = change.get("delta")
        if delta is None and change.get("new_score") is not None and change.get("old_score") is not None:
            delta = float(change.get("new_score", 0.0) or 0.0) - float(change.get("old_score", 0.0) or 0.0)
        if delta is not None:
            delta_value = round(float(delta or 0.0), 3)
            direction = "improved" if delta_value > 0.005 else "regressed" if delta_value < -0.005 else "held flat"
            summary = f"Score {direction} {abs(delta_value):.3f} since the last run." if direction != "held flat" else "Score held flat since the last run."
            old_tier = change.get("old_tier")
            new_tier = change.get("new_tier")
            if old_tier and new_tier and old_tier != new_tier:
                summary += f" Tier moved {old_tier} -> {new_tier}."
            return summary

    queue_item = _repo_queue_item(repo_name, report_data)
    if queue_item.get("summary"):
        return str(queue_item.get("summary"))
    if queue_item.get("title"):
        return str(queue_item.get("title"))

    hotspots = _hotspots(audit)
    if hotspots:
        return str(hotspots[0].get("summary") or hotspots[0].get("title") or "Current-run hotspot pressure is present.")

    return no_baseline_summary()


def _repo_hotspot_context(audit: Any) -> str:
    hotspots = _hotspots(audit)
    if not hotspots:
        return "No hotspot context is recorded yet."
    hotspot = _mapping(hotspots[0])
    title = str(hotspot.get("title") or "Current hotspot")
    summary = str(hotspot.get("summary") or "").strip()
    return f"{title}: {summary}" if summary else title


def _implementation_hotspot_line(hotspot: dict[str, Any]) -> str:
    path = str(hotspot.get("path") or "repo root")
    category = str(hotspot.get("category") or "implementation pressure").replace("-", " ")
    move = str(hotspot.get("suggested_first_move") or "").strip()
    prefix = f"{path} ({category})"
    return f"{prefix}: {move}" if move else prefix


def _where_to_start_summary(audit: Any) -> str:
    hotspots = _implementation_hotspots(audit)
    if not hotspots:
        return NO_WHERE_TO_START_SUMMARY
    hotspot = _mapping(hotspots[0])
    path = str(hotspot.get("path") or "repo root")
    why = str(hotspot.get("why_it_matters") or "").strip()
    move = str(hotspot.get("suggested_first_move") or "").strip()
    if why and move:
        return f"Start in {path}. {why} {move}"
    if move:
        return f"Start in {path}. {move}"
    if why:
        return f"Start in {path}. {why}"
    return f"Start in {path}."


def _repo_action_candidates(audit: Any) -> list[str]:
    candidates = []
    for item in _action_candidates(audit)[:3]:
        mapped = _mapping(item)
        title = mapped.get("title") or mapped.get("action")
        if title:
            candidates.append(str(title))
    return candidates


def _repo_artifact_label(repo_name: str, report_data: Any) -> str:
    queue_item = _repo_queue_item(repo_name, report_data)
    for key in ("artifact_url", "url", "html_url"):
        if queue_item.get(key):
            return str(queue_item.get(key))
    review_target = _repo_review_target(repo_name, report_data)
    for key in ("artifact_url", "url", "html_url"):
        if review_target.get(key):
            return str(review_target.get(key))
    return no_linked_artifact_summary()


def _score_map(audit: Any) -> dict[str, float]:
    scores: dict[str, float] = {}
    for result in _results(audit):
        if hasattr(result, "dimension"):
            dimension = getattr(result, "dimension", "")
            score = getattr(result, "score", 0.0)
        else:
            dimension = result.get("dimension", "")
            score = result.get("score", 0.0)
        if dimension:
            scores[dimension] = float(score or 0.0)

    security_score = _security_posture(audit).get("score")
    if security_score is not None:
        scores["security"] = float(security_score or 0.0)
    return scores


def _top_dimension_labels(scores: dict[str, float], *, reverse: bool) -> list[str]:
    ordered = sorted(
        scores.items(),
        key=lambda item: (-item[1], item[0]) if reverse else (item[1], item[0]),
    )
    labels: list[str] = []
    for dimension, score in ordered:
        if dimension == "interest":
            continue
        labels.append(f"{DIMENSION_LABELS.get(dimension, dimension.replace('_', ' ').title())} ({score:.2f})")
        if len(labels) == 3:
            break
    return labels


def _next_tier_gap_summary(score: float) -> str:
    for tier_name, threshold in COMPLETENESS_THRESHOLDS:
        if score < threshold:
            return f"Needs +{threshold - score:.2f} to reach {tier_name}."
    return "Already at shipped tier; focus on protecting momentum and preventing drift."


def build_score_explanation(audit: Any) -> dict[str, Any]:
    scores = _score_map(audit)
    actions = _action_candidates(audit)
    hotspots = _hotspots(audit)
    best_action = actions[0] if actions else {}
    metadata = _metadata(audit)
    return {
        "repo": metadata.get("name", ""),
        "top_positive_drivers": _top_dimension_labels(scores, reverse=True),
        "top_negative_drivers": _top_dimension_labels(scores, reverse=False),
        "next_tier_gap_summary": _next_tier_gap_summary(_overall_score(audit)),
        "next_best_action": best_action.get("title") or best_action.get("action") or "Review the current hotspot and pick the next best repo action.",
        "next_best_action_rationale": best_action.get("rationale") or (
            hotspots[0].get("summary") if hotspots else "No dominant rationale is recorded yet."
        ),
    }


def build_repo_briefing(
    audit: Any,
    report_data: Any,
    diff_data: dict | None = None,
) -> dict[str, Any]:
    metadata = _metadata(audit)
    repo_name = _repo_name(audit)
    explanation = _mapping((_mapping(audit).get("score_explanation") if isinstance(audit, dict) else getattr(audit, "score_explanation", None)))
    if not explanation:
        explanation = _mapping(build_score_explanation(audit))
    current_state = {
        "score": round(_overall_score(audit), 3),
        "grade": _mapping(audit).get("grade") if isinstance(audit, dict) else getattr(audit, "grade", ""),
        "tier": _mapping(audit).get("completeness_tier") if isinstance(audit, dict) else getattr(audit, "completeness_tier", ""),
        "language": metadata.get("language") or "Unknown",
        "trend": _repo_trend_label(repo_name, audit, report_data),
        "badges": _string_list(list(_mapping(audit).get("badges", []) if isinstance(audit, dict) else getattr(audit, "badges", []) or []), fallback="None"),
        "flags": _string_list(list(_mapping(audit).get("flags", []) if isinstance(audit, dict) else getattr(audit, "flags", []) or []), fallback="None"),
        "url": metadata.get("html_url", ""),
        "description": metadata.get("description") or "No description recorded yet.",
    }
    strongest_drivers = explanation.get("top_positive_drivers", []) or []
    biggest_drags = explanation.get("top_negative_drivers", []) or []
    next_tier_gap = explanation.get("next_tier_gap_summary") or "No next-tier gap is recorded yet."
    last_movement = _repo_last_movement(repo_name, report_data, diff_data)
    recent_change_summary = _repo_change_summary(repo_name, audit, report_data, diff_data)
    hotspot_context = _repo_hotspot_context(audit)
    next_best_action = explanation.get("next_best_action") or "Review the current hotspot and pick the next best repo action."
    next_best_action_rationale = explanation.get("next_best_action_rationale") or "No action rationale is recorded yet."
    top_action_candidates = _repo_action_candidates(audit)
    queue_item = _repo_queue_item(repo_name, report_data)
    review_target = _repo_review_target(repo_name, report_data)
    handoff_source = queue_item or review_target or {}
    recommended_action = build_action_handoff_summary(handoff_source) or str(next_best_action)
    follow_through_status = build_follow_through_status_label(handoff_source)
    follow_through_summary = build_follow_through_summary(handoff_source)
    follow_through_checkpoint = build_follow_through_checkpoint(handoff_source)
    follow_through_checkpoint_timing = build_follow_through_checkpoint_status_label(handoff_source)
    follow_through_escalation = build_follow_through_escalation_status_label(handoff_source)
    follow_through_escalation_summary = build_follow_through_escalation_summary(handoff_source)
    follow_through_recovery = build_follow_through_recovery_status_label(handoff_source)
    follow_through_recovery_summary = build_follow_through_recovery_summary(handoff_source)
    follow_through_recovery_persistence = build_follow_through_recovery_persistence_status_label(handoff_source)
    follow_through_recovery_persistence_summary = build_follow_through_recovery_persistence_summary(handoff_source)
    follow_through_relapse_churn = build_follow_through_relapse_churn_status_label(handoff_source)
    follow_through_relapse_churn_summary = build_follow_through_relapse_churn_summary(handoff_source)
    follow_through_recovery_freshness = build_follow_through_recovery_freshness_status_label(handoff_source)
    follow_through_recovery_freshness_summary = build_follow_through_recovery_freshness_summary(handoff_source)
    follow_through_recovery_decay = build_follow_through_recovery_decay_status_label(handoff_source)
    follow_through_recovery_decay_summary = build_follow_through_recovery_decay_summary(handoff_source)
    follow_through_recovery_memory_reset = build_follow_through_recovery_memory_reset_status_label(handoff_source)
    follow_through_recovery_memory_reset_summary = build_follow_through_recovery_memory_reset_summary(handoff_source)
    follow_through_recovery_rebuild_strength = build_follow_through_recovery_rebuild_strength_status_label(handoff_source)
    follow_through_recovery_rebuild_strength_summary = build_follow_through_recovery_rebuild_strength_summary(handoff_source)
    follow_through_recovery_reacquisition = build_follow_through_recovery_reacquisition_status_label(handoff_source)
    follow_through_recovery_reacquisition_summary = build_follow_through_recovery_reacquisition_summary(handoff_source)
    follow_through_reacquisition_durability = build_follow_through_reacquisition_durability_status_label(handoff_source)
    follow_through_reacquisition_durability_summary = build_follow_through_reacquisition_durability_summary(handoff_source)
    follow_through_reacquisition_consolidation = build_follow_through_reacquisition_consolidation_status_label(handoff_source)
    follow_through_reacquisition_consolidation_summary = build_follow_through_reacquisition_consolidation_summary(handoff_source)
    follow_through_reacquisition_softening_decay = build_follow_through_reacquisition_softening_decay_status_label(handoff_source)
    follow_through_reacquisition_softening_decay_summary = build_follow_through_reacquisition_softening_decay_summary(handoff_source)
    follow_through_reacquisition_confidence_retirement = build_follow_through_reacquisition_confidence_retirement_status_label(handoff_source)
    follow_through_reacquisition_confidence_retirement_summary = build_follow_through_reacquisition_confidence_retirement_summary(handoff_source)
    follow_through_reacquisition_revalidation_recovery = build_follow_through_reacquisition_revalidation_recovery_status_label(handoff_source)
    follow_through_reacquisition_revalidation_recovery_summary = build_follow_through_reacquisition_revalidation_recovery_summary(handoff_source)
    operator_focus = build_operator_focus(handoff_source)
    operator_focus_summary = build_operator_focus_summary(handoff_source)
    operator_focus_line = build_operator_focus_line(handoff_source)
    portfolio_catalog = build_portfolio_catalog_entry(audit)
    catalog_line = build_portfolio_catalog_line(audit)
    intent_alignment = build_intent_alignment_status(audit)
    intent_alignment_reason = build_intent_alignment_summary(audit)
    scorecard = build_scorecard_entry(audit)
    scorecard_line = build_scorecard_line(audit)
    maturity_gap_summary = build_maturity_gap_summary(audit)
    action_sync_line = build_action_sync_line(handoff_source)
    apply_packet_line = build_apply_packet_line(handoff_source)
    post_apply_line = build_post_apply_monitoring_line(handoff_source)
    campaign_tuning_line = build_campaign_tuning_line(handoff_source)
    historical_intelligence_line = build_historical_intelligence_line(handoff_source)
    automation_line = build_automation_line(handoff_source)
    follow_through_resurfacing_reason = build_follow_through_resurfacing_reason(handoff_source)
    implementation_hotspots = _implementation_hotspots(audit)[:3]
    where_to_start_summary = _where_to_start_summary(audit)
    return {
        "repo": repo_name,
        "anchor": f"repo-{_repo_anchor(repo_name)}",
        "headline": f"{repo_name} — {current_state['score']:.2f} ({current_state['tier'] or 'unrated'})",
        "current_state": current_state,
        "current_state_line": (
            f"Score {current_state['score']:.2f}, grade {current_state['grade'] or '—'}, "
            f"{current_state['tier'] or 'unrated'} tier, {current_state['language']}, trend: {current_state['trend']}"
        ),
        "why_this_repo_looks_this_way": {
            "strongest_drivers": _string_list(list(strongest_drivers), fallback="No strong positive drivers recorded yet."),
            "biggest_drags": _string_list(list(biggest_drags), fallback="No major drag factors recorded yet."),
            "next_tier_gap": str(next_tier_gap),
        },
        "why_it_matters_line": (
            f"Strongest drivers: {_string_list(list(strongest_drivers), fallback='No strong positive drivers recorded yet.')}. "
            f"Biggest drags: {_string_list(list(biggest_drags), fallback='No major drag factors recorded yet.')}. "
            f"Next tier gap: {next_tier_gap}"
        ),
        "what_changed": {
            "last_movement": last_movement,
            "recent_change_summary": recent_change_summary,
            "top_hotspot_context": hotspot_context,
        },
        "what_changed_line": f"{last_movement} {recent_change_summary}".strip(),
        "where_to_start_summary": where_to_start_summary,
        "where_to_start_line": where_to_start_summary,
        "implementation_hotspots": implementation_hotspots,
        "what_to_do_next": {
            "next_best_action": str(recommended_action),
            "rationale": str(next_best_action_rationale),
            "top_action_candidates": top_action_candidates,
            "linked_artifact": _repo_artifact_label(repo_name, report_data),
            "follow_through_status": follow_through_status,
            "follow_through_summary": follow_through_summary,
            "checkpoint_timing": follow_through_checkpoint_timing,
            "escalation": follow_through_escalation,
            "escalation_summary": follow_through_escalation_summary,
            "recovery_retirement": follow_through_recovery,
            "recovery_retirement_summary": follow_through_recovery_summary,
            "recovery_persistence": follow_through_recovery_persistence,
            "recovery_persistence_summary": follow_through_recovery_persistence_summary,
            "relapse_churn": follow_through_relapse_churn,
            "relapse_churn_summary": follow_through_relapse_churn_summary,
            "recovery_freshness": follow_through_recovery_freshness,
            "recovery_freshness_summary": follow_through_recovery_freshness_summary,
            "recovery_decay": follow_through_recovery_decay,
            "recovery_decay_summary": follow_through_recovery_decay_summary,
            "recovery_memory_reset": follow_through_recovery_memory_reset,
            "recovery_memory_reset_summary": follow_through_recovery_memory_reset_summary,
            "recovery_rebuild_strength": follow_through_recovery_rebuild_strength,
            "recovery_rebuild_strength_summary": follow_through_recovery_rebuild_strength_summary,
            "recovery_reacquisition": follow_through_recovery_reacquisition,
            "recovery_reacquisition_summary": follow_through_recovery_reacquisition_summary,
            "reacquisition_durability": follow_through_reacquisition_durability,
            "reacquisition_durability_summary": follow_through_reacquisition_durability_summary,
            "reacquisition_confidence": follow_through_reacquisition_consolidation,
            "reacquisition_confidence_summary": follow_through_reacquisition_consolidation_summary,
            "reacquisition_softening_decay": follow_through_reacquisition_softening_decay,
            "reacquisition_softening_decay_summary": follow_through_reacquisition_softening_decay_summary,
            "reacquisition_confidence_retirement": follow_through_reacquisition_confidence_retirement,
            "reacquisition_confidence_retirement_summary": follow_through_reacquisition_confidence_retirement_summary,
            "revalidation_recovery": follow_through_reacquisition_revalidation_recovery,
            "revalidation_recovery_summary": follow_through_reacquisition_revalidation_recovery_summary,
            "operator_focus": operator_focus,
            "operator_focus_summary": operator_focus_summary,
            "operator_focus_line": operator_focus_line,
            "what_would_count_as_progress": follow_through_checkpoint,
        },
        "what_to_do_next_line": f"{recommended_action} {next_best_action_rationale}".strip(),
        "follow_through_line": f"{follow_through_status}: {follow_through_summary}",
        "checkpoint_line": follow_through_checkpoint,
        "checkpoint_timing_line": follow_through_checkpoint_timing,
        "escalation_line": f"{follow_through_escalation}: {follow_through_escalation_summary}",
        "recovery_line": f"{follow_through_recovery}: {follow_through_recovery_summary}",
        "recovery_persistence_line": f"{follow_through_recovery_persistence}: {follow_through_recovery_persistence_summary}",
        "relapse_churn_line": f"{follow_through_relapse_churn}: {follow_through_relapse_churn_summary}",
        "recovery_freshness_line": f"{follow_through_recovery_freshness}: {follow_through_recovery_freshness_summary}",
        "recovery_decay_line": f"{follow_through_recovery_decay}: {follow_through_recovery_decay_summary}",
        "recovery_memory_reset_line": f"{follow_through_recovery_memory_reset}: {follow_through_recovery_memory_reset_summary}",
        "recovery_rebuild_strength_line": f"{follow_through_recovery_rebuild_strength}: {follow_through_recovery_rebuild_strength_summary}",
        "recovery_reacquisition_line": f"{follow_through_recovery_reacquisition}: {follow_through_recovery_reacquisition_summary}",
        "reacquisition_durability_line": f"{follow_through_reacquisition_durability}: {follow_through_reacquisition_durability_summary}",
        "reacquisition_confidence_line": f"{follow_through_reacquisition_consolidation}: {follow_through_reacquisition_consolidation_summary}",
        "reacquisition_softening_decay_line": f"{follow_through_reacquisition_softening_decay}: {follow_through_reacquisition_softening_decay_summary}",
        "reacquisition_confidence_retirement_line": f"{follow_through_reacquisition_confidence_retirement}: {follow_through_reacquisition_confidence_retirement_summary}",
        "revalidation_recovery_line": f"{follow_through_reacquisition_revalidation_recovery}: {follow_through_reacquisition_revalidation_recovery_summary}",
        "operator_focus": operator_focus,
        "operator_focus_summary": operator_focus_summary,
        "operator_focus_line": operator_focus_line,
        "action_sync_line": action_sync_line,
        "apply_packet_line": apply_packet_line,
        "post_apply_line": post_apply_line,
        "campaign_tuning_line": campaign_tuning_line,
        "historical_intelligence_line": historical_intelligence_line,
        "automation_line": automation_line,
        "portfolio_catalog": portfolio_catalog,
        "catalog_line": catalog_line,
        "intent_alignment": intent_alignment,
        "intent_alignment_reason": intent_alignment_reason,
        "intent_alignment_line": f"{intent_alignment}: {intent_alignment_reason}",
        "scorecard": scorecard,
        "scorecard_line": scorecard_line,
        "maturity_gap_summary": maturity_gap_summary,
        "maturity_gap_line": f"Maturity Gap: {maturity_gap_summary}",
        "action_sync_stage": str(handoff_source.get("action_sync_stage") or "idle"),
        "action_sync_reason": str(handoff_source.get("action_sync_reason") or "No current Action Sync guidance is surfaced for this repo."),
        "suggested_campaign": str(handoff_source.get("suggested_campaign") or ""),
        "suggested_writeback_target": str(handoff_source.get("suggested_writeback_target") or "none"),
        "apply_packet_state": str(handoff_source.get("apply_packet_state") or "stay-local"),
        "apply_packet_summary": str(handoff_source.get("apply_packet_summary") or "No current apply packet is surfaced for this repo."),
        "apply_packet_command": str(handoff_source.get("apply_packet_command") or ""),
        "post_apply_state": str(handoff_source.get("post_apply_state") or "no-recent-apply"),
        "post_apply_summary": str(handoff_source.get("post_apply_summary") or "No post-apply monitoring is surfaced for this repo yet."),
        "campaign_tuning_status": str(handoff_source.get("campaign_tuning_status") or "insufficient-evidence"),
        "campaign_tuning_summary": str(handoff_source.get("campaign_tuning_summary") or "No campaign tuning evidence is surfaced for this repo yet."),
        "automation_posture": str(handoff_source.get("automation_posture") or "manual-only"),
        "automation_summary": str(handoff_source.get("automation_summary") or "No automation guidance is surfaced for this repo yet."),
        "automation_command": str(handoff_source.get("automation_command") or ""),
        "historical_intelligence_status": str(handoff_source.get("historical_intelligence_status") or "insufficient-evidence"),
        "historical_intelligence_summary": str(handoff_source.get("historical_intelligence_summary") or "No historical intelligence evidence is surfaced for this repo yet."),
        "resurfacing_reason_line": follow_through_resurfacing_reason,
    }


def build_weekly_review_pack(
    report_data: Any,
    diff_data: dict | None = None,
    *,
    repo_limit: int = 3,
    attention_limit: int = 5,
) -> dict[str, Any]:
    data = _mapping(report_data)
    audits = list(data.get("audits") or [])
    operator_summary = _mapping(data.get("operator_summary"))
    operator_queue = list(data.get("operator_queue") or [])
    portfolio_headline = operator_summary.get("headline") or (
        f"Portfolio grade {data.get('portfolio_grade', 'F')} across {data.get('repos_audited', 0)} audited repos."
    )
    repo_names: list[str] = []
    for item in operator_queue:
        repo = (_mapping(item).get("repo") or _mapping(item).get("repo_name") or "").strip()
        if repo and repo not in repo_names:
            repo_names.append(repo)
    for audit in sorted(audits, key=_overall_score, reverse=True):
        name = _repo_name(audit)
        if name and name not in repo_names:
            repo_names.append(name)
        if len(repo_names) >= repo_limit:
            break
    audit_by_name = {_repo_name(audit): audit for audit in audits}
    repo_briefings = [
        build_repo_briefing(audit_by_name[name], data, diff_data)
        for name in repo_names[:repo_limit]
        if name in audit_by_name
    ]
    top_attention = []
    review_summary = _mapping(data.get("review_summary"))
    for item in operator_queue[:attention_limit]:
        mapped = _mapping(item)
        top_attention.append(_build_operator_focus_item(mapped, review_summary))
    grouped_focus_items = {bucket: [] for bucket in OPERATOR_FOCUS_DISPLAY_ORDER}
    for item in operator_queue:
        enriched = _build_operator_focus_item(_mapping(item), review_summary)
        focus_key = _operator_focus_bucket_key(item)
        grouped_focus_items[focus_key].append(enriched)
    top_recommendation = build_top_recommendation_summary(data)
    what_to_do_this_week = top_recommendation
    if repo_briefings:
        what_to_do_this_week = f"{top_recommendation} Start with {repo_briefings[0]['repo']} if you need a concrete place to begin."
    product_mode_summary = build_product_mode_summary(data, diff_data)
    artifact_role_summary = build_artifact_role_summary(data, diff_data)
    suggested_reading_order = build_suggested_reading_order(data, diff_data)
    next_best_workflow_step = build_next_best_workflow_step(data, diff_data)
    weekly_pack = {
        "product_mode_summary": product_mode_summary,
        "artifact_role_summary": artifact_role_summary,
        "suggested_reading_order": suggested_reading_order,
        "next_best_workflow_step": next_best_workflow_step,
        "portfolio_headline": str(portfolio_headline),
        "run_change_summary": build_run_change_summary(diff_data if diff_data is not None else data.get("diff_data")),
        "queue_pressure_summary": build_queue_pressure_summary(data, diff_data),
        "trust_actionability_summary": build_trust_actionability_summary(data),
        "top_recommendation_summary": top_recommendation,
        "operator_focus_summary": _build_operator_focus_summary_from_groups(grouped_focus_items),
        "portfolio_catalog_summary": build_portfolio_catalog_summary(data),
        "intent_alignment_summary": build_portfolio_intent_alignment_summary(data),
        "scorecards_summary": build_scorecards_summary(data),
        "implementation_hotspots_summary": str(
            _mapping(data.get("implementation_hotspots_summary")).get("summary")
            or "No meaningful implementation hotspots are currently surfaced."
        ),
        "operator_outcomes_summary": build_operator_outcomes_summary(data),
        "operator_effectiveness_line": build_operator_effectiveness_line(data),
        "high_pressure_queue_trend_line": build_high_pressure_queue_trend_line(data),
        "action_sync_summary": build_action_sync_summary(data),
        "next_action_sync_step": build_next_action_sync_step(data),
        "action_sync_readiness_line": build_action_sync_readiness_line(data),
        "apply_readiness_summary": build_apply_readiness_summary(data),
        "next_apply_candidate": build_next_apply_candidate_line(data),
        "action_sync_command_hint": build_action_sync_command_hint(data),
        "campaign_outcomes_summary": build_campaign_outcomes_summary(data),
        "next_monitoring_step": build_next_monitoring_step_line(data),
        "post_apply_monitoring_line": (
            f"{build_campaign_outcomes_summary(data)} Next step: {build_next_monitoring_step_line(data)}"
            if build_campaign_outcomes_summary(data) != NO_CAMPAIGN_OUTCOMES_SUMMARY
            or build_next_monitoring_step_line(data) != NO_NEXT_MONITORING_STEP
            else NO_POST_APPLY_MONITORING_LINE
        ),
        "campaign_tuning_summary": build_campaign_tuning_summary(data),
        "next_tuned_campaign": build_next_tuned_campaign_line(data),
        "next_tie_break_candidate": build_next_tie_break_candidate_line(data),
        "campaign_tuning_line": (
            f"{build_campaign_tuning_summary(data)} Next tie-break: {build_next_tuned_campaign_line(data)}"
            if build_campaign_tuning_summary(data) != NO_CAMPAIGN_TUNING_SUMMARY
            or build_next_tuned_campaign_line(data) != NO_NEXT_TUNED_CAMPAIGN
            else NO_CAMPAIGN_TUNING_LINE
        ),
        "historical_portfolio_intelligence": build_historical_portfolio_intelligence_summary(data),
        "next_historical_focus": build_next_historical_focus_line(data),
        "automation_guidance_summary": build_automation_guidance_summary(data),
        "next_safe_automation_step": build_next_safe_automation_step_line(data),
        "approval_workflow_summary": build_approval_workflow_summary(data),
        "next_approval_review": build_next_approval_review_line(data),
        "approval_workflow_line": (
            f"{build_approval_workflow_summary(data)} Next review: {build_next_approval_review_line(data)}"
            if build_approval_workflow_summary(data) != NO_APPROVAL_WORKFLOW_SUMMARY
            or build_next_approval_review_line(data) != NO_NEXT_APPROVAL_REVIEW
            else NO_APPROVAL_WORKFLOW_LINE
        ),
        "automation_guidance_line": (
            f"{build_automation_guidance_summary(data)} Next step: {build_next_safe_automation_step_line(data)}"
            if build_automation_guidance_summary(data) != NO_AUTOMATION_GUIDANCE_SUMMARY
            or build_next_safe_automation_step_line(data) != NO_NEXT_SAFE_AUTOMATION_STEP
            else NO_AUTOMATION_GUIDANCE_LINE
        ),
        "top_ready_for_review_approvals": list(operator_summary.get("top_ready_for_review_approvals") or []),
        "top_needs_reapproval_approvals": list(operator_summary.get("top_needs_reapproval_approvals") or []),
        "top_overdue_approval_followups": list(operator_summary.get("top_overdue_approval_followups") or []),
        "top_due_soon_approval_followups": list(operator_summary.get("top_due_soon_approval_followups") or []),
        "top_approved_manual_approvals": list(operator_summary.get("top_approved_manual_approvals") or []),
        "top_blocked_approvals": list(operator_summary.get("top_blocked_approvals") or []),
        "top_apply_ready_campaigns": list(operator_summary.get("top_apply_ready_campaigns") or []),
        "top_preview_ready_campaigns": list(operator_summary.get("top_preview_ready_campaigns") or []),
        "top_drift_review_campaigns": list(operator_summary.get("top_drift_review_campaigns") or []),
        "top_blocked_campaigns": list(operator_summary.get("top_blocked_campaigns") or []),
        "top_ready_to_apply_packets": list(operator_summary.get("top_ready_to_apply_packets") or []),
        "top_needs_approval_packets": list(operator_summary.get("top_needs_approval_packets") or []),
        "top_review_drift_packets": list(operator_summary.get("top_review_drift_packets") or []),
        "top_monitor_now_campaigns": list(operator_summary.get("top_monitor_now_campaigns") or []),
        "top_holding_clean_campaigns": list(operator_summary.get("top_holding_clean_campaigns") or []),
        "top_reopened_campaigns": list(operator_summary.get("top_reopened_campaigns") or []),
        "top_drift_returned_campaigns": list(operator_summary.get("top_drift_returned_campaigns") or []),
        "top_proven_campaigns": list(operator_summary.get("top_proven_campaigns") or []),
        "top_caution_campaigns": list(operator_summary.get("top_caution_campaigns") or []),
        "top_thin_evidence_campaigns": list(operator_summary.get("top_thin_evidence_campaigns") or []),
        "top_relapsing_repos": list(operator_summary.get("top_relapsing_repos") or []),
        "top_persistent_pressure_repos": list(operator_summary.get("top_persistent_pressure_repos") or []),
        "top_improving_repos": list(operator_summary.get("top_improving_repos") or []),
        "top_holding_repos": list(operator_summary.get("top_holding_repos") or []),
        "top_preview_safe_campaigns": list(operator_summary.get("top_preview_safe_campaigns") or []),
        "top_apply_manual_campaigns": list(operator_summary.get("top_apply_manual_campaigns") or []),
        "top_approval_first_campaigns": list(operator_summary.get("top_approval_first_campaigns") or []),
        "top_follow_up_safe_campaigns": list(operator_summary.get("top_follow_up_safe_campaigns") or []),
        "top_manual_only_campaigns": list(operator_summary.get("top_manual_only_campaigns") or []),
        "top_attention": top_attention,
        "repo_briefings": repo_briefings,
        "top_below_target_scorecard_items": list(_mapping(data).get("scorecards_summary", {}).get("top_below_target_repos") or []),
        "what_to_do_this_week": what_to_do_this_week,
        "follow_through_summary": str(operator_summary.get("follow_through_summary") or NO_FOLLOW_THROUGH_SUMMARY),
        "follow_through_checkpoint_summary": str(
            operator_summary.get("follow_through_checkpoint_summary") or NO_FOLLOW_THROUGH_CHECKPOINT
        ),
        "follow_through_escalation_summary": str(
            operator_summary.get("follow_through_escalation_summary") or NO_FOLLOW_THROUGH_ESCALATION
        ),
        "follow_through_recovery_summary": str(
            operator_summary.get("follow_through_recovery_summary") or NO_FOLLOW_THROUGH_RECOVERY
        ),
        "follow_through_recovery_persistence_summary": str(
            operator_summary.get("follow_through_recovery_persistence_summary") or NO_FOLLOW_THROUGH_RECOVERY_PERSISTENCE
        ),
        "follow_through_relapse_churn_summary": str(
            operator_summary.get("follow_through_relapse_churn_summary") or NO_FOLLOW_THROUGH_RELAPSE_CHURN
        ),
        "follow_through_recovery_freshness_summary": str(
            operator_summary.get("follow_through_recovery_freshness_summary") or NO_FOLLOW_THROUGH_RECOVERY_FRESHNESS
        ),
        "follow_through_recovery_decay_summary": str(
            operator_summary.get("follow_through_recovery_decay_summary") or NO_FOLLOW_THROUGH_RECOVERY_DECAY
        ),
        "follow_through_recovery_memory_reset_summary": str(
            operator_summary.get("follow_through_recovery_memory_reset_summary") or NO_FOLLOW_THROUGH_RECOVERY_MEMORY_RESET
        ),
        "follow_through_recovery_rebuild_strength_summary": str(
            operator_summary.get("follow_through_recovery_rebuild_strength_summary")
            or NO_FOLLOW_THROUGH_RECOVERY_REBUILD_STRENGTH
        ),
        "follow_through_recovery_reacquisition_summary": str(
            operator_summary.get("follow_through_recovery_reacquisition_summary")
            or NO_FOLLOW_THROUGH_RECOVERY_REACQUISITION
        ),
        "follow_through_reacquisition_durability_summary": str(
            operator_summary.get("follow_through_recovery_reacquisition_durability_summary")
            or NO_FOLLOW_THROUGH_REACQUISITION_DURABILITY
        ),
        "follow_through_reacquisition_consolidation_summary": str(
            operator_summary.get("follow_through_recovery_reacquisition_consolidation_summary")
            or NO_FOLLOW_THROUGH_REACQUISITION_CONSOLIDATION
        ),
        "follow_through_reacquisition_softening_decay_summary": str(
            operator_summary.get("follow_through_reacquisition_softening_decay_summary")
            or NO_FOLLOW_THROUGH_REACQUISITION_SOFTENING_DECAY
        ),
        "follow_through_reacquisition_confidence_retirement_summary": str(
            operator_summary.get("follow_through_reacquisition_confidence_retirement_summary")
            or NO_FOLLOW_THROUGH_REACQUISITION_CONFIDENCE_RETIREMENT
        ),
        "follow_through_reacquisition_revalidation_recovery_summary": str(
            operator_summary.get("follow_through_reacquisition_revalidation_recovery_summary")
            or NO_FOLLOW_THROUGH_REACQUISITION_REVALIDATION_RECOVERY
        ),
        "top_unattempted_items": list(operator_summary.get("top_unattempted_items") or []),
        "top_stale_follow_through_items": list(operator_summary.get("top_stale_follow_through_items") or []),
        "top_overdue_follow_through_items": list(operator_summary.get("top_overdue_follow_through_items") or []),
        "top_escalation_items": list(operator_summary.get("top_escalation_items") or []),
        "top_recovering_follow_through_items": list(operator_summary.get("top_recovering_follow_through_items") or []),
        "top_retiring_follow_through_items": list(operator_summary.get("top_retiring_follow_through_items") or []),
        "top_relapsing_follow_through_items": list(operator_summary.get("top_relapsing_follow_through_items") or []),
        "top_fragile_recovery_items": list(operator_summary.get("top_fragile_recovery_items") or []),
        "top_sustained_recovery_items": list(operator_summary.get("top_sustained_recovery_items") or []),
        "top_churn_follow_through_items": list(operator_summary.get("top_churn_follow_through_items") or []),
        "top_fresh_recovery_items": list(operator_summary.get("top_fresh_recovery_items") or []),
        "top_stale_recovery_items": list(operator_summary.get("top_stale_recovery_items") or []),
        "top_softening_recovery_items": list(operator_summary.get("top_softening_recovery_items") or []),
        "top_reset_recovery_items": list(operator_summary.get("top_reset_recovery_items") or []),
        "top_rebuilding_recovery_items": list(operator_summary.get("top_rebuilding_recovery_items") or []),
        "top_rebuilding_recovery_strength_items": list(operator_summary.get("top_rebuilding_recovery_strength_items") or []),
        "top_reacquiring_recovery_items": list(operator_summary.get("top_reacquiring_recovery_items") or []),
        "top_reacquired_recovery_items": list(operator_summary.get("top_reacquired_recovery_items") or []),
        "top_fragile_reacquisition_items": list(operator_summary.get("top_fragile_reacquisition_items") or []),
        "top_just_reacquired_items": list(operator_summary.get("top_just_reacquired_items") or []),
        "top_holding_reacquired_items": list(operator_summary.get("top_holding_reacquired_items") or []),
        "top_durable_reacquired_items": list(operator_summary.get("top_durable_reacquired_items") or []),
        "top_softening_reacquired_items": list(operator_summary.get("top_softening_reacquired_items") or []),
        "top_fragile_reacquisition_confidence_items": list(operator_summary.get("top_fragile_reacquisition_confidence_items") or []),
        "top_softening_reacquisition_items": list(operator_summary.get("top_softening_reacquisition_items") or []),
        "top_revalidation_needed_reacquisition_items": list(operator_summary.get("top_revalidation_needed_reacquisition_items") or []),
        "top_retired_reacquisition_confidence_items": list(operator_summary.get("top_retired_reacquisition_confidence_items") or []),
        "top_under_revalidation_recovery_items": list(operator_summary.get("top_under_revalidation_recovery_items") or []),
        "top_rebuilding_restored_confidence_items": list(operator_summary.get("top_rebuilding_restored_confidence_items") or []),
        "top_reearning_confidence_items": list(operator_summary.get("top_reearning_confidence_items") or []),
        "top_just_reearned_confidence_items": list(operator_summary.get("top_just_reearned_confidence_items") or []),
        "top_holding_reearned_confidence_items": list(operator_summary.get("top_holding_reearned_confidence_items") or []),
        "top_act_now_items": grouped_focus_items["act-now"][:3],
        "top_watch_closely_items": grouped_focus_items["watch-closely"][:3],
        "top_improving_items": grouped_focus_items["improving"][:3],
        "top_fragile_items": grouped_focus_items["fragile"][:3],
        "top_revalidate_items": grouped_focus_items["revalidate"][:3],
    }
    return finalize_weekly_pack(weekly_pack)


def build_run_change_counts(diff_data: dict | None) -> dict[str, int]:
    if not diff_data:
        return {
            "new_repos": 0,
            "removed_repos": 0,
            "tier_promotions": 0,
            "tier_demotions": 0,
            "score_improvements": 0,
            "score_regressions": 0,
            "security_changes": 0,
            "hotspot_changes": 0,
            "collection_changes": 0,
            "notable_repo_changes": 0,
        }

    tier_changes = diff_data.get("tier_changes", []) or []
    promotions = sum(1 for item in tier_changes if item.get("new_tier") != item.get("old_tier") and (item.get("new_score", 0) >= item.get("old_score", 0)))
    demotions = sum(1 for item in tier_changes if item.get("new_tier") != item.get("old_tier") and (item.get("new_score", 0) < item.get("old_score", 0)))
    return {
        "new_repos": len(diff_data.get("new_repos", []) or []),
        "removed_repos": len(diff_data.get("removed_repos", []) or []),
        "tier_promotions": promotions,
        "tier_demotions": demotions,
        "score_improvements": len(diff_data.get("score_improvements", []) or []),
        "score_regressions": len(diff_data.get("score_regressions", []) or []),
        "security_changes": len(diff_data.get("security_changes", []) or []),
        "hotspot_changes": len(diff_data.get("hotspot_changes", []) or []),
        "collection_changes": len(diff_data.get("collection_changes", []) or []),
        "notable_repo_changes": len(diff_data.get("repo_changes", []) or []),
    }


def build_run_change_summary(diff_data: dict | None) -> str:
    if not diff_data:
        return NO_BASELINE_SUMMARY

    counts = build_run_change_counts(diff_data)
    return (
        f"Average score moved {diff_data.get('average_score_delta', 0.0):+.3f}; "
        f"{counts['score_improvements']} meaningful improvements, "
        f"{counts['score_regressions']} regressions, "
        f"{counts['tier_promotions']} promotions, "
        f"and {counts['tier_demotions']} demotions were recorded."
    )


def no_baseline_summary() -> str:
    return NO_BASELINE_SUMMARY


def no_history_summary() -> str:
    return NO_HISTORY_SUMMARY


def no_linked_artifact_summary() -> str:
    return NO_LINKED_ARTIFACT_SUMMARY


def no_follow_through_summary() -> str:
    return NO_FOLLOW_THROUGH_SUMMARY


def no_follow_through_checkpoint() -> str:
    return NO_FOLLOW_THROUGH_CHECKPOINT


def no_follow_through_escalation() -> str:
    return NO_FOLLOW_THROUGH_ESCALATION


def no_follow_through_recovery() -> str:
    return NO_FOLLOW_THROUGH_RECOVERY


def no_follow_through_recovery_persistence() -> str:
    return NO_FOLLOW_THROUGH_RECOVERY_PERSISTENCE


def no_follow_through_relapse_churn() -> str:
    return NO_FOLLOW_THROUGH_RELAPSE_CHURN


def no_follow_through_recovery_freshness() -> str:
    return NO_FOLLOW_THROUGH_RECOVERY_FRESHNESS


def no_follow_through_recovery_decay() -> str:
    return NO_FOLLOW_THROUGH_RECOVERY_DECAY


def no_follow_through_recovery_memory_reset() -> str:
    return NO_FOLLOW_THROUGH_RECOVERY_MEMORY_RESET


def no_follow_through_recovery_rebuild_strength() -> str:
    return NO_FOLLOW_THROUGH_RECOVERY_REBUILD_STRENGTH


def no_follow_through_recovery_reacquisition() -> str:
    return NO_FOLLOW_THROUGH_RECOVERY_REACQUISITION


def no_follow_through_reacquisition_durability() -> str:
    return NO_FOLLOW_THROUGH_REACQUISITION_DURABILITY


def no_follow_through_reacquisition_consolidation() -> str:
    return NO_FOLLOW_THROUGH_REACQUISITION_CONSOLIDATION


def no_follow_through_reacquisition_softening_decay() -> str:
    return NO_FOLLOW_THROUGH_REACQUISITION_SOFTENING_DECAY


def no_follow_through_reacquisition_confidence_retirement() -> str:
    return NO_FOLLOW_THROUGH_REACQUISITION_CONFIDENCE_RETIREMENT


def no_follow_through_reacquisition_revalidation_recovery() -> str:
    return NO_FOLLOW_THROUGH_REACQUISITION_REVALIDATION_RECOVERY


def build_follow_through_status_label(value: Any) -> str:
    mapped = _mapping(value)
    status = str(mapped.get("follow_through_status", value if isinstance(value, str) else "") or "unknown")
    labels = {
        "untouched": "Untouched",
        "attempted": "Attempted",
        "waiting-on-evidence": "Waiting on Evidence",
        "stale-follow-through": "Stale Follow-Through",
        "resolved": "Resolved",
        "unknown": "Unknown",
    }
    return labels.get(status, status.replace("-", " ").title())


def build_follow_through_summary(value: Any) -> str:
    mapped = _mapping(value)
    return str(mapped.get("follow_through_summary") or NO_FOLLOW_THROUGH_SUMMARY)


def build_follow_through_checkpoint(value: Any) -> str:
    mapped = _mapping(value)
    return str(mapped.get("follow_through_next_checkpoint") or NO_FOLLOW_THROUGH_CHECKPOINT)


def build_follow_through_checkpoint_status_label(value: Any) -> str:
    mapped = _mapping(value)
    status = str(mapped.get("follow_through_checkpoint_status", value if isinstance(value, str) else "") or "unknown")
    labels = {
        "not-due": "Not Due",
        "due-soon": "Due Soon",
        "overdue": "Overdue",
        "satisfied": "Satisfied",
        "unknown": "Unknown",
    }
    return labels.get(status, status.replace("-", " ").title())


def build_follow_through_escalation_status_label(value: Any) -> str:
    mapped = _mapping(value)
    status = str(mapped.get("follow_through_escalation_status", value if isinstance(value, str) else "") or "unknown")
    labels = {
        "none": "None",
        "watch": "Watch",
        "nudge": "Nudge",
        "escalate-now": "Escalate Now",
        "resolved-watch": "Resolved Watch",
        "unknown": "Unknown",
    }
    return labels.get(status, status.replace("-", " ").title())


def build_follow_through_escalation_summary(value: Any) -> str:
    mapped = _mapping(value)
    return str(mapped.get("follow_through_escalation_summary") or NO_FOLLOW_THROUGH_ESCALATION)


def build_follow_through_recovery_status_label(value: Any) -> str:
    mapped = _mapping(value)
    status = str(mapped.get("follow_through_recovery_status", value if isinstance(value, str) else "") or "none")
    labels = {
        "none": "None",
        "recovering": "Recovering",
        "retiring-watch": "Retiring Watch",
        "retired": "Retired",
        "relapsing": "Relapsing",
        "insufficient-evidence": "Insufficient Evidence",
    }
    return labels.get(status, status.replace("-", " ").title())


def build_follow_through_recovery_summary(value: Any) -> str:
    mapped = _mapping(value)
    return str(mapped.get("follow_through_recovery_summary") or NO_FOLLOW_THROUGH_RECOVERY)


def build_follow_through_recovery_persistence_status_label(value: Any) -> str:
    mapped = _mapping(value)
    status = str(mapped.get("follow_through_recovery_persistence_status", value if isinstance(value, str) else "") or "none")
    labels = {
        "none": "None",
        "just-recovering": "Just Recovering",
        "holding-recovery": "Holding Recovery",
        "holding-retiring-watch": "Holding Retiring Watch",
        "sustained-retiring-watch": "Sustained Retiring Watch",
        "sustained-retired": "Sustained Retired",
        "fragile-recovery": "Fragile Recovery",
        "insufficient-evidence": "Insufficient Evidence",
    }
    return labels.get(status, status.replace("-", " ").title())


def build_follow_through_recovery_persistence_summary(value: Any) -> str:
    mapped = _mapping(value)
    return str(mapped.get("follow_through_recovery_persistence_summary") or NO_FOLLOW_THROUGH_RECOVERY_PERSISTENCE)


def build_follow_through_relapse_churn_status_label(value: Any) -> str:
    mapped = _mapping(value)
    status = str(mapped.get("follow_through_relapse_churn_status", value if isinstance(value, str) else "") or "none")
    labels = {
        "none": "None",
        "watch": "Watch",
        "fragile": "Fragile",
        "churn": "Churn",
        "blocked": "Blocked",
        "insufficient-evidence": "Insufficient Evidence",
    }
    return labels.get(status, status.replace("-", " ").title())


def build_follow_through_relapse_churn_summary(value: Any) -> str:
    mapped = _mapping(value)
    return str(mapped.get("follow_through_relapse_churn_summary") or NO_FOLLOW_THROUGH_RELAPSE_CHURN)


def build_follow_through_recovery_freshness_status_label(value: Any) -> str:
    mapped = _mapping(value)
    status = str(mapped.get("follow_through_recovery_freshness_status", value if isinstance(value, str) else "") or "none")
    labels = {
        "none": "None",
        "fresh": "Fresh",
        "holding-fresh": "Holding Fresh",
        "mixed-age": "Mixed Age",
        "stale": "Stale",
        "insufficient-evidence": "Insufficient Evidence",
    }
    return labels.get(status, status.replace("-", " ").title())


def build_follow_through_recovery_freshness_summary(value: Any) -> str:
    mapped = _mapping(value)
    return str(mapped.get("follow_through_recovery_freshness_summary") or NO_FOLLOW_THROUGH_RECOVERY_FRESHNESS)


def build_follow_through_recovery_decay_status_label(value: Any) -> str:
    mapped = _mapping(value)
    status = str(mapped.get("follow_through_recovery_decay_status", value if isinstance(value, str) else "") or "none")
    labels = {
        "none": "None",
        "softening": "Softening",
        "aging": "Aging",
        "fragile-aging": "Fragile Aging",
        "expired": "Expired",
        "insufficient-evidence": "Insufficient Evidence",
    }
    return labels.get(status, status.replace("-", " ").title())


def build_follow_through_recovery_decay_summary(value: Any) -> str:
    mapped = _mapping(value)
    return str(mapped.get("follow_through_recovery_decay_summary") or NO_FOLLOW_THROUGH_RECOVERY_DECAY)


def build_follow_through_recovery_memory_reset_status_label(value: Any) -> str:
    mapped = _mapping(value)
    status = str(mapped.get("follow_through_recovery_memory_reset_status", value if isinstance(value, str) else "") or "none")
    labels = {
        "none": "None",
        "reset-watch": "Reset Watch",
        "resetting": "Resetting",
        "reset": "Reset",
        "rebuilding": "Rebuilding",
        "insufficient-evidence": "Insufficient Evidence",
    }
    return labels.get(status, status.replace("-", " ").title())


def build_follow_through_recovery_memory_reset_summary(value: Any) -> str:
    mapped = _mapping(value)
    return str(mapped.get("follow_through_recovery_memory_reset_summary") or NO_FOLLOW_THROUGH_RECOVERY_MEMORY_RESET)


def build_follow_through_recovery_rebuild_strength_status_label(value: Any) -> str:
    mapped = _mapping(value)
    status = str(
        mapped.get("follow_through_recovery_rebuild_strength_status", value if isinstance(value, str) else "") or "none"
    )
    labels = {
        "none": "None",
        "just-rebuilding": "Just Rebuilding",
        "building": "Building",
        "holding-rebuild": "Holding Rebuild",
        "fragile-rebuild": "Fragile Rebuild",
        "insufficient-evidence": "Insufficient Evidence",
    }
    return labels.get(status, status.replace("-", " ").title())


def build_follow_through_recovery_rebuild_strength_summary(value: Any) -> str:
    mapped = _mapping(value)
    return str(
        mapped.get("follow_through_recovery_rebuild_strength_summary")
        or NO_FOLLOW_THROUGH_RECOVERY_REBUILD_STRENGTH
    )


def build_follow_through_recovery_reacquisition_status_label(value: Any) -> str:
    mapped = _mapping(value)
    status = str(
        mapped.get("follow_through_recovery_reacquisition_status", value if isinstance(value, str) else "") or "none"
    )
    labels = {
        "none": "None",
        "reacquiring": "Reacquiring",
        "just-reacquired": "Just Reacquired",
        "holding-reacquired": "Holding Reacquired",
        "reacquired": "Reacquired",
        "fragile-reacquisition": "Fragile Reacquisition",
        "insufficient-evidence": "Insufficient Evidence",
    }
    return labels.get(status, status.replace("-", " ").title())


def build_follow_through_recovery_reacquisition_summary(value: Any) -> str:
    mapped = _mapping(value)
    return str(
        mapped.get("follow_through_recovery_reacquisition_summary")
        or NO_FOLLOW_THROUGH_RECOVERY_REACQUISITION
    )


def build_follow_through_reacquisition_durability_status_label(value: Any) -> str:
    mapped = _mapping(value)
    status = str(
        mapped.get("follow_through_recovery_reacquisition_durability_status", value if isinstance(value, str) else "")
        or "none"
    )
    labels = {
        "none": "None",
        "just-reacquired": "Just Reacquired",
        "consolidating": "Consolidating",
        "holding-reacquired": "Holding Reacquired",
        "durable-reacquired": "Durable Reacquired",
        "softening": "Softening",
        "insufficient-evidence": "Insufficient Evidence",
    }
    return labels.get(status, status.replace("-", " ").title())


def build_follow_through_reacquisition_durability_summary(value: Any) -> str:
    mapped = _mapping(value)
    return str(
        mapped.get("follow_through_recovery_reacquisition_durability_summary")
        or NO_FOLLOW_THROUGH_REACQUISITION_DURABILITY
    )


def build_follow_through_reacquisition_consolidation_status_label(value: Any) -> str:
    mapped = _mapping(value)
    status = str(
        mapped.get(
            "follow_through_recovery_reacquisition_consolidation_status",
            value if isinstance(value, str) else "",
        )
        or "none"
    )
    labels = {
        "none": "None",
        "building-confidence": "Building Confidence",
        "holding-confidence": "Holding Confidence",
        "durable-confidence": "Durable Confidence",
        "fragile-confidence": "Fragile Confidence",
        "reversing": "Reversing",
        "insufficient-evidence": "Insufficient Evidence",
    }
    return labels.get(status, status.replace("-", " ").title())


def build_follow_through_reacquisition_consolidation_summary(value: Any) -> str:
    mapped = _mapping(value)
    return str(
        mapped.get("follow_through_recovery_reacquisition_consolidation_summary")
        or NO_FOLLOW_THROUGH_REACQUISITION_CONSOLIDATION
    )


def build_follow_through_reacquisition_softening_decay_status_label(value: Any) -> str:
    mapped = _mapping(value)
    status = str(
        mapped.get("follow_through_reacquisition_softening_decay_status", value if isinstance(value, str) else "")
        or "none"
    )
    labels = {
        "none": "None",
        "softening-watch": "Softening Watch",
        "step-down": "Step-Down",
        "revalidation-needed": "Revalidation Needed",
        "retired-softening": "Retired Softening",
        "insufficient-evidence": "Insufficient Evidence",
    }
    return labels.get(status, status.replace("-", " ").title())


def build_follow_through_reacquisition_softening_decay_summary(value: Any) -> str:
    mapped = _mapping(value)
    return str(
        mapped.get("follow_through_reacquisition_softening_decay_summary")
        or NO_FOLLOW_THROUGH_REACQUISITION_SOFTENING_DECAY
    )


def build_follow_through_reacquisition_confidence_retirement_status_label(value: Any) -> str:
    mapped = _mapping(value)
    status = str(
        mapped.get("follow_through_reacquisition_confidence_retirement_status", value if isinstance(value, str) else "")
        or "none"
    )
    labels = {
        "none": "None",
        "watch-retirement": "Watch Retirement",
        "retiring-confidence": "Retiring Confidence",
        "retired-confidence": "Retired Confidence",
        "revalidation-needed": "Revalidation Needed",
        "insufficient-evidence": "Insufficient Evidence",
    }
    return labels.get(status, status.replace("-", " ").title())


def build_follow_through_reacquisition_confidence_retirement_summary(value: Any) -> str:
    mapped = _mapping(value)
    return str(
        mapped.get("follow_through_reacquisition_confidence_retirement_summary")
        or NO_FOLLOW_THROUGH_REACQUISITION_CONFIDENCE_RETIREMENT
    )


def build_follow_through_reacquisition_revalidation_recovery_status_label(value: Any) -> str:
    mapped = _mapping(value)
    status = str(
        mapped.get("follow_through_reacquisition_revalidation_recovery_status", value if isinstance(value, str) else "")
        or "none"
    )
    labels = {
        "none": "None",
        "under-revalidation": "Under Revalidation",
        "rebuilding-restored-confidence": "Rebuilding Restored Confidence",
        "reearning-confidence": "Re-Earning Confidence",
        "just-reearned-confidence": "Just Re-Earned Confidence",
        "holding-reearned-confidence": "Holding Re-Earned Confidence",
        "insufficient-evidence": "Insufficient Evidence",
    }
    return labels.get(status, status.replace("-", " ").title())


def build_follow_through_reacquisition_revalidation_recovery_summary(value: Any) -> str:
    mapped = _mapping(value)
    return str(
        mapped.get("follow_through_reacquisition_revalidation_recovery_summary")
        or NO_FOLLOW_THROUGH_REACQUISITION_REVALIDATION_RECOVERY
    )


def _operator_focus_bucket_key(value: Any) -> str:
    mapped = _mapping(value)
    lane = str(mapped.get("lane") or "").strip()
    checkpoint_status = str(mapped.get("follow_through_checkpoint_status") or "").strip()
    escalation_status = str(mapped.get("follow_through_escalation_status") or "").strip()
    relapse_churn_status = str(mapped.get("follow_through_relapse_churn_status") or "").strip()
    recovery_persistence_status = str(mapped.get("follow_through_recovery_persistence_status") or "").strip()
    recovery_status = str(mapped.get("follow_through_recovery_status") or "").strip()
    reacquisition_durability_status = str(
        mapped.get("follow_through_recovery_reacquisition_durability_status") or ""
    ).strip()
    reacquisition_confidence_status = str(
        mapped.get("follow_through_recovery_reacquisition_consolidation_status") or ""
    ).strip()
    softening_status = str(mapped.get("follow_through_reacquisition_softening_decay_status") or "").strip()
    confidence_retirement_status = str(
        mapped.get("follow_through_reacquisition_confidence_retirement_status") or ""
    ).strip()
    revalidation_recovery_status = str(
        mapped.get("follow_through_reacquisition_revalidation_recovery_status") or ""
    ).strip()

    if lane in {"blocked", "urgent"} or checkpoint_status == "overdue" or escalation_status == "escalate-now":
        return "act-now"
    if confidence_retirement_status == "revalidation-needed" or revalidation_recovery_status in {
        "under-revalidation",
        "insufficient-evidence",
    }:
        return "revalidate"
    if relapse_churn_status in {"fragile", "churn", "blocked"}:
        return "fragile"
    if recovery_persistence_status == "fragile-recovery":
        return "fragile"
    if reacquisition_confidence_status in {"fragile-confidence", "reversing"}:
        return "fragile"
    if softening_status in {"softening-watch", "step-down", "revalidation-needed"}:
        return "fragile"
    if revalidation_recovery_status in {
        "rebuilding-restored-confidence",
        "reearning-confidence",
        "just-reearned-confidence",
    }:
        return "fragile"
    if recovery_status in {"recovering", "retiring-watch", "retired"}:
        return "improving"
    if recovery_persistence_status in {
        "holding-recovery",
        "holding-retiring-watch",
        "sustained-retiring-watch",
        "sustained-retired",
    }:
        return "improving"
    if reacquisition_durability_status == "durable-reacquired":
        return "improving"
    if reacquisition_confidence_status in {"holding-confidence", "durable-confidence"}:
        return "improving"
    if revalidation_recovery_status == "holding-reearned-confidence":
        return "improving"
    return "watch-closely"


def build_operator_focus(value: Any) -> str:
    return OPERATOR_FOCUS_LABELS[_operator_focus_bucket_key(value)]


def build_operator_focus_summary(value: Any) -> str:
    mapped = _mapping(value)
    focus_key = _operator_focus_bucket_key(mapped)
    if focus_key == "act-now":
        return _first_nonempty(
            mapped.get("lane_reason"),
            build_follow_through_escalation_summary(mapped),
            build_follow_through_checkpoint(mapped),
            mapped.get("summary"),
        ) or "Immediate operator action is still required."
    if focus_key == "revalidate":
        return _first_nonempty(
            build_follow_through_reacquisition_revalidation_recovery_summary(mapped),
            build_follow_through_reacquisition_confidence_retirement_summary(mapped),
            build_follow_through_checkpoint(mapped),
        ) or "This target still needs revalidation before confidence can be restored."
    if focus_key == "fragile":
        return _first_nonempty(
            build_follow_through_reacquisition_revalidation_recovery_summary(mapped),
            build_follow_through_reacquisition_softening_decay_summary(mapped),
            build_follow_through_relapse_churn_summary(mapped),
            build_follow_through_recovery_persistence_summary(mapped),
            build_follow_through_reacquisition_consolidation_summary(mapped),
        ) or "Progress is visible, but the restored posture is still fragile."
    if focus_key == "improving":
        return _first_nonempty(
            build_follow_through_reacquisition_revalidation_recovery_summary(mapped),
            build_follow_through_reacquisition_consolidation_summary(mapped),
            build_follow_through_reacquisition_durability_summary(mapped),
            build_follow_through_recovery_summary(mapped),
        ) or "The current path is stabilizing and regaining trust."
    return _first_nonempty(
        build_follow_through_summary(mapped),
        build_follow_through_checkpoint(mapped),
        mapped.get("lane_reason"),
        mapped.get("summary"),
    ) or "Keep this item in view while waiting for clearer evidence."


def build_operator_focus_line(value: Any) -> str:
    return f"{build_operator_focus(value)}: {build_operator_focus_summary(value)}"


def build_portfolio_catalog_entry(value: Any) -> dict[str, Any]:
    mapped = _mapping(value)
    entry = mapped.get("portfolio_catalog")
    return _mapping(entry)


def build_portfolio_catalog_line(value: Any) -> str:
    entry = build_portfolio_catalog_entry(value)
    return str(entry.get("catalog_line") or NO_PORTFOLIO_CATALOG_SUMMARY)


def build_intent_alignment_status(value: Any) -> str:
    entry = build_portfolio_catalog_entry(value)
    return str(entry.get("intent_alignment") or "missing-contract")


def build_intent_alignment_summary(value: Any) -> str:
    entry = build_portfolio_catalog_entry(value)
    return str(entry.get("intent_alignment_reason") or NO_INTENT_ALIGNMENT_SUMMARY)


def build_portfolio_catalog_summary(report_data: Any) -> str:
    summary = _mapping(_mapping(report_data).get("portfolio_catalog_summary"))
    return str(summary.get("summary") or NO_PORTFOLIO_CATALOG_SUMMARY)


def build_portfolio_intent_alignment_summary(report_data: Any) -> str:
    summary = _mapping(_mapping(report_data).get("intent_alignment_summary"))
    return str(summary.get("summary") or NO_INTENT_ALIGNMENT_SUMMARY)


def build_scorecard_entry(value: Any) -> dict[str, Any]:
    mapped = _mapping(value)
    entry = mapped.get("scorecard")
    return _mapping(entry)


def build_scorecard_line(value: Any) -> str:
    entry = build_scorecard_entry(value)
    if not entry:
        return f"Scorecard: {NO_SCORECARD_SUMMARY}"
    program_label = str(entry.get("program_label") or "Default")
    maturity_level = str(entry.get("maturity_level") or "missing-basics").replace("-", " ").title()
    target = str(entry.get("target_maturity") or "operating").replace("-", " ").title()
    return f"Scorecard: {program_label} — {maturity_level} (target {target})"


def build_maturity_gap_summary(value: Any) -> str:
    entry = build_scorecard_entry(value)
    if not entry:
        return NO_MATURITY_GAP_SUMMARY
    status = str(entry.get("status") or "").strip()
    program_label = str(entry.get("program_label") or entry.get("program") or "Default")
    target = str(entry.get("target_maturity") or "operating").replace("-", " ").title()
    if status == "on-track":
        return f"No active maturity gap. {program_label} is already meeting the {target} target."
    top_gaps = [str(item).strip() for item in entry.get("top_gaps", []) if str(item).strip()]
    if top_gaps:
        return f"{', '.join(top_gaps[:3]).lower()} are still below the {program_label.lower()} bar."
    return str(entry.get("summary") or NO_MATURITY_GAP_SUMMARY)


def build_scorecards_summary(report_data: Any) -> str:
    summary = _mapping(_mapping(report_data).get("scorecards_summary"))
    return str(summary.get("summary") or NO_SCORECARD_SUMMARY)


def build_operator_outcomes_summary(report_data: Any) -> str:
    summary = _mapping(_mapping(report_data).get("portfolio_outcomes_summary"))
    return str(summary.get("summary") or NO_OPERATOR_OUTCOMES_SUMMARY)


def build_operator_effectiveness_line(report_data: Any) -> str:
    summary = _mapping(_mapping(report_data).get("operator_effectiveness_summary"))
    return str(summary.get("summary") or NO_OPERATOR_EFFECTIVENESS_SUMMARY)


def build_high_pressure_queue_trend_line(report_data: Any) -> str:
    operator_summary = _mapping(_mapping(report_data).get("operator_summary"))
    return str(operator_summary.get("high_pressure_queue_trend_summary") or NO_HIGH_PRESSURE_QUEUE_TREND)


def build_action_sync_summary(report_data: Any) -> str:
    summary = _mapping(_mapping(report_data).get("action_sync_summary"))
    if not summary:
        summary = _mapping(_mapping(report_data).get("operator_summary")).get("action_sync_summary") or {}
    return str(_mapping(summary).get("summary") or NO_ACTION_SYNC_SUMMARY)


def build_next_action_sync_step(report_data: Any) -> str:
    data = _mapping(report_data)
    operator_summary = _mapping(data.get("operator_summary"))
    return str(
        data.get("next_action_sync_step")
        or operator_summary.get("next_action_sync_step")
        or NO_ACTION_SYNC_STEP
    )


def build_action_sync_readiness_line(report_data: Any) -> str:
    summary = build_action_sync_summary(report_data)
    next_step = build_next_action_sync_step(report_data)
    if summary == NO_ACTION_SYNC_SUMMARY and next_step == NO_ACTION_SYNC_STEP:
        return NO_ACTION_SYNC_LINE
    return f"{summary} Next step: {next_step}"


def build_apply_readiness_summary(report_data: Any) -> str:
    summary = _mapping(_mapping(report_data).get("apply_readiness_summary"))
    if not summary:
        summary = _mapping(_mapping(report_data).get("operator_summary")).get("apply_readiness_summary") or {}
    return str(_mapping(summary).get("summary") or NO_APPLY_READINESS_SUMMARY)


def build_next_apply_candidate_line(report_data: Any) -> str:
    candidate = _mapping(_mapping(report_data).get("next_apply_candidate"))
    if not candidate:
        candidate = _mapping(_mapping(report_data).get("operator_summary")).get("next_apply_candidate") or {}
    return str(_mapping(candidate).get("summary") or NO_NEXT_APPLY_CANDIDATE)


def build_action_sync_command_hint(report_data: Any) -> str:
    candidate = _mapping(_mapping(report_data).get("next_apply_candidate"))
    if not candidate:
        candidate = _mapping(_mapping(report_data).get("operator_summary")).get("next_apply_candidate") or {}
    return str(
        _mapping(candidate).get("apply_command")
        or _mapping(candidate).get("preview_command")
        or NO_ACTION_SYNC_COMMAND_HINT
    )


def build_campaign_outcomes_summary(report_data: Any) -> str:
    summary = _mapping(_mapping(report_data).get("campaign_outcomes_summary"))
    if not summary:
        summary = _mapping(_mapping(report_data).get("operator_summary")).get("campaign_outcomes_summary") or {}
    return str(_mapping(summary).get("summary") or NO_CAMPAIGN_OUTCOMES_SUMMARY)


def build_next_monitoring_step_line(report_data: Any) -> str:
    step = _mapping(_mapping(report_data).get("next_monitoring_step"))
    if not step:
        step = _mapping(_mapping(report_data).get("operator_summary")).get("next_monitoring_step") or {}
    return str(_mapping(step).get("summary") or NO_NEXT_MONITORING_STEP)


def build_campaign_tuning_summary(report_data: Any) -> str:
    summary = _mapping(_mapping(report_data).get("campaign_tuning_summary"))
    if not summary:
        summary = _mapping(_mapping(report_data).get("operator_summary")).get("campaign_tuning_summary") or {}
    return str(_mapping(summary).get("summary") or NO_CAMPAIGN_TUNING_SUMMARY)


def build_next_tuned_campaign_line(report_data: Any) -> str:
    campaign = _mapping(_mapping(report_data).get("next_tuned_campaign"))
    if not campaign:
        campaign = _mapping(_mapping(report_data).get("operator_summary")).get("next_tuned_campaign") or {}
    return str(_mapping(campaign).get("summary") or NO_NEXT_TUNED_CAMPAIGN)


def build_next_tie_break_candidate_line(report_data: Any) -> str:
    return build_next_tuned_campaign_line(report_data)


def build_historical_portfolio_intelligence_summary(report_data: Any) -> str:
    summary = _mapping(_mapping(report_data).get("intervention_ledger_summary"))
    if not summary:
        summary = _mapping(_mapping(report_data).get("operator_summary")).get("intervention_ledger_summary") or {}
    return str(_mapping(summary).get("summary") or NO_HISTORICAL_PORTFOLIO_INTELLIGENCE_SUMMARY)


def build_next_historical_focus_line(report_data: Any) -> str:
    focus = _mapping(_mapping(report_data).get("next_historical_focus"))
    if not focus:
        focus = _mapping(_mapping(report_data).get("operator_summary")).get("next_historical_focus") or {}
    return str(_mapping(focus).get("summary") or NO_NEXT_HISTORICAL_FOCUS)


def build_automation_guidance_summary(report_data: Any) -> str:
    summary = _mapping(_mapping(report_data).get("automation_guidance_summary"))
    if not summary:
        summary = _mapping(_mapping(report_data).get("operator_summary")).get("automation_guidance_summary") or {}
    return str(_mapping(summary).get("summary") or NO_AUTOMATION_GUIDANCE_SUMMARY)


def build_next_safe_automation_step_line(report_data: Any) -> str:
    step = _mapping(_mapping(report_data).get("next_safe_automation_step"))
    if not step:
        step = _mapping(_mapping(report_data).get("operator_summary")).get("next_safe_automation_step") or {}
    return str(_mapping(step).get("summary") or NO_NEXT_SAFE_AUTOMATION_STEP)


def build_approval_workflow_summary(report_data: Any) -> str:
    summary = _mapping(_mapping(report_data).get("approval_workflow_summary"))
    if not summary:
        summary = _mapping(_mapping(report_data).get("operator_summary")).get("approval_workflow_summary") or {}
    return str(_mapping(summary).get("summary") or NO_APPROVAL_WORKFLOW_SUMMARY)


def build_next_approval_review_line(report_data: Any) -> str:
    step = _mapping(_mapping(report_data).get("next_approval_review"))
    if not step:
        step = _mapping(_mapping(report_data).get("operator_summary")).get("next_approval_review") or {}
    return str(_mapping(step).get("summary") or NO_NEXT_APPROVAL_REVIEW)


def build_historical_intelligence_line(value: Any) -> str:
    mapped = _mapping(value)
    direct = str(mapped.get("historical_intelligence_line") or "").strip()
    if direct:
        return direct
    summary = str(mapped.get("historical_intelligence_summary") or "").strip()
    if summary:
        return f"Historical Portfolio Intelligence: {summary}"
    status = str(mapped.get("historical_intelligence_status") or "").strip()
    if status:
        return f"Historical Portfolio Intelligence: {status}."
    return NO_HISTORICAL_INTELLIGENCE_LINE


def build_approval_workflow_line(value: Any) -> str:
    mapped = _mapping(value)
    direct = str(mapped.get("approval_line") or "").strip()
    if direct:
        return direct
    summary = str(mapped.get("approval_summary") or "").strip()
    state = str(mapped.get("approval_state") or "").strip()
    if not summary and not state:
        return NO_APPROVAL_WORKFLOW_LINE
    return f"{ACTION_SYNC_CANONICAL_LABELS['approval_workflow']}: {summary or state.replace('-', ' ').title()}"


def build_automation_line(value: Any) -> str:
    mapped = _mapping(value)
    direct = str(mapped.get("automation_line") or "").strip()
    if direct:
        return direct
    summary = str(mapped.get("automation_summary") or "").strip()
    if summary:
        return f"{ACTION_SYNC_CANONICAL_LABELS['automation_guidance']}: {summary}"
    posture = str(mapped.get("automation_posture") or "").strip()
    if posture:
        return f"{ACTION_SYNC_CANONICAL_LABELS['automation_guidance']}: {posture.replace('-', ' ')}."
    return NO_AUTOMATION_GUIDANCE_LINE


def build_action_sync_line(value: Any) -> str:
    mapped = _mapping(value)
    direct = str(mapped.get("action_sync_line") or "").strip()
    if direct:
        return direct
    stage = str(mapped.get("action_sync_stage") or "").strip()
    campaign = str(mapped.get("suggested_campaign") or "").strip()
    target = str(mapped.get("suggested_writeback_target") or "").strip()
    if not stage and not campaign:
        return NO_ACTION_SYNC_LINE
    campaign_label = PRODUCT_MODE_LABELS.get(campaign, campaign.replace("-", " ").title()) if campaign in PRODUCT_MODE_LABELS else campaign.replace("-", " ").title()
    if target and target != "none":
        return f"Action Sync: {campaign_label or 'Campaign'} is {stage or 'idle'} — recommended target {target}."
    return f"Action Sync: {campaign_label or 'Campaign'} is {stage or 'idle'} — stay local until prerequisites are healthy."


def build_apply_packet_line(value: Any) -> str:
    mapped = _mapping(value)
    state = str(mapped.get("apply_packet_state") or "").strip()
    summary = str(mapped.get("apply_packet_summary") or "").strip()
    command = str(mapped.get("apply_packet_command") or "").strip()
    if not state and not summary:
        return "Apply Packet: no current execution handoff is surfaced."
    if command:
        return f"Apply Packet: {summary} Command: {command}"
    return f"Apply Packet: {summary or state.replace('-', ' ').title()}"


def build_post_apply_monitoring_line(value: Any) -> str:
    mapped = _mapping(value)
    direct = str(mapped.get("post_apply_line") or "").strip()
    if direct:
        return direct
    summary = str(mapped.get("post_apply_summary") or "").strip()
    state = str(mapped.get("post_apply_state") or "").strip()
    if not summary and not state:
        return NO_POST_APPLY_MONITORING_LINE
    return f"Post-Apply Monitoring: {summary or state.replace('-', ' ').title()}"


def build_campaign_tuning_line(value: Any) -> str:
    mapped = _mapping(value)
    direct = str(mapped.get("campaign_tuning_line") or "").strip()
    if direct:
        return direct
    summary = str(mapped.get("campaign_tuning_summary") or "").strip()
    status = str(mapped.get("campaign_tuning_status") or "").strip()
    if not summary and not status:
        return NO_CAMPAIGN_TUNING_LINE
    return f"Campaign Tuning: {summary or status.replace('-', ' ').title()}"


def _build_operator_focus_item(mapped: dict[str, Any], review_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "repo": mapped.get("repo") or mapped.get("repo_name") or "Portfolio",
        "title": str(mapped.get("title") or mapped.get("summary") or "Operator attention item"),
        "lane": mapped.get("lane_label") or mapped.get("lane") or "ready",
        "why": str(mapped.get("lane_reason") or mapped.get("summary") or "Operator pressure is active."),
        "next_step": str(
            mapped.get("recommended_action")
            or mapped.get("next_step")
            or "Review the latest repo state."
        ),
        "last_movement": build_last_movement_label(mapped, review_summary),
        "follow_through_status": build_follow_through_status_label(mapped),
        "follow_through_summary": build_follow_through_summary(mapped),
        "follow_through_checkpoint": build_follow_through_checkpoint(mapped),
        "follow_through_checkpoint_timing": build_follow_through_checkpoint_status_label(mapped),
        "follow_through_escalation": build_follow_through_escalation_status_label(mapped),
        "follow_through_escalation_summary": build_follow_through_escalation_summary(mapped),
        "follow_through_recovery": build_follow_through_recovery_status_label(mapped),
        "follow_through_recovery_summary": build_follow_through_recovery_summary(mapped),
        "follow_through_recovery_persistence": build_follow_through_recovery_persistence_status_label(mapped),
        "follow_through_recovery_persistence_summary": build_follow_through_recovery_persistence_summary(mapped),
        "follow_through_relapse_churn": build_follow_through_relapse_churn_status_label(mapped),
        "follow_through_relapse_churn_summary": build_follow_through_relapse_churn_summary(mapped),
        "follow_through_recovery_freshness": build_follow_through_recovery_freshness_status_label(mapped),
        "follow_through_recovery_freshness_summary": build_follow_through_recovery_freshness_summary(mapped),
        "follow_through_recovery_decay": build_follow_through_recovery_decay_status_label(mapped),
        "follow_through_recovery_decay_summary": build_follow_through_recovery_decay_summary(mapped),
        "follow_through_recovery_memory_reset": build_follow_through_recovery_memory_reset_status_label(mapped),
        "follow_through_recovery_memory_reset_summary": build_follow_through_recovery_memory_reset_summary(mapped),
        "follow_through_recovery_rebuild_strength": build_follow_through_recovery_rebuild_strength_status_label(mapped),
        "follow_through_recovery_rebuild_strength_summary": build_follow_through_recovery_rebuild_strength_summary(mapped),
        "follow_through_recovery_reacquisition": build_follow_through_recovery_reacquisition_status_label(mapped),
        "follow_through_recovery_reacquisition_summary": build_follow_through_recovery_reacquisition_summary(mapped),
        "follow_through_reacquisition_durability": build_follow_through_reacquisition_durability_status_label(mapped),
        "follow_through_reacquisition_durability_summary": build_follow_through_reacquisition_durability_summary(mapped),
        "follow_through_reacquisition_confidence": build_follow_through_reacquisition_consolidation_status_label(mapped),
        "follow_through_reacquisition_confidence_summary": build_follow_through_reacquisition_consolidation_summary(mapped),
        "follow_through_reacquisition_softening_decay": build_follow_through_reacquisition_softening_decay_status_label(mapped),
        "follow_through_reacquisition_softening_decay_summary": build_follow_through_reacquisition_softening_decay_summary(mapped),
        "follow_through_reacquisition_confidence_retirement": build_follow_through_reacquisition_confidence_retirement_status_label(mapped),
        "follow_through_reacquisition_confidence_retirement_summary": build_follow_through_reacquisition_confidence_retirement_summary(mapped),
        "follow_through_reacquisition_revalidation_recovery": build_follow_through_reacquisition_revalidation_recovery_status_label(mapped),
        "follow_through_reacquisition_revalidation_recovery_summary": build_follow_through_reacquisition_revalidation_recovery_summary(mapped),
        "operator_focus": build_operator_focus(mapped),
        "operator_focus_summary": build_operator_focus_summary(mapped),
        "operator_focus_line": build_operator_focus_line(mapped),
        "catalog_line": build_portfolio_catalog_line(mapped),
        "intent_alignment": build_intent_alignment_status(mapped),
        "intent_alignment_summary": build_intent_alignment_summary(mapped),
        "scorecard_line": build_scorecard_line(mapped),
        "maturity_gap_summary": build_maturity_gap_summary(mapped),
        "action_sync_stage": str(mapped.get("action_sync_stage") or "idle"),
        "action_sync_reason": str(mapped.get("action_sync_reason") or "No current Action Sync guidance is surfaced for this item."),
        "suggested_campaign": str(mapped.get("suggested_campaign") or ""),
        "suggested_writeback_target": str(mapped.get("suggested_writeback_target") or "none"),
        "action_sync_line": build_action_sync_line(mapped),
        "apply_packet_state": str(mapped.get("apply_packet_state") or "stay-local"),
        "apply_packet_summary": str(mapped.get("apply_packet_summary") or "No current apply packet is surfaced for this item."),
        "apply_packet_command": str(mapped.get("apply_packet_command") or ""),
        "apply_packet_line": build_apply_packet_line(mapped),
        "post_apply_state": str(mapped.get("post_apply_state") or "no-recent-apply"),
        "post_apply_summary": str(mapped.get("post_apply_summary") or "No post-apply monitoring is surfaced for this item yet."),
        "post_apply_line": build_post_apply_monitoring_line(mapped),
        "campaign_tuning_status": str(mapped.get("campaign_tuning_status") or "insufficient-evidence"),
        "campaign_tuning_summary": str(mapped.get("campaign_tuning_summary") or "No campaign tuning evidence is surfaced for this item yet."),
        "campaign_tuning_line": build_campaign_tuning_line(mapped),
        "approval_state": str(mapped.get("approval_state") or "not-applicable"),
        "approval_summary": str(mapped.get("approval_summary") or "No approval workflow is surfaced for this item yet."),
        "approval_line": build_approval_workflow_line(mapped),
        "automation_posture": str(mapped.get("automation_posture") or "manual-only"),
        "automation_summary": str(mapped.get("automation_summary") or "No automation guidance is surfaced for this item yet."),
        "automation_command": str(mapped.get("automation_command") or ""),
        "automation_line": build_automation_line(mapped),
    }


def _build_operator_focus_summary_from_groups(grouped_items: dict[str, list[dict[str, Any]]]) -> str:
    counts = {bucket: len(grouped_items.get(bucket, [])) for bucket in OPERATOR_FOCUS_DISPLAY_ORDER}

    def _labels(bucket: str) -> str:
        items = grouped_items.get(bucket, [])[:3]
        labels = [str(item.get("repo") or item.get("title") or "operator item") for item in items]
        return _string_list(labels, fallback="the current queue")

    if counts["act-now"]:
        return (
            f"{counts['act-now']} item(s) need immediate action first, led by {_labels('act-now')}."
        )
    if counts["revalidate"]:
        return (
            f"{counts['revalidate']} item(s) are in a revalidation posture, led by {_labels('revalidate')}."
        )
    if counts["fragile"]:
        return (
            f"{counts['fragile']} item(s) are improving but still fragile, led by {_labels('fragile')}."
        )
    if counts["improving"]:
        return (
            f"{counts['improving']} item(s) are clearly improving, led by {_labels('improving')}."
        )
    if counts["watch-closely"]:
        return (
            f"{counts['watch-closely']} item(s) should stay visible while more evidence arrives, led by {_labels('watch-closely')}."
        )
    return NO_OPERATOR_FOCUS_SUMMARY


def build_follow_through_resurfacing_reason(value: Any) -> str:
    mapped = _mapping(value)
    return str(
        mapped.get("follow_through_escalation_reason")
        or mapped.get("follow_through_escalation_summary")
        or NO_FOLLOW_THROUGH_ESCALATION
    )


def build_action_handoff_summary(value: Any) -> str:
    mapped = _mapping(value)
    action = str(mapped.get("recommended_action") or mapped.get("next_step") or "").strip()
    if action:
        return action
    return "Review the latest state and choose the next concrete follow-through step."


def build_queue_pressure_summary(report_data: Any, diff_data: dict | None = None) -> str:
    data = _mapping(report_data)
    operator_summary = _mapping(data.get("operator_summary"))
    counts = _mapping(operator_summary.get("counts"))
    if counts:
        return (
            f"{counts.get('blocked', 0)} blocked, "
            f"{counts.get('urgent', 0)} urgent, "
            f"{counts.get('ready', 0)} ready, and "
            f"{counts.get('deferred', 0)} deferred item(s) are currently in the queue."
        )

    run_change_counts = data.get("run_change_counts") or build_run_change_counts(diff_data)
    return (
        f"{run_change_counts.get('score_improvements', 0)} improving, "
        f"{run_change_counts.get('score_regressions', 0)} regressing, "
        f"{run_change_counts.get('tier_promotions', 0)} promoted, and "
        f"{run_change_counts.get('tier_demotions', 0)} demoted."
    )


def build_top_recommendation_summary(report_data: Any) -> str:
    data = _mapping(report_data)
    operator_summary = _mapping(data.get("operator_summary"))
    if operator_summary.get("what_to_do_next"):
        return str(operator_summary.get("what_to_do_next"))

    queue = list(data.get("operator_queue") or [])
    if queue:
        first = _mapping(queue[0])
        action = (
            first.get("recommended_action")
            or first.get("next_step")
            or first.get("title")
            or "Review the latest operator item."
        )
        repo = first.get("repo") or first.get("repo_name")
        if repo and repo not in str(action):
            return f"{repo}: {action}"
        return str(action)

    return "Continue the normal operator review loop."


def build_trust_actionability_summary(report_data: Any) -> str:
    data = _mapping(report_data)
    operator_summary = _mapping(data.get("operator_summary"))
    trust_policy = operator_summary.get("primary_target_trust_policy")
    trust_reason = operator_summary.get("primary_target_trust_policy_reason")
    if trust_policy and trust_reason:
        return f"{trust_policy} — {trust_reason}"
    if trust_policy:
        return str(trust_policy)
    if trust_reason:
        return str(trust_reason)
    return "No trust-policy guidance is recorded yet."


def build_last_movement_label(item: dict[str, Any], review_summary: dict[str, Any] | None = None) -> str:
    updated_at = item.get("updated_at")
    if updated_at:
        return f"Updated {str(updated_at)[:10]}"
    created_at = item.get("created_at")
    if created_at:
        return f"Opened {str(created_at)[:10]}"
    source_run_id = item.get("source_run_id")
    if source_run_id:
        return f"Seen in run {str(source_run_id).split(':')[-1]}"
    generated_at = _mapping(review_summary).get("generated_at")
    if generated_at:
        return f"Seen in run {str(generated_at)[:10]}"
    return "Current run"
