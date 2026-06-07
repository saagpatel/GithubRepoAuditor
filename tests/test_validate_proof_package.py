import json
from pathlib import Path

from scripts.validate_proof_package import validate_manifest


def test_valid_proof_package_fixture() -> None:
    manifest = Path("tests/fixtures/proof-packages/valid/proof-package.json")

    assert validate_manifest(manifest) == []


def test_missing_required_artifact_is_reported(tmp_path: Path) -> None:
    manifest = {
        "schema_version": "proof-package.v1",
        "package_id": "missing-artifact",
        "subject": {"repo": "Example", "lane": "demo", "claim": "Demo works"},
        "producer": {"repo": "Example", "mode": "demo", "commands": []},
        "source_state": {"generated_at": "2026-06-07T00:00:00Z"},
        "claims": [
            {
                "id": "claim-1",
                "statement": "Required evidence exists",
                "status": "passed",
                "evidence": ["missing-file"],
            }
        ],
        "verification": {
            "overall": "passed",
            "checks": [],
            "missing_receipts": [],
            "known_gaps": [],
        },
        "safety": {"redaction": "none", "secrets_checked": True, "live_write_performed": False},
        "artifacts": [
            {
                "id": "missing-file",
                "kind": "receipt",
                "path": "receipts/missing.json",
                "description": "Missing required receipt",
                "required": True,
            }
        ],
    }
    path = tmp_path / "proof-package.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    assert validate_manifest(path) == ["required artifact missing: receipts/missing.json"]
