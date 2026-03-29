"""Notion as registry source — query Local Portfolio Projects to reconcile against audits."""
from __future__ import annotations

import sys
import time
from pathlib import Path

from src.notion_client import (
    DEFAULT_NOTION_VERSION,
    REQUEST_DELAY,
    get_notion_token,
    load_notion_config,
    notion_request,
)


def load_notion_registry(config_dir: Path = Path("config")) -> dict[str, str] | None:
    """Query Notion for all projects, return as {name: status} dict.

    Compatible with registry_parser.reconcile(). Returns None if token/config missing.
    """
    token = get_notion_token()
    if not token:
        print("  NOTION_TOKEN not set. Cannot query Notion registry.", file=sys.stderr)
        return None

    config = load_notion_config(config_dir)
    if not config:
        return None

    db_id = config.get("projects_data_source_id", "")
    if not db_id:
        print("  projects_data_source_id not set in notion-config.json", file=sys.stderr)
        return None

    version = config.get("notion_version", DEFAULT_NOTION_VERSION)

    projects: dict[str, str] = {}
    start_cursor = None

    while True:
        body: dict = {"page_size": 100}
        if start_cursor:
            body["start_cursor"] = start_cursor

        resp = notion_request("POST", f"/databases/{db_id}/query", token, version, body)
        if not resp or resp.status_code != 200:
            print("  Failed to query Notion projects database.", file=sys.stderr)
            break

        data = resp.json()
        for page in data.get("results", []):
            name = _extract_title(page)
            if name:
                status = _extract_select(page, "Current State") or "active"
                projects[name] = _normalize_status(status)

        if not data.get("has_more"):
            break
        start_cursor = data.get("next_cursor")
        time.sleep(REQUEST_DELAY)

    print(f"  Notion registry: {len(projects)} projects loaded.", file=sys.stderr)
    return projects


def _extract_title(page: dict) -> str:
    """Extract the title text from a Notion page."""
    props = page.get("properties", {})
    for prop in props.values():
        if prop.get("type") == "title":
            title_parts = prop.get("title", [])
            if title_parts:
                return title_parts[0].get("text", {}).get("content", "")
    return ""


def _extract_select(page: dict, prop_name: str) -> str:
    """Extract a select property value from a Notion page."""
    props = page.get("properties", {})
    prop = props.get(prop_name, {})
    sel = prop.get("select")
    if sel:
        return sel.get("name", "")
    return ""


def _normalize_status(notion_status: str) -> str:
    """Map Notion project states to registry-compatible statuses."""
    s = notion_status.lower()
    if s in ("active", "building", "in progress"):
        return "active"
    if s in ("shipped", "complete", "done"):
        return "active"
    if s in ("paused", "on hold", "parked"):
        return "parked"
    if s in ("archived", "abandoned", "cold storage"):
        return "archived"
    return "active"
