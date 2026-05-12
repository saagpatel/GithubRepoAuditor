"""Tests for Arc G Sprint 13.4 — persistent suggestion cache TTL + v1→v2 schema migration."""

from __future__ import annotations

import json
from collections import OrderedDict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from src.suggest_initiatives import (
    _CACHE_TTL_DAYS,
    InitiativeSuggestion,
    load_suggestion_cache,
    save_suggestion_cache,
)


def _make_suggestion(name: str = "TestRepo") -> InitiativeSuggestion:
    return InitiativeSuggestion(
        repo_name=name,
        current_tier=1,
        target_tier=2,
        missing_requirements=["has_license"],
        rationale="test rationale",
        estimated_effort="small",
    )


def _iso(d: date) -> str:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc).isoformat()


def _fresh_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stale_ts() -> str:
    stale_date = date.today() - timedelta(days=_CACHE_TTL_DAYS + 5)
    return _iso(stale_date)


def _build_v2_file(tmp_path: Path, entries: list[dict]) -> Path:
    path = tmp_path / "suggestion-cache.json"
    path.write_text(json.dumps({"version": 2, "entries": entries}), encoding="utf-8")
    return path


class TestV1LegacyMigration:
    def test_v1_returns_empty(self, tmp_path, caplog):
        """v1 cache on disk → load returns empty OrderedDict (timestamps absent, can't TTL)."""
        import logging

        path = tmp_path / "suggestion-cache.json"
        path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "entries": [
                        {
                            "key": "k1",
                            "cost": 0.01,
                            "suggestions": [_make_suggestion().to_dict()],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        with caplog.at_level(logging.INFO, logger="src.suggest_initiatives"):
            result = load_suggestion_cache(path)

        assert result == OrderedDict()

    def test_v1_logs_legacy_message(self, tmp_path, caplog):
        """v1 load emits an INFO log explaining the cold-cache blip."""
        import logging

        path = tmp_path / "suggestion-cache.json"
        path.write_text(
            json.dumps({"version": 1, "entries": []}),
            encoding="utf-8",
        )
        with caplog.at_level(logging.INFO, logger="src.suggest_initiatives"):
            load_suggestion_cache(path)

        assert any("v1" in r.message and "dropping" in r.message for r in caplog.records)


class TestV2FreshEntries:
    def test_all_fresh_entries_returned(self, tmp_path):
        """v2 file with all-fresh timestamps → all entries returned."""
        ts = _fresh_ts()
        entries = [
            {
                "key": "k1",
                "cost": 0.05,
                "suggestions": [_make_suggestion("R1").to_dict()],
                "timestamp": ts,
            },
            {
                "key": "k2",
                "cost": 0.03,
                "suggestions": [_make_suggestion("R2").to_dict()],
                "timestamp": ts,
            },
        ]
        path = _build_v2_file(tmp_path, entries)
        result = load_suggestion_cache(path)

        assert list(result.keys()) == ["k1", "k2"]

    def test_fresh_file_not_rewritten(self, tmp_path):
        """v2 file with no stale entries is NOT rewritten (mtime unchanged)."""
        ts = _fresh_ts()
        entries = [
            {
                "key": "k1",
                "cost": 0.0,
                "suggestions": [_make_suggestion().to_dict()],
                "timestamp": ts,
            }
        ]
        path = _build_v2_file(tmp_path, entries)
        mtime_before = path.stat().st_mtime

        load_suggestion_cache(path)

        assert path.stat().st_mtime == mtime_before


class TestV2StaleEviction:
    def test_mixed_fresh_and_stale(self, tmp_path):
        """v2 file with mixed entries → only fresh entries returned."""
        fresh_ts = _fresh_ts()
        stale_ts = _stale_ts()
        entries = [
            {
                "key": "fresh",
                "cost": 0.01,
                "suggestions": [_make_suggestion("Fresh").to_dict()],
                "timestamp": fresh_ts,
            },
            {
                "key": "stale",
                "cost": 0.01,
                "suggestions": [_make_suggestion("Stale").to_dict()],
                "timestamp": stale_ts,
            },
        ]
        path = _build_v2_file(tmp_path, entries)
        result = load_suggestion_cache(path)

        assert "fresh" in result
        assert "stale" not in result

    def test_mixed_file_rewritten_with_only_fresh(self, tmp_path):
        """After eviction, the file on disk contains only surviving entries."""
        fresh_ts = _fresh_ts()
        stale_ts = _stale_ts()
        entries = [
            {
                "key": "fresh",
                "cost": 0.0,
                "suggestions": [_make_suggestion().to_dict()],
                "timestamp": fresh_ts,
            },
            {
                "key": "stale",
                "cost": 0.0,
                "suggestions": [_make_suggestion().to_dict()],
                "timestamp": stale_ts,
            },
        ]
        path = _build_v2_file(tmp_path, entries)
        load_suggestion_cache(path)

        on_disk = json.loads(path.read_text(encoding="utf-8"))
        keys_on_disk = [e["key"] for e in on_disk["entries"]]
        assert keys_on_disk == ["fresh"]

    def test_all_stale_returns_empty_and_rewrites(self, tmp_path):
        """All-stale v2 file → empty result + file rewritten with empty entries."""
        stale_ts = _stale_ts()
        entries = [
            {
                "key": "old1",
                "cost": 0.0,
                "suggestions": [_make_suggestion().to_dict()],
                "timestamp": stale_ts,
            }
        ]
        path = _build_v2_file(tmp_path, entries)
        result = load_suggestion_cache(path)

        assert result == OrderedDict()
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        assert on_disk["entries"] == []
        assert on_disk["version"] == 2


class TestCacheTTLBoundary:
    def test_exactly_ttl_days_old_is_kept(self, tmp_path):
        """Entry exactly _CACHE_TTL_DAYS old is kept (strictly-older-than rule)."""
        boundary_date = date.today() - timedelta(days=_CACHE_TTL_DAYS)
        ts = _iso(boundary_date)
        entries = [
            {
                "key": "boundary",
                "cost": 0.0,
                "suggestions": [_make_suggestion().to_dict()],
                "timestamp": ts,
            }
        ]
        path = _build_v2_file(tmp_path, entries)
        result = load_suggestion_cache(path)

        assert "boundary" in result

    def test_one_day_over_ttl_is_dropped(self, tmp_path):
        """Entry that is _CACHE_TTL_DAYS + 1 days old is evicted."""
        over_date = date.today() - timedelta(days=_CACHE_TTL_DAYS + 1)
        ts = _iso(over_date)
        entries = [
            {
                "key": "over",
                "cost": 0.0,
                "suggestions": [_make_suggestion().to_dict()],
                "timestamp": ts,
            }
        ]
        path = _build_v2_file(tmp_path, entries)
        result = load_suggestion_cache(path)

        assert "over" not in result


class TestSaveLoadRoundTrip:
    def test_round_trip_preserves_entries(self, tmp_path):
        """save → load returns the same keys and suggestion data."""
        path = tmp_path / "suggestion-cache.json"
        cache: OrderedDict[str, tuple[list[InitiativeSuggestion], float, str]] = OrderedDict()
        ts = _fresh_ts()
        cache["key1"] = ([_make_suggestion("RepoA")], 0.05, ts)
        cache["key2"] = ([_make_suggestion("RepoB")], 0.10, ts)

        save_suggestion_cache(path, cache)
        loaded = load_suggestion_cache(path)

        assert list(loaded.keys()) == ["key1", "key2"]
        for k in ("key1", "key2"):
            suggestions, cost, loaded_ts = loaded[k]
            orig_suggestions, orig_cost, orig_ts = cache[k]
            assert cost == orig_cost
            assert loaded_ts == orig_ts
            assert [s.repo_name for s in suggestions] == [s.repo_name for s in orig_suggestions]

    def test_save_writes_v2_schema(self, tmp_path):
        """save_suggestion_cache writes version=2 with timestamp fields."""
        path = tmp_path / "suggestion-cache.json"
        ts = _fresh_ts()
        cache: OrderedDict[str, tuple[list[InitiativeSuggestion], float, str]] = OrderedDict()
        cache["k"] = ([_make_suggestion()], 0.0, ts)

        save_suggestion_cache(path, cache)

        on_disk = json.loads(path.read_text(encoding="utf-8"))
        assert on_disk["version"] == 2
        assert "timestamp" in on_disk["entries"][0]

    def test_atomic_write_uses_tmp_rename(self, tmp_path):
        """save_suggestion_cache writes atomically (no .json tmp file left behind)."""
        path = tmp_path / "suggestion-cache.json"
        ts = _fresh_ts()
        cache: OrderedDict[str, tuple[list[InitiativeSuggestion], float, str]] = OrderedDict()
        cache["k"] = ([_make_suggestion()], 0.0, ts)

        save_suggestion_cache(path, cache)

        # No leftover tmp files
        tmp_files = list(tmp_path.glob(".suggestion_cache_tmp_*.json"))
        assert tmp_files == []
        assert path.exists()
