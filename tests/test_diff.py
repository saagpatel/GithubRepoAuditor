from __future__ import annotations

import json
from pathlib import Path

from src.diff import diff_reports, format_diff_markdown, print_diff_summary


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
        "lenses": {
            "ship_readiness": {"average_score": avg, "description": "Ready"},
            "security_posture": {"average_score": 0.4, "description": "Secure"},
        },
        "profiles": {
            "default": {
                "description": "Balanced",
                "lens_weights": {
                    "ship_readiness": 0.4,
                    "showcase_value": 0.3,
                    "security_posture": 0.3,
                },
            }
        },
        "collections": {
            "showcase": {
                "description": "Best examples",
                "repos": [{"name": audits[0]["metadata"]["name"], "reason": "leader"}] if audits else [],
            }
        },
        "scenario_summary": {
            "top_levers": [
                {
                    "key": "testing",
                    "title": "Strengthen tests",
                    "lens": "ship_readiness",
                    "repo_count": len(audits),
                    "average_expected_lens_delta": 0.1,
                    "projected_tier_promotions": 1,
                }
            ],
            "portfolio_projection": {
                "selected_repo_count": len(audits),
                "projected_average_score_delta": 0.03,
                "projected_tier_promotions": 1,
            },
        },
        "audits": audits,
    }


def _make_audit(name: str, score: float, tier: str) -> dict:
    return {
        "metadata": {"name": name},
        "overall_score": score,
        "completeness_tier": tier,
        "lenses": {
            "ship_readiness": {"score": score, "summary": "Ready"},
            "showcase_value": {"score": score, "summary": "Story"},
            "security_posture": {"score": 0.5, "summary": "Secure"},
        },
        "security_posture": {"label": "healthy", "score": 0.5},
        "hotspots": [{"title": "Promising but unfinished"}],
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

    def test_compare_payload_includes_analyst_fields(self, tmp_path):
        prev = _make_report([_make_audit("Alpha", 0.5, "wip")], avg=0.5)
        curr_audit = _make_audit("Alpha", 0.8, "shipped")
        curr_audit["security_posture"] = {"label": "strong", "score": 0.8}
        curr_audit["hotspots"] = []
        curr_audit["action_candidates"] = [
            {
                "key": "testing",
                "title": "Strengthen tests",
                "lens": "ship_readiness",
                "expected_lens_delta": 0.12,
                "expected_tier_movement": "Closer to shipped",
            }
        ]
        curr = _make_report([curr_audit], avg=0.8)
        curr["collections"]["showcase"]["repos"] = [{"name": "Alpha", "reason": "improved"}]
        curr["lenses"]["ship_readiness"]["average_score"] = 0.8
        (tmp_path / "prev.json").write_text(json.dumps(prev))
        (tmp_path / "curr.json").write_text(json.dumps(curr))

        diff = diff_reports(tmp_path / "prev.json", tmp_path / "curr.json")

        assert diff.repo_changes
        assert "ship_readiness" in diff.lens_deltas
        assert diff.profile_leaderboards
        assert diff.scenario_preview["portfolio_projection"]["projected_tier_promotions"] >= 1
        assert diff.security_changes
        assert diff.hotspot_changes


class TestDiffMarkdown:
    def test_format_produces_markdown(self, tmp_path):
        prev = _make_report([_make_audit("Alpha", 0.5, "wip")])
        curr = _make_report([_make_audit("Alpha", 0.8, "shipped"), _make_audit("Beta", 0.3, "skeleton")])
        curr["lenses"]["ship_readiness"]["average_score"] = 0.8
        (tmp_path / "prev.json").write_text(json.dumps(prev))
        (tmp_path / "curr.json").write_text(json.dumps(curr))

        diff = diff_reports(tmp_path / "prev.json", tmp_path / "curr.json")
        md = format_diff_markdown(diff)
        assert "# Audit Diff Report" in md
        assert "Beta" in md
        assert "Lens Deltas" in md
        assert "Scenario Preview" in md


class TestPrintDiffSummary:
    def test_prints_score_delta(self, capsys):
        from dataclasses import dataclass, field

        @dataclass
        class FakeDiff:
            average_score_delta: float = 0.05
            tier_changes: list = field(default_factory=list)
            score_changes: list = field(default_factory=list)
            new_repos: list = field(default_factory=list)
            removed_repos: list = field(default_factory=list)

        print_diff_summary(FakeDiff())
        captured = capsys.readouterr()
        assert "0.05" in captured.err or "0.050" in captured.err
