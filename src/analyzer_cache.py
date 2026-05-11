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


def _deep_equal(a: object, b: object, *, tol: float = 1e-6) -> bool:
    """Recursive equality check with float tolerance for nested structures."""
    if type(a) is not type(b):
        # Allow int/float interop (e.g. 1 vs 1.0).
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return abs(float(a) - float(b)) <= tol
        return False
    if isinstance(a, float):
        assert isinstance(b, float)
        return abs(a - b) <= tol
    if isinstance(a, dict):
        assert isinstance(b, dict)
        if set(a.keys()) != set(b.keys()):
            return False
        return all(_deep_equal(a[k], b[k], tol=tol) for k in a)
    if isinstance(a, list):
        assert isinstance(b, list)
        if len(a) != len(b):
            return False
        return all(_deep_equal(x, y, tol=tol) for x, y in zip(a, b))
    return a == b


def _diff_summary(cached: dict, fresh: dict, *, limit: int = 3) -> str:
    """Return a short human-readable diff for the first *limit* differing keys."""
    diffs: list[str] = []
    all_keys = sorted(set(cached.keys()) | set(fresh.keys()))
    for k in all_keys:
        if k not in cached:
            diffs.append(f"+{k}")
        elif k not in fresh:
            diffs.append(f"-{k}")
        elif not _deep_equal(cached[k], fresh[k]):
            diffs.append(f"{k}: {cached[k]!r} -> {fresh[k]!r}")
        if len(diffs) >= limit:
            break
    return "; ".join(diffs) if diffs else "(no diff)"


def reconcile(
    repo_paths: dict[str, object],  # repo_name -> Path (or None if not cloned)
    repo_metas: dict[str, object],  # repo_name -> RepoMetadata
    conn: sqlite3.Connection,
    run_analyzers_fn,  # callable(repo_path, metadata, conn=None) -> list[AnalyzerResult]
    commit_sha_map: dict[str, str] | None = None,
) -> dict:
    """Re-run analyzers without cache and compare against cached results.

    For each (repo, analyzer) pair that has a cache entry, runs the analyzer
    fresh (cache disabled) and deep-compares the result.

    Args:
        repo_paths: Mapping from repo name to cloned Path.
        repo_metas: Mapping from repo name to RepoMetadata.
        conn: Open warehouse SQLite connection.
        run_analyzers_fn: Callable that runs the full analyzer suite for one
            repo without cache.  Signature:
            ``(repo_path, metadata, conn=None) -> list[AnalyzerResult]``
        commit_sha_map: Optional mapping of repo name -> commit SHA used during
            the original audit (needed to look up cache keys).  If absent,
            the SHA is derived from ``metadata.pushed_at.isoformat()``.

    Returns:
        {
            "checked": int,
            "matched": int,
            "divergent": list[dict],          # [{repo, analyzer, diff_summary}, ...]
            "missing_from_cache": list[dict], # [{repo, analyzer}, ...]
            "ok": bool,
        }
    """
    from src.analyzers.base import BaseAnalyzer

    checked = 0
    matched = 0
    divergent: list[dict] = []
    missing_from_cache: list[dict] = []

    for repo_name, repo_path in repo_paths.items():
        if repo_path is None:
            continue
        meta = repo_metas.get(repo_name)
        if meta is None:
            continue

        sha: str = ""
        if commit_sha_map and repo_name in commit_sha_map:
            sha = commit_sha_map[repo_name]
        else:
            pushed_at = getattr(meta, "pushed_at", None)
            sha = pushed_at.isoformat() if pushed_at is not None else ""

        if not sha:
            # No stable key → cannot look up cache entries; skip.
            continue

        # Run fresh (no cache).
        try:
            fresh_results = run_analyzers_fn(repo_path, meta, conn=None)
        except Exception as exc:
            logger.warning("reconcile: fresh run failed for %s: %s", repo_name, exc)
            continue

        fresh_by_name: dict[str, dict] = {}
        for r in fresh_results:
            import dataclasses as _dc

            fresh_by_name[r.dimension] = _dc.asdict(r)

        for analyzer_name, fresh_dict in fresh_by_name.items():
            # Determine inputs_hash for cache lookup.  We re-derive it from
            # the analyzer instance matching by name.
            from src.analyzers import ALL_ANALYZERS

            analyzer_inst: BaseAnalyzer | None = next(
                (a for a in ALL_ANALYZERS if a.name == analyzer_name), None
            )
            inputs_hash: str | None = None
            if analyzer_inst is not None:
                try:
                    inputs_hash = analyzer_inst.cache_inputs_hash(repo_path, meta)
                except Exception as exc:
                    logger.warning(
                        "reconcile: cache_inputs_hash failed for %s/%s: %s",
                        repo_name,
                        analyzer_name,
                        exc,
                    )

            if inputs_hash is None:
                # Analyzer opts out of caching; skip.
                continue

            checked += 1
            cached_dict = lookup(conn, repo_name, sha, analyzer_name, inputs_hash)

            if cached_dict is None:
                missing_from_cache.append({"repo": repo_name, "analyzer": analyzer_name})
                continue

            if _deep_equal(cached_dict, fresh_dict):
                matched += 1
            else:
                diff_str = _diff_summary(cached_dict, fresh_dict)
                divergent.append(
                    {"repo": repo_name, "analyzer": analyzer_name, "diff_summary": diff_str}
                )

    return {
        "checked": checked,
        "matched": matched,
        "divergent": divergent,
        "missing_from_cache": missing_from_cache,
        "ok": len(divergent) == 0,
    }
