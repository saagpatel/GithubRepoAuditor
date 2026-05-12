# src/portfolio_context_triage.py
"""Context triage runner — B1 of Arc H operational stream."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class FailureMode(str, Enum):
    DESCRIPTION = "description"
    README = "readme"
    CATALOG = "catalog"
    CONTEXT = "context"


_DESCRIPTION_CONFIDENCE_WARN_BELOW = 0.5
_CATALOG_COMPLETENESS_WARN_BELOW = 0.6
_WEAK_CONTEXT_QUALITIES = {"none", "boilerplate"}


def assess_repo_failure_modes(repo: dict[str, Any]) -> list[FailureMode]:
    modes: list[FailureMode] = []

    desc_conf = (
        repo.get("analyzers", {})
        .get("description", {})
        .get("details", {})
        .get("description_confidence", 1.0)
    )
    if desc_conf < _DESCRIPTION_CONFIDENCE_WARN_BELOW:
        modes.append(FailureMode.DESCRIPTION)

    stale_by_age = (
        repo.get("analyzers", {})
        .get("readme", {})
        .get("details", {})
        .get("readme_stale_by_age", False)
    )
    if stale_by_age:
        modes.append(FailureMode.README)

    catalog_score = repo.get("catalog_completeness", 1.0)
    if catalog_score < _CATALOG_COMPLETENESS_WARN_BELOW:
        modes.append(FailureMode.CATALOG)

    context_quality = repo.get("context_quality", "full")
    if context_quality in _WEAK_CONTEXT_QUALITIES:
        modes.append(FailureMode.CONTEXT)

    return modes


@dataclass
class TriageEntry:
    repo_name: str
    failure_modes: list[FailureMode]
    severity: str  # "critical" | "moderate" | "low"

    @classmethod
    def from_repo(cls, repo: dict[str, Any]) -> "TriageEntry":
        modes = assess_repo_failure_modes(repo)
        if len(modes) >= 3:
            severity = "critical"
        elif len(modes) == 2:
            severity = "moderate"
        else:
            severity = "low"
        return cls(
            repo_name=repo.get("name", "unknown"),
            failure_modes=modes,
            severity=severity,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo": self.repo_name,
            "failure_modes": [m.value for m in self.failure_modes],
            "severity": self.severity,
        }


def run_triage(repos: list[dict[str, Any]]) -> list[TriageEntry]:
    """Return TriageEntry for every repo that has at least one failure mode."""
    return [
        TriageEntry.from_repo(repo)
        for repo in repos
        if assess_repo_failure_modes(repo)
    ]
