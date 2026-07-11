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


def _refresh_truth_for_cli(path: Path) -> None:
    payload = json.loads(path.read_text())
    payload["generated_at"] = datetime.now(UTC).isoformat()
    path.write_text(json.dumps(payload))


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
    activity_rows: list[tuple[str, str | None] | tuple[str, str | None, str]]
    | None = None,
    session_cost_names: list[str | None] | None = None,
    session_cost_rows: list[tuple[str | None, str]] | None = None,
) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE activity_log (project_name TEXT NOT NULL, canonical_key TEXT, timestamp TEXT)"
        )
        conn.execute("CREATE TABLE session_costs (project_name TEXT, started_at TEXT)")
        for row in activity_rows or []:
            project_name, canonical_key, *rest = row
            timestamp = rest[0] if rest else "2026-07-03T12:00:00+00:00"
            conn.execute(
                "INSERT INTO activity_log (project_name, canonical_key, timestamp) VALUES (?, ?, ?)",
                (project_name, canonical_key, timestamp),
            )
        cost_rows = session_cost_rows or [
            (name, "2026-07-03T12:00:00+00:00")
            for name in (session_cost_names or [])
        ]
        conn.executemany(
            "INSERT INTO session_costs (project_name, started_at) VALUES (?, ?)",
            cost_rows,
        )


def _write_notification_db(
    path: Path,
    projects: list[str | None],
    *,
    created_at: str = "2026-07-03T12:00:00+00:00",
) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE durable_events (project TEXT, created_at TEXT)")
        conn.executemany(
            "INSERT INTO durable_events (project, created_at) VALUES (?, ?)",
            [(project, created_at) for project in projects],
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


def test_legacy_schema_remains_readable_during_migration(tmp_path: Path) -> None:
    truth, markdown = _passing_paths(tmp_path)
    _write_truth(truth, schema_version="0.7.0")

    result = lint_operator_os_seams(truth_path=truth, markdown_paths=markdown, now=NOW)

    assert result.passed


def test_contract_shadow_marks_legacy_lineage_unknown_without_failing(
    tmp_path: Path,
) -> None:
    truth, markdown = _passing_paths(tmp_path)
    _write_truth(truth, schema_version="0.7.0")

    result = lint_operator_os_seams(
        truth_path=truth,
        markdown_paths=markdown,
        contract_shadow=True,
        now=NOW,
    )

    assert result.passed
    assert result.state == "unknown"
    assert {finding.check for finding in result.findings} == {
        "CL-PROD-001",
        "CL-INP-001",
        "CL-COUNT-001",
        "CL-EXCL-001",
    }


def test_contract_shadow_fails_unreconciled_decision_counts(tmp_path: Path) -> None:
    truth, markdown = _passing_paths(tmp_path)
    payload = json.loads(truth.read_text())
    payload.update(
        {
            "producer": {},
            "inputs": {
                "notion": {"mode": "unavailable"},
                "catalog": {"sha256": None},
            },
            "source_summary": {"attention_state_counts": {"decision-needed": 1}},
            "rollups": {"decision": {"decision_needed_count": 0}},
        }
    )
    truth.write_text(json.dumps(payload))

    result = lint_operator_os_seams(
        truth_path=truth,
        markdown_paths=markdown,
        contract_shadow=True,
        catalog_path=tmp_path / "missing-catalog.yaml",
        now=NOW,
    )

    assert not result.passed
    assert result.state == "fail"
    assert any(finding.check == "CL-COUNT-001" for finding in result.findings)


def test_contract_shadow_warns_for_carried_notion_older_than_48_hours(
    tmp_path: Path,
) -> None:
    truth, markdown = _passing_paths(tmp_path)
    payload = json.loads(truth.read_text())
    payload.update(
        {
            "producer": {},
            "inputs": {
                "notion": {
                    "mode": "carried-forward",
                    "carried_from_generated_at": "2026-07-01T00:00:00+00:00",
                },
                "catalog": {"sha256": None},
            },
            "source_summary": {"attention_state_counts": {"decision-needed": 0}},
            "rollups": {"decision": {"decision_needed_count": 0}},
        }
    )
    truth.write_text(json.dumps(payload))

    result = lint_operator_os_seams(
        truth_path=truth,
        markdown_paths=markdown,
        contract_shadow=True,
        catalog_path=tmp_path / "missing-catalog.yaml",
        now=NOW,
    )

    assert result.passed
    assert result.state == "warn"
    assert any(
        finding.check == "CL-FRESH-002" and finding.level == "warn"
        for finding in result.findings
    )


def test_contract_shadow_fails_when_excluded_backup_leaks_into_projects(
    tmp_path: Path,
) -> None:
    truth, markdown = _passing_paths(tmp_path)
    payload = json.loads(truth.read_text())
    payload.update(
        {
            "producer": {},
            "inputs": {
                "notion": {"mode": "unavailable"},
                "catalog": {"sha256": None},
            },
            "source_summary": {"attention_state_counts": {"decision-needed": 1}},
            "rollups": {"decision": {"decision_needed_count": 1}},
            "exclusions": {
                "policy_version": "workspace_discovery.v1",
                "counts": {},
            },
            "projects": [
                {
                    "identity": {
                        "path": "Documents/Codex Backups/Wave 2R Post-Update"
                    },
                    "derived": {"attention_state": "decision-needed"},
                }
            ],
        }
    )
    truth.write_text(json.dumps(payload))

    result = lint_operator_os_seams(
        truth_path=truth,
        markdown_paths=markdown,
        contract_shadow=True,
        catalog_path=tmp_path / "missing-catalog.yaml",
        now=NOW,
    )

    assert not result.passed
    finding = next(item for item in result.findings if item.check == "CL-EXCL-001")
    assert finding.level == "fail"
    assert "Codex Backups" in finding.detail


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


def test_identity_resolution_supplementary_project_resolves(tmp_path: Path) -> None:
    # personal-ops / SecondBrain are repo-less supplementary registry projects
    # (absent from portfolio-truth). Both their name and their supp: canonical
    # key must resolve, not flag as minted dialects.
    truth, markdown = _passing_paths(tmp_path)
    _write_identity_truth(truth)
    bridge_db = tmp_path / "bridge.db"
    _write_bridge_db(
        bridge_db,
        activity_rows=[
            ("personal-ops", "supp:personal-ops"),
            ("SecondBrain", "supp:SecondBrain"),
        ],
    )
    result = lint_operator_os_seams(
        truth_path=truth, markdown_paths=markdown, bridge_db_path=bridge_db, now=NOW
    )
    assert result.passed, [f.detail for f in result.findings]


def test_identity_resolution_migration_drift_alias_resolves(tmp_path: Path) -> None:
    # o2-fable-runpack is OPERANT activity logged under a loose name; the
    # census-seeded alias map maps it to the operant repo so it resolves.
    truth, markdown = _passing_paths(tmp_path)
    _write_identity_truth(truth)
    bridge_db = tmp_path / "bridge.db"
    _write_bridge_db(bridge_db, activity_rows=[("o2-fable-runpack", None)])
    result = lint_operator_os_seams(
        truth_path=truth, markdown_paths=markdown, bridge_db_path=bridge_db, now=NOW
    )
    assert result.passed, [f.detail for f in result.findings]


def test_identity_resolution_repo_less_truth_project_resolves(tmp_path: Path) -> None:
    # A repo-less project discovered by the auditor (no remote) resolves via its
    # supp:<project_key> key rather than flagging as a minted dialect.
    truth, markdown = _passing_paths(tmp_path)
    _write_truth(
        truth,
        projects=[
            {
                "identity": {
                    "project_key": "continuity",
                    "display_name": "continuity",
                    "repo_full_name": None,
                }
            },
        ],
    )
    bridge_db = tmp_path / "bridge.db"
    _write_bridge_db(bridge_db, activity_rows=[("continuity", "supp:continuity")])
    result = lint_operator_os_seams(
        truth_path=truth, markdown_paths=markdown, bridge_db_path=bridge_db, now=NOW
    )
    assert result.passed, [f.detail for f in result.findings]


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


def test_identity_resolution_notion_projection_only_rows_pass(tmp_path: Path) -> None:
    # Notion projection-only rows are intentionally not portfolio projects and
    # must not flag as minted dialects.
    truth, markdown = _passing_paths(tmp_path)
    _write_identity_truth(truth)
    notion_snapshot = tmp_path / "notion.json"
    _write_notion_snapshot(notion_snapshot, ["app", "RAG Knowledge Base"])
    result = lint_operator_os_seams(
        truth_path=truth,
        markdown_paths=markdown,
        notion_snapshot_path=notion_snapshot,
        now=NOW,
    )
    assert result.passed, [f.detail for f in result.findings]


def test_identity_resolution_notion_title_alias_resolves(tmp_path: Path) -> None:
    # A Notion title variant resolves to its real project via the title-alias map.
    truth, markdown = _passing_paths(tmp_path)
    _write_truth(
        truth,
        projects=[
            {
                "identity": {
                    "project_key": "OrbitForge",
                    "display_name": "OrbitForge",
                    "repo_full_name": "saagpatel/OrbitForge",
                }
            },
        ],
    )
    notion_snapshot = tmp_path / "notion.json"
    _write_notion_snapshot(notion_snapshot, ["OrbitForge (staging)"])
    result = lint_operator_os_seams(
        truth_path=truth,
        markdown_paths=markdown,
        notion_snapshot_path=notion_snapshot,
        now=NOW,
    )
    assert result.passed, [f.detail for f in result.findings]


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


def test_identity_resolution_since_ignores_old_timestamped_rows(tmp_path: Path) -> None:
    truth, markdown = _passing_paths(tmp_path)
    _write_identity_truth(truth)
    bridge_db = tmp_path / "bridge.db"
    notification_db = tmp_path / "notification.sqlite3"
    _write_bridge_db(
        bridge_db,
        activity_rows=[
            ("old-minted-bridge", None, "2026-07-03T11:59:00Z"),
        ],
        session_cost_rows=[
            ("085", "2026-07-03T11:59:00+00:00"),
        ],
    )
    _write_notification_db(
        notification_db,
        ["old-minted-notification"],
        created_at="2026-07-03T11:59:00+00:00",
    )

    result = lint_operator_os_seams(
        truth_path=truth,
        markdown_paths=markdown,
        bridge_db_path=bridge_db,
        notification_db_path=notification_db,
        identity_since=datetime(2026, 7, 3, 12, 0, tzinfo=UTC),
        now=NOW,
    )

    assert result.passed


def test_identity_resolution_since_skips_untimestamped_notion_snapshot(
    tmp_path: Path,
) -> None:
    truth, markdown = _passing_paths(tmp_path)
    _write_identity_truth(truth)
    notion_snapshot = tmp_path / "notion.json"
    _write_notion_snapshot(notion_snapshot, ["new-minted-non-windowable-row"])

    result = lint_operator_os_seams(
        truth_path=truth,
        markdown_paths=markdown,
        notion_snapshot_path=notion_snapshot,
        identity_since=datetime(2026, 7, 3, 12, 0, tzinfo=UTC),
        now=NOW,
    )

    assert result.passed


def test_identity_resolution_since_includes_new_timestamped_rows(tmp_path: Path) -> None:
    truth, markdown = _passing_paths(tmp_path)
    _write_identity_truth(truth)
    bridge_db = tmp_path / "bridge.db"
    notification_db = tmp_path / "notification.sqlite3"
    _write_bridge_db(
        bridge_db,
        activity_rows=[
            ("old-minted-bridge", None, "2026-07-03T11:59:00Z"),
            ("new-minted-bridge", None, "2026-07-03T12:00:00Z"),
        ],
        session_cost_rows=[
            ("085", "2026-07-03T11:59:00+00:00"),
            ("08f", "2026-07-03T12:00:00+00:00"),
        ],
    )
    _write_notification_db(
        notification_db,
        ["new-minted-notification"],
        created_at="2026-07-03T12:00:01+00:00",
    )

    result = lint_operator_os_seams(
        truth_path=truth,
        markdown_paths=markdown,
        bridge_db_path=bridge_db,
        notification_db_path=notification_db,
        identity_since=datetime(2026, 7, 3, 12, 0, tzinfo=UTC),
        now=NOW,
    )

    assert not result.passed
    assert [finding.violation for finding in result.findings] == [
        "minted identity dialect",
        "minted identity dialect",
        "silent unresolved identity",
    ]
    details = "\n".join(finding.detail for finding in result.findings)
    assert "new-minted-bridge" in details
    assert "new-minted-notification" in details
    assert "old-minted-bridge" not in details
    assert "085" not in details


def test_cli_identity_resolution_is_opt_in(tmp_path: Path) -> None:
    truth, markdown = _passing_paths(tmp_path)
    _refresh_truth_for_cli(truth)
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


def test_cli_identity_since_filters_timestamped_identity_rows(tmp_path: Path) -> None:
    truth, markdown = _passing_paths(tmp_path)
    _write_identity_truth(truth)
    _refresh_truth_for_cli(truth)
    bridge_db = tmp_path / "bridge.db"
    notification_db = tmp_path / "notification.sqlite3"
    notion_snapshot = tmp_path / "notion.json"
    _write_bridge_db(
        bridge_db,
        session_cost_rows=[
            ("085", "2026-07-03T11:59:00Z"),
        ],
    )

    code = main(
        [
            "--truth",
            str(truth),
            "--markdown",
            str(markdown[0]),
            "--markdown",
            str(markdown[1]),
            "--identity-resolution",
            "--identity-since",
            "2026-07-03T12:00:00Z",
            "--bridge-db",
            str(bridge_db),
            "--notification-db",
            str(notification_db),
            "--notion-snapshot",
            str(notion_snapshot),
            "--json",
        ]
    )

    assert code == 0


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
