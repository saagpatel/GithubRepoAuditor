from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ACKNOWLEDGMENTS_FILENAME = "operator-acknowledgments-{username}.json"
ACKNOWLEDGMENTS_VERSION = 1


def acknowledgments_path(output_dir: Path, username: str) -> Path:
    return Path(output_dir) / ACKNOWLEDGMENTS_FILENAME.format(username=username)


def load_acknowledgments(output_dir: Path, username: str) -> list[dict]:
    path = acknowledgments_path(output_dir, username)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    acks = payload.get("acknowledgments")
    if not isinstance(acks, list):
        return []
    return [ack for ack in acks if isinstance(ack, dict)]


def save_acknowledgment(output_dir: Path, username: str, ack: dict) -> Path:
    path = acknowledgments_path(output_dir, username)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_acknowledgments(output_dir, username)
    change_key = ack.get("change_key")
    deduped = [item for item in existing if item.get("change_key") != change_key]
    deduped.append(ack)
    payload = {
        "version": ACKNOWLEDGMENTS_VERSION,
        "username": username,
        "acknowledgments": deduped,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def directional_signature(change: dict) -> dict:
    change_type = change.get("change_type", "")
    details = change.get("details") or {}
    if change_type == "security-change":
        return {
            "old_label": details.get("old_label"),
            "new_label": details.get("new_label"),
        }
    if change_type == "lens-delta":
        lens = details.get("lens")
        lens_value = (details.get("lens_deltas") or {}).get(lens)
        if lens_value is None:
            lens_value = details.get("delta", 0.0)
        return {
            "lens": lens,
            "delta_sign": _sign(lens_value),
        }
    if change_type == "tier-change":
        return {
            "old_tier": details.get("old_tier"),
            "new_tier": details.get("new_tier"),
        }
    if change_type == "score-delta":
        delta = details.get("delta", 0.0)
        return {"delta_sign": _sign(delta)}
    return {}


def _sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def is_change_acknowledged(change: dict, acknowledgments: list[dict]) -> bool:
    if not acknowledgments:
        return False
    change_key = change.get("change_key")
    if not change_key:
        return False
    expected_signature = directional_signature(change)
    for ack in acknowledgments:
        if ack.get("change_key") != change_key:
            continue
        ack_signature = ack.get("signature") or {}
        if ack_signature == expected_signature:
            return True
    return False


def build_acknowledgment_record(change: dict, *, reviewer: str, note: str) -> dict:
    return {
        "change_key": change.get("change_key", ""),
        "change_type": change.get("change_type", ""),
        "repo_name": change.get("repo_name", ""),
        "title": change.get("title", ""),
        "signature": directional_signature(change),
        "acknowledged_at": datetime.now(timezone.utc).isoformat(),
        "reviewer": reviewer,
        "note": note,
    }


def find_matching_change(
    *,
    repo_name: str,
    change_kind: str,
    material_changes: list[dict],
) -> dict | None:
    for change in material_changes:
        if change.get("change_type") != change_kind:
            continue
        if change.get("repo_name") != repo_name:
            continue
        return change
    return None
