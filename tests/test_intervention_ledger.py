from __future__ import annotations

from pathlib import Path

from src.intervention_ledger import build_intervention_ledger_bundle


def _queue_item(repo: str, *, lane: str = "ready") -> dict:
    return {
        "repo": repo,
        "repo_name": repo,
        "lane": lane,
        "title": f"Review {repo}",
    }


def _snapshot(run_id: str, generated_at: str, queue: list[dict] | None = None) -> dict:
    return {
        "run_id": run_id,
        "generated_at": generated_at,
        "operator_summary": {},
        "operator_queue": list(queue or []),
    }


def _action_run(
    run_id: str,
    generated_at: str,
    repo: str,
    *,
    campaign_type: str = "security-review",
    reopened_at: str | None = None,
) -> dict:
    return {
        "run_id": run_id,
        "generated_at": generated_at,
        "repo": repo,
        "repo_id": f"user/{repo}",
        "repo_full_name": f"user/{repo}",
        "campaign_type": campaign_type,
        "reopened_at": reopened_at,
    }


def _score_row(repo: str, generated_at: str, score: float) -> dict:
    return {
        "repo": repo,
        "generated_at": generated_at,
        "score": score,
    }


def _hotspot_row(run_id: str, generated_at: str, repo: str, path: str = "src/core.py") -> dict:
    return {
        "run_id": run_id,
        "generated_at": generated_at,
        "repo": repo,
        "path": path,
        "category": "code-complexity",
        "pressure_score": 0.72,
        "suggestion_type": "refactor",
    }


def _campaign_outcome(campaign_type: str, monitoring_state: str) -> dict:
    return {
        "campaign_type": campaign_type,
        "monitoring_state": monitoring_state,
    }


def _report(repo: str = "RepoAlpha", *, lane: str = "ready", include_queue: bool = True) -> dict:
    return {
        "username": "testuser",
        "generated_at": "2026-04-13T12:00:00+00:00",
        "audits": [
            {
                "metadata": {"name": repo},
                "overall_score": 0.61,
                "completeness_tier": "functional",
                "scorecard": {"score": 0.61},
            }
        ],
        "operator_queue": [_queue_item(repo, lane=lane)] if include_queue else [],
        "operator_summary": {},
    }


def _record(bundle: dict, repo: str) -> dict:
    return next(item for item in bundle["historical_portfolio_intelligence"] if item["repo"] == repo)


def test_intervention_ledger_marks_insufficient_evidence_when_history_is_thin() -> None:
    bundle = build_intervention_ledger_bundle(_report())
    record = _record(bundle, "RepoAlpha")

    assert record["historical_intelligence_status"] == "insufficient-evidence"
    assert bundle["next_historical_focus"]["summary"].startswith("Stay local for now")


def test_intervention_ledger_marks_relapsing_when_operator_evidence_reopens() -> None:
    bundle = build_intervention_ledger_bundle(
        _report(lane="urgent"),
        recent_runs=[
            _snapshot("run-3", "2026-04-13T09:00:00+00:00", [_queue_item("RepoAlpha", lane="ready")]),
            _snapshot("run-2", "2026-04-13T10:00:00+00:00", [_queue_item("RepoAlpha", lane="ready")]),
            _snapshot("run-1", "2026-04-13T11:00:00+00:00", [_queue_item("RepoAlpha", lane="urgent")]),
        ],
        operator_evidence={
            "history": [],
            "events": [{"repo": "RepoAlpha", "outcome": "reopened"}],
        },
        recent_action_runs=[
            _action_run("run-apply", "2026-04-13T08:00:00+00:00", "RepoAlpha"),
        ],
    )
    record = _record(bundle, "RepoAlpha")

    assert record["historical_intelligence_status"] == "relapsing"
    assert bundle["next_historical_focus"]["repo"] == "RepoAlpha"


def test_intervention_ledger_marks_persistent_pressure_when_pressure_and_hotspots_repeat() -> None:
    bundle = build_intervention_ledger_bundle(
        _report(lane="ready"),
        recent_runs=[
            _snapshot("run-3", "2026-04-13T09:00:00+00:00", [_queue_item("RepoAlpha", lane="ready")]),
            _snapshot("run-2", "2026-04-13T10:00:00+00:00", [_queue_item("RepoAlpha", lane="ready")]),
            _snapshot("run-1", "2026-04-13T11:00:00+00:00", [_queue_item("RepoAlpha", lane="ready")]),
        ],
        implementation_hotspot_history=[
            _hotspot_row("run-3", "2026-04-13T09:00:00+00:00", "RepoAlpha"),
            _hotspot_row("run-2", "2026-04-13T10:00:00+00:00", "RepoAlpha"),
            _hotspot_row("run-1", "2026-04-13T11:00:00+00:00", "RepoAlpha"),
        ],
        repo_scorecard_history=[
            _score_row("RepoAlpha", "2026-04-13T09:00:00+00:00", 0.62),
            _score_row("RepoAlpha", "2026-04-13T10:00:00+00:00", 0.61),
            _score_row("RepoAlpha", "2026-04-13T11:00:00+00:00", 0.61),
            _score_row("RepoAlpha", "2026-04-13T12:00:00+00:00", 0.60),
        ],
    )
    record = _record(bundle, "RepoAlpha")

    assert record["historical_intelligence_status"] == "persistent-pressure"
    assert record["hotspot_persistence"] == "persistent"


def test_intervention_ledger_marks_improving_after_intervention_when_pressure_and_score_trend_improve() -> None:
    bundle = build_intervention_ledger_bundle(
        _report(lane="deferred", include_queue=False),
        recent_runs=[
            _snapshot("run-3", "2026-04-13T09:00:00+00:00", [_queue_item("RepoAlpha", lane="blocked")]),
            _snapshot("run-2", "2026-04-13T10:00:00+00:00", [_queue_item("RepoAlpha", lane="urgent")]),
            _snapshot("run-1", "2026-04-13T11:00:00+00:00", []),
        ],
        recent_action_runs=[
            _action_run("run-apply", "2026-04-13T08:00:00+00:00", "RepoAlpha"),
        ],
        repo_scorecard_history=[
            _score_row("RepoAlpha", "2026-04-13T09:00:00+00:00", 0.40),
            _score_row("RepoAlpha", "2026-04-13T10:00:00+00:00", 0.48),
            _score_row("RepoAlpha", "2026-04-13T11:00:00+00:00", 0.55),
            _score_row("RepoAlpha", "2026-04-13T12:00:00+00:00", 0.63),
        ],
    )
    record = _record(bundle, "RepoAlpha")

    assert record["historical_intelligence_status"] == "improving-after-intervention"
    assert record["scorecard_trend"] == "improving"
    assert record["pressure_trend"] == "improving"


def test_intervention_ledger_marks_holding_steady_when_earlier_intervention_is_quieting() -> None:
    bundle = build_intervention_ledger_bundle(
        _report(lane="deferred", include_queue=False),
        recent_runs=[
            _snapshot("run-3", "2026-04-13T09:00:00+00:00", []),
            _snapshot("run-2", "2026-04-13T10:00:00+00:00", []),
            _snapshot("run-1", "2026-04-13T11:00:00+00:00", []),
        ],
        recent_action_runs=[
            _action_run("run-apply", "2026-04-13T08:00:00+00:00", "RepoAlpha"),
        ],
        implementation_hotspot_history=[
            _hotspot_row("run-3", "2026-04-13T09:00:00+00:00", "RepoAlpha"),
            _hotspot_row("run-2", "2026-04-13T10:00:00+00:00", "RepoAlpha"),
            _hotspot_row("run-1", "2026-04-13T11:00:00+00:00", "RepoAlpha"),
        ],
    )
    record = _record(bundle, "RepoAlpha")

    assert record["historical_intelligence_status"] == "holding-steady"
    assert record["pressure_trend"] == "flat"


def test_intervention_ledger_marks_quiet_when_repo_has_no_active_pressure_story() -> None:
    bundle = build_intervention_ledger_bundle(
        _report(lane="deferred", include_queue=False),
        recent_runs=[
            _snapshot("run-3", "2026-04-13T09:00:00+00:00", []),
            _snapshot("run-2", "2026-04-13T10:00:00+00:00", []),
            _snapshot("run-1", "2026-04-13T11:00:00+00:00", []),
        ],
    )
    record = _record(bundle, "RepoAlpha")

    assert record["historical_intelligence_status"] == "quiet"
    assert record["hotspot_persistence"] == "quiet"


def test_intervention_ledger_uses_campaign_follow_through_as_supporting_signal() -> None:
    bundle = build_intervention_ledger_bundle(
        _report(lane="ready"),
        recent_runs=[
            _snapshot("run-3", "2026-04-13T09:00:00+00:00", [_queue_item("RepoAlpha", lane="ready")]),
            _snapshot("run-2", "2026-04-13T10:00:00+00:00", []),
            _snapshot("run-1", "2026-04-13T11:00:00+00:00", []),
        ],
        recent_action_runs=[
            _action_run("run-apply", "2026-04-13T08:00:00+00:00", "RepoAlpha", campaign_type="security-review"),
        ],
        campaign_outcomes=[
            _campaign_outcome("security-review", "holding-clean"),
        ],
    )
    record = _record(bundle, "RepoAlpha")

    assert record["campaign_follow_through"] == "helping"
    assert record["historical_intelligence_status"] == "improving-after-intervention"


def test_intervention_ledger_docs_explain_historical_portfolio_intelligence() -> None:
    architecture = Path("docs/architecture.md").read_text()
    modes = Path("docs/modes.md").read_text()
    weekly = Path("docs/weekly-review.md").read_text()

    combined = "\n".join([architecture, modes, weekly])

    assert "Historical Portfolio Intelligence" in combined
    assert "Intervention Ledger" in combined
    assert "current-state portfolio intelligence" in architecture or "current-state portfolio layer" in architecture
