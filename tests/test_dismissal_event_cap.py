"""Tests for Arc G Sprint 13.2 — bounded dismissal event log (_MAX_DISMISSAL_EVENTS)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.suggest_initiatives import (
    _MAX_DISMISSAL_EVENTS,
    DismissalEvent,
    _save_dismissed_full,
    dismissed_path,
    load_dismissal_events,
    load_dismissed,
)


def _make_event(
    repo: str, offset_seconds: int = 0, event_type: str = "dismissed"
) -> DismissalEvent:
    """Build a DismissalEvent with a deterministic occurred_at."""
    ts = (
        datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=offset_seconds)
    ).isoformat()
    return DismissalEvent(
        repo_name=repo,
        event_type=event_type,
        occurred_at=ts,
        actor="test-operator",
    )


def _make_events(count: int) -> list[DismissalEvent]:
    """Return *count* events with strictly increasing occurred_at timestamps."""
    return [_make_event(f"Repo{i:04d}", offset_seconds=i) for i in range(count)]


class TestEventCapUnderLimit:
    def test_under_limit_no_trim_event(self, tmp_path):
        """Writing < 1000 events produces no log_trimmed entry."""
        events = _make_events(999)
        _save_dismissed_full(dismissed_path(tmp_path), [], events)

        loaded = load_dismissal_events(dismissed_path(tmp_path))
        assert len(loaded) == 999
        assert not any(e.event_type == "log_trimmed" for e in loaded)

    def test_exactly_at_limit_no_trim_event(self, tmp_path):
        """Writing exactly 1000 events does NOT trigger a trim."""
        events = _make_events(_MAX_DISMISSAL_EVENTS)
        _save_dismissed_full(dismissed_path(tmp_path), [], events)

        loaded = load_dismissal_events(dismissed_path(tmp_path))
        assert len(loaded) == _MAX_DISMISSAL_EVENTS
        assert not any(e.event_type == "log_trimmed" for e in loaded)


class TestEventCapOverLimit:
    def test_over_limit_trim_applied(self, tmp_path):
        """Writing 1005 events trims to exactly _MAX_DISMISSAL_EVENTS (sentinel inclusive)."""
        events = _make_events(1005)
        _save_dismissed_full(dismissed_path(tmp_path), [], events)

        loaded = load_dismissal_events(dismissed_path(tmp_path))
        # 999 survivors + 1 log_trimmed sentinel = 1000
        assert len(loaded) == _MAX_DISMISSAL_EVENTS

    def test_trim_drops_oldest(self, tmp_path):
        """After trim, the retained events are the newest ones (highest occurred_at)."""
        events = _make_events(1005)
        _save_dismissed_full(dismissed_path(tmp_path), [], events)

        loaded = load_dismissal_events(dismissed_path(tmp_path))
        # Remove the log_trimmed sentinel for comparison
        non_trim = [e for e in loaded if e.event_type != "log_trimmed"]
        # We reserve 1 slot for the sentinel, so we keep _MAX_DISMISSAL_EVENTS - 1 = 999
        # of the newest events. From 1005 events, the 6 oldest (offset 0..5) are dropped.
        remaining_repos = {e.repo_name for e in non_trim}
        for i in range(6):
            assert f"Repo{i:04d}" not in remaining_repos, (
                f"Repo{i:04d} should have been dropped but was retained"
            )
        # The 999 newest (offset 6..1004) should all be present
        for i in range(6, 1005):
            assert f"Repo{i:04d}" in remaining_repos

    def test_log_trimmed_event_fields(self, tmp_path):
        """The log_trimmed sentinel has actor='system', correct event_type, non-empty reason."""
        events = _make_events(1002)
        _save_dismissed_full(dismissed_path(tmp_path), [], events)

        loaded = load_dismissal_events(dismissed_path(tmp_path))
        trim_events = [e for e in loaded if e.event_type == "log_trimmed"]
        assert len(trim_events) == 1
        sentinel = trim_events[0]
        assert sentinel.actor == "system"
        assert sentinel.event_type == "log_trimmed"
        assert sentinel.repo_name == "-"
        assert sentinel.reason != ""
        # 1002 events, keep_count=999, dropped=3
        assert "3" in sentinel.reason

    def test_trim_reason_mentions_dropped_count(self, tmp_path):
        """log_trimmed reason reports the exact number of dropped events.

        The trim reserves 1 slot for the sentinel itself, so dropping N events
        beyond the cap actually drops (N + 1) — the cap is sentinel-inclusive.
        """
        events = _make_events(_MAX_DISMISSAL_EVENTS + 7)
        _save_dismissed_full(dismissed_path(tmp_path), [], events)

        loaded = load_dismissal_events(dismissed_path(tmp_path))
        sentinel = next(e for e in loaded if e.event_type == "log_trimmed")
        # 1007 events, keep_count=999, dropped=8
        assert "8" in sentinel.reason

    def test_items_preserved_through_trim(self, tmp_path):
        """DismissedSuggestion items are unaffected by event log trimming."""
        from src.suggest_initiatives import DismissedSuggestion

        items = [
            DismissedSuggestion(
                repo_name="KeepMe",
                reason="test",
                dismissed_at="2026-01-01T00:00:00+00:00",
                dismissed_by="op",
            )
        ]
        events = _make_events(1001)
        _save_dismissed_full(dismissed_path(tmp_path), items, events)

        loaded_items = load_dismissed(dismissed_path(tmp_path))
        assert len(loaded_items) == 1
        assert loaded_items[0].repo_name == "KeepMe"
