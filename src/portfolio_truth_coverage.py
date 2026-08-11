"""Shared producer contract for PortfolioTruth coverage envelopes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from src.portfolio_truth_types import PortfolioTruthProject

ProjectLike = PortfolioTruthProject | Mapping[str, Any]


def _section(project: ProjectLike, name: str) -> Any:
    if isinstance(project, Mapping):
        return project[name]
    return getattr(project, name)


def _field(section: Any, name: str) -> Any:
    if isinstance(section, Mapping):
        return section.get(name)
    return getattr(section, name)


def _provider_state(project: ProjectLike, provider: str) -> str:
    security = _section(project, "security")
    if not isinstance(security, Mapping):
        return security.provider_state(provider)
    provider_payload = security.get("providers", {}).get(provider, {})
    return str(provider_payload.get("state") or "unknown")


def _provider_zero_findings(project: ProjectLike, provider: str) -> bool:
    security = _section(project, "security")
    providers = (
        security.get("providers", {})
        if isinstance(security, Mapping)
        else security.providers
    )
    return (providers.get(provider) or {}).get("zero_findings") is True


def build_coverage_envelope(
    *,
    projects: Sequence[ProjectLike],
    notion_context_carried_forward: bool,
    notion_context_rows: int,
) -> list[dict[str, Any]]:
    """Build the one canonical producer coverage envelope."""
    workspace_projects = [
        project
        for project in projects
        if not str(_field(_section(project, "identity"), "project_key")).startswith(
            "supp:"
        )
    ]
    workspace_project_count = len(workspace_projects)
    supplementary_project_count = len(projects) - workspace_project_count
    complete = sum(
        _field(_section(project, "security"), "coverage_state") == "complete"
        for project in workspace_projects
    )
    partial = sum(
        _field(_section(project, "security"), "coverage_state") == "partial"
        for project in workspace_projects
    )
    stale = sum(
        _field(_section(project, "security"), "coverage_state") == "stale"
        for project in workspace_projects
    )
    unknown = workspace_project_count - complete - partial - stale
    cohort_count = sum(
        _field(_section(project, "security"), "cohort_member")
        for project in workspace_projects
    )
    cohort_complete = sum(
        _field(_section(project, "security"), "cohort_member")
        and _field(_section(project, "security"), "coverage_state") == "complete"
        for project in workspace_projects
    )
    cohort_partial = sum(
        _field(_section(project, "security"), "cohort_member")
        and _field(_section(project, "security"), "coverage_state") == "partial"
        for project in workspace_projects
    )
    cohort_stale = sum(
        _field(_section(project, "security"), "cohort_member")
        and _field(_section(project, "security"), "coverage_state") == "stale"
        for project in workspace_projects
    )
    cohort_unknown = cohort_count - cohort_complete - cohort_partial - cohort_stale
    provider_counts = {
        provider: sum(
            _provider_state(project, provider) == "observed"
            for project in workspace_projects
        )
        for provider in ("dependabot", "code_scanning", "secret_scanning")
    }
    provider_zero_finding_counts = {
        provider: sum(
            _provider_zero_findings(project, provider)
            for project in workspace_projects
        )
        for provider in ("dependabot", "code_scanning", "secret_scanning")
    }
    remote_default_branch_counts = {
        state: sum(
            (
                _section(project, "repository_state").get("remote_default_branch")
                or {}
            ).get("state")
            == state
            for project in workspace_projects
        )
        for state in (
            "observed",
            "partial",
            "stale",
            "credential_unavailable",
            "forbidden",
            "not_found",
            "rate_limited",
            "transient_error",
            "malformed",
            "not_requested",
            "unknown",
        )
    }
    git_observed = sum(
        _section(project, "repository_state").get("state") == "observed"
        for project in workspace_projects
    )
    coverage = [
        {
            "source": "workspace",
            "state": "observed",
            "project_count": workspace_project_count,
        },
        {
            "source": "git",
            "state": "observed" if git_observed else "unknown",
            "observed_count": git_observed,
            "project_count": workspace_project_count,
        },
        {
            "source": "github_security",
            "state": (
                "known"
                if complete == workspace_project_count
                else "partial"
                if complete or partial
                else "unknown"
            ),
            "scanned_count": complete,
            "complete_repo_count": complete,
            "partial_repo_count": partial,
            "stale_count": stale,
            "unknown_count": unknown,
            "cohort_repository_count": cohort_count,
            "cohort_complete_count": cohort_complete,
            "cohort_partial_count": cohort_partial,
            "cohort_stale_count": cohort_stale,
            "cohort_unknown_count": cohort_unknown,
            "provider_observed_counts": provider_counts,
            "provider_zero_finding_counts": provider_zero_finding_counts,
            "remote_default_branch_counts": remote_default_branch_counts,
            "project_count": workspace_project_count,
        },
        {
            "source": "notion",
            "state": (
                "carried_forward"
                if notion_context_carried_forward
                else "observed"
                if notion_context_rows
                else "unknown"
            ),
            "observed_count": notion_context_rows,
        },
    ]
    if supplementary_project_count:
        coverage.append(
            {
                "source": "supplementary_registry",
                "state": "observed",
                "project_count": supplementary_project_count,
            }
        )
    return coverage
