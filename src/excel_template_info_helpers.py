"""Helpers for workbook metadata and template-info content."""

from __future__ import annotations

from typing import Any


def build_named_range_targets(template_info_sheet: str) -> list[tuple[str, str]]:
    return [
        ("nrGeneratedAt", "'Dashboard'!$A$2"),
        ("nrReviewOpenCount", f"'{template_info_sheet}'!$B$2"),
        ("nrReviewDeferredCount", f"'{template_info_sheet}'!$B$3"),
        ("nrReviewResolvedCount", f"'{template_info_sheet}'!$B$4"),
        ("nrCampaignActionCount", f"'{template_info_sheet}'!$B$5"),
        ("nrCampaignRepoCount", f"'{template_info_sheet}'!$B$6"),
        ("nrGovernanceReadyCount", f"'{template_info_sheet}'!$B$7"),
        ("nrGovernanceDriftCount", f"'{template_info_sheet}'!$B$8"),
        ("nrPortfolioGrade", f"'{template_info_sheet}'!$B$9"),
        ("nrAverageScore", f"'{template_info_sheet}'!$B$10"),
        ("nrLatestReviewState", f"'{template_info_sheet}'!$B$11"),
        ("nrSelectedProfileLabel", f"'{template_info_sheet}'!$B$12"),
        ("nrSelectedCollectionLabel", f"'{template_info_sheet}'!$B$13"),
    ]


def build_dashboard_generated_label(data: dict[str, Any]) -> str:
    return f"Generated: {data['generated_at'][:10]} | {data['repos_audited']} repos audited"


def build_template_info_rows(
    *,
    data: dict[str, Any],
    counts: dict[str, int],
    portfolio_profile: str,
    collection: str | None,
    excel_mode: str,
) -> list[tuple[str, Any]]:
    return [
        ("Workbook Mode", excel_mode),
        ("Review Open Count", counts["open"]),
        ("Review Deferred Count", counts["deferred"]),
        ("Review Resolved Count", counts["resolved"]),
        ("Campaign Action Count", data.get("campaign_summary", {}).get("action_count", 0)),
        ("Campaign Repo Count", data.get("campaign_summary", {}).get("repo_count", 0)),
        (
            "Governance Ready Count",
            data.get("governance_preview", {}).get(
                "applyable_count", len(data.get("security_governance_preview", []) or [])
            ),
        ),
        ("Governance Drift Count", len(data.get("governance_drift", []) or [])),
        ("Latest Portfolio Grade", data.get("portfolio_grade", "F")),
        ("Latest Average Score", round(data.get("average_score", 0.0), 3)),
        ("Latest Review State", data.get("review_summary", {}).get("status", "open")),
        ("Selected Profile", portfolio_profile),
        ("Selected Collection", collection or "all"),
    ]
