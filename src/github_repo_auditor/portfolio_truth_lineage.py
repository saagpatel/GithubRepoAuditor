from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def resolve_notion_origin(artifact_path: Path) -> str | None:
    """Resolve the oldest preserved Notion observation through carry-forward history."""
    return _resolve_notion_origin(artifact_path, visited=set())


def _resolve_notion_origin(
    artifact_path: Path, *, visited: set[Path]
) -> str | None:
    resolved_path = artifact_path.resolve()
    if resolved_path in visited:
        return None
    visited.add(resolved_path)
    payload = _read_json_object(artifact_path)
    if payload is None:
        return None
    generated_at = _text(payload.get("generated_at"))
    inputs = payload.get("inputs")
    notion = inputs.get("notion") if isinstance(inputs, dict) else None
    if not isinstance(notion, dict):
        return generated_at

    mode = notion.get("mode")
    if mode == "live":
        return _text(notion.get("observed_at")) or generated_at
    if mode != "carried-forward":
        return _text(notion.get("observed_at")) or generated_at

    declared_origin = _text(notion.get("carried_from_generated_at")) or _text(
        notion.get("observed_at")
    )
    if declared_origin is None:
        return None
    predecessor = _find_artifact_by_generated_at(
        artifact_path.parent,
        generated_at=declared_origin,
        excluded=visited,
    )
    if predecessor is None:
        return declared_origin
    return (
        _resolve_notion_origin(predecessor, visited=visited)
        or declared_origin
    )


def _find_artifact_by_generated_at(
    directory: Path, *, generated_at: str, excluded: set[Path]
) -> Path | None:
    for candidate in sorted(directory.glob("portfolio-truth-*.json"), reverse=True):
        if candidate.resolve() in excluded:
            continue
        payload = _read_json_object(candidate)
        if payload is not None and _text(payload.get("generated_at")) == generated_at:
            return candidate
    return None


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None
