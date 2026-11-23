from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from github_repo_auditor.portfolio_truth_reconcile import build_portfolio_truth_snapshot


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
