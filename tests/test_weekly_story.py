from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from src.excel_export import _build_print_pack
from src.report_enrichment import build_weekly_review_pack
from src.review_pack import export_review_pack
from src.scheduled_handoff import render_scheduled_handoff_markdown
from src.web_export import _render_html


def _report() -> dict:
    return {
        "username": "testuser",
        "generated_at": "2026-04-13T12:00:00+00:00",
        "repos_audited": 1,
        "average_score": 0.61,
        "portfolio_grade": "C",
        "portfolio_catalog_summary": {"summary": "1/1 repos have an explicit catalog contract."},
        "intent_alignment_summary": {"summary": "1 aligned, 0 needing review, and 0 missing a contract."},
        "scorecards_summary": {"summary": "0 repos are on track, 1 is below target, and 0 are missing a valid program."},
        "implementation_hotspots_summary": {"summary": "1 repo has concrete implementation pressure. Start with RepoA in src/core.py."},
        "audits": [
            {
                "metadata": {
                    "name": "RepoA",
                    "full_name": "user/RepoA",
                    "description": "Shared weekly story repo",
                    "language": "Python",
                    "html_url": "https://github.com/user/RepoA",
                },
                "overall_score": 0.61,
                "grade": "C",
                "completeness_tier": "functional",
                "badges": [],
                "flags": [],
                "portfolio_catalog": {
                    "has_explicit_entry": True,
                    "owner": "d",
                    "team": "operator-loop",
                    "purpose": "shared weekly story repo",
                    "lifecycle_state": "active",
                    "criticality": "high",
                    "review_cadence": "weekly",
                    "intended_disposition": "maintain",
                    "catalog_line": "operator-loop | shared weekly story repo | lifecycle active | criticality high | cadence weekly | disposition maintain",
                    "intent_alignment": "aligned",
                    "intent_alignment_reason": "The repo still matches the maintain posture.",
                },
                "scorecard": {
                    "program": "maintain",
                    "program_label": "Maintain",
                    "maturity_level": "operating",
                    "target_maturity": "strong",
                    "status": "below-target",
                    "top_gaps": ["Testing", "CI"],
                    "summary": "Maintain is at Operating and still below the Strong target because testing and ci are behind.",
                },
                "implementation_hotspots": [
                    {
                        "scope": "file",
                        "path": "src/core.py",
                        "module": "src",
                        "category": "code-complexity",
                        "pressure_score": 0.71,
                        "suggestion_type": "refactor",
                        "why_it_matters": "src/core.py is carrying concentrated complexity.",
                        "suggested_first_move": "Split the biggest function and add one regression test.",
                        "signal_summary": "Complexity pressure 0.71 across 2 blocks.",
                    }
                ],
                "lenses": {
                    "ship_readiness": {"score": 0.61, "orientation": "higher-is-better", "summary": "Ready enough", "drivers": []},
                    "momentum": {"score": 0.55, "orientation": "higher-is-better", "summary": "Holding", "drivers": []},
                },
            }
        ],
        "operator_summary": {
            "headline": "Approval review is the clean next weekly step.",
            "counts": {"blocked": 0, "urgent": 1, "ready": 0, "deferred": 0},
            "what_to_do_next": "Review Governance: all next, then decide whether the approval still matches the packet.",
            "action_sync_summary": {
                "summary": "Action Sync is preview-ready: Security Review is the strongest next campaign to preview from the current local facts."
            },
            "next_action_sync_step": "Preview Security Review next, then decide whether it is ready to sync to all.",
            "apply_readiness_summary": {
                "summary": "Apply handoff says preview Security Review next before deciding on apply to all."
            },
            "next_apply_candidate": {
                "summary": "Preview Security Review next, then decide whether it is ready to apply to all.",
                "preview_command": "audit testuser --campaign security-review --writeback-target all",
            },
            "campaign_outcomes_summary": {
                "summary": "Security Review was applied recently; monitor it now before treating it as stable."
            },
            "next_monitoring_step": {
                "summary": "Monitor Security Review for at least 2 post-apply runs before treating it as stable."
            },
            "campaign_tuning_summary": {
                "summary": "Security Review should win ties because recent outcomes are proven."
            },
            "next_tuned_campaign": {
                "summary": "Security Review should win ties inside the preview-ready group because recent outcome history is proven."
            },
            "intervention_ledger_summary": {
                "summary": "RepoA is improving after intervention and should be watched for durable quieting."
            },
            "next_historical_focus": {
                "summary": "Read RepoA next: it is the clearest current example of improvement after intervention."
            },
            "automation_guidance_summary": {
                "summary": "Preview Security Review next; that is the strongest safe automation step right now."
            },
            "next_safe_automation_step": {
                "summary": "Preview Security Review next; that is the strongest safe automation step right now.",
                "recommended_command": "audit testuser --campaign security-review --writeback-target all",
            },
            "approval_workflow_summary": {
                "summary": "Governance: all is the strongest approval review candidate right now."
            },
            "next_approval_review": {
                "summary": "Review Governance: all next and decide whether to capture approval."
            },
            "top_preview_ready_campaigns": [
                {"label": "Security Review", "reason": "1 action is ready for preview.", "recommended_target": "all"}
            ],
            "top_ready_to_apply_packets": [
                {
                    "label": "Security Review",
                    "summary": "Preview first, then reassess apply.",
                    "preview_command": "audit testuser --campaign security-review --writeback-target all",
                }
            ],
            "top_monitor_now_campaigns": [
                {"label": "Security Review", "summary": "Still inside the short monitoring window."}
            ],
            "top_proven_campaigns": [
                {"label": "Security Review", "summary": "Recent outcomes are proven."}
            ],
            "top_improving_repos": [
                {"repo": "RepoA", "summary": "Improving after intervention."}
            ],
            "top_preview_safe_campaigns": [
                {
                    "label": "Security Review",
                    "summary": "Preview is the strongest safe automation posture.",
                    "recommended_command": "audit testuser --campaign security-review --writeback-target all",
                }
            ],
            "top_ready_for_review_approvals": [
                {
                    "label": "Governance: all",
                    "subject_key": "all",
                    "summary": "Governance scope all is ready for review.",
                    "approval_command": "audit testuser --approve-governance --governance-scope all",
                }
            ],
        },
        "operator_queue": [
            {
                "repo": "RepoA",
                "title": "RepoA approval follow-up",
                "lane": "urgent",
                "lane_label": "Urgent",
                "lane_reason": "Approval review is now the clean next step.",
                "recommended_action": "Review the approval packet and capture local approval if it still matches.",
                "follow_through_checkpoint": "Use the next run to confirm the packet still matches.",
                "follow_through_checkpoint_status": "due-soon",
                "catalog_line": "operator-loop | shared weekly story repo | lifecycle active | criticality high | cadence weekly | disposition maintain",
                "intent_alignment": "aligned",
                "intent_alignment_reason": "The repo still matches the maintain posture.",
                "scorecard": {
                    "program": "maintain",
                    "program_label": "Maintain",
                    "maturity_level": "operating",
                    "target_maturity": "strong",
                    "status": "below-target",
                    "top_gaps": ["Testing", "CI"],
                    "summary": "Maintain is at Operating and still below the Strong target because testing and ci are behind.",
                },
                "action_sync_line": "Action Sync: Security Review is preview-ready — recommended target all.",
                "apply_packet_line": "Apply Packet: Security Review is the best campaign to preview next before deciding on apply to all.",
                "post_apply_line": "Post-Apply Monitoring: Security Review was applied recently; monitor it now before treating it as stable.",
                "campaign_tuning_line": "Campaign Tuning: Security Review should win ties because recent outcomes are proven.",
                "historical_intelligence_line": "Historical Portfolio Intelligence: RepoA is improving after intervention and should be watched for durable quieting.",
                "automation_line": "Automation Guidance: Security Review is preview-safe: use a preview-only step first.",
                "approval_line": "Approval Workflow: Governance: all is ready for review.",
            }
        ],
        "approval_workflow_summary": {
            "summary": "Governance: all is the strongest approval review candidate right now."
        },
        "next_approval_review": {
            "summary": "Review Governance: all next and decide whether to capture approval."
        },
    }


def test_weekly_review_pack_exposes_structured_story_and_compact_explainability() -> None:
    weekly_pack = build_weekly_review_pack(_report())

    story = weekly_pack["weekly_story_v1"]
    assert story["version"] == 1
    assert story["headline"] == weekly_pack["portfolio_headline"]
    assert story["decision"] == weekly_pack["what_to_do_this_week"]
    assert "approval-workflow" in story["section_order"]
    approval_section = next(section for section in story["sections"] if section["id"] == "approval-workflow")
    assert approval_section["state"] == "ready-for-review"
    assert approval_section["next_label"] == "Next Approval Review"
    assert approval_section["evidence_items"][0]["command_hint"] == "audit testuser --approve-governance --governance-scope all"

    attention_item = weekly_pack["top_attention"][0]
    assert attention_item["why_it_won"] == "Approval review is now the clean next step."
    assert attention_item["evidence_strip"][0]["label"] == "Operator Focus"

    repo_briefing = weekly_pack["repo_briefings"][0]
    assert repo_briefing["why_it_won"]
    assert repo_briefing["evidence_strip"][0]["label"] == "Where To Start"


def test_weekly_story_sections_render_across_review_pack_html_and_handoff(tmp_path: Path) -> None:
    report = _report()
    weekly_pack = build_weekly_review_pack(report)

    review_pack = export_review_pack(report, tmp_path)["review_pack_path"].read_text()
    html = _render_html(report)
    handoff = render_scheduled_handoff_markdown(
        {
            "username": report["username"],
            "generated_at": report["generated_at"],
            "operator_summary": report["operator_summary"],
            "operator_queue": report["operator_queue"],
            "operator_recent_changes": [],
            "campaign_summary": {},
            "writeback_preview": {},
            "managed_state_drift": [],
            "issue_candidate": {},
            "weekly_pack": weekly_pack,
        }
    )

    expected_summary = "Governance: all is the strongest approval review candidate right now."
    expected_next = "Review Governance: all next and decide whether to capture approval."

    assert expected_summary in review_pack
    assert expected_next in review_pack
    assert expected_summary in html
    assert expected_next in html
    assert expected_summary in handoff
    assert expected_next in handoff
    assert "Weekly decision:" in handoff


def test_weekly_story_visible_contract_reaches_workbook_html_markdown_and_handoff(tmp_path: Path) -> None:
    report = _report()
    weekly_pack = build_weekly_review_pack(report)
    approval_section = next(
        section for section in weekly_pack["weekly_story_v1"]["sections"] if section["id"] == "approval-workflow"
    )

    wb = Workbook()
    _build_print_pack(wb, report, None, portfolio_profile="default", collection="showcase", excel_mode="standard")
    print_ws = wb["Print Pack"]

    review_pack = export_review_pack(report, tmp_path)["review_pack_path"].read_text()
    html = _render_html(report)
    handoff = render_scheduled_handoff_markdown(
        {
            "username": report["username"],
            "generated_at": report["generated_at"],
            "operator_summary": report["operator_summary"],
            "operator_queue": report["operator_queue"],
            "operator_recent_changes": [],
            "campaign_summary": {},
            "writeback_preview": {},
            "managed_state_drift": [],
            "issue_candidate": {},
            "weekly_pack": weekly_pack,
        }
    )

    assert print_ws["B10"].value == weekly_pack["weekly_story_v1"]["decision"]
    assert print_ws["E21"].value == approval_section["headline"]
    assert print_ws["E22"].value == approval_section["next_step"]
    assert weekly_pack["weekly_story_v1"]["decision"] in review_pack
    assert approval_section["headline"] in review_pack
    assert weekly_pack["weekly_story_v1"]["decision"] in html
    assert approval_section["headline"] in html
    assert weekly_pack["weekly_story_v1"]["decision"] in handoff
    assert approval_section["headline"] in handoff


def test_scheduled_handoff_falls_back_cleanly_when_weekly_story_is_missing() -> None:
    report = _report()
    weekly_pack = build_weekly_review_pack(report)
    legacy_weekly_pack = dict(weekly_pack)
    legacy_weekly_pack.pop("weekly_story_v1", None)

    handoff = render_scheduled_handoff_markdown(
        {
            "username": report["username"],
            "generated_at": report["generated_at"],
            "operator_summary": report["operator_summary"],
            "operator_queue": report["operator_queue"],
            "operator_recent_changes": [],
            "campaign_summary": {},
            "writeback_preview": {},
            "managed_state_drift": [],
            "issue_candidate": {},
            "weekly_pack": legacy_weekly_pack,
        }
    )

    assert "Weekly decision:" in handoff
    assert weekly_pack["what_to_do_this_week"] in handoff
    assert weekly_pack["approval_workflow_summary"] in handoff
    assert weekly_pack["next_approval_review"] in handoff


def test_scheduled_handoff_prefers_shared_weekly_story_fields_before_fallbacks() -> None:
    report = _report()
    weekly_pack = build_weekly_review_pack(report)
    weekly_story = dict(weekly_pack["weekly_story_v1"])
    weekly_story["headline"] = "Shared weekly headline wins."
    weekly_story["decision"] = "Shared weekly decision wins."
    weekly_story["why_this_week"] = "Shared weekly reason wins."
    weekly_story["next_step"] = "Shared weekly next workflow step wins."

    updated_sections = []
    for section in weekly_story["sections"]:
        if section["id"] == "action-sync-readiness":
            updated_sections.append(
                {
                    **section,
                    "headline": "Shared Action Sync section wins.",
                    "next_step": "Shared Action Sync next step wins.",
                }
            )
        else:
            updated_sections.append(section)
    weekly_story["sections"] = updated_sections

    weekly_pack = {
        **weekly_pack,
        "portfolio_headline": "Legacy weekly-pack headline should lose.",
        "what_to_do_this_week": "Legacy weekly-pack decision should lose.",
        "queue_pressure_summary": "Legacy weekly-pack reason should lose.",
        "next_best_workflow_step": "Legacy weekly-pack next step should lose.",
        "action_sync_summary": "Legacy weekly-pack action sync should lose.",
        "next_action_sync_step": "Legacy weekly-pack action sync next step should lose.",
        "weekly_story_v1": weekly_story,
    }

    handoff = render_scheduled_handoff_markdown(
        {
            "username": report["username"],
            "generated_at": report["generated_at"],
            "operator_summary": {
                **report["operator_summary"],
                "headline": "Operator summary headline should lose.",
                "what_to_do_next": "Operator summary next step should lose.",
                "why_it_matters": "Operator summary reason should lose.",
                "action_sync_summary": {"summary": "Operator summary Action Sync should lose."},
                "next_action_sync_step": "Operator summary Action Sync next step should lose.",
            },
            "operator_queue": report["operator_queue"],
            "operator_recent_changes": [],
            "campaign_summary": {},
            "writeback_preview": {},
            "managed_state_drift": [],
            "issue_candidate": {},
            "weekly_pack": weekly_pack,
        }
    )

    assert "Shared weekly headline wins." in handoff
    assert "Shared weekly decision wins." in handoff
    assert "Shared weekly reason wins." in handoff
    assert "Shared weekly next workflow step wins." in handoff
    assert "Shared Action Sync section wins." in handoff
    assert "Shared Action Sync next step wins." in handoff
    assert "Legacy weekly-pack headline should lose." not in handoff
    assert "Operator summary headline should lose." not in handoff
