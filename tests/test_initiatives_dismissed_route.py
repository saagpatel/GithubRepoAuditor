"""Tests for GET /initiatives/dismissed + POST /initiatives/dismissed/undo (Arc G S12.2)
and GET /initiatives/dismissal-history (Arc G S13.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi", reason="[serve] extra not installed")
pytest.importorskip("uvicorn", reason="[serve] extra not installed")
pytest.importorskip("jinja2", reason="[serve] extra not installed")

from fastapi.testclient import TestClient  # noqa: E402

from src.serve.app import create_app  # noqa: E402

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def output_dir(tmp_path: Path) -> Path:
    od = tmp_path / "output"
    od.mkdir()
    return od


@pytest.fixture()
def client(output_dir: Path) -> TestClient:
    app = create_app(output_dir=output_dir)
    return TestClient(app, raise_server_exceptions=True)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _write_dismissed(output_dir: Path, entries: list[dict]) -> None:
    """Write a dismissed-suggestions.json fixture in the versioned schema."""
    path = output_dir / "dismissed-suggestions.json"
    path.write_text(json.dumps({"version": 1, "items": entries}))


def _write_dismissed_with_events(
    output_dir: Path,
    items: list[dict],
    events: list[dict],
) -> None:
    """Write a v2 dismissed-suggestions.json with both items and events arrays."""
    path = output_dir / "dismissed-suggestions.json"
    path.write_text(json.dumps({"version": 2, "items": items, "events": events}))


# ── GET /initiatives/dismissed ────────────────────────────────────────────────


class TestInitiativesDismissedGet:
    def test_no_dismissed_file_returns_200_empty_state(self, client: TestClient) -> None:
        """GET with no dismissed file → 200 + empty-state message."""
        resp = client.get("/initiatives/dismissed")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "No dismissed suggestions" in resp.text

    def test_two_dismissed_entries_both_visible(self, output_dir: Path, client: TestClient) -> None:
        """GET with 2 dismissed entries → 200, both repo names appear."""
        _write_dismissed(
            output_dir,
            [
                {
                    "repo_name": "alpha-repo",
                    "reason": "not a priority",
                    "dismissed_at": "2026-05-01T10:00:00",
                    "dismissed_by": "operator",
                },
                {
                    "repo_name": "beta-repo",
                    "reason": "already handled",
                    "dismissed_at": "2026-05-02T11:00:00",
                    "dismissed_by": "operator",
                },
            ],
        )
        resp = client.get("/initiatives/dismissed")
        assert resp.status_code == 200
        assert "alpha-repo" in resp.text
        assert "beta-repo" in resp.text
        # Reasons rendered
        assert "not a priority" in resp.text
        assert "already handled" in resp.text

    def test_permanent_shown_when_expires_at_absent(
        self, output_dir: Path, client: TestClient
    ) -> None:
        """GET row shows 'permanent' when expires_at is None / absent (v1 schema)."""
        _write_dismissed(
            output_dir,
            [
                {
                    "repo_name": "no-expiry-repo",
                    "reason": "",
                    "dismissed_at": "2026-05-01T10:00:00",
                    "dismissed_by": "operator",
                    # No expires_at key — v1 schema
                }
            ],
        )
        resp = client.get("/initiatives/dismissed")
        assert resp.status_code == 200
        assert "permanent" in resp.text

    def test_expires_at_date_shown_when_set(self, output_dir: Path, client: TestClient) -> None:
        """GET row: expires_at loaded from JSON and rendered by the template (Arc G S12.1).

        Sprint 12.1 added expires_at to DismissedSuggestion; the template renders the
        date when set, or 'permanent' when None.
        """
        _write_dismissed(
            output_dir,
            [
                {
                    "repo_name": "expiring-repo",
                    "reason": "will reconsider",
                    "dismissed_at": "2026-05-01T10:00:00",
                    "dismissed_by": "operator",
                    "expires_at": "2026-08-01T00:00:00",
                }
            ],
        )
        resp = client.get("/initiatives/dismissed")
        assert resp.status_code == 200
        assert "expiring-repo" in resp.text
        # expires_at is now on the dataclass → template renders the date, not "permanent"
        assert "2026-08-01" in resp.text


# ── POST /initiatives/dismissed/undo ─────────────────────────────────────────


class TestUndoDismissPost:
    def test_undo_existing_repo_returns_200_success_fragment(
        self, output_dir: Path, client: TestClient
    ) -> None:
        """POST undo with existing repo → 200, success fragment, file updated."""
        _write_dismissed(
            output_dir,
            [
                {
                    "repo_name": "my-repo",
                    "reason": "testing",
                    "dismissed_at": "2026-05-01T10:00:00",
                    "dismissed_by": "operator",
                }
            ],
        )
        resp = client.post("/initiatives/dismissed/undo", data={"repo_name": "my-repo"})
        assert resp.status_code == 200
        assert "Restored" in resp.text
        assert "my-repo" in resp.text
        # Verify file was actually updated (versioned schema: {"version": 1, "items": [...]})
        data = json.loads((output_dir / "dismissed-suggestions.json").read_text())
        remaining = data.get("items", [])
        assert not any(e["repo_name"] == "my-repo" for e in remaining)

    def test_undo_unknown_repo_returns_404_error_fragment(
        self, output_dir: Path, client: TestClient
    ) -> None:
        """POST undo with unknown repo → 404 + error fragment."""
        _write_dismissed(output_dir, [])
        resp = client.post("/initiatives/dismissed/undo", data={"repo_name": "ghost-repo"})
        assert resp.status_code == 404
        assert "not currently dismissed" in resp.text
        assert "ghost-repo" in resp.text

    def test_html_in_repo_name_is_escaped(self, client: TestClient) -> None:
        """XSS payload in repo_name is HTML-escaped in error response (no dismissed file)."""
        xss = "<script>alert(1)</script>"
        resp = client.post("/initiatives/dismissed/undo", data={"repo_name": xss})
        # Should be 404 (not found) — never a script tag in body
        assert resp.status_code == 404
        assert "<script>" not in resp.text
        assert "&lt;script&gt;" in resp.text

    def test_undo_empty_repo_name_returns_422(self, client: TestClient) -> None:
        """POST with empty repo_name → 422 (FastAPI Form validation)."""
        resp = client.post("/initiatives/dismissed/undo", data={"repo_name": ""})
        # FastAPI treats empty string as missing/invalid Form(...) value
        assert resp.status_code in (400, 422)


# ── Nav link visibility ───────────────────────────────────────────────────────


class TestNavLinkVisibility:
    def test_dismissed_nav_link_visible_on_dashboard(self, client: TestClient) -> None:
        """Nav link /initiatives/dismissed appears on Dashboard (GET /)."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert "/initiatives/dismissed" in resp.text

    def test_dismissed_nav_link_visible_on_approvals(self, client: TestClient) -> None:
        """Nav link /initiatives/dismissed appears on Approvals page."""
        resp = client.get("/approvals")
        assert resp.status_code == 200
        assert "/initiatives/dismissed" in resp.text


# ── Route ordering: /initiatives/dismissed not caught by parametric ───────────


class TestRouteOrdering:
    def test_dismissed_path_returns_dismissed_page_not_gap_partial(
        self, client: TestClient
    ) -> None:
        """GET /initiatives/dismissed returns the dismissed page, not the gap HTMX partial."""
        resp = client.get("/initiatives/dismissed")
        assert resp.status_code == 200
        # The gap partial returns a fragment with class "tier-gap-list" or similar,
        # not a full HTML page with nav. The dismissed page extends base.html.
        assert "Dismissed Suggestions" in resp.text
        assert "nav-links" in resp.text  # full page, not a partial fragment


# ── GET /initiatives/dismissal-history (Arc G S13.1) ─────────────────────────


class TestDismissalHistoryGet:
    def test_no_events_returns_200_empty_state(self, client: TestClient) -> None:
        """GET with no dismissed file → 200 + empty-state message."""
        resp = client.get("/initiatives/dismissal-history")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "No dismissal events recorded" in resp.text

    def test_multiple_events_sorted_newest_first(
        self, output_dir: Path, client: TestClient
    ) -> None:
        """GET with events → 200, sorted newest-first (most recent occurred_at at top)."""
        _write_dismissed_with_events(
            output_dir,
            items=[],
            events=[
                {
                    "repo_name": "old-repo",
                    "event_type": "dismissed",
                    "occurred_at": "2026-04-01T10:00:00+00:00",
                    "actor": "operator",
                    "reason": "deprioritized",
                },
                {
                    "repo_name": "new-repo",
                    "event_type": "undone",
                    "occurred_at": "2026-05-10T12:00:00+00:00",
                    "actor": "operator",
                    "reason": "",
                },
                {
                    "repo_name": "mid-repo",
                    "event_type": "expired",
                    "occurred_at": "2026-04-20T08:00:00+00:00",
                    "actor": "system",
                    "reason": "auto-expire",
                },
            ],
        )
        resp = client.get("/initiatives/dismissal-history")
        assert resp.status_code == 200
        # All three repos appear.
        assert "old-repo" in resp.text
        assert "new-repo" in resp.text
        assert "mid-repo" in resp.text
        # Newest first: new-repo (2026-05-10) should appear before mid-repo and old-repo.
        pos_new = resp.text.index("new-repo")
        pos_mid = resp.text.index("mid-repo")
        pos_old = resp.text.index("old-repo")
        assert pos_new < pos_mid < pos_old

    def test_route_not_captured_by_parametric_gap(
        self, output_dir: Path, client: TestClient
    ) -> None:
        """Fixed path /initiatives/dismissal-history resolves to the history page,
        not the parametric /initiatives/{repo_name}/gap partial."""
        # Write an item named "dismissal-history" so it would exist if the parametric
        # route fired.
        _write_dismissed_with_events(
            output_dir,
            items=[
                {
                    "repo_name": "dismissal-history",
                    "reason": "trick entry",
                    "dismissed_at": "2026-05-01T00:00:00",
                    "dismissed_by": "operator",
                }
            ],
            events=[],
        )
        resp = client.get("/initiatives/dismissal-history")
        assert resp.status_code == 200
        # The history page extends base.html and has "Dismissal History" in the page.
        assert "Dismissal History" in resp.text
        # nav-links confirms this is a full page, not an HTMX gap partial.
        assert "nav-links" in resp.text

    def test_xss_reason_is_escaped(self, output_dir: Path, client: TestClient) -> None:
        """User-controlled reason text is HTML-escaped — no raw script tags rendered."""
        _write_dismissed_with_events(
            output_dir,
            items=[],
            events=[
                {
                    "repo_name": "xss-repo",
                    "event_type": "dismissed",
                    "occurred_at": "2026-05-01T10:00:00+00:00",
                    "actor": "operator",
                    "reason": "<script>alert(1)</script>",
                }
            ],
        )
        resp = client.get("/initiatives/dismissal-history")
        assert resp.status_code == 200
        assert "<script>" not in resp.text
        assert "&lt;script&gt;" in resp.text

    def test_empty_state_copy_when_no_events(self, client: TestClient) -> None:
        """Empty state renders the 'No dismissal events recorded.' message."""
        resp = client.get("/initiatives/dismissal-history")
        assert "No dismissal events recorded" in resp.text
        # Table should NOT be present.
        assert "<table>" not in resp.text

    def test_all_event_types_render(self, output_dir: Path, client: TestClient) -> None:
        """dismissed, undone, and expired event types all appear in the table."""
        _write_dismissed_with_events(
            output_dir,
            items=[],
            events=[
                {
                    "repo_name": "r1",
                    "event_type": "dismissed",
                    "occurred_at": "2026-05-01T10:00:00+00:00",
                    "actor": "operator",
                    "reason": "",
                },
                {
                    "repo_name": "r2",
                    "event_type": "undone",
                    "occurred_at": "2026-05-02T10:00:00+00:00",
                    "actor": "operator",
                    "reason": "",
                },
                {
                    "repo_name": "r3",
                    "event_type": "expired",
                    "occurred_at": "2026-05-03T10:00:00+00:00",
                    "actor": "system",
                    "reason": "auto-expire",
                },
            ],
        )
        resp = client.get("/initiatives/dismissal-history")
        assert resp.status_code == 200
        assert "dismissed" in resp.text
        assert "undone" in resp.text
        assert "expired" in resp.text

    def test_back_link_to_dismissed_is_present(self, client: TestClient) -> None:
        """Footer contains a back-link to /initiatives/dismissed."""
        resp = client.get("/initiatives/dismissal-history")
        assert resp.status_code == 200
        assert "/initiatives/dismissed" in resp.text

    def test_dismissed_page_has_link_to_history(self, client: TestClient) -> None:
        """The /initiatives/dismissed page includes a forward-link to dismissal-history."""
        resp = client.get("/initiatives/dismissed")
        assert resp.status_code == 200
        assert "/initiatives/dismissal-history" in resp.text
