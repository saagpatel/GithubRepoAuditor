# Post-Merge Current State - 2026-04-24

## Status

PR #120, PR #121, and PR #122 are merged into `main`.

- PR #120 closed the workbook/export and operator-trend refactor batch, stabilized time-sensitive tests, and refreshed stale operator docs.
- PR #121 updated GitHub Actions to Node 24-compatible major versions.
- PR #122 recorded the post-merge rehearsal state and restored `python3 -m src.cli --help` behavior.
- Latest verified local branch before this note update: `main` aligned with `origin/main` at merge commit `743d833`.
- Latest verified GitHub main CI after PR #122: passed.

No P1/P2/P3 review findings from the April repair list remain open.

## 2026-05-16 Arc H Post-Merge Refresh

PR #176 is merged into `main`, and local `main` is aligned with `origin/main`.

Arc H added context-quality tooling:

- description confidence analyzer
- README age-based staleness signal
- catalog completeness validator
- tier recalibration report
- portfolio context triage output
- composite `context_quality_score`

Post-merge verification and refresh commands run:

```bash
python3 -m src report saagpatel --portfolio-truth --registry-output output/project-registry.md --portfolio-report-output output/PORTFOLIO-AUDIT-REPORT.md
python3 -m src report saagpatel --context-triage
python3 -m src report saagpatel --tier-recalibration-report
python3 -m src report saagpatel --portfolio-context-recovery --context-recovery-limit 5
python3 -m pytest tests/test_cli_subcommands.py tests/test_context_quality.py tests/test_portfolio_context_triage.py tests/test_catalog_validator.py -q -p no:cacheprovider
ruff check src/cli.py tests/test_cli_subcommands.py
```

Observed results:

- Portfolio truth regenerated for 131 projects.
- New truth warning remains display-name ambiguity: `IncidentWorkbench`, `OrbitForge`, and `StatusPage` require path-qualified registry labels.
- Context quality distribution is still weak: 79 `boilerplate`, 20 `minimum-viable`, 18 `none`, 11 `full`, and 3 `standard`.
- Path confidence is still the dominant portfolio risk: 108 projects are under an `investigate` override.
- Context triage flagged 107 repos: 42 moderate and 65 low. No critical rows were produced by the current scoring rules.
- Triage failure modes were concentrated in weak context quality (97 rows) and catalog completeness gaps (52 rows).
- Tier recalibration report found bunching: 51 Bronze, 79 Silver, 0 Gold, and 0 Platinum; Silver holds 60.3% of repos.
- Context recovery planning froze a 78-project target cohort: 50 eligible, 28 skipped by safety rules, 0 excluded.
- No context recovery writes were applied.

Incidental follow-up fixed during this refresh:

- The Arc H report flags were present in subcommand help but missing from the legacy parser used for execution. `--context-triage` and `--tier-recalibration-report` are now registered in both paths, with regression coverage in `tests/test_cli_subcommands.py`.

Current gate:

- Arc H tooling is merged and locally usable.
- The live portfolio still needs context recovery in batches. Start with the eligible active repos at the top of `output/context-recovery-plan-2026-05-16T091316Z.md`, not the skipped dirty-worktree or ambiguous-primary-context rows.
- Tier recalibration should stay report-only until the operator reviews whether the Bronze/Silver bunching reflects real maturity or threshold drift.

## 2026-05-09 Refresh

A bounded current-state refresh was run after returning to the project:

```bash
python3 -m src saagpatel --doctor
python3 -m src saagpatel --html --review-pack --badges --excel-mode standard
python3 -m src saagpatel --control-center
python3 -m src saagpatel --portfolio-truth --registry-output output/project-registry.md --portfolio-report-output output/PORTFOLIO-AUDIT-REPORT.md
python3 -m src saagpatel --approval-center
python3 -m src saagpatel --auto-apply-approved --dry-run
python3 -m src saagpatel --campaign security-review --writeback-target all
python3 -m src saagpatel --campaign promotion-push --writeback-target all
```

Observed results:

- Doctor completed with no blocking errors.
- Doctor warnings were optional setup gaps: no `audit-config.yaml` and no `config/notion-config.json`.
- Full audit completed against 115 GitHub repos after the analysis path was changed to default to one visible worker.
- Fresh May 9 artifacts were generated, including audit report, workbook, HTML dashboard, badges, review pack, control center, weekly command center, approval center, portfolio truth, and warehouse outputs.
- Audit score summary: average score `0.70`; tiers reported as `59 functional`, `45 shipped`, `8 wip`, and `3 skeleton`.
- Portfolio truth regenerated for 116 projects.
- Portfolio truth still has one known warning: duplicate `OrbitForge` display names require path-qualified registry labels.
- Control center now reads from the fresh May 9 full audit and remains urgent/sticky, led by `AuraForge` momentum drift.
- Approval center shows no current approval needs review; approval remains local-only.
- Auto-apply dry run reports 2 opted-in repos, 2 baseline opted-in repos, and 0 full trust-bar repos because decision quality is still `use-with-review`.
- Safe campaign previews completed with no live GitHub writes: `security-review` produced 20 preview actions across 18 repos, and `promotion-push` produced 20 preview actions across 15 repos.

Safety adjustment:

- `mcpforge` was removed from automation eligibility because the refreshed truth layer now classifies it as elevated risk: weak active context, investigate override, and missing run instructions.
- Do not re-add `mcpforge` to automation eligibility until its context quality and path confidence are repaired.

Current gate:

- Phase 123 remains preview-ready, but live apply is not ready because there are no approved-manual campaign packets and no repo currently passes the full auto-apply trust bar.
- The full-audit stall path was narrowed by making repo analysis default to one visible worker; use `--analysis-workers <n>` or `GITHUB_REPO_AUDITOR_ANALYSIS_WORKERS=<n>` only when intentionally opting back into parallel analysis.

Follow-up current-state refresh after the security noise cleanup:

- Control center now reports everything currently surfaced as safe to defer, with `0` blocked, `0` urgent, `0` ready, and `5` deferred queue items.
- Approval center still has no current approval needs review and no approved-manual packets.
- The latest Action Sync story remains preview-only: campaign previews are available, but no packet approval has been captured.
- The current strongest safe automation step is a preview of `security-review`; do not capture approval or run apply until a ready approval packet is visible.
- The manual approval-packet operating path is recorded in `docs/plans/2026-05-09-manual-approval-packet-workflow.md`.

## Rehearsal Results

Live weekly rehearsal was run from current `main` with the repo-native CLI entrypoint:

```bash
python3 -m src saagpatel --doctor
python3 -m src saagpatel --html --review-pack --badges --excel-mode standard
python3 -m src saagpatel --control-center
make workbook-gate
python3 -m src saagpatel --portfolio-truth --registry-output output/project-registry.md --portfolio-report-output output/PORTFOLIO-AUDIT-REPORT.md
python3 -m src saagpatel --approval-center
python3 -m src saagpatel --auto-apply-approved --dry-run
```

Observed results:

- Doctor completed with no blocking errors.
- Doctor warnings were expected optional-environment gaps: no `audit-config.yaml`, no `NOTION_TOKEN`, and no `config/notion-config.json`.
- Full audit completed against 114 GitHub repos.
- Fresh artifacts were generated for `2026-04-24`, including audit report, workbook, HTML dashboard, badges, review pack, control center, weekly command center, approval center, and portfolio truth.
- Audit score summary: average score `0.708`; tiers reported as `60 functional`, `44 shipped`, `7 wip`, and `3 skeleton`.
- Control center state is urgent/sticky, led by `AIGCCore shifted on momentum`.
- Workbook gate automated checks passed; manual desktop Excel signoff remains pending for this rehearsal.
- Portfolio truth generated for 115 projects.
- Approval center reported no current approval needs review.
- Auto-apply dry run reported no `approved-manual` campaign packets.

## Current Gates

Phase 123 is not ready for live automated apply.

Reasons:

- Portfolio truth currently has `0` automation-eligible projects.
- Approval center has no current approval needing review.
- Auto-apply dry run found no approved-manual campaign packets.

The safe next Phase 123 preparation is to choose 2-3 low-risk candidate repos, make their catalog/truth state explicitly automation-eligible, approve a bounded campaign packet, then rerun the dry-run gate before any live apply. The current candidate shortlist and prep commands are recorded in `docs/plans/2026-04-24-phase-123-readiness-prep.md`.

## Maintenance Findings

The post-refactor helper split is green but now has visible sprawl:

- `src/operator_trend*.py`: 30 files, about 15,217 lines.
- `src/excel*.py`: 49 files, about 15,440 lines including `src/excel_export.py`.
- The longest operator-trend module names are near 100 characters and encode too many lifecycle states in filenames.

Recommended maintainability pass:

1. Group `operator_trend_closure_forecast_*` helpers behind 3-5 conceptual modules instead of many recursively named stages.
2. Keep compatibility imports stable while consolidating names.
3. Preserve the scoped mypy command in `.github/workflows/ci.yml` during the consolidation.
4. Verify with full pytest, Ruff, scoped mypy, `python3 -m src --help`, `python3 -m src.cli --help`, and `make workbook-gate`.

2026-05-09 implementation note:

- The first closure-forecast modernization pass added four conceptual facade modules and routed `operator_resolution_trend.py` through them.
- Compatibility imports remain stable; the original `operator_trend_closure_forecast_*` modules were not removed.
- Details are recorded in `docs/plans/2026-05-09-closure-forecast-modernization.md`.

2026-05-10 implementation note:

- The closure-forecast sequence is complete through reset-family consolidation and wrapper-retirement audit.
- The first workbook-surface modernization pass moved `CORE_VISIBLE_SHEETS` from `src/excel_export.py` into `src/excel_workbook_helpers.py` while preserving compatibility through `src/excel_export.py`.
- The second workbook-surface modernization pass moved default workbook structure wiring into `src/excel_export_registry_helpers.py`; `src/excel_export.py` still re-exports the structure constants for compatibility.
- The third workbook-surface modernization pass moved default workbook build-step executor wiring into `src/excel_export_registry_helpers.py`.
- The fourth workbook-surface modernization pass moved default workbook finalization wiring into `src/excel_export_registry_helpers.py`.
- The workbook/exporter lane should pause unless future discovery finds another clear adapter boundary; broad sheet-rendering rewrites remain out of scope.
- Details are recorded in `docs/plans/2026-05-10-excel-workbook-contract-modernization.md`.

2026-05-11 implementation note:

- The recurring-review queue now supports operator acknowledgment capture: `--acknowledge-target <repo> --acknowledge-kind <type> --acknowledge-reviewer <name> --acknowledge-note <text>` writes to `output/operator-acknowledgments-<username>.json` and filters the change from both `material_changes` and `review_targets` on the next read.
- The filter is applied on both the fresh-bundle path (`build_review_bundle` in `src/recurring_review.py`) and the cached-report early-return path (`normalize_review_state` in `src/operator_control_center.py`), so `--control-center` reflects new acknowledgments without requiring a fresh full audit.
- Each ack stores a directional signature (security old/new label, lens-delta sign, tier old/new) so a regression in the opposite direction still surfaces.
- Sibling-key suppression: a single security posture movement emits both a `security-change` and a `lens-delta` for `security_posture` with distinct `change_key`s; acknowledging either now also captures a paired ack for the sibling, so one CLI invocation clears one logical event.
- Incidental fix: `src/recurring_review._change` for lens-delta had `details={"lens": ..., "delta": lens_delta, **item}` where the spread clobbered `delta` with the parent's overall-score delta; reordering restores per-lens values. Signature derivation also falls back through `details.lens_deltas[lens]` so reports generated before the fix can still be acknowledged.
- Live verification: the residual GithubRepoAuditor lens-change item from the post-PR-#155/#156 healthy state was successfully acknowledged and dropped from the ready queue.
- Shipped via PR #157 (initial flag), PR #158 (sibling-key suppression), and a defensive-defaults follow-up that addresses the two Codex review comments left on PR #157: `directional_signature` now returns a stable details fingerprint for unhandled change kinds (hotspot-change, campaign-drift, governance-drift, rollback-exposure) instead of `{}`, so acknowledging one no longer silently suppresses materially different later events; `_apply_acknowledgment_filter` now keeps `review_targets` for repos that still have unacknowledged material_changes, only dropping targets when every change for the repo has been acknowledged.

## Follow-Ups

1. Complete manual desktop Excel signoff for the generated workbook if this rehearsal becomes a release record.
2. Reduce GitHub security endpoint warning noise; expected 403/404 responses from code/secret-scanning alert endpoints should be summarized or quieted without hiding real API outages.
3. Use `python3 -m src` or the installed `audit` console script after `pip install -e ".[dev,config]"`; PR #122 restored `python3 -m src.cli --help` behavior.
4. Start Phase 123 only after explicit catalog eligibility and approval-center readiness exist.
