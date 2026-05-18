from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from src.analyzers.base import BaseAnalyzer
from src.models import AnalyzerResult, RepoMetadata

if TYPE_CHECKING:
    from src.github_client import GitHubClient

# Health files checked by GitHub's community profile endpoint
HEALTH_FILES = [
    "description",
    "documentation",
    "readme",
    "code_of_conduct",
    "contributing",
    "license",
    "security",
    "issue_template",
    "pull_request_template",
    "changelog",
]


class CommunityProfileAnalyzer(BaseAnalyzer):
    """Scores community health using GitHub's /community/profile endpoint.

    Checks: README, LICENSE, CODE_OF_CONDUCT, CONTRIBUTING, SECURITY,
    issue/PR templates — in a single API call.
    """

    name = "community_profile"
    weight = 0.03

    def analyze(
        self,
        repo_path: Path,
        metadata: RepoMetadata,
        github_client: GitHubClient | None = None,
    ) -> AnalyzerResult:
        score = 0.0
        findings: list[str] = []
        details: dict = {}

        if not github_client:
            findings.append("Skipped community profile (no API client)")
            return self._result(0.0, findings, details)

        owner = metadata.full_name.split("/")[0]
        profile = github_client.get_community_profile(owner, metadata.name)

        if not profile:
            findings.append("Could not fetch community profile")
            return self._result(0.0, findings, details)

        # Extract health percentage directly from API
        health_percentage = profile.get("health_percentage", 0)
        details["health_percentage"] = health_percentage

        # Check individual files
        files = profile.get("files", {})
        present: list[str] = []
        missing: list[str] = []

        for key in ["readme", "license", "code_of_conduct", "contributing", "security"]:
            if files.get(key):
                present.append(key)
            else:
                missing.append(key)

        # Issue and PR templates
        if files.get("issue_template"):
            present.append("issue_template")
        else:
            missing.append("issue_template")
        if files.get("pull_request_template"):
            present.append("pull_request_template")
        else:
            missing.append("pull_request_template")

        # Local filesystem fallback for files the API missed
        _LOCAL_FALLBACK = {
            "security": ["SECURITY.md", ".github/SECURITY.md"],
            "code_of_conduct": ["CODE_OF_CONDUCT.md", ".github/CODE_OF_CONDUCT.md"],
            "issue_template": [".github/ISSUE_TEMPLATE"],
            "pull_request_template": [".github/PULL_REQUEST_TEMPLATE.md"],
            "contributing": ["CONTRIBUTING.md", ".github/CONTRIBUTING.md"],
        }
        for file_key, paths in _LOCAL_FALLBACK.items():
            if file_key not in present:
                for p in paths:
                    target = repo_path / p
                    if target.is_file() or target.is_dir():
                        present.append(file_key)
                        if file_key in missing:
                            missing.remove(file_key)
                        break

        # Also check changelog (not in GitHub's API but valuable for completeness)
        for changelog_name in ("CHANGELOG.md", "CHANGELOG"):
            if (repo_path / changelog_name).is_file():
                present.append("changelog")
                break

        details["present"] = present
        details["missing"] = missing

        # Score: proportion of files present (8 possible with changelog)
        total_checks = 8
        score = len(present) / total_checks

        if present:
            findings.append(f"Health files: {', '.join(present)}")
        if missing:
            findings.append(f"Missing: {', '.join(missing)}")

        findings.append(f"GitHub health score: {health_percentage}%")

        return self._result(score, findings, details)
