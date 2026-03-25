from __future__ import annotations

import json
from pathlib import Path

from src.history import archive_report, find_previous, load_history_index


class TestArchive:
    def test_archives_report(self, tmp_path):
        history_dir = tmp_path / "history"
        report = tmp_path / "audit-report-user-2026-03-25.json"
        report.write_text(json.dumps({
            "generated_at": "2026-03-25T00:00:00+00:00",
            "repos_audited": 10,
            "average_score": 0.5,
            "tier_distribution": {"shipped": 5, "wip": 5},
        }))

        archived = archive_report(report, history_dir)
        assert archived.exists()
        assert archived.parent == history_dir

    def test_creates_index(self, tmp_path):
        history_dir = tmp_path / "history"
        report = tmp_path / "audit-report-user-2026-03-25.json"
        report.write_text(json.dumps({
            "generated_at": "2026-03-25T00:00:00+00:00",
            "repos_audited": 10,
            "average_score": 0.5,
            "tier_distribution": {},
        }))

        archive_report(report, history_dir)
        index = load_history_index(history_dir)
        assert len(index) == 1
        assert index[0]["repos_audited"] == 10


class TestFindPrevious:
    def test_finds_older_report(self, tmp_path):
        history_dir = tmp_path / "history"
        history_dir.mkdir()

        # Create two archived reports
        old = history_dir / "audit-report-user-2026-03-20.json"
        old.write_text("{}")

        result = find_previous("audit-report-user-2026-03-25.json", history_dir)
        assert result is not None
        assert result.name == "audit-report-user-2026-03-20.json"

    def test_returns_none_on_empty(self, tmp_path):
        result = find_previous("audit-report-user-2026-03-25.json", tmp_path / "empty")
        assert result is None

    def test_excludes_current_report(self, tmp_path):
        history_dir = tmp_path / "history"
        history_dir.mkdir()
        current = history_dir / "audit-report-user-2026-03-25.json"
        current.write_text("{}")

        result = find_previous("audit-report-user-2026-03-25.json", history_dir)
        assert result is None
