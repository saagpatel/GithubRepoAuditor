"""Tests for workspace discovery canonicalization in portfolio_truth_sources.

Multiple on-disk checkouts of the same repo (linked git worktrees and stray
duplicate full-clones left by multi-repo sweeps) share one origin
(`repo_full_name`). Discovery must collapse them to a single canonical project
so they don't inflate the project count and pollute catalog-completeness.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.portfolio_truth_sources import (
    _dedupe_checkouts_by_origin,
    _is_ignored_project_dir,
    discover_workspace_projects,
    workspace_exclusion_reason,
)


def _p(name: str, repo_full_name: str = "", path: str | None = None) -> dict:
    return {"name": name, "repo_full_name": repo_full_name, "path": path or name}


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
