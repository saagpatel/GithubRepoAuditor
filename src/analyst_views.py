from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

from src.warehouse import WAREHOUSE_FILENAME


def _normalize_profile_name(report_data: dict, profile_name: str | None) -> str:
    profiles = report_data.get("profiles", {})
    if profile_name and profile_name in profiles:
        return profile_name
    return "default" if "default" in profiles else (next(iter(profiles.keys()), "default"))


def collection_membership_map(report_data: dict) -> dict[str, list[str]]:
    memberships: dict[str, list[str]] = {}
    for collection_name, collection_data in report_data.get("collections", {}).items():
        for repo_data in collection_data.get("repos", []):
            repo_name = repo_data["name"] if isinstance(repo_data, dict) else str(repo_data)
            memberships.setdefault(repo_name, []).append(collection_name)
    return memberships


def filter_audits_by_collection(report_data: dict, collection_name: str | None = None) -> list[dict]:
    audits = list(report_data.get("audits", []))
    if not collection_name:
        return audits
    memberships = collection_membership_map(report_data)
    return [
        audit
        for audit in audits
        if collection_name in memberships.get(audit.get("metadata", {}).get("name", ""), [])
    ]


def compute_profile_score_for_audit(audit: dict, profiles: dict[str, dict], profile_name: str) -> float:
    profile = profiles.get(profile_name) or profiles.get("default", {})
    weights = profile.get("lens_weights", {})
    if not weights:
        return round(audit.get("overall_score", 0), 3)

    score = 0.0
    lenses = audit.get("lenses", {})
    for lens_name, weight in weights.items():
        score += lenses.get(lens_name, {}).get("score", 0.0) * weight
    return round(score, 3)


def rank_audits_for_profile(
    report_data: dict,
    profile_name: str | None = None,
    collection_name: str | None = None,
) -> list[dict]:
    normalized_profile = _normalize_profile_name(report_data, profile_name)
    profiles = report_data.get("profiles", {})
    memberships = collection_membership_map(report_data)
    ranked: list[dict] = []

    for audit in filter_audits_by_collection(report_data, collection_name):
        name = audit.get("metadata", {}).get("name", "")
        ranked.append({
            "name": name,
            "profile_score": compute_profile_score_for_audit(audit, profiles, normalized_profile),
            "overall_score": round(audit.get("overall_score", 0), 3),
            "interest_score": round(audit.get("interest_score", 0), 3),
            "tier": audit.get("completeness_tier", ""),
            "grade": audit.get("grade", ""),
            "collections": memberships.get(name, []),
            "hotspot_count": len(audit.get("hotspots", [])),
            "security_label": audit.get("security_posture", {}).get("label", "unknown"),
            "primary_hotspot": audit.get("hotspots", [{}])[0].get("title", "") if audit.get("hotspots") else "",
            "lenses": audit.get("lenses", {}),
            "audit": audit,
        })

    ranked.sort(
        key=lambda item: (
            item["profile_score"],
            item["overall_score"],
            item["interest_score"],
        ),
        reverse=True,
    )
    return ranked


def build_profile_leaderboard(
    report_data: dict,
    profile_name: str | None = None,
    collection_name: str | None = None,
    limit: int = 5,
) -> dict:
    normalized_profile = _normalize_profile_name(report_data, profile_name)
    ranked = rank_audits_for_profile(report_data, normalized_profile, collection_name)
    return {
        "profile_name": normalized_profile,
        "collection_name": collection_name,
        "leaders": [
            {
                "name": item["name"],
                "profile_score": item["profile_score"],
                "overall_score": item["overall_score"],
                "tier": item["tier"],
            }
            for item in ranked[:limit]
        ],
    }


def summarize_collection_views(report_data: dict) -> list[dict]:
    summary = []
    for collection_name, collection_data in report_data.get("collections", {}).items():
        repos = collection_data.get("repos", [])
        summary.append({
            "name": collection_name,
            "count": len(repos),
            "description": collection_data.get("description", ""),
            "repos": [
                repo_data["name"] if isinstance(repo_data, dict) else str(repo_data)
                for repo_data in repos[:5]
            ],
        })
    return summary


def summarize_scenario_preview(
    report_data: dict,
    profile_name: str | None = None,
    collection_name: str | None = None,
) -> dict:
    normalized_profile = _normalize_profile_name(report_data, profile_name)
    profiles = report_data.get("profiles", {})
    weights = profiles.get(normalized_profile, {}).get("lens_weights", {})
    selected_audits = filter_audits_by_collection(report_data, collection_name)

    grouped: dict[str, dict] = defaultdict(lambda: {
        "title": "",
        "lens": "",
        "repo_count": 0,
        "expected_lens_delta_total": 0.0,
        "weighted_impact_total": 0.0,
        "projected_tier_promotions": 0,
    })

    for audit in selected_audits:
        for action in audit.get("action_candidates", [])[:2]:
            entry = grouped[action.get("key", action.get("title", ""))]
            entry["title"] = action.get("title", "")
            entry["lens"] = action.get("lens", "")
            entry["repo_count"] += 1
            entry["expected_lens_delta_total"] += action.get("expected_lens_delta", 0.0)
            entry["weighted_impact_total"] += action.get("expected_lens_delta", 0.0) * abs(weights.get(action.get("lens", ""), 1.0))
            if str(action.get("expected_tier_movement", "")).startswith("Closer to"):
                entry["projected_tier_promotions"] += 1

    top_levers = sorted(
        [
            {
                "key": key,
                "title": value["title"],
                "lens": value["lens"],
                "repo_count": value["repo_count"],
                "average_expected_lens_delta": round(value["expected_lens_delta_total"] / value["repo_count"], 3),
                "weighted_impact": round(value["weighted_impact_total"], 3),
                "projected_tier_promotions": value["projected_tier_promotions"],
            }
            for key, value in grouped.items()
            if value["repo_count"] > 0
        ],
        key=lambda item: (item["weighted_impact"], item["repo_count"], item["average_expected_lens_delta"]),
        reverse=True,
    )[:5]

    projected_average_score_delta = round(sum(item["average_expected_lens_delta"] for item in top_levers) * 0.08, 3) if top_levers else 0.0

    return {
        "profile_name": normalized_profile,
        "collection_name": collection_name,
        "top_levers": top_levers,
        "portfolio_projection": {
            "selected_repo_count": len(selected_audits),
            "projected_average_score_delta": projected_average_score_delta,
            "projected_tier_promotions": sum(item["projected_tier_promotions"] for item in top_levers),
        },
    }


def build_analyst_context(
    report_data: dict,
    *,
    profile_name: str | None = None,
    collection_name: str | None = None,
) -> dict:
    normalized_profile = _normalize_profile_name(report_data, profile_name)
    return {
        "profile_name": normalized_profile,
        "collection_name": collection_name,
        "ranked_audits": rank_audits_for_profile(report_data, normalized_profile, collection_name),
        "profile_leaderboard": build_profile_leaderboard(report_data, normalized_profile, collection_name),
        "collection_summary": summarize_collection_views(report_data),
        "scenario_preview": summarize_scenario_preview(report_data, normalized_profile, collection_name),
    }


def load_run_catalog(output_dir: Path, username: str) -> list[dict]:
    db_path = output_dir / WAREHOUSE_FILENAME
    if not db_path.is_file():
        return []

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT generated_at, report_path, run_mode, scoring_profile
            FROM audit_runs
            WHERE username = ? AND report_path IS NOT NULL
            ORDER BY generated_at DESC
            """,
            (username,),
        ).fetchall()
    finally:
        conn.close()

    return [
        {
            "generated_at": row[0],
            "report_path": row[1],
            "run_mode": row[2],
            "scoring_profile": row[3],
        }
        for row in rows
    ]


def load_previous_report_path(output_dir: Path, username: str, current_report_path: Path | None = None) -> Path | None:
    catalog = load_run_catalog(output_dir, username)
    if not catalog:
        return None
    current_str = str(current_report_path) if current_report_path else None
    for entry in catalog:
        report_path = entry.get("report_path")
        if not report_path:
            continue
        if current_str and report_path == current_str:
            continue
        path = Path(report_path)
        if path.is_file():
            return path
    return None


def load_report_snapshot(path: Path) -> dict:
    return json.loads(path.read_text())
