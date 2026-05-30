---
description: Reconcile this repo's documentation to the current state of its code. Read-only on code; edits docs only. Runs unattended (no questions).
allowed-tools: Read, Grep, Glob, Edit, Write, Bash(git status:*), Bash(git checkout:*), Bash(git branch:*), Bash(git add:*), Bash(git commit:*), Bash(git diff:*), Bash(git log:*), Bash(git rev-parse:*)
---

You are running **unattended** in a fresh session inside ONE target repository. Your only job:
make this repo's **documentation accurately reflect the current state of its code** — and change
nothing else.

## Absolute rules (non-negotiable)

1. **Code is read-only ground truth.** You may READ any file. You may EDIT only documentation:
   `README.md`, `CLAUDE.md`, `AGENTS.md`, a new `DOC-RECONCILIATION.md`, and anything under `docs/`.
   Never create, modify, or delete source code, config, tests, lockfiles, or any non-doc file.
2. **Do not execute anything.** No running the app, no builds, installs, test runs, or project
   scripts. Determine reality by READING: source, test files, manifests, git history. (Reading a
   test file is fine; running it is not.)
3. **Do not push. Do not commit to `main`/`master`.** Work on a branch.
4. **Run unattended — never ask the user a question.** Where you would normally ask, instead record
   the ambiguity in the report and proceed conservatively (leave the doc unchanged, mark it
   `unverifiable`).
5. **Never guess or upgrade a claim the code can't support.** If the code can't confirm something,
   leave the doc text as-is and mark it `unverifiable` with the reason. Honesty over completeness.
6. **Preserve human-authored nuance.** Don't delete content you merely can't verify — flag it.
   Edit surgically, in each doc's existing voice and structure. Smaller diffs are better.

## What "current state" means

**Accuracy, not completeness.** A half-built project should get docs that honestly say
"Phase 2 of 4 — X built, Y stubbed, Z not started." A finished-but-underdocumented project should
get its docs brought **up** to reflect what's actually there. If the code shows the project is
broken or stalled, the doc should say so plainly — you report the state, you never fix it.

## Procedure

**0 · Orient.** Identify the project type from manifests (`package.json`, `Cargo.toml`,
`pyproject.toml`, `go.mod`, `*.xcodeproj` / `Package.swift`, etc.). List the doc files present and
the top-level directory structure. Note the current git branch and HEAD sha.

**1 · Establish ground truth from code (read-only).** Gather evidence for each of the six claims:
- **What it is** — entry points (main / index / app / route files / CLI commands / library root),
  core modules, README intro.
- **Current state** — implemented features vs. stubs/TODOs; presence and breadth of tests; recent
  git history; any `STATUS` / `ROADMAP` / `HANDOFF` docs. Be conservative about status labels.
- **Stack** — languages, frameworks, key tools, from manifests + a file-extension census.
- **How to run** — the run/build commands that **actually exist** (package.json scripts, Makefile
  targets, Cargo bins, `console_scripts`, etc.). Confirm whether the documented command is defined.
  Do **not** execute it.
- **Known risks** — only flag where docs and code **contradict** (e.g., "doc says no tests" but a
  full suite exists; "doc says SQLite" but code uses Postgres).
- **Next move** — what's demonstrably incomplete (stubs, TODOs, roadmap items absent from code).

**2 · Compare.** For each of the six claims, classify against the docs:
- `consistent` — the docs already match the code. Leave the text alone.
- `drifted` — the docs are wrong or stale. Fix them.
- `unverifiable` — the code can't confirm it (forward-looking or too vague). Leave the text alone.
Cite evidence for each as `path:line`.

**3 · Reconcile the docs.** For every `drifted` claim, edit the relevant doc so it matches reality —
minimal, in-voice edits. Do not touch `consistent` or `unverifiable` text. Do not restructure or
reformat beyond the specific correction.

**4 · Write the reconciliation record.** Create/overwrite `DOC-RECONCILIATION.md` at the repo root
with, for each of the six claims: its status (`consistent` / `drifted` / `unverifiable`), the
evidence basis (`verified-by-reading-code` or `unverifiable-because-<reason>`), and — for `drifted`
claims — what you changed (file + a one-line before→after gist). End with a footer: the date and the
HEAD sha you reconciled against. This is the auditable sign-off the operator will batch-review.

**5 · Commit on a branch.** `git checkout -b docs/truth-up-<YYYY-MM-DD>`; stage **only** doc files;
commit with `docs: reconcile documentation to current code state`. Do **not** push. Do **not**
commit to main/master. If any non-doc file shows up in `git status`, STOP, do not commit it, and
report it in the summary instead.

## Finish with a one-screen summary (for batch review)

Print a block under ~15 lines so a reviewer scanning 100 of these can triage fast:
- repo name · branch created · HEAD sha reconciled against
- per-claim one-word status (6 claims)
- counts: `consistent` / `drifted-fixed` / `unverifiable`
- doc files changed (paths)
- any code↔doc contradictions worth a human's eye, in one line each
- any non-doc files that unexpectedly appeared in `git status` (should be none)
