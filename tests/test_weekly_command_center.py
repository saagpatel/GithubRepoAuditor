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


def _sec(available: bool, critical: int = 0, high: int = 0) -> dict:
    return {
        "alerts_available": available,
        "dependabot_critical": critical,
        "dependabot_high": high,
        "dependabot_medium": 0,
        "dependabot_low": 0,
        "code_scanning_critical": 0,
        "code_scanning_high": 0,
        "secret_scanning_open": 0,
    }


def _security_project(name: str, tier: str, security: dict, factors: list | None = None) -> dict:
    return {
        "identity": {"display_name": name},
        "declared": {"operating_path": "maintain"},
        "derived": {
            "registry_status": "active",
            "activity_status": "active",
            "path_override": "",
            "path_confidence": "high",
            "context_quality": "standard",
        },
        "risk": {
            "risk_tier": tier,
            "risk_factors": factors or [],
            "risk_summary": f"{name} risk.",
            "doctor_gap": False,
            "context_risk": False,
            "path_risk": False,
            "security_risk": bool(
                security.get("dependabot_high") or security.get("dependabot_critical")
            ),
        },
        "security": security,
    }


def _digest_for(portfolio_truth: dict) -> dict:
    report_data = {
        "username": "testuser",
        "generated_at": "2026-04-14T12:00:00+00:00",
        "operator_summary": {"decision_quality_v1": {}},
        "audits": [],
    }
    snapshot = {"operator_summary": report_data["operator_summary"], "operator_queue": []}
    return build_weekly_command_center_digest(
        report_data,
        snapshot,
        portfolio_truth=portfolio_truth,
        generated_at="2026-04-14T12:00:00+00:00",
    )


def test_security_posture_surfaces_open_alerts_critical_first() -> None:
    portfolio_truth = {
        "projects": [
            _security_project(
                "CriticalRepo",
                "elevated",
                _sec(True, critical=2, high=1),
                ["active-high-severity-alerts"],
            ),
            _security_project(
                "HighRepo",
                "moderate",
                _sec(True, critical=0, high=3),
                ["active-high-severity-alerts"],
            ),
            _security_project("CleanRepo", "baseline", _sec(True, 0, 0)),
            _security_project("UnscannedRepo", "baseline", _sec(False, 0, 0)),
        ]
    }
    digest = _digest_for(portfolio_truth)
    posture = digest["security_posture"]

    # Only repos with alerts_available are scanned; UnscannedRepo is excluded.
    assert posture["scanned_count"] == 3
    assert posture["repos_with_open_high_critical"] == 2
    assert posture["total_open_critical"] == 2
    assert posture["total_open_high"] == 4

    top = posture["top_alerts"]
    assert [item["repo"] for item in top] == ["CriticalRepo", "HighRepo"]
    assert top[0]["dependabot_critical"] == 2

    rendered = render_weekly_command_center_markdown(digest)
    assert "## Security Posture" in rendered
    assert "CriticalRepo" in rendered
    assert "2 critical, 1 high" in rendered


def test_security_posture_reports_clean_when_scanned_and_no_open_alerts() -> None:
    portfolio_truth = {
        "projects": [
            _security_project("CleanA", "baseline", _sec(True, 0, 0)),
            _security_project("CleanB", "baseline", _sec(True, 0, 0)),
        ]
    }
    digest = _digest_for(portfolio_truth)
    assert digest["security_posture"]["scanned_count"] == 2
    assert digest["security_posture"]["top_alerts"] == []

    rendered = render_weekly_command_center_markdown(digest)
    assert "All 2 scanned repos are clear" in rendered


def test_security_posture_reports_not_run_when_no_overlay() -> None:
    # The existing fixture has no security blocks → overlay was not run.
    digest = _digest_for(_make_portfolio_truth())
    assert digest["security_posture"]["scanned_count"] == 0
    assert digest["security_posture"]["top_alerts"] == []

    rendered = render_weekly_command_center_markdown(digest)
    assert "## Security Posture" in rendered
    assert "Security overlay not run" in rendered
