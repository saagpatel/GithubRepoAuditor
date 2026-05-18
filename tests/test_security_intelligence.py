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
                "dependabot_supported": True,
                "dependabot_supported_ecosystems": ["pip"],
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


class _WarningOnlyCodeScanningClient(_FakeGitHubClient):
    def get_code_scanning_alert_count(self, owner: str, repo: str) -> dict:
        return {
            "available": True,
            "open_alerts": 3,
            "critical": 0,
            "high": 0,
            "warning": 3,
            "note": 0,
            "http_status": 200,
        }


class _ContextualHighCodeScanningClient(_FakeGitHubClient):
    def get_code_scanning_alert_count(self, owner: str, repo: str) -> dict:
        return {
            "available": True,
            "open_alerts": 2,
            "critical": 0,
            "high": 2,
            "actionable_high": 0,
            "contextual_high": 2,
            "warning": 0,
            "note": 0,
            "http_status": 200,
        }


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


def test_build_security_posture_downgrades_warning_only_code_scanning_alerts():
    posture = build_security_posture(
        _make_metadata(),
        _make_results(),
        _WarningOnlyCodeScanningClient(),
        security_offline=False,
        scorecard_enabled=False,
    )

    recommendation = next(
        item for item in posture["recommendations"] if item["key"] == "review-code-scanning-alerts"
    )

    assert posture["github"]["code_scanning_high_alerts"] == 0
    assert posture["github"]["code_scanning_warning_alerts"] == 3
    assert recommendation["priority"] == "medium"
    assert "warning-level or contextual" in recommendation["why"]


def test_build_security_posture_downgrades_contextual_scorecard_high_alerts():
    posture = build_security_posture(
        _make_metadata(),
        _make_results(),
        _ContextualHighCodeScanningClient(),
        security_offline=False,
        scorecard_enabled=False,
    )

    recommendation = next(
        item for item in posture["recommendations"] if item["key"] == "review-code-scanning-alerts"
    )

    assert posture["github"]["code_scanning_high_alerts"] == 2
    assert posture["github"]["code_scanning_actionable_high_alerts"] == 0
    assert posture["github"]["code_scanning_contextual_high_alerts"] == 2
    assert recommendation["priority"] == "medium"


def test_build_security_posture_scorecard_private_repo_skips_provider():
    posture = build_security_posture(
        _make_metadata(private=True, full_name="user/private-repo"),
        _make_results(),
        None,
        scorecard_enabled=True,
    )

    assert posture["scorecard"]["available"] is False
    assert posture["scorecard"]["reason"] == "private-repo"


def test_build_security_posture_skips_dependabot_recommendation_without_supported_ecosystem():
    results = [
        AnalyzerResult(
            dimension="security",
            score=0.9,
            max_score=1.0,
            findings=["No supported Dependabot ecosystem detected"],
            details={
                "secrets_found": 0,
                "dangerous_files": [],
                "has_security_md": True,
                "has_dependabot": False,
                "dependabot_supported": False,
                "dependabot_supported_ecosystems": [],
            },
        )
    ]

    posture = build_security_posture(
        _make_metadata(language="GDScript", languages={"GDScript": 1000}),
        results,
        None,
        security_offline=True,
    )

    assert posture["dependabot_supported"] is False
    assert not any(item["key"] == "add-dependabot-config" for item in posture["recommendations"])


def test_build_security_posture_keeps_dependabot_recommendation_for_supported_ecosystem():
    results = [
        AnalyzerResult(
            dimension="security",
            score=0.9,
            max_score=1.0,
            findings=["No Dependabot config"],
            details={
                "secrets_found": 0,
                "dangerous_files": [],
                "has_security_md": True,
                "has_dependabot": False,
                "dependabot_supported": True,
                "dependabot_supported_ecosystems": ["npm"],
            },
        )
    ]

    posture = build_security_posture(_make_metadata(), results, None, security_offline=True)

    assert posture["dependabot_supported_ecosystems"] == ["npm"]
    assert any(item["key"] == "add-dependabot-config" for item in posture["recommendations"])
