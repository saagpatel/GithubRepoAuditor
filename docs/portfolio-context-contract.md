# Portfolio Context Contract

## Purpose

Phase 104 introduced one explicit minimum-context contract for repos in `/Users/d/Projects`.

The goal is not to turn every repo into a full documentation portal. The goal is to make the
important repos resumable without rediscovery while keeping the truth snapshot derived from
repo-local files.

## Primary Context File Rule

Recovered context is written to exactly one primary file per repo:

1. existing `CLAUDE.md`
2. otherwise existing `AGENTS.md`
3. otherwise new `AGENTS.md`

The truth snapshot never becomes the writable source for context. `portfolio-truth-latest.json`
is derived output only.

## Managed Context Block

Phase 104 writes and updates one managed block:

- start marker: `<!-- portfolio-context:start -->`
- end marker: `<!-- portfolio-context:end -->`

That block can be appended to an existing repo guidance file without replacing the surrounding
repo-specific instructions.

## Required Minimum-Viable Fields

To qualify as `minimum-viable` or higher, the primary context file must contain non-trivial
content for all of these sections:

1. what the project is
2. current state
3. stack
4. how to run it
5. known risks
6. next recommended move

The truth snapshot exposes those as explicit booleans:

- `project_summary_present`
- `current_state_present`
- `stack_present`
- `run_instructions_present`
- `known_risks_present`
- `next_recommended_move_present`

## Accepted Heading Aliases

The classifier accepts a bounded set of aliases instead of one exact heading string.

Accepted aliases include:

- project summary:
  - `What This Project Is`
  - `Project Summary`
  - `Overview`
  - `Purpose`
  - `Product Goal`
- current state:
  - `Current State`
  - `Status`
  - `Current Phase`
  - `Current Focus`
- stack:
  - `Stack`
  - `Tech Stack`
  - `Technology`
- run instructions:
  - `How To Run`
  - `Local Setup`
  - `Local Development`
  - `Commands`
  - `Quick Start`
  - `Build & Run`
  - `Getting Started`
  - `Usage`
- known risks:
  - `Known Risks`
  - `Risks`
  - `Known Issues`
  - `Intentional Limits`
  - `Constraints`
- next move:
  - `Next Recommended Move`
  - `Next Step`
  - `Next Steps`
  - `Recommended Next Step`

## Context Quality Bands

- `none`
  - no primary context file exists yet
- `boilerplate`
  - primary context exists, but one or more required minimum fields are still missing
- `minimum-viable`
  - all six required fields are present in the primary context file
- `standard`
  - minimum-viable plus at least one supporting handoff-style artifact such as `HANDOFF.md`,
    `IMPLEMENTATION-ROADMAP.md`, `STATUS.md`, `PLAN.md`, or `RESUMPTION-PROMPT.md`
- `full`
  - standard plus multiple supporting artifacts, including at least one high-signal handoff or
    discovery doc

## Recovery Workflow Rules

- The planner only targets repos that are:
  - `active` or `recent`
  - currently `boilerplate` or `none`
- Automated writes are skipped for:
  - dirty git worktrees
  - ambiguous primary-context cases
  - temporary/generated repos identified by the phase baseline
- Temporary/generated exclusions currently include scaffold-style repos and `*-tmp-*` repos.

## Catalog Seeding

Phase 104 also seeds bounded repo-level catalog fields for recovered priority repos:

- `owner`
- `lifecycle_state`
- `review_cadence`
- `intended_disposition`
- `category` only when obvious
- `tool_provenance` only when obvious

That keeps declared portfolio intent from drifting entirely into prose.
