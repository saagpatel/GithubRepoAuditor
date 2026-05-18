from __future__ import annotations

import json
from pathlib import Path

from src.history import archive_report, find_previous, load_complexity_trends, load_history_index


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


def _make_report_with_code_quality(
    repo_name: str,
    mi: float,
    worst_cc: int = 5,
    complex_count: int = 2,
) -> dict:
    return {
        "generated_at": "2026-03-25T00:00:00+00:00",
        "repos_audited": 1,
        "average_score": 0.6,
        "tier_distribution": {},
        "audits": [
            {
                "metadata": {"name": repo_name},
                "overall_score": 0.6,
                "analyzer_results": [
                    {
                        "dimension": "code_quality",
                        "score": 0.7,
                        "details": {
                            "avg_maintainability_index": mi,
                            "worst_cc_score": worst_cc,
                            "complex_function_count": complex_count,
                        },
                    }
                ],
            }
        ],
    }


class TestLoadComplexityTrends:
    def _setup_history(self, tmp_path: Path, reports: list[dict]) -> Path:
        """Write reports into a history dir with an index and return output_dir."""
        output_dir = tmp_path / "output"
        history_dir = output_dir / "history"
        history_dir.mkdir(parents=True)

        index = []
        for i, report_data in enumerate(reports):
            filename = f"audit-report-user-2026-03-{20 + i:02d}.json"
            report_path = history_dir / filename
            report_path.write_text(json.dumps(report_data))
            index.append({
                "filename": filename,
                "generated_at": report_data["generated_at"],
            })

        (history_dir / "index.json").write_text(json.dumps(index))
        return output_dir

    def test_returns_empty_when_no_history(self, tmp_path: Path) -> None:
        result = load_complexity_trends(tmp_path / "output")
        assert result == {}

    def test_returns_empty_when_no_code_quality_dimension(self, tmp_path: Path) -> None:
        report = {
            "generated_at": "2026-03-25T00:00:00+00:00",
            "audits": [
                {
                    "metadata": {"name": "repo"},
                    "analyzer_results": [
                        {"dimension": "testing", "score": 0.5, "details": {}}
                    ],
                }
            ],
        }
        output_dir = self._setup_history(tmp_path, [report])
        result = load_complexity_trends(output_dir)
        assert result == {}

    def test_collects_mi_for_single_repo(self, tmp_path: Path) -> None:
        report = _make_report_with_code_quality("my-repo", mi=72.5, worst_cc=8, complex_count=3)
        output_dir = self._setup_history(tmp_path, [report])
        result = load_complexity_trends(output_dir)

        assert "my-repo" in result
        assert len(result["my-repo"]) == 1
        entry = result["my-repo"][0]
        assert entry["mi"] == 72.5
        assert entry["worst_cc"] == 8
        assert entry["complex_count"] == 3

    def test_accumulates_across_multiple_runs(self, tmp_path: Path) -> None:
        reports = [
            _make_report_with_code_quality("repo", mi=80.0),
            _make_report_with_code_quality("repo", mi=75.0),
            _make_report_with_code_quality("repo", mi=70.0),
        ]
        output_dir = self._setup_history(tmp_path, reports)
        result = load_complexity_trends(output_dir)

        assert "repo" in result
        mis = [e["mi"] for e in result["repo"]]
        assert mis == [80.0, 75.0, 70.0]

    def test_handles_missing_report_file(self, tmp_path: Path) -> None:
        """Index entry pointing to a non-existent file should be silently skipped."""
        output_dir = tmp_path / "output"
        history_dir = output_dir / "history"
        history_dir.mkdir(parents=True)
        index = [{"filename": "audit-report-ghost.json", "generated_at": "2026-03-25T00:00:00+00:00"}]
        (history_dir / "index.json").write_text(json.dumps(index))

        result = load_complexity_trends(output_dir)
        assert result == {}

    def test_handles_corrupt_report_file(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "output"
        history_dir = output_dir / "history"
        history_dir.mkdir(parents=True)
        bad_file = history_dir / "audit-report-bad.json"
        bad_file.write_text("not json {{{")
        index = [{"filename": "audit-report-bad.json", "generated_at": "2026-03-25T00:00:00+00:00"}]
        (history_dir / "index.json").write_text(json.dumps(index))

        result = load_complexity_trends(output_dir)
        assert result == {}

    def test_skips_audit_without_mi(self, tmp_path: Path) -> None:
        """code_quality result with no avg_maintainability_index should be skipped."""
        report = {
            "generated_at": "2026-03-25T00:00:00+00:00",
            "audits": [
                {
                    "metadata": {"name": "repo"},
                    "analyzer_results": [
                        {"dimension": "code_quality", "score": 0.5, "details": {"worst_cc_score": 3}}
                    ],
                }
            ],
        }
        output_dir = self._setup_history(tmp_path, [report])
        result = load_complexity_trends(output_dir)
        assert result == {}
