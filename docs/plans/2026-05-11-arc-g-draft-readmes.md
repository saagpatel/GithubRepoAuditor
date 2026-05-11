# Arc G — Sprint 5: Agentic README authoring (`--draft-readmes`)

**Status:** Sprint 5 / Arc G kickoff. Drafted 2026-05-11, immediately after Arc F merge (`9e0c636`) and `v0.19.0` tag.

**Why now:** Arc F shipped the semantic index (S3.1), operator preference memory (S3.3), LLM cost guard (S3.5), and the local web UI (S4.1) — all of which compose into the most natural next product step: have the LLM write draft READMEs for repos that need them, route the diff through the approval ledger, and let the operator review/edit/approve in the web UI.

This is the first item from the Arc F backlog (line 336 of `docs/plans/2026-05-10-arc-f-expansion-roadmap.md`). Sprint 5 ships this end-to-end. Sprint 6+ items (planner agent, tier tracker) remain in backlog.

---

## Scope

A new flag `audit report --draft-readmes` (also accessible via legacy `audit <user> --draft-readmes`) walks every repo where:

1. README is **stale** (S1.4 `readme_stale=True` — README touched > 5x older than latest code, code touched < 90 days ago), OR
2. README is **missing** entirely, OR
3. README is **trivially short** (< 200 chars excluding badges/headings), OR
4. Operator explicitly opts the repo in via `--draft-readmes-repo <name>` (repeatable)

For each qualifying repo, the LLM authors a draft README using:

- **Repo metadata** — language, topics, stars, latest release notes, license
- **Top-level file tree** — first two directory levels
- **Semantic neighbors** — `SemanticIndex.find_neighbors(repo, k=3)` from S3.1 supplies stylistic context ("repos in this portfolio look like this")
- **Existing README** if present (the LLM should improve, not rewrite, where possible)
- **Recent commit messages** — last 10 commits, subject lines only

The output is a **diff packet** (not a wholesale replacement file) recorded in the approval ledger with `action_type="draft-readme"`. Each packet contains:

```json
{
  "repo_name": "...",
  "action_type": "draft-readme",
  "current_readme_sha": "...",
  "proposed_readme": "...",
  "diff_summary": "Added: install, usage, badges sections",
  "llm_provider": "anthropic|github-models",
  "llm_model": "...",
  "llm_cost_usd": 0.0042,
  "generated_at": "2026-05-11T...",
  "context_repos": ["repo-a", "repo-b", "repo-c"]
}
```

Operator review path:

1. CLI: `audit triage --approval-center --approval-view ready` lists the packets
2. Web UI: `/approvals` page shows each draft with an "expand diff" HTMX action that renders the proposed README beside the current one
3. Approve via existing `approval_request_approve` flow → packet moves to `approved-manual` state
4. Apply via `audit report --apply-readmes` (S4 already wires this for some action types — extend if needed)

---

## Inventory

| # | Item | Status | Notes |
|---|---|---|---|
| 5.1 | `src/draft_readmes.py` module with `qualify_repos()`, `build_context()`, `generate_draft()` | ✅ Shipped | Pure functions, easy to unit-test |
| 5.2 | Wire `--draft-readmes` flag into `audit report` subcommand + legacy flat path | ✅ Shipped | Use existing approval ledger writer (no schema changes) |
| 5.3 | Preference suppression — skip repos where the operator rejected a draft-readme 3+ times | ✅ Shipped | Reuses S3.3 `operator_prefs.detect_suppressions()` |
| 5.4 | Web UI: `/approvals` shows draft-readme packets with side-by-side diff partial | ✅ Shipped | HTMX partial swap, no JS |
| 5.5 | `audit report --apply-readmes` writes approved drafts back via GitHub Contents API | ✅ Shipped | Reuse existing apply path if present, else add minimal one |
| 5.6 | Cost guard integration — abort batch if cumulative LLM spend > `--max-llm-spend` | ✅ Shipped | S3.5 `CostTracker` already wired into providers |
| 5.7 | Tests + docs + Sprint 5 closeout | ✅ Shipped | Final |

---

## Cross-arc principles inherited

From Arc F's three durable lessons:

1. **External-API specs go stale.** When using the GitHub Contents API for README writeback, treat the docs as "as-of-date" and validate against actual response shape.
2. **Module-level state keyed by `id()` is unsafe.** No registration caches keyed by object identity in this sprint.
3. **Subagent worktree branch-base brittleness.** When dispatching, verify the worktree base SHA matches `feat/arc-g-draft-readmes` tip before letting the subagent commit. If the agent reports a test count that doesn't match current, that's the signal of wrong base.

---

## Open questions (resolve at kickoff)

| Q | Default | Notes |
|---|---|---|
| Should we run all qualifying repos by default, or require explicit opt-in like Arc D's automation? | **Opt-in default.** Operator must pass `--draft-readmes-repo <name>` or `--draft-readmes-all`. | Safer; matches Arc D's trust-bar discipline. |
| Provider default — Anthropic or GitHub Models? | **Reuse existing `--narrative-provider` default** (Anthropic if API key set, else GitHub Models). | No new resolution logic. |
| Should drafts be diff-format or full-file replacement? | **Full file as proposed_readme, but show diff in UI.** | Easier to author; UI computes diff at render time. |

---

## Exit criteria

- `audit report --draft-readmes-repo <name>` generates a draft README and writes a packet to the approval ledger
- `audit triage --approval-center --approval-view ready` lists the packet
- Web UI `/approvals` renders the draft beside the current README
- Approve via existing flow → packet moves to `approved-manual`
- `audit report --apply-readmes` writes the approved draft to GitHub
- All 1469 existing tests still pass; +20-40 new tests for the new module
- Sprint 5 closeout appended to this doc with shipped/stopped/lessons

---

## Sprint 5 closeout (2026-05-11)

**Shipped (all 7 items):**

- **5.1 — `src/draft_readmes.py` core module.** `DraftReadmePacket` dataclass; `qualify_repos()` with opt-in / all-qualifying / no-op modes; `build_context()` bundling metadata + tree + neighbors + recent commits; `generate_draft()` taking provider + cost_tracker, catching `BudgetExceededError` and re-raising with repo context; `write_packets_to_ledger()` adapting to the existing warehouse `approval_subject_type` / `subject_key` columns rather than the docstring's `action_type` / `target_context`. Commit `f0fa9c5`.
- **5.2 — `audit report --draft-readmes` CLI wiring.** Three new flags: `--draft-readmes` (opt-in mode), `--draft-readmes-all` (every qualifying repo), `--draft-readmes-repo REPO` (repeatable explicit list). New `_run_draft_readmes_mode()` dispatched above the `serve` check. Resolves provider via the existing `_resolve_provider()` (reuses S1.2). Commit `f0fa9c5`.
- **5.3 — Preference suppression.** `is_suppressed(prefs, action_type="draft-readme", target_context=repo_name)` consulted before each `generate_draft()` call. After the batch, `detect_suppressions(prefs_path, output_path)` refreshes auto-suppressions based on existing rejection counts. No new schema. Commit `f0fa9c5`.
- **5.4 — Web UI draft-readme diff view.** New `GET /approvals/{record_id}/draft-diff` handler returning an HTMX partial (`src/serve/templates/draft_diff.html`) with two-column CSS grid (Current / Proposed). "View diff" HTMX button on each draft-readme row in `approvals.html`. `.draft-diff*` CSS classes in `audit.css` with responsive collapse at 700px. Existing approve/reject handlers worked without modification — they don't inspect `approval_subject_type`. +6 tests. Commit `54c26b2`.
- **5.5 — Ledger-driven writeback.** `--apply-readmes` now reads approved packets from the approval ledger when `--improvements-file` is absent. New `load_approved_drafts()` (skips packets > 30 days), `mark_draft_applied()`, `record_draft_apply_failure()` in `src/draft_readmes.py`. `_run_apply_improvements_mode` rewritten to merge file + ledger sources. Dry-run delegates to `apply_readme_updates(dry_run=True)`. State transitions: successful apply → `applied`; GitHub API failure → stays `approved-manual` with a failure event. +9 tests. Commit `d462eb5`. **Option A** chosen (reuse `--apply-readmes`, no new flag).
- **5.6 — Cost guard wiring.** Delivered inside S5.1-5.3 — `_run_draft_readmes_mode` constructs `CostTracker(budget_usd=args.max_llm_spend, output_path=output_dir)` from `--max-llm-spend`, passes it into `generate_draft()`. `BudgetExceededError` halts the batch with telemetry written for the records that succeeded. Verified via the existing `--max-llm-spend 0.0001` smoke test in the agent's S5.1-5.3 verification.
- **5.7 — This closeout.**

**Exit criteria verification:**

- `audit report --draft-readmes-repo <name>` generates a draft + writes packet: ✅
- `audit triage --approval-center --approval-view ready` lists the packet: ✅ (existing flow, packets are normal `approval_records` rows)
- Web UI `/approvals` renders the draft side-by-side with current README: ✅
- Approve via existing flow → state `approved-manual`: ✅ (no handler changes)
- `audit report --apply-readmes` writes approved drafts via GitHub Contents API: ✅
- 1469 → 1508 tests (+39 net new; spec range was +20-40): ✅
- Ruff clean: ✅
- Sprint 5 closeout appended (this section): ✅

**Lessons:**

1. **Schema-as-implemented beats schema-as-specified.** I scoped 5.1 with a docstring schema of `action_type` / `target_context` for the packet. The actual warehouse columns are `approval_subject_type` / `subject_key`. The agent adapted in-place by storing both shapes (DB columns + nested in `details_json`) instead of trying to migrate the schema or rewrite my spec. **Future plans for ledger-adjacent work should `grep src/warehouse.py` for the actual column names before fixing schema in prose.**
2. **Subagent base-SHA verification + cwd discipline both matter.** The base-SHA gate caught the bad-base hazard cleanly (S5.1-5.3 worktree branched correctly from `136e7da`, my opening sanity check confirmed it). But the second hazard surfaced: when I cherry-picked S5.4, my shell cwd silently shifted into the agent's worktree directory after a hook-triggered cwd recovery, so my next "cherry-pick" landed on the wrong branch with no error. Cost: ~5 minutes of confused reflog spelunking. **Action:** prepend every cherry-pick with `cd /Users/d/Projects/GithubRepoAuditor &&` to force the cwd, and verify `git rev-parse HEAD` matches the expected feat-branch tip both before and after.
3. **In-scope creep can be net positive when the agent stays disciplined.** S5.1-5.3's spec said "wire CostTracker" but the agent delivered the full S5.6 budget gate inside the core module: `BudgetExceededError` catch, telemetry write, partial-batch persistence. I didn't have to spawn a separate agent for 5.6. The agent's report flagged the addition explicitly, so the scope decision was visible rather than smuggled. **Heuristic:** when a scope item is genuinely inseparable from another (cost tracking only makes sense inside the call site), let the agent fold them — but require the report to call it out.

**Plan housekeeping:**

- Inventory items 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7 all flipped to ⏳ → ✅ in the table at the top of this doc. (Done in this closeout commit.)
- `--apply-readmes-from-ledger` flag was considered (Option B) and rejected — Option A (reuse `--apply-readmes` with auto-detect) is in production.

**Branch state:** `feat/arc-g-draft-readmes`, 4 commits ahead of `main`. 1508 tests pass. Ruff clean. Not pushed.

**Next:** PR + merge, then either Sprint 6 (planner agent for campaign authoring — `--plan-campaign "goal"`) or the deferred Tiered maturity + Initiative tracker. Both build on Sprint 5's approval-ledger packet pattern.
