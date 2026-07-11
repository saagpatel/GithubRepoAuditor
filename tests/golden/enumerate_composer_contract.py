"""Characterization enumerator for the multi-arg dict-composers in
``operator_trend_closure_forecast_reset_controls``.

The sibling enumerator (``enumerate_recovery_state_contract.py``) pins only the
single-arg ``(status: str) -> str`` classifiers. It is structurally blind to the
multi-argument composers -- the per-target persistence/churn/freshness/recovery
builders, the hotspot selectors, and the summary renderers -- whose dict/list/str
outputs feed the operator decision-quality string contract. This enumerator
captures those composers across a status-spanning corpus into a frozen golden.

Why it exists BEFORE any ``recovery_state(target, *, depth)`` collapse: the per-tier
composer families (rebuild / rererestore / rerererestore) are near-clones, and the
net both pins all 44 composers for the collapse and guards a real correctness fix.
``magnitude`` is per-event evidence strength (non-negative by concept; ``sign``
carries the direction). The rebuild persistence builder floors it at zero on every
decrement::

    magnitude = max(0.0, magnitude - 0.10)   # rebuild

The rererestore builder originally omitted that floor (``magnitude -= 0.10``), so an
over-penalized confirmation event could go NEGATIVE and -- after ``sign`` -- count
against its own side, producing a spurious clearance-leaning ``persistence_score``.
That divergence was invisible to the str->str golden. T3-2 phase 5 fixed it: the
rererestore builder now floors exactly like rebuild, so the SAME structural input
yields the SAME score across the tiers. The "clamp-divergence" scenario (the input
that drives a decrement event's magnitude below zero) now records 0.31 for BOTH
rebuild and rererestore, and ``test_magnitude_floor_unifies_rebuild_and_rererestore_tiers``
pins that convergence -- a regression that re-removed the floor would re-diverge and
fail. Any future change to these families must reproduce THIS golden byte-for-byte;
an intentional behavior change shows up here as a reviewed diff, never a silent one.

2026-07-10: re-pinned under production collaborators after the no-callable-
threading unwind (reset_controls satellite). Composers used to receive every
dependency (side/path classifiers, clamp_round, window constants, ...) as an
injected kwonly Callable/constant, and this enumerator swapped in deterministic
stand-ins for them via kwargs -- a semantics artifact of the injection idiom
itself, since production call sites never actually received those stand-ins.
The composers now resolve those dependencies directly (sibling call within this
module, or import from ``operator_trend_support`` /
``operator_trend_closure_forecast_freshness_controls``), so there is no longer a
kwarg to inject through, and determinism comes from the input corpus below
instead of from fixed-harness substitution. This is a harness-semantics re-pin,
not a production behavior change: the 34 composers whose output never depended
on a stand-in (i.e. never referenced a classifier/path-label dependency that the
old harness swapped) are byte-identical to the prior golden; only the 13 whose
recorded output depended on a stand-in value changed, and each was hand-verified
against the real function before the golden was refrozen.

Regenerate only with an intentional, reviewed behavior change::

    uv run python tests/golden/enumerate_composer_contract.py
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import src.operator_trend_closure_forecast_reset_controls as m

REPO = Path(__file__).resolve().parents[2]
GOLDEN_PATH = REPO / "tests" / "golden" / "composer_contract.golden.json"

# The modes every hotspot selector branches on (harvested from the source + the
# orchestrator call sites). Each is fed to every hotspots composer; whatever it
# returns is pinned.
HOTSPOT_MODES: tuple[str, ...] = (
    "churn",
    "clearance",
    "confirmation",
    "fresh",
    "holding",
    "just-rebuilt",
    "just-rererestored",
    "just-rerererestored",
    "stale",
)


# --------------------------------------------------------------------------- #
# Corpus. Events carry every tier's status keys at once, so one archetype
# meaningfully drives whichever tier composer consumes it. `decrement` events
# push per-event magnitude below zero -- the input that exposes the rebuild
# (floored) vs rererestore (unfloored) divergence.
# --------------------------------------------------------------------------- #
def _event(
    label: str,
    side: str,
    *,
    fresh: str = "fresh",
    stable: str = "stable",
    momentum: str = "sustained-confirmation",
    reset: bool = False,
    base: bool = True,
) -> dict[str, Any]:
    word = side  # after the early return below, side is "confirmation" or "clearance"
    event: dict[str, Any] = {
        "label": label,
        "class_key": "urgent:config",
        "closure_forecast_momentum_status": momentum,
        "closure_forecast_stability_status": stable,
    }
    if side == "none":
        return {"label": label, "class_key": "urgent:config"}
    # Recovery statuses set the event's side and a +0.10 base on every tier. The
    # `*_status` "rebuilt"/"rererestored" tokens add a further +0.15 -- omit them
    # (base=False) to keep buildup low so decrement events cross below zero, which
    # is where the rebuild floor (max(0.0, ..)) and rererestore non-floor diverge.
    if base:
        event["closure_forecast_reset_reentry_rebuild_status"] = (
            f"rebuilt-{word}-reentry"
        )
        event[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status"
        ] = f"rererestored-{word}-rebuild-reentry"
    event["closure_forecast_reset_reentry_refresh_recovery_status"] = (
        f"rebuilding-{word}-reentry"
    )
    event["closure_forecast_reset_reentry_freshness_status"] = fresh
    event[
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_status"
    ] = f"rererestoring-{word}-rebuild-reentry"
    event[
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status"
    ] = fresh
    if reset:
        event["closure_forecast_reset_reentry_reset_status"] = f"{word}-reset"
        event[
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_status"
        ] = f"{word}-reset"
    return event


def _for_target_scenarios() -> list[
    tuple[str, dict[str, Any], list[dict[str, Any]], dict[str, Any]]
]:
    strong = _event("strong-conf", "confirmation", fresh="fresh", stable="stable")
    decrement = _event(
        "decrement-conf",
        "confirmation",
        fresh="mixed-age",
        stable="watch",
        momentum="insufficient-data",
        reset=True,
        base=False,
    )
    clearance = _event("clearance", "clearance", momentum="sustained-clearance")
    reversing = _event(
        "reversing", "confirmation", momentum="reversing", stable="oscillating"
    )
    sparse = _event("sparse-none", "none")

    conf_target = {
        "lane": "urgent",
        "kind": "config",
        "closure_forecast_momentum_status": "sustained-confirmation",
        "closure_forecast_stability_status": "stable",
        "closure_forecast_reset_reentry_freshness_status": "fresh",
        "closure_forecast_reset_reentry_rebuild_status": "rebuilt-confirmation-reentry",
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": (
            "rererestored-confirmation-rebuild-reentry"
        ),
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status": "fresh",
    }
    reversing_target = {**conf_target, "closure_forecast_momentum_status": "reversing"}
    return [
        # The floor-path fixture: confirmation side, one strong event + one decrement
        # event whose magnitude crosses below zero. Both rebuild and the (now-fixed)
        # rererestore floor it at 0, so they agree; the scenario name is historical.
        ("clamp-divergence", conf_target, [strong, decrement], {}),
        ("sustained-confirmation", conf_target, [strong, strong, strong], {}),
        (
            "clearance-hold",
            {**conf_target, "closure_forecast_momentum_status": "sustained-clearance"},
            [clearance, clearance],
            {},
        ),
        (
            "reversing",
            reversing_target,
            [reversing, strong],
            {"current_transition_reversed": True},
        ),
        ("single-event", conf_target, [strong], {}),
        ("empty", conf_target, [], {}),
        ("sparse", conf_target, [sparse, strong, decrement], {}),
    ]


def _hotspot_targets() -> list[dict[str, Any]]:
    # Targets carrying the per-tier score/status/age keys the selectors rank on.
    # One generic bag of keys spanning the tiers; selectors read their own.
    def _target(
        title: str,
        lane: str,
        kind: str,
        score: float,
        churn: float,
        age: int,
        status: str,
    ) -> dict[str, Any]:
        keys = (
            "closure_forecast_reset_reentry_rebuild",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore",
            "closure_forecast_reset_reentry",
            "closure_forecast_reset_refresh",
        )
        target: dict[str, Any] = {"title": title, "lane": lane, "kind": kind}
        for tier_index, key in enumerate(keys):
            # Distinct value per tier (F4): a selector that reads a NEIGHBOUR tier's
            # key -- the copy-paste bug the collapse risks -- emits a different score
            # into its hotspot output and is caught by the golden diff, rather than
            # producing identical output to a correct read.
            tier_score = round(score + tier_index * 0.11, 2)
            tier_churn = round(min(churn + tier_index * 0.07, 0.95), 2)
            tier_age = age + tier_index
            target[f"{key}_persistence_score"] = tier_score
            target[f"{key}_persistence_status"] = status
            target[f"{key}_churn_score"] = tier_churn
            target[f"{key}_churn_status"] = "churn" if tier_churn >= 0.45 else "none"
            target[f"{key}_age_runs"] = tier_age
            target[f"{key}_freshness_status"] = "stale" if tier_age >= 3 else "fresh"
        return target

    return [
        _target(
            "RepoA", "urgent", "config", 0.34, 0.0, 3, "holding-confirmation-rebuild"
        ),
        _target("RepoB", "blocked", "setup", -0.28, 0.5, 2, "just-rebuilt"),
        _target("RepoC", "ready", "docs", 0.0, 0.0, 1, "none"),
    ]


def _summary_inputs() -> tuple[
    dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]
]:
    # Reuse the rich hotspot targets so every summary's hotspot inputs carry the
    # per-tier score/status/age keys (F5): a summary that branches on a hotspot key's
    # presence reaches its real branch instead of a degenerate fallback whose output
    # the golden would otherwise pin as if correct.
    rich = _hotspot_targets()
    primary = {**rich[0], "label": m.target_class_key(rich[0])}
    list_a = [{**rich[0], "label": m.target_class_key(rich[0])}]
    list_b = [{**rich[1], "label": m.target_class_key(rich[1])}]
    return primary, list_a, list_b


# --------------------------------------------------------------------------- #
# Discovery + drive.
# --------------------------------------------------------------------------- #
def _public_composers() -> dict[str, object]:
    found: dict[str, object] = {}
    for name, fn in inspect.getmembers(m, inspect.isfunction):
        if (
            fn.__module__ != m.__name__
            or name.startswith("_")
            or name.startswith("apply_")
        ):
            continue
        params = list(inspect.signature(fn).parameters.values())
        positional = [
            p for p in params if p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
        ]
        # Skip the single-arg str->str classifiers (already covered by the sibling golden).
        if (
            len(positional) == 1
            and _is_str(positional[0].annotation)
            and _is_str(inspect.signature(fn).return_annotation)
        ):
            continue
        found[name] = fn
    return found


def _is_str(annotation: object) -> bool:
    return annotation is str or annotation == "str"


def _role(name: str) -> str:
    if name.endswith("_for_target"):
        return "for_target"
    if name.endswith("_hotspots"):
        return "hotspots"
    if name.endswith("_summary"):
        return "summary"
    if name.endswith("_path_label"):
        return "path_label"
    return "other"


def _drive(name: str, fn: object) -> dict[str, Any]:
    role = _role(name)
    positional = [
        p
        for p in inspect.signature(fn).parameters.values()
        if p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    ]
    results: dict[str, Any] = {}

    if role == "for_target":
        for label, target, events, history_meta in _for_target_scenarios():
            args = (
                (target, events, history_meta)
                if len(positional) == 3
                else (target, events)
            )
            results[label] = fn(*args)
    elif role == "hotspots":
        targets = _hotspot_targets()
        for mode in HOTSPOT_MODES:
            results[f"mode={mode}"] = fn(targets, mode=mode)
    elif role == "summary":
        primary, list_a, list_b = _summary_inputs()
        args = (primary, list_a, list_b) if len(positional) == 3 else (primary, list_a)
        results["summary"] = fn(*args)
    elif role == "path_label":
        for label, event in {
            "confirmation": _event("c", "confirmation"),
            "clearance": _event("k", "clearance"),
            "none": _event("n", "none"),
        }.items():
            results[label] = fn(event)
    else:  # pragma: no cover - guards an unclassified composer shape
        raise KeyError(f"composer enumerator: unclassified composer {name!r}")
    return results


def build_contract() -> dict[str, Any]:
    """Drive every public composer over the corpus and return the captured contract.

    Shared by ``main`` (which freezes it to the golden JSON) and the companion test
    (which re-runs it against the current source and diffs) so generation and check
    use one identical harness.
    """
    composers = _public_composers()
    return {name: _drive(name, composers[name]) for name in sorted(composers)}


def main() -> None:
    golden = build_contract()
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_PATH.write_text(json.dumps(golden, indent=2, sort_keys=True) + "\n")

    roles: dict[str, int] = {}
    for name in golden:
        roles[_role(name)] = roles.get(_role(name), 0) + 1
    print(f"composers captured: {len(golden)}")
    print(f"by role: {roles}")
    print(f"golden -> {GOLDEN_PATH.relative_to(REPO)}")


if __name__ == "__main__":
    main()
