from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from github_repo_auditor.cli import build_parser, build_subcommand_parser
from github_repo_auditor.excel_export import export_excel
from github_repo_auditor.excel_portfolio_sheet_helpers import RECKONING_HEADERS
from github_repo_auditor.excel_template import load_workbook_allowing_native_sparklines
from github_repo_auditor.excel_workbook_helpers import CORE_VISIBLE_SHEETS
from github_repo_auditor.reckoning_overlay import (
    ReckoningOverlayError,
    load_reckoning_overlay,
)
from github_repo_auditor.workbook_gate import _sample_report_data, run_workbook_gate


def _family(key: str, **changes: object) -> dict:
    return {
        "title": key,
        "members": [{"key": key}],
        "fate": "pending",
        "status": "proposed",
        **changes,
    }


def _write_overlay(path: Path, families: dict) -> Path:
    path.write_text(
        yaml.safe_dump({"schema": "reckoning-verdicts/1", "families": families})
    )
    return path


def test_absent_env_and_cli_path_selection(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("github_repo_auditor.cli._gh_auth_token", lambda: None)
    monkeypatch.delenv("GHRA_RECKONING_OVERLAY", raising=False)
    assert load_reckoning_overlay() is None
    env_path = _write_overlay(tmp_path / "env.yaml", {"env": _family("Env")})
    explicit = _write_overlay(
        tmp_path / "explicit.yaml",
        {"explicit": _family("Explicit", future={"preserved": True})},
    )
    monkeypatch.setenv("GHRA_RECKONING_OVERLAY", str(env_path))
    assert "env" in load_reckoning_overlay().families
    overlay = load_reckoning_overlay(explicit)
    assert overlay.families["explicit"]["future"] == {"preserved": True}
    assert (
        build_parser()
        .parse_args(["fixture-owner", "--reckoning-overlay", str(explicit)])
        .reckoning_overlay
        == explicit
    )
    assert (
        build_subcommand_parser()
        .parse_args(["run", "fixture-owner", "--reckoning-overlay", str(explicit)])
        .reckoning_overlay
        == explicit
    )


def test_matching_precedence_and_archive_path(tmp_path) -> None:
    overlay = load_reckoning_overlay(
        _write_overlay(
            tmp_path / "private.yaml",
            {
                "by-path": _family(
                    "Local",
                    members=[{"key": "Local", "local_paths": ["_archive/Local"]}],
                ),
                "by-name": _family("fixture-owner/repo"),
                "by-id": _family(
                    "fixture-owner/renamed",
                    members=[{"key": "fixture-owner/renamed", "github_id": 17}],
                ),
            },
        )
    )
    original = copy.deepcopy(overlay.data)
    arguments = {
        "github_id": 17,
        "repo_full_name": "FIXTURE-OWNER/REPO",
        "local_path": "_archive/Local",
    }
    assert overlay.lookup(**arguments)[0] == "by-id"
    arguments["github_id"] = 18
    assert overlay.lookup(**arguments)[0] == "by-name"
    arguments["repo_full_name"] = ""
    assert overlay.lookup(**arguments)[0] == "by-path"
    assert (
        overlay.lookup(
            local_path=str(tmp_path / "_archive/Local"), workspace_root=tmp_path
        )[0]
        == "by-path"
    )
    assert overlay.lookup(local_path="Other") is None
    assert overlay.data == original


def test_validation_lists_all_schema_rule_problems(tmp_path) -> None:
    path = _write_overlay(
        tmp_path / "bad.yaml",
        {
            "first": _family(
                "Duplicate",
                fate="assimilate",
                assimilate_into="missing",
                tags=["reborn-seed"],
                status="approved",
            ),
            "second": _family("Duplicate"),
        },
    )
    with pytest.raises(ReckoningOverlayError) as error:
        load_reckoning_overlay(path)
    message = str(error.value)
    assert "assimilate_into" in message
    assert "seed_brief" in message
    assert "also appears" in message


@pytest.mark.parametrize(
    "contents",
    [
        "schema: wrong\nfamilies: {}",
        "[]",
        "families: [",
        "schema: reckoning-verdicts/1\nfamilies: {}\nfamilies: {}",
        "schema: reckoning-verdicts/1\nfamilies: {bad: {fate: [], status: [], members: [3]}}",
    ],
)
def test_invalid_overlay_is_never_silently_skipped(tmp_path, contents) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text(contents)
    with pytest.raises(ReckoningOverlayError):
        load_reckoning_overlay(path)
    with pytest.raises(ReckoningOverlayError, match="Cannot read"):
        load_reckoning_overlay(tmp_path / "missing.yaml")


@pytest.mark.parametrize(
    "field,value",
    [
        ("evidence", []),
        ("evidence", False),
        ("github", []),
        ("github", False),
        ("decided_at", {}),
        ("decided_at", "not-a-date"),
    ],
)
def test_invalid_optional_fields_are_not_silently_defaulted(
    tmp_path, field, value
) -> None:
    path = _write_overlay(
        tmp_path / "invalid.yaml", {"local": _family("Local", **{field: value})}
    )
    with pytest.raises(ReckoningOverlayError, match=field):
        load_reckoning_overlay(path)


@pytest.mark.parametrize("mode", ["standard", "template"])
def test_workbook_uses_full_truth_without_mutating_inputs(
    tmp_path, monkeypatch, mode
) -> None:
    monkeypatch.delenv("GHRA_RECKONING_OVERLAY", raising=False)
    report = tmp_path / "report.json"
    report.write_text(json.dumps(_sample_report_data()))
    overlay_path = _write_overlay(
        tmp_path / "private.yaml",
        {
            "local": _family(
                "_archive/LocalOnly",
                fate="archive",
                title="=Private text",
                tags=["custom-tag"],
                evidence={
                    "dossier": "dossiers/local.md",
                    "seed_brief": "seeds/local.md",
                },
                github={"visibility_after": "private"},
                wave=2,
                decided_at="2026-10-11T00:00:00Z",
            ),
        },
    )
    truth_path = tmp_path / "portfolio-truth-latest.json"
    truth_path.write_text(
        json.dumps(
            {
                "projects": [
                    {
                        "identity": {
                            "display_name": "LocalOnly",
                            "path": "_archive/LocalOnly",
                        },
                        "derived": {
                            "attention_state": "archived",
                            "last_meaningful_activity_at": "2026-01-01T00:00:00Z",
                        },
                    },
                    {
                        "identity": {
                            "display_name": "Unassigned",
                            "path": "Unassigned",
                        },
                        "derived": {},
                    },
                ]
            }
        )
    )
    before = {path: path.read_bytes() for path in (report, overlay_path, truth_path)}
    absent_path = export_excel(report, tmp_path / "absent.xlsx", excel_mode=mode)
    absent = load_workbook_allowing_native_sparklines(absent_path)
    assert "Reckoning" not in absent.sheetnames
    assert {
        ws.title for ws in absent.worksheets if ws.sheet_state == "visible"
    } == CORE_VISIBLE_SHEETS
    # Environment selection exercises the normal runtime entry point too.
    monkeypatch.setenv("GHRA_RECKONING_OVERLAY", str(overlay_path))
    present_path = export_excel(report, tmp_path / "present.xlsx", excel_mode=mode)
    present = load_workbook_allowing_native_sparklines(present_path)
    assert set(present.sheetnames) == set(absent.sheetnames) | {"Reckoning"}
    sheet = present["Reckoning"]
    assert sheet.sheet_state == "visible"
    assert [cell.value for cell in sheet[5]] == RECKONING_HEADERS
    assert [cell.value for cell in sheet[6]] == [
        "local",
        "=Private text",
        None,
        "_archive/LocalOnly",
        "archive",
        None,
        "custom-tag",
        None,
        "proposed",
        None,
        "dossiers/local.md",
        "seeds/local.md",
        "private",
        2,
        "2026-10-11T00:00:00Z",
        "archived",
        "2026-01-01T00:00:00Z",
    ]
    assert sheet["B6"].data_type == "s"
    assert sheet["B7"].value == "Unassigned"
    assert sheet["A7"].value is None and sheet["E7"].value is None
    assert sheet.max_row == 7
    for path, content in before.items():
        assert path.read_bytes() == content
    assert list(tmp_path.glob("*verdict*")) == []
    absent.close()
    present.close()


def test_requested_overlay_requires_saved_truth_before_writing_workbook(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.delenv("GHRA_RECKONING_OVERLAY", raising=False)
    report = tmp_path / "report.json"
    report.write_text(json.dumps(_sample_report_data()))
    overlay_path = _write_overlay(
        tmp_path / "private.yaml", {"local": _family("Local")}
    )
    output = tmp_path / "workbook.xlsx"
    with pytest.raises(ValueError, match="portfolio-truth-latest.json"):
        export_excel(
            report, output, excel_mode="template", reckoning_overlay=overlay_path
        )
    assert not output.exists()


def test_workbook_gate_with_synthetic_overlay(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("GHRA_RECKONING_OVERLAY", raising=False)
    result = run_workbook_gate(tmp_path, synthetic_reckoning_overlay=True)
    assert result["status"] == "ok"
    section = result["automated_checks"]["sections"][-1]
    assert section["name"] == "reckoning"
    assert section["status"] == "passed"
