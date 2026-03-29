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
        assert data["schema_version"] == "3.2"
        assert "lenses" in data
        assert "security_governance_preview" in data
        assert "campaign_summary" in data

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
        assert "### Decision Lenses" in content
        assert "### Security Overview" in content
        assert "## Functional" in content
        assert "<details>" in content
        assert "Interest" in content  # Interest column in tables

    def test_per_repo_details(self, tmp_path):
        report = _make_report()
        path = write_markdown_report(report, tmp_path)
        content = path.read_text()
        assert "test-repo" in content
        assert "https://github.com/user/test-repo" in content

    def test_includes_compare_summary_when_diff_passed(self, tmp_path):
        report = _make_report()
        diff_data = {
            "average_score_delta": 0.04,
            "lens_deltas": {"ship_readiness": 0.1},
            "repo_changes": [{"name": "test-repo", "delta": 0.1, "old_tier": "wip", "new_tier": "functional"}],
        }
        path = write_markdown_report(report, tmp_path, diff_data=diff_data)
        content = path.read_text()
        assert "Compare Summary" in content
        assert "ship_readiness" in content

    def test_includes_campaign_and_writeback_sections(self, tmp_path):
        report = _make_report()
        report.campaign_summary = {
            "campaign_type": "promotion-push",
            "label": "Promotion Push",
            "action_count": 1,
            "repo_count": 1,
        }
        report.writeback_preview = {
            "repos": [
                {
                    "repo": "test-repo",
                    "topics": ["ghra-call-promotion-push"],
                    "issue_title": "[Repo Auditor] Promotion Push",
                    "notion_action_count": 1,
                }
            ]
        }
        report.writeback_results = {
            "mode": "apply",
            "target": "github",
            "results": [
                {
                    "repo_full_name": "user/test-repo",
                    "target": "github-issue",
                    "status": "created",
                    "url": "https://github.com/user/test-repo/issues/1",
                }
            ],
        }
        path = write_markdown_report(report, tmp_path)
        content = path.read_text()
        assert "Campaign Summary" in content
        assert "Next Actions" in content
        assert "Writeback Results" in content


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
