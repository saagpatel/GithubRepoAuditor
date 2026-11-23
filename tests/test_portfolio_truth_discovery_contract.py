from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from github_repo_auditor import portfolio_truth_sources
from github_repo_auditor.portfolio_truth_reconcile import build_portfolio_truth_snapshot
from github_repo_auditor.portfolio_truth_sources import discover_workspace_projects
from github_repo_auditor.portfolio_truth_validate import validate_truth_snapshot


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


def test_local_linked_checkout_keeps_primary_catalog_identity(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    primary = workspace / "Primary"
    _make_repository(primary)

    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(primary), *args], check=True)

    git(
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "--allow-empty",
        "-qm",
        "fixture",
    )
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(
        "groups:\n  archive:\n    path_prefixes: [Primary]\n    lifecycle_state: archived\n"
        "repos:\n  Catalogued:\n    lifecycle_state: archived\n"
    )

    def identity(root: Path, catalog_path: Path = catalog) -> tuple[str, str]:
        result = build_portfolio_truth_snapshot(
            workspace_root=root,
            catalog_path=catalog_path,
            include_notion=False,
        )
        (row,) = result.snapshot.projects
        return row.identity.project_key, row.declared.lifecycle_state

    assert identity(workspace) == ("Primary", "archived")
    linked = workspace / "A"
    git("worktree", "add", "-q", "--detach", str(linked))
    assert identity(workspace) == ("Primary", "archived")
    assert identity(workspace, tmp_path / "absent.yaml") == ("Primary", "")
    git("worktree", "remove", str(linked))
    assert identity(workspace) == ("Primary", "archived")

    # With only linked checkouts in scope, an explicit repo entry anchors the key.
    linked_workspace = tmp_path / "linked-only"
    linked_workspace.mkdir()
    for name in ("A", "Catalogued"):
        git("worktree", "add", "-q", "--detach", str(linked_workspace / name))
    assert identity(linked_workspace) == ("Catalogued", "archived")


def test_unreadable_descendant_is_reported_and_siblings_continue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    workspace = tmp_path / "workspace"
    parent = workspace / "Widget"
    parent.mkdir(parents=True)
    (parent / "README.md").write_text("# Widget\n")
    restricted = parent / "restricted"
    _make_repository(restricted)
    sibling = parent / "Sibling"
    _make_repository(sibling)
    original_iterdir = Path.iterdir
    fail_workspace_root = False

    def guarded_iterdir(path: Path):
        if fail_workspace_root and path == workspace:
            raise PermissionError("synthetic unreadable workspace")
        if path == restricted:
            raise PermissionError("synthetic unreadable directory")
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", guarded_iterdir)
    snapshot = build_portfolio_truth_snapshot(
        workspace_root=workspace,
        catalog_path=tmp_path / "absent.yaml",
        include_notion=False,
    ).snapshot
    validate_truth_snapshot(snapshot)
    assert {project.identity.path for project in snapshot.projects} == {
        "Widget",
        "Widget/Sibling",
    }
    assert snapshot.exclusions["counts"] == {"unreadable-directory": 1}
    assert "discovery incomplete" in caplog.text.lower()
    fail_workspace_root = True
    with pytest.raises(PermissionError, match="synthetic unreadable workspace"):
        discover_workspace_projects(
            workspace,
            catalog_data={},
            now=datetime(2026, 11, 23, tzinfo=timezone.utc),
        )


@pytest.mark.parametrize(
    "probe_error",
    [
        subprocess.TimeoutExpired(["git"], timeout=5),
        FileNotFoundError("git executable unavailable"),
        PermissionError("git probe denied"),
    ],
)
def test_unavailable_git_marker_probe_keeps_candidate_with_unknown_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    probe_error: Exception,
) -> None:
    workspace = tmp_path / "workspace"
    project_path = workspace / "Widget"
    _make_repository(project_path)
    documents = workspace / "Documents"
    documents.mkdir()
    (documents / "README.md").write_text("# Documents\n")
    original_git_read = portfolio_truth_sources._git_read

    def guarded_git_read(path: Path, *args: str) -> str:
        if args[:2] == ("rev-parse", "--resolve-git-dir"):
            raise probe_error
        return original_git_read(path, *args)

    monkeypatch.setattr(portfolio_truth_sources, "_git_read", guarded_git_read)
    result = build_portfolio_truth_snapshot(
        workspace_root=workspace,
        catalog_path=tmp_path / "missing.yaml",
        include_notion=False,
        now=datetime(2026, 11, 23, tzinfo=timezone.utc),
    )

    validate_truth_snapshot(result.snapshot)
    rows = {
        project.identity.project_key: project for project in result.snapshot.projects
    }
    assert rows["Widget"].identity.has_git is True
    assert rows["Widget"].repository_state["state"] == "unknown"
    assert rows["Documents"].identity.has_git is False
    assert rows["Documents"].repository_state["state"] == "not_a_repository"
