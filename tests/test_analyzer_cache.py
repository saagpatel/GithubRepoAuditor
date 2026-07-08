"""Tests for the per-(repo, sha, analyzer) cache in src/analyzer_cache.py."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from src.analyzer_cache import _deep_equal, _diff_summary, invalidate_repo, lookup, reconcile, stats, store
from src.analyzers import ALL_ANALYZERS, run_all_analyzers, run_with_cache
from src.analyzers.dependencies import DependenciesAnalyzer
from src.analyzers.readme import ReadmeAnalyzer
from src.analyzers.structure import StructureAnalyzer
from src.models import AnalyzerResult, RepoMetadata

# ── Helpers ────────────────────────────────────────────────────────────


def _fresh_db() -> sqlite3.Connection:
    """In-memory SQLite connection with the analyzer_cache table."""
    conn = sqlite3.connect(":memory:")
    from src.warehouse import _ensure_schema

    _ensure_schema(conn)
    return conn


def _sample_metadata(name: str = "my-repo") -> RepoMetadata:
    return RepoMetadata(
        name=name,
        full_name=f"user/{name}",
        description=None,
        language="Python",
        languages={},
        private=False,
        fork=False,
        archived=False,
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        pushed_at=datetime(2024, 3, 1, tzinfo=timezone.utc),
        default_branch="main",
        stars=0,
        forks=0,
        open_issues=0,
        size_kb=0,
        html_url="",
        clone_url="",
        topics=[],
    )


class _FakeAnalyzer:
    def __init__(self, name: str, inputs_hash: str | Exception):
        self.name = name
        self._inputs_hash = inputs_hash

    def cache_inputs_hash(self, repo_path, metadata):
        if isinstance(self._inputs_hash, Exception):
            raise self._inputs_hash
        return self._inputs_hash


# ── lookup / store round-trip ──────────────────────────────────────────


class TestLookupStore:
    def test_miss_on_empty_db(self):
        conn = _fresh_db()
        result = lookup(conn, "repo", "abc123", "readme", "hashval")
        assert result is None

    def test_round_trip(self):
        conn = _fresh_db()
        payload = {
            "dimension": "readme",
            "score": 0.8,
            "max_score": 1.0,
            "findings": ["ok"],
            "details": {},
        }
        store(conn, "repo", "abc123", "readme", "hashval", payload)
        hit = lookup(conn, "repo", "abc123", "readme", "hashval")
        assert hit == payload

    def test_different_hash_is_miss(self):
        conn = _fresh_db()
        payload = {
            "dimension": "readme",
            "score": 0.5,
            "max_score": 1.0,
            "findings": [],
            "details": {},
        }
        store(conn, "repo", "abc123", "readme", "hash-A", payload)
        assert lookup(conn, "repo", "abc123", "readme", "hash-B") is None

    def test_different_sha_is_miss(self):
        conn = _fresh_db()
        payload = {
            "dimension": "readme",
            "score": 0.5,
            "max_score": 1.0,
            "findings": [],
            "details": {},
        }
        store(conn, "repo", "sha-1", "readme", "hashval", payload)
        assert lookup(conn, "repo", "sha-2", "readme", "hashval") is None

    def test_different_analyzer_is_miss(self):
        conn = _fresh_db()
        payload = {
            "dimension": "readme",
            "score": 0.5,
            "max_score": 1.0,
            "findings": [],
            "details": {},
        }
        store(conn, "repo", "abc123", "readme", "hashval", payload)
        assert lookup(conn, "repo", "abc123", "structure", "hashval") is None

    def test_schema_version_mismatch_returns_none(self):
        """If a row has schema_version != SCHEMA_VERSION, treat as cache miss."""
        conn = _fresh_db()
        payload = {
            "dimension": "readme",
            "score": 0.5,
            "max_score": 1.0,
            "findings": [],
            "details": {},
        }
        store(conn, "repo", "abc123", "readme", "hashval", payload)
        # Manually corrupt the schema_version.
        conn.execute(
            "UPDATE analyzer_cache SET schema_version = 99 "
            "WHERE repo_name = 'repo' AND analyzer_name = 'readme'"
        )
        conn.commit()
        assert lookup(conn, "repo", "abc123", "readme", "hashval") is None

    def test_store_replaces_existing_entry(self):
        conn = _fresh_db()
        payload1 = {
            "dimension": "readme",
            "score": 0.3,
            "max_score": 1.0,
            "findings": ["v1"],
            "details": {},
        }
        payload2 = {
            "dimension": "readme",
            "score": 0.9,
            "max_score": 1.0,
            "findings": ["v2"],
            "details": {},
        }
        store(conn, "repo", "abc123", "readme", "hashval", payload1)
        store(conn, "repo", "abc123", "readme", "hashval", payload2)
        hit = lookup(conn, "repo", "abc123", "readme", "hashval")
        assert hit["score"] == 0.9
        assert hit["findings"] == ["v2"]

    def test_lookup_returns_none_when_cached_json_is_invalid(self):
        conn = _fresh_db()
        conn.execute(
            """
            INSERT INTO analyzer_cache
                (repo_name, commit_sha, analyzer_name, inputs_hash, result_json, computed_at, schema_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "repo",
                "abc123",
                "readme",
                "hashval",
                "{not valid json",
                datetime.now(timezone.utc).isoformat(),
                1,
            ),
        )
        conn.commit()

        assert lookup(conn, "repo", "abc123", "readme", "hashval") is None

    def test_store_swallows_non_serializable_payload(self):
        conn = _fresh_db()
        store(conn, "repo", "abc123", "readme", "hashval", {"bad": {object()}})

        assert lookup(conn, "repo", "abc123", "readme", "hashval") is None


# ── reconcile diff helpers ────────────────────────────────────────────


class TestReconcileDiffHelpers:
    def test_deep_equal_rejects_different_non_numeric_types(self):
        assert _deep_equal("a", ["a"]) is False

    def test_deep_equal_rejects_lists_with_different_lengths(self):
        assert _deep_equal([1, 2], [1, 2, 3]) is False

    def test_diff_summary_marks_added_and_removed_keys(self):
        summary = _diff_summary({"oldkey": 1, "shared": 2}, {"newkey": 1, "shared": 2})

        assert "+newkey" in summary
        assert "-oldkey" in summary


# ── reconcile edge behavior ───────────────────────────────────────────


class TestReconcileEdges:
    def test_skips_repo_without_metadata(self, tmp_path: Path):
        repo = tmp_path / "repo"
        repo.mkdir()
        conn = _fresh_db()

        def _fresh(path, metadata, conn=None):
            raise AssertionError("reconcile should skip repos with no metadata")

        report = reconcile({"repo": repo}, {}, conn, _fresh)

        assert report == {
            "checked": 0,
            "matched": 0,
            "divergent": [],
            "missing_from_cache": [],
            "ok": True,
        }

    def test_uses_pushed_at_as_sha_when_commit_map_is_missing(self, tmp_path: Path, monkeypatch):
        repo = tmp_path / "repo"
        repo.mkdir()
        meta = _sample_metadata("repo")
        conn = _fresh_db()
        analyzer = _FakeAnalyzer("edge", "hashval")
        result = AnalyzerResult("edge", 1.0, 1.0, ["ok"], {"source": "fresh"})
        store(conn, "repo", meta.pushed_at.isoformat(), "edge", "hashval", asdict(result))

        def _fresh(path, metadata, conn=None):
            return [result]

        monkeypatch.setattr("src.analyzers.ALL_ANALYZERS", [analyzer])
        report = reconcile({"repo": repo}, {"repo": meta}, conn, _fresh)

        assert report["checked"] == 1
        assert report["matched"] == 1
        assert report["divergent"] == []
        assert report["missing_from_cache"] == []
        assert report["ok"] is True

    def test_skips_repo_when_sha_cannot_be_derived(self, tmp_path: Path):
        repo = tmp_path / "repo"
        repo.mkdir()
        meta = RepoMetadata(**{**vars(_sample_metadata("repo")), "pushed_at": None})
        conn = _fresh_db()

        def _fresh(path, metadata, conn=None):
            raise AssertionError("reconcile should skip repos with no stable sha")

        report = reconcile({"repo": repo}, {"repo": meta}, conn, _fresh)

        assert report["checked"] == 0
        assert report["matched"] == 0
        assert report["divergent"] == []
        assert report["missing_from_cache"] == []
        assert report["ok"] is True

    def test_fresh_run_exception_skips_repo_and_continues(self, tmp_path: Path, monkeypatch):
        bad_repo = tmp_path / "bad"
        good_repo = tmp_path / "good"
        bad_repo.mkdir()
        good_repo.mkdir()
        bad_meta = _sample_metadata("bad")
        good_meta = _sample_metadata("good")
        conn = _fresh_db()
        analyzer = _FakeAnalyzer("edge", "hashval")
        result = AnalyzerResult("edge", 0.7, 1.0, ["fresh"], {})

        def _fresh(path, metadata, conn=None):
            if metadata.name == "bad":
                raise RuntimeError("boom")
            return [result]

        monkeypatch.setattr("src.analyzers.ALL_ANALYZERS", [analyzer])
        report = reconcile(
            {"bad": bad_repo, "good": good_repo},
            {"bad": bad_meta, "good": good_meta},
            conn,
            _fresh,
            commit_sha_map={"bad": "bad-sha", "good": "good-sha"},
        )

        assert report["checked"] == 1
        assert report["matched"] == 0
        assert report["divergent"] == []
        assert report["missing_from_cache"] == [{"repo": "good", "analyzer": "edge"}]
        assert report["ok"] is True

    def test_cache_inputs_hash_exception_skips_analyzer_pair(self, tmp_path: Path, monkeypatch):
        repo = tmp_path / "repo"
        repo.mkdir()
        meta = _sample_metadata("repo")
        conn = _fresh_db()
        analyzer = _FakeAnalyzer("edge", RuntimeError("hash failed"))

        def _fresh(path, metadata, conn=None):
            return [AnalyzerResult("edge", 0.5, 1.0, ["fresh"], {})]

        monkeypatch.setattr("src.analyzers.ALL_ANALYZERS", [analyzer])
        report = reconcile(
            {"repo": repo},
            {"repo": meta},
            conn,
            _fresh,
            commit_sha_map={"repo": "sha"},
        )

        assert report["checked"] == 0
        assert report["matched"] == 0
        assert report["divergent"] == []
        assert report["missing_from_cache"] == []
        assert report["ok"] is True


# ── invalidate_repo ────────────────────────────────────────────────────


class TestInvalidateRepo:
    def test_returns_zero_on_empty(self):
        conn = _fresh_db()
        assert invalidate_repo(conn, "ghost") == 0

    def test_deletes_all_rows_for_repo(self):
        conn = _fresh_db()
        payload = {"dimension": "x", "score": 0.0, "max_score": 1.0, "findings": [], "details": {}}
        store(conn, "my-repo", "sha1", "readme", "h1", payload)
        store(conn, "my-repo", "sha1", "structure", "h2", payload)
        store(conn, "other-repo", "sha1", "readme", "h3", payload)
        deleted = invalidate_repo(conn, "my-repo")
        assert deleted == 2
        assert lookup(conn, "my-repo", "sha1", "readme", "h1") is None
        assert lookup(conn, "other-repo", "sha1", "readme", "h3") is not None

    def test_returns_count(self):
        conn = _fresh_db()
        payload = {"dimension": "x", "score": 0.0, "max_score": 1.0, "findings": [], "details": {}}
        for i in range(5):
            store(conn, "target", f"sha{i}", "readme", f"hash{i}", payload)
        deleted = invalidate_repo(conn, "target")
        assert deleted == 5


# ── stats ──────────────────────────────────────────────────────────────


class TestStats:
    def test_empty_db_shape(self):
        conn = _fresh_db()
        s = stats(conn)
        assert s["total_rows"] == 0
        assert s["distinct_repos"] == 0
        assert s["distinct_analyzers"] == 0
        assert s["oldest_entry"] is None

    def test_populated_db(self):
        conn = _fresh_db()
        payload = {"dimension": "x", "score": 0.0, "max_score": 1.0, "findings": [], "details": {}}
        store(conn, "repo-a", "sha1", "readme", "h1", payload)
        store(conn, "repo-a", "sha1", "structure", "h2", payload)
        store(conn, "repo-b", "sha1", "readme", "h3", payload)
        s = stats(conn)
        assert s["total_rows"] == 3
        assert s["distinct_repos"] == 2
        assert s["distinct_analyzers"] == 2
        assert s["oldest_entry"] is not None


# ── Schema migration: opening a DB without the table creates it ────────


class TestSchemaMigration:
    def test_ensure_schema_creates_table(self, tmp_path: Path):
        db_path = tmp_path / "fresh.db"
        conn = sqlite3.connect(str(db_path))
        # _ensure_schema should create analyzer_cache even on a blank DB.
        from src.warehouse import _ensure_schema

        _ensure_schema(conn)
        # Confirm the table exists by querying it.
        row = conn.execute("SELECT COUNT(*) FROM analyzer_cache").fetchone()
        assert row[0] == 0
        conn.close()


# ── Analyzer cache_inputs_hash stability ──────────────────────────────


class TestDependenciesHash:
    def test_stable_for_same_content(self, tmp_path: Path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "requirements.txt").write_bytes(b"requests==2.31.0\n")
        meta = _sample_metadata()
        h1 = DependenciesAnalyzer().cache_inputs_hash(repo, meta)
        h2 = DependenciesAnalyzer().cache_inputs_hash(repo, meta)
        assert h1 is not None
        assert h1 == h2

    def test_different_for_different_content(self, tmp_path: Path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "requirements.txt").write_bytes(b"requests==2.31.0\n")
        meta = _sample_metadata()
        h1 = DependenciesAnalyzer().cache_inputs_hash(repo, meta)
        (repo / "requirements.txt").write_bytes(b"requests==2.32.0\n")
        h2 = DependenciesAnalyzer().cache_inputs_hash(repo, meta)
        assert h1 != h2

    def test_returns_none_when_no_dep_files(self, tmp_path: Path):
        repo = tmp_path / "empty"
        repo.mkdir()
        meta = _sample_metadata()
        assert DependenciesAnalyzer().cache_inputs_hash(repo, meta) is None

    def test_returns_none_when_repo_path_is_none(self):
        meta = _sample_metadata()
        assert DependenciesAnalyzer().cache_inputs_hash(None, meta) is None

    def test_adding_lockfile_changes_hash(self, tmp_path: Path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "requirements.txt").write_bytes(b"requests==2.31.0\n")
        meta = _sample_metadata()
        h1 = DependenciesAnalyzer().cache_inputs_hash(repo, meta)
        (repo / "poetry.lock").write_bytes(b"# lockfile\n[metadata]\n")
        h2 = DependenciesAnalyzer().cache_inputs_hash(repo, meta)
        assert h1 != h2


class TestReadmeHash:
    def test_stable_for_same_readme(self, tmp_path: Path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "README.md").write_bytes(b"# Hello\n")
        meta = _sample_metadata()
        h1 = ReadmeAnalyzer().cache_inputs_hash(repo, meta)
        h2 = ReadmeAnalyzer().cache_inputs_hash(repo, meta)
        assert h1 is not None
        assert h1 == h2

    def test_different_for_different_readme(self, tmp_path: Path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "README.md").write_bytes(b"# Hello\n")
        meta = _sample_metadata()
        h1 = ReadmeAnalyzer().cache_inputs_hash(repo, meta)
        (repo / "README.md").write_bytes(b"# Goodbye\n")
        h2 = ReadmeAnalyzer().cache_inputs_hash(repo, meta)
        assert h1 != h2

    def test_no_readme_returns_sentinel(self, tmp_path: Path):
        repo = tmp_path / "no-readme"
        repo.mkdir()
        meta = _sample_metadata()
        h = ReadmeAnalyzer().cache_inputs_hash(repo, meta)
        # Should return a non-None sentinel (cached "no README" outcome).
        assert h is not None

    def test_returns_none_when_repo_path_is_none(self):
        meta = _sample_metadata()
        assert ReadmeAnalyzer().cache_inputs_hash(None, meta) is None


class TestStructureHash:
    def test_stable_for_same_listing(self, tmp_path: Path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".gitignore").write_text("")
        (repo / "README.md").write_text("")
        meta = _sample_metadata()
        h1 = StructureAnalyzer().cache_inputs_hash(repo, meta)
        h2 = StructureAnalyzer().cache_inputs_hash(repo, meta)
        assert h1 is not None
        assert h1 == h2

    def test_different_after_adding_file(self, tmp_path: Path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".gitignore").write_text("")
        meta = _sample_metadata()
        h1 = StructureAnalyzer().cache_inputs_hash(repo, meta)
        (repo / "LICENSE").write_text("MIT")
        h2 = StructureAnalyzer().cache_inputs_hash(repo, meta)
        assert h1 != h2

    def test_different_for_different_language(self, tmp_path: Path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".gitignore").write_text("")
        meta_py = _sample_metadata()
        meta_rs = _sample_metadata()
        meta_rs = RepoMetadata(**{**vars(meta_py), "language": "Rust"})
        h1 = StructureAnalyzer().cache_inputs_hash(repo, meta_py)
        h2 = StructureAnalyzer().cache_inputs_hash(repo, meta_rs)
        assert h1 != h2

    def test_returns_none_when_repo_path_is_none(self):
        meta = _sample_metadata()
        assert StructureAnalyzer().cache_inputs_hash(None, meta) is None


# ── Integration: cache is used on second run ───────────────────────────


class TestCacheIntegration:
    def test_second_run_hits_cache_not_analyzer(self, tmp_path: Path):
        """Analyzer.analyze() should only be called ONCE across two identical runs."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "requirements.txt").write_bytes(b"requests==2.31.0\n")

        meta = _sample_metadata()
        sha = "pushed-2024-03-01"
        conn = _fresh_db()

        analyzer = DependenciesAnalyzer()
        call_count = 0
        original_analyze = analyzer.analyze

        def counting_analyze(repo_path, metadata, github_client=None, **kwargs):
            nonlocal call_count
            call_count += 1
            return original_analyze(repo_path, metadata, github_client)

        analyzer.analyze = counting_analyze  # type: ignore[method-assign]

        # First run — should call analyze() and populate cache.
        r1 = run_with_cache(analyzer, repo, meta, None, sha, conn)
        assert call_count == 1
        first_run_count = call_count

        # Second run — should hit cache and NOT call analyze() again.
        r2 = run_with_cache(analyzer, repo, meta, None, sha, conn)
        assert call_count == first_run_count

        assert r1.dimension == r2.dimension
        assert r1.score == r2.score
        assert r1.findings == r2.findings

    def test_no_conn_always_runs_analyzer(self, tmp_path: Path):
        """With conn=None, the analyzer should always run (no caching)."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "requirements.txt").write_bytes(b"requests==2.31.0\n")

        meta = _sample_metadata()
        analyzer = DependenciesAnalyzer()
        call_count = 0
        original_analyze = analyzer.analyze

        def counting_analyze(repo_path, metadata, github_client=None, **kwargs):
            nonlocal call_count
            call_count += 1
            return original_analyze(repo_path, metadata, github_client)

        analyzer.analyze = counting_analyze  # type: ignore[method-assign]

        run_with_cache(analyzer, repo, meta, None, "sha1", None)
        run_with_cache(analyzer, repo, meta, None, "sha1", None)
        assert call_count == 2

    def test_run_all_analyzers_passes_conn(self, tmp_path: Path):
        """run_all_analyzers with conn + sha should not raise and returns results."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "README.md").write_text("# Hi\n")
        (repo / "requirements.txt").write_bytes(b"requests==2.31\n")
        meta = _sample_metadata()
        conn = _fresh_db()
        results = run_all_analyzers(repo, meta, conn=conn, commit_sha="sha-abc")
        assert len(results) == len(ALL_ANALYZERS)
        for r in results:
            assert isinstance(r, AnalyzerResult)
