"""Hosting resilience: a pluggable KV store, report cache, and per-IP throttle.

A public free endpoint that scans the GitHub API cannot survive without two
guards: caching (so the same username isn't re-scanned on every hit, which
otherwise burns the shared rate limit) and per-IP throttling (so one client
can't exhaust it). Both sit behind a small ``KVStore`` protocol so the default
in-process backend works locally and in tests, while a Redis/Upstash backend
drops in via ``GHRA_REDIS_URL`` for a multi-instance deployment.

The in-memory store is thread-safe because the report route runs in FastAPI's
threadpool — concurrent workers share one store instance.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Callable, Protocol, TypeVar, runtime_checkable

_V = TypeVar("_V")

# Defaults chosen for a free public tier; all overridable via env.
DEFAULT_REPORT_TTL_SECONDS = 3600  # 1h — within the 1–6h cache window.
DEFAULT_RATE_LIMIT = 20  # requests per window, per IP.
DEFAULT_RATE_WINDOW_SECONDS = 3600  # 1h.

REPORT_TTL_ENV_VAR = "GHRA_REPORT_TTL_SECONDS"
RATE_LIMIT_ENV_VAR = "GHRA_RATE_LIMIT"
RATE_WINDOW_ENV_VAR = "GHRA_RATE_WINDOW_SECONDS"
REDIS_URL_ENV_VAR = "GHRA_REDIS_URL"


@runtime_checkable
class KVStore(Protocol):
    """Minimal string KV interface backing both the cache and the throttle."""

    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str, ttl_seconds: int) -> None: ...

    def incr(self, key: str, ttl_seconds: int) -> int:
        """Increment a counter, setting its TTL on first creation; return count."""
        ...


class InMemoryKVStore:
    """Thread-safe, expiring in-process KV store (default backend).

    Entries expire lazily on access; to keep memory bounded under churn (e.g. a
    counter per unique client IP), each dict is swept of expired entries once it
    grows past ``reap_threshold``. The Redis backend relies on native TTL instead.
    """

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        reap_threshold: int = 10_000,
    ) -> None:
        self._clock = clock
        self._reap_threshold = reap_threshold
        self._lock = threading.Lock()
        self._values: dict[str, tuple[float, str]] = {}
        self._counters: dict[str, tuple[float, int]] = {}

    def _reap_locked(self, store: dict[str, tuple[float, _V]], now: float) -> None:
        """Drop expired entries when a store outgrows the threshold (lock held)."""
        if len(store) <= self._reap_threshold:
            return
        for key in [k for k, (expiry, _) in store.items() if expiry <= now]:
            del store[key]

    def get(self, key: str) -> str | None:
        with self._lock:
            now = self._clock()
            entry = self._values.get(key)
            if entry is None:
                return None
            expiry, value = entry
            if expiry <= now:
                del self._values[key]
                return None
            return value

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        with self._lock:
            now = self._clock()
            self._reap_locked(self._values, now)
            self._values[key] = (now + ttl_seconds, value)

    def incr(self, key: str, ttl_seconds: int) -> int:
        with self._lock:
            now = self._clock()
            self._reap_locked(self._counters, now)
            entry = self._counters.get(key)
            if entry is None or entry[0] <= now:
                # New window: start at 1 and stamp the expiry.
                self._counters[key] = (now + ttl_seconds, 1)
                return 1
            expiry, count = entry
            count += 1
            self._counters[key] = (expiry, count)  # keep the original window
            return count


class ReportCache:
    """Cache serialized report payloads by (normalized) username."""

    def __init__(self, store: KVStore, ttl_seconds: int) -> None:
        self._store = store
        self._ttl = ttl_seconds

    @property
    def enabled(self) -> bool:
        return self._ttl > 0

    @staticmethod
    def _key(username: str) -> str:
        return f"report:{username.lower()}"

    def get(self, username: str) -> dict | None:
        if not self.enabled:
            return None
        raw = self._store.get(self._key(username))
        return json.loads(raw) if raw is not None else None

    def put(self, username: str, payload: dict) -> None:
        if not self.enabled:
            return
        self._store.set(self._key(username), json.dumps(payload), self._ttl)


class RateLimiter:
    """Fixed-window per-IP throttle. A non-positive limit disables it."""

    def __init__(self, store: KVStore, limit: int, window_seconds: int) -> None:
        self._store = store
        self._limit = limit
        self._window = window_seconds

    @property
    def enabled(self) -> bool:
        return self._limit > 0

    def allow(self, ip: str) -> bool:
        if not self.enabled:
            return True
        count = self._store.incr(f"rl:{ip}", self._window)
        return count <= self._limit


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def build_kv_store() -> KVStore:
    """Select the KV backend: Redis when ``GHRA_REDIS_URL`` is set, else memory."""
    url = os.environ.get(REDIS_URL_ENV_VAR, "").strip()
    if url:
        # Lazy import so the redis dependency is only needed when configured.
        from src.serve.redis_store import RedisKVStore

        return RedisKVStore(url)
    return InMemoryKVStore()


def build_report_cache(store: KVStore) -> ReportCache:
    return ReportCache(store, _env_int(REPORT_TTL_ENV_VAR, DEFAULT_REPORT_TTL_SECONDS))


def build_rate_limiter(store: KVStore) -> RateLimiter:
    return RateLimiter(
        store,
        _env_int(RATE_LIMIT_ENV_VAR, DEFAULT_RATE_LIMIT),
        _env_int(RATE_WINDOW_ENV_VAR, DEFAULT_RATE_WINDOW_SECONDS),
    )
