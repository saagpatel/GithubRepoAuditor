# Arc G — Sprint 10 closeout

**Status:** SHIPPED 2026-05-12. Sprint 10 ran as planned in `docs/plans/2026-05-12-arc-g-sprint-10-polish.md`. Two parallel subagents, four polish items.

## Final state

- Feat branch tip: `457d363`
- Tests: 1819 → **1841 passed** (+22), 2 skipped, ruff clean
- All four Sprint 9 follow-on items closed

## Inventory

| # | Item | Commit | Tests | Notes |
|---|---|---|---|---|
| 10.1 | Briefing render smoke test (`--include-suggestions`) | `aaf2873` | +3 | Scope-check confirmed render path was already wired; tests guard against regression. |
| 10.2 | Excel "(approx.)" hint in Initiative Tracker sheet | `aaf2873` | +7 | New `_format_missing_requirements(gap)` helper that consumes `TierGap.requirement_sources` and appends `" (approx.)"` to proxy-derived items. Legacy-empty-sources falls back gracefully. |
| 10.3 | `cache_key` parameter + module-level `_suggestion_cache` dict | `3cfc7b3` | +5 | In-process opt-in cache. Caller controls key cardinality. `clear_suggestion_cache()` exported for tests + invalidation. Route uses `f"{generated_at}\|target={target or 'auto'}"`. |
| 10.4 | `force_deterministic: bool = False` parameter | `3cfc7b3` | +5 | Bypasses LLM entirely; returns `(suggestions, 0.0)`. `accept_suggestion()` switched from `budget_usd=0.0`+broad-except to `force_deterministic=True`. |

Tests landed: 1819 → 1841 (+22).

## Boot-test results

- `GET /initiatives/suggestions` → 200
- `GET /initiatives` → 200
- `generate_suggestions([], force_deterministic=True)` → `([], 0.0)` (no exception, no provider call)
- CLI surface check: `audit triage --help` does NOT mention `deterministic` or `force-deterministic` — internal API only, no leak.

## Subagent dispatch retrospective

Two Sonnet subagents, parallel Wave 1 (no overlap):

- Agent A (`a202c160c9e27e0e3`): items 10.1 + 10.2 — touched `tests/test_briefing.py`, `src/excel_initiative_tracker_helpers.py`, `tests/test_excel_initiative_tracker.py`. ~6 min.
- Agent B (`af9f4a919f45aebe8`): items 10.3 + 10.4 — touched `src/suggest_initiatives.py`, `src/serve/routes.py`, `tests/test_suggest_initiatives.py`, `tests/test_initiatives_suggestions_route.py`. ~6 min.

Both agents stayed inside their worktrees (cwd-discipline preamble continues to hold).

## Lessons (recurring)

### Cwd shift after worktree creation hit the LEAD this time

When Agent B completed and the lead attempted to cherry-pick, the lead's bash session had silently cwd'd INTO Agent B's worktree directory. The cherry-pick ran on the wrong branch (the worktree's branch, where the commit already existed) and reported "empty cherry-pick". Recovery:
- `cd /Users/d/Projects/GithubRepoAuditor`
- `git switch feat/arc-g-sprint-10` (a different branch — `fix/diff-tier-promoted-flag` from a parallel session — had become active)
- Cherry-pick both commits cleanly

**Action item:** every cherry-pick command should be prefixed with `cd /Users/d/Projects/GithubRepoAuditor && git switch feat/arc-g-sprint-<N> && git cherry-pick <SHA>` to guarantee branch + cwd state. Add this as a checklist in the next Sprint plan template.

### The "leaked!" false alarm

Initial CLI-surface check used `grep ... | head -3 && echo "leaked!"`. The pipe's exit code reflected `head`, not `grep`, so the conditional was always truthy. Fixed by using `grep -c` and reading the count directly. Trivial bug but a useful reminder that pipelines + `&&` need careful exit-code reasoning.

## Cross-arc constraint compliance

- ✅ MUST NOT break 1819 existing tests — went 1819 → 1841, all pass.
- ✅ Cache is opt-in via `cache_key` param — existing callers without it see no behavior change.
- ✅ `force_deterministic` defaults to False — existing callers see no behavior change.
- ✅ Excel hint format matches web template's semantic ("(approx.)" suffix) but rendered as plain text since Excel doesn't render HTML.
- ✅ No new dependencies.

## Out of scope (next sprint candidates)

- **Persistent cache** (cross-process / cross-restart) — current cache is in-process only. If operator workflow benefits from surviving restarts, consider an on-disk SQLite-backed cache.
- **Cache eviction** — unbounded today. Cardinality is naturally low (truth `generated_at` changes infrequently), but if it grows past 100 entries, swap to `functools.lru_cache`-style bounded dict.
- **"Reject suggestion" workflow** — operator currently ignores noisy suggestions silently; an explicit `--dismiss-suggestion REPO` flag could suppress a repo from future suggestions (write to `output/dismissed_suggestions.json`).
- **Suggestions in `audit run --briefing` markdown output via stdout** — currently the briefing markdown lands in `output/briefing-*.md` but the CLI doesn't print it inline. Small UX improvement.
- **`(approx.)` hint in the JSON output** — `tier_gap` already carries `requirement_sources`; the JSON serializer of `TierGap` (if any) could expose it as a structured field for external consumers.

## Next

Push, open PR #172, merge with merge commit.
