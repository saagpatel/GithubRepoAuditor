from __future__ import annotations

import json
import logging
import re
import hashlib
from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.portfolio_catalog import (
    catalog_entry_for_repo,
    group_entry_for_path,
    load_portfolio_catalog,
)
from src.portfolio_context_contract import has_substantive_readme_support
from src.portfolio_pathing import build_operating_path_entry
from src.portfolio_risk import build_risk_entry
from src.portfolio_repository_state import observe_repository_state
from src.portfolio_truth_sources import (
    WORKSPACE_DISCOVERY_POLICY_VERSION,
    discover_workspace_projects,
    load_legacy_registry_rows,
    load_safe_notion_project_context,
)
from src.portfolio_truth_types import (
    DERIVATION_POLICY_VERSION,
    SCHEMA_VERSION,
    AdvisoryFields,
    DeclaredFields,
    DerivedFields,
    IdentityFields,
    PortfolioTruthProject,
    PortfolioTruthSnapshot,
    RiskFields,
    SecurityFields,
    display_activity_status,
)
from src.registry_parser import _normalize

logger = logging.getLogger(__name__)

PRECEDENCE_MATRIX: dict[str, list[str]] = {
    "declared.owner": ["catalog_repo", "catalog_group"],
    "declared.team": ["catalog_repo", "catalog_group"],
    "declared.purpose": ["catalog_repo", "catalog_group"],
    "declared.lifecycle_state": ["catalog_repo", "catalog_group"],
    "declared.criticality": ["catalog_repo", "catalog_group"],
    "declared.review_cadence": ["catalog_repo", "catalog_group"],
    "declared.intended_disposition": ["catalog_repo", "catalog_group"],
    "declared.maturity_program": ["catalog_repo", "catalog_group", "catalog_defaults"],
    "declared.target_maturity": ["catalog_repo", "catalog_group", "catalog_defaults"],
    "declared.operating_path": ["normalized"],
    "declared.category": ["catalog_repo", "catalog_group", "legacy_registry"],
    "declared.tool_provenance": [
        "catalog_repo",
        "catalog_group",
        "inference",
        "legacy_registry",
    ],
    "declared.notes": ["catalog_repo", "catalog_group", "legacy_registry"],
    "derived.stack": ["workspace", "legacy_registry"],
    "derived.context_quality": ["workspace", "catalog_repo", "catalog_group"],
    "derived.context_files": ["workspace"],
    "derived.primary_context_file": ["workspace"],
    "derived.project_summary_present": ["workspace"],
    "derived.current_state_present": ["workspace"],
    "derived.stack_present": ["workspace"],
    "derived.run_instructions_present": ["workspace"],
    "derived.known_risks_present": ["workspace"],
    "derived.next_recommended_move_present": ["workspace"],
    "derived.last_meaningful_activity_at": ["git", "workspace"],
    "derived.activity_status": ["derived"],
    "derived.archived": ["derived"],
    "derived.attention_state": ["derived"],
    "derived.path_override": ["normalized"],
    "derived.path_confidence": ["normalized"],
    "derived.path_rationale": ["normalized"],
    "derived.has_tests": ["workspace"],
    "derived.has_ci": ["workspace"],
    "derived.readme_char_count": ["workspace"],
}

# ── Strict signal constants (mirror src/analyzers/testing.py and cicd.py) ──
_TEST_DIRS = frozenset(("test", "tests", "__tests__", "spec", "test_suite"))
_TEST_PATTERNS = (
    "test_*.py",
    "*_test.py",
    "*Test.swift",
    "*Tests.swift",
    "*.test.ts",
    "*.test.tsx",
    "*.spec.ts",
    "*.spec.tsx",
    "*_test.*",
    "*_spec.*",
    "test_*.*",
    "*.test.*",
    "*.spec.*",
)
_README_NAMES = ("README.md", "README.MD", "README.markdown", "README.rst", "readme.md")
_LICENSE_NAMES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "COPYING.md")


def _derive_has_tests(project_path: Path | None, has_git: bool) -> bool:
    """Return True if the project has a tests directory or test files."""
    if not has_git or project_path is None:
        return False
    if not project_path.exists():
        logger.debug("_derive_has_tests: path does not exist: %s", project_path)
        return False
    # Check for test directories
    for dirname in _TEST_DIRS:
        if (project_path / dirname).is_dir():
            return True
    # Check for test files via glob patterns (capped to avoid huge repos)
    for pattern in _TEST_PATTERNS:
        try:
            match = next(
                f
                for f in project_path.rglob(pattern)
                if f.is_file()
                and "node_modules" not in f.parts
                and ".git" not in f.parts
            )
            if match:
                return True
        except StopIteration:
            # No matching files for this pattern; try the next pattern.
            pass
    return False


def _derive_has_ci(project_path: Path | None, has_git: bool) -> bool:
    """Return True if .github/workflows/ contains any .yml or .yaml file."""
    if not has_git or project_path is None:
        return False
    if not project_path.exists():
        logger.debug("_derive_has_ci: path does not exist: %s", project_path)
        return False
    workflows_dir = project_path / ".github" / "workflows"
    if not workflows_dir.is_dir():
        return False
    return any(
        f.suffix in (".yml", ".yaml") and f.is_file() for f in workflows_dir.iterdir()
    )


def _derive_has_license(project_path: Path | None, has_git: bool) -> bool:
    """Return True if the project root contains a recognized license file."""
    if not has_git or project_path is None:
        return False
    if not project_path.exists():
        logger.debug("_derive_has_license: path does not exist: %s", project_path)
        return False
    for name in _LICENSE_NAMES:
        if (project_path / name).is_file():
            return True
    license_names = {name.lower() for name in _LICENSE_NAMES}
    for candidate in project_path.iterdir():
        if candidate.is_file() and candidate.name.lower() in license_names:
            return True
    return False


def _derive_readme_char_count(project_path: Path | None, has_git: bool) -> int:
    """Return char count of the first README found at the project root; 0 if none."""
    if not has_git or project_path is None:
        return 0
    if not project_path.exists():
        logger.debug("_derive_readme_char_count: path does not exist: %s", project_path)
        return 0
    # Try well-known names first, then case-insensitive glob
    for name in _README_NAMES:
        candidate = project_path / name
        if candidate.is_file():
            return len(candidate.read_text(errors="replace"))
    # Case-insensitive fallback
    for candidate in project_path.iterdir():
        if candidate.is_file() and candidate.name.lower().startswith("readme"):
            return len(candidate.read_text(errors="replace"))
    return 0


def _catalog_supported_context_quality(
    raw_context_quality: str,
    *,
    raw_project: dict[str, Any],
    declared_values: dict[str, Any],
    provenance: dict[str, dict[str, str]],
    readme_char_count: int,
) -> str:
    if raw_context_quality != "minimum-viable":
        return raw_context_quality
    if declared_values.get("lifecycle_state") != "active":
        return raw_context_quality
    if declared_values.get("criticality") != "high":
        return raw_context_quality
    if declared_values.get("intended_disposition") != "maintain":
        return raw_context_quality
    if declared_values.get("category") != "infrastructure":
        return raw_context_quality
    if provenance.get("declared.category", {}).get("source") not in {
        "catalog_repo",
        "catalog_group",
    }:
        return raw_context_quality
    if not has_substantive_readme_support(
        str(raw_project.get("primary_context_file") or ""),
        list(raw_project.get("context_files") or []),
        readme_char_count,
    ):
        return raw_context_quality
    return "standard"


@dataclass(frozen=True)
class PortfolioTruthBuildResult:
    snapshot: PortfolioTruthSnapshot
    catalog_data: dict[str, Any]
    legacy_rows: dict[str, dict[str, str]]


def build_portfolio_truth_snapshot(
    *,
    workspace_root: Path,
    catalog_path: Path | None = None,
    legacy_registry_path: Path | None = None,
    include_notion: bool = True,
    notion_context_fallback: dict[str, dict[str, str]] | None = None,
    now: datetime | None = None,
    release_count_by_name: dict[str, int] | None = None,
    security_alerts_by_name: dict[str, dict] | None = None,
    security_coverage_metadata: dict[str, Any] | None = None,
    repo_status_by_name: dict[str, dict] | None = None,
    producer: dict[str, Any] | None = None,
    prior_notion_generated_at: str | None = None,
) -> PortfolioTruthBuildResult:
    now = now or datetime.now(timezone.utc)
    catalog_data = load_portfolio_catalog(catalog_path)
    legacy_rows = load_legacy_registry_rows(legacy_registry_path)
    notion_context = load_safe_notion_project_context() if include_notion else {}
    notion_context_carried_forward = False
    if include_notion and not notion_context and notion_context_fallback:
        # Live Notion was unavailable; carry forward the prior published context so
        # a headless refresh updates risk/activity signals without dropping advisory
        # data to zero. The caller opts in via publish_portfolio_truth(allow_empty_notion=True).
        notion_context = notion_context_fallback
        notion_context_carried_forward = True
        logger.warning(
            "Live Notion context unavailable; carrying forward %d project rows "
            "from the prior portfolio-truth artifact.",
            len(notion_context),
        )

    exclusion_counts: dict[str, int] = {}
    workspace_projects = discover_workspace_projects(
        workspace_root,
        catalog_data=catalog_data,
        now=now,
        exclusion_counts=exclusion_counts,
    )
    projects = [
        _build_truth_project(
            raw_project,
            catalog_data=catalog_data,
            legacy_rows=legacy_rows,
            notion_context=notion_context,
            now=now,
            release_count_by_name=release_count_by_name,
            security_alerts_by_name=security_alerts_by_name,
            repo_status_by_name=repo_status_by_name,
        )
        for raw_project in workspace_projects
    ]
    projects.sort(
        key=lambda item: (
            item.identity.section_marker.lower(),
            item.identity.display_name.lower(),
        )
    )

    source_summary = {
        "workspace_root": workspace_root.as_posix(),
        "project_count": len(projects),
        "catalog_errors": list(catalog_data.get("errors") or []),
        "catalog_warnings": list(catalog_data.get("warnings") or []),
        "legacy_registry_rows": len(legacy_rows),
        "notion_context_rows": len(notion_context),
        "notion_context_carried_forward": notion_context_carried_forward,
        "context_quality_counts": dict(
            Counter(project.derived.context_quality for project in projects)
        ),
        "activity_status_counts": dict(
            Counter(project.derived.activity_status for project in projects)
        ),
        "archived_count": sum(1 for project in projects if project.derived.archived),
        "attention_state_counts": dict(
            Counter(project.derived.attention_state for project in projects)
        ),
        "github_archived_count": sum(
            1
            for project in projects
            if project.provenance.get("github.archived", {}).get("detail") == "true"
        ),
        "duplicate_display_names": _duplicate_display_names(projects),
        "unresolved_duplicate_display_names": _unresolved_duplicate_display_names(
            projects
        ),
    }
    warnings = list(catalog_data.get("errors") or []) + list(
        catalog_data.get("warnings") or []
    )
    duplicate_display_names = source_summary["unresolved_duplicate_display_names"]
    if duplicate_display_names:
        warnings.append(
            "Duplicate project display names require path-qualified registry labels: "
            + ", ".join(duplicate_display_names)
        )

    snapshot = PortfolioTruthSnapshot(
        schema_version=SCHEMA_VERSION,
        generated_at=now,
        workspace_root=workspace_root.as_posix(),
        source_summary=source_summary,
        precedence_matrix=PRECEDENCE_MATRIX,
        warnings=warnings,
        projects=projects,
        derivation_policy_version=DERIVATION_POLICY_VERSION,
        producer=producer or {},
        inputs=_build_input_envelope(
            workspace_root=workspace_root,
            catalog_data=catalog_data,
            now=now,
            include_notion=include_notion,
            notion_context_rows=len(notion_context),
            notion_context_carried_forward=notion_context_carried_forward,
            prior_notion_generated_at=prior_notion_generated_at,
            security_coverage_metadata=security_coverage_metadata,
        ),
        coverage=_build_coverage_envelope(
            projects=projects,
            notion_context_carried_forward=notion_context_carried_forward,
            notion_context_rows=len(notion_context),
        ),
        exclusions={
            "policy_version": WORKSPACE_DISCOVERY_POLICY_VERSION,
            "counts": dict(sorted(exclusion_counts.items())),
        },
    )
    return PortfolioTruthBuildResult(
        snapshot=snapshot, catalog_data=catalog_data, legacy_rows=legacy_rows
    )


def _build_coverage_envelope(
    *,
    projects: list[PortfolioTruthProject],
    notion_context_carried_forward: bool,
    notion_context_rows: int,
) -> list[dict[str, Any]]:
    complete = sum(project.security.coverage_state == "complete" for project in projects)
    partial = sum(project.security.coverage_state == "partial" for project in projects)
    stale = sum(project.security.coverage_state == "stale" for project in projects)
    unknown = len(projects) - complete - partial - stale
    cohort_count = sum(project.security.cohort_member for project in projects)
    cohort_complete = sum(
        project.security.cohort_member
        and project.security.coverage_state == "complete"
        for project in projects
    )
    cohort_partial = sum(
        project.security.cohort_member
        and project.security.coverage_state == "partial"
        for project in projects
    )
    cohort_stale = sum(
        project.security.cohort_member
        and project.security.coverage_state == "stale"
        for project in projects
    )
    cohort_unknown = cohort_count - cohort_complete - cohort_partial - cohort_stale
    provider_counts = {
        provider: sum(
            project.security.provider_state(provider) == "observed"
            for project in projects
        )
        for provider in ("dependabot", "code_scanning", "secret_scanning")
    }
    git_observed = sum(
        project.repository_state.get("state") == "observed" for project in projects
    )
    return [
        {"source": "workspace", "state": "observed", "project_count": len(projects)},
        {"source": "git", "state": "observed" if git_observed else "unknown", "observed_count": git_observed, "project_count": len(projects)},
        {
            "source": "github_security",
            "state": (
                "known"
                if complete == len(projects)
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
            "project_count": len(projects),
        },
        {"source": "notion", "state": "carried_forward" if notion_context_carried_forward else "observed" if notion_context_rows else "unknown", "observed_count": notion_context_rows},
    ]


def _build_input_envelope(
    *,
    workspace_root: Path,
    catalog_data: dict[str, Any],
    now: datetime,
    include_notion: bool,
    notion_context_rows: int,
    notion_context_carried_forward: bool,
    prior_notion_generated_at: str | None,
    security_coverage_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    resolved_catalog = Path(str(catalog_data.get("path") or ""))
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
        notion_mode = "live"
        notion_observed_at = now.isoformat()
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
        inputs["github_security"] = dict(security_coverage_metadata)
    return inputs


def load_prior_notion_context(latest_path: Path) -> dict[str, dict[str, str]]:
    """Reconstruct a Notion project-context map from a previously published
    portfolio-truth artifact, keyed identically to live Notion context
    (``_normalize(display_name)`` -> ``{portfolio_call, momentum, current_state}``).

    Used to carry advisory context forward on a headless refresh when a live
    Notion token is unavailable, rather than overwriting local truth with zero
    rows. Only projects that actually carried Notion advisory are returned, so
    the resulting row count reflects real carried context. Returns an empty map
    when the artifact is missing or malformed.
    """
    try:
        data = json.loads(latest_path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    projects = data.get("projects")
    if not isinstance(projects, list):
        return {}
    context: dict[str, dict[str, str]] = {}
    for project in projects:
        if not isinstance(project, dict):
            continue
        identity = project.get("identity")
        advisory = project.get("advisory")
        if not isinstance(identity, dict) or not isinstance(advisory, dict):
            continue
        display_name = str(identity.get("display_name", "")).strip()
        portfolio_call = str(advisory.get("notion_portfolio_call", "")).strip()
        momentum = str(advisory.get("notion_momentum", "")).strip()
        current_state = str(advisory.get("notion_current_state", "")).strip()
        if not display_name or not (portfolio_call or momentum or current_state):
            continue
        context[_normalize(display_name)] = {
            "portfolio_call": portfolio_call,
            "momentum": momentum,
            "current_state": current_state,
        }
    return context


def _duplicate_display_names(projects: list[PortfolioTruthProject]) -> list[str]:
    return sorted(
        name
        for name, count in Counter(
            project.identity.display_name for project in projects
        ).items()
        if count > 1
    )


def _unresolved_duplicate_display_names(
    projects: list[PortfolioTruthProject],
) -> list[str]:
    grouped: dict[str, list[PortfolioTruthProject]] = {}
    for project in projects:
        grouped.setdefault(project.identity.display_name, []).append(project)
    return sorted(
        name
        for name, members in grouped.items()
        if len(members) > 1
        and any(not _has_path_catalog_contract(project) for project in members)
    )


def _has_path_catalog_contract(project: PortfolioTruthProject) -> bool:
    for source in project.provenance.values():
        if (
            source.get("source") == "catalog_repo"
            and source.get("detail") == project.identity.path
        ):
            return True
    return False


def _build_security_fields(ghas_entry: dict[str, Any] | None) -> SecurityFields:
    """Map a validated receipt entry into provider-specific security fields.

    Legacy GHAS-shaped entries remain accepted for unit/backward compatibility,
    but only a fresh observation from all three providers is complete coverage.
    """
    if not ghas_entry:
        return SecurityFields()
    raw_providers = ghas_entry.get("providers")
    if isinstance(raw_providers, dict):
        providers = {
            name: dict(raw_providers.get(name) or {})
            for name in ("dependabot", "code_scanning", "secret_scanning")
        }
    else:
        providers = {}
        for name in ("dependabot", "code_scanning", "secret_scanning"):
            legacy = dict(ghas_entry.get(name) or {})
            providers[name] = {
                "state": "observed" if legacy.get("available") else "not_requested",
                "observed_at": None,
                "http_status": None,
                "reason": "legacy_ghas_entry",
                "etag": None,
                "last_modified": None,
                "pagination_complete": bool(legacy.get("available")),
                "counts": (
                    {
                        key: value
                        for key, value in legacy.items()
                        if key != "available"
                        and isinstance(value, int)
                        and value >= 0
                    }
                    if legacy.get("available")
                    else None
                ),
            }

    states = {
        name: str((providers.get(name) or {}).get("state") or "not_requested")
        for name in providers
    }
    observed_count = sum(state == "observed" for state in states.values())
    receipt_state = str(ghas_entry.get("receipt_state") or "unknown")
    if receipt_state == "stale":
        coverage_state = "stale"
    elif observed_count == 3:
        coverage_state = "complete"
    elif observed_count:
        coverage_state = "partial"
    elif any(state == "stale" for state in states.values()):
        coverage_state = "stale"
    else:
        coverage_state = "unknown"

    def _count(provider: str, key: str) -> int | None:
        source = providers.get(provider) or {}
        if source.get("state") != "observed":
            return None
        counts = source.get("counts") or {}
        value = counts.get(key)
        return value if isinstance(value, int) and value >= 0 else 0

    return SecurityFields(
        alerts_available=coverage_state == "complete",
        coverage_state=coverage_state,
        cohort_member=bool(ghas_entry.get("cohort_member", False)),
        cohort_policy=str(ghas_entry.get("cohort_policy") or ""),
        receipt_schema_version=str(
            ghas_entry.get("receipt_schema_version") or ""
        ),
        receipt_state=receipt_state,
        source_produced_at=str(ghas_entry.get("source_produced_at") or ""),
        providers=providers,
        dependabot_critical=_count("dependabot", "critical"),
        dependabot_high=_count("dependabot", "high"),
        dependabot_medium=_count("dependabot", "medium"),
        dependabot_low=_count("dependabot", "low"),
        code_scanning_critical=_count("code_scanning", "critical"),
        code_scanning_high=_count("code_scanning", "high"),
        secret_scanning_open=_count("secret_scanning", "open"),
    )


def _select_security_entry(
    lookup: dict[str, dict], repo_full_name: str | None, display_name: str
) -> dict | None:
    """Join a project to its GHAS overlay entry. The overlay is keyed by GitHub repo
    name, but the local dir display_name often differs (e.g. "Signal & Noise" vs
    "signal-noise"), so match on the repo name from repo_full_name first and fall back
    to display_name only when repo_full_name is absent or unmatched."""
    exact = lookup.get(repo_full_name or "")
    if exact is not None:
        return exact
    if any(entry.get("receipt_schema_version") for entry in lookup.values()):
        return None
    repo_name = (repo_full_name or "").rsplit("/", 1)[-1]
    return lookup.get(repo_name) or lookup.get(display_name)


def _select_repo_status_entry(
    lookup: dict[str, dict], repo_full_name: str | None, display_name: str
) -> dict | None:
    """Join GitHub repo metadata by remote repo name, then local display name."""
    repo_name = (repo_full_name or "").rsplit("/", 1)[-1]
    return lookup.get(repo_name) or lookup.get(display_name)


def _build_truth_project(
    raw_project: dict[str, Any],
    *,
    catalog_data: dict[str, Any],
    legacy_rows: dict[str, dict[str, str]],
    notion_context: dict[str, dict[str, str]],
    now: datetime,
    release_count_by_name: dict[str, int] | None = None,
    security_alerts_by_name: dict[str, dict] | None = None,
    repo_status_by_name: dict[str, dict] | None = None,
) -> PortfolioTruthProject:
    relative_path = raw_project["path"]
    group_entry = group_entry_for_path(relative_path, catalog_data)
    repo_entry = catalog_entry_for_repo(
        {
            "name": raw_project["name"],
            "full_name": raw_project.get("repo_full_name") or raw_project["name"],
            "path": relative_path,
        },
        catalog_data,
    )
    legacy = legacy_rows.get(_normalize(raw_project["name"]), {})
    notion = notion_context.get(_normalize(raw_project["name"]), {})

    warnings: list[str] = []
    provenance: dict[str, dict[str, str]] = {}

    identity = IdentityFields(
        project_key=relative_path,
        display_name=raw_project["name"],
        path=relative_path,
        top_level_dir=raw_project["top_level_dir"],
        group_key=_resolve_group_key(relative_path, group_entry, raw_project),
        group_label=_resolve_group_label(group_entry, raw_project),
        section_marker=_resolve_section_marker(relative_path, group_entry, raw_project),
        section_label=_resolve_section_label(group_entry, raw_project),
        has_git=bool(raw_project["has_git"]),
        repo_full_name=str(raw_project.get("repo_full_name") or ""),
        default_branch=str(raw_project.get("default_branch") or ""),
    )

    declared_values = {
        "owner": _select_declared("owner", repo_entry, group_entry, provenance),
        "team": _select_declared("team", repo_entry, group_entry, provenance),
        "purpose": _select_declared("purpose", repo_entry, group_entry, provenance),
        "lifecycle_state": _select_declared(
            "lifecycle_state", repo_entry, group_entry, provenance
        ),
        "criticality": _select_declared(
            "criticality", repo_entry, group_entry, provenance
        ),
        "review_cadence": _select_declared(
            "review_cadence", repo_entry, group_entry, provenance
        ),
        "operating_path": _select_declared(
            "operating_path", repo_entry, group_entry, provenance
        ),
        # Deprecated vintage of operating_path, kept as a read-compat fallback for one
        # release; resolve_declared_operating_path consumes both with operating_path
        # taking precedence.
        "intended_disposition": _select_declared(
            "intended_disposition", repo_entry, group_entry, provenance
        ),
        "maturity_program": _select_declared_with_default(
            "maturity_program",
            repo_entry,
            group_entry,
            default_field="catalog_default_maturity_program",
            provenance=provenance,
        ),
        "target_maturity": _select_declared_with_default(
            "target_maturity",
            repo_entry,
            group_entry,
            default_field="catalog_default_target_maturity",
            provenance=provenance,
        ),
        "category": _select_with_legacy(
            "category", repo_entry, group_entry, legacy, raw_project, provenance
        ),
        "tool_provenance": _select_tool_provenance(
            repo_entry, group_entry, legacy, raw_project, provenance
        ),
        "notes": _select_with_legacy(
            "notes", repo_entry, group_entry, legacy, raw_project, provenance
        ),
        "doctor_standard": _select_declared(
            "doctor_standard", repo_entry, group_entry, provenance
        ),
        "automation_eligible": bool(repo_entry.get("automation_eligible", False)),
    }

    project_path: Path | None = raw_project.get("project_path")
    has_git = bool(raw_project["has_git"])
    derived_readme_char_count = _derive_readme_char_count(project_path, has_git)
    raw_context_quality = raw_project["context_quality"]
    context_quality = _catalog_supported_context_quality(
        raw_context_quality,
        raw_project=raw_project,
        declared_values=declared_values,
        provenance=provenance,
        readme_char_count=derived_readme_char_count,
    )
    provenance["derived.context_quality"] = {
        "source": "workspace+catalog"
        if context_quality != raw_context_quality
        else "workspace",
        "detail": (
            f"{raw_context_quality}->{context_quality}"
            if context_quality != raw_context_quality
            else raw_context_quality
        ),
    }

    status_entry = _select_repo_status_entry(
        repo_status_by_name or {},
        raw_project.get("repo_full_name"),
        raw_project["name"],
    )
    github_archived = bool(status_entry and status_entry.get("archived") is True)
    if status_entry is not None:
        provenance["github.archived"] = {
            "source": str(status_entry.get("source") or "audit_report"),
            "detail": str(github_archived).lower(),
        }

    last_activity = raw_project["last_meaningful_activity_at"]
    activity_status = _activity_status_for(last_activity, now=now)
    # Lifecycle fact, not a recency observation — orthogonal to activity_status.
    archived = github_archived or declared_values["lifecycle_state"] == "archived"

    path_entry = build_operating_path_entry(
        {
            **declared_values,
            "has_explicit_entry": bool(
                repo_entry.get("has_explicit_entry")
                or group_entry.get("has_explicit_entry")
            ),
            "catalog_default_maturity_program": repo_entry.get(
                "catalog_default_maturity_program", ""
            ),
            "catalog_default_target_maturity": repo_entry.get(
                "catalog_default_target_maturity", ""
            ),
        },
        context_quality=context_quality,
        archived=archived,
    )
    provenance["declared.operating_path"] = {
        "source": "normalized",
        "detail": path_entry.get("operating_path_source", ""),
    }
    provenance["derived.path_override"] = {
        "source": "normalized",
        "detail": path_entry.get("path_override", ""),
    }
    provenance["derived.path_confidence"] = {
        "source": "normalized",
        "detail": path_entry.get("path_confidence", ""),
    }
    provenance["derived.path_rationale"] = {
        "source": "normalized",
        "detail": "derived",
    }

    security_entry = _select_security_entry(
        security_alerts_by_name or {},
        raw_project.get("repo_full_name"),
        raw_project["name"],
    )
    security = _build_security_fields(security_entry)

    # Only Dependabot high/critical counts drive the risk tier today. Code-scanning
    # and secret-scanning counts are captured in SecurityFields for visibility but do
    # not yet feed the active-high-severity-alerts factor (Dependabot-only scope).
    risk_entry = build_risk_entry(
        display_name=raw_project["name"],
        operating_path=path_entry.get("operating_path", ""),
        path_override=path_entry.get("path_override", ""),
        context_quality=context_quality,
        activity_status=activity_status,
        archived=archived,
        criticality=declared_values["criticality"],
        doctor_standard=declared_values["doctor_standard"],
        known_risks_present=bool(raw_project["known_risks_present"]),
        run_instructions_present=bool(raw_project["run_instructions_present"]),
        security_high_alerts=security.dependabot_high or 0,
        security_critical_alerts=security.dependabot_critical or 0,
    )
    if (
        security.coverage_state != "complete"
        and risk_entry.get("risk_summary") == "No elevated risk factors."
    ):
        risk_entry["risk_summary"] = (
            "No non-security risk factors detected; GitHub security coverage is "
            f"{security.coverage_state}."
        )
    attention_state = _attention_state_for(
        activity_status=activity_status,
        archived=archived,
        lifecycle_state=declared_values["lifecycle_state"],
        operating_path=path_entry.get("operating_path", ""),
        category=declared_values["category"],
        path_override=path_entry.get("path_override", ""),
        risk_entry=risk_entry,
    )
    if (
        not security.receipt_schema_version
        and attention_state in {"active-product", "active-infra", "decision-needed"}
    ):
        security = replace(
            security,
            cohort_member=True,
            cohort_policy="portfolio-default-attention-v1",
        )

    declared = DeclaredFields(
        owner=declared_values["owner"],
        team=declared_values["team"],
        purpose=declared_values["purpose"],
        lifecycle_state=declared_values["lifecycle_state"],
        criticality=declared_values["criticality"],
        review_cadence=declared_values["review_cadence"],
        intended_disposition=declared_values["intended_disposition"],
        maturity_program=declared_values["maturity_program"],
        target_maturity=declared_values["target_maturity"],
        operating_path=path_entry.get("operating_path", ""),
        category=declared_values["category"],
        tool_provenance=declared_values["tool_provenance"],
        notes=declared_values["notes"],
        doctor_standard=declared_values["doctor_standard"],
        automation_eligible=declared_values["automation_eligible"],
    )
    provenance["derived.last_meaningful_activity_at"] = {
        "source": "git" if raw_project["has_git"] and last_activity else "workspace",
        "detail": "derived",
    }
    provenance["derived.activity_status"] = {
        "source": "derived",
        "detail": activity_status,
    }
    provenance["derived.archived"] = {
        "source": "derived",
        "detail": str(archived).lower(),
    }
    provenance["derived.attention_state"] = {
        "source": "derived",
        "detail": attention_state,
    }
    provenance["derived.stack"] = {
        "source": "workspace",
        "detail": ", ".join(raw_project["stack"]),
    }
    provenance["derived.context_files"] = {
        "source": "workspace",
        "detail": str(len(raw_project["context_files"])),
    }
    provenance["derived.primary_context_file"] = {
        "source": "workspace",
        "detail": raw_project["primary_context_file"],
    }
    for field in (
        "project_summary_present",
        "current_state_present",
        "stack_present",
        "run_instructions_present",
        "known_risks_present",
        "next_recommended_move_present",
    ):
        provenance[f"derived.{field}"] = {
            "source": "workspace",
            "detail": str(bool(raw_project[field])).lower(),
        }

    displayed_status = display_activity_status(activity_status, archived=archived)
    if legacy and legacy.get("status") and legacy["status"] != displayed_status:
        warnings.append(
            f"Legacy registry status '{legacy['status']}' differs from derived registry status '{displayed_status}'."
        )
    if not repo_entry.get("has_explicit_entry") and not group_entry.get(
        "has_explicit_entry"
    ):
        warnings.append(
            "No explicit catalog contract is recorded for this project yet."
        )
    if path_entry.get("path_override") == "investigate":
        warnings.append(
            path_entry.get(
                "path_rationale",
                "Operating path currently requires investigate override.",
            )
        )
    if github_archived and declared_values["lifecycle_state"] != "archived":
        warnings.append(
            "GitHub metadata marks this repo archived/read-only; portfolio truth reconciled it as archived attention."
        )

    # ── Strict local-filesystem signals (Sprint 8.2) ─────────────────────────
    derived_has_tests = _derive_has_tests(project_path, has_git)
    derived_has_ci = _derive_has_ci(project_path, has_git)
    derived_has_license = _derive_has_license(project_path, has_git)
    derived_release_count: int | None = None
    if release_count_by_name is not None:
        derived_release_count = release_count_by_name.get(raw_project["name"])

    derived = DerivedFields(
        stack=raw_project["stack"],
        context_quality=context_quality,
        context_files=raw_project["context_files"],
        context_file_count=len(raw_project["context_files"]),
        primary_context_file=raw_project["primary_context_file"],
        project_summary_present=bool(raw_project["project_summary_present"]),
        current_state_present=bool(raw_project["current_state_present"]),
        stack_present=bool(raw_project["stack_present"]),
        run_instructions_present=bool(raw_project["run_instructions_present"]),
        known_risks_present=bool(raw_project["known_risks_present"]),
        next_recommended_move_present=bool(
            raw_project["next_recommended_move_present"]
        ),
        last_meaningful_activity_at=last_activity,
        activity_status=activity_status,
        archived=archived,
        attention_state=attention_state,
        path_override=path_entry.get("path_override", ""),
        path_confidence=path_entry.get("path_confidence", "legacy"),
        path_rationale=path_entry.get("path_rationale", ""),
        has_tests=derived_has_tests,
        has_ci=derived_has_ci,
        has_license=derived_has_license,
        readme_char_count=derived_readme_char_count,
        release_count=derived_release_count,
    )
    advisory = AdvisoryFields(
        notion_portfolio_call=notion.get("portfolio_call", ""),
        notion_momentum=notion.get("momentum", ""),
        notion_current_state=notion.get("current_state", ""),
        legacy_status=legacy.get("status", ""),
        legacy_context_quality=legacy.get("context_quality", ""),
        legacy_category=legacy.get("category", ""),
        legacy_tool_provenance=legacy.get("tool", ""),
    )
    risk = RiskFields(
        risk_tier=risk_entry["risk_tier"],
        risk_factors=risk_entry["risk_factors"],
        risk_summary=risk_entry["risk_summary"],
        doctor_gap=risk_entry["doctor_gap"],
        context_risk=risk_entry["context_risk"],
        path_risk=risk_entry["path_risk"],
        security_risk=risk_entry["security_risk"],
    )
    provenance["risk.risk_tier"] = {
        "source": "derived",
        "detail": risk_entry["risk_tier"],
    }
    provenance["risk.doctor_gap"] = {
        "source": "derived",
        "detail": str(risk_entry["doctor_gap"]).lower(),
    }
    return PortfolioTruthProject(
        identity=identity,
        declared=declared,
        derived=derived,
        risk=risk,
        security=security,
        advisory=advisory,
        repository_state=(
            observe_repository_state(project_path, observed_at=now)
            if project_path is not None and has_git
            else {"state": "not_a_repository", "observed_at": now.isoformat()}
        ),
        provenance=provenance,
        warnings=warnings,
    )


def _select_declared(
    field: str,
    repo_entry: dict[str, Any],
    group_entry: dict[str, Any],
    provenance: dict[str, dict[str, str]],
) -> str:
    for source_name, source in (
        ("catalog_repo", repo_entry),
        ("catalog_group", group_entry),
    ):
        value = str(source.get(field, "") or "").strip()
        if value:
            provenance[f"declared.{field}"] = {
                "source": source_name,
                "detail": str(
                    source.get("catalog_key") or source.get("group_key") or ""
                ),
            }
            return value
    provenance[f"declared.{field}"] = {"source": "fallback", "detail": ""}
    return ""


def _select_declared_with_default(
    field: str,
    repo_entry: dict[str, Any],
    group_entry: dict[str, Any],
    *,
    default_field: str,
    provenance: dict[str, dict[str, str]],
) -> str:
    value = _select_declared(field, repo_entry, group_entry, provenance)
    if value:
        return value
    default_value = str(repo_entry.get(default_field, "") or "").strip()
    if default_value:
        provenance[f"declared.{field}"] = {
            "source": "catalog_defaults",
            "detail": default_value,
        }
        return default_value
    return value


def _select_with_legacy(
    field: str,
    repo_entry: dict[str, Any],
    group_entry: dict[str, Any],
    legacy: dict[str, str],
    raw_project: dict[str, Any],
    provenance: dict[str, dict[str, str]],
) -> str:
    value = _select_declared(field, repo_entry, group_entry, provenance)
    if value:
        return value
    legacy_value = str(legacy.get(field, "") or "").strip()
    if field == "notes":
        legacy_value = _strip_generated_registry_note_decorations(
            legacy_value, repo_entry=repo_entry, group_entry=group_entry
        )
    if legacy_value:
        provenance[f"declared.{field}"] = {
            "source": "legacy_registry",
            "detail": raw_project["name"],
        }
        return legacy_value
    return ""


_GENERATED_SECURITY_NOTE_RE = re.compile(
    r"^(?:\[security: [^\]]+\]\s*)+", re.IGNORECASE
)
_GENERATED_PATH_NOTE_PREFIXES = (
    "Stable path is ",
    "No stable operating path is declared yet.",
)
_GENERATED_PATH_NOTE_MARKERS = (
    "Declared maturity program and intended disposition point at different paths.",
    "Context quality is still too weak for path guidance to stand on its own.",
    "Treat this repo as investigate until path confidence improves.",
)


def _strip_generated_registry_note_decorations(
    notes: str,
    *,
    repo_entry: dict[str, Any],
    group_entry: dict[str, Any],
) -> str:
    """Keep generated registry markdown idempotent when used as legacy input."""
    value = notes.strip()
    value = _GENERATED_SECURITY_NOTE_RE.sub("", value).strip()

    purpose = str(repo_entry.get("purpose") or group_entry.get("purpose") or "").strip()
    if purpose:
        while value == purpose or value.startswith(f"{purpose} "):
            value = value[len(purpose) :].strip()

    if value.startswith(_GENERATED_PATH_NOTE_PREFIXES) or any(
        marker in value for marker in _GENERATED_PATH_NOTE_MARKERS
    ):
        return ""
    return value


def _select_tool_provenance(
    repo_entry: dict[str, Any],
    group_entry: dict[str, Any],
    legacy: dict[str, str],
    raw_project: dict[str, Any],
    provenance: dict[str, dict[str, str]],
) -> str:
    for source_name, value in (
        ("catalog_repo", repo_entry.get("tool_provenance")),
        ("catalog_group", group_entry.get("tool_provenance")),
        ("inference", raw_project.get("inferred_tool_provenance")),
        ("legacy_registry", legacy.get("tool")),
    ):
        normalized = str(value or "").strip().lower()
        if normalized:
            provenance["declared.tool_provenance"] = {
                "source": source_name,
                "detail": normalized,
            }
            return normalized
    provenance["declared.tool_provenance"] = {"source": "fallback", "detail": "unknown"}
    return "unknown"


def _resolve_group_key(
    relative_path: str, group_entry: dict[str, Any], raw_project: dict[str, Any]
) -> str:
    if group_entry.get("group_key"):
        return str(group_entry["group_key"])
    if "Swift" in raw_project.get("stack", []):
        return "ios-projects"
    return "standalone"


def _resolve_group_label(
    group_entry: dict[str, Any], raw_project: dict[str, Any]
) -> str:
    if group_entry.get("section_label"):
        return str(group_entry["section_label"])
    if "Swift" in raw_project.get("stack", []):
        return "iOS Projects"
    return "Root Level"


def _resolve_section_marker(
    relative_path: str, group_entry: dict[str, Any], raw_project: dict[str, Any]
) -> str:
    if group_entry.get("section_marker"):
        return str(group_entry["section_marker"])
    if "Swift" in raw_project.get("stack", []):
        return "iOS Projects"
    return "Standalone Projects"


def _resolve_section_label(
    group_entry: dict[str, Any], raw_project: dict[str, Any]
) -> str:
    if group_entry.get("section_label"):
        return str(group_entry["section_label"])
    if "Swift" in raw_project.get("stack", []):
        return "iOS Projects"
    return "Root Level"


def _activity_status_for(last_activity: datetime | None, *, now: datetime) -> str:
    """Pure recency observation. Lifecycle intent (archived) is a separate axis,
    computed by the caller and passed to downstream consumers as its own boolean —
    see the `archived` local in `_build_truth_project`."""
    if last_activity is None:
        return "stale"
    delta_days = (now - last_activity).days
    if delta_days <= 14:
        return "active"
    if delta_days <= 30:
        return "recent"
    return "stale"


def _attention_state_for(
    *,
    activity_status: str,
    archived: bool,
    lifecycle_state: str,
    operating_path: str,
    category: str,
    path_override: str,
    risk_entry: dict[str, Any],
) -> str:
    if archived or operating_path == "archive":
        return "archived"
    if operating_path == "experiment" or lifecycle_state == "experimental":
        return "experiment"
    if lifecycle_state == "manual-only":
        return "manual-only"
    if activity_status == "stale":
        # A declared finish path is itself an unresolved operator decision. It can
        # remain valid while the default branch is stale (for example, when work is
        # on a release branch or waiting at a human/publication gate), so do not
        # silently collapse it back into the parked pool.
        return "decision-needed" if operating_path == "finish" else "parked"
    if risk_entry.get("security_risk"):
        return "decision-needed"
    if activity_status in {"active", "recent"} and operating_path in {
        "maintain",
        "finish",
    }:
        if category == "infrastructure":
            return "active-infra"
        if category == "commercial":
            return "active-product"
        return "manual-only"
    if activity_status in {"active", "recent"}:
        return "manual-only"
    return "parked"
