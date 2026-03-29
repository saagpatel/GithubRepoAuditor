from __future__ import annotations

from argparse import Namespace
from datetime import datetime, timedelta, timezone

from src.models import AnalyzerResult, AuditReport, RepoAudit, RepoMetadata
from src.recurring_review import build_review_bundle, choose_watch_plan
from src.scorer import WEIGHTS, score_repo
from src.warehouse import load_review_history, load_watch_checkpoint, write_warehouse_snapshot


def _metadata(name: str = "repo-a") -> RepoMetadata:
    return RepoMetadata(
        name=name,
        full_name=f"user/{name}",
        description="Recurring review test repo",
        language="Python",
        languages={"Python": 1000},
        private=False,
        fork=False,
        archived=False,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        pushed_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
        default_branch="main",
        stars=1,
        forks=0,
        open_issues=0,
        size_kb=128,
        html_url=f"https://github.com/user/{name}",
        clone_url=f"https://github.com/user/{name}.git",
        topics=["python"],
    )


def _results() -> list[AnalyzerResult]:
    items = [
        AnalyzerResult(dimension=dimension, score=0.7, max_score=1.0, findings=[], details={})
        for dimension in WEIGHTS
    ]
    items.append(AnalyzerResult(dimension="interest", score=0.55, max_score=1.0, findings=[], details={}))
    items.append(
        AnalyzerResult(
            dimension="security",
            score=0.5,
            max_score=1.0,
            findings=["No SECURITY.md"],
            details={"secrets_found": 0, "dangerous_files": [], "has_security_md": False, "has_dependabot": True},
        )
    )
    return items


def _report_dict() -> dict:
    audit = score_repo(_metadata(), _results())
    report = AuditReport.from_audits("user", [audit], [], 1)
    return report.to_dict()


def test_build_review_bundle_detects_material_changes(tmp_path):
    report_data = _report_dict()
    report_data["governance_preview"] = {"applyable_count": 2, "actions": []}
    diff_data = {
        "tier_changes": [{"name": "repo-a", "old_tier": "wip", "new_tier": "functional"}],
        "repo_changes": [
            {
                "name": "repo-a",
                "delta": 0.08,
                "old_tier": "wip",
                "new_tier": "functional",
                "lens_deltas": {"ship_readiness": 0.1},
                "security_change": {"old_label": "watch", "new_label": "healthy", "delta": 0.06},
                "hotspot_change": {"old_count": 0, "new_count": 1, "old_primary": "", "new_primary": "Testing gap"},
            }
        ],
    }
    report_data["audits"][0]["hotspots"] = [{"title": "Testing gap", "severity": 0.7}]
    bundle = build_review_bundle(
        report_data,
        output_dir=tmp_path,
        diff_data=diff_data,
        materiality="standard",
        portfolio_profile="default",
    )

    assert bundle["review_summary"]["material_change_count"] >= 4
    assert any(item["change_type"] == "tier-change" for item in bundle["material_changes"])
    assert any(item["decision"] == "approve-governance" for item in bundle["review_summary"]["decisions"])


def test_choose_watch_plan_prefers_full_without_baseline(tmp_path):
    args = Namespace(
        username="user",
        skip_forks=False,
        skip_archived=False,
        security_offline=False,
        scorecard=False,
        portfolio_profile="default",
        collection=None,
        watch_strategy="adaptive",
    )
    plan = choose_watch_plan(tmp_path, args, scoring_profile="default")
    assert plan.mode == "full"


def test_choose_watch_plan_uses_incremental_when_recent_full_exists(tmp_path):
    audit = score_repo(_metadata(), _results())
    report = AuditReport.from_audits("user", [audit], [], 1)
    report.review_summary = {
        "review_id": "user:review-1",
        "source_run_id": f"{report.username}:{report.generated_at.isoformat()}",
        "generated_at": report.generated_at.isoformat(),
        "materiality": "standard",
        "emitted": True,
        "safe_to_defer": False,
        "material_change_count": 1,
        "top_change_types": ["score-delta"],
        "review_sync": "local",
        "material_fingerprint": "abc",
        "decisions": [{"decision": "inspect-top-targets", "reason": "material"}],
    }
    report.watch_state = {"filter_signature": "same-signature"}
    write_warehouse_snapshot(report, tmp_path)

    args = Namespace(
        username="user",
        skip_forks=False,
        skip_archived=False,
        security_offline=False,
        scorecard=False,
        portfolio_profile="default",
        collection=None,
        watch_strategy="adaptive",
    )
    from src import recurring_review

    original = recurring_review.build_filter_signature
    recurring_review.build_filter_signature = lambda _args, scoring_profile: "same-signature"
    try:
        plan = choose_watch_plan(tmp_path, args, scoring_profile="default")
    finally:
        recurring_review.build_filter_signature = original

    assert plan.mode == "incremental"


def test_write_warehouse_snapshot_persists_review_rows(tmp_path):
    audit = score_repo(_metadata(), _results())
    report = AuditReport.from_audits("user", [audit], [], 1)
    report.review_summary = {
        "review_id": "user:review-1",
        "source_run_id": f"{report.username}:{report.generated_at.isoformat()}",
        "generated_at": (report.generated_at + timedelta(minutes=1)).isoformat(),
        "materiality": "standard",
        "emitted": True,
        "safe_to_defer": False,
        "material_change_count": 1,
        "top_change_types": ["score-delta"],
        "review_sync": "mixed",
        "material_fingerprint": "fingerprint",
        "decisions": [{"decision": "inspect-top-targets", "reason": "material"}],
    }
    report.material_changes = [
        {
            "change_key": "change-1",
            "change_type": "score-delta",
            "repo_name": "repo-a",
            "severity": 0.8,
            "title": "repo-a moved materially",
            "summary": "Overall score changed by +0.08",
            "recommended_next_step": "Inspect it",
        }
    ]
    report.review_targets = [{"repo": "repo-a", "reason": "Inspect", "recommended_next_step": "Inspect it"}]
    report.watch_state = {"filter_signature": "sig"}
    write_warehouse_snapshot(report, tmp_path)

    checkpoint = load_watch_checkpoint(tmp_path, "user")
    history = load_review_history(tmp_path, "user", limit=5)

    assert checkpoint is not None
    assert checkpoint["last_review_id"] == "user:review-1"
    assert history
    assert history[0]["review_id"] == "user:review-1"
