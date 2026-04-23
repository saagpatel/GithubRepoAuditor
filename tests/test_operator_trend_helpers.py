from __future__ import annotations

from src.operator_trend_pending_text import (
    class_pending_debt_summary,
    pending_debt_freshness_summary,
    transition_closure_confidence_summary,
)
from src.operator_trend_support import (
    is_generic_baseline_guidance,
    is_generic_monitor_guidance,
    is_generic_recommendation,
)


def test_transition_closure_confidence_summary_falls_back_to_hotspot_context() -> None:
    summary = transition_closure_confidence_summary(
        "RepoA blocker",
        {"transition_closure_likely_outcome": "none"},
        [{"label": "RepoA/src/core.py"}],
    )

    assert "RepoA/src/core.py" in summary
    assert "pending states" in summary


def test_pending_debt_summaries_preserve_label_specific_language() -> None:
    debt_summary = class_pending_debt_summary(
        "RepoA blocker",
        {"class_pending_debt_status": "active-debt"},
        [],
        [],
    )
    freshness_summary = pending_debt_freshness_summary(
        "RepoA blocker",
        {"pending_debt_freshness_status": "stale"},
        [],
        [],
    )

    assert debt_summary.startswith("RepoA blocker belongs to a class")
    assert freshness_summary.startswith("RepoA blocker is leaning on older pending-debt patterns")


def test_generic_guidance_helpers_cover_empty_and_baseline_refresh_cases() -> None:
    assert is_generic_recommendation("")
    assert is_generic_recommendation("Continue the normal operator loop after this run.")
    assert is_generic_monitor_guidance("Keep the operator loop lightweight while this settles.")
    assert is_generic_baseline_guidance(
        "",
        {"full_refresh_due": True},
    )
    assert is_generic_baseline_guidance(
        "Refresh the baseline before relying on incremental results.",
    )
