from __future__ import annotations

import json
from pathlib import Path

from src.portfolio_truth_trends import (
    build_verdict_transition_ledger,
    render_movement_summary,
)
from src.weekly_command_center import (
    build_weekly_command_center_digest,
    render_weekly_command_center_markdown,
)


def _project(
    name: str,
    *,
    attention: str = "active-product",
    activity: str = "active",
    risk: str = "baseline",
) -> dict:
    return {
        "identity": {"project_key": name.lower(), "display_name": name},
        "derived": {
            "attention_state": attention,
            "activity_status": activity,
        },
        "risk": {"risk_tier": risk},
    }


def _write_snapshot(directory: Path, stamp: str, projects: list[dict]) -> dict:
    snapshot = {
        "generated_at": f"{stamp}T12:00:00+00:00",
        "projects": projects,
    }
    (directory / f"portfolio-truth-{stamp.replace('-', '')}T120000Z.json").write_text(
        json.dumps(snapshot)
    )
    return snapshot


def test_transition_ledger_reports_no_movement_and_activity_streaks(tmp_path: Path) -> None:
    _write_snapshot(tmp_path, "2026-07-10", [_project("Steady")])
    _write_snapshot(tmp_path, "2026-07-11", [_project("Steady")])

    ledger = build_verdict_transition_ledger(tmp_path)

    assert ledger["snapshot_count"] == 2
    assert ledger["transitions"] == []
    assert ledger["summary"]["transition_count"] == 0
    assert ledger["activity_status_streaks"] == [
        {
            "repo": "Steady",
            "project_key": "steady",
            "status": "active",
            "run_count": 2,
            "consecutive_snapshots": 2,
            "since_generated_at": "2026-07-10T12:00:00+00:00",
            "through_generated_at": "2026-07-11T12:00:00+00:00",
        }
    ]
    assert render_movement_summary(ledger).startswith("No verdict movement")


def test_transition_ledger_reports_attention_activity_and_risk_changes(tmp_path: Path) -> None:
    _write_snapshot(
        tmp_path,
        "2026-07-10",
        [_project("Moving", attention="decision-needed", activity="stale", risk="elevated")],
    )
    current = _write_snapshot(
        tmp_path,
        "2026-07-11",
        [_project("Moving", attention="active-infra", activity="active", risk="baseline")],
    )

    ledger = build_verdict_transition_ledger(
        tmp_path,
        current_snapshot=current,
        current_path=tmp_path / "portfolio-truth-latest.json",
    )

    assert [(item["kind"], item["from"], item["to"]) for item in ledger["transitions"]] == [
        ("activity_status", "stale", "active"),
        ("attention_state", "decision-needed", "active-infra"),
        ("risk_tier", "elevated", "baseline"),
    ]
    assert all(item["from_date"] == "2026-07-10" for item in ledger["transitions"])
    assert all(item["to_date"] == "2026-07-11" for item in ledger["transitions"])
    assert "recovered stale→active" in render_movement_summary(ledger)
    assert "recovered decision-needed→active-infra" in render_movement_summary(ledger)


def test_transition_ledger_reports_repos_appearing_and_disappearing(tmp_path: Path) -> None:
    _write_snapshot(tmp_path, "2026-07-10", [_project("Stays"), _project("Leaves")])
    _write_snapshot(tmp_path, "2026-07-11", [_project("Stays")])
    _write_snapshot(tmp_path, "2026-07-12", [_project("Stays"), _project("Arrives")])

    ledger = build_verdict_transition_ledger(tmp_path)

    lifecycle = {
        (item["repo"], item["from"], item["to"])
        for item in ledger["repo_lifecycle_events"]
    }
    assert lifecycle == {
        ("Leaves", "present", "absent"),
        ("Arrives", "absent", "present"),
    }
    streaks = {item["repo"]: item for item in ledger["activity_status_streaks"]}
    assert streaks["Leaves"]["status"] == "disappeared"
    assert streaks["Arrives"]["run_count"] == 1
    assert ledger["summary"]["repo_appeared_count"] == 1
    assert ledger["summary"]["repo_disappeared_count"] == 1


def test_weekly_digest_surfaces_movement_section(tmp_path: Path) -> None:
    _write_snapshot(
        tmp_path,
        "2026-07-10",
        [_project("Moving", attention="decision-needed", activity="stale")],
    )
    current = _write_snapshot(
        tmp_path,
        "2026-07-11",
        [_project("Moving", attention="active-infra", activity="active")],
    )
    report_data = {
        "username": "testuser",
        "generated_at": "2026-07-11T12:00:00+00:00",
        "operator_summary": {"decision_quality_v1": {}},
        "audits": [],
    }
    snapshot = {"operator_summary": report_data["operator_summary"], "operator_queue": []}

    digest = build_weekly_command_center_digest(
        report_data,
        snapshot,
        portfolio_truth=current,
        portfolio_truth_history_dir=tmp_path,
        portfolio_truth_reference=str(tmp_path / "portfolio-truth-latest.json"),
    )
    rendered = render_weekly_command_center_markdown(digest)

    assert digest["movement"]["attention_state_transitions"][0]["repo"] == "Moving"
    assert "recovered decision-needed→active-infra" in digest["movement"]["summary_text"]
    assert "## Movement" in rendered
    assert "Moving" in rendered
    assert "2026-07-11" in rendered
