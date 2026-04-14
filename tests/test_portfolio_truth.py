from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.cli import main
from src.portfolio_context_recovery import (
    apply_context_recovery_plan,
    build_context_recovery_plan,
)
from src.portfolio_truth_publish import publish_portfolio_truth
from src.portfolio_truth_reconcile import build_portfolio_truth_snapshot
from src.portfolio_truth_render import render_registry_markdown
from src.portfolio_truth_sources import _classify_context_quality
from src.registry_parser import parse_registry


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _set_mtime(path: Path, timestamp: float) -> None:
    path.touch()
    path.chmod(0o644)
    import os

    os.utime(path, (timestamp, timestamp))


@pytest.fixture
def portfolio_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    alpha = workspace / "Alpha"
    alpha.mkdir()
    _write(
        alpha / "README.md",
        "# Alpha\n\nAlpha root project.\n",
    )
    _write(
        alpha / "CLAUDE.md",
        """# Alpha Context

## What This Project Is

Alpha is a root-level product repo used to test the portfolio truth contract.

## Current State

Alpha is the strongest fixture in this test workspace and should classify above minimum-viable.

## Stack

Next.js, React, and TypeScript.

## How To Run

Install dependencies with `npm install` and run local development with `npm run dev`.

## Known Risks

This fixture only models the recovery contract and not a real product handoff.

## Next Recommended Move

Keep the supporting handoff artifacts in sync with the primary context file.
""",
    )
    _write(alpha / "DISCOVERY-SUMMARY.md", "# Discovery\n")
    _write(alpha / "HANDOFF.md", "# Handoff\n")
    _write(alpha / "package.json", '{"dependencies":{"next":"14.2.0","react":"19.0.0","typescript":"5.0.0"}}')
    _set_mtime(alpha / "README.md", 1_700_000_000)

    beta = workspace / "ITPRJsViaClaude" / "Beta"
    beta.mkdir(parents=True)
    _write(beta / "AGENTS.md", "# AGENTS\n\ncodex-os baseline\n")
    _write(beta / "Cargo.toml", "[package]\nname = \"beta\"\n")
    _set_mtime(beta / "AGENTS.md", 1_696_000_000)
    _set_mtime(beta / "Cargo.toml", 1_696_000_000)

    gamma = workspace / "Calibrate"
    gamma.mkdir()
    _write(gamma / "Package.swift", "// swift package\n")
    _set_mtime(gamma / "Package.swift", 1_700_100_000)

    return workspace


@pytest.fixture
def portfolio_catalog(tmp_path: Path) -> Path:
    path = tmp_path / "portfolio-catalog.yaml"
    path.write_text(
        """
defaults:
  lifecycle_state: maintenance
  criticality: medium
  review_cadence: monthly
  category: vanity
  tool_provenance: unknown

groups:
  it:
    section_marker: ITPRJsViaClaude/
    section_label: IT Tools
    path_prefixes:
      - ITPRJsViaClaude
    category: it-work
    tool_provenance: claude-code

repos:
  Alpha:
    owner: d
    lifecycle_state: active
    review_cadence: weekly
    intended_disposition: maintain
    category: commercial
    tool_provenance: claude-code
"""
    )
    return path


@pytest.fixture
def legacy_registry(tmp_path: Path) -> Path:
    path = tmp_path / "project-registry.md"
    path.write_text(
        """
# Project Registry

## Standalone Projects (Root Level)

| Project | Status | Tool | Context Quality | Stack | Context Files | Category | Notes |
|---------|--------|------|-----------------|-------|---------------|----------|-------|
| Alpha | parked | claude-code | standard | Next.js | CLAUDE.md | commercial | Legacy row |

## ITPRJsViaClaude/ (IT Tools — 1 projects)

| Project | Status | Tool | Context Quality | Context Files | Notes |
|---------|--------|------|-----------------|---------------|-------|
| Beta | parked | codex | boilerplate | AGENTS.md | Legacy beta |
"""
    )
    return path


def test_truth_snapshot_respects_declared_and_derived_fields(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
) -> None:
    now = datetime.fromtimestamp(1_700_200_000, tz=timezone.utc)
    result = build_portfolio_truth_snapshot(
        workspace_root=portfolio_workspace,
        catalog_path=portfolio_catalog,
        legacy_registry_path=legacy_registry,
        include_notion=False,
        now=now,
    )

    projects = {project.identity.display_name: project for project in result.snapshot.projects}
    alpha = projects["Alpha"]
    beta = projects["Beta"]
    gamma = projects["Calibrate"]

    assert alpha.identity.project_key == "Alpha"
    assert alpha.declared.owner == "d"
    assert alpha.declared.category == "commercial"
    assert alpha.derived.context_quality == "full"
    assert alpha.derived.registry_status == "active"
    assert alpha.derived.primary_context_file == "CLAUDE.md"
    assert alpha.derived.project_summary_present is True
    assert alpha.derived.next_recommended_move_present is True

    assert beta.identity.section_marker == "ITPRJsViaClaude/"
    assert beta.declared.category == "it-work"
    assert beta.derived.context_quality == "boilerplate"
    assert beta.derived.registry_status == "parked"

    assert gamma.identity.section_marker == "iOS Projects"
    assert gamma.derived.stack == ["Swift"]


def test_truth_snapshot_matches_repo_contracts_by_full_name(
    portfolio_workspace: Path,
    legacy_registry: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog_path = tmp_path / "portfolio-catalog.yaml"
    catalog_path.write_text(
        """
defaults:
  lifecycle_state: maintenance
  review_cadence: monthly
  category: vanity
  tool_provenance: unknown

repos:
  d/Alpha:
    owner: portfolio-owner
    lifecycle_state: active
    review_cadence: weekly
    intended_disposition: maintain
    category: commercial
    tool_provenance: codex
"""
    )

    def _fake_git_facts(project_path: Path) -> dict[str, object]:
        if project_path.name == "Alpha":
            return {
                "has_git": True,
                "last_commit_at": datetime.fromtimestamp(1_700_100_000, tz=timezone.utc),
                "repo_full_name": "d/Alpha",
            }
        return {"has_git": False, "last_commit_at": None, "repo_full_name": ""}

    monkeypatch.setattr("src.portfolio_truth_sources._gather_git_facts", _fake_git_facts)

    result = build_portfolio_truth_snapshot(
        workspace_root=portfolio_workspace,
        catalog_path=catalog_path,
        legacy_registry_path=legacy_registry,
        include_notion=False,
        now=datetime.fromtimestamp(1_700_200_000, tz=timezone.utc),
    )

    alpha = next(project for project in result.snapshot.projects if project.identity.display_name == "Alpha")
    assert alpha.declared.owner == "portfolio-owner"
    assert alpha.declared.review_cadence == "weekly"
    assert alpha.declared.category == "commercial"
    assert alpha.provenance["declared.owner"]["source"] == "catalog_repo"


def test_agent_file_without_real_project_markers_stays_boilerplate(tmp_path: Path) -> None:
    project = tmp_path / "WeakContext"
    project.mkdir()
    _write(project / "AGENTS.md", "# AGENTS\n\nProject specific rules.\n")

    assert _classify_context_quality(project, ["AGENTS.md"]) == "boilerplate"


def test_primary_context_with_required_sections_becomes_minimum_viable(tmp_path: Path) -> None:
    project = tmp_path / "MinimumViable"
    project.mkdir()
    _write(
        project / "AGENTS.md",
        """# Portfolio Context

## What This Project Is

MinimumViable is a local fixture used to verify the new context contract.

## Current State

This fixture exists only to exercise the minimum-viable band.

## Stack

Python plus a tiny CLI entrypoint.

## How To Run

Use `python3 runner.py` to execute the local task flow.

## Known Risks

This fixture is intentionally small and does not model a full handoff package.

## Next Recommended Move

Promote it to standard by adding a supporting handoff document.
""",
    )

    assert _classify_context_quality(project, ["AGENTS.md"]) == "minimum-viable"


def test_rendered_registry_round_trips_through_parser(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
    tmp_path: Path,
) -> None:
    result = build_portfolio_truth_snapshot(
        workspace_root=portfolio_workspace,
        catalog_path=portfolio_catalog,
        legacy_registry_path=legacy_registry,
        include_notion=False,
    )
    markdown = render_registry_markdown(result.snapshot)
    registry_path = tmp_path / "generated-registry.md"
    registry_path.write_text(markdown)

    parsed = parse_registry(registry_path)
    assert len(parsed) == len(result.snapshot.projects)
    assert parsed["Alpha"] in {"active", "recent", "parked", "archived"}
    assert "## Portfolio Summary" in markdown
    assert "## Cowork Task Notes" in markdown


def test_duplicate_display_names_are_disambiguated_in_registry(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    orbit_a = workspace / "Arcade" / "OrbitForge"
    orbit_b = workspace / "Labs" / "OrbitForge"
    orbit_a.mkdir(parents=True)
    orbit_b.mkdir(parents=True)
    _write(orbit_a / "README.md", "# OrbitForge A\n")
    _write(orbit_b / "README.md", "# OrbitForge B\n")

    catalog_path = tmp_path / "portfolio-catalog.yaml"
    catalog_path.write_text(
        """
groups:
  arcade:
    section_marker: Arcade/
    section_label: Arcade
    path_prefixes:
      - Arcade
  labs:
    section_marker: Labs/
    section_label: Labs
    path_prefixes:
      - Labs
"""
    )

    result = build_portfolio_truth_snapshot(
        workspace_root=workspace,
        catalog_path=catalog_path,
        include_notion=False,
    )
    markdown = render_registry_markdown(result.snapshot)
    registry_path = tmp_path / "generated-registry.md"
    registry_path.write_text(markdown)

    parsed = parse_registry(registry_path)
    assert len(parsed) == 2
    assert "OrbitForge [Arcade/OrbitForge]" in parsed
    assert "OrbitForge [Labs/OrbitForge]" in parsed


def test_publish_is_noop_for_unchanged_compatibility_outputs(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "output"
    registry_output = portfolio_workspace / "project-registry.md"
    report_output = portfolio_workspace / "PORTFOLIO-AUDIT-REPORT.md"

    first = publish_portfolio_truth(
        workspace_root=portfolio_workspace,
        output_dir=output_dir,
        registry_output=registry_output,
        portfolio_report_output=report_output,
        catalog_path=portfolio_catalog,
        legacy_registry_path=legacy_registry,
        include_notion=False,
    )
    registry_mtime = registry_output.stat().st_mtime_ns
    report_mtime = report_output.stat().st_mtime_ns
    time.sleep(0.01)
    second = publish_portfolio_truth(
        workspace_root=portfolio_workspace,
        output_dir=output_dir,
        registry_output=registry_output,
        portfolio_report_output=report_output,
        catalog_path=portfolio_catalog,
        legacy_registry_path=legacy_registry,
        include_notion=False,
    )

    assert first.registry_changed is True
    assert first.report_changed is True
    assert second.registry_changed is False
    assert second.report_changed is False
    assert registry_output.stat().st_mtime_ns == registry_mtime
    assert report_output.stat().st_mtime_ns == report_mtime


def test_publish_failure_leaves_live_files_untouched(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "output"
    registry_output = portfolio_workspace / "project-registry.md"
    report_output = portfolio_workspace / "PORTFOLIO-AUDIT-REPORT.md"
    registry_output.write_text("sentinel-registry\n")
    report_output.write_text("sentinel-report\n")

    def _boom(_snapshot, _latest_json_path):
        raise RuntimeError("renderer exploded")

    monkeypatch.setattr("src.portfolio_truth_publish.render_portfolio_report_markdown", _boom)

    with pytest.raises(RuntimeError):
        publish_portfolio_truth(
            workspace_root=portfolio_workspace,
            output_dir=output_dir,
            registry_output=registry_output,
            portfolio_report_output=report_output,
            catalog_path=portfolio_catalog,
            legacy_registry_path=legacy_registry,
            include_notion=False,
        )

    assert registry_output.read_text() == "sentinel-registry\n"
    assert report_output.read_text() == "sentinel-report\n"
    assert not list(output_dir.glob("*.tmp"))


def test_context_recovery_plan_freezes_and_filters_targets(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
) -> None:
    active_repo = portfolio_workspace / "Fresh"
    active_repo.mkdir()
    _write(active_repo / "README.md", "# Fresh\n\nFresh repo.\n")
    _write(active_repo / "package.json", '{"dependencies":{"react":"19.0.0"}}')

    scaffold_repo = portfolio_workspace / "tmp-scaffold"
    scaffold_repo.mkdir()
    _write(scaffold_repo / "README.md", "# Scaffold\n")

    result = build_portfolio_truth_snapshot(
        workspace_root=portfolio_workspace,
        catalog_path=portfolio_catalog,
        legacy_registry_path=legacy_registry,
        include_notion=False,
        now=datetime.fromtimestamp(1_700_000_100, tz=timezone.utc),
    )
    plan = build_context_recovery_plan(result.snapshot, workspace_root=portfolio_workspace)
    targets = {target.project_key: target for target in plan.projects}

    assert targets["Fresh"].status == "eligible"
    assert targets["tmp-scaffold"].status == "excluded"
    assert targets["tmp-scaffold"].reason == "temporary-or-generated"


def test_context_recovery_apply_writes_primary_context_and_catalog_seed(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
) -> None:
    target_repo = portfolio_workspace / "FreshRecover"
    target_repo.mkdir()
    _write(target_repo / "README.md", "# FreshRecover\n\nFreshRecover is a small active repo.\n")
    _write(target_repo / "package.json", '{"dependencies":{"next":"14.2.0","react":"19.0.0"}}')

    result = build_portfolio_truth_snapshot(
        workspace_root=portfolio_workspace,
        catalog_path=portfolio_catalog,
        legacy_registry_path=legacy_registry,
        include_notion=False,
        now=datetime.fromtimestamp(1_700_000_100, tz=timezone.utc),
    )
    plan = build_context_recovery_plan(result.snapshot, workspace_root=portfolio_workspace)
    apply_result = apply_context_recovery_plan(
        result.snapshot,
        plan,
        workspace_root=portfolio_workspace,
        catalog_path=portfolio_catalog,
    )

    assert "FreshRecover" in apply_result.updated_projects
    agents_text = (target_repo / "AGENTS.md").read_text()
    assert "<!-- portfolio-context:start -->" in agents_text
    assert "## What This Project Is" in agents_text
    assert "## Next Recommended Move" in agents_text
    assert "FreshRecover:" in portfolio_catalog.read_text()


def test_cli_portfolio_truth_respects_path_overrides(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "output"
    registry_output = portfolio_workspace / "compat-registry.md"
    report_output = portfolio_workspace / "compat-report.md"
    argv = [
        "audit",
        "testuser",
        "--portfolio-truth",
        "--workspace-root",
        str(portfolio_workspace),
        "--output-dir",
        str(output_dir),
        "--catalog",
        str(portfolio_catalog),
        "--registry",
        str(legacy_registry),
        "--registry-output",
        str(registry_output),
        "--portfolio-report-output",
        str(report_output),
    ]
    monkeypatch.setattr("sys.argv", argv)

    main()

    snapshot_path = output_dir / "portfolio-truth-latest.json"
    assert snapshot_path.exists()
    assert registry_output.exists()
    assert report_output.exists()
    assert legacy_registry.read_text().startswith("\n# Project Registry")
    snapshot = json.loads(snapshot_path.read_text())
    projects = {item["identity"]["project_key"]: item for item in snapshot["projects"]}
    alpha = projects["Alpha"]
    calibrate = projects["Calibrate"]
    assert alpha["declared"]["operating_path"] == "maintain"
    assert alpha["derived"]["path_override"] == ""
    assert alpha["derived"]["path_confidence"] in {"medium", "high"}
    assert calibrate["derived"]["path_override"] == "investigate"


def test_sync_registry_flag_is_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["audit", "testuser", "--sync-registry"])
    with pytest.raises(SystemExit):
        main()


def test_cli_context_recovery_dry_run_does_not_mutate_repo(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "output"
    target_repo = portfolio_workspace / "DryRunRepo"
    target_repo.mkdir()
    _write(target_repo / "README.md", "# DryRunRepo\n\nDry run target.\n")
    _write(target_repo / "package.json", '{"dependencies":{"react":"19.0.0"}}')
    argv = [
        "audit",
        "testuser",
        "--portfolio-context-recovery",
        "--workspace-root",
        str(portfolio_workspace),
        "--output-dir",
        str(output_dir),
        "--catalog",
        str(portfolio_catalog),
        "--registry",
        str(legacy_registry),
    ]
    monkeypatch.setattr("sys.argv", argv)

    main()

    assert list(output_dir.glob("context-recovery-plan-*.json"))
    assert not (target_repo / "AGENTS.md").exists()
