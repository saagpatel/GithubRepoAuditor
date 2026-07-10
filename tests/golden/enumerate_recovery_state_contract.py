"""Golden-contract enumerator for the operator_resolution_trend restore-tier fractal.

Captures the EXACT current output of every pure ``(status: str) -> str`` classifier
across the full restore-tier status-string vocabulary (depths 1-4), into a golden
JSON file. After the ``recovery_state(target, *, depth)`` collapse, re-run this and
diff the JSON: byte-identical output proves the collapse preserved the contract.

Safety: only imports pure-computation modules (verified free of import-time DB/IO
side effects) and calls pure string classifiers. Never opens a live database.

Run from the repo root:  ``uv run python tests/golden/enumerate_recovery_state_contract.py``
"""

from __future__ import annotations

import ast
import inspect
import json
import re
from pathlib import Path
from types import ModuleType

import src.operator_resolution_trend as m_resolution
import src.operator_snapshot_packaging as m_pkg
import src.operator_trend_closure_forecast_reacquisition_controls as m_reacq
import src.operator_trend_closure_forecast_reset_controls as m_reset
import src.operator_trend_support as m_support  # scanned since 2026-07-10: classifiers moved here by the callable-threading unwind

REPO = Path(__file__).resolve().parents[2]
GOLDEN_PATH = REPO / "tests" / "golden" / "recovery_state_contract.golden.json"

# The restore-tier axis: depth == number of "re" prefixes on "store".
PREFIXES = ("holding", "pending", "sustained", "recovering")
SIDES = ("clearance", "confirmation")
TIERS = ("restore", "rerestore", "rererestore", "rerererestore")
TIERS_DONE = ("restored", "rerestored", "rererestored", "rerererestored")


def _family_persistence() -> list[str]:
    out: list[str] = []
    for prefix in PREFIXES:
        for side in SIDES:
            for tier in TIERS:
                base = f"{prefix}-{side}-rebuild-reentry-{tier}"
                out.append(f"{base}-reset" if prefix == "recovering" else base)
    return out


def _family_done() -> list[str]:
    return [f"{tier}-{side}-rebuild-reentry" for tier in TIERS_DONE for side in SIDES]


def _family_just() -> list[str]:
    return [f"just-{tier}" for tier in TIERS_DONE]


# Boundary inputs every classifier must still tolerate.
BOUNDARY = (
    "none",
    "",
    "hold",
    "reentered-clearance-rebuild",
    "reentered-confirmation-rebuild",
    "restoring-confirmation-rebuild-reentry",
    "restoring-clearance-rebuild-reentry",
)

# Status-token shape: a lowercase, hyphen-joined single token (no spaces). This is
# exactly the form of every dict key / branch literal the classifiers discriminate
# on (e.g. "holding-clearance-rebuild-reentry-rererestore", "insufficient-data",
# "just-restored", "none"). Harvesting these from source guarantees every branch of
# every dict-lookup table is exercised — a golden of all-"none" would be worthless.
_STATUS_TOKEN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


def _harvest_status_literals(modules: tuple[ModuleType, ...]) -> set[str]:
    harvested: set[str] = set()
    for module in modules:
        source = Path(inspect.getfile(module)).read_text()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                value = node.value
                if _STATUS_TOKEN.match(value) and len(value) <= 80:
                    harvested.add(value)
    return harvested


_MODULES: tuple[ModuleType, ...] = (m_resolution, m_reset, m_reacq, m_pkg, m_support)

VOCAB: tuple[str, ...] = tuple(
    sorted(
        set(_family_persistence())
        | set(_family_done())
        | set(_family_just())
        | set(BOUNDARY)
        | _harvest_status_literals(_MODULES)
    )
)


def _is_str_annotation(annotation: object) -> bool:
    # ``from __future__ import annotations`` makes annotations strings, not types.
    return annotation is str or annotation == "str"


def _pure_status_classifiers(module: ModuleType) -> dict[str, object]:
    """Single-parameter ``str -> str`` functions defined in *module* (not imported)."""
    found: dict[str, object] = {}
    for name, fn in inspect.getmembers(module, inspect.isfunction):
        if fn.__module__ != module.__name__:
            continue
        sig = inspect.signature(fn)
        params = list(sig.parameters.values())
        if len(params) != 1:
            continue
        (only,) = params
        if _is_str_annotation(only.annotation) and _is_str_annotation(sig.return_annotation):
            found[name] = fn
    return found


def main() -> None:
    golden: dict[str, dict[str, str]] = {}
    for module in _MODULES:
        for name, fn in sorted(_pure_status_classifiers(module).items()):
            qualname = f"{module.__name__}.{name}"
            results: dict[str, str] = {}
            for status in VOCAB:
                try:
                    results[status] = fn(status)
                except Exception as exc:  # the raise itself is part of the contract
                    results[status] = f"<<RAISED {type(exc).__name__}: {exc}>>"
            golden[qualname] = results

    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_PATH.write_text(json.dumps(golden, indent=2, sort_keys=True) + "\n")

    print(f"vocab inputs: {len(VOCAB)}")
    print(f"classifiers captured: {len(golden)}")
    for qualname in sorted(golden):
        print(f"  {qualname}")
    print(f"golden -> {GOLDEN_PATH.relative_to(REPO)}")


if __name__ == "__main__":
    main()
