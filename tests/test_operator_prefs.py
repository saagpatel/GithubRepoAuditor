"""Tests for src/operator_prefs.py — suppression hint detection and persistence."""

from __future__ import annotations

import json
import tempfile

from src.operator_prefs import (
    SuppressionHint,
    detect_suppressions,
    is_suppressed,
    load_prefs,
    load_rejection_events,
    merge_with_existing,
    post_process_approval_session,
    prefs_path,
    reset_prefs,
    save_prefs,
    save_rejection_event,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _rec(action_type: str, target: str, decision: str, ts: str) -> dict:
    return {
        "action_type": action_type,
        "target_context": target,
        "decision": decision,
        "timestamp": ts,
    }


# ── Test 1: 3 consecutive rejections triggers a hint ─────────────────────────


def test_detect_three_consecutive_rejections():
    records = [
        _rec("notion_writeback", "*", "rejected", "2026-05-01T10:00:00Z"),
        _rec("notion_writeback", "*", "rejected", "2026-05-03T10:00:00Z"),
        _rec("notion_writeback", "*", "rejected", "2026-05-05T10:00:00Z"),
    ]
    hints = detect_suppressions(records, threshold=3)
    assert len(hints) == 1
    hint = hints[0]
    assert hint.action_type == "notion_writeback"
    assert hint.target_context == "*"
    assert hint.rejection_count == 3
    assert hint.manual is False


# ── Test 2: intervening approval breaks streak ───────────────────────────────


def test_detect_approval_breaks_streak():
    records = [
        _rec("notion_writeback", "*", "rejected", "2026-05-01T10:00:00Z"),
        _rec("notion_writeback", "*", "rejected", "2026-05-02T10:00:00Z"),
        _rec("notion_writeback", "*", "approved", "2026-05-03T10:00:00Z"),
        _rec("notion_writeback", "*", "rejected", "2026-05-04T10:00:00Z"),
    ]
    hints = detect_suppressions(records, threshold=3)
    # Streak is only 1 after the approval reset
    assert hints == []


# ── Test 3: different target_context tracked separately ──────────────────────


def test_detect_separate_target_contexts():
    records = [
        _rec("action_A", "repo_X", "rejected", "2026-05-01T10:00:00Z"),
        _rec("action_A", "repo_X", "rejected", "2026-05-02T10:00:00Z"),
        _rec("action_A", "repo_X", "rejected", "2026-05-03T10:00:00Z"),
        _rec("action_A", "repo_Y", "rejected", "2026-05-01T10:00:00Z"),
        _rec("action_A", "repo_Y", "rejected", "2026-05-02T10:00:00Z"),
    ]
    hints = detect_suppressions(records, threshold=3)
    # Only repo_X has 3 consecutive rejections; repo_Y has only 2
    assert len(hints) == 1
    assert hints[0].action_type == "action_A"
    assert hints[0].target_context == "repo_X"


# ── Test 4: load_prefs with missing file returns {} ──────────────────────────


def test_load_prefs_missing_file(tmp_path):
    result = load_prefs(tmp_path / "nonexistent.json")
    assert result == {}


# ── Test 5: save_prefs uses atomic write (tmp + rename) ──────────────────────


def test_save_prefs_atomic(tmp_path, monkeypatch):
    """Verify atomic write: file contents must be consistent (no partial writes)."""
    path = tmp_path / "operator_prefs.json"
    hints = [
        SuppressionHint(
            action_type="notion_writeback",
            target_context="*",
            rejection_count=3,
            last_rejected_at="2026-05-05T10:00:00Z",
            suppressed_at="2026-05-05T10:00:00Z",
            manual=False,
        )
    ]

    # Track if NamedTemporaryFile was used (proof of tmp+rename pattern)
    original_ntf = tempfile.NamedTemporaryFile
    calls: list[str] = []

    def tracking_ntf(*args, **kwargs):
        calls.append("ntf")
        return original_ntf(*args, **kwargs)

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", tracking_ntf)

    save_prefs(path, hints)

    assert calls, "NamedTemporaryFile should have been called (atomic write)"
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["version"] == 1
    assert len(data["suppressions"]) == 1
    assert data["suppressions"][0]["action_type"] == "notion_writeback"


# ── Test 6: merge_with_existing preserves manual entries ─────────────────────


def test_merge_with_existing_preserves_manual():
    existing = {
        "version": 1,
        "suppressions": [
            {
                "action_type": "manual_action",
                "target_context": "some_repo",
                "rejection_count": 99,
                "last_rejected_at": "2026-01-01T00:00:00Z",
                "suppressed_at": "2026-01-01T00:00:00Z",
                "manual": True,
            },
            {
                "action_type": "old_auto",
                "target_context": "*",
                "rejection_count": 3,
                "last_rejected_at": "2026-04-01T00:00:00Z",
                "suppressed_at": "2026-04-01T00:00:00Z",
                "manual": False,
            },
        ],
    }
    new_hints = [
        SuppressionHint(
            action_type="new_auto",
            target_context="*",
            rejection_count=4,
            last_rejected_at="2026-05-01T00:00:00Z",
            suppressed_at="2026-05-01T00:00:00Z",
            manual=False,
        )
    ]

    merged = merge_with_existing(existing, new_hints)
    suppression_keys = {(s["action_type"], s["target_context"]) for s in merged["suppressions"]}

    # Manual entry preserved
    assert ("manual_action", "some_repo") in suppression_keys
    # Old auto entry removed (replaced by new_hints)
    assert ("old_auto", "*") not in suppression_keys
    # New auto entry present
    assert ("new_auto", "*") in suppression_keys

    # Manual flag still True on the preserved entry
    manual_entry = next(s for s in merged["suppressions"] if s["action_type"] == "manual_action")
    assert manual_entry["manual"] is True


# ── Test 7: is_suppressed exact-match and wildcard ───────────────────────────


def test_is_suppressed_exact_and_wildcard():
    prefs = {
        "version": 1,
        "suppressions": [
            {
                "action_type": "notion_writeback",
                "target_context": "*",
                "rejection_count": 4,
                "last_rejected_at": "2026-05-09T14:23:00Z",
                "suppressed_at": "2026-05-09T14:23:00Z",
                "manual": False,
            },
            {
                "action_type": "github_writeback",
                "target_context": "specific_repo",
                "rejection_count": 3,
                "last_rejected_at": "2026-05-08T10:00:00Z",
                "suppressed_at": "2026-05-08T10:00:00Z",
                "manual": False,
            },
        ],
    }

    # Wildcard match
    hint = is_suppressed(prefs, "notion_writeback", "any_repo")
    assert hint is not None
    assert hint.action_type == "notion_writeback"
    assert hint.target_context == "*"

    # Exact match
    hint2 = is_suppressed(prefs, "github_writeback", "specific_repo")
    assert hint2 is not None
    assert hint2.target_context == "specific_repo"

    # No match
    hint3 = is_suppressed(prefs, "github_writeback", "other_repo")
    assert hint3 is None

    # Completely different action
    hint4 = is_suppressed(prefs, "unknown_action", "any_repo")
    assert hint4 is None


# ── Test 8: reset_prefs idempotent ───────────────────────────────────────────


def test_reset_prefs_idempotent(tmp_path):
    path = tmp_path / "operator_prefs.json"
    path.write_text(json.dumps({"version": 1, "suppressions": []}))

    # First call deletes the file
    reset_prefs(path)
    assert not path.exists()

    # Second call does not raise
    reset_prefs(path)
    assert not path.exists()


# ── Test 9: CLI --reset-prefs clears file ────────────────────────────────────


def test_cli_reset_prefs_clears_file(tmp_path):
    """CLI --reset-prefs should delete operator_prefs.json and return cleanly."""
    prefs_file = tmp_path / "operator_prefs.json"
    prefs_file.write_text(
        json.dumps(
            {
                "version": 1,
                "suppressions": [
                    {
                        "action_type": "notion_writeback",
                        "target_context": "*",
                        "rejection_count": 3,
                        "last_rejected_at": "2026-05-09T00:00:00Z",
                        "suppressed_at": "2026-05-09T00:00:00Z",
                        "manual": False,
                    }
                ],
            }
        )
    )

    import sys

    from src.cli import main  # noqa: PLC0415

    sys.argv = [
        "audit",
        "--output-dir",
        str(tmp_path),
        "--reset-prefs",
        "placeholder_user",
    ]
    # main() returns (no SystemExit) after --reset-prefs
    main()

    assert not prefs_file.exists()


# ── Test 10: --approval-center integration updates prefs ─────────────────────


def test_post_process_approval_session_updates_prefs(tmp_path):
    """post_process_approval_session with 3 rejection events should write prefs."""
    # Write 3 rejection events to the rejection log
    for i in range(3):
        save_rejection_event(
            tmp_path,
            action_type="notion_writeback",
            target_context="*",
            timestamp=f"2026-05-0{i + 1}T10:00:00Z",
        )

    total, newly_added = post_process_approval_session(
        load_rejection_events(tmp_path),
        tmp_path,
        threshold=3,
    )

    assert newly_added == 1
    assert total >= 1

    prefs = load_prefs(prefs_path(tmp_path))
    suppressions = prefs.get("suppressions", [])
    assert any(
        s["action_type"] == "notion_writeback" and s["target_context"] == "*" for s in suppressions
    )


# ── Test 11: briefing skips suppressed actions ───────────────────────────────


def test_briefing_skips_suppressed_action():
    """build_briefing with prefs containing a suppression should skip that action."""
    from src.briefing import build_briefing

    prefs = {
        "version": 1,
        "suppressions": [
            {
                "action_type": "security",
                "target_context": "suppressed_repo",
                "rejection_count": 3,
                "last_rejected_at": "2026-05-01T00:00:00Z",
                "suppressed_at": "2026-05-01T00:00:00Z",
                "manual": False,
            }
        ],
    }

    audits = [
        {
            "overall_score": 0.2,
            "metadata": {"name": "suppressed_repo", "language": "Python"},
            "hotspots": [{"title": "Security issue", "category": "security"}],
        },
        {
            "overall_score": 0.3,
            "metadata": {"name": "normal_repo", "language": "Python"},
            "hotspots": [{"title": "Missing tests", "category": "testing"}],
        },
    ]

    briefing = build_briefing(
        audits,
        username="testuser",
        date="2026-05-11",
        provider=None,  # No LLM — suggestions will be empty but suppressed_by_prefs still set
        prefs=prefs,
    )

    # suppressed_repo should appear in suppressed_by_prefs
    assert "suppressed_repo" in briefing.suppressed_by_prefs
    # normal_repo should NOT be suppressed
    assert "normal_repo" not in briefing.suppressed_by_prefs


# ── Test 12: fallback fields — approval_subject_type and subject_key ─────────


def test_detect_fallback_fields():
    """detect_suppressions should fall back to approval_subject_type / subject_key."""
    records = [
        {
            "approval_subject_type": "campaign",
            "subject_key": "promotion-push",
            "decision": "rejected",
            "approved_at": "2026-05-01T10:00:00Z",
        },
        {
            "approval_subject_type": "campaign",
            "subject_key": "promotion-push",
            "decision": "rejected",
            "approved_at": "2026-05-03T10:00:00Z",
        },
        {
            "approval_subject_type": "campaign",
            "subject_key": "promotion-push",
            "decision": "rejected",
            "approved_at": "2026-05-05T10:00:00Z",
        },
    ]
    hints = detect_suppressions(records, threshold=3)
    assert len(hints) == 1
    assert hints[0].action_type == "campaign"
    assert hints[0].target_context == "promotion-push"
