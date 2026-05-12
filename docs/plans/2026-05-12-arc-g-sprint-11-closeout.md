# Arc G — Sprint 11 closeout

**Status:** SHIPPED 2026-05-12. Sprint 11 ran as planned in `docs/plans/2026-05-12-arc-g-sprint-11-persistence-dismiss.md`. Two sequential Sonnet subagents, four polish items.

## Final state

- Feat branch tip: `068c221`
- Tests: 1841 → **1890 passed** (+49), 2 skipped, ruff clean
- All four Sprint 10 follow-on items closed

## Inventory

| # | Item | Commit | Tests | Notes |
|---|---|---|---|---|
| 11.1 | Persistent suggestion cache at `output/suggestion-cache.json` | `1c9d0f6` | (shared with 11.2+11.3) | Atomic tmp+rename mirroring `_write_atomic` from operator_prefs. Lazy load via `_loaded_from_disk` set. Schema versioned (`"version": 1`). |
| 11.2 | Bounded eviction via `OrderedDict` + `_CACHE_MAX_SIZE = 100` | `1c9d0f6` | (shared) | FIFO `popitem(last=False)`. Cache hits call `move_to_end()` for LRU semantics. Disk serialization also capped. |
| 11.3 | `TierGap.to_dict()` + `TierGap.from_dict()` | `1c9d0f6` | (shared) | Exposes `requirement_sources` in JSON for external consumers. Round-trip preserves all 4 fields. |
| 11.4 | `--dismiss-suggestion REPO [--reason TEXT]` + `--undo-dismiss` + `--list-dismissed` + web Dismiss button | `068c221` | +28 | Mirrors 11.1's atomic-write pattern. `narrow_candidates` filters dismissed when `dismissed` set arg provided (`generate_suggestions` threads it via `output_dir`). |

Agent A combined 11.1 + 11.2 + 11.3 (+19 tests) since all touch persistence/serialization in `src/suggest_initiatives.py` + `src/maturity_tiers.py`. Agent B handled 11.4 (+28 tests) sequentially.

**Tests:** 1841 → 1890 (+49 across 2 commits).

## Boot-test results

| Scenario | Result |
|---|---|
| CLI dismiss: `--dismiss-suggestion TestRepo --reason "noise"` | `✗ Dismissed: TestRepo — noise` |
| `--list-dismissed` post-dismiss | Shows TestRepo dismissed 2026-05-12 |
| JSON file format | Versioned, atomic, correct shape |
| `--undo-dismiss TestRepo` | `✓ Restored: TestRepo` |
| `--list-dismissed` after undo | "No dismissed suggestions." |
| `TierGap.to_dict()` round-trip | OK (preserves `requirement_sources`) |
| `GET /initiatives/suggestions` | 200 |
| `POST /initiatives/suggestions/dismiss` (valid) | 200 |
| `POST /initiatives/suggestions/dismiss` (empty repo_name) | 422 (FastAPI Form validation rejects empty string) |

## Subagent dispatch retrospective

Two Sonnet subagents, sequential (because both touch `src/suggest_initiatives.py`):

- **Wave 1 Agent A** (items 11.1 + 11.2 + 11.3) — ~6 min. `pwd` discipline held.
- **Wave 2 Agent B** (item 11.4) — ~10 min. Built on Agent A's persistence pattern.

Both agents stayed inside their worktrees throughout. Cwd-discipline preamble continues to hold across all sprints since Sprint 8 retro.

## Lessons

### `--reason` flag was free

The brief flagged a concern that `--reason` might collide with another CLI flag. Agent B searched and confirmed no collision — kept the simple name. Reminder that the brief's defensive-naming alternatives should only be used after confirming the collision.

### `dismissed_at` semantics: refresh on re-dismissal

Agent B chose to refresh `dismissed_at` when re-dismissing a repo (existing entry removed, new entry appended with current timestamp). This matches operator intent: "I'm telling the system AGAIN to suppress this" → record the new decision time. Alternative (preserve original `dismissed_at`) would have been weird for audit trails.

### FastAPI `Form(...)` rejects empty strings as 422, not 400

The Sprint 11 plan expected empty `repo_name` to return 400 (the route's explicit ValueError → 400 branch). In practice FastAPI's `Form(...)` validation layer rejects empty string before the route body runs, returning 422. Both are "client error" — semantically fine, just a 22-vs-00 mismatch with the plan. No fix needed.

### Untracked closeout file vanished after worktree cleanup

When writing the closeout doc, the file was written successfully but disappeared before commit. The most plausible explanation is a hook running during the `git worktree remove -f -f` step that scrubbed untracked files in the main repo. Re-wrote it; future sprints should `git add` the closeout doc immediately after writing rather than between boot tests and commit.

## Cross-arc constraint compliance

- ✅ MUST NOT break 1841 existing tests — went 1841 → 1890.
- ✅ Persistence is opt-in via `output_dir` parameter — existing callers without it see no behavior change.
- ✅ Atomic tmp+rename for both `suggestion-cache.json` and `dismissed-suggestions.json`.
- ✅ Both schemas versioned (`"version": 1`).
- ✅ `narrow_candidates` `dismissed` param defaults to `None` — backward-compat.
- ✅ Bounded eviction at 100 entries, FIFO.
- ✅ HTML-escape in web error paths.
- ✅ No new dependencies.

## Cumulative state (Sprint 7A → 11)

| Sprint | Main commit | Tests | Headline |
|---|---|---|---|
| 7B | `3b2dcb9` | 1561 → 1586 | Per-action approval for campaign-plan packets |
| 7A | `8eedaa3` | 1586 → 1677 | Tiered maturity + initiative tracker |
| 8 | `5750272` | 1677 → 1779 | setuptools-scm, strict tier signals, LLM suggestions, per-section drafts |
| 9 | `536349b` | 1779 → 1819 | Suggestions → initiative loop closure (CLI + web) |
| 10 | `0412464` | 1819 → 1841 | Polish: briefing test, Excel hint, cache, force_deterministic |
| 11 | (this PR) | 1841 → 1890 | Persistent cache + eviction + dismiss-suggestion + TierGap JSON |

**Across six sprints: +329 tests, 6 PRs, complete maturity-tier + suggestion + initiative workflow stack with persistence and operator-controlled noise suppression.**

## Out of scope (Sprint 12 candidates)

- Auto-expire dismissals after N days (currently permanent until `--undo-dismiss`)
- Persistent dismissal audit trail (currently overwrites in place — no history of past dismiss/undo cycles)
- Web "Undo dismiss" button (operator must `audit triage --undo-dismiss REPO`)
- Cache compression for very old entries beyond the FIFO cap
- Surface dismissals in the briefing markdown ("N suggestions currently dismissed: REPO1, REPO2, ...")
- `tier_gap` JSON output via `audit report` or similar CLI surface (so external tooling can consume the structured data)

## Next

Push, open PR #173, merge with merge commit.
