from __future__ import annotations

from src.action_sync_readiness import build_action_sync_readiness_bundle


def _report_data(**overrides) -> dict:
    data = {
        "selected_portfolio_profile": "default",
        "selected_collection": None,
        "preflight_summary": {"checks": []},
        "governance_summary": {},
        "governance_preview": {},
        "governance_approval": {"approved": True},
        "governance_drift": [],
        "managed_state_drift": [],
        "campaign_summary": {},
        "writeback_preview": {"sync_mode": "reconcile"},
        "collections": {
            "showcase": {"repos": [{"name": "RepoShow"}]},
            "archive-soon": {"repos": [{"name": "RepoArchive"}]},
        },
        "security_governance_preview": [
            {
                "repo": "RepoSecure",
                "key": "enable-secret-scanning",
                "title": "Enable secret scanning",
                "priority": "high",
                "expected_posture_lift": 0.2,
                "effort": "medium",
                "source": "github",
                "why": "Secret scanning is not enabled.",
            }
        ],
        "action_backlog": [
            {
                "repo": "RepoPromo",
                "key": "ship-readiness",
                "title": "Finish release path",
                "lens": "ship_readiness",
                "effort": "medium",
                "confidence": 0.9,
                "expected_lens_delta": 0.15,
                "expected_tier_movement": "Promote to functional",
                "rationale": "The repo is close to a higher tier.",
                "action": "Finish the release path.",
            }
        ],
        "hotspots": [
            {
                "repo": "RepoMaint",
                "category": "fragile-maintenance",
                "severity": 0.8,
                "title": "Maintenance cleanup needed",
                "recommended_action": "Resolve the fragile maintenance hotspot.",
            }
        ],
        "audits": [
            {
                "metadata": {"name": "RepoSecure", "full_name": "user/RepoSecure", "topics": []},
                "overall_score": 0.42,
                "completeness_tier": "wip",
                "lenses": {"security_posture": {"score": 0.3}},
                "security_posture": {"label": "critical", "score": 0.3},
                "action_candidates": [],
                "portfolio_catalog": {},
            },
            {
                "metadata": {"name": "RepoPromo", "full_name": "user/RepoPromo", "topics": []},
                "overall_score": 0.58,
                "completeness_tier": "functional",
                "lenses": {"ship_readiness": {"score": 0.6}},
                "security_posture": {"label": "healthy", "score": 0.8},
                "action_candidates": [],
                "portfolio_catalog": {},
            },
            {
                "metadata": {"name": "RepoMaint", "full_name": "user/RepoMaint", "topics": []},
                "overall_score": 0.51,
                "completeness_tier": "functional",
                "lenses": {"maintenance_risk": {"score": 0.4}},
                "security_posture": {"label": "watch", "score": 0.55},
                "action_candidates": [],
                "portfolio_catalog": {},
            },
            {
                "metadata": {"name": "RepoShow", "full_name": "user/RepoShow", "topics": []},
                "overall_score": 0.81,
                "completeness_tier": "shipped",
                "lenses": {"showcase_value": {"score": 0.85}},
                "security_posture": {"label": "healthy", "score": 0.9},
                "action_candidates": [{"key": "readme", "action": "Polish README"}],
                "portfolio_catalog": {},
            },
            {
                "metadata": {"name": "RepoArchive", "full_name": "user/RepoArchive", "topics": []},
                "overall_score": 0.12,
                "completeness_tier": "skeleton",
                "lenses": {"maintenance_risk": {"score": 0.15}},
                "security_posture": {"label": "watch", "score": 0.45},
                "action_candidates": [],
                "portfolio_catalog": {"intended_disposition": "archive"},
            },
        ],
    }
    data.update(overrides)
    return data


def _campaign(bundle: dict, campaign_type: str) -> dict:
    return next(
        item
        for item in bundle["campaign_readiness_summary"]["campaigns"]
        if item["campaign_type"] == campaign_type
    )


def test_preview_ready_and_apply_ready_are_distinguished():
    preview_bundle = build_action_sync_readiness_bundle(_report_data(), queue=[])
    assert _campaign(preview_bundle, "security-review")["readiness_stage"] == "preview-ready"

    apply_bundle = build_action_sync_readiness_bundle(
        _report_data(
            campaign_summary={
                "campaign_type": "security-review",
                "label": "Security Review",
                "action_count": 1,
                "repo_count": 1,
            }
        ),
        queue=[],
    )
    assert _campaign(apply_bundle, "security-review")["readiness_stage"] == "apply-ready"


def test_drift_review_beats_apply_ready():
    bundle = build_action_sync_readiness_bundle(
        _report_data(
            campaign_summary={
                "campaign_type": "security-review",
                "label": "Security Review",
                "action_count": 1,
                "repo_count": 1,
            },
            managed_state_drift=[
                {
                    "campaign_type": "security-review",
                    "repo_full_name": "user/RepoSecure",
                    "target": "github-project-item",
                    "drift_state": "managed-project-item-missing",
                }
            ],
        ),
        queue=[],
    )

    assert _campaign(bundle, "security-review")["readiness_stage"] == "drift-review"
    assert bundle["next_action_sync_step"].startswith("Review managed drift")


def test_blocked_when_governance_or_targets_are_not_ready():
    bundle = build_action_sync_readiness_bundle(
        _report_data(
            governance_summary={"needs_reapproval": True},
            governance_approval={},
        ),
        queue=[],
    )
    security = _campaign(bundle, "security-review")
    assert security["readiness_stage"] == "blocked"
    assert "approval" in security["reason"].lower()


def test_recommended_target_uses_all_then_github_then_notion_then_none():
    assert _campaign(build_action_sync_readiness_bundle(_report_data(), queue=[]), "security-review")[
        "recommended_target"
    ] == "all"
    assert _campaign(
        build_action_sync_readiness_bundle(
            _report_data(
                preflight_summary={
                    "checks": [
                        {
                            "status": "error",
                            "category": "notion-auth",
                            "summary": "Notion token missing.",
                        }
                    ]
                }
            ),
            queue=[],
        ),
        "security-review",
    )["recommended_target"] == "github"
    assert _campaign(
        build_action_sync_readiness_bundle(
            _report_data(
                preflight_summary={
                    "checks": [
                        {
                            "status": "error",
                            "category": "github-auth",
                            "summary": "GitHub token missing.",
                        }
                    ]
                }
            ),
            queue=[],
        ),
        "security-review",
    )["recommended_target"] == "notion"
    assert _campaign(
        build_action_sync_readiness_bundle(
            _report_data(
                preflight_summary={
                    "checks": [
                        {"status": "error", "category": "github-auth", "summary": "GitHub token missing."},
                        {"status": "error", "category": "notion-auth", "summary": "Notion token missing."},
                    ]
                }
            ),
            queue=[],
        ),
        "security-review",
    )["recommended_target"] == "none"


def test_queue_items_gain_action_sync_handoff_fields():
    queue = [
        {
            "repo": "RepoSecure",
            "kind": "governance",
            "title": "RepoSecure drift needs review",
            "summary": "Secret scanning drift is active.",
            "recommended_action": "Review the governed control before syncing outward.",
            "operator_focus": "act-now",
        }
    ]

    bundle = build_action_sync_readiness_bundle(_report_data(), queue=queue)
    item = bundle["operator_queue"][0]

    assert item["suggested_campaign"] == "security-review"
    assert item["action_sync_stage"] == "preview-ready"
    assert item["suggested_writeback_target"] == "all"
    assert "Action Sync:" in item["action_sync_line"]
