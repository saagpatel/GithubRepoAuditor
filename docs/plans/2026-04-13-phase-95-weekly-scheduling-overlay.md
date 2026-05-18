# Phase 95 Design Note: Weekly Scheduling Overlay

Date: 2026-04-13
Status: Deferred design note (non-shipping)

This note is intentionally retained as design context only. Phase 97 explicitly quarantines the scheduling overlay from the tracked release boundary because the proposal is not wired into tracked weekly surfaces and depends on approval follow-up facts that the tracked approval model does not yet produce.

## Decision

Phase 95 is an additive weekly scheduling overlay, not a rewrite of raw operator targeting.

## Why

The operator queue, lane semantics, `primary_target`, and `what_to_do_next` already carry the raw triage contract. Reusing those fields for approval-aware planning would blur two different jobs:

- raw operational priority
- weekly planning guidance

That would create a shadow queue and make future regressions harder to detect.

## What This Phase Would Add

- one bounded scheduling computation in `src/weekly_scheduling.py`
- shared `Weekly Scheduling` and `Next Weekly Focus` lines across weekly-facing artifacts
- additive candidate lists for approval backlog, approval follow-up timing, and pressure conflicts

## What This Phase Explicitly Defers

- any rewrite of `operator_queue`
- any rewrite of `primary_target`
- any rewrite of `what_to_do_next`
- any new command tree
- any widening of write authority
- any approval-aware auto-apply behavior

## Current Repo Status

- `src/weekly_scheduling.py` is not part of the tracked release boundary.
- No tracked weekly surface currently consumes the scheduling overlay directly.
- If this idea is revisited later, it must be ported into the tracked weekly packaging seams after approval follow-up state exists in the tracked approval architecture.

## Safety Rule

Approval-aware weekly scheduling may recommend review, re-check, refresh, or approval-center paths. It must never treat `--writeback-apply` as the weekly scheduling outcome unless another existing Action Sync layer had already independently earned that posture.
