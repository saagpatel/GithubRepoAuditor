"""Tests for audit progress persistence (save/load/clear)."""
from __future__ import annotations

from pathlib import Path

from src.progress import PROGRESS_FILE, clear_progress, load_progress, save_progress


def _sample_audits() -> list[dict]:
    return [
        {"metadata": {"name": "repo-a"}, "overall_score": 0.75},
        {"metadata": {"name": "repo-b"}, "overall_score": 0.50},
    ]


def _sample_metadata() -> dict:
    return {"username": "testuser", "started_at": "2026-03-29T00:00:00+00:00"}


class TestSaveProgress:
    def test_creates_progress_file(self, tmp_path: Path) -> None:
        save_progress(tmp_path, _sample_audits(), _sample_metadata())
        assert (tmp_path / PROGRESS_FILE).is_file()

    def test_creates_output_dir_if_missing(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "output"
        save_progress(target, [], {})
        assert (target / PROGRESS_FILE).is_file()

    def test_no_tmp_file_left_behind(self, tmp_path: Path) -> None:
        save_progress(tmp_path, _sample_audits(), _sample_metadata())
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == []

    def test_overwrites_existing_progress(self, tmp_path: Path) -> None:
        save_progress(tmp_path, _sample_audits(), _sample_metadata())
        save_progress(tmp_path, [_sample_audits()[0]], {"run": 2})
        result = load_progress(tmp_path)
        assert result is not None
        completed, meta = result
        assert len(completed) == 1
        assert meta["run"] == 2


class TestLoadProgress:
    def test_returns_none_when_no_file(self, tmp_path: Path) -> None:
        result = load_progress(tmp_path)
        assert result is None

    def test_returns_correct_data_after_save(self, tmp_path: Path) -> None:
        audits = _sample_audits()
        meta = _sample_metadata()
        save_progress(tmp_path, audits, meta)

        result = load_progress(tmp_path)
        assert result is not None
        completed, run_meta = result
        assert len(completed) == 2
        assert completed[0]["metadata"]["name"] == "repo-a"
        assert run_meta["username"] == "testuser"

    def test_returns_none_on_corrupt_json(self, tmp_path: Path) -> None:
        (tmp_path / PROGRESS_FILE).write_text("NOT VALID JSON {{{")
        result = load_progress(tmp_path)
        assert result is None

    def test_empty_completed_list_round_trips(self, tmp_path: Path) -> None:
        save_progress(tmp_path, [], {"step": "init"})
        result = load_progress(tmp_path)
        assert result is not None
        completed, meta = result
        assert completed == []
        assert meta["step"] == "init"

    def test_preserves_audit_fields(self, tmp_path: Path) -> None:
        audits = [{"metadata": {"name": "x"}, "overall_score": 0.99, "extra": [1, 2]}]
        save_progress(tmp_path, audits, {})
        result = load_progress(tmp_path)
        assert result is not None
        completed, _ = result
        assert completed[0]["extra"] == [1, 2]


class TestClearProgress:
    def test_removes_progress_file(self, tmp_path: Path) -> None:
        save_progress(tmp_path, _sample_audits(), _sample_metadata())
        assert (tmp_path / PROGRESS_FILE).is_file()
        clear_progress(tmp_path)
        assert not (tmp_path / PROGRESS_FILE).is_file()

    def test_no_error_when_file_absent(self, tmp_path: Path) -> None:
        # Should not raise
        clear_progress(tmp_path)

    def test_load_returns_none_after_clear(self, tmp_path: Path) -> None:
        save_progress(tmp_path, _sample_audits(), _sample_metadata())
        clear_progress(tmp_path)
        assert load_progress(tmp_path) is None
