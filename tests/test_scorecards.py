from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.scorecards import (
    build_scorecards_summary,
    evaluate_repo_scorecard,
    evaluate_scorecards_for_report,
    load_scorecards,
)


def _make_audit(
    *,
    name: str = "RepoA",
    disposition: str = "maintain",
    maturity_program: str = "",
    target_maturity: str = "",
    tier: str = "functional",
    readme: float = 0.9,
    testing: float = 0.8,
    cicd: float = 0.8,
    dependencies: float = 0.8,
    community_profile: float = 0.7,
    build_readiness: float = 0.8,
    activity_days: int = 30,
    ship_readiness: float = 0.8,
    security_score: float = 0.85,
    flags: list[str] | None = None,
) -> dict:
    return {
        "metadata": {
            "name": name,
            "full_name": f"user/{name}",
            "archived": False,
            "pushed_at": "2026-04-01T00:00:00+00:00",
        },
        "overall_score": 0.74,
        "interest_score": 0.45,
        "completeness_tier": tier,
        "flags": list(flags or []),
        "analyzer_results": [
            {"dimension": "readme", "score": readme, "details": {}},
            {"dimension": "testing", "score": testing, "details": {}},
            {"dimension": "cicd", "score": cicd, "details": {}},
            {"dimension": "dependencies", "score": dependencies, "details": {}},
            {"dimension": "community_profile", "score": community_profile, "details": {}},
            {"dimension": "build_readiness", "score": build_readiness, "details": {}},
            {"dimension": "activity", "score": 0.6, "details": {"days_since_push": activity_days}},
        ],
        "lenses": {
            "ship_readiness": {"score": ship_readiness},
        },
        "security_posture": {
            "score": security_score,
        },
        "portfolio_catalog": {
            "has_explicit_entry": True,
            "intended_disposition": disposition,
            "maturity_program": maturity_program,
            "target_maturity": target_maturity,
            "catalog_default_maturity_program": "",
            "catalog_default_target_maturity": "",
        },
    }


def test_load_scorecards_accepts_valid_programs(tmp_path: Path):
    pytest.importorskip("yaml")
    path = tmp_path / "scorecards.yaml"
    path.write_text(
        """
levels:
  - key: missing-basics
    threshold: 0.0
  - key: operating
    threshold: 0.60
programs:
  maintain:
    label: Maintain
    target_maturity: operating
    rules:
      - key: readme
        label: README
        check: dimension_at_least
        dimension: readme
        threshold: 0.60
        partial_threshold: 0.45
        weight: 1.0
"""
    )

    scorecards = load_scorecards(path)

    assert scorecards["exists"] is True
    assert scorecards["errors"] == []
    assert "maintain" in scorecards["programs"]
    assert scorecards["programs"]["maintain"]["target_maturity"] == "operating"


def test_load_scorecards_reports_invalid_checks_and_level_order(tmp_path: Path):
    pytest.importorskip("yaml")
    path = tmp_path / "scorecards.yaml"
    path.write_text(
        """
levels:
  - key: operating
    threshold: 0.60
  - key: foundation
    threshold: 0.35
programs:
  broken:
    rules:
      - key: nope
        check: unsupported_check
        weight: 1.0
"""
    )

    scorecards = load_scorecards(path)

    assert any("unsupported check" in error for error in scorecards["errors"])
    assert any("ordered by ascending threshold" in error for error in scorecards["errors"])


def test_evaluate_repo_scorecard_prefers_explicit_program_and_target(tmp_path: Path):
    pytest.importorskip("yaml")
    scorecards = load_scorecards(Path(__file__).resolve().parents[1] / "config" / "scorecards.yaml")
    audit = _make_audit(
        maturity_program="maintain",
        target_maturity="strong",
        testing=0.9,
        cicd=0.9,
        dependencies=0.9,
        community_profile=0.8,
        security_score=0.9,
        activity_days=20,
    )

    result = evaluate_repo_scorecard(audit, scorecards["programs"])

    assert result["program"] == "maintain"
    assert result["target_maturity"] == "strong"
    assert result["status"] == "on-track"
    assert result["maturity_level"] in {"strong", "leading"}


def test_evaluate_repo_scorecard_falls_back_to_disposition_program():
    programs = {
        "experiment": {
            "key": "experiment",
            "label": "Experiment",
            "description": "Lightweight bar",
            "target_maturity": "foundation",
            "levels": [
                {"key": "missing-basics", "label": "Missing Basics", "threshold": 0.0},
                {"key": "foundation", "label": "Foundation", "threshold": 0.35},
            ],
            "rules": [
                {
                    "key": "readme",
                    "label": "README",
                    "check": "dimension_at_least",
                    "dimension": "readme",
                    "threshold": 0.35,
                    "partial_threshold": 0.20,
                    "weight": 1.0,
                }
            ],
        }
    }
    audit = _make_audit(disposition="experiment", readme=0.4)

    result = evaluate_repo_scorecard(audit, programs)

    assert result["program"] == "experiment"
    assert result["status"] == "on-track"


def test_evaluate_scorecards_for_report_builds_summary():
    programs = {
        "maintain": {
            "key": "maintain",
            "label": "Maintain",
            "description": "Maintain bar",
            "target_maturity": "strong",
            "levels": [
                {"key": "missing-basics", "label": "Missing Basics", "threshold": 0.0},
                {"key": "foundation", "label": "Foundation", "threshold": 0.35},
                {"key": "strong", "label": "Strong", "threshold": 0.8},
            ],
            "rules": [
                {
                    "key": "testing",
                    "label": "Testing",
                    "check": "dimension_at_least",
                    "dimension": "testing",
                    "threshold": 0.8,
                    "partial_threshold": 0.6,
                    "weight": 1.0,
                }
            ],
        }
    }
    report = SimpleNamespace(
        audits=[
            _make_audit(name="RepoOnTrack", maturity_program="maintain", target_maturity="strong", testing=0.9),
            _make_audit(name="RepoBelow", maturity_program="maintain", target_maturity="strong", testing=0.4),
        ]
    )

    repo_results, summary, programs_summary = evaluate_scorecards_for_report(
        report,
        {"path": "config/scorecards.yaml", "exists": True, "errors": [], "warnings": [], "programs": programs},
    )

    assert len(repo_results) == 2
    assert summary["status_counts"]["on-track"] == 1
    assert summary["status_counts"]["below-target"] == 1
    assert summary["top_below_target_repos"][0]["repo"] == "RepoBelow"
    assert programs_summary["maintain"]["rule_count"] == 1


def test_build_scorecards_summary_mentions_config_errors():
    summary = build_scorecards_summary(
        [{"repo": "RepoA", "program": "default", "program_label": "Default", "maturity_level": "foundation", "status": "below-target", "summary": "Below target."}],
        {"path": "config/scorecards.yaml", "exists": True, "errors": ["bad rule"], "warnings": [], "programs": {}},
    )

    assert "below target" in summary["summary"]
    assert "config errors" in summary["summary"]
