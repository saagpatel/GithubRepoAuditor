from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.portfolio_catalog import (
    catalog_entry_for_repo,
    group_entry_for_path,
    load_portfolio_catalog,
)
from src.portfolio_pathing import build_operating_path_entry
from src.portfolio_risk import build_risk_entry
from src.portfolio_truth_sources import (
    discover_workspace_projects,
    load_legacy_registry_rows,
    load_safe_notion_project_context,
)
from src.portfolio_truth_types import (
    SCHEMA_VERSION,
    AdvisoryFields,
    DeclaredFields,
    DerivedFields,
    IdentityFields,
    PortfolioTruthProject,
    PortfolioTruthSnapshot,
    RiskFields,
)
from src.registry_parser import _normalize

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
    "declared.tool_provenance": ["catalog_repo", "catalog_group", "inference", "legacy_registry"],
    "declared.notes": ["catalog_repo", "catalog_group", "legacy_registry"],
    "derived.stack": ["workspace", "legacy_registry"],
    "derived.context_quality": ["workspace"],
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
    "derived.registry_status": ["derived"],
    "derived.path_override": ["normalized"],
    "derived.path_confidence": ["normalized"],
    "derived.path_rationale": ["normalized"],
}


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
    now: datetime | None = None,
) -> PortfolioTruthBuildResult:
    now = now or datetime.now(timezone.utc)
    catalog_data = load_portfolio_catalog(catalog_path)
    legacy_rows = load_legacy_registry_rows(legacy_registry_path)
    notion_context = load_safe_notion_project_context() if include_notion else {}

    workspace_projects = discover_workspace_projects(
        workspace_root,
        catalog_data=catalog_data,
        now=now,
    )
    projects = [
        _build_truth_project(
            raw_project,
            catalog_data=catalog_data,
            legacy_rows=legacy_rows,
            notion_context=notion_context,
            now=now,
        )
        for raw_project in workspace_projects
    ]
    projects.sort(
        key=lambda item: (item.identity.section_marker.lower(), item.identity.display_name.lower())
    )

    source_summary = {
        "workspace_root": workspace_root.as_posix(),
        "project_count": len(projects),
        "catalog_errors": list(catalog_data.get("errors") or []),
        "catalog_warnings": list(catalog_data.get("warnings") or []),
        "legacy_registry_rows": len(legacy_rows),
        "notion_context_rows": len(notion_context),
        "context_quality_counts": dict(
            Counter(project.derived.context_quality for project in projects)
        ),
        "registry_status_counts": dict(
            Counter(project.derived.registry_status for project in projects)
        ),
        "duplicate_display_names": sorted(
            name
            for name, count in Counter(
                project.identity.display_name for project in projects
            ).items()
            if count > 1
        ),
    }
    warnings = list(catalog_data.get("errors") or []) + list(catalog_data.get("warnings") or [])
    duplicate_display_names = source_summary["duplicate_display_names"]
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
    )
    return PortfolioTruthBuildResult(
        snapshot=snapshot, catalog_data=catalog_data, legacy_rows=legacy_rows
    )


def _build_truth_project(
    raw_project: dict[str, Any],
    *,
    catalog_data: dict[str, Any],
    legacy_rows: dict[str, dict[str, str]],
    notion_context: dict[str, dict[str, str]],
    now: datetime,
) -> PortfolioTruthProject:
    relative_path = raw_project["path"]
    group_entry = group_entry_for_path(relative_path, catalog_data)
    repo_entry = catalog_entry_for_repo(
        {
            "name": raw_project["name"],
            "full_name": raw_project.get("repo_full_name") or raw_project["name"],
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
    )

    declared_values = {
        "owner": _select_declared("owner", repo_entry, group_entry, provenance),
        "team": _select_declared("team", repo_entry, group_entry, provenance),
        "purpose": _select_declared("purpose", repo_entry, group_entry, provenance),
        "lifecycle_state": _select_declared("lifecycle_state", repo_entry, group_entry, provenance),
        "criticality": _select_declared("criticality", repo_entry, group_entry, provenance),
        "review_cadence": _select_declared("review_cadence", repo_entry, group_entry, provenance),
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
        "doctor_standard": _select_declared("doctor_standard", repo_entry, group_entry, provenance),
    }

    context_quality = raw_project["context_quality"]
    provenance["derived.context_quality"] = {
        "source": "workspace",
        "detail": raw_project["context_quality"],
    }

    last_activity = raw_project["last_meaningful_activity_at"]
    activity_status = _activity_status_for(
        last_activity, declared_values["lifecycle_state"], now=now
    )
    registry_status = _registry_status_for(activity_status)

    path_entry = build_operating_path_entry(
        {
            **declared_values,
            "has_explicit_entry": bool(
                repo_entry.get("has_explicit_entry") or group_entry.get("has_explicit_entry")
            ),
            "catalog_default_maturity_program": repo_entry.get(
                "catalog_default_maturity_program", ""
            ),
            "catalog_default_target_maturity": repo_entry.get(
                "catalog_default_target_maturity", ""
            ),
        },
        context_quality=context_quality,
        registry_status=registry_status,
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

    risk_entry = build_risk_entry(
        display_name=raw_project["name"],
        operating_path=path_entry.get("operating_path", ""),
        path_override=path_entry.get("path_override", ""),
        path_confidence=path_entry.get("path_confidence", "legacy"),
        context_quality=context_quality,
        activity_status=activity_status,
        registry_status=registry_status,
        criticality=declared_values["criticality"],
        doctor_standard=declared_values["doctor_standard"],
        known_risks_present=bool(raw_project["known_risks_present"]),
        run_instructions_present=bool(raw_project["run_instructions_present"]),
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
    )
    provenance["derived.last_meaningful_activity_at"] = {
        "source": "git" if raw_project["has_git"] and last_activity else "workspace",
        "detail": "derived",
    }
    provenance["derived.activity_status"] = {"source": "derived", "detail": activity_status}
    provenance["derived.registry_status"] = {"source": "derived", "detail": registry_status}
    provenance["derived.stack"] = {"source": "workspace", "detail": ", ".join(raw_project["stack"])}
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

    if legacy and legacy.get("status") and legacy["status"] != registry_status:
        warnings.append(
            f"Legacy registry status '{legacy['status']}' differs from derived registry status '{registry_status}'."
        )
    if not repo_entry.get("has_explicit_entry") and not group_entry.get("has_explicit_entry"):
        warnings.append("No explicit catalog contract is recorded for this project yet.")
    if path_entry.get("path_override") == "investigate":
        warnings.append(
            path_entry.get(
                "path_rationale", "Operating path currently requires investigate override."
            )
        )

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
        next_recommended_move_present=bool(raw_project["next_recommended_move_present"]),
        last_meaningful_activity_at=last_activity,
        activity_status=activity_status,
        registry_status=registry_status,
        path_override=path_entry.get("path_override", ""),
        path_confidence=path_entry.get("path_confidence", "legacy"),
        path_rationale=path_entry.get("path_rationale", ""),
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
    )
    provenance["risk.risk_tier"] = {"source": "derived", "detail": risk_entry["risk_tier"]}
    provenance["risk.doctor_gap"] = {
        "source": "derived",
        "detail": str(risk_entry["doctor_gap"]).lower(),
    }
    return PortfolioTruthProject(
        identity=identity,
        declared=declared,
        derived=derived,
        risk=risk,
        advisory=advisory,
        provenance=provenance,
        warnings=warnings,
    )


def _select_declared(
    field: str,
    repo_entry: dict[str, Any],
    group_entry: dict[str, Any],
    provenance: dict[str, dict[str, str]],
) -> str:
    for source_name, source in (("catalog_repo", repo_entry), ("catalog_group", group_entry)):
        value = str(source.get(field, "") or "").strip()
        if value:
            provenance[f"declared.{field}"] = {
                "source": source_name,
                "detail": str(source.get("catalog_key") or source.get("group_key") or ""),
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
        provenance[f"declared.{field}"] = {"source": "catalog_defaults", "detail": default_value}
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
    if legacy_value:
        provenance[f"declared.{field}"] = {
            "source": "legacy_registry",
            "detail": raw_project["name"],
        }
        return legacy_value
    return ""


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
            provenance["declared.tool_provenance"] = {"source": source_name, "detail": normalized}
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


def _resolve_group_label(group_entry: dict[str, Any], raw_project: dict[str, Any]) -> str:
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


def _resolve_section_label(group_entry: dict[str, Any], raw_project: dict[str, Any]) -> str:
    if group_entry.get("section_label"):
        return str(group_entry["section_label"])
    if "Swift" in raw_project.get("stack", []):
        return "iOS Projects"
    return "Root Level"


def _activity_status_for(
    last_activity: datetime | None,
    lifecycle_state: str,
    *,
    now: datetime,
) -> str:
    if lifecycle_state == "archived":
        return "archived"
    if last_activity is None:
        return "stale"
    delta_days = (now - last_activity).days
    if delta_days <= 14:
        return "active"
    if delta_days <= 30:
        return "recent"
    return "stale"


def _registry_status_for(activity_status: str) -> str:
    if activity_status == "stale":
        return "parked"
    return activity_status
