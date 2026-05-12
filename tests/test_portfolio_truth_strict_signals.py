"""Tests for Arc G Sprint 8.2 strict signals in portfolio-truth derived block.

Covers has_tests, has_ci, readme_char_count, and opt-in release_count.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from src.portfolio_truth_reconcile import (
    _derive_has_ci,
    _derive_has_tests,
    _derive_readme_char_count,
)

# ── Helpers ─────────────────────────────────────────────────────────────────


def _make_project(tmp_path: Path) -> Path:
    """Return a project root with a .git marker so has_git=True."""
    (tmp_path / ".git").mkdir()
    return tmp_path


# ── has_tests ────────────────────────────────────────────────────────────────


def test_has_tests_with_tests_directory(tmp_path: Path) -> None:
    """Project with a tests/ directory → has_tests == True."""
    proj = _make_project(tmp_path)
    (proj / "tests").mkdir()
    (proj / "tests" / "test_foo.py").write_text("# test")
    assert _derive_has_tests(proj, has_git=True) is True


def test_has_tests_with_test_file_no_dir(tmp_path: Path) -> None:
    """Project with only test_foo.py (no tests/ dir) → has_tests == True."""
    proj = _make_project(tmp_path)
    (proj / "test_foo.py").write_text("# test")
    assert _derive_has_tests(proj, has_git=True) is True


def test_has_tests_no_test_files(tmp_path: Path) -> None:
    """Project with no test files → has_tests == False."""
    proj = _make_project(tmp_path)
    (proj / "src").mkdir()
    (proj / "src" / "main.py").write_text("print('hello')")
    assert _derive_has_tests(proj, has_git=True) is False


def test_has_tests_false_when_no_git(tmp_path: Path) -> None:
    """Project where has_git == False → has_tests == False."""
    # Even if test files exist, no-git means we return False
    (tmp_path / "tests").mkdir()
    assert _derive_has_tests(tmp_path, has_git=False) is False


def test_has_tests_false_when_path_nonexistent(tmp_path: Path) -> None:
    """Project where path doesn't exist → has_tests == False without crashing."""
    missing = tmp_path / "nonexistent_project"
    assert _derive_has_tests(missing, has_git=True) is False


def test_has_tests_swift_test_file(tmp_path: Path) -> None:
    """Project with a *Tests.swift file → has_tests == True."""
    proj = _make_project(tmp_path)
    (proj / "MyAppTests.swift").write_text("// swift test")
    assert _derive_has_tests(proj, has_git=True) is True


# ── has_ci ───────────────────────────────────────────────────────────────────


def test_has_ci_with_workflow_yml(tmp_path: Path) -> None:
    """Project with .github/workflows/ci.yml → has_ci == True."""
    proj = _make_project(tmp_path)
    workflows = proj / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("name: CI\n")
    assert _derive_has_ci(proj, has_git=True) is True


def test_has_ci_empty_workflows_dir(tmp_path: Path) -> None:
    """Project with empty .github/ (no yml files) → has_ci == False."""
    proj = _make_project(tmp_path)
    (proj / ".github").mkdir()
    assert _derive_has_ci(proj, has_git=True) is False


def test_has_ci_false_when_no_git(tmp_path: Path) -> None:
    """Project where has_git == False → has_ci == False."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("name: CI\n")
    assert _derive_has_ci(tmp_path, has_git=False) is False


def test_has_ci_false_when_path_nonexistent(tmp_path: Path) -> None:
    """Project where path doesn't exist → has_ci == False without crashing."""
    missing = tmp_path / "nonexistent_project"
    assert _derive_has_ci(missing, has_git=True) is False


# ── readme_char_count ────────────────────────────────────────────────────────


def test_readme_char_count_present(tmp_path: Path) -> None:
    """Project with README.md of length 250 chars → readme_char_count == 250."""
    proj = _make_project(tmp_path)
    content = "x" * 250
    (proj / "README.md").write_text(content)
    assert _derive_readme_char_count(proj, has_git=True) == 250


def test_readme_char_count_no_readme(tmp_path: Path) -> None:
    """Project with no README → readme_char_count == 0."""
    proj = _make_project(tmp_path)
    assert _derive_readme_char_count(proj, has_git=True) == 0


def test_readme_char_count_false_when_no_git(tmp_path: Path) -> None:
    """Project where has_git == False → readme_char_count == 0."""
    (tmp_path / "README.md").write_text("hello")
    assert _derive_readme_char_count(tmp_path, has_git=False) == 0


def test_readme_char_count_false_when_path_nonexistent(tmp_path: Path) -> None:
    """Project where path doesn't exist → readme_char_count == 0 without crashing."""
    missing = tmp_path / "nonexistent_project"
    assert _derive_readme_char_count(missing, has_git=True) == 0


def test_readme_char_count_non_utf8_bytes(tmp_path: Path) -> None:
    """README with non-UTF-8 bytes → doesn't crash; chars counted via replacement."""
    proj = _make_project(tmp_path)
    readme = proj / "README.md"
    # Write bytes that are invalid UTF-8
    readme.write_bytes(b"Hello \xff\xfe world")
    count = _derive_readme_char_count(proj, has_git=True)
    # Should not raise and should return a positive integer
    assert isinstance(count, int)
    assert count > 0


# ── release_count (opt-in, via audit JSON overlay) ───────────────────────────


def _make_audit_json(tmp_path: Path, username: str, repo_name: str, release_count: int) -> Path:
    """Create a minimal audit-report JSON with one repo entry."""
    audit_data = {
        "schema_version": "3.7",
        "username": username,
        "audits": [
            {
                "metadata": {"name": repo_name},
                "analyzer_results": [
                    {
                        "dimension": "activity",
                        "score": 0.5,
                        "details": {
                            "days_since_push": 10,
                            "release_count": release_count,
                        },
                    }
                ],
            }
        ],
    }
    path = tmp_path / f"audit-report-{username}-2026-05-11.json"
    path.write_text(json.dumps(audit_data))
    return path


def test_release_count_loaded_from_audit_json(tmp_path: Path) -> None:
    """--portfolio-truth-include-release-count with valid audit JSON → release_count == 3."""
    from src.cli import _load_release_count_by_name

    _make_audit_json(tmp_path, username="saagpatel", repo_name="MyRepo", release_count=3)
    result = _load_release_count_by_name(output_dir=tmp_path, username="saagpatel")
    assert result is not None
    assert result.get("MyRepo") == 3


def test_release_count_no_audit_json_returns_none(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """--portfolio-truth-include-release-count with no audit JSON → None returned, warning logged."""
    from src.cli import _load_release_count_by_name

    with caplog.at_level(logging.WARNING):
        result = _load_release_count_by_name(output_dir=tmp_path, username="saagpatel")

    assert result is None
    assert any("prior audit run" in record.message for record in caplog.records)


def test_release_count_absent_for_missing_project(tmp_path: Path) -> None:
    """Project not in the audit report → release_count key absent from returned dict."""
    from src.cli import _load_release_count_by_name

    _make_audit_json(tmp_path, username="saagpatel", repo_name="KnownRepo", release_count=5)
    result = _load_release_count_by_name(output_dir=tmp_path, username="saagpatel")
    assert result is not None
    assert "UnknownRepo" not in result
    assert result.get("KnownRepo") == 5
