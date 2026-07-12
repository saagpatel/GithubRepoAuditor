from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

from src.portfolio_repository_state import observe_repository_state


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "tests@example.invalid")
    _git(repo, "config", "user.name", "Tests")
    (repo / "README.md").write_text("fixture\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "fixture")
    return repo


def test_observation_reports_dirty_no_upstream_and_unknown_remote(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "dirty.txt").write_text("dirty\n")

    state = observe_repository_state(
        repo, observed_at=datetime(2026, 7, 12, tzinfo=UTC)
    )

    assert state["state"] == "observed"
    assert state["local"]["dirty"] is True
    assert state["local"]["dirty_path_count"] == 1
    assert state["local"]["upstream"] is None
    assert state["remote_default_branch"]["state"] == "unknown"


def test_observation_reports_linked_worktree_without_file_names(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    linked = tmp_path / "linked"
    _git(repo, "worktree", "add", "-b", "feature", str(linked), "HEAD")
    (linked / "untracked.txt").write_text("preserve\n")

    state = observe_repository_state(repo, observed_at=datetime.now(UTC))

    assert len(state["worktrees"]) == 2
    linked_state = next(item for item in state["worktrees"] if item["path"] == str(linked))
    assert linked_state["dirty"] is True
    assert linked_state["dirty_path_count"] == 1
    assert "untracked.txt" not in str(state)
