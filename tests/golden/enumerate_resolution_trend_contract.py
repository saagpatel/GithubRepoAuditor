"""Characterization enumerator for ``_build_resolution_trend`` — the 1,852-line
god-function in ``operator_resolution_trend`` whose 1,676-line ``payload.update({...})``
assembles the full operator resolution-trend payload (320+ keys) from the
apply-chain / summary-context stages.

The sibling enumerators pin the lower layers:
  * ``enumerate_recovery_state_contract.py`` — the pure ``(status:str)->str`` classifiers.
  * ``enumerate_composer_contract.py``       — the per-tier dict/list composers.
Neither exercises the *top-level assembly* — how the god-function wires the
apply-chain tiers and summary-context into the final payload dict the two real
consumers (``operator_control_center`` and ``operator_decision_quality``) read.
This enumerator captures that assembled payload across a representative input
corpus into a frozen golden, so the upcoming decomposition of the god-function
(extracting the payload-assembly seam, then collapsing the per-tier blocks onto a
parametrized base) is provably byte-identical: re-run this, diff the JSON, and a
clean diff proves the structure was preserved.

Safety: imports only the pure-computation module (verified free of import-time
DB/IO side effects, same as the sibling enumerators) and calls
``_build_resolution_trend`` on in-memory synthetic inputs. Never opens a database.

Regenerate the golden only with an intentional, reviewed behavior change::

    uv run python tests/golden/enumerate_resolution_trend_contract.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import src.operator_resolution_trend as m

REPO = Path(__file__).resolve().parents[2]
GOLDEN_PATH = REPO / "tests" / "golden" / "resolution_trend_contract.golden.json"


def _item(
    item_id: str,
    *,
    lane: str,
    kind: str,
    repo: str,
    title: str,
    age_days: int,
    severity: float,
) -> dict[str, Any]:
    """A queue/snapshot item rich enough for target selection + class keying."""
    return {
        "item_id": item_id,
        "id": item_id,
        "lane": lane,
        "kind": kind,
        "repo": repo,
        "title": title,
        "age_days": age_days,
        "severity": severity,
        "score": severity,
        "recommended_next_step": f"Act on {title}.",
        "reason": f"{title} needs attention.",
    }


def _snapshot(items: list[dict], *, generated_at: str) -> dict[str, Any]:
    """A history snapshot keyed by ``_queue_identity`` (item_id when present)."""
    return {
        "snapshot": {
            "items": {it["item_id"]: it for it in items},
            "has_attention": any(it["lane"] in ("blocked", "urgent") for it in items),
            "generated_at": generated_at,
        }
    }


def _ts(day: int) -> str:
    return f"2026-04-{day:02d}T12:00:00Z"


# --------------------------------------------------------------------------- #
# Corpus: each case is (label, queue, history, evidence_events,
# confidence_calibration, current_generated_at). Designed to exercise the empty
# branch (falsy primary_target -> IfExp false-branches) AND a stale-attention
# target that survives the full apply-chain (truthy primary_target -> IfExp
# true-branches + populated per-tier summaries/hotspots).
# --------------------------------------------------------------------------- #
def _rich_history_entry(
    item: dict,
    queue_items: list[dict] | None = None,
    *,
    generated_at: str,
    closure_likely_outcome: str = "none",
    hysteresis_status: str = "none",
    transition_status: str = "none",
    resolution_status: str = "none",
    reweight_direction: str = "neutral",
    reweight_score: float = 0.0,
    momentum_status: str = "insufficient-data",
    stability_status: str = "watch",
    freshness_status: str = "insufficient-data",
    reacquisition_freshness_status: str = "insufficient-data",
    persistence_reset_status: str = "none",
    reset_reentry_status: str = "none",
    reset_reentry_persistence_status: str = "none",
    reset_reentry_churn_status: str = "none",
    reset_reentry_freshness_status: str = "insufficient-data",
    reset_refresh_recovery_status: str = "none",
    rebuild_status: str = "none",
    rebuild_reentry_status: str = "none",
    rebuild_reentry_persistence_status: str = "none",
    rebuild_reentry_freshness_status: str = "insufficient-data",
    rebuild_reentry_refresh_recovery_status: str = "none",
    rebuild_freshness_status: str = "insufficient-data",
    rebuild_reset_status: str = "none",
    rebuild_reentry_reset_status: str = "none",
    restore_status: str = "none",
    restore_persistence_status: str = "none",
    restore_freshness_status: str = "insufficient-data",
    restore_refresh_recovery_status: str = "none",
    restore_reset_status: str = "none",
    rerestore_status: str = "none",
    rerestore_persistence_status: str = "none",
    rerestore_freshness_status: str = "insufficient-data",
    rerestore_refresh_recovery_status: str = "none",
    rerestore_reset_status: str = "none",
    rererestore_status: str = "none",
    rererestore_persistence_status: str = "none",
    trust_policy: str = "monitor",
) -> dict:
    """A history entry with a rich operator_summary.primary_target payload.

    ``_snapshot_from_history`` reads ``entry["operator_queue"]`` for items and
    ``_class_closure_forecast_events`` reads
    ``entry["operator_summary"]["primary_target"]``.  Both are populated so a
    single entry drives both the recency/attention tracking and the deep
    closure-forecast event history.
    """
    primary_target = {
        **item,
        "trust_policy": trust_policy,
        # transition / hysteresis
        "transition_closure_likely_outcome": closure_likely_outcome,
        "closure_forecast_hysteresis_status": hysteresis_status,
        "class_reweight_transition_status": transition_status,
        "class_transition_resolution_status": resolution_status,
        # reweight direction / score
        "closure_forecast_reweight_direction": reweight_direction,
        "closure_forecast_reweight_score": reweight_score,
        # momentum / stability / freshness
        "closure_forecast_momentum_status": momentum_status,
        "closure_forecast_stability_status": stability_status,
        "closure_forecast_freshness_status": freshness_status,
        "closure_forecast_reacquisition_freshness_status": reacquisition_freshness_status,
        # persistence reset (drives reset_refresh_recovery computation)
        "closure_forecast_persistence_reset_status": persistence_reset_status,
        # reset-reentry tier
        "closure_forecast_reset_reentry_status": reset_reentry_status,
        "closure_forecast_reset_reentry_persistence_status": reset_reentry_persistence_status,
        "closure_forecast_reset_reentry_churn_status": reset_reentry_churn_status,
        "closure_forecast_reset_reentry_freshness_status": reset_reentry_freshness_status,
        "closure_forecast_reset_refresh_recovery_status": reset_refresh_recovery_status,
        # rebuild tier
        "closure_forecast_reset_reentry_rebuild_status": rebuild_status,
        "closure_forecast_reset_reentry_rebuild_freshness_status": rebuild_freshness_status,
        # rebuild reset (drives rebuild_reentry tier via level-2 recovery)
        "closure_forecast_reset_reentry_rebuild_reset_status": rebuild_reset_status,
        # rebuild-reentry tier
        "closure_forecast_reset_reentry_rebuild_reentry_status": rebuild_reentry_status,
        "closure_forecast_reset_reentry_rebuild_reentry_persistence_status": rebuild_reentry_persistence_status,
        "closure_forecast_reset_reentry_rebuild_reentry_freshness_status": rebuild_reentry_freshness_status,
        "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status": rebuild_reentry_refresh_recovery_status,
        # rebuild-reentry reset (drives restore tier via level-3 recovery)
        "closure_forecast_reset_reentry_rebuild_reentry_reset_status": rebuild_reentry_reset_status,
        # restore tier
        "closure_forecast_reset_reentry_rebuild_reentry_restore_status": restore_status,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_status": restore_persistence_status,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_status": restore_freshness_status,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_status": restore_refresh_recovery_status,
        # restore reset (drives rerestore tier refresh recovery)
        "closure_forecast_reset_reentry_rebuild_reentry_restore_reset_status": restore_reset_status,
        # rerestore tier
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": rerestore_status,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_status": rerestore_persistence_status,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status": rerestore_freshness_status,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_status": rerestore_refresh_recovery_status,
        # rerestore reset (drives rererestore tier refresh recovery)
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_status": rerestore_reset_status,
        # rererestore tier
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": rererestore_status,
        "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": rererestore_persistence_status,
    }
    all_queue_items = queue_items if queue_items is not None else [item]
    return {
        "generated_at": generated_at,
        "operator_queue": all_queue_items,
        "operator_summary": {
            "primary_target": primary_target,
            "counts": {
                "blocked": sum(
                    1 for i in all_queue_items if i.get("lane") == "blocked"
                ),
                "urgent": sum(1 for i in all_queue_items if i.get("lane") == "urgent"),
            },
            # top-level summary shortcuts read by class_closure_forecast_events
            "primary_target_closure_forecast_reweight_direction": reweight_direction,
            "primary_target_closure_forecast_reweight_score": reweight_score,
        },
    }


def _corpus() -> list[tuple[str, list, list, list, dict, str]]:
    blocked = _item(
        "RepoA:Harden auth",
        lane="blocked",
        kind="security",
        repo="RepoA",
        title="Harden auth",
        age_days=12,
        severity=0.9,
    )
    urgent = _item(
        "RepoB:Ship migration",
        lane="urgent",
        kind="migration",
        repo="RepoB",
        title="Ship migration",
        age_days=9,
        severity=0.7,
    )
    ready = _item(
        "RepoC:Polish docs",
        lane="ready",
        kind="docs",
        repo="RepoC",
        title="Polish docs",
        age_days=2,
        severity=0.3,
    )

    # A long stale-attention history so the blocked item climbs the apply chain.
    stale_history = [
        _snapshot([blocked, urgent, ready], generated_at=_ts(day))
        for day in range(1, 9)
    ]

    evidence = [
        {
            "item_id": "RepoA:Harden auth",
            "kind": "intervention",
            "outcome": "in-progress",
            "generated_at": _ts(7),
            "magnitude": 0.8,
        },
        {
            "item_id": "RepoA:Harden auth",
            "kind": "resolution",
            "outcome": "confirmed",
            "generated_at": _ts(8),
            "magnitude": 0.6,
        },
    ]
    calibration = {
        "confidence": 0.62,
        "sample_size": 14,
        "reliability": "noisy",
        "recent_accuracy": 0.55,
    }

    return [
        ("empty", [], [], [], {}, _ts(9)),
        (
            "single_blocked_stale",
            [blocked],
            stale_history,
            evidence,
            calibration,
            _ts(9),
        ),
        (
            "multi_class_attention",
            [blocked, urgent, ready],
            stale_history,
            evidence,
            calibration,
            _ts(9),
        ),
        (
            "attention_no_history",
            [blocked, urgent],
            [],
            [],
            {},
            _ts(9),
        ),
        # ------------------------------------------------------------------ #
        # Case: confirmation-side reset-reentry (reentered-confirmation).
        # History: old reset event at day 2, fresh confirmation runs days 3-8.
        # The pipeline computes reentry_status="reentered-confirmation" and
        # persistence_status="holding-confirmation-reentry", driving the
        # _apply_reset_reentry_persistence_and_churn_control reentered-
        # confirmation branch and the freshness-stale branches.
        # ------------------------------------------------------------------ #
        (
            "reset_reentry_confirmation_holding",
            [blocked],
            # History sorted newest-first by generated_at.
            # Days 8..3: fresh confirmation signal post-reset.
            # Day 2: the confirmation-reset event.
            # Day 1: pre-reset confirmation baseline.
            [
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(d),
                    reweight_direction="supporting-confirmation",
                    reweight_score=0.6,
                    closure_likely_outcome="confirm-soon",
                    hysteresis_status="confirmed-confirmation",
                    momentum_status="sustained-confirmation",
                    stability_status="stable",
                    freshness_status="fresh",
                    reacquisition_freshness_status="fresh",
                    reset_reentry_status="reentered-confirmation",
                    reset_reentry_persistence_status="holding-confirmation-reentry",
                    reset_reentry_freshness_status="fresh",
                    trust_policy="act",
                )
                for d in range(8, 2, -1)  # days 8, 7, 6, 5, 4, 3
            ]
            + [
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(2),
                    reweight_direction="neutral",
                    reweight_score=0.0,
                    closure_likely_outcome="hold",
                    hysteresis_status="none",
                    momentum_status="insufficient-data",
                    stability_status="watch",
                    freshness_status="insufficient-data",
                    reacquisition_freshness_status="insufficient-data",
                    persistence_reset_status="confirmation-reset",
                    trust_policy="monitor",
                ),
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(1),
                    reweight_direction="supporting-confirmation",
                    reweight_score=0.5,
                    closure_likely_outcome="confirm-soon",
                    hysteresis_status="confirmed-confirmation",
                    momentum_status="sustained-confirmation",
                    stability_status="stable",
                    freshness_status="fresh",
                    reacquisition_freshness_status="fresh",
                    trust_policy="act",
                ),
            ],
            evidence,
            calibration,
            _ts(9),
        ),
        # ------------------------------------------------------------------ #
        # Case: clearance-side reset-reentry (reentered-clearance), stale.
        # Exercises "expire-risk"/"clear-risk" outcome downgrades + stale
        # freshness branch in _apply_reset_reentry_persistence_and_churn_control
        # ------------------------------------------------------------------ #
        (
            "reset_reentry_clearance_stale",
            [blocked],
            [
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(d),
                    reweight_direction="supporting-clearance",
                    reweight_score=-0.5,
                    closure_likely_outcome="expire-risk" if d > 4 else "clear-risk",
                    hysteresis_status="confirmed-clearance",
                    momentum_status="sustained-clearance",
                    stability_status="stable",
                    freshness_status="stale",
                    reacquisition_freshness_status="stale",
                    reset_reentry_status="reentered-clearance",
                    reset_reentry_persistence_status="holding-clearance-reentry",
                    reset_reentry_freshness_status="stale",
                    trust_policy="monitor",
                )
                for d in range(8, 3, -1)  # days 8..4 post-reset fresh clearance
            ]
            + [
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(3),
                    reweight_direction="neutral",
                    reweight_score=0.0,
                    persistence_reset_status="clearance-reset",
                    trust_policy="monitor",
                ),
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(2),
                    reweight_direction="supporting-clearance",
                    reweight_score=-0.4,
                    reacquisition_freshness_status="stale",
                    trust_policy="monitor",
                ),
            ],
            [],
            calibration,
            _ts(9),
        ),
        # ------------------------------------------------------------------ #
        # Case: clearance-side reentered-clearance with "cleared" resolution
        # and pending-caution so the restore-transition path fires.
        # ------------------------------------------------------------------ #
        (
            "reset_reentry_clearance_reversing_cleared",
            [blocked],
            [
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(d),
                    reweight_direction="supporting-clearance",
                    reweight_score=-0.4,
                    closure_likely_outcome="clear-risk",
                    hysteresis_status="confirmed-clearance",
                    transition_status="pending-caution",
                    resolution_status="cleared",
                    momentum_status="reversing",
                    stability_status="watch",
                    freshness_status="stale",
                    reacquisition_freshness_status="insufficient-data",
                    reset_reentry_status="reentered-clearance",
                    reset_reentry_persistence_status="reversing",
                    reset_reentry_freshness_status="stale",
                    trust_policy="monitor",
                )
                for d in range(8, 3, -1)
            ]
            + [
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(3),
                    reweight_direction="neutral",
                    reweight_score=0.0,
                    persistence_reset_status="clearance-reset",
                    trust_policy="monitor",
                ),
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(2),
                    reweight_direction="supporting-clearance",
                    reweight_score=-0.3,
                    reacquisition_freshness_status="insufficient-data",
                    trust_policy="monitor",
                ),
            ],
            [],
            calibration,
            _ts(9),
        ),
        # ------------------------------------------------------------------ #
        # Case: churn_status=="blocked" with confirmation side.
        # Uses same reset pattern; churn_status driven by oscillating momentum.
        # ------------------------------------------------------------------ #
        (
            "reset_reentry_churn_blocked_confirmation",
            [blocked],
            [
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(d),
                    reweight_direction="supporting-confirmation",
                    reweight_score=0.5,
                    closure_likely_outcome="confirm-soon",
                    hysteresis_status="confirmed-confirmation",
                    momentum_status="unstable",
                    stability_status="oscillating",
                    freshness_status="mixed-age",
                    reacquisition_freshness_status="mixed-age",
                    reset_reentry_status="reentered-confirmation",
                    reset_reentry_persistence_status="holding-confirmation-reentry",
                    reset_reentry_churn_status="blocked",
                    reset_reentry_freshness_status="mixed-age",
                    trust_policy="act",
                )
                for d in range(8, 3, -1)
            ]
            + [
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(3),
                    reweight_direction="neutral",
                    reweight_score=0.0,
                    persistence_reset_status="confirmation-reset",
                    trust_policy="monitor",
                ),
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(2),
                    reweight_direction="supporting-confirmation",
                    reweight_score=0.4,
                    reacquisition_freshness_status="mixed-age",
                    trust_policy="monitor",
                ),
            ],
            evidence,
            calibration,
            _ts(9),
        ),
        # ------------------------------------------------------------------ #
        # Case: deep rebuild-reentry tier, confirmation side.
        # Drives _apply_reset_reentry_rebuild_reentry_*_control helpers.
        # History: rebuild reset event at day 4, fresh-confirmation runs
        # at days 6 and 5 (within the 4-run window), baseline at day 3.
        # Window = 4: events [current, day6, day5, day4], reset at [3].
        # ------------------------------------------------------------------ #
        (
            "rebuild_reentry_confirmation_holding",
            [blocked],
            [
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(6),
                    reweight_direction="supporting-confirmation",
                    reweight_score=0.7,
                    closure_likely_outcome="confirm-soon",
                    hysteresis_status="confirmed-confirmation",
                    momentum_status="sustained-confirmation",
                    stability_status="stable",
                    freshness_status="fresh",
                    reacquisition_freshness_status="fresh",
                    rebuild_freshness_status="fresh",
                    rebuild_reentry_freshness_status="fresh",
                    trust_policy="act",
                ),
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(5),
                    reweight_direction="supporting-confirmation",
                    reweight_score=0.7,
                    closure_likely_outcome="confirm-soon",
                    hysteresis_status="confirmed-confirmation",
                    momentum_status="sustained-confirmation",
                    stability_status="stable",
                    freshness_status="fresh",
                    reacquisition_freshness_status="fresh",
                    rebuild_freshness_status="fresh",
                    rebuild_reentry_freshness_status="fresh",
                    trust_policy="act",
                ),
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(4),
                    reweight_direction="neutral",
                    reweight_score=0.0,
                    rebuild_reset_status="confirmation-reset",
                    trust_policy="monitor",
                ),
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(3),
                    reweight_direction="supporting-confirmation",
                    reweight_score=0.5,
                    trust_policy="act",
                ),
            ],
            evidence,
            {
                "confidence": 0.75,
                "sample_size": 20,
                "reliability": "healthy",
                "recent_accuracy": 0.72,
                "confidence_validation_status": "healthy",
            },
            _ts(7),
        ),
        # ------------------------------------------------------------------ #
        # Case: deep rebuild-reentry tier, clearance side, stale freshness.
        # History: rebuild reset event at day 4, clearance runs at days
        # 6 and 5 with rebuild_freshness_status="stale".
        # ------------------------------------------------------------------ #
        (
            "rebuild_reentry_clearance_stale",
            [blocked],
            [
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(6),
                    reweight_direction="supporting-clearance",
                    reweight_score=-0.6,
                    closure_likely_outcome="clear-risk",
                    hysteresis_status="confirmed-clearance",
                    momentum_status="sustained-clearance",
                    stability_status="stable",
                    freshness_status="stale",
                    reacquisition_freshness_status="stale",
                    rebuild_freshness_status="stale",
                    rebuild_reentry_freshness_status="stale",
                    trust_policy="monitor",
                ),
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(5),
                    reweight_direction="supporting-clearance",
                    reweight_score=-0.6,
                    closure_likely_outcome="expire-risk",
                    hysteresis_status="confirmed-clearance",
                    momentum_status="sustained-clearance",
                    stability_status="stable",
                    freshness_status="stale",
                    reacquisition_freshness_status="stale",
                    rebuild_freshness_status="stale",
                    rebuild_reentry_freshness_status="stale",
                    trust_policy="monitor",
                ),
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(4),
                    reweight_direction="neutral",
                    reweight_score=0.0,
                    rebuild_reset_status="clearance-reset",
                    trust_policy="monitor",
                ),
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(3),
                    reweight_direction="supporting-clearance",
                    reweight_score=-0.4,
                    trust_policy="monitor",
                ),
            ],
            [],
            calibration,
            _ts(7),
        ),
        # ------------------------------------------------------------------ #
        # Case: restore tier (rebuild-reentry-restore), confirmation side.
        # History: rebuild_reentry reset event at day 2
        # (rebuild_reentry_reset_status="confirmation-reset") + fresh-
        # confirmation runs days 8..3 after it.
        # ------------------------------------------------------------------ #
        (
            "restore_confirmation_holding",
            [blocked],
            [
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(d),
                    reweight_direction="supporting-confirmation",
                    reweight_score=0.8,
                    closure_likely_outcome="confirm-soon",
                    hysteresis_status="confirmed-confirmation",
                    momentum_status="sustained-confirmation",
                    stability_status="stable",
                    freshness_status="fresh",
                    reacquisition_freshness_status="fresh",
                    reset_reentry_status="reentered-confirmation",
                    reset_reentry_freshness_status="fresh",
                    rebuild_reentry_status="reentered-confirmation-rebuild",
                    rebuild_reentry_freshness_status="fresh",
                    restore_freshness_status="fresh",
                    trust_policy="act",
                )
                for d in range(8, 2, -1)
            ]
            + [
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(2),
                    reweight_direction="neutral",
                    reweight_score=0.0,
                    rebuild_reentry_reset_status="confirmation-reset",
                    trust_policy="monitor",
                ),
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(1),
                    reweight_direction="supporting-confirmation",
                    reweight_score=0.5,
                    rebuild_reentry_freshness_status="fresh",
                    trust_policy="act",
                ),
            ],
            evidence,
            {
                "confidence": 0.80,
                "sample_size": 25,
                "reliability": "healthy",
                "recent_accuracy": 0.78,
                "confidence_validation_status": "healthy",
            },
            _ts(9),
        ),
        # ------------------------------------------------------------------ #
        # Case: restore tier, clearance side, stale freshness.
        # History: rebuild_reentry reset event at day 2
        # (rebuild_reentry_reset_status="clearance-reset") + clearance
        # direction runs days 8..3.
        # ------------------------------------------------------------------ #
        (
            "restore_clearance_stale",
            [blocked],
            [
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(d),
                    reweight_direction="supporting-clearance",
                    reweight_score=-0.7,
                    closure_likely_outcome="expire-risk" if d < 6 else "clear-risk",
                    hysteresis_status="confirmed-clearance",
                    momentum_status="sustained-clearance",
                    stability_status="stable",
                    freshness_status="stale",
                    reacquisition_freshness_status="stale",
                    reset_reentry_status="reentered-clearance",
                    reset_reentry_freshness_status="stale",
                    rebuild_reentry_status="reentered-clearance-rebuild",
                    rebuild_reentry_freshness_status="stale",
                    restore_freshness_status="stale",
                    trust_policy="monitor",
                )
                for d in range(8, 2, -1)
            ]
            + [
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(2),
                    reweight_direction="neutral",
                    reweight_score=0.0,
                    rebuild_reentry_reset_status="clearance-reset",
                    trust_policy="monitor",
                ),
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(1),
                    reweight_direction="supporting-clearance",
                    reweight_score=-0.4,
                    rebuild_reentry_freshness_status="stale",
                    trust_policy="monitor",
                ),
            ],
            [],
            calibration,
            _ts(9),
        ),
        # ------------------------------------------------------------------ #
        # Case: rerestore tier, confirmation side.
        # History: restore reset event at day 2
        # (restore_reset_status="confirmation-reset") + fresh-confirmation
        # runs days 8..3 after it.
        # ------------------------------------------------------------------ #
        (
            "rerestore_confirmation_holding",
            [blocked],
            [
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(d),
                    reweight_direction="supporting-confirmation",
                    reweight_score=0.85,
                    closure_likely_outcome="confirm-soon",
                    hysteresis_status="confirmed-confirmation",
                    momentum_status="sustained-confirmation",
                    stability_status="stable",
                    freshness_status="fresh",
                    reacquisition_freshness_status="fresh",
                    reset_reentry_status="reentered-confirmation",
                    reset_reentry_freshness_status="fresh",
                    rebuild_reentry_status="reentered-confirmation-rebuild",
                    rebuild_reentry_freshness_status="fresh",
                    restore_status="holding-confirmation-restore",
                    restore_freshness_status="fresh",
                    rerestore_freshness_status="fresh",
                    trust_policy="act",
                )
                for d in range(8, 2, -1)
            ]
            + [
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(2),
                    reweight_direction="neutral",
                    reweight_score=0.0,
                    restore_reset_status="confirmation-reset",
                    trust_policy="monitor",
                ),
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(1),
                    reweight_direction="supporting-confirmation",
                    reweight_score=0.5,
                    restore_freshness_status="fresh",
                    trust_policy="act",
                ),
            ],
            evidence,
            {
                "confidence": 0.85,
                "sample_size": 30,
                "reliability": "healthy",
                "recent_accuracy": 0.82,
                "confidence_validation_status": "healthy",
            },
            _ts(9),
        ),
        # ------------------------------------------------------------------ #
        # Case: rerestore clearance stale.
        # History: restore reset event at day 2
        # (restore_reset_status="clearance-reset") + clearance runs
        # days 8..3.
        # ------------------------------------------------------------------ #
        (
            "rerestore_clearance_stale",
            [blocked],
            [
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(d),
                    reweight_direction="supporting-clearance",
                    reweight_score=-0.8,
                    closure_likely_outcome="expire-risk" if d < 6 else "clear-risk",
                    hysteresis_status="confirmed-clearance",
                    momentum_status="sustained-clearance",
                    stability_status="stable",
                    freshness_status="stale",
                    reacquisition_freshness_status="stale",
                    reset_reentry_status="reentered-clearance",
                    reset_reentry_freshness_status="stale",
                    rebuild_reentry_status="reentered-clearance-rebuild",
                    rebuild_reentry_freshness_status="stale",
                    restore_status="holding-clearance-restore",
                    restore_freshness_status="stale",
                    rerestore_freshness_status="stale",
                    trust_policy="monitor",
                )
                for d in range(8, 2, -1)
            ]
            + [
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(2),
                    reweight_direction="neutral",
                    reweight_score=0.0,
                    restore_reset_status="clearance-reset",
                    trust_policy="monitor",
                ),
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(1),
                    reweight_direction="supporting-clearance",
                    reweight_score=-0.4,
                    restore_freshness_status="stale",
                    trust_policy="monitor",
                ),
            ],
            [],
            calibration,
            _ts(9),
        ),
        # ------------------------------------------------------------------ #
        # Case: hysteresis confirm-soon + sustained-confirmation momentum
        # drives confirmed-confirmation branch.
        # ------------------------------------------------------------------ #
        (
            "hysteresis_confirm_soon_sustained",
            [blocked, urgent],
            [
                _rich_history_entry(
                    blocked,
                    [blocked, urgent],
                    generated_at=_ts(d),
                    reweight_direction="supporting-confirmation",
                    reweight_score=0.65,
                    closure_likely_outcome="confirm-soon",
                    hysteresis_status="pending-confirmation",
                    momentum_status="sustained-confirmation",
                    stability_status="stable",
                    freshness_status="fresh",
                    reacquisition_freshness_status="fresh",
                    trust_policy="act",
                )
                for d in range(1, 9)
            ],
            evidence,
            {
                "confidence": 0.75,
                "sample_size": 18,
                "reliability": "healthy",
                "recent_accuracy": 0.70,
                "confidence_validation_status": "healthy",
            },
            _ts(9),
        ),
        # ------------------------------------------------------------------ #
        # Case: hysteresis expire-risk + sustained-clearance.
        # ------------------------------------------------------------------ #
        (
            "hysteresis_expire_risk_sustained_clearance",
            [blocked],
            [
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(d),
                    reweight_direction="supporting-clearance",
                    reweight_score=-0.5,
                    closure_likely_outcome="expire-risk",
                    hysteresis_status="pending-clearance",
                    momentum_status="sustained-clearance",
                    stability_status="stable",
                    freshness_status="fresh",
                    reacquisition_freshness_status="fresh",
                    trust_policy="monitor",
                )
                for d in range(1, 9)
            ],
            [],
            {
                "confidence": 0.60,
                "sample_size": 12,
                "reliability": "mixed",
                "recent_accuracy": 0.60,
                "confidence_validation_status": "mixed",
            },
            _ts(9),
        ),
        # ------------------------------------------------------------------ #
        # Case: hysteresis reversing-momentum — softening path.
        # ------------------------------------------------------------------ #
        (
            "hysteresis_reversing_momentum",
            [blocked],
            [
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(d),
                    reweight_direction="supporting-confirmation",
                    reweight_score=0.4,
                    closure_likely_outcome="confirm-soon" if d < 6 else "hold",
                    hysteresis_status="pending-confirmation",
                    momentum_status="reversing",
                    stability_status="oscillating",
                    freshness_status="mixed-age",
                    reacquisition_freshness_status="mixed-age",
                    trust_policy="monitor",
                )
                for d in range(1, 9)
            ],
            [],
            calibration,
            _ts(9),
        ),
        # ------------------------------------------------------------------ #
        # Case: calibration healthy + blocked lane → +0.05 adjustment.
        # ------------------------------------------------------------------ #
        (
            "calibration_healthy_blocked",
            [blocked],
            stale_history,
            evidence,
            {
                "confidence": 0.72,
                "sample_size": 20,
                "reliability": "healthy",
                "recent_accuracy": 0.75,
                "confidence_validation_status": "healthy",
            },
            _ts(9),
        ),
        # ------------------------------------------------------------------ #
        # Case: calibration noisy + decision_memory_status "reopened"
        # → double-softening branch (-0.10 + -0.05).
        # ------------------------------------------------------------------ #
        (
            "calibration_noisy_reopened",
            [blocked],
            stale_history,
            [
                {
                    "item_id": "RepoA:Harden auth",
                    "kind": "resolution",
                    "outcome": "confirmed",
                    "generated_at": _ts(3),
                    "magnitude": 0.7,
                },
                {
                    "item_id": "RepoA:Harden auth",
                    "kind": "intervention",
                    "outcome": "reverted",
                    "generated_at": _ts(7),
                    "magnitude": -0.6,
                },
            ],
            {
                "confidence": 0.65,
                "sample_size": 10,
                "reliability": "noisy",
                "recent_accuracy": 0.45,
                "confidence_validation_status": "noisy",
            },
            _ts(9),
        ),
        # ------------------------------------------------------------------ #
        # Case: calibration noisy + pre-calibration score is HIGH (>=0.75).
        # Exercises _apply_calibration_adjustment lines 19127-19128 (high-label
        # softening) and 19136-19137 (extra reopened softening), both of which
        # require the noisy branch AND a different confidence path than the
        # existing calibration_noisy_reopened case (which only hits medium).
        #
        # Construction: blocked item with priority>=85, decision_memory_status
        # "reopened" (achieved via history where item was absent from attention
        # for several runs, then re-appeared blocked), and aging_status="chronic"
        # (age_days=30 produces chronic aging).  Pre-calibration confidence
        # score = 0.95 (high), so noisy calibration applies the -0.10 high
        # penalty first (lines 19127-19128) and then the additional -0.05
        # reopened penalty (lines 19136-19137).
        # ------------------------------------------------------------------ #
        (
            "calibration_noisy_high_score_reopened",
            [
                {
                    "item_id": "RepoA:Harden auth",
                    "id": "RepoA:Harden auth",
                    "lane": "blocked",
                    "kind": "security",
                    "repo": "RepoA",
                    "title": "Harden auth",
                    "age_days": 30,
                    "severity": 0.9,
                    "score": 0.9,
                    "priority": 90,
                    "recommended_next_step": "Fix the specific issue in auth.py line 42.",
                    "recommended_action": "Fix the specific issue in auth.py line 42.",
                    "reason": "needs attention.",
                }
            ],
            # History: item was in ready/non-attention lane at days 7-5 (absent
            # from attention), then blocked at days 4-1 (saw earlier attention).
            # This causes _was_resolved_then_reopened to return True, yielding
            # decision_memory_status="reopened" on the live target.
            [
                {
                    "generated_at": _ts(d),
                    "operator_queue": [
                        {
                            "item_id": "RepoA:Harden auth",
                            "id": "RepoA:Harden auth",
                            "lane": "ready",
                            "kind": "security",
                            "repo": "RepoA",
                            "title": "Harden auth",
                            "age_days": 2,
                            "severity": 0.4,
                            "score": 0.4,
                            "priority": 90,
                            "recommended_next_step": "Fix the specific issue in auth.py line 42.",
                            "recommended_action": "Fix the specific issue in auth.py line 42.",
                            "reason": "needs attention.",
                        }
                    ],
                    "operator_summary": {"counts": {"blocked": 0, "urgent": 0}},
                }
                for d in range(7, 4, -1)
            ]
            + [
                {
                    "generated_at": _ts(d),
                    "operator_queue": [
                        {
                            "item_id": "RepoA:Harden auth",
                            "id": "RepoA:Harden auth",
                            "lane": "blocked",
                            "kind": "security",
                            "repo": "RepoA",
                            "title": "Harden auth",
                            "age_days": 30,
                            "severity": 0.9,
                            "score": 0.9,
                            "priority": 90,
                            "recommended_next_step": "Fix the specific issue in auth.py line 42.",
                            "recommended_action": "Fix the specific issue in auth.py line 42.",
                            "reason": "needs attention.",
                        }
                    ],
                    "operator_summary": {"counts": {"blocked": 1, "urgent": 0}},
                }
                for d in range(4, 0, -1)
            ],
            [],
            {
                "confidence": 0.65,
                "sample_size": 10,
                "reliability": "noisy",
                "recent_accuracy": 0.45,
                "confidence_validation_status": "noisy",
            },
            _ts(9),
        ),
        # ------------------------------------------------------------------ #
        # Case: calibration noisy + pre-calibration score is LOW (<0.45).
        # Exercises _apply_calibration_adjustment line 19133 (the else branch
        # that leaves already-low recommendations unchanged).
        # Construction: a ready item with low priority (<60) produces base
        # confidence score = 0.05 (low), and the noisy calibration else-branch
        # fires since the label is neither "high" nor "medium".
        # ------------------------------------------------------------------ #
        (
            "calibration_noisy_low_score",
            [
                {
                    "item_id": "RepoC:Polish docs",
                    "id": "RepoC:Polish docs",
                    "lane": "ready",
                    "kind": "docs",
                    "repo": "RepoC",
                    "title": "Polish docs",
                    "age_days": 2,
                    "severity": 0.3,
                    "score": 0.3,
                    "priority": 50,
                    "recommended_next_step": "Polish it.",
                    "reason": "needs attention.",
                }
            ],
            [],
            [],
            {
                "confidence": 0.65,
                "sample_size": 10,
                "reliability": "noisy",
                "recent_accuracy": 0.45,
                "confidence_validation_status": "noisy",
            },
            _ts(9),
        ),
        # ------------------------------------------------------------------ #
        # Case: rebuild refresh-reentry-control blocked branch — drives the
        # "blocked" reentry_status path in the refresh-reentry helper.
        # ------------------------------------------------------------------ #
        (
            "rebuild_refresh_reentry_blocked",
            [blocked],
            [
                _rich_history_entry(
                    blocked,
                    generated_at=_ts(d),
                    reweight_direction="supporting-confirmation",
                    reweight_score=0.6,
                    closure_likely_outcome="hold",
                    hysteresis_status="pending-confirmation",
                    momentum_status="unstable",
                    stability_status="oscillating",
                    freshness_status="mixed-age",
                    reacquisition_freshness_status="mixed-age",
                    reset_reentry_status="reentered-confirmation",
                    reset_reentry_persistence_status="holding-confirmation-reentry",
                    reset_reentry_freshness_status="mixed-age",
                    rebuild_status="rebuilt-confirmation-reentry",
                    rebuild_reentry_status="blocked" if d >= 6 else "none",
                    rebuild_reentry_persistence_status="none",
                    rebuild_reentry_freshness_status="insufficient-data",
                    rebuild_reentry_refresh_recovery_status=(
                        "reversing" if d >= 5 else "none"
                    ),
                    trust_policy="monitor",
                )
                for d in range(1, 9)
            ],
            evidence,
            calibration,
            _ts(9),
        ),
    ]


def _jsonable(value: Any) -> Any:
    """Stable, lossless-enough JSON projection. Sets -> sorted lists; tuples ->
    lists; anything exotic -> its repr (recorded as part of the contract)."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, set):
        return ["<<set>>", *sorted(_jsonable(v) for v in value)]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def build_contract() -> dict[str, Any]:
    contract: dict[str, Any] = {}
    for label, queue, history, evidence, calibration, generated_at in _corpus():
        payload = m._build_resolution_trend(
            queue,
            history,
            evidence,
            confidence_calibration=calibration,
            current_generated_at=generated_at,
        )
        contract[label] = _jsonable(payload)
    return contract


def main() -> None:
    contract = build_contract()
    GOLDEN_PATH.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    # Operator-facing sanity print (not part of the contract).
    cases = len(contract)
    keysets = {label: len(rows) for label, rows in contract.items()}
    primary = {
        label: bool(rows.get("primary_target")) for label, rows in contract.items()
    }
    print(f"wrote {GOLDEN_PATH.relative_to(REPO)}")
    print(f"cases: {cases}")
    print(f"keys per case: {keysets}")
    print(f"truthy primary_target per case: {primary}")


if __name__ == "__main__":
    main()
