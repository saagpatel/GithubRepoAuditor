from __future__ import annotations

from argparse import Namespace
from datetime import datetime, timedelta, timezone

from src.baseline_context import build_baseline_context
from src.models import AuditReport, RepoAudit, RepoMetadata
from src.recurring_review import (
    MATERIALITY_THRESHOLDS,
    choose_watch_plan,
    evaluate_material_changes,
)
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
    report = AuditReport.from_audits(
        "testuser", [audit], [], 1, scoring_profile="default", run_mode="full"
    )
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


def test_material_changes_skip_resolved_security_posture():
    changes = evaluate_material_changes(
        {"audits": []},
        diff_data={
            "repo_changes": [
                {
                    "name": "RepoA",
                    "delta": 0.0,
                    "lens_deltas": {},
                    "security_change": {
                        "old_label": "watch",
                        "new_label": "healthy",
                        "old_score": 0.8,
                        "new_score": 0.9,
                        "delta": 0.1,
                    },
                }
            ]
        },
        thresholds=MATERIALITY_THRESHOLDS["standard"],
    )

    assert changes == []


def test_material_changes_lens_delta_preserves_per_lens_value():
    changes = evaluate_material_changes(
        {"audits": []},
        diff_data={
            "repo_changes": [
                {
                    "name": "RepoA",
                    "delta": 0.0,
                    "lens_deltas": {"security_posture": 0.077},
                    "security_change": {},
                }
            ]
        },
        thresholds=MATERIALITY_THRESHOLDS["standard"],
    )
    lens_changes = [c for c in changes if c["change_type"] == "lens-delta"]
    assert len(lens_changes) == 1
    assert lens_changes[0]["details"]["lens"] == "security_posture"
    assert lens_changes[0]["details"]["delta"] == 0.077


def test_material_changes_filter_acknowledged_security_change():
    diff_data = {
        "repo_changes": [
            {
                "name": "RepoA",
                "delta": 0.0,
                "lens_deltas": {},
                "security_change": {
                    "old_label": "critical",
                    "new_label": "watch",
                    "old_score": 0.4,
                    "new_score": 0.7,
                    "delta": 0.3,
                },
            }
        ]
    }
    visible = evaluate_material_changes(
        {"audits": []},
        diff_data=diff_data,
        thresholds=MATERIALITY_THRESHOLDS["standard"],
    )
    assert [change["change_type"] for change in visible] == ["security-change"]

    ack = {
        "change_key": visible[0]["change_key"],
        "change_type": "security-change",
        "repo_name": "RepoA",
        "title": visible[0]["title"],
        "signature": {"old_label": "critical", "new_label": "watch"},
        "acknowledged_at": "2026-05-11T00:00:00+00:00",
        "reviewer": "alice",
        "note": "reviewed",
    }

    filtered = evaluate_material_changes(
        {"audits": []},
        diff_data=diff_data,
        thresholds=MATERIALITY_THRESHOLDS["standard"],
        acknowledgments=[ack],
    )
    assert filtered == []


def test_material_changes_keep_security_regression_after_ack():
    healthy_diff = {
        "repo_changes": [
            {
                "name": "RepoA",
                "delta": 0.0,
                "lens_deltas": {},
                "security_change": {
                    "old_label": "critical",
                    "new_label": "watch",
                    "old_score": 0.4,
                    "new_score": 0.7,
                    "delta": 0.3,
                },
            }
        ]
    }
    visible = evaluate_material_changes(
        {"audits": []},
        diff_data=healthy_diff,
        thresholds=MATERIALITY_THRESHOLDS["standard"],
    )
    ack = {
        "change_key": visible[0]["change_key"],
        "change_type": "security-change",
        "repo_name": "RepoA",
        "title": visible[0]["title"],
        "signature": {"old_label": "critical", "new_label": "watch"},
        "acknowledged_at": "2026-05-11T00:00:00+00:00",
        "reviewer": "alice",
        "note": "reviewed",
    }

    regression_diff = {
        "repo_changes": [
            {
                "name": "RepoA",
                "delta": 0.0,
                "lens_deltas": {},
                "security_change": {
                    "old_label": "watch",
                    "new_label": "critical",
                    "old_score": 0.7,
                    "new_score": 0.3,
                    "delta": -0.4,
                },
            }
        ]
    }
    surfaced = evaluate_material_changes(
        {"audits": []},
        diff_data=regression_diff,
        thresholds=MATERIALITY_THRESHOLDS["standard"],
        acknowledgments=[ack],
    )
    assert [change["change_type"] for change in surfaced] == ["security-change"]


def test_material_changes_keep_unresolved_security_improvement():
    changes = evaluate_material_changes(
        {"audits": []},
        diff_data={
            "repo_changes": [
                {
                    "name": "RepoA",
                    "delta": 0.0,
                    "lens_deltas": {},
                    "security_change": {
                        "old_label": "critical",
                        "new_label": "watch",
                        "old_score": 0.4,
                        "new_score": 0.7,
                        "delta": 0.3,
                    },
                }
            ]
        },
        thresholds=MATERIALITY_THRESHOLDS["standard"],
    )

    assert [change["change_type"] for change in changes] == ["security-change"]
