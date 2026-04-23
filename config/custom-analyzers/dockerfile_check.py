"""Example custom analyzer — checks if a repo has a Dockerfile."""

from pathlib import Path

from src.analyzers.base import BaseAnalyzer
from src.github_client import GitHubClient
from src.models import AnalyzerResult, RepoMetadata


class DockerfileAnalyzer(BaseAnalyzer):
    name = "dockerfile"
    weight = 0.0  # Advisory — doesn't affect score

    def analyze(
        self,
        repo_path: Path,
        metadata: RepoMetadata,
        github_client: GitHubClient | None = None,
    ) -> AnalyzerResult:
        dockerfile = repo_path / "Dockerfile"
        compose = repo_path / "docker-compose.yml"
        compose_alt = repo_path / "compose.yml"

        score = 0.0
        findings = []
        details: dict = {"has_dockerfile": False, "has_compose": False}

        if dockerfile.is_file():
            score += 0.6
            findings.append("Has Dockerfile")
            details["has_dockerfile"] = True
        if compose.is_file() or compose_alt.is_file():
            score += 0.4
            findings.append("Has Docker Compose")
            details["has_compose"] = True

        if not findings:
            findings.append("No Docker configuration found")

        return self._result(score, findings, details)
