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


# ---------------------------------------------------------------------------
# SAFE_MUTATION_TARGETS constant coverage
# ---------------------------------------------------------------------------


def test_safe_mutation_targets_contains_notion_action():
    # Kill mutant that removes/renames "notion-action" from the frozenset
    assert "notion-action" in SAFE_MUTATION_TARGETS


def test_safe_mutation_targets_exact_members():
    assert SAFE_MUTATION_TARGETS == frozenset(
        {"github-topics", "github-custom-properties", "github-issue", "notion-action"}
    )


# ---------------------------------------------------------------------------
# build_trust_bar_index — edge cases for defaults and break/continue
# ---------------------------------------------------------------------------


def test_trust_bar_index_continue_skips_only_empty_name():
    # Kills continue→break mutation: a project with no display_name should skip,
    # NOT stop the loop — the next project with a valid name should still be processed.
    snapshot = {
        "projects": [
            {"identity": {}, "declared": {}, "risk": {}},  # no display_name
            _project("Alpha", automation_eligible=True, risk_tier="baseline"),
        ]
    }
    index = build_trust_bar_index(snapshot, "trusted")
    assert "Alpha" in index
    assert index["Alpha"] is True


def test_trust_bar_index_missing_declared_key_defaults_to_not_eligible():
    # Kills False→True default mutation for automation_eligible
    snapshot = {
        "projects": [
            {
                "identity": {"display_name": "Alpha"},
                "risk": {"risk_tier": "baseline"},
                # No "declared" key at all
            }
        ]
    }
    index = build_trust_bar_index(snapshot, "trusted")
    assert index["Alpha"] is False


def test_trust_bar_index_none_declared_defaults_to_not_eligible():
    snapshot = {
        "projects": [
            {
                "identity": {"display_name": "Alpha"},
                "declared": None,
                "risk": {"risk_tier": "baseline"},
            }
        ]
    }
    index = build_trust_bar_index(snapshot, "trusted")
    assert index["Alpha"] is False


def test_trust_bar_index_none_risk_tier_defaults_to_elevated():
    # Kills "XXelevatedXX" fallback mutation for risk_tier
    snapshot = {
        "projects": [
            {
                "identity": {"display_name": "Alpha"},
                "declared": {"automation_eligible": True},
                "risk": {"risk_tier": None},
            }
        ]
    }
    index = build_trust_bar_index(snapshot, "trusted")
    assert index["Alpha"] is False  # None risk_tier → elevated → fails


def test_trust_bar_index_missing_risk_tier_defaults_to_elevated():
    snapshot = {
        "projects": [
            {
                "identity": {"display_name": "Alpha"},
                "declared": {"automation_eligible": True},
                "risk": {},
            }
        ]
    }
    index = build_trust_bar_index(snapshot, "trusted")
    assert index["Alpha"] is False


def test_trust_bar_index_display_name_none_or_string():
    # Kills "XXXX" default/fallback mutation for display_name
    snapshot = {
        "projects": [
            {
                "identity": {"display_name": None},  # None display_name → coerced to ""
                "declared": {"automation_eligible": True},
                "risk": {"risk_tier": "baseline"},
            }
        ]
    }
    index = build_trust_bar_index(snapshot, "trusted")
    # None→str("")→empty→skipped
    assert index == {}


# ---------------------------------------------------------------------------
# summarize_trust_bar — edge cases for defaults and continue/break
# ---------------------------------------------------------------------------


def test_summarize_trust_bar_continue_skips_only_nameless():
    # Kills continue→break: project without display_name should not stop the loop
    snapshot = {
        "projects": [
            {"identity": {}, "declared": {}, "risk": {}},  # nameless, skip
            _project("Alpha", automation_eligible=True, risk_tier="baseline"),
        ]
    }
    summary = summarize_trust_bar(snapshot, "trusted")
    assert "Alpha" in summary["automation_eligible_repos"]
    assert "Alpha" in summary["trusted_repos"]


def test_summarize_trust_bar_missing_declared_key():
    # Kills False→True default mutation in summarize
    snapshot = {
        "projects": [
            {
                "identity": {"display_name": "Alpha"},
                "risk": {"risk_tier": "baseline"},
            }
        ]
    }
    summary = summarize_trust_bar(snapshot, "trusted")
    assert summary["automation_eligible_count"] == 0


def test_summarize_trust_bar_risk_tier_none_fallback():
    # Kills "XXelevatedXX" fallback mutation in summarize
    snapshot = {
        "projects": [
            {
                "identity": {"display_name": "Alpha"},
                "declared": {"automation_eligible": True},
                "risk": {"risk_tier": None},
            }
        ]
    }
    summary = summarize_trust_bar(snapshot, "trusted")
    assert summary["baseline_eligible_count"] == 0


def test_summarize_trust_bar_index_default_false():
    # Kills index.get(repo_name, True) mutation in summarize trusted_repos
    snapshot = {
        "projects": [
            _project("Alpha", automation_eligible=True, risk_tier="elevated"),
        ]
    }
    summary = summarize_trust_bar(snapshot, "trusted")
    # Alpha is eligible but elevated risk → should NOT be in trusted_repos
    assert "Alpha" not in summary["trusted_repos"]


# ---------------------------------------------------------------------------
# get_approved_manual_campaigns — None-fallback coverage
# ---------------------------------------------------------------------------


def test_get_approved_manual_campaigns_handles_none_approval_state():
    # Kills "XXXX" fallback mutation for approval_state
    bundle = {
        "approval_ledger": [
            {
                "approval_id": "campaign:topics",
                "approval_subject_type": "campaign",
                "subject_key": "topics",
                "approval_state": None,
            },
            _ledger_record("github-topics", "approved-manual"),
        ]
    }
    result = get_approved_manual_campaigns(bundle)
    assert len(result) == 1


def test_get_approved_manual_campaigns_handles_none_subject_type():
    # Kills "XXXX" fallback mutation for approval_subject_type
    bundle = {
        "approval_ledger": [
            {
                "approval_id": "campaign:topics",
                "approval_subject_type": None,
                "subject_key": "topics",
                "approval_state": "approved-manual",
            },
            _ledger_record("github-topics", "approved-manual"),
        ]
    }
    result = get_approved_manual_campaigns(bundle)
    assert len(result) == 1


# ---------------------------------------------------------------------------
# _action_mutation_targets — string key coverage
# ---------------------------------------------------------------------------


def test_filter_safe_actions_infers_github_topics_from_key():
    # Kills "XXmanaged_topicsXX" key mutation
    action = {
        "repo": "Alpha",
        "writeback_targets": {"github": {"managed_topics": ["tag1"]}},
    }
    assert filter_safe_actions([action]) == [action]


def test_filter_safe_actions_infers_github_issue_from_issue_title():
    # Kills "XXissue_titleXX" key mutation
    action = {
        "repo": "Alpha",
        "writeback_targets": {"github": {"issue_title": "Some issue"}},
    }
    assert filter_safe_actions([action]) == [action]


def test_filter_safe_actions_infers_notion_action():
    # Kills "XXnotionXX" key mutation and "XXnotion-actionXX" value mutation
    action = {
        "repo": "Alpha",
        "writeback_targets": {"notion": {"some": "payload"}},
    }
    assert filter_safe_actions([action]) == [action]


def test_filter_safe_actions_notion_writeback_and_github_not_in_unsafe():
    # notion-action must be in SAFE_MUTATION_TARGETS for this to pass
    action = {
        "repo": "Alpha",
        "writeback_targets": {"notion": {"x": 1}},
    }
    result = filter_safe_actions([action])
    assert len(result) == 1


# ---------------------------------------------------------------------------
# filter_trusted_repo_actions — fallback repo key
# ---------------------------------------------------------------------------


def test_filter_trusted_repo_actions_none_repo_field():
    # Kills "XXXX" fallback mutation for repo field in filter_trusted_repo_actions
    trust_bar = {"": False}
    action_no_repo = {"mutation_target": "github-topics"}  # no repo key
    result = filter_trusted_repo_actions([action_no_repo], trust_bar)
    assert result == []


def test_filter_trusted_repo_actions_repo_key_fallback_empty_string():
    # Kills "XXXX" repo fallback — empty string maps to missing entry → excluded
    trust_bar = {"Alpha": True}
    action_none_repo = {"repo": None, "mutation_target": "github-topics"}
    result = filter_trusted_repo_actions([action_none_repo], trust_bar)
    assert result == []


# ---------------------------------------------------------------------------
# build_trust_bar_index — risk_tier fallback chains
# ---------------------------------------------------------------------------


def test_trust_bar_index_missing_risk_key_has_no_baseline_chance():
    # Kills "XXelevatedXX" fallback for the default param (project has risk key but no risk_tier)
    # dict.get("risk_tier", "elevated") → "elevated" because missing → not "baseline"
    snapshot = {
        "projects": [
            {
                "identity": {"display_name": "Alpha"},
                "declared": {"automation_eligible": True},
                "risk": {},  # risk key exists, risk_tier key missing
            }
        ]
    }
    index = build_trust_bar_index(snapshot, "trusted")
    # Must be False because no risk_tier → defaults to "elevated" → fails
    assert index["Alpha"] is False


def test_trust_bar_index_risk_none_fallback_chain():
    # Kills the second "elevated" fallback: (project.get("risk") or {}).get("risk_tier", "elevated") or "elevated"
    # When risk is {} and risk_tier is None: str(None or "elevated") == "elevated"
    snapshot = {
        "projects": [
            {
                "identity": {"display_name": "Alpha"},
                "declared": {"automation_eligible": True},
                "risk": {"risk_tier": None},
            }
        ]
    }
    index = build_trust_bar_index(snapshot, "trusted")
    assert index["Alpha"] is False  # None → fallback "elevated" → not baseline


# ---------------------------------------------------------------------------
# summarize_trust_bar — risk_tier None fallback
# ---------------------------------------------------------------------------


def test_summarize_trust_bar_risk_none_not_in_baseline():
    # Kills "XXelevatedXX" in the summarize baseline branch
    snapshot = {
        "projects": [
            {
                "identity": {"display_name": "Alpha"},
                "declared": {"automation_eligible": True},
                "risk": {"risk_tier": None},
            }
        ]
    }
    summary = summarize_trust_bar(snapshot, "trusted")
    assert "Alpha" not in summary["baseline_eligible_repos"]


# ---------------------------------------------------------------------------
# get_approved_manual_campaigns — more null-safety coverage
# ---------------------------------------------------------------------------


def test_get_approved_manual_campaigns_item_with_no_keys():
    # Kills fallback "XXXX" mutations: item with no keys → both fields default to "" → won't match
    bundle = {
        "approval_ledger": [
            {},  # no keys at all
            _ledger_record("github-topics", "approved-manual"),
        ]
    }
    result = get_approved_manual_campaigns(bundle)
    assert len(result) == 1
