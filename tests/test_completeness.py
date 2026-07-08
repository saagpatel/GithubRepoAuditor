from __future__ import annotations

from pathlib import Path

from src.analyzers.completeness import (
    BuildReadinessAnalyzer,
    DocumentationAnalyzer,
    _sample_comment_density,
)


def test_documentation_analyzer_scores_complete_documentation(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "CHANGELOG.md").write_text("## 1.0\n", encoding="utf-8")
    (tmp_path / "CONTRIBUTING.md").write_text("# Contributing\n", encoding="utf-8")
    (tmp_path / "module.py").write_text(
        "# module notes\n"
        "# implementation note\n"
        "def answer():\n"
        "    return 42\n",
        encoding="utf-8",
    )

    result = DocumentationAnalyzer().analyze(tmp_path, metadata=None)

    assert result.dimension == "documentation"
    assert result.score == 1.0
    assert result.findings == [
        "Has docs/ directory",
        "Has CHANGELOG",
        "Has CONTRIBUTING guide",
        "Comment density: 50%",
    ]
    assert result.details == {"comment_ratio": 0.5}


def test_build_readiness_analyzer_scores_available_build_artifacts(tmp_path: Path) -> None:
    (tmp_path / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (tmp_path / "justfile").write_text("test:\n  pytest\n", encoding="utf-8")
    (tmp_path / ".env.sample").write_text("TOKEN=\n", encoding="utf-8")
    (tmp_path / "vercel.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "Procfile").write_text("web: python app.py\n", encoding="utf-8")

    result = BuildReadinessAnalyzer().analyze(tmp_path, metadata=None)

    assert result.dimension == "build_readiness"
    assert result.score == 1.0
    assert result.findings == [
        "Docker: Dockerfile, docker-compose.yml",
        "Has justfile",
        "Environment template: .env.sample",
        "Deploy config: vercel.json, Procfile",
    ]
    assert result.details == {
        "docker": ["Dockerfile", "docker-compose.yml"],
        "deploy_configs": ["vercel.json", "Procfile"],
    }


def test_analyzers_report_missing_documentation_and_build_artifacts(tmp_path: Path) -> None:
    documentation = DocumentationAnalyzer().analyze(tmp_path, metadata=None)
    build_readiness = BuildReadinessAnalyzer().analyze(tmp_path, metadata=None)

    assert documentation.score == 0.0
    assert documentation.findings == [
        "No docs/ directory",
        "No CHANGELOG",
        "No CONTRIBUTING guide",
        "Could not assess comment density",
    ]
    assert documentation.details == {"comment_ratio": None}
    assert build_readiness.score == 0.0
    assert build_readiness.findings == [
        "No Docker configuration",
        "No Makefile or build script",
        "No .env.example",
        "No deployment configuration",
    ]
    assert build_readiness.details == {"deploy_configs": []}


def test_sample_comment_density_skips_binary_hidden_node_and_oversized_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "image.png").write_bytes(b"binary")
    hidden_dir = tmp_path / ".github"
    hidden_dir.mkdir()
    (hidden_dir / "workflow.yml").write_text("# skipped\nname: ci\n", encoding="utf-8")
    node_dir = tmp_path / "node_modules"
    node_dir.mkdir()
    (node_dir / "package.js").write_text("// skipped\nconst x = 1;\n", encoding="utf-8")
    oversized = tmp_path / "generated.py"
    oversized.write_text("# skipped\nvalue = 1\n", encoding="utf-8")
    kept = tmp_path / "kept.py"
    kept.write_text("# counted\nvalue = 1\n", encoding="utf-8")

    original_stat = Path.stat

    def fake_stat(path: Path, *args, **kwargs):
        stat_result = original_stat(path, *args, **kwargs)
        if path == oversized:
            return type(
                "FakeStat",
                (),
                {"st_mode": stat_result.st_mode, "st_size": 1_000_001},
            )()
        return stat_result

    monkeypatch.setattr(Path, "stat", fake_stat)

    assert _sample_comment_density(tmp_path) == 0.5


def test_sample_comment_density_ignores_stat_and_read_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stat_error = tmp_path / "stat_error.py"
    stat_error.write_text("# skipped before sample\nvalue = 1\n", encoding="utf-8")
    read_error = tmp_path / "read_error.py"
    read_error.write_text("# skipped while sampled\nvalue = 1\n", encoding="utf-8")
    kept = tmp_path / "kept.js"
    kept.write_text("// counted\nconst value = 1;\n", encoding="utf-8")

    original_stat = Path.stat
    original_is_file = Path.is_file
    original_read_text = Path.read_text

    def fake_is_file(path: Path) -> bool:
        if path == stat_error:
            return True
        return original_is_file(path)

    def fake_stat(path: Path, *args, **kwargs):
        if path == stat_error:
            raise OSError("stat failed")
        return original_stat(path, *args, **kwargs)

    def fake_read_text(path: Path, *args, **kwargs):
        if path == read_error:
            raise OSError("read failed")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "is_file", fake_is_file)
    monkeypatch.setattr(Path, "stat", fake_stat)
    monkeypatch.setattr(Path, "read_text", fake_read_text)

    assert _sample_comment_density(tmp_path) == 0.5
