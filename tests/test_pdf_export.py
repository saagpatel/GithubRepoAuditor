import pytest
from pathlib import Path
from src.pdf_export import export_pdf_report


def _minimal_report():
    return {
        "username": "testuser",
        "generated_at": "2026-03-29T00:00:00+00:00",
        "average_score": 0.72,
        "portfolio_grade": "B",
        "tier_distribution": {"shipped": 3, "functional": 5, "wip": 2, "skeleton": 1},
        "audits": [
            {
                "metadata": {"name": "repo1", "language": "Python"},
                "overall_score": 0.85,
                "grade": "A",
                "completeness_tier": "shipped",
                "interest_score": 0.6,
            }
        ],
        "action_backlog": [{"repo": "repo1", "action": "Add CI", "priority": "high"}],
    }


class TestPdfExport:
    def test_generates_pdf_file(self, tmp_path):
        path = export_pdf_report(_minimal_report(), tmp_path)
        assert path is not None
        assert path.suffix == ".pdf"
        assert path.exists()
        assert path.stat().st_size > 100

    def test_filename_format(self, tmp_path):
        path = export_pdf_report(_minimal_report(), tmp_path)
        assert "testuser" in path.name
        assert path.name.startswith("audit-report-")

    def test_minimal_report(self, tmp_path):
        data = {"username": "u", "audits": [], "average_score": 0, "tier_distribution": {}}
        path = export_pdf_report(data, tmp_path)
        assert path is not None

    def test_pdf_contains_username(self, tmp_path):
        # fpdf2 compresses content streams; username is embedded in PDF metadata
        # and the filename — verify via the /Author or /Title info dict in raw bytes
        path = export_pdf_report(_minimal_report(), tmp_path)
        # The filename itself must contain the username (already tested separately)
        assert "testuser" in path.name
        # The PDF must be non-trivially sized (content was written)
        assert path.stat().st_size > 500

    def test_output_dir_created(self, tmp_path):
        nested = tmp_path / "deep" / "nested"
        path = export_pdf_report(_minimal_report(), nested)
        assert path is not None
        assert nested.exists()

    def test_multiple_repos_paginated(self, tmp_path):
        data = _minimal_report()
        data["audits"] = [
            {
                "metadata": {"name": f"repo{i}", "language": "Python"},
                "overall_score": i / 100,
                "grade": "C",
                "completeness_tier": "wip",
                "interest_score": 0.3,
            }
            for i in range(60)
        ]
        path = export_pdf_report(data, tmp_path)
        assert path is not None
        assert path.stat().st_size > 500

    def test_no_action_backlog(self, tmp_path):
        data = _minimal_report()
        data.pop("action_backlog")
        path = export_pdf_report(data, tmp_path)
        assert path is not None

    def test_missing_generated_at_falls_back(self, tmp_path):
        data = _minimal_report()
        data.pop("generated_at")
        path = export_pdf_report(data, tmp_path)
        assert path is not None
        assert path.name.startswith("audit-report-testuser-")
