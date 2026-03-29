from __future__ import annotations
from unittest.mock import MagicMock, patch

from src.notion_client import query_page_by_title
from src.notion_sync import _extract_audit_data
from src.notion_sync import (
    _render_quick_wins_markdown,
    _render_audit_highlights,
    _chunk_text,
    check_recommendation_followup,
    FLAG_TO_ACTION,
    ELIGIBLE_TIERS,
    sync_campaign_actions,
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


class TestCampaignActionSync:
    def test_fails_soft_without_token(self, monkeypatch):
        monkeypatch.setattr("src.notion_sync.get_notion_token", lambda: "")
        results, refs = sync_campaign_actions([], {"campaign_type": "security-review"}, apply=True)
        assert results[0]["status"] == "skipped"
        assert refs == {}


class TestCheckRecommendationFollowup:
    def _report(self, repo_names: list[str], scores: list[float]) -> dict:
        return {
            "audits": [
                {"metadata": {"name": name}, "overall_score": score}
                for name, score in zip(repo_names, scores)
            ]
        }

    def test_returns_zero_when_no_db_id(self):
        result = check_recommendation_followup(
            self._report(["RepoA"], [0.5]), "token", {}
        )
        assert result == {"checked": 0}

    def test_returns_zero_when_api_fails(self):
        with patch("src.notion_sync._notion_request", return_value=None):
            result = check_recommendation_followup(
                self._report(["RepoA"], [0.5]),
                "token",
                {"recommendation_runs_db_id": "db123"},
            )
        assert result == {"checked": 0}

    def test_returns_zero_when_no_previous_runs(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": []}

        with patch("src.notion_sync._notion_request", return_value=mock_resp):
            result = check_recommendation_followup(
                self._report(["RepoA"], [0.5]),
                "token",
                {"recommendation_runs_db_id": "db123"},
            )
        assert result == {"checked": 0}

    def test_returns_proper_structure_when_blocks_fetched(self):
        # First call: query returns one result; second call: block children
        query_resp = MagicMock()
        query_resp.status_code = 200
        query_resp.json.return_value = {"results": [{"id": "page-abc"}]}

        blocks_resp = MagicMock()
        blocks_resp.status_code = 200
        blocks_resp.json.return_value = {
            "results": [
                {
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"plain_text": "RepoA needs improvement, RepoB also listed"}]
                    },
                }
            ]
        }

        with patch("src.notion_sync._notion_request", side_effect=[query_resp, blocks_resp]):
            result = check_recommendation_followup(
                self._report(["RepoA", "RepoB", "RepoC"], [0.6, 0.4, 0.0]),
                "token",
                {"recommendation_runs_db_id": "db123"},
            )

        assert "checked" in result
        assert "improved" in result
        assert "still_open" in result
        assert "summary" in result
        assert result["checked"] == len(result["improved"]) + len(result["still_open"])

    def test_blocks_api_failure_returns_zero(self):
        query_resp = MagicMock()
        query_resp.status_code = 200
        query_resp.json.return_value = {"results": [{"id": "page-abc"}]}

        with patch("src.notion_sync._notion_request", side_effect=[query_resp, None]):
            result = check_recommendation_followup(
                self._report(["RepoA"], [0.5]),
                "token",
                {"recommendation_runs_db_id": "db123"},
            )
        assert result == {"checked": 0}


class TestQueryPageByTitle:
    def test_returns_page_id_when_found(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": [{"id": "page-xyz"}]}

        with patch("src.notion_client.notion_request", return_value=mock_resp):
            result = query_page_by_title("db123", "My Project", "token")

        assert result == "page-xyz"

    def test_returns_none_when_no_results(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": []}

        with patch("src.notion_client.notion_request", return_value=mock_resp):
            result = query_page_by_title("db123", "Nonexistent", "token")

        assert result is None

    def test_returns_none_when_api_fails(self):
        with patch("src.notion_client.notion_request", return_value=None):
            result = query_page_by_title("db123", "Any Title", "token")

        assert result is None

    def test_returns_none_on_non_200_status(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch("src.notion_client.notion_request", return_value=mock_resp):
            result = query_page_by_title("db123", "Any Title", "token")

        assert result is None

    def test_uses_custom_title_property(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": [{"id": "page-abc"}]}

        with patch("src.notion_client.notion_request", return_value=mock_resp) as mock_req:
            query_page_by_title("db123", "My Title", "token", title_property="Title")
            call_body = mock_req.call_args[0][4]  # body is 5th positional arg
            assert call_body["filter"]["property"] == "Title"
