"""Leaf report-discovery and artifact-time helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.models import AnalyzerResult, AuditReport, RepoAudit, RepoMetadata
from src.registry_parser import RegistryReconciliation


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def audit_from_dict(data: dict) -> RepoAudit:
    meta_data = data.get("metadata", {})
    metadata = RepoMetadata(
        name=meta_data["name"],
        full_name=meta_data["full_name"],
        description=meta_data.get("description"),
        language=meta_data.get("language"),
        languages=meta_data.get("languages", {}),
        private=meta_data["private"],
        fork=meta_data["fork"],
        archived=meta_data["archived"],
        created_at=parse_iso_datetime(meta_data.get("created_at")),  # type: ignore[arg-type]
        updated_at=parse_iso_datetime(meta_data.get("updated_at")),  # type: ignore[arg-type]
        pushed_at=parse_iso_datetime(meta_data.get("pushed_at")),
        default_branch=meta_data.get("default_branch", "main"),
        stars=meta_data.get("stars", 0),
        forks=meta_data.get("forks", 0),
        open_issues=meta_data.get("open_issues", 0),
        size_kb=meta_data.get("size_kb", 0),
        html_url=meta_data.get("html_url", ""),
        clone_url=meta_data.get("clone_url", ""),
        topics=meta_data.get("topics", []),
    )
    analyzer_results = [
        AnalyzerResult(
            dimension=result["dimension"],
            score=result["score"],
            max_score=result["max_score"],
            findings=result["findings"],
            details=result.get("details", {}),
        )
        for result in data.get("analyzer_results", [])
    ]
    return RepoAudit(
        metadata=metadata,
        analyzer_results=analyzer_results,
        overall_score=data.get("overall_score", 0),
        completeness_tier=data.get("completeness_tier", "abandoned"),
        interest_score=data.get("interest_score", 0),
        interest_tier=data.get("interest_tier", "mundane"),
        grade=data.get("grade", "F"), interest_grade=data.get("interest_grade", "F"),
        badges=data.get("badges", []), next_badges=data.get("next_badges", []),
        flags=data.get("flags", []), lenses=data.get("lenses", {}), hotspots=data.get("hotspots", []),
        action_candidates=data.get("action_candidates", []), security_posture=data.get("security_posture", {}),
        score_explanation=data.get("score_explanation", {}), portfolio_catalog=data.get("portfolio_catalog", {}),
        scorecard=data.get("scorecard", {}), ossf_scorecard=data.get("ossf_scorecard", {}),
    )


def report_from_dict(data: dict) -> AuditReport:
    reconciliation = (
        RegistryReconciliation(**data["reconciliation"])
        if data.get("reconciliation")
        else None
    )
    summary = data.get("summary", {})
    return AuditReport(
        username=data["username"],
        generated_at=parse_iso_datetime(data.get("generated_at")) or datetime.now(timezone.utc),
        total_repos=data.get("total_repos", 0), repos_audited=data.get("repos_audited", 0),
        tier_distribution=data.get("tier_distribution", {}), average_score=data.get("average_score", 0),
        language_distribution=data.get("language_distribution", {}),
        audits=[audit_from_dict(audit) for audit in data.get("audits", [])], errors=data.get("errors", []),
        portfolio_grade=data.get("portfolio_grade", "F"), portfolio_health_score=data.get("portfolio_health_score", 0),
        tech_stack=data.get("tech_stack", {}), best_work=data.get("best_work", []),
        most_active=summary.get("most_active", []), most_neglected=summary.get("most_neglected", []),
        highest_scored=summary.get("highest_scored", []), lowest_scored=summary.get("lowest_scored", []),
        scoring_profile=data.get("scoring_profile", "default"), run_mode=data.get("run_mode", "full"),
        portfolio_baseline_size=data.get("portfolio_baseline_size", len(data.get("audits", []))),
        baseline_signature=data.get("baseline_signature", ""), baseline_context=data.get("baseline_context", {}),
        schema_version=data.get("schema_version", "3.7"), lenses=data.get("lenses", {}), hotspots=data.get("hotspots", []),
        implementation_hotspots=data.get("implementation_hotspots", []), implementation_hotspots_summary=data.get("implementation_hotspots_summary", {}),
        portfolio_outcomes_summary=data.get("portfolio_outcomes_summary", {}), operator_effectiveness_summary=data.get("operator_effectiveness_summary", {}),
        high_pressure_queue_history=data.get("high_pressure_queue_history", []), campaign_readiness_summary=data.get("campaign_readiness_summary", {}),
        action_sync_summary=data.get("action_sync_summary", {}), next_action_sync_step=data.get("next_action_sync_step", ""), action_sync_packets=data.get("action_sync_packets", []),
        apply_readiness_summary=data.get("apply_readiness_summary", {}), next_apply_candidate=data.get("next_apply_candidate", {}), action_sync_outcomes=data.get("action_sync_outcomes", []),
        campaign_outcomes_summary=data.get("campaign_outcomes_summary", {}), next_monitoring_step=data.get("next_monitoring_step", {}),
        action_sync_tuning=data.get("action_sync_tuning", []), campaign_tuning_summary=data.get("campaign_tuning_summary", {}), next_tuned_campaign=data.get("next_tuned_campaign", {}),
        historical_portfolio_intelligence=data.get("historical_portfolio_intelligence", []), intervention_ledger_summary=data.get("intervention_ledger_summary", {}), next_historical_focus=data.get("next_historical_focus", {}),
        action_sync_automation=data.get("action_sync_automation", []), automation_guidance_summary=data.get("automation_guidance_summary", {}), next_safe_automation_step=data.get("next_safe_automation_step", {}),
        approval_ledger=data.get("approval_ledger", []), approval_workflow_summary=data.get("approval_workflow_summary", {}), next_approval_review=data.get("next_approval_review", {}),
        security_posture=data.get("security_posture", {}), security_governance_preview=data.get("security_governance_preview", []), collections=data.get("collections", {}), profiles=data.get("profiles", {}),
        scenario_summary=data.get("scenario_summary", {}), action_backlog=data.get("action_backlog", []), campaign_summary=data.get("campaign_summary", {}),
        writeback_preview=data.get("writeback_preview", {}), writeback_results=data.get("writeback_results", {}), action_runs=data.get("action_runs", []), external_refs=data.get("external_refs", {}),
        managed_state_drift=data.get("managed_state_drift", []), rollback_preview=data.get("rollback_preview", {}), campaign_history=data.get("campaign_history", []),
        governance_preview=data.get("governance_preview", {}), governance_approval=data.get("governance_approval", {}), governance_results=data.get("governance_results", {}),
        governance_history=data.get("governance_history", []), governance_drift=data.get("governance_drift", []), governance_summary=data.get("governance_summary", {}),
        preflight_summary=data.get("preflight_summary", {}), review_summary=data.get("review_summary", {}), review_alerts=data.get("review_alerts", []),
        material_changes=data.get("material_changes", []), review_targets=data.get("review_targets", []), review_history=data.get("review_history", []),
        watch_state=data.get("watch_state", {}), operator_summary=data.get("operator_summary", {}), operator_queue=data.get("operator_queue", []),
        portfolio_catalog_summary=data.get("portfolio_catalog_summary", {}), operating_paths_summary=data.get("operating_paths_summary", {}),
        intent_alignment_summary=data.get("intent_alignment_summary", {}), scorecards_summary=data.get("scorecards_summary", {}),
        scorecard_programs=data.get("scorecard_programs", {}), reconciliation=reconciliation,
    )
def load_latest_report(output_dir: Path) -> tuple[Path | None, dict | None]:
    reports = sorted(
        output_dir.glob("audit-report-*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not reports:
        return None, None
    latest = reports[0]
    return latest, json.loads(latest.read_text())


def report_artifact_datetime(report_path: Path | None, fallback: datetime) -> datetime:
    if report_path:
        stem = report_path.stem
        if len(stem) >= 10:
            parsed = datetime.fromisoformat(f"{stem[-10:]}T00:00:00+00:00")
            return parsed
    return fallback
