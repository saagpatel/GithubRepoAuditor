from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.analyzers.testing import TestingAnalyzer


class TestTestingAnalyzer:
    def test_find_test_files_caps_results_at_500(self, tmp_path: Path, sample_metadata) -> None:
        for index in range(501):
            (tmp_path / f"case_{index}_test.py").write_text("def test_case():\n    assert True\n")

        result = TestingAnalyzer().analyze(tmp_path, sample_metadata)

        assert result.details["test_file_count"] == 500
        assert result.score == 0.7
        assert "Found 500 test file(s)" in result.findings
        assert "Test files: 500" in result.findings

    @pytest.mark.parametrize(
        ("dependency", "framework"),
        [
            ("vitest", "vitest"),
            ("jest", "jest"),
            ("mocha", "mocha"),
            ("@playwright/test", "playwright"),
            ("cypress", "cypress"),
        ],
    )
    def test_detects_javascript_test_frameworks_from_package_json(
        self,
        tmp_path: Path,
        sample_metadata,
        dependency: str,
        framework: str,
    ) -> None:
        (tmp_path / "package.json").write_text(
            json.dumps({"devDependencies": {dependency: "latest"}})
        )

        result = TestingAnalyzer().analyze(tmp_path, sample_metadata)

        assert result.score == 0.3
        assert result.details["framework"] == framework
        assert f"Test framework: {framework}" in result.findings
        assert "Zero test files" in result.findings

    def test_invalid_package_json_falls_through_to_pytest_pyproject(
        self,
        tmp_path: Path,
        sample_metadata,
    ) -> None:
        (tmp_path / "package.json").write_text("{not valid json")
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")

        result = TestingAnalyzer().analyze(tmp_path, sample_metadata)

        assert result.score == 0.3
        assert result.details["framework"] == "pytest"
        assert "Test framework: pytest" in result.findings

    def test_detects_unittest_from_pyproject(self, tmp_path: Path, sample_metadata) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.unittest]\n")

        result = TestingAnalyzer().analyze(tmp_path, sample_metadata)

        assert result.score == 0.3
        assert result.details["framework"] == "unittest"
        assert "Test framework: unittest" in result.findings

    def test_detects_pytest_from_requirements_files(
        self,
        tmp_path: Path,
        sample_metadata,
    ) -> None:
        (tmp_path / "requirements-dev.txt").write_text("requests\npytest>=8\n")

        result = TestingAnalyzer().analyze(tmp_path, sample_metadata)

        assert result.score == 0.3
        assert result.details["framework"] == "pytest"
        assert "Test framework: pytest" in result.findings

    def test_detects_cargo_dev_dependencies(self, tmp_path: Path, sample_metadata) -> None:
        (tmp_path / "Cargo.toml").write_text(
            "[package]\nname = \"demo\"\n\n[dev-dependencies]\npretty_assertions = \"1\"\n"
        )

        result = TestingAnalyzer().analyze(tmp_path, sample_metadata)

        assert result.score == 0.3
        assert result.details["framework"] == "cargo-test"
        assert "Test framework: cargo-test" in result.findings

    def test_detects_go_test_files_without_config(self, tmp_path: Path, sample_metadata) -> None:
        (tmp_path / "math_test.go").write_text("package demo\n")

        result = TestingAnalyzer().analyze(tmp_path, sample_metadata)

        assert result.score == 1.0
        assert result.details["framework"] == "go-test"
        assert result.details["test_file_count"] == 1
        assert "Test framework: go-test" in result.findings

    def test_node_modules_test_files_are_ignored(
        self,
        tmp_path: Path,
        sample_metadata,
    ) -> None:
        node_modules = tmp_path / "node_modules" / "dep"
        node_modules.mkdir(parents=True)
        (node_modules / "dep.test.js").write_text("test('dep', () => {});\n")

        result = TestingAnalyzer().analyze(tmp_path, sample_metadata)

        assert result.score == 0.0
        assert result.details["test_file_count"] == 0
        assert result.details["framework"] is None
        assert "No test directories or test files found" in result.findings
        assert "No test framework configured" in result.findings
        assert "Zero test files" in result.findings
