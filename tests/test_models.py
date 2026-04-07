from __future__ import annotations

from datetime import datetime, timezone

from src.models import AnalyzerResult, AuditReport, RepoAudit, RepoMetadata


class TestRepoMetadata:
    def test_from_api_response(self):
        data = {
            "name": "my-repo",
            "full_name": "user/my-repo",
            "description": "A repo",
            "language": "Python",
            "private": False,
            "fork": False,
            "archived": False,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2026-03-01T00:00:00Z",
            "pushed_at": "2026-03-20T00:00:00Z",
            "default_branch": "main",
            "stargazers_count": 5,
            "forks_count": 1,
            "open_issues_count": 2,
            "size": 1024,
            "html_url": "https://github.com/user/my-repo",
            "clone_url": "https://github.com/user/my-repo.git",
            "topics": ["python"],
        }
        meta = RepoMetadata.from_api_response(data, languages={"Python": 5000})
        assert meta.name == "my-repo"
        assert meta.stars == 5
        assert meta.languages == {"Python": 5000}
        assert meta.pushed_at.year == 2026

    def test_to_dict_serializes_datetimes(self):
        meta = RepoMetadata(
            name="test", full_name="user/test", description=None,
            language="Python", languages={}, private=False, fork=False,
            archived=False,
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            pushed_at=None,
            default_branch="main", stars=0, forks=0, open_issues=0,
            size_kb=0, html_url="", clone_url="", topics=[],
        )
        d = meta.to_dict()
        assert isinstance(d["created_at"], str)
        assert d["pushed_at"] is None

    def test_nullable_pushed_at(self):
        data = {
            "name": "empty",
            "full_name": "user/empty",
            "description": None,
            "language": None,
            "private": False,
            "fork": False,
            "archived": False,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "pushed_at": None,
            "default_branch": "main",
            "stargazers_count": 0,
            "forks_count": 0,
            "open_issues_count": 0,
            "size": 0,
            "html_url": "",
            "clone_url": "",
        }
        meta = RepoMetadata.from_api_response(data)
        assert meta.pushed_at is None


class TestAnalyzerResult:
    def test_to_dict(self):
        r = AnalyzerResult(
            dimension="readme", score=0.8, max_score=1.0,
            findings=["Has README"], details={"exists": True},
        )
        d = r.to_dict()
        assert d["score"] == 0.8
        assert d["findings"] == ["Has README"]


class TestAuditReport:
    def test_from_audits(self, sample_metadata):
        audit = RepoAudit(
            metadata=sample_metadata,
            analyzer_results=[
                AnalyzerResult("readme", 0.8, 1.0, []),
                AnalyzerResult("activity", 0.6, 1.0, []),
            ],
            overall_score=0.7,
                completeness_tier="functional",
                flags=[],
            )
        report = AuditReport.from_audits(
            "user",
            [audit],
            [],
            1,
            scoring_profile="custom",
            run_mode="targeted",
            portfolio_baseline_size=7,
            baseline_signature="sig-123",
            baseline_context={"skip_forks": False},
        )
        assert report.repos_audited == 1
        assert report.average_score == 0.7
        assert "test-repo" in report.highest_scored
        assert report.language_distribution == {"Python": 1}
        assert report.scoring_profile == "custom"
        assert report.run_mode == "targeted"
        assert report.portfolio_baseline_size == 7
        assert report.baseline_signature == "sig-123"
        assert report.baseline_context == {"skip_forks": False}
        assert report.schema_version == "3.7"
        assert "ship_readiness" in report.lenses
        assert isinstance(report.security_governance_preview, list)
        assert "showcase" in report.collections
        assert "default" in report.profiles
        assert report.campaign_summary == {}
        assert report.managed_state_drift == []
        assert report.governance_summary == {}
        assert report.operator_summary == {}
        assert report.review_targets == []

    def test_to_dict_includes_reconciliation(self, sample_metadata):
        audit = RepoAudit(
            metadata=sample_metadata,
            analyzer_results=[],
            overall_score=0.5,
            completeness_tier="wip",
        )
        report = AuditReport.from_audits(
            "user",
            [audit],
            [],
            1,
            scoring_profile="profile-a",
            run_mode="incremental",
            portfolio_baseline_size=3,
            baseline_signature="sig-456",
            baseline_context={"skip_archived": True},
        )
        d = report.to_dict()
        assert d["reconciliation"] is None  # No registry used
        assert d["scoring_profile"] == "profile-a"
        assert d["run_mode"] == "incremental"
        assert d["portfolio_baseline_size"] == 3
        assert d["baseline_signature"] == "sig-456"
        assert d["baseline_context"] == {"skip_archived": True}
        assert d["schema_version"] == "3.7"
        assert "lenses" in d
        assert "security_governance_preview" in d
        assert "collections" in d
        assert "scenario_summary" in d
        assert "campaign_summary" in d
        assert "writeback_results" in d
        assert "campaign_history" in d
        assert "governance_summary" in d
        assert "preflight_summary" in d
        assert "review_summary" in d
        assert "operator_summary" in d
        assert "operator_queue" in d
