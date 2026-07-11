from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.producer_preflight import (
    ProducerEvidence,
    inspect_canonical_producer,
    verify_evidence_still_current,
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "tests@example.invalid")
    _git(repo, "config", "user.name", "Tests")
    (repo / "README.md").write_text("fixture\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "fixture")
    _git(repo, "remote", "add", "origin", "git@github.com:saagpatel/GithubRepoAuditor.git")
    commit = _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-ref", "refs/remotes/origin/main", commit)
    return repo, commit


def test_canonical_producer_passes_for_clean_matching_ref(tmp_path: Path) -> None:
    repo, commit = _repo(tmp_path)
    result = inspect_canonical_producer(
        repo_root=repo,
        expected_repository="saagpatel/GithubRepoAuditor",
        expected_ref="refs/remotes/origin/main",
        checkout_role="canonical-automation",
        now=datetime(2026, 7, 10, tzinfo=UTC),
    )
    assert result.state == "pass"
    assert result.evidence is not None
    assert result.evidence.commit == commit
    assert all(state == "pass" for state in result.checks.values())


def test_canonical_producer_fails_dirty_worktree(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    (repo / "untracked.txt").write_text("dirty\n")
    result = inspect_canonical_producer(
        repo_root=repo,
        expected_repository="saagpatel/GithubRepoAuditor",
        expected_ref="refs/remotes/origin/main",
        checkout_role="canonical-automation",
    )
    assert result.state == "fail"
    assert result.checks["worktree_clean"] == "fail"


def test_canonical_producer_missing_ref_is_unknown(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    result = inspect_canonical_producer(
        repo_root=repo,
        expected_repository="saagpatel/GithubRepoAuditor",
        expected_ref="refs/remotes/origin/missing",
        checkout_role="canonical-automation",
    )
    assert result.state == "unknown"


def test_evidence_rejects_head_change(tmp_path: Path) -> None:
    repo, commit = _repo(tmp_path)
    evidence = ProducerEvidence(
        repository="saagpatel/GithubRepoAuditor",
        commit=commit,
        ref="refs/remotes/origin/main",
        checkout_role="canonical-automation",
        worktree_clean=True,
        verified_at=datetime.now(UTC),
    )
    (repo / "README.md").write_text("changed\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "move head")
    with pytest.raises(ValueError, match="HEAD changed after preflight"):
        verify_evidence_still_current(repo, evidence)
