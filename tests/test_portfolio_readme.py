from __future__ import annotations

from src.portfolio_readme import export_portfolio_readme


def _make_report(**overrides) -> dict:
    defaults = {
        "username": "testuser",
        "generated_at": "2026-03-28T12:00:00Z",
        "repos_audited": 3,
        "average_score": 0.60,
        "portfolio_grade": "C",
        "tier_distribution": {"shipped": 1, "functional": 1, "wip": 1},
        "language_distribution": {"Python": 2, "TypeScript": 1},
        "tech_stack": {},
        "audits": [
            {
                "metadata": {"name": "ShippedRepo", "html_url": "https://github.com/user/ShippedRepo",
                             "description": "A great project", "language": "Python"},
                "overall_score": 0.85, "grade": "A", "completeness_tier": "shipped",
                "badges": ["fresh"], "flags": [], "analyzer_results": [],
            },
            {
                "metadata": {"name": "FuncRepo", "html_url": "https://github.com/user/FuncRepo",
                             "description": "Getting there", "language": "TypeScript"},
                "overall_score": 0.60, "grade": "C", "completeness_tier": "functional",
                "badges": [], "flags": [], "analyzer_results": [],
            },
            {
                "metadata": {"name": "WipRepo", "html_url": "https://github.com/user/WipRepo",
                             "description": None, "language": "Python"},
                "overall_score": 0.40, "grade": "D", "completeness_tier": "wip",
                "badges": [], "flags": ["no-tests"], "analyzer_results": [],
            },
        ],
    }
    defaults.update(overrides)
    return defaults


class TestPortfolioReadme:
    def test_file_created(self, tmp_path):
        result = export_portfolio_readme(_make_report(), tmp_path)
        assert result["readme_path"].is_file()

    def test_has_title(self, tmp_path):
        result = export_portfolio_readme(_make_report(), tmp_path)
        content = result["readme_path"].read_text()
        assert "# Portfolio: testuser" in content

    def test_has_shields_badges(self, tmp_path):
        result = export_portfolio_readme(_make_report(), tmp_path)
        content = result["readme_path"].read_text()
        assert "img.shields.io/badge/" in content

    def test_flagship_section_only_shipped(self, tmp_path):
        result = export_portfolio_readme(_make_report(), tmp_path)
        content = result["readme_path"].read_text()
        assert "## Flagship Projects (1)" in content
        assert "ShippedRepo" in content

    def test_in_progress_section(self, tmp_path):
        result = export_portfolio_readme(_make_report(), tmp_path)
        content = result["readme_path"].read_text()
        assert "## In Progress (2)" in content
        assert "FuncRepo" in content
        assert "WipRepo" in content

    def test_tech_stack_section(self, tmp_path):
        result = export_portfolio_readme(_make_report(), tmp_path)
        content = result["readme_path"].read_text()
        assert "## Tech Stack" in content
        assert "Python" in content

    def test_distribution_section(self, tmp_path):
        result = export_portfolio_readme(_make_report(), tmp_path)
        content = result["readme_path"].read_text()
        assert "## Distribution" in content
        assert "Shipped" in content

    def test_empty_audits(self, tmp_path):
        report = _make_report(audits=[], tier_distribution={}, language_distribution={})
        result = export_portfolio_readme(report, tmp_path)
        content = result["readme_path"].read_text()
        assert "# Portfolio:" in content
        assert "Flagship Projects (0)" in content
