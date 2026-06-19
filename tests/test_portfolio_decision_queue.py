from __future__ import annotations

from src.portfolio_decision_queue import build_decision_queue, summarize_decision_queue


def _project(
    name: str,
    *,
    attention_state: str,
    security_risk: bool = False,
    dependabot_critical: int = 0,
    dependabot_high: int = 0,
) -> dict:
    return {
        "identity": {"display_name": name, "path": name},
        "derived": {
            "attention_state": attention_state,
            "registry_status": "active",
            "activity_status": "active",
        },
        "risk": {
            "risk_tier": "baseline",
            "risk_summary": "No elevated risk factors.",
            "security_risk": security_risk,
        },
        "security": {
            "dependabot_critical": dependabot_critical,
            "dependabot_high": dependabot_high,
        },
    }


def test_default_attention_without_decision_signal_stays_out_of_queue() -> None:
    truth = {
        "generated_at": "2026-06-19T04:36:19+00:00",
        "projects": [
            _project("Product", attention_state="active-product"),
            _project("Infra", attention_state="active-infra"),
            _project("Manual", attention_state="manual-only"),
            _project("Experiment", attention_state="experiment"),
        ],
    }

    assert build_decision_queue(truth) == []
    assert summarize_decision_queue([]) == {
        "contract_version": "decision_queue_v1",
        "decision_queue_count": 0,
        "decision_queue_type_counts": {},
    }


def test_decision_needed_project_enters_queue() -> None:
    truth = {
        "generated_at": "2026-06-19T04:36:19+00:00",
        "projects": [_project("NeedsDecision", attention_state="decision-needed")],
    }

    [item] = build_decision_queue(truth)
    assert item["project"] == "NeedsDecision"
    assert item["decision_type"] == "owner or human decision"
    assert item["source_freshness"] == "2026-06-19T04:36:19+00:00"
    assert "attention_state=decision-needed" in item["evidence"]


def test_security_risk_enters_queue_even_when_manual_only() -> None:
    truth = {
        "generated_at": "2026-06-19T04:36:19+00:00",
        "projects": [
            _project(
                "ManualSecurity",
                attention_state="manual-only",
                security_risk=True,
                dependabot_critical=1,
            )
        ],
    }

    [item] = build_decision_queue(truth)
    assert item["project"] == "ManualSecurity"
    assert item["decision_type"] == "security follow-up"
    assert item["evidence"] == ["security_risk=true; dependabot critical=1, high=0"]


def test_archived_security_risk_stays_out_of_queue() -> None:
    truth = {
        "projects": [
            _project(
                "ArchivedSecurity",
                attention_state="archived",
                security_risk=True,
                dependabot_critical=1,
            )
        ],
    }

    assert build_decision_queue(truth) == []
