from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from src.analyzers.activity import ActivityAnalyzer
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


def run_all_analyzers(
    repo_path: Path,
    metadata: RepoMetadata,
    github_client: GitHubClient | None = None,
) -> list[AnalyzerResult]:
    """Run all analyzers against a repo, catching failures gracefully."""
    results: list[AnalyzerResult] = []

    for analyzer in ALL_ANALYZERS:
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
