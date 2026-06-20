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


def test_clamp_divergence_between_tiers_is_pinned() -> None:
    # The whole reason this net exists: the rebuild and rererestore persistence
    # builders are near-clones, but the rebuild per-event magnitude floor makes the
    # SAME structural input ("clamp-divergence" scenario) yield a different score.
    # A naive collapse that translated one tier into the other would erase this and
    # this assertion would fail -- which is the point.
    rebuild = GOLDEN[_REBUILD_PERSISTENCE]["clamp-divergence"]
    rererestore = GOLDEN[_RERERESTORE_PERSISTENCE]["clamp-divergence"]
    rebuild_score = rebuild[_REBUILD_SCORE_KEY]
    rererestore_score = rererestore[_RERERESTORE_SCORE_KEY]
    assert rebuild_score != rererestore_score, (rebuild_score, rererestore_score)
    # Rebuild floors the negative decrement term at 0, so it stays the higher score.
    assert rebuild_score > rererestore_score, (rebuild_score, rererestore_score)

    # The rerererestore tier is a thin wrapper that translates keys and delegates to
    # the rererestore builder, so it also does NOT floor the magnitude. Pin it as a
    # named three-way invariant: it diverges from the flooring rebuild tier (F7). A
    # collapse that accidentally gave it rebuild's floor would break this.
    rerererestore = GOLDEN[_RERERESTORE_WRAP_PERSISTENCE]["clamp-divergence"]
    rerererestore_score = rerererestore[_RERERESTORE_WRAP_SCORE_KEY]
    assert rerererestore_score != rebuild_score, (rerererestore_score, rebuild_score)
