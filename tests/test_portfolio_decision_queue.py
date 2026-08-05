from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from src.portfolio_decision_queue import (
    DIGEST_CONTRACT_VERSION,
    SECURITY_DECISION_VALIDITY_HOURS,
    build_decision_digest,
    build_decision_queue,
    build_withheld_decisions,
    main,
    render_decision_digest_markdown,
    summarize_decision_queue,
)


OBSERVED_AT = "2026-08-05T01:03:15+00:00"
PRODUCED_AT = "2026-08-05T01:03:27+00:00"
GENERATED_AT = "2026-08-05T01:06:22+00:00"
RECEIPT_ID = "sha256:" + "a" * 64
TRUTH_RECEIPT_ID = "sha256:" + "b" * 64
CONTENT_SHA256 = "c" * 64
PRODUCER_COMMIT = "d" * 40


def _project(
    name: str,
    *,
    attention_state: str,
    security_risk: bool = False,
    dependabot_critical: int = 0,
    dependabot_high: int = 0,
    owner: str = "d",
) -> dict:
    return {
        "identity": {
            "project_key": name,
            "display_name": name,
            "path": name,
            "repo_full_name": f"saagpatel/{name}",
        },
        "declared": {"owner": owner},
        "derived": {
            "attention_state": attention_state,
            "activity_status": "active",
        },
        "risk": {
            "risk_tier": "moderate" if security_risk else "baseline",
            "risk_summary": "Open high severity alerts." if security_risk else "",
            "security_risk": security_risk,
        },
        "security": {
            "coverage_state": "complete",
            "receipt_state": "fresh",
            "source_produced_at": PRODUCED_AT,
            "dependabot_critical": dependabot_critical,
            "dependabot_high": dependabot_high,
            "providers": {
                "dependabot": {
                    "state": "observed",
                    "observed_at": OBSERVED_AT,
                    "pagination_complete": True,
                    "completed": True,
                    "counts": {
                        "critical": dependabot_critical,
                        "high": dependabot_high,
                    },
                }
            },
        },
    }


def _truth(projects: list[dict], *, generated_at: str = GENERATED_AT) -> dict:
    return {
        "schema_version": "0.11.0",
        "generated_at": generated_at,
        "producer": {
            "commit": PRODUCER_COMMIT,
            "receipt_id": TRUTH_RECEIPT_ID,
        },
        "inputs": {
            "github_security": {
                "source_id": "github-security-coverage-receipt",
                "schema_version": "GitHubSecurityCoverageReceiptV1",
                "produced_at": PRODUCED_AT,
                "state": "fresh",
                "producer_commit": PRODUCER_COMMIT,
                "path": "/evidence/github-security-coverage-latest.json",
                "receipt_id": RECEIPT_ID,
                "content_sha256": CONTENT_SHA256,
            }
        },
        "projects": projects,
    }


def _next_truth(
    previous: dict,
    *,
    project: dict,
    produced_at: str = "2026-08-06T01:03:27+00:00",
    generated_at: str = "2026-08-06T01:06:22+00:00",
) -> dict:
    value = copy.deepcopy(previous)
    value["generated_at"] = generated_at
    value["producer"]["receipt_id"] = "sha256:" + "e" * 64
    source = value["inputs"]["github_security"]
    source["produced_at"] = produced_at
    source["receipt_id"] = "sha256:" + "f" * 64
    source["content_sha256"] = "1" * 64
    project["security"]["source_produced_at"] = produced_at
    project["security"]["providers"]["dependabot"]["observed_at"] = (
        "2026-08-06T01:03:15+00:00"
    )
    value["projects"] = [project]
    return value


def test_default_attention_without_decision_signal_stays_out_of_queue() -> None:
    truth = _truth(
        [
            _project("Product", attention_state="active-product"),
            _project("Infra", attention_state="active-infra"),
            _project("Manual", attention_state="manual-only"),
            _project("Experiment", attention_state="experiment"),
        ]
    )

    assert build_decision_queue(truth) == []
    assert build_withheld_decisions(truth) == []
    assert summarize_decision_queue([]) == {
        "contract_version": "decision_queue_v2",
        "decision_queue_count": 0,
        "canonical_decision_count": 0,
        "decision_queue_type_counts": {},
        "withheld_decision_count": 0,
        "withheld_reason_counts": {},
        "current_decision_keys": [],
        "truncated_decision_count": 0,
    }


def test_generic_owner_decision_is_withheld_instead_of_consumer_synthesized() -> None:
    truth = _truth([_project("NeedsDecision", attention_state="decision-needed")])

    assert build_decision_queue(truth) == []
    [withheld] = build_withheld_decisions(truth)
    assert withheld["decision_type"] == "owner or human decision"
    assert withheld["actionability"] == "withheld"
    assert withheld["withheld_reason_code"] == "OWNER_DECISION_SPEC_INCOMPLETE"
    assert withheld["decision_key"].startswith("sha256:")


def test_security_decision_has_complete_stable_contract_and_dual_clocks() -> None:
    truth = _truth(
        [
            _project(
                "MCPAudit",
                attention_state="decision-needed",
                security_risk=True,
                dependabot_high=1,
            )
        ]
    )

    [first] = build_decision_queue(truth)
    [replay] = build_decision_queue(copy.deepcopy(truth))
    assert first == replay
    assert first["schema_version"] == "portfolio_decision_item_v2"
    assert first["actionability"] == "actionable"
    assert first["decision_key"].startswith("sha256:")
    assert first["decision_fingerprint"].startswith("sha256:")
    assert first["owner"] == "d"
    assert [value["id"] for value in first["allowed_outcomes"]] == [
        "accept",
        "defer",
        "reject",
    ]
    assert first["approval_boundary"]["execution_is_separate"] is True
    assert first["evaluated_at"] == GENERATED_AT
    assert first["evidence_observed_at"] == OBSERVED_AT
    assert first["valid_until"] == "2026-08-06T13:03:15+00:00"
    assert first["readback_contract"]["requires_newer_receipt"] is True
    assert first["readback_contract"]["supporting_evidence_only"] == ["bridge-shipped"]
    assert SECURITY_DECISION_VALIDITY_HOURS == 36


def test_current_security_fixture_freezes_ids_fingerprints_and_withheld_items() -> None:
    fixture = json.loads(
        (
            Path(__file__).parent
            / "fixtures"
            / "portfolio_decision_current_security_v2.json"
        ).read_text(encoding="utf-8")
    )
    digest = build_decision_digest(fixture["portfolio_truth"])
    actual = {
        item["project"]: {
            "decision_key": item["decision_key"],
            "decision_fingerprint": item["decision_fingerprint"],
        }
        for item in digest["decision_queue"]
    }
    withheld = {
        item["project"]: item["withheld_reason_code"]
        for item in digest["withheld_decisions"]
    }
    assert actual == fixture["expected_security_decisions"]
    assert withheld == fixture["expected_withheld"]


def test_projection_regeneration_does_not_rejuvenate_evidence_or_fingerprint() -> None:
    truth = _truth(
        [
            _project(
                "MCPAudit",
                attention_state="decision-needed",
                security_risk=True,
                dependabot_high=1,
            )
        ]
    )
    regenerated = copy.deepcopy(truth)
    regenerated["generated_at"] = "2026-08-05T08:00:00+00:00"
    regenerated["producer"]["receipt_id"] = "sha256:" + "9" * 64

    [first] = build_decision_queue(truth)
    [second] = build_decision_queue(regenerated)
    assert second["evaluated_at"] == "2026-08-05T08:00:00+00:00"
    assert second["evidence_observed_at"] == first["evidence_observed_at"]
    assert second["valid_until"] == first["valid_until"]
    assert second["decision_key"] == first["decision_key"]
    assert second["decision_fingerprint"] == first["decision_fingerprint"]


@pytest.mark.parametrize(
    ("mutate", "reason_code"),
    [
        (
            lambda truth: truth.update({"generated_at": "2026-08-07T01:06:22+00:00"}),
            "SECURITY_EVIDENCE_EXPIRED",
        ),
        (
            lambda truth: truth["inputs"]["github_security"].update({"receipt_id": ""}),
            "SECURITY_SOURCE_IDENTITY_INCOMPLETE",
        ),
        (
            lambda truth: truth["projects"][0]["security"].update(
                {"source_produced_at": "2026-08-04T00:00:00+00:00"}
            ),
            "SECURITY_SOURCE_MISMATCH",
        ),
    ],
)
def test_security_contract_failures_are_withheld_with_stable_reason_codes(
    mutate, reason_code: str
) -> None:
    truth = _truth(
        [
            _project(
                "MCPAudit",
                attention_state="decision-needed",
                security_risk=True,
                dependabot_high=1,
            )
        ]
    )
    mutate(truth)
    assert build_decision_queue(truth) == []
    [withheld] = build_withheld_decisions(truth)
    assert withheld["withheld_reason_code"] == reason_code


def test_archived_security_risk_stays_out_of_queue() -> None:
    truth = _truth(
        [
            _project(
                "ArchivedSecurity",
                attention_state="archived",
                security_risk=True,
                dependabot_high=1,
            )
        ]
    )
    assert build_decision_queue(truth) == []
    assert build_withheld_decisions(truth) == []


def test_newer_authoritative_absence_closes_prior_fingerprint() -> None:
    old_project = _project(
        "MCPAudit",
        attention_state="decision-needed",
        security_risk=True,
        dependabot_high=1,
    )
    first_truth = _truth([old_project])
    first = build_decision_digest(first_truth)
    resolved_project = _project("MCPAudit", attention_state="active-infra")
    resolved_project["security"]["source_produced_at"] = "2026-08-06T01:03:27+00:00"
    resolved_project["security"]["providers"]["dependabot"]["observed_at"] = (
        "2026-08-06T01:03:15+00:00"
    )
    second_truth = _next_truth(first_truth, project=resolved_project)

    second = build_decision_digest(second_truth, previous_digest=first)
    assert second["decision_queue"] == []
    [historical] = second["superseded_decisions"]
    assert historical["readback_state"] == "authoritative-absence"
    assert historical["reason_code"] == "AUTHORITATIVE_READBACK_CLOSED"
    assert historical["closure_eligible"] is True
    assert historical["superseding_fingerprint"] is None


def test_newer_nonzero_receipt_reopens_with_superseding_fingerprint() -> None:
    first_truth = _truth(
        [
            _project(
                "MCPAudit",
                attention_state="decision-needed",
                security_risk=True,
                dependabot_high=1,
            )
        ]
    )
    first = build_decision_digest(first_truth)
    still_open = _project(
        "MCPAudit",
        attention_state="decision-needed",
        security_risk=True,
        dependabot_high=2,
    )
    second_truth = _next_truth(first_truth, project=still_open)

    second = build_decision_digest(second_truth, previous_digest=first)
    [current] = second["decision_queue"]
    [historical] = second["superseded_decisions"]
    assert (
        current["supersedes"]["decision_fingerprint"]
        == first["decision_queue"][0]["decision_fingerprint"]
    )
    assert historical["readback_state"] == "reopened"
    assert historical["reason_code"] == "READBACK_STILL_OPEN"
    assert historical["superseding_fingerprint"] == current["decision_fingerprint"]


def test_digest_renders_actionable_and_withheld_contracts() -> None:
    truth = _truth(
        [
            _project(
                "MCPAudit",
                attention_state="decision-needed",
                security_risk=True,
                dependabot_high=1,
            ),
            _project("proof-pr", attention_state="decision-needed"),
        ]
    )
    digest = build_decision_digest(truth)
    rendered = render_decision_digest_markdown(digest)

    assert digest["contract_version"] == DIGEST_CONTRACT_VERSION
    assert digest["summary"]["decision_queue_count"] == 1
    assert digest["summary"]["withheld_decision_count"] == 1
    assert "MCPAudit" in rendered
    assert "proof-pr" in rendered
    assert "OWNER_DECISION_SPEC_INCOMPLETE" in rendered
    assert "Evidence observed" in rendered


def test_cli_json_and_markdown_are_deterministic(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    truth_path = tmp_path / "portfolio-truth.json"
    truth_path.write_text(
        json.dumps(
            _truth(
                [
                    _project(
                        "MCPAudit",
                        attention_state="decision-needed",
                        security_risk=True,
                        dependabot_high=1,
                    )
                ]
            )
        ),
        encoding="utf-8",
    )

    assert main(["--truth", str(truth_path), "--format", "json"]) == 0
    first = capsys.readouterr().out
    assert main(["--truth", str(truth_path), "--format", "json"]) == 0
    second = capsys.readouterr().out
    assert first == second

    previous = tmp_path / "previous.json"
    previous.write_text(first, encoding="utf-8")
    assert (
        main(
            [
                "--truth",
                str(truth_path),
                "--previous-digest",
                str(previous),
                "--format",
                "markdown",
            ]
        )
        == 0
    )
    markdown = capsys.readouterr().out
    assert "## Portfolio Decision Digest — 2026-08-05" in markdown
    assert "**MCPAudit** [security follow-up]" in markdown
