from __future__ import annotations

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

    repo_a = catalog_entry_for_repo({"name": "RepoA", "full_name": "user/RepoA"}, catalog)
    repo_b = catalog_entry_for_repo({"name": "RepoB", "full_name": "user/RepoB"}, catalog)

    assert repo_a["matched_by"] == "full-name"
    assert repo_b["matched_by"] == "bare-name"


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
