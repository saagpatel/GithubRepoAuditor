"""Shared PortfolioTruth project risk and attention derivation."""

from __future__ import annotations

from typing import Any

from src.portfolio_risk import build_risk_entry


def derive_attention_state(
    *,
    activity_status: str,
    archived: bool,
    lifecycle_state: str,
    operating_path: str,
    category: str,
    path_override: str,
    risk_entry: dict[str, Any],
) -> str:
    """Apply the production attention policy to already-normalized facts."""
    if archived or operating_path == "archive":
        return "archived"
    if operating_path == "experiment" or lifecycle_state == "experimental":
        return "experiment"
    if risk_entry.get("security_risk"):
        return "decision-needed"
    if lifecycle_state == "manual-only":
        return "manual-only"
    if lifecycle_state == "dormant":
        return "parked"
    if lifecycle_state == "active" and operating_path == "maintain":
        if category == "infrastructure":
            return "active-infra"
        if category == "commercial":
            return "active-product"
    if activity_status == "stale":
        return "decision-needed" if operating_path == "finish" else "parked"
    if activity_status in {"active", "recent"} and operating_path in {
        "maintain",
        "finish",
    }:
        if category == "infrastructure":
            return "active-infra"
        if category == "commercial":
            return "active-product"
        return "manual-only"
    if activity_status in {"active", "recent"}:
        return "manual-only"
    return "parked"


def build_project_decision(
    *,
    display_name: str,
    operating_path: str,
    path_override: str,
    context_quality: str,
    activity_status: str,
    archived: bool,
    lifecycle_state: str,
    category: str,
    criticality: str,
    doctor_standard: str,
    known_risks_present: bool,
    run_instructions_present: bool,
    security_coverage_state: str,
    security_high_alerts: int = 0,
    security_critical_alerts: int = 0,
) -> tuple[dict[str, Any], str]:
    """Return the exact production risk envelope and attention decision."""
    risk_entry = build_risk_entry(
        display_name=display_name,
        operating_path=operating_path,
        path_override=path_override,
        context_quality=context_quality,
        activity_status=activity_status,
        archived=archived,
        criticality=criticality,
        doctor_standard=doctor_standard,
        known_risks_present=known_risks_present,
        run_instructions_present=run_instructions_present,
        security_high_alerts=security_high_alerts,
        security_critical_alerts=security_critical_alerts,
    )
    if (
        security_coverage_state != "complete"
        and risk_entry.get("risk_summary") == "No elevated risk factors."
    ):
        risk_entry["risk_summary"] = (
            "No non-security risk factors detected; GitHub security coverage is "
            f"{security_coverage_state}."
        )
    attention_state = derive_attention_state(
        activity_status=activity_status,
        archived=archived,
        lifecycle_state=lifecycle_state,
        operating_path=operating_path,
        category=category,
        path_override=path_override,
        risk_entry=risk_entry,
    )
    return risk_entry, attention_state
