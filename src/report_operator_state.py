"""Operator-state enrichment for reconstructed audit reports."""

from __future__ import annotations

from pathlib import Path

from src.governance_activation import build_governance_summary
from src.models import AuditReport
from src.operator_control_center import build_operator_snapshot, normalize_review_state


def enrich_report_with_operator_state(
    report: AuditReport,
    *,
    output_dir: Path,
    diff_dict: dict | None,
    triage_view: str,
    portfolio_profile: str,
    collection: str | None,
) -> AuditReport:
    normalized = normalize_review_state(
        report.to_dict(), output_dir=output_dir, diff_data=diff_dict,
        portfolio_profile=portfolio_profile, collection_name=collection,
    )
    normalized["governance_summary"] = build_governance_summary(normalized)
    snapshot = build_operator_snapshot(normalized, output_dir=output_dir, triage_view=triage_view)
    report.governance_summary = normalized.get("governance_summary", {})
    report.review_summary = normalized.get("review_summary", {})
    report.review_alerts = normalized.get("review_alerts", [])
    report.material_changes = normalized.get("material_changes", [])
    report.review_targets = normalized.get("review_targets", [])
    report.review_history = normalized.get("review_history", [])
    report.watch_state = normalized.get("watch_state", {})
    report.operator_summary = snapshot.get("operator_summary", {})
    report.operator_queue = snapshot.get("operator_queue", [])
    report.portfolio_outcomes_summary = snapshot.get("portfolio_outcomes_summary", {})
    report.operator_effectiveness_summary = snapshot.get("operator_effectiveness_summary", {})
    report.high_pressure_queue_history = snapshot.get("high_pressure_queue_history", [])
    report.campaign_readiness_summary = snapshot.get("campaign_readiness_summary", {})
    report.action_sync_summary = snapshot.get("action_sync_summary", {})
    report.next_action_sync_step = snapshot.get("next_action_sync_step", "")
    report.action_sync_packets = snapshot.get("action_sync_packets", [])
    report.apply_readiness_summary = snapshot.get("apply_readiness_summary", {})
    report.next_apply_candidate = snapshot.get("next_apply_candidate", {})
    report.action_sync_outcomes = snapshot.get("action_sync_outcomes", [])
    report.campaign_outcomes_summary = snapshot.get("campaign_outcomes_summary", {})
    report.next_monitoring_step = snapshot.get("next_monitoring_step", {})
    report.action_sync_tuning = snapshot.get("action_sync_tuning", [])
    report.campaign_tuning_summary = snapshot.get("campaign_tuning_summary", {})
    report.next_tuned_campaign = snapshot.get("next_tuned_campaign", {})
    report.historical_portfolio_intelligence = snapshot.get("historical_portfolio_intelligence", [])
    report.intervention_ledger_summary = snapshot.get("intervention_ledger_summary", {})
    report.next_historical_focus = snapshot.get("next_historical_focus", {})
    report.action_sync_automation = snapshot.get("action_sync_automation", [])
    report.automation_guidance_summary = snapshot.get("automation_guidance_summary", {})
    report.next_safe_automation_step = snapshot.get("next_safe_automation_step", {})
    report.approval_ledger = snapshot.get("approval_ledger", [])
    report.approval_workflow_summary = snapshot.get("approval_workflow_summary", {})
    report.next_approval_review = snapshot.get("next_approval_review", {})
    return report
