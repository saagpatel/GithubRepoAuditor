from __future__ import annotations

from src.operator_trend_recommendation_drift import (
    recommendation_drift_status,
    recommendation_drift_summary,
)


def test_recommendation_drift_status_flags_repeated_flips() -> None:
    assert recommendation_drift_status(2, []) == "drifting"
    assert recommendation_drift_status(0, [{"flip_count": 2}]) == "watch"
    assert recommendation_drift_status(0, []) == "stable"


def test_recommendation_drift_summary_prefers_primary_target_path_then_hotspot() -> None:
    primary = recommendation_drift_summary(
        "RepoA: Approval drift",
        1,
        "act-now -> verify-first",
        [],
    )
    hotspot = recommendation_drift_summary(
        "RepoA: Approval drift",
        0,
        "",
        [{"label": "RepoB", "flip_count": 3, "recent_policy_path": "monitor -> act-now"}],
    )

    assert "RepoA: Approval drift has started to wobble" in primary
    assert "Trust-policy drift is currently led by RepoB" in hotspot
