"""Bind supplied pull-request evidence to an explicit GitHub head SHA.

This module is deliberately pure and local. It evaluates a versioned JSON
snapshot without making GitHub requests or writing files. The result is not a
mergeability decision; it only reports whether the supplied review and check
evidence is current for the supplied pull-request head under the supplied
rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

SNAPSHOT_SCHEMA_VERSION = "PRHeadEvidenceV1"
VERDICT_SCHEMA_VERSION = "PRHeadEvidenceVerdictV1"

_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")
_REVIEW_STATES = {
    "APPROVED",
    "CHANGES_REQUESTED",
    "COMMENTED",
    "DISMISSED",
    "PENDING",
}
_PERMISSIONS = {"granted", "missing", "inaccessible", "unknown"}
_FRESHNESS_STATES = {"current", "stale", "unknown"}
_RULE_AVAILABILITY = {"available", "missing", "inaccessible"}
_RULE_SOURCES = {"branch_protection", "ruleset", "combined"}
_CHECK_KINDS = {"check_run", "check_suite"}
_PENDING_CHECK_STATUSES = {
    "queued",
    "in_progress",
    "requested",
    "waiting",
    "pending",
}
_SUCCESSFUL_GITHUB_CONCLUSIONS = {"success", "neutral", "skipped"}
_BLOCKING_CHECK_CONCLUSIONS = {
    "action_required",
    "failure",
    "startup_failure",
    "timed_out",
}


def _id_sort_key(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if value.isdigit() else (1, value)


def _actor_key(login: str) -> str:
    """Return the case-insensitive identity key GitHub uses for logins."""

    return login.casefold()


class SnapshotValidationError(ValueError):
    """Raised when a PRHeadEvidenceV1 snapshot is structurally malformed."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = tuple(sorted(set(errors)))
        super().__init__("; ".join(self.errors))


@dataclass(frozen=True)
class CoverageSlice:
    permission: str
    complete: bool
    truncated: bool
    pages_fetched: int


@dataclass(frozen=True)
class Actor:
    login: str
    can_count: bool | None


@dataclass(frozen=True)
class PullRequestIdentity:
    repository: str
    number: int
    author: str
    head_sha: str
    base_sha: str


@dataclass(frozen=True)
class LatestReviewablePush:
    pushed_at: datetime | None
    actor: str | None


@dataclass(frozen=True)
class Review:
    review_id: str
    actor: Actor
    state: str
    commit_id: str
    submitted_at: datetime | None
    dismissed: bool
    dismissed_at: datetime | None
    dismissed_prior_state: str | None


def _review_sort_key(review: Review) -> tuple[bool, datetime, tuple[int, int | str]]:
    submitted_at = review.submitted_at or datetime.min.replace(tzinfo=timezone.utc)
    return (
        review.submitted_at is None,
        submitted_at,
        _id_sort_key(review.review_id),
    )


@dataclass(frozen=True)
class Check:
    check_id: str
    kind: str
    name: str
    head_sha: str
    status: str
    conclusion: str | None
    integration_id: int | None


@dataclass(frozen=True)
class PullRequestRule:
    required_approving_review_count: int
    dismiss_stale_reviews: bool
    require_last_push_approval: bool
    require_code_owner_reviews: bool


@dataclass(frozen=True)
class RequiredCheck:
    context: str
    integration_id: int | None


@dataclass(frozen=True)
class RequiredStatusChecksRule:
    strict_required_status_checks_policy: bool
    checks: tuple[RequiredCheck, ...]


@dataclass(frozen=True)
class UnknownRule:
    rule_type: str


Rule = PullRequestRule | RequiredStatusChecksRule | UnknownRule


@dataclass(frozen=True)
class RulesSnapshot:
    source: str
    availability: str
    items: tuple[Rule, ...]


@dataclass(frozen=True)
class Provenance:
    source: str
    captured_at: datetime
    freshness: str


@dataclass(frozen=True)
class PRHeadEvidenceSnapshot:
    pull_request: PullRequestIdentity
    latest_reviewable_push: LatestReviewablePush
    reviews: tuple[Review, ...]
    checks: tuple[Check, ...]
    rules: RulesSnapshot
    coverage: Mapping[str, CoverageSlice]
    provenance: Provenance


def _mapping(value: object, path: str, errors: list[str]) -> Mapping[str, object]:
    if isinstance(value, dict):
        return value
    errors.append(f"{path}: expected object")
    return {}


def _reject_unknown_keys(
    payload: Mapping[str, object],
    allowed: set[str],
    path: str,
    errors: list[str],
) -> None:
    for key in sorted(set(payload) - allowed):
        errors.append(f"{path}.{key}: unknown field")


def _list(value: object, path: str, errors: list[str]) -> list[object]:
    if isinstance(value, list):
        return value
    errors.append(f"{path}: expected array")
    return []


def _text(value: object, path: str, errors: list[str]) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    errors.append(f"{path}: expected non-empty string")
    return ""


def _optional_text(value: object, path: str, errors: list[str]) -> str | None:
    if value is None:
        return None
    return _text(value, path, errors)


def _boolean(value: object, path: str, errors: list[str]) -> bool:
    if isinstance(value, bool):
        return value
    errors.append(f"{path}: expected boolean")
    return False


def _integer(value: object, path: str, errors: list[str]) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    errors.append(f"{path}: expected integer")
    return 0


def _optional_integer(value: object, path: str, errors: list[str]) -> int | None:
    if value is None:
        return None
    return _integer(value, path, errors)


def _timestamp(value: object, path: str, errors: list[str]) -> datetime:
    text = _text(value, path, errors)
    if not text:
        return datetime.min
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{path}: expected ISO-8601 timestamp")
        return datetime.min
    if parsed.tzinfo is None:
        errors.append(f"{path}: timestamp must include timezone")
    return parsed


def _optional_timestamp(
    value: object,
    path: str,
    errors: list[str],
) -> datetime | None:
    if value is None:
        return None
    return _timestamp(value, path, errors)


def _sha(value: object, path: str, errors: list[str]) -> str:
    text = _text(value, path, errors).lower()
    if text and not _SHA_RE.fullmatch(text):
        errors.append(f"{path}: expected full 40- or 64-character hexadecimal SHA")
    return text


def _choice(
    value: object,
    choices: set[str],
    path: str,
    errors: list[str],
    *,
    normalize_upper: bool = False,
) -> str:
    text = _text(value, path, errors)
    normalized = text.upper() if normalize_upper else text.lower()
    if normalized and normalized not in choices:
        errors.append(f"{path}: unsupported value {text!r}")
    return normalized


def _parse_coverage_slice(
    value: object,
    path: str,
    errors: list[str],
) -> CoverageSlice:
    payload = _mapping(value, path, errors)
    _reject_unknown_keys(
        payload,
        {"permission", "complete", "truncated", "pages_fetched"},
        path,
        errors,
    )
    permission = _choice(
        payload.get("permission"), _PERMISSIONS, f"{path}.permission", errors
    )
    complete = _boolean(payload.get("complete"), f"{path}.complete", errors)
    truncated = _boolean(payload.get("truncated"), f"{path}.truncated", errors)
    pages_fetched = _integer(
        payload.get("pages_fetched"), f"{path}.pages_fetched", errors
    )
    if pages_fetched < 0:
        errors.append(f"{path}.pages_fetched: must be non-negative")
    if truncated and complete:
        errors.append(f"{path}: truncated collection cannot be complete")
    if permission != "granted" and complete:
        errors.append(
            f"{path}: collection without granted permission cannot be complete"
        )
    return CoverageSlice(permission, complete, truncated, pages_fetched)


def _parse_actor(value: object, path: str, errors: list[str]) -> Actor:
    payload = _mapping(value, path, errors)
    _reject_unknown_keys(payload, {"login", "can_count"}, path, errors)
    login = _text(payload.get("login"), f"{path}.login", errors)
    can_count_value = payload.get("can_count")
    can_count: bool | None
    if can_count_value is None:
        can_count = None
    else:
        can_count = _boolean(can_count_value, f"{path}.can_count", errors)
    return Actor(login=login, can_count=can_count)


def _parse_review(value: object, index: int, errors: list[str]) -> Review:
    path = f"reviews[{index}]"
    payload = _mapping(value, path, errors)
    _reject_unknown_keys(
        payload,
        {"id", "actor", "state", "commit_id", "submitted_at", "dismissal"},
        path,
        errors,
    )
    review_id_value = payload.get("id")
    if isinstance(review_id_value, (str, int)) and not isinstance(
        review_id_value, bool
    ):
        review_id = str(review_id_value)
    else:
        errors.append(f"{path}.id: expected string or integer")
        review_id = ""
    actor = _parse_actor(payload.get("actor"), f"{path}.actor", errors)
    state = _choice(
        payload.get("state"),
        _REVIEW_STATES,
        f"{path}.state",
        errors,
        normalize_upper=True,
    )
    commit_id = _sha(payload.get("commit_id"), f"{path}.commit_id", errors)
    submitted_at = _optional_timestamp(
        payload.get("submitted_at"), f"{path}.submitted_at", errors
    )
    dismissal = _mapping(payload.get("dismissal"), f"{path}.dismissal", errors)
    _reject_unknown_keys(
        dismissal,
        {"dismissed", "dismissed_at", "prior_state"},
        f"{path}.dismissal",
        errors,
    )
    dismissed = _boolean(
        dismissal.get("dismissed"), f"{path}.dismissal.dismissed", errors
    )
    dismissed_at = _optional_timestamp(
        dismissal.get("dismissed_at"),
        f"{path}.dismissal.dismissed_at",
        errors,
    )
    dismissed_prior_state = _optional_text(
        dismissal.get("prior_state"),
        f"{path}.dismissal.prior_state",
        errors,
    )
    if dismissed_prior_state is not None:
        dismissed_prior_state = dismissed_prior_state.upper()
        if dismissed_prior_state not in {"APPROVED", "CHANGES_REQUESTED", "COMMENTED"}:
            errors.append(
                f"{path}.dismissal.prior_state: unsupported value {dismissed_prior_state!r}"
            )
    if state == "DISMISSED" and not dismissed:
        errors.append(f"{path}: DISMISSED state requires dismissal.dismissed=true")
    if state != "PENDING" and submitted_at is None:
        errors.append(f"{path}: submitted review requires submitted_at")
    if state != "DISMISSED" and dismissed:
        errors.append(f"{path}: dismissed review must use state DISMISSED")
    if dismissed and dismissed_at is None:
        errors.append(f"{path}: dismissed review requires dismissal.dismissed_at")
    if not dismissed and (
        dismissed_at is not None or dismissed_prior_state is not None
    ):
        errors.append(f"{path}: active review cannot include dismissal history")
    return Review(
        review_id=review_id,
        actor=actor,
        state=state,
        commit_id=commit_id,
        submitted_at=submitted_at,
        dismissed=dismissed,
        dismissed_at=dismissed_at,
        dismissed_prior_state=dismissed_prior_state,
    )


def _parse_check(value: object, index: int, errors: list[str]) -> Check:
    path = f"checks[{index}]"
    payload = _mapping(value, path, errors)
    _reject_unknown_keys(
        payload,
        {
            "id",
            "kind",
            "name",
            "head_sha",
            "status",
            "conclusion",
            "integration_id",
        },
        path,
        errors,
    )
    check_id_value = payload.get("id")
    if isinstance(check_id_value, (str, int)) and not isinstance(check_id_value, bool):
        check_id = str(check_id_value)
    else:
        errors.append(f"{path}.id: expected string or integer")
        check_id = ""
    kind = _choice(payload.get("kind"), _CHECK_KINDS, f"{path}.kind", errors)
    name = _text(payload.get("name"), f"{path}.name", errors)
    head_sha = _sha(payload.get("head_sha"), f"{path}.head_sha", errors)
    status = _text(payload.get("status"), f"{path}.status", errors).lower()
    conclusion_value = payload.get("conclusion")
    conclusion = (
        None
        if conclusion_value is None
        else _text(conclusion_value, f"{path}.conclusion", errors).lower()
    )
    integration_id = _optional_integer(
        payload.get("integration_id"),
        f"{path}.integration_id",
        errors,
    )
    if status == "completed" and conclusion is None:
        errors.append(f"{path}: completed check requires conclusion")
    if status != "completed" and conclusion is not None:
        errors.append(f"{path}: incomplete check must use conclusion=null")
    return Check(
        check_id=check_id,
        kind=kind,
        name=name,
        head_sha=head_sha,
        status=status,
        conclusion=conclusion,
        integration_id=integration_id,
    )


def _parse_rule(value: object, index: int, errors: list[str]) -> Rule:
    path = f"rules.items[{index}]"
    payload = _mapping(value, path, errors)
    rule_type = _text(payload.get("type"), f"{path}.type", errors)
    if rule_type == "pull_request":
        _reject_unknown_keys(
            payload,
            {
                "type",
                "required_approving_review_count",
                "dismiss_stale_reviews",
                "require_last_push_approval",
                "require_code_owner_reviews",
            },
            path,
            errors,
        )
        required_count = _integer(
            payload.get("required_approving_review_count"),
            f"{path}.required_approving_review_count",
            errors,
        )
        if required_count < 0 or required_count > 6:
            errors.append(
                f"{path}.required_approving_review_count: must be between 0 and 6"
            )
        return PullRequestRule(
            required_approving_review_count=required_count,
            dismiss_stale_reviews=_boolean(
                payload.get("dismiss_stale_reviews"),
                f"{path}.dismiss_stale_reviews",
                errors,
            ),
            require_last_push_approval=_boolean(
                payload.get("require_last_push_approval"),
                f"{path}.require_last_push_approval",
                errors,
            ),
            require_code_owner_reviews=_boolean(
                payload.get("require_code_owner_reviews"),
                f"{path}.require_code_owner_reviews",
                errors,
            ),
        )
    if rule_type == "required_status_checks":
        _reject_unknown_keys(
            payload,
            {
                "type",
                "strict_required_status_checks_policy",
                "checks",
            },
            path,
            errors,
        )
        checks_payload = _list(payload.get("checks"), f"{path}.checks", errors)
        required_checks: list[RequiredCheck] = []
        for check_index, check_value in enumerate(checks_payload):
            check_path = f"{path}.checks[{check_index}]"
            check_payload = _mapping(check_value, check_path, errors)
            _reject_unknown_keys(
                check_payload,
                {"context", "integration_id"},
                check_path,
                errors,
            )
            required_checks.append(
                RequiredCheck(
                    context=_text(
                        check_payload.get("context"),
                        f"{check_path}.context",
                        errors,
                    ),
                    integration_id=_optional_integer(
                        check_payload.get("integration_id"),
                        f"{check_path}.integration_id",
                        errors,
                    ),
                )
            )
        return RequiredStatusChecksRule(
            strict_required_status_checks_policy=_boolean(
                payload.get("strict_required_status_checks_policy"),
                f"{path}.strict_required_status_checks_policy",
                errors,
            ),
            checks=tuple(required_checks),
        )
    return UnknownRule(rule_type=rule_type or "<missing>")


def parse_snapshot(value: object) -> PRHeadEvidenceSnapshot:
    """Validate and parse a PRHeadEvidenceV1 JSON value."""

    errors: list[str] = []
    payload = _mapping(value, "$", errors)
    _reject_unknown_keys(
        payload,
        {
            "schema_version",
            "pull_request",
            "latest_reviewable_push",
            "reviews",
            "checks",
            "rules",
            "coverage",
            "provenance",
        },
        "$",
        errors,
    )
    schema_version = _text(payload.get("schema_version"), "schema_version", errors)
    if schema_version and schema_version != SNAPSHOT_SCHEMA_VERSION:
        errors.append(
            f"schema_version: expected {SNAPSHOT_SCHEMA_VERSION!r}, got {schema_version!r}"
        )

    pr_payload = _mapping(payload.get("pull_request"), "pull_request", errors)
    _reject_unknown_keys(
        pr_payload,
        {"repository", "number", "author", "head_sha", "base_sha"},
        "pull_request",
        errors,
    )
    pull_request = PullRequestIdentity(
        repository=_text(
            pr_payload.get("repository"), "pull_request.repository", errors
        ),
        number=_integer(pr_payload.get("number"), "pull_request.number", errors),
        author=_text(pr_payload.get("author"), "pull_request.author", errors),
        head_sha=_sha(pr_payload.get("head_sha"), "pull_request.head_sha", errors),
        base_sha=_sha(pr_payload.get("base_sha"), "pull_request.base_sha", errors),
    )
    if pull_request.number <= 0:
        errors.append("pull_request.number: must be positive")
    if pull_request.repository and "/" not in pull_request.repository:
        errors.append("pull_request.repository: expected owner/name")

    push_payload = _mapping(
        payload.get("latest_reviewable_push"),
        "latest_reviewable_push",
        errors,
    )
    _reject_unknown_keys(
        push_payload,
        {"pushed_at", "actor"},
        "latest_reviewable_push",
        errors,
    )
    latest_push = LatestReviewablePush(
        pushed_at=_optional_timestamp(
            push_payload.get("pushed_at"),
            "latest_reviewable_push.pushed_at",
            errors,
        ),
        actor=_optional_text(
            push_payload.get("actor"),
            "latest_reviewable_push.actor",
            errors,
        ),
    )

    reviews_payload = _list(payload.get("reviews"), "reviews", errors)
    reviews = tuple(
        _parse_review(review, index, errors)
        for index, review in enumerate(reviews_payload)
    )
    review_ids = [review.review_id for review in reviews]
    if len(set(review_ids)) != len(review_ids):
        errors.append("reviews: duplicate id")
    checks_payload = _list(payload.get("checks"), "checks", errors)
    checks = tuple(
        _parse_check(check, index, errors) for index, check in enumerate(checks_payload)
    )
    check_ids = [check.check_id for check in checks]
    if len(set(check_ids)) != len(check_ids):
        errors.append("checks: duplicate id")

    rules_payload = _mapping(payload.get("rules"), "rules", errors)
    _reject_unknown_keys(
        rules_payload,
        {"source", "availability", "items"},
        "rules",
        errors,
    )
    rule_items_payload = _list(rules_payload.get("items"), "rules.items", errors)
    rules = RulesSnapshot(
        source=_choice(
            rules_payload.get("source"),
            _RULE_SOURCES,
            "rules.source",
            errors,
        ),
        availability=_choice(
            rules_payload.get("availability"),
            _RULE_AVAILABILITY,
            "rules.availability",
            errors,
        ),
        items=tuple(
            _parse_rule(rule, index, errors)
            for index, rule in enumerate(rule_items_payload)
        ),
    )

    coverage_payload = _mapping(payload.get("coverage"), "coverage", errors)
    _reject_unknown_keys(
        coverage_payload,
        {"reviews", "checks", "rules"},
        "coverage",
        errors,
    )
    coverage: dict[str, CoverageSlice] = {}
    for collection in ("reviews", "checks", "rules"):
        coverage[collection] = _parse_coverage_slice(
            coverage_payload.get(collection),
            f"coverage.{collection}",
            errors,
        )

    provenance_payload = _mapping(payload.get("provenance"), "provenance", errors)
    _reject_unknown_keys(
        provenance_payload,
        {"source", "captured_at", "freshness"},
        "provenance",
        errors,
    )
    provenance = Provenance(
        source=_text(provenance_payload.get("source"), "provenance.source", errors),
        captured_at=_timestamp(
            provenance_payload.get("captured_at"),
            "provenance.captured_at",
            errors,
        ),
        freshness=_choice(
            provenance_payload.get("freshness"),
            _FRESHNESS_STATES,
            "provenance.freshness",
            errors,
        ),
    )

    if errors:
        raise SnapshotValidationError(errors)
    return PRHeadEvidenceSnapshot(
        pull_request=pull_request,
        latest_reviewable_push=latest_push,
        reviews=reviews,
        checks=checks,
        rules=rules,
        coverage=coverage,
        provenance=provenance,
    )


def _rule_requirements(
    snapshot: PRHeadEvidenceSnapshot,
) -> tuple[int, bool, bool, bool, tuple[RequiredCheck, ...], list[str]]:
    required_approvals = 0
    dismiss_stale_reviews = False
    require_last_push_approval = False
    pull_request_rule_present = False
    checks_by_key: dict[tuple[str, int | None], RequiredCheck] = {}
    reasons: list[str] = []
    for rule in snapshot.rules.items:
        if isinstance(rule, PullRequestRule):
            pull_request_rule_present = True
            required_approvals = max(
                required_approvals,
                rule.required_approving_review_count,
            )
            dismiss_stale_reviews = dismiss_stale_reviews or rule.dismiss_stale_reviews
            require_last_push_approval = (
                require_last_push_approval or rule.require_last_push_approval
            )
            if rule.require_code_owner_reviews:
                reasons.append("code_owner_review_requirement_not_evaluable")
        elif isinstance(rule, RequiredStatusChecksRule):
            for check in rule.checks:
                checks_by_key[(check.context, check.integration_id)] = check
        else:
            reasons.append(f"unknown_rule_type:{rule.rule_type}")
    required_checks = tuple(
        checks_by_key[key]
        for key in sorted(
            checks_by_key,
            key=lambda item: (item[0], -1 if item[1] is None else item[1]),
        )
    )
    return (
        required_approvals,
        pull_request_rule_present,
        dismiss_stale_reviews,
        require_last_push_approval,
        required_checks,
        reasons,
    )


def _review_payload(
    review: Review,
    snapshot: PRHeadEvidenceSnapshot,
) -> dict[str, object]:
    binding_state = (
        "current" if review.commit_id == snapshot.pull_request.head_sha else "stale"
    )
    if review.state == "DISMISSED":
        decision_state = "dismissed"
    else:
        decision_state = review.state.lower()
    is_pull_request_author = _actor_key(review.actor.login) == _actor_key(
        snapshot.pull_request.author
    )
    if is_pull_request_author:
        eligibility_state = "ineligible"
    elif review.actor.can_count is None:
        eligibility_state = "unknown"
    elif review.actor.can_count:
        eligibility_state = "eligible"
    else:
        eligibility_state = "ineligible"
    reasons: list[str] = []
    if binding_state == "stale":
        reasons.append("review_commit_does_not_match_head")
    if decision_state == "commented":
        reasons.append("commented_is_not_approval")
    if decision_state == "dismissed":
        reasons.append("review_dismissed")
    if eligibility_state == "unknown":
        reasons.append("reviewer_counting_eligibility_unknown")
    if eligibility_state == "ineligible":
        reasons.append("reviewer_does_not_count")
    if is_pull_request_author:
        reasons.append("pull_request_author_cannot_approve")
    return {
        "id": review.review_id,
        "actor": review.actor.login,
        "actor_can_count": review.actor.can_count,
        "review_state": review.state,
        "dismissed": review.dismissed,
        "dismissed_prior_state": review.dismissed_prior_state,
        "commit_id": review.commit_id,
        "submitted_at": (
            review.submitted_at.isoformat() if review.submitted_at is not None else None
        ),
        "binding_state": binding_state,
        "decision_state": decision_state,
        "eligibility_state": eligibility_state,
        "counts_toward_required_approvals": False,
        "satisfies_latest_push_approval": False,
        "reasons": reasons,
    }


def _latest_decisive_reviews(reviews: tuple[Review, ...]) -> dict[str, Review]:
    latest: dict[str, Review] = {}
    for review in sorted(reviews, key=_review_sort_key):
        if review.state in {"COMMENTED", "PENDING"}:
            continue
        latest[_actor_key(review.actor.login)] = review
    return latest


def _evaluate_reviews(
    snapshot: PRHeadEvidenceSnapshot,
    *,
    required_approvals: int,
    pull_request_rule_present: bool,
    dismiss_stale_reviews: bool,
    require_last_push_approval: bool,
) -> tuple[dict[str, object], list[dict[str, object]], list[str]]:
    review_rows = [
        _review_payload(review, snapshot)
        for review in sorted(snapshot.reviews, key=_review_sort_key)
    ]
    rows_by_id = {str(row["id"]): row for row in review_rows}
    latest = _latest_decisive_reviews(snapshot.reviews)
    counted: list[Review] = []
    current_count = 0
    retained_stale_count = 0
    unknown_eligibility = False
    blocking_change_requests: list[str] = []

    for review in latest.values():
        if _actor_key(review.actor.login) == _actor_key(snapshot.pull_request.author):
            continue
        if review.actor.can_count is None and review.state in {
            "APPROVED",
            "CHANGES_REQUESTED",
        }:
            unknown_eligibility = True
            continue
        if review.actor.can_count is not True:
            continue
        if review.state == "CHANGES_REQUESTED" and pull_request_rule_present:
            blocking_change_requests.append(review.actor.login)
            continue
        if review.state != "APPROVED" or review.dismissed:
            continue
        is_current = review.commit_id == snapshot.pull_request.head_sha
        if not is_current and dismiss_stale_reviews:
            continue
        counted.append(review)
        row = rows_by_id[review.review_id]
        row["counts_toward_required_approvals"] = True
        if is_current:
            current_count += 1
        else:
            retained_stale_count += 1
            existing_reasons = row["reasons"]
            normalized_reasons = (
                [str(reason) for reason in existing_reasons]
                if isinstance(existing_reasons, list)
                else []
            )
            row["reasons"] = [
                *normalized_reasons,
                "approval_retained_by_supplied_rule_but_not_head_bound",
            ]

    latest_push_satisfied = not require_last_push_approval
    latest_push_approval_actor: str | None = None
    latest_push_unknown = False
    if require_last_push_approval:
        push = snapshot.latest_reviewable_push
        if push.actor is None or push.pushed_at is None:
            latest_push_unknown = True
        else:
            candidates = [
                review
                for review in counted
                if review.commit_id == snapshot.pull_request.head_sha
                and review.submitted_at is not None
                and review.submitted_at >= push.pushed_at
                and _actor_key(review.actor.login) != _actor_key(push.actor)
            ]
            if candidates:
                selected = sorted(candidates, key=_review_sort_key)[-1]
                latest_push_satisfied = True
                latest_push_approval_actor = selected.actor.login
                rows_by_id[selected.review_id]["satisfies_latest_push_approval"] = True

    approval_count_satisfied = len(counted) >= required_approvals
    reasons: list[str] = []
    pending_review_count = sum(
        1 for review in snapshot.reviews if review.state == "PENDING"
    )
    stale_approval_count = sum(
        1
        for review in snapshot.reviews
        if review.state == "APPROVED"
        and not review.dismissed
        and review.commit_id != snapshot.pull_request.head_sha
    )

    if blocking_change_requests:
        state = "blocked"
        reasons.append("changes_requested")
    elif unknown_eligibility or latest_push_unknown:
        state = "unknown"
        if unknown_eligibility:
            reasons.append("reviewer_counting_eligibility_unknown")
        if latest_push_unknown:
            reasons.append("latest_push_metadata_missing")
    elif not approval_count_satisfied:
        if pending_review_count:
            state = "pending"
            reasons.append("required_approval_pending")
        elif stale_approval_count:
            state = "stale"
            reasons.append("required_approval_only_on_older_sha")
        else:
            state = "missing"
            reasons.append("required_approval_missing")
    elif not latest_push_satisfied:
        if stale_approval_count or retained_stale_count:
            state = "stale"
            reasons.append("latest_push_approval_not_current")
        else:
            state = "missing"
            reasons.append("latest_push_approval_missing")
    elif required_approvals > current_count:
        state = "stale"
        reasons.append("approval_requirement_uses_retained_stale_review")
    else:
        state = "current"

    return (
        {
            "state": state,
            "required_count": required_approvals,
            "counted_actors": sorted(
                (review.actor.login for review in counted),
                key=_actor_key,
            ),
            "counted_count": len(counted),
            "head_bound_count": current_count,
            "retained_stale_count": retained_stale_count,
            "dismiss_stale_reviews": dismiss_stale_reviews,
            "require_last_push_approval": require_last_push_approval,
            "latest_push_approval_actor": latest_push_approval_actor,
            "github_requirement_satisfied": (
                approval_count_satisfied
                and latest_push_satisfied
                and not blocking_change_requests
            ),
            "reasons": reasons,
        },
        review_rows,
        reasons,
    )


def _check_result_state(check: Check) -> str:
    if check.status in _PENDING_CHECK_STATUSES:
        return "pending"
    if check.status != "completed":
        return "unknown"
    if check.conclusion == "success":
        return "success"
    if check.conclusion == "neutral":
        return "neutral"
    if check.conclusion == "skipped":
        return "skipped"
    if check.conclusion == "cancelled":
        return "cancelled"
    if check.conclusion == "stale":
        return "stale"
    if check.conclusion in _BLOCKING_CHECK_CONCLUSIONS:
        return "blocked"
    return "unknown"


def _check_payload(
    check: Check,
    snapshot: PRHeadEvidenceSnapshot,
) -> dict[str, object]:
    binding_state = (
        "current" if check.head_sha == snapshot.pull_request.head_sha else "stale"
    )
    result_state = _check_result_state(check)
    reasons: list[str] = []
    if binding_state == "stale":
        reasons.append("check_head_does_not_match_pr_head")
    if result_state != "success":
        reasons.append(f"check_result_{result_state}")
    return {
        "id": check.check_id,
        "kind": check.kind,
        "name": check.name,
        "head_sha": check.head_sha,
        "status": check.status,
        "conclusion": check.conclusion,
        "integration_id": check.integration_id,
        "binding_state": binding_state,
        "result_state": result_state,
        "required": False,
        "github_requirement_satisfied": (
            binding_state == "current"
            and result_state in _SUCCESSFUL_GITHUB_CONCLUSIONS
        ),
        "reasons": reasons,
    }


def _required_check_matches(required: RequiredCheck, check: Check) -> bool:
    if check.kind != "check_run" or check.name != required.context:
        return False
    return (
        required.integration_id is None
        or check.integration_id == required.integration_id
    )


def _evaluate_checks(
    snapshot: PRHeadEvidenceSnapshot,
    required_checks: tuple[RequiredCheck, ...],
) -> tuple[dict[str, object], list[dict[str, object]], list[str]]:
    check_rows = [
        _check_payload(check, snapshot)
        for check in sorted(
            snapshot.checks,
            key=lambda item: (
                item.kind,
                item.name,
                -1 if item.integration_id is None else item.integration_id,
                _id_sort_key(item.check_id),
            ),
        )
    ]
    rows_by_id = {str(row["id"]): row for row in check_rows}
    requirement_rows: list[dict[str, object]] = []

    for required in required_checks:
        matches = [
            check
            for check in snapshot.checks
            if _required_check_matches(required, check)
        ]
        current_matches = [
            check
            for check in matches
            if check.head_sha == snapshot.pull_request.head_sha
        ]
        for check in matches:
            rows_by_id[check.check_id]["required"] = True

        reasons: list[str] = []
        selected_sha: str | None = None
        conclusion: str | None = None
        github_satisfied = False
        if len(current_matches) > 1:
            state = "unknown"
            reasons.append("duplicate_current_required_check_evidence")
        elif len(current_matches) == 1:
            selected = current_matches[0]
            selected_sha = selected.head_sha
            conclusion = selected.conclusion
            state = _check_result_state(selected)
            github_satisfied = state in _SUCCESSFUL_GITHUB_CONCLUSIONS
            if state != "success":
                reasons.append(f"required_check_{state}")
        else:
            stale_matches = [
                check
                for check in matches
                if _check_result_state(check) in _SUCCESSFUL_GITHUB_CONCLUSIONS
            ]
            if stale_matches:
                state = "stale"
                selected_sha = sorted(
                    stale_matches,
                    key=lambda item: (
                        item.head_sha,
                        _id_sort_key(item.check_id),
                    ),
                )[-1].head_sha
                reasons.append("required_check_only_on_older_sha")
            else:
                state = "missing"
                reasons.append("required_check_missing")

        requirement_rows.append(
            {
                "context": required.context,
                "integration_id": required.integration_id,
                "state": state,
                "evidence_sha": selected_sha,
                "conclusion": conclusion,
                "github_requirement_satisfied": github_satisfied,
                "reasons": reasons,
            }
        )

    states = {str(row["state"]) for row in requirement_rows}
    if "unknown" in states:
        overall_state = "unknown"
    elif states & {"blocked", "cancelled"}:
        overall_state = "blocked"
    elif "pending" in states:
        overall_state = "pending"
    elif "missing" in states:
        overall_state = "missing"
    elif "stale" in states:
        overall_state = "stale"
    elif "neutral" in states:
        overall_state = "neutral"
    elif "skipped" in states:
        overall_state = "skipped"
    else:
        overall_state = "current"
    reason_set: set[str] = set()
    for row in requirement_rows:
        row_reasons = row["reasons"]
        if isinstance(row_reasons, list):
            reason_set.update(str(reason) for reason in row_reasons)
    reasons = sorted(reason_set)
    return (
        {
            "state": overall_state,
            "required": requirement_rows,
            "github_requirement_satisfied": all(
                bool(row["github_requirement_satisfied"]) for row in requirement_rows
            ),
            "all_required_checks_successful": all(
                row["state"] == "success" for row in requirement_rows
            ),
            "reasons": reasons,
        },
        check_rows,
        reasons,
    )


def _coverage_reasons(snapshot: PRHeadEvidenceSnapshot) -> list[str]:
    reasons: list[str] = []
    for name in ("reviews", "checks", "rules"):
        coverage = snapshot.coverage[name]
        if coverage.permission != "granted":
            reasons.append(f"{name}_permission_{coverage.permission}")
        if not coverage.complete:
            reasons.append(f"{name}_pagination_incomplete")
        if coverage.truncated:
            reasons.append(f"{name}_pagination_truncated")
    if snapshot.rules.availability != "available":
        reasons.append(f"rules_{snapshot.rules.availability}")
    return sorted(set(reasons))


def _overall_state(
    *,
    freshness: str,
    coverage_reasons: list[str],
    rule_reasons: list[str],
    approval_state: str,
    check_state: str,
) -> str:
    if freshness == "unknown":
        return "unknown"
    if freshness == "stale":
        return "stale"
    if coverage_reasons or rule_reasons:
        return "unknown"
    states = {approval_state, check_state}
    if "unknown" in states:
        return "unknown"
    if "blocked" in states:
        return "blocked"
    if "pending" in states:
        return "pending"
    if "missing" in states:
        return "missing"
    if "stale" in states:
        return "stale"
    if "neutral" in states:
        return "neutral"
    if "skipped" in states:
        return "skipped"
    return "current"


def evaluate_snapshot(snapshot: PRHeadEvidenceSnapshot) -> dict[str, object]:
    """Return a deterministic PRHeadEvidenceVerdictV1 dictionary."""

    coverage_reasons = _coverage_reasons(snapshot)
    (
        required_approvals,
        pull_request_rule_present,
        dismiss_stale_reviews,
        require_last_push_approval,
        required_checks,
        rule_reasons,
    ) = _rule_requirements(snapshot)
    approvals, reviews, approval_reasons = _evaluate_reviews(
        snapshot,
        required_approvals=required_approvals,
        pull_request_rule_present=pull_request_rule_present,
        dismiss_stale_reviews=dismiss_stale_reviews,
        require_last_push_approval=require_last_push_approval,
    )
    checks, check_rows, check_reasons = _evaluate_checks(snapshot, required_checks)
    state = _overall_state(
        freshness=snapshot.provenance.freshness,
        coverage_reasons=coverage_reasons,
        rule_reasons=rule_reasons,
        approval_state=str(approvals["state"]),
        check_state=str(checks["state"]),
    )
    reasons = sorted(
        set(
            coverage_reasons
            + rule_reasons
            + approval_reasons
            + check_reasons
            + (
                [f"snapshot_freshness_{snapshot.provenance.freshness}"]
                if snapshot.provenance.freshness != "current"
                else []
            )
        )
    )
    if state == "current":
        claim = "supplied_required_evidence_is_current_for_supplied_head"
    else:
        claim = (
            "supplied_required_evidence_is_not_all_current_success_for_supplied_head"
        )
    return {
        "schema_version": VERDICT_SCHEMA_VERSION,
        "state": state,
        "current": state == "current",
        "claim": claim,
        "claim_ceiling": (
            "Evaluates only required evidence under the supplied rules, while classifying "
            "all supplied evidence against the supplied head; does not determine GitHub "
            "mergeability, code quality, reviewer effectiveness, CI correctness, or "
            "branch safety."
        ),
        "repository": snapshot.pull_request.repository,
        "pull_request_number": snapshot.pull_request.number,
        "head_sha": snapshot.pull_request.head_sha,
        "base_sha": snapshot.pull_request.base_sha,
        "coverage": {
            "state": "complete"
            if not coverage_reasons and not rule_reasons
            else "unknown",
            "reasons": sorted(set(coverage_reasons + rule_reasons)),
        },
        "requirements": {
            "approvals": approvals,
            "checks": checks,
        },
        "reviews": reviews,
        "checks": check_rows,
        "reasons": reasons,
    }


def invalid_snapshot_verdict(
    reason: str,
    errors: tuple[str, ...] | list[str],
) -> dict[str, object]:
    """Build deterministic machine-readable output for invalid input."""

    return {
        "schema_version": VERDICT_SCHEMA_VERSION,
        "state": "unknown",
        "current": False,
        "claim": "snapshot_not_evaluable",
        "claim_ceiling": (
            "No evidence-to-head claim can be made because the supplied snapshot "
            "was not a valid PRHeadEvidenceV1 document."
        ),
        "repository": None,
        "pull_request_number": None,
        "head_sha": None,
        "base_sha": None,
        "coverage": {
            "state": "unknown",
            "reasons": [reason],
        },
        "requirements": {
            "approvals": None,
            "checks": None,
        },
        "reviews": [],
        "checks": [],
        "reasons": [reason],
        "validation_errors": sorted(set(errors)),
    }
