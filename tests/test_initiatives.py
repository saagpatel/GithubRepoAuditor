"""Tests for src/initiatives.py and CLI wiring — Arc G Sprint 7A.2/7A.3."""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from src.initiatives import (
    Initiative,
    close_initiative,
    derive_status,
    initiatives_path,
    load_initiatives,
    operator_identity,
    save_initiatives,
    upsert_initiative,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _future(days: int = 30) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def _past(days: int = 5) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def _sample_initiative(
    repo_name: str = "Wavelength",
    target_tier: int = 3,
    deadline: str | None = None,
    closed_at: str | None = None,
    closed_reason: str | None = None,
) -> Initiative:
    return Initiative(
        repo_name=repo_name,
        target_tier=target_tier,
        deadline=deadline or _future(30),
        set_at="2026-05-12T10:00:00+00:00",
        set_by="operator",
        closed_at=closed_at,
        closed_reason=closed_reason,
    )


def _repo_at_tier(tier: int) -> dict:
    """Return a minimal portfolio-truth project dict at the given tier (1-3)."""
    from datetime import timedelta as td

    base = {
        "identity": {"display_name": "Wavelength", "has_git": True},
        "derived": {
            "last_meaningful_activity_at": (date.today() - td(days=30)).isoformat(),
            "activity_status": "active",
            "context_quality": "strong",
            "context_files": ["README.md", "LICENSE"],
            "run_instructions_present": True,
        },
        "risk": {
            "risk_tier": "baseline",
            "risk_factors": [],
            "doctor_gap": False,
        },
    }
    if tier < 2:
        # Remove Silver signals
        base["derived"]["run_instructions_present"] = False
        base["risk"]["doctor_gap"] = True
    if tier < 3:
        # Remove Gold signals
        base["derived"]["context_quality"] = "weak"
    return base


# ── initiatives_path ──────────────────────────────────────────────────────────


def test_initiatives_path(tmp_path: Path):
    assert initiatives_path(tmp_path) == tmp_path / "initiatives.json"


# ── load_initiatives ──────────────────────────────────────────────────────────


def test_load_initiatives_missing_file_returns_empty(tmp_path: Path):
    result = load_initiatives(tmp_path / "initiatives.json")
    assert result == []


def test_load_initiatives_empty_file_returns_empty(tmp_path: Path):
    p = tmp_path / "initiatives.json"
    p.write_text("", encoding="utf-8")
    result = load_initiatives(p)
    assert result == []


def test_load_initiatives_malformed_json_returns_empty(tmp_path: Path):
    p = tmp_path / "initiatives.json"
    p.write_text("{invalid json!!", encoding="utf-8")
    result = load_initiatives(p)
    assert result == []


def test_load_initiatives_roundtrip(tmp_path: Path):
    p = tmp_path / "initiatives.json"
    initiative = _sample_initiative()
    save_initiatives(p, [initiative])
    loaded = load_initiatives(p)
    assert len(loaded) == 1
    assert loaded[0].repo_name == "Wavelength"
    assert loaded[0].target_tier == 3


# ── save_initiatives ──────────────────────────────────────────────────────────


def test_save_initiatives_creates_versioned_schema(tmp_path: Path):
    p = tmp_path / "initiatives.json"
    save_initiatives(p, [_sample_initiative()])
    data = json.loads(p.read_text())
    assert data["version"] == 1
    assert "initiatives" in data
    assert len(data["initiatives"]) == 1


def test_save_initiatives_atomic_no_temp_file_left(tmp_path: Path):
    p = tmp_path / "initiatives.json"
    save_initiatives(p, [_sample_initiative()])
    # No .initiatives_tmp_ files should remain
    leftover = list(tmp_path.glob(".initiatives_tmp_*"))
    assert leftover == []


def test_save_initiatives_multiple(tmp_path: Path):
    p = tmp_path / "initiatives.json"
    items = [_sample_initiative("Repo1"), _sample_initiative("Repo2", target_tier=2)]
    save_initiatives(p, items)
    loaded = load_initiatives(p)
    assert len(loaded) == 2
    names = {i.repo_name for i in loaded}
    assert names == {"Repo1", "Repo2"}


# ── upsert_initiative ─────────────────────────────────────────────────────────


def test_upsert_adds_new(tmp_path: Path):
    p = tmp_path / "initiatives.json"
    upsert_initiative(p, _sample_initiative("Alpha"))
    loaded = load_initiatives(p)
    assert len(loaded) == 1
    assert loaded[0].repo_name == "Alpha"


def test_upsert_replaces_open_by_repo_name(tmp_path: Path):
    p = tmp_path / "initiatives.json"
    old = _sample_initiative("Wavelength", target_tier=2, deadline=_future(10))
    upsert_initiative(p, old)
    new = _sample_initiative("Wavelength", target_tier=3, deadline=_future(60))
    upsert_initiative(p, new)
    loaded = load_initiatives(p)
    assert len(loaded) == 1
    assert loaded[0].target_tier == 3
    assert loaded[0].deadline == _future(60)


def test_upsert_preserves_other_repos(tmp_path: Path):
    p = tmp_path / "initiatives.json"
    upsert_initiative(p, _sample_initiative("Alpha"))
    upsert_initiative(p, _sample_initiative("Beta"))
    upsert_initiative(p, _sample_initiative("Alpha", target_tier=4))
    loaded = load_initiatives(p)
    assert len(loaded) == 2
    alpha = next(i for i in loaded if i.repo_name == "Alpha")
    assert alpha.target_tier == 4


def test_upsert_does_not_replace_closed(tmp_path: Path):
    """A closed initiative should not be overwritten by a new upsert."""
    p = tmp_path / "initiatives.json"
    closed = _sample_initiative(
        "Wavelength", closed_at="2026-04-01T00:00:00+00:00", closed_reason="met"
    )
    save_initiatives(p, [closed])
    new_open = _sample_initiative("Wavelength", target_tier=4, deadline=_future(90))
    upsert_initiative(p, new_open)
    loaded = load_initiatives(p)
    # Should now have both the closed one and the new open one
    assert len(loaded) == 2
    open_ones = [i for i in loaded if i.closed_at is None]
    assert len(open_ones) == 1
    assert open_ones[0].target_tier == 4


# ── close_initiative ──────────────────────────────────────────────────────────


def test_close_initiative_marks_closed(tmp_path: Path):
    p = tmp_path / "initiatives.json"
    upsert_initiative(p, _sample_initiative("Wavelength"))
    closed = close_initiative(p, "Wavelength")
    assert closed is not None
    assert closed.closed_at is not None
    assert closed.closed_reason == "met"


def test_close_initiative_persists(tmp_path: Path):
    p = tmp_path / "initiatives.json"
    upsert_initiative(p, _sample_initiative("TideEngine"))
    close_initiative(p, "TideEngine")
    loaded = load_initiatives(p)
    assert loaded[0].closed_at is not None
    assert loaded[0].closed_reason == "met"


def test_close_initiative_not_found_returns_none(tmp_path: Path):
    p = tmp_path / "initiatives.json"
    result = close_initiative(p, "NoSuchRepo")
    assert result is None


def test_close_initiative_second_call_returns_none(tmp_path: Path):
    p = tmp_path / "initiatives.json"
    upsert_initiative(p, _sample_initiative("Repo"))
    close_initiative(p, "Repo")
    result = close_initiative(p, "Repo")  # already closed
    assert result is None


def test_close_initiative_custom_reason(tmp_path: Path):
    p = tmp_path / "initiatives.json"
    upsert_initiative(p, _sample_initiative("X"))
    closed = close_initiative(p, "X", reason="abandoned")
    assert closed is not None
    assert closed.closed_reason == "abandoned"


# ── derive_status ─────────────────────────────────────────────────────────────


def test_derive_status_closed_returns_met():
    initiative = _sample_initiative(closed_at="2026-05-01T00:00:00+00:00", closed_reason="met")
    status = derive_status(initiative, _repo_at_tier(1))
    assert status == "met"


def test_derive_status_tier_reached_returns_met():
    """Current tier >= target tier → met (even if not explicitly closed)."""
    initiative = _sample_initiative("Wavelength", target_tier=2)
    repo = _repo_at_tier(3)  # well above target
    status = derive_status(initiative, repo)
    assert status == "met"


def test_derive_status_overdue():
    initiative = _sample_initiative(deadline=_past(5))
    repo = _repo_at_tier(1)  # below target
    status = derive_status(initiative, repo, today=date.today().isoformat())
    assert status == "overdue"


def test_derive_status_at_risk_within_14_days():
    initiative = _sample_initiative(deadline=_future(7))
    repo = _repo_at_tier(1)
    status = derive_status(initiative, repo)
    assert status == "at-risk"


def test_derive_status_on_track():
    initiative = _sample_initiative(deadline=_future(60))
    repo = _repo_at_tier(1)
    status = derive_status(initiative, repo)
    assert status == "on-track"


def test_derive_status_today_param_respected():
    """Passing an explicit today date controls overdue/at-risk boundaries."""
    initiative = _sample_initiative(deadline="2026-06-01")
    repo = _repo_at_tier(1)
    # If "today" is a month before deadline → on-track
    assert derive_status(initiative, repo, today="2026-05-01") == "on-track"
    # If "today" is 10 days before deadline → at-risk
    assert derive_status(initiative, repo, today="2026-05-22") == "at-risk"
    # If "today" is after deadline → overdue
    assert derive_status(initiative, repo, today="2026-06-10") == "overdue"


def test_derive_status_abandoned_closed_returns_met():
    """closed_reason='abandoned' still returns 'met' (closed = terminal)."""
    initiative = _sample_initiative(
        closed_at="2026-05-01T00:00:00+00:00", closed_reason="abandoned"
    )
    status = derive_status(initiative, _repo_at_tier(1))
    assert status == "met"


# ── operator_identity ─────────────────────────────────────────────────────────


def test_operator_identity_uses_user_env():
    with patch.dict("os.environ", {"USER": "testuser"}):
        assert operator_identity() == "testuser"


def test_operator_identity_fallback():
    env = {k: v for k, v in __import__("os").environ.items() if k != "USER"}
    with patch.dict("os.environ", env, clear=True):
        assert operator_identity() == "operator"


# ── Initiative frozen dataclass ───────────────────────────────────────────────


def test_initiative_frozen():
    i = _sample_initiative()
    with pytest.raises((AttributeError, TypeError)):
        i.repo_name = "other"  # type: ignore[misc]


# ── CLI integration tests ─────────────────────────────────────────────────────


def _build_portfolio_truth(tmp_path: Path, repo_name: str = "Wavelength", tier: int = 2) -> Path:
    """Write a minimal portfolio-truth-latest.json for CLI tests."""
    from datetime import timedelta as td

    days_ago = 100
    project: dict = {
        "identity": {"display_name": repo_name, "has_git": True},
        "derived": {
            "last_meaningful_activity_at": (date.today() - td(days=days_ago)).isoformat(),
            "activity_status": "active",
            "context_quality": "strong" if tier >= 3 else "weak",
            "context_files": ["README.md", "LICENSE"] if tier >= 3 else ["README.md"],
            "run_instructions_present": tier >= 2,
        },
        "risk": {
            "risk_tier": "baseline",
            "risk_factors": [] if tier >= 4 else ["stale-dep"],
            "doctor_gap": False,
        },
    }
    pt = {"version": 1, "projects": [project]}
    pt_path = tmp_path / "portfolio-truth-latest.json"
    pt_path.write_text(json.dumps(pt), encoding="utf-8")
    return pt_path


def _run_cli(argv: list[str]) -> int:
    """Run the CLI and return exit code (0 = success)."""
    from src.cli import main

    with patch.object(sys, "argv", ["audit"] + argv):
        try:
            main()
            return 0
        except SystemExit as exc:
            return int(exc.code) if exc.code is not None else 0


def test_cli_set_initiative_writes_file(tmp_path: Path):
    _build_portfolio_truth(tmp_path, "WavelengthExample", tier=1)
    exit_code = _run_cli(
        [
            "triage",
            "saagpatel",
            "--set-initiative",
            "WavelengthExample",
            "--target-tier",
            "3",
            "--deadline",
            _future(60),
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert exit_code == 0
    p = tmp_path / "initiatives.json"
    assert p.exists()
    data = json.loads(p.read_text())
    assert data["version"] == 1
    assert data["initiatives"][0]["repo_name"] == "WavelengthExample"
    assert data["initiatives"][0]["target_tier"] == 3


def test_cli_set_initiative_target_leq_current_exits_2(tmp_path: Path):
    _build_portfolio_truth(tmp_path, "GoldRepo", tier=3)
    exit_code = _run_cli(
        [
            "triage",
            "saagpatel",
            "--set-initiative",
            "GoldRepo",
            "--target-tier",
            "2",  # target < current
            "--deadline",
            _future(30),
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert exit_code == 2


def test_cli_set_initiative_past_deadline_exits_2(tmp_path: Path):
    _build_portfolio_truth(tmp_path, "Repo", tier=1)
    exit_code = _run_cli(
        [
            "triage",
            "saagpatel",
            "--set-initiative",
            "Repo",
            "--target-tier",
            "2",
            "--deadline",
            _past(3),  # past date
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert exit_code == 2


def test_cli_set_initiative_missing_target_tier_exits_2(tmp_path: Path):
    _build_portfolio_truth(tmp_path, "Repo", tier=1)
    exit_code = _run_cli(
        [
            "triage",
            "saagpatel",
            "--set-initiative",
            "Repo",
            # no --target-tier
            "--deadline",
            _future(30),
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert exit_code == 2


def test_cli_list_initiatives_empty_exits_cleanly(tmp_path: Path):
    """--initiatives with no initiatives.json should print empty table and exit 0."""
    _build_portfolio_truth(tmp_path, "Repo", tier=1)
    exit_code = _run_cli(
        [
            "triage",
            "saagpatel",
            "--initiatives",
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert exit_code == 0


def test_cli_list_initiatives_shows_entries(tmp_path: Path, capsys):
    _build_portfolio_truth(tmp_path, "TideEngine", tier=1)
    p = tmp_path / "initiatives.json"
    save_initiatives(p, [_sample_initiative("TideEngine", target_tier=3, deadline=_future(10))])
    exit_code = _run_cli(
        [
            "triage",
            "saagpatel",
            "--initiatives",
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert exit_code == 0


def test_cli_close_initiative_updates_record(tmp_path: Path):
    _build_portfolio_truth(tmp_path, "Wavelength", tier=1)
    p = tmp_path / "initiatives.json"
    save_initiatives(p, [_sample_initiative("Wavelength", target_tier=3)])
    exit_code = _run_cli(
        [
            "triage",
            "saagpatel",
            "--close-initiative",
            "Wavelength",
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert exit_code == 0
    loaded = load_initiatives(p)
    assert loaded[0].closed_at is not None
    assert loaded[0].closed_reason == "met"


def test_cli_close_initiative_not_found_exits_2(tmp_path: Path):
    _build_portfolio_truth(tmp_path, "Repo", tier=1)
    exit_code = _run_cli(
        [
            "triage",
            "saagpatel",
            "--close-initiative",
            "NoSuchRepo",
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert exit_code == 2
