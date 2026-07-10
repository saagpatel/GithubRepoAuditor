"""Characterization (golden) test for the multi-arg dict-composers in
``operator_trend_closure_forecast_reset_controls``.

The sibling test (``test_recovery_state_golden_contract.py``) pins only the
single-arg ``str -> str`` classifiers. This pins the >1-arg composers -- the
per-target persistence/churn/freshness/recovery builders, the hotspot selectors,
and the summary renderers -- whose dict/list/str outputs feed the operator
decision-quality string contract. It is the safety net for the eventual
``recovery_state(target, *, depth)`` collapse of the rebuild / rererestore /
rerererestore families: any change to a composer's behavior surfaces here as a
byte-level diff before it can reach a consumer.

The golden and this test share one harness (``enumerate_composer_contract``): the
enumerator freezes the contract to JSON, this test re-runs the same drive against
the current source and diffs. Regenerate only with a reviewed behavior change:
    uv run python tests/golden/enumerate_composer_contract.py
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

# ``tests/golden`` is not an importable package, so load the enumerator (which
# holds the shared corpus + drive harness) directly from its file path.
_ENUMERATOR_PATH = Path(__file__).parent / "golden" / "enumerate_composer_contract.py"
_spec = importlib.util.spec_from_file_location(
    "composer_contract_enumerator", _ENUMERATOR_PATH
)
assert _spec is not None and _spec.loader is not None
_enum = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_enum)

assert _enum.GOLDEN_PATH.exists(), (
    f"composer golden missing at {_enum.GOLDEN_PATH}; regenerate with "
    "`uv run python tests/golden/enumerate_composer_contract.py`"
)
GOLDEN: dict[str, Any] = json.loads(_enum.GOLDEN_PATH.read_text())
# Re-run the live drive against the current source once; parametrized tests diff it.
LIVE: dict[str, Any] = _enum.build_contract()

# The persistence builders whose only logic delta is the per-event magnitude floor:
# rebuild clamps (``max(0.0, magnitude - X)``); rererestore does not (``magnitude -= X``).
_REBUILD_PERSISTENCE = "closure_forecast_reset_reentry_rebuild_persistence_for_target"
_RERERESTORE_PERSISTENCE = "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_for_target"
_REBUILD_SCORE_KEY = "closure_forecast_reset_reentry_rebuild_persistence_score"
_RERERESTORE_SCORE_KEY = "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score"
# The rerererestore tier wraps + delegates to rererestore (so it also does not floor).
_RERERESTORE_WRAP_PERSISTENCE = "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_for_target"
_RERERESTORE_WRAP_SCORE_KEY = "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score"


def _nontrivial_leaves(obj: Any) -> int:
    if isinstance(obj, dict):
        return sum(_nontrivial_leaves(value) for value in obj.values())
    if isinstance(obj, list):
        return sum(_nontrivial_leaves(value) for value in obj)
    return 0 if obj in ("none", "", 0, 0.0, None, False) else 1


def test_golden_covers_every_public_composer() -> None:
    assert set(GOLDEN) == set(_enum._public_composers())
    # The live drive and the frozen golden must cover exactly the same composers, so
    # an extra/missing key cannot slip past the per-composer parametrize (F6).
    assert set(LIVE) == set(GOLDEN)
    # Sanity floor: the rebuild/rererestore/rerererestore tiers alone are dozens.
    assert len(GOLDEN) >= 40, len(GOLDEN)


def test_golden_is_non_degenerate() -> None:
    # Guard against a golden that records only "none"/0 (which would pass any diff
    # while pinning nothing). The corpus must exercise real composer branches.
    count = _nontrivial_leaves(GOLDEN)
    assert count >= 300, count


@pytest.mark.parametrize("name", sorted(LIVE))
def test_composer_reproduces_golden(name: str) -> None:
    assert LIVE[name] == GOLDEN[name]


def test_magnitude_floor_unifies_rebuild_and_rererestore_tiers() -> None:
    # T3-2 phase 5 fix: the rererestore persistence builder now floors per-event
    # magnitude at 0 (max(0.0, ..)) exactly like rebuild -- previously it omitted the
    # floor (magnitude -= X), letting an over-penalized confirmation event go negative
    # and count against its own side. With the floor, the SAME structural input yields
    # the SAME score across the tiers. This pins the fix: a regression that re-removed
    # the floor would re-diverge here.
    #
    # This scenario is driven directly against the production composers (not read from
    # GOLDEN/the shared "clamp-divergence" corpus fixture) and gives its "strong" event
    # a `key`/`generated_at` that matches the target's `queue_identity`, so
    # `ordered_reset_reentry_events_for_target` takes its `current_index == 0` shortcut
    # and returns the two events unchanged. This sidesteps a known pre-existing gap:
    # `current_closure_forecast_event_for_target` (src/operator_trend_support.py,
    # ~line 210) synthesizes a "current" event from the target dict whose key coverage
    # stops at the "rerestore" tier and never reaches "rererestore", so when the shared
    # corpus fixture (which has no matching key/generated_at) falls through to that
    # synthesizer, the rebuild and rererestore tiers diverge for a reason unrelated to
    # the floor. Tracked as a follow-up; not fixed here (see operator report).
    target = {
        "lane": "urgent",
        "kind": "config",
        "item_id": "T1",
        "closure_forecast_momentum_status": "sustained-confirmation",
        "closure_forecast_stability_status": "stable",
    }
    strong = {
        "class_key": "urgent:config",
        "key": "T1",
        "generated_at": "",
        "closure_forecast_momentum_status": "sustained-confirmation",
        "closure_forecast_stability_status": "stable",
        "closure_forecast_reset_reentry_rebuild_status": "rebuilt-confirmation-reentry",
        "closure_forecast_reset_reentry_freshness_status": "fresh",
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": (
            "rererestored-confirmation-rebuild-reentry"
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status": "fresh",
    }
    decrement = {
        "class_key": "urgent:config",
        "closure_forecast_momentum_status": "insufficient-data",
        "closure_forecast_stability_status": "watch",
        "closure_forecast_reset_reentry_refresh_recovery_status": "rebuilding-confirmation-reentry",
        "closure_forecast_reset_reentry_freshness_status": "mixed-age",
        "closure_forecast_reset_reentry_reset_status": "confirmation-reset",
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_status": (
            "rererestoring-confirmation-rebuild-reentry"
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status": "mixed-age",
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_status": "confirmation-reset",
    }
    events = [strong, decrement]

    rebuild = _enum.m.closure_forecast_reset_reentry_rebuild_persistence_for_target(
        target, events, {}
    )
    rererestore = _enum.m.closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_for_target(
        target, events, {}
    )
    rebuild_score = rebuild[_REBUILD_SCORE_KEY]
    rererestore_score = rererestore[_RERERESTORE_SCORE_KEY]
    assert rebuild_score == rererestore_score, (rebuild_score, rererestore_score)
    assert rebuild_score > 0.0, rebuild_score

    # The rerererestore tier wraps + delegates to the now-fixed rererestore builder,
    # so this confirmation-side scenario no longer yields a spurious NEGATIVE score
    # (the bug symptom). It need not equal rebuild -- the wrapper feeds translated
    # inputs -- but it must reflect the floor (be non-negative here).
    rerererestore = GOLDEN[_RERERESTORE_WRAP_PERSISTENCE]["clamp-divergence"]
    rerererestore_score = rerererestore[_RERERESTORE_WRAP_SCORE_KEY]
    assert rerererestore_score >= 0.0, rerererestore_score
