"""Decision-queue compression for portfolio truth.

This layer is intentionally narrower than default attention. ``active-product``
and ``active-infra`` form the watch set; the decision queue is only for current
truth entries that already carry a concrete decision signal.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "decision_queue_v1"
DIGEST_CONTRACT_VERSION = "portfolio_decision_digest_v1"
MAX_DECISION_QUEUE_ITEMS = 5

NON_DEFAULT_STATES = frozenset(
    {"parked", "archived", "experiment", "evidence-history", "manual-only"}
)


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


@dataclass(frozen=True)
class DecisionQueueItem:
    project: str
    path: str
    attention_state: str
    decision_type: str
    why_now: str
    evidence: tuple[str, ...]
    source_freshness: str
    recommended_action: str
    do_not_refresh_docs_unless: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "path": self.path,
            "attention_state": self.attention_state,
            "decision_type": self.decision_type,
            "why_now": self.why_now,
            "evidence": list(self.evidence),
            "source_freshness": self.source_freshness,
            "recommended_action": self.recommended_action,
            "do_not_refresh_docs_unless": self.do_not_refresh_docs_unless,
        }


def _decision_for_project(
    project: dict[str, Any], *, generated_at: str
) -> DecisionQueueItem | None:
    identity = _mapping(project.get("identity"))
    derived = _mapping(project.get("derived"))
    risk = _mapping(project.get("risk"))
    security = _mapping(project.get("security"))

    attention_state = _text(derived.get("attention_state")) or "manual-only"
    project_name = _text(identity.get("display_name")) or "Repo"
    path = _text(identity.get("path")) or project_name

    if attention_state in {"archived", "evidence-history"}:
        return None

    evidence: list[str] = []
    decision_type = ""
    why_now = ""
    recommended_action = ""

    if bool(risk.get("security_risk")):
        critical = int(security.get("dependabot_critical") or 0)
        high = int(security.get("dependabot_high") or 0)
        decision_type = "security follow-up"
        why_now = "Current portfolio truth marks this project with security risk."
        evidence.append(f"security_risk=true; dependabot critical={critical}, high={high}")
        recommended_action = "Decide whether to run the repo's security follow-up lane."
    elif attention_state in NON_DEFAULT_STATES:
        return None
    elif attention_state == "decision-needed":
        decision_type = "owner or human decision"
        why_now = "Current portfolio truth marks this project as decision-needed."
        evidence.append("attention_state=decision-needed")
        risk_summary = _text(risk.get("risk_summary"))
        if risk_summary:
            evidence.append(risk_summary)
        recommended_action = "Resolve the explicit portfolio decision before expanding scope."
    else:
        return None

    return DecisionQueueItem(
        project=project_name,
        path=path,
        attention_state=attention_state,
        decision_type=decision_type,
        why_now=why_now,
        evidence=tuple(evidence),
        source_freshness=generated_at or "unknown",
        recommended_action=recommended_action,
        do_not_refresh_docs_unless=(
            "Do not refresh context, roadmap, handoff, AGENTS, or docs unless "
            "that work directly resolves this decision."
        ),
    )


def build_decision_queue(portfolio_truth: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the small decision queue from current portfolio truth.

    This is deliberately stricter than the watch set: active product or active
    infrastructure projects are ignored unless current truth also contains a
    concrete decision signal.
    """
    projects = portfolio_truth.get("projects") or []
    generated_at = _text(portfolio_truth.get("generated_at"))
    queue: list[DecisionQueueItem] = []
    for project in projects:
        if not isinstance(project, dict):
            continue
        item = _decision_for_project(project, generated_at=generated_at)
        if item is not None:
            queue.append(item)

    decision_rank = {"security follow-up": 0, "owner or human decision": 1}
    queue.sort(
        key=lambda item: (
            decision_rank.get(item.decision_type, 9),
            item.project.lower(),
        )
    )
    return [item.to_dict() for item in queue[:MAX_DECISION_QUEUE_ITEMS]]


def summarize_decision_queue(items: list[dict[str, Any]]) -> dict[str, Any]:
    type_counts: dict[str, int] = {}
    for item in items:
        decision_type = _text(item.get("decision_type")) or "unknown"
        type_counts[decision_type] = type_counts.get(decision_type, 0) + 1
    return {
        "contract_version": CONTRACT_VERSION,
        "decision_queue_count": len(items),
        "decision_queue_type_counts": type_counts,
    }


def build_decision_digest(portfolio_truth: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic, truth-native operator digest.

    The digest deliberately contains only the decision queue. It does not
    reintroduce stale-repo, weak-context, or prose-based "unshipped" watch
    lists that the portfolio attention contract excludes from decisions.
    """
    decision_queue = build_decision_queue(portfolio_truth)
    summary = summarize_decision_queue(decision_queue)
    return {
        "contract_version": DIGEST_CONTRACT_VERSION,
        "source": {
            "schema_version": _text(portfolio_truth.get("schema_version")) or "unknown",
            "generated_at": _text(portfolio_truth.get("generated_at")) or "unknown",
        },
        "decision_queue": decision_queue,
        "summary": summary,
    }


def render_decision_digest_markdown(digest: dict[str, Any]) -> str:
    """Render the compact nightly decision digest as deterministic Markdown."""
    source = _mapping(digest.get("source"))
    generated_at = _text(source.get("generated_at")) or "unknown"
    schema_version = _text(source.get("schema_version")) or "unknown"
    date_label = generated_at[:10] if generated_at != "unknown" else "unknown"
    decision_queue = [
        item for item in digest.get("decision_queue") or [] if isinstance(item, dict)
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
            project = _text(item.get("project")) or "Unknown project"
            decision_type = _text(item.get("decision_type")) or "unknown"
            why_now = _text(item.get("why_now")) or "No current rationale recorded."
            next_action = (
                _text(item.get("recommended_action")) or "Resolve the current decision."
            )
            lines.append(
                f"- **{project}** [{decision_type}]: {why_now} Next: {next_action}"
            )

    lines.extend(
        [
            "",
            "### Source Freshness",
            f"- PortfolioTruthV1 schema `{schema_version}`, generated `{generated_at}`.",
            "",
            "### Summary",
            f"{count} decision{'s' if count != 1 else ''} | contract `{CONTRACT_VERSION}`",
        ]
    )
    return "\n".join(lines) + "\n"


def _load_portfolio_truth(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("portfolio truth root must be an object")
    return raw


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render the DecisionQueueV1 digest from PortfolioTruthV1."
    )
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)

    digest = build_decision_digest(_load_portfolio_truth(args.truth))
    if args.format == "json":
        print(json.dumps(digest, indent=2, sort_keys=True))
    else:
        print(render_decision_digest_markdown(digest), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
