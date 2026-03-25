from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.models import AnalyzerResult, AuditReport, RepoAudit, RepoMetadata
from src.reporter import write_json_report, write_markdown_report, write_pcc_export


def _make_report() -> AuditReport:
    meta = RepoMetadata(
        name="test-repo", full_name="user/test-repo", description="A test",
        language="Python", languages={"Python": 5000}, private=False, fork=False,
        archived=False, created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        pushed_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
        default_branch="main", stars=3, forks=1, open_issues=0,
        size_kb=1024, html_url="https://github.com/user/test-repo",
        clone_url="", topics=["python"],
    )
    audit = RepoAudit(
        metadata=meta,
        analyzer_results=[
            AnalyzerResult("readme", 0.8, 1.0, ["Has README"]),
            AnalyzerResult("testing", 0.6, 1.0, ["5 test files"]),
        ],
        overall_score=0.7,
        completeness_tier="functional",
        interest_score=0.45,
        interest_tier="notable",
    )
    return AuditReport.from_audits("user", [audit], [], 1)


class TestJsonReport:
    def test_writes_valid_json(self, tmp_path):
        report = _make_report()
        path = write_json_report(report, tmp_path)
        data = json.loads(path.read_text())
        assert data["repos_audited"] == 1
        assert "audits" in data
        assert data["audits"][0]["interest_score"] == 0.45

    def test_filename_format(self, tmp_path):
        report = _make_report()
        path = write_json_report(report, tmp_path)
        assert path.name.startswith("audit-report-user-")
        assert path.suffix == ".json"


class TestMarkdownReport:
    def test_has_required_sections(self, tmp_path):
        report = _make_report()
        path = write_markdown_report(report, tmp_path)
        content = path.read_text()
        assert "## Summary" in content
        assert "## Functional" in content
        assert "<details>" in content
        assert "Interest" in content  # Interest column in tables

    def test_per_repo_details(self, tmp_path):
        report = _make_report()
        path = write_markdown_report(report, tmp_path)
        content = path.read_text()
        assert "test-repo" in content
        assert "https://github.com/user/test-repo" in content


class TestPccExport:
    def test_flat_array(self, tmp_path):
        report = _make_report()
        path = write_pcc_export(report, tmp_path)
        data = json.loads(path.read_text())
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "test-repo"
        assert data[0]["tier"] == "functional"
        assert data[0]["score"] == 0.7
