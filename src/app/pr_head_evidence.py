"""CLI adapter for local PR head-evidence snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from src.pr_head_evidence import (
    SnapshotValidationError,
    evaluate_snapshot,
    invalid_snapshot_verdict,
    parse_snapshot,
)


class PRHeadEvidenceArgs(Protocol):
    snapshot: str


def run_pr_head_evidence_mode(args: PRHeadEvidenceArgs) -> None:
    """Evaluate one local snapshot and emit deterministic JSON to stdout."""

    path = Path(args.snapshot)
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        verdict = invalid_snapshot_verdict(
            "snapshot_unreadable",
            [f"{exc.__class__.__name__}: {exc}"],
        )
        print(json.dumps(verdict, indent=2, sort_keys=True))
        raise SystemExit(2) from None
    try:
        value = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        verdict = invalid_snapshot_verdict(
            "snapshot_invalid_json",
            [f"line {exc.lineno}, column {exc.colno}: {exc.msg}"],
        )
        print(json.dumps(verdict, indent=2, sort_keys=True))
        raise SystemExit(2) from None
    try:
        snapshot = parse_snapshot(value)
    except SnapshotValidationError as exc:
        verdict = invalid_snapshot_verdict("snapshot_malformed", exc.errors)
        print(json.dumps(verdict, indent=2, sort_keys=True))
        raise SystemExit(2) from None
    verdict = evaluate_snapshot(snapshot)
    print(json.dumps(verdict, indent=2, sort_keys=True))
    if verdict["state"] == "unknown":
        raise SystemExit(2)
    if not verdict["current"]:
        raise SystemExit(1)
