from __future__ import annotations

import json
from pathlib import Path

from src.portfolio_truth_trends import build_truth_movement, load_portfolio_truth_history
from src.weekly_command_center import (
    build_weekly_command_center_digest,
    render_weekly_command_center_markdown,
)


def _project(
    name: str,
    *,
    attention: str = "active-infra",
    activity: str = "active",
    risk: str = "baseline",
) -> dict:
    return {
        "identity": {"display_name": name},
        "derived": {"attention_state": attention, "activity_status": activity},
        "risk": {"risk_tier": risk},
    }


def _write_snapshot(history_dir: Path, stamp: str, projects: list[dict]) -> None:
    (history_dir / f"portfolio-truth-{stamp}.json").write_text(
        json.dumps({"generated_at": f"{stamp}T12:00:00Z", "projects": projects}),
        encoding="utf-8",
    )


def _repo_record(movement: dict, name: str) -> dict:
    return next(repo for repo in movement["repos"] if repo["repo"] == name)


def test_truth_movement_reports_no_movement_and_activity_streaks(tmp_path: Path) -> None:
    _write_snapshot(tmp_path, "2026-04-01", [_project("RepoA")])
    _write_snapshot(tmp_path, "2026-04-02", [_project("RepoA")])
    _write_snapshot(tmp_path, "2026-04-03", [_project("RepoA")])

    movement = build_truth_movement(tmp_path)

    assert movement["history_window_runs"] == 3
    assert movement["summary"] == "No movement in the last 3 snapshot(s)."
    assert _repo_record(movement, "RepoA")["activity_status_streaks"] == [
        {
            "status": "active",
            "start_date": "2026-04-01",
            "end_date": "2026-04-03",
            "runs": 3,
        }
    ]


def test_truth_movement_reports_lane_activity_and_risk_transitions(tmp_path: Path) -> None:
    _write_snapshot(
        tmp_path,
        "2026-04-01",
        [_project("RepoA", attention="decision-needed", risk="baseline")],
    )
    _write_snapshot(
        tmp_path,
        "2026-04-02",
        [_project("RepoA", attention="active-infra", activity="stale", risk="elevated")],
    )

    movement = build_truth_movement(tmp_path)
    repo = _repo_record(movement, "RepoA")

    assert repo["attention_lane_transitions"] == [
        {"from": "decision-needed", "to": "active-infra", "date": "2026-04-02"}
    ]
    assert repo["activity_status_transitions"] == [
        {"from": "active", "to": "stale", "date": "2026-04-02"}
    ]
    assert repo["risk_tier_changes"] == [
        {"from": "baseline", "to": "elevated", "date": "2026-04-02"}
    ]
    assert movement["summary"] == (
        "1 repo slid active→stale; 1 repo recovered decision-needed→active-infra; "
        "1 repo risk rose baseline→elevated."
    )


def test_truth_movement_does_not_fake_transitions_for_appearing_or_disappearing_repos(
    tmp_path: Path,
) -> None:
    _write_snapshot(tmp_path, "2026-04-01", [_project("RepoA"), _project("RepoGone")])
    _write_snapshot(tmp_path, "2026-04-02", [_project("RepoA"), _project("RepoNew")])
    _write_snapshot(
        tmp_path,
        "2026-04-03",
        [_project("RepoA"), _project("RepoNew", activity="stale")],
    )

    movement = build_truth_movement(tmp_path)

    gone = _repo_record(movement, "RepoGone")
    new = _repo_record(movement, "RepoNew")
    assert gone["attention_lane_transitions"] == []
    assert gone["activity_status_transitions"] == []
    assert new["attention_lane_transitions"] == []
    assert new["activity_status_transitions"] == [
        {"from": "active", "to": "stale", "date": "2026-04-03"}
    ]


def test_weekly_digest_renders_movement_section_from_history(tmp_path: Path) -> None:
    _write_snapshot(
        tmp_path,
        "2026-04-01",
        [_project("RepoA", attention="decision-needed")],
    )
    _write_snapshot(tmp_path, "2026-04-02", [_project("RepoA")])
    report_data = {
        "username": "testuser",
        "generated_at": "2026-04-02T12:00:00+00:00",
        "operator_summary": {"decision_quality_v1": {}},
        "audits": [],
    }
    digest = build_weekly_command_center_digest(
        report_data,
        {"operator_summary": report_data["operator_summary"], "operator_queue": []},
        portfolio_truth={"projects": []},
        portfolio_truth_history_dir=tmp_path,
    )

    assert digest["movement"]["summary"] == "1 repo recovered decision-needed→active-infra."
    rendered = render_weekly_command_center_markdown(digest)
    assert "## Movement" in rendered
    assert "recovered decision-needed→active-infra" in rendered


def test_history_loader_limits_to_last_n_valid_artifacts(tmp_path: Path) -> None:
    _write_snapshot(tmp_path, "2026-04-01", [_project("RepoA")])
    _write_snapshot(tmp_path, "2026-04-02", [_project("RepoA")])
    _write_snapshot(tmp_path, "2026-04-03", [_project("RepoA")])
    (tmp_path / "portfolio-truth-invalid.json").write_text("not json", encoding="utf-8")

    history = load_portfolio_truth_history(tmp_path, max_runs=2)

    assert [item["generated_at"] for item in history] == [
        "2026-04-02T12:00:00Z",
        "2026-04-03T12:00:00Z",
    ]
