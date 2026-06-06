"""Tests for the Arc D bounded-automation eligibility + candidate layer.

This layer is strictly advisory/read-only: it identifies which repos clear the
automation trust bar (high path confidence + trusted portfolio decision quality
+ non-trivial context + eligible registry status). It opens no PRs and applies
no changes — proposal creation and execution land in later Arc D phases.
"""

from __future__ import annotations

from src.portfolio_automation import (
    AutomationCandidate,
    AutomationEligibility,
    evaluate_automation_eligibility,
    select_automation_candidates,
)
from src.weekly_command_center import (
    build_weekly_command_center_digest,
    render_weekly_command_center_markdown,
)


def _project(
    *,
    display_name: str = "Repo",
    repo_full_name: str = "owner/Repo",
    registry_status: str = "active",
    path_confidence: str = "high",
    context_quality: str = "standard",
) -> dict:
    return {
        "identity": {"display_name": display_name, "repo_full_name": repo_full_name},
        "declared": {"operating_path": "maintain"},
        "derived": {
            "registry_status": registry_status,
            "path_confidence": path_confidence,
            "context_quality": context_quality,
        },
    }


# --- evaluate_automation_eligibility ---------------------------------------


def test_fully_eligible_repo_has_no_blockers() -> None:
    result = evaluate_automation_eligibility(_project(), decision_quality_status="trusted")
    assert isinstance(result, AutomationEligibility)
    assert result.eligible is True
    assert result.blockers == ()


def test_non_trusted_decision_quality_blocks() -> None:
    result = evaluate_automation_eligibility(_project(), decision_quality_status="needs-skepticism")
    assert result.eligible is False
    assert "decision-quality-not-trusted" in result.blockers


def test_low_path_confidence_blocks() -> None:
    result = evaluate_automation_eligibility(
        _project(path_confidence="low"), decision_quality_status="trusted"
    )
    assert result.eligible is False
    assert "path-confidence-not-high" in result.blockers


def test_legacy_path_confidence_blocks() -> None:
    result = evaluate_automation_eligibility(
        _project(path_confidence="legacy"), decision_quality_status="trusted"
    )
    assert result.eligible is False
    assert "path-confidence-not-high" in result.blockers


def test_boilerplate_context_blocks() -> None:
    result = evaluate_automation_eligibility(
        _project(context_quality="boilerplate"), decision_quality_status="trusted"
    )
    assert result.eligible is False
    assert "context-quality-too-weak" in result.blockers


def test_none_context_blocks() -> None:
    result = evaluate_automation_eligibility(
        _project(context_quality="none"), decision_quality_status="trusted"
    )
    assert result.eligible is False
    assert "context-quality-too-weak" in result.blockers


def test_unknown_context_blocks_conservatively() -> None:
    result = evaluate_automation_eligibility(
        _project(context_quality=""), decision_quality_status="trusted"
    )
    assert result.eligible is False
    assert "context-quality-too-weak" in result.blockers


def test_archived_registry_status_blocks() -> None:
    result = evaluate_automation_eligibility(
        _project(registry_status="archived"), decision_quality_status="trusted"
    )
    assert result.eligible is False
    assert "registry-status-not-eligible" in result.blockers


def test_candidate_registry_status_is_eligible() -> None:
    result = evaluate_automation_eligibility(
        _project(registry_status="candidate"), decision_quality_status="trusted"
    )
    assert result.eligible is True


def test_minimum_viable_context_is_eligible() -> None:
    result = evaluate_automation_eligibility(
        _project(context_quality="minimum-viable"), decision_quality_status="trusted"
    )
    assert result.eligible is True


def test_multiple_blockers_accumulate() -> None:
    result = evaluate_automation_eligibility(
        _project(registry_status="archived", path_confidence="low", context_quality="none"),
        decision_quality_status="needs-skepticism",
    )
    assert result.eligible is False
    assert set(result.blockers) == {
        "decision-quality-not-trusted",
        "registry-status-not-eligible",
        "path-confidence-not-high",
        "context-quality-too-weak",
    }


# --- select_automation_candidates ------------------------------------------


def test_selects_only_eligible_repos_sorted_by_name() -> None:
    truth = {
        "projects": [
            _project(display_name="Zebra", repo_full_name="o/Zebra"),
            _project(display_name="Alpha", repo_full_name="o/Alpha"),
            _project(display_name="LowPath", path_confidence="low"),
            _project(display_name="Boiler", context_quality="boilerplate"),
            _project(display_name="Archived", registry_status="archived"),
        ]
    }
    candidates = select_automation_candidates(truth, decision_quality_status="trusted")
    assert [c.display_name for c in candidates] == ["Alpha", "Zebra"]
    assert all(isinstance(c, AutomationCandidate) for c in candidates)


def test_non_trusted_decision_quality_yields_no_candidates() -> None:
    # The portfolio-level gate kills every candidate regardless of per-repo state.
    truth = {"projects": [_project(), _project(display_name="Other", repo_full_name="o/Other")]}
    assert select_automation_candidates(truth, decision_quality_status="needs-skepticism") == []


def test_candidate_to_dict_shape() -> None:
    truth = {"projects": [_project(display_name="Solo", repo_full_name="acme/Solo")]}
    [candidate] = select_automation_candidates(truth, decision_quality_status="trusted")
    assert candidate.to_dict() == {
        "repo": "Solo",
        "repo_full_name": "acme/Solo",
        "registry_status": "active",
        "path_confidence": "high",
        "context_quality": "standard",
    }


def test_empty_or_missing_projects_is_safe() -> None:
    assert select_automation_candidates({}, decision_quality_status="trusted") == []
    assert select_automation_candidates({"projects": None}, decision_quality_status="trusted") == []


def test_non_dict_projects_are_skipped() -> None:
    truth = {"projects": ["not-a-dict", _project(display_name="Real", repo_full_name="o/Real")]}
    candidates = select_automation_candidates(truth, decision_quality_status="trusted")
    assert [c.display_name for c in candidates] == ["Real"]


def test_eligible_repo_with_missing_identity_falls_back_safely() -> None:
    # An eligible repo whose identity block is absent must not crash; it falls
    # back to a placeholder name and an empty (honest) slug.
    project = _project()
    del project["identity"]
    candidates = select_automation_candidates(
        {"projects": [project]}, decision_quality_status="trusted"
    )
    assert len(candidates) == 1
    assert candidates[0].display_name == "Repo"
    assert candidates[0].repo_full_name == ""


# --- weekly digest integration ---------------------------------------------


def _digest_for(portfolio_truth: dict, decision_quality_status: str) -> dict:
    operator_summary = {"decision_quality_v1": {"decision_quality_status": decision_quality_status}}
    report_data = {
        "username": "testuser",
        "generated_at": "2026-04-14T12:00:00+00:00",
        "operator_summary": operator_summary,
        "audits": [],
    }
    snapshot = {"operator_summary": operator_summary, "operator_queue": []}
    return build_weekly_command_center_digest(
        report_data,
        snapshot,
        portfolio_truth=portfolio_truth,
        generated_at="2026-04-14T12:00:00+00:00",
    )


def test_digest_surfaces_automation_candidates_when_trusted() -> None:
    truth = {
        "projects": [
            _project(display_name="EligibleOne", repo_full_name="o/EligibleOne"),
            _project(display_name="WeakContext", context_quality="boilerplate"),
        ]
    }
    digest = _digest_for(truth, "trusted")
    candidates = digest["automation_candidates"]
    assert [c["repo"] for c in candidates] == ["EligibleOne"]

    rendered = render_weekly_command_center_markdown(digest)
    assert "## Automation Candidates" in rendered
    assert "EligibleOne" in rendered


def test_digest_has_no_automation_candidates_when_not_trusted() -> None:
    truth = {"projects": [_project(display_name="EligibleOne", repo_full_name="o/EligibleOne")]}
    digest = _digest_for(truth, "needs-skepticism")
    assert digest["automation_candidates"] == []

    rendered = render_weekly_command_center_markdown(digest)
    assert "## Automation Candidates" in rendered
    assert "No repos currently clear the automation trust bar." in rendered
