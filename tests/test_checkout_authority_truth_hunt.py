from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from github_repo_auditor import portfolio_truth_reconcile
from github_repo_auditor.portfolio_checkout_authority import checkout_authority_blocker
from github_repo_auditor.portfolio_truth_reconcile import build_portfolio_truth_snapshot
from github_repo_auditor.portfolio_truth_validate import validate_truth_snapshot


def _git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_equivalent_independent_clones_without_declaration_remain_unknown(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    primary = workspace / "Widget"
    primary.mkdir()
    (primary / "README.md").write_text("# Widget\n")
    _git(primary, "init", "-q", "-b", "main")
    _git(primary, "add", "README.md")
    subprocess.run(
        [
            "git",
            "-C",
            str(primary),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-q",
            "-m",
            "fixture",
        ],
        check=True,
    )
    _git(primary, "remote", "add", "origin", "git@github.com:example/Widget.git")

    mirror = workspace / "Mirror"
    subprocess.run(
        ["git", "clone", "-q", str(primary), str(mirror)],
        check=True,
    )
    _git(mirror, "remote", "set-url", "origin", "https://github.com/example/Widget.git")

    result = build_portfolio_truth_snapshot(
        workspace_root=workspace,
        catalog_path=tmp_path / "missing.yaml",
        include_notion=False,
        now=datetime(2026, 8, 3, tzinfo=timezone.utc),
    )

    project = next(
        item
        for item in result.snapshot.projects
        if item.identity.repo_full_name == "example/Widget"
    )
    authority = project.repository_state["checkout_authority"]
    assert authority["full_clone_count"] == 2
    assert authority["selection"]["state"] == "unknown"
    assert authority["selection"]["selected_path"] is None


def test_publication_rechecks_selected_authority_against_row_topology(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    primary = workspace / "Widget"
    primary.mkdir(parents=True)
    _git(primary, "init", "-q", "-b", "main")
    _git(
        primary,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "--allow-empty",
        "-qm",
        "fixture",
    )
    _git(primary, "remote", "add", "origin", "https://github.com/example/Widget")
    linked = workspace / "_codex-worktrees"
    linked.mkdir()
    for branch in ("feature", "temporary"):
        _git(primary, "worktree", "add", "-qb", branch, str(linked / branch))

    observe = portfolio_truth_reconcile.observe_repository_state

    def observe_after_checkout_changes(path: Path, **kwargs: Any) -> dict[str, Any]:
        _git(primary, "worktree", "remove", str(linked / "temporary"))
        for index in range(4):
            (linked / "feature" / f"edit-{index}").touch()
        return observe(path, **kwargs)

    monkeypatch.setattr(
        portfolio_truth_reconcile,
        "observe_repository_state",
        observe_after_checkout_changes,
    )
    result = build_portfolio_truth_snapshot(
        workspace_root=workspace,
        catalog_path=tmp_path / "missing.yaml",
        include_notion=False,
        now=datetime(2026, 8, 3, tzinfo=timezone.utc),
    )
    (project,) = result.snapshot.projects
    authority = project.repository_state["checkout_authority"]
    assert authority["checkout_count"] == 3
    assert all(member["dirty"] is False for member in authority["checkouts"])
    assert sorted(
        tree["dirty_path_count"] for tree in project.repository_state["worktrees"]
    ) == [0, 4]
    assert authority["selection"]["state"] == "unknown", checkout_authority_blocker(
        project
    )
    assert authority["selection"]["selected_path"] is None
    assert "checkout-topology-local-work-present" in authority["selection"]["reason"]
    summary = result.snapshot.source_summary["checkout_collisions"]
    assert summary["groups"] == [authority]
    assert summary["ambiguous_group_count"] == 1
    validate_truth_snapshot(result.snapshot)
