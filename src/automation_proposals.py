"""Durable proposal queue + approval gate for bounded automation (Arc D, phase 2).

A *proposal* records the INTENT to take a bounded-automation action against a
single repo (open a context-improvement PR, or update catalog seeds) plus a
status. Proposals deliberately carry no precomputed payload — the executor
(phase 3) re-derives fresh content at apply time so nothing goes stale between
proposal and execution.

The approval gate is a real enforcement boundary: ``executable_proposals`` and
``require_approved`` only ever admit proposals an operator has explicitly
approved. Re-running proposal generation never resets an existing proposal's
status, so operator approvals and rejections are sticky.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Iterable

from src.portfolio_automation import AutomationCandidate

CONTRACT_VERSION = "automation_proposals_v1"

ACTION_CONTEXT_PR = "context-pr"
ACTION_CATALOG_SEED = "catalog-seed"
VALID_ACTION_TYPES = frozenset({ACTION_CONTEXT_PR, ACTION_CATALOG_SEED})

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_EXECUTED = "executed"
VALID_STATUSES = frozenset({STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED, STATUS_EXECUTED})

_ACTION_DESCRIPTIONS = {
    ACTION_CONTEXT_PR: "Open an auto-PR improving the managed context block for {repo}.",
    ACTION_CATALOG_SEED: "Apply catalog seed updates for {repo}.",
}


class ProposalNotFoundError(KeyError):
    """Raised when an operation references a proposal id that does not exist."""


class ProposalApprovalError(RuntimeError):
    """Raised when a status transition or execution gate is violated."""


@dataclass(frozen=True)
class AutomationProposal:
    proposal_id: str
    action_type: str
    display_name: str
    repo_full_name: str
    description: str
    status: str = STATUS_PENDING
    created_at: str = ""
    approved_at: str = ""
    approved_by: str = ""
    rejected_at: str = ""
    executed_at: str = ""
    execution_ref: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutomationProposal:
        if not isinstance(data, dict):
            raise ValueError(f"Proposal entry must be an object, got {type(data).__name__}.")
        for required in ("proposal_id", "action_type"):
            if required not in data:
                raise ValueError(f"Proposal entry is missing required field {required!r}.")
        status = str(data.get("status", STATUS_PENDING))
        if status not in VALID_STATUSES:
            raise ValueError(
                f"Proposal {data['proposal_id']!r} has invalid status {status!r}; "
                f"expected one of {sorted(VALID_STATUSES)}."
            )
        return cls(
            proposal_id=str(data["proposal_id"]),
            action_type=str(data["action_type"]),
            display_name=str(data.get("display_name", "")),
            repo_full_name=str(data.get("repo_full_name", "")),
            description=str(data.get("description", "")),
            status=status,
            created_at=str(data.get("created_at", "")),
            approved_at=str(data.get("approved_at", "")),
            approved_by=str(data.get("approved_by", "")),
            rejected_at=str(data.get("rejected_at", "")),
            executed_at=str(data.get("executed_at", "")),
            execution_ref=str(data.get("execution_ref", "")),
        )


def _require_action_type(action_type: str) -> None:
    if action_type not in VALID_ACTION_TYPES:
        raise ValueError(
            f"Unknown automation action type {action_type!r}; "
            f"expected one of {sorted(VALID_ACTION_TYPES)}."
        )


def make_proposal_id(action_type: str, candidate: AutomationCandidate) -> str:
    """Stable id for a (action, repo) pair — slug-preferred for cross-run identity."""
    _require_action_type(action_type)
    target = candidate.repo_full_name or candidate.display_name
    return f"{action_type}:{target}"


def proposal_for_candidate(
    candidate: AutomationCandidate, action_type: str, *, created_at: str
) -> AutomationProposal:
    """Build a fresh PENDING proposal for one candidate + action type."""
    _require_action_type(action_type)
    return AutomationProposal(
        proposal_id=make_proposal_id(action_type, candidate),
        action_type=action_type,
        display_name=candidate.display_name,
        repo_full_name=candidate.repo_full_name,
        description=_ACTION_DESCRIPTIONS[action_type].format(repo=candidate.display_name),
        status=STATUS_PENDING,
        created_at=created_at,
    )


def build_automation_proposals(
    candidates: Iterable[AutomationCandidate],
    *,
    action_type: str,
    created_at: str,
    existing: Iterable[AutomationProposal] = (),
) -> list[AutomationProposal]:
    """Merge fresh candidate proposals into an existing queue, id-deduplicated.

    Existing proposals are preserved verbatim (status, timestamps, and operator
    decisions are sticky). Only candidates without an existing proposal id are
    appended as new PENDING entries. Existing-first ordering is preserved; new
    entries follow in candidate order.
    """
    _require_action_type(action_type)
    merged: list[AutomationProposal] = list(existing)
    seen = {proposal.proposal_id for proposal in merged}
    for candidate in candidates:
        proposal = proposal_for_candidate(candidate, action_type, created_at=created_at)
        if proposal.proposal_id in seen:
            continue
        merged.append(proposal)
        seen.add(proposal.proposal_id)
    return merged


# --- persistence -----------------------------------------------------------


def load_proposals(path: Path) -> list[AutomationProposal]:
    """Load proposals from ``path``; missing file -> []. Malformed -> ValueError."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise ValueError(f"Malformed proposals file at {path}: {error}") from error
    if not isinstance(data, dict) or not isinstance(data.get("proposals"), list):
        raise ValueError(f"Proposals file at {path} is missing a 'proposals' list.")
    return [AutomationProposal.from_dict(entry) for entry in data["proposals"]]


def save_proposals(path: Path, proposals: Iterable[AutomationProposal]) -> None:
    """Persist proposals to ``path`` as JSON, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "contract_version": CONTRACT_VERSION,
        "proposals": [proposal.to_dict() for proposal in proposals],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")


# --- status transitions ----------------------------------------------------


def _transition(
    proposals: Iterable[AutomationProposal],
    proposal_id: str,
    *,
    expected_status: str,
    **changes: str,
) -> list[AutomationProposal]:
    result: list[AutomationProposal] = []
    found = False
    for proposal in proposals:
        if proposal.proposal_id != proposal_id:
            result.append(proposal)
            continue
        found = True
        if proposal.status != expected_status:
            raise ProposalApprovalError(
                f"Proposal {proposal_id!r} is {proposal.status!r}; "
                f"expected {expected_status!r} for this transition."
            )
        result.append(replace(proposal, **changes))
    if not found:
        raise ProposalNotFoundError(proposal_id)
    return result


def approve_proposal(
    proposals: Iterable[AutomationProposal],
    proposal_id: str,
    *,
    approved_by: str,
    approved_at: str,
) -> list[AutomationProposal]:
    """Transition a PENDING proposal to APPROVED, stamping operator + timestamp."""
    return _transition(
        proposals,
        proposal_id,
        expected_status=STATUS_PENDING,
        status=STATUS_APPROVED,
        approved_by=approved_by,
        approved_at=approved_at,
    )


def reject_proposal(
    proposals: Iterable[AutomationProposal],
    proposal_id: str,
    *,
    rejected_at: str,
) -> list[AutomationProposal]:
    """Transition a PENDING proposal to REJECTED."""
    return _transition(
        proposals,
        proposal_id,
        expected_status=STATUS_PENDING,
        status=STATUS_REJECTED,
        rejected_at=rejected_at,
    )


# --- enforcement gate ------------------------------------------------------


def executable_proposals(
    proposals: Iterable[AutomationProposal],
) -> list[AutomationProposal]:
    """Return only the APPROVED proposals — the executor acts on these alone."""
    return [proposal for proposal in proposals if proposal.status == STATUS_APPROVED]


def require_approved(proposal: AutomationProposal) -> None:
    """Raise unless ``proposal`` is APPROVED. The hard gate before any execution."""
    if proposal.status != STATUS_APPROVED:
        raise ProposalApprovalError(
            f"Proposal {proposal.proposal_id!r} is {proposal.status!r}; "
            "refusing to execute a proposal that is not approved."
        )
