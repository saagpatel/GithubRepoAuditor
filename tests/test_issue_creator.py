"""Tests for issue_creator.create_audit_issues."""
from __future__ import annotations

import pytest

from src.issue_creator import create_audit_issues
from src.github_client import GitHubClient


def _make_qw(name: str, score: float = 0.45, *, actions: list[str] | None = None) -> dict:
    return {
        "name": name,
        "score": score,
        "current_tier": "wip",
        "next_tier": "functional",
        "gap": 0.05,
        "actions": actions if actions is not None else ["Add a README", "Add CI workflow"],
    }


class FakeClient:
    """Minimal GitHubClient double."""

    def __init__(self, existing_issues: list[dict] | None = None, *, raise_on_list: bool = False) -> None:
        self._existing = existing_issues or []
        self._raise_on_list = raise_on_list
        self.created: list[dict] = []

    def list_repo_issues(self, owner: str, repo: str, state: str = "open") -> list[dict]:
        if self._raise_on_list:
            raise RuntimeError("network error")
        return self._existing

    def create_issue(self, owner: str, repo: str, payload: dict) -> dict:
        self.created.append({"repo": repo, "payload": payload})
        return {"ok": True, "html_url": f"https://github.com/{owner}/{repo}/issues/1"}


# ── dedup ───────────────────────────────────────────────────────────────

class TestDedup:
    def test_skips_repo_when_audit_issue_exists(self):
        client = FakeClient(existing_issues=[{"title": "[Audit] repo: something"}])
        result = create_audit_issues([_make_qw("my-repo")], "user", client)

        assert result["skipped"] == [{"repo": "my-repo", "reason": "existing [Audit] issue found"}]
        assert result["created"] == []
        assert client.created == []

    def test_proceeds_when_no_audit_issues_exist(self):
        client = FakeClient(existing_issues=[{"title": "Unrelated issue"}])
        result = create_audit_issues([_make_qw("my-repo")], "user", client)

        assert len(result["created"]) == 1
        assert result["skipped"] == []

    def test_proceeds_when_list_issues_raises(self):
        """If we can't check for duplicates, err on the side of creating."""
        client = FakeClient(raise_on_list=True)
        result = create_audit_issues([_make_qw("my-repo")], "user", client)

        assert len(result["created"]) == 1

    def test_skips_entry_with_empty_name(self):
        client = FakeClient()
        result = create_audit_issues([{"name": "", "actions": ["do something"]}], "user", client)

        assert result["created"] == []
        assert result["skipped"] == []
        assert client.created == []


# ── body formatting ─────────────────────────────────────────────────────

class TestBodyFormatting:
    def test_title_uses_first_action(self):
        client = FakeClient()
        create_audit_issues([_make_qw("proj", actions=["Add README", "Add CI"])], "user", client)

        assert client.created[0]["payload"]["title"] == "[Audit] proj: Add README"

    def test_title_fallback_when_no_actions(self):
        client = FakeClient()
        create_audit_issues([_make_qw("proj", actions=[])], "user", client)

        assert client.created[0]["payload"]["title"] == "[Audit] proj: Improve audit score"

    def test_body_contains_score_and_tiers(self):
        client = FakeClient()
        qw = _make_qw("proj", score=0.42)
        create_audit_issues([qw], "user", client)

        body = client.created[0]["payload"]["body"]
        assert "0.42" in body
        assert "wip" in body
        assert "functional" in body

    def test_body_lists_all_actions(self):
        actions = ["Step one", "Step two", "Step three"]
        client = FakeClient()
        create_audit_issues([_make_qw("proj", actions=actions)], "user", client)

        body = client.created[0]["payload"]["body"]
        for i, action in enumerate(actions, 1):
            assert f"{i}. {action}" in body

    def test_body_includes_generator_signature(self):
        client = FakeClient()
        create_audit_issues([_make_qw("proj")], "user", client)

        body = client.created[0]["payload"]["body"]
        assert "GitHub Repo Auditor" in body

    def test_label_is_applied(self):
        client = FakeClient()
        create_audit_issues([_make_qw("proj")], "user", client, label="tech-debt")

        assert client.created[0]["payload"]["labels"] == ["tech-debt"]


# ── dry-run mode ────────────────────────────────────────────────────────

class TestDryRun:
    def test_dry_run_does_not_call_create_issue(self):
        client = FakeClient()
        result = create_audit_issues([_make_qw("my-repo")], "user", client, dry_run=True)

        assert client.created == []

    def test_dry_run_returns_entry_with_dry_run_true(self):
        client = FakeClient()
        result = create_audit_issues([_make_qw("my-repo")], "user", client, dry_run=True)

        assert len(result["created"]) == 1
        assert result["created"][0]["dry_run"] is True
        assert result["created"][0]["repo"] == "my-repo"

    def test_dry_run_still_respects_dedup(self):
        """Dedup check runs before dry-run path, so existing issues are still skipped."""
        client = FakeClient(existing_issues=[{"title": "[Audit] my-repo: something"}])
        result = create_audit_issues([_make_qw("my-repo")], "user", client, dry_run=True)

        assert result["created"] == []
        assert result["skipped"][0]["repo"] == "my-repo"


# ── error handling ──────────────────────────────────────────────────────

class TestErrorHandling:
    def test_create_issue_exception_is_handled(self):
        class BrokenClient(FakeClient):
            def create_issue(self, owner, repo, payload):
                raise RuntimeError("API down")

        client = BrokenClient()
        # Should not raise; failure is logged to stderr
        result = create_audit_issues([_make_qw("my-repo")], "user", client)

        # The issue was attempted but not added to created
        assert result["created"] == []

    def test_multiple_repos_independent(self):
        """A failure on one repo should not prevent creation for others."""
        call_count = 0

        class SelectiveClient(FakeClient):
            def create_issue(self, owner, repo, payload):
                nonlocal call_count
                call_count += 1
                if repo == "bad-repo":
                    raise RuntimeError("fail")
                return {"ok": True, "html_url": f"https://github.com/{owner}/{repo}/issues/1"}

        client = SelectiveClient()
        result = create_audit_issues(
            [_make_qw("bad-repo"), _make_qw("good-repo")],
            "user",
            client,
        )

        assert call_count == 2
        assert len(result["created"]) == 1
        assert result["created"][0]["repo"] == "good-repo"
