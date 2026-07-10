from __future__ import annotations

import hashlib
import json
import time
from urllib.parse import parse_qsl, urlparse
from pathlib import Path
from typing import Any

CACHE_DIR = Path("output/.cache")
CACHE_TTL = 3600  # 1 hour
_SENSITIVE_FIELD_NAMES = frozenset(
    {
        "access_token",
    "api_key",
    "apikey",
    "authorization",
        "client_secret",
        "credential",
    "password",
    "private_key",
        "github_token",
        "secret",
        "token",
    }
)


def contains_sensitive_data(value: Any) -> bool:
    """Return whether JSON-compatible data contains a credential field."""
    if isinstance(value, dict):
        return any(
            str(key).lower() in _SENSITIVE_FIELD_NAMES or contains_sensitive_data(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(contains_sensitive_data(item) for item in value)
    if isinstance(value, tuple):
        return any(contains_sensitive_data(item) for item in value)
    return False


def _url_has_sensitive_query(url: str) -> bool:
    return any(name.lower() in _SENSITIVE_FIELD_NAMES for name, _value in parse_qsl(urlparse(url).query))


class ResponseCache:
    """File-based API response cache with TTL expiry."""

    def __init__(
        self,
        cache_dir: Path = CACHE_DIR,
        ttl: int = CACHE_TTL,
    ) -> None:
        self.cache_dir = cache_dir
        self.ttl = ttl
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.misses = 0

    def get(self, url: str, params: dict | None = None) -> object | None:
        """Return cached response data, or None if expired/missing."""
        path = self._path(url, params)
        if not path.is_file():
            self.misses += 1
            return None

        try:
            data = json.loads(path.read_text())
            cached_at = data.get("cached_at", 0)
            if time.time() - cached_at > self.ttl:
                path.unlink(missing_ok=True)
                self.misses += 1
                return None
            self.hits += 1
            return data["response"]
        except (json.JSONDecodeError, KeyError, OSError):
            self.misses += 1
            return None

    def put(
        self,
        url: str,
        params: dict | None,
        response: object,
    ) -> None:
        """Store response data with current timestamp."""
        if _url_has_sensitive_query(url) or contains_sensitive_data(params) or contains_sensitive_data(response):
            return
        path = self._path(url, params)
        entry = {
            "url": url,
            "params": params,
            "response": response,
            "cached_at": time.time(),
        }
        try:
            path.write_text(json.dumps(entry))  # lgtm [py/clear-text-storage-sensitive-data] redacted above
        except OSError:
            pass  # Cache write failure is non-fatal

    def _key(self, url: str, params: dict | None) -> str:
        """SHA256 hash of URL + sorted params."""
        raw = url
        if params:
            raw += "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _path(self, url: str, params: dict | None) -> Path:
        return self.cache_dir / f"{self._key(url, params)}.json"
