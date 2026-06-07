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


def test_ignore_predicate_keeps_real_projects() -> None:
    # guard against over-broad matching: legit names that merely resemble a rule
    for name in (
        "GithubRepoAuditor",
        "ApplyKit-public",
        "cost-tracker",
        "resume-evolver",  # the real repo, sans -tmp-<ts> suffix
        "smoke-test-runner",  # "smoke" but not "smoke-export"
        "tmp-tools",  # "tmp" but not the -tmp-<digits> clone pattern
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

    result = discover_workspace_projects(
        tmp_path,
        catalog_data={},
        now=datetime(2026, 6, 2, tzinfo=timezone.utc),
    )
    assert {p["name"] for p in result} == {"LegitProject"}
