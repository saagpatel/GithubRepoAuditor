"""Tests for the Arc D phase-3b automation workflow (content-gen + orchestrator).

This is the wiring layer: it binds the gated executor (phase 3a) to the
recovery content primitives and drives the
load -> filter-approved -> plan -> execute -> mark-executed -> save loop.

The executor's own safety rails are covered in ``test_automation_executor.py``;
here we verify the *wiring* — that approved proposals get a correct plan/seed,
that only real applies transition + persist, and that the slug / resolution
policies hold.  No real git or network is touched: every command goes through an
injected ``FakeRunner``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.automation_executor import AutomationExecutionError, CommandResult
from src.automation_proposals import (
    ACTION_CATALOG_SEED,
    ACTION_CONTEXT_PR,
    STATUS_APPROVED,
    STATUS_EXECUTED,
    STATUS_PENDING,
    STATUS_REJECTED,
    AutomationProposal,
    load_proposals,
    save_proposals,
)
from src.automation_workflow import (
    build_catalog_seeds_for,
    build_context_pr_plan,
    execute_approved_proposals,
)
from src.portfolio_context_contract import MANAGED_CONTEXT_START
from src.portfolio_truth_types import (
    DeclaredFields,
    DerivedFields,
    IdentityFields,
    PortfolioTruthProject,
    PortfolioTruthSnapshot,
)

NOW = "2026-04-14T12:00:00+00:00"


class FakeRunner:
    """Records every command, returns canned results keyed by the first 2 args."""

    def __init__(
        self, results: dict[tuple[str, ...], CommandResult] | None = None
    ) -> None:
        self.calls: list[tuple[list[str], Path]] = []
        self._results = results or {}

    def __call__(self, args: list[str], cwd: Path) -> CommandResult:
        self.calls.append((list(args), cwd))
        return self._results.get(tuple(args[:2]), CommandResult(returncode=0))

    @property
    def command_args(self) -> list[list[str]]:
        return [args for args, _ in self.calls]


def _project(
    *,
    display_name: str = "MyRepo",
    path: str = "MyRepo",
    repo_full_name: str = "owner/MyRepo",
    has_git: bool = True,
    primary_context_file: str = "AGENTS.md",
    default_branch: str = "",
    repository_state: dict | None = None,
) -> PortfolioTruthProject:
    return PortfolioTruthProject(
        identity=IdentityFields(
            project_key=display_name.lower(),
            display_name=display_name,
            path=path,
            top_level_dir=path,
            group_key="g",
            group_label="G",
            section_marker="m",
            section_label="M",
            has_git=has_git,
            repo_full_name=repo_full_name,
            default_branch=default_branch,
        ),
        declared=DeclaredFields(purpose=f"{display_name} does things."),
        derived=DerivedFields(
            context_quality="minimum-viable",
            primary_context_file=primary_context_file,
            activity_status="active",
            archived=False,
            path_confidence="high",
        ),
        repository_state=repository_state or {},
    )


def _snapshot(*projects: PortfolioTruthProject) -> PortfolioTruthSnapshot:
    from datetime import datetime, timezone

    return PortfolioTruthSnapshot(
        schema_version="0.5.0",
        generated_at=datetime(2026, 4, 14, tzinfo=timezone.utc),
        workspace_root="/ws",
        source_summary={},
        precedence_matrix={},
        warnings=[],
        projects=list(projects),
    )


def _proposal(
    *,
    action_type: str = ACTION_CONTEXT_PR,
    display_name: str = "MyRepo",
    repo_full_name: str = "owner/MyRepo",
    status: str = STATUS_APPROVED,
) -> AutomationProposal:
    return AutomationProposal(
        proposal_id=f"{action_type}:{repo_full_name or display_name}",
        action_type=action_type,
        display_name=display_name,
        repo_full_name=repo_full_name,
        description="d",
        status=status,
        created_at=NOW,
    )


def _write(proposals_path: Path, *proposals: AutomationProposal) -> None:
    save_proposals(proposals_path, proposals)


# --- build_context_pr_plan -------------------------------------------------


def test_context_pr_plan_carries_repo_path_and_safe_branch() -> None:
    project = _project(path="nested/MyRepo", repo_full_name="owner/My Repo")
    plan = build_context_pr_plan(project, workspace_root=Path("/ws"))

    assert plan.repo_path == Path("/ws/nested/MyRepo")
    assert plan.default_branch == "main"
    assert plan.has_git is True
    # Spaced/odd slug is sanitized to a safe, lowercased, non-flag branch name.
    assert plan.branch_name == "auto/context-my-repo"
    assert not plan.branch_name.startswith("-")


def test_context_pr_plan_respects_branch_prefix_and_default_branch() -> None:
    plan = build_context_pr_plan(
        _project(),
        workspace_root=Path("/ws"),
        branch_prefix="bot/ctx-",
        default_branch="trunk",
    )
    assert plan.branch_name == "bot/ctx-myrepo"
    assert plan.default_branch == "trunk"


def test_context_pr_plan_uses_repo_detected_default_branch() -> None:
    # No explicit override: the repo's own detected default branch drives the
    # PR base instead of the blanket "main".
    plan = build_context_pr_plan(
        _project(default_branch="develop"),
        workspace_root=Path("/ws"),
    )
    assert plan.default_branch == "develop"


def test_context_pr_plan_explicit_branch_overrides_repo_default() -> None:
    # An explicit caller override wins over the repo's detected default branch.
    plan = build_context_pr_plan(
        _project(default_branch="develop"),
        workspace_root=Path("/ws"),
        default_branch="trunk",
    )
    assert plan.default_branch == "trunk"


def test_context_pr_plan_blocks_unknown_checkout_authority() -> None:
    project = _project(
        repository_state={
            "checkout_authority": {
                "schema_version": "CheckoutCollisionV1",
                "selection": {
                    "state": "unknown",
                    "reason_code": "conflicting_full_clone_heads",
                    "representative_path": "MyRepo",
                    "selected_path": None,
                }
            }
        }
    )

    with pytest.raises(
        AutomationExecutionError,
        match="checkout-authority-unknown:conflicting_full_clone_heads",
    ):
        build_context_pr_plan(project, workspace_root=Path("/ws"))


def test_context_pr_plan_blocks_selected_path_mismatch() -> None:
    project = _project(
        repository_state={
            "checkout_authority": {
                "schema_version": "CheckoutCollisionV1",
                "selection": {
                    "state": "selected",
                    "reason_code": "equivalent_full_clones",
                    "representative_path": "Archive/MyRepo",
                    "selected_path": "Archive/MyRepo",
                }
            }
        }
    )

    with pytest.raises(
        AutomationExecutionError,
        match="checkout-authority-path-mismatch",
    ):
        build_context_pr_plan(project, workspace_root=Path("/ws"))


def test_context_pr_plan_uses_selected_checkout_without_replacing_identity() -> None:
    project = _project(
        display_name="Repo",
        path="Repo",
        repo_full_name="owner/Repo",
        repository_state={
            "checkout_authority": {
                "schema_version": "CheckoutCollisionV1",
                "canonical_project_path": "Repo",
                "selection": {
                    "state": "selected",
                    "reason_code": "single_clone_topology",
                    "representative_path": "_codex-worktrees/repo-main",
                    "selected_path": "_codex-worktrees/repo-main",
                },
                "checkouts": [
                    {
                        "path": "_codex-worktrees/repo-main",
                        "state": "observed",
                        "relation": "representative",
                        "bare": False,
                    }
                ],
            }
        },
    )

    plan = build_context_pr_plan(project, workspace_root=Path("/ws"))

    assert project.identity.display_name == "Repo"
    assert project.identity.path == "Repo"
    assert plan.repo_path == Path("/ws/_codex-worktrees/repo-main")


def test_context_pr_plan_apply_change_writes_managed_block(tmp_path: Path) -> None:
    project = _project(path="MyRepo")
    repo_path = tmp_path / "MyRepo"
    repo_path.mkdir()
    plan = build_context_pr_plan(project, workspace_root=tmp_path)

    plan.apply_change(repo_path)

    written = (repo_path / "AGENTS.md").read_text()
    assert MANAGED_CONTEXT_START in written


def test_context_pr_plan_apply_change_preserves_existing_text(tmp_path: Path) -> None:
    project = _project(path="MyRepo")
    repo_path = tmp_path / "MyRepo"
    repo_path.mkdir()
    (repo_path / "AGENTS.md").write_text("# Hand-written intro\n\nKeep me.\n")
    plan = build_context_pr_plan(project, workspace_root=tmp_path)

    plan.apply_change(repo_path)

    written = (repo_path / "AGENTS.md").read_text()
    assert "Keep me." in written
    assert MANAGED_CONTEXT_START in written


# --- build_catalog_seeds_for -----------------------------------------------


def test_catalog_seeds_keyed_by_display_name() -> None:
    project = _project(
        display_name="Signal & Noise", repo_full_name="owner/signal-noise"
    )
    seeds = build_catalog_seeds_for(project)

    assert set(seeds) == {"Signal & Noise"}
    assert seeds["Signal & Noise"]["owner"]  # seed carries the derived owner field


# --- execute_approved_proposals: gate + dry-run ----------------------------


def test_execute_ignores_non_approved(tmp_path: Path) -> None:
    proposals_path = tmp_path / "pending-proposals.json"
    _write(
        proposals_path,
        _proposal(status=STATUS_PENDING),
        _proposal(action_type=ACTION_CATALOG_SEED, status=STATUS_REJECTED),
    )
    results = execute_approved_proposals(
        proposals_path=proposals_path,
        snapshot=_snapshot(_project()),
        workspace_root=tmp_path,
        catalog_path=tmp_path / "catalog.yaml",
        executed_at=NOW,
    )
    assert results == []


def test_execute_dry_run_does_not_mutate_queue(tmp_path: Path) -> None:
    proposals_path = tmp_path / "pending-proposals.json"
    _write(proposals_path, _proposal())
    (tmp_path / "MyRepo").mkdir()

    results = execute_approved_proposals(
        proposals_path=proposals_path,
        snapshot=_snapshot(_project()),
        workspace_root=tmp_path,
        catalog_path=tmp_path / "catalog.yaml",
        executed_at=NOW,
        runner=FakeRunner(),
    )

    assert [r.outcome for r in results] == ["dry-run"]
    # Queue is untouched — proposal stays APPROVED, never transitions.
    assert load_proposals(proposals_path)[0].status == STATUS_APPROVED


# --- execute_approved_proposals: real context-PR run -----------------------


def test_execute_context_pr_applies_and_persists_executed(tmp_path: Path) -> None:
    proposals_path = tmp_path / "pending-proposals.json"
    _write(proposals_path, _proposal())
    (tmp_path / "MyRepo").mkdir()
    runner = FakeRunner(
        {("gh", "pr"): CommandResult(0, "https://github.com/owner/MyRepo/pull/1\n")}
    )

    results = execute_approved_proposals(
        proposals_path=proposals_path,
        snapshot=_snapshot(_project()),
        workspace_root=tmp_path,
        catalog_path=tmp_path / "catalog.yaml",
        executed_at=NOW,
        dry_run=False,
        runner=runner,
    )

    assert [r.outcome for r in results] == ["applied"]
    assert results[0].reference == "https://github.com/owner/MyRepo/pull/1"
    # Managed block actually written on the new branch.
    assert MANAGED_CONTEXT_START in (tmp_path / "MyRepo" / "AGENTS.md").read_text()
    # Real apply transitions + persists EXECUTED with the PR ref + timestamp.
    persisted = load_proposals(proposals_path)[0]
    assert persisted.status == STATUS_EXECUTED
    assert persisted.executed_at == NOW
    assert persisted.execution_ref == "https://github.com/owner/MyRepo/pull/1"
    # Never commits onto the default branch — checks out a feature branch first.
    assert ["git", "checkout", "-b", "auto/context-myrepo"] in runner.command_args


def test_execute_failed_push_keeps_proposal_approved(tmp_path: Path) -> None:
    proposals_path = tmp_path / "pending-proposals.json"
    _write(proposals_path, _proposal())
    (tmp_path / "MyRepo").mkdir()
    runner = FakeRunner({("git", "push"): CommandResult(1, "", "remote rejected")})

    results = execute_approved_proposals(
        proposals_path=proposals_path,
        snapshot=_snapshot(_project()),
        workspace_root=tmp_path,
        catalog_path=tmp_path / "catalog.yaml",
        executed_at=NOW,
        dry_run=False,
        runner=runner,
    )

    assert results[0].outcome == "failed"
    # Failed apply never transitions — operator can retry.
    assert load_proposals(proposals_path)[0].status == STATUS_APPROVED


# --- execute_approved_proposals: catalog-seed real run ---------------------


def test_execute_catalog_seed_applies_and_persists_executed(tmp_path: Path) -> None:
    proposals_path = tmp_path / "pending-proposals.json"
    _write(proposals_path, _proposal(action_type=ACTION_CATALOG_SEED))
    catalog_path = tmp_path / "catalog.yaml"

    results = execute_approved_proposals(
        proposals_path=proposals_path,
        snapshot=_snapshot(_project()),
        workspace_root=tmp_path,
        catalog_path=catalog_path,
        executed_at=NOW,
        dry_run=False,
    )

    assert results[0].outcome == "applied"
    assert catalog_path.exists()  # seed merged into a real (reversible) catalog file
    persisted = load_proposals(proposals_path)[0]
    assert persisted.status == STATUS_EXECUTED
    assert persisted.execution_ref == str(catalog_path)


def test_execute_catalog_seed_blocks_unknown_checkout_authority(tmp_path: Path) -> None:
    proposals_path = tmp_path / "pending-proposals.json"
    _write(proposals_path, _proposal(action_type=ACTION_CATALOG_SEED))
    catalog_path = tmp_path / "catalog.yaml"
    project = _project(
        repository_state={
            "checkout_authority": {
                "schema_version": "CheckoutCollisionV1",
                "selection": {
                    "state": "unknown",
                    "reason_code": "conflicting_full_clone_heads",
                    "representative_path": "MyRepo",
                    "selected_path": None,
                },
            }
        }
    )

    results = execute_approved_proposals(
        proposals_path=proposals_path,
        snapshot=_snapshot(project),
        workspace_root=tmp_path,
        catalog_path=catalog_path,
        executed_at=NOW,
        dry_run=False,
    )

    assert results[0].outcome == "failed"
    assert results[0].detail == (
        "checkout-authority-unknown:conflicting_full_clone_heads"
    )
    assert not catalog_path.exists()
    assert load_proposals(proposals_path)[0].status == STATUS_APPROVED


# --- execute_approved_proposals: resolution + slug policy ------------------


def test_execute_resolves_spaced_repo_by_slug(tmp_path: Path) -> None:
    project = _project(
        display_name="Signal & Noise",
        path="Signal & Noise",
        repo_full_name="owner/signal-noise",
    )
    (tmp_path / "Signal & Noise").mkdir()
    proposals_path = tmp_path / "pending-proposals.json"
    _write(
        proposals_path,
        _proposal(display_name="Signal & Noise", repo_full_name="owner/signal-noise"),
    )

    results = execute_approved_proposals(
        proposals_path=proposals_path,
        snapshot=_snapshot(project),
        workspace_root=tmp_path,
        catalog_path=tmp_path / "catalog.yaml",
        executed_at=NOW,
        dry_run=False,
        runner=FakeRunner(),
    )

    assert results[0].outcome == "applied"


def test_execute_skips_context_pr_without_slug(tmp_path: Path) -> None:
    project = _project(repo_full_name="")
    (tmp_path / "MyRepo").mkdir()
    proposals_path = tmp_path / "pending-proposals.json"
    _write(proposals_path, _proposal(repo_full_name=""))

    results = execute_approved_proposals(
        proposals_path=proposals_path,
        snapshot=_snapshot(project),
        workspace_root=tmp_path,
        catalog_path=tmp_path / "catalog.yaml",
        executed_at=NOW,
        dry_run=False,
        runner=FakeRunner(),
    )

    assert results[0].outcome == "skipped"
    assert results[0].detail == "no-repo-full-name"
    assert load_proposals(proposals_path)[0].status == STATUS_APPROVED


def test_execute_skips_proposal_with_no_matching_project(tmp_path: Path) -> None:
    proposals_path = tmp_path / "pending-proposals.json"
    _write(
        proposals_path, _proposal(display_name="Ghost", repo_full_name="owner/ghost")
    )

    results = execute_approved_proposals(
        proposals_path=proposals_path,
        snapshot=_snapshot(_project()),  # different repo
        workspace_root=tmp_path,
        catalog_path=tmp_path / "catalog.yaml",
        executed_at=NOW,
        dry_run=False,
        runner=FakeRunner(),
    )

    assert results[0].outcome == "skipped"
    assert results[0].detail == "project-not-found"


def test_execute_isolates_one_failure_from_the_rest_of_the_batch(
    tmp_path: Path,
) -> None:
    # A catalog-seed pointed at a path whose parent is missing raises OSError
    # inside the merge; that must become a `failed` result for THAT proposal and
    # leave the following context-PR proposal free to apply.
    catalog = _project(display_name="Cat", path="Cat", repo_full_name="owner/cat")
    pr = _project(display_name="MyRepo", path="MyRepo", repo_full_name="owner/MyRepo")
    (tmp_path / "MyRepo").mkdir()
    proposals_path = tmp_path / "pending-proposals.json"
    _write(
        proposals_path,
        _proposal(
            action_type=ACTION_CATALOG_SEED,
            display_name="Cat",
            repo_full_name="owner/cat",
        ),
        _proposal(),  # context-pr for MyRepo
    )

    results = execute_approved_proposals(
        proposals_path=proposals_path,
        snapshot=_snapshot(catalog, pr),
        workspace_root=tmp_path,
        catalog_path=tmp_path
        / "missing-dir"
        / "catalog.yaml",  # parent absent -> OSError
        executed_at=NOW,
        dry_run=False,
        runner=FakeRunner(),
    )

    assert [r.outcome for r in results] == ["failed", "applied"]
    by_id = {p.proposal_id: p for p in load_proposals(proposals_path)}
    assert (
        by_id["catalog-seed:owner/cat"].status == STATUS_APPROVED
    )  # failed -> retryable
    assert by_id["context-pr:owner/MyRepo"].status == STATUS_EXECUTED
