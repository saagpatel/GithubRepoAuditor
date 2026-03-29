from __future__ import annotations

from src.archive_candidates import find_archive_candidates, export_archive_report


class TestFindArchiveCandidates:
    def test_below_threshold_3_runs(self):
        history = {"BadRepo": [0.10, 0.08, 0.05]}
        candidates = find_archive_candidates(history)
        assert len(candidates) == 1
        assert candidates[0]["name"] == "BadRepo"

    def test_above_threshold_excluded(self):
        history = {"GoodRepo": [0.50, 0.55, 0.60]}
        candidates = find_archive_candidates(history)
        assert len(candidates) == 0

    def test_mixed_scores_excluded(self):
        history = {"MixedRepo": [0.10, 0.30, 0.05]}
        candidates = find_archive_candidates(history)
        assert len(candidates) == 0

    def test_too_few_runs(self):
        history = {"NewRepo": [0.05, 0.03]}
        candidates = find_archive_candidates(history)
        assert len(candidates) == 0

    def test_sorted_by_score(self):
        history = {
            "WorstRepo": [0.01, 0.02, 0.01],
            "BadRepo": [0.10, 0.12, 0.11],
        }
        candidates = find_archive_candidates(history)
        assert candidates[0]["name"] == "WorstRepo"

    def test_custom_threshold(self):
        history = {"MidRepo": [0.20, 0.22, 0.18]}
        assert len(find_archive_candidates(history, threshold=0.15)) == 0
        assert len(find_archive_candidates(history, threshold=0.25)) == 1


class TestExportArchiveReport:
    def test_creates_file(self, tmp_path):
        candidates = [{"name": "OldRepo", "last_scores": [0.05, 0.03, 0.02], "current_score": 0.02}]
        result = export_archive_report(candidates, "testuser", tmp_path)
        assert result["report_path"].is_file()
        assert result["count"] == 1

    def test_empty_candidates(self, tmp_path):
        result = export_archive_report([], "testuser", tmp_path)
        content = result["report_path"].read_text()
        assert "No repos" in content

    def test_contains_gh_command(self, tmp_path):
        candidates = [{"name": "OldRepo", "last_scores": [0.05], "current_score": 0.05}]
        result = export_archive_report(candidates, "testuser", tmp_path)
        content = result["report_path"].read_text()
        assert "gh repo edit" in content
