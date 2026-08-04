from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.portfolio_repository_state import observe_repository_state
from src.portfolio_truth_validate import _validate_repository_state_shape


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


def _bare_repo(tmp_path: Path) -> tuple[Path, str]:
    source = _repo(tmp_path)
    head = _git(source, "rev-parse", "HEAD")
    bare = tmp_path / "coordinator.git"
    subprocess.run(
        ["git", "clone", "--bare", str(source), str(bare)],
        check=True,
        capture_output=True,
        text=True,
    )
    return bare, head


def _remote_default(head: str, branch: str = "main") -> dict[str, Any]:
    return {
        "source": "fixture-live-remote-default",
        "state": "observed",
        "reason_code": "observed",
        "reason": None,
        "observed_at": "2026-07-12T00:00:00+00:00",
        "default_branch": branch,
        "head_sha": head,
        "archived": False,
    }


def test_observation_reports_dirty_no_upstream_and_unknown_remote(
    tmp_path: Path,
) -> None:
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
    linked_state = next(
        item for item in state["worktrees"] if item["path"] == str(linked)
    )
    assert linked_state["dirty"] is True
    assert linked_state["dirty_path_count"] == 1
    assert "untracked.txt" not in str(state)


def test_dangling_bare_head_uses_clean_matching_linked_worktree(
    tmp_path: Path,
) -> None:
    bare, head = _bare_repo(tmp_path)
    linked = tmp_path / "linked"
    _git(bare, "worktree", "add", str(linked), "main")
    _git(bare, "symbolic-ref", "HEAD", "refs/heads/missing-default")

    state = observe_repository_state(
        bare,
        observed_at=datetime(2026, 7, 12, tzinfo=UTC),
        remote_default_branch=_remote_default(head),
    )

    assert state["state"] == "observed"
    assert state["topology"]["kind"] == "bare_coordinator"
    assert state["topology"]["coordinator"]["head"] is None
    assert state["topology"]["coordinator"]["head_state"] == "dangling"
    assert state["topology"]["selection"]["state"] == "selected"
    assert state["local"]["path"] == str(linked)
    assert state["local"]["head"] == head
    assert state["local"]["dirty"] is False

    _validate_repository_state_shape(
        state,
        expected_remote=state["remote_default_branch"],
        project_key="fixture/bare-coordinator",
        generated_at=datetime(2026, 7, 12, tzinfo=UTC),
    )


def test_bare_coordinator_selects_unique_clean_remote_default_worktree(
    tmp_path: Path,
) -> None:
    bare, head = _bare_repo(tmp_path)
    linked = tmp_path / "linked"
    _git(bare, "worktree", "add", str(linked), "main")

    state = observe_repository_state(
        bare,
        observed_at=datetime(2026, 7, 12, tzinfo=UTC),
        remote_default_branch=_remote_default(head),
    )

    assert state["state"] == "observed"
    assert state["local"]["path"] == str(linked)
    assert state["topology"]["selection"]["reason_code"] == "unique_remote_head_match"
    assert len(state["worktrees"]) == 2
    coordinator = next(item for item in state["worktrees"] if item["bare"])
    assert coordinator["state"] == "coordinator"
    assert coordinator["dirty"] is None


def test_multiple_remote_head_candidates_use_default_branch_tiebreak(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    detached = tmp_path / "detached"
    _git(repo, "worktree", "add", "--detach", str(detached), head)

    state = observe_repository_state(
        repo,
        observed_at=datetime(2026, 7, 12, tzinfo=UTC),
        remote_default_branch=_remote_default(head),
    )

    selection = state["topology"]["selection"]
    assert state["state"] == "observed"
    assert selection["state"] == "selected"
    assert selection["reason_code"] == "default_branch_tiebreak"
    assert selection["candidate_count"] == 2
    assert state["local"]["path"] == str(repo)


def test_recovery_tracking_does_not_impersonate_remote_default(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    recovery_head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-b", "remote-main")
    (repo / "remote.txt").write_text("remote\n")
    _git(repo, "add", "remote.txt")
    _git(repo, "commit", "-m", "remote default")
    remote_head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "main")
    _git(repo, "remote", "add", "origin", str(repo))
    _git(
        repo,
        "update-ref",
        "refs/remotes/origin/recovery/repo-main",
        recovery_head,
    )
    _git(repo, "branch", "--set-upstream-to=origin/recovery/repo-main", "main")

    state = observe_repository_state(
        repo,
        observed_at=datetime(2026, 7, 12, tzinfo=UTC),
        remote_default_branch=_remote_default(remote_head),
    )

    assert state["state"] == "unknown"
    assert state["reason_code"] == "remote_default_worktree_not_found"
    assert state["local"]["head"] == recovery_head
    assert state["local"]["upstream"] == "origin/recovery/repo-main"
    assert state["remote_default_branch"]["head_sha"] == remote_head


def test_bare_coordinator_missing_remote_evidence_is_precise_unknown(
    tmp_path: Path,
) -> None:
    bare, _head = _bare_repo(tmp_path)
    linked = tmp_path / "linked"
    _git(bare, "worktree", "add", str(linked), "main")

    state = observe_repository_state(
        bare,
        observed_at=datetime(2026, 7, 12, tzinfo=UTC),
    )

    assert state["state"] == "unknown"
    assert state["reason_code"] == "remote_default_branch_unavailable"
    assert state["topology"]["kind"] == "bare_coordinator"
    assert state["topology"]["selection"]["candidate_count"] == 0
    assert "local" not in state


def test_ambiguous_remote_default_worktrees_fail_closed(tmp_path: Path) -> None:
    bare, head = _bare_repo(tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"
    _git(bare, "worktree", "add", "--detach", str(first), head)
    _git(bare, "worktree", "add", "--detach", str(second), head)

    state = observe_repository_state(
        bare,
        observed_at=datetime(2026, 7, 12, tzinfo=UTC),
        remote_default_branch=_remote_default(head),
    )

    selection = state["topology"]["selection"]
    assert state["state"] == "unknown"
    assert state["reason_code"] == "ambiguous_remote_default_worktrees"
    assert selection["state"] == "unknown"
    assert selection["candidate_count"] == 2
    assert "local" not in state
