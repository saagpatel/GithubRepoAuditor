"""Helpers for Action Items workbook content."""

from __future__ import annotations

from typing import Any

ACTION_ITEMS_HEADERS = ["#", "Repo", "Action", "Impact", "Effort", "Dimension"]
EFFORT_MAP = {
    "readme": "Low",
    "structure": "Low",
    "cicd": "Low",
    "documentation": "Low",
    "community_profile": "Low",
    "dependencies": "Low",
    "build_readiness": "Med",
    "testing": "Med",
    "code_quality": "Med",
    "activity": "High",
}
TIER_NEXT = {
    "abandoned": ("skeleton", 0.15),
    "skeleton": ("wip", 0.35),
    "wip": ("functional", 0.55),
    "functional": ("shipped", 0.75),
}


def collect_action_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for audit in data.get("audits", []):
        tier = audit.get("completeness_tier", "")
        if tier not in TIER_NEXT:
            continue

        next_tier, threshold = TIER_NEXT[tier]
        gap = threshold - audit.get("overall_score", 0)
        if gap <= 0:
            continue

        dimension_scores = {
            result["dimension"]: result["score"]
            for result in audit.get("analyzer_results", [])
            if result["dimension"] != "interest"
        }
        for dimension, score in sorted(dimension_scores.items(), key=lambda item: item[1])[:2]:
            actions.append(
                {
                    "repo": audit["metadata"]["name"],
                    "action": f"Improve {dimension} (currently {score:.1f})",
                    "impact": f"Close {gap:.3f} gap to {next_tier}",
                    "effort": EFFORT_MAP.get(dimension, "Med"),
                    "dimension": dimension,
                    "gap": gap,
                }
            )

        for badge_suggestion in audit.get("next_badges", [])[:1]:
            actions.append(
                {
                    "repo": audit["metadata"]["name"],
                    "action": badge_suggestion.get("action", ""),
                    "impact": f"Earn '{badge_suggestion.get('badge', '')}' badge",
                    "effort": (
                        "Low" if badge_suggestion.get("gap", 1) < 0.3 else "Med"
                    ),
                    "dimension": "badges",
                    "gap": badge_suggestion.get("gap", 1.0),
                }
            )

    effort_order = {"Low": 0, "Med": 1, "High": 2}
    actions.sort(key=lambda action: (effort_order.get(action["effort"], 1), action["gap"]))

    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, Any]] = []
    for action in actions:
        key = (action["repo"], action["dimension"])
        if key not in seen:
            seen.add(key)
            unique.append(action)
    return unique


def build_action_items_content(actions: list[dict[str, Any]]) -> dict[str, Any]:
    sprint_actions = [action for action in actions if action["effort"] == "Low"][:5]
    return {
        "sprint_rows": _build_action_rows(sprint_actions),
        "all_rows": _build_action_rows(actions[:100]),
    }


def write_action_items_sections(
    ws,
    content: dict[str, Any],
    *,
    section_font,
    style_header_row,
    style_data_cell,
    apply_zebra_stripes,
    set_autofilter,
) -> int:
    ws.freeze_panes = "A5"

    if content["sprint_rows"]:
        ws.cell(row=3, column=1, value="Weekly Sprint (Top 5 Low-Effort)").font = section_font
        for col, header in enumerate(ACTION_ITEMS_HEADERS, 1):
            ws.cell(row=4, column=col, value=header)
        style_header_row(ws, 4, len(ACTION_ITEMS_HEADERS))
        for row_number, row_values in enumerate(content["sprint_rows"], 5):
            for col, value in enumerate(row_values, 1):
                style_data_cell(ws.cell(row=row_number, column=col, value=value))

    full_start = len(content["sprint_rows"]) + 7
    ws.cell(row=full_start, column=1, value="All Actions (Prioritized)").font = section_font
    full_start += 1
    for col, header in enumerate(ACTION_ITEMS_HEADERS, 1):
        ws.cell(row=full_start, column=col, value=header)
    style_header_row(ws, full_start, len(ACTION_ITEMS_HEADERS))

    for row_number, row_values in enumerate(content["all_rows"], full_start + 1):
        for col, value in enumerate(row_values, 1):
            style_data_cell(ws.cell(row=row_number, column=col, value=value))

    final_row = full_start + len(content["all_rows"])
    if content["all_rows"]:
        apply_zebra_stripes(ws, full_start + 1, final_row, len(ACTION_ITEMS_HEADERS))
        set_autofilter(ws, len(ACTION_ITEMS_HEADERS), final_row, start_row=full_start)
    return final_row


def _build_action_rows(actions: list[dict[str, Any]]) -> list[list[Any]]:
    return [
        [
            index,
            action["repo"],
            action["action"],
            action["impact"],
            action["effort"],
            action["dimension"],
        ]
        for index, action in enumerate(actions, start=1)
    ]
