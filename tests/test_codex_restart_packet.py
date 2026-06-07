from __future__ import annotations

import json
import subprocess
from pathlib import Path

from src.codex_restart_packet import (
    build_restart_packet,
    discover_git_repos,
    render_markdown,
)
from src.portfolio_truth_types import TRUTH_LATEST_FILENAME


def _run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


def _git_repo(path: Path, *, remote: bool = True) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _run(["git", "init"], path)
    _run(["git", "config", "user.email", "test@example.com"], path)
    _run(["git", "config", "user.name", "Test User"], path)
    (path / "README.md").write_text("# test\n")
    _run(["git", "add", "README.md"], path)
    _run(["git", "commit", "-m", "init"], path)
    if remote:
        _run(["git", "remote", "add", "origin", "https://example.com/test/repo.git"], path)


def test_discovery_excludes_archive_dependency_and_eval_fixture_repos(tmp_path: Path) -> None:
    _git_repo(tmp_path / "RealRepo")
    _git_repo(tmp_path / ".portfolio-noise-archive" / "OldClone")
    _git_repo(tmp_path / "RealRepo" / "node_modules" / "NestedPackage")
    _git_repo(tmp_path / "evals" / "fixtures" / "adv-fixture")

    repos = {repo.relative_to(tmp_path).as_posix() for repo in discover_git_repos(tmp_path)}

    assert repos == {"RealRepo"}


def test_discovery_treats_git_backed_workspace_root_as_container(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    _git_repo(tmp_path / "NestedRepo")

    repos = {repo.relative_to(tmp_path).as_posix() for repo in discover_git_repos(tmp_path)}

    assert repos == {"NestedRepo"}


def test_restart_packet_prioritizes_dirty_operating_repos(tmp_path: Path) -> None:
    workspace = tmp_path / "Projects"
    _git_repo(workspace / "CleanRepo")
    dirty = workspace / "DirtyRepo"
    _git_repo(dirty)
    (dirty / "notes.txt").write_text("local work\n")
    operating = tmp_path / ".local/share/personal-ops"
    _git_repo(operating)
    (operating / "change.txt").write_text("ops work\n")
    truth_dir = workspace / "GithubRepoAuditor" / "output"
    truth_dir.mkdir(parents=True)
    truth_path = truth_dir / TRUTH_LATEST_FILENAME
    truth_path.write_text(
        json.dumps(
            {
                "schema_version": "0.5.0",
                "generated_at": "2026-06-07T08:32:03+00:00",
                "warnings": [],
                "projects": [],
            }
        )
    )

    packet = build_restart_packet(
        workspace_root=workspace,
        truth_path=truth_path,
        operating_repos=[operating],
    )

    labels = [repo["label"] for repo in packet["active_working_set"]]
    assert "personal-ops" in labels
    assert "DirtyRepo" in labels
    assert packet["git_summary"]["dirty"] == 2
    assert packet["truth"]["available"] is True


def test_render_markdown_includes_restart_contract_sections(tmp_path: Path) -> None:
    workspace = tmp_path / "Projects"
    _git_repo(workspace / "DirtyRepo")
    (workspace / "DirtyRepo" / "notes.txt").write_text("local work\n")

    packet = build_restart_packet(workspace_root=workspace, operating_repos=[])
    markdown = render_markdown(packet)

    assert "# Codex Restart Packet" in markdown
    assert "## Active Working Set" in markdown
    assert ".portfolio-noise-archive" in markdown
    assert "DirtyRepo" in markdown
