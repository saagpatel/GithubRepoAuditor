from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.cli import main
from src.portfolio_context_recovery import (
    apply_context_recovery_plan,
    build_context_recovery_plan,
)
from src.portfolio_truth_publish import PortfolioTruthPublishError, publish_portfolio_truth
from src.portfolio_truth_reconcile import build_portfolio_truth_snapshot
from src.portfolio_truth_render import (
    render_portfolio_report_markdown,
    render_registry_markdown,
)
from src.portfolio_truth_sources import (
    _classify_context_quality,
    _extract_github_full_name,
    _git_remote_full_name,
    load_safe_notion_project_context,
)
from src.portfolio_truth_validate import validate_portfolio_report_markdown
from src.registry_parser import parse_registry


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _set_mtime(path: Path, timestamp: float) -> None:
    path.touch()
    path.chmod(0o644)
    import os

    os.utime(path, (timestamp, timestamp))


def _security_test_project(
    name: str,
    *,
    critical: int,
    high: int,
    available: bool = True,
    tier: str = "elevated",
):
    """Minimal PortfolioTruthProject for exercising security render helpers directly."""
    from src.portfolio_truth_types import (
        DeclaredFields,
        DerivedFields,
        IdentityFields,
        PortfolioTruthProject,
        RiskFields,
        SecurityFields,
    )

    return PortfolioTruthProject(
        identity=IdentityFields(
            project_key=name,
            display_name=name,
            path=name,
            top_level_dir=name,
            group_key="g",
            group_label="G",
            section_marker="Standalone Projects",
            section_label="Standalone",
            has_git=True,
        ),
        declared=DeclaredFields(),
        derived=DerivedFields(),
        risk=RiskFields(risk_tier=tier),
        security=SecurityFields(
            alerts_available=available,
            dependabot_critical=critical,
            dependabot_high=high,
        ),
    )


def test_extract_github_full_name_uses_exact_github_host() -> None:
    assert _extract_github_full_name("https://github.com/octo/repo.git") == "octo/repo"
    assert _extract_github_full_name("git@github.com:octo/repo.git") == "octo/repo"
    assert _extract_github_full_name("https://evil.example/github.com/octo/repo.git") == ""


def test_git_remote_full_name_prefers_canonical_remote(tmp_path: Path) -> None:
    repo = tmp_path / "GithubRepoAuditor"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        [
            "git",
            "remote",
            "add",
            "origin",
            "https://github.com/saagpatel/GithubRepoAuditor-private-archive-20260518.git",
        ],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "remote",
            "add",
            "canonical",
            "https://github.com/saagpatel/GithubRepoAuditor.git",
        ],
        cwd=repo,
        capture_output=True,
        check=True,
    )

    assert _git_remote_full_name(repo) == "saagpatel/GithubRepoAuditor"


def test_git_remote_full_name_prefers_matching_public_remote_for_archive_origin(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "ApplyKit"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        [
            "git",
            "remote",
            "add",
            "origin",
            "https://github.com/saagpatel/ApplyKit-private-archive-20260517.git",
        ],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "remote",
            "add",
            "legacy-origin",
            "https://github.com/saagpatel/ApplyKit.git",
        ],
        cwd=repo,
        capture_output=True,
        check=True,
    )

    assert _git_remote_full_name(repo) == "saagpatel/ApplyKit"


def test_git_remote_full_name_keeps_normal_origin(tmp_path: Path) -> None:
    repo = tmp_path / "NormalProject"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/saagpatel/NormalProject.git"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "remote", "add", "mirror", "https://github.com/saagpatel/OtherProject.git"],
        cwd=repo,
        capture_output=True,
        check=True,
    )

    assert _git_remote_full_name(repo) == "saagpatel/NormalProject"


def test_notion_context_uses_configured_title_aliases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "project-registry-overrides.json").write_text(
        json.dumps(
            {
                "notion_title_aliases": {
                    "Notion Operating System": "Notion",
                }
            }
        )
    )

    monkeypatch.setattr(
        "src.portfolio_truth_sources.load_notion_project_context",
        lambda _config_dir: {
            "Notion Operating System": {
                "portfolio_call": "Build Now",
                "momentum": "Post-Build Review Done",
                "current_state": "Shipped",
            }
        },
    )

    context = load_safe_notion_project_context(config_dir)

    assert context["notion"]["current_state"] == "Shipped"


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
    _write(
        alpha / "package.json",
        '{"dependencies":{"next":"14.2.0","react":"19.0.0","typescript":"5.0.0"}}',
    )
    _set_mtime(alpha / "README.md", 1_700_000_000)

    beta = workspace / "ITPRJsViaClaude" / "Beta"
    beta.mkdir(parents=True)
    _write(beta / "AGENTS.md", "# AGENTS\n\ncodex-os baseline\n")
    _write(beta / "Cargo.toml", '[package]\nname = "beta"\n')
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
    assert alpha.derived.attention_state == "active-product"
    assert alpha.derived.primary_context_file == "CLAUDE.md"
    assert alpha.derived.project_summary_present is True
    assert alpha.derived.next_recommended_move_present is True
    assert hasattr(alpha.declared, "doctor_standard")
    assert hasattr(alpha.declared, "automation_eligible")
    assert alpha.declared.automation_eligible is False
    assert hasattr(alpha, "risk")
    assert alpha.risk.risk_tier in {"elevated", "moderate", "baseline", "deferred"}

    assert beta.identity.section_marker == "ITPRJsViaClaude/"
    assert beta.declared.category == "it-work"
    assert beta.derived.context_quality == "boilerplate"
    assert beta.derived.registry_status == "parked"
    assert beta.derived.attention_state == "parked"

    assert gamma.identity.section_marker == "iOS Projects"
    assert gamma.derived.stack == ["Swift"]

    assert result.snapshot.schema_version == "0.8.0"
    assert result.snapshot.derivation_policy_version == "portfolio_attention.v2"
    assert result.snapshot.inputs["catalog"]["sha256"]
    assert result.snapshot.inputs["notion"]["mode"] == "unavailable"
    assert result.snapshot.source_summary["attention_state_counts"]["active-product"] == 1
    assert result.snapshot.source_summary["attention_state_counts"]["parked"] == 1

    # Derived rollups are emitted so downstream consumers (command-center) read
    # them instead of re-deriving the auditor's risk/security logic.
    snapshot_dict = result.snapshot.to_dict()
    rollups = snapshot_dict["rollups"]
    assert set(rollups["risk_tier_counts"]) == {"elevated", "moderate", "baseline", "deferred"}
    assert sum(rollups["risk_tier_counts"].values()) == len(result.snapshot.projects)
    assert set(rollups["security"]) == {
        "scanned_count",
        "repos_with_open_high_critical",
        "total_open_high",
        "total_open_critical",
    }
    assert set(rollups["decision"]) == {"decision_needed_count", "default_attention_count"}
    assert (
        rollups["decision"]["default_attention_count"]
        >= rollups["decision"]["decision_needed_count"]
    )
    # Per-project open_high_critical is emitted in the security block.
    assert "open_high_critical" in snapshot_dict["projects"][0]["security"]


def test_attention_state_classifier_separates_activity_from_operator_attention() -> None:
    from src.portfolio_truth_reconcile import _attention_state_for

    assert (
        _attention_state_for(
            registry_status="active",
            lifecycle_state="active",
            operating_path="maintain",
            intended_disposition="maintain",
            category="commercial",
            path_override="",
            risk_entry={"security_risk": False},
        )
        == "active-product"
    )
    assert (
        _attention_state_for(
            registry_status="active",
            lifecycle_state="active",
            operating_path="maintain",
            intended_disposition="maintain",
            category="infrastructure",
            path_override="",
            risk_entry={"security_risk": False},
        )
        == "active-infra"
    )
    assert (
        _attention_state_for(
            registry_status="active",
            lifecycle_state="active",
            operating_path="maintain",
            intended_disposition="maintain",
            category="vanity",
            path_override="investigate",
            risk_entry={"security_risk": False},
        )
        == "decision-needed"
    )
    assert (
        _attention_state_for(
            registry_status="active",
            lifecycle_state="active",
            operating_path="maintain",
            intended_disposition="maintain",
            category="fun",
            path_override="",
            risk_entry={"security_risk": False},
        )
        == "manual-only"
    )
    assert (
        _attention_state_for(
            registry_status="active",
            lifecycle_state="active",
            operating_path="experiment",
            intended_disposition="experiment",
            category="vanity",
            path_override="investigate",
            risk_entry={"security_risk": True},
        )
        == "experiment"
    )
    assert (
        _attention_state_for(
            registry_status="archived",
            lifecycle_state="archived",
            operating_path="archive",
            intended_disposition="archive",
            category="commercial",
            path_override="investigate",
            risk_entry={"security_risk": True},
        )
        == "archived"
    )


def test_github_archived_status_reconciles_to_archived_attention(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
) -> None:
    now = datetime.fromtimestamp(1_700_200_000, tz=timezone.utc)
    baseline = build_portfolio_truth_snapshot(
        workspace_root=portfolio_workspace,
        catalog_path=portfolio_catalog,
        legacy_registry_path=legacy_registry,
        include_notion=False,
        now=now,
    )
    result = build_portfolio_truth_snapshot(
        workspace_root=portfolio_workspace,
        catalog_path=portfolio_catalog,
        legacy_registry_path=legacy_registry,
        include_notion=False,
        now=now,
        repo_status_by_name={
            "Alpha": {
                "full_name": "d/Alpha",
                "archived": True,
            }
        },
    )

    projects = {project.identity.display_name: project for project in result.snapshot.projects}
    alpha = projects["Alpha"]

    assert alpha.declared.lifecycle_state == "active"
    assert alpha.declared.operating_path == "maintain"
    assert alpha.derived.path_confidence == "low"
    assert alpha.derived.activity_status == "archived"
    assert alpha.derived.registry_status == "archived"
    assert alpha.derived.attention_state == "archived"
    assert alpha.provenance["github.archived"] == {
        "source": "audit_report",
        "detail": "true",
    }
    assert result.snapshot.source_summary["github_archived_count"] == 1
    assert baseline.snapshot.source_summary["attention_state_counts"]["active-product"] == 1
    assert result.snapshot.source_summary["attention_state_counts"].get("active-product", 0) == 0
    assert result.snapshot.source_summary["attention_state_counts"].get(
        "decision-needed", 0
    ) == baseline.snapshot.source_summary["attention_state_counts"].get("decision-needed", 0)


def test_build_security_fields_maps_ghas_entry() -> None:
    from src.portfolio_truth_reconcile import _build_security_fields

    fields = _build_security_fields(
        {
            "dependabot": {"critical": 2, "high": 3, "medium": 4, "low": 5, "available": True},
            "code_scanning": {"critical": 1, "high": 6, "available": True},
            "secret_scanning": {"open": 7, "available": True},
        }
    )
    assert fields.alerts_available is True
    assert fields.dependabot_critical == 2
    assert fields.dependabot_high == 3
    assert fields.dependabot_medium == 4
    assert fields.dependabot_low == 5
    assert fields.code_scanning_critical == 1
    assert fields.code_scanning_high == 6
    assert fields.secret_scanning_open == 7
    assert fields.open_high_critical == 5


def test_build_security_fields_none_is_unscanned() -> None:
    from src.portfolio_truth_reconcile import _build_security_fields

    fields = _build_security_fields(None)
    assert fields.alerts_available is False
    assert fields.open_high_critical == 0
    assert fields.dependabot_critical == 0


def test_build_security_fields_unavailable_dependabot_is_not_available() -> None:
    from src.portfolio_truth_reconcile import _build_security_fields

    fields = _build_security_fields(
        {"dependabot": {"available": False}, "secret_scanning": {"open": 0, "available": False}}
    )
    assert fields.alerts_available is False
    assert fields.dependabot_high == 0


def test_build_security_fields_scanned_clean_is_available_with_zero_counts() -> None:
    # A repo whose Dependabot scan succeeded with zero open alerts must read as
    # scanned-and-clean (available=True), distinct from an unscanned repo.
    from src.portfolio_truth_reconcile import _build_security_fields

    fields = _build_security_fields({"dependabot": {"available": True}})
    assert fields.alerts_available is True
    assert fields.dependabot_high == 0
    assert fields.dependabot_critical == 0
    assert fields.open_high_critical == 0


def test_security_overlay_populates_and_force_elevates(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
) -> None:
    now = datetime.fromtimestamp(1_700_200_000, tz=timezone.utc)
    security = {
        "Alpha": {
            "dependabot": {"critical": 1, "high": 0, "medium": 0, "low": 2, "available": True},
            "code_scanning": {"critical": 0, "high": 0, "available": True},
            "secret_scanning": {"open": 0, "available": True},
        }
    }
    result = build_portfolio_truth_snapshot(
        workspace_root=portfolio_workspace,
        catalog_path=portfolio_catalog,
        legacy_registry_path=legacy_registry,
        include_notion=False,
        now=now,
        security_alerts_by_name=security,
    )
    projects = {p.identity.display_name: p for p in result.snapshot.projects}
    alpha = projects["Alpha"]
    assert alpha.security.alerts_available is True
    assert alpha.security.dependabot_critical == 1
    assert alpha.risk.security_risk is True
    assert alpha.risk.risk_tier == "elevated"
    assert "active-high-severity-alerts" in alpha.risk.risk_factors

    # A repo with no security entry stays unscanned (overlay is strictly opt-in).
    calibrate = projects["Calibrate"]
    assert calibrate.security.alerts_available is False
    assert calibrate.security.dependabot_critical == 0
    assert calibrate.risk.security_risk is False

    # Serialized snapshot carries the security block.
    alpha_dict = alpha.to_dict()
    assert "security" in alpha_dict
    assert alpha_dict["security"]["dependabot_critical"] == 1


def test_security_overlay_absent_leaves_repos_unscanned(
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
    for project in result.snapshot.projects:
        assert project.security.alerts_available is False
        assert project.security.open_high_critical == 0
        assert project.risk.security_risk is False


def test_select_security_entry_joins_by_repo_name_when_display_differs() -> None:
    # GHAS is keyed by repo name ("signal-noise"); the local dir is "Signal & Noise".
    from src.portfolio_truth_reconcile import _select_security_entry

    entry = {"dependabot": {"high": 9, "available": True}}
    lookup = {"signal-noise": entry}
    assert _select_security_entry(lookup, "saagpatel/signal-noise", "Signal & Noise") is entry


def test_select_security_entry_falls_back_to_display_name() -> None:
    from src.portfolio_truth_reconcile import _select_security_entry

    entry = {"dependabot": {"high": 1, "available": True}}
    # No repo_full_name (local-only repo) → must fall back to display_name.
    assert _select_security_entry({"Alpha": entry}, None, "Alpha") is entry


def test_select_security_entry_prefers_repo_name_over_display() -> None:
    from src.portfolio_truth_reconcile import _select_security_entry

    by_repo = {"dependabot": {"high": 2, "available": True}}
    by_display = {"dependabot": {"high": 5, "available": True}}
    lookup = {"the-repo": by_repo, "DisplayName": by_display}
    assert _select_security_entry(lookup, "owner/the-repo", "DisplayName") is by_repo


def test_select_security_entry_returns_none_when_unmatched() -> None:
    from src.portfolio_truth_reconcile import _select_security_entry

    assert _select_security_entry({"other": {}}, "owner/missing", "AlsoMissing") is None


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

    alpha = next(
        project for project in result.snapshot.projects if project.identity.display_name == "Alpha"
    )
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


def _complete_agent_context(project_name: str) -> str:
    return f"""# {project_name}

## What This Project Is

{project_name} is local infrastructure used to coordinate operator workflows.

## Current State

Active and maintained, with the core workflow already running locally.

## Stack

Python, shell scripts, and local JSON artifacts.

## How To Run

Run `pytest tests` before publishing changes.

## Known Risks

Local paths and machine-specific dependencies can drift.

## Next Recommended Move

Keep the verification surface green and refresh context when workflows change.
"""


def _substantive_readme(project_name: str) -> str:
    return (
        f"# {project_name}\n\n"
        f"{project_name} is a durable operator infrastructure repo with separate "
        "agent guidance and README-level workflow documentation.\n\n"
        + ("It documents commands, boundaries, recovery paths, examples, and operator usage. " * 35)
    )


def test_catalog_backed_high_criticality_infra_readme_support_promotes_to_standard(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project = workspace / "InfraRepo"
    project.mkdir()
    subprocess.run(["git", "init"], cwd=project, capture_output=True, check=True)
    _write(project / "AGENTS.md", _complete_agent_context("InfraRepo"))
    _write(project / "README.md", _substantive_readme("InfraRepo"))
    _write(project / "pyproject.toml", "[project]\nname = \"infra-repo\"\n")
    catalog_path = tmp_path / "portfolio-catalog.yaml"
    catalog_path.write_text(
        """
repos:
  InfraRepo:
    owner: d
    lifecycle_state: active
    criticality: high
    review_cadence: weekly
    intended_disposition: maintain
    category: infrastructure
"""
    )

    result = build_portfolio_truth_snapshot(
        workspace_root=workspace,
        catalog_path=catalog_path,
        include_notion=False,
    )

    infra = next(project for project in result.snapshot.projects if project.identity.project_key == "InfraRepo")
    assert infra.derived.context_quality == "standard"
    assert infra.provenance["derived.context_quality"]["source"] == "workspace+catalog"
    assert infra.provenance["derived.context_quality"]["detail"] == "minimum-viable->standard"


def test_substantive_readme_support_does_not_promote_non_infra_repo(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project = workspace / "ProductRepo"
    project.mkdir()
    subprocess.run(["git", "init"], cwd=project, capture_output=True, check=True)
    _write(project / "AGENTS.md", _complete_agent_context("ProductRepo"))
    _write(project / "README.md", _substantive_readme("ProductRepo"))
    _write(project / "package.json", '{"dependencies":{"react":"19.0.0"}}')
    catalog_path = tmp_path / "portfolio-catalog.yaml"
    catalog_path.write_text(
        """
repos:
  ProductRepo:
    owner: d
    lifecycle_state: active
    criticality: high
    review_cadence: weekly
    intended_disposition: maintain
    category: commercial
"""
    )

    result = build_portfolio_truth_snapshot(
        workspace_root=workspace,
        catalog_path=catalog_path,
        include_notion=False,
    )

    product = next(
        project for project in result.snapshot.projects if project.identity.project_key == "ProductRepo"
    )
    assert product.derived.context_quality == "minimum-viable"
    assert product.provenance["derived.context_quality"]["source"] == "workspace"


def test_legacy_registry_infra_category_does_not_promote_context_quality(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project = workspace / "LegacyInfra"
    project.mkdir()
    subprocess.run(["git", "init"], cwd=project, capture_output=True, check=True)
    _write(project / "AGENTS.md", _complete_agent_context("LegacyInfra"))
    _write(project / "README.md", _substantive_readme("LegacyInfra"))
    _write(project / "pyproject.toml", "[project]\nname = \"legacy-infra\"\n")
    catalog_path = tmp_path / "portfolio-catalog.yaml"
    catalog_path.write_text(
        """
repos:
  LegacyInfra:
    owner: d
    lifecycle_state: active
    criticality: high
    review_cadence: weekly
    intended_disposition: maintain
"""
    )
    legacy_registry_path = tmp_path / "project-registry.md"
    legacy_registry_path.write_text(
        """
# Project Registry

## Standalone Projects

| Project | Status | Tool | Context Quality | Stack | Context Files | Category | Notes |
|---------|--------|------|-----------------|-------|---------------|----------|-------|
| LegacyInfra | active | codex | minimum-viable | Python | AGENTS.md | infrastructure | legacy category only |
"""
    )

    result = build_portfolio_truth_snapshot(
        workspace_root=workspace,
        catalog_path=catalog_path,
        legacy_registry_path=legacy_registry_path,
        include_notion=False,
    )

    infra = next(
        project for project in result.snapshot.projects if project.identity.project_key == "LegacyInfra"
    )
    assert infra.declared.category == "infrastructure"
    assert infra.provenance["declared.category"]["source"] == "legacy_registry"
    assert infra.derived.context_quality == "minimum-viable"
    assert infra.provenance["derived.context_quality"]["source"] == "workspace"


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


def test_registry_render_surfaces_security_and_round_trips(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
    tmp_path: Path,
) -> None:
    security = {
        "Alpha": {
            "dependabot": {"critical": 2, "high": 1, "medium": 0, "low": 0, "available": True},
            "code_scanning": {"available": True},
            "secret_scanning": {"open": 0, "available": True},
        }
    }
    result = build_portfolio_truth_snapshot(
        workspace_root=portfolio_workspace,
        catalog_path=portfolio_catalog,
        legacy_registry_path=legacy_registry,
        include_notion=False,
        security_alerts_by_name=security,
    )
    markdown = render_registry_markdown(result.snapshot)

    # Per-repo Notes flag fires for the scanned repo carrying open high/critical alerts.
    assert "[security: 2 critical / 1 high open Dependabot alerts]" in markdown
    # Aggregate rows land in the Portfolio Summary table.
    assert "| Repos scanned for security alerts | 1 |" in markdown
    assert "| Repos with open high/critical alerts | 1 |" in markdown
    assert "| Open critical Dependabot alerts | 2 |" in markdown
    assert "| Open high Dependabot alerts | 1 |" in markdown

    # The security flag is pipe-free + digit summary rows, so the parser round-trip is
    # unchanged: same project row count, no inflation from the new content.
    registry_path = tmp_path / "generated-registry.md"
    registry_path.write_text(markdown)
    parsed = parse_registry(registry_path)
    assert len(parsed) == len(result.snapshot.projects)


def test_registry_render_omits_security_flag_when_unscanned(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
) -> None:
    result = build_portfolio_truth_snapshot(
        workspace_root=portfolio_workspace,
        catalog_path=portfolio_catalog,
        legacy_registry_path=legacy_registry,
        include_notion=False,
    )
    markdown = render_registry_markdown(result.snapshot)
    assert "[security:" not in markdown
    # Summary rows stay present, all zero, documenting that the overlay was not run.
    assert "| Repos scanned for security alerts | 0 |" in markdown
    assert "| Repos with open high/critical alerts | 0 |" in markdown


def test_portfolio_report_security_posture_lists_open_alerts(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
) -> None:
    security = {
        "Alpha": {
            "dependabot": {"critical": 1, "high": 2, "medium": 0, "low": 0, "available": True},
            "code_scanning": {"available": True},
            "secret_scanning": {"open": 0, "available": True},
        }
    }
    result = build_portfolio_truth_snapshot(
        workspace_root=portfolio_workspace,
        catalog_path=portfolio_catalog,
        legacy_registry_path=legacy_registry,
        include_notion=False,
        security_alerts_by_name=security,
    )
    markdown = render_portfolio_report_markdown(result.snapshot, "output/x.json")

    assert "## Security Posture" in markdown
    assert "[Security Posture](#security-posture)" in markdown
    assert "- **Alpha** [elevated]: 1 critical, 2 high open Dependabot alerts" in markdown
    assert (
        "- Security posture: scanned `1`, with open high/critical Dependabot alerts `1`" in markdown
    )
    # The new section keeps the report validator green.
    validate_portfolio_report_markdown(markdown)


def test_portfolio_report_security_posture_scanned_clear(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
) -> None:
    # Scanned with zero open high/critical reads as "all clear", distinct from "not run".
    security = {
        "Alpha": {
            "dependabot": {"critical": 0, "high": 0, "medium": 3, "low": 0, "available": True},
            "code_scanning": {"available": True},
            "secret_scanning": {"open": 0, "available": True},
        }
    }
    result = build_portfolio_truth_snapshot(
        workspace_root=portfolio_workspace,
        catalog_path=portfolio_catalog,
        legacy_registry_path=legacy_registry,
        include_notion=False,
        security_alerts_by_name=security,
    )
    markdown = render_portfolio_report_markdown(result.snapshot, "output/x.json")
    assert "All 1 scanned repos are clear of open high/critical Dependabot alerts." in markdown
    validate_portfolio_report_markdown(markdown)

    # Same guard governs the registry: a scanned repo with only medium alerts gets no
    # per-repo flag, but it still counts as scanned in the summary table.
    registry_md = render_registry_markdown(result.snapshot)
    assert "[security:" not in registry_md
    assert "| Repos scanned for security alerts | 1 |" in registry_md
    assert "| Repos with open high/critical alerts | 0 |" in registry_md


def test_security_attention_items_caps_at_five_and_sorts_critical_first() -> None:
    from src.portfolio_truth_render import (
        MAX_SECURITY_ATTENTION_ITEMS,
        _security_attention_items,
    )

    projects = [
        _security_test_project("low-high", critical=0, high=1),
        _security_test_project("mid-crit", critical=2, high=0),
        _security_test_project("top-crit", critical=5, high=0),
        _security_test_project("clean", critical=0, high=0),  # excluded: nothing open
        _security_test_project("unscanned", critical=9, high=9, available=False),  # excluded
        _security_test_project("a-high", critical=0, high=3),
        _security_test_project("b-high", critical=0, high=3),
        _security_test_project("c-crit", critical=1, high=0),
    ]
    items = _security_attention_items(projects)

    # clean + unscanned drop out; six remain but the list is capped.
    assert len(items) == MAX_SECURITY_ATTENTION_ITEMS
    names = [project.identity.display_name for project in items]
    # critical desc, then high desc, then name asc — and the capped tail (low-high) falls off.
    assert names == ["top-crit", "mid-crit", "c-crit", "a-high", "b-high"]


def test_portfolio_report_security_posture_not_run(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
) -> None:
    result = build_portfolio_truth_snapshot(
        workspace_root=portfolio_workspace,
        catalog_path=portfolio_catalog,
        legacy_registry_path=legacy_registry,
        include_notion=False,
    )
    markdown = render_portfolio_report_markdown(result.snapshot, "output/x.json")
    assert "Security overlay not run for this snapshot" in markdown
    assert "- Security posture: scanned `0`," in markdown
    validate_portfolio_report_markdown(markdown)


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


def test_path_catalog_contracts_clear_duplicate_display_name_warning(tmp_path: Path) -> None:
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
repos:
  Arcade/OrbitForge:
    owner: d
    lifecycle_state: active
    review_cadence: monthly
    intended_disposition: maintain
  Labs/OrbitForge:
    owner: d
    lifecycle_state: archived
    review_cadence: quarterly
    intended_disposition: archive
"""
    )

    result = build_portfolio_truth_snapshot(
        workspace_root=workspace,
        catalog_path=catalog_path,
        include_notion=False,
    )

    assert result.snapshot.source_summary["duplicate_display_names"] == ["OrbitForge"]
    assert result.snapshot.source_summary["unresolved_duplicate_display_names"] == []
    assert not any(
        "Duplicate project display names" in warning for warning in result.snapshot.warnings
    )
    projects_by_path = {project.identity.path: project for project in result.snapshot.projects}
    assert projects_by_path["Arcade/OrbitForge"].declared.lifecycle_state == "active"
    assert projects_by_path["Labs/OrbitForge"].declared.lifecycle_state == "archived"


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


def test_generated_registry_notes_do_not_accumulate_purpose_prefix(
    portfolio_workspace: Path,
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "portfolio-catalog.yaml"
    catalog_path.write_text(
        """
repos:
  Alpha:
    owner: d
    purpose: flagship workbook-first flow
    lifecycle_state: active
    review_cadence: weekly
    intended_disposition: maintain
    category: commercial
    tool_provenance: codex
"""
    )
    legacy_registry_path = tmp_path / "project-registry.md"
    legacy_registry_path.write_text(
        """
# Project Registry

## Standalone Projects (Root Level)

| Project | Status | Tool | Context Quality | Stack | Context Files | Category | Notes |
|---------|--------|------|-----------------|-------|---------------|----------|-------|
| Alpha | active | codex | full | Next.js | CLAUDE.md | commercial | flagship workbook-first flow flagship workbook-first flow handoff note |
"""
    )

    result = build_portfolio_truth_snapshot(
        workspace_root=portfolio_workspace,
        catalog_path=catalog_path,
        legacy_registry_path=legacy_registry_path,
        include_notion=False,
    )

    alpha = next(
        project
        for project in result.snapshot.projects
        if project.identity.display_name == "Alpha"
    )
    assert alpha.declared.purpose == "flagship workbook-first flow"
    assert alpha.declared.notes == "handoff note"


def test_generated_registry_notes_drop_security_and_path_boilerplate(
    portfolio_workspace: Path,
    tmp_path: Path,
) -> None:
    archived = portfolio_workspace / "FreeLanceInvoice"
    archived.mkdir()
    _write(archived / "README.md", "# FreeLanceInvoice\n\nArchived invoice project.\n")

    catalog_path = tmp_path / "portfolio-catalog.yaml"
    catalog_path.write_text(
        """
repos:
  FreeLanceInvoice:
    owner: d
    lifecycle_state: archived
    review_cadence: quarterly
    intended_disposition: archive
    maturity_program: archive
    category: commercial
    tool_provenance: gpt
"""
    )
    legacy_registry_path = tmp_path / "project-registry.md"
    legacy_registry_path.write_text(
        """
# Project Registry

## Standalone Projects (Root Level)

| Project | Status | Tool | Context Quality | Stack | Context Files | Category | Notes |
|---------|--------|------|-----------------|-------|---------------|----------|-------|
| FreeLanceInvoice | archived | gpt | weak | Python | README.md | commercial | [security: 1 critical / 2 high open Dependabot alerts] [security: 1 critical / 2 high open Dependabot alerts] Stable path is Archive from intended disposition. Declared maturity program and intended disposition point at different paths. Context quality is still too weak for path guidance to stand on its own. Treat this repo as investigate until path confidence improves. |
"""
    )

    result = build_portfolio_truth_snapshot(
        workspace_root=portfolio_workspace,
        catalog_path=catalog_path,
        legacy_registry_path=legacy_registry_path,
        include_notion=False,
    )

    invoice = next(
        project
        for project in result.snapshot.projects
        if project.identity.display_name == "FreeLanceInvoice"
    )
    assert invoice.declared.maturity_program == "archive"
    assert invoice.declared.notes == ""
    assert invoice.provenance["declared.maturity_program"]["source"] == "catalog_repo"
    assert invoice.provenance["declared.notes"]["source"] != "legacy_registry"


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


def test_publish_requires_producer_evidence_before_touching_outputs(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "output"
    registry_output = portfolio_workspace / "project-registry.md"
    report_output = portfolio_workspace / "PORTFOLIO-AUDIT-REPORT.md"
    registry_output.write_text("sentinel-registry\n")
    report_output.write_text("sentinel-report\n")

    with pytest.raises(
        PortfolioTruthPublishError,
        match="requires validated producer evidence",
    ):
        publish_portfolio_truth(
            workspace_root=portfolio_workspace,
            output_dir=output_dir,
            registry_output=registry_output,
            portfolio_report_output=report_output,
            catalog_path=portfolio_catalog,
            legacy_registry_path=legacy_registry,
            include_notion=False,
            require_producer_evidence=True,
        )

    assert registry_output.read_text() == "sentinel-registry\n"
    assert report_output.read_text() == "sentinel-report\n"
    assert not output_dir.exists()


def test_publish_refuses_to_drop_existing_notion_context(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    latest_path = output_dir / "portfolio-truth-latest.json"
    latest_path.write_text(
        json.dumps({"source_summary": {"notion_context_rows": 137}}) + "\n"
    )
    registry_output = portfolio_workspace / "project-registry.md"
    report_output = portfolio_workspace / "PORTFOLIO-AUDIT-REPORT.md"

    monkeypatch.setattr(
        "src.portfolio_truth_sources.load_notion_project_context",
        lambda _config_dir: None,
    )
    monkeypatch.setattr(
        "src.portfolio_truth_publish._notion_project_context_configured",
        lambda: True,
    )

    with pytest.raises(RuntimeError, match="0 Notion context rows"):
        publish_portfolio_truth(
            workspace_root=portfolio_workspace,
            output_dir=output_dir,
            registry_output=registry_output,
            portfolio_report_output=report_output,
            catalog_path=portfolio_catalog,
            legacy_registry_path=legacy_registry,
            include_notion=True,
        )

    assert json.loads(latest_path.read_text())["source_summary"]["notion_context_rows"] == 137


def test_load_prior_notion_context_rebuilds_from_artifact(tmp_path: Path) -> None:
    from src.portfolio_truth_reconcile import load_prior_notion_context
    from src.registry_parser import _normalize

    latest_path = tmp_path / "portfolio-truth-latest.json"
    latest_path.write_text(
        json.dumps(
            {
                "source_summary": {"notion_context_rows": 2},
                "projects": [
                    {
                        "identity": {"display_name": "CryptForge"},
                        "advisory": {
                            "notion_portfolio_call": "Finish",
                            "notion_momentum": "Post-Build Review Done",
                            "notion_current_state": "Parked",
                        },
                    },
                    {
                        "identity": {"display_name": "NoNotion"},
                        "advisory": {
                            "notion_portfolio_call": "",
                            "notion_momentum": "",
                            "notion_current_state": "",
                        },
                    },
                ],
            }
        )
        + "\n"
    )

    context = load_prior_notion_context(latest_path)

    assert context[_normalize("CryptForge")] == {
        "portfolio_call": "Finish",
        "momentum": "Post-Build Review Done",
        "current_state": "Parked",
    }
    assert _normalize("NoNotion") not in context
    assert len(context) == 1


def test_load_prior_notion_context_missing_or_malformed_returns_empty(tmp_path: Path) -> None:
    from src.portfolio_truth_reconcile import load_prior_notion_context

    assert load_prior_notion_context(tmp_path / "absent.json") == {}
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{ not json")
    assert load_prior_notion_context(malformed) == {}


def test_publish_allow_empty_notion_carries_forward_prior_context(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    registry_output = portfolio_workspace / "project-registry.md"
    report_output = portfolio_workspace / "PORTFOLIO-AUDIT-REPORT.md"

    # Live Notion unavailable (token lost) - the exact condition that breaks the nightly job.
    monkeypatch.setattr(
        "src.portfolio_truth_sources.load_notion_project_context",
        lambda _config_dir: None,
    )
    monkeypatch.setattr(
        "src.portfolio_truth_publish._notion_project_context_configured",
        lambda: True,
    )

    # Discover a real workspace project name to seed prior advisory against.
    discovered = build_portfolio_truth_snapshot(
        workspace_root=portfolio_workspace,
        catalog_path=portfolio_catalog,
        legacy_registry_path=legacy_registry,
        include_notion=False,
    )
    target_name = discovered.snapshot.projects[0].identity.display_name

    # Seed the prior artifact with the per-project advisory a tokened run produced.
    latest_path = output_dir / "portfolio-truth-latest.json"
    latest_path.write_text(
        json.dumps(
            {
                "source_summary": {"notion_context_rows": 1},
                "projects": [
                    {
                        "identity": {"display_name": target_name},
                        "advisory": {
                            "notion_portfolio_call": "Ship",
                            "notion_momentum": "Active",
                            "notion_current_state": "Building",
                        },
                    }
                ],
            }
        )
        + "\n"
    )

    result = publish_portfolio_truth(
        workspace_root=portfolio_workspace,
        output_dir=output_dir,
        registry_output=registry_output,
        portfolio_report_output=report_output,
        catalog_path=portfolio_catalog,
        legacy_registry_path=legacy_registry,
        include_notion=True,
        allow_empty_notion=True,
    )

    published = json.loads(result.latest_path.read_text())
    summary = published["source_summary"]
    assert summary["notion_context_rows"] == 1
    assert summary["notion_context_carried_forward"] is True
    target = next(
        item for item in published["projects"] if item["identity"]["display_name"] == target_name
    )
    assert target["advisory"]["notion_portfolio_call"] == "Ship"
    assert target["advisory"]["notion_current_state"] == "Building"


def test_publish_without_allow_empty_notion_still_guards(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Opt-in: with the flag off, the data-safety guard must still fire.
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "portfolio-truth-latest.json").write_text(
        json.dumps({"source_summary": {"notion_context_rows": 137}}) + "\n"
    )
    monkeypatch.setattr(
        "src.portfolio_truth_sources.load_notion_project_context",
        lambda _config_dir: None,
    )
    monkeypatch.setattr(
        "src.portfolio_truth_publish._notion_project_context_configured",
        lambda: True,
    )

    with pytest.raises(RuntimeError, match="0 Notion context rows"):
        publish_portfolio_truth(
            workspace_root=portfolio_workspace,
            output_dir=output_dir,
            registry_output=portfolio_workspace / "project-registry.md",
            portfolio_report_output=portfolio_workspace / "PORTFOLIO-AUDIT-REPORT.md",
            catalog_path=portfolio_catalog,
            legacy_registry_path=legacy_registry,
            include_notion=True,
            allow_empty_notion=False,
        )


def test_report_subcommand_parses_allow_empty_notion_flag() -> None:
    # The nightly job runs `audit report <user> --portfolio-truth`; the new flag
    # must be accepted on that exact path and default to opt-in off.
    from src.cli import build_subcommand_parser

    parser = build_subcommand_parser()
    enabled = parser.parse_args(
        ["report", "testuser", "--portfolio-truth", "--portfolio-truth-allow-empty-notion"]
    )
    assert enabled.portfolio_truth_allow_empty_notion is True
    default = parser.parse_args(["report", "testuser", "--portfolio-truth"])
    assert default.portfolio_truth_allow_empty_notion is False


def test_portfolio_truth_app_passes_validated_producer_receipt_to_publisher(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from src.app.portfolio_truth import run_portfolio_truth_mode
    from src.producer_preflight import PREFLIGHT_SCHEMA_VERSION

    receipt = tmp_path / "producer.json"
    receipt.write_text(
        json.dumps(
            {
                "schema_version": PREFLIGHT_SCHEMA_VERSION,
                "state": "pass",
                "repository": "saagpatel/GithubRepoAuditor",
                "commit": "a" * 40,
                "ref": "refs/remotes/origin/main",
                "checkout_role": "canonical-automation",
                "worktree_clean": True,
                "verified_at": "2026-07-10T12:00:00Z",
                "checks": {},
            }
        )
    )
    captured: dict[str, object] = {}

    def fake_publish(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            latest_path=tmp_path / "latest.json",
            snapshot_path=tmp_path / "history.json",
            registry_output=tmp_path / "registry.md",
            portfolio_report_output=tmp_path / "report.md",
            project_count=0,
            registry_changed=False,
            report_changed=False,
        )

    monkeypatch.setattr("src.app.portfolio_truth.publish_portfolio_truth", fake_publish)
    monkeypatch.setattr(
        "src.app.portfolio_truth.load_live_repo_status_by_name", lambda **_kwargs: {}
    )
    monkeypatch.setattr(
        "src.app.portfolio_truth.warn_if_warehouse_report_stale", lambda *_args: None
    )
    monkeypatch.setenv("GHRA_REQUIRE_PRODUCER_EVIDENCE", "1")
    monkeypatch.setenv("GHRA_PRODUCER_EVIDENCE", str(receipt))
    monkeypatch.setenv("GHRA_PRODUCER_REPO_ROOT", str(tmp_path / "producer-repo"))
    args = SimpleNamespace(
        output_dir=str(tmp_path / "output"),
        workspace_root=str(tmp_path),
        registry_output=str(tmp_path / "registry.md"),
        portfolio_report_output=str(tmp_path / "report.md"),
        registry=None,
        catalog=None,
        username="testuser",
        token=None,
        no_cache=True,
        portfolio_truth_include_release_count=False,
        portfolio_truth_include_security=False,
        portfolio_truth_allow_empty_notion=False,
    )

    run_portfolio_truth_mode(args)

    evidence = captured["producer_evidence"]
    assert evidence.commit == "a" * 40
    assert captured["producer_repo_root"] == tmp_path / "producer-repo"
    assert captured["require_producer_evidence"] is True


def test_cli_portfolio_truth_allow_empty_notion_carries_forward(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    discovered = build_portfolio_truth_snapshot(
        workspace_root=portfolio_workspace,
        catalog_path=portfolio_catalog,
        legacy_registry_path=legacy_registry,
        include_notion=False,
    )
    target_name = discovered.snapshot.projects[0].identity.display_name

    (output_dir / "portfolio-truth-latest.json").write_text(
        json.dumps(
            {
                "source_summary": {"notion_context_rows": 1},
                "projects": [
                    {
                        "identity": {"display_name": target_name},
                        "advisory": {
                            "notion_portfolio_call": "Ship",
                            "notion_momentum": "Active",
                            "notion_current_state": "Building",
                        },
                    }
                ],
            }
        )
        + "\n"
    )
    monkeypatch.setattr(
        "src.portfolio_truth_sources.load_notion_project_context",
        lambda _config_dir: None,
    )
    monkeypatch.setattr(
        "src.portfolio_truth_publish._notion_project_context_configured",
        lambda: True,
    )
    argv = [
        "audit",
        "testuser",
        "--portfolio-truth",
        "--portfolio-truth-allow-empty-notion",
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

    # Must NOT raise SystemExit from the Notion-drop guard - carry-forward keeps rows > 0.
    main()

    published = json.loads((output_dir / "portfolio-truth-latest.json").read_text())
    assert published["source_summary"]["notion_context_rows"] == 1
    assert published["source_summary"]["notion_context_carried_forward"] is True


def test_publish_allow_empty_notion_without_prior_context_publishes_zero(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Flag set, but nothing to carry forward (prior has a count yet no per-project
    # advisory): the operator opted into empty-Notion publishing, so the guard must
    # not block and the run publishes with zero carried rows.
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "portfolio-truth-latest.json").write_text(
        json.dumps({"source_summary": {"notion_context_rows": 137}, "projects": []}) + "\n"
    )
    monkeypatch.setattr(
        "src.portfolio_truth_sources.load_notion_project_context",
        lambda _config_dir: None,
    )
    monkeypatch.setattr(
        "src.portfolio_truth_publish._notion_project_context_configured",
        lambda: True,
    )

    result = publish_portfolio_truth(
        workspace_root=portfolio_workspace,
        output_dir=output_dir,
        registry_output=portfolio_workspace / "project-registry.md",
        portfolio_report_output=portfolio_workspace / "PORTFOLIO-AUDIT-REPORT.md",
        catalog_path=portfolio_catalog,
        legacy_registry_path=legacy_registry,
        include_notion=True,
        allow_empty_notion=True,
    )

    published = json.loads(result.latest_path.read_text())
    assert published["source_summary"]["notion_context_rows"] == 0
    assert published["source_summary"]["notion_context_carried_forward"] is False


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


def test_context_recovery_preserves_fenced_run_commands(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
) -> None:
    target_repo = portfolio_workspace / "FenceRecover"
    target_repo.mkdir()
    _write(target_repo / "README.md", "# FenceRecover\n\nFenceRecover is a small active repo.\n")
    _write(
        target_repo / "CLAUDE.md",
        """# FenceRecover

## How To Run

```bash
# Install dependencies
npm install
npm run dev
```
""",
    )
    _write(target_repo / "package.json", '{"dependencies":{"vite":"6.0.0","react":"19.0.0"}}')

    result = build_portfolio_truth_snapshot(
        workspace_root=portfolio_workspace,
        catalog_path=portfolio_catalog,
        legacy_registry_path=legacy_registry,
        include_notion=False,
        now=datetime.fromtimestamp(1_700_000_100, tz=timezone.utc),
    )
    plan = build_context_recovery_plan(result.snapshot, workspace_root=portfolio_workspace)
    apply_context_recovery_plan(
        result.snapshot,
        plan,
        workspace_root=portfolio_workspace,
        catalog_path=portfolio_catalog,
    )

    context_text = (target_repo / "CLAUDE.md").read_text()
    managed_block = context_text.split("<!-- portfolio-context:start -->", 1)[1]
    assert "# Install dependencies" in managed_block
    assert "npm run dev" in managed_block
    assert managed_block.count("```") >= 2
    assert _classify_context_quality(target_repo, ["CLAUDE.md"]) == "minimum-viable"


def test_context_recovery_ignores_development_conventions_for_run_commands(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
) -> None:
    target_repo = portfolio_workspace / "ConventionsRecover"
    target_repo.mkdir()
    _write(target_repo / "README.md", "# ConventionsRecover\n\nConventionsRecover is active.\n")
    _write(
        target_repo / "CLAUDE.md",
        """# ConventionsRecover

## Development Conventions

- File naming: kebab-case for files.
- Conventional commits only.
""",
    )
    _write(target_repo / "package.json", '{"dependencies":{"vite":"6.0.0","react":"19.0.0"}}')

    result = build_portfolio_truth_snapshot(
        workspace_root=portfolio_workspace,
        catalog_path=portfolio_catalog,
        legacy_registry_path=legacy_registry,
        include_notion=False,
        now=datetime.fromtimestamp(1_700_000_100, tz=timezone.utc),
    )
    plan = build_context_recovery_plan(result.snapshot, workspace_root=portfolio_workspace)
    apply_context_recovery_plan(
        result.snapshot,
        plan,
        workspace_root=portfolio_workspace,
        catalog_path=portfolio_catalog,
    )

    context_text = (target_repo / "CLAUDE.md").read_text()
    managed_block = context_text.split("<!-- portfolio-context:start -->", 1)[1]
    how_to_run = managed_block.split("## How To Run", 1)[1].split("## Known Risks", 1)[0]
    assert "npm run dev" in how_to_run
    assert "File naming" not in how_to_run
    assert _classify_context_quality(target_repo, ["CLAUDE.md"]) == "minimum-viable"


def test_context_recovery_skips_pointer_preamble_for_project_summary(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
) -> None:
    target_repo = portfolio_workspace / "PointerRecover"
    target_repo.mkdir()
    _write(target_repo / "CLAUDE.md", "@AGENTS.md\n")
    _write(
        target_repo / "README.md",
        """# PointerRecover

## Product shape

PointerRecover is a local workflow app for validating recovered project summaries.

## Local setup

Run `npm run dev` after installing dependencies.

## Intentional limits

This fixture only models pointer preambles.
""",
    )
    _write(target_repo / "package.json", '{"dependencies":{"vite":"6.0.0","react":"19.0.0"}}')

    result = build_portfolio_truth_snapshot(
        workspace_root=portfolio_workspace,
        catalog_path=portfolio_catalog,
        legacy_registry_path=legacy_registry,
        include_notion=False,
        now=datetime.fromtimestamp(1_700_000_100, tz=timezone.utc),
    )
    plan = build_context_recovery_plan(result.snapshot, workspace_root=portfolio_workspace)
    apply_context_recovery_plan(
        result.snapshot,
        plan,
        workspace_root=portfolio_workspace,
        catalog_path=portfolio_catalog,
    )

    context_text = (target_repo / "CLAUDE.md").read_text()
    managed_block = context_text.split("<!-- portfolio-context:start -->", 1)[1]
    project_summary = managed_block.split("## What This Project Is", 1)[1].split(
        "## Current State", 1
    )[0]
    assert "@AGENTS.md" not in project_summary
    assert "workflow app" in project_summary
    assert _classify_context_quality(target_repo, ["CLAUDE.md"]) == "minimum-viable"


def test_context_recovery_does_not_use_unknown_as_stack(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
) -> None:
    target_repo = portfolio_workspace / "UnknownStackRecover"
    target_repo.mkdir()
    _write(target_repo / "README.md", "# UnknownStackRecover\n\nUnknownStackRecover is active.\n")

    result = build_portfolio_truth_snapshot(
        workspace_root=portfolio_workspace,
        catalog_path=portfolio_catalog,
        legacy_registry_path=legacy_registry,
        include_notion=False,
        now=datetime.fromtimestamp(1_700_000_100, tz=timezone.utc),
    )
    plan = build_context_recovery_plan(result.snapshot, workspace_root=portfolio_workspace)
    apply_context_recovery_plan(
        result.snapshot,
        plan,
        workspace_root=portfolio_workspace,
        catalog_path=portfolio_catalog,
    )

    context_text = (target_repo / "AGENTS.md").read_text()
    managed_block = context_text.split("<!-- portfolio-context:start -->", 1)[1]
    stack = managed_block.split("## Stack", 1)[1].split("## How To Run", 1)[0]
    assert "Unknown" not in stack
    assert "deeper explicit handoff" in stack
    assert _classify_context_quality(target_repo, ["AGENTS.md"]) == "minimum-viable"


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


def test_allow_dirty_worktree_makes_dirty_repos_eligible(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
) -> None:
    dirty_repo = portfolio_workspace / "DirtyRepo"
    dirty_repo.mkdir()
    _write(dirty_repo / "README.md", "# DirtyRepo\n\nA dirty repo.\n")
    _write(dirty_repo / "package.json", '{"dependencies":{"react":"19.0.0"}}')
    subprocess.run(["git", "init"], cwd=dirty_repo, capture_output=True, check=True)
    subprocess.run(["git", "add", "."], cwd=dirty_repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=dirty_repo,
        capture_output=True,
        check=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
    )
    _write(dirty_repo / "dirty.txt", "uncommitted")

    result = build_portfolio_truth_snapshot(
        workspace_root=portfolio_workspace,
        catalog_path=portfolio_catalog,
        legacy_registry_path=legacy_registry,
        include_notion=False,
        now=datetime.fromtimestamp(1_700_000_100, tz=timezone.utc),
    )

    # Without allow_dirty: should be skipped
    plan_strict = build_context_recovery_plan(result.snapshot, workspace_root=portfolio_workspace)
    strict_target = next((t for t in plan_strict.projects if t.project_key == "DirtyRepo"), None)
    assert strict_target is not None
    assert strict_target.status == "skipped"
    assert strict_target.reason == "dirty-worktree"

    # With allow_dirty: should be eligible
    plan_dirty = build_context_recovery_plan(
        result.snapshot, workspace_root=portfolio_workspace, allow_dirty=True
    )
    dirty_target = next((t for t in plan_dirty.projects if t.project_key == "DirtyRepo"), None)
    assert dirty_target is not None
    assert dirty_target.status == "eligible"


def _apply_recovery_for(
    target_repo: Path,
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
) -> str:
    """Run the full snapshot → plan → apply pipeline and return target CLAUDE.md text."""
    result = build_portfolio_truth_snapshot(
        workspace_root=portfolio_workspace,
        catalog_path=portfolio_catalog,
        legacy_registry_path=legacy_registry,
        include_notion=False,
        now=datetime.fromtimestamp(1_700_000_100, tz=timezone.utc),
    )
    plan = build_context_recovery_plan(result.snapshot, workspace_root=portfolio_workspace)
    apply_context_recovery_plan(
        result.snapshot,
        plan,
        workspace_root=portfolio_workspace,
        catalog_path=portfolio_catalog,
    )
    return (target_repo / "CLAUDE.md").read_text()


def _how_to_run_section(claude_md_text: str) -> str:
    managed_block = claude_md_text.split("<!-- portfolio-context:start -->", 1)[1]
    return managed_block.split("## How To Run", 1)[1].split("## Known Risks", 1)[0]


def test_context_recovery_overrides_npm_text_when_pnpm_lockfile_present(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
) -> None:
    target_repo = portfolio_workspace / "PnpmOverride"
    target_repo.mkdir()
    _write(target_repo / "README.md", "# PnpmOverride\n\nPnpmOverride is an active repo.\n")
    _write(
        target_repo / "CLAUDE.md",
        """# PnpmOverride

## How To Run

- Use `npm` only; this repo does not use pnpm.
- Run with `npm run dev`.
""",
    )
    _write(target_repo / "package.json", '{"dependencies":{"vite":"6.0.0"}}')
    _write(target_repo / "pnpm-lock.yaml", "lockfileVersion: '9.0'\n")

    text = _apply_recovery_for(target_repo, portfolio_workspace, portfolio_catalog, legacy_registry)
    how_to_run = _how_to_run_section(text)
    assert "pnpm" in how_to_run.lower()
    assert "Use `npm` only" not in how_to_run


def test_context_recovery_detects_package_manager_from_ci_workflow(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
) -> None:
    target_repo = portfolio_workspace / "CiWorkflowPnpm"
    target_repo.mkdir()
    _write(target_repo / "README.md", "# CiWorkflowPnpm\n\nCiWorkflowPnpm is an active repo.\n")
    _write(
        target_repo / "CLAUDE.md",
        """# CiWorkflowPnpm

## How To Run

- Use `npm install` to bootstrap.
""",
    )
    _write(target_repo / "package.json", '{"dependencies":{"vite":"6.0.0"}}')
    _write(
        target_repo / ".github" / "workflows" / "test.yml",
        "name: test\njobs:\n  test:\n    steps:\n      - run: pnpm install --frozen-lockfile\n      - run: pnpm test\n",
    )

    text = _apply_recovery_for(target_repo, portfolio_workspace, portfolio_catalog, legacy_registry)
    how_to_run = _how_to_run_section(text)
    assert "pnpm" in how_to_run.lower()


def test_context_recovery_respects_manual_override_marker(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
) -> None:
    target_repo = portfolio_workspace / "ManualMarker"
    target_repo.mkdir()
    _write(target_repo / "README.md", "# ManualMarker\n\nManualMarker is an active repo.\n")
    _write(
        target_repo / "CLAUDE.md",
        """# ManualMarker

## How To Run

<!-- manual:run-instructions -->
- Use `npm` only; we intentionally avoid pnpm here.
- Run `npm run dev`.
""",
    )
    _write(target_repo / "package.json", '{"dependencies":{"vite":"6.0.0"}}')
    _write(target_repo / "pnpm-lock.yaml", "lockfileVersion: '9.0'\n")

    text = _apply_recovery_for(target_repo, portfolio_workspace, portfolio_catalog, legacy_registry)
    how_to_run = _how_to_run_section(text)
    assert "Use `npm` only" in how_to_run
    assert "manual:run-instructions" in how_to_run


def test_context_recovery_emits_drift_note_when_correcting(
    portfolio_workspace: Path,
    portfolio_catalog: Path,
    legacy_registry: Path,
) -> None:
    target_repo = portfolio_workspace / "DriftNote"
    target_repo.mkdir()
    _write(target_repo / "README.md", "# DriftNote\n\nDriftNote is an active repo.\n")
    _write(
        target_repo / "CLAUDE.md",
        """# DriftNote

## How To Run

- Use `npm` only; this repo does not use pnpm.
""",
    )
    _write(target_repo / "package.json", '{"dependencies":{"vite":"6.0.0"}}')
    _write(target_repo / "pnpm-lock.yaml", "lockfileVersion: '9.0'\n")

    text = _apply_recovery_for(target_repo, portfolio_workspace, portfolio_catalog, legacy_registry)
    how_to_run = _how_to_run_section(text)
    assert "corrected" in how_to_run.lower() or "detected" in how_to_run.lower()


# --- _git_default_branch ---------------------------------------------------


def test_git_default_branch_reads_local_origin_head(tmp_path: Path) -> None:
    from src.portfolio_truth_sources import _git_default_branch

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    # Point the local origin/HEAD ref at a non-"main" branch (no network/clone).
    subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/develop"],
        cwd=repo,
        capture_output=True,
        check=True,
    )

    assert _git_default_branch(repo) == "develop"


def test_git_default_branch_keeps_multi_segment_branch(tmp_path: Path) -> None:
    from src.portfolio_truth_sources import _git_default_branch

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/release/v1"],
        cwd=repo,
        capture_output=True,
        check=True,
    )

    # Only the remote name is stripped; the branch path stays intact.
    assert _git_default_branch(repo) == "release/v1"


def test_git_default_branch_empty_when_origin_head_unset(tmp_path: Path) -> None:
    from src.portfolio_truth_sources import _git_default_branch

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)

    # A freshly init'd repo has no origin/HEAD → "" so callers fall back.
    assert _git_default_branch(repo) == ""


# ── F2: warehouse-report staleness reminder ────────────────────────────────
from src.portfolio_truth_status import warn_if_warehouse_report_stale  # noqa: E402


def _write_warehouse_report(d: Path, username: str, date_str: str) -> None:
    (d / f"audit-report-{username}-{date_str}.json").write_text("{}", encoding="utf-8")


class TestWarehouseStalenessReminder:
    """F2 (keep-dual): --portfolio-truth mode warns when the warehouse report Notion
    reads is missing or stale, so the operator refreshes it."""

    def test_missing_report_warns(self, tmp_path: Path, capsys) -> None:
        import re

        warn_if_warehouse_report_stale(tmp_path, "saagpatel")
        captured = capsys.readouterr()
        # print_warning word-wraps, so normalize whitespace before substring checks
        combined = re.sub(r"\s+", " ", captured.out + captured.err)
        assert "No audit-report-saagpatel" in combined
        assert "audit report saagpatel" in combined

    def test_stale_report_warns(self, tmp_path: Path, capsys) -> None:
        _write_warehouse_report(tmp_path, "saagpatel", "2020-01-01")
        warn_if_warehouse_report_stale(tmp_path, "saagpatel")
        captured = capsys.readouterr()
        assert "stale" in (captured.out + captured.err).lower()

    def test_fresh_report_no_warning(self, tmp_path: Path, capsys) -> None:
        from datetime import date

        _write_warehouse_report(tmp_path, "saagpatel", date.today().isoformat())
        warn_if_warehouse_report_stale(tmp_path, "saagpatel")
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert "stale" not in combined.lower()
        assert "No audit-report" not in combined
