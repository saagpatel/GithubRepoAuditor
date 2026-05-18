from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime, timezone

from src.analyst_views import build_analyst_context
from src.github_projects import (
    build_project_field_values,
    build_project_preview_summary,
    is_github_projects_config_valid,
)

MANAGED_TOPIC_PREFIX = "ghra-"
MANAGED_ISSUE_MARKER = "ghra-action-bundle"

CAMPAIGN_DEFINITIONS: dict[str, dict[str, str]] = {
    "security-review": {
        "label": "Security Review",
        "description": "Security posture actions that should be reviewed and tracked now.",
        "primary_lens": "security_posture",
    },
    "promotion-push": {
        "label": "Promotion Push",
        "description": "Actions aimed at moving repos toward the next higher tier.",
        "primary_lens": "ship_readiness",
    },
    "archive-sweep": {
        "label": "Archive Sweep",
        "description": "Low-value repos that should be reviewed for archival or retirement.",
        "primary_lens": "maintenance_risk",
    },
    "showcase-publish": {
        "label": "Showcase Publish",
        "description": "Repos worth polishing and publishing more aggressively.",
        "primary_lens": "showcase_value",
    },
    "maintenance-cleanup": {
        "label": "Maintenance Cleanup",
        "description": "Hotspot-driven cleanup actions for fragile or high-churn repos.",
        "primary_lens": "maintenance_risk",
    },
}

PRIORITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def _slug(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "unknown"


def _stable_action_id(repo_full_name: str, campaign_type: str, action_key: str) -> str:
    raw = f"{repo_full_name}|{campaign_type}|{action_key}".encode("utf-8")
    digest = hashlib.sha1(raw).hexdigest()[:12]
    return f"{_slug(campaign_type)}-{digest}"


def _build_audit_maps(report_data: dict) -> tuple[dict[str, dict], dict[str, list[str]], dict[str, float]]:
    analyst_context = build_analyst_context(
        report_data,
        profile_name=report_data.get("selected_portfolio_profile", "default"),
        collection_name=report_data.get("selected_collection"),
    )
    audit_by_name = {
        audit["metadata"]["name"]: audit
        for audit in report_data.get("audits", [])
    }
    collections_by_name = {
        entry["name"]: entry["collections"]
        for entry in analyst_context.get("ranked_audits", [])
    }
    profile_score_by_name = {
        entry["name"]: entry["profile_score"]
        for entry in analyst_context.get("ranked_audits", [])
    }
    return audit_by_name, collections_by_name, profile_score_by_name


def _selected_repo_names(report_data: dict, collection_name: str | None) -> set[str] | None:
    if not collection_name:
        return None
    collection = report_data.get("collections", {}).get(collection_name, {})
    names = {
        repo_data["name"] if isinstance(repo_data, dict) else str(repo_data)
        for repo_data in collection.get("repos", [])
    }
    return names


def _priority_sort_key(action: dict) -> tuple[int, float, float]:
    return (
        PRIORITY_RANK.get(action.get("priority", "medium"), 0),
        action.get("expected_lift", 0.0),
        action.get("profile_score", 0.0),
    )


def _make_base_action(
    *,
    audit: dict,
    campaign_type: str,
    action_key: str,
    title: str,
    body: str,
    kind: str,
    source: str,
    priority: str,
    effort: str,
    expected_lift: float,
    primary_lens: str,
    collections: list[str],
    profile_score: float,
    metadata: dict | None = None,
) -> dict:
    repo_full_name = audit.get("metadata", {}).get("full_name", audit.get("metadata", {}).get("name", "unknown"))
    repo_name = audit.get("metadata", {}).get("name", repo_full_name)
    return {
        "action_id": _stable_action_id(repo_full_name, campaign_type, action_key),
        "action_key": action_key,
        "campaign_type": campaign_type,
        "repo": repo_name,
        "repo_full_name": repo_full_name,
        "title": title,
        "body": body,
        "kind": kind,
        "source": source,
        "priority": priority,
        "effort": effort,
        "expected_lift": round(expected_lift, 3),
        "primary_lens": primary_lens,
        "collections": collections,
        "profile_score": round(profile_score, 3),
        "state": "preview",
        "portfolio_catalog": dict(audit.get("portfolio_catalog") or {}),
        "metadata": metadata or {},
    }


def _build_security_actions(
    report_data: dict,
    audit_by_name: dict[str, dict],
    collections_by_name: dict[str, list[str]],
    profile_score_by_name: dict[str, float],
    selected_names: set[str] | None,
) -> list[dict]:
    actions: list[dict] = []
    for item in report_data.get("security_governance_preview", []):
        repo_name = item.get("repo")
        if not repo_name or repo_name not in audit_by_name:
            continue
        if selected_names is not None and repo_name not in selected_names:
            continue
        audit = audit_by_name[repo_name]
        actions.append(
            _make_base_action(
                audit=audit,
                campaign_type="security-review",
                action_key=item.get("key", _slug(item.get("title", "security-review"))),
                title=item.get("title", "Security review"),
                body=item.get("why", item.get("summary", item.get("title", "Security review"))),
                kind="security-governance",
                source=item.get("source", "merged"),
                priority=item.get("priority", "medium"),
                effort=item.get("effort", "medium"),
                expected_lift=item.get("expected_posture_lift", 0.0),
                primary_lens="security_posture",
                collections=collections_by_name.get(repo_name, []),
                profile_score=profile_score_by_name.get(repo_name, 0.0),
                metadata={"recommendation": item},
            )
        )
    return actions


def _build_backlog_actions(
    report_data: dict,
    audit_by_name: dict[str, dict],
    collections_by_name: dict[str, list[str]],
    profile_score_by_name: dict[str, float],
    selected_names: set[str] | None,
) -> list[dict]:
    actions: list[dict] = []
    for item in report_data.get("action_backlog", []):
        repo_name = item.get("repo")
        if not repo_name or repo_name not in audit_by_name:
            continue
        if selected_names is not None and repo_name not in selected_names:
            continue
        audit = audit_by_name[repo_name]
        actions.append(
            _make_base_action(
                audit=audit,
                campaign_type="promotion-push",
                action_key=item.get("key", _slug(item.get("title", "promotion-push"))),
                title=item.get("title", "Promotion push"),
                body=item.get("rationale", item.get("action", item.get("title", "Promotion push"))),
                kind="promotion",
                source="action_backlog",
                priority="high" if item.get("confidence", 0) >= 0.85 else "medium",
                effort=item.get("effort", "medium"),
                expected_lift=item.get("expected_lens_delta", 0.0),
                primary_lens=item.get("lens", "ship_readiness"),
                collections=collections_by_name.get(repo_name, []),
                profile_score=profile_score_by_name.get(repo_name, 0.0),
                metadata={"action_candidate": item},
            )
        )
    return actions


def _build_archive_actions(
    report_data: dict,
    audit_by_name: dict[str, dict],
    collections_by_name: dict[str, list[str]],
    profile_score_by_name: dict[str, float],
    selected_names: set[str] | None,
) -> list[dict]:
    repos = report_data.get("collections", {}).get("archive-soon", {}).get("repos", [])
    actions: list[dict] = []
    for repo_data in repos:
        repo_name = repo_data["name"] if isinstance(repo_data, dict) else str(repo_data)
        if repo_name not in audit_by_name:
            continue
        if selected_names is not None and repo_name not in selected_names:
            continue
        audit = audit_by_name[repo_name]
        reason = repo_data.get("reason", "Low momentum and low showcase value.") if isinstance(repo_data, dict) else "Low momentum and low showcase value."
        actions.append(
            _make_base_action(
                audit=audit,
                campaign_type="archive-sweep",
                action_key="archive-review",
                title="Review archive candidacy",
                body=reason,
                kind="archive-review",
                source="collection",
                priority="medium",
                effort="small",
                expected_lift=0.1,
                primary_lens="maintenance_risk",
                collections=collections_by_name.get(repo_name, []),
                profile_score=profile_score_by_name.get(repo_name, 0.0),
            )
        )
    return actions


def _build_showcase_actions(
    report_data: dict,
    audit_by_name: dict[str, dict],
    collections_by_name: dict[str, list[str]],
    profile_score_by_name: dict[str, float],
    selected_names: set[str] | None,
) -> list[dict]:
    repos = report_data.get("collections", {}).get("showcase", {}).get("repos", [])
    actions: list[dict] = []
    for repo_data in repos:
        repo_name = repo_data["name"] if isinstance(repo_data, dict) else str(repo_data)
        if repo_name not in audit_by_name:
            continue
        if selected_names is not None and repo_name not in selected_names:
            continue
        audit = audit_by_name[repo_name]
        top_action = next(iter(audit.get("action_candidates", [])), {})
        actions.append(
            _make_base_action(
                audit=audit,
                campaign_type="showcase-publish",
                action_key=top_action.get("key", "showcase-pass"),
                title="Prepare showcase publish pass",
                body=top_action.get("action", "Polish README, screenshots, and public framing for this repo."),
                kind="showcase-publish",
                source="collection",
                priority="high",
                effort=top_action.get("effort", "medium"),
                expected_lift=top_action.get("expected_lens_delta", 0.08),
                primary_lens="showcase_value",
                collections=collections_by_name.get(repo_name, []),
                profile_score=profile_score_by_name.get(repo_name, 0.0),
                metadata={"action_candidate": top_action},
            )
        )
    return actions


def _build_maintenance_actions(
    report_data: dict,
    audit_by_name: dict[str, dict],
    collections_by_name: dict[str, list[str]],
    profile_score_by_name: dict[str, float],
    selected_names: set[str] | None,
) -> list[dict]:
    actions: list[dict] = []
    for hotspot in report_data.get("hotspots", []):
        repo_name = hotspot.get("repo")
        if not repo_name or repo_name not in audit_by_name:
            continue
        if selected_names is not None and repo_name not in selected_names:
            continue
        audit = audit_by_name[repo_name]
        actions.append(
            _make_base_action(
                audit=audit,
                campaign_type="maintenance-cleanup",
                action_key=f"hotspot-{_slug(hotspot.get('category', 'cleanup'))}",
                title=hotspot.get("title", "Maintenance cleanup"),
                body=hotspot.get("recommended_action", hotspot.get("summary", "Address the primary hotspot for this repo.")),
                kind="hotspot-cleanup",
                source="hotspot",
                priority="high" if hotspot.get("severity", 0) >= 0.7 else "medium",
                effort="medium",
                expected_lift=min(0.2, hotspot.get("severity", 0.0) * 0.2),
                primary_lens="maintenance_risk",
                collections=collections_by_name.get(repo_name, []),
                profile_score=profile_score_by_name.get(repo_name, 0.0),
                metadata={"hotspot": hotspot},
            )
        )
    return actions


def _campaign_actions(
    report_data: dict,
    campaign_type: str,
    selected_names: set[str] | None,
) -> list[dict]:
    audit_by_name, collections_by_name, profile_score_by_name = _build_audit_maps(report_data)
    builders = {
        "security-review": _build_security_actions,
        "promotion-push": _build_backlog_actions,
        "archive-sweep": _build_archive_actions,
        "showcase-publish": _build_showcase_actions,
        "maintenance-cleanup": _build_maintenance_actions,
    }
    builder = builders[campaign_type]
    return builder(report_data, audit_by_name, collections_by_name, profile_score_by_name, selected_names)


def build_campaign_bundle(
    report_data: dict,
    *,
    campaign_type: str,
    portfolio_profile: str = "default",
    collection_name: str | None = None,
    max_actions: int = 20,
    writeback_target: str | None = None,
) -> tuple[dict, list[dict]]:
    selected_names = _selected_repo_names(report_data, collection_name)
    report_data = dict(report_data)
    report_data["selected_portfolio_profile"] = portfolio_profile
    report_data["selected_collection"] = collection_name
    actions = _campaign_actions(report_data, campaign_type, selected_names)
    actions = sorted(actions, key=_priority_sort_key, reverse=True)[:max_actions]

    for index, action in enumerate(actions, start=1):
        action["rank"] = index
        action["writeback_targets"] = _preview_targets_for_action(action, writeback_target)
        action["managed_issue_title"] = managed_issue_title(action["campaign_type"])

    definition = CAMPAIGN_DEFINITIONS[campaign_type]
    summary = {
        "campaign_type": campaign_type,
        "label": definition["label"],
        "description": definition["description"],
        "collection_name": collection_name,
        "portfolio_profile": portfolio_profile,
        "action_count": len(actions),
        "repo_count": len({action["repo_full_name"] for action in actions}),
        "preview_only": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "top_actions": [
            {
                "action_id": action["action_id"],
                "repo": action["repo"],
                "title": action["title"],
                "priority": action["priority"],
                "expected_lift": action["expected_lift"],
            }
            for action in actions[:5]
        ],
    }
    return summary, actions


def _next_move_slug(action: dict) -> str:
    return _slug(action.get("action_key") or action.get("title", "next"))


def _preview_targets_for_action(action: dict, writeback_target: str | None) -> dict:
    if not writeback_target:
        return {}
    targets = {}
    if writeback_target in {"github", "all"}:
        targets["github"] = {
            "managed_topics": desired_managed_topics(action),
            "issue_title": managed_issue_title(action["campaign_type"]),
        }
    if writeback_target in {"notion", "all"}:
        targets["notion"] = {
            "status": "Draft",
            "campaign": action["campaign_type"],
        }
    return targets


def desired_managed_topics(action: dict) -> list[str]:
    topics = [
        f"{MANAGED_TOPIC_PREFIX}call-{_slug(action['campaign_type'])}",
        f"{MANAGED_TOPIC_PREFIX}lens-{_slug(action['primary_lens'])}",
        f"{MANAGED_TOPIC_PREFIX}next-{_next_move_slug(action)}",
    ]
    collections = set(action.get("collections", []))
    if "showcase" in collections:
        topics.append(f"{MANAGED_TOPIC_PREFIX}showcase")
    if "archive-soon" in collections:
        topics.append(f"{MANAGED_TOPIC_PREFIX}archive-candidate")
    if action["campaign_type"] == "security-review":
        topics.append(f"{MANAGED_TOPIC_PREFIX}security-high")
    return sorted(set(topics))


def managed_issue_title(campaign_type: str) -> str:
    return f"[Repo Auditor] {CAMPAIGN_DEFINITIONS[campaign_type]['label']}"


def managed_issue_body(repo_name: str, campaign_type: str, actions: list[dict]) -> str:
    lines = [
        f"<!-- {MANAGED_ISSUE_MARKER}:{campaign_type}:{_slug(repo_name)} -->",
        f"# {CAMPAIGN_DEFINITIONS[campaign_type]['label']}",
        "",
        CAMPAIGN_DEFINITIONS[campaign_type]["description"],
        "",
        "## Suggested actions",
    ]
    for action in actions:
        lines.append(f"- [ ] **{action['title']}** ({action['priority']}, effort {action['effort']})")
        lines.append(f"  - {action['body']}")
        lines.append(f"  - Expected lift: {action['expected_lift']:.3f} on {action['primary_lens']}")
    return "\n".join(lines)


def group_actions_by_repo(actions: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for action in actions:
        grouped[action["repo_full_name"]].append(action)
    return dict(grouped)


def build_writeback_preview(
    campaign_summary: dict,
    actions: list[dict],
    *,
    writeback_target: str | None,
    apply: bool,
    previous_state: dict | None = None,
    sync_mode: str = "reconcile",
    github_projects_config: dict | None = None,
    operator_context: dict[str, dict] | None = None,
) -> dict:
    grouped = group_actions_by_repo(actions)
    preview_repos = []
    github_projects_preview = build_project_preview_summary(
        github_projects_config,
        campaign_summary,
        grouped,
        operator_context=operator_context,
    )
    github_projects_rows = {
        item.get("repo_full_name", ""): item
        for item in github_projects_preview.get("repos", [])
    }
    for repo_full_name, repo_actions in grouped.items():
        project_row = github_projects_rows.get(repo_full_name, {})
        preview_repos.append({
            "repo_full_name": repo_full_name,
            "repo": repo_actions[0]["repo"],
            "topics": desired_managed_topics(repo_actions[0]) if writeback_target in {"github", "all"} else [],
            "issue_title": managed_issue_title(repo_actions[0]["campaign_type"]) if writeback_target in {"github", "all"} else None,
            "notion_action_count": len(repo_actions) if writeback_target in {"notion", "all"} else 0,
            "action_ids": [action["action_id"] for action in repo_actions],
            "github_project_field_count": project_row.get("field_count", 0),
            "github_project_fields": project_row.get("fields", {}),
        })
    current_action_ids = {action["action_id"] for action in actions}
    stale_actions = [
        item
        for item in (previous_state or {}).get("actions", {}).values()
        if item.get("action_id") not in current_action_ids
    ]
    return {
        "campaign_type": campaign_summary["campaign_type"],
        "target": writeback_target or "preview-only",
        "mode": "apply" if apply else "preview",
        "sync_mode": sync_mode,
        "action_count": len(actions),
        "repos": preview_repos,
        "stale_action_count": len(stale_actions),
        "stale_repos": sorted({item.get("repo_full_name", "") for item in stale_actions if item.get("repo_full_name")}),
        "github_projects": github_projects_preview,
    }


def _issue_lookup(issues: list[dict], campaign_type: str, repo_name: str) -> dict | None:
    marker = f"{MANAGED_ISSUE_MARKER}:{campaign_type}:{_slug(repo_name)}"
    for issue in issues:
        body = issue.get("body") or ""
        title = issue.get("title") or ""
        if marker in body or title == managed_issue_title(campaign_type):
            return issue
    return None


def _managed_property_values(action: dict) -> dict[str, str]:
    return {
        "portfolio_call": action["campaign_type"],
        "showcase": "true" if "showcase" in action.get("collections", []) else "false",
        "archive_candidate": "true" if "archive-soon" in action.get("collections", []) else "false",
        "security_tier": "high" if action["campaign_type"] == "security-review" else "normal",
        "next_move": _next_move_slug(action),
        "primary_lens": action["primary_lens"],
    }


def _managed_issue_drift(issue: dict | None, expected_title: str, expected_body: str) -> list[str]:
    if not issue:
        return []
    changed = []
    if issue.get("title") != expected_title:
        changed.append("title")
    if (issue.get("body") or "") != expected_body:
        changed.append("body")
    return changed


def _parse_external_key(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _find_issue_by_number(issues: list[dict], number: int | None) -> dict | None:
    if number is None:
        return None
    for issue in issues:
        if issue.get("number") == number:
            return issue
    return None


def _result_for_repo(sample: dict, action_ids: list[str], *, target: str, before: object, after: object, expected: dict | None = None) -> dict:
    return {
        "action_ids": action_ids,
        "action_id": sample["action_id"] if len(action_ids) == 1 else None,
        "repo_full_name": sample["repo_full_name"],
        "target": target,
        "before": before,
        "after": after,
        "expected": expected or {},
    }


def _find_project_item_by_id(items_result: dict, item_id: str | None) -> dict | None:
    if not item_id:
        return None
    item = items_result.get("item")
    if isinstance(item, dict) and item.get("id") == item_id:
        return item
    return None


def _project_item_snapshot(previous_actions: dict[str, dict], repo_full_name: str) -> dict:
    for previous in previous_actions.values():
        if previous.get("repo_full_name") != repo_full_name:
            continue
        snapshot = previous.get("snapshots", {}).get("github-project-item", {})
        if snapshot:
            return snapshot
    return {}


def _project_external_item_id(previous_actions: dict[str, dict], repo_full_name: str) -> str:
    snapshot = _project_item_snapshot(previous_actions, repo_full_name)
    external_key = str(snapshot.get("external_key") or "").strip()
    if external_key and not external_key.startswith("https://"):
        return external_key
    return ""


def _normalize_project_field_type(field: dict) -> str:
    field_type = str(field.get("data_type") or "").strip().lower()
    if field_type in {"single_select", "single-select", "singleselect"}:
        return "single_select"
    return "text"


def _sync_project_fields(
    client,
    *,
    sample: dict,
    action_ids: list[str],
    project: dict,
    item_id: str,
    desired_values: dict[str, str],
    fields_mapping: dict[str, str],
) -> tuple[dict, list[dict]]:
    expected_updates: dict[str, str] = {}
    applied_updates: dict[str, str] = {}
    drift_events: list[dict] = []
    unsupported_fields: list[str] = []
    inaccessible_fields: list[str] = []

    for internal_key, field_name in fields_mapping.items():
        desired_value = str(desired_values.get(internal_key) or "").strip()
        if not desired_value:
            continue
        field = (project.get("fields") or {}).get(field_name)
        if not field:
            inaccessible_fields.append(field_name)
            drift_events.append(
                {
                    "action_id": sample["action_id"],
                    "repo_full_name": sample["repo_full_name"],
                    "campaign_type": sample["campaign_type"],
                    "target": "github-project-fields",
                    "drift_state": "managed-project-field-missing",
                    "field_name": field_name,
                }
            )
            continue
        field_type = _normalize_project_field_type(field)
        if field_type == "single_select":
            option_id = (field.get("options") or {}).get(desired_value)
            if not option_id:
                unsupported_fields.append(field_name)
                drift_events.append(
                    {
                        "action_id": sample["action_id"],
                        "repo_full_name": sample["repo_full_name"],
                        "campaign_type": sample["campaign_type"],
                        "target": "github-project-fields",
                        "drift_state": "managed-project-field-value-unsupported",
                        "field_name": field_name,
                        "expected": desired_value,
                    }
                )
                continue
            update = client.update_project_v2_item_field(
                project_id=project.get("id", ""),
                item_id=item_id,
                field_id=field.get("id", ""),
                field_type=field_type,
                value=option_id,
            )
        else:
            update = client.update_project_v2_item_field(
                project_id=project.get("id", ""),
                item_id=item_id,
                field_id=field.get("id", ""),
                field_type=field_type,
                value=desired_value,
            )
        expected_updates[field_name] = desired_value
        if update.get("ok"):
            applied_updates[field_name] = desired_value

    if inaccessible_fields and not expected_updates:
        status = "skipped"
    elif unsupported_fields and not applied_updates:
        status = "skipped"
    elif applied_updates == expected_updates and expected_updates:
        status = "updated"
    elif expected_updates:
        status = "failed"
    else:
        status = "skipped"

    result = _result_for_repo(
        sample,
        action_ids,
        target="github-project-fields",
        before={},
        after=applied_updates,
        expected=expected_updates,
    )
    result["status"] = status
    result["item_id"] = item_id
    result["details"] = {
        "project_owner": project.get("owner", ""),
        "project_number": project.get("project_number", 0),
        "missing_fields": inaccessible_fields,
        "unsupported_fields": unsupported_fields,
    }
    return result, drift_events


def apply_github_writeback(
    client,
    actions: list[dict],
    *,
    previous_state: dict | None = None,
    sync_mode: str = "reconcile",
    campaign_summary: dict | None = None,
    github_projects_config: dict | None = None,
    operator_context: dict[str, dict] | None = None,
) -> tuple[list[dict], dict[str, dict], list[dict], list[dict]]:
    results: list[dict] = []
    external_refs: dict[str, dict] = {}
    managed_state_drift: list[dict] = []
    closure_events: list[dict] = []
    grouped = group_actions_by_repo(actions)
    previous_actions = (previous_state or {}).get("actions", {})
    current_action_ids = {action["action_id"] for action in actions}
    mirror_projects = is_github_projects_config_valid(github_projects_config)
    operator_context = operator_context or {}
    project = {}
    if mirror_projects:
        project = client.get_project_v2(
            github_projects_config.get("owner", ""),
            int(github_projects_config.get("project_number") or 0),
        )
        project["owner"] = github_projects_config.get("owner", "")
        project["project_number"] = github_projects_config.get("project_number", 0)

    for repo_full_name, repo_actions in grouped.items():
        owner, repo = repo_full_name.split("/", 1)
        sample = repo_actions[0]
        action_ids = [action["action_id"] for action in repo_actions]
        desired_topics = desired_managed_topics(sample)
        current_topics_info = client.get_repo_topics(owner, repo)
        existing_topics = current_topics_info.get("topics", []) if current_topics_info.get("available") else sample.get("metadata", {}).get("topics", [])
        preserved_topics = [topic for topic in existing_topics if not topic.startswith(MANAGED_TOPIC_PREFIX)]
        topic_result = _result_for_repo(
            sample,
            action_ids,
            target="github-topics",
            before=existing_topics,
            after=preserved_topics + desired_topics,
            expected={"managed_topics": desired_topics},
        )
        observed_managed_topics = sorted(topic for topic in existing_topics if topic.startswith(MANAGED_TOPIC_PREFIX))
        if current_topics_info.get("available") and observed_managed_topics != sorted(desired_topics):
            managed_state_drift.append(
                {
                    "action_id": sample["action_id"],
                    "repo_full_name": repo_full_name,
                    "campaign_type": sample["campaign_type"],
                    "target": "github-topics",
                    "drift_state": "managed-topics-drift",
                    "expected": desired_topics,
                    "observed": observed_managed_topics,
                }
            )
        if current_topics_info.get("available"):
            if sorted(existing_topics) == sorted(preserved_topics + desired_topics):
                topic_result["status"] = "unchanged"
            else:
                update = client.replace_repo_topics(owner, repo, preserved_topics + desired_topics)
                topic_result["status"] = "updated" if update.get("ok") else "failed"
                topic_result["after"] = update.get("topics", preserved_topics + desired_topics)
                topic_result["details"] = update
        else:
            topic_result["status"] = "skipped"
            topic_result["reason"] = "topics-unavailable"
        results.append(topic_result)

        property_values = _managed_property_values(sample)
        before_properties = client.get_repo_custom_property_values(owner, repo)
        current_property_values = before_properties.get("values", {})
        observed_managed_properties = {
            key: current_property_values.get(key)
            for key in property_values
        }
        if before_properties.get("available") and observed_managed_properties != property_values:
            managed_state_drift.append(
                {
                    "action_id": sample["action_id"],
                    "repo_full_name": repo_full_name,
                    "campaign_type": sample["campaign_type"],
                    "target": "github-custom-properties",
                    "drift_state": "managed-custom-properties-drift",
                    "expected": property_values,
                    "observed": observed_managed_properties,
                }
            )
        property_result = _result_for_repo(
            sample,
            action_ids,
            target="github-custom-properties",
            before=current_property_values,
            after=property_values,
            expected=property_values,
        )
        if before_properties.get("available") and observed_managed_properties == property_values:
            property_result["status"] = "unchanged"
        else:
            update = client.update_repo_custom_property_values(owner, repo, property_values)
            property_result["status"] = update.get("status", "updated" if update.get("ok") else "failed")
            property_result["before"] = update.get("before", current_property_values)
            property_result["after"] = update.get("after", current_property_values)
            property_result["details"] = update
        results.append(property_result)

        issues = client.list_repo_issues(owner, repo, state="all")
        previous_issue_number = None
        for previous in previous_actions.values():
            if previous.get("repo_full_name") != repo_full_name:
                continue
            snapshot = previous.get("snapshots", {}).get("github-issue", {})
            previous_issue_number = _parse_external_key(snapshot.get("external_key"))
            if previous_issue_number is not None:
                break
        existing_issue = _find_issue_by_number(issues, previous_issue_number) or _issue_lookup(issues, sample["campaign_type"], sample["repo"])
        issue_body = managed_issue_body(sample["repo"], sample["campaign_type"], repo_actions)
        issue_title = managed_issue_title(sample["campaign_type"])
        drift_fields = _managed_issue_drift(existing_issue, issue_title, issue_body)
        if existing_issue is None and any(previous.get("repo_full_name") == repo_full_name for previous in previous_actions.values()):
            managed_state_drift.append(
                {
                    "action_id": sample["action_id"],
                    "repo_full_name": repo_full_name,
                    "campaign_type": sample["campaign_type"],
                    "target": "github-issue",
                    "drift_state": "managed-issue-missing",
                }
            )
        elif drift_fields:
            managed_state_drift.append(
                {
                    "action_id": sample["action_id"],
                    "repo_full_name": repo_full_name,
                    "campaign_type": sample["campaign_type"],
                    "target": "github-issue",
                    "drift_state": "managed-issue-edited",
                    "changed_fields": drift_fields,
                }
            )
        issue_result = _result_for_repo(
            sample,
            action_ids,
            target="github-issue",
            before=existing_issue or {},
            after={"title": issue_title, "body": issue_body, "state": "open"},
            expected={"title": issue_title, "body": issue_body, "state": "open"},
        )
        if existing_issue:
            needs_update = (
                existing_issue.get("title") != issue_title
                or (existing_issue.get("body") or "") != issue_body
                or existing_issue.get("state") != "open"
            )
            if needs_update:
                updated = client.update_issue(
                    owner,
                    repo,
                    existing_issue["number"],
                    {
                        "title": issue_title,
                        "body": issue_body,
                        "state": "open",
                    },
                )
                issue_result["status"] = "reopened" if existing_issue.get("state") == "closed" and updated.get("ok") else ("updated" if updated.get("ok") else "failed")
                issue_result["number"] = existing_issue["number"]
                issue_result["url"] = updated.get("html_url", existing_issue.get("html_url"))
                issue_result["node_id"] = updated.get("node_id") or existing_issue.get("node_id")
                issue_result["details"] = updated
            else:
                issue_result["status"] = "unchanged"
                issue_result["number"] = existing_issue["number"]
                issue_result["url"] = existing_issue.get("html_url")
                issue_result["node_id"] = existing_issue.get("node_id")
        else:
            created = client.create_issue(
                owner,
                repo,
                {
                    "title": issue_title,
                    "body": issue_body,
                },
            )
            issue_result["status"] = "created" if created.get("ok") else "failed"
            issue_result["number"] = created.get("number")
            issue_result["url"] = created.get("html_url")
            issue_result["node_id"] = created.get("node_id")
            issue_result["details"] = created
        results.append(issue_result)
        for action in repo_actions:
            external_refs[action["action_id"]] = {
                "github_issue_url": issue_result.get("url"),
                "github_issue_number": issue_result.get("number"),
                "repo_full_name": repo_full_name,
            }

        if mirror_projects:
            desired_values = build_project_field_values(
                repo_actions,
                campaign_summary or {},
                operator_item=operator_context.get(repo_full_name),
            )
            project_item_result = _result_for_repo(
                sample,
                action_ids,
                target="github-project-item",
                before={},
                after={},
                expected={"project_owner": project.get("owner", ""), "project_number": project.get("project_number", 0)},
            )
            project_fields_result = _result_for_repo(
                sample,
                action_ids,
                target="github-project-fields",
                before={},
                after={},
                expected=desired_values,
            )
            project_fields_result["status"] = "skipped"
            project_fields_result["details"] = {}

            if not project.get("available"):
                project_item_result["status"] = "skipped"
                project_item_result["reason"] = "project-unavailable"
                project_item_result["details"] = {
                    "project_owner": project.get("owner", ""),
                    "project_number": project.get("project_number", 0),
                }
                project_fields_result["reason"] = "project-unavailable"
                project_fields_result["details"] = {
                    "project_owner": project.get("owner", ""),
                    "project_number": project.get("project_number", 0),
                }
                results.append(project_item_result)
                results.append(project_fields_result)
                managed_state_drift.append(
                    {
                        "action_id": sample["action_id"],
                        "repo_full_name": repo_full_name,
                        "campaign_type": sample["campaign_type"],
                        "target": "github-project-item",
                        "drift_state": "managed-project-unavailable",
                    }
                )
            else:
                issue_node_id = (
                    (existing_issue or {}).get("node_id")
                    or issue_result.get("node_id")
                    or (issue_result.get("details") or {}).get("node_id")
                )
                if not issue_node_id:
                    project_item_result["status"] = "skipped"
                    project_item_result["reason"] = "issue-node-id-unavailable"
                    project_fields_result["reason"] = "issue-node-id-unavailable"
                    results.append(project_item_result)
                    results.append(project_fields_result)
                    managed_state_drift.append(
                        {
                            "action_id": sample["action_id"],
                            "repo_full_name": repo_full_name,
                            "campaign_type": sample["campaign_type"],
                            "target": "github-project-item",
                            "drift_state": "managed-project-issue-link-missing",
                        }
                    )
                else:
                    previous_item_id = _project_external_item_id(previous_actions, repo_full_name)
                    existing_item_result = (
                        client.find_project_v2_item_by_id(project.get("id", ""), previous_item_id)
                        if previous_item_id
                        else {"available": True, "item": None}
                    )
                    if not existing_item_result.get("available"):
                        existing_item_result = {"available": True, "item": None}
                    existing_item = existing_item_result.get("item")
                    if existing_item and issue_node_id and existing_item.get("issue_node_id") not in {"", issue_node_id}:
                        managed_state_drift.append(
                            {
                                "action_id": sample["action_id"],
                                "repo_full_name": repo_full_name,
                                "campaign_type": sample["campaign_type"],
                                "target": "github-project-item",
                                "drift_state": "managed-project-item-link-mismatch",
                                "expected": issue_node_id,
                                "observed": existing_item.get("issue_node_id"),
                            }
                        )
                        existing_item = None
                    if not existing_item:
                        issue_lookup = client.find_project_v2_item_by_issue(project.get("id", ""), issue_node_id)
                        existing_item = issue_lookup.get("item") if issue_lookup.get("available") else None

                    project_item_result["before"] = existing_item or {}
                    if existing_item:
                        project_item_result["status"] = "unchanged"
                        project_item_result["item_id"] = existing_item.get("id", "")
                        project_item_result["url"] = project.get("url", "")
                    else:
                        created_item = client.add_issue_to_project_v2(project.get("id", ""), issue_node_id)
                        project_item_result["status"] = created_item.get("status", "created" if created_item.get("ok") else "failed")
                        project_item_result["item_id"] = created_item.get("item_id", "")
                        project_item_result["url"] = project.get("url", "")
                        project_item_result["details"] = created_item
                        existing_item = {"id": created_item.get("item_id", ""), "issue_node_id": issue_node_id}

                    if project_item_result.get("item_id"):
                        for action in repo_actions:
                            external_refs[action["action_id"]]["github_project_item_id"] = project_item_result.get("item_id")
                            external_refs[action["action_id"]]["github_project_url"] = project.get("url", "")

                    if project_item_result["status"] in {"created", "unchanged"} and existing_item.get("id"):
                        project_fields_result, field_drift = _sync_project_fields(
                            client,
                            sample=sample,
                            action_ids=action_ids,
                            project=project,
                            item_id=existing_item.get("id", ""),
                            desired_values=desired_values,
                            fields_mapping=github_projects_config.get("fields", {}),
                        )
                        project_fields_result["url"] = project.get("url", "")
                        managed_state_drift.extend(field_drift)
                    elif project_item_result["status"] == "failed":
                        project_fields_result["status"] = "skipped"
                        project_fields_result["reason"] = "project-item-failed"
                    results.append(project_item_result)
                    results.append(project_fields_result)

    for action_id, previous in previous_actions.items():
        if action_id in current_action_ids:
            continue
        repo_full_name = previous.get("repo_full_name", "")
        if not repo_full_name:
            continue
        event = {
            "action_id": action_id,
            "repo_full_name": repo_full_name,
            "target": "github-issue",
            "before": {},
            "after": {"state": "closed"},
            "expected": {"state": "closed"},
        }
        if sync_mode == "append-only":
            event["status"] = "stale"
            event["reason"] = "append-only"
            results.append(event)
            if mirror_projects:
                project_event = {
                    "action_id": action_id,
                    "repo_full_name": repo_full_name,
                    "target": "github-project-item",
                    "before": {},
                    "after": {},
                    "expected": {"state": "archived"},
                    "status": "stale",
                    "reason": "append-only",
                }
                results.append(project_event)
            closure_events.append(
                {
                    "action_id": action_id,
                    "repo_full_name": repo_full_name,
                    "campaign_type": previous.get("campaign_type", ""),
                    "lifecycle_state": "deferred",
                    "reconciliation_outcome": "stale",
                    "drift_state": "stale",
                    "rollback_state": "rollback-available",
                }
            )
            continue

        owner, repo = repo_full_name.split("/", 1)
        issues = client.list_repo_issues(owner, repo, state="all")
        snapshot = previous.get("snapshots", {}).get("github-issue", {})
        existing_issue = _find_issue_by_number(issues, _parse_external_key(snapshot.get("external_key"))) or _issue_lookup(issues, previous.get("campaign_type", ""), previous.get("details", {}).get("repo", repo))
        if not existing_issue:
            event["status"] = "drifted"
            event["drift_state"] = "managed-issue-missing"
            managed_state_drift.append(
                {
                    "action_id": action_id,
                    "repo_full_name": repo_full_name,
                    "campaign_type": previous.get("campaign_type", ""),
                    "target": "github-issue",
                    "drift_state": "managed-issue-missing",
                }
            )
            results.append(event)
            continue

        event["before"] = existing_issue
        if existing_issue.get("state") == "closed":
            event["status"] = "closed"
            event["number"] = existing_issue.get("number")
            event["url"] = existing_issue.get("html_url")
        else:
            updated = client.update_issue(owner, repo, existing_issue["number"], {"state": "closed"})
            event["status"] = "closed" if updated.get("ok") else "failed"
            event["number"] = existing_issue.get("number")
            event["url"] = updated.get("html_url", existing_issue.get("html_url"))
            event["details"] = updated
        results.append(event)
        closure_events.append(
            {
                "action_id": action_id,
                "repo_full_name": repo_full_name,
                "campaign_type": previous.get("campaign_type", ""),
                "lifecycle_state": "resolved" if event["status"] == "closed" else "failed",
                "reconciliation_outcome": "closed" if event["status"] == "closed" else "failed",
                "closed_at": datetime.now(timezone.utc).isoformat() if event["status"] == "closed" else None,
                "closed_reason": "left-campaign-selection",
                "rollback_state": "rollback-available",
            }
        )

        if mirror_projects and project.get("available"):
            project_item_id = _project_external_item_id(previous_actions, repo_full_name)
            project_item = None
            if project_item_id:
                item_lookup = client.find_project_v2_item_by_id(project.get("id", ""), project_item_id)
                project_item = item_lookup.get("item") if item_lookup.get("available") else None
            project_event = {
                "action_id": action_id,
                "repo_full_name": repo_full_name,
                "target": "github-project-item",
                "before": project_item or {},
                "after": {"state": "archived"},
                "expected": {"state": "archived"},
            }
            if not project_item:
                project_event["status"] = "drifted"
                project_event["drift_state"] = "managed-project-item-missing"
                managed_state_drift.append(
                    {
                        "action_id": action_id,
                        "repo_full_name": repo_full_name,
                        "campaign_type": previous.get("campaign_type", ""),
                        "target": "github-project-item",
                        "drift_state": "managed-project-item-missing",
                    }
                )
            else:
                archived = client.archive_project_v2_item(project_item.get("id", ""))
                project_event["status"] = archived.get("status", "archived" if archived.get("ok") else "failed")
                project_event["item_id"] = project_item.get("id", "")
                project_event["url"] = project.get("url", "")
                project_event["details"] = archived
            results.append(project_event)

    return results, external_refs, managed_state_drift, closure_events


def build_campaign_run(
    campaign_summary: dict,
    actions: list[dict],
    *,
    writeback_target: str | None,
    apply: bool,
    sync_mode: str = "reconcile",
) -> dict:
    return {
        "campaign_type": campaign_summary["campaign_type"],
        "label": campaign_summary["label"],
        "portfolio_profile": campaign_summary.get("portfolio_profile", "default"),
        "collection_name": campaign_summary.get("collection_name"),
        "writeback_target": writeback_target or "preview-only",
        "mode": "apply" if apply else "preview",
        "sync_mode": sync_mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_action_ids": [action["action_id"] for action in actions],
    }


def _results_for_action(results: list[dict], action_id: str, repo_full_name: str) -> list[dict]:
    matched = []
    for result in results:
        if result.get("action_id") == action_id:
            matched.append(result)
            continue
        if action_id in (result.get("action_ids") or []):
            matched.append(result)
            continue
        if result.get("repo_full_name") == repo_full_name and not result.get("action_id") and not result.get("action_ids"):
            matched.append(result)
    return matched


def build_action_runs(
    actions: list[dict],
    results: list[dict],
    target: str | None,
    apply: bool,
    *,
    previous_state: dict | None = None,
    sync_mode: str = "reconcile",
) -> list[dict]:
    previous_actions = (previous_state or {}).get("actions", {})
    current_actions = {action["action_id"]: action for action in actions}
    ordered_ids = list(current_actions) + [action_id for action_id in previous_actions if action_id not in current_actions]

    action_runs = []
    now = datetime.now(timezone.utc).isoformat()
    for action_id in ordered_ids:
        action = current_actions.get(action_id) or previous_actions.get(action_id, {})
        repo_full_name = action.get("repo_full_name", "")
        repo_results = _results_for_action(results, action_id, repo_full_name)
        statuses = [result.get("status") for result in repo_results]
        lifecycle_state = "planned"
        reconciliation_outcome = "preview"
        closed_at = None
        closed_reason = None
        reopened_at = None
        drift_state = next((result.get("drift_state") for result in repo_results if result.get("drift_state")), None)
        rollback_state = "partial" if any(result.get("before") not in ({}, None, []) for result in repo_results) else "non-reversible"

        if not apply:
            lifecycle_state = "planned"
            reconciliation_outcome = "preview"
        elif any(status == "failed" for status in statuses):
            lifecycle_state = "failed"
            reconciliation_outcome = "failed"
        elif action_id not in current_actions:
            if any(status == "closed" for status in statuses):
                lifecycle_state = "resolved"
                reconciliation_outcome = "closed"
                closed_at = now
                closed_reason = "left-campaign-selection"
            elif sync_mode == "append-only" or any(status == "stale" for status in statuses):
                lifecycle_state = "deferred"
                reconciliation_outcome = "stale"
                drift_state = drift_state or "stale"
            elif any(status == "drifted" for status in statuses):
                lifecycle_state = "failed"
                reconciliation_outcome = "drifted"
            else:
                lifecycle_state = "cancelled"
                reconciliation_outcome = "cancelled"
                closed_at = now
                closed_reason = "close-missing"
        elif any(status == "reopened" for status in statuses):
            lifecycle_state = "open"
            reconciliation_outcome = "reopened"
            reopened_at = now
        elif any(status == "created" for status in statuses):
            lifecycle_state = "open"
            reconciliation_outcome = "created"
        elif any(status == "updated" for status in statuses):
            lifecycle_state = "open"
            reconciliation_outcome = "updated"
        elif any(status == "drifted" for status in statuses):
            lifecycle_state = "open"
            reconciliation_outcome = "drifted"
        elif any(status == "unchanged" for status in statuses):
            lifecycle_state = "open"
            reconciliation_outcome = "unchanged"
        elif any(status == "skipped" for status in statuses):
            lifecycle_state = "deferred"
            reconciliation_outcome = "skipped"

        action_runs.append({
            "action_id": action_id,
            "repo_full_name": repo_full_name,
            "campaign_type": action.get("campaign_type", ""),
            "target": target or "preview-only",
            "status": reconciliation_outcome,
            "lifecycle_state": lifecycle_state,
            "reconciliation_outcome": reconciliation_outcome,
            "closed_at": closed_at,
            "closed_reason": closed_reason,
            "reopened_at": reopened_at,
            "supersedes_action_id": None,
            "superseded_by_action_id": None,
            "drift_state": drift_state,
            "rollback_state": rollback_state,
        })
    return action_runs


def summarize_writeback_results(results: list[dict], target: str | None, apply: bool) -> dict:
    counts = defaultdict(int)
    for result in results:
        counts[result.get("status", "unknown")] += 1
    return {
        "target": target or "preview-only",
        "mode": "apply" if apply else "preview",
        "counts": dict(counts),
        "results": results,
    }


def build_rollback_preview(results: list[dict]) -> dict:
    items = []
    reversible_targets = {"github-topics", "github-custom-properties", "github-issue", "notion-action"}
    for result in results:
        target = result.get("target")
        if not target:
            continue
        has_before = result.get("before") not in ({}, None, [])
        rollback_state = "fully-reversible" if target in reversible_targets and has_before else ("partial" if target in reversible_targets else "non-reversible")
        items.append({
            "action_id": result.get("action_id"),
            "repo_full_name": result.get("repo_full_name"),
            "target": target,
            "status": result.get("status"),
            "rollback_state": rollback_state,
        })
    return {
        "available": any(item["rollback_state"] != "non-reversible" for item in items),
        "item_count": len(items),
        "fully_reversible_count": sum(1 for item in items if item["rollback_state"] == "fully-reversible"),
        "partial_count": sum(1 for item in items if item["rollback_state"] == "partial"),
        "items": items,
    }
