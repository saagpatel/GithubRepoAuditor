from __future__ import annotations

from src.operator_trend_confidence_calibration import build_confidence_calibration


def _queue_identity(item: dict) -> str:
    return f"{item.get('repo', '')}:{item.get('title', '')}"


def _target_label(item: dict) -> str:
    repo = item.get("repo", "")
    title = item.get("title", "")
    return f"{repo}: {title}" if repo else title


def _run(
    run_id: str,
    generated_at: str,
    *,
    target: dict | None,
    confidence_label: str = "high",
    queue: list[dict] | None = None,
) -> dict:
    summary = {}
    if target is not None:
        summary = {
            "primary_target": target,
            "primary_target_confidence_label": confidence_label,
        }
    return {
        "run_id": run_id,
        "generated_at": generated_at,
        "operator_summary": summary,
        "operator_queue": queue or [],
    }


def test_build_confidence_calibration_marks_healthy_when_high_confidence_validates() -> None:
    target_a = {"repo": "RepoA", "title": "Fix A", "lane": "blocked"}
    target_b = {"repo": "RepoB", "title": "Fix B", "lane": "blocked"}
    target_c = {"repo": "RepoC", "title": "Fix C", "lane": "blocked"}
    target_d = {"repo": "RepoD", "title": "Fix D", "lane": "blocked"}
    history = [
        _run("run-1", "2026-01-01T00:00:00Z", target=target_a, queue=[target_a]),
        _run("run-2", "2026-01-02T00:00:00Z", target=target_b, queue=[target_b]),
        _run("run-3", "2026-01-03T00:00:00Z", target=target_c, queue=[target_c]),
        _run("run-4", "2026-01-04T00:00:00Z", target=target_d, queue=[target_d]),
        _run("run-5", "2026-01-05T00:00:00Z", target=None, queue=[]),
        _run("run-6", "2026-01-06T00:00:00Z", target=None, queue=[]),
    ]

    calibration = build_confidence_calibration(
        history,
        queue_identity=_queue_identity,
        target_label=_target_label,
    )

    assert calibration["confidence_validation_status"] == "healthy"
    assert calibration["validated_recommendation_count"] == 4
    assert calibration["reopened_recommendation_count"] == 0
    assert calibration["high_confidence_hit_rate"] == 1.0


def test_build_confidence_calibration_marks_noisy_when_reopens_repeat() -> None:
    target_a = {"repo": "RepoA", "title": "Fix A", "lane": "blocked"}
    target_b = {"repo": "RepoB", "title": "Fix B", "lane": "blocked"}
    target_c = {"repo": "RepoC", "title": "Fix C", "lane": "blocked"}
    target_d = {"repo": "RepoD", "title": "Fix D", "lane": "blocked"}
    history = [
        _run("run-1", "2026-02-01T00:00:00Z", target=target_a, queue=[target_a]),
        _run("run-2", "2026-02-02T00:00:00Z", target=target_b, queue=[target_b]),
        _run("run-3", "2026-02-03T00:00:00Z", target=target_c, queue=[target_a, target_c]),
        _run("run-4", "2026-02-04T00:00:00Z", target=target_d, queue=[target_b, target_d]),
        _run("run-5", "2026-02-05T00:00:00Z", target=None, queue=[target_c]),
        _run("run-6", "2026-02-06T00:00:00Z", target=None, queue=[target_d]),
    ]

    calibration = build_confidence_calibration(
        history,
        queue_identity=_queue_identity,
        target_label=_target_label,
    )

    assert calibration["confidence_validation_status"] == "noisy"
    assert calibration["reopened_recommendation_count"] == 4
    assert calibration["high_confidence_hit_rate"] == 0.0
    assert "noisy" in calibration["confidence_calibration_summary"]
