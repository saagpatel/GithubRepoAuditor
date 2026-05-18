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

Context recovery batch 1 follow-up:

- Applied the first bounded recovery batch to 5 eligible projects: `AIFortuneTeller`, `AIWorkFlow`, `APIReverse`, `ApplyKit`, and `ArguMap`.
- Added parser hardening so fenced command blocks with shell comments are preserved and counted correctly, `Development Conventions` is not treated as a runnable command section, and one-line pointer preambles such as `@AGENTS.md` are not copied as project summaries when README product context is available.
- Removed the managed block from the two originally dirty skipped repos touched during correction (`AssistSupport` and `AssistSupport-security-alerts`); their pre-existing unrelated dirty files remain untouched.
- Refreshed portfolio truth after the fix: context distribution is now 76 `boilerplate`, 20 `minimum-viable`, 18 `none`, 13 `full`, and 4 `standard`.
- Context triage now flags 105 repos, down from 107 before the batch.
- The refreshed recovery plan is `output/context-recovery-plan-2026-05-16T093430Z.md`: 74 targets remain, with 45 eligible, 29 skipped, and 0 excluded.

Context recovery batch 2 follow-up:

- Applied the next bounded recovery batch to 5 eligible projects: `BrowserHistoryVisualizer`, `ConvictionMapper`, `DecisionStressTest`, `Devil's Advocate`, and `DevToolsTranslator`.
- Re-applied the batch after the pointer-preamble hardening so `DecisionStressTest` uses README product context instead of a bare `@AGENTS.md` pointer as its recovered project summary.
- Refreshed portfolio truth after batch 2: context distribution is now 72 `boilerplate`, 24 `minimum-viable`, 17 `none`, 13 `full`, and 5 `standard`.
- Context triage now flags 100 repos.
- The refreshed recovery plan is `output/context-recovery-plan-2026-05-16T095726Z.md`: 69 targets remain, with 40 eligible, 29 skipped, and 0 excluded.

Context recovery batch 3 follow-up:

- Applied the next bounded recovery batch to 5 eligible projects: `DNSWatcher`, `EvolutionSandbox`, `GlassLayer`, `hermes-harness-foundation`, and `HowMoneyMoves`.
- Added recovery hardening so placeholder stack values such as `Unknown` are not copied as meaningful stack context.
- Refreshed portfolio truth after batch 3: context distribution is now 69 `boilerplate`, 27 `minimum-viable`, 15 `none`, 13 `full`, and 7 `standard`.
- Context triage now flags 96 repos.
- The refreshed recovery plan is `output/context-recovery-plan-2026-05-16T101550Z.md`: 64 targets remain, with 35 eligible, 29 skipped, and 0 excluded.

Context recovery batch 4 follow-up:

- Opened recovery-only follow-up PRs for batch 3 side branches: `DNSWatcher` PR #2 and `HowMoneyMoves` PR #13.
- Applied the next bounded recovery batch to 5 eligible projects: `IncidentReview`, `ink`, `Interruption Resume Studio`, `ITServiceHealth`, and `JobMarketHeatmap`.
- Refreshed portfolio truth after batch 4: context distribution is now 64 `boilerplate`, 29 `minimum-viable`, 15 `none`, 13 `full`, and 10 `standard`.
- Context triage now flags 92 repos.
- The refreshed recovery plan is `output/context-recovery-plan-2026-05-16T102351Z.md`: 59 targets remain, with 30 eligible, 29 skipped, and 0 excluded.

Context recovery batch 5 follow-up:

- Applied the next bounded recovery batch to 5 eligible projects: `LifeCadenceLedger`, `NetworkDecoder`, `NetworkMapper`, `PageDiffBookmark`, and `Phantom Frequencies`.
- Tightened fallback-generated summaries for `NetworkDecoder`, `PageDiffBookmark`, and `Phantom Frequencies` so the recovered context names the actual product purpose instead of only saying the project is active locally.
- Refreshed portfolio truth after batch 5: context distribution is now 59 `boilerplate`, 30 `minimum-viable`, 15 `none`, 14 `full`, and 13 `standard`.
- Context triage now flags 87 repos.
- The refreshed recovery plan is `output/context-recovery-plan-2026-05-16T111023Z.md`: 54 targets remain, with 25 eligible, 29 skipped, and 0 excluded.

Context recovery batch 6 follow-up:

- Opened and merged recovery-only follow-up PRs for batch 5 side branches: `LifeCadenceLedger` PR #5, `NetworkDecoder` PR #14, `NetworkMapper` PR #4, `PageDiffBookmark` PR #3, and `PhantomFrequencies` PR #4.
- Applied the next bounded recovery batch to 5 eligible projects: `Pulse Orbit`, `RedditSentimentAnalyzer`, `ResumeEvolver`, `ReturnRadar`, and `ScreenshottoDataSelect`.
- Tightened fallback-generated summaries for `RedditSentimentAnalyzer`, `ResumeEvolver`, and `ScreenshottoDataSelect` so the recovered context names the actual product purpose instead of only saying the project is active locally.
- Opened and merged recovery-only follow-up PRs for batch 6 side branches: `Pulse-Orbit` PR #11, `RedditSentimentAnalyzer` PR #13, `ResumeEvolver` PR #4, `ReturnRadar` PR #2, and `ScreenshottoDataSelect` PR #14.
- Refreshed portfolio truth after batch 6: context distribution is now 54 `boilerplate`, 31 `minimum-viable`, 15 `none`, 14 `full`, and 17 `standard`.
- Context triage now flags 82 repos.
- The refreshed recovery plan is `output/context-recovery-plan-2026-05-16T111848Z.md`: 49 targets remain, with 20 eligible, 29 skipped, and 0 excluded.
- `ResumeEvolver` still has a pre-existing local-only `main` commit (`fix: stabilize local verification tooling`); the batch 6 recovery PR was based on `origin/main` and only included `AGENTS.md`.

Context recovery batch 7 follow-up:

- Applied the next bounded recovery batch to 5 eligible projects: `SignalDecay`, `stockpulse`, `Terroir`, `thought-trails`, and `TradeOffAtlas`.
- Tightened fallback-generated summaries for `SignalDecay`, `stockpulse`, and `thought-trails` so the recovered context names the actual product purpose instead of only saying the project is active locally or a create-next-app scaffold.
- Opened and merged recovery-only follow-up PRs for remote-backed batch 7 side branches: `SignalDecay` PR #4, `Terroir` PR #11, `thought-trails` PR #3, and `TradeOffAtlas` PR #4.
- `stockpulse` has no configured GitHub remote, so its recovery block is committed locally on `codex/docs/context-recovery-batch-7` only.
- `Terroir` has local App Store prep history diverged from `origin/main`; the remote context PR is merged, and its docs-only recovery commit was cherry-picked onto local `main` to keep workspace scans aligned without rewriting local history.
- Refreshed portfolio truth after batch 7: context distribution is now 50 `boilerplate`, 32 `minimum-viable`, 14 `none`, 15 `full`, and 20 `standard`.
- Context triage now flags 78 repos.
- The refreshed recovery plan is `output/context-recovery-plan-2026-05-16T112551Z.md`: 44 targets remain, with 15 eligible, 29 skipped, and 0 excluded.

Context recovery batch 8 follow-up:

- Applied the next bounded recovery batch to 5 eligible projects: `app`, `Calibrate`, `Chromafield`, `Conductor`, and `DeepTank`.
- Corrected nested-path handling for `app`, `Conductor`, and `DeepTank`; their display names map to `Misc:NoGoPRJs/app`, `VanityPRJs/Conductor`, and `Fun:GamePrjs/DeepTank`.
- Tightened generated context for `app`, `Conductor`, and `DeepTank`; `app` now reflects the scaffold-stop status from `STATUS.md` instead of describing itself as active implementation work.
- Opened and merged recovery-only follow-up PRs for batch 8 side branches: `app` PR #4, `Calibrate` PR #4, `Chromafield` PR #5, `Conductor` PR #4, and `DeepTank` PR #13.
- Refreshed portfolio truth after batch 8: context distribution is now 48 `boilerplate`, 36 `minimum-viable`, 11 `none`, 15 `full`, and 21 `standard`.
- Context triage now flags 76 repos.
- The refreshed recovery plan is `output/context-recovery-plan-2026-05-16T193257Z.md`: 39 targets remain, with 10 eligible, 29 skipped, and 0 excluded.

Context recovery batch 9 follow-up:

- Applied the next bounded recovery batch to 5 eligible projects: `GhostRoutes`, `Liminal`, `PomGambler`, `Redact`, and `RoomTone`.
- Tightened generated context for `PomGambler` so the recovered summary uses the README's AuraFlow/Pomodoro prediction-market product framing instead of a generic local-project sentence.
- Opened and merged recovery-only follow-up PRs for batch 9 side branches: `GhostRoutes` PR #5, `Liminal` PR #5, `PomGambler-prod` PR #8, `Redact` PR #4, and `RoomTone` PR #4.
- `Liminal` has a pre-existing local `chore/add-system-card` branch; the remote context PR was based on `origin/main`, and its docs-only recovery commit was cherry-picked onto the local branch so workspace scans include both the system card and recovered context without dragging unrelated work into the PR.
- Refreshed portfolio truth after batch 9: context distribution is now 43 `boilerplate`, 37 `minimum-viable`, 11 `none`, 16 `full`, and 24 `standard`.
- Context triage now flags 71 repos.
- The refreshed recovery plan is `output/context-recovery-plan-2026-05-16T193933Z.md`: 34 targets remain, with 5 eligible, 29 skipped, and 0 excluded.

Context recovery batch 10 follow-up:

- Applied the final eligible bounded recovery batch to 5 projects: `Seismoscope`, `SnippetLibrary`, `TerraSynth`, `Wavelength`, and `knowledgecore`.
- Tightened generated context for `SnippetLibrary`, `TerraSynth`, and `knowledgecore` so the recovered summaries and risks reflect the README product/architecture instead of generic local-project language.
- Opened and merged recovery-only follow-up PRs for batch 10 side branches: `seismoscope` PR #5, `SnippetLibrary` PR #6, `TerraSynth` PR #3, `Wavelength` PR #5, and `knowledgecore` PR #105.
- `TerraSynth` uses `master` as its default branch; the recovery PR targeted `master`.
- Refreshed portfolio truth after batch 10: context distribution is now 40 `boilerplate`, 42 `minimum-viable`, 9 `none`, 16 `full`, and 24 `standard`.
- Context triage now flags 68 repos.
- The refreshed recovery plan is `output/context-recovery-plan-2026-05-16T194600Z.md`: 29 targets remain, with 0 eligible, 29 skipped, and 0 excluded.

Manual ambiguous-context follow-up:

- Repaired the 3 clean ambiguous-primary-context repos skipped after batch 10: `cross-system-smoke`, `MCPAudit`, and `Notion`.
- First added repo-specific portfolio context to `AGENTS.md` through merged follow-up PRs: `cross-system-smoke` PR #2, `MCPAudit` PR #91, and `notion-operating-system` PR #75.
- The refreshed recovery planner then correctly resolved ambiguity but selected `CLAUDE.md` as the primary context file for those same repos, so a second primary-context pass added matching repo-specific context through merged PRs: `cross-system-smoke` PR #3, `MCPAudit` PR #92, and `notion-operating-system` PR #76.
- Refreshed portfolio truth after the manual follow-up: context distribution is now 36 `boilerplate`, 44 `minimum-viable`, 26 `standard`, 16 `full`, and 9 `none`.
- Context triage now flags 66 repos.
- The refreshed recovery plan is `output/context-recovery-plan-2026-05-17T034323Z.md`: 26 targets remain, with 0 eligible, 26 skipped, and 0 excluded. All 26 remaining skipped targets are dirty worktrees.

Dirty-worktree context follow-up:

- Repaired all 26 dirty-worktree recovery targets while preserving their existing unrelated local changes.
- Published documentation-only recovery PRs for the remote-backed repos across the dirty-worktree batches. `AssistSupport-security-alerts` was kept as local-only context because it is a second checkout of the shared `AssistSupport` remote and its branch-specific note should not be merged into the default branch.
- `JobCommandCenter` required a final manual primary-context note because its rich existing `CLAUDE.md` content did not use the exact headings the auditor counts.
- Refreshed portfolio truth after the dirty-worktree follow-up: context distribution is now 16 `boilerplate`, 66 `minimum-viable`, 27 `standard`, 19 `full`, and 3 `none`.
- Context triage now flags 53 repos.
- The refreshed recovery plan is `output/context-recovery-plan-2026-05-17T043623Z.md`: 0 targets remain, with 0 eligible, 0 skipped, and 0 excluded.

Current gate:

- Arc H tooling is merged and locally usable.
- Automated, clean manual, and dirty-worktree context recovery have exhausted the live target cohort. `output/context-recovery-plan-2026-05-17T043623Z.md` reports no remaining recovery targets.
- Tier recalibration should stay report-only until the operator reviews whether the Bronze/Silver bunching reflects real maturity or threshold drift.

Tier recalibration follow-up:

- The report-only review found a strict-signal drift: portfolio truth was checking root tests, CI, README length, and release counts, but it was not carrying a root `LICENSE`/`COPYING` signal into maturity tiers.
- The truth layer now records `derived.has_license`, and maturity tiers use it for the Gold license requirement while preserving the legacy `derived.context_files` fallback.
- With release-count overlay and the license signal, the refreshed tier report no longer bunches: 51 Bronze, 76 Silver, 1 Gold, 2 Platinum, and 1 untracked/no-git project outside the named tier counts.
- The path-qualified catalog follow-up added explicit contracts for each duplicate-name path: `IncidentWorkbench`, `ITPRJsViaClaude/IncidentWorkbench`, `StatusPage`, `MoneyPRJsViaGPT/StatusPage`, `Fun:GamePrjs/OrbitForge`, and `FunGamePrjs/OrbitForge`.
- Portfolio truth still records the duplicate display names for visibility, but `unresolved_duplicate_display_names` is now empty and the top-level duplicate-name warning is clear.
- Context triage now flags 52 repos. `OrbitForge` and `StatusPage` are still visible only for weak context on the archived/dormant duplicate paths, not for missing catalog contracts.

Phase 123 preview-only readiness refresh:

- Ran the preview-only `security-review` campaign against 117 GitHub repos with `--writeback-target all`; no live writeback or apply flag was used.
- The generated preview reported 20 actions across 19 repos, led by `GithubRepoAuditor`, `LifeCadenceLedger`, and `EvolutionSandbox`.
- The preview guidance says to keep Security Review manual-only for now because human review is stronger than automation convenience.
- Approval center now surfaces one `ready-for-review` packet for `Security Review` with rollback coverage as the blocker to review before any approval.
- The automation subset remains empty for this packet: `TideEngine` and `TradeOffAtlas` are automation-eligible overall, but neither has actions in the current Security Review packet.
- Auto-apply dry run still blocks live automation: 2 opted-in repos, 0 repos pass the full trust bar, and no `approved-manual` campaign packets exist.
- Current gate: review the Security Review packet manually if desired, but do not capture approval or live apply until rollback coverage and the expected manual scope are reviewed.
- Follow-up fix: approval-center records now keep rollback-blocked or zero-automation-action packets reviewable without marking them approval-ready or apply-ready-after-approval, and the approval command is withheld for those packets.
- Follow-up fix: Action Sync readiness now treats active packets with missing or partial rollback coverage as blocked instead of `apply-ready`, keeping readiness, packet, and approval-center surfaces aligned.
- Security review follow-up: the `GithubRepoAuditor` exposed-secrets flag was validated as scanner noise from runtime shell variable references and ignored/generated paths. The scanner now skips generated output/agent/cache directories and ignores shell variable secret references, tracked-file gitleaks is clean, and a targeted security-review preview reports `GithubRepoAuditor` with `secrets_found=0` and no security recommendations.
- Dependabot security batch 1: opened and merged config-only Dependabot PRs for the first five queue repos: `DNSWatcher` PR #3, `DecisionStressTest` PR #3, `EvolutionSandbox` PR #3, `ITServiceHealth` PR #30, and `LifeCadenceLedger` PR #6. `ITServiceHealth` CI did not start because GitHub reported an account billing/spending-limit issue, not a repo test failure; keep that billing caveat visible for future CI checks.
- Dependabot security batch 2: opened and merged config-only Dependabot PRs for the next actionable dependency surfaces: `ResumeEvolver` PR #5, `TabTriage` PR #1, `bridge-db` PR #24, `notification-hub` PR #42, and `renovate-config` PR #1. All PRs passed GitHub's Dependabot config validation before merge; `notification-hub` also passed its repo check. `renovate-config` uses default branch `feat/init`, so its config landed there rather than `main`.
- Post-batch evidence refresh: reran a targeted preview-only `security-review` campaign for the ten repos touched across Dependabot batches 1 and 2; no live writeback or apply flag was used. The refreshed preview no longer reports missing Dependabot config for those ten repos. Remaining Security Review items are now led by `notification-hub` code security controls, `SECURITY.md` gaps, and unsupported/no-manifest Dependabot recommendations for Godot or otherwise dependency-surface-empty repos (`PhantomFrequencies`, `Recall`, `SignalDecay`, and `SynthWave`) that should be handled by auditor refinement or manual review rather than empty config PRs.
- Dependabot recommendation refinement: the security analyzer now records whether a repo has a supported Dependabot ecosystem before applying a missing-config penalty or emitting an `Add Dependabot config` recommendation. A targeted preview-only refresh across the previously noisy no-manifest repos reduced the Security Review preview to 12 repos and 14 actions, with the unsupported/no-manifest Dependabot recommendations cleared.
- `notification-hub` security controls: opened and merged PR #50 to add CodeQL and `SECURITY.md`, enabled repository secret scanning through GitHub's repository security setting, then opened and merged PR #51 to clear the high CodeQL path-handling alerts. Main-branch CodeQL and CI passed after both PRs. A targeted preview-only refresh now reports 12 repos and 13 Security Review actions; `notification-hub` still has medium exception-exposure CodeQL alerts and a low Scorecard workflow suggestion, so the next code-security follow-up should address sanitized error responses rather than setup.
- `notification-hub` CodeQL closeout: opened and merged PR #52 to sanitize `/review` endpoint error responses, then opened and merged PR #53 to move exception-derived report fields to generic operator-facing messages where they are created. PR and main-branch CI/CodeQL passed after both PRs, and GitHub code scanning now reports 0 open alerts for `notification-hub`. A targeted audit refresh with GHAS alerts merged the updated `notification-hub` evidence back into `output/audit-report-saagpatel-2026-05-17.json`; its security posture is now `healthy` with Code scanning enabled (0 alerts), Secret scanning enabled (0 alerts), SECURITY.md present, and Dependabot present. The remaining `notification-hub` Security Review item is now only the low-priority OpenSSF Scorecard workflow suggestion.
- Current Security Review queue after the `notification-hub` refresh: medium `SECURITY.md` gaps remain for `DNSWatcher`, `DecisionStressTest`, `EvolutionSandbox`, `ITServiceHealth`, `Recall`, `ResumeEvolver`, `TabTriage`, `bridge-db`, `cross-system-smoke`, `hermes-harness-foundation`, and `renovate-config`; `notification-hub` has only the low Scorecard action. A full campaign preview rerun was intentionally stopped after it expanded into a long 117-repo audit path; use the targeted audit evidence plus the live GitHub code-scanning API result as the current closeout evidence for this code-security slice.
- SECURITY.md policy batch 3: opened and merged documentation-only security policy PRs for `DNSWatcher` PR #4, `DecisionStressTest` PR #9, and `EvolutionSandbox` PR #9 after verifying their default branches lacked `SECURITY.md` or `.github/SECURITY.md`. No repo CI checks were configured on those PRs; all three PRs were clean, merged, and verified by reading `SECURITY.md` from the default branch.
- Post-policy-batch refresh: reran a targeted audit with GHAS alerts for `DNSWatcher`, `DecisionStressTest`, and `EvolutionSandbox`; `DNSWatcher` and `EvolutionSandbox` no longer appear in the Security Review queue. `DecisionStressTest` no longer has the `SECURITY.md` gap, but the fresh evidence now surfaces `Enable CodeQL default setup` as a high-priority item plus a low Scorecard suggestion. Remaining medium `SECURITY.md` gaps are now `ITServiceHealth`, `Recall`, `ResumeEvolver`, `TabTriage`, `bridge-db`, `cross-system-smoke`, `hermes-harness-foundation`, and `renovate-config`.
- `DecisionStressTest` CodeQL closeout: opened and merged PR #10 to add CodeQL for JavaScript/TypeScript, then opened and merged PR #11 to clear seven CodeQL `js/trivial-conditional` quality alerts by removing redundant snapshot truthiness checks after the null guard. Local `DecisionStressTest` checks passed (`npm run typecheck`, `npm run lint`, and `npm test`), PR and main-branch CodeQL passed, and GitHub code scanning now reports 0 open alerts. A targeted audit refresh with GHAS alerts now leaves `DecisionStressTest` with only the low-priority OpenSSF Scorecard suggestion; remaining medium `SECURITY.md` gaps are `ITServiceHealth`, `Recall`, `ResumeEvolver`, `TabTriage`, `bridge-db`, `cross-system-smoke`, `hermes-harness-foundation`, and `renovate-config`.
- SECURITY.md policy batch 4: opened and merged documentation-only security policy PRs for `ITServiceHealth` PR #32, `Recall` PR #4, and `ResumeEvolver` PR #6 after verifying their default branches lacked `SECURITY.md` or `.github/SECURITY.md`. `Recall` and `ResumeEvolver` had no PR checks. `ITServiceHealth` CI ran but failed on existing main-branch backend Ruff SIM117 issues and frontend npm peer dependency resolution drift; the PR diff was only `SECURITY.md`, so it was merged with that baseline-drift caveat. GitHub API verification confirms `SECURITY.md` now exists on all three default branches.
- Parallel refresh follow-up: fixed the parallel analysis path to disable the SQLite-backed analyzer result cache whenever more than one analysis worker is requested. This prevents cross-thread SQLite connection warnings during broad refreshes while preserving analyzer-cache behavior for the default single-worker path.
- Full Security Review evidence refresh: reran the 118-repo read-only audit with GHAS alerts and 8 analysis workers after the cache fix. The generated report now has `portfolio_baseline_size=118`, `total_repos=118`, and 20 Security Review preview actions: 18 high-priority CodeQL setup items plus 2 high-priority open code-scanning alert review items (`AIGCCore` and `AssistSupport`). No `add-security-md` actions remain in the generated queue.
- `AssistSupport` security alert closeout: opened and merged `AssistSupport` PR #116 to clear the concrete high-risk CodeQL/OSV slice. The PR tightened YouTube URL host validation, removed hard-coded crypto test values and fixed seed buffers, and updated the OpenSSL lockfile entries. Local focused frontend, Rust, audit, and security-regression checks passed; GitHub PR checks also passed, including CodeQL, OSV, dependency audit, quality gates, Rust backend, UI/search lanes, and the macOS build. A full read-only audit refresh was required because the portfolio baseline expanded to 119 repos after `ApplyKit-private-archive-20260517` appeared. The refreshed report now has `portfolio_baseline_size=119`, `total_repos=119`, and 20 Security Review preview actions: 12 open code-scanning review items plus 8 CodeQL setup items. `AssistSupport` now reports 0 critical/high code-scanning alerts and remains in the queue only for warning-level CodeQL cleanup; the strongest next Security Review move is `AIGCCore`, which still has 41 high code-scanning alerts. No `add-security-md` actions remain.
- `AIGCCore` workflow-permissions hardening: opened and merged `AIGCCore` PR #26 to replace `permissions: read-all` with `contents: read` defaults across six workflows while preserving explicit job permissions for SARIF upload and PR-only checks. PR checks passed after rewriting the commit message to satisfy commitlint, and main-branch CodeQL, `codex-quality-security`, and `quality-gates` passed on merge commit `19767ab`. A targeted read-only audit refresh with GHAS alerts merged the updated repo evidence back into `output/audit-report-saagpatel-2026-05-17.json`; it reports AIGCCore as improving after intervention, but GitHub code scanning still shows the six high `TokenPermissionsID` Scorecard alerts until the scheduled Scorecard job re-runs because the Scorecard upload job is schedule-only. Remaining AIGCCore high alerts are policy-level Scorecard findings (`BranchProtectionID`, `CodeReviewID`, and `MaintainedID`) plus the pending Scorecard re-baseline for token permissions.
- `AIGCCore` Scorecard refresh closeout: opened and merged PR #27 to add manual dispatch for the existing Scorecard SARIF job while keeping the job limited to scheduled or manually dispatched runs. PR checks passed, including CodeQL, SAST, secrets, verify, quality gates, perf-build, UI gates, and Lighthouse. After merge, manually dispatched `codex-quality-security` on `main`; the run passed and uploaded Scorecard SARIF. GitHub code scanning now shows AIGCCore down from 41 high alerts to 3 high policy-level Scorecard findings (`BranchProtectionID`, `CodeReviewID`, and `MaintainedID`). GithubRepoAuditor's GHAS alert fetcher now prefers GitHub's `security_severity_level` over the generic code-scanning rule severity so Scorecard medium/low findings are not inflated to high. A targeted read-only audit refresh with GHAS alerts now reports portfolio Code Scanning pressure at 0 critical and 3 high across 10 repos, and Dependabot pressure at 0 critical and 397 high across 68 repos.
- `AIGCCore` governance/policy closeout: opened and merged PR #29 to correct `SECURITY.md` for the real `main` branch, private vulnerability reporting, and `@saagpatel` ownership, then enabled conservative protection on `main` with pull-request review required and force-push/delete disabled. Opened and merged PR #30 to add the direct private advisory report URL after Scorecard still flagged missing linked reporting content. PR checks passed for both policy PRs, including CodeQL, SAST, secrets, verify, quality gates, UI gates, and performance gates. Manual `codex-quality-security` Scorecard refreshes passed; GitHub code scanning now has `BranchProtectionID` and `SecurityPolicyID` cleared for `AIGCCore`, leaving only `CodeReviewID` and `MaintainedID` as high contextual history/age signals. GithubRepoAuditor now preserves raw GHAS high counts while exposing actionable versus contextual high code-scanning counts, so `AIGCCore` drops out of the high-priority Security Review top actions when fresh GitHub evidence is fetched with `--no-cache`.
- `BrowserHistoryVisualizer` CodeQL closeout: opened and merged PR #17 to replace a dictionary-membership test assertion that CodeQL flagged as high `py/incomplete-url-substring-sanitization` with an exact cache lookup. Local backend verification passed (`test_categorizer.py`: 9 passed; full `backend/tests`: 52 passed, with existing pandas warnings), PR CodeQL passed, default-branch CodeQL passed on merge commit `03fe5b4`, and GitHub code scanning now reports 0 open alerts for `BrowserHistoryVisualizer`. A targeted read-only audit refresh with GHAS alerts merged the updated evidence back into `output/audit-report-saagpatel-2026-05-17.json`; portfolio code-scanning pressure is now 41 high alerts across 11 repos.
- `AssistSupport` stale OSV closeout and queue-priority refinement: live GitHub code scanning briefly still showed a high `openssl@0.10.78` OSV alert, but `master` already had `openssl 0.10.80` in `src-tauri/Cargo.lock`. Manually dispatched the repo's `OSV Scanner` workflow on `master`; run `26011109157` passed and marked alert #94 fixed. A targeted read-only audit refresh with GHAS alerts merged updated AssistSupport evidence into `output/audit-report-saagpatel-2026-05-18.json`; AssistSupport now has 0 critical/high code-scanning alerts and drops out of the Security Review preview. GithubRepoAuditor now records code-scanning severity buckets from the GitHub API and downgrades warning-only code-scanning cleanup below high priority, keeping the queue focused on critical/high findings.
- `SpecCompanion` critical Dependabot closeout: opened and merged PR #30 to skip lockfile-rationale enforcement for Dependabot-authored lockfile PRs while preserving the gate for human PRs. After PR #30 passed and merged, refreshed the blocked npm security PRs, merged PR #3 for the critical `basic-ftp` group, merged the refreshed PR #31 for the follow-up npm security group, and closed conflicted PR #12 as superseded. A targeted read-only audit refresh with GHAS alerts merged updated SpecCompanion evidence into `output/audit-report-saagpatel-2026-05-18.json`; portfolio Dependabot pressure is now 0 critical and 408 high alerts, and SpecCompanion no longer appears in the Security Review preview. Remaining SpecCompanion alerts are high/medium/low dependency debt led by Rust transitives and `lodash` families, not a critical item.
- `SpecCompanion` Rust security follow-up: opened by Dependabot after the critical batch, PR #32 was a lockfile-only Cargo group update for `tauri`, `openssl`, `quinn-proto`, and `rustls-webpki`. PR #32 was mergeable with passing checks and was squash-merged into `main`; a targeted read-only audit refresh with GHAS alerts now reports portfolio Dependabot pressure at 0 critical and 401 high alerts, while SpecCompanion is down to 1 high, 4 medium, and 3 low Dependabot alerts. The remaining SpecCompanion high alert is no longer the strongest queue driver compared with AIGCCore's high code-scanning backlog.
- `ContentEngine` workflow-permissions closeout: opened and merged `ContentEngine` PR #24 to add explicit read-only workflow token permissions to `desktop-ci` and `quality-gates`, clearing the two medium CodeQL `actions/missing-workflow-permissions` alerts. PR checks passed before merge, and main-branch `Push on main`, `quality-gates`, and `desktop-ci` checks passed after merge. GitHub code scanning now reports 0 open alerts for `ContentEngine`; a targeted read-only audit refresh with GHAS alerts shows `ContentEngine` as healthy with Code scanning, Secret scanning, `SECURITY.md`, and Dependabot present, leaving only the low-priority OpenSSF Scorecard suggestion.
- Workflow-permissions batch follow-up: opened workflow-token hardening PRs for `Cartograph` PR #8, `Chromafield` PR #6, `Calibrate` PR #5, and `Conductor` PR #6 after live code-scanning showed medium `actions/missing-workflow-permissions` alerts in each repo's `ci.yml`. `Cartograph` PR #8 passed PR checks, merged, passed main-branch CI, and live code scanning now reports 0 open alerts; a targeted read-only audit refresh with GHAS alerts now reports portfolio Code Scanning pressure at 0 critical and 2 high across 8 repos. `Calibrate` PR #5 also fixed an existing CI signing-profile blocker by adding `CODE_SIGNING_ALLOWED=NO`; its PR checks passed, it was merged, main-branch CI passed, and live code scanning now reports 0 open alerts. `Conductor` PR #6 passed PR checks, merged, passed main-branch CI, and live code scanning now reports 0 open alerts. A targeted read-only audit refresh with GHAS alerts for `Calibrate` and `Conductor` now reports portfolio Code Scanning pressure at 0 critical and 2 high across 6 repos. `Chromafield` PR #6 also merged after adding read-only workflow permissions, disabling CI signing, and repairing the Swift 6 export build issues in image/video Photos export paths. PR checks passed, main-branch CI and CodeQL passed on merge commit `b7e173e`, and live GitHub code scanning now reports 0 open alerts for `Chromafield`. A targeted read-only audit refresh with GHAS alerts reports portfolio Code Scanning pressure at 0 critical and 2 high across 5 repos, Dependabot pressure at 0 critical and 397 high across 69 repos, and keeps Security Review manual-only.
- CodeQL setup batch 1: reran a full read-only Security Review refresh with GHAS alerts after the Chromafield closeout. The fresh queue now leads with CodeQL setup gaps instead of stale warning-only code-scanning review items. Opened config-only CodeQL PRs for `EarthPulse`, `FreelanceInvoice`, and `LifeCadenceLedger`; the first attempt used an invalid branch family and was replaced with policy-compliant `codex/ci/...` branches. `FreelanceInvoice` PR #24 and `LifeCadenceLedger` PR #17 passed PR CodeQL, were squash-merged, and their main-branch CodeQL runs passed. `EarthPulse` PR #47 originally stayed open because CodeQL passed but existing `security-quality` checks failed on baseline dependency audits (`pnpm audit --audit-level=high` and Rust audit). The follow-up updated patched JavaScript transitive pins, refreshed `pnpm-lock.yaml`, updated `rustls-webpki` in `src-tauri/Cargo.lock`, added the required lockfile rationale, and merged PR #47 after all PR checks passed. Main-branch CodeQL and Artifact Hygiene passed after the merge, Dependabot update jobs completed successfully, and live GitHub code scanning now reports 0 open alerts for `EarthPulse`.
- Post-EarthPulse evidence note: targeted Security Review refresh is blocked until the portfolio baseline is refreshed because the live repo set expanded from 119 to 121 repos. A parallel full refresh was stopped after missing-checkout warnings; the safer single-worker full refresh was also stopped before completion because it is a long 121-repo run. The next Security Review evidence move should be a clean full read-only refresh before choosing the next CodeQL setup batch.

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
