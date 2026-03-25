from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from src.models import AnalyzerResult, RepoMetadata

if TYPE_CHECKING:
    from src.github_client import GitHubClient


class BaseAnalyzer(ABC):
    """Abstract base for all repo analyzers."""

    name: str
    weight: float

    @abstractmethod
    def analyze(
        self,
        repo_path: Path,
        metadata: RepoMetadata,
        github_client: GitHubClient | None = None,
    ) -> AnalyzerResult:
        ...

    def _result(
        self,
        score: float,
        findings: list[str],
        details: dict | None = None,
    ) -> AnalyzerResult:
        """Convenience to build an AnalyzerResult for this dimension."""
        return AnalyzerResult(
            dimension=self.name,
            score=min(max(score, 0.0), 1.0),
            max_score=1.0,
            findings=findings,
            details=details or {},
        )
