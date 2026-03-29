from __future__ import annotations

from src.notion_registry import _extract_title, _extract_rich_text, load_notion_project_context
from src.notion_sync import _render_audit_highlights, check_recommendation_followup
from src.notion_dashboard import _heading_block, _paragraph_block, _bullet_block, _divider_block


class TestExtractRichText:
    def test_extracts_text(self):
        page = {
            "properties": {
                "Next Move": {"type": "rich_text", "rich_text": [{"text": {"content": "Add tests"}}]},
            },
        }
        assert _extract_rich_text(page, "Next Move") == "Add tests"

    def test_empty_rich_text(self):
        page = {"properties": {"Next Move": {"type": "rich_text", "rich_text": []}}}
        assert _extract_rich_text(page, "Next Move") == ""

    def test_missing_property(self):
        page = {"properties": {}}
        assert _extract_rich_text(page, "Next Move") == ""


class TestDiffAwareHighlights:
    def test_with_diff_shows_changes(self):
        report = {
            "generated_at": "2026-03-29T00:00:00Z",
            "portfolio_grade": "B",
            "average_score": 0.58,
            "tier_distribution": {"shipped": 26, "functional": 37},
        }
        diff = {
            "tier_changes": [
                {"name": "RepoA", "direction": "promotion", "old_tier": "wip", "new_tier": "functional"},
            ],
        }
        md = _render_audit_highlights(report, diff, [])
        assert "RepoA" in md
        assert "1 promotions" in md

    def test_without_diff_shows_full_stats(self):
        report = {
            "generated_at": "2026-03-29T00:00:00Z",
            "portfolio_grade": "B",
            "average_score": 0.58,
            "tier_distribution": {"shipped": 26, "functional": 37},
        }
        md = _render_audit_highlights(report, None, [])
        assert "Grade B" in md
        assert "26 shipped" in md


class TestNotionDashboardBlocks:
    def test_heading_block(self):
        block = _heading_block("Test", level=2)
        assert block["type"] == "heading_2"

    def test_paragraph_block(self):
        block = _paragraph_block("Hello world")
        assert block["type"] == "paragraph"
        assert "Hello world" in block["paragraph"]["rich_text"][0]["text"]["content"]

    def test_bullet_block(self):
        block = _bullet_block("Item 1")
        assert block["type"] == "bulleted_list_item"

    def test_divider_block(self):
        block = _divider_block()
        assert block["type"] == "divider"


class TestRecommendationFollowup:
    def test_returns_checked_zero_without_config(self):
        result = check_recommendation_followup({"audits": []}, "fake-token", {})
        assert result["checked"] == 0
