#!/usr/bin/env python3
"""Validate a proof-package.v1 manifest.

This is deliberately lightweight. It verifies structure and local file
references so proof packages stay easy to inspect without becoming a platform.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ALLOWED_STATUSES = {"passed", "failed", "partial", "stale"}
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
                candidate = Path(artifact_path)
                if not candidate.is_absolute():
                    candidate = path.parent / candidate
                if not candidate.exists():
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
                errors.append(f"claims[{index}] missing fields: {', '.join(missing_claim)}")
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
