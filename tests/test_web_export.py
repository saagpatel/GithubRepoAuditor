from __future__ import annotations

from src.web_export import export_html_dashboard, _render_html


def _make_report(**overrides) -> dict:
    defaults = {
        "username": "testuser",
        "generated_at": "2026-03-29T12:00:00Z",
        "repos_audited": 3,
        "average_score": 0.60,
        "portfolio_grade": "C",
        "portfolio_health_score": 0.65,
        "tier_distribution": {"shipped": 1, "functional": 1, "wip": 1},
        "language_distribution": {"Python": 2, "Rust": 1},
        "audits": [
            {
                "metadata": {"name": "RepoA", "html_url": "https://github.com/user/RepoA",
                             "description": "A cool project", "language": "Python"},
                "overall_score": 0.85, "interest_score": 0.60, "grade": "A",
                "completeness_tier": "shipped", "badges": ["fresh"], "flags": [],
                "analyzer_results": [],
            },
            {
                "metadata": {"name": "RepoB", "html_url": "", "description": None, "language": "Rust"},
                "overall_score": 0.55, "interest_score": 0.30, "grade": "C",
                "completeness_tier": "functional", "badges": [], "flags": [],
                "analyzer_results": [],
            },
            {
                "metadata": {"name": "RepoC", "html_url": "", "description": "WIP", "language": "Python"},
                "overall_score": 0.40, "interest_score": 0.10, "grade": "D",
                "completeness_tier": "wip", "badges": [], "flags": ["no-tests"],
                "analyzer_results": [],
            },
        ],
    }
    defaults.update(overrides)
    return defaults


class TestExportHtmlDashboard:
    def test_creates_html_file(self, tmp_path):
        result = export_html_dashboard(_make_report(), tmp_path)
        assert result["html_path"].is_file()
        assert result["html_path"].suffix == ".html"

    def test_filename_includes_username(self, tmp_path):
        result = export_html_dashboard(_make_report(), tmp_path)
        assert "testuser" in result["html_path"].name

    def test_html_is_self_contained(self, tmp_path):
        result = export_html_dashboard(_make_report(), tmp_path)
        content = result["html_path"].read_text()
        assert "<!DOCTYPE html>" in content
        assert "<style>" in content
        assert "<script>" in content
        assert "const DATA =" in content


class TestRenderHtml:
    def test_has_header(self):
        html = _render_html(_make_report())
        assert "Portfolio Dashboard: testuser" in html

    def test_has_kpi_section(self):
        html = _render_html(_make_report())
        assert "Avg Score" in html
        assert "0.60" in html
        assert "Shipped" in html

    def test_has_scatter_canvas(self):
        html = _render_html(_make_report())
        assert '<canvas id="scatter"' in html

    def test_has_repo_table(self):
        html = _render_html(_make_report())
        assert "RepoA" in html
        assert "RepoB" in html
        assert "RepoC" in html

    def test_has_filter_controls(self):
        html = _render_html(_make_report())
        assert 'id="filter-tier"' in html
        assert 'id="filter-grade"' in html
        assert 'id="search"' in html

    def test_has_tier_distribution(self):
        html = _render_html(_make_report())
        assert "Tier Distribution" in html
        assert "Shipped" in html

    def test_has_footer(self):
        html = _render_html(_make_report())
        assert "GithubRepoAuditor" in html

    def test_has_print_css(self):
        html = _render_html(_make_report())
        assert "@media print" in html

    def test_empty_audits_still_renders(self):
        report = _make_report(audits=[], tier_distribution={})
        html = _render_html(report)
        assert "<!DOCTYPE html>" in html
        assert "Portfolio Dashboard" in html

    def test_data_embedded_as_json(self):
        html = _render_html(_make_report())
        assert '"username": "testuser"' in html
        assert '"audits":' in html
