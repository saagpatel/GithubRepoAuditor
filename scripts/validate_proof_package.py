#!/usr/bin/env python3
"""Validate a proof-package.v1 manifest.

This is deliberately lightweight. It verifies structure and local file
references so proof packages stay easy to inspect without becoming a platform.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Repo-local imports must work whether this runs as a script or is imported by
# the test suite, so the project root goes on the path before src/ is touched.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.portfolio_truth_types import (  # noqa: E402
    SCHEMA_VERSION as PRODUCER_TRUTH_SCHEMA_VERSION,
)
from src.portfolio_truth_types import TRUTH_LATEST_FILENAME  # noqa: E402

ALLOWED_STATUSES = {"passed", "failed", "partial", "stale"}
# Portfolio Command Center reads a snapshot older than this as aging, then
# stale. A proof package whose published truth has already left the fresh band
# cannot honestly claim to demonstrate the current app.
CONSUMER_FRESH_WINDOW_HOURS = 48
TRUTH_ARTIFACT_PREFIX = "portfolio-truth"
REQUIRED_TOP_LEVEL = {
    "schema_version",
    "package_id",
    "subject",
    "producer",
    "source_state",
    "claims",
    "verification",
    "safety",
    "artifacts",
}
REQUIRED_ARTIFACT_FIELDS = {"id", "kind", "path", "description", "required"}
REQUIRED_CLAIM_FIELDS = {"id", "statement", "status", "evidence"}


def _load_manifest(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("manifest must be a JSON object")
    return data


def _resolve_artifact_path(manifest_path: Path, artifact_path: str) -> Path:
    candidate = Path(artifact_path)
    return candidate if candidate.is_absolute() else manifest_path.parent / candidate


def _truth_artifacts(manifest_path: Path, artifacts: Any) -> list[tuple[str, Path]]:
    """Portfolio-truth snapshots this package publishes as local evidence."""
    found: list[tuple[str, Path]] = []
    if not isinstance(artifacts, list):
        return found
    for artifact in artifacts:
        if not isinstance(artifact, dict) or artifact.get("external", False):
            continue
        artifact_path = artifact.get("path")
        if not isinstance(artifact_path, str):
            continue
        resolved = _resolve_artifact_path(manifest_path, artifact_path)
        if (
            resolved.name.startswith(TRUTH_ARTIFACT_PREFIX)
            and resolved.suffix == ".json"
        ):
            found.append((artifact_path, resolved))
    return found


def _age_hours(generated_at: str, now: datetime) -> float | None:
    try:
        parsed = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (now - parsed).total_seconds() / 3600


def validate_truth_currency(manifest: dict[str, Any], path: Path) -> list[str]:
    """Refuse a proof package whose published truth no longer demonstrates the app.

    Structural validity is not enough for a demo lane: a package can be perfectly
    well-formed while pointing at a snapshot from a retired schema or a date that
    the consumer already renders as stale. Both are silent failures at screenshot
    time, so they are hard errors here.
    """
    truth_artifacts = _truth_artifacts(path, manifest.get("artifacts"))
    if not truth_artifacts:
        return []

    errors: list[str] = []
    source_state = manifest.get("source_state")
    source_state = source_state if isinstance(source_state, dict) else {}

    declared_schema = source_state.get("source_truth_schema")
    if declared_schema != PRODUCER_TRUTH_SCHEMA_VERSION:
        errors.append(
            f"source_state.source_truth_schema is {declared_schema!r}; the producer "
            f"currently emits {PRODUCER_TRUTH_SCHEMA_VERSION!r}"
        )

    window = source_state.get("freshness_window_hours")
    if not isinstance(window, (int, float)) or isinstance(window, bool) or window <= 0:
        window = CONSUMER_FRESH_WINDOW_HOURS

    now = datetime.now(timezone.utc)
    for declared_path, resolved in truth_artifacts:
        try:
            snapshot = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errors.append(f"truth artifact unreadable: {declared_path} ({exc})")
            continue
        if not isinstance(snapshot, dict):
            errors.append(f"truth artifact is not a JSON object: {declared_path}")
            continue

        schema_version = snapshot.get("schema_version")
        if schema_version != PRODUCER_TRUTH_SCHEMA_VERSION:
            errors.append(
                f"{declared_path} declares schema_version {schema_version!r}; "
                f"the producer currently emits {PRODUCER_TRUTH_SCHEMA_VERSION!r}"
            )

        # History snapshots are old on purpose; only the published "latest"
        # snapshot has to sit inside the consumer's fresh window.
        if resolved.name != TRUTH_LATEST_FILENAME:
            continue
        generated_at = snapshot.get("generated_at")
        if not isinstance(generated_at, str) or not generated_at:
            errors.append(f"{declared_path} has no generated_at; freshness is unknown")
            continue
        age = _age_hours(generated_at, now)
        if age is None:
            errors.append(
                f"{declared_path} has an unparseable generated_at: {generated_at!r}"
            )
        elif age > window:
            errors.append(
                f"{declared_path} was generated {age:.0f}h ago, outside the "
                f"{window:g}h freshness window the consumer treats as fresh"
            )
        elif age < 0:
            errors.append(f"{declared_path} has a future generated_at ({generated_at})")

    return errors


def validate_manifest(path: Path) -> list[str]:
    errors: list[str] = []
    manifest = _load_manifest(path)

    missing = sorted(REQUIRED_TOP_LEVEL - set(manifest))
    if missing:
        errors.append(f"missing top-level fields: {', '.join(missing)}")

    if manifest.get("schema_version") != "proof-package.v1":
        errors.append("schema_version must be proof-package.v1")

    artifacts = manifest.get("artifacts")
    artifact_ids: set[str] = set()
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("artifacts must be a non-empty list")
    else:
        for index, artifact in enumerate(artifacts):
            if not isinstance(artifact, dict):
                errors.append(f"artifacts[{index}] must be an object")
                continue
            missing_artifact = sorted(REQUIRED_ARTIFACT_FIELDS - set(artifact))
            if missing_artifact:
                errors.append(
                    f"artifacts[{index}] missing fields: {', '.join(missing_artifact)}"
                )
            artifact_id = artifact.get("id")
            if isinstance(artifact_id, str):
                if artifact_id in artifact_ids:
                    errors.append(f"duplicate artifact id: {artifact_id}")
                artifact_ids.add(artifact_id)
            artifact_path = artifact.get("path")
            if (
                isinstance(artifact_path, str)
                and not artifact.get("external", False)
                and artifact.get("required", False)
            ):
                if not _resolve_artifact_path(path, artifact_path).exists():
                    errors.append(f"required artifact missing: {artifact_path}")

    claims = manifest.get("claims")
    if not isinstance(claims, list) or not claims:
        errors.append("claims must be a non-empty list")
    else:
        for index, claim in enumerate(claims):
            if not isinstance(claim, dict):
                errors.append(f"claims[{index}] must be an object")
                continue
            missing_claim = sorted(REQUIRED_CLAIM_FIELDS - set(claim))
            if missing_claim:
                errors.append(
                    f"claims[{index}] missing fields: {', '.join(missing_claim)}"
                )
            status = claim.get("status")
            if status not in ALLOWED_STATUSES:
                errors.append(f"claims[{index}] has invalid status: {status}")
            evidence = claim.get("evidence")
            if not isinstance(evidence, list) or not evidence:
                errors.append(f"claims[{index}] evidence must be a non-empty list")
            else:
                for evidence_id in evidence:
                    if evidence_id not in artifact_ids:
                        errors.append(
                            f"claims[{index}] references unknown artifact: {evidence_id}"
                        )

    verification = manifest.get("verification")
    if isinstance(verification, dict):
        overall = verification.get("overall")
        if overall not in ALLOWED_STATUSES:
            errors.append(f"verification.overall has invalid status: {overall}")
        checks = verification.get("checks")
        if not isinstance(checks, list):
            errors.append("verification.checks must be a list")
    elif "verification" in manifest:
        errors.append("verification must be an object")

    errors.extend(validate_truth_currency(manifest, path))

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()

    errors = validate_manifest(args.manifest)
    if errors:
        for error in errors:
            print(f"proof package invalid: {error}")
        return 1
    print(f"proof package valid: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
