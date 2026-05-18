from unittest.mock import MagicMock

from src.issue_creator import create_audit_issues


def _mock_client(existing_issues=None):
    client = MagicMock()
    client.list_repo_issues.return_value = existing_issues or []
    client.create_issue.return_value = {"html_url": "https://github.com/u/r/issues/1"}
    return client


class TestCreateAuditIssues:
    def test_creates_issue_for_quick_win(self):
        qw = [{"name": "repo1", "actions": ["Add CI"], "score": 0.5, "current_tier": "wip", "next_tier": "functional", "gap": 0.1}]
        client = _mock_client()
        result = create_audit_issues(qw, "user", client)
        assert len(result["created"]) == 1
        client.create_issue.assert_called_once()

    def test_dedup_skips_existing_audit_issue(self):
        qw = [{"name": "repo1", "actions": ["Add CI"], "score": 0.5, "current_tier": "wip", "next_tier": "functional", "gap": 0.1}]
        client = _mock_client(existing_issues=[{"title": "[Audit] repo1: Add CI"}])
        result = create_audit_issues(qw, "user", client)
        assert len(result["skipped"]) == 1
        assert len(result["created"]) == 0
        client.create_issue.assert_not_called()

    def test_dry_run_does_not_create(self):
        qw = [{"name": "repo1", "actions": ["Add tests"], "score": 0.4, "current_tier": "skeleton", "next_tier": "wip", "gap": 0.05}]
        client = _mock_client()
        result = create_audit_issues(qw, "user", client, dry_run=True)
        assert len(result["created"]) == 1
        assert result["created"][0]["dry_run"] is True
        client.create_issue.assert_not_called()

    def test_empty_quick_wins(self):
        client = _mock_client()
        result = create_audit_issues([], "user", client)
        assert result["created"] == []
        assert result["skipped"] == []

    def test_error_in_one_repo_doesnt_stop_others(self):
        qw = [
            {"name": "repo1", "actions": ["Fix"], "score": 0.3, "current_tier": "skeleton", "next_tier": "wip", "gap": 0.1},
            {"name": "repo2", "actions": ["Add CI"], "score": 0.5, "current_tier": "wip", "next_tier": "functional", "gap": 0.1},
        ]
        client = _mock_client()
        client.create_issue.side_effect = [Exception("API error"), {"html_url": "https://example.com"}]
        result = create_audit_issues(qw, "user", client)
        assert len(result["created"]) == 1
