# Architecture

GitHub Repo Auditor is now a workbook-first portfolio operating system, not just a repo scoring CLI. The core product loop is:

1. run `audit <github-username> --doctor` when setup or baseline health is in doubt
2. run `audit <github-username> --html` to regenerate the shared artifact set
3. use the workbook as the primary read
4. use `audit <github-username> --control-center` for read-only operator triage
5. move into Action Sync only when the local story is already settled

The same weekly story is rendered across workbook, Markdown, HTML, review-pack, and scheduled handoff. The workbook remains the flagship surface, while the other artifacts mirror the same compressed interpretation so operators do not have to relearn the product by surface.

The weekly packaging seam now has an explicit structured contract, `weekly_story_v1`, finalized through `src/weekly_packaging.py` and exposed by `build_weekly_review_pack(...)`. That contract gives the visible weekly surfaces one shared summary, next-step, section order, and evidence-strip model instead of letting each renderer invent its own condensed story.

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

## Source Of Truth Modules

The current module boundaries are documented enough to guide work, but they still carry known concentration risk:

- `src/operator_control_center.py`
  Public façade and orchestration layer for control-center snapshot building.
- `src/operator_snapshot_packaging.py`
  Operator summary assembly, handoff packaging, and control-center artifact payload shaping.
- `src/operator_follow_through.py`
  Follow-through enrichment, projection, and follow-through summary families.
- `src/operator_resolution_trend.py`
  Resolution-trend, trust, closure-forecast, calibration, and queue-history reasoning.
- `src/operator_control_center_rendering.py`
  Markdown rendering for the control-center artifact.
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

This separation is deliberate, but it is not “finished architecture”:

- operator state stays raw and evidence-rich
- report enrichment owns user-facing wording and parity
- Action Sync modules each own one layer of the execution story

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

The tracked release boundary currently stops there. Approval-aware weekly scheduling remains a deferred design thread and is not a second weekly authority in the shipped architecture.

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
