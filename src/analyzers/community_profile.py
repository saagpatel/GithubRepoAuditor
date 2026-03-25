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

        details["present"] = present
        details["missing"] = missing

        # Score: proportion of files present (7 possible)
        total_checks = 7
        score = len(present) / total_checks

        if present:
            findings.append(f"Health files: {', '.join(present)}")
        if missing:
            findings.append(f"Missing: {', '.join(missing)}")

        findings.append(f"GitHub health score: {health_percentage}%")

        return self._result(score, findings, details)
