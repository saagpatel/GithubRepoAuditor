from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.implementation_hotspots import build_implementation_hotspots
from src.models import AnalyzerResult, RepoAudit, RepoMetadata


def _metadata() -> RepoMetadata:
    return RepoMetadata(
        name="sample",
        full_name="user/sample",
        description="sample",
        language="Python",
        languages={"Python": 2000},
        private=False,
        fork=False,
        archived=False,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        pushed_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        default_branch="main",
        stars=0,
        forks=0,
        open_issues=0,
        size_kb=10,
        html_url="https://github.com/user/sample",
        clone_url="",
        topics=[],
    )


def _audit(*, dependency_details: dict | None = None, code_quality_details: dict | None = None, structure_details: dict | None = None, testing_score: float = 0.5) -> RepoAudit:
    return RepoAudit(
        metadata=_metadata(),
        analyzer_results=[
            AnalyzerResult("dependencies", 0.4, 1.0, [], dependency_details or {"manifests": [], "lockfiles": [], "dep_count": 0}),
            AnalyzerResult("code_quality", 0.45, 1.0, [], code_quality_details or {"entry_point": "main.py", "total_loc": 100}),
            AnalyzerResult("structure", 0.5, 1.0, [], structure_details or {"source_dirs": ["src"], "config_files": ["pyproject.toml"]}),
            AnalyzerResult("testing", testing_score, 1.0, [], {}),
        ],
        overall_score=0.5,
        completeness_tier="functional",
        lenses={"ship_readiness": {"score": 0.5}},
        security_posture={"score": 0.7, "secrets_found": 0, "dangerous_files": []},
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_python_complexity_hotspot_scoring(tmp_path: Path):
    _write(
        tmp_path / "src" / "core.py",
        """
def tangled(a, b, c, d):
    total = 0
    for item in [a, b, c, d]:
        if item > 0:
            total += item
            if item % 2 == 0:
                total += 1
            else:
                total -= 1
        elif item == 0:
            total += 2
        else:
            try:
                total += abs(item)
            except Exception:
                total += 3
    return total
""",
    )

    hotspots = build_implementation_hotspots(tmp_path, _audit())

    assert any(item["category"] == "code-complexity" for item in hotspots)
    assert any(item["suggestion_type"] == "refactor" for item in hotspots)


def test_todo_density_hotspot_scoring(tmp_path: Path):
    _write(
        tmp_path / "src" / "notes.py",
        "\n".join(
            [
                "# TODO: tighten validation",
                "# FIXME: remove fallback",
                "# TODO: add tests",
                "def run():",
                "    return True",
            ]
        ),
    )

    hotspots = build_implementation_hotspots(tmp_path, _audit())

    assert any(item["category"] == "todo-density" for item in hotspots)


def test_security_file_hotspot_scoring(tmp_path: Path):
    _write(tmp_path / ".env", "SECRET_KEY='super-secret-value'\n")

    hotspots = build_implementation_hotspots(tmp_path, _audit())

    assert any(item["category"] == "security-exposure" for item in hotspots)
    assert any(item["suggestion_type"] == "security" for item in hotspots)


def test_dependency_fragility_hotspot_scoring(tmp_path: Path):
    _write(tmp_path / "package.json", '{"dependencies":{"a":"1","b":"1"}}')

    hotspots = build_implementation_hotspots(
        tmp_path,
        _audit(dependency_details={"manifests": ["package.json"], "lockfiles": [], "dep_count": 180}),
    )

    assert any(item["category"] == "dependency-fragility" for item in hotspots)
    assert any(item["path"] == "package.json" for item in hotspots)


def test_module_aggregation_from_multiple_file_signals(tmp_path: Path):
    _write(
        tmp_path / "src" / "a.py",
        """
def alpha(x):
    if x > 0:
        if x > 1:
            if x > 2:
                if x > 3:
                    return x
                return x - 1
            elif x == 2:
                return x + 2
            else:
                return x + 1
        elif x == 1:
            return x
        else:
            return 0
    elif x == 0:
        return 0
    else:
        return abs(x)
    return 0
""",
    )
    _write(
        tmp_path / "src" / "b.py",
        "# TODO: clean this up\n# FIXME: split this module\n\ndef beta():\n    return True\n",
    )

    hotspots = build_implementation_hotspots(tmp_path, _audit())

    assert any(item["scope"] == "module" and item["module"] == "src" for item in hotspots)


def test_scan_caps_skip_dirs_and_large_files(tmp_path: Path):
    _write(
        tmp_path / "node_modules" / "ignored.py",
        "# TODO: should be ignored\n" * 20,
    )
    huge_file = tmp_path / "src" / "huge.py"
    huge_file.parent.mkdir(parents=True, exist_ok=True)
    huge_file.write_text("# TODO: too large to scan\n" * 70000)
    _write(tmp_path / "src" / "real.py", "# TODO: keep me\n# FIXME: still real\n\ndef run():\n    return True\n")

    hotspots = build_implementation_hotspots(tmp_path, _audit())
    paths = {item["path"] for item in hotspots}

    assert "node_modules/ignored.py" not in paths
    assert "src/huge.py" not in paths
    assert any(path == "src/real.py" for path in paths)
