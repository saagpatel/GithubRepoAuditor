from __future__ import annotations

from pathlib import Path
from typing import Any

from src.report_enrichment import (
    build_follow_through_checkpoint_status_label,
    build_follow_through_reacquisition_confidence_retirement_status_label,
    build_follow_through_reacquisition_revalidation_recovery_status_label,
    build_follow_through_status_label,
    build_operator_focus,
)

DEFAULT_GITHUB_PROJECTS_CONFIG_PATH = Path("config") / "github-projects.yaml"
VALID_INTERNAL_FIELD_KEYS = {
    "campaign",
    "priority",
    "lane",
    "owner",
    "operator_focus",
    "confidence",
    "revalidation",
    "follow_through",
    "checkpoint_timing",
    "repo",
}


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_field_mapping(value: Any, errors: list[str]) -> dict[str, str]:
    if not isinstance(value, dict):
        if value:
            errors.append("GitHub Projects fields must be a mapping from internal keys to project field names.")
        return {}

    normalized: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        key = _safe_text(raw_key)
        field_name = _safe_text(raw_value)
        if not key:
            continue
        if key not in VALID_INTERNAL_FIELD_KEYS:
            errors.append(
                "GitHub Projects fields contains an unsupported key "
                f"'{key}'. Allowed keys: {', '.join(sorted(VALID_INTERNAL_FIELD_KEYS))}."
            )
            continue
        if not field_name:
            errors.append(f"GitHub Projects field '{key}' must map to a non-empty project field name.")
            continue
        normalized[key] = field_name
    return normalized


def load_github_projects_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or DEFAULT_GITHUB_PROJECTS_CONFIG_PATH
    if not config_path.is_file():
        return {
            "path": str(config_path),
            "exists": False,
            "errors": [],
            "warnings": [],
            "owner": "",
            "project_number": 0,
            "fields": {},
        }

    try:
        import yaml
    except ImportError:
        return {
            "path": str(config_path),
            "exists": True,
            "errors": [],
            "warnings": ["PyYAML is not installed, so the GitHub Projects config was skipped."],
            "owner": "",
            "project_number": 0,
            "fields": {},
        }

    try:
        loaded = yaml.safe_load(config_path.read_text()) or {}
    except yaml.YAMLError as exc:
        return {
            "path": str(config_path),
            "exists": True,
            "errors": [f"Failed to parse GitHub Projects config: {exc}"],
            "warnings": [],
            "owner": "",
            "project_number": 0,
            "fields": {},
        }

    if not isinstance(loaded, dict):
        return {
            "path": str(config_path),
            "exists": True,
            "errors": ["GitHub Projects config root must be a mapping."],
            "warnings": [],
            "owner": "",
            "project_number": 0,
            "fields": {},
        }

    errors: list[str] = []
    owner = _safe_text(loaded.get("owner"))
    if not owner:
        errors.append("GitHub Projects config requires 'owner'.")

    raw_project_number = loaded.get("project_number")
    project_number = 0
    if isinstance(raw_project_number, int) and raw_project_number > 0:
        project_number = raw_project_number
    else:
        errors.append("GitHub Projects config requires a positive integer 'project_number'.")

    fields = _normalize_field_mapping(loaded.get("fields") or {}, errors)
    if not fields:
        errors.append("GitHub Projects config requires at least one field mapping.")

    return {
        "path": str(config_path),
        "exists": True,
        "errors": errors,
        "warnings": [],
        "owner": owner,
        "project_number": project_number,
        "fields": fields,
    }


def is_github_projects_config_valid(config: dict[str, Any] | None) -> bool:
    if not isinstance(config, dict):
        return False
    return bool(config.get("exists") and not config.get("errors") and config.get("owner") and config.get("project_number") and config.get("fields"))


def operator_context_by_repo(operator_queue: list[dict] | None) -> dict[str, dict]:
    context: dict[str, dict] = {}
    for item in operator_queue or []:
        repo_full_name = _safe_text(item.get("repo_full_name")) or _safe_text(item.get("repo"))
        if repo_full_name and repo_full_name not in context:
            context[repo_full_name] = item
    return context


def _status_or_blank(status: str) -> str:
    normalized = _safe_text(status)
    return "" if normalized.lower() in {"", "none"} else normalized


def build_project_field_values(
    repo_actions: list[dict],
    campaign_summary: dict[str, Any],
    operator_item: dict[str, Any] | None = None,
) -> dict[str, str]:
    sample = repo_actions[0]
    catalog = dict(sample.get("portfolio_catalog") or {})
    highest_priority = next(
        (priority for priority in ("critical", "high", "medium", "low") if any(action.get("priority") == priority for action in repo_actions)),
        "",
    )
    item = operator_item or {}
    revalidation = ""
    checkpoint_timing = ""
    follow_through = ""
    operator_focus = ""
    if operator_item:
        revalidation = _status_or_blank(
            build_follow_through_reacquisition_revalidation_recovery_status_label(item)
        ) or _status_or_blank(
            build_follow_through_reacquisition_confidence_retirement_status_label(item)
        )
        checkpoint_timing = _status_or_blank(build_follow_through_checkpoint_status_label(item))
        follow_through = _status_or_blank(build_follow_through_status_label(item))
        operator_focus = _status_or_blank(build_operator_focus(item))
    return {
        "campaign": _safe_text(campaign_summary.get("label") or campaign_summary.get("campaign_type")),
        "priority": highest_priority,
        "lane": _safe_text(item.get("lane")),
        "owner": _safe_text(catalog.get("team")) or _safe_text(catalog.get("owner")),
        "operator_focus": operator_focus,
        "confidence": _safe_text(item.get("confidence_label")) or _safe_text(item.get("next_action_confidence_label")),
        "revalidation": revalidation,
        "follow_through": follow_through,
        "checkpoint_timing": checkpoint_timing,
        "repo": _safe_text(sample.get("repo_full_name")),
    }


def build_project_preview_summary(
    config: dict[str, Any] | None,
    campaign_summary: dict[str, Any],
    grouped_actions: dict[str, list[dict]],
    operator_context: dict[str, dict] | None = None,
) -> dict[str, Any]:
    enabled = bool(config)
    if not enabled:
        return {
            "enabled": False,
            "status": "disabled",
            "summary": "GitHub Projects mirror is not enabled for this run.",
            "repos": [],
            "project_owner": "",
            "project_number": 0,
            "field_count": 0,
            "item_count": 0,
            "errors": [],
            "warnings": [],
        }

    project_owner = _safe_text(config.get("owner"))
    project_number = int(config.get("project_number") or 0)
    errors = list(config.get("errors") or [])
    warnings = list(config.get("warnings") or [])
    if not is_github_projects_config_valid(config):
        return {
            "enabled": True,
            "status": "skipped",
            "summary": "GitHub Projects mirror was requested, but the config is missing or invalid so no project items will be synced.",
            "repos": [],
            "project_owner": project_owner,
            "project_number": project_number,
            "field_count": len(config.get("fields") or {}),
            "item_count": 0,
            "errors": errors,
            "warnings": warnings,
        }

    repo_rows = []
    context = operator_context or {}
    for repo_full_name, repo_actions in grouped_actions.items():
        desired_values = build_project_field_values(
            repo_actions,
            campaign_summary,
            operator_item=context.get(repo_full_name),
        )
        mapped_fields = {
            field_name: desired_values.get(key, "")
            for key, field_name in (config.get("fields") or {}).items()
        }
        repo_rows.append(
            {
                "repo_full_name": repo_full_name,
                "repo": repo_actions[0].get("repo", ""),
                "issue_title": repo_actions[0].get("managed_issue_title", ""),
                "field_count": sum(1 for value in mapped_fields.values() if value),
                "fields": mapped_fields,
            }
        )

    return {
        "enabled": True,
        "status": "configured",
        "summary": (
            f"GitHub Projects mirror is configured for {project_owner} project #{project_number} "
            f"with {len(repo_rows)} planned item(s)."
        ),
        "repos": repo_rows,
        "project_owner": project_owner,
        "project_number": project_number,
        "field_count": len(config.get("fields") or {}),
        "item_count": len(repo_rows),
        "errors": errors,
        "warnings": warnings,
    }
