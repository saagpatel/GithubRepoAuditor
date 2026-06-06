"""Characterization tests for the follow-through ``*_status_label`` and
``*_summary`` builder families in ``report_enrichment``.

These pin the *current* behavior of all 16 ``build_follow_through_*_status_label``
builders and their 16 ``*_summary``/checkpoint siblings before the Arc F
data-table refactor collapses the duplicated bodies into shared helpers. The
spec tables below are transcribed directly from the pre-refactor source, so they
form a golden net that is independent of whatever lookup table the refactored
implementation builds — a mis-wired key, default, label, or constant fails here.
"""

from __future__ import annotations

import pytest

import src.report_enrichment as RE

# (builder name -> (mapping key, default status, {status: label})) transcribed
# verbatim from the pre-refactor builder bodies.
STATUS_LABEL_SPECS: dict[str, tuple[str, str, dict[str, str]]] = {
    "build_follow_through_status_label": (
        "follow_through_status",
        "unknown",
        {
            "untouched": "Untouched",
            "attempted": "Attempted",
            "waiting-on-evidence": "Waiting on Evidence",
            "stale-follow-through": "Stale Follow-Through",
            "resolved": "Resolved",
            "unknown": "Unknown",
        },
    ),
    "build_follow_through_checkpoint_status_label": (
        "follow_through_checkpoint_status",
        "unknown",
        {
            "not-due": "Not Due",
            "due-soon": "Due Soon",
            "overdue": "Overdue",
            "satisfied": "Satisfied",
            "unknown": "Unknown",
        },
    ),
    "build_follow_through_escalation_status_label": (
        "follow_through_escalation_status",
        "unknown",
        {
            "none": "None",
            "watch": "Watch",
            "nudge": "Nudge",
            "escalate-now": "Escalate Now",
            "resolved-watch": "Resolved Watch",
            "unknown": "Unknown",
        },
    ),
    "build_follow_through_recovery_status_label": (
        "follow_through_recovery_status",
        "none",
        {
            "none": "None",
            "recovering": "Recovering",
            "retiring-watch": "Retiring Watch",
            "retired": "Retired",
            "relapsing": "Relapsing",
            "insufficient-evidence": "Insufficient Evidence",
        },
    ),
    "build_follow_through_recovery_persistence_status_label": (
        "follow_through_recovery_persistence_status",
        "none",
        {
            "none": "None",
            "just-recovering": "Just Recovering",
            "holding-recovery": "Holding Recovery",
            "holding-retiring-watch": "Holding Retiring Watch",
            "sustained-retiring-watch": "Sustained Retiring Watch",
            "sustained-retired": "Sustained Retired",
            "fragile-recovery": "Fragile Recovery",
            "insufficient-evidence": "Insufficient Evidence",
        },
    ),
    "build_follow_through_relapse_churn_status_label": (
        "follow_through_relapse_churn_status",
        "none",
        {
            "none": "None",
            "watch": "Watch",
            "fragile": "Fragile",
            "churn": "Churn",
            "blocked": "Blocked",
            "insufficient-evidence": "Insufficient Evidence",
        },
    ),
    "build_follow_through_recovery_freshness_status_label": (
        "follow_through_recovery_freshness_status",
        "none",
        {
            "none": "None",
            "fresh": "Fresh",
            "holding-fresh": "Holding Fresh",
            "mixed-age": "Mixed Age",
            "stale": "Stale",
            "insufficient-evidence": "Insufficient Evidence",
        },
    ),
    "build_follow_through_recovery_decay_status_label": (
        "follow_through_recovery_decay_status",
        "none",
        {
            "none": "None",
            "softening": "Softening",
            "aging": "Aging",
            "fragile-aging": "Fragile Aging",
            "expired": "Expired",
            "insufficient-evidence": "Insufficient Evidence",
        },
    ),
    "build_follow_through_recovery_memory_reset_status_label": (
        "follow_through_recovery_memory_reset_status",
        "none",
        {
            "none": "None",
            "reset-watch": "Reset Watch",
            "resetting": "Resetting",
            "reset": "Reset",
            "rebuilding": "Rebuilding",
            "insufficient-evidence": "Insufficient Evidence",
        },
    ),
    "build_follow_through_recovery_rebuild_strength_status_label": (
        "follow_through_recovery_rebuild_strength_status",
        "none",
        {
            "none": "None",
            "just-rebuilding": "Just Rebuilding",
            "building": "Building",
            "holding-rebuild": "Holding Rebuild",
            "fragile-rebuild": "Fragile Rebuild",
            "insufficient-evidence": "Insufficient Evidence",
        },
    ),
    "build_follow_through_recovery_reacquisition_status_label": (
        "follow_through_recovery_reacquisition_status",
        "none",
        {
            "none": "None",
            "reacquiring": "Reacquiring",
            "just-reacquired": "Just Reacquired",
            "holding-reacquired": "Holding Reacquired",
            "reacquired": "Reacquired",
            "fragile-reacquisition": "Fragile Reacquisition",
            "insufficient-evidence": "Insufficient Evidence",
        },
    ),
    # NOTE: builder name says "reacquisition_durability" but the mapping key
    # carries a "recovery_" prefix — keyed verbatim, do not derive from name.
    "build_follow_through_reacquisition_durability_status_label": (
        "follow_through_recovery_reacquisition_durability_status",
        "none",
        {
            "none": "None",
            "just-reacquired": "Just Reacquired",
            "consolidating": "Consolidating",
            "holding-reacquired": "Holding Reacquired",
            "durable-reacquired": "Durable Reacquired",
            "softening": "Softening",
            "insufficient-evidence": "Insufficient Evidence",
        },
    ),
    "build_follow_through_reacquisition_consolidation_status_label": (
        "follow_through_recovery_reacquisition_consolidation_status",
        "none",
        {
            "none": "None",
            "building-confidence": "Building Confidence",
            "holding-confidence": "Holding Confidence",
            "durable-confidence": "Durable Confidence",
            "fragile-confidence": "Fragile Confidence",
            "reversing": "Reversing",
            "insufficient-evidence": "Insufficient Evidence",
        },
    ),
    "build_follow_through_reacquisition_softening_decay_status_label": (
        "follow_through_reacquisition_softening_decay_status",
        "none",
        {
            "none": "None",
            "softening-watch": "Softening Watch",
            "step-down": "Step-Down",
            "revalidation-needed": "Revalidation Needed",
            "retired-softening": "Retired Softening",
            "insufficient-evidence": "Insufficient Evidence",
        },
    ),
    "build_follow_through_reacquisition_confidence_retirement_status_label": (
        "follow_through_reacquisition_confidence_retirement_status",
        "none",
        {
            "none": "None",
            "watch-retirement": "Watch Retirement",
            "retiring-confidence": "Retiring Confidence",
            "retired-confidence": "Retired Confidence",
            "revalidation-needed": "Revalidation Needed",
            "insufficient-evidence": "Insufficient Evidence",
        },
    ),
    "build_follow_through_reacquisition_revalidation_recovery_status_label": (
        "follow_through_reacquisition_revalidation_recovery_status",
        "none",
        {
            "none": "None",
            "under-revalidation": "Under Revalidation",
            "rebuilding-restored-confidence": "Rebuilding Restored Confidence",
            "reearning-confidence": "Re-Earning Confidence",
            "just-reearned-confidence": "Just Re-Earned Confidence",
            "holding-reearned-confidence": "Holding Re-Earned Confidence",
            "insufficient-evidence": "Insufficient Evidence",
        },
    ),
}

# (builder name -> (mapping key, NO_* constant attr)) transcribed from the
# pre-refactor ``*_summary`` (and checkpoint) builder bodies.
SUMMARY_SPECS: dict[str, tuple[str, str]] = {
    "build_follow_through_summary": (
        "follow_through_summary",
        "NO_FOLLOW_THROUGH_SUMMARY",
    ),
    "build_follow_through_checkpoint": (
        "follow_through_next_checkpoint",
        "NO_FOLLOW_THROUGH_CHECKPOINT",
    ),
    "build_follow_through_escalation_summary": (
        "follow_through_escalation_summary",
        "NO_FOLLOW_THROUGH_ESCALATION",
    ),
    "build_follow_through_recovery_summary": (
        "follow_through_recovery_summary",
        "NO_FOLLOW_THROUGH_RECOVERY",
    ),
    "build_follow_through_recovery_persistence_summary": (
        "follow_through_recovery_persistence_summary",
        "NO_FOLLOW_THROUGH_RECOVERY_PERSISTENCE",
    ),
    "build_follow_through_relapse_churn_summary": (
        "follow_through_relapse_churn_summary",
        "NO_FOLLOW_THROUGH_RELAPSE_CHURN",
    ),
    "build_follow_through_recovery_freshness_summary": (
        "follow_through_recovery_freshness_summary",
        "NO_FOLLOW_THROUGH_RECOVERY_FRESHNESS",
    ),
    "build_follow_through_recovery_decay_summary": (
        "follow_through_recovery_decay_summary",
        "NO_FOLLOW_THROUGH_RECOVERY_DECAY",
    ),
    "build_follow_through_recovery_memory_reset_summary": (
        "follow_through_recovery_memory_reset_summary",
        "NO_FOLLOW_THROUGH_RECOVERY_MEMORY_RESET",
    ),
    "build_follow_through_recovery_rebuild_strength_summary": (
        "follow_through_recovery_rebuild_strength_summary",
        "NO_FOLLOW_THROUGH_RECOVERY_REBUILD_STRENGTH",
    ),
    "build_follow_through_recovery_reacquisition_summary": (
        "follow_through_recovery_reacquisition_summary",
        "NO_FOLLOW_THROUGH_RECOVERY_REACQUISITION",
    ),
    "build_follow_through_reacquisition_durability_summary": (
        "follow_through_recovery_reacquisition_durability_summary",
        "NO_FOLLOW_THROUGH_REACQUISITION_DURABILITY",
    ),
    "build_follow_through_reacquisition_consolidation_summary": (
        "follow_through_recovery_reacquisition_consolidation_summary",
        "NO_FOLLOW_THROUGH_REACQUISITION_CONSOLIDATION",
    ),
    "build_follow_through_reacquisition_softening_decay_summary": (
        "follow_through_reacquisition_softening_decay_summary",
        "NO_FOLLOW_THROUGH_REACQUISITION_SOFTENING_DECAY",
    ),
    "build_follow_through_reacquisition_confidence_retirement_summary": (
        "follow_through_reacquisition_confidence_retirement_summary",
        "NO_FOLLOW_THROUGH_REACQUISITION_CONFIDENCE_RETIREMENT",
    ),
    "build_follow_through_reacquisition_revalidation_recovery_summary": (
        "follow_through_reacquisition_revalidation_recovery_summary",
        "NO_FOLLOW_THROUGH_REACQUISITION_REVALIDATION_RECOVERY",
    ),
}


def test_spec_tables_have_expected_size() -> None:
    """Guard against silently dropping a builder during the refactor."""
    assert len(STATUS_LABEL_SPECS) == 16
    assert len(SUMMARY_SPECS) == 16


@pytest.mark.parametrize("builder_name", sorted(STATUS_LABEL_SPECS))
def test_status_label_known_statuses(builder_name: str) -> None:
    """Each known status maps to its exact label via the builder's own key."""
    builder = getattr(RE, builder_name)
    key, _default, labels = STATUS_LABEL_SPECS[builder_name]
    for status, expected in labels.items():
        assert builder({key: status}) == expected


@pytest.mark.parametrize("builder_name", sorted(STATUS_LABEL_SPECS))
def test_status_label_default_path(builder_name: str) -> None:
    """Missing key / non-mapping inputs fall back to the builder's default."""
    builder = getattr(RE, builder_name)
    key, default, labels = STATUS_LABEL_SPECS[builder_name]
    expected_default = labels[default]
    assert builder({}) == expected_default
    assert builder(None) == expected_default
    # A dict missing the builder's key (e.g. a sibling's key) also defaults.
    assert builder({"some_unrelated_key": "x"}) == expected_default


@pytest.mark.parametrize("builder_name", sorted(STATUS_LABEL_SPECS))
def test_status_label_unknown_status_title_cased(builder_name: str) -> None:
    """An unrecognized status is hyphen-split and title-cased."""
    builder = getattr(RE, builder_name)
    key, _default, _labels = STATUS_LABEL_SPECS[builder_name]
    assert builder({key: "zz-mystery-val"}) == "Zz Mystery Val"


@pytest.mark.parametrize("builder_name", sorted(STATUS_LABEL_SPECS))
def test_status_label_bare_string_routes_via_value(builder_name: str) -> None:
    """A bare string with no mapping is treated as the status itself."""
    builder = getattr(RE, builder_name)
    _key, _default, labels = STATUS_LABEL_SPECS[builder_name]
    # Pick a non-default known status so the value branch is observable.
    known = next((s for s in labels if s not in {"none", "unknown"}), None)
    assert known is not None
    assert builder(known) == labels[known]


@pytest.mark.parametrize("builder_name", sorted(SUMMARY_SPECS))
def test_summary_returns_value_when_present(builder_name: str) -> None:
    """A present, truthy value is returned verbatim (stringified)."""
    builder = getattr(RE, builder_name)
    key, _const_attr = SUMMARY_SPECS[builder_name]
    assert builder({key: "probe-value"}) == "probe-value"


@pytest.mark.parametrize("builder_name", sorted(SUMMARY_SPECS))
def test_summary_falls_back_to_constant(builder_name: str) -> None:
    """Missing / empty / non-mapping inputs fall back to the NO_* constant."""
    builder = getattr(RE, builder_name)
    key, const_attr = SUMMARY_SPECS[builder_name]
    expected = getattr(RE, const_attr)
    assert builder({}) == expected
    assert builder(None) == expected
    assert builder({key: ""}) == expected  # falsy value -> constant
    assert builder({"unrelated": "x"}) == expected
