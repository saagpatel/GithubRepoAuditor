# Arc G — Sprint 10: Suggestions polish + briefing render verify + cache

**Status:** Drafted 2026-05-12 after Sprint 9 shipped (main `536349b`). Sprint 10 / Arc G handles four polish items surfaced in Sprint 9's closeout.

## Context

Sprint 9 closed the suggestion → initiative loop end-to-end. Closeout flagged four follow-on items:

1. **Verify `--briefing --include-suggestions` renders the section** — scope-check found it IS already wired (`src/briefing.py` line 613). Needs a smoke test only.
2. **`(approx.)` hint in Excel "Initiative Tracker" sheet** — Sprint 9 added the hint to web `/initiatives`; Excel sheet still missing it.
3. **Cache `generate_suggestions` per portfolio-truth `generated_at`** — currently every `GET /initiatives/suggestions` hit triggers a fresh LLM call. Browser refresh = repeat cost.
4. **`force_deterministic: bool` parameter on `generate_suggestions`** — replaces the `budget_usd=0.0` workaround in `accept_suggestion()`.

All four are small. Sprint 10 ships them together as polish.

## Inventory

| # | Item | Effort | Status |
|---|---|---|---|
| 10.1 | Smoke test that `audit triage --briefing --include-suggestions` actually renders "## Suggested Initiatives" in markdown | tiny | ⏳ |
| 10.2 | Thread `requirement_sources` into Excel "Initiative Tracker" sheet — render `(approx.)` next to proxy-derived gap requirements | small | ⏳ |
| 10.3 | Cache layer for `generate_suggestions` — keyed by truth `generated_at`, invalidated on schema change | small-medium | ⏳ |
| 10.4 | `force_deterministic: bool = False` parameter on `generate_suggestions` — bypasses LLM call without abusing budget | small | ⏳ |
| 10.5 | Closeout + PR | small | ⏳ |

**Test count target:** 1819 → ~1850 (+25-35 new tests).

## Subagent dispatch

Two Sonnet subagents, parallel (no overlap):

- **Agent A** — items 10.1 + 10.2. Touches `tests/test_briefing.py` + `src/excel_initiative_tracker_helpers.py` + `tests/test_excel_initiative_tracker.py`. No collision with B.
- **Agent B** — items 10.3 + 10.4. Touches `src/suggest_initiatives.py` + `src/serve/routes.py` + `tests/test_suggest_initiatives.py`. No collision with A.

Wave 1 (parallel) → closeout. ~10-15 min wall-clock.

**Brief discipline:** cwd preamble required (Sprint 8 retro lesson).

## Schema + code references

### 10.1 — Briefing smoke test

Add 1-2 tests to `tests/test_briefing.py`:
- Build a briefing with `include_suggestions=True` and a mock provider returning canned suggestions
- Assert `render_markdown(briefing)` output contains `"## Suggested Initiatives"` and at least one bullet entry
- Negative test: with `include_suggestions=False`, the section is omitted

No code changes needed in `src/briefing.py` — the render path already exists at line 613.

### 10.2 — Excel "(approx.)" hint

`src/excel_initiative_tracker_helpers.py` already renders per-row gap text. Find where `missing_requirements` is written to the cell (or wherever the gap content lives). Modify to consume `tier_gap(...).requirement_sources` (parallel-indexed) and append `" (approx.)"` to any requirement where the source is `"proxy"`.

The data flow:
- The Excel helper currently calls `tier_gap(project, target_tier)` somewhere. Confirm by reading the file.
- Update the formatting code to walk `gap.missing_requirements` AND `gap.requirement_sources` together.

Tests in `tests/test_excel_initiative_tracker.py`:
- Build a workbook with one initiative whose gap mixes strict + proxy requirements
- Open the workbook, read the relevant cell, assert "(approx.)" appears next to proxy items only

### 10.3 — Cache for `generate_suggestions`

New behavior: at module level in `src/suggest_initiatives.py`, add a simple cache:

```python
_suggestion_cache: dict[str, tuple[list[InitiativeSuggestion], float]] = {}

def _truth_cache_key(projects: list[dict], target_tier: int | None) -> str:
    """Derive a cache key from a portfolio-truth-derived projects list + target_tier.
    Use the truth's overall hash if available, else fall back to count+target."""
```

Cache key options (pick the cleanest):
- Hash of sorted `[(p['identity']['display_name'], p['identity']['has_git']) for p in projects]` plus `target_tier`. This invalidates when ANY project's name or git status changes.
- Caller passes an explicit `cache_key: str | None = None`. Route handler passes `truth.get("generated_at")`. Simpler, gives callers control.

Prefer the **caller-controlled** approach — clean separation of concerns:

```python
def generate_suggestions(
    projects: list[dict],
    target_tier: int | None = None,
    budget_usd: float = 0.10,
    max_missing: int = 3,
    cache_key: str | None = None,
    force_deterministic: bool = False,  # item 10.4 — fold in here
) -> tuple[list[InitiativeSuggestion], float]:
    """...
    
    If cache_key is provided and a cached result exists for that key, return it.
    Cache is in-process only (no persistence). Lifetime = process lifetime.
    
    force_deterministic=True bypasses the LLM entirely and uses _deterministic_rank.
    Useful when the caller doesn't care about LLM rationale (e.g. accept_suggestion's
    deadline derivation path).
    """
```

Cache lookup:
```python
if cache_key is not None and cache_key in _suggestion_cache:
    return _suggestion_cache[cache_key]

# ... do the work ...

if cache_key is not None:
    _suggestion_cache[cache_key] = (suggestions, cost)
return suggestions, cost
```

Route in `src/serve/routes.py`:
```python
cache_key = f"{truth.get('generated_at', '')}-target={target or 'auto'}"
suggestions, cost = generate_suggestions(
    projects, target_tier=target, budget_usd=0.10, cache_key=cache_key
)
```

Cache size: bounded by distinct `(generated_at, target)` combinations. In practice <10. No eviction needed; if it grows past 100 entries, swap to `functools.lru_cache`-style bounded dict (out of scope for v1).

### 10.4 — `force_deterministic` parameter

Already covered in the 10.3 signature above. The semantics:

- `force_deterministic=True` → skip `_resolve_provider()`, skip the LLM call, skip the CostTracker, go straight to `_deterministic_rank(candidates)`. Returns `(suggestions, 0.0)`.
- `force_deterministic=False` (default) → existing behavior.

Update `accept_suggestion()` to use `force_deterministic=True` instead of `budget_usd=0.0`:

```python
# Before (Sprint 9):
try:
    suggestions, _ = generate_suggestions(projects, target_tier=target, budget_usd=0.0)
except Exception:
    pass  # fall back to "medium"

# After (Sprint 10):
suggestions, _ = generate_suggestions(projects, target_tier=target, force_deterministic=True)
```

The broad `except Exception` becomes unnecessary.

Tests for 10.4:
- `generate_suggestions(..., force_deterministic=True)` returns `(suggestions, 0.0)` without an LLM call (mock provider that would raise if called)
- `accept_suggestion()` uses force_deterministic path; verify the mock provider is NOT called

## Tests target

| Item | New tests |
|---|---|
| 10.1 | ~2-3 (positive + negative briefing render) |
| 10.2 | ~3-5 (mixed strict/proxy, all-strict, all-proxy) |
| 10.3 | ~5-8 (cache hit, miss, key variance, no-key skip) |
| 10.4 | ~5-8 (force_deterministic skips LLM, returns 0.0 cost, accept_suggestion uses new path) |
| **Total** | **~15-24 new tests** |

## Exit criteria

- 10.1: `pytest tests/test_briefing.py -k include_suggestions` shows ≥2 passing tests for positive + negative paths.
- 10.2: Open an Excel workbook with mixed gap sources; the proxy-derived requirements visibly carry "(approx.)" suffix.
- 10.3: A test using a mock provider that raises on second call passes — confirming the cache prevented the second call.
- 10.4: `generate_suggestions(..., force_deterministic=True)` returns `(suggestions, 0.0)` with no LLM call. `accept_suggestion()` no longer has a broad `except Exception` for the budget workaround.
- All exit: 1819 → ~1845+ tests pass; ruff clean.

## Constraints

1. MUST NOT break the existing 1819 tests.
2. Cache is in-process only — no persistence, no cross-request mutation guard needed for the single-operator deployment.
3. `force_deterministic` is opt-in; existing callers default to `False` and see no behavior change.
4. `(approx.)` hint format MUST match the web template (`<span class="approx-hint">(approx.)</span>` rendered as just `(approx.)` in Excel since Excel doesn't render HTML). Suffix-append the literal `" (approx.)"` to the cell text.
5. No new dependencies.
6. Cwd discipline preamble in every subagent brief.

## Critical files

| File | Item(s) |
|---|---|
| `tests/test_briefing.py` | 10.1 |
| `src/excel_initiative_tracker_helpers.py` | 10.2 |
| `tests/test_excel_initiative_tracker.py` | 10.2 |
| `src/suggest_initiatives.py` | 10.3, 10.4 |
| `src/serve/routes.py` | 10.3 (route uses cache_key) |
| `tests/test_suggest_initiatives.py` | 10.3, 10.4 |
| `docs/plans/2026-05-12-arc-g-sprint-10-closeout.md` (new) | 10.5 |

## Verification

```bash
cd /Users/d/Projects/GithubRepoAuditor

# 10.1
python3 -m pytest tests/test_briefing.py -k suggestions -v -p no:cacheprovider | tail -10

# 10.2 — spot-check generated Excel (manual or test fixture)
python3 -m pytest tests/test_excel_initiative_tracker.py -v -p no:cacheprovider | tail -10

# 10.3 — cache hit (run a quick benchmark or check via test)
python3 -m pytest tests/test_suggest_initiatives.py -k cache -v -p no:cacheprovider | tail -10

# 10.4 — force_deterministic
python3 -m pytest tests/test_suggest_initiatives.py -k deterministic -v -p no:cacheprovider | tail -10

# Full suite
python3 -m pytest tests/ -q -p no:cacheprovider 2>&1 | tail -3
python3 -m ruff check src/ tests/ 2>&1 | tail -3
```

## Out of scope

- Persistent cache (cross-process / cross-restart) — keep in-process for v1
- Cache eviction policy — punt until cache grows past ~100 entries
- Briefing route caching (separate concern, lower priority)
- Excel hint styling beyond plain " (approx.)" suffix — keep simple
