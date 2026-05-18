"""Notion API sync — pushes audit signal events to Notion databases.

Uses raw requests (no SDK) consistent with the project's minimal dependency philosophy.
Requires NOTION_TOKEN environment variable and config/notion-config.json.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from src.notion_client import (
    DEFAULT_NOTION_VERSION,
    REQUEST_DELAY,
    get_notion_token,
    load_notion_config,
    notion_parent_for_collection,
    notion_request,
    query_notion_collection,
    rich_text_value,
    select_value,
    title_value,
)

# Keep private aliases for backward compat within this module
_notion_request = notion_request
_rich_text_value = rich_text_value
_select_value = select_value
_title_value = title_value
_load_notion_config = load_notion_config
_query_notion_collection = query_notion_collection
_notion_parent_for_collection = notion_parent_for_collection


def _extract_audit_data(event: dict) -> dict:
    """Extract audit fields from a typed event payload, with legacy fallback."""
    machine = event.get("machineData")
    if isinstance(machine, dict):
        return {
            "grade": machine.get("grade", event.get("status", "F")),
            "overall_score": machine.get("overall_score", 0),
            "interest_score": machine.get("interest_score", 0),
            "badges": machine.get("badges", []),
            "date": event.get("occurredAt", ""),
        }

    raw_excerpt = event.get("rawExcerpt", "")
    if isinstance(raw_excerpt, str):
        try:
            raw = json.loads(raw_excerpt)
        except json.JSONDecodeError:
            raw = {}
    else:
        raw = {}

    return {
        "grade": event.get("status", "F"),
        "overall_score": raw.get("overall_score", 0),
        "interest_score": raw.get("interest_score", 0),
        "badges": raw.get("badges", []),
        "date": event.get("occurredAt", ""),
    }


def _query_existing_event_keys(
    events_db_id: str,
    token: str,
    version: str,
) -> set[str]:
    """Query existing audit event keys for deduplication."""
    keys: set[str] = set()
    start_cursor = None

    while True:
        body: dict = {
            "filter": {
                "property": "Event Key",
                "rich_text": {"contains": "audit::report"},
            },
            "page_size": 100,
        }
        if start_cursor:
            body["start_cursor"] = start_cursor

        resp = _notion_request("POST", f"/databases/{events_db_id}/query", token, version, body)
        if not resp or resp.status_code != 200:
            break

        data = resp.json()
        for page in data.get("results", []):
            props = page.get("properties", {})
            ek = props.get("Event Key", {})
            rt = ek.get("rich_text", [])
            if rt:
                keys.add(rt[0].get("text", {}).get("content", ""))

        if not data.get("has_more"):
            break
        start_cursor = data.get("next_cursor")
        time.sleep(REQUEST_DELAY)

    return keys


def _create_event_page(
    event: dict,
    events_db_id: str,
    token: str,
    version: str,
) -> str | None:
    """Create an event page in the External Signal Events database."""
    properties: dict = {
        "Name": _title_value(event["title"]),
        "Provider": _select_value(event["provider"]),
        "Signal Type": _select_value(event["signalType"]),
        "Occurred At": {"date": {"start": event["occurredAt"]}},
        "Status": _rich_text_value(event["status"]),
        "Environment": _select_value(event["environment"]),
        "Severity": _select_value(event["severity"]),
        "Source ID": _rich_text_value(event["sourceIdValue"]),
        "Event Key": _rich_text_value(event["eventKey"]),
        "Summary": _rich_text_value(event["summary"]),
        "Raw Excerpt": _rich_text_value(event["rawExcerpt"]),
    }

    if event.get("sourceUrl"):
        properties["Source URL"] = {"url": event["sourceUrl"]}

    if event.get("localProjectId"):
        properties["Local Project"] = {"relation": [{"id": event["localProjectId"]}]}

    body = {
        "parent": {"database_id": events_db_id},
        "properties": properties,
    }

    resp = _notion_request("POST", "/pages", token, version, body)
    if resp and resp.status_code == 200:
        return resp.json().get("id")
    if resp:
        print(f"  Failed to create event: {resp.status_code} {resp.text[:200]}", file=sys.stderr)
    return None


def _update_project_fields(
    project_id: str,
    audit_data: dict,
    token: str,
    version: str,
) -> bool:
    """Update derived audit fields on a control tower project page."""
    properties = {
        "Audit Grade": _select_value(audit_data.get("grade", "F")),
        "Audit Score": {"number": round(audit_data.get("overall_score", 0), 3)},
        "Audit Interest": {"number": round(audit_data.get("interest_score", 0), 3)},
        "Audit Badge Count": {"number": len(audit_data.get("badges", []))},
        "Audit Date": {"date": {"start": audit_data.get("date", "")}},
    }

    resp = _notion_request("PATCH", f"/pages/{project_id}", token, version, {"properties": properties})
    if resp and resp.status_code == 200:
        return True
    if resp:
        print(f"  Failed to update project {project_id}: {resp.status_code}", file=sys.stderr)
    return False


def sync_notion_events(
    events_path: Path,
    config_dir: Path = Path("config"),
) -> dict:
    """Push audit events to Notion. Returns {created, deduped, updated_projects, errors}."""
    token = get_notion_token()
    if not token:
        print("  NOTION_TOKEN not set. Skipping Notion sync.", file=sys.stderr)
        return {"skipped": True, "reason": "no token"}

    config = _load_notion_config(config_dir)
    if not config:
        return {"skipped": True, "reason": "no config"}

    events_db_id = config.get("events_database_id", "")
    version = config.get("notion_version", DEFAULT_NOTION_VERSION)

    if not events_db_id:
        print("  events_database_id not set in notion-config.json", file=sys.stderr)
        return {"skipped": True, "reason": "no events_database_id"}

    # Load events
    try:
        data = json.loads(events_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  Failed to read events file: {exc}", file=sys.stderr)
        return {"skipped": True, "reason": str(exc)}

    events = data.get("events", [])
    if not events:
        print("  No events to sync.", file=sys.stderr)
        return {"created": 0, "deduped": 0, "updated_projects": 0, "errors": 0}

    # Query existing event keys for dedup
    print("  Querying existing audit events...", file=sys.stderr)
    existing_keys = _query_existing_event_keys(events_db_id, token, version)
    print(f"  Found {len(existing_keys)} existing audit events.", file=sys.stderr)

    created = 0
    deduped = 0
    errors = 0
    updated_projects = 0

    # Create new events
    for event in events:
        if event["eventKey"] in existing_keys:
            deduped += 1
            continue

        page_id = _create_event_page(event, events_db_id, token, version)
        if page_id:
            created += 1
        else:
            errors += 1
        time.sleep(REQUEST_DELAY)

    # Update project derived fields
    # Group events by project ID for field updates
    project_audits: dict[str, dict] = {}
    for event in events:
        pid = event.get("localProjectId")
        if pid and event["eventKey"] not in existing_keys:
            project_audits[pid] = _extract_audit_data(event)

    for project_id, audit_data in project_audits.items():
        if _update_project_fields(project_id, audit_data, token, version):
            updated_projects += 1
        time.sleep(REQUEST_DELAY)

    print(
        f"  Notion sync: {created} created, {deduped} deduped, "
        f"{updated_projects} projects updated, {errors} errors",
        file=sys.stderr,
    )

    return {
        "created": created,
        "deduped": deduped,
        "updated_projects": updated_projects,
        "errors": errors,
    }


def _resolve_collection_config(config: dict, stem: str) -> tuple[str | None, bool]:
    data_source_id = config.get(f"{stem}_data_source_id")
    if data_source_id:
        return data_source_id, True
    database_id = config.get(f"{stem}_db_id")
    if database_id:
        return database_id, False
    return None, False


def _query_page_by_rich_text_id(
    collection_id: str,
    *,
    use_data_source: bool,
    property_name: str,
    property_value: str,
    token: str,
    version: str,
) -> dict | None:
    body = {
        "filter": {
            "property": property_name,
            "rich_text": {"equals": property_value},
        },
        "page_size": 1,
    }
    response = _query_notion_collection(collection_id, token, version, body)
    if not response or response.status_code != 200:
        return None
    results = response.json().get("results", [])
    return results[0] if results else None


def sync_campaign_actions(
    actions: list[dict],
    campaign_summary: dict,
    *,
    config_dir: Path = Path("config"),
    apply: bool = False,
    previous_state: dict | None = None,
    sync_mode: str = "reconcile",
) -> tuple[list[dict], dict[str, dict], list[dict]]:
    """Create or update managed Notion action and campaign records."""
    if not apply:
        return [], {}, []

    token = get_notion_token()
    if not token:
        return ([{"target": "notion-actions", "status": "skipped", "reason": "no token"}], {}, [])

    config = _load_notion_config(config_dir)
    if not config:
        return ([{"target": "notion-actions", "status": "skipped", "reason": "no config"}], {}, [])

    action_collection_id, action_is_data_source = _resolve_collection_config(config, "action_requests")
    campaign_collection_id, campaign_is_data_source = _resolve_collection_config(config, "campaign_runs")
    if campaign_collection_id is None:
        campaign_collection_id, campaign_is_data_source = _resolve_collection_config(config, "recommendation_runs")

    version = config.get("notion_version", DEFAULT_NOTION_VERSION)
    results: list[dict] = []
    external_refs: dict[str, dict] = {}
    managed_state_drift: list[dict] = []
    previous_actions = (previous_state or {}).get("actions", {})
    project_map = {}
    try:
        from src.notion_export import _load_project_map

        project_map = _load_project_map(config_dir)
    except Exception:
        project_map = {}

    if action_collection_id:
        for action in actions:
            existing = _query_page_by_rich_text_id(
                action_collection_id,
                use_data_source=action_is_data_source,
                property_name="Action ID",
                property_value=action["action_id"],
                token=token,
                version=version,
            )
            desired_status = "Open"
            properties = {
                "Name": _title_value(action["title"]),
                "Source Type": _select_value("Audit"),
                "Status": _select_value(desired_status if apply else "Draft"),
                "Action ID": _rich_text_value(action["action_id"]),
                "Campaign": _select_value(action["campaign_type"]),
            }
            mapping = project_map.get(action["repo"], {})
            if mapping.get("localProjectId"):
                properties["Local Project"] = {"relation": [{"id": mapping["localProjectId"]}]}
            properties["Summary"] = _rich_text_value(action["body"])
            body = {"properties": properties}

            if existing:
                page_id = existing.get("id")
                previous_status = (
                    existing.get("properties", {})
                    .get("Status", {})
                    .get("select", {})
                    .get("name")
                )
                response = _notion_request("PATCH", f"/pages/{page_id}", token, version, body)
                if response and response.status_code == 200:
                    status = "reopened" if previous_status in {"Resolved", "Cancelled"} else ("unchanged" if previous_status == desired_status else "updated")
                else:
                    status = "failed"
                url = existing.get("url")
            else:
                body["parent"] = _notion_parent_for_collection(action_collection_id, use_data_source=action_is_data_source)
                response = _notion_request("POST", "/pages", token, version, body)
                status = "created" if response and response.status_code == 200 else "failed"
                payload = response.json() if response and response.status_code == 200 else {}
                page_id = payload.get("id")
                url = payload.get("url")

            results.append(
                {
                    "target": "notion-action",
                    "action_id": action["action_id"],
                    "repo_full_name": action["repo_full_name"],
                    "campaign_type": action["campaign_type"],
                    "status": status,
                    "page_id": page_id,
                    "url": url,
                    "expected": {"status": desired_status},
                }
            )
            if url:
                external_refs[action["action_id"]] = {
                    "notion_action_url": url,
                    "notion_action_page_id": page_id,
                }
            time.sleep(REQUEST_DELAY)

        current_action_ids = {action["action_id"] for action in actions}
        for action_id, previous in previous_actions.items():
            if action_id in current_action_ids:
                continue
            existing = _query_page_by_rich_text_id(
                action_collection_id,
                use_data_source=action_is_data_source,
                property_name="Action ID",
                property_value=action_id,
                token=token,
                version=version,
            )
            if sync_mode == "append-only":
                results.append(
                    {
                        "target": "notion-action",
                        "action_id": action_id,
                        "repo_full_name": previous.get("repo_full_name", ""),
                        "campaign_type": previous.get("campaign_type", ""),
                        "status": "stale",
                        "reason": "append-only",
                    }
                )
                continue
            if not existing:
                managed_state_drift.append(
                    {
                        "action_id": action_id,
                        "repo_full_name": previous.get("repo_full_name", ""),
                        "campaign_type": previous.get("campaign_type", ""),
                        "target": "notion-action",
                        "drift_state": "managed-notion-action-missing",
                    }
                )
                results.append(
                    {
                        "target": "notion-action",
                        "action_id": action_id,
                        "repo_full_name": previous.get("repo_full_name", ""),
                        "campaign_type": previous.get("campaign_type", ""),
                        "status": "drifted",
                        "drift_state": "managed-notion-action-missing",
                    }
                )
                continue
            page_id = existing.get("id")
            response = _notion_request(
                "PATCH",
                f"/pages/{page_id}",
                token,
                version,
                {"properties": {"Status": _select_value("Resolved")}},
            )
            results.append(
                {
                    "target": "notion-action",
                    "action_id": action_id,
                    "repo_full_name": previous.get("repo_full_name", ""),
                    "campaign_type": previous.get("campaign_type", ""),
                    "status": "closed" if response and response.status_code == 200 else "failed",
                    "page_id": page_id,
                    "url": existing.get("url"),
                    "expected": {"status": "Resolved"},
                }
            )
    else:
        results.append({"target": "notion-action", "status": "skipped", "reason": "no action collection config"})

    if campaign_collection_id:
        name = f"Campaign Run — {campaign_summary.get('label', campaign_summary.get('campaign_type', 'Campaign'))}"
        properties = {
            "Name": _title_value(name),
            "Run Type": _select_value("Audit"),
            "Status": _select_value("Succeeded"),
        }
        body = {
            "parent": _notion_parent_for_collection(campaign_collection_id, use_data_source=campaign_is_data_source),
            "properties": properties,
        }
        response = _notion_request("POST", "/pages", token, version, body)
        payload = response.json() if response and response.status_code == 200 else {}
        results.append(
            {
                "target": "notion-campaign",
                "status": "created" if response and response.status_code == 200 else "failed",
                "url": payload.get("url"),
            }
        )
    else:
        results.append({"target": "notion-campaign", "status": "skipped", "reason": "no campaign collection config"})

    return results, external_refs, managed_state_drift


# ── Recommendation Run ──────────────────────────────────────────────


ELIGIBLE_TIERS = {"shipped", "functional"}

FLAG_TO_ACTION = {
    "no-tests": ("Add test framework and initial tests", "testing"),
    "no-ci": ("Add GitHub Actions CI workflow", "cicd"),
    "no-readme": ("Create comprehensive README", "readme"),
}


def _render_quick_wins_markdown(quick_wins: list[dict], date: str) -> str:
    """Render quick wins as markdown for a Notion recommendation page."""
    lines = [
        f"## Audit Quick Wins ({date})",
        "",
    ]
    if not quick_wins:
        lines.append("No repos within striking distance of tier promotion.")
        return "\n".join(lines)

    for win in quick_wins[:10]:
        lines.append(
            f"**{win['name']}** — {win['current_tier']} → {win['next_tier']} "
            f"(gap: {win['gap']:.3f})"
        )
        for action in win.get("actions", []):
            lines.append(f"  - {action}")
        lines.append("")

    return "\n".join(lines)


def create_recommendation_run(
    report_data: dict,
    quick_wins: list[dict],
    token: str,
    config: dict,
) -> str | None:
    """Create an Audit Recommendation Run page in Notion."""
    db_id = config.get("recommendation_runs_db_id", "")
    if not db_id:
        print("  recommendation_runs_db_id not set, skipping.", file=sys.stderr)
        return None

    version = config.get("notion_version", DEFAULT_NOTION_VERSION)
    date = report_data.get("generated_at", "")[:10]

    properties = {
        "Name": _title_value(f"Audit Recommendation Run — {date}"),
        "Run Type": _select_value("Audit"),
        "Status": _select_value("Succeeded"),
    }

    # Build markdown content as children blocks
    md = _render_quick_wins_markdown(quick_wins, date)
    children = [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": chunk}}]
            },
        }
        for chunk in _chunk_text(md, 2000)
    ]

    body = {
        "parent": {"database_id": db_id},
        "properties": properties,
        "children": children,
    }

    resp = _notion_request("POST", "/pages", token, version, body)
    if resp and resp.status_code == 200:
        page_id = resp.json().get("id", "")
        print(f"  Recommendation run created: {page_id}", file=sys.stderr)
        return page_id
    if resp:
        print(f"  Failed to create recommendation run: {resp.status_code}", file=sys.stderr)
    return None


# ── Action Requests ─────────────────────────────────────────────────


def create_audit_action_requests(
    audits: list[dict],
    project_map: dict[str, dict],
    token: str,
    config: dict,
) -> int:
    """Create draft GitHub issue action requests for critical audit gaps."""
    db_id = config.get("action_requests_db_id", "")
    if not db_id:
        print("  action_requests_db_id not set, skipping.", file=sys.stderr)
        return 0

    version = config.get("notion_version", DEFAULT_NOTION_VERSION)
    created = 0

    for audit in audits:
        tier = audit.get("completeness_tier", "")
        if tier not in ELIGIBLE_TIERS:
            continue

        name = audit.get("metadata", {}).get("name", "")
        mapping = project_map.get(name)
        if not mapping:
            continue

        flags = set(audit.get("flags", []))
        for flag, (action_desc, dimension) in FLAG_TO_ACTION.items():
            if flag not in flags:
                continue

            title = f"Audit: {action_desc} for {name}"
            properties = {
                "Name": _title_value(title),
                "Source Type": _select_value("Audit"),
                "Status": _select_value("Draft"),
            }

            if mapping.get("localProjectId"):
                properties["Local Project"] = {"relation": [{"id": mapping["localProjectId"]}]}

            body = {
                "parent": {"database_id": db_id},
                "properties": properties,
            }

            resp = _notion_request("POST", "/pages", token, version, body)
            if resp and resp.status_code == 200:
                created += 1
            time.sleep(REQUEST_DELAY)

    if created:
        print(f"  Action requests: {created} draft requests created.", file=sys.stderr)
    return created


# ── Weekly Review Patch ─────────────────────────────────────────────

WEEKLY_REVIEW_BEGIN_MARKER = "[GHRA-BEGIN-AUDIT-HIGHLIGHTS]"
WEEKLY_REVIEW_END_MARKER = "[GHRA-END-AUDIT-HIGHLIGHTS]"


def _render_audit_highlights(
    report_data: dict,
    diff_data: dict | None,
    quick_wins: list[dict],
) -> str:
    """Render audit highlights markdown for weekly review."""
    date = report_data.get("generated_at", "")[:10]
    grade = report_data.get("portfolio_grade", "?")
    avg = report_data.get("average_score", 0)
    tiers = report_data.get("tier_distribution", {})
    shipped = tiers.get("shipped", 0)
    functional = tiers.get("functional", 0)

    lines = [
        f"### Audit Highlights ({date})",
        "",
        f"**Portfolio:** Grade {grade} | Avg {avg:.2f} | {shipped} shipped, {functional} functional",
        "",
    ]

    # Tier changes from diff
    if diff_data:
        changes = diff_data.get("tier_changes", [])
        if changes:
            promos = [c for c in changes if c.get("direction") == "promotion"]
            demos = [c for c in changes if c.get("direction") == "demotion"]
            lines.append(f"**Tier Changes:** {len(promos)} promotions, {len(demos)} demotions")
            for c in changes[:5]:
                icon = "+" if c.get("direction") == "promotion" else "-"
                lines.append(f"  {icon} {c['name']}: {c.get('old_tier', '?')} -> {c.get('new_tier', '?')}")
            lines.append("")

    # Quick wins
    if quick_wins:
        lines.append("**Top Quick Wins:**")
        for w in quick_wins[:3]:
            lines.append(f"  - {w['name']} needs {w['gap']:.3f} to reach {w['next_tier']}")
        lines.append("")

    operator_summary = report_data.get("operator_summary") or {}
    operator_queue = report_data.get("operator_queue") or []
    if operator_summary or operator_queue:
        counts = operator_summary.get("counts", {})
        lines.append("**Operator Control Center:**")
        lines.append(
            "  "
            f"Blocked {counts.get('blocked', 0)} | "
            f"Urgent {counts.get('urgent', 0)} | "
            f"Ready {counts.get('ready', 0)} | "
            f"Deferred {counts.get('deferred', 0)}"
        )
        lines.append(f"  Headline: {operator_summary.get('headline', 'No operator triage items are currently surfaced.')}")
        for item in operator_queue[:3]:
            repo = f"{item.get('repo')}: " if item.get("repo") else ""
            lines.append(f"  - {repo}{item.get('title', 'Triage item')} -> {item.get('recommended_action', 'Review the latest state.')}")
        lines.append("")

    return "\n".join(lines)


def _block_plain_text(block: dict) -> str:
    block_type = block.get("type", "")
    content = block.get(block_type, {}) if block_type else {}
    parts: list[str] = []
    for item in content.get("rich_text", []) or []:
        text = item.get("plain_text") or item.get("text", {}).get("content", "")
        if text:
            parts.append(text)
    return "".join(parts)


def _managed_section_block_ids(blocks: list[dict]) -> list[str]:
    start_index = None
    end_index = None
    for index, block in enumerate(blocks):
        text = _block_plain_text(block)
        if text == WEEKLY_REVIEW_BEGIN_MARKER:
            start_index = index
        if text == WEEKLY_REVIEW_END_MARKER and start_index is not None:
            end_index = index
            break
    if start_index is None:
        return []
    block_slice = blocks[start_index : (end_index + 1 if end_index is not None else len(blocks))]
    return [block.get("id", "") for block in block_slice if block.get("id")]


def _paragraph_block(text: str) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": text}}]
        },
    }


def _build_weekly_review_section_blocks(highlights: str) -> list[dict]:
    blocks = [_paragraph_block(WEEKLY_REVIEW_BEGIN_MARKER)]
    blocks.extend(_paragraph_block(chunk) for chunk in _chunk_text(highlights, 2000))
    blocks.append(_paragraph_block(WEEKLY_REVIEW_END_MARKER))
    return blocks


def patch_weekly_review(
    report_data: dict,
    diff_data: dict | None,
    quick_wins: list[dict],
    token: str,
    config: dict,
) -> bool:
    """Replace the managed audit-highlights section on the most recent weekly review page."""
    db_id = config.get("weekly_reviews_db_id", "")
    if not db_id:
        print("  weekly_reviews_db_id not set, skipping.", file=sys.stderr)
        return False

    version = config.get("notion_version", DEFAULT_NOTION_VERSION)

    # Find most recent weekly review
    query_body = {
        "sorts": [{"timestamp": "created_time", "direction": "descending"}],
        "page_size": 1,
    }
    resp = _notion_request("POST", f"/databases/{db_id}/query", token, version, query_body)
    if not resp or resp.status_code != 200:
        print("  Failed to query weekly reviews.", file=sys.stderr)
        return False

    results = resp.json().get("results", [])
    if not results:
        print("  No weekly review pages found.", file=sys.stderr)
        return False

    page_id = results[0]["id"]
    highlights = _render_audit_highlights(report_data, diff_data, quick_wins)
    existing_blocks_resp = _notion_request("GET", f"/blocks/{page_id}/children", token, version)
    if existing_blocks_resp and existing_blocks_resp.status_code == 200:
        existing_blocks = existing_blocks_resp.json().get("results", [])
        for block_id in _managed_section_block_ids(existing_blocks):
            _notion_request("PATCH", f"/blocks/{block_id}", token, version, {"archived": True})
            time.sleep(REQUEST_DELAY)

    children = _build_weekly_review_section_blocks(highlights)

    resp = _notion_request(
        "PATCH", f"/blocks/{page_id}/children", token, version,
        {"children": children},
    )
    if resp and resp.status_code == 200:
        print("  Weekly review updated with managed audit highlights.", file=sys.stderr)
        return True
    if resp:
        print(f"  Failed to patch weekly review: {resp.status_code}", file=sys.stderr)
    return False


def _chunk_text(text: str, max_len: int = 2000) -> list[str]:
    """Split text into chunks respecting Notion's 2000-char limit."""
    if len(text) <= max_len:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:max_len])
        text = text[max_len:]
    return chunks


# ── Audit History Database ──────────────────────────────────────────


def create_audit_history_entry(
    report_data: dict,
    token: str,
    config: dict,
) -> str | None:
    """Create an audit history row in Notion. Returns page ID or None."""
    db_id = config.get("audit_history_db_id", "")
    if not db_id:
        return None

    version = config.get("notion_version", DEFAULT_NOTION_VERSION)
    date = report_data.get("generated_at", "")[:10]
    tiers = report_data.get("tier_distribution", {})

    properties = {
        "Name": _title_value(f"Audit Run — {date}"),
        "Repos Audited": {"number": report_data.get("repos_audited", 0)},
        "Avg Score": {"number": round(report_data.get("average_score", 0), 3)},
        "Portfolio Grade": _select_value(report_data.get("portfolio_grade", "F")),
        "Shipped": {"number": tiers.get("shipped", 0)},
    }

    body = {"parent": {"database_id": db_id}, "properties": properties}
    resp = _notion_request("POST", "/pages", token, version, body)
    if resp and resp.status_code == 200:
        return resp.json().get("id")
    return None


# ── Project Completeness Cards ──────────────────────────────────────


def patch_project_completeness_cards(
    audits: list[dict],
    project_map: dict[str, dict],
    token: str,
    config: dict,
) -> int:
    """Append audit summary blocks to mapped project pages. Returns count updated."""
    version = config.get("notion_version", DEFAULT_NOTION_VERSION)
    updated = 0

    for audit in audits:
        name = audit.get("metadata", {}).get("name", "")
        mapping = project_map.get(name)
        if not mapping or not mapping.get("localProjectId"):
            continue

        page_id = mapping["localProjectId"]
        grade = audit.get("grade", "F")
        score = audit.get("overall_score", 0)
        tier = audit.get("completeness_tier", "")
        badges = ", ".join(audit.get("badges", [])[:5])

        dim_scores = {
            r["dimension"]: f"{r['score']:.1f}"
            for r in audit.get("analyzer_results", [])
            if r["dimension"] != "interest"
        }
        dims_str = " | ".join(f"{d}: {s}" for d, s in list(dim_scores.items())[:6])

        card_text = (
            f"Audit: Grade {grade} | Score {score:.2f} | Tier {tier}\n"
            f"{dims_str}\n"
            f"Badges: {badges or 'none'}"
        )

        children = [{
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": card_text[:2000]}}],
                "icon": {"emoji": "📊"},
            },
        }]

        resp = _notion_request(
            "PATCH", f"/blocks/{page_id}/children", token, version,
            {"children": children},
        )
        if resp and resp.status_code == 200:
            updated += 1
        time.sleep(REQUEST_DELAY)

    if updated:
        print(f"  Completeness cards: {updated} projects updated.", file=sys.stderr)
    return updated


# ── Recommendation Follow-Up ───────────────────────────────────────


def check_recommendation_followup(
    report_data: dict,
    token: str,
    config: dict,
) -> dict:
    """Check if previous audit recommendations were acted on.

    Returns {checked, improved, still_open, summary}.
    """
    db_id = config.get("recommendation_runs_db_id", "")
    if not db_id:
        return {"checked": 0}

    version = config.get("notion_version", DEFAULT_NOTION_VERSION)

    # Query most recent Audit recommendation run
    query_body = {
        "filter": {"property": "Run Type", "select": {"equals": "Audit"}},
        "sorts": [{"timestamp": "created_time", "direction": "descending"}],
        "page_size": 1,
    }
    resp = _notion_request("POST", f"/databases/{db_id}/query", token, version, query_body)
    if not resp or resp.status_code != 200:
        return {"checked": 0}

    results = resp.json().get("results", [])
    if not results:
        return {"checked": 0}

    # Extract repo names from the recommendation page title/content
    # The recommendation run contains quick-win repo names in its content
    # We can't easily parse block content via API, so use a simpler approach:
    # Compare current scores against previous audit's quick wins

    # Build current score map
    current_scores = {
        a.get("metadata", {}).get("name", ""): a.get("overall_score", 0)
        for a in report_data.get("audits", [])
    }

    # Fetch block children from the recommendation run page
    page_id = results[0]["id"]
    blocks_resp = _notion_request("GET", f"/blocks/{page_id}/children", token, version)
    if not blocks_resp or blocks_resp.status_code != 200:
        print("  Recommendation follow-up: could not fetch page blocks.", file=sys.stderr)
        return {"checked": 0}

    # Extract text content from all blocks
    block_text_parts: list[str] = []
    for block in blocks_resp.json().get("results", []):
        block_type = block.get("type", "")
        type_content = block.get(block_type, {})
        rich_text = type_content.get("rich_text", [])
        for rt in rich_text:
            text = rt.get("plain_text") or rt.get("text", {}).get("content", "")
            if text:
                block_text_parts.append(text)

    combined_text = " ".join(block_text_parts)

    # Match repo names from block text against current_scores
    improved: list[str] = []
    still_open: list[str] = []
    for repo_name, score in current_scores.items():
        if not repo_name:
            continue
        if repo_name.lower() in combined_text.lower():
            if score > 0:
                improved.append(repo_name)
            else:
                still_open.append(repo_name)

    matched = len(improved) + len(still_open)
    summary = f"{len(improved)} of {matched} repos tracked in current audit"
    print(f"  Recommendation follow-up: {summary}", file=sys.stderr)
    return {
        "checked": matched,
        "improved": improved,
        "still_open": still_open,
        "summary": summary,
    }
