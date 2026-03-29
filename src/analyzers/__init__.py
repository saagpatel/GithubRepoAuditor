from __future__ import annotations

import importlib.util
import inspect
import logging
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
            print(f"  Warning: failed to load custom analyzer from {py_file.name}: {e}", file=sys.stderr)
    return analyzers


def run_all_analyzers(
    repo_path: Path,
    metadata: RepoMetadata,
    github_client: GitHubClient | None = None,
    extra_analyzers: list[BaseAnalyzer] | None = None,
) -> list[AnalyzerResult]:
    """Run all analyzers against a repo, catching failures gracefully."""
    results: list[AnalyzerResult] = []
    analyzers_to_run = list(ALL_ANALYZERS) + (extra_analyzers or [])

    for analyzer in analyzers_to_run:
        try:
            result = analyzer.analyze(repo_path, metadata, github_client)
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
