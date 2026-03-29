from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from src import cli
from src.models import AuditReport, RepoAudit


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
        "scoring_profile": None,
        "portfolio_profile": "default",
        "collection": None,
        "review_pack": False,
        "scorecard": False,
        "security_offline": False,
        "campaign": None,
        "campaign_rollback": None,
        "writeback_target": None,
        "writeback_apply": False,
        "max_actions": 20,
        "auto_archive": False,
        "narrative": False,
        "pdf": False,
        "config": None,
        "governance_approve": None,
        "governance_apply": None,
        "governance_scope": "all",
        "watch": False,
        "watch_strategy": "adaptive",
        "watch_interval": 3600,
        "review_materiality": "standard",
        "review_sync": None,
        "review_from_latest": False,
        "dry_run": False,
        "summary": False,
        "create_issues": False,
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


def _make_report_dict(sample_metadata) -> dict:
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
        scoring_profile="baseline",
        run_mode="full",
        portfolio_baseline_size=1,
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


def test_main_rejects_watch_with_campaign_writeback(monkeypatch):
    args = _make_args(
        watch=True,
        campaign="promotion-push",
        writeback_target="github",
    )

    monkeypatch.setattr(cli, "build_parser", lambda: FakeParser(args))

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 2


def test_main_forwards_scoring_profile_to_targeted_audit(monkeypatch, sample_metadata):
    args = _make_args(
        repos=["test-repo"],
        scoring_profile="focus",
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


def test_main_forwards_scoring_profile_to_incremental_audit(monkeypatch, sample_metadata):
    args = _make_args(
        incremental=True,
        scoring_profile="focus",
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


def test_incremental_noop_regenerates_from_latest_report(monkeypatch, tmp_path, sample_metadata):
    args = _make_args(username="testuser")
    report_path = tmp_path / "audit-report-testuser-2026-03-29.json"
    report_path.write_text("{}")
    report_data = _make_report_dict(sample_metadata)
    report_data["audits"][0]["metadata"]["name"] = sample_metadata.name

    monkeypatch.setattr(cli, "_load_latest_report", lambda _output_dir: (report_path, report_data))
    monkeypatch.setattr(
        "src.history.load_fingerprints",
        lambda: {sample_metadata.name: {"pushed_at": sample_metadata.pushed_at.isoformat()}},
    )

    calls: list[dict[str, object]] = []

    def _record_regen(args, output_dir, *, client, existing_report_path, existing_report_data):
        calls.append(
            {
                "args": args,
                "output_dir": output_dir,
                "client": client,
                "existing_report_path": existing_report_path,
                "existing_report_data": existing_report_data,
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


def test_main_review_from_latest_regenerates_outputs(monkeypatch, tmp_path, sample_metadata):
    args = _make_args(username="testuser", review_from_latest=True)
    report_path = tmp_path / "audit-report-testuser-2026-03-29.json"
    report_path.write_text("{}")
    report_data = _make_report_dict(sample_metadata)
    captured: dict[str, object] = {}

    monkeypatch.setattr(cli, "build_parser", lambda: FakeParser(args))
    monkeypatch.setattr(cli, "_load_latest_report", lambda _output_dir: (report_path, report_data))
    monkeypatch.setattr(
        cli,
        "_regenerate_outputs_from_latest_report",
        lambda *a, **k: captured.update({"args": a, "kwargs": k}),
    )

    cli.main()

    assert captured["kwargs"]["existing_report_path"] == report_path


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
    monkeypatch.setattr("src.excel_export.export_excel", lambda *a, **k: tmp_path / "audit.xlsx")

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


def test_dry_run_exits_before_analysis_and_writes_no_files(monkeypatch, tmp_path, sample_metadata):
    """--dry-run should print a summary and return without creating any output files."""
    args = _make_args(username="testuser", dry_run=True, output_dir=str(tmp_path))

    monkeypatch.setattr(cli, "build_parser", lambda: FakeParser(args))
    monkeypatch.setattr(cli, "_fetch_repo_metadata", lambda *_: ([sample_metadata], []))

    # Ensure _analyze_repos is never called
    analyze_called = {"called": False}

    def _fail_if_called(*a, **k):
        analyze_called["called"] = True
        return []

    monkeypatch.setattr(cli, "_analyze_repos", _fail_if_called)

    # Stub out the rich table printer so output dir stays clean
    monkeypatch.setattr(cli, "_print_dry_run_summary", lambda repos, args: None)

    cli.main()

    assert not analyze_called["called"], "_analyze_repos should not be called in dry-run mode"
    # No output files should have been written
    output_files = list(tmp_path.iterdir())
    assert output_files == [], f"Unexpected output files: {output_files}"
