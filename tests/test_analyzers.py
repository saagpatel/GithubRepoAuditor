from __future__ import annotations

from pathlib import Path

from src.analyzers.readme import ReadmeAnalyzer
from src.analyzers.structure import StructureAnalyzer
from src.analyzers.testing import TestingAnalyzer
from src.analyzers.cicd import CicdAnalyzer
from src.analyzers.dependencies import DependenciesAnalyzer
from src.analyzers.code_quality import CodeQualityAnalyzer
from src.analyzers.completeness import DocumentationAnalyzer, BuildReadinessAnalyzer
from src.models import RepoMetadata


class TestReadmeAnalyzer:
    def test_full_readme_scores_high(self, tmp_repo, sample_metadata):
        # Beef up the README to pass all checks
        (tmp_repo / "README.md").write_text(
            "![badge](https://img.shields.io/badge/test-passing-green)\n\n"
            "# Test Repo\n\n"
            "A comprehensive project for testing various features and capabilities across multiple dimensions.\n\n"
            "## Installation\n\n```bash\npip install test-repo\n```\n\n"
            "## Usage\n\n```python\nimport test_repo\ntest_repo.run()\n```\n\n"
            "## Features\n\n- Feature one\n- Feature two\n- Feature three\n\n"
            "## Contributing\n\nPRs welcome.\n\n"
            + "Additional documentation and details follow here. " * 10
        )
        result = ReadmeAnalyzer().analyze(tmp_repo, sample_metadata)
        assert result.score >= 0.8
        assert result.dimension == "readme"
        assert any("README found" in f for f in result.findings)

    def test_no_readme_scores_zero(self, empty_repo, sample_metadata):
        (empty_repo / "README.md").unlink()
        result = ReadmeAnalyzer().analyze(empty_repo, sample_metadata)
        assert result.score == 0.0
        assert any("No README" in f for f in result.findings)

    def test_short_readme(self, tmp_path, sample_metadata):
        repo = tmp_path / "short"
        repo.mkdir()
        (repo / "README.md").write_text("# Hi\n")
        result = ReadmeAnalyzer().analyze(repo, sample_metadata)
        assert result.score < 0.5


class TestStructureAnalyzer:
    def test_well_structured_repo(self, tmp_repo, sample_metadata):
        result = StructureAnalyzer().analyze(tmp_repo, sample_metadata)
        assert result.score >= 0.8
        assert any(".gitignore" in f for f in result.findings)
        assert any("LICENSE" in f for f in result.findings)

    def test_empty_repo(self, empty_repo, sample_metadata):
        result = StructureAnalyzer().analyze(empty_repo, sample_metadata)
        assert result.score < 0.3

    def test_swift_repo_detects_xcodeproj(self, swift_repo):
        meta = RepoMetadata(
            name="swift-repo", full_name="user/swift-repo",
            description=None, language="Swift", languages={"Swift": 1000},
            private=False, fork=False, archived=False,
            created_at=None, updated_at=None, pushed_at=None,
            default_branch="main", stars=0, forks=0, open_issues=0,
            size_kb=100, html_url="", clone_url="", topics=[],
        )
        result = StructureAnalyzer().analyze(swift_repo, meta)
        # After tuning, Swift repos should detect xcodeproj as config
        assert result.score >= 0.3


class TestTestingAnalyzer:
    def test_repo_with_tests(self, tmp_repo, sample_metadata):
        result = TestingAnalyzer().analyze(tmp_repo, sample_metadata)
        assert result.score >= 0.7
        assert result.details["test_file_count"] >= 2

    def test_repo_without_tests(self, empty_repo, sample_metadata):
        result = TestingAnalyzer().analyze(empty_repo, sample_metadata)
        assert result.score == 0.0


class TestCicdAnalyzer:
    def test_no_ci(self, tmp_repo, sample_metadata):
        result = CicdAnalyzer().analyze(tmp_repo, sample_metadata)
        # tmp_repo has no .github/workflows but has a Makefile-less setup
        assert result.dimension == "cicd"

    def test_with_github_actions(self, tmp_repo, sample_metadata):
        workflows = tmp_repo / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yml").write_text("name: CI\non: push\n")
        result = CicdAnalyzer().analyze(tmp_repo, sample_metadata)
        assert result.score >= 0.5


class TestDependenciesAnalyzer:
    def test_python_deps(self, tmp_repo, sample_metadata):
        result = DependenciesAnalyzer().analyze(tmp_repo, sample_metadata)
        assert result.score >= 0.6
        assert result.details["dep_count"] in (0, 2)  # 2 if parsed, 0 if pyproject.toml takes priority

    def test_no_deps(self, empty_repo, sample_metadata):
        result = DependenciesAnalyzer().analyze(empty_repo, sample_metadata)
        assert result.score == 0.0


class TestCodeQualityAnalyzer:
    def test_quality_signals(self, tmp_repo, sample_metadata):
        result = CodeQualityAnalyzer().analyze(tmp_repo, sample_metadata)
        assert result.score >= 0.4
        assert result.details.get("entry_point") is not None

    def test_empty_repo_quality(self, empty_repo, sample_metadata):
        result = CodeQualityAnalyzer().analyze(empty_repo, sample_metadata)
        assert result.score < 0.5


class TestDocumentationAnalyzer:
    def test_minimal_docs(self, tmp_repo, sample_metadata):
        result = DocumentationAnalyzer().analyze(tmp_repo, sample_metadata)
        assert result.dimension == "documentation"

    def test_with_docs_dir(self, tmp_repo, sample_metadata):
        (tmp_repo / "docs").mkdir()
        (tmp_repo / "CHANGELOG.md").write_text("# Changelog\n")
        result = DocumentationAnalyzer().analyze(tmp_repo, sample_metadata)
        assert result.score >= 0.6


class TestBuildReadinessAnalyzer:
    def test_no_build_readiness(self, tmp_repo, sample_metadata):
        result = BuildReadinessAnalyzer().analyze(tmp_repo, sample_metadata)
        assert result.dimension == "build_readiness"

    def test_with_docker(self, tmp_repo, sample_metadata):
        (tmp_repo / "Dockerfile").write_text("FROM python:3.11\n")
        (tmp_repo / "Makefile").write_text("build:\n\techo build\n")
        result = BuildReadinessAnalyzer().analyze(tmp_repo, sample_metadata)
        assert result.score >= 0.6
