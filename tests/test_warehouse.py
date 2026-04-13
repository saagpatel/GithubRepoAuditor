from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from src.baseline_context import build_baseline_context
from src.models import AnalyzerResult, RepoMetadata
from src.scorer import WEIGHTS, score_repo
from src.warehouse import (
    load_campaign_history,
    load_latest_audit_runs,
    load_latest_campaign_state,
    load_latest_operator_state,
    load_review_history,
    load_watch_checkpoint,
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
        "notes": "",
        "intent_alignment": "aligned",
        "intent_alignment_reason": "The repo is holding a maintain posture without urgent or revalidation pressure.",
        "catalog_line": "operator-loop | warehouse verification | lifecycle active | criticality high | cadence weekly | disposition maintain",
    }
    report.portfolio_catalog_summary = {"summary": "1/1 repos have an explicit catalog contract."}
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
        catalog_rows = conn.execute("SELECT COUNT(*) FROM portfolio_catalog_entries").fetchone()[0]
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
    assert catalog_rows == 1
    assert scorecard_rows == 1

    history = load_campaign_history(tmp_path, "promotion-push")
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
    assert latest_runs[0]["intent_alignment_summary"]["summary"] == "1 aligned, 0 needing review, and 0 missing a contract."
    assert latest_runs[0]["scorecards_summary"]["summary"].startswith("0 repos are on track")
    assert latest_runs[0]["scorecard_programs"]["maintain"]["label"] == "Maintain"
    assert latest_runs[0]["baseline_signature"] == report.baseline_signature
    assert latest_runs[0]["baseline_context"]["portfolio_baseline_size"] == 1
    assert review_history[0]["review_id"] == "review-1"
    assert watch_checkpoint["filter_signature"] == "abc123"
    assert operator_state["operator_summary"]["headline"] == "Campaign work is ready for review."
    assert operator_state["governance_summary"]["needs_reapproval"] is True
    assert operator_state["portfolio_catalog_summary"]["summary"] == "1/1 repos have an explicit catalog contract."
    assert operator_state["scorecards_summary"]["summary"].startswith("0 repos are on track")
    assert operator_state["scorecard_programs"]["maintain"]["label"] == "Maintain"
