from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

CACHE_DIR = Path("output/.cache")
CACHE_TTL = 3600  # 1 hour


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
        path = self._path(url, params)
        entry = {
            "url": url,
            "params": params,
            "response": response,
            "cached_at": time.time(),
        }
        try:
            path.write_text(json.dumps(entry))
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
