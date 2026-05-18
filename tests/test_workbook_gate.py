from __future__ import annotations

import json

import pytest

from src.workbook_gate import format_gate_result, record_manual_signoff, run_workbook_gate


def test_workbook_gate_generates_artifacts_and_validates(tmp_path):
    result = run_workbook_gate(tmp_path)

    assert result["status"] == "ok"
    assert (tmp_path / "workbook-gate-report.json").is_file()
    assert (tmp_path / "workbook-gate-standard.xlsx").is_file()
    assert (tmp_path / "workbook-gate-template.xlsx").is_file()
    assert (tmp_path / "workbook-gate-checklist.md").is_file()
    assert (tmp_path / "workbook-gate-summary.md").is_file()

    checklist = (tmp_path / "workbook-gate-checklist.md").read_text()
    assert "desktop Excel" in checklist
    assert "repair prompt" in checklist
    assert "[ ]" in checklist

    result_json = json.loads((tmp_path / "workbook-gate-result.json").read_text())
    assert result_json["status"] == "ok"
    assert result_json["release_status"] == "pending_manual_signoff"
    assert result_json["automated_checks"]["status"] == "passed"
    assert result_json["manual_signoff"]["status"] == "pending"
    assert result_json["artifacts"]["gate_summary"].endswith("workbook-gate-summary.md")


def test_record_manual_signoff_marks_gate_ready_and_updates_artifacts(tmp_path):
    run_workbook_gate(tmp_path)

    result = record_manual_signoff(
        tmp_path,
        reviewer="Dana",
        outcome="passed",
        checks=[
            "excel-open-no-repair=passed",
            "visible-tabs-present=passed",
            "core-navigation-links-work=passed",
            "operator-story-consistent=passed",
            "repo-detail-selector-works=passed",
            "run-changes-readable=passed",
            "normal-zoom-readable=passed",
            "chart-placement-clean=passed",
            "filters-work=passed",
        ],
        notes="Opened cleanly in desktop Excel.",
    )

    assert result["release_status"] == "ready"
    assert result["manual_signoff"]["status"] == "passed"
    assert result["manual_signoff"]["reviewer"] == "Dana"
    assert len(result["manual_signoff_history"]) == 1
    checklist = (tmp_path / "workbook-gate-checklist.md").read_text()
    assert "[x]" in checklist
    assert "Dana" in checklist
    formatted = format_gate_result(result)
    assert "Release status: ready" in formatted
    assert "Manual signoff: passed" in formatted
    assert "Workbook release gate is ready." in formatted
    assert "complete the manual desktop Excel checklist" not in formatted


def test_record_manual_signoff_marks_gate_blocked_on_failure(tmp_path):
    run_workbook_gate(tmp_path)

    result = record_manual_signoff(
        tmp_path,
        reviewer="Dana",
        outcome="failed",
        checks=[
            "excel-open-no-repair=failed",
            "visible-tabs-present=passed",
            "core-navigation-links-work=passed",
            "operator-story-consistent=passed",
            "repo-detail-selector-works=passed",
            "run-changes-readable=passed",
            "normal-zoom-readable=passed",
            "chart-placement-clean=passed",
            "filters-work=passed",
        ],
    )

    assert result["release_status"] == "blocked"
    assert result["manual_signoff"]["status"] == "failed"
    assert result["manual_signoff"]["checks"][0]["status"] == "failed"


def test_record_manual_signoff_rejects_incomplete_check_payload(tmp_path):
    run_workbook_gate(tmp_path)

    with pytest.raises(ValueError, match="Missing manual signoff checks"):
        record_manual_signoff(
            tmp_path,
            reviewer="Dana",
            outcome="passed",
            checks=[
                "excel-open-no-repair=passed",
                "visible-tabs-present=passed",
            ],
        )
