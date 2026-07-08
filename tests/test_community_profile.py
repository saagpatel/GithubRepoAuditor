from __future__ import annotations

from pathlib import Path

from src.analyzers.community_profile import CommunityProfileAnalyzer
from src.models import RepoMetadata


class _CommunityProfileClient:
    def __init__(self, profile: dict | None) -> None:
        self.profile = profile

    def get_community_profile(self, owner: str, repo: str) -> dict | None:
        assert owner == "user"
        assert repo == "test-repo"
        return self.profile


def test_no_github_client_skips_community_profile(
    tmp_path: Path, sample_metadata: RepoMetadata
) -> None:
    result = CommunityProfileAnalyzer().analyze(tmp_path, sample_metadata)

    assert result.dimension == "community_profile"
    assert result.score == 0.0
    assert result.details == {}
    assert result.findings == ["Skipped community profile (no API client)"]


def test_falsy_community_profile_reports_fetch_failure(
    tmp_path: Path, sample_metadata: RepoMetadata
) -> None:
    client = _CommunityProfileClient(profile={})

    result = CommunityProfileAnalyzer().analyze(tmp_path, sample_metadata, client)

    assert result.score == 0.0
    assert result.details == {}
    assert result.findings == ["Could not fetch community profile"]


def test_api_present_and_missing_files_drive_score_details_and_findings(
    tmp_path: Path, sample_metadata: RepoMetadata
) -> None:
    client = _CommunityProfileClient(
        profile={
            "health_percentage": 66,
            "files": {
                "readme": {"name": "README.md"},
                "license": None,
                "code_of_conduct": {"name": "CODE_OF_CONDUCT.md"},
                "contributing": None,
                "security": {"name": "SECURITY.md"},
                "issue_template": {"name": "bug_report.md"},
                "pull_request_template": None,
            },
        }
    )

    result = CommunityProfileAnalyzer().analyze(tmp_path, sample_metadata, client)

    assert result.score == 4 / 8
    assert result.details == {
        "health_percentage": 66,
        "present": ["readme", "code_of_conduct", "security", "issue_template"],
        "missing": ["license", "contributing", "pull_request_template"],
    }
    assert result.findings == [
        "Health files: readme, code_of_conduct, security, issue_template",
        "Missing: license, contributing, pull_request_template",
        "GitHub health score: 66%",
    ]


def test_local_fallbacks_add_files_and_directories_when_api_reports_missing(
    tmp_path: Path, sample_metadata: RepoMetadata
) -> None:
    (tmp_path / ".github" / "ISSUE_TEMPLATE").mkdir(parents=True)
    (tmp_path / ".github" / "PULL_REQUEST_TEMPLATE.md").write_text("## Summary\n")
    (tmp_path / "SECURITY.md").write_text("# Security\n")
    (tmp_path / ".github" / "CODE_OF_CONDUCT.md").write_text("# Code of Conduct\n")
    (tmp_path / "CONTRIBUTING.md").write_text("# Contributing\n")
    (tmp_path / "CHANGELOG").write_text("# Changelog\n")
    client = _CommunityProfileClient(
        profile={
            "health_percentage": 10,
            "files": {
                "readme": None,
                "license": None,
                "code_of_conduct": None,
                "contributing": None,
                "security": None,
                "issue_template": None,
                "pull_request_template": None,
            },
        }
    )

    result = CommunityProfileAnalyzer().analyze(tmp_path, sample_metadata, client)

    assert result.score == 6 / 8
    assert result.details == {
        "health_percentage": 10,
        "present": [
            "security",
            "code_of_conduct",
            "issue_template",
            "pull_request_template",
            "contributing",
            "changelog",
        ],
        "missing": ["readme", "license"],
    }
    assert result.findings == [
        "Health files: security, code_of_conduct, issue_template, " +
        "pull_request_template, contributing, changelog",
        "Missing: readme, license",
        "GitHub health score: 10%",
    ]


def test_all_api_templates_present_with_changelog_reaches_full_score(
    tmp_path: Path, sample_metadata: RepoMetadata
) -> None:
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n")
    client = _CommunityProfileClient(
        profile={
            "health_percentage": 100,
            "files": {
                "readme": {"name": "README.md"},
                "license": {"name": "LICENSE"},
                "code_of_conduct": {"name": "CODE_OF_CONDUCT.md"},
                "contributing": {"name": "CONTRIBUTING.md"},
                "security": {"name": "SECURITY.md"},
                "issue_template": {"name": "ISSUE_TEMPLATE.md"},
                "pull_request_template": {"name": "PULL_REQUEST_TEMPLATE.md"},
            },
        }
    )

    result = CommunityProfileAnalyzer().analyze(tmp_path, sample_metadata, client)

    assert result.score == 1.0
    assert result.details == {
        "health_percentage": 100,
        "present": [
            "readme",
            "license",
            "code_of_conduct",
            "contributing",
            "security",
            "issue_template",
            "pull_request_template",
            "changelog",
        ],
        "missing": [],
    }
    assert result.findings == [
        "Health files: readme, license, code_of_conduct, contributing, security, "
        "issue_template, pull_request_template, changelog",
        "GitHub health score: 100%",
    ]
