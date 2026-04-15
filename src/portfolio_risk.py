from __future__ import annotations

from typing import Any

CONTRACT_VERSION = "portfolio_risk_v1"
AUTHORITY_CAP = "bounded-automation"

VALID_RISK_TIERS = frozenset({"elevated", "moderate", "baseline", "deferred"})
VALID_DOCTOR_STANDARDS = frozenset({"full", "basic"})
STRATEGIC_REPOS = frozenset(
    {
        "GithubRepoAuditor",
        "JobCommandCenter",
        "DecisionStressTest",
        "MCPAudit",
        "ResumeEvolver",
    }
)

ACTIVE_STATUSES = frozenset({"active", "recent"})
WEAK_CONTEXT = frozenset({"none", "boilerplate"})

_FACTOR_LABELS: dict[str, str] = {
    "weak-context-active": "weak context quality",
    "investigate-override": "investigate override active",
    "missing-operating-path": "no operating path declared",
    "missing-doctor-standard": "doctor standard not declared",
    "no-run-instructions": "run instructions missing",
    "undocumented-risks": "known risks not documented",
}

_DEFERRED_ARCHIVED = {
    "risk_tier": "deferred",
    "risk_factors": [],
    "risk_summary": "Archived or archive-path project.",
    "doctor_gap": False,
    "context_risk": False,
    "path_risk": False,
}

_DEFERRED_STALE = {
    "risk_tier": "deferred",
    "risk_factors": [],
    "risk_summary": "Stale project not on maintain path.",
    "doctor_gap": False,
    "context_risk": False,
    "path_risk": False,
}


def build_risk_entry(
    *,
    display_name: str,
    operating_path: str,
    path_override: str,
    path_confidence: str,
    context_quality: str,
    activity_status: str,
    registry_status: str,
    criticality: str,
    doctor_standard: str,
    known_risks_present: bool,
    run_instructions_present: bool,
) -> dict[str, Any]:
    # Short-circuit deferred: archived or archive-path
    if registry_status == "archived" or operating_path == "archive":
        return dict(_DEFERRED_ARCHIVED)

    # Short-circuit deferred: stale and not on maintain path
    if activity_status == "stale" and operating_path != "maintain":
        return dict(_DEFERRED_STALE)

    # Accumulate risk factors
    factors: list[str] = []

    if activity_status in ACTIVE_STATUSES and context_quality in WEAK_CONTEXT:
        factors.append("weak-context-active")

    if path_override == "investigate" and activity_status in ACTIVE_STATUSES:
        factors.append("investigate-override")

    if not operating_path and activity_status in ACTIVE_STATUSES:
        factors.append("missing-operating-path")

    if display_name in STRATEGIC_REPOS and not doctor_standard:
        factors.append("missing-doctor-standard")

    if activity_status in ACTIVE_STATUSES and not run_instructions_present:
        factors.append("no-run-instructions")

    if criticality in {"high", "critical"} and not known_risks_present:
        factors.append("undocumented-risks")

    # Derive tier
    is_elevated = len(factors) >= 3 or (
        "weak-context-active" in factors and "investigate-override" in factors
    )
    if is_elevated:
        risk_tier = "elevated"
    elif factors:
        risk_tier = "moderate"
    else:
        risk_tier = "baseline"

    # Derive booleans
    doctor_gap = "missing-doctor-standard" in factors
    context_risk = "weak-context-active" in factors
    path_risk = "investigate-override" in factors or "missing-operating-path" in factors

    # Build summary
    if not factors:
        risk_summary = "No elevated risk factors."
    else:
        parts = [_FACTOR_LABELS.get(f, f) for f in factors]
        risk_summary = f"{len(factors)} risk factor(s): {', '.join(parts)}."

    return {
        "risk_tier": risk_tier,
        "risk_factors": factors,
        "risk_summary": risk_summary,
        "doctor_gap": doctor_gap,
        "context_risk": context_risk,
        "path_risk": path_risk,
    }


def build_portfolio_risk_summary(projects: list[dict[str, Any]]) -> dict[str, Any]:
    risk_tier_counts: dict[str, int] = {}
    for project in projects:
        tier = (project.get("risk") or {}).get("risk_tier") or "baseline"
        risk_tier_counts[tier] = risk_tier_counts.get(tier, 0) + 1
    return {
        "risk_tier_counts": risk_tier_counts,
        "elevated_count": risk_tier_counts.get("elevated", 0),
        "moderate_count": risk_tier_counts.get("moderate", 0),
    }
