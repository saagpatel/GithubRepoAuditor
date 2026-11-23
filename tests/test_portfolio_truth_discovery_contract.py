from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from github_repo_auditor.portfolio_truth_sources import discover_workspace_projects


def _make_repository(path: Path) -> None:
    path.mkdir(parents=True)
    (path / "README.md").write_text("# Synthetic repository\n")
    subprocess.run(["git", "init", "-q", str(path)], check=True)


def test_discovery_finds_repository_nested_inside_project(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outer = workspace / "Outer"
    _make_repository(outer)
    _make_repository(outer / "packages" / "Nested")

    projects = discover_workspace_projects(
        workspace,
        catalog_data={},
        now=datetime(2026, 11, 23, tzinfo=timezone.utc),
    )

    assert {project["path"] for project in projects} == {
        "Outer",
        "Outer/packages/Nested",
    }


def test_discovery_finds_projects_beyond_two_category_levels(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    project = workspace / "Products" / "Category" / "Subcategory" / "Project"
    workspace.mkdir()
    _make_repository(project)

    projects = discover_workspace_projects(
        workspace,
        catalog_data={},
        now=datetime(2026, 11, 23, tzinfo=timezone.utc),
    )

    assert [item["path"] for item in projects] == [
        "Products/Category/Subcategory/Project"
    ]


def test_discovery_skips_scratch_dependencies_and_symlinked_projects(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _make_repository(workspace / "Category" / "Group" / "Visible")
    _make_repository(workspace / "Category" / "Group" / "node_modules" / "Dependency")
    _make_repository(workspace / "Category" / "Group" / "vendor" / "Vendored")
    _make_repository(workspace / "node_modules" / "RootDependency")
    _make_repository(workspace / "scratch" / "ScratchProject")
    _make_repository(workspace / "_codex-worktrees" / "WorkingCopy")
    _make_repository(workspace / "_claude-worktrees" / "WorkingCopy")
    _make_repository(workspace / ".codex-scratch" / "HiddenProject")
    external_project = tmp_path / "external" / "LinkedProject"
    _make_repository(external_project)
    (workspace / "LinkedProject").symlink_to(external_project, target_is_directory=True)

    exclusions: dict[str, int] = {}
    projects = discover_workspace_projects(
        workspace,
        catalog_data={},
        now=datetime(2026, 11, 23, tzinfo=timezone.utc),
        exclusion_counts=exclusions,
    )

    assert [project["path"] for project in projects] == ["Category/Group/Visible"]
    assert exclusions == {
        "linked-worktree-container": 2,
        "scratch-container": 1,
    }


def test_category_readme_and_child_repository_have_separate_entries(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    category = workspace / "Category"
    workspace.mkdir()
    category.mkdir()
    (category / "README.md").write_text("# Category index\n")
    _make_repository(category / "ChildRepo")

    projects = discover_workspace_projects(
        workspace,
        catalog_data={},
        now=datetime(2026, 11, 23, tzinfo=timezone.utc),
    )

    assert {project["path"] for project in projects} == {
        "Category",
        "Category/ChildRepo",
    }
