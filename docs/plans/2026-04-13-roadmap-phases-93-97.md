# Roadmap: Phases 93-97

## Current Status Snapshot
- Shipped through **Phase 92**
- Current baseline is `main`
- No open PRs
- Workbook automated gate passes; manual desktop Excel signoff remains a separate release step
- Only intentional local residue is untracked `.serena/`
- The `88-92` roadmap arc is complete and now historical context only
- **Phase 93** is the active target

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
Status: Active

Goal:
- Create one local, artifact-first approval workflow that unifies governance approvals and approval-eligible campaign packets without widening write authority.

Key targets:
- add `src/approval_ledger.py`
- add an approval ledger bundle to `AuditReport`, `operator_summary`, queue items, and weekly review pack surfaces
- add `--approval-center`, `--approve-governance`, and `--approve-packet`
- persist approval ledger snapshots and approval records in the warehouse
- add workbook, Markdown, HTML, review-pack, scheduled-handoff, and approval-center parity

## Phase 94: Recurring Review + Follow-Up Handoff
Status: Planned

Goal:
- Use the approval ledger plus the existing review and monitoring layers to manage approved-but-not-applied work, stale approvals, and recurring follow-up reminders without adding auto-apply behavior.

## Phase 95: Approval-Aware Portfolio Scheduling
Status: Planned

Goal:
- Blend approval backlog, follow-up timing, and portfolio pressure into clearer weekly scheduling guidance while keeping execution human-led.

## Phase 96: Evidence Pack Compression + Operator Explainability
Status: Planned

Goal:
- Make the operator story easier to skim by tightening summary wording, reducing repeated framing, and surfacing compact evidence packs for why a repo or campaign is being recommended.

## Phase 97: Stability, Docs, and Release Hardening
Status: Planned

Goal:
- Consolidate the post-Phase-93 system into a calmer long-term baseline with stronger regression coverage, docs refresh, and release-readiness cleanup.
