# Arc G — Sprint 13: Dismissal follow-ons + suggestion cache TTL

**Status:** Drafted 2026-05-12 after Sprint 12 shipped (main `cc86269`). Sprint 13 closes the four follow-on items deferred from Sprint 12 closeout.

## Context

Sprint 12 landed dismissal lifecycle (auto-expire + audit trail), web Undo, briefing surface, and tier-gap JSON export. Closeout flagged four follow-ons:

- **13.1** Web `/initiatives/dismissal-history` view — `--dismissal-history` is CLI-only today; web parity helps operators who live in the dashboard.
- **13.2** Auto-purge old `DismissalEvent` entries beyond bounded log size — Sprint 12.1 introduced events but the log grows unbounded.
- **13.3** Briefing → web cross-link for the dismissals section — operators reading the briefing markdown have no path to the web Undo page.
- **13.4** Persistent suggestion cache TTL — Sprint 11.1 cache survives across runs indefinitely; cache entries older than N days should be evicted.

Skip bulk-dismiss (low operator value, premature mass action).

## Inventory

| # | Item | Effort | Depends on | Status |
|---|---|---|---|---|
| 13.1 | Web `/initiatives/dismissal-history` view (CLI parity) | medium | none | ⏳ |
| 13.2 | Auto-purge old `DismissalEvent` entries beyond bounded log size | small-medium | none | ⏳ |
| 13.3 | Briefing → web cross-link for dismissals section | small | none | ⏳ |
| 13.4 | Persistent suggestion cache TTL | small-medium | none | ⏳ |
| 13.5 | Sprint 13 closeout + PR | small | 13.1-13.4 | ⏳ |

**Test count target:** 1965 → ~2010 (+30-45 new tests).

## Subagent dispatch plan

### Wave 1 — one Haiku subagent (read-only)

- **Agent S — scope confirmation.** Greps for: `DismissalEvent` persistence path in `src/suggest_initiatives.py`, current cache TTL/purge surface, `/initiatives/*` route ordering in `src/serve/routes.py`, briefing dismissals render block in `src/briefing.py`. Reports code locations + any surprises that would change the Wave 2 dispatch.

### Wave 2 — three parallel Sonnet subagents (isolation: worktree)

- **Agent A — Item 13.1** (web history view). Touches `src/serve/routes.py`, new `src/serve/templates/initiatives_dismissal_history.html`, `src/serve/templates/base.html` (nav). Tests in `tests/test_initiatives_dismissed_route.py` or similar.
- **Agent B — Items 13.2 + 13.4** (both modify `src/suggest_initiatives.py`). Bounded event log via `_MAX_DISMISSAL_EVENTS` constant + auto-trim on save. Cache TTL via new `_CACHE_TTL_DAYS` constant + eviction on load. Tests in `tests/test_suggest_initiatives.py`.
- **Agent C — Item 13.3** (briefing cross-link). Touches `src/briefing.py` only. Add web URL line to the "Currently Dismissed" markdown section. Tests in `tests/test_briefing.py`.

Agent A + B + C have minimal file overlap (only `tests/` collisions, and those are separate test files).

### Closeout (lead)

- Item 13.5 — closeout doc + PR + merge. Apply `/verify` skill (Playwright MCP) for `/initiatives/dismissal-history` and `/code-review` skill (mandatory for ~400+ LoC diff).

## Schema + code references

### 13.1 — Web `/initiatives/dismissal-history`

**New GET route** in `src/serve/routes.py`:

```python
@router.get("/initiatives/dismissal-history", response_class=HTMLResponse)
async def initiatives_dismissal_history(request: Request) -> HTMLResponse:
    """Show chronological audit trail of dismiss/undo/expire events (Arc G S13.1)."""
    from src.suggest_initiatives import dismissed_path, load_dismissal_events
    output_dir = _output_dir(request)
    events = load_dismissal_events(dismissed_path(output_dir))
    # Newest first
    rows = sorted(
        ({"repo_name": e.repo_name, "event_type": e.event_type,
          "occurred_at": e.occurred_at, "actor": e.actor, "reason": e.reason}
         for e in events),
        key=lambda r: r["occurred_at"], reverse=True,
    )
    return templates.TemplateResponse(
        request, "initiatives_dismissal_history.html",
        {"rows": rows, "count": len(rows)},
    )
```

Route MUST be declared BEFORE the parametric `/initiatives/{repo_name}/gap` route (Sprint 12.2 lesson).

**New template `src/serve/templates/initiatives_dismissal_history.html`** modeled after `initiatives_dismissed.html`:
- Header: "Dismissal History" + count
- Empty state: "No dismissal events recorded."
- Table columns: REPO | EVENT | OCCURRED AT | ACTOR | REASON
- Back-links to `/initiatives/dismissed` and `/initiatives/suggestions`

**Nav link** in `base.html`: optional — discuss with operator preference. Default: link from `/initiatives/dismissed` page footer rather than top-nav (top-nav already crowded).

### 13.2 — Auto-purge old `DismissalEvent` entries

In `src/suggest_initiatives.py`:

```python
_MAX_DISMISSAL_EVENTS = 1000  # cap log size; oldest events trimmed first
```

`save_dismissed(path, items, events)` (or whatever helper writes the v2 schema): before serializing, if `len(events) > _MAX_DISMISSAL_EVENTS`, keep only the most recent N events (sort by `occurred_at`, take tail). Add a one-line audit event `{"event_type": "log_trimmed", "occurred_at": now(), "actor": "system", "reason": f"trimmed to {_MAX_DISMISSAL_EVENTS} events"}` so operators see when truncation happened — but trim BEFORE adding the log-trimmed event to avoid recursion.

Tests:
- `_MAX_DISMISSAL_EVENTS + 5` events written → exactly `_MAX_DISMISSAL_EVENTS` events persisted + one `log_trimmed` event recorded.
- Trim preserves chronological newest-first; oldest 5 are gone.

### 13.3 — Briefing → web cross-link

In `src/briefing.py` `render_markdown(briefing)`, the existing "## Currently Dismissed" section. After the bullet list, add:

```markdown
_See [web view] for Undo or [history view] for audit trail._
```

Concrete URLs: `http://127.0.0.1:8765/initiatives/dismissed` and `http://127.0.0.1:8765/initiatives/dismissal-history` (using the default serve host/port — operators running on a different port will know to substitute).

Alternative: skip absolute URLs and just write `/initiatives/dismissed` and `/initiatives/dismissal-history` as paths. Cleaner for operators who reverse-proxy the dashboard. **Choose this — paths only.**

Update `render_voice` similarly if applicable, or leave voice format alone (it's terser by design).

### 13.4 — Persistent suggestion cache TTL

In `src/suggest_initiatives.py`, the persistent cache (Sprint 11.1) stores `{"version": 1, "entries": {cache_key: {"timestamp": ISO8601, "suggestions": [...]}, ...}}` in `output/suggestion-cache.json`.

```python
_CACHE_TTL_DAYS = 30  # entries older than this are evicted on load
```

In `load_suggestion_cache(path)` (or wherever the persistent cache is read): after loading, walk entries, drop any whose `timestamp` is older than `today - _CACHE_TTL_DAYS`. If anything was evicted, save the trimmed cache back atomically.

Alternative: lazy TTL check on `lookup` only. **Reject — purge on load keeps the file size bounded without requiring lookup pressure.**

Tests:
- Cache with 5 fresh entries + 3 stale (35-day-old) entries → load returns 5 fresh, file rewritten with 5 fresh.
- All entries stale → load returns empty cache, file rewritten as empty.
- All fresh → no rewrite (avoid unnecessary disk write).

## Tests target

| Item | New tests |
|---|---|
| 13.1 | ~8-10 (route happy path, empty state, route ordering, template renders all event types) |
| 13.2 | ~6-8 (trim at boundary, log_trimmed event recorded, chronological preservation) |
| 13.3 | ~3-5 (markdown contains cross-link, paths not absolute URLs) |
| 13.4 | ~8-10 (TTL eviction on load, all-stale, all-fresh no-rewrite, file rewrite atomic) |
| **Total** | **~30-45 new tests** |

## Exit criteria

- 13.1: `GET /initiatives/dismissal-history` returns 200 with chronological event table. Empty when no events. Route declared before parametric routes.
- 13.2: After writing > `_MAX_DISMISSAL_EVENTS` events, file contains exactly that many + one `log_trimmed` event. Oldest events dropped.
- 13.3: `audit triage --briefing --include-suggestions` markdown contains `/initiatives/dismissed` and `/initiatives/dismissal-history` paths inside the "## Currently Dismissed" section.
- 13.4: `output/suggestion-cache.json` entries older than 30 days are evicted on next CLI invocation that loads the cache. File rewritten atomically.
- All exit: 1965 → ~2000+ tests pass; ruff clean.

## Constraints

1. MUST NOT break the existing 1965 tests.
2. Schema additions are additive — no breaking changes to `dismissed-suggestions.json` v2 or `suggestion-cache.json` v1.
3. Atomic tmp+rename for all file writes.
4. Auto-trim and auto-purge are silent on the happy path. No CLI output unless operator runs verbose mode.
5. Web Dismissal History route is read-only — no mutation buttons. Operators undo via `/initiatives/dismissed` (already shipped Sprint 12).
6. Briefing cross-link uses paths (not absolute URLs) — reverse-proxy compatibility.
7. Cache TTL = 30 days, event log cap = 1000. Both are constants in `src/suggest_initiatives.py`, not CLI-configurable in v1.
8. No new dependencies.
9. Cwd discipline preamble + "always `git add` closeout immediately" note in every subagent brief.
10. Route ordering: new `/initiatives/dismissal-history` BEFORE `/initiatives/{repo_name}/gap`.
11. Parallel-wave coordination: Agent B owns both 13.2 + 13.4 to avoid `src/suggest_initiatives.py` conflicts.

## Critical files

| File | Item(s) |
|---|---|
| `src/serve/routes.py` | 13.1 |
| `src/serve/templates/initiatives_dismissal_history.html` (new) | 13.1 |
| `src/serve/templates/initiatives_dismissed.html` | 13.1 (back-link from existing page) |
| `src/suggest_initiatives.py` | 13.2, 13.4 |
| `src/briefing.py` | 13.3 |
| `tests/test_*.py` | all items |
| `docs/plans/2026-05-12-arc-g-sprint-13-closeout.md` (new) | 13.5 |

## Verification

```bash
cd /Users/d/Projects/GithubRepoAuditor

# 13.1 — web dismissal history page
python3 -m src serve --port 8765 --host 127.0.0.1 &
SERVER_PID=$!; sleep 4
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8765/initiatives/dismissal-history  # 200
kill $SERVER_PID

# 13.2 — bounded event log
python3 -c "
from pathlib import Path
from src.suggest_initiatives import _MAX_DISMISSAL_EVENTS
print(f'cap = {_MAX_DISMISSAL_EVENTS}')
"

# 13.3 — briefing cross-link
python3 -m src triage saagpatel --briefing --include-suggestions --output-dir output 2>&1 | grep -A2 "Currently Dismissed"

# 13.4 — cache TTL
python3 -c "
from src.suggest_initiatives import _CACHE_TTL_DAYS
print(f'ttl_days = {_CACHE_TTL_DAYS}')
"

# Full suite
python3 -m pytest tests/ -q -p no:cacheprovider 2>&1 | tail -3
python3 -m ruff check src/ tests/ 2>&1 | tail -3
```

Pre-merge: `/code-review` skill on Sprint 13 diff. `/verify` skill (Playwright MCP) for new page.

## Out of scope

- Bulk dismiss / bulk undo from web
- CLI flags for `_MAX_DISMISSAL_EVENTS` and `_CACHE_TTL_DAYS` (constants for v1; revisit if operators ask)
- Auto-expire heuristics based on repo activity
- Persistent storage for tier-gap snapshots over time
