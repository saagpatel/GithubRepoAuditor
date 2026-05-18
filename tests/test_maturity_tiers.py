"""Tests for src/maturity_tiers.py — Arc G Sprint 7A.1 + Sprint 8.3."""

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


def _sprint8_silver_repo() -> dict:
    """Sprint-8 snapshot: meets Silver via strict signals."""
    return {
        "identity": {"display_name": "Sprint8Silver", "has_git": True},
        "derived": {
            "last_meaningful_activity_at": _days_ago(100),
            "activity_status": "active",
            "context_quality": "boilerplate",  # would fail proxy README check
            "context_files": ["README.md"],
            "run_instructions_present": False,  # would fail proxy tests check
            "has_tests": True,  # strict: passes tests
            "has_ci": True,  # strict: passes CI
            "readme_char_count": 500,  # strict: passes README chars
        },
        "risk": {
            "risk_tier": "baseline",
            "risk_factors": ["stale-dep"],
            "doctor_gap": False,
        },
    }


def _sprint8_gold_repo() -> dict:
    """Sprint-8 snapshot: meets Gold via strict release_count."""
    return {
        "identity": {"display_name": "Sprint8Gold", "has_git": True},
        "derived": {
            "last_meaningful_activity_at": _days_ago(100),
            "activity_status": "active",
            "context_quality": "weak",  # would fail proxy shipped check
            "context_files": ["README.md", "LICENSE"],
            "run_instructions_present": False,
            "has_tests": True,
            "has_ci": True,
            "readme_char_count": 300,
            "release_count": 2,  # strict: passes shipped + recent
        },
        "risk": {
            "risk_tier": "baseline",
            "risk_factors": ["stale-dep"],
            "doctor_gap": False,
        },
    }


def _sprint8_platinum_repo() -> dict:
    """Sprint-8 snapshot: meets all tiers via strict signals."""
    return {
        "identity": {"display_name": "Sprint8Plat", "has_git": True},
        "derived": {
            "last_meaningful_activity_at": _days_ago(30),
            "activity_status": "active",
            "context_quality": "strong",
            "context_files": ["README.md", "LICENSE"],
            "run_instructions_present": True,
            "has_tests": True,
            "has_ci": True,
            "readme_char_count": 1000,
            "release_count": 3,
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


# ── Sprint 8.3: strict signal tests ──────────────────────────────────────────


# 1. Strict has_tests=True overrides proxy even when run_instructions_present=False
def test_strict_has_tests_true_passes_even_without_run_instructions():
    """Sprint-8 snapshot: has_tests=True → tests check passes regardless of proxy."""
    repo = _sprint8_silver_repo()
    # Ensure run_instructions_present is False (proxy would fail)
    assert repo["derived"]["run_instructions_present"] is False
    assert repo["derived"]["has_tests"] is True
    # Should reach Silver because strict signals all pass
    assert compute_tier(repo) == 2


# 2. Strict has_tests=False → fails even if proxy run_instructions_present=True
def test_strict_has_tests_false_fails_even_with_run_instructions():
    """Sprint-8 snapshot: has_tests=False → strict says no tests, no proxy fallback."""
    repo = _sprint8_silver_repo()
    repo = {
        **repo,
        "derived": {
            **repo["derived"],
            "has_tests": False,
            "run_instructions_present": True,  # proxy would pass but strict takes precedence
        },
    }
    gap = tier_gap(repo, target=2)
    combined = " ".join(gap.missing_requirements).lower()
    assert "tests" in combined


# 3. Pre-Sprint-8 snapshot (no has_tests key) → falls back to run_instructions_present proxy
def test_pre_sprint8_snapshot_falls_back_to_proxy_for_tests():
    """Pre-Sprint-8 snapshot: no has_tests key → proxy (run_instructions_present) is used."""
    repo = _silver_repo()
    # Confirm has_tests is absent
    assert "has_tests" not in repo["derived"]
    # run_instructions_present=True → proxy passes → Silver
    assert compute_tier(repo) == 2


def test_pre_sprint8_snapshot_proxy_fails_without_run_instructions():
    """Pre-Sprint-8 snapshot: no has_tests, run_instructions_present=False → fails tests check."""
    repo = _minimal_repo()
    assert "has_tests" not in repo["derived"]
    assert repo["derived"]["run_instructions_present"] is False
    gap = tier_gap(repo, target=2)
    combined = " ".join(gap.missing_requirements).lower()
    assert "tests" in combined


# 4. Strict has_ci=True overrides proxy even when doctor_gap=True
def test_strict_has_ci_true_passes_even_with_doctor_gap():
    """Sprint-8 snapshot: has_ci=True → CI check passes even if proxy would fail."""
    repo = _sprint8_silver_repo()
    repo = {
        **repo,
        "risk": {**repo["risk"], "doctor_gap": True},  # proxy would fail
    }
    # Still reaches Silver because has_ci=True strict passes
    assert compute_tier(repo) == 2


# 5. Strict has_ci=False → fails CI check regardless of proxy
def test_strict_has_ci_false_fails_regardless_of_proxy():
    """Sprint-8 snapshot: has_ci=False → fails CI even if proxy signals would pass."""
    repo = _sprint8_silver_repo()
    repo = {
        **repo,
        "derived": {
            **repo["derived"],
            "has_ci": False,
            "run_instructions_present": True,  # proxy would pass
        },
        "risk": {**repo["risk"], "doctor_gap": False},  # proxy would pass
    }
    gap = tier_gap(repo, target=2)
    combined = " ".join(gap.missing_requirements).lower()
    assert "ci" in combined


# 6. Strict readme_char_count >= 200 passes even if context_quality == "boilerplate"
def test_strict_readme_chars_passes_even_with_boilerplate_context_quality():
    """Sprint-8 snapshot: readme_char_count=500 → README check passes despite 'boilerplate'."""
    repo = _sprint8_silver_repo()
    assert repo["derived"]["context_quality"] == "boilerplate"
    assert repo["derived"]["readme_char_count"] == 500
    # Should still reach Silver
    assert compute_tier(repo) == 2


# 7. Strict readme_char_count < 200 fails even if context_quality != "boilerplate"
def test_strict_readme_chars_fails_when_count_below_threshold():
    """Sprint-8 snapshot: readme_char_count=50 → README check fails even if not boilerplate."""
    repo = _sprint8_silver_repo()
    repo = {
        **repo,
        "derived": {
            **repo["derived"],
            "context_quality": "strong",  # proxy would pass
            "readme_char_count": 50,  # strict: fails
        },
    }
    gap = tier_gap(repo, target=2)
    combined = " ".join(gap.missing_requirements).lower()
    assert "readme" in combined


# 8. release_count key absent (opt-in not set) → falls back to context_quality proxy
def test_release_count_absent_falls_back_to_proxy():
    """Sprint-8 snapshot without release_count → proxy (context_quality) used for shipped."""
    repo = _sprint8_silver_repo()
    # Add has_tests/has_ci but no release_count; also add LICENSE + strong context for Gold
    repo = {
        **repo,
        "derived": {
            **repo["derived"],
            "context_quality": "strong",  # proxy passes shipped check
            "context_files": ["README.md", "LICENSE"],  # required for Gold LICENSE check
        },
        "risk": {**repo["risk"], "risk_factors": [], "doctor_gap": False},
    }
    assert "release_count" not in repo["derived"]
    # Should reach Gold via context_quality proxy for shipped release
    assert compute_tier(repo) == 3


# 9. release_count present and >= 1 → strict passes even when context_quality is weak
def test_strict_release_count_ge1_passes_shipped_check():
    """Sprint-8 snapshot: release_count=2 → shipped check passes even with weak context."""
    repo = _sprint8_gold_repo()
    assert repo["derived"]["context_quality"] == "weak"
    assert repo["derived"]["release_count"] == 2
    # Should reach Gold because strict release_count passes the shipped check
    assert compute_tier(repo) == 3


def test_strict_has_license_passes_license_requirement():
    """Sprint-8 snapshot: derived.has_license=True passes Gold without context_files LICENSE."""
    repo = _sprint8_gold_repo()
    repo = {
        **repo,
        "derived": {
            **repo["derived"],
            "context_files": ["README.md"],
            "has_license": True,
        },
    }
    assert compute_tier(repo) == 3


# 10. release_count=0 → fails even if context_quality would pass proxy
def test_strict_release_count_zero_fails_shipped():
    """Sprint-8 snapshot: release_count=0 → shipped check fails even with strong context."""
    repo = _sprint8_gold_repo()
    repo = {
        **repo,
        "derived": {
            **repo["derived"],
            "context_quality": "strong",  # proxy would pass
            "release_count": 0,  # strict: fails
        },
    }
    gap = tier_gap(repo, target=3)
    combined = " ".join(gap.missing_requirements).lower()
    assert "release" in combined or "shipped" in combined


# 11. release_count >= 2 → strict passes recent-releases Platinum check
def test_strict_release_count_ge2_passes_recent_releases():
    """Sprint-8 snapshot: release_count=3 → ≥2 releases check passes."""
    repo = _sprint8_platinum_repo()
    assert repo["derived"]["release_count"] == 3
    assert compute_tier(repo) == 4


# 12. release_count=1 → fails ≥2 releases Platinum check
def test_strict_release_count_1_fails_recent_releases():
    """Sprint-8 snapshot: release_count=1 → fails ≥2 releases Platinum check."""
    repo = _sprint8_platinum_repo()
    repo = {
        **repo,
        "derived": {
            **repo["derived"],
            "release_count": 1,
            "activity_status": "active",  # proxy would pass if fallback used
        },
    }
    gap = tier_gap(repo, target=4)
    combined = " ".join(gap.missing_requirements).lower()
    assert "release" in combined or "2 release" in combined


# 13. TierGap.requirement_sources populated and matches missing_requirements length
def test_tier_gap_requirement_sources_length_matches_missing():
    """requirement_sources must have same length as missing_requirements."""
    repo = _minimal_repo()
    gap = tier_gap(repo, target=4)
    assert len(gap.requirement_sources) == len(gap.missing_requirements)


# 14. Proxy-derived gaps tagged "proxy"; strict-derived gaps tagged "strict"
def test_tier_gap_requirement_sources_strict_vs_proxy():
    """Gaps from Sprint-8 strict signals are tagged 'strict'; proxy ones are 'proxy'."""
    # Build a repo that fails tests via strict (has_tests=False) and CI via strict
    repo = {
        "identity": {"display_name": "Mixed", "has_git": True},
        "derived": {
            "last_meaningful_activity_at": _days_ago(100),
            "activity_status": "active",
            "context_quality": "boilerplate",  # would be proxy fail
            "context_files": ["README.md"],
            "run_instructions_present": True,  # proxy would pass tests
            "has_tests": False,  # strict override → fail
            "has_ci": False,  # strict override → fail
            "readme_char_count": 50,  # strict override → fail README
        },
        "risk": {
            "risk_tier": "baseline",
            "risk_factors": [],
            "doctor_gap": False,
        },
    }
    gap = tier_gap(repo, target=2)
    # All three Silver checks should be strict (has_tests, has_ci, readme_char_count present)
    for req, src in zip(gap.missing_requirements, gap.requirement_sources):
        if "tests" in req.lower() or "ci" in req.lower() or "readme" in req.lower():
            assert src == "strict", f"Expected 'strict' for {req!r}, got {src!r}"


# 15. Pre-Sprint-8 repo → requirement_sources are all "proxy"
def test_pre_sprint8_tier_gap_sources_all_proxy():
    """Pre-Sprint-8 snapshot: all gap sources should be 'proxy'."""
    repo = _minimal_repo()
    gap = tier_gap(repo, target=3)
    for src in gap.requirement_sources:
        assert src == "proxy", f"Expected all sources 'proxy' for pre-Sprint-8, got {src!r}"


# 16. Sprint-8 full platinum repo → no missing requirements
def test_sprint8_platinum_repo_no_gaps():
    """Sprint-8 platinum repo with all strict signals should have no gaps."""
    repo = _sprint8_platinum_repo()
    gap = tier_gap(repo, target=4)
    assert gap.missing_requirements == []
    assert gap.requirement_sources == []
    assert compute_tier(repo) == 4


# 17. Pre-Sprint-8 proxy-Silver repo behavior matches Sprint 7A baseline (regression)
def test_pre_sprint8_regression_silver_via_proxy():
    """Pre-Sprint-8 Silver repo still reaches tier 2 (proxy path unchanged)."""
    repo = _silver_repo()
    assert "has_tests" not in repo["derived"]
    assert compute_tier(repo) == 2


# 18. Pre-Sprint-8 proxy-Gold repo behavior matches Sprint 7A baseline (regression)
def test_pre_sprint8_regression_gold_via_proxy():
    """Pre-Sprint-8 Gold repo still reaches tier 3 (proxy path unchanged)."""
    repo = _gold_repo()
    assert "has_tests" not in repo["derived"]
    assert compute_tier(repo) == 3


# 19. TierGap default requirement_sources empty list when at target
def test_tier_gap_sources_empty_when_already_at_target():
    """requirement_sources is empty list when no missing requirements."""
    repo = _gold_repo()
    gap = tier_gap(repo, target=2)
    assert gap.missing_requirements == []
    assert gap.requirement_sources == []


# 20. TierGap frozen dataclass still works with new field
def test_tier_gap_frozen_with_sources():
    """TierGap with requirement_sources is still frozen."""
    tg = TierGap(1, 3, ["missing req"], ["proxy"])
    with pytest.raises((AttributeError, TypeError)):
        tg.requirement_sources = []  # type: ignore[misc]


# ── Arc G Sprint 11.3 — TierGap JSON serialisation ───────────────────────────


# 21. to_dict includes all four fields
def test_tier_gap_to_dict_includes_all_fields():
    """TierGap.to_dict() returns all four expected fields."""
    tg = TierGap(
        current_tier=1,
        target_tier=3,
        missing_requirements=["Has CI", "Has tests"],
        requirement_sources=["strict", "proxy"],
    )
    d = tg.to_dict()
    assert d["current_tier"] == 1
    assert d["target_tier"] == 3
    assert d["missing_requirements"] == ["Has CI", "Has tests"]
    assert d["requirement_sources"] == ["strict", "proxy"]


# 22. from_dict(to_dict(g)) == g — round-trip for various inputs
@pytest.mark.parametrize(
    "tg",
    [
        TierGap(current_tier=0, target_tier=2),
        TierGap(
            current_tier=1,
            target_tier=2,
            missing_requirements=["req A"],
            requirement_sources=["strict"],
        ),
        TierGap(
            current_tier=2,
            target_tier=4,
            missing_requirements=["req A", "req B"],
            requirement_sources=["strict", "proxy"],
        ),
    ],
    ids=["empty-sources", "all-strict", "mixed"],
)
def test_tier_gap_round_trip(tg: TierGap):
    """TierGap.from_dict(tg.to_dict()) == tg for various inputs."""
    assert TierGap.from_dict(tg.to_dict()) == tg


# 23. from_dict with missing requirement_sources key → empty list
def test_tier_gap_from_dict_missing_sources_defaults_to_empty():
    """from_dict with no 'requirement_sources' key yields an empty list."""
    d = {"current_tier": 2, "target_tier": 3, "missing_requirements": ["something"]}
    tg = TierGap.from_dict(d)
    assert tg.requirement_sources == []
    assert tg.missing_requirements == ["something"]
