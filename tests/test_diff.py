from __future__ import annotations

import io
import json
from pathlib import Path

from src.diff import AuditDiff, diff_reports, format_diff_markdown, print_diff_summary


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


def _make_diff(**overrides) -> AuditDiff:
    defaults = dict(
        previous_date="2026-03-01T00:00:00+00:00",
        current_date="2026-03-29T00:00:00+00:00",
        new_repos=["Gamma"],
        removed_repos=["Delta"],
        tier_changes=[
            {"name": "Alpha", "old_tier": "wip", "new_tier": "functional",
             "old_score": 0.4, "new_score": 0.6},
        ],
        score_changes=[
            {"name": "Alpha", "old_score": 0.4, "new_score": 0.6, "delta": 0.2},
            {"name": "Beta", "old_score": 0.7, "new_score": 0.5, "delta": -0.2},
        ],
        average_score_delta=0.05,
        tier_distribution_delta={"wip": -1, "functional": 1},
    )
    defaults.update(overrides)
    return AuditDiff(**defaults)


class TestPrintDiffSummary:
    def test_prints_score_delta(self, capsys):
        diff = _make_diff(average_score_delta=0.123)
        print_diff_summary(diff)
        captured = capsys.readouterr()
        assert "0.123" in captured.err

    def test_positive_delta_shows_plus_sign(self, capsys):
        diff = _make_diff(average_score_delta=0.05)
        print_diff_summary(diff)
        captured = capsys.readouterr()
        assert "+0.050" in captured.err

    def test_negative_delta_shown_without_plus(self, capsys):
        diff = _make_diff(average_score_delta=-0.03)
        print_diff_summary(diff)
        captured = capsys.readouterr()
        assert "-0.030" in captured.err

    def test_tier_changes_table_appears(self, capsys):
        diff = _make_diff()
        print_diff_summary(diff)
        captured = capsys.readouterr()
        assert "Alpha" in captured.err
        assert "wip" in captured.err
        assert "functional" in captured.err

    def test_improvements_listed(self, capsys):
        diff = _make_diff(
            score_changes=[{"name": "Zeta", "old_score": 0.3, "new_score": 0.7, "delta": 0.4}],
            tier_changes=[],
        )
        print_diff_summary(diff)
        captured = capsys.readouterr()
        assert "Zeta" in captured.err
        assert "+0.400" in captured.err

    def test_regressions_listed(self, capsys):
        diff = _make_diff(
            score_changes=[{"name": "Eta", "old_score": 0.8, "new_score": 0.5, "delta": -0.3}],
            tier_changes=[],
        )
        print_diff_summary(diff)
        captured = capsys.readouterr()
        assert "Eta" in captured.err
        assert "-0.300" in captured.err

    def test_summary_counts_shown(self, capsys):
        diff = _make_diff(new_repos=["X", "Y"], removed_repos=["Z"])
        print_diff_summary(diff)
        captured = capsys.readouterr()
        assert "New repos: 2" in captured.err
        assert "Removed: 1" in captured.err

    def test_empty_diff_does_not_crash(self, capsys):
        diff = _make_diff(tier_changes=[], score_changes=[], new_repos=[], removed_repos=[])
        print_diff_summary(diff)
        captured = capsys.readouterr()
        assert "Portfolio Score Delta" in captured.err
