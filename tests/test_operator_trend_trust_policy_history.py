from __future__ import annotations

from src.operator_trend_trust_policy_history import (
    build_trust_policy_events,
    false_positive_exception_hotspots,
    policy_flip_count,
    trust_policy_exception_for_target,
)


def _queue_identity(item: dict) -> str:
    return f"{item.get('repo', '')}:{item.get('title', '')}"


def _target_class_key(item: dict) -> str:
    return f"{item.get('lane', '')}:{item.get('kind', '') or 'unknown'}"


def _target_label(item: dict) -> str:
    repo = item.get("repo", "")
    title = item.get("title", "")
    return f"{repo}: {title}" if repo else title


def _recommendation_bucket(item: dict) -> int:
    return 1 if item.get("lane") == "blocked" else 4


def test_policy_flip_count_counts_only_actual_changes() -> None:
    assert policy_flip_count([]) == 0
    assert policy_flip_count(["verify-first"]) == 0
    assert policy_flip_count(["verify-first", "verify-first", "monitor"]) == 1


def test_trust_policy_exception_for_target_softens_flip_churn() -> None:
    target = {
        "repo": "RepoA",
        "title": "Fix drift",
        "lane": "urgent",
        "kind": "config",
        "trust_policy": "act-with-review",
        "trust_policy_reason": "Current posture is actionable.",
    }

    status, reason, softened, softened_reason = trust_policy_exception_for_target(
        target,
        {"policy_flip_count": 2, "class_policy_flip_count": 0, "strong_policy_failure_count": 0},
        {"confidence_validation_status": "healthy"},
        current_bucket=_recommendation_bucket(target),
        recommendation_bucket=_recommendation_bucket,
    )

    assert status == "softened-for-flip-churn"
    assert softened == "verify-first"
    assert "verification-aware" in softened_reason
    assert "trust-policy flips" in reason


def test_build_trust_policy_events_includes_current_and_history() -> None:
    current_target = {
        "repo": "RepoA",
        "title": "Fix drift",
        "lane": "urgent",
        "kind": "config",
        "trust_policy": "verify-first",
        "decision_memory_status": "reopened",
        "last_outcome": "reopened",
    }
    history = [
        {
            "generated_at": "2026-01-01T00:00:00Z",
            "operator_summary": {
                "primary_target": {
                    "repo": "RepoB",
                    "title": "Stabilize setup",
                    "lane": "blocked",
                    "kind": "setup",
                },
                "primary_target_trust_policy": "act-now",
                "decision_memory_status": "persisting",
                "primary_target_last_outcome": "no-change",
            },
        }
    ]

    events = build_trust_policy_events(
        history,
        current_primary_target=current_target,
        current_generated_at="2026-01-02T00:00:00Z",
        queue_identity=_queue_identity,
        target_class_key=_target_class_key,
        target_label=_target_label,
        history_window_runs=10,
    )

    assert events[0]["key"] == "RepoA:Fix drift"
    assert events[1]["key"] == "RepoB:Stabilize setup"


def test_false_positive_exception_hotspots_prefers_highest_overcautious_group() -> None:
    hotspots = false_positive_exception_hotspots(
        [
            {
                "key": "RepoA:Fix drift",
                "label": "RepoA: Fix drift",
                "class_key": "urgent:config",
                "trust_exception_status": "softened-for-noise",
                "case_outcome": "overcautious",
            },
            {
                "key": "RepoA:Fix drift",
                "label": "RepoA: Fix drift",
                "class_key": "urgent:config",
                "trust_exception_status": "softened-for-flip-churn",
                "case_outcome": "overcautious",
            },
            {
                "key": "RepoB:Fix setup",
                "label": "RepoB: Fix setup",
                "class_key": "blocked:setup",
                "trust_exception_status": "softened-for-noise",
                "case_outcome": "useful-caution",
            },
        ]
    )

    assert hotspots[0]["label"] == "RepoA: Fix drift"
    assert hotspots[0]["overcautious_count"] == 2
