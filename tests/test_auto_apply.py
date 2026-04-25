"""Tests for src/auto_apply — trust bar gating and action filtering."""

from __future__ import annotations

from src.auto_apply import (
    SAFE_MUTATION_TARGETS,
    build_trust_bar_index,
    filter_safe_actions,
    filter_trusted_repo_actions,
    get_approved_manual_campaigns,
    summarize_trust_bar,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _project(
    name: str,
    *,
    automation_eligible: bool = False,
    risk_tier: str = "baseline",
) -> dict:
    return {
        "identity": {"display_name": name},
        "declared": {"automation_eligible": automation_eligible},
        "risk": {"risk_tier": risk_tier},
    }


def _action(repo: str, mutation_target: str = "github-topics") -> dict:
    return {"repo": repo, "mutation_target": mutation_target}


def _ledger_record(campaign_type: str, state: str = "approved-manual") -> dict:
    return {
        "approval_id": f"campaign:{campaign_type}",
        "approval_subject_type": "campaign",
        "subject_key": campaign_type,
        "approval_state": state,
    }


# ---------------------------------------------------------------------------
# build_trust_bar_index
# ---------------------------------------------------------------------------


def test_trust_bar_index_trusted_portfolio_eligible_baseline_passes():
    snapshot = {"projects": [_project("Alpha", automation_eligible=True, risk_tier="baseline")]}
    index = build_trust_bar_index(snapshot, "trusted")
    assert index["Alpha"] is True


def test_trust_bar_index_not_automation_eligible_fails():
    snapshot = {"projects": [_project("Beta", automation_eligible=False, risk_tier="baseline")]}
    index = build_trust_bar_index(snapshot, "trusted")
    assert index["Beta"] is False


def test_trust_bar_index_elevated_risk_fails():
    snapshot = {"projects": [_project("Gamma", automation_eligible=True, risk_tier="elevated")]}
    index = build_trust_bar_index(snapshot, "trusted")
    assert index["Gamma"] is False


def test_trust_bar_index_portfolio_not_trusted_all_fail():
    snapshot = {
        "projects": [
            _project("Alpha", automation_eligible=True, risk_tier="baseline"),
            _project("Beta", automation_eligible=True, risk_tier="baseline"),
        ]
    }
    # Portfolio-level gate: not trusted → all repos fail
    index = build_trust_bar_index(snapshot, "use-with-review")
    assert index["Alpha"] is False
    assert index["Beta"] is False


def test_trust_bar_index_empty_snapshot():
    index = build_trust_bar_index({}, "trusted")
    assert index == {}


def test_trust_bar_index_skips_projects_without_display_name():
    snapshot = {"projects": [{"identity": {}, "declared": {}, "risk": {}}]}
    index = build_trust_bar_index(snapshot, "trusted")
    assert index == {}


# ---------------------------------------------------------------------------
# summarize_trust_bar
# ---------------------------------------------------------------------------


def test_summarize_trust_bar_surfaces_opt_in_baseline_and_trusted_repos():
    snapshot = {
        "projects": [
            _project("Alpha", automation_eligible=True, risk_tier="baseline"),
            _project("Beta", automation_eligible=True, risk_tier="elevated"),
            _project("Gamma", automation_eligible=False, risk_tier="baseline"),
        ]
    }

    summary = summarize_trust_bar(snapshot, "trusted")

    assert summary["decision_quality_status"] == "trusted"
    assert summary["automation_eligible_count"] == 2
    assert summary["automation_eligible_repos"] == ["Alpha", "Beta"]
    assert summary["baseline_eligible_count"] == 1
    assert summary["baseline_eligible_repos"] == ["Alpha"]
    assert summary["trusted_repo_count"] == 1
    assert summary["trusted_repos"] == ["Alpha"]


def test_summarize_trust_bar_keeps_opt_in_counts_when_portfolio_not_trusted():
    snapshot = {
        "projects": [
            _project("Alpha", automation_eligible=True, risk_tier="baseline"),
        ]
    }

    summary = summarize_trust_bar(snapshot, "")

    assert summary["decision_quality_status"] == "unknown"
    assert summary["automation_eligible_repos"] == ["Alpha"]
    assert summary["baseline_eligible_repos"] == ["Alpha"]
    assert summary["trusted_repos"] == []


# ---------------------------------------------------------------------------
# get_approved_manual_campaigns
# ---------------------------------------------------------------------------


def test_get_approved_manual_campaigns_returns_approved_only():
    bundle = {
        "approval_ledger": [
            _ledger_record("github-topics", "approved-manual"),
            _ledger_record("github-custom-properties", "ready-for-review"),
            _ledger_record("github-issue", "blocked"),
        ]
    }
    result = get_approved_manual_campaigns(bundle)
    assert len(result) == 1
    assert result[0]["subject_key"] == "github-topics"


def test_get_approved_manual_campaigns_excludes_governance_type():
    bundle = {
        "approval_ledger": [
            {
                "approval_id": "governance:topics",
                "approval_subject_type": "governance",
                "subject_key": "topics",
                "approval_state": "approved-manual",
            },
            _ledger_record("github-topics", "approved-manual"),
        ]
    }
    result = get_approved_manual_campaigns(bundle)
    assert len(result) == 1
    assert result[0]["subject_key"] == "github-topics"


def test_get_approved_manual_campaigns_empty_ledger():
    assert get_approved_manual_campaigns({}) == []
    assert get_approved_manual_campaigns({"approval_ledger": []}) == []


# ---------------------------------------------------------------------------
# filter_safe_actions
# ---------------------------------------------------------------------------


def test_filter_safe_actions_keeps_safe_targets():
    actions = [_action("repo1", t) for t in SAFE_MUTATION_TARGETS]
    assert filter_safe_actions(actions) == actions


def test_filter_safe_actions_excludes_unsafe_targets():
    unsafe = [
        _action("repo1", "github-project-item"),
        _action("repo1", "github-project-fields"),
    ]
    assert filter_safe_actions(unsafe) == []


def test_filter_safe_actions_mixed():
    actions = [
        _action("repo1", "github-topics"),
        _action("repo1", "github-project-item"),
        _action("repo1", "github-custom-properties"),
    ]
    result = filter_safe_actions(actions)
    targets = {a["mutation_target"] for a in result}
    assert "github-project-item" not in targets
    assert "github-topics" in targets
    assert "github-custom-properties" in targets


def test_filter_safe_actions_infers_safe_github_writeback_targets():
    actions = [
        {
            "repo": "Alpha",
            "writeback_targets": {
                "github": {
                    "managed_topics": ["ghra-call-promotion-push"],
                    "issue_title": "[Repo Auditor] Promotion Push",
                }
            },
        }
    ]

    assert filter_safe_actions(actions) == actions


def test_filter_safe_actions_excludes_actions_without_known_targets():
    actions = [{"repo": "Alpha", "writeback_targets": {}}]

    assert filter_safe_actions(actions) == []


def test_filter_safe_actions_empty():
    assert filter_safe_actions([]) == []


# ---------------------------------------------------------------------------
# filter_trusted_repo_actions
# ---------------------------------------------------------------------------


def test_filter_trusted_repo_actions_passes_trusted_repos():
    trust_bar = {"Alpha": True, "Beta": False}
    actions = [_action("Alpha"), _action("Beta")]
    result = filter_trusted_repo_actions(actions, trust_bar)
    assert len(result) == 1
    assert result[0]["repo"] == "Alpha"


def test_filter_trusted_repo_actions_unknown_repo_excluded():
    trust_bar = {"Alpha": True}
    actions = [_action("Alpha"), _action("Unknown")]
    result = filter_trusted_repo_actions(actions, trust_bar)
    assert len(result) == 1
    assert result[0]["repo"] == "Alpha"


def test_filter_trusted_repo_actions_no_repo_field_excluded():
    trust_bar = {"Alpha": True}
    actions = [{"mutation_target": "github-topics"}, _action("Alpha")]
    result = filter_trusted_repo_actions(actions, trust_bar)
    assert len(result) == 1


def test_filter_trusted_repo_actions_all_excluded():
    trust_bar = {"Alpha": False}
    assert filter_trusted_repo_actions([_action("Alpha")], trust_bar) == []
