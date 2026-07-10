"""Control-center filtering and artifact generation outside CLI dispatch."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from src.cache import redact_sensitive_data
from src.operator_artifact_paths import control_center_paths
from src.operator_control_center import (
    control_center_artifact_payload,
    render_control_center_markdown,
)
from src.weekly_command_center import (
    build_weekly_command_center_digest,
    load_latest_portfolio_truth,
    write_weekly_command_center_artifacts,
)


def should_print_control_center_item(item: dict) -> bool:
    catalog = item.get("portfolio_catalog") or {}
    lifecycle = str(catalog.get("lifecycle_state") or "").strip().lower()
    intended = str(catalog.get("intended_disposition") or "").strip().lower()
    program = str(catalog.get("maturity_program") or "").strip().lower()
    operating_path = str(
        item.get("operating_path") or catalog.get("operating_path") or ""
    ).strip().lower()
    if lifecycle in {"archived", "archive"}:
        return False
    if intended == "archive" or program == "archive" or operating_path == "archive":
        return False
    if lifecycle in {"experiment", "experimental"}:
        return False
    if intended == "experiment" or program == "experiment" or operating_path == "experiment":
        return False
    return True


def filter_snapshot_for_default_view(snapshot: dict) -> dict:
    queue = snapshot.get("operator_queue")
    if not isinstance(queue, list):
        return snapshot
    snapshot["operator_queue"] = [
        item
        for item in queue
        if isinstance(item, dict) and should_print_control_center_item(item)
    ]
    return snapshot


def _sanitize_control_center_text(value: str) -> str:
    """Scrub sensitive/security-secret phrasing from persisted narrative text."""
    sanitized = value
    sanitized = re.sub(r"\bsecret[-_\s]?scanning\b", "security scanning", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"\b(secret|token|password|private[_\s-]?key|credential)s?\b", "[REDACTED]", sanitized, flags=re.IGNORECASE)
    return sanitized


def _sanitize_control_center_snapshot(snapshot: dict) -> dict:
    sanitized_snapshot = dict(snapshot)
    queue = sanitized_snapshot.get("operator_queue")
    if isinstance(queue, list):
        cleaned_queue: list[dict] = []
        for item in queue:
            if not isinstance(item, dict):
                cleaned_queue.append(item)
                continue
            cleaned_item = dict(item)
            for text_key in (
                "summary",
                "follow_through_summary",
                "follow_through_evidence_hint",
                "recommended_action",
                "title",
            ):
                if isinstance(cleaned_item.get(text_key), str):
                    cleaned_item[text_key] = _sanitize_control_center_text(cleaned_item[text_key])
            cleaned_queue.append(cleaned_item)
        sanitized_snapshot["operator_queue"] = cleaned_queue
    return sanitized_snapshot


def write_control_center_artifacts(
    report_data: dict,
    snapshot: dict,
    output_dir: Path,
    *,
    username: str,
    generated_at: datetime,
    report_reference: str,
    diff_dict: dict | None = None,
) -> tuple[Path, Path, Path, Path, dict]:
    filter_snapshot_for_default_view(snapshot)
    json_path, md_path = control_center_paths(output_dir, username, generated_at)
    snapshot.setdefault("operator_summary", {})["control_center_reference"] = str(json_path)
    portfolio_truth_path, portfolio_truth = load_latest_portfolio_truth(output_dir)
    weekly_digest = build_weekly_command_center_digest(
        report_data,
        snapshot,
        diff_data=diff_dict,
        portfolio_truth=portfolio_truth,
        portfolio_truth_reference=str(portfolio_truth_path) if portfolio_truth_path else "",
        control_center_reference=str(json_path),
        report_reference=report_reference,
        generated_at=generated_at.isoformat(),
    )
    weekly_json, weekly_md = write_weekly_command_center_artifacts(
        output_dir,
        username=username,
        generated_at=generated_at,
        digest=weekly_digest,
    )
    payload = control_center_artifact_payload(report_data, snapshot)
    payload["weekly_command_center_digest_v1"] = weekly_digest
    payload["weekly_command_center_reference"] = {
        "json_path": str(weekly_json),
        "markdown_path": str(weekly_md),
    }
    safe_payload = redact_sensitive_data(payload)
    safe_snapshot = redact_sensitive_data(snapshot)
    safe_snapshot = _sanitize_control_center_snapshot(safe_snapshot)
    json_path.write_text(json.dumps(safe_payload, indent=2))  # lgtm [py/clear-text-storage-sensitive-data] redacted above
    md_path.write_text(render_control_center_markdown(safe_snapshot, username, generated_at.isoformat()))  # lgtm [py/clear-text-storage-sensitive-data] redacted above
    return json_path, md_path, weekly_json, weekly_md, payload
