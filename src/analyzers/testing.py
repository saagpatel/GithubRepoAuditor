from __future__ import annotations

import json
from pathlib import Path

from src.analyzers.base import BaseAnalyzer
from src.models import AnalyzerResult, RepoMetadata

TEST_DIRS = ("test", "tests", "__tests__", "spec", "test_suite")

TEST_PATTERNS = (
    "*_test.*",
    "*_spec.*",
    "test_*.*",
    "*.test.*",
    "*.spec.*",
    "*Tests.swift",
    "*Test.swift",
)


class TestingAnalyzer(BaseAnalyzer):
    name = "testing"
    weight = 0.15

    def analyze(
        self,
        repo_path: Path,
        metadata: RepoMetadata,
        github_client: object | None = None,
    ) -> AnalyzerResult:
        score = 0.0
        findings: list[str] = []
        details: dict = {}

        # Test directory or test files exist
        test_dirs_found = [d for d in TEST_DIRS if (repo_path / d).is_dir()]
        test_files = _find_test_files(repo_path)
        details["test_dirs"] = test_dirs_found
        details["test_file_count"] = len(test_files)

        if test_dirs_found or test_files:
            score += 0.4
            if test_dirs_found:
                findings.append(f"Test directories: {', '.join(test_dirs_found)}")
            if test_files:
                findings.append(f"Found {len(test_files)} test file(s)")
        else:
            findings.append("No test directories or test files found")

        # Test framework configured
        framework = _detect_test_framework(repo_path)
        details["framework"] = framework
        if framework:
            score += 0.3
            findings.append(f"Test framework: {framework}")
        else:
            findings.append("No test framework configured")

        # Test count >0 (file count heuristic)
        if len(test_files) > 0:
            score += 0.3
            findings.append(f"Test files: {len(test_files)}")
        else:
            findings.append("Zero test files")

        return self._result(score, findings, details)


def _find_test_files(repo_path: Path) -> list[Path]:
    """Find files matching test patterns, capped at 500 results."""
    test_files: list[Path] = []

    for pattern in TEST_PATTERNS:
        for match in repo_path.rglob(pattern):
            if match.is_file() and "node_modules" not in match.parts:
                test_files.append(match)
                if len(test_files) >= 500:
                    return test_files

    return test_files


def _detect_test_framework(repo_path: Path) -> str | None:
    """Detect which test framework is configured."""
    # JavaScript/TypeScript — check package.json
    pkg_json = repo_path / "package.json"
    if pkg_json.is_file():
        try:
            pkg = json.loads(pkg_json.read_text(errors="replace"))
            all_deps = {
                **pkg.get("devDependencies", {}),
                **pkg.get("dependencies", {}),
            }
            if "vitest" in all_deps:
                return "vitest"
            if "jest" in all_deps:
                return "jest"
            if "mocha" in all_deps:
                return "mocha"
            if "@playwright/test" in all_deps:
                return "playwright"
            if "cypress" in all_deps:
                return "cypress"
        except (json.JSONDecodeError, OSError):
            pass

    # Python — check pyproject.toml for pytest
    pyproject = repo_path / "pyproject.toml"
    if pyproject.is_file():
        try:
            content = pyproject.read_text(errors="replace")
            if "pytest" in content:
                return "pytest"
            if "unittest" in content:
                return "unittest"
        except OSError:
            pass

    # Python — check for pytest in requirements
    for req_file in ("requirements.txt", "requirements-dev.txt", "test-requirements.txt"):
        req_path = repo_path / req_file
        if req_path.is_file():
            try:
                content = req_path.read_text(errors="replace").lower()
                if "pytest" in content:
                    return "pytest"
            except OSError:
                pass

    # Rust — check Cargo.toml for dev-dependencies
    cargo = repo_path / "Cargo.toml"
    if cargo.is_file():
        try:
            content = cargo.read_text(errors="replace")
            if "[dev-dependencies]" in content:
                return "cargo-test"
        except OSError:
            pass

    # Go — test files convention
    go_test_files = list(repo_path.rglob("*_test.go"))
    if go_test_files:
        return "go-test"

    # Swift — XCTest
    if list(repo_path.rglob("*Tests.swift")) or list(repo_path.rglob("*Test.swift")):
        return "xctest"

    return None
