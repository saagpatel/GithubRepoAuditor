from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone

from src.models import AnalyzerResult, RepoAudit, RepoMetadata
from src.security_intelligence import build_security_governance_preview

REPORT_SCHEMA_VERSION = "3.7"

LENS_DEFINITIONS: dict[str, dict[str, str]] = {
    "ship_readiness": {
        "orientation": "higher-is-better",
        "description": "How confidently this repo could be shipped or resumed today.",
    },
    "maintenance_risk": {
        "orientation": "higher-is-riskier",
        "description": "How fragile the repo looks if it needs sustained maintenance.",
    },
    "showcase_value": {
        "orientation": "higher-is-better",
        "description": "How strong this repo is as a portfolio or hiring signal.",
    },
    "security_posture": {
        "orientation": "higher-is-better",
        "description": "How well the repo handles basic security and supply-chain hygiene.",
    },
    "momentum": {
        "orientation": "higher-is-better",
        "description": "How alive the repo feels based on activity, freshness, and follow-through.",
    },
    "portfolio_fit": {
        "orientation": "higher-is-better",
        "description": "How well this repo fits the default balanced portfolio profile.",
    },
}

DEFAULT_PROFILES: dict[str, dict] = {
    "default": {
        "description": "Balanced portfolio ranking across shipping confidence, story, and risk.",
        "lens_weights": {
            "ship_readiness": 0.25,
            "maintenance_risk": -0.15,
            "showcase_value": 0.20,
            "security_posture": 0.15,
            "momentum": 0.10,
            "portfolio_fit": 0.45,
        },
    },
    "shipping": {
        "description": "Prioritizes repos that can be pushed toward shipped quickly.",
        "lens_weights": {
            "ship_readiness": 0.45,
            "maintenance_risk": -0.10,
            "showcase_value": 0.10,
            "security_posture": 0.15,
            "momentum": 0.10,
            "portfolio_fit": 0.10,
        },
    },
    "job-search": {
        "description": "Prioritizes polished, narrative-friendly work for portfolio curation.",
        "lens_weights": {
            "ship_readiness": 0.20,
            "maintenance_risk": -0.10,
            "showcase_value": 0.35,
            "security_posture": 0.10,
            "momentum": 0.10,
            "portfolio_fit": 0.15,
        },
    },
    "maintenance": {
        "description": "Prioritizes repos that are safest to sustain and improve over time.",
        "lens_weights": {
            "ship_readiness": 0.15,
            "maintenance_risk": -0.35,
            "showcase_value": 0.05,
            "security_posture": 0.15,
            "momentum": 0.10,
            "portfolio_fit": 0.20,
        },
    },
    "security-first": {
        "description": "Prioritizes repos that need or demonstrate security investment.",
        "lens_weights": {
            "ship_readiness": 0.10,
            "maintenance_risk": -0.15,
            "showcase_value": 0.05,
            "security_posture": 0.45,
            "momentum": 0.05,
            "portfolio_fit": 0.10,
        },
    },
}

DEFAULT_COLLECTION_DESCRIPTIONS = {
    "showcase": "Repos most worth highlighting publicly right now.",
    "finish-next": "Repos closest to meaningful promotion with limited effort.",
    "secure-now": "Repos that would benefit most from immediate security posture work.",
    "archive-soon": "Repos with low momentum and low showcase value that may be ready to retire.",
}

TIER_THRESHOLDS = {
    "abandoned": 0.0,
    "skeleton": 0.15,
    "wip": 0.35,
    "functional": 0.55,
    "shipped": 0.75,
}

DIMENSION_ACTION_HINTS: dict[str, dict[str, str]] = {
    "readme": {
        "title": "Upgrade README",
        "action": "Add install, usage, and project intent sections to the README.",
        "lens": "showcase_value",
        "effort": "small",
    },
    "testing": {
        "title": "Strengthen tests",
        "action": "Add or expand a real test suite with at least one reliable happy path.",
        "lens": "ship_readiness",
        "effort": "medium",
    },
    "cicd": {
        "title": "Add CI automation",
        "action": "Set up a CI workflow that runs install, lint, and tests on every push.",
        "lens": "ship_readiness",
        "effort": "medium",
    },
    "dependencies": {
        "title": "Refresh dependency hygiene",
        "action": "Add or refresh lockfiles and dependency update automation.",
        "lens": "security_posture",
        "effort": "small",
    },
    "activity": {
        "title": "Show active ownership",
        "action": "Land a fresh commit, release note, or cleanup pass to prove momentum.",
        "lens": "momentum",
        "effort": "small",
    },
    "documentation": {
        "title": "Expand project docs",
        "action": "Add docs, changelog notes, or roadmap context beyond the README.",
        "lens": "showcase_value",
        "effort": "small",
    },
    "build_readiness": {
        "title": "Tighten build readiness",
        "action": "Add build/run instructions plus deployable scripts or config.",
        "lens": "ship_readiness",
        "effort": "medium",
    },
    "code_quality": {
        "title": "Reduce code drag",
        "action": "Clarify entry points, reduce TODO/FIXME debt, and harden core flows.",
        "lens": "maintenance_risk",
        "effort": "medium",
    },
    "security": {
        "title": "Improve security posture",
        "action": "Add SECURITY.md, Dependabot, and remove or quarantine risky files or secrets.",
        "lens": "security_posture",
        "effort": "medium",
    },
    "structure": {
        "title": "Clean up project structure",
        "action": "Organize source/config files into a clearer, reproducible layout.",
        "lens": "ship_readiness",
        "effort": "medium",
    },
    "community_profile": {
        "title": "Add contributor-facing polish",
        "action": "Add license, contribution notes, and project metadata that reduce ambiguity.",
        "lens": "maintenance_risk",
        "effort": "small",
    },
}


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 3)


def _score_map(results: list[AnalyzerResult]) -> dict[str, float]:
    return {result.dimension: result.score for result in results}


def _details_map(results: list[AnalyzerResult]) -> dict[str, dict]:
    return {result.dimension: result.details for result in results}


def _weighted_blend(score_map: dict[str, float], weights: dict[str, float]) -> float:
    weighted_sum = 0.0
    weight_sum = 0.0
    for dimension, weight in weights.items():
        weighted_sum += score_map.get(dimension, 0.0) * weight
        weight_sum += weight
    return weighted_sum / weight_sum if weight_sum else 0.0


def _days_since_push(metadata: RepoMetadata, activity_details: dict) -> int | None:
    if isinstance(activity_details.get("days_since_push"), int):
        return activity_details["days_since_push"]
    if metadata.pushed_at is None:
        return None
    return max(0, (datetime.now(timezone.utc) - metadata.pushed_at).days)


def _freshness_score(metadata: RepoMetadata, activity_details: dict) -> float:
    days_since_push = _days_since_push(metadata, activity_details)
    if days_since_push is None:
        return 0.0
    return _clamp(1.0 - min(days_since_push, 365) / 365)


def _top_and_bottom_drivers(score_map: dict[str, float], dimensions: list[str]) -> tuple[list[str], list[str]]:
    pairs = [(dimension, score_map.get(dimension, 0.0)) for dimension in dimensions]
    ordered = sorted(pairs, key=lambda item: item[1], reverse=True)
    strongest = [f"{dimension}={score:.2f}" for dimension, score in ordered[:2]]
    weakest = [f"{dimension}={score:.2f}" for dimension, score in ordered[-2:]]
    return strongest, weakest


def compute_lens_scores(
    metadata: RepoMetadata,
    results: list[AnalyzerResult],
    overall_score: float,
    interest_score: float,
    security_posture: dict | None = None,
) -> dict[str, dict]:
    score_map = _score_map(results)
    details_map = _details_map(results)
    activity_details = details_map.get("activity", {})
    security_details = details_map.get("security", {})
    posture = security_posture or {}

    freshness = _freshness_score(metadata, activity_details)
    activity_score = score_map.get("activity", 0.0)
    security_base = posture.get("score", score_map.get("security", max(0.25, score_map.get("dependencies", 0.0))))
    stars_signal = min(metadata.stars / 10.0, 1.0)
    release_count = activity_details.get("release_count", 0) or 0
    release_signal = min(release_count / 4.0, 1.0)

    ship_readiness = _clamp(_weighted_blend(score_map, {
        "readme": 0.10,
        "structure": 0.12,
        "code_quality": 0.15,
        "testing": 0.22,
        "cicd": 0.16,
        "build_readiness": 0.18,
        "documentation": 0.07,
    }))
    maintenance_health = _weighted_blend(score_map, {
        "code_quality": 0.24,
        "testing": 0.16,
        "dependencies": 0.14,
        "activity": 0.20,
        "documentation": 0.12,
        "community_profile": 0.14,
    })
    maintenance_risk = _clamp(
        1.0 - maintenance_health
        + (0.08 if metadata.archived else 0.0)
        + (0.08 if freshness < 0.25 else 0.0)
    )

    security_posture_score = _clamp(
        security_base
        + (0.02 if posture.get("github", {}).get("provider_available") else 0.0)
        + (0.02 if posture.get("scorecard", {}).get("available") else 0.0)
    )
    showcase_value = _clamp(
        overall_score * 0.25
        + interest_score * 0.35
        + freshness * 0.15
        + activity_score * 0.15
        + stars_signal * 0.10
    )
    momentum = _clamp(
        activity_score * 0.45
        + freshness * 0.25
        + interest_score * 0.20
        + release_signal * 0.10
    )
    portfolio_fit = _clamp(
        overall_score * 0.30
        + ship_readiness * 0.20
        + (1.0 - maintenance_risk) * 0.15
        + showcase_value * 0.15
        + security_posture_score * 0.10
        + momentum * 0.10
    )

    ship_strong, ship_weak = _top_and_bottom_drivers(
        score_map,
        ["testing", "cicd", "build_readiness", "structure", "readme", "code_quality"],
    )
    maintain_strong, maintain_weak = _top_and_bottom_drivers(
        score_map,
        ["code_quality", "testing", "dependencies", "documentation", "community_profile", "activity"],
    )
    showcase_strong, showcase_weak = _top_and_bottom_drivers(
        score_map,
        ["interest", "activity", "documentation", "readme", "build_readiness"],
    )

    return {
        "ship_readiness": {
            "score": ship_readiness,
            "orientation": LENS_DEFINITIONS["ship_readiness"]["orientation"],
            "summary": f"Best signals: {', '.join(ship_strong)}. Biggest drags: {', '.join(ship_weak)}.",
            "drivers": ship_strong,
        },
        "maintenance_risk": {
            "score": maintenance_risk,
            "orientation": LENS_DEFINITIONS["maintenance_risk"]["orientation"],
            "summary": f"Higher means riskier. Health anchors: {', '.join(maintain_strong)}. Weak points: {', '.join(maintain_weak)}.",
            "drivers": maintain_weak,
        },
        "showcase_value": {
            "score": showcase_value,
            "orientation": LENS_DEFINITIONS["showcase_value"]["orientation"],
            "summary": f"Portfolio story is driven by {', '.join(showcase_strong)} and held back by {', '.join(showcase_weak)}.",
            "drivers": showcase_strong,
        },
        "security_posture": {
            "score": security_posture_score,
            "orientation": LENS_DEFINITIONS["security_posture"]["orientation"],
            "summary": (
                f"Secrets={posture.get('secrets_found', security_details.get('secrets_found', 0))}, "
                f"Dependabot={'yes' if posture.get('has_dependabot', security_details.get('has_dependabot', False)) else 'no'}, "
                f"SECURITY.md={'yes' if posture.get('has_security_md', security_details.get('has_security_md', False)) else 'no'}, "
                f"GitHub={'yes' if posture.get('github', {}).get('provider_available') else 'no'}."
            ),
            "drivers": [
                f"security={security_posture_score:.2f}",
                f"dependencies={score_map.get('dependencies', 0.0):.2f}",
            ],
        },
        "momentum": {
            "score": momentum,
            "orientation": LENS_DEFINITIONS["momentum"]["orientation"],
            "summary": f"Freshness={freshness:.2f}, activity={activity_score:.2f}, interest={interest_score:.2f}.",
            "drivers": [
                f"activity={activity_score:.2f}",
                f"freshness={freshness:.2f}",
                f"releases={release_count}",
            ],
        },
        "portfolio_fit": {
            "score": portfolio_fit,
            "orientation": LENS_DEFINITIONS["portfolio_fit"]["orientation"],
            "summary": "Balanced fit across shipping confidence, story, and sustainability.",
            "drivers": [
                f"overall={overall_score:.2f}",
                f"ship={ship_readiness:.2f}",
                f"showcase={showcase_value:.2f}",
            ],
        },
    }


def _dimension_scores(audit: RepoAudit) -> dict[str, float]:
    return {result.dimension: result.score for result in audit.analyzer_results}


def _dimension_details(audit: RepoAudit) -> dict[str, dict]:
    return {result.dimension: result.details for result in audit.analyzer_results}


def _next_tier_name(score: float) -> str | None:
    ordered = [("skeleton", 0.15), ("wip", 0.35), ("functional", 0.55), ("shipped", 0.75)]
    for tier_name, threshold in ordered:
        if score < threshold:
            return tier_name
    return None


def build_action_candidates(audit: RepoAudit) -> list[dict]:
    score_map = _dimension_scores(audit)
    security_score = audit.security_posture.get("score", score_map.get("security", 1.0))
    candidate_dims = dict(score_map)
    candidate_dims["security"] = security_score

    ordered = sorted(candidate_dims.items(), key=lambda item: item[1])
    actions: list[dict] = []
    next_tier = _next_tier_name(audit.overall_score)

    for dimension, score in ordered:
        hint = DIMENSION_ACTION_HINTS.get(dimension)
        if not hint:
            continue
        if dimension != "security" and score >= 0.72:
            continue

        expected_delta = round(min(0.18, max(0.04, (0.78 - score) * 0.18)), 3)
        confidence = round(0.95 if score < 0.35 else (0.8 if score < 0.55 else 0.65), 2)
        title = hint["title"]
        action_text = hint["action"]
        rationale = f"{dimension} is currently scoring {score:.2f}, making it one of the biggest drags on this repo."
        if dimension == "security":
            recommendation = next(iter(audit.security_posture.get("recommendations", [])), None)
            if recommendation:
                title = recommendation.get("title", title)
                action_text = recommendation.get("why", action_text)
                rationale = recommendation.get("why", rationale)
        actions.append({
            "key": dimension,
            "title": title,
            "action": action_text,
            "lens": hint["lens"],
            "effort": hint["effort"],
            "confidence": confidence,
            "expected_lens_delta": expected_delta,
            "expected_tier_movement": f"Closer to {next_tier}" if next_tier else "Protect current tier",
            "rationale": rationale,
        })
        if len(actions) == 4:
            break

    return actions


def build_hotspots(audit: RepoAudit) -> list[dict]:
    score_map = _dimension_scores(audit)
    activity_details = _dimension_details(audit).get("activity", {})
    activity_score = score_map.get("activity", 0.0)
    testing = score_map.get("testing", 0.0)
    cicd = score_map.get("cicd", 0.0)
    code_quality = score_map.get("code_quality", 0.0)
    security = audit.security_posture or {"score": score_map.get("security", 1.0), "secrets_found": 0}
    actions = audit.action_candidates or build_action_candidates(audit)
    top_action = actions[0]["title"] if actions else "Review repo posture"
    hotspots: list[dict] = []

    if activity_score >= 0.60 and min(testing, cicd, code_quality) <= 0.45:
        severity = round(min(1.0, activity_score * 0.40 + (1.0 - min(testing, cicd, code_quality)) * 0.60), 3)
        hotspots.append({
            "category": "behavioral-risk",
            "severity": severity,
            "title": "High-churn weak foundation",
            "summary": "Recent activity is landing on a weak base, which raises rework risk.",
            "recommended_action": top_action,
        })

    if audit.interest_score >= 0.45 and audit.overall_score < 0.55:
        severity = round(min(1.0, audit.interest_score * 0.55 + (0.55 - audit.overall_score) * 0.75), 3)
        hotspots.append({
            "category": "finish-line",
            "severity": severity,
            "title": "Promising but under-finished",
            "summary": "This repo has portfolio upside but is still incomplete enough to under-sell itself.",
            "recommended_action": top_action,
        })

    if security.get("score", 1.0) < 0.65 or security.get("secrets_found", 0) > 0:
        severity = round(min(1.0, (1.0 - security.get("score", 1.0)) + security.get("secrets_found", 0) * 0.08), 3)
        hotspots.append({
            "category": "security-debt",
            "severity": severity,
            "title": "Security posture needs attention",
            "summary": "Security signals are weak enough that the repo should be reviewed before it is promoted.",
            "recommended_action": next(
                (action["title"] for action in actions if action["lens"] == "security_posture"),
                top_action,
            ),
        })

    days_since_push = activity_details.get("days_since_push")
    if (
        audit.completeness_tier in {"skeleton", "abandoned"}
        or "stale-2yr" in audit.flags
        or (isinstance(days_since_push, int) and days_since_push > 365 and audit.interest_score < 0.25)
    ):
        severity = round(min(1.0, (1.0 - audit.overall_score) * 0.55 + max(0.0, 0.25 - audit.interest_score)), 3)
        hotspots.append({
            "category": "archive-candidate",
            "severity": severity,
            "title": "Archive review candidate",
            "summary": "Low momentum and low strategic upside suggest this repo may be ready to retire or bundle elsewhere.",
            "recommended_action": "Review for archive, consolidation, or explicit de-prioritization.",
        })

    hotspots.sort(key=lambda item: item["severity"], reverse=True)
    return hotspots[:3]


def _fallback_lens_value(audit: RepoAudit, lens_name: str) -> float:
    if lens_name == "maintenance_risk":
        return round(1.0 - audit.overall_score, 3)
    if lens_name == "showcase_value":
        return round(audit.overall_score * 0.5 + audit.interest_score * 0.5, 3)
    if lens_name == "security_posture":
        return round(next((r.score for r in audit.analyzer_results if r.dimension == "security"), 0.0), 3)
    if lens_name == "momentum":
        return round(next((r.score for r in audit.analyzer_results if r.dimension == "activity"), 0.0), 3)
    return round(audit.overall_score, 3)


def build_portfolio_lens_summary(audits: list[RepoAudit]) -> dict[str, dict]:
    summary: dict[str, dict] = {}
    for lens_name, lens_meta in LENS_DEFINITIONS.items():
        values: list[tuple[str, float]] = []
        for audit in audits:
            lens = audit.lenses.get(lens_name) if hasattr(audit, "lenses") else None
            score = lens.get("score") if lens else _fallback_lens_value(audit, lens_name)
            values.append((audit.metadata.name, score))
        if not values:
            summary[lens_name] = {
                "orientation": lens_meta["orientation"],
                "average_score": 0.0,
                "leaders": [],
                "attention": [],
            }
            continue

        values.sort(key=lambda item: item[1], reverse=True)
        summary[lens_name] = {
            "orientation": lens_meta["orientation"],
            "average_score": round(sum(score for _, score in values) / len(values), 3),
            "leaders": [name for name, _ in values[:3]],
            "attention": (
                [name for name, _ in values[:3]]
                if lens_meta["orientation"] == "higher-is-riskier"
                else [name for name, _ in values[-3:]]
            ),
            "description": lens_meta["description"],
        }
    return summary


def build_portfolio_hotspots(audits: list[RepoAudit]) -> list[dict]:
    hotspots: list[dict] = []
    for audit in audits:
        for hotspot in audit.hotspots:
            hotspots.append({
                "repo": audit.metadata.name,
                "tier": audit.completeness_tier,
                **hotspot,
            })
    hotspots.sort(key=lambda item: item["severity"], reverse=True)
    return hotspots[:12]


def build_portfolio_security_posture(audits: list[RepoAudit]) -> dict:
    posture_counts = Counter(audit.security_posture.get("label", "unknown") for audit in audits)
    critical_repos = [
        audit.metadata.name
        for audit in audits
        if audit.security_posture.get("label") in {"critical", "at-risk"}
    ]
    github_available = sum(1 for audit in audits if audit.security_posture.get("github", {}).get("provider_available"))
    scorecard_available = sum(1 for audit in audits if audit.security_posture.get("scorecard", {}).get("available"))
    code_alerts = sum(audit.security_posture.get("github", {}).get("code_scanning_alerts") or 0 for audit in audits)
    secret_alerts = sum(audit.security_posture.get("github", {}).get("secret_scanning_alerts") or 0 for audit in audits)
    return {
        "average_score": round(
            sum(audit.security_posture.get("score", 0.0) for audit in audits) / len(audits),
            3,
        ) if audits else 0.0,
        "labels": dict(posture_counts),
        "critical_repos": critical_repos[:10],
        "repos_with_secrets": [
            audit.metadata.name
            for audit in audits
            if audit.security_posture.get("secrets_found", 0) > 0
        ],
        "provider_coverage": {
            "github": {"available_repos": github_available, "total_repos": len(audits)},
            "scorecard": {"available_repos": scorecard_available, "total_repos": len(audits)},
        },
        "open_alerts": {
            "code_scanning": code_alerts,
            "secret_scanning": secret_alerts,
        },
    }


def build_default_collections(audits: list[RepoAudit]) -> dict[str, dict]:
    ranked_showcase = sorted(
        audits,
        key=lambda audit: audit.lenses.get("showcase_value", {}).get("score", _fallback_lens_value(audit, "showcase_value")),
        reverse=True,
    )
    ranked_secure = sorted(
        audits,
        key=lambda audit: audit.security_posture.get("score", _fallback_lens_value(audit, "security_posture")),
    )

    finish_next: list[dict] = []
    archive_soon: list[dict] = []
    for audit in audits:
        next_tier = _next_tier_name(audit.overall_score)
        if next_tier and next_tier != audit.completeness_tier and audit.overall_score >= TIER_THRESHOLDS.get(audit.completeness_tier, 0.0):
            gap = TIER_THRESHOLDS[next_tier] - audit.overall_score
            if 0 < gap <= 0.15:
                finish_next.append({
                    "name": audit.metadata.name,
                    "reason": f"{gap:.3f} away from {next_tier}",
                })
        if (
            audit.completeness_tier in {"skeleton", "abandoned"}
            or "stale-2yr" in audit.flags
            or audit.lenses.get("showcase_value", {}).get("score", 0.0) < 0.30
        ):
            archive_soon.append({
                "name": audit.metadata.name,
                "reason": "Low showcase value and/or low maintenance momentum.",
            })

    return {
        "showcase": {
            "description": DEFAULT_COLLECTION_DESCRIPTIONS["showcase"],
            "repos": [
                {
                    "name": audit.metadata.name,
                    "reason": audit.lenses.get("showcase_value", {}).get("summary", "Strong portfolio signal."),
                }
                for audit in ranked_showcase[:8]
            ],
        },
        "finish-next": {
            "description": DEFAULT_COLLECTION_DESCRIPTIONS["finish-next"],
            "repos": finish_next[:8],
        },
        "secure-now": {
            "description": DEFAULT_COLLECTION_DESCRIPTIONS["secure-now"],
            "repos": [
                {
                    "name": audit.metadata.name,
                    "reason": (
                        audit.security_posture.get("recommendations", [{}])[0].get("title")
                        or audit.security_posture.get("label", "unknown")
                    ),
                }
                for audit in ranked_secure[:8]
            ],
        },
        "archive-soon": {
            "description": DEFAULT_COLLECTION_DESCRIPTIONS["archive-soon"],
            "repos": archive_soon[:8],
        },
    }


def build_scenario_summary(audits: list[RepoAudit]) -> dict:
    grouped: dict[str, dict] = defaultdict(lambda: {
        "title": "",
        "lens": "",
        "repo_count": 0,
        "expected_lens_delta_total": 0.0,
        "projected_tier_promotions": 0,
    })
    current_shipped = sum(1 for audit in audits if audit.completeness_tier == "shipped")

    for audit in audits:
        for action in audit.action_candidates[:2]:
            entry = grouped[action["key"]]
            entry["title"] = action["title"]
            entry["lens"] = action["lens"]
            entry["repo_count"] += 1
            entry["expected_lens_delta_total"] += action["expected_lens_delta"]
            if action["expected_tier_movement"].startswith("Closer to"):
                entry["projected_tier_promotions"] += 1

    top_levers = sorted(
        [
            {
                "key": key,
                "title": value["title"],
                "lens": value["lens"],
                "repo_count": value["repo_count"],
                "average_expected_lens_delta": round(value["expected_lens_delta_total"] / value["repo_count"], 3),
                "projected_tier_promotions": value["projected_tier_promotions"],
            }
            for key, value in grouped.items()
            if value["repo_count"] > 0
        ],
        key=lambda item: (item["repo_count"], item["average_expected_lens_delta"]),
        reverse=True,
    )[:5]

    projected_avg_delta = round(sum(item["average_expected_lens_delta"] for item in top_levers) * 0.08, 3) if top_levers else 0.0
    projected_shipped_delta = sum(1 for item in top_levers if item["lens"] == "ship_readiness")

    return {
        "top_levers": top_levers,
        "portfolio_projection": {
            "current_shipped": current_shipped,
            "projected_shipped": current_shipped + projected_shipped_delta,
            "projected_average_score_delta": projected_avg_delta,
        },
    }


def build_portfolio_security_governance_preview(audits: list[RepoAudit]) -> list[dict]:
    return build_security_governance_preview(audits)
