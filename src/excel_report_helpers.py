def collection_memberships(data: dict) -> dict[str, list[str]]:
    memberships: dict[str, list[str]] = {}
    for collection_name, collection_data in data.get("collections", {}).items():
        for repo_data in collection_data.get("repos", []):
            repo_name = repo_data["name"] if isinstance(repo_data, dict) else str(repo_data)
            memberships.setdefault(repo_name, []).append(collection_name)
    return memberships


def display_operator_state(value: str | None) -> str:
    mapping = {
        "preview-only": "Preview only",
        "needs-reapproval": "Needs re-approval",
        "ready": "Ready",
        "approved": "Approved",
        "applied": "Applied",
        "blocked": "Blocked",
        "drifted": "Drifted",
        "failed": "Failed",
    }
    if not value:
        return "Unknown"
    return mapping.get(value, value.replace("-", " ").title())


def severity_rank(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    mapping = {"critical": 1.0, "high": 0.85, "medium": 0.55, "low": 0.25}
    return mapping.get(str(value).lower(), 0.0)


def generate_narrative(data: dict, diff_data: dict | None) -> str:
    """Auto-generate a one-line dashboard narrative."""
    if not diff_data:
        tiers = data.get("tier_distribution", {})
        return (
            f"Portfolio: {data['repos_audited']} repos analyzed. "
            f"{tiers.get('shipped', 0)} shipped, avg score {data['average_score']:.2f}."
        )

    parts = [f"Since last audit ({diff_data.get('previous_date', '')[:10]}):"]
    shipped_d = diff_data.get("tier_distribution_delta", {}).get("shipped", 0)
    avg_d = diff_data.get("average_score_delta", 0)
    promos = len(diff_data.get("tier_changes", []))
    new_count = len(diff_data.get("new_repos", []))

    if shipped_d:
        parts.append(f"{shipped_d:+d} shipped")
    if abs(avg_d) > 0.005:
        parts.append(f"avg score {avg_d:+.3f}")
    if promos:
        parts.append(f"{promos} tier changes")
    if new_count:
        parts.append(f"{new_count} new repos")

    tier_next = {"functional": 0.75, "wip": 0.55, "skeleton": 0.35}
    closest_name, closest_gap = None, 1.0
    for audit in data.get("audits", []):
        tier = audit.get("completeness_tier", "")
        if tier in tier_next:
            gap = tier_next[tier] - audit.get("overall_score", 0)
            if 0 < gap < closest_gap:
                closest_gap = gap
                closest_name = audit["metadata"]["name"]
    if closest_name:
        parts.append(f"Priority: {closest_name} needs {closest_gap:.3f} to promote")

    return " | ".join(parts)
