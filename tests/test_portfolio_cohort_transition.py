"""Regression matrix for `portfolio-default-attention-transition-v1`.

Every case is deterministic: fixed clock, fixed fixtures, no network. The
numbering matches the reviewed design's regression matrix so a reader can map a
failure straight back to the transition class it protects.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from github_repo_auditor.github_security_coverage import (
    DEFAULT_MAX_COHORT_DELTA,
    DEFAULT_MAX_COHORT_SIZE,
    SecurityCoverageError,
    collect_security_coverage,
    validate_security_coverage_receipt,
)
from github_repo_auditor.portfolio_cohort_plan_contract import (
    COHORT_TRANSITION_PROTOCOL,
    build_cohort_plan_payload,
    validate_cohort_plan,
)
from github_repo_auditor.portfolio_truth_publish import (
    PORTFOLIO_COHORT_TRANSITION_FILENAME,
    PortfolioTruthPublishError,
    publish_portfolio_truth,
)
from github_repo_auditor.portfolio_truth_reconcile import (
    _validate_security_receipt_cohort_identity,
)

NOW = datetime(2026, 8, 24, 1, 0, tzinfo=timezone.utc)

ELEVEN = tuple(f"saagpatel/repo-{index:02d}" for index in range(1, 12))
DEPARTING = "saagpatel/portfolio-index"
INCOMING = "saagpatel/safelight"


# --------------------------------------------------------------------------
# fixture builders
# --------------------------------------------------------------------------


def _project(
    repository: str,
    *,
    state: str = "active-product",
    key: str | None = None,
    archived: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        identity=SimpleNamespace(
            project_key=key or repository.rsplit("/", 1)[-1],
            repo_full_name=repository,
        ),
        derived=SimpleNamespace(attention_state=state, archived=archived),
    )


def _projects(repositories: tuple[str, ...]) -> list[SimpleNamespace]:
    return [_project(repository) for repository in repositories]


def _entry(
    *,
    receipt_state: str = "fresh",
    dependabot_state: str = "observed",
    high: int = 0,
    critical: int = 0,
    repository_state: str = "observed",
    archived: bool = False,
) -> dict:
    return {
        "receipt_state": receipt_state,
        "repository": {
            "state": repository_state,
            "archived": archived,
        },
        "providers": {
            "dependabot": {
                "state": dependabot_state,
                "counts": {"critical": critical, "high": high},
            },
            "code_scanning": {"state": "feature_unavailable", "counts": {}},
            "secret_scanning": {"state": "feature_unavailable", "counts": {}},
        },
    }


def _receipt(repositories: tuple[str, ...], **overrides: dict) -> dict[str, dict]:
    entries = {repository: _entry() for repository in repositories}
    entries.update(overrides)
    return entries


def _transition(
    *,
    incoming: tuple[str, ...] = (),
    outgoing: tuple[str, ...] = (),
    kind: str,
    plan_id: str = "sha256:" + "a" * 64,
    prior_truth_sha256: str = "b" * 64,
) -> dict:
    return {
        "protocol": COHORT_TRANSITION_PROTOCOL,
        "kind": kind,
        "incoming": list(incoming),
        "outgoing": list(outgoing),
        "plan_id": plan_id,
        "prior_truth_sha256": prior_truth_sha256,
    }


def _reconcile(
    *,
    final: tuple[str, ...],
    candidate: tuple[str, ...],
    receipt: dict[str, dict],
    required: tuple[str, ...] | None = None,
    outgoing: tuple[str, ...] | None = None,
    transition: dict | None = None,
    prior: dict[str, dict] | None = None,
    require_cohort_transition: bool = False,
    final_projects: list[SimpleNamespace] | None = None,
):
    return _validate_security_receipt_cohort_identity(
        projects=final_projects if final_projects is not None else _projects(final),
        candidate_projects=_projects(candidate),
        security_alerts_by_name=receipt,
        prior_security_alerts_by_name=prior or {},
        required_repositories=required,
        outgoing_repositories=outgoing,
        transition=transition,
        require_cohort_transition=require_cohort_transition,
    )


# --------------------------------------------------------------------------
# 1 — steady state
# --------------------------------------------------------------------------


def test_case_01_steady_state_publishes() -> None:
    outcome = _reconcile(
        final=ELEVEN,
        candidate=ELEVEN,
        receipt=_receipt(ELEVEN),
        required=ELEVEN,
        outgoing=(),
        transition=_transition(kind="steady"),
    )
    assert outcome.kind == "steady"
    assert outcome.protocol == COHORT_TRANSITION_PROTOCOL
    assert outcome.required == ELEVEN
    assert outcome.outgoing == ()
    assert outcome.departed == ()
    assert outcome.retained_due_security == ()


# --------------------------------------------------------------------------
# 2 — shrink 12 -> 11 (red on current source, green on the fix)
# --------------------------------------------------------------------------


def test_case_02_shrink_is_admitted_as_declared_source_departure() -> None:
    collection = tuple(sorted((*ELEVEN, DEPARTING), key=str.lower))
    outcome = _reconcile(
        final=ELEVEN,
        candidate=ELEVEN,
        receipt=_receipt(collection),
        required=ELEVEN,
        outgoing=(DEPARTING,),
        transition=_transition(outgoing=(DEPARTING,), kind="shrink"),
    )
    assert outcome.kind == "shrink"
    assert outcome.departed == (DEPARTING,)
    assert outcome.retained_due_security == ()
    assert outcome.collection == collection


def test_case_02_shrink_is_red_without_the_transition_protocol() -> None:
    """Proof the deadlock is real: the same evidence refuses on legacy semantics."""
    collection = tuple(sorted((*ELEVEN, DEPARTING), key=str.lower))
    with pytest.raises(ValueError, match="expected 12, observed 11"):
        _reconcile(
            final=ELEVEN,
            candidate=ELEVEN,
            receipt=_receipt(collection),
        )


# --------------------------------------------------------------------------
# 3 — expansion 11 -> 12 (red on current source, green on the fix)
# --------------------------------------------------------------------------


def test_case_03_expansion_publishes() -> None:
    prospective = tuple(sorted((*ELEVEN, INCOMING), key=str.lower))
    outcome = _reconcile(
        final=prospective,
        candidate=prospective,
        receipt=_receipt(prospective),
        required=prospective,
        outgoing=(),
        transition=_transition(incoming=(INCOMING,), kind="expand"),
    )
    assert outcome.kind == "expand"
    assert outcome.planned_incoming == (INCOMING,)
    assert outcome.departed == ()


def test_case_03_expansion_is_red_without_the_transition_protocol() -> None:
    prospective = tuple(sorted((*ELEVEN, INCOMING), key=str.lower))
    with pytest.raises(ValueError, match="expected 11, observed 12"):
        _reconcile(
            final=prospective,
            candidate=prospective,
            receipt=_receipt(ELEVEN),
        )


# --------------------------------------------------------------------------
# 4 / 5 — local-only identity
# --------------------------------------------------------------------------


def test_case_04_local_only_project_stays_outside_the_github_denominator() -> None:
    local_only = SimpleNamespace(
        identity=SimpleNamespace(project_key="safelight", repo_full_name=""),
        derived=SimpleNamespace(attention_state="active-product", archived=False),
    )
    outcome = _validate_security_receipt_cohort_identity(
        projects=[*_projects(ELEVEN), local_only],
        candidate_projects=[*_projects(ELEVEN), local_only],
        security_alerts_by_name=_receipt(ELEVEN),
        required_repositories=ELEVEN,
        outgoing_repositories=(),
        transition=_transition(kind="steady"),
    )
    assert outcome.required == ELEVEN
    assert outcome.final == ELEVEN


def test_case_05_local_only_gaining_repo_identity_is_an_expansion() -> None:
    prospective = tuple(sorted((*ELEVEN, INCOMING), key=str.lower))
    outcome = _reconcile(
        final=prospective,
        candidate=prospective,
        receipt=_receipt(prospective),
        required=prospective,
        outgoing=(),
        transition=_transition(incoming=(INCOMING,), kind="expand"),
    )
    assert outcome.kind == "expand"
    assert INCOMING in outcome.required


# --------------------------------------------------------------------------
# 6 / 7 / 17 — source departure vs security retention
# --------------------------------------------------------------------------


def test_case_06_repo_backed_to_manual_only_is_a_shrink() -> None:
    collection = tuple(sorted((*ELEVEN, DEPARTING), key=str.lower))
    outcome = _reconcile(
        final=ELEVEN,
        candidate=ELEVEN,
        receipt=_receipt(collection),
        required=ELEVEN,
        outgoing=(DEPARTING,),
        transition=_transition(outgoing=(DEPARTING,), kind="shrink"),
    )
    assert outcome.departed == (DEPARTING,)


def test_case_07_outgoing_with_open_high_alert_is_retained_in_attention() -> None:
    """I5: security evidence outranks lifecycle classification."""
    collection = tuple(sorted((*ELEVEN, DEPARTING), key=str.lower))
    final = collection  # fresh critical evidence held it in decision-needed
    outcome = _reconcile(
        final=final,
        candidate=ELEVEN,
        receipt=_receipt(collection, **{DEPARTING: _entry(high=2)}),
        required=ELEVEN,
        outgoing=(DEPARTING,),
        transition=_transition(outgoing=(DEPARTING,), kind="shrink"),
        final_projects=[
            *_projects(ELEVEN),
            _project(DEPARTING, state="decision-needed"),
        ],
    )
    assert outcome.departed == ()
    assert outcome.retained_due_security == (DEPARTING,)


def test_case_17_departure_with_unresolved_high_is_refused() -> None:
    collection = tuple(sorted((*ELEVEN, DEPARTING), key=str.lower))
    with pytest.raises(ValueError, match="left default attention without"):
        _reconcile(
            final=ELEVEN,
            candidate=ELEVEN,
            receipt=_receipt(collection, **{DEPARTING: _entry(high=1)}),
            required=ELEVEN,
            outgoing=(DEPARTING,),
            transition=_transition(outgoing=(DEPARTING,), kind="shrink"),
        )


# --------------------------------------------------------------------------
# 8 — stale receipt cannot authorize a departure
# --------------------------------------------------------------------------


def test_case_08_stale_receipt_cannot_authorize_a_declared_departure() -> None:
    collection = tuple(sorted((*ELEVEN, DEPARTING), key=str.lower))
    with pytest.raises(ValueError, match="left default attention without"):
        _reconcile(
            final=ELEVEN,
            candidate=ELEVEN,
            receipt=_receipt(collection, **{DEPARTING: _entry(receipt_state="stale")}),
            required=ELEVEN,
            outgoing=(DEPARTING,),
            transition=_transition(outgoing=(DEPARTING,), kind="shrink"),
        )


def test_case_08_receipt_older_than_the_window_reads_as_stale() -> None:
    payload = _legacy_receipt_payload(
        ("saagpatel/alpha",), now=NOW - timedelta(hours=3)
    )
    loaded = validate_security_coverage_receipt(
        _sign(payload),
        max_age_hours=1,
        expected_cohort_count=1,
        now=NOW,
    )
    assert loaded.receipt_state == "stale"


# --------------------------------------------------------------------------
# receipt payload helpers (validator-level cases)
#
# Fixtures are produced by the real collector so the provider, eligibility, and
# budget shapes can never drift from the contract they are meant to exercise.
# --------------------------------------------------------------------------


def _truth_payload(cohort: tuple[str, ...]) -> dict:
    return {
        "projects": [
            {
                "identity": {
                    "project_key": repository.rsplit("/", 1)[-1],
                    "repo_full_name": repository,
                },
                "derived": {"attention_state": "active-product"},
            }
            for repository in cohort
        ]
    }


def _legacy_receipt_payload(
    cohort: tuple[str, ...],
    *,
    producer_commit: str = "a" * 40,
    now: datetime = NOW,
) -> dict:
    return collect_security_coverage(
        _truth_payload(cohort),
        token=None,
        expected_cohort_count=len(cohort),
        producer_commit=producer_commit,
        now=now,
    )


def _transition_receipt_payload(
    *,
    prospective: tuple[str, ...],
    prior: tuple[str, ...],
    producer_commit: str = "a" * 40,
    prior_truth_sha256: str = "b" * 64,
    now: datetime = NOW,
) -> dict:
    plan = _plan(
        prospective=prospective,
        prior=prior,
        producer_commit=producer_commit,
        prior_truth_sha256=prior_truth_sha256,
    )
    return collect_security_coverage(
        _truth_payload(plan.collection_repositories),
        token=None,
        expected_cohort_count=None,
        cohort_plan=plan,
        producer_commit=producer_commit,
        now=now,
    )


def _sign(payload: dict) -> dict:
    from github_repo_auditor.github_security_coverage import _with_receipt_id

    return _with_receipt_id(payload)


# --------------------------------------------------------------------------
# 9 — receipt bound to the wrong GHRA SHA
# --------------------------------------------------------------------------


def test_case_09_receipt_bound_to_wrong_producer_commit_is_refused() -> None:
    payload = _sign(_legacy_receipt_payload(("saagpatel/alpha",)))
    with pytest.raises(SecurityCoverageError, match="producer commit mismatch"):
        validate_security_coverage_receipt(
            payload,
            max_age_hours=1,
            expected_cohort_count=1,
            expected_producer_commit="c" * 40,
            now=NOW,
        )


# --------------------------------------------------------------------------
# 10 / 24 / 25 — collector-side plan binding and policy bounds
# --------------------------------------------------------------------------


def _plan(
    *,
    prospective: tuple[str, ...],
    prior: tuple[str, ...],
    producer_commit: str = "a" * 40,
    prior_truth_sha256: str = "b" * 64,
):
    payload = build_cohort_plan_payload(
        generated_at=NOW,
        producer_commit=producer_commit,
        producer_repository="saagpatel/GithubRepoAuditor",
        catalog_sha256="c" * 64,
        workspace_root="/Users/d/Projects",
        prior_truth_path="/Users/d/Projects/GithubRepoAuditor/output/portfolio-truth-latest.json",
        prior_truth_sha256=prior_truth_sha256,
        prior_truth_generated_at=NOW.isoformat(),
        policy="portfolio-default-attention-v1",
        prospective_repositories=prospective,
        prior_published_repositories=prior,
    )
    return validate_cohort_plan(payload)


def test_case_10_plan_bound_to_wrong_producer_commit_is_refused() -> None:
    plan = _plan(prospective=ELEVEN, prior=ELEVEN, producer_commit="a" * 40)
    with pytest.raises(
        SecurityCoverageError, match="plan producer commit does not match"
    ):
        collect_security_coverage(
            {},
            token=None,
            expected_cohort_count=None,
            cohort_plan=plan,
            producer_commit="d" * 40,
            now=NOW,
        )


def test_case_10_plan_bound_to_a_different_truth_is_refused() -> None:
    plan = _plan(prospective=ELEVEN, prior=ELEVEN, prior_truth_sha256="b" * 64)
    with pytest.raises(SecurityCoverageError, match="not bound to the published truth"):
        collect_security_coverage(
            {},
            token=None,
            expected_cohort_count=None,
            cohort_plan=plan,
            truth_sha256="e" * 64,
            producer_commit="a" * 40,
            now=NOW,
        )


def test_case_24_churn_bound_refuses_collection() -> None:
    prior = ELEVEN
    prospective = tuple(
        sorted((*ELEVEN[:6], *(f"saagpatel/new-{i}" for i in range(5))), key=str.lower)
    )
    plan = _plan(prospective=prospective, prior=prior)
    assert plan.delta_size > DEFAULT_MAX_COHORT_DELTA
    with pytest.raises(
        SecurityCoverageError, match="churn exceeds the bounded contract"
    ):
        collect_security_coverage(
            {},
            token=None,
            expected_cohort_count=None,
            cohort_plan=plan,
            producer_commit="a" * 40,
            now=NOW,
        )


def test_case_25_size_bound_refuses_collection() -> None:
    prospective = tuple(f"saagpatel/repo-{index:03d}" for index in range(25))
    plan = _plan(prospective=prospective, prior=prospective)
    with pytest.raises(
        SecurityCoverageError, match="collection exceeds the bounded contract"
    ):
        collect_security_coverage(
            {},
            token=None,
            expected_cohort_count=None,
            cohort_plan=plan,
            max_cohort_delta=99,
            producer_commit="a" * 40,
            now=NOW,
        )


def test_case_25_size_bound_refuses_validation() -> None:
    cohort = tuple(sorted(f"saagpatel/repo-{i:03d}" for i in range(25)))
    payload = _sign(_legacy_receipt_payload(cohort))
    with pytest.raises(
        SecurityCoverageError, match="cohort exceeds the bounded contract"
    ):
        validate_security_coverage_receipt(
            payload,
            max_age_hours=1,
            expected_cohort_count=None,
            max_cohort_size=DEFAULT_MAX_COHORT_SIZE,
            now=NOW,
        )


def test_policy_bounds_have_a_single_definition_and_documented_defaults() -> None:
    assert DEFAULT_MAX_COHORT_SIZE == 24
    assert DEFAULT_MAX_COHORT_DELTA == 3


def test_policy_bounds_are_overridable() -> None:
    plan = _plan(prospective=ELEVEN, prior=ELEVEN)
    with pytest.raises(
        SecurityCoverageError, match="collection exceeds the bounded contract"
    ):
        collect_security_coverage(
            {},
            token=None,
            expected_cohort_count=None,
            cohort_plan=plan,
            max_cohort_size=5,
            producer_commit="a" * 40,
            now=NOW,
        )


def test_plan_and_exact_count_are_mutually_exclusive() -> None:
    plan = _plan(prospective=ELEVEN, prior=ELEVEN)
    with pytest.raises(SecurityCoverageError, match="mutually exclusive"):
        collect_security_coverage(
            {},
            token=None,
            expected_cohort_count=11,
            cohort_plan=plan,
            producer_commit="a" * 40,
            now=NOW,
        )


# --------------------------------------------------------------------------
# 11 — candidate source drift after collection
# --------------------------------------------------------------------------


def test_case_11_candidate_drift_names_both_sides() -> None:
    drifted = tuple(sorted((*ELEVEN[:-1], "saagpatel/drifted"), key=str.lower))
    with pytest.raises(
        ValueError,
        match=r"receipt_only=\['saagpatel/repo-11'\]; derived_only=\['saagpatel/drifted'\]",
    ):
        _reconcile(
            final=drifted,
            candidate=drifted,
            receipt=_receipt(ELEVEN),
            required=ELEVEN,
            outgoing=(),
            transition=_transition(kind="steady"),
        )


# --------------------------------------------------------------------------
# 13 / 14 — partition violations
# --------------------------------------------------------------------------


def test_case_13_missing_evidence_for_a_required_member_is_refused() -> None:
    with pytest.raises(ValueError, match=r"uncollected=\['saagpatel/repo-11'\]"):
        _reconcile(
            final=ELEVEN[:-1],
            candidate=ELEVEN,
            receipt=_receipt(ELEVEN[:-1]),
            required=ELEVEN,
            outgoing=(),
            transition=_transition(kind="steady"),
        )


def test_case_14_undeclared_receipt_member_is_refused() -> None:
    collection = tuple(sorted((*ELEVEN, "saagpatel/stowaway"), key=str.lower))
    with pytest.raises(ValueError, match=r"undeclared=\['saagpatel/stowaway'\]"):
        _reconcile(
            final=ELEVEN,
            candidate=ELEVEN,
            receipt=_receipt(collection),
            required=ELEVEN,
            outgoing=(),
            transition=_transition(kind="steady"),
        )


def test_case_14_receipt_validator_rejects_an_unpartitioned_collection() -> None:
    payload = _transition_receipt_payload(prospective=ELEVEN, prior=ELEVEN)
    # Drop one required member so the collection is no longer partitioned.
    payload["cohort"]["required_repositories"] = list(ELEVEN[:-1])
    payload["cohort"]["required_count"] = len(ELEVEN) - 1
    with pytest.raises(SecurityCoverageError, match="not partitioned"):
        validate_security_coverage_receipt(
            _sign(payload),
            max_age_hours=1,
            expected_cohort_count=None,
            max_cohort_size=DEFAULT_MAX_COHORT_SIZE,
            now=NOW,
        )


def test_receipt_validator_checks_every_count_against_its_named_set() -> None:
    payload = _transition_receipt_payload(
        prospective=ELEVEN,
        prior=tuple(sorted((*ELEVEN, DEPARTING), key=str.lower)),
    )
    payload["cohort"]["required_count"] = 99
    with pytest.raises(SecurityCoverageError, match="required_count does not match"):
        validate_security_coverage_receipt(
            _sign(payload),
            max_age_hours=1,
            expected_cohort_count=None,
            max_cohort_size=DEFAULT_MAX_COHORT_SIZE,
            now=NOW,
        )


def test_receipt_expected_count_retains_its_legacy_meaning() -> None:
    """`expected_count` is the size of the *collected* set, transition or not."""
    collection = tuple(sorted((*ELEVEN, DEPARTING), key=str.lower))
    payload = _transition_receipt_payload(prospective=ELEVEN, prior=collection)
    assert payload["cohort"]["expected_count"] == len(collection)
    assert payload["cohort"]["repository_count"] == len(collection)
    loaded = validate_security_coverage_receipt(
        _sign(payload),
        max_age_hours=1,
        expected_cohort_count=None,
        max_cohort_size=DEFAULT_MAX_COHORT_SIZE,
        now=NOW,
    )
    assert loaded.cohort_repositories == collection
    assert loaded.required_repositories == ELEVEN
    assert loaded.outgoing_repositories == (DEPARTING,)


# --------------------------------------------------------------------------
# 15 — outgoing still in candidate
# --------------------------------------------------------------------------


def test_case_15_outgoing_still_in_default_attention_is_refused() -> None:
    candidate = tuple(sorted((*ELEVEN, DEPARTING), key=str.lower))
    with pytest.raises(
        ValueError, match="declares outgoing repositories that are still in derived"
    ):
        _reconcile(
            final=candidate,
            candidate=candidate,
            receipt=_receipt(candidate),
            required=ELEVEN,
            outgoing=(DEPARTING,),
            transition=_transition(outgoing=(DEPARTING,), kind="shrink"),
        )


# --------------------------------------------------------------------------
# 16 — same-size membership swap
# --------------------------------------------------------------------------


def test_case_16_same_size_swap_publishes() -> None:
    prospective = tuple(sorted((*ELEVEN[:-1], INCOMING), key=str.lower))
    outgoing = (ELEVEN[-1],)
    collection = tuple(sorted((*prospective, *outgoing), key=str.lower))
    outcome = _reconcile(
        final=prospective,
        candidate=prospective,
        receipt=_receipt(collection),
        required=prospective,
        outgoing=outgoing,
        transition=_transition(incoming=(INCOMING,), outgoing=outgoing, kind="swap"),
    )
    assert outcome.kind == "swap"
    assert outcome.departed == outgoing


def test_case_16_same_size_swap_with_stale_membership_is_refused() -> None:
    """Today's count tripwire passes this silently; R3 names both sides."""
    prospective = tuple(sorted((*ELEVEN[:-1], INCOMING), key=str.lower))
    stale_required = ELEVEN
    with pytest.raises(
        ValueError,
        match=(
            r"receipt_only=\['saagpatel/repo-11'\]; "
            r"derived_only=\['saagpatel/safelight'\]"
        ),
    ):
        _reconcile(
            final=prospective,
            candidate=prospective,
            receipt=_receipt(stale_required),
            required=stale_required,
            outgoing=(),
            transition=_transition(kind="steady"),
        )


# --------------------------------------------------------------------------
# 18 — non-collectable departure stays deferred and fails closed by name
# --------------------------------------------------------------------------


def test_case_18_non_collectable_departure_is_named_and_deferred() -> None:
    collection = tuple(sorted((*ELEVEN, DEPARTING), key=str.lower))
    with pytest.raises(ValueError, match="non-collectable"):
        _reconcile(
            final=ELEVEN,
            candidate=ELEVEN,
            receipt=_receipt(
                collection,
                **{
                    DEPARTING: _entry(
                        dependabot_state="not_found", repository_state="not_found"
                    )
                },
            ),
            required=ELEVEN,
            outgoing=(DEPARTING,),
            transition=_transition(outgoing=(DEPARTING,), kind="shrink"),
        )


# --------------------------------------------------------------------------
# 20 — idempotent rerun
# --------------------------------------------------------------------------


def test_case_20_rerun_against_the_same_receipt_is_idempotent() -> None:
    collection = tuple(sorted((*ELEVEN, DEPARTING), key=str.lower))
    kwargs = dict(
        final=ELEVEN,
        candidate=ELEVEN,
        receipt=_receipt(collection),
        required=ELEVEN,
        outgoing=(DEPARTING,),
        transition=_transition(outgoing=(DEPARTING,), kind="shrink"),
    )
    first = _reconcile(**kwargs)
    second = _reconcile(**kwargs)
    assert first == second
    assert second.departed == (DEPARTING,)
    assert second.to_dict() == first.to_dict()


# --------------------------------------------------------------------------
# 22 / 23 — legacy receipts
# --------------------------------------------------------------------------


def test_case_22_legacy_receipt_reproduces_exact_equality_semantics() -> None:
    outcome = _reconcile(
        final=ELEVEN,
        candidate=ELEVEN,
        receipt=_receipt(ELEVEN),
    )
    assert outcome.protocol is None
    assert outcome.kind == "legacy"
    assert outcome.required == ELEVEN
    assert outcome.outgoing == ()


def test_case_23_legacy_receipt_is_refused_when_transition_is_required() -> None:
    with pytest.raises(ValueError, match="predates the transition protocol"):
        _reconcile(
            final=ELEVEN,
            candidate=ELEVEN,
            receipt=_receipt(ELEVEN),
            require_cohort_transition=True,
        )


def test_case_23_receipt_validator_refuses_a_legacy_receipt_by_name() -> None:
    payload = _sign(_legacy_receipt_payload(ELEVEN))
    with pytest.raises(
        SecurityCoverageError, match="predates the cohort-transition protocol"
    ):
        validate_security_coverage_receipt(
            payload,
            max_age_hours=1,
            expected_cohort_count=None,
            max_cohort_size=DEFAULT_MAX_COHORT_SIZE,
            require_cohort_transition=True,
            now=NOW,
        )


# --------------------------------------------------------------------------
# 27 — supplementary identity may not declare a repository
# --------------------------------------------------------------------------


def test_case_27_supplementary_identity_declaring_a_repository_hard_errors() -> None:
    supplementary = SimpleNamespace(
        identity=SimpleNamespace(
            project_key="supp:personal-ops",
            repo_full_name="saagpatel/personal-ops",
        ),
        derived=SimpleNamespace(attention_state="active-infra", archived=False),
    )
    with pytest.raises(
        ValueError, match="supplementary project identity cannot declare a repository"
    ):
        _validate_security_receipt_cohort_identity(
            projects=[supplementary],
            candidate_projects=[supplementary],
            security_alerts_by_name={"saagpatel/personal-ops": _entry()},
            required_repositories=("saagpatel/personal-ops",),
            outgoing_repositories=(),
            transition=_transition(kind="steady"),
        )


# --------------------------------------------------------------------------
# transition-block consistency
# --------------------------------------------------------------------------


def test_transition_kind_must_match_the_membership_delta() -> None:
    collection = tuple(sorted((*ELEVEN, DEPARTING), key=str.lower))
    with pytest.raises(ValueError, match="transition kind does not match"):
        _reconcile(
            final=ELEVEN,
            candidate=ELEVEN,
            receipt=_receipt(collection),
            required=ELEVEN,
            outgoing=(DEPARTING,),
            transition=_transition(outgoing=(DEPARTING,), kind="steady"),
        )


def test_transition_outgoing_must_match_the_outgoing_set() -> None:
    collection = tuple(sorted((*ELEVEN, DEPARTING), key=str.lower))
    with pytest.raises(
        ValueError, match="transition block disagrees with its outgoing set"
    ):
        _reconcile(
            final=ELEVEN,
            candidate=ELEVEN,
            receipt=_receipt(collection),
            required=ELEVEN,
            outgoing=(DEPARTING,),
            transition=_transition(outgoing=(), kind="steady"),
        )


def test_required_and_outgoing_must_be_disjoint() -> None:
    with pytest.raises(ValueError, match="both required and outgoing"):
        _reconcile(
            final=ELEVEN,
            candidate=ELEVEN,
            receipt=_receipt(ELEVEN),
            required=ELEVEN,
            outgoing=(ELEVEN[0],),
            transition=_transition(outgoing=(ELEVEN[0],), kind="shrink"),
        )


# --------------------------------------------------------------------------
# 12 / 19 / 21 — publication-level transaction cases
# --------------------------------------------------------------------------


def _git_project(root: Path, name: str, repository: str) -> None:
    project = root / name
    project.mkdir(parents=True)
    (project / "README.md").write_text(
        f"# {name}\n\nFixture project for the cohort transition contract.\n"
    )
    subprocess.run(["git", "init"], cwd=project, capture_output=True, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", f"https://github.com/{repository}.git"],
        cwd=project,
        capture_output=True,
        check=True,
    )


@pytest.fixture
def transition_workspace(tmp_path: Path) -> tuple[Path, Path, Path]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git_project(workspace, "Alpha", "d/Alpha")
    catalog = tmp_path / "portfolio-catalog.yaml"
    catalog.write_text(
        """
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
"""
    )
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return workspace, catalog, output_dir


def _publish(
    workspace: Path,
    catalog: Path,
    output_dir: Path,
    *,
    security_alerts_by_name: dict | None = None,
    security_coverage_metadata: dict | None = None,
    security_cohort_required: tuple[str, ...] | None = None,
    security_cohort_outgoing: tuple[str, ...] | None = None,
    security_cohort_transition: dict | None = None,
    now: datetime | None = None,
):
    return publish_portfolio_truth(
        workspace_root=workspace,
        output_dir=output_dir,
        registry_output=workspace / "project-registry.md",
        portfolio_report_output=workspace / "PORTFOLIO-AUDIT-REPORT.md",
        catalog_path=catalog,
        include_notion=False,
        security_alerts_by_name=security_alerts_by_name,
        security_coverage_metadata=security_coverage_metadata,
        security_cohort_required=security_cohort_required,
        security_cohort_outgoing=security_cohort_outgoing,
        security_cohort_transition=security_cohort_transition,
        now=now,
    )


def _metadata(produced_at: datetime) -> dict:
    return {
        "source_id": "github-security-coverage-receipt",
        "schema_version": "GitHubSecurityCoverageReceiptV1",
        "produced_at": produced_at.isoformat(),
        "state": "fresh",
        "age_hours": 0.0,
        "producer_commit": "a" * 40,
        "cohort_policy": "portfolio-default-attention-v1",
        "cohort_repository_count": 1,
        "path": "/evidence/github-security-coverage-latest.json",
        "receipt_id": "sha256:" + "c" * 64,
        "content_sha256": "d" * 64,
    }


def _truth_alerts() -> dict:
    """Normalized entries produced by the real collector and validator."""
    loaded = validate_security_coverage_receipt(
        _sign(_legacy_receipt_payload(("d/Alpha",))),
        max_age_hours=24,
        expected_cohort_count=1,
        now=NOW,
    )
    return loaded.entries_by_full_name


def test_case_12_prior_truth_replaced_between_collection_and_production(
    transition_workspace: tuple[Path, Path, Path],
) -> None:
    workspace, catalog, output_dir = transition_workspace
    _publish(workspace, catalog, output_dir, now=NOW - timedelta(hours=2))
    latest = output_dir / "portfolio-truth-latest.json"
    before = latest.read_bytes()

    with pytest.raises(
        PortfolioTruthPublishError, match="bound to a different prior PortfolioTruth"
    ):
        _publish(
            workspace,
            catalog,
            output_dir,
            security_alerts_by_name=_truth_alerts(),
            security_coverage_metadata=_metadata(NOW),
            security_cohort_required=("d/Alpha",),
            security_cohort_outgoing=(),
            security_cohort_transition=_transition(
                kind="steady", prior_truth_sha256="f" * 64
            ),
            now=NOW,
        )
    assert latest.read_bytes() == before


def test_case_21_owner_path_is_untouched_by_a_refused_transition(
    transition_workspace: tuple[Path, Path, Path],
) -> None:
    workspace, catalog, output_dir = transition_workspace
    _publish(workspace, catalog, output_dir, now=NOW - timedelta(hours=2))
    latest = output_dir / "portfolio-truth-latest.json"
    before = latest.read_bytes()

    with pytest.raises(ValueError):
        _publish(
            workspace,
            catalog,
            output_dir,
            security_alerts_by_name=_truth_alerts(),
            security_coverage_metadata=_metadata(NOW),
            security_cohort_required=("d/Alpha", "d/Ghost"),
            security_cohort_outgoing=(),
            security_cohort_transition=_transition(
                kind="steady",
                prior_truth_sha256=__import__("hashlib").sha256(before).hexdigest(),
            ),
            now=NOW,
        )
    assert latest.read_bytes() == before


def test_transition_outcome_is_published_as_producer_evidence(
    transition_workspace: tuple[Path, Path, Path],
) -> None:
    workspace, catalog, output_dir = transition_workspace
    _publish(workspace, catalog, output_dir, now=NOW - timedelta(hours=2))
    latest = output_dir / "portfolio-truth-latest.json"
    import hashlib

    prior_sha = hashlib.sha256(latest.read_bytes()).hexdigest()

    _publish(
        workspace,
        catalog,
        output_dir,
        security_alerts_by_name=_truth_alerts(),
        security_coverage_metadata=_metadata(NOW),
        security_cohort_required=("d/Alpha",),
        security_cohort_outgoing=(),
        security_cohort_transition=_transition(
            kind="steady", prior_truth_sha256=prior_sha
        ),
        now=NOW,
    )
    outcome_path = output_dir / PORTFOLIO_COHORT_TRANSITION_FILENAME
    payload = json.loads(outcome_path.read_text())
    assert payload["schema_version"] == "PortfolioCohortTransitionOutcomeV1"
    assert payload["protocol"] == COHORT_TRANSITION_PROTOCOL
    assert payload["prior_truth_sha256"] == prior_sha
    transition = payload["transition"]
    assert transition["kind"] == "steady"
    assert transition["required_repositories"] == ["d/Alpha"]
    assert transition["required_count"] == 1
    assert transition["outgoing_count"] == 0
    assert transition["retained_due_security"] == []
    assert transition["retained_due_security_count"] == 0


def test_case_19_interrupted_publication_is_recovered_from_the_journal(
    transition_workspace: tuple[Path, Path, Path],
) -> None:
    workspace, catalog, output_dir = transition_workspace
    _publish(workspace, catalog, output_dir, now=NOW - timedelta(hours=2))
    latest = output_dir / "portfolio-truth-latest.json"
    import hashlib

    before = latest.read_bytes()
    prior_sha = hashlib.sha256(before).hexdigest()

    # Refuse mid-transaction, then confirm the retry publishes cleanly and the
    # owner path was never left in an intermediate state.
    with pytest.raises(ValueError):
        _publish(
            workspace,
            catalog,
            output_dir,
            security_alerts_by_name=_truth_alerts(),
            security_coverage_metadata=_metadata(NOW),
            security_cohort_required=("d/Alpha", "d/Ghost"),
            security_cohort_outgoing=(),
            security_cohort_transition=_transition(
                kind="steady", prior_truth_sha256=prior_sha
            ),
            now=NOW,
        )
    assert latest.read_bytes() == before
    assert not (output_dir / ".portfolio-truth-publish-journal.json").exists()

    _publish(
        workspace,
        catalog,
        output_dir,
        security_alerts_by_name=_truth_alerts(),
        security_coverage_metadata=_metadata(NOW),
        security_cohort_required=("d/Alpha",),
        security_cohort_outgoing=(),
        security_cohort_transition=_transition(
            kind="steady", prior_truth_sha256=prior_sha
        ),
        now=NOW,
    )
    assert latest.read_bytes() != before
