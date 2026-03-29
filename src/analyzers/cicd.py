from __future__ import annotations

import json
from pathlib import Path

from src.analyzers.base import BaseAnalyzer
from src.models import AnalyzerResult, RepoMetadata

ALT_CI_FILES = (
    ".travis.yml",
    "Jenkinsfile",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "bitbucket-pipelines.yml",
    "azure-pipelines.yml",
    "appveyor.yml",
)

ALT_CI_DIRS = (".circleci",)


class CicdAnalyzer(BaseAnalyzer):
    name = "cicd"
    weight = 0.10

    def analyze(
        self,
        repo_path: Path,
        metadata: RepoMetadata,
        github_client: object | None = None,
    ) -> AnalyzerResult:
        score = 0.0
        findings: list[str] = []
        details: dict = {}

        # GitHub Actions workflows
        workflows_dir = repo_path / ".github" / "workflows"
        workflow_files: list[str] = []
        if workflows_dir.is_dir():
            workflow_files = [
                f.name
                for f in workflows_dir.iterdir()
                if f.suffix in (".yml", ".yaml") and f.is_file()
            ]

        if workflow_files:
            score += 0.5
            findings.append(f"GitHub Actions: {', '.join(workflow_files)}")
            details["github_actions"] = workflow_files
        else:
            findings.append("No GitHub Actions workflows")

        # Alternative CI config
        alt_ci_found: list[str] = []
        for name in ALT_CI_FILES:
            if (repo_path / name).is_file():
                alt_ci_found.append(name)
        for name in ALT_CI_DIRS:
            if (repo_path / name).is_dir():
                alt_ci_found.append(name)

        if alt_ci_found:
            score += 0.3
            findings.append(f"Alternative CI: {', '.join(alt_ci_found)}")
            details["alt_ci"] = alt_ci_found
        elif not workflow_files:
            findings.append("No CI configuration found")

        # Build scripts in package.json or Makefile
        has_build_script = _has_build_scripts(repo_path)
        if has_build_script:
            score += 0.2
            findings.append("Has build/test scripts")
        else:
            findings.append("No build scripts detected")

        return self._result(score, findings, details)


def _has_build_scripts(repo_path: Path) -> bool:
    """Check for build/test scripts in package.json or Makefile."""
    # package.json scripts
    pkg_json = repo_path / "package.json"
    if pkg_json.is_file():
        try:
            pkg = json.loads(pkg_json.read_text(errors="replace"))
            scripts = pkg.get("scripts", {})
            if "build" in scripts or "test" in scripts:
                return True
        except (json.JSONDecodeError, OSError):
            pass

    # Makefile
    if (repo_path / "Makefile").is_file():
        return True

    # Justfile
    if (repo_path / "justfile").is_file() or (repo_path / "Justfile").is_file():
        return True

    # Swift build systems
    if (repo_path / "Package.swift").is_file():  # Swift Package Manager
        return True
    if (repo_path / "Podfile").is_file():  # CocoaPods
        return True
    if (repo_path / "project.yml").is_file() or (repo_path / "project.yaml").is_file():  # XcodeGen
        return True

    return False
