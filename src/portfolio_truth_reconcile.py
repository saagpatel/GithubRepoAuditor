from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.github_security_coverage import (
    DEFAULT_ATTENTION_STATES,
    SecurityCoverageError,
    derive_default_attention_cohort,
)
from src.portfolio_catalog import (
    catalog_entry_for_repo,
    group_entry_for_path,
    load_portfolio_catalog,
)
from src.portfolio_context_contract import has_substantive_readme_support
from src.portfolio_pathing import build_operating_path_entry
from src.portfolio_repository_state import observe_repository_state
from src.portfolio_truth_coverage import build_coverage_envelope
from src.portfolio_truth_decisions import build_project_decision
from src.portfolio_truth_metadata import (
    build_exclusions,
    build_input_envelope,
    build_source_summary,
    build_warnings,
)
from src.portfolio_truth_precedence import build_precedence_matrix
from src.portfolio_truth_sources import (
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
from src.project_registry import DEFAULT_SUPPLEMENTARY
from src.registry_parser import _normalize

logger = logging.getLogger(__name__)

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


def _validate_security_receipt_cohort_identity(
    *,
    projects: list[PortfolioTruthProject],
    security_alerts_by_name: dict[str, dict],
    candidate_projects: list[PortfolioTruthProject] | None = None,
    prior_security_alerts_by_name: dict[str, dict] | None = None,
) -> None:
    """Bind receipt membership to attention derived before the new receipt."""
    if candidate_projects is None:
        candidate_projects = projects
    prior_security_alerts_by_name = prior_security_alerts_by_name or {}
    receipt_repositories = tuple(sorted(security_alerts_by_name, key=str.lower))
    try:
        candidate_repositories = derive_default_attention_cohort(
            {
                "projects": [
                    {
                        "identity": {
                            "project_key": project.identity.project_key,
                            "repo_full_name": project.identity.repo_full_name,
                        },
                        "derived": {
                            "attention_state": project.derived.attention_state,
                        },
                    }
                    for project in candidate_projects
                ]
            },
            expected_count=len(receipt_repositories),
        )
    except SecurityCoverageError as exc:
        raise ValueError(
            "PortfolioTruth GitHub security receipt cohort cannot match freshly "
            f"derived default attention: {exc}."
        ) from exc

    receipt_only = sorted(
        set(receipt_repositories) - set(candidate_repositories),
        key=str.lower,
    )
    derived_only = sorted(
        set(candidate_repositories) - set(receipt_repositories),
        key=str.lower,
    )
    if receipt_only or derived_only:
        raise ValueError(
            "PortfolioTruth GitHub security receipt cohort differs from freshly "
            "derived pre-security default attention: "
            f"receipt_only={receipt_only}; derived_only={derived_only}."
        )

    final_repositories = _derive_project_security_cohort(projects)
    final_only = sorted(
        set(final_repositories) - set(receipt_repositories),
        key=str.lower,
    )
    if final_only:
        raise ValueError(
            "PortfolioTruth post-receipt attention contains repositories outside "
            f"the collected security cohort: {final_only}."
        )

    departed = sorted(
        set(receipt_repositories) - set(final_repositories),
        key=str.lower,
    )

    def final_project_is_archived(repository: str) -> bool:
        matches = [
            project
            for project in projects
            if project.identity.repo_full_name == repository
        ]
        return len(matches) == 1 and matches[0].derived.archived is True

    unresolved_departures = [
        repository
        for repository in departed
        if not _is_verified_security_cohort_departure(
            prior_security_alerts_by_name.get(repository),
            security_alerts_by_name.get(repository),
            final_project_archived=final_project_is_archived(repository),
        )
    ]
    if unresolved_departures:
        raise ValueError(
            "PortfolioTruth receipt members left default attention without fresh "
            "observed Dependabot resolution or repository archive evidence: "
            f"{unresolved_departures}."
        )


def _derive_project_security_cohort(
    projects: list[PortfolioTruthProject],
) -> tuple[str, ...]:
    expected_count = sum(
        project.derived.attention_state in DEFAULT_ATTENTION_STATES
        and not project.identity.project_key.startswith("supp:")
        for project in projects
    )
    try:
        return derive_default_attention_cohort(
            {
                "projects": [
                    {
                        "identity": {
                            "project_key": project.identity.project_key,
                            "repo_full_name": project.identity.repo_full_name,
                        },
                        "derived": {
                            "attention_state": project.derived.attention_state,
                        },
                    }
                    for project in projects
                ]
            },
            expected_count=expected_count,
        )
    except SecurityCoverageError as exc:
        raise ValueError(
            f"PortfolioTruth post-receipt security cohort is invalid: {exc}."
        ) from exc


def _is_verified_security_cohort_departure(
    prior_entry: dict[str, Any] | None,
    current_entry: dict[str, Any] | None,
    *,
    final_project_archived: bool,
) -> bool:
    prior = dict(prior_entry or {})
    current = dict(current_entry or {})
    prior_dependabot = dict((prior.get("providers") or {}).get("dependabot") or {})
    current_dependabot = dict((current.get("providers") or {}).get("dependabot") or {})
    current_repository = dict(current.get("repository") or {})
    prior_counts = dict(prior_dependabot.get("counts") or {})
    current_counts = dict(current_dependabot.get("counts") or {})
    observed_resolution = (
        prior_dependabot.get("state") == "observed"
        and sum(
            value
            for value in (
                prior_counts.get("high"),
                prior_counts.get("critical"),
            )
            if isinstance(value, int) and not isinstance(value, bool)
        )
        > 0
        and current.get("receipt_state") == "fresh"
        and current_dependabot.get("state") == "observed"
        and current_counts.get("high") == 0
        and current_counts.get("critical") == 0
    )
    observed_archive = (
        final_project_archived
        and current.get("receipt_state") == "fresh"
        and current_repository.get("state") == "observed"
        and current_repository.get("archived") is True
    )
    return observed_resolution or observed_archive


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
    prior_security_alerts_by_name: dict[str, dict] | None = None,
    repo_status_by_name: dict[str, dict] | None = None,
    producer: dict[str, Any] | None = None,
    prior_notion_generated_at: str | None = None,
) -> PortfolioTruthBuildResult:
    now = now or datetime.now(timezone.utc)
    catalog_data = load_portfolio_catalog(catalog_path)
    legacy_rows = load_legacy_registry_rows(legacy_registry_path)
    notion_context = load_safe_notion_project_context() if include_notion else {}
    notion_source_mode = str(
        getattr(notion_context, "source_mode", "live") or "live"
    )
    notion_observed_at = getattr(notion_context, "observed_at", None)
    notion_context_carried_forward = False
    if include_notion and not notion_context and notion_context_fallback:
        # Live Notion was unavailable; carry forward the prior published context so
        # a headless refresh updates risk/activity signals without dropping advisory
        # data to zero. The caller opts in via publish_portfolio_truth(allow_empty_notion=True).
        notion_context = notion_context_fallback
        notion_source_mode = "carried-forward"
        notion_observed_at = prior_notion_generated_at
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
    workspace_projects = _merge_supplementary_discoveries(
        discovered=workspace_projects,
        supplementary=_cataloged_supplementary_projects(
            catalog_data=catalog_data,
            now=now,
        ),
    )

    def materialize_projects(
        security_lookup: dict[str, dict] | None,
        *,
        repo_status_lookup: dict[str, dict] | None,
    ) -> list[PortfolioTruthProject]:
        return [
            _build_truth_project(
                raw_project,
                catalog_data=catalog_data,
                legacy_rows=legacy_rows,
                notion_context=notion_context,
                now=now,
                release_count_by_name=release_count_by_name,
                security_alerts_by_name=security_lookup,
                repo_status_by_name=repo_status_lookup,
            )
            for raw_project in workspace_projects
        ]

    prior_security_alerts = prior_security_alerts_by_name or {}
    candidate_repo_status_by_name = {
        name: status
        for name, status in (repo_status_by_name or {}).items()
        if status.get("source") == "github_api" and status.get("archived") is False
    }
    candidate_projects = (
        materialize_projects(
            prior_security_alerts,
            # Current status may only expand candidate membership. A fresh GitHub
            # unarchive therefore forces receipt coverage, while archive status is
            # applied only to the final projects and must be corroborated by the
            # receipt before it can authorize a departure.
            repo_status_lookup=candidate_repo_status_by_name,
        )
        if security_coverage_metadata is not None
        and security_alerts_by_name is not None
        else None
    )
    projects = materialize_projects(
        security_alerts_by_name,
        repo_status_lookup=repo_status_by_name,
    )
    if security_coverage_metadata is not None and security_alerts_by_name is not None:
        _validate_security_receipt_cohort_identity(
            projects=projects,
            candidate_projects=candidate_projects,
            security_alerts_by_name=security_alerts_by_name,
            prior_security_alerts_by_name=prior_security_alerts,
        )
    projects.sort(
        key=lambda item: (
            item.identity.section_marker.lower(),
            item.identity.display_name.lower(),
        )
    )

    source_summary = build_source_summary(
        workspace_root=workspace_root.as_posix(),
        projects=projects,
        catalog_errors=list(catalog_data.get("errors") or []),
        catalog_warnings=list(catalog_data.get("warnings") or []),
        legacy_registry_rows=len(legacy_rows),
        notion_context_rows=len(notion_context),
        notion_context_carried_forward=notion_context_carried_forward,
    )
    warnings = build_warnings(
        catalog_errors=source_summary["catalog_errors"],
        catalog_warnings=source_summary["catalog_warnings"],
        unresolved_duplicates=source_summary["unresolved_duplicate_display_names"],
    )

    snapshot = PortfolioTruthSnapshot(
        schema_version=SCHEMA_VERSION,
        generated_at=now,
        workspace_root=workspace_root.as_posix(),
        source_summary=source_summary,
        precedence_matrix=build_precedence_matrix(),
        warnings=warnings,
        projects=projects,
        derivation_policy_version=DERIVATION_POLICY_VERSION,
        producer=producer or {},
        inputs=build_input_envelope(
            workspace_root=workspace_root.as_posix(),
            catalog_path=catalog_data.get("path"),
            now=now,
            include_notion=include_notion,
            notion_context_rows=len(notion_context),
            notion_context_carried_forward=notion_context_carried_forward,
            prior_notion_generated_at=prior_notion_generated_at,
            notion_source_mode=notion_source_mode,
            notion_observed_at=notion_observed_at,
            security_coverage_metadata=security_coverage_metadata,
        ),
        coverage=build_coverage_envelope(
            projects=projects,
            notion_context_carried_forward=notion_context_carried_forward,
            notion_context_rows=len(notion_context),
        ),
        exclusions=build_exclusions(exclusion_counts),
    )
    return PortfolioTruthBuildResult(
        snapshot=snapshot, catalog_data=catalog_data, legacy_rows=legacy_rows
    )


def _cataloged_supplementary_projects(
    *, catalog_data: dict[str, Any], now: datetime
) -> list[dict[str, Any]]:
    """Promote explicitly cataloged repo-less Operator OS identities into truth."""

    projects: list[dict[str, Any]] = []
    for supplementary in DEFAULT_SUPPLEMENTARY:
        name = str(supplementary.get("display_name") or "").strip()
        canonical_key = str(supplementary.get("canonical_key") or "").strip()
        if not name or not canonical_key:
            continue
        catalog_entry = catalog_entry_for_repo(
            {"name": name, "full_name": name, "path": canonical_key},
            catalog_data,
        )
        if not catalog_entry.get("has_explicit_entry"):
            continue
        projects.append(
            {
                "name": name,
                "project_path": None,
                "path": canonical_key,
                "top_level_dir": "supplementary",
                "group_entry": {
                    "group_key": str(supplementary.get("group_key") or "operator_infra"),
                    "group_label": str(
                        supplementary.get("group_label") or "Operator Infrastructure"
                    ),
                    "section_marker": str(
                        supplementary.get("section_marker")
                        or "Supplementary Projects"
                    ),
                    "section_label": str(
                        supplementary.get("section_label") or "Operator OS"
                    ),
                },
                "has_git": False,
                "repo_full_name": "",
                "default_branch": "",
                "context_files": [],
                "context_quality": "none",
                "primary_context_file": "AGENTS.md",
                "project_summary_present": False,
                "current_state_present": False,
                "stack_present": False,
                "run_instructions_present": False,
                "known_risks_present": False,
                "next_recommended_move_present": False,
                "missing_context_fields": [],
                "supporting_context_files": [],
                "stack": ["Unknown"],
                "last_meaningful_activity_at": None,
                "inferred_tool_provenance": "",
                "now": now,
                "source": "supplementary-registry",
            }
        )
    return projects


def _merge_supplementary_discoveries(
    *,
    discovered: list[dict[str, Any]],
    supplementary: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep one canonical identity while retaining local checkout observations."""
    supplementary_by_name = {
        _normalize(str(project.get("name") or "")): project
        for project in supplementary
    }
    used: set[str] = set()
    merged: list[dict[str, Any]] = []
    for project in discovered:
        normalized_name = _normalize(str(project.get("name") or ""))
        supplement = supplementary_by_name.get(normalized_name)
        if supplement is None:
            merged.append(project)
            continue
        used.add(normalized_name)
        if str(project.get("repo_full_name") or "").strip():
            merged.append(project)
            continue
        merged.append(
            {
                **project,
                "path": supplement["path"],
                "top_level_dir": supplement["top_level_dir"],
                "group_entry": supplement["group_entry"],
                "source": "workspace+supplementary-registry",
            }
        )
    merged.extend(
        project
        for normalized_name, project in supplementary_by_name.items()
        if normalized_name not in used
    )
    return merged


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
                        if key != "available" and isinstance(value, int) and value >= 0
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
        receipt_schema_version=str(ghas_entry.get("receipt_schema_version") or ""),
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
    supplementary_group = raw_project.get("group_entry")
    if isinstance(supplementary_group, dict):
        group_entry = {**group_entry, **supplementary_group}
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
    raw_source = str(raw_project.get("source") or "workspace")
    provenance["derived.context_quality"] = {
        "source": f"{raw_source}+catalog"
        if context_quality != raw_context_quality
        else raw_source,
        "detail": (
            f"{raw_context_quality}->{context_quality}"
            if context_quality != raw_context_quality
            else raw_context_quality
        ),
    }

    security_entry = _select_security_entry(
        security_alerts_by_name or {},
        raw_project.get("repo_full_name"),
        raw_project["name"],
    )
    remote_repository = (
        dict(security_entry.get("repository") or {})
        if security_entry is not None
        else {}
    )
    status_entry = _select_repo_status_entry(
        repo_status_by_name or {},
        raw_project.get("repo_full_name"),
        raw_project["name"],
    )
    live_status_available = bool(
        status_entry and status_entry.get("source") == "github_api"
    )
    remote_status_available = (
        remote_repository.get("state") in {"observed", "partial"}
        and isinstance(remote_repository.get("archived"), bool)
    )
    if live_status_available:
        github_archived = status_entry.get("archived") is True
        provenance["github.archived"] = {
            "source": "github_api",
            "detail": str(github_archived).lower(),
        }
    elif remote_status_available:
        github_archived = remote_repository["archived"] is True
        provenance["github.archived"] = {
            "source": str(remote_repository.get("source") or "github_security"),
            "detail": str(github_archived).lower(),
        }
    else:
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

    security = _build_security_fields(security_entry)

    # Only Dependabot high/critical counts drive the risk tier today. Code-scanning
    # and secret-scanning counts are captured in SecurityFields for visibility but do
    # not yet feed the active-high-severity-alerts factor (Dependabot-only scope).
    risk_entry, attention_state = build_project_decision(
        display_name=raw_project["name"],
        operating_path=path_entry.get("operating_path", ""),
        path_override=path_entry.get("path_override", ""),
        context_quality=context_quality,
        activity_status=activity_status,
        archived=archived,
        lifecycle_state=declared_values["lifecycle_state"],
        category=declared_values["category"],
        criticality=declared_values["criticality"],
        doctor_standard=declared_values["doctor_standard"],
        known_risks_present=bool(raw_project["known_risks_present"]),
        run_instructions_present=bool(raw_project["run_instructions_present"]),
        security_coverage_state=security.coverage_state,
        security_high_alerts=security.dependabot_high or 0,
        security_critical_alerts=security.dependabot_critical or 0,
    )
    if (
        not security.receipt_schema_version
        and attention_state in DEFAULT_ATTENTION_STATES
        and not identity.project_key.startswith("supp:")
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
        "source": "git" if raw_project["has_git"] and last_activity else raw_source,
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
        "source": raw_source,
        "detail": ", ".join(raw_project["stack"]),
    }
    provenance["derived.context_files"] = {
        "source": raw_source,
        "detail": str(len(raw_project["context_files"])),
    }
    provenance["derived.primary_context_file"] = {
        "source": raw_source,
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
            "source": raw_source,
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
    remote_default_branch = (
        dict(security_entry.get("repository") or {})
        if security_entry is not None
        else None
    )
    repository_state = (
        observe_repository_state(
            project_path,
            observed_at=now,
            remote_default_branch=remote_default_branch,
        )
        if project_path is not None and has_git
        else {
            "state": "not_a_repository",
            "observed_at": now.isoformat(),
            "remote_default_branch": remote_default_branch
            or {
                "state": "unknown",
                "reason_code": "not_requested",
                "reason": (
                    "no independent live remote read was performed by "
                    "portfolio generation"
                ),
            },
        }
    )
    return PortfolioTruthProject(
        identity=identity,
        declared=declared,
        derived=derived,
        risk=risk,
        security=security,
        advisory=advisory,
        repository_state=repository_state,
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
    """Keep generated registry markdown idempotent when used as legacy input.

    ``_note_text`` composes ``[security: ...] <purpose> <notes>`` fresh on every
    run, and project-registry.md is both that render target and (by default,
    when ``--registry`` is omitted) the next run's legacy-notes source. For a
    repo with no declared purpose the accumulated security flags stay glued
    together at the front, so a single regex pass strips all of them. But when
    a purpose is declared, each run interleaves a fresh flag ahead of the
    purpose ahead of whatever notes text came back in, so old corruption reads
    as ``[secN] purpose [secN-1] purpose ...``, and a single strip pass only
    peels the outermost layer, leaving the rest to compound on the next run.
    Loop the strip to a fixed point so one call collapses any amount of
    accumulated history, not just the newest layer.
    """
    value = notes.strip()
    purpose = str(repo_entry.get("purpose") or group_entry.get("purpose") or "").strip()

    while True:
        next_value = _GENERATED_SECURITY_NOTE_RE.sub("", value).strip()
        if purpose and (next_value == purpose or next_value.startswith(f"{purpose} ")):
            next_value = next_value[len(purpose) :].strip()
        if next_value == value:
            break
        value = next_value

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
    if group_entry.get("group_label"):
        return str(group_entry["group_label"])
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
