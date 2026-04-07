from __future__ import annotations

from src.ops_writeback import (
    apply_github_writeback,
    build_action_runs,
    build_campaign_bundle,
    build_rollback_preview,
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


class _FakeGitHubClient:
    def __init__(self):
        self.topics = {"user/RepoA": ["python"], "user/RepoB": ["ghra-call-security-review"]}
        self.properties = {"user/RepoA": {}, "user/RepoB": {"portfolio_call": "security-review"}}
        self.issues = {
            "user/RepoA": [],
            "user/RepoB": [
                {
                    "number": 7,
                    "title": managed_issue_title("security-review"),
                    "body": "<!-- ghra-action-bundle:security-review:repob -->\nold body",
                    "state": "open",
                    "html_url": "https://github.com/user/RepoB/issues/7",
                }
            ],
        }

    def get_repo_topics(self, owner: str, repo: str) -> dict:
        return {"available": True, "topics": list(self.topics.get(f"{owner}/{repo}", []))}

    def replace_repo_topics(self, owner: str, repo: str, topics: list[str]) -> dict:
        self.topics[f"{owner}/{repo}"] = list(topics)
        return {"ok": True, "topics": list(topics)}

    def get_repo_custom_property_values(self, owner: str, repo: str) -> dict:
        return {"available": True, "values": dict(self.properties.get(f"{owner}/{repo}", {}))}

    def update_repo_custom_property_values(self, owner: str, repo: str, properties: dict[str, str]) -> dict:
        before = dict(self.properties.get(f"{owner}/{repo}", {}))
        after = {**before, **properties}
        self.properties[f"{owner}/{repo}"] = after
        return {"ok": True, "status": "updated", "before": before, "after": after}

    def list_repo_issues(self, owner: str, repo: str, state: str = "open") -> list[dict]:
        return [dict(item) for item in self.issues.get(f"{owner}/{repo}", [])]

    def create_issue(self, owner: str, repo: str, payload: dict) -> dict:
        issue = {
            "number": 11,
            "title": payload["title"],
            "body": payload["body"],
            "state": "open",
            "html_url": f"https://github.com/{owner}/{repo}/issues/11",
        }
        self.issues.setdefault(f"{owner}/{repo}", []).append(issue)
        return {"ok": True, "number": 11, "html_url": issue["html_url"]}

    def update_issue(self, owner: str, repo: str, issue_number: int, payload: dict) -> dict:
        for issue in self.issues.get(f"{owner}/{repo}", []):
            if issue["number"] == issue_number:
                issue.update(payload)
                issue["html_url"] = issue.get("html_url", f"https://github.com/{owner}/{repo}/issues/{issue_number}")
                return {"ok": True, "number": issue_number, "html_url": issue["html_url"]}
        return {"ok": False, "number": issue_number}


def test_apply_github_writeback_reopens_and_detects_drift():
    _, actions = build_campaign_bundle(
        _report_data(),
        campaign_type="security-review",
        max_actions=5,
        writeback_target="github",
    )
    previous_state = {
        "actions": {
            actions[0]["action_id"]: {
                "action_id": actions[0]["action_id"],
                "repo_full_name": actions[0]["repo_full_name"],
                "campaign_type": actions[0]["campaign_type"],
                "lifecycle_state": "resolved",
                "snapshots": {
                    "github-issue": {"external_key": "7"},
                },
            }
        }
    }

    client = _FakeGitHubClient()
    results, refs, drift, _closures = apply_github_writeback(
        client,
        actions,
        previous_state=previous_state,
        sync_mode="reconcile",
    )

    issue_result = next(item for item in results if item["target"] == "github-issue")
    assert issue_result["status"] == "updated"
    assert refs[actions[0]["action_id"]]["github_issue_url"].endswith("/7")
    assert any(item["drift_state"] == "managed-issue-edited" for item in drift)


def test_apply_github_writeback_closes_missing_actions_under_reconcile():
    _, actions = build_campaign_bundle(
        _report_data(),
        campaign_type="promotion-push",
        max_actions=5,
        writeback_target="github",
    )
    previous_state = {
        "actions": {
            "stale-action": {
                "action_id": "stale-action",
                "repo_full_name": "user/RepoB",
                "campaign_type": "security-review",
                "snapshots": {
                    "github-issue": {"external_key": "7"},
                },
            }
        }
    }
    client = _FakeGitHubClient()

    results, _refs, _drift, closures = apply_github_writeback(
        client,
        actions,
        previous_state=previous_state,
        sync_mode="reconcile",
    )

    stale_result = next(item for item in results if item.get("action_id") == "stale-action")
    assert stale_result["status"] == "closed"
    assert any(item["action_id"] == "stale-action" and item["lifecycle_state"] == "resolved" for item in closures)


def test_build_action_runs_marks_stale_actions_in_append_only_mode():
    _, actions = build_campaign_bundle(
        _report_data(),
        campaign_type="promotion-push",
        max_actions=5,
        writeback_target="github",
    )
    previous_state = {
        "actions": {
            "stale-action": {
                "action_id": "stale-action",
                "repo_full_name": "user/RepoB",
                "campaign_type": "security-review",
            }
        }
    }
    results = [{"action_id": "stale-action", "repo_full_name": "user/RepoB", "target": "github-issue", "status": "stale"}]

    action_runs = build_action_runs(
        actions,
        results,
        "github",
        True,
        previous_state=previous_state,
        sync_mode="append-only",
    )

    stale_run = next(item for item in action_runs if item["action_id"] == "stale-action")
    assert stale_run["lifecycle_state"] == "deferred"
    assert stale_run["reconciliation_outcome"] == "stale"


def test_build_rollback_preview_reports_reversibility():
    preview = build_rollback_preview(
        [
            {"repo_full_name": "user/RepoA", "target": "github-issue", "status": "updated", "before": {"state": "open"}},
            {"repo_full_name": "user/RepoA", "target": "github-topics", "status": "updated", "before": []},
        ]
    )

    assert preview["available"] is True
    assert preview["item_count"] == 2
