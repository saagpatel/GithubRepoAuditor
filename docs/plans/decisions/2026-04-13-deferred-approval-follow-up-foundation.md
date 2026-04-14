# Decision: Defer Approval Follow-Up Foundation

## Status

`deferred`

## Context

The tracked approval ledger shipped in Phase 93, but the tracked approval model does not yet carry the recurring follow-up facts needed for durable review aging, stale-approval packaging, or recurring handoff guidance. The weekly packaging seam and operator core also remain concentrated enough that layering this behavior in immediately would create avoidable rework.

## Decision

Do not implement approval follow-up foundation work until the roadmap reaches Phase 101, after weekly packaging extraction and operator-core decomposition are complete.

## Consequences

- roadmap and orientation docs must treat approval follow-up as deferred, not partially shipped
- scheduling work must not assume follow-up facts already exist in tracked architecture
- approval follow-up implementation should reopen only after the shared weekly seam and operator core are safer landing zones

## Supersedes

- deferred status language for Phase 94 in [2026-04-13-roadmap-phases-93-97.md](/Users/d/Projects/GithubRepoAuditor/docs/plans/2026-04-13-roadmap-phases-93-97.md)

## Superseded By

None yet.
