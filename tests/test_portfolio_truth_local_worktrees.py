from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from github_repo_auditor.portfolio_truth_publish import publish_portfolio_truth
from github_repo_auditor.portfolio_truth_reconcile import build_portfolio_truth_snapshot
from github_repo_auditor.portfolio_truth_validate import (
    _snapshot_from_payload,
    validate_truth_snapshot,
)


@pytest.fixture
def primary(tmp_path: Path) -> Path:
    repo = tmp_path / "workspace" / "Primary"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "--allow-empty",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    return repo


def _link(primary: Path, linked: Path) -> None:
    linked.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "-C", str(primary), "worktree", "add", "-q", "--detach", str(linked)],
        check=True,
    )


def test_primary_identity_precedes_inherited_linked_group(
    primary: Path, tmp_path: Path
) -> None:
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(
        "groups:\n  archive:\n    path_prefixes: [Archive]\n    lifecycle_state: archived\n"
    )

    def identity(workspace: Path) -> tuple[str, str, str]:
        snapshot = build_portfolio_truth_snapshot(
            workspace_root=workspace, catalog_path=catalog, include_notion=False
        ).snapshot
        (project,) = snapshot.projects
        return (
            project.identity.project_key,
            project.declared.lifecycle_state,
            project.derived.attention_state,
        )

    before = identity(primary.parent)
    assert before[:2] == ("Primary", "")
    _link(primary, primary.parent / "Archive" / "Linked")
    assert identity(primary.parent) == before

    linked_only = tmp_path / "linked-only"
    _link(primary, linked_only / "A")
    _link(primary, linked_only / "Archive" / "Linked")
    assert identity(linked_only) == ("Archive/Linked", "archived", "archived")


def test_upgrade_clears_collapsed_local_worktree_from_inventory_gap(
    primary: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = primary.parent
    _link(primary, workspace / "Archive" / "Linked")
    (workspace / "Unaccounted").mkdir()
    output = tmp_path / "published"
    output.mkdir()
    at = datetime(2026, 11, 23, tzinfo=timezone.utc)
    # Inventory comparison reads this projection of the prior 0.12 snapshot.
    keys = ["Archive/Linked", "Primary", "Unaccounted"]
    latest = output / "portfolio-truth-latest.json"
    latest.write_text(
        json.dumps(
            {
                "schema_version": "0.12.0",
                "workspace_root": str(workspace),
                "generated_at": at.isoformat(),
                "projects": [
                    {"identity": {"project_key": key, "path": key}} for key in keys
                ],
            }
        )
    )
    monkeypatch.setattr(
        "github_repo_auditor.portfolio_truth_publish.load_source_paths",
        lambda _: dict(bridge_db=None, notion_snapshot=None, memory_dir=None),
    )
    for minute in (1, 2):
        publish_portfolio_truth(
            workspace_root=workspace,
            output_dir=output,
            registry_output=workspace / "registry.md",
            portfolio_report_output=workspace / "report.md",
            catalog_path=tmp_path / "absent.yaml",
            include_notion=False,
            now=at.replace(minute=minute),
        )
        payload = json.loads(latest.read_text())
        summary = payload["source_summary"]
        assert summary["workspace_inventory_gap"] == {
            "missing_project_keys": ["Unaccounted"],
            "missing_project_paths": {"Unaccounted": "Unaccounted"},
            "baseline_generated_at": at.isoformat(),
        }
        assert summary["collapsed_local_worktrees"] == {"Primary": ["Archive/Linked"]}

    gap = summary["workspace_inventory_gap"]
    gap["missing_project_keys"].insert(0, "Archive/Linked")
    gap["missing_project_paths"]["Archive/Linked"] = "Archive/Linked"
    with pytest.raises(ValueError, match="inventory gap"):
        validate_truth_snapshot(_snapshot_from_payload(payload))
