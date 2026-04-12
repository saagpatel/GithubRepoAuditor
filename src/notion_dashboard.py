"""Notion native dashboard page creation with linked database views."""
from __future__ import annotations

import sys

from src.notion_client import (
    DEFAULT_NOTION_VERSION,
    notion_request,
)


def create_notion_dashboard(
    report_data: dict,
    token: str,
    config: dict,
) -> str | None:
    """Create an Audit Dashboard page in Notion. Returns page ID or None."""
    parent_id = config.get("dashboard_parent_page_id", "")
    if not parent_id:
        print("  dashboard_parent_page_id not set, skipping dashboard.", file=sys.stderr)
        return None

    version = config.get("notion_version", DEFAULT_NOTION_VERSION)
    date = report_data.get("generated_at", "")[:10]
    grade = report_data.get("portfolio_grade", "F")
    avg = report_data.get("average_score", 0)
    repos = report_data.get("repos_audited", 0)
    tiers = report_data.get("tier_distribution", {})

    # Build page content as blocks
    children = [
        _heading_block(f"Portfolio Audit Dashboard — {date}", level=1),
        _paragraph_block(
            f"Grade: {grade} | Avg Score: {avg:.2f} | "
            f"{repos} repos | "
            f"{tiers.get('shipped', 0)} shipped, {tiers.get('functional', 0)} functional"
        ),
        _divider_block(),
        _heading_block("Tier Distribution", level=2),
    ]

    # Add tier stats as a bulleted list
    for tier_name in ["shipped", "functional", "wip", "skeleton", "abandoned"]:
        count = tiers.get(tier_name, 0)
        if count:
            children.append(_bullet_block(f"{tier_name.capitalize()}: {count}"))

    children.append(_divider_block())
    children.append(_heading_block("Top Repos", level=2))

    # Add top 10 repos as bullets
    audits = sorted(report_data.get("audits", []), key=lambda a: a.get("overall_score", 0), reverse=True)
    for a in audits[:10]:
        name = a.get("metadata", {}).get("name", "")
        score = a.get("overall_score", 0)
        g = a.get("grade", "F")
        children.append(_bullet_block(f"{name} — Grade {g} ({score:.2f})"))

    # Create the page
    body = {
        "parent": {"page_id": parent_id},
        "properties": {
            "title": [{"text": {"content": f"Audit Dashboard — {date}"}}],
        },
        "children": children[:100],  # Notion limit: 100 blocks per request
    }

    resp = notion_request("POST", "/pages", token, version, body)
    if resp and resp.status_code == 200:
        page_id = resp.json().get("id", "")
        print(f"  Notion dashboard created: {page_id}", file=sys.stderr)
        return page_id
    if resp:
        print(f"  Failed to create dashboard: {resp.status_code} {resp.text[:200]}", file=sys.stderr)
    return None


def _heading_block(text: str, level: int = 2) -> dict:
    key = f"heading_{level}"
    return {
        "object": "block",
        "type": key,
        key: {"rich_text": [{"type": "text", "text": {"content": text}}]},
    }


def _paragraph_block(text: str) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {"content": text[:2000]}}]},
    }


def _bullet_block(text: str) -> dict:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": text}}]},
    }


def _divider_block() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}
