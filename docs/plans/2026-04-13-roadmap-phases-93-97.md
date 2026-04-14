# Roadmap: Phases 93-97

## Current Status Snapshot
- Phases 96 and 97 are complete and merged on `main`
- Phase 95 scheduling remains explicitly deferred and quarantined from the tracked release boundary
- The workbook automated gate remains part of the release standard for workbook-facing changes
- The `88-92` roadmap arc is complete and now historical context only
- The next planning arc begins in [2026-04-14-roadmap-phases-98-102.md](/Users/d/Projects/GithubRepoAuditor/docs/plans/2026-04-14-roadmap-phases-98-102.md)

## Phase Closeout Standard
Every phase from this roadmap is only complete when all of the following are true:

1. Roadmap status is refreshed first and the active phase is marked clearly.
2. Planned behavior is implemented and any explicit deferrals are called out.
3. Verification is recorded, including workbook-gate status and workbook manual signoff state.
4. Git work is closed end to end:
   - branch created
   - commit created
   - PR opened
   - PR merged
   - local `main` synced to `origin/main`
   - open PR check returns none
   - merged and stale branches are pruned
5. Generated artifacts are cleaned up unless intentionally retained.
6. The phase summary states what shipped and what the next phase will target.
7. Planning restarts before implementation begins for the next phase.

## Phase 93: Unified Approval Workflow + Approval Ledger
Status: Complete

Goal:
- Create one local, artifact-first approval workflow that unifies governance approvals and approval-eligible campaign packets without widening write authority.

Key targets:
- add `src/approval_ledger.py`
- add an approval ledger bundle to `AuditReport`, `operator_summary`, queue items, and weekly review pack surfaces
- add `--approval-center`, `--approve-governance`, and `--approve-packet`
- persist approval ledger snapshots and approval records in the warehouse
- add workbook, Markdown, HTML, review-pack, scheduled-handoff, and approval-center parity

## Phase 94: Recurring Review + Follow-Up Handoff
Status: Deferred on tracked baseline

Goal:
- Use the approval ledger plus the existing review and monitoring layers to manage approved-but-not-applied work, stale approvals, and recurring follow-up reminders without adding auto-apply behavior.

## Phase 95: Approval-Aware Portfolio Scheduling
Status: Deferred and quarantined

Goal:
- Blend approval backlog, follow-up timing, and portfolio pressure into clearer weekly scheduling guidance while keeping execution human-led.

## Phase 96: Weekly Story Consolidation + Explainability Baseline
Status: Complete on release branch

Goal:
- Consolidate the weekly story into one shared `weekly_story_v1` contract, route the weekly-facing artifacts through that contract, and then compress repeated wording into compact evidence packs without rewriting raw operator targeting.

## Phase 97: Stability, Docs, and Release Hardening
Status: Complete

Goal:
- Reconcile the deferred Phase 94/95 residue, close the current local work end to end, and harden the post-Phase-96 system with stronger regression coverage, docs truthfulness, and release-readiness cleanup.
