from __future__ import annotations

from src.notion_sync import _extract_audit_data
from src.notion_sync import (
    _render_quick_wins_markdown,
    _render_audit_highlights,
    _chunk_text,
    FLAG_TO_ACTION,
    ELIGIBLE_TIERS,
)


class TestRenderQuickWins:
    def test_empty_wins(self):
        md = _render_quick_wins_markdown([], "2026-03-29")
        assert "No repos" in md

    def test_with_wins(self):
        wins = [
            {"name": "RepoA", "current_tier": "wip", "next_tier": "functional",
             "gap": 0.03, "actions": ["Add tests (testing=0.2)"]},
        ]
        md = _render_quick_wins_markdown(wins, "2026-03-29")
        assert "RepoA" in md
        assert "functional" in md
        assert "Add tests" in md

    def test_limits_to_10(self):
        wins = [
            {"name": f"Repo{i}", "current_tier": "wip", "next_tier": "functional",
             "gap": 0.01 * i, "actions": []}
            for i in range(15)
        ]
        md = _render_quick_wins_markdown(wins, "2026-03-29")
        assert "Repo14" not in md  # 11th+ should be excluded


class TestRenderAuditHighlights:
    def test_basic_output(self):
        report = {
            "generated_at": "2026-03-29T00:00:00Z",
            "portfolio_grade": "C",
            "average_score": 0.57,
            "tier_distribution": {"shipped": 5, "functional": 10},
        }
        md = _render_audit_highlights(report, None, [])
        assert "Grade C" in md
        assert "0.57" in md
        assert "5 shipped" in md

    def test_with_diff_changes(self):
        report = {
            "generated_at": "2026-03-29T00:00:00Z",
            "portfolio_grade": "C",
            "average_score": 0.57,
            "tier_distribution": {"shipped": 5, "functional": 10},
        }
        diff = {
            "tier_changes": [
                {"name": "RepoX", "direction": "promotion", "old_tier": "wip", "new_tier": "functional"},
            ],
        }
        md = _render_audit_highlights(report, diff, [])
        assert "RepoX" in md
        assert "1 promotions" in md

    def test_with_quick_wins(self):
        report = {
            "generated_at": "2026-03-29T00:00:00Z",
            "portfolio_grade": "C",
            "average_score": 0.57,
            "tier_distribution": {},
        }
        wins = [{"name": "RepoY", "gap": 0.02, "next_tier": "shipped"}]
        md = _render_audit_highlights(report, None, wins)
        assert "RepoY" in md
        assert "shipped" in md


class TestChunkText:
    def test_short_text(self):
        assert _chunk_text("hello", 2000) == ["hello"]

    def test_long_text(self):
        text = "x" * 5000
        chunks = _chunk_text(text, 2000)
        assert len(chunks) == 3
        assert len(chunks[0]) == 2000


class TestFlagMapping:
    def test_critical_flags_mapped(self):
        assert "no-tests" in FLAG_TO_ACTION
        assert "no-ci" in FLAG_TO_ACTION
        assert "no-readme" in FLAG_TO_ACTION

    def test_eligible_tiers(self):
        assert "shipped" in ELIGIBLE_TIERS
        assert "functional" in ELIGIBLE_TIERS
        assert "wip" not in ELIGIBLE_TIERS


class TestExtractAuditData:
    def test_prefers_typed_machine_data(self):
        event = {
            "occurredAt": "2026-03-29",
            "status": "B",
            "machineData": {
                "grade": "A",
                "overall_score": 0.91,
                "interest_score": 0.33,
                "badges": ["fresh"],
            },
        }
        data = _extract_audit_data(event)
        assert data["grade"] == "A"
        assert data["overall_score"] == 0.91
        assert data["interest_score"] == 0.33
        assert data["badges"] == ["fresh"]
        assert data["date"] == "2026-03-29"

    def test_falls_back_to_legacy_raw_excerpt(self):
        event = {
            "occurredAt": "2026-03-29",
            "status": "C",
            "rawExcerpt": "{\"overall_score\": 0.75, \"interest_score\": 0.2, \"badges\": [\"fresh\"]}",
        }
        data = _extract_audit_data(event)
        assert data["grade"] == "C"
        assert data["overall_score"] == 0.75
        assert data["interest_score"] == 0.2
        assert data["badges"] == ["fresh"]

    def test_malformed_legacy_payload_fails_soft(self):
        event = {
            "occurredAt": "2026-03-29",
            "status": "F",
            "rawExcerpt": "{\"overall_score\": 0.75,",
        }
        data = _extract_audit_data(event)
        assert data["grade"] == "F"
        assert data["overall_score"] == 0
        assert data["interest_score"] == 0
        assert data["badges"] == []
