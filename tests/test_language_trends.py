from __future__ import annotations

import json
from pathlib import Path

from src.history import load_language_trends


def _write_report(tmp_path: Path, name: str, audits: list[dict]) -> None:
    report = {"audits": audits}
    (tmp_path / name).write_text(json.dumps(report))


def _audit(repo_name: str, language: str) -> dict:
    return {"metadata": {"name": repo_name, "language": language}}


class TestLanguageTrends:
    def test_empty_history(self, tmp_path):
        assert load_language_trends(tmp_path) == []

    def test_single_run(self, tmp_path):
        _write_report(tmp_path, "audit-report-test-2026-01-01.json", [
            _audit("repo1", "Python"),
            _audit("repo2", "Python"),
            _audit("repo3", "Rust"),
        ])
        trends = load_language_trends(tmp_path)
        assert len(trends) == 2
        python = next(t for t in trends if t["language"] == "Python")
        assert python["current_count"] == 2

    def test_growing_language_is_adopt(self, tmp_path):
        _write_report(tmp_path, "audit-report-test-2026-01-01.json", [
            _audit("repo1", "Rust"),
        ])
        _write_report(tmp_path, "audit-report-test-2026-02-01.json", [
            _audit("repo1", "Rust"),
            _audit("repo2", "Rust"),
            _audit("repo3", "Rust"),
        ])
        trends = load_language_trends(tmp_path)
        rust = next(t for t in trends if t["language"] == "Rust")
        assert rust["category"] == "Adopt"

    def test_stable_language_is_hold(self, tmp_path):
        _write_report(tmp_path, "audit-report-test-2026-01-01.json", [
            _audit("repo1", "Python"),
            _audit("repo2", "Python"),
        ])
        _write_report(tmp_path, "audit-report-test-2026-02-01.json", [
            _audit("repo1", "Python"),
            _audit("repo2", "Python"),
        ])
        trends = load_language_trends(tmp_path)
        py = next(t for t in trends if t["language"] == "Python")
        assert py["category"] == "Hold"

    def test_sorted_by_count(self, tmp_path):
        _write_report(tmp_path, "audit-report-test-2026-01-01.json", [
            _audit("r1", "Python"),
            _audit("r2", "Python"),
            _audit("r3", "Python"),
            _audit("r4", "Rust"),
        ])
        trends = load_language_trends(tmp_path)
        assert trends[0]["language"] == "Python"
        assert trends[1]["language"] == "Rust"
