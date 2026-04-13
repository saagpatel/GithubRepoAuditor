# GitHub Repo Auditor Roadmap: Phases 88-92

**Date:** 2026-04-12  
**Current Status Snapshot:**
- Shipped through **Phase 87**
- Current baseline is `main`
- No open PRs
- Workbook automated gate passes; manual desktop Excel signoff remains a separate release step
- [2026-04-12-roadmap-phases-78-85.md](/Users/d/Projects/GithubRepoAuditor/docs/plans/2026-04-12-roadmap-phases-78-85.md) is now historical context only

---

## Executive Summary

GitHub Repo Auditor now has a strong operator loop:

- weekly review and control-center triage
- campaign readiness guidance
- apply-packet handoff
- managed writeback and GitHub Projects mirroring
- workbook, Markdown, HTML, review-pack, and scheduled handoff parity

The next roadmap arc should focus on closing the loop after execution, then using that evidence to improve the system deliberately.

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

The main remaining gap is no longer deciding what to do next.  
It is proving whether the action actually helped after preview or apply.

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

### Constraint

Keep this descriptive first. Do not auto-retune campaign execution or add self-modifying behavior.

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

### Constraint

This phase is cleanup and simplification work, not a new capability layer.

---

## Phase 91: Historical Portfolio Intelligence

### Goal

Connect the longer-term signals that now exist across the product.

### Target

Bring together:

- implementation hotspots
- operator outcomes
- campaign outcomes
- scorecards and maturity signals
- repeated regressions and recurring pressure

The product should begin answering which repos improve after intervention and which ones repeatedly regress.

### Constraint

Prefer additive historical insight over new automation.

---

## Phase 92: Cautious Automation Expansion

### Goal

Add safer execution helpers only after the outcome loop is trustworthy.

### Target

Possible candidates:

- stronger next-step execution guidance
- optional approval workflows
- better recurring review handoff and follow-up
- limited automation around already-proven safe paths

### Constraint

No unsafe default automation. The operator and local report remain authoritative.
