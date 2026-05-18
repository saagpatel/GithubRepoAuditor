from __future__ import annotations

from src.notion_registry import _extract_select, _extract_title, _normalize_status


class TestExtractTitle:
    def test_extracts_from_title_property(self):
        page = {
            "properties": {
                "Name": {
                    "type": "title",
                    "title": [{"text": {"content": "My Project"}}],
                },
            },
        }
        assert _extract_title(page) == "My Project"

    def test_empty_title(self):
        page = {"properties": {"Name": {"type": "title", "title": []}}}
        assert _extract_title(page) == ""

    def test_no_title_property(self):
        page = {"properties": {"Status": {"type": "select"}}}
        assert _extract_title(page) == ""


class TestExtractSelect:
    def test_extracts_select(self):
        page = {
            "properties": {
                "Current State": {"type": "select", "select": {"name": "Active"}},
            },
        }
        assert _extract_select(page, "Current State") == "Active"

    def test_null_select(self):
        page = {
            "properties": {
                "Current State": {"type": "select", "select": None},
            },
        }
        assert _extract_select(page, "Current State") == ""

    def test_missing_property(self):
        page = {"properties": {}}
        assert _extract_select(page, "Current State") == ""


class TestNormalizeStatus:
    def test_active_states(self):
        assert _normalize_status("Active") == "active"
        assert _normalize_status("Building") == "active"
        assert _normalize_status("Shipped") == "active"

    def test_parked_states(self):
        assert _normalize_status("Paused") == "parked"
        assert _normalize_status("On Hold") == "parked"

    def test_archived_states(self):
        assert _normalize_status("Archived") == "archived"
        assert _normalize_status("Abandoned") == "archived"
        assert _normalize_status("Cold Storage") == "archived"

    def test_unknown_defaults_active(self):
        assert _normalize_status("Something New") == "active"
