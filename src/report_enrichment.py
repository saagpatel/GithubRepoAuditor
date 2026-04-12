from __future__ import annotations

import re
from typing import Any

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


def _string_list(items: list[str], *, fallback: str) -> str:
    cleaned = [str(item).strip() for item in items if str(item).strip()]
    return ", ".join(cleaned[:3]) if cleaned else fallback


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
        explanation = build_score_explanation(audit)
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
    follow_through_resurfacing_reason = build_follow_through_resurfacing_reason(handoff_source)
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
            "what_would_count_as_progress": follow_through_checkpoint,
        },
        "what_to_do_next_line": f"{recommended_action} {next_best_action_rationale}".strip(),
        "follow_through_line": f"{follow_through_status}: {follow_through_summary}",
        "checkpoint_line": follow_through_checkpoint,
        "checkpoint_timing_line": follow_through_checkpoint_timing,
        "escalation_line": f"{follow_through_escalation}: {follow_through_escalation_summary}",
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
        title = mapped.get("title") or mapped.get("summary") or "Operator attention item"
        repo = mapped.get("repo") or mapped.get("repo_name") or "Portfolio"
        top_attention.append(
            {
                "repo": repo,
                "title": str(title),
                "lane": mapped.get("lane_label") or mapped.get("lane") or "ready",
                "why": str(mapped.get("lane_reason") or mapped.get("summary") or "Operator pressure is active."),
                "next_step": str(mapped.get("recommended_action") or mapped.get("next_step") or "Review the latest repo state."),
                "last_movement": build_last_movement_label(mapped, review_summary),
                "follow_through_status": build_follow_through_status_label(mapped),
                "follow_through_summary": build_follow_through_summary(mapped),
                "follow_through_checkpoint": build_follow_through_checkpoint(mapped),
                "follow_through_checkpoint_timing": build_follow_through_checkpoint_status_label(mapped),
                "follow_through_escalation": build_follow_through_escalation_status_label(mapped),
                "follow_through_escalation_summary": build_follow_through_escalation_summary(mapped),
            }
        )
    top_recommendation = build_top_recommendation_summary(data)
    what_to_do_this_week = top_recommendation
    if repo_briefings:
        what_to_do_this_week = f"{top_recommendation} Start with {repo_briefings[0]['repo']} if you need a concrete place to begin."
    return {
        "portfolio_headline": str(portfolio_headline),
        "run_change_summary": build_run_change_summary(diff_data if diff_data is not None else data.get("diff_data")),
        "queue_pressure_summary": build_queue_pressure_summary(data, diff_data),
        "trust_actionability_summary": build_trust_actionability_summary(data),
        "top_recommendation_summary": top_recommendation,
        "top_attention": top_attention,
        "repo_briefings": repo_briefings,
        "what_to_do_this_week": what_to_do_this_week,
        "follow_through_summary": str(operator_summary.get("follow_through_summary") or NO_FOLLOW_THROUGH_SUMMARY),
        "follow_through_checkpoint_summary": str(
            operator_summary.get("follow_through_checkpoint_summary") or NO_FOLLOW_THROUGH_CHECKPOINT
        ),
        "follow_through_escalation_summary": str(
            operator_summary.get("follow_through_escalation_summary") or NO_FOLLOW_THROUGH_ESCALATION
        ),
        "top_unattempted_items": list(operator_summary.get("top_unattempted_items") or []),
        "top_stale_follow_through_items": list(operator_summary.get("top_stale_follow_through_items") or []),
        "top_overdue_follow_through_items": list(operator_summary.get("top_overdue_follow_through_items") or []),
        "top_escalation_items": list(operator_summary.get("top_escalation_items") or []),
    }


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
