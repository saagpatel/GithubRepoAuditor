"""Notion API sync — pushes audit signal events to Notion databases.

Uses raw requests (no SDK) consistent with the project's minimal dependency philosophy.
Requires NOTION_TOKEN environment variable and config/notion-config.json.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

NOTION_API_BASE = "https://api.notion.com/v1"
DEFAULT_NOTION_VERSION = "2022-06-28"
REQUEST_DELAY = 0.3  # seconds between API calls (rate limit ~3 req/s)
MAX_RETRIES = 3


def _load_notion_config(config_dir: Path) -> dict | None:
    """Load Notion database IDs from config."""
    path = config_dir / "notion-config.json"
    if not path.is_file():
        print("  Notion config not found at config/notion-config.json", file=sys.stderr)
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  Failed to read Notion config: {exc}", file=sys.stderr)
        return None


def _notion_request(
    method: str,
    path: str,
    token: str,
    version: str = DEFAULT_NOTION_VERSION,
    body: dict | None = None,
) -> requests.Response | None:
    """Make a Notion API request with retry on 429/5xx."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": version,
        "Content-Type": "application/json",
    }
    url = f"{NOTION_API_BASE}{path}"

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.request(
                method, url, headers=headers,
                json=body, timeout=30,
            )
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 2))
                print(f"  Rate limited, waiting {retry_after}s...", file=sys.stderr)
                time.sleep(retry_after)
                continue
            if response.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            return response
        except requests.RequestException as exc:
            if attempt == MAX_RETRIES - 1:
                print(f"  Notion API error: {exc}", file=sys.stderr)
                return None
            time.sleep(2 ** attempt)
    return None


def _rich_text_value(text: str) -> dict:
    """Build a Notion rich_text property value."""
    return {"rich_text": [{"text": {"content": text[:2000]}}]}


def _select_value(name: str) -> dict:
    """Build a Notion select property value."""
    return {"select": {"name": name}}


def _title_value(text: str) -> dict:
    """Build a Notion title property value."""
    return {"title": [{"text": {"content": text}}]}


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
    token = os.environ.get("NOTION_TOKEN", "").strip()
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
            raw = json.loads(event.get("rawExcerpt", "{}"))
            project_audits[pid] = {
                "grade": event["status"],
                "overall_score": raw.get("dimensions", {}).get("code_quality", 0),
                "interest_score": raw.get("interest_score", 0),
                "badges": raw.get("badges", []),
                "date": event["occurredAt"],
            }

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
