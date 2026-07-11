# HANDOFF — wrap-up work order (Fable → executor model)

*Written 2026-07-11 by the Fable session that produced everything in this folder. The
operator has approved all public artifacts AS-IS (no revisions wanted). Every remaining
task below is execution against locked decisions. No taste calls remain; if you hit one
anyway, stop and ask the operator rather than deciding.*

## State of the world

- `fable-explore/` (this folder): approved public material + discovery docs. Untracked.
- Branch `refactor/scoring-hygiene`, commit `327e21f`: P7 + mechanical P9 items, reviewed
  (python-reviewer, all findings addressed), full gate green (2,863 passed, ruff clean).
  NOT pushed — pushes are operator-run, always.
- Verdict Machine port re-synced to the branch's Python; 21,254/21,254 goldens pass;
  `dist/verdict-machine.html` rebuilt (53.6 KB).
- GHRA main is clean at `f58ad43`.

## Locked decisions (do not revisit, do not "improve")

1. Public-safe = mechanisms + synthetic inputs only. Never repo names, counts beyond what
   the essays already state, or anything from the private estate. The essays/note/explainer
   are FINAL COPY — publish byte-for-byte, no rewording, no added headings, zero em dashes.
2. Explainer route: `/verdict-machine` (08 already links it). Ship `dist/verdict-machine.html`
   as-is; it is self-contained.
3. Publish order: 07 first (or same deploy), then 08 and 09. 08's "wall of amber" line
   links to 09 once live. 08 embeds `diagrams/truth-pipeline.svg`.
4. P1 scope: read-side module ONLY (`src/portfolio_truth_trends.py`) + a `## Movement`
   section in the weekly digest. NO rollups/schema change (the "transitions block in
   rollups" idea from 05 is OUT — rollups are producer-computed and schema-pinned).
5. P8 scope: emit `scored_dimensions` + `scored_weight_sum` per repo; grade rendered as
   qualified ("B on 7/10 dimensions") when scored_weight_sum < 0.85 of full basis.
   Report-only: no tier-gating change, no conservative mode.
6. `goldens.json` (12 MB) is regenerable — gitignore it, never commit it.
7. Rejected paths (don't resurrect): dashboard-screenshot tour; live portfolio widget;
   ES modules in the explainer (file:// CORS); composite health score.

## Work order

### T1 — Commit this folder (housekeeping)
Branch `docs/fable-explore-material` off main. Add `fable-explore/verdict-machine/golden/goldens.json`
to .gitignore (repo root or folder-local). Commit everything else in `fable-explore/`.
Hand the operator the push + merge one-liner. Note: while this branch is unmerged, the
files sit only on it — merge promptly so main's working tree keeps them.

### T2 — Land `refactor/scoring-hygiene`
Operator runs: `git push -u origin refactor/scoring-hygiene`, then PR + merge (house
style: PR like #169-#172). Nothing for the executor beyond preparing the PR body from
the commit message. After merge: delete the local branch, confirm `origin/main` has it.

### T3 — Publish the public material (portfolio-index repo, saagarpatel.dev)
Follow the repo's AGENTS.md + these hard-won gotchas (from operator memory, all verified):
- Essay sources live in `scripts/sources/session-NN/` (NOT a `writing/*.md` mirror).
  Next NN = max(existing on disk, git log) + 1 — verify with `git -C`, don't trust index files.
- Register each piece in build-writing's SOURCES + CLUSTERS.
- Run the FULL canonical build sequence (`check-idempotency.sh`), never a single
  `build-*.py` — `build-related.py` injects blocks that solo runs drop.
- Two-commit date-settle: idempotency re-dates feed/sitemap/corpus, so build → commit →
  rebuild → commit the settled dates.
- Re-sign `mcp.json` after corpus changes; the MCP must follow the site.
- Scrub `.serena/` from the deploy copy before deploying.
- Deploy via the git-free Vercel flow; verify live via `vercel inspect` (alias → dpl id),
  allow ~5 min. Homepage is GENERATED — never hand-edit it.
- Content mapping: 07 + 09 → /writing essays; 08 → /notes (embeds the SVG — copy
  `diagrams/truth-pipeline.svg` into the site's diagram assets); explainer → `/verdict-machine`
  as a standalone page (no site chrome needed; it's self-contained).
- Suggested descriptions for 07/08/09 are in each file's header block.
- Before anything goes into the site repo: PII scan the new files (no /Users paths — the
  SVG footer and essay text are already clean, verify anyway).

### T4 — Implement P1 (verdict-transition ledger) in GHRA
Spec: `fable-explore/05-improvement-proposals.md` P1 + locked decision 4 above.
New `src/portfolio_truth_trends.py`: walk the last N (default 8) `portfolio-truth-*.json`
artifacts in `output/history` order (the #172 lineage resolver proves they're walkable);
emit per-repo attention-lane transitions (with dates), activity-status streaks, risk-tier
changes. Wire a `## Movement` section into the weekly digest ("3 repos slid active→stale;
1 recovered decision-needed→active-infra"). Tests: synthetic artifact fixtures covering
no-movement, single transition, repo appearing/disappearing between snapshots. Feature
branch, full gate (pytest + ruff), reviewed before commit.

### T5 — Implement P8 (partial-run disclosure) in GHRA
Spec: 05 P8 + locked decision 5. Emit `scored_dimensions`/`scored_weight_sum`; qualified
grade label in JSON, Excel, and dashboard when basis < 0.85. Keep the math untouched.
Include the missing seam test from review: exercise the `getattr(custom_weights,
"overrides", None)` extraction at `src/app/run_audit.py:559` through `_analyze_repos`
with a real ScoringProfile (not a monkeypatched dict).

### T6 — After T3 is live
Update `00-INDEX.md` statuses (Draft → PUBLISHED with URLs). Log a SHIPPED activity to
bridge-db for the published material (caller per your harness).

## Verification commands

- GHRA gate: `uv run pytest -q` (2,863+ pass) and `uv run ruff check .` — capture to a
  file and echo `$?`; never pipe a gate through tail.
- Goldens (only if `portfolio_risk.py`/`portfolio_pathing.py`/`context_quality.py`/
  `portfolio_truth_reconcile.py` change again):
  `uv run python fable-explore/verdict-machine/golden/generate_goldens.py` then
  `cd fable-explore/verdict-machine/golden && node run_golden.cjs`, then
  `node ../build_single.mjs` to rebuild dist.
- Site: canonical build sequence, then `vercel inspect` on the fresh deployment.

## Standing constraints

- Never push; hand the operator one-liners (prefix with `git push -u origin <branch>`).
- Feature branches always; conventional commits; no Co-Authored-By trailers; no PII in
  commits/PRs.
- Verify on bytes: diffs and test output, never exit codes or a subagent's claim.
- Anything voice/copy-shaped that comes up (a publish-flow edge case wanting a reworded
  sentence, a new description string) → STOP, ask the operator; final copy is locked.
