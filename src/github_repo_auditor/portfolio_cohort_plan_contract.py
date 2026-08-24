"""Shared contract for `PortfolioCohortPlanV1`.

The plan is the collector's *intent* for one governed cohort transition. It is
deliberately small, carries no project data, and is **not** PortfolioTruth: it
never authorizes portfolio state, only the membership of one bounded security
collection.

This module holds only the schema, the digest rule, and the validator so that
both the planner (`portfolio_cohort_plan`) and the collector
(`github_security_coverage`) can depend on it without an import cycle.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

PORTFOLIO_COHORT_PLAN_SCHEMA_VERSION = "PortfolioCohortPlanV1"
COHORT_TRANSITION_PROTOCOL = "portfolio-default-attention-transition-v1"
COHORT_TRANSITION_KINDS = frozenset({"steady", "shrink", "expand", "swap"})

_COMMIT_RE_TEXT = "[0-9a-f]{40}"
_SHA256_RE_TEXT = "[0-9a-f]{64}"


class CohortPlanError(ValueError):
    """Raised when a cohort plan is malformed or internally inconsistent."""


@dataclass(frozen=True)
class CohortPlan:
    """A validated `PortfolioCohortPlanV1` payload."""

    plan_id: str
    generated_at: str
    producer_commit: str
    catalog_sha256: str
    workspace_root: str
    prior_truth_path: str
    prior_truth_sha256: str
    prior_truth_generated_at: str
    policy: str
    prospective_repositories: tuple[str, ...]
    prior_published_repositories: tuple[str, ...]
    required_repositories: tuple[str, ...]
    outgoing_repositories: tuple[str, ...]
    incoming_repositories: tuple[str, ...]
    collection_repositories: tuple[str, ...]
    transition_kind: str

    @property
    def delta_size(self) -> int:
        """Symmetric difference between prospective and prior published sets."""
        return len(
            set(self.prospective_repositories) ^ set(self.prior_published_repositories)
        )


def derive_transition_kind(incoming: tuple[str, ...], outgoing: tuple[str, ...]) -> str:
    """Return the transition class implied by the planned membership delta."""
    if incoming and outgoing:
        return "swap"
    if outgoing:
        return "shrink"
    if incoming:
        return "expand"
    return "steady"


def plan_id_for_payload(payload: dict[str, Any]) -> str:
    """Return the deterministic content identity of a plan body."""
    unsigned = {key: value for key, value in payload.items() if key != "plan_id"}
    canonical = json.dumps(
        unsigned,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def build_cohort_plan_payload(
    *,
    generated_at: datetime,
    producer_commit: str,
    producer_repository: str,
    catalog_sha256: str,
    workspace_root: str,
    prior_truth_path: str,
    prior_truth_sha256: str,
    prior_truth_generated_at: str,
    policy: str,
    prospective_repositories: tuple[str, ...],
    prior_published_repositories: tuple[str, ...],
) -> dict[str, Any]:
    """Assemble a signed `PortfolioCohortPlanV1` payload from derived sets.

    `required` is the prospective cohort. `collection` is the union that the
    collector must query so that both incoming coverage and departure evidence
    exist in a single receipt.
    """
    prospective = tuple(sorted(set(prospective_repositories), key=str.lower))
    prior_published = tuple(sorted(set(prior_published_repositories), key=str.lower))
    outgoing = tuple(sorted(set(prior_published) - set(prospective), key=str.lower))
    incoming = tuple(sorted(set(prospective) - set(prior_published), key=str.lower))
    collection = tuple(sorted(set(prospective) | set(prior_published), key=str.lower))
    payload = {
        "schema_version": PORTFOLIO_COHORT_PLAN_SCHEMA_VERSION,
        "generated_at": generated_at.isoformat(),
        "producer": {
            "repository": producer_repository,
            "commit": producer_commit,
        },
        "source": {
            "catalog_sha256": catalog_sha256,
            "workspace_root": workspace_root,
            "prior_truth_path": prior_truth_path,
            "prior_truth_sha256": prior_truth_sha256,
            "prior_truth_generated_at": prior_truth_generated_at,
        },
        "cohort": {
            "policy": policy,
            "prospective_repositories": list(prospective),
            "prior_published_repositories": list(prior_published),
            "required_repositories": list(prospective),
            "outgoing_repositories": list(outgoing),
            "incoming_repositories": list(incoming),
            "collection_repositories": list(collection),
            "transition_kind": derive_transition_kind(incoming, outgoing),
        },
    }
    payload["plan_id"] = plan_id_for_payload(payload)
    return payload


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _repository_tuple(value: Any, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise CohortPlanError(f"cohort plan {field} must be a list of repositories")
    repositories = tuple(item.strip() for item in value)
    if len({repo.lower() for repo in repositories}) != len(repositories):
        raise CohortPlanError(f"cohort plan {field} contains duplicate repositories")
    if repositories != tuple(sorted(repositories, key=str.lower)):
        raise CohortPlanError(f"cohort plan {field} must be canonically sorted")
    return repositories


def _require_digest(value: Any, *, field: str) -> str:
    text = _text(value)
    if not re.fullmatch(_SHA256_RE_TEXT, text):
        raise CohortPlanError(f"cohort plan {field} must be a lowercase sha256 digest")
    return text


def validate_cohort_plan(payload: Any) -> CohortPlan:
    """Validate a plan payload and return its normalized identity."""
    if not isinstance(payload, dict):
        raise CohortPlanError("cohort plan must be a JSON object")
    if payload.get("schema_version") != PORTFOLIO_COHORT_PLAN_SCHEMA_VERSION:
        raise CohortPlanError(
            f"unexpected cohort plan schema: {payload.get('schema_version')!r}"
        )
    plan_id = _text(payload.get("plan_id"))
    if not re.fullmatch(rf"sha256:{_SHA256_RE_TEXT}", plan_id):
        raise CohortPlanError("cohort plan plan_id must be a sha256 identity")
    if plan_id != plan_id_for_payload(payload):
        raise CohortPlanError("cohort plan plan_id does not match the plan payload")

    generated_at = _text(payload.get("generated_at"))
    try:
        parsed_generated_at = datetime.fromisoformat(
            generated_at.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise CohortPlanError("cohort plan generated_at is invalid") from exc
    if parsed_generated_at.tzinfo is None:
        raise CohortPlanError("cohort plan generated_at must include a timezone")

    producer = _mapping(payload.get("producer"))
    producer_commit = _text(producer.get("commit"))
    if not re.fullmatch(_COMMIT_RE_TEXT, producer_commit):
        raise CohortPlanError("cohort plan producer commit is invalid")

    source = _mapping(payload.get("source"))
    catalog_sha256 = _require_digest(
        source.get("catalog_sha256"), field="source.catalog_sha256"
    )
    prior_truth_sha256 = _require_digest(
        source.get("prior_truth_sha256"), field="source.prior_truth_sha256"
    )
    workspace_root = _text(source.get("workspace_root"))
    prior_truth_path = _text(source.get("prior_truth_path"))
    prior_truth_generated_at = _text(source.get("prior_truth_generated_at"))
    if not workspace_root or not prior_truth_path or not prior_truth_generated_at:
        raise CohortPlanError("cohort plan source provenance is incomplete")

    cohort = _mapping(payload.get("cohort"))
    policy = _text(cohort.get("policy"))
    if not policy:
        raise CohortPlanError("cohort plan policy is required")
    prospective = _repository_tuple(
        cohort.get("prospective_repositories"),
        field="cohort.prospective_repositories",
    )
    prior_published = _repository_tuple(
        cohort.get("prior_published_repositories"),
        field="cohort.prior_published_repositories",
    )
    required = _repository_tuple(
        cohort.get("required_repositories"), field="cohort.required_repositories"
    )
    outgoing = _repository_tuple(
        cohort.get("outgoing_repositories"), field="cohort.outgoing_repositories"
    )
    incoming = _repository_tuple(
        cohort.get("incoming_repositories"), field="cohort.incoming_repositories"
    )
    collection = _repository_tuple(
        cohort.get("collection_repositories"),
        field="cohort.collection_repositories",
    )

    if set(required) != set(prospective):
        raise CohortPlanError(
            "cohort plan required set must equal the prospective cohort"
        )
    if set(outgoing) != set(prior_published) - set(prospective):
        raise CohortPlanError(
            "cohort plan outgoing set must equal prior published minus prospective"
        )
    if set(incoming) != set(prospective) - set(prior_published):
        raise CohortPlanError(
            "cohort plan incoming set must equal prospective minus prior published"
        )
    if set(collection) != set(prospective) | set(prior_published):
        raise CohortPlanError(
            "cohort plan collection set must equal the prospective/prior union"
        )
    if set(required) & set(outgoing):
        raise CohortPlanError("cohort plan required and outgoing sets must be disjoint")

    transition_kind = _text(cohort.get("transition_kind"))
    if transition_kind not in COHORT_TRANSITION_KINDS:
        raise CohortPlanError(
            f"unexpected cohort plan transition kind: {transition_kind!r}"
        )
    if transition_kind != derive_transition_kind(incoming, outgoing):
        raise CohortPlanError(
            "cohort plan transition_kind does not match its incoming/outgoing sets"
        )

    return CohortPlan(
        plan_id=plan_id,
        generated_at=generated_at,
        producer_commit=producer_commit,
        catalog_sha256=catalog_sha256,
        workspace_root=workspace_root,
        prior_truth_path=prior_truth_path,
        prior_truth_sha256=prior_truth_sha256,
        prior_truth_generated_at=prior_truth_generated_at,
        policy=policy,
        prospective_repositories=prospective,
        prior_published_repositories=prior_published,
        required_repositories=required,
        outgoing_repositories=outgoing,
        incoming_repositories=incoming,
        collection_repositories=collection,
        transition_kind=transition_kind,
    )
