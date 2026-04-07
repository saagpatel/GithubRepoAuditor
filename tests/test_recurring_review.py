from __future__ import annotations

from argparse import Namespace
from datetime import datetime, timedelta, timezone

from src.baseline_context import build_baseline_context
from src.models import AuditReport, RepoAudit, RepoMetadata
from src.recurring_review import choose_watch_plan
from src.warehouse import write_warehouse_snapshot


def _make_args(tmp_path, **overrides) -> Namespace:
    defaults = {
        "username": "testuser",
        "output_dir": str(tmp_path),
        "skip_forks": False,
        "skip_archived": False,
        "scorecard": False,
        "security_offline": False,
        "watch_strategy": "adaptive",
    }
    defaults.update(overrides)
    return Namespace(**defaults)


def _write_full_run(
    tmp_path,
    *,
    generated_at: datetime | None = None,
    skip_forks: bool = False,
    with_baseline_context: bool = True,
) -> AuditReport:
    metadata = RepoMetadata(
        name="repo-a",
        full_name="testuser/repo-a",
        description="Sample repo",
        language="Python",
        languages={"Python": 100},
        private=False,
        fork=False,
        archived=False,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        pushed_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        default_branch="main",
        stars=1,
        forks=0,
        open_issues=0,
        size_kb=10,
        html_url="https://github.com/testuser/repo-a",
        clone_url="https://github.com/testuser/repo-a.git",
    )
    audit = RepoAudit(
        metadata=metadata,
        analyzer_results=[],
        overall_score=0.7,
        completeness_tier="functional",
    )
    report = AuditReport.from_audits("testuser", [audit], [], 1, scoring_profile="default", run_mode="full")
    report.generated_at = generated_at or datetime.now(timezone.utc)
    if with_baseline_context:
        report.baseline_context = build_baseline_context(
            username="testuser",
            scoring_profile="default",
            skip_forks=skip_forks,
            skip_archived=False,
            scorecard=False,
            security_offline=False,
            portfolio_baseline_size=1,
        )
        report.baseline_signature = report.baseline_context["baseline_signature"]
    write_warehouse_snapshot(report, tmp_path)
    return report


def test_choose_watch_plan_prefers_incremental_when_baseline_is_trustworthy(tmp_path):
    _write_full_run(tmp_path)

    plan = choose_watch_plan(tmp_path, _make_args(tmp_path), scoring_profile="default")

    assert plan.mode == "incremental"
    assert plan.reason == "adaptive-incremental"
    assert plan.latest_trusted_baseline["run_id"]


def test_choose_watch_plan_requires_full_when_baseline_context_is_missing(tmp_path):
    _write_full_run(tmp_path, with_baseline_context=False)

    plan = choose_watch_plan(tmp_path, _make_args(tmp_path), scoring_profile="default")

    assert plan.mode == "full"
    assert plan.reason == "missing-trustworthy-baseline"


def test_choose_watch_plan_escalates_when_filter_contract_changes(tmp_path):
    _write_full_run(tmp_path, skip_forks=False)

    plan = choose_watch_plan(
        tmp_path,
        _make_args(tmp_path, watch_strategy="incremental", skip_forks=True),
        scoring_profile="default",
    )

    assert plan.mode == "full"
    assert plan.reason == "filter-or-profile-changed"


def test_choose_watch_plan_marks_full_refresh_due(tmp_path):
    stale_time = datetime.now(timezone.utc) - timedelta(days=10)
    _write_full_run(tmp_path, generated_at=stale_time)

    plan = choose_watch_plan(tmp_path, _make_args(tmp_path), scoring_profile="default")

    assert plan.mode == "full"
    assert plan.reason == "full-refresh-due"
    assert plan.full_refresh_due is True
