"""Characterization enumerator for the multi-arg dict-composers in
``operator_trend_closure_forecast_reset_controls``.

The sibling enumerator (``enumerate_recovery_state_contract.py``) pins only the
single-arg ``(status: str) -> str`` classifiers. It is structurally blind to the
multi-argument composers -- the per-target persistence/churn/freshness/recovery
builders, the hotspot selectors, and the summary renderers -- whose dict/list/str
outputs feed the operator decision-quality string contract. This enumerator
captures those composers across a status-spanning corpus into a frozen golden.

Why it must exist BEFORE any ``recovery_state(target, *, depth)`` collapse: the
per-tier composer families (rebuild / rererestore / rerererestore) are near-clones
with a real, OBSERVABLE logic delta. Concretely, the rebuild persistence builder
floors per-event magnitude at zero::

    magnitude = max(0.0, magnitude - 0.10)   # rebuild

while the rererestore builder does not::

    magnitude -= 0.10                        # rererestore

That unclamped negative survives the symmetric final ``clamp_round(.., -0.95,
0.95)`` and reaches ``persistence_score`` -- so the SAME structural input yields a
different score per tier (the pinned "clamp-divergence" scenario records 0.31 for
rebuild vs 0.24 for rererestore). The str->str golden cannot
see this. Any collapse of these families must reproduce THIS golden byte-for-byte;
an intentional unification shows up here as a reviewed diff, never a silent one.

Fixed-harness validity: the injected callables below are deterministic stand-ins,
not the production wiring (which threads ~15 helpers per composer). The golden's
validity does NOT depend on production-identical callables -- it pins composer
behavior under a FIXED harness, and the collapse must reproduce it under the SAME
harness. The harness only has to be (a) held constant between generation and check
(it is -- one enumerator) and (b) rich enough to exercise the real branches (the
companion test guards a non-degenerate branch count and the clamp divergence).

Regenerate only with an intentional, reviewed behavior change::

    uv run python tests/golden/enumerate_composer_contract.py
"""

from __future__ import annotations

import functools
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
# Fixed faithful callables (deterministic stand-ins for the injected helpers).
# --------------------------------------------------------------------------- #
def _clamp_round(value: float, lower: float, upper: float) -> float:
    return round(max(lower, min(upper, value)), 2)


def _side_from_event(event: dict[str, Any]) -> str:
    # Mirrors the production discriminator shape: confirmation wins over clearance,
    # scanning the event's status-bearing values in insertion order.
    for value in event.values():
        if isinstance(value, str):
            if "confirmation" in value:
                return "confirmation"
            if "clearance" in value:
                return "clearance"
    return "none"


def _side_from_status(status: str) -> str:
    if "confirmation" in status:
        return "confirmation"
    if "clearance" in status:
        return "clearance"
    return "none"


def _path_label(event: dict[str, Any]) -> str:
    for value in event.values():
        if isinstance(value, str) and "-" in value:
            return value
    return "hold"


def _direction_majority(directions: list[str]) -> str:
    confirmation = directions.count("supporting-confirmation")
    clearance = directions.count("supporting-clearance")
    if confirmation > clearance:
        return "supporting-confirmation"
    if clearance > confirmation:
        return "supporting-clearance"
    return "neutral"


def _direction_reversing(current_direction: str, earlier_majority: str) -> bool:
    if current_direction == "neutral" or earlier_majority == "neutral":
        return False
    return current_direction != earlier_majority


def _flip_count(directions: list[str]) -> int:
    return sum(
        1
        for previous, current in zip(directions, directions[1:])
        if previous != current
    )


def _normalization_noise(target: dict[str, Any], history_meta: dict[str, Any]) -> bool:
    return bool(
        target.get("local_noise") or history_meta.get("current_transition_reversed")
    )


def _class_key(item: dict[str, Any]) -> str:
    return f"{item.get('lane', '')}:{item.get('kind', '') or 'unknown'}"


def _label(item: dict[str, Any]) -> str:
    return item.get("title", "") or item.get("kind", "") or "target"


def _ordered_events(
    target: dict[str, Any], events: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    key = _class_key(target)
    return [event for event in events if event.get("class_key") == key]


def _normalized_direction(direction: str, value: float) -> str:
    return direction


def _freshness_status(weighted_evidence: float, recent_share: float) -> str:
    if weighted_evidence <= 0.0:
        return "insufficient-data"
    if recent_share >= 0.5:
        return "fresh"
    if recent_share >= 0.25:
        return "mixed-age"
    return "stale"


def _freshness_reason(
    freshness_status: str,
    weighted_evidence: float,
    recent_share: float,
    decayed_confirmation: float,
    decayed_clearance: float,
) -> str:
    return f"{freshness_status}:{round(weighted_evidence, 2)}:{round(recent_share, 2)}"


def _signal_mix(
    weighted_evidence: float,
    weighted_confirmation: float,
    weighted_clearance: float,
    recent_share: float,
) -> str:
    if weighted_confirmation > weighted_clearance:
        return "confirmation-leaning"
    if weighted_clearance > weighted_confirmation:
        return "clearance-leaning"
    return "balanced"


def _has_evidence(event: dict[str, Any]) -> bool:
    return _side_from_event(event) != "none"


def _is_confirmation_like(event: dict[str, Any]) -> bool:
    return _side_from_event(event) == "confirmation"


def _is_clearance_like(event: dict[str, Any]) -> bool:
    return _side_from_event(event) == "clearance"


def _signal_label(event: dict[str, Any]) -> str:
    return _side_from_event(event)


# --------------------------------------------------------------------------- #
# Kwarg registry: resolve each injected callable/constant by parameter name.
# Real module functions (str classifiers; the rererestore composers injected into
# the rerererestore wrappers) are bound recursively for faithfulness.
# --------------------------------------------------------------------------- #
def _resolve_kwargs(
    fn: object, *, skip: frozenset[str] = frozenset()
) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    for name, param in inspect.signature(fn).parameters.items():
        if param.kind is not inspect.Parameter.KEYWORD_ONLY or name in skip:
            continue
        resolved[name] = _resolve_one(name)
    return resolved


def _resolve_one(name: str) -> Any:
    if name.endswith("window_runs"):
        return 4
    if name == "class_memory_recency_weights":
        return (1.0, 0.8, 0.6, 0.4)

    # Explicit fixed stand-ins take priority over real module functions of the same
    # name (F3): e.g. `closure_forecast_reset_side_from_status` is a real str->str
    # module fn injected into four composers, but the net must use the fixed
    # `_side_from_status` stand-in so it never silently tracks the live function as
    # the collapse refactors it.
    if name.endswith(("side_from_event", "memory_side_from_event")):
        return _side_from_event
    if name.endswith(
        (
            "side_from_status",
            "side_from_persistence_status",
            "side_from_recovery_status",
        )
    ):
        return _side_from_status
    if name.endswith("path_label"):
        return _path_label
    if name == "clamp_round":
        return _clamp_round
    if name == "closure_forecast_direction_majority":
        return _direction_majority
    if name == "closure_forecast_direction_reversing":
        return _direction_reversing
    if name == "class_direction_flip_count":
        return _flip_count
    if name == "target_specific_normalization_noise":
        return _normalization_noise
    if name == "target_class_key":
        return _class_key
    if name == "target_label":
        return _label
    if name == "ordered_reset_reentry_events_for_target":
        return _ordered_events
    if name == "normalized_closure_forecast_direction":
        return _normalized_direction
    if name == "closure_forecast_freshness_status":
        return _freshness_status
    if name.endswith("freshness_reason"):
        return _freshness_reason
    if name == "recent_reset_reentry_signal_mix":
        return _signal_mix
    if name.endswith("event_has_evidence"):
        return _has_evidence
    if name.endswith("event_is_confirmation_like"):
        return _is_confirmation_like
    if name.endswith("event_is_clearance_like"):
        return _is_clearance_like
    if name.endswith("event_signal_label"):
        return _signal_label

    # Fallback: a kwarg that names a real module composer. The rerererestore wrappers
    # inject the live rererestore `*_for_target` builder (no suffix stand-in matches
    # it); bind it recursively under the same stand-in harness so the wrapper
    # genuinely delegates to the real tier it wraps.
    real = getattr(m, name, None)
    if callable(real) and getattr(real, "__module__", None) == m.__name__:
        sub = _resolve_kwargs(real)
        return functools.partial(real, **sub) if sub else real

    raise KeyError(
        f"composer enumerator: no fixed stand-in for injected kwarg {name!r}"
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
        # The divergence fixture: confirmation side, one strong event + one decrement
        # event -> rebuild floors the decrement to 0, rererestore keeps it negative.
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
    primary = {**rich[0], "label": _class_key(rich[0])}
    list_a = [{**rich[0], "label": _class_key(rich[0])}]
    list_b = [{**rich[1], "label": _class_key(rich[1])}]
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
        kwargs = _resolve_kwargs(fn)
        for label, target, events, history_meta in _for_target_scenarios():
            args = (
                (target, events, history_meta)
                if len(positional) == 3
                else (target, events)
            )
            results[label] = fn(*args, **kwargs)
    elif role == "hotspots":
        kwargs = _resolve_kwargs(fn, skip=frozenset({"mode"}))
        targets = _hotspot_targets()
        for mode in HOTSPOT_MODES:
            results[f"mode={mode}"] = fn(targets, mode=mode, **kwargs)
    elif role == "summary":
        kwargs = _resolve_kwargs(fn)
        primary, list_a, list_b = _summary_inputs()
        args = (primary, list_a, list_b) if len(positional) == 3 else (primary, list_a)
        results["summary"] = fn(*args, **kwargs)
    elif role == "path_label":
        kwargs = _resolve_kwargs(fn)
        for label, event in {
            "confirmation": _event("c", "confirmation"),
            "clearance": _event("k", "clearance"),
            "none": _event("n", "none"),
        }.items():
            results[label] = fn(event, **kwargs)
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
