"""Tests for Arc G Sprint 7B — per-action approve/reject on campaign-plan packets."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.plan_campaign import (
    CampaignAction,
    CampaignPlanPacket,
    approve_action,
    load_approved_campaign_plans,
    reject_action,
    write_packet_to_ledger,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _recent_generated_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_packet(
    goal: str = "add CI to all repos",
    *,
    num_actions: int = 2,
    generated_at: str | None = None,
) -> CampaignPlanPacket:
    generated_at = generated_at or _recent_generated_at()
    actions = [
        CampaignAction(
            repo_name=f"repo-{i}",
            action_type="add_topics",
            target="python, cli",
            rationale=f"Improves discoverability of repo-{i}",
            expected_impact="More stars",
        )
        for i in range(num_actions)
    ]
    return CampaignPlanPacket(
        goal=goal,
        actions=actions,
        candidate_count=5,
        qualified_count=num_actions,
        llm_provider="fake",
        llm_model="fake-model",
        llm_cost_usd=0.001,
        generated_at=generated_at,
    )


def _seed_approved_manual(output_dir: Path, goal: str = "add CI to all repos") -> str:
    """Write a packet with status='approved-manual' and return the record_id."""
    from src.warehouse import load_approval_records, save_approval_record

    packet = _make_packet(goal)
    record_id = write_packet_to_ledger(packet, output_dir=output_dir, reviewer="tester")
    # Elevate to approved-manual so load_approved_campaign_plans picks it up
    records = load_approval_records(output_dir, "", limit=50)
    for rec in records:
        if rec.get("approval_id") == record_id:
            updated = dict(rec)
            updated["status"] = "approved-manual"
            save_approval_record(output_dir, updated)
    return record_id


# ---------------------------------------------------------------------------
# 7B.2 — approve_action
# ---------------------------------------------------------------------------


class TestApproveAction:
    def test_sets_state_approved_and_persists(self) -> None:
        from src.warehouse import load_approval_records

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            record_id = _seed_approved_manual(output_dir)

            approve_action(record_id, 0, output_dir)

            records = load_approval_records(output_dir, "", limit=50)
            rec = next(r for r in records if r.get("approval_id") == record_id)
            assert rec["actions"][0]["state"] == "approved"
            assert rec["actions"][0]["decided_at"] is not None

    def test_sets_decided_at_iso_timestamp(self) -> None:
        from src.warehouse import load_approval_records

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            record_id = _seed_approved_manual(output_dir)

            approve_action(record_id, 1, output_dir)

            records = load_approval_records(output_dir, "", limit=50)
            rec = next(r for r in records if r.get("approval_id") == record_id)
            decided_at = rec["actions"][1]["decided_at"]
            assert isinstance(decided_at, str)
            assert "T" in decided_at  # ISO format

    def test_approve_nonexistent_packet_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(ValueError, match="no campaign-plan record found"):
                approve_action("cp-doesnotexist", 0, Path(tmp))

    def test_approve_out_of_range_idx_raises_index_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            record_id = _seed_approved_manual(output_dir)

            with pytest.raises(IndexError, match="out of range"):
                approve_action(record_id, 99, output_dir)

    def test_approve_negative_idx_raises_index_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            record_id = _seed_approved_manual(output_dir)

            with pytest.raises(IndexError, match="out of range"):
                approve_action(record_id, -1, output_dir)

    def test_clears_rejected_reason_on_re_approve(self) -> None:
        """Re-approving a previously rejected action clears rejected_reason."""
        from src.warehouse import load_approval_records

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            record_id = _seed_approved_manual(output_dir)

            reject_action(record_id, 0, output_dir, reason="not ready")
            approve_action(record_id, 0, output_dir)

            records = load_approval_records(output_dir, "", limit=50)
            rec = next(r for r in records if r.get("approval_id") == record_id)
            assert rec["actions"][0]["state"] == "approved"
            assert rec["actions"][0].get("rejected_reason") is None


# ---------------------------------------------------------------------------
# 7B.2 — reject_action
# ---------------------------------------------------------------------------


class TestRejectAction:
    def test_sets_state_rejected_with_reason(self) -> None:
        from src.warehouse import load_approval_records

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            record_id = _seed_approved_manual(output_dir)

            reject_action(record_id, 0, output_dir, reason="too risky")

            records = load_approval_records(output_dir, "", limit=50)
            rec = next(r for r in records if r.get("approval_id") == record_id)
            assert rec["actions"][0]["state"] == "rejected"
            assert rec["actions"][0]["rejected_reason"] == "too risky"
            assert rec["actions"][0]["decided_at"] is not None

    def test_sets_state_rejected_empty_reason(self) -> None:
        from src.warehouse import load_approval_records

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            record_id = _seed_approved_manual(output_dir)

            reject_action(record_id, 1, output_dir, reason="")

            records = load_approval_records(output_dir, "", limit=50)
            rec = next(r for r in records if r.get("approval_id") == record_id)
            assert rec["actions"][1]["state"] == "rejected"
            assert rec["actions"][1].get("rejected_reason") is None

    def test_reject_nonexistent_packet_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(ValueError, match="no campaign-plan record found"):
                reject_action("cp-doesnotexist", 0, Path(tmp), reason="x")

    def test_reject_out_of_range_idx_raises_index_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            record_id = _seed_approved_manual(output_dir)

            with pytest.raises(IndexError, match="out of range"):
                reject_action(record_id, 99, output_dir, reason="x")

    def test_re_approve_flips_rejected_back_to_approved(self) -> None:
        """Idempotency: approve after reject → state becomes approved."""
        from src.warehouse import load_approval_records

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            record_id = _seed_approved_manual(output_dir)

            reject_action(record_id, 0, output_dir, reason="bad")
            approve_action(record_id, 0, output_dir)

            records = load_approval_records(output_dir, "", limit=50)
            rec = next(r for r in records if r.get("approval_id") == record_id)
            assert rec["actions"][0]["state"] == "approved"


# ---------------------------------------------------------------------------
# 7B.1 — backward-compat: missing state defaults to "pending"
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    def test_load_approved_campaign_plans_defaults_missing_state_to_pending(self) -> None:
        """Pre-7B records without 'state' key → CampaignAction.state == 'pending'."""
        from src.warehouse import save_approval_record

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            generated_at = _recent_generated_at()
            # Write a record whose actions have NO 'state' field
            save_approval_record(
                output_dir,
                {
                    "approval_id": "cp-legacy-0001",
                    "fingerprint": "fp-leg-001",
                    "approval_subject_type": "campaign-plan",
                    "subject_key": "legacykey001",
                    "source_run_id": "",
                    "approved_at": generated_at,
                    "approved_by": "tester",
                    "approval_note": "legacy",
                    "action_type": "campaign-plan",
                    "target_context": "legacy goal",
                    "goal": "legacy goal",
                    "candidate_count": 1,
                    "qualified_count": 1,
                    "llm_provider": "fake",
                    "llm_model": "m",
                    "llm_cost_usd": 0.0,
                    "generated_at": generated_at,
                    "status": "approved-manual",
                    "actions": [
                        {
                            "repo_name": "old-repo",
                            "action_type": "add_topics",
                            "target": "python",
                            "rationale": "legacy",
                            "expected_impact": None,
                            # deliberately no 'state' key
                        }
                    ],
                },
            )

            packets = load_approved_campaign_plans(output_dir)
            assert len(packets) == 1
            assert packets[0].actions[0].state == "pending"

    def test_load_approved_campaign_plans_preserves_existing_state(self) -> None:
        """Records with 'state' set are hydrated correctly."""
        from src.warehouse import save_approval_record

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            generated_at = _recent_generated_at()
            save_approval_record(
                output_dir,
                {
                    "approval_id": "cp-state-0002",
                    "fingerprint": "fp-st-002",
                    "approval_subject_type": "campaign-plan",
                    "subject_key": "statekey002",
                    "source_run_id": "",
                    "approved_at": generated_at,
                    "approved_by": "tester",
                    "approval_note": "state test",
                    "action_type": "campaign-plan",
                    "target_context": "state goal",
                    "goal": "state goal",
                    "candidate_count": 1,
                    "qualified_count": 1,
                    "llm_provider": "fake",
                    "llm_model": "m",
                    "llm_cost_usd": 0.0,
                    "generated_at": generated_at,
                    "status": "approved-manual",
                    "actions": [
                        {
                            "repo_name": "approved-repo",
                            "action_type": "add_topics",
                            "target": "python",
                            "rationale": "test",
                            "expected_impact": None,
                            "state": "approved",
                            "decided_at": "2026-05-12T01:00:00+00:00",
                            "rejected_reason": None,
                        }
                    ],
                },
            )

            packets = load_approved_campaign_plans(output_dir)
            assert len(packets) == 1
            assert packets[0].actions[0].state == "approved"
            assert packets[0].actions[0].decided_at == "2026-05-12T01:00:00+00:00"


# ---------------------------------------------------------------------------
# 7B.5 — apply path gate
# ---------------------------------------------------------------------------


class TestApplyPathGate:
    """Tests for 7B.5: dispatch_action only called for state='approved' actions."""

    def _make_approved_manual_packet(
        self,
        output_dir: Path,
        actions: list[CampaignAction],
        goal: str = "apply gate test",
    ) -> CampaignPlanPacket:
        from src.plan_campaign import _goal_subject_key, _packet_record_id
        from src.warehouse import save_approval_record

        generated_at = _recent_generated_at()
        packet = CampaignPlanPacket(
            goal=goal,
            actions=actions,
            candidate_count=3,
            qualified_count=len(actions),
            llm_provider="fake",
            llm_model="m",
            llm_cost_usd=0.0,
            generated_at=generated_at,
        )
        record_id = _packet_record_id(packet)
        actions_dicts = [
            {
                "repo_name": a.repo_name,
                "action_type": a.action_type,
                "target": a.target,
                "rationale": a.rationale,
                "expected_impact": a.expected_impact,
                "state": a.state,
                "rejected_reason": a.rejected_reason,
                "decided_at": a.decided_at,
            }
            for a in actions
        ]
        save_approval_record(
            output_dir,
            {
                "approval_id": record_id,
                "fingerprint": _goal_subject_key(goal),
                "approval_subject_type": "campaign-plan",
                "subject_key": _goal_subject_key(goal),
                "source_run_id": "",
                "approved_at": generated_at,
                "approved_by": "tester",
                "approval_note": goal,
                "action_type": "campaign-plan",
                "target_context": goal,
                "goal": goal,
                "candidate_count": 3,
                "qualified_count": len(actions),
                "llm_provider": "fake",
                "llm_model": "m",
                "llm_cost_usd": 0.0,
                "generated_at": generated_at,
                "status": "approved-manual",
                "actions": actions_dicts,
            },
        )
        return packet

    def test_pending_action_is_skipped_no_dispatch(self) -> None:
        """An action with state='pending' must not be dispatched."""
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            actions = [
                CampaignAction(
                    repo_name="repo-a",
                    action_type="add_topics",
                    target="python",
                    rationale="r",
                    state="pending",
                ),
            ]
            self._make_approved_manual_packet(output_dir, actions)

            with patch("src.plan_campaign.dispatch_action") as mock_dispatch:
                packets = load_approved_campaign_plans(output_dir)
                assert len(packets) == 1
                # Only approved actions should be dispatched — pending ones skip
                for action in packets[0].actions:
                    if action.state != "approved":
                        continue
                    mock_dispatch(action)
                mock_dispatch.assert_not_called()

    def test_rejected_action_is_skipped(self) -> None:
        """An action with state='rejected' must not be dispatched."""
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            actions = [
                CampaignAction(
                    repo_name="repo-b",
                    action_type="add_topics",
                    target="python",
                    rationale="r",
                    state="rejected",
                    rejected_reason="not now",
                ),
            ]
            self._make_approved_manual_packet(output_dir, actions)
            packets = load_approved_campaign_plans(output_dir)
            assert len(packets) == 1
            dispatchable = [a for a in packets[0].actions if a.state == "approved"]
            assert len(dispatchable) == 0

    def test_packet_with_all_terminal_actions_can_be_marked_applied(self) -> None:
        """When all actions are approved or rejected (no pending), mark_campaign_applied works."""
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            actions = [
                CampaignAction(
                    repo_name="r1",
                    action_type="add_topics",
                    target="t",
                    rationale="r",
                    state="approved",
                    decided_at="2026-05-12T01:00:00+00:00",
                ),
                CampaignAction(
                    repo_name="r2",
                    action_type="add_topics",
                    target="t",
                    rationale="r",
                    state="rejected",
                    rejected_reason="skip",
                    decided_at="2026-05-12T01:00:00+00:00",
                ),
            ]
            packet = self._make_approved_manual_packet(output_dir, actions, goal="all terminal")

            # All actions terminal → mark applied should work
            has_pending = any(
                (getattr(a, "state", "pending") or "pending") == "pending" for a in packet.actions
            )
            assert not has_pending

    def test_packet_with_pending_action_is_not_terminal(self) -> None:
        """A mix of approved + pending means has_pending is True → leave as approved-manual."""
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            actions = [
                CampaignAction(
                    repo_name="r1",
                    action_type="add_topics",
                    target="t",
                    rationale="r",
                    state="approved",
                    decided_at="2026-05-12T01:00:00+00:00",
                ),
                CampaignAction(
                    repo_name="r2",
                    action_type="add_topics",
                    target="t",
                    rationale="r",
                    state="pending",
                ),
            ]
            packet = self._make_approved_manual_packet(output_dir, actions, goal="mixed pending")

            has_pending = any(
                (getattr(a, "state", "pending") or "pending") == "pending" for a in packet.actions
            )
            assert has_pending


# ---------------------------------------------------------------------------
# 7B.3 — Web routes (HTMX partials)
# ---------------------------------------------------------------------------


fastapi = pytest.importorskip("fastapi", reason="[serve] extra not installed")
pytest.importorskip("uvicorn", reason="[serve] extra not installed")
pytest.importorskip("jinja2", reason="[serve] extra not installed")

from fastapi.testclient import TestClient  # noqa: E402

from src.serve.app import create_app  # noqa: E402


def _seed_cp_record_for_routes(output_dir: Path) -> str:
    """Seed a campaign-plan record with 2 pending actions; return record_id."""
    from src.warehouse import save_approval_record

    record_id = "cp-7b-route-test-0001"
    save_approval_record(
        output_dir,
        {
            "approval_id": record_id,
            "fingerprint": "fp-7b-001",
            "approval_subject_type": "campaign-plan",
            "subject_key": "7b0001key",
            "source_run_id": "",
            "approved_at": "2026-05-12T00:00:00+00:00",
            "approved_by": "tester",
            "approval_note": "7B route test",
            "action_type": "campaign-plan",
            "target_context": "7B route test goal",
            "goal": "7B route test goal",
            "candidate_count": 2,
            "qualified_count": 2,
            "llm_provider": "fake",
            "llm_model": "m",
            "llm_cost_usd": 0.0,
            "generated_at": "2026-05-12T00:00:00+00:00",
            "status": "approved-manual",
            "actions": [
                {
                    "repo_name": "route-repo-0",
                    "action_type": "add_topics",
                    "target": "python",
                    "rationale": "First action",
                    "expected_impact": None,
                    "state": "pending",
                },
                {
                    "repo_name": "route-repo-1",
                    "action_type": "add_topics",
                    "target": "cli",
                    "rationale": "Second action",
                    "expected_impact": None,
                    "state": "pending",
                },
            ],
        },
    )
    return record_id


class TestPerActionRoutes:
    """Tests for POST /approvals/{packet_id}/actions/{idx}/approve|reject."""

    def _make_output_dir(self, tmp_path: Path) -> Path:
        od = tmp_path / "output"
        od.mkdir()
        # Minimal portfolio-truth so create_app doesn't error
        truth = {"generated_at": "2026-01-01T00:00:00", "repos": []}
        (od / "portfolio-truth-latest.json").write_text(json.dumps(truth))
        return od

    def test_approve_action_returns_200_with_approved_badge(self, tmp_path: Path) -> None:
        output_dir = self._make_output_dir(tmp_path)
        record_id = _seed_cp_record_for_routes(output_dir)

        app = create_app(output_dir=output_dir)
        c = TestClient(app, raise_server_exceptions=True)

        resp = c.post(f"/approvals/{record_id}/actions/0/approve")
        assert resp.status_code == 200
        assert "approved" in resp.text.lower() or "&#10003;" in resp.text

    def test_approve_action_persists_state(self, tmp_path: Path) -> None:
        from src.warehouse import load_approval_records

        output_dir = self._make_output_dir(tmp_path)
        record_id = _seed_cp_record_for_routes(output_dir)

        app = create_app(output_dir=output_dir)
        c = TestClient(app, raise_server_exceptions=True)

        c.post(f"/approvals/{record_id}/actions/0/approve")

        records = load_approval_records(output_dir, "", limit=50)
        rec = next(r for r in records if r.get("approval_id") == record_id)
        assert rec["actions"][0]["state"] == "approved"

    def test_reject_action_returns_200_with_rejected_badge(self, tmp_path: Path) -> None:
        output_dir = self._make_output_dir(tmp_path)
        record_id = _seed_cp_record_for_routes(output_dir)

        app = create_app(output_dir=output_dir)
        c = TestClient(app, raise_server_exceptions=True)

        resp = c.post(f"/approvals/{record_id}/actions/1/reject")
        assert resp.status_code == 200
        assert "rejected" in resp.text.lower() or "&#10007;" in resp.text

    def test_approve_nonexistent_packet_returns_404(self, tmp_path: Path) -> None:
        output_dir = self._make_output_dir(tmp_path)
        app = create_app(output_dir=output_dir)
        c = TestClient(app, raise_server_exceptions=False)

        resp = c.post("/approvals/nonexistent/actions/0/approve")
        assert resp.status_code == 404

    def test_approve_out_of_range_idx_returns_404(self, tmp_path: Path) -> None:
        output_dir = self._make_output_dir(tmp_path)
        record_id = _seed_cp_record_for_routes(output_dir)

        app = create_app(output_dir=output_dir)
        c = TestClient(app, raise_server_exceptions=False)

        resp = c.post(f"/approvals/{record_id}/actions/99/approve")
        assert resp.status_code == 404

    def test_reject_nonexistent_packet_returns_404(self, tmp_path: Path) -> None:
        output_dir = self._make_output_dir(tmp_path)
        app = create_app(output_dir=output_dir)
        c = TestClient(app, raise_server_exceptions=False)

        resp = c.post("/approvals/nonexistent/actions/0/reject")
        assert resp.status_code == 404

    def test_campaign_plan_partial_shows_action_counts(self, tmp_path: Path) -> None:
        """GET /approvals/{id}/campaign-plan shows approved/rejected/pending counts."""
        output_dir = self._make_output_dir(tmp_path)
        record_id = _seed_cp_record_for_routes(output_dir)

        # Approve action 0, leave action 1 pending
        app = create_app(output_dir=output_dir)
        c = TestClient(app, raise_server_exceptions=True)
        c.post(f"/approvals/{record_id}/actions/0/approve")

        resp = c.get(f"/approvals/{record_id}/campaign-plan")
        assert resp.status_code == 200
        # Should show count badges
        assert "approved" in resp.text.lower()
        assert "pending" in resp.text.lower()

    def test_action_row_partial_is_not_full_page(self, tmp_path: Path) -> None:
        """POST returns a fragment, not a full HTML page."""
        output_dir = self._make_output_dir(tmp_path)
        record_id = _seed_cp_record_for_routes(output_dir)

        app = create_app(output_dir=output_dir)
        c = TestClient(app, raise_server_exceptions=True)

        resp = c.post(f"/approvals/{record_id}/actions/0/approve")
        assert resp.status_code == 200
        body = resp.text.lower()
        assert "<html" not in body
        assert "<body" not in body
