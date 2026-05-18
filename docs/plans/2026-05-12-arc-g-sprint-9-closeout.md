# Arc G — Sprint 9 closeout

**Status:** SHIPPED 2026-05-12. Sprint 9 ran as planned in `docs/plans/2026-05-12-arc-g-sprint-9-suggestions-loop.md`. Two items merged onto `feat/arc-g-sprint-9`.

## Final state

- Feat branch tip: `b4ddc2d`
- Tests: 1779 → **1819 passed** (+40), 2 skipped, ruff clean
- Loop closed: operator can now accept LLM-suggested initiatives via CLI OR web with one click

## Inventory

| # | Item | Commit | Tests | Notes |
|---|---|---|---|---|
| 9.1 | `accept_suggestion()` backend + CLI `--accept-suggestion REPO` flag + `default_deadline_for_effort()` | `5326268` | +23 | Sonnet subagent (`a7280f47d129a138a`). Single backend entry for CLI + web. Re-uses existing `--target-tier`/`--deadline` flags. Idempotent re-accept via `upsert_initiative`. |
| 9.2 | `GET /initiatives/suggestions` web page + `POST /initiatives/accept` HTMX endpoint + `(approx.)` hint threading | `b4ddc2d` | +17 | Sonnet subagent (`aa298a32e6dcb90e4`). HTMX swap pattern matches Sprint 7B's per-action approval. Catches route-ordering issue (parametric route collision) — agent fixed proactively. |

**Tests:** 1779 → 1819 (+40 across 2 commits). Exit-criteria target was ~1820; we landed at 1819 (one short, well within margin).

## Boot-test results (post-cherry-pick, pre-merge)

| Endpoint | Result |
|---|---|
| `GET /` | 200 |
| `GET /initiatives` | 200 |
| `GET /initiatives/suggestions` | 200 |
| `POST /initiatives/accept` (nonexistent repo) | 400 |
| Nav link `/initiatives/suggestions` present in base.html | 1 occurrence |
| CLI `audit triage --help` shows `--accept-suggestion REPO` | ✅ |

## Subagent dispatch retrospective

Two-wave sequential pattern, smaller than Sprint 8 (which had parallel Wave 1). Each agent completed its scope cleanly:

- **Wave 1** (1 Sonnet agent): 9.1 — ~7 min wall-clock
- **Wave 2** (1 Sonnet agent): 9.2 — ~6.5 min wall-clock
- Total: ~14 min agent runtime for +40 tests + new web page + threaded UI hints

Neither agent escaped its worktree this time. The "cwd discipline preamble" added after Sprint 8's Wave-1 Agent B escape kept both agents inside their isolated worktrees. Both reported `pwd` confirmation per the brief.

## Lessons

### Route ordering matters for FastAPI parametric paths

Agent B initially placed the new `GET /initiatives/suggestions` route after the existing `GET /initiatives/{repo_name}/gap` route in `src/serve/routes.py`. FastAPI registers routes in declaration order, so `/initiatives/suggestions` would have been matched as `/initiatives/{repo_name=suggestions}/gap` (missing `/gap` → 404 on the actual `/initiatives/suggestions`). The agent caught this proactively when its initial GET test returned the wrong route and moved the new route before the parametric one.

**Action item for future briefs:** when adding fixed-path routes that share a prefix with parametric routes, explicitly call out the ordering requirement.

### Default deadline mapping is a single source of truth

`default_deadline_for_effort()` is called by both:
- `accept_suggestion()` when no explicit deadline is supplied
- The web template (`initiatives_suggestions.html`) via the route handler, to pre-fill the deadline input

This means changing the mapping (e.g. shortening "medium" from 30d to 21d) only requires editing one function. No duplication.

### `budget_usd=0.0` in `generate_suggestions()` triggers BudgetExceededError, not deterministic fallback

The Sprint 9 plan assumed `budget_usd=0.0` would force the deterministic-fallback path. Agent A discovered that `generate_suggestions(budget_usd=0.0)` actually raises `BudgetExceededError` before any LLM call (because estimated cost > $0.00). The agent's mitigation: catch `Exception` broadly in `accept_suggestion`'s deadline-derivation path and fall back to "medium" effort if no suggestion data is available. This works but is fragile.

**Action item for Sprint 10 or beyond:** consider adding an explicit `force_deterministic: bool` parameter to `generate_suggestions()` so callers can request fallback without abusing the budget.

## Cross-arc constraint compliance

- ✅ MUST NOT break 1779 existing tests — went 1779 → 1819, all pass.
- ✅ Single backend entry (`accept_suggestion()`) for CLI + web — no duplicated validation.
- ✅ Default deadline mapping is one function, called by both surfaces.
- ✅ Re-accepting an existing initiative is idempotent.
- ✅ HTML-escaping in error responses prevents XSS via repo_name input.
- ✅ No new dependencies.
- ✅ `accept_suggestion()` re-validates `target > current` at write time (handles stale suggestions).

## Deferred items still pending (per Sprint 8 closeout)

These remain out of scope:
- Partial-section apply for `--draft-readmes` (risky — produces broken READMEs)
- README staleness strict signal (proxy works fine)
- Bulk-accept ("Accept all suggestions" button) — premature, would mask per-suggestion review
- "Reject suggestion" workflow that suppresses repeated noise — defer until operator feedback

## Out of scope (new items to consider for Sprint 10)

- `--include-suggestions` modifier on `--briefing` is currently a no-op until the briefing's `render_markdown` is wired to actually render `suggested_initiatives`. Sprint 8.4 added the dataclass field; we should verify the markdown renders the section (TODO: spot-check `audit triage --briefing --include-suggestions`).
- The `(approx.)` hint is in `/initiatives` and the gap partial but not in the Excel "Initiative Tracker" sheet (Sprint 7A.4). Adding it there is a small Excel-helpers patch.
- `generate_suggestions()` could cache results per portfolio-truth `generated_at` timestamp to avoid LLM re-calls on browser refresh. Cost mitigation if the suggestions page is hit frequently.

## Next

Push, open PR #171, merge with merge commit. Then tag v0.20.0 if the operator wants a release published with both Sprint 8 + 9 features.
