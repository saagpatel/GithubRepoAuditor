from __future__ import annotations

import subprocess
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from src.portfolio_repository_state import (
    _local_from_worktree,
    _observed_result,
    _select_remote_default_worktree,
    observe_repository_state,
)
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
    assert state["local"]["upstream_branch"] is None
    assert state["local"]["upstream_remote"] is None
    assert state["worktrees"][0]["upstream"] is None
    assert state["worktrees"][0]["upstream_branch"] is None
    assert state["worktrees"][0]["upstream_remote"] is None
    assert state["remote_default_branch"]["state"] == "unknown"


def test_local_branch_upstream_is_observed_and_divergence_fails_closed(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    _git(repo, "branch", "topic")
    _git(repo, "config", "branch.main.remote", ".")
    _git(repo, "config", "branch.main.merge", "refs/heads/topic")
    assert _git(repo, "rev-parse", "--abbrev-ref", "@{upstream}") == "topic"

    observed_at = datetime(2026, 7, 12, tzinfo=UTC)
    state = observe_repository_state(repo, observed_at=observed_at)

    assert state["local"]["upstream"] == "topic"
    assert state["local"]["upstream_branch"] == "topic"
    assert state["local"]["upstream_remote"] == "."
    assert state["state"] == "unknown"
    assert (
        state["reason_code"]
        == "nonstandard_upstream_requires_remote_default_evidence"
    )
    _validate_repository_state_shape(
        state,
        expected_remote=state["remote_default_branch"],
        project_key="fixture/local-upstream",
        generated_at=observed_at,
    )


def test_slash_branch_tracking_same_local_branch_stays_observed(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-b", "feature/foo")
    _git(repo, "config", "branch.feature/foo.remote", ".")
    _git(repo, "config", "branch.feature/foo.merge", "refs/heads/feature/foo")
    assert _git(repo, "rev-parse", "--abbrev-ref", "@{upstream}") == "feature/foo"

    observed_at = datetime(2026, 7, 12, tzinfo=UTC)
    state = observe_repository_state(repo, observed_at=observed_at)

    assert state["state"] == "observed"
    assert state["local"]["branch"] == "feature/foo"
    assert state["local"]["upstream"] == "feature/foo"
    assert state["local"]["upstream_branch"] == "feature/foo"
    assert state["local"]["upstream_remote"] == "."
    _validate_repository_state_shape(
        state,
        expected_remote=state["remote_default_branch"],
        project_key="fixture/matching-local-slash-upstream",
        generated_at=observed_at,
    )


def test_branch_tracking_different_local_slash_branch_is_unknown(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    _git(repo, "branch", "feature/foo")
    _git(repo, "checkout", "-b", "foo")
    _git(repo, "config", "branch.foo.remote", ".")
    _git(repo, "config", "branch.foo.merge", "refs/heads/feature/foo")
    assert _git(repo, "rev-parse", "--abbrev-ref", "@{upstream}") == "feature/foo"

    state = observe_repository_state(
        repo, observed_at=datetime(2026, 7, 12, tzinfo=UTC)
    )

    assert state["state"] == "unknown"
    assert state["local"]["branch"] == "foo"
    assert state["local"]["upstream"] == "feature/foo"
    assert state["local"]["upstream_branch"] == "feature/foo"
    assert state["local"]["upstream_remote"] == "."
    assert (
        state["reason_code"]
        == "nonstandard_upstream_requires_remote_default_evidence"
    )


@pytest.mark.parametrize("remote_name", ("origin", "team/origin"))
def test_remote_slash_branch_preserves_display_and_exact_branch(
    tmp_path: Path,
    remote_name: str,
) -> None:
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-b", "feature/foo")
    _git(repo, "remote", "add", remote_name, str(repo))
    _git(repo, "update-ref", f"refs/remotes/{remote_name}/feature/foo", "HEAD")
    _git(repo, "config", "branch.feature/foo.remote", remote_name)
    _git(repo, "config", "branch.feature/foo.merge", "refs/heads/feature/foo")
    expected_upstream = f"{remote_name}/feature/foo"
    assert _git(repo, "rev-parse", "--abbrev-ref", "@{upstream}") == (
        expected_upstream
    )

    observed_at = datetime(2026, 7, 12, tzinfo=UTC)
    state = observe_repository_state(repo, observed_at=observed_at)

    assert state["state"] == "observed"
    assert state["local"]["upstream"] == expected_upstream
    assert state["local"]["upstream_branch"] == "feature/foo"
    assert state["local"]["upstream_remote"] == remote_name
    _validate_repository_state_shape(
        state,
        expected_remote=state["remote_default_branch"],
        project_key="fixture/matching-remote-slash-upstream",
        generated_at=observed_at,
    )


def test_custom_fetch_refspec_serializes_configured_upstream_identity(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-b", "feature/foo")
    _git(repo, "remote", "add", "origin", str(repo))
    _git(
        repo,
        "config",
        "remote.origin.fetch",
        "+refs/heads/*:refs/custom/origin/*",
    )
    _git(repo, "fetch", "origin")
    _git(repo, "config", "branch.feature/foo.remote", "origin")
    _git(repo, "config", "branch.feature/foo.merge", "refs/heads/feature/foo")
    assert _git(repo, "rev-parse", "--abbrev-ref", "@{upstream}") == (
        "custom/origin/feature/foo"
    )

    observed_at = datetime(2026, 7, 12, tzinfo=UTC)
    state = observe_repository_state(repo, observed_at=observed_at)

    assert state["state"] == "observed"
    assert state["local"]["upstream"] == "origin/feature/foo"
    assert state["local"]["upstream_branch"] == "feature/foo"
    assert state["local"]["upstream_remote"] == "origin"
    assert state["local"]["ahead"] == 0
    assert state["local"]["behind"] == 0
    _validate_repository_state_shape(
        state,
        expected_remote=state["remote_default_branch"],
        project_key="fixture/custom-fetch-refspec",
        generated_at=observed_at,
    )


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
    assert state["local"]["upstream_branch"] == "recovery/repo-main"
    assert state["local"]["upstream_remote"] == "origin"
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

    _validate_repository_state_shape(
        state,
        expected_remote=state["remote_default_branch"],
        project_key="fixture/bare-unknown",
        generated_at=datetime(2026, 7, 12, tzinfo=UTC),
    )
    tampered = deepcopy(state)
    tampered["local"] = None
    with pytest.raises(ValueError, match="omit null local"):
        _validate_repository_state_shape(
            tampered,
            expected_remote=state["remote_default_branch"],
            project_key="fixture/bare-unknown",
            generated_at=datetime(2026, 7, 12, tzinfo=UTC),
        )


def test_remote_selection_can_choose_linked_when_configured_worktree_is_unknown() -> (
    None
):
    observed_at = datetime(2026, 7, 12, tzinfo=UTC)
    remote = _remote_default("b" * 40)
    unknown = {
        "state": "unknown",
        "reason_code": "worktree_observation_failed",
        "reason": "git could not observe the linked worktree",
        "path": "/demo-workspace/fixture/configured",
        "head": "a" * 40,
        "branch": "feature",
        "detached": False,
        "bare": False,
        "dirty": None,
        "dirty_path_count": None,
    }
    linked = {
        "state": "observed",
        "path": "/demo-workspace/fixture/linked",
        "head": "b" * 40,
        "branch": "main",
        "dirty": False,
        "dirty_path_count": 0,
        "upstream": "origin/main",
        "upstream_branch": "main",
        "upstream_remote": "origin",
        "upstream_observation_source": "local_tracking_ref",
        "ahead": 0,
        "behind": 0,
        "detached": False,
        "bare": False,
    }
    worktrees = [unknown, linked]
    selection = _select_remote_default_worktree(worktrees, remote)
    state = _observed_result(
        observed_at=observed_at,
        remote=remote,
        worktrees=worktrees,
        topology={
            "kind": "working_repository",
            "configured_path": unknown["path"],
            "worktree_count": 2,
            "linked_worktree_count": 1,
            "selection": selection,
        },
        local=_local_from_worktree(linked),
    )

    _validate_repository_state_shape(
        state,
        expected_remote=remote,
        project_key="fixture/configured",
        generated_at=observed_at,
    )

    wrong_reason = deepcopy(state)
    wrong_reason["worktrees"][0]["reason"] = "different failure"
    with pytest.raises(ValueError, match="worktree 0"):
        _validate_repository_state_shape(
            wrong_reason,
            expected_remote=remote,
            project_key="fixture/configured",
            generated_at=observed_at,
        )


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
