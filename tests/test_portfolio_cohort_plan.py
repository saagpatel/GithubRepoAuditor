"""Cohort planner and `PortfolioCohortPlanV1` contract tests."""

from __future__ import annotations

import inspect
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from github_repo_auditor import portfolio_cohort_plan, portfolio_truth_reconcile
from github_repo_auditor.portfolio_cohort_plan import (
    CohortPlanDerivationError,
    build_cohort_plan,
    write_cohort_plan,
)
from github_repo_auditor.portfolio_cohort_plan_contract import (
    CohortPlanError,
    build_cohort_plan_payload,
    derive_transition_kind,
    plan_id_for_payload,
    validate_cohort_plan,
)
from github_repo_auditor.portfolio_truth_publish import publish_portfolio_truth

NOW = datetime(2026, 8, 24, 1, 0, tzinfo=timezone.utc)


def _payload(prospective: tuple[str, ...], prior: tuple[str, ...]) -> dict:
    return build_cohort_plan_payload(
        generated_at=NOW,
        producer_commit="a" * 40,
        producer_repository="saagpatel/GithubRepoAuditor",
        catalog_sha256="c" * 64,
        workspace_root="/Users/d/Projects",
        prior_truth_path="/tmp/portfolio-truth-latest.json",
        prior_truth_sha256="b" * 64,
        prior_truth_generated_at=NOW.isoformat(),
        policy="portfolio-default-attention-v1",
        prospective_repositories=prospective,
        prior_published_repositories=prior,
    )


# --------------------------------------------------------------------------
# contract
# --------------------------------------------------------------------------


def test_plan_derives_required_outgoing_incoming_and_collection() -> None:
    payload = _payload(("d/a", "d/c"), ("d/a", "d/b"))
    plan = validate_cohort_plan(payload)
    assert plan.required_repositories == ("d/a", "d/c")
    assert plan.outgoing_repositories == ("d/b",)
    assert plan.incoming_repositories == ("d/c",)
    assert plan.collection_repositories == ("d/a", "d/b", "d/c")
    assert plan.transition_kind == "swap"
    assert plan.delta_size == 2


@pytest.mark.parametrize(
    ("prospective", "prior", "kind"),
    (
        (("d/a",), ("d/a",), "steady"),
        (("d/a",), ("d/a", "d/b"), "shrink"),
        (("d/a", "d/b"), ("d/a",), "expand"),
        (("d/a", "d/c"), ("d/a", "d/b"), "swap"),
    ),
)
def test_transition_kind_is_derived_not_declared(
    prospective: tuple[str, ...], prior: tuple[str, ...], kind: str
) -> None:
    assert validate_cohort_plan(_payload(prospective, prior)).transition_kind == kind


def test_plan_id_binds_the_whole_body() -> None:
    payload = _payload(("d/a",), ("d/a",))
    payload["cohort"]["required_repositories"] = ["d/z"]
    with pytest.raises(CohortPlanError, match="plan_id does not match"):
        validate_cohort_plan(payload)


def test_plan_rejects_an_inconsistent_collection_set() -> None:
    payload = _payload(("d/a",), ("d/a", "d/b"))
    payload["cohort"]["collection_repositories"] = ["d/a"]
    payload["plan_id"] = plan_id_for_payload(payload)
    with pytest.raises(CohortPlanError, match="collection set must equal"):
        validate_cohort_plan(payload)


def test_plan_rejects_a_declared_kind_that_contradicts_the_delta() -> None:
    payload = _payload(("d/a",), ("d/a", "d/b"))
    payload["cohort"]["transition_kind"] = "steady"
    payload["plan_id"] = plan_id_for_payload(payload)
    with pytest.raises(CohortPlanError, match="transition_kind does not match"):
        validate_cohort_plan(payload)


def test_plan_rejects_unsorted_repositories() -> None:
    payload = _payload(("d/a", "d/b"), ("d/a", "d/b"))
    payload["cohort"]["collection_repositories"] = ["d/b", "d/a"]
    payload["plan_id"] = plan_id_for_payload(payload)
    with pytest.raises(CohortPlanError, match="must be canonically sorted"):
        validate_cohort_plan(payload)


def test_derive_transition_kind_is_total() -> None:
    assert derive_transition_kind((), ()) == "steady"
    assert derive_transition_kind(("d/a",), ()) == "expand"
    assert derive_transition_kind((), ("d/a",)) == "shrink"
    assert derive_transition_kind(("d/a",), ("d/b",)) == "swap"


# --------------------------------------------------------------------------
# H1 — one candidate-derivation implementation
# --------------------------------------------------------------------------


def test_planner_and_producer_share_one_candidate_derivation() -> None:
    assert (
        portfolio_cohort_plan.derive_candidate_cohort
        is portfolio_truth_reconcile.derive_candidate_cohort
    )
    producer_source = inspect.getsource(
        portfolio_truth_reconcile.build_portfolio_truth_snapshot
    )
    planner_source = inspect.getsource(portfolio_cohort_plan.build_cohort_plan)
    assert "derive_candidate_cohort(" in producer_source
    assert "derive_candidate_cohort(" in planner_source
    # A second equivalent algorithm is exactly what this asserts against.
    assert "materialize_projects(" not in planner_source


# --------------------------------------------------------------------------
# planner against a real workspace
# --------------------------------------------------------------------------


def _git_project(root: Path, name: str, repository: str | None) -> None:
    project = root / name
    project.mkdir(parents=True)
    (project / "README.md").write_text(
        f"# {name}\n\nFixture project for the cohort planner contract.\n"
    )
    subprocess.run(["git", "init"], cwd=project, capture_output=True, check=True)
    if repository is not None:
        subprocess.run(
            ["git", "remote", "add", "origin", f"https://github.com/{repository}.git"],
            cwd=project,
            capture_output=True,
            check=True,
        )


CATALOG = """
defaults:
  lifecycle_state: maintenance
  criticality: medium
  review_cadence: monthly
  category: vanity
  tool_provenance: unknown

repos:
  Alpha:
    owner: d
    lifecycle_state: active
    review_cadence: weekly
    intended_disposition: maintain
    operating_path: maintain
    category: commercial
  LocalOnly:
    lifecycle_state: active
    review_cadence: weekly
    intended_disposition: maintain
    operating_path: maintain
    category: commercial
"""


@pytest.fixture
def planner_workspace(tmp_path: Path) -> tuple[Path, Path, Path]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git_project(workspace, "Alpha", "d/Alpha")
    _git_project(workspace, "LocalOnly", None)
    catalog = tmp_path / "portfolio-catalog.yaml"
    catalog.write_text(CATALOG)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    publish_portfolio_truth(
        workspace_root=workspace,
        output_dir=output_dir,
        registry_output=workspace / "project-registry.md",
        portfolio_report_output=workspace / "PORTFOLIO-AUDIT-REPORT.md",
        catalog_path=catalog,
        include_notion=False,
        now=NOW - timedelta(hours=2),
    )
    return workspace, catalog, output_dir


def _plan_for(
    planner_workspace: tuple[Path, Path, Path],
    *,
    monkeypatch: pytest.MonkeyPatch,
    recorder: list | None = None,
) -> dict:
    workspace, catalog, output_dir = planner_workspace

    def _fake_live_status(*, username: str, token: str | None, cache: object) -> None:
        if recorder is not None:
            recorder.append({"username": username, "token": token})
        return None

    monkeypatch.setattr(
        portfolio_cohort_plan, "load_live_repo_status_by_name", _fake_live_status
    )
    return build_cohort_plan(
        truth_path=output_dir / "portfolio-truth-latest.json",
        workspace_root=workspace,
        catalog_path=catalog,
        output_dir=output_dir,
        username="d",
        producer_commit="a" * 40,
        repo_root=workspace,
        include_notion=False,
        now=NOW,
    )


def test_case_04_local_only_project_is_outside_the_github_denominator(
    planner_workspace: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _plan_for(planner_workspace, monkeypatch=monkeypatch)
    cohort = payload["cohort"]
    assert cohort["prospective_repositories"] == ["d/Alpha"]
    assert all("LocalOnly" not in repo for repo in cohort["collection_repositories"])
    assert cohort["transition_kind"] == "steady"


def test_case_05_local_only_gaining_repo_identity_is_planned_as_expansion(
    planner_workspace: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, _catalog, _output_dir = planner_workspace
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/d/LocalOnly.git"],
        cwd=workspace / "LocalOnly",
        capture_output=True,
        check=True,
    )
    payload = _plan_for(planner_workspace, monkeypatch=monkeypatch)
    cohort = payload["cohort"]
    assert cohort["prospective_repositories"] == ["d/Alpha", "d/LocalOnly"]
    assert cohort["incoming_repositories"] == ["d/LocalOnly"]
    assert cohort["outgoing_repositories"] == []
    assert cohort["transition_kind"] == "expand"
    assert cohort["collection_repositories"] == ["d/Alpha", "d/LocalOnly"]


def test_case_26_plan_derivation_uses_the_producer_credential_posture(
    planner_workspace: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The plan must never see a token: the 02:00 candidate pass does not."""
    recorder: list = []
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_should_not_be_used")
    with_token = _plan_for(
        planner_workspace, monkeypatch=monkeypatch, recorder=recorder
    )
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    without_token = _plan_for(planner_workspace, monkeypatch=monkeypatch)

    assert recorder and all(call["token"] is None for call in recorder)
    assert (
        with_token["cohort"]["required_repositories"]
        == without_token["cohort"]["required_repositories"]
    )
    assert with_token["plan_id"] == without_token["plan_id"]


def test_plan_is_written_atomically_and_validates_on_readback(
    planner_workspace: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = _plan_for(planner_workspace, monkeypatch=monkeypatch)
    destination = tmp_path / "plans" / "portfolio-cohort-plan-latest.json"
    digest = write_cohort_plan(payload, destination)
    assert len(digest) == 64
    reread = validate_cohort_plan(json.loads(destination.read_text()))
    assert reread.plan_id == payload["plan_id"]
    assert not list(destination.parent.glob(".*tmp"))


def test_plan_refuses_a_missing_prior_truth(tmp_path: Path) -> None:
    with pytest.raises(CohortPlanDerivationError, match="unreadable"):
        build_cohort_plan(
            truth_path=tmp_path / "absent.json",
            workspace_root=tmp_path,
            catalog_path=tmp_path / "catalog.yaml",
            output_dir=tmp_path,
            username="d",
            producer_commit="a" * 40,
            repo_root=tmp_path,
            include_notion=False,
            now=NOW,
        )


def test_plan_binds_the_prior_truth_digest(
    planner_workspace: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib

    _workspace, _catalog, output_dir = planner_workspace
    truth = output_dir / "portfolio-truth-latest.json"
    payload = _plan_for(planner_workspace, monkeypatch=monkeypatch)
    assert (
        payload["source"]["prior_truth_sha256"]
        == hashlib.sha256(truth.read_bytes()).hexdigest()
    )
    assert payload["producer"]["commit"] == "a" * 40
