from src.portfolio_risk import build_portfolio_risk_summary, build_risk_entry


def _baseline_kwargs(**overrides):
    defaults = dict(
        display_name="SomeRepo",
        operating_path="maintain",
        path_override="",
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


def test_security_high_alert_adds_single_factor_moderate():
    # An open high-severity Dependabot alert on an active, otherwise-healthy repo
    # contributes exactly one factor — moderate, not elevated, on its own.
    result = build_risk_entry(**_baseline_kwargs(security_high_alerts=2))
    assert result["risk_tier"] == "moderate"
    assert result["risk_factors"] == ["active-high-severity-alerts"]
    assert result["security_risk"] is True
    assert "open high/critical security alerts" in result["risk_summary"]


def test_security_critical_alert_force_elevates():
    # A lone open critical alert force-elevates even on an otherwise-clean repo —
    # an unpatched critical CVE cannot hide behind good context/path hygiene.
    result = build_risk_entry(**_baseline_kwargs(security_critical_alerts=1))
    assert result["risk_tier"] == "elevated"
    assert "active-high-severity-alerts" in result["risk_factors"]
    assert result["security_risk"] is True


def test_security_no_alerts_leaves_security_risk_false():
    result = build_risk_entry(**_baseline_kwargs())
    assert result["security_risk"] is False
    assert "active-high-severity-alerts" not in result["risk_factors"]


def test_security_alerts_ignored_when_not_active():
    # Alerts on a stale (non-active) repo on the maintain path do not fire the
    # factor or force elevation — the factor is gated on active status, like the others.
    result = build_risk_entry(
        **_baseline_kwargs(
            activity_status="stale",
            operating_path="maintain",
            security_critical_alerts=3,
            security_high_alerts=5,
        )
    )
    assert result["risk_tier"] != "elevated"
    assert result["security_risk"] is False
    assert "active-high-severity-alerts" not in result["risk_factors"]


def test_security_alerts_do_not_override_deferred_short_circuit():
    # A stale, non-maintain repo short-circuits to deferred BEFORE any factor is
    # evaluated — even open critical alerts cannot pull it out of deferred, and the
    # deferred constant carries security_risk=False.
    result = build_risk_entry(
        **_baseline_kwargs(
            activity_status="stale",
            operating_path="experiment",
            security_critical_alerts=4,
            security_high_alerts=2,
        )
    )
    assert result["risk_tier"] == "deferred"
    assert result["security_risk"] is False
    assert result["risk_factors"] == []


def test_security_high_alert_stacks_toward_three_factor_elevation():
    # A high alert counts toward the existing 3+ = elevated threshold alongside
    # weak-context-active and no-run-instructions.
    result = build_risk_entry(
        **_baseline_kwargs(
            context_quality="boilerplate",
            run_instructions_present=False,
            activity_status="active",
            security_high_alerts=1,
        )
    )
    assert result["risk_tier"] == "elevated"
    assert "active-high-severity-alerts" in result["risk_factors"]
    assert len(result["risk_factors"]) >= 3


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
