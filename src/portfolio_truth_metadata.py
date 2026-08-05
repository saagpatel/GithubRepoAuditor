"""Shared producer contracts for PortfolioTruth top-level metadata envelopes."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.portfolio_truth_coverage import ProjectLike
from src.portfolio_truth_sources import (
    WORKSPACE_DISCOVERY_POLICY_VERSION,
    checkout_collision_summary,
)


def _section(project: ProjectLike, name: str) -> Any:
    if isinstance(project, Mapping):
        return project[name]
    return getattr(project, name)


def _optional_section(project: ProjectLike, name: str) -> Any:
    if isinstance(project, Mapping):
        return project.get(name, {})
    return getattr(project, name, {})


def _field(section: Any, name: str) -> Any:
    if isinstance(section, Mapping):
        return section.get(name)
    return getattr(section, name)


def _has_path_catalog_contract(project: ProjectLike) -> bool:
    identity = _section(project, "identity")
    provenance = _optional_section(project, "provenance")
    return any(
        source.get("source") == "catalog_repo"
        and source.get("detail") == _field(identity, "path")
        for source in provenance.values()
        if isinstance(source, Mapping)
    )


def duplicate_display_names(projects: Sequence[ProjectLike]) -> list[str]:
    return sorted(
        name
        for name, count in Counter(
            str(_field(_section(project, "identity"), "display_name"))
            for project in projects
        ).items()
        if count > 1
    )


def unresolved_duplicate_display_names(
    projects: Sequence[ProjectLike],
) -> list[str]:
    grouped: dict[str, list[ProjectLike]] = {}
    for project in projects:
        name = str(_field(_section(project, "identity"), "display_name"))
        grouped.setdefault(name, []).append(project)
    return sorted(
        name
        for name, members in grouped.items()
        if len(members) > 1
        and any(not _has_path_catalog_contract(project) for project in members)
    )


def build_source_summary(
    *,
    workspace_root: str,
    projects: Sequence[ProjectLike],
    catalog_errors: Sequence[str],
    catalog_warnings: Sequence[str],
    legacy_registry_rows: int,
    notion_context_rows: int,
    notion_context_carried_forward: bool,
    checkout_collisions: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Build the exact producer summary from bounded inputs and project facts."""
    return {
        "workspace_root": workspace_root,
        "project_count": len(projects),
        "checkout_collisions": checkout_collision_summary(list(checkout_collisions)),
        "catalog_errors": list(catalog_errors),
        "catalog_warnings": list(catalog_warnings),
        "legacy_registry_rows": legacy_registry_rows,
        "notion_context_rows": notion_context_rows,
        "notion_context_carried_forward": notion_context_carried_forward,
        "context_quality_counts": dict(
            Counter(
                _field(_section(project, "derived"), "context_quality")
                for project in projects
            )
        ),
        "activity_status_counts": dict(
            Counter(
                _field(_section(project, "derived"), "activity_status")
                for project in projects
            )
        ),
        "archived_count": sum(
            _field(_section(project, "derived"), "archived")
            for project in projects
        ),
        "attention_state_counts": dict(
            Counter(
                _field(_section(project, "derived"), "attention_state")
                for project in projects
            )
        ),
        "github_archived_count": sum(
            (
                _optional_section(project, "provenance")
                .get("github.archived", {})
                .get("detail")
                == "true"
            )
            for project in projects
        ),
        "duplicate_display_names": duplicate_display_names(projects),
        "unresolved_duplicate_display_names": unresolved_duplicate_display_names(
            projects
        ),
    }


def build_warnings(
    *,
    catalog_errors: Sequence[str],
    catalog_warnings: Sequence[str],
    unresolved_duplicates: Sequence[str],
    checkout_collisions: Sequence[dict[str, Any]] = (),
) -> list[str]:
    warnings = [*catalog_errors, *catalog_warnings]
    if unresolved_duplicates:
        warnings.append(
            "Duplicate project display names require path-qualified registry labels: "
            + ", ".join(unresolved_duplicates)
        )
    ambiguous_checkout_origins = [
        str(group["origin"])
        for group in checkout_collisions
        if group.get("selection", {}).get("state") == "unknown"
    ]
    if ambiguous_checkout_origins:
        warnings.append(
            "Checkout authority is UNKNOWN for same-origin checkout groups: "
            + ", ".join(ambiguous_checkout_origins)
        )
    return warnings


def build_input_envelope(
    *,
    workspace_root: str,
    catalog_path: str | Path | None,
    now: datetime,
    include_notion: bool,
    notion_context_rows: int,
    notion_context_carried_forward: bool,
    prior_notion_generated_at: str | None,
    notion_source_mode: str,
    notion_observed_at: str | None,
    security_coverage_metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    resolved_catalog = Path(str(catalog_path or ""))
    catalog_hash = (
        hashlib.sha256(resolved_catalog.read_bytes()).hexdigest()
        if resolved_catalog.is_file()
        else None
    )
    if not include_notion or notion_context_rows == 0:
        notion_mode = "unavailable"
        notion_observed_at = None
    elif notion_context_carried_forward:
        notion_mode = "carried-forward" if prior_notion_generated_at else "unavailable"
        notion_observed_at = prior_notion_generated_at
    else:
        notion_mode = notion_source_mode
        notion_observed_at = notion_observed_at or now.isoformat()
    inputs = {
        "catalog": {
            "source_id": "portfolio-catalog",
            "sha256": catalog_hash,
            "observed_at": now.isoformat(),
        },
        "workspace": {
            "source_id": "projects-root",
            "observed_at": now.isoformat(),
        },
        "notion": {
            "mode": notion_mode,
            "observed_at": notion_observed_at,
            "carried_from_generated_at": (
                prior_notion_generated_at if notion_context_carried_forward else None
            ),
        },
    }
    if security_coverage_metadata:
        github_security = dict(security_coverage_metadata)
        produced_at = github_security.get("produced_at")
        if isinstance(produced_at, str):
            try:
                parsed_produced_at = datetime.fromisoformat(
                    produced_at.replace("Z", "+00:00")
                )
            except ValueError:
                pass
            else:
                if parsed_produced_at.tzinfo is not None:
                    raw_age_hours = (
                        now.astimezone(timezone.utc)
                        - parsed_produced_at.astimezone(timezone.utc)
                    ).total_seconds() / 3600
                    github_security["age_hours"] = round(
                        max(raw_age_hours, 0.0), 3
                    )
        inputs["github_security"] = github_security
    return inputs


def build_exclusions(counts: Mapping[str, int]) -> dict[str, Any]:
    return {
        "policy_version": WORKSPACE_DISCOVERY_POLICY_VERSION,
        "counts": dict(sorted(counts.items())),
    }
