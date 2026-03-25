from __future__ import annotations

import json
from pathlib import Path

from src.diff import diff_reports, format_diff_markdown


def _make_report(audits: list[dict], avg: float = 0.5, date: str = "2026-03-20") -> dict:
    tiers = {}
    for a in audits:
        t = a["completeness_tier"]
        tiers[t] = tiers.get(t, 0) + 1
    return {
        "generated_at": f"{date}T00:00:00+00:00",
        "total_repos": len(audits),
        "repos_audited": len(audits),
        "average_score": avg,
        "tier_distribution": tiers,
        "audits": audits,
    }


def _make_audit(name: str, score: float, tier: str) -> dict:
    return {
        "metadata": {"name": name},
        "overall_score": score,
        "completeness_tier": tier,
    }


class TestDiffReports:
    def test_new_repo_detected(self, tmp_path):
        prev = _make_report([_make_audit("Alpha", 0.8, "shipped")])
        curr = _make_report([_make_audit("Alpha", 0.8, "shipped"), _make_audit("Beta", 0.5, "wip")])
        (tmp_path / "prev.json").write_text(json.dumps(prev))
        (tmp_path / "curr.json").write_text(json.dumps(curr))

        diff = diff_reports(tmp_path / "prev.json", tmp_path / "curr.json")
        assert "Beta" in diff.new_repos
        assert len(diff.removed_repos) == 0

    def test_removed_repo_detected(self, tmp_path):
        prev = _make_report([_make_audit("Alpha", 0.8, "shipped"), _make_audit("Beta", 0.5, "wip")])
        curr = _make_report([_make_audit("Alpha", 0.8, "shipped")])
        (tmp_path / "prev.json").write_text(json.dumps(prev))
        (tmp_path / "curr.json").write_text(json.dumps(curr))

        diff = diff_reports(tmp_path / "prev.json", tmp_path / "curr.json")
        assert "Beta" in diff.removed_repos

    def test_tier_change_detected(self, tmp_path):
        prev = _make_report([_make_audit("Alpha", 0.5, "wip")])
        curr = _make_report([_make_audit("Alpha", 0.8, "shipped")])
        (tmp_path / "prev.json").write_text(json.dumps(prev))
        (tmp_path / "curr.json").write_text(json.dumps(curr))

        diff = diff_reports(tmp_path / "prev.json", tmp_path / "curr.json")
        assert len(diff.tier_changes) == 1
        assert diff.tier_changes[0]["old_tier"] == "wip"
        assert diff.tier_changes[0]["new_tier"] == "shipped"

    def test_score_change_tracked(self, tmp_path):
        prev = _make_report([_make_audit("Alpha", 0.5, "wip")], avg=0.5)
        curr = _make_report([_make_audit("Alpha", 0.7, "functional")], avg=0.7)
        (tmp_path / "prev.json").write_text(json.dumps(prev))
        (tmp_path / "curr.json").write_text(json.dumps(curr))

        diff = diff_reports(tmp_path / "prev.json", tmp_path / "curr.json")
        assert diff.average_score_delta > 0.1
        assert any(c["delta"] > 0.1 for c in diff.score_changes)

    def test_empty_diff(self, tmp_path):
        report = _make_report([_make_audit("Alpha", 0.5, "wip")])
        (tmp_path / "prev.json").write_text(json.dumps(report))
        (tmp_path / "curr.json").write_text(json.dumps(report))

        diff = diff_reports(tmp_path / "prev.json", tmp_path / "curr.json")
        assert len(diff.new_repos) == 0
        assert len(diff.removed_repos) == 0
        assert len(diff.tier_changes) == 0


class TestDiffMarkdown:
    def test_format_produces_markdown(self, tmp_path):
        prev = _make_report([_make_audit("Alpha", 0.5, "wip")])
        curr = _make_report([_make_audit("Alpha", 0.8, "shipped"), _make_audit("Beta", 0.3, "skeleton")])
        (tmp_path / "prev.json").write_text(json.dumps(prev))
        (tmp_path / "curr.json").write_text(json.dumps(curr))

        diff = diff_reports(tmp_path / "prev.json", tmp_path / "curr.json")
        md = format_diff_markdown(diff)
        assert "# Audit Diff Report" in md
        assert "Beta" in md
