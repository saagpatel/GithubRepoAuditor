from src.portfolio_risk import build_portfolio_risk_summary, build_risk_entry


def _baseline_kwargs(**overrides):
    defaults = dict(
        display_name="SomeRepo",
        operating_path="maintain",
        path_override="",
        path_confidence="high",
        context_quality="standard",
        activity_status="active",
        registry_status="active",
        criticality="medium",
        doctor_standard="",
        known_risks_present=True,
        run_instructions_present=True,
    )
    defaults.update(overrides)
    return defaults


def test_risk_tier_deferred_for_archived_registry():
    result = build_risk_entry(**_baseline_kwargs(registry_status="archived"))
    assert result["risk_tier"] == "deferred"
    assert result["risk_factors"] == []
    assert result["doctor_gap"] is False
    assert result["context_risk"] is False
    assert result["path_risk"] is False


def test_risk_tier_deferred_for_archive_path():
    result = build_risk_entry(**_baseline_kwargs(operating_path="archive"))
    assert result["risk_tier"] == "deferred"
    assert result["risk_factors"] == []


def test_risk_tier_deferred_for_stale_non_maintain():
    result = build_risk_entry(
        **_baseline_kwargs(activity_status="stale", operating_path="experiment")
    )
    assert result["risk_tier"] == "deferred"
    assert "Stale" in result["risk_summary"]


def test_stale_on_maintain_path_is_not_deferred():
    result = build_risk_entry(
        **_baseline_kwargs(activity_status="stale", operating_path="maintain")
    )
    assert result["risk_tier"] != "deferred"


def test_risk_tier_elevated_for_compound_factors():
    # weak-context-active + investigate-override → elevated (compound rule)
    result = build_risk_entry(
        **_baseline_kwargs(
            context_quality="boilerplate",
            path_override="investigate",
            activity_status="active",
        )
    )
    assert result["risk_tier"] == "elevated"
    assert "weak-context-active" in result["risk_factors"]
    assert "investigate-override" in result["risk_factors"]
    assert result["context_risk"] is True
    assert result["path_risk"] is True


def test_risk_tier_elevated_for_three_plus_factors():
    # weak-context + missing-path + no-run-instructions → 3 factors → elevated
    result = build_risk_entry(
        **_baseline_kwargs(
            context_quality="none",
            operating_path="",
            run_instructions_present=False,
            activity_status="active",
        )
    )
    assert result["risk_tier"] == "elevated"
    assert len(result["risk_factors"]) >= 3


def test_risk_tier_moderate_for_single_factor():
    result = build_risk_entry(
        **_baseline_kwargs(
            context_quality="boilerplate",
            path_override="",
            activity_status="active",
        )
    )
    assert result["risk_tier"] == "moderate"
    assert "weak-context-active" in result["risk_factors"]
    assert len(result["risk_factors"]) == 1


def test_risk_tier_baseline_for_healthy():
    result = build_risk_entry(**_baseline_kwargs())
    assert result["risk_tier"] == "baseline"
    assert result["risk_factors"] == []
    assert result["risk_summary"] == "No elevated risk factors."
    assert result["doctor_gap"] is False
    assert result["context_risk"] is False
    assert result["path_risk"] is False


def test_doctor_gap_true_for_strategic_without_standard():
    result = build_risk_entry(
        **_baseline_kwargs(
            display_name="GithubRepoAuditor",
            doctor_standard="",
        )
    )
    assert result["doctor_gap"] is True
    assert "missing-doctor-standard" in result["risk_factors"]


def test_doctor_gap_false_for_non_strategic():
    result = build_risk_entry(
        **_baseline_kwargs(
            display_name="RandomRepo",
            doctor_standard="",
        )
    )
    assert result["doctor_gap"] is False
    assert "missing-doctor-standard" not in result["risk_factors"]


def test_portfolio_risk_summary_aggregates_tiers():
    projects = [
        {"risk": {"risk_tier": "elevated"}},
        {"risk": {"risk_tier": "elevated"}},
        {"risk": {"risk_tier": "moderate"}},
        {"risk": {"risk_tier": "baseline"}},
        {"risk": {"risk_tier": "deferred"}},
    ]
    result = build_portfolio_risk_summary(projects)
    assert result["risk_tier_counts"]["elevated"] == 2
    assert result["risk_tier_counts"]["moderate"] == 1
    assert result["risk_tier_counts"]["baseline"] == 1
    assert result["risk_tier_counts"]["deferred"] == 1
    assert result["elevated_count"] == 2
    assert result["moderate_count"] == 1
