"""auto_apply — bounded automation execution for approved campaign packets.

Provides the trust-bar gating logic that guards --auto-apply-approved. The
actual GitHub API calls still go through the existing apply_github_writeback
path; this module is pure business logic with no side effects.

Trust bar for a repo to receive automated writes:
  1. automation_eligible: true  (catalog opt-in, per-repo)
  2. risk_tier: "baseline"       (truth snapshot, per-repo)
  3. decision_quality_status: "trusted"  (portfolio-level, from operator summary)

All three must pass. Any failure excludes the repo from auto-apply.
"""

from __future__ import annotations

from typing import Any

# Mutation target types safe for unattended execution.
# Excluded: github-project-item, github-project-fields (modify shared project boards).
SAFE_MUTATION_TARGETS: frozenset[str] = frozenset(
    {
        "github-topics",
        "github-custom-properties",
        "github-issue",
        "notion-action",
    }
)


def build_trust_bar_index(
    truth_snapshot: dict[str, Any],
    decision_quality_status: str,
) -> dict[str, bool]:
    """Return {display_name: passes_trust_bar} for every project in the snapshot.

    If the portfolio-level decision_quality_status is not "trusted", every repo
    fails (the index is populated but all values are False).
    """
    portfolio_trusted = decision_quality_status == "trusted"
    index: dict[str, bool] = {}
    for project in truth_snapshot.get("projects", []):
        repo_name = str(project.get("identity", {}).get("display_name", "") or "")
        if not repo_name:
            continue
        automation_eligible = bool(
            (project.get("declared") or {}).get("automation_eligible", False)
        )
        risk_tier = str((project.get("risk") or {}).get("risk_tier", "elevated") or "elevated")
        passes = portfolio_trusted and automation_eligible and risk_tier == "baseline"
        index[repo_name] = passes
    return index


def get_approved_manual_campaigns(ledger_bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Return approval ledger records with approval_state: approved-manual."""
    return [
        item
        for item in (ledger_bundle.get("approval_ledger") or [])
        if str(item.get("approval_state") or "") == "approved-manual"
        and str(item.get("approval_subject_type") or "") == "campaign"
    ]


def filter_safe_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only actions whose mutation_target is in the safe allowlist."""
    return [
        action
        for action in actions
        if str(action.get("mutation_target") or "") in SAFE_MUTATION_TARGETS
    ]


def filter_trusted_repo_actions(
    actions: list[dict[str, Any]],
    trust_bar_index: dict[str, bool],
) -> list[dict[str, Any]]:
    """Keep only actions targeting repos that pass the trust bar.

    Actions that carry no repo identifier are excluded (conservative).
    """
    return [
        action for action in actions if trust_bar_index.get(str(action.get("repo") or ""), False)
    ]
