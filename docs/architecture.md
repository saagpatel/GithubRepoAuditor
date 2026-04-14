# Architecture

GitHub Repo Auditor is now a workbook-first portfolio operating system, not just a repo scoring CLI. The core product loop is:

1. run `audit <github-username> --doctor` when setup or baseline health is in doubt
2. run `audit <github-username> --html` to regenerate the shared artifact set
3. use the workbook as the primary read
4. use `audit <github-username> --control-center` for read-only operator triage
5. move into Action Sync only when the local story is already settled

The same weekly story is rendered across workbook, Markdown, HTML, review-pack, and scheduled handoff. The workbook remains the flagship surface, while the other artifacts mirror the same compressed interpretation so operators do not have to relearn the product by surface.

## Product Shape

The shipped system now has five major layers:

- portfolio audit and scoring
- workbook-first review and shared surface parity
- operator control-center and follow-through state
- Action Sync execution guidance
- warehouse-backed history, regeneration, and trend work

That means the architecture is intentionally split between raw state assembly and compressed presentation.

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

## Source Of Truth Modules

The current module boundaries are intentionally explicit:

- `src/operator_control_center.py`
  Raw operator state assembly, queue shaping, priority logic, and follow-through families.
- `src/report_enrichment.py`
  Compressed wording and parity layer for workbook, Markdown, HTML, review-pack, and scheduled handoff.
- `src/action_sync_readiness.py`
  Readiness-stage logic for deciding whether a campaign should stay local, preview next, apply next, or stop for drift/blockers.
- `src/action_sync_packets.py`
  Execution handoff logic that turns a campaign into an `Apply Packet` with blockers, rollback posture, and command hints.
- `src/action_sync_outcomes.py`
  Post-apply monitoring logic that judges whether a recent sync is holding, drifting back, reopening, or still needs monitoring.
- `src/action_sync_tuning.py`
  Bounded tie-break layer that uses post-apply history to rank tied campaigns without changing stage precedence.
- `src/intervention_ledger.py`
  Cross-run repo intelligence synthesis that connects intervention history, recurring pressure, hotspot persistence, scorecard direction, and campaign aftermath.
- `src/implementation_hotspots.py`
  Repo-level implementation pressure and “where to start” guidance.
- `src/warehouse.py`
  Persistence, history loading, and compatibility handling for regenerated reports and historical trend work.

This separation is deliberate:

- operator state stays raw and evidence-rich
- report enrichment owns user-facing wording and parity
- Action Sync modules each own one layer of the execution story

## Shared Artifact Model

The generated artifact set is intentionally parallel:

- workbook: primary operating surface
- Markdown: readable text export
- HTML: interactive dashboard and shareable weekly surface
- review-pack: compact analyst/operator briefing
- JSON: machine-readable source artifact
- scheduled handoff: automation-safe weekly summary

Those surfaces should not invent different meanings. They all consume the same enriched weekly summary layer so headings, summary lines, and next-step guidance stay aligned.

## Operator Model

The operator system has two architectural layers:

- raw operator state in `src/operator_control_center.py`
- compressed operator packaging in `src/report_enrichment.py`

The raw layer keeps:

- queue lanes
- counts
- follow-through families
- review history
- calibration history
- governance and campaign readiness context

The compressed layer exposes the primary workbook-friendly story:

- headline
- queue pressure
- operator focus buckets
- follow-through checkpoints
- operator outcomes and effectiveness

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

## Warehouse And Regeneration

Warehouse-backed history is now part of the normal architecture, not an optional afterthought.

The warehouse supports:

- control-center regeneration from prior runs
- operator outcomes and effectiveness history
- Action Sync readiness, packets, outcomes, and tuning summaries
- Historical Portfolio Intelligence and intervention-ledger snapshots
- weekly trend work without re-auditing every repo

Historical compatibility remains a design constraint. Older rows and older reports must stay readable even when newer additive fields exist.

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
  operator_control_center.py
  implementation_hotspots.py
  action_sync_readiness.py
  action_sync_packets.py
  action_sync_outcomes.py
  action_sync_tuning.py
  action_sync_automation.py
  intervention_ledger.py
  warehouse.py

docs/
  architecture.md
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
