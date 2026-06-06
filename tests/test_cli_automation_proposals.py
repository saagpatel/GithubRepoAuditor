"""CLI integration for the Arc D phase-3b bounded-automation proposal flags.

Drives ``main()`` end-to-end (legacy flat form) for the queue-only triage flags
— list / approve / reject — proving arg parsing, subcommand inference, dispatch,
and the handler all wire together. The execute orchestration itself is covered
by ``test_automation_workflow.py`` (snapshot + runner injected); here we only
exercise the CLI seams that don't require building a real portfolio snapshot.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from src.automation_proposals import (
    ACTION_CONTEXT_PR,
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
    AutomationProposal,
    load_proposals,
    save_proposals,
)

NOW = "2026-04-14T12:00:00+00:00"


def _seed(output_dir: Path, status: str = STATUS_PENDING) -> Path:
    proposals_path = output_dir / "pending-proposals.json"
    save_proposals(
        proposals_path,
        [
            AutomationProposal(
                proposal_id="context-pr:owner/MyRepo",
                action_type=ACTION_CONTEXT_PR,
                display_name="MyRepo",
                repo_full_name="owner/MyRepo",
                description="Open an auto-PR improving the managed context block for MyRepo.",
                status=status,
                created_at=NOW,
            )
        ],
    )
    return proposals_path


def _run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *flags: str) -> None:
    from src.cli import main

    monkeypatch.setattr(sys, "argv", ["audit", "--output-dir", str(tmp_path), "user", *flags])
    main()


def test_list_proposals_empty(monkeypatch, tmp_path, capsys) -> None:
    _run(monkeypatch, tmp_path, "--list-proposals")
    assert "No bounded-automation proposals in the queue." in capsys.readouterr().err


def test_list_proposals_populated(monkeypatch, tmp_path, capsys) -> None:
    _seed(tmp_path)
    _run(monkeypatch, tmp_path, "--list-proposals")
    out = capsys.readouterr().err
    assert "context-pr:owner/MyRepo" in out
    assert "pending" in out


def test_approve_proposal_transitions_and_persists(monkeypatch, tmp_path, capsys) -> None:
    proposals_path = _seed(tmp_path)
    _run(monkeypatch, tmp_path, "--approve-proposal", "context-pr:owner/MyRepo")

    assert "Approved proposal" in capsys.readouterr().err
    persisted = load_proposals(proposals_path)[0]
    assert persisted.status == STATUS_APPROVED
    assert persisted.approved_by == "local-operator"


def test_reject_proposal_transitions_and_persists(monkeypatch, tmp_path, capsys) -> None:
    proposals_path = _seed(tmp_path)
    _run(monkeypatch, tmp_path, "--reject-proposal", "context-pr:owner/MyRepo")

    assert "Rejected proposal" in capsys.readouterr().err
    assert load_proposals(proposals_path)[0].status == STATUS_REJECTED


def test_approve_unknown_proposal_warns_and_leaves_queue(monkeypatch, tmp_path, capsys) -> None:
    proposals_path = _seed(tmp_path)
    _run(monkeypatch, tmp_path, "--approve-proposal", "context-pr:owner/Ghost")

    # Unknown id is surfaced, not a crash; the queue is untouched.
    capsys.readouterr()
    assert load_proposals(proposals_path)[0].status == STATUS_PENDING
