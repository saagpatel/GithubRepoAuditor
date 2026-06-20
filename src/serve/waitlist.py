"""Monitoring-waitlist email capture — the 'earn the tier' demand signal.

A durable, deduplicated store of emails captured from the free report's
"notify me about monitoring" CTA. SQLite-backed by default (stdlib, survives
restart); a deployment can point ``GHRA_WAITLIST_DB`` at a persistent volume or
swap the store for Postgres later. Writes are serialized with a lock and a
fresh connection per call, so it is safe under FastAPI's threadpool.
"""

from __future__ import annotations

import os
import re
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, runtime_checkable

WAITLIST_DB_ENV_VAR = "GHRA_WAITLIST_DB"
DEFAULT_WAITLIST_DB = "waitlist.db"

# Pragmatic email shape check — this gates a waitlist, not authentication, so a
# structural match (local@domain.tld, no spaces) is the right strictness.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_EMAIL_LEN = 254  # RFC 5321 maximum.


def is_valid_email(email: str) -> bool:
    candidate = email.strip()
    return len(candidate) <= MAX_EMAIL_LEN and bool(_EMAIL_RE.match(candidate))


@runtime_checkable
class WaitlistStore(Protocol):
    def add(self, email: str, source: str | None = None) -> bool:
        """Record an email; return True if newly added, False if already present."""
        ...

    def count(self) -> int: ...


class SqliteWaitlistStore:
    """SQLite-backed waitlist with email as the dedup key."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._lock = threading.Lock()
        # Ensure the parent dir exists so the DB can be created on a fresh host
        # (e.g. a container before its volume path is populated).
        parent = Path(path).parent
        if parent != Path(""):
            parent.mkdir(parents=True, exist_ok=True)
        with self._lock, closing(self._connect()) as conn, conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS waitlist ("
                "email TEXT PRIMARY KEY, source TEXT, created_at TEXT NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def add(self, email: str, source: str | None = None) -> bool:
        normalized = email.strip().lower()
        now = datetime.now(timezone.utc).isoformat()
        # closing() guarantees the fd is released; the inner `conn` context
        # manager commits the transaction. The lock serializes writers.
        with self._lock, closing(self._connect()) as conn, conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO waitlist(email, source, created_at) "
                "VALUES(?, ?, ?)",
                (normalized, source, now),
            )
            return cur.rowcount > 0

    def count(self) -> int:
        with self._lock, closing(self._connect()) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM waitlist").fetchone()[0])


def build_waitlist_store(default_dir: str | Path | None = None) -> WaitlistStore:
    """Build the waitlist store. ``GHRA_WAITLIST_DB`` wins; otherwise the DB lives
    under ``default_dir`` (the app's output dir) so it never lands in the cwd."""
    configured = os.environ.get(WAITLIST_DB_ENV_VAR)
    if configured:
        path = configured
    elif default_dir is not None:
        path = os.path.join(str(default_dir), DEFAULT_WAITLIST_DB)
    else:
        path = DEFAULT_WAITLIST_DB
    return SqliteWaitlistStore(path)
