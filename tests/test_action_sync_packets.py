from __future__ import annotations

from src.action_sync_packets import build_action_sync_packets_bundle
from src.action_sync_readiness import build_action_sync_readiness_bundle
from src.ops_writeback import build_campaign_bundle


def _report_data(**overrides) -> dict:
    data = {
        "username": "testuser",
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
        "writeback_results": {},
        "rollback_preview": {},
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


def _packet(bundle: dict, campaign_type: str) -> dict:
    return next(
        item for item in bundle["action_sync_packets"] if item["campaign_type"] == campaign_type
    )


def _bundle(report_data: dict, queue: list[dict] | None = None) -> dict:
    queue = queue or []
    readiness = build_action_sync_readiness_bundle(report_data, queue=queue)
    return build_action_sync_packets_bundle(report_data, readiness, readiness["operator_queue"])


def test_packet_is_stay_local_when_campaign_has_no_actions():
    report_data = _report_data(
        security_governance_preview=[],
        action_backlog=[],
        hotspots=[],
        collections={},
    )

    bundle = _bundle(report_data)
    packet = _packet(bundle, "security-review")

    assert packet["execution_state"] == "stay-local"
    assert packet["blocker_types"] == ["no-actions"]
    assert packet["rollback_status"] == "not-applicable"
    assert packet["apply_command"] == ""


def test_packet_is_preview_next_when_campaign_is_preview_ready():
    bundle = _bundle(_report_data())
    packet = _packet(bundle, "security-review")

    assert packet["execution_state"] == "preview-next"
    assert packet["preview_command"] == "audit testuser --campaign security-review --writeback-target all"
    assert packet["apply_command"] == ""


def test_packet_surfaces_automation_eligible_subset():
    report_data = _report_data()
    for audit in report_data["audits"]:
        if audit["metadata"]["name"] == "RepoSecure":
            audit["portfolio_catalog"] = {
                "repo": "RepoSecure",
                "automation_eligible": True,
            }

    bundle = _bundle(report_data)
    packet = _packet(bundle, "security-review")

    assert packet["action_count"] == 1
    assert packet["automation_subset"] == {
        "automation_eligible_repos": ["RepoSecure"],
        "automation_eligible_repo_count": 1,
        "automation_eligible_action_repos": ["RepoSecure"],
        "automation_eligible_action_repo_count": 1,
        "automation_eligible_action_count": 1,
        "non_eligible_action_count": 0,
    }


def test_packet_surfaces_non_eligible_actions_separately():
    report_data = _report_data()
    for audit in report_data["audits"]:
        if audit["metadata"]["name"] == "RepoSecure":
            audit["portfolio_catalog"] = {
                "repo": "RepoSecure",
                "automation_eligible": True,
            }

    bundle = _bundle(report_data)
    packet = _packet(bundle, "promotion-push")

    assert packet["action_count"] == 1
    assert packet["automation_subset"]["automation_eligible_repos"] == ["RepoSecure"]
    assert packet["automation_subset"]["automation_eligible_action_repos"] == []
    assert packet["automation_subset"]["automation_eligible_action_count"] == 0
    assert packet["automation_subset"]["non_eligible_action_count"] == 1


def test_packet_is_review_drift_when_managed_drift_exists():
    bundle = _bundle(
        _report_data(
            managed_state_drift=[
                {
                    "campaign_type": "security-review",
                    "repo_full_name": "user/RepoSecure",
                    "target": "github-project-item",
                    "drift_state": "managed-project-item-missing",
                }
            ]
        )
    )
    packet = _packet(bundle, "security-review")

    assert packet["execution_state"] == "review-drift"
    assert "managed-drift" in packet["blocker_types"]


def test_packet_is_needs_approval_for_governance_or_rollback_gaps():
    governance_bundle = _bundle(
        _report_data(
            governance_summary={"needs_reapproval": True},
            governance_approval={},
        )
    )
    governance_packet = _packet(governance_bundle, "security-review")
    assert governance_packet["execution_state"] == "needs-approval"
    assert "governance-approval" in governance_packet["blocker_types"]

    report_data = _report_data(
        campaign_summary={
            "campaign_type": "security-review",
            "label": "Security Review",
            "action_count": 1,
            "repo_count": 1,
        },
        writeback_results={"mode": "apply"},
    )
    rollback_bundle = _bundle(report_data)
    rollback_packet = _packet(rollback_bundle, "security-review")
    assert rollback_packet["execution_state"] == "needs-approval"
    assert rollback_packet["rollback_status"] == "missing"
    assert "rollback-coverage" in rollback_packet["blocker_types"]


def test_packet_is_ready_to_apply_when_readiness_and_rollback_are_healthy():
    report_data = _report_data(
        campaign_summary={
            "campaign_type": "security-review",
            "label": "Security Review",
            "action_count": 1,
            "repo_count": 1,
        }
    )
    _, actions = build_campaign_bundle(
        report_data,
        campaign_type="security-review",
        portfolio_profile="default",
        collection_name=None,
        max_actions=20,
        writeback_target=None,
    )
    action_id = actions[0]["action_id"]
    report_data["rollback_preview"] = {
        "items": [
            {
                "action_id": action_id,
                "rollback_state": "fully-reversible",
            }
        ]
    }

    bundle = _bundle(report_data)
    packet = _packet(bundle, "security-review")

    assert packet["execution_state"] == "ready-to-apply"
    assert packet["rollback_status"] == "ready"
    assert packet["apply_command"] == "audit testuser --campaign security-review --writeback-target all --writeback-apply"


def test_packet_command_generation_respects_target_and_github_projects_health():
    github_packet = _packet(
        _bundle(
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
            )
        ),
        "security-review",
    )
    assert github_packet["preview_command"] == "audit testuser --campaign security-review --writeback-target github"

    notion_packet = _packet(
        _bundle(
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
            )
        ),
        "security-review",
    )
    assert notion_packet["preview_command"] == "audit testuser --campaign security-review --writeback-target notion"

    all_packet = _packet(_bundle(_report_data()), "security-review")
    assert all_packet["preview_command"] == "audit testuser --campaign security-review --writeback-target all"

    projects_packet = _packet(
        _bundle(
            _report_data(
                writeback_preview={
                    "sync_mode": "reconcile",
                    "github_projects": {"enabled": True, "status": "configured"},
                }
            )
        ),
        "security-review",
    )
    assert "--github-projects" in projects_packet["preview_command"]

    unhealthy_projects_packet = _packet(
        _bundle(
            _report_data(
                writeback_preview={
                    "sync_mode": "reconcile",
                    "github_projects": {"enabled": True, "status": "misconfigured"},
                }
            )
        ),
        "security-review",
    )
    assert "--github-projects" not in unhealthy_projects_packet["preview_command"]


def test_packet_queue_items_gain_apply_handoff_fields():
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

    bundle = _bundle(_report_data(), queue=queue)
    item = bundle["operator_queue"][0]

    assert item["apply_packet_state"] == "preview-next"
    assert item["apply_packet_summary"]
    assert item["apply_packet_command"] == "audit testuser --campaign security-review --writeback-target all"


def test_next_apply_candidate_uses_execution_priority_order():
    report_data = _report_data(
        campaign_summary={
            "campaign_type": "promotion-push",
            "label": "Promotion Push",
            "action_count": 1,
            "repo_count": 1,
        },
        governance_summary={"needs_reapproval": True},
        governance_approval={},
        managed_state_drift=[
            {
                "campaign_type": "archive-sweep",
                "repo_full_name": "user/RepoArchive",
                "target": "github-issue",
                "drift_state": "managed-issue-edited",
            }
        ],
    )

    bundle = _bundle(report_data)

    assert bundle["next_apply_candidate"]["campaign_type"] == "archive-sweep"
    assert bundle["next_apply_candidate"]["execution_state"] == "review-drift"
