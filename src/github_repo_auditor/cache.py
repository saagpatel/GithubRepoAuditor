from __future__ import annotations

import copy
import hashlib
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

CACHE_DIR = Path("output/.cache")
CACHE_TTL = 3600  # 1 hour
_SENSITIVE_FIELD_NAMES = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "auth_token",
        "authorization",
        "client_secret",
        "credential",
        "password",
        "private_key",
        "refresh_token",
        "github_token",
        "secret",
        "token",
        "x_api_key",
    }
)
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)(?<![a-z0-9_-])(?:access[-_]?token|auth[-_]?token|refresh[-_]?token|"
    r"x[-_]?api[-_]?key|api[-_]?key|apikey|authorization|client[-_]?secret|"
    r"credential|github[-_]?token|password|private[-_]?key|secret|token)"
    r"\s*[:=]\s*[^\s,;}&\]]+"
)
_URL_WITH_USERINFO = re.compile(r"https?://[^/@\s]+@", re.IGNORECASE)
_SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[bpors]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bsecret_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bntn_[A-Za-z0-9]{20,}\b"),
    re.compile(r"-----BEGIN (?:(?:RSA|EC|DSA|OPENSSH|ENCRYPTED) )?PRIVATE KEY-----"),
)


def _normalized_field_name(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).casefold()).strip("_")


def contains_sensitive_data(value: Any) -> bool:
    """Return whether JSON-compatible data contains credential data."""
    if isinstance(value, dict):
        return any(
            _normalized_field_name(key) in _SENSITIVE_FIELD_NAMES
            or contains_sensitive_data(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(contains_sensitive_data(item) for item in value)
    if isinstance(value, tuple):
        return any(contains_sensitive_data(item) for item in value)
    if isinstance(value, str):
        return (
            any(pattern.search(value) for pattern in _SENSITIVE_VALUE_PATTERNS)
            or _SENSITIVE_ASSIGNMENT.search(value) is not None
            or _URL_WITH_USERINFO.search(value) is not None
        )
    return False


def _url_has_sensitive_components(url: str) -> bool:
    parsed = urlparse(url)
    names = (
        name
        for component in (parsed.query, parsed.fragment)
        for name, _value in parse_qsl(component)
    )
    return any(_normalized_field_name(name) in _SENSITIVE_FIELD_NAMES for name in names)


def _url_has_embedded_credentials(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.username is not None or parsed.password is not None


class ResponseCache:
    """Process-local API response cache with TTL expiry.

    Response payloads can contain arbitrary repository-authored or provider-
    returned text.  Keep them in memory for the lifetime of the caller instead
    of persisting cleartext JSON under ``output/.cache``.  ``cache_dir`` remains
    an accepted compatibility parameter for callers that previously supplied a
    directory, but it is intentionally unused.
    """

    def __init__(
        self,
        cache_dir: Path = CACHE_DIR,
        ttl: int = CACHE_TTL,
    ) -> None:
        self.cache_dir = cache_dir
        self.ttl = ttl
        self._entries: dict[str, tuple[float, Any]] = {}
        self.hits = 0
        self.misses = 0

    def get(self, url: str, params: dict | None = None) -> object | None:
        """Return cached response data, or None if expired/missing."""
        key = self._key(url, params)
        entry = self._entries.get(key)
        if entry is None:
            self.misses += 1
            return None

        cached_at, response = entry
        if time.time() - cached_at > self.ttl:
            self._entries.pop(key, None)
            self.misses += 1
            return None
        self.hits += 1
        return copy.deepcopy(response)

    def put(
        self,
        url: str,
        params: dict | None,
        response: object,
    ) -> None:
        """Store response data in memory with the current timestamp."""
        if (
            _url_has_sensitive_components(url)
            or _url_has_embedded_credentials(url)
            or contains_sensitive_data(url)
            or contains_sensitive_data(params)
            or contains_sensitive_data(response)
        ):
            return
        # Keep arbitrary response payloads process-local.  They can include
        # repository-authored text or provider fields that pattern matching
        # cannot prove are non-sensitive, so no cleartext filesystem sink is
        # permitted here.
        self._entries[self._key(url, params)] = (time.time(), copy.deepcopy(response))

    def _key(self, url: str, params: dict | None) -> str:
        """SHA256 hash of URL + sorted params."""
        raw = url
        if params:
            raw += "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _path(self, url: str, params: dict | None) -> Path:
        """Return the legacy cache path without creating or writing it."""
        return self.cache_dir / f"{self._key(url, params)}.json"
