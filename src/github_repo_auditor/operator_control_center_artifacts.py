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
    _PERSISTED_WEEKLY_DIGEST,
    build_weekly_command_center_digest,
    load_latest_portfolio_truth,
    write_weekly_command_center_artifacts,
)

_SENSITIVE_LABELLED_VALUE = re.compile(
    r"(?i)\b(?:[a-z0-9]+[-_])*(?:secret|token|password|credential)"
    r"(?:[-_][a-z0-9]+)+\b"
)
_SAFE_MARKDOWN_TEXT = "<redacted>"
_PERSISTED_CONTROL_SCHEMA = "control_center_artifact_v2"
_PERSISTED_REDACTED_TEXT = "<redacted>"
_SAFE_PERSISTED_LANES = frozenset({"blocked", "urgent", "ready", "deferred"})


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
    """Build a fail-closed projection for the persisted Markdown artifact.

    Operator prose, identifiers, paths, and URLs may contain opaque secrets that
    no pattern-based redactor can distinguish from ordinary text. Persist only
    fixed explanatory text plus finite status/lane values and numeric counts.
    """
    raw_setup = snapshot.get("operator_setup_health")
    setup = raw_setup if isinstance(raw_setup, dict) else {}
    safe_status = _persisted_status(setup.get("status", "unknown"))

    def safe_count(value: object) -> int:
        return value if isinstance(value, int) and value >= 0 else 0

    raw_queue = snapshot.get("operator_queue")
    safe_queue = []
    if isinstance(raw_queue, list):
        for item in raw_queue:
            if not isinstance(item, dict):
                continue
            lane = _persisted_lane(item.get("lane", "deferred"))
            safe_queue.append(
                {
                    "lane": lane,
                    "repo": "",
                    "title": _SAFE_MARKDOWN_TEXT,
                    "summary": _SAFE_MARKDOWN_TEXT,
                    "lane_reason": _SAFE_MARKDOWN_TEXT,
                    "recommended_action": _SAFE_MARKDOWN_TEXT,
                }
            )

    return {
        "operator_summary": {"headline": _SAFE_MARKDOWN_TEXT},
        "operator_setup_health": {
            "status": safe_status,
            "blocking_errors": safe_count(setup.get("blocking_errors")),
            "warnings": safe_count(setup.get("warnings")),
        },
        "operator_queue": safe_queue,
        "operator_recent_changes": [],
    }


def _persisted_count(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return max(0, min(value, 1_000_000))
    return 0


def _persisted_status(value: object) -> str:
    candidate = str(value or "").strip().lower()
    if candidate == "ok":
        return "ok"
    if candidate == "ready":
        return "ready"
    if candidate == "current":
        return "current"
    if candidate == "warning":
        return "warning"
    if candidate == "blocked":
        return "blocked"
    if candidate == "error":
        return "error"
    return "unknown"


def _persisted_lane(value: object) -> str:
    candidate = str(value or "").strip().lower()
    if candidate == "blocked":
        return "blocked"
    if candidate == "urgent":
        return "urgent"
    if candidate == "ready":
        return "ready"
    return "deferred"


def _persistable_control_center_payload(
    snapshot: dict,
    *,
    username: str,
    generated_at: datetime,
) -> dict:
    """Return the only projection permitted to cross the durable JSON sink.

    Rich report and operator data remains available to the current process and
    the in-memory return value.  Durable artifacts intentionally retain only
    fixed labels, finite statuses, and bounded structural counts; arbitrary
    prose, identifiers, paths, URLs, and provider-authored values are omitted.
    """
    setup = snapshot.get("operator_setup_health")
    setup = setup if isinstance(setup, dict) else {}
    queue = snapshot.get("operator_queue")
    queue_items = queue if isinstance(queue, list) else []
    lane_counts = {lane: 0 for lane in _SAFE_PERSISTED_LANES}
    for item in queue_items:
        if not isinstance(item, dict):
            continue
        lane = str(item.get("lane") or "").strip().lower()
        if lane in lane_counts:
            lane_counts[lane] += 1

    recent_changes = snapshot.get("operator_recent_changes")
    recent_change_count = len(recent_changes) if isinstance(recent_changes, list) else 0
    return {
        "contract_version": _PERSISTED_CONTROL_SCHEMA,
        "storage_policy": "allowlisted-summary-only",
        # Routing metadata is already present in the artifact filename; retain
        # it so scheduled-handoff discovery remains compatible.
        "username": username or "unknown",
        "generated_at": generated_at.isoformat(),
        "operator_summary": {
            "headline": _PERSISTED_REDACTED_TEXT,
            "queue_count": _persisted_count(len(queue_items)),
        },
        "operator_setup_health": {
            "status": _persisted_status(setup.get("status")),
            "blocking_errors": _persisted_count(setup.get("blocking_errors")),
            "warnings": _persisted_count(setup.get("warnings")),
        },
        "operator_queue_summary": {
            "count": _persisted_count(len(queue_items)),
            "lane_counts": {
                "blocked": _persisted_count(lane_counts["blocked"]),
                "urgent": _persisted_count(lane_counts["urgent"]),
                "ready": _persisted_count(lane_counts["ready"]),
                "deferred": _persisted_count(lane_counts["deferred"]),
            },
        },
        "operator_recent_changes_count": _persisted_count(recent_change_count),
        "weekly_command_center_digest_v1": _PERSISTED_WEEKLY_DIGEST,
    }


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
        markdown_snapshot, "operator", generated_at.date().isoformat()
    )
    if contains_sensitive_data(rendered_markdown):
        raise ValueError("control-center artifacts must not persist credential fields")
    safe_rendered_markdown = rendered_markdown
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
    # Persist only an explicit allowlisted projection.  The rich payload above
    # remains an in-memory compatibility return for the current operator run.
    persisted_payload = _persistable_control_center_payload(
        snapshot,
        username=username,
        generated_at=generated_at,
    )
    json_path.write_text(json.dumps(persisted_payload, indent=2, sort_keys=True))
    # The exact rendered value is redacted and rechecked immediately before persistence.
    md_path.write_text(safe_rendered_markdown)
    return json_path, md_path, weekly_json, weekly_md, payload
