from __future__ import annotations

import json

from src.workbook_gate import run_workbook_gate


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
    assert result_json["automated_checks"]["status"] == "passed"
    assert result_json["manual_signoff"]["status"] == "pending"
    assert result_json["artifacts"]["gate_summary"].endswith("workbook-gate-summary.md")
