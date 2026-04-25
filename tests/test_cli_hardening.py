from __future__ import annotations

import json
from argparse import Namespace
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src import cli
from src.baseline_context import build_baseline_context
from src.models import AnalyzerResult, AuditReport, RepoAudit


def _make_args(**overrides) -> Namespace:
    defaults = {
        "username": "testuser",
        "token": None,
        "output_dir": "output",
        "skip_forks": False,
        "skip_archived": False,
        "skip_clone": False,
        "registry": None,
        "sync_registry": False,
        "no_cache": True,
        "repos": None,
        "incremental": False,
        "verbose": False,
        "graphql": False,
        "diff": None,
        "badges": False,
        "upload_badges": False,
        "notion": False,
        "notion_sync": False,
        "portfolio_readme": False,
        "readme_suggestions": False,
        "notion_registry": False,
        "html": False,
        "excel_mode": "standard",
        "scoring_profile": None,
        "scorecards": None,
        "portfolio_profile": "default",
        "collection": None,
        "review_pack": False,
        "scorecard": False,
        "security_offline": False,
        "campaign": None,
        "writeback_target": None,
        "writeback_apply": False,
        "github_projects": False,
        "github_projects_config": None,
        "campaign_sync_mode": "reconcile",
        "governance_view": "all",
        "max_actions": 20,
        "auto_archive": False,
        "narrative": False,
        "pdf": False,
        "config": None,
        "doctor": False,
        "control_center": False,
        "approval_center": False,
        "triage_view": "all",
        "approval_view": "all",
        "approve_governance": False,
        "approve_packet": False,
        "review_governance": False,
        "review_packet": False,
        "governance_scope": "all",
        "approval_reviewer": None,
        "approval_note": "",
        "preflight_mode": "auto",
        "watch": False,
        "watch_interval": 3600,
        "watch_strategy": "adaptive",
        "create_issues": False,
        "analyzers_dir": None,
        "resume": False,
        "vuln_check": False,
        "generate_manifest": False,
        "apply_metadata": False,
        "apply_readmes": False,
        "improvements_file": None,
        "dry_run": False,
    }
    defaults.update(overrides)
    return Namespace(**defaults)


class FakeParser:
    def __init__(self, args: Namespace) -> None:
        self.args = args
        self.error_message: str | None = None

    def parse_args(self) -> Namespace:
        return self.args

    def error(self, message: str) -> None:
        self.error_message = message
        raise SystemExit(2)


def _make_report_dict(sample_metadata, *, baseline_size: int = 1, skip_forks: bool = False, skip_archived: bool = False, scorecard: bool = False, security_offline: bool = False, scoring_profile: str = "baseline") -> dict:
    audit = RepoAudit(
        metadata=sample_metadata,
        analyzer_results=[],
        overall_score=0.5,
        completeness_tier="functional",
    )
    report = AuditReport.from_audits(
        "testuser",
        [audit],
        [],
        1,
        scoring_profile=scoring_profile,
        run_mode="full",
        portfolio_baseline_size=baseline_size,
        baseline_signature=build_baseline_context(
            username="testuser",
            scoring_profile=scoring_profile,
            skip_forks=skip_forks,
            skip_archived=skip_archived,
            scorecard=scorecard,
            security_offline=security_offline,
            portfolio_baseline_size=baseline_size,
        )["baseline_signature"],
        baseline_context=build_baseline_context(
            username="testuser",
            scoring_profile=scoring_profile,
            skip_forks=skip_forks,
            skip_archived=skip_archived,
            scorecard=scorecard,
            security_offline=security_offline,
            portfolio_baseline_size=baseline_size,
        ),
    )
    return report.to_dict()


def test_main_rejects_registry_and_notion_registry_together(monkeypatch):
    args = _make_args(
        registry=Path("registry.md"),
        notion_registry=True,
    )

    monkeypatch.setattr(cli, "build_parser", lambda: FakeParser(args))

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 2


def test_main_rejects_writeback_apply_without_target(monkeypatch):
    args = _make_args(
        campaign="security-review",
        writeback_apply=True,
    )

    monkeypatch.setattr(cli, "build_parser", lambda: FakeParser(args))

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 2
    assert args.writeback_target is None


def test_main_rejects_github_projects_without_github_writeback(monkeypatch):
    args = _make_args(
        campaign="security-review",
        writeback_target="notion",
        github_projects=True,
    )
    parser = FakeParser(args)

    monkeypatch.setattr(cli, "build_parser", lambda: parser)

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 2
    assert "Action Sync" in parser.error_message


def test_build_parser_help_groups_examples_by_mode():
    parser = cli.build_parser()
    help_text = parser.format_help()

    assert "First Run" in help_text
    assert "Weekly Review" in help_text
    assert "Deep Dive" in help_text
    assert "Action Sync" in help_text
    assert "--doctor" in help_text
    assert "--control-center" in help_text
    assert "--github-projects" in help_text


def test_main_forwards_scoring_profile_to_targeted_audit(monkeypatch, sample_metadata):
    args = _make_args(
        repos=["test-repo"],
        scoring_profile="focus",
        preflight_mode="off",
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(cli, "build_parser", lambda: FakeParser(args))
    monkeypatch.setattr(cli, "_load_scoring_profile", lambda name: ({"readme": 1.5}, "focus"))
    monkeypatch.setattr(cli, "_fetch_repo_metadata", lambda *_: ([sample_metadata], []))
    monkeypatch.setattr(cli, "_run_targeted_audit", lambda *a, **k: captured.update(k))

    cli.main()

    assert captured["custom_weights"] == {"readme": 1.5}
    assert captured["scoring_profile_name"] == "focus"
    assert captured["all_repos"] == [sample_metadata]


def test_build_parser_defaults_excel_mode_to_standard():
    parser = cli.build_parser()
    args = parser.parse_args(["testuser"])
    assert args.excel_mode == "standard"


def test_build_parser_defaults_watch_strategy_to_adaptive():
    parser = cli.build_parser()
    args = parser.parse_args(["testuser"])
    assert args.watch_strategy == "adaptive"


def test_build_parser_accepts_scorecards_path():
    parser = cli.build_parser()
    args = parser.parse_args(["testuser", "--scorecards", "config/custom-scorecards.yaml"])
    assert str(args.scorecards) == "config/custom-scorecards.yaml"


def test_build_parser_accepts_github_projects_config_path():
    parser = cli.build_parser()
    args = parser.parse_args(["testuser", "--github-projects", "--github-projects-config", "config/custom-github-projects.yaml"])
    assert args.github_projects is True
    assert str(args.github_projects_config) == "config/custom-github-projects.yaml"


def test_main_rejects_writeback_target_without_campaign_with_mode_guidance(monkeypatch):
    args = _make_args(writeback_target="github")
    parser = FakeParser(args)

    monkeypatch.setattr(cli, "build_parser", lambda: parser)

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 2
    assert "Action Sync mode" in parser.error_message


def test_main_rejects_control_center_with_action_sync_flags(monkeypatch):
    args = _make_args(control_center=True, campaign="security-review", writeback_target="github")
    parser = FakeParser(args)

    monkeypatch.setattr(cli, "build_parser", lambda: parser)

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 2
    assert "read-only Weekly Review entrypoint" in parser.error_message


def test_main_rejects_approval_center_with_action_sync_flags(monkeypatch):
    args = _make_args(approval_center=True, campaign="security-review", writeback_target="github")
    parser = FakeParser(args)

    monkeypatch.setattr(cli, "build_parser", lambda: parser)

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 2
    assert "read-only approval view" in parser.error_message


def test_main_rejects_approve_packet_without_campaign(monkeypatch):
    args = _make_args(approve_packet=True)
    parser = FakeParser(args)

    monkeypatch.setattr(cli, "build_parser", lambda: parser)

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 2
    assert "--approve-packet requires --campaign" in parser.error_message


def test_main_rejects_approve_packet_with_writeback_apply(monkeypatch):
    args = _make_args(approve_packet=True, campaign="security-review", writeback_apply=True, writeback_target="all")
    parser = FakeParser(args)

    monkeypatch.setattr(cli, "build_parser", lambda: parser)

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 2
    assert "Remove --writeback-apply" in parser.error_message


def test_main_rejects_review_packet_without_campaign(monkeypatch):
    args = _make_args(review_packet=True)
    parser = FakeParser(args)

    monkeypatch.setattr(cli, "build_parser", lambda: parser)

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 2
    assert "--review-packet requires --campaign" in parser.error_message


def test_main_rejects_review_packet_with_writeback_apply(monkeypatch):
    args = _make_args(review_packet=True, campaign="security-review", writeback_apply=True, writeback_target="all")
    parser = FakeParser(args)

    monkeypatch.setattr(cli, "build_parser", lambda: parser)

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 2
    assert "local follow-up review only" in parser.error_message


def test_main_forwards_scoring_profile_to_incremental_audit(monkeypatch, sample_metadata):
    args = _make_args(
        incremental=True,
        scoring_profile="focus",
        preflight_mode="off",
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(cli, "build_parser", lambda: FakeParser(args))
    monkeypatch.setattr(cli, "_load_scoring_profile", lambda name: ({"readme": 1.5}, "focus"))
    monkeypatch.setattr(cli, "_fetch_repo_metadata", lambda *_: ([sample_metadata], []))
    monkeypatch.setattr(cli, "_run_incremental_audit", lambda *a, **k: captured.update(k))

    cli.main()

    assert captured["custom_weights"] == {"readme": 1.5}
    assert captured["scoring_profile_name"] == "focus"
    assert captured["all_repos"] == [sample_metadata]


def test_main_watch_uses_chosen_watch_plan(monkeypatch, sample_metadata, tmp_path):
    args = _make_args(
        watch=True,
        output_dir=str(tmp_path),
        preflight_mode="off",
    )
    captured: dict[str, object] = {}
    watch_plan = Namespace(
        mode="incremental",
        reason="adaptive-incremental",
        full_refresh_due=False,
        latest_trusted_baseline={"run_id": "baseline-1", "report_path": "output/audit-report-testuser.json"},
    )

    monkeypatch.setattr(cli, "build_parser", lambda: FakeParser(args))
    monkeypatch.setattr("src.recurring_review.choose_watch_plan", lambda *_a, **_k: watch_plan)
    monkeypatch.setattr("src.watch.run_watch_loop", lambda audit_fn, interval=0: audit_fn())
    monkeypatch.setattr(cli, "_load_scoring_profile", lambda name: (None, "default"))
    monkeypatch.setattr(cli, "_fetch_repo_metadata", lambda *_: ([sample_metadata], []))
    monkeypatch.setattr(cli, "_run_incremental_audit", lambda *a, **k: captured.update(k))

    cli.main()

    assert captured["watch_plan"] is watch_plan
    assert captured["latest_trusted_baseline"] == watch_plan.latest_trusted_baseline


def test_apply_scorecards_populates_report(monkeypatch, sample_metadata, tmp_path):
    scorecards_path = tmp_path / "scorecards.yaml"
    scorecards_path.write_text(
        """
programs:
  maintain:
    label: Maintain
    target_maturity: strong
    rules:
      - key: testing
        label: Testing
        check: dimension_at_least
        dimension: testing
        threshold: 0.80
        partial_threshold: 0.60
        weight: 1.0
"""
    )

    audit = RepoAudit(
        metadata=sample_metadata,
        analyzer_results=[
            AnalyzerResult("testing", 0.7, 1.0, [], {}),
            AnalyzerResult("activity", 0.8, 1.0, [], {"days_since_push": 30}),
        ],
        overall_score=0.7,
        completeness_tier="functional",
        flags=[],
        lenses={"ship_readiness": {"score": 0.75}},
        security_posture={"score": 0.8},
        portfolio_catalog={
            "has_explicit_entry": True,
            "intended_disposition": "maintain",
            "maturity_program": "maintain",
            "target_maturity": "strong",
        },
    )
    report = AuditReport.from_audits("testuser", [audit], [], 1)
    report.operator_queue = [{"repo": "test-repo", "title": "Review test-repo"}]

    updated = cli._apply_scorecards(report, _make_args(scorecards=scorecards_path))

    assert updated.audits[0].scorecard["program"] == "maintain"
    assert updated.scorecards_summary["status_counts"]["below-target"] == 1
    assert updated.operator_queue[0]["scorecard_line"].startswith("Scorecard: Maintain")


def test_main_doctor_writes_artifact_and_exits_cleanly(monkeypatch, tmp_path, capsys):
    args = _make_args(doctor=True, output_dir=str(tmp_path))
    artifact_path = tmp_path / "diagnostics-testuser-2026-03-29.json"

    class _Result:
        blocking_errors = 0

    monkeypatch.setattr(cli, "build_parser", lambda: FakeParser(args))
    monkeypatch.setattr("src.diagnostics.run_diagnostics", lambda *a, **k: _Result())
    monkeypatch.setattr("src.diagnostics.format_diagnostics_report", lambda result: "doctor ok")
    monkeypatch.setattr("src.diagnostics.write_diagnostics_report", lambda result, output_dir, username: artifact_path)

    cli.main()
    captured = capsys.readouterr()
    assert "Next step: run `audit testuser --html`" in (captured.out + captured.err)


def test_main_approval_center_writes_artifacts_without_apply(monkeypatch, tmp_path, sample_metadata, capsys):
    args = _make_args(approval_center=True, output_dir=str(tmp_path))
    report = cli._report_from_dict(_make_report_dict(sample_metadata))
    approval_json = tmp_path / "approval-center-testuser-2026-03-29.json"
    approval_md = tmp_path / "approval-center-testuser-2026-03-29.md"

    def _write_approval_center_artifacts(report_arg, output_dir, *, approval_view):
        assert report_arg.username == "testuser"
        assert output_dir == tmp_path
        assert approval_view == "all"
        approval_json.write_text("{}")
        approval_md.write_text("# approval\n")
        return (
            approval_json,
            approval_md,
            {
                "approval_workflow_summary": {"summary": "Approval queue needs local review."},
                "next_approval_review": {"summary": "Review governance approval next."},
            },
        )

    monkeypatch.setattr(cli, "build_parser", lambda: FakeParser(args))
    monkeypatch.setattr(
        cli,
        "_refresh_latest_report_state",
        lambda _output_dir, _args: (tmp_path / "audit-report-testuser-2026-03-29.json", {}, report),
    )
    monkeypatch.setattr(cli, "_write_approval_center_artifacts", _write_approval_center_artifacts)

    cli.main()

    assert approval_json.is_file()
    assert approval_md.is_file()
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Approval queue needs local review." in combined
    assert "Review governance approval next." in combined


def test_main_control_center_writes_artifacts_without_audit(monkeypatch, tmp_path, sample_metadata, capsys):
    args = _make_args(control_center=True, output_dir=str(tmp_path))
    report_path = tmp_path / "audit-report-testuser-2026-03-29.json"
    report_data = _make_report_dict(sample_metadata)
    report_path.write_text("{}")

    monkeypatch.setattr(cli, "build_parser", lambda: FakeParser(args))
    monkeypatch.setattr(cli, "_load_latest_report", lambda _output_dir: (report_path, report_data))
    monkeypatch.setattr("src.history.find_previous", lambda *_args, **_kwargs: None)

    cli.main()

    json_artifact = tmp_path / "operator-control-center-testuser-2026-03-29.json"
    md_artifact = tmp_path / "operator-control-center-testuser-2026-03-29.md"
    assert json_artifact.is_file()
    assert md_artifact.is_file()
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Reading order: workbook Dashboard" in combined
    assert "Move into Action Sync only when the local weekly story is already" in combined


def test_main_control_center_requires_latest_report(monkeypatch):
    args = _make_args(control_center=True)

    monkeypatch.setattr(cli, "build_parser", lambda: FakeParser(args))
    monkeypatch.setattr(cli, "_load_latest_report", lambda _output_dir: (None, None))

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 2


def test_auto_apply_dry_run_prints_automation_trust_bar(
    monkeypatch,
    tmp_path,
    sample_metadata,
    capsys,
):
    args = _make_args(output_dir=str(tmp_path), token=None)
    report_data = _make_report_dict(sample_metadata)
    report_data["operator_summary"] = {
        "decision_quality_v1": {"decision_quality_status": "trusted"}
    }
    report = cli._report_from_dict(report_data)
    truth_path = tmp_path / "portfolio-truth-latest.json"
    truth_path.write_text(
        json.dumps(
            {
                "projects": [
                    {
                        "identity": {"display_name": "Alpha"},
                        "declared": {"automation_eligible": True},
                        "risk": {"risk_tier": "baseline"},
                    },
                    {
                        "identity": {"display_name": "Beta"},
                        "declared": {"automation_eligible": True},
                        "risk": {"risk_tier": "elevated"},
                    },
                    {
                        "identity": {"display_name": "Gamma"},
                        "declared": {"automation_eligible": False},
                        "risk": {"risk_tier": "baseline"},
                    },
                ]
            }
        )
    )

    monkeypatch.setattr(
        cli,
        "_refresh_latest_report_state",
        lambda _output_dir, _args: (tmp_path / "audit-report-testuser-2026-03-29.json", {}, report),
    )
    monkeypatch.setattr(
        "src.approval_ledger.load_approval_ledger_bundle",
        lambda *_args, **_kwargs: {"approval_ledger": []},
    )

    cli._run_auto_apply_approved_mode(args, tmp_path)

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    normalized = " ".join(combined.split())
    assert "Automation trust bar: 2 opted-in repos" in normalized
    assert "1 baseline opted-in repos" in normalized
    assert "1 repos pass the full trust bar" in normalized
    assert "Automation-eligible repos: Alpha, Beta" in normalized
    assert "No approved-manual campaign packets found." in normalized


def test_auto_apply_dry_run_does_not_call_github_writeback(
    monkeypatch,
    tmp_path,
    sample_metadata,
    capsys,
):
    args = _make_args(output_dir=str(tmp_path), token="token", dry_run=True)
    report_data = _make_report_dict(sample_metadata)
    report_data["operator_summary"] = {
        "decision_quality_v1": {"decision_quality_status": "trusted"},
        "action_sync_packets": [
            {
                "campaign_type": "promotion-push",
                "label": "Promotion Push",
                "execution_state": "ready-to-apply",
                "recommended_target": "github",
                "sync_mode": "reconcile",
                "action_count": 1,
                "blocker_types": [],
                "actions": [{"action_id": "action-1"}],
            }
        ],
        "action_sync_automation": [
            {"campaign_type": "promotion-push", "automation_posture": "approval-first"}
        ],
    }
    report = cli._report_from_dict(report_data)
    (tmp_path / "portfolio-truth-latest.json").write_text(
        json.dumps(
            {
                "projects": [
                    {
                        "identity": {"display_name": "test-repo"},
                        "declared": {"automation_eligible": True},
                        "risk": {"risk_tier": "baseline"},
                    }
                ]
            }
        )
    )
    monkeypatch.setattr(
        cli,
        "_refresh_latest_report_state",
        lambda _output_dir, _args: (tmp_path / "audit-report-testuser-2026-03-29.json", {}, report),
    )
    monkeypatch.setattr(
        "src.approval_ledger.load_approval_ledger_bundle",
        lambda *_args, **_kwargs: {
            "approval_ledger": [
                {
                    "approval_id": "campaign:promotion-push",
                    "approval_subject_type": "campaign",
                    "subject_key": "promotion-push",
                    "approval_state": "approved-manual",
                    "sync_mode": "reconcile",
                }
            ]
        },
    )
    monkeypatch.setattr(
        "src.ops_writeback.build_campaign_bundle",
        lambda *_args, **_kwargs: (
            {"campaign_type": "promotion-push"},
            [
                {
                    "action_id": "action-1",
                    "repo": "test-repo",
                    "repo_full_name": "testuser/test-repo",
                    "writeback_targets": {
                        "github": {
                            "managed_topics": ["ghra-call-promotion-push"],
                            "issue_title": "[Repo Auditor] Promotion Push",
                        }
                    },
                }
            ],
        ),
    )

    def _apply_github_writeback(*_args, **_kwargs):
        raise AssertionError("dry-run must not call apply_github_writeback")

    monkeypatch.setattr("src.ops_writeback.apply_github_writeback", _apply_github_writeback)

    cli._run_auto_apply_approved_mode(args, tmp_path)

    captured = capsys.readouterr()
    normalized = " ".join((captured.out + captured.err).split())
    assert "1 eligible actions but dry-run mode is enabled" in normalized
    assert "Auto-apply complete: 0 applied, 0 skipped." in normalized


def test_main_approve_governance_captures_local_approval(monkeypatch, tmp_path, sample_metadata, capsys):
    args = _make_args(
        approve_governance=True,
        governance_scope="all",
        approval_reviewer="local-reviewer",
        approval_note="looks good",
        output_dir=str(tmp_path),
    )
    report = cli._report_from_dict(_make_report_dict(sample_metadata))
    approval_json = tmp_path / "approval-center-testuser-2026-03-29.json"
    approval_md = tmp_path / "approval-center-testuser-2026-03-29.md"
    saved: dict[str, object] = {}
    bundle_calls = {"count": 0}

    ledger_record = {
        "approval_id": "governance:all",
        "approval_state": "ready-for-review",
        "approval_subject_type": "governance",
        "subject_key": "all",
        "fingerprint": "fp-1",
        "source_run_id": "run-1",
        "label": "Governance approvals",
        "summary": "Governance approvals are ready for local review.",
    }
    updated_record = {
        **ledger_record,
        "approval_state": "approved-manual",
        "summary": "Governance approval captured locally.",
    }

    def _load_approval_ledger_bundle(_output_dir, _report_data, _queue, *, approval_view):
        assert approval_view == "all"
        bundle_calls["count"] += 1
        record = ledger_record if bundle_calls["count"] == 1 else updated_record
        return {"approval_ledger": [record]}

    def _save_approval_record(_output_dir, record):
        saved["record"] = record

    def _write_approval_center_artifacts(report_arg, output_dir, *, approval_view):
        assert report_arg.username == "testuser"
        assert output_dir == tmp_path
        assert approval_view == "all"
        approval_json.write_text("{}")
        approval_md.write_text("# approval\n")
        return (
            approval_json,
            approval_md,
            {
                "approval_workflow_summary": {"summary": "Approval workflow refreshed."},
                "next_approval_review": {"summary": "No urgent follow-up review is due."},
            },
        )

    monkeypatch.setattr(cli, "build_parser", lambda: FakeParser(args))
    monkeypatch.setattr(
        cli,
        "_utcnow",
        lambda: datetime(2026, 4, 17, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(
        cli,
        "_refresh_latest_report_state",
        lambda _output_dir, _args: (tmp_path / "audit-report-testuser-2026-03-29.json", {}, report),
    )
    monkeypatch.setattr(cli, "_refresh_shared_artifacts_from_report", lambda *_a, **_k: {})
    monkeypatch.setattr(cli, "_write_approval_center_artifacts", _write_approval_center_artifacts)
    monkeypatch.setattr("src.approval_ledger.load_approval_ledger_bundle", _load_approval_ledger_bundle)
    monkeypatch.setattr(
        "src.approval_ledger.build_approval_record",
        lambda ledger_record, *, reviewer, note="": {
            "approval_id": ledger_record["approval_id"],
            "approval_subject_type": ledger_record["approval_subject_type"],
            "subject_key": ledger_record["subject_key"],
            "source_run_id": ledger_record["source_run_id"],
            "fingerprint": ledger_record["fingerprint"],
            "approved_at": "2026-03-29T00:00:00+00:00",
            "approved_by": reviewer,
            "approval_note": note,
        },
    )
    monkeypatch.setattr("src.warehouse.save_approval_record", _save_approval_record)

    cli.main()

    assert saved["record"]["approval_id"] == "governance:all"
    assert saved["record"]["approved_by"] == "local-reviewer"
    assert approval_json.is_file()
    assert approval_md.is_file()
    receipt_json = tmp_path / "approval-receipt-testuser-2026-04-17.json"
    receipt_md = tmp_path / "approval-receipt-testuser-2026-04-17.md"
    assert receipt_json.is_file()
    assert receipt_md.is_file()
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Governance approval captured locally." in combined
    assert "Approval receipt JSON" in combined


def test_main_generate_manifest_writes_artifact(monkeypatch, tmp_path, sample_metadata, capsys):
    args = _make_args(generate_manifest=True, output_dir=str(tmp_path))
    report_path = tmp_path / "audit-report-testuser-2026-03-29.json"
    manifest_path = tmp_path / "improvement-manifest.json"
    report_data = _make_report_dict(sample_metadata)

    monkeypatch.setattr(cli, "build_parser", lambda: FakeParser(args))
    monkeypatch.setattr(cli, "_load_latest_report", lambda _output_dir: (report_path, report_data))
    monkeypatch.setattr("src.repo_improver.generate_manifest", lambda data: [{"repo": "testuser/test-repo"}])

    def _write_manifest(manifest, output_dir):
        assert manifest == [{"repo": "testuser/test-repo"}]
        assert output_dir == tmp_path
        manifest_path.write_text("[]")
        return manifest_path

    monkeypatch.setattr("src.repo_improver.write_manifest", _write_manifest)

    cli.main()

    assert manifest_path.is_file()
    captured = capsys.readouterr()
    assert "Improvement manifest:" in (captured.out + captured.err)


def test_main_apply_improvements_writes_execution_report(monkeypatch, tmp_path, capsys):
    args = _make_args(
        apply_metadata=True,
        apply_readmes=True,
        improvements_file=tmp_path / "improvements.json",
        output_dir=str(tmp_path),
        dry_run=True,
    )
    execution_report = tmp_path / "improvement-execution-report.json"
    args.improvements_file.write_text("{}")

    monkeypatch.setattr(cli, "build_parser", lambda: FakeParser(args))
    monkeypatch.setattr(
        "src.repo_improver.load_improvements",
        lambda path: {
            "testuser/test-repo": {
                "repo": "testuser/test-repo",
                "name": "test-repo",
                "description": "Updated description",
                "topics": ["python"],
                "readme": "# Test Repo",
            }
        },
    )

    metadata_calls: dict[str, object] = {}
    readme_calls: dict[str, object] = {}

    def _apply_metadata_updates(client, owner, updates, *, dry_run=False):
        metadata_calls["owner"] = owner
        metadata_calls["updates"] = updates
        metadata_calls["dry_run"] = dry_run
        return [{"repo": "test-repo", "actions": [{"type": "description", "dry_run": True}]}]

    def _apply_readme_updates(client, owner, updates, *, dry_run=False):
        readme_calls["owner"] = owner
        readme_calls["updates"] = updates
        readme_calls["dry_run"] = dry_run
        return [{"repo": "test-repo", "dry_run": True}]

    monkeypatch.setattr("src.repo_improver.apply_metadata_updates", _apply_metadata_updates)
    monkeypatch.setattr("src.repo_improver.apply_readme_updates", _apply_readme_updates)
    monkeypatch.setattr("src.repo_improver.generate_execution_report", lambda results, output_dir: execution_report)

    cli.main()

    assert metadata_calls["owner"] == "testuser"
    assert metadata_calls["dry_run"] is True
    assert readme_calls["owner"] == "testuser"
    assert readme_calls["dry_run"] is True
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Metadata updates: 1 actions previewed" in combined
    assert "README updates: 1 repos previewed" in combined
    assert "Execution report:" in combined


def test_main_auto_preflight_blocks_on_errors(monkeypatch):
    args = _make_args(repos=["test-repo"], output_dir="missing-baseline-output")

    monkeypatch.setattr(cli, "build_parser", lambda: FakeParser(args))

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 1


def test_main_strict_preflight_blocks_on_warnings(monkeypatch):
    args = _make_args(preflight_mode="strict", token=None)

    monkeypatch.setattr(cli, "build_parser", lambda: FakeParser(args))
    monkeypatch.setattr("src.diagnostics._resolve_github_token", lambda token: ("", ""))

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 1


def test_main_preflight_off_skips_auto_preflight(monkeypatch, sample_metadata):
    args = _make_args(repos=["test-repo"], preflight_mode="off")
    captured: dict[str, object] = {}

    monkeypatch.setattr(cli, "build_parser", lambda: FakeParser(args))
    monkeypatch.setattr(cli, "_load_scoring_profile", lambda name: (None, "default"))
    monkeypatch.setattr(cli, "_fetch_repo_metadata", lambda *_: ([sample_metadata], []))
    monkeypatch.setattr(cli, "_run_targeted_audit", lambda *a, **k: captured.update(k))

    cli.main()

    assert captured["all_repos"] == [sample_metadata]


def test_print_output_summary_emits_normal_audit_hint(capsys, sample_metadata):
    audit = RepoAudit(
        metadata=sample_metadata,
        analyzer_results=[],
        overall_score=0.5,
        completeness_tier="functional",
    )
    report = AuditReport.from_audits("testuser", [audit], [], 1)

    cli._print_output_summary(
        "Audited 1 repos for testuser",
        report,
        {
            "cache_info": "",
            "json_path": "output/audit-report.json",
            "md_path": "output/audit-report.md",
            "excel_path": "output/audit-report.xlsx",
            "pcc_path": "output/pcc.json",
            "raw_path": "output/raw.json",
            "warehouse_path": "output/history.db",
            "badge_info": "",
            "notion_info": "",
            "readme_info": "",
            "suggestions_info": "",
            "html_info": "",
            "pdf_info": "",
            "review_pack_info": "",
        },
    )

    captured = capsys.readouterr()
    assert "Next step: open the standard workbook first" in (captured.out + captured.err)


def test_print_output_summary_emits_post_apply_monitoring_hints(capsys, sample_metadata):
    audit = RepoAudit(
        metadata=sample_metadata,
        analyzer_results=[],
        overall_score=0.5,
        completeness_tier="functional",
    )
    report = AuditReport.from_audits("testuser", [audit], [], 1)
    report.campaign_outcomes_summary = {
        "summary": "Security Review was applied recently; monitor it now before treating it as stable.",
    }
    report.next_monitoring_step = {
        "summary": "Monitor Security Review for at least 2 post-apply runs before treating it as stable.",
    }
    report.campaign_tuning_summary = {
        "summary": "Security Review should win ties because recent outcomes are proven.",
    }
    report.next_tuned_campaign = {
        "summary": "Security Review should win ties inside the preview-ready group because recent outcome history is proven.",
    }

    cli._print_output_summary(
        "Audited 1 repos for testuser",
        report,
        {
            "cache_info": "",
            "json_path": "output/audit-report.json",
            "md_path": "output/audit-report.md",
            "excel_path": "output/audit-report.xlsx",
            "pcc_path": "output/pcc.json",
            "raw_path": "output/raw.json",
            "warehouse_path": "output/history.db",
            "badge_info": "",
            "notion_info": "",
            "readme_info": "",
            "suggestions_info": "",
            "html_info": "",
            "pdf_info": "",
            "review_pack_info": "",
        },
    )

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Post-apply monitoring: Security Review was applied recently" in combined
    assert "Next monitoring step: Monitor Security Review for at least 2 post-apply runs" in combined
    assert "Campaign tuning: Security Review should win ties" in combined
    assert "Next Tie-Break Candidate: Security Review should win ties inside" in combined


def test_incremental_noop_regenerates_from_latest_report(monkeypatch, tmp_path, sample_metadata):
    args = _make_args(username="testuser")
    report_path = tmp_path / "audit-report-testuser-2026-03-29.json"
    report_path.write_text("{}")
    report_data = _make_report_dict(sample_metadata)
    report_data["audits"][0]["metadata"]["name"] = sample_metadata.name

    monkeypatch.setattr(cli, "_load_latest_report", lambda _output_dir: (report_path, report_data))
    monkeypatch.setattr(
        "src.history.load_fingerprints",
        lambda *_args, **_kwargs: {sample_metadata.name: {"pushed_at": sample_metadata.pushed_at.isoformat()}},
    )

    calls: list[dict[str, object]] = []

    def _record_regen(args, output_dir, *, client, existing_report_path, existing_report_data, watch_state_override=None):
        calls.append(
            {
                "args": args,
                "output_dir": output_dir,
                "client": client,
                "existing_report_path": existing_report_path,
                "existing_report_data": existing_report_data,
                "watch_state_override": watch_state_override,
            }
        )

    monkeypatch.setattr(cli, "_regenerate_outputs_from_latest_report", _record_regen)

    cli._run_incremental_audit(
        args,
        cli.GitHubClient(token=None, cache=None),
        tmp_path / "output",
        all_repos=[sample_metadata],
        errors=[],
        custom_weights=None,
        scoring_profile_name="baseline",
    )

    assert len(calls) == 1
    assert calls[0]["client"] is not None
    assert calls[0]["existing_report_path"] == report_path
    assert calls[0]["existing_report_data"]["scoring_profile"] == "baseline"
    assert calls[0]["watch_state_override"]["chosen_mode"] == "incremental"


def test_targeted_audit_uses_full_filtered_portfolio_for_baseline(monkeypatch, tmp_path, sample_metadata):
    args = _make_args(username="testuser", repos=["test-repo"])
    other_repo = replace(
        sample_metadata,
        name="other-repo",
        full_name="testuser/other-repo",
        html_url="https://github.com/testuser/other-repo",
        clone_url="https://github.com/testuser/other-repo.git",
        language="Rust",
    )
    report_data = _make_report_dict(sample_metadata, baseline_size=2)
    captured: dict[str, object] = {}

    def _record_baseline(repos):
        captured["baseline_repos"] = [repo.name for repo in repos]
        return {}

    monkeypatch.setattr(
        cli,
        "_portfolio_lang_freq_for_filtered_baseline",
        _record_baseline,
    )
    monkeypatch.setattr(
        cli,
        "_analyze_repos",
        lambda repos, **kwargs: [
            RepoAudit(
                metadata=repos[0],
                analyzer_results=[],
                overall_score=0.5,
                completeness_tier="functional",
            )
        ],
    )
    monkeypatch.setattr(cli, "_write_report_outputs", lambda *a, **k: {
        "json_path": tmp_path / "audit-report.json",
        "md_path": tmp_path / "audit.md",
        "excel_path": tmp_path / "audit.xlsx",
        "pcc_path": tmp_path / "audit-pcc.json",
        "raw_path": tmp_path / "raw.json",
        "warehouse_path": tmp_path / "warehouse.db",
        "badge_info": "",
        "notion_info": "",
        "readme_info": "",
        "suggestions_info": "",
        "html_info": "",
        "pdf_info": "",
        "review_pack_info": "",
        "cache_info": "",
    })
    monkeypatch.setattr(cli, "_print_output_summary", lambda *a, **k: None)
    monkeypatch.setattr(cli, "_apply_requested_reconciliation", lambda *a, **k: None)

    cli._run_targeted_audit(
        args,
        cli.GitHubClient(token=None, cache=None),
        tmp_path / "output",
        all_repos=[sample_metadata, other_repo],
        errors=[],
        custom_weights=None,
        scoring_profile_name="baseline",
        existing_report_path=tmp_path / "audit-report-testuser-2026-03-29.json",
        existing_report_data=report_data,
    )

    assert captured["baseline_repos"] == ["test-repo", "other-repo"]


def test_incremental_audit_delegates_changed_repos_to_targeted_path(monkeypatch, tmp_path, sample_metadata):
    args = _make_args(username="testuser")
    report_path = tmp_path / "audit-report-testuser-2026-03-29.json"
    report_path.write_text("{}")
    changed_repo = replace(
        sample_metadata,
        name="changed-repo",
        full_name="testuser/changed-repo",
        html_url="https://github.com/testuser/changed-repo",
        clone_url="https://github.com/testuser/changed-repo.git",
    )
    report_data = _make_report_dict(sample_metadata, baseline_size=2)
    report_data["audits"][0]["metadata"]["name"] = changed_repo.name
    captured: dict[str, object] = {}

    monkeypatch.setattr(cli, "_load_latest_report", lambda _output_dir: (report_path, report_data))
    monkeypatch.setattr(
        "src.history.load_fingerprints",
        lambda *_args, **_kwargs: {
            changed_repo.name: {"pushed_at": "2026-03-19T00:00:00+00:00"},
            sample_metadata.name: {"pushed_at": sample_metadata.pushed_at.isoformat()},
        },
    )
    monkeypatch.setattr(cli, "_run_targeted_audit", lambda *a, **k: captured.update({"repos": a[0].repos, **k}))

    cli._run_incremental_audit(
        args,
        cli.GitHubClient(token=None, cache=None),
        tmp_path / "output",
        all_repos=[changed_repo, sample_metadata],
        errors=[],
        custom_weights=None,
        scoring_profile_name="baseline",
    )

    assert captured["repos"] == [changed_repo.name]
    assert captured["existing_report_data"]["baseline_context"]["portfolio_baseline_size"] == 2


def test_targeted_audit_blocks_without_baseline_context(monkeypatch, tmp_path, sample_metadata):
    args = _make_args(username="testuser", repos=["test-repo"])
    report_data = _make_report_dict(sample_metadata)
    report_data.pop("baseline_context", None)
    report_data.pop("baseline_signature", None)
    called = {"analyze": False}

    monkeypatch.setattr(cli, "_analyze_repos", lambda *a, **k: called.update({"analyze": True}) or [])

    cli._run_targeted_audit(
        args,
        cli.GitHubClient(token=None, cache=None),
        tmp_path / "output",
        all_repos=[sample_metadata],
        errors=[],
        custom_weights=None,
        scoring_profile_name="baseline",
        existing_report_data=report_data,
    )

    assert called["analyze"] is False


def test_targeted_audit_blocks_on_incompatible_baseline_context(monkeypatch, tmp_path, sample_metadata):
    args = _make_args(username="testuser", repos=["test-repo"], skip_forks=True)
    report_data = _make_report_dict(sample_metadata, skip_forks=False)
    called = {"analyze": False}

    monkeypatch.setattr(cli, "_analyze_repos", lambda *a, **k: called.update({"analyze": True}) or [])

    cli._run_targeted_audit(
        args,
        cli.GitHubClient(token=None, cache=None),
        tmp_path / "output",
        all_repos=[sample_metadata],
        errors=[],
        custom_weights=None,
        scoring_profile_name="baseline",
        existing_report_data=report_data,
    )

    assert called["analyze"] is False


def test_report_from_dict_keeps_legacy_reports_readable(sample_metadata):
    report_data = _make_report_dict(sample_metadata)
    report_data.pop("baseline_context", None)
    report_data.pop("baseline_signature", None)

    report = cli._report_from_dict(report_data)

    assert report.baseline_context == {}
    assert report.baseline_signature == ""


def test_report_from_dict_preserves_action_sync_packet_outcome_tuning_and_automation_layers(sample_metadata):
    report_data = _make_report_dict(sample_metadata)
    report_data["action_sync_packets"] = [
        {
            "campaign_type": "security-review",
            "summary": "Preview Security Review next.",
            "execution_state": "preview-next",
        }
    ]
    report_data["apply_readiness_summary"] = {"summary": "Preview Security Review next."}
    report_data["next_apply_candidate"] = {
        "summary": "Preview Security Review next.",
        "preview_command": "audit testuser --campaign security-review --writeback-target all",
    }
    report_data["action_sync_outcomes"] = [
        {
            "campaign_type": "security-review",
            "summary": "Security Review was applied recently; monitor it now before treating it as stable.",
            "monitoring_state": "monitor-now",
        }
    ]
    report_data["campaign_outcomes_summary"] = {
        "summary": "Security Review was applied recently; monitor it now before treating it as stable."
    }
    report_data["next_monitoring_step"] = {
        "summary": "Monitor Security Review for at least 2 post-apply runs before treating it as stable."
    }
    report_data["action_sync_tuning"] = [
        {
            "campaign_type": "security-review",
            "summary": "Security Review is proven.",
            "tuning_status": "proven",
            "recommendation_bias": "promote",
        }
    ]
    report_data["campaign_tuning_summary"] = {
        "summary": "Security Review should win ties because recent outcomes are proven."
    }
    report_data["next_tuned_campaign"] = {
        "summary": "Security Review should win ties inside the preview-ready group because recent outcome history is proven."
    }
    report_data["action_sync_automation"] = [
        {
            "campaign_type": "security-review",
            "summary": "Security Review is preview-safe: use a preview-only step first.",
            "automation_posture": "preview-safe",
            "recommended_command": "audit testuser --campaign security-review --writeback-target all",
        }
    ]
    report_data["automation_guidance_summary"] = {
        "summary": "Preview Security Review next; that is the strongest safe automation step right now."
    }
    report_data["next_safe_automation_step"] = {
        "summary": "Preview Security Review next; that is the strongest safe automation step right now.",
        "recommended_command": "audit testuser --campaign security-review --writeback-target all",
    }

    report = cli._report_from_dict(report_data)

    assert report.action_sync_packets[0]["campaign_type"] == "security-review"
    assert report.apply_readiness_summary["summary"] == "Preview Security Review next."
    assert report.next_apply_candidate["preview_command"].endswith("--writeback-target all")
    assert report.action_sync_outcomes[0]["monitoring_state"] == "monitor-now"
    assert report.campaign_outcomes_summary["summary"].startswith("Security Review was applied recently")
    assert report.next_monitoring_step["summary"].startswith("Monitor Security Review")
    assert report.action_sync_tuning[0]["tuning_status"] == "proven"
    assert report.campaign_tuning_summary["summary"].startswith("Security Review should win ties")
    assert report.next_tuned_campaign["summary"].startswith("Security Review should win ties")
    assert report.action_sync_automation[0]["automation_posture"] == "preview-safe"
    assert report.automation_guidance_summary["summary"].startswith("Preview Security Review next")
    assert report.next_safe_automation_step["recommended_command"].endswith("--writeback-target all")


def test_regenerate_outputs_from_latest_report_uses_existing_json(monkeypatch, tmp_path, sample_metadata):
    args = _make_args(username="testuser")
    report_path = tmp_path / "audit-report-testuser-2026-03-29.json"
    report_path.write_text("{}")
    report_data = _make_report_dict(sample_metadata)

    captured: dict[str, object] = {}

    def _record_write(report, passed_args, output_dir, **kwargs):
        captured.update(
            {
                "report": report,
                "args": passed_args,
                "output_dir": output_dir,
                **kwargs,
            }
        )
        return {
            "json_path": report_path,
            "md_path": output_dir / "audit.md",
            "excel_path": output_dir / "audit.xlsx",
            "pcc_path": output_dir / "audit-pcc.json",
            "raw_path": output_dir / "raw.json",
            "warehouse_path": output_dir / "warehouse.db",
            "badge_info": "",
            "notion_info": "",
            "readme_info": "",
            "suggestions_info": "",
            "html_info": "",
            "review_pack_info": "",
            "cache_info": "",
        }

    monkeypatch.setattr(cli, "_write_report_outputs", _record_write)

    cli._regenerate_outputs_from_latest_report(
        args,
        tmp_path / "output",
        client=None,
        existing_report_path=report_path,
        existing_report_data=report_data,
    )

    assert captured["write_json"] is False
    assert captured["archive"] is False
    assert captured["save_fingerprint_data"] is False
    assert captured["json_path"] == report_path
    assert captured["report"].scoring_profile == "baseline"
    assert captured["client"] is None


def test_write_report_outputs_forwards_analyst_view_args(monkeypatch, tmp_path, sample_metadata):
    args = _make_args(
        username="testuser",
        html=True,
        review_pack=True,
        portfolio_profile="shipping",
        collection="showcase",
    )
    report = cli._report_from_dict(_make_report_dict(sample_metadata))
    json_path = tmp_path / "audit-report-testuser-2026-03-29.json"

    monkeypatch.setattr(cli, "write_json_report", lambda *_: json_path)
    monkeypatch.setattr(cli, "write_markdown_report", lambda *a, **k: tmp_path / "audit.md")
    monkeypatch.setattr(cli, "write_pcc_export", lambda *a, **k: tmp_path / "audit-pcc.json")
    monkeypatch.setattr(cli, "write_raw_metadata", lambda *a, **k: tmp_path / "raw.json")
    monkeypatch.setattr("src.history.load_trend_data", lambda: [])
    monkeypatch.setattr("src.history.load_repo_score_history", lambda: {})
    monkeypatch.setattr("src.history.find_previous", lambda *_: None)
    monkeypatch.setattr("src.history.save_fingerprints", lambda *_: None)
    monkeypatch.setattr("src.history.archive_report", lambda *_: None)
    monkeypatch.setattr("src.warehouse.write_warehouse_snapshot", lambda *a, **k: tmp_path / "warehouse.db")
    excel_calls: dict[str, object] = {}

    def _record_excel(*_args, **kwargs):
        excel_calls.update(kwargs)
        return tmp_path / "audit.xlsx"

    monkeypatch.setattr("src.excel_export.export_excel", _record_excel)

    html_calls: dict[str, object] = {}
    review_pack_calls: dict[str, object] = {}

    def _record_html(*_args, **kwargs):
        html_calls.update(kwargs)
        return {"html_path": tmp_path / "dashboard.html"}

    def _record_review_pack(*_args, **kwargs):
        review_pack_calls.update(kwargs)
        return {"review_pack_path": tmp_path / "review-pack.md"}

    monkeypatch.setattr("src.web_export.export_html_dashboard", _record_html)
    monkeypatch.setattr("src.review_pack.export_review_pack", _record_review_pack)

    outputs = cli._write_report_outputs(report, args, tmp_path)

    assert html_calls["portfolio_profile"] == "shipping"
    assert html_calls["collection"] == "showcase"
    assert excel_calls["excel_mode"] == "standard"
    assert review_pack_calls["portfolio_profile"] == "shipping"
    assert review_pack_calls["collection"] == "showcase"
    assert outputs["review_pack_info"]


def test_analyze_repos_forwards_security_flags_to_scorer(monkeypatch, sample_metadata):
    args = _make_args(scorecard=True, security_offline=True)
    captured: list[dict[str, object]] = []

    class _CloneContext:
        def __enter__(self):
            return {sample_metadata.name: Path("/tmp/repo")}

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(cli, "clone_workspace", lambda *a, **k: _CloneContext())
    monkeypatch.setattr(cli, "create_progress", lambda: None)
    monkeypatch.setattr(cli, "run_all_analyzers", lambda *a, **k: [])

    def _record_score_repo(*a, **kwargs):
        captured.append(kwargs)
        return RepoAudit(
            metadata=sample_metadata,
            analyzer_results=[],
            overall_score=0.5,
            completeness_tier="functional",
        )

    monkeypatch.setattr(cli, "score_repo", _record_score_repo)

    cli._analyze_repos(
        [sample_metadata],
        args=args,
        client=cli.GitHubClient(token=None, cache=None),
        portfolio_lang_freq={},
        custom_weights=None,
    )

    assert captured[0]["scorecard_enabled"] is True
    assert captured[0]["security_offline"] is True
