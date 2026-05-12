# Arc G — Sprint 11: Persistent cache + cache eviction + dismiss-suggestion + TierGap JSON

**Status:** Drafted 2026-05-12 after Sprint 10 shipped (main `0412464`). Sprint 11 / Arc G addresses the four follow-on items surfaced in Sprint 10's closeout.

## Context

Sprint 10 added an in-process suggestion cache + `force_deterministic` parameter. Two limitations remain:
- Cache evaporates on process restart (every operator session re-pays the LLM cost on first `/initiatives/suggestions` hit).
- Cache is unbounded (cardinality is naturally low, but no safety net).

Sprint 9 + 10 also surfaced operator workflow gaps:
- No way to suppress noisy/wrong suggestions — the LLM may consistently surface a repo the operator has explicitly decided not to invest in.
- `TierGap.requirement_sources` is consumed by web template and Excel sheet but isn't included in any external JSON output, so downstream tooling can't tell strict from proxy.

Sprint 11 closes all four.

## Inventory

| # | Item | Effort | Depends on | Status |
|---|---|---|---|---|
| 11.1 | Persistent suggestion cache — write `_suggestion_cache` to `output/suggestion-cache.json` on update; load on import | small | none | ⏳ |
| 11.2 | Bounded cache eviction — LRU-style; default max 100 entries, evict oldest when exceeded | small | 11.1 | ⏳ |
| 11.3 | `(approx.)` hint in `TierGap` JSON serialization — add `to_dict()` method to `TierGap` exposing `requirement_sources` | tiny | none | ⏳ |
| 11.4 | `--dismiss-suggestion REPO [--reason TEXT]` CLI flag + dismissal list at `output/dismissed-suggestions.json`; `narrow_candidates()` filters dismissed repos; web "Dismiss" button on suggestion cards | medium | 11.1 (pattern reuse) | ⏳ |
| 11.5 | Sprint 11 closeout + PR | small | 11.1-11.4 | ⏳ |

**Test count target:** 1841 → ~1885 (+35-50 new tests).

## Subagent dispatch

Two Sonnet subagents, sequential (because 11.1 + 11.2 + 11.3 all touch `src/suggest_initiatives.py` or `src/maturity_tiers.py`, and 11.4 builds on the persistence pattern from 11.1).

- **Wave 1 Agent A** — items 11.1 + 11.2 + 11.3. Persistence + eviction + JSON-serialize the TierGap source list.
- **Wave 2 Agent B** — item 11.4. `--dismiss-suggestion` workflow. Reuses 11.1's atomic-write pattern.

Closeout (lead): 11.5.

**Brief discipline:** cwd preamble mandatory (Sprint 8/10 retro: cwd has shifted on the lead twice now during cherry-pick).

## Schema + code references

### 11.1 — Persistent suggestion cache

`src/suggest_initiatives.py` currently has:
```python
_suggestion_cache: dict[str, tuple[list[InitiativeSuggestion], float]] = {}
```

Convert to disk-backed. Pattern mirrors `src/operator_prefs.py` (Sprint 3.3) and `src/initiatives.py` (Sprint 7A):

- File path: `output/suggestion-cache.json`. Path is configurable via `output_dir` parameter; default falls back to `Path("output")`.
- File schema (versioned):
  ```json
  {
    "version": 1,
    "entries": [
      {
        "cache_key": "2026-05-12T12:34:56Z|target=auto",
        "suggestions": [<InitiativeSuggestion.to_dict() outputs>],
        "cost_usd": 0.0042,
        "stored_at": "2026-05-12T12:35:00Z"
      },
      ...
    ]
  }
  ```
- Atomic tmp+rename write (mirror `_write_atomic` from `src/operator_prefs.py`).
- Load on `generate_suggestions` first cache lookup (lazy, not at import time) so test isolation stays clean.

`InitiativeSuggestion` (Sprint 8.4) is a frozen dataclass — add `to_dict()` and `from_dict()` methods for JSON serialization. Trivial.

New API:
```python
def suggestion_cache_path(output_dir: Path) -> Path: ...
def load_suggestion_cache(path: Path) -> dict[str, tuple[list[InitiativeSuggestion], float]]: ...
def save_suggestion_cache(path: Path, cache: dict) -> None: ...
def clear_suggestion_cache(path: Path | None = None) -> None:
    """Drop in-memory cache. If path is provided, also delete the file."""
```

Update `generate_suggestions()`:
- Add `output_dir: Path | None = None` parameter (default None = no persistence; mirrors existing `cache_key` opt-in semantics).
- When `output_dir is not None and cache_key is not None`: load cache from disk on first miss, write to disk on every set.
- The in-memory dict is the primary cache. Disk is the warming layer that survives restarts.

Route in `src/serve/routes.py`:
```python
suggestions, cost = generate_suggestions(
    projects,
    target_tier=target,
    budget_usd=0.10,
    cache_key=cache_key,
    output_dir=output_dir,  # NEW — pass through for persistence
)
```

### 11.2 — Bounded cache eviction

When the in-memory `_suggestion_cache` grows past 100 entries, evict the OLDEST entry by insertion order (not LRU — simpler, and cardinality is bounded by `(generated_at, target)` tuples which churn slowly).

Use `collections.OrderedDict`:
```python
from collections import OrderedDict
_suggestion_cache: OrderedDict[str, tuple[list[InitiativeSuggestion], float]] = OrderedDict()
_CACHE_MAX_SIZE = 100

# On insert:
if cache_key in _suggestion_cache:
    _suggestion_cache.move_to_end(cache_key)
_suggestion_cache[cache_key] = (suggestions, cost)
if len(_suggestion_cache) > _CACHE_MAX_SIZE:
    _suggestion_cache.popitem(last=False)  # FIFO eviction
```

The on-disk cache file also has a soft cap — when serializing, only persist the most recent 100 entries.

### 11.3 — `TierGap.to_dict()` with `requirement_sources`

`src/maturity_tiers.py` `TierGap` is a frozen dataclass. Add:

```python
@dataclass(frozen=True)
class TierGap:
    current_tier: int
    target_tier: int
    missing_requirements: list[str]
    requirement_sources: list[Literal["strict", "proxy"]] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        """JSON-safe representation including parallel-indexed requirement_sources."""
        return {
            "current_tier": self.current_tier,
            "target_tier": self.target_tier,
            "missing_requirements": list(self.missing_requirements),
            "requirement_sources": list(self.requirement_sources),
        }
```

Also a `from_dict()` classmethod for symmetry (used by 11.1's serialization paths if any TierGap state crosses the cache boundary).

### 11.4 — `--dismiss-suggestion REPO` flag + dismissal list

New module data + functions in `src/suggest_initiatives.py` (or new `src/dismissed_suggestions.py` if it grows too large — start in same module, factor out if needed):

```python
@dataclass(frozen=True)
class DismissedSuggestion:
    repo_name: str
    reason: str          # operator-provided, default ""
    dismissed_at: str    # ISO timestamp
    dismissed_by: str    # operator_identity()

def dismissed_path(output_dir: Path) -> Path:
    """output_dir / 'dismissed-suggestions.json'."""

def load_dismissed(path: Path) -> list[DismissedSuggestion]:
    """Read versioned JSON; missing/malformed → []."""

def save_dismissed(path: Path, items: list[DismissedSuggestion]) -> None:
    """Atomic tmp+rename write. Schema {"version": 1, "items": [...]}."""

def dismiss_suggestion(path: Path, repo_name: str, reason: str = "") -> DismissedSuggestion:
    """Add or replace by repo_name (idempotent). Returns the recorded entry."""

def undo_dismiss(path: Path, repo_name: str) -> bool:
    """Remove dismissal entry for repo_name. Returns True if removed, False if not present."""
```

**Integration with `narrow_candidates`:**
```python
def narrow_candidates(
    projects: list[dict],
    target_tier: int | None = None,
    max_missing: int = 3,
    dismissed: set[str] | None = None,   # NEW — set of dismissed repo_names
) -> list[tuple[dict, int, TierGap]]:
    """... existing logic ...
    
    If `dismissed` contains a project's repo_name, skip it.
    """
```

`generate_suggestions()` accepts an `output_dir` parameter (from 11.1); when set, it loads `dismissed-suggestions.json` and passes the resulting set to `narrow_candidates`. When `output_dir` is None, no dismissal filtering occurs (backward-compatible).

**CLI flags in `src/cli.py`** (triage subparser + legacy build_parser, mirroring Sprint 9.1's dual registration):
```python
p.add_argument(
    "--dismiss-suggestion",
    type=str,
    default=None,
    metavar="REPO",
    help="Suppress repo from future LLM-suggested initiatives",
)
p.add_argument(
    "--reason",
    type=str,
    default="",
    help="Reason for dismissal (with --dismiss-suggestion)",
)
p.add_argument(
    "--undo-dismiss",
    type=str,
    default=None,
    metavar="REPO",
    help="Restore a dismissed repo to the suggestion pool",
)
p.add_argument(
    "--list-dismissed",
    action="store_true",
    help="List currently dismissed suggestion repos",
)
```

Dispatcher near existing initiative handlers:
```python
if getattr(args, "dismiss_suggestion", None):
    _run_dismiss_suggestion_mode(args)
    return
if getattr(args, "undo_dismiss", None):
    _run_undo_dismiss_mode(args)
    return
if getattr(args, "list_dismissed", False):
    _run_list_dismissed_mode(args)
    return
```

**Web "Dismiss" button:**

In `src/serve/templates/initiatives_suggestions.html` — add a small "Dismiss" link/button next to each suggestion card's Accept form:

```html
<form
  hx-post="/initiatives/suggestions/dismiss"
  hx-target="#suggestion-{{ loop.index }}"
  hx-swap="outerHTML"
  hx-confirm="Dismiss {{ s.repo_name }} from future suggestions?"
  class="dismiss-form"
>
  <input type="hidden" name="repo_name" value="{{ s.repo_name }}">
  <button type="submit" class="btn-secondary">Dismiss</button>
</form>
```

New POST route in `src/serve/routes.py`:
```python
@router.post("/initiatives/suggestions/dismiss", response_class=HTMLResponse)
async def dismiss_suggestion_route(
    request: Request,
    repo_name: str = Form(...),
    reason: str = Form(""),
) -> HTMLResponse:
    """Dismiss a suggestion. Returns HTMX partial."""
    from src.suggest_initiatives import dismiss_suggestion, dismissed_path
    
    output_dir = _output_dir(request)
    try:
        entry = dismiss_suggestion(dismissed_path(output_dir), repo_name, reason)
    except ValueError as exc:
        import html as _html
        return HTMLResponse(
            f'<div class="suggestion-card accept-error">Error: {_html.escape(str(exc))}</div>',
            status_code=400,
        )
    
    import html as _html
    return HTMLResponse(
        f'<div class="suggestion-card dismissed">'
        f'✗ Dismissed: {_html.escape(entry.repo_name)}. '
        f'<a href="/initiatives/suggestions">Refresh suggestions →</a>'
        f'</div>'
    )
```

After dismissing a repo, the operator can refresh `/initiatives/suggestions` and the repo will not reappear (filtered out by `narrow_candidates`).

## Tests target

| Item | New tests |
|---|---|
| 11.1 | ~10 (load/save round-trip, missing file, malformed JSON, atomic write, output_dir threading through generate_suggestions) |
| 11.2 | ~5 (cap at 100, FIFO eviction, move_to_end on hit) |
| 11.3 | ~3 (to_dict round-trip, requirement_sources preserved, empty TierGap shape) |
| 11.4 | ~15-20 (dismiss/undo/list CLI happy/error paths, narrow_candidates filters dismissed, web POST happy/error/HTML-escape, dismissed repo doesn't reappear after refresh) |
| **Total** | **~33-38 new tests** |

## Exit criteria

- 11.1: `output/suggestion-cache.json` exists after `audit triage --suggest-initiatives` (when run with `--output-dir` pointing to a writable dir). Subsequent runs in a new process read the cache and skip LLM calls for matching `cache_key`.
- 11.2: Cache holding >100 entries (forced via test) evicts oldest entry on each new insert.
- 11.3: `tier_gap(...).to_dict()` returns a dict containing `requirement_sources` list. Round-trips cleanly via `TierGap.from_dict()`.
- 11.4: `audit triage --dismiss-suggestion Wavelength` writes to `output/dismissed-suggestions.json`. Subsequent `--suggest-initiatives` invocation does NOT surface Wavelength. `--undo-dismiss Wavelength` restores it. `--list-dismissed` prints a table.
- 11.4 (web): `POST /initiatives/suggestions/dismiss` with valid `repo_name` returns 200 + dismissal partial. `GET /initiatives/suggestions` after a dismissal does not include the dismissed repo.
- All exit: 1841 → ~1885+ tests; ruff clean.

## Constraints

1. MUST NOT break the existing 1841 tests. All persistence changes are additive (file absent → empty list; pre-existing in-memory cache continues to work without `output_dir`).
2. Atomic file writes (tmp + rename) mirror Sprint 7A's pattern in `src/operator_prefs.py`. Never half-write JSON.
3. Cache file schema is versioned (`"version": 1`). Future schema changes are additive.
4. Dismissal is operator-scoped — `set_by = operator_identity()` (Sprint 7A pattern). Single-operator deployment; no cross-user logic needed.
5. Dismissed repos are filtered by `narrow_candidates` ONLY when `output_dir` is passed through. When `output_dir is None`, no filtering — preserves test isolation.
6. Cache + dismiss-list are separate files (`suggestion-cache.json` vs `dismissed-suggestions.json`). Independent invalidation paths.
7. **No CLI surface for `force_deterministic`** (lesson from Sprint 10) — same applies to `output_dir` and any cache-internal parameters. Keep internal-only.
8. Cwd discipline preamble in every subagent brief.

## Critical files

| File | Item(s) |
|---|---|
| `src/suggest_initiatives.py` | 11.1, 11.2, 11.4 |
| `src/maturity_tiers.py` | 11.3 |
| `src/cli.py` | 11.4 (CLI flags + dispatchers) |
| `src/serve/routes.py` | 11.1 (output_dir passthrough), 11.4 (dismiss route) |
| `src/serve/templates/initiatives_suggestions.html` | 11.4 (dismiss form) |
| `tests/test_suggest_initiatives.py` | 11.1, 11.2, 11.4 |
| `tests/test_maturity_tiers.py` | 11.3 |
| `tests/test_initiatives_suggestions_route.py` | 11.4 (web dismiss flow) |
| `docs/plans/2026-05-12-arc-g-sprint-11-closeout.md` (new) | 11.5 |

## Verification

```bash
cd /Users/d/Projects/GithubRepoAuditor

# 11.1 — persistent cache round-trip
mkdir -p /tmp/sprint11-test/output
unset ANTHROPIC_API_KEY GITHUB_TOKEN
python3 -m src triage saagpatel --suggest-initiatives --output-dir /tmp/sprint11-test/output 2>&1 | head -5
ls /tmp/sprint11-test/output/suggestion-cache.json
python3 -c "
import json
d = json.load(open('/tmp/sprint11-test/output/suggestion-cache.json'))
print(f'version={d[\"version\"]}, entries={len(d[\"entries\"])}')"

# 11.4 — dismiss workflow
python3 -m src triage saagpatel --dismiss-suggestion FakeRepo --reason 'test' --output-dir /tmp/sprint11-test/output
python3 -m src triage saagpatel --list-dismissed --output-dir /tmp/sprint11-test/output
python3 -m src triage saagpatel --undo-dismiss FakeRepo --output-dir /tmp/sprint11-test/output

# 11.3 — TierGap JSON
python3 -c "
from src.maturity_tiers import TierGap
g = TierGap(current_tier=1, target_tier=2, missing_requirements=['x', 'y'], requirement_sources=['strict', 'proxy'])
print(g.to_dict())
g2 = TierGap.from_dict(g.to_dict())
assert g == g2, 'round-trip failed'
print('TierGap round-trip OK')"

# Web dismiss
python3 -m src serve --port 8765 --host 127.0.0.1 &
SERVER_PID=$!
sleep 4
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8765/initiatives/suggestions/dismiss -d "repo_name=Test" -d "reason=noise"
kill $SERVER_PID

# Full suite
python3 -m pytest tests/ -q -p no:cacheprovider 2>&1 | tail -3
python3 -m ruff check src/ tests/ 2>&1 | tail -3
```

## Out of scope

- Persistent dismissal "undo history" (currently overwrites in place — no audit trail)
- Auto-expire dismissals after N days
- Dismiss propagation to `accept_suggestion` (dismissed repos should NOT be accept-able either — but accept_suggestion is called manually; operator decides)
- Web "Undo dismiss" button (operator can `audit triage --undo-dismiss REPO`)
- Cache compression / pruning of very old entries beyond the 100-entry cap
