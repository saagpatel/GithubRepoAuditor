"""Control-center filtering and artifact generation outside CLI dispatch."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from github_repo_auditor.cache import contains_sensitive_data
from github_repo_auditor.cli_output import redact_sensitive_text
from github_repo_auditor.operator_artifact_paths import control_center_paths
from github_repo_auditor.operator_control_center import (
    control_center_artifact_payload,
    render_control_center_markdown,
)
from github_repo_auditor.weekly_command_center import (
    build_weekly_command_center_digest,
    load_latest_portfolio_truth,
    write_weekly_command_center_artifacts,
)

_SENSITIVE_LABELLED_VALUE = re.compile(
    r"(?i)\b(?:[a-z0-9]+[-_])*(?:secret|token|password|credential)"
    r"(?:[-_][a-z0-9]+)+\b"
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


def _looks_sensitive_key(key: str) -> bool:
    lowered = str(key or "").strip().lower()
    return any(
        marker in lowered
        for marker in (
            "secret",
            "token",
            "password",
            "passwd",
            "credential",
            "api_key",
            "apikey",
            "private_key",
            "access_key",
        )
    )


def _redact_sensitive_values(value: object) -> object:
    if isinstance(value, dict):
        redacted: dict = {}
        for k, v in value.items():
            if _looks_sensitive_key(str(k)):
                redacted[k] = "[REDACTED]"
            else:
                redacted[k] = _redact_sensitive_values(v)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive_values(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_sensitive_values(item) for item in value)
    if isinstance(value, str):
        redacted_text = redact_sensitive_text(value)
        return _SENSITIVE_LABELLED_VALUE.sub("<redacted>", redacted_text)
    return value


def _sanitized_snapshot_for_rendering(snapshot: dict) -> dict:
    redacted = _redact_sensitive_values(snapshot)
    return redacted if isinstance(redacted, dict) else {}


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
    if contains_sensitive_data(report_data) or contains_sensitive_data(snapshot):
        raise ValueError("control-center artifacts must not persist credential fields")
    filter_snapshot_for_default_view(snapshot)
    json_path, md_path = control_center_paths(output_dir, username, generated_at)
    snapshot.setdefault("operator_summary", {})["control_center_reference"] = str(json_path)
    portfolio_truth_path, portfolio_truth = load_latest_portfolio_truth(output_dir)
    weekly_digest = build_weekly_command_center_digest(
        report_data,
        snapshot,
        diff_data=diff_dict,
        portfolio_truth=portfolio_truth,
        portfolio_truth_history_dir=portfolio_truth_path.parent if portfolio_truth_path else None,
        portfolio_truth_reference=str(portfolio_truth_path) if portfolio_truth_path else "",
        control_center_reference=str(json_path),
        report_reference=report_reference,
        generated_at=generated_at.isoformat(),
    )
    if contains_sensitive_data(weekly_digest):
        raise ValueError("control-center artifacts must not persist credential fields")
    markdown_snapshot = _sanitized_snapshot_for_rendering(snapshot)
    sanitized_report_data = _redact_sensitive_values(report_data)
    if not isinstance(sanitized_report_data, dict):
        raise ValueError("control-center artifacts must not persist credential fields")
    payload = control_center_artifact_payload(sanitized_report_data, markdown_snapshot)
    sanitized_weekly_digest_for_payload = _redact_sensitive_values(weekly_digest)
    payload["weekly_command_center_digest_v1"] = sanitized_weekly_digest_for_payload
    sanitized_payload = _redact_sensitive_values(payload)
    if not isinstance(sanitized_payload, dict):
        raise ValueError("control-center artifacts must not persist credential fields")
    payload = sanitized_payload
    if contains_sensitive_data(payload) or contains_sensitive_data(snapshot):
        raise ValueError("control-center artifacts must not persist credential fields")
    if contains_sensitive_data(markdown_snapshot):
        raise ValueError("control-center artifacts must not persist credential fields")
    rendered_markdown = render_control_center_markdown(
        markdown_snapshot, username, generated_at.isoformat()
    )
    if contains_sensitive_data(rendered_markdown):
        raise ValueError("control-center artifacts must not persist credential fields")
    safe_rendered_markdown = redact_sensitive_text(rendered_markdown)
    if contains_sensitive_data(safe_rendered_markdown):
        raise ValueError("control-center artifacts must not persist credential fields")
    sanitized_weekly_digest = _redact_sensitive_values(weekly_digest)
    if not isinstance(sanitized_weekly_digest, dict):
        raise ValueError("control-center artifacts must not persist credential fields")
    if contains_sensitive_data(sanitized_weekly_digest):
        raise ValueError("control-center artifacts must not persist credential fields")
    weekly_json, weekly_md = write_weekly_command_center_artifacts(
        output_dir,
        username=username,
        generated_at=generated_at,
        digest=sanitized_weekly_digest,
    )
    payload["weekly_command_center_reference"] = {
        "json_path": str(weekly_json),
        "markdown_path": str(weekly_md),
    }
    # The payload is recursively sanitized and checked before persistence.
    json_path.write_text(json.dumps(payload, indent=2))
    # The exact rendered value is redacted and rechecked immediately before persistence.
    md_path.write_text(safe_rendered_markdown)
    return json_path, md_path, weekly_json, weekly_md, payload
