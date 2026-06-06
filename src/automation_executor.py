"""Gated executor for bounded automation (Arc D, phase 3).

This is the only layer that mutates real repos, so it is built to be safe by
construction:

* every git/gh interaction goes through an injected ``CommandRunner`` (real
  subprocess in production, a fake in tests);
* ``require_approved`` is the hard pre-gate — an unapproved proposal never runs;
* ``dry_run`` defaults to ``True`` — callers must opt in to apply;
* context-PR work refuses the default/protected branch, never uses ``--force``,
  skips dirty worktrees and non-git repos, and aborts fast on the first failed
  command (so a failed commit never reaches push/PR);
* catalog-seed work is local + reversible and only fills missing fields.

Content generation (the managed block, the catalog seed dict) is supplied by the
caller via ``ExecutionPlan.apply_change`` / the ``seeds`` argument, computed fresh
at execution time — phase-3b wires those to the existing recovery primitives.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from src.automation_proposals import AutomationProposal, require_approved

CONTRACT_VERSION = "automation_execution_v1"

# Branches the executor will never commit automation onto.
PROTECTED_BRANCHES = frozenset({"main", "master"})

# A safe feature-branch name: alphanumeric/dot/underscore first char (never a
# leading '-', which git/gh would parse as a flag), then word/./_/-/ characters.
_SAFE_BRANCH = re.compile(r"^[A-Za-z0-9._][A-Za-z0-9._/-]*$")

_GIT_TIMEOUT_SECONDS = 120


class AutomationExecutionError(RuntimeError):
    """Raised when an execution safety rail (e.g. branch policy) is violated."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


# (args, cwd) -> CommandResult. Injected so tests never touch git/gh/network.
CommandRunner = Callable[[list[str], Path], CommandResult]


def default_command_runner(args: list[str], cwd: Path) -> CommandResult:
    """Run a command via subprocess (the production ``CommandRunner``)."""
    proc = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT_SECONDS,
        check=False,
    )
    return CommandResult(proc.returncode, proc.stdout, proc.stderr)


@dataclass(frozen=True)
class ExecutionPlan:
    """The concrete change to apply for one context-PR proposal.

    ``apply_change`` writes the file changes into ``repo_path`` (computed fresh
    by the caller); the executor handles all git/gh mechanics around it.
    """

    repo_path: Path
    default_branch: str
    branch_name: str
    commit_message: str
    pr_title: str
    pr_body: str
    apply_change: Callable[[Path], None]
    has_git: bool = True


@dataclass(frozen=True)
class ExecutionResult:
    proposal_id: str
    outcome: str  # applied | dry-run | skipped | failed
    detail: str
    reference: str = ""
    commands: tuple[str, ...] = ()


def _dirty_worktree(repo_path: Path, runner: CommandRunner) -> bool:
    result = runner(["git", "status", "--porcelain"], repo_path)
    if result.returncode != 0:
        # A failed status check is treated as "do not touch" (conservative).
        return True
    return bool(result.stdout.strip())


def execute_context_pr(
    proposal: AutomationProposal,
    plan: ExecutionPlan,
    *,
    dry_run: bool = True,
    runner: CommandRunner = default_command_runner,
) -> ExecutionResult:
    """Open a context-improvement PR for an APPROVED proposal, behind every rail."""
    require_approved(proposal)  # hard gate — raises if not approved

    branch = plan.branch_name.strip()
    default_branch = plan.default_branch.strip()
    if not branch:
        raise AutomationExecutionError("branch_name must be non-empty")
    if not default_branch:
        raise AutomationExecutionError("default_branch must be non-empty")
    if not _SAFE_BRANCH.match(branch):
        # Rejects leading '-' (flag injection into git/gh) and whitespace.
        raise AutomationExecutionError(f"unsafe branch name {branch!r}")
    if branch.lower() in PROTECTED_BRANCHES or branch.lower() == default_branch.lower():
        raise AutomationExecutionError(
            f"refusing to commit automation onto protected/default branch {branch!r}"
        )

    if not plan.has_git:
        return ExecutionResult(proposal.proposal_id, "skipped", "no-git-repo")

    planned = [
        f"git checkout -b {branch}",
        "<apply managed-context change>",
        "git add -A",
        f"git commit -m {plan.commit_message!r}",
        f"git push -u origin {branch}",
        f"gh pr create --base {default_branch} --head {branch} ...",
    ]

    if _dirty_worktree(plan.repo_path, runner):
        return ExecutionResult(proposal.proposal_id, "skipped", "dirty-worktree")

    if dry_run:
        return ExecutionResult(
            proposal.proposal_id,
            "dry-run",
            f"Would open a PR on branch {branch}.",
            commands=tuple(planned),
        )

    # Run checkout first, then apply the change, then stage/commit/push/PR.
    checkout = runner(["git", "checkout", "-b", branch], plan.repo_path)
    if checkout.returncode != 0:
        return ExecutionResult(
            proposal.proposal_id, "failed", f"checkout: {checkout.stderr}".strip()
        )

    try:
        plan.apply_change(plan.repo_path)
    except Exception as error:  # noqa: BLE001 - surface as a failed result, not a strand
        # The change failed after the branch was created; best-effort return to
        # the default branch and delete the just-created branch so the repo is
        # not stranded on a partial branch and a retry isn't blocked by an
        # "already exists" orphan.
        runner(["git", "checkout", default_branch], plan.repo_path)
        runner(["git", "branch", "-D", branch], plan.repo_path)
        return ExecutionResult(proposal.proposal_id, "failed", f"apply-change: {error}".strip())

    for args in (
        ["git", "add", "-A"],
        ["git", "commit", "-m", plan.commit_message],
        ["git", "push", "-u", "origin", branch],
    ):
        result = runner(args, plan.repo_path)
        if result.returncode != 0:
            return ExecutionResult(
                proposal.proposal_id, "failed", f"{args[1]}: {result.stderr}".strip()
            )

    pr = runner(
        [
            "gh",
            "pr",
            "create",
            "--base",
            default_branch,
            "--head",
            branch,
            "--title",
            plan.pr_title,
            "--body",
            plan.pr_body,
        ],
        plan.repo_path,
    )
    if pr.returncode != 0:
        return ExecutionResult(proposal.proposal_id, "failed", f"gh pr create: {pr.stderr}".strip())

    # gh prints the PR URL on success. If it somehow reported success with no
    # URL, the PR was still created (rc 0) so we must not fail and re-run (that
    # would duplicate it) — but surface the missing reference in the detail
    # rather than silently recording an empty audit ref.
    pr_url = pr.stdout.strip()
    detail = (
        f"Opened PR on branch {branch}."
        if pr_url
        else f"Opened PR on branch {branch} (gh returned no PR URL)."
    )
    return ExecutionResult(
        proposal.proposal_id,
        "applied",
        detail,
        reference=pr_url,
    )


def execute_catalog_seed(
    proposal: AutomationProposal,
    *,
    catalog_path: Path,
    seeds: dict[str, dict[str, str]],
    dry_run: bool = True,
    apply_seeds: Callable[[Path, dict[str, dict[str, str]]], None] | None = None,
) -> ExecutionResult:
    """Apply catalog seed updates for an APPROVED proposal (local + reversible)."""
    require_approved(proposal)  # hard gate

    repo_keys = ", ".join(sorted(seeds)) or "(none)"
    if dry_run:
        return ExecutionResult(
            proposal.proposal_id,
            "dry-run",
            f"Would fill missing catalog fields for: {repo_keys}.",
        )

    if apply_seeds is None:
        from src.portfolio_context_recovery import _merge_catalog_seeds

        apply_seeds = _merge_catalog_seeds
    apply_seeds(catalog_path, seeds)
    return ExecutionResult(
        proposal.proposal_id,
        "applied",
        f"Filled missing catalog fields for: {repo_keys}.",
        reference=str(catalog_path),
    )
