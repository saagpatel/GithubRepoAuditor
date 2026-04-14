# Decision: Defer Approval-Aware Weekly Scheduling

## Status

`deferred`

## Context

Approval-aware weekly scheduling depends on tracked approval follow-up facts that do not yet exist in the shipped approval architecture. Earlier residue already showed the failure mode: a second weekly recommendation path forms before the shared weekly contract and approval data model are ready.

## Decision

Do not implement approval-aware weekly scheduling until the roadmap reaches Phase 102, after approval follow-up facts exist in tracked architecture and the shared weekly packaging seam is already extracted.

## Consequences

- `weekly_story_v1` remains the only shipped weekly authority
- no second weekly recommendation engine should be introduced before Phase 102
- approval backlog and follow-up timing can be documented as future inputs, but not surfaced as shipped weekly scheduling behavior

## Supersedes

- deferred and quarantined status language for Phase 95 in [2026-04-13-roadmap-phases-93-97.md](/Users/d/Projects/GithubRepoAuditor/docs/plans/2026-04-13-roadmap-phases-93-97.md)
- deferred scheduling note in [2026-04-13-phase-95-weekly-scheduling-overlay.md](/Users/d/Projects/GithubRepoAuditor/docs/plans/2026-04-13-phase-95-weekly-scheduling-overlay.md)

## Superseded By

None yet.
