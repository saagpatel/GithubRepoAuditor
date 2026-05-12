# Arc G — Sprint 8 closeout

**Status:** SHIPPED 2026-05-12. Sprint 8 ran as planned in `/Users/d/.claude/plans/sprightly-tumbling-pumpkin.md`. All five items merged onto `feat/arc-g-sprint-8`.

## Final state

- Feat branch tip: `4e7e39a`
- Tests: 1677 → **1779 passed** (+102), 1 skipped, ruff clean
- All 4 candidate areas from Sprint 7A closeout addressed

## Inventory

| # | Item | Commit | Tests | Notes |
|---|---|---|---|---|
| 8.1 | `setuptools-scm` tag-derived versioning | `d234496` | +3 | Sonnet subagent (`a13a1a3958f7cf622`). `pyproject.toml` switched to `dynamic = ["version"]` with `fallback_version = "0.19.0"`. No release-workflow edits needed (`fetch-depth: 0` was already there). Local `python -m build` produced `0.19.1.dev23+g8eedaa3...` (correct — 23 commits past v0.19.0 tag). |
| 8.2 | Strict signals (`has_tests`/`has_ci`/`readme_char_count`/opt-in `release_count`) in portfolio-truth | `c0bf2f7` | +18 | Sonnet subagent (`a564055bce8b52c87`) "failed" mid-task self-assessment but its artifacts were intact in main checkout (escaped worktree isolation — see Lessons). Lead recovered via stash + direct commit. |
| 8.3 | `maturity_tiers.py` consumes strict signals with proxy fallback; `TierGap` gains `requirement_sources` | `7de2244` | +21 | Sonnet subagent (`a2e06826cc99d73e4`). 6 tier checks now use strict-when-present pattern via `_is_sprint8_snapshot` sentinel. Backward-compatible. |
| 8.4 | `--suggest-initiatives [TARGET_TIER]` CLI flag + briefing surface | `4e7e39a` | +31 | Sonnet subagent (`afd55029b659ae019`). New module `src/suggest_initiatives.py`. Deterministic ranking fallback when no LLM provider available. Cost-guarded (default $0.10). `--include-suggestions` briefing modifier (default off). |
| 8.5 | Per-section approval for `--draft-readmes` packets via sub-records | `561bdf1` | +29 | Sonnet subagent (`a3f56a4b7166dd7fc`). Mirrors Sprint 7B sub-action pattern. New `approval_subject_type = "draft-readme-section"`. Apply gate is all-or-nothing per packet in v1. |

**Tests:** 1677 → 1779 (+102 across 5 commits). Exit-criteria target was ~1770; we landed at 1779.

## Boot-test results (post-merge)

- `python3 -m src triage saagpatel --suggest-initiatives` (no LLM key) → deterministic fallback prints 8 candidates with `$0.0000` cost line. ✅
- `GET /` → 200; `/approvals` → 200; `/initiatives` → 200; `/approvals/nonexistent/draft-sections` → 404. ✅

## Subagent dispatch retrospective

Sprint 8 used the proven sequential→parallel pattern from Sprint 7A:

- **Wave 1** (parallel, 3 Sonnet agents): 8.1 + 8.2 + 8.5 — independent items.
- **Wave 2** (1 agent): 8.3 — depends on 8.2's schema.
- **Wave 3** (1 agent): 8.4 — depends on 8.3's tightened tiers.

Total wall-clock: ~30 min for Wave 1, ~5 min cherry-pick interleaving, ~6 min for Wave 2, ~16 min for Wave 3. **~57 min for ~+102 tests** of feature work — Sonnet-implemented, Opus-coordinated. The model-routing discipline (Opus stays coordinator, Sonnet implements) held throughout.

## Lessons learned

### Wave-1 Agent B escaped worktree isolation

The subagent assigned to Sprint 8.2 (`a564055bce8b52c87`) wrote its file modifications into the LEAD's main checkout instead of its isolated worktree. Symptoms: lead's `git status` showed unexpected modifications during the wait; the agent's worktree at `.claude/worktrees/agent-a564055bce8b52c87` stayed clean at base SHA; cherry-pick of a parallel agent's commit (8.5's) failed because lead's `src/cli.py` was dirty.

**Recovery:** Lead `git stash push -m "..."` of the in-progress files, cherry-picked the unblocked commit (8.5), then after Agent B reported a self-diagnosed "failure" (it confused itself thinking `ruff format` had reverted its work), lead popped the stash, ran the suite (all 18 new tests passed), and committed Agent B's recovered work directly to the feat branch.

**Root cause:** the agent's shell tools didn't honor the worktree's cwd. The agent's prompt did not prepend `cd <worktree path>` to its bash calls (or the harness didn't enforce it). Subsequent Wave-2 and Wave-3 agents received an explicit "CRITICAL — cwd discipline" preamble in their briefs and verified `pwd` before every edit — neither escaped.

**Action items for next sprint's briefs:**
1. Every subagent brief should open with: "Before ANY edit, run `pwd` and confirm it shows your worktree path."
2. Add a "trust `git diff HEAD` over file-state system reminders" line — Agent B got fooled by a system-reminder showing post-format file content that didn't match its mental model.
3. Lead should periodically `git status` during long parallel waves to catch escapes early.

### Subagent self-failure ≠ work failure

Agent B reported (paraphrased): "ruff format reverted my changes; tests gone; failing." In reality, the agent had written 389 lines across 5 files, 18 tests, all passing, ruff-clean. The agent's confusion came from misreading file-state reminders. **Don't trust an agent's "failure" report — always check the artifacts.** This sprint's recovery saved ~30 min of re-work.

### TaskCompleted hook noise: ignored throughout

The TaskCompleted hook keeps blocking task-status transitions on pre-existing mypy errors (~425 errors in 100 files). This is documented as expected hook noise and was ignored at every step. The tasks list shows many "in_progress" tasks that are actually done.

## Cross-arc constraint compliance

- ✅ MUST NOT break 1677 existing tests — went 1677 → 1779, all pass.
- ✅ No new runtime dependencies (only `setuptools-scm>=8` as a build-time requirement).
- ✅ All schema changes additive (pre-Sprint-8 portfolio-truth + pre-Sprint-8 draft-readme records continue to work).
- ✅ `compute_tier`/`tier_gap` public signatures unchanged.
- ✅ LLM cost-guarded with default $0.10 ceiling and deterministic fallback when no provider.

## Deferred to Sprint 9 (out of scope per plan)

- Web route `GET /initiatives/suggestions` rendering 8.4 output in HTML with "Set initiative" buttons
- Partial-section apply for draft-readmes (currently all-or-nothing per packet)
- Tightening the "README staleness" criterion (no strict signal exists yet)
- LLM-driven auto-creation of initiatives from suggestions (currently operator must manually `--set-initiative`)
- Threading the strict-signal-vs-proxy hint into the web `/initiatives` template (TierGap.requirement_sources is populated but the template doesn't render it yet)

## Next

Push, open PR #170, merge with merge commit. Then tag a release if the operator wants v0.20.0 published.
