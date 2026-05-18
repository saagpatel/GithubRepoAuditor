from __future__ import annotations

from src.operator_trend_decision_memory import (
    absent_decision_memory,
    current_item_last_outcome,
    current_item_resolution_evidence,
    format_intervention,
    resolution_evidence_summary,
    summary_decision_memory,
)

ATTENTION_LANES = {"blocked", "urgent"}


def test_current_item_resolution_evidence_reports_recent_attempt() -> None:
    evidence = current_item_resolution_evidence(
        "repo-a:blocker",
        {"lane": "urgent"},
        "attempted",
        {
            "recorded_at": "2026-04-17T00:00:00+00:00",
            "event_type": "drifted",
            "repo": "RepoA",
            "title": "Approval drift",
            "outcome": "open",
        },
        {"lane": "urgent"},
        [{"items": {"repo-a:blocker": {"lane": "urgent"}}}],
        attention_lanes=ATTENTION_LANES,
    )

    assert "2026-04-17 — drifted for RepoA: Approval drift (open)".lower() in evidence.lower()
    assert evidence.endswith("but the item is still open.")


def test_absent_decision_memory_confirms_resolved_after_two_absent_runs() -> None:
    result = absent_decision_memory(
        "repo-a:blocker",
        [
            {},
            {},
            {"repo-a:blocker": {"lane": "urgent"}},
        ],
        [
            {"items": {}, "generated_at": "2026-04-17T00:00:00+00:00"},
            {"items": {}, "generated_at": "2026-04-16T00:00:00+00:00"},
            {
                "items": {"repo-a:blocker": {"lane": "urgent"}},
                "generated_at": "2026-04-15T00:00:00+00:00",
            },
        ],
        None,
    )

    assert result["status"] == "confirmed_resolved"
    assert result["last_seen_at"] == "2026-04-15T00:00:00+00:00"


def test_decision_memory_helpers_preserve_summary_language() -> None:
    outcome = current_item_last_outcome(
        {"lane": "urgent"},
        {"lane": "blocked"},
        "persisting",
        attention_lanes=ATTENTION_LANES,
    )
    summary = resolution_evidence_summary("quieted", "", 2, 1, 0)
    formatted = format_intervention(
        {
            "recorded_at": "2026-04-17T00:00:00+00:00",
            "event_type": "previewed",
            "repo": "RepoA",
            "title": "Security Review",
            "outcome": "preview",
        }
    )

    assert outcome == "improved"
    assert summary == "2 item(s) are quieter, but not yet confirmed resolved."
    assert formatted == "2026-04-17 — previewed for RepoA: Security Review (preview)"


def test_summary_decision_memory_uses_default_rollup_without_primary_target() -> None:
    summary = summary_decision_memory(
        {},
        {
            "__summary__": {
                "recent_interventions": [{"item_id": "x"}],
                "recently_quieted_count": 1,
                "confirmed_resolved_count": 2,
                "reopened_after_resolution_count": 0,
                "decision_memory_window_runs": 4,
            }
        },
        [{"generated_at": "2026-04-17T00:00:00+00:00"}],
        queue_identity=lambda item: item.get("id", ""),
    )

    assert summary["decision_memory_status"] == "confirmed_resolved"
    assert summary["primary_target_last_outcome"] == "confirmed-resolved"
    assert summary["decision_memory_window_runs"] == 4
    assert "confirmed resolved" in summary["resolution_evidence_summary"].lower()
