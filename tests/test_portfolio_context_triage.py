# tests/test_portfolio_context_triage.py
"""Tests for the context triage runner (Arc H B1)."""

import json

from src.portfolio_context_triage import (
    FailureMode,
    TriageEntry,
    assess_repo_failure_modes,
    run_triage,
)


def _entry(
    description_confidence=1.0,
    readme_stale_by_age=False,
    catalog_completeness=1.0,
    context_quality="full",
    lifecycle_state="active",
) -> dict:
    return {
        "name": "test-repo",
        "analyzers": {
            "description": {"details": {"description_confidence": description_confidence}},
            "readme": {"details": {"readme_stale_by_age": readme_stale_by_age}},
        },
        "catalog_completeness": catalog_completeness,
        "context_quality": context_quality,
        "declared": {"lifecycle_state": lifecycle_state},
    }


def test_no_failure_modes_for_healthy_repo():
    modes = assess_repo_failure_modes(_entry())
    assert modes == []


def test_low_description_confidence_flagged():
    modes = assess_repo_failure_modes(_entry(description_confidence=0.2))
    assert FailureMode.DESCRIPTION in modes


def test_stale_readme_flagged():
    modes = assess_repo_failure_modes(_entry(readme_stale_by_age=True))
    assert FailureMode.README in modes


def test_low_catalog_completeness_flagged():
    modes = assess_repo_failure_modes(_entry(catalog_completeness=0.25))
    assert FailureMode.CATALOG in modes


def test_weak_context_quality_flagged():
    modes = assess_repo_failure_modes(_entry(context_quality="none"))
    assert FailureMode.CONTEXT in modes


def test_nested_portfolio_truth_context_quality_flagged():
    modes = assess_repo_failure_modes(
        {
            "identity": {"display_name": "RepoA"},
            "derived": {"context_quality": "boilerplate"},
        }
    )
    assert FailureMode.CONTEXT in modes


# Context quality is a "can someone resume this?" signal — irrelevant for repos
# that are intentionally not under active development. Archived and dormant
# repos must not be context-flagged even when their docs are boilerplate.


def test_archived_repo_not_context_flagged():
    modes = assess_repo_failure_modes(
        _entry(context_quality="boilerplate", lifecycle_state="archived")
    )
    assert FailureMode.CONTEXT not in modes


def test_dormant_repo_not_context_flagged():
    modes = assess_repo_failure_modes(_entry(context_quality="none", lifecycle_state="dormant"))
    assert FailureMode.CONTEXT not in modes


def test_active_repo_with_weak_context_still_flagged():
    modes = assess_repo_failure_modes(
        _entry(context_quality="boilerplate", lifecycle_state="active")
    )
    assert FailureMode.CONTEXT in modes


def test_maintenance_repo_with_weak_context_still_flagged():
    modes = assess_repo_failure_modes(
        _entry(context_quality="boilerplate", lifecycle_state="maintenance")
    )
    assert FailureMode.CONTEXT in modes


def test_missing_lifecycle_state_defaults_to_flagged():
    # no declared.lifecycle_state -> enforce context quality (do not suppress)
    modes = assess_repo_failure_modes(
        {"identity": {"display_name": "RepoB"}, "context_quality": "none"}
    )
    assert FailureMode.CONTEXT in modes


def test_severity_critical_when_multiple_failure_modes():
    entry = _entry(
        description_confidence=0.2,
        readme_stale_by_age=True,
        catalog_completeness=0.0,
        context_quality="none",
    )
    triage = TriageEntry.from_repo(entry)
    assert triage.severity == "critical"


def test_severity_moderate_for_two_failures():
    entry = _entry(readme_stale_by_age=True, catalog_completeness=0.0)
    triage = TriageEntry.from_repo(entry)
    assert triage.severity == "moderate"


def test_run_triage_returns_only_repos_with_failures():
    repos = [_entry(), _entry(description_confidence=0.2)]
    repos[0]["name"] = "clean-repo"
    repos[1]["name"] = "broken-repo"
    result = run_triage(repos)
    names = [e.repo_name for e in result]
    assert "clean-repo" not in names
    assert "broken-repo" in names


def test_run_triage_to_dict_is_json_serializable():
    repos = [
        _entry(description_confidence=0.2, readme_stale_by_age=True),
        _entry(catalog_completeness=0.0),
        _entry(),  # healthy
    ]
    for i, r in enumerate(repos):
        r["name"] = f"repo-{i}"
    entries = run_triage(repos)
    out = [e.to_dict() for e in entries]
    serialized = json.dumps({"triage": out})
    parsed = json.loads(serialized)
    assert len(parsed["triage"]) == 2  # healthy repo excluded
    assert all("severity" in e for e in parsed["triage"])
    assert all("context_quality_score" in e for e in parsed["triage"])
