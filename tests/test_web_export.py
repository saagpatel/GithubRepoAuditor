from __future__ import annotations

from src.report_enrichment import (
    build_queue_pressure_summary,
    build_top_recommendation_summary,
    no_baseline_summary,
    no_linked_artifact_summary,
)
from src.web_export import _render_html, export_html_dashboard


def _make_report(**overrides) -> dict:
    defaults = {
        "username": "testuser",
        "generated_at": "2026-03-29T12:00:00Z",
        "repos_audited": 3,
        "average_score": 0.60,
        "portfolio_grade": "C",
        "portfolio_health_score": 0.65,
        "tier_distribution": {"shipped": 1, "functional": 1, "wip": 1},
        "language_distribution": {"Python": 2, "Rust": 1},
        "lenses": {
            "ship_readiness": {"average_score": 0.72, "description": "Delivery readiness"},
            "showcase_value": {"average_score": 0.63, "description": "Story and polish"},
        },
        "collections": {
            "showcase": {
                "description": "Best examples",
                "repos": [{"name": "RepoA", "reason": "Strong showcase"}],
            }
        },
        "profiles": {
            "default": {
                "description": "Balanced",
                "lens_weights": {
                    "ship_readiness": 0.4,
                    "showcase_value": 0.3,
                    "security_posture": 0.3,
                },
            }
        },
        "scenario_summary": {
            "top_levers": [
                {
                    "key": "testing",
                    "title": "Strengthen tests",
                    "lens": "ship_readiness",
                    "repo_count": 2,
                    "average_expected_lens_delta": 0.11,
                    "projected_tier_promotions": 1,
                }
            ],
            "portfolio_projection": {
                "selected_repo_count": 3,
                "projected_average_score_delta": 0.04,
                "projected_tier_promotions": 1,
            },
        },
        "security_posture": {
            "average_score": 0.61,
            "critical_repos": ["RepoC"],
            "repos_with_secrets": [],
            "provider_coverage": {
                "github": {"available_repos": 2, "total_repos": 3},
                "scorecard": {"available_repos": 1, "total_repos": 3},
            },
            "open_alerts": {"code_scanning": 2, "secret_scanning": 1},
        },
        "security_governance_preview": [
            {
                "repo": "RepoC",
                "priority": "high",
                "title": "Enable CodeQL default setup",
                "expected_posture_lift": 0.12,
                "source": "github",
            }
        ],
        "writeback_preview": {"sync_mode": "reconcile"},
        "campaign_summary": {"campaign_type": "security-review", "label": "Security Review", "action_count": 1, "repo_count": 1},
        "writeback_results": {"mode": "apply", "target": "github", "results": [{"repo_full_name": "user/RepoC", "target": "github-issue", "status": "created"}]},
        "managed_state_drift": [{"repo_full_name": "user/RepoC", "target": "github-issue", "drift_state": "managed-issue-edited"}],
        "governance_results": {"results": [{"repo_full_name": "user/RepoC", "status": "applied"}]},
        "governance_approval": {"status": "approved"},
        "governance_drift": [{"repo_full_name": "user/RepoC", "drift_type": "already-enabled"}],
        "governance_summary": {
            "headline": "Governed control drift needs operator review.",
            "status": "drifted",
            "needs_reapproval": False,
            "drift_count": 1,
            "applyable_count": 1,
            "applied_count": 1,
            "rollback_available_count": 1,
            "top_actions": [
                {
                    "repo": "RepoC",
                    "title": "Enable CodeQL default setup",
                    "operator_state": "ready",
                    "expected_posture_lift": 0.12,
                    "source": "github",
                }
            ],
        },
        "operator_summary": {
            "headline": "There is live drift or high-severity change that needs attention now.",
            "counts": {"blocked": 0, "urgent": 2, "ready": 1, "deferred": 1},
            "watch_strategy": "adaptive",
            "next_recommended_run_mode": "incremental",
            "watch_decision_summary": "The current baseline is still compatible, so incremental watch remains safe for the next run.",
            "what_changed": "RepoC drift needs review — managed-issue-edited",
            "why_it_matters": "This has crossed into live drift, regression risk, or rollback exposure and should be reviewed before it spreads.",
            "what_to_do_next": "Inspect the managed issue before closing the campaign.",
            "trend_summary": "The queue is stable but still sticky: 1 attention item is persisting from the last run.",
            "follow_through_summary": "1 urgent item repeated in the recent window.",
            "follow_through_recovery_summary": "1 item is recovering from recent escalation, but it still needs another calmer run before the stronger resurfacing retires.",
            "accountability_summary": "The top target is still open because the same urgent drift item keeps surviving recent cycles.",
            "primary_target_reason": "This stays on top because urgent drift has persisted and should be cleared before lower-pressure work.",
            "primary_target_done_criteria": "Inspect the drift, reconcile it, and confirm the item no longer returns as urgent on the next run.",
            "closure_guidance": "Review the managed issue, reconcile the drift, and confirm the urgent queue shrinks on the next run.",
            "primary_target_last_intervention": {
                "repo": "RepoC",
                "title": "RepoC drift needs review",
                "event_type": "drifted",
                "recorded_at": "2026-03-29T12:00:00+00:00",
                "outcome": "drifted",
            },
            "primary_target_resolution_evidence": "The last intervention was drifted for RepoC: RepoC drift needs review, but the item is still open.",
            "primary_target_confidence_score": 0.7,
            "primary_target_confidence_label": "medium",
            "primary_target_confidence_reasons": [
                "Urgent drift or regression needs attention before ready work.",
                "A prior intervention happened, but the item is still open.",
            ],
            "next_action_confidence_score": 0.75,
            "next_action_confidence_label": "high",
            "next_action_confidence_reasons": ["The next step is tied directly to the current top target."],
            "primary_target_trust_policy": "verify-first",
            "primary_target_trust_policy_reason": "Recent calibration is noisy enough that this recommendation should be verified before acting on it.",
            "next_action_trust_policy": "verify-first",
            "next_action_trust_policy_reason": "Recent calibration is noisy enough that this recommendation should be verified before acting on it.",
            "primary_target_exception_status": "softened-for-noise",
            "primary_target_exception_reason": "Recent trust noise plus a reopened target warrants a softer verification-first posture.",
            "primary_target_exception_pattern_status": "useful-caution",
            "primary_target_exception_pattern_reason": "Recent soft caution was followed by renewed instability or unresolved pressure, so the softer posture still looks justified.",
            "primary_target_trust_recovery_status": "blocked",
            "primary_target_trust_recovery_reason": "Trust recovery is blocked because this target reopened again inside the recent recovery window.",
            "primary_target_recovery_confidence_score": 0.35,
            "primary_target_recovery_confidence_label": "low",
            "primary_target_recovery_confidence_reasons": [
                "Mixed calibration keeps retirement confidence in the middle for now.",
                "Recent exception history still shows useful caution, so the softer posture remains justified.",
                "The target reopened inside the retirement window, so caution still needs to stay in place.",
            ],
            "recovery_confidence_summary": "RepoC: RepoC drift needs review still has low recovery confidence (0.35), so the softer caution should stay in place.",
            "primary_target_exception_retirement_status": "blocked",
            "primary_target_exception_retirement_reason": "Exception retirement is blocked because the target reopened inside the retirement window.",
            "exception_retirement_summary": "RepoC: RepoC drift needs review still has reopen, flip, or calibration noise blocking exception retirement.",
            "retired_exception_hotspots": [],
            "sticky_exception_hotspots": [
                {"scope": "class", "label": "urgent:campaign", "sticky_count": 2, "exception_count": 2}
            ],
            "exception_retirement_window_runs": 4,
            "primary_target_policy_debt_status": "class-debt",
            "primary_target_policy_debt_reason": "This class keeps carrying sticky caution across recent runs, so class-level normalization would be premature.",
            "primary_target_class_normalization_status": "blocked",
            "primary_target_class_normalization_reason": "Class-level normalization is blocked by local reopen, flip, blocked-recovery, or calibration noise.",
            "policy_debt_summary": "RepoC: RepoC drift needs review belongs to a class that keeps carrying sticky caution, so class-level normalization should stay conservative for now.",
            "trust_normalization_summary": "RepoC: RepoC drift needs review is blocked from class-level normalization by local reopen, flip, or calibration noise.",
            "policy_debt_hotspots": [
                {"scope": "class", "label": "urgent:campaign", "match_count": 3, "exception_count": 3}
            ],
            "normalized_class_hotspots": [],
            "class_normalization_window_runs": 4,
            "primary_target_class_memory_freshness_status": "stale",
            "primary_target_class_memory_freshness_reason": "Older class evidence is now carrying more of the signal than recent runs, so class-level trust should not lean on it too heavily.",
            "primary_target_class_decay_status": "blocked",
            "primary_target_class_decay_reason": "Local reopen, flip, or blocked-recovery noise still overrides healthier class memory for this target.",
            "class_memory_summary": "RepoC: RepoC drift needs review is leaning on older class evidence that is now being down-weighted so it does not dominate the current trust posture.",
            "class_decay_summary": "RepoC: RepoC drift needs review still has local target noise blocking healthier class memory from changing the live posture.",
            "primary_target_weighted_class_support_score": 0.18,
            "primary_target_weighted_class_caution_score": 0.46,
            "primary_target_class_trust_reweight_score": -0.28,
            "primary_target_class_trust_reweight_direction": "supporting-caution",
            "primary_target_class_trust_reweight_reasons": [
                "Older class evidence is now carrying more of the signal than recent runs, so class-level trust should not lean on it too heavily.",
                "Sticky class caution is still weighing against broader relaxation.",
                "Local target noise is still blocking healthier class carry-forward.",
            ],
            "class_reweighting_summary": "RepoC: RepoC drift needs review still sits in caution-heavy class evidence, so class trust stays conservative (-0.28).",
            "supporting_class_hotspots": [],
            "caution_class_hotspots": [],
            "class_reweighting_window_runs": 4,
            "primary_target_class_trust_momentum_score": -0.34,
            "primary_target_class_trust_momentum_status": "sustained-caution",
            "primary_target_class_reweight_stability_status": "stable",
            "primary_target_class_reweight_transition_status": "confirmed-caution",
            "primary_target_class_reweight_transition_reason": "Caution-heavy class evidence has stayed strong long enough to confirm broader class caution.",
            "class_momentum_summary": "RepoC: RepoC drift needs review now has caution-heavy class evidence that stayed strong long enough to confirm broader caution (-0.34).",
            "class_reweight_stability_summary": "Class guidance for RepoC: RepoC drift needs review is stable across the recent path: supporting-caution -> supporting-caution.",
            "class_transition_window_runs": 4,
            "primary_target_class_transition_health_status": "none",
            "primary_target_class_transition_health_reason": "",
            "primary_target_class_transition_resolution_status": "confirmed",
            "primary_target_class_transition_resolution_reason": "Caution-heavy class evidence has stayed strong long enough to confirm broader class caution.",
            "class_transition_health_summary": "No active pending class transition is building or stalling right now.",
            "class_transition_resolution_summary": "RepoC: RepoC drift needs review resolved its earlier pending class transition into a confirmed broader class posture.",
            "class_transition_age_window_runs": 4,
            "primary_target_transition_closure_confidence_score": 0.72,
            "primary_target_transition_closure_confidence_label": "medium",
            "primary_target_transition_closure_likely_outcome": "hold",
            "primary_target_transition_closure_confidence_reasons": [
                "The pending class signal is still visible, but it is not strong enough to trust fully yet."
            ],
            "transition_closure_confidence_summary": "RepoC: RepoC drift needs review still has a viable pending class signal, but it is not strong enough to trust fully yet (0.72).",
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
            "primary_target_weighted_pending_resolution_support_score": 0.51,
            "primary_target_weighted_pending_debt_caution_score": 0.26,
            "primary_target_closure_forecast_reweight_score": 0.25,
            "primary_target_closure_forecast_reweight_direction": "supporting-confirmation",
            "primary_target_closure_forecast_reweight_reasons": [
                "Pending-transition memory is still useful, but it is partly aging: 50% of the weighted signal is recent and the rest is older carry-forward.",
                "Recent class resolution behavior is still strong enough that this pending signal could confirm soon.",
                "The live pending signal is still building in the same direction.",
            ],
            "closure_forecast_reweighting_summary": "RepoC: RepoC drift needs review still needs persistence before confirmation, but fresh class resolution behavior is strengthening the pending forecast (0.25).",
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
            "recommendation_drift_status": "watch",
            "recommendation_drift_summary": "RepoC: RepoC drift needs review has started to wobble between trust policies in the recent window: act-with-review -> verify-first.",
            "policy_flip_hotspots": [
                {
                    "scope": "target",
                    "label": "RepoC: RepoC drift needs review",
                    "flip_count": 1,
                    "recent_policy_path": "verify-first -> act-with-review",
                }
            ],
            "exception_pattern_summary": "Recent soft caution for RepoC: RepoC drift needs review has been justified and still looks appropriate.",
            "false_positive_exception_hotspots": [],
            "trust_recovery_window_runs": 3,
            "adaptive_confidence_summary": "Calibration is noisy, so the recommendation was softened and should be verified before acting.",
            "recommendation_quality_summary": "Strong recommendation because the next step is tied directly to the current top target.",
            "confidence_validation_status": "mixed",
            "confidence_window_runs": 8,
            "validated_recommendation_count": 2,
            "partially_validated_recommendation_count": 1,
            "unresolved_recommendation_count": 1,
            "reopened_recommendation_count": 1,
            "insufficient_future_runs_count": 2,
            "high_confidence_hit_rate": 0.5,
            "medium_confidence_hit_rate": 0.67,
            "low_confidence_caution_rate": 1.0,
            "recent_validation_outcomes": [
                {
                    "run_id": "testuser:2026-03-27T12:00:00+00:00",
                    "target_label": "RepoC: RepoC drift needs review",
                    "confidence_label": "high",
                    "outcome": "reopened",
                    "validated_in_runs": 2,
                }
            ],
            "confidence_calibration_summary": "Confidence is still useful, but recent outcomes are mixed: 50% high-confidence hit rate, 67% medium-confidence hit rate, and 1 reopened outcome(s).",
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
            "primary_target": {"repo": "RepoC", "title": "RepoC drift needs review"},
        },
        "operator_queue": [
            {
                "item_id": "campaign-drift:repo-c",
                "kind": "campaign",
                "lane": "urgent",
                "priority": 90,
                "repo": "RepoC",
                "title": "RepoC drift needs review",
                "summary": "managed-issue-edited",
                "recommended_action": "Inspect the managed issue before closing the campaign.",
                "source_run_id": "testuser:2026-03-29T12:00:00+00:00",
                "age_days": 0,
                "links": [],
                "follow_through_status": "waiting-on-evidence",
                "follow_through_age_runs": 1,
                "follow_through_checkpoint_status": "due-soon",
                "follow_through_summary": "RepoC has recent follow-up recorded and is now waiting for confirming evidence.",
                "follow_through_next_checkpoint": "Wait for the next run to confirm the pressure falls.",
                "follow_through_escalation_status": "watch",
                "follow_through_escalation_summary": "RepoC is not late yet, but it should stay visible until the next checkpoint lands.",
                "follow_through_recovery_age_runs": 1,
                "follow_through_recovery_status": "recovering",
                "follow_through_recovery_summary": "RepoC is recovering from recent escalation, but the lower-pressure state still needs to hold.",
            }
        ],
        "audits": [
            {
                "metadata": {"name": "RepoA", "html_url": "https://github.com/user/RepoA",
                             "description": "A cool project", "language": "Python"},
                "overall_score": 0.85, "interest_score": 0.60, "grade": "A",
                "completeness_tier": "shipped", "badges": ["fresh"], "flags": [],
                "lenses": {
                    "ship_readiness": {"score": 0.85, "summary": "Ready"},
                    "showcase_value": {"score": 0.9, "summary": "Strong story"},
                    "security_posture": {"score": 0.8, "summary": "Healthy"},
                },
                "security_posture": {"label": "healthy", "score": 0.8},
                "hotspots": [{"title": "Keep momentum"}],
                "analyzer_results": [],
            },
            {
                "metadata": {"name": "RepoB", "html_url": "", "description": None, "language": "Rust"},
                "overall_score": 0.55, "interest_score": 0.30, "grade": "C",
                "completeness_tier": "functional", "badges": [], "flags": [],
                "lenses": {
                    "ship_readiness": {"score": 0.55, "summary": "Needs work"},
                    "showcase_value": {"score": 0.5, "summary": "Average"},
                    "security_posture": {"score": 0.6, "summary": "Okay"},
                },
                "security_posture": {"label": "watch", "score": 0.6},
                "hotspots": [{"title": "Finish testing"}],
                "analyzer_results": [],
            },
            {
                "metadata": {"name": "RepoC", "html_url": "", "description": "WIP", "language": "Python"},
                "overall_score": 0.40, "interest_score": 0.10, "grade": "D",
                "completeness_tier": "wip", "badges": [], "flags": ["no-tests"],
                "lenses": {
                    "ship_readiness": {"score": 0.4, "summary": "Thin"},
                    "showcase_value": {"score": 0.25, "summary": "Weak"},
                    "security_posture": {"score": 0.3, "summary": "Risky"},
                },
                "security_posture": {"label": "critical", "score": 0.3},
                "hotspots": [{"title": "Security debt"}],
                "analyzer_results": [],
            },
        ],
    }
    defaults.update(overrides)
    return defaults


class TestExportHtmlDashboard:
    def test_creates_html_file(self, tmp_path):
        result = export_html_dashboard(_make_report(), tmp_path)
        assert result["html_path"].is_file()
        assert result["html_path"].suffix == ".html"

    def test_filename_includes_username(self, tmp_path):
        result = export_html_dashboard(_make_report(), tmp_path)
        assert "testuser" in result["html_path"].name

    def test_html_is_self_contained(self, tmp_path):
        result = export_html_dashboard(_make_report(), tmp_path)
        content = result["html_path"].read_text()
        assert "<!DOCTYPE html>" in content
        assert "<style>" in content
        assert "<script>" in content
        assert 'id="dashboard-data"' in content
        assert 'type="application/json"' in content
        assert "const DATA = JSON.parse" in content


class TestRenderHtml:
    def test_has_header(self):
        html = _render_html(_make_report())
        assert "Portfolio Dashboard: testuser" in html

    def test_has_kpi_section(self):
        html = _render_html(_make_report())
        assert "Avg Score" in html
        assert "0.60" in html
        assert "Shipped" in html

    def test_has_scatter_canvas(self):
        html = _render_html(_make_report())
        assert '<canvas id="scatter"' in html

    def test_has_repo_table(self):
        html = _render_html(_make_report())
        assert "RepoA" in html
        assert "RepoB" in html
        assert "RepoC" in html
        assert "Profile" in html
        assert "Collections" in html

    def test_repo_table_includes_next_action_explainability(self):
        html = _render_html(_make_report())
        assert "Next:" in html or "Gap:" in html

    def test_run_changes_section_is_rendered(self):
        html = _render_html(
            _make_report(run_change_summary="One repo improved and one regressed."),
            diff_data={"repo_changes": [], "score_changes": []},
        )
        assert "Run Changes" in html
        assert "One repo improved and one regressed." in html

    def test_run_changes_uses_shared_fallback_without_diff(self):
        html = _render_html(_make_report(), diff_data=None)
        assert no_baseline_summary() in html

    def test_operator_section_includes_trend_and_primary_target(self):
        html = _render_html(_make_report())
        assert f"Queue Pressure:</strong> {build_queue_pressure_summary(_make_report())}" in html
        assert f"Top Recommendation:</strong> {build_top_recommendation_summary(_make_report())}" in html
        assert "Top Attention / Next Action" in html
        assert "Trend:" in html
        assert "Accountability:" in html
        assert "Primary Target:" in html
        assert "Why This Is The Top Target:" in html
        assert "What Counts As Done:" in html
        assert "Closure Guidance:" in html
        assert "What We Tried:" in html
        assert "Resolution Evidence:" in html
        assert "Primary Target Confidence:" in html
        assert "Next Action Confidence:" in html
        assert "Recommendation Quality:" in html
        assert "Confidence Validation:" in html
        assert "Trust Policy:" in html
        assert "Trust Policy Exception:" in html
        assert "Exception Pattern Learning:" in html
        assert "Trust Recovery:" in html
        assert "Recovery Confidence:" in html
        assert "Exception Retirement:" in html
        assert "Policy Debt Cleanup:" in html
        assert "Class-Level Trust Normalization:" in html
        assert "Class Memory Freshness:" in html
        assert "Trust Decay Controls:" in html
        assert "Class Trust Reweighting:" in html
        assert "Why Class Guidance Shifted:" in html
        assert "Class Trust Momentum:" in html
        assert "Reweighting Stability:" in html
        assert "Class Transition Health:" in html
        assert "Pending Transition Resolution:" in html
        assert "Transition Closure Confidence:" in html
        assert "Class Pending Debt Audit:" in html
        assert "Pending Debt Freshness:" in html
        assert "Closure Forecast Reweighting:" in html
        assert "Closure Forecast Momentum:" in html
        assert "Closure Forecast Hysteresis:" in html
        assert "Closure Forecast Freshness:" in html
        assert "Hysteresis Decay Controls:" in html
        assert "Closure Forecast Refresh Recovery:" in html
        assert "Reacquisition Controls:" in html
        assert "Reacquisition Persistence:" in html
        assert "Recovery Churn Controls:" in html
        assert "Reacquisition Freshness:" in html
        assert "Persistence Reset Controls:" in html
        assert "Reset Refresh Recovery:" in html
        assert "Reset Re-entry Controls:" in html
        assert "Reset Re-entry Persistence:" in html
        assert "Reset Re-entry Churn Controls:" in html
        assert "Reset Re-entry Freshness:" in html
        assert "Reset Re-entry Reset Controls:" in html
        assert "Reset Re-entry Refresh Recovery:" in html
        assert "Reset Re-entry Rebuild Controls:" in html
        assert "Reset Re-entry Rebuild Freshness:" in html
        assert "Reset Re-entry Rebuild Reset Controls:" in html
        assert "Reset Re-entry Rebuild Refresh Recovery:" in html
        assert "Reset Re-entry Rebuild Re-entry Controls:" in html
        assert "Reset Re-entry Rebuild Re-Entry Persistence:" in html
        assert "Reset Re-entry Rebuild Re-Entry Churn Controls:" in html
        assert "Reset Re-entry Rebuild Re-Entry Freshness:" in html
        assert "Reset Re-entry Rebuild Re-Entry Reset Controls:" in html
        assert "Reset Re-entry Rebuild Re-Entry Refresh Recovery:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Controls:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Freshness:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Reset Controls:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Refresh Recovery:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Controls:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Persistence:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Churn Controls:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Freshness:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Reset Controls:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Refresh Recovery:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Controls:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Persistence:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Churn Controls:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Freshness:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Reset Controls:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Refresh Recovery:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Controls:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Persistence:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Churn Controls:" in html
        assert "Reset Re-entry Rebuild Persistence:" in html
        assert "Reset Re-entry Rebuild Churn Controls:" in html
        assert "Recommendation Drift:" in html
        assert "Policy Debt Summary:" in html
        assert "Trust Normalization Summary:" in html
        assert "Class Reweighting Summary:" in html
        assert "Class Momentum Summary:" in html
        assert "Reweighting Stability Summary:" in html
        assert "Class Transition Health Summary:" in html
        assert "Pending Transition Resolution Summary:" in html
        assert "Transition Closure Confidence Summary:" in html
        assert "Pending Debt Freshness Summary:" in html
        assert "Closure Forecast Reweighting Summary:" in html
        assert "Class Pending Debt Summary:" in html
        assert "Closure Forecast Momentum Summary:" in html
        assert "Closure Forecast Hysteresis Summary:" in html
        assert "Closure Forecast Freshness Summary:" in html
        assert "Closure Forecast Decay Summary:" in html
        assert "Closure Forecast Refresh Recovery Summary:" in html
        assert "Reacquisition Persistence Summary:" in html
        assert "Recovery Churn Summary:" in html
        assert "Reacquisition Freshness Summary:" in html
        assert "Persistence Reset Summary:" in html
        assert "Reset Refresh Recovery Summary:" in html
        assert "Reset Re-entry Summary:" in html
        assert "Reset Re-entry Persistence Summary:" in html
        assert "Reset Re-entry Churn Summary:" in html
        assert "Reset Re-entry Freshness Summary:" in html
        assert "Reset Re-entry Reset Summary:" in html
        assert "Reset Re-entry Refresh Recovery Summary:" in html
        assert "Reset Re-entry Rebuild Summary:" in html
        assert "Reset Re-entry Rebuild Freshness Summary:" in html
        assert "Reset Re-entry Rebuild Reset Summary:" in html
        assert "Reset Re-entry Rebuild Refresh Recovery Summary:" in html
        assert "Reset Re-entry Rebuild Re-entry Summary:" in html
        assert "Reset Re-entry Rebuild Re-Entry Persistence Summary:" in html
        assert "Reset Re-entry Rebuild Re-Entry Churn Summary:" in html
        assert "Reset Re-entry Rebuild Re-Entry Freshness Summary:" in html
        assert "Reset Re-entry Rebuild Re-Entry Reset Summary:" in html
        assert "Reset Re-entry Rebuild Re-Entry Refresh Recovery Summary:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Summary:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Freshness Summary:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Reset Summary:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Refresh Recovery Summary:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Summary:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Persistence Summary:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Churn Summary:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Freshness Summary:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Reset Summary:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Refresh Recovery Summary:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Summary:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Persistence Summary:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Churn Summary:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Freshness Summary:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Refresh Recovery Summary:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Summary:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Persistence Summary:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Churn Summary:" in html
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Reset Summary:" in html
        assert "Reset Re-entry Rebuild Persistence Summary:" in html
        assert "Reset Re-entry Rebuild Churn Summary:" in html
        assert "Closure Forecast Reacquisition Summary:" in html
        assert "Why This Confidence Is Actionable:" in html
        assert "Recent Confidence Outcomes:" in html
        assert "RepoC: RepoC drift needs review" in html

    def test_has_filter_controls(self):
        html = _render_html(_make_report())
        assert 'id="filter-tier"' in html
        assert 'id="filter-grade"' in html
        assert 'id="filter-collection"' in html
        assert 'id="sort-mode"' in html
        assert 'id="search"' in html

    def test_has_tier_distribution(self):
        html = _render_html(_make_report())
        assert "Tier Distribution" in html
        assert "Shipped" in html

    def test_has_footer(self):
        html = _render_html(_make_report())
        assert "GithubRepoAuditor" in html

    def test_has_print_css(self):
        html = _render_html(_make_report())
        assert "@media print" in html

    def test_empty_audits_still_renders(self):
        report = _make_report(audits=[], tier_distribution={})
        html = _render_html(report)
        assert "<!DOCTYPE html>" in html
        assert "Portfolio Dashboard" in html

    def test_html_includes_campaign_and_governance_operator_state(self):
        html = _render_html(_make_report())
        assert "Sync mode:" in html
        assert "Managed drift:" in html
        assert "Approved:" in html
        assert "Needs Re-Approval:" in html
        assert "Governance Operator State" in html

    def test_html_includes_preflight_diagnostics_when_present(self):
        html = _render_html(
            _make_report(
                preflight_summary={
                    "status": "warning",
                    "blocking_errors": 0,
                    "warnings": 2,
                    "checks": [{"category": "config", "summary": "No audit-config.yaml was found."}],
                }
            )
        )
        assert "Preflight Diagnostics" in html
        assert "No audit-config.yaml was found." in html

    def test_html_includes_operator_control_center(self):
        html = _render_html(_make_report())
        assert "Operator Control Center" in html
        assert "Weekly Review Pack" in html
        assert "Repo Drilldowns" in html
        assert "Top Repo Drilldowns" in html
        assert 'href="#repo-' in html
        assert "Next Recommended Run" in html
        assert "Watch Strategy" in html
        assert "RepoC drift needs review" in html
        assert "Why It Matters" in html
        assert "What To Do Next" in html
        assert "Follow-Through" in html
        assert "Review-to-Action Follow-Through" in html
        assert "What Would Count As Progress" in html
        assert "Next Checkpoint" in html
        assert "Follow-Through Aging and Escalation" in html
        assert "Follow-Through Recovery and Escalation Retirement" in html
        assert "Checkpoint Timing" in html
        assert "Escalation" in html
        assert "Recovery / Retirement" in html
        assert "Last movement:" in html
        assert no_linked_artifact_summary() in html

    def test_data_embedded_as_json(self):
        html = _render_html(_make_report())
        assert '"username": "testuser"' in html
        assert '"audits":' in html
        assert '"selected_profile": "default"' in html

    def test_html_includes_portfolio_trends(self):
        trend_data = [
            {"date": "2026-01-01", "average_score": 0.50, "repos_audited": 5,
             "tier_distribution": {"shipped": 1, "functional": 2, "wip": 1, "skeleton": 1},
             "top_repos": {}},
            {"date": "2026-02-01", "average_score": 0.55, "repos_audited": 6,
             "tier_distribution": {"shipped": 2, "functional": 2, "wip": 1, "skeleton": 1},
             "top_repos": {}},
            {"date": "2026-03-01", "average_score": 0.62, "repos_audited": 7,
             "tier_distribution": {"shipped": 3, "functional": 2, "wip": 1, "skeleton": 1},
             "top_repos": {}},
        ]
        html = _render_html(_make_report(), trend_data=trend_data)
        assert "Portfolio Trends" in html
        assert '<canvas id="trends-chart"' in html
        assert "Score trend:" in html
        assert "0.500" in html
        assert "0.620" in html

    def test_html_trends_graceful_empty(self):
        html = _render_html(_make_report(), trend_data=[])
        assert "Portfolio Trends" in html
        assert "Not enough historical data for trends" in html
        assert '<canvas id="trends-chart"' not in html

    def test_escapes_malicious_text_and_safe_json_embedding(self):
        report = _make_report(
            audits=[
                {
                    "metadata": {
                        "name": '</script><script>alert("xss")</script>',
                        "html_url": "https://github.com/user/repo",
                        "description": '</script><script>alert("xss")</script>',
                        "language": "Python",
                    },
                    "overall_score": 0.85,
                    "interest_score": 0.6,
                    "grade": "A",
                    "completeness_tier": "shipped",
                    "badges": [],
                    "flags": [],
                    "analyzer_results": [],
                }
            ]
        )
        html = _render_html(report)
        assert '&lt;/script&gt;&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;' in html
        assert '</script><script>alert("xss")</script>' not in html
        assert '<script id="dashboard-data" type="application/json">' in html
        assert '<\\/script>' in html

    def test_renders_analyst_sections(self):
        diff_data = {
            "average_score_delta": 0.04,
            "lens_deltas": {"ship_readiness": 0.1},
            "repo_changes": [{"name": "RepoA", "delta": 0.1, "old_tier": "functional", "new_tier": "shipped"}],
        }
        html = _render_html(_make_report(), diff_data=diff_data, portfolio_profile="default", collection="showcase")
        assert "Analyst View" in html
        assert "Decision Lenses" in html
        assert "Security Overview" in html
        assert "Governance Operator State" in html
        assert "Compare" in html
        assert "Scenario Preview" in html
        assert "showcase" in html
