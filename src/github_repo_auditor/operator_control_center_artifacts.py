"""Control-center filtering and artifact generation outside CLI dispatch."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from github_repo_auditor.cache import contains_sensitive_data
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
    payload = control_center_artifact_payload(report_data, snapshot)
    payload["weekly_command_center_digest_v1"] = weekly_digest
    if contains_sensitive_data(payload) or contains_sensitive_data(snapshot):
        raise ValueError("control-center artifacts must not persist credential fields")
    markdown_snapshot = _sanitized_snapshot_for_rendering(snapshot)
    if contains_sensitive_data(markdown_snapshot):
        raise ValueError("control-center artifacts must not persist credential fields")
    rendered_markdown = render_control_center_markdown(
        markdown_snapshot, username, generated_at.isoformat()
    )
    if contains_sensitive_data(rendered_markdown):
        raise ValueError("control-center artifacts must not persist credential fields")
    weekly_json, weekly_md = write_weekly_command_center_artifacts(
        output_dir,
        username=username,
        generated_at=generated_at,
        digest=weekly_digest,
    )
    payload["weekly_command_center_reference"] = {
        "json_path": str(weekly_json),
        "markdown_path": str(weekly_md),
    }
    # Credential-shaped data is rejected above.
    # codeql[py/clear-text-storage-sensitive-data]
    json_path.write_text(json.dumps(payload, indent=2))
    # The exact rendered value is rejected above if it contains credential data.
    # lgtm[py/clear-text-storage-sensitive-data]
    md_path.write_text(rendered_markdown)
    return json_path, md_path, weekly_json, weekly_md, payload
