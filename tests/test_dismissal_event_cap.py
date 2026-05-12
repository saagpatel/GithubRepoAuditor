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
        """Writing 1005 events results in 1000 kept + 1 log_trimmed = 1001 total."""
        events = _make_events(1005)
        _save_dismissed_full(dismissed_path(tmp_path), [], events)

        loaded = load_dismissal_events(dismissed_path(tmp_path))
        # 1000 survivors + 1 log_trimmed sentinel
        assert len(loaded) == _MAX_DISMISSAL_EVENTS + 1

    def test_trim_drops_oldest(self, tmp_path):
        """After trim, the retained events are the newest ones (highest occurred_at)."""
        events = _make_events(1005)
        _save_dismissed_full(dismissed_path(tmp_path), [], events)

        loaded = load_dismissal_events(dismissed_path(tmp_path))
        # Remove the log_trimmed sentinel for comparison
        non_trim = [e for e in loaded if e.event_type != "log_trimmed"]
        # The 5 oldest events (offset 0..4) should have been dropped
        remaining_repos = {e.repo_name for e in non_trim}
        for i in range(5):
            assert f"Repo{i:04d}" not in remaining_repos, (
                f"Repo{i:04d} should have been dropped but was retained"
            )
        # The 1000 newest (offset 5..1004) should all be present
        for i in range(5, 1005):
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
        assert "2" in sentinel.reason  # "trimmed 2 oldest events"

    def test_trim_reason_mentions_dropped_count(self, tmp_path):
        """log_trimmed reason reports the exact number of dropped events."""
        dropped = 7
        events = _make_events(_MAX_DISMISSAL_EVENTS + dropped)
        _save_dismissed_full(dismissed_path(tmp_path), [], events)

        loaded = load_dismissal_events(dismissed_path(tmp_path))
        sentinel = next(e for e in loaded if e.event_type == "log_trimmed")
        assert str(dropped) in sentinel.reason

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
