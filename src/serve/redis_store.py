"""Redis/Upstash KVStore backend — selected when ``GHRA_REDIS_URL`` is set.

Kept in its own module so the optional ``redis`` dependency is imported only
when a Redis URL is configured (see ``hosting.build_kv_store``). Works against
Upstash via a ``rediss://`` TLS URL, suitable for the persistent FastAPI server
the engine deploys as (not a serverless function).
"""

from __future__ import annotations


class RedisKVStore:
    """KVStore backed by redis-py, satisfying the ``hosting.KVStore`` protocol."""

    def __init__(self, url: str) -> None:
        import redis  # type: ignore[import-not-found]  # optional dep; installed only when Redis is configured

        # decode_responses=True so get/set round-trip str, matching KVStore.
        self._client = redis.Redis.from_url(url, decode_responses=True)

    def get(self, key: str) -> str | None:
        value = self._client.get(key)
        return value if value is None else str(value)

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._client.setex(key, ttl_seconds, value)

    def incr(self, key: str, ttl_seconds: int) -> int:
        # Fixed-window: INCR, then stamp the TTL only on the first hit of the
        # window. Plain EXPIRE (no NX) works on every Redis server version, and
        # only the request that creates the key (count == 1) sets the expiry, so
        # the window is never extended by later increments.
        count = int(self._client.incr(key))
        if count == 1:
            self._client.expire(key, ttl_seconds)
        return count
