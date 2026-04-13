from __future__ import annotations

from src.review_pack import export_review_pack


def _make_report() -> dict:
    return {
        "username": "testuser",
        "generated_at": "2026-04-12T10:00:00+00:00",
        "repos_audited": 1,
        "average_score": 0.62,
        "portfolio_grade": "C",
        "tier_distribution": {"functional": 1},
        "collections": {"showcase": {"description": "Best examples", "repos": [{"name": "RepoC", "reason": "Operator focus"}]}},
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
        "scenario_summary": {"top_levers": [], "portfolio_projection": {}},
        "portfolio_catalog_summary": {"summary": "1/1 repos have an explicit catalog contract."},
        "intent_alignment_summary": {"summary": "1 aligned, 0 needing review, and 0 missing a contract."},
        "scorecards_summary": {"summary": "0 repos are on track, 1 is below target, and 0 are missing a valid program."},
        "implementation_hotspots_summary": {"summary": "1 repos have concrete implementation pressure. Start with RepoC in file src/core.py."},
        "audits": [
            {
                "metadata": {
                    "name": "RepoC",
                    "full_name": "user/RepoC",
                    "description": "Phase 78 test repo",
                    "language": "Python",
                    "html_url": "https://github.com/user/RepoC",
                },
                "overall_score": 0.62,
                "interest_score": 0.3,
                "grade": "C",
                "completeness_tier": "functional",
                "badges": [],
                "flags": [],
                "lenses": {
                    "ship_readiness": {"score": 0.62, "orientation": "higher-is-better", "summary": "Ready enough", "drivers": []},
                    "showcase_value": {"score": 0.58, "orientation": "higher-is-better", "summary": "Good story", "drivers": []},
                    "security_posture": {"score": 0.55, "orientation": "higher-is-better", "summary": "Watch", "drivers": []},
                    "momentum": {"score": 0.52, "orientation": "higher-is-better", "summary": "Holding", "drivers": []},
                    "portfolio_fit": {"score": 0.64, "orientation": "higher-is-better", "summary": "Fits", "drivers": []},
                },
                "security_posture": {"label": "watch", "score": 0.55},
                "action_candidates": [{"title": "Recheck restored evidence"}],
                "hotspots": [{"title": "Restored confidence still needs confirmation"}],
                "implementation_hotspots": [
                    {
                        "scope": "file",
                        "path": "src/core.py",
                        "module": "src",
                        "category": "code-complexity",
                        "pressure_score": 0.74,
                        "suggestion_type": "refactor",
                        "why_it_matters": "src/core.py is carrying concentrated complexity.",
                        "suggested_first_move": "Split the biggest function and add one regression test.",
                        "signal_summary": "Complexity pressure 0.74 across 2 complex blocks.",
                    }
                ],
                "portfolio_catalog": {
                    "has_explicit_entry": True,
                    "owner": "d",
                    "team": "operator-loop",
                    "purpose": "flagship workbook-first flow",
                    "lifecycle_state": "active",
                    "criticality": "high",
                    "review_cadence": "weekly",
                    "intended_disposition": "maintain",
                    "catalog_line": "operator-loop | flagship workbook-first flow | lifecycle active | criticality high | cadence weekly | disposition maintain",
                    "intent_alignment": "aligned",
                    "intent_alignment_reason": "The repo is holding a maintain posture without urgent or revalidation pressure.",
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
                "analyzer_results": [],
            }
        ],
        "operator_summary": {
            "headline": "Restored confidence is coming back after revalidation.",
            "counts": {"blocked": 0, "urgent": 1, "ready": 0, "deferred": 0},
            "action_sync_summary": {
                "summary": "Action Sync is preview-ready: Security Review is the strongest next campaign to preview from the current local facts.",
            },
            "next_action_sync_step": "Preview Security Review next, then decide whether it is ready to sync to all.",
            "apply_readiness_summary": {
                "summary": "Apply handoff says preview Security Review next before deciding on apply to all."
            },
            "next_apply_candidate": {
                "summary": "Preview Security Review next, then decide whether it is ready to apply to all.",
                "preview_command": "audit user --campaign security-review --writeback-target all",
            },
            "top_preview_ready_campaigns": [
                {
                    "label": "Security Review",
                    "reason": "1 action is ready for preview.",
                    "recommended_target": "all",
                }
            ],
            "top_ready_to_apply_packets": [],
            "top_needs_approval_packets": [],
            "top_review_drift_packets": [],
            "follow_through_reacquisition_revalidation_recovery_summary": "1 restored-confidence path has only just been re-earned and still needs another confirming run.",
            "top_just_reearned_confidence_items": [
                {"repo": "RepoC", "title": "RepoC drift needs review"}
            ],
        },
        "operator_queue": [
            {
                "repo": "RepoC",
                "title": "RepoC drift needs review",
                "lane": "urgent",
                "lane_label": "Urgent",
                "lane_reason": "Restored confidence is back, but still fragile after revalidation.",
                "recommended_action": "Wait for one more confirming run before retiring caution.",
                "follow_through_status": "waiting-on-evidence",
                "follow_through_summary": "RepoC has recent follow-up recorded and is now waiting for confirming evidence.",
                "follow_through_checkpoint": "Use the next run to confirm the rebuilt posture is still holding.",
                "follow_through_checkpoint_status": "due-soon",
                "follow_through_escalation_status": "none",
                "follow_through_escalation_summary": "No stronger follow-through escalation is currently surfaced.",
                "follow_through_recovery_status": "recovering",
                "follow_through_recovery_summary": "RepoC is recovering from recent escalation, but it still needs another calmer run before the stronger resurfacing retires.",
                "follow_through_recovery_reacquisition_status": "reacquired",
                "follow_through_recovery_reacquisition_summary": "RepoC has rebuilt the calmer posture after reset.",
                "follow_through_recovery_reacquisition_durability_status": "durable-reacquired",
                "follow_through_recovery_reacquisition_durability_summary": "RepoC has held the restored posture long enough to treat it as durable again.",
                "follow_through_recovery_reacquisition_consolidation_status": "holding-confidence",
                "follow_through_recovery_reacquisition_consolidation_summary": "RepoC has started holding restored confidence again.",
                "follow_through_reacquisition_softening_decay_status": "none",
                "follow_through_reacquisition_softening_decay_summary": "No reacquisition softening-decay signal is currently surfaced.",
                "follow_through_reacquisition_confidence_retirement_status": "none",
                "follow_through_reacquisition_confidence_retirement_summary": "No reacquisition confidence-retirement signal is currently surfaced.",
                "follow_through_reacquisition_revalidation_recovery_status": "just-reearned-confidence",
                "follow_through_reacquisition_revalidation_recovery_summary": "RepoC has only just re-earned restored confidence after revalidation.",
                "catalog_line": "operator-loop | flagship workbook-first flow | lifecycle active | criticality high | cadence weekly | disposition maintain",
                "intent_alignment": "aligned",
                "intent_alignment_reason": "The repo is holding a maintain posture without urgent or revalidation pressure.",
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
                "apply_packet_line": "Apply Packet: Security Review is the best campaign to preview next before deciding on apply to all. Command: audit user --campaign security-review --writeback-target all",
            }
        ],
    }


def test_review_pack_includes_revalidation_recovery_section(tmp_path):
    path = export_review_pack(_make_report(), tmp_path)["review_pack_path"]
    content = path.read_text()

    assert "Product Mode:" in content
    assert "Artifact Role:" in content
    assert "Suggested Reading Order:" in content
    assert "Next Best Workflow Step:" in content
    assert "### Operator Focus" in content
    assert "Operator Focus:" in content
    assert "Act Now" in content
    assert "Portfolio Catalog: 1/1 repos have an explicit catalog contract." in content
    assert "Intent Alignment: 1 aligned, 0 needing review, and 0 missing a contract." in content
    assert "Scorecards: 0 repos are on track, 1 is below target" in content
    assert "Implementation Hotspots: 1 repos have concrete implementation pressure." in content
    assert "Operator Outcomes:" in content
    assert "Operator Effectiveness:" in content
    assert "High-Pressure Queue Trend:" in content
    assert "Action Sync Readiness:" in content
    assert "Apply Packet:" in content
    assert "Next Apply Candidate:" in content
    assert "Action Sync Command Hint:" in content
    assert "Preview Ready" in content
    assert "Catalog: operator-loop | flagship workbook-first flow" in content
    assert "Where To Start: Start in src/core.py." in content
    assert "Intent Alignment: aligned: The repo is holding a maintain posture" in content
    assert "Scorecard: Maintain — Operating (target Strong)" in content
    assert "Maturity Gap: testing, ci are still below the maintain bar." in content
    assert "Action Sync: Security Review is preview-ready — recommended target all." in content
    assert "Follow-Through Revalidation Recovery and Confidence Re-Earning" not in content


def test_review_pack_includes_github_projects_campaign_context(tmp_path):
    report = _make_report()
    report["campaign_summary"] = {
        "campaign_type": "security-review",
        "label": "Security Review",
        "action_count": 1,
        "repo_count": 1,
    }
    report["writeback_preview"] = {
        "sync_mode": "reconcile",
        "github_projects": {
            "enabled": True,
            "status": "configured",
            "project_owner": "octo-org",
            "project_number": 7,
            "item_count": 1,
        },
        "repos": [
            {
                "repo": "RepoC",
                "issue_title": "[Repo Auditor] Security Review",
                "topics": ["ghra-call-security-review"],
                "github_project_field_count": 3,
                "notion_action_count": 1,
            }
        ],
    }

    path = export_review_pack(report, tmp_path)["review_pack_path"]
    content = path.read_text()

    assert "GitHub Projects: configured (octo-org #7, 1 items)" in content
    assert "RepoC: [Repo Auditor] Security Review | 3 project fields | 1 managed topics | 1 Notion actions" in content
