"""Repo detail and run-change row builders for workbook hidden sheets."""

from __future__ import annotations

from src.excel_detail_helpers import repo_detail_last_movement
from src.excel_report_helpers import collection_memberships, severity_rank
from src.excel_timeline_helpers import extend_score_history_with_current
from src.report_enrichment import (
    build_repo_briefing,
    build_run_change_counts,
    build_run_change_summary,
    build_score_explanation,
)
from src.sparkline import sparkline as render_sparkline


def score_explanation_for_audit(audit: dict) -> dict:
    explanation = dict(audit.get("score_explanation") or {})
    if explanation:
        return explanation
    return build_score_explanation(audit)


def repo_detail_rows(
    data: dict, score_history: dict[str, list[float]] | None
) -> tuple[list[list[object]], list[list[object]], list[list[object]]]:
    memberships = collection_memberships(data)
    history = extend_score_history_with_current(data, score_history)
    detail_rows: list[list[object]] = []
    dimension_rows: list[list[object]] = []
    history_rows: list[list[object]] = []

    for audit in sorted(
        data.get("audits", []), key=lambda item: item.get("metadata", {}).get("name", "")
    ):
        metadata = audit.get("metadata", {})
        repo_name = metadata.get("name", "")
        explanation = score_explanation_for_audit(audit)
        briefing = build_repo_briefing(audit, data, None)
        hotspot_titles = [item.get("title", "") for item in (audit.get("hotspots") or [])[:3]]
        implementation_hotspot_lines = [
            f"{item.get('path', 'repo root')}: {item.get('signal_summary', 'No signal summary recorded yet.')}"
            for item in (briefing.get("implementation_hotspots") or [])[:3]
        ]
        action_titles = [item.get("title", "") for item in (audit.get("action_candidates") or [])[:3]]
        lenses = audit.get("lenses", {})
        scores = history.get(repo_name, [])
        detail_rows.append(
            [
                repo_name,
                metadata.get("html_url", ""),
                metadata.get("language") or "Unknown",
                metadata.get("description") or "No description recorded yet.",
                round(audit.get("overall_score", 0.0), 3),
                round(audit.get("interest_score", 0.0), 3),
                audit.get("grade", ""),
                audit.get("completeness_tier", ""),
                ", ".join(audit.get("badges", [])[:6]) or "None",
                ", ".join(audit.get("flags", [])[:6]) or "None",
                ", ".join(memberships.get(repo_name, [])) or "—",
                audit.get("security_posture", {}).get("label", "unknown"),
                round(audit.get("security_posture", {}).get("score", 0.0), 3),
                lenses.get("ship_readiness", {}).get("summary", "")
                or "No ship-readiness summary recorded yet.",
                lenses.get("momentum", {}).get("summary", "")
                or "No momentum summary recorded yet.",
                lenses.get("security_posture", {}).get("summary", "")
                or "No security summary recorded yet.",
                lenses.get("portfolio_fit", {}).get("summary", "")
                or "No portfolio-fit summary recorded yet.",
                render_sparkline(scores)
                if scores
                else briefing.get("current_state", {}).get("trend", "No trend history yet."),
                briefing.get("why_this_repo_looks_this_way", {}).get(
                    "strongest_drivers",
                    ", ".join(explanation.get("top_positive_drivers", [])[:3])
                    or "No strong positive drivers recorded yet.",
                ),
                briefing.get("why_this_repo_looks_this_way", {}).get(
                    "biggest_drags",
                    ", ".join(explanation.get("top_negative_drivers", [])[:3])
                    or "No major drag factors recorded yet.",
                ),
                briefing.get("why_this_repo_looks_this_way", {}).get(
                    "next_tier_gap",
                    explanation.get("next_tier_gap_summary", "")
                    or "No next-tier gap is recorded yet.",
                ),
                briefing.get("what_to_do_next", {}).get(
                    "next_best_action",
                    explanation.get("next_best_action", "")
                    or "No clear next action is recorded yet.",
                ),
                briefing.get("what_to_do_next", {}).get(
                    "rationale",
                    explanation.get("next_best_action_rationale", "")
                    or "No action rationale is recorded yet.",
                ),
                briefing.get("what_changed", {}).get(
                    "top_hotspot_context",
                    hotspot_titles[0] if len(hotspot_titles) > 0 else "No hotspot recorded yet.",
                ),
                hotspot_titles[1]
                if len(hotspot_titles) > 1
                else "No secondary hotspot recorded yet.",
                hotspot_titles[2] if len(hotspot_titles) > 2 else "No third hotspot recorded yet.",
                briefing.get("what_to_do_next", {}).get(
                    "next_best_action",
                    action_titles[0]
                    if len(action_titles) > 0
                    else "No action candidate recorded yet.",
                ),
                action_titles[1]
                if len(action_titles) > 1
                else "No second action candidate recorded yet.",
                action_titles[2]
                if len(action_titles) > 2
                else "No third action candidate recorded yet.",
                briefing.get("what_changed", {}).get(
                    "last_movement", repo_detail_last_movement(scores)
                ),
                briefing.get("what_changed", {}).get(
                    "recent_change_summary", "No recent change summary is recorded yet."
                ),
                briefing.get("what_to_do_next", {}).get("follow_through_status", "Unknown"),
                briefing.get("what_to_do_next", {}).get(
                    "follow_through_summary", "No follow-through evidence is recorded yet."
                ),
                briefing.get("what_to_do_next", {}).get("checkpoint_timing", "Unknown"),
                briefing.get("what_to_do_next", {}).get("escalation", "Unknown"),
                briefing.get("what_to_do_next", {}).get(
                    "escalation_summary",
                    "No stronger follow-through escalation is currently surfaced.",
                ),
                briefing.get("what_to_do_next", {}).get("recovery_retirement", "None"),
                briefing.get("what_to_do_next", {}).get(
                    "recovery_retirement_summary",
                    "No follow-through recovery or escalation-retirement signal is currently surfaced.",
                ),
                briefing.get("what_to_do_next", {}).get("recovery_persistence", "None"),
                briefing.get("what_to_do_next", {}).get(
                    "recovery_persistence_summary",
                    "No follow-through recovery persistence signal is currently surfaced.",
                ),
                briefing.get("what_to_do_next", {}).get("relapse_churn", "None"),
                briefing.get("what_to_do_next", {}).get(
                    "relapse_churn_summary", "No relapse churn is currently surfaced."
                ),
                briefing.get("what_to_do_next", {}).get("recovery_freshness", "None"),
                briefing.get("what_to_do_next", {}).get(
                    "recovery_freshness_summary",
                    "No follow-through recovery freshness signal is currently surfaced.",
                ),
                briefing.get("what_to_do_next", {}).get("recovery_memory_reset", "None"),
                briefing.get("what_to_do_next", {}).get(
                    "recovery_memory_reset_summary",
                    "No follow-through recovery memory reset signal is currently surfaced.",
                ),
                briefing.get("what_to_do_next", {}).get("recovery_rebuild_strength", "None"),
                briefing.get("what_to_do_next", {}).get(
                    "recovery_rebuild_strength_summary",
                    "No follow-through recovery rebuild-strength signal is currently surfaced.",
                ),
                briefing.get("what_to_do_next", {}).get("recovery_reacquisition", "None"),
                briefing.get("what_to_do_next", {}).get(
                    "recovery_reacquisition_summary",
                    "No follow-through recovery reacquisition signal is currently surfaced.",
                ),
                briefing.get("what_to_do_next", {}).get("reacquisition_durability", "None"),
                briefing.get("what_to_do_next", {}).get(
                    "reacquisition_durability_summary",
                    "No follow-through reacquisition durability signal is currently surfaced.",
                ),
                briefing.get("what_to_do_next", {}).get("reacquisition_confidence", "None"),
                briefing.get("what_to_do_next", {}).get(
                    "reacquisition_confidence_summary",
                    "No follow-through reacquisition confidence-consolidation signal is currently surfaced.",
                ),
                briefing.get("what_to_do_next", {}).get("reacquisition_softening_decay", "None"),
                briefing.get("what_to_do_next", {}).get(
                    "reacquisition_softening_decay_summary",
                    "No reacquisition softening-decay signal is currently surfaced.",
                ),
                briefing.get("what_to_do_next", {}).get(
                    "reacquisition_confidence_retirement", "None"
                ),
                briefing.get("what_to_do_next", {}).get(
                    "reacquisition_confidence_retirement_summary",
                    "No reacquisition confidence-retirement signal is currently surfaced.",
                ),
                briefing.get("what_to_do_next", {}).get("revalidation_recovery", "None"),
                briefing.get("what_to_do_next", {}).get(
                    "revalidation_recovery_summary",
                    "No post-revalidation recovery or confidence re-earning signal is currently surfaced.",
                ),
                briefing.get("what_to_do_next", {}).get(
                    "what_would_count_as_progress",
                    "Use the next run or linked artifact to confirm whether the recommendation moved.",
                ),
                briefing.get("catalog_line", "No portfolio catalog contract is recorded yet."),
                briefing.get(
                    "operating_path_line",
                    "Operating Path: Unspecified (legacy confidence) — No operating-path rationale is recorded yet.",
                ),
                briefing.get(
                    "intent_alignment_line",
                    "missing-contract: Intent alignment cannot be judged until a portfolio catalog contract exists.",
                ),
                briefing.get("scorecard_line", "Scorecard: No maturity scorecard is recorded yet."),
                briefing.get("maturity_gap_summary", "No maturity gap summary is recorded yet."),
                briefing.get(
                    "where_to_start_summary",
                    "No meaningful implementation hotspot is currently surfaced.",
                ),
                implementation_hotspot_lines[0]
                if len(implementation_hotspot_lines) > 0
                else "No implementation hotspot is currently surfaced.",
                implementation_hotspot_lines[1]
                if len(implementation_hotspot_lines) > 1
                else "No second implementation hotspot is currently surfaced.",
                implementation_hotspot_lines[2]
                if len(implementation_hotspot_lines) > 2
                else "No third implementation hotspot is currently surfaced.",
            ]
        )

        ranked_dimensions = sorted(
            [
                (
                    result.get("dimension", ""),
                    round(result.get("score", 0.0), 3),
                    "; ".join((result.get("findings") or [])[:2]) or "No major concerns recorded.",
                )
                for result in audit.get("analyzer_results", [])
                if result.get("dimension") != "interest"
            ],
            key=lambda item: item[1],
        )
        for rank, (dimension, score, summary) in enumerate(ranked_dimensions, 1):
            lookup_key = f"{repo_name}::{rank}"
            dimension_rows.append([lookup_key, repo_name, rank, dimension, score, summary])

        for run_index, score in enumerate(scores, 1):
            history_rows.append([repo_name, run_index, score, render_sparkline(scores)])

    return detail_rows, dimension_rows, history_rows


def run_change_rows(
    data: dict, diff_data: dict | None
) -> tuple[list[list[object]], list[list[object]]]:
    counts = build_run_change_counts(diff_data)
    summary_rows = [
        ["Summary", build_run_change_summary(diff_data), ""],
        [
            "Score Improvements",
            counts.get("score_improvements", 0),
            "Repos that improved since the last run.",
        ],
        [
            "Score Regressions",
            counts.get("score_regressions", 0),
            "Repos that regressed since the last run.",
        ],
        ["Tier Promotions", counts.get("tier_promotions", 0), "Repos that moved up a tier."],
        ["Tier Demotions", counts.get("tier_demotions", 0), "Repos that moved down a tier."],
        ["New Repos", counts.get("new_repos", 0), "Repos that are new in this run."],
        [
            "Removed Repos",
            counts.get("removed_repos", 0),
            "Repos missing compared with the prior run.",
        ],
        [
            "Security Changes",
            counts.get("security_changes", 0),
            "Repos with security posture movement.",
        ],
        [
            "Governance Changes",
            counts.get("collection_changes", 0),
            "Repos with collection or governance drift.",
        ],
        [
            "Notable Repo Changes",
            counts.get("notable_repo_changes", 0),
            "Repos with notable diff rows.",
        ],
    ]

    repo_rows: list[list[object]] = []
    for change in diff_data.get("repo_changes", []) if diff_data else []:
        repo_rows.append(
            [
                "repo-change",
                change.get("name", ""),
                round(change.get("delta", 0.0), 3),
                change.get("old_tier", ""),
                change.get("new_tier", ""),
                change.get("security_change", {}).get("new_label", ""),
                change.get("hotspot_change", {}).get("new_count", 0),
                ", ".join(change.get("collection_change", {}).get("new", []) or []),
                "General repo movement since the previous run.",
            ]
        )
    for change in diff_data.get("tier_changes", []) if diff_data else []:
        repo_rows.append(
            [
                f"tier-{change.get('direction', 'change')}",
                change.get("name", ""),
                round(change.get("new_score", 0.0) - change.get("old_score", 0.0), 3),
                change.get("old_tier", ""),
                change.get("new_tier", ""),
                "",
                "",
                "",
                f"Tier {change.get('direction', 'change')} detected in the comparison window.",
            ]
        )
    for item in data.get("material_changes", []) or []:
        repo_rows.append(
            [
                f"material-{item.get('change_type', 'other')}",
                item.get("repo", ""),
                severity_rank(item.get("severity")),
                "",
                "",
                "",
                "",
                "",
                item.get("title", ""),
            ]
        )
    return summary_rows, repo_rows
