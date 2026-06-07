from __future__ import annotations

from src.excel_dashboard_helpers import build_dashboard_kpi_specs


def test_kpi_specs_include_elevated_risk_when_present() -> None:
    specs = build_dashboard_kpi_specs(
        grade="B",
        average_score=0.7,
        tiers={"shipped": 2},
        risk_lookup={"a": "elevated", "b": "elevated", "c": "baseline"},
    )
    labels = {spec[0]: spec[1] for spec in specs}
    assert labels["Elevated Risk"] == 2


def test_kpi_specs_omit_risk_when_no_lookup() -> None:
    specs = build_dashboard_kpi_specs(grade="B", average_score=0.7, tiers={})
    assert all(spec[0] != "Elevated Risk" for spec in specs)
