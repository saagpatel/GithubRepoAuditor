"""Tests for workspace discovery canonicalization in portfolio_truth_sources.

Multiple on-disk checkouts of the same repo (linked git worktrees and stray
duplicate full-clones left by multi-repo sweeps) share one origin
(`repo_full_name`). Discovery must collapse them to a single canonical project
so they don't inflate the project count and pollute catalog-completeness.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from src.portfolio_truth_sources import (
    _dedupe_checkouts_by_origin,
    _is_ignored_project_dir,
    checkout_collision_summary,
    discover_workspace_projects,
    workspace_exclusion_reason,
)


def _p(
    name: str,
    repo_full_name: str = "",
    path: str | None = None,
    *,
    head: str | None = None,
    branch: str | None = "main",
    common_dir: str | None = None,
    dirty: bool | None = False,
    dirty_path_count: int | None = 0,
    declared_paths: list[dict[str, str]] | None = None,
) -> dict:
    relative_path = path or name
    project = {
        "name": name,
        "repo_full_name": repo_full_name,
        "path": relative_path,
        "project_path": Path("/workspace") / relative_path,
    }
    if head is not None or common_dir is not None:
        project["_checkout_observation"] = {
            "state": "observed",
            "head": head,
            "branch": branch,
            "dirty": dirty,
            "dirty_path_count": dirty_path_count,
            "git_common_dir": common_dir,
            "declared_paths": declared_paths or [],
        }
    return project


def test_collapses_same_origin_checkouts_to_one() -> None:
    discovered = [
        _p("AssistSupport-openssl-fix", "saagpatel/AssistSupport"),
        _p("AssistSupport", "saagpatel/AssistSupport"),
        _p("AssistSupport-security-followup", "saagpatel/AssistSupport"),
    ]
    result = _dedupe_checkouts_by_origin(discovered)
    assert len(result) == 1
    # the canonical checkout is the one whose dir name matches the repo basename
    assert result[0]["name"] == "AssistSupport"


def test_prefers_basename_match_then_shortest_name() -> None:
    # no exact-basename checkout present -> shortest name wins
    discovered = [
        _p("IncidentWorkbench-statuspage-finish", "saagpatel/IncidentWorkbench"),
        _p("IncidentWorkbench-zendesk", "saagpatel/IncidentWorkbench"),
    ]
    result = _dedupe_checkouts_by_origin(discovered)
    assert len(result) == 1
    assert result[0]["name"] == "IncidentWorkbench-zendesk"  # shortest


def test_distinct_origins_are_kept() -> None:
    discovered = [
        _p("Alpha", "saagpatel/Alpha"),
        _p("Beta", "saagpatel/Beta"),
    ]
    result = _dedupe_checkouts_by_origin(discovered)
    assert {p["name"] for p in result} == {"Alpha", "Beta"}


def test_origin_basename_match_is_case_insensitive() -> None:
    discovered = [
        _p("notion-operating-system", "saagpatel/notion-operating-system"),
        _p("Notion", "saagpatel/notion-operating-system"),
    ]
    result = _dedupe_checkouts_by_origin(discovered)
    assert len(result) == 1
    assert result[0]["name"] == "notion-operating-system"


def test_local_only_projects_without_origin_are_never_collapsed() -> None:
    # empty repo_full_name => genuinely distinct local projects, keep all
    discovered = [
        _p("scratch-a", ""),
        _p("scratch-b", ""),
        _p("scratch-c", ""),
    ]
    result = _dedupe_checkouts_by_origin(discovered)
    assert len(result) == 3


def test_result_is_sorted_by_name_case_insensitively() -> None:
    discovered = [
        _p("zeta", "saagpatel/zeta"),
        _p("Alpha", "saagpatel/Alpha"),
        _p("mike", ""),
    ]
    result = _dedupe_checkouts_by_origin(discovered)
    assert [p["name"] for p in result] == ["Alpha", "mike", "zeta"]


def test_linked_worktrees_keep_discarded_checkout_evidence() -> None:
    collisions: list[dict] = []
    head = "1" * 40
    discovered = [
        _p(
            "Repo",
            "owner/Repo",
            head=head,
            common_dir="/git/Repo/.git",
        ),
        _p(
            "Repo-fix",
            "owner/Repo",
            head="2" * 40,
            branch="fix",
            common_dir="/git/Repo/.git",
        ),
    ]

    result = _dedupe_checkouts_by_origin(
        discovered,
        checkout_collisions=collisions,
    )

    assert len(result) == 1
    assert len(collisions) == 1
    collision = collisions[0]
    assert collision["selection"]["state"] == "selected"
    assert collision["selection"]["reason_code"] == "single_clone_topology"
    assert collision["full_clone_count"] == 1
    assert collision["discarded_checkouts"] == [
        {
            "path": "Repo-fix",
            "state": "observed",
            "relation": "linked_worktree",
            "head": "2" * 40,
            "branch": "fix",
            "dirty": False,
            "dirty_path_count": 0,
        }
    ]


def test_conflicting_independent_full_clone_heads_are_unknown() -> None:
    collisions: list[dict] = []
    discovered = [
        _p(
            "Repo",
            "owner/Repo",
            head="1" * 40,
            common_dir="/git/Repo/.git",
        ),
        _p(
            "Archive/Repo",
            "owner/Repo",
            path="Archive/Repo",
            head="2" * 40,
            common_dir="/git/Archive/Repo/.git",
        ),
    ]

    result = _dedupe_checkouts_by_origin(
        discovered,
        checkout_collisions=collisions,
    )

    assert len(result) == 1
    collision = collisions[0]
    assert collision["full_clone_count"] == 2
    assert collision["selection"]["state"] == "unknown"
    assert collision["selection"]["selected_path"] is None
    assert collision["selection"]["reason_code"] == "conflicting_full_clone_heads"
    assert collision["discarded_checkouts"][0]["relation"] == "independent_full_clone"

    summary = checkout_collision_summary(collisions)
    assert summary["state"] == "unknown"
    assert summary["group_count"] == 1
    assert summary["full_clone_group_count"] == 1
    assert summary["ambiguous_group_count"] == 1
    assert summary["discarded_checkout_count"] == 1


def test_dirty_linked_worktree_in_independent_clone_is_unknown() -> None:
    collisions: list[dict] = []
    head = "1" * 40
    discovered = [
        _p(
            "Repo",
            "owner/Repo",
            head=head,
            common_dir="/git/Repo/.git",
        ),
        _p(
            "Repo",
            "owner/Repo",
            path="Archive/Repo",
            head=head,
            common_dir="/git/Archive/Repo/.git",
        ),
        _p(
            "Repo-fix",
            "owner/Repo",
            path="Archive/Repo-fix",
            head="2" * 40,
            branch="fix",
            common_dir="/git/Archive/Repo/.git",
            dirty=True,
            dirty_path_count=1,
        ),
    ]

    _dedupe_checkouts_by_origin(discovered, checkout_collisions=collisions)

    collision = collisions[0]
    assert collision["full_clone_count"] == 2
    assert collision["selection"]["state"] == "unknown"
    assert collision["selection"]["selected_path"] is None
    assert collision["selection"]["reason_code"] == "full_clone_local_work_present"
    assert any(
        checkout["path"] == "Archive/Repo-fix" and checkout["dirty"] is True
        for checkout in collision["discarded_checkouts"]
    )


def test_declared_path_to_other_full_clone_overrides_head_reason() -> None:
    nested_declaration = {
        "absolute_path": "/workspace/Money/AIGCCore/src",
        "workspace_relative_path": "Money/AIGCCore/src",
        "source_file": "AGENTS.md",
    }
    collisions: list[dict] = []
    discovered = [
        _p(
            "AIGCCore",
            "owner/AIGCCore",
            head="1" * 40,
            common_dir="/git/AIGCCore/.git",
            declared_paths=[nested_declaration],
        ),
        _p(
            "AIGCCore",
            "owner/AIGCCore",
            path="Money/AIGCCore",
            head="2" * 40,
            common_dir="/git/Money/AIGCCore/.git",
            declared_paths=[nested_declaration],
        ),
    ]

    _dedupe_checkouts_by_origin(discovered, checkout_collisions=collisions)

    collision = collisions[0]
    assert collision["selection"]["state"] == "unknown"
    assert (
        collision["selection"]["reason_code"]
        == "declared_path_conflicts_with_representative"
    )
    assert collision["declared_checkout_paths"] == ["Money/AIGCCore"]
    assert collision["declared_path_evidence"] == [
        {
            "source_path": "AIGCCore/AGENTS.md",
            "target_checkout_path": "Money/AIGCCore",
        },
        {
            "source_path": "Money/AIGCCore/AGENTS.md",
            "target_checkout_path": "Money/AIGCCore",
        },
    ]


# --- discovery ignore-list: transient / non-project directories ---
# NoGoPRJs (operator-flagged never-pursued), `*-smoke-export` (generated
# AuraForge bundles), and `*-tmp-<ts>` clones are scratch artifacts, not real
# projects. Discovery must skip them (and their subtrees) so they never reach
# the catalog-completeness gate.


def test_ignore_predicate_matches_transient_dirs() -> None:
    assert _is_ignored_project_dir("Misc:NoGoPRJs")  # colon form, as on disk
    assert _is_ignored_project_dir("NoGoPRJs")
    assert _is_ignored_project_dir("auraforge-signed-smoke-export")
    assert _is_ignored_project_dir("resume-evolver-tmp-1776063720")
    assert _is_ignored_project_dir("Codex Backups")
    assert workspace_exclusion_reason("Codex Backups") == "backup-container"
    assert workspace_exclusion_reason("scratch") == "scratch-container"
    assert workspace_exclusion_reason("_backups") == "backup-container"
    assert (
        workspace_exclusion_reason("_preserved-local-artifacts")
        == "preserved-artifacts"
    )
    assert workspace_exclusion_reason("sweep-reports") == "generated-reports"
    assert (
        workspace_exclusion_reason("_fable-worktrees")
        == "linked-worktree-container"
    )
    assert (
        workspace_exclusion_reason("_codex-worktrees")
        == "linked-worktree-container"
    )
    assert workspace_exclusion_reason("packets") is None
    assert workspace_exclusion_reason("packets", nested=True) == "nested-content"
    assert workspace_exclusion_reason("prompts", nested=True) == "nested-content"


def test_ignore_predicate_keeps_real_projects() -> None:
    # guard against over-broad matching: legit names that merely resemble a rule
    for name in (
        "GithubRepoAuditor",
        "ApplyKit-public",
        "cost-tracker",
        "resume-evolver",  # the real repo, sans -tmp-<ts> suffix
        "smoke-test-runner",  # "smoke" but not "smoke-export"
        "tmp-tools",  # "tmp" but not the -tmp-<digits> clone pattern
        "CodexBackupTool",
        "BackupBuddy",
    ):
        assert not _is_ignored_project_dir(name), name


def test_discovery_skips_ignored_subtrees(tmp_path) -> None:
    def _project(*parts: str) -> None:
        d = tmp_path.joinpath(*parts)
        d.mkdir(parents=True)
        (d / "README.md").write_text("# fixture")

    _project("LegitProject")  # real top-level project -> kept
    _project("NoGoPRJs", "app")  # nested under ignored container -> skipped
    _project("auraforge-signed-smoke-export", "foo-plan")  # ignored bundle -> skipped
    _project("resume-evolver-tmp-1776063720")  # top-level tmp clone -> skipped
    _project("Documents", "Codex Backups", "Wave 2R Post-Update", "README-fixture")
    _project("Documents", "RealNestedProject")
    _project("scratch", "README-fixture")
    _project("_backups", "old-repo")
    _project("_preserved-local-artifacts", "saved-repo")
    _project("sweep-reports", "branch-hygiene-2026-07-03")
    _project("_fable-worktrees", "personal-ops-worklist-phase1")
    _project("_codex-worktrees", "personal-ops-truth-authority")
    _project("Campaign", "packets")
    _project("Campaign", "prompts")

    exclusion_counts: dict[str, int] = {}
    result = discover_workspace_projects(
        tmp_path,
        catalog_data={},
        now=datetime(2026, 6, 2, tzinfo=timezone.utc),
        exclusion_counts=exclusion_counts,
    )
    assert {p["name"] for p in result} == {"LegitProject", "RealNestedProject"}
    assert exclusion_counts == {
        "backup-container": 2,
        "generated-evidence": 1,
        "generated-reports": 1,
        "linked-worktree-container": 2,
        "nested-content": 2,
        "operator-excluded": 1,
        "preserved-artifacts": 1,
        "scratch-container": 1,
        "temporary-checkout": 1,
    }


def test_discovery_recognizes_conventional_bare_coordinator(tmp_path) -> None:
    coordinator = tmp_path / "bare-coordinator"
    subprocess.run(
        ["git", "init", "--bare", str(coordinator)],
        check=True,
        capture_output=True,
        text=True,
    )

    result = discover_workspace_projects(
        tmp_path,
        catalog_data={},
        now=datetime(2026, 7, 30, tzinfo=timezone.utc),
    )

    project = next(item for item in result if item["name"] == coordinator.name)
    assert project["has_git"] is True
    assert project["project_path"] == coordinator
    assert project["_checkout_observation"]["state"] == "observed"
    assert project["_checkout_observation"]["head"] is None
    assert project["_checkout_observation"]["git_common_dir"] == str(coordinator)


def test_discovery_observes_conflicting_full_clones_without_count_inflation(
    tmp_path,
) -> None:
    root_clone = tmp_path / "Widget"
    nested_clone = tmp_path / "Archive" / "Widget"
    for index, clone in enumerate((root_clone, nested_clone), start=1):
        clone.mkdir(parents=True)
        (clone / "README.md").write_text(f"# Widget {index}\n")
        if clone == root_clone:
            (clone / "AGENTS.md").write_text(
                "# Instructions\n\n## Canonical Paths\n\n"
                f"- Source: `{nested_clone / 'src'}`\n"
            )
        subprocess.run(
            ["git", "init", "-q", "-b", "main"],
            cwd=clone,
            check=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", "git@github.com:owner/Widget.git"],
            cwd=clone,
            check=True,
        )
        subprocess.run(["git", "add", "."], cwd=clone, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "-q",
                "-m",
                f"fixture {index}",
            ],
            cwd=clone,
            check=True,
        )

    collisions: list[dict] = []
    projects = discover_workspace_projects(
        tmp_path,
        catalog_data={},
        now=datetime(2026, 8, 3, tzinfo=timezone.utc),
        checkout_collisions=collisions,
    )

    widget_projects = [
        project for project in projects if project["repo_full_name"] == "owner/Widget"
    ]
    assert len(widget_projects) == 1
    assert widget_projects[0]["path"] == "Widget"
    assert len(collisions) == 1
    collision = collisions[0]
    assert collision["checkout_count"] == 2
    assert collision["full_clone_count"] == 2
    assert collision["selection"]["state"] == "unknown"
    assert (
        collision["selection"]["reason_code"]
        == "declared_path_conflicts_with_representative"
    )
    assert collision["declared_checkout_paths"] == ["Archive/Widget"]
    assert all(checkout["state"] == "observed" for checkout in collision["checkouts"])
    assert all(len(checkout["head"]) == 40 for checkout in collision["checkouts"])
