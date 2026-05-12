"""Tests for src/maturity_tiers.py — Arc G Sprint 7A.1."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.maturity_tiers import (
    TIER_DEFINITIONS,
    TierCriteria,
    TierGap,
    compute_tier,
    tier_gap,
    tier_name,
)

# ── Fixtures / helpers ────────────────────────────────────────────────────────


def _days_ago(n: int) -> str:
    """Return an ISO date string n days ago."""
    return (date.today() - timedelta(days=n)).isoformat()


def _minimal_repo() -> dict:
    """A repo that satisfies only Bronze (has_git + README + one commit)."""
    return {
        "identity": {"display_name": "TestRepo", "has_git": True},
        "derived": {
            "last_meaningful_activity_at": _days_ago(100),
            "activity_status": "active",
            "context_quality": "weak",
            "context_files": ["README.md", "src/main.py"],
            "run_instructions_present": False,
            "stack_present": True,
        },
        "risk": {
            "risk_tier": "elevated",
            "risk_factors": ["stale-dep"],
            "doctor_gap": True,
        },
    }


def _silver_repo() -> dict:
    """Meets Bronze + Silver criteria."""
    return {
        "identity": {"display_name": "SilverRepo", "has_git": True},
        "derived": {
            "last_meaningful_activity_at": _days_ago(100),
            "activity_status": "active",
            "context_quality": "weak",  # not boilerplate
            "context_files": ["README.md"],
            "run_instructions_present": True,
        },
        "risk": {
            "risk_tier": "baseline",
            "risk_factors": ["stale-dep"],
            "doctor_gap": False,
        },
    }


def _gold_repo() -> dict:
    """Meets Bronze + Silver + Gold criteria."""
    return {
        "identity": {"display_name": "GoldRepo", "has_git": True},
        "derived": {
            "last_meaningful_activity_at": _days_ago(100),
            "activity_status": "active",
            "context_quality": "strong",
            "context_files": ["README.md", "LICENSE"],
            "run_instructions_present": True,
        },
        "risk": {
            "risk_tier": "baseline",
            "risk_factors": ["stale-dep"],
            "doctor_gap": False,
        },
    }


def _platinum_repo() -> dict:
    """Meets all four tiers."""
    return {
        "identity": {"display_name": "PlatRepo", "has_git": True},
        "derived": {
            "last_meaningful_activity_at": _days_ago(30),
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


# ── TIER_DEFINITIONS sanity ───────────────────────────────────────────────────


def test_tier_definitions_keys():
    assert set(TIER_DEFINITIONS.keys()) == {1, 2, 3, 4}


def test_tier_definitions_names():
    assert TIER_DEFINITIONS[1].name == "Bronze"
    assert TIER_DEFINITIONS[2].name == "Silver"
    assert TIER_DEFINITIONS[3].name == "Gold"
    assert TIER_DEFINITIONS[4].name == "Platinum"


def test_tier_criteria_frozen():
    tc = TierCriteria(1, "Bronze", ["req"])
    with pytest.raises((AttributeError, TypeError)):
        tc.tier = 9  # type: ignore[misc]


# ── compute_tier ──────────────────────────────────────────────────────────────


def test_compute_tier_no_git_returns_0():
    repo = {"identity": {"has_git": False}, "derived": {}, "risk": {}}
    assert compute_tier(repo) == 0


def test_compute_tier_minimal_repo_is_bronze():
    """Repo with has_git + README + one commit → at least tier 1."""
    assert compute_tier(_minimal_repo()) == 1


def test_compute_tier_silver_repo():
    assert compute_tier(_silver_repo()) == 2


def test_compute_tier_gold_repo():
    assert compute_tier(_gold_repo()) == 3


def test_compute_tier_platinum_repo():
    assert compute_tier(_platinum_repo()) == 4


def test_compute_tier_stale_repo_capped_at_silver():
    """A repo with activity_status='stale' cannot reach Gold (README staleness proxy)."""
    repo = _silver_repo()
    repo = {
        **repo,
        "derived": {
            **repo["derived"],
            "activity_status": "stale",
            "context_quality": "strong",
            "context_files": ["README.md", "LICENSE"],
        },
        "risk": {**repo["risk"], "risk_factors": []},
    }
    tier = compute_tier(repo)
    assert tier <= 2


def test_compute_tier_recent_activity_only_not_enough_for_platinum_without_active():
    """Platinum proxy requires activity_status=='active'. 'maintenance' should not qualify."""
    repo = _gold_repo()
    repo = {
        **repo,
        "derived": {
            **repo["derived"],
            "last_meaningful_activity_at": _days_ago(30),
            "activity_status": "maintenance",  # not 'active'
        },
        "risk": {**repo["risk"], "risk_factors": []},
    }
    tier = compute_tier(repo)
    assert tier < 4


def test_compute_tier_missing_fields_does_not_crash():
    """Completely empty repo dict → 0 (no has_git)."""
    assert compute_tier({}) == 0


def test_compute_tier_partial_fields_does_not_crash():
    """Repo with only has_git + README → tier 1 without crashing."""
    repo = {
        "identity": {"has_git": True},
        "derived": {
            "last_meaningful_activity_at": _days_ago(10),
            "context_files": ["README.md"],
        },
    }
    result = compute_tier(repo)
    assert isinstance(result, int)
    assert result >= 1


def test_compute_tier_over_365_days_caps_at_bronze():
    """Commits older than 365 days fail Silver ≤365d criterion."""
    repo = _minimal_repo()
    repo = {
        **repo,
        "derived": {
            **repo["derived"],
            "last_meaningful_activity_at": _days_ago(400),
            "context_quality": "weak",
            "run_instructions_present": True,
        },
        "risk": {"risk_tier": "baseline", "risk_factors": [], "doctor_gap": False},
    }
    assert compute_tier(repo) == 1


# ── tier_gap ─────────────────────────────────────────────────────────────────


def test_tier_gap_already_at_target_empty_missing():
    repo = _gold_repo()
    gap = tier_gap(repo, target=3)
    assert gap.missing_requirements == []
    assert gap.current_tier == 3
    assert gap.target_tier == 3


def test_tier_gap_above_target_empty_missing():
    repo = _platinum_repo()
    gap = tier_gap(repo, target=2)
    assert gap.missing_requirements == []
    assert gap.current_tier == 4


def test_tier_gap_bronze_to_gold_lists_silver_and_gold_gaps():
    repo = _minimal_repo()
    gap = tier_gap(repo, target=3)
    assert gap.current_tier == 1
    assert gap.target_tier == 3
    # Should mention tests/CI proxy and the Gold criteria
    combined = " ".join(gap.missing_requirements).lower()
    assert "run_instructions_present" in combined or "tests" in combined


def test_tier_gap_invalid_target_raises():
    with pytest.raises(ValueError, match="1-4"):
        tier_gap({}, target=5)


def test_tier_gap_no_git_reports_bronze_gap():
    repo = {"identity": {"has_git": False}, "derived": {}, "risk": {}}
    gap = tier_gap(repo, target=2)
    assert "has_git" in " ".join(gap.missing_requirements).lower()


def test_tier_gap_platinum_missing_risk_factors():
    """Repo with non-empty risk_factors can't reach Platinum."""
    repo = _gold_repo()
    # gold_repo has stale-dep risk factor → platinum fails
    gap = tier_gap(repo, target=4)
    combined = " ".join(gap.missing_requirements).lower()
    assert "risk_factors" in combined or "abandoned" in combined


def test_tier_gap_frozen_dataclass():
    tg = TierGap(1, 3, ["missing req"])
    with pytest.raises((AttributeError, TypeError)):
        tg.current_tier = 99  # type: ignore[misc]


# ── tier_name ─────────────────────────────────────────────────────────────────


def test_tier_name_known():
    assert tier_name(1) == "Bronze"
    assert tier_name(2) == "Silver"
    assert tier_name(3) == "Gold"
    assert tier_name(4) == "Platinum"


def test_tier_name_zero():
    assert tier_name(0) == "Untracked"
