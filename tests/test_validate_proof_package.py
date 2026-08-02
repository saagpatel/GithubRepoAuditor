import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.validate_proof_package import (
    CONSUMER_FRESH_WINDOW_HOURS,
    PRODUCER_TRUTH_SCHEMA_VERSION,
    validate_manifest,
    validate_truth_currency,
)


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
        "safety": {
            "redaction": "none",
            "secrets_checked": True,
            "live_write_performed": False,
        },
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

    assert validate_manifest(path) == [
        "required artifact missing: receipts/missing.json"
    ]


def _truth_manifest(
    tmp_path: Path,
    *,
    declared_schema: str | None,
    truth_schema: str,
    age_hours: float,
) -> Path:
    """Write a manifest publishing one portfolio-truth artifact."""
    generated_at = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    (tmp_path / "portfolio-truth-latest.json").write_text(
        json.dumps(
            {
                "schema_version": truth_schema,
                "generated_at": generated_at.isoformat(),
                "projects": [],
            }
        ),
        encoding="utf-8",
    )
    source_state: dict[str, object] = {"source_data_mode": "fixture"}
    if declared_schema is not None:
        source_state["source_truth_schema"] = declared_schema
    manifest = {
        "schema_version": "proof-package.v1",
        "package_id": "truth-currency",
        "subject": {"repo": "Example", "lane": "demo", "claim": "Demo works"},
        "producer": {"repo": "Example", "mode": "fixture", "commands": []},
        "source_state": source_state,
        "claims": [
            {
                "id": "claim-1",
                "statement": "Truth is published",
                "status": "passed",
                "evidence": ["demo-truth"],
            }
        ],
        "verification": {"overall": "passed", "checks": []},
        "safety": {"redaction": "none", "secrets_checked": True},
        "artifacts": [
            {
                "id": "demo-truth",
                "kind": "json",
                "path": "portfolio-truth-latest.json",
                "description": "Published portfolio truth",
                "required": True,
            }
        ],
    }
    path = tmp_path / "proof-package.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_current_fresh_truth_passes(tmp_path: Path) -> None:
    path = _truth_manifest(
        tmp_path,
        declared_schema=PRODUCER_TRUTH_SCHEMA_VERSION,
        truth_schema=PRODUCER_TRUTH_SCHEMA_VERSION,
        age_hours=6,
    )

    assert validate_manifest(path) == []


def test_legacy_truth_schema_is_rejected(tmp_path: Path) -> None:
    path = _truth_manifest(
        tmp_path, declared_schema="0.7.0", truth_schema="0.7.0", age_hours=6
    )

    errors = validate_manifest(path)

    assert any("source_state.source_truth_schema is '0.7.0'" in e for e in errors)
    assert any("declares schema_version '0.7.0'" in e for e in errors)


def test_truth_outside_the_consumer_fresh_window_is_rejected(tmp_path: Path) -> None:
    path = _truth_manifest(
        tmp_path,
        declared_schema=PRODUCER_TRUTH_SCHEMA_VERSION,
        truth_schema=PRODUCER_TRUTH_SCHEMA_VERSION,
        age_hours=CONSUMER_FRESH_WINDOW_HOURS + 1,
    )

    errors = validate_manifest(path)

    assert len(errors) == 1
    assert "outside the 48h freshness window" in errors[0]


def test_future_dated_truth_is_rejected(tmp_path: Path) -> None:
    """A timestamp ahead of now is a clock or generation bug, not freshness."""
    path = _truth_manifest(
        tmp_path,
        declared_schema=PRODUCER_TRUTH_SCHEMA_VERSION,
        truth_schema=PRODUCER_TRUTH_SCHEMA_VERSION,
        age_hours=-24,
    )

    errors = validate_manifest(path)

    assert len(errors) == 1
    assert "future generated_at" in errors[0]


def test_missing_declared_truth_schema_is_rejected(tmp_path: Path) -> None:
    path = _truth_manifest(
        tmp_path,
        declared_schema=None,
        truth_schema=PRODUCER_TRUTH_SCHEMA_VERSION,
        age_hours=6,
    )

    errors = validate_manifest(path)

    assert errors == [
        "source_state.source_truth_schema is None; the producer currently "
        f"emits {PRODUCER_TRUTH_SCHEMA_VERSION!r}"
    ]


def test_history_snapshots_are_schema_checked_but_not_freshness_checked(
    tmp_path: Path,
) -> None:
    """Trend snapshots are old on purpose; only the published latest must be fresh."""
    old = datetime.now(timezone.utc) - timedelta(days=60)
    history = tmp_path / "portfolio-truth-history-01.json"
    history.write_text(
        json.dumps(
            {
                "schema_version": PRODUCER_TRUTH_SCHEMA_VERSION,
                "generated_at": old.isoformat(),
            }
        ),
        encoding="utf-8",
    )
    path = _truth_manifest(
        tmp_path,
        declared_schema=PRODUCER_TRUTH_SCHEMA_VERSION,
        truth_schema=PRODUCER_TRUTH_SCHEMA_VERSION,
        age_hours=6,
    )
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["artifacts"].append(
        {
            "id": "demo-history",
            "kind": "json",
            "path": "portfolio-truth-history-01.json",
            "description": "Trend snapshot",
            "required": True,
        }
    )
    path.write_text(json.dumps(manifest), encoding="utf-8")

    assert validate_manifest(path) == []

    history.write_text(
        json.dumps({"schema_version": "0.7.0", "generated_at": old.isoformat()}),
        encoding="utf-8",
    )

    assert validate_manifest(path) == [
        "portfolio-truth-history-01.json declares schema_version '0.7.0'; "
        f"the producer currently emits {PRODUCER_TRUTH_SCHEMA_VERSION!r}"
    ]


def test_manifest_without_a_truth_artifact_is_unaffected(tmp_path: Path) -> None:
    """The gate must stay inert for proof packages that publish no truth."""
    manifest = {"source_state": {}, "artifacts": [{"path": "SUMMARY.md"}]}

    assert validate_truth_currency(manifest, tmp_path / "proof-package.json") == []
