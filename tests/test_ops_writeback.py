from __future__ import annotations

from src.ops_writeback import (
    build_campaign_bundle,
    build_writeback_preview,
    desired_managed_topics,
    managed_issue_body,
    managed_issue_title,
)


def _report_data() -> dict:
    return {
        "selected_portfolio_profile": "default",
        "audits": [
            {
                "metadata": {
                    "name": "RepoA",
                    "full_name": "user/RepoA",
                    "topics": ["python"],
                },
                "overall_score": 0.8,
                "completeness_tier": "shipped",
                "lenses": {"showcase_value": {"score": 0.8}},
                "security_posture": {"label": "healthy", "score": 0.9},
                "action_candidates": [
                    {
                        "key": "readme",
                        "title": "Upgrade README",
                        "action": "Add stronger framing",
                        "lens": "showcase_value",
                        "effort": "small",
                        "confidence": 0.8,
                        "expected_lens_delta": 0.1,
                        "expected_tier_movement": "Protect current tier",
                        "rationale": "README is thin",
                    }
                ],
            },
            {
                "metadata": {
                    "name": "RepoB",
                    "full_name": "user/RepoB",
                    "topics": [],
                },
                "overall_score": 0.45,
                "completeness_tier": "wip",
                "lenses": {"security_posture": {"score": 0.3}},
                "security_posture": {"label": "critical", "score": 0.3},
                "action_candidates": [],
            },
        ],
        "collections": {
            "showcase": {
                "repos": [{"name": "RepoA", "reason": "Strong showcase"}],
            },
            "secure-now": {
                "repos": [{"name": "RepoB", "reason": "Security debt"}],
            },
            "archive-soon": {
                "repos": [],
            },
        },
        "profiles": {
            "default": {
                "description": "Balanced",
                "lens_weights": {"showcase_value": 1.0},
            }
        },
        "security_governance_preview": [
            {
                "repo": "RepoB",
                "key": "enable-secret-scanning",
                "priority": "high",
                "title": "Enable secret scanning",
                "expected_posture_lift": 0.15,
                "effort": "medium",
                "source": "github",
                "why": "Secret scanning is not enabled",
            }
        ],
        "action_backlog": [
            {
                "repo": "RepoA",
                "key": "readme",
                "title": "Upgrade README",
                "lens": "showcase_value",
                "effort": "small",
                "confidence": 0.8,
                "expected_lens_delta": 0.1,
                "expected_tier_movement": "Protect current tier",
                "rationale": "README is thin",
                "action": "Add stronger framing",
            }
        ],
        "hotspots": [
            {
                "repo": "RepoB",
                "category": "security-debt",
                "severity": 0.8,
                "title": "Security posture needs attention",
                "recommended_action": "Enable secret scanning",
            }
        ],
    }


def test_build_campaign_bundle_uses_stable_actions_and_collection_filter():
    summary, actions = build_campaign_bundle(
        _report_data(),
        campaign_type="promotion-push",
        portfolio_profile="default",
        collection_name="showcase",
        max_actions=10,
        writeback_target="github",
    )

    assert summary["campaign_type"] == "promotion-push"
    assert len(actions) == 1
    assert actions[0]["repo"] == "RepoA"
    assert actions[0]["action_id"].startswith("promotion-push-")
    assert actions[0]["writeback_targets"]["github"]["issue_title"] == managed_issue_title("promotion-push")


def test_security_campaign_builds_expected_preview():
    summary, actions = build_campaign_bundle(
        _report_data(),
        campaign_type="security-review",
        portfolio_profile="default",
        collection_name=None,
        max_actions=10,
        writeback_target="all",
    )
    preview = build_writeback_preview(summary, actions, writeback_target="all", apply=False)
    assert preview["action_count"] == 1
    assert preview["repos"][0]["repo"] == "RepoB"
    assert "ghra-security-high" in preview["repos"][0]["topics"]


def test_managed_topics_and_issue_body_include_expected_markers():
    action = {
        "repo": "RepoA",
        "campaign_type": "showcase-publish",
        "primary_lens": "showcase_value",
        "action_key": "readme",
        "collections": ["showcase"],
        "title": "Upgrade README",
        "priority": "high",
        "effort": "small",
        "expected_lift": 0.1,
        "body": "Add stronger framing",
    }
    topics = desired_managed_topics(action)
    assert "ghra-showcase" in topics
    assert "ghra-call-showcase-publish" in topics

    body = managed_issue_body("RepoA", "showcase-publish", [action])
    assert "ghra-action-bundle:showcase-publish:repoa" in body
    assert "Upgrade README" in body
