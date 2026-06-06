"""Tests for the Arc D phase-2 proposal queue + approval gate.

Proposals record *intent* (action type + target + description) and a status.
They carry no precomputed payload — the executor (phase 3) derives fresh content
at apply time. The approval gate (`executable_proposals` / `require_approved`)
is a real enforcement check: nothing is executable until an operator approves.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.automation_proposals import (
    ACTION_CATALOG_SEED,
    ACTION_CONTEXT_PR,
    STATUS_APPROVED,
    STATUS_EXECUTED,
    STATUS_PENDING,
    STATUS_REJECTED,
    AutomationProposal,
    ProposalApprovalError,
    ProposalNotFoundError,
    approve_proposal,
    build_automation_proposals,
    executable_proposals,
    load_proposals,
    make_proposal_id,
    proposal_for_candidate,
    reject_proposal,
    require_approved,
    save_proposals,
)
from src.portfolio_automation import AutomationCandidate

NOW = "2026-04-14T12:00:00+00:00"
LATER = "2026-04-15T09:00:00+00:00"


def _candidate(
    display_name: str = "Repo", repo_full_name: str = "owner/Repo"
) -> AutomationCandidate:
    return AutomationCandidate(
        display_name=display_name,
        repo_full_name=repo_full_name,
        registry_status="active",
        path_confidence="high",
        context_quality="standard",
    )


# --- ids + single-proposal construction ------------------------------------


def test_make_proposal_id_prefers_slug() -> None:
    assert make_proposal_id(ACTION_CONTEXT_PR, _candidate()) == "context-pr:owner/Repo"


def test_make_proposal_id_falls_back_to_display_name() -> None:
    candidate = _candidate(repo_full_name="")
    assert make_proposal_id(ACTION_CATALOG_SEED, candidate) == "catalog-seed:Repo"


def test_proposal_for_candidate_is_pending_with_metadata() -> None:
    proposal = proposal_for_candidate(_candidate(), ACTION_CONTEXT_PR, created_at=NOW)
    assert proposal.status == STATUS_PENDING
    assert proposal.created_at == NOW
    assert proposal.action_type == ACTION_CONTEXT_PR
    assert proposal.repo_full_name == "owner/Repo"
    assert "Repo" in proposal.description


def test_unknown_action_type_is_rejected() -> None:
    with pytest.raises(ValueError):
        proposal_for_candidate(_candidate(), "delete-everything", created_at=NOW)


# --- build/merge -----------------------------------------------------------


def test_build_creates_pending_proposals_for_each_candidate() -> None:
    candidates = [_candidate("Alpha", "o/Alpha"), _candidate("Beta", "o/Beta")]
    proposals = build_automation_proposals(
        candidates, action_type=ACTION_CONTEXT_PR, created_at=NOW
    )
    assert [p.proposal_id for p in proposals] == ["context-pr:o/Alpha", "context-pr:o/Beta"]
    assert all(p.status == STATUS_PENDING for p in proposals)


def test_build_preserves_existing_proposal_status_and_timestamp() -> None:
    existing = [
        AutomationProposal(
            proposal_id="context-pr:o/Alpha",
            action_type=ACTION_CONTEXT_PR,
            display_name="Alpha",
            repo_full_name="o/Alpha",
            description="old",
            status=STATUS_APPROVED,
            created_at="2026-01-01T00:00:00+00:00",
            approved_at="2026-01-02T00:00:00+00:00",
            approved_by="operator",
        )
    ]
    merged = build_automation_proposals(
        [_candidate("Alpha", "o/Alpha")],
        action_type=ACTION_CONTEXT_PR,
        created_at=NOW,
        existing=existing,
    )
    [alpha] = merged
    # Existing approval is NOT reset by re-proposing.
    assert alpha.status == STATUS_APPROVED
    assert alpha.created_at == "2026-01-01T00:00:00+00:00"
    assert alpha.approved_by == "operator"


def test_build_does_not_resurrect_rejected_proposal() -> None:
    existing = [
        AutomationProposal(
            proposal_id="context-pr:o/Alpha",
            action_type=ACTION_CONTEXT_PR,
            display_name="Alpha",
            repo_full_name="o/Alpha",
            description="old",
            status=STATUS_REJECTED,
            created_at="2026-01-01T00:00:00+00:00",
        )
    ]
    merged = build_automation_proposals(
        [_candidate("Alpha", "o/Alpha")],
        action_type=ACTION_CONTEXT_PR,
        created_at=NOW,
        existing=existing,
    )
    [alpha] = merged
    assert alpha.status == STATUS_REJECTED


def test_build_appends_new_candidates_alongside_existing() -> None:
    existing = [
        AutomationProposal(
            proposal_id="context-pr:o/Alpha",
            action_type=ACTION_CONTEXT_PR,
            display_name="Alpha",
            repo_full_name="o/Alpha",
            description="old",
            status=STATUS_APPROVED,
            created_at="2026-01-01T00:00:00+00:00",
        )
    ]
    merged = build_automation_proposals(
        [_candidate("Alpha", "o/Alpha"), _candidate("Beta", "o/Beta")],
        action_type=ACTION_CONTEXT_PR,
        created_at=NOW,
        existing=existing,
    )
    by_id = {p.proposal_id: p for p in merged}
    assert set(by_id) == {"context-pr:o/Alpha", "context-pr:o/Beta"}
    assert by_id["context-pr:o/Beta"].status == STATUS_PENDING


# --- persistence -----------------------------------------------------------


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "pending-proposals.json"
    proposals = build_automation_proposals(
        [_candidate("Alpha", "o/Alpha")], action_type=ACTION_CONTEXT_PR, created_at=NOW
    )
    save_proposals(path, proposals)
    loaded = load_proposals(path)
    assert loaded == proposals


def test_load_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_proposals(tmp_path / "nope.json") == []


def test_load_malformed_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not valid json")
    with pytest.raises(ValueError):
        load_proposals(path)


def test_load_missing_proposals_key_raises(tmp_path: Path) -> None:
    path = tmp_path / "noproposals.json"
    path.write_text('{"contract_version": "automation_proposals_v1"}')
    with pytest.raises(ValueError):
        load_proposals(path)


def test_load_non_dict_entry_raises(tmp_path: Path) -> None:
    path = tmp_path / "nondict.json"
    path.write_text('{"proposals": ["not-an-object"]}')
    with pytest.raises(ValueError):
        load_proposals(path)


def test_load_entry_missing_required_field_raises(tmp_path: Path) -> None:
    path = tmp_path / "missingfield.json"
    path.write_text('{"proposals": [{"action_type": "context-pr"}]}')
    with pytest.raises(ValueError):
        load_proposals(path)


def test_load_entry_with_invalid_status_raises(tmp_path: Path) -> None:
    path = tmp_path / "badstatus.json"
    path.write_text(
        '{"proposals": [{"proposal_id": "x", "action_type": "context-pr", "status": "APPROVED"}]}'
    )
    with pytest.raises(ValueError):
        load_proposals(path)


# --- approval gate ---------------------------------------------------------


def test_approve_pending_sets_status_and_metadata() -> None:
    proposals = build_automation_proposals(
        [_candidate("Alpha", "o/Alpha")], action_type=ACTION_CONTEXT_PR, created_at=NOW
    )
    updated = approve_proposal(
        proposals, "context-pr:o/Alpha", approved_by="saagar", approved_at=LATER
    )
    [alpha] = updated
    assert alpha.status == STATUS_APPROVED
    assert alpha.approved_by == "saagar"
    assert alpha.approved_at == LATER


def test_approve_unknown_id_raises() -> None:
    with pytest.raises(ProposalNotFoundError):
        approve_proposal([], "context-pr:o/Ghost", approved_by="x", approved_at=LATER)


def test_approve_non_pending_raises() -> None:
    proposals = [
        AutomationProposal(
            proposal_id="context-pr:o/Alpha",
            action_type=ACTION_CONTEXT_PR,
            display_name="Alpha",
            repo_full_name="o/Alpha",
            description="d",
            status=STATUS_EXECUTED,
            created_at=NOW,
        )
    ]
    with pytest.raises(ProposalApprovalError):
        approve_proposal(proposals, "context-pr:o/Alpha", approved_by="x", approved_at=LATER)


def test_reject_pending_sets_status_and_rejected_at_only() -> None:
    proposals = build_automation_proposals(
        [_candidate("Alpha", "o/Alpha")], action_type=ACTION_CONTEXT_PR, created_at=NOW
    )
    updated = reject_proposal(proposals, "context-pr:o/Alpha", rejected_at=LATER)
    assert updated[0].status == STATUS_REJECTED
    assert updated[0].rejected_at == LATER
    # Rejection must NOT contaminate the approval fields.
    assert updated[0].approved_at == ""
    assert updated[0].approved_by == ""


def test_reject_unknown_id_raises() -> None:
    with pytest.raises(ProposalNotFoundError):
        reject_proposal([], "context-pr:o/Ghost", rejected_at=LATER)


# --- enforcement gate ------------------------------------------------------


def test_executable_proposals_returns_only_approved() -> None:
    proposals = [
        AutomationProposal(
            "context-pr:a", ACTION_CONTEXT_PR, "A", "o/a", "d", status=STATUS_PENDING
        ),
        AutomationProposal(
            "context-pr:b", ACTION_CONTEXT_PR, "B", "o/b", "d", status=STATUS_APPROVED
        ),
        AutomationProposal(
            "context-pr:c", ACTION_CONTEXT_PR, "C", "o/c", "d", status=STATUS_REJECTED
        ),
        AutomationProposal(
            "context-pr:d", ACTION_CONTEXT_PR, "D", "o/d", "d", status=STATUS_EXECUTED
        ),
    ]
    assert [p.proposal_id for p in executable_proposals(proposals)] == ["context-pr:b"]


def test_require_approved_passes_for_approved() -> None:
    proposal = AutomationProposal(
        "context-pr:b", ACTION_CONTEXT_PR, "B", "o/b", "d", status=STATUS_APPROVED
    )
    require_approved(proposal)  # must not raise


@pytest.mark.parametrize("status", [STATUS_PENDING, STATUS_REJECTED, STATUS_EXECUTED])
def test_require_approved_blocks_non_approved(status: str) -> None:
    proposal = AutomationProposal("context-pr:b", ACTION_CONTEXT_PR, "B", "o/b", "d", status=status)
    with pytest.raises(ProposalApprovalError):
        require_approved(proposal)
