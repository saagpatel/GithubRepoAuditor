from __future__ import annotations

from src.weekly_command_center import (
    build_weekly_command_center_digest,
    render_weekly_command_center_markdown,
)


def _make_portfolio_truth() -> dict:
    return {
        "projects": [
            {
                "identity": {"display_name": "GithubRepoAuditor"},
                "declared": {"operating_path": "maintain"},
                "derived": {
                    "registry_status": "active",
                    "activity_status": "active",
                    "path_override": "investigate",
                    "path_confidence": "low",
                    "context_quality": "boilerplate",
                    "path_rationale": "Still missing enough trustworthy context.",
                },
                "risk": {
                    "risk_tier": "elevated",
                    "risk_factors": ["weak-context-active", "investigate-override"],
                    "risk_summary": "2 risk factor(s): weak context quality, investigate override active.",
                    "doctor_gap": False,
                    "context_risk": True,
                    "path_risk": True,
                },
            },
            {
                "identity": {"display_name": "JobCommandCenter"},
                "declared": {"operating_path": ""},
                "derived": {
                    "registry_status": "active",
                    "activity_status": "active",
                    "path_override": "investigate",
                    "path_confidence": "low",
                    "context_quality": "boilerplate",
                    "path_rationale": "No stable path is declared yet.",
                },
                "risk": {
                    "risk_tier": "elevated",
                    "risk_factors": ["weak-context-active", "missing-operating-path"],
                    "risk_summary": "2 risk factor(s): weak context quality, no operating path declared.",
                    "doctor_gap": False,
                    "context_risk": True,
                    "path_risk": True,
                },
            },
            {
                "identity": {"display_name": "ArchiveMe"},
                "declared": {"operating_path": "archive"},
                "derived": {
                    "registry_status": "archived",
                    "activity_status": "stale",
                    "path_override": "",
                    "path_confidence": "high",
                    "context_quality": "standard",
                    "path_rationale": "Archive path is settled.",
                },
                "risk": {
                    "risk_tier": "deferred",
                    "risk_factors": [],
                    "risk_summary": "Archived or archive-path project.",
                    "doctor_gap": False,
                    "context_risk": False,
                    "path_risk": False,
                },
            },
        ]
    }


def test_build_weekly_command_center_digest_surfaces_truth_and_guardrails() -> None:
    report_data = {
        "username": "testuser",
        "generated_at": "2026-04-14T12:00:00+00:00",
        "latest_report_path": "output/audit-report-testuser-2026-04-14.json",
        "operator_summary": {
            "headline": "Urgent portfolio pressure is active.",
            "decision_quality_v1": {
                "decision_quality_status": "needs-skepticism",
                "human_skepticism_required": True,
                "recommendation_quality_summary": "Recent evidence is mixed, so keep a human in the loop.",
                "authority_cap": "advisory-only",
            },
            "top_preview_ready_campaigns": [
                {
                    "label": "Security Review",
                    "reason": "One campaign is preview ready.",
                    "recommended_target": "all",
                }
            ],
        },
        "operator_queue": [],
        "audits": [],
    }
    snapshot = {
        "operator_summary": report_data["operator_summary"],
        "operator_queue": [],
    }
    portfolio_truth = _make_portfolio_truth()

    digest = build_weekly_command_center_digest(
        report_data,
        snapshot,
        portfolio_truth=portfolio_truth,
        portfolio_truth_reference="output/portfolio-truth-latest.json",
        control_center_reference="output/operator-control-center-testuser-2026-04-14.json",
        report_reference="output/audit-report-testuser-2026-04-14.json",
        generated_at="2026-04-14T12:00:00+00:00",
    )

    assert digest["contract_version"] == "weekly_command_center_digest_v1"
    assert digest["authority_cap"] == "bounded-automation"
    assert digest["decision_quality"]["status"] == "needs-skepticism"
    assert digest["portfolio_truth"]["project_count"] == 3
    assert digest["portfolio_truth"]["investigate_override_count"] == 2
    assert digest["path_attention"][0]["repo"] == "JobCommandCenter"
    assert digest["path_attention"][0]["headline"] == "Unspecified stable path"
    assert digest["report_only_guardrail"].startswith("This digest is descriptive only.")

    # Risk posture assertions
    assert digest["risk_posture"]["elevated_count"] == 2
    assert digest["portfolio_truth"]["risk_tier_counts"]["elevated"] == 2
    assert digest["portfolio_truth"]["risk_tier_counts"]["deferred"] == 1

    rendered_md = render_weekly_command_center_markdown(digest)
    assert "## Risk Posture" in rendered_md
    assert "GithubRepoAuditor" in rendered_md
    assert "JobCommandCenter" in rendered_md
