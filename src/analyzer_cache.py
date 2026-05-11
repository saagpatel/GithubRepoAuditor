"""Per-(repo_name, commit_sha, analyzer_name, inputs_hash) cache backed by the warehouse SQLite DB.

All functions accept an open sqlite3.Connection — opening and closing connections
is the caller's responsibility.  If a cache read fails for any reason, callers
should log and fall through to running the analyzer rather than raising.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


def lookup(
    conn: sqlite3.Connection,
    repo_name: str,
    sha: str,
    analyzer_name: str,
    inputs_hash: str,
) -> dict | None:
    """Return the cached result dict, or None on miss.

    Never raises — any database error is logged and treated as a cache miss.
    """
    try:
        row = conn.execute(
            """
            SELECT result_json, schema_version
            FROM analyzer_cache
            WHERE repo_name = ? AND commit_sha = ? AND analyzer_name = ? AND inputs_hash = ?
            """,
            (repo_name, sha, analyzer_name, inputs_hash),
        ).fetchone()
        if row is None:
            return None
        result_json, schema_version = row
        if schema_version != SCHEMA_VERSION:
            # Stale schema — treat as miss so result gets recomputed and stored fresh.
            return None
        return json.loads(result_json)
    except Exception as exc:
        logger.warning(
            "analyzer_cache.lookup failed for %s/%s/%s: %s",
            repo_name,
            analyzer_name,
            sha[:8] if sha else sha,
            exc,
        )
        return None


def store(
    conn: sqlite3.Connection,
    repo_name: str,
    sha: str,
    analyzer_name: str,
    inputs_hash: str,
    result: dict,
) -> None:
    """Persist result dict.  Silently replaces an existing entry for the same key.

    Never raises — any database error is logged and suppressed so the audit can continue.
    """
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO analyzer_cache
                (repo_name, commit_sha, analyzer_name, inputs_hash, result_json, computed_at, schema_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                repo_name,
                sha,
                analyzer_name,
                inputs_hash,
                json.dumps(result),
                datetime.now(timezone.utc).isoformat(),
                SCHEMA_VERSION,
            ),
        )
        conn.commit()
    except Exception as exc:
        logger.warning(
            "analyzer_cache.store failed for %s/%s/%s: %s",
            repo_name,
            analyzer_name,
            sha[:8] if sha else sha,
            exc,
        )


def invalidate_repo(conn: sqlite3.Connection, repo_name: str) -> int:
    """Delete all cache entries for *repo_name*.  Returns the number of rows deleted."""
    cursor = conn.execute(
        "DELETE FROM analyzer_cache WHERE repo_name = ?",
        (repo_name,),
    )
    conn.commit()
    return cursor.rowcount


def stats(conn: sqlite3.Connection) -> dict:
    """Return summary statistics about the cache table."""
    row = conn.execute(
        """
        SELECT
            COUNT(*)                    AS total_rows,
            COUNT(DISTINCT repo_name)   AS distinct_repos,
            COUNT(DISTINCT analyzer_name) AS distinct_analyzers,
            MIN(computed_at)            AS oldest_entry
        FROM analyzer_cache
        """
    ).fetchone()
    return {
        "total_rows": row[0],
        "distinct_repos": row[1],
        "distinct_analyzers": row[2],
        "oldest_entry": row[3],
    }
