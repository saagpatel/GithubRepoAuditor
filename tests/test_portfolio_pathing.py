from __future__ import annotations

from src.portfolio_pathing import (
    INVESTIGATE_OVERRIDE,
    build_operating_path_entry,
    build_operating_path_line,
    build_operating_paths_summary,
)


def test_operating_path_prefers_explicit_declared_path() -> None:
    entry = build_operating_path_entry(
        {
            "has_explicit_entry": True,
            "operating_path": "finish",
            "maturity_program": "maintain",
            "intended_disposition": "maintain",
        },
        context_quality="standard",
        intent_alignment="aligned",
        completeness_tier="functional",
        decision_quality_status="trusted",
    )

    assert entry["operating_path"] == "finish"
    assert entry["operating_path_source"] == "explicit-operating-path"
    assert entry["path_confidence"] == "high"
    assert entry["path_override"] == ""


def test_operating_path_uses_investigate_override_for_weak_confidence() -> None:
    entry = build_operating_path_entry(
        {
            "has_explicit_entry": True,
            "maturity_program": "finish",
            "intended_disposition": "",
        },
        context_quality="boilerplate",
        intent_alignment="needs-review",
        completeness_tier="skeleton",
        decision_quality_status="needs-skepticism",
    )

    assert entry["operating_path"] == "finish"
    assert entry["path_confidence"] == "low"
    assert entry["path_override"] == INVESTIGATE_OVERRIDE
    assert "Treat this repo as investigate" in entry["path_rationale"]


def test_operating_path_prefers_intended_disposition_over_defaulted_program() -> None:
    entry = build_operating_path_entry(
        {
            "has_explicit_entry": True,
            "maturity_program": "maintain",
            "intended_disposition": "experiment",
        },
        context_quality="minimum-viable",
        intent_alignment="aligned",
        completeness_tier="functional",
        decision_quality_status="trusted",
    )

    assert entry["operating_path"] == "experiment"
    assert entry["operating_path_source"] == "intended-disposition"


def test_operating_paths_summary_counts_paths_and_overrides() -> None:
    summary = build_operating_paths_summary(
        [
            {"portfolio_catalog": {"operating_path": "maintain", "path_confidence": "high"}},
            {
                "portfolio_catalog": {
                    "operating_path": "finish",
                    "path_confidence": "low",
                    "path_override": INVESTIGATE_OVERRIDE,
                }
            },
            {"portfolio_catalog": {}},
        ]
    )

    assert summary["path_counts"]["maintain"] == 1
    assert summary["path_counts"]["finish"] == 1
    assert summary["path_counts"]["unspecified"] == 1
    assert summary["override_counts"][INVESTIGATE_OVERRIDE] == 1
    assert "Maintain 1" in summary["summary"]
    assert "Finish 1" in summary["summary"]


def test_operating_path_line_mentions_override() -> None:
    line = build_operating_path_line(
        {
            "operating_path": "archive",
            "path_override": INVESTIGATE_OVERRIDE,
            "path_confidence": "low",
            "path_rationale": "Current evidence is contradictory.",
        }
    )

    assert "Archive with Investigate override" in line
    assert "(low confidence)" in line
