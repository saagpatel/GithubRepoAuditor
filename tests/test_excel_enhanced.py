from __future__ import annotations

import json
from pathlib import Path

from openpyxl import Workbook

from src.excel_export import (
    _build_all_repos,
    _build_repo_profiles,
    _build_security,
    _build_changes,
    _build_hidden_data_sheets,
    _build_hotspots,
    _build_portfolio_explorer,
    _build_by_lens,
    _build_compare_sheet,
    _build_scenario_planner,
    _build_executive_summary,
    _build_campaigns,
    _build_writeback_audit,
    RADAR_DIMS,
    RADAR_LABELS,
)


def _make_audit(name: str, score: float, grade: str = "C", tier: str = "functional", **kwargs) -> dict:
    dims = kwargs.get("dims", {})
    results = [
        {"dimension": d, "score": dims.get(d, score), "max_score": 1.0, "findings": [], "details": {}}
        for d in RADAR_DIMS
    ]
    # Add security dimension
    sec_details = kwargs.get("security_details", {"secrets_found": 0, "dangerous_files": [], "has_security_md": False, "has_dependabot": False})
    results.append({"dimension": "security", "score": kwargs.get("security_score", 0.8), "max_score": 1.0, "findings": [], "details": sec_details})
    # Add interest
    results.append({"dimension": "interest", "score": 0.3, "max_score": 1.0, "findings": [], "details": {}})
    return {
        "metadata": {"name": name, "html_url": f"https://github.com/user/{name}", "language": "Python"},
        "overall_score": score, "interest_score": 0.3, "grade": grade,
        "completeness_tier": tier, "badges": [], "flags": [],
        "lenses": {
            "ship_readiness": {"score": score, "orientation": "higher-is-better", "summary": "Ready", "drivers": []},
            "maintenance_risk": {"score": round(1 - score, 3), "orientation": "higher-is-riskier", "summary": "Risk", "drivers": []},
            "showcase_value": {"score": min(1.0, score + 0.1), "orientation": "higher-is-better", "summary": "Story", "drivers": []},
            "security_posture": {"score": kwargs.get("security_score", 0.8), "orientation": "higher-is-better", "summary": "Security", "drivers": []},
            "momentum": {"score": 0.5, "orientation": "higher-is-better", "summary": "Momentum", "drivers": []},
            "portfolio_fit": {"score": score, "orientation": "higher-is-better", "summary": "Fit", "drivers": []},
        },
        "security_posture": {
            "label": "healthy" if kwargs.get("security_score", 0.8) >= 0.65 else "critical",
            "score": kwargs.get("security_score", 0.8),
            "secrets_found": sec_details.get("secrets_found", 0),
            "dangerous_files": sec_details.get("dangerous_files", []),
            "has_security_md": sec_details.get("has_security_md", False),
            "has_dependabot": sec_details.get("has_dependabot", False),
            "evidence": [],
        },
        "action_candidates": [
            {
                "key": "testing",
                "title": "Strengthen tests",
                "lens": "ship_readiness",
                "effort": "medium",
                "confidence": 0.8,
                "expected_lens_delta": 0.12,
                "expected_tier_movement": "Closer to shipped",
                "rationale": "testing is weak",
            }
        ],
        "hotspots": [
            {
                "category": "finish-line",
                "severity": 0.72,
                "title": "Promising but under-finished",
                "summary": "Worth finishing",
                "recommended_action": "Strengthen tests",
            }
        ],
        "analyzer_results": results,
    }


def _make_report(audits=None) -> dict:
    if audits is None:
        audits = [
            _make_audit("RepoA", 0.85, "A", "shipped"),
            _make_audit("RepoB", 0.60, "C", "functional"),
            _make_audit("RepoC", 0.40, "D", "wip", security_score=0.3, security_details={"secrets_found": 2, "dangerous_files": [".env"], "has_security_md": False, "has_dependabot": False}),
        ]
    return {
        "audits": audits,
        "repos_audited": len(audits),
        "average_score": 0.62,
        "hotspots": [
            {
                "repo": "RepoC",
                "category": "security-debt",
                "severity": 0.83,
                "title": "Security posture needs attention",
                "summary": "Needs attention",
                "recommended_action": "Improve security posture",
                "tier": "wip",
            }
        ],
        "collections": {
            "showcase": {
                "description": "Worth showing",
                "repos": [{"name": "RepoA", "reason": "High value"}],
            }
        },
        "profiles": {
            "default": {"description": "Balanced"}
        },
        "lenses": {
            "ship_readiness": {"description": "Ready", "average_score": 0.7},
        },
        "scenario_summary": {
            "top_levers": [
                {
                    "key": "testing",
                    "title": "Strengthen tests",
                    "lens": "ship_readiness",
                    "repo_count": 2,
                    "average_expected_lens_delta": 0.11,
                    "projected_tier_promotions": 1,
                }
            ],
            "portfolio_projection": {
                "current_shipped": 1,
                "projected_shipped": 2,
                "projected_average_score_delta": 0.03,
            },
        },
        "security_posture": {
            "average_score": 0.61,
            "critical_repos": ["RepoC"],
            "repos_with_secrets": ["RepoC"],
            "provider_coverage": {
                "github": {"available_repos": 2, "total_repos": len(audits)},
                "scorecard": {"available_repos": 1, "total_repos": len(audits)},
            },
            "open_alerts": {"code_scanning": 2, "secret_scanning": 1},
        },
        "security_governance_preview": [
            {
                "repo": "RepoC",
                "key": "enable-codeql-default-setup",
                "priority": "high",
                "title": "Enable CodeQL default setup",
                "expected_posture_lift": 0.12,
                "effort": "medium",
                "source": "github",
                "why": "Code scanning is not configured",
            }
        ],
        "campaign_summary": {
            "campaign_type": "security-review",
            "label": "Security Review",
            "portfolio_profile": "default",
            "collection_name": None,
            "action_count": 1,
            "repo_count": 1,
        },
        "writeback_preview": {
            "repos": [
                {
                    "repo": "RepoC",
                    "topics": ["ghra-call-security-review"],
                    "issue_title": "[Repo Auditor] Security Review",
                    "notion_action_count": 1,
                    "action_ids": ["security-review-abc123"],
                }
            ]
        },
        "writeback_results": {
            "results": [
                {
                    "repo_full_name": "user/RepoC",
                    "target": "github-issue",
                    "status": "created",
                    "url": "https://github.com/user/RepoC/issues/1",
                }
            ]
        },
    }


class TestRadarChart:
    def test_creates_sheet(self):
        wb = Workbook()
        _build_repo_profiles(wb, _make_report())
        assert "Repo Profiles" in wb.sheetnames

    def test_has_charts(self):
        wb = Workbook()
        _build_repo_profiles(wb, _make_report())
        ws = wb["Repo Profiles"]
        assert len(ws._charts) >= 1

    def test_dimension_labels(self):
        wb = Workbook()
        _build_repo_profiles(wb, _make_report())
        ws = wb["Repo Profiles"]
        labels = [ws.cell(row=i+2, column=1).value for i in range(len(RADAR_LABELS))]
        assert labels == RADAR_LABELS


class TestSecuritySheet:
    def test_creates_sheet(self):
        wb = Workbook()
        _build_security(wb, _make_report())
        assert "Security" in wb.sheetnames

    def test_sorts_by_score_ascending(self):
        wb = Workbook()
        _build_security(wb, _make_report())
        ws = wb["Security"]
        # Row 2 should be worst security score
        assert ws.cell(row=2, column=2).value <= ws.cell(row=3, column=2).value

    def test_shows_secrets_found(self):
        wb = Workbook()
        _build_security(wb, _make_report())
        ws = wb["Security"]
        # Find RepoC (has 2 secrets) — should be first (lowest score)
        assert ws.cell(row=2, column=3).value == 2


class TestChangesSheet:
    def test_no_sheet_without_diff(self):
        wb = Workbook()
        _build_changes(wb, _make_report(), None)
        assert "Changes" not in wb.sheetnames

    def test_creates_sheet_with_diff(self):
        wb = Workbook()
        diff = {
            "tier_changes": [{"name": "RepoA", "old_tier": "functional", "new_tier": "shipped", "direction": "promotion", "old_score": 0.72, "new_score": 0.80}],
            "score_changes": [{"name": "RepoA", "old_score": 0.72, "new_score": 0.80, "delta": 0.08}],
            "average_score_delta": 0.03,
        }
        _build_changes(wb, _make_report(), diff)
        assert "Changes" in wb.sheetnames

    def test_shows_promotions(self):
        wb = Workbook()
        diff = {
            "tier_changes": [{"name": "RepoA", "old_tier": "functional", "new_tier": "shipped", "direction": "promotion", "old_score": 0.72, "new_score": 0.80}],
            "score_changes": [],
            "average_score_delta": 0.03,
        }
        _build_changes(wb, _make_report(), diff)
        ws = wb["Changes"]
        assert ws.cell(row=3, column=2).value == 1  # 1 promotion


class TestAllReposSheet:
    def _build(self, score_history=None):
        wb = Workbook()
        _build_all_repos(wb, _make_report(), score_history)
        return wb["All Repos"]

    def test_creates_sheet(self):
        wb = Workbook()
        _build_all_repos(wb, _make_report())
        assert "All Repos" in wb.sheetnames

    def test_headers_include_interest_breakdown(self):
        ws = self._build()
        header_values = [ws.cell(row=1, column=c).value for c in range(1, 28)]
        for label in ("Tech Novelty", "Burst", "Ambition", "Storytelling"):
            assert label in header_values, f"Missing header: {label}"

    def test_trend_is_column_27(self):
        ws = self._build()
        assert ws.cell(row=1, column=27).value == "Trend"

    def test_iconset_rule_on_score_column(self):
        wb = Workbook()
        _build_all_repos(wb, _make_report())
        ws = wb["All Repos"]
        rules = [
            rule
            for rule_list in ws.conditional_formatting._cf_rules.values()
            for rule in rule_list
            if rule.type == "iconSet"
        ]
        assert len(rules) >= 1, "Expected at least one iconSet rule on All Repos sheet"

    def test_sparkline_written_to_column_27(self):
        score_history = {"RepoA": [0.5, 0.6, 0.7, 0.8, 0.85]}
        ws = self._build(score_history=score_history)
        # Find RepoA row (sorted by score descending, RepoA has highest score)
        repoA_row = None
        for r in range(2, 10):
            if ws.cell(row=r, column=1).value == "RepoA":
                repoA_row = r
                break
        assert repoA_row is not None, "RepoA row not found"
        spark_val = ws.cell(row=repoA_row, column=27).value
        assert spark_val is not None, "Expected sparkline in column 27"


class TestSecurityIconSetRule:
    def test_iconset_rule_on_security_score_column(self):
        wb = Workbook()
        _build_security(wb, _make_report())
        ws = wb["Security"]
        rules = [
            rule
            for rule_list in ws.conditional_formatting._cf_rules.values()
            for rule in rule_list
            if rule.type == "iconSet"
        ]
        assert len(rules) >= 1, "Expected at least one iconSet rule on Security sheet"


class TestHotspotsAndDataSheets:
    def test_creates_hotspots_sheet(self):
        wb = Workbook()
        _build_hotspots(wb, _make_report())
        assert "Hotspots" in wb.sheetnames

    def test_hidden_data_sheets_are_created(self):
        wb = Workbook()
        _build_hidden_data_sheets(wb, _make_report(), trend_data=[{"average_score": 0.6}], score_history={"RepoA": [0.5, 0.8]})
        assert "Data_Repos" in wb.sheetnames
        assert "Data_Lenses" in wb.sheetnames
        assert wb["Data_Repos"].sheet_state == "hidden"

    def test_hidden_repo_sheet_has_structured_table(self):
        wb = Workbook()
        _build_hidden_data_sheets(wb, _make_report())
        ws = wb["Data_Repos"]
        assert ws.tables
        assert "tblRepos" in ws.tables


class TestAnalystWorkbookSheets:
    def test_creates_portfolio_explorer_and_by_lens(self):
        wb = Workbook()
        _build_portfolio_explorer(wb, _make_report(), portfolio_profile="default", collection="showcase")
        _build_by_lens(wb, _make_report(), portfolio_profile="default", collection="showcase")
        assert "Portfolio Explorer" in wb.sheetnames
        assert "By Lens" in wb.sheetnames

    def test_creates_campaign_and_writeback_sheets(self):
        wb = Workbook()
        _build_campaigns(wb, _make_report())
        _build_writeback_audit(wb, _make_report())
        assert "Campaigns" in wb.sheetnames
        assert "Writeback Audit" in wb.sheetnames

    def test_compare_sheet_only_when_diff_present(self):
        wb = Workbook()
        _build_compare_sheet(wb, None)
        assert "Compare" not in wb.sheetnames

        diff = {
            "previous_date": "2026-03-28T00:00:00+00:00",
            "current_date": "2026-03-29T00:00:00+00:00",
            "average_score_delta": 0.03,
            "lens_deltas": {"ship_readiness": 0.1},
            "repo_changes": [
                {
                    "name": "RepoA",
                    "delta": 0.1,
                    "old_tier": "functional",
                    "new_tier": "shipped",
                    "security_change": {"old_label": "watch", "new_label": "healthy"},
                    "hotspot_change": {"old_count": 1, "new_count": 0},
                    "collection_change": {"old": [], "new": ["showcase"]},
                }
            ],
        }
        _build_compare_sheet(wb, diff)
        assert "Compare" in wb.sheetnames

    def test_creates_scenario_and_executive_summary(self):
        wb = Workbook()
        _build_scenario_planner(wb, _make_report(), portfolio_profile="default", collection="showcase")
        _build_executive_summary(wb, _make_report(), None, portfolio_profile="default", collection="showcase")
        assert "Scenario Planner" in wb.sheetnames
        assert "Executive Summary" in wb.sheetnames

    def test_creates_security_phase_sheets(self):
        from src.excel_export import _build_security_controls, _build_supply_chain, _build_security_debt

        wb = Workbook()
        _build_security_controls(wb, _make_report())
        _build_supply_chain(wb, _make_report())
        _build_security_debt(wb, _make_report())
        assert "Security Controls" in wb.sheetnames
        assert "Supply Chain" in wb.sheetnames
        assert "Security Debt" in wb.sheetnames
