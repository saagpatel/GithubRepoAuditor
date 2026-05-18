from src.excel_template import TREND_HISTORY_WINDOW


def extend_score_history_with_current(
    data: dict,
    score_history: dict[str, list[float]] | None,
) -> dict[str, list[float]]:
    extended = {name: list(scores) for name, scores in (score_history or {}).items()}
    for audit in data.get("audits", []):
        name = audit.get("metadata", {}).get("name", "")
        if not name:
            continue
        current_score = round(audit.get("overall_score", 0), 3)
        history = extended.setdefault(name, [])
        if not history or abs(history[-1] - current_score) > 1e-9:
            history.append(current_score)
        extended[name] = history[-TREND_HISTORY_WINDOW:]
    return extended


def extend_portfolio_trend_with_current(
    data: dict,
    trend_data: list[dict] | None,
) -> list[dict]:
    trends = [dict(item) for item in (trend_data or [])]
    current = {
        "date": data.get("generated_at", "")[:10],
        "average_score": data.get("average_score", 0.0),
        "repos_audited": data.get("repos_audited", 0),
        "tier_distribution": data.get("tier_distribution", {}),
        "review_emitted": bool(data.get("material_changes")),
        "campaign_drift_count": len(data.get("managed_state_drift", []) or []),
        "governance_drift_count": len(data.get("governance_drift", []) or []),
    }
    if not trends or trends[-1].get("date") != current["date"]:
        trends.append(current)
    else:
        trends[-1] = current
    return trends[-TREND_HISTORY_WINDOW:]


def review_status_counts(data: dict) -> dict[str, int]:
    counts = {"open": 0, "deferred": 0, "resolved": 0}
    for item in data.get("review_history", []):
        status = item.get("status")
        if status in counts:
            counts[status] += 1
    review_summary = data.get("review_summary", {})
    review_id = review_summary.get("review_id")
    if review_id and not any(
        item.get("review_id") == review_id for item in data.get("review_history", [])
    ):
        status = review_summary.get("status")
        if status in counts:
            counts[status] += 1
    return counts
