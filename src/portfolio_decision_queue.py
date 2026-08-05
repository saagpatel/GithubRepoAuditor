"""Canonical portfolio-decision admission and closure contract.

The decision queue is narrower than the default-attention watch set.  Version 2
makes that boundary machine-checkable: an item is actionable only when the
producer can provide a complete operator decision, immutable evidence identity,
an expiry derived from the evidence clock, and an authoritative readback rule.
Incomplete candidates are retained as explicitly withheld evidence instead of
being silently promoted or dropped.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.security_admission import derive_security_admission

CONTRACT_VERSION = "decision_queue_v2"
DIGEST_CONTRACT_VERSION = "portfolio_decision_digest_v2"
ITEM_SCHEMA_VERSION = "portfolio_decision_item_v2"
WITHHELD_SCHEMA_VERSION = "portfolio_decision_withheld_v2"
KEY_SCHEMA_VERSION = "portfolio_decision_key_v1"
FINGERPRINT_SCHEMA_VERSION = "portfolio_decision_fingerprint_v1"
READBACK_CONTRACT_VERSION = "portfolio_decision_readback_v1"
MAX_DECISION_QUEUE_ITEMS = 5

# The security receipt is produced daily before the 02:00 portfolio job.  A
# 36-hour window admits one missed daily projection without pretending that a
# newly generated projection refreshed the underlying GitHub observation.
SECURITY_DECISION_VALIDITY_HOURS = 36

NON_DEFAULT_STATES = frozenset(
    {"parked", "archived", "experiment", "evidence-history", "manual-only"}
)
SHA256_ID_PREFIX = "sha256:"


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_identity(value: Any) -> str:
    return SHA256_ID_PREFIX + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _parse_datetime(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _canonical_project_identity(project: dict[str, Any]) -> str:
    identity = _mapping(project.get("identity"))
    repo_full_name = _text(identity.get("repo_full_name"))
    if repo_full_name:
        return f"repo:{repo_full_name.casefold()}"
    project_key = _text(identity.get("project_key"))
    if project_key:
        return f"supp:{project_key.casefold()}"
    path = _text(identity.get("path"))
    if path:
        return f"path:{path.casefold()}"
    display_name = _text(identity.get("display_name")) or "unknown"
    return f"unknown:{display_name.casefold()}"


def _decision_key(project: dict[str, Any], decision_type: str) -> str:
    return _sha256_identity(
        {
            "schema_version": KEY_SCHEMA_VERSION,
            "project_identity": _canonical_project_identity(project),
            "decision_type": decision_type,
        }
    )


def _portfolio_truth_sha256(portfolio_truth: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(portfolio_truth)).hexdigest()


def _source_generation(portfolio_truth: dict[str, Any]) -> dict[str, Any]:
    producer = _mapping(portfolio_truth.get("producer"))
    github_security = _mapping(
        _mapping(portfolio_truth.get("inputs")).get("github_security")
    )
    return {
        "portfolio_truth": {
            "generated_at": _text(portfolio_truth.get("generated_at")) or "unknown",
            "receipt_id": _text(producer.get("receipt_id")) or None,
            "producer_commit": _text(producer.get("commit")) or None,
            "content_sha256": _portfolio_truth_sha256(portfolio_truth),
        },
        "github_security": {
            "produced_at": _text(github_security.get("produced_at")) or None,
            "receipt_id": _text(github_security.get("receipt_id")) or None,
            "content_sha256": _text(github_security.get("content_sha256")) or None,
            "state": _text(github_security.get("state")) or "unknown",
        },
    }


def _project_basics(project: dict[str, Any]) -> dict[str, str]:
    identity = _mapping(project.get("identity"))
    derived = _mapping(project.get("derived"))
    project_name = _text(identity.get("display_name")) or "Repo"
    return {
        "project": project_name,
        "path": _text(identity.get("path")) or project_name,
        "project_identity": _canonical_project_identity(project),
        "attention_state": _text(derived.get("attention_state")) or "manual-only",
    }


def _allowed_security_outcomes(
    project_name: str, valid_until: str
) -> list[dict[str, str]]:
    return [
        {
            "id": "accept",
            "label": "Accept",
            "effect": (
                f"Approve one repository-scoped security follow-up for {project_name}; "
                "execution remains a separate operator-gated action."
            ),
        },
        {
            "id": "defer",
            "label": "Defer",
            "effect": f"Defer this exact evidence fingerprint until {valid_until}.",
        },
        {
            "id": "reject",
            "label": "Reject",
            "effect": (
                "Reject this exact evidence fingerprint; a newer authoritative "
                "fingerprint reopens review."
            ),
        },
    ]


def _approval_boundary() -> dict[str, Any]:
    return {
        "kind": "operator",
        "required": True,
        "execution_is_separate": True,
        "scope": "one repository-scoped security follow-up",
        "forbidden_without_accept": [
            "repository mutation",
            "dependency update",
            "pull request publication",
        ],
    }


def _readback_contract(project_identity: str) -> dict[str, Any]:
    return {
        "contract_version": READBACK_CONTRACT_VERSION,
        "authoritative_source": "github-security-coverage-receipt",
        "project_identity": project_identity,
        "requires_newer_receipt": True,
        "success_condition": {
            "dependabot_critical": 0,
            "dependabot_high": 0,
            "code_scanning_critical": 0,
            "code_scanning_high": 0,
            "secret_scanning_open": 0,
        },
        "preserve_if": "matching newer receipt still reports open high or critical alerts",
        "reopen_if": "a newer receipt yields a different nonzero decision fingerprint",
        "supporting_evidence_only": ["bridge-shipped"],
        "failure_reason_codes": [
            "READBACK_MISSING",
            "READBACK_SOURCE_NOT_NEWER",
            "READBACK_SOURCE_MISMATCH",
            "READBACK_STILL_OPEN",
        ],
    }


def _withheld(
    project: dict[str, Any],
    *,
    decision_type: str,
    reason_code: str,
    why_now: str,
    source_generation: dict[str, Any],
) -> dict[str, Any]:
    basics = _project_basics(project)
    decision_key = _decision_key(project, decision_type)
    fingerprint = _sha256_identity(
        {
            "schema_version": FINGERPRINT_SCHEMA_VERSION,
            "decision_key": decision_key,
            "reason_code": reason_code,
            "source_generation": source_generation,
        }
    )
    return {
        "schema_version": WITHHELD_SCHEMA_VERSION,
        **basics,
        "decision_type": decision_type,
        "decision_key": decision_key,
        "decision_fingerprint": fingerprint,
        "actionability": "withheld",
        "withheld_reason_code": reason_code,
        "why_now": why_now,
        "evaluated_at": source_generation["portfolio_truth"]["generated_at"],
        "source_generation": source_generation,
    }


def _security_decision(
    project: dict[str, Any],
    *,
    portfolio_truth: dict[str, Any],
    source_generation: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    basics = _project_basics(project)
    declared = _mapping(project.get("declared"))
    security = _mapping(project.get("security"))
    admission = derive_security_admission(security)
    github_source = _mapping(
        _mapping(portfolio_truth.get("inputs")).get("github_security")
    )
    decision_type = "security follow-up"
    decision_key = _decision_key(project, decision_type)

    def refuse(code: str, detail: str) -> tuple[None, dict[str, Any]]:
        return None, _withheld(
            project,
            decision_type=decision_type,
            reason_code=code,
            why_now=detail,
            source_generation=source_generation,
        )

    owner = _text(declared.get("owner"))
    if not owner:
        return refuse(
            "DECISION_OWNER_MISSING", "The declared accountable owner is missing."
        )
    if basics["project_identity"].startswith("unknown:"):
        return refuse(
            "DECISION_IDENTITY_MISSING",
            "No canonical repository or supplementary project identity is available.",
        )
    required_source_fields = (
        "schema_version",
        "produced_at",
        "receipt_id",
        "content_sha256",
        "path",
        "producer_commit",
    )
    if any(not _text(github_source.get(field)) for field in required_source_fields):
        return refuse(
            "SECURITY_SOURCE_IDENTITY_INCOMPLETE",
            "The GitHub security receipt identity or reference is incomplete.",
        )
    if _text(github_source.get("state")) != "fresh":
        return refuse(
            "SECURITY_SOURCE_NOT_FRESH",
            "The GitHub security receipt is not marked fresh.",
        )
    producer_commit = _text(_mapping(portfolio_truth.get("producer")).get("commit"))
    if producer_commit and producer_commit != _text(
        github_source.get("producer_commit")
    ):
        return refuse(
            "SECURITY_SOURCE_PRODUCER_MISMATCH",
            "PortfolioTruth and the GitHub security receipt name different producer commits.",
        )
    if _text(security.get("source_produced_at")) != _text(
        github_source.get("produced_at")
    ):
        return refuse(
            "SECURITY_SOURCE_MISMATCH",
            "The project security envelope does not match the admitted receipt generation.",
        )
    if not admission.evidence_complete:
        reason_code = next(
            (
                code
                for code in admission.reason_codes
                if code
                not in {
                    "SECURITY_ADMISSION_FINDINGS",
                    "SECURITY_ADMISSION_UNKNOWN",
                }
            ),
            "SECURITY_ADMISSION_UNKNOWN",
        )
        return refuse(
            reason_code,
            "Canonical security admission failed closed: "
            + ", ".join(admission.reason_codes),
        )

    evaluated = _parse_datetime(portfolio_truth.get("generated_at"))
    evidence_observed = _parse_datetime(admission.evidence_observed_at)
    receipt_produced = _parse_datetime(github_source.get("produced_at"))
    if not evaluated:
        return refuse(
            "PROJECTION_CLOCK_MISSING",
            "PortfolioTruth generated_at is missing or invalid.",
        )
    if not evidence_observed:
        return refuse(
            "EVIDENCE_CLOCK_MISSING",
            "Canonical security admission observed_at is missing or invalid.",
        )
    if not receipt_produced:
        return refuse(
            "RECEIPT_CLOCK_MISSING",
            "The GitHub security receipt produced_at is missing or invalid.",
        )
    if evidence_observed > receipt_produced or receipt_produced > evaluated:
        return refuse(
            "SECURITY_CLOCK_CONFLICT",
            "Evidence, receipt, and projection clocks are not monotonic.",
        )
    valid_until_dt = evidence_observed + timedelta(
        hours=SECURITY_DECISION_VALIDITY_HOURS
    )
    if evaluated > valid_until_dt:
        return refuse(
            "SECURITY_EVIDENCE_EXPIRED",
            "The oldest admitted security observation expired; projection regeneration cannot rejuvenate it.",
        )

    critical = admission.total_open_critical
    high = admission.total_open_high
    secrets = admission.total_open_secrets
    if critical + high + secrets <= 0:
        return refuse(
            "SECURITY_RISK_COUNT_MISMATCH",
            "Security risk is set without an admitted blocking GitHub security finding.",
        )

    valid_until = _iso(valid_until_dt)
    evidence_observed_at = _iso(evidence_observed)
    evaluated_at = _iso(evaluated)
    allowed_outcomes = _allowed_security_outcomes(basics["project"], valid_until)
    approval_boundary = _approval_boundary()
    readback_contract = _readback_contract(basics["project_identity"])
    question = (
        f"Should {owner} approve one repository-scoped security follow-up for "
        f"{basics['project']} against {critical} critical and {high} high "
        f"alerts plus {secrets} open secret-scanning findings before {valid_until}?"
    )
    evidence_reference = {
        "source_id": _text(github_source.get("source_id")),
        "schema_version": _text(github_source.get("schema_version")),
        "receipt_id": _text(github_source.get("receipt_id")),
        "content_sha256": _text(github_source.get("content_sha256")),
        "path": _text(github_source.get("path")),
        "project_identity": basics["project_identity"],
        "security_admission_schema": admission.schema_version,
        "security_admission_status": admission.status,
        "provider": "github_security_combined",
        "provider_observed_at": evidence_observed_at,
        "provider_observed_at_by_name": admission.provider_observed_at,
        "dependabot_critical": admission.dependabot_critical,
        "dependabot_high": admission.dependabot_high,
        "code_scanning_critical": admission.code_scanning_critical,
        "code_scanning_high": admission.code_scanning_high,
        "secret_scanning_open": admission.secret_scanning_open,
    }
    fingerprint_payload = {
        "schema_version": FINGERPRINT_SCHEMA_VERSION,
        "decision_key": decision_key,
        "decision_question": question,
        "owner": owner,
        "allowed_outcomes": allowed_outcomes,
        "approval_boundary": approval_boundary,
        "evidence_reference": evidence_reference,
        "valid_until": valid_until,
        "readback_contract": readback_contract,
    }
    decision_fingerprint = _sha256_identity(fingerprint_payload)
    item = {
        "schema_version": ITEM_SCHEMA_VERSION,
        **basics,
        "decision_type": decision_type,
        "decision_key": decision_key,
        "decision_fingerprint": decision_fingerprint,
        "actionability": "actionable",
        "withheld_reason_code": None,
        "decision_question": question,
        "owner": owner,
        "allowed_outcomes": allowed_outcomes,
        "approval_boundary": approval_boundary,
        "why_now": "Current authoritative GitHub security evidence reports admitted blocking findings.",
        "evidence": [
            "security_risk=true; "
            f"critical={critical}, high={high}, open_secrets={secrets}; "
            f"admission={admission.schema_version}"
        ],
        "authoritative_source": "github-security-coverage-receipt",
        "evidence_reference": evidence_reference,
        "evaluated_at": evaluated_at,
        "evidence_observed_at": evidence_observed_at,
        "valid_until": valid_until,
        "source_generation": source_generation,
        "supersedes": None,
        "readback_contract": readback_contract,
        "source_freshness": evaluated_at,
        "recommended_action": (
            "Record accept, defer, or reject in the existing Personal Ops outcome log. "
            "After accept, execute the repository-owned security lane separately and wait "
            "for a newer authoritative security receipt."
        ),
        "do_not_refresh_docs_unless": (
            "Do not refresh context, roadmap, handoff, AGENTS, or docs unless "
            "that work directly resolves this decision."
        ),
    }
    return item, None


def _build_candidates(
    portfolio_truth: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    projects = portfolio_truth.get("projects") or []
    source_generation = _source_generation(portfolio_truth)
    actionable: list[dict[str, Any]] = []
    withheld: list[dict[str, Any]] = []
    for project in projects:
        if not isinstance(project, dict):
            continue
        basics = _project_basics(project)
        if basics["attention_state"] in {"archived", "evidence-history"}:
            continue
        risk = _mapping(project.get("risk"))
        admission = derive_security_admission(project.get("security"))
        if bool(risk.get("security_risk")) or admission.has_findings:
            item, refused = _security_decision(
                project,
                portfolio_truth=portfolio_truth,
                source_generation=source_generation,
            )
            if item is not None:
                actionable.append(item)
            if refused is not None:
                withheld.append(refused)
            continue
        if basics["attention_state"] in NON_DEFAULT_STATES:
            continue
        if basics["attention_state"] == "decision-needed":
            withheld.append(
                _withheld(
                    project,
                    decision_type="owner or human decision",
                    reason_code="OWNER_DECISION_SPEC_INCOMPLETE",
                    why_now=(
                        "PortfolioTruth marks this project decision-needed, but the "
                        "authoritative source does not provide an exact question, options, "
                        "approval boundary, or readback contract."
                    ),
                    source_generation=source_generation,
                )
            )

    actionable.sort(
        key=lambda item: (item["decision_type"], item["project"].casefold())
    )
    withheld.sort(key=lambda item: (item["decision_type"], item["project"].casefold()))
    return actionable, withheld


def build_decision_queue(portfolio_truth: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only complete actionable decisions, capped for operator attention."""
    actionable, _ = _build_candidates(portfolio_truth)
    return actionable[:MAX_DECISION_QUEUE_ITEMS]


def build_withheld_decisions(portfolio_truth: dict[str, Any]) -> list[dict[str, Any]]:
    """Return incomplete decision candidates with deterministic refusal codes."""
    _, withheld = _build_candidates(portfolio_truth)
    return withheld


def summarize_decision_queue(
    items: list[dict[str, Any]],
    *,
    withheld: list[dict[str, Any]] | None = None,
    canonical_count: int | None = None,
) -> dict[str, Any]:
    type_counts: dict[str, int] = {}
    for item in items:
        decision_type = _text(item.get("decision_type")) or "unknown"
        type_counts[decision_type] = type_counts.get(decision_type, 0) + 1
    withheld_items = withheld or []
    withheld_counts: dict[str, int] = {}
    for item in withheld_items:
        reason = _text(item.get("withheld_reason_code")) or "UNKNOWN"
        withheld_counts[reason] = withheld_counts.get(reason, 0) + 1
    full_count = len(items) if canonical_count is None else canonical_count
    return {
        "contract_version": CONTRACT_VERSION,
        "decision_queue_count": len(items),
        "canonical_decision_count": full_count,
        "decision_queue_type_counts": type_counts,
        "withheld_decision_count": len(withheld_items),
        "withheld_reason_counts": withheld_counts,
        "current_decision_keys": [item["decision_key"] for item in items],
        "truncated_decision_count": max(0, full_count - len(items)),
    }


def _generation_time(generation: dict[str, Any]) -> datetime | None:
    return _parse_datetime(
        _mapping(generation.get("github_security")).get("produced_at")
    )


def _apply_supersession(
    current: list[dict[str, Any]],
    previous_digest: dict[str, Any] | None,
    *,
    current_generation: dict[str, Any],
) -> list[dict[str, Any]]:
    if previous_digest is None:
        return []
    if previous_digest.get("contract_version") != DIGEST_CONTRACT_VERSION:
        raise ValueError(
            f"previous digest contract_version must be {DIGEST_CONTRACT_VERSION}"
        )
    previous_items = [
        item
        for item in previous_digest.get("decision_queue") or []
        if isinstance(item, dict)
    ]
    previous_by_key = {_text(item.get("decision_key")): item for item in previous_items}
    current_by_key = {_text(item.get("decision_key")): item for item in current}
    superseded: list[dict[str, Any]] = []

    for key, item in current_by_key.items():
        old = previous_by_key.get(key)
        if old and _text(old.get("decision_fingerprint")) != _text(
            item.get("decision_fingerprint")
        ):
            item["supersedes"] = {
                "source_generation": old.get("source_generation"),
                "decision_fingerprint": old.get("decision_fingerprint"),
            }

    current_time = _generation_time(current_generation)
    for key, old in sorted(previous_by_key.items()):
        replacement = current_by_key.get(key)
        if replacement and _text(replacement.get("decision_fingerprint")) == _text(
            old.get("decision_fingerprint")
        ):
            continue
        old_generation = _mapping(old.get("source_generation"))
        old_time = _generation_time(old_generation)
        source_is_newer = bool(current_time and old_time and current_time > old_time)
        if replacement:
            state = "reopened"
            reason_code = (
                "READBACK_STILL_OPEN"
                if source_is_newer
                else "CONTRACT_FINGERPRINT_CHANGED"
            )
        else:
            state = "authoritative-absence" if source_is_newer else "unverified-absence"
            reason_code = (
                "AUTHORITATIVE_READBACK_CLOSED"
                if source_is_newer
                else "READBACK_SOURCE_NOT_NEWER"
            )
        superseded.append(
            {
                "decision_key": key,
                "decision_fingerprint": old.get("decision_fingerprint"),
                "project": old.get("project"),
                "decision_type": old.get("decision_type"),
                "evidence_observed_at": old.get("evidence_observed_at"),
                "valid_until": old.get("valid_until"),
                "source_generation": old.get("source_generation"),
                "superseding_generation": current_generation,
                "superseding_fingerprint": (
                    replacement.get("decision_fingerprint") if replacement else None
                ),
                "readback_state": state,
                "reason_code": reason_code,
                "closure_eligible": state == "authoritative-absence",
            }
        )
    return superseded


def build_decision_digest(
    portfolio_truth: dict[str, Any],
    *,
    previous_digest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the deterministic producer-owned decision and readback digest."""
    actionable, withheld = _build_candidates(portfolio_truth)
    presented = actionable[:MAX_DECISION_QUEUE_ITEMS]
    generation = _source_generation(portfolio_truth)
    superseded = _apply_supersession(
        presented,
        previous_digest,
        current_generation=generation,
    )
    summary = summarize_decision_queue(
        presented,
        withheld=withheld,
        canonical_count=len(actionable),
    )
    return {
        "contract_version": DIGEST_CONTRACT_VERSION,
        "source": {
            "schema_version": _text(portfolio_truth.get("schema_version")) or "unknown",
            "generated_at": _text(portfolio_truth.get("generated_at")) or "unknown",
            "portfolio_truth_sha256": _portfolio_truth_sha256(portfolio_truth),
            "portfolio_truth_receipt_id": _mapping(portfolio_truth.get("producer")).get(
                "receipt_id"
            ),
            "github_security_receipt_id": _mapping(
                _mapping(portfolio_truth.get("inputs")).get("github_security")
            ).get("receipt_id"),
            "github_security_produced_at": _mapping(
                _mapping(portfolio_truth.get("inputs")).get("github_security")
            ).get("produced_at"),
        },
        "decision_queue": presented,
        "withheld_decisions": withheld,
        "superseded_decisions": superseded,
        "summary": summary,
    }


def render_decision_digest_markdown(digest: dict[str, Any]) -> str:
    """Render the compact decision digest without weakening actionability state."""
    source = _mapping(digest.get("source"))
    generated_at = _text(source.get("generated_at")) or "unknown"
    schema_version = _text(source.get("schema_version")) or "unknown"
    date_label = generated_at[:10] if generated_at != "unknown" else "unknown"
    decision_queue = [
        item for item in digest.get("decision_queue") or [] if isinstance(item, dict)
    ]
    withheld = [
        item
        for item in digest.get("withheld_decisions") or []
        if isinstance(item, dict)
    ]
    summary = _mapping(digest.get("summary"))
    count = int(summary.get("decision_queue_count") or len(decision_queue))

    lines = [
        f"## Portfolio Decision Digest — {date_label}",
        "",
        "### Decision Queue",
    ]
    if not decision_queue:
        lines.append("- No portfolio decisions clear the current evidence bar.")
    else:
        for item in decision_queue:
            lines.append(
                f"- **{item['project']}** [{item['decision_type']}] "
                f"`{item['decision_key']}`: {item['decision_question']} "
                f"Evidence observed `{item['evidence_observed_at']}`; valid until "
                f"`{item['valid_until']}`. Next: {item['recommended_action']}"
            )
    lines.extend(["", "### Withheld Decisions"])
    if not withheld:
        lines.append("- No incomplete decisions are withheld.")
    else:
        for item in withheld:
            lines.append(
                f"- **{item['project']}** [{item['decision_type']}]: withheld "
                f"`{item['withheld_reason_code']}`. {item['why_now']}"
            )
    lines.extend(
        [
            "",
            "### Source Freshness",
            f"- PortfolioTruthV1 schema `{schema_version}`, evaluated `{generated_at}`.",
            f"- GitHub security receipt `{_text(source.get('github_security_receipt_id')) or 'unknown'}`, produced `{_text(source.get('github_security_produced_at')) or 'unknown'}`.",
            "",
            "### Summary",
            f"{count} actionable decision{'s' if count != 1 else ''}; {len(withheld)} withheld | contract `{CONTRACT_VERSION}`",
        ]
    )
    return "\n".join(lines) + "\n"


def _load_object(path: Path, *, label: str) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{label} root must be an object")
    return raw


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render the DecisionQueueV2 digest from PortfolioTruthV1."
    )
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--previous-digest", type=Path)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)

    truth = _load_object(args.truth, label="portfolio truth")
    previous = (
        _load_object(args.previous_digest, label="previous decision digest")
        if args.previous_digest
        else None
    )
    digest = build_decision_digest(truth, previous_digest=previous)
    if args.format == "json":
        print(json.dumps(digest, indent=2, sort_keys=True))
    else:
        print(render_decision_digest_markdown(digest), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
