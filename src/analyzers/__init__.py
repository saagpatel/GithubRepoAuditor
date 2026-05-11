from __future__ import annotations

import dataclasses
import importlib.util
import inspect
import logging
import sqlite3
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from src.analyzers.activity import ActivityAnalyzer
from src.analyzers.base import BaseAnalyzer
from src.analyzers.cicd import CicdAnalyzer
from src.analyzers.code_quality import CodeQualityAnalyzer
from src.analyzers.community_profile import CommunityProfileAnalyzer
from src.analyzers.completeness import BuildReadinessAnalyzer, DocumentationAnalyzer
from src.analyzers.dependencies import DependenciesAnalyzer
from src.analyzers.interest import InterestAnalyzer
from src.analyzers.readme import ReadmeAnalyzer
from src.analyzers.security import SecurityAnalyzer
from src.analyzers.structure import StructureAnalyzer
from src.analyzers.testing import TestingAnalyzer
from src.models import AnalyzerResult, RepoMetadata

if TYPE_CHECKING:
    from src.github_client import GitHubClient

logger = logging.getLogger(__name__)

ALL_ANALYZERS = [
    ReadmeAnalyzer(),
    StructureAnalyzer(),
    CodeQualityAnalyzer(),
    TestingAnalyzer(),
    CicdAnalyzer(),
    DependenciesAnalyzer(),
    ActivityAnalyzer(),
    DocumentationAnalyzer(),
    BuildReadinessAnalyzer(),
    CommunityProfileAnalyzer(),
    InterestAnalyzer(),
    SecurityAnalyzer(),
]


def load_custom_analyzers(directory: Path) -> list[BaseAnalyzer]:
    """Discover BaseAnalyzer subclasses in .py files under directory."""
    analyzers: list[BaseAnalyzer] = []
    if not directory.is_dir():
        return analyzers

    for py_file in sorted(directory.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            for _, cls in inspect.getmembers(mod, inspect.isclass):
                if issubclass(cls, BaseAnalyzer) and cls is not BaseAnalyzer:
                    analyzers.append(cls())
        except Exception as e:
            print(
                f"  Warning: failed to load custom analyzer from {py_file.name}: {e}",
                file=sys.stderr,
            )
    return analyzers


def _result_from_dict(d: dict) -> AnalyzerResult:
    """Reconstruct an AnalyzerResult from its to_dict() representation."""
    return AnalyzerResult(
        dimension=d["dimension"],
        score=d["score"],
        max_score=d["max_score"],
        findings=d["findings"],
        details=d.get("details", {}),
    )


def run_with_cache(
    analyzer: BaseAnalyzer,
    repo_path: Path,
    metadata: RepoMetadata,
    github_client: "GitHubClient | None",
    commit_sha: str,
    conn: sqlite3.Connection | None,
) -> AnalyzerResult:
    """Run *analyzer*, using the SQLite cache when available.

    Cache is skipped (transparently) if:
    - ``conn`` is None  (cache disabled for this run)
    - ``analyzer.cache_inputs_hash()`` returns None  (analyzer opts out)
    - Any cache I/O error occurs (logged, falls through to re-run)
    """
    from src.analyzer_cache import lookup, store

    inputs_hash: str | None = None
    if conn is not None:
        try:
            inputs_hash = analyzer.cache_inputs_hash(repo_path, metadata)
        except Exception as exc:
            logger.warning(
                "cache_inputs_hash failed for %s on %s: %s",
                analyzer.name,
                metadata.name,
                exc,
            )

    if inputs_hash is not None and conn is not None:
        cached = lookup(conn, metadata.name, commit_sha, analyzer.name, inputs_hash)
        if cached is not None:
            return _result_from_dict(cached)

    result = analyzer.analyze(repo_path, metadata, github_client)

    if inputs_hash is not None and conn is not None:
        store(
            conn, metadata.name, commit_sha, analyzer.name, inputs_hash, dataclasses.asdict(result)
        )

    return result


def run_all_analyzers(
    repo_path: Path,
    metadata: RepoMetadata,
    github_client: "GitHubClient | None" = None,
    extra_analyzers: list[BaseAnalyzer] | None = None,
    conn: sqlite3.Connection | None = None,
    commit_sha: str = "",
) -> list[AnalyzerResult]:
    """Run all analyzers against a repo, catching failures gracefully.

    Args:
        repo_path: Path to the cloned repository.
        metadata: Repository metadata from the GitHub API.
        github_client: Optional authenticated GitHub API client.
        extra_analyzers: Additional analyzer instances to run after the defaults.
        conn: Open SQLite connection to the warehouse DB.  Pass ``None`` to disable
            the analyzer result cache (equivalent to ``--no-analyzer-cache``).
        commit_sha: Stable identifier for the current repo state (e.g. pushed_at ISO
            string or a git SHA).  Used as the cache key; an empty string disables
            caching even when ``conn`` is provided.
    """
    results: list[AnalyzerResult] = []
    analyzers_to_run = list(ALL_ANALYZERS) + (extra_analyzers or [])

    # Disable cache when no commit SHA is available to avoid polluting the cache
    # with entries that can never be invalidated.
    effective_conn = conn if commit_sha else None

    for analyzer in analyzers_to_run:
        try:
            result = run_with_cache(
                analyzer, repo_path, metadata, github_client, commit_sha, effective_conn
            )
            results.append(result)
        except Exception as exc:
            logger.warning(
                "Analyzer %s failed on %s: %s",
                analyzer.name,
                metadata.name,
                exc,
            )
            results.append(
                AnalyzerResult(
                    dimension=analyzer.name,
                    score=0.0,
                    max_score=1.0,
                    findings=[f"Analysis failed: {exc}"],
                    details={"error": str(exc)},
                )
            )

    return results
