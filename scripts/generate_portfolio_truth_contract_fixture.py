#!/usr/bin/env python3
"""Write or verify the portable PortfolioTruth consumer contract artifacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.portfolio_truth_contract_fixture import (  # noqa: E402
    CONSUMER_PROFILE_MANIFEST_PATHS,
    FIXTURE_RELATIVE_PATH,
    MANIFEST_RELATIVE_PATH,
    PORTABLE_FIXTURE_RELATIVE_PATH,
    build_contract_fixture,
    build_portable_contract_fixture,
    consumer_profile_manifest_bytes,
    fixture_bytes,
    manifest_bytes,
    portable_fixture_bytes,
)
from src.portfolio_truth_validate import validate_truth_snapshot_payload  # noqa: E402


def _expected_artifacts() -> tuple[tuple[Path, bytes], ...]:
    profile_manifests = tuple(
        (
            REPO_ROOT / manifest_path,
            consumer_profile_manifest_bytes(profile_id),
        )
        for profile_id, manifest_path in sorted(
            CONSUMER_PROFILE_MANIFEST_PATHS.items()
        )
    )
    return (
        (REPO_ROOT / FIXTURE_RELATIVE_PATH, fixture_bytes()),
        (REPO_ROOT / MANIFEST_RELATIVE_PATH, manifest_bytes()),
        (REPO_ROOT / PORTABLE_FIXTURE_RELATIVE_PATH, portable_fixture_bytes()),
        *profile_manifests,
    )


def _check() -> int:
    try:
        validate_truth_snapshot_payload(build_contract_fixture())
        validate_truth_snapshot_payload(build_portable_contract_fixture())
    except ValueError as exc:
        print(
            f"Portable PortfolioTruth consumer contract is invalid: {exc}",
            file=sys.stderr,
        )
        return 1
    drifted: list[Path] = []
    for path, expected in _expected_artifacts():
        if not path.is_file() or path.read_bytes() != expected:
            drifted.append(path.relative_to(REPO_ROOT))
    if drifted:
        print(
            "PortfolioTruth consumer contract drifted: "
            + ", ".join(str(path) for path in drifted),
            file=sys.stderr,
        )
        print(
            "Regenerate with: python "
            "scripts/generate_portfolio_truth_contract_fixture.py",
            file=sys.stderr,
        )
        return 1
    print("Portable PortfolioTruth consumer contract is current.")
    return 0


def _write() -> int:
    for path, content in _expected_artifacts():
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
