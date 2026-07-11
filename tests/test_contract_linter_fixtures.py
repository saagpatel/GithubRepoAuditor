from __future__ import annotations

import json
from pathlib import Path


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "contract_linter"


def test_contract_linter_fixtures_have_stable_expected_outcomes() -> None:
    fixtures = {
        path.stem: json.loads(path.read_text())
        for path in sorted(FIXTURE_ROOT.glob("*.json"))
    }
    assert set(fixtures) == {
        "canonical_queue_truncated",
        "historical_evidence_artifact",
        "known_good_0_8",
        "legacy_0_7_without_envelope",
        "mixed_stale_and_unresolved",
        "notion_carried_fresh",
        "notion_carried_origin_unknown",
        "notion_carried_stale",
        "notion_live",
        "stale_producer_catalog_miss",
    }
    for fixture_id, payload in fixtures.items():
        assert payload["fixture_id"] == fixture_id
        assert payload["expected"]
        assert all(key.startswith("CL-") for key in payload["expected"])


def test_mixed_fixture_does_not_conflate_unknown_with_stale() -> None:
    payload = json.loads(
        (FIXTURE_ROOT / "mixed_stale_and_unresolved.json").read_text()
    )
    assert payload["expected"]["CL-DECL-001:stale-one"] == "fail"
    assert payload["expected"]["CL-DECL-001:unresolved-one"] == "unknown"
