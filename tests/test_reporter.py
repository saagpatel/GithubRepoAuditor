from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.models import AnalyzerResult, AuditReport, RepoAudit, RepoMetadata
from src.reporter import (
    _sanitize_for_json,
    write_json_report,
    write_markdown_report,
    write_pcc_export,
    write_raw_metadata,
)


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


class TestSanitizeForJson:
    def test_sanitize_for_json_strips_control_chars(self):
        data = {"name": "test\x00repo", "items": ["hello\x0bworld"], "nested": {"key": "val\x0cue"}}
        result = _sanitize_for_json(data)
        assert result["name"] == "testrepo"
        assert result["items"][0] == "helloworld"
        assert result["nested"]["key"] == "value"
        # Non-string types pass through
        assert _sanitize_for_json(42) == 42
        assert _sanitize_for_json(None) is None


class TestJsonReport:
    def test_writes_valid_json(self, tmp_path):
        report = _make_report()
        path = write_json_report(report, tmp_path)
        data = json.loads(path.read_text())
        assert data["repos_audited"] == 1
        assert "audits" in data
        assert data["audits"][0]["interest_score"] == 0.45
        assert data["schema_version"] == "3.7"
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
        report.managed_state_drift = [
            {
                "repo_full_name": "user/test-repo",
                "target": "github-issue",
                "drift_state": "managed-issue-edited",
            }
        ]
        report.rollback_preview = {"available": True, "item_count": 1, "fully_reversible_count": 1}
        path = write_markdown_report(report, tmp_path)
        content = path.read_text()
        assert "Campaign Summary" in content
        assert "Next Actions" in content
        assert "Writeback Results" in content
        assert "Managed State Drift" in content
        assert "Rollback Preview" in content

    def test_includes_preflight_diagnostics_when_present(self, tmp_path):
        report = _make_report()
        report.preflight_summary = {
            "status": "warning",
            "blocking_errors": 0,
            "warnings": 2,
            "checks": [
                {"category": "github-auth", "summary": "GitHub token is not configured."},
            ],
        }
        path = write_markdown_report(report, tmp_path)
        content = path.read_text()
        assert "Preflight Diagnostics" in content
        assert "GitHub token is not configured." in content

    def test_includes_operator_control_center_when_present(self, tmp_path):
        report = _make_report()
        report.operator_summary = {
            "headline": "A blocked setup item needs attention.",
            "counts": {"blocked": 1, "urgent": 1, "ready": 0, "deferred": 0},
            "watch_strategy": "adaptive",
            "next_recommended_run_mode": "full",
            "watch_decision_summary": "The next run should be full because the scheduled full refresh interval has been reached.",
            "what_changed": "Missing template asset — Template mode cannot load the workbook template.",
            "why_it_matters": "A trustworthy next step is blocked until this is cleared.",
            "what_to_do_next": "Restore the workbook template before exporting.",
            "trend_summary": "The operator picture is worsening: 1 new attention item appeared and the top blocker should be cleared first.",
            "follow_through_summary": "1 urgent item repeated in the recent window.",
            "accountability_summary": "The current top target is fresh and should be closed before taking on newly ready work.",
            "primary_target_reason": "This outranks the rest of the queue because a setup blocker stops the next trustworthy export path.",
            "primary_target_done_criteria": "Clear the failing prerequisite and rerun the relevant export command so the blocker exits the queue.",
            "closure_guidance": "Restore the workbook template, rerun the export, and confirm this blocker disappears on the next run.",
            "primary_target": {"title": "Missing template asset"},
        }
        report.operator_queue = [
            {
                "lane": "blocked",
                "repo": "",
                "title": "Missing template asset",
                "summary": "Template mode cannot load the workbook template.",
                "recommended_action": "Restore the workbook template before exporting.",
            }
        ]
        path = write_markdown_report(report, tmp_path)
        content = path.read_text()
        assert "Operator Control Center" in content
        assert "Missing template asset" in content
        assert "Next Recommended Run" in content
        assert "Watch Strategy" in content
        assert "What Changed" in content
        assert "What To Do Next" in content
        assert "Trend" in content
        assert "Follow-Through" in content
        assert "Accountability" in content
        assert "Primary Target" in content
        assert "Why This Is The Top Target" in content
        assert "What Counts As Done" in content
        assert "Closure Guidance" in content

    def test_includes_governance_operator_summary_when_present(self, tmp_path):
        report = _make_report()
        report.governance_summary = {
            "headline": "Governed controls need re-approval before the next manual apply step.",
            "status": "blocked",
            "needs_reapproval": True,
            "drift_count": 1,
            "applyable_count": 1,
            "applied_count": 0,
            "rollback_available_count": 1,
            "approval_age_days": 3,
            "top_actions": [
                {
                    "repo": "test-repo",
                    "title": "Enable CodeQL default setup",
                    "operator_state": "needs-reapproval",
                }
            ],
        }
        path = write_markdown_report(report, tmp_path)
        content = path.read_text()
        assert "Governance Operator State" in content
        assert "Needs Re-Approval: yes" in content
        assert "Enable CodeQL default setup [needs-reapproval]" in content


class TestRawMetadata:
    def test_writes_preflight_summary_when_present(self, tmp_path):
        report = _make_report()
        report.preflight_summary = {"status": "warning", "warnings": 1, "blocking_errors": 0}
        path = write_raw_metadata(report, tmp_path)
        data = json.loads(path.read_text())
        assert data["preflight_summary"]["status"] == "warning"

    def test_writes_governance_summary_when_present(self, tmp_path):
        report = _make_report()
        report.governance_summary = {"status": "ready", "headline": "Governed controls are ready for manual review."}
        path = write_raw_metadata(report, tmp_path)
        data = json.loads(path.read_text())
        assert data["governance_summary"]["status"] == "ready"


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
