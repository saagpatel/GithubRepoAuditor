"""Tests for the canonical cross-store project-identity registry."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.project_registry import (
    build_index,
    build_project_registry,
    normalize,
    resolve,
)


def _snapshot(*identities: dict) -> dict:
    return {
        "projects": [
            {"identity": ident, "declared": {"lifecycle_state": "active"}} for ident in identities
        ]
    }


def _ident(project_key: str, display_name: str, repo: str | None = None) -> dict:
    return {
        "project_key": project_key,
        "display_name": display_name,
        "repo_full_name": repo,
        "group_key": "test",
    }


# A snapshot covering the tricky cases: a space-vs-camel name, the screenshot
# collision pair, a notion-os-style repo, and a Notion-orphan project.
SNAPSHOT = _snapshot(
    _ident("MCPAudit", "MCPAudit", "saagpatel/MCPAudit"),
    _ident("ScreenshottoDataSelect", "ScreenshottoDataSelect", "saagpatel/ScreenshottoDataSelect"),
    _ident(
        "ITPRJsViaClaude/ScreenshotAnnotate", "ScreenshotAnnotate", "saagpatel/ScreenshotAnnotate"
    ),
    _ident("JobCommandCenter", "JobCommandCenter", "saagpatel/JobCommandCenter"),
    _ident(
        "BrowserHistoryVisualizer", "BrowserHistoryVisualizer", "saagpatel/BrowserHistoryVisualizer"
    ),
    _ident("Notion", "Notion", "saagpatel/notion-operating-system"),
    _ident("PortfolioCommandCenter", "PortfolioCommandCenter", "saagpatel/PortfolioCommandCenter"),
    _ident("Fun:GamePrjs/DesktopPEt", "DesktopPEt", "saagpatel/DesktopPEt"),
)


def _bridge_db(tmp_path: Path, names: list[str]) -> Path:
    db_path = tmp_path / "bridge.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE activity_log (project_name TEXT)")
    conn.execute("CREATE TABLE pending_handoffs (project_name TEXT)")
    conn.executemany("INSERT INTO activity_log VALUES (?)", [(n,) for n in names])
    conn.commit()
    conn.close()
    return db_path


def test_normalize_strips_case_separators_and_taxonomy_path():
    assert normalize("MCP Audit") == "mcpaudit"
    assert normalize("MCPAudit") == "mcpaudit"
    assert normalize("ITPRJsViaClaude/SlackIncidentBot") == "slackincidentbot"
    assert normalize("Devil's Advocate") == "devilsadvocate"
    assert normalize(None) == ""


def test_build_includes_supplementary_projects_from_defaults():
    registry = build_project_registry(SNAPSHOT, overrides_config_path=None)
    keys = {e["canonical_key"] for e in registry["entries"]}
    assert "supp:personal-ops" in keys
    assert "supp:SecondBrain" in keys
    assert registry["entry_count"] == len(SNAPSHOT["projects"]) + 2


def test_build_does_not_duplicate_supplementary_project_promoted_into_truth():
    snapshot = _snapshot(_ident("supp:personal-ops", "personal-ops", None))

    registry = build_project_registry(snapshot, overrides_config_path=None)
    personal_ops = [
        entry
        for entry in registry["entries"]
        if entry["canonical_key"] == "supp:personal-ops"
    ]

    assert len(personal_ops) == 1
    assert personal_ops[0]["source"] == "auditor"


def test_supp_key_is_emitted_for_repo_less_entries_only():
    # A repo-backed and a repo-less auditor project side by side.
    snapshot = _snapshot(
        _ident("MCPAudit", "MCPAudit", "saagpatel/MCPAudit"),
        _ident("fable-os-divergence", "fable-os-divergence", repo=None),
    )
    registry = build_project_registry(snapshot, overrides_config_path=None)
    by_key = {e["canonical_key"]: e for e in registry["entries"]}

    # Repo-backed: canonical key is repo_full_name, so supp_key is None.
    assert by_key["MCPAudit"]["supp_key"] is None

    # Repo-less auditor entry: gets a stable supp:<slug> key.
    assert by_key["fable-os-divergence"]["supp_key"] == "supp:fable-os-divergence"

    # Hardcoded supplementary entry already carries a supp: canonical_key and
    # passes through unchanged (not double-prefixed).
    assert by_key["supp:personal-ops"]["supp_key"] == "supp:personal-ops"


def test_supp_key_preserves_full_canonical_key_no_leaf_collision():
    # Two repo-less projects sharing a leaf segment must NOT collapse onto one
    # supp: key. The full path-shaped canonical_key is preserved for uniqueness.
    snapshot = _snapshot(
        _ident("team-a/2026-07-03", "report-a", None),
        _ident("team-b/2026-07-03", "report-b", None),
    )
    registry = build_project_registry(snapshot, overrides_config_path=None)
    by_key = {e["canonical_key"]: e for e in registry["entries"]}
    a = by_key["team-a/2026-07-03"]["supp_key"]
    b = by_key["team-b/2026-07-03"]["supp_key"]
    assert a == "supp:team-a/2026-07-03"
    assert b == "supp:team-b/2026-07-03"
    assert a != b  # no leaf-segment collision


def test_resolve_joins_spelling_variants():
    registry = build_project_registry(SNAPSHOT, overrides_config_path=None)
    index = build_index(registry)
    for spelling in ("MCPAudit", "MCP Audit", "mcpaudit", "mcp_audit"):
        result = resolve(spelling, index)
        assert result is not None, spelling
        assert result["canonical_key"] == "MCPAudit", spelling


def test_configured_notion_title_aliases_cover_operating_spellings():
    snapshot = _snapshot(
        _ident("GithubRepoAuditor", "GithubRepoAuditor", "saagpatel/GithubRepoAuditor"),
        _ident("MCPAudit", "MCPAudit", "saagpatel/MCPAudit"),
        _ident("Notion", "Notion", "saagpatel/notion-operating-system"),
    )
    registry = build_project_registry(
        snapshot,
        notion_snapshot_path=None,
        overrides_config_path=Path("config/project-registry-overrides.json"),
    )
    index = build_index(registry)
    assert resolve("GitHub Repo Auditor", index)["canonical_key"] == "GithubRepoAuditor"
    assert resolve("MCP Audit", index)["canonical_key"] == "MCPAudit"
    assert resolve("Notion Operating System", index)["canonical_key"] == "Notion"


def test_resolve_hard_normalization_failures_via_override():
    registry = build_project_registry(SNAPSHOT, overrides_config_path=None)
    index = build_index(registry)
    assert resolve("notion_os", index)["canonical_key"] == "Notion"
    assert resolve("jcc", index)["canonical_key"] == "JobCommandCenter"
    assert resolve("bhv", index)["canonical_key"] == "BrowserHistoryVisualizer"


def test_configured_shipped_mappings_cover_operator_os_and_claude_harness():
    snapshot = _snapshot(
        _ident(
            "operator-os-explainer",
            "operator-os-explainer",
            "saagpatel/operator-os-explainer",
        )
    )
    registry = build_project_registry(
        snapshot,
        notion_project_map_path=Path("config/notion-project-map.json"),
        overrides_config_path=Path("config/project-registry-overrides.json"),
    )
    index = build_index(registry)
    by_key = {entry["canonical_key"]: entry for entry in registry["entries"]}

    assert resolve("claude-harness-modernization", index)["canonical_key"] == (
        "supp:claude-code-harness"
    )
    assert by_key["supp:claude-code-harness"]["notion_local_page_id"] == (
        "362c21f1-caf0-81bd-8c6e-dd3acaebc34b"
    )
    assert by_key["operator-os-explainer"]["notion_local_page_id"] == (
        "39dc21f1-caf0-8142-8718-e1454dea1198"
    )


def test_resolve_collision_guard_screenshotselect():
    registry = build_project_registry(SNAPSHOT, overrides_config_path=None)
    index = build_index(registry)
    result = resolve("screenshotselect", index)
    assert result["canonical_key"] == "ScreenshottoDataSelect"
    assert result["canonical_key"] != "ITPRJsViaClaude/ScreenshotAnnotate"


def test_resolve_supplementary_from_each_spelling():
    registry = build_project_registry(SNAPSHOT, overrides_config_path=None)
    index = build_index(registry)
    assert resolve("personal-ops", index)["canonical_key"] == "supp:personal-ops"
    assert resolve("personal_ops", index)["canonical_key"] == "supp:personal-ops"
    assert resolve("Personal Ops", index)["canonical_key"] == "supp:personal-ops"
    assert resolve("SecondBrain", index)["canonical_key"] == "supp:SecondBrain"


def test_projection_policy_is_published_from_defaults():
    registry = build_project_registry(SNAPSHOT, overrides_config_path=None)
    policy = registry["projection_policy"]
    assert policy["schema_version"] == "notion_projection_policy.v2"
    assert policy["notion_title_aliases"]["DesktopPEt-ready"] == "DesktopPEt"
    assert "SecondBrain" in policy["notion_projection_only_rows"]
    assert policy["notion_truth_shadow_rows"]["agent-bridge-launch"] == "agent-bridge"


def test_configured_projection_policy_preserves_rag_planning_row_exclusion():
    registry = build_project_registry(
        SNAPSHOT,
        notion_snapshot_path=None,
        overrides_config_path=Path("config/project-registry-overrides.json"),
    )

    assert registry["projection_policy"]["notion_projection_only_rows"][
        "RAG Knowledge Base"
    ] == "notion planning row; not a portfolio-truth repo"


def test_resolve_returns_none_for_non_projects():
    registry = build_project_registry(SNAPSHOT, overrides_config_path=None)
    index = build_index(registry)
    for junk in ("weekly-review", "Phase 18 audit task", "app", "totally-unknown"):
        assert resolve(junk, index) is None, junk


def test_build_degrades_gracefully_without_external_sources():
    registry = build_project_registry(
        SNAPSHOT,
        bridge_db_path=None,
        notion_snapshot_path=None,
        notion_project_map_path=None,
        memory_dir=None,
        overrides_config_path=None,
    )
    assert registry["entry_count"] == len(SNAPSHOT["projects"]) + 2
    for entry in registry["entries"]:
        assert entry["coverage"]["bridge"] is False
        assert entry["coverage"]["notion_local"] is False


def test_build_attaches_external_sources(tmp_path: Path):
    bridge = _bridge_db(tmp_path, ["MCPAudit", "PortfolioCommandCenter", "weekly-review"])
    snap = tmp_path / "snapshot.json"
    snap.write_text(
        json.dumps(
            {
                "projects": [
                    {"title": "MCP Audit"},
                    {"title": "DesktopPEt-ready"},
                    {"title": "app"},
                ]
            }
        )
    )
    page_map = tmp_path / "notion-project-map.json"
    page_map.write_text(
        json.dumps(
            {
                "MCP Audit": {"localProjectId": "page-mcp"},
                "DesktopPEt": {"localProjectId": "page-desktop"},
            }
        )
    )
    memdir = tmp_path / "memory"
    memdir.mkdir()
    (memdir / "project_mcpaudit.md").write_text("x")

    registry = build_project_registry(
        SNAPSHOT,
        bridge_db_path=bridge,
        notion_snapshot_path=snap,
        notion_project_map_path=page_map,
        memory_dir=memdir,
        overrides_config_path=None,
    )
    by_key = {e["canonical_key"]: e for e in registry["entries"]}
    mcp = by_key["MCPAudit"]
    assert mcp["bridge_project_names"] == ["MCPAudit"]
    assert mcp["notion_local_title"] == "MCP Audit"
    assert mcp["notion_local_page_id"] == "page-mcp"
    assert mcp["memory_slug"] == "project_mcpaudit"
    desktop = by_key["Fun:GamePrjs/DesktopPEt"]
    assert desktop["notion_local_title"] == "DesktopPEt-ready"
    assert desktop["notion_local_page_id"] == "page-desktop"
    assert "notion:DesktopPEt-ready" in desktop["aliases"]
    # bridge noise lands in unmatched; projection-only Notion rows are explained separately
    assert "weekly-review" in registry["unmatched"]["bridge"]
    assert registry["unmatched"]["notion_local"] == []
    assert registry["projection_only"]["notion_local"] == [
        {
            "title": "app",
            "reason": "local runtime/app shell placeholder; not a portfolio-truth repo",
        }
    ]
    # PortfolioCommandCenter resolves from bridge but has no Notion/memory row
    assert by_key["PortfolioCommandCenter"]["bridge_project_names"] == ["PortfolioCommandCenter"]
    assert by_key["PortfolioCommandCenter"]["notion_local_title"] is None


def test_normalized_key_collision_is_surfaced_not_silent():
    # Two distinct projects whose display names normalize to the same form.
    colliding = _snapshot(
        _ident("NetMapper", "Net Mapper", "saagpatel/NetMapper"),
        _ident("NetworkMapperAlt", "NetMapper", "saagpatel/NetworkMapperAlt"),
    )
    registry = build_project_registry(colliding, overrides_config_path=None)
    collisions = registry["warnings"]["normalized_key_collisions"]
    assert any(c["normalized_form"] == "netmapper" for c in collisions)


def test_real_snapshot_shape_has_no_collisions_block_when_clean():
    registry = build_project_registry(SNAPSHOT, overrides_config_path=None)
    assert registry["warnings"]["normalized_key_collisions"] == []


def test_scoring_pageids_attach_to_matching_entries():
    registry = build_project_registry(
        SNAPSHOT,
        scoring_pageids={"MCPAudit": "page-123", "Unknown Idea": "page-999"},
        overrides_config_path=None,
    )
    by_key = {e["canonical_key"]: e for e in registry["entries"]}
    assert by_key["MCPAudit"]["notion_scoring_page_id"] == "page-123"
