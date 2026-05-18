"""Core hidden-sheet row builders for the Excel workbook."""

from __future__ import annotations

import json

from src.analyst_views import build_analyst_context
from src.excel_report_helpers import collection_memberships
from src.excel_timeline_helpers import (
    extend_portfolio_trend_with_current,
    extend_score_history_with_current,
)


def build_core_hidden_rows(
    data: dict,
    trend_data: list[dict] | None,
    score_history: dict[str, list[float]] | None,
    *,
    trend_history_window: int,
    tier_order: list[str],
) -> dict[str, list[list[object]]]:
    memberships = collection_memberships(data)
    extended_score_history = extend_score_history_with_current(data, score_history)
    extended_trends = extend_portfolio_trend_with_current(data, trend_data)

    repo_rows: list[list[object]] = []
    dimension_rows: list[list[object]] = []
    lens_rows: list[list[object]] = []
    history_rows: list[list[object]] = []
    trend_matrix_rows: list[list[object]] = []
    portfolio_history_rows: list[list[object]] = []
    rollup_rows: list[list[object]] = []
    review_target_rows: list[list[object]] = []
    review_history_rows: list[list[object]] = []
    security_rows: list[list[object]] = []
    security_control_rows: list[list[object]] = []
    security_provider_rows: list[list[object]] = []
    security_alert_rows: list[list[object]] = []
    action_rows: list[list[object]] = []
    collection_rows: list[list[object]] = []
    scenario_rows: list[list[object]] = []
    governance_rows: list[list[object]] = []
    campaign_rows: list[list[object]] = []
    writeback_rows: list[list[object]] = []
    portfolio_catalog_rows: list[list[object]] = []
    scorecard_rows: list[list[object]] = []
    implementation_hotspot_rows: list[list[object]] = []
    lookup_rows: list[list[object]] = []

    for audit in data.get("audits", []):
        metadata = audit.get("metadata", {})
        repo_name = metadata.get("name", "")
        lenses = audit.get("lenses", {})
        repo_rows.append(
            [
                repo_name,
                metadata.get("full_name", ""),
                metadata.get("language") or "Unknown",
                "Yes" if metadata.get("private") else "No",
                "Yes" if metadata.get("archived") else "No",
                round(audit.get("overall_score", 0), 3),
                round(audit.get("interest_score", 0), 3),
                audit.get("grade", ""),
                audit.get("completeness_tier", ""),
                audit.get("security_posture", {}).get("label", "unknown"),
                ", ".join(memberships.get(repo_name, [])),
                lenses.get("ship_readiness", {}).get("score", 0.0),
                lenses.get("maintenance_risk", {}).get("score", 0.0),
                lenses.get("showcase_value", {}).get("score", 0.0),
                lenses.get("security_posture", {}).get("score", 0.0),
                lenses.get("momentum", {}).get("score", 0.0),
                lenses.get("portfolio_fit", {}).get("score", 0.0),
            ]
        )
        catalog = audit.get("portfolio_catalog", {})
        portfolio_catalog_rows.append(
            [
                repo_name,
                metadata.get("full_name", ""),
                catalog.get("owner", ""),
                catalog.get("team", ""),
                catalog.get("purpose", ""),
                catalog.get("lifecycle_state", ""),
                catalog.get("criticality", ""),
                catalog.get("review_cadence", ""),
                catalog.get("intended_disposition", ""),
                catalog.get("maturity_program", ""),
                catalog.get("target_maturity", ""),
                catalog.get("operating_path", ""),
                catalog.get("path_override", ""),
                catalog.get("path_confidence", ""),
                catalog.get("notes", ""),
                catalog.get("intent_alignment", "missing-contract"),
                catalog.get("intent_alignment_reason", ""),
                catalog.get("catalog_line", ""),
            ]
        )
        scorecard = audit.get("scorecard", {})
        scorecard_rows.append(
            [
                repo_name,
                metadata.get("full_name", ""),
                scorecard.get("program", ""),
                scorecard.get("program_label", ""),
                scorecard.get("score", 0.0),
                scorecard.get("maturity_level", ""),
                scorecard.get("target_maturity", ""),
                scorecard.get("status", ""),
                scorecard.get("passed_rules", 0),
                scorecard.get("applicable_rules", 0),
                ", ".join(scorecard.get("failed_rule_keys", [])),
                ", ".join(scorecard.get("top_gaps", [])),
                scorecard.get("summary", ""),
            ]
        )
        for hotspot in audit.get("implementation_hotspots", []):
            implementation_hotspot_rows.append(
                [
                    repo_name,
                    metadata.get("full_name", ""),
                    hotspot.get("scope", ""),
                    hotspot.get("path", ""),
                    hotspot.get("module", ""),
                    hotspot.get("category", ""),
                    hotspot.get("pressure_score", 0.0),
                    hotspot.get("suggestion_type", ""),
                    hotspot.get("why_it_matters", ""),
                    hotspot.get("suggested_first_move", ""),
                    hotspot.get("signal_summary", ""),
                ]
            )

        for result in audit.get("analyzer_results", []):
            dimension_rows.append(
                [
                    repo_name,
                    result.get("dimension", ""),
                    result.get("score", 0.0),
                    result.get("max_score", 1.0),
                    "; ".join(result.get("findings", [])[:3]),
                ]
            )

        for lens_name, lens_data in lenses.items():
            lens_rows.append(
                [
                    repo_name,
                    lens_name,
                    lens_data.get("score", 0.0),
                    lens_data.get("orientation", ""),
                    lens_data.get("summary", ""),
                    ", ".join(lens_data.get("drivers", [])),
                ]
            )

        posture = audit.get("security_posture", {})
        security_rows.append(
            [
                repo_name,
                posture.get("label", "unknown"),
                posture.get("score", 0.0),
                posture.get("secrets_found", 0),
                len(posture.get("dangerous_files", [])),
                "Yes" if posture.get("has_security_md") else "No",
                "Yes" if posture.get("has_dependabot") else "No",
                "; ".join(posture.get("evidence", [])),
            ]
        )
        github = posture.get("github", {})
        security_control_rows.extend(
            [
                [
                    repo_name,
                    "security_md",
                    "enabled" if posture.get("has_security_md") else "missing",
                    "local",
                    "",
                ],
                [
                    repo_name,
                    "dependabot_config",
                    "enabled" if posture.get("has_dependabot") else "missing",
                    "local",
                    "",
                ],
                [
                    repo_name,
                    "dependency_graph",
                    github.get("dependency_graph_status", "unavailable"),
                    "github",
                    str(github.get("dependency_graph_enabled")),
                ],
                [
                    repo_name,
                    "sbom_export",
                    github.get("sbom_status", "unavailable"),
                    "github",
                    str(github.get("sbom_exportable")),
                ],
                [
                    repo_name,
                    "code_scanning",
                    github.get("code_scanning_status", "unavailable"),
                    "github",
                    str(github.get("code_scanning_alerts")),
                ],
                [
                    repo_name,
                    "secret_scanning",
                    github.get("secret_scanning_status", "unavailable"),
                    "github",
                    str(github.get("secret_scanning_alerts")),
                ],
            ]
        )
        for provider_name, provider_data in (posture.get("providers") or {}).items():
            security_provider_rows.append(
                [
                    repo_name,
                    provider_name,
                    "Yes" if provider_data.get("available") else "No",
                    provider_data.get("score", ""),
                    posture.get(provider_name, {}).get("reason", "")
                    if provider_name != "local"
                    else "",
                ]
            )
        security_alert_rows.append(
            [
                repo_name,
                "code_scanning",
                github.get("code_scanning_alerts") or 0,
                github.get("code_scanning_status", "unavailable"),
            ]
        )
        security_alert_rows.append(
            [
                repo_name,
                "secret_scanning",
                github.get("secret_scanning_alerts") or 0,
                github.get("secret_scanning_status", "unavailable"),
            ]
        )
        for recommendation in posture.get("recommendations", []):
            governance_rows.append(
                [
                    repo_name,
                    recommendation.get("key", ""),
                    recommendation.get("priority", "medium"),
                    recommendation.get("title", ""),
                    recommendation.get("expected_posture_lift", 0.0),
                    recommendation.get("effort", ""),
                    recommendation.get("source", ""),
                    recommendation.get("why", ""),
                ]
            )

        for action in audit.get("action_candidates", []):
            action_rows.append(
                [
                    repo_name,
                    action.get("key", ""),
                    action.get("title", ""),
                    action.get("lens", ""),
                    action.get("effort", ""),
                    action.get("confidence", 0.0),
                    action.get("expected_lens_delta", 0.0),
                    action.get("expected_tier_movement", ""),
                    action.get("rationale", ""),
                ]
            )

    if extended_score_history:
        for repo_name, scores in extended_score_history.items():
            for run_index, score in enumerate(scores, 1):
                history_rows.append([repo_name, run_index, score])
            padded_scores = ([None] * trend_history_window + list(scores))[-trend_history_window:]
            trend_matrix_rows.append([repo_name] + padded_scores)

    if extended_trends:
        for run_index, trend in enumerate(extended_trends, 1):
            history_rows.append(["__portfolio__", run_index, trend.get("average_score", 0.0)])
            portfolio_history_rows.append(
                [
                    run_index,
                    trend.get("date", ""),
                    trend.get("average_score", 0.0),
                    trend.get("repos_audited", 0),
                    trend.get("tier_distribution", {}).get("shipped", 0),
                    trend.get("tier_distribution", {}).get("functional", 0),
                    trend.get(
                        "security_average_score",
                        data.get("security_posture", {}).get("average_score", 0.0),
                    ),
                    "yes" if trend.get("review_emitted") else "no",
                    trend.get("campaign_drift_count", 0),
                    trend.get("governance_drift_count", 0),
                ]
            )

    for collection_name, collection_data in data.get("collections", {}).items():
        for rank_index, repo_data in enumerate(collection_data.get("repos", []), 1):
            repo_name = repo_data["name"] if isinstance(repo_data, dict) else str(repo_data)
            reason = repo_data.get("reason", "") if isinstance(repo_data, dict) else ""
            collection_rows.append(
                [
                    collection_name,
                    repo_name,
                    rank_index,
                    reason,
                    collection_data.get("description", ""),
                ]
            )

    scenario_summary = data.get("scenario_summary", {})
    for lever in scenario_summary.get("top_levers", []):
        scenario_rows.append(
            [
                lever.get("key", ""),
                lever.get("title", ""),
                lever.get("lens", ""),
                lever.get("repo_count", 0),
                lever.get("average_expected_lens_delta", 0.0),
                lever.get("projected_tier_promotions", 0),
            ]
        )
    projection = scenario_summary.get("portfolio_projection", {})
    if projection:
        scenario_rows.append(
            [
                "portfolio_projection",
                "Portfolio projection",
                "portfolio_fit",
                projection.get("projected_shipped", 0),
                projection.get("projected_average_score_delta", 0.0),
                projection.get("current_shipped", 0),
            ]
        )

    contexts: list[tuple[str, str | None, dict]] = []
    profile_names = list(data.get("profiles", {}).keys()) or ["default"]
    collection_names = [None] + list(data.get("collections", {}).keys())
    for profile_name in profile_names:
        for collection_name in collection_names:
            contexts.append(
                (
                    profile_name,
                    collection_name,
                    build_analyst_context(
                        data,
                        profile_name=profile_name,
                        collection_name=collection_name,
                    ),
                )
            )

    for profile_name, collection_name, context in contexts:
        leaders = context.get("profile_leaderboard", {}).get("leaders", [])
        top_repo = leaders[0]["name"] if leaders else ""
        for lens_name in data.get("lenses", {}):
            selected = [item for item in context.get("ranked_audits", [])]
            scores = [
                item.get("audit", {}).get("lenses", {}).get(lens_name, {}).get("score", 0.0)
                for item in selected
            ]
            rollup_rows.append(
                [
                    profile_name,
                    collection_name or "all",
                    lens_name,
                    len(selected),
                    round(sum(scores) / len(scores), 3) if scores else 0.0,
                    top_repo,
                    leaders[0]["profile_score"] if leaders else 0.0,
                ]
            )

    for item in data.get("review_targets", []):
        review_target_rows.append(
            [
                item.get("repo", ""),
                item.get("title", ""),
                item.get("severity", 0.0),
                item.get("next_step", ""),
                item.get("decision_hint", ""),
                "yes" if item.get("safe_to_defer") else "no",
            ]
        )

    for item in data.get("review_history", []):
        review_history_rows.append(
            [
                item.get("review_id", ""),
                item.get("source_run_id", ""),
                item.get("generated_at", ""),
                item.get("materiality", ""),
                item.get("material_change_count", 0),
                item.get("status", ""),
                item.get("decision_state", ""),
                item.get("sync_state", ""),
                "yes" if item.get("safe_to_defer") else "no",
                "yes" if item.get("emitted") else "no",
            ]
        )

    for lens_name, lens_data in data.get("lenses", {}).items():
        lookup_rows.append(["lens", lens_name, lens_data.get("description", "")])
    for profile_name, profile_data in data.get("profiles", {}).items():
        lookup_rows.append(["profile", profile_name, profile_data.get("description", "")])
    for tier_name in tier_order:
        lookup_rows.append(["tier", tier_name, str(data.get("tier_distribution", {}).get(tier_name, 0))])
    for audit in sorted(
        data.get("audits", []), key=lambda item: item.get("metadata", {}).get("name", "")
    ):
        repo_name = audit.get("metadata", {}).get("name", "")
        if repo_name:
            lookup_rows.append(["repo-selector", repo_name, repo_name])

    campaign_summary = data.get("campaign_summary", {})
    if campaign_summary:
        campaign_rows.append(
            [
                campaign_summary.get("campaign_type", ""),
                campaign_summary.get("label", ""),
                campaign_summary.get("portfolio_profile", "default"),
                campaign_summary.get("collection_name", ""),
                campaign_summary.get("action_count", 0),
                campaign_summary.get("repo_count", 0),
            ]
        )
    for result in data.get("writeback_results", {}).get("results", []):
        writeback_rows.append(
            [
                result.get("repo_full_name", ""),
                result.get("target", ""),
                result.get("status", ""),
                result.get("url", ""),
                json.dumps(result.get("before", {})),
                json.dumps(result.get("after", {})),
            ]
        )

    return {
        "repo_rows": repo_rows,
        "dimension_rows": dimension_rows,
        "lens_rows": lens_rows,
        "history_rows": history_rows,
        "trend_matrix_rows": trend_matrix_rows,
        "portfolio_history_rows": portfolio_history_rows,
        "rollup_rows": rollup_rows,
        "review_target_rows": review_target_rows,
        "review_history_rows": review_history_rows,
        "security_rows": security_rows,
        "security_control_rows": security_control_rows,
        "security_provider_rows": security_provider_rows,
        "security_alert_rows": security_alert_rows,
        "action_rows": action_rows,
        "collection_rows": collection_rows,
        "scenario_rows": scenario_rows,
        "governance_rows": governance_rows,
        "campaign_rows": campaign_rows,
        "writeback_rows": writeback_rows,
        "portfolio_catalog_rows": portfolio_catalog_rows,
        "scorecard_rows": scorecard_rows,
        "implementation_hotspot_rows": implementation_hotspot_rows,
        "lookup_rows": lookup_rows,
    }
