from __future__ import annotations

from src.operator_trend_class_transitions import (
    build_class_reweight_events,
    build_class_transition_events,
    consecutive_transition_runs,
    current_transition_strengthening,
    pending_transition_direction,
    target_class_transition_history,
)


def _queue_identity(item: dict) -> str:
    return f"{item.get('repo', '')}:{item.get('title', '')}"


def _target_class_key(item: dict) -> str:
    return f"{item.get('lane', '')}:{item.get('kind', '') or 'unknown'}"


def _target_label(item: dict) -> str:
    repo = item.get("repo", "")
    title = item.get("title", "")
    return f"{repo}: {title}" if repo else title


def _normalized_class_reweight_direction(direction: str, score: float) -> str:
    normalized = (direction or "neutral").strip().lower()
    if normalized in {"supporting-normalization", "supporting-caution", "neutral"}:
        return normalized
    if score >= 0.1:
        return "supporting-normalization"
    if score <= -0.1:
        return "supporting-caution"
    return "neutral"


def _clamp_round(value: float) -> float:
    return round(max(-0.95, min(0.95, value)), 2)


def _policy_flip_count(policies: list[str]) -> int:
    flips = 0
    previous = None
    for policy in policies:
        if previous is not None and policy != previous:
            flips += 1
        previous = policy
    return flips


def test_build_class_reweight_events_includes_current_and_history() -> None:
    current_target = {
        "repo": "RepoA",
        "title": "Fix drift",
        "lane": "urgent",
        "kind": "config",
        "trust_policy": "verify-first",
        "class_trust_reweight_score": 0.45,
        "class_trust_reweight_direction": "supporting-normalization",
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
                "primary_target_class_trust_reweight_score": -0.25,
                "primary_target_class_trust_reweight_direction": "supporting-caution",
            },
        }
    ]

    events = build_class_reweight_events(
        history,
        current_primary_target=current_target,
        current_generated_at="2026-01-02T00:00:00Z",
        queue_identity=_queue_identity,
        target_class_key=_target_class_key,
        target_label=_target_label,
        history_window_runs=10,
    )

    assert events[0]["key"] == "RepoA:Fix drift"
    assert events[0]["class_trust_reweight_score"] == 0.45
    assert events[1]["key"] == "RepoB:Stabilize setup"
    assert events[1]["class_trust_reweight_direction"] == "supporting-caution"


def test_build_class_transition_events_reads_summary_fields() -> None:
    history = [
        {
            "generated_at": "2026-01-01T00:00:00Z",
            "operator_summary": {
                "primary_target": {
                    "repo": "RepoA",
                    "title": "Fix drift",
                    "lane": "urgent",
                    "kind": "config",
                    "trust_policy": "verify-first",
                },
                "primary_target_trust_policy": "act-with-review",
                "primary_target_class_reweight_transition_status": "pending-support",
                "primary_target_class_transition_health_status": "healthy",
                "primary_target_class_transition_resolution_status": "progressing",
                "decision_memory_status": "reopened",
                "primary_target_last_outcome": "reopened",
            },
        }
    ]

    events = build_class_transition_events(
        history,
        current_primary_target={},
        current_generated_at="",
        queue_identity=_queue_identity,
        target_class_key=_target_class_key,
        target_label=_target_label,
        history_window_runs=10,
    )

    assert events[0]["trust_policy"] == "act-with-review"
    assert events[0]["class_reweight_transition_status"] == "pending-support"
    assert events[0]["decision_memory_status"] == "reopened"


def test_target_class_transition_history_tracks_pending_support_strengthening() -> None:
    target = {"repo": "RepoA", "title": "Fix drift", "lane": "urgent", "kind": "config"}
    transition_events = [
        {
            "class_key": "urgent:config",
            "class_reweight_transition_status": "pending-support",
            "class_trust_reweight_score": 0.55,
            "class_trust_reweight_direction": "supporting-normalization",
            "class_transition_health_status": "healthy",
            "class_transition_resolution_status": "progressing",
            "trust_policy": "verify-first",
            "decision_memory_status": "persisting",
            "last_outcome": "no-change",
        },
        {
            "class_key": "urgent:config",
            "class_reweight_transition_status": "pending-support",
            "class_trust_reweight_score": 0.42,
            "class_trust_reweight_direction": "supporting-normalization",
            "class_transition_health_status": "watch",
            "class_transition_resolution_status": "progressing",
            "trust_policy": "act-with-review",
            "decision_memory_status": "persisting",
            "last_outcome": "no-change",
        },
    ]

    history_meta = target_class_transition_history(
        target,
        transition_events,
        target_class_key=_target_class_key,
        normalized_class_reweight_direction=_normalized_class_reweight_direction,
        consecutive_transition_runs=consecutive_transition_runs,
        current_transition_strengthening=current_transition_strengthening,
        pending_transition_direction=pending_transition_direction,
        clamp_round=_clamp_round,
        policy_flip_count=_policy_flip_count,
        class_pending_resolution_window_runs=4,
        class_transition_closure_window_runs=3,
    )

    assert history_meta["class_transition_age_runs"] == 2
    assert history_meta["current_transition_strengthening"] is True
    assert history_meta["transition_score_delta"] == 0.13
    assert history_meta["recent_policy_flip_count"] == 1


def test_target_class_transition_history_marks_reversal_after_pending_caution() -> None:
    target = {"repo": "RepoB", "title": "Stabilize setup", "lane": "blocked", "kind": "setup"}
    transition_events = [
        {
            "class_key": "blocked:setup",
            "class_reweight_transition_status": "none",
            "class_trust_reweight_score": 0.05,
            "class_trust_reweight_direction": "supporting-normalization",
            "class_transition_health_status": "watch",
            "class_transition_resolution_status": "none",
            "trust_policy": "verify-first",
            "decision_memory_status": "persisting",
            "last_outcome": "no-change",
        },
        {
            "class_key": "blocked:setup",
            "class_reweight_transition_status": "pending-caution",
            "class_trust_reweight_score": -0.45,
            "class_trust_reweight_direction": "supporting-caution",
            "class_transition_health_status": "watch",
            "class_transition_resolution_status": "progressing",
            "trust_policy": "verify-first",
            "decision_memory_status": "reopened",
            "last_outcome": "reopened",
        },
    ]

    history_meta = target_class_transition_history(
        target,
        transition_events,
        target_class_key=_target_class_key,
        normalized_class_reweight_direction=_normalized_class_reweight_direction,
        consecutive_transition_runs=consecutive_transition_runs,
        current_transition_strengthening=current_transition_strengthening,
        pending_transition_direction=pending_transition_direction,
        clamp_round=_clamp_round,
        policy_flip_count=_policy_flip_count,
        class_pending_resolution_window_runs=4,
        class_transition_closure_window_runs=3,
    )

    assert history_meta["recent_pending_status"] == "pending-caution"
    assert history_meta["recent_pending_age_runs"] == 1
    assert history_meta["current_transition_reversed"] is True
    assert history_meta["current_lost_pending_support"] is True
