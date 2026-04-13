# Next Chat Handoff: GitHub Repo Auditor

Last updated: 2026-04-07
Workspace: `/Users/d/Projects/GithubRepoAuditor`

## Purpose
This file is the canonical handoff for the next chat window.

Use it when starting a new Codex thread so the new chat can pick up without having to reconstruct context from the previous conversation.

This handoff is intentionally detailed. It captures:
- overall project state
- what phases have already been completed
- the recent Excel workbook work
- what was fixed versus what is still open
- the current git status
- the next likely planning focus

## Project Overview
GitHub Repo Auditor is an automated portfolio audit tool for a large GitHub account. It clones and analyzes repositories, scores them across multiple dimensions, and produces a portfolio-level operating system across several surfaces:
- JSON report
- Markdown report
- HTML dashboard
- Excel workbook
- warehouse/history
- Notion sync
- operator control center

The product direction has shifted over time from "repo scanner" into a true operator-facing portfolio command center.

Primary operator loop:
1. `audit --doctor`
2. `audit`
3. `audit --control-center`

## Important Architectural Invariants
These are hard constraints and should be preserved unless there is an explicit intentional redesign.

### 1. Full filtered portfolio baseline invariant
Interest/novelty and portfolio-wide views must be anchored to the full filtered portfolio baseline.

This is especially important for:
- full runs
- targeted reruns
- incremental reruns

There is an outstanding repeated review finding that suggests this invariant may still be at risk in targeted reruns. See "Open Risk / Review Finding" below.

### 2. One workbook artifact
There should be one Excel workbook artifact:
- `output/audit-dashboard-<username>-<date>.xlsx`

Do not split into multiple workbook files for the operational path.

### 3. Excel safety rule
Mac Excel compatibility was a major issue and has already been debugged at length.

Confirmed safe architecture:
- visible sheets use plain worksheet ranges + autofilters
- hidden `Data_*` sheets keep structured Excel tables

Do not reintroduce visible-sheet structured Excel Table objects unless compatibility is revalidated in real Excel.

### 4. Standard mode is the stable operational workbook mode
Current operational/default path:
- `--excel-mode standard`

`template` remains supported, but should be treated as optional/curated rather than the default automation path.

### 5. Hidden workbook contract stability
The workbook relies on:
- hidden `Data_*` sheets
- stable named ranges
- stable hidden tables

Changes to that contract should be additive-only unless there is an explicit migration plan.

### 6. Governance stays bounded
Governance scope remains intentionally narrow and manual/opt-in:
- code security
- secret scanning
- push protection
- CodeQL default setup

No automatic mutation path should be introduced casually.

## Current Git State
As of this handoff:
- branch: `main`
- local branch state: `main...origin/main [ahead 2]`

This means the local repo currently has two commits that are not yet pushed to `origin/main`.

Recent commits:
- `9d2f7a6 feat(excel): improve workbook readability and layout`
- `8660d8c feat(excel): polish workbook operator presentation`
- `55a7f58 docs(excel): align workbook guidance with safe mode`
- `ccbf8f3 ci(excel): pin automated workbook exports to standard mode`
- `f023f1f fix(excel): harden workbook compatibility for Excel`
- `846c208 feat(excel): harden workbook UX and safety`
- `0821406 chore(repo): ignore local operator artifacts`
- `4b42747 feat(operator): complete product hardening finish pass`
- `41eae32 Merge pull request #33 from saagpatel/fix/excel-visual-polish`
- `2fb9277 fix(excel): visual polish — column widths, wrap text, zebra stripes, freeze panes`

Important practical note:
- Earlier chat messages claimed that everything was already pushed/synced.
- The real current state is that `main` is now ahead of `origin/main` by 2 commits.
- The next chat should treat that as the source of truth.

## What Was Completed Before This Handoff

### Phase 19 / operator completion and hardening
Core work completed:
- package-first install and setup story
- Makefile/operator flow cleanup
- docs/examples cleanup
- operator control center parity across surfaces
- governance trust hardening
- workflow/docs/package alignment

Key commit:
- `4b42747 feat(operator): complete product hardening finish pass`

### Excel compatibility crisis and fix
There was a real Mac Excel repair/corruption problem when opening generated workbooks.

Root cause that was actually confirmed:
- visible-sheet structured Excel Table objects triggered Excel repair prompts on the target Mac Excel environment
- hidden `Data_*` tables were safe

Debugging path included:
- multiple "safe" workbook variants
- isolating visible-table vs hidden-table behavior
- proving that hidden tables opened cleanly while visible tables caused repair

Final architecture adopted:
- visible sheets: plain ranges + worksheet autofilters
- hidden sheets: structured tables retained

Key commits:
- `f023f1f fix(excel): harden workbook compatibility for Excel`
- `ccbf8f3 ci(excel): pin automated workbook exports to standard mode`
- `55a7f58 docs(excel): align workbook guidance with safe mode`

### Workbook productization / presentation improvements
Subsequent workbook work focused on making the workbook safer, more readable, and more operator-friendly.

Major changes already implemented:
- `standard` became the CLI/config default
- top-level workbook journey improved
- stronger `Review Queue`
- stronger `Dashboard`
- stronger `Executive Summary`
- stronger `Print Pack`
- freeze panes expanded
- empty states improved
- hidden contract preserved

Key commit:
- `8660d8c feat(excel): polish workbook operator presentation`

### Latest workbook readability pass
The most recent local-only pass focused on what was seen in actual Excel screenshots:
- font sizing
- readability
- section hierarchy
- chart overlap on `Dashboard`
- tab sprawl

What changed in the latest local commits:
- larger, more readable workbook typography
- softened palette while keeping light-mode cells
- smarter default zoom
- gridlines hidden on summary/operator sheets
- dashboard chart overlap fixed by shrinking/repositioning charts and moving chart support data out of the visible canvas
- non-core sheets hidden by default to reduce tab overload
- `Index` updated to explain advanced sheets are hidden by default

Latest local commit:
- `9d2f7a6 feat(excel): improve workbook readability and layout`

## Current Workbook State

### Canonical generated workbook
- `/Users/d/Projects/GithubRepoAuditor/output/audit-dashboard-saagpatel-2026-03-29.xlsx`

### Canonical report used for regeneration
- `/Users/d/Projects/GithubRepoAuditor/output/audit-report-saagpatel-2026-03-29.json`

### Desktop copies created during iteration
Human-facing copies currently present:
- `/Users/d/Desktop/GitHub Portfolio Audit Dashboard - saagpatel - Final.xlsx`
- `/Users/d/Desktop/GitHub Portfolio Audit Dashboard - saagpatel - Updated.xlsx`

There may also be temporary Excel lock files depending on whether Excel is open.

### Current workbook behavior
The workbook now opens cleanly in Excel Mac using the safe architecture above.

The current visible/core tab set is intentionally smaller. A smoke inspection after the latest pass showed these main visible tabs:
- `Index`
- `Dashboard`
- `Review Queue`
- `Portfolio Explorer`
- `Executive Summary`
- `By Lens`
- `By Collection`
- `Trend Summary`
- `Campaigns`
- `Governance Controls`
- `Print Pack`
- `All Repos`

Advanced/deep-dive tabs are preserved but hidden by default.

### Current workbook UX direction
The current design choice is a hybrid:
- keep cells in light mode
- use darker section/header bands for hierarchy
- reduce gridline noise
- increase font size / zoom on summary surfaces

Recommendation from prior chat:
- do not convert the entire workbook to true dark-mode cells

Reason:
- dense tables become harder to scan
- print/PDF quality gets worse
- conditional formats become harder to interpret
- mixed operator + executive use cases suffer

The preferred direction is:
- dark headers / section bands
- lighter data regions
- stronger hierarchy
- fewer visible gridlines
- better zoom and spacing

## Open Risk / Review Finding
There is one repeated review finding that must be explicitly preserved into the next chat:

### Review finding
`[P2] Partial reruns recompute interest against the wrong portfolio baseline`

Restated:
- targeted audits rebuild `portfolio_lang_freq` from only the repos being re-audited
- this can change interest scoring relative to the wrong baseline
- the targeted flow should reuse the full filtered portfolio baseline or force a full recompute

### Current code evidence
In `src/cli.py`:
- `_compute_portfolio_lang_freq(...)` exists around line 691
- `_portfolio_lang_freq_for_filtered_baseline(...)` exists around line 696
- `_run_targeted_audit(...)` exists around line 1275
- `_run_incremental_audit(...)` exists around line 1405

Important detail:
- `_run_targeted_audit(...)` currently computes:
  - `portfolio_lang_freq = _portfolio_lang_freq_for_filtered_baseline(filtered_repos)`

That strongly suggests the review finding may still be valid.

Do not assume this issue is fixed just because later Excel work happened.

The next chat should explicitly audit this before saying the portfolio-baseline invariant is fully protected.

## Current Workbook/Excel File References
Most relevant implementation files:
- `/Users/d/Projects/GithubRepoAuditor/src/excel_export.py`
- `/Users/d/Projects/GithubRepoAuditor/src/excel_styles.py`
- `/Users/d/Projects/GithubRepoAuditor/src/cli.py`
- `/Users/d/Projects/GithubRepoAuditor/src/config.py`
- `/Users/d/Projects/GithubRepoAuditor/src/diagnostics.py`

Most relevant tests/docs:
- `/Users/d/Projects/GithubRepoAuditor/tests/test_excel_enhanced.py`
- `/Users/d/Projects/GithubRepoAuditor/tests/test_cli_hardening.py`
- `/Users/d/Projects/GithubRepoAuditor/tests/test_packaging.py`
- `/Users/d/Projects/GithubRepoAuditor/tests/test_config.py`
- `/Users/d/Projects/GithubRepoAuditor/README.md`
- `/Users/d/Projects/GithubRepoAuditor/docs/architecture.md`
- `/Users/d/Projects/GithubRepoAuditor/docs/operator-troubleshooting.md`
- `/Users/d/Projects/GithubRepoAuditor/docs/workbook-template-maintenance.md`
- `/Users/d/Projects/GithubRepoAuditor/config/examples/audit-config.example.yaml`
- `/Users/d/Projects/GithubRepoAuditor/config/audit-config.example.yaml`

## Verified State From Recent Testing
Recent test results already obtained in the previous chat:

### Full suite
- command: `python3 -m pytest -q`
- result: `509 passed, 2 warnings`

Warnings:
- existing `openpyxl` sparkline-extension warnings in template-mode tests
- these were not treated as new regressions

### Workbook smoke observations from the latest pass
- `Dashboard` zoom: `120`
- `Index` zoom: `125`
- `Print Pack` zoom: `125`
- `Dashboard` gridlines: off
- `Review Queue` gridlines: off
- `Hotspots`: hidden by default

## What The User Just Asked For
The user wants to open a new chat window due to context limits.

The new chat should:
- read this handoff file first
- continue in plan mode
- treat this file as the authoritative context handoff

The user specifically wants the next chat to have:
- all major context
- the workbook history
- the current state of the repo
- the current state of the Excel file
- what phase comes next
- what still needs improvement
- what still needs explicit checking

## Recommended Next Phase Focus
The next chat should likely start by planning the next workbook phase, but with one important prerequisite:

### First prerequisite
Explicitly audit the outstanding targeted-rerun baseline review finding in `src/cli.py`.

If it is still valid, that is not a cosmetic issue. It is a correctness issue and should be addressed before doing more “finished product” framing.

### After that, likely next phase
A strong next phase would be a workbook visual + presentation refinement phase focused on:
- sheet-by-sheet visual clarity
- readability at normal Excel zoom
- further operator summary compression
- dashboard density reduction
- executive sheet polish
- whether additional tab grouping/hiding rules make sense
- whether template mode should get any limited presentation-only enhancements

But this should be planned on top of the current safe architecture:
- one workbook
- standard operational mode
- no visible-sheet Excel tables

## Suggested Questions For The Next Chat To Answer
1. Is the repeated portfolio-baseline review finding still valid in current code?
2. If yes, what is the safest fix that preserves the full filtered portfolio baseline invariant for targeted and incremental runs?
3. After that correctness issue is handled, what is the next workbook polish phase?
4. Which workbook improvements belong in:
   - standard mode
   - template mode
   - docs only
5. Which local commits should now be pushed to `origin/main`?

## Current Local / Remote Sync Caveat
As of this handoff, local `main` is ahead of `origin/main` by 2 commits.

The next chat should not assume everything is already pushed.

The next chat should verify whether to:
- push the two local Excel polish commits
- or continue work locally first and push later

## Recommended Opening Move For The Next Chat
1. Read this file first.
2. Confirm current git status and whether local `main` is still ahead of remote.
3. Re-audit the `src/cli.py` targeted/incremental baseline logic.
4. Then create the next plan.

## Short Executive Summary
If you need the shortest possible version:

- The project is broadly mature and productized.
- The Excel workbook went through a real Mac Excel compatibility incident and now has a confirmed safe architecture.
- The workbook has already had major UX/readability/productization work.
- Two additional Excel polish commits now exist locally and are not yet pushed.
- The biggest open correctness risk is the repeated review finding about targeted reruns using the wrong portfolio novelty baseline.
- The next chat should start by validating or fixing that risk before planning the next visual polish phase.
