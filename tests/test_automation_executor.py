"""Tests for the Arc D phase-3 gated executor.

Every git/gh interaction goes through an injected ``CommandRunner``, so these
tests verify the exact command sequence and every safety rail (approval gate,
never-default-branch, never-force, skip-dirty, dry-run default, fail-fast) with
no real repository or network involved.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.automation_executor import (
    AutomationExecutionError,
    CommandResult,
    ExecutionPlan,
    execute_catalog_seed,
    execute_context_pr,
)
from src.automation_proposals import (
    ACTION_CATALOG_SEED,
    ACTION_CONTEXT_PR,
    STATUS_APPROVED,
    STATUS_EXECUTED,
    STATUS_PENDING,
    AutomationProposal,
    ProposalApprovalError,
    ProposalNotFoundError,
    mark_executed,
)

NOW = "2026-04-14T12:00:00+00:00"


class FakeRunner:
    """Records every command and returns canned results keyed by the first 2 args."""

    def __init__(self, results: dict[tuple[str, ...], CommandResult] | None = None) -> None:
        self.calls: list[tuple[list[str], Path]] = []
        self._results = results or {}

    def __call__(self, args: list[str], cwd: Path) -> CommandResult:
        self.calls.append((list(args), cwd))
        key = tuple(args[:2])
        return self._results.get(key, CommandResult(returncode=0, stdout="", stderr=""))

    @property
    def command_args(self) -> list[list[str]]:
        return [args for args, _ in self.calls]


def _approved(action_type: str = ACTION_CONTEXT_PR) -> AutomationProposal:
    return AutomationProposal(
        proposal_id=f"{action_type}:owner/Repo",
        action_type=action_type,
        display_name="Repo",
        repo_full_name="owner/Repo",
        description="d",
        status=STATUS_APPROVED,
        created_at=NOW,
    )


def _plan(tmp_path: Path, applied: list[Path], **overrides) -> ExecutionPlan:
    defaults = dict(
        repo_path=tmp_path,
        default_branch="main",
        branch_name="auto/context-repo",
        commit_message="docs: refresh managed context block",
        pr_title="docs: refresh managed context block",
        pr_body="Automated context improvement.",
        apply_change=lambda path: applied.append(path),
        has_git=True,
    )
    defaults.update(overrides)
    return ExecutionPlan(**defaults)


# --- approval gate ---------------------------------------------------------


def test_context_pr_requires_approved_proposal(tmp_path: Path) -> None:
    pending = AutomationProposal(
        proposal_id="context-pr:owner/Repo",
        action_type=ACTION_CONTEXT_PR,
        display_name="Repo",
        repo_full_name="owner/Repo",
        description="d",
        status=STATUS_PENDING,
    )
    runner = FakeRunner()
    with pytest.raises(ProposalApprovalError):
        execute_context_pr(pending, _plan(tmp_path, []), dry_run=False, runner=runner)
    assert runner.calls == []  # nothing ran


# --- never the default branch ----------------------------------------------


@pytest.mark.parametrize("branch", ["main", "master"])
def test_context_pr_refuses_protected_branch(tmp_path: Path, branch: str) -> None:
    runner = FakeRunner()
    with pytest.raises(AutomationExecutionError):
        execute_context_pr(
            _approved(), _plan(tmp_path, [], branch_name=branch), dry_run=False, runner=runner
        )
    assert runner.calls == []


def test_context_pr_refuses_branch_equal_to_default(tmp_path: Path) -> None:
    runner = FakeRunner()
    with pytest.raises(AutomationExecutionError):
        execute_context_pr(
            _approved(),
            _plan(tmp_path, [], default_branch="develop", branch_name="develop"),
            dry_run=False,
            runner=runner,
        )


def test_context_pr_refuses_empty_branch(tmp_path: Path) -> None:
    runner = FakeRunner()
    with pytest.raises(AutomationExecutionError):
        execute_context_pr(
            _approved(), _plan(tmp_path, [], branch_name=""), dry_run=False, runner=runner
        )


@pytest.mark.parametrize("branch", ["Main", "MASTER"])
def test_context_pr_protected_branch_guard_is_case_insensitive(tmp_path: Path, branch: str) -> None:
    runner = FakeRunner()
    with pytest.raises(AutomationExecutionError):
        execute_context_pr(
            _approved(), _plan(tmp_path, [], branch_name=branch), dry_run=False, runner=runner
        )
    assert runner.calls == []


def test_context_pr_refuses_branch_equal_to_default_case_insensitive(tmp_path: Path) -> None:
    runner = FakeRunner()
    with pytest.raises(AutomationExecutionError):
        execute_context_pr(
            _approved(),
            _plan(tmp_path, [], default_branch="Develop", branch_name="develop"),
            dry_run=False,
            runner=runner,
        )


@pytest.mark.parametrize("branch", ["--force", "-q", "has space", "--head"])
def test_context_pr_refuses_flag_like_or_unsafe_branch(tmp_path: Path, branch: str) -> None:
    runner = FakeRunner()
    with pytest.raises(AutomationExecutionError):
        execute_context_pr(
            _approved(), _plan(tmp_path, [], branch_name=branch), dry_run=False, runner=runner
        )
    assert runner.calls == []


def test_context_pr_refuses_empty_default_branch(tmp_path: Path) -> None:
    runner = FakeRunner()
    with pytest.raises(AutomationExecutionError):
        execute_context_pr(
            _approved(), _plan(tmp_path, [], default_branch=""), dry_run=False, runner=runner
        )


def test_context_pr_apply_change_failure_returns_failed_and_restores_branch(
    tmp_path: Path,
) -> None:
    runner = FakeRunner()

    def boom(_path: Path) -> None:
        raise OSError("disk full")

    plan = _plan(tmp_path, [], apply_change=boom)
    result = execute_context_pr(_approved(), plan, dry_run=False, runner=runner)
    assert result.outcome == "failed"
    assert "disk full" in result.detail
    # Best-effort restore to the default branch; never reaches commit/push/PR.
    assert ["git", "checkout", "main"] in runner.command_args
    # The orphan branch is deleted so a retry isn't blocked by "already exists".
    assert ["git", "branch", "-D", "auto/context-repo"] in runner.command_args
    assert not any(args[:2] == ["git", "commit"] for args in runner.command_args)
    assert not any(args[:2] == ["gh", "pr"] for args in runner.command_args)


# --- skip rails ------------------------------------------------------------


def test_context_pr_skips_dirty_worktree(tmp_path: Path) -> None:
    runner = FakeRunner({("git", "status"): CommandResult(0, " M file.py\n")})
    applied: list[Path] = []
    result = execute_context_pr(_approved(), _plan(tmp_path, applied), dry_run=False, runner=runner)
    assert result.outcome == "skipped"
    assert "dirty" in result.detail
    assert applied == []  # change never applied
    # Only the read-only status check ran; no mutating commands.
    assert runner.command_args == [["git", "status", "--porcelain"]]


def test_context_pr_skips_when_no_git(tmp_path: Path) -> None:
    runner = FakeRunner()
    applied: list[Path] = []
    result = execute_context_pr(
        _approved(), _plan(tmp_path, applied, has_git=False), dry_run=False, runner=runner
    )
    assert result.outcome == "skipped"
    assert applied == []
    assert runner.calls == []


# --- dry run (default) -----------------------------------------------------


def test_context_pr_dry_run_is_default_and_mutates_nothing(tmp_path: Path) -> None:
    runner = FakeRunner()
    applied: list[Path] = []
    result = execute_context_pr(
        _approved(), _plan(tmp_path, applied), runner=runner
    )  # no dry_run arg
    assert result.outcome == "dry-run"
    assert applied == []
    # Only the read-only dirty check ran; planned commands are reported, not run.
    assert runner.command_args == [["git", "status", "--porcelain"]]
    assert any("gh pr create" in cmd for cmd in result.commands)
    assert any("checkout -b auto/context-repo" in cmd for cmd in result.commands)


# --- apply -----------------------------------------------------------------


def test_context_pr_apply_runs_full_sequence_and_opens_pr(tmp_path: Path) -> None:
    runner = FakeRunner({("gh", "pr"): CommandResult(0, "https://github.com/owner/Repo/pull/7\n")})
    applied: list[Path] = []
    result = execute_context_pr(_approved(), _plan(tmp_path, applied), dry_run=False, runner=runner)
    assert result.outcome == "applied"
    assert result.reference == "https://github.com/owner/Repo/pull/7"
    assert applied == [tmp_path]  # change applied exactly once

    cmds = runner.command_args
    assert cmds == [
        ["git", "status", "--porcelain"],
        ["git", "checkout", "-b", "auto/context-repo"],
        ["git", "add", "-A"],
        ["git", "commit", "-m", "docs: refresh managed context block"],
        ["git", "push", "-u", "origin", "auto/context-repo"],
        [
            "gh",
            "pr",
            "create",
            "--base",
            "main",
            "--head",
            "auto/context-repo",
            "--title",
            "docs: refresh managed context block",
            "--body",
            "Automated context improvement.",
        ],
    ]


def test_context_pr_applied_with_no_pr_url_surfaces_missing_reference(tmp_path: Path) -> None:
    # gh reports success (rc 0) but prints no URL: the PR was created, so the
    # outcome stays "applied" (re-running would duplicate it), but the empty
    # reference is made visible in the detail rather than silently recorded.
    runner = FakeRunner({("gh", "pr"): CommandResult(0, "")})
    result = execute_context_pr(_approved(), _plan(tmp_path, []), dry_run=False, runner=runner)
    assert result.outcome == "applied"
    assert result.reference == ""
    assert "no PR URL" in result.detail


def test_context_pr_never_uses_force(tmp_path: Path) -> None:
    runner = FakeRunner()
    execute_context_pr(_approved(), _plan(tmp_path, []), dry_run=False, runner=runner)
    flat = [token for args in runner.command_args for token in args]
    assert not any("force" in token for token in flat)


def test_context_pr_apply_change_runs_after_branch_before_add(tmp_path: Path) -> None:
    order: list[str] = []

    def record_runner(args: list[str], cwd: Path) -> CommandResult:
        order.append(" ".join(args[:2]))
        return CommandResult(0, "")

    plan = _plan(tmp_path, [], apply_change=lambda path: order.append("APPLY"))
    execute_context_pr(_approved(), plan, dry_run=False, runner=record_runner)
    assert order.index("git checkout") < order.index("APPLY") < order.index("git add")


def test_context_pr_aborts_on_commit_failure(tmp_path: Path) -> None:
    runner = FakeRunner({("git", "commit"): CommandResult(1, "", "nothing to commit")})
    result = execute_context_pr(_approved(), _plan(tmp_path, []), dry_run=False, runner=runner)
    assert result.outcome == "failed"
    assert "nothing to commit" in result.detail
    # push / pr create must NOT run after a failed commit.
    assert ["git", "push", "-u", "origin", "auto/context-repo"] not in runner.command_args
    assert not any(args[:2] == ["gh", "pr"] for args in runner.command_args)


# --- catalog seed (local, reversible) --------------------------------------


def test_catalog_seed_requires_approved(tmp_path: Path) -> None:
    pending = AutomationProposal(
        proposal_id="catalog-seed:owner/Repo",
        action_type=ACTION_CATALOG_SEED,
        display_name="Repo",
        repo_full_name="owner/Repo",
        description="d",
        status=STATUS_PENDING,
    )
    with pytest.raises(ProposalApprovalError):
        execute_catalog_seed(
            pending,
            catalog_path=tmp_path / "catalog.yaml",
            seeds={"repo": {"path_confidence": "high"}},
            dry_run=False,
        )


def test_catalog_seed_dry_run_does_not_write(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.yaml"
    result = execute_catalog_seed(
        _approved(ACTION_CATALOG_SEED),
        catalog_path=catalog,
        seeds={"repo": {"path_confidence": "high"}},
    )  # dry_run defaults True
    assert result.outcome == "dry-run"
    assert not catalog.exists()


def test_catalog_seed_apply_writes_only_missing_fields(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text("repos:\n  repo:\n    purpose: existing\n")
    result = execute_catalog_seed(
        _approved(ACTION_CATALOG_SEED),
        catalog_path=catalog,
        seeds={"repo": {"path_confidence": "high", "purpose": "should-not-overwrite"}},
        dry_run=False,
    )
    assert result.outcome == "applied"
    text = catalog.read_text()
    assert "path_confidence: high" in text
    assert "purpose: existing" in text  # never overwritten
    assert "should-not-overwrite" not in text


# --- mark_executed lifecycle ----------------------------------------------


def test_mark_executed_transitions_approved_to_executed() -> None:
    proposals = [_approved()]
    updated = mark_executed(
        proposals,
        "context-pr:owner/Repo",
        executed_at=NOW,
        execution_ref="https://github.com/owner/Repo/pull/7",
    )
    [proposal] = updated
    assert proposal.status == STATUS_EXECUTED
    assert proposal.executed_at == NOW
    assert proposal.execution_ref == "https://github.com/owner/Repo/pull/7"


def test_mark_executed_rejects_non_approved() -> None:
    pending = AutomationProposal(
        proposal_id="context-pr:owner/Repo",
        action_type=ACTION_CONTEXT_PR,
        display_name="Repo",
        repo_full_name="owner/Repo",
        description="d",
        status=STATUS_PENDING,
    )
    with pytest.raises(ProposalApprovalError):
        mark_executed([pending], "context-pr:owner/Repo", executed_at=NOW, execution_ref="x")


def test_mark_executed_unknown_id_raises() -> None:
    with pytest.raises(ProposalNotFoundError):
        mark_executed([], "context-pr:ghost", executed_at=NOW, execution_ref="x")
