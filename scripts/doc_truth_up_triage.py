#!/usr/bin/env python3
"""Build the `/doc-truth-up` triage list from the presence-claims audit artifacts.

Joins the audit pre-step (per-repo ``abs_path`` + git ``drifted`` flag) with the
audit cells (per-repo doc-quality disagreements) to rank which repos most likely
have docs out of sync with their code:

- **Tier 1** — repo drifted since the snapshot (code moved) OR the audit flagged a
  doc-quality disagreement. Run the reconciliation pass on these first.
- **Tier 2** — clean in the audit AND no commits since the snapshot. Lower priority.
  (Not a guarantee of accuracy: docs can be stale from evolution predating the snapshot.)

Output: ``output/doc-truth-up-targets.json`` (consumed by ``doc_truth_up_batch.py``).
Inputs are the gitignored audit artifacts, so run the presence-claims audit first.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT = REPO_ROOT / "output"
DEFAULT_PRESTEP = OUT / "presence-claims-audit-all-prestep.json"


def _latest_cells() -> Path:
    cells = sorted(OUT.glob("presence-claims-audit-*.cells.json"))
    if not cells:
        raise SystemExit("no presence-claims-audit-*.cells.json in output/ — run the audit first")
    return cells[-1]


def build_targets(prestep_path: Path, cells_path: Path) -> list[dict]:
    prestep = json.loads(prestep_path.read_text())
    cells = json.loads(cells_path.read_text())

    disagreements: dict[str, list[dict]] = defaultdict(list)
    for c in cells:
        if not c["bucket"].startswith("agree"):
            disagreements[c["project_key"]].append({"claim": c["claim"], "bucket": c["bucket"]})

    targets = []
    for r in prestep["records"]:
        key = r["project_key"]
        dis = disagreements.get(key, [])
        drifted = bool(r.get("drifted"))
        targets.append(
            {
                "project_key": key,
                "abs_path": r["abs_path"],
                "primary_file_name": r["primary_file_name"],
                "drifted": drifted,
                "disagreement_count": len(dis),
                "disagreements": dis,
                "tier": 1 if (drifted or dis) else 2,
            }
        )
    # Tier 1 first; within a tier, most disagreements first, then drifted, then key.
    targets.sort(
        key=lambda t: (t["tier"], -t["disagreement_count"], not t["drifted"], t["project_key"])
    )
    return targets


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the /doc-truth-up triage list.")
    ap.add_argument("--prestep", default=str(DEFAULT_PRESTEP))
    ap.add_argument("--cells", default="", help="Audit cells JSON (default: newest in output/).")
    ap.add_argument("--out", default=str(OUT / "doc-truth-up-targets.json"))
    args = ap.parse_args()

    cells_path = Path(args.cells) if args.cells else _latest_cells()
    targets = build_targets(Path(args.prestep), cells_path)
    Path(args.out).write_text(json.dumps(targets, indent=2))

    t1 = [t for t in targets if t["tier"] == 1]
    print(
        f"{len(targets)} eligible · Tier 1 (run first): {len(t1)} · Tier 2: {len(targets) - len(t1)}"
    )
    print(
        f"  (Tier 1 = {sum(t['drifted'] for t in t1)} drifted + "
        f"{sum(bool(t['disagreement_count']) for t in t1)} audit-flagged)"
    )
    print(f"wrote {args.out} (from {cells_path.name})")


if __name__ == "__main__":
    main()
