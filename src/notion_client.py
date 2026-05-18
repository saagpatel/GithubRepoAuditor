"""Shared Notion API client helpers.

Provides HTTP request wrapper with retry, property value builders,
and config loading. Used by notion_sync.py and notion_registry.py.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

NOTION_API_BASE = "https://api.notion.com/v1"
DEFAULT_NOTION_VERSION = "2026-03-11"
REQUEST_DELAY = 0.3  # seconds between API calls (rate limit ~3 req/s)
MAX_RETRIES = 3


def load_notion_config(config_dir: Path) -> dict | None:
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


def notion_request(
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


def query_notion_collection(
    collection_id: str,
    token: str,
    version: str = DEFAULT_NOTION_VERSION,
    body: dict | None = None,
) -> requests.Response | None:
    """Query a Notion database or data source with compatibility fallback."""
    body = body or {}
    response = notion_request("POST", f"/data-sources/{collection_id}/query", token, version, body)
    if response is not None and response.status_code != 404:
        return response
    return notion_request("POST", f"/databases/{collection_id}/query", token, version, body)


def notion_parent_for_collection(collection_id: str, *, use_data_source: bool = False) -> dict:
    """Build a Notion parent object for either a database or data source."""
    return {"data_source_id": collection_id} if use_data_source else {"database_id": collection_id}


def rich_text_value(text: str) -> dict:
    """Build a Notion rich_text property value."""
    return {"rich_text": [{"text": {"content": text[:2000]}}]}


def select_value(name: str) -> dict:
    """Build a Notion select property value."""
    return {"select": {"name": name}}


def title_value(text: str) -> dict:
    """Build a Notion title property value."""
    return {"title": [{"text": {"content": text}}]}


def get_notion_token() -> str:
    """Read NOTION_TOKEN from environment. Returns empty string if unset."""
    import os
    return os.environ.get("NOTION_TOKEN", "").strip()


def query_page_by_title(
    db_id: str,
    title: str,
    token: str,
    title_property: str = "Name",
    version: str = DEFAULT_NOTION_VERSION,
) -> str | None:
    """Query a Notion database for a page by title. Returns page_id or None."""
    body = {
        "filter": {"property": title_property, "title": {"equals": title}},
        "page_size": 1,
    }
    resp = notion_request("POST", f"/databases/{db_id}/query", token, version, body)
    if resp and resp.status_code == 200:
        results = resp.json().get("results", [])
        return results[0]["id"] if results else None
    return None
