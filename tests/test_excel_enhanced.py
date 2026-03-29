from __future__ import annotations

import json
from pathlib import Path

from openpyxl import Workbook

from src.excel_export import (
    _build_all_repos,
    _build_repo_profiles,
    _build_security,
    _build_changes,
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
        "completeness_tier": tier, "badges": [], "flags": [], "analyzer_results": results,
    }


def _make_report(audits=None) -> dict:
    if audits is None:
        audits = [
            _make_audit("RepoA", 0.85, "A", "shipped"),
            _make_audit("RepoB", 0.60, "C", "functional"),
            _make_audit("RepoC", 0.40, "D", "wip", security_score=0.3, security_details={"secrets_found": 2, "dangerous_files": [".env"], "has_security_md": False, "has_dependabot": False}),
        ]
    return {"audits": audits, "repos_audited": len(audits), "average_score": 0.62}


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
