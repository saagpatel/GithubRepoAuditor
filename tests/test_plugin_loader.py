"""Tests for the custom analyzer plugin loader."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.analyzers import load_custom_analyzers
from src.analyzers.base import BaseAnalyzer
from src.models import AnalyzerResult, RepoMetadata


def _make_analyzer_source(name: str = "custom_test", weight: float = 0.5) -> str:
    return f"""\
from pathlib import Path
from src.analyzers.base import BaseAnalyzer
from src.models import AnalyzerResult, RepoMetadata

class CustomTestAnalyzer(BaseAnalyzer):
    name = "{name}"
    weight = {weight}

    def analyze(self, repo_path, metadata, github_client=None):
        return self._result(0.8, ["Custom check passed"], {{"custom": True}})
"""


def _make_metadata() -> RepoMetadata:
    from datetime import datetime, timezone

    return RepoMetadata(
        name="test-repo",
        full_name="user/test-repo",
        description=None,
        language=None,
        languages={},
        private=False,
        fork=False,
        archived=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        pushed_at=None,
        default_branch="main",
        stars=0,
        forks=0,
        open_issues=0,
        size_kb=0,
        html_url="https://github.com/user/test-repo",
        clone_url="https://github.com/user/test-repo.git",
        topics=[],
    )


class TestLoadCustomAnalyzers:
    def test_returns_empty_for_missing_directory(self, tmp_path: Path) -> None:
        result = load_custom_analyzers(tmp_path / "does_not_exist")
        assert result == []

    def test_returns_empty_for_file_instead_of_directory(self, tmp_path: Path) -> None:
        f = tmp_path / "not_a_dir.py"
        f.write_text("")
        result = load_custom_analyzers(f)
        assert result == []

    def test_discovers_subclass_in_py_file(self, tmp_path: Path) -> None:
        (tmp_path / "my_analyzer.py").write_text(_make_analyzer_source("my_custom"))
        result = load_custom_analyzers(tmp_path)
        assert len(result) == 1
        assert result[0].name == "my_custom"

    def test_skips_dunder_files(self, tmp_path: Path) -> None:
        (tmp_path / "__init__.py").write_text(_make_analyzer_source("should_skip"))
        result = load_custom_analyzers(tmp_path)
        assert result == []

    def test_skips_files_without_subclass(self, tmp_path: Path) -> None:
        (tmp_path / "helpers.py").write_text("def util(): pass\n")
        result = load_custom_analyzers(tmp_path)
        assert result == []

    def test_warns_on_broken_file(self, tmp_path: Path, capsys) -> None:
        (tmp_path / "broken.py").write_text("raise RuntimeError('oops')\n")
        result = load_custom_analyzers(tmp_path)
        assert result == []
        captured = capsys.readouterr()
        assert "broken.py" in captured.err
        assert "Warning" in captured.err

    def test_discovered_analyzer_can_run_analyze(self, tmp_path: Path) -> None:
        (tmp_path / "checker.py").write_text(_make_analyzer_source("docker_check", 0.0))
        analyzers = load_custom_analyzers(tmp_path)
        assert len(analyzers) == 1

        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        metadata = _make_metadata()
        result = analyzers[0].analyze(repo_path, metadata)
        assert isinstance(result, AnalyzerResult)
        assert result.dimension == "docker_check"
        assert result.score == pytest.approx(0.8)

    def test_loads_multiple_files_in_sorted_order(self, tmp_path: Path) -> None:
        (tmp_path / "z_last.py").write_text(_make_analyzer_source("z_analyzer"))
        (tmp_path / "a_first.py").write_text(_make_analyzer_source("a_analyzer"))
        result = load_custom_analyzers(tmp_path)
        assert len(result) == 2
        assert result[0].name == "a_analyzer"
        assert result[1].name == "z_analyzer"
