#!/usr/bin/env python3
"""Write or verify the EvidenceFreshnessConformanceV1 contract artifacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evidence_freshness_conformance import (  # noqa: E402
    MANIFEST_RELATIVE_PATH,
    VECTORS_RELATIVE_PATH,
    manifest_bytes,
    vectors_bytes,
)


def _artifacts() -> tuple[tuple[Path, bytes], ...]:
    return (
        (REPO_ROOT / VECTORS_RELATIVE_PATH, vectors_bytes()),
        (REPO_ROOT / MANIFEST_RELATIVE_PATH, manifest_bytes()),
    )


def _check() -> int:
    drifted = [
        path.relative_to(REPO_ROOT)
        for path, expected in _artifacts()
        if not path.is_file() or path.read_bytes() != expected
    ]
    if drifted:
        print(
            "Evidence freshness conformance artifacts drifted: "
            + ", ".join(str(path) for path in drifted),
            file=sys.stderr,
        )
        print(
            "Regenerate with: python scripts/generate_evidence_freshness_conformance.py",
            file=sys.stderr,
        )
        return 1
    print("EvidenceFreshnessConformanceV1 artifacts are current.")
    return 0


def _write() -> int:
    for path, content in _artifacts():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        print(f"Wrote {path.relative_to(REPO_ROOT)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when committed artifacts differ from deterministic output.",
    )
    args = parser.parse_args()
    return _check() if args.check else _write()


if __name__ == "__main__":
    raise SystemExit(main())
