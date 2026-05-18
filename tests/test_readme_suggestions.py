from __future__ import annotations

from src.readme_suggestions import generate_readme_suggestions


def _make_report(**overrides) -> dict:
    defaults = {
        "username": "testuser",
        "generated_at": "2026-03-28T12:00:00Z",
        "repos_audited": 3,
        "average_score": 0.60,
        "audits": [
            {
                "metadata": {"name": "NoReadme"},
                "overall_score": 0.30, "grade": "D",
                "analyzer_results": [
                    {"dimension": "readme", "score": 0.0, "findings": ["No README found"], "details": {}},
                ],
            },
            {
                "metadata": {"name": "WeakReadme"},
                "overall_score": 0.50, "grade": "D",
                "analyzer_results": [
                    {"dimension": "readme", "score": 0.3, "findings": ["Short README"], "details": {}},
                ],
            },
            {
                "metadata": {"name": "GoodReadme"},
                "overall_score": 0.85, "grade": "A",
                "analyzer_results": [
                    {"dimension": "readme", "score": 0.9, "findings": ["Comprehensive README with images"], "details": {}},
                ],
            },
        ],
    }
    defaults.update(overrides)
    return defaults


class TestReadmeSuggestions:
    def test_creates_file(self, tmp_path):
        result = generate_readme_suggestions(_make_report(), tmp_path)
        assert result["suggestions_path"].is_file()

    def test_no_readme_gets_suggestions(self, tmp_path):
        result = generate_readme_suggestions(_make_report(), tmp_path)
        content = result["suggestions_path"].read_text()
        assert "NoReadme" in content
        assert "Create a README" in content

    def test_weak_readme_gets_suggestions(self, tmp_path):
        result = generate_readme_suggestions(_make_report(), tmp_path)
        content = result["suggestions_path"].read_text()
        assert "WeakReadme" in content

    def test_good_readme_no_suggestions(self, tmp_path):
        result = generate_readme_suggestions(_make_report(), tmp_path)
        content = result["suggestions_path"].read_text()
        # GoodReadme (score 0.9) should not appear in suggestions
        assert "GoodReadme" not in content

    def test_counts_correct(self, tmp_path):
        result = generate_readme_suggestions(_make_report(), tmp_path)
        assert result["repos_with_suggestions"] == 2
        assert result["total_suggestions"] >= 2

    def test_empty_audits(self, tmp_path):
        result = generate_readme_suggestions({"audits": [], "generated_at": "2026-03-28T00:00:00Z"}, tmp_path)
        assert result["total_suggestions"] == 0
        content = result["suggestions_path"].read_text()
        assert "No suggestions" in content
