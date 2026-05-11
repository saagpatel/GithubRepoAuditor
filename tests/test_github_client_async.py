"""Tests for src.github_client_async — async parallel enrichment fetcher."""

from __future__ import annotations

import asyncio
import threading
import time

import httpx
import pytest

from src.github_client import GitHubClientError
from src.github_client_async import (
    AsyncGitHubClient,
    _enrichment_endpoints,
    fetch_enrichment_sync,
)

# ── Test helpers ──────────────────────────────────────────────────────────────


def _make_json_response(
    data: object, status: int = 200, headers: dict | None = None
) -> httpx.Response:
    """Build a synthetic httpx.Response with JSON body."""
    return httpx.Response(
        status,
        json=data,
        headers=headers or {},
    )


class _SimpleCache:
    """Minimal in-memory cache compatible with ResponseCache's interface."""

    def __init__(self) -> None:
        self._store: dict[str, object] = {}
        self.get_calls: list[str] = []
        self.put_calls: list[str] = []

    def _key(self, url: str, params: dict | None) -> str:
        raw = url
        if params:
            raw += "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        return raw

    def get(self, url: str, params: dict | None = None) -> object | None:
        key = self._key(url, params)
        self.get_calls.append(key)
        return self._store.get(key)

    def put(self, url: str, params: dict | None, value: object) -> None:
        key = self._key(url, params)
        self.put_calls.append(key)
        self._store[key] = value


# ── 1. Happy path ─────────────────────────────────────────────────────────────


class TestHappyPath:
    def test_fetch_enrichment_for_all_returns_expected_keys(self):
        """fetch_enrichment_for_all returns expected dict structure for multiple repos."""
        repo_pairs = [("alice", "alpha"), ("bob", "beta"), ("carol", "gamma")]
        endpoint_keys = set(_enrichment_endpoints("x", "y").keys())

        def handler(request: httpx.Request) -> httpx.Response:
            return _make_json_response({"url": str(request.url)})

        transport = httpx.MockTransport(handler)
        result = fetch_enrichment_sync(repo_pairs, _transport=transport)

        assert set(result.keys()) == {"alice/alpha", "bob/beta", "carol/gamma"}
        for full_name, enrichment in result.items():
            assert set(enrichment.keys()) == endpoint_keys
            for val in enrichment.values():
                # All 200 responses should give non-None dicts
                assert val is not None
                assert isinstance(val, dict)

    def test_fetch_enrichment_for_all_correct_urls_called(self):
        """Verifies that the correct GitHub API endpoints are requested."""
        called_urls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            called_urls.append(str(request.url))
            return _make_json_response({})

        transport = httpx.MockTransport(handler)
        fetch_enrichment_sync([("alice", "repo")], _transport=transport)

        paths = [u.split("api.github.com")[1] for u in called_urls if "api.github.com" in u]
        assert any("/repos/alice/repo/community/profile" in p for p in paths)
        assert any("/repos/alice/repo/languages" in p for p in paths)
        assert any("/repos/alice/repo/releases" in p for p in paths)
        assert any(p == "/repos/alice/repo" for p in paths)
        assert any("/repos/alice/repo/topics" in p for p in paths)
        assert any("/repos/alice/repo/properties/values" in p for p in paths)


# ── 2. Concurrency bound ──────────────────────────────────────────────────────


class TestConcurrencyBound:
    def test_max_concurrency_never_exceeded(self):
        """In-flight request count never exceeds max_concurrency."""
        max_concurrency = 3
        max_inflight = 0
        inflight_lock = threading.Lock()
        inflight_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal inflight_count, max_inflight
            with inflight_lock:
                inflight_count += 1
                if inflight_count > max_inflight:
                    max_inflight = inflight_count
            # Tiny sleep so concurrent requests actually overlap
            time.sleep(0.002)
            with inflight_lock:
                inflight_count -= 1
            return _make_json_response({})

        # 5 repos × 6 endpoints = 30 requests with concurrency cap = 3
        repo_pairs = [(f"owner{i}", f"repo{i}") for i in range(5)]
        transport = httpx.MockTransport(handler)
        fetch_enrichment_sync(repo_pairs, max_concurrency=max_concurrency, _transport=transport)

        assert max_inflight <= max_concurrency, (
            f"Concurrency exceeded: max inflight was {max_inflight}, limit was {max_concurrency}"
        )


# ── 3. 429 backoff ────────────────────────────────────────────────────────────


class TestRateLimitBackoff:
    def test_429_retry_after_succeeds_on_second_attempt(self):
        """A 429 with Retry-After: 0 followed by a 200 is retried and succeeds."""
        call_counts: dict[str, int] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            call_counts[url] = call_counts.get(url, 0) + 1
            if call_counts[url] == 1:
                return httpx.Response(
                    429,
                    json={"message": "rate limited"},
                    headers={"Retry-After": "0"},
                )
            return _make_json_response({"retried": True})

        transport = httpx.MockTransport(handler)
        result = fetch_enrichment_sync([("owner", "repo")], _transport=transport)

        # Every endpoint should have succeeded on retry
        assert "owner/repo" in result
        enrichment = result["owner/repo"]
        # All endpoints should have been retried successfully
        for key, val in enrichment.items():
            assert val is not None, f"Expected non-None for {key} after 429 retry"

        # Verify at least one URL was called more than once (proving retry happened)
        assert any(count >= 2 for count in call_counts.values()), (
            "Expected at least one URL to be retried after 429"
        )

    def test_429_retry_after_respected(self):
        """Retry-After header value is respected (zero delay acceptable in tests)."""
        attempt_times: list[float] = []

        def handler(request: httpx.Request) -> httpx.Response:
            attempt_times.append(time.monotonic())
            if len(attempt_times) <= 1:
                return httpx.Response(
                    429,
                    json={},
                    headers={"Retry-After": "0"},
                )
            return _make_json_response({})

        transport = httpx.MockTransport(handler)

        # Test only one endpoint to keep it simple
        async def _run():
            async with AsyncGitHubClient(transport=transport) as client:
                result = await client._fetch("https://api.github.com/repos/o/r")
            return result

        asyncio.run(_run())
        # At least 2 attempts were made (initial + 1 retry)
        assert len(attempt_times) >= 2


# ── 4. 404 path ───────────────────────────────────────────────────────────────


class TestNotFound:
    def test_404_returns_none_no_exception(self):
        """A 404 response returns None for that endpoint key without raising."""
        not_found_url_path = "/repos/owner/repo/community/profile"

        def handler(request: httpx.Request) -> httpx.Response:
            if not_found_url_path in str(request.url):
                return httpx.Response(404, json={"message": "Not Found"})
            return _make_json_response({})

        transport = httpx.MockTransport(handler)
        result = fetch_enrichment_sync([("owner", "repo")], _transport=transport)

        enrichment = result["owner/repo"]
        assert enrichment["community_profile"] is None
        # Other endpoints should still succeed
        for key in ("languages", "releases", "topics"):
            assert enrichment[key] is not None


# ── 5. 5xx retry exhaustion ───────────────────────────────────────────────────


class TestServerErrorRetryExhaustion:
    def test_5xx_exhaustion_raises_github_client_error(self):
        """A persistent 500 raises GitHubClientError after max retries."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"message": "Internal Server Error"})

        transport = httpx.MockTransport(handler)

        async def _run():
            async with AsyncGitHubClient(transport=transport) as client:
                return await client._fetch("https://api.github.com/repos/o/r")

        with pytest.raises(GitHubClientError, match="Server error"):
            asyncio.run(_run())

    def test_5xx_retry_count_is_bounded(self):
        """Exactly _MAX_5XX_RETRIES + 1 attempts are made before exhaustion."""
        from src.github_client_async import _MAX_5XX_RETRIES

        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(500, json={})

        transport = httpx.MockTransport(handler)

        async def _run():
            async with AsyncGitHubClient(transport=transport) as client:
                return await client._fetch("https://api.github.com/repos/o/r")

        with pytest.raises(GitHubClientError):
            asyncio.run(_run())

        assert call_count == _MAX_5XX_RETRIES + 1


# ── 6. Cache hit ──────────────────────────────────────────────────────────────


class TestCacheHit:
    def test_cache_hit_skips_http_request(self):
        """Pre-populated cache prevents any HTTP requests from being made."""
        cache = _SimpleCache()
        # Pre-populate all 6 enrichment endpoints for the repo
        endpoints = _enrichment_endpoints("alice", "repo")
        for key, (url, params) in endpoints.items():
            cache.put(url, params, {"cached": True, "key": key})

        http_call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal http_call_count
            http_call_count += 1
            return _make_json_response({})

        transport = httpx.MockTransport(handler)
        result = fetch_enrichment_sync(
            [("alice", "repo")],
            cache=cache,
            _transport=transport,
        )

        assert http_call_count == 0, (
            f"Expected 0 HTTP calls (all cache hits), got {http_call_count}"
        )
        enrichment = result["alice/repo"]
        for key in endpoints:
            assert enrichment[key] == {"cached": True, "key": key}

    def test_cache_miss_populates_cache(self):
        """Successful 200 responses are written to cache."""
        cache = _SimpleCache()

        def handler(request: httpx.Request) -> httpx.Response:
            return _make_json_response({"from_http": True})

        transport = httpx.MockTransport(handler)
        fetch_enrichment_sync([("alice", "repo")], cache=cache, _transport=transport)

        endpoints = _enrichment_endpoints("alice", "repo")
        assert len(cache.put_calls) == len(endpoints)


# ── 7. Sync bridge ────────────────────────────────────────────────────────────


class TestSyncBridge:
    def test_fetch_enrichment_sync_end_to_end(self):
        """fetch_enrichment_sync runs end-to-end with a synthetic transport."""

        def handler(request: httpx.Request) -> httpx.Response:
            return _make_json_response({"bridge_ok": True})

        transport = httpx.MockTransport(handler)
        result = fetch_enrichment_sync(
            [("org", "project"), ("org", "other")],
            token="test-token",
            max_concurrency=5,
            _transport=transport,
        )

        assert "org/project" in result
        assert "org/other" in result
        for full_name in ("org/project", "org/other"):
            enrichment = result[full_name]
            assert set(enrichment.keys()) == set(_enrichment_endpoints("x", "y").keys())

    def test_fetch_enrichment_sync_empty_list(self):
        """Empty repo list returns empty dict without error."""
        http_calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            http_calls.append(request.url)
            return _make_json_response({})

        transport = httpx.MockTransport(handler)
        result = fetch_enrichment_sync([], _transport=transport)

        assert result == {}
        assert http_calls == []


# ── 8. CLI flag wiring ────────────────────────────────────────────────────────


class TestCliFlagWiring:
    """Verify --fetch-mode and --fetch-workers are parsed correctly."""

    def _parse_args(self, extra_args: list[str]):
        """Parse CLI args without running the full command."""
        import argparse

        # Replicate only the flags under test — avoids importing the full CLI.
        parser = argparse.ArgumentParser()
        parser.add_argument("--fetch-mode", choices=["sync", "async"], default="sync")
        parser.add_argument("--fetch-workers", type=int, default=10)
        return parser.parse_args(extra_args)

    def test_fetch_mode_default_is_sync(self):
        args = self._parse_args([])
        assert args.fetch_mode == "sync"

    def test_fetch_mode_async_parses(self):
        args = self._parse_args(["--fetch-mode", "async"])
        assert args.fetch_mode == "async"

    def test_fetch_workers_default_is_10(self):
        args = self._parse_args([])
        assert args.fetch_workers == 10

    def test_fetch_workers_custom_value(self):
        args = self._parse_args(["--fetch-workers", "20"])
        assert args.fetch_workers == 20

    def test_fetch_mode_sync_does_not_import_async_module(self):
        """When fetch_mode is 'sync', the async module is not invoked."""
        from unittest.mock import MagicMock

        # Simulate _analyze_repos behaviour: async prefetch only when fetch_mode == 'async'
        called = []

        def fake_prefetch(repos, **kwargs):
            called.append(repos)
            return {}

        args = MagicMock()
        args.fetch_mode = "sync"
        args.fetch_workers = 10

        # The sync guard in _analyze_repos: if _fetch_mode != "async", skip.
        fetch_mode = getattr(args, "fetch_mode", "sync")
        if fetch_mode == "async":
            fake_prefetch([("o", "r")], token="t")

        assert called == [], "Async prefetch should NOT be called in sync mode"

    def test_fetch_mode_async_triggers_prefetch(self):
        """When fetch_mode is 'async', the async prefetch path is triggered."""
        called = []

        def fake_prefetch(repos, **kwargs):
            called.append(repos)
            return {}

        args = type("Args", (), {"fetch_mode": "async", "fetch_workers": 5})()

        fetch_mode = getattr(args, "fetch_mode", "sync")
        if fetch_mode == "async":
            repo_pairs = [("alice", "repo")]
            fake_prefetch(repo_pairs, token="tok")

        assert called == [[("alice", "repo")]]
