from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from src.baseline_context import build_baseline_context
from src.models import AnalyzerResult, RepoMetadata
from src.scorer import WEIGHTS, score_repo
from src.warehouse import (
    load_action_sync_automation,
    load_approval_followup_events,
    load_approval_records,
    load_campaign_history,
    load_campaign_outcomes,
    load_campaign_tuning,
    load_intervention_ledger,
    load_latest_audit_runs,
    load_latest_campaign_state,
    load_latest_operator_state,
    load_recent_campaign_history,
    load_recent_implementation_hotspots,
    load_recent_repo_scorecards,
    load_review_history,
    load_watch_checkpoint,
    save_approval_followup_event,
    save_approval_record,
    write_warehouse_snapshot,
)


def _make_metadata() -> RepoMetadata:
    return RepoMetadata(
        name="warehouse-repo",
        full_name="user/warehouse-repo",
        description="Warehouse test repo",
        language="Python",
        languages={"Python": 1000},
        private=False,
        fork=False,
        archived=False,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        pushed_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
        default_branch="main",
        stars=4,
        forks=1,
        open_issues=0,
        size_kb=128,
        html_url="https://github.com/user/warehouse-repo",
        clone_url="https://github.com/user/warehouse-repo.git",
        topics=["python"],
    )


def _make_results() -> list[AnalyzerResult]:
    results = []
    for dimension, score in WEIGHTS.items():
        details = {}
        if dimension == "structure":
            details = {"config_files": ["pyproject.toml"], "source_dirs": ["src"]}
        if dimension == "code_quality":
            details = {"entry_point": "main.py", "total_loc": 200}
        results.append(
            AnalyzerResult(
                dimension=dimension,
                score=0.75 if dimension != "testing" else 0.45,
                max_score=1.0,
                findings=[],
                details=details,
            )
        )
    results.append(
        AnalyzerResult(
            dimension="interest",
            score=0.55,
            max_score=1.0,
            findings=[],
            details={"tech_novelty": 0.10},
        )
    )
    results.append(
        AnalyzerResult(
            dimension="security",
            score=0.50,
            max_score=1.0,
            findings=["No SECURITY.md"],
            details={
                "secrets_found": 0,
                "dangerous_files": [],
                "has_security_md": False,
                "has_dependabot": True,
            },
        )
    )
    return results


def test_write_warehouse_snapshot_persists_core_entities(tmp_path):
    audit = score_repo(_make_metadata(), _make_results())
    audit.implementation_hotspots = [
        {
            "scope": "file",
            "path": "src/core.py",
            "module": "src",
            "category": "code-complexity",
            "pressure_score": 0.74,
            "suggestion_type": "refactor",
            "why_it_matters": "src/core.py is carrying concentrated complexity.",
            "suggested_first_move": "Split the biggest function and add one regression test.",
            "signal_summary": "Complexity pressure 0.74 across 2 complex blocks.",
        }
    ]

    from src.models import AuditReport

    report = AuditReport.from_audits("user", [audit], [], 1)
    report.baseline_context = build_baseline_context(
        username="user",
        scoring_profile="default",
        skip_forks=False,
        skip_archived=False,
        scorecard=False,
        security_offline=False,
        portfolio_baseline_size=1,
    )
    report.baseline_signature = report.baseline_context["baseline_signature"]
    report.campaign_summary = {
        "campaign_type": "promotion-push",
        "label": "Promotion Push",
        "action_count": 1,
        "repo_count": 1,
    }
    report.writeback_results = {
        "mode": "apply",
        "target": "github",
        "results": [
            {
                "action_id": "promotion-push-abc123",
                "repo_full_name": "user/warehouse-repo",
                "target": "github-issue",
                "status": "created",
                "before": {},
                "after": {"state": "open"},
                "number": 1,
                "url": "https://github.com/user/warehouse-repo/issues/1",
            }
        ],
        "campaign_run": {
            "portfolio_profile": "default",
            "writeback_target": "github",
            "mode": "apply",
            "generated_at": report.generated_at.isoformat(),
            "generated_action_ids": ["promotion-push-abc123"],
        },
    }
    report.action_runs = [
        {
            "action_id": "promotion-push-abc123",
            "repo_full_name": "user/warehouse-repo",
            "campaign_type": "promotion-push",
            "target": "github",
            "status": "created",
            "lifecycle_state": "open",
            "reconciliation_outcome": "created",
            "rollback_state": "rollback-available",
        }
    ]
    report.campaign_history = list(report.action_runs)
    report.external_refs = {
        "promotion-push-abc123": {"github_issue_url": "https://github.com/user/warehouse-repo/issues/1"}
    }
    report.review_summary = {
        "review_id": "review-1",
        "source_run_id": f"{report.username}:{report.generated_at.isoformat()}",
        "status": "open",
        "decision_state": "needs-review",
    }
    report.governance_summary = {
        "status": "blocked",
        "headline": "Governed controls need re-approval before the next manual apply step.",
        "needs_reapproval": True,
        "drift_count": 1,
        "applyable_count": 1,
        "rollback_available_count": 1,
    }
    report.review_targets = [
        {
            "repo": "warehouse-repo",
            "title": "Review warehouse-repo",
            "severity": 0.7,
            "recommended_next_step": "Inspect the repo and decide on the next campaign step.",
            "next_step": "Inspect the repo and decide on the next campaign step.",
            "safe_to_defer": False,
        }
    ]
    report.review_history = [dict(report.review_summary)]
    report.watch_state = {"filter_signature": "abc123", "review_sync": "local"}
    report.operator_summary = {
        "headline": "Campaign work is ready for review.",
        "counts": {"blocked": 0, "urgent": 0, "ready": 1, "deferred": 0},
    }
    report.operator_queue = [
        {
            "item_id": "campaign-ready:promotion-push",
            "kind": "campaign",
            "lane": "ready",
            "priority": 70,
            "repo": "",
            "title": "Promotion Push is ready for review",
            "summary": "1 action across 1 repo.",
            "recommended_action": "Review the reconcile queue before manual writeback.",
            "source_run_id": f"{report.username}:{report.generated_at.isoformat()}",
            "age_days": 0,
            "links": [],
        }
    ]
    audit.portfolio_catalog = {
        "has_explicit_entry": True,
        "owner": "d",
        "team": "operator-loop",
        "purpose": "warehouse verification",
        "lifecycle_state": "active",
        "criticality": "high",
        "review_cadence": "weekly",
        "intended_disposition": "maintain",
        "maturity_program": "maintain",
        "target_maturity": "strong",
        "operating_path": "maintain",
        "path_override": "",
        "path_confidence": "high",
        "path_rationale": "Stable path is Maintain from intended disposition.",
        "notes": "",
        "intent_alignment": "aligned",
        "intent_alignment_reason": "The repo is holding a maintain posture without urgent or revalidation pressure.",
        "catalog_line": "operator-loop | warehouse verification | lifecycle active | criticality high | cadence weekly | disposition maintain",
    }
    report.portfolio_catalog_summary = {"summary": "1/1 repos have an explicit catalog contract."}
    report.operating_paths_summary = {"summary": "Maintain 1", "path_counts": {"maintain": 1}, "confidence_counts": {"high": 1}, "override_counts": {}}
    report.intent_alignment_summary = {"summary": "1 aligned, 0 needing review, and 0 missing a contract."}
    audit.scorecard = {
        "program": "maintain",
        "program_label": "Maintain",
        "target_maturity": "strong",
        "maturity_level": "operating",
        "score": 0.74,
        "status": "below-target",
        "failed_rule_keys": ["testing", "ci"],
        "summary": "Maintain is at Operating and still below the Strong target because testing and ci are behind.",
    }
    report.scorecards_summary = {"summary": "0 repos are on track, 1 is below target, and 0 are missing a valid program."}
    report.scorecard_programs = {"maintain": {"label": "Maintain", "rule_count": 8}}
    report.portfolio_outcomes_summary = {
        "summary": "Managed action closure is at 50%; blocked and urgent pressure quiets in about 2.0 run(s); repeated regression is running at 25%.",
        "review_to_action_closure_rate": {"status": "measured", "value": 0.5},
    }
    report.operator_effectiveness_summary = {
        "summary": "recommendation validation is at 75%; guidance noise is at 25%.",
        "recommendation_validation_rate": {"status": "measured", "value": 0.75},
    }
    report.high_pressure_queue_history = [
        {
            "run_id": "user:2026-03-20T00:00:00+00:00",
            "generated_at": "2026-03-20T00:00:00+00:00",
            "blocked_count": 0,
            "urgent_count": 1,
            "high_pressure_count": 1,
        }
    ]
    report.operator_summary.update(
        {
            "portfolio_outcomes_summary": report.portfolio_outcomes_summary,
            "operator_effectiveness_summary": report.operator_effectiveness_summary,
            "decision_quality_v1": {
                "contract_version": "decision_quality_v1",
                "authority_cap": "bounded-automation",
                "evidence_window_runs": 6,
                "validation_window_runs": 2,
                "judged_recommendation_count": 4,
                "validated_recommendation_count": 3,
                "partially_validated_recommendation_count": 1,
                "reopened_recommendation_count": 0,
                "unresolved_recommendation_count": 0,
                "high_confidence_hit_rate": 0.75,
                "medium_confidence_hit_rate": 0.67,
                "low_confidence_caution_rate": 1.0,
                "confidence_validation_status": "healthy",
                "decision_quality_status": "trusted",
                "human_skepticism_required": False,
                "downgrade_reasons": [],
                "recommendation_quality_summary": "Strong recommendation because the next step is tied directly to the current top target.",
                "confidence_calibration_summary": "Recent high-confidence recommendations are validating well.",
                "recent_validation_outcomes": [],
                "primary_target_trust_policy": "act-with-review",
                "primary_target_trust_policy_reason": "Healthy calibration supports a confident next step, with light operator judgment.",
                "next_action_trust_policy": "act-with-review",
                "next_action_trust_policy_reason": "Healthy calibration supports a confident next step, with light operator judgment.",
                "adaptive_confidence_summary": "Calibration is validating well, so the recommendation can be acted on with light operator review.",
            },
            "recommendation_quality_summary": "Strong recommendation because the next step is tied directly to the current top target.",
            "confidence_validation_status": "healthy",
            "decision_quality_status": "trusted",
            "decision_quality_authority_cap": "bounded-automation",
            "human_skepticism_required": False,
            "downgrade_reasons": [],
            "confidence_window_runs": 6,
            "validation_window_runs": 2,
            "judged_recommendation_count": 4,
            "validated_recommendation_count": 3,
            "partially_validated_recommendation_count": 1,
            "unresolved_recommendation_count": 0,
            "reopened_recommendation_count": 0,
            "high_confidence_hit_rate": 0.75,
            "medium_confidence_hit_rate": 0.67,
            "low_confidence_caution_rate": 1.0,
            "confidence_calibration_summary": "Recent high-confidence recommendations are validating well.",
            "high_pressure_queue_history": report.high_pressure_queue_history,
            "high_pressure_queue_trend_status": "stable",
            "high_pressure_queue_trend_summary": "Blocked and urgent queue pressure is stable.",
            "recent_closed_actions": [{"repo": "warehouse-repo", "title": "Close warehouse follow-up"}],
            "recent_reopened_recommendations": [{"repo": "warehouse-repo", "title": "warehouse recommendation"}],
            "recent_regression_examples": [{"repo": "warehouse-repo", "title": "warehouse regression"}],
        }
    )
    report.action_sync_outcomes = [
        {
            "campaign_type": "promotion-push",
            "label": "Promotion Push",
            "latest_target": "github",
            "latest_run_mode": "apply",
            "recent_apply_count": 1,
            "monitored_repo_count": 1,
            "monitoring_state": "monitor-now",
            "pressure_effect": "flat",
            "drift_state": "clear",
            "reopen_state": "none",
            "rollback_state": "ready",
            "follow_up_recommendation": "Monitor Promotion Push for at least 2 post-apply runs before treating it as stable.",
            "top_repos": ["user/warehouse-repo"],
            "summary": "Promotion Push was applied recently; monitor it now before treating it as stable.",
        }
    ]
    report.campaign_outcomes_summary = {
        "summary": "Promotion Push was applied recently; monitor it now before treating it as stable.",
        "counts": {"monitor-now": 1},
    }
    report.next_monitoring_step = {
        "campaign_type": "promotion-push",
        "monitoring_state": "monitor-now",
        "summary": "Monitor Promotion Push for at least 2 post-apply runs before treating it as stable.",
    }
    report.action_sync_tuning = [
        {
            "campaign_type": "promotion-push",
            "label": "Promotion Push",
            "judged_count": 3,
            "monitor_now_count": 1,
            "holding_clean_rate": 0.67,
            "drift_return_rate": 0.0,
            "reopen_rate": 0.0,
            "rollback_watch_rate": 0.33,
            "pressure_reduction_rate": 0.67,
            "tuning_status": "proven",
            "recommendation_bias": "promote",
            "summary": "Promotion Push should win ties because recent outcomes are proven.",
        }
    ]
    report.campaign_tuning_summary = {
        "summary": "Promotion Push should win ties because recent outcomes are proven.",
        "counts": {"proven": 1, "mixed": 0, "caution": 0, "insufficient-evidence": 0},
    }
    report.next_tuned_campaign = {
        "campaign_type": "promotion-push",
        "summary": "Promotion Push should win ties inside the current group because recent outcome history is proven.",
    }
    report.historical_portfolio_intelligence = [
        {
            "repo": "warehouse-repo",
            "latest_tier": "functional",
            "latest_score": 0.74,
            "recent_intervention_count": 1,
            "last_intervention": report.generated_at.isoformat(),
            "pressure_trend": "improving",
            "hotspot_persistence": "changing",
            "scorecard_trend": "improving",
            "campaign_follow_through": "helping",
            "historical_intelligence_status": "improving-after-intervention",
            "summary": "warehouse-repo is improving after intervention.",
        }
    ]
    report.intervention_ledger_summary = {
        "summary": "warehouse-repo is improving after intervention while no repos currently look relapsing.",
        "counts": {"improving-after-intervention": 1},
    }
    report.next_historical_focus = {
        "repo": "warehouse-repo",
        "historical_intelligence_status": "improving-after-intervention",
        "summary": "Read warehouse-repo next: it is the clearest current example of improvement after intervention.",
    }
    report.action_sync_automation = [
        {
            "campaign_type": "promotion-push",
            "label": "Promotion Push",
            "automation_posture": "follow-up-safe",
            "automation_reason": "Only non-mutating follow-up is appropriate right now.",
            "review_required": False,
            "recommended_command": "audit user --control-center",
            "recommended_follow_up": "Use a non-mutating follow-up for Promotion Push, then review the refreshed workbook or control center.",
            "requires_approval": False,
            "summary": "Promotion Push is follow-up-safe: use a non-mutating refresh or control-center pass next. Safe follow-up command: audit user --control-center.",
        }
    ]
    report.automation_guidance_summary = {
        "summary": "Use a non-mutating follow-up for Promotion Push next.",
        "counts": {"follow-up-safe": 1},
    }
    report.next_safe_automation_step = {
        "campaign_type": "promotion-push",
        "automation_posture": "follow-up-safe",
        "summary": "Use a non-mutating follow-up for Promotion Push next.",
        "recommended_command": "audit user --control-center",
    }
    report.operator_summary.update(
        {
            "action_sync_outcomes": report.action_sync_outcomes,
            "campaign_outcomes_summary": report.campaign_outcomes_summary,
            "next_monitoring_step": report.next_monitoring_step,
            "action_sync_tuning": report.action_sync_tuning,
            "campaign_tuning_summary": report.campaign_tuning_summary,
            "next_tuned_campaign": report.next_tuned_campaign,
            "historical_portfolio_intelligence": report.historical_portfolio_intelligence,
            "intervention_ledger_summary": report.intervention_ledger_summary,
            "next_historical_focus": report.next_historical_focus,
            "action_sync_automation": report.action_sync_automation,
            "automation_guidance_summary": report.automation_guidance_summary,
            "next_safe_automation_step": report.next_safe_automation_step,
        }
    )
    db_path = write_warehouse_snapshot(report, tmp_path)

    conn = sqlite3.connect(db_path)
    try:
        audit_runs = conn.execute("SELECT COUNT(*) FROM audit_runs").fetchone()[0]
        repo_rows = conn.execute("SELECT COUNT(*) FROM repos").fetchone()[0]
        lens_rows = conn.execute("SELECT COUNT(*) FROM lens_scores").fetchone()[0]
        action_rows = conn.execute("SELECT COUNT(*) FROM actions").fetchone()[0]
        collection_rows = conn.execute("SELECT COUNT(*) FROM collections").fetchone()[0]
        scenario_rows = conn.execute("SELECT COUNT(*) FROM scenarios").fetchone()[0]
        control_rows = conn.execute("SELECT COUNT(*) FROM security_controls").fetchone()[0]
        provider_rows = conn.execute("SELECT COUNT(*) FROM security_providers").fetchone()[0]
        recommendation_rows = conn.execute("SELECT COUNT(*) FROM security_recommendations").fetchone()[0]
        campaign_history_rows = conn.execute("SELECT COUNT(*) FROM campaign_history").fetchone()[0]
        campaign_outcome_rows = conn.execute("SELECT COUNT(*) FROM campaign_outcomes").fetchone()[0]
        campaign_tuning_rows = conn.execute("SELECT COUNT(*) FROM campaign_tuning").fetchone()[0]
        intervention_ledger_rows = conn.execute("SELECT COUNT(*) FROM intervention_ledger").fetchone()[0]
        action_sync_automation_rows = conn.execute("SELECT COUNT(*) FROM action_sync_automation").fetchone()[0]
        hotspot_history_rows = conn.execute("SELECT COUNT(*) FROM repo_implementation_hotspots").fetchone()[0]
        catalog_rows = conn.execute("SELECT COUNT(*) FROM portfolio_catalog_entries").fetchone()[0]
        catalog_contract = conn.execute(
            "SELECT operating_path, path_override, path_confidence, path_rationale FROM portfolio_catalog_entries"
        ).fetchone()
        scorecard_rows = conn.execute("SELECT COUNT(*) FROM repo_scorecards").fetchone()[0]
    finally:
        conn.close()

    assert audit_runs == 1
    assert repo_rows == 1
    assert lens_rows >= 5
    assert action_rows >= 1
    assert collection_rows >= 1
    assert scenario_rows >= 1
    assert control_rows >= 4
    assert provider_rows >= 1
    assert recommendation_rows >= 1
    assert campaign_history_rows == 1
    assert campaign_outcome_rows == 1
    assert campaign_tuning_rows == 1
    assert intervention_ledger_rows == 1
    assert action_sync_automation_rows == 1
    assert hotspot_history_rows == 1
    assert catalog_rows == 1
    assert catalog_contract == (
        "maintain",
        "",
        "high",
        "Stable path is Maintain from intended disposition.",
    )
    assert scorecard_rows == 1

    campaign_outcomes = load_campaign_outcomes(tmp_path, "user", limit=5)
    campaign_tuning = load_campaign_tuning(tmp_path, "user", limit=5)
    action_sync_automation = load_action_sync_automation(tmp_path, "user", limit=5)
    intervention_ledger = load_intervention_ledger(tmp_path, "user", limit=5)
    history = load_campaign_history(tmp_path, "promotion-push")
    recent_campaign_history = load_recent_campaign_history(tmp_path, "user", limit=5)
    hotspot_history = load_recent_implementation_hotspots(tmp_path, "user", limit=5)
    repo_scorecards = load_recent_repo_scorecards(tmp_path, "user", limit=5)
    latest_state = load_latest_campaign_state(tmp_path, "promotion-push")
    latest_runs = load_latest_audit_runs(tmp_path, "user", limit=5)
    review_history = load_review_history(tmp_path, "user", limit=5)
    watch_checkpoint = load_watch_checkpoint(tmp_path, "user")
    operator_state = load_latest_operator_state(tmp_path, "user")
    assert history[0]["action_id"] == "promotion-push-abc123"
    assert latest_state["actions"]["promotion-push-abc123"]["repo_full_name"] == "user/warehouse-repo"
    assert latest_runs[0]["review_summary"]["review_id"] == "review-1"
    assert latest_runs[0]["governance_summary"]["status"] == "blocked"
    assert latest_runs[0]["portfolio_catalog_summary"]["summary"] == "1/1 repos have an explicit catalog contract."
    assert latest_runs[0]["operating_paths_summary"]["summary"] == "Maintain 1"
    assert latest_runs[0]["intent_alignment_summary"]["summary"] == "1 aligned, 0 needing review, and 0 missing a contract."
    assert latest_runs[0]["scorecards_summary"]["summary"].startswith("0 repos are on track")
    assert latest_runs[0]["scorecard_programs"]["maintain"]["label"] == "Maintain"
    assert latest_runs[0]["portfolio_outcomes_summary"]["summary"].startswith("Managed action closure")
    assert latest_runs[0]["operator_effectiveness_summary"]["summary"].startswith("recommendation validation")
    assert latest_runs[0]["decision_quality_summary"]["contract_version"] == "decision_quality_v1"
    assert latest_runs[0]["decision_quality_summary"]["authority_cap"] == "bounded-automation"
    assert latest_runs[0]["high_pressure_queue_history"][0]["high_pressure_count"] == 1
    assert latest_runs[0]["campaign_outcomes_summary"]["summary"].startswith("Promotion Push was applied recently")
    assert latest_runs[0]["automation_guidance_summary"]["summary"].startswith("Use a non-mutating follow-up")
    assert action_sync_automation[0]["automation_posture"] == "follow-up-safe"
    assert operator_state["automation_guidance_summary"]["summary"].startswith("Use a non-mutating follow-up")
    assert operator_state["next_safe_automation_step"]["recommended_command"] == "audit user --control-center"
    assert latest_runs[0]["campaign_tuning_summary"]["summary"].startswith("Promotion Push should win ties")
    assert latest_runs[0]["baseline_signature"] == report.baseline_signature
    assert latest_runs[0]["baseline_context"]["portfolio_baseline_size"] == 1
    assert campaign_outcomes[0]["campaign_type"] == "promotion-push"
    assert campaign_outcomes[0]["monitoring_state"] == "monitor-now"
    assert campaign_tuning[0]["campaign_type"] == "promotion-push"
    assert campaign_tuning[0]["tuning_status"] == "proven"
    assert intervention_ledger[0]["repo"] == "warehouse-repo"
    assert intervention_ledger[0]["historical_intelligence_status"] == "improving-after-intervention"
    assert hotspot_history[0]["repo"] == "warehouse-repo"
    assert repo_scorecards[0]["repo"] == "warehouse-repo"
    assert review_history[0]["review_id"] == "review-1"
    assert watch_checkpoint["filter_signature"] == "abc123"
    assert operator_state["operator_summary"]["headline"] == "Campaign work is ready for review."
    assert operator_state["governance_summary"]["needs_reapproval"] is True
    assert operator_state["portfolio_catalog_summary"]["summary"] == "1/1 repos have an explicit catalog contract."
    assert operator_state["operating_paths_summary"]["summary"] == "Maintain 1"
    assert operator_state["scorecards_summary"]["summary"].startswith("0 repos are on track")
    assert operator_state["scorecard_programs"]["maintain"]["label"] == "Maintain"
    assert operator_state["portfolio_outcomes_summary"]["summary"].startswith("Managed action closure")
    assert operator_state["operator_effectiveness_summary"]["summary"].startswith("recommendation validation")
    assert operator_state["decision_quality_summary"]["decision_quality_status"] == "trusted"
    assert operator_state["decision_quality_summary"]["authority_cap"] == "bounded-automation"
    assert operator_state["high_pressure_queue_history"][0]["high_pressure_count"] == 1
    assert operator_state["campaign_outcomes_summary"]["summary"].startswith("Promotion Push was applied recently")
    assert operator_state["campaign_tuning_summary"]["summary"].startswith("Promotion Push should win ties")
    assert operator_state["next_tuned_campaign"]["summary"].startswith("Promotion Push should win ties")
    assert operator_state["intervention_ledger_summary"]["summary"].startswith("warehouse-repo is improving after intervention")
    assert operator_state["next_historical_focus"]["summary"].startswith("Read warehouse-repo next")
    assert recent_campaign_history[0]["action_id"] == "promotion-push-abc123"


def test_write_warehouse_snapshot_defaults_empty_campaign_outcomes_for_older_style_rows(tmp_path):
    audit = score_repo(_make_metadata(), _make_results())

    from src.models import AuditReport

    report = AuditReport.from_audits("user", [audit], [], 1)
    write_warehouse_snapshot(report, tmp_path)

    latest_runs = load_latest_audit_runs(tmp_path, "user", limit=1)
    operator_state = load_latest_operator_state(tmp_path, "user")

    assert latest_runs[0]["campaign_outcomes_summary"] == {}
    assert latest_runs[0]["campaign_tuning_summary"] == {}
    assert latest_runs[0]["intervention_ledger_summary"] == {}
    assert latest_runs[0]["decision_quality_summary"]["decision_quality_status"] == "insufficient-data"
    assert latest_runs[0]["decision_quality_summary"]["downgrade_reasons"] == [
        "legacy-run-without-decision-quality-contract"
    ]
    assert operator_state["campaign_outcomes_summary"] == {}
    assert operator_state["campaign_tuning_summary"] == {}
    assert operator_state["intervention_ledger_summary"] == {}
    assert operator_state["decision_quality_summary"]["decision_quality_status"] == "insufficient-data"


def test_approval_workflow_summary_and_records_round_trip(tmp_path):
    audit = score_repo(_make_metadata(), _make_results())

    from src.models import AuditReport

    report = AuditReport.from_audits("user", [audit], [], 1)
    report.approval_workflow_summary = {
        "summary": "Governance: all is the strongest approval review candidate right now."
    }
    report.approval_ledger = [
        {
            "approval_id": "governance:all",
            "approval_subject_type": "governance",
            "subject_key": "all",
            "label": "Governance: all",
            "approval_state": "ready-for-review",
            "source_run_id": f"{report.username}:{report.generated_at.isoformat()}",
            "fingerprint": "fingerprint-1",
            "approved_at": "",
            "approved_by": "",
            "apply_ready_after_approval": True,
            "summary": "Governance scope all is ready for review.",
        }
    ]
    report.operator_summary = {
        "approval_ledger": report.approval_ledger,
        "approval_workflow_summary": report.approval_workflow_summary,
        "next_approval_review": {"summary": "Review Governance: all next."},
    }
    write_warehouse_snapshot(report, tmp_path)

    latest = load_latest_audit_runs(tmp_path, "user", limit=1)[0]
    assert latest["approval_workflow_summary"]["summary"].startswith("Governance: all")

    save_approval_record(
        tmp_path,
        {
            "approval_id": "governance:all",
            "approval_subject_type": "governance",
            "subject_key": "all",
            "source_run_id": f"{report.username}:{report.generated_at.isoformat()}",
            "fingerprint": "fingerprint-1",
            "approved_at": report.generated_at.isoformat(),
            "approved_by": "sam",
            "approval_note": "Reviewed locally",
            "details_json": {"action_count": 1, "applyable_count": 1},
        },
    )
    loaded = load_approval_records(tmp_path, "user")
    assert loaded[0]["approval_note"] == "Reviewed locally"


def test_approval_followup_events_round_trip(tmp_path):
    audit = score_repo(_make_metadata(), _make_results())

    from src.models import AuditReport

    report = AuditReport.from_audits("user", [audit], [], 1)
    write_warehouse_snapshot(report, tmp_path)

    save_approval_followup_event(
        tmp_path,
        {
            "event_id": "followup-1",
            "approval_id": "governance:all",
            "fingerprint": "fingerprint-1",
            "approval_subject_type": "governance",
            "subject_key": "all",
            "source_run_id": f"{report.username}:{report.generated_at.isoformat()}",
            "reviewed_at": report.generated_at.isoformat(),
            "reviewed_by": "sam",
            "review_note": "Still valid",
            "cadence_days": 7,
            "details_json": {"summary": "Still valid"},
        },
    )

    loaded = load_approval_followup_events(tmp_path, "user")
    assert loaded[0]["review_note"] == "Still valid"
    assert loaded[0]["cadence_days"] == 7
