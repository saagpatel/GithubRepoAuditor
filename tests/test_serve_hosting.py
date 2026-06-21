"""Tests for src/serve/hosting.py — KV store, report cache, per-IP throttle."""

from __future__ import annotations

import pytest

from src.serve.hosting import (
    InMemoryKVStore,
    RateLimiter,
    ReportCache,
    build_rate_limiter,
    build_report_cache,
)


class FakeClock:
    """Manually-advanced monotonic clock for deterministic expiry tests."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# ---------------------------------------------------------------------------
# InMemoryKVStore
# ---------------------------------------------------------------------------
def test_kv_set_get_roundtrip() -> None:
    store = InMemoryKVStore()
    store.set("k", "v", ttl_seconds=60)
    assert store.get("k") == "v"


def test_kv_missing_key_returns_none() -> None:
    assert InMemoryKVStore().get("nope") is None


def test_kv_value_expires() -> None:
    clock = FakeClock()
    store = InMemoryKVStore(clock=clock)
    store.set("k", "v", ttl_seconds=30)
    clock.advance(29)
    assert store.get("k") == "v"
    clock.advance(2)  # now 31s elapsed, past the 30s TTL
    assert store.get("k") is None


def test_kv_incr_counts_within_window_then_resets() -> None:
    clock = FakeClock()
    store = InMemoryKVStore(clock=clock)
    assert store.incr("c", ttl_seconds=10) == 1
    assert store.incr("c", ttl_seconds=10) == 2
    assert store.incr("c", ttl_seconds=10) == 3
    clock.advance(11)  # window elapsed
    assert store.incr("c", ttl_seconds=10) == 1


def test_kv_incr_keeps_original_window() -> None:
    clock = FakeClock()
    store = InMemoryKVStore(clock=clock)
    store.incr("c", ttl_seconds=10)
    clock.advance(6)
    store.incr("c", ttl_seconds=10)  # must NOT extend the window
    clock.advance(5)  # 11s total — original window has elapsed
    assert store.incr("c", ttl_seconds=10) == 1


def test_kv_reaps_expired_counters_past_threshold() -> None:
    clock = FakeClock()
    store = InMemoryKVStore(clock=clock, reap_threshold=3)
    for i in range(4):  # 4 distinct keys, each a 10s window
        store.incr(f"ip-{i}", ttl_seconds=10)
    assert len(store._counters) == 4  # below/at threshold, not yet swept
    clock.advance(11)  # all four windows expire
    store.incr("trigger", ttl_seconds=10)  # size > threshold → sweep runs
    # The four expired counters are gone; only the fresh "trigger" remains.
    assert set(store._counters) == {"trigger"}


# ---------------------------------------------------------------------------
# ReportCache
# ---------------------------------------------------------------------------
def test_report_cache_roundtrips_dict() -> None:
    cache = ReportCache(InMemoryKVStore(), ttl_seconds=3600)
    payload = {"username": "octocat", "repos": [{"x": 1}]}
    cache.put("octocat", payload)
    assert cache.get("octocat") == payload


def test_report_cache_is_case_insensitive() -> None:
    cache = ReportCache(InMemoryKVStore(), ttl_seconds=3600)
    cache.put("OctoCat", {"username": "OctoCat", "repos": []})
    assert cache.get("octocat") is not None


def test_report_cache_miss_returns_none() -> None:
    cache = ReportCache(InMemoryKVStore(), ttl_seconds=3600)
    assert cache.get("ghost") is None


def test_report_cache_disabled_when_ttl_zero() -> None:
    cache = ReportCache(InMemoryKVStore(), ttl_seconds=0)
    assert cache.enabled is False
    cache.put("octocat", {"username": "octocat", "repos": []})
    assert cache.get("octocat") is None


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------
def test_rate_limiter_allows_up_to_limit_then_blocks() -> None:
    limiter = RateLimiter(InMemoryKVStore(), limit=3, window_seconds=60)
    assert [limiter.allow("1.2.3.4") for _ in range(4)] == [True, True, True, False]


def test_rate_limiter_is_per_ip() -> None:
    limiter = RateLimiter(InMemoryKVStore(), limit=1, window_seconds=60)
    assert limiter.allow("1.1.1.1") is True
    assert limiter.allow("2.2.2.2") is True  # different IP, own budget
    assert limiter.allow("1.1.1.1") is False


def test_rate_limiter_window_resets() -> None:
    clock = FakeClock()
    limiter = RateLimiter(InMemoryKVStore(clock=clock), limit=1, window_seconds=60)
    assert limiter.allow("1.1.1.1") is True
    assert limiter.allow("1.1.1.1") is False
    clock.advance(61)
    assert limiter.allow("1.1.1.1") is True


def test_rate_limiter_disabled_when_limit_nonpositive() -> None:
    limiter = RateLimiter(InMemoryKVStore(), limit=0, window_seconds=60)
    assert limiter.enabled is False
    assert all(limiter.allow("1.1.1.1") for _ in range(100))


# ---------------------------------------------------------------------------
# Env-driven builders
# ---------------------------------------------------------------------------
def test_builders_read_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GHRA_REPORT_TTL_SECONDS", "120")
    monkeypatch.setenv("GHRA_RATE_LIMIT", "5")
    monkeypatch.setenv("GHRA_RATE_WINDOW_SECONDS", "30")
    store = InMemoryKVStore()
    cache = build_report_cache(store)
    limiter = build_rate_limiter(store)
    cache.put("u", {"username": "u", "repos": []})
    assert cache.get("u") is not None
    assert [limiter.allow("ip") for _ in range(6)] == [True] * 5 + [False]


def test_builders_fall_back_to_defaults_on_bad_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GHRA_RATE_LIMIT", "not-a-number")
    limiter = build_rate_limiter(InMemoryKVStore())
    assert limiter.enabled is True  # default 20, not crashed
