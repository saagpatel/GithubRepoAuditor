"""Characterization (golden) test for ``_build_resolution_trend``'s assembled
payload — the top-level operator resolution-trend dict (320+ keys) built by the
god-function's 1,676-line ``payload.update({...})``.

This pins the EXACT current assembled output across a representative input corpus
to a frozen golden. It is the safety net for the god-function decomposition:
extracting the payload-assembly seam into its own module, then collapsing the
per-tier blocks onto a parametrized base, must reproduce this byte-for-byte. Any
dropped key, mis-wired source, or per-tier drift shows up here as a diff before it
can reach a consumer (``operator_control_center`` / ``operator_decision_quality``).

The corpus + projection live in the enumerator so there is one source of truth;
this test re-runs it against the frozen golden. Regenerate the golden only with an
intentional, reviewed behavior change::

    uv run python tests/golden/enumerate_resolution_trend_contract.py
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

_GOLDEN_DIR = Path(__file__).parent / "golden"
GOLDEN_PATH = _GOLDEN_DIR / "resolution_trend_contract.golden.json"
_ENUMERATOR_PATH = _GOLDEN_DIR / "enumerate_resolution_trend_contract.py"


def _load_enumerator() -> Any:
    # Load by path (tests/golden is not a package). Module name is NOT
    # "__main__", so the enumerator's main()/golden-write never fires here.
    spec = importlib.util.spec_from_file_location(
        "_enumerate_resolution_trend_contract", _ENUMERATOR_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_ENUM = _load_enumerator()
GOLDEN: dict[str, dict[str, Any]] = json.loads(GOLDEN_PATH.read_text())

_DEFAULTISH = ("", "none", 0, 0.0, [], {}, None, False)


def test_golden_is_non_degenerate() -> None:
    # Guard against a corpus that captures only empty/default structure.
    assert GOLDEN, "golden contract is empty"
    assert {"empty", "single_blocked_stale"} <= set(GOLDEN)
    assert not GOLDEN["empty"]["primary_target"], (
        "empty case must have falsy primary_target"
    )
    assert GOLDEN["single_blocked_stale"]["primary_target"], (
        "stale case must select a target"
    )

    populated = GOLDEN["single_blocked_stale"]
    assert len(populated) >= 380, f"assembled payload too small ({len(populated)} keys)"
    nondefault = sum(1 for value in populated.values() if value not in _DEFAULTISH)
    assert nondefault >= 100, (
        f"golden exercises too few populated values ({nondefault})"
    )

    # The empty and populated cases must genuinely diverge (real branches fired).
    differing = sum(
        1 for key in populated if populated.get(key) != GOLDEN["empty"].get(key)
    )
    assert differing >= 50, f"empty vs populated barely diverge ({differing} keys)"


def test_build_resolution_trend_reproduces_golden() -> None:
    actual = _ENUM.build_contract()
    assert set(actual) == set(GOLDEN), "corpus case set drifted from the golden"
    for label in sorted(GOLDEN):
        expected = GOLDEN[label]
        got = actual[label]
        assert set(got) == set(expected), f"payload key set drifted in case {label!r}"
        # Per-key compare for a readable first divergence on failure.
        for key in expected:
            assert got[key] == expected[key], (
                f"payload value drift: case {label!r}, key {key!r}"
            )
