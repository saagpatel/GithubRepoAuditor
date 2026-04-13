from __future__ import annotations

from argparse import Namespace
from dataclasses import replace
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
        "triage_view": "all",
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
