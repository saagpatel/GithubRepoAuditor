from __future__ import annotations

import json
from pathlib import Path

from src.report_enrichment import build_risk_lookup, build_weekly_review_pack


def _make_report() -> dict:
    return {
        "username": "testuser",
        "generated_at": "2026-04-14T12:00:00Z",
        "repos_audited": 0,
        "average_score": 0.0,
        "portfolio_grade": "F",
        "tier_distribution": {},
        "collections": {},
        "profiles": {
            "default": {
                "description": "Balanced",
                "lens_weights": {
                    "ship_readiness": 0.4,
                    "showcase_value": 0.3,
                    "security_posture": 0.3,
                },
            }
        },
        "scenario_summary": {"top_levers": [], "portfolio_projection": {}},
        "audits": [],
    }


def _make_truth(elevated: int = 2, moderate: int = 1, baseline: int = 3) -> dict:
    projects = []
    for i in range(elevated):
        projects.append(
            {
                "identity": {"display_name": f"ElevatedRepo{i}"},
                "risk": {
                    "risk_tier": "elevated",
                    "risk_summary": f"Elevated repo {i} has weak context.",
                },
            }
        )
    for i in range(moderate):
        projects.append(
            {
                "identity": {"display_name": f"ModerateRepo{i}"},
                "risk": {"risk_tier": "moderate", "risk_summary": "One risk factor."},
            }
        )
    for i in range(baseline):
        projects.append(
            {
                "identity": {"display_name": f"BaselineRepo{i}"},
                "risk": {"risk_tier": "baseline", "risk_summary": "No elevated risk factors."},
            }
        )
    return {"schema_version": "0.4.0", "projects": projects}


def test_risk_posture_present_when_truth_available(tmp_path: Path) -> None:
    (tmp_path / "portfolio-truth-latest.json").write_text(
        json.dumps(_make_truth(elevated=2, moderate=1, baseline=3))
    )
    pack = build_weekly_review_pack(_make_report(), output_dir=tmp_path)
    risk = pack.get("risk_posture")
    assert risk is not None
    assert risk["elevated_count"] == 2
    assert risk["moderate_count"] == 1
    assert risk["baseline_count"] == 3
    assert len(risk["top_elevated"]) == 2
    assert risk["top_elevated"][0]["repo"].startswith("ElevatedRepo")


def test_risk_posture_empty_when_truth_absent(tmp_path: Path) -> None:
    pack = build_weekly_review_pack(_make_report(), output_dir=tmp_path)
    assert pack.get("risk_posture") == {}


def test_risk_posture_empty_when_no_output_dir() -> None:
    pack = build_weekly_review_pack(_make_report())
    assert pack.get("risk_posture") == {}


def test_build_risk_lookup_maps_name_to_tier_and_summary(tmp_path: Path) -> None:
    (tmp_path / "portfolio-truth-latest.json").write_text(
        json.dumps(_make_truth(elevated=1, moderate=1, baseline=1))
    )
    lookup = build_risk_lookup(tmp_path)
    assert set(lookup) == {"ElevatedRepo0", "ModerateRepo0", "BaselineRepo0"}
    assert lookup["ElevatedRepo0"] == {
        "risk_tier": "elevated",
        "risk_summary": "Elevated repo 0 has weak context.",
    }
    assert lookup["ModerateRepo0"]["risk_tier"] == "moderate"
    assert lookup["BaselineRepo0"]["risk_tier"] == "baseline"


def test_build_risk_lookup_empty_when_truth_absent(tmp_path: Path) -> None:
    assert build_risk_lookup(tmp_path) == {}


def test_build_risk_lookup_empty_when_no_output_dir() -> None:
    assert build_risk_lookup(None) == {}


def test_extract_risk_posture_still_derived_from_same_source(tmp_path: Path) -> None:
    # _extract_risk_posture is reimplemented on top of build_risk_lookup; aggregate
    # counts must still match the per-repo lookup.
    (tmp_path / "portfolio-truth-latest.json").write_text(
        json.dumps(_make_truth(elevated=2, moderate=1, baseline=3))
    )
    pack = build_weekly_review_pack(_make_report(), output_dir=tmp_path)
    risk = pack["risk_posture"]
    lookup = build_risk_lookup(tmp_path)
    elevated = [n for n, e in lookup.items() if e["risk_tier"] == "elevated"]
    assert risk["elevated_count"] == len(elevated) == 2
