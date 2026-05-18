from __future__ import annotations

import json

from src.scheduled_handoff import build_scheduled_handoff


def _control_center_payload(*, urgency: str = "urgent") -> dict:
    return {
        "username": "testuser",
        "generated_at": "2026-04-07T12:00:00+00:00",
        "report_reference": "output/audit-report-testuser-2026-04-07.json",
        "operator_summary": {
            "headline": "There is live drift or high-severity change that needs attention now.",
            "counts": {"blocked": 0, "urgent": 1, "ready": 0, "deferred": 0},
            "urgency": urgency,
            "escalation_reason": "drift-or-regression",
            "what_changed": "RepoC drift needs review — managed-issue-edited",
            "why_it_matters": "This has crossed into live drift, regression risk, or rollback exposure and should be reviewed before it spreads.",
            "what_to_do_next": "Inspect the managed issue before closing the campaign.",
            "trend_status": "stable",
            "trend_summary": "The queue is stable but still sticky: 1 attention item is persisting from the last run. Close RepoC: RepoC drift needs review next.",
            "new_attention_count": 0,
            "resolved_attention_count": 0,
            "persisting_attention_count": 1,
            "reopened_attention_count": 0,
            "quiet_streak_runs": 0,
            "aging_status": "watch",
            "primary_target_reason": "This urgent item is already being watched across recent runs, so it stays ahead of ready work until it clears.",
            "primary_target_done_criteria": "Inspect and reconcile the drift, then confirm this item no longer reappears on the next run.",
            "closure_guidance": "Inspect the managed issue before closing the campaign. Treat this as done only when inspect and reconcile the drift, then confirm this item no longer reappears on the next run.",
            "decision_memory_status": "attempted",
            "primary_target_last_intervention": {
                "item_id": "campaign-drift:repo-c",
                "repo": "RepoC",
                "title": "RepoC drift needs review",
                "event_type": "drifted",
                "recorded_at": "2026-04-07T12:00:00+00:00",
                "outcome": "drifted",
            },
            "primary_target_last_outcome": "no-change",
            "primary_target_resolution_evidence": "The last intervention was drifted for RepoC: RepoC drift needs review, but the item is still open.",
            "primary_target_confidence_score": 0.7,
            "primary_target_confidence_label": "medium",
            "primary_target_confidence_reasons": [
                "Urgent drift or regression needs attention before ready work.",
                "A prior intervention happened, but the item is still open.",
                "This item has repeated recently and is no longer brand new.",
            ],
            "recent_interventions": [
                {
                    "item_id": "campaign-drift:repo-c",
                    "repo": "RepoC",
                    "title": "RepoC drift needs review",
                    "event_type": "drifted",
                    "recorded_at": "2026-04-07T12:00:00+00:00",
                    "outcome": "drifted",
                }
            ],
            "recently_quieted_count": 0,
            "confirmed_resolved_count": 0,
            "reopened_after_resolution_count": 0,
            "decision_memory_window_runs": 3,
            "resolution_evidence_summary": "The last intervention was drifted for RepoC: RepoC drift needs review, but the item is still open.",
            "next_action_confidence_score": 0.75,
            "next_action_confidence_label": "high",
            "next_action_confidence_reasons": ["The next step is tied directly to the current top target."],
            "primary_target_trust_policy": "act-with-review",
            "primary_target_trust_policy_reason": "Urgent work has enough tuned confidence to act, with a quick operator review.",
            "next_action_trust_policy": "act-with-review",
            "next_action_trust_policy_reason": "Healthy calibration supports a confident next step, with light operator judgment.",
            "primary_target_exception_status": "none",
            "primary_target_exception_reason": "",
            "primary_target_exception_pattern_status": "candidate",
            "primary_target_exception_pattern_reason": "This target is stabilizing under healthy calibration, but it has not held steady long enough to earn stronger trust yet.",
            "primary_target_trust_recovery_status": "candidate",
            "primary_target_trust_recovery_reason": "This target is stabilizing under healthy calibration, but it has not held steady long enough to earn stronger trust yet.",
            "primary_target_recovery_confidence_score": 0.72,
            "primary_target_recovery_confidence_label": "medium",
            "primary_target_recovery_confidence_reasons": [
                "Healthy calibration supports relaxing the earlier soft caution.",
                "Recent runs are stabilizing, but the retirement window is still short.",
            ],
            "recovery_confidence_summary": "RepoC: RepoC drift needs review is building recovery confidence (medium, 0.72), but the earlier caution has not retired yet.",
            "primary_target_exception_retirement_status": "candidate",
            "primary_target_exception_retirement_reason": "This target is trending toward retirement, but it has not earned it yet.",
            "exception_retirement_summary": "RepoC: RepoC drift needs review is trending toward exception retirement, but the evidence is not strong enough to retire it yet.",
            "retired_exception_hotspots": [],
            "sticky_exception_hotspots": [],
            "exception_retirement_window_runs": 4,
            "primary_target_policy_debt_status": "watch",
            "primary_target_policy_debt_reason": "This class has enough recent exception activity to watch for lingering caution, but it is not yet clearly sticky or clearly normalization-friendly.",
            "primary_target_class_normalization_status": "candidate",
            "primary_target_class_normalization_reason": "This class is trending healthier, but the current target has not earned class-level normalization yet.",
            "policy_debt_summary": "RepoC: RepoC drift needs review sits in a class with mixed recent caution behavior, so watch for policy debt before normalizing further.",
            "trust_normalization_summary": "RepoC: RepoC drift needs review belongs to a healthier class trend, but it has not earned class-level normalization yet.",
            "policy_debt_hotspots": [],
            "normalized_class_hotspots": [],
            "class_normalization_window_runs": 4,
            "primary_target_class_memory_freshness_status": "mixed-age",
            "primary_target_class_memory_freshness_reason": "Class memory is still useful, but it is partly aging: 50% of the weighted signal is recent and the rest is older carry-forward.",
            "primary_target_class_decay_status": "none",
            "primary_target_class_decay_reason": "",
            "class_memory_summary": "RepoC: RepoC drift needs review still has useful class memory, but part of that signal is aging and should be treated more cautiously.",
            "class_decay_summary": "Fresh class signals are still strong enough that no class-level trust posture needs to decay yet.",
            "primary_target_weighted_class_support_score": 0.48,
            "primary_target_weighted_class_caution_score": 0.24,
            "primary_target_class_trust_reweight_score": 0.24,
            "primary_target_class_trust_reweight_direction": "supporting-normalization",
            "primary_target_class_trust_reweight_reasons": [
                "Class memory is still useful, but it is partly aging: 50% of the weighted signal is recent and the rest is older carry-forward.",
                "Existing class normalization support is still contributing to a stronger posture.",
                "Fresh sticky class evidence is still carrying meaningful caution.",
            ],
            "class_reweighting_summary": "RepoC: RepoC drift needs review inherited a stronger posture because fresh class support crossed the reweight threshold (0.24).",
            "supporting_class_hotspots": [],
            "caution_class_hotspots": [],
            "class_reweighting_window_runs": 4,
            "primary_target_class_trust_momentum_score": 0.26,
            "primary_target_class_trust_momentum_status": "building",
            "primary_target_class_reweight_stability_status": "watch",
            "primary_target_class_reweight_transition_status": "pending-support",
            "primary_target_class_reweight_transition_reason": "The class signal is visible, but it has not stayed strong long enough to confirm broader normalization yet.",
            "class_momentum_summary": "RepoC: RepoC drift needs review shows healthier class support, but it has not stayed persistent enough to confirm broader normalization yet (0.26).",
            "class_reweight_stability_summary": "Class guidance for RepoC: RepoC drift needs review is still settling and should be watched for one more stable stretch: supporting-normalization -> neutral.",
            "class_transition_window_runs": 4,
            "primary_target_class_transition_health_status": "building",
            "primary_target_class_transition_health_reason": "The pending class signal is still accumulating in the same direction and may confirm soon.",
            "primary_target_class_transition_resolution_status": "none",
            "primary_target_class_transition_resolution_reason": "",
            "class_transition_health_summary": "RepoC: RepoC drift needs review still has a pending class signal that is accumulating and may confirm soon (1 run(s)).",
            "class_transition_resolution_summary": "No pending class transition has just confirmed, cleared, or expired in the recent window.",
            "class_transition_age_window_runs": 4,
            "primary_target_transition_closure_confidence_score": 0.75,
            "primary_target_transition_closure_confidence_label": "high",
            "primary_target_transition_closure_likely_outcome": "confirm-soon",
            "primary_target_transition_closure_confidence_reasons": [
                "The pending class signal is still accumulating in the same direction and may confirm soon."
            ],
            "transition_closure_confidence_summary": "RepoC: RepoC drift needs review still has a pending class signal that looks strong enough to confirm soon if the next run stays aligned (0.75).",
            "transition_closure_window_runs": 4,
            "primary_target_class_pending_debt_status": "watch",
            "primary_target_class_pending_debt_reason": "This class has mixed recent pending-transition outcomes, so watch whether new pending signals resolve cleanly or start to accumulate debt.",
            "class_pending_debt_summary": "RepoC: RepoC drift needs review belongs to a class with mixed pending-transition outcomes, so watch whether new pending signals confirm or start to linger.",
            "class_pending_resolution_summary": "No class-level pending-resolution pattern is strong enough to call out yet.",
            "class_pending_debt_window_runs": 10,
            "pending_debt_hotspots": [],
            "healthy_pending_resolution_hotspots": [],
            "primary_target_pending_debt_freshness_status": "mixed-age",
            "primary_target_pending_debt_freshness_reason": "Pending-transition memory is still useful, but it is partly aging: 50% of the weighted signal is recent and the rest is older carry-forward.",
            "pending_debt_freshness_summary": "RepoC: RepoC drift needs review still has useful pending-transition memory, but some of that signal is aging and should be weighted more cautiously.",
            "pending_debt_decay_summary": "No strong pending-debt freshness trend is dominating the closure forecast yet.",
            "stale_pending_debt_hotspots": [],
            "fresh_pending_resolution_hotspots": [],
            "pending_debt_decay_window_runs": 4,
            "primary_target_weighted_pending_resolution_support_score": 0.58,
            "primary_target_weighted_pending_debt_caution_score": 0.31,
            "primary_target_closure_forecast_reweight_score": 0.27,
            "primary_target_closure_forecast_reweight_direction": "supporting-confirmation",
            "primary_target_closure_forecast_reweight_reasons": [
                "Pending-transition memory is still useful, but it is partly aging: 50% of the weighted signal is recent and the rest is older carry-forward.",
                "Recent class resolution behavior is still strong enough that this pending signal could confirm soon.",
                "The live pending signal is still building in the same direction.",
            ],
            "closure_forecast_reweighting_summary": "RepoC: RepoC drift needs review still needs persistence before confirmation, but fresh class resolution behavior is strengthening the pending forecast (0.27).",
            "closure_forecast_reweighting_window_runs": 4,
            "primary_target_closure_forecast_momentum_score": 0.18,
            "primary_target_closure_forecast_momentum_status": "building",
            "primary_target_closure_forecast_stability_status": "watch",
            "primary_target_closure_forecast_hysteresis_status": "pending-confirmation",
            "primary_target_closure_forecast_hysteresis_reason": "The confirmation-leaning forecast is visible, but it has not stayed persistent enough to trust fully yet.",
            "closure_forecast_momentum_summary": "The closure forecast for RepoC: RepoC drift needs review is trending in one direction, but it has not held long enough to lock in (0.18).",
            "closure_forecast_stability_summary": "Closure forecasting for RepoC: RepoC drift needs review is still settling and should be watched for one more stable stretch: supporting-confirmation -> neutral.",
            "closure_forecast_hysteresis_summary": "The confirmation-leaning forecast for RepoC: RepoC drift needs review is visible but not yet persistent enough to trust fully.",
            "primary_target_closure_forecast_freshness_status": "mixed-age",
            "primary_target_closure_forecast_freshness_reason": "Closure-forecast memory is still useful, but it is partly aging: 50% of the weighted forecast signal is recent and the rest is older carry-forward.",
            "primary_target_closure_forecast_decay_status": "none",
            "primary_target_closure_forecast_decay_reason": "",
            "closure_forecast_freshness_summary": "RepoC: RepoC drift needs review still has useful closure-forecast memory, but some of that signal is aging and should be weighted more cautiously.",
            "closure_forecast_decay_summary": "Recent closure-forecast evidence is still fresh enough that no forecast carry-forward needs to decay yet.",
            "primary_target_closure_forecast_refresh_recovery_score": 0.16,
            "primary_target_closure_forecast_refresh_recovery_status": "recovering-confirmation",
            "primary_target_closure_forecast_reacquisition_status": "pending-confirmation-reacquisition",
            "primary_target_closure_forecast_reacquisition_reason": "Fresh confirmation-side forecast evidence is returning, but it has not fully re-earned stronger carry-forward yet.",
            "closure_forecast_refresh_recovery_summary": "Fresh confirmation-side forecast evidence is returning for RepoC: RepoC drift needs review, but it has not fully re-earned stronger carry-forward yet (0.16).",
            "closure_forecast_reacquisition_summary": "Fresh confirmation-side forecast evidence is returning, but it has not fully re-earned stronger carry-forward yet.",
            "primary_target_closure_forecast_reacquisition_age_runs": 1,
            "primary_target_closure_forecast_reacquisition_persistence_score": 0.19,
            "primary_target_closure_forecast_reacquisition_persistence_status": "just-reacquired",
            "primary_target_closure_forecast_reacquisition_persistence_reason": "Stronger closure-forecast posture has returned, but it has not yet proved it can hold.",
            "closure_forecast_reacquisition_persistence_summary": "RepoC: RepoC drift needs review has only just re-earned stronger closure-forecast posture, so it is still fragile (0.19; 1 run).",
            "primary_target_closure_forecast_recovery_churn_score": 0.22,
            "primary_target_closure_forecast_recovery_churn_status": "watch",
            "primary_target_closure_forecast_recovery_churn_reason": "Recovery is wobbling and may lose its restored strength soon.",
            "closure_forecast_recovery_churn_summary": "Recovery for RepoC: RepoC drift needs review is wobbling enough that restored forecast strength may soften soon (0.22).",
            "primary_target_closure_forecast_reacquisition_freshness_status": "mixed-age",
            "primary_target_closure_forecast_reacquisition_freshness_reason": "Reacquired closure-forecast memory is still useful, but it is partly aging: 50% of the weighted signal is recent and the rest is older carry-forward.",
            "closure_forecast_reacquisition_freshness_summary": "RepoC: RepoC drift needs review still has useful reacquired closure-forecast memory, but the restored posture is no longer getting fully fresh reinforcement.",
            "primary_target_closure_forecast_persistence_reset_status": "none",
            "primary_target_closure_forecast_persistence_reset_reason": "",
            "closure_forecast_persistence_reset_summary": "Reacquired posture for RepoC: RepoC drift needs review is aging enough that it can keep holding, but it should no longer stay indefinitely at sustained strength.",
            "primary_target_closure_forecast_reset_refresh_recovery_score": 0.18,
            "primary_target_closure_forecast_reset_refresh_recovery_status": "recovering-confirmation-reset",
            "primary_target_closure_forecast_reset_reentry_status": "pending-confirmation-reentry",
            "primary_target_closure_forecast_reset_reentry_reason": "Fresh confirmation-side evidence is returning after a reset, but it has not yet re-earned re-entry.",
            "closure_forecast_reset_refresh_recovery_summary": "Fresh confirmation-side evidence is returning for RepoC: RepoC drift needs review after a reset, but it has not yet re-earned re-entry (0.18).",
            "closure_forecast_reset_reentry_summary": "Fresh confirmation-side evidence is returning after a reset, but it has not yet re-earned re-entry.",
            "primary_target_closure_forecast_reset_reentry_age_runs": 1,
            "primary_target_closure_forecast_reset_reentry_persistence_score": 0.24,
            "primary_target_closure_forecast_reset_reentry_persistence_status": "just-reentered",
            "primary_target_closure_forecast_reset_reentry_persistence_reason": "Stronger closure-forecast posture has re-entered after reset, but it has not yet proved it can hold.",
            "closure_forecast_reset_reentry_persistence_summary": "RepoC: RepoC drift needs review has only just re-entered stronger closure-forecast posture after reset, so it is still fragile (0.24; 1 run).",
            "primary_target_closure_forecast_reset_reentry_churn_score": 0.18,
            "primary_target_closure_forecast_reset_reentry_churn_status": "none",
            "primary_target_closure_forecast_reset_reentry_churn_reason": "",
            "closure_forecast_reset_reentry_churn_summary": "No meaningful reset re-entry churn is active right now.",
            "primary_target_closure_forecast_reset_reentry_freshness_status": "mixed-age",
            "primary_target_closure_forecast_reset_reentry_freshness_reason": "Reset re-entry memory is still useful, but it is partly aging: 50% of the weighted signal is recent and the rest is older carry-forward.",
            "closure_forecast_reset_reentry_freshness_summary": "RepoC: RepoC drift needs review still has useful reset re-entry memory, but the restored posture is no longer getting fully fresh reinforcement.",
            "primary_target_closure_forecast_reset_reentry_reset_status": "none",
            "primary_target_closure_forecast_reset_reentry_reset_reason": "",
            "closure_forecast_reset_reentry_reset_summary": "Reset re-entry posture for RepoC: RepoC drift needs review is aging enough that it can keep holding, but it should no longer stay indefinitely at sustained strength.",
            "primary_target_closure_forecast_reset_reentry_refresh_recovery_score": 0.31,
            "primary_target_closure_forecast_reset_reentry_refresh_recovery_status": "rebuilding-confirmation-reentry",
            "primary_target_closure_forecast_reset_reentry_rebuild_status": "pending-confirmation-rebuild",
            "primary_target_closure_forecast_reset_reentry_rebuild_reason": "Fresh confirmation-side evidence is rebuilding after the reset re-entry aged out, but it has not yet fully re-earned stronger posture.",
            "closure_forecast_reset_reentry_refresh_recovery_summary": "Fresh confirmation-side evidence is rebuilding for RepoC: RepoC drift needs review after reset re-entry aged out (0.31).",
            "closure_forecast_reset_reentry_rebuild_summary": "RepoC: RepoC drift needs review is rebuilding confirmation-side reset re-entry, but it has not fully re-earned stronger posture yet.",
            "primary_target_closure_forecast_reset_reentry_rebuild_freshness_status": "mixed-age",
            "primary_target_closure_forecast_reset_reentry_rebuild_freshness_reason": "Rebuilt reset re-entry memory is still useful, but it is partly aging: 50% of the weighted signal is recent and the rest is older carry-forward.",
            "closure_forecast_reset_reentry_rebuild_freshness_summary": "RepoC: RepoC drift needs review still has useful rebuilt reset re-entry memory, but the restored posture is no longer getting fully fresh reinforcement.",
            "primary_target_closure_forecast_reset_reentry_rebuild_reset_status": "none",
            "primary_target_closure_forecast_reset_reentry_rebuild_reset_reason": "",
            "closure_forecast_reset_reentry_rebuild_reset_summary": "Rebuilt posture for RepoC: RepoC drift needs review is aging enough that it can keep holding, but it should no longer stay indefinitely at sustained strength.",
            "primary_target_closure_forecast_reset_reentry_rebuild_refresh_recovery_score": 0.27,
            "primary_target_closure_forecast_reset_reentry_rebuild_refresh_recovery_status": "recovering-confirmation-rebuild-reset",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_status": "pending-confirmation-rebuild-reentry",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_reason": "Fresh confirmation-side evidence is returning after rebuilt posture was softened or reset, but it has not yet re-earned stronger rebuilt posture.",
            "closure_forecast_reset_reentry_rebuild_refresh_recovery_summary": "Fresh confirmation-side evidence is returning for RepoC: RepoC drift needs review after rebuilt posture softened, but it has not yet re-earned stronger rebuilt posture (0.27).",
            "closure_forecast_reset_reentry_rebuild_reentry_summary": "RepoC: RepoC drift needs review is recovering after rebuilt posture softened, but stronger rebuilt confirmation posture still needs more fresh follow-through before it is re-earned.",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_age_runs": 1,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_score": 0.26,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_status": "just-reentered",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_reason": "Stronger rebuilt posture has been re-earned, but it has not yet proved it can hold.",
            "closure_forecast_reset_reentry_rebuild_reentry_persistence_summary": "RepoC: RepoC drift needs review has only just re-earned stronger rebuilt posture, so it is still fragile (0.26; 1 run).",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_score": 0.0,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_status": "none",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_reason": "",
            "closure_forecast_reset_reentry_rebuild_reentry_churn_summary": "No meaningful rebuilt re-entry churn is active right now.",
            "primary_target_closure_forecast_reset_reentry_rebuild_age_runs": 1,
            "primary_target_closure_forecast_reset_reentry_rebuild_persistence_score": 0.29,
            "primary_target_closure_forecast_reset_reentry_rebuild_persistence_status": "just-rebuilt",
            "primary_target_closure_forecast_reset_reentry_rebuild_persistence_reason": "Stronger reset re-entry posture has been rebuilt, but it has not yet proved it can hold.",
            "closure_forecast_reset_reentry_rebuild_persistence_summary": "RepoC: RepoC drift needs review has only just rebuilt stronger reset re-entry posture, so it is still fragile (0.29; 1 run).",
            "primary_target_closure_forecast_reset_reentry_rebuild_churn_score": 0.14,
            "primary_target_closure_forecast_reset_reentry_rebuild_churn_status": "none",
            "primary_target_closure_forecast_reset_reentry_rebuild_churn_reason": "",
            "closure_forecast_reset_reentry_rebuild_churn_summary": "No meaningful reset re-entry rebuild churn is active right now.",
            "just_rebuilt_hotspots": [],
            "just_reentered_rebuild_hotspots": [],
            "holding_reset_reentry_rebuild_hotspots": [],
            "holding_reset_reentry_rebuild_reentry_hotspots": [],
            "reset_reentry_rebuild_churn_hotspots": [],
            "reset_reentry_rebuild_reentry_churn_hotspots": [],
            "stale_reset_reentry_rebuild_hotspots": [],
            "fresh_reset_reentry_rebuild_signal_hotspots": [],
            "recovering_from_confirmation_rebuild_reset_hotspots": [],
            "recovering_from_clearance_rebuild_reset_hotspots": [],
            "stale_reset_reentry_hotspots": [],
            "fresh_reset_reentry_signal_hotspots": [],
            "closure_forecast_reset_reentry_decay_window_runs": 4,
            "closure_forecast_reset_reentry_refresh_window_runs": 4,
            "closure_forecast_reset_reentry_rebuild_window_runs": 4,
            "closure_forecast_reset_reentry_rebuild_decay_window_runs": 4,
            "closure_forecast_reset_reentry_rebuild_refresh_window_runs": 4,
            "stale_closure_forecast_hotspots": [],
            "fresh_closure_forecast_signal_hotspots": [],
            "closure_forecast_decay_window_runs": 4,
            "closure_forecast_refresh_window_runs": 4,
            "closure_forecast_reacquisition_window_runs": 4,
            "closure_forecast_reacquisition_decay_window_runs": 4,
            "closure_forecast_transition_window_runs": 4,
            "sustained_confirmation_hotspots": [],
            "sustained_clearance_hotspots": [],
            "oscillating_closure_forecast_hotspots": [],
            "recovering_confirmation_hotspots": [],
            "recovering_clearance_hotspots": [],
            "just_reacquired_hotspots": [],
            "holding_reacquisition_hotspots": [],
            "recovery_churn_hotspots": [],
            "stale_reacquisition_hotspots": [],
            "fresh_reacquisition_signal_hotspots": [],
            "just_reentered_hotspots": [],
            "holding_reset_reentry_hotspots": [],
            "reset_reentry_churn_hotspots": [],
            "recovering_from_confirmation_reentry_reset_hotspots": [],
            "recovering_from_clearance_reentry_reset_hotspots": [],
            "supporting_pending_resolution_hotspots": [],
            "caution_pending_debt_hotspots": [],
            "stalled_transition_hotspots": [],
            "resolving_transition_hotspots": [],
            "sustained_class_hotspots": [],
            "oscillating_class_hotspots": [],
            "stale_class_memory_hotspots": [],
            "fresh_class_signal_hotspots": [],
            "class_decay_window_runs": 4,
            "recommendation_drift_status": "stable",
            "recommendation_drift_summary": "Recent trust-policy behavior is stable enough that no meaningful recommendation drift is recorded.",
            "policy_flip_hotspots": [],
            "exception_pattern_summary": "RepoC: RepoC drift needs review is stabilizing, but it has not yet earned stronger trust.",
            "false_positive_exception_hotspots": [],
            "trust_recovery_window_runs": 3,
            "adaptive_confidence_summary": "Calibration is validating well, so the recommendation can be acted on with light operator review.",
            "recommendation_quality_summary": "Strong recommendation because the next step is tied directly to the current top target.",
            "confidence_validation_status": "healthy",
            "confidence_window_runs": 8,
            "validated_recommendation_count": 4,
            "partially_validated_recommendation_count": 1,
            "unresolved_recommendation_count": 1,
            "reopened_recommendation_count": 0,
            "insufficient_future_runs_count": 2,
            "high_confidence_hit_rate": 0.75,
            "medium_confidence_hit_rate": 0.5,
            "low_confidence_caution_rate": 1.0,
            "recent_validation_outcomes": [
                {
                    "run_id": "testuser:2026-04-05T12:00:00+00:00",
                    "target_label": "RepoC: RepoC drift needs review",
                    "confidence_label": "high",
                    "outcome": "validated",
                    "validated_in_runs": 2,
                }
            ],
            "confidence_calibration_summary": "Recent high-confidence recommendations are validating well: 75% high-confidence hit rate across 6 judged runs with no reopen noise.",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_score": 0.32,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status": "recovering-confirmation-rebuild-reentry-rererestore-reset",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status": "pending-confirmation-rebuild-reentry-rerererestore",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_reason": "Fresh confirmation-side evidence is returning after stronger re-re-restored posture softened or reset, but it has not yet re-re-re-restored stronger posture.",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_summary": "Fresh confirmation-side evidence is returning for RepoC: RepoC drift needs review after stronger re-re-restored posture softened, but it has not yet re-re-re-restored stronger posture (0.32).",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_summary": "RepoC: RepoC drift needs review is recovering after stronger re-re-restored posture softened, but it still needs more fresh follow-through before it is re-re-re-restored.",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_window_runs": 4,
            "recovering_from_confirmation_rebuild_reentry_rererestore_reset_hotspots": [],
            "recovering_from_clearance_rebuild_reentry_rererestore_reset_hotspots": [],
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs": 1,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score": 0.24,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status": "just-rerererestored",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_reason": "Stronger re-re-restored rebuilt re-entry posture has been re-re-re-restored, but it has not yet proved it can hold.",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_summary": "RepoC: RepoC drift needs review has only just re-re-re-restored stronger re-re-restored posture, so it is still fragile (0.24; 1 run).",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_window_runs": 4,
            "just_rerererestored_rebuild_reentry_hotspots": [],
            "holding_reset_reentry_rebuild_reentry_restore_rerererestore_hotspots": [],
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score": 0.21,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status": "watch",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason": "Re-re-re-restored rebuilt re-entry is wobbling and may lose its stronger re-re-restored posture soon.",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_summary": "Re-re-re-restored rebuilt re-entry for RepoC: RepoC drift needs review is wobbling enough that stronger re-re-restored posture may soften soon (0.21).",
            "reset_reentry_rebuild_reentry_restore_rerererestore_churn_hotspots": [],
            "chronic_item_count": 0,
            "newly_stale_count": 0,
            "longest_persisting_item": {
                "repo": "RepoC",
                "title": "RepoC drift needs review",
                "age_days": 4,
                "aging_status": "watch",
            },
            "attention_age_bands": {"0-1 days": 0, "2-7 days": 1, "8-21 days": 0, "22+ days": 0},
            "accountability_summary": "This urgent item is already being watched across recent runs, so it stays ahead of ready work until it clears. Aging pressure: 0 chronic item(s) and 0 newly stale item(s).",
            "primary_target": {
                "item_id": "campaign-drift:repo-c",
                "repo": "RepoC",
                "title": "RepoC drift needs review",
                "recommended_action": "Inspect the managed issue before closing the campaign.",
                "policy_flip_count": 0,
                "recent_policy_path": "",
                "trust_recovery_status": "candidate",
                "trust_recovery_reason": "This target is stabilizing under healthy calibration, but it has not held steady long enough to earn stronger trust yet.",
                "exception_pattern_status": "recovering",
                "exception_pattern_reason": "This target is stabilizing under healthy calibration, but it has not held steady long enough to earn stronger trust yet.",
                "class_retirement_rate": 0.50,
                "class_sticky_rate": 0.25,
                "class_transition_age_runs": 1,
                "recent_transition_path": "pending-support",
                "recent_closure_forecast_path": "supporting-confirmation -> neutral",
                "recent_closure_forecast_refresh_path": "stale confirmation -> fresh confirmation",
                "recent_reacquisition_persistence_path": "reacquired-confirmation -> hold",
                "recent_recovery_churn_path": "reacquired-confirmation -> hold",
            },
            "next_recommended_run_mode": "incremental",
            "watch_strategy": "adaptive",
            "watch_decision_summary": "The current baseline is still compatible, so incremental watch remains safe for the next run.",
        },
        "operator_queue": [
            {
                "lane": "urgent",
                "lane_label": "Needs Attention Now",
                "repo": "RepoC",
                "title": "RepoC drift needs review",
                "summary": "managed-issue-edited",
                "recommended_action": "Inspect the managed issue before closing the campaign.",
            }
        ],
        "operator_recent_changes": [
            {"generated_at": "2026-04-07T12:00:00+00:00", "repo": "RepoC", "summary": "managed-issue-edited"}
        ],
    }


def test_build_scheduled_handoff_writes_artifacts_and_issue_candidate(tmp_path):
    (tmp_path / "operator-control-center-testuser-2026-04-07.json").write_text(
        json.dumps(_control_center_payload())
    )

    payload = build_scheduled_handoff(tmp_path)

    assert payload["status"] == "ok"
    assert payload["issue_candidate"]["should_open"] is True
    assert payload["issue_candidate"]["action"] == "open"
    assert payload["issue_candidate"]["title"] == "Scheduled Audit Handoff: testuser"
    assert (tmp_path / "scheduled-handoff-testuser-2026-04-07.md").is_file()
    assert (tmp_path / "scheduled-handoff-testuser-2026-04-07.json").is_file()
    markdown = (tmp_path / "scheduled-handoff-testuser-2026-04-07.md").read_text()
    assert "What Got Better" in markdown
    assert "What Needs Attention Now" in markdown
    assert "Primary target: RepoC: RepoC drift needs review" in markdown
    assert "What We Tried" in markdown
    assert "Why This Is Still Open" in markdown
    assert "What Counts As Done" in markdown
    assert "Resolution Evidence" in markdown
    assert "Recommendation Confidence" in markdown
    assert "Primary target confidence: medium (0.70)" in markdown
    assert "Operator Trust Policy" in markdown
    assert "act-with-review" in markdown
    assert "Trust Policy Exception" in markdown
    assert "Exception Pattern Learning" in markdown
    assert "Trust Recovery" in markdown
    assert "Recovery Confidence" in markdown
    assert "Exception Retirement" in markdown
    assert "Policy Debt Cleanup" in markdown
    assert "Class-Level Trust Normalization" in markdown
    assert "Class Memory Freshness" in markdown
    assert "Trust Decay Controls" in markdown
    assert "Class Trust Reweighting" in markdown
    assert "Class Trust Momentum" in markdown
    assert "Reweighting Stability" in markdown
    assert "Class Transition Health" in markdown
    assert "Pending Transition Resolution" in markdown
    assert "Transition Closure Confidence" in markdown
    assert "Class Pending Debt Audit" in markdown
    assert "Pending Debt Freshness" in markdown
    assert "Closure Forecast Reweighting" in markdown
    assert "Closure Forecast Momentum" in markdown
    assert "Closure Forecast Hysteresis" in markdown
    assert "Closure Forecast Freshness" in markdown
    assert "Hysteresis Decay Controls" in markdown
    assert "Closure Forecast Refresh Recovery" in markdown
    assert "Reacquisition Controls" in markdown
    assert "Reset Re-entry Persistence" in markdown
    assert "Reset Re-entry Churn Controls" in markdown
    assert "Reset Re-entry Freshness" in markdown
    assert "Reset Re-entry Reset Controls" in markdown
    assert "Reset Re-entry Refresh Recovery" in markdown
    assert "Reset Re-entry Rebuild Controls" in markdown
    assert "Reset Re-entry Rebuild Freshness" in markdown
    assert "Reset Re-entry Rebuild Reset Controls" in markdown
    assert "Reset Re-entry Rebuild Refresh Recovery" in markdown
    assert "Reset Re-entry Rebuild Re-entry Controls" in markdown
    assert "Reset Re-entry Rebuild Re-Entry Persistence" in markdown
    assert "Reset Re-entry Rebuild Re-Entry Churn Controls" in markdown
    assert "Reset Re-entry Rebuild Re-Entry Freshness" in markdown
    assert "Reset Re-entry Rebuild Re-Entry Reset Controls" in markdown
    assert "Reset Re-entry Rebuild Re-Entry Refresh Recovery" in markdown
    assert "Reset Re-entry Rebuild Re-Entry Restore Controls" in markdown
    assert "Reset Re-entry Rebuild Re-Entry Restore Freshness" in markdown
    assert "Reset Re-entry Rebuild Re-Entry Restore Reset Controls" in markdown
    assert "Reset Re-entry Rebuild Re-Entry Restore Refresh Recovery" in markdown
    assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Controls" in markdown
    assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Persistence" in markdown
    assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Churn Controls" in markdown
    assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Freshness" in markdown
    assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Reset Controls" in markdown
    assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Refresh Recovery" in markdown
    assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Controls" in markdown
    assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Persistence" in markdown
    assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Churn Controls" in markdown
    assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Freshness" in markdown
    assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Reset Controls" in markdown
    assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Refresh Recovery" in markdown
    assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Controls" in markdown
    assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Persistence" in markdown
    assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Churn Controls" in markdown
    assert "Reset Re-entry Rebuild Persistence" in markdown
    assert "Reset Re-entry Rebuild Churn Controls" in markdown
    assert "Reacquisition Persistence" in markdown
    assert "Recovery Churn Controls" in markdown
    assert "Reacquisition Freshness" in markdown
    assert "Persistence Reset Controls" in markdown
    assert "Reset Refresh Recovery" in markdown
    assert "Reset Re-entry Controls" in markdown
    assert "Reset Re-entry Freshness" in markdown
    assert "Reset Re-entry Reset Controls" in markdown
    assert "Reset Re-entry Refresh Recovery" in markdown
    assert "Reset Re-entry Rebuild Controls" in markdown
    assert "Reset Re-entry Rebuild Persistence" in markdown
    assert "Reset Re-entry Rebuild Churn Controls" in markdown
    assert "Why class guidance shifted" in markdown
    assert "Recommendation Drift" in markdown
    assert "Confidence Validation" in markdown
    assert "75%" in markdown
    assert "Aging Pressure" in markdown
    assert "What Reopened" in markdown


def test_build_scheduled_handoff_includes_github_projects_campaign_status(tmp_path):
    payload = _control_center_payload()
    payload["operator_summary"]["action_sync_summary"] = {
        "summary": "Action Sync is preview-ready: Security Review is the strongest next campaign to preview from the current local facts.",
    }
    payload["operator_summary"]["next_action_sync_step"] = "Preview Security Review next, then decide whether it is ready to sync to all."
    payload["operator_summary"]["apply_readiness_summary"] = {
        "summary": "Apply handoff says preview Security Review next before deciding on apply to all."
    }
    payload["operator_summary"]["next_apply_candidate"] = {
        "summary": "Preview Security Review next, then decide whether it is ready to apply to all.",
        "preview_command": "audit testuser --campaign security-review --writeback-target all",
    }
    payload["operator_summary"]["campaign_outcomes_summary"] = {
        "summary": "Security Review was applied recently; monitor it now before treating it as stable.",
    }
    payload["operator_summary"]["next_monitoring_step"] = {
        "summary": "Monitor Security Review for at least 2 post-apply runs before treating it as stable.",
    }
    payload["operator_summary"]["campaign_tuning_summary"] = {
        "summary": "Security Review should win ties because recent outcomes are proven.",
    }
    payload["operator_summary"]["next_tuned_campaign"] = {
        "summary": "Security Review should win ties inside the preview-ready group because recent outcome history is proven.",
    }
    payload["operator_summary"]["intervention_ledger_summary"] = {
        "summary": "RepoC is improving after intervention while RepoD still looks relapsing.",
    }
    payload["operator_summary"]["next_historical_focus"] = {
        "summary": "Read RepoC next: it is the clearest current example of improvement after intervention.",
    }
    payload["operator_summary"]["automation_guidance_summary"] = {
        "summary": "Preview Security Review next; that is the strongest safe automation step right now.",
    }
    payload["operator_summary"]["next_safe_automation_step"] = {
        "summary": "Preview Security Review next; that is the strongest safe automation step right now.",
        "recommended_command": "audit testuser --campaign security-review --writeback-target all",
    }
    payload["campaign_summary"] = {
        "campaign_type": "security-review",
        "label": "Security Review",
        "action_count": 2,
        "repo_count": 2,
    }
    payload["writeback_preview"] = {
        "sync_mode": "reconcile",
        "github_projects": {
            "enabled": True,
            "status": "configured",
            "project_owner": "octo-org",
            "project_number": 7,
            "item_count": 2,
        },
    }
    payload["managed_state_drift"] = [
        {
            "action_id": "campaign-1",
            "repo_full_name": "user/RepoD",
            "target": "github-project-item",
            "drift_state": "managed-project-item-missing",
        }
    ]
    (tmp_path / "operator-control-center-testuser-2026-04-07.json").write_text(json.dumps(payload))

    build_scheduled_handoff(tmp_path)

    markdown = (tmp_path / "scheduled-handoff-testuser-2026-04-07.md").read_text()
    assert "Campaign mirror: Security Review" in markdown
    assert "GitHub Projects: configured (octo-org #7, 2 items, 1 project drift)" in markdown
    assert "Action Sync readiness: Action Sync is preview-ready" in markdown
    assert "Next Action Sync step: Preview Security Review next" in markdown
    assert "Apply packet: Apply handoff says preview Security Review next" in markdown
    assert "Action Sync command hint: audit testuser --campaign security-review --writeback-target all" in markdown
    assert "Post-apply monitoring: Security Review was applied recently" in markdown
    assert "Next monitoring step: Monitor Security Review for at least 2 post-apply runs" in markdown
    assert "Campaign tuning: Security Review should win ties because recent outcomes are proven." in markdown
    assert "Next Tie-Break Candidate: Security Review should win ties inside the preview-ready group" in markdown
    assert "Historical portfolio intelligence: RepoC is improving after intervention while RepoD still looks relapsing." in markdown
    assert "Next historical focus: Read RepoC next: it is the clearest current example of improvement after intervention." in markdown
    assert "Automation Guidance: Preview Security Review next; that is the strongest safe automation step right now." in markdown
    assert "Next safe automation step: Preview Security Review next; that is the strongest safe automation step right now." in markdown
    assert "Safe automation command: audit testuser --campaign security-review --writeback-target all" in markdown


def test_build_scheduled_handoff_stays_quiet_for_quiet_runs(tmp_path):
    payload = _control_center_payload(urgency="quiet")
    payload["operator_summary"]["headline"] = "No operator triage items are currently surfaced."
    payload["operator_summary"]["what_changed"] = "No new blocking or urgent drift is surfaced in the latest operator snapshot."
    payload["operator_summary"]["why_it_matters"] = "The latest run is quiet enough that no immediate operator intervention is required."
    payload["operator_summary"]["what_to_do_next"] = "Continue the normal audit/control-center loop and review the next artifact for change."
    payload["operator_summary"]["counts"] = {"blocked": 0, "urgent": 0, "ready": 0, "deferred": 0}
    payload["operator_summary"]["trend_status"] = "quiet"
    payload["operator_summary"]["trend_summary"] = "The queue is quiet and has stayed that way for 2 consecutive run(s)."
    payload["operator_summary"]["quiet_streak_runs"] = 2
    payload["operator_summary"]["resolved_attention_count"] = 1
    payload["operator_summary"]["persisting_attention_count"] = 0
    payload["operator_queue"] = []
    payload["operator_recent_changes"] = []
    (tmp_path / "operator-control-center-testuser-2026-04-07.json").write_text(json.dumps(payload))

    result = build_scheduled_handoff(tmp_path)

    assert result["issue_candidate"]["should_open"] is False
    assert result["issue_candidate"]["action"] == "quiet"
    markdown = (tmp_path / "scheduled-handoff-testuser-2026-04-07.md").read_text()
    assert "Issue automation: `quiet`" in markdown
    assert "2 consecutive run(s)" in markdown


def test_build_scheduled_handoff_closes_open_issue_when_run_turns_quiet(tmp_path):
    payload = _control_center_payload(urgency="quiet")
    payload["operator_summary"]["headline"] = "No operator triage items are currently surfaced."
    payload["operator_summary"]["counts"] = {"blocked": 0, "urgent": 0, "ready": 0, "deferred": 0}
    payload["operator_summary"]["what_changed"] = "No new blocking or urgent drift is surfaced in the latest operator snapshot."
    payload["operator_summary"]["why_it_matters"] = "The latest run is quiet enough that no immediate operator intervention is required."
    payload["operator_summary"]["what_to_do_next"] = "Continue the normal audit/control-center loop and review the next artifact for change."
    payload["operator_queue"] = []
    (tmp_path / "operator-control-center-testuser-2026-04-07.json").write_text(json.dumps(payload))

    result = build_scheduled_handoff(tmp_path, issue_state="open", issue_number="42", issue_url="https://example.com/42")

    assert result["issue_candidate"]["action"] == "close"
    assert result["issue_candidate"]["close_reason"] == "quiet-recovery"
    assert result["issue_candidate"]["issue_number"] == "42"


def test_build_scheduled_handoff_reopens_closed_canonical_issue_for_new_noise(tmp_path):
    (tmp_path / "operator-control-center-testuser-2026-04-07.json").write_text(
        json.dumps(_control_center_payload())
    )

    result = build_scheduled_handoff(tmp_path, issue_state="closed", issue_number="42", issue_url="https://example.com/42")

    assert result["issue_candidate"]["action"] == "update"
    assert result["issue_candidate"]["reopen_existing"] is True
