from __future__ import annotations

from src.operator_trend_exception_recovery import (
    exception_pattern_summary,
    recovery_pattern_reason,
    trust_recovery_for_target,
)


def _target_label(item: dict) -> str:
    repo = item.get("repo", "")
    title = item.get("title", "")
    return f"{repo}: {title}" if repo else title


def test_trust_recovery_for_target_earns_act_with_review_when_stable() -> None:
    status, reason, policy, policy_reason = trust_recovery_for_target(
        {
            "repo": "RepoA",
            "title": "Fix setup",
            "lane": "blocked",
            "kind": "setup",
            "trust_exception_status": "softened-for-noise",
        },
        {
            "recent_reopened": False,
            "recent_policy_flip_count": 0,
            "same_or_lower_pressure_path": True,
            "stable_policy_run_count": 3,
        },
        {"confidence_validation_status": "healthy"},
        trust_policy="verify-first",
        trust_policy_reason="Need verification first.",
        trust_recovery_window_runs=3,
    )

    assert status == "earned"
    assert policy == "act-with-review"
    assert "earned" in reason
    assert policy_reason == reason


def test_recovery_pattern_reason_preserves_candidate_message() -> None:
    assert (
        recovery_pattern_reason("candidate", "")
        == "This target is stabilizing, but it has not yet earned stronger trust."
    )


def test_exception_pattern_summary_uses_hotspot_when_available() -> None:
    summary = exception_pattern_summary(
        {"exception_pattern_status": "none", "trust_recovery_status": "none"},
        [{"label": "RepoA: Fix drift"}],
        target_label=_target_label,
    )

    assert "RepoA: Fix drift" in summary
    assert "verify-first guidance" in summary
