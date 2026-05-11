"""Tests for the cache reconcile quality gate (src/analyzer_cache.reconcile).

Covers:
- All matched (ok: True)
- One divergent pair detected
- Missing-from-cache entries
- Float tolerance within 1e-6
- Nested dict float tolerance
- Analyzers that opt out of caching (inputs_hash returns None)
- CLI --reconcile-cache flag exits 0 on match, 1 on divergence
- reconcile skips repos with no clone path
"""

from __future__ import annotations

import dataclasses
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src.analyzer_cache import _deep_equal, _diff_summary, reconcile, store
from src.analyzers.readme import ReadmeAnalyzer
from src.models import AnalyzerResult, RepoMetadata

# ── Helpers ────────────────────────────────────────────────────────────


def _fresh_db() -> sqlite3.Connection:
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


def _make_result(name: str = "readme", score: float = 0.8) -> AnalyzerResult:
    return AnalyzerResult(
        dimension=name,
        score=score,
        max_score=1.0,
        findings=["ok"],
        details={},
    )


def _populate_cache(conn, repo_name, sha, analyzer_name, inputs_hash, result):
    store(conn, repo_name, sha, analyzer_name, inputs_hash, dataclasses.asdict(result))


# ── _deep_equal tests ─────────────────────────────────────────────────


class TestDeepEqual:
    def test_equal_scalars(self):
        assert _deep_equal(1, 1)
        assert _deep_equal("hello", "hello")
        assert _deep_equal(None, None)

    def test_float_within_tolerance(self):
        # 0.1 + 0.2 in floating-point is 0.30000000000000004
        assert _deep_equal(0.1 + 0.2, 0.3)

    def test_float_outside_tolerance(self):
        assert not _deep_equal(0.5, 0.5 + 2e-6)

    def test_nested_dict_floats(self):
        a = {"score": 0.1 + 0.2, "name": "x"}
        b = {"score": 0.3, "name": "x"}
        assert _deep_equal(a, b)

    def test_list_order_sensitive(self):
        assert _deep_equal([1, 2, 3], [1, 2, 3])
        assert not _deep_equal([1, 2, 3], [3, 2, 1])

    def test_dict_key_mismatch(self):
        assert not _deep_equal({"a": 1}, {"b": 1})

    def test_int_float_interop(self):
        # 1 (int) vs 1.0 (float) should be equal within tolerance
        assert _deep_equal(1, 1.0)
        assert _deep_equal(1.0, 1)


# ── reconcile unit tests ──────────────────────────────────────────────


class TestReconcileAllMatched:
    def test_all_matched_returns_ok(self, tmp_path: Path):
        """When fresh results match cached results, ok is True."""
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        (repo_dir / "README.md").write_text("# Hello\n")

        meta = _sample_metadata("repo")
        conn = _fresh_db()
        sha = meta.pushed_at.isoformat()

        # Pre-populate cache with results that will match the fresh run.
        analyzer = ReadmeAnalyzer()
        inputs_hash = analyzer.cache_inputs_hash(repo_dir, meta)
        assert inputs_hash is not None
        result = analyzer.analyze(repo_dir, meta, None)
        _populate_cache(conn, "repo", sha, analyzer.name, inputs_hash, result)

        def _fresh(path, m, conn=None):
            return [analyzer.analyze(path, m, None)]

        report = reconcile(
            {"repo": repo_dir},
            {"repo": meta},
            conn,
            _fresh,
            commit_sha_map={"repo": sha},
        )

        assert report["ok"] is True
        assert report["checked"] == 1
        assert report["matched"] == 1
        assert report["divergent"] == []


class TestReconcileOneDivergent:
    def test_divergence_detected(self, tmp_path: Path):
        """When fresh result differs from cached, divergent list is populated."""
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        (repo_dir / "README.md").write_text("# Hello\n")

        meta = _sample_metadata("repo")
        conn = _fresh_db()
        sha = meta.pushed_at.isoformat()

        # Store a *different* result in the cache.
        analyzer = ReadmeAnalyzer()
        inputs_hash = analyzer.cache_inputs_hash(repo_dir, meta)
        assert inputs_hash is not None
        cached_result = AnalyzerResult(
            dimension=analyzer.name,
            score=0.99,  # will differ from fresh run
            max_score=1.0,
            findings=["cached finding"],
            details={"cached": True},
        )
        _populate_cache(conn, "repo", sha, analyzer.name, inputs_hash, cached_result)

        def _fresh(path, m, conn=None):
            # Return a result with a different score.
            return [
                AnalyzerResult(
                    dimension=analyzer.name,
                    score=0.10,
                    max_score=1.0,
                    findings=["fresh finding"],
                    details={"cached": False},
                )
            ]

        report = reconcile(
            {"repo": repo_dir},
            {"repo": meta},
            conn,
            _fresh,
            commit_sha_map={"repo": sha},
        )

        assert report["ok"] is False
        assert len(report["divergent"]) == 1
        entry = report["divergent"][0]
        assert entry["repo"] == "repo"
        assert entry["analyzer"] == analyzer.name
        assert "diff_summary" in entry
        assert entry["diff_summary"] != "(no diff)"


class TestReconcileMissingFromCache:
    def test_missing_entry_recorded(self, tmp_path: Path):
        """When the cache has no entry for an analyzer, it goes into missing_from_cache."""
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        (repo_dir / "README.md").write_text("# Hi\n")

        meta = _sample_metadata("repo")
        conn = _fresh_db()
        sha = meta.pushed_at.isoformat()
        # Do NOT populate the cache.

        analyzer = ReadmeAnalyzer()

        def _fresh(path, m, conn=None):
            return [analyzer.analyze(path, m, None)]

        report = reconcile(
            {"repo": repo_dir},
            {"repo": meta},
            conn,
            _fresh,
            commit_sha_map={"repo": sha},
        )

        assert any(e["repo"] == "repo" for e in report["missing_from_cache"])
        # Missing entries should NOT appear in divergent.
        assert report["divergent"] == []
        # ok is True because divergent is empty.
        assert report["ok"] is True


class TestReconcileFloatTolerance:
    def test_float_tolerance_treated_as_matched(self, tmp_path: Path):
        """0.1+0.2 vs 0.3 are within 1e-6 and should count as matched."""
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        (repo_dir / "README.md").write_text("# Hi\n")

        meta = _sample_metadata("repo")
        conn = _fresh_db()
        sha = meta.pushed_at.isoformat()

        analyzer = ReadmeAnalyzer()
        inputs_hash = analyzer.cache_inputs_hash(repo_dir, meta)
        assert inputs_hash is not None

        # Cache stores 0.3 exactly.
        cached_result = AnalyzerResult(
            dimension=analyzer.name,
            score=0.3,
            max_score=1.0,
            findings=[],
            details={},
        )
        _populate_cache(conn, "repo", sha, analyzer.name, inputs_hash, cached_result)

        def _fresh(path, m, conn=None):
            # Return the floating-point 0.1+0.2 = 0.30000000000000004.
            return [
                AnalyzerResult(
                    dimension=analyzer.name,
                    score=0.1 + 0.2,
                    max_score=1.0,
                    findings=[],
                    details={},
                )
            ]

        report = reconcile(
            {"repo": repo_dir},
            {"repo": meta},
            conn,
            _fresh,
            commit_sha_map={"repo": sha},
        )

        assert report["ok"] is True
        assert report["matched"] == 1
        assert report["divergent"] == []


class TestReconcileSkipsNoneRepoPath:
    def test_skips_missing_clone(self, tmp_path: Path):
        """Repos with repo_path=None are skipped silently."""
        meta = _sample_metadata("missing-repo")
        conn = _fresh_db()
        sha = meta.pushed_at.isoformat()

        def _fresh(path, m, conn=None):
            raise AssertionError("Should not be called for missing repo")

        report = reconcile(
            {"missing-repo": None},
            {"missing-repo": meta},
            conn,
            _fresh,
            commit_sha_map={"missing-repo": sha},
        )

        assert report["checked"] == 0
        assert report["ok"] is True


class TestReconcileOptOutAnalyzer:
    def test_none_inputs_hash_skipped(self, tmp_path: Path):
        """Analyzers returning None from cache_inputs_hash are skipped."""
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()

        meta = _sample_metadata("repo")
        conn = _fresh_db()
        sha = meta.pushed_at.isoformat()

        class _OptOutAnalyzer:
            name = "opt_out"

            def analyze(self, path, m, client=None):
                return AnalyzerResult("opt_out", 1.0, 1.0, [], {})

            def cache_inputs_hash(self, path, m):
                return None  # opts out

        opt_out = _OptOutAnalyzer()

        def _fresh(path, m, conn=None):
            return [opt_out.analyze(path, m)]

        # Patch ALL_ANALYZERS in the namespace used by reconcile's inner import.
        with patch("src.analyzers.ALL_ANALYZERS", [opt_out]):
            report = reconcile(
                {"repo": repo_dir},
                {"repo": meta},
                conn,
                _fresh,
                commit_sha_map={"repo": sha},
            )

        assert report["checked"] == 0
        assert report["ok"] is True


# ── _diff_summary tests ───────────────────────────────────────────────


class TestDiffSummary:
    def test_no_diff(self):
        d = {"a": 1, "b": 2}
        assert _diff_summary(d, d) == "(no diff)"

    def test_value_diff(self):
        a = {"score": 0.5, "findings": []}
        b = {"score": 0.9, "findings": []}
        summary = _diff_summary(a, b)
        assert "score" in summary

    def test_limit_capped(self):
        a = {str(i): i for i in range(10)}
        b = {str(i): i + 1 for i in range(10)}
        summary = _diff_summary(a, b, limit=3)
        # Should mention at most 3 keys
        assert summary.count(":") <= 3
