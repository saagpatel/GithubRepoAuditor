from __future__ import annotations

import sys
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from github_repo_auditor import cli


def _write_overlay(path: Path) -> Path:
    path.write_text(
        "schema: reckoning-verdicts/1\nupdated_at: null\nfamilies: {}\n",
        encoding="utf-8",
    )
    return path


def _main_args(monkeypatch, output_dir: Path, *extra: str) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["audit", "run", "fixture-user", "--output-dir", str(output_dir), *extra],
    )
    monkeypatch.setattr(
        "github_repo_auditor.config.inspect_config",
        lambda _path: SimpleNamespace(data={}),
    )


@pytest.mark.parametrize("truth", [None, "not JSON", {}, {"projects": [{}]}])
def test_reckoning_overlay_truth_failure_precedes_audit(
    tmp_path: Path, monkeypatch, truth
) -> None:
    overlay_path = _write_overlay(tmp_path / "overlay.yaml")
    audit_called = False

    def run_audit(*_args):
        nonlocal audit_called
        audit_called = True

    monkeypatch.setattr(cli, "_run_main_audit_cycle", run_audit)
    output_dir = tmp_path / "output"
    if truth is not None:
        output_dir.mkdir()
        (output_dir / "portfolio-truth-latest.json").write_text(
            truth if isinstance(truth, str) else json.dumps(truth)
        )
    _main_args(
        monkeypatch,
        output_dir,
        "--reckoning-overlay",
        str(overlay_path),
        "--preflight-mode",
        "off",
    )

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 2
    assert not audit_called


def test_invalid_environment_overlay_fails_before_audit(tmp_path, monkeypatch) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text("schema: wrong\nfamilies: {}\n")
    monkeypatch.setenv("GHRA_RECKONING_OVERLAY", str(path))
    monkeypatch.setattr(
        cli, "_run_main_audit_cycle", lambda *_args: pytest.fail("audit must not start")
    )
    _main_args(monkeypatch, tmp_path, "--preflight-mode", "off")
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2


def test_cli_explicit_overlay_wins_and_loaded_object_reaches_audit(
    tmp_path: Path, monkeypatch
) -> None:
    from github_repo_auditor import excel_export_truth_helpers

    explicit_path = tmp_path / "explicit.yaml"
    env_path = tmp_path / "environment.yaml"
    marker = object()
    loaded_paths: list[Path | None] = []
    truth_dirs: list[Path] = []
    audit_args = []

    def load_overlay(path):
        loaded_paths.append(path)
        return marker

    monkeypatch.setattr(cli, "load_reckoning_overlay", load_overlay)
    monkeypatch.setattr(
        excel_export_truth_helpers,
        "load_reckoning_truth",
        lambda truth_dir: truth_dirs.append(truth_dir),
    )
    monkeypatch.setattr(
        cli, "_run_main_audit_cycle", lambda args, _config: audit_args.append(args)
    )
    monkeypatch.setenv("GHRA_RECKONING_OVERLAY", str(env_path))
    _main_args(
        monkeypatch,
        tmp_path / "output",
        "--reckoning-overlay",
        str(explicit_path),
        "--preflight-mode",
        "off",
    )

    cli.main()

    assert loaded_paths == [explicit_path]
    assert truth_dirs == [tmp_path / "output"]
    assert len(audit_args) == 1
    assert audit_args[0].reckoning_overlay is marker


def test_shared_artifact_refresh_passes_overlay_to_workbook(
    monkeypatch, tmp_path: Path
) -> None:
    from github_repo_auditor import report_shared_artifacts as shared

    captured = {}
    report = SimpleNamespace(
        username="fixture-user",
        generated_at=datetime(2026, 10, 12, tzinfo=timezone.utc),
        operator_summary={},
        operator_queue=[],
        to_dict=lambda: {},
    )
    args = SimpleNamespace(
        approval_view="all",
        portfolio_profile="default",
        collection=None,
        excel_mode="standard",
        reckoning_overlay=object(),
    )
    json_path = tmp_path / "report.json"
    monkeypatch.setattr(
        shared,
        "write_approval_center_artifacts",
        lambda *_a, **_k: (Path("approval.json"), Path("approval.md"), {}),
    )
    monkeypatch.setattr(shared, "write_json_report", lambda *_a, **_k: json_path)
    monkeypatch.setattr(shared, "write_markdown_report", lambda *_a, **_k: None)
    monkeypatch.setattr(shared, "write_pcc_export", lambda *_a, **_k: None)
    monkeypatch.setattr(shared, "write_raw_metadata", lambda *_a, **_k: None)
    monkeypatch.setattr(shared, "load_trend_data", lambda: [])
    monkeypatch.setattr(shared, "load_repo_score_history", lambda: {})
    monkeypatch.setattr(
        shared, "export_excel", lambda *_a, **kwargs: captured.update(kwargs)
    )
    monkeypatch.setattr(shared, "export_review_pack", lambda *_a, **_k: None)
    monkeypatch.setattr(shared, "export_html_dashboard", lambda *_a, **_k: None)
    monkeypatch.setattr(
        shared, "report_artifact_datetime", lambda *_a: report.generated_at
    )
    monkeypatch.setattr(
        shared,
        "write_control_center_artifacts",
        lambda *_a, **_k: (
            Path("control.json"),
            Path("control.md"),
            Path("weekly.json"),
            Path("weekly.md"),
            {},
        ),
    )
    monkeypatch.setattr(shared, "write_warehouse_snapshot", lambda *_a, **_k: None)

    shared.refresh_shared_artifacts_from_report(report, tmp_path, args)

    assert captured["reckoning_overlay"] is args.reckoning_overlay
