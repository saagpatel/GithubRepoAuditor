# Spec — External Audit of `run_instructions_present` (Dynamic Workflow)

- **Date:** 2026-05-29
- **Status:** Design approved; spec under review (pre-implementation)
- **Branch:** `feat/run-instructions-external-audit`
- **Owner:** d
- **Type:** Read-only verification workflow (first dynamic-workflow build for this project)

## 1. Purpose

`portfolio-truth-latest.json` makes ~22 derived claims about each of 132 projects on disk.
This workflow is a **second pair of eyes the tool cannot fool**: it independently re-checks one
high-value claim — `run_instructions_present` — against the actual files on disk, using LLM
judgment where the tool uses a brittle regex. It produces a discrepancy report for human review.
It never modifies repos, the snapshot, or git state.

This is **not** a replacement for `portfolio_truth_validate.py` (which checks the snapshot's
internal schema/consistency). This audits the snapshot's claims against **ground truth**.

## 2. What we are auditing (the heuristic under test)

Every `derived` presence-boolean traces through one function:

- `_inspect_project_dir` — `src/portfolio_truth_sources.py:200`
- → `analyze_project_context` — `src/portfolio_context_contract.py:135`
- → `choose_primary_context_file` — `src/portfolio_context_contract.py:128`
  (returns `CLAUDE.md`, else `AGENTS.md` — **never `README.md`**)
- → `_section_has_meaningful_content` — `src/portfolio_context_contract.py:265`
  (true iff a markdown heading matches a hardcoded alias in `CONTEXT_SECTION_ALIASES` **and**
  has non-trivial text under it)

So `run_instructions_present` is true **iff** the primary file has a heading matching the alias
list, with content. Two known failure modes follow directly from the code:

- **Alias gap:** run instructions exist in the primary file under a heading the alias list does
  not recognize. NB the list is already broad — `how to run`, `usage`, `getting started`,
  `quick start`, `commands`, `local setup`, `local development`, `build run`,
  `development commands`, `run instructions` — so realistic misses are headings *outside* it
  (`## Running`, `## Run the app`, `## Develop`, `## Scripts`, `## Make targets`) or run steps
  present only as prose / a code block under no recognized heading.
- **Input blind spot:** run instructions exist only in `README.md`, which the tool never reads
  as the primary file → the project can score `context_quality: none` despite rich human docs.

Because the alias list is broad, the **dominant discrepancy class is likely the blind spot
(README-only repos), not the alias gap** — a hypothesis this pilot will test. Either way, both
are exactly what an LLM reading the prose catches and a regex never will.

## 3. Locked scope decisions

| Decision | Choice | Rationale |
|---|---|---|
| Claim to verify | `run_instructions_present` | Atomic, semantic, fragile heuristic, demonstrable, cheap. Widening to all 6 booleans later is near-free (same file already read). |
| Evidence mode | Categorized ground-truth | Verifier judges whether run instructions truly exist anywhere, and the harness classifies *why* the tool missed: alias-gap vs blind-spot vs genuinely-absent. Each bucket implies a different fix. |
| Population (first run) | Stratified pilot ~15–20 | Small enough to hand-verify every disagreement and earn trust in the mechanism before scaling. Same script scales to full 132 as a one-line change. |

## 4. Snapshot facts (as of generation)

- `schema_version`: `0.4.0`
- `generated_at`: `2026-05-17T05:01:39Z` (**12 days stale as of this spec — drift is real, see §8**)
- `workspace_root`: `/Users/d/Projects`
- `projects`: 132 (a list; key on `identity.project_key`, **not** `display_name` — dupes exist:
  `IncidentWorkbench`, `OrbitForge`, `StatusPage`)
- `context_quality_counts`: `none: 3, boilerplate: 17, minimum-viable: 66, standard: 27, full: 19`

## 5. Architecture — four stages + live-recompute refinement

Only **Stage 2** is LLM judgment. Everything else is deterministic code. The harness controls
the evidence; the LLM only judges it.

### Where each stage physically runs (critical for a Workflow build)

The Workflow script's JS sandbox has **no filesystem access** and cannot run Python. Therefore:

| Stage | Runs in | Mechanism |
|---|---|---|
| 0 · Pilot selection | Main session (pre-step) | `ctx_execute(python)` — reads snapshot, emits compact records |
| 1 · Evidence prep + live recompute | Main session (pre-step) | `ctx_execute(python)` — per-repo metadata only, **no file bodies into context** |
| 2 · Per-repo verifier | Workflow `agent()` fan-out | Haiku subagents `Read` their own repo files |
| 3 · Tally | Workflow JS | pure arithmetic over verdicts + passed-in claims |
| 4 · Synthesis | Workflow `agent()` | one Sonnet call → report markdown |
| (write report) | Main session | `Write` to `output/…md` |

The pre-step (Stages 0–1) emits a compact `evidence_packets` array passed to the Workflow as
`args`. **File bodies never enter the main Opus context** — they are read inside each Haiku
subagent. This is the context-hygiene win of the harness-controls-metadata / subagent-reads-body
split.

### Stage 0 · Pilot selection (deterministic)
- Read `output/portfolio-truth-latest.json`.
- Exclude `derived.registry_status == "archived"` and fork-junk by path/name regex
  (`-security-fix`, `-cve-`, `-backup-`, `.bundle`, `-openssl-`).
- Group remaining by `derived.context_quality`; within each tier sort by `project_key`.
- Take all 3 from `none`; 4 each from `boilerplate / minimum-viable / standard / full`. → ~19.
- Output one record per repo (no file bodies):
  `{ project_key, display_name, abs_path, primary_file_name, context_files[], snapshot_claim }`
  where `abs_path = workspace_root + "/" + path` and `snapshot_claim =
  derived.run_instructions_present`.

### Stage 1 · Evidence prep + live recompute (deterministic, read-only)
For each pilot record, compute and attach:
- `primary_file_name` = `choose_primary_context_file(context_files)`.
- `tool_today` = live recompute on **today's** files:
  ```python
  from src.portfolio_context_contract import analyze_project_context
  from src.portfolio_truth_sources import _collect_context_files
  tool_today = analyze_project_context(
      abs_path, _collect_context_files(abs_path)
  ).run_instructions_present
  ```
- `drifted` = repo has git commits after `generated_at`
  (`git -C <abs_path> log -1 --format=%cI` > `2026-05-17T05:01:39Z`).
- Pre-flight: assert the **directory** `abs_path` resolves. The primary file **may legitimately
  be absent** (README-only repos — `choose_primary_context_file` still returns `AGENTS.md`); that
  is a `fn_blind_spot` candidate, **not** an error. Only an unresolvable `abs_path` (missing dir)
  goes to a separate error bucket — never silently dropped.

`tool_today` is the refinement: it lets us isolate **heuristic error** from **snapshot drift**
without depending on the snapshot being fresh.

### Stage 2 · Per-repo verifier (Haiku, schema-locked — the only LLM call in the fan-out)
One subagent per record. Given `{abs_path, primary_file_name, context_files}`, it `Read`s **all
available context files** (the primary file flagged; the primary may be absent for README-only
repos), then judges. It is told which file is primary; it is **not** told the tool's claim (blind
verification). `evidence_in_primary` is `false` when the primary file is absent or the evidence
lives only in a non-primary file. Forced schema:

```jsonc
{
  "verdict": true | false,            // do run instructions genuinely exist in these files?
  "evidence_in_primary": true | false,// is the evidence in the primary file (vs only README/other)?
  "evidence_quote": "string<=240",    // the actual run command / heading text, or ""
  "evidence_location": "CLAUDE.md §Usage" | "README §Getting Started" | "",
  "confidence": "high" | "med" | "low"
}
```
Rule (anti-inflation): if no run instructions exist anywhere, return `verdict:false` and quote
nothing. Default-to-false on uncertainty.

### Stage 3 · Tally (deterministic JS in the workflow)
Combine each verdict with `tool_today` (authoritative tool answer) to assign a bucket:

| `tool_today` | `verdict` | `evidence_in_primary` | bucket |
|---|---|---|---|
| true | true | — | `agree_present` |
| false | false | — | `agree_absent` |
| false | true | true | `fn_alias_gap` → add an alias |
| false | true | false | `fn_blind_spot` → broaden primary-file selection |
| true | false | — | `fp_overclaim` → tool matched an empty/trivial heading |

Separately, `snapshot_claim` vs `tool_today` → **drift bucket** (`fresh` / `claim_changed` /
`claim_same`), so a stale snapshot never masquerades as a heuristic miss.

### Stage 4 · Synthesis + report (one Sonnet call)
Given the tallied disagreements, name the **pattern** ("the tool systematically misses run
instructions documented under headings outside the alias set, e.g. `## Running`") and emit
markdown:
- **Headline:** N repos, agreement rate (verifier vs `tool_today`), counts per bucket.
- **Disagreement table**, keyed by `project_key`: bucket, verifier quote + location, confidence,
  drift flag.
- **Drift summary:** how many snapshot claims differ from `tool_today`.
- **Prescriptive fixes:** which aliases to add to `CONTEXT_SECTION_ALIASES`; whether
  `choose_primary_context_file` should consider `README.md`.

Main session writes the report to `output/run-instructions-audit-2026-05-29.md`.

## 6. Data contract — assembled per-repo record (post-tally)
```jsonc
{
  "project_key": "Fun:GamePrjs/BattleGrid",
  "display_name": "BattleGrid",
  "abs_path": "/Users/d/Projects/Fun:GamePrjs/BattleGrid",
  "primary_file_name": "AGENTS.md",
  "snapshot_claim": false,
  "tool_today": false,
  "drifted": false,
  "verifier": { /* Stage 2 schema */ },
  "bucket": "fn_alias_gap",
  "drift_bucket": "claim_same"
}
```

## 7. Guarantees
- **Read-only:** repos, snapshot, and git are never written. Only artifact is the report file in
  `output/` (gitignored).
- **No Opus in the fan-out:** Stage 2 pinned `model: "haiku"`; Stage 4 `model: "sonnet"`; Opus is
  orchestrator only (writes/edits the script, reviews results).
- **Blind verification:** verifier is not shown the tool's claim, removing anchoring bias.
- **Cost:** ~19 small Haiku calls + 1 Sonnet synthesis → pennies, ~1–2 min wall-clock.

## 8. Known risks / gotchas
1. **Snapshot drift (12 days).** Handled by `tool_today` live recompute + drift bucket; raw
   verifier-vs-snapshot would conflate heuristic error with change-since-snapshot.
2. **README blind spot is a whole discrepancy class** (`fn_blind_spot`) and is arguably the
   biggest source of wrong claims — surfaced explicitly, not collapsed.
3. **Polluted population (132 incl. archived + fork-junk + colon-encoded nested paths).** Stage 0
   filters; pre-flight asserts path resolution.
4. **Path encoding.** Real dirs include colons (`Fun:GamePrjs/`) and near-duplicates
   (`FunGamePrjs`, top-level `BattleGrid`). Always use snapshot `path` joined to `workspace_root`;
   never reconstruct from `display_name`.
5. **Workflow JS sandbox has no FS/Python.** Drives the main-session-pre-step architecture (§5).

## 9. Out of scope (explicit — future widening, not silent cuts)
- Verifying the other 5 presence booleans (same subagent file-read; trivial to add later).
- The numeric `context_quality_score` (Arc-H merge gate) — lives in `src/context_quality.py`, a
  separate code path **not** in the snapshot.
- Full 132-repo run — invocation #2 after the pilot is hand-validated.
- Auditing mechanical claims (`has_tests`, `has_ci`, staleness, …) — a script reproduces those
  exactly; no LLM value.

## 10. Done criteria (first run)
- Report written to `output/run-instructions-audit-2026-05-29.md`.
- Every disagreement carries a verifier quote + location and a drift flag.
- Buckets sum to the pilot count; no path silently dropped (unresolved paths reported).
- Operator can open each flagged repo and confirm the verifier's call by hand.

## Pilot result (run 2026-05-29)

Pilot ran: 16 repos (0 unresolved paths), via a 2-repo smoke then the full fan-out
(16 Haiku verifiers + 1 Sonnet synthesis, ~56s, ~800k subagent tokens). Report:
`output/run-instructions-audit-2026-05-29.md`; per-row sidecar:
`output/run-instructions-audit-2026-05-29.rows.json`.

**Headline: 75% agreement (12/16). All 4 disagreements are `fn_blind_spot`. Zero
`fn_alias_gap`, zero `fp_overclaim`.** The spec's hypothesis is confirmed: the alias list
is broad enough that the regex rarely misses *within* the primary file — the tool's only
real weakness on this claim is being structurally blind to `README.md`.

**Hand-validation (every disagreement, by reading the files):** all 4 confirmed true.
`BattleGrid` / `OrbitForge` / `SlackIncidentBot` each have a generic Codex-OS bootstrap
`AGENTS.md` primary (Communication Contract / Definition of Done / Verification Contract —
no run content) while the real run instructions live in `README.md` (`make dev`,
`pnpm exec tauri dev`, `cargo run --release`). The verifier's semantic judgment and its
`evidence_in_primary=false` calls were accurate.

**Confound — auditing the auditor:** `GithubRepoAuditor` was scanned on this `feat`
branch (cut from `main`), where `main`'s "prepare public distribution path" had removed
`CLAUDE.md` **and** `AGENTS.md`. So its scanned tree is the stripped public state — the
`fn_blind_spot` is valid for that tree (README is the only run-doc) and `drifted=true`
fired correctly, but it does **not** reflect the codex working branch (which still has
`CLAUDE.md`) or the snapshot state. Lesson: run the pre-step from the repo's canonical
branch when the auditor audits itself.

**Second-order nuance (not a bucket error):** 3 of the 12 `agree_present` rows
(`LoreKeeper`, `Afterimage`, +1) have `evidence_in_primary=false` — the tool reports
present (from a matched primary-file heading) but the verifier found the *runnable command*
in `README.md`. "Right for the wrong reason." Preserved in `rows.json`; doesn't change the
present/absent verdict. A v2 could escalate this to its own bucket.

**Actionable fix surfaced:** broaden `choose_primary_context_file` (or add a `README.md`
fallback for structural claims like run instructions) — this resolves all 4 blind spots.
No additions to `CONTEXT_SECTION_ALIASES` are warranted by this pilot.

**Mechanism verdict:** the workflow is trustworthy on this claim — verifier calls matched
ground truth on every disagreement. Ready to widen to all 6 presence booleans and/or the
full 132-repo population (run the pre-step from each repo's canonical branch; for the
auditor repo specifically, scan a non-stripped branch).

## Widening to all 6 presence claims (run 2026-05-29, branch `feat/widen-audit-six-claims`)

The pre-step now captures `snapshot_claims{}` and `tool_today{}` as dicts over all six
fields (`CLAIM_FIELDS`); the workflow (`scripts/presence-claims-audit.workflow.js`) has the
verifier judge all six in one file-read and the tally produces one cell per (repo × claim).
Report: `output/presence-claims-audit-2026-05-29.md`; cells:
`output/presence-claims-audit-2026-05-29.cells.json`. Same 16-repo sample, 2-repo smoke
first, then 16 Haiku verifiers + 1 Sonnet (~139s, ~864k subagent tokens).

**Result: 96 cells, 80% agreement.** Per-claim scorecard:

| claim | agreement | fn_blind_spot | fn_alias_gap |
|---|---|---|---|
| project_summary_present | 75% | 4 | 0 |
| current_state_present | 87.5% | 2 | 0 |
| stack_present | 75% | 4 | 0 |
| run_instructions_present | 75% | 4 | 0 |
| known_risks_present | 81% | 2 | 1 |
| next_recommended_move_present | 87.5% | 1 | 1 |

Totals: 70 agree_present, 7 agree_absent, **17 fn_blind_spot, 2 fn_alias_gap** (0 overclaim).

**Key finding — the README blind spot is not specific to run instructions; it dominates ALL
six claims.** The same generic-`AGENTS.md`-stub repos (BattleGrid, OrbitForge,
SlackIncidentBot) carry their real summary/stack/run docs in `README.md`, which the tool
never reads as primary. So a single fix — teach `choose_primary_context_file` to fall back
to `README.md` — would lift agreement across the whole claim set, not just one claim.

**The 2 fn_alias_gap cells are NOT real alias gaps.** Both are LoreKeeper
(`known_risks`, `next_recommended_move`). Hand-verification: LoreKeeper's `AGENTS.md` has an
**unclosed ```bash fence under `## How To Run`** (no command, never closed) that swallows the
later `## Known Risks` and `## Next Recommended Move` headings — so the tool's markdown parser
correctly excludes them, while the verifier (reading raw text) counts them as documented. The
aliases `known risks` / `next recommended move` already exist; the real bug is the Codex-OS
`AGENTS.md` generator's malformed fence. The synthesis was hardened to flag fn_alias_gap as
**review candidates** (alias-may-already-exist / malformed-markdown / sub-threshold /
verifier-over-credit) rather than auto-prescribing alias additions — and the run's report did
so correctly.

**GithubRepoAuditor:** all 6 cells are `claim_changed_drift` — the same auditor-audits-itself
confound (CLAUDE.md/AGENTS.md stripped on the `feat` branch cut from `main`'s public-
distribution prep). Valid for that tree; not representative of the canonical branch.

**Verifier-reliability note (carried from the smoke):** the verifier judges *human
readability*, so on malformed-markdown sections it can disagree with the tool's parser. That
makes fn_alias_gap a "review me" bucket, not a "trust me" bucket — the audit surfaces
candidates; a human (or a parser-aware follow-up) adjudicates.

**Not yet done (deliberate):** scaling to all ~132 repos (a `per_tier`/"all" change in the
pre-step), fixing the README blindness, and hardening into a one-command runner — parked per
operator decision.

## Fix + re-verify (branch `feat/readme-fallback-fix`, 2026-05-29)

Closed the loop: fixed the README blindness, then used this audit as the regression test.

**The fix** wires the dormant `readme_text` parameter of `analyze_project_context`
(`src/portfolio_context_contract.py`): each presence boolean is now "documented in the primary
file **OR** the top-level README"; the `context_quality == "none"` gate also considers the
README. Primary-file *identity* is unchanged (surgical). Added
`tests/test_portfolio_context_contract.py` (5 tests; the function previously had **no** direct
unit coverage). Full suite 2087 passed, 0 regressions.

**Verification — measured three ways (the deterministic one is authoritative):**

| measure | agreement | meaning |
|---|---|---|
| pre-fix | 80% (77/96) | baseline |
| **fix-only** (pre-fix verifier verdicts held constant, only `tool_today` recomputed) | **86% (83/96)** | the pure effect of the code change |
| post-fix live re-run | 85% (82/96) | fix effect minus verifier-variance noise |

**The fix did exactly what was predicted: +6 cells** — `stack` 75%→**100%** (4 cells) and `run`
75%→87.5% (2 cells). These are the cases where the README uses a conventional alias heading
(`## Tech Stack`, `## Quick Start`, `## Getting Started`).

**The fix is deliberately partial — it exposed a second, deeper layer.** "README blindness" was
really two problems: (1) *wrong file* (content in README, tool read AGENTS) — now fixed; and
(2) *no matching heading* — project summaries are the **lead paragraph under the `# Title`**
(not an `## Overview` section), and some content sits under bespoke headings
(`## Recommended Default Path`, `## What This Project Is Today`) or nested in sub-sections/code
blocks. Heading-alias matching cannot see those *regardless of which file it reads*. The 11
residual `fn_blind_spot` cells are almost entirely this layer-2 problem; the 2 `fn_alias_gap`
remain the LoreKeeper malformed-fence artifact.

**Methodological finding — the verifier (Haiku) is not perfectly deterministic.** Re-running on
identical files flipped exactly **1 of 96 cells** (Afterimage `next_recommended_move`,
`agree_present`→`fp_overclaim`; the verifier wobbled on whether a generic portfolio-context
block counts as a real "next move"). So a fresh re-run conflates the fix with ~1% verifier
noise. **To measure a fix, hold the verifier verdicts constant and recompute only `tool_today`**
(the deterministic 86% above) — re-running the full fan-out is for confirming the harness
re-runs, not for the before/after number.

**Net:** the fix is verified, the audit functioned as a regression harness, and the loop caught
an over-claim (my initial "~98%, all blind spots close") before it could mislead. Residual work
is the layer-2 heading problem (a harder heuristic change: lead-paragraph summaries, bespoke
headings) — not a file-scope gap. Artifacts: `output/presence-claims-audit-2026-05-29-postfix.md`
and `…-postfix.cells.json`.

## Layer-2 fix: lead-paragraph summaries (same branch, 2026-05-29)

Scoped to the single largest, lowest-risk layer-2 category: project summaries that live as the
**lead paragraph under the `# Title`** rather than under an `## Overview` section (4 of the
residual blind spots, a universal README convention). Deferred the riskier layer-2 cases
(bespoke-heading fuzzy matching, nested-code detection, supporting-file scan) as
false-positive-prone / lower-value.

**The fix:** new `_has_lead_summary` / `_lead_paragraph_text` helpers extract the prose between
the H1 title and the first `##` heading (stripping badges/images, keeping link text); for
`project_summary` only, when no alias section matched, a non-trivial lead paragraph now counts.
4 new tests; full suite 2091 passed, 0 regressions.

**Verified deterministically (verifier verdicts held constant, only `tool_today` recomputed —
the method lesson from the prior round, so no re-sampling noise):**

| step | overall agreement | project_summary |
|---|---|---|
| baseline (no fix) | 76/96 = 79% | 12/16 |
| + README fallback | 82/96 = 85% | 12/16 |
| **+ lead-paragraph (both fixes)** | **86/96 = 90%** | **16/16 (100%)** |

`project_summary` 75% → **100%** (all 4 lead-paragraph blind spots closed); overall **79% → 90%**
across the two fixes. (Baseline shows 79% here, not the earlier 80%, only because one consistent
verdict set is applied across all three columns — making the deltas pure tool-effects.)

**Residual at 90% (≈10 cells) is now mostly non-heuristic or deliberately deferred:** the 2
LoreKeeper malformed-fence cells (generator bug), the Afterimage boilerplate/variance cell, the
GithubRepoAuditor branch confound, and a few deferred bespoke-heading/nested cases. Further gains
need either the riskier layer-2 work or upstream doc/generator fixes — not more file/lead-paragraph
plumbing.
