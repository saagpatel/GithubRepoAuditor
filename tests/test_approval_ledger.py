from __future__ import annotations

from pathlib import Path

from src.approval_ledger import build_approval_record, load_approval_ledger_bundle
from src.warehouse import load_approval_records, save_approval_record


def _base_report() -> dict:
    return {
        "username": "testuser",
        "run_id": "testuser:2026-04-13T12:00:00+00:00",
        "generated_at": "2026-04-13T12:00:00+00:00",
        "governance_preview": {
            "fingerprint": "gov-fingerprint-a",
            "actions": [
                {
                    "action_id": "gov-1",
                    "control_key": "enable-secret-scanning",
                    "repo_full_name": "user/RepoA",
                    "title": "Enable secret scanning",
                    "applyable": True,
                    "prerequisites": [],
                }
            ],
        },
        "governance_summary": {
            "status": "ready",
            "needs_reapproval": False,
        },
        "governance_results": {"results": []},
        "operator_summary": {
            "action_sync_packets": [],
            "action_sync_automation": [],
        },
    }


def test_governance_approval_is_ready_for_review_by_default(tmp_path: Path) -> None:
    bundle = load_approval_ledger_bundle(tmp_path, _base_report(), [])

    record = next(item for item in bundle["approval_ledger"] if item["approval_id"] == "governance:all")
    assert record["approval_state"] == "ready-for-review"
    assert bundle["next_approval_review"]["approval_id"] == "governance:all"


def test_governance_approval_needs_reapproval_when_fingerprint_changes(tmp_path: Path) -> None:
    original = _base_report()
    bundle = load_approval_ledger_bundle(tmp_path, original, [])
    ledger_record = next(item for item in bundle["approval_ledger"] if item["approval_id"] == "governance:all")
    save_approval_record(tmp_path, build_approval_record(ledger_record, reviewer="sam", note="Looks good"))

    changed = _base_report()
    changed["governance_preview"] = {
        **changed["governance_preview"],
        "fingerprint": "gov-fingerprint-b",
    }
    changed_bundle = load_approval_ledger_bundle(tmp_path, changed, [])
    record = next(item for item in changed_bundle["approval_ledger"] if item["approval_id"] == "governance:all")

    assert record["approval_state"] == "needs-reapproval"
    assert "needs re-approval" in record["summary"].lower()


def test_campaign_approval_stays_blocked_when_nonapproval_blockers_remain(tmp_path: Path) -> None:
    report = _base_report()
    report["operator_summary"] = {
        "action_sync_packets": [
            {
                "campaign_type": "security-review",
                "label": "Security Review",
                "execution_state": "needs-approval",
                "recommended_target": "github",
                "sync_mode": "reconcile",
                "action_count": 2,
                "blocker_types": ["github-access"],
                "rollback_status": "ready",
                "apply_command": "audit testuser --campaign security-review --writeback-target github --writeback-apply",
                "top_repos": ["user/RepoA"],
                "actions": [{"action_id": "action-1"}],
            }
        ],
        "action_sync_automation": [
            {
                "campaign_type": "security-review",
                "automation_posture": "approval-first",
            }
        ],
    }

    bundle = load_approval_ledger_bundle(tmp_path, report, [])
    record = next(item for item in bundle["approval_ledger"] if item["approval_id"] == "campaign:security-review")

    assert record["approval_state"] == "blocked"
    assert "cannot clear the path" in record["summary"].lower()


def test_campaign_approval_can_become_approved_but_manual(tmp_path: Path) -> None:
    report = _base_report()
    report["operator_summary"] = {
        "action_sync_packets": [
            {
                "campaign_type": "security-review",
                "label": "Security Review",
                "execution_state": "needs-approval",
                "recommended_target": "all",
                "sync_mode": "reconcile",
                "action_count": 2,
                "blocker_types": ["governance-approval"],
                "rollback_status": "ready",
                "apply_command": "audit testuser --campaign security-review --writeback-target all --writeback-apply",
                "top_repos": ["user/RepoA"],
                "actions": [{"action_id": "action-1"}],
            }
        ],
        "action_sync_automation": [
            {
                "campaign_type": "security-review",
                "automation_posture": "approval-first",
            }
        ],
    }

    first_bundle = load_approval_ledger_bundle(tmp_path, report, [])
    first_record = next(item for item in first_bundle["approval_ledger"] if item["approval_id"] == "campaign:security-review")
    save_approval_record(tmp_path, build_approval_record(first_record, reviewer="sam", note="Approved manually"))

    second_bundle = load_approval_ledger_bundle(tmp_path, report, [])
    second_record = next(item for item in second_bundle["approval_ledger"] if item["approval_id"] == "campaign:security-review")

    assert second_record["approval_state"] == "approved-manual"
    assert second_record["manual_apply_command"].endswith("--writeback-apply")


def test_save_and_load_approval_record_preserves_note(tmp_path: Path) -> None:
    record = {
        "approval_id": "governance:all",
        "approval_subject_type": "governance",
        "subject_key": "all",
        "source_run_id": "testuser:2026-04-13T12:00:00+00:00",
        "fingerprint": "fingerprint-1",
        "approved_at": "2026-04-13T12:00:00+00:00",
        "approved_by": "sam",
        "approval_note": "Reviewed by hand",
        "details_json": {"action_count": 1, "applyable_count": 1},
    }

    save_approval_record(tmp_path, record)
    loaded = load_approval_records(tmp_path, "testuser")

    assert loaded[0]["approval_note"] == "Reviewed by hand"
