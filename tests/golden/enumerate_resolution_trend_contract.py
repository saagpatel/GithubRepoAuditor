"""Characterization enumerator for ``_build_resolution_trend`` — the 1,852-line
god-function in ``operator_resolution_trend`` whose 1,676-line ``payload.update({...})``
assembles the full operator resolution-trend payload (320+ keys) from the
apply-chain / summary-context stages.

The sibling enumerators pin the lower layers:
  * ``enumerate_recovery_state_contract.py`` — the pure ``(status:str)->str`` classifiers.
  * ``enumerate_composer_contract.py``       — the per-tier dict/list composers.
Neither exercises the *top-level assembly* — how the god-function wires the
apply-chain tiers and summary-context into the final payload dict the two real
consumers (``operator_control_center`` and ``operator_decision_quality``) read.
This enumerator captures that assembled payload across a representative input
corpus into a frozen golden, so the upcoming decomposition of the god-function
(extracting the payload-assembly seam, then collapsing the per-tier blocks onto a
parametrized base) is provably byte-identical: re-run this, diff the JSON, and a
clean diff proves the structure was preserved.

Safety: imports only the pure-computation module (verified free of import-time
DB/IO side effects, same as the sibling enumerators) and calls
``_build_resolution_trend`` on in-memory synthetic inputs. Never opens a database.

Regenerate the golden only with an intentional, reviewed behavior change::

    uv run python tests/golden/enumerate_resolution_trend_contract.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import src.operator_resolution_trend as m

REPO = Path(__file__).resolve().parents[2]
GOLDEN_PATH = REPO / "tests" / "golden" / "resolution_trend_contract.golden.json"


def _item(
    item_id: str,
    *,
    lane: str,
    kind: str,
    repo: str,
    title: str,
    age_days: int,
    severity: float,
) -> dict[str, Any]:
    """A queue/snapshot item rich enough for target selection + class keying."""
    return {
        "item_id": item_id,
        "id": item_id,
        "lane": lane,
        "kind": kind,
        "repo": repo,
        "title": title,
        "age_days": age_days,
        "severity": severity,
        "score": severity,
        "recommended_next_step": f"Act on {title}.",
        "reason": f"{title} needs attention.",
    }


def _snapshot(items: list[dict], *, generated_at: str) -> dict[str, Any]:
    """A history snapshot keyed by ``_queue_identity`` (item_id when present)."""
    return {
        "snapshot": {
            "items": {it["item_id"]: it for it in items},
            "has_attention": any(it["lane"] in ("blocked", "urgent") for it in items),
            "generated_at": generated_at,
        }
    }


def _ts(day: int) -> str:
    return f"2026-04-{day:02d}T12:00:00Z"


# --------------------------------------------------------------------------- #
# Corpus: each case is (label, queue, history, evidence_events,
# confidence_calibration, current_generated_at). Designed to exercise the empty
# branch (falsy primary_target -> IfExp false-branches) AND a stale-attention
# target that survives the full apply-chain (truthy primary_target -> IfExp
# true-branches + populated per-tier summaries/hotspots).
# --------------------------------------------------------------------------- #
def _corpus() -> list[tuple[str, list, list, list, dict, str]]:
    blocked = _item(
        "RepoA:Harden auth",
        lane="blocked",
        kind="security",
        repo="RepoA",
        title="Harden auth",
        age_days=12,
        severity=0.9,
    )
    urgent = _item(
        "RepoB:Ship migration",
        lane="urgent",
        kind="migration",
        repo="RepoB",
        title="Ship migration",
        age_days=9,
        severity=0.7,
    )
    ready = _item(
        "RepoC:Polish docs",
        lane="ready",
        kind="docs",
        repo="RepoC",
        title="Polish docs",
        age_days=2,
        severity=0.3,
    )

    # A long stale-attention history so the blocked item climbs the apply chain.
    stale_history = [
        _snapshot([blocked, urgent, ready], generated_at=_ts(day))
        for day in range(1, 9)
    ]

    evidence = [
        {
            "item_id": "RepoA:Harden auth",
            "kind": "intervention",
            "outcome": "in-progress",
            "generated_at": _ts(7),
            "magnitude": 0.8,
        },
        {
            "item_id": "RepoA:Harden auth",
            "kind": "resolution",
            "outcome": "confirmed",
            "generated_at": _ts(8),
            "magnitude": 0.6,
        },
    ]
    calibration = {
        "confidence": 0.62,
        "sample_size": 14,
        "reliability": "noisy",
        "recent_accuracy": 0.55,
    }

    return [
        ("empty", [], [], [], {}, _ts(9)),
        (
            "single_blocked_stale",
            [blocked],
            stale_history,
            evidence,
            calibration,
            _ts(9),
        ),
        (
            "multi_class_attention",
            [blocked, urgent, ready],
            stale_history,
            evidence,
            calibration,
            _ts(9),
        ),
        (
            "attention_no_history",
            [blocked, urgent],
            [],
            [],
            {},
            _ts(9),
        ),
    ]


def _jsonable(value: Any) -> Any:
    """Stable, lossless-enough JSON projection. Sets -> sorted lists; tuples ->
    lists; anything exotic -> its repr (recorded as part of the contract)."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, set):
        return ["<<set>>", *sorted(_jsonable(v) for v in value)]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def build_contract() -> dict[str, Any]:
    contract: dict[str, Any] = {}
    for label, queue, history, evidence, calibration, generated_at in _corpus():
        payload = m._build_resolution_trend(
            queue,
            history,
            evidence,
            confidence_calibration=calibration,
            current_generated_at=generated_at,
        )
        contract[label] = _jsonable(payload)
    return contract


def main() -> None:
    contract = build_contract()
    GOLDEN_PATH.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    # Operator-facing sanity print (not part of the contract).
    cases = len(contract)
    keysets = {label: len(rows) for label, rows in contract.items()}
    primary = {
        label: bool(rows.get("primary_target")) for label, rows in contract.items()
    }
    print(f"wrote {GOLDEN_PATH.relative_to(REPO)}")
    print(f"cases: {cases}")
    print(f"keys per case: {keysets}")
    print(f"truthy primary_target per case: {primary}")


if __name__ == "__main__":
    main()
