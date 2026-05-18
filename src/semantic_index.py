"""Portfolio-wide semantic index for repo discovery and similarity search.

Stores repo embeddings in a sqlite-vec virtual table (``repo_embeddings``) inside
the portfolio warehouse DB.  Two embedder backends are supported:

- ``voyage``  — Voyage AI ``voyage-code-3`` (512-dim, default).  Requires the
  ``VOYAGE_API_KEY`` env var.
- ``local``   — ``sentence-transformers/all-MiniLM-L6-v2`` (384-dim).  Requires
  ``pip install -e ".[semantic]"``.

Import-time guards ensure that missing optional deps surface a helpful message
only when the module is *used*, not when it is merely imported.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, runtime_checkable

from src.models import RepoAudit

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

VOYAGE_API_BASE_URL = os.environ.get("VOYAGE_API_BASE_URL", "https://api.voyageai.com/v1")
VOYAGE_MODEL = "voyage-code-3"
VOYAGE_DIM = 512
LOCAL_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
LOCAL_DIM = 384


@dataclass
class SearchResult:
    repo_name: str
    score: float  # cosine distance (0 = identical, lower = more similar)
    snippet: str


@dataclass
class DuplicateGroup:
    """A set of repos whose pairwise cosine similarity exceeds the configured threshold."""

    members: list[str]
    representative: str  # the member with the most recent push (or first alphabetically)
    min_pairwise_cosine: float


@runtime_checkable
class Embedder(Protocol):
    """Minimal protocol for text embedders."""

    name: str
    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Embedder implementations
# ---------------------------------------------------------------------------


class VoyageEmbedder:
    """Voyage AI embedder using direct HTTP (no SDK)."""

    name = "voyage-code-3"
    dimension = VOYAGE_DIM

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("VOYAGE_API_KEY") or ""
        if not self._api_key:
            raise RuntimeError(
                "VOYAGE_API_KEY environment variable is not set. Export it or use --embedder local."
            )

    def embed(self, texts: list[str]) -> list[list[float]]:
        import requests  # already a core dep

        url = f"{VOYAGE_API_BASE_URL}/embeddings"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": VOYAGE_MODEL,
            "input": texts,
            "output_dimension": self.dimension,
            "output_dtype": "float",
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return [item["embedding"] for item in data["data"]]


class LocalEmbedder:
    """sentence-transformers local fallback (optional dep)."""

    name = "sentence-transformers/all-MiniLM-L6-v2"
    dimension = LOCAL_DIM

    def __init__(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import]

            self._model = SentenceTransformer(LOCAL_MODEL)
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is not installed. Run: pip install -e '.[semantic]'"
            ) from exc

    def embed(self, texts: list[str]) -> list[list[float]]:
        vecs = self._model.encode(texts, convert_to_numpy=True)
        return [v.tolist() for v in vecs]


# ---------------------------------------------------------------------------
# Helper: doc construction
# ---------------------------------------------------------------------------


def build_repo_doc(audit: RepoAudit) -> str:
    """Build a text document from a RepoAudit for embedding."""
    meta = audit.metadata
    name = meta.name
    description = meta.description or ""
    topics = ", ".join(meta.topics) if meta.topics else "—"
    language = meta.language or "—"

    # Collect file-like signals from structure analyzer details
    source_dirs: list[str] = []
    config_files: list[str] = []
    for ar in audit.analyzer_results:
        if ar.dimension == "structure":
            source_dirs = ar.details.get("source_dirs", [])[:10]
            config_files = ar.details.get("config_files", [])[:10]
            break

    all_files = source_dirs + config_files
    files_str = ", ".join(all_files[:20]) if all_files else "—"

    # README first paragraph from readme analyzer details
    readme_snippet = ""
    for ar in audit.analyzer_results:
        if ar.dimension == "readme":
            readme_snippet = ar.details.get("first_paragraph", "")
            break

    parts = [
        name,
        description,
        "",
        readme_snippet[:2000] if readme_snippet else "",
        "",
        f"Files: {files_str}",
        f"Topics: {topics}",
        f"Language: {language}",
    ]
    return "\n".join(parts).strip()


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

_SCHEMA_VEC = """
CREATE VIRTUAL TABLE IF NOT EXISTS repo_embeddings USING vec0(
    embedding FLOAT[{dim}] distance_metric=cosine
);
"""

_SCHEMA_META = """
CREATE TABLE IF NOT EXISTS repo_embedding_meta (
    rowid INTEGER PRIMARY KEY,
    repo_name TEXT UNIQUE NOT NULL,
    doc_sha256 TEXT NOT NULL,
    embedder_name TEXT NOT NULL,
    pushed_at TEXT,
    indexed_at TEXT NOT NULL
);
"""


def _load_sqlite_vec(conn: sqlite3.Connection) -> None:
    """Load the sqlite-vec extension into a connection."""
    try:
        import sqlite_vec  # type: ignore[import]
    except ImportError as exc:
        raise ImportError("sqlite-vec is not installed. Run: pip install -e '.[semantic]'") from exc
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)


def _ensure_schema(conn: sqlite3.Connection, dimension: int) -> None:
    _load_sqlite_vec(conn)
    conn.executescript(_SCHEMA_VEC.format(dim=dimension))
    conn.executescript(_SCHEMA_META)
    conn.commit()


def _doc_sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# ---------------------------------------------------------------------------
# SemanticIndex
# ---------------------------------------------------------------------------


class SemanticIndex:
    """Portfolio-wide semantic index backed by sqlite-vec.

    Parameters
    ----------
    db_path:
        Path to the warehouse SQLite database (``portfolio-warehouse.db``).
    embedder:
        An :class:`Embedder` instance.  Pass ``None`` to construct with
        :meth:`from_embedder_name`.
    """

    def __init__(self, db_path: Path, embedder: Embedder) -> None:
        self._db_path = db_path
        self._embedder = embedder

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_embedder_name(
        cls, db_path: Path, embedder_name: str = "voyage"
    ) -> "SemanticIndex | None":
        """Return a SemanticIndex, or None with a logged reason if unavailable."""
        embedder: Embedder
        if embedder_name == "voyage":
            try:
                embedder = VoyageEmbedder()
            except RuntimeError as exc:
                logger.warning("Semantic index unavailable: %s", exc)
                return None
        elif embedder_name == "local":
            try:
                embedder = LocalEmbedder()
            except ImportError as exc:
                logger.warning("Semantic index unavailable: %s", exc)
                return None
        else:
            logger.warning("Unknown embedder '%s'. Choose 'voyage' or 'local'.", embedder_name)
            return None

        # Verify sqlite-vec is importable
        try:
            import sqlite_vec  # type: ignore[import]  # noqa: F401
        except ImportError:
            logger.warning(
                "Semantic index unavailable: sqlite-vec not installed. "
                "Run: pip install -e '.[semantic]'"
            )
            return None

        return cls(db_path, embedder)

    # ------------------------------------------------------------------
    # Connection helper
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        _ensure_schema(conn, self._embedder.dimension)
        return conn

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reindex(self, audits: list[RepoAudit], *, force: bool = False) -> dict[str, object]:
        """Embed each repo's document.  Skip if doc_sha256 and embedder unchanged.

        Returns
        -------
        dict with keys: ``embedded``, ``skipped``, ``total``, ``duration_s``.
        """
        conn = self._connect()
        try:
            return self._reindex_inner(conn, audits, force=force)
        finally:
            conn.close()

    def _reindex_inner(
        self, conn: sqlite3.Connection, audits: list[RepoAudit], *, force: bool
    ) -> dict[str, object]:
        t0 = time.perf_counter()
        embedded = 0
        skipped = 0

        # Load existing meta for quick lookups
        existing: dict[str, dict] = {}
        for row in conn.execute(
            "SELECT repo_name, doc_sha256, embedder_name FROM repo_embedding_meta"
        ).fetchall():
            existing[row[0]] = {"doc_sha256": row[1], "embedder_name": row[2]}

        # Partition into need-embed vs skip
        to_embed: list[tuple[RepoAudit, str, str]] = []  # (audit, doc, sha)
        for audit in audits:
            doc = build_repo_doc(audit)
            sha = _doc_sha256(doc)
            prev = existing.get(audit.metadata.name)
            if (
                not force
                and prev is not None
                and prev["doc_sha256"] == sha
                and prev["embedder_name"] == self._embedder.name
            ):
                skipped += 1
            else:
                to_embed.append((audit, doc, sha))

        # Embed in batches of 32
        batch_size = 32
        for i in range(0, len(to_embed), batch_size):
            batch = to_embed[i : i + batch_size]
            docs = [item[1] for item in batch]
            vectors = self._embedder.embed(docs)

            for (audit, doc, sha), vec in zip(batch, vectors):
                repo_name = audit.metadata.name
                pushed_at = (
                    audit.metadata.pushed_at.isoformat() if audit.metadata.pushed_at else None
                )
                indexed_at = datetime.now(timezone.utc).isoformat()

                # Get or create rowid via meta table
                row = conn.execute(
                    "SELECT rowid FROM repo_embedding_meta WHERE repo_name = ?",
                    (repo_name,),
                ).fetchone()

                if row is not None:
                    rowid = row[0]
                    # Update meta
                    conn.execute(
                        """UPDATE repo_embedding_meta
                           SET doc_sha256=?, embedder_name=?, pushed_at=?, indexed_at=?
                           WHERE rowid=?""",
                        (sha, self._embedder.name, pushed_at, indexed_at, rowid),
                    )
                    # Delete old vec row then re-insert (vec0 doesn't support UPDATE)
                    conn.execute("DELETE FROM repo_embeddings WHERE rowid=?", (rowid,))
                else:
                    # Insert meta first to get rowid
                    cur = conn.execute(
                        """INSERT INTO repo_embedding_meta
                           (repo_name, doc_sha256, embedder_name, pushed_at, indexed_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        (repo_name, sha, self._embedder.name, pushed_at, indexed_at),
                    )
                    rowid = cur.lastrowid

                # Insert embedding with the same rowid
                vec_str = "[" + ", ".join(str(v) for v in vec) + "]"
                conn.execute(
                    "INSERT INTO repo_embeddings(rowid, embedding) VALUES (?, ?)",
                    (rowid, vec_str),
                )
                embedded += 1

        conn.commit()
        return {
            "embedded": embedded,
            "skipped": skipped,
            "total": len(audits),
            "duration_s": round(time.perf_counter() - t0, 3),
        }

    def search(self, query: str, *, k: int = 5) -> list[SearchResult]:
        """Top-K cosine retrieval.  Returns ranked results (ascending distance)."""
        conn = self._connect()
        try:
            return self._search_inner(conn, query, k=k)
        finally:
            conn.close()

    def _search_inner(self, conn: sqlite3.Connection, query: str, *, k: int) -> list[SearchResult]:
        vec = self._embedder.embed([query])[0]
        vec_str = "[" + ", ".join(str(v) for v in vec) + "]"

        rows = conn.execute(
            """
            SELECT m.repo_name, e.distance, m.doc_sha256
            FROM repo_embeddings e
            JOIN repo_embedding_meta m ON e.rowid = m.rowid
            WHERE e.embedding MATCH ?
              AND k = ?
            ORDER BY e.distance
            """,
            (vec_str, k),
        ).fetchall()

        results = []
        for repo_name, distance, _sha in rows:
            snippet = f"repo: {repo_name}"
            results.append(SearchResult(repo_name=repo_name, score=distance, snippet=snippet))
        return results

    def find_neighbors(self, repo_name: str, k: int = 5) -> list[SearchResult]:
        """Return the top-K most similar repos to *repo_name* (excluding itself).

        If *repo_name* is not in the index, returns an empty list without raising.
        Results are ordered by ascending cosine distance (most similar first).
        """
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT rowid FROM repo_embedding_meta WHERE repo_name = ?",
                (repo_name,),
            ).fetchone()
            if row is None:
                logger.debug("find_neighbors: repo %r not in index, returning []", repo_name)
                return []

            rowid = row[0]
            vec_row = conn.execute(
                "SELECT embedding FROM repo_embeddings WHERE rowid = ?",
                (rowid,),
            ).fetchone()
            if vec_row is None:
                logger.debug("find_neighbors: no embedding for repo %r, returning []", repo_name)
                return []

            vec_str = vec_row[0]
            # Fetch k+1 to account for the repo itself appearing in results
            rows = conn.execute(
                """
                SELECT m.repo_name, e.distance, m.doc_sha256
                FROM repo_embeddings e
                JOIN repo_embedding_meta m ON e.rowid = m.rowid
                WHERE e.embedding MATCH ?
                  AND k = ?
                ORDER BY e.distance
                """,
                (vec_str, k + 1),
            ).fetchall()

            results = []
            for rname, distance, _sha in rows:
                if rname == repo_name:
                    continue
                snippet = f"repo: {rname}"
                results.append(SearchResult(repo_name=rname, score=distance, snippet=snippet))
                if len(results) >= k:
                    break
            return results
        finally:
            conn.close()

    def find_duplicate_groups(
        self,
        *,
        threshold: float | None = None,
        min_group_size: int = 2,
    ) -> list[DuplicateGroup]:
        """Detect candidate duplicate repos via all-pairs cosine similarity.

        Pairs with cosine *similarity* above *threshold* are grouped using union-find
        for transitive closure.  Returns only groups with at least *min_group_size*
        members.

        The default threshold is read from the ``SEMANTIC_DUPLICATE_THRESHOLD`` env var
        (float) or falls back to ``0.85``.

        Note: cosine *distance* stored in the index is 1 - similarity.  The threshold
        comparison is: ``(1 - distance) >= threshold``, i.e. distance <= (1 - threshold).

        O(N²) similarity checks — fast enough for portfolios up to ~500 repos.
        """
        if threshold is None:
            threshold = float(os.environ.get("SEMANTIC_DUPLICATE_THRESHOLD", "0.85"))

        conn = self._connect()
        try:
            meta_rows = conn.execute(
                "SELECT rowid, repo_name, pushed_at FROM repo_embedding_meta ORDER BY rowid"
            ).fetchall()
        finally:
            conn.close()

        if len(meta_rows) < min_group_size:
            return []

        rowids = [r[0] for r in meta_rows]
        names = [r[1] for r in meta_rows]
        pushed_ats = [r[2] for r in meta_rows]

        # Load all embedding vectors once
        conn = self._connect()
        try:
            vecs: dict[int, str] = {}
            for rowid in rowids:
                row = conn.execute(
                    "SELECT embedding FROM repo_embeddings WHERE rowid = ?",
                    (rowid,),
                ).fetchone()
                if row is not None:
                    vecs[rowid] = row[0]
        finally:
            conn.close()

        # All-pairs similarity: for each pair (i < j), compute similarity
        # using the vec index's own distance metric (ask for k=N, filter by distance)
        # For efficiency, use the stored vectors directly rather than re-querying.
        # We compute cosine similarity from the stored distance: similarity = 1 - distance.
        distance_threshold = 1.0 - threshold

        # Union-find for transitive closure
        parent: dict[int, int] = {i: i for i in range(len(names))}

        def _find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def _union(a: int, b: int) -> None:
            ra, rb = _find(a), _find(b)
            if ra != rb:
                parent[rb] = ra

        # Track min pairwise cosine distance per group root (we accumulate and reduce later)
        pair_distances: dict[tuple[int, int], float] = {}

        conn = self._connect()
        try:
            for i, (rowid_i, name_i) in enumerate(zip(rowids, names)):
                if rowid_i not in vecs:
                    continue
                # Use vec index to find neighbors of repo i with distance <= threshold
                n_total = len(names)
                rows = conn.execute(
                    """
                    SELECT m.repo_name, e.distance
                    FROM repo_embeddings e
                    JOIN repo_embedding_meta m ON e.rowid = m.rowid
                    WHERE e.embedding MATCH ?
                      AND k = ?
                    ORDER BY e.distance
                    """,
                    (vecs[rowid_i], n_total),
                ).fetchall()

                for rname_j, dist in rows:
                    if rname_j == name_i:
                        continue
                    if dist > distance_threshold:
                        continue
                    # Find j index
                    try:
                        j = names.index(rname_j)
                    except ValueError:
                        continue
                    _union(i, j)
                    key = (min(i, j), max(i, j))
                    pair_distances[key] = min(pair_distances.get(key, dist), dist)
        finally:
            conn.close()

        # Collect groups from union-find
        groups: dict[int, list[int]] = {}
        for i in range(len(names)):
            root = _find(i)
            groups.setdefault(root, []).append(i)

        result: list[DuplicateGroup] = []
        for root, members_idx in groups.items():
            if len(members_idx) < min_group_size:
                continue

            member_names = [names[i] for i in members_idx]

            # Compute min pairwise cosine similarity (= 1 - max pairwise distance)
            relevant_dists = [
                dist
                for (a, b), dist in pair_distances.items()
                if a in members_idx and b in members_idx
            ]
            min_pairwise_cosine = 1.0 - max(relevant_dists) if relevant_dists else threshold

            # Representative = most recently pushed, or first alphabetically as tiebreak
            best_idx = members_idx[0]
            best_pushed = pushed_ats[best_idx]
            for idx in members_idx[1:]:
                pt = pushed_ats[idx]
                if pt is not None and (best_pushed is None or pt > best_pushed):
                    best_idx = idx
                    best_pushed = pt
            representative = names[best_idx]

            result.append(
                DuplicateGroup(
                    members=sorted(member_names),
                    representative=representative,
                    min_pairwise_cosine=round(min_pairwise_cosine, 4),
                )
            )

        # Sort by group size descending, then representative name
        result.sort(key=lambda g: (-len(g.members), g.representative))
        return result


# ---------------------------------------------------------------------------
# CLI convenience wrappers (thin, testable callables)
# ---------------------------------------------------------------------------


def _run_reindex(
    index: SemanticIndex,
    audits: list[RepoAudit],
    *,
    force: bool = False,
) -> dict[str, object]:
    """Run reindex and return the summary dict.  Called from cli.py."""
    return index.reindex(audits, force=force)


def _run_search(
    index: SemanticIndex,
    query: str,
    *,
    k: int = 5,
) -> list[SearchResult]:
    """Run a semantic search and return ranked results.  Called from cli.py."""
    return index.search(query, k=k)
