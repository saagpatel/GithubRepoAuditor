# Architecture

GitHub Repo Auditor is now a workbook-first portfolio operating system, not just a repo scoring CLI. The core product loop is:

1. run `audit <github-username> --doctor` when setup or baseline health is in doubt
2. run `audit <github-username> --html` to regenerate the shared artifact set
3. use the workbook as the primary read
4. use `audit <github-username> --control-center` for read-only operator triage
5. move into Action Sync only when the local story is already settled

The same weekly story is rendered across workbook, Markdown, HTML, review-pack, and scheduled handoff. The workbook remains the flagship surface, while the other artifacts mirror the same compressed interpretation so operators do not have to relearn the product by surface.

The weekly packaging seam now has an explicit structured contract, `weekly_story_v1`, finalized through `src/weekly_packaging.py` and exposed by `build_weekly_review_pack(...)`. That contract gives the visible weekly surfaces one shared summary, next-step, section order, and evidence-strip model instead of letting each renderer invent its own condensed story. The current release also adds a bounded approval-aware weekly overlay in `src/weekly_scheduling_overlay.py`, but that overlay still lives inside the same weekly contract instead of creating a second recommendation engine.

Phase 107 adds one more bounded read model on top of that same weekly seam: `weekly_command_center_digest_v1` in `src/weekly_command_center.py`. The digest is derived from `weekly_story_v1`, the latest operator summary, and the current portfolio-truth snapshot. It is explicitly report-only and workbook-first. Its job is to give a future weekly loop one canonical digest artifact without creating a second weekly authority or widening automation power.

The portfolio layer now has its own explicit truth contract too. `--portfolio-truth` builds a versioned machine-readable snapshot for the broader `/Users/d/Projects` workspace and treats the legacy markdown registry/report files as derived compatibility surfaces rather than as canonical inputs.

Phase 104 extends that contract with a minimum-context recovery layer. The truth snapshot now distinguishes `none`, `boilerplate`, `minimum-viable`, `standard`, and `full`, and the workspace recovery workflow writes context only into one primary repo-local file (`CLAUDE.md` first, otherwise `AGENTS.md`) instead of inventing a second mutable database for portfolio context.

Phase 106 extends the truth layer again with a normalized operating-path contract. Stable path semantics now live in one machine-facing seam instead of being split across portfolio catalog entries, maturity programs, tactical collections, and renderer-local wording. The stable path vocabulary is `maintain`, `finish`, `archive`, and `experiment`; `investigate` exists only as a temporary derived override when confidence is too weak to trust the stable path presentation.

## Product Shape

The shipped system now has five major layers:

- portfolio audit and scoring
- workbook-first review and shared surface parity
- operator control-center and follow-through state
- Action Sync execution guidance
- warehouse-backed history, regeneration, and trend work

That means the architecture is intentionally split between raw state assembly and compressed presentation, but the code boundaries are still under active cleanup pressure. The current module map is good enough to explain the shipped system, not yet the final maintainable shape.

## Core Entry Paths

### `audit`

`src/cli.py` remains the single entrypoint. It keeps one flag-based command surface and packages the product around four guidance modes:

- `First Run`
- `Weekly Review`
- `Deep Dive`
- `Action Sync`

The CLI does not create separate execution engines for those modes. The modes are packaging and guidance layers over the same audit/report pipeline.

### `--doctor`

`--doctor` is the preflight and environment health path. It validates setup, credentials, workbook prerequisites, output paths, and baseline health before operators invest time in a full run.

### `--control-center`

`--control-center` is the read-only operator entrypoint. It consumes the latest report plus warehouse-backed history to assemble one current triage view without running a new audit.

Phase 107 extends that same read-only path. A control-center refresh now also writes `weekly-command-center-<username>-<date>.json` plus `.md`, so the paused weekly loop has one bounded digest contract that already speaks in terms of truth, trust, and path attention.

### `--portfolio-truth`

`--portfolio-truth` is the workspace-truth entrypoint. It does not run the GitHub audit pipeline. Instead it scans the local workspace, reconciles declared catalog metadata with local activity and context signals, writes `portfolio-truth-latest.json` plus a dated history snapshot, and regenerates the external compatibility artifacts for the shared project registry and portfolio audit report.

### `--portfolio-context-recovery`

`--portfolio-context-recovery` is the bounded workspace write path for Phase 104. It freezes the active/recent weak-context cohort from the truth snapshot, writes dry-run recovery plan artifacts into `output/`, skips dirty and temporary repos automatically, and can apply managed context blocks plus bounded catalog seeds before regenerating the truth snapshot and compatibility outputs.

## Source Of Truth Modules

The current module boundaries are documented enough to guide work, but they still carry known concentration risk:

- `src/operator_control_center.py`
  Public façade and orchestration layer for control-center snapshot building.
- `src/operator_snapshot_packaging.py`
  Operator summary assembly, handoff packaging, and control-center artifact payload shaping.
- `src/operator_decision_quality.py`
  Versioned `decision_quality_v1` contract assembly, historical downgrade rules, and the single ownership seam for decision-quality derivation.
- `src/operator_follow_through.py`
  Follow-through enrichment, projection, and follow-through summary families.
- `src/operator_resolution_trend.py`
  Resolution-trend, trust, closure-forecast, calibration, and queue-history reasoning.
- `src/operator_control_center_rendering.py`
  Markdown rendering for the control-center artifact.
- `src/weekly_command_center.py`
  Report-only weekly digest contract and artifact rendering for the bounded command-center loop.
- `src/report_enrichment.py`
  Raw `weekly_pack` assembly plus the compatibility façade that hands off to the extracted weekly packaging seam.
- `src/weekly_packaging.py`
  Shared weekly contract finalization, compact explainability, and parity layer for workbook, Markdown, HTML, review-pack, and scheduled handoff.
- `src/action_sync_readiness.py`
  Readiness-stage logic for deciding whether a campaign should stay local, preview next, apply next, or stop for drift/blockers.
- `src/action_sync_packets.py`
  Execution handoff logic that turns a campaign into an `Apply Packet` with blockers, rollback posture, and command hints.
- `src/action_sync_outcomes.py`
  Post-apply monitoring logic that judges whether a recent sync is holding, drifting back, reopening, or still needs monitoring.
- `src/action_sync_tuning.py`
  Bounded tie-break layer that uses post-apply history to rank tied campaigns without changing stage precedence.
- `src/approval_ledger.py`
  Local approval workflow synthesis, fingerprinting, approval receipts, and approval-center packaging.
- `src/intervention_ledger.py`
  Cross-run repo intelligence synthesis that connects intervention history, recurring pressure, hotspot persistence, scorecard direction, and campaign aftermath.
- `src/implementation_hotspots.py`
  Repo-level implementation pressure and “where to start” guidance.
- `src/warehouse.py`
  Persistence, history loading, and compatibility handling for regenerated reports and historical trend work.
- `src/portfolio_truth_types.py`
  Versioned public truth contract for workspace projects.
- `src/portfolio_truth_sources.py`
  Safe local workspace, legacy-registry, and optional Notion source adapters for portfolio truth generation.
- `src/portfolio_truth_reconcile.py`
  Field-by-field precedence, derived status mapping, and truth snapshot assembly.
- `src/portfolio_truth_validate.py`
  Truth contract, compatibility, and external-path safety validation.
- `src/portfolio_truth_render.py`
  Compatibility rendering for `project-registry.md` and `PORTFOLIO-AUDIT-REPORT.md`.
- `src/portfolio_truth_publish.py`
  Publish orchestration with temp-file staging, validation, and replace-on-success semantics.
- `src/portfolio_context_contract.py`
  Semantic contract for minimum-viable context, accepted heading aliases, managed context blocks, and context-band classification.
- `src/portfolio_context_recovery.py`
  Frozen-cohort planning, dirty/temp skip rules, managed context block application, and bounded catalog seed handling for workspace recovery.
- `src/portfolio_pathing.py`
  Single owner for normalized operating-path derivation, confidence, override, and rationale assembly.

This separation is deliberate, but it is not “finished architecture”:

- operator state stays raw and evidence-rich
- report enrichment owns user-facing wording and parity
- Action Sync modules each own one layer of the execution story

## Operating Path Normalization

Phase 106 turns path-like portfolio semantics into one explicit truth-layer contract. Before this phase, the repo already had path-adjacent concepts in several places:

- declared intent via `intended_disposition`
- scorecard and maturity semantics via `maturity_program` and `target_maturity`
- tactical prioritization collections such as `finish-next` and `archive-soon`
- renderer-local weekly/report wording

Those concepts remain useful, but they no longer compete as separate machine-facing path owners.

The architecture rule is now:

- declared portfolio metadata stays in the catalog
- scorecards still own maturity evaluation
- tactical collections remain derived views
- `src/portfolio_pathing.py` normalizes stable path, temporary override, confidence, and rationale
- the truth snapshot is the one machine-facing surface that other renderers consume

The normalized path contract is intentionally strict:

- stable declared `operating_path` is one of `maintain`, `finish`, `archive`, or `experiment`
- `path_override` may currently only be `investigate`
- contradictory or weak inputs lower `path_confidence` and extend `path_rationale`
- weak confidence never silently rewrites the stable path
- tactical views may filter or group by path, but they may not redefine it

This keeps path semantics advisory and portable without reopening queue, approval, automation, or command authority.

## Portfolio Risk Overlay

Phase 108 adds a structured risk overlay on top of the shipped truth, context, path, and trust layers. `src/portfolio_risk.py` is the single owner of risk tier derivation. Risk tiers are `elevated`, `moderate`, `baseline`, and `deferred`. The overlay is advisory-only and derives from already-present truth fields — no new data collection.

Risk factors are accumulated during reconciliation and written into `RiskFields` on each `PortfolioTruthProject`. Compound factor thresholds keep signal gradation useful: `elevated` requires three or more factors, or the specific compound pair `weak-context-active + investigate-override`. Most repos land at `moderate` or `baseline`. Archived and stale-non-maintain repos are short-circuited to `deferred`.

The weekly command center digest surfaces risk posture via `risk_posture.elevated_count`, `risk_posture.risk_tier_counts`, and `risk_posture.top_elevated`, and renders a `## Risk Posture` section. Risk data is advisory-only and does not widen any automation or approval authority.

## Cross-Repo Doctor Standard

Phase 108 standardizes a minimal doctor/release-check contract for strategic repos. The standard defines `full` and `basic` tiers with stack-specific patterns. Documented in `docs/doctor-release-standard.md`.

`declared.doctor_standard` is set in the catalog for repos that have adopted the standard. `risk.doctor_gap` is a derived boolean that flags strategic repos missing a declared standard. The standard is advisory-only — it documents expected commands and patterns, does not enforce them automatically.

The active roadmap already treats two cleanup tracks as real dependencies for later feature work:

- Phase 99 extracted the weekly packaging seam into `src/weekly_packaging.py`, but `src/report_enrichment.py` still remains a broad raw-assembly module that should not absorb new weekly feature growth casually
- Phase 100 extracted the highest-risk operator subsystems into dedicated modules, but later approval work should still land on those bounded seams instead of rebuilding concentration inside the façade

## Shared Artifact Model

The generated artifact set is intentionally parallel:

- workbook: primary operating surface
- Markdown: readable text export
- HTML: interactive dashboard and shareable weekly surface
- review-pack: compact analyst/operator briefing
- JSON: machine-readable source artifact
- scheduled handoff: automation-safe weekly summary

Those surfaces should not invent different meanings. They all consume the same enriched weekly summary layer so headings, summary lines, and next-step guidance stay aligned.

The shared-weekly rule is now explicit:

- workbook, Markdown, HTML, review-pack, and scheduled handoff should all read from the same `weekly_story_v1` structure
- renderer-specific formatting is still allowed
- renderer-specific section selection, local winner selection, and ad hoc summary invention are not
- weekly-facing summary slots such as workbook Dashboard, Executive Summary, and shared run-change summaries should resolve their decision/why/next-step values from that same weekly story before falling back to raw operator summaries

`scheduled_handoff` is inside that shared contract, but it still carries bounded fallback logic when older report payloads do not have the newer weekly packaging fields. That fallback is a compatibility seam, not a second weekly authority.

## Operator Model

The operator system has two architectural layers:

- raw operator state orchestration in `src/operator_control_center.py`
- extracted operator subsystem logic in:
  - `src/operator_resolution_trend.py`
  - `src/operator_follow_through.py`
  - `src/operator_snapshot_packaging.py`
  - `src/operator_control_center_rendering.py`
- compressed weekly packaging in `src/weekly_packaging.py`

The operator façade keeps:

- queue/bootstrap orchestration
- warehouse-backed history loading
- Action Sync / approval bundle orchestration
- public control-center entrypoints

The extracted operator layers keep:

- trust and closure-forecast reasoning
- follow-through projections and summaries
- operator handoff and summary packaging
- rendered control-center Markdown output

The packaging layers expose the primary workbook-friendly story:

- headline
- queue pressure
- operator focus buckets
- follow-through checkpoints
- operator outcomes and effectiveness
- structured weekly sections with compact evidence items

That split keeps the workbook fast to read without losing the historical or machine-facing detail underneath.

## Implementation Hotspots

Implementation hotspots are now a first-class decision aid. They help answer where the operator should start inside a repo after the broader weekly story already says which repos matter most.

Hotspot guidance is descriptive only:

- it does not change queue ordering by itself
- it gives repo-level starting points
- it complements scorecards, maturity gaps, and operator focus rather than replacing them

## Operator Outcomes And Effectiveness

The product now measures whether recent operator activity appears to be helping the portfolio:

- outcomes describe whether pressure and follow-through are improving
- effectiveness describes whether recommendations are validating cleanly or becoming noisy

These are warehouse-backed descriptive summaries. They inform the weekly read but do not create a new scorecard or trust engine.

## Decision Quality And Trust Calibration

Phase 105 adds a bounded trust-contract layer on top of the existing effectiveness and calibration evidence. The goal is not to invent a second recommendation engine. The goal is to make the existing trust posture explicit, reusable, and historically comparable.

The new contract is `decision_quality_v1`. It is assembled in `src/operator_decision_quality.py`, stored inside `operator_summary`, and also persisted as a compact warehouse-backed summary so later runs do not have to scrape prose to compare recommendation quality.

`decision_quality_v1` is intentionally narrow:

- it summarizes measured recommendation quality and trust posture
- it exposes downgrade reasons and a `human_skepticism_required` flag
- it carries a hard `authority_cap` of `advisory-only`
- it does not grant stronger automation, approval, or execution rights

The architecture rule for this layer is strict:

- raw evidence may come from operator history, calibration history, trend history, and current operator state
- `src/operator_decision_quality.py` is the only owner that turns that evidence into a decision-quality contract
- workbook, Markdown, HTML, review-pack, scheduled handoff, and control-center surfaces consume the same contract through packaged summary fields instead of recomputing trust locally
- older warehouse runs that predate the contract are explicitly downgraded to `insufficient-data` rather than guessed into compatibility

This keeps decision quality descriptive and measured, while preserving the existing authority boundaries:

- `weekly_story_v1` remains the only weekly authority
- Action Sync posture remains bounded by existing readiness and approval seams
- decision quality may add caution, skepticism, or downgrade language
- decision quality may not widen command exposure or execution posture

## Action Sync Model

Action Sync now has three operational layers plus one bounded recommendation overlay.

### 1. `Action Sync Readiness`

Readiness answers whether the campaign should:

- stay local
- preview next
- apply next
- stop for blockers
- stop for drift review

This is the first operational gate.

### 2. `Apply Packet`

The apply packet is the execution handoff. It packages:

- execution state
- blockers
- rollback posture
- preview command
- apply command when safe

This is still descriptive. It never auto-applies.

### 3. `Post-Apply Monitoring`

Post-apply monitoring closes the loop after execution. It answers whether a recent apply is:

- holding clean
- drifting back
- reopening
- still inside a short monitoring window
- carrying rollback concern

This is the outcome-tracking layer.

### bounded recommendation overlay: `Campaign Tuning`

Phase 89 added one bounded overlay on top of the three operational layers.

`Campaign Tuning`:

- only uses observed post-apply track record
- only breaks ties inside the same readiness or execution group
- never changes queue order
- never changes write authority
- never moves a weaker stage ahead of a stronger stage

The visible pick for that layer is `Next Tie-Break Candidate`.

## Historical Portfolio Intelligence

Phase 91 adds one bounded historical layer on top of the current workbook and operator story: `Historical Portfolio Intelligence`.

It is powered by the `Intervention Ledger`, which connects:

- recurring operator attention
- implementation hotspot recurrence
- repo scorecard direction
- Action Sync aftermath that intersects with the repo

This layer is descriptive only. It does not create:

- a new queue
- a new score
- a new writeback authority

Instead it explains whether a repo currently looks:

- relapsing
- under persistent pressure
- improving after intervention
- holding steady

Architecturally, this keeps the split clean:

- `src/portfolio_intelligence.py` remains the current-state portfolio layer
- `src/intervention_ledger.py` owns cross-run historical synthesis
- `src/operator_control_center.py` carries those results into `operator_summary` and queue items
- `src/report_enrichment.py` packages the same historical story across workbook, Markdown, HTML, review-pack, and scheduled handoff

## Weekly Story Contract

The visible weekly surfaces now share one section-based contract:

- `headline`
- `decision`
- `why_this_week`
- `next_step`
- `section_order`
- `sections[]`

Each section is intentionally compact:

- `id`
- `label`
- `state`
- `headline`
- `next_step`
- `reason_codes[]`
- `evidence_items[]`

That contract is not a new source of truth for raw portfolio priority. It is the shared explanation layer that sits on top of the raw operator, Action Sync, and enrichment state so the visible weekly artifacts stay aligned while remaining easier to scan.

The tracked release boundary now includes one bounded approval-aware weekly scheduling overlay. That overlay may promote approval review or follow-up work inside `weekly_story_v1`, but only when blocked or urgent portfolio pressure is not active. It is not a second weekly authority and it does not rewrite `operator_queue`, `primary_target`, or raw operator recommendation state.

## Warehouse And Regeneration

Warehouse-backed history is now part of the normal architecture, not an optional afterthought.

The warehouse supports:

- control-center regeneration from prior runs
- operator outcomes and effectiveness history
- Action Sync readiness, packets, outcomes, and tuning summaries
- Historical Portfolio Intelligence and intervention-ledger snapshots
- weekly trend work without re-auditing every repo

Historical compatibility remains a design constraint. Older rows and older reports must stay readable even when newer additive fields exist.

## Approval Workflow

Phase 93 and Phase 101 together add one local, artifact-first approval layer: `Approval Workflow`.

That layer does not widen write authority. It exists to answer:

- what needs review now
- what needs re-approval because the fingerprint changed
- what is approved but still waits on an explicit manual apply
- what is still approved but now needs a local recurring follow-up review soon
- what is blocked for reasons approval alone cannot solve

Architecturally:

- `src/approval_ledger.py` owns approval synthesis and fingerprinting
- `src/approval_ledger.py` now also derives approval freshness from the latest tracked follow-up review event or the original approval timestamp fallback
- `src/operator_control_center.py` carries approval state into the operator summary and queue items
- `src/report_enrichment.py` passes the approval story through the shared weekly/report contracts, and `src/weekly_packaging.py` now carries the final weekly approval packaging across workbook, Markdown, HTML, review-pack, and scheduled handoff artifacts
- `src/warehouse.py` persists approval ledger snapshots, initial approval records, and append-only approval follow-up events while keeping legacy governance approvals readable

Approval stays local-authoritative:

- approval capture writes a local attestation
- recurring follow-up review writes a separate local review event
- it may regenerate shared artifacts
- it never auto-runs `--writeback-apply`
- explicit apply remains a separate human action

## Compatibility Rules

Phase 90 keeps these boundaries intact:

- no queue-order changes
- no lane-semantic changes
- no trust-policy rewrites
- no scorecard or scoring changes
- no write-authority expansion
- no warehouse-breaking field renames

Visible terminology can be cleaned up, but stored keys and historical loading paths must remain compatible.

## Current Directory Map

The most important current paths are:

```text
src/
  cli.py
  reporter.py
  review_pack.py
  web_export.py
  excel_export.py
  scheduled_handoff.py
  report_enrichment.py
  weekly_command_center.py       — report-only weekly digest contract and artifact rendering
  operator_control_center.py
  operator_decision_quality.py   — versioned decision_quality_v1 contract assembly
  operator_control_center_rendering.py
  operator_snapshot_packaging.py
  operator_resolution_trend.py
  implementation_hotspots.py
  action_sync_readiness.py
  action_sync_packets.py
  action_sync_outcomes.py
  action_sync_tuning.py
  action_sync_automation.py
  intervention_ledger.py
  warehouse.py
  portfolio_truth_types.py       — schema, dataclasses (Identity/Declared/Derived/Advisory/Risk/Truth)
  portfolio_truth_sources.py     — workspace inspection, context analysis
  portfolio_truth_reconcile.py   — multi-source reconciliation pipeline
  portfolio_truth_render.py      — truth table and registry markdown rendering
  portfolio_truth_validate.py    — snapshot validation
  portfolio_truth_publish.py     — JSON + markdown file publishing
  portfolio_catalog.py           — YAML catalog loading and normalization
  portfolio_context_contract.py  — context quality analysis contract
  portfolio_context_recovery.py  — context recovery planning and application
  portfolio_pathing.py           — operating path derivation
  portfolio_risk.py              — risk tier derivation (Phase 108)

docs/
  architecture.md
  doctor-release-standard.md     — doctor/release-check standard for strategic repos
  modes.md
  weekly-review.md
  writeback-safety-model.md
  plans/

output/
  *.json
  *.md
  *.html
  *.xlsx
```

## Design Intent

## Automation Guidance

Phase 92 adds one bounded execution-guidance layer on top of the existing Action Sync and historical stack: `Automation Guidance`.

Its job is narrow:

- classify whether the strongest next move is `preview-safe`, `apply-manual`, `approval-first`, `follow-up-safe`, `manual-only`, or `quiet-safe`
- surface command hints only when those hints stay inside existing authority boundaries
- keep scheduled handoff and issue automation artifact-first rather than mutation-first

Architecturally:

- `src/action_sync_automation.py` owns the posture classification and safe-command packaging
- `src/operator_control_center.py` carries the posture into `operator_summary` and queue items
- `src/report_enrichment.py` packages the same wording across workbook, Markdown, HTML, review-pack, and scheduled handoff

This layer does not widen write authority:

- it does not auto-run `--writeback-apply`
- it does not create a second executor
- it does not change readiness, execution, monitoring, tuning, or historical-intelligence precedence

The current architecture is optimized for one outcome: make the weekly portfolio loop clear enough that operators can trust the workbook, understand the control-center, and only move into managed execution when the local story is already coherent.

That is the baseline the next roadmap arc should reassess after the bounded automation phase is complete.
