from __future__ import annotations

import json
import time

from src.cache import ResponseCache


class TestResponseCache:
    def test_put_and_get(self, tmp_path):
        cache = ResponseCache(cache_dir=tmp_path / "cache", ttl=3600)
        url = "https://api.github.com/repos/user/repo/languages"

        cache.put(url, None, {"Python": 5000})
        result = cache.get(url, None)

        assert result == {"Python": 5000}
        assert cache.hits == 1
        assert cache.misses == 0

    def test_miss_on_empty(self, tmp_path):
        cache = ResponseCache(cache_dir=tmp_path / "cache", ttl=3600)
        result = cache.get("https://example.com/nothing", None)
        assert result is None
        assert cache.misses == 1

    def test_expired_entry(self, tmp_path):
        cache = ResponseCache(cache_dir=tmp_path / "cache", ttl=1)
        url = "https://api.github.com/test"

        cache.put(url, None, {"data": True})

        # Manually backdate the cache entry
        path = cache._path(url, None)
        entry = json.loads(path.read_text())
        entry["cached_at"] = time.time() - 10  # 10 seconds ago, TTL is 1s
        path.write_text(json.dumps(entry))

        result = cache.get(url, None)
        assert result is None
        assert cache.misses == 1

    def test_params_differentiate_keys(self, tmp_path):
        cache = ResponseCache(cache_dir=tmp_path / "cache", ttl=3600)
        url = "https://api.github.com/repos/user/repo/commits"

        cache.put(url, {"per_page": "10"}, [{"sha": "abc"}])
        cache.put(url, {"per_page": "5"}, [{"sha": "def"}])

        result1 = cache.get(url, {"per_page": "10"})
        result2 = cache.get(url, {"per_page": "5"})

        assert result1 == [{"sha": "abc"}]
        assert result2 == [{"sha": "def"}]

    def test_put_skips_payloads_that_contain_credentials(self, tmp_path):
        cache = ResponseCache(cache_dir=tmp_path / "cache", ttl=3600)
        url = "https://api.github.com/repos/user/repo"

        cache.put(
            url,
            {"access_token": "secret-param", "per_page": "10"},
            {"name": "repo", "nested": {"client_secret": "secret-value"}},
        )

        assert not cache._path(url, {"access_token": "secret-param", "per_page": "10"}).exists()

    def test_put_preserves_noncredential_secret_scanning_shape(self, tmp_path):
        cache = ResponseCache(cache_dir=tmp_path / "cache", ttl=3600)
        url = "https://api.github.com/repos/user/repo"
        response = {"security_and_analysis": {"secret_scanning": {"status": "enabled"}}}

        cache.put(url, None, response)

        assert cache.get(url, None) == response

    def test_cache_creates_dir(self, tmp_path):
        cache_dir = tmp_path / "deep" / "nested" / "cache"
        ResponseCache(cache_dir=cache_dir, ttl=3600)
        assert cache_dir.exists()
