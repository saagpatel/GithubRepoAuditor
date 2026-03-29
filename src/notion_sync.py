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
    notion_request,
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
    print(f"  Querying existing audit events...", file=sys.stderr)
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

    return "\n".join(lines)


def patch_weekly_review(
    report_data: dict,
    diff_data: dict | None,
    quick_wins: list[dict],
    token: str,
    config: dict,
) -> bool:
    """Append audit highlights to the most recent weekly review page."""
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

    # Append as a new block to the page
    children = [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": chunk}}]
            },
        }
        for chunk in _chunk_text(highlights, 2000)
    ]

    resp = _notion_request(
        "PATCH", f"/blocks/{page_id}/children", token, version,
        {"children": children},
    )
    if resp and resp.status_code == 200:
        print(f"  Weekly review patched with audit highlights.", file=sys.stderr)
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
        date = audit.get("metadata", {}).get("pushed_at", "")[:10] or "?"
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
