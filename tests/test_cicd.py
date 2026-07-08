from __future__ import annotations

import pytest

from src.analyzers.cicd import CicdAnalyzer, _has_build_scripts


class TestCicdAnalyzerAltCi:
    def test_github_actions_alt_ci_and_package_build_score_together(
        self, tmp_path, sample_metadata
    ):
        repo = tmp_path / "full-ci-repo"
        repo.mkdir()
        workflows = repo / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yaml").write_text("name: CI\non: push\n")
        (repo / "Dockerfile").write_text("FROM python:3.12\n")
        (repo / "package.json").write_text('{"scripts": {"build": "vite build"}}\n')

        result = CicdAnalyzer().analyze(repo, sample_metadata)

        assert result.score == pytest.approx(1.0)
        assert "GitHub Actions: ci.yaml" in result.findings
        assert "Alternative CI: Dockerfile" in result.findings
        assert "Has build/test scripts" in result.findings
        assert result.details["github_actions"] == ["ci.yaml"]
        assert result.details["alt_ci"] == ["Dockerfile"]

    def test_dockerfile_scores_alt_ci_only(self, tmp_path, sample_metadata):
        repo = tmp_path / "docker-repo"
        repo.mkdir()
        (repo / "Dockerfile").write_text("FROM python:3.12\n")

        result = CicdAnalyzer().analyze(repo, sample_metadata)

        assert result.score == pytest.approx(0.3)
        assert "Alternative CI: Dockerfile" in result.findings
        assert "No GitHub Actions workflows" in result.findings
        assert "No build scripts detected" in result.findings
        assert result.details["alt_ci"] == ["Dockerfile"]

    def test_circleci_directory_scores_alt_ci_only(self, tmp_path, sample_metadata):
        repo = tmp_path / "circleci-repo"
        repo.mkdir()
        (repo / ".circleci").mkdir()

        result = CicdAnalyzer().analyze(repo, sample_metadata)

        assert result.score == pytest.approx(0.3)
        assert "Alternative CI: .circleci" in result.findings
        assert "No GitHub Actions workflows" in result.findings
        assert "No build scripts detected" in result.findings
        assert result.details["alt_ci"] == [".circleci"]


class TestHasBuildScripts:
    def test_package_json_build_script_is_detected(self, tmp_path):
        repo = tmp_path / "package-build-repo"
        repo.mkdir()
        (repo / "package.json").write_text('{"scripts": {"build": "vite build"}}\n')

        assert _has_build_scripts(repo) is True

    def test_package_json_test_script_is_detected(self, tmp_path):
        repo = tmp_path / "package-test-repo"
        repo.mkdir()
        (repo / "package.json").write_text('{"scripts": {"test": "vitest"}}\n')

        assert _has_build_scripts(repo) is True

    def test_malformed_package_json_falls_through_to_false(self, tmp_path):
        repo = tmp_path / "malformed-package-repo"
        repo.mkdir()
        (repo / "package.json").write_text('{"scripts": {"build": "missing brace"\n')

        assert _has_build_scripts(repo) is False

    def test_makefile_is_detected(self, tmp_path):
        repo = tmp_path / "makefile-repo"
        repo.mkdir()
        (repo / "Makefile").write_text("test:\n\tpytest\n")

        assert _has_build_scripts(repo) is True

    @pytest.mark.parametrize("filename", ["justfile", "Justfile"])
    def test_justfile_variants_are_detected(self, tmp_path, filename):
        repo = tmp_path / f"{filename}-repo"
        repo.mkdir()
        (repo / filename).write_text("test:\n    pytest\n")

        assert _has_build_scripts(repo) is True
