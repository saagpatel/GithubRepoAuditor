from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from src.analyst_views import build_analyst_context

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
) -> dict:
    grouped = group_actions_by_repo(actions)
    preview_repos = []
    for repo_full_name, repo_actions in grouped.items():
        preview_repos.append({
            "repo_full_name": repo_full_name,
            "repo": repo_actions[0]["repo"],
            "topics": desired_managed_topics(repo_actions[0]) if writeback_target in {"github", "all"} else [],
            "issue_title": managed_issue_title(repo_actions[0]["campaign_type"]) if writeback_target in {"github", "all"} else None,
            "notion_action_count": len(repo_actions) if writeback_target in {"notion", "all"} else 0,
            "action_ids": [action["action_id"] for action in repo_actions],
        })
    return {
        "campaign_type": campaign_summary["campaign_type"],
        "target": writeback_target or "preview-only",
        "mode": "apply" if apply else "preview",
        "action_count": len(actions),
        "repos": preview_repos,
    }


def _issue_lookup(issues: list[dict], campaign_type: str, repo_name: str) -> dict | None:
    marker = f"{MANAGED_ISSUE_MARKER}:{campaign_type}:{_slug(repo_name)}"
    for issue in issues:
        body = issue.get("body") or ""
        title = issue.get("title") or ""
        if marker in body or title == managed_issue_title(campaign_type):
            return issue
    return None


def apply_github_writeback(client, actions: list[dict]) -> tuple[list[dict], dict[str, dict]]:
    results: list[dict] = []
    external_refs: dict[str, dict] = {}
    grouped = group_actions_by_repo(actions)

    for repo_full_name, repo_actions in grouped.items():
        owner, repo = repo_full_name.split("/", 1)
        sample = repo_actions[0]
        desired_topics = desired_managed_topics(sample)
        current_topics_info = client.get_repo_topics(owner, repo)
        existing_topics = current_topics_info.get("topics", []) if current_topics_info.get("available") else sample.get("metadata", {}).get("topics", [])
        preserved_topics = [topic for topic in existing_topics if not topic.startswith(MANAGED_TOPIC_PREFIX)]
        topic_result = {
            "repo_full_name": repo_full_name,
            "target": "github-topics",
            "status": "skipped",
            "before": existing_topics,
            "after": preserved_topics + desired_topics,
        }
        if current_topics_info.get("available"):
            update = client.replace_repo_topics(owner, repo, preserved_topics + desired_topics)
            topic_result["status"] = "updated" if update.get("ok") else "failed"
            topic_result["details"] = update
        results.append(topic_result)

        property_values = {
            "portfolio_call": sample["campaign_type"],
            "showcase": "true" if "showcase" in sample.get("collections", []) else "false",
            "archive_candidate": "true" if "archive-soon" in sample.get("collections", []) else "false",
            "security_tier": "high" if sample["campaign_type"] == "security-review" else "normal",
            "next_move": _next_move_slug(sample),
            "primary_lens": sample["primary_lens"],
        }
        property_result = client.update_repo_custom_property_values(owner, repo, property_values)
        property_result.update({"repo_full_name": repo_full_name, "target": "github-custom-properties"})
        results.append(property_result)

        issues = client.list_repo_issues(owner, repo, state="all")
        existing_issue = _issue_lookup(issues, sample["campaign_type"], sample["repo"])
        issue_body = managed_issue_body(sample["repo"], sample["campaign_type"], repo_actions)
        if existing_issue:
            updated = client.update_issue(
                owner,
                repo,
                existing_issue["number"],
                {
                    "title": managed_issue_title(sample["campaign_type"]),
                    "body": issue_body,
                    "state": "open",
                },
            )
            issue_result = {
                "repo_full_name": repo_full_name,
                "target": "github-issue",
                "status": "updated" if updated.get("ok") else "failed",
                "number": existing_issue["number"],
                "url": updated.get("html_url", existing_issue.get("html_url")),
            }
        else:
            created = client.create_issue(
                owner,
                repo,
                {
                    "title": managed_issue_title(sample["campaign_type"]),
                    "body": issue_body,
                },
            )
            issue_result = {
                "repo_full_name": repo_full_name,
                "target": "github-issue",
                "status": "created" if created.get("ok") else "failed",
                "number": created.get("number"),
                "url": created.get("html_url"),
            }
        results.append(issue_result)
        for action in repo_actions:
            external_refs[action["action_id"]] = {
                "github_issue_url": issue_result.get("url"),
                "repo_full_name": repo_full_name,
            }

    return results, external_refs


def build_campaign_run(
    campaign_summary: dict,
    actions: list[dict],
    *,
    writeback_target: str | None,
    apply: bool,
) -> dict:
    return {
        "campaign_type": campaign_summary["campaign_type"],
        "label": campaign_summary["label"],
        "portfolio_profile": campaign_summary.get("portfolio_profile", "default"),
        "collection_name": campaign_summary.get("collection_name"),
        "writeback_target": writeback_target or "preview-only",
        "mode": "apply" if apply else "preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_action_ids": [action["action_id"] for action in actions],
    }


def build_action_runs(actions: list[dict], results: list[dict], target: str | None, apply: bool) -> list[dict]:
    indexed_results = defaultdict(list)
    for result in results:
        repo_full_name = result.get("repo_full_name")
        if repo_full_name:
            indexed_results[repo_full_name].append(result)

    action_runs = []
    for action in actions:
        repo_results = indexed_results.get(action["repo_full_name"], [])
        status = "preview"
        if apply:
            if repo_results and all(result.get("status") not in {"failed", "skipped"} for result in repo_results):
                status = "applied"
            elif any(result.get("status") == "failed" for result in repo_results):
                status = "failed"
            else:
                status = "skipped"
        action_runs.append({
            "action_id": action["action_id"],
            "repo_full_name": action["repo_full_name"],
            "campaign_type": action["campaign_type"],
            "target": target or "preview-only",
            "status": status,
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
