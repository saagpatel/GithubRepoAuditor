from __future__ import annotations

import json
from datetime import datetime, timezone

from src.models import AnalyzerResult, AuditReport, RepoAudit, RepoMetadata
from src.report_enrichment import (
    build_queue_pressure_summary,
    build_top_recommendation_summary,
    build_trust_actionability_summary,
    no_linked_artifact_summary,
)
from src.reporter import (
    _sanitize_for_json,
    write_json_report,
    write_markdown_report,
    write_pcc_export,
    write_raw_metadata,
)


def _make_report() -> AuditReport:
    meta = RepoMetadata(
        name="test-repo", full_name="user/test-repo", description="A test",
        language="Python", languages={"Python": 5000}, private=False, fork=False,
        archived=False, created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        pushed_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
        default_branch="main", stars=3, forks=1, open_issues=0,
        size_kb=1024, html_url="https://github.com/user/test-repo",
        clone_url="", topics=["python"],
    )
    audit = RepoAudit(
        metadata=meta,
        analyzer_results=[
            AnalyzerResult("readme", 0.8, 1.0, ["Has README"]),
            AnalyzerResult("testing", 0.6, 1.0, ["5 test files"]),
        ],
        overall_score=0.7,
        completeness_tier="functional",
        interest_score=0.45,
        interest_tier="notable",
    )
    audit.implementation_hotspots = [
        {
            "scope": "file",
            "path": "src/core.py",
            "module": "src",
            "category": "code-complexity",
            "pressure_score": 0.74,
            "suggestion_type": "refactor",
            "why_it_matters": "src/core.py is carrying concentrated complexity.",
            "suggested_first_move": "Split the biggest function and add one regression test.",
            "signal_summary": "Complexity pressure 0.74 across 2 complex blocks.",
        }
    ]
    return AuditReport.from_audits("user", [audit], [], 1)


class TestSanitizeForJson:
    def test_sanitize_for_json_strips_control_chars(self):
        data = {"name": "test\x00repo", "items": ["hello\x0bworld"], "nested": {"key": "val\x0cue"}}
        result = _sanitize_for_json(data)
        assert result["name"] == "testrepo"
        assert result["items"][0] == "helloworld"
        assert result["nested"]["key"] == "value"
        # Non-string types pass through
        assert _sanitize_for_json(42) == 42
        assert _sanitize_for_json(None) is None


class TestJsonReport:
    def test_writes_valid_json(self, tmp_path):
        report = _make_report()
        path = write_json_report(report, tmp_path)
        data = json.loads(path.read_text())
        assert data["repos_audited"] == 1
        assert "audits" in data
        assert data["audits"][0]["interest_score"] == 0.45
        assert data["schema_version"] == "3.7"
        assert "lenses" in data
        assert "security_governance_preview" in data
        assert "campaign_summary" in data
        assert "implementation_hotspots_summary" in data

    def test_filename_format(self, tmp_path):
        report = _make_report()
        path = write_json_report(report, tmp_path)
        assert path.name.startswith("audit-report-user-")
        assert path.suffix == ".json"


class TestMarkdownReport:
    def test_has_required_sections(self, tmp_path):
        report = _make_report()
        path = write_markdown_report(report, tmp_path)
        content = path.read_text()
        assert "## Summary" in content
        assert "### Decision Lenses" in content
        assert "### Security Overview" in content
        assert "Implementation Hotspots" in content
        assert "## Functional" in content
        assert "<details>" in content
        assert "Interest" in content  # Interest column in tables

    def test_per_repo_details(self, tmp_path):
        report = _make_report()
        path = write_markdown_report(report, tmp_path)
        content = path.read_text()
        assert "test-repo" in content
        assert "https://github.com/user/test-repo" in content
        assert "Where To Start" in content
        assert "src/core.py" in content

    def test_includes_compare_summary_when_diff_passed(self, tmp_path):
        report = _make_report()
        diff_data = {
            "average_score_delta": 0.04,
            "lens_deltas": {"ship_readiness": 0.1},
            "repo_changes": [{"name": "test-repo", "delta": 0.1, "old_tier": "wip", "new_tier": "functional"}],
        }
        path = write_markdown_report(report, tmp_path, diff_data=diff_data)
        content = path.read_text()
        assert "Compare Summary" in content
        assert "ship_readiness" in content

    def test_includes_campaign_and_writeback_sections(self, tmp_path):
        report = _make_report()
        report.campaign_summary = {
            "campaign_type": "promotion-push",
            "label": "Promotion Push",
            "action_count": 1,
            "repo_count": 1,
        }
        report.writeback_preview = {
            "repos": [
                {
                    "repo": "test-repo",
                    "topics": ["ghra-call-promotion-push"],
                    "issue_title": "[Repo Auditor] Promotion Push",
                    "notion_action_count": 1,
                }
            ]
        }
        report.writeback_results = {
            "mode": "apply",
            "target": "github",
            "results": [
                {
                    "repo_full_name": "user/test-repo",
                    "target": "github-issue",
                    "status": "created",
                    "url": "https://github.com/user/test-repo/issues/1",
                }
            ],
        }
        report.managed_state_drift = [
            {
                "repo_full_name": "user/test-repo",
                "target": "github-issue",
                "drift_state": "managed-issue-edited",
            }
        ]
        report.rollback_preview = {"available": True, "item_count": 1, "fully_reversible_count": 1}
        path = write_markdown_report(report, tmp_path)
        content = path.read_text()
        assert "Campaign Summary" in content
        assert "Next Actions" in content
        assert "Writeback Results" in content
        assert "Managed State Drift" in content
        assert "Rollback Preview" in content

    def test_campaign_section_includes_github_projects_summary(self, tmp_path):
        report = _make_report()
        report.campaign_summary = {
            "campaign_type": "security-review",
            "label": "Security Review",
            "action_count": 1,
            "repo_count": 1,
        }
        report.writeback_preview = {
            "sync_mode": "reconcile",
            "github_projects": {
                "enabled": True,
                "status": "configured",
                "project_owner": "octo-org",
                "project_number": 7,
                "item_count": 1,
            },
            "repos": [
                {
                    "repo": "test-repo",
                    "topics": ["ghra-call-security-review"],
                    "issue_title": "[Repo Auditor] Security Review",
                    "github_project_field_count": 3,
                    "notion_action_count": 0,
                }
            ],
        }
        path = write_markdown_report(report, tmp_path)
        content = path.read_text()

        assert "GitHub Projects: configured (octo-org #7, 1 items)" in content
        assert "| test-repo | ghra-call-security-review | [Repo Auditor] Security Review | 3 field(s) | 0 |" in content

    def test_includes_preflight_diagnostics_when_present(self, tmp_path):
        report = _make_report()
        report.preflight_summary = {
            "status": "warning",
            "blocking_errors": 0,
            "warnings": 2,
            "checks": [
                {"category": "github-auth", "summary": "GitHub token is not configured."},
            ],
        }
        path = write_markdown_report(report, tmp_path)
        content = path.read_text()
        assert "Preflight Diagnostics" in content
        assert "GitHub token is not configured." in content

    def test_includes_operator_control_center_when_present(self, tmp_path):
        report = _make_report()
        report.operator_summary = {
            "headline": "A blocked setup item needs attention.",
            "counts": {"blocked": 1, "urgent": 1, "ready": 0, "deferred": 0},
            "watch_strategy": "adaptive",
            "next_recommended_run_mode": "full",
            "watch_decision_summary": "The next run should be full because the scheduled full refresh interval has been reached.",
            "what_changed": "Missing template asset — Template mode cannot load the workbook template.",
            "why_it_matters": "A trustworthy next step is blocked until this is cleared.",
            "what_to_do_next": "Restore the workbook template before exporting.",
            "trend_summary": "The operator picture is worsening: 1 new attention item appeared and the top blocker should be cleared first.",
            "follow_through_summary": "1 urgent item repeated in the recent window.",
            "accountability_summary": "The current top target is fresh and should be closed before taking on newly ready work.",
            "primary_target_reason": "This outranks the rest of the queue because a setup blocker stops the next trustworthy export path.",
            "primary_target_done_criteria": "Clear the failing prerequisite and rerun the relevant export command so the blocker exits the queue.",
            "closure_guidance": "Restore the workbook template, rerun the export, and confirm this blocker disappears on the next run.",
            "primary_target_last_intervention": {
                "repo": "",
                "title": "Missing template asset",
                "event_type": "rerun",
                "recorded_at": "2026-04-07T12:00:00+00:00",
                "outcome": "no-change",
            },
            "primary_target_resolution_evidence": "The last intervention reran the export path, but the blocker is still open.",
            "primary_target_confidence_score": 0.9,
            "primary_target_confidence_label": "high",
            "primary_target_confidence_reasons": [
                "Blocked setup issue is directly stopping a trustworthy next step.",
                "This item is now chronic, so follow-through pressure is high.",
            ],
            "next_action_confidence_score": 0.95,
            "next_action_confidence_label": "high",
            "next_action_confidence_reasons": ["The next step is tied directly to the current top target."],
            "primary_target_trust_policy": "act-now",
            "primary_target_trust_policy_reason": "Blocked work with tuned high confidence should be cleared before new work.",
            "next_action_trust_policy": "act-now",
            "next_action_trust_policy_reason": "Blocked work with tuned high confidence should be cleared before new work.",
            "primary_target_exception_status": "none",
            "primary_target_exception_reason": "",
            "primary_target_exception_pattern_status": "overcautious",
            "primary_target_exception_pattern_reason": "Recent soft caution was followed by stable recovery without renewed pressure, so the softer posture may now be more cautious than the evidence supports.",
            "primary_target_trust_recovery_status": "earned",
            "primary_target_trust_recovery_reason": "Recent stability has earned this target back from verify-first to act-with-review.",
            "primary_target_recovery_confidence_score": 0.9,
            "primary_target_recovery_confidence_label": "high",
            "primary_target_recovery_confidence_reasons": [
                "Healthy calibration supports relaxing the earlier soft caution.",
                "Recent runs stayed stable after the exception without new pressure spikes.",
                "Recent exception history looks overcautious, so relaxing the softer posture is safer.",
            ],
            "recovery_confidence_summary": "Missing template asset has high recovery confidence (0.90), so the earlier caution can now retire.",
            "primary_target_exception_retirement_status": "retired",
            "primary_target_exception_retirement_reason": "Recent evidence is stable enough that the earlier soft caution has been formally retired.",
            "exception_retirement_summary": "Missing template asset has formally retired the earlier soft caution and returned to act-now.",
            "retired_exception_hotspots": [],
            "sticky_exception_hotspots": [],
            "exception_retirement_window_runs": 4,
            "primary_target_policy_debt_status": "watch",
            "primary_target_policy_debt_reason": "This class has enough recent exception activity to watch for lingering caution, but it is not yet clearly sticky or clearly normalization-friendly.",
            "primary_target_class_normalization_status": "candidate",
            "primary_target_class_normalization_reason": "This class is trending healthier, but the current target has not earned class-level normalization yet.",
            "policy_debt_summary": "Missing template asset sits in a class with mixed recent caution behavior, so watch for policy debt before normalizing further.",
            "trust_normalization_summary": "Missing template asset belongs to a healthier class trend, but it has not earned class-level normalization yet.",
            "policy_debt_hotspots": [],
            "normalized_class_hotspots": [],
            "class_normalization_window_runs": 4,
            "primary_target_class_memory_freshness_status": "fresh",
            "primary_target_class_memory_freshness_reason": "Recent class evidence is still current enough to trust, with 70% of the weighted signal coming from the latest 4 runs.",
            "primary_target_class_decay_status": "none",
            "primary_target_class_decay_reason": "",
            "class_memory_summary": "Missing template asset sits in class evidence that is still fresh enough to trust, so recent class behavior should carry more weight than older lessons.",
            "class_decay_summary": "Fresh class signals are still strongest here, so the current class posture still has enough recent support.",
            "primary_target_weighted_class_support_score": 0.62,
            "primary_target_weighted_class_caution_score": 0.18,
            "primary_target_class_trust_reweight_score": 0.44,
            "primary_target_class_trust_reweight_direction": "supporting-normalization",
            "primary_target_class_trust_reweight_reasons": [
                "Recent class evidence is still current enough to trust, with 70% of the weighted signal coming from the latest 4 runs.",
                "Existing class normalization support is still contributing to a stronger posture.",
                "Fresh sticky class evidence is still carrying meaningful caution.",
            ],
            "class_reweighting_summary": "Missing template asset inherited a stronger posture because fresh class support crossed the reweight threshold (0.44).",
            "supporting_class_hotspots": [],
            "caution_class_hotspots": [],
            "class_reweighting_window_runs": 4,
            "primary_target_class_trust_momentum_score": 0.38,
            "primary_target_class_trust_momentum_status": "sustained-support",
            "primary_target_class_reweight_stability_status": "stable",
            "primary_target_class_reweight_transition_status": "confirmed-support",
            "primary_target_class_reweight_transition_reason": "Fresh class support has stayed strong long enough to confirm broader normalization for this target.",
            "class_momentum_summary": "Missing template asset now has class support that stayed strong long enough to confirm broader normalization (0.38).",
            "class_reweight_stability_summary": "Class guidance for Missing template asset is stable across the recent path: supporting-normalization -> supporting-normalization.",
            "class_transition_window_runs": 4,
            "primary_target_class_transition_health_status": "none",
            "primary_target_class_transition_health_reason": "",
            "primary_target_class_transition_resolution_status": "confirmed",
            "primary_target_class_transition_resolution_reason": "Fresh class support has stayed strong long enough to confirm broader normalization for this target.",
            "class_transition_health_summary": "No active pending class transition is building or stalling right now.",
            "class_transition_resolution_summary": "Missing template asset resolved its earlier pending class transition into a confirmed broader class posture.",
            "class_transition_age_window_runs": 4,
            "primary_target_transition_closure_confidence_score": 0.78,
            "primary_target_transition_closure_confidence_label": "high",
            "primary_target_transition_closure_likely_outcome": "confirm-soon",
            "primary_target_transition_closure_confidence_reasons": [
                "The pending class signal is still accumulating in the same direction and may confirm soon."
            ],
            "transition_closure_confidence_summary": "Missing template asset still has a pending class signal that looks strong enough to confirm soon if the next run stays aligned (0.78).",
            "transition_closure_window_runs": 4,
            "primary_target_class_pending_debt_status": "watch",
            "primary_target_class_pending_debt_reason": "This class has mixed recent pending-transition outcomes, so watch whether new pending signals resolve cleanly or start to accumulate debt.",
            "class_pending_debt_summary": "Missing template asset belongs to a class with mixed pending-transition outcomes, so watch whether new pending signals confirm or start to linger.",
            "class_pending_resolution_summary": "No class-level pending-resolution pattern is strong enough to call out yet.",
            "class_pending_debt_window_runs": 10,
            "pending_debt_hotspots": [],
            "healthy_pending_resolution_hotspots": [],
            "primary_target_pending_debt_freshness_status": "mixed-age",
            "primary_target_pending_debt_freshness_reason": "Pending-transition memory is still useful, but it is partly aging: 50% of the weighted signal is recent and the rest is older carry-forward.",
            "pending_debt_freshness_summary": "Missing template asset still has useful pending-transition memory, but some of that signal is aging and should be weighted more cautiously.",
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
            "closure_forecast_reweighting_summary": "Missing template asset still needs persistence before confirmation, but fresh class resolution behavior is strengthening the pending forecast (0.27).",
            "closure_forecast_reweighting_window_runs": 4,
            "primary_target_closure_forecast_momentum_score": 0.18,
            "primary_target_closure_forecast_momentum_status": "building",
            "primary_target_closure_forecast_stability_status": "watch",
            "primary_target_closure_forecast_hysteresis_status": "pending-confirmation",
            "primary_target_closure_forecast_hysteresis_reason": "The confirmation-leaning forecast is visible, but it has not stayed persistent enough to trust fully yet.",
            "closure_forecast_momentum_summary": "The closure forecast for Missing template asset is trending in one direction, but it has not held long enough to lock in (0.18).",
            "closure_forecast_stability_summary": "Closure forecasting for Missing template asset is still settling and should be watched for one more stable stretch: supporting-confirmation -> neutral.",
            "closure_forecast_hysteresis_summary": "The confirmation-leaning forecast for Missing template asset is visible but not yet persistent enough to trust fully.",
            "primary_target_closure_forecast_freshness_status": "mixed-age",
            "primary_target_closure_forecast_freshness_reason": "Closure-forecast memory is still useful, but it is partly aging: 50% of the weighted forecast signal is recent and the rest is older carry-forward.",
            "primary_target_closure_forecast_decay_status": "none",
            "primary_target_closure_forecast_decay_reason": "",
            "closure_forecast_freshness_summary": "Missing template asset still has useful closure-forecast memory, but some of that signal is aging and should be weighted more cautiously.",
            "closure_forecast_decay_summary": "Recent closure-forecast evidence is still fresh enough that no forecast carry-forward needs to decay yet.",
            "primary_target_closure_forecast_refresh_recovery_score": 0.16,
            "primary_target_closure_forecast_refresh_recovery_status": "recovering-confirmation",
            "primary_target_closure_forecast_reacquisition_status": "pending-confirmation-reacquisition",
            "primary_target_closure_forecast_reacquisition_reason": "Fresh confirmation-side forecast evidence is returning, but it has not fully re-earned stronger carry-forward yet.",
            "closure_forecast_refresh_recovery_summary": "Fresh confirmation-side forecast evidence is returning for Missing template asset, but it has not fully re-earned stronger carry-forward yet (0.16).",
            "closure_forecast_reacquisition_summary": "Fresh confirmation-side forecast evidence is returning, but it has not fully re-earned stronger carry-forward yet.",
            "primary_target_closure_forecast_reacquisition_age_runs": 1,
            "primary_target_closure_forecast_reacquisition_persistence_score": 0.19,
            "primary_target_closure_forecast_reacquisition_persistence_status": "just-reacquired",
            "primary_target_closure_forecast_reacquisition_persistence_reason": "Stronger closure-forecast posture has returned, but it has not yet proved it can hold.",
            "closure_forecast_reacquisition_persistence_summary": "Missing template asset has only just re-earned stronger closure-forecast posture, so it is still fragile (0.19; 1 run).",
            "primary_target_closure_forecast_recovery_churn_score": 0.22,
            "primary_target_closure_forecast_recovery_churn_status": "watch",
            "primary_target_closure_forecast_recovery_churn_reason": "Recovery is wobbling and may lose its restored strength soon.",
            "closure_forecast_recovery_churn_summary": "Recovery for Missing template asset is wobbling enough that restored forecast strength may soften soon (0.22).",
            "primary_target_closure_forecast_reacquisition_freshness_status": "mixed-age",
            "primary_target_closure_forecast_reacquisition_freshness_reason": "Reacquired closure-forecast memory is still useful, but it is partly aging: 50% of the weighted signal is recent and the rest is older carry-forward.",
            "closure_forecast_reacquisition_freshness_summary": "Missing template asset still has useful reacquired closure-forecast memory, but the restored posture is no longer getting fully fresh reinforcement.",
            "primary_target_closure_forecast_persistence_reset_status": "none",
            "primary_target_closure_forecast_persistence_reset_reason": "",
            "closure_forecast_persistence_reset_summary": "Reacquired posture for Missing template asset is aging enough that it can keep holding, but it should no longer stay indefinitely at sustained strength.",
            "primary_target_closure_forecast_reset_refresh_recovery_score": 0.18,
            "primary_target_closure_forecast_reset_refresh_recovery_status": "recovering-confirmation-reset",
            "primary_target_closure_forecast_reset_reentry_status": "pending-confirmation-reentry",
            "primary_target_closure_forecast_reset_reentry_reason": "Fresh confirmation-side evidence is returning after a reset, but it has not yet re-earned re-entry.",
            "closure_forecast_reset_refresh_recovery_summary": "Fresh confirmation-side evidence is returning for Missing template asset after a reset, but it has not yet re-earned re-entry (0.18).",
            "closure_forecast_reset_reentry_summary": "Fresh confirmation-side evidence is returning after a reset, but it has not yet re-earned re-entry.",
            "primary_target_closure_forecast_reset_reentry_age_runs": 1,
            "primary_target_closure_forecast_reset_reentry_persistence_score": 0.24,
            "primary_target_closure_forecast_reset_reentry_persistence_status": "just-reentered",
            "primary_target_closure_forecast_reset_reentry_persistence_reason": "Stronger closure-forecast posture has re-entered after reset, but it has not yet proved it can hold.",
            "closure_forecast_reset_reentry_persistence_summary": "Missing template asset has only just re-entered stronger closure-forecast posture after reset, so it is still fragile (0.24; 1 run).",
            "primary_target_closure_forecast_reset_reentry_churn_score": 0.18,
            "primary_target_closure_forecast_reset_reentry_churn_status": "none",
            "primary_target_closure_forecast_reset_reentry_churn_reason": "",
            "closure_forecast_reset_reentry_churn_summary": "No meaningful reset re-entry churn is active right now.",
            "primary_target_closure_forecast_reset_reentry_freshness_status": "mixed-age",
            "primary_target_closure_forecast_reset_reentry_freshness_reason": "Reset re-entry memory is still useful, but it is partly aging: 50% of the weighted signal is recent and the rest is older carry-forward.",
            "closure_forecast_reset_reentry_freshness_summary": "Missing template asset still has useful reset re-entry memory, but the restored posture is no longer getting fully fresh reinforcement.",
            "primary_target_closure_forecast_reset_reentry_reset_status": "none",
            "primary_target_closure_forecast_reset_reentry_reset_reason": "",
            "closure_forecast_reset_reentry_reset_summary": "Reset re-entry posture for Missing template asset is aging enough that it can keep holding, but it should no longer stay indefinitely at sustained strength.",
            "primary_target_closure_forecast_reset_reentry_refresh_recovery_score": 0.31,
            "primary_target_closure_forecast_reset_reentry_refresh_recovery_status": "rebuilding-confirmation-reentry",
            "primary_target_closure_forecast_reset_reentry_rebuild_status": "pending-confirmation-rebuild",
            "primary_target_closure_forecast_reset_reentry_rebuild_reason": "Fresh confirmation-side evidence is rebuilding after the reset re-entry aged out, but it has not yet fully re-earned stronger posture.",
            "closure_forecast_reset_reentry_refresh_recovery_summary": "Fresh confirmation-side evidence is rebuilding for Missing template asset after reset re-entry aged out (0.31).",
            "closure_forecast_reset_reentry_rebuild_summary": "Missing template asset is rebuilding confirmation-side reset re-entry, but it has not fully re-earned stronger posture yet.",
            "primary_target_closure_forecast_reset_reentry_rebuild_freshness_status": "mixed-age",
            "primary_target_closure_forecast_reset_reentry_rebuild_freshness_reason": "Rebuilt reset re-entry memory is still useful, but it is partly aging: 50% of the weighted signal is recent and the rest is older carry-forward.",
            "closure_forecast_reset_reentry_rebuild_freshness_summary": "Missing template asset still has useful rebuilt reset re-entry memory, but the restored posture is no longer getting fully fresh reinforcement.",
            "primary_target_closure_forecast_reset_reentry_rebuild_reset_status": "none",
            "primary_target_closure_forecast_reset_reentry_rebuild_reset_reason": "",
            "closure_forecast_reset_reentry_rebuild_reset_summary": "Rebuilt posture for Missing template asset is aging enough that it can keep holding, but it should no longer stay indefinitely at sustained strength.",
            "primary_target_closure_forecast_reset_reentry_rebuild_refresh_recovery_score": 0.27,
            "primary_target_closure_forecast_reset_reentry_rebuild_refresh_recovery_status": "recovering-confirmation-rebuild-reset",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_status": "pending-confirmation-rebuild-reentry",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_reason": "Fresh confirmation-side evidence is returning after rebuilt posture was softened or reset, but it has not yet re-earned stronger rebuilt posture.",
            "closure_forecast_reset_reentry_rebuild_refresh_recovery_summary": "Fresh confirmation-side evidence is returning for Missing template asset after rebuilt posture softened, but it has not yet re-earned stronger rebuilt posture (0.27).",
            "closure_forecast_reset_reentry_rebuild_reentry_summary": "Missing template asset is recovering after rebuilt posture softened, but stronger rebuilt confirmation posture still needs more fresh follow-through before it is re-earned.",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_age_runs": 1,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_score": 0.26,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_status": "just-reentered",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_persistence_reason": "Stronger rebuilt posture has been re-earned, but it has not yet proved it can hold.",
            "closure_forecast_reset_reentry_rebuild_reentry_persistence_summary": "Missing template asset has only just re-earned stronger rebuilt posture, so it is still fragile (0.26; 1 run).",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_score": 0.0,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_status": "none",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_churn_reason": "",
            "closure_forecast_reset_reentry_rebuild_reentry_churn_summary": "No meaningful rebuilt re-entry churn is active right now.",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_freshness_status": "mixed-age",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_freshness_reason": "Rebuilt re-entry memory is still useful, but it is partly aging: 50% of the weighted signal is recent and the rest is older carry-forward.",
            "closure_forecast_reset_reentry_rebuild_reentry_freshness_summary": "Missing template asset still has useful rebuilt re-entry memory, but the restored posture is no longer getting fully fresh reinforcement.",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_reset_status": "none",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_reset_reason": "",
            "closure_forecast_reset_reentry_rebuild_reentry_reset_summary": "Rebuilt re-entry posture for Missing template asset is aging enough that it can keep holding, but it should no longer stay indefinitely at sustained strength.",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_score": 0.29,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_status": "recovering-confirmation-rebuild-reentry-reset",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_status": "pending-confirmation-rebuild-reentry-restore",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reason": "Fresh confirmation-side evidence is returning after rebuilt re-entry was softened or reset, but it has not yet restored stronger rebuilt re-entry posture.",
            "closure_forecast_reset_reentry_rebuild_reentry_refresh_recovery_summary": "Fresh confirmation-side evidence is returning for Missing template asset after rebuilt re-entry softened, but it has not yet restored stronger rebuilt re-entry posture (0.29).",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_summary": "Missing template asset is recovering after rebuilt re-entry softened, but stronger rebuilt re-entry posture still needs more fresh follow-through before it is restored.",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_age_runs": 1,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_score": 0.21,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_status": "just-restored",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_reason": "Stronger rebuilt re-entry posture has been restored, but it has not yet proved it can hold.",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_persistence_summary": "Missing template asset has only just restored stronger rebuilt re-entry posture, so it is still fragile (0.21; 1 run).",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_churn_score": 0.0,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_churn_status": "none",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_churn_reason": "",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_churn_summary": "No meaningful restored rebuilt re-entry churn is active right now.",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_status": "mixed-age",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_reason": "Restored rebuilt re-entry memory is still useful, but it is partly aging: 50% of the weighted signal is recent and the rest is older carry-forward.",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_freshness_summary": "Missing template asset still has useful restored rebuilt re-entry memory, but the restored posture is no longer getting fully fresh reinforcement.",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reset_status": "none",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_reset_reason": "",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_reset_summary": "Restored rebuilt re-entry posture for Missing template asset is aging enough that it can keep holding, but it should no longer stay indefinitely at sustained strength.",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_score": 0.31,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_status": "recovering-confirmation-rebuild-reentry-restore-reset",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_status": "pending-confirmation-rebuild-reentry-rerestore",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reason": "Fresh confirmation-side evidence is returning after restored rebuilt re-entry softened or reset, but it has not yet re-restored stronger restored posture.",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_refresh_recovery_summary": "Fresh confirmation-side evidence is returning for Missing template asset after restored rebuilt re-entry softened, but it has not yet re-restored stronger restored posture (0.31).",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_summary": "Missing template asset is recovering after restored rebuilt re-entry softened, but stronger restored posture still needs more fresh follow-through before it is re-restored.",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_age_runs": 1,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_score": 0.18,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_status": "just-rerestored",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_reason": "Stronger restored rebuilt re-entry posture has been re-restored, but it has not yet proved it can hold.",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_persistence_summary": "Missing template asset has only just re-restored stronger restored rebuilt re-entry posture, so it is still fragile (0.18; 1 run).",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_score": 0.0,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_status": "none",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_reason": "",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_churn_summary": "No meaningful re-restored rebuilt re-entry churn is active right now.",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_status": "mixed-age",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_reason": "Rerestored rebuilt re-entry memory is still useful, but it is partly aging: 50% of the weighted signal is recent and the rest is older carry-forward.",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_freshness_summary": "Missing template asset still has useful rerestored rebuilt re-entry memory, but the stronger posture is no longer getting fully fresh reinforcement.",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_status": "none",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_reason": "",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_reset_summary": "Rerestored rebuilt re-entry posture for Missing template asset is aging enough that it can keep holding, but it should no longer stay indefinitely at sustained strength.",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_score": 0.34,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_status": "recovering-confirmation-rebuild-reentry-rerestore-reset",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_status": "pending-confirmation-rebuild-reentry-rererestore",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reason": "Fresh confirmation-side evidence is returning after stronger rerestored posture softened or reset, but it has not yet re-re-restored stronger posture.",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_age_runs": 2,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_score": 0.27,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_status": "holding-confirmation-rebuild-reentry-rererestore",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_reason": "Confirmation-side re-re-restored posture has stayed aligned long enough to keep the stronger rerestored forecast in place.",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence_summary": "Confirmation-side re-re-restored posture for Missing template asset has held long enough to keep the stronger rerestored forecast in place (0.27; 2 runs).",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_score": 0.22,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_status": "watch",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_reason": "Re-re-restored rebuilt re-entry is wobbling and may lose its stronger posture soon.",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_churn_summary": "Re-re-restored rebuilt re-entry for Missing template asset is wobbling enough that stronger rerestored posture may soften soon (0.22).",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_status": "mixed-age",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_reason": "Re-re-restored rebuilt re-entry memory is still useful, but it is partly aging and no longer fully fresh.",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness_summary": "Missing template asset still has useful re-re-restored rebuilt re-entry memory, but the stronger posture is no longer getting fully fresh reinforcement.",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_status": "confirmation-softened",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_reason": "Re-re-restored confirmation-side rebuilt re-entry is aging and has been stepped down from sustained strength.",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_reset_summary": "Missing template asset has softened its re-re-restored confirmation-side rebuilt re-entry posture because the supporting signal is aging.",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_score": 0.33,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_status": "recovering-confirmation-rebuild-reentry-rererestore-reset",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_status": "pending-confirmation-rebuild-reentry-rerererestore",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_reason": "Fresh confirmation-side evidence is returning after stronger re-re-restored posture softened or reset, but it has not yet re-re-re-restored stronger posture.",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_recovery_summary": "Fresh confirmation-side evidence is returning for Missing template asset after stronger re-re-restored posture softened, but it has not yet re-re-re-restored stronger posture (0.33).",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_summary": "Missing template asset is recovering after stronger re-re-restored posture softened, but it still needs more fresh follow-through before it is re-re-re-restored.",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_refresh_window_runs": 4,
            "recovering_from_confirmation_rebuild_reentry_rererestore_reset_hotspots": [],
            "recovering_from_clearance_rebuild_reentry_rererestore_reset_hotspots": [],
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_age_runs": 1,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_score": 0.24,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_status": "just-rerererestored",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_reason": "Stronger re-re-restored rebuilt re-entry posture has been re-re-re-restored, but it has not yet proved it can hold.",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence_summary": "Missing template asset has only just re-re-re-restored stronger re-re-restored posture, so it is still fragile (0.24; 1 run).",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_window_runs": 4,
            "just_rerererestored_rebuild_reentry_hotspots": [],
            "holding_reset_reentry_rebuild_reentry_restore_rerererestore_hotspots": [],
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_score": 0.21,
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_status": "watch",
            "primary_target_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_reason": "Re-re-re-restored rebuilt re-entry is wobbling and may lose its stronger re-re-restored posture soon.",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_churn_summary": "Re-re-re-restored rebuilt re-entry for Missing template asset is wobbling enough that stronger re-re-restored posture may soften soon (0.21).",
            "reset_reentry_rebuild_reentry_restore_rerererestore_churn_hotspots": [],
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_recovery_summary": "Fresh confirmation-side evidence is returning for Missing template asset after stronger rerestored posture softened, but it has not yet re-re-restored stronger posture (0.34).",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_summary": "Missing template asset is recovering after stronger rerestored posture softened, but it still needs more fresh follow-through before it is re-re-restored.",
            "closure_forecast_reset_reentry_rebuild_reentry_restore_rerestore_refresh_window_runs": 4,
            "recovering_from_confirmation_rebuild_reentry_rerestore_reset_hotspots": [],
            "recovering_from_clearance_rebuild_reentry_rerestore_reset_hotspots": [],
            "decayed_rerestored_rebuild_reentry_confirmation_rate": 0.58,
            "decayed_rerestored_rebuild_reentry_clearance_rate": 0.12,
            "recent_reset_reentry_rebuild_reentry_restore_rerestore_signal_mix": "2.40 weighted rerestored run(s) with 1.39 confirmation-like, 0.29 clearance-like, and 50% of the signal from the freshest runs.",
            "primary_target_closure_forecast_reset_reentry_rebuild_age_runs": 1,
            "primary_target_closure_forecast_reset_reentry_rebuild_persistence_score": 0.29,
            "primary_target_closure_forecast_reset_reentry_rebuild_persistence_status": "just-rebuilt",
            "primary_target_closure_forecast_reset_reentry_rebuild_persistence_reason": "Stronger reset re-entry posture has been rebuilt, but it has not yet proved it can hold.",
            "closure_forecast_reset_reentry_rebuild_persistence_summary": "Missing template asset has only just rebuilt stronger reset re-entry posture, so it is still fragile (0.29; 1 run).",
            "primary_target_closure_forecast_reset_reentry_rebuild_churn_score": 0.14,
            "primary_target_closure_forecast_reset_reentry_rebuild_churn_status": "none",
            "primary_target_closure_forecast_reset_reentry_rebuild_churn_reason": "",
            "closure_forecast_reset_reentry_rebuild_churn_summary": "No meaningful reset re-entry rebuild churn is active right now.",
            "just_rebuilt_hotspots": [],
            "just_reentered_rebuild_hotspots": [],
            "holding_reset_reentry_rebuild_hotspots": [],
            "holding_reset_reentry_rebuild_reentry_hotspots": [],
            "just_restored_rebuild_reentry_hotspots": [],
            "holding_reset_reentry_rebuild_reentry_restore_hotspots": [],
            "just_rerestored_rebuild_reentry_hotspots": [],
            "holding_reset_reentry_rebuild_reentry_restore_rerestore_hotspots": [],
            "just_rererestored_rebuild_reentry_hotspots": [],
            "holding_reset_reentry_rebuild_reentry_restore_rererestore_hotspots": [],
            "reset_reentry_rebuild_reentry_restore_rererestore_churn_hotspots": [],
            "stale_reset_reentry_rebuild_reentry_restore_rererestore_hotspots": [],
            "fresh_reset_reentry_rebuild_reentry_restore_rererestore_signal_hotspots": [],
            "reset_reentry_rebuild_churn_hotspots": [],
            "reset_reentry_rebuild_reentry_churn_hotspots": [],
            "reset_reentry_rebuild_reentry_restore_churn_hotspots": [],
            "reset_reentry_rebuild_reentry_restore_rerestore_churn_hotspots": [],
            "stale_reset_reentry_rebuild_reentry_restore_rerestore_hotspots": [],
            "fresh_reset_reentry_rebuild_reentry_restore_rerestore_signal_hotspots": [],
            "stale_reset_reentry_rebuild_reentry_restore_hotspots": [],
            "fresh_reset_reentry_rebuild_reentry_restore_signal_hotspots": [],
            "recovering_from_confirmation_rebuild_reset_hotspots": [],
            "recovering_from_clearance_rebuild_reset_hotspots": [],
            "recovering_from_confirmation_rebuild_reentry_reset_hotspots": [],
            "recovering_from_clearance_rebuild_reentry_reset_hotspots": [],
            "stale_reset_reentry_rebuild_hotspots": [],
            "fresh_reset_reentry_rebuild_signal_hotspots": [],
            "stale_reset_reentry_rebuild_reentry_hotspots": [],
            "fresh_reset_reentry_rebuild_reentry_signal_hotspots": [],
            "stale_reset_reentry_hotspots": [],
            "fresh_reset_reentry_signal_hotspots": [],
            "closure_forecast_reset_reentry_decay_window_runs": 4,
            "closure_forecast_reset_reentry_refresh_window_runs": 4,
            "closure_forecast_reset_reentry_rebuild_window_runs": 4,
            "closure_forecast_reset_reentry_rebuild_decay_window_runs": 4,
            "closure_forecast_reset_reentry_rebuild_reentry_decay_window_runs": 4,
            "closure_forecast_reset_reentry_rebuild_reentry_refresh_window_runs": 4,
            "closure_forecast_reset_reentry_rebuild_reentry_restore_window_runs": 4,
            "stale_closure_forecast_hotspots": [],
            "fresh_closure_forecast_signal_hotspots": [],
            "closure_forecast_decay_window_runs": 4,
            "closure_forecast_refresh_window_runs": 4,
            "closure_forecast_reacquisition_window_runs": 4,
            "closure_forecast_reacquisition_decay_window_runs": 4,
            "closure_forecast_reset_refresh_window_runs": 4,
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
            "recovering_from_confirmation_reset_hotspots": [],
            "recovering_from_clearance_reset_hotspots": [],
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
            "exception_pattern_summary": "Missing template asset has stayed stable long enough to earn trust back from verify-first to act-with-review.",
            "false_positive_exception_hotspots": [],
            "trust_recovery_window_runs": 3,
            "adaptive_confidence_summary": "Calibration is validating well, so the live recommendation was strengthened and is ready for immediate action.",
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
                    "run_id": "user:2026-04-05T12:00:00+00:00",
                    "target_label": "Missing template asset",
                    "confidence_label": "high",
                    "outcome": "validated",
                    "validated_in_runs": 2,
                }
            ],
            "confidence_calibration_summary": "Recent high-confidence recommendations are validating well: 75% high-confidence hit rate across 6 judged runs with no reopen noise.",
            "primary_target": {"title": "Missing template asset"},
        }
        report.operator_queue = [
            {
                "lane": "blocked",
                "repo": "",
                "title": "Missing template asset",
                "summary": "Template mode cannot load the workbook template.",
                "recommended_action": "Restore the workbook template before exporting.",
            }
        ]
        path = write_markdown_report(report, tmp_path)
        content = path.read_text()
        assert "Operator Control Center" in content
        assert "Missing template asset" in content
        assert build_queue_pressure_summary(report.to_dict()) in content
        assert build_top_recommendation_summary(report.to_dict()) in content
        assert build_trust_actionability_summary(report.to_dict()) in content
        assert "Recommendation Drift:" in content
        assert "Exception Pattern Learning:" in content
        assert "Trust Recovery:" in content
        assert "Recovery Confidence:" in content
        assert "Exception Retirement:" in content
        assert "Policy Debt Cleanup:" in content
        assert "Class-Level Trust Normalization:" in content
        assert "Class Memory Freshness:" in content
        assert "Trust Decay Controls:" in content
        assert "Class Trust Reweighting:" in content
        assert "Why Class Guidance Shifted:" in content
        assert "Class Trust Momentum:" in content
        assert "Reweighting Stability:" in content
        assert "Class Transition Health:" in content
        assert "Pending Transition Resolution:" in content
        assert "Transition Closure Confidence:" in content
        assert "Class Pending Debt Audit:" in content
        assert "Pending Debt Freshness:" in content
        assert "Closure Forecast Reweighting:" in content
        assert "Closure Forecast Momentum:" in content
        assert "Closure Forecast Hysteresis:" in content
        assert "Closure Forecast Freshness:" in content
        assert "Hysteresis Decay Controls:" in content
        assert "Closure Forecast Refresh Recovery:" in content
        assert "Reacquisition Controls:" in content
        assert "Reacquisition Persistence:" in content
        assert "Recovery Churn Controls:" in content
        assert "Next Recommended Run" in content
        assert "Watch Strategy" in content
        assert "Weekly Review Pack" in content
        assert "### Operator Focus" in content
        assert "- Summary:" in content
        assert "- Act Now:" in content
        assert "- Watch Closely:" in content
        assert "- Improving:" in content
        assert "- Fragile:" in content
        assert "- Revalidate:" in content
        assert "Top Repo Drilldowns" in content
        assert "What To Do This Week" in content
        assert "Current State" in content
        assert "What Changed" in content
        assert "What To Do Next" in content
        assert "What Would Count As Progress" in content
        assert "Queue Pressure" in content
        assert "Trust / Actionability" in content
        assert "Top Recommendation" in content
        assert "Top Attention" in content
        assert "Trend" in content
        assert "Follow-Through" in content
        assert "Next Checkpoint" in content
        assert "Checkpoint Timing" in content
        assert "Escalation" in content
        assert "Recovery / Retirement" in content
        assert "Recovery Persistence" in content
        assert "Relapse Churn" in content
        assert "Reacquisition Durability" in content
        assert "Reacquisition Confidence" in content
        assert "Reacquisition Softening Decay" in content
        assert "Reacquisition Confidence Retirement" in content
        assert "Revalidation Recovery" in content
        assert "Accountability" in content
        assert "Primary Target" in content
        assert "Why This Is The Top Target" in content
        assert "What Counts As Done" in content
        assert "Closure Guidance" in content
        assert "What We Tried" in content
        assert "Resolution Evidence" in content
        assert "Primary Target Confidence" in content
        assert "Next Action Confidence" in content
        assert "Trust Policy" in content
        assert "Why This Confidence Is Actionable" in content
        assert "Recommendation Quality" in content
        assert "Policy Debt Summary" in content
        assert "Trust Normalization Summary" in content
        assert "Class Reweighting Summary" in content
        assert "Class Momentum Summary" in content
        assert "Reweighting Stability Summary" in content
        assert "Class Transition Health Summary" in content
        assert "Pending Transition Resolution Summary" in content
        assert "Transition Closure Confidence Summary" in content
        assert "Pending Debt Freshness Summary" in content
        assert "Closure Forecast Reweighting Summary" in content
        assert "Closure Forecast Momentum Summary" in content
        assert "Closure Forecast Hysteresis Summary" in content
        assert "Closure Forecast Freshness Summary" in content
        assert "Closure Forecast Decay Summary" in content
        assert "Closure Forecast Refresh Recovery Summary" in content
        assert "Reacquisition Persistence Summary" in content
        assert "Recovery Churn Summary" in content
        assert "Reacquisition Freshness:" in content
        assert "Persistence Reset Controls:" in content
        assert "Reset Refresh Recovery:" in content
        assert "Reset Re-entry Controls:" in content
        assert "Reset Re-entry Persistence:" in content
        assert "Reset Re-entry Churn Controls:" in content
        assert "Reset Re-entry Freshness:" in content
        assert "Reset Re-entry Reset Controls:" in content
        assert "Reset Re-entry Refresh Recovery:" in content
        assert "Reset Re-entry Rebuild Controls:" in content
        assert "Reset Re-entry Rebuild Freshness:" in content
        assert "Reset Re-entry Rebuild Reset Controls:" in content
        assert "Reset Re-entry Rebuild Refresh Recovery:" in content
        assert "Reset Re-entry Rebuild Re-entry Controls:" in content
        assert "Reset Re-entry Rebuild Re-Entry Persistence:" in content
        assert "Reset Re-entry Rebuild Re-Entry Churn Controls:" in content
        assert "Reset Re-entry Rebuild Re-Entry Freshness:" in content
        assert "Reset Re-entry Rebuild Re-Entry Reset Controls:" in content
        assert "Reset Re-entry Rebuild Re-Entry Refresh Recovery:" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Controls:" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Freshness:" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Reset Controls:" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Refresh Recovery:" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Controls:" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Persistence:" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Churn Controls:" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Freshness:" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Reset Controls:" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Refresh Recovery:" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Controls:" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Persistence:" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Churn Controls:" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Freshness:" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Reset Controls:" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Refresh Recovery:" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Controls:" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Persistence:" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Churn Controls:" in content
        assert "Reset Re-entry Rebuild Persistence:" in content
        assert "Reset Re-entry Rebuild Churn Controls:" in content
        assert "Reset Re-entry Persistence Summary" in content
        assert "Reset Re-entry Churn Summary" in content
        assert "Reset Re-entry Freshness Summary" in content
        assert "Reset Re-entry Reset Summary" in content
        assert "Reset Re-entry Refresh Recovery Summary" in content
        assert "Reset Re-entry Rebuild Summary" in content
        assert "Reset Re-entry Rebuild Freshness Summary" in content
        assert "Reset Re-entry Rebuild Reset Summary" in content
        assert "Reset Re-entry Rebuild Refresh Recovery Summary" in content
        assert "Reset Re-entry Rebuild Re-entry Summary" in content
        assert "Reset Re-entry Rebuild Re-Entry Persistence Summary" in content
        assert "Reset Re-entry Rebuild Re-Entry Churn Summary" in content
        assert "Reset Re-entry Rebuild Re-Entry Freshness Summary" in content
        assert "Reset Re-entry Rebuild Re-Entry Reset Summary" in content
        assert "Reset Re-entry Rebuild Re-Entry Refresh Recovery Summary" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Summary" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Freshness Summary" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Reset Summary" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Refresh Recovery Summary" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Summary" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Persistence Summary" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Churn Summary" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Freshness Summary" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Reset Summary" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Restore Refresh Recovery Summary" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Summary" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Persistence Summary" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Churn Summary" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Freshness Summary" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Refresh Recovery Summary" in content
        assert "Reacquisition Durability:" in content
        assert "Reacquisition Confidence:" in content
        assert "Reacquisition Softening Decay:" in content
        assert "Reacquisition Confidence Retirement:" in content
        assert "Revalidation Recovery:" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Summary" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Persistence Summary" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Re-Restore Churn Summary" in content
        assert "Reset Re-entry Rebuild Re-Entry Restore Re-Re-Restore Reset Summary" in content
        assert "Reset Re-entry Rebuild Persistence Summary" in content
        assert "Reset Re-entry Rebuild Churn Summary" in content
        assert "Reacquisition Freshness Summary" in content
        assert "Persistence Reset Summary" in content
        assert "Reset Refresh Recovery Summary" in content
        assert "Reset Re-entry Summary" in content
        assert "Closure Forecast Reacquisition Summary" in content
        assert "Class Pending Debt Summary" in content
        assert "Confidence Validation" in content
        assert "Recent Confidence Outcomes" in content
        assert no_linked_artifact_summary() in content

    def test_includes_governance_operator_summary_when_present(self, tmp_path):
        report = _make_report()
        report.governance_summary = {
            "headline": "Governed controls need re-approval before the next manual apply step.",
            "status": "blocked",
            "needs_reapproval": True,
            "drift_count": 1,
            "applyable_count": 1,
            "applied_count": 0,
            "rollback_available_count": 1,
            "approval_age_days": 3,
            "top_actions": [
                {
                    "repo": "test-repo",
                    "title": "Enable CodeQL default setup",
                    "operator_state": "needs-reapproval",
                }
            ],
        }
        path = write_markdown_report(report, tmp_path)
        content = path.read_text()
        assert "Governance Operator State" in content
        assert "Needs Re-Approval: yes" in content
        assert "Enable CodeQL default setup [needs-reapproval]" in content


class TestRawMetadata:
    def test_writes_preflight_summary_when_present(self, tmp_path):
        report = _make_report()
        report.preflight_summary = {"status": "warning", "warnings": 1, "blocking_errors": 0}
        path = write_raw_metadata(report, tmp_path)
        data = json.loads(path.read_text())
        assert data["preflight_summary"]["status"] == "warning"

    def test_writes_governance_summary_when_present(self, tmp_path):
        report = _make_report()
        report.governance_summary = {"status": "ready", "headline": "Governed controls are ready for manual review."}
        path = write_raw_metadata(report, tmp_path)
        data = json.loads(path.read_text())
        assert data["governance_summary"]["status"] == "ready"

    def test_writes_portfolio_catalog_summaries_when_present(self, tmp_path):
        report = _make_report()
        report.portfolio_catalog_summary = {"summary": "1/1 repos have an explicit catalog contract."}
        report.intent_alignment_summary = {"summary": "1 aligned, 0 needing review, and 0 missing a contract."}
        report.audits[0].portfolio_catalog = {
            "has_explicit_entry": True,
            "owner": "d",
            "team": "operator-loop",
            "purpose": "flagship workbook",
            "lifecycle_state": "active",
            "criticality": "high",
            "review_cadence": "weekly",
            "intended_disposition": "maintain",
            "catalog_line": "operator-loop | flagship workbook | lifecycle active | criticality high | cadence weekly | disposition maintain",
            "intent_alignment": "aligned",
            "intent_alignment_reason": "The repo is holding a maintain posture without urgent or revalidation pressure.",
        }
        path = write_raw_metadata(report, tmp_path)
        data = json.loads(path.read_text())
        assert data["portfolio_catalog_summary"]["summary"] == "1/1 repos have an explicit catalog contract."
        assert data["intent_alignment_summary"]["summary"] == "1 aligned, 0 needing review, and 0 missing a contract."
        assert data["audits"][0]["portfolio_catalog"]["intent_alignment"] == "aligned"

    def test_writes_scorecard_summaries_when_present(self, tmp_path):
        report = _make_report()
        report.scorecards_summary = {"summary": "0 repos are on track, 1 is below target, and 0 are missing a valid program."}
        report.scorecard_programs = {"maintain": {"label": "Maintain", "rule_count": 8}}
        report.audits[0].scorecard = {
            "program": "maintain",
            "program_label": "Maintain",
            "maturity_level": "operating",
            "target_maturity": "strong",
            "status": "below-target",
            "top_gaps": ["Testing", "CI"],
            "summary": "Maintain is at Operating and still below the Strong target because testing and ci are behind.",
        }
        path = write_raw_metadata(report, tmp_path)
        data = json.loads(path.read_text())
        assert data["scorecards_summary"]["summary"].startswith("0 repos are on track")
        assert data["scorecard_programs"]["maintain"]["label"] == "Maintain"
        assert data["audits"][0]["scorecard"]["program"] == "maintain"


class TestPortfolioCatalogMarkdown:
    def test_includes_portfolio_catalog_and_intent_alignment_when_present(self, tmp_path):
        report = _make_report()
        report.portfolio_catalog_summary = {
            "summary": "1/1 repos have an explicit catalog contract.",
        }
        report.intent_alignment_summary = {
            "summary": "1 aligned, 0 needing review, and 0 missing a contract.",
        }
        report.audits[0].portfolio_catalog = {
            "has_explicit_entry": True,
            "owner": "d",
            "team": "operator-loop",
            "purpose": "flagship workbook",
            "lifecycle_state": "active",
            "criticality": "high",
            "review_cadence": "weekly",
            "intended_disposition": "maintain",
            "catalog_line": "operator-loop | flagship workbook | lifecycle active | criticality high | cadence weekly | disposition maintain",
            "intent_alignment": "aligned",
            "intent_alignment_reason": "The repo is holding a maintain posture without urgent or revalidation pressure.",
        }
        report.operator_queue = [
            {
                "repo": "test-repo",
                "title": "Protect flagship repo",
                "lane": "ready",
                "lane_reason": "Portfolio-critical repo needs a quick review.",
                "recommended_action": "Review the latest state.",
                "catalog_line": report.audits[0].portfolio_catalog["catalog_line"],
                "intent_alignment": "aligned",
                "intent_alignment_reason": report.audits[0].portfolio_catalog["intent_alignment_reason"],
            }
        ]

        path = write_markdown_report(report, tmp_path)
        content = path.read_text()

        assert "Portfolio Catalog: 1/1 repos have an explicit catalog contract." in content
        assert "Intent Alignment: 1 aligned, 0 needing review, and 0 missing a contract." in content
        assert "Catalog: operator-loop | flagship workbook" in content
        assert "Intent Alignment: aligned: The repo is holding a maintain posture" in content


class TestScorecardsMarkdown:
    def test_includes_scorecard_summary_and_repo_lines_when_present(self, tmp_path):
        report = _make_report()
        report.scorecards_summary = {
            "summary": "0 repos are on track, 1 is below target, and 0 are missing a valid program.",
        }
        report.audits[0].scorecard = {
            "program": "maintain",
            "program_label": "Maintain",
            "maturity_level": "operating",
            "target_maturity": "strong",
            "status": "below-target",
            "top_gaps": ["Testing", "CI"],
            "summary": "Maintain is at Operating and still below the Strong target because testing and ci are behind.",
        }
        report.operator_queue = [
            {
                "repo": "test-repo",
                "title": "Protect flagship repo",
                "lane": "ready",
                "lane_reason": "Portfolio-critical repo needs a quick review.",
                "recommended_action": "Review the latest state.",
                "scorecard": report.audits[0].scorecard,
            }
        ]

        path = write_markdown_report(report, tmp_path)
        content = path.read_text()

        assert "Scorecards: 0 repos are on track, 1 is below target" in content
        assert "Scorecard: Maintain — Operating (target Strong)" in content
        assert "Maturity Gap: testing, ci are still below the maintain bar." in content


class TestPccExport:
    def test_flat_array(self, tmp_path):
        report = _make_report()
        path = write_pcc_export(report, tmp_path)
        data = json.loads(path.read_text())
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "test-repo"
        assert data[0]["tier"] == "functional"
        assert data[0]["score"] == 0.7
