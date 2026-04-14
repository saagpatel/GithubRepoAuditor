# GitHub Repo Auditor Roadmap: Phases 88-92

**Date:** 2026-04-12
**Current Status Snapshot:**
- Shipped through **Phase 92**
- Current baseline is `main`
- No open PRs
- Workbook automated gate passes; manual desktop Excel signoff remains a separate release step
- Only intentional local residue is untracked `.serena/`
- [2026-04-12-roadmap-phases-78-85.md](/Users/d/Projects/GithubRepoAuditor/docs/plans/2026-04-12-roadmap-phases-78-85.md) is now historical context only
- This `88-92` roadmap arc is now complete; the next phase should start by opening a new roadmap file and reassessing the next arc

---

## Executive Summary

GitHub Repo Auditor now has a strong operator loop:

- weekly review and control-center triage
- campaign readiness guidance
- apply-packet handoff
- managed writeback and GitHub Projects mirroring
- workbook, Markdown, HTML, review-pack, and scheduled handoff parity

The next roadmap arc has now closed the loop after execution, tuned tied campaign recommendations, cleaned up terminology, and connected longer-run repo history through the Intervention Ledger.

The healthiest next sequence is:

1. measure what happened after apply
2. use those outcomes to tune campaign guidance
3. clean up architecture and naming drift
4. connect history across hotspots, outcomes, and portfolio intelligence
5. expand automation only where the loop is already trustworthy

---

## Phase Closeout Standard

Every phase from Phase 88 onward is only complete when all of the following are done:

1. **Completion check**
   - Confirm every planned behavior shipped
   - Call out any explicit deferrals or scope cuts

2. **Verification check**
   - Record the commands that were run
   - Record the results
   - Record workbook manual signoff state explicitly

3. **Git / PR completion**
   - Create the branch
   - Create the commit
   - Open the PR
   - Merge the PR
   - Sync local `main` to `origin/main`
   - Confirm there are no open PRs remaining
   - Prune merged or stale local/remote branch references that are no longer needed

4. **Workspace cleanup**
   - Remove generated artifacts unless intentionally retained
   - Leave only intentional untracked files

5. **Phase handoff**
   - Summarize what the phase completed
   - State exactly what the next phase will target
   - Return to planning for the next phase before implementation starts

---

## Current Baseline

The shipped product shape now includes:

- workbook-first portfolio review
- read-only operator queue via `--control-center`
- shared wording and surface parity across JSON, Markdown, HTML, workbook, and review-pack outputs
- managed campaign/writeback flows across GitHub, Notion, and GitHub Projects mirroring
- implementation hotspot guidance
- operator effectiveness and outcomes summaries
- action sync readiness and apply-packet guidance
- post-apply monitoring
- bounded campaign tuning for same-stage recommendation ties

The Action Sync stack now has three operational layers:

- readiness
- apply packet
- post-apply monitoring

Phase 89 added one bounded recommendation overlay on top of those three layers:

- campaign tuning

That overlay uses post-apply history to break ties only when campaigns are already in the same readiness or execution group.

The main remaining gap is no longer actionability, outcome visibility, terminology coherence, or bounded historical synthesis.
It is helping the product say what execution guidance is safe to automate, what still requires manual review, and what should remain explicitly human-only.

---

## Phase 88: Action Sync Outcome Tracking + Post-Apply Monitoring

### Goal

Close the loop after apply by teaching the system to show whether a campaign:

- held cleanly
- drifted again
- reopened work
- needs rollback watch
- still needs follow-up monitoring

### Outcome

The operator loop should gain a clear post-apply layer built from recent campaign history, action runs, managed drift, rollback posture, and operator pressure history.

This phase should produce:

- campaign-level post-apply monitoring records
- one top-line monitoring summary for the report and operator summary
- per-item post-apply handoff lines in the queue
- parity across workbook, Markdown, HTML, review-pack, control-center, and scheduled handoff
- additive warehouse persistence for later tuning work

### Constraint

This phase stays descriptive and monitoring-oriented:

- no auto-apply behavior
- no new action system
- no queue ordering or trust-policy changes

---

## Phase 89: Outcome-Aware Campaign Tuning

### Goal

Use Phase 88 outcome history to improve campaign recommendations without changing the local-authoritative model.

### Target

The system should start showing which campaign types:

- reduce pressure reliably
- reopen often
- drift back quickly
- need more approval or rollback caution

This phase should stay bounded:

- tuning is a recommendation overlay, not a fourth Action Sync execution layer
- tuning may break ties inside the same readiness or execution group
- tuning must not move a weaker stage ahead of a stronger one
- queue order, lane semantics, trust policy, scoring, and write authority stay unchanged

### Constraint

Keep this descriptive first. Do not auto-retune campaign execution or add self-modifying behavior.

### Status

Shipped. Phase 89 added bounded recommendation tuning, warehouse persistence for campaign tuning snapshots, and surface parity for the new `Campaign Tuning` story.

---

## Phase 90: Architecture and Naming Coherence

### Goal

Bring the shipped product and the code/docs vocabulary back into alignment.

### Target

Refresh the architecture story across:

- operator internals
- workbook labels
- surface wording
- docs
- campaign and writeback language

Phase 90 should specifically:

- refresh `docs/architecture.md` so it matches the shipped operator and Action Sync system
- standardize visible Action Sync labels across workbook, Markdown, HTML, review-pack, control-center, CLI, and scheduled handoff
- keep backward compatibility for stored and historical field names while cleaning up visible terminology
- make the role boundaries between `operator_control_center`, `report_enrichment`, and the Action Sync modules explicit

### Constraint

This phase is cleanup and simplification work, not a new capability layer.

### Status

Shipped. Phase 90 refreshed the architecture story, standardized visible Action Sync terminology, preserved compatibility for stored field names, and aligned workbook/Markdown/HTML/review-pack/control-center wording around one coherent mental model.

---

## Phase 91: Historical Portfolio Intelligence

### Goal

Connect the longer-term signals that now exist across the product through one bounded `Intervention Ledger`.

### Target

Bring together:

- implementation hotspots
- operator attention and reopen history
- campaign outcomes and tuning context
- scorecards and maturity signals
- repeated regressions and recurring pressure

The product should begin answering:

- which repos improved after intervention
- which repos are relapsing after intervention
- which repos keep consuming attention without durable progress
- which repos are now holding steady

This phase should specifically:

- add a cross-run historical intelligence builder through `src/intervention_ledger.py`
- persist implementation hotspot history additively so recurrence can be assessed credibly
- surface a `Historical Portfolio Intelligence` block across workbook, Markdown, HTML, review-pack, control-center, and scheduled handoff
- keep the synthesis path inside `AuditReport` -> `operator_control_center` -> `report_enrichment`

### Constraint

Prefer additive historical insight over new automation, new queues, or new scoring.

---

## Phase 92: Cautious Automation Expansion

### Goal

Add safer execution helpers only after the outcome loop is trustworthy.

### Target

Phase 92 should stay bounded. The product should tell the operator:

- what is safe to automate as a preview-only step
- what still requires approval or human review first
- what is safe to treat as non-mutating follow-up
- what must stay explicitly manual

This phase should specifically:

- add one `Automation Guidance` layer on top of Action Sync readiness, apply packets, post-apply monitoring, campaign tuning, and historical portfolio intelligence
- keep scheduled handoff and issue automation artifact-first
- surface safe command hints only when the posture is clearly bounded
- keep `--writeback-apply` human-only even when a campaign is otherwise ready

### Constraint

No new command tree, no background mutation runner, and no widening of write authority.
`apply-manual` remains an explicit human action, not an automatic one.

### Status

Shipped. Phase 92 added bounded `Automation Guidance`, automation-safe command/posture packaging across the Action Sync stack, scheduled-handoff parity for safe execution hints, workbook/Markdown/HTML/review-pack/control-center parity, and additive warehouse persistence for automation guidance snapshots.

### Target

Possible candidates:

- stronger next-step execution guidance
- optional approval workflows
- better recurring review handoff and follow-up
- limited automation around already-proven safe paths

### Constraint

No unsafe default automation. The operator and local report remain authoritative.
