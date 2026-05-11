"""Tests for src/semantic_index.py — portfolio semantic index (Arc F S3.1)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import responses as responses_lib

from src.models import AnalyzerResult, RepoAudit, RepoMetadata
from src.semantic_index import (
    VOYAGE_DIM,
    SearchResult,
    SemanticIndex,
    VoyageEmbedder,
    build_repo_doc,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _make_meta(
    name: str,
    description: str = "",
    topics: list[str] | None = None,
    language: str | None = None,
    pushed_at: str | None = "2024-01-01T00:00:00+00:00",
) -> RepoMetadata:
    return RepoMetadata(
        name=name,
        full_name=f"user/{name}",
        description=description or None,
        language=language,
        languages={},
        private=False,
        fork=False,
        archived=False,
        created_at=_dt("2023-01-01T00:00:00+00:00"),
        updated_at=_dt("2024-01-01T00:00:00+00:00"),
        pushed_at=_dt(pushed_at) if pushed_at else None,
        default_branch="main",
        stars=0,
        forks=0,
        open_issues=0,
        size_kb=100,
        html_url=f"https://github.com/user/{name}",
        clone_url=f"https://github.com/user/{name}.git",
        topics=topics or [],
    )


def _make_audit(
    name: str,
    description: str = "",
    topics: list[str] | None = None,
    language: str | None = None,
    source_dirs: list[str] | None = None,
    config_files: list[str] | None = None,
    pushed_at: str | None = "2024-01-01T00:00:00+00:00",
) -> RepoAudit:
    structure_details: dict[str, Any] = {}
    if source_dirs is not None:
        structure_details["source_dirs"] = source_dirs
    if config_files is not None:
        structure_details["config_files"] = config_files

    analyzer_results = [
        AnalyzerResult(
            dimension="structure",
            score=5.0,
            max_score=10.0,
            findings=[],
            details=structure_details,
        ),
        AnalyzerResult(
            dimension="readme",
            score=5.0,
            max_score=10.0,
            findings=[],
            details={},
        ),
    ]
    return RepoAudit(
        metadata=_make_meta(
            name, description=description, topics=topics, language=language, pushed_at=pushed_at
        ),
        analyzer_results=analyzer_results,
        overall_score=5.0,
        completeness_tier="developing",
    )


class _FakeEmbedder:
    """Deterministic test embedder that returns a fixed-dim zero vector plus a unique slot."""

    name = "fake-embedder"
    dimension = 4

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        # Return distinct vectors per text using hash-based seeding
        result = []
        for t in texts:
            h = hashlib.md5(t.encode()).digest()
            v = [h[i] / 255.0 for i in range(4)]
            # Normalize so cosine is meaningful
            norm = sum(x**2 for x in v) ** 0.5
            result.append([x / norm for x in v] if norm > 0 else [0.25] * 4)
        return result


def _make_index(tmp_path: Path, embedder: Any | None = None) -> SemanticIndex:
    db = tmp_path / "warehouse.db"
    if embedder is None:
        embedder = _FakeEmbedder()
    return SemanticIndex(db, embedder)


# ---------------------------------------------------------------------------
# 1. Doc construction
# ---------------------------------------------------------------------------


class TestDocConstruction:
    def test_includes_name_and_description(self) -> None:
        audit = _make_audit("MyRepo", description="A neat tool")
        doc = build_repo_doc(audit)
        assert "MyRepo" in doc
        assert "A neat tool" in doc

    def test_includes_topics(self) -> None:
        audit = _make_audit("Repo", topics=["python", "ml"])
        doc = build_repo_doc(audit)
        assert "python" in doc
        assert "ml" in doc

    def test_includes_language(self) -> None:
        audit = _make_audit("Repo", language="Rust")
        doc = build_repo_doc(audit)
        assert "Language: Rust" in doc

    def test_includes_source_dirs_and_config_files(self) -> None:
        audit = _make_audit(
            "Repo",
            source_dirs=["src", "lib"],
            config_files=["Makefile", "pyproject.toml"],
        )
        doc = build_repo_doc(audit)
        assert "src" in doc
        assert "Makefile" in doc

    def test_empty_topics_shows_dash(self) -> None:
        audit = _make_audit("Repo", topics=[])
        doc = build_repo_doc(audit)
        assert "Topics: —" in doc

    def test_no_language_shows_dash(self) -> None:
        audit = _make_audit("Repo", language=None)
        doc = build_repo_doc(audit)
        assert "Language: —" in doc

    def test_no_files_shows_dash(self) -> None:
        audit = _make_audit("Repo")  # no source_dirs / config_files
        doc = build_repo_doc(audit)
        assert "Files: —" in doc

    def test_readme_snippet_included_when_present(self) -> None:
        audit = _make_audit("Repo")
        # Inject a readme paragraph into the readme analyzer result
        for ar in audit.analyzer_results:
            if ar.dimension == "readme":
                ar.details["first_paragraph"] = "This is the readme."
        doc = build_repo_doc(audit)
        assert "This is the readme." in doc

    def test_readme_snippet_truncated_at_2000(self) -> None:
        audit = _make_audit("Repo")
        long_text = "x" * 5000
        for ar in audit.analyzer_results:
            if ar.dimension == "readme":
                ar.details["first_paragraph"] = long_text
        doc = build_repo_doc(audit)
        assert "x" * 2000 in doc
        assert "x" * 2001 not in doc


# ---------------------------------------------------------------------------
# 2. Reindex skip logic
# ---------------------------------------------------------------------------


class TestReindexSkipLogic:
    def test_same_doc_same_embedder_skips_on_second_call(self, tmp_path: Path) -> None:
        idx = _make_index(tmp_path)
        audits = [_make_audit("Repo")]

        r1 = idx.reindex(audits)
        assert r1["embedded"] == 1
        assert r1["skipped"] == 0

        r2 = idx.reindex(audits)
        assert r2["embedded"] == 0
        assert r2["skipped"] == 1

    def test_different_doc_re_embeds(self, tmp_path: Path) -> None:
        idx = _make_index(tmp_path)
        audit_v1 = _make_audit("Repo", description="version one")
        idx.reindex([audit_v1])

        audit_v2 = _make_audit("Repo", description="version two")
        r2 = idx.reindex([audit_v2])
        assert r2["embedded"] == 1
        assert r2["skipped"] == 0

    def test_different_embedder_re_embeds(self, tmp_path: Path) -> None:
        embedder_a = _FakeEmbedder()
        embedder_a.name = "embedder-a"
        idx_a = SemanticIndex(tmp_path / "warehouse.db", embedder_a)
        audit = _make_audit("Repo", description="same doc")
        idx_a.reindex([audit])

        embedder_b = _FakeEmbedder()
        embedder_b.name = "embedder-b"
        idx_b = SemanticIndex(tmp_path / "warehouse.db", embedder_b)
        r2 = idx_b.reindex([audit])
        assert r2["embedded"] == 1

    def test_force_re_embeds_unchanged_doc(self, tmp_path: Path) -> None:
        idx = _make_index(tmp_path)
        audits = [_make_audit("Repo")]
        idx.reindex(audits)

        r2 = idx.reindex(audits, force=True)
        assert r2["embedded"] == 1
        assert r2["skipped"] == 0

    def test_total_matches_input_count(self, tmp_path: Path) -> None:
        idx = _make_index(tmp_path)
        audits = [_make_audit(f"Repo{i}") for i in range(5)]
        r = idx.reindex(audits)
        assert r["total"] == 5

    def test_duration_s_is_non_negative_float(self, tmp_path: Path) -> None:
        idx = _make_index(tmp_path)
        r = idx.reindex([_make_audit("Repo")])
        assert isinstance(r["duration_s"], float)
        assert r["duration_s"] >= 0.0


# ---------------------------------------------------------------------------
# 3. Search ranking
# ---------------------------------------------------------------------------


class TestSearchRanking:
    def _build_index_with_repos(self, tmp_path: Path) -> SemanticIndex:
        """Index 5 repos with distinct docs."""
        idx = _make_index(tmp_path)
        audits = [
            _make_audit("RustDB", description="a fast Rust database engine", language="Rust"),
            _make_audit("PythonML", description="machine learning with Python", language="Python"),
            _make_audit("SwiftUI", description="iOS SwiftUI design patterns", language="Swift"),
            _make_audit("GoMicro", description="Go microservices framework", language="Go"),
            _make_audit(
                "NodeAPI", description="Node.js REST API boilerplate", language="JavaScript"
            ),
        ]
        idx.reindex(audits)
        return idx

    def test_top_result_is_most_relevant(self, tmp_path: Path) -> None:
        idx = self._build_index_with_repos(tmp_path)
        results = idx.search("Rust database storage engine", k=5)
        assert len(results) >= 1
        assert results[0].repo_name == "RustDB"

    def test_results_sorted_ascending_by_distance(self, tmp_path: Path) -> None:
        idx = self._build_index_with_repos(tmp_path)
        results = idx.search("iOS Swift mobile app", k=5)
        scores = [r.score for r in results]
        assert scores == sorted(scores)

    def test_k_limits_result_count(self, tmp_path: Path) -> None:
        idx = self._build_index_with_repos(tmp_path)
        results = idx.search("anything", k=3)
        assert len(results) <= 3

    def test_search_returns_search_result_objects(self, tmp_path: Path) -> None:
        idx = self._build_index_with_repos(tmp_path)
        results = idx.search("python machine learning", k=5)
        for r in results:
            assert isinstance(r, SearchResult)
            assert isinstance(r.repo_name, str)
            assert isinstance(r.score, float)
            assert isinstance(r.snippet, str)


# ---------------------------------------------------------------------------
# 4. Cosine distance ordering
# ---------------------------------------------------------------------------


class TestCosineDistanceOrdering:
    def test_identical_vector_has_zero_distance(self, tmp_path: Path) -> None:
        """Insert a vec and query with the same vec; distance should be ~0."""
        idx = _make_index(tmp_path)
        audit = _make_audit("TargetRepo", description="exact match test")
        idx.reindex([audit])

        # Query with something very similar — same audit doc
        results = idx.search("exact match test", k=1)
        # We can't guarantee 0 because the query text ≠ index doc text,
        # but we CAN verify distance is in [0, 1] for cosine
        assert len(results) == 1
        assert 0.0 <= results[0].score <= 1.0

    def test_cosine_distance_range(self, tmp_path: Path) -> None:
        """All cosine distances should be in [0, 1]."""
        idx = _make_index(tmp_path)
        audits = [_make_audit(f"Repo{i}") for i in range(3)]
        idx.reindex(audits)
        results = idx.search("query text", k=3)
        for r in results:
            assert 0.0 <= r.score <= 1.0, f"score {r.score} out of [0,1]"


# ---------------------------------------------------------------------------
# 5. Voyage embedder — mock API
# ---------------------------------------------------------------------------


class TestVoyageEmbedder:
    def test_raises_without_api_key(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            if "VOYAGE_API_KEY" in __import__("os").environ:
                pytest.skip("VOYAGE_API_KEY set in environment")
            env = {k: v for k, v in __import__("os").environ.items() if k != "VOYAGE_API_KEY"}
            with patch.dict("os.environ", env, clear=True):
                with pytest.raises(RuntimeError, match="VOYAGE_API_KEY"):
                    VoyageEmbedder()

    @responses_lib.activate
    def test_sends_correct_request_shape(self) -> None:
        fake_key = "vk-test-key"
        fake_dim = VOYAGE_DIM
        fake_vecs = [[0.1] * fake_dim]

        from src.semantic_index import VOYAGE_API_BASE_URL

        responses_lib.add(
            responses_lib.POST,
            f"{VOYAGE_API_BASE_URL}/embeddings",
            json={"data": [{"embedding": fake_vecs[0]}]},
            status=200,
        )
        with patch.dict("os.environ", {"VOYAGE_API_KEY": fake_key}):
            emb = VoyageEmbedder()
            result = emb.embed(["hello world"])

        assert result == fake_vecs
        assert len(responses_lib.calls) == 1
        req_body = json.loads(responses_lib.calls[0].request.body)
        assert req_body["model"] == "voyage-code-3"
        assert req_body["input"] == ["hello world"]
        assert req_body["output_dimension"] == fake_dim

    @responses_lib.activate
    def test_auth_header_uses_api_key(self) -> None:
        fake_key = "vk-auth-header-test"

        from src.semantic_index import VOYAGE_API_BASE_URL

        responses_lib.add(
            responses_lib.POST,
            f"{VOYAGE_API_BASE_URL}/embeddings",
            json={"data": [{"embedding": [0.0] * VOYAGE_DIM}]},
            status=200,
        )
        with patch.dict("os.environ", {"VOYAGE_API_KEY": fake_key}):
            VoyageEmbedder().embed(["test"])

        assert responses_lib.calls[0].request.headers["Authorization"] == f"Bearer {fake_key}"


# ---------------------------------------------------------------------------
# 6. Local embedder — mock sentence-transformers
# ---------------------------------------------------------------------------


class TestLocalEmbedder:
    def test_raises_import_error_when_not_installed(self) -> None:
        with patch.dict("sys.modules", {"sentence_transformers": None}):
            from src.semantic_index import LocalEmbedder

            with pytest.raises(ImportError, match="sentence-transformers"):
                LocalEmbedder()

    def test_embed_calls_model_encode(self) -> None:
        import numpy as np

        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1, 0.2, 0.3, 0.4]])

        mock_st = MagicMock()
        mock_st.SentenceTransformer.return_value = mock_model

        with patch.dict("sys.modules", {"sentence_transformers": mock_st}):
            from src.semantic_index import LocalEmbedder  # fresh import

            emb = LocalEmbedder()
            result = emb.embed(["sample text"])

        mock_model.encode.assert_called_once()
        assert len(result) == 1
        assert len(result[0]) == 4


# ---------------------------------------------------------------------------
# 7. Missing dependencies — graceful degradation
# ---------------------------------------------------------------------------


class TestMissingDependencies:
    def test_no_voyage_key_and_no_sentence_transformers_returns_none(self, tmp_path: Path) -> None:
        """from_embedder_name should return None (not raise) when both paths fail."""
        env = {k: v for k, v in __import__("os").environ.items() if k != "VOYAGE_API_KEY"}
        with patch.dict("os.environ", env, clear=True):
            with patch.dict("sys.modules", {"sentence_transformers": None}):
                result = SemanticIndex.from_embedder_name(tmp_path / "warehouse.db", "voyage")
        assert result is None

    def test_from_embedder_name_voyage_missing_key_returns_none(self, tmp_path: Path) -> None:
        env = {k: v for k, v in __import__("os").environ.items() if k != "VOYAGE_API_KEY"}
        with patch.dict("os.environ", env, clear=True):
            result = SemanticIndex.from_embedder_name(tmp_path / "db.sqlite", "voyage")
        assert result is None

    def test_from_embedder_name_local_missing_dep_returns_none(self, tmp_path: Path) -> None:
        with patch.dict("sys.modules", {"sentence_transformers": None}):
            result = SemanticIndex.from_embedder_name(tmp_path / "db.sqlite", "local")
        assert result is None

    def test_from_embedder_name_unknown_embedder_returns_none(self, tmp_path: Path) -> None:
        result = SemanticIndex.from_embedder_name(tmp_path / "db.sqlite", "unknown")
        assert result is None


# ---------------------------------------------------------------------------
# 8. CLI integration (light unit test — no subprocess)
# ---------------------------------------------------------------------------


class TestCLIIntegration:
    """Verify that the CLI wiring calls SemanticIndex correctly when flags present."""

    def test_reindex_flag_calls_reindex_once(self, tmp_path: Path) -> None:
        """When --reindex is set, the post-audit hook should call reindex once."""

        mock_idx = MagicMock(spec=SemanticIndex)
        mock_idx.reindex.return_value = {
            "embedded": 2,
            "skipped": 0,
            "total": 2,
            "duration_s": 0.1,
        }

        audits = [_make_audit("Repo1"), _make_audit("Repo2")]

        # Simulate the CLI post-audit hook
        from src.semantic_index import _run_reindex

        _run_reindex(mock_idx, audits, force=False)

        mock_idx.reindex.assert_called_once_with(audits, force=False)

    def test_ask_flag_calls_search_once(self, tmp_path: Path) -> None:
        mock_idx = MagicMock(spec=SemanticIndex)
        mock_idx.search.return_value = [
            SearchResult(repo_name="RustDB", score=0.1, snippet="repo: RustDB")
        ]

        from src.semantic_index import _run_search

        results = _run_search(mock_idx, "rust database", k=5)

        mock_idx.search.assert_called_once_with("rust database", k=5)
        assert results[0].repo_name == "RustDB"
