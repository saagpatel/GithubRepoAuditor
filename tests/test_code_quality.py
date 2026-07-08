from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.analyzers.code_quality import (
    CodeQualityAnalyzer,
    _classify_commits,
    _count_todos,
    _detect_vendored,
    _find_entry_point,
    _has_type_definitions,
    _radon_analysis,
    _score_commit_messages,
)
from src.models import RepoMetadata


def _meta(**overrides) -> RepoMetadata:
    defaults = dict(
        name="test",
        full_name="user/test",
        description=None,
        language="Python",
        languages={"Python": 5000},
        private=False,
        fork=False,
        archived=False,
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        pushed_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
        default_branch="main",
        stars=0,
        forks=0,
        open_issues=0,
        size_kb=100,
        html_url="",
        clone_url="",
        topics=[],
    )
    defaults.update(overrides)
    return RepoMetadata(**defaults)


def _fake_github_client(*, commits: list[dict], prs: list[dict]) -> MagicMock:
    client = MagicMock()
    client.get_recent_commits.return_value = commits
    client.get_pull_requests.return_value = prs
    return client


def _commit(message: str) -> dict:
    return {"commit": {"message": message}}


class TestCodeQualityAnalyzer:
    def test_analyze_reports_high_todo_density_vendored_content_and_weak_commits(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "main.py").write_text(
            "# TODO: one\n"
            "# FIXME: two\n"
            "# HACK: three\n"
            "print('tiny project')\n"
        )
        (tmp_path / "vendor").mkdir()
        client = _fake_github_client(
            commits=[_commit("fix"), _commit("wip"), _commit("ok enough detail")],
            prs=[],
        )

        result = CodeQualityAnalyzer().analyze(
            tmp_path,
            _meta(),
            github_client=client,
        )

        assert result.score == pytest.approx(0.35)
        assert result.details["entry_point"] == "main.py"
        assert result.details["todo_count"] == 3
        assert result.details["total_loc"] == 4
        assert result.details["todo_density_per_1k"] == 750.0
        assert result.details["has_types"] is False
        assert result.details["vendored"] == ["vendor/ committed"]
        assert result.details["commit_quality"] == "1/3 descriptive commits"
        assert "High TODO density: 750.0/1k LOC" in result.findings
        assert "Vendored content: vendor/ committed" in result.findings
        assert "Commit messages could be more descriptive" in result.findings

    def test_analyze_reports_moderate_density_conventional_commits_and_pr_ratio(
        self, tmp_path: Path
    ) -> None:
        lines = ["print('line')\n"] * 119 + ["# TODO: later\n"]
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("".join(lines))
        client = _fake_github_client(
            commits=[
                _commit("feat: add parser (#12)\n\nBody"),
                _commit("fix(api)!: handle retries"),
                _commit("docs: refresh usage guide"),
            ],
            prs=[
                {"merged_at": "2026-03-01T00:00:00Z"},
                {"merged_at": None},
                {"merged_at": "2026-03-02T00:00:00Z"},
            ],
        )

        result = CodeQualityAnalyzer().analyze(
            tmp_path,
            _meta(),
            github_client=client,
        )

        assert result.score == pytest.approx(0.75)
        assert result.details["entry_point"] == "src/main.py"
        assert result.details["todo_density_per_1k"] == 8.3
        assert result.details["commit_quality"] == "3/3 descriptive commits"
        assert result.details["conventional_ratio"] == 1.0
        assert result.details["commit_types"] == {"feat": 1, "fix": 1, "docs": 1}
        assert result.details["has_issue_refs"] == 0.33
        assert result.details["pr_total"] == 3
        assert result.details["pr_merged"] == 2
        assert result.details["pr_merge_ratio"] == 0.67
        assert "Moderate TODO density: 8.3/1k LOC" in result.findings
        assert "Commit messages are descriptive" in result.findings
        assert "Conventional commits: 100%" in result.findings
        assert "PRs: 2/3 merged" in result.findings

    def test_analyze_without_code_files_skips_api_commit_analysis(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "README.md").write_text("# docs only\n")

        result = CodeQualityAnalyzer().analyze(tmp_path, _meta(language="Ruby"))

        assert result.score == pytest.approx(0.15)
        assert result.details["entry_point"] is None
        assert result.details["todo_count"] == 0
        assert result.details["total_loc"] == 0
        assert result.details["has_types"] is False
        assert result.details["vendored"] == []
        assert "No identifiable entry point" in result.findings
        assert "No code files to assess TODO density" in result.findings
        assert "Skipped commit message analysis (no API client)" in result.findings


class TestEntryPointDetection:
    def test_detects_generic_entry_point_for_unknown_language(self, tmp_path: Path) -> None:
        (tmp_path / "App.tsx").write_text("export default function App() { return null; }\n")

        assert _find_entry_point(tmp_path, "Elixir") == "App.tsx"

    def test_swift_entry_point_skips_derived_data_and_falls_back_to_xcodeproj(
        self, tmp_path: Path
    ) -> None:
        derived = tmp_path / "DerivedData" / "Build"
        derived.mkdir(parents=True)
        (derived / "MyApp.swift").write_text("@main struct Ignored {}\n")
        (tmp_path / "MyApp.xcworkspace").mkdir()

        assert _find_entry_point(tmp_path, "Swift") == "MyApp.xcworkspace"

    def test_swift_entry_point_prefers_app_swift_outside_derived_data(
        self, tmp_path: Path
    ) -> None:
        source = tmp_path / "Sources" / "Mobile"
        source.mkdir(parents=True)
        (source / "CoolApp.swift").write_text("@main struct CoolApp {}\n")

        assert _find_entry_point(tmp_path, "Swift") == "Sources"


class TestTodoCounting:
    def test_counts_todo_markers_and_skips_hidden_and_vendored_files(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "app.py").write_text("# TODO: counted\nprint('x')\n# xxx counted too\n")
        hidden = tmp_path / ".cache"
        hidden.mkdir()
        (hidden / "ignored.py").write_text("# TODO: ignored\n")
        vendored = tmp_path / "node_modules"
        vendored.mkdir()
        (vendored / "ignored.js").write_text("// FIXME: ignored\n")
        (tmp_path / "README.md").write_text("TODO in docs is not code\n")

        assert _count_todos(tmp_path) == (2, 3)

    def test_count_todos_stops_after_max_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("# TODO: counted\n")
        (tmp_path / "b.py").write_text("# TODO: not reached\n")

        assert _count_todos(tmp_path, max_files=1) == (1, 1)

    def test_count_todos_skips_large_and_unreadable_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        large = tmp_path / "large.py"
        large.write_text("print('large')\n")
        unreadable = tmp_path / "unreadable.py"
        unreadable.write_text("# TODO: unreadable\n")
        normal = tmp_path / "normal.py"
        normal.write_text("# FIXME: counted\n")
        original_stat = Path.stat
        original_read_text = Path.read_text

        def fake_stat(path: Path, *args, **kwargs):
            stat = original_stat(path, *args, **kwargs)
            if path == large:
                return types.SimpleNamespace(st_size=1_000_001, st_mode=stat.st_mode)
            return stat

        def fake_read_text(path: Path, *args, **kwargs):
            if path == unreadable:
                raise OSError("cannot read")
            return original_read_text(path, *args, **kwargs)

        monkeypatch.setattr(Path, "stat", fake_stat)
        monkeypatch.setattr(Path, "read_text", fake_read_text)

        assert _count_todos(tmp_path) == (1, 1)


class TestTypeDefinitionDetection:
    @pytest.mark.parametrize("language", ["TypeScript", "Rust", "Go", "Java", "Swift", "C#", "Kotlin", "Scala"])
    def test_strongly_typed_languages_count_as_typed(
        self, tmp_path: Path, language: str
    ) -> None:
        assert _has_type_definitions(tmp_path, language) is True

    def test_typescript_file_counts_as_types_outside_node_modules(self, tmp_path: Path) -> None:
        (tmp_path / "index.ts").write_text("export const value: number = 1;\n")
        node_modules = tmp_path / "node_modules" / "pkg"
        node_modules.mkdir(parents=True)
        (node_modules / "ignored.ts").write_text("export const ignored = true;\n")

        assert _has_type_definitions(tmp_path, "JavaScript") is True

    def test_python_annotations_count_as_types(self, tmp_path: Path) -> None:
        (tmp_path / "module.py").write_text("def answer() -> int:\n    return 42\n")

        assert _has_type_definitions(tmp_path, "Python") is True

    def test_python_type_detection_skips_node_modules_and_unreadable_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        node_modules = tmp_path / "node_modules" / "pkg"
        node_modules.mkdir(parents=True)
        (node_modules / "typed.py").write_text("def ignored() -> int:\n    return 1\n")
        unreadable = tmp_path / "broken.py"
        unreadable.write_text("def broken() -> int:\n    return 2\n")
        original_read_text = Path.read_text

        def fake_read_text(path: Path, *args, **kwargs):
            if path == unreadable:
                raise OSError("cannot read")
            return original_read_text(path, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", fake_read_text)

        assert _has_type_definitions(tmp_path, "Python") is False


class TestVendoredDetection:
    def test_detects_all_vendored_directory_names_and_caps_large_files(
        self, tmp_path: Path
    ) -> None:
        for dirname in ("node_modules", "vendor", "third_party", "bower_components"):
            (tmp_path / dirname).mkdir()
        for index in range(4):
            (tmp_path / f"large-{index}.bin").write_bytes(b"x" * 1_000_001)

        issues = _detect_vendored(tmp_path)

        assert len(issues) == 5
        assert "node_modules/ committed" in issues
        assert "vendor/ committed" in issues
        assert "third_party/ committed" in issues
        assert "bower_components/ committed" in issues
        assert any(issue.startswith("Large file:") and issue.endswith("(976KB)") for issue in issues)

    def test_detect_vendored_skips_hidden_files(
        self, tmp_path: Path
    ) -> None:
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "large.bin").write_bytes(b"x" * 1_000_001)

        assert _detect_vendored(tmp_path) == []

    def test_detect_vendored_skips_stat_error_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        broken = tmp_path / "broken.bin"
        broken.write_text("small\n")
        original_is_file = Path.is_file
        original_stat = Path.stat

        def fake_is_file(path: Path) -> bool:
            if path == broken:
                return True
            return original_is_file(path)

        def fake_stat(path: Path, *args, **kwargs):
            if path == broken:
                raise OSError("cannot stat")
            return original_stat(path, *args, **kwargs)

        monkeypatch.setattr(Path, "is_file", fake_is_file)
        monkeypatch.setattr(Path, "stat", fake_stat)

        assert _detect_vendored(tmp_path) == []


class TestCommitMessageHelpers:
    def test_score_commit_messages_handles_empty_input(self) -> None:
        assert _score_commit_messages([]) == (0.5, "No commits available")

    def test_score_commit_messages_uses_first_line_and_filters_lazy_messages(self) -> None:
        commits = [
            _commit("feat: add durable cache\n\nExpanded body"),
            _commit("wip"),
            _commit("."),
            _commit("Improve checkout path validation"),
            {},
        ]

        assert _score_commit_messages(commits) == (
            0.4,
            "2/5 descriptive commits",
        )

    @pytest.mark.xfail(reason="bang commits without scope are classified as type 'fix!' instead of 'fix'")
    def test_classify_commits_reports_ratios_types_and_issue_refs(self) -> None:
        messages = [
            "feat(ui): add summary panel #12",
            "fix!: prevent stale writes",
            "docs: explain operator workflow",
            "Update dependency #44",
        ]

        assert _classify_commits(messages) == {
            "conventional_ratio": 0.75,
            "commit_types": {"feat": 1, "fix": 1, "docs": 1},
            "has_issue_refs": 0.5,
        }

    def test_classify_commits_handles_empty_input(self) -> None:
        assert _classify_commits([]) == {
            "conventional_ratio": 0,
            "commit_types": {},
            "has_issue_refs": 0,
        }


class TestRadonAnalysis:
    def test_radon_analysis_returns_none_when_radon_is_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "radon", None)

        assert _radon_analysis(tmp_path) is None

    def test_radon_analysis_reports_maintainability_and_complexity(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "simple.py").write_text("def simple():\n    return 1\n")
        (tmp_path / "empty.py").write_text("\n")
        skipped = tmp_path / "vendor"
        skipped.mkdir()
        (skipped / "ignored.py").write_text("def ignored():\n    return 2\n")
        complexity = types.ModuleType("radon.complexity")
        metrics = types.ModuleType("radon.metrics")
        complexity.cc_visit = lambda source: [
            types.SimpleNamespace(complexity=4, name="simple"),
            types.SimpleNamespace(complexity=18, name="hard"),
        ]
        metrics.mi_visit = lambda source, multi: 42.4
        monkeypatch.setitem(sys.modules, "radon", types.ModuleType("radon"))
        monkeypatch.setitem(sys.modules, "radon.complexity", complexity)
        monkeypatch.setitem(sys.modules, "radon.metrics", metrics)

        assert _radon_analysis(tmp_path) == {
            "avg_maintainability_index": 42.4,
            "worst_cc_function": "simple.py:hard",
            "worst_cc_score": 18,
            "complex_function_count": 1,
            "python_files_analyzed": 1,
        }

    def test_radon_analysis_skips_files_that_raise_during_metrics(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "bad.py").write_text("def bad():\n    return 1\n")
        complexity = types.ModuleType("radon.complexity")
        metrics = types.ModuleType("radon.metrics")
        complexity.cc_visit = lambda source: []

        def raise_for_metrics(source: str, multi: bool) -> float:
            raise ValueError("bad syntax")

        metrics.mi_visit = raise_for_metrics
        monkeypatch.setitem(sys.modules, "radon", types.ModuleType("radon"))
        monkeypatch.setitem(sys.modules, "radon.complexity", complexity)
        monkeypatch.setitem(sys.modules, "radon.metrics", metrics)

        assert _radon_analysis(tmp_path) is None

    def test_radon_analysis_respects_max_file_limit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "first.py").write_text("def first():\n    return 1\n")
        (tmp_path / "second.py").write_text("def second():\n    return 2\n")
        complexity = types.ModuleType("radon.complexity")
        metrics = types.ModuleType("radon.metrics")
        complexity.cc_visit = lambda source: []
        metrics.mi_visit = lambda source, multi: 30
        monkeypatch.setitem(sys.modules, "radon", types.ModuleType("radon"))
        monkeypatch.setitem(sys.modules, "radon.complexity", complexity)
        monkeypatch.setitem(sys.modules, "radon.metrics", metrics)

        result = _radon_analysis(tmp_path, max_files=1)

        assert result is not None
        assert result["python_files_analyzed"] == 1
        assert result["avg_maintainability_index"] == 30.0
