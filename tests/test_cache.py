from __future__ import annotations

import json
import time

import pytest

from github_repo_auditor.cache import ResponseCache


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

        # Manually backdate the process-local entry.
        cache._entries[cache._key(url, None)] = (time.time() - 10, {"data": True})

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

        assert cache.get(url, {"access_token": "secret-param", "per_page": "10"}) is None

    def test_put_skips_embedded_url_credentials(self, tmp_path):
        cache = ResponseCache(cache_dir=tmp_path / "cache", ttl=3600)
        url = "https://operator:opaque-value@example.invalid/repos"

        cache.put(url, None, {"status": "ok"})

        assert cache.get(url, None) is None

    def test_put_skips_hyphenated_credential_alias(self, tmp_path):
        cache = ResponseCache(cache_dir=tmp_path / "cache", ttl=3600)
        url = "https://api.github.com/repos/user/repo"

        cache.put(url, None, {"access-token": "opaque-value"})

        assert cache.get(url, None) is None

    @pytest.mark.parametrize("alias", ["auth-token", "refresh_token", "x-api-key"])
    def test_put_skips_additional_credential_aliases(self, tmp_path, alias):
        cache = ResponseCache(cache_dir=tmp_path / "cache", ttl=3600)
        url = "https://api.github.com/repos/user/repo"

        cache.put(url, None, {alias: "opaque-value"})

        assert cache.get(url, None) is None

    def test_put_skips_sensitive_url_fragment(self, tmp_path):
        cache = ResponseCache(cache_dir=tmp_path / "cache", ttl=3600)
        url = "https://example.invalid/callback#access-token=opaque-value"

        cache.put(url, None, {"status": "ok"})

        assert cache.get(url, None) is None

    def test_put_skips_additional_provider_token_family(self, tmp_path):
        cache = ResponseCache(cache_dir=tmp_path / "cache", ttl=3600)
        url = "https://api.github.com/repos/user/repo"

        cache.put(url, None, {"note": "secret_" + ("a" * 40)})

        assert cache.get(url, None) is None

    def test_put_skips_credential_shaped_value_under_benign_key(self, tmp_path):
        cache = ResponseCache(cache_dir=tmp_path / "cache", ttl=3600)
        url = "https://api.github.com/repos/user/repo"
        response = {"note": "ghp_" + ("a" * 36)}

        cache.put(url, None, response)

        assert cache.get(url, None) is None

    def test_put_skips_credential_inside_serialized_payload(self, tmp_path):
        cache = ResponseCache(cache_dir=tmp_path / "cache", ttl=3600)
        url = "https://api.github.com/repos/user/repo"
        response = json.dumps({"note": "github_pat_" + ("a" * 40)})

        cache.put(url, None, response)

        assert cache.get(url, None) is None

    def test_put_skips_private_key_material_under_benign_key(self, tmp_path):
        cache = ResponseCache(cache_dir=tmp_path / "cache", ttl=3600)
        url = "https://api.github.com/repos/user/repo"
        response = {"content": "-----BEGIN PRIVATE KEY-----\nnot-a-real-key"}

        cache.put(url, None, response)

        assert cache.get(url, None) is None

    def test_put_preserves_noncredential_secret_scanning_shape(self, tmp_path):
        cache = ResponseCache(cache_dir=tmp_path / "cache", ttl=3600)
        url = "https://api.github.com/repos/user/repo"
        response = {"security_and_analysis": {"secret_scanning": {"status": "enabled"}}}

        cache.put(url, None, response)

        assert cache.get(url, None) == response

    def test_cache_does_not_create_disk_directory(self, tmp_path):
        cache_dir = tmp_path / "deep" / "nested" / "cache"
        ResponseCache(cache_dir=cache_dir, ttl=3600)
        assert not cache_dir.exists()

    def test_cache_never_writes_response_payload_to_disk(self, tmp_path):
        cache_dir = tmp_path / "cache"
        cache = ResponseCache(cache_dir=cache_dir, ttl=3600)
        url = "https://api.github.com/repos/user/repo/contents/README.md"

        cache.put(url, None, {"content": "repository-authored text"})

        assert cache.get(url, None) == {"content": "repository-authored text"}
        assert not cache_dir.exists()
