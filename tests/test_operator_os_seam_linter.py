from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from src.operator_os_seam_linter import (
    build_worklist_payload,
    lint_operator_os_seams,
    main,
)
from src.portfolio_truth_render import GENERATED_MARKDOWN_PROVENANCE_MARKER
from src.portfolio_truth_types import SCHEMA_VERSION


NOW = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)


def _write_truth(
    path: Path,
    *,
    generated_at: str = "2026-07-03T09:00:00+00:00",
    schema_version: str | None = SCHEMA_VERSION,
    projects: list[dict] | None = None,
) -> None:
    payload = {
        "generated_at": generated_at,
        "projects": projects or [],
    }
    if schema_version is not None:
        payload["schema_version"] = schema_version
    path.write_text(json.dumps(payload))


def _write_markdown(path: Path, *, marker: bool = True) -> None:
    prefix = f"{GENERATED_MARKDOWN_PROVENANCE_MARKER}\n\n" if marker else ""
    path.write_text(f"{prefix}# Generated Artifact\n")


def _passing_paths(tmp_path: Path) -> tuple[Path, list[Path]]:
    truth = tmp_path / "portfolio-truth-latest.json"
    registry = tmp_path / "project-registry.md"
    report = tmp_path / "PORTFOLIO-AUDIT-REPORT.md"
    _write_truth(truth)
    _write_markdown(registry)
    _write_markdown(report)
    return truth, [registry, report]


def _write_identity_truth(path: Path) -> None:
    _write_truth(
        path,
        projects=[
            {
                "identity": {
                    "project_key": "Fun:GamePrjs/ CryptForge",
                    "display_name": "CryptForge",
                    "repo_full_name": "saagpatel/CryptForge",
                }
            },
            {
                "identity": {
                    "project_key": "operant-public",
                    "display_name": "operant-public",
                    "repo_full_name": "saagpatel/operant",
                }
            },
        ],
    )


def _write_bridge_db(
    path: Path,
    *,
    activity_rows: list[tuple[str, str | None]] | None = None,
    session_cost_names: list[str | None] | None = None,
) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE activity_log (project_name TEXT NOT NULL, canonical_key TEXT)"
        )
        conn.execute("CREATE TABLE session_costs (project_name TEXT)")
        conn.executemany(
            "INSERT INTO activity_log (project_name, canonical_key) VALUES (?, ?)",
            activity_rows or [],
        )
        conn.executemany(
            "INSERT INTO session_costs (project_name) VALUES (?)",
            [(name,) for name in (session_cost_names or [])],
        )


def _write_notification_db(path: Path, projects: list[str | None]) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE durable_events (project TEXT)")
        conn.executemany(
            "INSERT INTO durable_events (project) VALUES (?)",
            [(project,) for project in projects],
        )


def _write_notion_snapshot(path: Path, titles: list[str]) -> None:
    path.write_text(json.dumps({"projects": [{"title": title} for title in titles]}))


def test_fresh_artifact_passes(tmp_path: Path) -> None:
    truth, markdown = _passing_paths(tmp_path)

    result = lint_operator_os_seams(
        truth_path=truth,
        markdown_paths=markdown,
        now=NOW,
        max_staleness_hours=30,
    )

    assert result.passed


def test_stale_artifact_fails(tmp_path: Path) -> None:
    truth, markdown = _passing_paths(tmp_path)
    _write_truth(truth, generated_at="2026-07-01T00:00:00+00:00")

    result = lint_operator_os_seams(
        truth_path=truth,
        markdown_paths=markdown,
        now=NOW,
        max_staleness_hours=30,
    )

    assert not result.passed
    assert [finding.check for finding in result.findings] == ["artifact_freshness"]
    assert "stale" in result.findings[0].violation


def test_schema_pin_passes(tmp_path: Path) -> None:
    truth, markdown = _passing_paths(tmp_path)

    result = lint_operator_os_seams(truth_path=truth, markdown_paths=markdown, now=NOW)

    assert result.passed


def test_schema_pin_mismatch_fails(tmp_path: Path) -> None:
    truth, markdown = _passing_paths(tmp_path)
    _write_truth(truth, schema_version="0.6.0")

    result = lint_operator_os_seams(truth_path=truth, markdown_paths=markdown, now=NOW)

    assert not result.passed
    assert result.findings[0].check == "schema_pin"
    assert "mismatch" in result.findings[0].violation


def test_schema_pin_missing_fails(tmp_path: Path) -> None:
    truth, markdown = _passing_paths(tmp_path)
    _write_truth(truth, schema_version=None)

    result = lint_operator_os_seams(truth_path=truth, markdown_paths=markdown, now=NOW)

    assert not result.passed
    assert result.findings[0].check == "schema_pin"
    assert "missing" in result.findings[0].violation


def test_generated_markdown_with_marker_passes(tmp_path: Path) -> None:
    truth, markdown = _passing_paths(tmp_path)

    result = lint_operator_os_seams(truth_path=truth, markdown_paths=markdown, now=NOW)

    assert result.passed


def test_hand_edited_markdown_without_marker_fails(tmp_path: Path) -> None:
    truth, markdown = _passing_paths(tmp_path)
    _write_markdown(markdown[0], marker=False)

    result = lint_operator_os_seams(truth_path=truth, markdown_paths=markdown, now=NOW)

    assert not result.passed
    assert result.findings[0].check == "markdown_generated_not_hand_edited"
    assert "provenance marker is missing" in result.findings[0].violation


def test_worklist_payload_uses_existing_attention_item_shape(tmp_path: Path) -> None:
    truth, markdown = _passing_paths(tmp_path)
    _write_truth(truth, schema_version="0.6.0")
    result = lint_operator_os_seams(truth_path=truth, markdown_paths=markdown, now=NOW)

    payload = build_worklist_payload(result)

    assert payload["schema_version"] == "operator_os_seam_linter_worklist.v1"
    assert payload["state"] == "fail"
    assert payload["items"][0]["kind"] == "operator_os_seam_linter"
    assert payload["items"][0]["severity"] == "critical"
    assert payload["items"][0]["target_type"] == "artifact"


def test_identity_resolution_known_aliases_pass(tmp_path: Path) -> None:
    truth, markdown = _passing_paths(tmp_path)
    _write_identity_truth(truth)
    bridge_db = tmp_path / "bridge.db"
    notification_db = tmp_path / "notification.sqlite3"
    notion_snapshot = tmp_path / "notion.json"
    _write_bridge_db(
        bridge_db,
        activity_rows=[("CryptForge", "saagpatel/CryptForge")],
        session_cost_names=["Fun-GamePrjs-CryptForge"],
    )
    _write_notification_db(notification_db, ["CryptForge"])
    _write_notion_snapshot(notion_snapshot, ["OPERANT"])

    result = lint_operator_os_seams(
        truth_path=truth,
        markdown_paths=markdown,
        bridge_db_path=bridge_db,
        notification_db_path=notification_db,
        notion_snapshot_path=notion_snapshot,
        now=NOW,
    )

    assert result.passed


def test_identity_resolution_explicit_home_adhoc_passes(tmp_path: Path) -> None:
    truth, markdown = _passing_paths(tmp_path)
    _write_identity_truth(truth)
    bridge_db = tmp_path / "bridge.db"
    _write_bridge_db(bridge_db, session_cost_names=["home-adhoc"])

    result = lint_operator_os_seams(
        truth_path=truth,
        markdown_paths=markdown,
        bridge_db_path=bridge_db,
        now=NOW,
    )

    assert result.passed


def test_identity_resolution_minted_dialect_fails(tmp_path: Path) -> None:
    truth, markdown = _passing_paths(tmp_path)
    _write_identity_truth(truth)
    notification_db = tmp_path / "notification.sqlite3"
    _write_notification_db(notification_db, ["task-clear-my-portfolio-s-dependabot"])

    result = lint_operator_os_seams(
        truth_path=truth,
        markdown_paths=markdown,
        notification_db_path=notification_db,
        now=NOW,
    )

    assert not result.passed
    assert result.findings[0].check == "identity_resolution"
    assert result.findings[0].violation == "minted identity dialect"


def test_identity_resolution_hex_fragment_fails(tmp_path: Path) -> None:
    truth, markdown = _passing_paths(tmp_path)
    _write_identity_truth(truth)
    bridge_db = tmp_path / "bridge.db"
    _write_bridge_db(bridge_db, session_cost_names=["085"])

    result = lint_operator_os_seams(
        truth_path=truth,
        markdown_paths=markdown,
        bridge_db_path=bridge_db,
        now=NOW,
    )

    assert not result.passed
    assert result.findings[0].check == "identity_resolution"
    assert result.findings[0].violation == "silent unresolved identity"


def test_identity_resolution_bridge_canonical_key_disagreement_fails(
    tmp_path: Path,
) -> None:
    truth, markdown = _passing_paths(tmp_path)
    _write_identity_truth(truth)
    bridge_db = tmp_path / "bridge.db"
    _write_bridge_db(bridge_db, activity_rows=[("OPERANT", "operant-public")])

    result = lint_operator_os_seams(
        truth_path=truth,
        markdown_paths=markdown,
        bridge_db_path=bridge_db,
        now=NOW,
    )

    assert not result.passed
    assert result.findings[0].check == "identity_resolution"
    assert result.findings[0].violation == "bridge canonical_key disagrees with alias map"


def test_cli_identity_resolution_is_opt_in(tmp_path: Path) -> None:
    truth, markdown = _passing_paths(tmp_path)
    bridge_db = tmp_path / "bridge.db"
    _write_bridge_db(bridge_db, session_cost_names=["085"])

    code = main(
        [
            "--truth",
            str(truth),
            "--markdown",
            str(markdown[0]),
            "--markdown",
            str(markdown[1]),
            "--bridge-db",
            str(bridge_db),
            "--json",
        ]
    )

    assert code == 0

    code = main(
        [
            "--truth",
            str(truth),
            "--markdown",
            str(markdown[0]),
            "--markdown",
            str(markdown[1]),
            "--identity-resolution",
            "--bridge-db",
            str(bridge_db),
            "--json",
        ]
    )

    assert code == 1


def test_cli_exits_nonzero_and_writes_worklist_on_failure(tmp_path: Path) -> None:
    truth, markdown = _passing_paths(tmp_path)
    _write_truth(truth, schema_version="0.6.0")
    worklist = tmp_path / "worklist.json"

    code = main(
        [
            "--truth",
            str(truth),
            "--markdown",
            str(markdown[0]),
            "--markdown",
            str(markdown[1]),
            "--worklist-output",
            str(worklist),
            "--json",
        ]
    )

    assert code == 1
    payload = json.loads(worklist.read_text())
    assert payload["items"][0]["kind"] == "operator_os_seam_linter"
