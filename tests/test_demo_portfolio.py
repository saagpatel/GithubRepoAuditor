"""Contract tests for the public-safe synthetic demo portfolio.

These assert the properties the downstream consumer depends on: current schema,
fresh timestamp, receipt-backed coverage that survives the consumer's gate, and
rollups that agree with the per-project records. A fixture that violates any of
them renders as UNKNOWN or stale in the app, which is worse than no demo.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.automation_proposals import VALID_ACTION_TYPES, VALID_STATUSES
from src.demo_portfolio import (
    DEMO_PROJECTS,
    FRESH_OFFSET_HOURS,
    HISTORY_POINTS,
    STALE_RECEIPT_AGE_HOURS,
    build_projects,
    build_proposals,
    build_security_burndown,
    build_snapshot,
    build_weekly_digest,
    fixture_generated_at,
    history_snapshots,
    resolved_coverage_state,
)
from src.github_security_coverage import (
    GITHUB_SECURITY_RECEIPT_SCHEMA_VERSION,
    PROVIDER_NAMES,
    _provider_result,
)
from src.portfolio_truth_types import (
    SCHEMA_VERSION,
    TRUTH_LATEST_FILENAME,
    VALID_ACTIVITY_STATUS,
    VALID_ATTENTION_STATES,
    VALID_CONTEXT_QUALITY,
)
from src.portfolio_truth_reconcile import _build_security_fields
from src.portfolio_truth_validate import validate_truth_snapshot_payload

# Portfolio Command Center reads anything older than this as no longer fresh.
CONSUMER_FRESH_WINDOW_HOURS = 48

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
DEMO_OUTPUT_DIR = Path("output/demo")


def _snapshot() -> dict:
    return build_snapshot(fixture_generated_at(NOW))


def test_schema_version_tracks_the_producer_constant() -> None:
    assert _snapshot()["schema_version"] == SCHEMA_VERSION


def test_envelope_collection_shapes_match_the_canonical_serializer() -> None:
    snapshot = _snapshot()

    assert snapshot["inputs"] == {
        "catalog": {
            "source_id": "portfolio-catalog",
            "sha256": None,
            "observed_at": snapshot["generated_at"],
        },
        "workspace": {
            "source_id": "projects-root",
            "observed_at": snapshot["generated_at"],
        },
        "notion": {
            "mode": "unavailable",
            "observed_at": None,
            "carried_from_generated_at": None,
        },
    }
    assert snapshot["exclusions"] == {
        "policy_version": "workspace_discovery.v2",
        "counts": {},
    }
    assert snapshot["producer"] == {}
    validate_truth_snapshot_payload(snapshot)


def test_committed_demo_truth_artifacts_match_the_canonical_envelope() -> None:
    paths = [DEMO_OUTPUT_DIR / TRUTH_LATEST_FILENAME]
    paths.extend(
        DEMO_OUTPUT_DIR / f"portfolio-truth-history-{index:02d}.json"
        for index in range(1, HISTORY_POINTS + 1)
    )

    for path in paths:
        snapshot = json.loads(path.read_text())
        generated_at = snapshot["generated_at"]
        assert snapshot["inputs"] == {
            "catalog": {
                "source_id": "portfolio-catalog",
                "sha256": None,
                "observed_at": generated_at,
            },
            "workspace": {
                "source_id": "projects-root",
                "observed_at": generated_at,
            },
            "notion": {
                "mode": "unavailable",
                "observed_at": None,
                "carried_from_generated_at": None,
            },
        }
        assert snapshot["exclusions"] == {
            "policy_version": "workspace_discovery.v2",
            "counts": {},
        }
        assert snapshot["producer"] == {}
        validate_truth_snapshot_payload(snapshot)

        raw = path.read_text().lower()
        for forbidden in ("/users/", "saagpatel", "saagar", "@gmail.com", "gmail"):
            assert forbidden not in raw


def test_generated_at_lands_inside_the_consumer_fresh_window() -> None:
    generated_at = datetime.fromisoformat(_snapshot()["generated_at"])
    age_hours = (NOW - generated_at).total_seconds() / 3600

    assert age_hours == FRESH_OFFSET_HOURS
    assert 0 < age_hours < CONSUMER_FRESH_WINDOW_HOURS


def test_portfolio_is_broad_enough_to_demonstrate_the_app() -> None:
    projects = _snapshot()["projects"]

    assert len(projects) == len(DEMO_PROJECTS)
    assert len(projects) >= 30
    assert len({p["identity"]["project_key"] for p in projects}) == len(projects)


def test_every_project_uses_known_enum_values() -> None:
    for project in _snapshot()["projects"]:
        derived = project["derived"]
        assert derived["attention_state"] in VALID_ATTENTION_STATES
        assert derived["activity_status"] in VALID_ACTIVITY_STATUS
        assert derived["context_quality"] in VALID_CONTEXT_QUALITY
        assert project["risk"]["risk_tier"] in {
            "elevated",
            "moderate",
            "baseline",
            "deferred",
        }


def test_coverage_states_span_the_whole_receipt_model() -> None:
    states = [resolved_coverage_state(p["security"]) for p in _snapshot()["projects"]]

    for state in ("complete", "partial", "stale", "unknown"):
        assert states.count(state) > 0, f"no {state} coverage row in the fixture"


def test_declared_complete_rows_survive_the_consumer_receipt_gate() -> None:
    """A complete row whose receipt does not hold up degrades to UNKNOWN."""
    for project in _snapshot()["projects"]:
        security = project["security"]
        if security["coverage_state"] != "complete":
            continue
        assert security["receipt_schema_version"] == (
            GITHUB_SECURITY_RECEIPT_SCHEMA_VERSION
        )
        assert security["receipt_state"] == "fresh"
        for name in ("dependabot", "code_scanning", "secret_scanning"):
            provider = security["providers"][name]
            assert provider["state"] == "observed"
            assert provider["pagination_complete"] is True
            assert isinstance(provider["counts"], dict)
        assert resolved_coverage_state(security) == "complete"


def test_stale_rows_are_older_than_the_receipt_freshness_window() -> None:
    snapshot = _snapshot()
    generated_at = datetime.fromisoformat(snapshot["generated_at"])

    for project in snapshot["projects"]:
        security = project["security"]
        if security["coverage_state"] != "stale":
            continue
        source_produced_at = datetime.fromisoformat(security["source_produced_at"])
        age_hours = (generated_at - source_produced_at).total_seconds() / 3600

        assert age_hours == STALE_RECEIPT_AGE_HOURS
        assert age_hours > 24
        assert set(security["providers"]) == set(PROVIDER_NAMES)
        for name in PROVIDER_NAMES:
            assert security["providers"][name] == _provider_result(
                name,
                state="stale",
                observed_at=security["source_produced_at"],
                http_status=200,
                reason="receipt_stale",
                pagination_complete=True,
                conditional_request=True,
                conditional_result="modified",
                http_classification="success",
            )
        assert _build_security_fields(security).to_dict() == security


def test_unknown_rows_carry_no_receipt_evidence() -> None:
    for project in _snapshot()["projects"]:
        security = project["security"]
        if security["coverage_state"] != "unknown":
            continue
        assert security["providers"] == {}
        assert security["receipt_schema_version"] == ""
        assert security["dependabot_high"] is None


def test_rollups_agree_with_the_project_records() -> None:
    snapshot = _snapshot()
    projects = snapshot["projects"]
    security = snapshot["rollups"]["security"]

    assert sum(snapshot["rollups"]["risk_tier_counts"].values()) == len(projects)
    assert snapshot["source_summary"]["project_count"] == len(projects)
    assert snapshot["rollups"]["decision"]["decision_needed_count"] == sum(
        1 for p in projects if p["derived"]["attention_state"] == "decision-needed"
    )
    for state, field in (
        ("complete", "complete_repo_count"),
        ("partial", "partial_repo_count"),
        ("stale", "stale_count"),
        ("unknown", "unknown_count"),
    ):
        assert security[field] == sum(
            1 for p in projects if resolved_coverage_state(p["security"]) == state
        )


def test_risk_text_and_tiers_use_canonical_dependabot_alert_counts() -> None:
    snapshot = _snapshot()
    repos_with_open_high_critical = 0

    for project in snapshot["projects"]:
        security = project["security"]
        risk = project["risk"]
        canonical_count = (security["dependabot_critical"] or 0) + (
            security["dependabot_high"] or 0
        )
        factor = f"{canonical_count} open high/critical security alerts"

        assert security["open_high_critical"] == canonical_count
        assert risk["security_risk"] is (canonical_count > 0)
        assert (factor in risk["risk_factors"]) is (canonical_count > 0)
        if canonical_count > 0:
            repos_with_open_high_critical += 1
            assert risk["risk_tier"] == "elevated"

    assert snapshot["rollups"]["security"][
        "repos_with_open_high_critical"
    ] == repos_with_open_high_critical


def test_attention_state_counts_match_the_project_records() -> None:
    snapshot = _snapshot()
    counts = snapshot["source_summary"]["attention_state_counts"]

    for state, count in counts.items():
        assert count == sum(
            1 for p in snapshot["projects"] if p["derived"]["attention_state"] == state
        )


def test_history_gives_the_trends_view_a_real_curve() -> None:
    snapshots = history_snapshots(fixture_generated_at(NOW))

    assert len(snapshots) == HISTORY_POINTS
    assert len({name for name, _ in snapshots}) == HISTORY_POINTS

    timestamps = [datetime.fromisoformat(s["generated_at"]) for _, s in snapshots]
    assert timestamps == sorted(timestamps)
    assert len(set(timestamps)) == len(timestamps)
    assert all(s["schema_version"] == SCHEMA_VERSION for _, s in snapshots)
    for _, snapshot in snapshots:
        validate_truth_snapshot_payload(snapshot)

    # Backlog pressure decays toward the present, so the curve actually moves.
    open_high = [s["rollups"]["security"]["total_open_high"] for _, s in snapshots]
    assert open_high[0] > open_high[-1]


def test_backlog_pressure_never_invents_counts_for_unobserved_rows() -> None:
    pressured = build_projects(fixture_generated_at(NOW), pressure=8)

    for project in pressured:
        if resolved_coverage_state(project["security"]) in {"stale", "unknown"}:
            assert project["security"]["dependabot_high"] is None


def test_proposals_present_a_mixed_state_triage_queue() -> None:
    queue = build_proposals(fixture_generated_at(NOW))
    proposals = queue["proposals"]

    assert queue["contract_version"] == "automation_proposals_v1"
    assert len(proposals) >= 3
    assert {p["status"] for p in proposals} == VALID_STATUSES
    assert all(p["action_type"] in VALID_ACTION_TYPES for p in proposals)
    assert len({p["proposal_id"] for p in proposals}) == len(proposals)


def test_weekly_digest_and_burndown_agree_with_the_snapshot() -> None:
    snapshot = _snapshot()
    digest = build_weekly_digest(snapshot)
    burndown = build_security_burndown(snapshot)

    assert digest["generated_at"] == snapshot["generated_at"]
    assert (
        digest["risk_posture"]["risk_tier_counts"]
        == (snapshot["rollups"]["risk_tier_counts"])
    )
    assert (
        digest["security_posture"]["total_open_high"]
        == (snapshot["rollups"]["security"]["total_open_high"])
    )
    assert burndown["repos_touched"] == sum(
        1
        for p in snapshot["projects"]
        if (p["security"]["open_high_critical"] or 0) > 0
    )
    assert all(
        entry["ghsa_id"].startswith("GHSA-DEMO-") for entry in burndown["entries"]
    )


def test_fixture_carries_no_operator_identifying_strings() -> None:
    """The whole point of the fixture is that it is safe to publish."""
    payload = json.dumps(
        [
            _snapshot(),
            build_proposals(fixture_generated_at(NOW)),
            build_weekly_digest(_snapshot()),
        ]
    ).lower()

    for forbidden in ("/users/", "saagpatel", "saagar", "@gmail.com", "gmail"):
        assert forbidden not in payload


def test_history_timestamps_stay_behind_the_published_snapshot() -> None:
    generated_at = fixture_generated_at(NOW)
    newest = max(
        datetime.fromisoformat(s["generated_at"])
        for _, s in history_snapshots(generated_at)
    )

    assert newest == generated_at
    assert newest < NOW
    assert newest > NOW - timedelta(hours=CONSUMER_FRESH_WINDOW_HOURS)
