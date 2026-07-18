from __future__ import annotations

import re
import tempfile

from pathlib import Path

from src.portfolio_catalog import (
    build_catalog_line,
    build_intent_alignment_summary,
    build_portfolio_catalog_summary,
    catalog_entry_for_repo,
    evaluate_intent_alignment,
    group_entry_for_path,
    load_portfolio_catalog,
)
from src.portfolio_pathing import resolve_declared_operating_path


def test_load_portfolio_catalog_accepts_defaults_and_repo_entries(tmp_path: Path):
    path = tmp_path / "portfolio-catalog.yaml"
    path.write_text(
        """
defaults:
  lifecycle_state: maintenance
  criticality: medium
  review_cadence: monthly
  maturity_program: default
  target_maturity: operating

repos:
  user/RepoA:
    owner: d
    team: operator-loop
    purpose: flagship surface
    intended_disposition: maintain
    category: commercial
    tool_provenance: claude-code
    maturity_program: maintain
    target_maturity: strong
  RepoB:
    purpose: finishing push
    lifecycle_state: active
    intended_disposition: finish
groups:
  it:
    path_prefixes:
      - ITPRJsViaClaude
    section_marker: ITPRJsViaClaude/
    category: it-work
"""
    )

    catalog = load_portfolio_catalog(path)

    assert catalog["exists"] is True
    assert catalog["errors"] == []
    assert catalog["repos"]["user/repoa"]["criticality"] == "medium"
    assert catalog["repos"]["repob"]["review_cadence"] == "monthly"
    assert catalog["repos"]["user/repoa"]["maturity_program"] == "maintain"
    assert catalog["repos"]["repob"]["target_maturity"] == "operating"
    assert catalog["groups"]["it"]["category"] == "it-work"
    assert catalog["groups"]["it"]["section_marker"] == "ITPRJsViaClaude/"
    # doctor_standard defaults to empty when not specified
    assert catalog["repos"]["user/repoa"]["doctor_standard"] == ""
    assert catalog["repos"]["repob"]["doctor_standard"] == ""


def test_load_portfolio_catalog_indexes_repo_aliases(tmp_path: Path):
    path = tmp_path / "portfolio-catalog.yaml"
    path.write_text(
        """
repos:
  Signal & Noise:
    owner: d
    purpose: public portfolio surface
    lifecycle_state: active
    criticality: medium
    review_cadence: monthly
    intended_disposition: maintain
    category: vanity
    aliases:
      - signal-noise
""",
        encoding="utf-8",
    )

    catalog = load_portfolio_catalog(path)
    entry = catalog_entry_for_repo(
        {
            "name": "signal-noise",
            "full_name": "saagpatel/signal-noise",
            "path": "signal-noise",
        },
        catalog,
    )

    assert catalog["errors"] == []
    assert entry["has_explicit_entry"] is True
    assert entry["catalog_key"] == "Signal & Noise"
    assert entry["owner"] == "d"
    assert entry["matched_by"] == "path"


def test_load_portfolio_catalog_normalizes_doctor_standard(tmp_path: Path):
    path = tmp_path / "portfolio-catalog.yaml"
    path.write_text(
        """
defaults:
  lifecycle_state: maintenance

repos:
  RepoWithFullStandard:
    doctor_standard: full
  RepoWithBasicStandard:
    doctor_standard: basic
  RepoWithInvalidStandard:
    doctor_standard: invalid
  RepoWithNoStandard: {}
"""
    )

    catalog = load_portfolio_catalog(path)

    assert catalog["repos"]["repowithfullstandard"]["doctor_standard"] == "full"
    assert catalog["repos"]["repowithbasicstandard"]["doctor_standard"] == "basic"
    assert catalog["repos"]["repowithinvalidstandard"]["doctor_standard"] == ""
    assert catalog["repos"]["repowithnostandard"]["doctor_standard"] == ""


def test_load_portfolio_catalog_normalizes_automation_eligible(tmp_path: Path):
    path = tmp_path / "portfolio-catalog.yaml"
    path.write_text(
        """
repos:
  RepoEnabled:
    automation_eligible: "true"
  RepoDisabled:
    automation_eligible: "false"
  RepoAbsent: {}
"""
    )

    catalog = load_portfolio_catalog(path)

    assert catalog["repos"]["repoenabled"]["automation_eligible"] is True
    assert catalog["repos"]["repodisabled"]["automation_eligible"] is False
    assert catalog["repos"]["repoabsent"]["automation_eligible"] is False


def test_catalog_entry_for_repo_defaults_automation_eligible_false():
    catalog = {"repos": {}, "defaults": {}}
    entry = catalog_entry_for_repo(
        {"name": "unknown-repo", "full_name": "user/unknown-repo"}, catalog
    )
    assert entry["automation_eligible"] is False


def test_live_catalog_reflects_tribunal_reactivation_of_recovery_exclusions() -> None:
    # The 2026-06 recovery settlement archived these two; the operator-approved
    # 2026-07-17 Portfolio Tribunal ledger reversed both on live evidence
    # (engraph: in-flight perf branch + harness-registered MCP server;
    # reliability-vault: substantive feature commits 07-09/07-10). This pin now
    # guards the reactivated state; automation stays off pending re-review.
    catalog_path = Path(__file__).parents[1] / "config" / "portfolio-catalog.yaml"
    catalog = load_portfolio_catalog(catalog_path)

    for repo_name in ("engraph", "reliability-vault"):
        entry = catalog["repos"][repo_name]
        assert entry["lifecycle_state"] == "active"
        assert entry["operating_path"] == "maintain"
        # Migrated off the deprecated field; read-compat fallback is covered
        # separately by test_load_portfolio_catalog_warns_on_deprecated_disposition.
        assert entry["intended_disposition"] == ""
        assert entry["maturity_program"] == "maintain"
        assert entry["automation_eligible"] is False


def test_live_catalog_matches_operator_attention_reconciliation() -> None:
    catalog_path = Path(__file__).parents[1] / "config" / "portfolio-catalog.yaml"
    catalog = load_portfolio_catalog(catalog_path)

    tier_zero = {
        "MCPAudit": "infrastructure",
        "mcp-trust": "infrastructure",
        "bridge-db": "infrastructure",
        "GithubRepoAuditor": "infrastructure",
        "PortfolioCommandCenter": "infrastructure",
        "operant-public": "infrastructure",
        "portfolio-index": "commercial",
        "operator-os-explainer": "commercial",
    }
    for repo_name, category in tier_zero.items():
        entry = catalog["repos"][repo_name.lower()]
        assert entry["lifecycle_state"] == "active"
        assert entry["operating_path"] == "maintain"
        assert entry["category"] == category

    # Tier 1, Tier 2, and explicitly unranked projects remain available only when
    # the operator asks for them. They do not create default portfolio attention.
    manual_only = {
        "_machine/machine-control-tower",
        "agent-bridge",
        "knowledgecore",
        "mcpforge",
        "mcpaudit-web",
        "notification-hub",
        "cross-system-smoke",
        "continuity",
        "cross-provider-egress-guard",
        "cost-tracker",
        "portfolio-health",
        "portfolio-mcp",
        "Lazarus",
        "peer-agent-tools",
        "AIGCCore",
        "ApplyKit",
        "JobCommandCenter",
        "AIWorkFlow",
        "Phantom Frequencies",
        "SignalDecay",
        "Afterimage",
        "Liminal",
        "GPT_RAG",
        "DeepTank",
        "BattleGrid",
        "OddworksCabinet",
        "Temper",
        "book-two-manuscript",
        "ccusage",
        "manipulable-library",
    }
    for repo_name in manual_only:
        assert catalog["repos"][repo_name.lower()]["lifecycle_state"] == "manual-only"


def test_catalog_entry_matches_full_name_then_bare_name():
    catalog = {
        "repos": {
            "user/repoa": {
                "owner": "d",
                "team": "operator-loop",
                "purpose": "flagship surface",
                "lifecycle_state": "active",
                "criticality": "high",
                "review_cadence": "weekly",
                "intended_disposition": "maintain",
                "category": "commercial",
                "tool_provenance": "claude-code",
                "maturity_program": "maintain",
                "target_maturity": "strong",
                "notes": "",
                "catalog_key": "user/RepoA",
                "matched_by": "full-name",
                "has_explicit_entry": True,
            },
            "repob": {
                "owner": "",
                "team": "",
                "purpose": "finish this",
                "lifecycle_state": "active",
                "criticality": "medium",
                "review_cadence": "monthly",
                "intended_disposition": "finish",
                "category": "vanity",
                "tool_provenance": "codex",
                "maturity_program": "finish",
                "target_maturity": "operating",
                "notes": "",
                "catalog_key": "RepoB",
                "matched_by": "bare-name",
                "has_explicit_entry": True,
            },
        }
    }

    repo_a = catalog_entry_for_repo(
        {"name": "RepoA", "full_name": "user/RepoA"}, catalog
    )
    repo_b = catalog_entry_for_repo(
        {"name": "RepoB", "full_name": "user/RepoB"}, catalog
    )

    assert repo_a["matched_by"] == "full-name"
    assert repo_b["matched_by"] == "bare-name"


def test_catalog_entry_matches_path_before_full_name_and_bare_name():
    catalog = {
        "repos": {
            "teams/repo": {
                "owner": "remote-owner",
                "catalog_key": "teams/repo",
                "matched_by": "full-name",
                "has_explicit_entry": True,
            },
            "tools/repo": {
                "owner": "path-owner",
                "catalog_key": "Tools/Repo",
                "matched_by": "full-name",
                "has_explicit_entry": True,
            },
            "repo": {
                "owner": "bare-owner",
                "catalog_key": "Repo",
                "matched_by": "bare-name",
                "has_explicit_entry": True,
            },
        }
    }

    entry = catalog_entry_for_repo(
        {"name": "Repo", "full_name": "teams/repo", "path": "Tools/Repo"}, catalog
    )

    assert entry["owner"] == "path-owner"
    assert entry["matched_by"] == "path"


def test_catalog_entry_matches_unambiguous_path_basename():
    catalog = {
        "repos": {
            "_machine/machine-control-tower": {
                "owner": "d",
                "catalog_key": "_machine/machine-control-tower",
                "matched_by": "full-name",
                "has_explicit_entry": True,
            },
        }
    }

    entry = catalog_entry_for_repo(
        {"name": "machine-control-tower", "full_name": "user/machine-control-tower"},
        catalog,
    )

    assert entry["owner"] == "d"
    assert entry["matched_by"] == "path-basename"


def test_catalog_entry_does_not_guess_ambiguous_path_basename():
    catalog = {
        "repos": {
            "alpha/shared": {
                "owner": "alpha",
                "catalog_key": "alpha/shared",
                "matched_by": "full-name",
                "has_explicit_entry": True,
            },
            "beta/shared": {
                "owner": "beta",
                "catalog_key": "beta/shared",
                "matched_by": "full-name",
                "has_explicit_entry": True,
            },
        }
    }

    entry = catalog_entry_for_repo(
        {"name": "shared", "full_name": "user/shared"},
        catalog,
    )

    assert entry["has_explicit_entry"] is False
    assert entry["matched_by"] == ""


def test_group_entry_matches_path_prefix():
    catalog = {
        "groups": {
            "it": {
                "group_key": "it",
                "label": "IT Tools",
                "section_marker": "ITPRJsViaClaude/",
                "section_label": "IT Tools",
                "path_prefixes": ["ITPRJsViaClaude"],
                "category": "it-work",
                "tool_provenance": "claude-code",
                "has_explicit_entry": True,
                "order": 0,
            }
        }
    }

    group = group_entry_for_path("ITPRJsViaClaude/IncidentWorkbench", catalog)
    assert group["group_key"] == "it"
    assert group["category"] == "it-work"


def test_evaluate_intent_alignment_uses_disposition_and_focus():
    maintain_entry = {
        "has_explicit_entry": True,
        "intended_disposition": "maintain",
    }
    archive_entry = {
        "has_explicit_entry": True,
        "intended_disposition": "archive",
    }

    assert (
        evaluate_intent_alignment(
            maintain_entry,
            completeness_tier="functional",
            archived=False,
            operator_focus="Watch Closely",
        )[0]
        == "aligned"
    )
    assert (
        evaluate_intent_alignment(
            archive_entry,
            completeness_tier="abandoned",
            archived=False,
            operator_focus="Fragile",
        )[0]
        == "aligned"
    )
    assert (
        evaluate_intent_alignment(
            maintain_entry,
            completeness_tier="skeleton",
            archived=False,
            operator_focus="Revalidate",
        )[0]
        == "needs-review"
    )


def test_evaluate_intent_alignment_trusts_on_track_maintain_scorecard():
    maintain_entry = {
        "has_explicit_entry": True,
        "intended_disposition": "maintain",
        "scorecard": {
            "status": "on-track",
            "maturity_level": "leading",
            "target_maturity": "operating",
        },
    }

    alignment, reason = evaluate_intent_alignment(
        maintain_entry,
        completeness_tier="",
        archived=False,
        operator_focus="Act Now",
    )

    assert alignment == "aligned"
    assert "scorecard" in reason


def test_catalog_line_and_summaries_cover_missing_contracts():
    audits = [
        {
            "portfolio_catalog": {
                "has_explicit_entry": True,
                "owner": "d",
                "purpose": "flagship",
                "lifecycle_state": "active",
                "criticality": "high",
                "review_cadence": "weekly",
                "intended_disposition": "maintain",
                "intent_alignment": "aligned",
            }
        },
        {
            "portfolio_catalog": {
                "has_explicit_entry": False,
                "intent_alignment": "missing-contract",
            }
        },
    ]

    line = build_catalog_line(audits[0]["portfolio_catalog"])
    catalog_summary = build_portfolio_catalog_summary(audits)
    alignment_summary = build_intent_alignment_summary(audits)

    assert "flagship" in line
    assert catalog_summary["cataloged_repo_count"] == 1
    assert catalog_summary["missing_contract_count"] == 1
    assert alignment_summary["counts"]["aligned"] == 1
    assert alignment_summary["counts"]["missing-contract"] == 1


def test_load_portfolio_catalog_normalizes_operating_path(tmp_path: Path):
    path = tmp_path / "portfolio-catalog.yaml"
    path.write_text(
        """
repos:
  RepoA:
    owner: d
    lifecycle_state: active
    review_cadence: weekly
    operating_path: finish
"""
    )

    catalog = load_portfolio_catalog(path)

    assert catalog["errors"] == []
    assert catalog["warnings"] == []
    assert catalog["repos"]["repoa"]["operating_path"] == "finish"
    assert catalog["repos"]["repoa"]["intended_disposition"] == ""


def test_load_portfolio_catalog_warns_on_deprecated_disposition(tmp_path: Path):
    path = tmp_path / "portfolio-catalog.yaml"
    path.write_text(
        """
repos:
  RepoA:
    owner: d
    lifecycle_state: active
    review_cadence: weekly
    intended_disposition: maintain
groups:
  legacy:
    path_prefixes:
      - legacy
    intended_disposition: archive
"""
    )

    catalog = load_portfolio_catalog(path)

    assert catalog["errors"] == []
    assert catalog["repos"]["repoa"]["intended_disposition"] == "maintain"
    assert catalog["repos"]["repoa"]["operating_path"] == ""
    assert catalog["groups"]["legacy"]["intended_disposition"] == "archive"
    assert any(
        "RepoA" in w and "deprecated" in w and "intended_disposition" in w
        for w in catalog["warnings"]
    )
    assert any(
        "legacy" in w and "deprecated" in w and "intended_disposition" in w
        for w in catalog["warnings"]
    )


def test_evaluate_intent_alignment_falls_back_to_legacy_disposition():
    legacy_entry = {"has_explicit_entry": True, "intended_disposition": "archive"}
    migrated_entry = {"has_explicit_entry": True, "operating_path": "archive"}

    legacy_result = evaluate_intent_alignment(
        legacy_entry, completeness_tier="abandoned", archived=False, operator_focus=""
    )
    migrated_result = evaluate_intent_alignment(
        migrated_entry, completeness_tier="abandoned", archived=False, operator_focus=""
    )

    assert (
        legacy_result
        == migrated_result
        == (
            "aligned",
            "The repo posture already matches the plan to archive or let it stay dormant.",
        )
    )


def test_operating_path_takes_precedence_over_legacy_disposition_in_alignment():
    conflicting_entry = {
        "has_explicit_entry": True,
        "operating_path": "maintain",
        "intended_disposition": "archive",
    }

    alignment, _reason = evaluate_intent_alignment(
        conflicting_entry,
        completeness_tier="functional",
        archived=False,
        operator_focus="Watch Closely",
    )

    assert alignment == "aligned"


def test_live_catalog_migration_is_lossless_for_every_entry() -> None:
    """Whole-catalog parity proof for the intended_disposition -> operating_path
    migration: reconstruct the pre-migration catalog by mechanically inverting the
    rename on the live (migrated) file, then assert every repo and group entry
    resolves to the identical *stable path* either way. This runs against the real,
    full catalog (179 repo entries), not a toy sample.

    `path_source` is deliberately NOT required to match: moving a value from the
    deprecated `intended_disposition` fallback to the canonical `operating_path`
    field is supposed to flip the provenance label from "intended-disposition" to
    "explicit-operating-path" -- that label change is the correct, intended
    signal that the entry now declares its path explicitly rather than relying on
    the fallback. What must not change is the routing decision itself, since risk
    tier and attention state are pure functions of the resolved path value."""
    live_path = Path(__file__).parents[1] / "config" / "portfolio-catalog.yaml"
    migrated_text = live_path.read_text()
    assert "intended_disposition:" not in migrated_text, (
        "fixture assumption: the live catalog has fully migrated to operating_path"
    )

    pre_migration_text = re.sub(
        r"^(\s*)operating_path:",
        r"\1intended_disposition:",
        migrated_text,
        flags=re.MULTILINE,
    )

    migrated = load_portfolio_catalog(live_path)

    with tempfile.TemporaryDirectory() as tmp_dir:
        pre_migration_path = Path(tmp_dir) / "portfolio-catalog.yaml"
        pre_migration_path.write_text(pre_migration_text)
        pre_migration = load_portfolio_catalog(pre_migration_path)

    assert pre_migration["errors"] == []
    assert migrated["errors"] == []

    repo_keys = set(migrated["repos"]) | set(pre_migration["repos"])
    assert repo_keys, "live catalog must have at least one repo entry to prove parity"

    mismatches = []
    migrated_source_counts: dict[str, int] = {}
    for repo_key in sorted(repo_keys):
        before_path, _before_source = resolve_declared_operating_path(
            pre_migration["repos"][repo_key]
        )
        after_path, after_source = resolve_declared_operating_path(
            migrated["repos"][repo_key]
        )
        if before_path != after_path:
            mismatches.append((repo_key, before_path, after_path))
        migrated_source_counts[after_source] = (
            migrated_source_counts.get(after_source, 0) + 1
        )

    assert mismatches == [], (
        f"{len(mismatches)} repo(s) resolve to a different path after migration: {mismatches}"
    )
    # Every migrated entry with a declared path now resolves via the canonical
    # field, not the deprecated fallback -- the whole point of the migration.
    assert migrated_source_counts.get("intended-disposition", 0) == 0
    assert migrated_source_counts.get("explicit-operating-path", 0) == len(repo_keys)

    group_keys = set(migrated["groups"]) | set(pre_migration["groups"])
    for group_key in sorted(group_keys):
        before_path, _before_source = resolve_declared_operating_path(
            pre_migration["groups"][group_key]
        )
        after_path, _after_source = resolve_declared_operating_path(
            migrated["groups"][group_key]
        )
        assert before_path == after_path, (
            f"group '{group_key}' resolves to a different path: "
            f"{before_path} vs {after_path}"
        )
