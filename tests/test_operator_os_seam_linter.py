from __future__ import annotations

import json
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
) -> None:
    payload = {
        "generated_at": generated_at,
        "projects": [],
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
