from __future__ import annotations

from src.operator_trend_topline_payload import build_resolution_trend_topline_payload


def test_build_resolution_trend_topline_payload_packages_core_summary() -> None:
    payload = build_resolution_trend_topline_payload(
        trend_status="watch",
        new_attention_count=1,
        resolved_attention_count=2,
        persisting_attention_count=3,
        reopened_attention_count=4,
        history_window_runs=5,
        quiet_streak_runs=0,
        primary_target={"aging_status": "chronic"},
        primary_target_reason="reason",
        primary_target_done_criteria="done",
        closure_guidance="guide",
        current_attention={"a": {}},
        chronic_item_count=6,
        newly_stale_count=7,
        resolution_targets=[{"id": "x"}, {"id": "y"}],
        accountability_summary="acct",
        trend_summary="trend",
        recommendation_drift={
            "primary_target_exception_status": "exc",
            "primary_target_exception_reason": "why",
            "recommendation_drift_status": "drift",
            "recommendation_drift_summary": "summary",
            "policy_flip_hotspots": [{"label": "p"}],
        },
        exception_learning={
            "primary_target_exception_pattern_status": "pattern",
            "primary_target_exception_pattern_reason": "pattern-why",
            "primary_target_trust_recovery_status": "recover",
            "primary_target_trust_recovery_reason": "recover-why",
            "exception_pattern_summary": "eps",
            "false_positive_exception_hotspots": [],
            "trust_recovery_window_runs": 3,
        },
        exception_retirement={
            "primary_target_recovery_confidence_score": 0.5,
            "primary_target_recovery_confidence_label": "mid",
            "primary_target_recovery_confidence_reasons": ["a"],
            "recovery_confidence_summary": "rcs",
            "primary_target_exception_retirement_status": "retire",
            "primary_target_exception_retirement_reason": "retire-why",
            "exception_retirement_summary": "ers",
            "retired_exception_hotspots": [],
            "sticky_exception_hotspots": [],
            "exception_retirement_window_runs": 4,
        },
        class_normalization={
            "primary_target_policy_debt_status": "debt",
            "primary_target_policy_debt_reason": "debt-why",
            "primary_target_class_normalization_status": "norm",
            "primary_target_class_normalization_reason": "norm-why",
            "policy_debt_hotspots": [{"label": "d"}],
            "normalized_class_hotspots": [{"label": "n"}],
            "class_normalization_window_runs": 5,
        },
        class_memory_decay={
            "primary_target_class_memory_freshness_status": "fresh",
            "primary_target_class_memory_freshness_reason": "fresh-why",
            "primary_target_class_decay_status": "none",
            "primary_target_class_decay_reason": "",
            "class_memory_summary": "cms",
            "class_decay_summary": "cds",
            "stale_class_memory_hotspots": [],
            "fresh_class_signal_hotspots": [],
            "class_decay_window_runs": 6,
        },
        class_trust_reweighting={
            "primary_target_weighted_class_support_score": 1.0,
            "primary_target_weighted_class_caution_score": 0.2,
            "primary_target_class_trust_reweight_score": 0.8,
            "primary_target_class_trust_reweight_direction": "support",
            "primary_target_class_trust_reweight_reasons": ["r"],
            "class_reweighting_summary": "crs",
            "supporting_class_hotspots": [],
            "caution_class_hotspots": [],
            "class_reweighting_window_runs": 7,
        },
        attention_age_bands_fn=lambda current_attention: {"fresh": len(current_attention)},
        longest_persisting_item_fn=lambda resolution_targets: resolution_targets[0],
        policy_debt_summary_fn=lambda primary_target, hotspots: "pds",
        trust_normalization_summary_fn=lambda primary_target, normalized, debt: "tns",
    )

    assert payload["trend_status"] == "watch"
    assert payload["new_attention_count"] == 1
    assert payload["resolution_targets"] == [{"id": "x"}, {"id": "y"}]
    assert payload["policy_debt_summary"] == "pds"
    assert payload["class_reweighting_window_runs"] == 7
