"""Tests for the canonical cross-store project-identity registry."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from github_repo_auditor.project_registry import (
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
    # Page ids are no longer a function of config: they come from the verified
    # live snapshot, so what the shipped configuration still has to guarantee is
    # that both identities resolve from the spellings shipped events arrive under.
    snapshot = _snapshot(
        _ident(
            "operator-os-explainer",
            "operator-os-explainer",
            "saagpatel/operator-os-explainer",
        )
    )
    registry = build_project_registry(
        snapshot,
        overrides_config_path=Path("config/project-registry-overrides.json"),
    )
    index = build_index(registry)

    assert resolve("claude-harness-modernization", index)["canonical_key"] == (
        "supp:claude-code-harness"
    )
    assert resolve("operator-os-explainer", index)["canonical_key"] == (
        "operator-os-explainer"
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
        memory_dir=None,
        overrides_config_path=None,
    )
    assert registry["entry_count"] == len(SNAPSHOT["projects"]) + 2
    for entry in registry["entries"]:
        assert entry["coverage"]["bridge"] is False
        assert entry["coverage"]["notion_local"] is False


def test_build_attaches_external_sources(tmp_path: Path):
    bridge = _bridge_db(tmp_path, ["MCPAudit", "PortfolioCommandCenter", "weekly-review"])
    snap = _pid_snapshot(
        tmp_path,
        [
            {"title": "MCP Audit", "page_id": "page-mcp"},
            {"title": "DesktopPEt-ready", "page_id": "page-desktop"},
            {"title": "app", "page_id": "page-app-shell"},
        ],
    )
    memdir = tmp_path / "memory"
    memdir.mkdir()
    (memdir / "project_mcpaudit.md").write_text("x")

    registry = build_project_registry(
        SNAPSHOT,
        bridge_db_path=bridge,
        notion_snapshot_path=snap,
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


# --- Notion page ids sourced from the live snapshot -------------------------
#
# Titles always scaled with the live snapshot while page ids came only from a
# hand-maintained static map, so a project could carry a known Notion title and
# no reachable Notion target. The snapshot producer now emits page_id per row.


def _pid_snapshot(tmp_path: Path, rows: list[dict], *, verified: bool = True) -> Path:
    """Write a snapshot that passes the full verification contract by default.

    Page ids are only honoured from a verified snapshot, so a fixture that skips
    the receipts is testing the refusal path, not the happy one.
    """
    import hashlib
    from datetime import datetime, timezone

    path = tmp_path / "snapshot.json"
    if not verified:
        path.write_text(json.dumps({"schema_version": "2.0.0", "projects": rows}))
        return path
    content_sha256 = hashlib.sha256(
        json.dumps(rows, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    path.write_text(
        json.dumps(
            {
                "schema_version": "2.0.0",
                "generated_at": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                "project_count": len(rows),
                "live_read_receipt": {"state": "verified", "page_count": len(rows)},
                "attention_authority_receipt": {"state": "verified"},
                "content_sha256": content_sha256,
                "projects": rows,
            }
        )
    )
    return path


def test_page_ids_come_from_the_live_snapshot_without_a_static_map(tmp_path: Path):
    snap = _pid_snapshot(
        tmp_path,
        [
            {"title": "MCP Audit", "page_id": "live-mcp"},
            {"title": "DesktopPEt-ready", "page_id": "live-desktop"},
        ],
    )
    registry = build_project_registry(
        SNAPSHOT,
        notion_snapshot_path=snap,
        overrides_config_path=None,
    )
    by_key = {e["canonical_key"]: e for e in registry["entries"]}
    assert by_key["MCPAudit"]["notion_local_page_id"] == "live-mcp"
    assert by_key["Fun:GamePrjs/DesktopPEt"]["notion_local_page_id"] == "live-desktop"


def test_snapshot_row_without_a_page_id_yields_no_page_id(tmp_path: Path):
    # Never reconstructed from the title or any neighbouring row: an invented
    # page id would be a false mapping in a receipts system.
    snap = _pid_snapshot(
        tmp_path,
        [{"title": "MCP Audit"}, {"title": "DesktopPEt-ready", "page_id": "  "}],
    )
    registry = build_project_registry(
        SNAPSHOT,
        notion_snapshot_path=snap,
        overrides_config_path=None,
    )
    by_key = {e["canonical_key"]: e for e in registry["entries"]}
    assert by_key["MCPAudit"]["notion_local_title"] == "MCP Audit"
    assert by_key["MCPAudit"]["notion_local_page_id"] is None
    assert by_key["Fun:GamePrjs/DesktopPEt"]["notion_local_page_id"] is None


def test_the_verified_snapshot_is_the_only_page_id_source(tmp_path: Path):
    # The registry used to fall back to a hand-maintained static map, which is
    # how a stale id could outlive the row it named. That file now serves only
    # notion_export's repo-name keyspace, and the registry does not read it, so
    # a row the snapshot left without an id simply has none.
    snap = _pid_snapshot(
        tmp_path,
        [{"title": "MCP Audit", "page_id": "live-mcp"}, {"title": "DesktopPEt-ready"}],
    )
    registry = build_project_registry(
        SNAPSHOT,
        notion_snapshot_path=snap,
        overrides_config_path=None,
    )
    by_key = {e["canonical_key"]: e for e in registry["entries"]}
    assert by_key["MCPAudit"]["notion_local_page_id"] == "live-mcp"
    assert by_key["Fun:GamePrjs/DesktopPEt"]["notion_local_page_id"] is None


def test_build_project_registry_takes_no_static_page_id_map():
    # A caller that still passes the retired map must fail loudly rather than
    # have its argument silently ignored: a quietly dropped id source is exactly
    # the failure mode this split removes.
    import inspect

    params = inspect.signature(build_project_registry).parameters
    assert "notion_project_map_path" not in params


# --- Ambiguous Notion bindings are refused, not resolved by entry order -----


COLLIDING = _snapshot(
    _ident("conductor", "conductor"),
    _ident("VanityPRJs/Conductor", "Conductor", "saagpatel/Conductor"),
    _ident("MCPAudit", "MCPAudit", "saagpatel/MCPAudit"),
)


def test_ambiguous_notion_title_binds_to_nothing(tmp_path: Path):
    # Two distinct projects normalize to "conductor". Binding the Notion row to
    # whichever the index happened to keep would give one project the other's
    # page, and any shipped event for it would sync into the wrong row.
    snap = _pid_snapshot(tmp_path, [{"title": "Conductor", "page_id": "page-app"}])
    registry = build_project_registry(
        COLLIDING,
        notion_snapshot_path=snap,
        overrides_config_path=None,
    )
    for entry in registry["entries"]:
        assert entry["notion_local_title"] is None
        assert entry["notion_local_page_id"] is None


def test_refused_notion_title_is_reported_with_its_candidates(tmp_path: Path):
    snap = _pid_snapshot(tmp_path, [{"title": "Conductor", "page_id": "page-app"}])
    registry = build_project_registry(
        COLLIDING,
        notion_snapshot_path=snap,
        overrides_config_path=None,
    )
    ambiguous = registry["unmatched"]["notion_local_ambiguous"]
    assert [row["title"] for row in ambiguous] == ["Conductor"]
    assert ambiguous[0]["candidates"] == ["VanityPRJs/Conductor", "conductor"]
    # A refused binding is not the same condition as an unrecognized row.
    assert registry["unmatched"]["notion_local"] == []


def test_explicit_override_still_binds_an_otherwise_ambiguous_title(
    tmp_path: Path,
):
    # The refusal blocks resolution by entry order, not resolution by decision:
    # once the operator says which project the row is, the binding must work.
    snap = _pid_snapshot(tmp_path, [{"title": "Conductor", "page_id": "page-app"}])
    overrides = tmp_path / "overrides.json"
    overrides.write_text(json.dumps({"overrides": {"Conductor": "VanityPRJs/Conductor"}}))
    registry = build_project_registry(
        COLLIDING,
        notion_snapshot_path=snap,
        overrides_config_path=overrides,
    )
    by_key = {e["canonical_key"]: e for e in registry["entries"]}
    assert by_key["VanityPRJs/Conductor"]["notion_local_title"] == "Conductor"
    assert by_key["VanityPRJs/Conductor"]["notion_local_page_id"] == "page-app"
    assert by_key["conductor"]["notion_local_page_id"] is None
    assert registry["unmatched"]["notion_local_ambiguous"] == []


def test_unambiguous_titles_are_unaffected_by_the_refusal(tmp_path: Path):
    snap = _pid_snapshot(
        tmp_path,
        [{"title": "Conductor", "page_id": "page-app"}, {"title": "MCPAudit", "page_id": "page-mcp"}],
    )
    registry = build_project_registry(
        COLLIDING,
        notion_snapshot_path=snap,
        overrides_config_path=None,
    )
    by_key = {e["canonical_key"]: e for e in registry["entries"]}
    assert by_key["MCPAudit"]["notion_local_page_id"] == "page-mcp"


def test_personal_ops_has_one_identity_not_a_supplementary_duplicate():
    # personal-ops is tracked by the auditor as saagpatel/personal-ops. A
    # leftover supp:personal-ops enrollment would collide with it on the
    # normalized form "personalops", and the collision would refuse the Notion
    # binding for the most active project in bridge-db.
    from github_repo_auditor.project_registry import load_overrides_config

    _, supplementary, memory_meta, *_ = load_overrides_config(
        Path("config/project-registry-overrides.json")
    )
    assert [s["canonical_key"] for s in supplementary if "personal-ops" in s["canonical_key"]] == []
    # Memory notes must point at the surviving identity, not the retired key.
    assert "supp:personal-ops" not in memory_meta.values()


def test_configured_overrides_settle_the_private_public_collisions():
    # ReturnRadar and cross-provider-egress-guard each exist twice: a private
    # working repo and a public release repo, colliding on one normalized form.
    # The operator settled both in favour of the private repo, so the Notion
    # binding must follow that decision rather than entry order.
    from github_repo_auditor.project_registry import load_overrides_config

    overrides, *_ = load_overrides_config(Path("config/project-registry-overrides.json"))
    assert overrides["ReturnRadar"] == "ReturnRadar"
    assert overrides["cross-provider-egress-guard"] == "cross-provider-egress-guard"
    # conductor is deliberately absent: its two identities are unrelated projects
    # and the Notion row belongs to neither by name alone.
    assert "conductor" not in {key.lower() for key in overrides}


def test_unverified_snapshot_page_ids_are_refused(tmp_path: Path):
    # A page id is a Notion write target. A snapshot missing its receipts -
    # stale, truncated, or hand-edited - must not be able to redirect one. With
    # no static fallback left, refusing verification means no id at all, which
    # is the safe direction: no target beats the wrong target.
    snap = _pid_snapshot(
        tmp_path, [{"title": "MCP Audit", "page_id": "untrusted-mcp"}], verified=False
    )
    registry = build_project_registry(
        SNAPSHOT,
        notion_snapshot_path=snap,
        overrides_config_path=None,
    )
    by_key = {e["canonical_key"]: e for e in registry["entries"]}
    # The title still binds: a wrong title costs enrichment, not a bad write.
    assert by_key["MCPAudit"]["notion_local_title"] == "MCP Audit"
    assert by_key["MCPAudit"]["notion_local_page_id"] is None


def test_tampered_snapshot_digest_refuses_page_ids(tmp_path: Path):
    snap = _pid_snapshot(tmp_path, [{"title": "MCP Audit", "page_id": "live-mcp"}])
    payload = json.loads(snap.read_text())
    payload["projects"][0]["page_id"] = "swapped-after-signing"
    snap.write_text(json.dumps(payload))
    registry = build_project_registry(
        SNAPSHOT,
        notion_snapshot_path=snap,
        overrides_config_path=None,
    )
    by_key = {e["canonical_key"]: e for e in registry["entries"]}
    assert by_key["MCPAudit"]["notion_local_page_id"] is None


def test_title_aliases_point_from_the_notion_title_to_the_registry_key(tmp_path: Path):
    # Direction matters and is easy to get backwards. The alias is consulted for
    # a raw string that failed to resolve, and the string that fails is the
    # Notion row title, so the alias key must be the title and the value the
    # registry key. Reversed, the snapshot row stays an orphan and the project
    # never receives its page id.
    snap = _pid_snapshot(tmp_path, [{"title": "MCP Audit Detector", "page_id": "live-mcp"}])
    overrides = tmp_path / "overrides.json"
    overrides.write_text(
        json.dumps({"notion_title_aliases": {"MCP Audit Detector": "MCPAudit"}})
    )
    registry = build_project_registry(
        SNAPSHOT,
        notion_snapshot_path=snap,
        overrides_config_path=overrides,
    )
    by_key = {e["canonical_key"]: e for e in registry["entries"]}
    assert by_key["MCPAudit"]["notion_local_title"] == "MCP Audit Detector"
    assert by_key["MCPAudit"]["notion_local_page_id"] == "live-mcp"
    assert registry["unmatched"]["notion_local"] == []


def test_configured_kbfreshness_alias_resolves_the_snapshot_title():
    # Regression: this alias was written KBFreshness -> KBFreshnessDetector,
    # which is the reverse of what the resolver consults. The snapshot row
    # "KBFreshnessDetector" sat unmatched and the project's page id had to come
    # from the static map instead of the live snapshot.
    from github_repo_auditor.project_registry import load_overrides_config

    *_, aliases, _, _ = load_overrides_config(
        Path("config/project-registry-overrides.json")
    )
    assert aliases.get("KBFreshnessDetector") == "KBFreshness"
    assert "KBFreshness" not in aliases
