from __future__ import annotations

import json
from argparse import Namespace

from src.baseline_context import build_baseline_context
from src.config import inspect_config
from src.diagnostics import run_diagnostics


def _make_args(tmp_path, **overrides) -> Namespace:
    defaults = {
        "username": "testuser",
        "token": "ghp_test",
        "output_dir": str(tmp_path / "output"),
        "repos": None,
        "incremental": False,
        "notion": False,
        "notion_sync": False,
        "notion_registry": False,
        "excel_mode": "standard",
        "scorecard": False,
        "security_offline": False,
        "campaign": None,
        "writeback_target": None,
        "writeback_apply": False,
        "create_issues": False,
        "apply_metadata": False,
        "apply_readmes": False,
        "generate_manifest": False,
        "scoring_profile": None,
        "portfolio_profile": "default",
        "config": None,
        "doctor": False,
    }
    defaults.update(overrides)
    return Namespace(**defaults)


def test_clean_preflight_is_ok(tmp_path):
    args = _make_args(tmp_path)
    result = run_diagnostics(args, full=False)
    assert result.status == "ok"
    assert result.blocking_errors == 0
    assert result.warnings == 0


def test_malformed_config_is_error(tmp_path):
    config_path = tmp_path / "audit-config.yaml"
    config_path.write_text("html: [broken\n")
    args = _make_args(tmp_path, config=str(config_path))
    inspection = inspect_config(config_path)
    result = run_diagnostics(args, config_inspection=inspection, full=False)
    assert result.status == "error"
    assert any(check.category == "config" and check.status == "error" for check in result.checks)


def test_missing_optional_notion_setup_is_warning_in_doctor(tmp_path, monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    args = _make_args(tmp_path)
    result = run_diagnostics(args, full=True)
    assert any(check.category == "notion" and check.status == "warning" for check in result.checks)


def test_requested_notion_sync_without_token_or_config_is_error(tmp_path, monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    args = _make_args(tmp_path, notion=True, notion_sync=True)
    result = run_diagnostics(args, full=False)
    assert result.status == "error"
    assert any(check.category == "notion" and check.status == "error" for check in result.checks)


def test_template_mode_missing_asset_is_error(tmp_path, monkeypatch):
    monkeypatch.setattr("src.diagnostics.DEFAULT_TEMPLATE_PATH", tmp_path / "missing-template.xlsx")
    args = _make_args(tmp_path, excel_mode="template")
    result = run_diagnostics(args, full=False)
    assert any(check.category == "excel" and check.status == "error" for check in result.checks)


def test_targeted_run_without_baseline_is_error(tmp_path):
    args = _make_args(tmp_path, repos=["repo-a"])
    result = run_diagnostics(args, full=False)
    assert any(check.key == "latest-report" and check.status == "error" for check in result.checks)


def test_incremental_run_without_fingerprints_is_error(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "audit-report-testuser-2026-03-29.json").write_text("{}")
    args = _make_args(tmp_path, incremental=True)
    result = run_diagnostics(args, full=False)
    assert any(check.key == "fingerprints" and check.status == "error" for check in result.checks)


def test_scorecard_with_security_offline_warns(tmp_path):
    args = _make_args(tmp_path, scorecard=True, security_offline=True)
    result = run_diagnostics(args, full=False)
    assert any(check.key == "scorecard-offline" and check.status == "warning" for check in result.checks)


def test_targeted_run_with_legacy_report_without_baseline_context_is_error(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "audit-report-testuser-2026-03-29.json").write_text(json.dumps({"username": "testuser"}))

    args = _make_args(tmp_path, repos=["repo-a"])
    result = run_diagnostics(args, full=False)

    assert any(check.key == "baseline-context" and check.status == "error" for check in result.checks)


def test_incremental_run_with_mismatched_baseline_context_is_error(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    report_data = {
        "username": "testuser",
        "baseline_signature": "unused",
        "baseline_context": build_baseline_context(
            username="testuser",
            scoring_profile="default",
            skip_forks=False,
            skip_archived=False,
            scorecard=False,
            security_offline=False,
            portfolio_baseline_size=4,
        ),
    }
    (output_dir / "audit-report-testuser-2026-03-29.json").write_text(json.dumps(report_data))
    (output_dir / ".audit-fingerprints.json").write_text("{}")

    args = _make_args(tmp_path, incremental=True, skip_forks=True)
    result = run_diagnostics(args, full=False)

    assert any(check.key == "baseline-context" and check.status == "error" for check in result.checks)
