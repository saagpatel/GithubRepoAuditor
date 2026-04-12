from __future__ import annotations

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


def _metadata(audit: Any) -> dict[str, Any]:
    metadata = getattr(audit, "metadata", None)
    if metadata is None:
        return (audit or {}).get("metadata", {})
    if hasattr(metadata, "to_dict"):
        return metadata.to_dict()
    return metadata


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
        return "No prior run comparison is available yet."

    counts = build_run_change_counts(diff_data)
    return (
        f"Average score moved {diff_data.get('average_score_delta', 0.0):+.3f}; "
        f"{counts['score_improvements']} meaningful improvements, "
        f"{counts['score_regressions']} regressions, "
        f"{counts['tier_promotions']} promotions, "
        f"and {counts['tier_demotions']} demotions were recorded."
    )
