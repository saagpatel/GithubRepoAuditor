from __future__ import annotations

from datetime import datetime, timezone

from src.models import AnalyzerResult, RepoMetadata
from src.security_intelligence import build_security_posture


def _make_metadata(**overrides) -> RepoMetadata:
    defaults = dict(
        name="secure-repo",
        full_name="user/secure-repo",
        description=None,
        language="Python",
        languages={"Python": 1000},
        private=False,
        fork=False,
        archived=False,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        pushed_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
        default_branch="main",
        stars=5,
        forks=0,
        open_issues=0,
        size_kb=100,
        html_url="https://github.com/user/secure-repo",
        clone_url="https://github.com/user/secure-repo.git",
        topics=[],
    )
    defaults.update(overrides)
    return RepoMetadata(**defaults)


def _make_results() -> list[AnalyzerResult]:
    return [
        AnalyzerResult(
            dimension="security",
            score=0.55,
            max_score=1.0,
            findings=["No SECURITY.md"],
            details={
                "secrets_found": 0,
                "dangerous_files": [],
                "has_security_md": False,
                "has_dependabot": True,
            },
        )
    ]


class _FakeGitHubClient:
    def get_repo_security_and_analysis(self, owner: str, repo: str) -> dict:
        return {
            "available": True,
            "data": {"security_and_analysis": {"secret_scanning": {"status": "enabled"}}},
        }

    def get_secret_scanning_alert_count(self, owner: str, repo: str) -> dict:
        return {"available": True, "open_alerts": 0, "http_status": 200}

    def get_code_scanning_alert_count(self, owner: str, repo: str) -> dict:
        return {"available": True, "open_alerts": 2, "http_status": 200}

    def get_sbom_exportability(self, owner: str, repo: str) -> dict:
        return {"available": True, "package_count": 4, "http_status": 200}


def test_build_security_posture_local_only():
    posture = build_security_posture(_make_metadata(), _make_results(), None, security_offline=True)

    assert posture["local"]["available"] is True
    assert posture["github"]["provider_available"] is False
    assert posture["recommendations"]
    assert posture["score"] > 0


def test_build_security_posture_merges_github_signals():
    posture = build_security_posture(
        _make_metadata(),
        _make_results(),
        _FakeGitHubClient(),
        security_offline=False,
        scorecard_enabled=False,
    )

    assert posture["github"]["provider_available"] is True
    assert posture["github"]["sbom_exportable"] is True
    assert posture["github"]["code_scanning_alerts"] == 2
    assert any(item["key"] == "review-code-scanning-alerts" for item in posture["recommendations"])


def test_build_security_posture_scorecard_private_repo_skips_provider():
    posture = build_security_posture(
        _make_metadata(private=True, full_name="user/private-repo"),
        _make_results(),
        None,
        scorecard_enabled=True,
    )

    assert posture["scorecard"]["available"] is False
    assert posture["scorecard"]["reason"] == "private-repo"
