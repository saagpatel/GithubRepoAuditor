from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import cast

import pytest

from src.pr_head_evidence import (
    SnapshotValidationError,
    evaluate_snapshot,
    parse_snapshot,
)

HEAD_A = "a" * 40
HEAD_B = "b" * 40
BASE = "c" * 40


def _review(
    *,
    review_id: int = 1,
    actor: str = "alice",
    state: str = "APPROVED",
    commit_id: str = HEAD_A,
    submitted_at: str | None = "2026-07-28T10:05:00Z",
    can_count: bool | None = True,
) -> dict[str, object]:
    dismissed = state == "DISMISSED"
    return {
        "id": review_id,
        "actor": {"login": actor, "can_count": can_count},
        "state": state,
        "commit_id": commit_id,
        "submitted_at": submitted_at,
        "dismissal": {
            "dismissed": dismissed,
            "dismissed_at": "2026-07-28T10:06:00Z" if dismissed else None,
            "prior_state": "APPROVED" if dismissed else None,
        },
    }


def _check(
    *,
    check_id: int = 10,
    kind: str = "check_run",
    name: str = "ci/test",
    head_sha: str = HEAD_A,
    status: str = "completed",
    conclusion: str | None = "success",
    integration_id: int | None = 99,
) -> dict[str, object]:
    return {
        "id": check_id,
        "kind": kind,
        "name": name,
        "head_sha": head_sha,
        "status": status,
        "conclusion": conclusion,
        "integration_id": integration_id,
    }


def _snapshot(
    *,
    head_sha: str = HEAD_A,
    reviews: list[dict[str, object]] | None = None,
    checks: list[dict[str, object]] | None = None,
    required_approvals: int = 1,
    dismiss_stale_reviews: bool = True,
    require_last_push_approval: bool = False,
    rule_items: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    if reviews is None:
        reviews = [_review(commit_id=head_sha)]
    if checks is None:
        checks = [_check(head_sha=head_sha)]
    if rule_items is None:
        rule_items = [
            {
                "type": "pull_request",
                "required_approving_review_count": required_approvals,
                "dismiss_stale_reviews": dismiss_stale_reviews,
                "require_last_push_approval": require_last_push_approval,
                "require_code_owner_reviews": False,
            },
            {
                "type": "required_status_checks",
                "strict_required_status_checks_policy": False,
                "checks": [{"context": "ci/test", "integration_id": 99}],
            },
        ]
    return {
        "schema_version": "PRHeadEvidenceV1",
        "pull_request": {
            "repository": "octo/example",
            "number": 42,
            "author": "author",
            "head_sha": head_sha,
            "base_sha": BASE,
        },
        "latest_reviewable_push": {
            "pushed_at": "2026-07-28T10:00:00Z",
            "actor": "bob",
        },
        "reviews": reviews,
        "checks": checks,
        "rules": {
            "source": "branch_protection",
            "availability": "available",
            "items": rule_items,
        },
        "coverage": {
            "reviews": {
                "permission": "granted",
                "complete": True,
                "truncated": False,
                "pages_fetched": 1,
            },
            "checks": {
                "permission": "granted",
                "complete": True,
                "truncated": False,
                "pages_fetched": 1,
            },
            "rules": {
                "permission": "granted",
                "complete": True,
                "truncated": False,
                "pages_fetched": 1,
            },
        },
        "provenance": {
            "source": "synthetic_fixture",
            "captured_at": "2026-07-28T10:10:00Z",
            "freshness": "current",
        },
    }


def _evaluate(value: dict[str, object]) -> dict[str, object]:
    return evaluate_snapshot(parse_snapshot(value))


def _requirements(verdict: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], verdict["requirements"])


def _approval_result(verdict: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], _requirements(verdict)["approvals"])


def _check_result(verdict: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], _requirements(verdict)["checks"])


def test_valid_approval_and_check_set_is_current() -> None:
    verdict = _evaluate(_snapshot())

    assert verdict["schema_version"] == "PRHeadEvidenceVerdictV1"
    assert verdict["state"] == "current"
    assert verdict["current"] is True
    assert verdict["head_sha"] == HEAD_A
    assert _approval_result(verdict)["head_bound_count"] == 1
    assert _check_result(verdict)["all_required_checks_successful"] is True


def test_head_advance_invalidates_only_sha_bound_evidence_and_preserves_history() -> (
    None
):
    original_snapshot = _snapshot()
    original_verdict = _evaluate(original_snapshot)
    advanced = copy.deepcopy(original_snapshot)
    cast(dict[str, object], advanced["pull_request"])["head_sha"] = HEAD_B

    advanced_verdict = _evaluate(advanced)

    assert original_verdict["state"] == "current"
    assert original_verdict["head_sha"] == HEAD_A
    assert advanced_verdict["state"] == "stale"
    review_rows = cast(list[dict[str, object]], advanced_verdict["reviews"])
    check_rows = cast(list[dict[str, object]], advanced_verdict["checks"])
    assert review_rows[0]["commit_id"] == HEAD_A
    assert review_rows[0]["binding_state"] == "stale"
    assert check_rows[0]["head_sha"] == HEAD_A
    assert check_rows[0]["binding_state"] == "stale"
    assert original_verdict == _evaluate(original_snapshot)


def test_old_approval_can_be_retained_by_rule_without_becoming_head_bound() -> None:
    snapshot = _snapshot(
        head_sha=HEAD_B,
        reviews=[_review(commit_id=HEAD_A)],
        checks=[_check(head_sha=HEAD_B)],
        dismiss_stale_reviews=False,
    )

    verdict = _evaluate(snapshot)
    approvals = _approval_result(verdict)
    review_rows = cast(list[dict[str, object]], verdict["reviews"])

    assert verdict["state"] == "stale"
    assert approvals["github_requirement_satisfied"] is True
    assert approvals["retained_stale_count"] == 1
    assert review_rows[0]["binding_state"] == "stale"
    assert review_rows[0]["counts_toward_required_approvals"] is True
    assert (
        "approval_retained_by_supplied_rule_but_not_head_bound"
        in review_rows[0]["reasons"]
    )


def test_commented_review_never_counts_as_approval() -> None:
    verdict = _evaluate(_snapshot(reviews=[_review(state="COMMENTED")]))
    row = cast(list[dict[str, object]], verdict["reviews"])[0]

    assert verdict["state"] == "missing"
    assert row["decision_state"] == "commented"
    assert row["counts_toward_required_approvals"] is False
    assert "commented_is_not_approval" in row["reasons"]


def test_pending_review_accepts_githubs_absent_submitted_at() -> None:
    verdict = _evaluate(
        _snapshot(reviews=[_review(state="PENDING", submitted_at=None)])
    )
    row = cast(list[dict[str, object]], verdict["reviews"])[0]

    assert verdict["state"] == "pending"
    assert row["decision_state"] == "pending"
    assert row["submitted_at"] is None
    assert row["counts_toward_required_approvals"] is False


def test_dismissed_approval_preserves_dismissal_and_does_not_count() -> None:
    verdict = _evaluate(_snapshot(reviews=[_review(state="DISMISSED")]))
    row = cast(list[dict[str, object]], verdict["reviews"])[0]

    assert verdict["state"] == "missing"
    assert row["review_state"] == "DISMISSED"
    assert row["dismissed"] is True
    assert row["dismissed_prior_state"] == "APPROVED"
    assert row["counts_toward_required_approvals"] is False


def test_latest_push_approval_requires_other_actor_after_push() -> None:
    same_actor = _snapshot(
        reviews=[_review(actor="bob")],
        require_last_push_approval=True,
    )
    missing_verdict = _evaluate(same_actor)

    other_actor = copy.deepcopy(same_actor)
    cast(list[dict[str, object]], other_actor["reviews"]).append(
        _review(
            review_id=2,
            actor="carol",
            submitted_at="2026-07-28T10:07:00Z",
        )
    )
    current_verdict = _evaluate(other_actor)

    assert missing_verdict["state"] == "missing"
    assert "latest_push_approval_missing" in missing_verdict["reasons"]
    assert current_verdict["state"] == "current"
    assert _approval_result(current_verdict)["latest_push_approval_actor"] == "carol"


def test_latest_decisive_review_orders_timezone_offsets_by_instant() -> None:
    verdict = _evaluate(
        _snapshot(
            reviews=[
                _review(
                    review_id=1,
                    state="APPROVED",
                    submitted_at="2026-07-28T10:05:00Z",
                ),
                _review(
                    review_id=2,
                    state="CHANGES_REQUESTED",
                    submitted_at="2026-07-28T09:30:00-01:00",
                ),
            ]
        )
    )

    assert verdict["state"] == "blocked"
    assert "changes_requested" in verdict["reasons"]
    assert _approval_result(verdict)["counted_count"] == 0


def test_latest_push_approval_actor_orders_timezone_offsets_by_instant() -> None:
    verdict = _evaluate(
        _snapshot(
            reviews=[
                _review(
                    review_id=1,
                    actor="alice",
                    submitted_at="2026-07-28T10:05:00Z",
                ),
                _review(
                    review_id=2,
                    actor="carol",
                    submitted_at="2026-07-28T09:30:00-01:00",
                ),
            ],
            require_last_push_approval=True,
        )
    )

    assert verdict["state"] == "current"
    assert _approval_result(verdict)["latest_push_approval_actor"] == "carol"


def test_actor_logins_are_case_insensitive_for_counts_and_latest_push() -> None:
    duplicate_case = _snapshot(
        reviews=[
            _review(review_id=1, actor="Alice"),
            _review(review_id=2, actor="alice"),
        ],
        required_approvals=2,
    )
    duplicate_verdict = _evaluate(duplicate_case)

    assert duplicate_verdict["state"] == "missing"
    assert _approval_result(duplicate_verdict)["counted_count"] == 1

    same_pusher = _snapshot(
        reviews=[_review(actor="Alice")],
        require_last_push_approval=True,
    )
    cast(dict[str, object], same_pusher["latest_reviewable_push"])["actor"] = "alice"
    pusher_verdict = _evaluate(same_pusher)

    assert pusher_verdict["state"] == "missing"
    assert _approval_result(pusher_verdict)["latest_push_approval_actor"] is None


def test_pull_request_author_cannot_count_own_approval() -> None:
    snapshot = _snapshot(reviews=[_review(actor="Alice", can_count=True)])
    cast(dict[str, object], snapshot["pull_request"])["author"] = "alice"

    verdict = _evaluate(snapshot)
    row = cast(list[dict[str, object]], verdict["reviews"])[0]

    assert verdict["state"] == "missing"
    assert _approval_result(verdict)["counted_count"] == 0
    assert row["eligibility_state"] == "ineligible"
    assert row["counts_toward_required_approvals"] is False
    assert "pull_request_author_cannot_approve" in row["reasons"]


@pytest.mark.parametrize(
    ("status", "conclusion", "expected_state", "github_satisfied"),
    [
        ("completed", "neutral", "neutral", True),
        ("completed", "skipped", "skipped", True),
        ("completed", "cancelled", "blocked", False),
        ("completed", "failure", "blocked", False),
        ("queued", None, "pending", False),
    ],
)
def test_non_success_check_states_remain_distinct(
    status: str,
    conclusion: str | None,
    expected_state: str,
    github_satisfied: bool,
) -> None:
    verdict = _evaluate(
        _snapshot(checks=[_check(status=status, conclusion=conclusion)])
    )
    required = cast(
        list[dict[str, object]],
        _check_result(verdict)["required"],
    )[0]

    assert verdict["state"] == expected_state
    assert required["state"] in {
        "neutral",
        "skipped",
        "cancelled",
        "blocked",
        "pending",
    }
    assert required["github_requirement_satisfied"] is github_satisfied
    assert verdict["current"] is False


def test_missing_required_check_is_not_green() -> None:
    verdict = _evaluate(_snapshot(checks=[]))
    required = cast(
        list[dict[str, object]],
        _check_result(verdict)["required"],
    )[0]

    assert verdict["state"] == "missing"
    assert required["state"] == "missing"
    assert required["evidence_sha"] is None


def test_old_check_success_is_stale_not_current_success() -> None:
    verdict = _evaluate(
        _snapshot(
            head_sha=HEAD_B,
            reviews=[_review(commit_id=HEAD_B)],
            checks=[_check(head_sha=HEAD_A)],
        )
    )
    required = cast(
        list[dict[str, object]],
        _check_result(verdict)["required"],
    )[0]

    assert verdict["state"] == "stale"
    assert required["state"] == "stale"
    assert required["evidence_sha"] == HEAD_A


def test_check_suite_is_bound_to_head_but_does_not_masquerade_as_required_check() -> (
    None
):
    verdict = _evaluate(
        _snapshot(
            checks=[
                _check(
                    kind="check_suite",
                    name="ci/test",
                    head_sha=HEAD_A,
                )
            ]
        )
    )
    row = cast(list[dict[str, object]], verdict["checks"])[0]

    assert verdict["state"] == "missing"
    assert row["kind"] == "check_suite"
    assert row["binding_state"] == "current"
    assert row["required"] is False


@pytest.mark.parametrize(
    ("collection", "updates", "reason"),
    [
        (
            "reviews",
            {"complete": False, "truncated": True},
            "reviews_pagination_truncated",
        ),
        (
            "checks",
            {"permission": "inaccessible", "complete": False},
            "checks_permission_inaccessible",
        ),
        (
            "rules",
            {"permission": "missing", "complete": False},
            "rules_permission_missing",
        ),
    ],
)
def test_incomplete_or_inaccessible_coverage_is_unknown(
    collection: str,
    updates: dict[str, object],
    reason: str,
) -> None:
    snapshot = _snapshot()
    coverage = cast(dict[str, dict[str, object]], snapshot["coverage"])
    coverage[collection].update(updates)

    verdict = _evaluate(snapshot)

    assert verdict["state"] == "unknown"
    assert reason in verdict["reasons"]


def test_missing_protection_data_is_unknown_without_inventing_defaults() -> None:
    snapshot = _snapshot()
    rules = cast(dict[str, object], snapshot["rules"])
    rules["availability"] = "missing"
    rules["items"] = []
    coverage = cast(dict[str, dict[str, object]], snapshot["coverage"])
    coverage["rules"].update({"complete": False, "pages_fetched": 0})

    verdict = _evaluate(snapshot)

    assert verdict["state"] == "unknown"
    assert "rules_missing" in verdict["reasons"]
    assert _approval_result(verdict)["required_count"] == 0


def test_unknown_rule_type_forces_unknown_coverage() -> None:
    snapshot = _snapshot()
    cast(dict[str, object], snapshot["rules"])["items"] = [
        {"type": "required_magic_attestation"}
    ]

    verdict = _evaluate(snapshot)

    assert verdict["state"] == "unknown"
    assert "unknown_rule_type:required_magic_attestation" in verdict["reasons"]


def test_malformed_review_commit_id_is_rejected() -> None:
    snapshot = _snapshot()
    cast(list[dict[str, object]], snapshot["reviews"])[0].pop("commit_id")

    with pytest.raises(SnapshotValidationError) as exc:
        parse_snapshot(snapshot)

    assert any("reviews[0].commit_id" in error for error in exc.value.errors)


def test_unknown_input_field_is_rejected_instead_of_ignored() -> None:
    snapshot = _snapshot()
    cast(dict[str, object], snapshot["pull_request"])["headSHa"] = HEAD_A

    with pytest.raises(SnapshotValidationError) as exc:
        parse_snapshot(snapshot)

    assert "pull_request.headSHa: unknown field" in exc.value.errors


def test_repeat_run_json_is_byte_deterministic() -> None:
    snapshot = parse_snapshot(_snapshot())

    first = json.dumps(evaluate_snapshot(snapshot), indent=2, sort_keys=True) + "\n"
    second = json.dumps(evaluate_snapshot(snapshot), indent=2, sort_keys=True) + "\n"

    assert first == second


def _deep_merge(target: dict[str, object], patch: dict[str, object]) -> None:
    for key, value in patch.items():
        current = target.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            _deep_merge(
                cast(dict[str, object], current),
                cast(dict[str, object], value),
            )
        else:
            target[key] = copy.deepcopy(value)


def test_semantic_fixture_triplets_pin_expected_transitions() -> None:
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "pr_head_evidence"
        / "semantic_triplets.json"
    )
    fixture_set = json.loads(fixture_path.read_text(encoding="utf-8"))
    base = cast(dict[str, object], fixture_set["base_snapshot"])
    triplets = cast(list[dict[str, object]], fixture_set["triplets"])

    assert len(triplets) == 9
    for triplet in triplets:
        before = copy.deepcopy(base)
        after = copy.deepcopy(base)
        _deep_merge(
            before,
            cast(dict[str, object], triplet["before_patch"]),
        )
        _deep_merge(
            after,
            cast(dict[str, object], triplet["after_patch"]),
        )
        expected = cast(dict[str, object], triplet["expected"])
        before_verdict = _evaluate(before)
        after_verdict = _evaluate(after)
        assert before_verdict["state"] == expected["before_state"], triplet["name"]
        assert after_verdict["state"] == expected["after_state"], triplet["name"]
        for reason in cast(list[str], expected.get("after_reasons", [])):
            assert reason in after_verdict["reasons"], triplet["name"]
